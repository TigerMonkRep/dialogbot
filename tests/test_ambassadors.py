"""Ambassador programme: sign-up with rules quiz, parent consent for minors, attribution (link/code, no
self-referral), customer discount, commission only on paid invoices (bonus + share, 30-day hold, 12 months),
reversals on refund, payouts with encrypted CPR/bank, B-income CSV, and operator-only administration."""
from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import select

from app.models import Ambassador, CommissionEntry, Invoice, Referral
from app.modules.ambassadors import service
from app.modules.billing import stripe
from app.worker import runner

QUIZ = {q["id"]: q["correct"] for q in service.RULES_QUIZ}


def _born(years: int, extra_days: int = 30) -> str:
    today = date.today()
    return (today.replace(year=today.year - years) - timedelta(days=extra_days)).isoformat()


def _cpr(birth: str, tail: str = "1234") -> str:
    d = date.fromisoformat(birth)
    return d.strftime("%d%m%y") + tail


def _apply(api, tok, **over):
    body = {"kind": "private", "full_name": "Mads Jensen", "birth_date": _born(17), "parent_name": "Lone Jensen",
            "parent_email": "lone@testmail.dk", "headline": "Jeg hjælper min onkels VVS-firma",
            "rules_version": service.RULES_VERSION, "quiz": QUIZ} | over
    return api.c.post("/api/v1/ambassador/apply", json=body, headers=api.h(tok))


def _invoice(db, ws: str, month: date, net: int, sid: str) -> Invoice:
    inv = Invoice(workspace_id=uuid.UUID(ws), month=month, status="open", net_minor=net, tax_minor=net // 4,
                  gross_minor=net + net // 4, lines=[], stripe_invoice_id=sid)
    db.add(inv)
    db.commit()
    return inv


def _pay(db, sid: str):
    assert stripe.process_event(db, {"type": "invoice.paid", "data": {"object": {"id": sid, "status": "paid"}}}) == "applied"
    db.commit()


def _parent_link(api, email="lone@testmail.dk") -> str:
    """The parent's consent link, read from the parent's own (simulated) mailbox."""
    tok = api._parent if getattr(api, "_parent", None) else api.user(email)
    api._parent = tok
    return api.mailbox_link(tok, "vil du godkende", r"foraelder\?token=([A-Za-z0-9_\-]+)")


def _approved_ambassador(api, email="mads@testmail.dk", **over) -> tuple[str, dict]:
    tok = api.user(email)
    r = _apply(api, tok, **over)
    assert r.status_code == 201, r.text
    a = r.json()
    op = api.operator()
    r = api.c.post(f"/api/v1/operator/ambassadors/{a['id']}/approve", json={"note": ""}, headers=api.h(op))
    assert r.status_code == 200 and r.json()["status"] == "active", r.text
    return tok, r.json()


def test_signup_rules_and_validation(api):
    tok = api.user("ung@testmail.dk")
    bad = dict(QUIZ, cold_email="yes")
    r = _apply(api, tok, quiz=bad)
    assert r.status_code == 422 and r.json()["code"] == "rules_quiz_failed"
    assert _apply(api, tok, birth_date=_born(14)).json()["code"] == "too_young"
    r = _apply(api, tok, parent_email=None)
    assert r.status_code == 422
    r = _apply(api, tok, cpr="0101011234")
    assert r.status_code == 422 and "fødselsdato" in r.json()["message"]
    r = _apply(api, tok, kind="company", cvr="123")
    assert r.status_code == 422
    r = _apply(api, tok)
    assert r.status_code == 201, r.text
    me = r.json()
    assert me["status"] == "pending" and me["minor"] is True and me["parent_consent_at"] is None
    assert me["terms"]["bonus_minor"] == 50_000 and me["terms"]["rate_bp"] == 1_000 and me["terms"]["months"] == 12
    assert "En forælder har ikke godkendt aftalen endnu" in me["payout_blockers"]
    assert _apply(api, tok).json()["code"] == "already_ambassador"
    # The parent got an e-mail with a consent link; a pending ambassador has no public page yet.
    link = _parent_link(api)
    assert api.c.get(f"/api/v1/public/ambassadors/{me['slug']}").status_code == 404
    pv = api.c.get(f"/api/v1/public/ambassadors/parent-consent/{link}").json()
    assert pv["ambassador_name"] == "Mads Jensen" and pv["confirmed"] is False
    r = api.c.post("/api/v1/public/ambassadors/parent-consent", json={"token": link, "confirm": True, "parent_name": "Lone"})
    assert r.status_code == 200
    assert api.get(tok, "/ambassador/me").json()["parent_consent_at"] is not None
    # Programme terms are public (without the quiz answers).
    prog = api.c.get("/api/v1/public/ambassadors/program").json()
    assert prog["terms"]["min_age"] == 15 and "correct" not in prog["quiz"][0]


def test_full_flow_attribution_commission_and_payout(api, db, monkeypatch):
    amb_tok, a = _approved_ambassador(api)
    slug, code = a["slug"], a["code"]
    # Public page + visit counter.
    page = api.c.get(f"/api/v1/public/ambassadors/{slug}").json()
    assert page["first_name"] == "Mads" and page["code"] == code and "full_name" not in page
    for _ in range(3):
        assert api.c.post(f"/api/v1/public/ambassadors/{slug}/visit").status_code == 204
    assert api.get(amb_tok, "/ambassador/me").json()["stats"]["clicks_30d"] == 3

    # Self-referral is ignored; a real customer via the link is attributed.
    r = api.c.post("/api/v1/workspaces", json={"name": "Mads' eget firma", "referral_link": slug}, headers=api.h(amb_tok))
    assert r.status_code == 201 and db.get(Referral, uuid.UUID(r.json()["id"])) is None
    cust = api.user("vvs@testmail.dk")
    r = api.c.post("/api/v1/workspaces", json={"name": "Hansen VVS", "referral_link": slug}, headers=api.h(cust))
    ws = r.json()["id"]
    ref = db.get(Referral, uuid.UUID(ws))
    assert ref is not None and ref.via == "link"
    assert api.get(cust, f"/workspaces/{ws}/referral").json()["ambassador_first_name"] == "Mads"

    # The customer's first month is 50 % off.
    month = date(2026, 8, 1)
    from app.modules.billing.statement import statement

    lines = [{"kind": "subscription", "description": "x", "net_minor": 149_500}]
    d = service.discount_line(db, uuid.UUID(ws), month, lines)
    assert d is not None and d["net_minor"] == -74_750
    st = statement(db, uuid.UUID(ws), month, "Europe/Copenhagen")
    assert all(x["kind"] != "ambassador_discount" for x in st["lines"])  # nothing to discount without charges

    # Nothing is earned before payment.
    _invoice(db, ws, month, 74_750, "in_amb_1")
    assert db.scalar(select(CommissionEntry.id)) is None
    _pay(db, "in_amb_1")
    _pay(db, "in_amb_1")  # webhook redelivery is a no-op
    entries = db.scalars(select(CommissionEntry).order_by(CommissionEntry.kind)).all()
    assert [(e.kind, e.amount_minor, e.status) for e in entries] == [("bonus", 50_000, "held"), ("share", 7_475, "held")]
    # After month 2 the discount no longer applies.
    assert service.discount_line(db, uuid.UUID(ws), date(2026, 9, 1), lines) is None
    _invoice(db, ws, date(2026, 9, 1), 149_500, "in_amb_2")
    _pay(db, "in_amb_2")
    assert db.scalar(select(CommissionEntry).where(CommissionEntry.month == date(2026, 9, 1))).amount_minor == 14_950
    db.expire_all()
    me = api.get(amb_tok, "/ambassador/me").json()
    assert me["balances"]["held_minor"] == 72_425 and me["balances"]["payable_minor"] == 0
    assert me["stats"] == {"clicks_30d": 3, "customers": 1, "paying": 1}
    custs = api.get(amb_tok, "/ambassador/me/customers").json()["items"]
    assert custs[0]["company"] == "Hansen VVS" and custs[0]["status"] == "betalende" and custs[0]["share_until"] == "2027-08"
    assert set(custs[0]) == {"workspace_id", "company", "status", "signed_up", "via", "first_paid_month", "share_until",
                             "earned_minor"}

    # 30 days later the entries become payable.
    for e in db.scalars(select(CommissionEntry)):
        e.hold_until = datetime.now(UTC) - timedelta(minutes=1)
    db.commit()
    assert service.release_held(db) == 3
    db.commit()

    op = api.operator()
    # Blocked: no CPR / bank yet (parent has not confirmed either).
    r = api.c.post("/api/v1/operator/ambassadors/payouts", json={}, headers=api.h(op))
    assert r.json()["created"] == [] and "Bankoplysninger mangler" in r.json()["skipped"][0]["reason"]
    link = _parent_link(api)
    api.c.post("/api/v1/public/ambassadors/parent-consent", json={"token": link, "confirm": True})
    me = api.get(amb_tok, "/ambassador/me").json()
    r = api.put(amb_tok, "/ambassador/me", {"cpr": _cpr(me["birth_date"]), "bank_reg": "1234", "bank_account": "0012345678",
                                            "expected_version": me["version"]})
    assert r.status_code == 200 and r.json()["payout_blockers"] == [] and r.json()["bank_last4"] == "5678"
    raw = db.scalar(select(Ambassador)).cpr_enc
    assert _cpr(me["birth_date"]).encode() not in raw  # stored encrypted

    r = api.c.post("/api/v1/operator/ambassadors/payouts", json={}, headers=api.h(op))
    assert r.status_code == 201 and r.json()["created"][0]["amount_minor"] == 72_425
    pid = r.json()["created"][0]["id"]
    assert api.get(amb_tok, "/ambassador/me").json()["balances"]["in_payout_minor"] == 72_425
    rev = api.c.post(f"/api/v1/operator/ambassadors/{a['id']}/reveal", headers=api.h(op)).json()
    assert rev["bank"] == {"reg": "1234", "account": "0012345678"} and rev["cpr"] == _cpr(me["birth_date"])
    r = api.c.post(f"/api/v1/operator/ambassadors/payouts/{pid}/paid", json={"reference": "Bank 2026-10-01"},
                   headers=api.h(op))
    assert r.status_code == 200 and r.json()["status"] == "paid"
    assert api.c.post(f"/api/v1/operator/ambassadors/payouts/{pid}/paid", json={"reference": "x"},
                      headers=api.h(op)).status_code == 409
    bilag = api.get(amb_tok, f"/ambassador/me/payouts/{pid}").json()
    assert bilag["income_type"] == "b_income" and len(bilag["lines"]) == 3 and "B-indkomst" in bilag["tax_note"]
    assert api.get(amb_tok, "/ambassador/me").json()["balances"]["paid_minor"] == 72_425
    runner.drain()

    csv = api.c.get(f"/api/v1/operator/ambassadors/b-income.csv?year={datetime.now(UTC).year}", headers=api.h(op))
    assert csv.status_code == 200 and f"Mads Jensen;{_cpr(me['birth_date'])};724,25;1;B-indkomst" in csv.text

    # A full refund after payout claws back through a negative entry the next payout deducts.
    db.expire_all()  # the payout was marked paid through the API (another session)
    inv1 = db.scalar(select(Invoice).where(Invoice.stripe_invoice_id == "in_amb_1"))
    stripe.process_event(db, {"type": "charge.refunded", "data": {"object": {
        "id": "ch_1", "invoice": "in_amb_1", "amount_refunded": inv1.gross_minor}}})
    db.commit()
    neg = db.scalar(select(CommissionEntry).where(CommissionEntry.kind == "reversal"))
    assert neg.amount_minor == -57_475 and neg.status == "payable"
    stripe.process_event(db, {"type": "charge.refunded", "data": {"object": {
        "id": "ch_1", "invoice": "in_amb_1", "amount_refunded": inv1.gross_minor}}})
    db.commit()
    assert len(db.scalars(select(CommissionEntry).where(CommissionEntry.kind == "reversal")).all()) == 1

    # Newer Stripe API versions leave `invoice` off the charge: the invoice is found via its payment intent.
    calls = []

    def fake_request(method, path, data=None, **_):
        calls.append((method, path, data))
        return {"data": [{"invoice": "in_amb_1"}]}

    monkeypatch.setattr(stripe, "request", fake_request)
    outcome = stripe.process_event(db, {"type": "charge.refunded", "data": {"object": {
        "id": "ch_1", "payment_intent": "pi_1", "amount_refunded": inv1.gross_minor}}})
    db.commit()
    assert outcome == "applied"
    assert calls == [("GET", "/invoice_payments",
                      {"payment": {"type": "payment_intent", "payment_intent": "pi_1"}, "limit": 1})]
    assert len(db.scalars(select(CommissionEntry).where(CommissionEntry.kind == "reversal")).all()) == 1


def test_code_wins_partial_refund_window_and_access(api, db):
    _, a1 = _approved_ambassador(api, "a1@testmail.dk", full_name="Sara Holm")
    _, a2 = _approved_ambassador(api, "a2@testmail.dk", kind="company", full_name="Peter Berg", cvr="12345678",
                                 company_name="Berg Consult", birth_date=None, parent_email=None, parent_name=None)
    assert a2["kind"] == "company" and a2["minor"] is False
    cust = api.user("kunde@testmail.dk")
    r = api.c.post("/api/v1/workspaces", json={"name": "Klinik Nord", "referral_link": a1["slug"],
                                               "referral_code": a2["code"].lower()}, headers=api.h(cust))
    ws = r.json()["id"]
    ref = db.get(Referral, uuid.UUID(ws))
    assert str(ref.ambassador_id) == a2["id"] and ref.via == "code"

    # A partial credit note before payout reduces the share; the bonus stays.
    _invoice(db, ws, date(2026, 1, 1), 100_000, "in_c1")
    _pay(db, "in_c1")
    stripe.process_event(db, {"type": "credit_note.created", "data": {"object": {"id": "cn_1", "invoice": "in_c1",
                                                                                "total": 62_500}}})
    db.commit()
    share = db.scalar(select(CommissionEntry).where(CommissionEntry.kind == "share"))
    bonus = db.scalar(select(CommissionEntry).where(CommissionEntry.kind == "bonus"))
    assert share.amount_minor == 5_000 and bonus.amount_minor == 50_000 and bonus.status == "held"

    # The share stops after 12 months from the first paid month.
    _invoice(db, ws, date(2027, 1, 1), 100_000, "in_c13")
    _pay(db, "in_c13")
    assert db.scalar(select(CommissionEntry).where(CommissionEntry.month == date(2027, 1, 1))) is None
    _invoice(db, ws, date(2026, 12, 1), 100_000, "in_c12")
    _pay(db, "in_c12")
    assert db.scalar(select(CommissionEntry).where(CommissionEntry.month == date(2026, 12, 1))).amount_minor == 10_000

    # Void after payment reverses what is not yet paid out.
    stripe.process_event(db, {"type": "invoice.voided", "data": {"object": {"id": "in_c12", "status": "void"}}})
    db.commit()
    assert db.scalar(select(CommissionEntry).where(CommissionEntry.month == date(2026, 12, 1))).status == "reversed"

    # Only operators administer; an ambassador only sees their own data.
    r = api.c.get("/api/v1/operator/ambassadors", headers=api.h(cust))
    assert r.status_code == 403
    assert api.get(cust, "/ambassador/me").json() == {"enrolled": False}
    assert api.get(cust, "/ambassador/me/ledger").status_code == 404
    op = api.operator()
    lst = api.c.get("/api/v1/operator/ambassadors", headers=api.h(op)).json()
    assert len(lst["items"]) == 2 and lst["totals"]["pending"] == 0
    # Terms can be changed with optimistic locking; referral can be moved (audited).
    det = api.c.get(f"/api/v1/operator/ambassadors/{a2['id']}", headers=api.h(op)).json()
    r = api.c.put(f"/api/v1/operator/ambassadors/{a2['id']}/terms",
                  json={"bonus_minor": 75_000, "rate_bp": 1500, "months": 24, "expected_version": det["version"] - 1},
                  headers=api.h(op))
    assert r.status_code == 409
    r = api.c.put(f"/api/v1/operator/ambassadors/{a2['id']}/terms",
                  json={"bonus_minor": 75_000, "rate_bp": 1500, "months": 24, "expected_version": det["version"]},
                  headers=api.h(op))
    assert r.status_code == 200 and r.json()["terms"]["rate_bp"] == 1500
    r = api.c.put(f"/api/v1/operator/ambassadors/referrals/{ws}", json={"ambassador_id": a1["id"], "reason": "Fejl"},
                  headers=api.h(op))
    assert r.status_code == 200
    db.expire_all()
    assert str(db.get(Referral, uuid.UUID(ws)).ambassador_id) == a1["id"]
    r = api.c.post(f"/api/v1/operator/ambassadors/{a1['id']}/suspend", json={"note": "Spam"}, headers=api.h(op))
    assert r.json()["status"] == "suspended"
    assert api.c.get(f"/api/v1/public/ambassadors/{a1['slug']}").status_code == 404


def test_customer_adds_code_later(api, db):
    amb_tok, a = _approved_ambassador(api)
    cust = api.user("sen@testmail.dk")
    ws = api.workspace(cust, "Frisør Sen")
    r = api.get(cust, f"/workspaces/{ws}/referral").json()
    assert r == {"referred": False, "can_add_code": True}
    assert api.put(cust, f"/workspaces/{ws}/referral", {"code": "FINDESIKKE"}).json()["code"] == "unknown_code"
    r = api.put(cust, f"/workspaces/{ws}/referral", {"code": a["code"]})
    assert r.status_code == 200 and r.json()["referred"] is True
    assert api.put(cust, f"/workspaces/{ws}/referral", {"code": a["code"]}).json()["code"] == "already_referred"
    # The ambassador cannot use their own code.
    own = api.workspace(amb_tok, "Eget")
    assert api.put(amb_tok, f"/workspaces/{own}/referral", {"code": a["code"]}).json()["code"] == "self_referral"
