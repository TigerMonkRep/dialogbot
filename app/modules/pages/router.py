"""Site documents: small pages on dialogbot.dk that Dialogbot's staff edit in place.

GET /public/pages/{slug} is open (the blob is opaque – the Gastro Hall manuscript is encrypted in the browser with a
password, so the server only ever stores ciphertext). PUT /operator/pages/{slug} replaces it and is for platform
operators only (scripts/grant_operator.py). Slugs are a fixed allow-list, so nobody can create pages by guessing."""
from __future__ import annotations

import json
from datetime import datetime

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session as OrmSession

from app.core.audit import record_audit
from app.core.auth import Principal
from app.core.errors import NotFound, ValidationFailed
from app.db import get_db
from app.models import SiteDocument
from app.modules.voices.operator_router import operator

public_router = APIRouter(prefix="/public/pages", tags=["pages"])
operator_router = APIRouter(prefix="/operator/pages", tags=["pages-operator"])

SLUGS = frozenset({"gastrohall"})
MAX_BLOB_BYTES = 512_000


class BlobIn(BaseModel):
    blob: dict = Field(..., description="Opaque document; for encrypted pages {v, salt, iv, ct, updatedAt}")


class DocOut(BaseModel):
    slug: str
    blob: dict
    updated_at: datetime


def _slug(slug: str) -> str:
    if slug not in SLUGS:
        raise NotFound("Siden findes ikke", code="page_not_found")
    return slug


@public_router.get("/{slug}", response_model=DocOut)
def read_page(slug: str, db: OrmSession = Depends(get_db)):
    doc = db.get(SiteDocument, _slug(slug))
    if doc is None:
        raise NotFound("Siden er ikke gemt endnu", code="page_empty")
    return DocOut(slug=doc.slug, blob=doc.blob, updated_at=doc.updated_at)


@operator_router.put("/{slug}", response_model=DocOut)
def write_page(slug: str, body: BlobIn, request: Request, principal: Principal = Depends(operator),
               db: OrmSession = Depends(get_db)):
    slug = _slug(slug)
    if len(json.dumps(body.blob)) > MAX_BLOB_BYTES:
        raise ValidationFailed("Dokumentet er for stort", code="page_too_large")
    doc = db.get(SiteDocument, slug)
    if doc is None:
        doc = SiteDocument(slug=slug, blob=body.blob, updated_by=principal.user.id)
        db.add(doc)
    else:
        doc.blob = body.blob
        doc.updated_by = principal.user.id
    record_audit(db, workspace_id=None, actor_user_id=principal.user.id, action="site_page.update",
                 object_type="site_document", object_id=None, after={"slug": slug, "updatedAt": body.blob.get("updatedAt")},
                 request_id=request.state.request_id)
    db.commit()
    db.refresh(doc)
    return DocOut(slug=doc.slug, blob=doc.blob, updated_at=doc.updated_at)
