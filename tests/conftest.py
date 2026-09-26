"""Integration test fixtures.

All tests run against a real PostgreSQL database (TEST_DATABASE_URL), migrated
with Alembic from empty at session start (acceptance criterion 10). Tables are
truncated between tests.
"""
from __future__ import annotations

import os
import re

os.environ.setdefault("APP_ENV", "test")
os.environ["DATABASE_URL"] = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+psycopg://postgres@localhost:5432/dialogbot_test"
)
os.environ["ENABLE_DEV_TOOLS"] = "true"
os.environ["EMAIL_ADAPTER"] = "simulated"
os.environ["FRONTEND_BASE_URL"] = "http://frontend.test"

import pytest  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

from alembic import command  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.db import Base, get_engine, get_session_factory  # noqa: E402
from app.main import create_app  # noqa: E402
from app.worker import runner  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture(scope="session", autouse=True)
def migrated_database():
    get_settings.cache_clear()
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(text("drop schema public cascade; create schema public;"))
    cfg = Config(os.path.join(ROOT, "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(ROOT, "alembic"))
    command.upgrade(cfg, "head")
    with engine.connect() as conn:
        assert conn.execute(text("select version_num from alembic_version")).scalar()
    yield


@pytest.fixture(autouse=True)
def clean_tables():
    yield
    engine = get_engine()
    tables = [t.name for t in reversed(Base.metadata.sorted_tables)]
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE " + ", ".join(tables) + " RESTART IDENTITY CASCADE"))
    runner.FAIL_EVENT_TYPES.clear()


@pytest.fixture(scope="session")
def app():
    return create_app()


@pytest.fixture
def client(app):
    return TestClient(app)


@pytest.fixture
def db():
    s = get_session_factory()()
    try:
        yield s
    finally:
        s.close()


class Api:
    """Thin helper that mirrors the documented client flow."""

    def __init__(self, client: TestClient):
        self.c = client
        self.base = "/api/v1"

    def register(self, email: str, name: str = "Test", password: str = "CorrectHorse!42", intent="reception"):
        r = self.c.post(f"{self.base}/auth/register", json={"email": email, "password": password,
                                                            "display_name": name, "signup_intent": intent})
        assert r.status_code == 201, r.text
        return r.json()

    def login(self, email: str, password: str = "CorrectHorse!42") -> str:
        r = self.c.post(f"{self.base}/auth/login", json={"email": email, "password": password})
        assert r.status_code == 200, r.text
        return r.json()["access_token"]

    def h(self, token: str, **extra) -> dict:
        return {"Authorization": f"Bearer {token}", **extra}

    def mailbox_link(self, token: str, subject_part: str, pattern: str) -> str:
        runner.drain()
        r = self.c.get(f"{self.base}/dev/mailbox", headers=self.h(token))
        assert r.status_code == 200, r.text
        for m in r.json()["items"]:
            if subject_part in m["subject"]:
                found = re.search(pattern, m["body_text"])
                if found:
                    return found.group(1)
        raise AssertionError(f"no mail with {subject_part!r}")

    def verify(self, token: str) -> None:
        raw = self.mailbox_link(token, "Bekræft", r"verify-email\?token=([A-Za-z0-9_\-]+)")
        r = self.c.post(f"{self.base}/auth/verify-email", json={"token": raw})
        assert r.status_code == 200, r.text

    def user(self, email: str, intent="reception") -> str:
        """register + verify + login → session token"""
        self.register(email, intent=intent)
        tok = self.login(email)
        self.verify(tok)
        return tok

    def workspace(self, token: str, name: str, intent: str | None = None) -> str:
        r = self.c.post(f"{self.base}/workspaces", json={"name": name, "product_intent": intent}, headers=self.h(token))
        assert r.status_code == 201, r.text
        return r.json()["id"]

    def invite(self, token: str, ws: str, email: str, role="staff", key: str | None = None):
        headers = self.h(token)
        if key:
            headers["Idempotency-Key"] = key
        return self.c.post(f"{self.base}/workspaces/{ws}/invitations", json={"email": email, "role": role},
                           headers=headers)

    def invite_link(self, invitee_token: str) -> str:
        return self.mailbox_link(invitee_token, "inviteret", r"invite/([A-Za-z0-9_\-]+)")

    def add_member(self, owner_token: str, ws: str, email: str, role: str) -> str:
        """Invite + accept through the real flow. Returns the new member's session token."""
        r = self.invite(owner_token, ws, email, role)
        assert r.status_code == 201, r.text
        tok = self.user(email)
        raw = self.invite_link(tok)
        r = self.c.post(f"{self.base}/invitations/accept", json={"token": raw}, headers=self.h(tok))
        assert r.status_code == 200, r.text
        return tok

    def knowledge(self, token: str, ws: str, kind: str, title: str, content: dict | None = None):
        r = self.c.post(f"{self.base}/workspaces/{ws}/knowledge/items",
                        json={"kind": kind, "title": title, "content": content or {}}, headers=self.h(token))
        assert r.status_code == 201, r.text
        return r.json()

    def submit(self, token: str, ws: str, version_id: str):
        r = self.c.post(f"{self.base}/workspaces/{ws}/knowledge/versions/{version_id}/submit", headers=self.h(token))
        assert r.status_code == 200, r.text
        return r.json()

    def approve(self, token: str, ws: str, version_id: str, key: str | None = None):
        headers = self.h(token)
        if key:
            headers["Idempotency-Key"] = key
        return self.c.post(f"{self.base}/workspaces/{ws}/knowledge/versions/{version_id}/approve", headers=headers)

    def plan(self, token: str, ws: str) -> dict:
        r = self.c.get(f"{self.base}/workspaces/{ws}/setup/plan", headers=self.h(token))
        assert r.status_code == 200, r.text
        return r.json()

    def get(self, token: str, path: str):
        return self.c.get(f"{self.base}{path}", headers=self.h(token))

    def put(self, token: str, path: str, json: dict):
        return self.c.put(f"{self.base}{path}", json=json, headers=self.h(token))

    def delete(self, token: str, path: str):
        return self.c.delete(f"{self.base}{path}", headers=self.h(token))

    def post(self, token: str, path: str, json: dict | None = None, **headers):
        return self.c.post(f"{self.base}{path}", json=json, headers=self.h(token, **headers))


@pytest.fixture
def api(client) -> Api:
    return Api(client)


@pytest.fixture
def two_workspaces(api):
    """Owner A with workspace A (reception), owner B with workspace B (campaigns)."""
    tok_a = api.user("owner-a@testmail.dk", intent="reception")
    ws_a = api.workspace(tok_a, "Fjord Gulvservice ApS")
    tok_b = api.user("owner-b@testmail.dk", intent="campaigns")
    ws_b = api.workspace(tok_b, "Havnebord Café")
    return {"tok_a": tok_a, "ws_a": ws_a, "tok_b": tok_b, "ws_b": ws_b}
