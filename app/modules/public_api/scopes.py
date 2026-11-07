"""Scopes of the public API, mapped onto the internal permission matrix (app.core.auth.PERMISSIONS).

A scope names what a key may do; the capability it maps to is the role check the same action needs in the app.
Issuing a key with a scope needs that capability (an admin cannot hand out more than an admin may do). Business
(`kind=business`) and personal (Dialogbot Privat) workspaces have separate scope sets; the Privat resources arrive
in phase 3 (docs/public-api.md) – today a Privat key only answers `GET /v1/me`.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Scope:
    name: str
    capability: str  # app.core.auth.PERMISSIONS key
    description: str
    write: bool = False


BUSINESS_SCOPES: dict[str, Scope] = {s.name: s for s in (
    Scope("calls:read", "telephony.read", "Læs opkald (tidspunkt, varighed, resumé, udfald)"),
    Scope("conversations:read", "conversations.read", "Læs samtaler og beskeder (webchat og telefon)"),
    Scope("bookings:read", "bookings.read", "Læs aftaler og aftaletyper"),
    Scope("bookings:write", "bookings.create", "Opret og aflys aftaler (fase 5 – ingen endpoints endnu)", write=True),
    Scope("leads:read", "leads.read", "Læs henvendelser"),
    Scope("knowledge:read", "knowledge.read", "Læs den godkendte viden"),
    Scope("knowledge:propose", "knowledge.draft", "Foreslå viden som kladde til godkendelse (fase 3)", write=True),
    Scope("campaigns:read", "campaigns.read", "Læs kampagner og ring-ikke-listen"),
    Scope("campaigns:write", "campaigns.read", "Tilføj numre til ring-ikke-listen", write=True),
    Scope("reports:read", "reports.read", "Læs daglige rapporter"),
    Scope("contacts:read", "leads.read", "Telefonnumre og e-mails i klartekst (ellers maskeret)"),
    Scope("webhooks:manage", "integrations.manage", "Opret, læs og slet webhooks", write=True),
)}

PERSONAL_SCOPES: dict[str, Scope] = {s.name: s for s in (
    Scope("tasks:read", "workspace.read", "Læs lister og påmindelser (fase 3)"),
    Scope("tasks:write", "workspace.read", "Opret lister og punkter (fase 3)", write=True),
    Scope("calls:read", "workspace.read", "Læs opkald assistenten har foretaget (fase 3)"),
    Scope("calls:propose", "workspace.read", "Foreslå et opkald – godkendes i appen (fase 3)", write=True),
    Scope("reminders:write", "workspace.read", "Opret og ret påmindelser (fase 3)", write=True),
)}


def scopes_for(kind: str) -> dict[str, Scope]:
    return BUSINESS_SCOPES if kind == "business" else PERSONAL_SCOPES


def validate(kind: str, requested: list[str]) -> list[str]:
    """Known scopes for the workspace kind, de-duplicated, in catalogue order. Raises ValueError on an unknown one."""
    catalogue = scopes_for(kind)
    unknown = [s for s in requested if s not in catalogue]
    if unknown:
        raise ValueError(", ".join(sorted(set(unknown))))
    wanted = set(requested)
    return [name for name in catalogue if name in wanted]
