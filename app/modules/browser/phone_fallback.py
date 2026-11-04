"""The phone track after the browser could not book: the task's `call` part is created or updated with what the agent
found, so the call starts smarter («ydelse», «tider, der var ledige på hjemmesiden»).

This only PREPARES the normal call proposal (a `PrivateCall` in status `proposed`). Nothing is dialled: the user approves the
call exactly as any other call (credits/plan, mobile number, opening hours), see app/modules/privat/calls.py.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session as OrmSession

from app.models import BrowserRun, PrivateCall, PrivateTask
from app.modules.privat import calls, rules
from app.modules.privat import service as privat_service

REASONS = {
    "captcha": "siden bad om en sikkerhedskontrol, som jeg ikke må løse",
    "login_required": "siden kræver login",
    "no_availability": "der var ingen ledige tider i dit tidsvindue",
    "budget_steps": "det tog for mange trin",
    "budget_time": "det tog for lang tid",
    "session_expired": "forslaget var udløbet",
    "unexpected_step": "siden bad om en bekræftelse, jeg ikke havde forventet",
    "dns_failed": "siden kunne ikke åbnes",
    "intent_unsupported": "jeg kan endnu ikke ændre eller aflyse tider på hjemmesider",
    "ai_unavailable": "jeg kunne ikke finde ud af siden",
    "llm_gave_up": "jeg kunne ikke finde ud af siden",
    "user_switched": "du bad om et opkald i stedet",
}


def reason_text(code: str) -> str:
    if code in REASONS:
        return REASONS[code]
    return "jeg kunne ikke finde ud af siden" if code.startswith("playbook:") else "bookingen på siden lykkedes ikke"


def describe_found(found: dict | None) -> str:
    """What the browser saw that is worth telling the person on the phone. Danish, short, nothing invented."""
    found = found or {}
    parts: list[str] = []
    if found.get("service"):
        parts.append(f"Ydelse: {found['service']}")
    times = found.get("times_seen") or {}
    if times:
        parts.append("Ledige tider på hjemmesiden: " + "; ".join(f"{d}: {', '.join(ts)}" for d, ts in list(times.items())[:4]))
    elif found.get("dates_seen"):
        parts.append("Datoer på hjemmesiden: " + ", ".join(found["dates_seen"][:6]))
    return ". ".join(parts)


def apply(db: OrmSession, run: BrowserRun, task: PrivateTask, found: dict | None, code: str) -> PrivateCall:
    c = db.scalar(select(PrivateCall).where(PrivateCall.task_id == task.id).order_by(PrivateCall.created_at.desc(),
                                                                                     PrivateCall.id).limit(1))
    goal = run.goal or {}
    window = _window_text(goal)
    service_name = goal.get("service") or "en tid"
    if c is None or c.status != "proposed":
        c = PrivateCall(workspace_id=run.workspace_id, task_id=task.id, status="proposed", created_at=rules.now(),
                        business_name=(goal.get("business_name") or task.title)[:200],
                        business_address=(goal.get("business_address") or "")[:300],
                        business_phone_e164=goal.get("business_phone"), phone_source=goal.get("phone_source"),
                        place_id=goal.get("place_id"), purpose=f"Book {service_name}"[:2000], window=window[:200],
                        may_ask=f"Om de kan {service_name.lower()} {window}, og hvad det koster".strip(),
                        may_agree=f"En tid {window}".strip() if window else "Et tidspunkt, der passer",
                        may_not="Betale, give andre oplysninger end dit navn, eller sige ja til ekstra arbejde eller andre tider")
        db.add(c)
    seen = describe_found(found)
    if seen:  # the call knows what the website showed: «Ledige tider på hjemmesiden: …» (may be out of date when it rings)
        note = f"{seen}. Tjek, at tiden stadig er ledig."
        c.may_ask = f"{c.may_ask}. {note}"[:2000]
        c.purpose = c.purpose[:1500]
    task.kind = "call"
    task.status, task.next_step, task.who = "awaiting_user", "Godkend opkaldet", "Dig"
    task.usage_text = calls.pending_usage_text(db, task.workspace_id)
    db.flush()
    privat_service.event(db, task, "Opkaldet er klar som forslag" + (f" – {seen}" if seen else ""))
    return c


def _window_text(goal: dict) -> str:
    w = (goal.get("preferred_windows") or [{}])[0]
    if not w.get("date"):
        return ""
    t = f" kl. {w['from']}–{w['to']}" if w.get("from") and w.get("to") else ""
    return f"{w['date']}{t}"
