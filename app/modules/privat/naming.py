"""The assistant's name. Dialogbot Privat's assistant is «Peter» unless the user picks another name when the account is
made (the first screen of /privat/start) or later under Konto. The name is shown everywhere the app says «Peter»: the
shop texts, the chat's own name, and the app overviews. Calls and e-mails keep saying «Dialogbot» – that is the brand
the business and the guests see («jeg ringer fra Dialogbot på vegne af …»)."""
from __future__ import annotations

import re

from app.core.errors import ValidationFailed

DEFAULT = "Peter"
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


def personalize(text: str, name: str):
    """«Peter» (and «Peters») in a text, list or dict → the user's name."""
    if name == DEFAULT or not text:
        return text
    if isinstance(text, str):
        return _PETER.sub(name, text)
    if isinstance(text, list):
        return [personalize(x, name) for x in text]
    if isinstance(text, dict):
        return {k: personalize(v, name) for k, v in text.items()}
    return text
