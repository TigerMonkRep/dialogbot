"""Privat: the user's answer to a browser booking (docs/privat-api.md «Booking på hjemmeside»).

`approve` / `decline` are idempotent (repeat = same state; `Idempotency-Key` replays the stored answer). Everything is
reached through the task (private_task_members), so another user's task id is a plain 404.
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Header, Response
from sqlalchemy.orm import Session as OrmSession

from app.core.idempotency import IdempotencyGuard, scope_for
from app.db import get_db
from app.modules.browser import service
from app.modules.privat.deps import PrivateCtx, private_ctx

router = APIRouter(prefix="/privat/tasks", tags=["privat-browser"])


@router.get("/{task_id}/browser")
def get_run(task_id: uuid.UUID, ctx: PrivateCtx = Depends(private_ctx), db: OrmSession = Depends(get_db)):
    """The latest run for the task, without internal selectors; evidence links are signed and expire after minutes."""
    _, run = service.latest_run(db, ctx, task_id)
    return service.run_out(run)


def _answer(kind: str, fn, task_id, response, ctx, db, key):
    guard = IdempotencyGuard(db, scope_for(ctx.user_id, f"privat.browser.{kind}", ctx.ws_id), key,
                             {"task_id": str(task_id)})
    if guard.replay:
        response.status_code = guard.replay[0]
        return guard.replay[1]
    out = service.run_out(fn(db, ctx, task_id))
    guard.store(200, out)
    db.commit()
    return out


@router.post("/{task_id}/browser/approve")
def approve(task_id: uuid.UUID, response: Response, ctx: PrivateCtx = Depends(private_ctx),
            db: OrmSession = Depends(get_db), idempotency_key: str | None = Header(default=None, alias="Idempotency-Key")):
    return _answer("approve", service.approve, task_id, response, ctx, db, idempotency_key)


@router.post("/{task_id}/browser/decline")
def decline(task_id: uuid.UUID, response: Response, ctx: PrivateCtx = Depends(private_ctx),
            db: OrmSession = Depends(get_db), idempotency_key: str | None = Header(default=None, alias="Idempotency-Key")):
    return _answer("decline", service.decline, task_id, response, ctx, db, idempotency_key)
