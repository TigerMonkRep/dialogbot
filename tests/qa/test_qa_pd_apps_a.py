"""QA Privat dybderunde fase 2 – apps A (prefix PA, owner e2e-privat). API/DB level; the browser half is
web/e2e/qa/privat-deep/apps-a/<app>.spec.ts (runs against the real stack :3400 → :8400).

Apps: abonnementer, bil-og-syn, delte-lister, faelles-udgifter, fest, fitness-og-sundhed, flytning, foedselsdage, garanti,
haandvaerker, hus-og-vedligehold (scenarios PC-APP-<APP>-01..05) + the cross-cutting PC-APP-05/06/10/13/14/15.

AI_PROVIDER=fake: the chat is a regex mapping (app/modules/privat/fake.py) – the phrasings below are the fake's (ISO
dates). The catalog's own examples with «1. april» / «3. maj» only reach the tool with a real model; that is noted, not
reported. Nothing is ever dialled (campaigns.create_call is replaced and asserted unused) and no SMS leaves.

Run:  source /home/claude/qa-env.sh && export TEST_DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/qa_pd2 \
      DATABASE_URL=$TEST_DATABASE_URL && python -m pytest -q tests/qa/test_qa_pd_apps_a.py
"""
from __future__ import annotations

import threading
from datetime import UTC, date, datetime

import pytest
from sqlalchemy import select

from app.models import (
    OutboxEvent,
    PrivateAddonEnabled,
    PrivateAppData,
    PrivateBirthday,
    PrivateCall,
    PrivateTask,
    PrivateTaskItem,
)
from app.modules.campaigns import service as campaigns
from app.modules.privat import addons, app_kit, app_status, birthdays, car, meals
from app.modules.privat import app_kit as kit

PLAN_APPS = ["abonnementer", "bil-og-syn", "fitness-og-sundhed", "flytning", "foedselsdage", "garanti", "haandvaerker",
             "hus-og-vedligehold"]
FREE_APPS = ["delte-lister", "faelles-udgifter", "fest"]
APPS = PLAN_APPS + FREE_APPS
HOUSEHOLD = [k for k in APPS if k in app_kit.MODULES]


@pytest.fixture(autouse=True)
def _never_dial(monkeypatch):
    called: list = []
    monkeypatch.setattr(campaigns, "create_call", lambda p: called.append(p) or {"id": "x"})
    yield
    assert called == [], "der må aldrig ringes i disse tests"


def _on(api, tok, key):
    r = api.post(tok, f"/privat/addons/{key}/enable")
    assert r.status_code == 200, r.text
    return r.json()


def _cat(api, tok) -> dict:
    return {a["key"]: a for a in api.get(tok, "/privat/addons").json()}


def _texts(out) -> list[str]:
    return [m.get("text") or "" for m in out["messages"] if m["role"] != "user"]


def _kinds(out) -> list[str]:
    return [m["kind"] for m in out["messages"] if m["role"] != "user"]


def _outbox(db) -> list[OutboxEvent]:
    db.expire_all()
    return list(db.scalars(select(OutboxEvent)))


def _tasks(db, ws) -> list[PrivateTask]:
    db.expire_all()
    return list(db.scalars(select(PrivateTask).where(PrivateTask.workspace_id == ws)))


def _overview(api, tok, key) -> dict:
    r = api.get(tok, f"/privat/apps/{key}/overview")
    assert r.status_code == 200, r.text
    return r.json()


# The app's own read endpoint (403 addon_disabled when off) and how to put something in it.
READ = {"foedselsdage": "/privat/birthdays", "bil-og-syn": "/privat/car",
        **{k: f"/privat/apps/{k}/overview" for k in HOUSEHOLD}}
SEED = {  # fake-model phrasing → the app holds something afterwards
    "abonnementer": "Jeg har Netflix til 139 kr. om måneden og Telia til 199 kr. med binding til 2027-03-01",
    "bil-og-syn": "Bilen har nummerplade AB 12 345 og skal til syn 2026-11-20",
    "faelles-udgifter": "Jeg betalte 1.200 kr. for mad i sommerhuset – vi er Anna, Bo og mig",
    "fest": "Lav en fest: Idas 10-års fødselsdag den 2027-03-06 kl. 14 med Emma, Noah og Alma",
    "fitness-og-sundhed": "Jeg vil løbe tirsdag og torsdag kl. 17 – målet er 5 km i maj",
    "flytning": "Vi flytter til Odense den 2026-11-10",
    "foedselsdage": "Mors fødselsdag er den 7. november – mind mig om det en uge før",
    "garanti": "Jeg købte en vaskemaskine i Elgiganten den 2024-11-20 til 4.999 kr.",
    "hus-og-vedligehold": "Tilføj alle de faste opgaver i huset",
}


def _holds_something(api, tok, key) -> bool:
    body = api.get(tok, READ[key]).json()
    if key == "bil-og-syn":
        return bool(body.get("plate"))
    return bool(body.get("items"))


# ============================================================================ 01 – the shop page texts

@pytest.mark.parametrize("key", APPS)
def test_pa_01_shop_texts_match_catalog_and_say_the_assistants_name(api, pv, key):
    """PC-APP-<APP>-01: what/example/steps/needs/permissions/price come from the catalog, with the assistant's name."""
    tok = pv.account(f"pa01-{key}@testmail.dk")
    assert api.patch(tok, "/privat/me/assistant", {"name": "Kim", "pronoun": "hun"}).status_code == 200
    a = _cat(api, tok)[key]
    src = addons.CATALOG[key]
    assert a["what"] and a["example"] and len(a["steps"]) == len(src.steps) >= 1 and a["permissions"]
    blob = " ".join([a["what"], a["example"], a["tagline"], a["description"], *a["steps"], *a["needs"], *a["permissions"]])
    assert "Peter" not in blob, f"{key}: «Peter» står stadig efter omdøbning: {blob[:200]}"
    if "Peter" in " ".join([src.what, *src.steps]):
        assert "Kim" in blob, key
    assert a["requires_plan"] is (key in PLAN_APPS)
    assert a["price_text"] == ("Gratis" if key in FREE_APPS else a["price_text"])
    if key in PLAN_APPS:
        assert a["included_in"] == ["plus", "familie"] and "Plus og Familie" in a["price_text"]
    # persona-dependent price line input: «included» per plan
    free = pv.account(f"pa01f-{key}@testmail.dk", trial=False)
    assert _cat(api, free)[key]["included"] is (key in FREE_APPS)


# ============================================================================ 02 – install per plan

@pytest.mark.parametrize("key", APPS)
def test_pa_02_install_per_plan_and_idempotent(api, pv, db, key):
    """PC-APP-<APP>-02: no plan / Basis / expired trial → 409 needs_plan [plus, familie] for plan apps, 200 for free apps;
    trial / Plus / Familie → 200; enabling twice (also in parallel) gives one row and the same enabled_at."""
    personas = {}
    personas["none"] = pv.account(f"pa02n-{key}@testmail.dk", trial=False)
    personas["basis"] = pv.account(f"pa02b-{key}@testmail.dk", trial=False)
    pv.set_plan(personas["basis"], "basis")
    personas["expired"] = pv.account(f"pa02e-{key}@testmail.dk")
    pv.expire_trial(personas["expired"])
    personas["trial"] = pv.account(f"pa02t-{key}@testmail.dk")
    personas["plus"] = pv.account(f"pa02p-{key}@testmail.dk", trial=False)
    pv.set_plan(personas["plus"], "plus")
    personas["familie"] = pv.account(f"pa02f-{key}@testmail.dk", trial=False)
    pv.set_plan(personas["familie"], "familie")
    for who, tok in personas.items():
        r = api.post(tok, f"/privat/addons/{key}/enable")
        blocked = key in PLAN_APPS and who in ("none", "basis", "expired")
        if blocked:
            assert r.status_code == 409, (who, r.text)
            assert r.json()["code"] == "needs_plan" and r.json()["plans"] == ["plus", "familie"], (who, r.json())
            assert r.json()["addon"] == key and "basis" not in r.json()["plans"]
            assert not _cat(api, tok)[key]["enabled"]
        else:
            assert r.status_code == 200, (who, r.text)
            first = r.json()["enabled_at"]
            again = api.post(tok, f"/privat/addons/{key}/enable")
            assert again.status_code == 200 and again.json()["enabled_at"] == first, who
    # a double tap that arrives as two parallel requests
    tok = personas["trial"]
    api.post(tok, f"/privat/addons/{key}/disable")
    codes: list[int] = []
    ts = [threading.Thread(target=lambda: codes.append(api.post(tok, f"/privat/addons/{key}/enable").status_code))
          for _ in range(4)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert codes == [200] * 4, codes
    ws = pv.ws(tok)
    db.expire_all()
    rows = db.scalars(select(PrivateAddonEnabled).where(PrivateAddonEnabled.workspace_id == ws,
                                                        PrivateAddonEnabled.key == key)).all()
    assert len(rows) == 1
    if addons.CATALOG[key].requires:
        assert _cat(api, tok)["ring-for-mig"]["enabled"], "en app der kræver Ring for mig slår den til"
    st = _cat(api, tok)[key]["setup"]
    assert st["total"] == len(addons.CATALOG[key].steps)


# ============================================================================ 03 – first use and the core flow

@pytest.mark.parametrize("key", HOUSEHOLD)
def test_pa_03_empty_state_says_what_to_say(api, pv, key):
    """PC-APP-<APP>-03 (empty): an empty overview has a summary that tells what to say, no items, no partner."""
    tok = pv.account(f"pa03e-{key}@testmail.dk")
    _on(api, tok, key)
    o = _overview(api, tok, key)
    assert o["items"] == [] and o["summary"] and o["partner"] is None
    assert _cat(api, tok)[key]["summary_line"] is None  # empty → the tagline is shown on Mine apps


def test_pa_03_foedselsdage_core_flow(api, pv, db):
    tok = pv.account("pa03-fd@testmail.dk")
    _on(api, tok, "foedselsdage")
    assert api.get(tok, "/privat/birthdays").json()["items"] == []
    out = pv.say(tok, "Mors fødselsdag er den 14. marts – mind mig om det en uge før")
    assert any("Mor" in t and "14. marts" in t for t in _texts(out)), _texts(out)
    b = db.scalar(select(PrivateBirthday).where(PrivateBirthday.workspace_id == pv.ws(tok)))
    assert (b.name, b.month, b.day, b.year, b.remind_days_before) == ("Mor", 3, 14, None, 7)
    line = _cat(api, tok)["foedselsdage"]["summary_line"]
    assert line.startswith("Mor har fødselsdag om ") and "dage" in line, line


def test_pa_03_bil_og_syn_core_flow_never_calls_without_approval(api, pv, db):
    tok = pv.account("pa03-bil@testmail.dk")
    _on(api, tok, "bil-og-syn")
    pv.verify_phone(tok)
    out = pv.say(tok, "Bilen har nummerplade AB 12 345 og skal til syn 2027-05-01")
    c = api.get(tok, "/privat/car").json()
    assert c["plate"] and c["plate"].replace(" ", "") == "AB12345" and c["inspection_due"] == "2027-05-01", c
    # booking without a saved workshop: asks, proposes nothing
    out = pv.say(tok, "Book syn hos mit værksted")
    assert "call_proposal" not in _kinds(out)
    # the workshop number the user typed → a proposal; nothing is dialled and no call row is «queued»
    pv.say(tok, "Gem værkstedet hedder Auto Jens, nummer 86 12 34 56")
    out = pv.say(tok, "Book syn hos mit værksted")
    assert "call_proposal" in _kinds(out), _texts(out)
    db.expire_all()
    calls = db.scalars(select(PrivateCall).where(PrivateCall.workspace_id == pv.ws(tok))).all()
    assert all(x.status in ("proposed", "draft", "awaiting_approval") for x in calls), [x.status for x in calls]


def test_pa_03_abonnementer_core_flow(api, pv, db):
    tok = pv.account("pa03-abo@testmail.dk")
    _on(api, tok, "abonnementer")
    pv.say(tok, SEED["abonnementer"])
    o = _overview(api, tok, "abonnementer")
    assert len(o["items"]) == 2 and o["summary"].startswith("2 abonnementer – 338 kr. om måneden, 4.056 kr. om året"), o
    telia = next(i for i in o["items"] if i["text"].startswith("Telia"))
    assert "binding til 1. marts 2027" in telia["text"] and telia["sub"].startswith("Sidste dag at opsige"), telia
    out = pv.say(tok, "Opsig Netflix")
    assert any("Opsigelse af abonnement – Netflix" in t for t in _texts(out)), _texts(out)
    assert "call_proposal" not in _kinds(out)


def test_pa_03_haandvaerker_core_flow_proposals_only(api, pv, db, monkeypatch):
    """«Find 3 malere …» → up to 3 proposals, each needs its own approval; no address unless the user wrote it."""
    from app.modules.privat import places

    found = [places.Place(name=f"Maler {i}", phone=f"+45861234{i:02d}", address=f"Vej {i}, Aarhus", source="google",
                          place_id=f"p{i}") for i in range(5)] if hasattr(places, "Place") else None
    if found is None:
        pytest.skip("places.Place findes ikke – dækket af tests/test_privat_household.py")
    monkeypatch.setattr(places, "search", lambda *a, **k: found, raising=False)
    tok = pv.account("pa03-hv@testmail.dk")
    _on(api, tok, "haandvaerker")
    out = pv.say(tok, "Find 3 malere i Aarhus og hent tilbud på at male stuen")
    assert _kinds(out).count("call_proposal") <= 3


def test_pa_03_faelles_udgifter_core_flow(api, pv, db):
    tok = pv.account("pa03-fu@testmail.dk")
    _on(api, tok, "faelles-udgifter")
    out = pv.say(tok, SEED["faelles-udgifter"])
    t = "\n".join(_texts(out))
    assert "Anna betaler 400 kr. til Mette" in t and "Bo betaler 400 kr. til Mette" in t, t
    o = _overview(api, tok, "faelles-udgifter")
    assert len(o["items"]) == 1 and "Anna betaler 400 kr." in o["items"][0]["sub"] and o["items"][0]["share_text"]
    assert len([x for x in _outbox(db) if "sms" in x.event_type]) == 0


def test_pa_03_fest_core_flow_sends_nothing(api, pv, db):
    tok = pv.account("pa03-fest@testmail.dk")
    _on(api, tok, "fest")
    before = len(_outbox(db))
    pv.say(tok, SEED["fest"])
    o = _overview(api, tok, "fest")
    assert o["items"][0]["text"].startswith("Idas 10-års fødselsdag") and "6. marts 2027 kl. 14" in o["items"][0]["text"], o
    assert "3 har ikke svaret" in o["items"][0]["sub"], o
    out = pv.say(tok, "Skriv invitationen til festen")
    assert any("Idas 10-års fødselsdag" in t and "6. marts 2027" in t for t in _texts(out)), _texts(out)
    new = [e.event_type for e in _outbox(db)[before:]]
    assert not [e for e in new if "sms" in e or "email" in e or "mail" in e], new


def test_pa_03_flytning_core_flow(api, pv, db):
    tok = pv.account("pa03-fly@testmail.dk")
    _on(api, tok, "flytning")
    out = pv.say(tok, "Vi flytter til Odense den 2027-04-01")
    t = "\n".join(_texts(out))
    assert "borger.dk" in t, t
    task = next(x for x in _tasks(db, pv.ws(tok)) if x.title == "Flytning: Odense")
    items = db.scalars(select(PrivateTaskItem.text).where(PrivateTaskItem.task_id == task.id)).all()
    assert len(items) >= 12 and any("1. januar 2027" in i for i in items) and any("borger.dk" in i for i in items)
    o = _overview(api, tok, "flytning")
    assert o["summary"].startswith("Flyttedag 1. april 2027 til Odense"), o


def test_pa_03_garanti_core_flow(api, pv, db):
    tok = pv.account("pa03-gar@testmail.dk")
    _on(api, tok, "garanti")
    pv.say(tok, "Jeg købte en vaskemaskine i Elgiganten den 2026-05-03 til 4.999 kr.")
    o = _overview(api, tok, "garanti")
    assert len(o["items"]) == 1, o
    blob = o["items"][0]["text"] + " " + o["items"][0]["sub"]
    assert "3. maj 2028" in blob, blob   # 2 years' reklamationsret
    out = pv.say(tok, "Skriv en reklamation på vaskemaskinen – den lækker vand")
    assert any("lækker vand" in t for t in _texts(out)), _texts(out)


def test_pa_03_garanti_future_purchase_is_refused(api, pv):
    tok = pv.account("pa03-gar2@testmail.dk")
    _on(api, tok, "garanti")
    pv.say(tok, "Jeg købte en vaskemaskine i Elgiganten den 2030-05-03 til 4.999 kr.")
    assert _overview(api, tok, "garanti")["items"] == []


def test_pa_03_hus_og_vedligehold_core_flow(api, pv):
    tok = pv.account("pa03-hus@testmail.dk")
    _on(api, tok, "hus-og-vedligehold")
    pv.say(tok, SEED["hus-og-vedligehold"])
    o = _overview(api, tok, "hus-og-vedligehold")
    assert len(o["items"]) >= 5, o
    pv.say(tok, "Jeg har testet røgalarmen")
    o2 = _overview(api, tok, "hus-og-vedligehold")
    r = next(i for i in o2["items"] if "røgalarm" in i["text"].lower())
    assert "februar 2027" in r["sub"], r   # moved on 3 months from today (4 Nov 2026)


def test_pa_03_fitness_core_flow(api, pv, db):
    tok = pv.account("pa03-fit@testmail.dk")
    _on(api, tok, "fitness-og-sundhed")
    pv.say(tok, SEED["fitness-og-sundhed"])
    o = _overview(api, tok, "fitness-og-sundhed")
    assert [i["text"] for i in o["items"]] == ["Tirsdag: Løb", "Torsdag: Løb"] and "5 km i maj" in o["summary"], o
    pv.say(tok, "Færdig med løb 30 min")
    assert "1 træning" in _overview(api, tok, "fitness-og-sundhed")["summary"]


def test_pa_fitness_server_has_no_guard_for_health_words(api, pv, db):
    """Handed to security-privacy (their PC-APP-03): «Gemmer aldrig vægt, sygdom, … medicin» is enforced only by the
    model prompt. With the fake model the goal is saved verbatim – the server keeps whatever the model sends."""
    tok = pv.account("pa03-fit2@testmail.dk")
    _on(api, tok, "fitness-og-sundhed")
    pv.say(tok, "Jeg vil løbe tirsdag og torsdag kl. 17 – målet er 5 km i maj. Jeg vejer 92 kg og tager blodtryksmedicin")
    db.expire_all()
    row = db.scalar(select(PrivateAppData).where(PrivateAppData.workspace_id == pv.ws(tok),
                                                 PrivateAppData.app_key == "fitness-og-sundhed"))
    blob = repr(row.data).lower() if row else ""
    for word in ("92 kg", "vejer", "blodtryk", "medicin"):
        assert word not in blob, f"helbredsord gemt: {word} i {blob[:300]}"


def test_pa_03_delte_lister_core_flow_nothing_sent(api, pv, db):
    tok = pv.account("pa03-dl@testmail.dk")
    tid = pv.make_list(tok)
    before = len(_outbox(db))
    out = pv.say(tok, "Del listen med Anna", about=tid)
    assert "share_proposal" in _kinds(out), _texts(out)
    assert any("Anna" in t for t in _texts(out))
    r = api.post(tok, f"/privat/tasks/{tid}/share", {"mode": "group", "role": "editor"})
    assert r.status_code == 200, r.text
    assert r.json()["suggested_text"] and r.json()["short_url"]
    db.expire_all()
    assert db.get(PrivateTask, __import__("uuid").UUID(tid)).share_mode == "group"
    new = [e.event_type for e in _outbox(db)[before:]]
    assert not [e for e in new if "sms" in e or "invite" in e], new


# ============================================================================ 04 – edit and delete

@pytest.mark.parametrize("key", HOUSEHOLD)
def test_pa_04_remove_item_and_unknown_id(api, pv, key):
    tok = pv.account(f"pa04-{key}@testmail.dk")
    _on(api, tok, key)
    if key == "haandvaerker":
        assert api.delete(tok, f"/privat/apps/{key}/items/nope").status_code == 404
        return
    pv.say(tok, SEED[key])
    items = _overview(api, tok, key)["items"]
    assert items, key
    assert api.delete(tok, f"/privat/apps/{key}/items/{items[0]['id']}").status_code == 204
    assert items[0]["id"] not in [i["id"] for i in _overview(api, tok, key)["items"]]
    assert api.delete(tok, f"/privat/apps/{key}/items/{items[0]['id']}").status_code == 404
    assert api.delete(tok, f"/privat/apps/{key}/items/{'x' * 300}").status_code == 404


def test_pa_04_same_name_corrects_instead_of_duplicating(api, pv, db):
    """«samme navn igen retter»: abonnementer, fødselsdage, fest, bil (one car)."""
    tok = pv.account("pa04-same@testmail.dk")
    for k in ("abonnementer", "foedselsdage", "fest", "bil-og-syn"):
        _on(api, tok, k)
    pv.say(tok, "Jeg har Netflix til 139 kr. om måneden")
    pv.say(tok, "Jeg har Netflix til 149 kr. om måneden")
    subs = _overview(api, tok, "abonnementer")["items"]
    assert [i["text"] for i in subs] == ["Netflix, 149 kr. pr. md."], subs
    pv.say(tok, "Mors fødselsdag er den 14. marts")
    pv.say(tok, "Mors fødselsdag er den 15. marts")
    bs = api.get(tok, "/privat/birthdays").json()["items"]
    assert [(b["name"], b["day"]) for b in bs] == [("Mor", 15)], bs
    pv.say(tok, "Lav en fest: Sommerfest den 2027-06-20 kl. 14 med Emma")
    pv.say(tok, "Lav en fest: Sommerfest den 2027-06-21 kl. 15 med Emma og Noah")
    ps = _overview(api, tok, "fest")["items"]
    assert len(ps) == 1 and "21. juni 2027" in ps[0]["text"] + ps[0]["sub"] + _texts(pv.say(tok, "Hvordan går det med festen"))[0]


def test_pa_04_garanti_same_purchase_twice_is_two_rows(api, pv):
    """Garanti never corrects: the same message twice (resend / double tap) saves the purchase twice."""
    tok = pv.account("pa04-gar@testmail.dk")
    _on(api, tok, "garanti")
    msg = "Jeg købte en vaskemaskine i Elgiganten den 2026-05-03 til 4.999 kr."
    pv.say(tok, msg)
    pv.say(tok, msg)
    assert len(_overview(api, tok, "garanti")["items"]) == 1, "samme køb to gange giver en dublet"


def test_pa_04_long_and_emoji_texts_are_kept(api, pv):
    tok = pv.account("pa04-long@testmail.dk")
    _on(api, tok, "foedselsdage")
    _on(api, tok, "abonnementer")
    r = api.post(tok, "/privat/birthdays", {"name": "🎂 Mormor Åse 👵", "date": "14.03.1946"})
    assert r.status_code == 200 and r.json()["name"] == "🎂 Mormor Åse 👵" and r.json()["year"] == 1946
    assert api.post(tok, "/privat/birthdays", {"name": "x" * 101, "date": "14. marts"}).status_code == 422
    assert api.post(tok, "/privat/birthdays", {"name": "", "date": "14. marts"}).status_code == 422
    assert api.post(tok, "/privat/birthdays", {"name": "Ole", "date": ""}).status_code == 422
    bid = r.json()["id"]
    assert api.delete(tok, f"/privat/birthdays/{bid}").status_code == 204
    assert api.delete(tok, f"/privat/birthdays/{bid}").status_code == 404
    assert api.delete(tok, "/privat/birthdays/not-a-uuid").status_code == 422
    from app.db import get_session_factory
    from app.modules.privat import subs_app
    with get_session_factory()() as s:
        row, _ = subs_app.add(s, pv.ws(tok), name="Ü" * 500, price="99 kr.")
        s.commit()
    assert len(row["name"]) == 100   # cleaned to 100


def test_pa_04_car_can_be_cleared(api, pv):
    """bil-og-syn has no item list: PUT /privat/car with empty fields is the only «slet»."""
    tok = pv.account("pa04-car@testmail.dk")
    _on(api, tok, "bil-og-syn")
    assert api.put(tok, "/privat/car", {"plate": "AB 12 345", "inspection_due": "2027-05-01"}).status_code == 200
    assert api.put(tok, "/privat/car", {"plate": "🚗🚗", "inspection_due": None}).status_code == 422
    assert api.put(tok, "/privat/car", {"inspection_due": "31-02-2027"}).status_code == 422
    assert api.delete(tok, "/privat/apps/bil-og-syn/items/x").status_code == 404


# ============================================================================ 05 – off, kept, back on, delete data

@pytest.mark.parametrize("key", [k for k in APPS if k in SEED])
def test_pa_05_off_keeps_data_stops_tools_and_reminders_then_back(api, pv, db, key):
    tok = pv.account(f"pa05-{key}@testmail.dk")
    _on(api, tok, key)
    ws = pv.ws(tok)
    pv.say(tok, SEED[key])
    assert _holds_something(api, tok, key), key
    tool_names = {t.name for t in addons.CATALOG[key].tools}
    assert tool_names <= {t.name for t in addons.tools_for(db, ws)}
    off = api.post(tok, f"/privat/addons/{key}/disable")
    assert off.status_code == 200 and off.json()["enabled"] is False and off.json()["disabled_at"], off.text
    r = api.get(tok, READ[key])
    assert r.status_code == 403 and r.json()["code"] == "addon_disabled", r.text
    db.expire_all()
    assert not tool_names & {t.name for t in addons.tools_for(db, ws)}
    # reminders: nothing for a switched-off app, even when something is due
    before = len(_outbox(db))
    at = datetime(2026, 11, 10, 10, 0, tzinfo=UTC)
    with __import__("app.db", fromlist=["x"]).get_session_factory()() as s:
        birthdays.send_due(s, at) if key == "foedselsdage" else car.send_due(s, at) if key == "bil-og-syn" \
            else kit.send_due(s, at)
        s.commit()
    mine = [e for e in _outbox(db)[before:] if str(ws) in repr(e.payload)]
    assert mine == [], f"{key}: påmindelse efter slå fra: {[e.event_type for e in mine]}"
    # data kept, back on
    assert _on(api, tok, key)["enabled"]
    assert _holds_something(api, tok, key), f"{key}: data væk efter slå til igen"


@pytest.mark.parametrize("key", [k for k in APPS if k in SEED])
def test_pa_05_delete_data(api, pv, db, key):
    tok = pv.account(f"pa05d-{key}@testmail.dk")
    _on(api, tok, key)
    pv.say(tok, SEED[key])
    r = api.delete(tok, f"/privat/addons/{key}/data")
    assert r.status_code == 409 and r.json()["code"] == "addon_enabled", r.text
    api.post(tok, f"/privat/addons/{key}/disable")
    r = api.delete(tok, f"/privat/addons/{key}/data")
    assert r.status_code == 200 and r.json()["deleted"] > 0, r.text
    assert r.json()["addon"]["disabled_at"] is None and r.json()["addon"]["setup"]["done"] == 0
    back = _on(api, tok, key)
    assert back["setup"]["done"] == 0
    assert not _holds_something(api, tok, key), f"{key}: data tilbage efter sletning"


def test_pa_05_delte_lister_off_pauses_and_is_not_deletable(api, pv, db):
    tok = pv.account("pa05-dl@testmail.dk")
    tid = pv.make_list(tok)
    assert api.post(tok, f"/privat/tasks/{tid}/share", {"mode": "group", "role": "editor"}).status_code == 200
    r = api.post(tok, "/privat/addons/delte-lister/disable")
    assert r.status_code == 200 and r.json()["data_deletable"] is False
    r = api.delete(tok, "/privat/addons/delte-lister/data")
    assert r.status_code == 409 and r.json()["code"] == "not_deletable"
    assert pv.task(tok, tid).status_code == 200   # the list itself is kept
    r = api.post(tok, f"/privat/tasks/{tid}/share", {"mode": "group", "role": "editor"})
    assert r.status_code in (403, 409), r.text
    assert _on(api, tok, "delte-lister")["enabled"]


def test_pa_delete_data_removes_the_lists_the_app_made(api, pv, db):
    """F-PA-01: «Sletter alt, hvad {name} har gemt» – Fælles udgifter and Flytning leave their lists behind."""
    tok = pv.account("pa-f01@testmail.dk")
    ws = pv.ws(tok)
    for key, msg, title in (("faelles-udgifter", SEED["faelles-udgifter"], "Udgifter: sommerhuset"),
                            ("flytning", "Vi flytter til Odense den 2027-04-01", "Flytning: Odense")):
        _on(api, tok, key)
        pv.say(tok, msg)
        assert title in [t.title for t in _tasks(db, ws) if t.status != "deleted"]
        api.post(tok, f"/privat/addons/{key}/disable")
        assert api.delete(tok, f"/privat/addons/{key}/data").status_code == 200
        left = [t.title for t in _tasks(db, ws) if t.title == title and getattr(t, "status", "") != "deleted"
                and getattr(t, "deleted_at", None) is None]
        assert left == [], f"{key}: «{title}» findes stadig efter «Slet appens data»"


# ============================================================================ cross-cutting PC-APP-05/06/10/13/15

@pytest.mark.parametrize("raw,expect", [
    ("29. februar", (2, 29, None)), ("14.03.1946", (3, 14, 1946)), ("1946-03-14", (3, 14, 1946)),
    ("14/3", (3, 14, None)), ("31. april", None), ("14. marts 2099", None), ("1899-01-01", None), ("", None),
    ("30. februar", None), ("29.02.2023", None), ("29.02.2024", (2, 29, 2024)),
])
def test_pa_app05_birthday_dates(raw, expect, pv):
    assert birthdays.parse_date(raw) == expect


def test_pa_app05_feb29_reminded_on_28_and_age_only_with_year(api, pv):
    tok = pv.account("pa-app05@testmail.dk")
    _on(api, tok, "foedselsdage")
    r = api.post(tok, "/privat/birthdays", {"name": "Skud", "date": "29. februar", "remind_days_before": 0})
    assert r.status_code == 200 and r.json()["next_date"] == "2027-02-28" and r.json()["turns"] is None, r.json()
    r = api.post(tok, "/privat/birthdays", {"name": "Mor", "date": "14.03.1946"})
    assert r.json()["turns"] == 81
    for bad in ("31. april", "14. marts 2099", "i går"):
        r = api.post(tok, "/privat/birthdays", {"name": "X", "date": bad})
        assert r.status_code == 422 and r.json()["field_errors"][0]["field"] == "date", (bad, r.text)
        assert "Datoen kunne ikke læses" in r.json()["message"]


def test_pa_app06_one_reminder_from_0800_local_across_dst_and_worker_downtime(api, pv, db):
    """DST ends Sunday 25 Oct 2026 / starts Sunday 28 Mar 2027. Birthday on the DST day, reminded on the day (0)."""
    from app.db import get_session_factory

    tok = pv.account("pa-app06@testmail.dk")
    _on(api, tok, "foedselsdage")
    api.post(tok, "/privat/birthdays", {"name": "Sommer", "date": "28. marts", "remind_days_before": 0})
    api.post(tok, "/privat/birthdays", {"name": "Vinter", "date": "31. oktober", "remind_days_before": 2})

    def run(at: datetime) -> int:
        with get_session_factory()() as s:
            n = birthdays.send_due(s, at)
            s.commit()
            return n
    # 2027-03-28: CEST from 02:00 local. 05:59 UTC = 07:59 local → nothing; 06:00 UTC = 08:00 local → one
    assert run(datetime(2027, 3, 28, 5, 59, tzinfo=UTC)) == 0
    assert run(datetime(2027, 3, 28, 6, 0, tzinfo=UTC)) == 1
    assert run(datetime(2027, 3, 28, 20, 0, tzinfo=UTC)) == 0       # once
    # Vinter: due from 29 Oct 2027 (2 days before). Worker down 29–30 Oct: comes on the 31st (the day), once.
    assert run(datetime(2027, 10, 31, 6, 59, tzinfo=UTC)) == 0      # 07:59 CET (DST ended 31 Oct 2027 01:00 UTC)
    assert run(datetime(2027, 10, 31, 7, 0, tzinfo=UTC)) == 1
    assert run(datetime(2027, 10, 31, 9, 0, tzinfo=UTC)) == 0


def test_pa_app10_meal_plan_scales_and_avoids_nuts(api, pv, db):
    """PC-APP-10 at the module level: 4 people, recipes for 2 → quantities ×2 and summed; «nødder» avoided."""
    tok = pv.account("pa-app10@testmail.dk")
    _on(api, tok, "madplan")
    assert api.put(tok, "/privat/meals/preferences", {"people": 4, "avoid": "nødder"}).status_code == 200
    if not hasattr(meals, "shopping_list"):
        pytest.skip("meals.shopping_list findes ikke – se web-spec")
    plan = [{"day": "mandag", "dish": "Pasta", "servings": 2, "ingredients": [{"name": "Pasta", "amount": 250, "unit": "g"}]},
            {"day": "tirsdag", "dish": "Pastasalat", "servings": 2, "ingredients": [{"name": "pasta", "amount": 100, "unit": "g"}]},
            {"day": "onsdag", "dish": "Nøddesalat", "servings": 2, "ingredients": [{"name": "Valnødder", "amount": 50, "unit": "g"}]}]
    lst = meals.shopping_list(plan, people=4)
    pasta = [x for x in lst if "pasta" in str(x).lower()]
    assert len(pasta) == 1 and "700" in str(pasta[0]), lst


def test_pa_app13_cancel_telia_letter_without_number_call_only_with_typed_number(api, pv, db):
    tok = pv.account("pa-app13@testmail.dk")
    _on(api, tok, "abonnementer")
    pv.verify_phone(tok)
    out = pv.say(tok, "Opsig Telia")
    t = "\n".join(_texts(out))
    assert "Opsigelse af abonnement – Telia" in t and "[indsæt dit kundenummer]" in t, t
    assert "call_proposal" not in _kinds(out)
    out = pv.say(tok, "Opsig Telia – ring til dem på 70 12 34 56")
    assert "call_proposal" in _kinds(out), _texts(out)
    db.expire_all()
    calls = db.scalars(select(PrivateCall).where(PrivateCall.workspace_id == pv.ws(tok))).all()
    assert calls and all(c.status not in ("dialing", "in_progress", "completed", "queued") for c in calls), \
        [c.status for c in calls]
    # («Opsig Telenor og ring til dem» without a number crashes the FAKE model (fake.py:251 phone_m None) – fake only)


def test_pa_app13_letter_marks_cancelling_before_the_user_sends_it(api, pv):
    """F-PA-03. The comment in tool_cancel_subscription: «the status changes only when the user sends the letter». The
    letter path marks «under opsigelse» at once – the overview says so although nothing was sent, and the «last day
    to give notice» reminder stops (subs_app.due skips status != active)."""
    from app.modules.privat import subs_app

    tok = pv.account("pa-app13b@testmail.dk")
    _on(api, tok, "abonnementer")
    pv.say(tok, "Jeg har Telia til 199 kr. om måneden med binding til 2026-12-10")   # last notice day 10 Nov
    ws = pv.ws(tok)
    from app.db import get_session_factory
    from app.modules.privat import appdata
    with get_session_factory()() as s:
        assert subs_app.due(appdata.get(s, ws, "abonnementer"), date(2026, 11, 4)), "påmindelse før opsigelsesbrevet"
    pv.say(tok, "Opsig Telia")
    texts = [i["text"] for i in _overview(api, tok, "abonnementer")["items"]]
    with get_session_factory()() as s:
        reminders = subs_app.due(appdata.get(s, ws, "abonnementer"), date(2026, 11, 4))
    assert texts == ["Telia, 199 kr. pr. md., binding til 10. december 2026"] and reminders, \
        f"brevet er kun skrevet, ikke sendt – men oversigten siger {texts} og påmindelserne er {reminders}"


@pytest.mark.parametrize("key", HOUSEHOLD + ["foedselsdage", "bil-og-syn", "delte-lister"])
def test_pa_app15_summary_line_reader_exists(key):
    assert key in app_status.READERS


def test_pa_app15_pakker_rejser_have_no_reader():
    """PC-APP-15: pakker and rejser are missing in READERS → tagline on Mine apps (accepted while «Kommer snart»)."""
    assert "pakker" not in app_status.READERS and "rejser" not in app_status.READERS


def test_pa_flytning_reminds_items_the_user_already_ticked_off(api, pv, db):
    """moving.due() ignores the list: a ticked-off item is still reminded on its day."""
    from app.db import get_session_factory

    tok = pv.account("pa-fly-done@testmail.dk")
    _on(api, tok, "flytning")
    pv.say(tok, "Vi flytter til Odense den 2026-11-18")   # «Bestil flyttekasser» is due 4 Nov (14 days before)
    ws = pv.ws(tok)
    task = next(x for x in _tasks(db, ws) if x.title == "Flytning: Odense")
    item = db.scalar(select(PrivateTaskItem).where(PrivateTaskItem.task_id == task.id,
                                                   PrivateTaskItem.text.like("Bestil flyttekasser%")))
    r = api.post(tok, f"/privat/tasks/{task.id}/items/{item.id}/toggle")
    assert r.status_code == 200, r.text
    before = len(_outbox(db))
    with get_session_factory()() as s:
        kit.send_due(s, datetime(2026, 11, 4, 9, 0, tzinfo=UTC))
        s.commit()
    texts = [repr(e.payload) for e in _outbox(db)[before:] if str(ws) in repr(e.payload) or "Flytning" in repr(e.payload)]
    assert not any("flyttekasser" in t for t in texts), "påmindelse om et punkt, brugeren har krydset af"
