"""GET /privat/bootstrap: everything the app shows, in one request – the same data the ten single endpoints give."""
from __future__ import annotations


def test_bootstrap_matches_the_single_endpoints(api, pv):
    tok = pv.account("mette@testmail.dk")
    pv.say(tok, "Lav en liste med kaffe og te")
    b = api.get(tok, "/privat/bootstrap")
    assert b.status_code == 200, b.text
    x = b.json()
    assert set(x) == {"me", "day", "tasks", "messages", "ledger", "addons", "referrals", "groups", "subscription"}
    assert x["me"] == api.get(tok, "/privat/me").json()
    assert x["tasks"] == api.get(tok, "/privat/tasks").json()
    assert x["messages"] == api.get(tok, "/privat/messages").json()
    assert x["ledger"] == api.get(tok, "/privat/ledger").json()
    assert x["addons"] == api.get(tok, "/privat/addons").json()
    assert x["groups"] == api.get(tok, "/privat/groups").json()
    assert x["subscription"]["plan"] == api.get(tok, "/privat/subscription").json()["plan"]
    assert x["day"]["awaiting"] == api.get(tok, "/privat/day").json()["awaiting"]


def test_bootstrap_needs_a_private_account(api, pv):
    tok = pv.user("ny@testmail.dk")
    r = api.get(tok, "/privat/bootstrap")
    assert r.status_code == 404 and r.json()["code"] == "privat_account_missing"
