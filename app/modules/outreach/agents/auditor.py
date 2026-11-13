"""ComplianceAndSafetyAuditorAgent – nothing is queued without passing here.

1. Deterministic checks (no model): market still allowed, not suppressed, word count, the exact legal footer with
   {{unsubscribe_link}}, no B2C wording or "Peter", no generic opener, no meeting push, only our own link, price and
   phone number exactly as configured, plain text, honest subject.
2. Only if those pass: an adversarial read by Claude Haiku (CLAUDE_AUDITOR_MODEL) that compares every claim in the
   e-mail with the research evidence and the product facts.
3. Daily sending limits per inbox and per sending domain decide whether the e-mail is queued for today or deferred.
"""
from __future__ import annotations

import re
from datetime import UTC, date, datetime

from sqlalchemy.orm import Session as OrmSession

from app.config import get_settings
from app.models import OutreachLead, OutreachLog, OutreachMessage
from app.modules.outreach import llm, localization
from app.modules.outreach.agents.copywriter import MAX_WORDS, word_count
from app.modules.outreach.compliance import ComplianceEngine, LeadFacts, rate_limits
from app.modules.outreach.schemas import AuditVerdict

PROMPT_VERSION = "outreach-audit-v1"
PH = localization.UNSUBSCRIBE_PLACEHOLDER

_GENERIC = re.compile(r"^\W*(i\s+)?(hope (this|you)|my name is|i wanted to reach out|i'?m reaching out|just (reaching|checking)|"
                      r"i came across your|quick question|hi there|hello|dear )", re.I)
_B2C = re.compile(r"\b(peter|b2c|consumers?|private (users?|persons?|individuals?|customers?)|dialogbot privat|"
                  r"personal assistant|households?|your family)\b", re.I)
_MEETING = re.compile(r"\b(\d{2}[- ]?min(ute)?s?\b(?! callback)|book (a|an|your) (call|meeting|slot|time)|"
                      r"schedule (a|an|your) (call|meeting|chat)|calendly|(hop|jump) on a call|sales (call|meeting)|"
                      r"discovery call)", re.I)
_CLAIMS = re.compile(r"(\bguarantee[ds]?\b|\brisk[- ]free\b|100\s?%|#1\b|\bnumber one\b|\bbest[- ]in[- ]class\b|\biso[- ]?\d+|"
                     r"\bsla\b|\bcertified\b|\bfree\b|\bnever miss(es)? (a|another) call\b)", re.I)
_URL = re.compile(r"(?:https?://|www\.)[^\s)>\]]+|\b[a-z0-9-]+\.(?:com|app|dk|io|net|co|ai)\b[^\s)]*", re.I)
_PRICE = re.compile(r"([$£€]\s?\d[\d.,]*|\d[\d.,  ]*\s?(?:kr\.?|eur|usd|gbp|sek|nok|dkk))\s*(?:/|per|a)\s?(?:mo|month)", re.I)
_PHONE = re.compile(r"\+\d[\d\s().-]{6,}\d")
_LOCAL_NUMBER = re.compile(r"\+(1|44)\b|\blocal (callback )?number\b", re.I)
_MARKUP = re.compile(r"<[a-z/][^>]*>|\*\*|\]\(|^#{1,3} ", re.I | re.M)


def _digits(t: str | None) -> str:
    return re.sub(r"\D", "", t or "")


def deterministic_issues(db: OrmSession, lead: OutreachLead, msg: OutreachMessage) -> list[str]:
    issues: list[str] = []
    decision = ComplianceEngine(db).evaluate(LeadFacts(
        company_name=lead.company_name, email=lead.email_normalized, country=lead.country,
        email_source=lead.email_source, email_source_url=lead.email_source_url,
        registration_number=lead.registration_number))
    if not decision.allowed:
        return [f"compliance: {decision.action} – {'; '.join(decision.reasons)}"]
    loc = localization.locale_for(lead.country)
    body, subject = msg.body, msg.subject

    if word_count(body) >= MAX_WORDS:
        issues.append(f"word_count: {word_count(body)} words (must be under {MAX_WORDS}, footer excluded)")
    if len([p for p in body.split("\n\n") if p.strip()]) != 3:
        issues.append("structure: the body must be exactly three lines")
    if msg.footer != localization.footer(lead.country, lead.company_name, lead.email_source):
        issues.append("footer: not the mandatory footer for this market")
    if msg.footer.count(PH) != 1 or localization.sender_line() not in msg.footer:
        issues.append("footer: sender identity or {{unsubscribe_link}} missing")
    if PH in body or PH in subject:
        issues.append("footer: {{unsubscribe_link}} belongs in the footer only")
    if _GENERIC.search(body):
        issues.append("opener: generic opening line")
    for label, text in (("body", body), ("subject", subject)):
        if m := _B2C.search(text):
            issues.append(f"b2c: '{m.group(0)}' in the {label}")
        if m := _CLAIMS.search(text):
            issues.append(f"claim: '{m.group(0)}' in the {label}")
        if m := _MARKUP.search(text):
            issues.append(f"plain_text: markup '{m.group(0)}' in the {label}")
    if m := _MEETING.search(body):
        issues.append(f"meeting_push: '{m.group(0)}'")
    urls = _URL.findall(body)
    if any("dialogbot.app" not in u.lower() for u in urls):
        issues.append("links: only dialogbot.app may be linked")
    if "dialogbot.app" not in body.lower():
        issues.append("cta: the demo at https://dialogbot.app is missing")
    if loc.demo_line and _digits(loc.demo_line) not in _digits(body):
        issues.append(f"cta: the demo line {loc.demo_line} is missing")
    want = loc.price.split("/")[0]
    for m in _PRICE.finditer(body):
        got = m.group(1).strip()
        if _digits(got) != _digits(want) or (want[0] in "$£€" and got[0] != want[0]):
            issues.append(f"price: '{m.group(0)}' is not the price for {lead.country} ({loc.price})")
    for m in _PHONE.finditer(body):
        if _digits(m.group(0)) not in {_digits(n) for n in (loc.callback_number, loc.demo_line) if n}:
            issues.append(f"phone: '{m.group(0)}' is not the configured callback number or demo line")
    if not (loc.callback_number or loc.demo_line) and _LOCAL_NUMBER.search(body):
        issues.append("phone: mentions a local number, none is configured for this market")
    if re.match(r"\s*(re|fwd?)\s*:", subject, re.I):
        issues.append("subject: pretends to be a reply or a forward")
    if len(subject) > 70 or sum(1 for w in subject.split() if len(w) > 3 and w.isupper()) >= 2 or "!!" in subject:
        issues.append("subject: too long or shouting")
    return issues


SYSTEM = """You are a hostile compliance reviewer for cold B2B e-mail. Fail the e-mail if ANY of this is true:
- It states something about the recipient's business that the research evidence does not support, or quotes a review
  with words that are not in the evidence (unsupported_personalization).
- It makes a claim about Dialogbot that goes beyond the product facts, or a promise, a number or a comparison that
  is not in them (deceptive_claim).
- The subject line misleads about what the e-mail is (deceptive_claim).
- It addresses a consumer or private person, or names a person at Dialogbot (b2c).
- It pushes for a meeting or sales call instead of the 90-second demo in the product facts (meeting_push).
- It pressures, flatters dishonestly or invents urgency (tone).
When in doubt, fail. Quote the offending words. Finish by calling submit_audit."""


class ComplianceAndSafetyAuditorAgent:
    def __init__(self, db: OrmSession):
        self.db = db
        self.s = get_settings()

    def review(self, lead: OutreachLead, msg: OutreachMessage, *, today: date | None = None) -> OutreachMessage:
        today = today or datetime.now(UTC).date()
        issues = deterministic_issues(self.db, lead, msg)
        model_audit: dict = {"ran": False}
        if not issues:
            # A clearance exists here: deterministic_issues() returned early unless the engine said EMAIL.
            clearance = ComplianceEngine(self.db).evaluate(LeadFacts(
                company_name=lead.company_name, email=lead.email_normalized, country=lead.country,
                email_source=lead.email_source, email_source_url=lead.email_source_url)).clearance()
            loc = localization.locale_for(lead.country)
            user = (f"<email>\nSubject: {msg.subject}\n\n{msg.body}\n</email>\n<evidence>{lead.brief}</evidence>\n"
                    f"<product_facts>{' '.join(localization.product_facts(lead.country))} Price in this market: {loc.price}.</product_facts>")
            call = llm.structured(self.db, clearance=clearance, purpose="audit", model=self.s.claude_auditor_model,
                                  system=SYSTEM, user=user, output=AuditVerdict, tool_name="submit_audit",
                                  tool_description="Return the audit verdict.", max_tokens=600, lead_id=lead.id)
            verdict: AuditVerdict = call.data
            model_audit = {"ran": True, **verdict.model_dump()}
            if verdict.verdict == "fail" or verdict.issues:
                issues += [f"{i.category}: {i.quote} – {i.explanation}" for i in verdict.issues] or ["model audit: fail"]
        msg.audit = {"passed": not issues, "issues": issues, "model": model_audit, "prompt_version": PROMPT_VERSION,
                     "checked_at": datetime.now(UTC).isoformat()}
        if issues:
            msg.status, lead.status = "rejected", "audit_failed"
        else:
            inbox = rate_limits.pick_inbox(self.db, today)
            if inbox:
                msg.status, msg.sender_inbox, msg.send_on = "queued", inbox, today
            else:
                msg.status = "deferred"   # every inbox is at its daily limit; queue_deferred() picks it up another day
            lead.status = "queued"
        self.db.flush()
        self.db.add(OutreachLog(lead_id=lead.id, kind="audit", outcome="passed" if not issues else "failed",
                                detail={"issues": issues, "message_status": msg.status}))
        return msg

    def queue_deferred(self, *, today: date | None = None) -> int:
        """Give deferred e-mails an inbox once there is capacity again. Returns how many were queued."""
        from sqlalchemy import select

        today = today or datetime.now(UTC).date()
        n = 0
        for msg in self.db.scalars(select(OutreachMessage).where(OutreachMessage.status == "deferred")
                                   .order_by(OutreachMessage.created_at)):
            inbox = rate_limits.pick_inbox(self.db, today)
            if not inbox:
                break
            msg.status, msg.sender_inbox, msg.send_on = "queued", inbox, today
            self.db.flush()
            n += 1
        return n
