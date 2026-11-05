"""The Håndværker & tilbud app: «find 3 tømrere og hent tilbud på et nyt gulv» – side by side.

How it works: the business search (places.search, at most 3 operational businesses with a number) finds the trade near
the user; each becomes an ordinary call proposal (app «Ring for mig») that the user approves one by one – Dialogbot never
dials by itself and never says yes to the job, a price or a visit. Each call opens «jeg ringer fra Dialogbot på vegne
af …» (calls.script) and the replies (business_reply / business_price_text) are shown side by side. When the user
picks one, Dialogbot can call it back to say yes thank you and ask them to get in touch – again only after approval.

Revenue: every business asked is a `PrivateBusinessReferral` (asked → chosen / not_chosen). That ledger is what later
lets Dialogbot say «we sent you N customers» and charge per won job. The search order is Google's relevance order –
never bought: a paid placement would have to be marked as such (docs/sales/privat-revenue.md).
"""
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session as OrmSession

from app.core.errors import ValidationFailed
from app.models import PrivateBusinessReferral, PrivateCall
from app.modules.privat import app_kit as kit
from app.modules.privat import rules

ADDON, PATH = "haandvaerker", "/privat/apps/haandvaerker"
MAX_BUSINESSES = 3
KEEP = 20


def _purpose(job: str) -> str:
    return f"Få et tilbud på {job}"


def request(db: OrmSession, ctx, *, job: str, trade: str, city: str | None = None, window: str = "",
            app_key: str = ADDON) -> tuple[dict, list[dict]]:
    """Find up to 3 businesses and make one call proposal each. Returns (job, the businesses). Raises Conflict
    needs_location from places.search when there is no city or position."""
    from app.modules.privat import calls, places

    job, trade = kit.clean(job, 200), kit.clean(trade, 80)
    if not job or not trade:
        raise ValidationFailed("Skriv hvilken opgave og hvilken slags håndværker", field_errors=[{"field": "job"}])
    found = [r for r in places.search(db, ctx, trade, city=kit.clean(city, 80) or None) if r.get("phone_e164")]
    entry = {"id": kit.new_id(), "job": job, "trade": trade, "city": kit.clean(city, 80), "window": kit.clean(window, 120),
             "at": rules.now().isoformat(), "app": app_key, "quotes": [], "chosen": None}
    for r in found[:MAX_BUSINESSES]:
        task = calls.propose(db, ctx, business_name=r["name"], phone=r["phone_e164"], address=r.get("address") or "",
                             price_text=None, purpose=_purpose(job), window=entry["window"],
                             may_ask="Hvad opgaven cirka koster, om de skal se den først, og hvornår de kan gå i gang",
                             may_agree="Kun at de sender et tilbud eller ringer tilbage – ingen aftale om selve arbejdet",
                             may_not="Sige ja til opgaven, aftale en pris eller en besigtigelse, betale eller give "
                                     "adresse og andre oplysninger end navnet",
                             place_id=r.get("place_id"), next_open_at=None, phone_source=r.get("source"))
        call = db.scalar(select(PrivateCall).where(PrivateCall.task_id == task.id))
        ref = PrivateBusinessReferral(workspace_id=ctx.ws_id, app_key=app_key, job=job, trade=trade,
                                      business_name=r["name"][:200], business_phone_e164=r["phone_e164"],
                                      place_id=(r.get("place_id") or None), call_id=call.id if call else None,
                                      status="asked")
        db.add(ref)
        db.flush()
        entry["quotes"].append({"name": r["name"], "task_id": str(task.id), "call_id": str(call.id) if call else None,
                                "referral_id": str(ref.id), "address": r.get("address") or ""})
    if entry["quotes"]:
        rows = [entry] + kit.items(db, ctx.ws_id, ADDON)
        kit.save_items(db, ctx.ws_id, ADDON, rows[:KEEP])
    return entry, found[:MAX_BUSINESSES]


def _call(db: OrmSession, q: dict) -> PrivateCall | None:
    return db.get(PrivateCall, uuid.UUID(q["call_id"])) if q.get("call_id") else None


def quote_line(db: OrmSession, q: dict) -> str:
    c = _call(db, q)
    if c is None or c.status == "proposed":
        return f"{q['name']}: venter på, at du godkender opkaldet"
    if c.status in ("approved", "scheduled", "dialling", "in_progress", "unknown"):
        return f"{q['name']}: jeg ringer snart"
    if c.status == "declined":
        return f"{q['name']}: du afviste opkaldet"
    price = f" Pris: {c.business_price_text}." if c.business_price_text else ""
    reply = c.business_reply or ("tog ikke telefonen" if c.status in ("no_answer", "failed") else "intet svar endnu")
    return f"{q['name']}: {reply}{price}"


def compare_text(db: OrmSession, entry: dict) -> str:
    lines = [f"Tilbud på {entry['job']}:"] + [f"{i}. {quote_line(db, q)}" for i, q in enumerate(entry["quotes"], 1)]
    if entry.get("chosen"):
        lines.append(f"Du valgte {entry['chosen']}.")
    else:
        lines.append("Sig hvem du vælger, så ringer jeg og siger ja tak – når du har godkendt det.")
    return "\n".join(lines)


def latest(db: OrmSession, ws_id: uuid.UUID, wanted: str | None = None) -> dict | None:
    rows = kit.items(db, ws_id, ADDON)
    if wanted:
        return kit.find(rows, wanted, "job") or None
    return rows[0] if rows else None


def choose(db: OrmSession, ctx, entry: dict, business: str):
    """Mark the chosen business (and the others not chosen) and propose the «ja tak» call. Returns the task."""
    from app.modules.privat import calls

    q = kit.find(entry["quotes"], business)
    if q is None:
        raise ValidationFailed("Den virksomhed er ikke en af dem, jeg spurgte: "
                               + ", ".join(x["name"] for x in entry["quotes"]), field_errors=[{"field": "business"}])
    now = rules.now()
    for x in entry["quotes"]:
        ref = db.get(PrivateBusinessReferral, uuid.UUID(x["referral_id"])) if x.get("referral_id") else None
        if ref is not None:
            ref.status, ref.chosen_at = ("chosen", now) if x is q else ("not_chosen", None)
    rows = kit.items(db, ctx.ws_id, ADDON)
    for r in rows:
        if r["id"] == entry["id"]:
            r["chosen"] = q["name"]
    kit.save_items(db, ctx.ws_id, ADDON, rows)
    c = _call(db, q)
    return calls.propose(db, ctx, business_name=q["name"], phone=c.business_phone_e164 if c else None,
                         address=q.get("address") or "", price_text=None,
                         purpose=f"Sig ja tak til jeres tilbud på {entry['job']} og bed jer kontakte mig for at aftale "
                                 "det videre",
                         window="", may_ask="Hvordan de vil kontakte mig, og hvornår",
                         may_agree="At de kontakter mig for at aftale arbejdet",
                         may_not="Indgå den endelige aftale, aftale en pris, betale eller give adresse",
                         place_id=None, next_open_at=None, phone_source="user")


def overview(db: OrmSession, ws_id: uuid.UUID) -> dict:
    rows = kit.items(db, ws_id, ADDON)
    return {"summary": (f"{len(rows)} opgaver med tilbud." if rows else
                        "Ingen tilbud endnu. Sig fx «Find 3 malere i Aarhus og hent tilbud på at male stuen»."),
            "items": [{"id": r["id"], "text": r["job"].capitalize(),
                       "sub": "; ".join(quote_line(db, q) for q in r["quotes"])
                              + (f" · Valgt: {r['chosen']}" if r.get("chosen") else "")} for r in rows],
            "partner": None}  # never an ad next to businesses the user asked about


def remove(db: OrmSession, ws_id: uuid.UUID, item_id: str) -> bool:
    return kit.remove_item(db, ws_id, ADDON, item_id)
