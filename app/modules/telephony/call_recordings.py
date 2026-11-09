"""Recordings of customers' own calls: the customer turns recording on per number, callers are told in the greeting,
and the customer listens to the call under «Opkald» next to the transcript.

Vapi records every call unless the assistant says otherwise (`artifactPlan.recordingEnabled` defaults to true), so the
inbound assistant always sets it explicitly: on only when the number has `record_calls` AND recording storage is
configured (SALES_RECORDING_STORAGE). Then the greeting says so in the caller's language. After the end-of-call report
the audio is fetched by the worker (same path as Dialogbot's own sales calls, sales.recordings) into the private bucket
under `calls/<workspace_id>/<call_id>.<ext>`. Playback is a signed URL that lives 10 minutes, and every play/download
is logged. The audio is deleted after the number's `recording_retention_days` (daily, with the sales retention run),
or when the customer deletes it; then Vapi is asked to delete its copy too.
"""
from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime, timedelta

import structlog
from sqlalchemy import select
from sqlalchemy.orm import Session as OrmSession

from app.core.errors import ApiError
from app.models import Call, CallRecording, PhoneNumber
from app.modules.sales import recordings

log = structlog.get_logger("dialogbot.telephony.recordings")

RETENTION_CHOICES = (7, 30, 90, 180, 365)
EVENT = "calls.recording_fetch"

DISCLOSURE = {
    "da": "Samtalen bliver også optaget.",
    "en": "This call is also recorded.",
    "de": "Das Gespräch wird aufgezeichnet.",
    "es": "La llamada también se graba.",
    "fr": "L'appel est également enregistré.",
    "it": "La chiamata viene anche registrata.",
    "no": "Samtalen blir også tatt opp.",
    "sv": "Samtalet spelas också in.",
}
# A greeting that already tells the caller about the recording is left as it is.
_ALREADY_SAID = re.compile(r"optag|record|aufgezeichnet|aufgenommen|grab|enregistr|registrat|tatt opp|tas opp|spelas in",
                           re.IGNORECASE)


def enabled(number: PhoneNumber | None) -> bool:
    return number is not None and bool(number.record_calls) and recordings.storage_on()


def artifact_plan(number: PhoneNumber | None) -> dict:
    return {"recordingEnabled": enabled(number)}


def with_disclosure(greeting: str, lang: str) -> str:
    """The greeting with the recording notice, placed before the closing question («… Hvad kan jeg hjælpe med?»)."""
    text = greeting.strip()
    if not text or _ALREADY_SAID.search(text):
        return text
    notice = DISCLOSURE.get(lang, DISCLOSURE["da"])
    if text.endswith("?"):
        cut = max(text.rfind(". ", 0, len(text) - 1), text.rfind("! ", 0, len(text) - 1))
        if cut >= 0:
            return f"{text[:cut + 1]} {notice} {text[cut + 2:]}"
        return f"{notice} {text}"
    return f"{text}{'' if text[-1] in '.!' else '.'} {notice}"


def on_report(db: OrmSession, call: Call, number: PhoneNumber) -> None:
    """After the end-of-call report of a customer's call: queue the download, or note that there is no audio. A call
    that the sales or campaign path already gave a recording row keeps it."""
    from app.core.outbox import enqueue

    if db.scalar(select(CallRecording.id).where(CallRecording.call_id == call.id)):
        return
    if not enabled(number):
        call.recording_status = "NOT_RECORDED"
        call.recording_url = None  # nothing from a call the customer did not choose to record is kept
        return
    db.add(CallRecording(call_id=call.id, status="PENDING", provider_ref=call.provider_call_id))
    call.recording_status = "PENDING"
    db.flush()
    enqueue(db, event_type=EVENT, dedupe_key=f"call_recording:{call.id}", payload={"call_id": str(call.id)})


def handle_fetch(db: OrmSession, ev) -> None:
    call = db.get(Call, uuid.UUID(ev.payload["call_id"]))
    if call is not None:
        recordings.fetch(db, call.id, prefix=f"calls/{call.workspace_id}")


def recording_of(db: OrmSession, call_id: uuid.UUID) -> CallRecording | None:
    return db.scalar(select(CallRecording).where(CallRecording.call_id == call_id))


def out(db: OrmSession, call: Call) -> dict:
    """What the customer sees: the status, and when the audio goes. Never storage keys or provider links."""
    rec = recording_of(db, call.id)
    if rec is None:
        return {"status": call.recording_status or "NOT_RECORDED", "duration_seconds": None, "delete_after": None,
                "deleted_at": None}
    keep = None
    number = db.get(PhoneNumber, call.phone_number_id) if call.phone_number_id else None
    if rec.status == "AVAILABLE" and rec.available_at is not None and number is not None:
        keep = (rec.available_at + timedelta(days=number.recording_retention_days)).isoformat()
    return {"status": rec.status, "duration_seconds": rec.duration_seconds or call.duration_seconds,
            "delete_after": keep, "deleted_at": rec.deleted_at.isoformat() if rec.deleted_at else None}


NO_AUDIO = {"PENDING": "Optagelsen bliver hentet – prøv igen om et øjeblik",
            "FAILED": "Optagelsen kunne ikke hentes", "DELETED": "Optagelsen er slettet"}


def play_url(db: OrmSession, call: Call, user_id: uuid.UUID, *, download: bool) -> dict:
    rec = recording_of(db, call.id)
    if rec is None or rec.status != "AVAILABLE":
        status = rec.status if rec else (call.recording_status or "NOT_RECORDED")
        raise recordings.RecordingUnavailable(NO_AUDIO.get(status, "Opkaldet blev ikke optaget"),
                                              extra={"status": status})
    return recordings.play_url(db, call, user_id, export=download)


def delete(db: OrmSession, call: Call, reason: str) -> None:
    rec = recording_of(db, call.id)
    if rec is None or rec.status == "DELETED":
        raise ApiError("Der er ingen optagelse at slette", code="recording_unavailable", status_code=409)
    recordings.delete(db, rec, reason)
    call.recording_url = None
    recordings.delete_at_vapi(call.provider_call_id)


def run_retention(db: OrmSession, now: datetime | None = None) -> int:
    """Delete customers' recordings older than their number's retention. Dialogbot's own sales calls are left to
    sales.privacy (they have their own rules)."""
    now = now or datetime.now(UTC)
    n = 0
    rows = db.execute(select(CallRecording, Call, PhoneNumber).join(Call, Call.id == CallRecording.call_id)
                      .join(PhoneNumber, PhoneNumber.id == Call.phone_number_id)
                      .where(CallRecording.status == "AVAILABLE", CallRecording.storage_key.like("calls/%")))
    for rec, call, number in rows:
        if rec.available_at and rec.available_at < now - timedelta(days=number.recording_retention_days):
            recordings.delete(db, rec, "retention")
            call.recording_url = None
            recordings.delete_at_vapi(call.provider_call_id)
            n += 1
    db.commit()
    if n:
        log.info("calls.recording_retention", deleted=n)
    return n
