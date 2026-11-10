"""Score voice eval cases (qa/voice/cases/<scenario>.yaml) against call transcripts – no calls, no network.

A case describes caller turns, what Peter must do and what he must never do. A transcript is a list of turns
[{"role": "assistant"|"user", "text": "..."}] – from a stored call (the conversation under /app/opkald, exported as
JSON) or from an offline simulation. Every case also carries reference transcripts (one that must pass, one that
must fail) so the scorer itself is tested (tests/qa/test_qa_voice_X16.py).

    python qa/voice/run_cases.py qa/voice/cases/X16.yaml                 # score the reference transcripts
    python qa/voice/run_cases.py qa/voice/cases/X16.yaml --transcript t.json --case X16-01

Checks (all optional per case, under `expect` / `forbid`):
  language: da|en           every assistant turn reads as that language (simple marker-word test)
  first_words_language: …   the first assistant turn reads as that language
  spell_back: "B, E, R, L, E"  the assistant spells the unknown name back before using it
  name / max_mentions_after_confirmation: N   after the spelled confirmation the name is said at most N times
  spell_first: true         the name must not be said (only spelled) before the spelled confirmation
  must_say: [...]           phrases that must appear in some assistant turn (case-insensitive)
  forbid: [...]             phrases that must never appear in an assistant turn (case-insensitive)
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import yaml

MARKERS = {
    "da": {"jeg", "du", "det", "er", "og", "ikke", "hvad", "kan", "hjælpe", "tak", "dag", "ringer", "vi", "har"},
    "en": {"i", "you", "the", "is", "and", "not", "what", "can", "help", "thanks", "day", "call", "we", "have"},
}


def language_of(text: str) -> str | None:
    words = re.findall(r"[a-zæøåé]+", text.lower())
    scores = {lang: sum(w in m for w in words) for lang, m in MARKERS.items()}
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 and list(scores.values()).count(scores[best]) == 1 else None


def score(case: dict, transcript: list[dict]) -> tuple[bool, list[str]]:
    expect, forbid = case.get("expect") or {}, [f.lower() for f in case.get("forbid") or []]
    bot = [t["text"] for t in transcript if t.get("role") == "assistant"]
    problems: list[str] = []
    if not bot:
        return False, ["no assistant turn"]
    if (lang := expect.get("first_words_language")) and language_of(bot[0]) != lang:
        problems.append(f"first assistant turn is not {lang}: {bot[0]!r}")
    if lang := expect.get("language"):
        for t in bot:
            if (got := language_of(t)) not in (lang, None):
                problems.append(f"assistant turn in {got}, expected {lang}: {t!r}")
    for phrase in expect.get("must_say") or []:
        if not any(phrase.lower() in t.lower() for t in bot):
            problems.append(f"never said {phrase!r}")
    for t in bot:
        for f in forbid:
            if f in t.lower():
                problems.append(f"forbidden {f!r} in {t!r}")
    if spelled := expect.get("spell_back"):
        idx = next((i for i, t in enumerate(bot) if spelled.lower() in t.lower()), None)
        if idx is None:
            problems.append(f"name never spelled back ({spelled!r})")
        elif (name := expect.get("name")) and (limit := expect.get("max_mentions_after_confirmation")) is not None:
            pattern = re.compile(rf"(?<!\w){re.escape(name)}(?!\w)", re.IGNORECASE)
            before = sum(len(pattern.findall(t)) for t in bot[:idx])
            if before and expect.get("spell_first"):
                problems.append(f"name {name!r} used {before}x before it was confirmed by spelling")
            after = sum(len(pattern.findall(t)) for t in bot[idx + 1:])
            if after > limit:
                problems.append(f"name {name!r} said {after}x after confirmation (max {limit})")
    return not problems, problems


def load(path: str | Path) -> list[dict]:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    return data["cases"]


def main(argv: list[str]) -> int:
    cases = load(argv[0])
    if "--transcript" in argv:
        transcript = json.loads(Path(argv[argv.index("--transcript") + 1]).read_text(encoding="utf-8"))
        wanted = argv[argv.index("--case") + 1] if "--case" in argv else None
        cases = [c for c in cases if wanted in (None, c["id"])]
        ok_all = True
        for c in cases:
            ok, why = score(c, transcript)
            ok_all &= ok
            print(f"{c['id']}: {'pass' if ok else 'fail'} {'; '.join(why)}")
        return 0 if ok_all else 1
    bad = 0
    for c in cases:
        for kind, want in (("pass", True), ("fail", False)):
            for tr in (c.get("reference_transcripts") or {}).get(kind) or []:
                ok, why = score(c, tr)
                bad += ok != want
                print(f"{c['id']} reference {kind}: {'ok' if ok == want else 'SCORER WRONG'} {'; '.join(why)}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
