"""Every Dialogbot Privat mail, built in one place (QA F-JP-03, F-JP-06, F-JP-07, F-JP-08).

Each builder returns an `Email` with audience "privat" (the Privat orange, the Privat icon, «Dialogbot Privat»), in the
recipient's language (the texts are in email_texts_privat.py, read with email_texts.t) and with one next action: a
button to the place in the Privat app the mail is about. Code under app/modules/privat and the Privat funnel never
build `tpl.Email(...)` themselves; tests/test_privat_mails.py renders every builder here in all 8 languages.

A task title, a call summary or an app's own reminder line is the user's or the assistant's text and is shown as it is.
"""
from __future__ import annotations

from datetime import UTC, datetime

from app.config import get_settings
from app.core.languages import normalize
from app.modules.integrations.email_templates import Email
from app.modules.integrations.email_texts import t

AUDIENCE = "privat"


def url(path: str) -> str:
    """An absolute link into the Privat app (`path` starts with /privat/)."""
    return f"{get_settings().frontend_base_url.rstrip('/')}{path}"


def _mail(lang: str, **kw) -> Email:
    return Email(lang=lang, audience=AUDIENCE, **kw)


def when_text(at: datetime, lang: str) -> str:
    """A reminder's time as the recipient reads it. Danish keeps the app's own words ("i morgen kl. 16.00")."""
    from app.modules.integrations import sms_templates
    from app.modules.privat import rules

    lang = normalize(lang)
    if lang == "da":
        return rules.lower_first(rules.when_text(at))
    return sms_templates.when(at, rules.TZ.key, lang)


def reminder(title: str, at: datetime | None, link: str, lang: str = "da") -> Email:
    lang = normalize(lang)
    return _mail(lang, subject=t(lang, "privat_reminder_subject", title=title), heading=title,
                 paragraphs=[t(lang, "privat_reminder_body", when=when_text(at, lang))] if at else [],
                 button_label=t(lang, "privat_open_task"), button_url=link,
                 footer_reason=t(lang, "privat_reminder_footer"))


def task_notice(subject: str, title: str, text: str, link: str, lang: str = "da") -> Email:
    """A call outcome or another update on a task Dialogbot works on (privat.service.notify_owner)."""
    lang = normalize(lang)
    return _mail(lang, subject=subject, heading=title, paragraphs=[text], button_label=t(lang, "privat_open_task"),
                 button_url=link, footer_reason=t(lang, "privat_task_footer"))


def invite_accepted(name: str, title: str, link: str, lang: str = "da") -> Email:
    lang = normalize(lang)
    head = t(lang, "privat_accepted_subject", name=name)
    return _mail(lang, subject=head, heading=head, paragraphs=[t(lang, "privat_accepted_body", name=name, title=title)],
                 button_label=t(lang, "privat_accepted_button"), button_url=link,
                 footer_reason=t(lang, "privat_accepted_footer"))


def parcel(text: str, event: str, link: str, lang: str = "da") -> Email:
    lang = normalize(lang)
    return _mail(lang, subject=t(lang, "privat_parcel_subject"), heading=text, paragraphs=[event] if event else [],
                 button_label=t(lang, "privat_parcel_button"), button_url=link,
                 footer_reason=t(lang, "privat_parcel_footer"))


def car(text: str, link: str, lang: str = "da") -> Email:
    lang = normalize(lang)
    return _mail(lang, subject=t(lang, "privat_car_subject"), heading=text, paragraphs=[],
                 button_label=t(lang, "privat_car_button"), button_url=link, footer_reason=t(lang, "privat_car_footer"))


def birthday(name: str, text: str, link: str, lang: str = "da") -> Email:
    lang = normalize(lang)
    return _mail(lang, subject=t(lang, "privat_birthday_subject", name=name), heading=text,
                 paragraphs=[t(lang, "privat_birthday_body")], button_label=t(lang, "privat_birthday_button"),
                 button_url=link, footer_reason=t(lang, "privat_birthday_footer"))


def bill(name: str, text: str, link: str, lang: str = "da") -> Email:
    lang = normalize(lang)
    return _mail(lang, subject=t(lang, "privat_bill_subject", name=name), heading=text,
                 paragraphs=[t(lang, "privat_bill_body")], button_label=t(lang, "privat_bill_button"),
                 button_url=link, footer_reason=t(lang, "privat_bill_footer"))


def app_reminder(app: str, text: str, link: str, lang: str = "da") -> Email:
    """A reminder from one of the Privat apps (app_kit): the app's name and its own reminder line."""
    lang = normalize(lang)
    return _mail(lang, subject=app, heading=text, paragraphs=[], button_label=t(lang, "privat_app_button", app=app),
                 button_url=link, footer_reason=t(lang, "privat_app_footer", app=app))


def group_gift(text: str, link: str, lang: str = "da") -> Email:
    lang = normalize(lang)
    head = t(lang, "privat_gift_subject")
    return _mail(lang, subject=head, heading=head, paragraphs=[text], button_label=t(lang, "privat_gift_button"),
                 button_url=link, footer_reason=t(lang, "privat_gift_footer"))


def funnel_welcome(name: str, email: str, link: str, hours: int, lang: str = "da") -> Email:
    """The Privat quiz-funnel's welcome: the account exists with a random password – «Vælg adgangskode»."""
    lang = normalize(lang)
    return _mail(lang, subject=t(lang, "privat_welcome_subject"), preheader=t(lang, "welcome_preheader"),
                 heading=t(lang, "welcome_heading", name=name),
                 paragraphs=[t(lang, "privat_welcome_body", email=email), t(lang, "welcome_ignore")],
                 button_label=t(lang, "welcome_button"), button_url=link,
                 note=t(lang, "welcome_note", hours=hours), footer_reason=t(lang, "welcome_footer"))


BILLING_KINDS = {"receipt": "receipt", "payment_failed": "failed", "refund": "refund", "trial_ending": "trial"}


def billing(kind: str, amount: str, link: str, lang: str = "da", *, date: str = "", plan: str = "") -> Email:
    """Dialogbot Privat's own billing mails (F-PBQ-08, via billing.customer_mails): a receipt, a failed payment
    (dunning), a refund, or the trial ending in 3 days. `amount` is already formatted (billing.markets.fmt); the button
    opens Konto. The texts are shared with Erhverv's billing mails (email_texts.py), «what» says Dialogbot Privat."""
    lang = normalize(lang)
    k = BILLING_KINDS[kind]
    kw = {"amount": amount, "what": t(lang, "what_privat"), "plan": plan, "date": date}
    return _mail(lang, subject=t(lang, f"{k}_subject", **kw), heading=t(lang, f"{k}_heading", **kw),
                 paragraphs=[t(lang, f"{k}_body", **kw)], button_label=t(lang, "manage_button"), button_url=link,
                 footer_reason=t(lang, "billing_footer"))


def data_export(link: str, days: int, lang: str = "da") -> Email:
    """«Eksportér mine data» is ready (PC-ACC-02/03, privat.gdpr): the link opens Konto, works `days` days, login only."""
    lang = normalize(lang)
    return _mail(lang, subject=t(lang, "privat_export_subject"), heading=t(lang, "privat_export_heading"),
                 paragraphs=[t(lang, "privat_export_body")], button_label=t(lang, "privat_export_button"),
                 button_url=link, note=t(lang, "privat_export_note", days=days),
                 footer_reason=t(lang, "privat_export_footer"))


def sms_code(code: str, lang: str = "da") -> str:
    """The SMS with a verification code (Privat phone, group join, quiz-funnel)."""
    return t(lang, "privat_sms_code", code=code)


def samples(lang: str = "da") -> dict[str, Email]:
    """One example of every Privat mail in `lang` – the account mails (verify, reset) included. A new builder above
    must be added here; tests/test_privat_mails.py checks it."""
    from app.modules.integrations import email_templates as tpl

    task = url("/privat/opgaver/00000000-0000-0000-0000-000000000001")
    at = datetime(2026, 11, 5, 15, 0, tzinfo=UTC)
    return {
        "verify": tpl.verify(url("/verify-email?token=eksempel&for=privat"), lang=lang, privat=True),
        "verify_invitee": tpl.verify(url("/verify-email?token=eksempel&for=privat&next=%2Fi%2FABCDEFGH"), lang=lang,
                                     privat=True, variant="list"),
        "verify_other": tpl.verify(url("/verify-email?token=eksempel&for=privat&next=%2Fprivat%2Fdag"), lang=lang,
                                   privat=True, variant="other"),
        "reset": tpl.reset(url("/password/reset?token=eksempel&for=privat"), lang=lang, privat=True),
        "reminder": reminder("Hente pakken", at, task, lang),
        "task_notice": task_notice("Opkaldet er klaret", "Ring til tandlægen", "Tandlægen har givet dig en tid.", task,
                                   lang),
        "invite_accepted": invite_accepted("Ole", "Indkøb", task, lang),
        "parcel": parcel("Din pakke er klar til afhentning.", "Pakkeshop Netto", url("/privat/pakker"), lang),
        "car": car("Bilen skal synes om 14 dage.", url("/privat/bil"), lang),
        "birthday": birthday("Mor", "Mor fylder 70 i morgen.", url("/privat/foedselsdage"), lang),
        "bill": bill("El", "El skal betales i morgen.", url("/privat/regninger"), lang),
        "app_reminder": app_reminder("Planter", "Vand monsteraen.", url("/privat/apps/planter"), lang),
        "group_gift": group_gift("Der mangler 200 kr. til fællesgaven.", task, lang),
        "funnel_welcome": funnel_welcome("Pia", "pia@example.dk",
                                         url("/password/reset?token=eksempel&for=privat&next=%2Fprivat%2Fdag"), 48, lang),
        "billing": billing("receipt", "99 kr.", url("/privat/konto"), lang),
        "billing_failed": billing("payment_failed", "99 kr.", url("/privat/konto"), lang),
        "billing_refund": billing("refund", "99 kr.", url("/privat/konto"), lang),
        "billing_trial": billing("trial_ending", "99 kr.", url("/privat/konto"), lang, date="14.11.2026", plan="Plus"),
        "data_export": data_export(url("/privat/konto?eksport=eksempel"), 7, lang),
    }
