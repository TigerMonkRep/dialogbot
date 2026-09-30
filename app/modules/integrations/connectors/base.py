"""Connector and action declarations.

A *connector* is one of the customer's systems (their Google Calendar, a Zapier webhook, SMS). It declares the
*actions* the assistant may perform there – each with a Danish description, a JSON schema for input and output,
and whether the person on the phone must confirm before it runs. The tool-builder (app/modules/integrations/actions)
turns the actions of every `connected` connector into function tools for the phone assistant and the webchat, and
routes each call back to the connector's adapter after validating the input against the schema.

Adapters come in two flavours behind the same interface: the real one (HTTP calls to the provider) and a fake for
dev/test whose every result is marked `simulated`. Nothing in this module touches the database or logs secrets.
"""
from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal, Protocol

ConnectorStatus = Literal["not_connected", "connected", "error", "not_implemented"]
AuthKind = Literal["oauth", "api_key", "secret", "builtin"]
Availability = Literal["ready", "coming", "via_zapier"]
Category = Literal["calendar", "messaging", "automation", "crm", "accounting", "booking", "field_service", "staffing"]


class ActionError(Exception):
    """A failed action, with a plain-Danish message the assistant may relay to the customer."""

    def __init__(self, message: str, *, code: str = "action_failed", retryable: bool = False):
        super().__init__(message)
        self.message = message
        self.code = code
        self.retryable = retryable


class ActionRefused(ActionError):
    """The adapter refused to act (not confirmed, outside policy, disabled by the customer)."""

    def __init__(self, message: str, *, code: str = "action_refused"):
        super().__init__(message, code=code)


@dataclass(frozen=True)
class ActionSpec:
    name: str  # tool name the model calls, snake_case, Danish (e.g. "opret_booking")
    label: str  # short Danish label for the inbox ("Booket tid i kalenderen")
    description: str  # what the model reads: when to use it, what to say first
    input_schema: dict  # JSON schema (object); validated before the adapter runs
    output_schema: dict  # JSON schema of the adapter's result
    confirm: bool = False  # the person in the call/chat must say yes first; input then carries bekraeftet=true
    channels: tuple[str, ...] = ("phone", "webchat")
    # Renders the customer-facing/inbox sentence from validated input + output (never raises).
    summarize: Callable[[dict, dict], str] | None = None


@dataclass
class RunContext:
    """What the adapter may know about the situation an action runs in. Never carries credentials."""

    workspace_id: uuid.UUID
    channel: str  # phone | webchat | test | system
    conversation_id: uuid.UUID | None = None
    caller_phone: str | None = None
    caller_name: str | None = None
    provider_call_id: str | None = None
    user_id: uuid.UUID | None = None  # a person running a test action
    now: datetime | None = None
    tz: str = "Europe/Copenhagen"


@dataclass
class ActionResult:
    output: dict
    label: str = ""  # Danish one-liner; falls back to ActionSpec.summarize / label
    provider_ref: str | None = None
    simulated: bool = False


class Adapter(Protocol):
    """One connected instance: knows the workspace's decrypted secret and config for the duration of a call."""

    simulated: bool

    def test_connection(self) -> dict:
        """A real round-trip to the provider. Returns non-secret facts to show the customer (e.g. calendar name)."""
        ...

    def run(self, action: str, data: dict, ctx: RunContext) -> ActionResult: ...


@dataclass(frozen=True)
class ConnectorSpec:
    key: str
    label: str
    description: str  # Danish, shown in the catalogue
    category: Category
    auth_kind: AuthKind
    availability: Availability = "ready"
    actions: tuple[ActionSpec, ...] = ()
    # JSON schema of the non-secret configuration the customer edits (webhook URL, sender name …).
    config_schema: dict = field(default_factory=dict)
    # Secret fields the customer types (api_key / secret connectors); OAuth connectors have none.
    secret_fields: tuple[str, ...] = ()
    # Provider events the connector receives (webhook sinks) – informational for the catalogue.
    events: tuple[str, ...] = ()
    # Why the connector cannot be offered in this deployment (None = it can). Evaluated at request time.
    unavailable_reason: Callable[[], str | None] = lambda: None
    # Builds the adapter for one connection: (db, workspace_id, secret dict or None, config dict, simulated) -> Adapter
    adapter: Callable[..., Adapter] | None = None
    docs_url: str = ""
    # Systems reachable through Zapier/Make instead of a native connector (shown as "via Zapier").
    zapier_note: str = ""

    def action(self, name: str) -> ActionSpec | None:
        return next((a for a in self.actions if a.name == name), None)


def obj(properties: dict[str, Any], required: list[str] | None = None, **extra: Any) -> dict:
    """Small helper for JSON-schema objects; additionalProperties is always false so the model cannot smuggle
    unknown fields into an adapter."""
    return {"type": "object", "properties": properties, "required": required or [], "additionalProperties": False,
            **extra}
