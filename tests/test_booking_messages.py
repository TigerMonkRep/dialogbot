"""E07: booking communication templates in eight languages, previewed without sending anything."""
from __future__ import annotations

import re

import pytest
from sqlalchemy import func, select

from app.config import get_settings
from app.core.languages import LANGUAGES
from app.models import ActionRun, Booking, EmailDelivery, OutboxEvent
from app.modules.bookings import messages as m
from app.modules.integrations.connectors.fakes import WORLD
from tests.qa.test_qa_integ_E07 import _call, _ready


@pytest.fixture
def fake(monkeypatch):
    monkeypatch.setenv("CONNECTORS_PROVIDER", "fake")
    monkeypatch.delenv("TELEPHONY_PROVIDER", raising=False)
    get_settings.cache_clear()
    WORLD.reset()
    yield WORLD
    WORLD.reset()
    get_settings.cache_clear()


SIGN = {"da": "Vh Hansen VVS", "en": "Kind regards, Hansen VVS", "de": "Freundliche Grüße, Hansen VVS",
        "es": "Saludos, Hansen VVS", "fr": "Cordialement, Hansen VVS", "it": "Cordiali saluti, Hansen VVS",
        "no": "Mvh Hansen VVS", "sv": "Mvh Hansen VVS"}


@pytest.mark.parametrize("lang", LANGUAGES)
def test_every_variant_exists_filled_and_follows_the_sms_rules(lang):
    got = m.samples(lang)
    assert tuple(got) == m.VARIANTS
    for v, r in got.items():
        mail = r["email"]
        blob = mail.subject + mail.text() + (r["sms"]["text"] if r["sms"] else "")
        assert not re.search(r"\{\w+\}", blob), (lang, v, blob)  # every placeholder filled
        assert not re.search("[\U0001F300-\U0001FAFF☀-➿]", blob), (lang, v)
        if v in m.CUSTOMER_VARIANTS:
            s = r["sms"]
            assert s["chars"] <= 160 and s["text"].endswith(SIGN[lang]), (lang, v, s)
            assert "Dialogbot" not in s["text"] and "http" not in s["text"] and "!" not in s["text"], (lang, v)
            if s["encoding"] == "GSM-7":
                assert s["segments"] == 1, (lang, v, s)
            # the customer's mail is the business's: its name in the header and signature, no Dialogbot company line
            h = mail.html()
            assert mail.sender == "Hansen VVS" and ">Hansen VVS</strong>" in h and "CVR-nr. 25632710" not in h
            assert "icon-192.png" not in h and "button" not in mail.text().lower()
        else:
            assert r["sms"] is None and mail.sender is None and mail.button_url.endswith("/app/aftaler")
    if lang != "da":
        da = m.samples("da")
        assert all(got[v]["email"].subject != da[v]["email"].subject for v in m.VARIANTS), lang  # translated


def test_segments_are_counted_honestly():
    assert m.segments("a" * 160) == {"chars": 160, "encoding": "GSM-7", "segments": 1}
    assert m.segments("a" * 161)["segments"] == 2
    assert m.segments("€" * 80)["segments"] == 1 and m.segments("€" * 81)["segments"] == 2  # extension = 2 septets
    assert m.segments("está" * 18) == {"chars": 72, "encoding": "UCS-2", "segments": 2}


def test_contents_carry_the_times_and_reasons():
    d = m.samples("da")
    assert "tirsdag 3. november kl. 10.00" in d["confirmed"]["sms"]["text"]
    assert "onsdag 4. november kl. 14.00" in d["rescheduled"]["sms"]["text"]
    assert d["proposed_change"]["email"].rows[-1] == ("Ny tid", "onsdag 4. november kl. 14.00")
    assert "kunne ikke skrives i jeres kalender" in d["owner_attention"]["email"].text()
    fail = d["delivery_failure"]["email"].text()
    assert "«Aftale bekræftet»" in fail and "nummeret findes ikke" in fail and "SMS" in fail
    de = m.samples("de")
    assert "Sie" in de["confirmed"]["email"].text() and "Dienstag, 3. November um 10:00 Uhr" in de["confirmed"]["sms"]["text"]


def test_preview_endpoint_sends_nothing_and_is_tenant_scoped(api, client, fake, db):
    tok, ws = _ready(api, client, "e07-preview")
    slots = _call(db, ws, "ledige_tider", {})["run"]["output"]["tider"]
    _call(db, ws, "book_tid", {"start": slots[0]["start"], "navn": "Mette Nielsen", "bekraeftet": True})
    booking = db.scalar(select(Booking).where(Booking.workspace_id == ws))
    before = (db.scalar(select(func.count()).select_from(OutboxEvent)), db.scalar(select(func.count()).select_from(EmailDelivery)),
              db.scalar(select(func.count()).select_from(ActionRun)), len(fake.sms))
    r = api.get(tok, f"/workspaces/{ws}/bookings/messages")
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["sends_nothing"] is True and out["lang"] == out["default_lang"] == "da" and out["languages"] == list(LANGUAGES)
    assert [x["variant"] for x in out["items"]] == list(m.VARIANTS) and out["source"] == "sample"
    conf = next(x for x in out["items"] if x["variant"] == "confirmed")
    assert "Fjord Gulvservice ApS" in conf["sms"]["text"] and conf["email"]["from_name"] == "Fjord Gulvservice ApS"
    assert conf["email"]["html"].startswith("<!doctype html>")
    for lang in LANGUAGES:
        x = api.get(tok, f"/workspaces/{ws}/bookings/messages?lang={lang}").json()
        assert x["lang"] == lang and len(x["items"]) == 8
    own = api.get(tok, f"/workspaces/{ws}/bookings/messages?booking_id={booking.id}&lang=en").json()
    assert own["source"] == "booking" and "Hi Mette." in own["items"][1]["sms"]["text"]
    db.expire_all()
    after = (db.scalar(select(func.count()).select_from(OutboxEvent)), db.scalar(select(func.count()).select_from(EmailDelivery)),
             db.scalar(select(func.count()).select_from(ActionRun)), len(fake.sms))
    assert after == before  # a preview queues, sends and logs nothing
    other_tok = api.user("e07-other@testmail.dk")
    other_ws = api.workspace(other_tok, "Havnebord Café")
    assert api.get(other_tok, f"/workspaces/{other_ws}/bookings/messages?booking_id={booking.id}").status_code == 404
    assert api.get(other_tok, f"/workspaces/{ws}/bookings/messages").status_code in (403, 404)
