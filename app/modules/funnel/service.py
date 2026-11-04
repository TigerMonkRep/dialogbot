"""Quiz-funnels (docs/funnel-api.md): /start (Erhverv) and /privat/start (Privat).

A visitor answers one question per screen. While they answer, a FunnelDraft (no account, no identity) collects the
answers and what Dialogbot builds from them:
- Erhverv: the company from Google Places (name, address, phone, website, opening hours), an estimate of missed
  calls, the industry voice, and – when the website is known – a crawl of the site, kept on the draft until there is
  a workspace to import it into.
- Privat: a preview of the tasks and lists Peter would set up (privat_seed.plan). Nothing is created.

The reveal needs the gate: name, e-mail, mobile → a 6-digit SMS code (10 minutes, 5 attempts, only an HMAC stored).
verify() then creates or logs in the user, starts a session like POST /auth/login, and
- Erhverv: creates the business workspace with profile, category, voice and the crawled knowledge as UNAPPROVED
  drafts, and asks Peter to ring the number the visitor just proved (sales.service.request_web, with the company's
  public facts as context) – never before the SMS code.
- Privat: creates the private account (trial starts) and the real tasks: lists, reminders, and call proposals
  WITHOUT a number («Hvad er deres nummer?»), so nothing is ever dialled from the funnel.

Drafts that never reached verification are deleted by the worker seven days after creation (purge_expired).
"""
from __future__ import annotations

import hashlib
import hmac
import re
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import structlog
from sqlalchemy import delete, select
from sqlalchemy.orm import Session as OrmSession
from sqlalchemy.orm.attributes import flag_modified

from app.config import get_settings
from app.core.audit import record_audit
from app.core.errors import ApiError, Conflict, Forbidden, NotFound, ValidationFailed
from app.core.outbox import enqueue
from app.core.security import hash_password, new_token, normalize_email, token_digest
from app.models import (
    AuthToken,
    BusinessProfile,
    Call,
    DemoCall,
    FunnelDraft,
    KnowledgeItem,
    KnowledgeVersion,
    User,
    Workspace,
    WorkspaceCategory,
    WorkspaceVoiceSettings,
)
from app.modules.funnel import estimates, privat_seed
from app.modules.privat import phone as sms_code
from app.modules.privat import rules
from app.modules.sales import places as gp

log = structlog.get_logger("dialogbot.funnel")

KINDS = ("erhverv", "privat")
TTL = timedelta(days=7)
CODE_TTL, MAX_ATTEMPTS, RESEND_AFTER = sms_code.CODE_TTL, sms_code.MAX_ATTEMPTS, sms_code.RESEND_AFTER
MAX_STEP = 7
PLACES_RESULTS = 5
PLACES_CENTER, PLACES_RADIUS_M = (56.0, 10.5), 50_000  # a bias over Denmark; the visitor types the company's name
CONSENT_VERSION = "funnel-gate-v1"
CONSENT_TEXT_ERHVERV = ("Ja tak, Peter fra Dialogbot, en digital assistent, må ringe mig op på dette nummer, når jeg "
                        "har bekræftet koden, og vise, hvordan Dialogbot tager telefonen for min virksomhed. Opkaldet "
                        "bliver skrevet ned, og en medarbejder fra Dialogbot må kontakte mig bagefter om det, vi talte "
                        "om. Dialogbot må oprette en konto til mig med denne e-mail og dette mobilnummer.")
CONSENT_TEXT_PRIVAT = ("Ja tak, Dialogbot må oprette en privat konto til mig med denne e-mail og dette mobilnummer og "
                       "sætte mine opgaver op. Der ringes ikke til nogen, før jeg selv godkender et opkald.")
NEXT = {"erhverv": "/start/klar", "privat": "/privat/dag?velkommen=1"}
PRIVAT_PATHS = {"postponed": list, "household": str, "hate_calls": str, "remind_at": str}
ERHVERV_PATHS = {"industry": str, "company_name": str, "place_id": str, "missed": list, "missed_per_week": int,
                 "wants": list}


def _now() -> datetime:
    return datetime.now(UTC)


# --------------------------------------------------------------------------- drafts

def create(db: OrmSession, *, kind: str, hook: str | None, industry: str | None, utm: dict | None) -> FunnelDraft:
    if kind not in KINDS:
        raise ValidationFailed("Ukendt funnel", field_errors=[{"field": "kind"}])
    utm = {k: str(v)[:120] for k, v in (utm or {}).items() if k in ("source", "medium", "campaign", "content") and v}
    d = FunnelDraft(kind=kind, hook=(hook or "").strip()[:80] or None, industry=estimates.normalize_industry(industry),
                    utm=utm, step=1, answers={}, build={}, expires_at=_now() + TTL)
    if d.industry:
        d.answers = {"industry": d.industry}
    d.build = _build(d)
    db.add(d)
    db.flush()
    return d


def get(db: OrmSession, draft_id: uuid.UUID, *, lock: bool = False) -> FunnelDraft:
    q = select(FunnelDraft).where(FunnelDraft.id == draft_id)
    d = db.scalar(q.with_for_update() if lock else q)
    if d is None:
        raise NotFound("Vi kunne ikke finde dine svar. Start forfra.", code="draft_not_found")
    if d.user_id is None and d.expires_at <= _now():
        raise NotFound("Dine svar er udløbet. Start forfra.", code="draft_expired")
    return d


def _clean(value, typ):
    if typ is list:
        return [str(x).strip()[:40] for x in value if str(x).strip()][:12] if isinstance(value, list) else None
    if typ is int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return None
    return re.sub(r"[<>{}\[\]`]", "", str(value)).strip()[:200] if value is not None else None


def patch(db: OrmSession, d: FunnelDraft, *, step: int, answers: dict) -> tuple[FunnelDraft, bool]:
    """Merge answers (later answers win), record the step, and do the step's work. Returns (draft, crawl_needed):
    the router starts the crawl in the background when crawl_needed is true (step 4 with a website)."""
    if d.user_id is not None:
        raise Conflict("Kontoen er oprettet – svarene kan ikke ændres mere", code="draft_verified")
    allowed = ERHVERV_PATHS if d.kind == "erhverv" else PRIVAT_PATHS
    merged = dict(d.answers or {})
    for k, typ in allowed.items():
        if k in answers:
            v = _clean(answers[k], typ)
            if v is None or v == "" or v == []:
                merged.pop(k, None)
            else:
                merged[k] = v
    d.answers = merged
    d.step = max(1, min(int(step), MAX_STEP))
    crawl_needed = False
    if d.kind == "erhverv":
        if "industry" in merged:
            d.industry = estimates.normalize_industry(merged["industry"]) or d.industry
            merged["industry"] = d.industry or merged["industry"]
        if d.step >= 2 and (merged.get("company_name") or merged.get("place_id")):
            _lookup_company(db, d)
        if d.step >= 3:
            d.estimate = estimates.estimate(d.industry, merged.get("missed"), merged.get("missed_per_week"))
        if d.step >= 4 and d.website and not (d.build or {}).get("crawl_started"):
            crawl_needed = True
            d.build = {**(d.build or {}), "crawl_started": True}
    d.build = _build(d)
    flag_modified(d, "answers")
    flag_modified(d, "build")
    return d, crawl_needed


def _build(d: FunnelDraft) -> dict:
    """knowledge: done = the site was fetched (imported at verify), pending = known site not fetched yet,
    skipped = no site, demo data, or the fetch failed."""
    b = dict(d.build or {})
    if d.kind == "privat":
        return {k: v for k, v in b.items() if k == "created"} | privat_seed.plan(d.answers or {})
    if b.get("pages"):
        b["knowledge"] = "done"
    elif d.website and not b.get("knowledge_error"):
        b["knowledge"] = "pending"
    else:
        b["knowledge"] = "skipped"
    b["voice"] = "done"
    b["voice_key"] = estimates.voice_for(d.industry)
    b["hours"] = "done" if (d.company or {}).get("opening_hours_text") else "default"
    return b


def _number_ready(db: OrmSession) -> bool:
    from app.modules.sales import service as sales

    return sales.problem(db) is None


def out(db: OrmSession, d: FunnelDraft) -> dict:
    b = {k: v for k, v in (d.build or {}).items()
         if k not in ("pages", "created", "call", "knowledge_error", "crawl_started")}
    if d.kind == "erhverv":
        b["number"] = "done" if _number_ready(db) else "pending"
    return {"id": str(d.id), "kind": d.kind, "hook": d.hook, "industry": d.industry, "step": d.step,
            "answers": d.answers or {}, "company": d.company, "estimate": d.estimate, "build": b,
            "gated": d.gate is not None, "verified": d.user_id is not None,
            "phone_display": rules.phone_display((d.gate or {}).get("phone_e164")) if d.gate else None,
            "expires_at": d.expires_at.isoformat(), "next": NEXT[d.kind] if d.user_id else None}


# --------------------------------------------------------------------------- Places (Erhverv step 2)

def _places_client():
    from app.modules.privat import places as privat_places

    return privat_places.client()


def _hours_text(details: gp.Details) -> str | None:
    if details.opening_hours:
        return "; ".join(details.opening_hours)[:600]
    return None


def _weekly(periods: list[dict] | None) -> list[dict]:
    """Google periods (day 0 = Sunday) → the knowledge kind opening_hours' weekly rows."""
    days = ("sun", "mon", "tue", "wed", "thu", "fri", "sat")
    rows: dict[tuple[str, str], list[str]] = {}
    for p in periods or []:
        o, c = p.get("open") or {}, p.get("close")
        if not c:
            continue
        key = (f"{o.get('hour', 0):02d}:{o.get('minute', 0):02d}", f"{c.get('hour', 0):02d}:{c.get('minute', 0):02d}")
        day = days[o.get("day", 0) % 7]
        if key[0] < key[1] and day not in rows.setdefault(key, []):
            rows[key].append(day)
    order = {d: i for i, d in enumerate(("mon", "tue", "wed", "thu", "fri", "sat", "sun"))}
    return [{"days": sorted(ds, key=order.get), "open": o, "close": c} for (o, c), ds in rows.items()]


def _result(place: gp.Place, details: gp.Details, source: str) -> dict:
    from app.modules.privat import places as privat_places

    e164, kind = privat_places.classify_phone(details.phone_international or details.phone_national)
    return {"place_id": place.id, "name": place.name, "address": place.address or "",
            "postal_code": place.postal_code, "city": place.city,
            "phone_display": details.phone_national or rules.phone_display(e164) or "",
            "phone_e164": e164 if kind in ("business", "mobile") else None,
            "website": details.website, "opening_hours_text": _hours_text(details), "periods": details.periods,
            "open_now": privat_places.is_open(details.periods, rules.now()), "source": source}


def search_places(q: str, industry: str | None) -> list[dict]:
    """≤ 5 operational candidates for «Hvad hedder virksomheden?». Nothing is stored."""
    q = (q or "").strip()[:120]
    if len(q) < 2:
        raise ValidationFailed("Skriv virksomhedens navn", field_errors=[{"field": "q"}])
    c = _places_client()
    source = getattr(c, "source", "google")
    try:
        found, _ = c.search(text_query=q, included_type=None, center=PLACES_CENTER, radius_m=PLACES_RADIUS_M)
    except gp.PlacesError as e:
        raise ApiError("Søgningen virker ikke lige nu. Skriv navnet, og gå videre.", code="search_failed",
                       status_code=502) from e
    out = []
    for p in [x for x in found if x.business_status in (None, "OPERATIONAL")][:PLACES_RESULTS]:
        try:
            det = c.details(p.id)
        except gp.PlacesError:
            det = gp.Details()
        r = _result(p, det, source)
        out.append({k: r[k] for k in ("place_id", "name", "address", "phone_display", "website", "open_now", "source")})
    return out


def _lookup_company(db: OrmSession, d: FunnelDraft) -> None:
    """Step 2: the company behind the answer. A chosen place_id is looked up exactly; a bare name is searched and
    used only when the first hit's name matches the visitor's words. Done once per (name, place_id)."""
    a = d.answers or {}
    name, place_id = (a.get("company_name") or "").strip(), (a.get("place_id") or "").strip() or None
    current = d.company or {}
    if current.get("_lookup") == [name, place_id]:
        return
    c = _places_client()
    source = getattr(c, "source", "google")
    company: dict = {"name": name, "address": "", "phone_display": "", "website": None, "opening_hours_text": None,
                     "place_id": None, "source": None, "_lookup": [name, place_id]}
    try:
        found, _ = c.search(text_query=name or place_id, included_type=None, center=PLACES_CENTER,
                            radius_m=PLACES_RADIUS_M)
        hit = None
        if place_id:
            hit = next((p for p in found if p.id == place_id), None) or gp.Place(id=place_id, name=name)
        elif found and _names_match(name, found[0].name):
            hit = found[0]
        if hit is not None:
            det = c.details(hit.id)
            r = _result(hit, det, source)
            company |= {"name": hit.name or name, "address": r["address"], "phone_display": r["phone_display"],
                        "phone_e164": r["phone_e164"], "website": r["website"], "postal_code": r["postal_code"],
                        "city": r["city"], "opening_hours_text": r["opening_hours_text"], "periods": r["periods"],
                        "place_id": hit.id, "source": source}
    except gp.PlacesError as e:
        log.warning("funnel.places_failed", error=str(e))
    d.company = company
    d.place_id = company["place_id"]
    d.website = _crawlable(company.get("website"))
    d.build = {k: v for k, v in (d.build or {}).items() if k not in ("pages", "pages_count", "crawl_started", "knowledge_error")}
    flag_modified(d, "company")
    flag_modified(d, "build")


def _crawlable(website: str | None) -> str | None:
    """The site the import may fetch: a valid public address; demo data (.invalid) is never fetched."""
    if not website or ".invalid" in website:
        return None
    try:
        from app.modules.knowledge.importer import normalize_url

        return normalize_url(website)[:500]
    except ValidationFailed:
        return None


def _names_match(wanted: str, found: str) -> bool:
    w, f = wanted.lower().strip(), found.lower().strip()
    return bool(w) and (w in f or f in w)


# --------------------------------------------------------------------------- crawl (Erhverv step 4)

def crawl_draft(draft_id: uuid.UUID, fetcher=None) -> None:
    """Background job (own DB session): fetch the company's website now, keep the pages on the draft for the import
    that runs once there is a workspace. Never raises; a failure marks knowledge "skipped"."""
    from app.db import get_session_factory
    from app.modules.knowledge import importer

    db = get_session_factory()()
    try:
        d = db.scalar(select(FunnelDraft).where(FunnelDraft.id == draft_id).with_for_update())
        if d is None or not d.website or d.user_id is not None:
            return
        try:
            pages = importer.crawl(d.website, fetcher)
            d.build = {**(d.build or {}), "pages": pages, "pages_count": len(pages)}
        except ApiError as e:
            d.build = {**(d.build or {}), "knowledge_error": e.message}
        except Exception as e:  # noqa: BLE001 - the visitor only sees "skipped"
            d.build = {**(d.build or {}), "knowledge_error": f"{type(e).__name__}"}
        d.build = _build(d)
        flag_modified(d, "build")
        db.commit()
    finally:
        db.close()


# --------------------------------------------------------------------------- gate

def _code_hash(d: FunnelDraft, phone: str, code: str) -> str:
    key = (get_settings().secret_key or "").encode()
    return hmac.new(key, f"funnel:{d.id}:{phone}:{code}".encode(), hashlib.sha256).hexdigest()


def _sms_workspace(db: OrmSession):
    """The SMS goes out on Dialogbot's main account (privat/phone.py). sms.send wants a workspace for the sender
    lookup and the log: the sales workspace when configured, else a placeholder id that matches nothing."""
    from app.modules.sales import service as sales

    return sales.sales_workspace(db) or SimpleNamespace(id=uuid.UUID(int=0))


def gate(db: OrmSession, d: FunnelDraft, *, name: str, email: str, phone: str, consent: bool) -> dict:
    from app.modules.integrations.connectors import sms
    from app.modules.sales.service import danish_number

    if d.user_id is not None:
        raise Conflict("Kontoen er allerede oprettet", code="draft_verified")
    if not consent:
        raise ValidationFailed("Sæt kryds for at fortsætte", field_errors=[{"field": "consent", "message": "Påkrævet"}])
    name = re.sub(r"[<>{}\[\]`]", "", name or "").strip()[:200]
    if not name:
        raise ValidationFailed("Skriv dit navn", field_errors=[{"field": "name"}])
    e164 = danish_number(phone)  # Danish mobile/landline, 8 digits, never premium rate
    if d.kind == "privat":
        _check_privat_allowed(email)
    now = _now()
    if d.code_sent_at and now - d.code_sent_at < RESEND_AFTER:
        raise Conflict("Vent et øjeblik, før du beder om en ny kode", code="too_soon")
    code = f"{secrets.randbelow(1_000_000):06d}"
    d.gate = {"name": name, "email": email.strip()[:320], "phone_e164": e164, "consent_version": CONSENT_VERSION,
              "consent_text": CONSENT_TEXT_ERHVERV if d.kind == "erhverv" else CONSENT_TEXT_PRIVAT,
              "consent_at": now.isoformat()}
    d.code_hash, d.code_attempts, d.code_expires_at, d.code_sent_at = _code_hash(d, e164, code), 0, now + CODE_TTL, now
    d.step = max(d.step, 6)
    flag_modified(d, "gate")
    try:
        sms.send(db, _sms_workspace(db), sender=sms_code.SENDER, to=e164,
                 body=f"Din kode til Dialogbot er {code}. Den gælder i 10 minutter.", simulated=sms_code._simulated())
    except ApiError as e:
        raise ApiError("SMS kunne ikke sendes lige nu. Prøv igen om lidt.", code="sms_failed", status_code=502) from e
    except Exception as e:  # noqa: BLE001 - e.g. ActionError from the adapter
        raise ApiError("SMS kunne ikke sendes lige nu. Prøv igen om lidt.", code="sms_failed", status_code=502) from e
    return {"status": "code_sent", "phone_display": rules.phone_display(e164)}


def _check_privat_allowed(email: str) -> None:
    s = get_settings()
    if not s.privat_enabled:
        raise Forbidden("Dialogbot Privat er ikke åbnet endnu", code="privat_not_enabled")
    allowed = {e.strip().lower() for e in s.privat_allowed_emails.split(",") if e.strip()}
    if allowed and normalize_email(email) not in allowed:
        raise Forbidden("Dialogbot Privat er i lukket pilot. Din e-mail er ikke på listen endnu.",
                        code="privat_not_enabled")


# --------------------------------------------------------------------------- verify

def _check_code(db: OrmSession, d: FunnelDraft, code: str) -> None:
    now = _now()
    if d.gate is None or not d.code_hash or not d.code_expires_at or d.code_expires_at <= now:
        raise Conflict("Koden er udløbet. Bed om en ny.", code="code_expired")
    if d.code_attempts >= MAX_ATTEMPTS:
        raise Conflict("For mange forsøg. Bed om en ny kode.", code="too_many_attempts")
    d.code_attempts += 1
    if not hmac.compare_digest(d.code_hash, _code_hash(d, d.gate["phone_e164"], (code or "").strip())):
        db.commit()  # the attempt counts even though the request fails
        raise ValidationFailed("Koden passer ikke", field_errors=[{"field": "code"}],
                               extra={"attempts_left": MAX_ATTEMPTS - d.code_attempts})
    d.code_hash = d.code_expires_at = None
    d.code_attempts = 0


def _welcome(db: OrmSession, user: User, kind: str) -> None:
    """A new account has a random password: the welcome mail carries a «vælg adgangskode» link (the ordinary
    password-reset token, valid as long as a verification link)."""
    from app.modules.integrations import email_templates as tpl

    s = get_settings()
    raw = new_token()
    db.add(AuthToken(user_id=user.id, purpose="password_reset", token_hash=token_digest(raw),
                     expires_at=_now() + timedelta(hours=s.verification_ttl_hours)))
    link = f"{s.frontend_base_url}/password/reset?token={raw}"
    what = ("din digitale receptionist" if kind == "erhverv" else "din personlige assistent")
    mail = tpl.Email(subject="Velkommen til Dialogbot – vælg din adgangskode",
                     preheader="Din konto er oprettet. Vælg en adgangskode, så du kan logge ind igen.",
                     heading=f"Velkommen, {rules.first_name(user.display_name)}",
                     paragraphs=[f"Din konto hos Dialogbot er oprettet med {user.email}, og {what} er klar. Du er "
                                 "logget ind nu; vælg en adgangskode, så du også kan logge ind næste gang.",
                                 "Har du ikke oprettet en konto hos Dialogbot, kan du se bort fra denne mail – der "
                                 "sker ikke mere."],
                     button_label="Vælg adgangskode", button_url=link,
                     note=f"Linket virker i {s.verification_ttl_hours} timer.",
                     footer_reason="Du får denne e-mail, fordi der er oprettet en konto hos Dialogbot med din adresse.")
    enqueue(db, event_type="email.branded", dedupe_key=f"funnel-welcome:{user.id}",
            payload={"user_id": str(user.id), "to_email": user.email, "email": tpl.to_payload(mail)})


def _user_for(db: OrmSession, d: FunnelDraft, request_id: str | None) -> tuple[User, bool]:
    g = d.gate
    norm = normalize_email(g["email"])
    now = _now()
    user = db.scalar(select(User).where(User.email_normalized == norm).with_for_update())
    if user is not None:
        if not user.is_active:
            raise Forbidden("Kontoen er deaktiveret", code="user_inactive")
        if user.phone_verified_at is None:
            user.phone_verified_at = now
        record_audit(db, workspace_id=None, actor_user_id=user.id, action="user.funnel_login", object_type="user",
                     object_id=user.id, after={"draft_id": str(d.id), "kind": d.kind, "phone": g["phone_e164"],
                                               "proof": "sms_code"}, request_id=request_id)
        return user, False
    user = User(email=g["email"].strip(), email_normalized=norm, password_hash=hash_password(new_token()),
                display_name=g["name"], signup_intent="reception" if d.kind == "erhverv" else None,
                interface_language="da", phone_verified_at=now,
                signup_source=f"funnel:{d.kind}" + (f":{d.hook}" if d.hook else ""))
    db.add(user)
    db.flush()
    record_audit(db, workspace_id=None, actor_user_id=user.id, action="user.registered", object_type="user",
                 object_id=user.id, after={"email": norm, "signup_intent": user.signup_intent, "source": "funnel",
                                           "kind": d.kind, "proof": "sms_code"}, request_id=request_id)
    _welcome(db, user, d.kind)
    return user, True


def verify(db: OrmSession, d: FunnelDraft, *, code: str, user_agent: str | None,
           request_id: str | None) -> tuple[dict, list]:
    """Returns (response, background jobs [(fn, *args)]) – the router runs the jobs after the commit."""
    from app.modules.identity.router import user_out
    from app.modules.identity.service import start_session

    if d.user_id is not None:
        raise Conflict("Kontoen er allerede oprettet. Log ind.", code="draft_verified")
    _check_code(db, d, code)
    if d.kind == "privat":
        _check_privat_allowed(d.gate["email"])
    user, created = _user_for(db, d, request_id)
    now = _now()
    d.user_id = user.id
    d.gate = {**d.gate, "verified_at": now.isoformat()}
    d.step = MAX_STEP
    flag_modified(d, "gate")
    jobs: list = []
    if d.kind == "erhverv":
        jobs = _finish_erhverv(db, d, user, request_id)
    else:
        _finish_privat(db, d, user)
    raw = start_session(db, user, user_agent)
    record_audit(db, workspace_id=d.workspace_id, actor_user_id=user.id, action="funnel.verified",
                 object_type="funnel_draft", object_id=d.id,
                 after={"kind": d.kind, "new_user": created, "hook": d.hook, "utm": d.utm}, request_id=request_id)
    flag_modified(d, "build")
    return ({"status": "ok", "next": NEXT[d.kind], "session_token": raw, "access_token": raw, "token_type": "bearer",
             "user": user_out(user).model_dump(mode="json"), "new_user": created,
             "workspace_id": str(d.workspace_id) if d.workspace_id else None}, jobs)


# --------------------------------------------------------------------------- Erhverv: the workspace and the call

def _address_parts(address: str) -> tuple[str | None, str | None, str | None]:
    parts = [p.strip() for p in (address or "").split(",") if p.strip()]
    line = parts[0] if parts else None
    m = re.search(r"\b(\d{4})\s+([^,]+)", address or "")
    return line, (m.group(1) if m else None), (m.group(2).strip() if m else None)


def _category(industry: str | None) -> tuple[str, str, bool]:
    from app.modules.business.router import SUGGESTED_CATEGORIES

    suggested = dict(SUGGESTED_CATEGORIES)
    slug = {"klinik": "klinik-sundhed", "vaerksted": "bilvaerksted", "restaurant": "restaurant-catering"}.get(industry or "")
    if slug and slug in suggested:
        return slug, suggested[slug], False
    label = estimates.playbook_label(industry) or "Anden branche"
    s = re.sub(r"[^a-z0-9]+", "-", label.lower().replace("æ", "ae").replace("ø", "oe").replace("å", "aa")).strip("-")
    return s[:80] or "kategori", label, True


def _context(d: FunnelDraft) -> str:
    c, a = d.company or {}, d.answers or {}
    lines = []
    if c.get("address"):
        lines.append(f"Adresse: {c['address']}")
    if c.get("opening_hours_text"):
        lines.append(f"Åbningstider ifølge Google: {c['opening_hours_text']}")
    if c.get("website"):
        lines.append(f"Hjemmeside: {c['website']}")
    missed = {"lunch": "ved frokost", "after16": "efter kl. 16", "driving": "når de kører", "weekend": "i weekenden",
              "never_free": "stort set aldrig – ingen er fri til telefonen"}
    if a.get("missed"):
        lines.append("Hvornår de ikke tager telefonen (kontaktens svar): " + ", ".join(missed.get(m, m) for m in a["missed"]))
    if d.estimate:
        lines.append(f"Skøn vist i kvizzen: ca. {d.estimate['missed_per_week']} ubesvarede opkald om ugen ({d.estimate['source']})")
    wants = {"book": "booke tider", "message": "tage imod beskeder", "prices": "svare på priser"}
    if a.get("wants"):
        lines.append("Hvad receptionisten skal kunne (kontaktens valg): " + ", ".join(wants.get(w, w) for w in a["wants"]))
    return re.sub(r"[<>{}\[\]`]", "", "\n".join(lines))[:3500]


def _finish_erhverv(db: OrmSession, d: FunnelDraft, user: User, request_id: str | None) -> list:
    from app.modules.knowledge import importer
    from app.modules.sales import service as sales
    from app.modules.workspaces.service import create_workspace

    g, c, a = d.gate, d.company or {}, d.answers or {}
    company_name = (c.get("name") or a.get("company_name") or f"{rules.first_name(g['name'])}s virksomhed").strip()[:200]
    ws = create_workspace(db, user=user, name=company_name, product_intent="reception", request_id=request_id,
                          require_verified=False)
    d.workspace_id = ws.id
    # Profile (trin 1 på /opsaetning: navn, beskrivelse og telefon → «udfyldt»)
    p = db.get(BusinessProfile, ws.id)
    line, postal, city = _address_parts(c.get("address") or "")
    desc = estimates.INDUSTRIES.get(d.industry or "", {}).get("description", "")
    if c.get("address"):
        desc = f"{desc} {company_name} ligger på {c['address']}.".strip()
    p.description = (desc or f"{company_name}.")[:2000]
    p.website_url = d.website
    p.manual_setup = not d.website
    p.address_line, p.postal_code, p.city = (line or None), (c.get("postal_code") or postal), (c.get("city") or city)
    p.phone = (c.get("phone_display") or None)
    p.version += 1
    slug, label, custom = _category(d.industry)
    db.add(WorkspaceCategory(workspace_id=ws.id, slug=slug, label=label, is_custom=custom, is_primary=True, position=0))
    db.add(WorkspaceVoiceSettings(workspace_id=ws.id, standard_voice=estimates.voice_for(d.industry)))
    # Opening hours from Google as an UNAPPROVED draft the owner confirms
    weekly = _weekly(c.get("periods"))
    if weekly:
        from app.modules.knowledge.service import _key

        item = KnowledgeItem(workspace_id=ws.id, kind="opening_hours", key=_key("opening_hours", "Åbningstider"))
        db.add(item)
        db.flush()
        db.add(KnowledgeVersion(item_id=item.id, workspace_id=ws.id, version_no=1, status="draft", title="Åbningstider",
                                content={"weekly": weekly, "closed_note": ""}, source_type="import",
                                source_ref="Google Places (fra kvizzen)", created_by=user.id))
    db.flush()
    build = dict(d.build or {})
    # The demo call: Peter rings the number the visitor just proved, knowing the company
    try:
        call = sales.request_web(db, phone=g["phone_e164"], name=g["name"], company=company_name,
                                 industry=estimates.script_key(d.industry), context=_context(d))
        if call is None:
            build["call"] = {"status": "skipped", "code": "do_not_call", "message": "Nummeret ringes ikke op"}
        else:
            d.demo_call_id = call.id
            build["call"] = {"status": call.status, "code": None, "message": call.error}
    except ApiError as e:
        build["call"] = {"status": "unavailable", "code": e.code, "message": e.message}
    # The crawled pages become knowledge DRAFTS in the new workspace (importer.run marks them unapproved)
    jobs: list = []
    pages = build.pop("pages", None)
    if pages and d.website:
        try:
            imp, is_new = importer.start(db, ws, user.id, d.website)  # commits
            d.crawl_job_ref = str(imp.id)
            build["knowledge_import"] = "running"
            if is_new:
                jobs.append((importer.run, imp.id, None, pages))
        except ApiError as e:  # AI not configured: the pages are dropped, honestly
            build["knowledge"], build["knowledge_error"] = "skipped", e.message
    elif build.get("knowledge") == "done":
        build["knowledge"] = "skipped"
    d.build = build
    return jobs


# --------------------------------------------------------------------------- Privat: the account and the tasks

def _finish_privat(db: OrmSession, d: FunnelDraft, user: User) -> None:
    from app.core.auth import Principal
    from app.modules.privat import deps

    profile, created = deps.ensure_account(db, user, signup_source="funnel:privat" + (f":{d.hook}" if d.hook else ""))
    if profile.phone_verified_at is None:
        profile.phone_e164, profile.phone_verified_at = d.gate["phone_e164"], _now()
    d.workspace_id = profile.workspace_id
    ctx = deps._ctx(db, Principal(user=user, session=None), profile)
    made = privat_seed.create(db, ctx, d.answers or {})
    d.build = {**(d.build or {}), "created": made | {"account_created": created}}


# --------------------------------------------------------------------------- reveal

def reveal(db: OrmSession, d: FunnelDraft, user: User) -> dict:
    if d.user_id is None or d.user_id != user.id:
        raise NotFound("Vi kunne ikke finde dine svar")
    call = None
    if d.demo_call_id:
        dc = db.get(DemoCall, d.demo_call_id)
        if dc is not None:
            dur = db.scalar(select(Call.duration_seconds).where(Call.provider_call_id == dc.provider_call_id)) \
                if dc.provider_call_id else None
            call = {"status": dc.status, "outcome": dc.outcome, "summary": dc.summary or "", "duration_seconds": dur,
                    "error": dc.error}
    problem = (d.build or {}).get("call") or {}
    knowledge = None
    if d.kind == "erhverv":
        from app.models import SourceImport
        from app.modules.knowledge.importer import import_out

        imp = db.get(SourceImport, uuid.UUID(d.crawl_job_ref)) if d.crawl_job_ref else None
        knowledge = {"status": (d.build or {}).get("knowledge"), "import": import_out(imp) if imp else None}
    return {"kind": d.kind, "call": call,
            "call_problem": problem.get("message") if call is None and problem else None,
            "workspace_id": str(d.workspace_id) if d.workspace_id else None, "next": NEXT[d.kind],
            "knowledge": knowledge, "company": {k: v for k, v in (d.company or {}).items() if not k.startswith("_")
                                               and k != "periods"} if d.kind == "erhverv" else None,
            "created": (d.build or {}).get("created") if d.kind == "privat" else None}


# --------------------------------------------------------------------------- worker

def purge_expired(db: OrmSession) -> int:
    """Drafts nobody verified, seven days after they were made – with whatever gate data they carried."""
    r = db.execute(delete(FunnelDraft).where(FunnelDraft.user_id.is_(None), FunnelDraft.expires_at <= _now()))
    db.commit()
    return r.rowcount or 0


def workspace_of(db: OrmSession, d: FunnelDraft) -> Workspace | None:
    return db.get(Workspace, d.workspace_id) if d.workspace_id else None
