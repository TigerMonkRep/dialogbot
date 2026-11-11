"""Hotfix regressions: SMS pumping through Privat (F-PS-01), bearer secrets in the request log (F-PS-04) and the
client IP behind Render's proxy (F-PS-02). Simulated SMS only (fake connectors)."""
from __future__ import annotations

from datetime import timedelta

import pytest
from starlette.requests import Request

from app.config import get_settings
from app.core.logging import redact_path
from app.modules.integrations.connectors.fakes import WORLD
from app.modules.privat import lookup_limits

P = "/api/v1/privat"
SECRET = "test-client-ip-secret-0123456789abcdef"


def _sms() -> list[dict]:
    with WORLD.lock:
        return list(WORLD.sms)


def _link(api, tok, g) -> str:
    r = api.post(tok, f"/privat/groups/{g['id']}/join-link")
    assert r.status_code == 200, r.text
    return r.json()["short_code"]


def _group(api, tok, name="Familien") -> dict:
    r = api.post(tok, "/privat/groups", {"name": name})
    assert r.status_code == 201, r.text
    return r.json()


def _join(api, code, phone, ip):
    return api.c.post(f"{P}/group-invites/by-code/{code}/join", json={"name": "X", "phone": phone},
                      headers={"x-forwarded-for": ip})


# --------------------------------------------------------------------------- F-PS-01 SMS pumping

@pytest.mark.parametrize("phone", ["+88213000001", "+447911123456", "90 12 34 56", "+4590123456", "12345678"])
def test_group_join_never_texts_a_non_danish_or_premium_number(api, pv, phone):
    mette = pv.account("pump-a@testmail.dk", trial=False)
    code = _link(api, mette, _group(api, mette))
    before = len(_sms())
    r = _join(api, code, phone, "198.51.100.1")
    assert r.status_code == 422 and r.json()["field_errors"][0]["field"] == "phone", r.text
    assert len(_sms()) == before
    assert _join(api, code, "22 33 44 55", "198.51.100.1").json() == {"joined": False, "code_sent": True}


def test_minting_more_links_never_buys_more_sms(api, pv):
    """One owner, five links, 20 tries each from fresh addresses: at most CODES_PER_OWNER_HOUR codes in the hour."""
    from app.modules.privat import groups

    mette = pv.account("pump-b@testmail.dk", trial=False)
    g = _group(api, mette, "Pump")
    codes = [_link(api, mette, g) for _ in range(5)]
    before, n = len(_sms()), 0
    for code in codes:
        for _ in range(20):
            n += 1
            _join(api, code, f"+4522{n:06d}", f"203.0.113.{n % 250}")
    sent = _sms()[before:]
    assert len(sent) == groups.CODES_PER_OWNER_HOUR and all(s["to"].startswith("+45") for s in sent)
    r = _join(api, codes[0], "+4523000001", "192.0.2.200")
    assert r.status_code == 429 and r.json()["code"] == "rate_limited"
    pv.clock.at += timedelta(hours=1, minutes=1)  # a new hour, a new budget
    assert _join(api, codes[0], "+4523000001", "192.0.2.201").json()["code_sent"] is True


def test_one_address_gets_a_limited_number_of_codes_across_owners(api, pv):
    a, b = pv.account("pump-c@testmail.dk", trial=False), pv.account("pump-d@testmail.dk", trial=False)
    codes = [_link(api, a, _group(api, a)), _link(api, b, _group(api, b))]
    before = len(_sms())
    statuses = [_join(api, codes[i % 2], f"+4524{i:06d}", "198.51.100.9").status_code
                for i in range(lookup_limits.SMS_PER_IP_HOUR + 2)]
    assert statuses.count(200) == lookup_limits.SMS_PER_IP_HOUR and statuses[-1] == 429
    assert len(_sms()) - before == lookup_limits.SMS_PER_IP_HOUR


def test_privat_wide_sms_ceiling(api, pv, monkeypatch):
    monkeypatch.setattr(lookup_limits, "SMS_GLOBAL_HOUR", 3)
    a, b = pv.account("pump-e@testmail.dk", trial=False), pv.account("pump-f@testmail.dk", trial=False)
    ca, cb = _link(api, a, _group(api, a)), _link(api, b, _group(api, b))
    assert [_join(api, ca, f"+4525{i:06d}", f"198.51.100.{20 + i}").status_code for i in range(3)] == [200] * 3
    assert _join(api, cb, "+4526000001", "198.51.100.40").status_code == 429
    tok = pv.account("pump-g@testmail.dk")
    assert api.post(tok, "/privat/phone/start", {"phone": "26 00 00 02"}).status_code == 429


@pytest.mark.parametrize("phone", ["+447911123456", "+88213000001", "90123456"])
def test_phone_start_only_texts_danish_numbers(api, pv, phone):
    tok = pv.account("ph-a@testmail.dk")
    before = len(_sms())
    r = api.post(tok, "/privat/phone/start", {"phone": phone})
    assert r.status_code == 422 and len(_sms()) == before, r.text


def test_phone_start_has_an_hourly_cap_per_account(api, pv):
    from app.modules.privat import phone

    tok = pv.account("ph-b@testmail.dk")
    out = []
    for i in range(phone.CODES_PER_ACCOUNT_HOUR + 1):
        out.append(api.post(tok, "/privat/phone/start", {"phone": f"2030405{i}"}).status_code)
        pv.clock.at += phone.RESEND_AFTER + timedelta(seconds=1)
    assert out == [200] * phone.CODES_PER_ACCOUNT_HOUR + [429], out


# --------------------------------------------------------------------------- F-PS-04 secrets in the log

TOK = "WyXshO-BrxEafSElcptuAbDaXEqS5K4esY_Lpe1F4ck"


@pytest.mark.parametrize("path", [
    f"/api/v1/privat/invites/{TOK}", f"/api/v1/privat/invites/{TOK}/accept", f"/api/v1/privat/invites/by-code/{TOK}",
    f"/api/v1/privat/invites/by-code/{TOK}/accept", f"/api/v1/privat/group-invites/by-code/{TOK}",
    f"/api/v1/privat/group-invites/by-code/{TOK}/join", f"/api/v1/privat/calendar/feed/{TOK}.ics",
    f"/api/v1/invitations/{TOK}", f"/api/v1/public/offers/{TOK}", f"/api/v1/public/offers/{TOK}/accept",
    f"/api/v1/public/calendar/{TOK}.ics", f"/api/v1/public/ambassadors/parent-consent/{TOK}",
])
def test_bearer_link_secrets_are_redacted_from_logged_paths(path):
    red = redact_path(path)
    assert TOK not in red and "***" in red, red


@pytest.mark.parametrize("path", [
    "/api/v1/invitations/accept", "/api/v1/workspaces/1f0c/invitations/9a2b/revoke", "/api/v1/privat/groups",
])
def test_ordinary_paths_are_logged_as_they_are(path):
    assert redact_path(path) == path


def test_request_log_line_has_no_invitation_token(api, capsys):
    api.c.get(f"{P}/invites/{TOK}")
    api.c.get(f"{P}/group-invites/by-code/ABCDEFGH")
    out = capsys.readouterr().out
    assert TOK not in out and "ABCDEFGH" not in out


# --------------------------------------------------------------------------- F-PS-02 client IP

def _req(headers: dict[str, str], peer: str = "10.1.2.3") -> Request:
    return Request({"type": "http", "method": "GET", "path": "/", "query_string": b"", "client": (peer, 1234),
                    "headers": [(k.lower().encode(), v.encode()) for k, v in headers.items()]})


@pytest.fixture
def ip_secret(monkeypatch):
    monkeypatch.setenv("CLIENT_IP_SECRET", SECRET)
    get_settings.cache_clear()
    yield SECRET
    get_settings.cache_clear()


def test_client_ip_takes_the_address_the_proxy_appended(ip_secret, monkeypatch):
    forged = {"x-forwarded-for": "203.0.113.5, 10.0.0.1, 198.51.100.77"}
    assert lookup_limits.client_ip(_req(forged)) == "198.51.100.77"
    assert lookup_limits.client_ip(_req({"x-forwarded-for": "198.51.100.77"})) == "198.51.100.77"
    assert lookup_limits.client_ip(_req({})) == "10.1.2.3"
    monkeypatch.setenv("TRUSTED_PROXY_HOPS", "2")
    get_settings.cache_clear()
    assert lookup_limits.client_ip(_req(forged)) == "10.0.0.1"


def test_client_ip_trusts_only_a_correctly_signed_bff_address(ip_secret):
    xff = {"x-forwarded-for": "203.0.113.5, 198.51.100.77"}  # BFF: visitor, then Render appends the BFF's egress
    good = {**xff, "x-dialogbot-client-ip": "203.0.113.5",
            "x-dialogbot-client-ip-sig": lookup_limits.client_ip_sig(SECRET, "203.0.113.5")}
    assert lookup_limits.client_ip(_req(good)) == "203.0.113.5"
    moved = {**good, "x-dialogbot-client-ip": "203.0.113.6"}  # signature of another address
    assert lookup_limits.client_ip(_req(moved)) == "198.51.100.77"
    forged = {**xff, "x-dialogbot-client-ip": "203.0.113.5",
              "x-dialogbot-client-ip-sig": lookup_limits.client_ip_sig("wrong", "203.0.113.5")}
    assert lookup_limits.client_ip(_req(forged)) == "198.51.100.77"


def test_without_the_secret_the_first_forwarded_address_counts():
    """Legacy until CLIENT_IP_SECRET is set on API and web: BFF calls carry only the visitor's address."""
    assert lookup_limits.client_ip(_req({"x-forwarded-for": "203.0.113.5, 198.51.100.77"})) == "203.0.113.5"


def test_rotating_x_forwarded_for_no_longer_escapes_the_lookup_limits(api, pv, ip_secret):
    statuses = [api.c.get(f"{P}/invites/by-code/QQQQ{i:04d}",
                          headers={"x-forwarded-for": f"203.0.113.{i}, 198.51.100.50"}).status_code
                for i in range(lookup_limits.MISSES_PER_MINUTE + 2)]
    assert statuses[:lookup_limits.MISSES_PER_MINUTE] == [404] * lookup_limits.MISSES_PER_MINUTE
    assert statuses[-1] == 429


def test_rotating_x_forwarded_for_no_longer_escapes_the_sms_limit(api, pv, ip_secret):
    mette = pv.account("pump-h@testmail.dk", trial=False)
    a, b = _link(api, mette, _group(api, mette)), _link(api, mette, _group(api, mette, "Venner"))
    statuses = [_join(api, (a, b)[i % 2], f"+4527{i:06d}", f"203.0.113.{i}, 198.51.100.60").status_code
                for i in range(lookup_limits.SMS_PER_IP_HOUR + 1)]
    assert statuses[-1] == 429 and statuses.count(200) == lookup_limits.SMS_PER_IP_HOUR
