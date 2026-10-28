"""Draws the images of a post in Dialogbot's brand (ink, paper, block blue, step yellow, Outfit) with Pillow.

JPEG on purpose: Instagram's publishing API only accepts JPEG and TikTok photo posts accept JPEG/WEBP, not PNG.

Formats: Facebook 1080×1080 (one card), Instagram 1080×1350 (4:5 carousel), TikTok 1080×1920 (9:16 carousel; the
text stays out of the top and bottom bands and the right edge, where TikTok draws its own buttons and caption).
Three looks keep a carousel lively, all from docs/brand.md ("Byggevejledningen"):
  `hook`  – ink background, yellow kicker pill and step square, white Outfit headline;
  `point` – paper background, a 2 px ink-outlined card with the block shadow, yellow step number taken from the
            kicker ("2 / 3" → 2) and «1×» chips for any `parts` the slide lists;
  `cta`   – yellow background, ink text and the web address as a blue button.
No gradients, no soft shadows, no emoji (anything Outfit cannot draw is dropped).
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

INK, PAPER, PANEL = (20, 33, 61), (255, 255, 255), (238, 244, 251)
ACCENT, HIGHLIGHT = (36, 86, 246), (255, 207, 63)
MUTED, LINE, WHITE = (91, 100, 117), (214, 222, 234), (255, 255, 255)
ACCENT_LIGHT = (220, 230, 255)  # light text on ink

_emoji = re.compile("[\U00010000-\U0010ffff☀-➿️‍]")
_step = re.compile(r"^\s*(\d{1,2})\s*/\s*\d{1,2}\s*$")  # "2 / 3" kickers carry the step number


@lru_cache(maxsize=32)
def font(weight: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(ASSETS / f"Outfit-{weight}.ttf"), size)


@lru_cache(maxsize=1)
def _missing_glyph() -> tuple:
    m = font("Bold", 64).getmask("￿")
    return m.size, bytes(m)


def printable(text: str) -> str:
    """Drop what Outfit cannot draw (emoji, check marks, arrows) so no tofu boxes appear on an image."""
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
    return Image.open(ASSETS / "logo.png").convert("RGBA")


def _brand_row(img: Image.Image, d: ImageDraw.ImageDraw, x: int, y: int, ink, size: int = 84) -> None:
    """The mark and «Dialogbot» in Outfit 800 (the mark's PNG already has transparent rounded corners)."""
    mark = _logo().resize((size, size), Image.LANCZOS)
    img.paste(mark, (x, y), mark)
    d.text((x + size + 22, y + size // 2), "Dialogbot", font=font("ExtraBold", 40), fill=ink, anchor="lm")


def _pill(d, xy: tuple[int, int], text: str, f, fill, ink, pad: tuple[int, int] = (26, 14),
          outline=None, radius: int | None = None) -> int:
    """A pill (or, with `radius`, a button shape); returns its height."""
    w = int(d.textlength(text, font=f))
    h = f.size
    x, y = xy
    box = (x, y, x + w + 2 * pad[0], y + h + 2 * pad[1])
    d.rounded_rectangle(box, radius=radius if radius is not None else (h + 2 * pad[1]) // 2, fill=fill,
                        outline=outline, width=2 if outline else 0)
    d.text((x + pad[0], y + pad[1] + h // 2), text, font=f, fill=ink, anchor="lm")
    return h + 2 * pad[1]


def _step_square(d, xy: tuple[int, int], side: int, label: str, fill=HIGHLIGHT, ink=INK) -> None:
    """Yellow rounded square with an Outfit 800 numeral – the brand's step number."""
    x, y = xy
    d.rounded_rectangle((x, y, x + side, y + side), radius=side // 4, fill=fill)
    d.text((x + side / 2, y + side / 2 + side * 0.02), label, font=font("ExtraBold", int(side * 0.54)), fill=ink,
           anchor="mm")


def _chip(d, xy: tuple[int, int], count: str, label: str, size: int = 30, fill=PANEL, ink=INK) -> tuple[int, int]:
    """«1× åbningstider» chip; returns (width, height)."""
    x, y = xy
    fb, fl = font("ExtraBold", size), font("Bold", size)
    pad_x, pad_y, gap = int(size * 0.7), int(size * 0.45), int(size * 0.5)
    wb, wl = d.textlength(count, font=fb), d.textlength(label, font=fl)
    w, h = int(pad_x * 2 + wb + gap + wl), size + 2 * pad_y
    d.rounded_rectangle((x, y, x + w, y + h), radius=int(size * 0.45), fill=fill)
    d.text((x + pad_x, y + h / 2), count, font=fb, fill=ink, anchor="lm")
    d.text((x + pad_x + wb + gap, y + h / 2), label, font=fl, fill=ink, anchor="lm")
    return w, h


def _arrow(d, x: int, y: int, ink, size: int = 44) -> None:
    d.line((x, y, x + size, y), fill=ink, width=8)
    d.line((x + size - 22, y - 22, x + size, y), fill=ink, width=8)
    d.line((x + size - 22, y + 22, x + size, y), fill=ink, width=8)
    for px, py in ((x, y), (x + size, y), (x + size - 22, y - 22), (x + size - 22, y + 22)):
        d.ellipse((px - 4, py - 4, px + 4, py + 4), fill=ink)


def render_slide(platform: str, slide: dict, index: int = 0, total: int = 1) -> bytes:
    w, h = SIZES[platform]
    top_safe, bottom_safe, right_safe = SAFE[platform]
    role = slide.get("role", "point")
    bg, ink, soft = {"hook": (INK, WHITE, ACCENT_LIGHT), "point": (PAPER, INK, MUTED), "cta": (HIGHLIGHT, INK, INK)}[role]
    img = Image.new("RGB", (w, h), bg)
    d = ImageDraw.Draw(img)

    left, right = MARGIN, w - MARGIN - right_safe
    y0, y1 = MARGIN + top_safe, h - MARGIN - bottom_safe
    text_w = right - left

    # Brand row on top, URL line at the bottom of the safe area.
    _brand_row(img, d, left, y0, ink)
    d.text((left, y1), "dialogbot.dk", font=font("Bold", 34), fill=soft, anchor="ld")
    if total > 1:
        d.text((right, y1), f"{index + 1}/{total}", font=font("Bold", 34), fill=soft, anchor="rd")

    kicker = printable(slide.get("kicker", ""))
    title = printable(slide.get("title", ""))
    body = "" if role == "cta" else printable(slide.get("body", ""))  # the CTA's address is the button below
    button = printable(slide.get("body", "")).lower() if role == "cta" else ""
    bullets = [printable(b) for b in slide.get("bullets", [])]
    parts = [printable(p) for p in slide.get("parts", [])][:4]
    step = _step.match(kicker)
    number = step.group(1) if step else str(index + 1) if role != "cta" else None

    has_arrow = role == "hook" and platform != "facebook" and total > 1
    area_top, area_bottom = y0 + 84 + 70, y1 - 70 - (110 if has_arrow else 0)  # keep the swipe arrow clear
    title_start = 78 if bullets else (120 if platform == "tiktok" else 104) if role == "hook" else 92
    pad = 44 if role == "point" else 0  # the point card's inner padding
    inner_w = text_w - 2 * pad

    def paint(d: ImageDraw.ImageDraw, y: int) -> int:
        """Draw the text block from y; returns the y below it. Run once to measure and once to draw."""
        x = left + pad
        y += pad
        if role == "point":  # yellow step number top-left of the card, the kicker beside it as a label
            _step_square(d, (x, y), 72, number or "1")
            d.text((x + 72 + 24, y + 36), (kicker if not step else f"Trin {number}").upper(), font=font("Bold", 24),
                   fill=MUTED, anchor="lm")
            y += 72 + 40
        elif kicker:
            if role == "hook":
                y += _pill(d, (x, y), kicker.upper(), font("ExtraBold", 28), HIGHLIGHT, INK) + 44
            else:
                y += _pill(d, (x, y), kicker.upper(), font("ExtraBold", 28), INK, HIGHLIGHT) + 44
        avail = area_bottom - y - pad
        title_share = 0.36 if bullets else 0.52 if body else (0.8 if parts else 1.0)
        f, lines, lh = fit(d, title, "ExtraBold", inner_w, int(avail * title_share), start=title_start, minimum=46)
        for ln in lines:
            d.text((x, y), ln, font=f, fill=ink)
            y += lh
        y += 36
        if body:
            bf, blines, blh = fit(d, body, "Bold", inner_w, max(area_bottom - y - pad, 60), start=44, minimum=30,
                                  spacing=1.3)
            for ln in blines:
                d.text((x, y), ln, font=bf, fill=soft if role == "hook" else ink)
                y += blh
            y += 20
        for i, b in enumerate(bullets, 1):  # Facebook card: three numbered lines
            bf, blines, blh = fit(d, b, "Bold", inner_w - 80, 2 * 48, start=36, minimum=28, spacing=1.2)
            _step_square(d, (x, y + 2), 48, str(i))
            for ln in blines:
                d.text((x + 72, y + 4), ln, font=bf, fill=WHITE if role == "hook" else ink)
                y += blh
            y += 18
        if parts:  # «Du skal bruge» chips
            d.text((x, y + 12), "DU SKAL BRUGE", font=font("Bold", 22), fill=MUTED, anchor="lm")
            y += 44
            cx = x
            for p in parts:
                cw, chh = _chip(ImageDraw.Draw(Image.new("RGB", (8, 8))), (0, 0), "1×", p)
                if cx + cw > x + inner_w and cx > x:
                    cx, y = x, y + chh + 16
                _chip(d, (cx, y), "1×", p, fill=PANEL if role == "point" else PAPER)
                cx += cw + 16
            y += chh + 24
        if button:  # the web address as a blue button
            y += 24
            y += _pill(d, (x, y), button, font("ExtraBold", 44), ACCENT, WHITE, pad=(48, 30), radius=28)
        return y + pad

    scratch = ImageDraw.Draw(Image.new("RGB", (w, h)))
    used = paint(scratch, 0)
    top = area_top + max(0, (area_bottom - area_top - used) // 2)  # centred between brand row and footer
    if role == "point":  # the ink-outlined card with the block shadow behind the text
        box = (left, top, right, top + used)
        d.rounded_rectangle(tuple(v + 8 for v in box), radius=24, fill=INK)
        d.rounded_rectangle(box, radius=24, fill=PAPER, outline=INK, width=3)
    paint(d, top)
    if has_arrow:
        _arrow(d, right - 56, y1 - 150, HIGHLIGHT)

    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=92, subsampling=0, optimize=True)
    return buf.getvalue()


def render_post(platform: str, slides: list[dict]) -> list[tuple[bytes, int, int]]:
    w, h = SIZES[platform]
    return [(render_slide(platform, s, i, len(slides)), w, h) for i, s in enumerate(slides)]
