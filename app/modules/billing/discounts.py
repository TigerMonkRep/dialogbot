"""Discount codes – made by operators in the admin, used by Erhverv and Privat customers.

One table of codes (billing/README: «rabatkoder»), two ways in:

- Erhverv: the owner types the code on Konto → one redemption per workspace. From then on the monthly statement
  carries a negative line «Rabatkode VELKOMMEN: 20 %» (and so does the Stripe invoice): `once` = the first month
  from the redemption on, `repeating` = duration_months months, `forever` = every month. Percent is of the
  month's positive lines; an amount is ex VAT and never more than the month.
- Privat: the plan is paid through Stripe Checkout, so the code is mirrored to a Stripe coupon + promotion code
  when it is made. Checkout gets `discounts=[{promotion_code}]` when the customer arrives with the code (the plan
  picker, ?kode=) and otherwise shows Stripe's own «Tilføj rabatkode» field; the completed session tells us which
  promotion code was used and that becomes the redemption.

Codes are A–Z and 0–9, 3–20 characters, stored upper-case; a code is valid when it is active, inside its window
and under its cap. Nothing here reads payment state into calls or tasks.
"""
from __future__ import annotations

import re
import uuid
from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session as OrmSession

from app.core.errors import Conflict, NotFound, ValidationFailed
from app.models import DISCOUNT_AUDIENCES, DISCOUNT_DURATIONS, DiscountCode, DiscountRedemption, Workspace
from app.modules.billing import stripe as stripe_api

CODE_RE = re.compile(r"^[A-Z0-9]{3,20}$")
LINE_KIND = "discount_code"
MAX_AMOUNT_MINOR = 1_000_000  # 10.000 kr.


def now() -> datetime:
    return datetime.now(UTC)


def normalize(code: str) -> str:
    return re.sub(r"[\s\-_]", "", (code or "")).upper()


def _check_terms(*, audience: str, percent_off: int | None, amount_off_minor: int | None, duration: str,
                 duration_months: int | None, max_redemptions: int | None, starts_at: datetime | None,
                 ends_at: datetime | None) -> None:
    if audience not in DISCOUNT_AUDIENCES:
        raise ValidationFailed("Vælg Erhverv, Privat eller begge", field_errors=[{"field": "audience"}])
    if (percent_off is None) == (amount_off_minor is None):
        raise ValidationFailed("Angiv enten procent eller beløb – ikke begge", field_errors=[{"field": "percent_off"}])
    if percent_off is not None and not 1 <= percent_off <= 100:
        raise ValidationFailed("Procenten skal være mellem 1 og 100", field_errors=[{"field": "percent_off"}])
    if amount_off_minor is not None and not 1 <= amount_off_minor <= MAX_AMOUNT_MINOR:
        raise ValidationFailed("Beløbet skal være mellem 0,01 og 10.000 kr.", field_errors=[{"field": "amount_off_minor"}])
    if duration not in DISCOUNT_DURATIONS:
        raise ValidationFailed("Vælg én gang, et antal måneder eller altid", field_errors=[{"field": "duration"}])
    if duration == "repeating" and not (duration_months and 1 <= duration_months <= 36):
        raise ValidationFailed("Antal måneder skal være mellem 1 og 36", field_errors=[{"field": "duration_months"}])
    if max_redemptions is not None and max_redemptions < 1:
        raise ValidationFailed("Maks. antal skal være mindst 1", field_errors=[{"field": "max_redemptions"}])
    if starts_at and ends_at and ends_at <= starts_at:
        raise ValidationFailed("Slutdatoen skal ligge efter startdatoen", field_errors=[{"field": "ends_at"}])


def create(db: OrmSession, *, code: str, audience: str, percent_off: int | None = None, amount_off_minor: int | None = None,
           duration: str = "once", duration_months: int | None = None, max_redemptions: int | None = None,
           starts_at: datetime | None = None, ends_at: datetime | None = None, note: str = "",
           created_by: uuid.UUID | None = None) -> DiscountCode:
    c = normalize(code)
    if not CODE_RE.fullmatch(c):
        raise ValidationFailed("Koden skal være 3-20 bogstaver eller tal (A-Z, 0-9)", field_errors=[{"field": "code"}])
    if duration != "repeating":
        duration_months = None
    _check_terms(audience=audience, percent_off=percent_off, amount_off_minor=amount_off_minor, duration=duration,
                 duration_months=duration_months, max_redemptions=max_redemptions, starts_at=starts_at, ends_at=ends_at)
    if db.scalar(select(DiscountCode.id).where(DiscountCode.code == c)):
        raise Conflict("Koden findes allerede", code="code_taken")
    row = DiscountCode(code=c, audience=audience, percent_off=percent_off, amount_off_minor=amount_off_minor,
                       duration=duration, duration_months=duration_months, max_redemptions=max_redemptions,
                       starts_at=starts_at, ends_at=ends_at, active=True, note=(note or "").strip()[:300], created_by=created_by)
    db.add(row)
    db.flush()
    if audience in ("privat", "begge") and stripe_api.configured():
        _mirror_to_stripe(row)
    return row


def _mirror_to_stripe(row: DiscountCode) -> None:
    """A Stripe coupon with the same terms and a promotion code with the same text, so Checkout can apply it."""
    coupon: dict = {"name": row.code, "duration": row.duration, "metadata": {"dialogbot_discount_code": str(row.id)}}
    if row.duration == "repeating":
        coupon["duration_in_months"] = row.duration_months
    if row.percent_off is not None:
        coupon["percent_off"] = row.percent_off
    else:
        coupon["amount_off"] = row.amount_off_minor
        coupon["currency"] = "dkk"
    if row.max_redemptions:
        coupon["max_redemptions"] = row.max_redemptions
    if row.ends_at:
        coupon["redeem_by"] = int(row.ends_at.timestamp())
    cp = stripe_api.request("POST", "/coupons", coupon, idempotency_key=f"dialogbot-coupon-{row.id}")
    row.stripe_coupon_id = cp["id"]
    # Stripe API 2025-10+: a promotion code points at `promotion` ({type, coupon}); the old top-level `coupon`
    # parameter is rejected ("Received unknown parameter: coupon").
    pc = stripe_api.request("POST", "/promotion_codes", {"promotion": {"type": "coupon", "coupon": cp["id"]},
                                                        "code": row.code, "active": True,
                                                        "metadata": {"dialogbot_discount_code": str(row.id)}},
                            idempotency_key=f"dialogbot-promo-{row.id}")
    row.stripe_promotion_code_id = pc["id"]


def deactivate(db: OrmSession, code_id: uuid.UUID) -> DiscountCode:
    row = db.get(DiscountCode, code_id)
    if row is None:
        raise NotFound("Rabatkoden findes ikke")
    row.active = False
    row.updated_at = now()
    if row.stripe_promotion_code_id and stripe_api.configured():
        stripe_api.request("POST", f"/promotion_codes/{row.stripe_promotion_code_id}", {"active": False})
    return row


def redemptions(db: OrmSession, code_id: uuid.UUID) -> int:
    return int(db.scalar(select(func.count(DiscountRedemption.id)).where(DiscountRedemption.code_id == code_id)) or 0)


def lookup(db: OrmSession, code: str, *, audience: str, at: datetime | None = None) -> DiscountCode:
    """The usable code for this audience, or a ValidationFailed that says why not (field «code»)."""
    at = at or now()
    c = normalize(code)
    row = db.scalar(select(DiscountCode).where(DiscountCode.code == c)) if c else None
    if row is None:
        raise ValidationFailed("Rabatkoden findes ikke", field_errors=[{"field": "code"}])
    if not row.active:
        raise ValidationFailed("Rabatkoden er ikke længere aktiv", field_errors=[{"field": "code"}])
    if row.audience not in ("begge", audience):
        raise ValidationFailed("Rabatkoden gælder ikke her", field_errors=[{"field": "code"}])
    if row.starts_at and at < row.starts_at:
        raise ValidationFailed("Rabatkoden kan ikke bruges endnu", field_errors=[{"field": "code"}])
    if row.ends_at and at > row.ends_at:
        raise ValidationFailed("Rabatkoden er udløbet", field_errors=[{"field": "code"}])
    if row.max_redemptions is not None and redemptions(db, row.id) >= row.max_redemptions:
        raise ValidationFailed("Rabatkoden er brugt op", field_errors=[{"field": "code"}])
    return row


def describe(row: DiscountCode) -> str:
    """«20 % i 3 måneder», «500 kr. én gang», «10 % altid»."""
    value = f"{row.percent_off} %" if row.percent_off is not None else f"{row.amount_off_minor / 100:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".") + " kr."
    when = ("én gang" if row.duration == "once" else "altid" if row.duration == "forever"
            else f"i {row.duration_months} måned{'er' if row.duration_months != 1 else ''}")
    return f"{value} {when}"


def out(db: OrmSession, row: DiscountCode) -> dict:
    return {"id": str(row.id), "code": row.code, "audience": row.audience, "percent_off": row.percent_off,
            "amount_off_minor": row.amount_off_minor, "duration": row.duration, "duration_months": row.duration_months,
            "max_redemptions": row.max_redemptions, "redemptions": redemptions(db, row.id),
            "starts_at": row.starts_at.isoformat() if row.starts_at else None,
            "ends_at": row.ends_at.isoformat() if row.ends_at else None, "active": row.active, "note": row.note,
            "text": describe(row), "stripe": bool(row.stripe_promotion_code_id),
            "created_at": row.created_at.isoformat()}


# --------------------------------------------------------------------------- Erhverv

def erhverv_redemption(db: OrmSession, ws_id: uuid.UUID) -> DiscountRedemption | None:
    return db.scalar(select(DiscountRedemption).where(DiscountRedemption.workspace_id == ws_id,
                                                      DiscountRedemption.audience == "erhverv")
                     .order_by(DiscountRedemption.redeemed_at.desc()).limit(1))


def redeem_erhverv(db: OrmSession, ws_id: uuid.UUID, code: str) -> DiscountRedemption:
    """The owner types a code on Konto. One code per workspace; it starts counting from this month."""
    ws = db.get(Workspace, ws_id)
    if ws is None or ws.kind != "business":
        raise NotFound("Arbejdsrummet findes ikke")
    if erhverv_redemption(db, ws_id) is not None:
        raise Conflict("I har allerede brugt en rabatkode", code="discount_already_used")
    row = lookup(db, code, audience="erhverv")
    if row.percent_off is None:
        from app.modules.billing.customer_market import currency_of

        if currency_of(db, ws_id) != "DKK":
            raise ValidationFailed("Rabatkoden er et beløb i danske kroner og kan ikke bruges i jeres valuta",
                                   code="discount_currency_mismatch", field_errors=[{"field": "code"}])
    r = DiscountRedemption(code_id=row.id, workspace_id=ws_id, audience="erhverv", source="erhverv_konto")
    db.add(r)
    db.flush()
    return r


def erhverv_status(db: OrmSession, ws_id: uuid.UUID, tz: str) -> dict:
    r = erhverv_redemption(db, ws_id)
    if r is None:
        return {"code": None, "can_add": True}
    row = db.get(DiscountCode, r.code_id)
    first = _month_of(r.redeemed_at, tz)
    last = (None if row.duration == "forever" else first if row.duration == "once"
            else _add_months(first, row.duration_months - 1))
    return {"code": row.code, "text": describe(row), "from_month": first.strftime("%Y-%m"),
            "to_month": last.strftime("%Y-%m") if last else None, "can_add": False}


def _month_of(at: datetime, tz: str) -> date:
    return at.astimezone(ZoneInfo(tz)).date().replace(day=1)


def _add_months(m: date, n: int) -> date:
    k = m.month - 1 + n
    return date(m.year + k // 12, k % 12 + 1, 1)


def describe_en(row: DiscountCode) -> str:
    """English for statements in other currencies than DKK: «20 % for 3 months», «10 % always»."""
    value = f"{row.percent_off} %" if row.percent_off is not None else f"DKK {row.amount_off_minor / 100:,.2f}"
    when = ("once" if row.duration == "once" else "always" if row.duration == "forever"
            else f"for {row.duration_months} month{'s' if row.duration_months != 1 else ''}")
    return f"{value} {when}"


def erhverv_line(db: OrmSession, ws_id: uuid.UUID, month: date, tz: str, lines: list[dict], *,
                 currency: str = "DKK") -> dict | None:
    """The statement's negative line for the workspace's code in this month, or None. An amount-off code is in DKK,
    so it only applies to a DKK statement (redeem_erhverv refuses it for other currencies)."""
    r = erhverv_redemption(db, ws_id)
    if r is None:
        return None
    row = db.get(DiscountCode, r.code_id)
    if row.percent_off is None and currency != "DKK":
        return None
    first = _month_of(r.redeemed_at, tz)
    month = month.replace(day=1)
    if month < first:
        return None
    if row.duration == "once" and month != first:
        return None
    if row.duration == "repeating" and month > _add_months(first, row.duration_months - 1):
        return None
    positive = sum(x["net_minor"] for x in lines if x["net_minor"] > 0)
    if positive <= 0:
        return None
    off = positive * row.percent_off // 100 if row.percent_off is not None else min(positive, row.amount_off_minor)
    if off <= 0:
        return None
    text = f"Rabatkode {row.code}: {describe(row)}" if currency == "DKK" else f"Discount code {row.code}: {describe_en(row)}"
    return {"kind": LINE_KIND, "code": row.code, "description": text, "net_minor": -off}


# --------------------------------------------------------------------------- Privat

def privat_checkout_discounts(db: OrmSession, code: str | None) -> list[dict] | None:
    """`discounts` for a Privat Checkout Session when the customer arrives with a code; None without one."""
    if not code or not normalize(code):
        return None
    row = lookup(db, code, audience="privat")
    if not row.stripe_promotion_code_id:
        raise ValidationFailed("Rabatkoden kan ikke bruges til betaling endnu", field_errors=[{"field": "code"}])
    return [{"promotion_code": row.stripe_promotion_code_id}]


def record_privat_redemption(db: OrmSession, ws_id: uuid.UUID, session: dict) -> DiscountRedemption | None:
    """A completed Checkout Session: the promotion code it used (if any) becomes the workspace's redemption."""
    refs: set[str] = set()
    for d in session.get("discounts") or []:
        pc = d.get("promotion_code") if isinstance(d, dict) else None
        if isinstance(pc, dict):
            pc = pc.get("id")
        if pc:
            refs.add(str(pc))
    if not refs:
        return None
    row = db.scalar(select(DiscountCode).where(DiscountCode.stripe_promotion_code_id.in_(refs)))
    if row is None:
        return None
    existing = db.scalar(select(DiscountRedemption).where(DiscountRedemption.code_id == row.id,
                                                          DiscountRedemption.workspace_id == ws_id))
    if existing is not None:
        return existing
    r = DiscountRedemption(code_id=row.id, workspace_id=ws_id, audience="privat", source="privat_checkout",
                           stripe_ref=str(session.get("id") or "")[:80] or None)
    db.add(r)
    db.flush()
    return r
