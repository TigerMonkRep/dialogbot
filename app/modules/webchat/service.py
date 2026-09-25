"""Web widget (W01): settings, availability, anonymous conversations and spend limits.

Security model
- The widget key is public. Embedding is limited by CSP `frame-ancestors` to the workspace's
  allowed origins; the chat itself runs in a frame on the API origin, so the visitor token never
  touches the customer's page.
- Visitor writes must come from that frame (Origin == API origin). Scripts can still call the API
  directly, so every conversation, message and reply is also bounded by DB-counted limits.
- Replies come from `ai.service.complete_logged`: approved knowledge only, one `ai_usage` row each.
"""
from __future__ import annotations

import secrets
import uuid
from datetime import UTC, datetime, timedelta
from urllib.parse import urlsplit

from sqlalchemy import func, select
from sqlalchemy.orm import Session as OrmSession

from app.config import get_settings
from app.core.errors import ApiError, NotFound, Unauthenticated, ValidationFailed
from app.core.security import token_digest
from app.models import AiUsage, Conversation, ConversationMessage, WebchatSettings, Workspace
from app.modules.ai.service import complete_logged, visible_reply
from app.modules.integrations.registry import capability
from app.modules.knowledge.service import active_knowledge

MAX_ORIGINS = 10
MAX_MESSAGE_CHARS = 1000
MAX_VISITOR_MESSAGES = 20  # per conversation
MAX_NEW_CONVERSATIONS_PER_HOUR = 60  # per widget
HISTORY_MESSAGES = 12  # context sent to the model
DEFAULT_GREETING = "Hej! Jeg er {name}s digitale assistent. Hvad kan jeg hjælpe med?"
UNAVAILABLE_TEXT = "Chatten er ikke tilgængelig lige nu. Kontakt virksomheden direkte."


class RateLimited(ApiError):
    status_code = 429
    code = "rate_limited"


class WebchatUnavailable(ApiError):
    status_code = 409
    code = "webchat_unavailable"


def _now() -> datetime:
    return datetime.now(UTC)


def new_widget_key() -> str:
    return "wk_" + secrets.token_urlsafe(18)


def get_or_create(db: OrmSession, workspace_id: uuid.UUID) -> WebchatSettings:
    s = db.get(WebchatSettings, workspace_id)
    if s is None:
        s = WebchatSettings(workspace_id=workspace_id, widget_key=new_widget_key(), allowed_origins=[], greeting="")
        db.add(s)
        db.flush()
    return s


def by_key(db: OrmSession, key: str) -> WebchatSettings:
    s = db.scalar(select(WebchatSettings).where(WebchatSettings.widget_key == key)) if key.startswith("wk_") else None
    if s is None:
        raise NotFound("Ukendt widget")
    return s


def normalize_origin(raw: str) -> str:
    """'https://www.Example.dk/' → 'https://www.example.dk'. Only https (http for localhost in dev/test)."""
    raw = raw.strip()
    parts = urlsplit(raw)
    host = (parts.hostname or "").lower()
    dev = get_settings().app_env in ("dev", "test")
    ok_scheme = parts.scheme == "https" or (parts.scheme == "http" and dev and host in ("localhost", "127.0.0.1"))
    if not ok_scheme or not host or parts.path not in ("", "/") or parts.query or parts.fragment or parts.username:
        raise ValidationFailed(f"Ugyldigt domæne: {raw!r}. Brug fx https://www.dinvirksomhed.dk",
                               field_errors=[{"field": "allowed_origins", "message": raw}])
    port = f":{parts.port}" if parts.port else ""
    return f"{parts.scheme}://{host}{port}"


def api_origin() -> str:
    u = urlsplit(get_settings().public_base_url)
    return f"{u.scheme}://{u.netloc}"


def greeting_text(db: OrmSession, s: WebchatSettings) -> str:
    if s.greeting.strip():
        return s.greeting.strip()
    ws = db.get(Workspace, s.workspace_id)
    return DEFAULT_GREETING.format(name=ws.name if ws else "virksomheden")


def unavailable_reasons(db: OrmSession, s: WebchatSettings, *, ignore_enabled: bool = False) -> list[str]:
    reasons = []
    if not ignore_enabled and not s.enabled:
        reasons.append("disabled")
    if not s.allowed_origins:
        reasons.append("no_allowed_origins")
    if capability("webchat").status == "not_implemented":
        reasons.append("ai_not_configured")
    if not active_knowledge(db, s.workspace_id):
        reasons.append("no_approved_knowledge")
    return reasons


def origin_allowed(s: WebchatSettings, origin: str | None) -> bool:
    return bool(origin) and origin in s.allowed_origins


def record_seen(db: OrmSession, s: WebchatSettings, origin: str) -> None:
    if s.last_seen_at is None or s.last_seen_origin != origin or _now() - s.last_seen_at > timedelta(minutes=5):
        s.last_seen_at, s.last_seen_origin = _now(), origin
        db.commit()


def _require_available(db: OrmSession, s: WebchatSettings) -> None:
    reasons = unavailable_reasons(db, s)
    if reasons:
        raise WebchatUnavailable(UNAVAILABLE_TEXT, extra={"reasons": reasons})


def start_conversation(db: OrmSession, s: WebchatSettings, host_origin: str | None) -> tuple[Conversation, str]:
    _require_available(db, s)
    since = _now() - timedelta(hours=1)
    recent = db.scalar(select(func.count()).select_from(Conversation).where(
        Conversation.workspace_id == s.workspace_id, Conversation.channel == "webchat", Conversation.created_at >= since))
    if recent >= MAX_NEW_CONVERSATIONS_PER_HOUR:
        raise RateLimited("Der er travlt i chatten lige nu. Prøv igen om lidt.")
    token = secrets.token_urlsafe(32)
    conv = Conversation(workspace_id=s.workspace_id, channel="webchat", visitor_token_digest=token_digest(token),
                        origin=host_origin if origin_allowed(s, host_origin) else None)
    db.add(conv)
    db.commit()
    return conv, token


def visitor_conversation(db: OrmSession, s: WebchatSettings, conversation_id: uuid.UUID, token: str | None) -> Conversation:
    conv = db.scalar(select(Conversation).where(Conversation.id == conversation_id,
                                                Conversation.workspace_id == s.workspace_id,
                                                Conversation.channel == "webchat"))
    if conv is None or not token or not secrets.compare_digest(conv.visitor_token_digest, token_digest(token)):
        # Same answer for "no such conversation" and "wrong token".
        raise Unauthenticated("Samtalen kunne ikke findes", code="invalid_visitor_token")
    return conv


def messages_of(db: OrmSession, conv: Conversation) -> list[ConversationMessage]:
    return list(db.scalars(select(ConversationMessage).where(ConversationMessage.conversation_id == conv.id)
                           .order_by(ConversationMessage.created_at, ConversationMessage.id)))


def daily_reply_limit_reached(db: OrmSession, workspace_id: uuid.UUID) -> bool:
    since = _now() - timedelta(days=1)
    n = db.scalar(select(func.count()).select_from(AiUsage).where(
        AiUsage.workspace_id == workspace_id, AiUsage.purpose == "webchat", AiUsage.created_at >= since))
    return n >= get_settings().webchat_daily_reply_limit


def post_visitor_message(db: OrmSession, s: WebchatSettings, conv: Conversation, text: str) -> dict:
    text = text.strip()
    if not text or len(text) > MAX_MESSAGE_CHARS:
        raise ValidationFailed(f"Beskeden skal være 1–{MAX_MESSAGE_CHARS} tegn",
                               field_errors=[{"field": "text"}])
    _require_available(db, s)
    if conv.status != "open":
        raise WebchatUnavailable("Samtalen er afsluttet. Start en ny.")
    if conv.visitor_message_count >= MAX_VISITOR_MESSAGES:
        raise RateLimited("Samtalen er blevet lang. Kontakt virksomheden direkte, så hjælper en medarbejder dig videre.",
                          code="conversation_limit")
    if daily_reply_limit_reached(db, s.workspace_id):
        raise RateLimited("Chatten har nået dagens grænse. Kontakt virksomheden direkte.", code="daily_limit")

    history = messages_of(db, conv)[-(HISTORY_MESSAGES - 1):]
    visitor_msg = ConversationMessage(conversation_id=conv.id, workspace_id=s.workspace_id, role="visitor", text=text)
    db.add(visitor_msg)
    conv.visitor_message_count += 1
    conv.last_message_at = _now()
    db.commit()

    turns = [{"role": "user" if m.role == "visitor" else "assistant", "content": m.text} for m in history]
    turns.append({"role": "user", "content": text})
    # The model requires alternating turns starting with the user; drop a leading assistant turn.
    while turns and turns[0]["role"] != "user":
        turns.pop(0)
    ws = db.get(Workspace, s.workspace_id)
    c, usage = complete_logged(db, ws, user_id=None, purpose="webchat", messages=_alternate(turns), channel="webchat")
    reply = ConversationMessage(conversation_id=conv.id, workspace_id=s.workspace_id, role="assistant",
                                text=visible_reply(c), ai_usage_id=usage.id)
    db.add(reply)
    conv.last_message_at = _now()
    db.commit()
    return {"reply": message_out(reply), "refused": usage.outcome == "refused",
            "remaining_messages": MAX_VISITOR_MESSAGES - conv.visitor_message_count}


def _alternate(turns: list[dict]) -> list[dict]:
    """Merge consecutive same-role turns (e.g. a visitor message whose reply failed)."""
    out: list[dict] = []
    for t in turns:
        if out and out[-1]["role"] == t["role"]:
            out[-1] = {"role": t["role"], "content": out[-1]["content"] + "\n\n" + t["content"]}
        else:
            out.append(dict(t))
    return out


def message_out(m: ConversationMessage) -> dict:
    return {"id": str(m.id), "role": m.role, "text": m.text, "created_at": m.created_at.isoformat()}
