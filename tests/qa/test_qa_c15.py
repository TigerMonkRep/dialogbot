"""QA C15 (e2e-erhverv B): campaign reconciliation – counters derived from one source (DB-003), packages/refunds
(DB-012).

Requirement C15: "Purchased/consumed/unused/pending packages, cancellation and pending/confirmed refunds."
Business rule: campaign counters (contacts vs attempts) are derived from one source.
"""
from __future__ import annotations

from datetime import UTC, date, datetime, time

from app.config import get_settings
from app.models import CampaignCall, CampaignContact
from app.modules.campaigns import service

SECRET = "vapi-test-secret-0123456789abcdef"


def _running(api, t, monkeypatch):
    tok, ws = t["tok_a"], t["ws_a"]
    monkeypatch.setenv("VAPI_SERVER_SECRET", SECRET)
    monkeypatch.setenv("AI_PROVIDER", "fake")
    monkeypatch.setenv("VAPI_API_KEY", "vapi-private-key-test")
    get_settings.cache_clear()
    it = api.knowledge(tok, ws, "service", "Gulvafslibning", {"description": "Vi sliber trægulve."})
    api.submit(tok, ws, it["open_draft"]["id"])
    api.approve(tok, ws, it["open_draft"]["id"])
    api.map_number(ws, "+4570123456", "pn_qa_c15", outbound=True)
    c = api.post(tok, f"/workspaces/{ws}/campaigns", {"name": "QA-EB afstemning", "purpose": "Tilbud",
                                                       "call_days": list(service.DAYS), "call_from": "00:00", "call_to": "23:59"}).json()
    api.post(tok, f"/workspaces/{ws}/campaigns/{c['id']}/contacts/import",
             {"csv": "Mette Hansen;20304050\nOle Berg;21222324\nBo Lund;22334455", "kind": "business",
              "consent_source": "Tilmelding på hjemmesiden, marts 2026"})
    c = api.get(tok, f"/workspaces/{ws}/campaigns/{c['id']}").json()
    r = api.post(tok, f"/workspaces/{ws}/campaigns/{c['id']}/start",
                 {"expected_version": c["version"], "legal_confirmed": True, "accept_max_net_minor": c["max_cost"]["net_minor"]})
    assert r.status_code == 200, r.text
    return c


def _report(client, call_id, number, messages, reason="customer-ended-call", seconds=60):
    return client.post("/api/v1/webhooks/vapi", headers={"authorization": f"Bearer {SECRET}"}, json={"message": {
        "type": "end-of-call-report", "endedReason": reason, "durationSeconds": seconds,
        "call": {"id": call_id, "phoneNumberId": "pn_qa_c15", "type": "outboundPhoneCall", "customer": {"number": number}},
        "artifact": {"messages": messages}}})


def test_c15_counters_from_one_source(api, client, two_workspaces, db, monkeypatch):
    """Contacts, attempts and answered calls shown on the campaign page (kampagner/[id]/page.tsx: stats) must
    reconcile with the stored contacts and calls."""
    t = two_workspaces
    tok, ws = t["tok_a"], t["ws_a"]
    c = _running(api, t, monkeypatch)
    calls = []
    monkeypatch.setattr(service, "create_call", lambda p: calls.append(p) or {"id": f"qa_out_{len(calls)}"})
    now = datetime.combine(date.today(), time(8, 0), tzinfo=UTC)
    monkeypatch.setattr(service, "_now", lambda: now)
    # Mette: answers, interested. Ole: answers and opts out. Bo: no answer.
    assert service.dispatch(db, now) == 1
    assert _report(client, "qa_out_1", "+4520304050", [{"role": "bot", "message": "Hej"},
                                                        {"role": "user", "message": "Ja, jeg er interesseret i et tilbud"}]).status_code == 200
    assert service.dispatch(db, now) == 1
    assert _report(client, "qa_out_2", "+4521222324", [{"role": "bot", "message": "Hej"},
                                                        {"role": "user", "message": "Nej tak, ring ikke igen."}]).status_code == 200
    assert service.dispatch(db, now) == 1
    assert _report(client, "qa_out_3", "+4522334455", [{"role": "bot", "message": "Hej"}],
                   reason="customer-did-not-answer", seconds=0).status_code == 200
    db.expire_all()
    out = api.get(tok, f"/workspaces/{ws}/campaigns/{c['id']}").json()
    counts = out["counts"]
    contacts = db.query(CampaignContact).filter(CampaignContact.campaign_id == __import__("uuid").UUID(c["id"])).all()
    n_calls = db.query(CampaignCall).filter(CampaignCall.campaign_id == __import__("uuid").UUID(c["id"])).count()
    # contacts vs attempts kept apart and consistent
    assert counts["total"] == len(contacts) == 3
    assert counts["calls"] == n_calls == sum(x.attempts for x in contacts) == 3
    assert sum(counts["by_status"].values()) == counts["total"]
    # "Talt med" on the campaign page and list is counts.answered (kampagner/[id]/page.tsx, kampagner/page.tsx –
    # since c3bed12; before it was by_status.done). Two people answered (Mette and Ole); Ole's call was answered and
    # ended with an opt-out, so his status stays opted_out (used by «Frabedt sig opkald»). The counter must count both.
    answered_contacts = sum(1 for x in contacts if x.connected_seconds > 0 or x.outcome in service.OUTCOMES)
    assert answered_contacts == 2
    assert counts["by_status"].get("done", 0) == 1 and counts["by_status"].get("opted_out", 0) == 1
    ui_answered = counts.get("answered", counts["by_status"].get("done", 0))
    assert ui_answered == answered_contacts, (
        f"Besvaret shows {ui_answered} but {answered_contacts} contacts answered (by_status={counts['by_status']})")
    get_settings.cache_clear()


def test_c15_campaign_does_not_claim_packages(api, two_workspaces):
    """C15/DB-012: campaigns are pay per call, billed monthly – the campaign payload carries the max cost and does
    not claim packages it does not have."""
    t = two_workspaces
    tok, ws = t["tok_a"], t["ws_a"]
    c = api.post(tok, f"/workspaces/{ws}/campaigns", {"name": "QA-EB pakker"}).json()
    assert "max_cost" in c and "packages" not in c


def test_c15_c09_packages_checkout_and_refunds_exist(api, two_workspaces):
    """C15/C09 with the minute package (Fürster 2026-11-10): a campaign has no packages, checkout or orders of its own
    – its minutes draw on the workspace's monthly package and are billed on the monthly invoice. What C15 asks for
    («consumed/unused», «refunds») is: the campaign shows the package left and an honest maximum before it starts,
    and a refund is a complaint about one call (billing disputes)."""
    t = two_workspaces
    tok, ws = t["tok_a"], t["ws_a"]
    c = api.post(tok, f"/workspaces/{ws}/campaigns", {"name": "QA-EB pakker"}).json()
    assert c["package"] == {"included": 300, "remaining": 300} and c["pricing"]["call_prices"]["answered"] == 400
    assert {"max_cost", "max_cost_with_package", "max_minutes"} <= set(c)
    for p in ("checkout", "packages", "order"):  # no per-campaign purchase exists
        assert api.get(tok, f"/workspaces/{ws}/campaigns/{c['id']}/{p}").status_code in (404, 405)
    assert api.get(tok, f"/workspaces/{ws}/billing/disputes").status_code == 200  # «refunds»: complaints about calls
    assert api.get(tok, f"/workspaces/{ws}/billing/usage").status_code == 200     # consumed per call
