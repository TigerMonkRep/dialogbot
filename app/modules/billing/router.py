from __future__ import annotations

import re
from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session as OrmSession

from app.core.auth import WorkspaceContext, require_capability
from app.core.errors import ValidationFailed
from app.db import get_db
from app.modules.billing.statement import statement
from app.modules.reports.service import local_today, tz_of

router = APIRouter(prefix="/workspaces/{workspace_id}/billing", tags=["billing"])


@router.get("/statement")
def get_statement(month: str | None = Query(default=None, description="YYYY-MM; default: current month"),
                  ctx: WorkspaceContext = Depends(require_capability("billing.read")), db: OrmSession = Depends(get_db)):
    """Preview of what the month would cost under the agreement. Not an invoice; nothing is charged."""
    tz = tz_of(db, ctx.workspace.id)
    if month is None:
        m = local_today(tz).replace(day=1)
    elif re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", month):
        m = date(int(month[:4]), int(month[5:]), 1)
    else:
        raise ValidationFailed("month skal være på formen ÅÅÅÅ-MM", field_errors=[{"field": "month"}])
    return statement(db, ctx.workspace.id, m, tz)
