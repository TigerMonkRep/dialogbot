"""Code SMS sent from the worker, never inside the request (F-VER1112-01 rest, Fürster 13/11: «A»).

The public code doors – «Ring mig op nu» (app/modules/sales/verification.py) and the customer's code in the web chat
and on the booking link (app/modules/customer/service.py, W04/W13) – answer 202 `code_sent` after the limits and a
queued `sms.code` outbox event, for EVERY number. The request never waits for Twilio, so the answer and its timing
are the same for a number on the do-not-call list (which never gets an SMS) and any other number, and a Twilio
failure can no longer turn into a 502 that only ordinary numbers get. A failed delivery is retried by the outbox
(backoff, `outbox.handler_failed` in the log); the page offers «Fik du ikke koden? Send igen».

The event carries the verification row's id and the code encrypted with CREDENTIALS_KEY (app/core/crypto.py – the
worker does not share the API's SECRET_KEY), bound to that row; the number is read from the row. After the attempt
the code is removed from the payload. Each SMS sent for a workspace is one `sms_usage` row (keyed on the event, so a
redelivered event never sends twice) – the business pays for its customers' codes; SMS carry no price yet."""
from __future__ import annotations

import base64
import secrets
import uuid
from datetime import datetime

import structlog
from sqlalchemy import select
from sqlalchemy.orm import Session as OrmSession

from app.core import crypto
from app.core.outbox import enqueue
from app.models import CustomerVerification, DemoCallVerification, OutboxEvent, SmsUsage, Workspace

EVENT = "sms.code"
KINDS = ("demo", "customer")
log = structlog.get_logger("dialogbot.sms_codes")


def _aad(kind: str, vid: uuid.UUID) -> bytes:
    return f"sms-code:{kind}:{vid}".encode()


def queue(db: OrmSession, *, kind: str, verification_id: uuid.UUID, code: str) -> OutboxEvent:
    """Queue the code SMS for a verification row (already flushed). Same work for every number."""
    assert kind in KINDS
    env = crypto.encrypt(code.encode(), aad=_aad(kind, verification_id))
    # workspace_id stays empty: the code belongs to a conversation that is still going on, and an operator's pause of
    # the workspace (M03) holds its outbound jobs, not the chat (app/core/suspension.py).
    return enqueue(db, event_type=EVENT, dedupe_key=f"sms-code:{kind}:{verification_id}",
                   payload={"kind": kind, "verification_id": str(verification_id), "key_version": env.key_version,
                            "code": base64.b64encode(env.blob).decode()})


def _code(ev: OutboxEvent, kind: str, vid: uuid.UUID) -> str:
    p = ev.payload
    env = crypto.Envelope(p["key_version"], base64.b64decode(p["code"]))
    return crypto.decrypt(env, aad=_aad(kind, vid)).decode()


def _scrub(ev: OutboxEvent, outcome: str) -> None:
    ev.payload = {k: v for k, v in ev.payload.items() if k not in ("code", "key_version")} | {"outcome": outcome}


def segments(body: str) -> int:
    """SMS parts for a GSM-7 text (the code texts are GSM-7): 160 characters in one, 153 per part above that."""
    return 1 if len(body) <= 160 else -(-len(body) // 153)


def _now(kind: str) -> datetime:
    """The clock of the door that issued the code (tests move those)."""
    if kind == "demo":
        from app.modules.sales import verification

        return verification._now()
    from app.modules.customer import service as customer

    return customer._now()


def handle(db: OrmSession, ev: OutboxEvent) -> None:
    """Worker handler for `sms.code`. Raises on a failed send so the outbox retries; an expired, used or deleted
    code is dropped, and a do-not-call number (demo door) gets nothing and its code can never match."""
    from app.modules.integrations.connectors import sms
    from app.modules.privat import phone as privat_phone
    from app.worker.runner import HandlerError

    p = ev.payload
    if "code" not in p:
        return  # already handled (the payload is scrubbed after the attempt)
    if db.scalar(select(SmsUsage.id).where(SmsUsage.outbox_event_id == ev.id)) is not None:
        _scrub(ev, "sent")
        return
    kind, vid = p["kind"], uuid.UUID(p["verification_id"])
    model = DemoCallVerification if kind == "demo" else CustomerVerification
    v = db.get(model, vid)
    if v is None or v.verified_at is not None or v.expires_at <= _now(kind):
        _scrub(ev, "expired")
        return
    if kind == "demo":
        from app.modules.sales import service as sales
        from app.modules.sales import verification

        ws = sales.sales_workspace(db)
        if sales._blocked(db, ws, v.phone):
            # Do-not-call: no SMS, and the stored hash is replaced so no code can ever match this row.
            v.code_hash = verification._code_hash(v.id, v.phone, secrets.token_hex(16))
            _scrub(ev, "suppressed")
            return
        sender, body, purpose = verification.SENDER, verification.sms_text(_code(ev, kind, vid), v.language), \
            "demo_call_code"
    else:
        from app.modules.customer import service as customer
        from app.modules.integrations import sms_templates

        ws = db.get(Workspace, v.workspace_id)
        if ws is None:
            _scrub(ev, "expired")
            return
        sender = customer._sender(db, ws)
        body = sms_templates.code(ws.name, _code(ev, kind, vid), sms.caller_language(db, ws))
        purpose = v.purpose
    simulated = privat_phone._simulated()
    try:
        ref = sms.send(db, ws, sender=sender, to=v.phone, body=body, simulated=simulated)
    except Exception as e:  # noqa: BLE001 - ApiError, or ActionError from the adapter
        log.warning("sms_code.failed", kind=kind, purpose=purpose, workspace_id=str(ws.id), attempt=ev.attempts,
                    error=getattr(e, "code", type(e).__name__))
        raise HandlerError(f"sms not sent: {getattr(e, 'code', type(e).__name__)}") from e
    db.add(SmsUsage(workspace_id=ws.id, purpose=purpose, segments=segments(body), simulated=simulated,
                    provider_ref=(ref or None) and str(ref)[:64], outbox_event_id=ev.id))
    _scrub(ev, "sent")
