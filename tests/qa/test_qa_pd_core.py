"""PK – Privat-dybderunde fase 2, kerneflows (e2e-privat), mod den KØRENDE Privat-stak (tests/qa/qa_privat_stack.py):
API http://localhost:8400, db qa_privdeep_stack, falsk Stripe/Vapi, intet netværk. Flere brugere ad gangen (ejer,
husstand, inviteret ikke-bruger, ønskeliste-gæst). Skippes, hvis stakken ikke kører.

    source /home/claude/qa-env.sh && pytest tests/qa/test_qa_pd_core.py -q
Scenarie-ID'er: qa/privat/scenarios.csv (PC-*)."""
from __future__ import annotations

import concurrent.futures as cf
import json
import os
import random
import re
import time
import uuid

import httpx
import psycopg
import pytest

API = os.environ.get("PK_API", "http://localhost:8400")
DB = os.environ.get("PK_STACK_DB", "postgresql://postgres:postgres@localhost:5432/qa_privdeep_stack")
PW = "Korrekt-Hest-Batteri-42"
CSRF = {"x-requested-with": "dialogbot"}


def _up() -> bool:
    try:
        return httpx.get(f"{API}/__qa/calls", timeout=3).status_code == 200
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not _up(), reason="kræver Privat-stakken på :8400 (tests/qa/qa_privat_stack.py)")


def ip() -> str:
    return f"10.{random.randint(0, 250)}.{random.randint(0, 250)}.{random.randint(1, 250)}"


def sql(q: str, *a):
    with psycopg.connect(DB) as c:
        cur = c.execute(q, a or None)
        return cur.fetchall() if cur.description else None


def sessions():
    return httpx.get(f"{API}/__qa/stripe/sessions").json()["sessions"]


def dialled():
    return httpx.get(f"{API}/__qa/calls").json()["dialled"]


class U:
    """A real user: register → login (bearer) → verify e-mail (simulated mailbox) → private account."""

    def __init__(self, tag="u", name="Mette Hansen", account=True):
        self.email = f"qa-pk-{tag}-{int(time.time() * 1000)}-{random.randint(0, 10**6)}@example.com"
        self.c = httpx.Client(base_url=f"{API}/api/v1", headers={**CSRF, "x-real-ip": ip()}, timeout=30)
        assert self.c.post("/auth/register", json={"email": self.email, "password": PW, "display_name": name}).status_code == 201
        self.c.headers["authorization"] = "Bearer " + self.c.post("/auth/login", json={"email": self.email, "password": PW}).json()["access_token"]
        tok = None
        for _ in range(40):
            for m in self.c.get("/dev/mailbox").json()["items"]:
                if (mm := re.search(r"token=([\w-]+)", m.get("body_text") or "")):
                    tok = mm.group(1)
            if tok:
                break
            time.sleep(0.25)
        assert self.c.post("/auth/verify-email", json={"token": tok}).status_code == 200
        if account:
            assert self.c.post("/privat/account").status_code < 300

    def __getattr__(self, k):  # get/post/put/patch/delete
        return getattr(self.c, k)

    def pay(self, url, card="4242424242424242"):
        return httpx.post(url, data={"name": "Mette Hansen", "line1": "Abildgade 18", "postal_code": "8200", "city": "Aarhus N",
                                     "phone": "+4520304050", "email": self.email, "card": card}, follow_redirects=False)

    def trial(self, plan="plus"):
        url = self.c.post("/privat/subscription/checkout", json={"plan": plan, "interval": "month"}).json()["url"]
        assert self.pay(url).status_code == 303
        s = self.c.get("/privat/subscription", params={"session_id": url.split("/pay/")[1]}).json()
        assert s["entitled"] and s["status"] == "trial"
        return s

    def say(self, text, key=None):
        r = self.c.post("/privat/messages", json={"text": text}, headers={"Idempotency-Key": key} if key else {})
        assert r.status_code == 200, r.text
        return r.json()["messages"]

    def make(self, text) -> str:
        return next(m["task_id"] for m in self.say(text) if m.get("task_id"))

    def addons(self):
        return {a["key"]: a for a in self.c.get("/privat/addons").json()}


# ------------------------------------------------------------------------------------------------ abonnement (SUB/ENT)
def test_sub02_trial_turns_on_standard_apps():
    u = U("sub02")
    s = u.trial()
    assert (s["plan"], s["trial_days_left"], s["calls_quota"]) == ("plus", 14, 10)
    on = {k for k, a in u.addons().items() if a["enabled"]}
    assert {"ring-for-mig", "delte-lister", "oenskelister"} <= on


def test_sub08_parallel_checkout_never_two_subscriptions():
    """F-PK-01: double-tap / two tabs → two open sessions → both payable → two Stripe subscriptions."""
    u = U("sub08")
    with cf.ThreadPoolExecutor(2) as ex:
        rs = list(ex.map(lambda _: u.post("/privat/subscription/checkout", json={"plan": "plus", "interval": "month"}), range(2)))
    for r in rs:
        if r.status_code == 200:
            u.pay(r.json()["url"])
    subs = {s["subscription"] for s in sessions() if s["customer_email"] == u.email and s["status"] == "complete"}
    assert len(subs) <= 1, f"to Stripe-abonnementer på én konto: {subs}"


def test_sub10_session_id_validation_never_5xx():
    u = U("sub10")
    u.trial()
    assert u.get("/privat/subscription", params={"session_id": "abc"}).status_code == 422
    assert u.get("/privat/subscription", params={"session_id": "cs_" + "x" * 300}).status_code == 422
    r = u.get("/privat/subscription", params={"session_id": "cs_test_findes_ikke"})
    assert r.status_code < 500, f"ukendt/bogmærket session_id giver {r.status_code} {r.text[:120]} (F-PK-02)"


def test_sub20_portal_without_customer_is_501_not_configured():
    r = U("sub20").post("/privat/subscription/portal")
    assert (r.status_code, r.json()["code"]) == (501, "not_configured")


def test_ent01_basis_gets_needs_plan_for_every_plus_app():
    u = U("ent01")
    u.trial("basis")
    for k, a in u.addons().items():
        r = u.post(f"/privat/addons/{k}/enable")
        if a["status"] == "coming_soon":
            assert r.json()["code"] == "coming_soon", k
        elif "basis" in a["included_in"] or not a["included_in"]:
            assert r.status_code == 200, k
        else:
            assert (r.status_code, r.json()["code"], r.json()["plans"]) == (409, "needs_plan", ["plus", "familie"]), k


def test_ent09_free_account_can_enable_free_apps_but_chat_tasks_wait_as_drafts():
    f = U("ent09")
    for k in ("fest", "faelles-udgifter", "oenskelister", "delte-lister"):
        assert f.post(f"/privat/addons/{k}/enable").status_code == 200, k
    for k in ("madplan", "ring-for-mig"):
        assert f.post(f"/privat/addons/{k}/enable").json()["code"] == "needs_plan", k
    f.say("Lav en indkøbsliste med mælk og æg")
    assert [t["status"] for t in f.get("/privat/tasks").json()] == ["draft"]


def test_fun04_drafts_become_active_when_trial_starts():
    g = U("fun04")
    g.say("Lav en indkøbsliste med mælk og æg")
    g.say("Mind mig om at købe gave i morgen kl. 10")
    assert {t["status"] for t in g.get("/privat/tasks").json()} == {"draft"}
    g.trial()
    assert {t["status"] for t in g.get("/privat/tasks").json()} == {"in_progress", "planned"}
    assert any(o["event_type"] == "privat.reminder" and o["status"] == "queued" for o in g.get("/dev/outbox").json()["items"])


# ------------------------------------------------------------------------------------------------ Butikken (SHOP)
def test_shop04_enable_disable_idempotent_and_parallel():
    u = U("shop04")
    u.trial()
    assert u.post("/privat/addons/madplan/enable").status_code == 200
    e1 = u.addons()["madplan"]["enabled_at"]
    assert u.post("/privat/addons/madplan/enable").status_code == 200
    assert u.addons()["madplan"]["enabled_at"] == e1
    assert [u.post("/privat/addons/madplan/disable").status_code for _ in range(2)] == [200, 200]
    with cf.ThreadPoolExecutor(4) as ex:
        assert set(ex.map(lambda i: u.post(f"/privat/addons/regninger/{'enable' if i % 2 else 'disable'}").status_code, range(6))) == {200}
    assert sql("select key, count(*) from private_addon_enabled group by workspace_id, key having count(*) > 1") == []


def test_shop05_06_ring_for_mig_cascade():
    u = U("shop05")
    u.trial()
    deps = ["bil-og-syn", "laege-og-tandlaege", "abonnementer", "haandvaerker", "kaeledyr"]
    for k in deps:
        u.post(f"/privat/addons/{k}/enable")
    u.post("/privat/addons/ring-for-mig/disable")
    st = u.addons()
    assert not any(st[k]["enabled"] for k in deps + ["ring-for-mig"])
    u.post("/privat/addons/bil-og-syn/enable")  # SHOP-06: requires → Ring for mig comes on by itself
    st = u.addons()
    assert st["bil-og-syn"]["enabled"] and st["ring-for-mig"]["enabled"]


def test_shop07_08_09_coming_soon_setup_and_data():
    u = U("shop07")
    u.trial()
    for k in ("pakker", "rejser"):
        assert u.post(f"/privat/addons/{k}/enable").json()["code"] == "coming_soon"
        assert u.post(f"/privat/addons/{k}/notify").status_code == 200
        assert u.post(f"/privat/addons/{k}/notify").status_code == 200
        assert u.addons()[k]["notify_requested"] is True
    u.post("/privat/addons/foedselsdage/enable")
    total = u.addons()["foedselsdage"]["setup"]["total"]
    codes = {d: u.put("/privat/addons/foedselsdage/setup", json={"done": d}).status_code for d in (-1, 0, total, total + 1, 21)}
    assert codes == {-1: 422, 0: 200, total: 200, total + 1: 422, 21: 422}
    u.post("/privat/addons/flytning/disable")
    assert u.put("/privat/addons/flytning/setup", json={"done": 1}).json()["code"] == "addon_disabled"
    assert u.delete("/privat/addons/foedselsdage/data").json()["code"] == "addon_enabled"
    for k in ("ring-for-mig", "delte-lister", "oenskelister", "kalender", "rejser"):
        u.post(f"/privat/addons/{k}/disable")
        assert u.delete(f"/privat/addons/{k}/data").json()["code"] == "not_deletable", k
        assert u.addons()[k]["data_deletable"] is False
    u.post("/privat/addons/foedselsdage/disable")
    assert u.delete("/privat/addons/foedselsdage/data").status_code == 200


def test_shop03_unknown_keys_404():
    u = U("shop03")
    for k in ("ukendt", "MADPLAN", "mad%20plan"):
        assert u.post(f"/privat/addons/{k}/enable").status_code == 404, k


# ------------------------------------------------------------------------------------------------ chat, påmindelser, lister
def test_chat01_same_idempotency_key_replays_one_task():
    u = U("chat01")
    u.trial()
    k = str(uuid.uuid4())
    a = u.post("/privat/messages", json={"text": "Lav en indkøbsliste med mælk, æg og rugbrød"}, headers={"Idempotency-Key": k})
    b = u.post("/privat/messages", json={"text": "Lav en indkøbsliste med mælk, æg og rugbrød"}, headers={"Idempotency-Key": k})
    assert a.status_code == b.status_code == 200 and a.json() == b.json()
    tasks = u.get("/privat/tasks").json()
    assert len(tasks) == 1
    assert [i["text"] for i in u.get(f"/privat/tasks/{tasks[0]['id']}").json()["items"]] == ["Mælk", "Æg", "Rugbrød"]


def test_chat08_assistant_name():
    u = U("chat08")
    u.trial()
    assert u.patch("/privat/me/assistant", json={"name": "Kim", "pronoun": "hun"}).json()["assistant_name"] == "Kim"
    assert u.patch("/privat/me/assistant", json={"name": ""}).json()["assistant_name"] == "Peter"
    assert u.patch("/privat/me/assistant", json={"name": "x" * 21}).status_code == 422
    assert u.patch("/privat/me/assistant", json={"name": "🦊 Ræv"}).status_code == 422


def test_rem01_02_03_reminder_time_move_and_done_task_not_sent():
    u = U("rem")
    u.trial()
    a = u.make("Mind mig om at ringe til mor i morgen kl. 9")
    t = u.get(f"/privat/tasks/{a}").json()
    assert t["remind_at"].endswith(("T08:00:00+00:00", "T07:00:00+00:00"))  # 09:00 Europe/Copenhagen (CET/CEST)
    r = u.post("/privat/messages", json={"text": "Flyt den til fredag kl. 10", "about_task_id": a})
    assert any(m["kind"] == "move" for m in r.json()["messages"])
    evs = [o for o in u.get("/dev/outbox").json()["items"] if o["event_type"] == "privat.reminder"]
    assert sorted(o["status"] for o in evs) == ["blocked", "queued"]
    b = u.make("Mind mig om at vande blomster i morgen kl. 10")
    sql("update private_tasks set status='done' where id=%s", b)
    sql("update outbox_events set next_attempt_at=now() - interval '1 minute' where event_type='privat.reminder' and payload->>'task_id'=%s", b)
    for _ in range(30):
        if sql("select status from outbox_events where event_type='privat.reminder' and payload->>'task_id'=%s", b)[0][0] != "queued":
            break
        time.sleep(1)
    assert not [m for m in u.get("/dev/mailbox").json()["items"] if "Vande blomster" in m["subject"]]


def test_list01_items_limits_and_list03_status_filter():
    u = U("list01")
    u.trial()
    lid = u.make("Lav en indkøbsliste med mel og gær")
    assert u.post(f"/privat/tasks/{lid}/items", json={"text": ""}).status_code == 422
    assert u.post(f"/privat/tasks/{lid}/items", json={"text": "   "}).status_code == 422
    assert u.post(f"/privat/tasks/{lid}/items", json={"text": "x" * 301}).status_code == 422
    assert u.post(f"/privat/tasks/{lid}/items", json={"text": "🥚 Æg 🐣"}).status_code == 200
    it = u.get(f"/privat/tasks/{lid}").json()["items"][-1]["id"]
    assert [u.delete(f"/privat/tasks/{lid}/items/{it}").status_code for _ in range(2)] == [200, 404]
    assert u.get("/privat/tasks", params={"status": "bogus"}).status_code < 500


# ------------------------------------------------------------------------------------------------ deling, invitationer, grupper
def _shared_list(owner: U, role="editor", mode="group"):
    lid = owner.make("Lav en ønskeliste med cykel, bog og lego" if mode == "wishlist" else "Lav en indkøbsliste med mel og gær")
    sh = owner.post(f"/privat/tasks/{lid}/share", json={"mode": mode, "role": role}).json()
    return lid, sh


def test_inv01_share_returns_text_and_no_sms_is_queued():
    o = U("inv01", "Olivia Ejer")
    o.trial()
    lid, sh = _shared_list(o, mode="wishlist", role="viewer")
    assert sh["short_url"].endswith(sh["short_code"]) and len(sh["suggested_text"]) <= 160
    assert not [x for x in o.get("/dev/outbox").json()["items"] if "sms" in x["event_type"]]


def test_inv02_share_group_payload_for_own_phone():
    o = U("inv02", "Olivia Ejer")
    o.trial()
    nums = [f"2{random.randint(1000000, 9999999)}" for _ in range(3)]
    g = o.post("/privat/groups", json={"name": "Familien", "members": [{"name": n, "phone": p} for n, p in zip("ABC", nums)]}).json()
    lid = o.make("Lav en indkøbsliste med mel og gær")
    gs = o.post(f"/privat/tasks/{lid}/share-group", json={"group_id": g["id"], "mode": "group", "style": "group_sms"}).json()
    assert sorted(gs["sms_group"]["recipients"]) == sorted(f"+45{n}" for n in nums) and gs["sms_queue"] is None
    one = o.post(f"/privat/tasks/{lid}/share-group", json={"group_id": g["id"], "mode": "group", "style": "one_by_one"}).json()
    assert [q["body"].startswith(f"Hej {q['name']}!") for q in one["sms_queue"]] == [True] * 3
    assert not [x for x in o.get("/dev/outbox").json()["items"] if "sms" in x["event_type"]]
    log = open("/home/claude/pd-api.log").read() if os.path.exists("/home/claude/pd-api.log") else ""
    assert not any(n in line for line in log.splitlines() if "sms.simulated" in line for n in nums)


def test_inv06_07_09_10_accept_twice_own_revoke_expiry():
    o = U("inv", "Olivia Ejer")
    o.trial()
    lid, sh = _shared_list(o)
    g = U("g", "Gustav Gæst", account=False)
    assert g.post(f"/privat/invites/by-code/{sh['short_code']}/accept").status_code == 200
    assert g.post(f"/privat/invites/by-code/{sh['short_code']}/accept").status_code == 200
    assert o.post(f"/privat/invites/by-code/{sh['short_code']}/accept").json() == {}
    assert sorted(m["role"] for m in o.get(f"/privat/tasks/{lid}/members").json()) == ["editor", "owner"]
    for _ in range(40):  # «X har sagt ja» goes out via the worker
        if any("Gustav har sagt ja" in m["subject"] for m in o.get("/dev/mailbox").json()["items"]):
            break
        time.sleep(0.5)
    else:
        pytest.fail("ejeren fik ingen «Gustav har sagt ja»-e-mail")
    o.post(f"/privat/tasks/{lid}/share/revoke")
    pub = lambda c: httpx.get(f"{API}/api/v1/privat/invites/by-code/{c}", headers={"x-real-ip": ip()})  # noqa: E731
    assert pub(sh["short_code"]).json()["code"] == "invite_invalid"
    assert g.get(f"/privat/tasks/{lid}").status_code == 200
    sh2 = o.post(f"/privat/tasks/{lid}/share", json={"mode": "group"}).json()
    sql("update private_invites set expires_at=now() - interval '1 minute' where short_code=%s", sh2["short_code"])
    assert pub(sh2["short_code"]).json() == {**pub("ZZZZZZZZ").json(), "request_id": pub(sh2["short_code"]).json()["request_id"]} or \
        pub(sh2["short_code"]).json()["code"] == "invite_invalid"


def test_share01_02_03_04_roles_leave_pause_mode_lock():
    o = U("share", "Olivia Ejer")
    o.trial()
    lid, she = _shared_list(o, role="editor")
    shv = o.post(f"/privat/tasks/{lid}/share", json={"mode": "group", "role": "viewer"}).json()
    e, v = U("e", "Anna Editor", account=False), U("v", "Viggo Viewer", account=False)
    e.post(f"/privat/invites/by-code/{she['short_code']}/accept")
    v.post(f"/privat/invites/by-code/{shv['short_code']}/accept")
    item = o.get(f"/privat/tasks/{lid}").json()["items"][0]["id"]
    assert v.post(f"/privat/tasks/{lid}/items", json={"text": "Salt"}).json()["code"] == "read_only"
    assert v.post(f"/privat/tasks/{lid}/items/{item}/toggle").json()["code"] == "read_only"
    assert e.post(f"/privat/tasks/{lid}/items/{item}/toggle").status_code == 200
    assert o.get(f"/privat/tasks/{lid}").json()["items"][0]["done_by_name"] == "Anna Editor"
    assert o.post(f"/privat/tasks/{lid}/share", json={"mode": "wishlist"}).json()["code"] == "share_mode_locked"
    vm = next(m for m in o.get(f"/privat/tasks/{lid}/members").json() if m["name"].startswith("Viggo"))
    o.delete(f"/privat/tasks/{lid}/members/{vm['id']}")
    assert v.get(f"/privat/tasks/{lid}").status_code == 404
    om = next(m for m in o.get(f"/privat/tasks/{lid}/members").json() if m["role"] == "owner")
    assert o.delete(f"/privat/tasks/{lid}/members/{om['id']}").json()["code"] == "owner_cannot_leave"
    link = o.post(f"/privat/tasks/{lid}/share", json={"mode": "group"}).json()["short_code"]
    o.post("/privat/addons/delte-lister/disable")
    assert e.get(f"/privat/tasks/{lid}").json()["code"] == "sharing_paused"
    o.post("/privat/addons/delte-lister/enable")
    assert e.get(f"/privat/tasks/{lid}").status_code == 200
    assert httpx.get(f"{API}/api/v1/privat/invites/by-code/{link}", headers={"x-real-ip": ip()}).status_code == 404


def test_grp01_05_groups_owner_only_cascade_and_join_attempts():
    o = U("grp", "Olivia Ejer")
    o.trial()
    g = o.post("/privat/groups", json={"name": "Familien", "members": [{"name": "Anna", "phone": f"2{random.randint(10**6, 9999999)}"}, {"name": "Erik"}]}).json()
    assert U("x").get("/privat/groups").json() == []
    assert o.patch(f"/privat/groups/{g['id']}", json={"name": "Familien Hansen"}).status_code == 200
    assert o.delete(f"/privat/groups/{g['id']}").status_code == 204
    assert sql("select count(*) from private_group_members where group_id=%s", g["id"]) == [(0,)]
    g2 = o.post("/privat/groups", json={"name": "Venner", "members": []}).json()
    code = o.post(f"/privat/groups/{g2['id']}/join-link").json()["short_code"]
    h = {**CSRF, "x-real-ip": ip()}
    assert httpx.post(f"{API}/api/v1/privat/group-invites/by-code/{code}/join", headers=h, json={"name": "Kun Navn"}).json()["joined"] is True
    ph = f"2{random.randint(10**6, 9999999)}"
    assert httpx.post(f"{API}/api/v1/privat/group-invites/by-code/{code}/join", headers=h, json={"name": "N", "phone": ph}).json()["code_sent"] is True
    codes = [httpx.post(f"{API}/api/v1/privat/group-invites/by-code/{code}/join", headers=h, json={"name": "N", "phone": ph, "code": "000000"}).json().get("code") for _ in range(6)]
    assert codes[-1] == "too_many_attempts"


# ------------------------------------------------------------------------------------------------ ønskelister og fællesgaver
def _owner_scan(o: U, lid: str) -> list[str]:
    bad = []
    for path in (f"/privat/tasks/{lid}", "/privat/tasks", "/privat/day", "/privat/messages", f"/privat/tasks/{lid}/invite-status",
                 f"/privat/tasks/{lid}/members", "/dev/mailbox"):
        txt = o.get(path).text
        for pat in (r'"reserved":\s*true', r"reserveret", r"pledge", r"participant", r"coordinator", r'"done":\s*true', r"købt"):
            if re.search(pat, txt):
                bad.append(f"{path}: {pat}")
    return bad


def test_wish06_07_race_unreserve_and_owner_never_sees():
    o = U("wish", "Olivia Ejer")
    o.trial()
    lid, sh = _shared_list(o, role="viewer", mode="wishlist")
    a, b = U("a", "Gustav Gæst", account=False), U("b", "Gerda Gæst", account=False)
    for g in (a, b):
        g.post(f"/privat/invites/by-code/{sh['short_code']}/accept")
    item = o.get(f"/privat/tasks/{lid}").json()["items"][0]["id"]
    with cf.ThreadPoolExecutor(2) as ex:
        rs = list(ex.map(lambda g: g.post(f"/privat/tasks/{lid}/items/{item}/reserve"), (a, b)))
    assert sorted(r.status_code for r in rs) == [200, 409]
    loser = b if rs[0].status_code == 200 else a
    assert loser.post(f"/privat/tasks/{lid}/items/{item}/unreserve").json()["code"] == "not_reserved_by_you"
    assert all(i["reserved"] is None for i in o.get(f"/privat/tasks/{lid}").json()["items"])
    assert _owner_scan(o, lid) == []


def test_gift02_03_coordinator_bought_leave_and_owner_never_sees():
    o = U("gift", "Olivia Ejer")
    o.trial()
    lid, sh = _shared_list(o, role="viewer", mode="wishlist")
    item = o.get(f"/privat/tasks/{lid}").json()["items"][2]["id"]
    assert o.patch(f"/privat/tasks/{lid}/wishes/{item}", json={"group_gift_enabled": True, "group_gift_target_minor": 150000}).status_code == 200
    g, h, k = (U(t, n, account=False) for t, n in (("g", "Gustav"), ("h", "Hanne"), ("k", "Karl")))
    for x in (g, h, k):
        x.post(f"/privat/invites/by-code/{sh['short_code']}/accept")
    assert g.put(f"/privat/tasks/{lid}/items/{item}/gift/pledge", json={"amount_minor": 50000}).status_code == 200
    assert h.put(f"/privat/tasks/{lid}/items/{item}/gift/pledge", json={"amount_minor": 30000}).status_code == 200
    assert o.put(f"/privat/tasks/{lid}/items/{item}/gift/pledge", json={"amount_minor": 100}).status_code == 403
    assert k.post(f"/privat/tasks/{lid}/items/{item}/reserve").json()["code"] == "group_gift_active"
    g.post(f"/privat/tasks/{lid}/items/{item}/gift/coordinator", json={"action": "take"})
    assert h.post(f"/privat/tasks/{lid}/items/{item}/gift/bought", json={"bought": True}).json()["code"] == "not_coordinator"
    ref = next(p["user_ref"] for p in g.get(f"/privat/tasks/{lid}").json()["items"][2]["group_gift"]["participant_names"] if p["name"] == "Hanne")
    g.post(f"/privat/tasks/{lid}/items/{item}/gift/coordinator", json={"action": "transfer", "to": ref})
    h.post(f"/privat/tasks/{lid}/items/{item}/gift/coordinator", json={"action": "accept"})
    me = next(m for m in g.get(f"/privat/tasks/{lid}/members").json() if m.get("is_me"))
    g.delete(f"/privat/tasks/{lid}/members/{me['id']}")
    assert sorted(sql("select p.status from private_gift_pledges p join private_group_gifts gg on gg.id=p.gift_id where gg.task_id=%s", lid)) == [("active",), ("cancelled",)]
    assert h.post(f"/privat/tasks/{lid}/items/{item}/gift/bought", json={"bought": True}).status_code == 200
    assert o.get(f"/privat/tasks/{lid}").json()["items"][2]["group_gift"] == {"enabled": True, "target_minor": 150000, "currency": "DKK"}
    assert _owner_scan(o, lid) == []


def test_wish08_12_13_guest_without_plan_and_design_and_search():
    o = U("w8", "Olivia Ejer")
    o.trial()
    lid, sh = _shared_list(o, role="viewer", mode="wishlist")
    g = U("g", "Gustav Gæst", account=False)
    g.post(f"/privat/invites/by-code/{sh['short_code']}/accept")
    item = o.get(f"/privat/tasks/{lid}").json()["items"][0]["id"]
    assert g.post(f"/privat/tasks/{lid}/items/{item}/reserve").status_code == 200
    assert g.get("/privat/subscription").json()["entitled"] is False
    assert g.post("/privat/addons/madplan/enable").json()["code"] == "needs_plan"
    assert g.get("/privat/businesses/search", params={"q": "frisør"}).status_code == 403
    g.say("Lav en indkøbsliste med mælk og æg")
    assert {t["status"] for t in g.get("/privat/tasks").json() if t["id"] != lid} == {"draft"}
    assert g.put(f"/privat/tasks/{lid}/design", json={"theme": "jul"}).json()["code"] == "read_only"
    assert o.put(f"/privat/tasks/{lid}/design", json={"theme": "jul"}).status_code == 200
    assert o.get("/privat/wishes/search", params={"q": "lego"}).json()["code"] == "search_unavailable"


# ------------------------------------------------------------------------------------------------ opkald (CALL)
def test_call_never_dialled_without_approval_and_once_after():
    o = U("call", "Olivia Ejer")
    o.trial()
    httpx.post(f"{API}/__qa/phone-verified", json={"email": o.email, "phone": "+4520304050"})
    tid = o.make("Ring til Tandlæge Holm på 86 12 34 56 og flyt min tid")
    time.sleep(2)
    assert not [d for d in dialled() if tid in json.dumps(d)]
    assert sql("select status from private_calls where task_id=%s", tid) == [("proposed",)]
    x = U("x")
    x.trial()
    assert x.post(f"/privat/calls/{tid}/approve", json={}).status_code == 404
    t2 = o.make("Ring til Frisør Lene på 20 30 40 50 og book en tid")
    o.post(f"/privat/calls/{t2}/decline")
    o.post(f"/privat/calls/{t2}/approve", json={})
    assert o.post(f"/privat/calls/{tid}/approve", json={}).status_code == 200
    for _ in range(20):
        if [d for d in dialled() if tid in json.dumps(d)]:
            break
        time.sleep(0.5)
    o.post(f"/privat/calls/{tid}/approve", json={})
    time.sleep(2)
    assert len([d for d in dialled() if tid in json.dumps(d)]) == 1
    assert not [d for d in dialled() if t2 in json.dumps(d)]


def test_call13_search_limit_and_addon_gate():
    o = U("c13")
    o.trial()
    assert U("np").get("/privat/businesses/search", params={"q": "x"}).status_code == 403
    o.post("/privat/addons/ring-for-mig/disable")
    assert o.get("/privat/businesses/search", params={"q": "x"}).json()["code"] == "addon_disabled"
    o.post("/privat/addons/ring-for-mig/enable")
    codes = [o.get("/privat/businesses/search", params={"q": f"frisør {i}"}).status_code for i in range(31)]
    assert codes[:30] == [200] * 30 and codes[30] == 429
