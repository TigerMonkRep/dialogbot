"""The Fælles udgifter app: who paid what on the trip, in the summer house or in the shared flat – and who owes whom.

Saved (`private_app_data` «faelles-udgifter», `items` = groups): a name, the people (first names, as the user writes
them), and expenses (who paid, amount, what for, shared among whom – everyone by default). Settling up gives the
fewest transfers. Dialogbot never moves money (MobilePay has no open API for private users): it calculates and
writes a summary the user can send to the others – with Dialogbot's footer, so the friends see where it came from.
"""
from __future__ import annotations

import uuid

from sqlalchemy.orm import Session as OrmSession

from app.core.errors import ValidationFailed
from app.modules.privat import app_kit as kit
from app.modules.privat import brand, rules

ADDON, PATH = "faelles-udgifter", "/privat/apps/faelles-udgifter"
MAX_GROUPS, MAX_EXPENSES, MAX_PEOPLE = 30, 300, 30


def _name(s: str) -> str:
    s = kit.clean(s, 40)
    return s[:1].upper() + s[1:]


def _person(group: dict, raw: str, me: str) -> str:
    n = _name(raw)
    if kit.key_of(n) in ("jeg", "mig", "mig selv"):
        n = me
    hit = next((p for p in group["people"] if kit.key_of(p) == kit.key_of(n)), None)
    if hit:
        return hit
    if len(group["people"]) >= MAX_PEOPLE:
        raise ValidationFailed("Der er for mange personer i gruppen", field_errors=[{"field": "people"}])
    group["people"].append(n)
    return n


def group_for(rows: list[dict], name: str | None) -> dict | None:
    if name:
        return kit.find(rows, name)
    return rows[0] if rows else None


def add_expense(db: OrmSession, ws_id: uuid.UUID, *, me: str, group: str | None, paid_by: str, amount, text: str = "",
                among: list[str] | None = None, people: list[str] | None = None) -> tuple[dict, dict]:
    minor = kit.amount(amount, required=True)
    if not minor:
        raise ValidationFailed("Beløbet skal være over 0 kr.", field_errors=[{"field": "amount"}])
    rows = kit.items(db, ws_id, ADDON)
    g = group_for(rows, group)
    if g is None:
        if len(rows) >= MAX_GROUPS:
            raise ValidationFailed("Du har for mange grupper – slet en gammel først", field_errors=[{"field": "group"}])
        g = {"id": kit.new_id(), "name": kit.clean(group, 60) or "Fælles udgifter", "people": [], "expenses": []}
        rows.insert(0, g)
    for p in people or []:
        _person(g, p, me)
    payer = _person(g, paid_by or me, me)
    split = [_person(g, p, me) for p in (among or [])] or None
    if len(g["expenses"]) >= MAX_EXPENSES:
        raise ValidationFailed("Gruppen har for mange udgifter", field_errors=[{"field": "amount"}])
    e = {"id": kit.new_id(), "payer": payer, "amount_minor": minor, "text": kit.clean(text, 120),
         "among": split, "at": rules.now().isoformat()}
    g["expenses"].append(e)
    kit.save_items(db, ws_id, ADDON, rows)
    return g, e


def balances(g: dict) -> dict[str, int]:
    """+ = is owed money, - = owes. Shares are split in whole øre; the leftover øre go to the first people."""
    bal = {p: 0 for p in g["people"]}
    for e in g["expenses"]:
        among = e.get("among") or g["people"]
        share, rest = divmod(e["amount_minor"], len(among))
        bal[e["payer"]] = bal.get(e["payer"], 0) + e["amount_minor"]
        for i, p in enumerate(among):
            bal[p] = bal.get(p, 0) - share - (1 if i < rest else 0)
    return bal


def settle(g: dict) -> list[tuple[str, str, int]]:
    """The fewest transfers (debtor, creditor, øre): largest debtor pays largest creditor first."""
    bal = balances(g)
    debt = sorted([[p, -v] for p, v in bal.items() if v < 0], key=lambda x: -x[1])
    cred = sorted([[p, v] for p, v in bal.items() if v > 0], key=lambda x: -x[1])
    out, i, j = [], 0, 0
    while i < len(debt) and j < len(cred):
        n = min(debt[i][1], cred[j][1])
        out.append((debt[i][0], cred[j][0], n))
        debt[i][1] -= n
        cred[j][1] -= n
        i += debt[i][1] == 0
        j += cred[j][1] == 0
    return out


def summary_text(g: dict, *, share: bool = False) -> str:
    total = sum(e["amount_minor"] for e in g["expenses"])
    lines = [f"{g['name']}: {kit.money(total)} i alt fordelt på {len(g['people'])} personer."]
    moves = settle(g)
    lines += [f"- {a} betaler {kit.money(n)} til {b}" for a, b, n in moves] or ["- I er kvit."]
    text = "\n".join(lines)
    return brand.branded(text) if share else text


def overview(db: OrmSession, ws_id: uuid.UUID) -> dict:
    rows = kit.items(db, ws_id, ADDON)
    return {"summary": f"{len(rows)} grupper." if rows else
            "Ingen fælles udgifter endnu. Sig fx «Jeg betalte 1.200 kr. for mad i sommerhuset – vi er Anna, Bo og mig».",
            "items": [{"id": g["id"], "text": g["name"], "sub": " · ".join(summary_text(g).split("\n")[1:4]),
                       "share_text": summary_text(g, share=True)} for g in rows],
            "partner": None}


def remove(db: OrmSession, ws_id: uuid.UUID, item_id: str) -> bool:
    return kit.remove_item(db, ws_id, ADDON, item_id)
