"""Dialogbot Privat apps: «Mine apps» state – «Du skal bruge», the one line per app, setup progress, switched off with
data kept, «Giv mig besked», deleting an app's data, and the app the user wanted coming on with a new plan."""
from __future__ import annotations

from datetime import timedelta

from app.models import PrivateBill
from app.modules.privat import addons, subscriptions
from tests.privat_fixtures import WED_10


def _app(api, tok, key):
    return next(a for a in api.get(tok, "/privat/addons").json() if a["key"] == key)


def test_shape_needs_setup_and_line(api, pv):
    tok = pv.account("mette@testmail.dk")
    a = _app(api, tok, "regninger")
    assert a["needs"] == ["Navn, beløb og forfaldsdag"] and a["setup"] == {"done": 0, "total": len(a["steps"])}
    assert a["summary_line"] is None and a["disabled_at"] is None and a["data_deletable"] is True
    assert api.post(tok, "/privat/addons/regninger/enable").status_code == 200
    assert _app(api, tok, "regninger")["summary_line"] is None  # nothing saved yet → the web shows the tagline
    api.post(tok, "/privat/bills", {"name": "Husleje", "amount": "8.500", "due_day": 28})
    line = _app(api, tok, "regninger")["summary_line"]
    assert line.startswith("1 regning i november") and "8.500" in line
    api.post(tok, "/privat/addons/bil-og-syn/enable")
    api.put(tok, "/privat/car", {"plate": "AB 12 345", "inspection_due": "2026-12-08"})
    assert _app(api, tok, "bil-og-syn")["summary_line"] == "Syn om 34 dage · 8. dec."
    assert _app(api, tok, "ring-for-mig")["summary_line"].endswith("opkald tilbage i november")


def test_setup_progress(api, pv):
    tok = pv.account("mette@testmail.dk")
    r = api.put(tok, "/privat/addons/madplan/setup", {"done": 1})
    assert r.status_code == 409 and r.json()["code"] == "addon_disabled"
    api.post(tok, "/privat/addons/madplan/enable")
    total = _app(api, tok, "madplan")["setup"]["total"]
    assert api.put(tok, "/privat/addons/madplan/setup", {"done": 1}).json()["setup"] == {"done": 1, "total": total}
    assert api.put(tok, "/privat/addons/madplan/setup", {"done": total + 1}).status_code == 422
    assert _app(api, tok, "madplan")["setup"]["done"] == 1  # kept across requests (and devices)


def test_switched_off_keeps_data_and_shows_it(api, pv, db):
    tok = pv.account("mette@testmail.dk")
    api.post(tok, "/privat/addons/regninger/enable")
    api.post(tok, "/privat/bills", {"name": "Husleje", "amount": "8.500", "due_day": 28})
    api.post(tok, "/privat/addons/regninger/disable")
    a = _app(api, tok, "regninger")
    assert a["enabled"] is False and a["disabled_at"] and a["summary_line"] is None
    assert db.query(PrivateBill).count() == 1  # «Slået fra · dine data er gemt» is true
    api.post(tok, "/privat/addons/regninger/enable")
    assert _app(api, tok, "regninger")["disabled_at"] is None


def test_delete_data_only_when_off_and_only_own_data(api, pv, db):
    tok = pv.account("mette@testmail.dk")
    api.post(tok, "/privat/addons/regninger/enable")
    api.post(tok, "/privat/bills", {"name": "Husleje", "amount": "8.500", "due_day": 28})
    r = api.delete(tok, "/privat/addons/regninger/data")
    assert r.status_code == 409 and r.json()["code"] == "addon_enabled"
    api.post(tok, "/privat/addons/regninger/disable")
    other = pv.account("ole@testmail.dk", "Ole")
    api.post(other, "/privat/addons/regninger/enable")
    api.post(other, "/privat/bills", {"name": "El", "amount": "600", "due_day": 5})
    r = api.delete(tok, "/privat/addons/regninger/data")
    assert r.status_code == 200 and r.json()["deleted"] == 1 and r.json()["addon"]["disabled_at"] is None
    assert [b.name for b in db.query(PrivateBill)] == ["El"]  # another account's bills are untouched
    r = api.delete(tok, "/privat/addons/oenskelister/data")
    assert r.status_code == 409  # wishlists are lists: on (default) or not deletable here
    assert r.json()["code"] in ("addon_enabled", "not_deletable")


def test_notify_me_is_stored(api, pv):
    tok = pv.account("mette@testmail.dk")
    assert api.post(tok, "/privat/addons/pakker/notify").json()["notify_requested"] is True
    assert _app(api, tok, "pakker")["notify_requested"] is True


def test_app_comes_on_with_the_plan(api, pv, db, monkeypatch):
    tok = pv.account("mette@testmail.dk", trial=False)
    ws = pv.ws(tok)
    assert api.post(tok, "/privat/addons/madplan/enable").json()["code"] == "needs_plan"
    sub = {"id": "sub_app", "object": "subscription", "status": "trialing", "customer": "cus_1",
           "trial_end": int((WED_10 + timedelta(days=14)).timestamp()), "cancel_at_period_end": False,
           "items": {"data": [{"current_period_end": int((WED_10 + timedelta(days=14)).timestamp()),
                               "price": {"recurring": {"interval": "month"}}}]},
           "metadata": {"kind": "privat_subscription", "workspace_id": str(ws), "plan": "plus", "interval": "month",
                        "app": "madplan"}}
    assert subscriptions.upsert_from_stripe_subscription(db, sub) == "applied"
    db.commit()
    assert addons.is_enabled(db, ws, "madplan")
    assert _app(api, tok, "madplan")["enabled"] is True


def test_checkout_carries_the_app(api, pv, monkeypatch):
    from tests.test_privat_subscription import _fake_checkout, _sessions, _stripe_env

    _stripe_env(monkeypatch)
    sent = _fake_checkout(monkeypatch)
    tok = pv.account("mette@testmail.dk", trial=False)
    r = api.post(tok, "/privat/subscription/checkout", {"plan": "plus", "app": "kalender"})
    assert r.status_code == 200, r.text
    d = _sessions(sent)[-1]
    assert d["metadata"]["app"] == "kalender" and d["subscription_data"]["metadata"]["app"] == "kalender"
    assert d["success_url"].endswith("&app=kalender")
    api.post(tok, "/privat/subscription/checkout", {"plan": "plus", "app": "findes-ikke"})
    assert "app" not in _sessions(sent)[-1]["metadata"]


def test_plan_app_stops_when_the_plan_lapses_and_comes_back_with_its_data(api, pv, db):
    """PC-ENT-02/03 (decision Fürster 2026-11-10): an app that needs a plan stops when the plan no longer applies – no
    use, no reminders – but keeps its data and runs again when the plan is back. Free apps are not affected."""
    from app.modules.privat import appdata

    tok = pv.account("ent-02@testmail.dk")  # trial = Plus
    ws = pv.ws(tok)
    assert api.post(tok, "/privat/addons/kaeledyr/enable").status_code == 200
    pv.say(tok, "Vores kat Misser skal vaccineres 2027-03-01")
    assert api.get(tok, "/privat/apps/kaeledyr/overview").status_code == 200
    pv.expire_trial(tok)
    r = api.get(tok, "/privat/apps/kaeledyr/overview")
    assert r.status_code == 403 and r.json()["code"] == "needs_plan", r.text
    card = next(a for a in api.get(tok, "/privat/addons").json() if a["key"] == "kaeledyr")
    assert card["needs_plan"] is True
    db.expire_all()
    assert "kaeledyr" not in addons.enabled_keys(db, ws)
    assert appdata.get(db, ws, "kaeledyr").get("items")  # the data is kept
    pv.set_plan(tok, "plus")
    db.expire_all()
    assert "kaeledyr" in addons.enabled_keys(db, ws)
    over = api.get(tok, "/privat/apps/kaeledyr/overview").json()
    assert any("Misser" in i["text"] for i in over["items"])


def test_first_setup_step_counts_as_done_when_the_app_has_data(api, pv):
    """F-UX-04: Fødselsdage with Sofie saved stood on «Trin 1 af 3» – an app with data has its first step done."""
    tok = pv.account("ux04@testmail.dk")
    assert api.post(tok, "/privat/addons/foedselsdage/enable").status_code == 200
    card = next(a for a in api.get(tok, "/privat/addons").json() if a["key"] == "foedselsdage")
    assert card["setup"]["done"] == 0
    assert api.post(tok, "/privat/birthdays", {"name": "Sofie", "date": "2019-12-03"}).status_code in (200, 201)
    card = next(a for a in api.get(tok, "/privat/addons").json() if a["key"] == "foedselsdage")
    assert card["summary_line"] and card["setup"]["done"] >= 1
