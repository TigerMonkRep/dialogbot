"""Live bug 11/11: a Dialogbot Privat sign-up got the blue Erhverv verify mail and landed in the business set-up."""
from __future__ import annotations

from sqlalchemy import select

from app.models import OutboxEvent
from app.modules.integrations import email_templates as tpl


def _verify_event(db, email):
    evs = db.scalars(select(OutboxEvent).where(OutboxEvent.event_type == "email.verify_address")).all()
    return next(e for e in evs if e.payload["to_email"] == email)


def test_privat_signup_gets_the_privat_mail_and_link(api, client, db):
    r = api.c.post(f"{api.base}/auth/register", json={"email": "p@testmail.dk", "password": "hemmelig-kode-1",
                                            "display_name": "Pia", "signup_intent": "privat"})
    assert r.status_code == 201, r.text
    ev = _verify_event(db, "p@testmail.dk")
    assert ev.payload["audience"] == "privat"
    assert ev.payload["link"].endswith("&for=privat")
    mail = tpl.verify(ev.payload["link"], lang="da", privat=True)
    html = mail.html()
    assert mail.audience == "privat"
    assert tpl.PRIVAT_ACCENT in html and tpl.ACCENT not in html
    assert "Dialogbot Privat" in html and "/icons/privat-icon-192.png" in html
    assert "AI-receptionist" not in html and "Dialogbot Privat" in mail.heading


def test_erhverv_signup_keeps_the_blue_mail(api, client, db):
    api.register("e@testmail.dk", intent="reception")
    ev = _verify_event(db, "e@testmail.dk")
    assert "audience" not in ev.payload and "for=privat" not in ev.payload["link"]
    html = tpl.verify(ev.payload["link"], lang="da").html()
    assert tpl.ACCENT in html and tpl.PRIVAT_ACCENT not in html and "privat-icon" not in html


def test_privat_verify_texts_in_every_language():
    for lang in ("da", "en", "de", "es", "fr", "it", "no", "sv"):
        m = tpl.verify("https://x/verify-email?token=t&for=privat", lang=lang, privat=True)
        assert "Dialogbot Privat" in m.heading and "Dialogbot Privat" in m.paragraphs[0], lang


def test_privat_signup_can_still_create_a_business(api, db):
    """F-JE-01: «privat» is not a product – a Privat sign-up who creates a company gets the default product."""
    r = api.c.post(f"{api.base}/auth/register", json={"email": "both@testmail.dk", "password": "hemmelig-kode-1",
                                                       "display_name": "Bo", "signup_intent": "privat"})
    assert r.status_code == 201, r.text
    tok = api.login("both@testmail.dk", password="hemmelig-kode-1")
    api.verify(tok)
    r = api.post(tok, "/workspaces", {"name": "Bo ApS", "product_intent": "privat"})
    assert r.status_code == 201, r.text
    assert r.json()["product_intent"] == "reception"
    r = api.post(tok, "/workspaces", {"name": "Bo 2 ApS"})
    assert r.status_code == 201 and r.json()["product_intent"] == "reception", r.text
