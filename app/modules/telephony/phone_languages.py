"""What changes on the phone when a business serves its callers in another language than Danish.

The business picks the language once (language_settings.default_conversation_language). Everything the caller hears
or says follows it: the recogniser's language, the greeting, the dialogue model's language, the voice, the closing
phrases that end the call and the backchannels ("ja", "mm") that must never interrupt Peter. Instructions to the
dialogue model stay in Danish (they are written and reviewed in Danish); a language directive in English on top tells
the model to speak the caller's language only."""
from __future__ import annotations

from sqlalchemy.orm import Session as OrmSession

from app.core.languages import DEFAULT, NAME_EN, normalize

# The default greeting when the business has written none. {name} = the business's name.
GREETING = {
    "da": "Hej, du har ringet til {name}. Du taler med en digital assistent, og samtalen bliver skrevet ned. "
          "Hvad kan jeg hjælpe med?",
    "en": "Hello, you've reached {name}. You're speaking with a digital assistant, and this call is transcribed. "
          "How can I help?",
    "de": "Guten Tag, Sie sind verbunden mit {name}. Sie sprechen mit einem digitalen Assistenten, und das Gespräch "
          "wird aufgezeichnet. Wie kann ich helfen?",
    "es": "Hola, ha llamado a {name}. Está hablando con un asistente digital y la llamada se transcribe. "
          "¿En qué puedo ayudarle?",
    "fr": "Bonjour, vous êtes bien chez {name}. Vous parlez avec un assistant numérique et l'appel est retranscrit. "
          "Comment puis-je vous aider ?",
    "it": "Buongiorno, ha chiamato {name}. Sta parlando con un assistente digitale e la chiamata viene trascritta. "
          "Come posso aiutarla?",
    "no": "Hei, du har ringt til {name}. Du snakker med en digital assistent, og samtalen blir skrevet ned. "
          "Hva kan jeg hjelpe deg med?",
    "sv": "Hej, du har ringt till {name}. Du pratar med en digital assistent och samtalet skrivs ner. "
          "Vad kan jag hjälpa till med?",
}

# Said at the end of every call (the phone prompt ends with it); hearing one ends the call.
END_PHRASES = {
    "da": ["hav en rigtig god dag", "hav en god dag"],
    "en": ["have a great day", "have a nice day", "have a good day"],
    "de": ["einen schönen tag noch", "schönen tag noch", "auf wiederhören"],
    "es": ["que tenga un buen día", "que tenga un excelente día"],
    "fr": ["bonne journée", "excellente journée"],
    "it": ["buona giornata", "buona continuazione"],
    "no": ["ha en fin dag", "ha en god dag"],
    "sv": ["ha en bra dag", "ha en fin dag"],
}

# Short listening sounds that must not stop Peter mid-sentence.
BACKCHANNELS = {
    "da": ["ja", "jo", "jah", "mm", "mhm", "okay", "ok", "nå", "nåh", "præcis", "netop", "fint", "godt", "javel", "jaja",
           "yes", "klart"],
    "en": ["yes", "yeah", "yep", "mm", "mhm", "uh-huh", "okay", "ok", "right", "sure", "exactly", "great", "fine"],
    "de": ["ja", "jaja", "mm", "mhm", "okay", "ok", "genau", "gut", "richtig", "stimmt", "klar", "aha"],
    "es": ["sí", "si", "vale", "ajá", "mm", "mhm", "claro", "bien", "exacto", "okay", "ok", "de acuerdo"],
    "fr": ["oui", "ouais", "d'accord", "mm", "mhm", "ok", "okay", "exactement", "bien", "voilà", "ah"],
    "it": ["sì", "si", "certo", "mm", "mhm", "ok", "okay", "esatto", "bene", "va bene", "giusto"],
    "no": ["ja", "jo", "mm", "mhm", "okei", "ok", "akkurat", "greit", "fint", "klart", "nettopp"],
    "sv": ["ja", "jo", "mm", "mhm", "okej", "ok", "precis", "bra", "absolut", "visst", "japp"],
}


# The language a caller from this country code most likely speaks (longest prefix wins).
COUNTRY_LANGUAGE = {"+45": "da", "+299": "da", "+298": "da", "+46": "sv", "+47": "no", "+49": "de", "+43": "de",
                    "+41": "de", "+44": "en", "+353": "en", "+1": "en", "+61": "en", "+64": "en", "+34": "es",
                    "+33": "fr", "+32": "fr", "+352": "fr", "+39": "it"}


def caller_language(caller: str | None) -> str | None:
    """+4520… → "da". None for a withheld or unknown number."""
    c = (caller or "").replace(" ", "")
    if not c.startswith("+"):
        return None
    for n in (4, 3, 2):
        if c[:n] in COUNTRY_LANGUAGE:
            return COUNTRY_LANGUAGE[c[:n]]
    return None


def call_language(db: OrmSession, workspace_id, caller: str | None = None) -> str:
    """The language this call is answered in: the caller's own language (from the country code) when the business has
    turned that language on, otherwise the business's default language. A Danish number is answered in Danish whenever
    Danish is on, even if the default is another language."""
    from app.models import LanguageSettings

    ls = db.get(LanguageSettings, workspace_id) if workspace_id else None
    default = normalize(ls.default_conversation_language if ls else DEFAULT)
    enabled = {normalize(x) for x in ((ls.enabled_conversation_languages if ls else None) or [])} | {default}
    guess = caller_language(caller)
    return guess if guess in enabled else default


def report_language(db: OrmSession, workspace_id) -> str:
    from app.models import LanguageSettings

    ls = db.get(LanguageSettings, workspace_id) if workspace_id else None
    return normalize(ls.report_language if ls else DEFAULT)


def directive(lang: str) -> str:
    """Put FIRST in the system prompt for a non-Danish call."""
    if lang == DEFAULT:
        return ""
    name = NAME_EN[lang]
    return (f"LANGUAGE: This phone call is in {name}. Speak {name} only, naturally and idiomatically, as a native "
            f"receptionist would – also if the caller's first words are in another language, unless they ask to "
            f"switch. The instructions and the business knowledge below are written in Danish: follow them, but "
            f"never speak Danish to the caller and translate facts, prices and names of services into {name} when "
            f"you say them. Say numbers, prices, dates, times and phone numbers the way {name} speakers say them "
            f"(ignore any Danish-specific formatting rule below). End the call with a short {name} goodbye such as "
            f"\"{END_PHRASES[lang][0]}\".\n\n")


def greeting(lang: str, name: str) -> str:
    return GREETING.get(lang, GREETING[DEFAULT]).format(name=name)


def summary_instruction(lang: str) -> str:
    """Appended to the Danish summary prompt when the business reads its reports in another language."""
    return "" if lang == DEFAULT else f" Skriv resuméet på {NAME_EN[lang]} (write the summary in {NAME_EN[lang]})."
