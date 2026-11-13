"""F-PBQ-06 (Fürster 12/11, binding): plan apps from Butikken – «Ring for mig» too – STOP when the trial ends without a
paid plan. The gate is in the backend (addons.enabled_keys / require, the worker's running_rows); the data is kept and
comes back with a plan. The app list says so (`needs_plan`), which the UI shows as «Kræver plan» with the plan choice.

Walks the whole catalogue, so a new plan app that forgets the gate turns this red.
"""
from __future__ import annotations

import pytest

from app.core.errors import ApiError
from app.modules.privat import addons

PLAN_APPS = sorted(k for k, a in addons.CATALOG.items() if a.included_in and a.live_status != "coming_soon")
PLUS_ONLY = sorted(k for k in PLAN_APPS if "basis" not in addons.CATALOG[k].included_in)


def _catalog(api, tok) -> dict:
    return {a["key"]: a for a in api.get(tok, "/privat/addons").json()}


def test_every_plan_app_stops_after_the_trial_and_comes_back_with_a_plan(api, pv, db):
    assert "ring-for-mig" in PLAN_APPS and len(PLUS_ONLY) >= 10
    tok = pv.account("lapse-all@testmail.dk")
    ws = pv.ws(tok)
    for key in PLAN_APPS:
        r = api.post(tok, f"/privat/addons/{key}/enable")
        assert r.status_code in (200, 409), (key, r.text)  # 409: already on / needs another app first
    on = {k for k, a in _catalog(api, tok).items() if a["enabled"]}
    assert set(PLAN_APPS) <= on | {k for k in PLAN_APPS if addons.CATALOG[k].requires}
    running = addons.enabled_keys(db, ws)
    assert {k for k in PLAN_APPS if k in on} <= running and not any(_catalog(api, tok)[k]["needs_plan"] for k in on)

    pv.expire_trial(tok)  # 14 days are over, no plan bought
    db.expire_all()
    assert pv.subscription(tok)["entitled"] is False
    cat = _catalog(api, tok)
    tools = {t.name for t in addons.tools_for(db, ws)}
    for key in on & set(PLAN_APPS):
        a = cat[key]
        assert a["enabled"] is True and a["needs_plan"] is True, key  # still switched on (data kept), but stopped
        assert key not in addons.enabled_keys(db, ws), key
        with pytest.raises(ApiError) as e:
            addons.require(db, ws, key)
        assert e.value.code == "needs_plan", key
        assert not tools & {t.name for t in addons.CATALOG[key].tools}, key  # Peter cannot use it in the chat
    # the app endpoints answer needs_plan (403), not data
    paths = {"/privat/bills": "regninger", "/privat/birthdays": "foedselsdage", "/privat/car": "bil-og-syn",
             "/privat/health-contacts": "laege-og-tandlaege", "/privat/parcels": "pakker", "/privat/meals/preferences": "madplan",
             "/privat/apps/garanti/overview": "garanti", "/privat/apps/flytning/overview": "flytning"}
    checked = [p for p, k in paths.items() if k in on]
    assert len(checked) >= 6, checked
    for path in checked:
        r = api.get(tok, path)
        assert r.status_code == 403 and r.json()["code"] == "needs_plan", (path, r.status_code, r.text)

    pv.set_plan(tok, "basis")  # Basis: «Ring for mig» runs again, the Plus apps stay stopped
    db.expire_all()
    cat = _catalog(api, tok)
    assert cat["ring-for-mig"]["needs_plan"] is False and "ring-for-mig" in addons.enabled_keys(db, ws)
    assert all(cat[k]["needs_plan"] for k in PLUS_ONLY if k in on)

    pv.set_plan(tok, "plus")  # Plus: everything runs again
    db.expire_all()
    cat = _catalog(api, tok)
    assert not any(cat[k]["needs_plan"] for k in on & set(PLAN_APPS))
    assert api.get(tok, "/privat/bills").status_code == 200


def test_free_apps_never_stop_without_a_plan(api, pv, db):
    tok = pv.account("lapse-free@testmail.dk")
    pv.expire_trial(tok)
    free = [k for k, a in addons.CATALOG.items() if not a.included_in and a.live_status != "coming_soon"]
    cat = _catalog(api, tok)
    for key in free:
        assert cat[key]["needs_plan"] is False, key
