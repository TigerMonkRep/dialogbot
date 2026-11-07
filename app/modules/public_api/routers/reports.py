from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session as OrmSession

from app.core.errors import NotFound
from app.db import get_db
from app.models import DailyReport
from app.modules.public_api.auth import PublicPrincipal, require_scope
from app.modules.public_api.schemas import v1

router = APIRouter(prefix="/workspaces/{workspace_id}", tags=["reports"])


@router.get("/reports/daily", response_model=v1.Page[v1.DailyReport], summary="Daglige rapporter (afsluttede dage), nyeste først")
def list_daily_reports(from_date: date | None = Query(default=None, alias="from"),
                       to_date: date | None = Query(default=None, alias="to"),
                       limit: int = Query(31, ge=1, le=366),
                       principal: PublicPrincipal = Depends(require_scope("reports:read")),
                       db: OrmSession = Depends(get_db)):
    q = select(DailyReport).where(DailyReport.workspace_id == principal.workspace_id)
    if from_date is not None:
        q = q.where(DailyReport.report_date >= from_date)
    if to_date is not None:
        q = q.where(DailyReport.report_date <= to_date)
    rows = db.scalars(q.order_by(DailyReport.report_date.desc()).limit(limit)).all()
    return {"items": [v1.daily_report_out(r) for r in rows], "next_cursor": None}


@router.get("/reports/daily/{report_date}", response_model=v1.DailyReport, summary="Rapporten for én dag")
def get_daily_report(report_date: date, principal: PublicPrincipal = Depends(require_scope("reports:read")),
                     db: OrmSession = Depends(get_db)) -> v1.DailyReport:
    r = db.scalar(select(DailyReport).where(DailyReport.workspace_id == principal.workspace_id,
                                            DailyReport.report_date == report_date))
    if r is None:
        raise NotFound("Der er ingen rapport for den dag")
    return v1.daily_report_out(r)
