"""Customer support (H01) and the operators' support queue (M06).

A business workspace's members open a ticket (subject, category, first message, attachments) and follow it at
/app/support/<number>; Dialogbot's platform operators work the queue at /app/operator/admin/support: assign, set
priority and status, write replies the customer sees and internal notes the customer never sees (DB-016).

- `number` counts per workspace (1, 2, 3 …) so the customer's URL never reveals another workspace's ticket count.
- `SupportMessage.visibility`: 'public' (customer and operators) or 'internal' (operators only). A customer's own
  message is always public (check constraint). Every customer serializer filters on visibility='public'.
- `SupportAttachment` belongs to one message and follows its visibility. The bytes live in private object storage
  (app/modules/voices/storage, key ws/<workspace_id>/support/…) and are only served through authorised endpoints.
- `priority` and `assigned_to` are the operators' triage fields; the customer's view does not include them."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.identity import ts_now, uuid_pk

SUPPORT_STATUSES = ("open", "in_progress", "waiting_customer", "resolved")
SUPPORT_CATEGORIES = ("reception", "campaigns", "calendar", "billing", "other")
SUPPORT_PRIORITIES = ("low", "normal", "high", "critical")


def _in(col: str, values: tuple[str, ...]) -> str:
    return f"{col} in ({', '.join(repr(v) for v in values)})"


class SupportTicket(Base):
    __tablename__ = "support_tickets"
    __table_args__ = (
        UniqueConstraint("workspace_id", "number", name="uq_support_tickets_workspace_number"),
        CheckConstraint(_in("status", SUPPORT_STATUSES), name="ck_support_tickets_status"),
        CheckConstraint(_in("category", SUPPORT_CATEGORIES), name="ck_support_tickets_category"),
        CheckConstraint(_in("priority", SUPPORT_PRIORITIES), name="ck_support_tickets_priority"),
        Index("ix_support_tickets_status_updated", "status", "updated_at"),
        Index("ix_support_tickets_assigned", "assigned_to"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    number: Mapped[int] = mapped_column(Integer, nullable=False)
    subject: Mapped[str] = mapped_column(String(160), nullable=False)
    category: Mapped[str] = mapped_column(String(20), nullable=False, default="other")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="open")
    priority: Mapped[str] = mapped_column(String(10), nullable=False, default="normal", server_default="normal")
    context_path: Mapped[str] = mapped_column(String(200), nullable=False, default="", server_default="")
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    assigned_to: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = ts_now()
    updated_at: Mapped[datetime] = ts_now()
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class SupportMessage(Base):
    __tablename__ = "support_messages"
    __table_args__ = (
        CheckConstraint("author_kind in ('customer','operator')", name="ck_support_messages_author_kind"),
        CheckConstraint("visibility in ('public','internal')", name="ck_support_messages_visibility"),
        CheckConstraint("author_kind = 'operator' or visibility = 'public'", name="ck_support_messages_customer_public"),
        Index("ix_support_messages_ticket_created", "ticket_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    ticket_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("support_tickets.id", ondelete="CASCADE"), nullable=False)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    author_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    author_kind: Mapped[str] = mapped_column(String(10), nullable=False)
    visibility: Mapped[str] = mapped_column(String(10), nullable=False, default="public")
    body: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = ts_now()


class SupportAttachment(Base):
    __tablename__ = "support_attachments"
    __table_args__ = (Index("ix_support_attachments_message", "message_id"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    ticket_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("support_tickets.id", ondelete="CASCADE"), nullable=False)
    message_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("support_messages.id", ondelete="CASCADE"), nullable=False)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    filename: Mapped[str] = mapped_column(String(120), nullable=False)
    content_type: Mapped[str] = mapped_column(String(40), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(250), nullable=False)
    uploaded_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = ts_now()


class StorageDeletion(Base):
    """An object in private storage that must be removed because its row is gone (GDPR, Fürster 13/11: a deleted
    workspace or ticket takes its support files with it). Filled by the database itself – an AFTER DELETE trigger on
    support_attachments (migration d1a7c3e5f9b2) – so every way a row can disappear (a ticket deleted, a workspace
    deleted and the delete cascading, a privat account deleted) queues its file. The worker removes the objects
    (app/modules/support/attachments.sweep_deletions) and marks the row done."""

    __tablename__ = "storage_deletions"
    __table_args__ = (Index("ix_storage_deletions_pending", "done_at", "created_at"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    storage_key: Mapped[str] = mapped_column(String(250), nullable=False)
    reason: Mapped[str] = mapped_column(String(40), nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    last_error: Mapped[str | None] = mapped_column(String(200))
    done_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = ts_now()
