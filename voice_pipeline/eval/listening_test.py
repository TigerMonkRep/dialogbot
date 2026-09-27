"""Blind listening test for Danish raters, and scoring of the returned answers.

    # 1) build: pick N sentences per candidate, shuffle, anonymise
    python -m voice_pipeline.eval.listening_test build --run coral-a=eval-runs/a --run coral-b=eval-runs/b \
        --per-candidate 20 --out listening/2026-10
    # → listening/2026-10/index.html (self-contained page: audio + 1–5 scales + CSV download)
    #   listening/2026-10/key.json   (which clip is which candidate – keep away from raters)
    # 2) score: after ≥3 raters have sent their CSV files
    python -m voice_pipeline.eval.listening_test score --dir listening/2026-10 answers/*.csv

Scales 1–5: forståelighed, naturlighed, stemmestabilitet, dialekt (only rated by raters who speak that dialect;
leave empty otherwise). Critical error = a wrong date, number, amount, negation or booking status. The score
command prints per-candidate means and the evidence JSON for the operator check `listening_test`. It never
invents ratings; missing raters stay missing.
"""
from __future__ import annotations

import argparse
import csv
import html
import json
import random
import shutil
import statistics
from pathlib import Path

SCALES = ("forstaaelighed", "naturlighed", "stabilitet", "dialekt")
LABELS = {"forstaaelighed": "Forståelighed", "naturlighed": "Naturlighed", "stabilitet": "Stemmestabilitet",
          "dialekt": "Dialekt (kun hvis du selv taler den)"}


def build(runs: list[str], per: int, out: Path, seed: int) -> None:
    rng = random.Random(seed)
    out.mkdir(parents=True, exist_ok=True)
    (out / "audio").mkdir(exist_ok=True)
    items, key = [], {}
    for spec in runs:
        name, path = spec.split("=", 1)
        rows = [json.loads(x) for x in (Path(path) / "results.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()]
        for r in rng.sample(rows, min(per, len(rows))):
            clip = f"k{rng.randrange(16**8):08x}"
            shutil.copy(Path(path) / f"{r['id']}.wav", out / "audio" / f"{clip}.wav")
            key[clip] = {"candidate": name, "sentence": r["id"], "simulated": r.get("simulated")}
            items.append((clip, r["text"], r["meaning"]))
    rng.shuffle(items)
    (out / "key.json").write_text(json.dumps(key, indent=2, ensure_ascii=False))
    rows_html = []
    for clip, text, meaning in items:
        scales = "".join(
            f'<label>{LABELS[s]} <select name="{clip}:{s}"><option value="">–</option>'
            + "".join(f"<option>{i}</option>" for i in range(1, 6)) + "</select></label>" for s in SCALES)
        rows_html.append(f'<section><p><b>Tekst:</b> {html.escape(text)}<br><small>Betydning: {html.escape(meaning)}</small></p>'
                         f'<audio controls preload="none" src="audio/{clip}.wav"></audio><div>{scales}'
                         f'<label><input type="checkbox" name="{clip}:kritisk"> Kritisk fejl (dato, tal, beløb, nægtelse, bookingstatus)</label>'
                         f'<label>Kommentar <input name="{clip}:kommentar"></label></div></section>')
    page = f"""<!doctype html><html lang="da"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Lyttetest</title><style>body{{font-family:Manrope,system-ui,sans-serif;background:#e7fef9;color:#164e43;max-width:760px;margin:auto;padding:16px}}
section{{background:#fff;border-radius:12px;padding:12px;margin:12px 0}}label{{display:inline-block;margin:4px 8px 4px 0}}
button{{background:#164e43;color:#fff;border:0;border-radius:8px;padding:10px 16px}}</style>
<h1>Lyttetest – danske stemmer</h1><p>Lyt til hvert klip og giv 1 (dårligst) til 5 (bedst). Du ved ikke, hvilken stemme der er hvilken.
Dit navn: <input id="rater"></p>{''.join(rows_html)}
<button onclick="dl()">Hent mine svar (CSV)</button>
<script>function dl(){{const r=document.getElementById('rater').value||'anonym';const rows=[['rater','clip','field','value']];
document.querySelectorAll('select,input[name]').forEach(e=>{{const [c,f]=e.name.split(':');const v=e.type==='checkbox'?(e.checked?'1':''):e.value;if(v)rows.push([r,c,f,v]);}});
const csv=rows.map(x=>x.map(y=>'"'+String(y).replaceAll('"','""')+'"').join(',')).join('\\n');
const a=document.createElement('a');a.href=URL.createObjectURL(new Blob([csv],{{type:'text/csv'}}));a.download='lyttetest-'+r+'.csv';a.click();}}</script></html>"""
    (out / "index.html").write_text(page, encoding="utf-8")
    print(f"{len(items)} clips → {out / 'index.html'}")


def score(directory: Path, files: list[Path]) -> dict:
    key = json.loads((directory / "key.json").read_text())
    per: dict = {}
    raters = set()
    for f in files:
        with f.open(encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                meta = key.get(row["clip"])
                if meta is None:
                    continue
                raters.add(row["rater"])
                c = per.setdefault(meta["candidate"], {s: [] for s in SCALES} | {"kritisk": 0, "raters": set(),
                                                                                  "simulated": bool(meta.get("simulated"))})
                c["raters"].add(row["rater"])
                if row["field"] in SCALES and row["value"]:
                    c[row["field"]].append(int(row["value"]))
                elif row["field"] == "kritisk":
                    c["kritisk"] += 1
    out = {}
    for name, c in per.items():
        means = {s: round(statistics.mean(c[s]), 2) if c[s] else None for s in SCALES}
        out[name] = {"raters": len(c["raters"]), "intelligibility": means["forstaaelighed"],
                     "naturalness": means["naturlighed"], "stability": means["stabilitet"], "dialect": means["dialekt"],
                     "critical_errors": c["kritisk"], "simulated_audio": c["simulated"],
                     "meets_goal": (len(c["raters"]) >= 3 and (means["forstaaelighed"] or 0) >= 4
                                    and (means["naturlighed"] or 0) >= 4 and c["kritisk"] == 0 and not c["simulated"])}
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build")
    b.add_argument("--run", action="append", required=True)
    b.add_argument("--per-candidate", type=int, default=20)
    b.add_argument("--out", required=True, type=Path)
    b.add_argument("--seed", type=int, default=2026)
    s = sub.add_parser("score")
    s.add_argument("--dir", required=True, type=Path)
    s.add_argument("files", nargs="+", type=Path)
    args = ap.parse_args(argv)
    if args.cmd == "build":
        build(args.run, args.per_candidate, args.out, args.seed)
    else:
        print(json.dumps(score(args.dir, args.files), indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
