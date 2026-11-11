"""Journey audit Erhverv (F-JE-*): follow the REAL user through every touchpoint – mails and links included.

Background: live 11/11 a Dialogbot Privat sign-up got the blue Erhverv verify mail and landed in the Erhverv set-up
(fixed in PR #179). The same class of defect is hunted here on origin/main + #179:
- every mail is rendered with app.modules.integrations.email_templates (html + text) from the outbox payload the API
  really queued, and every link in it is resolved against web/src/app + next.config redirects (tests/qa/qa_routes.py);
- Erhverv branding: blue #2456F6, the wordmark «Dialogbot», the Erhverv icon – never the Privat orange #C4461A;
- the language: the 8 languages of app.core.languages;
- where the next button leads (verify → onboarding → opsætningsguide → lancering).

Passing tests document touchpoints that are OK. Each `xfail(strict=True)` is an open finding in qa/findings/F-JE-*.md;
it turns into an XPASS (= red) the moment the defect is fixed, so the marker must then be removed.

Run: source /home/claude/qa-env.sh; TEST_DATABASE_URL=…/qa_audit_erh python -m pytest tests/qa/test_qa_journey_erhverv.py
"""
from __future__ import annotations

import re
import uuid
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from app.core.security import hash_password, new_token
from app.models import OutboxEvent, User
from app.modules.integrations import email_templates as tpl
from app.worker import runner
from tests.qa.qa_routes import read, resolve

LANGS = ("da", "en", "de", "es", "fr", "it", "no", "sv")
PW = "CorrectHorse!42"
OWNER = "owner@fjordgulv.example"
STAFF = "staff@fjordgulv.example"
BUSINESS = "Fjord Gulvservice"


# --------------------------------------------------------------------------- helpers

def _events(db, event_type: str, to: str | None = None) -> list[OutboxEvent]:
    db.expire_all()
    evs = db.scalars(select(OutboxEvent).where(OutboxEvent.event_type == event_type)
                     .order_by(OutboxEvent.created_at)).all()
    return [e for e in evs if to is None or e.payload.get("to_email") == to]


def _render(ev: OutboxEvent) -> tpl.Email:
    """The Email exactly as the worker builds it for this outbox event (app/worker/runner.py)."""
    p, t = ev.payload, ev.event_type
    if t == "email.verify_address":
        return tpl.verify(p["link"], lang=p.get("lang") or "da", privat=p.get("audience") == "privat")
    if t == "email.password_reset":
        return tpl.reset(p["link"], lang=p.get("lang") or "da")
    if t == "email.invitation":
        return tpl.invitation(p["workspace_name"], p["invited_by"], p["role"], p["link"], lang=p.get("lang") or "da")
    if t == "email.new_lead":
        return tpl.new_lead(p["workspace_name"], p["contact_name"], p.get("need_summary") or "", p["link"],
                            lang=p.get("lang") or "da")
    if t == "email.daily_report":
        return tpl.daily_report(p["subject"], p["body"], p.get("link"), lang=p.get("lang") or "da")
    return tpl.from_payload(p)


def _links(html: str) -> list[str]:
    return [h for h in re.findall(r'href="([^"]+)"', html) if h.startswith("http")]


def assert_erhverv_mail(mail: tpl.Email, where: str) -> None:
    html, text = mail.html(), mail.text()
    assert tpl.ACCENT in html, f"{where}: not the Erhverv blue"
    assert tpl.PRIVAT_ACCENT not in html, f"{where}: Privat orange in an Erhverv mail"
    assert "Dialogbot Privat" not in html and "Dialogbot Privat" not in text, f"{where}: Privat wordmark"
    assert "/icons/icon-192.png" in html and "privat-icon" not in html, f"{where}: wrong icon"
    for href in _links(html):
        if "frontend.test" in href:
            assert resolve(href), f"{where}: link lands on no route: {href}"


def assert_privat_mail(mail: tpl.Email, where: str) -> None:
    html = mail.html()
    assert tpl.PRIVAT_ACCENT in html and tpl.ACCENT not in html, f"{where}: a Privat user got the blue Erhverv mail"
    assert "Dialogbot Privat" in html, f"{where}: no «Dialogbot Privat» wordmark"


def _register(api, email, *, intent="reception", lang=None, name="Mads Jensen"):
    body = {"email": email, "password": PW, "display_name": name, "signup_intent": intent}
    if lang:
        body["interface_language"] = lang
    r = api.c.post(f"{api.base}/auth/register", json=body)
    assert r.status_code == 201, r.text
    return r.json()


def _verify_from_outbox(api, db, email) -> None:
    ev = _events(db, "email.verify_address", email)[-1]
    raw = re.search(r"token=([A-Za-z0-9_\-]+)", ev.payload["link"]).group(1)
    r = api.c.post(f"{api.base}/auth/verify-email", json={"token": raw})
    assert r.status_code == 200, r.text


def _owner_with_workspace(api, db, email=OWNER, intent="reception", name=BUSINESS):
    _register(api, email, intent=intent)
    _verify_from_outbox(api, db, email)
    tok = api.login(email, PW)
    ws = api.workspace(tok, name)
    return tok, ws


# =========================================================================== OK touchpoints (documentation)

@pytest.mark.parametrize("intent", ["reception", "campaigns", "both"])
def test_ok_signup_intent_verify_mail_is_erhverv_and_next_step_exists(api, client, db, intent):
    """/signup?intent=… → blue verify mail → /verify-email → «Fortsæt» /onboarding/workspace → /opsaetning/1."""
    email = f"{intent}@fjordgulv.example"
    u = _register(api, email, intent=intent)
    assert u["signup_intent"] == intent
    ev = _events(db, "email.verify_address", email)[-1]
    assert "audience" not in ev.payload and "for=privat" not in ev.payload["link"]
    assert_erhverv_mail(_render(ev), f"verify[{intent}]")
    assert resolve(ev.payload["link"]) == "/verify-email"
    assert resolve("/onboarding/workspace") == "/opsaetning/1"  # verified page CTA (verify-email/page.tsx)
    _verify_from_outbox(api, db, email)
    tok = api.login(email, PW)
    ws = api.workspace(tok, BUSINESS)  # CreateWorkspace sends product_intent = signup_intent
    r = api.c.get(f"{api.base}/workspaces", headers=api.h(tok))
    assert [w["product_intent"] for w in r.json() if w["id"] == ws] == [intent]


@pytest.mark.parametrize("lang", LANGS)
def test_ok_erhverv_account_mails_render_blue_and_localized(lang):
    """Every Erhverv mail builder in all 8 languages: blue, «Dialogbot», Erhverv icon, links land on a route."""
    base = "http://frontend.test"
    mails = {
        "verify": tpl.verify(f"{base}/verify-email?token=t", lang=lang),
        "reset": tpl.reset(f"{base}/password/reset?token=t", lang=lang),
        "invitation": tpl.invitation(BUSINESS, "Mads Jensen", "staff", f"{base}/invite/t", lang=lang),
        "new_lead": tpl.new_lead(BUSINESS, "Mette Nielsen", "Gulvslibning 45 m²", f"{base}/app/leads/x", lang=lang),
        "daily_report": tpl.daily_report("Dagsrapport", "Dagsrapport\n\nSamtaler: 3", f"{base}/app/ugen?date=2026-11-10",
                                         lang=lang),
        "ambassador_approved": tpl.ambassador_approved("Mads", f"{base}/a/mads", "MADS42", f"{base}/ambassador",
                                                       lang=lang),
    }
    for k, m in mails.items():
        assert_erhverv_mail(m, f"{k}[{lang}]")
        assert f'lang="{"nb" if lang == "no" else lang}"' in m.html() or f'lang="{lang}"' in m.html(), k
    if lang != "da":
        da = tpl.verify(f"{base}/verify-email?token=t", lang="da")
        assert mails["verify"].paragraphs != da.paragraphs and mails["verify"].button_label != da.button_label


def test_ok_reset_invitation_lead_report_links_from_real_outbox(api, client, db):
    """The links the API really queues land on existing routes (reset, invitation, new lead, daily report)."""
    tok, ws = _owner_with_workspace(api, db)
    assert api.c.post(f"{api.base}/auth/password/forgot", json={"email": OWNER}).status_code == 202
    assert api.invite(tok, ws, STAFF, "staff").status_code == 201
    for t in ("email.password_reset", "email.invitation"):
        ev = _events(db, t)[-1]
        assert_erhverv_mail(_render(ev), t)
        assert resolve(ev.payload["link"]), ev.payload["link"]
    assert resolve("http://frontend.test/app/leads/00000000-0000-0000-0000-000000000000") == "/app/opkald/henvendelser/[id]"
    assert resolve("http://frontend.test/app/ugen?date=2026-11-10") == "/app/ugen"
    assert resolve("http://frontend.test/app/konto?card=saved") == "/app/konto"  # Stripe success_url
    assert resolve("/app/konto/abonnement") == "/app/konto"  # step 3 «bekræft abonnement»


def test_ok_backend_inapp_links_resolve():
    """Every in-app href the backend hands the web (overview activity, setup plan, push, connections) is a route."""
    import os

    root = os.path.join(os.path.dirname(__file__), "..", "..", "app", "modules")
    bad = []
    for mod in ("overview", "setup", "push", "integrations", "reports", "leads", "workspaces", "identity"):
        for dp, _dn, fn in os.walk(os.path.join(root, mod)):
            for f in fn:
                if not f.endswith(".py"):
                    continue
                for path in re.findall(r'''["'](/app[^"'\s]*|/opsaetning[^"'\s]*|/verify-email|/invite/|/password/[a-z]+)''',
                                       open(os.path.join(dp, f), encoding="utf-8").read()):
                    probe = re.sub(r"\{[^}]*\}", "x", path)
                    if "/app/api" in probe or "operator" in probe:
                        continue
                    if probe.endswith("/"):
                        probe += "x"
                    if resolve(probe) is None:
                        bad.append(f"{mod}/{f}: {path}")
    assert not bad, bad


# =========================================================================== findings (open → xfail strict)

@pytest.mark.xfail(strict=True, reason="F-JE-01: samme login i Privat og Erhverv – signup_intent «privat» (#179) "
                                       "giver 422 «Ugyldig produktintention» ved oprettelse af virksomhed")
def test_F_JE_01_privat_signup_can_still_create_an_erhverv_workspace(api, client, db):
    email = "privat-foerst@fjordgulv.example"
    _register(api, email, intent="privat")
    _verify_from_outbox(api, db, email)
    tok = api.login(email, PW)
    # exactly what /opsaetning/1 CreateWorkspace sends: product_intent = me.signup_intent
    me = api.c.get(f"{api.base}/auth/me", headers=api.h(tok)).json()
    r = api.c.post(f"{api.base}/workspaces", json={"name": BUSINESS, "product_intent": me["signup_intent"]},
                   headers=api.h(tok))
    assert r.status_code == 201, r.text


@pytest.mark.xfail(strict=True, reason="F-JE-01: også uden product_intent falder backend tilbage på signup_intent «privat»")
def test_F_JE_01b_workspace_without_intent_for_privat_signup(api, client, db):
    email = "privat-foerst2@fjordgulv.example"
    _register(api, email, intent="privat")
    _verify_from_outbox(api, db, email)
    tok = api.login(email, PW)
    r = api.c.post(f"{api.base}/workspaces", json={"name": BUSINESS}, headers=api.h(tok))
    assert r.status_code == 201, r.text


@pytest.mark.xfail(strict=True, reason="F-JE-02: Privat-bruger, der nulstiller adgangskode, får den blå Erhverv-mail")
def test_F_JE_02_privat_user_reset_mail_is_privat(api, client, db):
    email = "pia@fjordgulv.example"
    _register(api, email, intent="privat", name="Pia Jensen")
    assert api.c.post(f"{api.base}/auth/password/forgot", json={"email": email}).status_code == 202
    ev = _events(db, "email.password_reset", email)[-1]
    assert_privat_mail(_render(ev), "reset[privat]")


@pytest.mark.xfail(strict=True, reason="F-JE-02: /password/reset sender altid til /login?reset=1 (→ /app) og har "
                                       "altid Erhverv-ramme – også for Privat-brugere")
def test_F_JE_02b_reset_page_knows_privat():
    src = read("web/src/app/password/reset/page.tsx")
    assert "privat" in src, "reset page has no Privat variant (frame or destination)"


@pytest.mark.xfail(strict=True, reason="F-JE-03: login uden ?next sender alle til /app – en Privat-bruger lander i "
                                       "Erhverv-opsætningen /opsaetning/1")
def test_F_JE_03_login_without_next_routes_by_account():
    src = read("web/src/app/login/page.tsx")
    body = src[src.index("useSubmit("):src.index("return (")]
    # the destination must depend on the account (Privat profile / business workspace / signup_intent), not be "/app"
    assert re.search(r"privat|signup_intent|workspaces", body), body


@pytest.mark.xfail(strict=True, reason="F-JE-04: Privat-quiz-funnelens velkomstmail er den blå Erhverv-mail, og "
                                       "dens link fører via /login?reset=1 til /app (Erhverv)")
def test_F_JE_04_privat_funnel_welcome_mail_is_privat(api, client, db):
    from app.modules.funnel import service as funnel

    u = User(email="funnel-pia@fjordgulv.example", email_normalized="funnel-pia@fjordgulv.example",
             password_hash=hash_password(new_token()), display_name="Pia Jensen", signup_intent=None,
             interface_language="da")
    db.add(u)
    db.flush()
    funnel._welcome(db, u, "privat")
    db.commit()
    ev = _events(db, "email.branded", u.email)[-1]
    assert_privat_mail(_render(ev), "funnel-welcome[privat]")


@pytest.mark.xfail(strict=True, reason="F-JE-05: Privat-funnel-bruger (signup_intent None) får ved «Send igen» den blå "
                                       "Erhverv-bekræftelsesmail, og «Fortsæt» fører til Erhverv-opsætningen")
def test_F_JE_05_privat_funnel_user_resend_verify_is_privat(api, client, db, monkeypatch):
    from app.config import get_settings
    from app.modules.privat import deps

    monkeypatch.setenv("PRIVAT_ENABLED", "true")
    get_settings.cache_clear()

    u = User(email="funnel-pia2@fjordgulv.example", email_normalized="funnel-pia2@fjordgulv.example",
             password_hash=hash_password(PW), display_name="Pia Jensen", signup_intent=None, interface_language="da")
    db.add(u)
    db.flush()
    from datetime import UTC, datetime

    u.phone_verified_at = datetime.now(UTC)  # the funnel proves the phone, not the e-mail
    deps.ensure_account(db, u)  # the personal workspace the Privat funnel creates
    db.commit()
    tok = api.login(u.email, PW)
    assert api.c.post(f"{api.base}/auth/verify-email/resend", headers=api.h(tok)).status_code == 202
    ev = _events(db, "email.verify_address", u.email)[-1]
    assert "for=privat" in ev.payload["link"]
    assert_privat_mail(_render(ev), "verify-resend[privat-funnel]")


@pytest.mark.xfail(strict=True, reason="F-JE-06: Privat-notifikationsmails (påmindelse, regning, fødselsdag, pakke, bil, "
                                       "fællesgave, invitation) sætter aldrig audience=«privat» – de er blå Erhverv-mails")
def test_F_JE_06_every_privat_mail_builder_sets_privat_audience():
    import os

    root = os.path.join(os.path.dirname(__file__), "..", "..", "app", "modules", "privat")
    missing = []
    for f in sorted(os.listdir(root)):
        if not f.endswith(".py"):
            continue
        src = open(os.path.join(root, f), encoding="utf-8").read()
        for m in re.finditer(r"tpl\.Email\((.{0,600}?)\)\n", src, re.S):
            if "audience" not in m.group(1):
                missing.append(f"{f}:{src[:m.start()].count(chr(10)) + 1}")
    assert not missing, missing


@pytest.mark.xfail(strict=True, reason="F-JE-07: /signup sender ikke interface_language – bekræftelsesmail og alle "
                                       "senere konto-mails er danske for en tysk/engelsk/… besøgende")
def test_F_JE_07_signup_sends_the_visitors_language():
    src = read("web/src/app/signup/page.tsx")
    assert "interface_language" in src or "useLocale" in src


def test_F_JE_07_api_side_language_is_respected_when_sent(api, client, db):
    """Control: the API itself does it right when the language is sent – the defect is that the web never sends it."""
    _register(api, "de@fjordgulv.example", lang="de")
    m = _render(_events(db, "email.verify_address", "de@fjordgulv.example")[-1])
    assert m.lang == "de" and "Bestätigen" in m.html()
    _register(api, "web@fjordgulv.example")  # what /signup posts today (no interface_language)
    assert _events(db, "email.verify_address", "web@fjordgulv.example")[-1].payload["lang"] == "da"


@pytest.mark.xfail(strict=True, reason="F-JE-08: Erhverv-quiz-funnel: velkomstmailen er hårdkodet dansk, og kontoen "
                                       "oprettes altid med interface_language «da»")
def test_F_JE_08_erhverv_funnel_welcome_follows_language(api, client, db):
    from app.modules.funnel import service as funnel

    u = User(email="funnel-de@fjordgulv.example", email_normalized="funnel-de@fjordgulv.example",
             password_hash=hash_password(new_token()), display_name="Mads Jensen", signup_intent="reception",
             interface_language="de")
    db.add(u)
    db.flush()
    funnel._welcome(db, u, "erhverv")
    db.commit()
    m = _render(_events(db, "email.branded", u.email)[-1])
    assert m.lang == "de" and "Velkommen" not in m.subject, m.subject


@pytest.mark.xfail(strict=True, reason="F-JE-09: funnel-bruger får aldrig en bekræftelsesmail; «Vælg adgangskode»-linket "
                                       "(beviser e-mailen) markerer den ikke bekræftet → gult «Bekræft e-mail»-banner bliver")
def test_F_JE_09_funnel_choose_password_link_verifies_email(api, client, db):
    from app.modules.funnel import service as funnel

    u = User(email="funnel-mads@fjordgulv.example", email_normalized="funnel-mads@fjordgulv.example",
             password_hash=hash_password(new_token()), display_name="Mads Jensen", signup_intent="reception",
             interface_language="da")
    db.add(u)
    db.flush()
    funnel._welcome(db, u, "erhverv")
    db.commit()
    link = _render(_events(db, "email.branded", u.email)[-1]).button_url
    assert resolve(link) == "/password/reset"
    raw = re.search(r"token=([A-Za-z0-9_\-]+)", link).group(1)
    r = api.c.post(f"{api.base}/auth/password/reset", json={"token": raw, "password": PW})
    assert r.status_code == 200, r.text
    assert r.json()["email_verified"] is True


@pytest.mark.xfail(strict=True, reason="F-JE-10: inviteret medarbejder sendes efter accept til /opsaetning/1 "
                                       "(ejerens virksomhedsopsætning) i stedet for /app")
def test_F_JE_10_invite_accept_goes_to_the_app():
    src = read("web/src/app/invite/[token]/accept.tsx")
    assert 'router.push("/opsaetning/1")' not in src


@pytest.mark.xfail(strict=True, reason="F-JE-10: inviteret medarbejders bekræftelsesmail lover «sæt din AI-receptionist "
                                       "op», og «Fortsæt» fører til opsætningen (opretter ny virksomhed, hvis invitationen "
                                       "endnu ikke er accepteret)")
def test_F_JE_10b_invited_staff_verify_mail_is_not_owner_setup(api, client, db):
    tok, ws = _owner_with_workspace(api, db)
    assert api.invite(tok, ws, STAFF, "staff").status_code == 201
    _register(api, STAFF)  # /signup?next=/invite/… posts the default intent «reception»
    m = _render(_events(db, "email.verify_address", STAFF)[-1])
    assert "receptionist" not in " ".join(m.paragraphs).lower(), m.paragraphs


@pytest.mark.xfail(strict=True, reason="F-JE-11: «Ny henvendelse»-mailens link bærer ikke arbejdsrummet – ejer med to "
                                       "virksomheder får fejl/den forkerte virksomhed")
def test_F_JE_11_new_lead_link_carries_workspace(api, client, db):
    from app.modules.leads import service as leads

    tok, ws = _owner_with_workspace(api, db)
    lead = SimpleNamespace(id=uuid.uuid4(), workspace_id=uuid.UUID(ws), contact_name="Mette Nielsen",
                           need_summary="Gulvslibning 45 m²")
    leads._notify_new_lead(db, lead)
    db.commit()
    link = _events(db, "email.new_lead", OWNER)[-1].payload["link"]
    assert ws in link, link


@pytest.mark.xfail(strict=True, reason="F-JE-11: dagsrapportens link /app/ugen?date=… viser den valgte virksomheds uge, "
                                       "ikke rapportens")
def test_F_JE_11b_daily_report_link_carries_workspace():
    src = read("app/modules/reports/service.py")
    line = next(ln for ln in src.splitlines() if "/app/ugen?date=" in ln)
    assert "ws.id" in line or "workspace" in line, line


@pytest.mark.xfail(strict=True, reason="F-JE-12: login/tilmelding/bekræft/nulstil viser backendens danske fejltekst på "
                                       "alle 8 sprog")
def test_F_JE_12_auth_errors_are_localized(api, client):
    import json
    import os

    api.register("x@fjordgulv.example")
    r = api.c.post(f"{api.base}/auth/login", json={"email": "x@fjordgulv.example", "password": "forkert-kode-123"},
                   headers={"Accept-Language": "de"})
    assert r.status_code == 401
    code = r.json()["code"]
    msgs = json.load(open(os.path.join(os.path.dirname(__file__), "..", "..", "web", "src", "i18n", "messages", "de",
                                       "auth.json"), encoding="utf-8"))
    localized_in_web = code in json.dumps(msgs.get("errors", {}))
    assert localized_in_web or r.json()["message"] != "Forkert e-mail eller adgangskode"


def test_runner_handlers_cover_every_account_mail():
    """Sanity: every account mail type the journey depends on has a worker handler (else it is never sent)."""
    for t in ("email.verify_address", "email.password_reset", "email.invitation", "email.new_lead",
              "email.daily_report", "email.branded", "email.ambassador"):
        assert t in runner.HANDLERS, t
