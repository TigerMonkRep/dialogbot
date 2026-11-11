"""«Dine data» in Dialogbot Privat (Konto): export everything and delete the account (GDPR art. 15, 17 and 20).

EXPORT. POST /privat/data-export queues a job; the worker (event privat.data_export) collects every piece of Privat
data that belongs to the caller – account, plan, household, apps and their data, own tasks with items and history,
lists and wishlists shared with them (only what is theirs there: their own items and reservations), messages with
the assistant, call log with the business's reply, appointments, birthdays, bills, Opkaldssaldo movements, invitations,
referrals, groups, browser bookings – into JSON plus a readable overview (oversigt.txt), and e-mails a link. The
link needs the token from the e-mail AND the same login, works for EXPORT_DAYS days, after which the content is wiped.
Never in an export: other people's data (who reserved the owner's wishes stays secret; shared lists only show what
the caller wrote), tokens, code hashes, push keys, or internal call identifiers.

DELETE. POST /privat/account/delete with the e-mail typed again. In this order, in one transaction:
1. A live Stripe subscription is cancelled at once (nothing more is charged). If Stripe cannot be reached, nothing is
   deleted (409/502) – a deleted account must never go on paying. Invoices stay at Stripe (bogføringsloven, 5 år –
   privatlivspolitikken «Betaling»); our own records of them go with the workspace.
2. The household: an owner's members lose the Familie rights (their own accounts and data are untouched); a member
   leaves.
3. Everything in the personal workspace (tasks, items, messages, calls with transcripts/replies, appointments, apps
   and their data, ledger, subscription row, add-on states …) is deleted with it (ON DELETE CASCADE), and its files
   (receipt photos, wish pictures, covers) are removed from storage. Private calls are never recorded (no audio).
4. Wishlist rule: the caller's wishlists disappear, and with them every reservation and group-gift pledge OTHERS made
   on them. On OTHER people's lists the caller's reservations and pledges are released and their name is removed from
   items they added or ticked (the item text stays – it belongs to that list). Their membership of shared lists ends.
5. Groups they own, invitations and referral rows, push subscriptions, data exports, pending e-mails and SMS codes to
   them, quiz-funnel drafts and Stripe webhook payloads that name them are deleted or scrubbed.
6. All sessions end. The login itself (users row) is deleted too – unless the same login is also used for something
   outside Privat (a business workspace, an ambassador agreement with payouts that must be kept, or operator rights):
   then only Privat is deleted and the login stays (`login_kept`).
7. One audit row WITHOUT personal data: action privat.account_deleted, counts and flags only.
The legal texts (legal.json: privatlivspolitikken) promise the right to deletion and data portability but no period for
Privat; deletion is therefore immediate. (The 30 days in the terms are for business customers' data on termination.)
Connected Google/Outlook calendars of the Privat workspace are revoked at the provider first (best effort, logged,
never blocking; Microsoft has no revocation endpoint – the token is deleted with the workspace).

RETENTION (decision Fürster 2026-11-11, privatlivspolitikken «Dialogbot Privat»):
- Chats and call summaries (business_reply, confirmed_text, price) are kept as long as the account exists. The user
  can delete one message (DELETE /privat/messages/{id}) or one finished call with its summary (DELETE
  /privat/calls/{task_id}) at any time.
- Raw transcripts are deleted after TRANSCRIPT_DAYS (purge_transcripts, daily in the worker): Privat keeps no full
  transcript itself, only the lead-pitch excerpt (pitch_transcript_excerpt), which is cleared; Vapi's copy of the
  call (outbound and call-backs) is deleted through its API.
- The export link works for EXPORT_DAYS (7) days.
"""
from __future__ import annotations

import io
import json
import uuid
import zipfile
from datetime import date, datetime, timedelta

import structlog
from sqlalchemy import Text, cast, delete, func, or_, select, update
from sqlalchemy.orm import Session as OrmSession

from app.config import get_settings
from app.core.errors import ApiError, Conflict, NotFound, ValidationFailed
from app.core.security import new_token, token_digest
from app.models import (
    AuditLog,
    BrowserRun,
    CreditLedger,
    EmailDelivery,
    IdempotencyKey,
    Membership,
    OutboxEvent,
    PrivateAddonEnabled,
    PrivateAddonState,
    PrivateAppData,
    PrivateAppointment,
    PrivateBill,
    PrivateBirthday,
    PrivateCall,
    PrivateDataExport,
    PrivateGiftPledge,
    PrivateGroup,
    PrivateGroupGift,
    PrivateGroupMember,
    PrivateInvite,
    PrivateMessage,
    PrivatePhoneCode,
    PrivateProfile,
    PrivateReferral,
    PrivateSubscription,
    PrivateTask,
    PrivateTaskEvent,
    PrivateTaskItem,
    PrivateTaskMember,
    PushSubscription,
    Session,
    User,
    WebhookEvent,
    Workspace,
)
from app.models.funnel import FunnelDraft
from app.modules.privat import rules

log = structlog.get_logger("dialogbot.privat.gdpr")

EXPORT_DAYS = 7
EXPORTS_PER_DAY = 3
TRANSCRIPT_DAYS = 90
RUNNING_CALL = ("approved", "scheduled", "dialling", "in_progress", "unknown")
EVENT = "privat.data_export"


class RateLimited(ApiError):
    status_code = 429
    code = "rate_limited"


# --------------------------------------------------------------------------- serialising

def _v(x):
    if isinstance(x, datetime | date):
        return x.isoformat()
    if isinstance(x, uuid.UUID):
        return str(x)
    return x


def _row(obj, *, skip: tuple[str, ...] = (), only: tuple[str, ...] | None = None) -> dict:
    cols = [c.key for c in obj.__table__.columns]
    return {k: _v(getattr(obj, k)) for k in cols if k not in skip and (only is None or k in only)}


_TASK_SKIP = ("workspace_id", "reminder_version")
_ITEM_SKIP = ("workspace_id", "task_id", "reserved_by_user_id", "added_by_user_id", "done_by_user_id", "image_key")
_SECRET_PROFILE = ("phone_code_hash", "phone_code_attempts", "phone_code_expires_at", "phone_code_sent_at",
                   "phone_pending_e164", "calendar_feed_token_hash")


def collect(db: OrmSession, user: User) -> dict:
    """Everything Privat holds about `user`, as JSON-able data. Only their own; see the module docstring."""
    from app.modules.privat import household

    prof = db.scalar(select(PrivateProfile).where(PrivateProfile.user_id == user.id))
    ws = prof.workspace_id if prof else None
    out: dict = {
        "format": "dialogbot-privat-export/1", "created_at": rules.now().isoformat(),
        "account": {"email": user.email, "name": user.display_name, "language": user.interface_language,
                    "created_at": _v(user.created_at), "email_verified_at": _v(user.email_verified_at),
                    "phone_verified_at": _v(user.phone_verified_at)},
    }
    if ws is None:
        return out
    out["profile"] = _row(prof, skip=_SECRET_PROFILE + ("workspace_id", "user_id")) | {
        "calendar_link_active": prof.calendar_feed_token_hash is not None}
    sub = db.get(PrivateSubscription, ws)
    out["subscription"] = _row(sub, only=("plan", "status", "interval", "trial_ends_at", "current_period_end",
                                          "cancel_at_period_end", "currency", "created_at")) if sub else None

    class _Ctx:  # household.state needs the caller's ws and name only
        ws_id = ws
        user = None

    _Ctx.user = user
    hh = household.state(db, _Ctx)
    out["household"] = {k: hh[k] for k in ("role", "active", "count", "owner_first_name")} | {
        "members": [m["name"] for m in hh["members"]]}
    out["apps"] = {
        "enabled": [_row(r, only=("key", "enabled_at")) for r in db.scalars(
            select(PrivateAddonEnabled).where(PrivateAddonEnabled.workspace_id == ws))],
        "state": [_row(r, skip=("workspace_id",)) for r in db.scalars(
            select(PrivateAddonState).where(PrivateAddonState.workspace_id == ws))],
        "data": {r.app_key: r.data for r in db.scalars(select(PrivateAppData).where(PrivateAppData.workspace_id == ws))},
    }
    tasks = []
    for t in db.scalars(select(PrivateTask).where(PrivateTask.workspace_id == ws).order_by(PrivateTask.created_at)):
        items = db.scalars(select(PrivateTaskItem).where(PrivateTaskItem.task_id == t.id)
                           .order_by(PrivateTaskItem.position, PrivateTaskItem.created_at))
        n_members = db.scalar(select(func.count()).select_from(PrivateTaskMember).where(
            PrivateTaskMember.task_id == t.id, PrivateTaskMember.role != "owner")) or 0
        tasks.append(_row(t, skip=_TASK_SKIP) | {
            # a wishlist's reservations are secret to its owner – also here
            "items": [_row(i, skip=_ITEM_SKIP) | {"has_image": bool(i.image_key)} for i in items],
            "history": [_row(e, only=("at", "text")) for e in db.scalars(
                select(PrivateTaskEvent).where(PrivateTaskEvent.task_id == t.id).order_by(PrivateTaskEvent.at))],
            "shared_with_people": int(n_members)})
    out["tasks"] = tasks
    shared = []
    for m, t in db.execute(select(PrivateTaskMember, PrivateTask).join(PrivateTask, PrivateTask.id == PrivateTaskMember.task_id)
                           .where(PrivateTaskMember.user_id == user.id, PrivateTaskMember.role != "owner")):
        mine = db.scalars(select(PrivateTaskItem).where(PrivateTaskItem.task_id == t.id, or_(
            PrivateTaskItem.added_by_user_id == user.id, PrivateTaskItem.done_by_user_id == user.id,
            PrivateTaskItem.reserved_by_user_id == user.id)))
        shared.append({"title": t.title, "list_type": t.list_type, "my_role": m.role, "joined_at": _v(m.created_at),
                       "my_items": [{"text": i.text, "added_by_me": i.added_by_user_id == user.id,
                                     "ticked_by_me": i.done_by_user_id == user.id,
                                     "reserved_by_me": i.reserved_by_user_id == user.id} for i in mine]})
    out["shared_with_me"] = shared
    out["group_gift_pledges"] = [
        {"wish": i.text, "amount_minor": p.amount_minor, "currency": g.currency, "status": p.status,
         "created_at": _v(p.created_at)}
        for p, g, i in db.execute(select(PrivateGiftPledge, PrivateGroupGift, PrivateTaskItem)
                                  .join(PrivateGroupGift, PrivateGroupGift.id == PrivateGiftPledge.gift_id)
                                  .join(PrivateTaskItem, PrivateTaskItem.id == PrivateGroupGift.item_id)
                                  .where(PrivateGiftPledge.user_id == user.id))]
    out["messages"] = [
        _row(m, only=("role", "kind", "text", "before", "after", "created_at")) | {
            "options": [{"label": o.get("label"), "sub": o.get("sub")} for o in (m.options or []) if isinstance(o, dict)]}
        for m in db.scalars(select(PrivateMessage).where(PrivateMessage.workspace_id == ws).order_by(PrivateMessage.created_at))]
    out["calls"] = [_row(c, skip=("workspace_id", "vapi_call_id", "pool_number")) for c in db.scalars(
        select(PrivateCall).where(PrivateCall.workspace_id == ws).order_by(PrivateCall.created_at))]
    out["appointments"] = [_row(a, skip=("workspace_id", "external")) for a in db.scalars(
        select(PrivateAppointment).where(PrivateAppointment.workspace_id == ws).order_by(PrivateAppointment.starts_at))]
    out["birthdays"] = [_row(b, skip=("workspace_id", "name_key")) for b in db.scalars(
        select(PrivateBirthday).where(PrivateBirthday.workspace_id == ws))]
    out["bills"] = [_row(b, skip=("workspace_id", "name_key")) for b in db.scalars(
        select(PrivateBill).where(PrivateBill.workspace_id == ws))]
    out["call_balance"] = [_row(r, only=("kind", "amount", "currency", "text", "created_at")) for r in db.scalars(
        select(CreditLedger).where(CreditLedger.workspace_id == ws).order_by(CreditLedger.created_at))]
    out["bookings"] = [_row(r, only=("engine", "goal", "status", "before_after", "result", "created_at", "finished_at"))
                       for r in db.scalars(select(BrowserRun).where(BrowserRun.workspace_id == ws))]
    out["invitations_sent"] = [_row(i, only=("resource_type", "addon_key", "mode", "role", "created_at", "expires_at",
                                             "revoked_at", "opened_count", "accepted_count"))
                               for i in db.scalars(select(PrivateInvite).where(PrivateInvite.inviter_user_id == user.id))]
    out["referrals"] = [
        {"as": "inviter" if r.inviter_user_id == user.id else "invitee", "accepted_at": _v(r.accepted_at),
         "activated_at": _v(r.activated_at), "rewarded_at": _v(r.rewarded_at)}
        for r in db.scalars(select(PrivateReferral).where(or_(PrivateReferral.inviter_user_id == user.id,
                                                              PrivateReferral.invitee_user_id == user.id)))]
    groups = []
    for g in db.scalars(select(PrivateGroup).where(PrivateGroup.owner_user_id == user.id)):
        groups.append({"name": g.name, "created_at": _v(g.created_at), "people": [
            {"name": m.name, "phone": m.phone_e164} for m in db.scalars(
                select(PrivateGroupMember).where(PrivateGroupMember.group_id == g.id))]})
    out["groups"] = groups
    out["in_others_groups"] = [
        {"group": g.name, "owner_first_name": rules.first_name(o.display_name if o else None)}
        for _m, g, o in db.execute(select(PrivateGroupMember, PrivateGroup, User)
                                   .join(PrivateGroup, PrivateGroup.id == PrivateGroupMember.group_id)
                                   .join(User, User.id == PrivateGroup.owner_user_id, isouter=True)
                                   .where(PrivateGroupMember.user_id == user.id))]
    out["devices"] = [_row(p, only=("audience", "user_agent", "created_at", "last_success_at")) for p in db.scalars(
        select(PushSubscription).where(PushSubscription.user_id == user.id))]
    out["signup_answers"] = [_row(d, only=("kind", "answers", "gate", "created_at")) for d in db.scalars(
        select(FunnelDraft).where(FunnelDraft.user_id == user.id))]
    return out


def _overview(data: dict, lang: str) -> str:
    """oversigt.txt: the same export, readable. Danish, or English for any other interface language."""
    da = (lang or "da").startswith("da")
    L = (lambda d, e: d if da else e)  # noqa: E731
    a = data.get("account", {})
    lines = [L("DIALOGBOT PRIVAT – DINE DATA", "DIALOGBOT PRIVAT – YOUR DATA"),
             L(f"Lavet {data.get('created_at', '')[:16].replace('T', ' ')} (UTC)",
               f"Created {data.get('created_at', '')[:16].replace('T', ' ')} (UTC)"), "",
             f"{L('Navn', 'Name')}: {a.get('name', '')}", f"E-mail: {a.get('email', '')}"]
    p = data.get("profile") or {}
    if p.get("phone_e164"):
        lines.append(f"{L('Mobil', 'Mobile')}: {p['phone_e164']}")
    if p.get("location_city"):
        lines.append(f"{L('By', 'City')}: {p['location_city']}")
    s = data.get("subscription") or {}
    if s:
        lines.append(f"{L('Plan', 'Plan')}: {s.get('plan')} · {s.get('status')}")
    hh = data.get("household") or {}
    if hh.get("role"):
        lines.append(f"{L('Husstand', 'Household')}: {hh['role']} · {hh.get('count')}")
    lines.append("")
    counts = [(L("Opgaver og lister", "Tasks and lists"), len(data.get("tasks", []))),
              (L("Delt med dig", "Shared with you"), len(data.get("shared_with_me", []))),
              (L("Beskeder med assistenten", "Messages with the assistant"), len(data.get("messages", []))),
              (L("Opkald", "Calls"), len(data.get("calls", []))),
              (L("Aftaler", "Appointments"), len(data.get("appointments", []))),
              (L("Fødselsdage", "Birthdays"), len(data.get("birthdays", []))),
              (L("Regninger", "Bills"), len(data.get("bills", []))),
              (L("Apps slået til", "Apps switched on"), len((data.get("apps") or {}).get("enabled", []))),
              (L("Invitationer sendt", "Invitations sent"), len(data.get("invitations_sent", []))),
              (L("Grupper", "Groups"), len(data.get("groups", [])))]
    lines += [f"{k}: {n}" for k, n in counts] + [""]
    for t in data.get("tasks", []):
        lines.append(f"# {t.get('title')} ({t.get('list_type') or t.get('kind')}, {str(t.get('created_at', ''))[:10]})")
        lines += [f"  - [{'x' if i.get('done') else ' '}] {i.get('text')}" for i in t.get("items", [])]
    if data.get("calls"):
        lines += ["", L("OPKALD", "CALLS")]
        for c in data["calls"]:
            lines.append(f"- {str(c.get('approved_at') or c.get('created_at') or '')[:16]} {c.get('business_name')}: "
                         f"{c.get('result') or c.get('status')}"
                         + (f" – {c['business_reply']}" if c.get("business_reply") else ""))
    lines += ["", L("Alt står også i data.json.", "Everything is also in data.json.")]
    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------- export

def export_out(row: PrivateDataExport | None) -> dict:
    if row is None:
        return {"status": None, "requested_at": None, "expires_at": None}
    return {"status": row.status, "requested_at": _v(row.requested_at), "expires_at": _v(row.expires_at)}


def latest_export(db: OrmSession, user_id: uuid.UUID) -> PrivateDataExport | None:
    purge_expired(db, user_id=user_id)
    return db.scalar(select(PrivateDataExport).where(PrivateDataExport.user_id == user_id)
                     .order_by(PrivateDataExport.requested_at.desc(), PrivateDataExport.id).limit(1))


def request_export(db: OrmSession, ctx) -> dict:
    """Queue an export (idempotent while one is being made); at most EXPORTS_PER_DAY a day."""
    from app.core.outbox import enqueue

    busy = db.scalar(select(PrivateDataExport).where(PrivateDataExport.user_id == ctx.user_id,
                                                     PrivateDataExport.status == "queued"))
    if busy is not None:
        return export_out(busy)
    n = db.scalar(select(func.count()).select_from(PrivateDataExport).where(
        PrivateDataExport.user_id == ctx.user_id, PrivateDataExport.requested_at > rules.now() - timedelta(days=1))) or 0
    if n >= EXPORTS_PER_DAY:
        raise RateLimited("Du har bedt om dine data mange gange i dag. Prøv igen i morgen.")
    row = PrivateDataExport(user_id=ctx.user_id, status="queued", requested_at=rules.now())
    db.add(row)
    db.flush()
    enqueue(db, event_type=EVENT, dedupe_key=f"{EVENT}:{row.id}", workspace_id=ctx.ws_id,
            payload={"export_id": str(row.id)})
    return export_out(row)


def _link(raw: str) -> str:
    return f"{get_settings().frontend_base_url.rstrip('/')}/privat/konto?eksport={raw}"


def handle_export(db: OrmSession, ev) -> None:
    """Worker: build the export, keep it with a hashed token, and e-mail the link. Idempotent (a done row is skipped)."""
    from app.core.outbox import enqueue
    from app.modules.integrations import email_templates as tpl
    from app.modules.integrations import privat_mails

    row = db.get(PrivateDataExport, uuid.UUID(str(ev.payload.get("export_id"))))
    if row is None or row.status != "queued":
        return
    user = db.get(User, row.user_id)
    if user is None:
        db.delete(row)
        db.commit()
        return
    data = collect(db, user)
    data["overview"] = _overview(data, user.interface_language)
    raw = new_token()
    now = rules.now()
    row.status, row.data, row.token_hash = "ready", data, token_digest(raw)
    row.ready_at, row.expires_at = now, now + timedelta(days=EXPORT_DAYS)
    mail = privat_mails.data_export(_link(raw), EXPORT_DAYS, user.interface_language or "da")
    prof = db.scalar(select(PrivateProfile).where(PrivateProfile.user_id == user.id))
    enqueue(db, event_type="email.branded", dedupe_key=f"privat-export-mail:{row.id}",
            workspace_id=prof.workspace_id if prof else None,
            payload={"to_email": user.email, "email": tpl.to_payload(mail)})
    db.commit()


def download(db: OrmSession, ctx, token: str) -> tuple[bytes, str]:
    """(zip bytes, file name). The token from the e-mail AND the same login; expired/unknown/someone else's = 404."""
    purge_expired(db, user_id=ctx.user_id)
    row = db.scalar(select(PrivateDataExport).where(PrivateDataExport.token_hash == token_digest((token or "")[:200])))
    if row is None or row.user_id != ctx.user_id or row.status != "ready" or row.data is None:
        raise NotFound("Linket er udløbet eller ugyldigt. Bed om dine data igen under Konto.", code="export_invalid")
    data = dict(row.data)
    overview = data.pop("overview", "")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("data.json", json.dumps(data, ensure_ascii=False, indent=2))
        z.writestr("oversigt.txt" if (ctx.user.interface_language or "da").startswith("da") else "overview.txt",
                   overview)
    row.downloaded_at = rules.now()
    return buf.getvalue(), f"dialogbot-privat-data-{rules.now().date().isoformat()}.zip"


def purge_expired(db: OrmSession, *, user_id: uuid.UUID | None = None) -> int:
    """Expired links: the content and the token hash are wiped (the row stays as «expired»)."""
    q = update(PrivateDataExport).where(PrivateDataExport.status == "ready", PrivateDataExport.expires_at <= rules.now())
    if user_id is not None:
        q = q.where(PrivateDataExport.user_id == user_id)
    r = db.execute(q.values(status="expired", data=None, token_hash=None))
    return r.rowcount or 0


# --------------------------------------------------------------------------- one message / one call, raw transcripts

def delete_message(db: OrmSession, ctx, message_id: uuid.UUID) -> None:
    """One chat line, the user's own or the assistant's, in the caller's own workspace. 404 otherwise."""
    m = db.get(PrivateMessage, message_id)
    if m is None or m.workspace_id != ctx.ws_id:
        raise NotFound("Beskeden findes ikke")
    db.delete(m)
    db.flush()


def delete_call(db: OrmSession, ctx, task_id: uuid.UUID) -> None:
    """A call the user no longer wants kept: the task, every call attempt with its summary, its history and the chat
    lines about it, and Vapi's copy. Owner only (404 otherwise); not while the call is approved or running (409).
    Opkaldssaldo movements stay (bookkeeping; they hold no summary) and an appointment it created stays in the calendar."""
    from app.modules.privat import sharing
    from app.modules.sales.recordings import delete_at_vapi

    task, m = sharing.access(db, task_id, ctx.user_id, lock=True)
    if task.kind != "call" or m.role != "owner" or task.workspace_id != ctx.ws_id:
        raise NotFound("Opkaldet findes ikke")
    rows = list(db.scalars(select(PrivateCall).where(PrivateCall.task_id == task.id).with_for_update()))
    if any(c.status in RUNNING_CALL for c in rows):
        raise Conflict("Opkaldet er i gang eller planlagt. Annullér det først, eller vent til det er slut.",
                       code="call_running")
    for c in rows:
        if c.vapi_call_id:
            delete_at_vapi(c.vapi_call_id)
    db.execute(delete(PrivateMessage).where(PrivateMessage.workspace_id == ctx.ws_id, or_(
        PrivateMessage.task_id == task.id, PrivateMessage.about_task_id == task.id)))
    db.delete(task)  # calls, events, items and members go with it (ON DELETE CASCADE)
    db.flush()
    log.info("privat.call_deleted", attempts=len(rows))


def purge_transcripts(db: OrmSession, now: datetime | None = None) -> dict:
    """Worker, daily: raw call transcripts older than TRANSCRIPT_DAYS. Our own excerpt is cleared; Vapi is asked to
    delete its copy of every Privat call (outbound by private_calls.vapi_call_id, call-backs by their webhook row).
    A Vapi failure is logged and tried again the next day; summaries are never touched."""
    from app.modules.sales.recordings import delete_at_vapi

    now = now or rules.now()
    cutoff = now - timedelta(days=TRANSCRIPT_DAYS)
    done = {"excerpts": 0, "provider": 0, "provider_failed": 0}
    old = func.coalesce(PrivateCall.ended_at, PrivateCall.dialled_at, PrivateCall.created_at) < cutoff
    done["excerpts"] = db.execute(update(PrivateCall).where(PrivateCall.pitch_transcript_excerpt.is_not(None), old)
                                  .values(pitch_transcript_excerpt=None)).rowcount or 0
    no_provider = not get_settings().vapi_api_key
    calls = list(db.scalars(select(PrivateCall).where(PrivateCall.vapi_call_id.is_not(None), old)))
    events = list(db.scalars(select(WebhookEvent).where(
        WebhookEvent.provider == "vapi", WebhookEvent.received_at < cutoff,
        WebhookEvent.payload["privat"].as_boolean().is_(True),
        WebhookEvent.payload["transcript_deleted"].as_boolean().is_not(True))))
    ids = {c.vapi_call_id for c in calls} | {str(e.payload.get("call_id") or "") for e in events}
    gone = set()
    for vid in sorted(i for i in ids if i):
        if no_provider or delete_at_vapi(vid):
            gone.add(vid)
            done["provider"] += 0 if no_provider else 1
        else:
            done["provider_failed"] += 1
    for c in calls:
        if c.vapi_call_id in gone:
            c.vapi_call_id = None
    for e in events:
        if not e.payload.get("call_id") or str(e.payload.get("call_id")) in gone:
            e.payload = {**e.payload, "transcript_deleted": True}
    db.commit()
    if any(done.values()):
        log.info("privat.transcripts_purged", **done)
    return done


# --------------------------------------------------------------------------- delete

def _revoke_calendars(db: OrmSession, ws_id: uuid.UUID) -> dict:
    """Google/Outlook access of the PRIVAT workspace (never a business workspace's): revoked at the provider, best
    effort. Never raises – the deletion goes on whatever happens; the outcome is logged (no personal data)."""
    from app.modules.integrations import credentials, oauth
    from app.modules.privat.appointments import PROVIDER_CONNECTOR

    out: dict = {}
    for provider, key in PROVIDER_CONNECTOR.items():
        try:
            conn = credentials.connection(db, ws_id, key)
            if conn is None:
                continue
            if conn.auth_kind != "oauth" or conn.simulated:
                out[provider] = "simulated"
                continue
            secret = credentials.get_secret(conn) or {}
            tok = secret.get("refresh_token") or secret.get("access_token")
            out[provider] = oauth.revoke(oauth.provider_for(provider), tok) if tok else "no_token"
        except Exception as e:  # noqa: BLE001 – best effort: never blocks the deletion
            out[provider] = "failed"
            log.warning("privat.calendar_revoke_failed", provider=provider, error=type(e).__name__)
    for provider, outcome in out.items():
        log.info("privat.calendar_revoke", provider=provider, outcome=outcome)
    return out


def _keeps_login(db: OrmSession, user: User, ws_id: uuid.UUID) -> bool:
    """Whether the login is used for something outside Privat that must survive (see module docstring, step 6)."""
    from app.models import Ambassador

    other = db.scalar(select(func.count()).select_from(Membership).where(
        Membership.user_id == user.id, Membership.workspace_id != ws_id)) or 0
    amb = db.scalar(select(Ambassador.id).where(Ambassador.user_id == user.id)) is not None
    return bool(other) or amb or bool(user.is_platform_operator)


def _cancel_stripe(row: PrivateSubscription | None) -> bool:
    """Cancel a live Stripe subscription now. True if one was cancelled. Raises when Stripe cannot do it."""
    from app.modules.billing import stripe as stripe_api

    if row is None or not row.stripe_subscription_id or row.status not in ("trial", "active", "past_due", "canceled"):
        return False
    if row.status == "canceled" and not (row.current_period_end and row.current_period_end > rules.now()):
        return False  # already over
    try:
        stripe_api.request("DELETE", f"/subscriptions/{row.stripe_subscription_id}")
    except stripe_api.StripeFailed as e:
        if "No such subscription" in str(e) or "resource_missing" in str(e) or "canceled" in str(e):
            return False  # already gone at Stripe
        raise ApiError("Vi kunne ikke opsige dit abonnement lige nu, så intet er slettet. Prøv igen om lidt.",
                       code="subscription_cancel_failed", status_code=502) from e
    except ApiError as e:  # Stripe not configured on a server that still has a subscription row
        raise ApiError("Vi kunne ikke opsige dit abonnement lige nu, så intet er slettet. Prøv igen om lidt.",
                       code="subscription_cancel_failed", status_code=502) from e
    return True


def delete_account(db: OrmSession, ctx, confirm_email: str) -> dict:
    from app.modules.privat import files, household

    user, ws = ctx.user, ctx.ws_id
    if (confirm_email or "").strip().lower() != (user.email or "").strip().lower():
        raise ValidationFailed("Skriv din e-mail præcis, som den står, for at slette kontoen",
                               field_errors=[{"field": "confirm_email"}])
    if ctx.principal.session.impersonator_user_id is not None:
        raise Conflict("En konto kan ikke slettes i «se som kunde»", code="view_as_not_allowed")
    sub = db.scalar(select(PrivateSubscription).where(PrivateSubscription.workspace_id == ws).with_for_update())
    had_sub = _cancel_stripe(sub)
    hh = household.state(db, ctx)
    counts = {
        "tasks": db.scalar(select(func.count()).select_from(PrivateTask).where(PrivateTask.workspace_id == ws)) or 0,
        "calls": db.scalar(select(func.count()).select_from(PrivateCall).where(PrivateCall.workspace_id == ws)) or 0,
        "household_members_released": len(hh["members"]) if hh["role"] == "owner" else 0,
    }
    uid = user.id
    email = user.email
    phone = ctx.profile.phone_e164
    # 2. household (the FK cascades as well; explicit so the rule is visible)
    from app.models import PrivateHouseholdMember

    db.execute(delete(PrivateHouseholdMember).where(or_(PrivateHouseholdMember.owner_workspace_id == ws,
                                                        PrivateHouseholdMember.member_workspace_id == ws)))
    # 4. other people's lists: release reservations/pledges, drop the name from items, end memberships
    db.execute(update(PrivateTaskItem).where(PrivateTaskItem.reserved_by_user_id == uid).values(reserved_by_user_id=None))
    db.execute(update(PrivateTaskItem).where(PrivateTaskItem.added_by_user_id == uid).values(added_by_user_id=None))
    db.execute(update(PrivateTaskItem).where(PrivateTaskItem.done_by_user_id == uid).values(done_by_user_id=None))
    db.execute(delete(PrivateGiftPledge).where(PrivateGiftPledge.user_id == uid))
    db.execute(update(PrivateGroupGift).where(PrivateGroupGift.coordinator_user_id == uid).values(coordinator_user_id=None))
    db.execute(update(PrivateGroupGift).where(PrivateGroupGift.pending_coordinator_user_id == uid)
               .values(pending_coordinator_user_id=None))
    db.execute(delete(PrivateTaskMember).where(PrivateTaskMember.user_id == uid))
    # 5. groups, invitations, referrals, devices, exports, pending mails/codes, funnel, webhook payloads
    db.execute(delete(PrivateGroupMember).where(PrivateGroupMember.user_id == uid,
                                                PrivateGroupMember.joined_via_link_id.is_not(None)))
    db.execute(update(PrivateGroupMember).where(PrivateGroupMember.user_id == uid)
               .values(user_id=None, joined_via_invite_id=None))
    db.execute(delete(PrivateGroup).where(PrivateGroup.owner_user_id == uid))
    db.execute(delete(PrivateReferral).where(or_(PrivateReferral.inviter_user_id == uid,
                                                 PrivateReferral.invitee_user_id == uid)))
    db.execute(delete(PrivateInvite).where(PrivateInvite.inviter_user_id == uid))
    db.execute(delete(PushSubscription).where(PushSubscription.user_id == uid, PushSubscription.audience == "privat"))
    db.execute(delete(PrivateDataExport).where(PrivateDataExport.user_id == uid))
    if phone:
        db.execute(delete(PrivatePhoneCode).where(PrivatePhoneCode.phone_e164 == phone))
    db.execute(delete(FunnelDraft).where(or_(FunnelDraft.user_id == uid, FunnelDraft.workspace_id == ws)))
    db.execute(delete(IdempotencyKey).where(IdempotencyKey.scope.startswith(f"{uid}:")))
    quoted = json.dumps(email)  # the address as it appears inside a JSON payload
    db.execute(delete(OutboxEvent).where(OutboxEvent.workspace_id.is_(None), OutboxEvent.status != "processing",
                                         cast(OutboxEvent.payload, Text).contains(quoted)))
    db.execute(delete(EmailDelivery).where(EmailDelivery.workspace_id.is_(None), func.lower(EmailDelivery.to_email)
                                           == email.lower()))
    db.execute(update(WebhookEvent).where(or_(cast(WebhookEvent.payload, Text).contains(str(ws)),
                                              cast(WebhookEvent.payload, Text).contains(quoted)))
               .values(payload={"scrubbed": "privat_account_deleted"}))
    # 3. calendar access revoked at Google/Microsoft (best effort), then the workspace and everything in it, and its files
    revoked = _revoke_calendars(db, ws)
    files.delete_workspace(ws)
    keep = _keeps_login(db, user, ws)
    db.execute(delete(Workspace).where(Workspace.id == ws))
    # 6. sessions and the login
    if keep:
        db.execute(update(Session).where(Session.user_id == uid, Session.revoked_at.is_(None))
                   .values(revoked_at=rules.now()))
    else:
        db.execute(delete(User).where(User.id == uid))
    # 7. audit without personal data
    db.add(AuditLog(workspace_id=None, actor_user_id=None, action="privat.account_deleted", object_type="private_account",
                    object_id=None, before=None,
                    after={"login_kept": keep, "subscription_cancelled": had_sub, "household_role": hh["role"],
                           "calendar_revoke": revoked, **counts}))
    db.flush()
    db.expunge_all()
    log.info("privat.account_deleted", login_kept=keep, subscription_cancelled=had_sub)
    return {"deleted": True, "login_kept": keep}
