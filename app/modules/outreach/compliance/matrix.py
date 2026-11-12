"""The country matrix for cold B2B e-mail. Data only – the rules are applied in engine.py.

This is the owner's matrix of 12 November 2026 with two changes made while building it, both on the cautious side:

- **PL** and **ES** are `hold`, not approved. Poland's Electronic Communications Law (art. 398, in force 10 November
  2024) asks for prior consent for commercial e-mail and covers business recipients too. Spain's LSSI art. 21 asks for
  prior consent as the main rule and sources disagree on how far a B2B exception reaches. A held market sends nothing
  until a lawyer has signed it off and its code is listed in OUTREACH_SIGNED_OFF_MARKETS.
- A market that is not listed here at all is blocked (unknown is never «allowed»).

Not legal advice: have the matrix confirmed before the first live send (docs/sales/cold-outreach.md).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Status = Literal["approved", "hold", "blocked"]
FooterKind = Literal["can_spam", "gdpr_li", "casl", "spam_act"]


@dataclass(frozen=True)
class Jurisdiction:
    code: str
    tier: int                      # 1 | 2 for approved/held markets, 0 for blocked
    status: Status
    regime: str
    footer: FooterKind = "gdpr_li"
    spelling: Literal["US", "UK", "INTL"] = "INTL"
    webmail_allowed: bool = False          # gmail.com etc.: an address that is most likely a person or a sole trader
    legal_forms: tuple[str, ...] = ()      # company name must end in one of these (corporate subscribers only)
    role_address_only: bool = False        # only generic addresses (info@, post@ …), never a named person
    published_source_required: bool = False  # implied/inferred consent rests on the address being published


WEBMAIL_DOMAINS = frozenset({
    "gmail.com", "googlemail.com", "yahoo.com", "yahoo.co.uk", "yahoo.ca", "yahoo.com.au", "yahoo.fr", "yahoo.es",
    "ymail.com", "hotmail.com", "hotmail.co.uk", "hotmail.fr", "hotmail.es", "hotmail.se", "outlook.com", "live.com",
    "live.co.uk", "live.se", "msn.com", "aol.com", "icloud.com", "me.com", "mac.com", "proton.me", "protonmail.com",
    "gmx.com", "gmx.net", "mail.com", "zoho.com", "yandex.com", "btinternet.com", "sky.com", "talktalk.net",
    "virginmedia.com", "ntlworld.com", "blueyonder.co.uk", "bigpond.com", "optusnet.com.au", "shaw.ca", "rogers.com",
    "telus.net", "sympatico.ca", "comcast.net", "verizon.net", "att.net", "sbcglobal.net", "cox.net", "orange.fr",
    "wanadoo.fr", "free.fr", "laposte.net", "sfr.fr", "telia.com", "spray.se", "comhem.se", "online.no", "eircom.net",
})

ROLE_LOCAL_PARTS = frozenset({
    "info", "post", "kontakt", "contact", "hello", "hei", "hej", "mail", "office", "kontor", "firmapost", "booking",
    "bestilling", "resepsjon", "reception", "admin", "service", "kundeservice", "support", "sales", "salg", "enquiries",
})

UK_FORMS = ("ltd", "limited", "llp", "plc")
DK_FORMS = ("aps", "a/s")

MATRIX: dict[str, Jurisdiction] = {j.code: j for j in (
    # Tier 1 – English-speaking opt-out markets
    Jurisdiction("US", 1, "approved", "CAN-SPAM Act", footer="can_spam", spelling="US", webmail_allowed=True),
    Jurisdiction("UK", 1, "approved", "UK GDPR + PECR reg. 22 (corporate subscribers)", spelling="UK", legal_forms=UK_FORMS),
    Jurisdiction("IE", 1, "approved", "GDPR + ePrivacy Regulations 2011 reg. 13", spelling="UK"),
    Jurisdiction("CA", 1, "approved", "CASL s. 10(9)(b) conspicuous publication", footer="casl", spelling="UK",
                 published_source_required=True),
    Jurisdiction("AU", 1, "approved", "Spam Act 2003 sch. 2 inferred consent", footer="spam_act", spelling="UK",
                 published_source_required=True),
    # Tier 2 – European B2B opt-out / legitimate interest
    Jurisdiction("SE", 2, "approved", "Marknadsföringslagen 19 § (legal persons)"),
    Jurisdiction("FR", 2, "approved", "CPCE L34-5 (professional address, offer related to the profession)"),
    Jurisdiction("NO", 2, "approved", "Markedsføringsloven § 15 (generic company addresses)", role_address_only=True),
    Jurisdiction("ES", 2, "hold", "LSSI art. 21 – consent is the main rule; B2B exception disputed"),
    Jurisdiction("PL", 2, "hold", "Prawo komunikacji elektronicznej art. 398 – prior consent, also B2B"),
    # Hard block: opt-in markets. No cold e-mail, SMS or DM, ever.
    *(Jurisdiction(c, 0, "blocked", r) for c, r in (
        ("DK", "Markedsføringsloven § 10"), ("DE", "UWG § 7"), ("AT", "TKG § 174"), ("NL", "Telecommunicatiewet 11.7"),
        ("IT", "Codice privacy art. 130"), ("CH", "UWG art. 3(1)(o)"), ("BE", "Code de droit économique XII.13"))),
)}

# Automated channels this system may never use towards a scraped contact, in any country.
FORBIDDEN_CHANNELS = frozenset({"sms", "dm", "ai_voice", "voice", "whatsapp"})


def normalize_country(raw: str | None) -> str:
    c = (raw or "").strip().upper()
    return {"GB": "UK", "USA": "US", "UNITED KINGDOM": "UK", "UNITED STATES": "US"}.get(c, c)
