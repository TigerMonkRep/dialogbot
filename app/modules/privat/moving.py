"""The Flytning app: the moving checklist with dates, and help with the calls.

`plan` makes an ordinary to-do list «Flytning: <til>» (sharing and ticking off as for any list) from the checklist
below, each item with its date counted back from the moving day, and remembers the move (`private_app_data`
«flytning»). Reminders: one on the day each item is due. The address change itself the user does on
borger.dk (MitID) – Dialogbot never does that. Movers: «Find 3 flyttefirmaer» goes through Håndværker & tilbud (a
referral = lead revenue). Revenue: disclosed partner links for electricity, internet, insurance and movers.
"""
from __future__ import annotations

import uuid
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session as OrmSession

from app.core.errors import ValidationFailed
from app.models import PrivateTask, PrivateTaskItem
from app.modules.privat import app_kit as kit
from app.modules.privat import brand, service

ADDON, PATH = "flytning", "/privat/apps/flytning"


def _today() -> date:
    from app.modules.privat import rules

    return rules.local().date()
# (days before the move – negative = after, text, partner category)
CHECKLIST = (
    (90, "Opsig lejemålet (typisk 3 måneders varsel) eller sæt boligen til salg", None),
    (45, "Få tilbud fra flyttefirmaer – eller book en trailer", "flyttefirma"),
    (30, "Flyt eller opsig internet og tv", "internet"),
    (30, "Giv institution, skole og arbejde besked", None),
    (21, "Flyt el-aftalen til den nye adresse", "el"),
    (21, "Flyt indboforsikringen", "forsikring"),
    (14, "Bestil flyttekasser og pakkemateriale", None),
    (7, "Giv bank, læge, tandlæge og abonnementer den nye adresse", None),
    (2, "Pak en kasse med det, I skal bruge den første nat", None),
    (0, "Aflæs el, vand og varme i begge boliger – tag billeder", None),
    (-1, "Meld flytning på borger.dk (fra flyttedagen og senest 5 dage efter)", None),
    (-3, "Tjek at posten kommer frem på den nye adresse", None),
)


def plan(db: OrmSession, ctx, *, moving_day: str, to: str = "") -> tuple[PrivateTask, dict]:
    d = kit.parse_date(moving_day, "moving_day", required=True)
    day = date.fromisoformat(d)
    if day < _today() - timedelta(days=7):
        raise ValidationFailed("Flyttedagen ligger i fortiden", field_errors=[{"field": "moving_day"}])
    to = kit.clean(to, 100)
    items = [f"{text} ({kit.date_text((day - timedelta(days=n)).isoformat())})" for n, text, _ in CHECKLIST]
    items += _from_other_apps(db, ctx.ws_id, day)
    task = service.create_digital(db, ctx, kind="list", title=f"Flytning{': ' + to if to else ''}"[:300], items=items,
                                  list_type="todo")
    task.next_step = f"Flyttedag {kit.date_text(d)}"
    move = {"id": kit.new_id(), "day": d, "to": to, "task_id": str(task.id)}
    kit.save_items(db, ctx.ws_id, ADDON, [move])   # one move at a time
    return task, move


def _from_other_apps(db: OrmSession, ws_id: uuid.UUID, day: date) -> list[str]:
    """The move touches the other apps: the subscriptions tied to the address (Abonnementer) and the home's jobs."""
    from app.modules.privat import addons, subs_app

    out = []
    if addons.is_enabled(db, ws_id, subs_app.ADDON):
        tied = [r["name"] for r in kit.items(db, ws_id, subs_app.ADDON)
                if r.get("status") != "cancelled" and r.get("category") in ("internet", "el", "forsikring")]
        if tied:
            out.append(f"Flyt eller opsig {', '.join(tied[:6])} ({kit.date_text((day - timedelta(days=30)).isoformat())})")
    if addons.is_enabled(db, ws_id, "hus-og-vedligehold"):
        out.append(f"Vælg de faste opgaver i det nye hjem i Hus & vedligehold "
                   f"({kit.date_text((day + timedelta(days=7)).isoformat())})")
    return out


def partner_lines() -> list[str]:
    out = []
    for cat in ("flyttefirma", "el", "internet", "forsikring"):
        if (o := brand.offer(cat)):
            out.append(f"{o['text']}: {o['url']}")
    return out + ([f"({brand.AD_NOTE})"] if out else [])


def _open_items(db: OrmSession, move: dict) -> list[str]:
    task = db.get(PrivateTask, uuid.UUID(move["task_id"])) if move.get("task_id") else None
    if task is None:
        return []
    return list(db.scalars(select(PrivateTaskItem.text).where(PrivateTaskItem.task_id == task.id,
                                                               PrivateTaskItem.done.is_(False))
                           .order_by(PrivateTaskItem.position)))


def overview(db: OrmSession, ws_id: uuid.UUID) -> dict:
    rows = kit.items(db, ws_id, ADDON)
    if not rows:
        return {"summary": "Ingen flytning planlagt. Sig fx «Vi flytter til Odense den 1. april».", "items": [],
                "partner": brand.offer("flyttefirma")}
    m = rows[0]
    left = _open_items(db, m)
    return {"summary": f"Flyttedag {kit.date_text(m['day'])}{' til ' + m['to'] if m.get('to') else ''} – "
                       f"{len(left)} ting tilbage på listen.",
            "items": [{"id": m["id"], "text": f"Flytning{' til ' + m['to'] if m.get('to') else ''}",
                       "sub": "; ".join(left[:4])}],
            "partner": brand.offer("flyttefirma") or brand.offer("el") or brand.offer("internet")}


def remove(db: OrmSession, ws_id: uuid.UUID, item_id: str) -> bool:
    return kit.remove_item(db, ws_id, ADDON, item_id)


def due_for(db: OrmSession, data: dict, today: date) -> list[tuple[str, str]]:
    """`due`, but only for checklist points still OPEN on the move's list – ticked off or deleted means done
    (F-PA-04). Without the list (deleted) nothing is reminded either."""
    out = []
    for m in data.get("items", []):
        task = db.get(PrivateTask, uuid.UUID(m["task_id"])) if m.get("task_id") else None
        open_items = _open_items(db, m) if task is not None else None
        for tag, text in due({"items": [m]}, today):
            n = int(tag.rsplit(":", 1)[1])
            point = next((t for k, t, _ in CHECKLIST if k == n), "")
            if open_items is None and m.get("task_id"):
                continue  # the list is gone
            if open_items is not None and not any(i.startswith(point) for i in open_items):
                continue
            out.append((tag, text))
    return out


def due(data: dict, today: date) -> list[tuple[str, str]]:
    out = []
    for m in data.get("items", []):
        day = date.fromisoformat(m["day"])
        for n, text, _ in CHECKLIST:
            if 0 <= (today - (day - timedelta(days=n))).days <= 2:   # on the day, or a little late
                out.append((f"{m['id']}:{n}", f"Flytning {kit.date_text(m['day'])}: {text}."))
    return out
