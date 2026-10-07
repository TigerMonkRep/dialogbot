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

import hashlib
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
from app.models import Booking, Call, Conversation, ConversationMessage, Lead, PhoneNumber, WebhookEvent, Workspace
from app.modules.ai.service import CHANNEL_INSTRUCTIONS, build_system_prompt
from app.modules.reception import service as reception

PROVIDER = "vapi"
E164 = re.compile(r"^\+[1-9]\d{6,14}$")
DEFAULT_GREETING = ("Hej, du har ringet til {name}. Du taler med en digital assistent, og samtalen bliver skrevet ned. "
                    "Hvad kan jeg hjælpe med?")


# Danish speech-to-text by default (Deepgram Nova-3 supports "da"); VAPI_TRANSCRIBER_JSON overrides it.
# ElevenLabs Scribe hears Danish names and places far better than Deepgram on phone audio; Deepgram Nova-3 (with the
# business's key terms) takes over if Scribe fails during a call.
DEFAULT_TRANSCRIBER = {"provider": "11labs", "model": "scribe_v2_realtime", "language": "da"}
FALLBACK_TRANSCRIBER = {"provider": "deepgram", "model": "nova-3", "language": "da"}
# Turn-taking that feels like a person: short Danish backchannels ("ja", "mm") never cut the assistant off, and it
# waits a moment after an interruption before speaking again.
STOP_SPEAKING_PLAN = {"numWords": 2, "backoffSeconds": 1.0,
                      "acknowledgementPhrases": ["ja", "jo", "jah", "mm", "mhm", "okay", "ok", "nå", "nåh", "præcis",
                                                 "netop", "fint", "godt", "javel", "jaja", "yes", "klart"]}
START_SPEAKING_PLAN = {"waitSeconds": 0.5}
# The assistant hangs up itself: Vapi's endCall tool, plus the closing line the phone prompt ends every call with.
END_CALL_TOOL = {"type": "endCall"}
END_CALL_PHRASES = ["hav en rigtig god dag", "hav en god dag"]
# ElevenLabs models a number may use. Only Flash v2.5 accepts an explicit language; the others detect it
# from the (Danish) text and reject a language code.
VOICE_MODELS = ("eleven_multilingual_v2", "eleven_flash_v2_5", "eleven_turbo_v2_5", "eleven_v4_turbo")
# Models that take an explicit language code (multilingual_v2 detects the language itself).
LANGUAGE_CODE_MODELS = ("eleven_flash_v2_5", "eleven_turbo_v2_5", "eleven_v4_turbo")
VOICE_ID = re.compile(r"^[A-Za-z0-9]{10,64}$")


class VoiceNotConfigured(ApiError):
    status_code = 503
    code = "voice_not_configured"


def verify(authorization: str | None, x_vapi_secret: str | None) -> None:
    secret = (get_settings().vapi_server_secret or "").strip()
    if not secret:
        raise VoiceNotConfigured("Stemmewebhook er ikke konfigureret (VAPI_SERVER_SECRET mangler)")
    # Vapi sends the credential as "Bearer <token>", as a raw token in Authorization, or in X-Vapi-Secret
    # (sometimes alongside an empty one) – accept any non-empty candidate that matches.
    candidates: list[str] = []
    if authorization and authorization.strip():
        a = authorization.strip()
        candidates.append(a[7:].strip() if a.lower().startswith("bearer ") else a)
    if x_vapi_secret and x_vapi_secret.strip():
        candidates.append(x_vapi_secret.strip())
    ok = False
    for c in candidates:
        ok = hmac.compare_digest(c.encode(), secret.encode()) or ok
    if not ok:
        # Diagnose without revealing anything usable: which header arrived, lengths and 6-hex fingerprints.
        from app.core.logging import log

        def fp(v: str | None) -> str | None:
            return hashlib.sha256(v.encode()).hexdigest()[:6] if v else None

        a = (authorization or "").strip()
        log.warning("vapi.auth_failed", authorization_header=authorization is not None,
                    authorization_scheme=("bearer" if a.lower().startswith("bearer ") else "raw") if a else None,
                    x_vapi_secret_header=x_vapi_secret is not None,
                    presented_lens=[len(c) for c in candidates], presented_fps=[fp(c) for c in candidates],
                    expected_len=len(secret), expected_fp=fp(secret))
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
    """Map the dialled number to exactly one workspace – strictly (see platform.route): an unknown provider id,
    an id/number mismatch, a foreign Vapi org or an inactive number is never routed to anyone."""
    from app.modules.telephony.platform import route

    return route(db, message)


# Vapi validates assistant.model against its own enum per provider; an unknown id makes Vapi reject the whole
# assistant-request answer and the caller hears a server error. Keep this in step with Vapi's AnthropicModel enum.
VAPI_ANTHROPIC_MODELS = frozenset({
    "claude-sonnet-5", "claude-sonnet-4-6", "claude-opus-4-6", "claude-sonnet-4-5-20250929", "claude-opus-4-5-20251101",
    "claude-haiku-4-5-20251001", "claude-sonnet-4-20250514", "claude-opus-4-20250514"})
# Phone answers must start fast; a pause before every reply is what makes a call feel robotic. Haiku 4.5 answers far
# quicker than Sonnet; set VAPI_MODEL (e.g. claude-sonnet-4-6) to trade speed for depth.
VAPI_DEFAULT_ANTHROPIC_MODEL = "claude-haiku-4-5-20251001"


# Vapi writes call.analysis.summary with an English default prompt; our inbox, leads and daily reports are Danish.
ANALYSIS_PLAN = {"summaryPlan": {"messages": [
    {"role": "system", "content": "Du er en erfaren referent. Du får udskriften af et telefonopkald til en dansk virksomhed. "
                                  "Opsummér opkaldet på dansk i 2-3 sætninger: hvem ringede, hvad de ville, og hvad der "
                                  "blev aftalt. Returnér kun resuméet."},
    {"role": "user", "content": "Udskrift:\n\n{{transcript}}\n\nÅrsag til at opkaldet sluttede: {{endedReason}}"}]}}


def phone_model(s) -> str:
    """The model id sent to Vapi: VAPI_MODEL, else the fast phone default – replaced by that default when Vapi would
    refuse it (only checked for the anthropic provider, whose list we know)."""
    m = s.vapi_model or (VAPI_DEFAULT_ANTHROPIC_MODEL if s.vapi_model_provider == "anthropic" else s.ai_model_id)
    if s.vapi_model_provider == "anthropic" and m not in VAPI_ANTHROPIC_MODELS:
        return VAPI_DEFAULT_ANTHROPIC_MODEL
    return m


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
        raise NotImplementedYet("Stemmeprøven er ikke sat op endnu", code="voice_preview_not_configured")
    try:
        r = httpx.post(ELEVENLABS_TTS.format(voice_id=voice_id), params={"output_format": "mp3_44100_128"},
                       headers={"xi-api-key": key}, json={"text": text, "model_id": voice_model}, timeout=30.0)
    except httpx.HTTPError as e:
        raise ApiError("Stemmetjenesten svarede ikke", code="voice_preview_failed", status_code=502) from e
    if r.status_code >= 400:
        raise ApiError(f"Stemmeprøven kunne ikke laves ({r.status_code}). Tjek stemme-id og model.",
                       code="voice_preview_failed", status_code=502)
    return r.content


MAX_KEYTERMS = 50  # Deepgram: 500 tokens per request; recommends focusing on the 20-50 most important terms
KEYTERM_MODELS = ("nova-3", "flux")


def keyterms(db: OrmSession, ws: Workspace) -> list[str]:
    """Words the caller is likely to say that a generic Danish model mishears: the business's own name, its
    services and booking types, and place names from its profile and approved coverage area. Only approved knowledge
    and the profile are used, so nothing unapproved leaks into the call."""
    from app.models import BookingType, BusinessProfile
    from app.modules.knowledge.service import active_knowledge

    terms: list[str] = [ws.name]
    p = db.get(BusinessProfile, ws.id)
    if p is not None:
        terms += [p.legal_name, p.city or "", (p.address_line or "").rsplit(" ", 1)[0]]
    for item in active_knowledge(db, ws.id):
        if item["kind"] in ("service", "offer"):
            terms.append(item["title"])
        elif item["kind"] == "coverage_area":
            c = item["content"] or {}
            terms.append(item["title"])
            for key in ("areas", "cities", "postal_areas", "municipalities"):
                terms += [str(x) for x in c.get(key) or [] if isinstance(x, str)]
    terms += list(db.scalars(select(BookingType.name).where(BookingType.workspace_id == ws.id, BookingType.active)))
    out: list[str] = []
    seen: set[str] = set()
    for t in terms:
        t = re.sub(r"\s+", " ", str(t or "")).strip(" .,:;-")
        t = re.sub(r"\b(ApS|A/S|I/S|IVS|P/S)\b", "", t).strip()
        if 2 < len(t) <= 50 and t.lower() not in seen:
            seen.add(t.lower())
            out.append(t)
    return out[:MAX_KEYTERMS]


def transcriber_for(db: OrmSession, ws: Workspace | None) -> dict:
    """The transcriber config (VAPI_TRANSCRIBER_JSON, or ElevenLabs Scribe Danish with Deepgram Nova-3 as fallback),
    with the business's key terms added to any Deepgram model that supports keyterm prompting."""
    configured = _json_setting(get_settings().vapi_transcriber_json)
    t = configured or dict(DEFAULT_TRANSCRIBER)
    if configured is None:
        t["fallbackPlan"] = {"transcribers": [dict(FALLBACK_TRANSCRIBER)]}
    for d in [t, *t.get("fallbackPlan", {}).get("transcribers", [])]:
        if (ws is not None and d.get("provider") == "deepgram" and str(d.get("model", "")).startswith(KEYTERM_MODELS)
                and "keyterm" not in d):
            terms = keyterms(db, ws)
            if terms:
                d["keyterm"] = terms
    return t


def booking_tools(db: OrmSession, ws: Workspace) -> list[dict]:
    """Function tools for the call: every action of a connected connector (Dialogbot's calendar when online booking
    is on, a connected Google/Microsoft calendar, SMS confirmations …), built by app/modules/integrations/actions."""
    from app.modules.integrations import actions

    return actions.to_vapi(actions.tools_for(db, ws, "phone"))


def tool_calls(db: OrmSession, message: dict) -> dict:
    """Answer Vapi `tool-calls`: run each call through the action runner (validation, connected connectors only,
    one action_runs row each). Always returns a result per call (errors as plain text the assistant can relay)."""
    import json as _json

    from app.modules.integrations import actions
    from app.modules.integrations.connectors.base import RunContext
    from app.modules.reports.service import tz_of

    number = find_number(db, message)
    calls = message.get("toolCallList") or [x.get("toolCall") for x in message.get("toolWithToolCallList") or []] or []
    results = []
    for tc in calls:
        tc = tc or {}
        fn = tc.get("function") or {}
        name, args = fn.get("name"), fn.get("arguments") or {}
        if isinstance(args, str):
            try:
                args = _json.loads(args)
            except ValueError:
                args = {}
        result = "Handlingen er ikke tilgængelig på dette nummer. Tilbyd i stedet, at en medarbejder ringer tilbage."
        if number is not None and number.active and name:
            ws = db.get(Workspace, number.workspace_id)
            caller = _dig(message, "call", "customer", "number")
            ctx = RunContext(workspace_id=ws.id, channel="phone", caller_phone=normalize_e164(str(caller)) if caller else None,
                             provider_call_id=str(_dig(message, "call", "id") or "") or None, tz=tz_of(db, ws.id))
            result, _run = actions.execute(db, ws, str(name), args if isinstance(args, dict) else {}, ctx)
            db.commit()
        results.append({"toolCallId": tc.get("id"), "result": result})
    return {"results": results}


def voice_config(number: PhoneNumber) -> dict | None:
    """The number's own ElevenLabs voice, or None (then VAPI_VOICE_JSON or the provider default applies)."""
    if not number.voice_id:
        return None
    voice: dict[str, Any] = {"provider": "11labs", "voiceId": number.voice_id, "model": number.voice_model}
    if number.voice_model in LANGUAGE_CODE_MODELS:
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
        "firstMessage": (number.greeting.strip() or reception.spoken_greeting(db.get(reception.ReceptionScript, ws.id), ws)
                         or DEFAULT_GREETING.format(name=ws.name)),
        "model": {"provider": s.vapi_model_provider, "model": phone_model(s),
                  "messages": [{"role": "system", "content": f"{system}\n\n{phone_rules}"}]},
        "transcriber": transcriber_for(db, ws),
        "analysisPlan": ANALYSIS_PLAN,
        "stopSpeakingPlan": STOP_SPEAKING_PLAN, "startSpeakingPlan": START_SPEAKING_PLAN,
        "endCallPhrases": END_CALL_PHRASES,
        "metadata": {"workspace_id": str(ws.id), "phone_number_id": str(number.id)},
    }
    from app.modules.integrations import actions as _actions

    action_tools = _actions.tools_for(db, ws, "phone")
    assistant["model"]["tools"] = [END_CALL_TOOL]
    if action_tools:
        assistant["model"]["tools"] = _actions.to_vapi(action_tools) + [END_CALL_TOOL]
        assistant["model"]["messages"][0]["content"] += "\n\n" + _actions.prompt_section(action_tools)
    from app.modules.voices import service as voices
    from app.modules.voices import standard

    provider_voice = standard.provider_voice(db, ws.id, number)

    dialogbot_voice, session = voices.vapi_voice(db, ws.id, channel="inbound_phone", provider_voice=provider_voice,
                                                 number=number)
    if dialogbot_voice is not None:
        assistant["voice"] = dialogbot_voice
        assistant["metadata"]["voice_session_id"] = str(session.id)
    elif provider_voice is not None:
        assistant["voice"] = provider_voice
    if session is not None:
        db.commit()
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
    lines: list[str] = []
    for m in (_dig(message, "artifact", "messages") or message.get("messages") or []):
        role = ROLE.get(str(m.get("role", "")).lower()) if isinstance(m, dict) else None
        text = (m.get("message") or m.get("content") or "") if role else ""
        if not role or not str(text).strip():
            continue  # system prompts, tool calls and empty turns are not part of the transcript
        visitor_lines += role == "visitor"
        lines.append(("Kontakt" if role == "visitor" else "Assistent") + ": " + str(text).strip())
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
    from app.modules.telephony import platform

    platform.record_call_cost(db, call, message)
    platform.evaluate_test(db, call, message)
    from app.models import ActionRun
    from app.modules.integrations import events

    for run in db.scalars(select(ActionRun).where(ActionRun.provider_call_id == call_id, ActionRun.conversation_id.is_(None))):
        run.conversation_id = conv.id  # actions taken during the call now show in its conversation
    events.emit(db, ws_id, "conversation.ended",
                {"conversation_id": str(conv.id), "channel": "phone", "from": caller, "to": number.e164,
                 "duration_seconds": int(duration) if duration is not None else None, "summary": summary,
                 "ended_reason": call.ended_reason}, key=call_id)
    from app.modules.campaigns import service as campaigns

    if campaigns.on_report(db, message, call_id=call_id, conv=conv, duration=duration, visitor_lines=visitor_lines,
                           transcript="\n".join(lines), summary=summary):
        return "applied"  # an outbound campaign call: its contact gets the outcome, not a generic callback lead
    from app.modules.sales import service as sales

    if sales.on_report(db, message, call_id=call_id, conv=conv, visitor_lines=visitor_lines,
                       transcript="\n".join(lines), summary=summary):
        return "applied"  # a demo call from the sales workspace: outcome on the demo call, lead only when relevant
    booked = db.scalar(select(Booking).where(Booking.workspace_id == ws_id, Booking.source == "phone",
                                             Booking.provider_call_id == call_id)) if call_id else None
    if booked is not None:  # the caller booked during the call: that booking's lead is the lead
        booked.conversation_id = conv.id
        lead = db.get(Lead, booked.lead_id) if booked.lead_id else None
        if lead is not None and lead.conversation_id is None:
            lead.conversation_id = conv.id
        return "applied"
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


def not_active_assistant(db: OrmSession, number: PhoneNumber) -> dict:
    """A call reached the destination before the customer activated (or while paused): say so briefly and end.
    No knowledge is used and nothing is promised."""
    from app.modules.voices import standard

    ws = db.get(Workspace, number.workspace_id)
    s = get_settings()
    text = (f"Tak for dit opkald til {ws.name}. Telefonsvareren er ikke aktiveret endnu. "
            "Prøv venligst igen senere. Farvel.")
    return {"assistant": {
        "firstMessage": text, "endCallMessage": "Farvel.", "maxDurationSeconds": 20,
        "model": {"provider": s.vapi_model_provider, "model": phone_model(s),
                  "messages": [{"role": "system", "content": "Sig kun farvel. Svar ikke på spørgsmål."}]},
        "transcriber": transcriber_for(db, None), "analysisPlan": ANALYSIS_PLAN,
        "voice": standard.provider_voice(db, ws.id, number),
        "metadata": {"workspace_id": str(ws.id), "phone_number_id": str(number.id), "not_active": True}}}
