"""The Madplan app: the week's dinners, and the shopping list that follows from them.

Peter (the chat model) suggests the dishes from what the household likes and does not eat (`private_app_data`
«madplan»: people, avoid, likes – only what the user wrote). Nothing is saved until the user says yes; then the plan
becomes a to-do list («Mandag: Lasagne», with the dish's ingredients as the item's note) and the ingredients one
shopping list. Amounts are scaled to the number of people (a dish's `servings` → the plan's `people`) and the same
ingredient is there once with the amounts added up («500 g» + «250 g hakket oksekød» = «750 g hakket oksekød»).
Ordering the groceries: a disclosed partner link (brand.offer("dagligvarer")) – Danish grocery shops have no open
basket API yet, so a one-click basket needs a partner agreement (docs/sales/privat-revenue.md).
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


def _item_key(name: str) -> str:
    """«2 peberfrugt» and «2 peberfrugter», «tomat» and «tomater», «æble» and «æbler» are one line: the last word
    without its plural ending."""
    words = _key(name).split(" ")
    w = words[-1]
    for end in ("er", "r", "e"):
        if len(w) > len(end) + 2 and w.endswith(end):
            w = w[: -len(end)]
            break
    return " ".join(words[:-1] + [w])


UNITS = {"g": ("g", 1), "gram": ("g", 1), "kg": ("g", 1000), "ml": ("ml", 1), "cl": ("ml", 10), "dl": ("ml", 100),
         "l": ("ml", 1000), "liter": ("ml", 1000), "stk": ("stk", 1), "stk.": ("stk", 1), "spsk": ("spsk", 1),
         "spsk.": ("spsk", 1), "tsk": ("tsk", 1), "tsk.": ("tsk", 1), "dåse": ("dåse", 1), "dåser": ("dåse", 1),
         "ds": ("dåse", 1), "ds.": ("dåse", 1), "pakke": ("pakke", 1), "pakker": ("pakke", 1), "pk": ("pakke", 1),
         "pk.": ("pakke", 1), "fed": ("fed", 1), "bundt": ("bundt", 1)}
_AMOUNT = re.compile(r"^(\d+(?:[.,]\d+)?|½|¼)\s*([a-zæøå.]+)?\s+(.+)$", re.I)


def parse_ingredient(raw) -> tuple[float | None, str, str]:
    """(amount in the base unit or None, base unit or "", name). «500 g hakket oksekød» → (500, "g", "hakket oksekød");
    «2 løg» → (2, "", "løg"); «Salt» → (None, "", "Salt"). A dict {name, amount, unit} works too."""
    if isinstance(raw, dict):
        raw = f"{raw.get('amount') or ''} {raw.get('unit') or ''} {raw.get('name') or ''}"
    t = " ".join(str(raw).split())[:300]
    m = _AMOUNT.match(t)
    if not m:
        return None, "", t
    n = {"½": 0.5, "¼": 0.25}.get(m.group(1)) or float(m.group(1).replace(",", "."))
    unit = (m.group(2) or "").lower()
    if unit and unit not in UNITS:   # «2 store løg»: the word is part of the name
        return n, "", f"{m.group(2)} {m.group(3)}"
    base, factor = UNITS.get(unit, ("", 1))
    return n * factor, base, m.group(3)


COUNTABLE = ("", "stk", "dåse", "pakke", "fed", "bundt")


def _fmt(amount: float, unit: str, name: str) -> str:
    if unit in COUNTABLE:   # things you buy whole: ½ løg is fine, 2,7 dåser → 3 (rounded after adding up)
        amount = max(1, int(amount * 2 + 0.5) / 2 if amount < 3 else int(amount + 0.5))
    if unit == "g" and amount >= 1000:
        amount, unit = amount / 1000, "kg"
    elif unit == "ml" and amount >= 1000:
        amount, unit = amount / 1000, "l"
    elif unit == "ml" and amount >= 100 and amount % 100 == 0:
        amount, unit = amount / 100, "dl"
    elif unit == "g" and amount >= 50:
        amount = round(amount / 25) * 25   # 333 g → 325 g: how it is bought
    if amount > 1 and unit in ("dåse", "pakke"):
        unit += "r"
    num = f"{amount:.1f}".rstrip("0").rstrip(".").replace(".", ",") if amount != int(amount) else str(int(amount))
    return f"{num} {unit} {name}" if unit else f"{num} {name}"


def scaled(raw, factor: float) -> tuple[float | None, str, str]:
    n, unit, name = parse_ingredient(raw)
    return (n * factor if n is not None else None), unit, name


def _factor(d: dict, people: int | None) -> float:
    servings = d.get("servings")
    if not people or not isinstance(servings, int | float) or servings <= 0:
        return 1.0
    return people / servings


def dish_ingredients(d: dict, people: int | None = None) -> list[str]:
    f = _factor(d, people)
    return [_fmt(n, u, name) if n is not None else name for n, u, name in
            (scaled(i, f) for i in d.get("ingredients") or [] if str(i).strip())][:40]


def merge_ingredients(days: list[dict], people: int | None = None) -> list[str]:
    """One line per ingredient, in first-seen order; the same ingredient (case and spaces ignored) once, with the
    amounts in the same unit added up and scaled to `people`."""
    seen: dict[tuple[str, str], list] = {}
    for d in days:
        f = _factor(d, people)
        for i in d.get("ingredients") or []:
            n, unit, name = scaled(i, f)
            if not name.strip():
                continue
            k = (_item_key(name), unit)
            if k in seen:
                if n is not None and seen[k][0] is not None:
                    seen[k][0] += n
                if len(name) > len(seen[k][2]):   # «peberfrugter» over «peberfrugt»: the plural reads right for 2+
                    seen[k][2] = name
            else:
                seen[k] = [n, unit, name]
    out = [(_fmt(n, u, name) if n is not None else name) for n, u, name in seen.values()]
    return [o[:1].upper() + o[1:] for o in out][:150]


def save_plan(db: OrmSession, ctx, *, title: str, days: list[dict], shopping: bool = True, people: int | None = None
              ) -> tuple[PrivateTask, PrivateTask | None]:
    rows = []
    for d in days[:14]:
        dish = " ".join(str(d.get("dish") or "").split())[:200]
        day = str(d.get("day") or "").strip().lower()
        if dish:
            rows.append(f"{day[:1].upper() + day[1:]}: {dish}" if day else dish)
    plan = service.create_digital(db, ctx, kind="list", title=(title or "Madplan")[:300], items=rows, list_type="todo")
    plan.next_step = "Ugens aftensmad" + (f" til {people}" if people else "")
    _notes(db, plan, [dish_ingredients(d, people) for d in days[:14] if " ".join(str(d.get("dish") or "").split())])
    shop = None
    ingredients = merge_ingredients(days, people)
    if shopping and ingredients:
        shop = service.create_digital(db, ctx, kind="list", title=f"Indkøb til {(title or 'madplanen').lower()}"[:300],
                                      items=ingredients, list_type="shopping")
    # The lists this app made, so «Slet appens data» takes them too (app_status.delete_data, F-PA-01).
    made = list(appdata.get(db, ctx.ws_id, ADDON).get("lists") or [])
    made += [{"task_id": str(t.id)} for t in (plan, shop) if t is not None]
    appdata.update(db, ctx.ws_id, ADDON, last_plan_id=str(plan.id), last_plan_at=rules.now().isoformat(), lists=made[-200:])
    return plan, shop


def _notes(db: OrmSession, plan: PrivateTask, per_dish: list[list[str]]) -> None:
    """Each day's ingredients on its row, so the recipe is one tap away."""
    from sqlalchemy import select

    from app.models import PrivateTaskItem

    rows = list(db.scalars(select(PrivateTaskItem).where(PrivateTaskItem.task_id == plan.id)
                           .order_by(PrivateTaskItem.position, PrivateTaskItem.created_at)))
    for row, ing in zip(rows, per_dish, strict=False):
        if ing:
            row.note = ", ".join(ing)[:500]
    db.flush()
