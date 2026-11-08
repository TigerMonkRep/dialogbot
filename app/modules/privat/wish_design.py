"""«Design ønskeseddel»: a theme and a few safe overrides per wishlist (private_tasks.design).

Stored: {"theme", "accent", "background", "text", "font", "decorations", "subtitle", "date", "cover": {"key", "zoom",
"x", "y"}} – every key but theme optional (null = the theme's own value). Only known theme and font keys, #RRGGBB
colours and a cover key from this workspace's own storage are accepted: no HTML, CSS, URLs or fonts from users.
Readability is enforced here (WCAG): text on background ≥ 4.5:1, white button text on the accent ≥ 4.5:1 and the accent
on the background ≥ 3:1. Over a cover the web always lays a dark scrim under white text, whatever the photo.

The palette is mirrored in web/src/lib/privat/wish-themes.json (the editor's live preview); a test keeps them equal.
Saving a design never touches items, members, reservations or group gifts. A design applies to that one list only.
"""
from __future__ import annotations

import re
from datetime import date

from sqlalchemy.orm import Session as OrmSession

from app.core.errors import Conflict, ValidationFailed
from app.models import PrivateTask
from app.modules.privat import rules, wish_images

THEMES: dict[str, dict] = {
    "jul":          {"accent": "#B3261E", "background": "#FBF6EE", "text": "#1F2A24", "font": "serif"},
    "foedselsdag":  {"accent": "#C2185B", "background": "#FFF8EC", "text": "#2A2233", "font": "rounded"},
    "bryllup":      {"accent": "#7A5C2E", "background": "#FAF7F2", "text": "#2E2A26", "font": "serif"},
    "konfirmation": {"accent": "#2F5D9E", "background": "#F3F6FB", "text": "#1E2A3A", "font": "outfit"},
    "barnedaab":    {"accent": "#2F7470", "background": "#F1F7F6", "text": "#22343A", "font": "rounded"},
    "babyshower":   {"accent": "#6A4FB0", "background": "#F7F4FC", "text": "#2D2740", "font": "rounded"},
    "student":      {"accent": "#B0102A", "background": "#F5F6F8", "text": "#14213D", "font": "outfit"},
    "jubilaeum":    {"accent": "#7D6214", "background": "#F8F5EC", "text": "#2B2618", "font": "serif"},
    "indflytning":  {"accent": "#3F6B2E", "background": "#F3F5EF", "text": "#24301F", "font": "inter"},
    "neutral":      {"accent": "#2456F6", "background": "#FFFFFF", "text": "#1A1A1A", "font": "outfit"},
}
DEFAULT_THEME = "neutral"
FONTS = ("outfit", "inter", "serif", "rounded")
HEX = re.compile(r"^#[0-9A-Fa-f]{6}$")
COLOR_KEYS = ("accent", "background", "text")


def _lum(h: str) -> float:
    r, g, b = (int(h[i:i + 2], 16) / 255 for i in (1, 3, 5))

    def f(c: float) -> float:
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b)


def contrast(a: str, b: str) -> float:
    x, y = sorted((_lum(a), _lum(b)), reverse=True)
    return (x + 0.05) / (y + 0.05)


def _bad(field: str, msg: str) -> ValidationFailed:
    return ValidationFailed(msg, field_errors=[{"field": field, "message": msg}])


def resolved(design: dict | None) -> dict:
    """The design as everybody sees it: the theme's values with the owner's overrides on top (+ signed cover links)."""
    d = design or {}
    theme = d.get("theme") if d.get("theme") in THEMES else DEFAULT_THEME
    base = THEMES[theme]
    cover = d.get("cover") if isinstance(d.get("cover"), dict) else None
    links = wish_images.urls(cover.get("key")) if cover else None
    return {"theme": theme, **{k: d.get(k) or base[k] for k in (*COLOR_KEYS, "font")},
            "decorations": d.get("decorations") if isinstance(d.get("decorations"), bool) else True,
            "subtitle": d.get("subtitle") or None, "date": d.get("date") or None,
            "cover": ({"key": cover.get("key"), "url": links["url"], "url_sm": links["url_sm"], "zoom": cover.get("zoom", 1),
                       "x": cover.get("x", 50), "y": cover.get("y", 50)} if links else None),
            "overrides": sorted(k for k in (*COLOR_KEYS, "font") if d.get(k)),
            "customized": design is not None}


def validate(task: PrivateTask, body: dict) -> dict:
    theme = body.get("theme")
    if theme not in THEMES:
        raise _bad("theme", "Vælg et af temaerne")
    out: dict = {"theme": theme}
    for k in COLOR_KEYS:
        v = body.get(k)
        if v in (None, ""):
            continue
        if not isinstance(v, str) or not HEX.match(v):
            raise _bad(k, "Farven skal være en farvekode som #1A2B3C")
        out[k] = v.upper()
    font = body.get("font")
    if font not in (None, ""):
        if font not in FONTS:
            raise _bad("font", "Vælg en af skrifterne")
        out["font"] = font
    if body.get("decorations") is not None:
        out["decorations"] = bool(body["decorations"])
    sub = " ".join(str(body.get("subtitle") or "").split())[:160]
    if sub:
        out["subtitle"] = sub
    if body.get("date"):
        try:
            out["date"] = date.fromisoformat(str(body["date"])).isoformat()
        except ValueError as e:
            raise _bad("date", "Datoen skal være en gyldig dato") from e
    cover = body.get("cover")
    if cover:
        key = cover.get("key")
        if not wish_images.owns(task.workspace_id, key, "cover"):
            raise _bad("cover", "Coverbilledet findes ikke – upload det igen")
        try:
            zoom = min(3.0, max(1.0, float(cover.get("zoom", 1))))
            x = min(100.0, max(0.0, float(cover.get("x", 50))))
            y = min(100.0, max(0.0, float(cover.get("y", 50))))
        except (TypeError, ValueError) as e:
            raise _bad("cover", "Ugyldig beskæring") from e
        out["cover"] = {"key": key, "zoom": round(zoom, 2), "x": round(x, 1), "y": round(y, 1)}
    r = THEMES[theme] | {k: out[k] for k in COLOR_KEYS if k in out}
    if contrast(r["text"], r["background"]) < 4.5:
        raise _bad("text", "Teksten er svær at læse på baggrunden – vælg en mørkere tekst eller lysere baggrund")
    if contrast("#FFFFFF", r["accent"]) < 4.5:
        raise _bad("accent", "Accentfarven er for lys til knapper med hvid tekst – vælg en mørkere farve")
    if contrast(r["accent"], r["background"]) < 3:
        raise _bad("accent", "Accentfarven skiller sig ikke nok ud fra baggrunden")
    return out


def save(db: OrmSession, task: PrivateTask, body: dict | None, *, title: str | None = None) -> None:
    """Owner only (the caller checks). body None = back to the default theme (design only – items stay)."""
    if task.kind != "list" or task.list_type != "wishlist":
        raise Conflict("Kun ønskelister har et design", code="not_a_wishlist")
    old_cover = ((task.design or {}).get("cover") or {}).get("key")
    task.design = validate(task, body) if body is not None else None
    new_cover = ((task.design or {}).get("cover") or {}).get("key")
    if title is not None:
        t = " ".join(title.split())[:300]
        if not t:
            raise _bad("title", "Ønskesedlen skal have en titel")
        task.title = t
    if old_cover and old_cover != new_cover:
        wish_images.delete(old_cover)
    task.updated_at = rules.now()
