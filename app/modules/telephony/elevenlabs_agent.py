"""ElevenLabs Agents as the call engine (trial alongside Vapi).

ElevenLabs runs speech-to-text, the language model and the voice in one place. A Twilio number imported into
ElevenLabs calls two of our webhooks:
- conversation initiation: ElevenLabs posts {caller_id, called_number, call_sid, agent_id, conversation_id};
  we answer with the workspace's prompt and greeting as overrides (the same content Vapi gets); the voice is
  the agent's own.
- post-call transcription: the transcript and summary, HMAC-signed (`ElevenLabs-Signature: t=…,v0=…`); we store
  it exactly like a Vapi end-of-call report (conversation, call, lead and call-back task).
"""
from __future__ import annotations

import hashlib
import hmac
import time
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session as OrmSession

from app.config import get_settings
from app.core.errors import Unauthenticated
from app.models import PhoneNumber, Workspace
from app.modules.telephony import vapi

SIGNATURE_TOLERANCE_SECONDS = 30 * 60


def verify_init(secret_header: str | None) -> None:
    secret = (get_settings().elevenlabs_agent_secret or "").strip()
    if not secret:
        raise vapi.VoiceNotConfigured("ElevenLabs-agenten er ikke sat op (ELEVENLABS_AGENT_SECRET mangler)")
    if not secret_header or not hmac.compare_digest(secret_header.strip().encode(), secret.encode()):
        raise Unauthenticated("Ugyldig webhook-legitimation", code="invalid_signature")


def verify_post_call(raw: bytes, signature: str | None) -> None:
    """t=<unix>,v0=<hex hmac-sha256 of "t.body"> – the scheme of the official ElevenLabs SDK."""
    secret = (get_settings().elevenlabs_webhook_secret or "").strip()
    if not secret:
        raise vapi.VoiceNotConfigured("ElevenLabs-webhooken er ikke sat op (ELEVENLABS_WEBHOOK_SECRET mangler)")
    parts = dict(p.split("=", 1) for p in (signature or "").split(",") if "=" in p)
    ts, sig = parts.get("t", ""), parts.get("v0", "")
    if not ts.isdigit() or not sig or abs(time.time() - int(ts)) > SIGNATURE_TOLERANCE_SECONDS:
        raise Unauthenticated("Ugyldig webhook-signatur", code="invalid_signature")
    expected = hmac.new(secret.encode(), f"{ts}.".encode() + raw, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig, expected):
        raise Unauthenticated("Ugyldig webhook-signatur", code="invalid_signature")


def _number(db: OrmSession, e164: str | None) -> PhoneNumber | None:
    if not e164:
        return None
    row = db.scalar(select(PhoneNumber).where(PhoneNumber.e164 == vapi.normalize_e164(str(e164))))
    return row if row is not None and row.status == "active" and row.active else None


def initiation(db: OrmSession, body: dict) -> dict:
    """Overrides for one inbound call: prompt, first message and Danish."""
    from app.modules.telephony import platform

    number = _number(db, body.get("called_number"))
    call_sid = str(body.get("call_sid") or body.get("conversation_id") or "")
    out: dict[str, Any] = {"type": "conversation_initiation_client_data", "dynamic_variables": {}}
    if number is None:
        out["conversation_config_override"] = {"agent": {
            "first_message": "Dette nummer er ikke i brug. Farvel.", "language": "da",
            "prompt": {"prompt": "Sig kun farvel."}}}
        return out
    message = {"call": {"id": call_sid, "customer": {"number": body.get("caller_id")}}}
    mode = platform.call_mode(db, number, message)
    if mode in ("loop", "not_active"):
        cfg = vapi.not_active_assistant(db, number)["assistant"]
        system = cfg["model"]["messages"][0]["content"]
    else:
        cfg = vapi.assistant_config(db, number)["assistant"]
        system = cfg["model"]["messages"][0]["content"]
        if mode == "test":
            cfg["firstMessage"] = "Dette er et prøveopkald. " + cfg.get("firstMessage", "")
            platform.mark_test_call(db, number, f"el_{body.get('conversation_id') or call_sid}")
            db.commit()
    caller = vapi.normalize_e164(str(body.get("caller_id"))) if body.get("caller_id") else None
    if caller and mode not in ("loop", "not_active"):
        system += (f"\n\nKunden ringer fra {caller}. Du kender altså allerede deres nummer: spørg ikke efter det, "
                   "men bekræft gerne, at en medarbejder kan ringe tilbage på det nummer, de ringer fra. Læs aldrig "
                   "nummeret op, medmindre kunden beder om det.")
    agent: dict[str, Any] = {"first_message": cfg.get("firstMessage", ""), "language": "da",
                             "prompt": {"prompt": system}}
    # The voice is the agent's own (chosen in the ElevenLabs dashboard): a Voice Library voice is only usable there
    # once it is added to that account, so overriding it per call could make the call fail.
    out["conversation_config_override"] = {"agent": agent}
    out["dynamic_variables"] = {"workspace_id": str(number.workspace_id), "caller": str(body.get("caller_id") or "")}
    return out


def _iso(unix: Any) -> str | None:
    try:
        return datetime.fromtimestamp(float(unix), UTC).isoformat()
    except (TypeError, ValueError):
        return None


def post_call(db: OrmSession, payload: dict) -> str:
    """Store a finished ElevenLabs call through the same path as a Vapi end-of-call report."""
    if payload.get("type") != "post_call_transcription":
        return "ignored"
    data = payload.get("data") or {}
    meta = data.get("metadata") or {}
    phone = meta.get("phone_call") or {}
    number = _number(db, phone.get("agent_number"))
    if number is None:
        return "unmatched"
    started = meta.get("start_time_unix_secs")
    duration = meta.get("call_duration_secs")
    turns = [{"role": "user" if t.get("role") == "user" else "assistant", "message": t.get("message") or ""}
             for t in (data.get("transcript") or []) if isinstance(t, dict)]
    message = {
        "call": {"id": f"el_{data.get('conversation_id')}", "phoneNumberId": number.provider_number_id,
                 "customer": {"number": phone.get("external_number")}},
        "phoneNumber": {"number": number.e164},
        "startedAt": _iso(started),
        "endedAt": _iso(float(started) + float(duration)) if started is not None and duration is not None else None,
        "durationSeconds": duration,
        "endedReason": str(data.get("status") or ""),
        "analysis": {"summary": (data.get("analysis") or {}).get("transcript_summary") or ""},
        "artifact": {"messages": turns},
    }
    return vapi.end_of_call(db, message)


# Fields ElevenLabs fills from system dynamic variables on every tool call; everything else is the action's input.
TOOL_SYSTEM_FIELDS = ("called_number", "caller_id", "conversation_id")


def run_tool(db: OrmSession, name: str, body: dict) -> dict:
    """A server tool of the agent (`POST …/elevenlabs/tools/{name}`): the same action runner as Vapi tool-calls, so
    only actions of the number's workspace that are connected right now can run. Always answers with text the agent
    can say; a refused or failed action is a result, not an error."""
    from app.modules.integrations import actions
    from app.modules.integrations.connectors.base import RunContext
    from app.modules.reports.service import tz_of

    number = _number(db, body.get("called_number"))
    if number is None:
        return {"result": "Handlingen er ikke tilgængelig på dette nummer. Tilbyd i stedet, at en medarbejder ringer tilbage."}
    # The model leaves optional fields empty rather than out; drop them so the action's schema sees them as absent.
    args = {k: v for k, v in body.items() if k not in TOOL_SYSTEM_FIELDS and v not in (None, "")}
    ws = db.get(Workspace, number.workspace_id)
    caller = body.get("caller_id")
    conv = str(body.get("conversation_id") or "")
    ctx = RunContext(workspace_id=ws.id, channel="phone", caller_phone=vapi.normalize_e164(str(caller)) if caller else None,
                     provider_call_id=f"el_{conv}" if conv else None, tz=tz_of(db, ws.id))
    result, _run = actions.execute(db, ws, name, args, ctx)
    db.commit()
    return {"result": result}
