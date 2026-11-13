"""Craft rules for Dialogbot's own social posts: hook scoring, per-platform lint, a light humaniser, and the trail
("forløb") each post carries so the operator dashboard can show how it came about.

The rules are a Danish port of two rule sets:

* Instagram follows the ``ig-*`` skills (hook formulas and scoring, caption lint, humaniser, five hashtags).
* Facebook, TikTok (and X, once it is connected) follow the ``social-media-skills`` playbooks.

Nothing here calls the network and nothing here is allowed to block a post. The facts guard in ``content.check`` is
the only thing that rejects copy; the scores and lint findings below are advice that ends up in the trail and in the
operator's eyes, because a person approves every post (SOCIAL_REQUIRE_APPROVAL).

The hook score is a heuristic. The skill it is ported from measured it at AUC 0.83 for telling a real hook from a
deliberately bad one, but only 0.56 (a coin flip is 0.50) for telling one good creator's hits from their misses. So
it is used to drop weak hooks and to pick between candidates, never to predict reach.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime

# --- rule sets per platform ---------------------------------------------------------------------------------------

SKILLSET_INSTAGRAM = "ig-skills"
SKILLSET_OTHER = "social-media-skills"


@dataclass(frozen=True)
class Playbook:
    platform: str
    skillset: str
    hashtag_limit: int
    visible_chars: int | None  # how much of the text shows before "mere" (None: not an issue on the platform)
    connected: bool  # False: rules are ready, but Dialogbot cannot post there yet
    rules: tuple[str, ...]


PLAYBOOKS: dict[str, Playbook] = {
    "instagram": Playbook("instagram", SKILLSET_INSTAGRAM, hashtag_limit=5, visible_chars=125, connected=True, rules=(
        "Første linje i teksten er hooken og skal give mening alene: kun de første ca. 125 tegn ses, før der står 'mere'.",
        "Højst 5 hashtags (Instagrams grænse siden december 2025). Hashtags sorterer opslaget, de giver ikke rækkevidde.",
        "Slide 1 er løftet, hver slide leverer ét punkt, og sidste slide har én opfordring.",
        "Skriv, så opslaget kan gemmes eller sendes videre: konkret og brugbart, ikke reklamesprog.",
        "Ingen fyldfraser og åbninger som 'I en verden hvor' eller 'Tag din virksomhed til næste niveau'.",
    )),
    "tiktok": Playbook("tiktok", SKILLSET_OTHER, hashtag_limit=5, visible_chars=None, connected=True, rules=(
        "Hooken skal virke på tre sekunder: et spørgsmål eller en lille provokation i talesprog.",
        "Brug de ord, folk søger på (telefonpasning, AI-receptionist), i selve teksten, fordi TikTok også er en søgemaskine.",
        "3-5 hashtags. Ingen opfordringer som 'like og del, hvis du er enig'.",
        "Tekst på billederne holdes væk fra TikToks egne knapper (højre side og nederst).",
    )),
    "facebook": Playbook("facebook", SKILLSET_OTHER, hashtag_limit=3, visible_chars=None, connected=True, rules=(
        "Rolig, fortællende tone: 2-4 korte afsnit, ét budskab.",
        "Linket står i selve opslaget og sættes af systemet. Afslut med en inviterende sætning, ikke med reklame.",
        "1-3 hashtags. Ingen opfordringer til at like, dele eller tagge for at få rækkevidde.",
    )),
    "x": Playbook("x", SKILLSET_OTHER, hashtag_limit=2, visible_chars=280, connected=False, rules=(
        "Højst 280 tegn og én idé pr. opslag. Hooken er den første halve linje.",
        "Højst 2 hashtags. Link sidst, ikke først. Tråde kun, hvis hver enkelt del står alene.",
    )),
}


def rules_for(platform: str) -> str:
    """The rule lines for the AI prompt, one block per platform."""
    p = PLAYBOOKS[platform]
    return "\n".join(f"  - {r}" for r in p.rules)


# --- hook score ---------------------------------------------------------------------------------------------------

_WORD = re.compile(r"[A-Za-z0-9ÆØÅæøå'’-]+")
_DIGIT = re.compile(r"\d")
# "i" is left out on purpose: lower-cased it cannot be told from the preposition "i" (in).
_ADDRESS = {"du", "dig", "din", "dit", "dine", "jer", "jeres"}
_NEGATION = {"ikke", "aldrig", "ingen", "uden", "intet", "stop", "slut", "undgå", "ingenting"}
_CONTRAST = {"men", "i stedet", "alligevel", "bare uden", "til gengæld"}
_SCENE = {"stige", "stigen", "vask", "saks", "saksen", "stol", "stolen", "møde", "værksted", "aftenrush", "morgentimerne",
          "telefon", "telefonen", "opkald", "hænderne", "hænder", "albuerne", "nummer", "nummeret", "tid", "tider",
          "kunden", "kunde", "receptionen", "bil", "bilen", "dækskift", "bord", "bordbestilling", "bordbestillinger"}
_GREETING = ("hej", "velkommen", "goddag", "god dag", "hey ", "i dag vil jeg", "i dag skal", "lad mig fortælle")
# Generic marketing words that make a hook interchangeable with every other company's.
_GENERIC = ("revolution", "innovativ", "næste niveau", "game changer", "fremtidens", "state of the art", "skræddersyet løsning",
            "helhedsløsning", "optimer", "synergi")


def _words(text: str) -> list[str]:
    return [w.lower() for w in _WORD.findall(text)]


def _clamp(n: float) -> float:
    return max(0.0, min(100.0, n))


@dataclass
class HookScore:
    text: str
    score: float
    parts: dict[str, float]
    formula: str
    verdict: str  # svag | ok | stærk
    flags: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {"text": self.text, "score": round(self.score), "parts": {k: round(v) for k, v in self.parts.items()},
                "formula": self.formula, "verdict": self.verdict, "flags": self.flags}


def classify_formula(text: str) -> str:
    t = text.strip().lower()
    w = _words(text)
    if t.endswith("?"):
        return "spørgsmål"
    if re.match(r"^(stop|slut med|undgå|lad være)\b", t):
        return "negativ kommando"
    if _DIGIT.search(t):
        return "tal"
    if any(c in t for c in (" men ", "i stedet", "bare uden", "alligevel")):
        return "kontrast"
    if set(w) & _SCENE:
        return "scene"
    if set(w) & _ADDRESS:
        return "direkte henvendelse"
    return "påstand"


def score_hook(text: str) -> HookScore:
    """Four 0-100 checks on the first line of a post: a length that can be said in a breath, something concrete,
    something at stake, and a person it is aimed at. Higher is better."""
    text = " ".join(text.split())
    w = _words(text)
    n = len(w)
    flags: list[str] = []

    # length: 4-12 spoken words is the working range
    if 4 <= n <= 12:
        length = 100.0
    elif n < 4:
        length = _clamp(n * 25.0)
    else:
        length = _clamp(100 - (n - 12) * 12.0)
    if n > 14:
        flags.append("for lang til at sige i ét åndedrag")

    # specificity: a figure or a scene the reader can picture
    concrete = (1 if _DIGIT.search(text) else 0) + len(set(w) & _SCENE)
    specificity = _clamp(30 + concrete * 35.0)
    if concrete == 0:
        flags.append("ingenting konkret")

    # stakes: a question, a negation or a contrast creates tension
    low = f" {text.lower()} "
    tension = (1 if text.endswith("?") else 0) + (1 if set(w) & _NEGATION else 0) + (1 if any(c in low for c in _CONTRAST) else 0)
    stakes = _clamp(25 + tension * 40.0)

    # address: aimed at someone
    address = 100.0 if set(w) & _ADDRESS else 45.0

    score = (length + specificity + stakes + address) / 4
    if any(g in low for g in _GREETING):
        score -= 25
        flags.append("begynder med hilsen eller indledning")
    generic = [g for g in _GENERIC if g in low]
    if generic:
        score -= 15
        flags.append(f"generisk: {generic[0]}")
    score = _clamp(score)
    verdict = "svag" if score < 45 else "ok" if score < 70 else "stærk"
    return HookScore(text, score, {"længde": length, "konkret": specificity, "spænding": stakes, "henvendt": address},
                     classify_formula(text), verdict, flags)


# --- humaniser ----------------------------------------------------------------------------------------------------

_INVISIBLE = "​‌‍⁠﻿­"
# Phrases that read as machine-written in Danish marketing copy. They are reported, not rewritten.
_SLOP = ("i en verden hvor", "i dagens digitale", "i nutidens", "dykke ned i", "låse op for", "tag din virksomhed til næste niveau",
         "næste niveau", "game changer", "sømløs", "revolutionere", "i en tid hvor", "det er ikke bare", "uden at gå på kompromis",
         "ikke kun", "lad os være ærlige", "her er sagen", "delve", "leverage", "unlock")


def humanize(text: str) -> tuple[str, list[dict]]:
    """Clean what makes text look pasted from an AI: invisible characters, em dashes and doubled spaces.
    Danish uses a spaced en dash, so an em dash becomes that. Stock phrases are flagged, never rewritten."""
    changes: list[dict] = []
    n = sum(text.count(c) for c in _INVISIBLE)
    if n:
        text = text.translate({ord(c): None for c in _INVISIBLE})
        changes.append({"kind": "usynlige tegn fjernet", "count": n})
    n = text.count("—")
    if n:
        text = re.sub(r"\s*—\s*", " – ", text)
        changes.append({"kind": "tankestreg ændret til dansk tankestreg", "count": n})
    cleaned = re.sub(r"[ \t]{2,}", " ", text)
    if cleaned != text:
        changes.append({"kind": "dobbelte mellemrum", "count": 1})
        text = cleaned
    return text, changes


def slop_flags(text: str) -> list[str]:
    low = text.lower()
    return [p for p in _SLOP if p in low]


# --- lint per platform ---------------------------------------------------------------------------------------------

_EMOJI = re.compile("[\U0001F300-\U0001FAFF☀-➿]")


def lint(platform: str, body: str, tags: list[str], hook: str | None = None) -> list[dict]:
    """Findings on the text before links and hashtags are added. Each is {level: info|warn, code, message}."""
    pb = PLAYBOOKS[platform]
    out: list[dict] = []

    def add(level: str, code: str, message: str) -> None:
        out.append({"level": level, "code": code, "message": message})

    if len(tags) > pb.hashtag_limit:
        add("warn", "hashtags", f"{len(tags)} hashtags, men {platform} bør have højst {pb.hashtag_limit}")
    first = body.strip().split("\n", 1)[0] if body.strip() else ""
    if pb.visible_chars and len(first) > pb.visible_chars:
        add("warn", "first_line", f"første linje er {len(first)} tegn, og kun ca. {pb.visible_chars} ses før 'mere'")
    if len(_EMOJI.findall(body)) > 3:
        add("warn", "emoji", "mere end tre emojis")
    stock = slop_flags(body)
    if stock:
        add("warn", "stock_phrase", "fyldfrase: " + ", ".join(stock[:3]))
    if re.search(r"\b(like og del|tag en ven|del hvis du)\b", body.lower()):
        add("warn", "engagement_bait", "opfordring til at like/dele for rækkevidde")
    if hook:
        hs = score_hook(hook)
        if hs.verdict == "svag":
            add("warn", "weak_hook", f"svag hook ({round(hs.score)}/100): " + "; ".join(hs.flags or ["lav samlet score"]))
    if not out:
        add("info", "clean", "ingen bemærkninger")
    return out


# --- the trail ---------------------------------------------------------------------------------------------------

STEPS = ("idea", "hooks", "copy", "checks", "approval", "edit", "publish")


def step(kind: str, status: str = "ok", **detail) -> dict:
    """One entry in a post's trail. status: ok | warn | fail | skipped."""
    return {"step": kind, "status": status, "at": datetime.now(UTC).isoformat(timespec="seconds"), "detail": detail}


def append(trail: list | None, kind: str, status: str = "ok", **detail) -> list[dict]:
    """A new list (so SQLAlchemy sees the JSONB column change) with one more step."""
    return [*(trail or []), step(kind, status, **detail)]
