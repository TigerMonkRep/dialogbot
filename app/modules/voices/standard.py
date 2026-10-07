"""Ready-made Danish phone voices that work without Dialogbot's own speech engine.

Christel and Jeppe are native Danish neural voices from Azure, spoken through Vapi (billed via Vapi credits, no extra
key). Camilla and Peter are ElevenLabs voices and need the platform's ElevenLabs key connected in Vapi. A workspace
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
    # ElevenLabs Voice Library voices, spoken through Vapi with the platform's ElevenLabs key (Vapi → Integrations).
    "camilla": {"name": "Camilla", "gender": "female", "image": "/voices/camilla.svg",
                "description": "Klar, rolig og professionel på rigsdansk med en meget naturlig betoning.",
                "voice": {"provider": "11labs", "voiceId": "4RklGmuxoAskAbGXplXN", "model": "eleven_v4_turbo",
                          "language": "da"}},
    "peter": {"name": "Peter", "gender": "male", "image": "/voices/peter.svg",
              "description": "Naturlig og klar med en let jysk klang. Lyder som en rigtig medarbejder.",
              "voice": {"provider": "11labs", "voiceId": "qhEux886xDKbOdF7jkFP", "model": "eleven_v4_turbo",
                        "language": "da"}},
}
DEFAULT = "christel"
# Vapi formatters that only strip markup; number/date/time/amount/phone/acronym formatters speak English.
LANGUAGE_NEUTRAL_FORMATTERS = ("markdown", "asterisk", "stripAsterisk", "quote", "newline")
# Said the way Danes say them; a workspace's own entry for the same term wins.
DEFAULT_PRONUNCIATIONS = ({"term": "AI", "say": "ej aj"},)


def catalog() -> list[dict]:
    """What customers see. Never names the speech provider."""
    return [{"key": k, **{f: v[f] for f in ("name", "gender", "image", "description")}, "sample": sample_available(k)}
            for k, v in STANDARD_VOICES.items()]


SAMPLE_TEXT = ("Hej, du har ringet til Hansens VVS. Jeg hedder {name}, og jeg tager telefonen for firmaet. "
               "Hvad kan jeg hjælpe dig med i dag?")


def sample_available(key: str) -> bool:
    s = get_settings()
    provider = STANDARD_VOICES[key]["voice"]["provider"]
    return bool(s.elevenlabs_api_key) if provider == "11labs" else bool(s.azure_speech_key)


def _sample_key(key: str) -> str:
    import hashlib

    v = STANDARD_VOICES[key]
    h = hashlib.sha256(f"{v['voice']}|{SAMPLE_TEXT.format(name=v['name'])}".encode()).hexdigest()[:12]
    return f"cache/platform/standard-samples/{key}-{h}.mp3"


def sample_audio(key: str) -> bytes:
    """A short MP3 of a standard voice, rendered once by the provider and then served from voice storage."""
    from app.core.errors import NotImplementedYet
    from app.modules.voices import storage

    if not sample_available(key):
        raise NotImplementedYet("Lydprøven er ikke klar endnu", code="voice_sample_not_configured")
    skey = _sample_key(key)
    if (cached := storage.get(skey)) is not None:
        return cached
    v = STANDARD_VOICES[key]
    text = SAMPLE_TEXT.format(name=v["name"])
    voice = v["voice"]
    if voice["provider"] == "11labs":
        from app.modules.telephony import vapi

        audio = vapi.voice_preview(voice["voiceId"], voice["model"], text)
    else:
        audio = _azure_tts(voice["voiceId"], text)
    storage.put(skey, audio, "audio/mpeg")
    return audio


def _azure_tts(voice_name: str, text: str) -> bytes:
    from xml.sax.saxutils import escape

    import httpx

    from app.core.errors import ApiError

    s = get_settings()
    ssml = (f"<speak version='1.0' xml:lang='da-DK'><voice name='{escape(voice_name)}'>{escape(text)}</voice></speak>")
    try:
        r = httpx.post(f"https://{s.azure_speech_region}.tts.speech.microsoft.com/cognitiveservices/v1",
                       headers={"Ocp-Apim-Subscription-Key": s.azure_speech_key or "", "Content-Type": "application/ssml+xml",
                                "X-Microsoft-OutputFormat": "audio-24khz-48kbitrate-mono-mp3", "User-Agent": "dialogbot"},
                       content=ssml.encode(), timeout=30.0)
    except httpx.HTTPError as e:
        raise ApiError("Lydprøven kunne ikke hentes", code="voice_sample_failed", status_code=502) from e
    if r.status_code >= 400:
        raise ApiError(f"Lydprøven kunne ikke laves ({r.status_code})", code="voice_sample_failed", status_code=502)
    return r.content


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
    own = list(vs.pronunciations if vs else [])
    taken = {str(e.get("term", "")).strip().lower() for e in own}
    own += [e for e in DEFAULT_PRONUNCIATIONS if e["term"].lower() not in taken]
    entries = sorted(own, key=lambda x: -len(str(x.get("term", ""))))
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
