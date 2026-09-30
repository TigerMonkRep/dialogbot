"""In-memory doubles for every connector (CONNECTORS_PROVIDER=fake, dev/test only).

They behave like the real providers as far as the rest of the app can tell – events are stored, SMS are recorded,
webhooks are "delivered" – but every result is marked simulated, and nothing leaves the process. Tests inspect and
reset `WORLD`. `fail_next` makes the next matching call raise, to exercise error paths and retries.
"""
from __future__ import annotations

import itertools
import threading
from dataclasses import dataclass, field
from datetime import UTC, datetime

from app.modules.integrations.connectors.base import ActionError


@dataclass
class FakeWorld:
    events: dict[str, dict] = field(default_factory=dict)  # event id -> {calendar, start, end, title, description}
    sms: list[dict] = field(default_factory=list)
    webhooks: list[dict] = field(default_factory=list)  # delivered posts
    fail_next: set[str] = field(default_factory=set)  # op names that fail once: "calendar", "sms", "webhook", "oauth"
    fail_webhook_times: int = 0  # the next N webhook deliveries fail (retry tests)
    oauth_email: str = "ejer@fjordgulv.example"
    seq: itertools.count = field(default_factory=lambda: itertools.count(1))
    lock: threading.Lock = field(default_factory=threading.Lock)

    def reset(self) -> None:
        self.events.clear()
        self.sms.clear()
        self.webhooks.clear()
        self.fail_next.clear()
        self.fail_webhook_times = 0
        self.oauth_email = "ejer@fjordgulv.example"

    def _maybe_fail(self, op: str) -> None:
        if op in self.fail_next:
            self.fail_next.discard(op)
            raise ActionError(f"{op}: leverandøren svarede ikke (simuleret)", code="provider_unavailable", retryable=True)


WORLD = FakeWorld()


class FakeCalendarClient:
    """Same interface as the Google/Microsoft clients in connectors/calendar.py."""

    simulated = True

    def __init__(self, calendar: str):
        self.calendar = calendar  # e.g. "google:<workspace>"

    def info(self) -> dict:
        WORLD._maybe_fail("calendar")
        return {"calendar_id": "primary", "name": "Kalender (simuleret)", "email": WORLD.oauth_email}

    def busy(self, frm: datetime, to: datetime) -> list[tuple[datetime, datetime]]:
        WORLD._maybe_fail("calendar")
        return [(e["start"], e["end"]) for e in WORLD.events.values()
                if e["calendar"] == self.calendar and e["end"] > frm and e["start"] < to]

    def create_event(self, *, title: str, start: datetime, end: datetime, description: str = "") -> str:
        WORLD._maybe_fail("calendar")
        with WORLD.lock:
            eid = f"fake-ev-{next(WORLD.seq)}"
            WORLD.events[eid] = {"calendar": self.calendar, "start": start, "end": end, "title": title,
                                 "description": description, "created_at": datetime.now(UTC)}
        return eid

    def update_event(self, event_id: str, *, start: datetime, end: datetime) -> None:
        WORLD._maybe_fail("calendar")
        ev = WORLD.events.get(event_id)
        if ev is None:
            raise ActionError("Aftalen findes ikke længere i kalenderen", code="event_not_found")
        ev["start"], ev["end"] = start, end

    def delete_event(self, event_id: str) -> None:
        WORLD._maybe_fail("calendar")
        WORLD.events.pop(event_id, None)


def fake_oauth_tokens(connector: str) -> dict:
    """What the provider's token endpoint would answer. The id_token carries the account e-mail as a label."""
    import base64
    import json

    WORLD._maybe_fail("oauth")
    payload = base64.urlsafe_b64encode(json.dumps({"email": WORLD.oauth_email}).encode()).decode().rstrip("=")
    return {"access_token": f"fake-access-{connector}-{next(WORLD.seq)}", "refresh_token": f"fake-refresh-{connector}",
            "token_type": "Bearer", "expires_in": 3600, "id_token": f"e30.{payload}.sig"}


def fake_send_sms(*, sender: str, to: str, body: str, workspace_id: str) -> str:
    WORLD._maybe_fail("sms")
    with WORLD.lock:
        sid = f"SMfake{next(WORLD.seq):026d}"
        WORLD.sms.append({"sid": sid, "from": sender, "to": to, "body": body, "workspace_id": workspace_id})
    return sid


def fake_deliver_webhook(*, url: str, body: bytes, headers: dict) -> int:
    """Returns the simulated HTTP status; raises like a network failure when told to."""
    if WORLD.fail_webhook_times > 0:
        WORLD.fail_webhook_times -= 1
        raise ActionError("webhook: modtageren svarede 503 (simuleret)", code="provider_unavailable", retryable=True)
    with WORLD.lock:
        WORLD.webhooks.append({"url": url, "body": body.decode(), "headers": dict(headers), "at": datetime.now(UTC)})
    return 200
