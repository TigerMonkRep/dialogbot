"""Which track books the user's appointment: the website (browser agent) or the phone? Rules in code, in this order:

1. The user said «ring» -> phone. The user said «skriv» -> the browser, if it can (otherwise the phone, and we say why). No questions.
2. The intent is not «book» (flyt/aflys are not automated in v1) -> phone.
3. A website was found, its engine is known and has a playbook, a booking address exists, and the user has a name and a verified
   phone on the profile -> browser. (Also needed: the worker is switched on, the booking price is on the Opkaldssaldo, and the user has asked for a
   CONCRETE booking: service + time window. Without the last one nothing starts: the assistant asks.)
4. Otherwise -> phone.

The model never picks the track: it only passes what the user said. This module is pure so each rule is tested on its own.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.config import get_settings
from browser_worker import playbooks  # the registry only: importing the package does not import Playwright

BLOCKER_TEXT = {
    "intent_not_book": "jeg kan endnu kun booke nye tider på hjemmesider, ikke flytte eller aflyse",
    "no_website": "jeg har ikke fundet en hjemmeside",
    "engine_unknown": "jeg kender ikke virksomhedens bookingsystem",
    "no_booking_url": "jeg kan ikke finde bookingsiden",
    "no_contact": "dit navn og dit bekræftede mobilnummer skal stå på din profil",
    "worker_disabled": "booking på hjemmesider er ikke slået til",
    "no_balance": "der er ikke nok på din opkaldssaldo",
}


@dataclass(frozen=True)
class Facts:
    user_said: str | None       # "ring" | "skriv" | None: only what the user EXPLICITLY asked for
    intent: str                 # book | flyt | aflys
    website: str | None
    engine: str                 # "unknown" when not detected
    booking_url: str | None
    has_name_and_phone: bool    # the user's own name and VERIFIED mobile number on the profile
    concrete: bool              # service + at least one dated time window
    worker_enabled: bool
    has_balance: bool


@dataclass(frozen=True)
class Decision:
    track: str                  # browser | phone | ask
    rule: int                   # 1-4
    reason: str                 # machine word: why (a blocker, or «ok»)

    @property
    def say_blocker(self) -> str:
        return BLOCKER_TEXT.get(self.reason, "")


def engine_supported(engine: str) -> bool:
    return engine in get_settings().browser_engines and engine in playbooks.REGISTRY


def blockers(f: Facts) -> list[str]:
    """Why the browser cannot be used, most fundamental first (concreteness is separate: it asks, it does not switch track)."""
    out = []
    if f.intent != "book":
        out.append("intent_not_book")
    if not f.website:
        out.append("no_website")
    elif not engine_supported(f.engine):
        out.append("engine_unknown")
    elif not f.booking_url:
        out.append("no_booking_url")
    if not f.has_name_and_phone:
        out.append("no_contact")
    if not f.worker_enabled:
        out.append("worker_disabled")
    if not f.has_balance:
        out.append("no_balance")
    return out


def decide(f: Facts) -> Decision:
    b = blockers(f)
    if f.user_said == "ring":
        return Decision("phone", 1, "user_said_ring")
    if f.user_said == "skriv":
        if b:
            return Decision("phone", 1, b[0])
        return Decision("ask", 1, "needs_details") if not f.concrete else Decision("browser", 1, "ok")
    if f.intent != "book":
        return Decision("phone", 2, "intent_not_book")
    if b:
        return Decision("phone", 4, b[0])
    return Decision("ask", 3, "needs_details") if not f.concrete else Decision("browser", 3, "ok")
