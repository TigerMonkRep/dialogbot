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
        Capability("telephony.outbound", "Udgående kampagneopkald",
                   "available" if (s.vapi_api_key and s.vapi_server_secret) else "not_implemented", s.app_env,
                   "Vapi ringer op fra jeres eget nummer inden for kampagnens tidsrum. Betaling starter aldrig opkald – "
                   "kun en administrator kan starte en kampagne." if (s.vapi_api_key and s.vapi_server_secret)
                   else "Kræver VAPI_API_KEY og VAPI_SERVER_SECRET på serveren. Kampagner kan forberedes, men ikke startes."),
        Capability("calendar", "Kalender og online booking", "available", s.app_env,
                   "Ledige tider ud fra godkendte åbningstider. Jeres Google/Outlook-kalender kobles på med dens hemmelige "
                   "iCal-adresse (optaget tid blokerer), og bookinger vises i kalenderen via et iCal-abonnement."),
        Capability("payment", "Kortbetaling og fakturaer", "available" if s.stripe_secret_key else "not_implemented", s.app_env,
                   ("Stripe" + (" (testtilstand)" if (s.stripe_secret_key or "").startswith("sk_test_") else "") +
                    ": kort gemmes hos Stripe, og hver måned faktureres bagud automatisk. Betaling starter aldrig opkald.")
                   if s.stripe_secret_key else "Kræver STRIPE_SECRET_KEY og STRIPE_WEBHOOK_SECRET på serveren."),
        Capability("ai.assistant_preview", "AI-assistent: intern forhåndsvisning", ai_status, s.app_env,
                   ai_note),
        Capability("ai.conversation", "AI-samtale med kunder", ai_status, s.app_env,
                   ("Kunderne taler med assistenten i web-widgetten"
                    + (" og i telefonen (Vapi, dansk transskribering)" if s.vapi_server_secret else "")
                    + ". Svarer kun ud fra godkendt viden.")
                   if ai_status != "not_implemented" else "Kræver en AI-udbyder (AI_PROVIDER)."),
        Capability("knowledge.source_import", "Forslag fra hjemmesiden", ai_status, s.app_env,
                   "Henter jeres egne sider og foreslår ydelser, fakta og spørgsmål som kladder, der skal godkendes. "
                   "Priser gættes aldrig." if ai_status != "not_implemented" else "Kræver en AI-udbyder (AI_PROVIDER)."),
        Capability("cvr.lookup", "Opslag i CVR-registret", "available" if s.cvr_username and s.cvr_password
                   else "not_implemented", s.app_env,
                   "Navn og adresse hentes fra CVR-registret, når I beder om det." if s.cvr_username and s.cvr_password
                   else "Kræver gratis adgang fra Erhvervsstyrelsen (CVR_USERNAME/CVR_PASSWORD)."),
        Capability("webchat", "Web-widget", ai_status, s.app_env,
                   "Chat-widget til jeres hjemmeside; svarer kun ud fra godkendt viden og kun på godkendte domæner."
                   if ai_status != "not_implemented" else "Kræver en AI-udbyder (AI_PROVIDER)."),
    ]


def capability(key: str) -> Capability:
    for c in capabilities():
        if c.key == key:
            return c
    raise KeyError(key)
