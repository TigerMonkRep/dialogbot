"""QA journey audit, Dialogbot Privat (F-JP-*): follow the real person through sign-up, mails, SMS and links.

Background: live bug 11/11 (PR #179) – a Privat sign-up got the blue Erhverv verify mail and the link led into the
Erhverv set-up. These tests follow the same person across screens, API, outbox and mails, and render every mail with
email_templates (html + text + links). Each test that fails on production (origin/main 1140a1c + #179) is
xfail(strict=True) with its finding id, so it turns into an XPASS (= a failure) the day the bug is fixed.

Nothing is ever really sent: mails go through the simulated adapter and are captured; SMS go to the fake WORLD."""
from __future__ import annotations

import hashlib
import hmac
import json
import re
import time
from pathlib import Path

import pytest
from sqlalchemy import select

from app.config import get_settings
from app.models import OutboxEvent, User
from app.modules.integrations import email_templates as tpl
from app.worker import runner

ROOT = Path(__file__).resolve().parents[2]
WEB_APP = ROOT / "web" / "src" / "app"
ERHVERV_WORDS = ("AI-receptionist", "arbejdsrum", "virksomhed", "opsaetning", "/onboarding", "/app")
PASSWORD = "hemmelig-kode-1"


# --------------------------------------------------------------------------- helpers

@pytest.fixture
def mails(monkeypatch):
    """Every Email object the worker sends, with the outbox event it belongs to (still delivered as usual)."""
    sent: list[tuple[OutboxEvent, tpl.Email]] = []
    real = runner._send_mail

    def capture(db, ev, mail):
        sent.append((ev, mail))
        return real(db, ev, mail)

    monkeypatch.setattr(runner, "_send_mail", capture)
    return sent


def privat_signup(api, email: str, name: str = "Pia Privat", lang: str = "da", next_: str | None = None) -> str:
    """What /signup?next=<Privat route> does: signup_intent privat, the page's language and `next`, then log in."""
    r = api.c.post(f"{api.base}/auth/register", json={"email": email, "password": PASSWORD, "display_name": name,
                                                      "signup_intent": "privat", "interface_language": lang,
                                                      **({"next": next_} if next_ else {})})
    assert r.status_code == 201, r.text
    return api.login(email, PASSWORD)


def link_next(link: str) -> str | None:
    """The decoded `next` of a mailed link (what the web page reads with searchParams.get("next"))."""
    from urllib.parse import parse_qs, urlsplit

    return (parse_qs(urlsplit(link).query).get("next") or [None])[0]


def verify_from_mailbox(api, tok: str) -> str:
    """Click the link in the newest verify mail; returns the link."""
    runner.drain()
    items = api.c.get(f"{api.base}/dev/mailbox", headers=api.h(tok)).json()["items"]
    link = next(re.search(r"(http\S+verify-email\?\S+)", m["body_text"]).group(1) for m in items
                if "verify-email?token=" in m["body_text"])
    raw = re.search(r"token=([A-Za-z0-9_\-]+)", link).group(1)
    assert api.c.post(f"{api.base}/auth/verify-email", json={"token": raw}).status_code == 200
    return link


def assert_privat_mail(mail: tpl.Email, where: str) -> None:
    """The four rules for a Privat mail: audience (orange, Privat icon, «Dialogbot Privat»), no Erhverv words,
    links on Privat routes, a next action."""
    html, text = mail.html(), mail.text()
    assert mail.audience == "privat", f"{where}: audience={mail.audience!r} (blue Erhverv layout)"
    assert tpl.PRIVAT_ACCENT in html and tpl.ACCENT not in html, f"{where}: not the Privat orange"
    assert "/icons/privat-icon-192.png" in html, f"{where}: Erhverv icon"
    assert "Dialogbot Privat" in html, f"{where}: no «Dialogbot Privat» header"
    for w in ERHVERV_WORDS[:3]:
        assert w not in html and w not in text, f"{where}: Erhverv word {w!r}"


def stripe_webhook(client, event: dict, secret: str = "whsec_privat") -> dict:
    body = json.dumps(event).encode()
    ts = int(time.time())
    sig = hmac.new(secret.encode(), f"{ts}.".encode() + body, hashlib.sha256).hexdigest()
    return client.post("/api/v1/webhooks/stripe", content=body, headers={"stripe-signature": f"t={ts},v1={sig}"}).json()


def fake_stripe(monkeypatch):
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_x")
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_privat")
    get_settings.cache_clear()
    from app.modules.billing import stripe

    calls: list = []
    monkeypatch.setattr(stripe, "request", lambda m, p, d=None, **k: calls.append((m, p, d)) or
                        {"id": "cs_test_jp", "url": "https://checkout.stripe.com/c/pay/cs_test_jp"})
    return calls


def src(rel: str) -> str:
    return (WEB_APP.parent / rel).read_text(encoding="utf-8")


# --------------------------------------------------------------------------- what #179 fixed (must stay green)

def test_jp_verify_mail_is_privat_and_lands_on_a_privat_route(api, db, mails, pv):
    tok = privat_signup(api, "pia@testmail.dk")
    link = verify_from_mailbox(api, tok)
    assert link.endswith("&for=privat") or "&for=privat&" in link
    ev, mail = next((e, m) for e, m in mails if e.event_type == "email.verify_address")
    assert_privat_mail(mail, "verify")
    page = (WEB_APP / "verify-email" / "page.tsx").read_text(encoding="utf-8")
    # qa/privat-deep: without `next` on to the plans, opened (/privat/konto?planer=1)
    assert 'setAfter("/privat/konto?planer=1")' in page and (WEB_APP / "privat" / "(app)" / "konto" / "page.tsx").exists()


def test_jp_verify_mail_in_all_8_languages(api, mails, pv):
    for lang in ("da", "en", "de", "es", "fr", "it", "no", "sv"):
        privat_signup(api, f"pia-{lang}@testmail.dk", lang=lang)
    runner.drain()
    got = {m.lang: m for e, m in mails if e.event_type == "email.verify_address"}
    assert set(got) == {"da", "en", "de", "es", "fr", "it", "no", "sv"}
    for lang, m in got.items():
        assert_privat_mail(m, f"verify/{lang}")


# --------------------------------------------------------------------------- F-JP-01  «Prøv gratis» stops at e-mail

PLAN_NEXT = "/privat/konto?plan=plus&interval=month"


def test_jp01_try_free_goes_straight_to_checkout(api, pv, monkeypatch):
    """F-JP-01 (decision: the e-mail is confirmed BEFORE the checkout – kept). «Prøv gratis i 14 dage» →
    /privat/konto?plan=plus&interval=month → /signup?next=… (next goes to the API) → verify link carries that next →
    back on the plan → the checkout starts. Another browser works too: the way back is in the link, not localStorage."""
    fake_stripe(monkeypatch)
    tok = pv.unverified("ny@testmail.dk", next_=PLAN_NEXT)
    r = api.post(tok, "/privat/subscription/checkout", {"plan": "plus", "interval": "month", "locale": "da"})
    assert r.status_code == 403 and r.json()["code"] == "email_not_verified"  # deliberate: e-mail first
    link = pv.verify_link(tok)
    assert "for=privat" in link and link_next(link) == PLAN_NEXT, link
    pv.click_verify(link)
    r = api.post(tok, "/privat/subscription/checkout", {"plan": "plus", "interval": "month", "locale": "da"})
    assert r.status_code == 200, r.text
    # the web: the signup sends `next`, waits on the Privat verify page, and the verify page goes to `next`, where
    # /privat/konto?plan= starts the checkout by itself
    signup = (WEB_APP / "signup" / "page.tsx").read_text(encoding="utf-8")
    assert "next: privatNext(next)" in signup and "/verify-email?for=privat&next=" in signup
    verify = (WEB_APP / "verify-email" / "page.tsx").read_text(encoding="utf-8")
    assert "setAfter(next)" in verify


def test_jp01_verify_link_resumes_the_chosen_plan(api, pv):
    tok = privat_signup(api, "ny2@testmail.dk", next_=PLAN_NEXT)
    link = verify_from_mailbox(api, tok)
    assert link_next(link) == PLAN_NEXT, link
    page = (WEB_APP / "verify-email" / "page.tsx").read_text(encoding="utf-8")
    assert 'kind === "trial" ? t("verify.continuePrivat")' in page  # «Fortsæt til din prøveperiode» → the plan


def test_jp01_bad_next_is_dropped_never_an_open_redirect(api, pv):
    from app.modules.identity.privat_context import safe_next

    for bad in ("https://evil.example/privat", "//evil.example", "/\\evil.example", "/app", "/opsaetning/1",
                "/privat/../app", "/privatx", "/privat/ x", "javascript:alert(1)"):
        assert safe_next(bad) is None, bad
    for ok in ("/privat", "/privat/dag", PLAN_NEXT, "/g/ABCDEFGH", "/i/ABCDEFGH", "/privat/invitation/AB?accept=1"):
        assert safe_next(ok) == ok, ok
    tok = privat_signup(api, "ny3@testmail.dk", next_="//evil.example/privat")
    link = verify_from_mailbox(api, tok)
    assert "evil" not in link and link_next(link) is None


# --------------------------------------------------------------------------- F-JP-02  password reset → Erhverv

def test_jp02_reset_mail_is_privat(api, pv, mails):
    tok = privat_signup(api, "glemsom@testmail.dk")
    verify_from_mailbox(api, tok)
    assert api.post(tok, "/privat/account").status_code == 200
    assert api.c.post(f"{api.base}/auth/password/forgot", json={"email": "glemsom@testmail.dk"}).status_code == 202
    runner.drain()
    ev, mail = next((e, m) for e, m in mails if e.event_type == "email.password_reset")
    assert_privat_mail(mail, "reset")
    assert "for=privat" in mail.button_url


def test_jp02_erhverv_reset_mail_is_unchanged(api, mails):
    tok = api.user("ejer@testmail.dk")
    api.workspace(tok, "Hansen VVS")
    assert api.c.post(f"{api.base}/auth/password/forgot", json={"email": "ejer@testmail.dk"}).status_code == 202
    runner.drain()
    ev, mail = next((e, m) for e, m in mails if e.event_type == "email.password_reset")
    assert mail.audience == "erhverv" and "for=privat" not in mail.button_url

def test_jp02_after_reset_a_privat_user_lands_in_privat(api, pv):
    """Login without ?next: the API's user.home decides – /privat/dag for a Privat-only account, /app otherwise; the
    login page and /app (requireWorkspace) both follow it."""
    tok = pv.account("pia@testmail.dk")
    r = api.c.post(f"{api.base}/auth/login", json={"email": "pia@testmail.dk", "password": "CorrectHorse!42"})
    assert r.json()["user"]["home"] == "/privat/dag"
    assert api.c.get(f"{api.base}/auth/me", headers=api.h(tok)).json()["home"] == "/privat/dag"
    # a fresh Privat sign-up without a personal workspace yet is Privat too
    privat_signup(api, "ny@testmail.dk")
    r = api.c.post(f"{api.base}/auth/login", json={"email": "ny@testmail.dk", "password": PASSWORD})
    assert r.json()["user"]["home"] == "/privat/dag"
    # an Erhverv owner – and a Privat user who also has a company – go to /app
    api.workspace(tok, "Pias Frisør")
    assert api.c.get(f"{api.base}/auth/me", headers=api.h(tok)).json()["home"] == "/app"
    owner = api.user("ejer@testmail.dk")
    assert api.c.get(f"{api.base}/auth/me", headers=api.h(owner)).json()["home"] == "/app"
    login = (WEB_APP / "login" / "page.tsx").read_text(encoding="utf-8")
    assert "safeNext(params.get(\"next\"), home)" in login
    ws = src("lib/workspace.server.ts")
    assert 'me?.home === "/privat/dag"' in ws and 'redirect("/opsaetning/1")' not in ws
    reset = (WEB_APP / "password" / "reset" / "page.tsx").read_text(encoding="utf-8")
    assert "isPrivatContext(params)" in reset and "/login?reset=1${nextQuery(next)}" in reset


# --------------------------------------------------------------------------- F-JP-03  funnel welcome mail

def test_jp03_funnel_welcome_mail_is_privat(api, pv, db, mails, monkeypatch):
    from app.modules.funnel import service as funnel

    u = User(email="quiz@testmail.dk", email_normalized="quiz@testmail.dk", password_hash="x",
             display_name="Quiz Person", signup_intent=None, interface_language="da")
    db.add(u)
    db.flush()
    funnel._welcome(db, u, "privat")
    db.commit()
    runner.drain()
    ev, mail = next((e, m) for e, m in mails if (e.dedupe_key or "").startswith("funnel-welcome:"))
    assert_privat_mail(mail, "funnel welcome")
    assert "for=privat" in mail.button_url and link_next(mail.button_url) == "/privat/dag"


def test_jp03_funnel_account_resend_verify_is_privat(api, pv, db, mails):
    """A Privat funnel account is marked Privat, and «Send nyt link» gives the Privat verify mail – also for an older
    funnel account from before the fix (signup_intent NULL, but a personal workspace)."""
    from datetime import UTC, datetime
    from types import SimpleNamespace

    from app.core.security import hash_password
    from app.modules.funnel import service as funnel
    from app.modules.privat import deps

    d = SimpleNamespace(kind="privat", hook=None, gate={"email": "quiz2@testmail.dk", "name": "Quiz To"})
    monkey_welcome = funnel._welcome
    try:
        funnel._welcome = lambda *a, **k: None
        u = funnel._new_user(db, d, None)
    finally:
        funnel._welcome = monkey_welcome
    assert u.signup_intent == "privat"
    old = User(email="gammel@testmail.dk", email_normalized="gammel@testmail.dk", password_hash=hash_password(PASSWORD),
               display_name="Gammel Konto", signup_intent=None, interface_language="da", phone_verified_at=datetime.now(UTC))
    db.add(old)
    db.flush()
    deps.ensure_account(db, old)
    db.commit()
    tok = api.login("gammel@testmail.dk", PASSWORD)
    assert api.c.post(f"{api.base}/auth/verify-email/resend", headers=api.h(tok)).status_code == 202
    runner.drain()
    ev, mail = next((e, m) for e, m in mails if e.event_type == "email.verify_address")
    assert "for=privat" in ev.payload["link"]
    assert_privat_mail(mail, "resend verify (funnel account)")


# --------------------------------------------------------------------------- F-JP-04  /g group link → Erhverv sign-up

def test_jp04_group_link_login_is_privat(api, pv, mails):
    """/g/ and /i/ are Privat in the one shared rule (web/src/lib/privat-next.ts, used by signup, login, verify, forgot
    and reset) and in the API; a sign-up from a group link gets the Privat mail and returns to the group."""
    lib = src("lib/privat-next.ts")
    rule = re.search(r"const PRIVAT_NEXT = (/.+/);", lib).group(1)
    assert "g\\/" in rule and "i\\/" in rule, rule
    for page in ("signup", "login", "verify-email"):
        assert "privatNext(" in (WEB_APP / page / "page.tsx").read_text(encoding="utf-8"), page
    tok = privat_signup(api, "gruppe@testmail.dk", next_="/g/ABCDEFGH")
    link = verify_from_mailbox(api, tok)
    assert link_next(link) == "/g/ABCDEFGH"
    ev, mail = next((e, m) for e, m in mails if e.event_type == "email.verify_address")
    assert_privat_mail(mail, "verify from /g/")
    assert "prøveperiode" not in mail.text()


# --------------------------------------------------------------------------- F-JP-05  invitee loses the invitation

def test_jp05_invitee_can_open_the_list_after_signup(api, pv, client, mails):
    """The whole way for a new person a list was shared with (Fürster's decision: a FREE account, no trial, no plan):
    invitation → «Opret gratis konto» (/signup?next=/privat/invitation/<code>?accept=1) → Privat verify page (no accept
    before the e-mail) → the mail («…åbne listen», never «prøveperiode») → «Åbn listen» = next → accept → the list.
    No 403 anywhere, never /privat/konto."""
    statuses: list[tuple[str, int]] = []
    real = client.request

    def spy(method, url, *a, **k):
        r = real(method, url, *a, **k)
        statuses.append((f"{method} {url}", r.status_code))
        return r

    client.request = spy
    try:
        anna = pv.account("anna@testmail.dk", "Anna Ejer")
        tid = pv.make_list(anna, "Lav en ønskeliste med bog")
        r = api.post(anna, f"/privat/tasks/{tid}/share", {"mode": "wishlist", "role": "editor"})
        assert r.status_code == 200, r.text
        code = r.json()["short_code"]
        assert api.c.get(f"{api.base}/privat/invites/by-code/{code}").status_code == 200  # the public invitation page
        nxt = f"/privat/invitation/{code}?accept=1"
        ole = privat_signup(api, "ole@testmail.dk", "Ole Gæst", next_=nxt)
        link = verify_from_mailbox(api, ole)
        assert "for=privat" in link and link_next(link) == nxt, link
        ev, mail = next((e, m) for e, m in mails if e.event_type == "email.verify_address"
                        and e.payload["to_email"] == "ole@testmail.dk")
        assert_privat_mail(mail, "invitee verify")
        assert "prøveperiode" not in mail.text().lower() and "åbne listen" in mail.text(), mail.text()
        r = api.post(ole, f"/privat/invites/by-code/{code}/accept")
        assert r.status_code == 200, r.text
        task_id = r.json()["id"]
        r = api.get(ole, f"/privat/tasks/{task_id}")
        assert r.status_code == 200 and [i["text"] for i in r.json()["items"]] == ["Bog"], r.text
    finally:
        client.request = real
    assert not [s for s in statuses if s[1] == 403], statuses
    # the web half: free-account CTA on the invitation, signup waits on the verify page, «Fortsæt» goes to next
    pub = src("components/privat/public.tsx")
    assert 't("invitation.signupFree")' in pub and "/verify-email?for=privat&next=" in pub
    verify = (WEB_APP / "verify-email" / "page.tsx").read_text(encoding="utf-8")
    assert 'kind === "list" ? t("verify.continueList")' in verify
    signup = (WEB_APP / "signup" / "page.tsx").read_text(encoding="utf-8")
    assert 't("signup.freeSubtitle")' in signup
    for lang in ("da", "en", "de", "es", "fr", "it", "no", "sv"):
        auth = json.loads((WEB_APP.parent / "i18n" / "messages" / lang / "auth.json").read_text(encoding="utf-8"))
        assert auth["signup"]["freeSubtitle"] and auth["verify"]["subtitlePrivatList"], lang
        assert not re.search(r"14|Plus|prøve|trial|Test|prueba|essai|prova|prøve|provperiod",
                             auth["signup"]["freeSubtitle"]), (lang, auth["signup"]["freeSubtitle"])


# --------------------------------------------------------------------------- F-JP-06  service mails in Erhverv layout

def test_jp06_reminder_mail_is_privat(api, pv, db, mails):
    from datetime import UTC, datetime

    tok = pv.account("mette@testmail.dk")
    out = pv.say(tok, "Mind mig om at hente pakken i morgen kl 16")
    tid = out["messages"][2]["task_id"]
    db.query(OutboxEvent).filter(OutboxEvent.event_type == "privat.reminder",
                                 OutboxEvent.dedupe_key.like(f"privat-reminder:{tid}:%")).update(
        {"next_attempt_at": datetime.now(UTC)}, synchronize_session=False)
    db.commit()
    runner.drain()
    ev, mail = next((e, m) for e, m in mails if e.event_type == "privat.reminder")
    assert_privat_mail(mail, "reminder")


def test_jp06_invite_accepted_mail_is_privat(api, pv, mails):
    anna = pv.account("anna@testmail.dk", "Anna Ejer")
    ole = pv.user("ole@testmail.dk", "Ole Berg")
    tid = pv.make_list(anna)
    inv = api.post(anna, f"/privat/tasks/{tid}/share", {"mode": "group", "role": "editor"}).json()
    assert api.post(ole, f"/privat/invites/{inv['token']}/accept").status_code == 200
    runner.drain()
    ev, mail = next((e, m) for e, m in mails if (e.dedupe_key or "").startswith("privat-notify:invite-accepted"))
    assert_privat_mail(mail, "invite accepted")


def test_jp06_task_notice_mail_is_privat(api, pv, db, mails):
    from app.models import PrivateTask
    from app.modules.privat import service

    tok = pv.account("mette@testmail.dk")
    tid = pv.make_list(tok)
    task = db.get(PrivateTask, __import__("uuid").UUID(tid))
    service.notify_owner(db, task, subject="Opkaldet er klaret", text="Tandlægen har givet dig en tid.", dedupe="jp06")
    db.commit()
    runner.drain()
    ev, mail = next((e, m) for e, m in mails if (e.dedupe_key or "") == "privat-notify:jp06")
    assert mail.button_url and "/privat/opgaver/" in mail.button_url
    assert_privat_mail(mail, "task notice")


def test_jp06_no_privat_mail_without_audience():
    offenders = []
    for p in sorted((ROOT / "app" / "modules" / "privat").glob("*.py")):
        s = p.read_text(encoding="utf-8")
        for m in re.finditer(r"tpl\.Email\(", s):
            end = s.find("\n\n", m.start())
            if "audience" not in s[m.start(): end if end > 0 else m.start() + 800]:
                offenders.append(f"{p.name}:{s[:m.start()].count(chr(10)) + 1}")
    assert offenders == []


# --------------------------------------------------------------------------- F-JP-07  language

def test_jp07_reminder_mail_follows_user_language(api, pv, db, mails):
    from datetime import UTC, datetime

    tok = pv.account("mette@testmail.dk")
    db.query(User).filter(User.email_normalized == "mette@testmail.dk").update({"interface_language": "en"})
    db.commit()
    out = pv.say(tok, "Mind mig om at hente pakken i morgen kl 16")
    tid = out["messages"][2]["task_id"]
    db.query(OutboxEvent).filter(OutboxEvent.dedupe_key.like(f"privat-reminder:{tid}:%")).update(
        {"next_attempt_at": datetime.now(UTC)}, synchronize_session=False)
    db.commit()
    runner.drain()
    ev, mail = next((e, m) for e, m in mails if e.event_type == "privat.reminder")
    assert mail.lang == "en" and not mail.subject.startswith("Påmindelse"), (mail.lang, mail.subject)


def test_jp07_sms_code_follows_user_language(api, pv, db):
    from app.modules.integrations.connectors.fakes import WORLD

    tok = pv.account("mette@testmail.dk")
    db.query(User).filter(User.email_normalized == "mette@testmail.dk").update({"interface_language": "en"})
    db.commit()
    r = api.post(tok, "/privat/phone/start", {"phone": "+4520304050"})
    assert r.status_code in (200, 202), r.text
    assert "Din kode" not in WORLD.sms[-1]["body"], WORLD.sms[-1]["body"]


# --------------------------------------------------------------------------- F-JP-08  no next action

def test_jp08_reminder_mail_has_a_next_action(api, pv, db, mails):
    from datetime import UTC, datetime

    tok = pv.account("mette@testmail.dk")
    out = pv.say(tok, "Mind mig om at hente pakken i morgen kl 16")
    tid = out["messages"][2]["task_id"]
    db.query(OutboxEvent).filter(OutboxEvent.dedupe_key.like(f"privat-reminder:{tid}:%")).update(
        {"next_attempt_at": datetime.now(UTC)}, synchronize_session=False)
    db.commit()
    runner.drain()
    ev, mail = next((e, m) for e, m in mails if e.event_type == "privat.reminder")
    assert mail.button_url and "/privat/" in mail.button_url


def test_jp08_invite_accepted_has_a_next_action(api, pv, mails):
    anna = pv.account("anna@testmail.dk", "Anna Ejer")
    ole = pv.user("ole@testmail.dk", "Ole Berg")
    tid = pv.make_list(anna)
    inv = api.post(anna, f"/privat/tasks/{tid}/share", {"mode": "group", "role": "editor"}).json()
    api.post(ole, f"/privat/invites/{inv['token']}/accept")
    runner.drain()
    ev, mail = next((e, m) for e, m in mails if (e.dedupe_key or "").startswith("privat-notify:invite-accepted"))
    assert mail.button_url and "/privat/" in mail.button_url


# --------------------------------------------------------------------------- F-JP-09  billing mails / portal

# F-JP-09 (mail part) fixed on qa/privat-deep: billing.customer_mails → privat_mails.billing (F-PBQ-08)
def test_jp09_failed_renewal_sends_a_privat_mail(api, pv, client, db, monkeypatch):
    fake_stripe(monkeypatch)
    tok = pv.account("mette@testmail.dk")
    ws = pv.ws(tok)
    sub = {"id": f"sub_trial_{ws.hex[:8]}", "object": "subscription", "status": "past_due", "customer": "cus_test",
           "metadata": {"kind": "privat_subscription", "workspace_id": str(ws), "plan": "plus", "interval": "month"},
           "items": {"data": [{"price": {"recurring": {"interval": "month"}}, "current_period_end": int(time.time()) + 86400}]}}
    stripe_webhook(client, {"id": "evt_jp09a", "type": "customer.subscription.updated", "data": {"object": sub}})
    inv = {"id": "in_jp09", "object": "invoice", "customer": "cus_test", "subscription": sub["id"], "amount_due": 9900,
           "currency": "dkk", "attempt_count": 1, "status": "open",
           "subscription_details": {"metadata": sub["metadata"]}}
    stripe_webhook(client, {"id": "evt_jp09b", "type": "invoice.payment_failed", "data": {"object": inv}})
    db.expire_all()
    evs = db.scalars(select(OutboxEvent).where(OutboxEvent.event_type == "email.branded")).all()
    mails_ = [e for e in evs if e.payload.get("to_email") == "mette@testmail.dk"]
    assert mails_, "no mail queued for the failed renewal"
    assert tpl.from_payload(mails_[-1].payload).audience == "privat"


@pytest.mark.xfail(strict=True, reason="F-JP-09: the Stripe Billing Portal session (cancel, change plan, update card) "
                                       "carries no Privat configuration/branding – it shows the Erhverv account branding")
def test_jp09_portal_is_privat(api, pv, monkeypatch):
    calls = fake_stripe(monkeypatch)
    from app.modules.billing import stripe

    monkeypatch.setattr(stripe, "configured", lambda: True)
    tok = pv.account("mette@testmail.dk")
    r = api.post(tok, "/privat/subscription/portal")
    assert r.status_code == 200, r.text
    m, p, d = next(c for c in calls if c[1] == "/billing_portal/sessions")
    assert d.get("configuration"), d


# --------------------------------------------------------------------------- F-JP-10  /verify-email from the Privat app

def test_jp10_privat_banner_links_to_privat_verify_page():
    shell = src("components/privat/shell.tsx")
    assert 'href="/verify-email"' not in shell and "`/verify-email?for=privat${nextQuery(" in shell
    page = (WEB_APP / "verify-email" / "page.tsx").read_text(encoding="utf-8")
    assert "isPrivatContext(params)" in page  # ?for=privat or a Privat next → never the workspace/company subtitle


# --------------------------------------------------------------------------- F-JP-11  404 / error pages

def test_jp11_privat_has_its_own_404_and_error_page():
    have = [p for p in ("privat/not-found.tsx", "not-found.tsx") if (WEB_APP / p).exists()]
    err = [p for p in ("privat/error.tsx", "error.tsx", "global-error.tsx") if (WEB_APP / p).exists()]
    assert have and err, (have, err)
    # unknown /privat/… addresses reach the Privat 404 (catch-all → notFound()), and both pages are i18n, orange, with
    # a way back
    assert "notFound()" in (WEB_APP / "privat" / "[...rest]" / "page.tsx").read_text(encoding="utf-8")
    frame = src("components/privat/not-found-frame.tsx")
    assert 'data-theme="privat"' in frame
    for f in ("privat/not-found.tsx", "privat/error.tsx"):
        page = (WEB_APP / f).read_text(encoding="utf-8")
        assert 't("problem.' in page and "/privat/dag" in page, f
    for lang in ("da", "en", "de", "es", "fr", "it", "no", "sv"):
        msgs = json.loads((WEB_APP.parent / "i18n" / "messages" / lang / "privat.json").read_text(encoding="utf-8"))
        assert set(msgs["problem"]) >= {"notFoundTitle", "errorTitle", "toDay", "toHome", "retry"}, lang


# --------------------------------------------------------------------------- F-JP-12  Stripe Checkout colour

def test_jp12_checkout_button_is_the_accessible_orange():
    from app.modules.privat import branding

    assert branding.branding_settings()["button_color"].upper() == "#C4461A"


# --------------------------------------------------------------------------- F-JP-13  ?ref on /privat

@pytest.mark.xfail(strict=True, reason="F-JP-13: the invite page's brand card links to /privat?ref=<invite token>, but "
                                       "nothing reads ?ref – the referral is lost when the visitor starts their own trial")
def test_jp13_ref_on_privat_landing_is_used():
    files = [WEB_APP / "privat" / "page.tsx", WEB_APP.parent / "components" / "privat" / "account.tsx",
             WEB_APP / "signup" / "page.tsx", WEB_APP.parent / "proxy.ts"]
    assert any(re.search(r"""get\(["']ref["']\)""", f.read_text(encoding="utf-8")) for f in files)


# --------------------------------------------------------------------------- F-JP-14  expired session pitch

def test_jp14_expired_login_does_not_pitch_the_trial():
    login = (WEB_APP / "login" / "page.tsx").read_text(encoding="utf-8")
    assert re.search(r"expired[^\n]*privatSubtitle|privatSubtitle[^\n]*expired", login)


# --------------------------------------------------------------------------- F-JP-15  register in the #179 texts

def test_jp15_privat_verify_mail_keeps_one_register():
    formal = {"de": r"\bSie\b", "es": r"\b(usted|su)\b", "fr": r"\bvous\b", "it": r"\b(Lei|Suo|può)\b"}
    informal = {"de": r"\b(du|deine?)\b", "es": r"\b(tu|podrás|Confirma)\b", "fr": r"\b(ton|Confirme)\b",
                "it": r"\b(tuo|Conferma)\b"}
    mixed = []
    for lang in formal:
        m = tpl.verify("https://x/verify-email?token=t&for=privat", lang=lang, privat=True)
        whole = " ".join([m.paragraphs[0], m.note or "", m.footer_reason or ""])
        if re.search(informal[lang], m.paragraphs[0]) and re.search(formal[lang], whole):
            mixed.append(lang)
    assert mixed == []
