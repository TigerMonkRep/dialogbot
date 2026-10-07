"""Turns a topic into one post per platform: different structure, different voice, different hashtags and links.

- Facebook: one square image card and a short story-style text with a clickable link.
- Instagram: a swipeable carousel (hook, one point per slide, call to action) and a caption with hashtags; links are
  not clickable in captions, so the call to action points to the link in the bio.
- TikTok: a full-screen 9:16 photo carousel with a spoken-style hook and a very short text with few hashtags.

The AI provider writes the copy when it is configured; every answer is checked against the verified facts (prices,
promises, length limits, no links or hashtags where code adds them). A platform whose AI copy fails the checks, or any
platform when the AI is off or errors, gets the hand-written copy from `topics.py`. A post is therefore never
blocked by the AI and never contains a number or promise that is not in `topics.FACTS`.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

import structlog

from app.config import get_settings
from app.core.errors import ApiError
from app.modules.social.topics import ALLOWED_AMOUNTS, FACTS, PLATFORMS, Topic

log = structlog.get_logger("dialogbot.social")

PROMPT_VERSION = "social-v1"
MAX_TOKENS = 4000

# The number of slides each platform gets from the fallback copy, and the range the AI may use.
SLIDES = {"facebook": (1, 1), "instagram": (4, 7), "tiktok": (4, 6)}
CAPTION_MAX = {"facebook": 900, "instagram": 1500, "tiktok": 280}
TITLE_MAX, BODY_MAX = 90, 170

FORBIDDEN = ("garanti", "garanter", "nr. 1", "nummer 1", "nummer ét", "bedst", "markedets", "spar ", "sparer", "omsætning",
             "procent", "%", "risikofri", "gratis prøve", "gratis demo")


@dataclass
class Draft:
    platform: str
    slides: list[dict]  # {role: hook|point|cta, kicker, title, body, bullets?}
    caption: str  # complete text as it is posted (hashtags and link appended by `finish`)
    hashtags: list[str]
    link: str | None
    generator: str = "template"
    model: str | None = None
    body: str = ""  # the text before links and hashtags were added (what `check` reads)
    errors: list[str] = field(default_factory=list)


# --- hashtags, links, final caption ------------------------------------------------------------------------------

_TAG_RE = re.compile(r"[^0-9a-zæøåA-ZÆØÅ]")
BASE_TAGS = {
    "facebook": ("dialogbot",),
    "instagram": ("dialogbot", "aireceptionist", "telefonsvarer", "småvirksomhed", "danskevirksomheder", "kundeservice"),
    "tiktok": ("dialogbot", "ai", "småvirksomhed"),
}
TAG_LIMIT = {"facebook": 3, "instagram": 10, "tiktok": 5}


def clean_tag(tag: str) -> str:
    return _TAG_RE.sub("", tag.lstrip("#")).lower()


def hashtags_for(platform: str, topic: Topic, extra: list[str] | None = None) -> list[str]:
    out: list[str] = []
    for t in [*BASE_TAGS[platform][:1], *topic.tags, *(extra or []), *BASE_TAGS[platform][1:]]:
        t = clean_tag(t)
        if t and t not in out:
            out.append(t)
    return out[: TAG_LIMIT[platform]]


def link_for(topic: Topic, platform: str) -> str:
    base = get_settings().social_site_url.rstrip("/")
    return f"{base}{topic.path}" if topic.path != "/" else base


def finish(platform: str, text: str, tags: list[str], link: str | None) -> str:
    """Append the platform's call to action and hashtags to the body text. Only code writes links."""
    text = text.strip()
    tag_line = " ".join(f"#{t}" for t in tags)
    if platform == "facebook":
        return f"{text}\n\n👉 Læs mere: {link}\n\n{tag_line}"
    if platform == "instagram":
        return f"{text}\n\n🔗 Link i bio – eller find os på dialogbot.dk\n💾 Gem opslaget, hvis du kender en, der har brug for det.\n\n{tag_line}"
    return f"{text}\n\nLink i bio 👆\n{tag_line}"


# --- hand-written fallback ---------------------------------------------------------------------------------------

def template_draft(platform: str, topic: Topic) -> Draft:
    hook, pts = topic.hooks[platform], topic.points
    if platform == "facebook":
        slides = [{"role": "hook", "kicker": topic.kicker, "title": hook, "body": "", "bullets": list(pts)}]
        body = f"{hook}\n\n" + "\n".join(f"✔ {p}" for p in pts) + f"\n\n{topic.proof}"
    elif platform == "instagram":
        slides = [{"role": "hook", "kicker": topic.kicker, "title": hook, "body": ""}]
        slides += [{"role": "point", "kicker": f"{i} / 3", "title": p, "body": ""} for i, p in enumerate(pts, 1)]
        slides.append({"role": "cta", "kicker": "Dialogbot", "title": topic.proof, "body": "dialogbot.dk"})
        body = f"{hook}\n\n" + "\n".join(f"{p}." for p in pts) + f"\n\n{topic.proof}"
    else:
        slides = [{"role": "hook", "kicker": topic.kicker, "title": hook, "body": ""}]
        slides += [{"role": "point", "kicker": f"{i} / 3", "title": p, "body": ""} for i, p in enumerate(pts, 1)]
        slides.append({"role": "cta", "kicker": "Dialogbot", "title": "Prøv Dialogbot", "body": "dialogbot.dk"})
        body = hook
    tags = hashtags_for(platform, topic)
    link = link_for(topic, platform) if platform == "facebook" else None
    return Draft(platform, slides, finish(platform, body, tags, link), tags, link, body=body)


# --- AI copy -----------------------------------------------------------------------------------------------------

SYSTEM = """Du skriver opslag til sociale medier for Dialogbot på dansk. Du er en venlig, jordnær og konkret tekstforfatter
til små virksomheder i Danmark. Skriv naturligt dansk uden amerikanske floskler.

Det eneste, du må sige om Dialogbot, står i <fakta>. Opfind aldrig tal, statistikker, kundecitater, kundenavne,
sammenligninger med konkurrenter eller løfter. Kronebeløb må kun være 1.495 kr. og 149 kr. Skriv ingen procenter og ingen
garantier, og skriv ikke "bedst", "nr. 1" eller lignende. Skriv ikke links, e-mailadresser eller hashtags i teksterne;
dem tilføjer systemet selv.

<fakta>
{facts}
</fakta>

Svar KUN med et JSON-objekt og ingen forklaring, med nøglerne "facebook", "instagram" og "tiktok". Hver nøgle har
{{"slides": [{{"title": "...", "body": "..."}}], "caption": "...", "hashtags": ["...", "..."]}}.

De tre platforme skal føles forskellige, ikke som tre kopier af samme tekst:
- facebook: PRÆCIS 1 slide (title = overskrift på billedet, højst 70 tegn; body = én kort sætning). caption: 2-4 korte
  afsnit i en rolig, fortællende tone, højst 700 tegn, gerne en afsluttende invitation til at læse mere. 1-2 hashtags.
- instagram: 5 slides: slide 1 er en stærk hook (title højst 70 tegn), slide 2-4 hvert ét punkt (title højst 70 tegn,
  body valgfri kort uddybning), slide 5 er en opfordring (title højst 50 tegn). caption: levende og lidt mere personlig,
  1-3 korte afsnit, højst 1200 tegn, du må bruge 1-3 emojis. 6-8 hashtags.
- tiktok: 5 slides i et hurtigt, direkte talesprog: slide 1 er et spørgsmål eller en provokation, der får folk til at
  blive (title højst 60 tegn), slide 2-4 hvert ét punkt, slide 5 er en opfordring. caption: højst 150 tegn. 3-4 hashtags.

Hashtags skrives uden # og uden mellemrum."""

USER = """Emne: {key}
Vinkel: {angle}
Branche-/emnemærke på billederne: {kicker}
Stikord du kan bygge på (må omformuleres, men ikke udvides med nye påstande):
- {p1}
- {p2}
- {p3}
Afslutning: {proof}

Undgå at gentage åbningslinjer fra de seneste opslag:
{recent}"""


def _complete(db, system: str, user: str):
    """One provider call, logged on the sales workspace when it exists (Dialogbot's own usage log)."""
    from app.modules.ai.provider import get_provider
    from app.modules.ai.service import log_call
    from app.modules.sales.service import sales_workspace

    provider = get_provider()  # raises ApiError (501) when AI_PROVIDER=none
    messages = [{"role": "user", "content": user}]
    ws = sales_workspace(db)
    if ws is not None:
        c, _ = log_call(db, ws, provider, user_id=None, purpose="social_post", system=system, messages=messages,
                        prompt_version=PROMPT_VERSION, revision=ws.knowledge_revision, max_tokens=MAX_TOKENS)
        return c
    return provider.complete(system=system, messages=messages, max_tokens=MAX_TOKENS)


def parse_json(text: str) -> dict:
    a, b = text.find("{"), text.rfind("}")
    if a < 0 or b <= a:
        raise ValueError("no JSON object in the answer")
    data = json.loads(text[a:b + 1])
    if not isinstance(data, dict):
        raise ValueError("answer is not an object")
    return data


def _s(v, limit: int) -> str:
    return " ".join(str(v or "").split())[:limit].rstrip()


def draft_from_ai(platform: str, topic: Topic, raw: dict, model: str | None) -> Draft:
    if not isinstance(raw, dict):
        raise ValueError(f"{platform}: not an object")
    lo, hi = SLIDES[platform]
    slides_in = raw.get("slides")
    if not isinstance(slides_in, list) or not lo <= len(slides_in) <= hi:
        raise ValueError(f"{platform}: expected {lo}-{hi} slides")
    slides: list[dict] = []
    for i, s in enumerate(slides_in):
        if not isinstance(s, dict):
            raise ValueError(f"{platform}: slide {i + 1} is not an object")
        role = "hook" if i == 0 else "cta" if (i == len(slides_in) - 1 and platform != "facebook") else "point"
        kicker = topic.kicker if i == 0 else "Dialogbot" if role == "cta" else f"{i} / {len(slides_in) - 2}"
        body = "dialogbot.dk" if role == "cta" else _s(s.get("body"), BODY_MAX)  # the CTA's body is the address button
        if platform == "facebook":
            slides.append({"role": role, "kicker": kicker, "title": _s(s.get("title"), 200), "body": body,
                           "bullets": list(topic.points)})
        else:
            slides.append({"role": role, "kicker": kicker, "title": _s(s.get("title"), 200), "body": body})
    tags_in = raw.get("hashtags") if isinstance(raw.get("hashtags"), list) else []
    tags = hashtags_for(platform, topic, [str(t) for t in tags_in])
    link = link_for(topic, platform) if platform == "facebook" else None
    body_text = str(raw.get("caption") or "").strip()
    d = Draft(platform, slides, finish(platform, body_text, tags, link), tags, link, generator="ai", model=model,
              body=body_text)
    d.errors = check(d)
    return d


def check(d: Draft) -> list[str]:
    """Why a draft may not be posted ([] = fine). Looks at the text before code added links and hashtags."""
    errors: list[str] = []
    body_text = d.body
    lo, hi = SLIDES[d.platform]
    if not lo <= len(d.slides) <= hi:
        errors.append("slide count")
    for i, s in enumerate(d.slides, 1):
        if not s["title"]:
            errors.append(f"slide {i} has no title")
        if len(s["title"]) > TITLE_MAX or len(s.get("body", "")) > BODY_MAX:
            errors.append(f"slide {i} too long")
    if not body_text or len(body_text) > CAPTION_MAX[d.platform]:
        errors.append("caption empty or too long")
    if re.search(r"https?://|www\.|@\w+\.\w+|#", body_text):
        errors.append("link, e-mail or hashtag in the text")
    everything = " ".join([body_text, *(f"{s['title']} {s.get('body', '')}" for s in d.slides)]).lower()
    for word in FORBIDDEN:
        if word in everything:
            errors.append(f"forbidden phrase: {word.strip()}")
    for m in re.finditer(r"(\d[\d.,]*)\s*(?:kr\b|kr\.|kroner|dkk)", everything):
        amount = m.group(1).rstrip(".,")
        if amount.replace(".", "") not in {a.replace(".", "") for a in ALLOWED_AMOUNTS}:
            errors.append(f"amount not in the facts: {amount}")
    if "gratis" in everything and "opsætning" not in everything:
        errors.append("'gratis' without the setup context")
    return errors


def generate(db, topic: Topic, platforms: tuple[str, ...] = PLATFORMS, recent_hooks: list[str] | None = None) -> list[Draft]:
    """One Draft per platform. Never raises: the hand-written copy is the floor."""
    drafts = {p: template_draft(p, topic) for p in platforms}
    if get_settings().ai_provider == "none":
        return list(drafts.values())
    system = SYSTEM.format(facts="\n".join(f"- {f}" for f in FACTS))
    user = USER.format(key=topic.key, angle=topic.angle, kicker=topic.kicker, p1=topic.points[0], p2=topic.points[1],
                       p3=topic.points[2], proof=topic.proof,
                       recent="\n".join(f"- {h}" for h in (recent_hooks or [])[:8]) or "- (ingen endnu)")
    try:
        c = _complete(db, system, user)
        if c.stop_reason in ("refusal", "max_tokens") or not c.text:
            raise ValueError(f"unusable answer ({c.stop_reason})")
        data = parse_json(c.text)
    except (ApiError, ValueError, json.JSONDecodeError) as e:
        log.warning("social.ai_unavailable", topic=topic.key, error=f"{type(e).__name__}: {e}")
        return list(drafts.values())
    for p in platforms:
        try:
            d = draft_from_ai(p, topic, data.get(p), c.served_model)
        except (ValueError, TypeError) as e:
            log.warning("social.ai_rejected", platform=p, topic=topic.key, error=str(e))
            continue
        if d.errors:
            log.warning("social.ai_rejected", platform=p, topic=topic.key, errors=d.errors)
            continue
        drafts[p] = d
    return list(drafts.values())
