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


def privat_signup(api, email: str, name: str = "Pia Privat", lang: str = "da") -> str:
    """What /signup?next=/privat… does since #179: signup_intent privat, then log in."""
    r = api.c.post(f"{api.base}/auth/register", json={"email": email, "password": PASSWORD, "display_name": name,
                                                      "signup_intent": "privat", "interface_language": lang})
    assert r.status_code == 201, r.text
    return api.login(email, PASSWORD)


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
    assert link.endswith("&for=privat")
    ev, mail = next((e, m) for e, m in mails if e.event_type == "email.verify_address")
    assert_privat_mail(mail, "verify")
    page = (WEB_APP / "verify-email" / "page.tsx").read_text(encoding="utf-8")
    assert 'setAfter("/privat/konto")' in page and (WEB_APP / "privat" / "(app)" / "konto" / "page.tsx").exists()


def test_jp_verify_mail_in_all_8_languages(api, mails, pv):
    for lang in ("da", "en", "de", "es", "fr", "it", "no", "sv"):
        privat_signup(api, f"pia-{lang}@testmail.dk", lang=lang)
    runner.drain()
    got = {m.lang: m for e, m in mails if e.event_type == "email.verify_address"}
    assert set(got) == {"da", "en", "de", "es", "fr", "it", "no", "sv"}
    for lang, m in got.items():
        assert_privat_mail(m, f"verify/{lang}")


# --------------------------------------------------------------------------- F-JP-01  «Prøv gratis» stops at e-mail

@pytest.mark.xfail(strict=True, reason="F-JP-01: a new e-mail sign-up cannot reach Stripe Checkout before the e-mail "
                                       "is verified (403 email_not_verified)")
def test_jp01_try_free_goes_straight_to_checkout(api, pv, monkeypatch):
    fake_stripe(monkeypatch)
    tok = privat_signup(api, "ny@testmail.dk")
    # /privat «Prøv gratis i 14 dage» → /privat/konto?plan=plus&interval=month → /signup?next=… → back → checkout
    r = api.post(tok, "/privat/subscription/checkout", {"plan": "plus", "interval": "month", "locale": "da"})
    assert r.status_code == 200, r.text


@pytest.mark.xfail(strict=True, reason="F-JP-01: after the verify mail the person lands on /privat/konto without the "
                                       "plan they chose – the checkout does not resume")
def test_jp01_verify_link_resumes_the_chosen_plan(api, pv):
    tok = privat_signup(api, "ny2@testmail.dk")
    link = verify_from_mailbox(api, tok)
    page = (WEB_APP / "verify-email" / "page.tsx").read_text(encoding="utf-8")
    # either the link itself carries the chosen plan, or the verify page sends the person back to the ?plan= checkout
    assert "plan=" in link or re.search(r"privat/konto\?plan", page), link


# --------------------------------------------------------------------------- F-JP-02  password reset → Erhverv

@pytest.mark.xfail(strict=True, reason="F-JP-02: a Privat user's password-reset mail is the blue Erhverv mail")
def test_jp02_reset_mail_is_privat(api, pv, mails):
    tok = privat_signup(api, "glemsom@testmail.dk")
    verify_from_mailbox(api, tok)
    assert api.post(tok, "/privat/account").status_code == 200
    assert api.c.post(f"{api.base}/auth/password/forgot", json={"email": "glemsom@testmail.dk"}).status_code == 202
    runner.drain()
    ev, mail = next((e, m) for e, m in mails if e.event_type == "email.password_reset")
    assert_privat_mail(mail, "reset")


@pytest.mark.xfail(strict=True, reason="F-JP-02: after a reset (and any login without ?next) a Privat user is sent to "
                                       "/app → /opsaetning/1 (Erhverv set-up) – nothing routes a personal-only account "
                                       "to /privat")
def test_jp02_after_reset_a_privat_user_lands_in_privat():
    reset = (WEB_APP / "password" / "reset" / "page.tsx").read_text(encoding="utf-8")
    ws = src("lib/workspace.server.ts")
    # either the reset page keeps the Privat context, or /app sends a person without a business workspace to /privat
    assert "privat" in reset or "/privat" in ws


# --------------------------------------------------------------------------- F-JP-03  funnel welcome mail

@pytest.mark.xfail(strict=True, reason="F-JP-03: the Privat quiz-funnel's welcome mail («Vælg adgangskode») is the "
                                       "blue Erhverv mail, Danish only, and its link goes through the Erhverv reset")
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


@pytest.mark.xfail(strict=True, reason="F-JP-03: a Privat funnel account has signup_intent NULL, so a later «Send nyt "
                                       "link» gives the Erhverv verify mail («AI-receptionist», → /opsaetning/1)")
def test_jp03_funnel_account_resend_verify_is_privat(api, pv, db, mails):
    from app.modules.funnel import service as funnel

    src_ = Path(funnel.__file__).read_text(encoding="utf-8")
    m = re.search(r'signup_intent="reception" if d\.kind == "erhverv" else (\w+)', src_)
    assert m is None or m.group(1) != "None", "funnel privat account gets signup_intent=None"


# --------------------------------------------------------------------------- F-JP-04  /g group link → Erhverv sign-up

@pytest.mark.xfail(strict=True, reason="F-JP-04: /signup and /login treat only ?next=/privat… as Privat; the group "
                                       "link /g/<code> sends people to the Erhverv sign-up (intent=reception)")
def test_jp04_group_link_login_is_privat():
    signup = (WEB_APP / "signup" / "page.tsx").read_text(encoding="utf-8")
    m = re.search(r"const isPrivat = \(next: string \| null\) => (.+);", signup)
    assert m and "/g/" in m.group(1), m.group(1) if m else "isPrivat not found"


# --------------------------------------------------------------------------- F-JP-05  invitee loses the invitation

@pytest.mark.xfail(strict=True, reason="F-JP-05: a new person who signs up from a shared list/wishlist gets 403 "
                                       "email_not_verified on «Åbn listen», and the verify link then goes to the trial "
                                       "page (/privat/konto), not back to the list")
def test_jp05_invitee_can_open_the_list_after_signup(api, pv):
    anna = pv.account("anna@testmail.dk", "Anna Ejer")
    tid = pv.make_list(anna, "Lav en ønskeliste med bog")
    r = api.post(anna, f"/privat/tasks/{tid}/share", {"mode": "wishlist", "role": "editor"})
    assert r.status_code == 200, r.text
    inv = r.json()
    ole = privat_signup(api, "ole@testmail.dk", "Ole Gæst")
    r = api.post(ole, f"/privat/invites/{inv['token']}/accept")
    if r.status_code == 403:
        link = verify_from_mailbox(api, ole)
        assert "invitation" in link, f"verify link loses the invitation: {link}"
    else:
        assert r.status_code == 200, r.text


# --------------------------------------------------------------------------- F-JP-06  service mails in Erhverv layout

@pytest.mark.xfail(strict=True, reason="F-JP-06: the reminder mail is the blue Erhverv layout")
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


@pytest.mark.xfail(strict=True, reason="F-JP-06: «X har sagt ja til din invitation» is the blue Erhverv layout")
def test_jp06_invite_accepted_mail_is_privat(api, pv, mails):
    anna = pv.account("anna@testmail.dk", "Anna Ejer")
    ole = pv.user("ole@testmail.dk", "Ole Berg")
    tid = pv.make_list(anna)
    inv = api.post(anna, f"/privat/tasks/{tid}/share", {"mode": "group", "role": "editor"}).json()
    assert api.post(ole, f"/privat/invites/{inv['token']}/accept").status_code == 200
    runner.drain()
    ev, mail = next((e, m) for e, m in mails if (e.dedupe_key or "").startswith("privat-notify:invite-accepted"))
    assert_privat_mail(mail, "invite accepted")


@pytest.mark.xfail(strict=True, reason="F-JP-06: call outcomes and task notices (notify_owner) are the blue Erhverv layout")
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


@pytest.mark.xfail(strict=True, reason="F-JP-06: tpl.Email(...) under app/modules/privat without audience='privat'")
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

@pytest.mark.xfail(strict=True, reason="F-JP-07: Privat service mails are Danish whatever the user's language")
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


@pytest.mark.xfail(strict=True, reason="F-JP-07: the SMS code is Danish for every language")
def test_jp07_sms_code_follows_user_language(api, pv, db):
    from app.modules.integrations.connectors.fakes import WORLD

    tok = pv.account("mette@testmail.dk")
    db.query(User).filter(User.email_normalized == "mette@testmail.dk").update({"interface_language": "en"})
    db.commit()
    r = api.post(tok, "/privat/phone/start", {"phone": "+4520304050"})
    assert r.status_code in (200, 202), r.text
    assert "Din kode" not in WORLD.sms[-1]["body"], WORLD.sms[-1]["body"]


# --------------------------------------------------------------------------- F-JP-08  no next action

@pytest.mark.xfail(strict=True, reason="F-JP-08: reminder mail has no button/link – no next action")
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


@pytest.mark.xfail(strict=True, reason="F-JP-08: «X har sagt ja» mail has no link to the list (push url is None too)")
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

@pytest.mark.xfail(strict=True, reason="F-JP-09: Dialogbot sends no Privat mail when a renewal fails (only Stripe's "
                                       "account-level, Erhverv-branded mail, if any)")
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

@pytest.mark.xfail(strict=True, reason="F-JP-10: «Bekræft din e-mail» in the Privat app links to /verify-email without "
                                       "?for=privat – Erhverv frame and «arbejdsrummet … oprette virksomheder»")
def test_jp10_privat_banner_links_to_privat_verify_page():
    shell = src("components/privat/shell.tsx")
    assert 'href="/verify-email"' not in shell


# --------------------------------------------------------------------------- F-JP-11  404 / error pages

@pytest.mark.xfail(strict=True, reason="F-JP-11: no not-found/error page at all – an unknown /privat/… URL shows Next's "
                                       "default English 404, no Privat theme, no way back")
def test_jp11_privat_has_its_own_404_and_error_page():
    have = [p for p in ("privat/not-found.tsx", "not-found.tsx") if (WEB_APP / p).exists()]
    err = [p for p in ("privat/error.tsx", "error.tsx", "global-error.tsx") if (WEB_APP / p).exists()]
    assert have and err, (have, err)


# --------------------------------------------------------------------------- F-JP-12  Stripe Checkout colour

@pytest.mark.xfail(strict=True, reason="F-JP-12: the Privat Checkout button is #E0521A (white text 3.9:1), not the "
                                       "accessible #C4461A used everywhere else in the app")
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

@pytest.mark.xfail(strict=True, reason="F-JP-14: a paying Privat user whose session expired sees «14 dage gratis med "
                                       "Plus» on the login page")
def test_jp14_expired_login_does_not_pitch_the_trial():
    login = (WEB_APP / "login" / "page.tsx").read_text(encoding="utf-8")
    assert re.search(r"expired[^\n]*privatSubtitle|privatSubtitle[^\n]*expired", login)


# --------------------------------------------------------------------------- F-JP-15  register in the #179 texts

@pytest.mark.xfail(strict=True, reason="F-JP-15: the #179 Privat verify texts say «du» (de/es/fr/it) inside a mail whose "
                                       "other lines say «Sie/usted/vous/Lei»")
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
