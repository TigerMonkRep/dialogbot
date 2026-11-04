"""Tasks, the monthly quota, reminders and the JSON shapes of docs/privat-api.md.

Rules:
- With the trial or a plan (subscriptions.entitlements → entitled) lists and reminders are unlimited (paid_by 'plan').
- Otherwise 10 new digital tasks (lists, reminders) per calendar month, Europe/Copenhagen. Editing, ticking, reading
  and clarifying are free; a shared list is ONE task for its owner, whatever its members do.
- Task #11 in a month is saved as a draft until activated with 1 credit (spend:<task_id>) or a sponsor spot (max 2 a
  day, sponsor:<task_id>). A draft reminder never fires.
- A reminder is one outbox event (privat.reminder) due at remind_at; moving it cancels the old event and creates
  exactly one new one (dedupe key includes reminder_version).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta

from sqlalchemy import func, or_, select, update
from sqlalchemy.orm import Session as OrmSession

from app.core.errors import Conflict, Forbidden, NotFound, ValidationFailed
from app.core.outbox import enqueue
from app.models import (
    OutboxEvent,
    PrivateCall,
    PrivateMessage,
    PrivateProfile,
    PrivateTask,
    PrivateTaskEvent,
    PrivateTaskItem,
    PrivateTaskMember,
    User,
)
from app.modules.privat import ledger, rules, sharing

ACTIVE_STATUSES = ("planned", "in_progress", "awaiting_business")
LIST_TYPES = ("shopping", "wishlist", "todo")


def event(db: OrmSession, task: PrivateTask, text: str) -> None:
    db.flush()
    at = rules.now()
    last = db.scalar(select(func.max(PrivateTaskEvent.at)).where(PrivateTaskEvent.task_id == task.id))
    if last is not None and last >= at:  # strict order, also with a frozen test clock
        at = last + timedelta(microseconds=1)
    db.add(PrivateTaskEvent(task_id=task.id, workspace_id=task.workspace_id, text=text[:2000], at=at))


def touch(task: PrivateTask) -> None:
    task.updated_at = rules.now()


# --------------------------------------------------------------------------- quota and balance

def free_used(db: OrmSession, ws_id: uuid.UUID) -> int:
    return db.scalar(select(func.count()).select_from(PrivateTask).where(
        PrivateTask.workspace_id == ws_id, PrivateTask.paid_by == "free",
        PrivateTask.free_month == rules.month_key())) or 0


def balance_out(db: OrmSession, ctx) -> dict:
    from app.modules.privat import subscriptions

    p = ctx.profile
    ent = subscriptions.entitlements(db, ctx.ws_id)
    return {"free_used": free_used(db, ctx.ws_id), "free_limit": rules.FREE_LIMIT,
            "credits": ledger.balance(db, ctx.ws_id), "reserved": ledger.reserved(db, ctx.ws_id),
            "sponsor_left_today": max(0, rules.SPONSOR_PER_DAY - ledger.sponsor_used_today(db, ctx.ws_id)),
            "phone_display": rules.phone_display(p.phone_e164) if p.phone_verified_at else None,
            "phone_verified": p.phone_verified_at is not None,
            # the subscription (docs/privat-api.md): trial counts as Plus; credits are "ekstra opkald" beyond the quota
            "plan": ent["plan"], "plan_status": ent["status"], "trial_days_left": ent["trial_days_left"],
            "calls_quota": ent["calls_quota"], "calls_used": ent["calls_used"], "calls_left": ent["calls_left"],
            "entitled": ent["entitled"]}


def _lock_profile(db: OrmSession, ws_id: uuid.UUID) -> PrivateProfile:
    """Serialises quota and credit decisions per account."""
    return db.scalar(select(PrivateProfile).where(PrivateProfile.workspace_id == ws_id).with_for_update())


# --------------------------------------------------------------------------- tasks

def create_digital(db: OrmSession, ctx, *, kind: str, title: str, items: list[str] | None = None,
                   list_type: str | None = None, remind_at: datetime | None = None) -> PrivateTask:
    """A new list or reminder: one of the month's free tasks, or a draft once they are used."""
    if kind not in ("list", "reminder"):
        raise ValidationFailed("Ukendt opgavetype")
    if list_type is not None and list_type not in LIST_TYPES:
        list_type = None
    title = (title or "").strip()[:300] or ("Liste" if kind == "list" else "Påmindelse")
    _lock_profile(db, ctx.ws_id)
    status = "in_progress" if kind == "list" else "planned"
    task = PrivateTask(workspace_id=ctx.ws_id, kind=kind, title=title, status=status, list_type=list_type,
                       who="Dig" if kind == "list" else "Assistenten minder dig", created_at=rules.now(),
                       updated_at=rules.now())
    if kind == "reminder":
        if remind_at is None:
            raise ValidationFailed("Hvornår skal jeg minde dig om det?", field_errors=[{"field": "remind_at"}])
        task.remind_at = task.due_at = remind_at
        task.next_step = "Påmindelse " + rules.lower_first(rules.when_text(remind_at))
    else:
        task.next_step = {"shopping": "Køb ind", "wishlist": "Del ønskelisten", "todo": "Gør punkterne færdige"}.get(
            list_type or "", "Kryds af, når det er klaret")
    from app.modules.privat import subscriptions

    ent = subscriptions.entitlements(db, ctx.ws_id)
    used = free_used(db, ctx.ws_id)
    if ent["entitled"]:
        # the trial and every plan include unlimited lists and reminders: never one of the month's free tasks
        task.paid_by = "plan"
        task.usage_text = "Med i prøveperioden" if ent["status"] == "trial" else f"Med i {subscriptions.plan_label(ent)}"
    elif used < rules.FREE_LIMIT:
        task.paid_by, task.free_month = "free", rules.month_key()
        task.usage_text = f"{used + 1} af {rules.FREE_LIMIT} gratis opgaver i {rules.month_name()}"
    else:
        task.pending_status, task.status, task.paid_by = status, "draft", "none"
        task.next_step, task.usage_text = "Vælg, hvordan opgaven skal betales", "Ikke betalt endnu"
    db.add(task)
    db.flush()
    sharing.add_owner(db, task, ctx.user_id)
    for i, text in enumerate(items or []):
        _add_item(db, task, text, ctx.user_id, position=i)
    event(db, task, "Oprettet i samtalen")
    if task.status != "draft" and kind == "reminder":
        schedule_reminder(db, task)
    db.flush()
    from app.modules.privat import referrals

    referrals.try_activate(db, ctx.user_id)
    return task


def _add_item(db: OrmSession, task: PrivateTask, text: str, user_id: uuid.UUID, *, position: int | None = None,
              note: str | None = None, link: str | None = None) -> PrivateTaskItem:
    text = (text or "").strip()[:300]
    if not text:
        raise ValidationFailed("Punktet må ikke være tomt", field_errors=[{"field": "text"}])
    if position is None:
        position = (db.scalar(select(func.max(PrivateTaskItem.position)).where(PrivateTaskItem.task_id == task.id))
                    or 0) + 1
    if link and not link.startswith(("https://", "http://")):
        raise ValidationFailed("Linket skal starte med https://", field_errors=[{"field": "link"}])
    it = PrivateTaskItem(task_id=task.id, workspace_id=task.workspace_id, text=text, position=position,
                         note=(note or "").strip()[:500] or None, link=(link or "").strip()[:1000] or None,
                         added_by_user_id=user_id)
    db.add(it)
    return it


def can_add(task: PrivateTask, m: PrivateTaskMember) -> None:
    if task.kind != "list":
        raise Conflict("Kun lister har punkter", code="not_a_list")
    if m.role == "viewer":
        raise Forbidden("Du kan kun se denne liste", code="read_only")
    if task.share_mode == "wishlist" and m.role != "owner":
        raise Forbidden("Kun ejeren tilføjer ønsker til en ønskeliste", code="owner_only")


def add_items(db: OrmSession, task: PrivateTask, m: PrivateTaskMember, texts: list[str], *, note: str | None = None,
              link: str | None = None) -> list[PrivateTaskItem]:
    """Free: editing an existing list never uses a task."""
    can_add(task, m)
    out = [_add_item(db, task, t, m.user_id, note=note if len(texts) == 1 else None,
                     link=link if len(texts) == 1 else None) for t in texts if (t or "").strip()]
    if not out:
        raise ValidationFailed("Skriv mindst ét punkt", field_errors=[{"field": "text"}])
    db.flush()
    who = db.get(User, m.user_id)
    prefix = "" if m.role == "owner" else f"{rules.first_name(who.display_name)}: "
    event(db, task, f"{prefix}Tilføjet: " + ", ".join(i.text.lower() for i in out) + " (gratis rettelse)")
    touch(task)
    return out


def toggle_item(db: OrmSession, task: PrivateTask, m: PrivateTaskMember, item_id: uuid.UUID) -> PrivateTaskItem:
    if m.role == "viewer":
        raise Forbidden("Du kan kun se denne liste", code="read_only")
    if task.share_mode == "wishlist" and m.role != "owner":
        raise Forbidden("Brug «Jeg køber den» på en ønskeliste", code="use_reserve")
    it = db.scalar(select(PrivateTaskItem).where(PrivateTaskItem.id == item_id, PrivateTaskItem.task_id == task.id)
                   .with_for_update())
    if it is None:
        raise NotFound("Punktet findes ikke")
    it.done = not it.done
    it.done_by_user_id = m.user_id if it.done else None
    touch(task)
    return it


def delete_item(db: OrmSession, task: PrivateTask, m: PrivateTaskMember, item_id: uuid.UUID) -> None:
    can_add(task, m)
    it = db.scalar(select(PrivateTaskItem).where(PrivateTaskItem.id == item_id, PrivateTaskItem.task_id == task.id))
    if it is None:
        raise NotFound("Punktet findes ikke")
    db.delete(it)
    touch(task)


def activate(db: OrmSession, ctx, task: PrivateTask, method: str) -> PrivateTask:
    """Draft → active, paid with 1 credit or a sponsor spot. Repeating it on an active task changes nothing."""
    if task.workspace_id != ctx.ws_id:
        raise NotFound("Opgaven findes ikke")
    _lock_profile(db, ctx.ws_id)
    db.refresh(task)
    if task.status != "draft":
        return task
    if method == "credit":
        if ledger.balance(db, ctx.ws_id) < 1:
            raise Conflict("Du har ingen credits", code="insufficient_credits")
        ledger.add(db, ctx.ws_id, kind="spend", amount=-1, source_ref=f"spend:{task.id}", task_id=task.id,
                   text="Ny opgave efter månedsgrænsen")
        task.paid_by, task.usage_text = "credit", "1 credit (efter månedens 10 gratis)"
    elif method == "sponsor":
        if ledger.sponsor_used_today(db, ctx.ws_id) >= rules.SPONSOR_PER_DAY:
            raise Conflict("Du har set dagens 2 sponsorindslag", code="sponsor_limit")
        ledger.add(db, ctx.ws_id, kind="sponsor", amount=0, source_ref=f"sponsor:{task.id}", task_id=task.id,
                   text="Sponsorindslag set – 1 ekstra opgave")
        task.paid_by, task.usage_text = "sponsor", "Sponsorindslag (+1 opgave)"
    else:
        raise ValidationFailed("Vælg credit eller sponsor", field_errors=[{"field": "method"}])
    task.status, task.pending_status = task.pending_status or "planned", None
    if task.kind == "reminder" and task.remind_at:
        task.next_step = "Påmindelse " + rules.lower_first(rules.when_text(task.remind_at))
        schedule_reminder(db, task)
    elif task.kind == "list":
        task.next_step = "Kryds af, når det er klaret"
    event(db, task, f"Fortsat: {task.usage_text}")
    touch(task)
    add_message(db, ctx.ws_id, kind="text", text="Opgaven er aktiv nu.", task_id=task.id)
    add_message(db, ctx.ws_id, kind="task", text=task.title, task_id=task.id)
    return task


# --------------------------------------------------------------------------- reminders

def _active_reminder_events(db: OrmSession, task_id: uuid.UUID):
    return select(OutboxEvent).where(OutboxEvent.event_type == "privat.reminder",
                                     OutboxEvent.dedupe_key.like(f"privat-reminder:{task_id}:%"),
                                     OutboxEvent.status == "queued")


def schedule_reminder(db: OrmSession, task: PrivateTask) -> None:
    owner = db.get(User, sharing.owner_member(db, task.id).user_id) if sharing.owner_member(db, task.id) else None
    if owner is None:
        db.flush()
        owner_id = db.scalar(select(PrivateProfile.user_id).where(PrivateProfile.workspace_id == task.workspace_id))
        owner = db.get(User, owner_id)
    ev = enqueue(db, event_type="privat.reminder", dedupe_key=f"privat-reminder:{task.id}:{task.reminder_version}",
                 workspace_id=task.workspace_id,
                 payload={"task_id": str(task.id), "version": task.reminder_version, "to_email": owner.email,
                          "remind_at": task.remind_at.isoformat()})
    ev.next_attempt_at = task.remind_at


def move_reminder(db: OrmSession, task: PrivateTask, when: datetime) -> tuple[str, str]:
    """Free. Cancels the queued event and creates exactly one new one. Returns (before, after) texts."""
    if task.kind != "reminder":
        raise Conflict("Kun påmindelser kan flyttes", code="not_a_reminder")
    if task.status in ("done", "declined"):
        raise Conflict("Påmindelsen er allerede sendt", code="reminder_done")
    before = rules.when_text(task.remind_at) if task.remind_at else ""
    for ev in db.scalars(_active_reminder_events(db, task.id).with_for_update()):
        ev.status, ev.last_error = "blocked", "cancelled: reminder moved"
    task.reminder_version += 1
    task.remind_at = task.due_at = when
    after = rules.when_text(when)
    if task.status != "draft":
        task.next_step = "Påmindelse " + rules.lower_first(after)
        schedule_reminder(db, task)
    event(db, task, f"Flyttet fra {rules.lower_first(before)} til {rules.lower_first(after)}")
    touch(task)
    return before, after


def handle_reminder(db: OrmSession, ev: OutboxEvent) -> None:
    """Worker handler (privat.reminder): e-mail now. Push notifications are a later step: see push_hook."""
    from app.modules.integrations import email_templates as tpl
    from app.worker.runner import _send_mail

    task = db.get(PrivateTask, uuid.UUID(ev.payload["task_id"]))
    if task is None or task.kind != "reminder" or task.status != "planned" \
            or task.reminder_version != ev.payload.get("version"):
        return  # moved, cancelled or already sent: nothing to do
    when = rules.when_text(task.remind_at) if task.remind_at else ""
    mail = tpl.Email(subject=f"Påmindelse: {task.title}", heading=task.title,
                     paragraphs=[f"Du bad mig minde dig om det {rules.lower_first(when)}."],
                     footer_reason="Du får denne e-mail, fordi du bad Dialogbot om en påmindelse.")
    _send_mail(db, ev, mail)
    push_hook(db, task, title="Påmindelse", body=task.title)
    task.status, task.next_step, task.who = "done", "Klaret", "Dig"
    event(db, task, "Påmindelse sendt")
    touch(task)


def push_hook(db: OrmSession, task: PrivateTask, *, title: str, body: str) -> None:
    """Hook for push notifications (app/PWA), not built yet. Every user notification passes here, so adding push is
    one function: look up the user's push subscriptions and send. E-mail is the channel today."""
    return None


def notify_owner(db: OrmSession, task: PrivateTask, *, subject: str, text: str, dedupe: str) -> None:
    """Tell the task's owner by e-mail (and later push) – a service message about their own task, never marketing."""
    from app.config import get_settings
    from app.modules.integrations import email_templates as tpl

    owner_id = db.scalar(select(PrivateProfile.user_id).where(PrivateProfile.workspace_id == task.workspace_id))
    owner = db.get(User, owner_id)
    if owner is None:
        return
    mail = tpl.Email(subject=subject, heading=task.title, paragraphs=[text], button_label="Åbn opgaven",
                     button_url=f"{get_settings().frontend_base_url.rstrip('/')}/privat/opgaver/{task.id}",
                     footer_reason="Du får denne e-mail, fordi Dialogbot arbejder på en opgave for dig.")
    enqueue(db, event_type="email.branded", dedupe_key=f"privat-notify:{dedupe}"[:200], workspace_id=task.workspace_id,
            payload={"to_email": owner.email, "email": tpl.to_payload(mail)})
    push_hook(db, task, title=subject, body=text)


# --------------------------------------------------------------------------- reading

def visible_tasks(db: OrmSession, user_id: uuid.UUID):
    return select(PrivateTask).join(PrivateTaskMember, PrivateTaskMember.task_id == PrivateTask.id).where(
        PrivateTaskMember.user_id == user_id)


def list_tasks(db: OrmSession, ctx, *, status: str | None = None, shared: bool | None = None) -> list[PrivateTask]:
    q = visible_tasks(db, ctx.user_id)
    if status:
        q = q.where(PrivateTask.status.in_([s.strip() for s in status.split(",") if s.strip()]))
    if shared:
        q = q.where(PrivateTask.share_mode.is_not(None))
    rows = list(db.scalars(q.order_by(PrivateTask.created_at.desc()).limit(500)))
    return [t for t in rows if not _paused_for(db, t, ctx.user_id)]


def _paused_for(db: OrmSession, t: PrivateTask, user_id: uuid.UUID) -> bool:
    return t.workspace_id is not None and t.share_mode is not None and sharing.sharing_paused(db, t) \
        and not sharing.is_owner_profile(db, t, user_id)


def day(db: OrmSession, ctx) -> dict:
    today = rules.local().date()
    awaiting, today_l, soon = [], [], []
    for t in reversed(list_tasks(db, ctx)):
        due = rules.local(t.due_at).date() if t.due_at else None
        if t.status in ("awaiting_user", "draft"):
            awaiting.append(t)
        elif t.status in ACTIVE_STATUSES and (due == today or (due is None and t.kind == "list")):
            today_l.append(t)
        elif (t.status in ACTIVE_STATUSES or (t.status == "done" and t.kind == "call")) and due and due > today:
            soon.append(t)
    soon.sort(key=lambda t: t.due_at)
    return {"awaiting": [task_out(db, t, ctx.user_id) for t in awaiting],
            "today": [task_out(db, t, ctx.user_id) for t in today_l],
            "soon": [task_out(db, t, ctx.user_id) for t in soon[:10]]}


def latest_call(db: OrmSession, task_id: uuid.UUID) -> PrivateCall | None:
    return db.scalar(select(PrivateCall).where(PrivateCall.task_id == task_id)
                     .order_by(PrivateCall.created_at.desc(), PrivateCall.id).limit(1))


def call_out(c: PrivateCall | None) -> dict | None:
    if c is None:
        return None
    return {"business_name": c.business_name, "address": c.business_address,
            "phone_display": rules.phone_display(c.business_phone_e164), "may_ask": c.may_ask,
            "may_agree": c.may_agree, "may_not": c.may_not, "window": c.window, "max_credits": rules.CALL_CREDITS,
            "share_phone": c.share_phone, "result": c.result, "confirmed_text": c.confirmed_text,
            "business_reply": c.business_reply, "business_price_text": c.business_price_text,
            "duration_seconds": c.duration_seconds, "status": c.status}


def _names(db: OrmSession, ids: set) -> dict:
    ids = {i for i in ids if i}
    if not ids:
        return {}
    return dict(db.execute(select(User.id, User.display_name).where(User.id.in_(ids))).all())


def items_out(db: OrmSession, task: PrivateTask, viewer_id: uuid.UUID, role: str) -> list[dict]:
    rows = list(db.scalars(select(PrivateTaskItem).where(PrivateTaskItem.task_id == task.id)
                           .order_by(PrivateTaskItem.position, PrivateTaskItem.created_at)))
    names = _names(db, {i.added_by_user_id for i in rows} | {i.done_by_user_id for i in rows})
    wishlist_owner = task.share_mode == "wishlist" and role == "owner"
    out = []
    for i in rows:
        x = {"id": str(i.id), "text": i.text, "done": i.done, "note": i.note, "link": i.link,
             "added_by_name": names.get(i.added_by_user_id) if task.share_mode else None,
             "done_by_name": names.get(i.done_by_user_id) if task.share_mode and i.done else None}
        if task.share_mode == "wishlist":
            # The owner never learns anything about reservations; others see that it is taken, not by whom.
            x["reserved"] = None if wishlist_owner else i.reserved_by_user_id is not None
            x["reserved_by_me"] = (not wishlist_owner) and i.reserved_by_user_id == viewer_id
        else:
            x["reserved"], x["reserved_by_me"] = None, False
        out.append(x)
    return out


def task_out(db: OrmSession, task: PrivateTask, viewer_id: uuid.UUID) -> dict:
    m = sharing.member(db, task.id, viewer_id)
    role = m.role if m else "viewer"
    evs = db.scalars(select(PrivateTaskEvent).where(PrivateTaskEvent.task_id == task.id)
                     .order_by(PrivateTaskEvent.at, PrivateTaskEvent.id))
    is_owner = role == "owner"
    return {
        "id": str(task.id), "kind": task.kind, "title": task.title, "status": task.status, "next_step": task.next_step,
        "due_at": task.due_at.isoformat() if task.due_at else None, "who": task.who,
        "usage_text": task.usage_text if is_owner else "Delt med dig – koster dig ingenting",
        "is_example": task.is_example, "created_at": task.created_at.isoformat(),
        "updated_at": task.updated_at.isoformat(),
        "items": items_out(db, task, viewer_id, role) if task.kind == "list" else [],
        "remind_at": task.remind_at.isoformat() if task.remind_at else None,
        "call": call_out(latest_call(db, task.id)) if task.kind == "call" else None,
        "events": [{"at": e.at.isoformat(), "text": e.text} for e in evs] if is_owner or task.share_mode == "group" else [],
        "list_type": task.list_type, "shared": task.share_mode is not None, "share_mode": task.share_mode,
        "my_role": role, "members": sharing.members_out(db, task, viewer_id) if task.share_mode else [],
    }


# --------------------------------------------------------------------------- chat messages

def add_message(db: OrmSession, ws_id: uuid.UUID, *, kind: str, text: str, role: str = "assistant",
                task_id: uuid.UUID | None = None, about_task_id: uuid.UUID | None = None,
                before: str | None = None, after: str | None = None, options: list[dict] | None = None,
                links: list[str] | None = None, addon_key: str | None = None) -> PrivateMessage:
    at = rules.now()
    last = db.scalar(select(func.max(PrivateMessage.created_at)).where(PrivateMessage.workspace_id == ws_id))
    if last is not None and last >= at:  # keep the conversation's order strict, also with a frozen test clock
        at = last + timedelta(microseconds=1)
    m = PrivateMessage(workspace_id=ws_id, role=role, kind=kind, text=text[:4000], task_id=task_id,
                       about_task_id=about_task_id, before=before, after=after, options=options, links=links,
                       addon_key=addon_key, created_at=at)
    db.add(m)
    db.flush()
    return m


def message_out(m: PrivateMessage) -> dict:
    return {"id": str(m.id), "role": m.role, "kind": m.kind, "text": m.text,
            "task_id": str(m.task_id) if m.task_id else None,
            "about_task_id": str(m.about_task_id) if m.about_task_id else None, "before": m.before, "after": m.after,
            "options": [{"id": o["id"], "label": o["label"], "sub": o.get("sub") or ""} for o in m.options]
            if m.options else None,
            "links": m.links, "answered_option_id": m.answered_option_id, "addon_key": m.addon_key,
            "created_at": m.created_at.isoformat()}


def messages(db: OrmSession, ctx, task_id: uuid.UUID | None = None, limit: int = 200) -> list[PrivateMessage]:
    q = select(PrivateMessage).where(PrivateMessage.workspace_id == ctx.ws_id)
    if task_id is not None:
        q = q.where(or_(PrivateMessage.task_id == task_id, PrivateMessage.about_task_id == task_id))
    rows = list(db.scalars(q.order_by(PrivateMessage.created_at.desc(), PrivateMessage.id.desc()).limit(limit)))
    return list(reversed(rows))


def cancel_reminders_for(db: OrmSession, task_id: uuid.UUID) -> None:
    db.execute(update(OutboxEvent).where(OutboxEvent.event_type == "privat.reminder",
                                         OutboxEvent.dedupe_key.like(f"privat-reminder:{task_id}:%"),
                                         OutboxEvent.status == "queued").values(status="blocked",
                                                                                last_error="cancelled"))
