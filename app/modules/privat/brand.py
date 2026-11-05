"""Dialogbot's name on everything the Privat apps send out, and the partner links that earn indirect revenue.

Branding: every text a user sends on (a cancellation, a complaint, an invitation, an expense summary) ends with
`footer()` – one line with Dialogbot's name and address, never more. Calls already open with «jeg ringer fra Dialogbot».

Partner links: `offer(category)` returns a partner from PRIVAT_PARTNER_LINKS, or None. Shown ONLY with the word
«Annonce» and the note that Dialogbot may get a commission (markedsføringsloven: no hidden advertising), never mixed
into a ranking of businesses the user asked about, and never instead of what the user asked for.
"""
from __future__ import annotations

import json
from functools import lru_cache

from app.config import get_settings

CATEGORIES = ("mobil", "internet", "el", "streaming", "forsikring", "dyreforsikring", "flyttefirma", "fest", "hjem",
              "garanti", "dagligvarer", "fitness")
AD_NOTE = "Annonce – Dialogbot kan få provision, hvis du køber."


def site() -> str:
    return get_settings().frontend_base_url.rstrip("/")


def footer() -> str:
    return f"– Sendt med Dialogbot, din personlige assistent · {site()}/privat"


def branded(text: str) -> str:
    return f"{text.rstrip()}\n\n{footer()}"


@lru_cache(maxsize=4)
def _parse(raw: str) -> dict:
    try:
        data = json.loads(raw) if raw.strip() else {}
    except ValueError:
        return {}
    out = {}
    for k, v in (data.items() if isinstance(data, dict) else []):
        if k in CATEGORIES and isinstance(v, dict) and str(v.get("url", "")).startswith("https://") and v.get("name"):
            out[k] = {"category": k, "name": str(v["name"])[:80], "url": str(v["url"])[:500],
                      "text": str(v.get("text") or v["name"])[:160], "note": AD_NOTE}
    return out


def offer(category: str | None) -> dict | None:
    return _parse(get_settings().privat_partner_links).get(category or "")


def offer_line(category: str | None) -> str:
    o = offer(category)
    return f"\n\n{o['text']}: {o['url']} ({AD_NOTE})" if o else ""
