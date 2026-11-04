"""Shared helpers for the Dialogbot Privat tests (tests/test_privat_*.py)."""
from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

from app.config import get_settings
from app.db import get_session_factory
from app.models import PrivateProfile, User
from app.modules.privat import rules

SECRET = "vapi-secret-privat-test"
POOL = "+4589870000"
# Wednesday 4 November 2026, 10:00 in Copenhagen (09:00 UTC): inside calling hours
WED_10 = datetime(2026, 11, 4, 9, 0, tzinfo=UTC)


class Clock:
    def __init__(self, at: datetime):
        self.at = at

    def __call__(self) -> datetime:
        return self.at


class Pv:
    """Thin client for /privat."""

    def __init__(self, api, clock: Clock):
        self.api, self.clock = api, clock

    def user(self, email: str, name: str = "Mette Hansen") -> str:
        self.api.register(email, name=name)
        tok = self.api.login(email)
        self.api.verify(tok)
        return tok

    def account(self, email: str, name: str = "Mette Hansen") -> str:
        tok = self.user(email, name)
        r = self.api.post(tok, "/privat/account")
        assert r.status_code == 200, r.text
        return tok

    def ws(self, tok: str) -> uuid.UUID:
        uid = self.uid(tok)
        with get_session_factory()() as db:
            return db.query(PrivateProfile).filter_by(user_id=uid).one().workspace_id

    def uid(self, tok: str) -> uuid.UUID:
        me = self.api.c.get("/api/v1/auth/me", headers=self.api.h(tok)).json()
        return uuid.UUID(me.get("id") or me["user"]["id"])

    def say(self, tok: str, text: str, about: str | None = None, key: str | None = None) -> dict:
        body = {"text": text, **({"about_task_id": about} if about else {})}
        r = self.api.post(tok, "/privat/messages", body, **({"Idempotency-Key": key} if key else {}))
        assert r.status_code == 200, r.text
        return r.json()

    def verify_phone(self, tok: str, e164: str = "+4520304050") -> None:
        uid = self.uid(tok)
        with get_session_factory()() as db:
            p = db.query(PrivateProfile).filter_by(user_id=uid).one()
            p.phone_e164, p.phone_verified_at = e164, self.clock()
            db.commit()

    def me(self, tok: str) -> dict:
        return self.api.get(tok, "/privat/me").json()

    def task(self, tok: str, tid: str):
        return self.api.get(tok, f"/privat/tasks/{tid}")

    def make_list(self, tok: str, text: str = "Lav en indkøbsliste med mælk og rugbrød") -> str:
        out = self.say(tok, text)
        return next(m["task_id"] for m in out["messages"] if m["kind"] == "task")


@pytest.fixture
def pv(api, monkeypatch):
    monkeypatch.setenv("PRIVAT_ENABLED", "true")
    monkeypatch.setenv("PRIVAT_ALLOWED_EMAILS", "")
    monkeypatch.setenv("AI_PROVIDER", "fake")
    monkeypatch.setenv("VAPI_SERVER_SECRET", SECRET)
    monkeypatch.setenv("VAPI_API_KEY", "vapi-private-key-test")
    monkeypatch.setenv("PRIVAT_POOL_NUMBERS", f"{POOL}=pn_pool")
    monkeypatch.setenv("CONNECTORS_PROVIDER", "fake")
    get_settings.cache_clear()
    clock = Clock(WED_10)
    monkeypatch.setattr(rules, "now", clock)
    yield Pv(api, clock)
    get_settings.cache_clear()


def user_row(db, email: str) -> User:
    return db.query(User).filter_by(email_normalized=email).one()
