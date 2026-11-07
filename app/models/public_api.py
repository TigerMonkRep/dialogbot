"""Public API (api.dialogbot.app/v1): per-workspace API keys and outgoing webhook endpoints.

See docs/public-api.md. Keys are opaque bearer tokens (`dbk_live_…` / `dbk_test_…`); like sessions, only the SHA-256
digest is stored. A webhook endpoint's signing secret is envelope-encrypted with app/core/crypto (the worker needs the
plaintext to sign deliveries) and is shown to the customer exactly once, when the endpoint is created.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, LargeBinary, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.identity import ts_now, uuid_pk

KEY_PREFIXES = ("dbk_live_", "dbk_test_")


class ApiKey(Base):
    __tablename__ = "api_keys"
    __table_args__ = (
        CheckConstraint("prefix in ('dbk_live_','dbk_test_')", name="ck_api_keys_prefix"),
        Index("ix_api_keys_workspace", "workspace_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    prefix: Mapped[str] = mapped_column(String(16), nullable=False)
    # The last four characters of the plaintext key, so a customer can tell their keys apart in the list.
    last4: Mapped[str] = mapped_column(String(4), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    scopes: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = ts_now()
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))

    @property
    def is_active(self) -> bool:
        return self.revoked_at is None


class WebhookEndpoint(Base):
    """Where the public API posts signed events for one workspace. Deliveries are outbox events
    (event_type `public_webhook.deliver`, one per endpoint and event); the endpoint row keeps the running state
    (last delivery, consecutive failures) and is switched off after too many consecutive failures."""

    __tablename__ = "webhook_endpoints"
    __table_args__ = (Index("ix_webhook_endpoints_workspace", "workspace_id", "created_at"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    # Signing secret ("whsec_…"), envelope-encrypted (app/core/crypto); the plaintext is returned once at creation.
    secret_blob: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    key_version: Mapped[str] = mapped_column(String(16), nullable=False)
    events: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_by_key_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("api_keys.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = ts_now()
    last_delivery_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(String(300))
    # Consecutive failed deliveries; reset to 0 by a success. At PUBLIC_API_WEBHOOK_DISABLE_AFTER the endpoint is
    # switched off (active=false, disabled_at, disabled_reason) and must be re-enabled by the customer.
    failure_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    disabled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    disabled_reason: Mapped[str | None] = mapped_column(String(300))
