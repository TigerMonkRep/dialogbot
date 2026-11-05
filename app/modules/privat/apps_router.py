"""Privat: the endpoints of the small apps in the shop (docs/privat-api.md «Apps»). Each resolves the caller's own
personal workspace and needs its app switched on (403 addon_disabled)."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session as OrmSession

from app.db import get_db
from app.modules.privat import addons, bills, birthdays, car, health, meals, parcels
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


# --------------------------------------------------------------------------- Regninger

class BillIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    amount: str | None = Field(default=None, max_length=40, description="«640 kr.», «1.250,50»")
    frequency: str = Field(default="monthly", pattern="^(monthly|quarterly|half_yearly|yearly|once)$")
    due_date: str | None = Field(default=None, max_length=10, description="Next due date, YYYY-MM-DD")
    due_day: int | None = Field(default=None, ge=1, le=31, description="Day of the month, when no due_date")
    remind_days_before: int | None = Field(default=None, ge=0, le=30)


class BillPatch(BaseModel):
    remind_days_before: int = Field(ge=0, le=30)


@router.get("/bills")
def list_bills(ctx: PrivateCtx = Depends(private_ctx), db: OrmSession = Depends(get_db)):
    """Every bill by next due date, plus this month's overview (total of the known amounts)."""
    addons.require(db, ctx.ws_id, bills.ADDON)
    items = [bills.out(b) for b in bills.all_for(db, ctx.ws_id)]
    overview = bills.month_overview(db, ctx.ws_id)
    db.commit()   # due dates that passed have moved on
    return {"items": items, "month": overview}


@router.post("/bills")
def add_bill(body: BillIn, ctx: PrivateCtx = Depends(private_ctx), db: OrmSession = Depends(get_db)):
    addons.require(db, ctx.ws_id, bills.ADDON)
    b, created = bills.save(db, ctx.ws_id, name=body.name, amount=body.amount, frequency=body.frequency,
                            due_date=body.due_date, due_day=body.due_day, remind_days_before=body.remind_days_before)
    db.commit()
    return {**bills.out(b), "created": created}


@router.patch("/bills/{bill_id}")
def update_bill(bill_id: uuid.UUID, body: BillPatch, ctx: PrivateCtx = Depends(private_ctx),
                db: OrmSession = Depends(get_db)):
    addons.require(db, ctx.ws_id, bills.ADDON)
    b = bills.set_days(db, bills.own(db, ctx.ws_id, bill_id), body.remind_days_before)
    db.commit()
    return bills.out(b)


@router.delete("/bills/{bill_id}", status_code=204)
def delete_bill(bill_id: uuid.UUID, ctx: PrivateCtx = Depends(private_ctx), db: OrmSession = Depends(get_db)):
    addons.require(db, ctx.ws_id, bills.ADDON)
    bills.remove(db, bills.own(db, ctx.ws_id, bill_id))
    db.commit()
    return Response(status_code=204)


# --------------------------------------------------------------------------- Madplan, Læge & tandlæge, Bil & syn, Pakker

class FoodPrefsIn(BaseModel):
    people: int | None = Field(default=None, ge=1, le=20)
    avoid: str | None = Field(default=None, max_length=500)
    likes: str | None = Field(default=None, max_length=500)


@router.get("/meals/preferences")
def get_food_preferences(ctx: PrivateCtx = Depends(private_ctx), db: OrmSession = Depends(get_db)):
    addons.require(db, ctx.ws_id, meals.ADDON)
    p = meals.preferences(db, ctx.ws_id)
    return {"people": p.get("people"), "avoid": p.get("avoid") or "", "likes": p.get("likes") or ""}


@router.put("/meals/preferences")
def put_food_preferences(body: FoodPrefsIn, ctx: PrivateCtx = Depends(private_ctx), db: OrmSession = Depends(get_db)):
    addons.require(db, ctx.ws_id, meals.ADDON)
    data = meals.preferences(db, ctx.ws_id)
    data.update(people=body.people, avoid=(body.avoid or "").strip() or None, likes=(body.likes or "").strip() or None)
    from app.modules.privat import appdata

    appdata.put(db, ctx.ws_id, meals.ADDON, data)
    db.commit()
    return {"people": data.get("people"), "avoid": data.get("avoid") or "", "likes": data.get("likes") or ""}


@router.get("/health-contacts")
def get_health_contacts(ctx: PrivateCtx = Depends(private_ctx), db: OrmSession = Depends(get_db)):
    addons.require(db, ctx.ws_id, health.ADDON)
    from app.modules.privat import rules

    return {"items": [{"kind": k, "label": health.KINDS[k], "name": v["name"], "phone_display": rules.phone_display(v["phone"])}
                      for k, v in health.contacts(db, ctx.ws_id).items()]}


@router.delete("/health-contacts/{kind}", status_code=204)
def delete_health_contact(kind: str, ctx: PrivateCtx = Depends(private_ctx), db: OrmSession = Depends(get_db)):
    addons.require(db, ctx.ws_id, health.ADDON)
    health.remove_contact(db, ctx.ws_id, kind)
    db.commit()
    return Response(status_code=204)


class CarIn(BaseModel):
    plate: str | None = Field(default=None, max_length=12)
    inspection_due: str | None = Field(default=None, max_length=10)
    service_due: str | None = Field(default=None, max_length=10)
    tire_reminders: bool | None = None


def _car_out(data: dict) -> dict:
    from app.modules.privat import rules

    w = data.get("workshop")
    return {"plate": data.get("plate"), "inspection_due": data.get("inspection_due"), "service_due": data.get("service_due"),
            "tire_reminders": bool(data.get("tire_reminders")), "summary": car.status_text(data),
            "workshop": {"name": w["name"], "phone_display": rules.phone_display(w["phone"])} if w else None}


@router.get("/car")
def get_car(ctx: PrivateCtx = Depends(private_ctx), db: OrmSession = Depends(get_db)):
    addons.require(db, ctx.ws_id, car.ADDON)
    return _car_out(car.get(db, ctx.ws_id))


@router.put("/car")
def put_car(body: CarIn, ctx: PrivateCtx = Depends(private_ctx), db: OrmSession = Depends(get_db)):
    addons.require(db, ctx.ws_id, car.ADDON)
    data = car.save_car(db, ctx.ws_id, plate=body.plate or None, inspection_due=body.inspection_due or None,
                        service_due=body.service_due or None, tire_reminders=body.tire_reminders)
    db.commit()
    return _car_out(data)


class ParcelIn(BaseModel):
    number: str = Field(min_length=6, max_length=60)
    label: str | None = Field(default=None, max_length=100)


def _parcel_out(p: dict) -> dict:
    return {"number": p["number"], "label": p.get("label"), "status": p.get("status"), "text": parcels.text_of(p),
            "event": p.get("event") or "", "carrier": p.get("carrier") or "", "done": bool(p.get("done"))}


@router.get("/parcels")
def list_parcels(ctx: PrivateCtx = Depends(private_ctx), db: OrmSession = Depends(get_db)):
    addons.require(db, ctx.ws_id, parcels.ADDON)
    return {"items": [_parcel_out(p) for p in parcels.parcels(db, ctx.ws_id)]}


@router.post("/parcels")
def add_parcel(body: ParcelIn, ctx: PrivateCtx = Depends(private_ctx), db: OrmSession = Depends(get_db)):
    addons.require(db, ctx.ws_id, parcels.ADDON)
    p = parcels.add(db, ctx.ws_id, number=body.number, label=body.label)
    db.commit()
    return _parcel_out(p)


@router.delete("/parcels/{number}", status_code=204)
def delete_parcel(number: str, ctx: PrivateCtx = Depends(private_ctx), db: OrmSession = Depends(get_db)):
    addons.require(db, ctx.ws_id, parcels.ADDON)
    if parcels.remove(db, ctx.ws_id, number) is None:
        from app.core.errors import NotFound

        raise NotFound("Pakken findes ikke")
    db.commit()
    return Response(status_code=204)
