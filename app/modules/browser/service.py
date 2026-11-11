"""Browser runs, backend side (no Playwright import here: the API image does not have it).

State machine (`browser_runs.status`):

    planned ─▶ running ─▶ awaiting_approval ─▶ approved ─▶ running ─▶ done
                 │              │ decline                     │
                 ▼              ▼                             ▼
          fallback_phone     failed(declined)      failed / fallback_phone

Every transition that two processes could race for (start, approve, resume) is a compare-and-set UPDATE (`cas`), so a run
is driven by exactly one executor and a booking is confirmed at most once, whatever happens to the outbox events.
"""
from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.orm import Session as OrmSession

from app.config import get_settings
from app.core import outbox
from app.core.errors import Conflict, Forbidden, NotFound, ValidationFailed
from app.models import BrowserRun, PrivateMessage, PrivateTask
from app.modules.billing import markets, prices
from app.modules.browser import storage
from app.modules.browser.events import BROWSER_EVENT_TYPES, EVENT_DECISION, EVENT_RUN  # noqa: F401
from app.modules.privat import ledger, sharing
from app.modules.privat import service as privat_service

ACTIVE = ("planned", "running", "awaiting_approval", "approved")
FINAL = ("done", "failed", "fallback_phone")
APPROVAL_MAX_AGE = timedelta(hours=24)  # a yes older than a day no longer fits the slot that was shown
INTENTS = ("book", "flyt", "aflys")
SAME_AS_APPROVED_KEYS = ("service", "date", "time", "price", "name", "staff")
# What a browser booking costs on the Opkaldssaldo (øre, DKK; markets.privat_from_dkk for other currencies). It cost
# 1 credit until 2026-11-11 and has no price of its own by decision yet, so it is the converted 2,90 kr.
# (prices.PRIVAT_BROWSER_BOOKING_MINOR). Reserved at start, spent when the run ends in a booking (or in a click that
# may have booked), released when nothing was booked.
BROWSER_BOOKING_MINOR = prices.PRIVAT_BROWSER_BOOKING_MINOR


def booking_price(db: OrmSession, ws_id) -> int:
    return markets.privat_from_dkk(BROWSER_BOOKING_MINOR, ledger.currency(db, ws_id))
SPENT_ERROR_CODES = ("unexpected_commit", "commit_unconfirmed")


def _now() -> datetime:
    return datetime.now(UTC)


# --------------------------------------------------------------------------- starting a run

def validate_goal(goal: dict) -> dict:
    if goal.get("intent") not in INTENTS:
        raise ValidationFailed("Ukendt ønske", field_errors=[{"field": "intent"}])
    contact = goal.get("contact") or {}
    if not str(contact.get("name") or "").strip():
        raise ValidationFailed("Navn mangler", field_errors=[{"field": "contact.name"}])
    out = {"intent": goal["intent"], "service": str(goal.get("service") or "")[:200],
           "preferred_windows": [w for w in (goal.get("preferred_windows") or []) if isinstance(w, dict) and w.get("date")][:10],
           "contact": {k: str(contact[k])[:200] for k in ("name", "phone", "mail") if contact.get(k)}}
    if goal.get("business_name"):
        out["business_name"] = str(goal["business_name"])[:200]
    if goal.get("business_address"):  # the location of the appointment in the user's calendar (Kalender app)
        out["business_address"] = str(goal["business_address"])[:300]
    return out


def start_run(db: OrmSession, task: PrivateTask, *, goal: dict, allowed_domains: list[str], engine: str,
              booking_url: str) -> BrowserRun:
    """Plan a run for the caller's own task and queue it. Nothing is done on any website before the worker picks it up,
    and nothing is confirmed before the user says yes."""
    from browser_worker import netguard

    s = get_settings()
    if not s.browser_worker_enabled:
        raise Forbidden("Booking på hjemmesider er ikke slået til", code="browser_worker_disabled")
    if engine not in s.browser_engines:
        raise Conflict("Den bookingmotor må agenten ikke bruge endnu", code="engine_not_allowed")
    try:
        domains = netguard.normalize_domains(allowed_domains)
        host = netguard.normalize_domain(booking_url)
    except ValueError as e:
        raise ValidationFailed("Ugyldigt domæne", field_errors=[{"field": "allowed_domains"}]) from e
    if not netguard.host_allowed(host, domains):
        raise ValidationFailed("Booking-adressen ligger uden for de godkendte domæner",
                               field_errors=[{"field": "booking_url"}])
    if db.scalar(select(BrowserRun.id).where(BrowserRun.task_id == task.id, BrowserRun.status.in_(ACTIVE))):
        raise Conflict("Der kører allerede en booking for opgaven", code="browser_run_active")
    run = BrowserRun(task_id=task.id, workspace_id=task.workspace_id, engine=engine, allowed_domains=domains,
                     goal={**validate_goal(goal), "start_url": booking_url[:1000]}, status="planned",
                     max_steps=s.browser_max_steps, max_seconds=s.browser_max_seconds)
    db.add(run)
    db.flush()
    price, cur = booking_price(db, task.workspace_id), ledger.currency(db, task.workspace_id)
    if ledger.balance(db, task.workspace_id) < price:
        raise Conflict(f"Fyld op: en booking på hjemmesiden reserverer {markets.fmt(price, cur)} på din opkaldssaldo",
                       code="insufficient_balance", extra={"needed_minor": price, "currency": cur})
    ledger.reserve(db, task.workspace_id, f"browser:{run.id}", price, task_id=task.id,
                   text="Booking på hjemmeside – reserveret")
    task.usage_text = f"{markets.fmt(price, cur)} reserveret"
    task.status, task.next_step, task.who = "in_progress", "Booker online – intet bliver bekræftet uden dit ja", "Dialogbot"
    privat_service.event(db, task, "Dialogbot går i gang med at finde en tid på virksomhedens bookingside")
    privat_service.touch(task)
    outbox.enqueue(db, event_type=EVENT_RUN, dedupe_key=f"browser:{run.id}:start", payload={"run_id": str(run.id)},
                   workspace_id=task.workspace_id)
    return run


# --------------------------------------------------------------------------- reading

def _own_task(db: OrmSession, ctx, task_id: uuid.UUID, *, lock: bool = False) -> PrivateTask:
    task, m = sharing.access(db, task_id, ctx.user_id, lock=lock)
    if m.role != "owner":
        raise NotFound("Opgaven findes ikke")
    return task


def latest_run(db: OrmSession, ctx, task_id: uuid.UUID, *, lock: bool = False) -> tuple[PrivateTask, BrowserRun]:
    """404 for a task that is not the caller's (another workspace's id looks like a missing one) or without a run."""
    task = _own_task(db, ctx, task_id, lock=lock)
    q = (select(BrowserRun).where(BrowserRun.task_id == task.id, BrowserRun.workspace_id == task.workspace_id)
         .order_by(BrowserRun.created_at.desc(), BrowserRun.id).limit(1))
    run = db.scalar(q.with_for_update() if lock else q)
    if run is None:
        raise NotFound("Der er ingen booking på hjemmeside for opgaven")
    return task, run


_REF = re.compile(r"\be\d{1,5}\b ?")
_TYPED = re.compile(r"= .*$")


def public_step(st: dict) -> dict:
    """A step without internal selectors/refs and without what was typed into fields."""
    arg = st.get("arg") or ""
    if st.get("tool") in ("click", "type", "select"):
        arg = _REF.sub("", arg).strip()
        if st.get("tool") in ("type", "select"):
            arg = _TYPED.sub("= …", arg)
    shot = st.get("screenshot_url")
    return {"n": st.get("n"), "tool": st.get("tool"), "arg": arg[:200], "result": (st.get("result") or "")[:200],
            "at": st.get("at"), "screenshot_url": storage.sign(shot) if shot else None}


def approval_expires_at(run: BrowserRun) -> datetime | None:
    if run.status != "awaiting_approval" or run.awaiting_since is None:
        return None
    return run.awaiting_since + timedelta(seconds=get_settings().browser_approval_ttl_seconds)


def run_out(run: BrowserRun) -> dict:
    ev = []
    for e in run.evidence_urls or []:
        url = storage.sign(e["key"]) if e.get("key") else None
        if url:
            ev.append({"kind": e.get("kind"), "name": e.get("name"), "url": url})
    iso = lambda d: d.isoformat() if d else None  # noqa: E731
    exp = approval_expires_at(run)
    res = run.result or {}
    return {"id": str(run.id), "task_id": str(run.task_id), "engine": run.engine, "mode": run.mode, "status": run.status,
            "goal": {k: v for k, v in (run.goal or {}).items() if k != "start_url"},
            "before_after": run.before_after, "steps": [public_step(x) for x in (run.steps or [])],
            "evidence": ev, "result": {k: v for k, v in res.items() if not k.startswith("_")} or None,
            "error_code": run.error_code, "max_steps": run.max_steps, "max_seconds": run.max_seconds,
            "started_at": iso(run.started_at), "awaiting_since": iso(run.awaiting_since),
            "approval_expires_at": iso(exp), "approved_at": iso(run.approved_at), "finished_at": iso(run.finished_at),
            "created_at": iso(run.created_at)}


# --------------------------------------------------------------------------- compare-and-set transitions

def cas(db: OrmSession, run_id: uuid.UUID, from_: tuple[str, ...] | str, to: str, **fields) -> bool:
    """Move a run from one of `from_` to `to` atomically. False when somebody else got there first."""
    src = (from_,) if isinstance(from_, str) else tuple(from_)
    res = db.execute(update(BrowserRun).where(BrowserRun.id == run_id, BrowserRun.status.in_(src))
                     .values(status=to, **fields))
    db.flush()
    db.expire_all()
    return res.rowcount == 1


def _settle_balance(db: OrmSession, run: BrowserRun, task: PrivateTask, *, spent: bool) -> None:
    """The reservation becomes the price (capture) or comes back (release). Idempotent per run (unique source_ref)."""
    if spent:
        held = -(ledger.amount_of(db, f"browser:{run.id}:reserve") or 0)
        if ledger.settle(db, run.workspace_id, f"browser:{run.id}", held, task_id=task.id,
                         text="Booking på hjemmeside") is not None:
            task.usage_text = f"{markets.fmt(held, ledger.currency(db, run.workspace_id))} · booking på hjemmeside"
    else:
        ledger.settle(db, run.workspace_id, f"browser:{run.id}", None, task_id=task.id,
                      text="Booking på hjemmeside ikke gennemført – reservation frigivet")
        task.usage_text = "Intet forbrug"


def _owner_message(db: OrmSession, run: BrowserRun, task: PrivateTask, *, kind: str = "text", text: str,
                   **kw) -> PrivateMessage:
    return privat_service.add_message(db, run.workspace_id, kind=kind, text=text, task_id=task.id, **kw)


def _business(run: BrowserRun, task: PrivateTask) -> str:
    return (run.goal or {}).get("business_name") or task.title


def format_proposal(ba: dict | None) -> str:
    ba = ba or {}
    if not ba.get("service") and ba.get("text"):  # an LLM run: the page's own words, not a parsed summary
        return str(ba["text"])[:200]
    staff = ba.get("staff")
    parts = [ba.get("service"), f"{ba.get('date')} kl. {ba.get('time')}" if ba.get("date") and ba.get("time") else None,
             f"hos {staff}" if staff and not re.search(r"pr[æe]ference", staff, re.I) else None, ba.get("price")]
    return ", ".join(p for p in parts if p)[:200] or "Se detaljerne"


def to_awaiting(db: OrmSession, run: BrowserRun, before_after: dict, *, changed: bool = False) -> None:
    """The form is filled in, nothing is confirmed: ask the user. `changed` = a replay found a different slot than the
    one the user approved, so the old yes does not count and a new draft is shown."""
    task = db.get(PrivateTask, run.task_id)
    run.before_after = before_after
    run.awaiting_since = _now()
    run.approved_at = None
    task.status, task.next_step, task.who = "awaiting_user", "Godkend bookingen", "Dig"
    biz = _business(run, task)
    why = ("Siden har ændret sig, siden du sagde ja, så jeg har ikke booket noget. " if changed else "")
    privat_service.event(db, task, "Bookingen er udfyldt og venter på dit ja – intet er bekræftet" if not changed else
                         "Tiden havde ændret sig – nyt forslag venter på dit ja")
    privat_service.touch(task)
    _owner_message(db, run, task, kind="booking_proposal", before=(run.goal or {}).get("current") or "Ingen tid endnu",
                   after=format_proposal(before_after), about_task_id=task.id,
                   text=f"{why}Jeg er klar til at booke hos {biz}. Intet er booket endnu. Godkend, hvis det skal "
                        f"gennemføres, eller afvis. Forslaget gælder i {get_settings().browser_approval_ttl_seconds // 60} "
                        "minutter, derefter prøver jeg igen, når du godkender.",
                   options=[{"id": "approve", "label": "Godkend", "sub": "Book tiden", "action": "browser_approve"},
                            {"id": "decline", "label": "Afvis", "sub": "Gør ingenting", "action": "browser_decline"}])
    privat_service.notify_owner(db, task, subject=f"Godkend booking hos {biz}",
                                text=f"Jeg har udfyldt bookingen: {format_proposal(before_after)}. Intet er booket, før du godkender.",
                                dedupe=f"browser:{run.id}:awaiting:{int(run.awaiting_since.timestamp())}")


def enter_awaiting(db: OrmSession, run_id: uuid.UUID, before_after: dict, *, changed: bool = False) -> bool:
    """Worker: running -> awaiting_approval with the proposal and the draft message. False if the run was moved meanwhile."""
    if not cas(db, run_id, "running", "awaiting_approval"):
        return False
    to_awaiting(db, db.get(BrowserRun, run_id), before_after, changed=changed)
    return True


def _answer_draft(db: OrmSession, task: PrivateTask, option_id: str) -> None:
    for m in db.scalars(select(PrivateMessage).where(PrivateMessage.task_id == task.id, PrivateMessage.kind == "booking_proposal",
                                                     PrivateMessage.answered_option_id.is_(None))):
        m.answered_option_id = option_id


def finish_done(db: OrmSession, run: BrowserRun, result: dict) -> None:
    task = db.get(PrivateTask, run.task_id)
    s = result.get("summary") or {}
    ba = run.before_after or {}
    if not ba.get("service") and ba.get("text"):
        confirmed = str(ba["text"])[:300]
    else:
        when = f"{s.get('date') or ba.get('date')} kl. {s.get('time') or ba.get('time')}"
        confirmed = f"{s.get('service') or ba.get('service') or 'Tid'}, {when}"[:300]
    price = s.get("price") or ba.get("price")
    run.status, run.finished_at, run.error_code, run.result = "done", _now(), None, result
    task.status, task.next_step, task.who = "done", confirmed, f"{_business(run, task)} har bekræftet"
    _settle_balance(db, run, task, spent=True)
    privat_service.event(db, task, f"Booket: {confirmed}" + (f" · pris {price}" if price else "")
                         + (f" · bookingnr. {result['reference']}" if result.get("reference") else ""))
    ev = run.evidence_urls or []
    if ev:  # the links themselves are signed and short-lived, so the event only says what exists (see the run page)
        kinds = {"receipt_pdf": "kvittering som PDF", "video": "video", "screenshot": "billeder"}
        privat_service.event(db, task, "Bevis gemt: " + ", ".join(kinds[k] for k in kinds if any(e.get("kind") == k for e in ev)))
    call = privat_service.latest_call(db, task.id)
    if call is not None:
        call.confirmed_text = confirmed
        if price:
            call.business_price_text = str(price)[:300]
    privat_service.touch(task)
    text = f"Booket hos {_business(run, task)}: {confirmed}." + (f" Pris: {price}." if price else "") \
        + (f" Bookingnummer: {result['reference']}." if result.get("reference") else "")
    from app.modules.privat import appointments
    from app.modules.privat import rules as privat_rules

    appt = appointments.from_browser(db, run, task, service=s.get("service") or ba.get("service"),
                                     date_text=s.get("date") or ba.get("date"), time_text=s.get("time") or ba.get("time"),
                                     business=_business(run, task), price=price, agreed_at=_now())
    if appt is not None:
        privat_service.event(db, task, f"Aftale gemt: {privat_rules.when_text(appt.starts_at)}")
        if appointments.lands_in_calendar(db, task.workspace_id):
            text += " Tiden er lagt i din kalender."
    _owner_message(db, run, task, text=text)
    privat_service.notify_owner(db, task, subject=f"Booket hos {_business(run, task)}", text=text,
                                dedupe=f"browser:{run.id}:done")


def finish_failed(db: OrmSession, run: BrowserRun, error_code: str, *, details: dict | None = None) -> None:
    task = db.get(PrivateTask, run.task_id)
    run.status, run.finished_at, run.error_code = "failed", _now(), error_code[:40]
    if details:
        run.result = {**(run.result or {}), "error_details": details}
    biz = _business(run, task)
    _settle_balance(db, run, task, spent=error_code in SPENT_ERROR_CODES)
    if error_code == "declined":
        task.status, task.next_step, task.who = "declined", "Afvist – der er ikke booket", "Dig"
        privat_service.event(db, task, "Du afviste bookingen. Intet er booket")
        _owner_message(db, run, task, text="Okay, jeg har ikke booket noget.")
    elif error_code == "unexpected_commit":
        url = (details or {}).get("url") or ""
        task.status, task.next_step, task.who = "awaiting_user", "Tjek og aflys bookingen, hvis du ikke ønsker den", "Dig"
        text = (f"Bookingen hos {biz} kan være gennemført, selvom du ikke har godkendt den. Siden ændrede sig til en "
                f"kvittering efter et klik, som ikke så ud som en bekræftelse. Side: {url}. Bookingen kan være gennemført – "
                "ring eller skriv til virksomheden for at aflyse, hvis du ikke ønsker den.")
        privat_service.event(db, task, "Mulig booking uden godkendelse – tjek hos virksomheden og aflys, hvis du ikke ønsker den")
        _owner_message(db, run, task, text=text)
        privat_service.notify_owner(db, task, subject=f"Tjek din booking hos {biz}", text=text,
                                    dedupe=f"browser:{run.id}:unexpected_commit")
    elif error_code == "commit_unconfirmed":
        # The confirming click WAS made, but the run did not end with a receipt we could read. Never say «intet er booket».
        task.status, task.next_step, task.who = "awaiting_user", "Tjek hos virksomheden, om tiden er booket", "Dig"
        text = (f"Jeg trykkede på bekræft hos {biz}, men kunne ikke se en kvittering bagefter. Bookingen kan være "
                "gennemført – tjek hos virksomheden, og ring eller skriv til dem, hvis du ikke ønsker tiden.")
        privat_service.event(db, task, "Bekræft blev trykket, men kvitteringen kunne ikke læses – tjek hos virksomheden")
        _owner_message(db, run, task, text=text)
        privat_service.notify_owner(db, task, subject=f"Tjek din booking hos {biz}", text=text,
                                    dedupe=f"browser:{run.id}:commit_unconfirmed")
    else:
        task.status, task.next_step, task.who = "awaiting_user", "Booking på hjemmesiden lykkedes ikke", "Dig"
        privat_service.event(db, task, f"Booking på hjemmesiden stoppede ({error_code}). Intet er bekræftet")
        _owner_message(db, run, task, text=f"Jeg kunne ikke gennemføre bookingen hos {biz} på hjemmesiden. Intet er booket.")
    privat_service.touch(task)
    _answer_draft(db, task, "decline" if error_code == "declined" else "expired")


def calls_pending_usage(db: OrmSession, task: PrivateTask) -> str:
    from app.modules.privat import calls

    return calls.pending_usage_text(db, task.workspace_id)


def finish_fallback(db: OrmSession, run: BrowserRun, error_code: str, found: dict | None = None) -> None:
    """The browser could not do it (CAPTCHA, login, budget, no free time ...): hand over to the phone track. The task's
    call part is prepared with what was found (phone_fallback.apply); the user approves the call like any other call."""
    from app.modules.browser import phone_fallback

    task = db.get(PrivateTask, run.task_id)
    run.status, run.finished_at, run.error_code = "fallback_phone", _now(), error_code[:40]
    run.result = {**(run.result or {}), "found": found or {}}
    phone_fallback.apply(db, run, task, found, error_code)
    _settle_balance(db, run, task, spent=False)
    task.usage_text = calls_pending_usage(db, task)
    switched = error_code == "user_switched"
    privat_service.event(db, task, "Du bad om et opkald i stedet for en booking på hjemmesiden" if switched else
                         f"Booking på hjemmesiden kunne ikke gennemføres ({error_code}). Intet er booket")
    privat_service.touch(task)
    biz = _business(run, task)
    text = (f"Okay, jeg ringer til {biz} i stedet. Her er forslaget til opkaldet; der bliver ikke ringet, før du godkender."
            if switched else
            f"Jeg kunne ikke booke hos {biz} på hjemmesiden – {phone_fallback.reason_text(error_code)}. Intet er booket. "
            "Her er et forslag til et opkald i stedet; der bliver ikke ringet, før du godkender.")
    _owner_message(db, run, task, kind="call_proposal", text=text)
    _answer_draft(db, task, "expired")


# --------------------------------------------------------------------------- the user's answer

def approve(db: OrmSession, ctx, task_id: uuid.UUID) -> BrowserRun:
    """Idempotent: a repeated yes changes nothing. The yes covers exactly the before→after the user was shown."""
    task, run = latest_run(db, ctx, task_id, lock=True)
    if run.status in ("approved", "done"):
        return run
    if run.status != "awaiting_approval":
        raise Conflict("Bookingen venter ikke på dit svar", code="browser_run_not_awaiting")
    if run.awaiting_since and _now() - run.awaiting_since > APPROVAL_MAX_AGE:
        finish_failed(db, run, "approval_expired")
        db.commit()
        raise Conflict("Forslaget er for gammelt. Bed om en ny booking", code="approval_expired")
    run.status, run.approved_at = "approved", _now()
    privat_service.event(db, task, "Du godkendte bookingen")
    privat_service.touch(task)
    task.status, task.next_step, task.who = "in_progress", "Gennemfører bookingen", "Dialogbot"
    _answer_draft(db, task, "approve")
    outbox.enqueue(db, event_type=EVENT_DECISION, dedupe_key=f"browser:{run.id}:approve:{int(run.approved_at.timestamp() * 1000)}",
                   payload={"run_id": str(run.id), "decision": "approve"}, workspace_id=run.workspace_id)
    return run


def decline(db: OrmSession, ctx, task_id: uuid.UUID) -> BrowserRun:
    task, run = latest_run(db, ctx, task_id, lock=True)
    if run.status == "failed" and run.error_code == "declined":
        return run
    if run.status not in ("awaiting_approval", "approved"):
        raise Conflict("Bookingen venter ikke på dit svar", code="browser_run_not_awaiting")
    finish_failed(db, run, "declined")
    outbox.enqueue(db, event_type=EVENT_DECISION, dedupe_key=f"browser:{run.id}:decline",
                   payload={"run_id": str(run.id), "decision": "decline"}, workspace_id=run.workspace_id)
    return run


def cancel_for_phone(db: OrmSession, ctx, task_id: uuid.UUID) -> BrowserRun:
    """«Ring i stedet»: end an unfinished browser run and prepare the call. The worker lets go of the browser by itself (it
    sees the status change). Refused once the confirming click may be made: a booking in flight cannot be called back."""
    task, run = latest_run(db, ctx, task_id, lock=True)
    if run.status == "fallback_phone" and run.error_code == "user_switched":
        return run
    if run.status in FINAL:
        raise Conflict("Bookingen er allerede afsluttet", code="browser_run_finished")
    if (run.result or {}).get("_confirming"):
        raise Conflict("Bookingen er allerede ved at blive gennemført og kan ikke fortrydes her", code="browser_run_confirming")
    finish_fallback(db, run, "user_switched", (run.result or {}).get("found") or {})
    return run


def active_run_for(db: OrmSession, task_id: uuid.UUID) -> BrowserRun | None:
    return db.scalar(select(BrowserRun).where(BrowserRun.task_id == task_id, BrowserRun.status.in_(ACTIVE))
                     .order_by(BrowserRun.created_at.desc()).limit(1))
