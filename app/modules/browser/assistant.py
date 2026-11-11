"""The Privat assistant's booking tools (add-on «Ring for mig»): find_business, start_booking, switch_to_phone.

The model says WHAT the user wants (business, service, time windows, and only what the user explicitly said about «ring» or
«skriv»). The code picks the track (routing.py), says which track it took, and never starts a browser run unless the user asked
for a concrete booking (service + a dated time window). The only contact details a run ever gets are the user's own name and
verified mobile number from the profile. Nothing here dials a number or confirms anything: the phone track is the normal call
proposal, the browser track ends at the user's Godkend.
"""
from __future__ import annotations

import json
import uuid
from datetime import date

import structlog
from sqlalchemy import select

from app.config import get_settings
from app.core.errors import ApiError, Conflict, NotFound
from app.models import ExternalBusinessContact, PrivateCall, PrivateMessage, PrivateTask
from app.modules.browser import lookup, profiles, routing, service
from app.modules.privat import ledger, places, rules, sharing

log = structlog.get_logger("dialogbot.browser")
MAX_WINDOWS = 5


def clean_windows(raw) -> list[dict]:
    """Dated time windows the user gave: [{date: 'YYYY-MM-DD', from?: 'HH:MM', to?: 'HH:MM'}]. Past dates and junk are dropped."""
    out = []
    today = rules.local().date()
    for w in raw if isinstance(raw, list) else []:
        if not isinstance(w, dict):
            continue
        try:
            d = date.fromisoformat(str(w.get("date")))
        except ValueError:
            continue
        if d < today:
            continue
        item = {"date": d.isoformat()}
        for k in ("from", "to"):
            v = str(w.get(k) or "")
            if len(v) == 5 and v[2] == ":" and v[:2].isdigit() and v[3:].isdigit() and int(v[:2]) < 24 and int(v[3:]) < 60:
                item[k] = v
        out.append(item)
    return out[:MAX_WINDOWS]


def window_text(windows: list[dict]) -> str:
    if not windows:
        return ""
    w = windows[0]
    d = date.fromisoformat(w["date"])
    t = f" kl. {w['from']}–{w['to']}" if w.get("from") and w.get("to") else ""
    return f"{rules.WEEKDAYS[d.weekday()]} {d.day}/{d.month}{t}"


def tool_find_business(turn, a: dict) -> str:
    """Look the business up (CVR + Google Places, remembered). Returns facts for the model; decides nothing."""
    name = str(a.get("name") or "").strip()[:200]
    city = str(a.get("city") or "").strip()[:100] or None
    if not name:
        turn.say("text", "Hvad hedder virksomheden – og i hvilken by?")
        return "Mangler virksomhedens navn. Opfind det ikke."
    try:
        b = lookup.find_business(turn.db, turn.ctx, name, city)
    except ApiError as e:
        log.warning("browser.find_business_failed", code=e.code)
        b = None
    if b is None:
        turn.say("text", f"Jeg kunne ikke finde «{name}»{' i ' + city if city else ''}. Skriv navn, by og gerne nummeret, så "
                         "laver jeg et forslag til et opkald.")
        return "Ingen virksomhed fundet. Opfind hverken navn, nummer eller hjemmeside."
    return json.dumps({"business_id": b.id, "navn": b.name, "adresse": b.address, "by": b.city,
                       "telefon": rules.phone_display(b.phone_e164) if b.phone_e164 else None,
                       "hjemmeside_fundet": bool(b.website), "cvr": b.cvr,
                       "bemærkning": "Kald start_booking med business_id. Du vælger ikke selv spor."},
                      ensure_ascii=False)


def _facts(db, ctx, row: ExternalBusinessContact, *, user_said, intent, concrete) -> tuple[routing.Facts, str, str | None]:
    engine, booking_url = "unknown", None
    if row.website:
        try:
            prof = profiles.get_or_detect(db, website=row.website, cvr=row.cvr, phone=row.phone_e164)
            engine, booking_url = prof.engine, prof.booking_url
            row.booking_profile_id = prof.id
        except Exception as e:  # noqa: BLE001 – a site we cannot read is simply «unknown»: the phone track
            log.warning("browser.engine_detect_failed", error=type(e).__name__)
    p, u = ctx.profile, ctx.user
    facts = routing.Facts(
        user_said=user_said, intent=intent, website=row.website, engine=engine, booking_url=booking_url,
        has_name_and_phone=bool((u.display_name or "").strip() and p.phone_e164 and p.phone_verified_at),
        concrete=concrete, worker_enabled=get_settings().browser_worker_enabled,
        has_balance=ledger.balance(db, ctx.ws_id) >= service.booking_price(db, ctx.ws_id))
    return facts, engine, booking_url


def tool_start_booking(turn, a: dict) -> str:
    db, ctx = turn.db, turn.ctx
    try:
        row = db.get(ExternalBusinessContact, uuid.UUID(str(a.get("business_id"))))
    except (ValueError, TypeError):
        row = None
    if row is None:
        turn.say("text", "Hvilken virksomhed mener du? Skriv navnet og byen.")
        return "Ukendt business_id. Kald find_business først; opfind intet."
    intent = a.get("intent") if a.get("intent") in service.INTENTS else "book"
    said = a.get("user_said_track") if a.get("user_said_track") in ("ring", "skriv") else None
    svc = " ".join(str(a.get("service") or "").split())[:200]
    windows = clean_windows(a.get("preferred_windows"))
    concrete = len(svc) >= 2 and bool(windows)
    facts, engine, booking_url = _facts(db, ctx, row, user_said=said, intent=intent, concrete=concrete)
    d = routing.decide(facts)
    if d.track == "ask":
        turn.say("text", "Hvilken ydelse skal jeg booke hos " + row.name + ", og hvornår kan du? Skriv fx «herreklip tirsdag "
                         "formiddag». Så kan jeg prøve at booke online og vise dig et forslag, du kan godkende.")
        return "Mangler ydelse og tidsrum. Spørg brugeren; start intet, og opfind intet."
    if d.track == "browser":
        return _browser(turn, row, svc, windows, engine, booking_url)
    return _phone(turn, row, d, svc, windows)


def _phone(turn, row: ExternalBusinessContact, d: routing.Decision, svc: str, windows: list[dict]) -> str:
    from app.modules.privat import chat

    when = window_text(windows)
    if d.reason == "user_said_ring":
        say = f"Jeg ringer til {row.name} i åbningstiden, når du har godkendt opkaldet."
    elif d.say_blocker:
        say = f"Jeg ringer til {row.name} i åbningstiden, når du har godkendt opkaldet – {d.say_blocker}."
    else:
        say = f"Jeg ringer til {row.name} i åbningstiden, når du har godkendt opkaldet."
    turn.say("text", say)
    nxt = None
    if row.opening_hours and places.is_open(row.opening_hours, rules.now()) is False:
        nxt = places.next_call_time(row.opening_hours, rules.now())
    purpose = f"Book {svc}" if svc else "Aftal en tid"
    chat._propose(turn, name=row.name, phone=row.phone_e164, source="google" if row.place_id else "cvr",
                  address=row.address or "", place_id=row.place_id, next_open_at=nxt.isoformat() if nxt else None,
                  data={"purpose": purpose, "window": when})
    return f"Spor: telefon (regel {d.rule}, {d.reason}). Forslaget er oprettet; der er IKKE ringet."


def _browser(turn, row: ExternalBusinessContact, svc: str, windows: list[dict], engine: str, booking_url: str | None) -> str:
    from app.modules.privat import addons

    db, ctx = turn.db, turn.ctx
    addons.require(db, ctx.ws_id, "ring-for-mig")
    host_url = booking_url if booking_url and booking_url.startswith("http") else f"https://{booking_url}"
    domains = _allowed_domains(row.website, host_url)
    when = window_text(windows)
    try:
        with db.begin_nested():  # if the run cannot be planned, nothing of it stays and the phone track takes over
            task = _plan_browser(db, ctx, row, svc, windows, when, domains, engine, host_url)
    except ApiError as e:
        log.warning("browser.start_failed", code=e.code)
        return _phone(turn, row, routing.Decision("phone", 4, "no_balance" if e.code == "insufficient_balance" else "engine_unknown"),
                      svc, windows)
    turn.say("text", f"Jeg prøver at booke online hos {row.name} – du får et forslag at godkende. Intet bliver booket, før du "
                     "siger ja. Du kan altid skrive «ring i stedet».", task_id=task.id)
    return f"Spor: browser. Booking startet (opgave {task.id}). Intet er bekræftet."


def _plan_browser(db, ctx, row, svc, windows, when, domains, engine, host_url) -> PrivateTask:
    task = PrivateTask(workspace_id=ctx.ws_id, kind="call", title=f"Book {svc.lower()} hos {row.name}"[:300], status="in_progress",
                       next_step="Booker online", who="Dialogbot", paid_by="call", usage_text="", created_at=rules.now(),
                       updated_at=rules.now())
    db.add(task)
    db.flush()
    sharing.add_owner(db, task, ctx.user_id)
    # The call part exists from the start (status «proposed», hidden while the task runs): if the browser cannot do it, this
    # is the proposal the user sees, already filled with what the browser found.
    db.add(PrivateCall(workspace_id=ctx.ws_id, task_id=task.id, status="proposed", created_at=rules.now(),
                       business_name=row.name[:200], business_address=row.address or "", business_phone_e164=row.phone_e164,
                       phone_source="google" if row.place_id else "cvr", place_id=row.place_id, purpose=f"Book {svc}"[:2000],
                       window=when[:200], may_ask=f"Om de kan {svc.lower()} {when}, og hvad det koster".strip()))
    goal = {"intent": "book", "service": svc, "preferred_windows": windows, "business_name": row.name,
            "business_phone": row.phone_e164, "business_address": row.address or "", "place_id": row.place_id,
            "phone_source": "google" if row.place_id else "cvr",
            # ONLY what the user gave Dialogbot for this purpose: their name and verified mobile. Never the e-mail.
            "contact": {"name": ctx.user.display_name.strip(), "phone": ctx.profile.phone_e164}}
    service.start_run(db, task, goal=goal, allowed_domains=domains, engine=engine, booking_url=host_url)
    return task


def _allowed_domains(website: str | None, booking_url: str) -> list[str]:
    from browser_worker import netguard

    out = []
    for u in (booking_url, website):
        if u:
            try:
                h = netguard.normalize_domain(u)
            except ValueError:
                continue
            if h not in out:
                out.append(h)
    return out


def tool_switch_to_phone(turn, a: dict) -> str:
    """«Ring i stedet»: end the running browser booking and prepare the call."""
    db, ctx = turn.db, turn.ctx
    tid = a.get("task_id")
    task = None
    try:
        if tid:
            task, _ = sharing.access(db, uuid.UUID(str(tid)), ctx.user_id)
    except (ValueError, NotFound):
        task = None
    if task is None:
        task = (turn.about if turn.about is not None and service.active_run_for(db, turn.about.id) else None) or next(
            (t for t in db.scalars(select(PrivateTask).where(PrivateTask.workspace_id == ctx.ws_id, PrivateTask.status == "in_progress")
                                   .order_by(PrivateTask.updated_at.desc())) if service.active_run_for(db, t.id)), None)
    if task is None or service.active_run_for(db, task.id) is None:
        turn.say("text", "Der kører ingen booking på en hjemmeside lige nu. Skriv, hvem jeg skal ringe til.")
        return "Ingen aktiv browser-booking. Brug propose_call, hvis brugeren vil have et opkald."
    try:
        service.cancel_for_phone(db, ctx, task.id)
    except Conflict as e:
        turn.say("text", f"{e.message}. Tjek hos virksomheden, om tiden er booket.")
        return f"Kan ikke annulleres: {e.message}"
    msg = db.scalar(select(PrivateMessage).where(PrivateMessage.task_id == task.id, PrivateMessage.kind == "call_proposal")
                    .order_by(PrivateMessage.created_at.desc()).limit(1))
    if msg is not None:
        turn.out.append(msg)  # the card the service made is part of this turn's answer
    return "Browser-bookingen er stoppet; forslaget til opkaldet er oprettet. Der er IKKE ringet."
