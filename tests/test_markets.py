"""Markets: price tables per currency, VAT rules by country, the workspace's currency (locked by the agreement), customer
campaigns priced in it, statements and Stripe invoices in it with the right VAT (manual rules or Stripe Tax), the VAT
number endpoint and the 409 for an EU company without one."""
from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta

import pytest

from app.config import get_settings
from app.core.errors import ValidationFailed
from app.models import BillingAccount, BusinessProfile, Campaign, CampaignCall, CampaignContact, ReceptionAgreement
from app.modules.billing import customer_market, markets, prices
from app.modules.billing import stripe as stripe_api

# --------------------------------------------------------------------------- the tables


def test_every_currency_has_every_price_and_yearly_is_twelve_months():
    assert markets.CURRENCIES == ("DKK", "SEK", "NOK", "EUR", "USD")
    for cur in markets.CURRENCIES:
        # no per-call price (2026-11-10): the package (same everywhere) and the minute above it per direction
        assert set(markets.ERHVERV[cur]) == {"monthly", "extra_minute", "outbound_extra_minute", "call_answered",
                                             "call_voicemail", "call_no_answer", "setup"}
        e = markets.ERHVERV[cur]
        assert e["call_answered"] > e["call_voicemail"] > e["call_no_answer"] > 0  # after the package, by outcome
        assert all(isinstance(v, int) and v > 0 for v in markets.ERHVERV[cur].values())
        assert set(markets.PRIVAT[cur]) == {"basis", "plus", "familie"}
        for plan, p in markets.PRIVAT[cur].items():
            assert p["yearly_total"] == 12 * p["yearly_monthly"], (cur, plan)
            assert p["yearly_monthly"] < p["monthly"]
        assert set(markets.PRIVAT_EXTRA_CALL[cur]) == {"answered", "voicemail", "no_answer", "minute", "max"}
        assert len(markets.PRIVAT_TOPUPS[cur]) == 3 and all(a > 0 and a % 100 == 0 for a in markets.PRIVAT_TOPUPS[cur])
    assert markets.ERHVERV["DKK"]["monthly"] == prices.SUBSCRIPTION_MONTHLY_NET_MINOR == 249_500
    assert markets.PRIVAT["DKK"]["plus"]["monthly"] == 9900 and markets.PRIVAT_TOPUPS["DKK"] == (5000, 10000, 20000)
    assert markets.currency_for_country("se") == "SEK" and markets.currency_for_country("DE") == "EUR"
    assert markets.currency_for_country(None) == "DKK" and markets.currency_for_locale("no") == "NOK"
    assert (markets.fmt(249_500, "DKK"), markets.fmt(55, "EUR"), markets.fmt(32_900, "EUR")) == (
        "2.495 kr.", "€0.55", "€329")


def test_erhverv_vat_rules():
    assert markets.erhverv_vat("DK", None) == markets.Vat(2500, "domestic", "DK")
    se = markets.erhverv_vat("SE", "SE556677889901")
    assert (se.rate_bp, se.kind, se.note) == (0, "reverse_charge", markets.REVERSE_CHARGE_NOTE)
    assert markets.erhverv_vat("DE", "DE123456789").kind == "reverse_charge"
    with pytest.raises(markets.VatNumberRequired):
        markets.erhverv_vat("DE", "")
    assert markets.erhverv_vat("NO", None).kind == "outside_eu" and markets.erhverv_vat("US", None).rate_bp == 0
    assert customer_market.vat_out("DE", None)["kind"] == "vat_number_required"


def test_privat_vat_rules_in_both_modes():
    assert markets.privat_vat("DK") == markets.Vat(2500, "domestic", "DK")
    assert markets.privat_vat("DE") == markets.Vat(2500, "domestic", "DK")  # danish mode: Danish VAT for the EU
    assert markets.privat_vat("DE", eu_mode="destination") == markets.Vat(1900, "destination", "DE")
    assert markets.privat_vat("DK", eu_mode="destination").rate_bp == 2500
    assert markets.privat_vat("NO").rate_bp == 0
    assert markets.privat_vat("NO", voec_registered=True) == markets.Vat(2500, "destination", "NO")
    assert markets.privat_vat("US", eu_mode="destination").rate_bp == 0
    assert [v.country for v in markets.privat_checkout_rates()] == ["DK"]
    assert len(markets.privat_checkout_rates(eu_mode="destination", voec_registered=True)) == 28


def test_vat_number_normalisation():
    n = customer_market.normalize_vat_number
    assert n(" se 5566.7788-9901 ", "SE") == "SE556677889901"
    assert n("123456789", "DE") == "DE123456789"  # the prefix is added
    assert n("el123456789", "GR") == "EL123456789"
    assert n("NO 123 456 789 MVA", "NO") == "123456789MVA" and n("123456789", "NO") == "123456789MVA"
    assert n("", "SE") is None and n("  ", "DE") is None
    with pytest.raises(ValidationFailed) as e:
        n("DE123456789", "SE")
    assert e.value.code == "vat_number_country_mismatch"
    for bad in ("SE1", "SE!!!!!!!", "SEABCDEFGH"):
        with pytest.raises(ValidationFailed):
            n(bad, "SE")
    with pytest.raises(ValidationFailed):
        n("12345", "NO")


# --------------------------------------------------------------------------- workspace currency


def _country(db, ws, country, **address):
    p = db.get(BusinessProfile, uuid.UUID(ws))
    p.country = country
    for k, v in address.items():
        setattr(p, k, v)
    db.commit()


def test_agreement_takes_the_countrys_currency_and_keeps_it(api, two_workspaces, db):
    tok, ws = two_workspaces["tok_a"], two_workspaces["ws_a"]
    _country(db, ws, "SE")
    a = api.post(tok, f"/workspaces/{ws}/agreement", {"model": "A"}).json()
    assert a["currency"] == "SEK" and a["monthly"]["net_minor"] == markets.ERHVERV["SEK"]["monthly"]
    assert "campaign_call" not in a and a["included_minutes"] == 300
    assert a["outbound_extra_minute"]["net_minor"] == 295 and a["outbound_extra_minute"]["currency"] == "SEK"
    assert a["inbound_extra_minute"]["net_minor"] == 220
    _country(db, ws, "DE")  # a later country change does not move the currency
    b = api.post(tok, f"/workspaces/{ws}/agreement", {"model": "A"}).json()
    assert (b["version"], b["currency"], b["monthly"]["net_minor"]) == (2, "SEK", 369_500)
    acc = api.get(tok, f"/workspaces/{ws}/billing/account").json()
    assert (acc["country"], acc["currency"], acc["vat_number"]) == ("DE", "SEK", None)
    assert acc["vat"]["kind"] == "vat_number_required" and acc["vat"]["rate_bp"] == 0
    # a Danish workspace is unchanged
    tok_b, ws_b = two_workspaces["tok_b"], two_workspaces["ws_b"]
    c = api.post(tok_b, f"/workspaces/{ws_b}/agreement", {"model": "A"}).json()
    assert (c["currency"], c["monthly"]["net_minor"], c["monthly"]["tax_basis_points"]) == ("DKK", 249_500, 2500)


def test_customer_campaigns_snapshot_the_workspace_currency(api, two_workspaces, db):
    tok, ws = two_workspaces["tok_a"], two_workspaces["ws_a"]
    _country(db, ws, "NO")
    lst = api.get(tok, f"/workspaces/{ws}/campaigns").json()
    assert lst["pricing"]["currency"] == "NOK" and lst["pricing"]["call_net_minor"] == 630  # answered, after the package
    c = api.post(tok, f"/workspaces/{ws}/campaigns", {"name": "Vår"}).json()
    assert c["pricing"] == c["pricing"] | {"currency": "NOK", "call_net_minor": 630, "minute_net_minor": 315,
                                           "call_prices": {"answered": 630, "voicemail": 160, "no_answer": 40}}
    assert c["max_cost"]["currency"] == "NOK" and c["max_cost"]["tax_basis_points"] == 0  # outside the EU
    tok_b, ws_b = two_workspaces["tok_b"], two_workspaces["ws_b"]
    d = api.post(tok_b, f"/workspaces/{ws_b}/campaigns", {"name": "Forår"}).json()
    assert (d["pricing"]["currency"], d["pricing"]["call_net_minor"], d["pricing"]["minute_net_minor"]) == ("DKK", 400, 200)
    assert d["max_cost"]["tax_basis_points"] == 2500


# --------------------------------------------------------------------------- statement


def _eur_month(db, ws, *, vat_number=None):
    """A German company on an EUR agreement with three campaign calls in September 2026."""
    ws = uuid.UUID(ws)
    p = db.get(BusinessProfile, ws)
    p.country, p.address_line, p.postal_code, p.city = "DE", "Hauptstr. 1", "10115", "Berlin"
    if vat_number:
        db.add(BillingAccount(workspace_id=ws, vat_number=vat_number))
    db.add(ReceptionAgreement(workspace_id=ws, version=1, model="A", currency="EUR", monthly_net_minor=32_900,
                              tax_basis_points=0, created_at=datetime(2026, 8, 1, tzinfo=UTC)))
    camp = Campaign(workspace_id=ws, name="Herbst", call_net_minor=55, minute_net_minor=27, max_attempts=2,
                    max_connected_seconds=180)
    db.add(camp)
    db.flush()
    contact = CampaignContact(campaign_id=camp.id, workspace_id=ws, phone="+4930123456", kind="business")
    db.add(contact)
    db.flush()
    for h in range(3):
        db.add(CampaignCall(workspace_id=ws, campaign_id=camp.id, contact_id=contact.id,
                            dialled_at=datetime(2026, 9, 10, 9 + h, tzinfo=UTC), net_minor=55))
    db.commit()


def test_statement_in_eur_with_reverse_charge(api, two_workspaces, db):
    tok, ws = two_workspaces["tok_a"], two_workspaces["ws_a"]
    _eur_month(db, ws, vat_number="DE123456789")
    s = api.get(tok, f"/workspaces/{ws}/billing/statement?month=2026-09").json()
    assert s["currency"] == "EUR"
    assert s["vat"] == {"kind": "reverse_charge", "rate_bp": 0, "country": "DE", "note": markets.REVERSE_CHARGE_NOTE,
                        "source": "estimate"}
    assert s["totals"] == {"currency": "EUR", "net_minor": 32_900 + 165, "tax_minor": 0, "gross_minor": 33_065,
                           "tax_basis_points": 0, "rounding": "half_up"}
    texts = [x["description"] for x in s["lines"]]
    assert texts == ["Dialogbot – subscription (agreement v1)",
                     'Campaign "Herbst": 3 outbound calls, 0 minutes of conversation']


def test_statement_without_vat_number_is_a_preview_that_asks_for_it(api, two_workspaces, db):
    tok, ws = two_workspaces["tok_a"], two_workspaces["ws_a"]
    _eur_month(db, ws)
    s = api.get(tok, f"/workspaces/{ws}/billing/statement?month=2026-09").json()
    assert s["vat"]["kind"] == "vat_number_required" and s["vat"]["rate_bp"] == 0
    assert s["totals"]["gross_minor"] == s["totals"]["net_minor"] == 33_065


def test_danish_statement_has_danish_vat_and_text(api, two_workspaces, db):
    ws = uuid.UUID(two_workspaces["ws_a"])
    db.add(ReceptionAgreement(workspace_id=ws, version=1, model="A", monthly_net_minor=249_500,
                              created_at=datetime(2026, 8, 1, tzinfo=UTC)))
    db.commit()
    s = api.get(two_workspaces["tok_a"], f"/workspaces/{ws}/billing/statement?month=2026-09").json()
    assert s["currency"] == "DKK" and s["vat"]["kind"] == "domestic" and s["vat"]["rate_bp"] == 2500
    assert s["lines"][0]["description"] == "Dialogbot – abonnement (aftale v1)" and s["totals"]["tax_minor"] == 62_375


# --------------------------------------------------------------------------- VAT number endpoint


def test_vat_number_endpoint(api, two_workspaces, db):
    tok, ws = two_workspaces["tok_a"], two_workspaces["ws_a"]
    _country(db, ws, "SE")
    url = f"/workspaces/{ws}/billing/vat-number"
    admin = api.add_member(tok, ws, "admin-vat@testmail.dk", "admin")
    assert api.put(admin, url, {"vat_number": "SE556677889901"}).status_code == 403  # billing.manage = the owner
    r = api.put(tok, url, {"vat_number": "se 5566 7788 9901"})
    assert r.status_code == 200, r.text
    out = r.json()
    assert (out["vat_number"], out["country"], out["currency"]) == ("SE556677889901", "SE", "SEK")
    assert out["vat"] == {"kind": "reverse_charge", "rate_bp": 0, "country": "SE", "note": markets.REVERSE_CHARGE_NOTE}
    bad = api.put(tok, url, {"vat_number": "DE123456789"})
    assert bad.status_code == 422 and bad.json()["code"] == "vat_number_country_mismatch"
    assert api.put(tok, url, {"vat_number": "SE1"}).json()["code"] == "invalid_vat_number"
    from app.models import AuditLog

    assert db.query(AuditLog).filter_by(action="billing.vat_number_changed").count() == 1
    cleared = api.put(tok, url, {"vat_number": ""}).json()
    assert cleared["vat_number"] is None and cleared["vat"]["kind"] == "vat_number_required"
    _country(db, ws, "GR")
    assert api.put(tok, url, {"vat_number": "123456789"}).json()["vat_number"] == "EL123456789"


# --------------------------------------------------------------------------- Stripe


class FakeStripe:
    def __init__(self, total=None, taxes=None):
        self.calls: list[tuple[str, str, dict]] = []
        self.total, self.taxes = total, taxes

    def __call__(self, method, path, data=None, *, idempotency_key=None, version=None):
        self.calls.append((method, path, data or {}))
        if path == "/customers":
            return {"id": "cus_eu"}
        if path == "/checkout/sessions":
            return {"id": "cs_1", "url": "https://checkout.stripe.com/c/pay/cs_1"}
        if path == "/tax_rates":
            return {"data": []} if method == "GET" else {"id": f"txr_{data['metadata']['dialogbot']}"}
        if path.endswith("/tax_ids") and method == "GET":
            return {"data": [{"id": "txi_old", "type": "eu_vat", "value": "DE999999999"}]}
        if path == "/invoices":
            return {"id": "in_eu", "status": "draft"}
        if path.endswith("/finalize"):
            out = {"id": "in_eu", "status": "open", "number": "DB-0101", "total": self.total}
            if self.taxes is not None:
                out |= {"total_excluding_tax": self.total - sum(self.taxes), "total_taxes": [{"amount": t} for t in self.taxes]}
            return out
        return {"id": f"obj_{len(self.calls)}"}

    def find(self, method, path):
        return [d for m, p, d in self.calls if (m, p) == (method, path)]


@pytest.fixture
def stripe_on(monkeypatch):
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_dummy")
    get_settings.cache_clear()
    yield monkeypatch
    get_settings.cache_clear()


def test_card_checkout_needs_the_vat_number_and_uses_currency_and_language(api, two_workspaces, db, stripe_on):
    tok, ws = two_workspaces["tok_a"], two_workspaces["ws_a"]
    fake = FakeStripe()
    stripe_on.setattr(stripe_api, "request", fake)
    _country(db, ws, "DE", address_line="Hauptstr. 1", postal_code="10115", city="Berlin")
    r = api.post(tok, f"/workspaces/{ws}/billing/card/checkout")
    assert r.status_code == 409 and r.json()["code"] == "vat_number_required" and "momsnummer" in r.json()["message"]
    assert fake.calls == []  # nothing at Stripe before the number is given
    api.put(tok, f"/workspaces/{ws}/billing/vat-number", {"vat_number": "DE123456789"})
    assert api.post(tok, f"/workspaces/{ws}/billing/card/checkout").status_code == 200
    cust = fake.find("POST", "/customers")[0]
    assert cust["preferred_locales"] == ["de"] and cust["tax_id_data"] == [{"type": "eu_vat", "value": "DE123456789"}]
    assert cust["address"] == {"country": "DE", "line1": "Hauptstr. 1", "postal_code": "10115", "city": "Berlin"}
    sess = fake.find("POST", "/checkout/sessions")[0]
    assert (sess["mode"], sess["currency"], sess["locale"]) == ("setup", "eur", "de")
    # a changed number replaces the customer's tax id (the old eu_vat id is deleted, the new one added)
    api.put(tok, f"/workspaces/{ws}/billing/vat-number", {"vat_number": "DE111222333"})
    assert ("DELETE", "/customers/cus_eu/tax_ids/txi_old", {}) in fake.calls
    assert fake.find("POST", "/customers/cus_eu/tax_ids")[-1] == {"type": "eu_vat", "value": "DE111222333"}


def _card(db, ws):
    a = db.get(BillingAccount, uuid.UUID(ws))
    a.stripe_customer_id, a.payment_method_id = "cus_eu", "pm_1"
    db.commit()


def _last_month_eur(db, ws):
    """_eur_month moved to last month (only closed months can be invoiced)."""
    first = date.today().replace(day=1)
    last = (first - timedelta(days=1)).replace(day=10)
    _eur_month(db, ws, vat_number="DE123456789")
    wsid = uuid.UUID(ws)
    db.query(ReceptionAgreement).filter_by(workspace_id=wsid).update(
        {"created_at": datetime.combine(last, datetime.min.time(), tzinfo=UTC) - timedelta(days=40)})
    db.query(CampaignCall).filter_by(workspace_id=wsid).update(
        {"dialled_at": datetime.combine(last, datetime.min.time(), tzinfo=UTC)})
    db.commit()
    _card(db, ws)
    return last.strftime("%Y-%m")


def test_invoice_in_eur_with_reverse_charge_and_no_tax_rate(api, two_workspaces, db, stripe_on):
    tok, ws = two_workspaces["tok_a"], two_workspaces["ws_a"]
    month = _last_month_eur(db, ws)
    fake = FakeStripe(total=33_065)
    stripe_on.setattr(stripe_api, "request", fake)
    r = api.post(tok, f"/workspaces/{ws}/billing/invoices", {"month": month})
    assert r.status_code == 201, r.text
    inv = r.json()
    assert (inv["currency"], inv["net_minor"], inv["tax_minor"], inv["gross_minor"], inv["tax_source"], inv["note"]) == (
        "EUR", 33_065, 0, 33_065, "manual", None)
    created = fake.find("POST", "/invoices")[0]
    assert created["currency"] == "eur" and "default_tax_rates" not in created and "automatic_tax" not in created
    assert created["footer"].endswith("\n" + markets.REVERSE_CHARGE_NOTE) and "CVR-nr. 25632710" in created["footer"]
    assert created["custom_fields"] == [{"name": "VAT", "value": markets.REVERSE_CHARGE_NOTE}]
    items = fake.find("POST", "/invoiceitems")
    assert [(i["currency"], i["amount"]) for i in items] == [("eur", 32_900), ("eur", 165)]
    assert all("tax_code" not in i for i in items)
    assert fake.find("GET", "/tax_rates") == []  # no tax rate at all


def test_invoice_with_stripe_tax_takes_the_amounts_from_stripe(api, two_workspaces, db, stripe_on):
    tok, ws = two_workspaces["tok_a"], two_workspaces["ws_a"]
    month = _last_month_eur(db, ws)
    stripe_on.setenv("STRIPE_TAX_ENABLED", "true")
    get_settings.cache_clear()
    fake = FakeStripe(total=33_100, taxes=[35])  # whatever Stripe Tax decided is what the row says
    stripe_on.setattr(stripe_api, "request", fake)
    inv = api.post(tok, f"/workspaces/{ws}/billing/invoices", {"month": month}).json()
    assert (inv["net_minor"], inv["tax_minor"], inv["gross_minor"], inv["tax_source"], inv["note"]) == (
        33_065, 35, 33_100, "stripe_tax", None)
    created = fake.find("POST", "/invoices")[0]
    assert created["automatic_tax"] == {"enabled": True} and "default_tax_rates" not in created
    assert "custom_fields" not in created and "Reverse charge" not in created["footer"]  # Stripe prints its own
    items = fake.find("POST", "/invoiceitems")
    assert all((i["tax_code"], i["tax_behavior"]) == ("txcd_10103001", "exclusive") for i in items)
    upd = fake.find("POST", "/customers/cus_eu")[0]  # address and tax id on the customer before the invoice
    assert upd["address"]["country"] == "DE" and upd["preferred_locales"] == ["de"]
    assert fake.find("POST", "/customers/cus_eu/tax_ids") == [{"type": "eu_vat", "value": "DE123456789"}]
    st = api.get(tok, f"/workspaces/{ws}/billing/statement?month={month}").json()
    assert st["vat"]["source"] == "estimate"


def test_no_invoice_without_the_vat_number(api, two_workspaces, db, stripe_on):
    tok, ws = two_workspaces["tok_a"], two_workspaces["ws_a"]
    month = _last_month_eur(db, ws)
    db.get(BillingAccount, uuid.UUID(ws)).vat_number = None
    db.commit()
    stripe_on.setattr(stripe_api, "request", FakeStripe(total=1))
    r = api.post(tok, f"/workspaces/{ws}/billing/invoices", {"month": month})
    assert r.status_code == 409 and r.json()["code"] == "vat_number_required"


def test_tax_rate_ids_are_cached_per_key_and_keep_the_danish_tag(stripe_on):
    fake = FakeStripe()
    stripe_on.setattr(stripe_api, "request", fake)
    assert stripe_api.tax_rate_id() == "txr_dk_vat_25"
    assert stripe_api.tax_rate_id("DK", 2500, True) == "txr_dk_vat_2500_incl"
    assert stripe_api.tax_rate_id("FI", 2550, True) == "txr_fi_vat_2550_incl"
    stripe_api.tax_rate_id()
    created = fake.find("POST", "/tax_rates")
    assert len(created) == 3 and created[2]["percentage"] == 25.5 and created[0]["display_name"] == "Moms"
