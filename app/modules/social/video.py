"""Short-form video for Dialogbot's own channels: the manuscript ("brief"), its score, the monthly budget and the loop
that learns from what was published.

A brief is a script for a 15-35 second vertical video with a person in it. It is built around five things that decide
whether a short video is watched to the end and passed on:
  1. the first three seconds carry a spoken hook, on-screen text and movement together;
  2. one of four repeatable concept formulas (tool-outcome-time, story arc, myth buster, relatable stakes);
  3. a reason to send or save it (practical value, social currency, emotion);
  4. pace: a cut or a new text line at least every 3-4 seconds, no filler;
  5. signals the platforms weigh: finishing, sending, saving.

The score is advice for the operator and for the learning loop, never a gate; a person approves every video. It does
not predict reach. What the platforms report after publishing (`SocialVideo.metrics`) is what `learn` ranks the
formulas by, and what decides which formula the next brief uses.

Nothing here talks to a video model. `render` is the single place where that will happen, so the cost guard and the
approval step already work before any money can be spent.
"""
from __future__ import annotations

import random
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session as OrmSession

from app.config import get_settings
from app.core.errors import Conflict, NotFound
from app.models import SocialVideo
from app.modules.social import content, craft
from app.modules.social.topics import FACTS, TOPICS_BY_KEY, Topic

PROMPT_VERSION = "video-v1"
FORMULAS = ("tool_outcome_time", "story_arc", "myth_buster", "relatable_stakes")
FORMULA_LABEL = {"tool_outcome_time": "Værktøj, resultat, tid", "story_arc": "Mikro-fortælling",
                 "myth_buster": "Myte eller fejl", "relatable_stakes": "Genkendelig frustration"}
CRITERIA = ("first3", "concept", "share", "pace", "signals")
CRITERIA_LABEL = {"first3": "De første 3 sekunder", "concept": "Koncept", "share": "Del- og gemværdi", "pace": "Tempo",
                  "signals": "Signaler til algoritmen"}
WEIGHTS = {"first3": 0.30, "concept": 0.20, "share": 0.20, "pace": 0.15, "signals": 0.15}
MIN_SECONDS, MAX_SECONDS = 15, 35
HOOK_SECONDS = 3
WORDS_PER_SECOND = 3.0  # Danish voice-over, comfortable and brisk
FILLER = ("øh", "altså", "ligesom", "sådan set", "ikke også", "som sagt", "jamen")
PERSONAS = ("ai_person", "rigtig_person", "blandet")


# --- the brief ---------------------------------------------------------------------------------------------------

def _s(v, limit: int = 240) -> str:
    return " ".join(str(v or "").split())[:limit].rstrip()


def normalise(raw: dict, *, topic: Topic, formula: str, persona: str = "ai_person") -> dict:
    """Coerce whatever the model (or a template) returned into the stored shape; nothing outside it is kept."""
    hook = raw.get("hook") or {}
    beats = []
    for b in (raw.get("beats") or [])[:8]:
        if not isinstance(b, dict):
            continue
        try:
            start, end = float(b.get("start")), float(b.get("end"))
        except (TypeError, ValueError):
            continue
        beats.append({"start": round(start, 1), "end": round(end, 1), "role": _s(b.get("role"), 12) or "value",
                      "spoken": _s(b.get("spoken")), "on_screen": _s(b.get("on_screen"), 70), "visual": _s(b.get("visual")),
                      "cut": _s(b.get("cut"), 24) or "klip"})
    cta = raw.get("cta") or {}
    tags = [content.clean_tag(str(t)) for t in (raw.get("hashtags") or []) if content.clean_tag(str(t))][:5]
    try:
        duration = float(raw.get("duration"))
    except (TypeError, ValueError):
        duration = beats[-1]["end"] if beats else 0.0
    return {
        "topic": topic.key, "formula": formula if formula in FORMULAS else FORMULAS[0], "persona": persona if persona in PERSONAS else "ai_person",
        "duration": round(duration, 1),
        "hook": {"spoken": _s(hook.get("spoken")), "on_screen": _s(hook.get("on_screen"), 70), "visual": _s(hook.get("visual")),
                 "motion": _s(hook.get("motion"), 120), "end": round(float(hook.get("end") or HOOK_SECONDS), 1)},
        "beats": beats,
        "cta": {"spoken": _s(cta.get("spoken")), "on_screen": _s(cta.get("on_screen"), 70), "ask": _s(cta.get("ask"), 8).lower()},
        "save_asset": _s(raw.get("save_asset")),
        "caption": _s(raw.get("caption"), 300), "hashtags": tags,
        "disclosure": "AI-genereret" if persona != "rigtig_person" else "",
    }


def spoken_text(brief: dict) -> str:
    parts = [brief["hook"]["spoken"], *[b["spoken"] for b in brief["beats"]], brief["cta"]["spoken"]]
    return " ".join(p for p in parts if p)


def screen_text(brief: dict) -> list[str]:
    return [t for t in [brief["hook"]["on_screen"], *[b["on_screen"] for b in brief["beats"]], brief["cta"]["on_screen"]] if t]


def problems(brief: dict) -> list[str]:
    """Facts guard: the same rules as the posts (no price outside the allowed ones, no promises, no links)."""
    out: list[str] = []
    for text in [spoken_text(brief), *screen_text(brief), brief["caption"], brief["save_asset"]]:
        for p in content._text_problems(text):
            if p not in out:
                out.append(p)
    if brief["persona"] != "rigtig_person" and not brief["disclosure"]:
        out.append("mangler AI-mærkning")
    return out


# --- score -------------------------------------------------------------------------------------------------------

@dataclass
class VideoScore:
    total: int
    criteria: dict[str, dict]
    verdict: str
    flags: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {"total": self.total, "verdict": self.verdict, "criteria": self.criteria, "flags": self.flags}


def _c(score: float, notes: list[str]) -> dict:
    return {"score": int(max(0, min(100, round(score)))), "notes": notes}


def score_brief(brief: dict) -> VideoScore:
    hook, beats, cta = brief["hook"], brief["beats"], brief["cta"]
    spoken = spoken_text(brief)
    words = len(re.findall(r"\w+", spoken, flags=re.UNICODE))
    duration = brief["duration"] or (beats[-1]["end"] if beats else 0)
    flags: list[str] = []

    # 1. the first three seconds: the trio (voice + text + movement) inside 3 seconds, and a hook line that holds up
    n: list[str] = []
    trio = [bool(hook["spoken"]), bool(hook["on_screen"]), bool(hook["motion"])]
    s1 = 20 * sum(trio)
    for ok, label in zip(trio, ("sagt hook", "tekst på skærmen", "bevægelse eller visuelt brud"), strict=True):
        if not ok:
            n.append(f"Mangler {label} i de første 3 sekunder")
    if hook["end"] > HOOK_SECONDS:
        s1 -= 15
        n.append("Hooken varer længere end 3 sekunder")
    hs = craft.score_hook(hook["spoken"] or hook["on_screen"])
    s1 += hs.score * 0.4
    if hs.verdict == "svag":
        n.append("Hook-linjen er svag: " + ", ".join(hs.flags or ["gør den mere konkret og henvendt"]))
    first3 = _c(s1, n)

    # 2. concept: one recognisable formula with its own parts
    n = []
    f = brief["formula"]
    roles = [b["role"] for b in beats]
    low = " ".join([hook["spoken"], spoken]).lower()
    c = 40
    if f == "tool_outcome_time":
        has_tool = "dialogbot" in low or "peter" in low
        has_time = bool(re.search(r"\b(\d+|et|en|to|tre|fem|ti)\s+(sekund|minut|time|halv|dag)", low)) or "halv time" in low
        has_outcome = any(w in low for w in ("tager telefonen", "booker", "opsummering", "svarer", "sms", "kunde"))
        c += 20 * has_tool + 20 * has_time + 20 * has_outcome
        n += [m for ok, m in ((has_tool, "Navngiv værktøjet"), (has_time, "Sig hvor hurtigt det går"), (has_outcome, "Sig resultatet konkret")) if not ok]
    elif f == "story_arc":
        order = [r for r in roles if r in ("setup", "value", "payoff")]
        good = "setup" in order and "payoff" in order and order.index("setup") < len(order) - 1 - order[::-1].index("payoff")
        c += 40 * good + 20 * ("value" in order)
        if not good:
            n.append("Fortællingen mangler setup og payoff i den rækkefølge")
        if "value" not in order:
            n.append("Mangler et midterstykke med værdi")
    elif f == "myth_buster":
        has = bool(re.search(r"\b(myte|forkert|fejl|tror|alle)\b", low))
        c += 40 * has + 20 * any(r == "payoff" for r in roles)
        if not has:
            n.append("Peg på den udbredte fejl eller myte")
    elif f == "relatable_stakes":
        has = any(w in low for w in ("når du", "din ", "dine ", "du "))
        c += 40 * has + 20 * any(r == "payoff" for r in roles)
        if not has:
            n.append("Tag udgangspunkt i en frustration, seeren kender")
    concept = _c(c, n)

    # 3. a reason to send or save it
    n = []
    sh = 30
    if brief["save_asset"]:
        sh += 30
    else:
        n.append("Giv noget at gemme: en tjekliste, tre spørgsmål eller en konkret tommelfingerregel")
    if cta["ask"] in ("send", "gem"):
        sh += 20
    else:
        n.append("Bed om at sende den til én bestemt person eller gemme den")
    if re.search(r"\d", spoken) or any(b["role"] == "value" and len(b["spoken"].split()) >= 5 for b in beats):
        sh += 20
    else:
        n.append("Mere konkret værdi i midten")
    share = _c(sh, n)

    # 4. pace
    n = []
    p = 100
    if not (MIN_SECONDS <= duration <= MAX_SECONDS):
        p -= 25
        n.append(f"Længden er {duration:.0f} s; sigt efter {MIN_SECONDS}-{MAX_SECONDS} s")
    longest = max([hook["end"], *[b["end"] - b["start"] for b in beats]] or [0])
    if longest > 4.5:
        p -= 20
        n.append(f"Et stykke varer {longest:.0f} s uden klip; del det op")
    rate = words / duration if duration else 0
    if rate > WORDS_PER_SECOND + 0.6:
        p -= 20
        n.append("For mange ord pr. sekund til at kunne følges")
    elif duration and rate < 1.2:
        p -= 15
        n.append("Meget tyndt talt; der er dødt luft")
    fill = [w for w in FILLER if re.search(rf"\b{w}\b", low)]
    if fill:
        p -= 10 * len(fill)
        n.append("Fyldord: " + ", ".join(fill))
    if beats and sum(1 for b in beats if b["on_screen"]) < len(beats):
        p -= 15
        n.append("Hvert klip skal have tekst på skærmen")
    if beats and sum(1 for b in beats if b["visual"]) < len(beats):
        p -= 10
        n.append("Hvert klip skal have et nyt billede")
    pace = _c(p, n)

    # 5. what the platforms measure: finishing, sending, saving
    n = []
    g = 40
    if duration and duration <= 30:
        g += 20
    else:
        n.append("Kortere videoer ses oftere til ende")
    last = beats[-1]["spoken"].lower() if beats else ""
    hook_words = {w for w in re.findall(r"\w{4,}", hook["spoken"].lower())}
    if hook_words & set(re.findall(r"\w{4,}", " ".join([last, cta["spoken"].lower()]))):
        g += 20
    else:
        n.append("Lad slutningen ekkoe hooken, så videoen kan loope")
    if cta["spoken"] and cta["on_screen"]:
        g += 20
    else:
        n.append("Sig og vis opfordringen")
    signals = _c(g, n)

    crit = {"first3": first3, "concept": concept, "share": share, "pace": pace, "signals": signals}
    total = round(sum(crit[k]["score"] * WEIGHTS[k] for k in CRITERIA))
    for k in CRITERIA:
        if crit[k]["score"] < 50:
            flags.append(f"{CRITERIA_LABEL[k]}: {crit[k]['notes'][0] if crit[k]['notes'] else 'svag'}")
    verdict = "stærk" if total >= 80 else "ok" if total >= 60 else "svag"
    return VideoScore(total, crit, verdict, flags)


# --- cost and budget ---------------------------------------------------------------------------------------------

def estimate_cost_dkk(duration: float) -> float:
    """Worst-case spend to render one brief: seconds x price per second x retries (about three in ten clips are discarded)
    x the exchange rate. Voice-over is not included; it runs on the existing speech plan."""
    s = get_settings()
    return round(duration * s.video_price_usd_per_second * s.video_retry_factor * s.video_usd_dkk, 2)


def month_spend_dkk(db, now: datetime | None = None) -> float:
    from sqlalchemy import func

    now = now or datetime.now(timezone.utc)
    start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    q = select(func.coalesce(func.sum(SocialVideo.est_cost_dkk), 0)).where(
        SocialVideo.status.in_(("approved", "rendered", "published")), SocialVideo.approved_at >= start)
    return float(db.scalar(q) or 0)


def budget(db, now: datetime | None = None) -> dict:
    cap = float(get_settings().video_monthly_budget_dkk)
    spent = month_spend_dkk(db, now)
    return {"monthly_dkk": cap, "committed_dkk": round(spent, 2), "left_dkk": round(max(0.0, cap - spent), 2)}


# --- learning ----------------------------------------------------------------------------------------------------

def engagement(metrics: dict | None) -> float | None:
    """One comparable number per published video: what the platforms weigh most, per view. Returns None until there are
    views to divide by. Sends and saves count most, watch share (average watch time / length) next, likes least."""
    m = metrics or {}
    views = m.get("views")
    if not views:
        return None
    send = (m.get("shares") or 0) / views
    save = (m.get("saves") or 0) / views
    like = ((m.get("likes") or 0) + (m.get("comments") or 0)) / views
    watch = min(1.0, float(m.get("watch_share") or 0))
    return round(100 * (4 * send + 3 * save + 2 * watch / 10 + like), 4)


def learn(rows: list[dict]) -> dict:
    """Rank formulas and hook formulas by the mean engagement of published videos that have views. `rows` are plain dicts
    ({formula, hook_formula, duration, engagement}) so this can be tested without a database."""
    def agg(key: str) -> list[dict]:
        groups: dict[str, list[float]] = {}
        for r in rows:
            if r.get("engagement") is not None and r.get(key):
                groups.setdefault(r[key], []).append(r["engagement"])
        out = [{"key": k, "n": len(v), "mean": round(sum(v) / len(v), 4)} for k, v in groups.items()]
        return sorted(out, key=lambda x: -x["mean"])
    return {"formulas": agg("formula"), "hooks": agg("hook_formula"), "measured": sum(1 for r in rows if r.get("engagement") is not None)}


MIN_SAMPLES = 3  # a formula must have this many measured videos before it can be called a winner
EXPLORE = 0.25   # share of briefs that always try a formula at random, so a lucky early winner cannot lock the rest out


def choose_formulas(n: int, learned: dict, rng: random.Random | None = None) -> list[str]:
    """Pick a formula per new brief: mostly the best measured one, a quarter at random, and any formula still below
    MIN_SAMPLES measured videos first (so every formula gets a fair test before one is favoured)."""
    rng = rng or random.Random()
    counts = {f["key"]: f["n"] for f in learned.get("formulas", [])}
    untested = [f for f in FORMULAS if counts.get(f, 0) < MIN_SAMPLES]
    ranked = [f["key"] for f in learned.get("formulas", []) if f["n"] >= MIN_SAMPLES]
    out: list[str] = []
    for i in range(n):
        if untested:
            out.append(untested[i % len(untested)])
        elif rng.random() < EXPLORE or not ranked:
            out.append(rng.choice(FORMULAS))
        else:
            out.append(ranked[0])
    return out


# --- template briefs (used when the AI is off or its answer fails the checks) -------------------------------------------

def template_brief(topic: Topic, formula: str, persona: str = "ai_person") -> dict:
    """A hand-written brief: hook (0-3 s), four beats of about four seconds each, and a closing line that repeats the hook so
    the video can loop. Built only from the topic's own verified hooks and points."""
    p1, p2, p3 = topic.points
    hook = topic.hooks["tiktok"]
    base = {
        "duration": 23, "persona": persona,
        "hook": {"spoken": hook, "on_screen": _s(hook, 70), "visual": "Personen kigger direkte i kameraet, telefonen ringer i forgrunden",
                 "motion": "Hurtigt zoom ind og telefonen ryster i billedet", "end": 3},
        "save_asset": "Tre ting at tjekke, før du lader en AI tage telefonen: " + "; ".join([p1, p2, p3]).lower(),
        "caption": topic.angle, "hashtags": list(topic.tags),
    }
    if formula == "tool_outcome_time":
        beats = [
            ("setup", "Mød Dialogbot, en dansk AI-receptionist, der tager telefonen døgnet rundt.", "Mød Dialogbot", "Skærmoptagelse af et opkald, der bliver taget", "klip"),
            ("value", f"{p1}.", _s(p1, 70), "Tekstlinjen popper frem ved siden af personen", "jump cut"),
            ("value", f"{p2}.", _s(p2, 70), "Nærbillede af telefonen med opsummeringen", "indklip"),
            ("payoff", "Opsætningen tager cirka en halv time, og du beholder dit eget nummer.", "Op på en halv time", "Personen nikker, nummeret vises på telefonen", "zoom"),
        ]
    elif formula == "story_arc":
        beats = [
            ("setup", topic.hooks["instagram"], "Det kender du", "Klip fra hverdagen: hænder fulde, telefonen lyser op", "klip"),
            ("value", f"{p1}.", _s(p1, 70), "Telefonen bliver taget, teksten popper frem", "jump cut"),
            ("value", f"{p2}.", _s(p2, 70), "Indklip af skærmen med svaret", "indklip"),
            ("payoff", f"{p3}. Så kan du blive ved med dit arbejde.", "Du bliver ved med dit arbejde", "Personen smiler og arbejder videre", "zoom"),
        ]
    elif formula == "myth_buster":
        beats = [
            ("setup", "Mange tror, at en telefonsvarer er nok. Den beder bare kunden om at lægge en besked.", "Myte: en telefonsvarer er nok", "Personen ryster på hovedet, teksten streges over", "klip"),
            ("value", f"{p1}.", _s(p1, 70), "Punkt ét popper op", "jump cut"),
            ("value", f"{p2}.", _s(p2, 70), "Punkt to popper op", "indklip"),
            ("payoff", f"{p3}. Det er forskellen.", "Det er forskellen", "Personen peger på tekstlinjen", "zoom"),
        ]
    else:
        beats = [
            ("setup", "Du står midt i en opgave, og telefonen ringer. Igen.", "Telefonen ringer. Igen.", "Hænderne er fulde, telefonen lyser op", "klip"),
            ("value", f"Dialogbot tager den. {p1}.", _s(p1, 70), "Telefonen bliver taget, teksten popper frem", "jump cut"),
            ("value", f"{p2}.", _s(p2, 70), "Indklip af skærmen med svaret", "indklip"),
            ("payoff", f"{p3}. Så kan du holde fokus.", "Du holder fokus", "Personen arbejder videre i ro", "zoom"),
        ]
    t = 3.0
    out = []
    for role, spoken, on_screen, visual, cut in beats:
        out.append({"role": role, "start": t, "end": t + 4, "spoken": spoken, "on_screen": on_screen, "visual": visual, "cut": cut})
        t += 4
    base["beats"] = out
    base["cta"] = {"spoken": f"{hook} Send den til en, der har travlt.", "on_screen": "Send til en, der har travlt", "ask": "send"}
    return normalise(base, topic=topic, formula=formula, persona=persona)


# --- AI brief ----------------------------------------------------------------------------------------------------

SYSTEM = """Du skriver manuskripter til korte lodrette videoer (15-30 sekunder) for Dialogbot på dansk. Videoen har ét menneske i
billedet, der taler direkte til kameraet, afbrudt af indklip. Du er konkret og jordnær; skriv naturligt, talt dansk uden
amerikanske floskler.

Det eneste, du må sige om Dialogbot, står i <fakta>. Opfind aldrig tal, statistikker, kundecitater, navne, sammenligninger eller
løfter. Skriv ingen priser og ingen kronebeløb, ingen procenter og ingen garantier, og ikke "bedst", "nr. 1" eller "gratis".
Ingen links, e-mailadresser eller hashtags i de talte linjer eller på skærmen.

<fakta>
{facts}
</fakta>

Videoen skal opfylde fem ting:
1. De første 3 sekunder: et talt hook, en tekst på skærmen og en bevægelse eller et visuelt brud, alt inden for 3 sekunder.
   Hooken vækker nysgerrighed (et spørgsmål, en modsigelse, en konkret scene), den afslører ikke svaret.
2. Konceptet følger formlen "{formula}": {formula_help}
3. Der er noget at gemme (save_asset: en tjekliste, tre spørgsmål eller en tommelfingerregel) og en grund til at sende den videre.
4. Tempo: et nyt klip eller en ny tekstlinje mindst hver 3.-4. sekund, ingen fyldord, højst 3 ord pr. sekund.
5. Slutningen ekkoer hooken, så videoen kan loope, og opfordringen er "send" eller "gem".

Svar KUN med et JSON-objekt: {{"duration": tal, "hook": {{"spoken": "", "on_screen": "", "visual": "", "motion": "", "end": 3}},
"beats": [{{"role": "setup|value|payoff", "start": 3, "end": 8, "spoken": "", "on_screen": "", "visual": "", "cut": ""}}],
"cta": {{"spoken": "", "on_screen": "", "ask": "send|gem"}}, "save_asset": "", "caption": "højst 150 tegn", "hashtags": ["3-5 ord uden #"]}}.
Hver beat har sin egen tekst på skærmen (højst 70 tegn) og sit eget billede. Hold dig til 3-5 beats."""

FORMULA_HELP = {
    "tool_outcome_time": "navngiv værktøjet (Dialogbot), sig det konkrete resultat og hvor hurtigt det går (kun tider fra fakta).",
    "story_arc": "en mikro-fortælling med setup, et midterstykke med værdi og en payoff eller drejning til sidst.",
    "myth_buster": "udpeg en udbredt fejl eller myte ('alle gør X forkert'), og vis, hvad der er rigtigt.",
    "relatable_stakes": "start i en frustration, målgruppen kender, og vis, hvad der står på spil, før løsningen.",
}

USER = """Emne: {key}
Vinkel: {angle}
Stikord (må omformuleres, ikke udvides med nye påstande):
- {p1}
- {p2}
- {p3}
Afslutning: {proof}
Undgå disse hooks fra de seneste videoer:
{recent}"""


def generate_brief(db, topic: Topic, formula: str, *, persona: str = "ai_person", recent: list[str] | None = None) -> tuple[dict, dict]:
    """One brief and a note on how it came about: {"generator": "ai"|"template", "model", "fallback"?}.
    The AI answer must pass `problems`; if it does not, or the AI is unavailable, the hand-written brief is used."""
    note: dict = {"generator": "template", "model": None}
    settings = get_settings()
    if settings.ai_provider != "none":
        system = SYSTEM.format(facts="\n".join(f"- {f}" for f in FACTS), formula=FORMULA_LABEL[formula], formula_help=FORMULA_HELP[formula])
        user = USER.format(key=topic.key, angle=topic.angle, p1=topic.points[0], p2=topic.points[1], p3=topic.points[2],
                           proof=topic.proof, recent="\n".join(f"- {h}" for h in (recent or [])) or "(ingen)")
        try:
            comp = content._complete(db, system, user)
            brief = normalise(content.parse_json(comp.text), topic=topic, formula=formula, persona=persona)
            errors = problems(brief)
            if not brief["beats"]:
                errors.append("ingen beats")
            if errors:
                note["fallback"] = {"code": "ai_rejected", "errors": errors}
            else:
                return brief, {"generator": "ai", "model": getattr(comp, "model", None)}
        except Exception as e:  # noqa: BLE001 - any provider or parsing trouble means the hand-written brief is used
            note["fallback"] = {"code": "ai_unavailable", "message": f"{type(e).__name__}: {e}"[:200]}
    else:
        note["fallback"] = {"code": "ai_off"}
    return template_brief(topic, formula, persona), note


def render(video) -> None:  # pragma: no cover - wired up when a video model is configured
    """Where the approved brief becomes a file. Deliberately empty: nothing may spend money before the provider, its key
    and the budget guard have been connected and tested end to end."""
    raise NotImplementedError("video rendering is not connected yet")



# --- stored briefs: plan, approve, reject, overview ---------------------------------------------------------------------

def _row(db: OrmSession, topic: Topic, formula: str, persona: str, recent: list[str]) -> SocialVideo:
    brief, note = generate_brief(db, topic, formula, persona=persona, recent=recent)
    sc = score_brief(brief)
    v = SocialVideo(topic=topic.key, formula=brief["formula"], hook_formula=craft.classify_formula(brief["hook"]["spoken"]),
                    status="draft", brief=brief, score=sc.as_dict(), generator=note["generator"], generator_model=note.get("model"),
                    note=note.get("fallback"), est_cost_dkk=estimate_cost_dkk(brief["duration"]))
    db.add(v)
    return v


def plan_videos(db: OrmSession, count: int = 3, *, topic_key: str | None = None, persona: str = "ai_person",
                rng: random.Random | None = None) -> list[SocialVideo]:
    """New draft briefs: topics that were used longest ago first, formulas chosen by what the numbers say so far."""
    from app.modules.social.topics import TOPICS

    used = dict(db.execute(select(SocialVideo.topic, SocialVideo.created_at).order_by(SocialVideo.created_at)).all())
    order = sorted(TOPICS, key=lambda t: (used.get(t.key) or datetime.min.replace(tzinfo=timezone.utc), TOPICS.index(t)))
    if topic_key:
        if topic_key not in TOPICS_BY_KEY:
            raise NotFound("Ukendt emne")
        order = [TOPICS_BY_KEY[topic_key]] * count
    learned = learn(_rows(db))
    formulas = choose_formulas(count, learned, rng)
    recent = [h for (h,) in db.execute(select(SocialVideo.brief["hook"]["spoken"].astext).order_by(SocialVideo.created_at.desc()).limit(8))]
    out = []
    for i in range(count):
        v = _row(db, order[i % len(order)], formulas[i], persona, recent)
        recent.insert(0, v.brief["hook"]["spoken"])
        out.append(v)
    db.commit()
    return out


def get_video(db: OrmSession, video_id: uuid.UUID) -> SocialVideo:
    v = db.get(SocialVideo, video_id)
    if v is None:
        raise NotFound("Videoen findes ikke")
    return v


def approve(db: OrmSession, v: SocialVideo, user_id: uuid.UUID, now: datetime | None = None) -> SocialVideo:
    """Commits the render cost against the month. Refused when it would not fit, so a month can never overspend."""
    if v.status != "draft":
        raise Conflict(f"Videoen er {v.status} og kan ikke godkendes")
    b = budget(db, now)
    if float(v.est_cost_dkk) > b["left_dkk"]:
        raise Conflict(f"Budgettet rækker ikke: videoen koster op til {float(v.est_cost_dkk):.2f} kr., der er {b['left_dkk']:.2f} kr. tilbage denne måned")
    v.status, v.approved_by_user_id, v.approved_at = "approved", user_id, now or datetime.now(timezone.utc)
    db.commit()
    return v


def reject(db: OrmSession, v: SocialVideo) -> SocialVideo:
    if v.status != "draft":
        raise Conflict(f"Videoen er {v.status} og kan ikke afvises")
    v.status = "rejected"
    db.commit()
    return v


def _rows(db: OrmSession) -> list[dict]:
    out = []
    for v in db.scalars(select(SocialVideo).where(SocialVideo.status == "published")).all():
        out.append({"formula": v.formula, "hook_formula": v.hook_formula, "duration": v.brief.get("duration"),
                    "engagement": engagement(v.metrics)})
    return out


def to_dict(v: SocialVideo) -> dict:
    return {"id": str(v.id), "topic": v.topic, "formula": v.formula, "formula_label": FORMULA_LABEL.get(v.formula, v.formula),
            "hook_formula": v.hook_formula, "status": v.status, "brief": v.brief, "score": v.score, "generator": v.generator,
            "generator_model": v.generator_model, "note": v.note, "est_cost_dkk": float(v.est_cost_dkk),
            "metrics": v.metrics, "created_at": v.created_at.isoformat() if v.created_at else None}


def overview(db: OrmSession, now: datetime | None = None) -> dict:
    """What the operator page shows about video: the budget, what the numbers say so far, and the latest briefs."""
    rows = db.scalars(select(SocialVideo).order_by(SocialVideo.created_at.desc()).limit(30)).all()
    return {"budget": budget(db, now), "learning": learn(_rows(db)), "min_samples": MIN_SAMPLES,
            "rendering_connected": False, "items": [to_dict(v) for v in rows],
            "formulas": {k: FORMULA_LABEL[k] for k in FORMULAS}, "criteria": CRITERIA_LABEL}
