"""Replies to cold e-mails, and the other Resend events that concern outreach.

The outreach inboxes (OUTREACH_SENDER_INBOXES, e.g. rene@hello.dialogbot.app) have no mailbox behind them: Resend
receives for the domain and posts `email.received` to the one Resend webhook this API has (/webhooks/resend). That
endpoint hands every verified event here, so replies need no second endpoint and no second signing secret.

- A reply to an outreach inbox stops the sequence for the sender, and a copy goes to OUTREACH_REPLY_FORWARD_TO, so
  a person reads it. The Resend account is shared: mail to any other address is not ours and is left alone.
- A bounce or a complaint about an address that is an outreach lead suppresses it for good.

Forwarding never fails the webhook: Resend would retry, and the reply is stored in Resend either way. What happened
is written to the outreach log.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session as OrmSession

from app.config import get_settings
from app.models import OutreachLead, OutreachLog
from app.modules.outreach import suppression
from app.modules.outreach.agents.dispatcher import DispatcherAndWebhookHandler, normalize_resend

RECEIVED_URL = "https://api.resend.com/emails/receiving/{id}"
SEND_URL = "https://api.resend.com/emails"
MAX_BODY = 20_000


def _bare(addr: object) -> str:
    a = str(addr or "")
    if "<" in a:
        a = a.split("<", 1)[1].rstrip("> ")
    return suppression.norm(a)


def _our_inbox(to: object) -> str | None:
    """The outreach inbox this mail was sent to. Any address on an inbox's domain counts (a reply may go to
    another local part), but the copy is always sent from a configured inbox."""
    inboxes = get_settings().outreach_inboxes
    domains = {i.rsplit("@", 1)[-1]: i for i in inboxes}
    for addr in (to if isinstance(to, list) else [to]):
        a = _bare(addr)
        if a in inboxes:
            return a
        if (hit := domains.get(a.rsplit("@", 1)[-1])):
            return hit
    return None


def _api_key() -> str | None:
    s = get_settings()
    return s.outreach_resend_api_key or s.resend_api_key


def fetch_body(email_id: str) -> dict:
    """The received e-mail from Resend's Receiving API (the webhook carries metadata only)."""
    import httpx

    r = httpx.get(RECEIVED_URL.format(id=email_id), timeout=15.0, headers={"Authorization": f"Bearer {_api_key()}"})
    if r.status_code >= 400:
        raise RuntimeError(f"resend {r.status_code}: {r.text[:200]}")
    out = r.json()
    return out if isinstance(out, dict) else {}


def forward(*, inbox: str, sender: str, subject: str, email_id: str | None) -> str:
    """Send a copy of the reply to OUTREACH_REPLY_FORWARD_TO. Returns "forwarded", "off" or "failed: …"."""
    import httpx

    s = get_settings()
    to = suppression.norm(s.outreach_reply_forward_to or "")
    if not to or not _api_key():
        return "off"
    text = ""
    try:
        if email_id:
            mail = fetch_body(email_id)
            text = str(mail.get("text") or "").strip()
            subject = str(mail.get("subject") or subject)
    except Exception as e:  # noqa: BLE001 – the copy still goes out, without the body
        text = f"(The text could not be fetched from Resend: {str(e)[:120]}. Read it under Emails → Receiving.)"
    body = (f"Reply to a cold e-mail, received on {inbox}.\nFrom: {sender}\nSubject: {subject}\n"
            f"The follow-ups to this address are stopped. Answer by replying to this e-mail.\n\n"
            f"{'-' * 40}\n{text[:MAX_BODY] or '(no text part)'}")
    try:
        r = httpx.post(SEND_URL, timeout=15.0,
                       headers={"Authorization": f"Bearer {_api_key()}",
                                **({"Idempotency-Key": f"outreach-reply-{email_id}"} if email_id else {})},
                       json={"from": f"{s.outreach_sender_name} replies <{inbox}>", "to": [to], "reply_to": sender,
                             "subject": f"Reply: {subject}"[:200], "text": body})
        if r.status_code >= 400:
            return f"failed: resend {r.status_code}"
    except Exception as e:  # noqa: BLE001
        return f"failed: {str(e)[:120]}"
    return "forwarded"


def on_resend_event(db: OrmSession, payload: dict) -> str:
    """Apply one verified, not-seen-before Resend event to outreach. Returns what was done."""
    if get_settings().outreach_mode == "off":
        return "ignored"
    ev = normalize_resend(payload)
    if ev is None:
        return "ignored"
    event, email = ev[0], suppression.norm(ev[1])
    data = payload.get("data") or {}
    handler = DispatcherAndWebhookHandler(db)
    if event == "reply":
        inbox = _our_inbox(data.get("to") or [])
        if inbox is None or email in get_settings().outreach_inboxes:
            return "ignored"
        result = handler.handle_event("reply", email, source="resend")
        fwd = forward(inbox=inbox, sender=email, subject=str(data.get("subject") or "")[:200],
                      email_id=str(data.get("email_id") or "") or None)
        lead_id = db.scalar(select(OutreachLead.id).where(OutreachLead.email_normalized == email))
        db.add(OutreachLog(lead_id=lead_id, kind="webhook", outcome="reply_forward",
                           detail={"result": fwd, "inbox": inbox}))
        return result
    if db.scalar(select(OutreachLead.id).where(OutreachLead.email_normalized == email)) is None:
        return "ignored"  # a bounce on a system e-mail, or another project's mail on the shared account
    return handler.handle_event(event, email, source="resend")
