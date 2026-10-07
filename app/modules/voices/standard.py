"""Ready-made Danish phone voices that work without Dialogbot's own speech engine.

They are native Danish neural voices from Azure, spoken through Vapi (billed via Vapi credits, no extra key). A workspace
picks one as its standard; until then the phone uses DEFAULT. A number's own ElevenLabs voice or a chosen Dialogbot
voice (voices.service.vapi_voice) still wins over this.
"""
from __future__ import annotations

import uuid

from sqlalchemy.orm import Session as OrmSession

from app.config import get_settings

STANDARD_VOICES: dict[str, dict] = {
    "christel": {"name": "Christel", "gender": "female", "image": "/voices/christel.svg",
                 "description": "Rolig, venlig og tydelig. Passer til reception, klinikker og bookinger.",
                 "voice": {"provider": "azure", "voiceId": "da-DK-ChristelNeural"}},
    "jeppe": {"name": "Jeppe", "gender": "male", "image": "/voices/jeppe.svg",
              "description": "Klar og imødekommende. Passer til håndværk, service og kundeopfølgning.",
              "voice": {"provider": "azure", "voiceId": "da-DK-JeppeNeural"}},
}
DEFAULT = "christel"
# Vapi formatters that only strip markup; number/date/time/amount/phone/acronym formatters speak English.
LANGUAGE_NEUTRAL_FORMATTERS = ("markdown", "asterisk", "stripAsterisk", "quote", "newline")


def catalog() -> list[dict]:
    return [{"key": k, **{f: v[f] for f in ("name", "gender", "image", "description")}} for k, v in STANDARD_VOICES.items()]


def chosen(db: OrmSession, ws_id: uuid.UUID) -> str | None:
    from app.models import WorkspaceVoiceSettings

    vs = db.get(WorkspaceVoiceSettings, ws_id)
    key = vs.standard_voice if vs else None
    return key if key in STANDARD_VOICES else None


def provider_voice(db: OrmSession, ws_id: uuid.UUID, number=None) -> dict:
    """Vapi voice for a call: the number's ElevenLabs voice → the workspace's chosen standard voice →
    VAPI_VOICE_JSON → the default Danish standard voice (so the phone never falls back to a non-Danish voice).
    Always carries the Danish chunk plan (see danish_chunk_plan)."""
    from app.modules.telephony import vapi

    if number is not None and (own := vapi.voice_config(number)):
        voice = own
    elif key := chosen(db, ws_id):
        voice = dict(STANDARD_VOICES[key]["voice"])
    else:
        voice = vapi._json_setting(get_settings().vapi_voice_json) or dict(STANDARD_VOICES[DEFAULT]["voice"])
    voice.setdefault("chunkPlan", danish_chunk_plan(db, ws_id))
    return voice


def danish_chunk_plan(db: OrmSession, ws_id: uuid.UUID) -> dict:
    """Vapi's own text formatter is English: it turns numbers into English words ("1200" → "twelve hundred") and
    reads Danish thousand separators as decimals. The Danish voices normalise Danish text themselves, so only the
    language-neutral clean-up formatters stay on, plus the workspace's pronunciation dictionary (Stemmer → Udtale) is applied,
    as whole-word, case-insensitive replacements – the same rule as voices.danish.apply_pronunciations."""
    import re

    from app.models import WorkspaceVoiceSettings

    vs = db.get(WorkspaceVoiceSettings, ws_id)
    entries = sorted(vs.pronunciations if vs else [], key=lambda x: -len(str(x.get("term", ""))))
    replacements = []
    for e in entries:
        term, say = str(e.get("term", "")).strip(), str(e.get("say", "")).strip()
        if term and say:
            # Only the option types Vapi's RegexOption enum allows; an unknown one makes Vapi reject the call.
            replacements.append({"type": "regex", "regex": re.escape(term), "value": say,
                                 "options": [{"type": "ignore-case", "enabled": True},
                                             {"type": "whole-word", "enabled": True}]})
    return {"enabled": True, "formatPlan": {"enabled": True, "formattersEnabled": list(LANGUAGE_NEUTRAL_FORMATTERS),
                                            "replacements": replacements}}
