"""PainPointResearchAgent – Claude (CLAUDE_RESEARCH_MODEL) reads what is known about the business, optionally searches
the web, and returns a LeadBrief. What the model claims is then checked: a quote that cannot be found in the supplied
text is dropped, and a brief without verifiable evidence cannot reach the confidence the pipeline asks for."""
from __future__ import annotations

import json
import re

from sqlalchemy.orm import Session as OrmSession

from app.config import get_settings
from app.models import OutreachLead, OutreachLog
from app.modules.outreach import llm
from app.modules.outreach.compliance import Clearance
from app.modules.outreach.schemas import LeadBrief

PROMPT_VERSION = "outreach-research-v1"
SYSTEM = """You research one small service business for a B2B sales team that sells an AI phone receptionist.
Find out how the business handles phone calls today and whether customers complain about reaching it.

Rules:
- Use only what is in the supplied material{search}. Never invent a review, a quote or a fact.
- A review snippet must be the reviewer's own words, verbatim, and must be about missed calls, unreturned voicemails
  or long hold times. If there is none, return an empty list.
- call_handling: voicemail, callback_form, answering_service or staffed_reception only when something shows it;
  otherwise unknown.
- ticket_value: a realistic range for one typical job or visit in this niche and country, in local currency.
- personalization_hook: one concrete observation about THIS business that an e-mail could open with. If all you have is
  the niche and the city, say so in the hook and set confidence_score below 0.5.
- confidence_score: high only when the hook is specific and backed by evidence you return.
- is_business = false if this looks like a private person rather than a business.
Finish by calling submit_lead_brief."""


def _norm(t: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (t or "").lower()).strip()


class PainPointResearchAgent:
    def __init__(self, db: OrmSession):
        self.db = db
        self.s = get_settings()

    def run(self, lead: OutreachLead, clearance: Clearance) -> LeadBrief | None:
        """The brief, or None when the lead is rejected (not a business, or confidence under the threshold)."""
        search = self.s.outreach_web_search
        facts = {"company": lead.company_name, "niche": lead.niche, "city": lead.city, "country": lead.country,
                 "website": lead.website}
        user = (f"<lead>{json.dumps(facts, ensure_ascii=False)}</lead>\n"
                f"<material>\n{(lead.context or '(nothing supplied)')[:12000]}\n</material>")
        call = llm.structured(
            self.db, clearance=clearance, purpose="research", model=self.s.claude_research_model,
            system=SYSTEM.format(search=" and what you find with web search (their website, Google and Yelp reviews)" if search else ""),
            user=user, output=LeadBrief, tool_name="submit_lead_brief",
            tool_description="Return the finished research brief for this business.", web_search=search, lead_id=lead.id)
        brief = self._verify(call.data, lead, searched=search)
        lead.brief = brief.model_dump()
        lead.confidence_score = brief.confidence_score
        ok = brief.is_business and brief.confidence_score >= self.s.outreach_min_confidence
        lead.status = "researched" if ok else ("disqualified" if not brief.is_business else "low_confidence")
        self.db.add(OutreachLog(lead_id=lead.id, kind="research", outcome=lead.status,
                                detail={"confidence": brief.confidence_score, "prompt_version": PROMPT_VERSION,
                                        "model_confidence": call.data.confidence_score,
                                        "snippets_kept": len(brief.review_snippets),
                                        "snippets_dropped": len(call.data.review_snippets) - len(brief.review_snippets)}))
        return brief if ok else None

    def _verify(self, brief: LeadBrief, lead: OutreachLead, *, searched: bool) -> LeadBrief:
        material = _norm(lead.context or "")
        kept = []
        for sn in brief.review_snippets:
            in_material = len(_norm(sn.quote)) >= 12 and _norm(sn.quote) in material
            from_web = searched and (sn.source_url or "").startswith("http") and sn.source_type != "provided_context"
            if in_material or from_web:
                kept.append(sn)
        handling = brief.call_handling != "unknown" and bool(brief.call_handling_evidence.strip())
        conf = brief.confidence_score
        if not kept and not handling:
            conf = min(conf, 0.4)   # nothing to stand on: the hook would be generic or made up
        return brief.model_copy(update={"review_snippets": kept, "confidence_score": conf})
