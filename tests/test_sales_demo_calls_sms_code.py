"""F-AUD26-02-P06 · «Ring mig op nu» rings only a number its visitor proved with an SMS code (Fürster 12/11: «A,
SMS-kode først»). Code: 6 digits, 10 minutes, 5 attempts; token: one use, bound to the number, 10 minutes; limits per
number (shared with the /start quiz) and per client IP (the BFF-signed address with CLIENT_IP_SECRET) on codes and
calls; do-not-call: no SMS, same answer; SMS text GSM-7 in 8 languages. Fake SMS and fake Vapi: nothing leaves."""
from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from alembic.config import Config
from sqlalchemy import text

from alembic import command
from app.config import get_settings
from app.models import DemoCall, DemoCallVerification
from app.modules.integrations.connectors.fakes import WORLD
from app.modules.privat.lookup_limits import client_ip_sig
from app.modules.sales import verification
from tests.test_sales_demo_calls import _unproven, _web, last_code, sales  # noqa: F401 – the fixture

GSM7 = set("@£$¥èéùìòÇ\nØø\rÅåΔ_ΦΓΛΩΠΨΣΘΞÆæßÉ !\"#¤%&'()*+,-./0123456789:;<=>?¡ABCDEFGHIJKLMNOPQRSTUVWXYZÄÖÑÜ§"
           "¿abcdefghijklmnopqrstuvwxyzäöñüà")


def _code(client, phone="20 30 40 50", **kw):
    return client.post("/api/v1/demo-call/code", json={"phone": phone, "consent": True} | kw)


def _verify(client, vid, code):
    return client.post("/api/v1/demo-call/verify", json={"verification_id": vid, "code": code})


def _later(sales, **delta):  # noqa: F811
    sales["clock"][0] = sales["clock"][0] + timedelta(**delta)


@pytest.mark.parametrize("lang", verification.LANGUAGES)
def test_sms_text_is_gsm7_one_segment_in_every_language(lang):
    body = verification.sms_text("123456", lang)
    assert "123456" in body and "10" in body and "Dialogbot" in body
    assert set(body) <= GSM7, set(body) - GSM7
    assert len(body) <= 160


def test_the_code_goes_to_the_number_in_the_page_language_and_the_call_follows(client, sales, db):  # noqa: F811
    r = _code(client, language="de")
    assert r.status_code == 202, r.text
    out = r.json()
    assert out["status"] == "code_sent" and out["phone_display"] == "20 30 40 50"
    assert (out["resend_after"], out["expires_in"]) == (30, 600)
    assert [m["to"] for m in WORLD.sms] == ["+4520304050"] and WORLD.sms[0]["from"] == "Dialogbot"
    assert WORLD.sms[0]["body"].startswith("Ihr Code für Dialogbot ist ")
    assert sales["calls"] == []  # a code alone rings nobody
    row = db.query(DemoCallVerification).one()
    assert last_code("+4520304050") not in (row.code_hash, row.ip_hash)  # only HMACs are stored
    v = _verify(client, out["verification_id"], last_code("+4520304050"))
    assert v.status_code == 200 and v.json()["status"] == "verified"
    r = _unproven(client, verification_token=v.json()["verification_token"])
    assert r.status_code == 202 and r.json() == {"status": "calling"}
    assert len(sales["calls"]) == 1
    db.expire_all()
    row = db.query(DemoCallVerification).one()
    assert row.consumed_at is not None and row.demo_call_id == db.query(DemoCall).one().id


def test_five_attempts_then_a_new_code(client, sales):  # noqa: F811
    vid = _code(client).json()["verification_id"]
    lefts = []
    for _ in range(5):
        r = _verify(client, vid, "000000")
        assert r.status_code == 422 and r.json()["code"] == "code_invalid"
        lefts.append(r.json()["attempts_left"])
    assert lefts == [4, 3, 2, 1, 0]
    r = _verify(client, vid, last_code("+4520304050"))  # even the right code: too late
    assert r.status_code == 409 and r.json()["code"] == "too_many_attempts"
    assert sales["calls"] == []


def test_the_code_expires_after_10_minutes_and_the_token_too(client, sales):  # noqa: F811
    vid = _code(client).json()["verification_id"]
    _later(sales, minutes=10, seconds=1)
    r = _verify(client, vid, last_code("+4520304050"))
    assert r.status_code == 409 and r.json()["code"] == "code_expired"
    vid = _code(client).json()["verification_id"]
    token = _verify(client, vid, last_code("+4520304050")).json()["verification_token"]
    _later(sales, minutes=10, seconds=1)
    r = _unproven(client, verification_token=token)
    assert r.status_code == 409 and r.json()["code"] == "verification_invalid"
    assert sales["calls"] == []


def test_a_used_code_cannot_be_verified_twice(client, sales):  # noqa: F811
    vid = _code(client).json()["verification_id"]
    code = last_code("+4520304050")
    assert _verify(client, vid, code).status_code == 200
    assert _verify(client, vid, code).json()["code"] == "code_expired"
    assert _verify(client, "not-a-uuid", code).json()["code"] == "code_expired"


def test_resend_after_30_seconds_per_number(client, sales):  # noqa: F811
    assert _code(client).status_code == 202
    r = _code(client)
    assert r.status_code == 409 and r.json()["code"] == "too_soon" and 1 <= r.json()["retry_after"] <= 30
    _later(sales, seconds=31)
    assert _code(client).status_code == 202
    assert len(WORLD.sms) == 2


def test_per_number_limit_whatever_the_ip(client, sales, monkeypatch):  # noqa: F811
    monkeypatch.setenv("CLIENT_IP_SECRET", "test-client-ip-secret")
    get_settings.cache_clear()
    statuses = []
    for i in range(verification.SMS_PER_NUMBER_HOUR + 1):
        ip = f"198.51.100.{i + 1}"
        h = {"x-dialogbot-client-ip": ip, "x-dialogbot-client-ip-sig": client_ip_sig("test-client-ip-secret", ip)}
        statuses.append(client.post("/api/v1/demo-call/code", headers=h,
                                    json={"phone": "20 30 40 50", "consent": True}).status_code)
        _later(sales, seconds=31)
    assert statuses == [202] * verification.SMS_PER_NUMBER_HOUR + [429]
    assert len(WORLD.sms) == verification.SMS_PER_NUMBER_HOUR


def test_per_ip_limits_count_the_signed_client_ip(client, sales, monkeypatch):  # noqa: F811
    """With CLIENT_IP_SECRET the BFF-signed address counts: one visitor runs into the limit, another does not – and a
    forged X-Forwarded-For moves nothing."""
    monkeypatch.setenv("CLIENT_IP_SECRET", "test-client-ip-secret")
    get_settings.cache_clear()

    def h(ip):
        return {"x-dialogbot-client-ip": ip, "x-dialogbot-client-ip-sig": client_ip_sig("test-client-ip-secret", ip),
                "x-forwarded-for": f"10.0.0.{len(WORLD.sms)}"}

    phones = [f"2{i}304050" for i in range(verification.SMS_PER_IP_HOUR + 1)]
    rs = [client.post("/api/v1/demo-call/code", headers=h("203.0.113.7"), json={"phone": p, "consent": True})
          for p in phones]
    assert [r.status_code for r in rs] == [202] * verification.SMS_PER_IP_HOUR + [429]
    assert rs[-1].json()["code"] == "sms_rate_limited"
    other = client.post("/api/v1/demo-call/code", headers=h("203.0.113.8"), json={"phone": phones[-1], "consent": True})
    assert other.status_code == 202


def test_per_ip_limit_on_calls(client, sales, monkeypatch):  # noqa: F811
    monkeypatch.setattr(verification, "CALLS_PER_IP_HOUR", 2)
    assert _web(client, phone="21 30 40 50").status_code == 202
    assert _web(client, phone="22 30 40 50").status_code == 202
    r = _web(client, phone="23 30 40 50")
    assert r.status_code == 429 and r.json()["code"] == "demo_rate_limited"
    assert len(sales["calls"]) == 2


def test_no_code_for_a_number_already_rung_today_or_when_demo_calls_are_off(client, sales, monkeypatch):  # noqa: F811
    assert _web(client).status_code == 202
    _later(sales, minutes=5)
    r = _code(client)
    assert r.status_code == 429 and r.json()["code"] == "demo_already_called"
    monkeypatch.delenv("SALES_WORKSPACE_ID")
    get_settings.cache_clear()
    r = _code(client, phone="21 30 40 50")
    assert r.status_code == 503 and r.json()["code"] == "demo_unavailable"
    assert len(WORLD.sms) == 1


def test_consent_honeypot_and_number_checks_come_before_any_sms(client, sales):  # noqa: F811
    assert _code(client, consent=False).status_code == 422
    assert _code(client, consent_version="demo-call-web-v0").json()["code"] == "consent_outdated"
    assert _code(client, phone="+46701234567").status_code == 422
    assert _code(client, phone="90 12 34 56").status_code == 422
    bot = _code(client, website="http://spam")
    assert bot.status_code == 202 and bot.json()["status"] == "code_sent"
    assert WORLD.sms == []


def test_sms_failure_is_reported(client, sales, db):  # noqa: F811
    WORLD.fail_next.add("sms")
    r = _code(client)
    assert r.status_code == 502 and r.json()["code"] == "sms_failed"
    assert db.query(DemoCallVerification).count() == 0  # rolled back: it does not count against the visitor


def _shape(r):
    body = r.json()
    return r.status_code, body.get("status") or body.get("code"), sorted(body)


def test_a_do_not_call_number_gets_the_same_answers_as_any_number_over_many_codes(client, sales, db, monkeypatch):  # noqa: F811
    """F-VER1112-01-P06: the do-not-call branch must spend the same per-number, per-IP and global budgets (and the
    30 s resend wait) as any number, so a 5th code in an hour gives 429 for both – and still no SMS to the opt-out."""
    from app.models import DoNotCall

    db.add(DoNotCall(workspace_id=uuid.UUID(sales["ws"]), phone="+4520304051", source="call"))
    db.commit()
    monkeypatch.setenv("CLIENT_IP_SECRET", "test-client-ip-secret")
    get_settings.cache_clear()

    def run(phone, net):
        out = []
        for i in range(verification.SMS_PER_NUMBER_HOUR + 1):
            ip = f"198.51.{net}.{i + 1}"  # a fresh IP each time: the per-number limit is what bites
            h = {"x-dialogbot-client-ip": ip, "x-dialogbot-client-ip-sig": client_ip_sig("test-client-ip-secret", ip)}
            out.append(_shape(client.post("/api/v1/demo-call/code", headers=h,
                                          json={"phone": phone, "consent": True})))
            out.append(_shape(client.post("/api/v1/demo-call/code", headers=h,
                                          json={"phone": phone, "consent": True})))  # inside the 30 s wait
            _later(sales, seconds=31)
        return out

    plain, blocked = run("20 30 40 50", 100), run("20 30 40 51", 101)
    assert plain == blocked
    assert [s for s, _, _ in plain] == [202, 409] * verification.SMS_PER_NUMBER_HOUR + [429, 429]
    assert {m["to"] for m in WORLD.sms} == {"+4520304050"}  # never an SMS to the do-not-call number
    assert len(WORLD.sms) == verification.SMS_PER_NUMBER_HOUR
    assert sales["calls"] == []


def test_the_quiz_shares_the_per_number_sms_limit(client, sales, db):  # noqa: F811
    """/start sends its own code to the number it rings; codes to one number from both doors share one budget."""
    for _ in range(verification.SMS_PER_NUMBER_HOUR):
        assert _code(client).status_code == 202
        _later(sales, seconds=31)
    did = client.post("/api/v1/funnel/drafts", json={"kind": "erhverv"}).json()["id"]
    r = client.post(f"/api/v1/funnel/drafts/{did}/gate", json={"name": "Mette", "email": "mette@testmail.dk",
                                                               "phone": "20 30 40 50", "consent": True})
    assert r.status_code == 429 and r.json()["code"] == "sms_rate_limited"


def test_rows_are_purged_after_two_days(client, sales, db):  # noqa: F811
    sales["clock"][0] = datetime.now(UTC)  # created_at is the database's now()
    assert _code(client).status_code == 202 and _code(client, phone="21 30 40 50").status_code == 202
    db.execute(text("update demo_call_verifications set created_at = now() - interval '3 days' "
                    "where phone = '+4520304050'"))
    db.commit()
    assert verification.purge(db) == 1
    assert [v.phone for v in db.query(DemoCallVerification)] == ["+4521304050"]


def test_migration_down_and_up(db):
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    cfg = Config(os.path.join(root, "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(root, "alembic"))
    db.close()
    command.downgrade(cfg, "0c1d5e7a9b3f")
    try:
        with db.bind.connect() as conn:
            assert conn.execute(text("select to_regclass('demo_call_verifications')")).scalar() is None
    finally:
        command.upgrade(cfg, "head")
    with db.bind.connect() as conn:
        assert conn.execute(text("select to_regclass('demo_call_verifications')")).scalar() == "demo_call_verifications"
