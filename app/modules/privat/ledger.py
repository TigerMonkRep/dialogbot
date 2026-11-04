"""Credit ledger. Balance = SUM(amount); every movement has a unique `source_ref`, so the same command or webhook can
never move credits twice (a repeat returns False and changes nothing)."""
from __future__ import annotations

import uuid
from datetime import timedelta

from sqlalchemy import and_, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as OrmSession
from sqlalchemy.orm import aliased

from app.models import CreditLedger
from app.modules.privat import rules


def add(db: OrmSession, ws_id: uuid.UUID, *, kind: str, amount: int, source_ref: str, text: str,
        task_id: uuid.UUID | None = None) -> bool:
    """Insert one movement. False (and nothing written) when `source_ref` already exists."""
    if db.scalar(select(CreditLedger.id).where(CreditLedger.source_ref == source_ref)) is not None:
        return False
    try:
        with db.begin_nested():
            db.add(CreditLedger(workspace_id=ws_id, kind=kind, amount=amount, source_ref=source_ref, text=text[:300],
                                task_id=task_id, created_at=rules.now()))
    except IntegrityError:  # a concurrent writer won the unique source_ref
        return False
    return True


def exists(db: OrmSession, source_ref: str) -> bool:
    return db.scalar(select(CreditLedger.id).where(CreditLedger.source_ref == source_ref)) is not None


def balance(db: OrmSession, ws_id: uuid.UUID) -> int:
    return int(db.scalar(select(func.coalesce(func.sum(CreditLedger.amount), 0))
                         .where(CreditLedger.workspace_id == ws_id)) or 0)


def reserved(db: OrmSession, ws_id: uuid.UUID) -> int:
    """Credits held by reservations that are neither captured nor released yet."""
    settle = aliased(CreditLedger)
    open_reserves = select(func.coalesce(func.sum(-CreditLedger.amount), 0)).where(
        CreditLedger.workspace_id == ws_id, CreditLedger.kind == "reserve",
        ~select(settle.id).where(and_(settle.workspace_id == ws_id, settle.kind.in_(("capture", "release")),
                                      settle.source_ref.in_([
                                          func.replace(CreditLedger.source_ref, ":reserve", ":capture"),
                                          func.replace(CreditLedger.source_ref, ":reserve", ":release")]))).exists())
    return int(db.scalar(open_reserves) or 0)


def sponsor_used_today(db: OrmSession, ws_id: uuid.UUID) -> int:
    start_local = rules.local().replace(hour=0, minute=0, second=0, microsecond=0)
    return int(db.scalar(select(func.count()).select_from(CreditLedger).where(
        CreditLedger.workspace_id == ws_id, CreditLedger.kind == "sponsor",
        CreditLedger.created_at >= start_local, CreditLedger.created_at < start_local + timedelta(days=1))) or 0)


def rows(db: OrmSession, ws_id: uuid.UUID, limit: int = 200) -> list[CreditLedger]:
    return list(db.scalars(select(CreditLedger).where(CreditLedger.workspace_id == ws_id)
                           .order_by(CreditLedger.created_at.desc(), CreditLedger.id).limit(limit)))
