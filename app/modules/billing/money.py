"""Money and pricing rules kept as pure functions for the billing stage.

NOT wired to any endpoint in stage 1. They exist so the domain model cannot
drift into the export's known defects (DB-001, DB-002) and so the fixture
examples in canonical-demo-data.json are enforced by tests from day one.

Rules encoded:
- amounts are integers in minor units with explicit currency; net/tax/gross
  are snapshotted together; no floats;
- reception model A (subscription) and model B (per approved lead) are
  mutually exclusive; the lead count never changes a model-A total;
- callback is part of reception, never a third price plan;
- a campaign package has a fixed net price, max attempts and max connected
  seconds; payment never starts calls (that is a state, not a price rule);
- an unbilled dispute uphold excludes the line without a credit note; a
  rejection keeps the charge for the next invoice; neither creates a credit note.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

ReceptionModel = Literal["A", "B"]


@dataclass(frozen=True)
class Money:
    currency: str
    net_minor: int
    tax_basis_points: int  # 2500 = 25 %

    @property
    def tax_minor(self) -> int:
        # round half up on integer arithmetic
        return (self.net_minor * self.tax_basis_points + 5000) // 10000

    @property
    def gross_minor(self) -> int:
        return self.net_minor + self.tax_minor

    def snapshot(self) -> dict:
        return {"currency": self.currency, "net_minor": self.net_minor, "tax_minor": self.tax_minor,
                "gross_minor": self.gross_minor, "tax_basis_points": self.tax_basis_points, "rounding": "half_up"}


@dataclass(frozen=True)
class ReceptionAgreement:
    model: ReceptionModel
    monthly_net_minor: int = 0        # model A
    lead_fee_net_minor: int = 0       # model B
    included_chats: int = 0
    included_ai_minutes: int = 0


@dataclass(frozen=True)
class CampaignPackageTerms:
    net_minor: int
    max_attempts: int
    max_connected_ai_seconds_total: int


def reception_total_net(agreement: ReceptionAgreement, approved_leads: int) -> int:
    if agreement.model == "A":
        return agreement.monthly_net_minor  # leads never change a model-A total
    if agreement.model == "B":
        return agreement.lead_fee_net_minor * approved_leads
    raise ValueError("reception model must be A or B; callback is not a model")


def campaign_total_net(terms: CampaignPackageTerms, packages: int) -> int:
    if packages < 0:
        raise ValueError("packages must be >= 0")
    return terms.net_minor * packages


def calculator_total_net(agreement: ReceptionAgreement, approved_leads: int, terms: CampaignPackageTerms,
                         packages: int) -> int:
    return reception_total_net(agreement, approved_leads) + campaign_total_net(terms, packages)


@dataclass(frozen=True)
class LeadBillingState:
    approved_count: int
    approved_subtotal_net_minor: int
    suspended_total_net_minor: int
    excluded_net_minor: int = 0
    next_invoice_addition_net_minor: int = 0
    credit_note_created: bool = False


def decide_unbilled_dispute(state: LeadBillingState, *, disputed_net_minor: int,
                            ruling: Literal["uphold", "reject"]) -> LeadBillingState:
    """Alternative outcome from the same start state. Never apply sequentially."""
    if ruling == "uphold":
        return LeadBillingState(
            approved_count=state.approved_count,
            approved_subtotal_net_minor=state.approved_subtotal_net_minor,
            suspended_total_net_minor=state.suspended_total_net_minor - disputed_net_minor,
            excluded_net_minor=state.excluded_net_minor + disputed_net_minor,
            credit_note_created=False,
        )
    if ruling == "reject":
        return LeadBillingState(
            approved_count=state.approved_count + 1,
            approved_subtotal_net_minor=state.approved_subtotal_net_minor + disputed_net_minor,
            suspended_total_net_minor=state.suspended_total_net_minor - disputed_net_minor,
            next_invoice_addition_net_minor=state.next_invoice_addition_net_minor + disputed_net_minor,
            credit_note_created=False,
        )
    raise ValueError("ruling must be uphold or reject")
