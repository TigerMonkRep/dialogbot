"""QA A01 (e2e-erhverv instans A): independent signup preserves reception/campaigns/both.

Krav A01: "Independent signup; preserve whether the visitor chose reception, campaigns or both."
DB-013: invite never creates subscription; tenant isolation (checked in A05/S02).
"""
from __future__ import annotations

import pytest
from sqlalchemy import func, select

from app.models import User, Workspace


@pytest.mark.parametrize("intent,inbound", [("reception", True), ("campaigns", False), ("both", True)])
def test_intent_survives_signup_verify_and_first_workspace(api, db, intent, inbound):
    email = f"a01-{intent}@testmail.dk"
    out = api.register(email, intent=intent)
    assert out["signup_intent"] == intent and out["email_verified"] is False
    tok = api.login(email)
    assert api.get(tok, "/auth/me").json()["signup_intent"] == intent
    api.verify(tok)
    # The workspace is created WITHOUT repeating the intent: the signup choice must be the default.
    r = api.c.post("/api/v1/workspaces", json={"name": f"A01 {intent} ApS"}, headers=api.h(tok))
    assert r.status_code == 201, r.text
    ws = r.json()
    assert ws["product_intent"] == intent and ws["role"] == "owner"
    goals = api.get(tok, f"/workspaces/{ws['id']}/goals").json()
    assert goals["product_intent"] == intent
    assert goals["inbound_phone"] is inbound


def test_signup_rejects_unknown_intent_and_duplicate_email_case_insensitive(api, db):
    r = api.c.post("/api/v1/auth/register", json={"email": "a01-x@testmail.dk", "password": "CorrectHorse!42",
                                                   "display_name": "X", "signup_intent": "everything"})
    assert r.status_code == 422
    assert db.scalar(select(func.count()).select_from(User)) == 0
    api.register("a01-dup@testmail.dk")
    r = api.c.post("/api/v1/auth/register", json={"email": "A01-DUP@testmail.dk", "password": "CorrectHorse!42",
                                                   "display_name": "Y", "signup_intent": "reception"})
    assert r.status_code == 409 and r.json()["code"] == "email_taken"


def test_unverified_user_cannot_create_workspace(api, db):
    api.register("a01-unv@testmail.dk", intent="campaigns")
    tok = api.login("a01-unv@testmail.dk")
    r = api.c.post("/api/v1/workspaces", json={"name": "Uverificeret ApS"}, headers=api.h(tok))
    assert r.status_code == 403 and r.json()["code"] == "email_not_verified"
    assert db.scalar(select(func.count()).select_from(Workspace)) == 0


def test_short_password_rejected_without_creating_user(api, db):
    r = api.c.post("/api/v1/auth/register", json={"email": "a01-short@testmail.dk", "password": "kort",
                                                   "display_name": "Kort", "signup_intent": "reception"})
    assert r.status_code == 422
    assert db.scalar(select(func.count()).select_from(User)) == 0


def test_register_with_overlong_interface_language_is_a_validation_error_not_500(api, db):
    """RegisterIn.interface_language has no max_length; users.interface_language is String(16)."""
    r = api.c.post("/api/v1/auth/register", json={"email": "a01-lang@testmail.dk", "password": "CorrectHorse!42",
                                                   "display_name": "Sprog", "signup_intent": "reception",
                                                   "interface_language": "x" * 40})
    assert r.status_code in (400, 422), f"expected a validation error, got {r.status_code}: {r.text[:200]}"
