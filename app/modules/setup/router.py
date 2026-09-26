from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session as OrmSession

from app.config import get_settings
from app.core.audit import record_audit
from app.core.auth import WorkspaceContext, get_workspace_context, require_capability
from app.core.errors import Conflict, NotFound, NotImplementedYet, ValidationFailed
from app.db import get_db
from app.models import Membership, SetupTaskState
from app.modules.integrations.registry import capability
from app.modules.setup import checks as checks_svc
from app.modules.setup.plan import TASK_INDEX, compute_plan

router = APIRouter(prefix="/workspaces/{workspace_id}/setup", tags=["setup"])


class AssignIn(BaseModel):
    user_id: uuid.UUID | None


@router.get("/plan")
def get_plan(ctx: WorkspaceContext = Depends(require_capability("setup.read")), db: OrmSession = Depends(get_db)):
    """G01/G02/G05/G08 in one server-computed document: tasks, next action, checks, resume state."""
    return compute_plan(db, ctx)


@router.get("/tasks/{task_key}")
def get_task(task_key: str, ctx: WorkspaceContext = Depends(require_capability("setup.read")),
             db: OrmSession = Depends(get_db)):
    plan = compute_plan(db, ctx)
    for t in plan["tasks"]:
        if t["key"] == task_key:
            return t
    raise NotFound("Opgaven findes ikke eller er ikke relevant for de valgte mål")


def _state(db: OrmSession, ws_id: uuid.UUID, task_key: str) -> SetupTaskState:
    st = db.scalar(select(SetupTaskState).where(SetupTaskState.workspace_id == ws_id,
                                                SetupTaskState.task_key == task_key).with_for_update())
    if st is None:
        st = SetupTaskState(workspace_id=ws_id, task_key=task_key)
        db.add(st)
        db.flush()
    return st


@router.post("/tasks/{task_key}/skip")
def skip_task(task_key: str, request: Request, ctx: WorkspaceContext = Depends(require_capability("setup.edit")),
              db: OrmSession = Depends(get_db)):
    plan = compute_plan(db, ctx)
    task = next((t for t in plan["tasks"] if t["key"] == task_key), None)
    if task is None:
        raise NotFound("Opgaven findes ikke")
    if task["required"]:
        raise Conflict("Et nødvendigt trin kan ikke springes over", code="task_required")
    if task["status"] == "complete":
        raise Conflict("Opgaven er allerede gennemført", code="task_complete")
    st = _state(db, ctx.workspace.id, task_key)
    from datetime import UTC, datetime

    st.skipped_at = datetime.now(UTC)
    st.skipped_by = ctx.user_id
    record_audit(db, workspace_id=ctx.workspace.id, actor_user_id=ctx.user_id, action="setup.task_skipped",
                 object_type="setup_task", object_id=task_key, request_id=request.state.request_id)
    db.commit()
    return get_task(task_key, ctx, db)


@router.post("/tasks/{task_key}/unskip")
def unskip_task(task_key: str, request: Request, ctx: WorkspaceContext = Depends(require_capability("setup.edit")),
                db: OrmSession = Depends(get_db)):
    if task_key not in TASK_INDEX:
        raise NotFound("Opgaven findes ikke")
    st = _state(db, ctx.workspace.id, task_key)
    st.skipped_at = None
    st.skipped_by = None
    record_audit(db, workspace_id=ctx.workspace.id, actor_user_id=ctx.user_id, action="setup.task_unskipped",
                 object_type="setup_task", object_id=task_key, request_id=request.state.request_id)
    db.commit()
    return get_task(task_key, ctx, db)


@router.put("/tasks/{task_key}/assignee")
def assign_task(task_key: str, body: AssignIn, request: Request,
                ctx: WorkspaceContext = Depends(require_capability("setup.edit")), db: OrmSession = Depends(get_db)):
    """G07: hand a task to a colleague who is a member of this workspace."""
    if task_key not in TASK_INDEX:
        raise NotFound("Opgaven findes ikke")
    if body.user_id is not None:
        m = db.scalar(select(Membership).where(Membership.workspace_id == ctx.workspace.id,
                                               Membership.user_id == body.user_id))
        if m is None:
            raise ValidationFailed("Personen er ikke medlem af arbejdsrummet", field_errors=[{"field": "user_id"}])
        if ctx.role not in ("owner", "admin") and body.user_id != ctx.user_id:
            from app.core.errors import Forbidden

            raise Forbidden("Kun administratorer kan tildele opgaver til andre", code="insufficient_role")
    st = _state(db, ctx.workspace.id, task_key)
    before = str(st.assigned_to) if st.assigned_to else None
    st.assigned_to = body.user_id
    record_audit(db, workspace_id=ctx.workspace.id, actor_user_id=ctx.user_id, action="setup.task_assigned",
                 object_type="setup_task", object_id=task_key, before={"assigned_to": before},
                 after={"assigned_to": str(body.user_id) if body.user_id else None}, request_id=request.state.request_id)
    db.commit()
    return get_task(task_key, ctx, db)


@router.post("/checks/{check_key}/run")
def run_check(check_key: str, request: Request, ctx: WorkspaceContext = Depends(require_capability("setup.run_check")),
              db: OrmSession = Depends(get_db)):
    res = checks_svc.run_check(db, ctx.workspace.id, check_key, run_by=ctx.user_id,
                               environment=f"server:{get_settings().app_env}")
    record_audit(db, workspace_id=ctx.workspace.id, actor_user_id=ctx.user_id, action="setup.check_run",
                 object_type="check_result", object_id=res.id, after={"check_key": check_key, "status": res.status},
                 request_id=request.state.request_id)
    db.commit()
    return {"id": str(res.id), "check_key": res.check_key, "status": res.status, "scope": res.scope,
            "environment": res.environment, "config_versions": res.config_versions, "evidence": res.evidence,
            "run_at": res.run_at.isoformat()}


@router.post("/checks/run-all")
def run_all_checks(request: Request, ctx: WorkspaceContext = Depends(require_capability("setup.run_check")),
                   db: OrmSession = Depends(get_db)):
    """Runs every server-side check. Checks needing an unimplemented capability
    are reported as skipped with the reason; they are never recorded."""
    from app.models import GoalSelection

    g = db.get(GoalSelection, ctx.workspace.id)
    campaigns = bool(g and g.product_intent in ("campaigns", "both"))
    results, skipped = [], []
    for key, d in checks_svc.CHECKS.items():
        if d.required_when and not any((f == "campaigns" and campaigns) or (f != "campaigns" and getattr(g, f, False))
                                       for f in d.required_when):
            skipped.append({"check_key": key, "reason": "not_selected"})
            continue
        if d.capability and capability(d.capability).status != "available":
            skipped.append({"check_key": key, "reason": "not_implemented", "capability": d.capability})
            continue
        res = checks_svc.run_check(db, ctx.workspace.id, key, run_by=ctx.user_id,
                                   environment=f"server:{get_settings().app_env}")
        results.append({"check_key": key, "status": res.status, "evidence": res.evidence})
    record_audit(db, workspace_id=ctx.workspace.id, actor_user_id=ctx.user_id, action="setup.checks_run_all",
                 object_type="check_result", after={"results": results, "skipped": skipped},
                 request_id=request.state.request_id)
    db.commit()
    return {"results": results, "skipped": skipped}


@router.get("/checks/history")
def check_history(ctx: WorkspaceContext = Depends(require_capability("setup.read")), db: OrmSession = Depends(get_db)):
    from app.models import CheckResult

    rows = db.scalars(select(CheckResult).where(CheckResult.workspace_id == ctx.workspace.id)
                      .order_by(CheckResult.run_at.desc()).limit(200))
    return {"items": [{"id": str(r.id), "check_key": r.check_key, "status": r.status, "environment": r.environment,
                       "config_versions": r.config_versions, "evidence": r.evidence, "run_at": r.run_at.isoformat(),
                       "stale_reason": r.stale_reason} for r in rows]}


# Explicit, separate activation commands (G06). They are not implemented in
# this stage and never succeed; they exist so that the API contract keeps
# publication, activation, payment and launch as distinct commands.


@router.post("/activate/reception")
def activate_reception(ctx: WorkspaceContext = Depends(get_workspace_context)):
    ctx.require("knowledge.approve")
    raise NotImplementedYet("Aktivering af reception kræver en implementeret telefoniudbyder og et bestået prøveopkald. "
                            "Ingen integration er aktiveret.", extra={"capability": "telephony.inbound"})


@router.post("/activate/campaigns")
def activate_campaigns(ctx: WorkspaceContext = Depends(get_workspace_context)):
    ctx.require("knowledge.approve")
    raise NotImplementedYet("Kampagneaktivering, betaling og lancering er særskilte kommandoer i etape 4. "
                            "Ingen integration er aktiveret.", extra={"capability": "telephony.outbound"})
