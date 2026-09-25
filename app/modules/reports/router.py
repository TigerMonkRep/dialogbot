from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session as OrmSession

from app.core.audit import record_audit
from app.core.auth import WorkspaceContext, require_capability
from app.db import get_db
from app.models import DailyReport
from app.modules.reports import service

router = APIRouter(prefix="/workspaces/{workspace_id}/reports", tags=["reports"])


def _for_role(ctx: WorkspaceContext, data: dict) -> dict:
    """Costs and fees are for owners/admins; staff see activity only."""
    if ctx.can("reports.costs"):
        return data
    d = {**data, "ai": {k: v for k, v in data["ai"].items() if k != "est_cost_usd_micros"},
         "leads": {k: v for k, v in data["leads"].items() if k != "approved_fee_net_minor"}}
    return d


@router.get("")
def list_reports(limit: int = Query(default=30, ge=1, le=366),
                 ctx: WorkspaceContext = Depends(require_capability("reports.read")), db: OrmSession = Depends(get_db)):
    rows = db.scalars(select(DailyReport).where(DailyReport.workspace_id == ctx.workspace.id)
                      .order_by(DailyReport.report_date.desc()).limit(limit)).all()
    tz = service.tz_of(db, ctx.workspace.id)
    return {"timezone": tz, "today": service.local_today(tz).isoformat(),
            "items": [{"date": r.report_date.isoformat(), "generated_at": r.generated_at.isoformat(),
                       "summary": {"conversations": r.data["conversations"]["started"], "new_leads": r.data["leads"]["new"],
                                   "approved_leads": r.data["leads"]["approved"]}} for r in rows]}


class SettingsIn(BaseModel):
    email_enabled: bool
    send_hour_local: int = Field(ge=0, le=23)


@router.get("/settings")
def get_settings_(ctx: WorkspaceContext = Depends(require_capability("reports.read")), db: OrmSession = Depends(get_db)):
    s = service.settings_for(db, ctx.workspace.id)
    db.commit()
    return {"email_enabled": s.email_enabled, "send_hour_local": s.send_hour_local,
            "timezone": service.tz_of(db, ctx.workspace.id)}


@router.put("/settings")
def put_settings(body: SettingsIn, request: Request, ctx: WorkspaceContext = Depends(require_capability("reports.manage")),
                 db: OrmSession = Depends(get_db)):
    s = service.settings_for(db, ctx.workspace.id)
    before = {"email_enabled": s.email_enabled, "send_hour_local": s.send_hour_local}
    s.email_enabled, s.send_hour_local = body.email_enabled, body.send_hour_local
    record_audit(db, workspace_id=ctx.workspace.id, actor_user_id=ctx.user_id, action="reports.settings_updated",
                 object_type="report_settings", object_id=ctx.workspace.id, before=before, after=body.model_dump(),
                 request_id=request.state.request_id)
    db.commit()
    return {**body.model_dump(), "timezone": service.tz_of(db, ctx.workspace.id)}


@router.get("/{day}")
def get_report(day: date, ctx: WorkspaceContext = Depends(require_capability("reports.read")),
               db: OrmSession = Depends(get_db)):
    """A stored snapshot for a finished day, or live numbers (marked preliminary) for today."""
    tz = service.tz_of(db, ctx.workspace.id)
    r = db.scalar(select(DailyReport).where(DailyReport.workspace_id == ctx.workspace.id, DailyReport.report_date == day))
    if r is not None:
        return {"status": "final", "generated_at": r.generated_at.isoformat(), **_for_role(ctx, r.data)}
    today = service.local_today(tz)
    if day > today:
        from app.core.errors import NotFound

        raise NotFound("Rapporten findes ikke endnu")
    status = "preliminary" if day == today else "not_generated"
    return {"status": status, "generated_at": None, **_for_role(ctx, service.compute(db, ctx.workspace.id, day, tz))}
