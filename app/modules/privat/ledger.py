"""The «Opkaldssaldo»: a prepaid balance in kroner (Fürster's decision 2026-11-11, F-PDEC-01). Amounts are øre –
minor units of the account's currency, incl. VAT. Balance = SUM(amount) of the rows in the account's currency; every
movement has a unique `source_ref`, so the same command or webhook can never move money twice (a repeat returns False
and changes nothing).

Currency: the account's Privat currency (private_subscriptions.currency – kept from the first Checkout), else DKK.
The welcome bonus is granted in DKK before any Checkout; when the first Checkout gives the account another currency,
`adopt_currency` moves the DKK balance over once (two 'convert' rows: the untouched welcome bonus becomes the round bonus
of the new currency, markets.PRIVAT_BALANCE; anything else at the factor, markets.privat_from_dkk).

Extra calls (calls.py) reserve first and settle once (a website booking is included in the plan and moves nothing,
F-PDEC-02; a run started before that releases its old reservation when it ends):
  reserve  −held                      (<what>:<id>:reserve)
  capture  +(held − price)            (<what>:<id>:capture)  the rest comes back, the price stays spent
  release  +held                      (<what>:<id>:release)  nothing was spent
"""
from __future__ import annotations

import uuid
from datetime import timedelta

from sqlalchemy import and_, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as OrmSession
from sqlalchemy.orm import aliased

from app.models import CreditLedger, PrivateSubscription
from app.modules.billing import markets
from app.modules.privat import rules


def currency(db: OrmSession, ws_id: uuid.UUID) -> str:
    row = db.get(PrivateSubscription, ws_id)
    return row.currency if row is not None and row.currency in markets.CURRENCIES else "DKK"


def add(db: OrmSession, ws_id: uuid.UUID, *, kind: str, amount: int, source_ref: str, text: str,
        task_id: uuid.UUID | None = None, cur: str | None = None) -> bool:
    """Insert one movement (øre, in the account's currency unless `cur`). False (and nothing written) when
    `source_ref` already exists."""
    if db.scalar(select(CreditLedger.id).where(CreditLedger.source_ref == source_ref)) is not None:
        return False
    try:
        with db.begin_nested():
            db.add(CreditLedger(workspace_id=ws_id, kind=kind, amount=int(amount), source_ref=source_ref,
                                text=text[:300], task_id=task_id, currency=cur or currency(db, ws_id),
                                created_at=rules.now()))
    except IntegrityError:  # a concurrent writer won the unique source_ref
        return False
    return True


def exists(db: OrmSession, source_ref: str) -> bool:
    return db.scalar(select(CreditLedger.id).where(CreditLedger.source_ref == source_ref)) is not None


def amount_of(db: OrmSession, source_ref: str) -> int | None:
    return db.scalar(select(CreditLedger.amount).where(CreditLedger.source_ref == source_ref))


def balance(db: OrmSession, ws_id: uuid.UUID) -> int:
    """What is on the Opkaldssaldo now (øre; open reservations already taken off)."""
    return _sum(db, ws_id, currency(db, ws_id))


def _sum(db: OrmSession, ws_id: uuid.UUID, cur: str) -> int:
    return int(db.scalar(select(func.coalesce(func.sum(CreditLedger.amount), 0))
                         .where(CreditLedger.workspace_id == ws_id, CreditLedger.currency == cur)) or 0)


def reserved(db: OrmSession, ws_id: uuid.UUID) -> int:
    """Øre held by reservations that are neither captured nor released yet."""
    settle = aliased(CreditLedger)
    open_reserves = select(func.coalesce(func.sum(-CreditLedger.amount), 0)).where(
        CreditLedger.workspace_id == ws_id, CreditLedger.kind == "reserve",
        ~select(settle.id).where(and_(settle.workspace_id == ws_id, settle.kind.in_(("capture", "release")),
                                      settle.source_ref.in_([
                                          func.replace(CreditLedger.source_ref, ":reserve", ":capture"),
                                          func.replace(CreditLedger.source_ref, ":reserve", ":release")]))).exists())
    return int(db.scalar(open_reserves) or 0)


def reserve(db: OrmSession, ws_id: uuid.UUID, ref: str, held: int, *, text: str, task_id: uuid.UUID | None = None) -> bool:
    return add(db, ws_id, kind="reserve", amount=-held, source_ref=f"{ref}:reserve", text=text, task_id=task_id)


def settle(db: OrmSession, ws_id: uuid.UUID, ref: str, price: int | None, *, text: str,
           task_id: uuid.UUID | None = None) -> int | None:
    """Settle the reservation `ref` once: `price` None = release everything, else capture `price` (never more than was
    held) and give back the rest. Returns what was spent (øre), or None when there was nothing to settle (no
    reservation, or already settled – a replay changes nothing)."""
    held = amount_of(db, f"{ref}:reserve")
    if held is None or exists(db, f"{ref}:capture") or exists(db, f"{ref}:release"):
        return None
    held = -held
    if price is None:
        return 0 if add(db, ws_id, kind="release", amount=held, source_ref=f"{ref}:release", text=text,
                        task_id=task_id) else None
    spent = max(0, min(int(price), held))
    return spent if add(db, ws_id, kind="capture", amount=held - spent, source_ref=f"{ref}:capture", text=text,
                        task_id=task_id) else None


def adopt_currency(db: OrmSession, ws_id: uuid.UUID, new: str) -> None:
    """The account got its currency at its first Checkout: move a DKK balance from before (the welcome bonus) into it,
    once. Called right after private_subscriptions.currency is set."""
    if new == "DKK" or new not in markets.CURRENCIES:
        return
    old = _sum(db, ws_id, "DKK")
    if old <= 0:
        return
    # The untouched welcome bonus becomes the round bonus of the new currency (markets.PRIVAT_BALANCE); only what else is
    # on the DKK balance (a spent part of it, never the bonus itself) moves at the market's factor.
    welcome = rules.WELCOME_BONUS_MINOR if amount_of(db, f"welcome:{ws_id}") == rules.WELCOME_BONUS_MINOR else 0
    if welcome and old >= welcome:
        moved = markets.privat_balance_amount(new, "welcome") + markets.privat_from_dkk(old - welcome, new)
    else:
        moved = markets.privat_from_dkk(old, new)
    ref = f"convert:{ws_id}:DKK-{new}"
    if add(db, ws_id, kind="convert", amount=-old, source_ref=f"{ref}:out", cur="DKK",
           text=f"Saldo flyttet til {new}"):
        add(db, ws_id, kind="convert", amount=moved, source_ref=f"{ref}:in", cur=new,
            text=f"Saldo fra {markets.fmt(old, 'DKK')}")


def sponsor_used_today(db: OrmSession, ws_id: uuid.UUID) -> int:
    start_local = rules.local().replace(hour=0, minute=0, second=0, microsecond=0)
    return int(db.scalar(select(func.count()).select_from(CreditLedger).where(
        CreditLedger.workspace_id == ws_id, CreditLedger.kind == "sponsor",
        CreditLedger.created_at >= start_local, CreditLedger.created_at < start_local + timedelta(days=1))) or 0)


def rows(db: OrmSession, ws_id: uuid.UUID, limit: int = 200) -> list[CreditLedger]:
    return list(db.scalars(select(CreditLedger).where(CreditLedger.workspace_id == ws_id)
                           .order_by(CreditLedger.created_at.desc(), CreditLedger.id).limit(limit)))


def row_out(r: CreditLedger) -> dict:
    """One movement for the API: `amount_minor` in øre of `currency` (never a number of credits)."""
    return {"id": str(r.id), "kind": r.kind, "amount_minor": r.amount, "currency": r.currency, "text": r.text,
            "created_at": r.created_at.isoformat()}


def summary(db: OrmSession, ws_id: uuid.UUID) -> dict:
    """The Opkaldssaldo for /privat/me and the payment sheet: balance and held amount in øre, the extra-call prices and
    the top-ups in the account's currency."""
    cur = currency(db, ws_id)
    return {"balance_minor": balance(db, ws_id), "held_minor": reserved(db, ws_id), "currency": cur,
            "extra_call": markets.privat_extra_call(cur), "topups_minor": list(markets.privat_topups(cur)),
            "extra_task_minor": markets.privat_balance_amount(cur, "extra_task")}
