"""QA X17 (voice-qa): "Peter svarer kun fra godkendt viden; ingen «privat preview/invitationskode»; må nævne Dialogbot
Privat; humor uden at gøre grin med kunden".

Peter = the assistant on Dialogbot's own channels, all built from the SALES workspace (SALES_WORKSPACE_ID):
  1. inbound on Dialogbot's number   → telephony.vapi.assistant_config (generic inbound path)
  2. the website chat on dialogbot.dk → sales.service.chat_reply (POST /api/v1/demo-call/chat)
  3. the demo call Peter places       → sales.service.system_prompt / first_message
Offline: the prompt the model would get is captured at ai.service.log_call / the Vapi assistant-request answer. No
model, no network, no call. What the model then says is scored with qa/voice/run_cases.py against
qa/voice/cases/X17.yaml (reference transcripts; model-in-the-loop needs the network → blocked)."""
from __future__ import annotations

import importlib.util
import re
from pathlib import Path

import pytest

from app.modules.ai import service as ai_service
from app.modules.sales import script as sales_script
from app.modules.sales import service as sales_service
from tests.test_sales_demo_calls import SECRET, _web, sales  # noqa: F401  (fixture)

ROOT = Path(__file__).resolve().parents[2]
FORBIDDEN_WORDING = re.compile(r"privat[e]? preview|private preview|invitationskode|forhåndskode|preview-kode|"
                               r"adgangskode til preview", re.I)


def _runner():
    spec = importlib.util.spec_from_file_location("qa_voice_run_cases", ROOT / "qa/voice/run_cases.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _approve(api, tok, ws, kind, title, content, audience="public"):
    it = api.post(tok, f"/workspaces/{ws}/knowledge/items",
                  {"kind": kind, "title": title, "content": content, "audience": audience})
    assert it.status_code == 201, it.text
    vid = it.json()["open_draft"]["id"]
    api.submit(tok, ws, vid)
    assert api.approve(tok, ws, vid).status_code == 200
    return it.json()["id"]


def _inbound_system(client, *, caller="+4520304050") -> str:
    r = client.post("/api/v1/webhooks/vapi", headers={"authorization": f"Bearer {SECRET}"}, json={"message": {
        "type": "assistant-request", "call": {"id": "x17_in", "phoneNumberId": "pn_sales", "customer": {"number": caller}}}})
    assert r.status_code == 200, r.text
    body = r.json()
    assert "assistant" in body, body
    return body["assistant"]["model"]["messages"][0]["content"] + "\n" + body["assistant"]["firstMessage"]


def _chat_system(client, monkeypatch, question="Hvad kan I?") -> str:
    seen: dict = {}
    real = ai_service.log_call

    def spy(db, workspace, provider, **kw):
        seen["system"] = kw["system"]
        return real(db, workspace, provider, **kw)

    monkeypatch.setattr(ai_service, "log_call", spy)
    r = client.post("/api/v1/demo-call/chat", json={"messages": [{"role": "user", "content": question}]})
    assert r.status_code == 200, r.text
    return seen["system"]


def _demo_system(client, sales, db):  # noqa: F811
    assert _web(client, name="Mette Hansen", company="Berle Pool").status_code in (200, 201, 202)
    from app.models import DemoCall, PhoneNumber, Workspace

    d = db.query(DemoCall).order_by(DemoCall.created_at.desc()).first()
    ws = db.get(Workspace, d.workspace_id) if hasattr(d, "workspace_id") else db.get(Workspace, sales["ws"])
    db.query(PhoneNumber).first()
    return sales_service.system_prompt(db, ws, d) + "\n" + sales_service.first_message(d)


# --------------------------------------------------------------------------- 1. only approved knowledge (inbound: pass)

def test_x17_inbound_on_dialogbots_number_uses_only_approved_public_knowledge(client, api, sales, db):  # noqa: F811
    tok, ws = sales["tok"], sales["ws"]
    _approve(api, tok, ws, "fact", "Telefonpasning døgnet rundt", {"text": "Dialogbot tager telefonen døgnet rundt."})
    _approve(api, tok, ws, "fact", "INTERN-SALGSNOTE", {"text": "Rabatgrænse 30 procent"}, audience="internal")
    api.knowledge(tok, ws, "fact", "KLADDE-IKKE-GODKENDT", {"text": "Gratis i et år"})
    system = _inbound_system(client)
    assert "Telefonpasning døgnet rundt" in system
    assert "INTERN-SALGSNOTE" not in system and "Rabatgrænse" not in system, "internal knowledge reached Peter"
    assert "KLADDE-IKKE-GODKENDT" not in system and "Gratis i et år" not in system, "a draft reached Peter"
    # honest unknown → call-back, never a guess
    assert "Brug udelukkende oplysningerne i <godkendt_viden>" in system
    assert "sig det ærligt og tilbyd, at en medarbejder vender tilbage" in system
    assert "Gæt aldrig på priser, tider, tilbud eller vilkår" in system


def test_x17_archived_fact_disappears_from_peters_inbound_prompt(client, api, sales):  # noqa: F811
    tok, ws = sales["tok"], sales["ws"]
    item = _approve(api, tok, ws, "fact", "Booking i kalenderen", {"text": "Assistenten kan booke tider i kalenderen."})
    assert "Booking i kalenderen" in _inbound_system(client)
    assert api.delete(tok, f"/workspaces/{ws}/knowledge/items/{item}").status_code == 204
    assert "booke tider i kalenderen" not in _inbound_system(client)


# --------------------------------------------------------------------------- 1b. chat + demo call (F-V2-01: fail)

def test_x17_website_chat_only_claims_what_the_sales_workspace_has_approved(client, api, sales, monkeypatch):  # noqa: F811
    """The sales workspace has approved ONE fact (sales fixture: "Dialogbot – AI-receptionist …"). Nothing approved says
    the product books in a calendar, sends SMS, offers webchat or lets customers keep their number. Peter's chat on
    dialogbot.dk must then not be told so: «Svar kun ud fra den godkendte viden». Today chat_reply appends
    script.FEATURES (hard-coded product claims incl. prices) to every chat prompt, approved or not."""
    system = _chat_system(client, monkeypatch)
    approved_part = system.split("</godkendt_viden>")[0]
    extra_part = system.split("</godkendt_viden>", 1)[1]
    unapproved_claims = [c for c in ("Kan booke, flytte og aflyse tider", "Chat på hjemmesiden",
                                     "beholde sit nummer og viderestille", "Opfølgning på sendte tilbud")
                         if c in extra_part and c not in approved_part]
    assert not unapproved_claims, f"product claims outside approved knowledge are in Peter's chat prompt: {unapproved_claims}"


def test_x17_demo_call_only_claims_what_the_sales_workspace_has_approved(client, api, sales, db):  # noqa: F811
    system = _demo_system(client, sales, db)
    approved_part = system.split("</godkendt_viden>")[0]
    extra_part = system.split("</godkendt_viden>", 1)[1]
    unapproved_claims = [c for c in ("Kan booke, flytte og aflyse tider", "Chat på hjemmesiden",
                                     "beholde sit nummer og viderestille", "Opfølgning på sendte tilbud")
                         if c in extra_part and c not in approved_part]
    assert not unapproved_claims, f"product claims outside approved knowledge are in the demo-call prompt: {unapproved_claims}"


# --------------------------------------------------------------------------- 2. no «privat preview / invitationskode» (pass)

def test_x17_no_preview_or_invitation_wording_on_any_peter_path(client, api, sales, db, monkeypatch):  # noqa: F811
    from scripts.seed_sales_knowledge import ITEMS

    texts = {
        "inbound": _inbound_system(client),
        "chat": _chat_system(client, monkeypatch, "Har I en invitationskode til preview?"),
        "demo": _demo_system(client, sales, db),
        "FEATURES": sales_script.FEATURES,
        "CHAT_INSTRUCTIONS": sales_service.CHAT_INSTRUCTIONS,
        "phone_rules": ai_service.CHANNEL_INSTRUCTIONS["phone"][1],
        "seed_sales_knowledge": "\n".join(f"{t} {x}" for _, t, x, _ in ITEMS),
    }
    hits = {k: FORBIDDEN_WORDING.findall(v) for k, v in texts.items() if FORBIDDEN_WORDING.search(v)}
    assert not hits, f"preview/invitation wording in Peter's instructions: {hits}"


# --------------------------------------------------------------------------- 3. humour never at the caller's expense (F-V2-02)

HUMOUR_RULE = re.compile(r"humor|humør|spøg|munter", re.I)
AT_EXPENSE = re.compile(r"(aldrig|ikke)[^.]{0,60}(på kundens bekostning|gøre grin med|grine af|gør grin med)", re.I)


def test_x17_every_peter_prompt_allows_humour_but_never_at_the_callers_expense(client, api, sales, db, monkeypatch):  # noqa: F811
    prompts = {"inbound": _inbound_system(client), "chat": _chat_system(client, monkeypatch),
               "demo": _demo_system(client, sales, db)}
    missing = [k for k, p in prompts.items() if not (HUMOUR_RULE.search(p) and AT_EXPENSE.search(p))]
    assert not missing, f"no humour rule (allowed, never at the caller's expense) in Peter's prompt on: {missing}"


# --------------------------------------------------------------------------- 4. Dialogbot Privat (note only, per qa-lead)

def test_x17_nothing_forbids_peter_to_mention_dialogbot_privat(client, api, sales, db, monkeypatch):  # noqa: F811
    """Peter MAY mention Dialogbot Privat. Known (qa-lead, wave 2): Privat is not in his approved knowledge, so with
    «Brug udelukkende …» he will in practice say he does not know. Only asserted here: no rule FORBIDS it."""
    prompts = [_inbound_system(client), _chat_system(client, monkeypatch), _demo_system(client, sales, db)]
    for p in prompts:
        assert not re.search(r"(nævn|tal) (aldrig|ikke)[^.\n]{0,40}privat", p, re.I)


# --------------------------------------------------------------------------- 5. the scorer and the cases

def test_x17_cases_score_their_reference_transcripts():
    run = _runner()
    cases = run.load(ROOT / "qa/voice/cases/X17.yaml")
    assert len(cases) >= 4
    for c in cases:
        for kind, want in (("pass", True), ("fail", False)):
            for tr in (c.get("reference_transcripts") or {}).get(kind) or []:
                ok, why = run.score(c, tr)
                assert ok == want, f"{c['id']} reference {kind}: {why}"
