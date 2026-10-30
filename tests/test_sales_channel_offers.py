"""Internal sales channel, phase 3: offers and the acceptance page, Peter's call tools, meetings and statistics."""
from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from sqlalchemy import select

from app.models import (
    ActionRun,
    ReceptionAgreement,
    SalesBlockList,
    SalesCompany,
    SalesMeeting,
    SalesMessageRequest,
    SalesOffer,
    Task,
)
from app.modules.billing import prices
from app.modules.billing.statement import statement
from app.modules.sales import offers
from app.worker import runner
from tests.sales_fixtures import SECRET, TEST_NUMBER


def _offer(api, op, company_id, kind="specialist"):
    r = api.post(op, f"/operator/salg/companies/{company_id}/offers", {"setup_kind": kind})
    assert r.status_code == 201, r.text
    return r.json()


def _token_from_mail(db, to_email: str) -> str:
    import re

    from app.models import EmailDelivery

    runner.drain()
    body = db.scalar(select(EmailDelivery.body_text).where(EmailDelivery.to_email == to_email)
                     .order_by(EmailDelivery.created_at.desc()).limit(1))
    return re.search(r"/tilbud/([A-Za-z0-9_\-]+)", body).group(1)


def test_offer_amounts_come_from_the_price_list_and_sent_is_not_accepted(api, ring, db):
    op, company = ring["op"], ring["company"]
    o = _offer(api, op, company.id)
    assert o["status"] == "draft" and o["monthly_net_minor"] == prices.SUBSCRIPTION_MONTHLY_NET_MINOR
    assert o["setup_net_minor"] == prices.SPECIALIST_SETUP_NET_MINOR and o["monthly_vat_minor"] == 62_375
    assert _offer(api, op, company.id, "diy")["setup_net_minor"] == 0
    bad = api.post(op, f"/operator/salg/companies/{company.id}/offers", {"setup_kind": "gratis"})
    assert bad.status_code == 422
    r = api.post(op, f"/operator/salg/offers/{o['id']}/send", {"channel": "email", "destination": "Rene@Example.invalid"})
    assert r.status_code == 200, r.text
    assert r.json()["messages"][0]["status"] == "requested"  # queued, not yet delivered
    runner.drain()
    db.expire_all()
    offer = db.get(SalesOffer, o["id"])
    assert offer.status == "sent" and offer.sent_to == "rene@example.invalid" and offer.accepted_at is None
    req = db.scalar(select(SalesMessageRequest).where(SalesMessageRequest.offer_id == offer.id))
    assert req.status == "sent" and "Simuleret" in (req.error or "")
    token = _token_from_mail(db, "rene@example.invalid")
    view = api.c.get(f"/api/v1/public/offers/{token}").json()
    assert view["status"] == "sent" and view["setup_net_minor"] == 500_000 and view["company"] == "Salon Fiktiv"
    assert api.c.get("/api/v1/public/offers/forkert-token").status_code == 404
    # accepting needs a logged-in, verified user
    assert api.c.post(f"/api/v1/public/offers/{token}/accept", json={"confirm": True}).status_code == 401
    cust = api.user("kunde@testmail.dk")
    r = api.post(cust, f"/public/offers/{token}/accept", {"confirm": False})
    assert r.status_code == 422
    r = api.post(cust, f"/public/offers/{token}/accept", {"confirm": True, "workspace_name": "Salon Fiktiv ApS"})
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["checkout_url"] is None and out["next"] == "/app/konto"  # Stripe not configured in tests
    db.expire_all()
    offer = db.get(SalesOffer, o["id"])
    a = db.get(ReceptionAgreement, offer.agreement_id)
    assert offer.status == "accepted" and str(offer.workspace_id) == out["workspace_id"]
    assert a.setup_net_minor == 500_000 and a.sales_offer_id == offer.id and a.monthly_net_minor == 249_500
    # the setup fee is on the first statement, once
    st = statement(db, a.workspace_id, date.today().replace(day=1), "Europe/Copenhagen")
    assert [x["net_minor"] for x in st["lines"] if x["kind"] == "setup_fee"] == [500_000]
    nxt = (date.today().replace(day=1) + timedelta(days=32)).replace(day=1)
    assert not [x for x in statement(db, a.workspace_id, nxt, "Europe/Copenhagen")["lines"] if x["kind"] == "setup_fee"]
    assert api.post(cust, f"/public/offers/{token}/accept", {"confirm": True}).status_code == 409
    # paying customer only from the first paid invoice
    assert db.get(SalesCompany, company.id).existing_customer_workspace_id is None
    offers.on_invoice_paid(db, a.workspace_id)
    db.commit()
    db.expire_all()
    assert db.get(SalesCompany, company.id).existing_customer_workspace_id == a.workspace_id
    assert db.get(SalesOffer, o["id"]).first_invoice_paid_at is not None


def test_an_expired_or_cancelled_link_cannot_be_accepted(api, ring, db):
    op, company = ring["op"], ring["company"]
    o = _offer(api, op, company.id, "diy")
    api.post(op, f"/operator/salg/offers/{o['id']}/send", {"channel": "email", "destination": "a@example.invalid"})
    runner.drain()
    token = _token_from_mail(db, "a@example.invalid")
    offer = db.get(SalesOffer, o["id"])
    offer.valid_until = datetime.now(UTC) - timedelta(minutes=1)
    db.commit()
    cust = api.user("sen@testmail.dk")
    r = api.post(cust, f"/public/offers/{token}/accept", {"confirm": True})
    assert r.status_code == 409 and r.json()["code"] == "offer_not_open"
    assert api.c.get(f"/api/v1/public/offers/{token}").json()["status"] == "expired"
    o2 = _offer(api, op, company.id, "diy")
    api.post(op, f"/operator/salg/offers/{o2['id']}/send", {"channel": "email", "destination": "b@example.invalid"})
    api.post(op, f"/operator/salg/offers/{o2['id']}/cancel")
    assert api.post(op, f"/operator/salg/offers/{o2['id']}/send",
                    {"channel": "email", "destination": "b@example.invalid"}).status_code == 409


def _tool(client, call_id, name, args):
    r = client.post("/api/v1/webhooks/vapi", headers={"authorization": f"Bearer {SECRET}"}, json={"message": {
        "type": "tool-calls", "call": {"id": call_id, "phoneNumberId": "pn_sales", "customer": {"number": TEST_NUMBER}},
        "toolCallList": [{"id": "tc1", "function": {"name": name, "arguments": args}}]}})
    assert r.status_code == 200, r.text
    return r.json()["results"][0]["result"]


def _test_call(api, ring) -> str:
    r = api.post(ring["op"], "/operator/salg/test-calls", {"company_id": str(ring["company"].id),
                                                           "script_id": str(ring["script"].id), "phone": TEST_NUMBER,
                                                           "accepted_test": True})
    assert r.status_code == 201, r.text
    return r.json()["provider_call_id"]


def test_peters_tools_check_everything_against_the_database(api, ring, db, client):
    call_id = _test_call(api, ring)
    company = db.get(SalesCompany, ring["company"].id)
    assert "2.495" in _tool(client, call_id, "hent_tilbud", {})
    # tools that act need the customer's explicit yes
    assert "udtrykkeligt ja" in _tool(client, call_id, "send_bestillingslink",
                                      {"kanal": "email", "bekraeftet_destination": "x@example.invalid"})
    said = _tool(client, call_id, "opret_ordreudkast", {"setup_kind": "specialist"})
    assert "ikke en ordre" in said and "5.000" in said
    # an address we do not hold is never sent automatically: it waits for an operator, with a task
    said = _tool(client, call_id, "send_bestillingslink", {"kanal": "email", "bekraeftet_destination": "x@example.invalid",
                                                           "bekraeftet": True})
    assert "kollega" in said and "lov ikke" in said
    req = db.scalar(select(SalesMessageRequest).where(SalesMessageRequest.destination == "x@example.invalid"))
    assert req.status == "requested" and req.outbox_event_id is None
    assert db.scalar(select(Task).where(Task.title.contains("x@example.invalid"))) is not None
    # the company's own public e-mail is known: queued and sent
    company.public_email = "info@salon-fiktiv.invalid"
    db.commit()
    said = _tool(client, call_id, "send_bestillingslink", {"kanal": "email", "bekraeftet_destination": "INFO@salon-fiktiv.invalid",
                                                           "bekraeftet": True})
    assert "på vej" in said
    runner.drain()
    db.expire_all()
    sent = db.scalar(select(SalesMessageRequest).where(SalesMessageRequest.destination == "info@salon-fiktiv.invalid"))
    assert sent.status == "sent"
    # the operator can release the waiting one after checking it
    r = api.post(ring["op"], f"/operator/salg/messages/{req.id}/send")
    assert r.status_code == 200, r.text
    # follow-up and opt-out
    assert "to timer" in _tool(client, call_id, "bed_menneske_foelge_op", {"emne": "Kan I koble til Planway?"})
    assert "kontakter ikke" in _tool(client, call_id, "registrer_frabedelse", {"grund": "Ring ikke igen"})
    assert db.scalar(select(SalesBlockList).where(SalesBlockList.value == TEST_NUMBER, SalesBlockList.source == "call"))
    runs = db.scalars(select(ActionRun).where(ActionRun.connector == "dialogbot_sales")).all()
    assert {r.status for r in runs} == {"ok", "refused"} and all(str(r.workspace_id) == ring["ws"] for r in runs)
    # a call that is not an internal sales call never reaches Peter's tools
    assert "ikke tilgængelig" in _tool(client, "an_unknown_call", "registrer_frabedelse", {})


def test_meetings_are_booked_only_on_free_slots_of_the_intro_type(api, ring, db, client):
    op, tok, ws = ring["op"], ring["tok"], ring["ws"]
    call_id = _test_call(api, ring)
    said = _tool(client, call_id, "ledige_moedetider", {})
    assert "bed_menneske_foelge_op" in said  # no intro type yet: no promised times
    week = [{"days": ["mon", "tue", "wed", "thu", "fri", "sat", "sun"], "open": "08:00", "close": "16:00"}]
    it = api.knowledge(tok, ws, "opening_hours", "Åbningstider", {"weekly": week})
    api.submit(tok, ws, it["open_draft"]["id"])
    api.approve(tok, ws, it["open_draft"]["id"])
    api.post(tok, f"/workspaces/{ws}/bookings/types", {"name": "Intro-møde (30 min)", "duration_minutes": 30})
    s = api.get(tok, f"/workspaces/{ws}/bookings/settings").json()
    api.put(tok, f"/workspaces/{ws}/bookings/settings", {"expected_version": s["version"], "enabled": True,
                                                         "lead_time_hours": 0, "horizon_days": 7, "buffer_minutes": 0})
    said = _tool(client, call_id, "ledige_moedetider", {})
    slots = [p.split("slot ")[1].rstrip(")") for p in said.split("; ")]
    assert 1 <= len(slots) <= 2
    assert "ikke ledig" in _tool(client, call_id, "book_moede", {"slot": "2020-01-01T08:00:00+00:00", "navn": "René",
                                                                 "bekraeftet": True})
    said = _tool(client, call_id, "book_moede", {"slot": slots[0], "navn": "René", "email": "rene@example.invalid",
                                                 "bekraeftet": True})
    assert "booket" in said, said
    m = db.scalar(select(SalesMeeting))
    assert m.status == "confirmed" and m.booking_id is not None
    r = api.post(op, f"/operator/salg/meetings/{m.id}", {"status": "cancelled"})
    assert r.status_code == 200 and r.json()["booking"]["status"] == "cancelled"
    detail = api.get(op, f"/operator/salg/companies/{ring['company'].id}").json()
    assert detail["meetings"][0]["status"] == "cancelled"


def test_statistics_leave_out_tests_and_say_what_they_count(api, ring, db):
    op = ring["op"]
    _test_call(api, ring)
    o = _offer(api, op, ring["company"].id, "diy")
    api.post(op, f"/operator/salg/offers/{o['id']}/send", {"channel": "email", "destination": "c@example.invalid"})
    runner.drain()
    r = api.get(op, "/operator/salg/stats")
    assert r.status_code == 200, r.text
    m = {x["key"]: x for x in r.json()["metrics"]}
    assert m["answer_rate"]["denominator"] == 0 and m["answer_rate"]["value"] is None  # test calls never count
    assert m["offers_sent"]["value"] == 1 and m["companies_found"]["value"] >= 1
    assert all(x["definition"] for x in r.json()["metrics"])
    assert m["cost_per_customer"]["value"] is None  # no division by zero
    tiles = api.get(op, "/operator/salg").json()["tiles"]
    assert tiles["offers_open"] == 1
    plain = api.user("almindelig@testmail.dk")
    assert api.get(plain, "/operator/salg/stats").status_code == 403
