"""Ambassador programme API: public page data, the ambassador's own portal, the customer's code, and operators.

See service.py for the rules. The ambassador portal is tied to the logged-in user (one ambassador per user);
it never exposes customers' conversations, leads or contact data – only company name, status and earnings.
"""
from __future__ import annotations

import csv
import io
import uuid
from datetime import date, timedelta

from fastapi import APIRouter, Depends, Query, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session as OrmSession

from app.core.audit import record_audit
from app.core.auth import Principal, WorkspaceContext, get_current_principal, require_capability
from app.core.errors import Conflict, NotFound, ValidationFailed
from app.db import get_db
from app.models import Ambassador, AmbassadorPayout, CommissionEntry, Invoice, Referral, User, Workspace
from app.modules.ambassadors import service
from app.modules.voices.operator_router import operator

public_router = APIRouter(prefix="/public/ambassadors", tags=["ambassadors"])
router = APIRouter(prefix="/ambassador", tags=["ambassadors"])
workspace_router = APIRouter(prefix="/workspaces/{workspace_id}/referral", tags=["ambassadors"])
operator_router = APIRouter(prefix="/operator/ambassadors", tags=["ambassadors-operator"])

CODE_WINDOW_DAYS = 30


# --------------------------------------------------------------------------- public

@public_router.get("/program")
def program():
    """Terms and rules shown on the sign-up page (the quiz without the answers)."""
    return {"rules_version": service.RULES_VERSION, "rules_text": service.RULES_TEXT,
            "quiz": [{k: q[k] for k in ("id", "question", "options")} for q in service.RULES_QUIZ],
            "terms": {"bonus_minor": service.DEFAULT_BONUS_MINOR, "rate_bp": service.DEFAULT_RATE_BP,
                      "months": service.DEFAULT_MONTHS, "hold_days": service.HOLD_DAYS,
                      "min_payout_minor": service.MIN_PAYOUT_MINOR, "min_age": service.MIN_AGE,
                      "customer_discount_bp": service.CUSTOMER_DISCOUNT_BP}}


@public_router.get("/{ref}")
def public_page(ref: str, db: OrmSession = Depends(get_db)):
    """What an ambassador's personal page shows. Only active ambassadors; first name only."""
    a = service.find_by_ref(db, ref)
    if a is None:
        raise NotFound("Siden findes ikke")
    return {"slug": a.slug, "code": a.code, "first_name": a.full_name.split()[0], "headline": a.headline,
            "customer_discount_bp": service.CUSTOMER_DISCOUNT_BP}


@public_router.post("/{ref}/visit", status_code=status.HTTP_204_NO_CONTENT)
def public_visit(ref: str, db: OrmSession = Depends(get_db)):
    """Count one visit (per day, aggregated). Unknown refs are ignored silently."""
    a = service.find_by_ref(db, ref)
    if a is not None:
        service.record_click(db, a)
        db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


class ParentIn(BaseModel):
    token: str = Field(min_length=10, max_length=200)
    parent_name: str = Field(default="", max_length=200)
    confirm: bool


@public_router.get("/parent-consent/{token}")
def parent_preview(token: str, db: OrmSession = Depends(get_db)):
    a = service.parent_preview(db, token)
    return {"ambassador_name": a.full_name, "parent_name": a.parent_name, "rules_text": service.RULES_TEXT,
            "terms": {"bonus_minor": a.bonus_minor, "rate_bp": a.rate_bp, "months": a.months},
            "confirmed": a.parent_consent_at is not None}


@public_router.post("/parent-consent")
def parent_confirm(body: ParentIn, request: Request, db: OrmSession = Depends(get_db)):
    if not body.confirm:
        raise ValidationFailed("Sæt kryds for at godkende", field_errors=[{"field": "confirm"}])
    a = service.parent_confirm(db, body.token, body.parent_name, request.state.request_id)
    db.commit()
    return {"confirmed": True, "ambassador_name": a.full_name}


# --------------------------------------------------------------------------- ambassador portal

class ApplyIn(BaseModel):
    kind: str = Field(pattern="^(private|company)$")
    full_name: str = Field(min_length=2, max_length=200)
    phone: str = Field(default="", max_length=20)
    birth_date: date | None = None
    cpr: str | None = Field(default=None, max_length=12)
    parent_name: str | None = Field(default=None, max_length=200)
    parent_email: str | None = Field(default=None, max_length=320)
    company_name: str | None = Field(default=None, max_length=200)
    cvr: str | None = Field(default=None, max_length=12)
    vat_registered: bool = False
    bank_reg: str | None = Field(default=None, max_length=6)
    bank_account: str | None = Field(default=None, max_length=14)
    headline: str = Field(default="", max_length=300)
    motivation: str = Field(default="", max_length=1000)
    rules_version: str
    quiz: dict[str, str]


class DetailsIn(BaseModel):
    cpr: str | None = Field(default=None, max_length=12)
    bank_reg: str | None = Field(default=None, max_length=6)
    bank_account: str | None = Field(default=None, max_length=14)
    headline: str | None = Field(default=None, max_length=300)
    phone: str | None = Field(default=None, max_length=20)
    vat_registered: bool | None = None
    expected_version: int | None = None


def _mine(db: OrmSession, principal: Principal) -> Ambassador:
    a = db.scalar(select(Ambassador).where(Ambassador.user_id == principal.user.id))
    if a is None:
        raise NotFound("Du er ikke tilmeldt som ambassadør", code="not_ambassador")
    return a


@router.get("/me")
def me(principal: Principal = Depends(get_current_principal), db: OrmSession = Depends(get_db)):
    a = db.scalar(select(Ambassador).where(Ambassador.user_id == principal.user.id))
    if a is None:
        return {"enrolled": False}
    return {"enrolled": True} | service.profile_out(db, a, principal.user)


@router.post("/apply", status_code=status.HTTP_201_CREATED)
def apply(body: ApplyIn, request: Request, principal: Principal = Depends(get_current_principal),
          db: OrmSession = Depends(get_db)):
    a = service.apply(db, principal.user, body.model_dump(), request.state.request_id)
    db.commit()
    return {"enrolled": True} | service.profile_out(db, a, principal.user)


@router.put("/me")
def update_me(body: DetailsIn, request: Request, principal: Principal = Depends(get_current_principal),
              db: OrmSession = Depends(get_db)):
    a = _mine(db, principal)
    service.update_details(db, a, body.model_dump(), request.state.request_id)
    db.commit()
    return {"enrolled": True} | service.profile_out(db, a, principal.user)


@router.post("/me/parent-consent/resend", status_code=status.HTTP_202_ACCEPTED)
def resend_parent(principal: Principal = Depends(get_current_principal), db: OrmSession = Depends(get_db)):
    a = _mine(db, principal)
    if not a.parent_email or a.parent_consent_at is not None:
        raise Conflict("Der er ingen godkendelse, der venter", code="nothing_to_resend")
    service.send_parent_request(db, a, principal.user)
    db.commit()
    return {"status": "queued"}


@router.get("/me/customers")
def my_customers(principal: Principal = Depends(get_current_principal), db: OrmSession = Depends(get_db)):
    return {"items": service.customers(db, _mine(db, principal).id)}


@router.get("/me/ledger")
def my_ledger(limit: int = Query(default=200, ge=1, le=1000), principal: Principal = Depends(get_current_principal),
              db: OrmSession = Depends(get_db)):
    a = _mine(db, principal)
    names: dict = {}
    rows = db.scalars(select(CommissionEntry).where(CommissionEntry.ambassador_id == a.id)
                      .order_by(CommissionEntry.created_at.desc()).limit(limit))
    return {"items": [service.entry_out(db, e, names) for e in rows]}


@router.get("/me/payouts")
def my_payouts(principal: Principal = Depends(get_current_principal), db: OrmSession = Depends(get_db)):
    a = _mine(db, principal)
    rows = db.scalars(select(AmbassadorPayout).where(AmbassadorPayout.ambassador_id == a.id,
                                                     AmbassadorPayout.status != "cancelled")
                      .order_by(AmbassadorPayout.created_at.desc()))
    return {"items": [service.payout_out(p) for p in rows]}


def _statement(db: OrmSession, a: Ambassador, p: AmbassadorPayout) -> dict:
    names: dict = {}
    entries = db.scalars(select(CommissionEntry).where(CommissionEntry.payout_id == p.id)
                         .order_by(CommissionEntry.month, CommissionEntry.created_at)).all()
    return service.payout_out(p) | {
        "ambassador": {"full_name": a.full_name, "kind": a.kind, "company_name": a.company_name, "cvr": a.cvr,
                       "vat_registered": a.vat_registered, "bank_last4": a.bank_last4},
        "lines": [service.entry_out(db, e, names) for e in entries],
        "tax_note": ("B-indkomst. Dialogbot indberetter beløbet til Skattestyrelsen (eIndkomst). Der er ikke "
                     "trukket skat – husk at tjekke din forskudsopgørelse." if p.income_type == "b_income" else
                     "Afregning til virksomhed (selvfaktura)." + (" Moms 25 % lægges oveni." if a.vat_registered else
                                                                  " Ikke momsregistreret: ingen moms.")),
    }


@router.get("/me/payouts/{payout_id}")
def my_payout(payout_id: uuid.UUID, principal: Principal = Depends(get_current_principal),
              db: OrmSession = Depends(get_db)):
    a = _mine(db, principal)
    p = db.scalar(select(AmbassadorPayout).where(AmbassadorPayout.id == payout_id,
                                                 AmbassadorPayout.ambassador_id == a.id))
    if p is None:
        raise NotFound("Udbetalingen findes ikke")
    return _statement(db, a, p)


# --------------------------------------------------------------------------- the customer's side

class CodeIn(BaseModel):
    code: str = Field(min_length=3, max_length=60)


@workspace_router.get("")
def get_referral(ctx: WorkspaceContext = Depends(require_capability("billing.read")), db: OrmSession = Depends(get_db)):
    r = db.get(Referral, ctx.workspace.id)
    if r is None:
        can_add = (service.now() - ctx.workspace.created_at) < timedelta(days=CODE_WINDOW_DAYS) and not db.scalar(
            select(Invoice.id).where(Invoice.workspace_id == ctx.workspace.id).limit(1))
        return {"referred": False, "can_add_code": bool(can_add and ctx.can("billing.manage"))}
    a = db.get(Ambassador, r.ambassador_id)
    return {"referred": True, "ambassador_first_name": a.full_name.split()[0] if a else None, "via": r.via,
            "customer_discount_bp": service.CUSTOMER_DISCOUNT_BP, "can_add_code": False}


@workspace_router.put("")
def add_code(body: CodeIn, request: Request, ctx: WorkspaceContext = Depends(require_capability("billing.manage")),
             db: OrmSession = Depends(get_db)):
    """The customer types an ambassador's code after signing up (within 30 days, before the first invoice)."""
    if db.get(Referral, ctx.workspace.id) is not None:
        raise Conflict("Der er allerede registreret en ambassadør", code="already_referred")
    if (service.now() - ctx.workspace.created_at) >= timedelta(days=CODE_WINDOW_DAYS) or db.scalar(
            select(Invoice.id).where(Invoice.workspace_id == ctx.workspace.id).limit(1)):
        raise Conflict("Koden kan kun tilføjes de første 30 dage og før første faktura", code="code_window_closed")
    a = service.find_by_ref(db, body.code)
    if a is None:
        raise ValidationFailed("Koden findes ikke", code="unknown_code", field_errors=[{"field": "code"}])
    if a.user_id == ctx.user_id:
        raise ValidationFailed("Du kan ikke bruge din egen kode", code="self_referral", field_errors=[{"field": "code"}])
    service.attribute(db, ctx.workspace, ctx.principal.user, code=body.code, link=None,
                      request_id=request.state.request_id)
    db.commit()
    return get_referral(ctx, db)


# --------------------------------------------------------------------------- operators

class DecideIn(BaseModel):
    note: str = Field(default="", max_length=500)


class TermsIn(BaseModel):
    bonus_minor: int = Field(ge=0, le=10_000_000)
    rate_bp: int = Field(ge=0, le=5000)
    months: int = Field(ge=1, le=120)
    expected_version: int


class MoveIn(BaseModel):
    ambassador_id: uuid.UUID | None = None  # None removes the attribution
    reason: str = Field(min_length=3, max_length=300)


class PayoutsIn(BaseModel):
    ambassador_ids: list[uuid.UUID] | None = None


class PaidIn(BaseModel):
    reference: str = Field(min_length=1, max_length=100)


def _get(db: OrmSession, ambassador_id: uuid.UUID) -> Ambassador:
    a = db.get(Ambassador, ambassador_id)
    if a is None:
        raise NotFound("Ambassadøren findes ikke")
    return a


def _audit(db, request, principal, action, a_id, after=None, ws_id=None):
    record_audit(db, workspace_id=ws_id, actor_user_id=principal.user.id, action=action, object_type="ambassador",
                 object_id=a_id, after=after, request_id=request.state.request_id)


@operator_router.get("")
def op_list(status_filter: str | None = Query(default=None, alias="status"), db: OrmSession = Depends(get_db),
            _: Principal = Depends(operator)):
    q = select(Ambassador, User.email).join(User, User.id == Ambassador.user_id).order_by(Ambassador.created_at.desc())
    if status_filter:
        q = q.where(Ambassador.status == status_filter)
    items = []
    for a, email in db.execute(q).all():
        b = service.balances(db, a.id)
        items.append({"id": str(a.id), "full_name": a.full_name, "email": email, "status": a.status, "kind": a.kind,
                      "minor": service.is_minor(a), "parent_confirmed": a.parent_consent_at is not None,
                      "slug": a.slug, "code": a.code, "created_at": a.created_at.isoformat(),
                      "customers": db.scalar(select(func.count()).select_from(Referral)
                                             .where(Referral.ambassador_id == a.id)) or 0,
                      "clicks_30d": service.clicks(db, a.id), "payout_blockers": service.payout_blockers(a)} | b)
    totals = {"pending": sum(1 for i in items if i["status"] == "pending"),
              "payable_minor": sum(i["payable_minor"] for i in items),
              "held_minor": sum(i["held_minor"] for i in items),
              "in_payout_minor": sum(i["in_payout_minor"] for i in items)}
    return {"items": items, "totals": totals}


@operator_router.get("/payouts")
def op_payouts(status_filter: str | None = Query(default=None, alias="status"), db: OrmSession = Depends(get_db),
               _: Principal = Depends(operator)):
    q = select(AmbassadorPayout, Ambassador).join(Ambassador, Ambassador.id == AmbassadorPayout.ambassador_id)\
        .order_by(AmbassadorPayout.created_at.desc()).limit(500)
    if status_filter:
        q = q.where(AmbassadorPayout.status == status_filter)
    return {"items": [service.payout_out(p) | {"ambassador_id": str(a.id), "ambassador_name": a.full_name,
                                                "bank_last4": a.bank_last4} for p, a in db.execute(q).all()]}


@operator_router.post("/payouts", status_code=status.HTTP_201_CREATED)
def op_create_payouts(body: PayoutsIn, request: Request, db: OrmSession = Depends(get_db),
                      principal: Principal = Depends(operator)):
    created, skipped = service.create_payouts(db, principal.user.id, body.ambassador_ids, request.state.request_id)
    db.commit()
    return {"created": [service.payout_out(p) for p in created], "skipped": skipped}


def _payout(db: OrmSession, payout_id: uuid.UUID) -> AmbassadorPayout:
    p = db.scalar(select(AmbassadorPayout).where(AmbassadorPayout.id == payout_id).with_for_update())
    if p is None:
        raise NotFound("Udbetalingen findes ikke")
    return p


@operator_router.get("/payouts/{payout_id}")
def op_payout(payout_id: uuid.UUID, db: OrmSession = Depends(get_db), _: Principal = Depends(operator)):
    p = _payout(db, payout_id)
    return _statement(db, _get(db, p.ambassador_id), p)


@operator_router.post("/payouts/{payout_id}/paid")
def op_mark_paid(payout_id: uuid.UUID, body: PaidIn, request: Request, db: OrmSession = Depends(get_db),
                 principal: Principal = Depends(operator)):
    p = service.mark_paid(db, _payout(db, payout_id), principal.user.id, body.reference, request.state.request_id)
    db.commit()
    return service.payout_out(p)


@operator_router.post("/payouts/{payout_id}/cancel")
def op_cancel_payout(payout_id: uuid.UUID, request: Request, db: OrmSession = Depends(get_db),
                     principal: Principal = Depends(operator)):
    p = _payout(db, payout_id)
    service.cancel_payout(db, p, principal.user.id, request.state.request_id)
    db.commit()
    return service.payout_out(p)


@operator_router.get("/b-income.csv")
def op_b_income(request: Request, year: int = Query(ge=2025, le=2100), db: OrmSession = Depends(get_db),
                principal: Principal = Depends(operator)):
    """Paid B-income per private ambassador for the year – the basis for reporting to eIndkomst. Contains CPR."""
    rows = service.b_income_rows(db, year)
    record_audit(db, workspace_id=None, actor_user_id=principal.user.id, action="ambassador.b_income_exported",
                 object_type="ambassador_report", object_id=str(year), after={"rows": len(rows)},
                 request_id=request.state.request_id)
    db.commit()
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";")
    w.writerow(["navn", "cpr", "beloeb_kr", "antal_udbetalinger", "indkomsttype", "aar"])
    for r in rows:
        w.writerow([r["name"], r["cpr"], f"{r['amount_minor'] / 100:.2f}".replace(".", ","), r["payouts"], "B-indkomst", year])
    return Response(buf.getvalue(), media_type="text/csv; charset=utf-8",
                    headers={"content-disposition": f'attachment; filename="b-indkomst-{year}.csv"',
                             "cache-control": "no-store"})


@operator_router.get("/{ambassador_id}")
def op_get(ambassador_id: uuid.UUID, db: OrmSession = Depends(get_db), _: Principal = Depends(operator)):
    a = _get(db, ambassador_id)
    u = db.get(User, a.user_id)
    names: dict = {}
    ledger = db.scalars(select(CommissionEntry).where(CommissionEntry.ambassador_id == a.id)
                        .order_by(CommissionEntry.created_at.desc()).limit(500))
    payouts = db.scalars(select(AmbassadorPayout).where(AmbassadorPayout.ambassador_id == a.id)
                         .order_by(AmbassadorPayout.created_at.desc()))
    return service.profile_out(db, a, u) | {
        "motivation": a.motivation, "rules_version": a.rules_version, "rules_accepted_at": a.rules_accepted_at.isoformat(),
        "customers": service.customers(db, a.id), "ledger": [service.entry_out(db, e, names) for e in ledger],
        "payouts": [service.payout_out(p) for p in payouts]}


@operator_router.post("/{ambassador_id}/reveal")
def op_reveal(ambassador_id: uuid.UUID, request: Request, db: OrmSession = Depends(get_db),
              principal: Principal = Depends(operator)):
    """CPR and bank details in clear text, for making a transfer or reporting. Every reveal is audited."""
    a = _get(db, ambassador_id)
    _audit(db, request, principal, "ambassador.details_revealed", a.id)
    db.commit()
    return service.reveal(a)


def _decide(db, request, principal, a: Ambassador, new: str, note: str, allowed_from: tuple[str, ...]):
    if a.status not in allowed_from:
        raise Conflict(f"Kan ikke skifte fra '{a.status}' til '{new}'", code="invalid_transition")
    before = a.status
    a.status, a.decided_by, a.decided_at, a.decision_note = new, principal.user.id, service.now(), note.strip()
    a.version += 1
    _audit(db, request, principal, f"ambassador.{new}", a.id, {"from": before, "note": a.decision_note})
    if new in ("active", "rejected") and before == "pending":
        from app.config import get_settings
        from app.core.outbox import enqueue

        u = db.get(User, a.user_id)
        first = a.full_name.split()[0]
        body = (f"Hej {first}\n\nDu er godkendt som ambassadør for Dialogbot. Dit personlige link er "
                f"{service.link_for(a)} og din kode er {a.code}.\n\nSe dine kunder og din bonus på "
                f"{get_settings().frontend_base_url}/ambassador.\n\nVenlig hilsen\nDialogbot") if new == "active" else (
                f"Hej {first}\n\nTak for din interesse. Vi kan desværre ikke godkende dig som ambassadør lige nu."
                + (f"\n\n{a.decision_note}" if a.decision_note else "") + "\n\nVenlig hilsen\nDialogbot")
        enqueue(db, event_type="email.ambassador", dedupe_key=f"ambassador-decided:{a.id}:{new}",
                payload={"to_email": u.email, "subject": "Du er godkendt som Dialogbot-ambassadør" if new == "active"
                         else "Din ansøgning som Dialogbot-ambassadør", "body": body})
    db.commit()
    return service.profile_out(db, a, db.get(User, a.user_id))


@operator_router.post("/{ambassador_id}/approve")
def op_approve(ambassador_id: uuid.UUID, body: DecideIn, request: Request, db: OrmSession = Depends(get_db),
               principal: Principal = Depends(operator)):
    return _decide(db, request, principal, _get(db, ambassador_id), "active", body.note, ("pending",))


@operator_router.post("/{ambassador_id}/reject")
def op_reject(ambassador_id: uuid.UUID, body: DecideIn, request: Request, db: OrmSession = Depends(get_db),
              principal: Principal = Depends(operator)):
    return _decide(db, request, principal, _get(db, ambassador_id), "rejected", body.note, ("pending",))


@operator_router.post("/{ambassador_id}/suspend")
def op_suspend(ambassador_id: uuid.UUID, body: DecideIn, request: Request, db: OrmSession = Depends(get_db),
               principal: Principal = Depends(operator)):
    return _decide(db, request, principal, _get(db, ambassador_id), "suspended", body.note, ("active",))


@operator_router.post("/{ambassador_id}/reactivate")
def op_reactivate(ambassador_id: uuid.UUID, body: DecideIn, request: Request, db: OrmSession = Depends(get_db),
                  principal: Principal = Depends(operator)):
    return _decide(db, request, principal, _get(db, ambassador_id), "active", body.note, ("suspended",))


@operator_router.put("/{ambassador_id}/terms")
def op_terms(ambassador_id: uuid.UUID, body: TermsIn, request: Request, db: OrmSession = Depends(get_db),
             principal: Principal = Depends(operator)):
    """Change bonus, share and period. Applies to invoices paid from now on; earned entries are not touched."""
    a = _get(db, ambassador_id)
    if body.expected_version != a.version:
        raise Conflict("Ambassadøren er ændret et andet sted – genindlæs", code="version_conflict")
    before = {"bonus_minor": a.bonus_minor, "rate_bp": a.rate_bp, "months": a.months}
    a.bonus_minor, a.rate_bp, a.months = body.bonus_minor, body.rate_bp, body.months
    a.version += 1
    a.updated_at = service.now()
    record_audit(db, workspace_id=None, actor_user_id=principal.user.id, action="ambassador.terms_changed",
                 object_type="ambassador", object_id=a.id, before=before,
                 after={"bonus_minor": a.bonus_minor, "rate_bp": a.rate_bp, "months": a.months},
                 request_id=request.state.request_id)
    db.commit()
    return service.profile_out(db, a, db.get(User, a.user_id))


@operator_router.put("/referrals/{workspace_id}")
def op_move_referral(workspace_id: uuid.UUID, body: MoveIn, request: Request, db: OrmSession = Depends(get_db),
                     principal: Principal = Depends(operator)):
    """Move a customer to another ambassador, or remove the attribution. Earned entries stay where they are."""
    ws = db.get(Workspace, workspace_id)
    if ws is None:
        raise NotFound("Arbejdsrummet findes ikke")
    r = db.get(Referral, workspace_id)
    before = {"ambassador_id": str(r.ambassador_id) if r else None}
    if body.ambassador_id is None:
        if r is not None:
            db.delete(r)
    else:
        a = _get(db, body.ambassador_id)
        if r is None:
            db.add(Referral(workspace_id=workspace_id, ambassador_id=a.id, via="operator"))
        else:
            r.ambassador_id, r.via = a.id, "operator"
    record_audit(db, workspace_id=workspace_id, actor_user_id=principal.user.id, action="referral.moved",
                 object_type="workspace", object_id=workspace_id, before=before,
                 after={"ambassador_id": str(body.ambassador_id) if body.ambassador_id else None, "reason": body.reason},
                 request_id=request.state.request_id)
    db.commit()
    return {"workspace_id": str(workspace_id), "ambassador_id": str(body.ambassador_id) if body.ambassador_id else None}
