"""Public waitlist: consent required, idempotent per e-mail, no enumeration, honeypot."""
from __future__ import annotations

from sqlalchemy import select

from app.models import WaitlistSignup

URL = "/api/v1/waitlist"


def _join(client, **over):
    body = {"email": "Mads@Virksomhed.DK", "industry": "craft", "interests": ["missed_calls"], "consent": True} | over
    return client.post(URL, json=body)


def test_signup_is_stored_normalised(client, db):
    r = _join(client)
    assert r.status_code == 202 and r.json() == {"status": "received"}
    row = db.scalars(select(WaitlistSignup)).one()
    assert (row.email, row.industry, row.interests, row.source, row.consent_version) == \
        ("mads@virksomhed.dk", "craft", ["missed_calls"], "p00", "waitlist-v1")


def test_repeat_signup_updates_answers_and_gives_same_response(client, db):
    first = _join(client)
    again = _join(client, email="mads@virksomhed.dk", industry="clinic", interests=["quote_followup", "calendar_booking"])
    assert first.json() == again.json() and again.status_code == 202
    row = db.scalars(select(WaitlistSignup)).one()
    assert row.industry == "clinic" and row.interests == ["calendar_booking", "quote_followup"]


def test_consent_and_validation(client, db):
    assert _join(client, consent=False).status_code == 422
    assert _join(client, email="ikke-en-mail").status_code == 422
    assert _join(client, industry="casino").status_code == 422
    assert _join(client, interests=["missed_calls"] * 4).status_code == 422
    assert db.scalars(select(WaitlistSignup)).all() == []


def test_honeypot_is_accepted_but_not_stored(client, db):
    r = _join(client, website="http://spam.example")
    assert r.status_code == 202 and r.json() == {"status": "received"}
    assert db.scalars(select(WaitlistSignup)).all() == []
