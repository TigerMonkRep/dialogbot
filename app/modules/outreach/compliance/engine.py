"""ComplianceEngine: the deterministic gate every lead passes before anything else happens to it.

No model call, no enrichment and no send may take place without a `Clearance`, and only `Decision.clearance()` of an
EMAIL decision hands one out. The engine itself never calls a model or the network: it reads the lead's own fields,
the matrix and the suppression list.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import StrEnum

from sqlalchemy.orm import Session as OrmSession

from app.config import get_settings
from app.modules.outreach import suppression
from app.modules.outreach.compliance import matrix as m

RULESET = "outreach-compliance-v1"
_EMAIL = re.compile(r"^[^@\s]+@([a-z0-9-]+\.)+[a-z]{2,}$")
_mint = object()


class Action(StrEnum):
    EMAIL = "EMAIL"            # cold e-mail may be prepared (and sent, once audited)
    CALL_QUEUE = "CALL_QUEUE"  # no e-mail; a person may ring the company
    HOLD = "HOLD"              # market awaits a lawyer's sign-off; nothing happens
    BLOCK = "BLOCK"


class ComplianceBlocked(Exception):
    """Something tried to act on a lead without an EMAIL decision."""


@dataclass(frozen=True)
class LeadFacts:
    company_name: str
    email: str
    country: str
    email_source: str = "unknown"
    email_source_url: str | None = None
    registration_number: str | None = None


@dataclass(frozen=True)
class Clearance:
    """Proof that the ComplianceEngine allowed e-mail to this address. Only Decision.clearance() creates one."""

    email: str
    country: str
    _token: object = field(repr=False, compare=False, default=None)

    def __post_init__(self):
        if self._token is not _mint:
            raise ComplianceBlocked("a Clearance is only issued by the ComplianceEngine")


@dataclass(frozen=True)
class Decision:
    action: Action
    country: str
    email: str
    reasons: tuple[str, ...]
    regime: str = ""
    ruleset: str = RULESET

    @property
    def allowed(self) -> bool:
        return self.action is Action.EMAIL

    def clearance(self) -> Clearance:
        if not self.allowed:
            raise ComplianceBlocked(f"{self.country}: {self.action} – {'; '.join(self.reasons)}")
        return Clearance(email=self.email, country=self.country, _token=_mint)

    def out(self) -> dict:
        return {"action": str(self.action), "country": self.country, "reasons": list(self.reasons), "regime": self.regime,
                "ruleset": self.ruleset}


def _ends_with_form(name: str, forms: tuple[str, ...]) -> bool:
    n = re.sub(r"[.,]", "", (name or "").strip().lower())
    return any(n.endswith(" " + f) or n == f for f in forms)


class ComplianceEngine:
    def __init__(self, db: OrmSession):
        self.db = db
        self.settings = get_settings()

    def evaluate(self, lead: LeadFacts, channel: str = "email") -> Decision:
        country = m.normalize_country(lead.country)
        email = (lead.email or "").strip().lower()

        def out(action: Action, *reasons: str, regime: str = "") -> Decision:
            return Decision(action=action, country=country, email=email, reasons=tuple(reasons), regime=regime)

        if channel in m.FORBIDDEN_CHANNELS:
            return out(Action.BLOCK, f"channel '{channel}' is never used towards a cold contact")
        if channel != "email":
            return out(Action.BLOCK, f"unknown channel '{channel}'")
        j = m.MATRIX.get(country)
        if j is None:
            return out(Action.BLOCK, f"country '{country or '?'}' is not in the approved matrix")
        if not _EMAIL.match(email):
            return out(Action.BLOCK, "e-mail address is not valid", regime=j.regime)
        domain = email.rsplit("@", 1)[1]
        hit = suppression.find(self.db, email)
        if hit:
            return out(Action.BLOCK, f"suppressed ({hit.kind}: {hit.reason})", regime=j.regime)

        if j.status == "blocked":
            if country in self.settings.outreach_call_queue and country == "DK":
                if not _ends_with_form(lead.company_name, m.DK_FORMS):
                    return out(Action.BLOCK, "opt-in market; not an ApS or A/S, so not placed on the call list", regime=j.regime)
                if not (lead.registration_number or "").strip():
                    return out(Action.BLOCK, "opt-in market; no CVR number to check reklamebeskyttelse against", regime=j.regime)
                return out(Action.CALL_QUEUE, "opt-in market: no cold e-mail, SMS or DM; manual call list only", regime=j.regime)
            return out(Action.BLOCK, "opt-in market: cold e-mail, SMS and DM are not allowed", regime=j.regime)
        if j.status == "hold" and country not in self.settings.outreach_signed_off:
            return out(Action.HOLD, "market awaits legal sign-off (OUTREACH_SIGNED_OFF_MARKETS)", regime=j.regime)

        reasons: list[str] = []
        if domain in m.WEBMAIL_DOMAINS and not j.webmail_allowed:
            reasons.append(f"webmail address ({domain}): likely a private person, sole trader or partnership")
        if j.legal_forms and not _ends_with_form(lead.company_name, j.legal_forms):
            reasons.append("not a corporate subscriber: company name does not end in " + "/".join(j.legal_forms).upper())
        if j.role_address_only and email.split("@", 1)[0] not in m.ROLE_LOCAL_PARTS:
            reasons.append("only generic company addresses (info@, post@ …) may be used in this market")
        if j.published_source_required and not (
                lead.email_source == "published_website" and (lead.email_source_url or "").startswith("http")):
            reasons.append("implied consent needs the page where the business itself published this address")
        if reasons:
            return out(Action.BLOCK, *reasons, regime=j.regime)
        return out(Action.EMAIL, f"tier {j.tier} market", regime=j.regime)
