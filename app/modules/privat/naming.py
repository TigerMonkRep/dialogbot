"""The assistant's name. Dialogbot Privat's assistant is «Peter» unless the user picks another name when the account is
made (the first screen of /privat/start) or later under Konto. The name is shown everywhere the app says «Peter»: the
shop texts, the chat's own name, and the app overviews. Calls and e-mails keep saying «Dialogbot» – that is the brand
the business and the guests see («jeg ringer fra Dialogbot på vegne af …»)."""
from __future__ import annotations

import re

from app.core.errors import ValidationFailed

DEFAULT = "Peter"
PRONOUNS = {"han": ("han", "ham", "hans"), "hun": ("hun", "hende", "hendes"), "den": ("den", "den", "dens")}
_HAN = re.compile(r"\b(han|ham|hans)\b", re.I)
_OK = re.compile(r"[A-Za-zÆØÅæøåÄÖÜäöüÉéÈèÁáÍíÓóÚúÑñ' -]{1,20}")
_PETER = re.compile(r"\bPeter(?=s?\b)")
# Names the assistant may not take: it would pretend to be the company, a public authority or a person in charge.
RESERVED = {"dialogbot", "admin", "support", "politi", "politiet", "skat", "kommunen", "mitid", "nemid", "banken"}


def clean(raw: str | None) -> str | None:
    """A valid name, or None for «use the default». Raises on an invalid one."""
    s = " ".join(str(raw or "").split())
    if not s:
        return None
    if not _OK.fullmatch(s) or s.lower() in RESERVED:
        raise ValidationFailed("Navnet må have op til 20 bogstaver – fx Ida, Max eller Assistenten",
                               field_errors=[{"field": "assistant_name"}])
    return s[:1].upper() + s[1:]


def of(profile) -> str:
    return (getattr(profile, "assistant_name", None) or DEFAULT) if profile is not None else DEFAULT


def pronoun_of(profile) -> str:
    p = getattr(profile, "assistant_pronoun", None) if profile is not None else None
    if p in PRONOUNS:
        return p
    return "han" if of(profile) == DEFAULT else "den"   # a chosen name never gets a guessed gender


def clean_pronoun(raw: str | None) -> str | None:
    if raw in (None, ""):
        return None
    if raw not in PRONOUNS:
        raise ValidationFailed("Vælg han, hun eller den", field_errors=[{"field": "pronoun"}])
    return raw


def _swap_pronoun(m: re.Match, pronoun: str) -> str:
    word = m.group(1)
    new = PRONOUNS[pronoun][("han", "ham", "hans").index(word.lower())]
    return new.capitalize() if word[0].isupper() else new


def personalize(text, name: str, pronoun: str = "han"):
    """«Peter» (and «Peters») → the user's name, and han/ham/hans → the chosen pronoun, in a text, list or dict."""
    if (name == DEFAULT and pronoun == "han") or not text:
        return text
    if isinstance(text, str):
        out = _PETER.sub(name, text)
        return _HAN.sub(lambda m: _swap_pronoun(m, pronoun), out) if pronoun != "han" else out
    if isinstance(text, list):
        return [personalize(x, name, pronoun) for x in text]
    if isinstance(text, dict):
        return {k: personalize(v, name, pronoun) for k, v in text.items()}
    return text
