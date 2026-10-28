"""Static TTF instances of the variable Outfit/Inter fonts shipped in web/node_modules (latin + latin-ext merged)."""
import os, tempfile
from fontTools.ttLib import TTFont
from fontTools.varLib import instancer
from fontTools.merge import Merger
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]  # web/
NM = str(ROOT / "node_modules/@fontsource-variable")
OUT = str(Path(__file__).resolve().parent / ".build/fonts")
os.makedirs(OUT, exist_ok=True)
jobs = [("outfit", "Outfit", {800: "ExtraBold", 700: "Bold", 600: "SemiBold"}),
        ("inter", "Inter", {600: "SemiBold", 500: "Medium", 400: "Regular"})]
for pkg, fam, weights in jobs:
    for w, name in weights.items():
        parts = []
        for sub in ("latin", "latin-ext"):
            f = TTFont(f"{NM}/{pkg}/files/{pkg}-{sub}-wght-normal.woff2")
            inst = instancer.instantiateVariableFont(f, {"wght": w}, inplace=False, updateFontNames=True)
            inst.flavor = None
            p = tempfile.mktemp(suffix=".ttf"); inst.save(p); parts.append(p)
        merged = Merger().merge(parts)
        n = merged["name"]
        for rec in list(n.names):
            if rec.nameID in (1, 4, 6, 16, 17):
                n.removeNames(rec.nameID, rec.platformID, rec.platEncID, rec.langID)
        n.setName(fam, 1, 3, 1, 0x409); n.setName(name, 2, 3, 1, 0x409)
        n.setName(f"{fam} {name}", 4, 3, 1, 0x409); n.setName(f"{fam}-{name}", 6, 3, 1, 0x409)
        n.setName(fam, 16, 3, 1, 0x409); n.setName(name, 17, 3, 1, 0x409)
        merged.save(f"{OUT}/{fam}-{name}.ttf")
        cm = merged.getBestCmap()
        print(f"{fam}-{name}.ttf", len(cm), all(ord(c) in cm for c in "Dialogbot æøåÆØÅ–×·"))
        for p in parts: os.remove(p)
