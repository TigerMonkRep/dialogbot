"""Outbox worker.

Run: `python -m app.worker.runner` (loop) or call `process_once()` from tests.

Guarantees:
- at-least-once delivery with a time-bounded lease; a crashed worker's job is
  re-picked once the lease expires (resume after process interruption);
- controlled retries with exponential backoff up to max_attempts, then `failed`;
- handlers are idempotent: side effects are keyed on the event id via unique
  constraints (e.g. email_deliveries.outbox_event_id), so redelivery never
  produces a second domain effect.
"""
from __future__ import annotations

import os
import socket
import time
import uuid
from datetime import UTC, datetime, timedelta

import structlog
from sqlalchemy import or_, select, text
from sqlalchemy.orm import Session as OrmSession

from app.config import get_settings
from app.core.logging import configure_logging
from app.db import get_session_factory
from app.models import EmailDelivery, OutboxEvent
from app.modules.integrations import email_templates as tpl
from app.modules.integrations.email import OutgoingEmail, get_email_adapter
from app.modules.integrations.email_texts import user_language, workspace_language

log = structlog.get_logger("dialogbot.worker")


class HandlerError(Exception):
    pass


def _now() -> datetime:
    return datetime.now(UTC)


# --- handlers ---------------------------------------------------------------


def _send_mail(db: OrmSession, ev: OutboxEvent, mail) -> None:
    """Send one branded email (app.modules.integrations.email_templates.Email) for this outbox event."""
    if db.scalar(select(EmailDelivery).where(EmailDelivery.outbox_event_id == ev.id)) is not None:
        return  # already delivered for this event: redelivery is a no-op
    adapter = get_email_adapter()
    adapter.deliver(db, ev.id, OutgoingEmail(to_email=ev.payload["to_email"], subject=mail.subject,
                                             body_text=mail.text(), body_html=mail.html(),
                                             workspace_id=ev.workspace_id))


# The mail's language is chosen where it is queued (payload "lang"). Events queued before that carried no language:
# account mails then follow the user's interface language and an invitation the workspace's, everything else Danish.

def handle_invitation(db: OrmSession, ev: OutboxEvent) -> None:
    p = ev.payload
    lang = p.get("lang") or workspace_language(db, ev.workspace_id)
    _send_mail(db, ev, tpl.invitation(p["workspace_name"], p["invited_by"], p["role"], p["link"], lang=lang))


def handle_verify(db: OrmSession, ev: OutboxEvent) -> None:
    lang = ev.payload.get("lang") or user_language(db, ev.payload.get("user_id"))
    _send_mail(db, ev, tpl.verify(ev.payload["link"], lang=lang, privat=ev.payload.get("audience") == "privat",
                                  variant=ev.payload.get("variant", "trial")))


def handle_reset(db: OrmSession, ev: OutboxEvent) -> None:
    lang = ev.payload.get("lang") or user_language(db, ev.payload.get("user_id"))
    _send_mail(db, ev, tpl.reset(ev.payload["link"], lang=lang, privat=ev.payload.get("audience") == "privat"))


def handle_new_lead(db: OrmSession, ev: OutboxEvent) -> None:
    p = ev.payload
    _send_mail(db, ev, tpl.new_lead(p["workspace_name"], p["contact_name"], p.get("need_summary") or "", p["link"],
                                    lang=p.get("lang") or "da"))


def handle_daily_report(db: OrmSession, ev: OutboxEvent) -> None:
    p = ev.payload
    _send_mail(db, ev, tpl.daily_report(p["subject"], p["body"], p.get("link"), lang=p.get("lang") or "da"))


def handle_branded(db: OrmSession, ev: OutboxEvent) -> None:
    """Emails whose content is built where they are queued (ambassador programme)."""
    _send_mail(db, ev, tpl.from_payload(ev.payload))


def handle_knowledge_approved(db: OrmSession, ev: OutboxEvent) -> None:
    # Downstream consumers (script regeneration, embeddings) belong to later
    # stages. The event is acknowledged so the audit/outbox trail is complete.
    log.info("knowledge.version_approved", version_id=ev.payload.get("version_id"))


def handle_webhook_deliver(db: OrmSession, ev: OutboxEvent) -> None:
    from app.modules.integrations.events import handle_deliver

    handle_deliver(db, ev)


def handle_public_webhook(db: OrmSession, ev: OutboxEvent) -> None:
    from app.modules.public_api.webhook_delivery import handle_deliver

    handle_deliver(db, ev)


HANDLERS = {
    "webhook.deliver": handle_webhook_deliver,
    "public_webhook.deliver": handle_public_webhook,  # public API webhooks (app/modules/public_api)
    "email.invitation": handle_invitation,
    "email.verify_address": handle_verify,
    "email.password_reset": handle_reset,
    "knowledge.version_approved": handle_knowledge_approved,
    "email.new_lead": handle_new_lead,
    "email.daily_report": handle_daily_report,
    "email.ambassador": handle_branded,
    "email.branded": handle_branded,  # any mail built where it is queued (tpl.to_payload)
    "sales.message": lambda db, ev: _sales_message(db, ev),
    "sales.recording_fetch": lambda db, ev: _sales_recording(db, ev),
    "calls.recording_fetch": lambda db, ev: _call_recording(db, ev),
    "privat.reminder": lambda db, ev: _privat_reminder(db, ev),
    "privat.call_due": lambda db, ev: _privat("handle_call_due", db, ev),
    "privat.call_ask": lambda db, ev: _privat("handle_call_ask", db, ev),
    "privat.calendar_sync": lambda db, ev: _privat_calendar(db, ev),
    "privat.data_export": lambda db, ev: _privat_export(db, ev),
    "push.send": lambda db, ev: _push_send(db, ev),
    "sms.code": lambda db, ev: _sms_code(db, ev),
}


def _sms_code(db: OrmSession, ev: OutboxEvent) -> None:
    from app.modules.integrations.sms_codes import handle

    handle(db, ev)


def _privat(name: str, db: OrmSession, ev: OutboxEvent) -> None:
    from app.modules.privat import calls

    getattr(calls, name)(db, ev)


def _privat_export(db: OrmSession, ev: OutboxEvent) -> None:
    from app.modules.privat.gdpr import handle_export

    handle_export(db, ev)


def _privat_calendar(db: OrmSession, ev: OutboxEvent) -> None:
    from app.modules.privat.appointments import handle_sync

    handle_sync(db, ev)


def _push_send(db: OrmSession, ev: OutboxEvent) -> None:
    from app.modules.privat.push import handle_send

    handle_send(db, ev)


def _privat_reminder(db: OrmSession, ev: OutboxEvent) -> None:
    from app.modules.privat.service import handle_reminder

    handle_reminder(db, ev)


def _sales_recording(db: OrmSession, ev: OutboxEvent) -> None:
    from app.modules.sales.recordings import handle_fetch

    handle_fetch(db, ev)


def _call_recording(db: OrmSession, ev: OutboxEvent) -> None:
    from app.modules.telephony.call_recordings import handle_fetch

    handle_fetch(db, ev)


def _sales_message(db: OrmSession, ev: OutboxEvent) -> None:
    from app.modules.sales.offers import handle_message

    handle_message(db, ev)

# Test hook: event types listed here raise, to exercise retry paths.
FAIL_EVENT_TYPES: set[str] = set()


# --- processing --------------------------------------------------------------


def _worker_id() -> str:
    return f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:6]}"


def _browser_types() -> tuple[str, ...]:
    from app.modules.browser.events import BROWSER_EVENT_TYPES

    return BROWSER_EVENT_TYPES


def claim_one(db: OrmSession, worker_id: str, *, only_types: tuple[str, ...] | None = None) -> OutboxEvent | None:
    """Claim one due event. The main worker never claims browser events (they belong to the browser worker process,
    which holds the live browser sessions); the browser worker claims ONLY those (`only_types`)."""
    s = get_settings()
    now = _now()
    q = (select(OutboxEvent)
         .where(OutboxEvent.next_attempt_at <= now,
                or_(OutboxEvent.status == "queued",
                    (OutboxEvent.status == "processing") & (OutboxEvent.lease_expires_at < now))))
    q = q.where(OutboxEvent.event_type.in_(only_types)) if only_types else q.where(
        OutboxEvent.event_type.not_in(_browser_types()))
    # M03: a suspended workspace's jobs wait in the queue until an operator resumes it (app/core/suspension.py)
    from app.core.suspension import suspended_ids

    q = q.where(or_(OutboxEvent.workspace_id.is_(None), OutboxEvent.workspace_id.not_in(suspended_ids())))
    ev = db.scalar(q.order_by(OutboxEvent.next_attempt_at).with_for_update(skip_locked=True).limit(1))
    if ev is None:
        return None
    ev.status = "processing"
    ev.lease_owner = worker_id
    ev.lease_expires_at = now + timedelta(seconds=s.worker_lease_seconds)
    ev.attempts += 1
    db.commit()
    return ev


def finish(db: OrmSession, ev_id: uuid.UUID, *, error: str | None) -> None:
    ev = db.scalar(select(OutboxEvent).where(OutboxEvent.id == ev_id).with_for_update())
    if ev is None:
        return
    if error is None:
        ev.status = "done"
        ev.processed_at = _now()
        ev.last_error = None
    else:
        ev.last_error = error[:2000]
        if ev.attempts >= ev.max_attempts:
            ev.status = "failed"
        else:
            ev.status = "queued"
            ev.next_attempt_at = _now() + timedelta(seconds=min(300, 2 ** ev.attempts))
    ev.lease_owner = None
    ev.lease_expires_at = None
    db.commit()


def process_once(worker_id: str | None = None, *, handlers: dict | None = None,
                 only_types: tuple[str, ...] | None = None) -> OutboxEvent | None:
    """Claim and process a single event. Returns the event (post-state) or None. `handlers`/`only_types` let a separate
    worker process (the browser worker) reuse this mechanism with its own event types."""
    worker_id = worker_id or _worker_id()
    factory = get_session_factory()
    with factory() as db:
        ev = claim_one(db, worker_id, only_types=only_types)
        if ev is None:
            return None
        ev_id, ev_type = ev.id, ev.event_type
    error: str | None = None
    with factory() as db:
        try:
            ev = db.get(OutboxEvent, ev_id)
            if ev_type in FAIL_EVENT_TYPES:
                raise HandlerError("simulated failure")
            handler = (handlers if handlers is not None else HANDLERS).get(ev_type)
            if handler is None:
                raise HandlerError(f"no handler for {ev_type}")
            handler(db, ev)
            db.commit()
        except Exception as exc:  # noqa: BLE001
            db.rollback()
            error = f"{type(exc).__name__}: {exc}"
            log.warning("outbox.handler_failed", event_id=str(ev_id), event_type=ev_type, error=error)
    with factory() as db:
        finish(db, ev_id, error=error)
        return db.get(OutboxEvent, ev_id)


def drain(max_events: int = 1000) -> int:
    n = 0
    while n < max_events and process_once() is not None:
        n += 1
    return n


SCHEDULE_EVERY_SECONDS = 60


def schema_ready() -> bool:
    """False (and an error in the log) while the database and this code are on different migrations."""
    from app.migrations_head import schema_status

    with get_session_factory()() as db:
        st = schema_status(db)
    if not st["ok"]:
        log.error("worker.schema_mismatch", database=st["database"], code=st["code"],
                  action="scheduled jobs are paused until the database and the code agree")
    return st["ok"]


_RETENTION_RAN: dict = {}


def run_schedules() -> None:
    """Periodic jobs. Each is idempotent (unique snapshots + outbox dedupe), so several workers are safe.

    Paused while the schema differs from this code: during a rolling deploy the migration (run before the API
    starts) and the new worker do not switch at the same instant, and a job against the wrong schema only fills the
    log with errors (that is what `campaigns.package_net_minor does not exist` was, 28/10 10:19–10:21)."""
    if not schema_ready():
        return
    from app.modules.reports.service import run_due

    with get_session_factory()() as db:
        try:
            n = run_due(db)
            if n:
                log.info("reports.generated", count=n)
        except Exception as exc:  # noqa: BLE001 - a failing job must not stop event delivery
            db.rollback()
            log.warning("reports.failed", error=f"{type(exc).__name__}: {exc}")
    with get_session_factory()() as db:
        try:
            from app.modules.billing import grace

            n = grace.run_due(db)  # the 7 days' grace after a paid subscription stops being paid, and its mails
            if n:
                log.info("billing.grace", count=n)
        except Exception as exc:  # noqa: BLE001
            db.rollback()
            log.warning("billing.grace_failed", error=f"{type(exc).__name__}: {exc}")
    with get_session_factory()() as db:
        try:
            n = sync_calendars(db)
            if n:
                log.info("calendars.synced", count=n)
        except Exception as exc:  # noqa: BLE001
            db.rollback()
            log.warning("calendars.failed", error=f"{type(exc).__name__}: {exc}")
    with get_session_factory()() as db:
        try:
            from app.modules.campaigns.service import dispatch

            n = dispatch(db)
            if n:
                log.info("campaigns.dialled", count=n)
        except Exception as exc:  # noqa: BLE001
            db.rollback()
            log.warning("campaigns.failed", error=f"{type(exc).__name__}: {exc}")
    with get_session_factory()() as db:
        try:
            from app.modules.telephony import platform

            n = platform.run_due_jobs(db)
            platform.expire_tests(db)
            db.commit()
            if n:
                log.info("telephony.jobs_run", count=n)
        except Exception as exc:  # noqa: BLE001
            db.rollback()
            log.warning("telephony.jobs_failed", error=f"{type(exc).__name__}")  # details stay on the job row
    with get_session_factory()() as db:
        try:
            from app.modules.billing.stripe import invoice_due

            n = invoice_due(db)
            if n:
                log.info("invoices.created", count=n)
        except Exception as exc:  # noqa: BLE001
            db.rollback()
            log.warning("invoices.failed", error=f"{type(exc).__name__}: {exc}")
    with get_session_factory()() as db:
        try:
            from app.modules.ambassadors.service import release_held

            n = release_held(db)
            db.commit()
            if n:
                log.info("commission.released", count=n)
        except Exception as exc:  # noqa: BLE001
            db.rollback()
            log.warning("commission.release_failed", error=f"{type(exc).__name__}: {exc}")
    with get_session_factory()() as db:
        try:
            from app.modules.sales import search as sales_search

            if get_settings().sales_outbound_mode != "off":
                n = sales_search.run_due(db)
                if n:
                    log.info("sales.search_steps", count=n)
                refreshed = sales_search.daily_refresh_due(db)
                if refreshed:
                    log.info("sales.google_refresh", **refreshed)
        except Exception as exc:  # noqa: BLE001
            db.rollback()
            log.warning("sales.search_failed", error=f"{type(exc).__name__}: {exc}")
    with get_session_factory()() as db:
        try:  # sales retention: daily from 03:00 Copenhagen time, also when the channel is off
            from datetime import datetime
            from zoneinfo import ZoneInfo

            from app.modules.sales.privacy import run_retention

            local = datetime.now(ZoneInfo("Europe/Copenhagen"))
            if local.hour >= 3 and _RETENTION_RAN.get("day") != local.date():
                run_retention(db)
                from app.modules.telephony.call_recordings import run_retention as calls_retention

                calls_retention(db)  # customers' own recordings, after their number's retention
                _RETENTION_RAN["day"] = local.date()
        except Exception as exc:  # noqa: BLE001
            db.rollback()
            log.warning("sales.retention_failed", error=f"{type(exc).__name__}: {exc}")
    with get_session_factory()() as db:
        try:  # GDPR: support files of deleted tickets/workspaces (queued by the database, app/models/support.py)
            from app.modules.support.attachments import sweep_deletions

            n = sweep_deletions(db)
            if n:
                log.info("support.files_deleted", count=n)
        except Exception as exc:  # noqa: BLE001
            db.rollback()
            log.warning("support.files_delete_failed", error=f"{type(exc).__name__}")
    with get_session_factory()() as db:
        try:  # Dialogbot Privat: release reservations of calls that never got a report
            from app.modules.privat.calls import sweep_stale
            from app.modules.privat.lookup_limits import prune

            prune(db)  # rate-limit rows older than two days
            from app.modules.privat.gdpr import purge_expired as purge_exports

            purge_exports(db)  # «Eksportér mine data»: expired links lose their content
            from app.modules.privat import rules as privat_rules

            today = privat_rules.local(privat_rules.now()).date()
            if _RETENTION_RAN.get("privat_transcripts") != today:
                from app.modules.privat.gdpr import purge_transcripts

                purge_transcripts(db)  # raw call transcripts after 90 days (ours and Vapi's copy), once a day
                _RETENTION_RAN["privat_transcripts"] = today
            from app.modules.browser.lookup import scrub_expired
            from app.modules.privat.places import scrub_cached

            scrub_cached(db)  # Google content older than GOOGLE_PLACES_CACHE_DAYS (place_id is kept)
            scrub_expired(db)  # ... also in the cached business lookups of the assistant's booking
            n = sweep_stale(db)
            if n:
                log.info("privat.calls_released", count=n)
        except Exception as exc:  # noqa: BLE001
            db.rollback()
            log.warning("privat.sweep_failed", error=f"{type(exc).__name__}: {exc}")
    with get_session_factory()() as db:
        try:  # Fødselsdage and Regninger: once per birthday / due date, from 08:00 Copenhagen time
            from app.modules.privat import app_kit, bills, birthdays, car

            n = birthdays.send_due(db) + bills.send_due(db) + car.send_due(db)
            n += app_kit.send_due(db)   # the household apps (Abonnementer, Garanti, Fest, Flytning, Kæledyr, Hus …)
            from app.modules.privat import parcels

            n += parcels.poll(db)  # Pakker: each parcel at most every 2 hours
            db.commit()
            if n:
                log.info("privat.app_reminders", count=n)
        except Exception as exc:  # noqa: BLE001
            db.rollback()
            log.warning("privat.birthdays_failed", error=f"{type(exc).__name__}: {exc}")
    with get_session_factory()() as db:
        try:  # demo calls queued before 12/11 (nothing new is queued): rung at their time or dropped when stale
            from app.modules.sales.service import place_due
            from app.modules.sales.verification import purge as purge_codes

            purge_codes(db)  # SMS-code rows (the visitor's number) after two days
            from app.modules.customer.service import purge as purge_customer

            purge_customer(db)  # customers' SMS-code rows after two days, links 30 days after they expired
            db.commit()
            n = place_due(db)
            if n:
                log.info("sales.demo_calls_placed_from_queue", count=n)
        except Exception as exc:  # noqa: BLE001
            db.rollback()
            log.warning("sales.demo_queue_failed", error=f"{type(exc).__name__}: {exc}")
    with get_session_factory()() as db:
        try:  # quiz-funnel drafts nobody verified within seven days
            from app.modules.funnel.service import purge_expired

            n = purge_expired(db)
            if n:
                log.info("funnel.drafts_purged", count=n)
        except Exception as exc:  # noqa: BLE001
            db.rollback()
            log.warning("funnel.purge_failed", error=f"{type(exc).__name__}: {exc}")
    with get_session_factory()() as db:
        try:
            from app.modules.social.service import run_due as run_social

            n = run_social(db)
            if n:
                log.info("social.posts_attempted", count=n)
        except Exception as exc:  # noqa: BLE001
            db.rollback()
            log.warning("social.failed", error=f"{type(exc).__name__}: {exc}")


def sync_calendars(db, max_age_minutes: int = 15) -> int:
    """Refresh busy time from connected iCal calendars that are older than `max_age_minutes`."""
    from datetime import UTC, datetime, timedelta

    from sqlalchemy import or_, select

    from app.models import BookingSettings
    from app.modules.bookings.service import sync_busy

    cutoff = datetime.now(UTC) - timedelta(minutes=max_age_minutes)
    rows = db.scalars(select(BookingSettings).where(BookingSettings.busy_ics_url.is_not(None),
                                                    or_(BookingSettings.busy_synced_at.is_(None),
                                                        BookingSettings.busy_synced_at < cutoff))
                      .with_for_update(skip_locked=True).limit(50)).all()
    for s in rows:
        sync_busy(db, s)
    db.commit()
    return len(rows)


def main() -> None:
    s = get_settings()
    configure_logging(s.log_level)
    wid = _worker_id()
    log.info("worker.start", worker_id=wid, env=s.app_env)
    with get_session_factory()() as db:
        db.execute(text("select 1"))
    next_schedule = 0.0
    while True:
        if time.monotonic() >= next_schedule:
            run_schedules()
            next_schedule = time.monotonic() + SCHEDULE_EVERY_SECONDS
        ev = process_once(wid)
        if ev is None:
            time.sleep(s.worker_poll_seconds)
        else:
            log.info("outbox.processed", event_id=str(ev.id), event_type=ev.event_type, status=ev.status,
                     attempts=ev.attempts)


if __name__ == "__main__":
    main()
