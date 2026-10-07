"""Draws the images of a post in Dialogbot's brand (dark green, lime, Manrope) with Pillow.

JPEG on purpose: Instagram's publishing API only accepts JPEG and TikTok photo posts accept JPEG/WEBP, not PNG.

Formats: Facebook 1080×1080 (one card), Instagram 1080×1350 (4:5 carousel), TikTok 1080×1920 (9:16 carousel; the
text stays out of the top and bottom bands and the right edge, where TikTok draws its own buttons and caption).
Three looks keep a carousel lively: `hook` (dark), `point` (light) and `cta` (lime).
"""
from __future__ import annotations

import io
import re
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ASSETS = Path(__file__).parent / "assets"
SIZES = {"facebook": (1080, 1080), "instagram": (1080, 1350), "tiktok": (1080, 1920)}
# Per-platform keep-out zones (top, bottom, right) in pixels, beyond the normal margin.
SAFE = {"facebook": (0, 0, 0), "instagram": (0, 0, 0), "tiktok": (150, 330, 120)}
MARGIN = 84

DARK, LIGHT, LIME, MINT = (0, 54, 45), (231, 254, 249), (214, 236, 133), (155, 209, 195)
INK, WHITE, MUTED = (10, 31, 28), (255, 255, 255), (136, 190, 176)

_emoji = re.compile("[\U00010000-\U0010ffff☀-➿️‍]")


@lru_cache(maxsize=32)
def font(weight: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(ASSETS / f"Manrope-{weight}.ttf"), size)


@lru_cache(maxsize=1)
def _missing_glyph() -> tuple:
    m = font("Bold", 64).getmask("￿")
    return m.size, bytes(m)


def printable(text: str) -> str:
    """Drop what Manrope cannot draw (emoji, check marks, arrows) so no tofu boxes appear on an image."""
    f = font("Bold", 64)
    out = []
    for ch in _emoji.sub("", text):
        if ch.isspace() or (lambda m: (m.size, bytes(m)) != _missing_glyph())(f.getmask(ch)):
            out.append(ch)
    return " ".join("".join(out).split())


def wrap(draw: ImageDraw.ImageDraw, text: str, f: ImageFont.FreeTypeFont, max_w: int) -> list[str]:
    lines: list[str] = []
    cur = ""
    for word in text.split():
        trial = f"{cur} {word}".strip()
        if draw.textlength(trial, font=f) <= max_w or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines


def fit(draw, text: str, weight: str, max_w: int, max_h: int, start: int, minimum: int, spacing: float = 1.14):
    """Largest font size (start → minimum) whose wrapped text fits the box; returns (font, lines, line_height)."""
    size = start
    while True:
        f = font(weight, size)
        lines = wrap(draw, text, f, max_w)
        lh = int(size * spacing)
        widest = max((draw.textlength(ln, font=f) for ln in lines), default=0)
        if (len(lines) * lh <= max_h and widest <= max_w) or size <= minimum:
            if len(lines) * lh > max_h:  # still too tall at the minimum: cut with an ellipsis rather than overflow
                lines = lines[: max(1, max_h // lh)]
                lines[-1] = lines[-1].rstrip(" .,;:") + "…"
            return f, lines, lh
        size -= 4


@lru_cache(maxsize=1)
def _logo() -> Image.Image:
    return Image.open(ASSETS / "logo.png").convert("RGB")


def _brand_row(img: Image.Image, d: ImageDraw.ImageDraw, x: int, y: int, ink, size: int = 84) -> None:
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, size, size), radius=size // 4, fill=255)
    img.paste(_logo().resize((size, size), Image.LANCZOS), (x, y), mask)
    d.text((x + size + 22, y + size // 2), "Dialogbot", font=font("ExtraBold", 40), fill=ink, anchor="lm")


def _pill(d, xy: tuple[int, int], text: str, f, fill, ink, pad: tuple[int, int] = (26, 14)) -> int:
    w = int(d.textlength(text, font=f))
    h = f.size
    x, y = xy
    d.rounded_rectangle((x, y, x + w + 2 * pad[0], y + h + 2 * pad[1]), radius=(h + 2 * pad[1]) // 2, fill=fill)
    d.text((x + pad[0], y + pad[1] + h // 2), text, font=f, fill=ink, anchor="lm")
    return h + 2 * pad[1]


def _arrow(d, x: int, y: int, ink, size: int = 44) -> None:
    d.line((x, y, x + size, y), fill=ink, width=8)
    d.line((x + size - 22, y - 22, x + size, y), fill=ink, width=8)
    d.line((x + size - 22, y + 22, x + size, y), fill=ink, width=8)


def render_slide(platform: str, slide: dict, index: int = 0, total: int = 1) -> bytes:
    w, h = SIZES[platform]
    top_safe, bottom_safe, right_safe = SAFE[platform]
    role = slide.get("role", "point")
    bg, ink, accent = {"hook": (DARK, WHITE, LIME), "point": (LIGHT, DARK, DARK), "cta": (LIME, DARK, DARK)}[role]
    img = Image.new("RGB", (w, h), bg)
    d = ImageDraw.Draw(img)

    left, right = MARGIN, w - MARGIN - right_safe
    y0, y1 = MARGIN + top_safe, h - MARGIN - bottom_safe
    text_w = right - left

    # Brand row on top, URL line at the bottom of the safe area.
    _brand_row(img, d, left, y0, ink)
    d.text((left, y1), "dialogbot.dk", font=font("Bold", 34), fill=MUTED if role == "hook" else ink, anchor="ld")
    if total > 1:
        d.text((right, y1), f"{index + 1}/{total}", font=font("Bold", 34), fill=MUTED if role == "hook" else ink,
               anchor="rd")

    kicker = printable(slide.get("kicker", ""))
    title = printable(slide.get("title", ""))
    body = "" if role == "cta" else printable(slide.get("body", ""))  # the CTA's address is the button below
    button = printable(slide.get("body", "")).lower() if role == "cta" else ""
    bullets = [printable(b) for b in slide.get("bullets", [])]

    has_arrow = role == "hook" and platform != "facebook" and total > 1
    area_top, area_bottom = y0 + 84 + 70, y1 - 70 - (110 if has_arrow else 0)  # keep the swipe arrow clear
    title_start = 78 if bullets else (120 if platform == "tiktok" else 104) if role == "hook" else 92

    def paint(d: ImageDraw.ImageDraw, y: int) -> int:
        """Draw the text block from y; returns the y below it. Run once to measure and once to draw."""
        if kicker:
            pill_fill, pill_ink = (LIME, DARK) if role == "hook" else (DARK, LIME)
            y += _pill(d, (left, y), kicker.upper(), font("ExtraBold", 28), pill_fill, pill_ink) + 44
        avail = area_bottom - y
        title_share = 0.36 if bullets else 0.52 if body else 1.0
        f, lines, lh = fit(d, title, "ExtraBold", text_w, int(avail * title_share), start=title_start, minimum=46)
        for ln in lines:
            d.text((left, y), ln, font=f, fill=ink)
            y += lh
        y += 36
        if role == "point":  # an accent bar under the headline
            d.rounded_rectangle((left, y, left + 160, y + 14), radius=7, fill=(155, 190, 40))
            y += 14 + 36
        if body:
            bf, blines, blh = fit(d, body, "Bold", text_w, max(area_bottom - y, 60), start=44, minimum=30, spacing=1.3)
            for ln in blines:
                d.text((left, y), ln, font=bf, fill=MINT if role == "hook" else ink)
                y += blh
            y += 20
        for b in bullets:  # Facebook card: three checked lines
            bf, blines, blh = fit(d, b, "Bold", text_w - 80, 2 * 48, start=36, minimum=28, spacing=1.2)
            d.ellipse((left, y + 6, left + 44, y + 50), fill=LIME)
            d.line((left + 11, y + 29, left + 20, y + 38), fill=DARK, width=7)
            d.line((left + 20, y + 38, left + 34, y + 18), fill=DARK, width=7)
            for ln in blines:
                d.text((left + 72, y), ln, font=bf, fill=WHITE)
                y += blh
            y += 18
        if button:  # the web address as a dark button
            y += 24
            y += _pill(d, (left, y), button, font("ExtraBold", 44), DARK, LIME, pad=(40, 26))
        return y

    scratch = ImageDraw.Draw(Image.new("RGB", (w, h)))
    used = paint(scratch, 0)
    paint(d, area_top + max(0, (area_bottom - area_top - used) // 2))  # centred between brand row and footer
    if has_arrow:
        _arrow(d, right - 56, y1 - 150, LIME)

    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=92, subsampling=0, optimize=True)
    return buf.getvalue()


def render_post(platform: str, slides: list[dict]) -> list[tuple[bytes, int, int]]:
    w, h = SIZES[platform]
    return [(render_slide(platform, s, i, len(slides)), w, h) for i, s in enumerate(slides)]
