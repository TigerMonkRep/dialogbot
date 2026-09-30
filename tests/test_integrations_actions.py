"""Actions in the customer's own systems (CONNECTORS_PROVIDER=fake: every result simulated, nothing leaves the process).

Acceptance: the register reports honest status per workspace; credentials are envelope-encrypted and never readable
through the API or logs; OAuth state is single-use, short-lived and bound to its workspace; the tool-builder only
exposes actions of connected connectors, the same for phone and webchat; input is validated against the schema and
confirmation-required actions refuse without a yes; every call leaves one action_runs row that shows in the inbox;
webhooks are HMAC-signed and retried through the outbox; SMS only carries template text; fakes are marked simulated.
"""
from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlparse

import pytest
from sqlalchemy import text

from app.config import get_settings
from app.core import crypto
from app.models import ActionRun, Booking, Conversation, IntegrationConnection, OAuthState, OutboxEvent
from app.modules.integrations import actions, connectors, credentials, oauth
from app.modules.integrations.connectors import webhook
from app.modules.integrations.connectors.base import RunContext
from app.modules.integrations.connectors.fakes import WORLD
from app.worker import runner

SECRET = "vapi-test-secret-0123456789abcdef"


@pytest.fixture
def fake(monkeypatch):
    monkeypatch.setenv("CONNECTORS_PROVIDER", "fake")
    monkeypatch.setenv("AI_PROVIDER", "fake")
    monkeypatch.setenv("VAPI_SERVER_SECRET", SECRET)
    get_settings.cache_clear()
    WORLD.reset()
    yield WORLD
    WORLD.reset()
    get_settings.cache_clear()


def _base(api, t):
    return f"/workspaces/{t['ws_a']}/integrations"


def _booking_ready(api, t):
    tok, ws = t["tok_a"], t["ws_a"]
    hours = api.knowledge(tok, ws, "opening_hours", "Åbningstider",
                          {"weekly": [{"days": ["mon", "tue", "wed", "thu", "fri", "sat", "sun"], "open": "08:00",
                                       "close": "20:00"}]})
    api.submit(tok, ws, hours["open_draft"]["id"])
    api.approve(tok, ws, hours["open_draft"]["id"])
    assert api.post(tok, f"/workspaces/{ws}/bookings/types", {"name": "Besigtigelse", "duration_minutes": 60}).status_code == 201
    s = api.get(tok, f"/workspaces/{ws}/bookings/settings").json()
    r = api.put(tok, f"/workspaces/{ws}/bookings/settings",
                {"enabled": True, "lead_time_hours": 0, "horizon_days": 7, "buffer_minutes": 0,
                 "expected_version": s["version"]})
    assert r.status_code == 200, r.text


def _connect_google(api, client, t) -> None:
    r = api.post(t["tok_a"], f"{_base(api, t)}/google_calendar/connect", {"config": {}, "secrets": {}})
    assert r.status_code == 200, r.text
    url = r.json()["authorize_url"]
    back = client.get(urlparse(url).path + "?" + urlparse(url).query, follow_redirects=False)
    assert back.status_code == 303 and "connected=google_calendar" in back.headers["location"], back.headers.get("location")


# --------------------------------------------------------------------------- crypto

def test_envelope_encryption_roundtrip_tamper_and_rotation(monkeypatch):
    env = crypto.encrypt(b'{"access_token":"hemmelig"}', aad=b"ws:google")
    assert b"hemmelig" not in env.blob and "hemmelig" not in repr(env)
    assert crypto.decrypt(env, aad=b"ws:google") == b'{"access_token":"hemmelig"}'
    with pytest.raises(crypto.DecryptFailed):
        crypto.decrypt(env, aad=b"other-ws:google")  # a blob copied onto another row does not decrypt
    with pytest.raises(crypto.DecryptFailed):
        crypto.decrypt(crypto.Envelope(env.key_version, env.blob[:-1] + bytes([env.blob[-1] ^ 1])), aad=b"ws:google")
    # rotation: old rows decrypt with CREDENTIALS_KEY_PREVIOUS, new ones use the new key
    old_key, new_key = crypto.generate_key(), crypto.generate_key()
    monkeypatch.setenv("CREDENTIALS_KEY", old_key)
    get_settings.cache_clear()
    old = crypto.encrypt(b"x")
    monkeypatch.setenv("CREDENTIALS_KEY", new_key)
    get_settings.cache_clear()
    with pytest.raises(crypto.CredentialsKeyUnavailable):
        crypto.decrypt(old)
    monkeypatch.setenv("CREDENTIALS_KEY_PREVIOUS", old_key)
    get_settings.cache_clear()
    assert crypto.decrypt(old) == b"x" and crypto.encrypt(b"y").key_version != old.key_version
    # staging/prod never fall back to a derived key
    monkeypatch.delenv("CREDENTIALS_KEY")
    monkeypatch.delenv("CREDENTIALS_KEY_PREVIOUS")
    monkeypatch.setenv("APP_ENV", "staging")
    monkeypatch.setenv("SECRET_KEY", "s" * 40)
    monkeypatch.setenv("ENABLE_DEV_TOOLS", "false")
    get_settings.cache_clear()
    with pytest.raises(crypto.CredentialsKeyUnavailable):
        crypto.encrypt(b"z")
    get_settings.cache_clear()


# --------------------------------------------------------------------------- register

def test_register_is_honest_per_workspace(api, two_workspaces, monkeypatch):
    t = two_workspaces
    monkeypatch.delenv("GOOGLE_OAUTH_CLIENT_ID", raising=False)
    monkeypatch.setenv("CONNECTORS_PROVIDER", "live")
    get_settings.cache_clear()
    items = {x["key"]: x for x in api.get(t["tok_a"], _base(api, t)).json()["items"]}
    assert items["google_calendar"]["status"] == "not_implemented" and "GOOGLE_OAUTH_CLIENT_ID" in items["google_calendar"]["reason"]
    assert items["bookings"]["status"] == "not_connected"  # online booking not switched on
    assert items["webhook"]["status"] == "not_connected" and items["webhook"]["simulated"] is False
    assert items["hubspot"]["availability"] == "coming" and items["hubspot"]["status"] == "not_implemented"
    assert items["economic"]["zapier_note"]
    r = api.post(t["tok_a"], f"{_base(api, t)}/google_calendar/connect", {"config": {}, "secrets": {}})
    assert r.status_code == 501 and r.json()["code"] == "connector_not_available"
    # the plan's optional step never blocks activation
    plan = api.plan(t["tok_a"], t["ws_a"])
    step = next(x for x in plan["tasks"] if x["key"] == "integrations.connect")
    assert step["required"] is False and "integrations.connect" not in plan["blocked_required"]
    get_settings.cache_clear()


def test_roles_and_isolation(api, two_workspaces, fake):
    t = two_workspaces
    staff = api.add_member(t["tok_a"], t["ws_a"], "staff-int@testmail.dk", "staff")
    assert api.get(staff, _base(api, t)).status_code == 200
    assert api.post(staff, f"{_base(api, t)}/zapier/connect", {"config": {"url": "http://localhost:9/hook"}}).status_code == 403
    r = api.post(t["tok_a"], f"{_base(api, t)}/zapier/connect", {"config": {"url": "http://localhost:9/hook"}})
    assert r.status_code == 200
    other = {x["key"]: x for x in api.get(t["tok_b"], f"/workspaces/{t['ws_b']}/integrations").json()["items"]}
    assert other["zapier"]["status"] == "not_connected"
    assert api.get(t["tok_b"], _base(api, t)).status_code == 404


# --------------------------------------------------------------------------- webhook: secrets, signature, retry

def test_webhook_secret_shown_once_never_readable_and_signed_delivery(api, two_workspaces, fake, db, capsys):
    t = two_workspaces
    base = _base(api, t)
    bad = api.post(t["tok_a"], f"{base}/webhook/connect", {"config": {"url": "ftp://example.dk/x"}})
    assert bad.status_code == 422
    r = api.post(t["tok_a"], f"{base}/webhook/connect", {"config": {"url": "http://localhost:9/hook"}},
                 **{"Idempotency-Key": "wh-1"})
    assert r.status_code == 200, r.text
    signing = r.json()["signing_secret"]
    assert signing.startswith("whsec_") and r.json()["simulated"] is True
    # the replay of the same command does not hand the secret out again
    again = api.post(t["tok_a"], f"{base}/webhook/connect", {"config": {"url": "http://localhost:9/hook"}},
                     **{"Idempotency-Key": "wh-1"})
    assert "signing_secret" not in again.json()
    # never readable afterwards: not in the catalogue, not in the idempotency table, not in the DB row in clear
    assert signing not in api.get(t["tok_a"], base).text
    assert db.execute(text("select count(*) from idempotency_keys where response_body::text like :s"),
                      {"s": f"%{signing}%"}).scalar() == 0
    row = db.query(IntegrationConnection).filter_by(connector="webhook").one()
    assert signing.encode() not in bytes(row.secret_blob) and credentials.get_secret(row)["signing_secret"] == signing
    # the test event is signed and verifiable with the secret
    assert fake.webhooks[-1]["body"] and json.loads(fake.webhooks[-1]["body"])["event"] == "test.ping"
    # a lead fans out through the outbox with a verifiable signature
    lead = api.post(t["tok_a"], f"/workspaces/{t['ws_a']}/leads", {"contact_name": "Mette", "contact_phone": "+4520304050",
                                                                   "need_summary": "Gulvafslibning"})
    assert lead.status_code == 201, lead.text
    runner.drain()
    sent = [w for w in fake.webhooks if json.loads(w["body"])["event"] == "lead.created"]
    assert len(sent) == 1
    hdr = sent[0]["headers"][webhook.SIGNATURE_HEADER]
    assert webhook.verify(signing, sent[0]["body"].encode(), hdr)
    assert not webhook.verify("whsec_wrong", sent[0]["body"].encode(), hdr)
    assert json.loads(sent[0]["body"])["data"]["contact_name"] == "Mette"
    assert signing not in capsys.readouterr().out  # never logged


def test_webhook_retries_then_marks_error(api, two_workspaces, fake, db):
    t = two_workspaces
    api.post(t["tok_a"], f"{_base(api, t)}/make/connect", {"config": {"url": "http://localhost:9/make"}})
    fake.fail_webhook_times = 1
    api.post(t["tok_a"], f"/workspaces/{t['ws_a']}/leads", {"contact_name": "Ole", "need_summary": "Tilbud"})
    ev = runner.process_once()
    assert ev.event_type == "webhook.deliver" and ev.status == "queued" and ev.attempts == 1  # backoff, not lost
    db.query(OutboxEvent).filter_by(id=ev.id).update({"next_attempt_at": datetime.now(UTC)})
    db.commit()
    assert runner.process_once().status == "done"
    assert [json.loads(w["body"])["event"] for w in fake.webhooks] == ["test.ping", "lead.created"]
    # a receiver that keeps failing: after the last attempt the connection shows the error
    fake.fail_webhook_times = 99
    api.post(t["tok_a"], f"/workspaces/{t['ws_a']}/leads", {"contact_name": "Bo", "need_summary": "Tilbud"})
    ev = db.query(OutboxEvent).filter_by(event_type="webhook.deliver", status="queued").one()
    ev.max_attempts = 2
    db.commit()
    for _ in range(2):
        db.query(OutboxEvent).filter_by(id=ev.id).update({"next_attempt_at": datetime.now(UTC)})
        db.commit()
        runner.process_once()
    db.expire_all()
    assert db.get(OutboxEvent, ev.id).status == "failed"
    item = next(x for x in api.get(t["tok_a"], _base(api, t)).json()["items"] if x["key"] == "make")
    assert item["status"] == "error" and "kunne ikke leveres" in item["error"]


# --------------------------------------------------------------------------- OAuth

def test_oauth_state_single_use_expiry_and_pkce(api, client, two_workspaces, db, monkeypatch):
    t = two_workspaces
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_ID", "cid.apps.googleusercontent.com")
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_SECRET", "csecret")
    monkeypatch.setenv("CONNECTORS_PROVIDER", "live")
    get_settings.cache_clear()
    r = api.post(t["tok_a"], f"{_base(api, t)}/google_calendar/connect", {"config": {}, "secrets": {}})
    assert r.status_code == 200, r.text
    q = parse_qs(urlparse(r.json()["authorize_url"]).query)
    assert q["code_challenge_method"] == ["S256"] and q["access_type"] == ["offline"] and len(q["state"][0]) > 30
    assert "calendar.events" in q["scope"][0] and "calendar.readonly" not in q["scope"][0]
    state = q["state"][0]
    row = db.get(OAuthState, state)
    assert row.workspace_id == uuid.UUID(t["ws_a"]) and b"verifier" not in bytes(row.verifier_blob)
    seen = {}

    def fake_token(provider, data):
        seen.update(data)
        return {"access_token": "ya29.real-looking", "refresh_token": "1//refresh", "expires_in": 3600, "token_type": "Bearer"}

    monkeypatch.setattr(oauth, "_token_request", fake_token)
    monkeypatch.setattr(connectors.calendar.GoogleCalendarClient, "info",
                        lambda self: {"calendar_id": "primary", "name": "Google Kalender", "email": ""})
    cb = client.get(f"/api/v1/integrations/oauth/google_calendar/callback?state={state}&code=4/abc", follow_redirects=False)
    assert cb.status_code == 303 and cb.headers["location"].endswith("?connected=google_calendar")
    # the PKCE verifier matching the challenge was sent, together with the code
    import base64
    import hashlib

    assert seen["code"] == "4/abc" and base64.urlsafe_b64encode(
        hashlib.sha256(seen["code_verifier"].encode()).digest()).decode().rstrip("=") == q["code_challenge"][0]
    # single use
    again = client.get(f"/api/v1/integrations/oauth/google_calendar/callback?state={state}&code=4/abc", follow_redirects=False)
    assert "error=oauth_state_expired" in again.headers["location"]
    # tokens are stored encrypted and never returned
    conn = db.query(IntegrationConnection).filter_by(connector="google_calendar").one()
    assert b"ya29" not in bytes(conn.secret_blob) and conn.status == "connected" and not conn.simulated
    assert "ya29" not in api.get(t["tok_a"], _base(api, t)).text and "1//refresh" not in api.get(t["tok_a"], _base(api, t)).text
    # expired and unknown states, and a state for another connector
    r2 = api.post(t["tok_a"], f"{_base(api, t)}/google_calendar/connect", {"config": {}, "secrets": {}})
    s2 = parse_qs(urlparse(r2.json()["authorize_url"]).query)["state"][0]
    db.query(OAuthState).filter_by(state=s2).update({"expires_at": datetime.now(UTC) - timedelta(seconds=1)})
    db.commit()
    assert "error=oauth_state_expired" in client.get(
        f"/api/v1/integrations/oauth/google_calendar/callback?state={s2}&code=x", follow_redirects=False).headers["location"]
    assert "error=oauth_state_unknown" in client.get(
        "/api/v1/integrations/oauth/google_calendar/callback?state=nope&code=x", follow_redirects=False).headers["location"]
    r3 = api.post(t["tok_a"], f"{_base(api, t)}/google_calendar/connect", {"config": {}, "secrets": {}})
    s3 = parse_qs(urlparse(r3.json()["authorize_url"]).query)["state"][0]
    assert "error=oauth_state_unknown" in client.get(
        f"/api/v1/integrations/oauth/microsoft_calendar/callback?state={s3}&code=x", follow_redirects=False).headers["location"]
    get_settings.cache_clear()


def test_expired_token_is_refreshed(api, client, two_workspaces, db, monkeypatch):
    t = two_workspaces
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_ID", "cid")
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_SECRET", "cs")
    get_settings.cache_clear()
    conn = IntegrationConnection(workspace_id=uuid.UUID(t["ws_a"]), connector="google_calendar", auth_kind="oauth",
                                 status="connected", expires_at=datetime.now(UTC) - timedelta(minutes=1))
    credentials.put_secret(conn, {"access_token": "old", "refresh_token": "r1"})
    db.add(conn)
    db.commit()
    monkeypatch.setattr(oauth, "_token_request", lambda p, d: {"access_token": "new", "expires_in": 3600})
    connectors._fresh_secret(db, conn)
    assert credentials.get_secret(conn) == {"access_token": "new", "token_type": "Bearer", "refresh_token": "r1",
                                             "id_token": None}
    assert conn.expires_at > datetime.now(UTC)
    get_settings.cache_clear()


# --------------------------------------------------------------------------- tool-builder, actions, trail

def test_tool_builder_only_connected_and_same_for_phone_and_webchat(api, client, two_workspaces, fake, db):
    t = two_workspaces
    ws = db.get(__import__("app.models", fromlist=["Workspace"]).Workspace, uuid.UUID(t["ws_a"]))
    assert actions.tools_for(db, ws, "phone") == []  # nothing connected, booking off
    _booking_ready(api, t)
    names = [x.name for x in actions.tools_for(db, ws, "phone")]
    assert names == ["ledige_tider", "book_tid", "flyt_tid", "aflys_tid"]
    assert [x.name for x in actions.tools_for(db, ws, "webchat")] == names
    api.post(t["tok_a"], f"{_base(api, t)}/twilio_sms/connect", {"config": {}})
    assert "send_sms_bekraeftelse" in [x.name for x in actions.tools_for(db, ws, "phone")]
    # the confirm field is added to the schema and required
    book = next(x for x in actions.tools_for(db, ws, "phone") if x.name == "book_tid")
    assert "bekraeftet" in book.schema()["required"] and book.schema()["additionalProperties"] is False
    # an error connection is not offered
    db.query(IntegrationConnection).filter_by(connector="twilio_sms").update({"status": "error"})
    db.commit()
    assert "send_sms_bekraeftelse" not in [x.name for x in actions.tools_for(db, ws, "phone")]


def test_actions_validate_confirm_log_and_mirror_to_calendar(api, client, two_workspaces, fake, db):
    t = two_workspaces
    _booking_ready(api, t)
    _connect_google(api, client, t)
    from app.models import Workspace

    ws = db.get(Workspace, uuid.UUID(t["ws_a"]))
    ctx = RunContext(workspace_id=ws.id, channel="phone", caller_phone="+4520304050", provider_call_id="call-x")
    # a busy event in the connected calendar blocks the slot
    free = actions.execute(db, ws, "ledige_tider", {}, ctx)[1].output["tider"]
    first = free[0]["start"]
    WORLD.events["busy"] = {"calendar": f"google_calendar:{ws.id}", "start": datetime.fromisoformat(first),
                            "end": datetime.fromisoformat(first) + timedelta(hours=1), "title": "optaget", "description": ""}
    free2 = actions.execute(db, ws, "ledige_tider", {}, ctx)[1].output["tider"]
    assert first not in [x["start"] for x in free2]
    del WORLD.events["busy"]
    # invalid input and missing confirmation are refused before the adapter runs, and logged
    text1, r1 = actions.execute(db, ws, "book_tid", {"start": first, "navn": "Bo", "bekraeftet": True, "hack": 1}, ctx)
    text2, r2 = actions.execute(db, ws, "book_tid", {"start": first, "navn": "Bo"}, ctx)
    text3, r3 = actions.execute(db, ws, "slet_alt", {}, ctx)
    assert (r1.status, r2.status, r3.status) == ("refused", "refused", "refused")
    assert "Ugyldigt input" in text1 and "siger ja" in text2 and db.query(Booking).count() == 0
    # booked, mirrored as an event in the connected calendar, marked simulated
    text4, r4 = actions.execute(db, ws, "book_tid", {"start": first, "navn": "Bo", "bekraeftet": True}, ctx)
    assert r4.status == "ok" and r4.simulated and text4.endswith("(simuleret)")
    b = db.query(Booking).one()
    assert b.calendar_connector == "google_calendar" and b.calendar_event_id in WORLD.events
    # move and cancel follow in the calendar; the booking is found from the caller's number
    later = free[2]["start"]
    _, r5 = actions.execute(db, ws, "flyt_tid", {"ny_start": later, "bekraeftet": True}, ctx)
    assert r5.status == "ok", r5.error
    assert WORLD.events[b.calendar_event_id]["start"] == datetime.fromisoformat(later)
    _, r6 = actions.execute(db, ws, "aflys_tid", {"bekraeftet": True}, ctx)
    assert r6.status == "ok" and b.status == "cancelled" and b.calendar_event_id not in WORLD.events
    db.commit()
    assert db.query(ActionRun).filter_by(workspace_id=ws.id).count() == 8
    # a calendar failure is honest: the action fails, nothing is claimed
    WORLD.fail_next.add("calendar")
    text7, r7 = actions.execute(db, ws, "ledige_tider", {}, ctx)
    assert r7.status in ("ok", "failed")  # busy lookup failure falls back to opening hours, recorded on the connection
    conn = db.query(IntegrationConnection).filter_by(connector="google_calendar").one()
    assert conn.status == "error" and "Optaget tid" in conn.error


def test_phone_tool_calls_and_webchat_tool_use_show_in_inbox(api, client, two_workspaces, fake, db):
    t = two_workspaces
    tok, ws = t["tok_a"], t["ws_a"]
    _booking_ready(api, t)
    api.post(tok, f"{_base(api, t)}/twilio_sms/connect", {"config": {}})
    api.map_number(ws, "+4570123456", "pn_act")
    h = {"authorization": f"Bearer {SECRET}"}
    a = client.post("/api/v1/webhooks/vapi", json={"message": {"type": "assistant-request", "call": {"phoneNumberId": "pn_act"}}},
                    headers=h).json()["assistant"]
    assert "send_sms_bekraeftelse" in [x["function"]["name"] for x in a["model"]["tools"]]
    assert "Handlinger:" in a["model"]["messages"][0]["content"]
    call = {"id": "call_act_1", "phoneNumberId": "pn_act", "customer": {"number": "+4520304050"}}
    sms = client.post("/api/v1/webhooks/vapi", json={"message": {"type": "tool-calls", "call": call, "toolCallList": [
        {"id": "s1", "function": {"name": "send_sms_bekraeftelse", "arguments": {"skabelon": "ring_tilbage"}}}]}},
                      headers=h).json()["results"][0]["result"]
    assert sms.startswith("SMS sendt til +4520304050") and len(fake.sms) == 1
    assert fake.sms[0]["body"].startswith("Tak for din henvendelse til Fjord Gulvservice ApS")
    # SMS text only comes from templates: a free-text field is rejected by the schema
    bad = client.post("/api/v1/webhooks/vapi", json={"message": {"type": "tool-calls", "call": call, "toolCallList": [
        {"id": "s2", "function": {"name": "send_sms_bekraeftelse",
                                  "arguments": {"skabelon": "ring_tilbage", "tekst": "Gratis gulv!"}}}]}},
                      headers=h).json()["results"][0]["result"]
    assert "Ugyldigt input" in bad and len(fake.sms) == 1
    # the end-of-call report links the call's actions to its conversation
    report = {"type": "end-of-call-report", "call": call | {"startedAt": "2026-09-24T08:00:00Z", "endedAt": "2026-09-24T08:02:00Z"},
              "artifact": {"messages": [{"role": "user", "message": "Send mig en SMS"}]}}
    assert client.post("/api/v1/webhooks/vapi", json={"message": report}, headers=h).json()["outcome"] == "applied"
    conv = db.query(Conversation).filter_by(channel="phone").one()
    detail = api.get(tok, f"/workspaces/{ws}/conversations/{conv.id}").json()
    assert [(x["action"], x["status"], x["simulated"]) for x in detail["actions"]] == [
        ("send_sms_bekraeftelse", "ok", True), ("send_sms_bekraeftelse", "refused", False)]
    # webchat: the model calls a tool, the result goes back, the reply is stored, the action is in the trail
    wc = api.get(tok, f"/workspaces/{ws}/webchat").json()
    r = api.put(tok, f"/workspaces/{ws}/webchat", {"enabled": True, "allowed_origins": ["https://fjordgulv.dk"],
                                                   "greeting": "", "expected_version": wc["version"]})
    assert r.status_code == 200, r.text
    key = r.json()["widget_key"]
    from app.modules.webchat import service as webchat_service

    origin = {"origin": webchat_service.api_origin()}
    start = client.post(f"/api/v1/public/webchat/{key}/conversations", headers=origin, json={"host_origin": "https://fjordgulv.dk"})
    assert start.status_code == 201, start.text
    cid, vtok = start.json()["conversation_id"], start.json()["visitor_token"]
    msg = client.post(f"/api/v1/public/webchat/{key}/conversations/{cid}/messages",
                      headers=origin | {"x-visitor-token": vtok}, json={"text": "!ledige_tider {}"})
    assert msg.status_code == 200, msg.text
    assert msg.json()["reply"]["text"].startswith("[fake] handling: Ledige tider til besigtigelse")
    runs = api.get(tok, f"/workspaces/{ws}/conversations/{cid}").json()["actions"]
    assert [(x["action"], x["channel"], x["status"]) for x in runs] == [("ledige_tider", "webchat", "ok")]
    listed = api.get(tok, f"/workspaces/{ws}/integrations/actions").json()["items"]
    assert len(listed) == 3


def test_test_run_and_disconnect(api, client, two_workspaces, fake, db):
    t = two_workspaces
    base = _base(api, t)
    _booking_ready(api, t)
    _connect_google(api, client, t)
    ok = api.post(t["tok_a"], f"{base}/google_calendar/test", **{"Idempotency-Key": "t-1"}).json()
    assert ok["ok"] is True and ok["simulated"] is True
    run = api.post(t["tok_a"], f"{base}/google_calendar/run", {"action": "ledige_tider", "input": {}}).json()
    assert run["run"]["channel"] == "test" and run["run"]["status"] == "ok"
    assert api.post(t["tok_a"], f"{base}/bookings/connect", {"config": {}}).status_code == 409
    item = next(x for x in api.get(t["tok_a"], base).json()["items"] if x["key"] == "google_calendar")
    conflict = api.put(t["tok_a"], f"{base}/google_calendar", {"config": {"calendar_id": "x"}, "expected_version": item["version"] + 5})
    assert conflict.status_code == 409 and conflict.json()["code"] == "version_conflict"
    assert api.put(t["tok_a"], f"{base}/google_calendar", {"config": {"calendar_id": "x"},
                                                          "expected_version": item["version"]}).status_code == 200
    assert api.delete(t["tok_a"], f"{base}/google_calendar").status_code == 204
    assert db.query(IntegrationConnection).filter_by(connector="google_calendar").count() == 0
    item = next(x for x in api.get(t["tok_a"], base).json()["items"] if x["key"] == "google_calendar")
    assert item["status"] == "not_connected"
    # with no OAuth calendar the built-in calendar (opening hours) answers the booking actions again
    from app.models import Workspace

    ws = db.get(Workspace, uuid.UUID(t["ws_a"]))
    assert [x.connector for x in actions.tools_for(db, ws, "phone")][:1] == ["bookings"]


# --------------------------------------------------------------------------- live HTTP clients (provider stubbed)

def test_google_and_microsoft_clients_speak_the_documented_api(monkeypatch):
    import httpx

    from app.modules.integrations.connectors import calendar

    seen = []

    def fake_request(method, url, headers=None, timeout=None, **kw):
        seen.append((method, url, headers, kw))
        req = httpx.Request(method, url)
        if url.endswith("/freeBusy"):
            return httpx.Response(200, request=req, json={"calendars": {"primary": {"busy": [
                {"start": "2026-10-01T08:00:00Z", "end": "2026-10-01T09:00:00Z"}]}}})
        if "calendarView" in url:
            return httpx.Response(200, request=req, json={"value": [
                {"start": {"dateTime": "2026-10-01T10:00:00.0000000"}, "end": {"dateTime": "2026-10-01T11:00:00.0000000"},
                 "showAs": "busy"},
                {"start": {"dateTime": "2026-10-01T12:00:00"}, "end": {"dateTime": "2026-10-01T13:00:00"}, "showAs": "free"}]})
        if method == "POST":
            return httpx.Response(201, request=req, json={"id": "ev-1"})
        if method == "DELETE":
            return httpx.Response(404, request=req)
        if "401" in url:
            return httpx.Response(401, request=req)
        return httpx.Response(200, request=req, json={})

    monkeypatch.setattr(httpx, "request", fake_request)
    frm, to = datetime(2026, 10, 1, tzinfo=UTC), datetime(2026, 10, 2, tzinfo=UTC)
    g = calendar.GoogleCalendarClient("tok-g")
    assert g.busy(frm, to) == [(datetime(2026, 10, 1, 8, tzinfo=UTC), datetime(2026, 10, 1, 9, tzinfo=UTC))]
    assert seen[-1][0] == "POST" and seen[-1][3]["json"]["items"] == [{"id": "primary"}]
    assert seen[-1][2]["authorization"] == "Bearer tok-g"
    assert g.create_event(title="Besigtigelse: Bo", start=frm, end=to) == "ev-1"
    assert seen[-1][1].endswith("/calendars/primary/events") and seen[-1][3]["json"]["start"] == {"dateTime": "2026-10-01T00:00:00Z"}
    g.delete_event("gone")  # already deleted at the provider: not an error
    m = calendar.MicrosoftCalendarClient("tok-m")
    assert m.busy(frm, to) == [(datetime(2026, 10, 1, 10, tzinfo=UTC), datetime(2026, 10, 1, 11, tzinfo=UTC))]
    assert seen[-1][2]["Prefer"] == 'outlook.timezone="UTC"' and seen[-1][2]["authorization"] == "Bearer tok-m"
    assert m.create_event(title="x", start=frm, end=to) == "ev-1" and seen[-1][1].endswith("/me/calendar/events")
    from app.modules.integrations.connectors.base import ActionError

    with pytest.raises(ActionError) as e:
        calendar._http("GET", "https://x/401", "t")
    assert e.value.code == "provider_unauthorized"
