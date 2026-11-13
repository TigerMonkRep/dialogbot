"""«Inden du går live»: the to-do list for the admin tab, worked out from the running configuration.

Automatic points are read from settings and code (nothing to tick – they turn green when the thing is in place).
Manual points (lawyer, DNS, having read a dry run) are ticked by an operator and stored in outreach_todo_marks.
Texts are Danish: this is shown as-is in the admin (the admin is Danish only).
"""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session as OrmSession

from app.config import get_settings
from app.models import OutreachCallQueue, OutreachLead, OutreachMessage, OutreachSuppression, OutreachTodoMark
from app.modules.billing import markets
from app.modules.outreach import finder, localization
from app.modules.outreach.compliance import matrix as m
from app.modules.outreach.compliance import rate_limits
from app.modules.outreach.schemas import NICHES

MANUAL = {
    "legal_review": ("Få markederne og bundteksterne godkendt af en jurist",
                     "Matrixen (docs/sales/cold-outreach.md), bundteksterne, privatlivsteksten (GDPR art. 14) og en "
                     "skriftlig interesseafvejning. Sæt hak, når det er gjort."),
    "sending_domain": ("Sæt SPF, DKIM og DMARC op på afsenderdomænet og varm det op",
                       "Brug et særskilt domæne til kold e-mail (ikke dialogbot.app), så hoveddomænets omdømme er beskyttet."),
    "dry_run_read": ("Læs en tørkørsel igennem og godkend teksterne",
                     "Kør en kampagne i tørkørsel herunder, og læs de færdige e-mails, før noget sendes rigtigt."),
}
NICHE_LABELS = {"plumber": "VVS / blikkenslager", "hvac": "Varme og ventilation (HVAC)", "dentist": "Tandlæge",
                "med spa": "Skønhedsklinik (med spa)", "auto repair": "Autoværksted", "hair salon": "Frisør"}
RULES = {
    "US": "Alle virksomhedsformer. Webmail-adresser er tilladt.",
    "UK": "Kun selskaber (Ltd, Limited, LLP, PLC). Webmail og enkeltmandsfirmaer afvises.",
    "IE": "Kun firmaadresser – webmail afvises.",
    "CA": "Kun adresser, virksomheden selv har offentliggjort (kilde-URL gemmes).",
    "AU": "Kun adresser, virksomheden selv har offentliggjort (kilde-URL gemmes).",
    "SE": "Kun juridiske personer – webmail afvises.",
    "FR": "Kun professionelle adresser – webmail afvises.",
    "NO": "Kun generelle firmaadresser (post@, info@ …).",
    "DK": "Ingen e-mail. ApS og A/S uden reklamebeskyttelse kommer på ringelisten (upload CSV).",
}
NAMES = {"US": "USA", "UK": "Storbritannien", "IE": "Irland", "CA": "Canada", "AU": "Australien", "SE": "Sverige",
         "FR": "Frankrig", "NO": "Norge", "ES": "Spanien", "PL": "Polen", "DK": "Danmark", "DE": "Tyskland",
         "AT": "Østrig", "NL": "Holland", "IT": "Italien", "CH": "Schweiz", "BE": "Belgien"}


def market_rows() -> list[dict]:
    s = get_settings()
    rows = []
    for code, j in m.MATRIX.items():
        open_, why = finder.market_open(code)
        state = "email" if open_ else ("call_list" if code == "DK" and code in s.outreach_call_queue else j.status)
        rows.append({
            "code": code, "name": NAMES.get(code, code), "tier": j.tier, "state": state, "regime": j.regime,
            "rules": RULES.get(code) or why,
            "price": localization.locale_for(code).price if open_ else None,
            "demo_available": code in s.outreach_demo_countries,
        })
    return rows


def todos(db: OrmSession) -> list[dict]:
    s = get_settings()
    marks = {x.key: x for x in db.scalars(select(OutreachTodoMark))}
    email_markets = [r["code"] for r in market_rows() if r["state"] == "email"]
    no_demo = [c for c in email_markets if c not in s.outreach_demo_countries]
    out: list[dict] = []

    def auto(key: str, title: str, how: str, done: bool, needed_for: str = "live") -> None:
        out.append({"key": key, "title": title, "how": how, "done": bool(done), "kind": "auto", "needed_for": needed_for})

    auto("mode", "Slå outreach til i tørkørsel",
         "Sæt OUTREACH_MODE=dry_run på Render (dialogbot-api-staging). Så kan du finde virksomheder og få e-mails "
         "skrevet og kontrolleret – uden at noget sendes.", s.outreach_mode != "off", "dry_run")
    auto("anthropic", "Claude er sat op til research og tekst",
         "AI_PROVIDER=anthropic og ANTHROPIC_API_KEY på Render.", s.ai_provider == "anthropic", "dry_run")
    auto("places", "Google Places-nøglen er sat (virksomhedssøgning)",
         "GOOGLE_PLACES_API_KEY på Render. Uden den kan du stadig uploade en CSV.", bool(s.google_places_api_key), "optional")
    auto("demo", "Demo-opkaldet kan ringe til de lande, du skriver til",
         ("Mangler for: " + ", ".join(no_demo) + ". " if no_demo else "") +
         "Demoen på dialogbot.app tager i dag kun danske numre og taler dansk. E-mailens eneste opfordring er at prøve "
         "demoen, så den skal virke på engelsk med lokale numre. Når den gør, tilføjes landet i "
         "OUTREACH_DEMO_CALLBACK_COUNTRIES. Indtil da holder systemet e-mails til det land tilbage.", not no_demo)
    auto("postal", "Fuld postadresse i bundteksten",
         "Sæt OUTREACH_POSTAL_ADDRESS (vej, postnummer, by, land). «Aarhus, Denmark» er ikke nok til CAN-SPAM og CASL.",
         bool(s.outreach_postal_address))
    auto("inboxes", "Afsenderadresser er valgt",
         "Sæt OUTREACH_SENDER_INBOXES (kommasepareret). Hver adresse sender højst "
         f"{s.outreach_daily_limit_per_inbox} e-mails om dagen.", bool(s.outreach_inboxes))
    auto("provider", f"Afsendelse via {s.outreach_provider} er sat op",
         "OUTREACH_RESEND_API_KEY (Resend) eller OUTREACH_SMTP_HOST m.fl. (SMTP). Instantly og Smartlead er ikke bygget.",
         (s.outreach_provider == "resend" and bool(s.outreach_resend_api_key))
         or (s.outreach_provider == "smtp" and bool(s.outreach_smtp_host)))
    auto("webhooks", "Svar, afvisninger og klager kommer retur fra udbyderen",
         "Peg udbyderens webhook på /api/v1/webhooks/events og sæt RESEND_WEBHOOK_SECRET (Resend) eller "
         "OUTREACH_WEBHOOK_SECRET (andre).", bool(s.resend_webhook_secret or s.outreach_webhook_secret))
    auto("prices", "Priserne i e-mailen kan faktisk købes",
         f"E-mails til USA og UK nævner {s.outreach_price_us} og {s.outreach_price_uk}, men der faktureres kun i "
         "DKK, SEK, NOK og EUR. Tilføj USD og GBP i priserne, eller ret OUTREACH_PRICE_US / OUTREACH_PRICE_UK.",
         "USD" in markets.ERHVERV and "GBP" in markets.ERHVERV)
    auto("numbers", "Lokale numre, demoen ringer fra (+1 / +44)",
         "Valgfrit: OUTREACH_CALLBACK_NUMBER_US og _UK. Uden dem må e-mailen ikke nævne et lokalt nummer.",
         bool(s.outreach_callback_number_us and s.outreach_callback_number_uk), "optional")
    for key, (title, how) in MANUAL.items():
        mark = marks.get(key)
        out.append({"key": key, "title": title, "how": how, "done": mark is not None, "kind": "manual", "needed_for": "live",
                    "done_at": mark.done_at.isoformat() if mark else None})
    auto("live", "Skift til rigtig afsendelse",
         "Til sidst: OUTREACH_MODE=live på Render. Tjenesten nægter at starte, hvis afsender, postadresse eller "
         "udbyder mangler.", s.outreach_mode == "live")
    return out


def overview(db: OrmSession) -> dict:
    s = get_settings()
    items = todos(db)
    from datetime import UTC, datetime

    today = datetime.now(UTC).date()
    by_status = dict(db.execute(select(OutreachLead.status, func.count()).group_by(OutreachLead.status)).all())
    batches = [{"name": n, "created_at": c.isoformat(), "leads": k}
               for n, c, k in db.execute(select(OutreachLead.batch, func.min(OutreachLead.created_at), func.count())
                                         .group_by(OutreachLead.batch).order_by(func.min(OutreachLead.created_at).desc()).limit(30))]
    per_batch = db.execute(select(OutreachLead.batch, OutreachLead.status, func.count())
                           .group_by(OutreachLead.batch, OutreachLead.status)).all()
    for b in batches:
        b["totals"] = {st: k for n, st, k in per_batch if n == b["name"]}
    blocking = [x["key"] for x in items if not x["done"] and x["needed_for"] == "live" and x["key"] != "live"]
    return {
        "mode": s.outreach_mode,
        "ready_for_dry_run": all(x["done"] for x in items if x["needed_for"] == "dry_run"),
        "ready_for_live": not blocking,
        "todos": items,
        "open_todos": len([x for x in items if not x["done"] and x["needed_for"] != "optional"]),
        "markets": market_rows(),
        "niches": [{"key": n, "label": NICHE_LABELS[n]} for n in NICHES],
        "search_available": bool(s.google_places_api_key),
        "stats": {
            "leads": by_status,
            "queued": db.scalar(select(func.count()).select_from(OutreachMessage).where(OutreachMessage.status == "queued")) or 0,
            "sent_today": sum(rate_limits.used(db, today).values()),
            "daily_capacity": len(s.outreach_inboxes) * s.outreach_daily_limit_per_inbox,
            "suppressed": db.scalar(select(func.count()).select_from(OutreachSuppression)) or 0,
            "call_list_open": db.scalar(select(func.count()).select_from(OutreachCallQueue).where(
                OutreachCallQueue.status == "open", OutreachCallQueue.scrub_status == "cleared")) or 0,
            "call_list_review": db.scalar(select(func.count()).select_from(OutreachCallQueue).where(
                OutreachCallQueue.status == "open", OutreachCallQueue.scrub_status == "needs_review")) or 0,
        },
        "batches": batches,
    }


def set_mark(db: OrmSession, key: str, done: bool, user_id) -> None:
    from app.core.errors import ValidationFailed

    if key not in MANUAL:
        raise ValidationFailed("Dette punkt kan ikke hakkes af i hånden", code="not_manual")
    mark = db.get(OutreachTodoMark, key)
    if done and mark is None:
        db.add(OutreachTodoMark(key=key, done_by=user_id))
    elif not done and mark is not None:
        db.delete(mark)
