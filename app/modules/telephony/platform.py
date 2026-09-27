"""Platform-managed telephony: the customer keeps their number at their own carrier and forwards it to a
destination number that Dialogbot provisions and operates. The customer never logs in to Twilio or Vapi.

Customer status (derived, never "active" just because a global key exists):
  not_started      Ikke sat op            – no business number yet
  awaiting_info    Afventer oplysninger   – verification, company documents or price agreement missing
  provisioning     Forbindelse klargøres  – Dialogbot is buying/importing the destination (or waiting for review)
  ready_for_test   Klar til prøveopkald   – destination works; forward and test
  test_failed      Test fejlede           – last test failed (reason shown)
  active           Aktiv                  – test passed and the customer activated
  paused           Sat på pause           – customer paused; callers hear a short message

Routing is strict: a webhook is answered only for a number Dialogbot mapped to exactly one workspace (by the
provider's number id, cross-checked against E.164 and our Vapi org). Unknown numbers are never routed to anyone.
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session as OrmSession

from app.config import get_settings
from app.core.audit import record_audit
from app.core.errors import ApiError, Conflict, ValidationFailed
from app.models import (
    Call,
    PhoneNumber,
    ReceptionAgreement,
    TelephonyAccount,
    TelephonyCost,
    TelephonyJob,
    TelephonySetup,
    TelephonyTest,
    Workspace,
)
from app.modules.telephony import providers as prov

LABELS = {"not_started": "Ikke sat op", "awaiting_info": "Afventer oplysninger", "provisioning": "Forbindelse klargøres",
          "ready_for_test": "Klar til prøveopkald", "test_failed": "Test fejlede", "active": "Aktiv",
          "paused": "Sat på pause"}
TEST_MINUTES = 15
VERIFY_MINUTES = 10
VERIFY_MAX_PER_HOUR = 3
VERIFY_MAX_ATTEMPTS = 5
JOB_LEASE = timedelta(minutes=5)
JOB_BACKOFF = (1, 5, 15, 60, 240)  # minutes


def _now() -> datetime:
    return datetime.now(UTC)


def _hash(code: str, ws_id: uuid.UUID) -> str:
    key = (get_settings().secret_key or "").encode()
    return hmac.new(key, f"{ws_id}:{code}".encode(), hashlib.sha256).hexdigest()


def setup_for(db: OrmSession, ws_id: uuid.UUID, *, lock: bool = False) -> TelephonySetup:
    q = select(TelephonySetup).where(TelephonySetup.workspace_id == ws_id)
    s = db.scalar(q.with_for_update() if lock else q)
    if s is None:
        s = TelephonySetup(workspace_id=ws_id, verify_sent=[])
        db.add(s)
        db.flush()
    return s


def documents_required() -> bool:
    return get_settings().telephony_number_type == "local"  # Danish local numbers need a regulatory bundle


def agreement(db: OrmSession, ws_id: uuid.UUID) -> ReceptionAgreement | None:
    return db.scalar(select(ReceptionAgreement).where(ReceptionAgreement.workspace_id == ws_id)
                     .order_by(ReceptionAgreement.version.desc()).limit(1))


def destination(db: OrmSession, s: TelephonySetup) -> PhoneNumber | None:
    n = db.get(PhoneNumber, s.destination_number_id) if s.destination_number_id else None
    return n if n is not None and n.workspace_id == s.workspace_id else None


def job_for(db: OrmSession, ws_id: uuid.UUID) -> TelephonyJob | None:
    return db.scalar(select(TelephonyJob).where(TelephonyJob.workspace_id == ws_id,
                                                TelephonyJob.kind == "provision_destination")
                     .order_by(TelephonyJob.created_at.desc()).limit(1))


def last_test(db: OrmSession, s: TelephonySetup) -> TelephonyTest | None:
    return db.get(TelephonyTest, s.last_test_id) if s.last_test_id else None


def missing_info(db: OrmSession, s: TelephonySetup) -> list[dict]:
    out = []
    if not s.business_number:
        return [{"key": "business_number", "text": "Angiv virksomhedens nuværende telefonnummer."}]
    if s.business_number_verified_at is None:
        out.append({"key": "verify", "text": "Bekræft nummeret med koden fra kontrolopkaldet."})
    if documents_required() and s.documents_status in ("missing", "rejected"):
        out.append({"key": "documents", "text": "Upload virksomhedsregistrering (CVR-udskrift) med dansk adresse, "
                                                "så vi må tildele et dansk nummer."})
    if agreement(db, s.workspace_id) is None:
        out.append({"key": "agreement", "text": "Vælg jeres prisaftale under Indstillinger → Aftale."})
    return out


def status(db: OrmSession, ws_id: uuid.UUID) -> dict:
    s = setup_for(db, ws_id)
    dest = destination(db, s)
    job = job_for(db, ws_id)
    test = last_test(db, s)
    missing = missing_info(db, s)
    if s.state == "active":
        code = "active"
    elif s.state == "paused":
        code = "paused"
    elif not s.business_number:
        code = "not_started"
    elif dest is not None and dest.status == "active":
        code = "test_failed" if test is not None and test.status in ("failed", "expired") else "ready_for_test"
    elif missing:
        code = "awaiting_info"
    elif job is not None and job.status in ("pending", "running", "waiting", "failed"):
        code = "provisioning"
    else:
        code = "awaiting_info"
    nxt = _next_step(code, missing, job, test, s)
    return {"code": code, "label": LABELS[code], "next_step": nxt, "missing": missing,
            "platform_ready": prov.providers() is not None}


def _next_step(code: str, missing: list, job: TelephonyJob | None, test: TelephonyTest | None,
               s: TelephonySetup) -> str:
    if code == "not_started":
        return "Angiv virksomhedens nuværende telefonnummer for at komme i gang."
    if code == "awaiting_info":
        return missing[0]["text"] if missing else "Tryk på 'Forbind telefonen', så klargør Dialogbot jeres nummer."
    if code == "provisioning":
        if job is not None and job.waiting_for == "documents_review":
            return ("Dialogbot gennemgår jeres virksomhedsdokumentation hos teleleverandøren. Det kan tage op til nogle "
                    "hverdage. I får besked, når nummeret er klar.")
        if job is not None and job.waiting_for == "platform":
            return "Dialogbots telefonforbindelse er ikke sat op endnu. Vi kontakter jer, når den er klar."
        if job is not None and job.status == "failed":
            return "Klargøringen gik i stå. Dialogbot er underrettet og følger op. I behøver ikke gøre noget."
        return "Dialogbot klargør jeres Dialogbot-nummer. Det tager normalt kun få minutter."
    if code == "ready_for_test":
        return "Viderestil jeres nummer til jeres Dialogbot-nummer, og ring et prøveopkald."
    if code == "test_failed":
        return (test.result.get("reason") if test and test.result.get("reason") else "Prøv prøveopkaldet igen.")
    if code == "paused":
        return "Opkald bliver ikke besvaret af assistenten. Aktivér igen, når I er klar."
    return "Assistenten tager telefonen, når opkald viderestilles til jeres Dialogbot-nummer."


# --------------------------------------------------------------------------- business number and verification

def set_business_number(db: OrmSession, ws_id: uuid.UUID, *, e164: str, subscription_type: str, carrier: str,
                        forwarding_mode: str, wants_new_number: bool) -> TelephonySetup:
    from app.modules.telephony.vapi import E164, normalize_e164

    s = setup_for(db, ws_id, lock=True)
    num = normalize_e164(e164)
    if not E164.match(num):
        raise ValidationFailed("Skriv nummeret med landekode, fx +45 70 12 34 56", field_errors=[{"field": "e164"}])
    ours = db.scalar(select(PhoneNumber.id).where(PhoneNumber.e164 == num))
    if ours is not None:
        raise ValidationFailed("Det er et Dialogbot-nummer. Angiv jeres eget nummer hos teleselskabet.",
                               field_errors=[{"field": "e164"}])
    if s.state in ("active",) and s.business_number and num != s.business_number:
        raise Conflict("Sæt telefonen på pause, før I skifter nummer", code="telephony_active")
    if num != s.business_number:
        s.business_number, s.business_number_verified_at, s.business_number_verified_by = num, None, None
        s.verify_code_hash, s.verify_attempts = None, 0
    s.subscription_type, s.carrier, s.forwarding_mode = subscription_type, carrier.strip()[:80], forwarding_mode
    s.wants_new_number = wants_new_number
    s.version += 1
    return s


def start_verification(db: OrmSession, ws: Workspace) -> dict:
    """Call the business number and read a 6-digit code aloud (from a platform number). Proves the customer can
    answer calls to it. Rate limited; the code is stored hashed and expires."""
    s = setup_for(db, ws.id, lock=True)
    if not s.business_number:
        raise ValidationFailed("Angiv nummeret først")
    now = _now()
    recent = [t for t in (s.verify_sent or []) if datetime.fromisoformat(t) > now - timedelta(hours=1)]
    if len(recent) >= VERIFY_MAX_PER_HOUR:
        raise ApiError("For mange kontrolopkald. Prøv igen om lidt.", code="verify_rate_limited", status_code=429)
    p = prov.providers()
    settings = get_settings()
    if p is None or not settings.telephony_verify_number_id:
        raise ApiError("Kontrolopkald er ikke tilgængeligt endnu. Dialogbot bekræfter nummeret manuelt og kontakter jer.",
                       code="verify_unavailable", status_code=503)
    code = f"{secrets.randbelow(10**6):06d}"
    spoken = " ".join(code)
    _twilio, vapi = p
    call_id = vapi.call({
        "phoneNumberId": settings.telephony_verify_number_id,
        "customer": {"number": s.business_number},
        "assistant": {"firstMessage": f"Hej. Dette er Dialogbot. Din kode er {spoken}. Jeg gentager: {spoken}. Farvel.",
                      "endCallMessage": "Farvel.", "maxDurationSeconds": 45,
                      "model": {"provider": settings.vapi_model_provider, "model": settings.vapi_model or settings.ai_model_id,
                                "messages": [{"role": "system", "content": "Sig kun koden og farvel. Svar ikke på spørgsmål."}]},
                      "metadata": {"purpose": "verification", "workspace_id": str(ws.id)}},
        "metadata": {"purpose": "verification", "workspace_id": str(ws.id)}})
    s.verify_code_hash = _hash(code, ws.id)
    s.verify_expires_at = now + timedelta(minutes=VERIFY_MINUTES)
    s.verify_attempts = 0
    s.verify_sent = [*recent, now.isoformat()]
    return {"call_id": call_id, "expires_at": s.verify_expires_at.isoformat()}


def confirm_verification(db: OrmSession, ws_id: uuid.UUID, code: str) -> TelephonySetup:
    s = setup_for(db, ws_id, lock=True)
    if not s.verify_code_hash or not s.verify_expires_at or s.verify_expires_at < _now():
        raise ValidationFailed("Koden er udløbet. Bestil et nyt kontrolopkald.", field_errors=[{"field": "code"}])
    if s.verify_attempts >= VERIFY_MAX_ATTEMPTS:
        raise ValidationFailed("For mange forkerte forsøg. Bestil et nyt kontrolopkald.", field_errors=[{"field": "code"}])
    s.verify_attempts += 1
    if not hmac.compare_digest(_hash(code.strip(), ws_id), s.verify_code_hash):
        raise ValidationFailed("Koden passer ikke", field_errors=[{"field": "code"}])
    s.business_number_verified_at, s.business_number_verified_by = _now(), "code_call"
    s.verify_code_hash = None
    return s


# --------------------------------------------------------------------------- provisioning (idempotent job)

def request_connection(db: OrmSession, ws_id: uuid.UUID) -> TelephonyJob:
    """Start (or resume) provisioning the workspace's destination. Nothing billable happens before the business
    number is verified, documentation is in (when required) and a price agreement is accepted."""
    s = setup_for(db, ws_id, lock=True)
    missing = [m for m in missing_info(db, s) if m["key"] != "documents" or s.documents_status == "rejected"]
    if missing:
        raise Conflict(missing[0]["text"], code="telephony_missing_info", extra={"missing": missing})
    if destination(db, s) is not None:
        raise Conflict("Jeres Dialogbot-nummer er allerede klar", code="telephony_already_provisioned")
    job = job_for(db, ws_id)
    if job is not None and job.status != "succeeded":
        if job.status == "failed":  # an explicit retry resets the backoff but keeps the progress
            job.status, job.attempts, job.next_attempt_at = "pending", 0, _now()
        return job
    job = TelephonyJob(workspace_id=ws_id, kind="provision_destination", status="pending", step="start",
                       idempotency_key=f"dialogbot-{ws_id}", state={}, next_attempt_at=_now())
    db.add(job)
    agr = agreement(db, ws_id)
    s.agreement_version = agr.version if agr else None
    s.state = "provisioning"
    db.flush()
    return job


def _name(ws_id: uuid.UUID) -> str:
    return f"dialogbot-{ws_id}"


def run_job(db: OrmSession, job: TelephonyJob) -> TelephonyJob:
    """Advance one provisioning job as far as possible. Safe to call again after any failure or timeout: each
    step first looks for what a previous attempt may already have created (by idempotency name)."""
    s = setup_for(db, job.workspace_id, lock=True)
    p = prov.providers()
    job.attempts += 1
    job.locked_until = _now() + JOB_LEASE
    if p is None:
        job.status, job.waiting_for, job.next_attempt_at = "waiting", "platform", _now() + timedelta(hours=1)
        job.last_error = "Platformtelefoni er ikke konfigureret (TELEPHONY_PROVIDER / Twilio / Vapi)."
        return job
    twilio, vapi = p
    settings = get_settings()
    name = job.idempotency_key or _name(job.workspace_id)
    job.status = "running"
    try:
        # 1. technical sub-account for this workspace
        acct = db.scalar(select(TelephonyAccount).where(TelephonyAccount.workspace_id == job.workspace_id,
                                                        TelephonyAccount.provider == "twilio",
                                                        TelephonyAccount.kind == "subaccount"))
        if acct is None:
            sid = twilio.find_subaccount(name) or twilio.create_subaccount(name)
            acct = TelephonyAccount(provider="twilio", kind="subaccount", workspace_id=job.workspace_id,
                                    external_id=sid, friendly_name=name)
            db.add(acct)
            db.flush()
        job.step, job.state = "subaccount", {**job.state, "subaccount_sid": acct.external_id}
        # 2. documentation approved (Danish local numbers)
        if documents_required() and not (s.documents_status == "approved" and s.regulatory_bundle_sid):
            job.status, job.waiting_for = "waiting", "documents_review"
            job.next_attempt_at = _now() + timedelta(minutes=30)
            return job
        # 3. the number: adopt one a previous attempt bought, else buy exactly one
        num = twilio.find_number(acct.external_id, name)
        if num is None:
            if job.state.get("purchase_started"):  # bought before a timeout but not listed yet: wait, never re-buy
                job.status, job.waiting_for = "waiting", "reconcile_purchase"
                job.next_attempt_at = _now() + timedelta(minutes=2)
                if job.attempts < 6:
                    return job
                job.status, job.last_error = "failed", "Købet kunne ikke genfindes hos Twilio. Tjek underkontoen manuelt."
                return job
            options = twilio.available(acct.external_id, settings.telephony_number_country, settings.telephony_number_type)
            if not options:
                raise prov.ProviderError("Ingen ledige danske numre lige nu", retryable=True)
            job.state = {**job.state, "purchase_started": True, "purchase_candidate": options[0]}
            db.flush()
            try:
                num = twilio.buy(acct.external_id, options[0], name, s.regulatory_bundle_sid, s.regulatory_address_sid)
            except prov.ProviderError as e:
                if not e.timeout:  # definitively refused: nothing was bought, a later attempt may buy
                    job.state = {k: v for k, v in job.state.items() if k != "purchase_started"}
                raise
            db.add(TelephonyCost(workspace_id=job.workspace_id, provider="twilio", kind="number_purchase",
                                 reference=num.sid, amount_micros=None, details={"e164": num.e164}))
        job.step, job.state = "number", {**job.state, "number_sid": num.sid, "e164": num.e164}
        row = db.scalar(select(PhoneNumber).where(PhoneNumber.provider_sid == num.sid))
        if row is None:
            row = PhoneNumber(workspace_id=job.workspace_id, e164=num.e164, provider="vapi", source="platform",
                              status="provisioning", telephony_account_id=acct.id, provider_sid=num.sid,
                              label="Dialogbot-nummer")
            db.add(row)
            db.flush()
        if row.workspace_id != job.workspace_id:
            raise ValidationFailed("Nummeret tilhører et andet arbejdsrum")  # never re-home a number
        # 4. import into Vapi with our webhook (adopt an earlier import of the same number)
        if not row.provider_number_id:
            vid = vapi.find_number(num.e164)
            if vid is None:
                vid = vapi.import_twilio(e164=num.e164, account_sid=acct.external_id,
                                         auth_token=twilio.subaccount_token(acct.external_id), name=name,
                                         server_url=f"{settings.public_base_url}/api/v1/webhooks/vapi",
                                         server_secret=settings.vapi_server_secret or "fake")
            row.provider_number_id = vid
        row.status = "active"
        s.destination_number_id = row.id
        if s.state in ("draft", "provisioning"):
            s.state = "provisioned"
        job.step, job.status, job.waiting_for, job.last_error, job.next_attempt_at = "done", "succeeded", "", "", None
        return job
    except prov.ProviderError as e:
        job.last_error = e.message[:500]
        delay = JOB_BACKOFF[min(job.attempts - 1, len(JOB_BACKOFF) - 1)]
        if e.retryable or e.timeout:
            job.status, job.next_attempt_at = "pending", _now() + timedelta(minutes=delay)
        else:
            job.status = "failed"
        return job
    finally:
        job.locked_until = None


def run_due_jobs(db: OrmSession, now: datetime | None = None, limit: int = 10) -> int:
    now = now or _now()
    q = (select(TelephonyJob).where(TelephonyJob.status.in_(("pending", "waiting", "running")),
                                    (TelephonyJob.next_attempt_at.is_(None)) | (TelephonyJob.next_attempt_at <= now),
                                    (TelephonyJob.locked_until.is_(None)) | (TelephonyJob.locked_until < now))
         .order_by(TelephonyJob.created_at).limit(limit).with_for_update(skip_locked=True))
    n = 0
    for job in db.scalars(q).all():
        run_job(db, job)
        db.commit()
        n += 1
    return n


# --------------------------------------------------------------------------- routing, tests, activation

def route(db: OrmSession, message: dict) -> PhoneNumber | None:
    """Strict mapping of a provider webhook to one of OUR numbers. None = do not answer for anyone."""
    from app.modules.telephony.vapi import _dig, normalize_e164

    org = get_settings().vapi_org_id
    msg_org = _dig(message, "call", "orgId") or _dig(message, "phoneNumber", "orgId")
    if org and msg_org and str(msg_org) != org:
        return None
    pid = _dig(message, "call", "phoneNumberId") or _dig(message, "phoneNumber", "id")
    num = _dig(message, "phoneNumber", "number") or _dig(message, "call", "phoneNumber", "number")
    row = None
    if pid:
        row = db.scalar(select(PhoneNumber).where(PhoneNumber.provider_number_id == str(pid)))
        if row is None:
            return None  # an id we do not know is never matched by number instead
        if num and normalize_e164(str(num)) != row.e164:
            return None  # id and number disagree: reject rather than guess
    elif num:
        row = db.scalar(select(PhoneNumber).where(PhoneNumber.e164 == normalize_e164(str(num))))
    if row is None or row.status != "active" or not row.active:
        return None
    return row


def call_mode(db: OrmSession, number: PhoneNumber, message: dict) -> str:
    """normal | test | not_active | loop"""
    from app.modules.telephony.vapi import _dig, normalize_e164

    s = setup_for(db, number.workspace_id)
    caller = _dig(message, "call", "customer", "number")
    caller = normalize_e164(str(caller)) if caller else None
    ours = set(db.scalars(select(PhoneNumber.e164).where(PhoneNumber.status == "active")))
    if caller and caller in ours:
        return "loop"  # a Dialogbot number calling a Dialogbot number is a forwarding loop
    t = last_test(db, s)
    if t is not None and t.status == "waiting" and t.expires_at > _now() and t.destination_number_id == number.id:
        return "test"
    if number.source == "legacy_customer" and s.state == "active":
        return "normal"
    return "normal" if s.state == "active" else "not_active"


def start_test(db: OrmSession, ws_id: uuid.UUID, user_id: uuid.UUID, *, called_business_number: bool,
               simulated: bool = False) -> TelephonyTest:
    s = setup_for(db, ws_id, lock=True)
    dest = destination(db, s)
    if dest is None or dest.status != "active":
        raise Conflict("Jeres Dialogbot-nummer er ikke klar endnu", code="telephony_not_ready")
    t = TelephonyTest(workspace_id=ws_id, destination_number_id=dest.id, called_business_number=called_business_number,
                      simulated=simulated, started_by=user_id, expires_at=_now() + timedelta(minutes=TEST_MINUTES),
                      result={})
    db.add(t)
    db.flush()
    s.last_test_id = t.id
    return t


def mark_test_call(db: OrmSession, number: PhoneNumber, provider_call_id: str | None) -> None:
    s = setup_for(db, number.workspace_id)
    t = last_test(db, s)
    if t is not None and t.status == "waiting" and provider_call_id:
        t.provider_call_id = provider_call_id[:100]


def evaluate_test(db: OrmSession, call: Call, message: dict) -> None:
    """After a call's end-of-call report: pass or fail the open test for that workspace."""
    from app.modules.telephony.vapi import _dig

    s = setup_for(db, call.workspace_id)
    t = last_test(db, s)
    if t is None or t.status != "waiting":
        return
    now = _now()
    pid = _dig(message, "call", "phoneNumberId")
    dest = destination(db, s)
    result = {"reached_number": call.to_number, "workspace_ok": call.workspace_id == t.workspace_id,
              "destination_ok": bool(dest and (pid is None or str(pid) == dest.provider_number_id)),
              "conversation_stored": call.conversation_id is not None, "duration_seconds": call.duration_seconds,
              "loop": False, "simulated": t.simulated}
    reason = None
    if t.expires_at < now:
        t.status, reason = "expired", "Prøveopkaldet kom ikke inden for 15 minutter. Start et nyt prøveopkald."
    elif not result["destination_ok"]:
        reason = "Opkaldet ramte ikke jeres Dialogbot-nummer. Tjek viderestillingen."
    elif not result["conversation_stored"]:
        reason = "Opkaldet blev ikke gemt i indbakken. Prøv igen, eller kontakt Dialogbot."
    elif (call.duration_seconds or 0) < 3:
        reason = "Opkaldet var for kort til at blive besvaret. Ring igen og vent på assistentens hilsen."
    t.result = {**result, **({"reason": reason} if reason else {})}
    t.call_id, t.finished_at = call.id, now
    if t.status == "waiting":
        t.status = "failed" if reason else "passed"


def expire_tests(db: OrmSession) -> int:
    n = 0
    for t in db.scalars(select(TelephonyTest).where(TelephonyTest.status == "waiting",
                                                    TelephonyTest.expires_at < _now())):
        t.status, t.finished_at = "expired", _now()
        t.result = {**(t.result or {}), "reason": "Der kom intet opkald inden for 15 minutter. Tjek viderestillingen, "
                                                  "og start et nyt prøveopkald."}
        n += 1
    return n


def activate(db: OrmSession, ws_id: uuid.UUID, user_id: uuid.UUID) -> TelephonySetup:
    s = setup_for(db, ws_id, lock=True)
    t = last_test(db, s)
    if destination(db, s) is None:
        raise Conflict("Jeres Dialogbot-nummer er ikke klar endnu", code="telephony_not_ready")
    if t is None or t.status != "passed":
        raise Conflict("Aktivér først efter et bestået prøveopkald", code="telephony_test_required")
    if agreement(db, ws_id) is None:
        raise Conflict("Vælg jeres prisaftale først", code="telephony_agreement_required")
    s.state, s.activated_at, s.activated_by = "active", _now(), user_id
    return s


def pause(db: OrmSession, ws_id: uuid.UUID) -> TelephonySetup:
    s = setup_for(db, ws_id, lock=True)
    if s.state != "active":
        raise Conflict("Telefonen er ikke aktiv", code="telephony_not_active")
    s.state = "paused"
    return s


def record_call_cost(db: OrmSession, call: Call, message: dict) -> None:
    """Internal provider cost of a call (Vapi reports `cost` in USD). Never part of the customer's invoice."""
    from app.modules.telephony.vapi import _dig

    cost = _dig(message, "call", "cost") if _dig(message, "call", "cost") is not None else message.get("cost")
    if cost is None or not call.provider_call_id:
        return
    try:
        micros = int(round(float(cost) * 1_000_000))
    except (TypeError, ValueError):
        return
    if db.scalar(select(TelephonyCost.id).where(TelephonyCost.provider == "vapi", TelephonyCost.kind == "call",
                                                TelephonyCost.reference == call.provider_call_id)):
        return
    db.add(TelephonyCost(workspace_id=call.workspace_id, provider="vapi", kind="call", reference=call.provider_call_id,
                         amount_micros=micros, currency="USD",
                         details={"breakdown": message.get("costBreakdown") or _dig(message, "call", "costBreakdown") or {}}))


def audit(db: OrmSession, ws_id: uuid.UUID, user_id: uuid.UUID | None, action: str, after: dict,
          request_id: str | None = None) -> None:
    record_audit(db, workspace_id=ws_id, actor_user_id=user_id, action=action, object_type="telephony_setup",
                 object_id=ws_id, after=after, request_id=request_id)
