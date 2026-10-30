"""Find companies by industry and area with Google Places (New), as a background job the worker runs.

A job is a plan: sub-areas × queries. A query is one Google type (`includedType`, strict) or one free-text term. Each
step asks Text Search for up to 3 pages of 20 (Google never returns more than 60 per query, which is why larger areas
are split into sub-areas), keeps what is new and relevant, and only then pays for Place Details (website, phone,
opening hours) for those companies. Every request is counted against SALES_SEARCH_DAILY_REQUEST_CAP; the job pauses
with a reason when the cap is reached and can be resumed. Cancel stops between requests.

Duplicates: a known place id is updated, not added. A new place that shares CVR, domain + postal code or phone with
another company is stored and marked "mulig dublet"; the same domain at another address is a "mulig afdeling".
Namesakes with another postal code stay separate. Companies of existing customers are marked and skipped.
"""
from __future__ import annotations

import csv
import io
import math
import uuid
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from pathlib import Path
from zoneinfo import ZoneInfo

import structlog
from sqlalchemy import or_, select
from sqlalchemy.orm import Session as OrmSession

from app.config import get_settings
from app.core.errors import ApiError, Conflict, NotFound, ValidationFailed
from app.models import SalesCompany, SalesSearchJob
from app.modules.sales import channel, companies, places

log = structlog.get_logger("dialogbot.sales.search")
TZ = ZoneInfo("Europe/Copenhagen")
EXTRACTOR = "google-places-v1"
PLACE_RADIUS_M = 5_000      # a named place (town/district) is a 5 km circle
POSTAL_RADIUS_M = 3_000     # one circle per postal code centre
GRID_CELL_KM = 3.0          # a radius over 5 km is covered by cells of at least 3 km
MAX_GRID_CELLS = 60
LEASE = timedelta(minutes=3)
STEP_TIME_LIMIT = 40.0      # seconds of work per worker tick, so other schedules keep running
POSTCODES = Path(__file__).parent / "data" / "postnumre.csv"


def _now() -> datetime:
    return datetime.now(UTC)


# --------------------------------------------------------------------------- areas


@lru_cache
def postcodes() -> dict[str, dict]:
    lines = [ln for ln in POSTCODES.read_text(encoding="utf-8").splitlines() if not ln.startswith("#")]
    return {r["postnr"]: {"code": r["postnr"], "name": r["navn"], "municipality": r["kommune"],
                          "municipality_code": r["kommunekode"], "lat": float(r["lat"]), "lng": float(r["lng"])}
            for r in csv.DictReader(lines)}


def _place_from_postcodes(text: str) -> dict | None:
    t = " ".join(text.lower().split())
    hits = [p for p in postcodes().values() if p["name"].lower() == t] \
        or [p for p in postcodes().values() if p["name"].lower().startswith(t + " ")]
    if not hits:
        return None
    return {"label": text.strip(), "lat": sum(p["lat"] for p in hits) / len(hits),
            "lng": sum(p["lng"] for p in hits) / len(hits), "radius_m": PLACE_RADIUS_M,
            "postal_codes": sorted({p["code"] for p in hits})}


def _grid(lat: float, lng: float, km: float) -> list[dict]:
    """Cover a circle with smaller, overlapping circles (each Google query returns at most 60), at most
    MAX_GRID_CELLS of them: a wide radius gets larger cells rather than hundreds of requests."""
    cell = GRID_CELL_KM
    while True:
        step = cell * 1.5
        n = int(math.ceil(km / step))
        out = []
        for i in range(-n, n + 1):
            for j in range(-n, n + 1):
                dy, dx = i * step, j * step
                if math.hypot(dx, dy) > km + cell / 2:
                    continue
                out.append({"label": f"{lat:.3f},{lng:.3f} ({i:+d},{j:+d})", "lat": lat + dy / 111.0,
                            "lng": lng + dx / (111.0 * math.cos(math.radians(lat))), "radius_m": int(cell * 1000)})
        if len(out) <= MAX_GRID_CELLS:
            return out
        cell *= 1.25


def plan_areas(geo_kind: str, geo: dict, client) -> tuple[list[dict], int]:
    """Sub-areas for a job and the number of Places requests spent finding them (geocoding)."""
    if geo_kind == "place":
        text = str(geo.get("text") or "").strip()
        if not text:
            raise ValidationFailed("Skriv et område, fx Aarhus C", field_errors=[{"field": "geo.text"}])
        if (hit := _place_from_postcodes(text)) is not None:
            return [hit], 0
        point = client.geocode(f"{text}, Danmark")
        if point is None:
            raise ValidationFailed(f"Området \"{text}\" kunne ikke findes. Brug et bynavn, et postnummer eller en "
                                   "radius.", field_errors=[{"field": "geo.text"}])
        return [{"label": text, "lat": point[0], "lng": point[1], "radius_m": PLACE_RADIUS_M}], 1
    if geo_kind == "postal_codes":
        codes = [str(c).strip() for c in geo.get("postal_codes") or [] if str(c).strip()]
        unknown = [c for c in codes if c not in postcodes()]
        if not codes or unknown:
            raise ValidationFailed(f"Ukendte postnumre: {', '.join(unknown) or 'ingen angivet'}",
                                   field_errors=[{"field": "geo.postal_codes"}])
        return [{"label": f"{c} {postcodes()[c]['name']}", "lat": postcodes()[c]["lat"], "lng": postcodes()[c]["lng"],
                 "radius_m": POSTAL_RADIUS_M, "postal_codes": [c]} for c in dict.fromkeys(codes)][:100], 0
    if geo_kind == "radius":
        try:
            lat, lng, km = float(geo["lat"]), float(geo["lng"]), float(geo["km"])
        except (KeyError, TypeError, ValueError) as e:
            raise ValidationFailed("Radius kræver lat, lng og km", field_errors=[{"field": "geo"}]) from e
        if not (54.0 <= lat <= 58.0 and 7.5 <= lng <= 15.5):
            raise ValidationFailed("Midtpunktet skal ligge i Danmark", field_errors=[{"field": "geo"}])
        if not 0.5 <= km <= 50:
            raise ValidationFailed("Radius skal være mellem 0,5 og 50 km", field_errors=[{"field": "geo.km"}])
        if km <= 5:
            return [{"label": f"{km:g} km omkring {lat:.3f},{lng:.3f}", "lat": lat, "lng": lng,
                     "radius_m": int(km * 1000)}], 0
        return _grid(lat, lng, km), 0
    raise ValidationFailed("Ukendt geografi", field_errors=[{"field": "geo_kind"}])


# --------------------------------------------------------------------------- queries

TYPE_TERMS = {
    "plumber": "VVS", "electrician": "elektriker", "roofing_contractor": "tagdækker", "painter": "maler",
    "general_contractor": "entreprenør", "dentist": "tandlæge", "physiotherapist": "fysioterapeut",
    "chiropractor": "kiropraktor", "doctor": "læge", "veterinary_care": "dyrlæge", "hair_salon": "frisør",
    "barber_shop": "barber", "beauty_salon": "skønhedssalon", "nail_salon": "neglesalon", "massage": "massage",
    "car_repair": "autoværksted", "car_dealer": "bilforhandler", "car_wash": "bilvask", "lawyer": "advokat",
    "accounting": "revisor", "real_estate_agency": "ejendomsmægler", "insurance_agency": "forsikring",
    "store": "butik", "florist": "blomsterhandler", "moving_company": "flyttefirma", "locksmith": "låsesmed",
    "restaurant": "restaurant", "cafe": "café", "hotel": "hotel", "bakery": "bager",
}


def plan_queries(db: OrmSession, industry_keys: list[str], google_types: list[str], keywords: list[str]) -> list[dict]:
    known = channel.industries(db)
    unknown = [k for k in industry_keys if k not in known]
    if unknown:
        raise ValidationFailed(f"Ukendte brancher: {', '.join(unknown)}", field_errors=[{"field": "industry_keys"}])
    out: list[dict] = []
    seen: set[tuple] = set()

    def add(q: dict) -> None:
        k = (q["type"], q["term"].lower())
        if k not in seen:
            seen.add(k)
            out.append(q)

    for key in industry_keys:
        for t in known[key]["google_types"]:
            add({"type": t, "term": TYPE_TERMS.get(t, known[key]["label"]), "industry_key": key})
    for t in google_types:
        t = t.strip()
        if t:
            add({"type": t, "term": TYPE_TERMS.get(t, t.replace("_", " ")),
                 "industry_key": channel.industry_for_types(db, [t])})
    for kw in keywords:
        kw = companies.clean_text(kw, 60)
        if kw:
            add({"type": None, "term": kw, "industry_key": industry_keys[0] if len(industry_keys) == 1 else None})
    if not out:
        raise ValidationFailed("Vælg mindst én branche, Google-type eller ét søgeord",
                               field_errors=[{"field": "industry_keys"}])
    return out


def estimate(n_steps: int, max_results: int) -> dict:
    """Upper bound: every step uses all 3 pages; Place Details for at most max_results companies."""
    search = n_steps * places.MAX_PAGES
    details = max_results
    return {"steps": n_steps, "search_requests_max": search, "details_requests_max": details,
            "cost_minor_max": search * places.SEARCH_REQUEST_COST_MINOR + details * places.DETAILS_REQUEST_COST_MINOR,
            "price_note": "Overslag ud fra analysedokumentets listepriser (Pro $32, Enterprise $35 pr. 1.000); "
                          "Googles gratis månedskvote er ikke fratrukket."}


# --------------------------------------------------------------------------- jobs


def requests_today(db: OrmSession, now: datetime | None = None) -> int:
    """Places requests counted today (Copenhagen day) across all jobs, plus refreshes made by this process."""
    now = now or _now()
    day = now.astimezone(TZ).date().isoformat()
    budgets = db.scalars(select(SalesSearchJob.budget).where(SalesSearchJob.created_at >= now - timedelta(days=30))).all()
    return sum(int((b or {}).get("by_day", {}).get(day, 0)) for b in budgets) + _refresh_used.get(day, 0)


_refresh_used: dict[str, int] = {}


def create_job(db: OrmSession, *, user_id: uuid.UUID | None, industry_keys: list[str], google_types: list[str],
               keywords: list[str], geo_kind: str, geo: dict, max_results: int,
               exclude_existing_customers: bool = True, client=None) -> SalesSearchJob:
    s = get_settings()
    if not 1 <= max_results <= s.sales_search_max_results:
        raise ValidationFailed(f"Højst {s.sales_search_max_results} virksomheder pr. søgning",
                               field_errors=[{"field": "max_results"}])
    client = client or places.client()
    queries = plan_queries(db, industry_keys, google_types, keywords)
    try:
        areas, geo_requests = plan_areas(geo_kind, geo, client)
    except places.PlacesError as e:
        raise ApiError(f"Området kunne ikke slås op: {e}", code="places_unavailable", status_code=502) from e
    steps = [{"area": a, "query": q} for a in areas for q in queries]
    day = _now().astimezone(TZ).date().isoformat()
    job = SalesSearchJob(created_by=user_id, industry_keys=industry_keys, google_types=google_types, keywords=keywords,
                         geo_kind=geo_kind, geo=geo, max_results=max_results,
                         exclude_existing_customers=exclude_existing_customers, source=client.source, status="queued",
                         plan=steps, cursor=0,
                         progress={"examined": 0, "found": 0, "skipped": 0, "incomplete": 0, "duplicates": 0,
                                   "requests_used": geo_requests, "details_used": 0, "estimated_cost_minor":
                                   geo_requests * places.SEARCH_REQUEST_COST_MINOR, "reasons": {}, "steps_done": 0,
                                   "steps": len(steps)},
                         budget={"estimate": estimate(len(steps), max_results), "day_cap": s.sales_search_daily_request_cap,
                                 "by_day": {day: geo_requests} if geo_requests else {}})
    db.add(job)
    db.flush()
    return job


def cancel(db: OrmSession, job: SalesSearchJob) -> SalesSearchJob:
    if job.status in ("done", "failed", "cancelled"):
        raise Conflict(f"Søgningen er allerede {job.status}", code="search_finished")
    job.status, job.finished_at, job.lease_expires_at = "cancelled", _now(), None
    return job


def resume(db: OrmSession, job: SalesSearchJob) -> SalesSearchJob:
    if job.status not in ("paused", "failed"):
        raise Conflict("Kun en sat på pause eller fejlet søgning kan genoptages", code="search_not_paused")
    job.status, job.error, job.finished_at, job.lease_expires_at = "queued", None, None, None
    return job


def _bump(job: SalesSearchJob, key: str, n: int = 1, reason: str | None = None) -> None:
    p = dict(job.progress or {})
    p[key] = int(p.get(key, 0)) + n
    if reason:
        reasons = dict(p.get("reasons") or {})
        reasons[reason] = int(reasons.get(reason, 0)) + n
        p["reasons"] = reasons
    job.progress = p


def _count_request(job: SalesSearchJob, kind: str) -> None:
    day = _now().astimezone(TZ).date().isoformat()
    b = dict(job.budget or {})
    by_day = dict(b.get("by_day") or {})
    by_day[day] = int(by_day.get(day, 0)) + 1
    b["by_day"] = by_day
    job.budget = b
    _bump(job, "requests_used" if kind == "search" else "details_used")
    _bump(job, "estimated_cost_minor", places.SEARCH_REQUEST_COST_MINOR if kind == "search"
          else places.DETAILS_REQUEST_COST_MINOR)


class _CapReached(Exception):
    pass


def _spend(db: OrmSession, job: SalesSearchJob, kind: str) -> None:
    if requests_today(db) >= get_settings().sales_search_daily_request_cap:
        raise _CapReached
    _count_request(job, kind)


def _relevance(place: places.Place, query: dict) -> tuple[int, list[str]]:
    score, reasons = 0, []
    if query["type"] and place.primary_type == query["type"]:
        score, reasons = score + 3, reasons + [f"Primær Google-type {query['type']}"]
    elif query["type"] and query["type"] in place.types:
        score, reasons = score + 2, reasons + [f"Google-type {query['type']}"]
    if query["term"].lower() in place.name.lower():
        score, reasons = score + 1, reasons + [f"Navnet indeholder \"{query['term']}\""]
    if place.business_status == "OPERATIONAL":
        score, reasons = score + 1, reasons + ["I drift ifølge Google"]
    return score, reasons


def _store_place(db: OrmSession, job: SalesSearchJob, place: places.Place, query: dict, client) -> str:
    """Returns what happened: new | known | incomplete | skipped_<reason> | irrelevant."""
    if not place.id or not place.name:
        return "irrelevant"
    existing = db.scalar(select(SalesCompany).where(SalesCompany.google_place_id == place.id))
    if existing is not None:
        _apply_google(existing, place)
        existing.last_search_job_id = job.id
        return "known"
    score, reasons = _relevance(place, query)
    if query["type"] is None and score == 0 and place.business_status == "OPERATIONAL":
        score, reasons = 1, ["Fundet på søgeordet"]
    if score == 0:
        return "irrelevant"
    c = SalesCompany(source=job.source, google_place_id=place.id, display_name=companies.clean_text(place.name, 200),
                     relevance_score=score, relevance_reasons=reasons, last_search_job_id=job.id,
                     industry_key=query.get("industry_key") or channel.industry_for_types(db, place.types),
                     research_status="found")
    _apply_google(c, place)
    c.industry_text = (channel.industries(db).get(c.industry_key) or {}).get("label") if c.industry_key else None
    db.add(c)
    db.flush()
    ref = f"google_place:{place.id}"
    for field, value in (("name", place.name), ("address", place.address), ("google_types", ", ".join(place.types)),
                         ("business_status", place.business_status)):
        if value:
            companies.add_fact(db, c, field=field, value=value, ref=ref, extractor=EXTRACTOR, confidence="high")
    if place.business_status and place.business_status != "OPERATIONAL":
        c.research_status = "incomplete"
        companies.compute_quality(db, c)
        return "incomplete"
    _spend(db, job, "details")
    try:
        d = client.details(place.id)
    except places.PlacesError as e:
        c.research_status, c.research_error = "incomplete", str(e)[:300]
        companies.compute_quality(db, c)
        return "incomplete"
    apply_details(db, c, d)
    c.existing_customer_workspace_id = companies.existing_customer(db, domain=c.domain, cvr=c.cvr)
    companies.flag_duplicates(db, c)
    companies.compute_quality(db, c)
    if c.existing_customer_workspace_id and job.exclude_existing_customers:
        return "skipped_existing_customer"
    if c.possible_duplicate_of:
        return "duplicate"
    return "new"


def _apply_google(c: SalesCompany, p: places.Place) -> None:
    c.google_fetched_at = _now()
    c.google_types, c.google_primary_type = p.types, p.primary_type
    c.google_business_status, c.google_maps_uri = p.business_status, p.maps_uri
    c.latitude, c.longitude = p.lat, p.lng
    c.display_name = companies.clean_text(p.name, 200) or c.display_name
    if p.address:
        c.address_line = companies.clean_text(p.address.split(",")[0], 300)
    if p.postal_code:
        c.postal_code = p.postal_code[:8]
        pc = postcodes().get(p.postal_code)
        c.municipality_code = pc["municipality_code"][:8] if pc else None
    if p.city:
        c.city = companies.clean_text(p.city, 120)


def apply_details(db: OrmSession, c: SalesCompany, d: places.Details) -> None:
    from app.modules.campaigns.service import normalize_phone

    ref = f"google_place:{c.google_place_id}"
    c.google_fetched_at = _now()
    c.rating, c.user_rating_count, c.google_opening_hours = d.rating, d.user_rating_count, d.opening_hours
    if d.website:
        c.website_url = d.website[:500]
        c.domain = companies.normalize_domain(d.website)
        companies.add_fact(db, c, field="website", value=d.website, ref=ref, extractor=EXTRACTOR)
    phone = normalize_phone(d.phone_international or d.phone_national or "")
    if phone:
        fact = companies.add_fact(db, c, field="phone_e164", value=phone, ref=ref, extractor=EXTRACTOR,
                                  evidence=d.phone_national or "")
        companies.set_main_phone(db, c, phone, fact)
    if d.opening_hours:
        companies.add_fact(db, c, field="opening_hours", value="; ".join(d.opening_hours), ref=ref, extractor=EXTRACTOR)


def _finish(job: SalesSearchJob, status: str, error: str | None = None) -> None:
    job.status, job.error, job.lease_expires_at = status, error, None
    if status in ("done", "failed", "cancelled"):
        job.finished_at = _now()


def claim(db: OrmSession) -> SalesSearchJob | None:
    """At most one job runs at a time; an expired lease (crashed worker) is taken over."""
    now = _now()
    if db.scalar(select(SalesSearchJob.id).where(SalesSearchJob.status == "running",
                                                 SalesSearchJob.lease_expires_at > now).limit(1)):
        return None
    job = db.scalar(select(SalesSearchJob)
                    .where(or_(SalesSearchJob.status == "queued",
                               (SalesSearchJob.status == "running") & (SalesSearchJob.lease_expires_at <= now)))
                    .order_by(SalesSearchJob.created_at).with_for_update(skip_locked=True).limit(1))
    if job is None:
        return None
    job.status, job.lease_expires_at = "running", now + LEASE
    job.started_at = job.started_at or now
    db.commit()
    return job


def run_step(db: OrmSession, job: SalesSearchJob, client) -> bool:
    """Run one plan step (one area × query, up to 3 pages). Returns False when the job is finished or stopped."""
    step = job.plan[job.cursor]
    area, query = step["area"], step["query"]
    token: str | None = None
    for _page in range(places.MAX_PAGES):
        db.refresh(job)
        if job.status != "running":
            return False
        if job.progress.get("found", 0) >= job.max_results:
            _finish(job, "done")
            return False
        _spend(db, job, "search")
        text = f"{query['term']} i {area['label'].split(' (')[0]}"
        found, token = client.search(text_query=text, included_type=query["type"],
                                     center=(area["lat"], area["lng"]), radius_m=area["radius_m"], page_token=token)
        for place in found:
            if job.progress.get("found", 0) >= job.max_results:
                break
            _bump(job, "examined")
            what = _store_place(db, job, place, query, client)
            if what == "new":
                _bump(job, "found")
            elif what == "duplicate":
                _bump(job, "found")
                _bump(job, "duplicates")
            elif what == "incomplete":
                _bump(job, "incomplete")
            elif what == "known":
                _bump(job, "skipped", reason="already_known")
            elif what.startswith("skipped_"):
                _bump(job, "skipped", reason=what.removeprefix("skipped_"))
            else:
                _bump(job, "skipped", reason="not_relevant")
            job.lease_expires_at = _now() + LEASE
        db.commit()
        if not token:
            break
    job.cursor += 1
    _bump(job, "steps_done")
    if job.cursor >= len(job.plan) or job.progress.get("found", 0) >= job.max_results:
        _finish(job, "done")
    db.commit()
    return job.status == "running"


def run_due(db: OrmSession, client=None, time_limit: float = STEP_TIME_LIMIT) -> int:
    """Worker hook: continue the oldest queued/running job for up to `time_limit` seconds. Returns steps run."""
    import time

    job = claim(db)
    if job is None:
        return 0
    client = client or places.client()
    started, steps = time.monotonic(), 0
    try:
        while job.cursor < len(job.plan) and time.monotonic() - started < time_limit:
            steps += 1
            if not run_step(db, job, client):
                break
        else:
            if job.cursor >= len(job.plan) and job.status == "running":
                _finish(job, "done")
    except _CapReached:
        db.rollback()
        job = db.get(SalesSearchJob, job.id)
        _finish(job, "paused", f"Dagens loft på {get_settings().sales_search_daily_request_cap} Google-forespørgsler "
                               "er nået. Genoptag i morgen eller hæv SALES_SEARCH_DAILY_REQUEST_CAP.")
    except places.PlacesError as e:
        db.rollback()
        job = db.get(SalesSearchJob, job.id)
        _finish(job, "paused" if e.retryable else "failed", str(e)[:500])
    else:
        if job.status == "running":
            job.lease_expires_at = _now()  # free for the next tick (or another worker) to continue
    db.commit()
    log.info("sales.search.tick", job_id=str(job.id), steps=steps, status=job.status)
    return steps


def refresh_stale(db: OrmSession, client=None, limit: int = 50) -> dict:
    """Google's caching rule: refresh Google fields older than GOOGLE_PLACES_CACHE_DAYS, or clear them when that is
    not possible. The place id is kept (Google allows storing it indefinitely). Demo/import rows are ours."""
    s = get_settings()
    cutoff = _now() - timedelta(days=s.google_places_cache_days)
    rows = db.scalars(select(SalesCompany).where(SalesCompany.source == "google",
                                                 SalesCompany.google_fetched_at < cutoff)
                      .order_by(SalesCompany.google_fetched_at).limit(limit)).all()
    client = client or places.client()
    refreshed = cleared = 0
    for c in rows:
        day = _now().astimezone(TZ).date().isoformat()
        ok = False
        if client.source == "google" and requests_today(db) < s.sales_search_daily_request_cap:
            _refresh_used[day] = _refresh_used.get(day, 0) + 1
            try:
                apply_details(db, c, client.details(c.google_place_id))
                ok = True
            except places.PlacesError:
                ok = False
        if ok:
            refreshed += 1
        else:
            clear_google(db, c)
            cleared += 1
    db.commit()
    return {"refreshed": refreshed, "cleared": cleared}


def clear_google(db: OrmSession, c: SalesCompany) -> None:
    from app.models import SalesContact, SalesSourceFact

    for f in db.scalars(select(SalesSourceFact).where(SalesSourceFact.company_id == c.id,
                                                      SalesSourceFact.url_or_ref.like("google_place:%"))):
        db.query(SalesContact).filter(SalesContact.source_fact_id == f.id).update({"source_fact_id": None})
        db.delete(f)
    c.google_fetched_at = None
    c.google_types, c.google_primary_type, c.google_business_status, c.google_maps_uri = [], None, None, None
    c.google_opening_hours, c.rating, c.user_rating_count, c.latitude, c.longitude = None, None, None, None, None
    if c.research_status != "profiled":
        c.research_status = "incomplete"
    c.research_error = "Google-data udløbet og kunne ikke genopfriskes"


def daily_refresh_due(db: OrmSession) -> dict | None:
    """Worker hook: once per Copenhagen day after 03:00."""
    local = _now().astimezone(TZ)
    key = local.date().isoformat()
    if local.hour < 3 or _refresh_ran.get("day") == key:
        return None
    _refresh_ran["day"] = key
    return refresh_stale(db)


_refresh_ran: dict[str, str] = {}


# --------------------------------------------------------------------------- import


IMPORT_HEADERS = {"name": ("navn", "name", "virksomhed", "firma"), "cvr": ("cvr", "cvr-nummer"),
                  "website": ("hjemmeside", "website", "url"), "phone": ("telefon", "tlf", "phone"),
                  "email": ("e-mail", "email", "mail"), "postal_code": ("postnr", "postnummer", "postal_code")}


def import_csv(db: OrmSession, *, user_id: uuid.UUID | None, text: str, industry_key: str | None = None) -> SalesSearchJob:
    from app.modules.campaigns.service import normalize_phone
    from app.modules.knowledge.importer import cvr_valid

    if industry_key and industry_key not in channel.industries(db):
        raise ValidationFailed("Ukendt branche", field_errors=[{"field": "industry_key"}])
    sample = text[:2000]
    dialect = csv.Sniffer().sniff(sample, delimiters=",;\t") if sample.strip() else csv.excel
    reader = csv.reader(io.StringIO(text), dialect)
    rows = list(reader)
    if len(rows) < 2:
        raise ValidationFailed("CSV-filen skal have en overskriftslinje og mindst én virksomhed", field_errors=[{"field": "csv"}])
    head = [h.strip().lower() for h in rows[0]]
    cols = {k: next((i for i, h in enumerate(head) if h in names), None) for k, names in IMPORT_HEADERS.items()}
    if cols["name"] is None:
        raise ValidationFailed("CSV-filen mangler kolonnen \"navn\"", field_errors=[{"field": "csv"}])
    if len(rows) - 1 > get_settings().sales_search_max_results:
        raise ValidationFailed(f"Højst {get_settings().sales_search_max_results} rækker pr. import",
                               field_errors=[{"field": "csv"}])
    job = SalesSearchJob(created_by=user_id, industry_keys=[industry_key] if industry_key else [], google_types=[],
                         keywords=[], geo_kind="postal_codes", geo={}, max_results=len(rows) - 1, source="import",
                         status="running", started_at=_now(), plan=[], cursor=0,
                         progress={"examined": 0, "found": 0, "skipped": 0, "incomplete": 0, "duplicates": 0,
                                   "requests_used": 0, "details_used": 0, "estimated_cost_minor": 0, "reasons": {}},
                         budget={})
    db.add(job)
    db.flush()
    ref = f"import:{job.id}"

    def col(r: list[str], k: str) -> str:
        i = cols[k]
        return r[i].strip() if i is not None and i < len(r) else ""

    for r in rows[1:]:
        _bump(job, "examined")
        name = companies.clean_text(col(r, "name"), 200)
        if not name:
            _bump(job, "skipped", reason="missing_name")
            continue
        cvr = "".join(ch for ch in col(r, "cvr") if ch.isdigit()) or None
        if cvr and not cvr_valid(cvr):
            cvr = None
        if cvr and db.scalar(select(SalesCompany.id).where(SalesCompany.cvr == cvr)):
            _bump(job, "skipped", reason="already_known")
            continue
        website = col(r, "website") or None
        phone = normalize_phone(col(r, "phone")) if col(r, "phone") else None
        postal = "".join(ch for ch in col(r, "postal_code") if ch.isdigit())[:4] or None
        c = SalesCompany(source="import", display_name=name, cvr=cvr, website_url=website[:500] if website else None,
                         domain=companies.normalize_domain(website), postal_code=postal,
                         city=(postcodes().get(postal) or {}).get("name") if postal else None,
                         public_email=col(r, "email")[:320] or None, industry_key=industry_key,
                         industry_text=(channel.industries(db).get(industry_key) or {}).get("label") if industry_key else None,
                         relevance_score=1, relevance_reasons=["Importeret af operatør"], last_search_job_id=job.id)
        db.add(c)
        db.flush()
        companies.add_fact(db, c, field="name", value=name, ref=ref, confidence="medium", extractor="csv-import-v1")
        for field, value in (("cvr", cvr), ("website", website), ("postal_code", postal), ("email", c.public_email)):
            if value:
                companies.add_fact(db, c, field=field, value=value, ref=ref, confidence="medium", extractor="csv-import-v1")
        if phone:
            fact = companies.add_fact(db, c, field="phone_e164", value=phone, ref=ref, confidence="medium",
                                      extractor="csv-import-v1")
            companies.set_main_phone(db, c, phone, fact)
        c.existing_customer_workspace_id = companies.existing_customer(db, domain=c.domain, cvr=c.cvr)
        companies.flag_duplicates(db, c)
        companies.compute_quality(db, c)
        _bump(job, "found")
        if c.possible_duplicate_of:
            _bump(job, "duplicates")
    _finish(job, "done")
    return job


def get_job(db: OrmSession, job_id: uuid.UUID) -> SalesSearchJob:
    job = db.get(SalesSearchJob, job_id)
    if job is None:
        raise NotFound("Søgningen findes ikke")
    return job


def job_out(j: SalesSearchJob) -> dict:
    return {"id": str(j.id), "industry_keys": j.industry_keys, "google_types": j.google_types, "keywords": j.keywords,
            "geo_kind": j.geo_kind, "geo": j.geo, "max_results": j.max_results,
            "exclude_existing_customers": j.exclude_existing_customers, "source": j.source, "status": j.status,
            "progress": j.progress, "budget": j.budget, "error": j.error,
            "areas": len({str(s["area"]) for s in j.plan}), "steps": len(j.plan), "cursor": j.cursor,
            "created_at": j.created_at.isoformat() if j.created_at else None,
            "started_at": j.started_at.isoformat() if j.started_at else None,
            "finished_at": j.finished_at.isoformat() if j.finished_at else None}
