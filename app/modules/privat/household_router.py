"""Konto → «Husstand» (Familie, household.py) and «Dine data» (export and account deletion, gdpr.py).
Every route resolves the caller's OWN personal workspace (deps.private_ctx)."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session as OrmSession

from app.db import get_db
from app.modules.privat import gdpr, household
from app.modules.privat.deps import PrivateCtx, private_ctx

router = APIRouter(prefix="/privat", tags=["privat"])


# --------------------------------------------------------------------------- household (Familie)

@router.get("/household")
def household_get(ctx: PrivateCtx = Depends(private_ctx), db: OrmSession = Depends(get_db)):
    """role owner|member|null, active (rights flow now), can_invite, limit (5), count, first names only."""
    return household.state(db, ctx)


@router.post("/household/invites")
def household_invite(ctx: PrivateCtx = Depends(private_ctx), db: OrmSession = Depends(get_db)):
    """A link for the owner to text from their own phone (suggested_text). 409 needs_plan | household_full |
    household_member."""
    out = household.invite(db, ctx)
    db.commit()
    return out


@router.delete("/household/members/{member_id}", status_code=204)
def household_remove(member_id: uuid.UUID, ctx: PrivateCtx = Depends(private_ctx), db: OrmSession = Depends(get_db)):
    """The owner takes a person out: their Familie rights stop at once; their own data stays theirs."""
    household.remove(db, ctx, member_id)
    db.commit()
    return Response(status_code=204)


@router.post("/household/leave", status_code=204)
def household_leave(ctx: PrivateCtx = Depends(private_ctx), db: OrmSession = Depends(get_db)):
    household.leave(db, ctx)
    db.commit()
    return Response(status_code=204)


# --------------------------------------------------------------------------- «Dine data»

class DeleteIn(BaseModel):
    confirm_email: str = Field(min_length=3, max_length=320, description="Brugerens e-mail, skrevet igen")


@router.get("/data-export")
def data_export_status(ctx: PrivateCtx = Depends(private_ctx), db: OrmSession = Depends(get_db)):
    out = gdpr.export_out(gdpr.latest_export(db, ctx.user_id))
    db.commit()
    return out


@router.post("/data-export", status_code=202)
def data_export_request(ctx: PrivateCtx = Depends(private_ctx), db: OrmSession = Depends(get_db)):
    """Queue «Eksportér mine data»: the worker e-mails a link (7 days, login needed). 429 after 3 a day."""
    out = gdpr.request_export(db, ctx)
    db.commit()
    return out


@router.get("/data-export/download")
def data_export_download(token: str = Query(min_length=10, max_length=200), ctx: PrivateCtx = Depends(private_ctx),
                         db: OrmSession = Depends(get_db)):
    gdpr.purge_expired(db, user_id=ctx.user_id)
    db.commit()  # an expired link loses its content even though the answer is 404
    body, name = gdpr.download(db, ctx, token)
    db.commit()
    return Response(content=body, media_type="application/zip",
                    headers={"content-disposition": f'attachment; filename="{name}"', "cache-control": "no-store"})


@router.post("/account/delete")
def account_delete(body: DeleteIn, ctx: PrivateCtx = Depends(private_ctx), db: OrmSession = Depends(get_db)):
    """«Slet min konto»: cancels a live subscription, deletes all Privat data and the login (unless it is also used
    outside Privat: login_kept). Irreversible."""
    out = gdpr.delete_account(db, ctx, body.confirm_email)
    db.commit()
    return out
