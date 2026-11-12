"""What the copy may say per market: price, spelling, the number the demo rings from, and the legal footer."""
from __future__ import annotations

from dataclasses import dataclass

from app.config import get_settings
from app.modules.billing import markets
from app.modules.outreach.compliance.matrix import MATRIX

DEMO_URL = "https://dialogbot.app"
UNSUBSCRIBE_PLACEHOLDER = "{{unsubscribe_link}}"

# Product statements the copy may make (the owner's wording). The auditor rejects product claims beyond these.
PRODUCT_FACTS = (
    "Dialogbot is an AI receptionist that answers the business's phone calls in under 2 seconds.",
    "It books appointments directly into Google Calendar or Microsoft 365.",
    "It sends SMS confirmations to the caller.",
    f"Anyone can try a live 90-second callback demo at {DEMO_URL}: enter a phone number and Dialogbot calls right away. "
    "No signup and no credit card.",
)


@dataclass(frozen=True)
class Locale:
    country: str
    spelling: str             # US | UK | INTL
    price: str                # as it may appear in the copy, e.g. "$349/mo"
    callback_number: str | None


def _list_price(currency: str) -> str:
    return f"{markets.fmt(markets.ERHVERV[currency]['monthly'], currency)}/mo"


def locale_for(country: str) -> Locale:
    s = get_settings()
    j = MATRIX[country]
    if country == "US":
        return Locale(country, j.spelling, s.outreach_price_us, s.outreach_callback_number_us)
    if country == "UK":
        return Locale(country, j.spelling, s.outreach_price_uk, s.outreach_callback_number_uk)
    # Everywhere else the copy quotes the real list price of the currency the customer will be billed in.
    return Locale(country, j.spelling, _list_price(markets.COUNTRY_CURRENCY.get(country, "EUR")), None)


def sender_line() -> str:
    """«Dialogbot, CVR 25632710, <postal address>» – the identity line every footer starts with."""
    s = get_settings()
    return f"{s.outreach_legal_name}, {s.outreach_postal_address or 'Aarhus, Denmark'}"


def footer(country: str, company_name: str, email_source: str = "unknown") -> str:
    s = get_settings()
    kind = MATRIX[country].footer
    who = sender_line()
    if kind == "can_spam":
        body = (f"This is a commercial message from {who}.\n"
                f"Don't want these e-mails? Unsubscribe with one click: {UNSUBSCRIBE_PLACEHOLDER}")
    elif kind == "casl":
        body = (f"Sent by {who} · {DEMO_URL}\n"
                f"We wrote to the business address {company_name} publishes for enquiries. "
                f"Unsubscribe at any time: {UNSUBSCRIBE_PLACEHOLDER}")
    elif kind == "spam_act":
        body = (f"Sent by {who} · {DEMO_URL}\n"
                f"We wrote to the business address {company_name} publishes. Unsubscribe: {UNSUBSCRIBE_PLACEHOLDER}")
    else:  # gdpr_li – names the legal basis and where the address came from (GDPR art. 14)
        found = "on your company's website" if email_source == "published_website" else "in a public business directory"
        body = (f"{who}\n"
                f"We are contacting {company_name} as a business, on the basis of our legitimate interest in offering "
                f"a relevant business service. We found this address {found}. "
                f"Privacy: {s.outreach_privacy_url}\n"
                f"Opt out at once, for good: {UNSUBSCRIBE_PLACEHOLDER}")
    return "--\n" + body
