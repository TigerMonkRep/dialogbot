"""QA X10 + X12 (e2e-privat, P1) – API/DB level. The browser half: web/e2e/qa/privat/X10.spec.ts, X12.spec.ts.

X10: «Delte lister, påmindelser, invitationer fra brugerens eget nummer (SMS i outbox), kontaktimport på iPhone».
  The product's contract (invites.py / groups.py docstrings, privat.json share.ownPhone): Dialogbot NEVER sends an
  invitation itself – the web opens the user's OWN Messages app with a suggested text. So «outbox» here means: the
  payload the API hands the phone (recipients + body) is right, and no SMS/e-mail to an invitee is queued or sent
  (outbox rows + the fake SMS world). Numbers saved in a group are used only to give them back to the owner and to
  recognise people already on Dialogbot.
X12: «Butikken: hvert app-ikon → "Hvad den gør" → egen installér-flow; installér/afinstallér idempotent».
"""
from __future__ import annotations

import threading

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.models import OutboxEvent, PrivateAddonEnabled, PrivateTaskMember
from app.modules.integrations.connectors.fakes import WORLD
from app.modules.privat import invites as inv_mod
from app.worker import runner

GSM7 = inv_mod.GSM7


def _outbox(db) -> list[OutboxEvent]:
    db.expire_all()
    return db.query(OutboxEvent).all()


def _sms_world() -> list[dict]:
    with WORLD.lock:
        return list(WORLD.sms)


def _invitee_traffic(db, invitee_numbers: set[str], invitee_emails: set[str]) -> list[str]:
    """Anything queued or sent that is addressed to an invitee (they must never hear from Dialogbot)."""
    hits = []
    for ev in _outbox(db):
        blob = repr(ev.payload)
        if any(n in blob for n in invitee_numbers) or any(e in blob for e in invitee_emails):
            hits.append(f"outbox {ev.event_type}: {blob[:200]}")
    for s in _sms_world():
        if s["to"] in invitee_numbers:
            hits.append(f"sms to {s['to']}: {s['body'][:80]}")
    return hits


# ============================================================================ X10 – shared lists and invitations

def test_x10_list_invite_is_a_text_for_the_users_own_phone_and_nothing_is_sent(api, pv, db):
    mette = pv.account("x10-a@testmail.dk", "Mette Hansen")
    tid = pv.make_list(mette)
    before_out, before_sms = len(_outbox(db)), len(_sms_world())
    r = api.post(mette, f"/privat/tasks/{tid}/share", {"mode": "group", "role": "editor"})
    assert r.status_code == 200, r.text
    o = r.json()
    text = o["suggested_text"]
    # one SMS segment, GSM-7, signed with the user's first name, the short link without scheme
    assert len(text) <= 160 and all(ch in GSM7 for ch in text), text
    assert text.endswith("- Mette"), text
    assert o["short_url"].split("://", 1)[-1] in text and "/i/" in o["short_url"]
    assert "indkøbsliste" in text  # a shopping list says so
    # Dialogbot itself sends nothing: no outbox row, no SMS
    runner.drain()
    assert len(_sms_world()) == before_sms
    new = [e for e in _outbox(db)[before_out:] if "sms" in e.event_type or "invite" in e.event_type]
    assert new == []


def test_x10_group_share_returns_recipients_and_personal_texts_never_sends(api, pv, db):
    mette = pv.account("x10-b@testmail.dk", "Mette Hansen")
    tid = pv.make_list(mette, "Lav en liste med ting til sommerhuset: kul og tændvæske")
    g = api.post(mette, "/privat/groups", {"name": "Familien", "members": [
        {"name": "Ole Berg", "phone": "20 11 22 33"}, {"name": "Anna", "phone": "+45 21 11 22 33"},
        {"name": "Dublet", "phone": "4520112233"}, {"name": "Forkert", "phone": "123"}]})
    assert g.status_code == 201, g.text
    gj = g.json()
    assert [m["phone_e164"] for m in gj["members"]] == ["+4520112233", "+4521112233"]  # deduped, invalid dropped

    r = api.post(mette, f"/privat/tasks/{tid}/share-group", {"group_id": gj["id"], "mode": "group", "style": "group_sms"})
    assert r.status_code == 200, r.text
    sg = r.json()["sms_group"]
    assert sg["recipients"] == ["+4520112233", "+4521112233"]
    assert len(sg["body"]) <= 160 and all(ch in GSM7 for ch in sg["body"])

    r = api.post(mette, f"/privat/tasks/{tid}/share-group", {"group_id": gj["id"], "mode": "group", "style": "one_by_one"})
    q = r.json()["sms_queue"]
    assert [x["phone_e164"] for x in q] == ["+4520112233", "+4521112233"]
    assert q[0]["body"].startswith("Hej Ole!") and q[1]["body"].startswith("Hej Anna!")
    assert q[0]["short_url"] != q[1]["short_url"]  # personal links → invite-status per person
    st = api.get(mette, f"/privat/tasks/{tid}/invite-status").json()
    assert {(x["name"], x["status"]) for x in st} == {("Ole Berg", "invited"), ("Anna", "invited")}
    code = q[0]["short_url"].rsplit("/", 1)[1]
    assert api.c.get(f"/api/v1/privat/invites/by-code/{code}").status_code == 200
    st = api.get(mette, f"/privat/tasks/{tid}/invite-status").json()
    assert ("Ole Berg", "opened") in {(x["name"], x["status"]) for x in st}

    runner.drain()
    assert _invitee_traffic(db, {"+4520112233", "+4521112233"}, set()) == []


def test_x10_public_invite_preview_shows_no_items_and_no_contact_data(api, pv):
    mette = pv.account("x10-c@testmail.dk", "Mette Hansen")
    pv.verify_phone(mette, "+4520304050")
    tid = pv.make_list(mette, "Lav en indkøbsliste med hemmelig kage")
    o = api.post(mette, f"/privat/tasks/{tid}/share", {"mode": "group"}).json()
    body = api.c.get(f"/api/v1/privat/invites/{o['token']}").text
    for leak in ("kage", "x10-c@testmail.dk", "20304050", "Hansen"):
        assert leak not in body.lower() if leak.islower() else leak not in body, (leak, body)


def test_x10_a_typed_phone_number_reveals_and_enrols_a_stranger(api, pv, db):
    """Privacy probe. Mette types ANY number into a group («Mine folk»). If it is a verified Dialogbot Privat user, the
    API (a) tells her so (has_dialogbot) and (b) on «Del med gruppen» adds that person to her list without their
    consent and (c) shows her the person's real name. Expected (groups.py docstring: «Dialogbot never contacts them»,
    invites.py: «no recipient ever reaches the server»): typing a number must not reveal whether, or as whom, the
    number is registered, and nobody joins a list without saying yes."""
    stranger = pv.account("x10-stranger@testmail.dk", "Birgitte Stranger Sørensen")
    pv.verify_phone(stranger, "+4531313131")
    mette = pv.account("x10-d@testmail.dk", "Mette Hansen")
    tid = pv.make_list(mette, "Lav en indkøbsliste med mælk")
    g = api.post(mette, "/privat/groups", {"name": "Gæt", "members": [{"name": "?", "phone": "31313131"}]}).json()
    leaks = []
    if g["members"][0]["has_dialogbot"]:
        leaks.append("group_out.has_dialogbot=true for a number Mette typed")
    r = api.post(mette, f"/privat/tasks/{tid}/share-group", {"group_id": g["id"], "mode": "group", "style": "one_by_one"})
    assert r.status_code == 200, r.text
    db.expire_all()
    joined = db.scalar(select(PrivateTaskMember).where(PrivateTaskMember.task_id == tid,
                                                       PrivateTaskMember.user_id == pv.uid(stranger)))
    if joined is not None:
        leaks.append("stranger added to Mette's list without accepting anything")
    members = api.get(mette, f"/privat/tasks/{tid}/members").text + api.get(mette, f"/privat/tasks/{tid}").text
    if "Birgitte" in members:
        leaks.append("Mette now sees the stranger's real name")
    assert leaks == [], leaks


# ============================================================================ X10 – reminders on the shared side

def test_x10_reminder_goes_to_its_creator_only(api, pv, db):
    mette = pv.account("x10-e@testmail.dk", "Mette Hansen")
    tid = pv.make_list(mette)
    o = api.post(mette, f"/privat/tasks/{tid}/share", {"mode": "group"}).json()
    ole = pv.account("x10-ole@testmail.dk", "Ole Berg")
    assert api.post(ole, f"/privat/invites/{o['token']}/accept").status_code == 200
    out = pv.say(ole, "Mind mig om at købe ind i morgen kl 16")
    rid = next(m["task_id"] for m in out["messages"] if m["kind"] == "task")
    evs = [e for e in _outbox(db) if e.event_type == "privat.reminder" and rid in e.dedupe_key]
    assert len(evs) == 1 and evs[0].payload["to_email"] == "x10-ole@testmail.dk"
    # Mette sees nothing of Ole's own reminder
    assert rid not in api.get(mette, "/privat/tasks").text
    assert api.get(mette, f"/privat/tasks/{rid}").status_code == 404


# ============================================================================ X12 – Butikken

def test_x12_every_app_has_what_it_does_and_its_own_setup_steps(api, pv):
    mette = pv.account("x12-a@testmail.dk", "Mette Hansen")
    apps = api.get(mette, "/privat/addons").json()
    assert len(apps) >= 15
    assert len({a["key"] for a in apps}) == len(apps)
    for a in apps:
        assert a["what"].strip(), a["key"]
        assert len(a["steps"]) >= 1, a["key"]
        assert a["name"] and a["icon"], a["key"]
        assert "{name}" not in a["what"] and "{" not in a["tagline"], a["key"]  # personalised


def test_x12_install_and_uninstall_are_idempotent_for_every_app(api, pv, db):
    mette = pv.account("x12-b@testmail.dk", "Mette Hansen")
    ws = pv.ws(mette)
    for a in api.get(mette, "/privat/addons").json():
        k = a["key"]
        if a["status"] == "coming_soon":
            r = api.post(mette, f"/privat/addons/{k}/enable")
            assert r.status_code == 409 and r.json()["code"] == "coming_soon", (k, r.text)
            continue
        r1 = api.post(mette, f"/privat/addons/{k}/enable")
        r2 = api.post(mette, f"/privat/addons/{k}/enable")
        assert (r1.status_code, r2.status_code) == (200, 200), (k, r1.text, r2.text)
        assert r1.json()["enabled"] and r2.json()["enabled_at"] == r1.json()["enabled_at"], k
        db.expire_all()
        assert db.query(PrivateAddonEnabled).filter_by(workspace_id=ws, key=k).count() == 1
        d1 = api.post(mette, f"/privat/addons/{k}/disable")
        d2 = api.post(mette, f"/privat/addons/{k}/disable")
        assert (d1.status_code, d2.status_code) == (200, 200), (k, d1.text, d2.text)
        assert not d2.json()["enabled"], k
        db.expire_all()
        assert db.query(PrivateAddonEnabled).filter_by(workspace_id=ws, key=k).count() == 0
        r3 = api.post(mette, f"/privat/addons/{k}/enable")  # and back on
        assert r3.status_code == 200 and r3.json()["enabled"], k
    assert api.post(mette, "/privat/addons/findes-ikke/enable").status_code == 404


def test_x12_plan_apps_need_the_trial_and_free_apps_do_not(api, pv):
    free = pv.account("x12-c@testmail.dk", "Ole Berg", trial=False)
    r = api.post(free, "/privat/addons/madplan/enable")
    assert r.status_code == 409 and r.json()["code"] == "needs_plan"
    assert api.post(free, "/privat/addons/fest/enable").status_code == 200  # free app, no plan


def _parallel(app, tok, path, n=6):
    barrier = threading.Barrier(n)
    codes: list[int] = []

    def go():
        c = TestClient(app)
        barrier.wait()
        codes.append(c.post(f"/api/v1{path}", headers={"Authorization": f"Bearer {tok}",
                                                         "x-requested-with": "dialogbot"}).status_code)

    ts = [threading.Thread(target=go) for _ in range(n)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    return codes


@pytest.mark.parametrize("key", ["madplan", "fest"])
def test_x12_double_tap_install_and_uninstall_never_500(api, pv, db, app, key):
    """A 60-year-old taps «Slå til» twice (or the phone retries): the second request must not fail with 500."""
    mette = pv.account(f"x12-d-{key}@testmail.dk", "Mette Hansen")
    ws = pv.ws(mette)
    on = _parallel(app, mette, f"/privat/addons/{key}/enable")
    db.expire_all()
    assert db.query(PrivateAddonEnabled).filter_by(workspace_id=ws, key=key).count() == 1
    off = _parallel(app, mette, f"/privat/addons/{key}/disable")
    db.expire_all()
    assert db.query(PrivateAddonEnabled).filter_by(workspace_id=ws, key=key).count() == 0
    assert all(c < 500 for c in on), ("enable", on)
    assert all(c < 500 for c in off), ("disable", off)


def test_x12_reinstall_after_the_trial_ended_is_still_idempotent(api, pv):
    """An app that is already on answers «on» to another «Slå til» – also after the trial ended (it stays on by design,
    addons.py docstring), instead of 409 needs_plan for something the user already has."""
    mette = pv.account("x12-e@testmail.dk", "Mette Hansen")
    assert api.post(mette, "/privat/addons/madplan/enable").status_code == 200
    pv.expire_trial(mette)
    assert next(a for a in api.get(mette, "/privat/addons").json() if a["key"] == "madplan")["enabled"] is True
    r = api.post(mette, "/privat/addons/madplan/enable")
    assert r.status_code == 200, r.text


# ============================================================================ X04 – funnel gate = login?

@pytest.mark.parametrize("kind", ["privat", "erhverv"])
def test_x04_funnel_code_to_any_phone_must_not_log_into_an_existing_account(api, pv, db, kind):
    """S0 probe (F-P2-01-X04). The quiz-funnel's verify finds the user by the e-mail typed at the gate and logs them in
    (funnel/service.py _user_for: «user.funnel_login», proof sms_code) – but the SMS code went to the number typed at
    the same gate, which is never compared with anything the account owns. Whoever knows an e-mail address gets a
    session for that account with a code to their own phone."""
    victim = pv.user(f"x04-victim-{kind}@testmail.dk", "Victim Person")
    assert victim
    h = {"x-real-ip": f"10.4.0.{1 if kind == 'privat' else 2}"}
    d = api.c.post("/api/v1/funnel/drafts", json={"kind": kind}, headers=h).json()
    before = len(_sms_world())
    r = api.c.post(f"/api/v1/funnel/drafts/{d['id']}/gate", headers=h,
                   json={"name": "Attacker", "email": f"x04-victim-{kind}@testmail.dk", "phone": "29876543", "consent": True})
    assert r.status_code == 202, r.text
    sms = _sms_world()[before:]
    assert sms and sms[-1]["to"] == "+4529876543"
    import re
    code = re.search(r"\b(\d{6})\b", sms[-1]["body"]).group(1)
    from app.models import Session as UserSession
    from app.models import User
    victim_row = db.scalars(select(User).where(User.email_normalized == f"x04-victim-{kind}@testmail.dk")).one()
    pv_before, sessions_before = victim_row.phone_verified_at, db.query(UserSession).filter_by(user_id=victim_row.id).count()
    v = api.c.post(f"/api/v1/funnel/drafts/{d['id']}/verify", json={"code": code}, headers=h)
    # the owner's account is untouched: no session minted, phone_verified_at not set by the attacker's code
    assert v.status_code == 409 and v.json()["code"] == "account_exists", v.text
    db.expire_all()
    assert db.get(User, victim_row.id).phone_verified_at == pv_before
    assert db.query(UserSession).filter_by(user_id=victim_row.id).count() == sessions_before
    me = None
    if v.status_code == 200:
        tok = v.json()["session_token"]
        me = api.c.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {tok}"}).json()
    assert me is None or me.get("email") != f"x04-victim-{kind}@testmail.dk", \
        f"the attacker's phone code opened the victim's account: {v.status_code} {me}"
