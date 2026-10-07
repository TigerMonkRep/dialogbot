"""Rebuild public/fonts/material-symbols-subset.woff2 with only the Material Symbols the code uses.

The full icon font is 4 MB; the subset is ~30 KB. Run after adding a new icon name:
    python3 web/scripts/subset-icons.py
It collects every string literal in web/src and app/ that is a valid icon name and asks Google Fonts for a subset
(FILL 0..1, weight 400, grade 0, optical size 24 – the only axes the app uses)."""
import glob, json, os, re, urllib.request

WEB = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ua = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"}
# Google's own list is the source of truth (the npm package's type list misses some names, e.g. expand_more).
meta = urllib.request.urlopen(urllib.request.Request("https://fonts.google.com/metadata/icons?key=material_symbols&incomplete=true", headers=ua)).read().decode()
valid = {i["name"] for i in json.loads(meta[meta.index("{"):])["icons"]}
valid |= set(re.findall(r'"([a-z0-9_]+)"', open(os.path.join(WEB, "node_modules/material-symbols/index.d.ts")).read()))
lits = set()
for root in (os.path.join(WEB, "src"), os.path.join(WEB, "..", "app")):
    for p in glob.glob(root + "/**/*", recursive=True):
        if p.endswith((".ts", ".tsx", ".py")) and os.path.isfile(p):
            lits |= set(re.findall(r'["\'`]([a-z][a-z0-9_]{1,40})["\'`]', open(p, errors="ignore").read()))
used = sorted(lits & valid)
css_url = ("https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined:opsz,wght,FILL,GRAD@24,400,0..1,0"
           f"&icon_names={','.join(used)}&display=block")
css = urllib.request.urlopen(urllib.request.Request(css_url, headers=ua)).read().decode()
font_url = re.search(r"url\((https://fonts\.gstatic\.com[^)]+)\)", css).group(1)
data = urllib.request.urlopen(urllib.request.Request(font_url, headers=ua)).read()
out = os.path.join(WEB, "public/fonts/material-symbols-subset.woff2")
open(out, "wb").write(data)
print(f"{len(used)} icons, {len(data)} bytes -> {out}")
