"""Vapi voice webhook (server URL).

Vapi calls our server URL with `{"message": {"type": ...}}`:
- `assistant-request` (needs a JSON answer): we map the dialled number to a workspace and return a
  transient assistant whose system prompt is built ONLY from approved knowledge.
- `end-of-call-report`: we store the call, its transcript as a `phone` conversation, and — when the
  caller left a number and said something — a lead plus a "call back" task.
- anything else (status-update, …) is acknowledged and ignored.

Authentication: `Authorization: Bearer <VAPI_SERVER_SECRET>` (Vapi's Bearer credential) or the
legacy `X-Vapi-Secret` header, compared in constant time. Reports are idempotent per call id.
"""
from __future__ import annotations

import hmac
import json
import re
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as OrmSession

from app.config import get_settings
from app.core.errors import ApiError, Unauthenticated
from app.models import Call, Conversation, ConversationMessage, PhoneNumber, WebhookEvent, Workspace
from app.modules.ai.service import CHANNEL_INSTRUCTIONS, build_system_prompt

PROVIDER = "vapi"
E164 = re.compile(r"^\+[1-9]\d{6,14}$")
DEFAULT_GREETING = ("Hej, du har ringet til {name}. Du taler med en digital assistent, og samtalen bliver skrevet ned. "
                    "Hvad kan jeg hjælpe med?")


# Danish speech-to-text by default (Deepgram Nova-3 supports "da"); VAPI_TRANSCRIBER_JSON overrides it.
DEFAULT_TRANSCRIBER = {"provider": "deepgram", "model": "nova-3", "language": "da"}
# ElevenLabs models a number may use. Only Flash v2.5 accepts an explicit language; the others detect it
# from the (Danish) text and reject a language code.
VOICE_MODELS = ("eleven_multilingual_v2", "eleven_flash_v2_5", "eleven_turbo_v2_5")
VOICE_ID = re.compile(r"^[A-Za-z0-9]{10,64}$")


class VoiceNotConfigured(ApiError):
    status_code = 503
    code = "voice_not_configured"


def verify(authorization: str | None, x_vapi_secret: str | None) -> None:
    secret = get_settings().vapi_server_secret
    if not secret:
        raise VoiceNotConfigured("Stemmewebhook er ikke konfigureret (VAPI_SERVER_SECRET mangler)")
    presented = None
    if authorization and authorization.lower().startswith("bearer "):
        presented = authorization[7:].strip()
    elif x_vapi_secret:
        presented = x_vapi_secret.strip()
    if not presented or not hmac.compare_digest(presented.encode(), secret.encode()):
        raise Unauthenticated("Ugyldig webhook-legitimation", code="invalid_signature")


def normalize_e164(raw: str) -> str:
    n = re.sub(r"[\s()-]", "", raw or "")
    if n.startswith("00"):
        n = "+" + n[2:]
    return n


def _dig(d: Any, *path: str) -> Any:
    for p in path:
        if not isinstance(d, dict):
            return None
        d = d.get(p)
    return d


def find_number(db: OrmSession, message: dict) -> PhoneNumber | None:
    """Map the dialled number to a workspace: by the provider's number id, else by E.164."""
    pid = _dig(message, "call", "phoneNumberId") or _dig(message, "phoneNumber", "id")
    if pid:
        n = db.scalar(select(PhoneNumber).where(PhoneNumber.provider_number_id == str(pid)))
        if n is not None:
            return n
    num = _dig(message, "phoneNumber", "number") or _dig(message, "call", "phoneNumber", "number")
    if num:
        return db.scalar(select(PhoneNumber).where(PhoneNumber.e164 == normalize_e164(str(num))))
    return None


def _json_setting(raw: str | None) -> dict | None:
    if not raw:
        return None
    try:
        v = json.loads(raw)
        return v if isinstance(v, dict) else None
    except ValueError:
        return None


PREVIEW_TEXT_MAX = 300
ELEVENLABS_TTS = "https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"


def voice_preview(voice_id: str, voice_model: str, text: str) -> bytes:
    """Render a short sample with ElevenLabs (mp3). The key never leaves the server."""
    import httpx

    from app.core.errors import NotImplementedYet

    key = get_settings().elevenlabs_api_key
    if not key:
        raise NotImplementedYet("Stemmeprøve kræver ELEVENLABS_API_KEY på serveren", code="voice_preview_not_configured")
    try:
        r = httpx.post(ELEVENLABS_TTS.format(voice_id=voice_id), params={"output_format": "mp3_44100_128"},
                       headers={"xi-api-key": key}, json={"text": text, "model_id": voice_model}, timeout=30.0)
    except httpx.HTTPError as e:
        raise ApiError("ElevenLabs svarede ikke", code="voice_preview_failed", status_code=502) from e
    if r.status_code >= 400:
        raise ApiError(f"ElevenLabs afviste stemmeprøven ({r.status_code}). Tjek stemme-id og model.",
                       code="voice_preview_failed", status_code=502)
    return r.content


def voice_config(number: PhoneNumber) -> dict | None:
    """The number's own ElevenLabs voice, or None (then VAPI_VOICE_JSON or the provider default applies)."""
    if not number.voice_id:
        return None
    voice: dict[str, Any] = {"provider": "11labs", "voiceId": number.voice_id, "model": number.voice_model}
    if number.voice_model == "eleven_flash_v2_5":
        voice["language"] = "da"
    return voice


def assistant_config(db: OrmSession, number: PhoneNumber) -> dict:
    ws = db.get(Workspace, number.workspace_id)
    system, _revision = build_system_prompt(db, ws)  # 409 without approved knowledge
    _suffix, phone_rules = CHANNEL_INSTRUCTIONS["phone"]
    style = (number.speaking_style or "").strip()
    if style:
        phone_rules += ("\n\nVirksomhedens ønsker til talestil (følg dem, men de ændrer aldrig fakta eller reglerne "
                        f"ovenfor):\n{style}")
    s = get_settings()
    assistant: dict[str, Any] = {
        "firstMessage": (number.greeting.strip() or DEFAULT_GREETING.format(name=ws.name)),
        "model": {"provider": s.vapi_model_provider, "model": s.vapi_model or s.ai_model_id,
                  "messages": [{"role": "system", "content": f"{system}\n\n{phone_rules}"}]},
        "transcriber": _json_setting(s.vapi_transcriber_json) or dict(DEFAULT_TRANSCRIBER),
        "metadata": {"workspace_id": str(ws.id), "phone_number_id": str(number.id)},
    }
    if voice := voice_config(number):
        assistant["voice"] = voice
    elif (voice := _json_setting(s.vapi_voice_json)) is not None:
        assistant["voice"] = voice
    return {"assistant": assistant}


def _parse_ts(v: Any) -> datetime | None:
    if not v:
        return None
    try:
        return datetime.fromisoformat(str(v).replace("Z", "+00:00"))
    except ValueError:
        return None


ROLE = {"user": "visitor", "customer": "visitor", "assistant": "assistant", "bot": "assistant"}


def end_of_call(db: OrmSession, message: dict) -> str:
    """Store one call. Returns outcome: applied | unmatched | duplicate."""
    call_id = str(_dig(message, "call", "id") or "")
    if not call_id:
        return "ignored"
    if db.scalar(select(Call.id).where(Call.provider_call_id == call_id)):
        return "duplicate"
    number = find_number(db, message)
    if number is None:
        return "unmatched"
    ws_id = number.workspace_id
    started = _parse_ts(message.get("startedAt") or _dig(message, "call", "startedAt"))
    ended = _parse_ts(message.get("endedAt") or _dig(message, "call", "endedAt"))
    duration = message.get("durationSeconds")
    if duration is None and started and ended:
        duration = (ended - started).total_seconds()
    caller = _dig(message, "call", "customer", "number") or _dig(message, "customer", "number")
    caller = normalize_e164(str(caller)) if caller else None
    summary = str(_dig(message, "analysis", "summary") or message.get("summary") or "")[:4000]
    cost = message.get("cost")
    now = datetime.now(UTC)

    conv = Conversation(workspace_id=ws_id, channel="phone", visitor_token_digest="-" * 64, origin=caller,
                        created_at=started or now, last_message_at=ended or now)
    db.add(conv)
    db.flush()
    visitor_lines = 0
    for m in (_dig(message, "artifact", "messages") or message.get("messages") or []):
        role = ROLE.get(str(m.get("role", "")).lower()) if isinstance(m, dict) else None
        text = (m.get("message") or m.get("content") or "") if role else ""
        if not role or not str(text).strip():
            continue  # system prompts, tool calls and empty turns are not part of the transcript
        visitor_lines += role == "visitor"
        db.add(ConversationMessage(conversation_id=conv.id, workspace_id=ws_id, role=role, text=str(text)[:4000]))
    conv.visitor_message_count = visitor_lines
    call = Call(workspace_id=ws_id, phone_number_id=number.id, conversation_id=conv.id, provider=PROVIDER,
                provider_call_id=call_id, from_number=caller, to_number=number.e164, started_at=started, ended_at=ended,
                duration_seconds=int(duration) if duration is not None else None,
                ended_reason=str(message.get("endedReason") or "")[:100] or None, summary=summary,
                cost_usd_micros=round(float(cost) * 1_000_000) if isinstance(cost, int | float) else None)
    db.add(call)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        return "duplicate"
    if caller and visitor_lines:
        from app.modules.leads.service import create_lead, create_task

        lead = create_lead(db, ws_id, source="phone", created_by=None, conversation=conv, contact_phone=caller,
                           need_summary=summary or "Opkald – se samtalen")
        create_task(db, ws_id, title=f"Ring tilbage til {caller}", created_by=None, lead=lead,
                    due_at=now + timedelta(hours=4))
    return "applied"


def record_event(db: OrmSession, event_id: str, event_type: str, payload: dict, outcome: str) -> None:
    db.add(WebhookEvent(provider=PROVIDER, event_id=event_id[:200], event_type=event_type[:64] or "unknown",
                        payload=payload, outcome=outcome if outcome in ("applied", "ignored", "unmatched") else "ignored"))
