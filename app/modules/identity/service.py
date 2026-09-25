from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session as OrmSession

from app.config import get_settings
from app.core.audit import record_audit
from app.core.errors import Conflict, Unauthenticated, ValidationFailed
from app.core.outbox import enqueue
from app.core.security import hash_password, new_token, normalize_email, token_digest, verify_password
from app.models import AuthToken, Session, User

INTENTS = ("reception", "campaigns", "both")


def _now() -> datetime:
    return datetime.now(UTC)


def register(db: OrmSession, *, email: str, password: str, display_name: str, signup_intent: str | None,
             interface_language: str = "da", request_id: str | None = None) -> User:
    if len(password) < 10:
        raise ValidationFailed("Adgangskoden skal være mindst 10 tegn", field_errors=[{"field": "password"}])
    if signup_intent is not None and signup_intent not in INTENTS:
        raise ValidationFailed("Ugyldig produktintention", field_errors=[{"field": "signup_intent"}])
    norm = normalize_email(email)
    if db.scalar(select(User).where(User.email_normalized == norm)):
        raise Conflict("E-mailen er allerede registreret", code="email_taken")
    user = User(
        email=email.strip(), email_normalized=norm, password_hash=hash_password(password),
        display_name=display_name.strip(), signup_intent=signup_intent, interface_language=interface_language,
    )
    db.add(user)
    db.flush()
    issue_verification(db, user)
    record_audit(db, workspace_id=None, actor_user_id=user.id, action="user.registered", object_type="user",
                 object_id=user.id, after={"email": norm, "signup_intent": signup_intent}, request_id=request_id)
    return user


def issue_verification(db: OrmSession, user: User) -> None:
    s = get_settings()
    raw = new_token()
    db.add(AuthToken(user_id=user.id, purpose="verify_email", token_hash=token_digest(raw),
                     expires_at=_now() + timedelta(hours=s.verification_ttl_hours)))
    link = f"{s.frontend_base_url}/verify-email?token={raw}"
    enqueue(db, event_type="email.verify_address", dedupe_key=f"verify:{user.id}:{token_digest(raw)[:16]}",
            payload={"user_id": str(user.id), "to_email": user.email, "link": link})


def verify_email(db: OrmSession, raw_token: str) -> User:
    tok = _consume(db, raw_token, "verify_email")
    user = db.get(User, tok.user_id)
    assert user is not None
    if user.email_verified_at is None:
        user.email_verified_at = _now()
    return user


def _consume(db: OrmSession, raw_token: str, purpose: str) -> AuthToken:
    tok = db.scalar(select(AuthToken).where(AuthToken.token_hash == token_digest(raw_token),
                                            AuthToken.purpose == purpose).with_for_update())
    if tok is None or tok.used_at is not None:
        raise ValidationFailed("Linket er ugyldigt eller allerede brugt", code="token_invalid")
    if tok.expires_at <= _now():
        raise ValidationFailed("Linket er udløbet", code="token_expired")
    tok.used_at = _now()
    return tok


def login(db: OrmSession, *, email: str, password: str, user_agent: str | None) -> tuple[User, str]:
    s = get_settings()
    user = db.scalar(select(User).where(User.email_normalized == normalize_email(email)))
    # Constant-shape failure regardless of which part was wrong.
    if user is None or not user.is_active or not verify_password(password, user.password_hash):
        raise Unauthenticated("Forkert e-mail eller adgangskode", code="invalid_credentials")
    raw = new_token()
    db.add(Session(user_id=user.id, token_hash=token_digest(raw),
                   expires_at=_now() + timedelta(hours=s.session_ttl_hours), user_agent=(user_agent or "")[:400]))
    return user, raw


def logout(db: OrmSession, session: Session) -> None:
    session.revoked_at = _now()


def request_password_reset(db: OrmSession, email: str) -> None:
    """Always succeeds from the caller's perspective (no account enumeration)."""
    s = get_settings()
    user = db.scalar(select(User).where(User.email_normalized == normalize_email(email)))
    if user is None:
        return
    raw = new_token()
    db.add(AuthToken(user_id=user.id, purpose="password_reset", token_hash=token_digest(raw),
                     expires_at=_now() + timedelta(minutes=s.reset_ttl_minutes)))
    link = f"{s.frontend_base_url}/password/reset?token={raw}"
    enqueue(db, event_type="email.password_reset", dedupe_key=f"reset:{user.id}:{token_digest(raw)[:16]}",
            payload={"user_id": str(user.id), "to_email": user.email, "link": link})


def reset_password(db: OrmSession, *, raw_token: str, new_password: str) -> User:
    if len(new_password) < 10:
        raise ValidationFailed("Adgangskoden skal være mindst 10 tegn", field_errors=[{"field": "password"}])
    tok = _consume(db, raw_token, "password_reset")
    user = db.get(User, tok.user_id)
    assert user is not None
    user.password_hash = hash_password(new_password)
    # Revoke all sessions after a reset.
    for sess in db.scalars(select(Session).where(Session.user_id == user.id, Session.revoked_at.is_(None))):
        sess.revoked_at = _now()
    record_audit(db, workspace_id=None, actor_user_id=user.id, action="user.password_reset",
                 object_type="user", object_id=user.id)
    return user


def list_sessions(db: OrmSession, user_id: uuid.UUID) -> list[Session]:
    return list(db.scalars(select(Session).where(Session.user_id == user_id, Session.revoked_at.is_(None),
                                                 Session.expires_at > _now()).order_by(Session.created_at.desc())))
