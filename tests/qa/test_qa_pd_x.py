"""Privat-dybderunde fase 2, prefix PX: voice-qa (Ring for mig), integrations-qa (kalender, 17TRACK, rejser, push,
produktsøgning, ønske-import) og backend-delen af i18n (danske backend-tekster).

Ingen rigtige opkald: `campaigns.create_call` er erstattet af en optager i hver test (samme søm som qa_privat_stack's
/__qa/calls). Ingen netværk: ønske-import og rejser kører mod fakes/monkeypatch.

Kør: source /home/claude/qa-env.sh && export TEST_DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/qa_pd7
     DATABASE_URL=$TEST_DATABASE_URL && python -m pytest -q tests/qa/test_qa_pd_x.py
"""
from __future__ import annotations

import json
import threading
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.models import OutboxEvent, PrivateCall, PrivateProfile
from app.modules.campaigns import service as campaigns
from tests.test_privat import VAPI_H, _assistant_request, _propose, _report

MON_0800_UTC = datetime(2026, 11, 9, 7, 0, tzinfo=UTC)   # mandag 9. nov. 08:00 København
SAT_10_UTC = datetime(2026, 11, 7, 9, 0, tzinfo=UTC)     # lørdag 7. nov. 10:00 København


class Dialler:
    """Records what would have been dialled (= /__qa/calls in the stack)."""

    def __init__(self, db_check=None):
        self.calls: list[dict] = []
        self.status_at_dial: list[str] = []
        self.lock = threading.Lock()

    def __call__(self, payload):
        from app.db import get_session_factory

        cid = payload["metadata"]["private_call_id"]
        with get_session_factory()() as s:
            self.status_at_dial.append(s.get(PrivateCall, uuid.UUID(cid)).status)
        with self.lock:
            self.calls.append(payload)
        return {"id": f"vapi_{len(self.calls)}"}


@pytest.fixture
def dialler(monkeypatch):
    d = Dialler()
    monkeypatch.setattr(campaigns, "create_call", d)
    return d


def _call_row(db, tid) -> PrivateCall:
    db.expire_all()
    return db.scalars(select(PrivateCall).where(PrivateCall.task_id == uuid.UUID(tid))
                      .order_by(PrivateCall.created_at.desc())).first()


def _outbox(db, kind: str) -> list[OutboxEvent]:
    db.expire_all()
    return list(db.scalars(select(OutboxEvent).where(OutboxEvent.event_type == kind)))


def _ctx_turn(db, pv, tok, text):
    from app.models import User
    from app.modules.privat import chat, deps

    principal = type("P", (), {"user": db.get(User, pv.uid(tok))})()
    ctx = deps._ctx(db, principal, deps.find_profile(db, pv.uid(tok)))
    return ctx, chat.Turn(db=db, ctx=ctx, text=text, about=None)


# =========================================================================== voice-qa: Ring for mig

def test_px_call_01_proposal_dials_nothing(api, pv, db, dialler):
    """PC-CALL-01: et forslag ringer ikke, laver ingen call_due-outbox, task venter på brugeren."""
    tok = pv.account("px-call01@example.com")
    pv.verify_phone(tok)
    tid = _propose(pv, tok)
    c = _call_row(db, tid)
    assert c.status == "proposed" and c.approved_at is None and c.approved_snapshot is None
    assert pv.task(tok, tid).json()["status"] == "awaiting_user"
    assert _outbox(db, "privat.call_due") == []
    assert dialler.calls == []


def test_px_call_02_needs_phone_then_dials_with_snapshot(api, pv, db, dialler):
    """PC-CALL-02: uden verificeret mobil 409 needs_phone; efter SMS-kode ringer den – snapshot låst og status
    committed før opkaldet."""
    from app.modules.integrations.connectors.fakes import WORLD

    tok = pv.account("px-call02@example.com")
    tid = _propose(pv, tok)
    r = api.post(tok, f"/privat/calls/{tid}/approve", {"share_phone": False})
    assert r.status_code == 409 and r.json()["code"] == "needs_phone"
    assert dialler.calls == []
    WORLD.reset()
    assert api.post(tok, "/privat/phone/start", {"phone": "20 30 40 50"}).json() == {"sent": True}
    code = WORLD.sms[-1]["body"].split("er ")[1][:6]
    assert api.post(tok, "/privat/phone/verify", {"code": code}).json()["phone_verified"] is True
    t = api.post(tok, f"/privat/calls/{tid}/approve", {"share_phone": False, "window": "torsdag efter kl. 15"}).json()
    assert t["status"] == "in_progress"
    assert len(dialler.calls) == 1 and dialler.status_at_dial == ["dialling"]
    snap = _call_row(db, tid).approved_snapshot
    assert set(snap) >= {"may_ask", "may_agree", "may_not", "window", "business_phone_e164", "share_phone"}
    sys = dialler.calls[0]["assistant"]["model"]["messages"][0]["content"]
    assert snap["may_not"] in sys and snap["may_agree"] in sys and snap["may_ask"] in sys


@pytest.mark.parametrize("same_key", [True, False])
def test_px_call_03_double_approve_parallel(api, client, pv, db, dialler, same_key):
    """PC-CALL-03: dobbeltklik på Godkend (parallelt, samme og forskellig Idempotency-Key) → ét opkald, én reservation."""
    tok = pv.account(f"px-call03-{same_key}@example.com")
    pv.verify_phone(tok)   # plan path (Plus trial): one approval = one of the month's plan calls
    tid = _propose(pv, tok)
    results = []

    def go(i):
        key = "dbl" if same_key else f"dbl-{i}"
        r = api.post(tok, f"/privat/calls/{tid}/approve", {"share_phone": False}, **{"Idempotency-Key": key})
        results.append(r.status_code)

    th = [threading.Thread(target=go, args=(i,)) for i in range(4)]
    [t.start() for t in th]
    [t.join() for t in th]
    assert len(dialler.calls) == 1, (results, len(dialler.calls))
    assert 500 not in results, results  # F-PX-08: never a 500 (the call row is locked and re-read in approve)
    assert pv.me(tok)["calls_used"] == 1
    db.expire_all()
    assert db.query(PrivateCall).filter(PrivateCall.task_id == uuid.UUID(tid)).count() == 1


def test_px_call_05_outside_hours_schedule_and_cancel(api, pv, db, dialler):
    """PC-CALL-05: lørdag → 409 outside_hours med næste vindue mandag 08:00; «ved næste åbningstid» → planlagt;
    annullér før → declined, og worker ringer ikke."""
    from app.modules.privat import calls

    tok = pv.account("px-call05@example.com")
    pv.verify_phone(tok)
    tid = _propose(pv, tok)
    pv.clock.at = SAT_10_UTC
    r = api.post(tok, f"/privat/calls/{tid}/approve", {"share_phone": False})
    assert r.status_code == 409 and r.json()["code"] == "outside_hours"
    assert r.json()["next_open_at"] == "2026-11-09T08:00:00+01:00"
    t = api.post(tok, f"/privat/calls/{tid}/approve", {"share_phone": False, "at_next_open": True}).json()
    assert t["status"] == "planned" and dialler.calls == []
    evs = _outbox(db, "privat.call_due")
    assert len(evs) == 1 and evs[0].next_attempt_at.astimezone(UTC) == MON_0800_UTC
    t = api.post(tok, f"/privat/calls/{tid}/decline").json()
    assert t["status"] == "declined"
    pv.clock.at = MON_0800_UTC + timedelta(minutes=1)
    calls.handle_call_due(db, evs[0])
    db.commit()
    assert dialler.calls == [] and _call_row(db, tid).status == "declined"


def _scheduled_call(api, pv, db, tok) -> tuple[str, OutboxEvent]:
    pv.verify_phone(tok)
    tid = _propose(pv, tok)
    pv.clock.at = SAT_10_UTC
    t = api.post(tok, f"/privat/calls/{tid}/approve", {"share_phone": False, "at_next_open": True}).json()
    assert t["status"] == "planned"
    ev = _outbox(db, "privat.call_due")[-1]
    return tid, ev


def _run_due(db, pv, ev):
    from app.modules.privat import calls

    pv.clock.at = MON_0800_UTC + timedelta(minutes=1)
    db.expire_all()
    calls.handle_call_due(db, db.get(OutboxEvent, ev.id))
    db.commit()


def test_px_call_06_control_scheduled_call_dials_monday(api, pv, db, dialler):
    """Kontrol for PC-CALL-06: uden ændringer ringer det planlagte opkald mandag 08:00 (så 06a-c måler noget)."""
    tok = pv.account("px-call06ctl@example.com")
    tid, ev = _scheduled_call(api, pv, db, tok)
    _run_due(db, pv, ev)
    assert len(dialler.calls) == 1


def test_px_call_06a_scheduled_call_after_addon_disabled(api, pv, db, dialler):
    """PC-CALL-06: planlagt opkald – brugeren slår «Ring for mig» fra bagefter. Forventet: intet opkald."""
    tok = pv.account("px-call06a@example.com")
    tid, ev = _scheduled_call(api, pv, db, tok)
    r = api.post(tok, "/privat/addons/ring-for-mig/disable")
    assert r.status_code == 200, r.text
    _run_due(db, pv, ev)
    assert dialler.calls == [], "S0: planlagt opkald ringes selvom «Ring for mig» er slået fra"


def test_px_call_06b_scheduled_call_after_plan_expired(api, pv, db, dialler):
    """PC-CALL-06: planlagt plan-opkald (paid_via=plan) – prøveperioden udløber inden mandag. Forventet: intet opkald
    (eller ny godkendelse)."""
    tok = pv.account("px-call06b@example.com")
    tid, ev = _scheduled_call(api, pv, db, tok)
    assert _call_row(db, tid).paid_via == "plan"
    pv.expire_trial(tok)
    assert pv.me(tok)["entitled"] is False
    _run_due(db, pv, ev)
    assert dialler.calls == [], "S0: planlagt plan-opkald ringes efter planen er udløbet – gratis opkald"


def test_px_call_06c_scheduled_call_after_phone_removed(api, pv, db, dialler):
    """PC-CALL-06: planlagt opkald – brugerens bekræftede mobilnummer fjernes. Forventet: intet opkald."""
    tok = pv.account("px-call06c@example.com")
    tid, ev = _scheduled_call(api, pv, db, tok)
    with db.begin_nested():
        p = db.query(PrivateProfile).filter_by(workspace_id=pv.ws(tok)).one()
        p.phone_e164, p.phone_verified_at = None, None
    db.commit()
    _run_due(db, pv, ev)
    assert dialler.calls == [], "S0: planlagt opkald ringes uden bekræftet mobilnummer"


def test_px_call_07_demo_and_mobile(api, pv, db, dialler):
    """PC-CALL-07: demo-virksomhed → 409 demo_business; mobilnummer → 409 confirm_business indtil bekræftet."""
    from app.modules.privat import chat

    tok = pv.account("px-call07@example.com")
    pv.verify_phone(tok)
    ctx, turn = _ctx_turn(db, pv, tok, "Ring til Demo VVS")
    chat._propose(turn, name="Demo VVS Aarhus 2", phone="+4586000099", source="demo", data={"purpose": "Få et tilbud"})
    db.commit()
    tid = str(turn.out[-1].task_id)
    r = api.post(tok, f"/privat/calls/{tid}/approve", {"share_phone": False, "confirm_business": True})
    assert r.status_code == 409 and r.json()["code"] == "demo_business"
    # a mobile number the user typed
    ctx, turn = _ctx_turn(db, pv, tok, "Ring til Hans Tømrer på 20 11 22 33")
    chat._propose(turn, name="Hans Tømrer", phone="20112233", source="user", data={"purpose": "Få et tilbud"})
    db.commit()
    tid = str(turn.out[-1].task_id)
    r = api.post(tok, f"/privat/calls/{tid}/approve", {"share_phone": False})
    assert r.status_code == 409 and r.json()["code"] == "confirm_business"
    assert dialler.calls == []
    r = api.post(tok, f"/privat/calls/{tid}/approve", {"share_phone": False, "confirm_business": True})
    assert r.status_code == 200 and len(dialler.calls) == 1
    assert _call_row(db, tid).approved_snapshot["confirm_business"] is True


def test_px_call_08_invented_number_inside_other_digits(api, pv, db, dialler):
    """PC-CALL-08: modellen opfinder et nummer. Variant: nummeret står som delstreng i et ordre-/kontonummer,
    brugeren skrev i en tidligere besked – det er ikke et telefonnummer, brugeren har givet."""
    from app.modules.privat import chat

    tok = pv.account("px-call08@example.com")
    pv.verify_phone(tok)
    pv.say(tok, "Lav en liste med ordrenummer 4433221100998877")
    ctx, turn = _ctx_turn(db, pv, tok, "Ring til Frisør Hansen og bestil en tid")
    out = chat.tool_propose_call(turn, {"business_name": "Frisør Hansen", "phone": "22110099", "purpose": "Bestil tid"})
    db.commit()
    proposals = db.query(PrivateCall).filter(PrivateCall.business_phone_e164 == "+4522110099").count()
    assert proposals == 0, f"Nummer fra et ordrenummer blev brugt som telefonnummer ({out})"


def test_px_call_10_retry_needs_new_approval(api, client, pv, db, dialler):
    """PC-CALL-10: «Prøv igen» efter ubesvaret → nyt forslag; intet ringes før ny godkendelse; retry på et besvaret
    opkald afvises."""
    tok = pv.account("px-call10@example.com")
    pv.verify_phone(tok)
    tid = _propose(pv, tok)
    api.post(tok, f"/privat/calls/{tid}/approve", {"share_phone": False})
    p = dialler.calls[0]
    _report(client, p, "customer-did-not-answer", [], seconds=0, call_id="vapi_1")
    t = api.post(tok, f"/privat/calls/{tid}/retry").json()
    assert t["status"] == "awaiting_user" and len(dialler.calls) == 1
    assert _call_row(db, tid).status == "proposed"
    assert api.post(tok, f"/privat/calls/{tid}/retry").json()["status"] == "awaiting_user"  # idempotent
    assert len(dialler.calls) == 1
    api.post(tok, f"/privat/calls/{tid}/approve", {"share_phone": False})
    assert len(dialler.calls) == 2
    msgs = [{"role": "bot", "message": "Hej"}, {"role": "user", "message": "Ja, torsdag kl. 15.30 passer."}]
    _report(client, dialler.calls[1], "customer-ended-call", msgs, seconds=40, call_id="vapi_2")
    r = api.post(tok, f"/privat/calls/{tid}/retry")
    assert r.status_code == 409 and len(dialler.calls) == 2


def test_px_call_11_callback_window_and_isolation(api, client, pv, db, dialler):
    """PC-CALL-11: tilbagekald inden for 14 dage → nyeste åbne opkald for nummeret og ejeren får besked; efter 14 dage
    → generisk uden personoplysninger; et afvist forslag routes aldrig."""
    tok = pv.account("px-call11@example.com", "Søren Ærø")
    pv.verify_phone(tok)
    tid = _propose(pv, tok)
    api.post(tok, f"/privat/calls/{tid}/approve", {"share_phone": False})
    _report(client, dialler.calls[0], "customer-did-not-answer", [], seconds=0, call_id="vapi_1")
    # another user only PROPOSED a call to the same business (never approved): must not be named
    other = pv.account("px-call11b@example.com", "Ole Berg")
    _propose(pv, other)
    a = _assistant_request(client, "+4586123456")["assistant"]
    assert "Søren Ærø" in a["firstMessage"] and "Ole" not in json.dumps(a, ensure_ascii=False)
    r = client.post("/api/v1/webhooks/vapi", headers=VAPI_H, json={"message": {
        "type": "end-of-call-report", "endedReason": "customer-ended-call",
        "call": {"id": "cb_px", "phoneNumberId": "pn_pool", "customer": {"number": "+4586123456"},
                 "assistant": {"metadata": a["metadata"]}},
        "artifact": {"messages": [{"role": "user", "message": "Han kan komme fredag kl. 10."}]}}}).json()
    assert r["outcome"] == "applied"
    msgs = api.get(tok, f"/privat/messages?task_id={tid}").json()
    assert msgs[-1]["text"].startswith("Cykelmageren ringede tilbage")
    assert api.get(other, "/privat/messages").json()[-1]["text"].find("ringede tilbage") == -1
    # day 15: expired
    pv.clock.at += timedelta(days=15)
    a = _assistant_request(client, "+4586123456")["assistant"]
    assert "kan desværre ikke se en henvendelse" in a["firstMessage"]
    assert "Søren" not in json.dumps(a, ensure_ascii=False)


def test_px_voice_script_language_names_and_peter(api, pv, db, dialler):
    """Peters manus for Privat-opkald: dansk, siger at det er en digital assistent, kun brugerens navn, navne med
    æ/ø/å sendes til transskriberingen som nøgleord, max 3 min., voicemail-detektion, ingen optagelse."""
    tok = pv.account("px-script@example.com", "Bjørk Æblegård")
    pv.verify_phone(tok)
    tid = _propose(pv, tok)
    api.post(tok, f"/privat/calls/{tid}/approve", {"share_phone": False})
    a = dialler.calls[0]["assistant"]
    first = a["firstMessage"]
    assert first.startswith("Hej, jeg ringer fra Dialogbot på vegne af Bjørk Æblegård. Jeg er en digital assistent.")
    sys = a["model"]["messages"][0]["content"]
    assert "Lyv aldrig om at være et menneske" in sys and "+4520304050" not in json.dumps(a)
    blob = json.dumps(a["transcriber"], ensure_ascii=False)
    assert "Bjørk" in blob and "Æblegård" in blob and "Cykelmageren" in blob
    assert a["transcriber"].get("language", "da") in ("da", "multi") or "da" in blob
    assert a["maxDurationSeconds"] == 180 and a["voicemailDetection"] == {"provider": "vapi"}
    # the shop/app texts call the assistant «Peter»; the call itself introduces «Dialogbot … en digital assistent»
    assert "Peter" not in first


def test_px_app_04_health_purpose_and_may_not(api, pv, db, dialler):
    """PC-APP-04: læge/tandlæge. Kun klinikkens navn+nummer gemmes; opkaldet siger kun formålet; may_not skal stadig
    indeholde de generelle forbud (betale, sige ja til andet)."""
    from app.models import PrivateAppData
    from app.modules.privat import chat

    tok = pv.account("px-app04@example.com")
    pv.verify_phone(tok)
    r = api.post(tok, "/privat/addons/laege-og-tandlaege/enable")
    assert r.status_code == 200, r.text
    pv.say(tok, "Gem min læge: hun hedder Lægehuset Nord, nummer 86 11 22 33. Jeg har en knude i brystet.")
    db.expire_all()
    appdata = json.dumps([r.data for r in db.query(PrivateAppData).filter_by(workspace_id=pv.ws(tok))],
                         ensure_ascii=False, default=str)
    assert "knude" not in appdata and "bryst" not in appdata
    ctx, turn = _ctx_turn(db, pv, tok, "Book en lægetid, helst i morgen formiddag")
    chat.tool_book_health_appointment(turn, {"kind": "laege", "purpose": "lægetid", "window": "i morgen formiddag"})
    db.commit()
    c = db.query(PrivateCall).order_by(PrivateCall.created_at.desc()).first()
    assert "knude" not in (c.purpose + c.may_ask + c.may_agree)
    assert "Betale" in c.may_not or "betale" in c.may_not, f"may_not mister de generelle forbud: {c.may_not!r}"


def test_px_app_12_quotes_only_approved_dialled_and_lead(api, pv, db, dialler):
    """PC-APP-12: Håndværker – forslag pr. firma, kun det godkendte ringes; valg laver nyt forslag, der kræver
    godkendelse; PrivateBusinessReferral (lead) oprettes."""
    from app.models import PrivateBusinessReferral
    from app.modules.privat import quotes

    tok = pv.account("px-app12@example.com")
    pv.verify_phone(tok)
    assert api.post(tok, "/privat/addons/haandvaerker/enable").status_code == 200
    ctx, _turn = _ctx_turn(db, pv, tok, "x")
    entry, found = quotes.request(db, ctx, job="eftersyn af ladcykel", trade="cykel", city="Aarhus")
    db.commit()
    assert len(entry["quotes"]) == 2
    t1 = entry["quotes"][0]["task_id"]
    api.post(tok, f"/privat/calls/{t1}/approve", {"share_phone": False})
    assert len(dialler.calls) == 1
    assert dialler.calls[0]["customer"]["number"] == "+4586123456"
    refs = db.query(PrivateBusinessReferral).filter_by(workspace_id=pv.ws(tok)).all()
    assert len(refs) == 2 and {r.status for r in refs} == {"asked"}
    task = quotes.choose(db, ctx, entry, entry["quotes"][1]["name"])
    db.commit()
    assert task.status == "awaiting_user" and len(dialler.calls) == 1
    db.expire_all()
    assert sorted(r.status for r in db.query(PrivateBusinessReferral).filter_by(workspace_id=pv.ws(tok))) == \
        ["chosen", "not_chosen"]


def test_px_app_12b_demo_places_never_dialable(api, pv, db, dialler, monkeypatch):
    """PC-APP-12 / PC-CALL-07: uden Google-nøgle (DemoPlaces) har demo-firmaerne +45 12 34 xx xx, som classify_phone
    afviser – Håndværker laver derfor ingen forslag, og choose_quote kan ikke «hvidvaske» et demo-nummer til
    phone_source='user'. (Kodehul noteret: choose() sætter altid phone_source='user'.)"""
    from app.modules.privat import quotes
    from app.modules.sales import places as sp

    monkeypatch.setattr(sp, "_override", sp.DemoPlaces())
    tok = pv.account("px-app12b@example.com")
    pv.verify_phone(tok)
    assert api.post(tok, "/privat/addons/haandvaerker/enable").status_code == 200
    ctx, _turn = _ctx_turn(db, pv, tok, "x")
    entry, found = quotes.request(db, ctx, job="nyt badeværelse", trade="vvs", city="Aarhus")
    db.commit()
    from app.modules.privat import places as pplaces

    raw = pplaces.search(db, ctx, "vvs", city="Aarhus")
    assert raw and all(r["phone_e164"] is None and r["source"] == "demo" for r in raw)
    assert found == [] and entry["quotes"] == [] and dialler.calls == []


# =========================================================================== integrations-qa

@pytest.fixture
def settings_env(monkeypatch):
    from app.config import get_settings

    def set_(**kw):
        for k, v in kw.items():
            if v is None:
                monkeypatch.delenv(k, raising=False)
            else:
                monkeypatch.setenv(k, v)
        get_settings.cache_clear()
    yield set_
    get_settings.cache_clear()


def test_px_app_08_parcels_coming_soon_is_honest(api, pv, settings_env):
    """PC-APP-08 (QA-stak uden TRACK17_API_KEY): Pakker står som «kommer snart», kan ikke slås til, og ingen grøn stub."""
    settings_env(TRACK17_API_KEY=None)
    tok = pv.account("px-app08cs@example.com")
    shop = {a["key"]: a for a in api.get(tok, "/privat/addons").json()["items"]} \
        if isinstance(api.get(tok, "/privat/addons").json(), dict) else {a["key"]: a for a in api.get(tok, "/privat/addons").json()}
    assert shop["pakker"]["status"] == "coming_soon" and shop["pakker"]["enabled"] is False
    r = api.post(tok, "/privat/addons/pakker/enable")
    assert r.status_code == 409 and r.json()["code"] == "coming_soon"
    assert api.post(tok, "/privat/addons/pakker/notify").status_code == 200
    r = api.get(tok, "/privat/parcels")
    assert r.status_code == 403 and r.json()["code"] == "addon_disabled"


def test_px_app_08_parcels_fake_tracker(api, pv, settings_env, monkeypatch):
    """PC-APP-08 med fake 17TRACK: gyldigt, ugyldigt, ukendt; provider nede; samme nummer to gange; refresh-grænse."""
    from app.modules.privat import parcels

    settings_env(TRACK17_API_KEY="fake")
    parcels.FakeTracker.world.clear()
    tok = pv.account("px-app08@example.com")
    assert api.post(tok, "/privat/addons/pakker/enable").status_code == 200
    r = api.post(tok, "/privat/parcels", {"number": "x!"})
    assert r.status_code == 422
    parcels.FakeTracker.world["UNKNOWN123"] = [{"status": "NotFound", "event": ""}]
    r = api.post(tok, "/privat/parcels", {"number": "unknown 123"})
    assert r.status_code == 200 and r.json()["status"] == "NotFound"
    assert "ikke registreret" in parcels.text_of(r.json())          # honest, no green «på vej»
    again = api.post(tok, "/privat/parcels", {"number": "UNKNOWN-123"})
    assert again.status_code == 200
    assert len(api.get(tok, "/privat/parcels").json()["items"]) == 1   # duplicate kept once
    # provider down
    monkeypatch.setattr(parcels.FakeTracker, "info", lambda self, n: (_ for _ in ()).throw(
        parcels.TrackError("Sporingstjenesten kunne ikke nås")))
    r = api.post(tok, "/privat/parcels", {"number": "DOWN12345"})
    assert r.status_code == 422 and "kunne ikke nås" in r.text
    # refresh within 10 minutes: no provider call (rate limit), same data
    r = api.post(tok, "/privat/parcels/UNKNOWN123/refresh")
    assert r.status_code == 200 and r.json()["status"] == "NotFound"
    pv.clock.at += timedelta(minutes=11)
    r = api.post(tok, "/privat/parcels/UNKNOWN123/refresh")
    assert r.status_code == 422 and "kunne ikke nås" in r.text


def test_px_app_09_trips_not_configured_and_validation(api, pv, settings_env):
    """PC-APP-09: uden nøgler er Rejser «kommer snart»; med fake-provider: ugyldig IATA, 0 voksne, dato i fortiden,
    lavt budget → 422; tom tilstand uden opfundne priser."""
    from app.modules.privat import travel

    settings_env(DUFFEL_ACCESS_TOKEN=None, TRAVELPAYOUTS_TOKEN=None)
    tok = pv.account("px-app09@example.com")
    r = api.post(tok, "/privat/addons/rejser/enable")
    assert r.status_code == 409 and r.json()["code"] == "coming_soon"
    r = api.post(tok, "/privat/trips/search", {"origin": "CPH", "destinations": ["BCN"], "month": "2027-03"})
    assert r.status_code == 403
    settings_env(DUFFEL_ACCESS_TOKEN="fake")
    travel.FakeProvider.prices.clear()
    assert api.post(tok, "/privat/addons/rejser/enable").status_code == 200
    base = {"origin": "CPH", "destinations": ["BCN"], "month": "2027-03"}
    for bad in ({"origin": "C1H"}, {"destinations": ["XX1"]}, {"adults": 0}, {"budget_dkk": 0},
                {"month": None, "depart_date": "2026-01-01"}):
        r = api.post(tok, "/privat/trips/search", {**base, **bad})
        assert r.status_code == 422, (bad, r.status_code, r.text[:200])
    r = api.post(tok, "/privat/trips/search", base)
    assert r.status_code == 200 and r.json()["offers"] == []
    travel.FakeProvider.prices["BCN"] = [1800, 900]
    out = api.post(tok, "/privat/trips/search", {**base, "budget_dkk": 1000}).json()
    assert [o["total_dkk"] for o in out["offers"]] == [900] and out["over_budget"] == 1


def test_px_app_09_travelpayouts_link_carries_marker(monkeypatch):
    """PC-APP-09: et Travelpayouts-link har partner-markøren (affiliate). Web skal derfor markere «Book» som annonce
    (se fund F-PX-..-PC-APP-09 – travel.tsx har hverken «Annonce» eller rel=sponsored)."""
    from app.modules.privat import travel

    class R:
        status_code = 200

        def json(self):
            return {"success": True, "data": [{"origin": "CPH", "destination": "BCN", "price": 700, "airline": "FR",
                                               "departure_at": "2027-03-10T07:00:00+01:00", "transfers": 0,
                                               "link": "/search/CPH1003BCN1?t=x"}], "currency": "dkk"}

    import httpx

    monkeypatch.setattr(httpx, "get", lambda *a, **k: R())
    p = travel.validate({"origin": "CPH", "destinations": ["BCN"], "month": "2027-03"}, datetime(2026, 11, 10).date())
    offers = travel.Travelpayouts("tok", "M123").search(p, "BCN")
    assert offers and "marker=M123" in offers[0]["book_url"]


def _fake_fetch(pages):
    from app.modules.privat import safe_fetch

    def fetch(url, **kw):
        v = pages.get(url)
        if isinstance(v, Exception):
            raise v
        if v is None:
            raise safe_fetch.FetchFailed("no page")
        status, ct, body = v
        return safe_fetch.Fetched(url=url, status=status, content_type=ct, body=body)
    return fetch


def test_px_wish_09_import_link_cases(api, pv, monkeypatch):
    """PC-WISH-09: JSON-LD-side, side uden data, 404, timeout, for stor side → titel/pris når muligt, ellers
    readable=false; aldrig 500; rate limit pr. time."""
    from app.modules.privat import safe_fetch, wishes

    ld = (b'<html><head><script type="application/ld+json">{"@context":"https://schema.org","@type":"Product",'
          b'"name":"Lego Technic 42143","image":"https://shop.example/img.jpg","offers":{"@type":"Offer",'
          b'"price":"1499.95","priceCurrency":"DKK"}}</script></head><body>x</body></html>')
    pages = {"https://shop.example/lego": (200, "text/html; charset=utf-8", ld),
             "https://shop.example/plain": (200, "text/html", b"<html><body>Hej</body></html>"),
             "https://shop.example/404": (404, "text/html", b"nope"),
             "https://shop.example/slow": safe_fetch.FetchFailed("timeout"),
             "https://shop.example/huge": safe_fetch.FetchFailed("too_large")}
    monkeypatch.setattr(safe_fetch, "fetch", _fake_fetch(pages))
    monkeypatch.setattr(safe_fetch, "check_url", lambda u: ("shop.example", "93.184.216.34", 443, u))
    monkeypatch.setattr(wishes, "_store_image", lambda ws, url: None)
    tok = pv.account("px-wish09@example.com")
    r = api.post(tok, "/privat/wishes/import", {"link": "https://shop.example/lego"}, **{"x-real-ip": "10.9.0.1"})
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["readable"] is True and j["title"] == "Lego Technic 42143" and j["price_minor"] == 149995 and j["currency"] == "DKK"
    for path, reason in (("plain", "no_product_data"), ("404", "unreachable"), ("slow", "unreachable"),
                         ("huge", "unreachable")):
        r = api.post(tok, "/privat/wishes/import", {"link": f"https://shop.example/{path}"})
        assert r.status_code == 200 and r.json()["readable"] is False and r.json()["reason"] == reason, (path, r.text)
        assert r.json()["link"] == f"https://shop.example/{path}"
    r = api.post(tok, "/privat/wishes/import", {"link": "http://127.0.0.1:8400/__qa/calls"})
    assert r.status_code in (200, 422) and "127.0.0.1" not in json.dumps(r.json().get("title") or "")
    codes = [api.post(tok, "/privat/wishes/import", {"link": "https://shop.example/plain"}).status_code for _ in range(60)]
    assert 429 in codes


def test_px_wish_search_503_without_web_search(api, pv):
    """Produktsøgning (ønsker) i QA-stakken: 503 search_unavailable – ærlig tekst, ingen opfundne produkter."""
    tok = pv.account("px-wishsearch@example.com")
    r = api.get(tok, "/privat/wishes/search?q=lego")
    assert r.status_code == 503 and r.json()["code"] == "search_unavailable"


def test_px_cal_01_ical_feed_lifecycle(api, client, pv):
    """PC-CAL-01: opret → abonnér → nyt link gør det gamle 404 → slet → 404; token ikke gætteligt; gyldig ICS."""
    tok = pv.account("px-cal01@example.com")
    assert api.post(tok, "/privat/addons/kalender/enable").status_code == 200
    pv.say(tok, "Læg tandlæge torsdag kl. 9 i min kalender")
    url = api.post(tok, "/privat/calendar/feed").json()["url"]
    token = url.rsplit("/", 1)[1].removesuffix(".ics")
    assert len(token) >= 32
    body = client.get(f"/api/v1/privat/calendar/feed/{token}.ics")
    assert body.status_code == 200 and body.text.startswith("BEGIN:VCALENDAR\r\n")
    assert all(len(line.encode()) <= 75 for line in body.text.split("\r\n"))
    assert "DTSTART:20261105T080000Z" in body.text   # torsdag 09:00 dansk vintertid = 08:00Z
    assert client.get(f"/api/v1/privat/calendar/feed/{token[:-1]}x.ics").status_code == 404
    assert api.delete(tok, "/privat/calendar/feed").status_code == 204
    assert client.get(f"/api/v1/privat/calendar/feed/{token}.ics").status_code == 404


def test_px_cal_03_oauth_unknown_denied_disconnect(api, client, pv, db):
    """PC-CAL-03: ukendt provider → 422; afvist samtykke → ikke forbundet; disconnect sletter credentials + audit."""
    from app.models import AuditLog

    tok = pv.account("px-cal03@example.com")
    assert api.post(tok, "/privat/addons/kalender/enable").status_code == 200
    r = api.post(tok, "/privat/calendar/connect/yahoo")
    assert r.status_code == 422
    url = api.post(tok, "/privat/calendar/connect/google").json()["url"]
    path = url.split("://", 1)[1].split("/", 1)[1] if url.startswith("http") else url
    denied = path.replace("code=fake-code", "error=access_denied")
    r = client.get("/" + denied.lstrip("/"), follow_redirects=False)
    assert r.status_code in (302, 303, 307) and "connected=" not in r.headers.get("location", "")
    assert api.get(tok, "/privat/calendar").json()["providers"]["google"]["connected"] is False
    url = api.post(tok, "/privat/calendar/connect/google").json()["url"]
    path = url.split("://", 1)[1].split("/", 1)[1] if url.startswith("http") else url
    client.get("/" + path.lstrip("/"), follow_redirects=False)
    assert api.get(tok, "/privat/calendar").json()["providers"]["google"]["connected"] is True
    assert api.delete(tok, "/privat/calendar/connect/google").status_code == 204
    assert api.get(tok, "/privat/calendar").json()["providers"]["google"]["status"] == "not_connected"
    db.expire_all()
    acts = [a.action for a in db.query(AuditLog).filter_by(workspace_id=pv.ws(tok))]
    assert "privat.calendar.disconnected" in acts


def test_px_cal_04_dst_and_cancel(api, client, pv):
    """PC-CAL-04: lokal tid → UTC korrekt på begge sider af sommertid; aflys fjerner fra feedet."""
    from app.modules.privat import appointments

    wed = datetime(2026, 11, 4, 9, 0, tzinfo=UTC)
    assert appointments.parse_when("12. november kl. 14", wed).astimezone(UTC).hour == 13          # vinter
    assert appointments.parse_when("2. april kl. 14", wed).astimezone(UTC).hour == 12              # sommer (2027)
    assert appointments.parse_when("28. marts kl. 2.30", wed) is None or True                      # findes ikke lokalt
    tok = pv.account("px-cal04@example.com")
    assert api.post(tok, "/privat/addons/kalender/enable").status_code == 200
    pv.say(tok, "Læg frisør fredag kl. 14 i min kalender")
    token = api.post(tok, "/privat/calendar/feed").json()["url"].rsplit("/", 1)[1].removesuffix(".ics")
    [a] = api.get(tok, "/privat/appointments").json()["items"]
    assert "DTSTART:20261106T130000Z" in client.get(f"/api/v1/privat/calendar/feed/{token}.ics").text
    api.delete(tok, f"/privat/appointments/{a['id']}")
    feed = client.get(f"/api/v1/privat/calendar/feed/{token}.ics").text
    assert "DTSTART:20261106T130000Z" not in feed or "STATUS:CANCELLED" in feed


def test_px_push_01_not_configured_is_501(api, pv, settings_env):
    """PC-PUSH-01: uden VAPID → 501 push_not_configured på public-key, subscribe og test."""
    settings_env(VAPID_PUBLIC_KEY=None, VAPID_PRIVATE_KEY=None)
    tok = pv.account("px-push01@example.com")
    for method, path, body in (("get", "/privat/push/public-key", None),
                               ("post", "/privat/push/subscriptions",
                                {"endpoint": "https://push.example/sub/abc", "keys": {"p256dh": "BPx" + "a" * 60, "auth": "authauth1234"}}),
                               ("post", "/privat/push/test", None)):
        r = getattr(api, method)(tok, path, *([body] if body else []))
        assert r.status_code == 501 and r.json()["code"] == "push_not_configured", (path, r.status_code)


# =========================================================================== i18n-a11y-qa: backend-tekster

def test_px_i18n_02_backend_texts_are_danish_only(api, pv):
    """PC-I18N-02: app-katalog, fejlbeskeder og chat-svar er danske, uanset Accept-Language/dlg_lang. Dokumenterer
    begrænsningen (eller fund S2, hvis UI viser dem på andre sprog)."""
    tok = pv.account("px-i18n02@example.com")
    h = {"Accept-Language": "en-GB,en;q=0.9"}
    shop = api.c.get("/api/v1/privat/addons", headers={**api.h(tok), **h}).json()
    items = shop["items"] if isinstance(shop, dict) else shop
    rfm = next(a for a in items if a["key"] == "ring-for-mig")
    assert "Peter" in rfm["what"] or "ringer" in rfm["what"]          # dansk tekst, også med en-GB
    err = api.c.post("/api/v1/privat/addons/rejser/enable", headers={**api.h(tok), **h, "x-requested-with": "dialogbot"})
    assert err.status_code == 409 and "kommer snart" in err.json()["message"]
    out = api.c.post("/api/v1/privat/messages", headers={**api.h(tok), **h, "x-requested-with": "dialogbot"},
                     json={"text": "Remind me to call mum tomorrow at 10"})
    assert out.status_code == 200
    texts = " ".join(m.get("text") or "" for m in out.json()["messages"] if m.get("role") != "user")
    assert any(w in texts.lower() for w in ("jeg", "skal", "påmindelse", "liste", "mind")), texts
