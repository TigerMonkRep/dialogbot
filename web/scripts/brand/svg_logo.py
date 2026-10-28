"""Hand-built brand SVGs: mark, wordmark (Outfit 800 outlines), full logo in ink and in white."""
from fontTools.ttLib import TTFont
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen

from pathlib import Path
FONTS = str(Path(__file__).resolve().parent / ".build/fonts")
OUT = str(Path(__file__).resolve().parents[2] / "public/brand")
BLUE, INK, WHITE = "#2456F6", "#14213D", "#FFFFFF"
BUBBLE = "M4 6a2 2 0 0 1 2-2h12a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H9l-5 4z"

def mark_group(x, y, side, bg=BLUE, fg=WHITE):
    """Rounded square (radius 28 %) with the chat bubble scaled to 55 % of the side, centred."""
    r = round(side * 0.28, 3)
    icon = side * 0.55
    s = icon / 24
    ox, oy = x + (side - icon) / 2, y + (side - icon) / 2
    return (f'<rect x="{x}" y="{y}" width="{side}" height="{side}" rx="{r}" fill="{bg}"/>'
            f'<path d="{BUBBLE}" transform="translate({ox:.3f} {oy:.3f}) scale({s:.5f})" fill="none" stroke="{fg}" '
            f'stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"/>')

def wordmark_path(text, size, x, baseline, tracking):
    """One SVG path for `text` set in Outfit ExtraBold at `size` px; returns (d, advance width)."""
    font = TTFont(f"{FONTS}/Outfit-ExtraBold.ttf")
    cmap, hmtx, gs = font.getBestCmap(), font["hmtx"], font.getGlyphSet()
    upm = font["head"].unitsPerEm
    k = size / upm
    pen = SVGPathPen(gs, ntos=lambda v: f"{v:.2f}".rstrip("0").rstrip("."))
    pos = x
    for ch in text:
        g = cmap[ord(ch)]
        gs[g].draw(TransformPen(pen, (k, 0, 0, -k, pos, baseline)))
        pos += hmtx[g][0] * k + tracking
    return pen.getCommands(), pos - tracking - x

def svg(w, h, body):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" role="img" '
            f'aria-label="Dialogbot">\n{body}\n</svg>\n')

def build():
    side = 48
    size = 44            # Outfit 800, tracking -0.3 px at 22 px → -0.6 at 44
    gap = 14
    d, adv = wordmark_path("Dialogbot", size, side + gap, 0, -0.6)
    # vertical: centre the cap height (Outfit cap ≈ 0.70 em) on the mark
    cap = 0.70 * size
    baseline = side / 2 + cap / 2
    d, adv = wordmark_path("Dialogbot", size, side + gap, baseline, -0.6)
    w = round(side + gap + adv + 1)
    h = round(baseline + 0.23 * size + 0.5)   # room for the descender of the g
    files = {
        "logo.svg": svg(w, h, mark_group(0, 0, side) + f'\n<path d="{d}" fill="{INK}"/>'),
        "logo-dark.svg": svg(w, h, mark_group(0, 0, side) + f'\n<path d="{d}" fill="{WHITE}"/>'),
        "logo-mark.svg": svg(side, side, mark_group(0, 0, side)),
    }
    d2, adv2 = wordmark_path("Dialogbot", size, 0, cap + 0.5, -0.6)
    files["logo-wordmark.svg"] = svg(round(adv2 + 1), round(cap + 1 + 0.23 * size), f'<path d="{d2}" fill="{INK}"/>')
    for name, content in files.items():
        with open(f"{OUT}/{name}", "w") as fh:
            fh.write(content)
        print(name, len(content), "bytes")

if __name__ == "__main__":
    build()
