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


def catalog() -> list[dict]:
    return [{"key": k, **{f: v[f] for f in ("name", "gender", "image", "description")}} for k, v in STANDARD_VOICES.items()]


def chosen(db: OrmSession, ws_id: uuid.UUID) -> str | None:
    from app.models import WorkspaceVoiceSettings

    vs = db.get(WorkspaceVoiceSettings, ws_id)
    key = vs.standard_voice if vs else None
    return key if key in STANDARD_VOICES else None


def provider_voice(db: OrmSession, ws_id: uuid.UUID, number=None) -> dict:
    """Vapi voice for a call: the number's ElevenLabs voice → the workspace's chosen standard voice →
    VAPI_VOICE_JSON → the default Danish standard voice (so the phone never falls back to a non-Danish voice)."""
    from app.modules.telephony import vapi

    if number is not None and (own := vapi.voice_config(number)):
        return own
    if key := chosen(db, ws_id):
        return dict(STANDARD_VOICES[key]["voice"])
    return vapi._json_setting(get_settings().vapi_voice_json) or dict(STANDARD_VOICES[DEFAULT]["voice"])
