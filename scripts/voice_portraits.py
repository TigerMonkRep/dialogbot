"""Draw an illustrated portrait (SVG) for every designed voice in voice_pipeline/designed/catalog.json.

python -m scripts.voice_portraits  → web/public/voices/designed/<slug>.svg

The look follows the voice's registered group only (gender, age band, region): hair, grey hair and glasses for 55+,
and a background colour per region. They are illustrations, not likenesses of the NST speakers.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "web/public/voices/designed"
BG = {"kbh": ("#d6ec85", "#e7fef9"), "oestjylland": ("#b6eede", "#e7fef9"), "nordjylland": ("#c6e7ff", "#eef8ff"),
      "vestjylland": ("#f3e2b8", "#fff7e2"), "soenderjylland": ("#f6d0c4", "#fff0ea"), "fyn": ("#d9d2f5", "#f3f0ff"),
      "sjaelland": ("#cfe8c0", "#f0fbe9"), "jylland": ("#f3e2b8", "#fff7e2"), "oerne": ("#c6e7ff", "#eef8ff")}
SKIN = ["#f2c7a5", "#ebb994", "#e0a982", "#f5d0b5"]
HAIR_YOUNG = ["#3b2a20", "#7a4a2a", "#c9952e", "#5b3a1e", "#a0632f"]
HAIR_MID = ["#4a3426", "#6b4a33", "#8b6a4a", "#3b2a20"]
GREY = ["#c9c6c0", "#b5b2ac", "#dedbd5"]
SHIRT = ["#164e43", "#00362d", "#33675c", "#184f44"]


def pick(options: list[str], slug: str, salt: str) -> str:
    return options[int(hashlib.sha256((slug + salt).encode()).hexdigest(), 16) % len(options)]


def portrait(slug: str, name: str) -> str:
    female, region = "kvinde" in slug, slug.split("-")[2]
    old, young = slug.endswith("55-90"), slug.endswith("18-34")
    bg, glow = BG.get(region, BG["kbh"])
    skin = pick(SKIN, slug, "s")
    hair = pick(GREY, slug, "h") if old else pick(HAIR_YOUNG if young else HAIR_MID, slug, "h")
    shirt = pick(SHIRT, slug, "c")
    collar = "#e7fef9" if female else "#d6ec85"
    p = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 240 240" role="img" aria-label="{name}">',
         f'<defs><clipPath id="c-{slug}"><rect width="240" height="240" rx="48"/></clipPath></defs>',
         f'<g clip-path="url(#c-{slug})"><rect width="240" height="240" fill="{bg}"/>',
         f'<circle cx="{196 if female else 44}" cy="44" r="70" fill="{glow}" opacity=".6"/>']
    if female:
        if young or pick(["long", "bob"], slug, "f") == "long":
            p.append(f'<path d="M62 128c-6-58 22-92 58-92s64 34 58 92c-2 22 4 44 10 60H52c6-16 12-38 10-60z" fill="{hair}"/>')
        else:
            p.append(f'<path d="M70 124c-6-50 18-84 50-84s56 34 50 84c-1 10 0 18 4 26H66c4-8 5-16 4-26z" fill="{hair}"/>')
    p += [f'<path d="M36 240c4-44 40-64 84-64s80 20 84 64z" fill="{shirt}"/>',
          f'<path d="M101 177h38l-19 24z" fill="{collar}"/>',
          f'<rect x="105" y="148" width="30" height="34" rx="12" fill="{skin}" style="filter:brightness(.93)"/>',
          f'<ellipse cx="120" cy="115" rx="40" ry="46" fill="{skin}"/>']
    if not female and pick(["beard", "none", "none"], slug, "b") == "beard":
        p.append(f'<path d="M82 120c2 30 18 46 38 46s36-16 38-46c-8 12-22 18-38 18s-30-6-38-18z" fill="{hair}" opacity=".9"/>')
    if female:
        p.append(f'<path d="M78 110c2-40 26-60 46-60 26 0 44 22 40 52-14-20-38-30-60-30-10 12-18 24-26 38z" fill="{hair}"/>')
    elif old and pick(["bald", "hair"], slug, "o") == "bald":
        p.append(f'<path d="M82 112c-2-16 2-26 8-32-2 12-2 22 0 32zM158 112c2-16-2-26-8-32 2 12 2 22 0 32z" fill="{hair}"/>')
    else:
        p.append(f'<path d="M80 104c-4-36 16-56 42-56 28 0 44 20 40 54-8-16-22-24-40-24-18 0-32 8-42 26z" fill="{hair}"/>')
    p += ['<circle cx="104" cy="116" r="4.5" fill="#00362d"/><circle cx="136" cy="116" r="4.5" fill="#00362d"/>',
          '<path d="M107 136c8 7 18 7 26 0" stroke="#00362d" stroke-width="4" fill="none" stroke-linecap="round"/>']
    if old:
        p.append('<g stroke="#00362d" stroke-width="3" fill="none"><circle cx="104" cy="116" r="11"/>'
                 '<circle cx="136" cy="116" r="11"/><path d="M115 116h10"/></g>')
    if female:
        p.append('<circle cx="96" cy="130" r="7" fill="#e89a8a" opacity=".4"/><circle cx="144" cy="130" r="7" fill="#e89a8a" opacity=".4"/>')
    p += ['<path d="M74 116c0-34 20-58 46-58s46 24 46 58" stroke="#00362d" stroke-width="8" fill="none" stroke-linecap="round"/>',
          '<rect x="64" y="106" width="18" height="30" rx="8" fill="#00362d"/><rect x="158" y="106" width="18" height="30" rx="8" fill="#00362d"/>',
          '<path d="M166 134c0 18-14 26-30 26" stroke="#00362d" stroke-width="5" fill="none" stroke-linecap="round"/>',
          '<circle cx="134" cy="160" r="6" fill="#00362d"/></g></svg>']
    return "\n".join(p) + "\n"


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    voices = json.loads((ROOT / "voice_pipeline/designed/catalog.json").read_text())["voices"]
    for v in voices:
        (OUT / f"{v['slug']}.svg").write_text(portrait(v["slug"], v["display_name"]))
    print(f"wrote {len(voices)} portraits to {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
