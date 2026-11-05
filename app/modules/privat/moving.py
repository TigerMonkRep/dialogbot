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
    task = service.create_digital(db, ctx, kind="list", title=f"Flytning{': ' + to if to else ''}"[:300], items=items,
                                  list_type="todo")
    task.next_step = f"Flyttedag {kit.date_text(d)}"
    move = {"id": kit.new_id(), "day": d, "to": to, "task_id": str(task.id)}
    kit.save_items(db, ctx.ws_id, ADDON, [move])   # one move at a time
    return task, move


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


def due(data: dict, today: date) -> list[tuple[str, str]]:
    out = []
    for m in data.get("items", []):
        day = date.fromisoformat(m["day"])
        for n, text, _ in CHECKLIST:
            if 0 <= (today - (day - timedelta(days=n))).days <= 2:   # on the day, or a little late
                out.append((f"{m['id']}:{n}", f"Flytning {kit.date_text(m['day'])}: {text}."))
    return out
