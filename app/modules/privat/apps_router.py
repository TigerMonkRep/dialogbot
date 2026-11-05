"""Privat: the endpoints of the small apps in the shop (docs/privat-api.md «Apps»). Each resolves the caller's own
personal workspace and needs its app switched on (403 addon_disabled)."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session as OrmSession

from app.db import get_db
from app.modules.privat import addons, birthdays
from app.modules.privat.deps import PrivateCtx, private_ctx

router = APIRouter(prefix="/privat", tags=["privat-apps"])


# --------------------------------------------------------------------------- Fødselsdage

class BirthdayIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    date: str = Field(min_length=1, max_length=40, description="«14. marts», «14.03.1946» or «1946-03-14»")
    remind_days_before: int | None = Field(default=None, ge=0, le=60)


class BirthdayPatch(BaseModel):
    remind_days_before: int = Field(ge=0, le=60)


@router.get("/birthdays")
def list_birthdays(ctx: PrivateCtx = Depends(private_ctx), db: OrmSession = Depends(get_db)):
    addons.require(db, ctx.ws_id, birthdays.ADDON)
    return {"items": [birthdays.out(b) for b in birthdays.all_for(db, ctx.ws_id)]}


@router.post("/birthdays")
def add_birthday(body: BirthdayIn, ctx: PrivateCtx = Depends(private_ctx), db: OrmSession = Depends(get_db)):
    """Adds the birthday, or changes the date of the person with the same name."""
    addons.require(db, ctx.ws_id, birthdays.ADDON)
    b, created = birthdays.save(db, ctx.ws_id, name=body.name, when=body.date, remind_days_before=body.remind_days_before)
    db.commit()
    return {**birthdays.out(b), "created": created}


@router.patch("/birthdays/{birthday_id}")
def update_birthday(birthday_id: uuid.UUID, body: BirthdayPatch, ctx: PrivateCtx = Depends(private_ctx),
                    db: OrmSession = Depends(get_db)):
    addons.require(db, ctx.ws_id, birthdays.ADDON)
    b = birthdays.set_days(db, birthdays.own(db, ctx.ws_id, birthday_id), body.remind_days_before)
    db.commit()
    return birthdays.out(b)


@router.delete("/birthdays/{birthday_id}", status_code=204)
def delete_birthday(birthday_id: uuid.UUID, ctx: PrivateCtx = Depends(private_ctx), db: OrmSession = Depends(get_db)):
    addons.require(db, ctx.ws_id, birthdays.ADDON)
    birthdays.remove(db, birthdays.own(db, ctx.ws_id, birthday_id))
    db.commit()
    return Response(status_code=204)
