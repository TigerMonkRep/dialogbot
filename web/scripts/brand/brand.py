"""Pillow helpers for the Dialogbot "Byggevejledning" brand: colours, fonts, mark, step squares, chips, blocks."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

SCRATCH = Path(__file__).resolve().parent / ".build"  # fonts/ and mark-2048.png (see README)
FONTS = SCRATCH / "fonts"
MARK_PNG = SCRATCH / "mark-2048.png"

INK = (20, 33, 61)
INK_SOFT = (60, 70, 89)
PAPER = (255, 255, 255)
PANEL = (238, 244, 251)
LINE = (214, 222, 234)
MUTED = (91, 100, 117)
ACCENT = (36, 86, 246)
ACCENT_DARK = (26, 63, 192)
ACCENT_LIGHT = (220, 230, 255)
HIGHLIGHT = (255, 207, 63)
WHITE = (255, 255, 255)


@lru_cache(maxsize=64)
def font(name: str, size: int) -> ImageFont.FreeTypeFont:
    """name: Outfit-ExtraBold, Outfit-Bold, Inter-SemiBold, Inter-Medium, Inter-Regular."""
    return ImageFont.truetype(str(FONTS / f"{name}.ttf"), size)


@lru_cache(maxsize=1)
def _mark_src() -> Image.Image:
    return Image.open(MARK_PNG).convert("RGBA")


def mark(size: int) -> Image.Image:
    """The blue mark (rounded square + bubble) at `size` px, RGBA with transparent corners."""
    return _mark_src().resize((size, size), Image.LANCZOS)


def paste_mark(img: Image.Image, xy: tuple[int, int], size: int) -> None:
    m = mark(size)
    img.paste(m, xy, m)


def text_tracked(d: ImageDraw.ImageDraw, xy, text: str, f: ImageFont.FreeTypeFont, fill, tracking: float = 0.0,
                 anchor: str = "ls") -> float:
    """Draw text with letter-spacing (Pillow has none). Anchor: 'ls' (left/baseline) or 'lm'. Returns width."""
    x, y = xy
    width = sum(d.textlength(ch, font=f) for ch in text) + tracking * (len(text) - 1)
    for ch in text:
        d.text((x, y), ch, font=f, fill=fill, anchor=anchor)
        x += d.textlength(ch, font=f) + tracking
    return width


def brand_row(img: Image.Image, d: ImageDraw.ImageDraw, x: int, y: int, size: int = 56, ink=INK,
              wordmark: bool = True) -> int:
    """Mark + «Dialogbot» in Outfit 800 (cap height centred on the mark). Returns total width."""
    paste_mark(img, (x, y), size)
    if not wordmark:
        return size
    fs = int(size * 0.92)
    f = font("Outfit-ExtraBold", fs)
    gap = int(size * 0.29)
    baseline = y + size / 2 + 0.70 * fs / 2
    w = text_tracked(d, (x + size + gap, baseline), "Dialogbot", f, ink, tracking=-0.3 * fs / 22)
    return int(size + gap + w)


def step_square(d: ImageDraw.ImageDraw, xy: tuple[int, int], side: int, label: str, fill=HIGHLIGHT, ink=INK,
                outline=None) -> None:
    """Yellow rounded square with an Outfit 800 numeral (56 px → radius 14, font 30)."""
    x, y = xy
    d.rounded_rectangle((x, y, x + side, y + side), radius=side // 4, fill=fill,
                        outline=outline, width=max(2, side // 28) if outline else 0)
    f = font("Outfit-ExtraBold", int(side * 0.54))
    d.text((x + side / 2, y + side / 2 + side * 0.02), label, font=f, fill=ink, anchor="mm")


def card(d: ImageDraw.ImageDraw, box, radius: int = 20, fill=PAPER, ink=INK, border: int = 2,
         block_shadow: bool = False) -> None:
    """2 px ink-outlined card, optionally with the solid 8 px block shadow (scaled with the border)."""
    x0, y0, x1, y1 = box
    if block_shadow:
        off = border * 4
        d.rounded_rectangle((x0 + off, y0 + off, x1 + off, y1 + off), radius=radius, fill=ink)
    d.rounded_rectangle(box, radius=radius, fill=fill, outline=ink, width=border)


def chip(d: ImageDraw.ImageDraw, xy: tuple[int, int], count: str, label: str, size: int = 28, fill=PANEL,
         ink=INK) -> int:
    """«1× telefonnummer» chip. Returns its width."""
    x, y = xy
    fb, fl = font("Outfit-ExtraBold", size), font("Inter-Medium", size)
    pad_x, pad_y, gap = int(size * 0.7), int(size * 0.45), int(size * 0.5)
    wb, wl = d.textlength(count, font=fb), d.textlength(label, font=fl)
    h = size + 2 * pad_y
    w = int(pad_x * 2 + wb + gap + wl)
    d.rounded_rectangle((x, y, x + w, y + h), radius=int(size * 0.5), fill=fill)
    d.text((x + pad_x, y + h / 2), count, font=fb, fill=ink, anchor="lm")
    d.text((x + pad_x + wb + gap, y + h / 2), label, font=fl, fill=ink, anchor="lm")
    return w


def eyebrow(d: ImageDraw.ImageDraw, xy, text: str, size: int = 13, fill=MUTED, anchor: str = "ls") -> float:
    return text_tracked(d, xy, text.upper(), font("Inter-SemiBold", size), fill, tracking=0.12 * size, anchor=anchor)


def arrow(d: ImageDraw.ImageDraw, x: int, y: int, length: int, ink=INK, width: int = 3, head: int = 10,
          direction: int = 1) -> None:
    """Flat black arrow «→» (direction 1) or «←» (−1) with round joins."""
    x2 = x + length * direction
    d.line((x, y, x2, y), fill=ink, width=width)
    d.line((x2 - head * direction, y - head, x2, y), fill=ink, width=width)
    d.line((x2 - head * direction, y + head, x2, y), fill=ink, width=width)
    r = width / 2
    for px, py in ((x, y), (x2, y), (x2 - head * direction, y - head), (x2 - head * direction, y + head)):
        d.ellipse((px - r, py - r, px + r, py + r), fill=ink)


def block(d: ImageDraw.ImageDraw, box, fill=ACCENT, radius: int | None = None, outline=None, width: int = 0):
    """A flat rounded building block (no studs)."""
    x0, y0, x1, y1 = box
    r = radius if radius is not None else min(x1 - x0, y1 - y0) // 4
    d.rounded_rectangle(box, radius=r, fill=fill, outline=outline, width=width)


def parts_motif(d: ImageDraw.ImageDraw, x: int, y: int, unit: int = 44, ink=INK) -> int:
    """The «parts box» motif from the style sheet: blue block + nub, arrow, yellow block. Returns width."""
    bw, bh = int(unit * 1.8), unit
    block(d, (x, y, x + bw, y + bh), ACCENT, radius=int(unit * 0.27))
    nub = int(unit * 0.32)
    d.rounded_rectangle((x + bw - 2, y, x + bw + nub, y + bh), radius=int(unit * 0.18), fill=ACCENT)
    d.rectangle((x + bw - 2, y, x + bw + 2, y + bh), fill=ACCENT)
    ax = x + bw + nub + int(unit * 0.35)
    alen = int(unit * 0.8)
    arrow(d, ax, y + bh // 2, alen, ink, width=max(3, unit // 14), head=int(unit * 0.22))
    bx = ax + alen + int(unit * 0.35)
    block(d, (bx, y, bx + bw, y + bh), HIGHLIGHT, radius=int(unit * 0.27))
    return bx + bw - x


def wrap(d: ImageDraw.ImageDraw, text: str, f: ImageFont.FreeTypeFont, max_w: int) -> list[str]:
    lines, cur = [], ""
    for word in text.split():
        trial = f"{cur} {word}".strip()
        if d.textlength(trial, font=f) <= max_w or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines


def headline(d: ImageDraw.ImageDraw, xy, text: str, size: int, max_w: int, fill=INK, spacing: float = 1.04,
             tracking: float | None = None, name: str = "Outfit-ExtraBold") -> int:
    """Outfit 800 headline, wrapped, letter-spacing −1 px at display sizes. Returns y below the block."""
    f = font(name, size)
    tr = tracking if tracking is not None else (-1.0 * size / 56 if size >= 32 else 0)
    x, y = xy
    for ln in [l for para in text.split("\n") for l in wrap(d, para, f, max_w)]:
        text_tracked(d, (x, y + size * 0.78), ln, f, fill, tracking=tr, anchor="ls")
        y += int(size * spacing)
    return y


def body(d: ImageDraw.ImageDraw, xy, text: str, size: int, max_w: int, fill=INK_SOFT, spacing: float = 1.5,
         name: str = "Inter-Regular") -> int:
    f = font(name, size)
    x, y = xy
    for ln in wrap(d, text, f, max_w):
        d.text((x, y), ln, font=f, fill=fill)
        y += int(size * spacing)
    return y


def button(d: ImageDraw.ImageDraw, xy, text: str, size: int = 17, fill=ACCENT, ink=WHITE, pad=(22, 0),
           height: int | None = None, radius: int = 14, name: str = "Inter-SemiBold") -> tuple[int, int]:
    """Primary button shape (radius 14, min height 52 at 17 px). Returns (width, height)."""
    f = font(name, size)
    x, y = xy
    h = height or int(size * 3.05)
    w = int(d.textlength(text, font=f) + 2 * pad[0])
    d.rounded_rectangle((x, y, x + w, y + h), radius=radius, fill=fill)
    d.text((x + w / 2, y + h / 2), text, font=f, fill=ink, anchor="mm")
    return w, h


def new(size: tuple[int, int], bg=PAPER) -> tuple[Image.Image, ImageDraw.ImageDraw]:
    img = Image.new("RGB", size, bg)
    return img, ImageDraw.Draw(img)
