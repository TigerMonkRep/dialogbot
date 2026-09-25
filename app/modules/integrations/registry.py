"""Capability registry for external integrations.

Every adapter declares an honest status. Anything not implemented in this
stage is reported as `not_implemented` and can never be reported as connected
or as a passed test. The setup plan reads this registry to decide which tasks
are blocked and why.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from app.config import get_settings

CapabilityStatus = Literal["available", "simulated", "not_implemented"]


@dataclass(frozen=True)
class Capability:
    key: str
    label: str
    status: CapabilityStatus
    environment: str
    note: str


def capabilities() -> list[Capability]:
    s = get_settings()
    email_status: CapabilityStatus = "simulated" if s.email_adapter == "simulated" else "available"
    return [
        Capability("email", "E-mail (konto, invitationer)", email_status, s.app_env,
                   ("Simuleret adapter gemmer beskeder i databasen." if s.email_adapter == "simulated"
                    else "Resend-adapter: 'sent' = accepteret af udbyder; leveringshændelser følger i milepæl B.")),
        Capability("telephony.inbound", "Indgående telefoni / viderestilling", "not_implemented", s.app_env,
                   "Planlagt til etape 2. Ingen udbyder er valgt eller forbundet."),
        Capability("telephony.outbound", "Udgående kampagneopkald", "not_implemented", s.app_env,
                   "Planlagt til etape 4. Betaling starter aldrig opkald."),
        Capability("calendar", "Kalenderforbindelse (Google/Microsoft/CalDAV)", "not_implemented", s.app_env,
                   "Planlagt til etape 3. Ingen simuleret test kan aktivere produktion."),
        Capability("payment", "Kortbetaling", "not_implemented", s.app_env, "Planlagt til etape 4."),
        Capability("ai.conversation", "AI-samtale / stemmemodel", "not_implemented", s.app_env,
                   "Planlagt til etape 2. Assistenten læser kun godkendt viden via API'et."),
        Capability("knowledge.source_import", "Kildeimport / udtræk / embeddings", "not_implemented", s.app_env,
                   "Planlagt senere. Der vises ingen fiktive udtræk."),
        Capability("webchat", "Web-widget", "not_implemented", s.app_env, "Planlagt til etape 2."),
    ]


def capability(key: str) -> Capability:
    for c in capabilities():
        if c.key == key:
            return c
    raise KeyError(key)
