from __future__ import annotations

import re
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session as OrmSession

from app.core.audit import record_audit
from app.core.auth import WorkspaceContext, get_workspace_context, require_capability
from app.core.errors import Conflict, NotFound, ValidationFailed
from app.db import get_db
from app.models import BusinessProfile, GoalSelection, LanguageSettings, WorkspaceCategory
from app.modules.setup.checks import invalidate_checks

router = APIRouter(prefix="/workspaces/{workspace_id}", tags=["business"])

# Suggested categories are a starting point only (O01). Custom categories are
# first-class; floor service is a demo, not a product constraint.
SUGGESTED_CATEGORIES = [
    ("haandvaerk-gulvservice", "Håndværk & Gulvservice"),
    ("overfladebehandling-traepleje", "Overfladebehandling & Træpleje"),
    ("restaurant-catering", "Restaurant og catering"),
    ("klinik-sundhed", "Klinik og sundhed"),
    ("bilvaerksted", "Bilværksted"),
    ("ejendomsservice", "Ejendomsservice"),
    ("it-support", "IT-support"),
]


def _check_version(expected: int, actual: int) -> None:
    if expected != actual:
        raise Conflict(f"Objektet er ændret af en anden (version {actual}). Genindlæs og prøv igen.",
                       code="version_conflict", extra={"current_version": actual})


# --- Business profile (O01, S01) --------------------------------------------


class ProfileOut(BaseModel):
    workspace_id: uuid.UUID
    version: int
    legal_name: str
    description: str
    website_url: str | None
    manual_setup: bool
    cvr: str | None
    address_line: str | None
    postal_code: str | None
    city: str | None
    country: str
    timezone: str
    phone: str | None
    updated_at: datetime


class ProfileIn(BaseModel):
    expected_version: int
    legal_name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=4000)
    website_url: str | None = Field(default=None, max_length=500)
    manual_setup: bool = True
    cvr: str | None = Field(default=None, max_length=32)
    address_line: str | None = Field(default=None, max_length=300)
    postal_code: str | None = Field(default=None, max_length=16)
    city: str | None = Field(default=None, max_length=120)
    country: str = Field(default="DK", min_length=2, max_length=2)
    timezone: str = Field(default="Europe/Copenhagen", max_length=64)
    phone: str | None = Field(default=None, max_length=40)


def _profile_out(p: BusinessProfile) -> ProfileOut:
    return ProfileOut(**{k: getattr(p, k) for k in ProfileOut.model_fields})


@router.get("/profile", response_model=ProfileOut)
def get_profile(ctx: WorkspaceContext = Depends(get_workspace_context), db: OrmSession = Depends(get_db)):
    p = db.get(BusinessProfile, ctx.workspace.id)
    if p is None:
        raise NotFound("Profilen findes ikke")
    return _profile_out(p)


@router.put("/profile", response_model=ProfileOut)
def update_profile(body: ProfileIn, request: Request, ctx: WorkspaceContext = Depends(require_capability("profile.edit")),
                   db: OrmSession = Depends(get_db)):
    p = db.scalar(select(BusinessProfile).where(BusinessProfile.workspace_id == ctx.workspace.id).with_for_update())
    if p is None:
        raise NotFound("Profilen findes ikke")
    _check_version(body.expected_version, p.version)
    if body.website_url and not re.match(r"^https?://", body.website_url):
        raise ValidationFailed("URL skal begynde med http:// eller https://", field_errors=[{"field": "website_url"}])
    try:
        from zoneinfo import ZoneInfo

        ZoneInfo(body.timezone)
    except Exception:
        raise ValidationFailed("Ukendt tidszone", field_errors=[{"field": "timezone"}])
    before = _profile_out(p).model_dump(mode="json")
    for k, v in body.model_dump(exclude={"expected_version"}).items():
        setattr(p, k, v)
    p.version += 1
    if ctx.workspace.name != p.legal_name and p.legal_name:
        ctx.workspace.name = p.legal_name
    record_audit(db, workspace_id=ctx.workspace.id, actor_user_id=ctx.user_id, action="profile.updated",
                 object_type="business_profile", object_id=ctx.workspace.id, before=before,
                 after=_profile_out(p).model_dump(mode="json"), request_id=request.state.request_id)
    invalidate_checks(db, ctx.workspace.id, changed_area="profile", reason="Virksomhedsprofilen blev ændret")
    db.commit()
    return _profile_out(p)


# --- Categories --------------------------------------------------------------


class CategoryIn(BaseModel):
    label: str = Field(min_length=1, max_length=120)
    slug: str | None = Field(default=None, max_length=80)
    is_primary: bool = False


class CategoryOut(BaseModel):
    id: uuid.UUID
    slug: str
    label: str
    is_custom: bool
    is_primary: bool
    position: int


def _slug(label: str) -> str:
    s = label.lower().replace("æ", "ae").replace("ø", "oe").replace("å", "aa")
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")[:80] or "kategori"


@router.get("/categories/suggested")
def suggested_categories(ctx: WorkspaceContext = Depends(get_workspace_context)):
    return {"items": [{"slug": s, "label": lab} for s, lab in SUGGESTED_CATEGORIES]}


@router.get("/categories", response_model=list[CategoryOut])
def list_categories(ctx: WorkspaceContext = Depends(get_workspace_context), db: OrmSession = Depends(get_db)):
    rows = db.scalars(select(WorkspaceCategory).where(WorkspaceCategory.workspace_id == ctx.workspace.id)
                      .order_by(WorkspaceCategory.position, WorkspaceCategory.created_at))
    return [CategoryOut.model_validate(c, from_attributes=True) for c in rows]


@router.post("/categories", response_model=CategoryOut, status_code=201)
def add_category(body: CategoryIn, request: Request, ctx: WorkspaceContext = Depends(require_capability("profile.edit")),
                 db: OrmSession = Depends(get_db)):
    slug = body.slug or _slug(body.label)
    suggested = dict(SUGGESTED_CATEGORIES)
    is_custom = slug not in suggested
    if db.scalar(select(WorkspaceCategory).where(WorkspaceCategory.workspace_id == ctx.workspace.id,
                                                 WorkspaceCategory.slug == slug)):
        raise Conflict("Kategorien er allerede tilføjet", code="category_exists")
    existing = list(db.scalars(select(WorkspaceCategory).where(WorkspaceCategory.workspace_id == ctx.workspace.id)))
    if body.is_primary:
        for c in existing:
            c.is_primary = False
    cat = WorkspaceCategory(workspace_id=ctx.workspace.id, slug=slug, label=body.label if is_custom else suggested[slug],
                            is_custom=is_custom, is_primary=body.is_primary or not existing, position=len(existing))
    db.add(cat)
    db.flush()
    record_audit(db, workspace_id=ctx.workspace.id, actor_user_id=ctx.user_id, action="category.added",
                 object_type="workspace_category", object_id=cat.id, after={"slug": slug, "custom": is_custom},
                 request_id=request.state.request_id)
    invalidate_checks(db, ctx.workspace.id, changed_area="profile", reason="Kategorier blev ændret")
    db.commit()
    return CategoryOut.model_validate(cat, from_attributes=True)


@router.delete("/categories/{category_id}", status_code=204)
def remove_category(category_id: uuid.UUID, request: Request,
                    ctx: WorkspaceContext = Depends(require_capability("profile.edit")),
                    db: OrmSession = Depends(get_db)):
    from fastapi import Response

    from app.core.auth import get_scoped

    cat = get_scoped(db, WorkspaceCategory, category_id, ctx.workspace.id)
    record_audit(db, workspace_id=ctx.workspace.id, actor_user_id=ctx.user_id, action="category.removed",
                 object_type="workspace_category", object_id=cat.id, before={"slug": cat.slug},
                 request_id=request.state.request_id)
    db.delete(cat)
    invalidate_checks(db, ctx.workspace.id, changed_area="profile", reason="Kategorier blev ændret")
    db.commit()
    return Response(status_code=204)


# --- Goals (O03, G02) ---------------------------------------------------------


class GoalsOut(BaseModel):
    version: int
    product_intent: str
    guidance_mode: str
    inbound_phone: bool
    webchat: bool
    callback: bool
    booking: bool
    conversation_goals: list
    updated_at: datetime


class GoalsIn(BaseModel):
    expected_version: int
    product_intent: str
    guidance_mode: str = "guided"
    inbound_phone: bool = True
    webchat: bool = False
    callback: bool = False
    booking: bool = False
    conversation_goals: list[str] = Field(default_factory=list, max_length=50)


@router.get("/goals", response_model=GoalsOut)
def get_goals(ctx: WorkspaceContext = Depends(get_workspace_context), db: OrmSession = Depends(get_db)):
    g = db.get(GoalSelection, ctx.workspace.id)
    return GoalsOut.model_validate(g, from_attributes=True)


@router.put("/goals", response_model=GoalsOut)
def update_goals(body: GoalsIn, request: Request, ctx: WorkspaceContext = Depends(require_capability("goals.edit")),
                 db: OrmSession = Depends(get_db)):
    if body.product_intent not in ("reception", "campaigns", "both"):
        raise ValidationFailed("product_intent skal være reception, campaigns eller both",
                               field_errors=[{"field": "product_intent"}])
    if body.guidance_mode not in ("guided", "self_managed"):
        raise ValidationFailed("guidance_mode skal være guided eller self_managed",
                               field_errors=[{"field": "guidance_mode"}])
    if body.product_intent == "campaigns" and (body.inbound_phone or body.callback or body.webchat):
        raise ValidationFailed("Receptionskapabiliteter kræver produktintention reception eller both",
                               field_errors=[{"field": "product_intent"}])
    g = db.scalar(select(GoalSelection).where(GoalSelection.workspace_id == ctx.workspace.id).with_for_update())
    _check_version(body.expected_version, g.version)
    before = GoalsOut.model_validate(g, from_attributes=True).model_dump(mode="json")
    for k, v in body.model_dump(exclude={"expected_version"}).items():
        setattr(g, k, v)
    g.version += 1
    ctx.workspace.product_intent = body.product_intent
    record_audit(db, workspace_id=ctx.workspace.id, actor_user_id=ctx.user_id, action="goals.updated",
                 object_type="goal_selection", object_id=ctx.workspace.id, before=before,
                 after=GoalsOut.model_validate(g, from_attributes=True).model_dump(mode="json"),
                 request_id=request.state.request_id)
    invalidate_checks(db, ctx.workspace.id, changed_area="goals", reason="Mål/kapabiliteter blev ændret")
    db.commit()
    return GoalsOut.model_validate(g, from_attributes=True)


# --- Languages (O04) ----------------------------------------------------------


class LanguagesOut(BaseModel):
    version: int
    interface_language: str
    default_conversation_language: str
    enabled_conversation_languages: list[str]
    report_language: str
    updated_at: datetime


class LanguagesIn(BaseModel):
    expected_version: int
    interface_language: str = Field(min_length=2, max_length=16)
    default_conversation_language: str = Field(min_length=2, max_length=16)
    enabled_conversation_languages: list[str] = Field(min_length=1, max_length=20)
    report_language: str = Field(min_length=2, max_length=16)


@router.get("/languages", response_model=LanguagesOut)
def get_languages(ctx: WorkspaceContext = Depends(get_workspace_context), db: OrmSession = Depends(get_db)):
    return LanguagesOut.model_validate(db.get(LanguageSettings, ctx.workspace.id), from_attributes=True)


@router.put("/languages", response_model=LanguagesOut)
def update_languages(body: LanguagesIn, request: Request,
                     ctx: WorkspaceContext = Depends(require_capability("languages.edit")),
                     db: OrmSession = Depends(get_db)):
    if body.default_conversation_language not in body.enabled_conversation_languages:
        raise ValidationFailed("Standardsamtalesproget skal være blandt de aktiverede samtalesprog",
                               field_errors=[{"field": "default_conversation_language"}])
    ls = db.scalar(select(LanguageSettings).where(LanguageSettings.workspace_id == ctx.workspace.id).with_for_update())
    _check_version(body.expected_version, ls.version)
    before = LanguagesOut.model_validate(ls, from_attributes=True).model_dump(mode="json")
    for k, v in body.model_dump(exclude={"expected_version"}).items():
        setattr(ls, k, v)
    ls.version += 1
    record_audit(db, workspace_id=ctx.workspace.id, actor_user_id=ctx.user_id, action="languages.updated",
                 object_type="language_settings", object_id=ctx.workspace.id, before=before,
                 after=LanguagesOut.model_validate(ls, from_attributes=True).model_dump(mode="json"),
                 request_id=request.state.request_id)
    invalidate_checks(db, ctx.workspace.id, changed_area="languages", reason="Sprogindstillinger blev ændret")
    db.commit()
    return LanguagesOut.model_validate(ls, from_attributes=True)


@router.get("/cvr/{cvr}")
def cvr_lookup(cvr: str, ctx: WorkspaceContext = Depends(require_capability("profile.edit"))):
    """Name and address from the CVR register, for the owner to accept into the profile. Nothing is saved."""
    from app.modules.business import cvr as cvr_register

    return cvr_register.lookup(cvr)
