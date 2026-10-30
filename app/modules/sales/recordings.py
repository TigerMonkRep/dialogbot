"""Call recordings of Dialogbot's own sales calls (phase 4).

Vapi records every call unless the assistant says otherwise (`artifactPlan.recordingEnabled` defaults to true –
docs.vapi.ai/assistants/call-recording, read 30 October 2026). So Peter's assistant always sets it explicitly: on only
when SALES_RECORDING_STORAGE is not `none` AND the campaign has `recording_enabled`, and then the opening says so.

After the end-of-call report the file is fetched with the private API key from `GET /call/{id}/mono-recording`, which
answers with a 302 to a short-lived signed URL (docs.vapi.ai/assistants/retrieve-call-artifacts), and stored in a
PRIVATE Supabase Storage bucket under `sales/calls/<call_id>.<ext>`. Playback goes through a signed URL that lives at
most 10 minutes and every play/export is logged. Vapi offers no documented way to stop recording mid-call, so an
objection ("jeg vil ikke optages") is honoured by never fetching the file and asking Vapi to delete the call
(`DELETE /call/{id}`, which erases its recordings).
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime

import httpx
import structlog
from sqlalchemy import select
from sqlalchemy.orm import Session as OrmSession

from app.config import get_settings
from app.core.errors import ApiError
from app.models import Call, CallRecording, Campaign, SalesCallEvent, SalesMediaAccessLog

log = structlog.get_logger("dialogbot.sales.recordings")

DISCLOSURE = "Samtalen bliver optaget til kvalitetssikring – sig til, hvis du ikke ønsker det."
SIGNED_SECONDS = 600
MAX_BYTES = 60 * 1024 * 1024
EXT = {"audio/wav": "wav", "audio/x-wav": "wav", "audio/wave": "wav", "audio/mpeg": "mp3", "audio/mp3": "mp3"}


class RecordingUnavailable(ApiError):
    status_code = 409
    code = "recording_unavailable"


def storage_on() -> bool:
    return get_settings().sales_recording_storage != "none"


def enabled(c: Campaign) -> bool:
    return storage_on() and bool(c.recording_enabled)


def artifact_plan(c: Campaign) -> dict:
    return {"recordingEnabled": enabled(c)}


# --------------------------------------------------------------------------- storage backend (private bucket)


class SupabaseBucket:
    def _url(self, path: str) -> tuple[str, dict]:
        s = get_settings()
        return (f"{s.supabase_url.rstrip('/')}/storage/v1/object/{path}",
                {"authorization": f"Bearer {s.supabase_service_role_key}", "apikey": s.supabase_service_role_key})

    def put(self, key: str, data: bytes, content_type: str) -> None:
        url, h = self._url(f"{get_settings().sales_recording_bucket}/{key}")
        r = httpx.post(url, content=data, headers=h | {"content-type": content_type, "x-upsert": "true"}, timeout=120.0)
        if r.status_code >= 400:
            raise ApiError(f"Lagring af lyd fejlede ({r.status_code})", code="recording_storage_failed")

    def signed_url(self, key: str, seconds: int, download: bool) -> str:
        s = get_settings()
        url, h = self._url(f"sign/{s.sales_recording_bucket}/{key}")
        r = httpx.post(url, json={"expiresIn": seconds}, headers=h, timeout=20.0)
        if r.status_code >= 400:
            raise ApiError(f"Kunne ikke lave et afspilningslink ({r.status_code})", code="recording_storage_failed")
        signed = r.json().get("signedURL") or r.json().get("signedUrl") or ""
        full = f"{s.supabase_url.rstrip('/')}/storage/v1{signed}"
        return full + ("&download=" if download and "?" in full else "")

    def delete(self, key: str) -> None:
        url, h = self._url(get_settings().sales_recording_bucket)
        r = httpx.request("DELETE", url, json={"prefixes": [key]}, headers=h, timeout=60.0)
        if r.status_code >= 400:
            raise ApiError(f"Sletning af lyd fejlede ({r.status_code})", code="recording_storage_failed")


_backend = None


def set_backend_override(b) -> None:
    """Test hook: an object with put/signed_url/delete."""
    global _backend
    _backend = b


def backend():
    return _backend or SupabaseBucket()


def _vapi(method: str, path: str, **kw) -> httpx.Response:
    s = get_settings()
    return httpx.request(method, f"{s.vapi_api_url.rstrip('/')}{path}", headers={"authorization": f"Bearer {s.vapi_api_key}"},
                         timeout=60.0, **kw)


_vapi_override = None


def set_vapi_override(fn) -> None:
    """Test hook: fn(method, path, **kw) -> httpx.Response."""
    global _vapi_override
    _vapi_override = fn


def vapi(method: str, path: str, **kw) -> httpx.Response:
    return (_vapi_override or _vapi)(method, path, **kw)


# --------------------------------------------------------------------------- lifecycle


def objected(db: OrmSession, campaign_contact_id: uuid.UUID, provider_call_id: str) -> bool:
    return db.scalar(select(SalesCallEvent.id).where(SalesCallEvent.campaign_contact_id == campaign_contact_id,
                                                     SalesCallEvent.provider_call_id == provider_call_id,
                                                     SalesCallEvent.event_type == "recording_objection")) is not None


def on_report(db: OrmSession, call: Call, campaign: Campaign, campaign_contact_id: uuid.UUID) -> None:
    """After the end-of-call report: queue the download, or record why there is no audio."""
    from app.core.outbox import enqueue

    rec = db.scalar(select(CallRecording).where(CallRecording.call_id == call.id))
    if rec is None:
        rec = CallRecording(call_id=call.id, status="PENDING", provider_ref=call.provider_call_id)
        db.add(rec)
        db.flush()
    if not enabled(campaign):
        rec.status, call.recording_status = "NOT_RECORDED", "NOT_RECORDED"
        return
    if objected(db, campaign_contact_id, call.provider_call_id):
        rec.status, rec.deleted_at, rec.delete_reason = "DELETED", datetime.now(UTC), "objection"
        call.recording_status = "DELETED"
        delete_at_vapi(call.provider_call_id)
        return
    if rec.status in ("AVAILABLE", "DELETED"):
        return
    call.recording_status = "PENDING"
    enqueue(db, event_type="sales.recording_fetch", dedupe_key=f"sales_recording:{call.id}",
            payload={"call_id": str(call.id)})


def fetch(db: OrmSession, call_id: uuid.UUID) -> CallRecording | None:
    """Worker: download from Vapi (302 → signed URL) and store privately. Raises on a retryable failure."""
    call = db.get(Call, call_id)
    rec = db.scalar(select(CallRecording).where(CallRecording.call_id == call_id))
    if call is None or rec is None or rec.status != "PENDING":
        return rec
    r = vapi("GET", f"/call/{call.provider_call_id}/mono-recording", follow_redirects=True)
    if r.status_code == 404:
        rec.status, call.recording_status = "FAILED", "FAILED"
        rec.delete_reason = "Vapi har ingen optagelse af opkaldet"
        return rec
    if r.status_code >= 400:
        raise ApiError(f"Vapi svarede {r.status_code} på optagelsen", code="recording_fetch_failed")
    data = r.content
    if not data or len(data) > MAX_BYTES:
        rec.status, call.recording_status = "FAILED", "FAILED"
        rec.delete_reason = "Tom eller for stor lydfil"
        return rec
    ctype = (r.headers.get("content-type") or "audio/wav").split(";")[0].strip().lower()
    key = f"sales/calls/{call.id}.{EXT.get(ctype, 'wav')}"
    backend().put(key, data, ctype if ctype in EXT else "audio/wav")
    rec.status, rec.storage_key, rec.bytes, rec.content_type = "AVAILABLE", key, len(data), ctype
    rec.duration_seconds, rec.available_at = call.duration_seconds, datetime.now(UTC)
    call.recording_status = "AVAILABLE"
    return rec


def handle_fetch(db: OrmSession, ev) -> None:
    fetch(db, uuid.UUID(ev.payload["call_id"]))


def delete(db: OrmSession, rec: CallRecording, reason: str) -> None:
    if rec.status == "AVAILABLE" and rec.storage_key:
        backend().delete(rec.storage_key)
    rec.status, rec.deleted_at, rec.delete_reason = "DELETED", datetime.now(UTC), reason
    call = db.get(Call, rec.call_id)
    if call is not None:
        call.recording_status = "DELETED"


def delete_at_vapi(provider_call_id: str | None) -> bool:
    """Ask Vapi to delete the call (and its recordings). Best effort: a failure is logged, not raised."""
    if not provider_call_id or not get_settings().vapi_api_key:
        return False
    try:
        r = vapi("DELETE", f"/call/{provider_call_id}")
    except httpx.HTTPError:
        log.warning("sales.vapi_delete_failed", call=provider_call_id, error="unreachable")
        return False
    if r.status_code >= 400:
        log.warning("sales.vapi_delete_failed", call=provider_call_id, status=r.status_code)
        return False
    return True


def play_url(db: OrmSession, call: Call, user_id: uuid.UUID, *, export: bool) -> dict:
    rec = db.scalar(select(CallRecording).where(CallRecording.call_id == call.id))
    if rec is None or rec.status != "AVAILABLE" or not rec.storage_key:
        raise RecordingUnavailable(f"Ingen lyd: {(rec.status if rec else call.recording_status)}")
    url = backend().signed_url(rec.storage_key, SIGNED_SECONDS, export)
    db.add(SalesMediaAccessLog(call_id=call.id, user_id=user_id, kind="export" if export else "play"))
    return {"url": url, "expires_in": SIGNED_SECONDS, "content_type": rec.content_type}


def out(rec: CallRecording | None) -> dict | None:
    if rec is None:
        return None
    return {"status": rec.status, "bytes": rec.bytes, "duration_seconds": rec.duration_seconds,
            "content_type": rec.content_type, "available_at": rec.available_at.isoformat() if rec.available_at else None,
            "deleted_at": rec.deleted_at.isoformat() if rec.deleted_at else None, "delete_reason": rec.delete_reason}
