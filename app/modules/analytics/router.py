"""Operator-only website statistics (Vercel Web Analytics + Google Analytics 4), read server-side with cached results."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.core.auth import Principal
from app.modules.analytics import service
from app.modules.voices.operator_router import operator

router = APIRouter(prefix="/operator/analytics", tags=["analytics-operator"])


@router.get("/website")
def website(days: int = Query(default=30, ge=1, le=365), _: Principal = Depends(operator)) -> dict:
    """Visitors, page views, top pages, referrers and so on for dialogbot.dk from both sources. Each half says
    whether it is configured; an unconfigured half is not an error, it just has no numbers yet."""
    return service.website_stats(days)
