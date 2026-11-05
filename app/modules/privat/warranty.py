"""The Garanti & kvitteringer app: what you bought, where, and until when you can complain.

Saved (`private_app_data` «garanti», `items`): product, shop, purchase date, price and any extra warranty the user
mentions. Danish consumers have 2 years' reklamationsret (købeloven § 83) from delivery; a shop's own warranty can be
longer. Reminder: 30 days before the reklamationsret (and an extra warranty) runs out – «does it still work?». When
something breaks, Peter writes the complaint to the shop (with Dialogbot's footer); the user sends it.
Photos of receipts are not stored yet – the user keeps the receipt (said in the app).
"""
from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy.orm import Session as OrmSession

from app.core.errors import ValidationFailed
from app.modules.privat import app_kit as kit
from app.modules.privat import brand

ADDON, PATH = "garanti", "/privat/apps/garanti"


def _today() -> date:
    from app.modules.privat import rules

    return rules.local().date()
REKLAMATION_YEARS, WARN_DAYS = 2, 30


def add(db: OrmSession, ws_id: uuid.UUID, *, product: str, bought: str, shop: str = "", price=None,
        warranty_years: int | None = None) -> dict:
    product = kit.clean(product, 120)
    if not product:
        raise ValidationFailed("Hvilken ting?", field_errors=[{"field": "product"}])
    row = {"id": kit.new_id(), "name": product[:1].upper() + product[1:], "shop": kit.clean(shop, 80),
           "bought": kit.parse_date(bought, "bought", required=True)}
    if date.fromisoformat(row["bought"]) > _today():
        raise ValidationFailed("Købsdatoen ligger i fremtiden", field_errors=[{"field": "bought"}])
    if (p := kit.amount(price, "price")) is not None:
        row["price_minor"] = p
    if warranty_years:
        row["warranty_years"] = max(1, min(int(warranty_years), 10))
    rows = [row] + kit.items(db, ws_id, ADDON)
    kit.save_items(db, ws_id, ADDON, rows[:500])
    return row


def reklamation_until(row: dict) -> date:
    return kit.add_months(date.fromisoformat(row["bought"]), 12 * REKLAMATION_YEARS)


def warranty_until(row: dict) -> date | None:
    return kit.add_months(date.fromisoformat(row["bought"]), 12 * row["warranty_years"]) if row.get("warranty_years") else None


def line(row: dict, today: date | None = None) -> str:
    today = today or _today()
    rek = reklamation_until(row)
    bits = [row["name"] + (f" fra {row['shop']}" if row.get("shop") else ""), f"købt {kit.date_text(row['bought'])}"]
    bits.append(f"reklamationsret til {kit.date_text(rek.isoformat())}" if rek >= today else "reklamationsretten er udløbet")
    if (w := warranty_until(row)) and w > rek:
        bits.append(f"garanti til {kit.date_text(w.isoformat())}")
    return ", ".join(bits)


def complaint(row: dict, problem: str, user_name: str, today: date | None = None) -> str:
    today = today or _today()
    inside = reklamation_until(row) >= today or ((w := warranty_until(row)) is not None and w >= today)
    basis = ("Jeg gør hermed min reklamationsret gældende efter købeloven § 83, da varen er købt for mindre end 2 år siden"
             if reklamation_until(row) >= today else "Jeg henviser til den garanti, der fulgte med varen")
    if not inside:
        basis = "Jeg er klar over, at reklamationsretten er udløbet, men beder jer se på sagen af kulance"
    first_year = (today - date.fromisoformat(row["bought"])).days < 365
    proof = (" Fejlen er opstået inden for det første år, så det formodes, at den var der ved leveringen." if first_year
             else "")
    return brand.branded(
        f"Emne: Reklamation – {row['name']}\n\nHej {row.get('shop') or 'butikken'}\n\n"
        f"Jeg købte {row['name']} hos jer den {kit.date_text(row['bought'])}. {kit.clean(problem, 400).rstrip('.')}.\n\n"
        f"{basis}.{proof} Jeg beder jer om at reparere eller ombytte varen og vende tilbage med, hvordan jeg sender "
        f"eller afleverer den.\n\nKvitteringen er vedlagt.\n\nVenlig hilsen\n{user_name}")


def overview(db: OrmSession, ws_id: uuid.UUID) -> dict:
    rows = kit.items(db, ws_id, ADDON)
    today = _today()
    active = [r for r in rows if reklamation_until(r) >= today or (warranty_until(r) or today) > today]
    return {"summary": (f"{len(rows)} ting gemt – {len(active)} kan du stadig reklamere over. Gem selv kvitteringen."
                        if rows else "Ingen ting gemt endnu. Sig fx «Jeg købte en vaskemaskine i Elgiganten den 3. maj»."),
            "items": [{"id": r["id"], "text": r["name"], "sub": line(r, today)} for r in rows],
            "partner": brand.offer("garanti")}


def remove(db: OrmSession, ws_id: uuid.UUID, item_id: str) -> bool:
    return kit.remove_item(db, ws_id, ADDON, item_id)


def due(data: dict, today: date) -> list[tuple[str, str]]:
    out = []
    for r in data.get("items", []):
        for label, until in (("reklamationsretten", reklamation_until(r)), ("garantien", warranty_until(r))):
            if until and 0 <= (until - today).days <= WARN_DAYS:
                out.append((f"{label[:3]}:{r['id']}:{until.isoformat()}",
                            f"{label.capitalize()} på {r['name']} udløber {kit.date_text(until.isoformat())}. "
                            "Virker den, som den skal? Ellers skriver jeg reklamationen nu."))
    return out
