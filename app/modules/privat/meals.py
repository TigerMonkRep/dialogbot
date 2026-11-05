"""The Madplan app: the week's dinners, and the shopping list that follows from them.

Peter (the chat model) suggests the dishes from what the household likes and does not eat (`private_app_data`
«madplan»: people, avoid, likes – only what the user wrote). Nothing is saved until the user says yes; then the plan
becomes a to-do list («Mandag: Lasagne») and the ingredients one shopping list, merged so the same thing is there once.
"""
from __future__ import annotations

import re
import uuid

from sqlalchemy.orm import Session as OrmSession

from app.models import PrivateTask
from app.modules.privat import appdata, rules, service

ADDON = "madplan"
DAYS = ("mandag", "tirsdag", "onsdag", "torsdag", "fredag", "lørdag", "søndag")


def preferences(db: OrmSession, ws_id: uuid.UUID) -> dict:
    return appdata.get(db, ws_id, ADDON)


def save_preferences(db: OrmSession, ws_id: uuid.UUID, *, people: int | None = None, avoid: str | None = None,
                     likes: str | None = None) -> dict:
    if people is not None and not 1 <= people <= 20:
        people = None
    return appdata.update(db, ws_id, ADDON, people=people, avoid=(avoid or "").strip()[:500] or None,
                          likes=(likes or "").strip()[:500] or None)


def preferences_text(p: dict) -> str:
    parts = []
    if p.get("people"):
        parts.append(f"{p['people']} personer")
    if p.get("avoid"):
        parts.append(f"spiser ikke: {p['avoid']}")
    if p.get("likes"):
        parts.append(f"kan lide: {p['likes']}")
    return "; ".join(parts) or "Ingen gemte madvaner endnu."


def _key(s: str) -> str:
    return re.sub(r"\s+", " ", s.strip().lower())


def merge_ingredients(days: list[dict]) -> list[str]:
    """One line per ingredient, in first-seen order; the same ingredient (case and spaces ignored) only once."""
    seen: dict[str, str] = {}
    for d in days:
        for i in d.get("ingredients") or []:
            t = " ".join(str(i).split())[:300]
            if t and _key(t) not in seen:
                seen[_key(t)] = t
    return list(seen.values())[:150]


def save_plan(db: OrmSession, ctx, *, title: str, days: list[dict], shopping: bool = True
              ) -> tuple[PrivateTask, PrivateTask | None]:
    rows = []
    for d in days[:14]:
        dish = " ".join(str(d.get("dish") or "").split())[:200]
        day = str(d.get("day") or "").strip().lower()
        if dish:
            rows.append(f"{day[:1].upper() + day[1:]}: {dish}" if day else dish)
    plan = service.create_digital(db, ctx, kind="list", title=(title or "Madplan")[:300], items=rows, list_type="todo")
    plan.next_step = "Ugens aftensmad"
    shop = None
    ingredients = merge_ingredients(days)
    if shopping and ingredients:
        shop = service.create_digital(db, ctx, kind="list", title=f"Indkøb til {(title or 'madplanen').lower()}"[:300],
                                      items=ingredients, list_type="shopping")
    appdata.update(db, ctx.ws_id, ADDON, last_plan_id=str(plan.id), last_plan_at=rules.now().isoformat())
    return plan, shop
