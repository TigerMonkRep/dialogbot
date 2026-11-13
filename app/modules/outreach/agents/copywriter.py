"""OutreachCopywriterAgent – Claude (CLAUDE_WRITER_MODEL) writes three short plain-text lines from the LeadBrief. The
legal footer is NOT written by the model: it is appended here from localization.footer()."""
from __future__ import annotations

import json

from sqlalchemy.orm import Session as OrmSession

from app.config import get_settings
from app.models import OutreachLead, OutreachLog, OutreachMessage
from app.modules.outreach import llm, localization
from app.modules.outreach.compliance import Clearance
from app.modules.outreach.schemas import EmailDraft, LeadBrief

PROMPT_VERSION = "outreach-copy-v1"
MAX_WORDS = 90
SYSTEM = """You write one cold B2B e-mail from Dialogbot to the owner of a small service business. Plain text, under 80
words in total across the three lines, no greeting formula, no sign-off, no links other than {demo}.

Line 1 – the specific observation from the research brief about THIS business. Only state what the brief's evidence
supports; if you cite a review, quote only words that are in the brief. Never open with a generic line ("Hope this
finds you well", "My name is", "I wanted to reach out").
Line 2 – what Dialogbot does, using only these facts:
{facts}
Line 3 – {invite} Do NOT ask for a meeting or a call with sales.

Market: {country}. Spelling: {spelling}. If you mention the price, write exactly "{price}". {number}
The reader is a business. Never mention consumers, private users or anyone's name at Dialogbot. No promises, no
superlatives, no "guarantee", no "free". Subject: under 8 words, lower-key, about them, no "Re:".
Finish by calling submit_email."""


def word_count(text: str) -> int:
    return len(text.split())


class OutreachCopywriterAgent:
    def __init__(self, db: OrmSession):
        self.db = db
        self.s = get_settings()

    def run(self, lead: OutreachLead, brief: LeadBrief, clearance: Clearance) -> OutreachMessage:
        loc = localization.locale_for(lead.country)
        spelling = {"US": "US English", "UK": "British English", "INTL": "concise international English"}[loc.spelling]
        demo = localization.demo_url(lead.country)
        if loc.demo_line:   # the reader rings Dialogbot's own demo line and hears the assistant answer
            invite = (f"invite them to call Dialogbot's demo line on {loc.demo_line} and hear the AI receptionist "
                      f"answer: about 90 seconds, at any hour, no signup and no credit card. Write the number exactly "
                      f"as \"{loc.demo_line}\" and add {demo} for the details.")
            number = "Mention no other phone number."
        else:
            invite = (f"invite them to try the live 90-second callback demo at {demo}: they enter their phone number "
                      "and Dialogbot calls them right away, no signup and no credit card.")
            number = (f'The demo rings from the local number {loc.callback_number}; you may mention it.'
                      if loc.callback_number else "Do not mention any phone number or a local number.")
        system = SYSTEM.format(demo=demo, facts="\n".join("- " + f for f in localization.product_facts(lead.country)),
                               invite=invite, country=lead.country, spelling=spelling, price=loc.price, number=number)
        user = (f"<business>{json.dumps({'company': lead.company_name, 'niche': lead.niche, 'city': lead.city, 'country': lead.country})}</business>\n"
                f"<brief>{brief.model_dump_json()}</brief>")
        call = llm.structured(self.db, clearance=clearance, purpose="copy", model=self.s.claude_writer_model, system=system,
                              user=user, output=EmailDraft, tool_name="submit_email",
                              tool_description="Return the finished e-mail.", max_tokens=700, lead_id=lead.id)
        draft: EmailDraft = call.data
        msg = OutreachMessage(lead_id=lead.id, step=1, to_email=lead.email_normalized, subject=draft.subject.strip(),
                              body=draft.body, footer=localization.footer(lead.country, lead.company_name, lead.email_source),
                              word_count=word_count(draft.body), status="draft")
        self.db.add(msg)
        self.db.flush()
        self.db.add(OutreachLog(lead_id=lead.id, kind="copy", outcome="draft",
                                detail={"words": msg.word_count, "prompt_version": PROMPT_VERSION}))
        return msg
