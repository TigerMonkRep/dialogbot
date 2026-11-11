"""The Abonnementer & opsigelse app: what the household pays for every month, lock-in periods, and cancelling.

Saved (`private_app_data` «abonnementer», `items`): name, price and period (monthly/yearly), category, the lock-in end
(binding) and the notice period, as the user gives them – Dialogbot never sees the bank. Reminders: before the last day
to give notice (so the user can decide in time), and before a yearly renewal. Cancelling = a written cancellation the
user sends from their own e-mail (with Dialogbot's footer), or a call proposal (app «Ring for mig») – never on its own.
Revenue: a disclosed partner link for a cheaper alternative in the category (brand.offer), if one is configured.
"""
from __future__ import annotations

import uuid
from datetime import date, timedelta

from sqlalchemy.orm import Session as OrmSession

from app.core.errors import ValidationFailed
from app.modules.privat import app_kit as kit
from app.modules.privat import brand

ADDON, PATH = "abonnementer", "/privat/apps/abonnementer"


def _today() -> date:
    from app.modules.privat import rules

    return rules.local().date()
PERIODS = {"monthly": "md.", "yearly": "år", "quarterly": "kvartal"}
PER_MONTH = {"monthly": 1, "quarterly": 1 / 3, "yearly": 1 / 12}
CATEGORIES = ("streaming", "mobil", "internet", "el", "forsikring", "fitness", "avis", "andet")
GUESS = {"netflix": "streaming", "hbo": "streaming", "max": "streaming", "viaplay": "streaming", "disney": "streaming",
         "spotify": "streaming", "tv 2": "streaming", "mofibo": "streaming", "podimo": "streaming",
         "telia": "mobil", "telenor": "mobil", "3": "mobil", "cbb": "mobil", "lebara": "mobil", "oister": "mobil",
         "yousee": "internet", "stofa": "internet", "norlys": "internet", "hiper": "internet", "fibia": "internet",
         "ørsted": "el", "andel": "el", "ok": "el", "tryg": "forsikring", "alm brand": "forsikring", "topdanmark":
         "forsikring", "codan": "forsikring", "fitness world": "fitness", "sats": "fitness", "politiken": "avis",
         "berlingske": "avis", "jyllands-posten": "avis"}
NOTICE_WARN_DAYS, RENEW_WARN_DAYS = 10, 21


def _category(name: str, given: str | None) -> str:
    if given in CATEGORIES:
        return given
    k = kit.key_of(name)
    return next((c for n, c in GUESS.items() if k == n or k.startswith(n + " ")), "andet")


def add(db: OrmSession, ws_id: uuid.UUID, *, name: str, price=None, period: str = "monthly", category: str | None = None,
        binding_until=None, notice_days: int | None = None, renews_on=None) -> tuple[dict, bool]:
    name = kit.clean(name, 100)
    if not name:
        raise ValidationFailed("Hvad hedder abonnementet?", field_errors=[{"field": "name"}])
    period = period if period in PERIODS else "monthly"
    rows = kit.items(db, ws_id, ADDON)
    row = kit.find(rows, name, exact=True)
    created = row is None
    if row is None:
        row = {"id": kit.new_id(), "name": name, "status": "active"}
        rows.append(row)
    price_minor = kit.amount(price, "price")
    if price_minor is not None:
        row["price_minor"] = price_minor
    row["period"] = period if (created or price is not None) else row.get("period", "monthly")
    row["category"] = _category(name, category) if (created or category) else row.get("category", "andet")
    for k, v in (("binding_until", binding_until), ("renews_on", renews_on)):
        d = kit.parse_date(v, k)
        if d:
            row[k] = d
    if notice_days is not None:
        row["notice_days"] = max(0, min(int(notice_days), 180))
    row.setdefault("notice_days", 30)
    kit.save_items(db, ws_id, ADDON, rows)
    return row, created


def monthly_minor(row: dict) -> int:
    return round((row.get("price_minor") or 0) * PER_MONTH.get(row.get("period", "monthly"), 1))


def last_notice_day(row: dict) -> date | None:
    """The last day to give notice so the subscription ends when the lock-in ends."""
    if not row.get("binding_until"):
        return None
    return date.fromisoformat(row["binding_until"]) - timedelta(days=int(row.get("notice_days") or 0))


def line(row: dict) -> str:
    bits = [row["name"]]
    if row.get("price_minor") is not None:
        bits.append(f"{kit.money(row['price_minor'])} pr. {PERIODS.get(row.get('period', 'monthly'), 'md.')}")
    if row.get("binding_until"):
        bits.append(f"binding til {kit.date_text(row['binding_until'])}")
    if row.get("status") == "cancelling":
        bits.append("under opsigelse")
    return ", ".join(bits)


def overview(db: OrmSession, ws_id: uuid.UUID) -> dict:
    rows = [r for r in kit.items(db, ws_id, ADDON)]
    active = [r for r in rows if r.get("status") != "cancelled"]
    total = sum(monthly_minor(r) for r in active)
    cats = {r.get("category") for r in active}
    partner = next((brand.offer(c) for c in ("mobil", "internet", "el", "streaming", "forsikring") if c in cats
                    and brand.offer(c)), None)
    return {"summary": (f"{len(active)} abonnementer – {kit.money(total)} om måneden, {kit.money(total * 12)} om året."
                        if active else "Ingen abonnementer endnu. Fortæl Peter, hvad I betaler for."),
            "items": [{"id": r["id"], "text": line(r), "sub": (f"Sidste dag at opsige: {kit.date_text(last_notice_day(r).isoformat())}"
                                                                 if last_notice_day(r) else
                                                                 ("" if r.get("category") == "andet" else r.get("category", "").capitalize()))}
                      for r in sorted(active, key=lambda r: -monthly_minor(r))],
            "partner": partner}


def overview_text(db: OrmSession, ws_id: uuid.UUID) -> str:
    o = overview(db, ws_id)
    lines = [o["summary"]] + [f"- {i['text']}" for i in o["items"][:20]]
    if o["partner"]:
        lines.append(f"{o['partner']['text']}: {o['partner']['url']} ({brand.AD_NOTE})")
    return "\n".join(lines)


def remove(db: OrmSession, ws_id: uuid.UUID, item_id: str) -> bool:
    return kit.remove_item(db, ws_id, ADDON, item_id)


def cancellation_letter(row: dict, user_name: str, customer_no: str | None = None) -> str:
    end = (f"ved udløbet af bindingsperioden den {kit.date_text(row['binding_until'])}"
           if row.get("binding_until") and date.fromisoformat(row["binding_until"]) >= _today()
           else "hurtigst muligt i henhold til opsigelsesvarslet")
    ref = f"\nKundenummer: {customer_no}" if customer_no else "\nKundenummer: [indsæt dit kundenummer]"
    return brand.branded(
        f"Emne: Opsigelse af abonnement – {row['name']}\n\nHej {row['name']}\n\nJeg opsiger hermed mit abonnement {end}."
        f"{ref}\n\nJeg beder om en skriftlig bekræftelse på opsigelsen og datoen for, hvornår abonnementet stopper.\n\n"
        f"Venlig hilsen\n{user_name}")


def mark_cancelling(db: OrmSession, ws_id: uuid.UUID, row_id: str) -> None:
    rows = kit.items(db, ws_id, ADDON)
    for r in rows:
        if r["id"] == row_id:
            r["status"] = "cancelling"
    kit.save_items(db, ws_id, ADDON, rows)


def due(data: dict, today: date) -> list[tuple[str, str]]:
    out = []
    for r in data.get("items", []):
        if r.get("status") != "active":
            continue
        last = last_notice_day(r)
        if last and 0 <= (last - today).days <= NOTICE_WARN_DAYS:
            out.append((f"notice:{r['id']}:{last.isoformat()}",
                        f"Sidste dag at opsige {r['name']} er {kit.date_text(last.isoformat())}, hvis det skal stoppe, "
                        f"når bindingen udløber. Vil du beholde det – eller skal jeg skrive opsigelsen?"))
        if r.get("renews_on"):
            ren = date.fromisoformat(r["renews_on"])
            if 0 <= (ren - today).days <= RENEW_WARN_DAYS:
                out.append((f"renew:{r['id']}:{r['renews_on']}",
                            f"{r['name']} fornyes {kit.date_text(r['renews_on'])}"
                            f"{' for ' + kit.money(r['price_minor']) if r.get('price_minor') is not None else ''}. "
                            "Bruger I det stadig?"))
    return out
