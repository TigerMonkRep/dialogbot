"""QA wave 2 (P1), e2e-erhverv instance C: campaign flow C02-C14 against the API + dialler with fake telephony.

Prices/amounts are deliberately NOT asserted (the price model changes on another branch). These tests cover
flow, legal rules (consent, opt-out, suppression), script/variables, live control (pause/resume) and the rule that
nobody is called without an explicit admin confirmation.

Run: source /home/claude/qa-env.sh && export TEST_DATABASE_URL=...qa_p1c DATABASE_URL=$TEST_DATABASE_URL &&
     pytest -p no:cacheprovider tests/qa/test_qa_e2c_campaigns.py
"""
from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, time

import pytest

from app.config import get_settings
from app.models import Campaign, CampaignContact, DoNotCall
from app.modules.campaigns import service

SECRET = "vapi-test-secret-0123456789abcdef"
CONSENT = "Tilmelding på hjemmesiden, marts 2026"
NOW = datetime.combine(date.today(), time(8, 0), tzinfo=UTC)  # 09/10:00 in Copenhagen


def _ready(api, t, monkeypatch, pn="pn_qa_e2c"):
    tok, ws = t["tok_a"], t["ws_a"]
    monkeypatch.setenv("VAPI_SERVER_SECRET", SECRET)
    monkeypatch.setenv("AI_PROVIDER", "fake")
    monkeypatch.setenv("VAPI_API_KEY", "vapi-private-key-test")
    get_settings.cache_clear()
    it = api.knowledge(tok, ws, "service", "Gulvafslibning", {"description": "Vi sliber trægulve."})
    api.submit(tok, ws, it["open_draft"]["id"])
    api.approve(tok, ws, it["open_draft"]["id"])
    api.map_number(ws, "+4570123456", pn, outbound=True)


def _campaign(api, t, name="QA-E2C", **extra):
    tok, ws = t["tok_a"], t["ws_a"]
    body = {"name": name, "purpose": "Tilbyde gulvafslibning til tidligere kunder", "call_days": list(service.DAYS),
            "call_from": "00:00", "call_to": "23:59"} | extra
    r = api.post(tok, f"/workspaces/{ws}/campaigns", body)
    assert r.status_code == 201, r.text
    return r.json()


def _import(api, t, cid, csv):
    r = api.post(t["tok_a"], f"/workspaces/{t['ws_a']}/campaigns/{cid}/contacts/import",
                 {"csv": csv, "kind": "business", "consent_source": CONSENT})
    assert r.status_code == 200, r.text
    return r.json()


def _start(api, t, cid):
    tok, ws = t["tok_a"], t["ws_a"]
    c = api.get(tok, f"/workspaces/{ws}/campaigns/{cid}").json()
    r = api.post(tok, f"/workspaces/{ws}/campaigns/{cid}/start",
                 {"expected_version": c["version"], "legal_confirmed": True, "accept_max_net_minor": c["max_cost"]["net_minor"]})
    assert r.status_code == 200, r.text
    return r.json()


def _report(client, call_id, number, messages, pn="pn_qa_e2c", reason="customer-ended-call", seconds=40):
    r = client.post("/api/v1/webhooks/vapi", headers={"authorization": f"Bearer {SECRET}"}, json={"message": {
        "type": "end-of-call-report", "endedReason": reason, "durationSeconds": seconds,
        "call": {"id": call_id, "phoneNumberId": pn, "type": "outboundPhoneCall", "customer": {"number": number}},
        "artifact": {"messages": messages}}})
    assert r.status_code == 200, r.text
    return r.json()


@pytest.fixture
def dial(monkeypatch):
    calls: list[dict] = []
    monkeypatch.setattr(service, "create_call", lambda p: calls.append(p) or {"id": f"qa_e2c_{len(calls)}"})
    monkeypatch.setattr(service, "_now", lambda: NOW)
    yield calls
    get_settings.cache_clear()


# --------------------------------------------------------------------------- C02 / C11: explicit start only

def test_c02_draft_never_dials_and_role_rules(api, two_workspaces, db, monkeypatch, dial):
    """C02: name, purpose, success saved via API and survive a re-read. A draft is never dialled by the worker;
    staff cannot create/start; another workspace cannot read it."""
    t = two_workspaces
    tok, ws = t["tok_a"], t["ws_a"]
    _ready(api, t, monkeypatch)
    c = _campaign(api, t, success="Kunden vil have et tilbud")
    _import(api, t, c["id"], "Mette Hansen;20304050")
    again = api.get(tok, f"/workspaces/{ws}/campaigns/{c['id']}").json()
    assert (again["name"], again["purpose"], again["success"], again["status"]) == (
        "QA-E2C", "Tilbyde gulvafslibning til tidligere kunder", "Kunden vil have et tilbud", "draft")
    assert service.dispatch(db, NOW) == 0 and dial == []
    # validation: empty name, inverted window
    assert api.post(tok, f"/workspaces/{ws}/campaigns", {"name": ""}).status_code == 422
    assert api.post(tok, f"/workspaces/{ws}/campaigns", {"name": "x", "call_from": "17:00", "call_to": "09:00"}).status_code == 422
    staff = api.add_member(tok, ws, "staff-e2c@testmail.dk", "staff")
    assert api.post(staff, f"/workspaces/{ws}/campaigns", {"name": "x"}).status_code == 403
    assert api.post(staff, f"/workspaces/{ws}/campaigns/{c['id']}/start",
                    {"expected_version": again["version"], "legal_confirmed": True, "accept_max_net_minor": 10**9}).status_code == 403
    assert api.post(staff, f"/workspaces/{ws}/campaigns/{c['id']}/contacts/import",
                    {"csv": "Ole;21222324", "kind": "business", "consent_source": CONSENT}).status_code == 403
    assert api.get(t["tok_b"], f"/workspaces/{t['ws_b']}/campaigns/{c['id']}").status_code == 404
    # start without legal confirmation is refused, and nothing is dialled
    r = api.post(tok, f"/workspaces/{ws}/campaigns/{c['id']}/start",
                 {"expected_version": again["version"], "legal_confirmed": False, "accept_max_net_minor": 10**9})
    assert r.status_code == 422
    assert service.dispatch(db, NOW) == 0 and dial == []


def test_c12_contacts_added_while_running_are_not_dialled_without_new_confirmation(api, two_workspaces, db, monkeypatch, dial):
    """F-E2C-03: the admin confirmed the legal checklist and the maximum for ONE contact. Contacts imported while the
    campaign runs must not be dialled until the admin confirms again (pause + start), otherwise people the admin
    never confirmed are called (C08 'snapshot selection', DB-008 'paid status does not launch')."""
    t = two_workspaces
    tok, ws = t["tok_a"], t["ws_a"]
    _ready(api, t, monkeypatch)
    c = _campaign(api, t)
    _import(api, t, c["id"], "Mette Hansen;20304050")
    started = _start(api, t, c["id"])
    confirmed_max = started["legal_confirmation"]["accepted_max_net_minor"]
    assert service.dispatch(db, NOW) == 1
    _report(api.c, "qa_e2c_1", "+4520304050", [{"role": "bot", "message": "Hej"}, {"role": "user", "message": "Ja, jeg er interesseret"}])
    # while running, 3 more contacts are imported (the UI shows «Tilføj kontakter» for running campaigns too)
    imp = api.post(tok, f"/workspaces/{ws}/campaigns/{c['id']}/contacts/import",
                   {"csv": "Ole Berg;21222324\nBo Lund;22334455\nJens Juul;23344556", "kind": "business", "consent_source": CONSENT})
    now_max = api.get(tok, f"/workspaces/{ws}/campaigns/{c['id']}").json()["max_cost"]["net_minor"]
    dialled_new = 0
    for _ in range(3):
        dialled_new += service.dispatch(db, NOW)
        if dial:
            n = dial[-1]["customer"]["number"]
            if n != "+4520304050":
                _report(api.c, f"qa_e2c_{len(dial)}", n, [{"role": "bot", "message": "Hej"}, {"role": "user", "message": "Måske"}])
    assert imp.status_code == 409 or dialled_new == 0, (
        f"{dialled_new} new contacts were dialled although the admin only confirmed 1 contact "
        f"(confirmed max {confirmed_max}, max for the remaining contacts now {now_max}); import status {imp.status_code}")


def test_c12_pause_stops_dialling_and_resume_requires_confirmation(api, two_workspaces, db, monkeypatch, dial):
    t = two_workspaces
    tok, ws = t["tok_a"], t["ws_a"]
    _ready(api, t, monkeypatch)
    c = _campaign(api, t)
    _import(api, t, c["id"], "Mette Hansen;20304050\nOle Berg;21222324")
    _start(api, t, c["id"])
    assert service.dispatch(db, NOW) == 1
    paused = api.post(tok, f"/workspaces/{ws}/campaigns/{c['id']}/pause").json()
    assert paused["status"] == "paused"
    _report(api.c, "qa_e2c_1", "+4520304050", [{"role": "bot", "message": "Hej"}, {"role": "user", "message": "Ja gerne"}])
    assert service.dispatch(db, NOW) == 0 and len(dial) == 1  # paused: Ole is not called
    # double pause is harmless
    assert api.post(tok, f"/workspaces/{ws}/campaigns/{c['id']}/pause").json()["status"] == "paused"
    # resume needs the legal confirmation again
    cur = api.get(tok, f"/workspaces/{ws}/campaigns/{c['id']}").json()
    assert cur["counts"]["by_status"] == {"done": 1, "pending": 1} and cur["counts"]["open"] == 1
    r = api.post(tok, f"/workspaces/{ws}/campaigns/{c['id']}/start",
                 {"expected_version": cur["version"], "legal_confirmed": False, "accept_max_net_minor": cur["max_cost"]["net_minor"]})
    assert r.status_code == 422
    # double submit of resume: the second request is a version conflict, not a second start
    body = {"expected_version": cur["version"], "legal_confirmed": True, "accept_max_net_minor": cur["max_cost"]["net_minor"]}
    assert api.post(tok, f"/workspaces/{ws}/campaigns/{c['id']}/start", body).status_code == 200
    assert api.post(tok, f"/workspaces/{ws}/campaigns/{c['id']}/start", body).status_code == 409
    assert service.dispatch(db, NOW) == 1 and dial[-1]["customer"]["number"] == "+4521222324"


# --------------------------------------------------------------------------- C04/C05: consent, validation, dedup

def test_c05_validation_counts_and_suppression(api, two_workspaces, db, monkeypatch):
    t = two_workspaces
    tok, ws = t["tok_a"], t["ws_a"]
    _ready(api, t, monkeypatch)
    c = _campaign(api, t)
    api.post(tok, f"/workspaces/{ws}/do-not-call", {"phone": "+45 21 22 23 24", "reason": "Bad os lade være"})
    csv = ("Navn;Telefon;Firma\nMette Hansen;20 30 40 50;Hansen Byg ApS\nOle Berg;21222324;Berg VVS\n"
           "Forkert;123;X\nMette igen;0045 20304050;Dup\n")
    r = _import(api, t, c["id"], csv)
    assert (r["added"], r["duplicates"], r["blocked"], r["invalid_count"]) == (1, 1, 1, 1)
    # re-import the same file (double submit / refresh): nothing new, everything a duplicate or blocked
    r2 = _import(api, t, c["id"], csv)
    assert (r2["added"], r2["duplicates"], r2["blocked"]) == (0, 2, 1)
    items = api.get(tok, f"/workspaces/{ws}/campaigns/{c['id']}/contacts").json()["items"]
    assert [(x["phone"], x["consent_source"]) for x in items] == [("+4520304050", CONSENT)]
    # consent is required for businesses too (markedsføringsloven § 10)
    no = api.post(tok, f"/workspaces/{ws}/campaigns/{c['id']}/contacts/import", {"csv": "Bo;22334455", "kind": "business", "consent_source": " "})
    assert no.status_code == 422 and no.json()["field_errors"][0]["field"] == "consent_source"
    empty = api.post(tok, f"/workspaces/{ws}/campaigns/{c['id']}/contacts/import", {"csv": "Navn;Telefon\n", "kind": "business", "consent_source": CONSENT})
    assert empty.status_code == 422


@pytest.mark.xfail(strict=True, reason="F-E2C-09-C05: S3 new – «ugyldige numre (fx række N)» tæller ikke overskriftsrækken med: det ugyldige nummer på linje 3 i filen …")
def test_c05_invalid_row_number_matches_the_file_line(api, two_workspaces, monkeypatch):
    """F-E2C-09: «ugyldige numre (fx række N)» – N must be the row the user sees in Excel/the file. With a header
    row, the invalid number on file line 3 is reported as «række 2» (the header is not counted); without a header
    the same data on line 3 is «række 3». The UI cannot tell the user which one it means."""
    t = two_workspaces
    _ready(api, t, monkeypatch)
    c = _campaign(api, t)
    with_header = _import(api, t, c["id"], "Navn;Telefon\nMette Hansen;20304050\nForkert;123\n")
    # file line 3 holds "123"
    assert with_header["invalid"][0]["row"] == 3, with_header["invalid"]


# --------------------------------------------------------------------------- C06/C07: script and variables

def test_c06_opening_always_discloses_ai_and_fills_known_variables(api, two_workspaces, db, monkeypatch, dial):
    t = two_workspaces
    _ready(api, t, monkeypatch)
    c = _campaign(api, t, opening="Godmorgen {navn}, her er {virksomhed}.")
    _import(api, t, c["id"], "Mette Hansen;20304050")
    _start(api, t, c["id"])
    assert service.dispatch(db, NOW) == 1
    first = dial[0]["assistant"]["firstMessage"]
    assert first.startswith("Godmorgen Mette, her er Fjord Gulvservice ApS.") and "digital assistent" in first


@pytest.mark.xfail(strict=True, reason="F-E2C-04-C07: S2 new – Ukendte variabler i første replik ({fornavn}, {firma}, {Navn}) gemmes uden advarsel og læses højt for …")
def test_c07_unknown_script_variable_is_rejected_not_spoken(api, two_workspaces, db, monkeypatch, dial):
    """F-E2C-04: «{fornavn}» (or a typo like «{Navn}») is not a known variable. It must be refused when saving (or at
    least before start), never read aloud as «krøllet parentes fornavn» to a customer."""
    t = two_workspaces
    tok, ws = t["tok_a"], t["ws_a"]
    _ready(api, t, monkeypatch)
    c = _campaign(api, t)
    r = api.put(tok, f"/workspaces/{ws}/campaigns/{c['id']}",
                {"name": c["name"], "purpose": c["purpose"], "opening": "Hej {fornavn}, det er den digitale assistent fra {firma}.",
                 "phone_number_id": c["phone_number_id"], "call_days": list(service.DAYS), "call_from": "00:00", "call_to": "23:59",
                 "expected_version": c["version"]})
    if r.status_code == 422:
        return  # refused at save: fine
    _import(api, t, c["id"], "Mette Hansen;20304050")
    _start(api, t, c["id"])
    assert service.dispatch(db, NOW) == 1
    first = dial[0]["assistant"]["firstMessage"]
    assert "{" not in first, f"spoken to the customer: {first!r}"


# --------------------------------------------------------------------------- C13/C14: outcomes and suppression

def test_c14_opt_out_suppresses_in_every_campaign(api, two_workspaces, db, monkeypatch, dial):
    t = two_workspaces
    tok, ws = t["tok_a"], t["ws_a"]
    _ready(api, t, monkeypatch)
    a = _campaign(api, t, name="Kampagne A")
    _import(api, t, a["id"], "Ole Berg;21222324")
    _start(api, t, a["id"])
    assert service.dispatch(db, NOW) == 1
    _report(api.c, "qa_e2c_1", "+4521222324", [{"role": "bot", "message": "Hej Ole"}, {"role": "user", "message": "Ring ikke igen, tak."}])
    ole = api.get(tok, f"/workspaces/{ws}/campaigns/{a['id']}/contacts").json()["items"][0]
    assert (ole["status"], ole["outcome"], ole["attempts"]) == ("opted_out", "opt_out", 1)
    assert ole["conversation_id"]  # transcript is kept (permitted transcript, C14)
    b = _campaign(api, t, name="Kampagne B")
    assert _import(api, t, b["id"], "Ole Berg;21 22 23 24")["blocked"] == 1
    entry = next(x for x in api.get(tok, f"/workspaces/{ws}/do-not-call").json()["items"] if x["phone"] == "+4521222324")
    assert entry["source"] == "call"
    assert api.delete(tok, f"/workspaces/{ws}/do-not-call/{entry['id']}").status_code == 409


def test_c14_nej_tak_is_never_called_again_as_promised(api, two_workspaces, db, monkeypatch, dial):
    """F-E2C-02: the campaign prompt tells the assistant: «Hvis personen siger nej eller ikke vil ringes op igen, så
    ... bekræft at de ikke bliver ringet op igen» (campaigns/service.py:247) and the editor tells the owner «Siger de
    nej, kommer de på spærrelisten» (da/app.json campaigns.editor.whenSub). A plain «Nej tak» (outcome
    not_interested) must therefore suppress future calls. It does not: the number can be imported and dialled in the
    next campaign."""
    t = two_workspaces
    tok, ws = t["tok_a"], t["ws_a"]
    _ready(api, t, monkeypatch)
    prompt_rule = "Hvis personen siger nej eller ikke vil ringes op igen"
    a = _campaign(api, t, name="Forår")
    _import(api, t, a["id"], "Mette Hansen;20304050")
    _start(api, t, a["id"])
    assert service.dispatch(db, NOW) == 1
    assert prompt_rule in dial[0]["assistant"]["model"]["messages"][0]["content"]
    _report(api.c, "qa_e2c_1", "+4520304050", [{"role": "bot", "message": "Hej Mette"}, {"role": "user", "message": "Nej tak."}])
    mette = api.get(tok, f"/workspaces/{ws}/campaigns/{a['id']}/contacts").json()["items"][0]
    assert mette["outcome"] == "not_interested"
    b = _campaign(api, t, name="Efterår")
    imp = _import(api, t, b["id"], "Mette Hansen;20304050")
    on_list = db.query(DoNotCall).filter_by(workspace_id=uuid.UUID(ws), phone="+4520304050").count()
    assert on_list == 1 and imp["added"] == 0, (
        f"Mette said «Nej tak» and was told she will not be called again; on do-not-call list: {on_list}, "
        f"added to the next campaign: {imp['added']}")


def test_c13_results_follow_up_lead_and_completion(api, two_workspaces, db, monkeypatch, dial):
    t = two_workspaces
    tok, ws = t["tok_a"], t["ws_a"]
    _ready(api, t, monkeypatch)
    c = _campaign(api, t)
    _import(api, t, c["id"], "Mette Hansen;20304050")
    _start(api, t, c["id"])
    assert service.dispatch(db, NOW) == 1
    _report(api.c, "qa_e2c_1", "+4520304050", [{"role": "bot", "message": "Hej"}, {"role": "user", "message": "Ja, jeg er interesseret"}])
    service.dispatch(db, NOW)
    out = api.get(tok, f"/workspaces/{ws}/campaigns/{c['id']}").json()
    assert out["status"] == "completed" and out["completed_at"]
    assert out["counts"]["by_outcome"] == {"interested": 1} and out["counts"]["answered"] == 1 and out["counts"]["open"] == 0
    x = api.get(tok, f"/workspaces/{ws}/campaigns/{c['id']}/contacts").json()["items"][0]
    assert x["lead_id"] and x["summary"]
    # a completed campaign cannot be restarted or receive contacts
    assert api.post(tok, f"/workspaces/{ws}/campaigns/{c['id']}/contacts/import",
                    {"csv": "Ole;21222324", "kind": "business", "consent_source": CONSENT}).status_code == 409
    assert api.post(tok, f"/workspaces/{ws}/campaigns/{c['id']}/start",
                    {"expected_version": out["version"], "legal_confirmed": True, "accept_max_net_minor": 10**9}).status_code == 409
    db.expire_all()  # the test's own session still holds the contact as dispatch() left it («calling»); read the committed row
    assert db.get(Campaign, uuid.UUID(c["id"])).status == "completed"
    assert db.query(CampaignContact).filter_by(campaign_id=uuid.UUID(c["id"])).one().status == "done"
