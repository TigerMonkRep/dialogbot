"""Dialogbot's languages, shared by the API, the phone and e-mail. Danish is the source language.

Codes are ISO 639-1 as the web uses them; Norwegian is "no" (Bokmål). Older rows may hold "da-DK" or "nb":
`normalize` maps every known form to one of LANGUAGES and anything unknown to Danish."""
from __future__ import annotations

LANGUAGES = ("da", "en", "de", "es", "fr", "it", "no", "sv")
DEFAULT = "da"

# The language's name in English (for instructions to the dialogue model) and in Danish (for Danish UI/audit text).
NAME_EN = {"da": "Danish", "en": "English", "de": "German", "es": "Spanish", "fr": "French", "it": "Italian",
           "no": "Norwegian (Bokmål)", "sv": "Swedish"}
NAME_DA = {"da": "dansk", "en": "engelsk", "de": "tysk", "es": "spansk", "fr": "fransk", "it": "italiensk",
           "no": "norsk", "sv": "svensk"}


def normalize(code: str | None) -> str:
    c = (code or "").strip().lower().replace("_", "-").split("-")[0]
    if c in ("nb", "nn"):
        c = "no"
    if c == "us":   # the website's US edition (/us) is English with dollar prices – a market, not a language
        c = "en"
    return c if c in LANGUAGES else DEFAULT
