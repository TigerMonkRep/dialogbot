"""Ambassador programme: sign-up, attribution, commission ledger and payouts.

Rules (docs/ambassadors/program.md):
- An ambassador earns from customers (workspaces) attributed to them: a one-off bonus when the customer pays
  its first invoice, plus a share of every paid invoice (net, excl. VAT) for `months` months from that first
  paid month. Defaults: 500 kr + 10 % for 12 months, adjustable per ambassador by an operator.
- Nothing is earned before an invoice is PAID. Earnings are held 30 days, then payable. A refund, credit note
  or void reverses what the invoice earned (a negative entry if it was already paid out).
- Attribution happens once, when the workspace is created (link cookie or code); a code typed by the customer
  wins over a link. Self-referral is ignored. Operators may move or remove an attribution (audited).
- The referred customer gets 50 % off the first invoiced month (statement line `ambassador_discount`).
- Payouts: operator-created batches of payable entries ≥ 500 kr. Private ambassadors need CPR + bank details;
  under 18 also a parent's confirmation. B-income is reported by the operator from the yearly CSV.
"""
from __future__ import annotations

import json
import re
import secrets
import unicodedata
import uuid
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session as OrmSession

from app.config import get_settings
from app.core import crypto
from app.core.audit import record_audit
from app.core.errors import Conflict, NotFound, ValidationFailed
from app.core.outbox import enqueue
from app.core.security import new_token, token_digest
from app.models import (
    Ambassador,
    AmbassadorPayout,
    BusinessProfile,
    CommissionEntry,
    Invoice,
    Referral,
    ReferralClick,
    User,
    Workspace,
)

DEFAULT_BONUS_MINOR = 50_000  # 500 kr
DEFAULT_RATE_BP = 1_000  # 10 %
DEFAULT_MONTHS = 12
HOLD_DAYS = 30
MIN_PAYOUT_MINOR = 50_000  # 500 kr
MIN_AGE = 15
ADULT_AGE = 18
CUSTOMER_DISCOUNT_BP = 5_000  # 50 % off the first invoiced month
RULES_VERSION = "ambassador-rules-2026-10"

# The rules every ambassador must answer correctly before signing up. Shown in the sign-up form; checked here.
RULES_QUIZ: list[dict] = [
    {"id": "cold_email", "question": "Må du sende en reklamemail til en virksomhed, du ikke kender?",
     "options": [{"id": "yes", "label": "Ja, bare det er en firmamail"},
                 {"id": "no", "label": "Nej, ikke uden at de har sagt ja til det først"}],
     "correct": "no", "explain": "Uopfordret reklame på mail og sms kræver forudgående samtykke – også til virksomheder."},
    {"id": "disclose", "question": "Du laver et opslag om Dialogbot på Instagram. Hvad skal der stå?",
     "options": [{"id": "nothing", "label": "Ingenting – det er min egen profil"},
                 {"id": "ad", "label": "At det er reklame, fx #reklame, og at jeg får bonus"}],
     "correct": "ad", "explain": "Reklame skal altid kunne ses som reklame. Skjult reklame er ulovlig."},
    {"id": "ai_calls", "question": "Må du bruge Dialogbots AI til at ringe folk op, der ikke har bedt om det?",
     "options": [{"id": "yes", "label": "Ja, det er jo en demo"},
                 {"id": "no", "label": "Nej, AI-opkald kræver, at de har sagt ja først"}],
     "correct": "no", "explain": "Et AI-opkald er et automatisk opkaldssystem og kræver forudgående samtykke."},
    {"id": "phone_protected", "question": "Må du selv ringe til en virksomhed, der er reklamebeskyttet i CVR?",
     "options": [{"id": "yes", "label": "Ja"}, {"id": "no", "label": "Nej, dem ringer jeg ikke til med reklame"}],
     "correct": "no", "explain": "Reklamebeskyttede virksomheder må ikke kontaktes med reklame."},
]
RULES_TEXT = (
    "Jeg anbefaler Dialogbot til folk og virksomheder, jeg selv kender eller møder, og jeg siger altid, at jeg får "
    "en bonus. Jeg markerer opslag som reklame. Jeg sender ikke uopfordrede reklamemails eller -sms'er, jeg bruger "
    "ikke AI eller automatiske opkald til nogen, der ikke har sagt ja, og jeg kontakter ikke reklamebeskyttede "
    "virksomheder. Jeg lover ikke kunder noget, Dialogbot ikke tilbyder. Bryder jeg reglerne, kan min aftale "
    "stoppes, og bonus for kunder skaffet i strid med reglerne bortfalder."
)


def _kr(minor: int) -> str:
    """1234567 → "12.345,67 kr." (whole kroner without decimals)."""
    whole, ore = divmod(minor, 100)
    txt = f"{whole:,}".replace(",", ".")
    return f"{txt},{ore:02d} kr." if ore else f"{txt} kr."


def now() -> datetime:
    return datetime.now(UTC)


def age_on(birth: date, day: date) -> int:
    return day.year - birth.year - ((day.month, day.day) < (birth.month, birth.day))


def is_minor(a: Ambassador, day: date | None = None) -> bool:
    return a.kind == "private" and a.birth_date is not None and age_on(a.birth_date, day or now().date()) < ADULT_AGE


def month_add(m: date, n: int) -> date:
    k = m.year * 12 + (m.month - 1) + n
    return date(k // 12, k % 12 + 1, 1)


def _slugify(s: str) -> str:
    s = unicodedata.normalize("NFKD", s.lower().replace("æ", "ae").replace("ø", "oe").replace("å", "aa"))
    s = re.sub(r"[^a-z0-9]+", "-", s.encode("ascii", "ignore").decode()).strip("-")
    return (s or "ambassador")[:40]


def _unique_slug(db: OrmSession, name: str) -> str:
    base = _slugify(name)
    slug, n = base, 1
    while db.scalar(select(Ambassador.id).where(Ambassador.slug == slug)):
        n += 1
        slug = f"{base}-{n}"
    return slug


def _unique_code(db: OrmSession, name: str) -> str:
    first = re.sub(r"[^A-Z]", "", _slugify(name.split()[0] if name.split() else "").upper())[:8] or "DIALOG"
    for _ in range(50):
        code = f"{first}{secrets.randbelow(90) + 10}"
        if not db.scalar(select(Ambassador.id).where(Ambassador.code == code)):
            return code
    return f"{first}{secrets.token_hex(3).upper()}"


# --------------------------------------------------------------------------- encrypted details

def _aad(a_id: uuid.UUID, what: str) -> bytes:
    return f"ambassador:{a_id}:{what}".encode()


def _seal(a: Ambassador, *, cpr: str | None = None, bank: dict | None = None) -> None:
    """(Re-)encrypt CPR and bank details together under the current key, so both share `secrets_key_version`."""
    cur = reveal(a) if (a.cpr_enc is not None or a.bank_enc is not None) else {"cpr": None, "bank": None}
    if cpr is not None:
        cur["cpr"] = cpr
    if bank is not None:
        cur["bank"] = bank
    if cur["cpr"] is not None:
        env = crypto.encrypt(cur["cpr"].encode(), aad=_aad(a.id, "cpr"))
        a.cpr_enc, a.secrets_key_version = env.blob, env.key_version
    if cur["bank"] is not None:
        env = crypto.encrypt(json.dumps(cur["bank"]).encode(), aad=_aad(a.id, "bank"))
        a.bank_enc, a.secrets_key_version = env.blob, env.key_version
        a.bank_last4 = cur["bank"]["account"][-4:]


def reveal(a: Ambassador) -> dict:
    """Decrypt CPR and bank details. Callers outside this module must audit the reveal."""
    out: dict = {"cpr": None, "bank": None}
    v = a.secrets_key_version or ""
    if a.cpr_enc is not None:
        out["cpr"] = crypto.decrypt(crypto.Envelope(v, a.cpr_enc), aad=_aad(a.id, "cpr")).decode()
    if a.bank_enc is not None:
        out["bank"] = json.loads(crypto.decrypt(crypto.Envelope(v, a.bank_enc), aad=_aad(a.id, "bank")))
    return out


def _check_cpr(cpr: str, birth: date) -> str:
    c = re.sub(r"[\s-]", "", cpr or "")
    if not re.fullmatch(r"\d{10}", c):
        raise ValidationFailed("CPR-nummeret skal være 10 cifre", field_errors=[{"field": "cpr", "message": "10 cifre"}])
    if c[:6] != birth.strftime("%d%m%y"):
        raise ValidationFailed("CPR-nummeret passer ikke med fødselsdatoen",
                               field_errors=[{"field": "cpr", "message": "Passer ikke med fødselsdato"}])
    return c


def _check_bank(reg: str, account: str) -> dict:
    r, k = re.sub(r"\D", "", reg or ""), re.sub(r"\D", "", account or "")
    if len(r) != 4:
        raise ValidationFailed("Registreringsnummeret skal være 4 cifre", field_errors=[{"field": "bank_reg"}])
    if not 6 <= len(k) <= 10:
        raise ValidationFailed("Kontonummeret skal være 6-10 cifre", field_errors=[{"field": "bank_account"}])
    return {"reg": r, "account": k}


def payout_blockers(a: Ambassador) -> list[str]:
    """Why this ambassador cannot be paid yet (empty = ready)."""
    out = []
    if a.status != "active":
        out.append("Ambassadøren er ikke godkendt og aktiv")
    if a.bank_enc is None:
        out.append("Bankoplysninger mangler")
    if a.kind == "private" and a.cpr_enc is None:
        out.append("CPR-nummer mangler (kræves for at indberette B-indkomst)")
    if a.kind == "company" and not a.cvr:
        out.append("CVR-nummer mangler")
    if is_minor(a) and a.parent_consent_at is None:
        out.append("En forælder har ikke godkendt aftalen endnu")
    return out


# --------------------------------------------------------------------------- sign-up

def apply(db: OrmSession, user: User, data: dict, request_id: str | None = None) -> Ambassador:
    if db.scalar(select(Ambassador).where(Ambassador.user_id == user.id)):
        raise Conflict("Du er allerede tilmeldt som ambassadør", code="already_ambassador")
    if user.email_verified_at is None:
        raise ValidationFailed("Bekræft din e-mail først", code="email_not_verified")
    answers = data.get("quiz") or {}
    wrong = [q["id"] for q in RULES_QUIZ if answers.get(q["id"]) != q["correct"]]
    if wrong:
        raise ValidationFailed("Et eller flere svar om reglerne er forkerte – læs forklaringen og prøv igen",
                               code="rules_quiz_failed", extra={"wrong": wrong})
    if data.get("rules_version") != RULES_VERSION:
        raise ValidationFailed("Genindlæs siden – reglerne er opdateret", code="rules_outdated")
    kind = data["kind"]
    name = data["full_name"].strip()
    a = Ambassador(id=uuid.uuid4(), user_id=user.id, kind=kind, full_name=name, phone=(data.get("phone") or "").strip(),
                   headline=(data.get("headline") or "").strip(), motivation=(data.get("motivation") or "").strip(),
                   rules_version=RULES_VERSION, rules_accepted_at=now(), bonus_minor=DEFAULT_BONUS_MINOR,
                   rate_bp=DEFAULT_RATE_BP, months=DEFAULT_MONTHS, slug=_unique_slug(db, name), code=_unique_code(db, name))
    if kind == "private":
        birth = data.get("birth_date")
        if birth is None:
            raise ValidationFailed("Fødselsdato mangler", field_errors=[{"field": "birth_date"}])
        age = age_on(birth, now().date())
        if age < MIN_AGE:
            raise ValidationFailed(f"Du skal være mindst {MIN_AGE} år", code="too_young",
                                   field_errors=[{"field": "birth_date"}])
        a.birth_date = birth
        if age < ADULT_AGE:
            pe = (data.get("parent_email") or "").strip()
            pn = (data.get("parent_name") or "").strip()
            if not pe or not pn:
                raise ValidationFailed("Når du er under 18, skal en forælder godkende aftalen – skriv navn og e-mail",
                                       field_errors=[{"field": "parent_email"}, {"field": "parent_name"}])
            if pe.lower() == user.email.lower():
                raise ValidationFailed("Brug din forælders egen e-mail", field_errors=[{"field": "parent_email"}])
            a.parent_name, a.parent_email = pn, pe
        if data.get("cpr"):
            _seal(a, cpr=_check_cpr(data["cpr"], birth))
    else:
        cvr = re.sub(r"\D", "", data.get("cvr") or "")
        if len(cvr) != 8:
            raise ValidationFailed("CVR-nummeret skal være 8 cifre", field_errors=[{"field": "cvr"}])
        a.cvr, a.company_name = cvr, (data.get("company_name") or "").strip() or name
        a.vat_registered = bool(data.get("vat_registered"))
    if data.get("bank_reg") or data.get("bank_account"):
        _seal(a, bank=_check_bank(data.get("bank_reg", ""), data.get("bank_account", "")))
    db.add(a)
    db.flush()
    if a.parent_email:
        send_parent_request(db, a, user)
    record_audit(db, workspace_id=None, actor_user_id=user.id, action="ambassador.applied", object_type="ambassador",
                 object_id=a.id, after={"kind": kind, "slug": a.slug, "minor": is_minor(a)}, request_id=request_id)
    return a


def update_details(db: OrmSession, a: Ambassador, data: dict, request_id: str | None = None) -> Ambassador:
    if data.get("expected_version") is not None and data["expected_version"] != a.version:
        raise Conflict("Oplysningerne er ændret et andet sted – genindlæs", code="version_conflict")
    changed = []
    if data.get("cpr"):
        if a.kind != "private" or a.birth_date is None:
            raise ValidationFailed("CPR bruges kun for privatpersoner", field_errors=[{"field": "cpr"}])
        _seal(a, cpr=_check_cpr(data["cpr"], a.birth_date))
        changed.append("cpr")
    if data.get("bank_reg") or data.get("bank_account"):
        _seal(a, bank=_check_bank(data.get("bank_reg", ""), data.get("bank_account", "")))
        changed.append("bank")
    for f in ("headline", "phone"):
        if data.get(f) is not None:
            setattr(a, f, data[f].strip())
            changed.append(f)
    if a.kind == "company" and data.get("vat_registered") is not None:
        a.vat_registered = bool(data["vat_registered"])
        changed.append("vat_registered")
    if changed:
        a.version += 1
        a.updated_at = now()
        record_audit(db, workspace_id=None, actor_user_id=a.user_id, action="ambassador.details_updated",
                     object_type="ambassador", object_id=a.id, after={"fields": changed}, request_id=request_id)
    return a


def send_parent_request(db: OrmSession, a: Ambassador, user: User) -> None:
    raw = new_token()
    a.parent_token_hash = token_digest(raw)
    link = f"{get_settings().frontend_base_url}/ambassador/foraelder?token={raw}"
    from app.modules.integrations import email_templates as tpl

    mail = tpl.ambassador_parent(a.parent_name or "", a.full_name, user.email, link, RULES_TEXT,
                                 _kr(a.bonus_minor), f"{a.rate_bp / 100:g} %".replace(".", ","), a.months)
    enqueue(db, event_type="email.ambassador", dedupe_key=f"ambassador-parent:{a.id}:{a.parent_token_hash[:16]}",
            payload={"to_email": a.parent_email, "email": tpl.to_payload(mail)})


def parent_preview(db: OrmSession, raw: str) -> Ambassador:
    a = db.scalar(select(Ambassador).where(Ambassador.parent_token_hash == token_digest(raw or "")))
    if a is None:
        raise NotFound("Linket er ugyldigt eller allerede brugt")
    return a


def parent_confirm(db: OrmSession, raw: str, parent_name: str, request_id: str | None = None) -> Ambassador:
    a = parent_preview(db, raw)
    if a.parent_consent_at is None:
        a.parent_consent_at = now()
        if parent_name.strip():
            a.parent_name = parent_name.strip()[:200]
        a.version += 1
        record_audit(db, workspace_id=None, actor_user_id=None, action="ambassador.parent_consent",
                     object_type="ambassador", object_id=a.id,
                     after={"parent_name": a.parent_name, "parent_email": a.parent_email}, request_id=request_id)
    return a


# --------------------------------------------------------------------------- attribution

def find_by_ref(db: OrmSession, ref: str | None) -> Ambassador | None:
    r = (ref or "").strip()
    if not r or len(r) > 60:
        return None
    a = db.scalar(select(Ambassador).where(func.upper(Ambassador.code) == r.upper()))
    if a is None:
        a = db.scalar(select(Ambassador).where(Ambassador.slug == r.lower()))
    return a if a is not None and a.status == "active" else None


def attribute(db: OrmSession, ws: Workspace, user: User, *, code: str | None, link: str | None,
              request_id: str | None = None) -> Referral | None:
    """Attach the new workspace to an ambassador: a typed code wins over a link. Never raises on a bad ref."""
    if db.get(Referral, ws.id) is not None:
        return None
    for ref, via in ((code, "code"), (link, "link")):
        a = find_by_ref(db, ref)
        if a is None or a.user_id == user.id:
            continue
        r = Referral(workspace_id=ws.id, ambassador_id=a.id, via=via)
        db.add(r)
        record_audit(db, workspace_id=ws.id, actor_user_id=user.id, action="referral.attributed", object_type="workspace",
                     object_id=ws.id, after={"ambassador_id": str(a.id), "via": via}, request_id=request_id)
        return r
    return None


def record_click(db: OrmSession, a: Ambassador) -> None:
    from sqlalchemy.dialects.postgresql import insert

    stmt = insert(ReferralClick).values(id=uuid.uuid4(), ambassador_id=a.id, day=now().date(), count=1)
    db.execute(stmt.on_conflict_do_update(constraint="uq_referral_clicks_day",
                                          set_={"count": ReferralClick.count + 1}))


def discount_line(db: OrmSession, workspace_id: uuid.UUID, month: date, lines: list[dict]) -> dict | None:
    """50 % off the first invoiced month for a referred workspace (the first month with a positive total)."""
    r = db.get(Referral, workspace_id)
    if r is None:
        return None
    earlier = db.scalar(select(Invoice.id).where(Invoice.workspace_id == workspace_id, Invoice.month < month,
                                                 Invoice.net_minor > 0).limit(1))
    if earlier is not None:
        return None
    net = sum(x["net_minor"] for x in lines)
    if net <= 0:
        return None
    a = db.get(Ambassador, r.ambassador_id)
    who = a.full_name.split()[0] if a else "en ambassadør"
    return {"kind": "ambassador_discount", "description": f"Velkomstrabat 50 % første måned (anbefalet af {who})",
            "net_minor": -(net * CUSTOMER_DISCOUNT_BP // 10_000)}


# --------------------------------------------------------------------------- commission

def accrue_for_invoice(db: OrmSession, inv: Invoice) -> list[CommissionEntry]:
    """Called when an invoice is paid. Idempotent (unique invoice+kind)."""
    r = db.get(Referral, inv.workspace_id)
    if r is None or inv.net_minor <= 0:
        return []
    a = db.get(Ambassador, r.ambassador_id)
    if a is None or a.status == "rejected":
        return []
    if r.first_paid_month is None or inv.month < r.first_paid_month:
        r.first_paid_month = inv.month
    hold = now() + timedelta(days=HOLD_DAYS)
    made: list[CommissionEntry] = []
    existing = {e.kind for e in db.scalars(select(CommissionEntry).where(CommissionEntry.invoice_id == inv.id))}
    has_bonus = db.scalar(select(CommissionEntry.id).where(CommissionEntry.ambassador_id == a.id,
                                                           CommissionEntry.workspace_id == inv.workspace_id,
                                                           CommissionEntry.kind == "bonus").limit(1))
    if not has_bonus and a.bonus_minor > 0:
        made.append(CommissionEntry(ambassador_id=a.id, workspace_id=inv.workspace_id, invoice_id=inv.id, kind="bonus",
                                    month=inv.month, base_minor=inv.net_minor, amount_minor=a.bonus_minor, hold_until=hold))
    if "share" not in existing and inv.month < month_add(r.first_paid_month, a.months) and a.rate_bp > 0:
        amount = (inv.net_minor * a.rate_bp + 5_000) // 10_000
        if amount > 0:
            made.append(CommissionEntry(ambassador_id=a.id, workspace_id=inv.workspace_id, invoice_id=inv.id,
                                        kind="share", month=inv.month, base_minor=inv.net_minor, amount_minor=amount,
                                        hold_until=hold))
    for e in made:
        db.add(e)
    if made:
        db.flush()
        record_audit(db, workspace_id=inv.workspace_id, actor_user_id=None, action="commission.accrued",
                     object_type="invoice", object_id=inv.id,
                     after={"ambassador_id": str(a.id), "entries": [{"kind": e.kind, "amount_minor": e.amount_minor}
                                                                     for e in made]})
    return made


def reverse_for_invoice(db: OrmSession, inv: Invoice, *, source_ref: str, fraction: float = 1.0) -> int:
    """Undo what an invoice earned (refund, credit note, void). `fraction` = refunded share of the invoice.

    Not yet paid out → the entry is reduced (or marked reversed when fully refunded). Already paid → a negative
    `reversal` entry, payable immediately, that the next payout deducts. The bonus is only reversed on a full
    refund. Idempotent per `source_ref`."""
    fraction = max(0.0, min(1.0, fraction))
    if fraction <= 0 or db.scalar(select(CommissionEntry.id).where(CommissionEntry.invoice_id == inv.id,
                                                                   CommissionEntry.kind == "reversal",
                                                                   CommissionEntry.source_ref == source_ref)):
        return 0
    entries = db.scalars(select(CommissionEntry).where(CommissionEntry.invoice_id == inv.id,
                                                       CommissionEntry.kind.in_(("bonus", "share")),
                                                       CommissionEntry.status != "reversed")).all()
    full = fraction >= 0.999
    clawback = 0
    touched = 0
    amb: uuid.UUID | None = None
    for e in entries:
        if e.kind == "bonus" and not full:
            continue
        cut = e.amount_minor if full else round(e.amount_minor * fraction)
        if cut <= 0:
            continue
        touched += 1
        if e.status in ("held", "payable") and e.payout_id is None:
            if cut >= e.amount_minor:
                e.status = "reversed"
            else:
                e.amount_minor -= cut
        else:
            clawback += cut
            amb = e.ambassador_id
    if clawback and amb is not None:
        db.add(CommissionEntry(ambassador_id=amb, workspace_id=inv.workspace_id, invoice_id=inv.id, kind="reversal",
                               source_ref=source_ref[:64], month=inv.month, base_minor=0, amount_minor=-clawback,
                               status="payable", hold_until=now()))
    if touched:
        record_audit(db, workspace_id=inv.workspace_id, actor_user_id=None, action="commission.reversed",
                     object_type="invoice", object_id=inv.id,
                     after={"source": source_ref, "fraction": round(fraction, 4), "clawback_minor": clawback})
    return touched


def release_held(db: OrmSession) -> int:
    """Worker job: held entries whose 30 days have passed become payable."""
    rows = db.scalars(select(CommissionEntry).where(CommissionEntry.status == "held",
                                                    CommissionEntry.hold_until <= now())).all()
    for e in rows:
        e.status = "payable"
    return len(rows)


# --------------------------------------------------------------------------- payouts

def balances(db: OrmSession, ambassador_id: uuid.UUID) -> dict:
    rows = db.execute(select(CommissionEntry.status, CommissionEntry.payout_id.is_(None), func.sum(CommissionEntry.amount_minor))
                      .where(CommissionEntry.ambassador_id == ambassador_id)
                      .group_by(CommissionEntry.status, CommissionEntry.payout_id.is_(None))).all()
    out = {"held_minor": 0, "payable_minor": 0, "in_payout_minor": 0, "paid_minor": 0}
    for status, unassigned, total in rows:
        total = int(total or 0)
        if status == "held":
            out["held_minor"] += total
        elif status == "payable" and unassigned:
            out["payable_minor"] += total
        elif status == "payable":
            out["in_payout_minor"] += total
        elif status == "paid":
            out["paid_minor"] += total
    out["min_payout_minor"] = MIN_PAYOUT_MINOR
    return out


def create_payouts(db: OrmSession, operator_id: uuid.UUID, ambassador_ids: list[uuid.UUID] | None = None,
                   request_id: str | None = None) -> tuple[list[AmbassadorPayout], list[dict]]:
    """One pending payout per ready ambassador whose payable balance is ≥ 500 kr. Returns (created, skipped)."""
    q = select(Ambassador).where(Ambassador.status == "active")
    if ambassador_ids:
        q = q.where(Ambassador.id.in_(ambassador_ids))
    created, skipped = [], []
    for a in db.scalars(q.with_for_update()).all():
        entries = db.scalars(select(CommissionEntry).where(CommissionEntry.ambassador_id == a.id,
                                                           CommissionEntry.status == "payable",
                                                           CommissionEntry.payout_id.is_(None))
                             .with_for_update()).all()
        total = sum(e.amount_minor for e in entries)
        if not entries:
            continue
        if total < MIN_PAYOUT_MINOR:
            skipped.append({"ambassador_id": str(a.id), "name": a.full_name, "reason": "Under 500 kr", "amount_minor": total})
            continue
        blockers = payout_blockers(a)
        if blockers:
            skipped.append({"ambassador_id": str(a.id), "name": a.full_name, "reason": "; ".join(blockers),
                            "amount_minor": total})
            continue
        number = (db.scalar(select(func.max(AmbassadorPayout.number))) or 1000) + 1
        p = AmbassadorPayout(ambassador_id=a.id, number=number, amount_minor=total, created_by=operator_id,
                             income_type="b_income" if a.kind == "private" else "invoice")
        db.add(p)
        db.flush()
        for e in entries:
            e.payout_id = p.id
        record_audit(db, workspace_id=None, actor_user_id=operator_id, action="ambassador.payout_created",
                     object_type="ambassador_payout", object_id=p.id,
                     after={"ambassador_id": str(a.id), "amount_minor": total, "entries": len(entries)},
                     request_id=request_id)
        created.append(p)
    return created, skipped


def mark_paid(db: OrmSession, p: AmbassadorPayout, operator_id: uuid.UUID, reference: str,
              request_id: str | None = None) -> AmbassadorPayout:
    if p.status != "pending":
        raise Conflict("Udbetalingen er ikke afventende", code="payout_not_pending")
    p.status, p.paid_at, p.paid_by, p.reference = "paid", now(), operator_id, reference.strip()[:100]
    for e in db.scalars(select(CommissionEntry).where(CommissionEntry.payout_id == p.id)):
        e.status = "paid"
    record_audit(db, workspace_id=None, actor_user_id=operator_id, action="ambassador.payout_paid",
                 object_type="ambassador_payout", object_id=p.id,
                 after={"amount_minor": p.amount_minor, "reference": p.reference}, request_id=request_id)
    a = db.get(Ambassador, p.ambassador_id)
    u = db.get(User, a.user_id) if a else None
    if a and u:
        from app.modules.integrations import email_templates as tpl

        mail = tpl.ambassador_paid(a.full_name.split()[0], _kr(p.amount_minor), a.bank_last4, p.number,
                                   p.income_type == "b_income", f"{get_settings().frontend_base_url}/ambassador")
        enqueue(db, event_type="email.ambassador", dedupe_key=f"ambassador-paid:{p.id}",
                payload={"to_email": u.email, "email": tpl.to_payload(mail)})
    return p


def cancel_payout(db: OrmSession, p: AmbassadorPayout, operator_id: uuid.UUID, request_id: str | None = None) -> None:
    if p.status != "pending":
        raise Conflict("Kun afventende udbetalinger kan annulleres", code="payout_not_pending")
    p.status = "cancelled"
    for e in db.scalars(select(CommissionEntry).where(CommissionEntry.payout_id == p.id)):
        e.payout_id = None
    record_audit(db, workspace_id=None, actor_user_id=operator_id, action="ambassador.payout_cancelled",
                 object_type="ambassador_payout", object_id=p.id, request_id=request_id)


def b_income_rows(db: OrmSession, year: int) -> list[dict]:
    """Paid B-income per private ambassador in a calendar year (for eIndkomst). Decrypts CPR: audit the caller."""
    start = datetime(year, 1, 1, tzinfo=UTC)
    end = datetime(year + 1, 1, 1, tzinfo=UTC)
    rows = db.execute(select(AmbassadorPayout.ambassador_id, func.sum(AmbassadorPayout.amount_minor),
                             func.count(AmbassadorPayout.id))
                      .where(AmbassadorPayout.status == "paid", AmbassadorPayout.income_type == "b_income",
                             AmbassadorPayout.paid_at >= start, AmbassadorPayout.paid_at < end)
                      .group_by(AmbassadorPayout.ambassador_id)).all()
    out = []
    for aid, total, n in rows:
        a = db.get(Ambassador, aid)
        out.append({"name": a.full_name, "cpr": reveal(a).get("cpr") or "", "amount_minor": int(total or 0),
                    "payouts": int(n), "ambassador_id": str(aid)})
    return sorted(out, key=lambda x: x["name"])


# --------------------------------------------------------------------------- views

def customers(db: OrmSession, ambassador_id: uuid.UUID) -> list[dict]:
    """What an ambassador may see about their customers: company name, status, start month, what they earned."""
    rows = db.execute(select(Referral, Workspace).join(Workspace, Workspace.id == Referral.workspace_id)
                      .where(Referral.ambassador_id == ambassador_id).order_by(Referral.attributed_at.desc())).all()
    earned = dict(db.execute(select(CommissionEntry.workspace_id, func.sum(CommissionEntry.amount_minor))
                             .where(CommissionEntry.ambassador_id == ambassador_id,
                                    CommissionEntry.status != "reversed")
                             .group_by(CommissionEntry.workspace_id)).all())
    a = db.get(Ambassador, ambassador_id)
    out = []
    for r, ws in rows:
        p = db.get(BusinessProfile, ws.id)
        if ws.status != "active":
            status = "opsagt"
        elif r.first_paid_month is None:
            status = "i gang med opstart"
        elif a and month_add(r.first_paid_month, a.months) <= now().date().replace(day=1):
            status = "betalende (bonusperiode slut)"
        else:
            status = "betalende"
        out.append({"workspace_id": str(ws.id), "company": (p.legal_name if p and p.legal_name else ws.name),
                    "status": status, "signed_up": r.attributed_at.date().isoformat(), "via": r.via,
                    "first_paid_month": r.first_paid_month.strftime("%Y-%m") if r.first_paid_month else None,
                    "share_until": (month_add(r.first_paid_month, a.months).strftime("%Y-%m")
                                    if r.first_paid_month and a else None),
                    "earned_minor": int(earned.get(ws.id) or 0)})
    return out


def entry_out(db: OrmSession, e: CommissionEntry, names: dict | None = None) -> dict:
    ws_name = (names or {}).get(e.workspace_id)
    if ws_name is None:
        p = db.get(BusinessProfile, e.workspace_id)
        ws = db.get(Workspace, e.workspace_id)
        ws_name = p.legal_name if p and p.legal_name else (ws.name if ws else "")
        if names is not None:
            names[e.workspace_id] = ws_name
    label = {"bonus": "Startbonus", "share": "Løbende andel", "reversal": "Modregning (refusion)"}[e.kind]
    status = "under udbetaling" if e.status == "payable" and e.payout_id else {
        "held": "optjent – frigives", "payable": "klar til udbetaling", "paid": "udbetalt", "reversed": "annulleret"}[e.status]
    return {"id": str(e.id), "kind": e.kind, "label": label, "company": ws_name, "month": e.month.strftime("%Y-%m"),
            "base_minor": e.base_minor, "amount_minor": e.amount_minor, "status": e.status, "status_label": status,
            "hold_until": e.hold_until.date().isoformat(), "payout_id": str(e.payout_id) if e.payout_id else None,
            "created_at": e.created_at.isoformat()}


def payout_out(p: AmbassadorPayout) -> dict:
    return {"id": str(p.id), "number": p.number, "status": p.status, "amount_minor": p.amount_minor,
            "income_type": p.income_type, "reference": p.reference, "paid_at": p.paid_at.isoformat() if p.paid_at else None,
            "created_at": p.created_at.isoformat()}


def clicks(db: OrmSession, ambassador_id: uuid.UUID, days: int = 30) -> int:
    since = now().date() - timedelta(days=days)
    return int(db.scalar(select(func.coalesce(func.sum(ReferralClick.count), 0))
                         .where(ReferralClick.ambassador_id == ambassador_id, ReferralClick.day >= since)) or 0)


def link_for(a: Ambassador) -> str:
    return f"{get_settings().frontend_base_url}/a/{a.slug}"


def profile_out(db: OrmSession, a: Ambassador, user: User | None = None) -> dict:
    n_customers = db.scalar(select(func.count()).select_from(Referral).where(Referral.ambassador_id == a.id)) or 0
    n_paying = db.scalar(select(func.count()).select_from(Referral).where(Referral.ambassador_id == a.id,
                                                                          Referral.first_paid_month.is_not(None))) or 0
    return {
        "id": str(a.id), "status": a.status, "kind": a.kind, "full_name": a.full_name, "email": user.email if user else None,
        "phone": a.phone, "slug": a.slug, "code": a.code, "link": link_for(a), "headline": a.headline,
        "company_name": a.company_name, "cvr": a.cvr, "vat_registered": a.vat_registered,
        "birth_date": a.birth_date.isoformat() if a.birth_date else None, "minor": is_minor(a),
        "parent_name": a.parent_name, "parent_email": a.parent_email,
        "parent_consent_at": a.parent_consent_at.isoformat() if a.parent_consent_at else None,
        "has_cpr": a.cpr_enc is not None, "has_bank": a.bank_enc is not None, "bank_last4": a.bank_last4,
        "terms": {"bonus_minor": a.bonus_minor, "rate_bp": a.rate_bp, "months": a.months,
                  "hold_days": HOLD_DAYS, "customer_discount_bp": CUSTOMER_DISCOUNT_BP},
        "payout_blockers": payout_blockers(a), "decision_note": a.decision_note,
        "stats": {"clicks_30d": clicks(db, a.id), "customers": int(n_customers), "paying": int(n_paying)},
        "balances": balances(db, a.id), "version": a.version, "created_at": a.created_at.isoformat(),
    }
