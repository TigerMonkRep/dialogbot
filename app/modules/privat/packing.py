"""The Pakkeliste app: packing lists for trips that are kept for next time.

A packing list is an ordinary to-do list (sharing, ticking off and the quota work as for any list); the app remembers
which lists are packing lists (`private_app_data` «pakkeliste»: `lists` = [{task_id, trip, at}]). «Brug den fra sidst»
copies the newest one's items into a new list with nothing ticked off.
"""
from __future__ import annotations

import re
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session as OrmSession

from app.models import PrivateTask, PrivateTaskItem
from app.modules.privat import appdata, rules, service

ADDON = "pakkeliste"
KEEP = 30


def _remember(db: OrmSession, ws_id: uuid.UUID, task: PrivateTask, trip: str) -> None:
    data = appdata.get(db, ws_id, ADDON)
    lists = [x for x in data.get("lists", []) if x.get("task_id") != str(task.id)]
    lists.insert(0, {"task_id": str(task.id), "trip": trip[:200], "at": rules.now().isoformat()})
    appdata.put(db, ws_id, ADDON, {**data, "lists": lists[:KEEP]})


def create(db: OrmSession, ctx, *, trip: str, items: list[str]) -> PrivateTask:
    trip = " ".join((trip or "").split())[:200] or "turen"
    items = [" ".join(str(i).split())[:300] for i in items if str(i).strip()][:150]
    task = service.create_digital(db, ctx, kind="list", title=f"Pakkeliste: {trip}"[:300], items=items, list_type="todo")
    task.next_step = "Kryds af, mens I pakker"
    _remember(db, ctx.ws_id, task, trip)
    return task


def previous(db: OrmSession, ws_id: uuid.UUID) -> tuple[PrivateTask, list[str]] | None:
    """The newest packing list that still exists, with its items."""
    for x in appdata.get(db, ws_id, ADDON).get("lists", []):
        task = db.get(PrivateTask, uuid.UUID(x["task_id"]))
        if task is not None and task.workspace_id == ws_id:
            items = list(db.scalars(select(PrivateTaskItem.text).where(PrivateTaskItem.task_id == task.id)
                                    .order_by(PrivateTaskItem.position, PrivateTaskItem.id)))
            return task, items
    return None


def reuse(db: OrmSession, ctx, *, trip: str | None = None) -> PrivateTask | None:
    prev = previous(db, ctx.ws_id)
    if prev is None:
        return None
    old, items = prev
    base = trip or re.sub(r" · \d{1,2}/\d{1,2}$", "", old.title.removeprefix("Pakkeliste: "))
    today = rules.local()
    return create(db, ctx, trip=f"{base} · {today.day}/{today.month}", items=items)
