"""Dialogbot Privat: a personal assistant for private Danish consumers.

Everything here belongs to ONE personal workspace (workspaces.kind = 'personal'), owned by exactly one user through
`private_profiles`. Business endpoints never resolve a personal workspace, and the private endpoints only ever
resolve the caller's own (app/modules/privat/deps.py).
"""
from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.identity import ts_now, uuid_pk

PRIVATE_TASK_KINDS = ("list", "reminder", "call")
PRIVATE_TASK_STATUSES = ("awaiting_user", "draft", "planned", "in_progress", "awaiting_business", "done", "declined")
CREDIT_KINDS = ("grant", "purchase", "reserve", "capture", "release", "spend", "sponsor", "referral", "convert")
PRIVATE_CALL_STATUSES = ("proposed", "approved", "scheduled", "dialling", "in_progress", "unknown", "answered", "no_answer",
                         "failed", "declined")


class PrivateProfile(Base):
    """The one personal workspace of a user, plus the verified mobile number the assistant may share."""

    __tablename__ = "private_profiles"

    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True)
    phone_e164: Mapped[str | None] = mapped_column(String(20))
    phone_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # A pending SMS code: only an HMAC of it is stored; 10 minutes, at most 5 attempts.
    phone_pending_e164: Mapped[str | None] = mapped_column(String(20))
    phone_code_hash: Mapped[str | None] = mapped_column(String(64))
    phone_code_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    phone_code_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    phone_code_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Where to look for businesses – only what the user gave themselves (PATCH /privat/me/location).
    location_city: Mapped[str | None] = mapped_column(String(100))
    location_postcode: Mapped[str | None] = mapped_column(String(10))
    location_lat: Mapped[float | None] = mapped_column(Float)
    location_lng: Mapped[float | None] = mapped_column(Float)
    # The private calendar subscription link (Kalender app): only a SHA-256 of the secret token is kept; the link is
    # shown once when made and a new one replaces it. Null = no link.
    calendar_feed_token_hash: Mapped[str | None] = mapped_column(String(64), unique=True)
    calendar_feed_created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # What the assistant is called (app/modules/privat/naming.py). Null = «Peter».
    assistant_name: Mapped[str | None] = mapped_column(String(30))
    # How the texts refer to it: han | hun | den. Null = «han» for Peter, «den» for any other name (never guessed).
    assistant_pronoun: Mapped[str | None] = mapped_column(String(4))
    created_at: Mapped[datetime] = ts_now()


class PrivateTask(Base):
    __tablename__ = "private_tasks"
    __table_args__ = (
        CheckConstraint("kind in ('list','reminder','call')", name="ck_private_tasks_kind"),
        CheckConstraint("status in ('awaiting_user','draft','planned','in_progress','awaiting_business','done',"
                        "'declined')", name="ck_private_tasks_status"),
        CheckConstraint("paid_by in ('free','balance','sponsor','none','call','plan')", name="ck_private_tasks_paid_by"),
        CheckConstraint("list_type is null or list_type in ('shopping','wishlist','todo')",
                        name="ck_private_tasks_list_type"),
        CheckConstraint("share_mode is null or share_mode in ('group','wishlist')", name="ck_private_tasks_share_mode"),
        Index("ix_private_tasks_ws_created", "workspace_id", "created_at"),
        Index("ix_private_tasks_ws_free_month", "workspace_id", "free_month"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    # The status the task gets when a draft (task #11+ in a month) is activated.
    pending_status: Mapped[str | None] = mapped_column(String(24))
    next_step: Mapped[str] = mapped_column(Text, nullable=False, default="")
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    remind_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Bumped on every move; part of the reminder's outbox dedupe key so a move creates exactly one new event.
    reminder_version: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    who: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    usage_text: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    # free (one of the month's 10) | balance (3 kr. from the Opkaldssaldo) | sponsor (history only, F-PQ-03) | none (draft, not paid yet) |
    # call (paid with the call: a plan call or an extra call from the Opkaldssaldo) | plan
    # | plan (included in the trial or a subscription: never counts against the free quota)
    paid_by: Mapped[str] = mapped_column(String(16), nullable=False, default="none")
    free_month: Mapped[str | None] = mapped_column(String(7))  # "2026-11" when it used a free task that month
    is_example: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    # Lists: shopping | wishlist | todo (null for other kinds)
    list_type: Mapped[str | None] = mapped_column(String(16))
    # Shared lists: group (everyone adds and ticks, attributed) | wishlist (members reserve; the owner never sees it).
    # Null = not shared. Access ALWAYS goes through private_task_members, never through workspace_id.
    share_mode: Mapped[str | None] = mapped_column(String(16))
    # Wishlists: the list's own look («Design ønskeseddel», wish_design.py): theme key plus the owner's overrides.
    # Null = the default theme. Never HTML/CSS – only validated keys, #RRGGBB colours and a stored cover image.
    design: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = ts_now()
    updated_at: Mapped[datetime] = ts_now()


class PrivateTaskItem(Base):
    __tablename__ = "private_task_items"
    __table_args__ = (Index("ix_private_task_items_task", "task_id", "position"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    task_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("private_tasks.id", ondelete="CASCADE"), nullable=False)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    text: Mapped[str] = mapped_column(String(300), nullable=False)
    done: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    note: Mapped[str | None] = mapped_column(String(500))
    link: Mapped[str | None] = mapped_column(String(1000))
    added_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    done_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    # Wishlists: who said "Jeg køber den". Never shown to the list's owner, and to other members only as "Reserveret".
    reserved_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    # ---- wish details (wishes.py). `text` is the title, `note` the personal note, `link` the product link (kept
    # verbatim, variant parameters included). All optional: an experience or a homemade gift has none of them.
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    price_minor: Mapped[int | None] = mapped_column(BigInteger)  # in the currency's smallest unit (øre)
    currency: Mapped[str | None] = mapped_column(String(3))
    # "shop": read from the shop's structured data at price_fetched_at; "user": typed by the owner. Never live.
    price_source: Mapped[str | None] = mapped_column(String(8))
    price_fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    shop: Mapped[str | None] = mapped_column(String(120))
    size: Mapped[str | None] = mapped_column(String(80))
    color: Mapped[str | None] = mapped_column(String(80))
    variant: Mapped[str | None] = mapped_column(String(120))
    # The stored image (private bucket, wish_images.py): key of the large WebP; the small one sits beside it.
    image_key: Mapped[str | None] = mapped_column(String(200))
    image_origin: Mapped[str | None] = mapped_column(String(8))  # "shop" (imported) | "upload" (the owner's own photo)
    # What the shop's page said, as data: brand, sku, availability, description and the variants it offers.
    details: Mapped[dict | None] = mapped_column(JSONB)
    # «Tillad fællesgave» (the owner's setting). The agreement itself – with its own, frozen target – is
    # private_group_gifts; it belongs to the givers and is never shown to the owner.
    group_gift_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    group_gift_target_minor: Mapped[int | None] = mapped_column(BigInteger)
    # Deleted by the owner while givers had an agreement on it: hidden from the owner, kept for those givers.
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = ts_now()


class PrivateGroupGift(Base):
    """«Deles om en gave»: the givers' agreement on one wish. Coordination of PLEDGES only – no money moves. One
    currency; the target is copied from the wish when the first pledge arrives and never follows later edits.
    status: open | bought (set by the coordinator, never by the sum) | cancelled (the owner removed the wish or
    switched the group gift off; pledges are kept so the givers see what happened). «Fuldt tilsagn» is derived."""

    __tablename__ = "private_group_gifts"
    __table_args__ = (
        CheckConstraint("status in ('open','bought','cancelled')", name="ck_private_group_gifts_status"),
        CheckConstraint("target_minor > 0", name="ck_private_group_gifts_target"),
        Index("uq_private_group_gifts_live_item", "item_id", unique=True,
              postgresql_where="status <> 'cancelled'"),
        Index("ix_private_group_gifts_task", "task_id"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    item_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("private_task_items.id", ondelete="CASCADE"), nullable=False)
    task_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("private_tasks.id", ondelete="CASCADE"), nullable=False)
    target_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="open")
    cancel_reason: Mapped[str | None] = mapped_column(String(32))  # wish_removed | disabled
    coordinator_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    # A handover offered by the coordinator; the role moves only when this person accepts.
    pending_coordinator_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    bought_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = ts_now()
    updated_at: Mapped[datetime] = ts_now()


class PrivateGiftPledge(Base):
    """One giver's pledge on a group gift: at most one row per person (a retry or a double click updates it, never
    adds one). Cancelled pledges keep their row (status) so a later re-join is the same row."""

    __tablename__ = "private_gift_pledges"
    __table_args__ = (
        UniqueConstraint("gift_id", "user_id", name="uq_private_gift_pledges_gift_user"),
        CheckConstraint("amount_minor > 0", name="ck_private_gift_pledges_amount"),
        CheckConstraint("status in ('active','cancelled')", name="ck_private_gift_pledges_status"),
        Index("ix_private_gift_pledges_user", "user_id"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    gift_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("private_group_gifts.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    amount_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    created_at: Mapped[datetime] = ts_now()
    updated_at: Mapped[datetime] = ts_now()


class PrivateTaskMember(Base):
    """The ONLY way to reach a task: every task has its owner here, a shared list also its members."""

    __tablename__ = "private_task_members"
    __table_args__ = (
        UniqueConstraint("task_id", "user_id", name="uq_private_task_members_task_user"),
        CheckConstraint("role in ('owner','editor','viewer')", name="ck_private_task_members_role"),
        Index("ix_private_task_members_user", "user_id"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    task_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("private_tasks.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[datetime] = ts_now()


class PrivateInvite(Base):
    """ONE invitation mechanism for every shareable add-on (and for "try Dialogbot" links): a resource
    (resource_type/resource_id, e.g. "list"/<task id>) shared by its inviter. Only the SHA-256 of the token is
    stored; 30 days; revocable. opened/accepted counters feed the growth numbers."""

    __tablename__ = "private_invites"
    __table_args__ = (
        CheckConstraint("role in ('editor','viewer')", name="ck_private_invites_role"),
        Index("ix_private_invites_resource", "resource_type", "resource_id"),
        Index("ix_private_invites_inviter", "inviter_user_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    # 8 characters (A-Z2-9 without 0/O/1/I/L) for the short link the user texts from their own phone; stored upper-case.
    short_code: Mapped[str] = mapped_column(String(8), nullable=False, unique=True)
    resource_type: Mapped[str] = mapped_column(String(32), nullable=False)
    resource_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    addon_key: Mapped[str | None] = mapped_column(String(40))
    inviter_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    mode: Mapped[str | None] = mapped_column(String(16))
    role: Mapped[str] = mapped_column(String(16), nullable=False, default="editor")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # A personal invite for one person of a saved group (status per person); null for a shared link.
    recipient_group_member_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("private_group_members.id", ondelete="SET NULL"))
    opened_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    accepted_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    created_at: Mapped[datetime] = ts_now()


class PrivateReferral(Base):
    """A NEW user who joined through an invite. One row per invitee for life (unique), so the +3/+3 reward can only
    ever happen once per person."""

    __tablename__ = "private_referrals"
    __table_args__ = (Index("ix_private_referrals_inviter", "inviter_user_id", "accepted_at"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    inviter_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    invitee_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False,
                                                       unique=True)
    invite_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("private_invites.id", ondelete="SET NULL"))
    addon_key: Mapped[str | None] = mapped_column(String(40))
    accepted_at: Mapped[datetime] = ts_now()
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rewarded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # False when the inviter had already had 10 rewards that month (the invitee is rewarded anyway).
    inviter_rewarded: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")


class PrivateTaskEvent(Base):
    __tablename__ = "private_task_events"
    __table_args__ = (Index("ix_private_task_events_task", "task_id", "at"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    task_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("private_tasks.id", ondelete="CASCADE"), nullable=False)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    at: Mapped[datetime] = ts_now()
    text: Mapped[str] = mapped_column(Text, nullable=False)


class PrivateMessage(Base):
    __tablename__ = "private_messages"
    __table_args__ = (
        CheckConstraint("role in ('user','assistant')", name="ck_private_messages_role"),
        CheckConstraint("kind in ('text','task','move','clarify','call_proposal','draft','waiting','addon',"
                        "'share_proposal','booking_proposal')",
                        name="ck_private_messages_kind"),
        Index("ix_private_messages_ws_created", "workspace_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False, default="text")
    text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    task_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("private_tasks.id", ondelete="SET NULL"))
    about_task_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("private_tasks.id", ondelete="SET NULL"))
    before: Mapped[str | None] = mapped_column(String(200))
    after: Mapped[str | None] = mapped_column(String(200))
    # [{id, label, sub, action, ...}] – `action` and its data never leave the server (see service.message_out)
    options: Mapped[list | None] = mapped_column(JSONB)
    links: Mapped[list | None] = mapped_column(JSONB)
    answered_option_id: Mapped[str | None] = mapped_column(String(320))  # e.g. "place:<google place id>"
    addon_key: Mapped[str | None] = mapped_column(String(40))  # kind "addon": the add-on the user is offered
    created_at: Mapped[datetime] = ts_now()


class CreditLedger(Base):
    """The «Opkaldssaldo»: append-only movements in øre (minor units of `currency`, incl. VAT). Balance = SUM(amount).
    An extra call reserves its maximum (-1750) and is settled once: a capture gives back what the call did not cost
    (+ reserve − price), a release gives back everything. `source_ref` is unique, so a replayed webhook or command can
    never move money twice. (Table name from the credits it held until 2026-11-11, migration f3a8c6d2b5e9.)"""

    __tablename__ = "credit_ledger"
    __table_args__ = (
        CheckConstraint("kind in ('grant','purchase','reserve','capture','release','spend','sponsor','referral',"
                        "'convert')", name="ck_credit_ledger_kind"),
        CheckConstraint("currency in ('DKK','SEK','NOK','EUR')", name="ck_credit_ledger_currency"),
        Index("ix_credit_ledger_ws_created", "workspace_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    amount: Mapped[int] = mapped_column(Integer, nullable=False)  # øre (minor units of currency)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="DKK", server_default="DKK")
    source_ref: Mapped[str] = mapped_column(String(200), nullable=False, unique=True)
    task_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("private_tasks.id", ondelete="SET NULL"))
    text: Mapped[str] = mapped_column(String(300), nullable=False, default="")
    created_at: Mapped[datetime] = ts_now()


class PrivateCall(Base):
    """One proposed/approved call to a business on the user's behalf. Fields are locked when the user approves."""

    __tablename__ = "private_calls"
    __table_args__ = (
        CheckConstraint("status in ('proposed','approved','scheduled','dialling','in_progress','unknown','answered',"
                        "'no_answer','failed','declined')", name="ck_private_calls_status"),
        CheckConstraint("paid_via is null or paid_via in ('balance','plan')", name="ck_private_calls_paid_via"),
        CheckConstraint("pitch_outcome is null or pitch_outcome in ('interested','declined','skipped','not_asked')",
                        name="ck_private_calls_pitch_outcome"),
        Index("ix_private_calls_task", "task_id", "created_at"),
        Index("ix_private_calls_ws_approved", "workspace_id", "approved_at"),
        Index("ix_private_calls_business_phone", "business_phone_e164", "expires_at"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    task_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("private_tasks.id", ondelete="CASCADE"), nullable=False)
    business_name: Mapped[str] = mapped_column(String(200), nullable=False)
    business_address: Mapped[str] = mapped_column(String(300), nullable=False, default="")
    # Null when the business has no number we can use yet: the user replies with it in the chat (about_task_id).
    business_phone_e164: Mapped[str | None] = mapped_column(String(20))
    # Where the number came from: google | demo (never dialled) | user
    phone_source: Mapped[str | None] = mapped_column(String(8))
    purpose: Mapped[str] = mapped_column(Text, nullable=False, default="")
    may_ask: Mapped[str] = mapped_column(Text, nullable=False, default="")
    may_agree: Mapped[str] = mapped_column(Text, nullable=False, default="")
    may_not: Mapped[str] = mapped_column(Text, nullable=False, default="")
    window: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    share_phone: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="proposed")
    # answered | no_answer | failed | declined (null while proposed or running)
    result: Mapped[str | None] = mapped_column(String(16))
    # Set at approval: plan (one of the month's plan calls) | balance (an extra call beyond them: its maximum price is
    # reserved on the Opkaldssaldo). Null for calls approved before subscriptions existed (paid like 'balance').
    paid_via: Mapped[str | None] = mapped_column(String(8))
    pool_number: Mapped[str | None] = mapped_column(String(20))
    vapi_call_id: Mapped[str | None] = mapped_column(String(100), unique=True)
    ended_reason: Mapped[str | None] = mapped_column(String(100))
    duration_seconds: Mapped[int | None] = mapped_column(Integer)
    business_reply: Mapped[str | None] = mapped_column(Text)
    business_price_text: Mapped[str | None] = mapped_column(String(300))
    confirmed_text: Mapped[str | None] = mapped_column(String(300))
    # What the user approved, exactly as dialled (recipient, number, rules, window, share_phone).
    approved_snapshot: Mapped[dict | None] = mapped_column(JSONB)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    dialled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Lead loop (app/modules/privat/lead_pitch.py): what happened to the fixed closing line. NULL = the feature was off.
    pitch_outcome: Mapped[str | None] = mapped_column(String(16))     # interested | declined | skipped | not_asked
    pitch_skipped_reason: Mapped[str | None] = mapped_column(String(60))
    pitch_transcript_excerpt: Mapped[str | None] = mapped_column(String(500))  # only the closing line and the answer, never more
    pitch_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # A call back from this business to a pool number is matched to this call until then (dialled + 14 days).
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Google place id (the only Places field that may be stored indefinitely); null for a number the user typed.
    place_id: Mapped[str | None] = mapped_column(String(300))
    # The business was closed when proposed: its next opening (inside our calling hours). With approval «ved næste
    # åbningstid» the call waits (status scheduled) and is dialled at scheduled_for by the worker.
    next_open_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    scheduled_for: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = ts_now()


class PrivateSubscription(Base):
    """The one subscription of a personal workspace (app/modules/privat/subscriptions.py).

    status: none (the free tier: no rights, no Stripe object) | trial (Stripe's trialing – 14 days on the
    subscription the card was given for; older rows: the card-less trial) | active | past_due | canceled – the last
    four mirror the Stripe subscription in `stripe_subscription_id`. "expired" (a trial past trial_ends_at) is derived
    when read."""

    __tablename__ = "private_subscriptions"
    __table_args__ = (
        CheckConstraint("plan in ('basis','plus','familie')", name="ck_private_subscriptions_plan"),
        CheckConstraint("status in ('none','trial','active','past_due','canceled')", name="ck_private_subscriptions_status"),
        CheckConstraint("interval is null or interval in ('month','year')", name="ck_private_subscriptions_interval"),
    )

    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), primary_key=True)
    plan: Mapped[str] = mapped_column(String(16), nullable=False, default="plus")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="none")
    interval: Mapped[str | None] = mapped_column(String(8))
    stripe_customer_id: Mapped[str | None] = mapped_column(String(100))
    stripe_subscription_id: Mapped[str | None] = mapped_column(String(100), unique=True)
    trial_ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    current_period_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancel_at_period_end: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    # DKK / SEK / NOK / EUR: set at the first Checkout (from the visitor's language) and kept from then on – a
    # customer keeps the currency it subscribed in. Null = never been to Checkout (shown in DKK unless asked).
    currency: Mapped[str | None] = mapped_column(String(3))
    created_at: Mapped[datetime] = ts_now()
    updated_at: Mapped[datetime] = ts_now()


class PrivateAddonEnabled(Base):
    """An add-on (app/modules/privat/addons.py) switched on for a personal workspace. Disabling deletes the row; the
    add-on's data stays."""

    __tablename__ = "private_addon_enabled"

    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), primary_key=True)
    key: Mapped[str] = mapped_column(String(40), primary_key=True)
    enabled_at: Mapped[datetime] = ts_now()


class PrivateAddonState(Base):
    """What the app shell remembers about an add-on per account, beside whether it is on (PrivateAddonEnabled):
    how far the user got in its setup steps, when it was last switched off (its data is kept – «Slået fra · dine data
    er gemt») and whether the user asked to hear when a «Kommer snart» app arrives."""

    __tablename__ = "private_addon_state"

    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), primary_key=True)
    key: Mapped[str] = mapped_column(String(40), primary_key=True)
    setup_done: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    disabled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    notify_requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = ts_now()


class PrivateGroup(Base):
    """A saved group («Mine folk»). Only its owner can ever read it. Phone numbers in it are used ONLY to give them back
    to the owner (to text from their own phone) and to recognise people already on Dialogbot – never to contact anyone."""

    __tablename__ = "private_groups"
    __table_args__ = (Index("ix_private_groups_owner", "owner_user_id", "created_at"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    owner_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = ts_now()


class PrivateGroupMember(Base):
    __tablename__ = "private_group_members"
    __table_args__ = (
        UniqueConstraint("group_id", "phone_e164", name="uq_private_group_members_phone"),
        UniqueConstraint("group_id", "user_id", name="uq_private_group_members_user"),
        Index("ix_private_group_members_group", "group_id"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    group_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("private_groups.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    phone_e164: Mapped[str | None] = mapped_column(String(20))
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    joined_via_invite_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("private_invites.id", ondelete="SET NULL", use_alter=True, name="fk_private_group_members_invite"))
    # Joined by themselves through the group's join link («Byg gruppen selv»)
    joined_via_link_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("private_group_links.id", ondelete="SET NULL", use_alter=True, name="fk_private_group_members_link"))
    created_at: Mapped[datetime] = ts_now()


class PrivateGroupLink(Base):
    """A join link to a saved group, sent by the owner from their own phone into an existing group chat. Short code
    (same alphabet as invites), 30 days, revocable. The public preview shows the group name, the owner's first name and
    the member COUNT – never names or numbers."""

    __tablename__ = "private_group_links"

    id: Mapped[uuid.UUID] = uuid_pk()
    group_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("private_groups.id", ondelete="CASCADE"), nullable=False,
                                                index=True)
    short_code: Mapped[str] = mapped_column(String(8), nullable=False, unique=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = ts_now()


class PrivatePhoneCode(Base):
    """An SMS code for someone WITHOUT an account who adds their number when joining a group (purpose group_join,
    ref_id = the join link). Only an HMAC is stored; 10 minutes; 5 attempts."""

    __tablename__ = "private_phone_codes"
    __table_args__ = (Index("ix_private_phone_codes_ref", "purpose", "ref_id", "phone_e164", "created_at"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    purpose: Mapped[str] = mapped_column(String(24), nullable=False)
    ref_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    phone_e164: Mapped[str] = mapped_column(String(20), nullable=False)
    code_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = ts_now()


class PrivateLookup(Base):
    """One public lookup of an invitation or group link (by token or short code), for rate limiting so codes cannot be
    enumerated. Only a keyed hash of the IP is stored; rows older than two days are deleted by the worker."""

    __tablename__ = "private_lookups"
    __table_args__ = (
        CheckConstraint("outcome in ('hit','miss')", name="ck_private_lookups_outcome"),
        Index("ix_private_lookups_ip_created", "ip_hash", "created_at"),
        Index("ix_private_lookups_outcome_created", "outcome", "created_at"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    ip_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    outcome: Mapped[str] = mapped_column(String(8), nullable=False)
    created_at: Mapped[datetime] = ts_now()


class PrivateBusinessSearch(Base):
    """One business search by a private user (rate limit 30/hour). The query itself is not stored."""

    __tablename__ = "private_business_searches"
    __table_args__ = (Index("ix_private_business_searches_ws_created", "workspace_id", "created_at"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    created_at: Mapped[datetime] = ts_now()


class PushSubscription(Base):
    """A Web Push subscription (VAPID) of one browser/device. Deleted when the push service answers 404/410."""

    __tablename__ = "push_subscriptions"
    __table_args__ = (CheckConstraint("audience in ('privat','erhverv')", name="ck_push_subscriptions_audience"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    # Which app subscribed: privat (Dialogbot Privat) or erhverv (the business PWA, bound to one workspace). The
    # same browser endpoint can only belong to one of them; re-subscribing from the other app moves it.
    audience: Mapped[str] = mapped_column(String(16), nullable=False, default="privat", server_default="privat")
    workspace_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"))
    endpoint: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    p256dh: Mapped[str] = mapped_column(String(200), nullable=False)
    auth: Mapped[str] = mapped_column(String(100), nullable=False)
    user_agent: Mapped[str | None] = mapped_column(String(400))
    created_at: Mapped[datetime] = ts_now()
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    failures: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")


class PrivateAppointment(Base):
    """An agreed time the user approved: a call where the business confirmed a time, a confirmed browser booking, or a
    time the user told the assistant themselves. It is what the Kalender app puts in the user's own calendar (.ics,
    the subscription link, and Google/Outlook when connected). `external` holds the event ids per connected calendar."""

    __tablename__ = "private_appointments"
    __table_args__ = (
        CheckConstraint("source in ('call','browser','manual')", name="ck_private_appointments_source"),
        CheckConstraint("status in ('confirmed','cancelled')", name="ck_private_appointments_status"),
        CheckConstraint("ends_at > starts_at", name="ck_private_appointments_range"),
        Index("ix_private_appointments_ws_starts", "workspace_id", "starts_at"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    task_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("private_tasks.id", ondelete="SET NULL"))
    source: Mapped[str] = mapped_column(String(16), nullable=False)
    # call:<id> | browser:<id> | manual:<uuid> – one appointment per approved errand, whatever is retried.
    source_ref: Mapped[str] = mapped_column(String(80), nullable=False, unique=True)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    location: Mapped[str] = mapped_column(String(300), nullable=False, default="", server_default="")
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="confirmed", server_default="confirmed")
    # iCalendar SEQUENCE: bumped on every change so calendars replace the old version.
    sequence: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    # {"google_calendar": {"event_id": "...", "sequence": 2, "error": null}, ...}
    external: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")
    created_at: Mapped[datetime] = ts_now()
    updated_at: Mapped[datetime] = ts_now()


class PrivateBirthday(Base):
    """Fødselsdage app: a birthday the user told the assistant. Reminded `remind_days_before` days before (0 = on the
    day), once a year (`last_reminded_for` is the birthday date the last reminder was about)."""

    __tablename__ = "private_birthdays"
    __table_args__ = (
        CheckConstraint("month between 1 and 12", name="ck_private_birthdays_month"),
        CheckConstraint("day between 1 and 31", name="ck_private_birthdays_day"),
        CheckConstraint("year is null or year between 1900 and 2100", name="ck_private_birthdays_year"),
        CheckConstraint("remind_days_before between 0 and 60", name="ck_private_birthdays_remind"),
        UniqueConstraint("workspace_id", "name_key", name="uq_private_birthdays_name"),
        Index("ix_private_birthdays_ws_month_day", "workspace_id", "month", "day"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    name_key: Mapped[str] = mapped_column(String(100), nullable=False)   # lower-case, single spaces: one per person
    month: Mapped[int] = mapped_column(Integer, nullable=False)
    day: Mapped[int] = mapped_column(Integer, nullable=False)
    year: Mapped[int | None] = mapped_column(Integer)                     # only when the user gave it (for the age)
    remind_days_before: Mapped[int] = mapped_column(Integer, nullable=False, default=7, server_default="7")
    last_reminded_for: Mapped[date | None] = mapped_column(Date)
    created_at: Mapped[datetime] = ts_now()
    updated_at: Mapped[datetime] = ts_now()


class PrivateBill(Base):
    """Regninger app: a bill the user told the assistant about – reminded before it is due. Dialogbot never pays and
    never sees the bank. `next_due` moves on by `frequency` once the due date has passed (`anchor_day` keeps «the 31st»)."""

    __tablename__ = "private_bills"
    __table_args__ = (
        CheckConstraint("frequency in ('monthly','quarterly','half_yearly','yearly','once')",
                        name="ck_private_bills_frequency"),
        CheckConstraint("anchor_day between 1 and 31", name="ck_private_bills_anchor_day"),
        CheckConstraint("amount_minor is null or amount_minor >= 0", name="ck_private_bills_amount"),
        CheckConstraint("remind_days_before between 0 and 30", name="ck_private_bills_remind"),
        UniqueConstraint("workspace_id", "name_key", name="uq_private_bills_name"),
        Index("ix_private_bills_ws_next_due", "workspace_id", "next_due"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    name_key: Mapped[str] = mapped_column(String(100), nullable=False)
    amount_minor: Mapped[int | None] = mapped_column(Integer)          # øre; only when the user said the amount
    frequency: Mapped[str] = mapped_column(String(16), nullable=False, default="monthly")
    anchor_day: Mapped[int] = mapped_column(Integer, nullable=False)
    next_due: Mapped[date] = mapped_column(Date, nullable=False)
    remind_days_before: Mapped[int] = mapped_column(Integer, nullable=False, default=3, server_default="3")
    last_reminded_for: Mapped[date | None] = mapped_column(Date)
    created_at: Mapped[datetime] = ts_now()
    updated_at: Mapped[datetime] = ts_now()


class PrivateAppData(Base):
    """Small per-app settings of a personal workspace, as JSON: Pakkeliste (its lists), Madplan (household and food
    habits), Læge & tandlæge (the saved practices), Bil & syn (the car, dates, the workshop), Pakker (tracked parcels).
    Only what the user gave; deleted with the account."""

    __tablename__ = "private_app_data"

    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), primary_key=True)
    app_key: Mapped[str] = mapped_column(String(40), primary_key=True)
    data: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")
    updated_at: Mapped[datetime] = ts_now()


class PrivateBusinessReferral(Base):
    """A business a Privat user asked for a quote through Dialogbot (Håndværker & tilbud, Flytning, Hus & vedligehold),
    and whether the user chose it. The basis for Dialogbot's lead revenue: «we sent you N customers». It keeps only the
    business side and a short job title; the workspace is set to NULL when the account is deleted."""

    __tablename__ = "private_business_referrals"

    id: Mapped[uuid.UUID] = uuid_pk()
    workspace_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("workspaces.id", ondelete="SET NULL"))
    app_key: Mapped[str] = mapped_column(String(40), nullable=False)
    job: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    trade: Mapped[str] = mapped_column(String(80), nullable=False, default="")
    business_name: Mapped[str] = mapped_column(String(200), nullable=False)
    business_phone_e164: Mapped[str | None] = mapped_column(String(20))
    place_id: Mapped[str | None] = mapped_column(String(300))
    call_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("private_calls.id", ondelete="SET NULL"))
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="asked")  # asked | chosen | not_chosen
    created_at: Mapped[datetime] = ts_now()
    chosen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint("status IN ('asked','chosen','not_chosen')", name="ck_private_business_referrals_status"),
        Index("ix_private_business_referrals_phone", "business_phone_e164"),
        Index("ix_private_business_referrals_ws", "workspace_id"),
    )


class PrivateHouseholdMember(Base):
    """Familie (app/modules/privat/household.py): one person in the household of a Familie subscriber – at most 4
    members besides the owner («Op til 5 personer»). Membership lends the owner's plan rights (apps, the household's
    shared call quota); it NEVER gives access to anybody's data: each person keeps their own personal workspace.
    A person is in at most one household (unique member). Rights are derived live from the owner's subscription, so
    removal, leaving, a downgrade or a cancellation takes effect at once; the row stays through a downgrade (the
    household is paused) and is deleted on removal, leaving or account deletion."""

    __tablename__ = "private_household_members"
    __table_args__ = (
        CheckConstraint("owner_workspace_id <> member_workspace_id", name="ck_private_household_members_self"),
        Index("ix_private_household_members_owner", "owner_workspace_id", "joined_at"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    owner_workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"),
                                                          nullable=False)
    member_workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"),
                                                           nullable=False, unique=True)
    invite_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("private_invites.id", ondelete="SET NULL"))
    joined_at: Mapped[datetime] = ts_now()


class PrivateDataExport(Base):
    """«Eksportér mine data» (app/modules/privat/gdpr.py): built by the worker, fetched with a link from an e-mail.
    Only the SHA-256 of the link's token is kept; the content is wiped when the link expires (or the account is
    deleted – the row cascades with the user)."""

    __tablename__ = "private_data_exports"
    __table_args__ = (
        CheckConstraint("status in ('queued','ready','expired','failed')", name="ck_private_data_exports_status"),
        Index("ix_private_data_exports_user", "user_id", "requested_at"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="queued")
    token_hash: Mapped[str | None] = mapped_column(String(64), unique=True)
    data: Mapped[dict | None] = mapped_column(JSONB)
    requested_at: Mapped[datetime] = ts_now()
    ready_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    downloaded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PrivateTrialCard(Base):
    """One free trial per CARD (decision Fürster 2026-11-10, F-PBQ-02): Stripe's card fingerprint (a hash Stripe makes
    of the card number – never card data) for every card that has started a Privat trial. A new account whose card is
    already here gets no trial (subscriptions.upsert_from_stripe_subscription ends it at once). Kept when the account
    is deleted (workspace_id → NULL), or deleting and re-signing up would buy a new trial."""

    __tablename__ = "private_trial_cards"

    fingerprint: Mapped[str] = mapped_column(String(64), primary_key=True)
    workspace_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("workspaces.id", ondelete="SET NULL"))
    stripe_subscription_id: Mapped[str | None] = mapped_column(String(100))
    first_trial_at: Mapped[datetime] = ts_now()
