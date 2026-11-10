"""QA billing-qa · B05 – campaign order detail (/app/billing/orders/:id): immutable price snapshot, package usage,
related invoice and refund history. DB-012 (P0) fixture: 500 packages gross 562.500; 200 unused gross 225.000 at 25 %.

Per-call pricing replaced packages/orders (prices.py): there is no order model. What is testable: the money rule
(DB-012 numbers), and that agreements and campaign calls snapshot their price so a later list-price change does not
alter an old month."""
from __future__ import annotations

import uuid
from datetime import UTC, datetime

from app.models import ReceptionAgreement


def test_b05_db012_net_tax_gross_are_separate_and_half_up():
    from app.modules.billing.money import CampaignPackageTerms, Money, campaign_total_net

    terms = CampaignPackageTerms(net_minor=900, max_attempts=2, max_connected_ai_seconds_total=180)
    net = campaign_total_net(terms, 500)                  # 500 × 9 kr. = 4.500 kr.
    m = Money("DKK", net, 2500)
    assert (m.net_minor, m.tax_minor, m.gross_minor) == (450_000, 112_500, 562_500)
    unused = Money("DKK", campaign_total_net(terms, 200), 2500)
    assert (unused.net_minor, unused.tax_minor, unused.gross_minor) == (180_000, 45_000, 225_000)
    snap = m.snapshot()
    assert snap == {"currency": "DKK", "net_minor": 450_000, "tax_minor": 112_500, "gross_minor": 562_500,
                    "tax_basis_points": 2500, "rounding": "half_up"}
    # half-up at the øre: 1,50 kr. → 0,375 kr. moms → 38 øre; 1 øre → 0,25 → 0
    assert (Money("DKK", 150, 2500).tax_minor, Money("DKK", 1, 2500).tax_minor, Money("DKK", 2, 2500).tax_minor) == (38, 0, 1)


def test_b05_agreement_price_snapshot_is_immutable_under_a_list_price_change(api, two_workspaces, db, monkeypatch):
    from app.modules.billing import markets, prices

    ws = uuid.UUID(two_workspaces["ws_a"])
    tok = two_workspaces["tok_a"]
    assert api.post(tok, f"/workspaces/{ws}/agreement", {"model": "A"}).status_code == 201
    a = db.query(ReceptionAgreement).filter_by(workspace_id=ws).one()
    a.created_at = datetime(2026, 8, 1, tzinfo=UTC)
    db.commit()
    monkeypatch.setattr(prices, "SUBSCRIPTION_MONTHLY_NET_MINOR", 299_500)
    monkeypatch.setitem(markets.ERHVERV["DKK"], "monthly", 299_500)
    st = api.get(tok, f"/workspaces/{ws}/billing/statement?month=2026-09").json()
    assert [x["net_minor"] for x in st["lines"] if x["kind"] == "subscription"] == [249_500]
    # a NEW version takes the new list price; the old month is unchanged
    assert api.post(tok, f"/workspaces/{ws}/agreement", {"model": "A"}).json()["monthly"]["net_minor"] == 299_500
    st = api.get(tok, f"/workspaces/{ws}/billing/statement?month=2026-09").json()
    assert [x["net_minor"] for x in st["lines"] if x["kind"] == "subscription"] == [249_500]


def test_b05_order_detail_is_not_built(app):
    """Evidence for not-implemented: no order route, no order model."""
    import app.models as models

    assert not [getattr(r, "path", "") for r in app.routes if "/orders" in getattr(r, "path", "")]
    assert not [n for n in dir(models) if n.lower() in ("order", "campaignorder", "refund", "creditnote")]
