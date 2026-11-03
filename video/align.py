"""python3 align.py <lang>: line timings from the forced alignment (raw/<lang>-words.json) → out/<lang>/timing.json,
voice.m4a and captions.vtt. Lines are separated by the <break> tags we put in the prompt."""
import json, os, subprocess, sys
LEAD, TAIL = 0.6, 2.4
lang = sys.argv[1]; here = os.path.dirname(os.path.abspath(__file__)); out = os.path.join(here, "out", lang)
voice = json.load(open(os.path.join(here, "script", f"{lang}.json")))["voice"]
counts = [len(s) for s in voice]
words = json.load(open(os.path.join(here, "raw", f"{lang}-words.json")))
lines, cur, skip = [], [], 0
for w in words:
    if skip: skip -= 1; continue
    if w["text"].startswith("<break"):
        lines.append(cur); cur = []; skip = 2; continue
    cur.append(w)
lines.append(cur)
assert len(lines) == sum(counts), (lang, len(lines), sum(counts))
spans = [(ws[0]["start"], ws[-1]["end"]) for ws in lines]
first = spans[0][0]; shift = LEAD - first
spans = [(a + shift, b + shift) for a, b in spans]
scenes, k = [], 0
for i, c in enumerate(counts):
    ls = spans[k:k + c]; k += c
    scenes.append({"start": 0.0 if i == 0 else round(ls[0][0] - 0.5, 3), "lines": [{"start": round(a, 3), "end": round(b, 3)} for a, b in ls]})
total = round(spans[-1][1] + TAIL, 3)
json.dump({"scenes": scenes, "total": total}, open(os.path.join(out, "timing.json"), "w"), indent=1)
src = os.path.join(here, "raw", f"{lang}-1.mp3")
pre = f"adelay={int(shift * 1000)}:all=1," if shift > 0 else ""
ss = ["-ss", f"{-shift:.3f}"] if shift < 0 else []
subprocess.run(["ffmpeg", "-v", "error", "-y", *ss, "-i", src, "-af", pre + "apad,loudnorm=I=-16:TP=-1.5", "-t", f"{total}",
                "-ar", "48000", "-c:a", "aac", "-b:a", "128k", os.path.join(out, "voice.m4a")], check=True)
ts = lambda x: f"{int(x // 3600):02d}:{int(x % 3600 // 60):02d}:{x % 60:06.3f}"
flat = [l for s in voice for l in s]
open(os.path.join(out, "captions.vtt"), "w").write("WEBVTT\n\n" + "\n".join(f"{ts(a)} --> {ts(b + 0.3)}\n{t}\n" for (a, b), t in zip(spans, flat)))
print(lang, total)
