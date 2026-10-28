"""Generates every raster brand asset: logos, app icons, OG image, social profile kit and post examples."""
from __future__ import annotations

import shutil
from pathlib import Path

from PIL import Image, ImageDraw

import brand as B
from brand import (ACCENT, HIGHLIGHT, INK, INK_SOFT, LINE, MUTED, PANEL, PAPER, WHITE, ACCENT_LIGHT, font, new,
                   paste_mark, step_square, card, chip, eyebrow, parts_motif, headline, body, button, brand_row,
                   text_tracked, arrow)

REPO = Path(__file__).resolve().parents[3]
BRAND = REPO / "web/public/brand"
SOCIAL = BRAND / "social"
ICONS = REPO / "web/public/icons"
APP = REPO / "web/src/app"
KIT = B.SCRATCH / "brandkit"  # review copies of the social kit
SOCIAL.mkdir(exist_ok=True)
KIT.mkdir(exist_ok=True)

HEAD = "Din AI-receptionist –\npå dansk, døgnet rundt"
CONTACT = "dialogbot.dk · 93 70 34 33"


def save(img: Image.Image, path: Path, also_kit: bool = False, **kw) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path, optimize=True, **kw)
    if also_kit:
        shutil.copy(path, KIT / path.name)
    print(f"{path.relative_to(REPO) if path.is_relative_to(REPO) else path}  {img.size[0]}x{img.size[1]}")


def mark_on(size: int, bg, pad_frac: float, mode: str = "RGB") -> Image.Image:
    img = Image.new("RGBA", (size, size), bg + (255,) if bg else (0, 0, 0, 0))
    inner = int(size * (1 - 2 * pad_frac))
    off = (size - inner) // 2
    paste_mark(img, (off, off), inner)
    return img.convert(mode)


def full_square(size: int, bubble_frac: float = 0.55) -> Image.Image:
    """Blue square without rounded corners (the platform masks it) with the bubble at bubble_frac of the side."""
    img = Image.new("RGBA", (size, size), ACCENT + (255,))  # RGBA: Next.js's image loader rejects RGB PNGs
    # the mark's bubble occupies 55 % of the mark side: scale the mark so its bubble is bubble_frac of `size`
    m_side = int(size * bubble_frac / 0.55)
    src = B._mark_src()
    c0, c1 = int(src.width * 0.19), int(src.width * 0.81)          # the bubble sits well inside this crop
    inner = src.crop((c0, c0, c1, c1)).resize((int(m_side * 0.62), int(m_side * 0.62)), Image.LANCZOS)
    off = (size - inner.width) // 2
    img.paste(inner, (off, off), inner)
    return img


# ---------------------------------------------------------------- A. logos
def logos() -> None:
    save(B.mark(1024), BRAND / "logo-mark-1024.png", also_kit=True)
    save(mark_on(720, PAPER, 0.12), BRAND / "logo-720.png", also_kit=True)


# ---------------------------------------------------------------- B. icons + OG
def icons() -> None:
    save(B.mark(512).convert("RGBA"), APP / "icon.png")
    save(full_square(180).convert("RGBA"), APP / "apple-icon.png")
    ico = full_square(256).convert("RGBA")
    ico.save(APP / "favicon.ico", format="ICO", sizes=[(16, 16), (32, 32), (48, 48)])
    print("web/src/app/favicon.ico  16/32/48")
    save(B.mark(192), ICONS / "icon-192.png")
    save(B.mark(512), ICONS / "icon-512.png")
    save(full_square(512, bubble_frac=0.42), ICONS / "icon-maskable-512.png")


def og_image() -> None:
    img, d = new((1200, 630), PANEL)
    m = 72
    # step square + eyebrow
    step_square(d, (m, m), 72, "1")
    eyebrow(d, (m + 72 + 24, m + 30), "Byggevejledning · Trin 1 af 3", size=18, anchor="ls")
    d.text((m + 72 + 24, m + 44), "Én handling pr. trin. Ingen manual.", font=font("Inter-Regular", 20), fill=INK_SOFT)
    y = headline(d, (m, 190), "Byg din egen AI-receptionist. Trin for trin.", 72, 1200 - 2 * m - 60, spacing=1.02)
    # parts motif in a card with block shadow (right side under the headline)
    cx0, cy0 = 1200 - m - 420, y + 10
    card(d, (cx0, cy0, 1200 - m, cy0 + 176), radius=20, block_shadow=True)
    eyebrow(d, (cx0 + 24, cy0 + 40), "Du skal bruge", size=14)
    chip(d, (cx0 + 24, cy0 + 56), "1×", "telefonnummer", size=22)
    parts_motif(d, cx0 + 24, cy0 + 118, unit=32)
    # logo bottom-left
    brand_row(img, d, m, 630 - m - 56, 56)
    d.text((1200 - m, 630 - m - 28), CONTACT, font=font("Inter-SemiBold", 22), fill=MUTED, anchor="rm")
    save(img.convert("RGBA"), APP / "opengraph-image.png", also_kit=True)
    save(img.convert("RGBA"), APP / "twitter-image.png")


# ---------------------------------------------------------------- A. cover + foto equivalents
def steps_123(d, x, y, side=56, gap=None, ink=INK):
    gap = gap or int(side * 0.8)
    for i in range(3):
        step_square(d, (x, y), side, str(i + 1))
        x += side
        if i < 2:
            arrow(d, x + int(gap * 0.2), y + side // 2, int(gap * 0.6), ink, width=max(3, side // 16),
                  head=int(side * 0.2))
            x += gap
    return x


def cover_generic(size, bg, ink, sub_ink, pad, head_size, kit_name=None, safe=None, logo_size=56):
    """Panel/ink cover: headline, 1→2→3 motif, contact line. `safe` = (x0, y0, x1, y1) box to stay inside."""
    w, h = size
    img, d = new(size, bg)
    x0, y0, x1, y1 = safe or (pad, pad, w - pad, h - pad)
    steps_123(d, x0, y0, side=int(head_size * 0.9), ink=ink)
    y = y0 + int(head_size * 0.9) + int(head_size * 0.5)
    y = headline(d, (x0, y), HEAD, head_size, x1 - x0, fill=ink, spacing=1.02)
    d.text((x0, y + int(head_size * 0.25)), "Tager telefonen, booker tider og svarer på hjemmesiden – vi sætter den op sammen med dig.",
           font=font("Inter-Regular", int(head_size * 0.36)), fill=sub_ink)
    brand_row(img, d, x0, y1 - logo_size, logo_size, ink=ink)
    d.text((x1, y1 - logo_size // 2), CONTACT, font=font("Inter-SemiBold", int(logo_size * 0.42)), fill=sub_ink,
           anchor="rm")
    return img


def covers() -> None:
    # Google Business cover 1024x576 (also replaces the old brand/cover-1024x576.png)
    g = cover_generic((1024, 576), PANEL, INK, INK_SOFT, 72, 56)
    save(g, SOCIAL / "cover-google-1024x576.png", also_kit=True)
    save(g, BRAND / "cover-1024x576.png")
    # Facebook 1640x624: mobile shows the central 1250 px — keep everything inside it
    fb = cover_generic((1640, 624), INK, WHITE, ACCENT_LIGHT, 0, 60, safe=(260, 72, 1640 - 260, 624 - 72))
    save(fb, SOCIAL / "cover-facebook-1640x624.png", also_kit=True)
    # LinkedIn 1584x396: the profile picture sits bottom-left — keep text in the right part and top
    img, d = new((1584, 396), PANEL)
    x0 = 470
    steps_123(d, x0, 56, side=48)
    y = headline(d, (x0, 136), HEAD, 52, 1584 - x0 - 64, spacing=1.02)
    d.text((x0, y + 10), "Tager telefonen, booker tider og svarer på hjemmesiden.", font=font("Inter-Regular", 20),
           fill=INK_SOFT)
    d.text((1584 - 64, 396 - 44), CONTACT, font=font("Inter-SemiBold", 20), fill=MUTED, anchor="rm")
    brand_row(img, d, 1584 - 64 - 232, 44, 44)
    save(img, SOCIAL / "cover-linkedin-1584x396.png", also_kit=True)
    # TikTok story 1080x1920: top 250 / bottom 400 / right 120 are covered by the UI
    img, d = new((1080, 1920), INK)
    x0, y0, x1, y1 = 84, 300, 1080 - 84 - 120, 1920 - 420
    steps_123(d, x0, y0, side=96, ink=WHITE)
    y = headline(d, (x0, y0 + 96 + 72), HEAD, 78, x1 - x0, fill=WHITE, spacing=1.02)
    y = body(d, (x0, y + 36), "Tager telefonen, booker tider og svarer på hjemmesiden – døgnet rundt.", 40, x1 - x0,
             fill=ACCENT_LIGHT, spacing=1.35)
    button(d, (x0, y + 48), "Prøv den – den ringer til dig", size=36, fill=HIGHLIGHT, ink=INK, pad=(44, 0), height=112,
           radius=28, name="Outfit-Bold")
    brand_row(img, d, x0, y1 - 72, 72, ink=WHITE)
    d.text((x0, y1 + 40), CONTACT, font=font("Inter-SemiBold", 34), fill=ACCENT_LIGHT, anchor="ls")
    save(img, SOCIAL / "cover-tiktok-1080x1920-story.png", also_kit=True)


def profile() -> None:
    save(mark_on(1024, PAPER, 0.12), SOCIAL / "profile-1024.png", also_kit=True)


def fotos() -> None:
    """Flat replacements for the old green «foto» panels (features, prices) in the new style."""
    # funktioner: paper, eyebrow, headline, 6 outlined rows with blue icon tiles
    img, d = new((1200, 900), PANEL)
    m = 80
    eyebrow(d, (m, m + 14), "Det kan Dialogbot", size=16)
    y = headline(d, (m, m + 40), HEAD, 56, 1040, spacing=1.02)
    items = ["Tager telefonen, når I er optaget", "Svarer ud fra jeres egen viden", "Booker, flytter og aflyser tider",
             "Sender SMS-bekræftelse", "Chat på hjemmesiden", "Opsummering af hver henvendelse"]
    cw, ch, gap = 505, 100, 30
    top = y + 36
    for i, t in enumerate(items):
        cx = m + (i % 2) * (cw + gap)
        cy = top + (i // 2) * (ch + gap)
        card(d, (cx, cy, cx + cw, cy + ch), radius=16, fill=PAPER, border=2)
        step_square(d, (cx + 24, cy + 22), 56, str(i + 1))
        for j, ln in enumerate(B.wrap(d, t, font("Inter-SemiBold", 24), cw - 120)):
            d.text((cx + 100, cy + 36 + j * 30 - (12 if len(ln) and j == 0 and False else 0)), ln,
                   font=font("Inter-SemiBold", 24), fill=INK)
    foot_y = 900 - m - 40
    brand_row(img, d, m, foot_y - 8, 48)
    d.text((1200 - m, foot_y + 16), "Vi guider jer gennem hele opsætningen · www.dialogbot.dk",
           font=font("Inter-Regular", 22), fill=INK_SOFT, anchor="rm")
    save(img, BRAND / "foto-funktioner-1200x900.png")
    # priser: ink background, two cards (paper / yellow)
    img, d = new((1200, 900), INK)
    eyebrow(d, (m, m + 14), "To måder at betale på", size=16, fill=ACCENT_LIGHT)
    y = headline(d, (m, m + 40), "Vælg det, der passer jer", 60, 1040, fill=WHITE, spacing=1.02)
    top = y + 40
    for i, (title, price, sub, fill) in enumerate([
            ("Fast abonnement", "Fast pris", "pr. måned – alt inkluderet, ekskl. moms", PAPER),
            ("Kampagner", "Pr. opkald", "betal kun for udgående kampagneopkald", HIGHLIGHT)]):
        cx = m + i * (505 + 30)
        card(d, (cx, top, cx + 505, top + 300), radius=20, fill=fill, border=2, block_shadow=(i == 1))
        step_square(d, (cx + 32, top + 32), 48, "AB"[i], fill=INK if i == 1 else HIGHLIGHT, ink=HIGHLIGHT if i == 1 else INK)
        d.text((cx + 100, top + 56), title, font=font("Outfit-Bold", 28), fill=INK, anchor="lm")
        text_tracked(d, (cx + 32, top + 190), price, font("Outfit-ExtraBold", 76), INK, tracking=-1.4)
        for j, ln in enumerate(B.wrap(d, sub, font("Inter-Regular", 22), 440)):
            d.text((cx + 32, top + 220 + j * 30), ln, font=font("Inter-Regular", 22), fill=INK_SOFT)
    foot_y = 900 - m - 40
    brand_row(img, d, m, foot_y - 8, 48, ink=WHITE)
    d.text((1200 - m, foot_y + 16), "Hør den selv: bliv ringet op på www.dialogbot.dk",
           font=font("Inter-Regular", 22), fill=ACCENT_LIGHT, anchor="rm")
    save(img, BRAND / "foto-priser-1200x900.png")


# ---------------------------------------------------------------- C. post templates
def posts() -> None:
    m = 84
    # hook 1080x1080: ink, yellow step number, white Outfit headline
    img, d = new((1080, 1080), INK)
    brand_row(img, d, m, m, 84, ink=WHITE)
    step_square(d, (m, 300), 120, "1")
    y = headline(d, (m, 460), "Hvem tager telefonen, når I har travlt?", 92, 1080 - 2 * m, fill=WHITE, spacing=1.02)
    d.text((m, y + 40), "Trin 1 af 3 · Byggevejledningen", font=font("Inter-SemiBold", 30), fill=ACCENT_LIGHT)
    d.text((m, 1080 - m), "dialogbot.dk", font=font("Inter-SemiBold", 34), fill=ACCENT_LIGHT, anchor="ld")
    arrow(d, 1080 - m - 56, 1080 - m - 18, 56, WHITE, width=6, head=18)
    save(img, SOCIAL / "post-hook-1080x1080.png", also_kit=True)
    # point 1080x1350: paper, ink-outlined card, «Du skal bruge» box
    img, d = new((1080, 1350), PAPER)
    brand_row(img, d, m, m, 84)
    scratch = ImageDraw.Draw(Image.new("RGB", (10, 10)))
    parts = [("1×", "åbningstider"), ("1×", "prisliste"), ("3×", "typiske spørgsmål")]
    inner_w = 1080 - 2 * m - 88
    # lay the chips out first so the parts box gets the right height
    rows, cx, row = [], 0, []
    for c, l in parts:
        w = chip(scratch, (0, 0), c, l, size=30)
        if cx + w > inner_w - 56 and row:
            rows.append(row); row, cx = [], 0
        row.append((c, l, w)); cx += w + 16
    rows.append(row)
    box_h = 84 + len(rows) * (30 + 27 + 16) + 12
    content_h = 44 + 96 + 30 + 2 * 71 + 24 + 2 * 48 + 40 + box_h + 44
    card(d, (m, 230, 1080 - m, 230 + content_h), radius=24, fill=PAPER, border=3, block_shadow=True)
    step_square(d, (m + 44, 230 + 44), 96, "2")
    eyebrow(d, (m + 44 + 96 + 28, 230 + 44 + 60), "Trin 2 · Fortæl den om jer", size=24)
    y = headline(d, (m + 44, 400), "Giv den jeres åbningstider og priser", 68, inner_w, spacing=1.04)
    y = body(d, (m + 44, y + 24), "Receptionisten svarer kun på det, I har fortalt den. Kort og konkret er bedst.", 34,
             inner_w, spacing=1.4)
    bx0, by0 = m + 44, y + 40
    d.rounded_rectangle((bx0, by0, 1080 - m - 44, by0 + box_h), radius=18, fill=PAPER, outline=INK, width=2)
    eyebrow(d, (bx0 + 28, by0 + 52), "Du skal bruge", size=22)
    for r, row in enumerate(rows):
        cx = bx0 + 28
        for c, l, w in row:
            chip(d, (cx, by0 + 84 + r * (30 + 27 + 16)), c, l, size=30)
            cx += w + 16
    d.text((m, 1350 - m), "dialogbot.dk", font=font("Inter-SemiBold", 34), fill=INK, anchor="ld")
    d.text((1080 - m, 1350 - m), "2/3", font=font("Inter-SemiBold", 34), fill=INK, anchor="rd")
    save(img, SOCIAL / "post-point-1080x1350.png", also_kit=True)
    # cta 1080x1080: yellow, ink text, blue button pill
    img, d = new((1080, 1080), HIGHLIGHT)
    brand_row(img, d, m, m, 84)
    step_square(d, (m, 300), 120, "3", fill=INK, ink=HIGHLIGHT)
    y = headline(d, (m, 460), "Prøv den – den ringer til dig", 96, 1080 - 2 * m, spacing=1.02)
    y = body(d, (m, y + 24), "Indtast dit nummer, så ringer receptionisten op med det samme.", 34, 1080 - 2 * m,
             fill=INK, spacing=1.4)
    button(d, (m, y + 44), "dialogbot.dk", size=44, fill=ACCENT, ink=WHITE, pad=(52, 0), height=120, radius=30,
           name="Outfit-ExtraBold")
    d.text((1080 - m, 1080 - m), "93 70 34 33", font=font("Inter-SemiBold", 34), fill=INK, anchor="rd")
    save(img, SOCIAL / "post-cta-1080x1080.png", also_kit=True)


if __name__ == "__main__":
    logos()
    icons()
    og_image()
    profile()
    covers()
    fotos()
    posts()
