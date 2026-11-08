"""Wishes on a wishlist: the product fields, «Indsæt link» (import) and «Søg efter produkt» (search).

One data model for all three ways in (private_task_items): search → pick → import → the same editable form as a pasted
link or a wish typed by hand. Nothing is saved before the owner presses «Gem ønske».

Import reads the shop's own structured data (product_meta.py) through the SSRF-safe fetcher (safe_fetch.py). Price,
stock and variants are only what the page declares; the link is kept verbatim apart from pure tracking parameters
(variant=, size= … stay). When the page cannot be read, the answer still carries the link (readable: false) so the
owner fills in the rest and saves. The product image is downloaded, validated and stored in our private bucket, so
givers never load images from the shop and a picture never changes behind the owner's back.

Search uses the same web search as «Hvor kan den købes?» (links.py: Anthropic's server-side web search, needs
AI_PROVIDER=anthropic and PRIVAT_WEB_SEARCH=true), then reads every candidate page like an import. Results contain only
what those pages say – no model-written prices. Without that configuration search answers 503 search_unavailable and
the web offers «Indsæt link» and «Opret selv» instead (it never pretends to search).
"""
from __future__ import annotations

import logging
import re
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from app.core.errors import ApiError, ValidationFailed
from app.models import PrivateTaskItem
from app.modules.privat import product_meta, rules, safe_fetch, wish_images

log = logging.getLogger(__name__)

CURRENCY = re.compile(r"^[A-Z]{3}$")
TEXT_FIELDS = {"size": 80, "color": 80, "variant": 120, "shop": 120}


class SearchUnavailable(ApiError):
    status_code = 503
    code = "search_unavailable"


def _bad(field: str, msg: str) -> ValidationFailed:
    return ValidationFailed(msg, field_errors=[{"field": field, "message": msg}])


def clean_link(link: str | None) -> str | None:
    link = (link or "").strip()
    if not link:
        return None
    if not link.lower().startswith(("https://", "http://")):
        link = "https://" + link
    try:
        u = product_meta.clean_url(link)
    except ValueError as e:
        raise _bad("link", "Linket ser ikke ud som en webadresse") from e
    if not re.match(r"^https?://[^/\s]+\.[^/\s]+", u):
        raise _bad("link", "Linket ser ikke ud som en webadresse")
    return u[:1000]


def apply_fields(item: PrivateTaskItem, data: dict, *, ws_id: uuid.UUID, partial: bool) -> None:
    """Validate and copy the wish fields of `data` onto `item` (partial: only the keys present)."""
    has = (lambda k: k in data) if partial else (lambda k: True)
    if has("text"):
        t = " ".join(str(data.get("text") or "").split())[:300]
        if not t:
            raise _bad("text", "Giv ønsket en titel")
        item.text = t
    if has("note"):
        item.note = (str(data.get("note") or "")).strip()[:500] or None
    if has("link"):
        item.link = clean_link(data.get("link"))
    if has("quantity"):
        q = data.get("quantity") if data.get("quantity") is not None else 1
        if not isinstance(q, int) or q < 1 or q > 99:
            raise _bad("quantity", "Antal skal være mellem 1 og 99")
        item.quantity = q
    for k, n in TEXT_FIELDS.items():
        if has(k):
            setattr(item, k, " ".join(str(data.get(k) or "").split())[:n] or None)
    if has("currency"):
        cur = (data.get("currency") or "").strip().upper() or None
        if cur and not CURRENCY.match(cur):
            raise _bad("currency", "Ugyldig valuta")
        item.currency = cur
    if has("price_minor"):
        p = data.get("price_minor")
        if p is not None and (not isinstance(p, int) or isinstance(p, bool) or p < 0 or p > 10**10):
            raise _bad("price_minor", "Prisen skal være et beløb")
        item.price_minor = p
        src = data.get("price_source")
        if p is None:
            item.price_source, item.price_fetched_at = None, None
        elif src == "shop" and data.get("price_fetched_at"):
            try:
                at = datetime.fromisoformat(str(data["price_fetched_at"]))
            except ValueError as e:
                raise _bad("price_fetched_at", "Ugyldigt tidspunkt") from e
            item.price_source, item.price_fetched_at = "shop", min(at, rules.now())
        elif not partial or "price_source" in data or src is None:
            item.price_source, item.price_fetched_at = "user", None
    if item.price_minor is not None and not item.currency:
        item.currency = "DKK"
    if has("image_key"):
        key = data.get("image_key")
        if key and key != item.image_key:
            if not wish_images.owns(ws_id, key, "oensker"):
                raise _bad("image_key", "Billedet findes ikke – upload det igen")
            old = item.image_key
            item.image_key = key
            item.image_origin = "upload" if data.get("image_origin") == "upload" else "shop"
            if old:
                wish_images.delete(old)
        elif not key and item.image_key:
            wish_images.delete(item.image_key)
            item.image_key, item.image_origin = None, None
    if has("details"):
        d = data.get("details")
        item.details = _clean_details(d) if isinstance(d, dict) else None


def _clean_details(d: dict) -> dict | None:
    out: dict = {}
    for k, n in (("brand", 120), ("sku", 80), ("description", 500), ("availability", 24), ("source_url", 1000)):
        if isinstance(d.get(k), str) and d[k].strip():
            out[k] = d[k].strip()[:n]
    opts = d.get("options")
    if isinstance(opts, dict):
        o = {k: [str(x)[:80] for x in opts.get(k) or [] if isinstance(x, str)][:40] for k in ("sizes", "colors")}
        o["variants"] = [{kk: (str(v[kk])[:160] if isinstance(v[kk], str) else v[kk]) for kk in
                          ("name", "size", "color", "sku", "price_minor", "currency", "availability") if kk in v
                          and isinstance(v[kk], (str, int)) and not isinstance(v[kk], bool)}
                         for v in (opts.get("variants") or [])[:60] if isinstance(v, dict)]
        if o["sizes"] or o["colors"] or o["variants"]:
            out["options"] = o
    return out or None


def wish_out(item: PrivateTaskItem) -> dict:
    """The product part of an item, the same for everybody who may see the list."""
    img = wish_images.urls(item.image_key)
    return {"quantity": item.quantity or 1, "price_minor": item.price_minor, "currency": item.currency,
            "price_source": item.price_source,
            "price_fetched_at": item.price_fetched_at.isoformat() if item.price_fetched_at else None,
            "shop": item.shop, "size": item.size, "color": item.color, "variant": item.variant,
            "image": img, "image_origin": item.image_origin if img else None, "details": item.details}


# --------------------------------------------------------------------------- import («Indsæt link»)

def _store_image(ws_id: uuid.UUID, url: str | None) -> dict | None:
    if not url:
        return None
    try:
        f = safe_fetch.fetch(url, max_bytes=safe_fetch.IMAGE_MAX_BYTES, accept="image/webp,image/png,image/jpeg,*/*;q=0.5")
        if f.status != 200:
            return None
        stored = wish_images.store(ws_id, f.body, "oensker")
    except (safe_fetch.FetchBlocked, safe_fetch.FetchFailed, ValidationFailed):
        return None
    except Exception:  # noqa: BLE001 – storage down, odd image: the wish works without it
        log.warning("wishes: product image not stored", exc_info=True)
        return None
    return {"image_key": stored["key"], "image": wish_images.urls(stored["key"])}


def read_page(url: str) -> tuple[str, dict | None, str | None]:
    """(final url, parsed product facts or None, why it could not be read)."""
    try:
        f = safe_fetch.fetch(url)
    except safe_fetch.FetchBlocked:
        return url, None, "blocked"
    except safe_fetch.FetchFailed:
        return url, None, "unreachable"
    if f.status != 200:
        return url, None, "unreachable"
    if "html" not in f.content_type.lower() and "<html" not in f.text[:2000].lower():
        return f.url, None, "not_a_page"
    facts = product_meta.parse(f.text, f.url)
    return f.url, facts, None if facts.get("found") else "no_product_data"


def import_link(ws_id: uuid.UUID, link: str) -> dict:
    """The preview the owner checks before saving. Always carries the link, also when nothing could be read."""
    url = clean_link(link)
    try:
        safe_fetch.check_url(url)
    except safe_fetch.FetchBlocked as e:
        raise _bad("link", "Linket kan ikke bruges – brug et almindeligt link til en webshop") from e
    except safe_fetch.FetchFailed:
        pass  # does not resolve: answered as «kunne ikke læses» below
    final, facts, why = read_page(url)
    out = {"link": url, "readable": facts is not None and why is None, "reason": why,
           "fetched_at": rules.now().isoformat()}
    if facts:
        out |= {k: facts.get(k) for k in ("title", "price_minor", "currency", "shop", "size", "color", "variant")}
        out["shop"] = out.get("shop") or _shop_from(final)
        out["details"] = _clean_details({**facts, "source_url": final}) or None
        out["options"] = facts.get("options")
        out |= _store_image(ws_id, facts.get("image_url")) or {"image_key": None, "image": None}
        out["source_image_url"] = facts.get("image_url")
    else:
        out["shop"] = _shop_from(url)
    return out


def _shop_from(url: str) -> str | None:
    from urllib.parse import urlsplit

    host = re.sub(r"^(www|shop|m)\.", "", (urlsplit(url).hostname or "").lower())
    return host or None


# --------------------------------------------------------------------------- search («Søg efter produkt»)

def search_available() -> bool:
    from app.config import get_settings
    from app.modules.privat import links

    return links.enabled() and get_settings().ai_provider == "anthropic"


def search(query: str, city: str | None) -> tuple[list[dict], object | None]:
    """Real product pages for `query`: candidates from web search, each one READ (structured data only). Returns
    (results, completion for ai_usage)."""
    from app.modules.privat import links

    if not search_available():
        raise SearchUnavailable("Produktsøgning er ikke sat op endnu. Indsæt et link, eller opret ønsket selv.")
    q = " ".join(query.split())[:120]
    if len(q) < 2:
        raise _bad("q", "Skriv, hvad du leder efter")
    cands, completion = links.search_candidates(q, city)
    cands = [c for c in cands if not links.looks_like_search(c["url"])][:3]

    def one(c: dict) -> dict | None:
        final, facts, why = read_page(c["url"])
        if facts is None or why is not None or not facts.get("title"):
            return None
        return {"link": product_meta.clean_url(final)[:1000], "title": facts.get("title"),
                "image_url": facts.get("image_url"), "price_minor": facts.get("price_minor"),
                "currency": facts.get("currency"), "shop": facts.get("shop") or _shop_from(final),
                "availability": facts.get("availability"), "options": facts.get("options")}

    if not cands:
        return [], completion
    with ThreadPoolExecutor(max_workers=len(cands)) as ex:
        rows = [r for r in ex.map(one, cands) if r]
    return rows, completion
