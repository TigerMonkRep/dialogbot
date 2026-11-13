"""What the copy may say per market: price, spelling, the number the demo rings from, and the legal footer."""
from __future__ import annotations

from dataclasses import dataclass

from app.config import get_settings
from app.modules.billing import markets
from app.modules.outreach.compliance.matrix import MATRIX

DEMO_URL = "https://dialogbot.app"
# The edition a market's readers are sent to (dollars, American spelling and the US video for the US).
DEMO_URLS = {"US": "https://dialogbot.app/us"}


def demo_url(country: str) -> str:
    return DEMO_URLS.get(country, DEMO_URL)


UNSUBSCRIBE_PLACEHOLDER = "{{unsubscribe_link}}"

# Product statements the copy may make (the owner's wording). The auditor rejects product claims beyond these.
PRODUCT_FACTS = (
    "Dialogbot is an AI receptionist that answers the business's phone calls in under 2 seconds.",
    "It books appointments directly into Google Calendar or Microsoft 365.",
    "It sends SMS confirmations to the caller.",
    f"Anyone can try a live 90-second callback demo at {DEMO_URL}: enter a phone number and Dialogbot calls right away. "
    "No signup and no credit card.",
)


def display_number(e164: str) -> str:
    """+16283773337 → "+1 628 377 3337": how a number is written in the copy (and what the auditor compares)."""
    d = "".join(ch for ch in e164 if ch.isdigit())
    if e164.strip().startswith("+1") and len(d) == 11:
        return f"+1 {d[1:4]} {d[4:7]} {d[7:]}"
    if e164.strip().startswith("+44") and len(d) >= 11:
        return f"+44 {d[2:6]} {d[6:]}"
    return e164.strip()


def product_facts(country: str) -> tuple[str, ...]:
    """The statements the copy may make in this market. Where a demo line is set, the demo is a number the reader
    rings (Dialogbot's own assistant answers it); the callback demo is then not offered in the e-mail."""
    line = get_settings().outreach_demo_lines.get(country)
    if not line:
        return PRODUCT_FACTS
    return (*PRODUCT_FACTS[:3],
            f"Anyone can call Dialogbot's own demo line on {display_number(line)}, at any hour, and hear the AI "
            f"receptionist answer – it takes about 90 seconds. No signup and no credit card. More at {demo_url(country)}.")


@dataclass(frozen=True)
class Locale:
    country: str
    spelling: str             # US | UK | INTL
    price: str                # as it may appear in the copy, e.g. "$349/mo"
    callback_number: str | None
    demo_line: str | None = None   # as written in the copy ("+1 628 377 3337"); set = the reader rings the demo


def _list_price(currency: str) -> str:
    return f"{markets.fmt(markets.ERHVERV[currency]['monthly'], currency)}/mo"


def locale_for(country: str) -> Locale:
    s = get_settings()
    j = MATRIX[country]
    line = display_number(s.outreach_demo_lines[country]) if country in s.outreach_demo_lines else None
    if country == "US":   # dollars are a billing currency (markets.ERHVERV["USD"]); the setting only overrides the text
        return Locale(country, j.spelling, s.outreach_price_us or _list_price("USD"), s.outreach_callback_number_us, line)
    if country == "UK":
        return Locale(country, j.spelling, s.outreach_price_uk, s.outreach_callback_number_uk, line)
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
