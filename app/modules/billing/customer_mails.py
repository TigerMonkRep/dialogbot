"""Dialogbot's own billing mails (F-PBQ-08, decision Fürster 2026-11-10) – for Privat AND Erhverv, in the branded
layout (email_templates.Email; Privat in its orange), 8 languages (email_texts.py), queued as `email.branded`:

- receipt          a payment went through (Privat subscription invoices; Erhverv's invoices are e-mailed by Stripe)
- payment_failed   dunning (E06): the card was declined – update it in the portal
- refund           a refund is on its way
- trial_ending     Stripe's customer.subscription.trial_will_end (3 days before): what will be charged, and when

Before this, NEITHER product sent payment_failed or refund mails (billing-qa wave 1, E06), and Privat sent none at all.
Privat's mails are built by integrations.privat_mails.billing (the one Privat mail mechanism: audience privat, 8
languages, button to /privat/konto – tests/test_privat_mails.py renders them); Erhverv's are built here.
Each mail is queued once per Stripe object (dedupe key), so a replayed webhook never mails twice."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy.orm import Session as OrmSession

from app.config import get_settings
from app.core.languages import normalize as normalize_language
from app.core.outbox import enqueue
from app.modules.billing import markets

KINDS = ("receipt", "payment_failed", "refund", "trial_ending")
_KEY = {"receipt": "receipt", "payment_failed": "failed", "refund": "refund", "trial_ending": "trial"}


def build(kind: str, *, lang: str, audience: str, amount_minor: int, currency: str, link: str,
          date: datetime | None = None, plan: str | None = None):
    from app.modules.integrations import email_templates as tpl
    from app.modules.integrations import privat_mails

    lang = tpl.normalize(lang)
    k = _KEY[kind]
    amount = markets.fmt(int(amount_minor or 0), currency or "DKK")
    day = f"{date.day}.{date.month}.{date.year}" if date else ""
    if audience == "privat":
        return privat_mails.billing(kind, amount, link, lang, date=day, plan=plan or "")
    kw = {"amount": amount, "what": tpl.t(lang, "what_erhverv"), "plan": plan or "", "date": day}
    return tpl.Email(subject=tpl.t(lang, f"{k}_subject", **kw), heading=tpl.t(lang, f"{k}_heading", **kw),
                     paragraphs=[tpl.t(lang, f"{k}_body", **kw)], button_label=tpl.t(lang, "manage_button"),
                     button_url=link, footer_reason=tpl.t(lang, "billing_footer"), lang=lang, audience=audience)


def send(db: OrmSession, *, kind: str, to_email: str | None, lang: str | None, audience: str, dedupe: str,
         amount_minor: int, currency: str, workspace_id: uuid.UUID | None = None, date: datetime | None = None,
         plan: str | None = None) -> bool:
    """Queue one billing mail. False when there is no address."""
    from app.modules.integrations import email_templates as tpl

    if kind not in KINDS or not to_email:
        return False
    base = get_settings().frontend_base_url.rstrip("/")
    link = f"{base}/privat/konto" if audience == "privat" else f"{base}/app/konto/abonnement"
    mail = build(kind, lang=normalize_language(lang), audience=audience, amount_minor=amount_minor, currency=currency,
                 link=link, date=date, plan=plan)
    enqueue(db, event_type="email.branded", dedupe_key=f"billing-mail:{kind}:{dedupe}"[:200], workspace_id=workspace_id,
            payload={"to_email": to_email, "email": tpl.to_payload(mail)})
    return True
