"""Sales profile and personal script for Peter (`peter-sales-v1`).

Profile: from source facts with confidence high/medium only – at most 3 facts (each pointing to its source fact),
at most 2 hypotheses (always questions), the service Dialogbot would start with and why. Nothing from the website
goes into a prompt as raw text: facts are short structured values, cleaned of markup.

Script: a fixed JSON body (schema below) plus the rendered runtime instruction. The instruction text is
data/peter-sales-v1.txt, unchanged except for the fields; a field without a value removes its whole sentence – never
a placeholder read aloud. Validation before approval: no placeholders, every amount is one of the list prices in
billing/prices.py, every integration status comes from the register, facts point to stored source facts, features
are approved knowledge (or the documented fallback), booking is only mentioned when the integration is AKTIV.
"""
from __future__ import annotations

import re
import uuid
from functools import lru_cache
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session as OrmSession

from app.core.audit import record_audit
from app.core.errors import Conflict, NotFound
from app.models import SalesCompany, SalesProfile, SalesScript, SalesSourceFact
from app.modules.billing import prices
from app.modules.sales import companies, integrations, script
from app.modules.sales.research import is_instruction

SCRIPT_VERSION = "peter-sales-v1"
TERMS_VERSION = "prisliste-2026-10b"  # 10b: campaign minutes + included inbound minutes (PR #91)  # the list prices in billing/prices.py; offers get their own version in phase 3
TEMPLATE = Path(__file__).parent / "data" / f"{SCRIPT_VERSION}.txt"
FACT_FIELDS = ("service", "booking_system", "customer_type", "service_area", "opening_hours")
FACT_SENTENCE = {"service": "tilbyder {v}", "booking_system": "bruger {v} til booking",
                 "customer_type": "henvender sig til {v}", "service_area": "dækker {v}",
                 "opening_hours": "har åbent {v}"}
WORK = {"haandvaerk": "en opgave ude hos en kunde", "klinik": "en behandling", "skoenhed": "en kunde i stolen",
        "auto": "en bil på liften", "raadgivning": "et møde", "butik": "kunderne i butikken",
        "restaurant": "gæsterne"}
# Fallback product claims when the sales workspace has no approved knowledge yet: the lines of script.FEATURES.
FALLBACK_FEATURES = {
    "telefon": "tager telefonen på dansk, når I er optaget eller har lukket",
    "viden": "svarer kun ud fra den viden, I selv har godkendt",
    "besked": "sender jer en kort opsummering med navn, nummer og behov",
    "booking": "kan booke, flytte og aflyse tider i jeres kalender",
    "chat": "svarer i chatten på jeres hjemmeside med samme viden",
    "nummer": "kan tage opkaldene via viderestilling, så I beholder jeres nummer",
}
ALLOWED_AMOUNTS = {prices.kr(m) for m in (prices.SUBSCRIPTION_MONTHLY_NET_MINOR, prices.CAMPAIGN_CALL_NET_MINOR,
                                          prices.CAMPAIGN_MINUTE_NET_MINOR, prices.INBOUND_EXTRA_MINUTE_NET_MINOR,
                                          prices.SPECIALIST_SETUP_NET_MINOR)}
AMOUNT_RE = re.compile(r"(\d[\d.]*(?:,\d+)?)\s*(?:kr\b|kr\.|kroner)", re.I)
PLACEHOLDER_RE = re.compile(r"\{\{|\}\}|\[|\]")


# --------------------------------------------------------------------------- profile


def _facts(db: OrmSession, company: SalesCompany) -> list[SalesSourceFact]:
    return list(db.scalars(select(SalesSourceFact).where(SalesSourceFact.company_id == company.id,
                                                         SalesSourceFact.confidence.in_(("high", "medium")))
                           .order_by(SalesSourceFact.confidence, SalesSourceFact.fetched_at.desc())))


def _sales_revision(db: OrmSession) -> int | None:
    from app.modules.sales import service

    ws = service.sales_workspace(db)
    return ws.knowledge_revision if ws else None


def build_profile(db: OrmSession, company: SalesCompany, *, user_id: uuid.UUID | None,
                  request_id: str | None = None) -> SalesProfile:
    facts = _facts(db, company)
    chosen: list[dict] = []
    for field in FACT_FIELDS:  # one fact per kind first, so the three are varied
        f = next((x for x in facts if x.field == field and not is_instruction(x.value)), None)
        if f and len(chosen) < 3:
            v = companies.clean_text(f.value, 120 if field != "opening_hours" else 160)
            chosen.append({"field": field, "text": FACT_SENTENCE[field].format(v=v), "value": v,
                           "source_fact_id": str(f.id), "source": _source_label(f)})
    key = company.industry_key if company.industry_key in script.INDUSTRIES else None
    work = WORK.get(key or "", "andet arbejde")
    hypotheses = [{"question": f"Hvad sker der med dem, der ringer, når I er optaget af {work}?"},
                  {"question": "Ringer kunderne også, når I har lukket?"}]
    ind = script.INDUSTRIES.get(key) if key else None
    relevant = "telefonpasning, der tager de opkald, I ikke selv når, og sender jer en kort besked"
    why = (f"Typisk for branchen ({ind['label']}): {ind['pain']}" if ind else
           "Virksomheder, der har travlt med kunderne, mister ofte opkald, de ikke når at tage.")
    n = (db.scalar(select(func.max(SalesProfile.version)).where(SalesProfile.company_id == company.id)) or 0) + 1
    p = SalesProfile(company_id=company.id, version=n, facts=chosen, hypotheses=hypotheses[:2],
                     relevant_service=relevant, why_relevant=why, knowledge_revision=_sales_revision(db),
                     created_by=user_id)
    db.add(p)
    company.research_status = "profiled"
    db.flush()
    record_audit(db, workspace_id=None, actor_user_id=user_id, action="sales.profile_created", object_type="sales_profile",
                 object_id=p.id, after={"company_id": str(company.id), "version": n, "facts": len(chosen)},
                 request_id=request_id)
    return p


def _source_label(f: SalesSourceFact) -> str:
    if f.url_or_ref.startswith("google_place:"):
        return "Google"
    if f.url_or_ref.startswith(("import", "cvr:")):
        return "import" if f.url_or_ref.startswith("import") else "CVR"
    return f.url_or_ref


# --------------------------------------------------------------------------- script


def _features(db: OrmSession, booking_active: bool) -> tuple[list[str], list[str], str]:
    """(feature keys, allowed keys, source). Keys of approved public/customer_docs knowledge, else the fallback."""
    from app.modules.knowledge.service import active_knowledge
    from app.modules.sales import service

    ws = service.sales_workspace(db)
    items = active_knowledge(db, ws.id, ("public", "customer_docs")) if ws else []
    if items:
        allowed = [i["item_id"] for i in items]
        return allowed[:6], allowed, "knowledge"
    keys = ["telefon", "viden", "besked"] + (["booking"] if booking_active else [])
    return keys, list(FALLBACK_FEATURES), "fallback"


def build_body(db: OrmSession, company: SalesCompany, profile: SalesProfile) -> dict:
    booking_fact = next((f for f in profile.facts if f["field"] == "booking_system"), None)
    booking = integrations.lookup(db, booking_fact["value"]) if booking_fact else None
    booking_active = bool(booking and booking["status"] == "AKTIV")
    features, _allowed, feature_source = _features(db, booking_active)
    service_fact = next((f for f in profile.facts if f["field"] == "service"), None)
    key = company.industry_key if company.industry_key in script.INDUSTRIES else None
    work = WORK.get(key or "", "andet arbejde")
    feature_phrases = [FALLBACK_FEATURES["telefon"], FALLBACK_FEATURES["besked"]]
    if booking_active:
        feature_phrases.append(FALLBACK_FEATURES["booking"])
    setup = (f"gør-det-selv-opsætning, der er med i abonnementet, eller specialist-opsætning til "
             f"{prices.kr(prices.SPECIALIST_SETUP_NET_MINOR)} kroner én gang ekskl. moms")
    return {
        "opening": {"greeting": "Hej, det er Peter, AI-assistent hos Dialogbot.", "who": "den ansvarlige for telefonen",
                    "reason": "telefon, kundehenvendelser og booking",
                    "verified_service": f"tilbyder {service_fact['value']}" if service_fact else None},
        "discovery": [f"Når I er optaget af {work}, hvad sker der så med dem, der ringer eller skriver?",
                      *[h["question"] for h in profile.hypotheses]],
        "work": work,
        "partial_accepts": [
            {"no": 1, "question": "Har jeg forstået rigtigt, hvad I især vil have hjælp til?", "on_no": "Spørg, hvad det så er."},
            {"no": 2, "question": "Ville det gøre en mærkbar forskel, hvis henvendelserne blev håndteret?", "on_no": "Afslut pænt."},
            {"no": 3, "question": "Er det den form for hjælp, du havde i tankerne?", "on_no": "Spørg, hvad der mangler."},
            {"no": 4, "question": "Passer koblingen til jeres system ind i hverdagen?", "on_no": "Tilbyd at en kollega afklarer."},
            {"no": 5, "question": "Er det en investering, der giver mening for jer?", "on_no": "Afklar én gang: pris, funktion eller timing."},
        ],
        "demo": {"offer_line": f"Vil du høre et kort eksempel på, hvordan det kunne lyde for {company.display_name}?",
                 "example_service": service_fact["value"] if service_fact else None},
        "features": features, "feature_source": feature_source,
        "features_sentence": " og ".join(feature_phrases[:2]) if not booking_active else
        f"{feature_phrases[0]}, {feature_phrases[2]}",
        "handoff_sentence": "en kort besked med navn, nummer og hvad det drejer sig om, så I kan ringe tilbage",
        "customer_problem": "at få taget de opkald, I ikke selv når",
        "main_result": "at ingen henvendelser går tabt, mens I arbejder",
        "scope": profile.relevant_service,
        "limits": ["Ingen rabat, frist eller gratis periode.", "Ingen løfter om omsætning eller besparelse.",
                   "Kalenderbooking nævnes kun, når integrationen er AKTIV."],
        "integration_status": {booking["system"]: booking["status"]} if booking else {},
        "integration": ({"system": booking["system"], "label": booking["label"], "status": booking["status"]}
                        if booking else None),
        "offer": {"monthly_net_minor": prices.SUBSCRIPTION_MONTHLY_NET_MINOR, "setup_kind": "diy",
                  "setup_net_minor": prices.SPECIALIST_SETUP_NET_MINOR,
                  "campaign_call_net_minor": prices.CAMPAIGN_CALL_NET_MINOR,
                  "campaign_minute_net_minor": prices.CAMPAIGN_MINUTE_NET_MINOR,
                  "inbound_included_minutes": prices.INBOUND_INCLUDED_MINUTES, "terms_version": TERMS_VERSION,
                  "package_text": "Dialogbot-receptionisten", "setup_text": setup, "terms": "uden binding"},
        "close": {"order_question": f"Skal vi sætte Dialogbot op til {company.display_name} på de vilkår?",
                  "on_demo": "Tilbyd en demonstration med højst to tider.", "on_partner": "Tilbyd at sende oplægget efter anmodning.",
                  "on_no": "Tak for tiden og afslut."},
        "contact_channel": "jeres e-mail" if company.public_email else "SMS" if company.main_phone_e164 else None,
        "objections": ["robot", "receptionist", "onlinebooking", "mister ikke opkald", "pris", "send noget", "tid",
                       "fejl", "nummer", "integration", "opstart", "samtaler", "persondata", "systemet", "kilde",
                       "ring ikke igen", "sletning"],
        "facts": profile.facts, "hypotheses": profile.hypotheses,
        "sources": sorted({f["source"] for f in profile.facts}),
        "versions": {"profile": profile.version, "knowledge_revision": profile.knowledge_revision, "offer": None,
                     "script": SCRIPT_VERSION},
    }


@lru_cache
def template() -> str:
    """The template unwrapped: hard-wrapped lines joined into paragraphs, so a sentence is one line."""
    lines = TEMPLATE.read_text(encoding="utf-8").rstrip("\n").split("\n")
    out: list[str] = []
    for ln in lines:
        new_para = (not out or not ln.strip() or not out[-1].strip() or re.match(r"^\d\. ", ln)
                    or ln.startswith(("{{#", "Hypoteser", "Indvendinger:", "Åbning:", "Afslutning:"))
                    or out[-1].startswith("{{#"))
        if new_para:
            out.append(ln)
        else:
            out[-1] = f"{out[-1]} {ln.strip()}"
    return "\n".join(out)


_BOUNDARY = re.compile(r'(?<=[.?!])"?\s+|\n|\s·\s')


def _drop_sentence(text: str, pos: int) -> str:
    starts = [m.end() for m in _BOUNDARY.finditer(text, 0, pos)]
    left = starts[-1] if starts else 0
    m = _BOUNDARY.search(text, pos)
    right = m.end() if m else len(text)
    if m and m.group(0) == "\n":
        right = m.start()
    return text[:left] + text[right:]


def render(body: dict, company: SalesCompany) -> str:
    offer = body.get("offer") or {}
    integ = body.get("integration")
    values: dict[str, str | None] = {
        "contact.name_or_role": body["opening"]["who"],
        "company.display_name": company.display_name,
        "company.industry_text": company.industry_text or "ukendt branche",
        "company.city": company.city or "ukendt by",
        "basis.sentence": None,          # contact basis arrives in phase 2: the sentence is left out
        "basis.source_sentence": None,
        "opening.verified_service": body["opening"].get("verified_service"),
        "discovery.work": body.get("work"),
        "customer_problem": body.get("customer_problem"),
        "features.sentence": body.get("features_sentence"),
        "handoff.sentence": body.get("handoff_sentence"),
        "confirmed_system": integ["label"] if integ and integ["status"] == "AKTIV" else None,
        "integration.sentence": integrations.sentence(integ) if integ and integ["status"] == "AKTIV" else None,
        "offer.package_text": offer.get("package_text"),
        "offer.monthly": prices.kr(offer["monthly_net_minor"]) if offer.get("monthly_net_minor") else None,
        "offer.setup_text": offer.get("setup_text"),
        "offer.terms": offer.get("terms"),
        "main_result": body.get("main_result"),
        "scope": body.get("scope"),
        "contact.channel": body.get("contact_channel"),
    }
    text = template()
    facts = "\n".join(f"- {f['text']} (kilde: {f['source']})" for f in body.get("facts") or []) \
        or "- (ingen – sig intet konstaterende om virksomheden)"
    hyps = "\n".join(f"- {h['question']}" for h in body.get("hypotheses") or []) or "- (ingen)"
    text = re.sub(r"\{\{#facts\}\}.*?\{\{/facts\}\}", lambda _m: facts, text, flags=re.S)
    text = re.sub(r"\{\{#hypotheses\}\}.*?\{\{/hypotheses\}\}", lambda _m: "\n" + hyps + "\n", text, flags=re.S)
    for _ in range(100):
        m = re.search(r"\{\{([a-z_.]+)\}\}", text)
        if not m:
            break
        v = values.get(m.group(1))
        if v:
            text = text[:m.start()] + companies.clean_text(v, 300) + text[m.end():]
        else:
            text = _drop_sentence(text, m.start())
    return re.sub(r"\n[ \t]+", "\n", re.sub(r"[ \t]+\n", "\n", text)).strip()


def validate(db: OrmSession, company: SalesCompany, body: dict, rendered: str) -> dict:
    errors: list[str] = []
    warnings: list[str] = []
    if PLACEHOLDER_RE.search(rendered):
        errors.append("Manuskriptet indeholder en pladsholder ({{…}} eller […]).")
    for amount in AMOUNT_RE.findall(rendered):
        if amount not in ALLOWED_AMOUNTS:
            errors.append(f"Beløbet {amount} kr. findes ikke i prislisten.")
    offer = body.get("offer")
    if offer:
        if offer.get("monthly_net_minor") != prices.SUBSCRIPTION_MONTHLY_NET_MINOR \
                or offer.get("setup_net_minor") not in (0, prices.SPECIALIST_SETUP_NET_MINOR) \
                or offer.get("campaign_call_net_minor") != prices.CAMPAIGN_CALL_NET_MINOR \
                or offer.get("campaign_minute_net_minor", prices.CAMPAIGN_MINUTE_NET_MINOR) != prices.CAMPAIGN_MINUTE_NET_MINOR:
            errors.append("Tilbuddets beløb svarer ikke til prislisten i billing/prices.py.")
    for system, status in (body.get("integration_status") or {}).items():
        if status not in integrations.STATUSES:
            errors.append(f"Ukendt integrationsstatus for {system}: {status}.")
            continue
        current = integrations.lookup(db, (body.get("integration") or {}).get("label") or system)
        if current["status"] != status:
            errors.append(f"Integrationsstatus for {system} er ændret ({status} → {current['status']}).")
    booking_active = any(s == "AKTIV" for s in (body.get("integration_status") or {}).values())
    if re.search(r"\bbook", body.get("features_sentence") or "", re.I) and not booking_active:
        errors.append("Kalenderbooking nævnes, men integrationen er ikke AKTIV.")
    fact_ids = [f.get("source_fact_id") for f in body.get("facts") or []]
    if len(fact_ids) > 3 or len(body.get("hypotheses") or []) > 2:
        errors.append("Højst 3 fakta og 2 hypoteser.")
    for fid, f in zip(fact_ids, body.get("facts") or [], strict=True):
        row = db.get(SalesSourceFact, uuid.UUID(fid)) if fid else None
        if row is None or row.company_id != company.id or row.confidence not in ("high", "medium"):
            errors.append(f"Faktum uden gyldig kilde: {f.get('text', '')[:60]}")
        elif is_instruction(f.get("text", "")):
            errors.append("Et faktum ligner en instruktion og må ikke bruges.")
    for h in body.get("hypotheses") or []:
        if not str(h.get("question", "")).rstrip().endswith("?"):
            errors.append("En hypotese skal være et spørgsmål.")
    _keys, allowed, source = _features(db, booking_active)
    unknown = [k for k in body.get("features") or [] if k not in allowed]
    if unknown:
        errors.append("Funktioner uden godkendt viden: " + ", ".join(map(str, unknown)))
    if source == "fallback":
        warnings.append("Salgsarbejdsrummet har ingen godkendt viden – funktionerne er reservelisten (FEATURES). "
                        "Kør scripts.seed_sales_knowledge og godkend posterne.")
    warnings.append("Intet kontaktgrundlag registreret (fase 2) – sætningen om grundlag er udeladt.")
    if company.advertising_protected is None:
        warnings.append("Reklamebeskyttelse er ukendt (intet CVR-opslag).")
    if company.advertising_protected is True:
        errors.append("Virksomheden er reklamebeskyttet.")
    return {"ok": not errors, "errors": errors, "warnings": warnings, "checked_at": companies.now().isoformat()}


def build_script(db: OrmSession, company: SalesCompany, profile: SalesProfile, *, user_id: uuid.UUID | None,
                 request_id: str | None = None) -> SalesScript:
    body = build_body(db, company, profile)
    rendered = render(body, company)
    validation = validate(db, company, body, rendered)
    n = (db.scalar(select(func.max(SalesScript.version)).where(SalesScript.company_id == company.id)) or 0) + 1
    s = SalesScript(company_id=company.id, profile_id=profile.id, version=n, script_version=SCRIPT_VERSION, body=body,
                    rendered_prompt=rendered, validation=validation, status="draft", created_by=user_id)
    db.add(s)
    db.flush()
    record_audit(db, workspace_id=None, actor_user_id=user_id, action="sales.script_created", object_type="sales_script",
                 object_id=s.id, after={"company_id": str(company.id), "version": n, "ok": validation["ok"]},
                 request_id=request_id)
    return s


def approve(db: OrmSession, s: SalesScript, *, user_id: uuid.UUID, request_id: str | None = None) -> SalesScript:
    if s.status == "approved":
        return s
    if s.status != "draft":
        raise Conflict("Kun et udkast kan godkendes", code="script_not_draft")
    company = db.get(SalesCompany, s.company_id)
    s.validation = validate(db, company, s.body, s.rendered_prompt)  # re-check: prices/integrations may have changed
    if not s.validation["ok"]:
        raise Conflict("Manuskriptet har valideringsfejl og kan ikke godkendes", code="script_invalid",
                       extra={"errors": s.validation["errors"]})
    for old in db.scalars(select(SalesScript).where(SalesScript.company_id == s.company_id,
                                                    SalesScript.status == "approved")):
        old.status = "superseded"
    s.status, s.approved_by, s.approved_at = "approved", user_id, companies.now()
    record_audit(db, workspace_id=None, actor_user_id=user_id, action="sales.script_approved", object_type="sales_script",
                 object_id=s.id, after={"company_id": str(s.company_id), "version": s.version}, request_id=request_id)
    return s


def get_script(db: OrmSession, script_id: uuid.UUID) -> SalesScript:
    s = db.get(SalesScript, script_id)
    if s is None:
        raise NotFound("Manuskriptet findes ikke")
    return s


def profile_out(p: SalesProfile) -> dict:
    return {"id": str(p.id), "version": p.version, "facts": p.facts, "hypotheses": p.hypotheses,
            "relevant_service": p.relevant_service, "why_relevant": p.why_relevant,
            "knowledge_revision": p.knowledge_revision, "created_at": p.created_at.isoformat() if p.created_at else None}


def script_out(s: SalesScript) -> dict:
    return {"id": str(s.id), "profile_id": str(s.profile_id), "version": s.version, "script_version": s.script_version,
            "status": s.status, "body": s.body, "rendered_prompt": s.rendered_prompt, "validation": s.validation,
            "approved_at": s.approved_at.isoformat() if s.approved_at else None,
            "created_at": s.created_at.isoformat() if s.created_at else None}
