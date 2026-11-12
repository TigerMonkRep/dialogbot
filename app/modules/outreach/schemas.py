"""Structured outputs of the agents. The JSON schemas below are handed to Claude as tool input schemas, and every
tool call is validated against the pydantic model before it is used."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

NICHES = ("plumber", "hvac", "dentist", "med spa", "auto repair", "hair salon")


class Evidence(BaseModel):
    quote: str = Field(max_length=400, description="Verbatim words from the source – never paraphrased or invented")
    source_type: Literal["website", "google_review", "yelp_review", "other_review", "provided_context"]
    source_url: str | None = Field(default=None, max_length=500)


class TicketValue(BaseModel):
    low: int = Field(ge=0)
    high: int = Field(ge=0)
    currency: str = Field(min_length=3, max_length=3)
    basis: str = Field(max_length=200, description="How the estimate was reached (niche norm, prices on their site …)")


class LeadBrief(BaseModel):
    business_summary: str = Field(max_length=400)
    is_business: bool = Field(description="False if this is a private person or a consumer, not a business")
    call_handling: Literal["voicemail", "callback_form", "answering_service", "staffed_reception", "unknown"]
    call_handling_evidence: str = Field(max_length=300, description="What shows it; empty string when unknown")
    review_snippets: list[Evidence] = Field(default_factory=list, max_length=5,
                                            description="Only reviews about missed calls, unreturned voicemails or long hold times")
    ticket_value: TicketValue
    personalization_hook: str = Field(max_length=300, description="One specific, true observation the e-mail can open with")
    confidence_score: float = Field(ge=0, le=1, description="How sure you are that the hook is specific AND backed by evidence")


class EmailDraft(BaseModel):
    subject: str = Field(min_length=3, max_length=70)
    line1: str = Field(min_length=10, max_length=400, description="The specific observation")
    line2: str = Field(min_length=10, max_length=400, description="What Dialogbot does")
    line3: str = Field(min_length=10, max_length=300, description="The invitation to the 90-second callback demo")

    @property
    def body(self) -> str:
        return "\n\n".join(x.strip() for x in (self.line1, self.line2, self.line3))


class AuditIssue(BaseModel):
    category: Literal["deceptive_claim", "unsupported_personalization", "b2c", "meeting_push", "tone", "other"]
    quote: str = Field(max_length=300)
    explanation: str = Field(max_length=300)


class AuditVerdict(BaseModel):
    verdict: Literal["pass", "fail"]
    issues: list[AuditIssue] = Field(default_factory=list, max_length=10)


def tool(name: str, description: str, model: type[BaseModel]) -> dict:
    return {"name": name, "description": description, "input_schema": model.model_json_schema()}
