from __future__ import annotations

import re
import uuid
from datetime import UTC, date, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session as OrmSession

from app.core.audit import record_audit
from app.core.auth import WorkspaceContext, get_scoped
from app.core.errors import Conflict, NotFound, ValidationFailed
from app.core.outbox import enqueue
from app.models import KNOWLEDGE_KINDS, KnowledgeItem, KnowledgeVersion, Workspace
from app.modules.setup.checks import invalidate_checks


def _now() -> datetime:
    return datetime.now(UTC)


def _key(kind: str, title: str) -> str:
    s = title.lower().replace("æ", "ae").replace("ø", "oe").replace("å", "aa")
    return f"{kind}:{re.sub(r'[^a-z0-9]+', '-', s).strip('-')[:80] or 'item'}"


def validate_content(kind: str, content: dict) -> None:
    """Minimal structural validation per kind. The offer kind enforces the
    reconciled K04 rule shape (operator + threshold + inclusive date range)."""
    if kind == "offer":
        cond = content.get("condition") or {}
        if cond.get("area_operator") not in ("gte", "gt", "lte", "lt", None):
            raise ValidationFailed("condition.area_operator skal være gte, gt, lte eller lt",
                                   field_errors=[{"field": "content.condition.area_operator"}])
        if "area_threshold_m2" in cond and not isinstance(cond["area_threshold_m2"], (int, float)):
            raise ValidationFailed("condition.area_threshold_m2 skal være et tal",
                                   field_errors=[{"field": "content.condition.area_threshold_m2"}])
        for f in ("starts_on", "ends_on_inclusive"):
            if f in content:
                try:
                    date.fromisoformat(content[f])
                except Exception:
                    raise ValidationFailed(f"{f} skal være en ISO-dato", field_errors=[{"field": f"content.{f}"}])
        if "starts_on" in content and "ends_on_inclusive" in content and content["starts_on"] > content["ends_on_inclusive"]:
            raise ValidationFailed("Slutdato må ikke ligge før startdato",
                                   field_errors=[{"field": "content.ends_on_inclusive"}])
    if kind == "opening_hours":
        if not isinstance(content.get("weekly"), list):
            raise ValidationFailed("opening_hours kræver 'weekly' som liste", field_errors=[{"field": "content.weekly"}])


def offer_is_eligible(content: dict, *, area_m2: float | None, on_date: date) -> bool:
    """Pure rule for the K04 example: discount applies when area OP threshold
    (>= 40 m² in the fixture) AND on_date is inside [starts_on, ends_on_inclusive]."""
    starts = content.get("starts_on")
    ends = content.get("ends_on_inclusive")
    if starts and on_date < date.fromisoformat(starts):
        return False
    if ends and on_date > date.fromisoformat(ends):
        return False
    cond = content.get("condition") or {}
    op = cond.get("area_operator")
    thr = cond.get("area_threshold_m2")
    if op and thr is not None:
        if area_m2 is None:
            return False
        return {"gte": area_m2 >= thr, "gt": area_m2 > thr, "lte": area_m2 <= thr, "lt": area_m2 < thr}[op]
    return True


def open_draft(db: OrmSession, item_id: uuid.UUID) -> KnowledgeVersion | None:
    return db.scalar(select(KnowledgeVersion).where(KnowledgeVersion.item_id == item_id,
                                                    KnowledgeVersion.status.in_(("draft", "in_review"))))


def approved_version(db: OrmSession, item_id: uuid.UUID) -> KnowledgeVersion | None:
    return db.scalar(select(KnowledgeVersion).where(KnowledgeVersion.item_id == item_id,
                                                    KnowledgeVersion.status == "approved"))


def create_item(db: OrmSession, ctx: WorkspaceContext, *, kind: str, title: str, content: dict,
                source_ref: str | None, request_id: str | None) -> tuple[KnowledgeItem, KnowledgeVersion]:
    ctx.require("knowledge.draft")
    if kind not in KNOWLEDGE_KINDS:
        raise ValidationFailed("Ugyldig vidensart", field_errors=[{"field": "kind"}])
    validate_content(kind, content)
    key = _key(kind, title)
    if db.scalar(select(KnowledgeItem).where(KnowledgeItem.workspace_id == ctx.workspace.id,
                                             KnowledgeItem.kind == kind, KnowledgeItem.key == key)):
        raise Conflict("Der findes allerede et vidensemne med denne titel og art", code="knowledge_key_exists")
    item = KnowledgeItem(workspace_id=ctx.workspace.id, kind=kind, key=key)
    db.add(item)
    db.flush()
    v = KnowledgeVersion(item_id=item.id, workspace_id=ctx.workspace.id, version_no=1, status="draft", title=title,
                         content=content, source_type="manual", source_ref=source_ref, created_by=ctx.user_id)
    db.add(v)
    db.flush()
    record_audit(db, workspace_id=ctx.workspace.id, actor_user_id=ctx.user_id, action="knowledge.draft_created",
                 object_type="knowledge_version", object_id=v.id, after={"item_id": str(item.id), "kind": kind,
                                                                         "title": title}, request_id=request_id)
    return item, v


def new_draft(db: OrmSession, ctx: WorkspaceContext, item_id: uuid.UUID, *, title: str, content: dict,
              source_ref: str | None, request_id: str | None) -> KnowledgeVersion:
    """Create a new draft version of an existing item. Never touches the approved version."""
    ctx.require("knowledge.draft")
    item = get_scoped(db, KnowledgeItem, item_id, ctx.workspace.id)
    if open_draft(db, item.id) is not None:
        raise Conflict("Der findes allerede en åben kladde for dette emne. Redigér den i stedet.",
                       code="draft_exists")
    validate_content(item.kind, content)
    max_no = db.scalar(select(func.max(KnowledgeVersion.version_no)).where(KnowledgeVersion.item_id == item.id)) or 0
    v = KnowledgeVersion(item_id=item.id, workspace_id=ctx.workspace.id, version_no=max_no + 1, status="draft",
                         title=title, content=content, source_type="manual", source_ref=source_ref,
                         created_by=ctx.user_id)
    db.add(v)
    db.flush()
    record_audit(db, workspace_id=ctx.workspace.id, actor_user_id=ctx.user_id, action="knowledge.draft_created",
                 object_type="knowledge_version", object_id=v.id, after={"item_id": str(item.id),
                                                                         "version_no": v.version_no},
                 request_id=request_id)
    return v


def edit_draft(db: OrmSession, ctx: WorkspaceContext, version_id: uuid.UUID, *, expected_edit_version: int,
               title: str, content: dict, source_ref: str | None, request_id: str | None) -> KnowledgeVersion:
    ctx.require("knowledge.draft")
    v = db.scalar(select(KnowledgeVersion).where(KnowledgeVersion.id == version_id,
                                                 KnowledgeVersion.workspace_id == ctx.workspace.id).with_for_update())
    if v is None:
        raise NotFound("Versionen findes ikke")
    if v.status not in ("draft", "in_review"):
        raise Conflict("Kun kladder kan redigeres. Opret en ny kladde for at ændre en godkendt version.",
                       code="version_not_editable")
    if v.edit_version != expected_edit_version:
        raise Conflict("Kladden er ændret af en anden. Genindlæs og prøv igen.", code="version_conflict",
                       extra={"current_version": v.edit_version})
    item = db.get(KnowledgeItem, v.item_id)
    validate_content(item.kind, content)
    before = {"title": v.title, "content": v.content}
    v.title, v.content, v.source_ref = title, content, source_ref
    v.edit_version += 1
    if v.status == "in_review":
        v.status = "draft"  # edits after submission return the draft to review start
        v.submitted_at = None
    record_audit(db, workspace_id=ctx.workspace.id, actor_user_id=ctx.user_id, action="knowledge.draft_edited",
                 object_type="knowledge_version", object_id=v.id, before=before,
                 after={"title": title, "content": content}, request_id=request_id)
    return v


def submit_for_review(db: OrmSession, ctx: WorkspaceContext, version_id: uuid.UUID, request_id: str | None):
    ctx.require("knowledge.submit")
    v = db.scalar(select(KnowledgeVersion).where(KnowledgeVersion.id == version_id,
                                                 KnowledgeVersion.workspace_id == ctx.workspace.id).with_for_update())
    if v is None:
        raise NotFound("Versionen findes ikke")
    if v.status != "draft":
        raise Conflict(f"Versionen har status {v.status} og kan ikke sendes til gennemgang", code="invalid_transition")
    v.status = "in_review"
    v.submitted_at = _now()
    record_audit(db, workspace_id=ctx.workspace.id, actor_user_id=ctx.user_id, action="knowledge.submitted",
                 object_type="knowledge_version", object_id=v.id, before={"status": "draft"},
                 after={"status": "in_review"}, request_id=request_id)
    return v


def approve(db: OrmSession, ctx: WorkspaceContext, version_id: uuid.UUID, request_id: str | None) -> KnowledgeVersion:
    """Approve an in-review version. Supersedes the previously approved version,
    bumps the workspace knowledge revision and invalidates dependent checks.
    Approval is idempotent: approving an already-approved version is a no-op."""
    ctx.require("knowledge.approve")
    v = db.scalar(select(KnowledgeVersion).where(KnowledgeVersion.id == version_id,
                                                 KnowledgeVersion.workspace_id == ctx.workspace.id).with_for_update())
    if v is None:
        raise NotFound("Versionen findes ikke")
    if v.status == "approved":
        return v
    if v.status not in ("in_review", "draft"):
        raise Conflict(f"Versionen har status {v.status} og kan ikke godkendes", code="invalid_transition")
    prev = approved_version(db, v.item_id)
    if prev is not None:
        prev.status = "superseded"
        prev.superseded_at = _now()
        db.flush()
    v.status = "approved"
    v.approved_by = ctx.user_id
    v.approved_at = _now()
    ws = db.scalar(select(Workspace).where(Workspace.id == ctx.workspace.id).with_for_update())
    ws.knowledge_revision += 1
    db.flush()
    record_audit(db, workspace_id=ctx.workspace.id, actor_user_id=ctx.user_id, action="knowledge.approved",
                 object_type="knowledge_version", object_id=v.id,
                 before={"status": "in_review", "previous_approved_version_id": str(prev.id) if prev else None},
                 after={"status": "approved", "version_no": v.version_no, "knowledge_revision": ws.knowledge_revision},
                 request_id=request_id)
    enqueue(db, event_type="knowledge.version_approved", dedupe_key=f"knowledge-approved:{v.id}",
            workspace_id=ctx.workspace.id, payload={"version_id": str(v.id), "item_id": str(v.item_id),
                                                    "knowledge_revision": ws.knowledge_revision})
    invalidate_checks(db, ctx.workspace.id, changed_area="knowledge",
                      reason=f"Viden blev godkendt (revision {ws.knowledge_revision})")
    return v


def archive_item(db: OrmSession, ctx: WorkspaceContext, item_id: uuid.UUID, request_id: str | None) -> KnowledgeItem:
    """Delete an item from the knowledge base (soft: archived, kept for audit). Removing approved
    knowledge changes what the assistant says, so it needs the approver role and bumps the revision;
    a draft-only item can be removed by whoever may draft. The key is freed for a new item."""
    ctx.require("knowledge.draft")
    item = get_scoped(db, KnowledgeItem, item_id, ctx.workspace.id)
    if item.archived_at is not None:
        return item
    live = approved_version(db, item.id)
    if live is not None:
        ctx.require("knowledge.approve")
    for v in db.scalars(select(KnowledgeVersion).where(KnowledgeVersion.item_id == item.id,
                                                       KnowledgeVersion.status.in_(("draft", "in_review")))):
        v.status = "rejected"
    item.archived_at = _now()
    item.key = f"{item.key[:100]}~{str(item.id)[:8]}"
    after: dict = {"kind": item.kind, "had_approved_version": live is not None}
    if live is not None:
        ws = db.scalar(select(Workspace).where(Workspace.id == ctx.workspace.id).with_for_update())
        ws.knowledge_revision += 1
        after["knowledge_revision"] = ws.knowledge_revision
    db.flush()
    record_audit(db, workspace_id=ctx.workspace.id, actor_user_id=ctx.user_id, action="knowledge.item_deleted",
                 object_type="knowledge_item", object_id=item.id,
                 before={"title": live.title if live else None}, after=after, request_id=request_id)
    invalidate_checks(db, ctx.workspace.id, changed_area="knowledge", reason="Et vidensemne blev slettet")
    return item


def reject(db: OrmSession, ctx: WorkspaceContext, version_id: uuid.UUID, reason: str, request_id: str | None):
    ctx.require("knowledge.approve")
    v = db.scalar(select(KnowledgeVersion).where(KnowledgeVersion.id == version_id,
                                                 KnowledgeVersion.workspace_id == ctx.workspace.id).with_for_update())
    if v is None:
        raise NotFound("Versionen findes ikke")
    if v.status not in ("in_review", "draft"):
        raise Conflict(f"Versionen har status {v.status}", code="invalid_transition")
    v.status = "rejected"
    record_audit(db, workspace_id=ctx.workspace.id, actor_user_id=ctx.user_id, action="knowledge.rejected",
                 object_type="knowledge_version", object_id=v.id, after={"reason": reason}, request_id=request_id)
    return v


def active_knowledge(db: OrmSession, workspace_id: uuid.UUID) -> list[dict]:
    """The assistant's read model: ONLY approved, current versions of
    non-archived items in this workspace. Drafts and raw sources are never
    included."""
    rows = db.execute(
        select(KnowledgeItem, KnowledgeVersion).join(KnowledgeVersion, KnowledgeVersion.item_id == KnowledgeItem.id)
        .where(KnowledgeItem.workspace_id == workspace_id, KnowledgeVersion.status == "approved",
               KnowledgeItem.archived_at.is_(None))
        .order_by(KnowledgeItem.kind, KnowledgeItem.key)
    )
    return [
        {"id": str(v.id), "item_id": str(i.id), "kind": i.kind, "title": v.title, "content": v.content,
         "version_no": v.version_no, "status": v.status, "approved_at": v.approved_at.isoformat() if v.approved_at else None}
        for i, v in rows
    ]
