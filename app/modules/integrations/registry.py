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
    ai_status: CapabilityStatus = {"anthropic": "available", "fake": "simulated"}.get(s.ai_provider, "not_implemented")
    ai_note = {
        "anthropic": f"Anthropic ({s.ai_model_id}). Svarer kun ud fra godkendt viden.",
        "fake": "Testdobbelt uden rigtig model.",
    }.get(s.ai_provider, "Ingen AI-udbyder er konfigureret (AI_PROVIDER=none).")
    return [
        Capability("email", "E-mail (konto, invitationer)", email_status, s.app_env,
                   ("Simuleret adapter gemmer beskeder i databasen." if s.email_adapter == "simulated"
                    else "Resend-adapter: 'sent' = accepteret af udbyder; levering/bounce/klage kommer via signeret webhook.")),
        Capability("telephony.inbound", "Indgående telefoni / viderestilling",
                   "available" if s.vapi_server_secret else "not_implemented", s.app_env,
                   "Vapi-stemmeassistent på jeres egne numre; svarer kun ud fra godkendt viden."
                   if s.vapi_server_secret else "Kræver en Vapi-konto og VAPI_SERVER_SECRET; intet nummer er forbundet."),
        Capability("telephony.outbound", "Udgående kampagneopkald", "not_implemented", s.app_env,
                   "Planlagt til etape 4. Betaling starter aldrig opkald."),
        Capability("calendar", "Kalenderforbindelse (Google/Microsoft/CalDAV)", "not_implemented", s.app_env,
                   "Planlagt til etape 3. Ingen simuleret test kan aktivere produktion."),
        Capability("payment", "Kortbetaling", "not_implemented", s.app_env, "Planlagt til etape 4."),
        Capability("ai.assistant_preview", "AI-assistent: intern forhåndsvisning", ai_status, s.app_env,
                   ai_note),
        Capability("ai.conversation", "AI-samtale med kunder", ai_status, s.app_env,
                   ("Kunderne taler med assistenten i web-widgetten"
                    + (" og i telefonen (Vapi, dansk transskribering)" if s.vapi_server_secret else "")
                    + ". Svarer kun ud fra godkendt viden.")
                   if ai_status != "not_implemented" else "Kræver en AI-udbyder (AI_PROVIDER)."),
        Capability("knowledge.source_import", "Kildeimport / udtræk / embeddings", "not_implemented", s.app_env,
                   "Planlagt senere. Der vises ingen fiktive udtræk."),
        Capability("webchat", "Web-widget", ai_status, s.app_env,
                   "Chat-widget til jeres hjemmeside; svarer kun ud fra godkendt viden og kun på godkendte domæner."
                   if ai_status != "not_implemented" else "Kræver en AI-udbyder (AI_PROVIDER)."),
    ]


def capability(key: str) -> Capability:
    for c in capabilities():
        if c.key == key:
            return c
    raise KeyError(key)
