"""Dialogbot Privat: a personal assistant for private Danish consumers.

Everything here belongs to ONE personal workspace (workspaces.kind = 'personal'), owned by exactly one user through
`private_profiles`. Business endpoints never resolve a personal workspace, and the private endpoints only ever
resolve the caller's own (app/modules/privat/deps.py).
"""
from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import (
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
CREDIT_KINDS = ("grant", "purchase", "reserve", "capture", "release", "spend", "sponsor", "referral")
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
    created_at: Mapped[datetime] = ts_now()


class PrivateTask(Base):
    __tablename__ = "private_tasks"
    __table_args__ = (
        CheckConstraint("kind in ('list','reminder','call')", name="ck_private_tasks_kind"),
        CheckConstraint("status in ('awaiting_user','draft','planned','in_progress','awaiting_business','done',"
                        "'declined')", name="ck_private_tasks_status"),
        CheckConstraint("paid_by in ('free','credit','sponsor','none','call','plan')", name="ck_private_tasks_paid_by"),
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
    # free (one of the month's 10) | credit | sponsor | none (draft, not paid yet) | call (paid by call credits)
    # | plan (included in the trial or a subscription: never counts against the free quota)
    paid_by: Mapped[str] = mapped_column(String(16), nullable=False, default="none")
    free_month: Mapped[str | None] = mapped_column(String(7))  # "2026-11" when it used a free task that month
    is_example: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    # Lists: shopping | wishlist | todo (null for other kinds)
    list_type: Mapped[str | None] = mapped_column(String(16))
    # Shared lists: group (everyone adds and ticks, attributed) | wishlist (members reserve; the owner never sees it).
    # Null = not shared. Access ALWAYS goes through private_task_members, never through workspace_id.
    share_mode: Mapped[str | None] = mapped_column(String(16))
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
    created_at: Mapped[datetime] = ts_now()


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
    """Append-only credit movements. Balance = SUM(amount). A reserve (-3) is later captured (0, the reserve becomes
    the spend) or released (+3). `source_ref` is unique, so a replayed webhook or command can never move credits twice."""

    __tablename__ = "credit_ledger"
    __table_args__ = (
        CheckConstraint("kind in ('grant','purchase','reserve','capture','release','spend','sponsor','referral')",
                        name="ck_credit_ledger_kind"),
        Index("ix_credit_ledger_ws_created", "workspace_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    amount: Mapped[int] = mapped_column(Integer, nullable=False)
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
        CheckConstraint("paid_via is null or paid_via in ('credits','plan')", name="ck_private_calls_paid_via"),
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
    # Set at approval: credits (3 credits reserved, the pre-subscription path) | plan (one of the month's plan calls).
    # Null for calls approved before subscriptions existed (they were all paid with credits).
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
    created_at: Mapped[datetime] = ts_now()
    updated_at: Mapped[datetime] = ts_now()


class PrivateAddonEnabled(Base):
    """An add-on (app/modules/privat/addons.py) switched on for a personal workspace. Disabling deletes the row; the
    add-on's data stays."""

    __tablename__ = "private_addon_enabled"

    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), primary_key=True)
    key: Mapped[str] = mapped_column(String(40), primary_key=True)
    enabled_at: Mapped[datetime] = ts_now()


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

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
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
