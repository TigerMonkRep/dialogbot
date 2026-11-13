"""QA W04, W09, W13 (P0, DB-016): the business's own customers, without a login.

W04: "Code entry, resend cooldown, wrong/expired code, verified and exhausted-attempt state."
W09: "Secure callback cancellation and communication-preference/opt-out views with invalid-link state."
W13: "Secure appointment management, verification where needed, reschedule/cancel, policy restrictions and
      invalid/expired links."
DB-016: "Customer serializers and attachments exclude internal notes; expired/wrong-purpose token denied; OTP retry
         limits enforced."

Against the fake world (simulated SMS and calendar). The chat is switched on without any phone number of the business:
the code SMS goes out with the business's name as sender."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta

import pytest
from sqlalchemy import select
from test_qa_w12_bk15 import _booking_ready, _connect_google, _widget, fake  # noqa: F401 – fake world fixture

from app.models import Booking, CustomerLink, DoNotCall, Lead, PhoneNumber, Task
from app.modules.customer import service as customer
from app.modules.integrations.connectors.fakes import WORLD
from tests.test_leads import chat  # noqa: F401 – fixture
from tests.webchat_phone import last_code, request_code, submit_code, verify_phone

PUB = "/api/v1/public"
E164 = "+4520304050"


def _contact(client, chat, **over):  # noqa: F811
    body = {"name": "Henrik Villumsen", "email": None, "phone": "+45 20 30 40 50", "note": "", "consent": True} | over
    c = chat["conv"]
    return client.post(f"{PUB}/webchat/{chat['key']}/conversations/{c['conversation_id']}/contact", json=body,
                       headers={"origin": "http://localhost:8000", "x-visitor-token": c["visitor_token"]})


def _clock(monkeypatch, delta: timedelta):
    real = customer._now
    monkeypatch.setattr(customer, "_now", lambda: real() + delta)


# --------------------------------------------------------------------------- W04

def test_w04_phone_needs_the_code_resend_cooldown_wrong_code_then_verified(client, chat, db):  # noqa: F811
    assert db.scalar(select(PhoneNumber)) is None  # the chat is live without a phone number of the business
    r = _contact(client, chat)
    assert r.status_code == 422 and r.json()["code"] == "verification_required"
    assert db.scalar(select(Lead)) is None  # nothing stored before the number is proven
    sent = request_code(client, chat["key"], chat["conv"], "20 30 40 50")
    assert sent.status_code == 202, sent.text
    out = sent.json()
    assert out["status"] == "code_sent" and out["phone_display"] == "20 •• •• 50" and out["resend_after"] == 30
    sms = [m for m in WORLD.sms if m["to"] == E164][-1]
    # the business's own text and sender (≤ 11 letters, not a number), Danish by default
    assert not sms["from"].startswith("+") and len(sms["from"]) <= 11
    assert sms["body"].startswith("Din kode er ") and "Dialogbot" not in sms["body"] and sms["body"].endswith("Vh Fjord Gulvservice ApS")
    again = request_code(client, chat["key"], chat["conv"], "20 30 40 50")
    assert again.status_code == 409 and again.json()["code"] == "too_soon" and 1 <= again.json()["retry_after"] <= 30
    code = last_code(E164)
    wrong = submit_code(client, chat["key"], chat["conv"], out["verification_id"], "000000" if code != "000000" else "111111")
    assert wrong.status_code == 422 and wrong.json()["code"] == "code_invalid" and wrong.json()["attempts_left"] == 4
    ok = submit_code(client, chat["key"], chat["conv"], out["verification_id"], code)
    assert ok.status_code == 200 and ok.json() == {"status": "verified", "phone_display": "20 •• •• 50"}
    # the same code cannot be used twice
    assert submit_code(client, chat["key"], chat["conv"], out["verification_id"], code).json()["code"] == "code_expired"
    r = _contact(client, chat)
    assert r.status_code == 200, r.text
    assert r.json()["manage_url"].startswith("http://frontend.test/kunde/")
    lead = db.scalar(select(Lead))
    assert lead.contact_phone == "+45 20 30 40 50" and lead.phone_verified_at is not None


def test_w04_exhausted_attempts_and_expired_code(client, chat, db, monkeypatch):  # noqa: F811
    out = request_code(client, chat["key"], chat["conv"], E164).json()
    code = last_code(E164)
    bad = "000000" if code != "000000" else "111111"
    for left in (4, 3, 2, 1, 0):
        r = submit_code(client, chat["key"], chat["conv"], out["verification_id"], bad)
        assert r.status_code == 422 and r.json()["attempts_left"] == left
    r = submit_code(client, chat["key"], chat["conv"], out["verification_id"], code)  # even the right code now
    assert r.status_code == 409 and r.json()["code"] == "too_many_attempts"
    assert _contact(client, chat).json()["code"] == "verification_required"
    # a new code after the cooldown, but it expires after 10 minutes
    _clock(monkeypatch, timedelta(seconds=31))
    out2 = request_code(client, chat["key"], chat["conv"], E164).json()
    code2 = last_code(E164)
    _clock(monkeypatch, timedelta(minutes=11))
    r = submit_code(client, chat["key"], chat["conv"], out2["verification_id"], code2)
    assert r.status_code == 409 and r.json()["code"] == "code_expired"


def test_w04_code_is_bound_to_its_conversation_and_number(client, chat, db):  # noqa: F811
    out = request_code(client, chat["key"], chat["conv"], E164).json()
    other = client.post(f"{PUB}/webchat/{chat['key']}/conversations", json={"host_origin": "https://www.fjordgulv.example"},
                        headers={"origin": "http://localhost:8000"}).json()
    r = submit_code(client, chat["key"], other, out["verification_id"], last_code(E164))
    assert r.status_code == 409 and r.json()["code"] == "code_expired"  # another visitor cannot use it
    assert submit_code(client, chat["key"], chat["conv"], out["verification_id"], last_code(E164)).status_code == 200
    # verified 20 30 40 50 – a different number on the form still needs its own code
    r = _contact(client, chat, phone="+45 31 32 33 34")
    assert r.status_code == 422 and r.json()["code"] == "verification_required"
    # e-mail only needs no code
    assert _contact(client, chat, phone=None, email="henrik@example.com").status_code == 200


def test_w04_limits_frame_only_and_bad_numbers(client, chat, db, monkeypatch):  # noqa: F811
    c = chat["conv"]
    r = client.post(f"{PUB}/webchat/{chat['key']}/conversations/{c['conversation_id']}/contact/code",
                    json={"phone": E164}, headers={"origin": "https://evil.example", "x-visitor-token": c["visitor_token"]})
    assert r.status_code == 403
    r = client.post(f"{PUB}/webchat/{chat['key']}/conversations/{c['conversation_id']}/contact/code",
                    json={"phone": E164}, headers={"origin": "http://localhost:8000", "x-visitor-token": "forkert"})
    assert r.status_code == 401
    assert request_code(client, chat["key"], c, "+45 90 12 34 56").json()["code"] == "phone_invalid"  # premium rate
    assert request_code(client, chat["key"], c, "123456").json()["code"] == "phone_invalid"
    # per number: the budget shared with every public door (4 an hour)
    for i in range(4):
        _clock(monkeypatch, timedelta(seconds=31 * (i + 1)))
        assert request_code(client, chat["key"], c, E164).status_code == 202
    _clock(monkeypatch, timedelta(seconds=31 * 6))
    r = request_code(client, chat["key"], c, E164)
    assert r.status_code == 429 and r.json()["code"] == "sms_rate_limited"


# --------------------------------------------------------------------------- W09

def _callback_link(client, chat, db, **over):  # noqa: F811
    verify_phone(client, chat["key"], chat["conv"], "+45 20 30 40 50", E164)
    windows = client.get(f"{PUB}/webchat/{chat['key']}/callback-windows").json()["options"]
    r = _contact(client, chat, window=windows[-1]["key"], **over)
    assert r.status_code == 200, r.text
    return r.json()["manage_url"].rsplit("/", 1)[1]


def test_w09_customer_sees_and_cancels_the_call_back(client, api, chat, db):  # noqa: F811
    token = _callback_link(client, chat, db)
    v = client.get(f"{PUB}/customer/callback/{token}")
    assert v.status_code == 200, v.text
    view = v.json()
    # DB-016: only what the customer gave and what was agreed – no notes, tasks, staff, ids
    assert set(view) == {"business", "first_name", "status", "phone_display", "phone_verified", "window", "timezone",
                         "calls_opt_out", "can_opt_out", "expires_at"}
    assert (view["business"], view["first_name"], view["status"], view["phone_display"], view["phone_verified"]) == \
        ("Fjord Gulvservice ApS", "Henrik", "requested", "20 •• •• 50", True)
    assert view["window"]["from"] and view["timezone"] == "Europe/Copenhagen"
    lead = db.scalar(select(Lead))
    assert db.scalar(select(Task).where(Task.lead_id == lead.id)).status == "open"
    r = client.post(f"{PUB}/customer/callback/{token}/cancel")
    assert r.status_code == 200 and r.json()["status"] == "cancelled"
    assert client.post(f"{PUB}/customer/callback/{token}/cancel").json()["status"] == "cancelled"  # idempotent
    db.expire_all()
    lead = db.scalar(select(Lead))
    assert lead.callback_cancelled_at is not None
    assert [t.status for t in db.scalars(select(Task).where(Task.lead_id == lead.id))] == ["done"]
    # staff see it on the lead
    got = api.get(chat["tok_a"], f"/workspaces/{chat['ws_a']}/leads/{lead.id}").json()
    assert got["callback_cancelled_at"] and got["phone_verified_at"]


def test_w09_opt_out_puts_the_number_on_the_do_not_call_list_and_back(client, chat, db):  # noqa: F811
    token = _callback_link(client, chat, db)
    r = client.put(f"{PUB}/customer/callback/{token}/preferences", json={"calls_opt_out": True})
    assert r.status_code == 200 and r.json()["calls_opt_out"] is True
    row = db.scalar(select(DoNotCall))
    assert (row.phone, row.source) == (E164, "customer")
    r = client.put(f"{PUB}/customer/callback/{token}/preferences", json={"calls_opt_out": False})
    assert r.json()["calls_opt_out"] is False and db.scalar(select(DoNotCall)) is None
    # a number staff put on the list stays there
    db.add(DoNotCall(workspace_id=uuid.UUID(chat["ws_a"]), phone=E164, source="manual", reason="Bedt om det i telefonen"))
    db.commit()
    r = client.put(f"{PUB}/customer/callback/{token}/preferences", json={"calls_opt_out": False})
    assert r.json()["calls_opt_out"] is True
    db.expire_all()
    assert db.scalar(select(DoNotCall)).source == "manual"


def test_w09_invalid_replaced_wrong_purpose_and_expired_links(client, chat, db, monkeypatch):  # noqa: F811
    assert client.get(f"{PUB}/customer/callback/{'x' * 43}").json()["code"] == "link_invalid"
    assert client.post(f"{PUB}/customer/callback/nope/cancel").status_code == 404
    first = _callback_link(client, chat, db)
    second = _callback_link_again(client, chat)
    assert client.get(f"{PUB}/customer/callback/{first}").status_code == 404  # replaced by the newer link
    assert client.get(f"{PUB}/customer/callback/{second}").status_code == 200
    # a callback token opens nothing on the booking door (and only an HMAC is stored)
    assert client.get(f"{PUB}/booking/manage/{second}").json()["code"] == "link_invalid"
    assert db.scalar(select(CustomerLink).where(CustomerLink.revoked_at.is_(None))).token_hash != second
    _clock(monkeypatch, timedelta(days=31))
    r = client.get(f"{PUB}/customer/callback/{second}")
    assert r.status_code == 410 and r.json()["code"] == "link_expired"
    assert client.post(f"{PUB}/customer/callback/{second}/cancel").status_code == 410


def _callback_link_again(client, chat):  # noqa: F811
    r = _contact(client, chat)  # same verified number in the same conversation
    assert r.status_code == 200, r.text
    return r.json()["manage_url"].rsplit("/", 1)[1]


def test_w09_new_request_after_cancel_makes_a_new_call_task(client, chat, db):  # noqa: F811
    token = _callback_link(client, chat, db)
    client.post(f"{PUB}/customer/callback/{token}/cancel")
    new = _callback_link_again(client, chat)
    assert client.get(f"{PUB}/customer/callback/{new}").json()["status"] == "requested"
    lead = db.scalar(select(Lead))
    assert sorted(t.status for t in db.scalars(select(Task).where(Task.lead_id == lead.id))) == ["done", "open"]


# --------------------------------------------------------------------------- W13

def _book(api, client, t, *, phone="+4520304050", email=None, slot=0):
    type_id = _booking_ready(api, t)
    key, conv_id, h = _widget(api, client, t)
    opts = client.get(f"{PUB}/webchat/{key}/booking").json()
    r = client.post(f"{PUB}/webchat/{key}/conversations/{conv_id}/booking",
                    json={"type_id": type_id, "start": opts["slots"][slot]["start"], "name": "Henrik Villumsen",
                          "phone": phone, "email": email, "consent": True}, headers=h)
    assert r.status_code == 201, r.text
    assert r.json()["manage_url"].startswith("http://frontend.test/booking/manage/")
    _book.last = {"key": key, "type_id": type_id, "origin": h["origin"]}
    return r.json()["manage_url"].rsplit("/", 1)[1], opts["slots"]


def _session(client, token):
    out = client.post(f"{PUB}/booking/manage/{token}/code").json()
    r = client.post(f"{PUB}/booking/manage/{token}/verify", json={"verification_id": out["verification_id"],
                                                                 "code": last_code(E164)})
    assert r.status_code == 200, r.text
    return r.json()["session"]


def test_w13_view_needs_code_before_move_then_moves_and_cancels(api, client, two_workspaces, fake, db):  # noqa: F811
    t = two_workspaces
    token, slots = _book(api, client, t)
    view = client.get(f"{PUB}/booking/manage/{token}").json()
    assert set(view) == {"business", "what", "first_name", "starts_at", "ends_at", "label", "timezone", "status",
                         "confirmation", "policy", "verification", "expires_at"}
    assert (view["what"], view["status"], view["policy"]["can_change"]) == ("Besigtigelse", "confirmed", True)
    assert view["verification"] == {"required": True, "phone_display": "20 •• •• 50", "verified": False}
    new_start = client.get(f"{PUB}/booking/manage/{token}/slots").json()["slots"][2]["start"]
    r = client.post(f"{PUB}/booking/manage/{token}/move", json={"start": new_start})
    assert r.status_code == 403 and r.json()["code"] == "verification_required"
    r = client.post(f"{PUB}/booking/manage/{token}/move", json={"start": new_start, "session": "gættet"})
    assert r.status_code == 403
    session = _session(client, token)
    r = client.post(f"{PUB}/booking/manage/{token}/move", json={"start": new_start, "session": session})
    assert r.status_code == 200, r.text
    assert r.json()["starts_at"] != view["starts_at"] and r.json()["verification"]["verified"] is True
    db.expire_all()
    b = db.scalar(select(Booking))
    assert b.starts_at == datetime.fromisoformat(new_start)
    titles = [x.title for x in db.scalars(select(Task).where(Task.lead_id == b.lead_id))]
    assert any("flyttede besigtigelse til" in x and "(via link)" in x for x in titles), titles
    booking_task = next(x for x in db.scalars(select(Task).where(Task.lead_id == b.lead_id)) if x.title.startswith("Besigtigelse med"))
    assert booking_task.due_at == b.starts_at  # the booking's own task follows the new time
    # a time that is not free (in the past) → 409
    r = client.post(f"{PUB}/booking/manage/{token}/move", json={"start": "2020-01-01T10:00:00+00:00", "session": session})
    assert r.status_code == 409 and r.json()["code"] == "slot_taken"
    r = client.post(f"{PUB}/booking/manage/{token}/cancel", json={"session": session})
    assert r.status_code == 200 and r.json()["status"] == "cancelled" and r.json()["policy"]["can_change"] is False
    r = client.post(f"{PUB}/booking/manage/{token}/move", json={"start": new_start, "session": session})
    assert r.status_code == 409 and r.json()["code"] == "booking_cancelled"


def test_w13_email_only_booking_needs_no_code(api, client, two_workspaces, fake, db):  # noqa: F811
    token, _ = _book(api, client, two_workspaces, phone=None, email="henrik@example.com")
    view = client.get(f"{PUB}/booking/manage/{token}").json()
    assert view["verification"] == {"required": False, "phone_display": None, "verified": True}
    assert client.post(f"{PUB}/booking/manage/{token}/code").json()["code"] == "verification_not_needed"
    assert client.post(f"{PUB}/booking/manage/{token}/cancel", json={}).json()["status"] == "cancelled"


def test_w13_policy_blocks_changes_inside_the_lead_time(api, client, two_workspaces, fake, db):  # noqa: F811
    t = two_workspaces
    token, _ = _book(api, client, t)
    s = api.get(t["tok_a"], f"/workspaces/{t['ws_a']}/bookings/settings").json()
    api.put(t["tok_a"], f"/workspaces/{t['ws_a']}/bookings/settings", {"enabled": True, "lead_time_hours": 168,
                                                                       "horizon_days": 7, "buffer_minutes": 0,
                                                                       "expected_version": s["version"]})
    view = client.get(f"{PUB}/booking/manage/{token}").json()
    assert view["policy"]["can_change"] is False and view["policy"]["reason"] == "too_late"
    assert view["policy"]["cutoff_hours"] == 168
    session = _session(client, token)
    r = client.post(f"{PUB}/booking/manage/{token}/cancel", json={"session": session})
    assert r.status_code == 409 and r.json()["code"] == "change_too_late"
    assert db.scalar(select(Booking)).status == "confirmed"


def test_w13_invalid_wrong_purpose_other_link_and_expired(api, client, two_workspaces, fake, db, monkeypatch):  # noqa: F811
    t = two_workspaces
    token, _ = _book(api, client, t)
    assert client.get(f"{PUB}/booking/manage/{'y' * 43}").json()["code"] == "link_invalid"
    assert client.get(f"{PUB}/customer/callback/{token}").json()["code"] == "link_invalid"  # wrong purpose
    session = _session(client, token)
    # a second booking's link: the first link's session does not open it
    last = _book.last
    conv2 = client.post(f"{PUB}/webchat/{last['key']}/conversations", json={"host_origin": "https://fjord.dk"},
                        headers={"origin": last["origin"]}).json()
    other_start = client.get(f"{PUB}/webchat/{last['key']}/booking").json()["slots"][5]["start"]
    r = client.post(f"{PUB}/webchat/{last['key']}/conversations/{conv2['conversation_id']}/booking",
                    json={"type_id": last["type_id"], "start": other_start, "name": "Anden", "phone": "+4531323334",
                          "consent": True}, headers={"origin": last["origin"], "x-visitor-token": conv2["visitor_token"]})
    assert r.status_code == 201, r.text
    other = r.json()["manage_url"].rsplit("/", 1)[1]
    r = client.post(f"{PUB}/booking/manage/{other}/cancel", json={"session": session})
    assert r.status_code == 403 and r.json()["code"] == "verification_required"
    # after the appointment the link has expired
    _clock(monkeypatch, timedelta(days=9))
    r = client.get(f"{PUB}/booking/manage/{token}")
    assert r.status_code == 410 and r.json()["code"] == "link_expired"


def test_w13_move_when_the_calendar_write_fails_is_not_told_as_done(api, client, two_workspaces, fake, db, monkeypatch):  # noqa: F811
    """DB-007/DB-011: the customer moves, Google refuses the update → the new time awaits a staff confirmation."""
    t = two_workspaces
    _connect_google(api, client, t)
    token, _ = _book(api, client, t)
    from app.modules.integrations.connectors import fakes
    from app.modules.integrations.connectors.base import ActionError

    def fail_update(self, event_id, *, start, end):
        raise ActionError("calendar: leverandøren svarede ikke (simuleret)", code="provider_unavailable", retryable=True)

    monkeypatch.setattr(fakes.FakeCalendarClient, "update_event", fail_update)
    session = _session(client, token)
    new_start = client.get(f"{PUB}/booking/manage/{token}/slots").json()["slots"][3]["start"]
    r = client.post(f"{PUB}/booking/manage/{token}/move", json={"start": new_start, "session": session})
    assert r.status_code == 200, r.text
    assert r.json()["confirmation"] == "pending"
    db.expire_all()
    b = db.scalar(select(Booking))
    assert b.calendar_sync == "failed"
    assert any(x.title.startswith("Bekræft aftale") for x in db.scalars(select(Task).where(Task.status == "open")))


def _delete_like_google(monkeypatch):
    """The fake calendar's DELETE behaves like Google: a second DELETE of the same event is refused (410 Gone)."""
    from app.modules.integrations.connectors import fakes
    from app.modules.integrations.connectors.base import ActionError

    calls = []

    def delete(self, event_id):
        calls.append(event_id)
        if event_id not in WORLD.events:
            raise ActionError("Kalenderen afviste kaldet (410)", code="provider_rejected")
        WORLD.events.pop(event_id)

    monkeypatch.setattr(fakes.FakeCalendarClient, "delete_event", delete)
    return calls


@pytest.mark.parametrize("who", ["customer", "staff"])
def test_w13_cancel_deletes_the_calendar_event_once(api, client, two_workspaces, fake, db, monkeypatch, who):  # noqa: F811
    """F-VER1113-01: one cancellation → one DELETE; the booking stays synced and the connection is not set to error."""
    from app.models import IntegrationConnection

    t = two_workspaces
    _connect_google(api, client, t)
    token, _ = _book(api, client, t)
    db.expire_all()
    b = db.scalar(select(Booking))
    assert b.calendar_event_id and b.calendar_sync == "synced"
    calls = _delete_like_google(monkeypatch)
    if who == "customer":
        r = client.post(f"{PUB}/booking/manage/{token}/cancel", json={"session": _session(client, token)})
    else:
        r = api.post(t["tok_a"], f"/workspaces/{t['ws_a']}/bookings/{b.id}/cancel", {})
    assert r.status_code == 200, r.text
    db.expire_all()
    b = db.scalar(select(Booking))
    assert calls == [b.calendar_event_id]
    assert (b.status, b.calendar_sync, b.calendar_sync_error) == ("cancelled", "synced", None)
    assert all(c.status != "error" for c in db.scalars(select(IntegrationConnection)))


@pytest.mark.parametrize("status", [404, 410])
def test_calendar_delete_of_an_event_already_gone_is_success(monkeypatch, status):
    """F-VER1113-01: Google answers 410 Gone (Microsoft 404) on an event that is already deleted – that is the
    outcome a DELETE wants, not a provider error."""
    import httpx

    from app.modules.integrations.connectors import calendar

    monkeypatch.setattr(httpx, "request", lambda *a, **kw: httpx.Response(status, json={"error": "gone"}))
    for cls in (calendar.GoogleCalendarClient, calendar.MicrosoftCalendarClient):
        cls("tok").delete_event("ev-1")  # no ActionError


@pytest.mark.parametrize("path", ["/customer/callback/{t}", "/booking/manage/{t}"])
def test_db016_token_length_and_unknown_tokens_are_the_same_404(client, path):
    for tok in ("a", "a" * 43, "a" * 101):
        r = client.get(PUB + path.format(t=tok))
        assert r.status_code == 404 and r.json()["code"] == "link_invalid"
