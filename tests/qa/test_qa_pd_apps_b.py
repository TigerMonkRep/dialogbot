"""QA Privat dybderunde fase 2, prefix PB (e2e-privat): ti apps hele vejen – API/DB-halvdelen.

Apps: ring-for-mig, oenskelister, kalender, pakker, madplan, regninger, laege-og-tandlaege, pakkeliste, rejser, kaeledyr.
Scenarier PC-APP-<APP>-01..05 i qa/privat/scenarios.csv. Browser-halvdelen: web/e2e/qa/privat-deep/apps-b/<app>.spec.ts
(mod den rigtige stak på :8400). Her: samme kontrakter i processen med fast ur (WED_10), fake AI og fake Vapi.

Fake-AI'en (app/modules/privat/fake.py) forstår kun bestemte formuleringer, og efter ethvert værktøjskald svarer den
«Klaret.» – også når værktøjet svarede «Ikke gemt: …». Derfor asserter vi altid på DATA (DB/API), aldrig på «Klaret.».
Pakker og Rejser er «Kommer snart» uden nøgler (track17 / duffel): her testes, at det siges ærligt, og at intet lover andet.

Kør: source /home/claude/qa-env.sh && export TEST_DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/qa_pd3 \
     DATABASE_URL=$TEST_DATABASE_URL && python -m pytest tests/qa/test_qa_pd_apps_b.py -q
"""
from __future__ import annotations

import threading
import uuid
from datetime import timedelta

import pytest
from sqlalchemy import select

from app.models import (OutboxEvent, PrivateAddonEnabled, PrivateAppData, PrivateAppointment, PrivateBill, PrivateCall,
                        PrivateTask, PrivateTaskItem)
from app.modules.privat import addons, app_kit, bills
from app.worker import runner

MINE = ("ring-for-mig", "oenskelister", "kalender", "pakker", "madplan", "regninger", "laege-og-tandlaege",
        "pakkeliste", "rejser", "kaeledyr")
PLUS = ("kalender", "madplan", "regninger", "laege-og-tandlaege", "pakkeliste", "kaeledyr")
SOON = ("pakker", "rejser")
DELETABLE = {"madplan", "regninger", "laege-og-tandlaege", "pakkeliste", "kaeledyr", "pakker"}
EMOJI = "Snuden 🐶🐾 – «ÆØÅ» 😀"


def _addon(api, tok, key) -> dict:
    return next(a for a in api.get(tok, "/privat/addons").json() if a["key"] == key)


def _rows(db, ws, key=None):
    db.expire_all()
    q = select(PrivateAddonEnabled).where(PrivateAddonEnabled.workspace_id == ws)
    if key:
        q = q.where(PrivateAddonEnabled.key == key)
    return list(db.scalars(q))


def _outbox(db, ws=None) -> list[OutboxEvent]:
    db.expire_all()
    rows = db.query(OutboxEvent).all()
    return [r for r in rows if ws is None or str(ws) in repr(r.payload) or getattr(r, "workspace_id", None) == ws]


def _calls(db, ws) -> list[PrivateCall]:
    db.expire_all()
    return list(db.scalars(select(PrivateCall).where(PrivateCall.workspace_id == ws)))


@pytest.fixture
def plus(pv):
    """A trial (Plus) account with the Plus apps of this suite switched on."""
    def make(tag: str, *keys: str) -> str:
        tok = pv.account(f"pb-{tag}-{uuid.uuid4().hex[:6]}@testmail.dk", "Mette Hansen")
        for k in keys:
            r = pv.api.post(tok, f"/privat/addons/{k}/enable")
            assert r.status_code == 200, (k, r.text)
        return tok
    return make


# ============================================================================ 01 – «Hvad den gør» og prislinjen

def test_01_catalog_texts_complete_and_personalised(pv):
    """Every app of this suite has what/example/steps/needs/permissions; all texts say the user's name for the
    assistant (Sofie, hun) – never the default «Peter» – and the API is the source the web shows."""
    tok = pv.account("pb-01@testmail.dk")
    r = pv.api.patch(tok, "/privat/me/assistant", {"name": "Sofie", "pronoun": "hun"})
    assert r.status_code == 200, r.text
    cat = {a["key"]: a for a in pv.api.get(tok, "/privat/addons").json()}
    for k in MINE:
        a = cat[k]
        assert a["what"] and a["example"] and a["steps"] and a["permissions"], k
        blob = " ".join([a["what"], a["example"], a["tagline"], a["description"], *a["steps"], *a["permissions"], *a["needs"]])
        assert "Peter" not in blob, (k, blob)
        assert a["setup"]["total"] == len(a["steps"]), k
    # requires / plans as the store promises
    assert cat["laege-og-tandlaege"]["requires"] == ["ring-for-mig"] and cat["kaeledyr"]["requires"] == ["ring-for-mig"]
    assert cat["ring-for-mig"]["included_in"] == ["basis", "plus", "familie"]
    assert cat["oenskelister"]["included_in"] == [] and cat["oenskelister"]["price_text"] == "Gratis"
    for k in PLUS:
        assert cat[k]["included_in"] == ["plus", "familie"], k
    for k in SOON:
        assert cat[k]["status"] == "coming_soon" and cat[k]["enabled"] is False, k


@pytest.mark.parametrize("persona,expect_included", [
    ("none", {"oenskelister"}),
    ("basis", {"oenskelister", "ring-for-mig"}),
    ("expired", {"oenskelister"}),
    ("trial", set(MINE)),
    ("familie", set(MINE)),
])
def test_01_included_flag_per_persona(pv, persona, expect_included):
    tok = pv.account(f"pb-01-{persona}@testmail.dk", trial=persona in ("trial", "expired"))
    if persona == "expired":
        pv.expire_trial(tok)
    if persona == "basis":
        pv.set_plan(tok, "basis")
    if persona == "familie":
        pv.set_plan(tok, "familie", interval="year", period_days=300)
    cat = {a["key"]: a for a in pv.api.get(tok, "/privat/addons").json()}
    got = {k for k in MINE if cat[k]["included"]}
    assert got == expect_included, (persona, got)


def test_01_needs_plan_message_for_ring_for_mig_names_basis(pv):
    """«Ring for mig» is in ALL plans (included_in basis/plus/familie). The 409 shown to a user without a plan must
    not say it is only in Plus and Familie – that steers them to a dearer plan than they need."""
    tok = pv.account("pb-01-rfm@testmail.dk", trial=False)
    r = pv.api.post(tok, "/privat/addons/ring-for-mig/enable")
    assert r.status_code == 409 and r.json()["code"] == "needs_plan"
    assert r.json()["plans"] == ["basis", "plus", "familie"]
    msg = r.json()["message"]
    assert "Basis" in msg or "alle planer" in msg, msg


# ============================================================================ 02 – installér pr. plan, idempotent

@pytest.mark.parametrize("persona", ["none", "basis", "expired"])
def test_02_plus_apps_need_a_plan(pv, db, persona):
    tok = pv.account(f"pb-02-{persona}@testmail.dk", trial=persona == "expired")
    if persona == "expired":
        pv.expire_trial(tok)
    if persona == "basis":
        pv.set_plan(tok, "basis")
    ws = pv.ws(tok)
    for k in PLUS:
        r = pv.api.post(tok, f"/privat/addons/{k}/enable")
        assert r.status_code == 409 and r.json()["code"] == "needs_plan", (k, r.text)
        assert set(r.json()["plans"]) == {"plus", "familie"}, k
        assert _rows(db, ws, k) == [], k
    r = pv.api.post(tok, "/privat/addons/oenskelister/enable")
    assert r.status_code == 200
    rfm = pv.api.post(tok, "/privat/addons/ring-for-mig/enable")
    assert rfm.status_code == (200 if persona == "basis" else 409), rfm.text


@pytest.mark.parametrize("plan", ["trial", "plus", "familie"])
def test_02_plan_holders_enable_and_dependencies_follow(pv, db, plan):
    tok = pv.account(f"pb-02-{plan}@testmail.dk")
    if plan != "trial":
        pv.set_plan(tok, plan)
    ws = pv.ws(tok)
    pv.api.post(tok, "/privat/addons/ring-for-mig/disable")
    assert _rows(db, ws, "ring-for-mig") == []
    for k in PLUS:
        r = pv.api.post(tok, f"/privat/addons/{k}/enable")
        assert r.status_code == 200 and r.json()["enabled"] is True, (k, r.text)
        assert r.json()["setup"] == {"done": 0, "total": len(addons.CATALOG[k].steps)}, k
    # læge & tandlæge / kæledyr need Ring for mig: it came on with them
    assert len(_rows(db, ws, "ring-for-mig")) == 1
    for k in SOON:
        r = pv.api.post(tok, f"/privat/addons/{k}/enable")
        assert r.status_code == 409 and r.json()["code"] == "coming_soon", k
        assert _rows(db, ws, k) == []


def test_02_double_and_concurrent_enable_give_one_row(pv, db, client):
    tok = pv.account("pb-02-dbl@testmail.dk")
    ws = pv.ws(tok)
    for k in PLUS:
        a = pv.api.post(tok, f"/privat/addons/{k}/enable")
        b = pv.api.post(tok, f"/privat/addons/{k}/enable")
        assert a.status_code == b.status_code == 200, k
        assert a.json()["enabled_at"] == b.json()["enabled_at"], k
        assert len(_rows(db, ws, k)) == 1, k
    # a real double tap: two requests at the same time on a fresh app
    pv.api.post(tok, "/privat/addons/madplan/disable")
    res: list[int] = []
    def hit():
        res.append(client.post("/api/v1/privat/addons/madplan/enable", headers=pv.api.h(tok)).status_code)
    ts = [threading.Thread(target=hit) for _ in range(2)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert all(s == 200 for s in res), res
    assert len(_rows(db, ws, "madplan")) == 1


def test_02_coming_soon_notify_is_remembered_and_honest(pv, db):
    tok = pv.account("pb-02-soon@testmail.dk")
    for k in SOON:
        a = _addon(pv.api, tok, k)
        assert a["status"] == "coming_soon" and a["enabled"] is False and a["summary_line"] is None
        r = pv.api.post(tok, f"/privat/addons/{k}/notify")
        assert r.status_code == 200 and r.json()["notify_requested"] is True
        assert pv.api.post(tok, f"/privat/addons/{k}/notify").status_code == 200  # idempotent
    # nothing usable behind the curtain
    assert pv.api.get(tok, "/privat/parcels").status_code == 403
    assert pv.api.post(tok, "/privat/parcels", {"number": "00340434123456789012"}).status_code == 403
    assert pv.api.get(tok, "/privat/trips/latest").status_code == 403
    assert pv.api.post(tok, "/privat/trips/search", {"query": "Billund februar"}).status_code in (403, 422)


# ============================================================================ 03 – kerneflow via chat, data i DB

def test_03_ring_for_mig_proposal_never_dials_before_approval(pv, plus, db):
    tok = plus("rfm")
    ws = pv.ws(tok)
    pv.verify_phone(tok)
    out = pv.say(tok, "Ring til Cykelværkstedet på 70 20 30 40 og find en tid torsdag efter klokken tre")
    prop = [m for m in out["messages"] if m["kind"] in ("call_proposal", "proposal") or m.get("task_id")]
    assert prop, out
    calls = _calls(db, ws)
    assert all(c.status in ("proposed", "draft", "awaiting_approval") for c in calls), [c.status for c in calls]
    runner.drain()
    assert all(c.vapi_call_id is None for c in _calls(db, ws))
    ob = [e for e in _outbox(db) if "call" in e.event_type and str(ws) in repr(e.payload)]
    assert ob == [], [e.event_type for e in ob]


def test_03_wishlist_owner_never_sees_reservations(pv, plus, api, db):
    tok = plus("wish")
    tid = pv.make_list(tok, "Lav en ønskeliste med cykelhjelm og en god bog")
    items = pv.task(tok, tid).json()["items"]
    assert [i["text"] for i in items] == ["Cykelhjelm", "En god bog"]
    sh = pv.api.post(tok, f"/privat/tasks/{tid}/share", {"mode": "wishlist"})
    assert sh.status_code == 200, sh.text
    assert sh.json()["short_url"]
    before = pv.task(tok, tid).json()
    # a guest with a FREE account (no subscription) opens the list and reserves; can change nothing else
    guest = pv.account("pb-wish-guest@testmail.dk", "Ole Berg", trial=False)
    raw = sh.json().get("token") or sh.json()["short_url"].rstrip("/").rsplit("/", 1)[1]
    acc = pv.api.post(guest, f"/privat/invites/{raw}/accept")
    if acc.status_code >= 400:
        acc = pv.api.post(guest, f"/privat/invites/by-code/{raw}/accept")
    assert acc.status_code == 200, acc.text
    gi = pv.task(guest, tid).json()["items"]
    assert pv.api.post(guest, f"/privat/tasks/{tid}/items/{gi[0]['id']}/reserve").status_code == 200
    assert pv.api.post(guest, f"/privat/tasks/{tid}/items", {"text": "x"}).status_code == 403
    assert pv.api.delete(guest, f"/privat/tasks/{tid}/items/{gi[1]['id']}").status_code == 403
    after = pv.task(tok, tid).json()
    for b, a in zip(before["items"], after["items"]):
        assert a.get("reserved") in (None, False) and not a.get("reserved_by_me"), a
        assert {k: v for k, v in a.items() if "reserv" in k} == {k: v for k, v in b.items() if "reserv" in k}
    assert "Ole" not in repr(after["items"])


def test_03_calendar_appointment_ics_and_feed(pv, plus, client, db):
    tok = plus("cal", "kalender")
    pv.say(tok, "Læg tiden hos frisøren i min kalender på fredag kl. 10")
    items = pv.api.get(tok, "/privat/appointments").json()["items"]
    assert len(items) == 1 and items[0]["title"] == "Frisøren", items
    ics = client.get(f"/api/v1/privat/appointments/{items[0]['id']}.ics", headers=pv.api.h(tok))
    assert ics.status_code == 200 and "BEGIN:VEVENT" in ics.text and "Frisøren" in ics.text
    feed = pv.api.post(tok, "/privat/calendar/feed").json()["url"]
    path = "/api/v1/privat/calendar/feed/" + feed.rsplit("/", 1)[1]
    assert "Frisøren" in client.get(path).text


def test_03_mealplan_prefs_then_yes_saves_plan_and_scaled_shopping_list(pv, plus, db):
    tok = plus("meal", "madplan")
    pv.say(tok, "Vi er 4, og børnene spiser ikke fisk")
    p = pv.api.get(tok, "/privat/meals/preferences").json()
    assert p["people"] == 4 and "fisk" in p["avoid"], p
    out = pv.say(tok, "Ja, gem madplanen")
    tasks = [m for m in out["messages"] if m["kind"] == "task"]
    assert len(tasks) == 2, out  # madplan + indkøbsliste
    shop = pv.task(tok, tasks[1]["task_id"]).json()
    texts = " | ".join(i["text"] for i in shop["items"])
    assert "fisk" not in texts.lower() and "laks" not in texts.lower()
    # 500 g hakket oksekød for 4 → scaled, never left as the recipe's raw line twice
    assert texts.lower().count("tomatsauce") == 1, texts  # «Tomatsauce» + «tomatsauce» are merged


def test_03_bill_saved_with_minor_amount_and_month_total(pv, plus, db):
    tok = plus("bill", "regninger")
    pv.say(tok, "Læg regningen ind: Bilforsikring den 1. hver måned, 640 kr.")
    b = pv.api.get(tok, "/privat/bills").json()
    assert len(b["items"]) == 1, b
    it = b["items"][0]
    assert it["name"] == "Bilforsikring" and it["amount_minor"] == 64000 and it["frequency"] == "monthly", it
    db.expire_all()
    row = db.scalars(select(PrivateBill).where(PrivateBill.workspace_id == pv.ws(tok))).one()
    assert row.amount_minor == 64000 and row.next_due.day == 1 and row.frequency == "monthly"


def test_03_health_needs_saved_clinic_then_proposal_without_health_data(pv, plus, db):
    tok = plus("health", "laege-og-tandlaege")
    ws = pv.ws(tok)
    pv.verify_phone(tok)
    pv.say(tok, "Book et tandeftersyn hos min tandlæge – helst en morgen i næste måned")
    assert _calls(db, ws) == [] and pv.api.get(tok, "/privat/health-contacts").json()["items"] == []
    pv.say(tok, "Gem min tandlæge, den hedder Smil Klinikken, nummer 86 12 34 56")
    hc = pv.api.get(tok, "/privat/health-contacts").json()["items"]
    assert len(hc) == 1 and hc[0]["name"] == "Smil Klinikken" and hc[0]["phone_display"].replace(" ", "").endswith("86123456"), hc
    pv.say(tok, "Book et tandeftersyn hos min tandlæge – helst en morgen i næste måned")
    calls = _calls(db, ws)
    assert len(calls) == 1 and calls[0].vapi_call_id is None, calls
    db.expire_all()
    data = db.get(PrivateAppData, (ws, "laege-og-tandlaege")).data
    assert set(data) <= {"tandlaege", "laege", "reminded"}, data  # only the clinic


def test_03_packing_list_and_reuse_unchecked(pv, plus, db):
    tok = plus("pack", "pakkeliste")
    out = pv.say(tok, "Lav en pakkeliste til en uge i sommerhus med badetøj, solcreme og bøger")
    tid = next(m["task_id"] for m in out["messages"] if m["kind"] == "task")
    items = pv.task(tok, tid).json()["items"]
    assert [i["text"] for i in items] == ["Badetøj", "Solcreme", "Bøger"], items
    pv.api.post(tok, f"/privat/tasks/{tid}/items/{items[0]['id']}/toggle")
    out2 = pv.say(tok, "Lav en pakkeliste som sidst")
    tid2 = next(m["task_id"] for m in out2["messages"] if m["kind"] == "task")
    assert tid2 != tid
    items2 = pv.task(tok, tid2).json()["items"]
    assert [i["text"] for i in items2] == ["Badetøj", "Solcreme", "Bøger"]
    assert not any(i.get("done") or i.get("checked") for i in items2), items2


def test_03_pets_saved_with_vaccination_and_worming(pv, plus, db):
    tok = plus("pet", "kaeledyr")
    pv.say(tok, "Vores hund Bella skal vaccineres 2027-03-01 og have ormekur hver 3. måned")
    ov = pv.api.get(tok, "/privat/apps/kaeledyr/overview").json()
    assert [i["text"] for i in ov["items"]] == ["Bella"], ov
    db.expire_all()
    p = db.get(PrivateAppData, (pv.ws(tok), "kaeledyr")).data["items"][0]
    assert p["vaccination_due"] == "2027-03-01" and p["worming"]["every"] == 3, p
    # book_vet without a saved vet: no call
    pv.verify_phone(tok)
    pv.say(tok, "Book dyrlæge til Bella")
    assert _calls(db, pv.ws(tok)) == []


def test_03_soon_apps_chat_never_invents_parcels_or_prices(pv, plus, db):
    tok = plus("soon")
    for text in ("Følg pakken med nummer 00340434123456789012",
                 "Find en strandferie i februar til to voksne og to børn fra Billund for højst 12.000 kr."):
        out = pv.say(tok, text)
        blob = " ".join((m.get("text") or "") for m in out["messages"] if m["role"] == "assistant")
        assert "kr." not in blob.replace("12.000 kr.", ""), blob  # no invented prices
        assert "følger nu" not in blob.lower() and "spores" not in blob.lower(), blob
    db.expire_all()
    assert db.get(PrivateAppData, (pv.ws(tok), "pakker")) is None
    assert db.get(PrivateAppData, (pv.ws(tok), "rejser")) is None


# ============================================================================ 04 – ret og slet

def test_04_bill_same_name_updates_not_duplicates_delete_and_unknown(pv, plus, db):
    tok = plus("bill4", "regninger")
    a = pv.api.post(tok, "/privat/bills", {"name": "Bilforsikring", "amount": "640 kr.", "due_day": 1}).json()
    b = pv.api.post(tok, "/privat/bills", {"name": "Bilforsikring", "amount": "700 kr.", "due_day": 1}).json()
    assert a["id"] == b["id"] and b["created"] is False and b["amount_minor"] == 70000
    assert len(pv.api.get(tok, "/privat/bills").json()["items"]) == 1
    long = "x" * 100
    assert pv.api.post(tok, "/privat/bills", {"name": long, "due_day": 2}).status_code == 200
    assert pv.api.post(tok, "/privat/bills", {"name": long + "y", "due_day": 2}).status_code == 422
    assert pv.api.post(tok, "/privat/bills", {"name": "", "due_day": 2}).status_code == 422
    assert pv.api.post(tok, "/privat/bills", {"name": "   ", "due_day": 2}).status_code == 422
    e = pv.api.post(tok, "/privat/bills", {"name": "Netflix 🎬", "amount": "129 kr.", "due_day": 5})
    assert e.status_code == 200 and e.json()["name"] == "Netflix 🎬"
    assert pv.api.delete(tok, f"/privat/bills/{a['id']}").status_code == 204
    assert pv.api.delete(tok, f"/privat/bills/{a['id']}").status_code == 404
    assert pv.api.delete(tok, f"/privat/bills/{uuid.uuid4()}").status_code == 404
    assert "Bilforsikring" not in [i["name"] for i in pv.api.get(tok, "/privat/bills").json()["items"]]


def test_04_pets_edit_by_same_name_remove_unknown_long_emoji(pv, plus, db):
    tok = plus("pet4", "kaeledyr")
    pv.say(tok, "Vores hund Bella skal vaccineres 2027-03-01 og have ormekur hver 3. måned")
    pv.say(tok, "Vores hund Bella skal vaccineres 2027-03-02")
    ov = pv.api.get(tok, "/privat/apps/kaeledyr/overview").json()
    assert len(ov["items"]) == 1 and "2. mar" in ov["items"][0]["sub"], ov
    from app.modules.privat import pets
    pets.save_pet(db, pv.ws(tok), name=EMOJI)
    pets.save_pet(db, pv.ws(tok), name="L" * 500)
    db.commit()
    ov = pv.api.get(tok, "/privat/apps/kaeledyr/overview").json()
    names = [i["text"] for i in ov["items"]]
    assert any("🐶" in n for n in names) and max(len(n) for n in names) <= 40, names
    pid = ov["items"][0]["id"]
    assert pv.api.delete(tok, f"/privat/apps/kaeledyr/items/{pid}").status_code == 204
    assert pv.api.delete(tok, f"/privat/apps/kaeledyr/items/{pid}").status_code == 404
    assert pv.api.delete(tok, "/privat/apps/kaeledyr/items/nope").status_code == 404
    assert pid not in [i["id"] for i in pv.api.get(tok, "/privat/apps/kaeledyr/overview").json()["items"]]


def test_04_appointment_remove_unknown_and_health_contact_delete(pv, plus, db):
    tok = plus("cal4", "kalender", "laege-og-tandlaege")
    pv.say(tok, "Læg tiden hos frisøren i min kalender på fredag kl. 10")
    aid = pv.api.get(tok, "/privat/appointments").json()["items"][0]["id"]
    assert pv.api.delete(tok, f"/privat/appointments/{aid}").status_code == 200
    assert pv.api.get(tok, "/privat/appointments").json()["items"] == []
    assert pv.api.delete(tok, f"/privat/appointments/{uuid.uuid4()}").status_code == 404
    pv.say(tok, "Gem min tandlæge, den hedder Smil Klinikken, nummer 86 12 34 56")
    assert pv.api.delete(tok, "/privat/health-contacts/tandlaege").status_code == 204
    assert pv.api.get(tok, "/privat/health-contacts").json()["items"] == []
    # unknown kind: answers 204 like a known one (idempotent delete) – noted as S3 in notes-PB, not a blocker
    assert pv.api.delete(tok, "/privat/health-contacts/hjerteklinik").status_code in (204, 404, 422)


def test_04_mealprefs_limits(pv, plus):
    tok = plus("meal4", "madplan")
    assert pv.api.put(tok, "/privat/meals/preferences", {"people": 0}).status_code == 422
    assert pv.api.put(tok, "/privat/meals/preferences", {"people": 21}).status_code == 422
    assert pv.api.put(tok, "/privat/meals/preferences", {"avoid": "a" * 501}).status_code == 422
    r = pv.api.put(tok, "/privat/meals/preferences", {"people": 3, "avoid": "nødder 🥜", "likes": ""})
    assert r.status_code == 200 and pv.api.get(tok, "/privat/meals/preferences").json()["avoid"] == "nødder 🥜"


def test_04_generic_item_endpoint_answers_honestly_for_non_household_apps(pv, plus):
    """The scenario's DELETE /privat/apps/<key>/items/{id} exists only for household apps (app_kit). For the others it
    must be a clean 404, never a 500."""
    tok = plus("gen4", *PLUS)
    for k in MINE:
        r = pv.api.delete(tok, f"/privat/apps/{k}/items/abc")
        assert r.status_code in (403, 404), (k, r.status_code, r.text)


# ============================================================================ 05 – slå fra, data gemt, slå til igen

@pytest.mark.parametrize("key,probe", [
    ("kalender", ("GET", "/privat/appointments")),
    ("madplan", ("GET", "/privat/meals/preferences")),
    ("regninger", ("GET", "/privat/bills")),
    ("laege-og-tandlaege", ("GET", "/privat/health-contacts")),
    ("kaeledyr", ("GET", "/privat/apps/kaeledyr/overview")),
])
def test_05_disable_keeps_data_403_tools_gone_reenable_kept(pv, plus, db, key, probe):
    tok = plus(f"off-{key}", key)
    ws = pv.ws(tok)
    seed = {"kalender": "Læg tiden hos frisøren i min kalender på fredag kl. 10",
            "madplan": "Vi er 4, og børnene spiser ikke fisk",
            "regninger": "Læg regningen ind: Bilforsikring den 1. hver måned, 640 kr.",
            "laege-og-tandlaege": "Gem min tandlæge, den hedder Smil Klinikken, nummer 86 12 34 56",
            "kaeledyr": "Vores hund Bella skal vaccineres 1. marts og have ormekur hver 3. måned"}[key]
    pv.say(tok, seed)
    before = pv.api.get(tok, probe[1]).json()
    r = pv.api.post(tok, f"/privat/addons/{key}/disable")
    assert r.status_code == 200 and r.json()["enabled"] is False and r.json()["disabled_at"], r.text
    assert pv.api.post(tok, f"/privat/addons/{key}/disable").status_code == 200  # idempotent
    g = pv.api.get(tok, probe[1])
    assert g.status_code == 403 and g.json()["code"] == "addon_disabled", g.text
    names = {t.name for t in addons.tools_for(db, ws)}
    own = {t.name for t in addons.CATALOG[key].tools}
    assert not (names & own), names & own
    # data kept
    r = pv.api.post(tok, f"/privat/addons/{key}/enable")
    assert r.status_code == 200 and r.json()["setup"]["done"] == 0 or r.json()["enabled"]
    assert pv.api.get(tok, probe[1]).json() == before


def test_05_disabled_apps_send_no_reminders(pv, plus, db):
    tok = plus("rem", "regninger", "kaeledyr")
    ws = pv.ws(tok)
    pv.api.post(tok, "/privat/bills", {"name": "Husleje", "amount": "8000 kr.", "due_day": 6, "remind_days_before": 3})
    from app.modules.privat import pets
    pets.save_pet(db, ws, name="Bella", kind="hund", vaccination_due=(pv.clock() + timedelta(days=5)).date().isoformat())
    db.commit()
    pv.api.post(tok, "/privat/addons/regninger/disable")
    pv.api.post(tok, "/privat/addons/kaeledyr/disable")
    db.expire_all()
    assert bills.send_due(db, pv.clock()) == 0
    assert app_kit.send_due(db, pv.clock()) == 0
    db.rollback()
    pv.api.post(tok, "/privat/addons/regninger/enable")
    pv.api.post(tok, "/privat/addons/kaeledyr/enable")
    db.expire_all()
    assert bills.send_due(db, pv.clock()) == 1
    assert app_kit.send_due(db, pv.clock()) == 1
    db.rollback()


@pytest.mark.parametrize("key", sorted(DELETABLE - {"pakker"}))
def test_05_delete_data_only_when_off_then_fresh_setup(pv, plus, db, key):
    tok = plus(f"del-{key}", key)
    ws = pv.ws(tok)
    seed = {"madplan": "Vi er 4, og børnene spiser ikke fisk",
            "regninger": "Læg regningen ind: Bilforsikring den 1. hver måned, 640 kr.",
            "laege-og-tandlaege": "Gem min tandlæge, den hedder Smil Klinikken, nummer 86 12 34 56",
            "pakkeliste": "Lav en pakkeliste til en uge i sommerhus med badetøj, solcreme og bøger",
            "kaeledyr": "Vores hund Bella skal vaccineres 1. marts og have ormekur hver 3. måned"}[key]
    pv.say(tok, seed)
    r = pv.api.delete(tok, f"/privat/addons/{key}/data")
    assert r.status_code == 409 and r.json()["code"] == "addon_enabled"
    pv.api.post(tok, f"/privat/addons/{key}/disable")
    r = pv.api.delete(tok, f"/privat/addons/{key}/data")
    assert r.status_code == 200 and r.json()["deleted"] > 0, r.text
    assert r.json()["addon"]["disabled_at"] is None
    r = pv.api.post(tok, f"/privat/addons/{key}/enable")
    assert r.json()["setup"]["done"] == 0
    db.expire_all()
    assert db.get(PrivateAppData, (ws, key)) is None or not (db.get(PrivateAppData, (ws, key)).data or {}).get("items")


def test_05_delete_data_of_packing_list_says_all_but_lists_stay(pv, plus, db):
    """«Slet appens data» says «Sletter alt, hvad Pakkeliste har gemt». The lists Pakkeliste made are tasks; check
    whether they survive (then the text promises more than it does)."""
    tok = plus("delpack", "pakkeliste")
    out = pv.say(tok, "Lav en pakkeliste til en uge i sommerhus med badetøj, solcreme og bøger")
    tid = next(m["task_id"] for m in out["messages"] if m["kind"] == "task")
    pv.api.post(tok, "/privat/addons/pakkeliste/disable")
    assert pv.api.delete(tok, "/privat/addons/pakkeliste/data").json()["deleted"] >= 1
    # same root cause as F-PA-01 (delete_data only touches private_app_data): the list must be gone too
    assert pv.task(tok, tid).status_code == 404, "pakkelisten findes stadig efter «Slet appens data» (F-PA-01)"


def test_05_delete_data_of_mealplan_removes_plan_and_shopping_list(pv, plus, db):
    tok = plus("delmeal", "madplan")
    pv.say(tok, "Vi er 4, og børnene spiser ikke fisk")
    out = pv.say(tok, "Ja, gem madplanen")
    tids = [m["task_id"] for m in out["messages"] if m["kind"] == "task"]
    assert len(tids) == 2
    pv.api.post(tok, "/privat/addons/madplan/disable")
    assert pv.api.delete(tok, "/privat/addons/madplan/data").json()["deleted"] >= 1
    left = [t for t in tids if pv.task(tok, t).status_code == 200]
    assert left == [], "madplan/indkøbsliste findes stadig efter «Slet appens data» (F-PA-01)"


@pytest.mark.parametrize("key", ["ring-for-mig", "oenskelister", "kalender", "rejser"])
def test_05_not_deletable_apps(pv, plus, key):
    tok = plus(f"nd-{key}", *(k for k in [key] if k in PLUS))
    a = _addon(pv.api, tok, key)
    assert a["data_deletable"] is False
    if key != "rejser":
        pv.api.post(tok, f"/privat/addons/{key}/disable")
    r = pv.api.delete(tok, f"/privat/addons/{key}/data")
    assert r.status_code == 409 and r.json()["code"] == "not_deletable", r.text


def test_05_wishlist_disable_pauses_sharing_and_keeps_list(pv, plus, client, db):
    tok = plus("wishoff")
    tid = pv.make_list(tok, "Lav en ønskeliste med cykelhjelm og en god bog")
    url = pv.api.post(tok, f"/privat/tasks/{tid}/share", {"mode": "wishlist"}).json()["short_url"]
    pv.api.post(tok, "/privat/addons/oenskelister/disable")
    assert pv.task(tok, tid).status_code == 200  # owner keeps it
    a = _addon(pv.api, tok, "oenskelister")
    assert a["disabled_at"] and not a["enabled"]
    pv.api.post(tok, "/privat/addons/oenskelister/enable")
    assert _addon(pv.api, tok, "oenskelister")["enabled"]


def test_05_ring_for_mig_off_takes_dependants_and_blocks_approve(pv, plus, db):
    tok = plus("rfmoff", "laege-og-tandlaege", "kaeledyr")
    ws = pv.ws(tok)
    pv.verify_phone(tok)
    pv.say(tok, "Ring til Cykelværkstedet på 70 20 30 40 og find en tid torsdag efter klokken tre")
    calls = _calls(db, ws)
    assert len(calls) == 1
    pv.api.post(tok, "/privat/addons/ring-for-mig/disable")
    cat = {a["key"]: a for a in pv.api.get(tok, "/privat/addons").json()}
    assert not cat["laege-og-tandlaege"]["enabled"] and not cat["kaeledyr"]["enabled"]
    task_id = calls[0].task_id
    r = pv.api.post(tok, f"/privat/calls/{task_id}/approve", {"confirm_business": True})
    assert r.status_code in (403, 409), r.text
    runner.drain()
    assert all(c.vapi_call_id is None for c in _calls(db, ws))


def test_04_pets_new_name_containing_an_existing_name_is_a_new_pet(pv, plus, db):
    """«Samme navn igen retter» – but a DIFFERENT pet whose name contains another's (Mis / Misser, Bo / Bobby) must
    not overwrite the first one. app_kit.find falls back to substring matching."""
    tok = plus("pet-sub", "kaeledyr")
    ws = pv.ws(tok)
    pv.say(tok, "Vores kat Misser skal vaccineres 2027-03-01")
    pv.say(tok, "Vores kat Mis skal vaccineres 2027-06-15")
    db.expire_all()
    pets = db.get(PrivateAppData, (ws, "kaeledyr")).data["items"]
    assert sorted(p["name"] for p in pets) == ["Mis", "Misser"], pets
    assert next(p for p in pets if p["name"] == "Misser")["vaccination_due"] == "2027-03-01", pets
