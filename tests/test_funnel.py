"""The quiz-funnels (/start and /privat/start): drafts without an account, Places and the estimate, the crawl kept
on the draft, the SMS gate (honeypot, limits, wrong code), and the reveal: user + session + workspace + demo call
with the company's facts (Erhverv) or the private account with real tasks (Privat). Nothing is called or created
before the code; crawled knowledge stays unapproved."""
from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.config import get_settings
from app.db import get_session_factory
from app.models import (
    AuditLog,
    BusinessProfile,
    DemoCall,
    FunnelDraft,
    KnowledgeVersion,
    OutboxEvent,
    PrivateTask,
    User,
    WorkspaceCategory,
    WorkspaceVoiceSettings,
)
from app.modules.ai import provider as ai_provider
from app.modules.ai.provider import FakeProvider
from app.modules.campaigns import service as campaigns
from app.modules.funnel import limits, service
from app.modules.integrations.connectors.fakes import WORLD
from app.modules.knowledge import importer
from app.modules.privat import rules
from app.modules.sales import places as gp
from app.modules.sales import service as sales
from app.worker import runner
from tests.privat_fixtures import WED_10, Clock
from tests.test_website_import import fake_fetch

SECRET = "vapi-test-secret-0123456789abcdef"
MON_10 = datetime(2026, 9, 28, 8, 0, tzinfo=UTC)  # 10:00 in Copenhagen: inside the demo-call hours
MON_22 = datetime(2026, 9, 28, 20, 0, tzinfo=UTC)
# A demo place with a crawlable site (tests/test_website_import.SITE) and Google-style opening hours
HANSEN = {"id": "demo_hansen", "displayName": {"text": "Hansen VVS Aarhus", "languageCode": "da"},
          "formattedAddress": "Havnevej 12, 8000 Aarhus C, Danmark",
          "addressComponents": [{"longText": "8000", "shortText": "8000", "types": ["postal_code"]},
                                {"longText": "Aarhus C", "shortText": "Aarhus C", "types": ["locality"]}],
          "location": {"latitude": 56.15, "longitude": 10.2}, "types": ["plumber"], "primaryType": "plumber",
          "businessStatus": "OPERATIONAL", "googleMapsUri": "https://maps.example.invalid/demo_hansen",
          "searchTerms": ["vvs", "hansen"],
          "details": {"websiteUri": "https://fjordgulv.dk/", "nationalPhoneNumber": "86 12 34 56",
                      "internationalPhoneNumber": "+45 86 12 34 56",
                      "regularOpeningHours": {"weekdayDescriptions": ["mandag: 07.00–16.00", "tirsdag: 07.00–16.00"],
                                              "periods": [{"open": {"day": d, "hour": 7, "minute": 0},
                                                           "close": {"day": d, "hour": 16, "minute": 0}}
                                                          for d in (1, 2, 3, 4, 5)]}}}


@pytest.fixture
def funnel(api, two_workspaces, monkeypatch):
    """Sales workspace ready for demo calls (faked Vapi), fake AI and SMS, demo Places with one crawlable company."""
    t = two_workspaces
    tok, ws = t["tok_a"], t["ws_a"]
    monkeypatch.setenv("VAPI_SERVER_SECRET", SECRET)
    monkeypatch.setenv("VAPI_API_KEY", "vapi-private-key-test")
    monkeypatch.setenv("AI_PROVIDER", "fake")
    monkeypatch.setenv("SALES_WORKSPACE_ID", ws)
    monkeypatch.setenv("CONNECTORS_PROVIDER", "fake")
    monkeypatch.setenv("PRIVAT_ENABLED", "true")
    monkeypatch.setenv("PRIVAT_ALLOWED_EMAILS", "")
    monkeypatch.setenv("PRIVAT_POOL_NUMBERS", "+4589870000=pn_pool")
    get_settings.cache_clear()
    ai_provider.set_provider_override(FakeProvider(get_settings()))
    monkeypatch.setattr(importer, "fetch", fake_fetch)
    it = api.knowledge(tok, ws, "service", "Dialogbot", {"description": "AI-receptionist til danske virksomheder."})
    api.submit(tok, ws, it["open_draft"]["id"])
    api.approve(tok, ws, it["open_draft"]["id"])
    api.map_number(ws, "+4570123456", "pn_sales", outbound=True)
    calls: list[dict] = []
    monkeypatch.setattr(campaigns, "create_call", lambda payload: (calls.append(payload) or {"id": f"demo_{len(calls)}"}))
    clock = [MON_10]
    monkeypatch.setattr(sales, "_now", lambda: clock[0])
    monkeypatch.setattr(rules, "now", Clock(WED_10))
    gp.set_client_override(gp.DemoPlaces([HANSEN]))
    WORLD.reset()
    yield {"calls": calls, "clock": clock, "ws": ws, "tok": tok}
    gp.set_client_override(None)
    ai_provider.set_provider_override(None)
    get_settings.cache_clear()


def _code() -> str:
    return re.search(r"er (\d{6})\.", WORLD.sms[-1]["body"]).group(1)


def _gate(client, did, **over):
    body = {"name": "Mette Hansen", "email": "mette@testmail.dk", "phone": "20 30 40 50", "consent": True} | over
    return client.post(f"/api/v1/funnel/drafts/{did}/gate", json=body)


def _patch(client, did, step, answers):
    r = client.patch(f"/api/v1/funnel/drafts/{did}", json={"step": step, "answers": answers})
    assert r.status_code == 200, r.text
    return r.json()


def test_erhverv_full_path(client, api, funnel, db):
    r = client.post("/api/v1/funnel/drafts", json={"kind": "erhverv", "hook": "mister-opkald", "industry": "haandvaerker",
                                                   "utm": {"source": "meta", "campaign": "q4", "medium": "cpc"}})
    assert r.status_code == 201, r.text
    d = r.json()
    did = d["id"]
    assert d["kind"] == "erhverv" and d["industry"] == "haandvaerker" and d["step"] == 1 and d["gated"] is False
    assert d["company"] is None and d["estimate"] is None
    assert d["build"] == {"knowledge": "skipped", "voice": "done", "voice_key": "peter", "hours": "default", "number": "done"}
    # step 2: Places suggestions, then the chosen company
    sug = client.get("/api/v1/funnel/places", params={"q": "Hansen", "industry": "haandvaerker"}).json()["items"]
    assert sug[0]["name"] == "Hansen VVS Aarhus" and sug[0]["phone_display"] == "86 12 34 56" and sug[0]["website"]
    assert set(sug[0]) == {"place_id", "name", "address", "phone_display", "website", "open_now", "source"}
    d = _patch(client, did, 2, {"company_name": "Hansen VVS", "place_id": "demo_hansen"})
    c = d["company"]
    assert c["name"] == "Hansen VVS Aarhus" and c["address"] == "Havnevej 12, 8000 Aarhus C, Danmark"
    assert c["phone_display"] == "86 12 34 56" and c["website"] == "https://fjordgulv.dk/" and c["place_id"] == "demo_hansen"
    assert c["opening_hours_text"] == "mandag: 07.00–16.00; tirsdag: 07.00–16.00"
    assert d["build"]["hours"] == "done" and d["build"]["knowledge"] == "pending"  # a site is known, not fetched yet
    # step 3: the estimate (table × chips), overridden by the visitor's own number
    d = _patch(client, did, 3, {"missed": ["lunch", "after16"]})
    assert d["estimate"] == {"missed_per_week": 11, "source": service.estimates.SOURCE}
    d = _patch(client, did, 3, {"missed_per_week": 7})
    assert d["estimate"] == {"missed_per_week": 7, "source": "Dit eget tal"} and d["answers"]["missed"] == ["lunch", "after16"]
    # step 4: the crawl runs in the background and stays on the draft; nothing exists in any workspace
    d = _patch(client, did, 4, {"wants": ["book", "prices"]})
    d = client.get(f"/api/v1/funnel/drafts/{did}").json()
    assert d["build"]["knowledge"] == "done" and d["build"]["pages_count"] == 3 and "pages" not in d["build"]
    assert db.query(KnowledgeVersion).filter_by(source_type="extraction").count() == 0
    assert db.query(User).filter_by(email_normalized="mette@testmail.dk").count() == 0 and funnel["calls"] == []
    # the gate: SMS code (only the HMAC stored), 5 attempts
    g = _gate(client, did)
    assert g.status_code == 202 and g.json() == {"status": "code_sent", "phone_display": "20 30 40 50"}
    assert WORLD.sms[-1]["to"] == "+4520304050" and WORLD.sms[-1]["from"] == "Dialogbot"
    code = _code()
    row = db.get(FunnelDraft, uuid.UUID(did))
    assert code not in (row.code_hash or "") and row.gate["email"] == "mette@testmail.dk"
    assert client.get(f"/api/v1/funnel/drafts/{did}").json()["gated"] is True
    assert _gate(client, did).json()["code"] == "too_soon"
    bad = client.post(f"/api/v1/funnel/drafts/{did}/verify", json={"code": "000000" if code != "000000" else "111111"})
    assert bad.status_code == 422 and bad.json()["attempts_left"] == 4
    assert funnel["calls"] == []
    # the right code: user, session, workspace, demo call
    v = client.post(f"/api/v1/funnel/drafts/{did}/verify", json={"code": code})
    assert v.status_code == 200, v.text
    out = v.json()
    assert out["status"] == "ok" and out["next"] == "/start/klar" and out["new_user"] is True
    assert out["session_token"] == out["access_token"] and out["token_type"] == "bearer"
    assert out["user"]["email"] == "mette@testmail.dk" and out["user"]["email_verified"] is False
    tok = out["session_token"]
    assert api.get(tok, "/auth/me").json()["display_name"] == "Mette Hansen"
    ws = out["workspace_id"]
    db.expire_all()
    u = db.query(User).filter_by(email_normalized="mette@testmail.dk").one()
    assert u.phone_verified_at is not None and u.email_verified_at is None and u.signup_source == "funnel:erhverv:mister-opkald"
    # the workspace: profile for /opsaetning/1 (name, description, phone), category, voice
    p = db.get(BusinessProfile, uuid.UUID(ws))
    assert p.legal_name == "Hansen VVS Aarhus" and p.phone == "86 12 34 56" and p.website_url == "https://fjordgulv.dk/"
    assert "Håndværksvirksomhed" in p.description and p.postal_code == "8000" and p.city == "Aarhus C" and p.version == 2
    assert p.address_line == "Havnevej 12" and p.manual_setup is False
    assert db.query(WorkspaceCategory).filter_by(workspace_id=uuid.UUID(ws)).one().label == "Håndværk & byg"
    assert db.get(WorkspaceVoiceSettings, uuid.UUID(ws)).standard_voice == "peter"
    plan = api.plan(tok, ws)
    assert {t["key"]: t["status"] for t in plan["tasks"]}["business.profile"] == "complete"
    assert {t["key"]: t["status"] for t in plan["tasks"]}["business.categories"] == "complete"
    # knowledge: the crawl became drafts in the new workspace, plus the Google hours – nothing approved
    versions = db.scalars(select(KnowledgeVersion).where(KnowledgeVersion.workspace_id == uuid.UUID(ws))).all()
    assert {v.status for v in versions} == {"draft"} and len(versions) >= 4
    hours = next(v for v in versions if v.source_type == "import")
    assert hours.title == "Åbningstider" and hours.content["weekly"] == [{"days": ["mon", "tue", "wed", "thu", "fri"],
                                                                          "open": "07:00", "close": "16:00"}]
    assert {v.title for v in versions if v.source_type == "extraction"} >= {"Gulvafslibning", "Lakering"}
    assert api.get(tok, f"/workspaces/{ws}/assistant/knowledge").json()["items"] == []
    # the demo call: Peter rings the proven number and knows the company
    assert len(funnel["calls"]) == 1
    payload = funnel["calls"][0]
    assert payload["customer"]["number"] == "+4520304050"
    first = payload["assistant"]["firstMessage"]
    assert first.startswith("Hej Mette, det er Peter fra Dialogbot.") and "Hansen VVS Aarhus" in first
    system = payload["assistant"]["model"]["messages"][0]["content"]
    assert "Håndværk & byg" in system and "Havnevej 12" in system and "mandag: 07.00–16.00" in system
    assert "booke tider, svare på priser" in system and "ca. 7 ubesvarede opkald" in system
    dc = db.query(DemoCall).one()
    assert dc.status == "calling" and dc.company == "Hansen VVS Aarhus" and dc.industry == "haandvaerk" and dc.context
    # the reveal: only with the session of the draft's user
    assert client.get(f"/api/v1/funnel/drafts/{did}/reveal").status_code == 401
    assert api.get(funnel["tok"], f"/funnel/drafts/{did}/reveal").status_code == 404
    rev = api.get(tok, f"/funnel/drafts/{did}/reveal").json()
    assert rev["call"] == {"status": "calling", "outcome": None, "summary": "", "duration_seconds": None, "error": None,
                           "scheduled_for": None}
    assert rev["workspace_id"] == ws and rev["next"] == "/start/klar" and rev["knowledge"]["import"]["status"] == "done"
    # answers are frozen; the code cannot be replayed
    assert client.post(f"/api/v1/funnel/drafts/{did}/verify", json={"code": code}).json()["code"] == "draft_verified"
    assert client.patch(f"/api/v1/funnel/drafts/{did}", json={"step": 3, "answers": {}}).status_code == 409
    # the welcome mail carries a «vælg adgangskode» link that works
    assert db.query(OutboxEvent).filter_by(event_type="email.branded").count() == 1
    raw = api.mailbox_link(tok, "Velkommen", r"password/reset\?token=([A-Za-z0-9_\-]+)")
    r = client.post("/api/v1/auth/password/reset", json={"token": raw, "password": "NyAdgangskode!42"})
    assert r.status_code == 200
    assert api.login("mette@testmail.dk", "NyAdgangskode!42")


def test_erhverv_without_places_hit_and_closed_demo_line(client, api, funnel, db):
    """A name Google does not know: the workspace still gets the name; outside the calling hours the demo call is
    queued for the next opening (S0 «Erhverv døgnåbent») – the sign-up never waits for it."""
    did = client.post("/api/v1/funnel/drafts", json={"kind": "erhverv", "industry": "klinik"}).json()["id"]
    d = _patch(client, did, 2, {"company_name": "Tandlæge Ukendt"})
    assert d["company"]["name"] == "Tandlæge Ukendt" and d["company"]["place_id"] is None and d["build"]["hours"] == "default"
    d = _patch(client, did, 4, {"missed": ["never_free"], "wants": ["book"]})
    assert d["estimate"]["missed_per_week"] == 25 and d["build"]["knowledge"] == "skipped"
    funnel["clock"][0] = MON_22
    _gate(client, did, email="klinik@testmail.dk", phone="21222324")
    out = client.post(f"/api/v1/funnel/drafts/{did}/verify", json={"code": _code()}).json()
    assert out["status"] == "ok" and funnel["calls"] == []
    rev = api.get(out["session_token"], f"/funnel/drafts/{did}/reveal").json()
    # 22:00 Monday: Peter rings Tuesday from 08:00; nothing is refused and nobody is rung at night
    assert rev["call"]["status"] == "scheduled" and rev["call_problem"] is None
    assert rev["call"]["scheduled_for"] == "2026-09-29T06:00:00+00:00"
    assert rev["next"] and rev["workspace_id"] == out["workspace_id"]
    assert db.get(BusinessProfile, uuid.UUID(out["workspace_id"])).legal_name == "Tandlæge Ukendt"
    assert db.get(WorkspaceVoiceSettings, uuid.UUID(out["workspace_id"])).standard_voice == "camilla"


def test_privat_full_path(client, api, funnel, db, pv):
    r = client.post("/api/v1/funnel/drafts", json={"kind": "privat", "hook": "udsat"})
    assert r.status_code == 201
    did = r.json()["id"]
    assert r.json()["build"] == {"tasks": 0, "lists": 0, "first_call": None, "items": []}
    d = _patch(client, did, 1, {"postponed": ["dentist", "gift", "nonsense"], "assistant_name": " ida "})
    assert d["answers"]["postponed"] == ["dentist", "gift", "nonsense"]
    d = _patch(client, did, 2, {"household": "kids"})
    d = _patch(client, did, 3, {"hate_calls": "health"})
    d = _patch(client, did, 4, {"remind_at": "evening"})
    assert d["build"]["tasks"] == 2 and d["build"]["lists"] == 2 and d["build"]["first_call"] == {"title": "Bestil tid hos tandlægen"}
    assert db.query(PrivateTask).count() == 0 and db.query(User).filter_by(email_normalized="mette@testmail.dk").count() == 0
    assert _gate(client, did).status_code == 202
    r = client.post(f"/api/v1/funnel/drafts/{did}/verify", json={"code": _code()})
    out = r.json()
    assert r.status_code == 200, r.text
    assert out["status"] == "ok" and out["next"] == "/privat/konto?plan=plus&velkommen=1" and out["new_user"] is True
    tok = out["session_token"]
    me = api.get(tok, "/privat/me").json()
    assert me["phone_verified"] is True and me["phone_display"] == "20 30 40 50" and me["plan_status"] == "none"
    assert me["assistant_name"] == "Ida"                    # the name chosen on the first screen
    # everything the quiz built waits as drafts until the trial (card first) is in
    tasks = api.get(tok, "/privat/tasks").json()
    assert sorted(t["status"] for t in tasks) == ["awaiting_user", "draft", "draft", "draft"]
    pv.start_trial(tok)
    assert api.get(tok, "/privat/me").json()["plan_status"] == "trial"
    db.expire_all()
    assert db.query(User).filter_by(email_normalized="mette@testmail.dk").one().email_verified_at is None  # phone proof only
    day = api.get(tok, "/privat/day").json()
    call = next(t for t in day["awaiting"] if t["kind"] == "call")
    assert call["status"] == "awaiting_user" and "tandlægen" in call["title"] and call["call"]["phone_display"] == ""
    tasks = api.get(tok, "/privat/tasks").json()
    kinds = sorted((t["kind"], t["title"]) for t in tasks)
    assert kinds == [("call", "Bestil en tid til eftersyn hos tandlægen"), ("list", "Indkøbsliste"), ("list", "Pakkeliste"),
                     ("reminder", "Køb gaven")]
    rem = next(t for t in tasks if t["kind"] == "reminder")
    assert rem["status"] == "planned" and rem["remind_at"] == "2026-11-05T18:00:00+00:00"  # tomorrow 19:00 Copenhagen
    assert rem["usage_text"] == "Med i prøveperioden"
    assert next(t for t in tasks if t["title"] == "Pakkeliste")["status"] == "in_progress"
    assert [i["text"] for i in next(t for t in tasks if t["title"] == "Indkøbsliste")["items"]] == ["Mælk", "Brød", "Frugt", "Madpakkepålæg"]
    msgs = api.get(tok, "/privat/messages").json()
    assert any(m["kind"] == "call_proposal" and "Skriv nummeret her" in m["text"] for m in msgs)
    # «Hvad er deres nummer?» works exactly as in the chat
    r = api.post(tok, "/privat/messages", {"text": "86 12 34 56", "about_task_id": call["id"]})
    assert r.status_code == 200 and api.get(tok, f"/privat/tasks/{call['id']}").json()["call"]["phone_display"] == "86 12 34 56"
    assert api.get(tok, f"/funnel/drafts/{did}/reveal").json()["workspace_id"] == out["workspace_id"]
    assert funnel["calls"] == []  # nothing was dialled


def test_honeypot_sends_nothing(client, funnel, db):
    did = client.post("/api/v1/funnel/drafts", json={"kind": "privat"}).json()["id"]
    r = _gate(client, did, website="http://spam")
    assert r.status_code == 202 and r.json() == {"status": "code_sent", "phone_display": None}
    assert WORLD.sms == [] and db.get(FunnelDraft, uuid.UUID(did)).gate is None
    # and the real gate validates
    assert _gate(client, did, consent=False).status_code == 422
    assert _gate(client, did, phone="+46701234567").status_code == 422
    assert _gate(client, did, email="not-an-email").status_code == 422


def test_rate_limit_per_ip(client, funnel, monkeypatch):
    monkeypatch.setitem(limits.LIMITS, "create", (3, 1000))
    for _ in range(3):
        assert client.post("/api/v1/funnel/drafts", json={"kind": "privat"}).status_code == 201
    r = client.post("/api/v1/funnel/drafts", json={"kind": "privat"})
    assert r.status_code == 429 and r.json()["code"] == "rate_limited"
    # another address is not affected
    assert client.post("/api/v1/funnel/drafts", json={"kind": "privat"}, headers={"x-forwarded-for": "203.0.113.9"}).status_code == 201


@pytest.mark.parametrize("kind", ["privat", "erhverv"])
def test_existing_email_is_never_logged_in_by_a_funnel_code(client, api, funnel, db, kind):
    """F-P2-01-X04 (S0): the SMS code proves only the number typed at the gate, not the account behind the typed
    e-mail. verify must refuse with 409 account_exists: no session, nothing on the account changes, no workspace,
    no private account, the draft stays unclaimed – the owner logs in the ordinary way."""
    from app.models import Membership, PrivateProfile
    from app.models import Session as UserSession

    api.user("mette@testmail.dk")
    db.expire_all()
    victim = db.query(User).filter_by(email_normalized="mette@testmail.dk").one()
    before = (victim.phone_verified_at, victim.display_name, victim.password_hash, victim.signup_source)
    sessions = db.query(UserSession).filter_by(user_id=victim.id).count()
    memberships = db.query(Membership).filter_by(user_id=victim.id).count()
    did = client.post("/api/v1/funnel/drafts", json={"kind": kind}).json()["id"]
    assert _gate(client, did, name="Attacker", phone="29 87 65 43").status_code == 202
    assert WORLD.sms[-1]["to"] == "+4529876543"
    r = client.post(f"/api/v1/funnel/drafts/{did}/verify", json={"code": _code()})
    assert r.status_code == 409 and r.json()["code"] == "account_exists", r.text
    assert "session_token" not in r.json() and "set-cookie" not in {k.lower() for k in r.headers}
    db.expire_all()
    v = db.get(User, victim.id)
    assert (v.phone_verified_at, v.display_name, v.password_hash, v.signup_source) == before
    assert db.query(UserSession).filter_by(user_id=victim.id).count() == sessions
    assert db.query(Membership).filter_by(user_id=victim.id).count() == memberships
    assert db.query(PrivateProfile).filter_by(user_id=victim.id).count() == 0
    d = db.get(FunnelDraft, uuid.UUID(did))
    assert d.user_id is None and d.workspace_id is None and "verified_at" not in (d.gate or {})
    assert db.scalars(select(AuditLog).where(AuditLog.action == "user.funnel_login")).all() == []
    audit = db.scalars(select(AuditLog).where(AuditLog.action == "funnel.account_exists")).one()
    assert audit.actor_user_id is None and audit.after["user_id"] == str(victim.id) and audit.after["phone"] == "+4529876543"
    assert db.query(OutboxEvent).filter_by(event_type="email.branded").count() == 0
    # the code is used up: a replay is not a second try
    again = client.post(f"/api/v1/funnel/drafts/{did}/verify", json={"code": "000000"})
    assert again.status_code == 409 and again.json()["code"] == "code_expired"


def test_expiry_and_cleanup(client, funnel, db, monkeypatch):
    old = client.post("/api/v1/funnel/drafts", json={"kind": "erhverv"}).json()["id"]
    fresh = client.post("/api/v1/funnel/drafts", json={"kind": "privat"}).json()["id"]
    _gate(client, fresh)
    done = client.post(f"/api/v1/funnel/drafts/{fresh}/verify", json={"code": _code()}).json()
    assert done["status"] == "ok"
    row = db.get(FunnelDraft, uuid.UUID(old))
    row.expires_at = datetime.now(UTC) - timedelta(minutes=1)
    db.commit()
    r = client.get(f"/api/v1/funnel/drafts/{old}")
    assert r.status_code == 404 and r.json()["code"] == "draft_expired"
    assert client.patch(f"/api/v1/funnel/drafts/{old}", json={"step": 2, "answers": {}}).status_code == 404
    # the worker's scheduled pass deletes it; a verified draft stays
    with get_session_factory()() as s:
        assert service.purge_expired(s) == 1
    db.expire_all()
    assert db.get(FunnelDraft, uuid.UUID(old)) is None
    assert db.get(FunnelDraft, uuid.UUID(fresh)).user_id is not None
    runner.run_schedules()  # the pass itself runs without error
    assert client.get("/api/v1/funnel/drafts/" + str(uuid.uuid4())).json()["code"] == "draft_not_found"
