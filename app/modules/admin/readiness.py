"""M02: what a business customer is entitled to and how far its setup is, for the operator's customer page.

Read-only and side-effect free (no `get_or_create`, no grace sync): the operator looking at a customer must never
change it. The rules mirror what the customer sees in the guide (web/src/lib/setup.server.ts `setupStatus`,
setup-steps.ts `stepsFor`, setup-done.ts `profileIsDone`) and the live gates in the backend
(billing.agreements.subscription_paid, webchat.service.unavailable_reasons, campaigns `_billing_ready`).
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session as OrmSession

from app.models import (
    BillingAccount,
    BookingSettings,
    BusinessProfile,
    GoalSelection,
    IntegrationConnection,
    KnowledgeItem,
    KnowledgeVersion,
    TelephonySetup,
    WebchatSettings,
    Workspace,
)

CALENDARS = ("google_calendar", "microsoft_calendar")


def _subscription(db: OrmSession, ws_id: uuid.UUID, now: datetime) -> dict:
    from app.modules.billing import grace
    from app.modules.billing.agreements import current

    agreement = current(db, ws_id)
    acc = db.get(BillingAccount, ws_id)
    strictly = grace.strictly_paid(db, ws_id, now)
    ends = grace.grace_ends(acc, now)
    if strictly:
        state = "paid"
    elif ends is not None and now < ends:
        state = "grace"
    elif acc is not None and acc.first_paid_at is not None:
        state = "stopped"
    else:
        state = "never_paid"
    return {"state": state, "paid": state in ("paid", "grace"),
            "agreement": ({"model": agreement.model, "version": agreement.version,
                           "confirmed": agreement.model != "B"} if agreement else None),
            "card": bool(acc and acc.payment_method_id),
            "payment_failed": bool(acc and acc.payment_failed_at),
            "grace_ends": ends.isoformat() if state == "grace" and ends else None}


def customer_readiness(db: OrmSession, ws: Workspace, now: datetime | None = None) -> dict:
    now = now or datetime.now(UTC)
    goals = db.get(GoalSelection, ws.id)
    profile = db.get(BusinessProfile, ws.id)
    tel = db.scalar(select(TelephonySetup).where(TelephonySetup.workspace_id == ws.id))
    chat = db.get(WebchatSettings, ws.id)
    booking = db.get(BookingSettings, ws.id)
    sub = _subscription(db, ws.id, now)

    wants_phone = goals.inbound_phone if goals else True
    wants_chat = goals.webchat if goals else False
    wants_booking = goals.booking if goals else False
    intent = (goals.product_intent if goals else None) or ws.product_intent or "reception"
    reception = intent in ("reception", "both")
    campaigns = intent in ("campaigns", "both")

    approved = db.scalar(select(func.count()).select_from(KnowledgeVersion)
                         .join(KnowledgeItem, KnowledgeItem.id == KnowledgeVersion.item_id)
                         .where(KnowledgeItem.workspace_id == ws.id, KnowledgeVersion.status == "approved",
                                KnowledgeItem.archived_at.is_(None))) or 0
    calendar = db.scalar(select(IntegrationConnection.connector).where(
        IntegrationConnection.workspace_id == ws.id, IntegrationConnection.connector.in_(CALENDARS),
        IntegrationConnection.status == "connected").limit(1))
    profile_done = bool(profile and profile.legal_name.strip() and profile.description.strip()
                        and (not wants_phone or (profile.phone or "").strip()))
    phone_live = bool(tel and tel.state in ("active", "paused"))
    phone_set = phone_live or bool(tel and tel.business_number and tel.business_number_verified_at
                                   and tel.documents_status in ("not_required", "submitted", "approved"))
    if chat is not None:
        from app.modules.webchat.service import unavailable_reasons

        chat_missing = [r for r in unavailable_reasons(db, chat) if r not in ("disabled", "subscription_required")]
        chat_live = chat.enabled and not unavailable_reasons(db, chat)
    else:
        chat_missing, chat_live = ["not_set_up"], False

    def item(key: str, label: str, ok: bool, detail: str, applies: bool = True) -> dict:
        return {"key": key, "label": label, "ok": ok, "detail": detail, "applies": applies}

    steps = [
        item("virksomhed", "Virksomhed", profile_done,
             "Navn, beskrivelse" + (" og telefonnummer" if wants_phone else "") + (" udfyldt" if profile_done else " mangler")),
        item("viden", "Viden", approved > 0, f"{approved} godkendte vidensposter"),
        item("telefon", "Telefon", phone_set,
             f"status {tel.state}, nummer {'bekræftet' if tel.business_number_verified_at else 'ikke bekræftet'}, "
             f"dokumenter {tel.documents_status}" if tel else "ikke sat op", applies=wants_phone),
        item("chat", "Webchat", chat_live or (chat is not None and not chat_missing),
             "live" if chat_live else ("mangler: " + ", ".join(chat_missing) if chat_missing else
                                      "klar, men ikke live (slået fra eller ikke betalt)"), applies=wants_chat),
        item("kalender", "Kalender", calendar is not None,
             f"{calendar} forbundet" if calendar else "ingen kalender forbundet", applies=wants_booking),
        item("betaling", "Betaling", sub["paid"], {"paid": "betalt", "grace": "respit", "stopped": "stoppet",
                                                   "never_paid": "ikke betalt"}[sub["state"]]),
    ]
    live = (not wants_phone or phone_live) and (not wants_chat or chat_live)
    return {
        "entitlements": {
            "product_intent": intent,
            "subscription": sub,
            # The same gates the backend enforces: phone/chat go live and customer campaigns start only when paid.
            "reception_may_go_live": reception and sub["paid"],
            "campaigns_may_start": campaigns and sub["paid"],
            "booking_enabled": bool(booking and booking.enabled),
        },
        "readiness": {
            "goals": {"inbound_phone": wants_phone, "webchat": wants_chat, "booking": wants_booking},
            "steps": [s for s in steps if s["applies"]],
            "setup_done": all(s["ok"] for s in steps if s["applies"] and s["key"] != "betaling"),
            "live": bool(live and sub["paid"]),
            "channels": {"phone": "live" if phone_live else ("klar" if phone_set else "ikke klar"),
                         "webchat": "live" if chat_live else ("klar" if chat is not None and not chat_missing else "ikke klar"),
                         "booking": ("klar" if booking and booking.enabled and calendar else
                                     "slået til uden kalender" if booking and booking.enabled else "slået fra")},
        },
    }
