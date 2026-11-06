"""The test profiles and the capability matrix.

A–D are the base prompt's profiles, E/F the addendum's (its C+ is folded into C, see there). A and B are PRODUCTION-path profiles (Vapi decides the
recogniser); C, C+, D, E, F are DIRECT profiles run through our adapters on replayed audio, and – for D, E and F –
also live through the existing Vapi custom-transcriber bridge (`telephony/linden.py`), so they can be tried as real
calls with the same LLM, instructions, customer context, booking tools and Peter's voice. The conversation runtime is
therefore Vapi for every profile: no second framework (no LiveKit/Pipecat) was added, because the project already has
an own integration that can carry all of them. See docs/voice/stemmetest.md for the reasoning and its limits.

Statuses in the matrix are only ever "verificeret" (checked against docs/SDK/tests, source named), "ikke understøttet"
or "ikke testet". Nothing is marked verified from a marketing page.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from app.modules.stt import adapters

V, N, T = "verificeret", "ikke understøttet", "ikke testet"
CHECKED = "2026-11-03"


@dataclass(frozen=True)
class Profile:
    id: str
    label: str
    purpose: str
    adapter: str | None                 # None = the production path (Vapi chooses), not runnable as a direct replay
    model: str | None
    turn_owner: str                     # EXACTLY ONE component closes the customer's turn
    needs: tuple[str, ...] = ()         # settings that must be present, else "Mangler adgang"
    live: str = ""                      # how it is tried as a real call
    notes: str = ""
    matrix: dict = field(default_factory=dict)


def _m(model, danish, vocab, segments, turns, diar, region, config, src) -> dict:
    return {"model": model, "dansk": danish, "ordliste": vocab, "segmenter": segments, "taleture": turns,
            "taleradskillelse": diar, "region": region, "konfiguration": config, "kilde": src, "kontrolleret": CHECKED}


PROFILES: tuple[Profile, ...] = (
    Profile("A", "A · Nuværende", "Baseline: versionsfast snapshot af opsætningen, som den er (Deepgram Nova-3 via Vapi)",
            None, "nova-3", "Vapi (startSpeakingPlan)", live="Vapi-assistent som i produktion",
            notes="Replay af samme lyd er ikke muligt: Vapi kan ikke få injiceret en optagelse (ingen opfundet replay). "
                  "A måles i live-opkald og browser. Ændringer mellem A og B/D er model OG samtalestyring.",
            matrix=_m("Deepgram nova-3 (Vapi)", V + " (da)", V + " (keyterm, højst 50)", T, V + " (Vapis startSpeakingPlan, se PACING)", N + " (ikke brugt)", T, "VAPI_TRANSCRIBER_JSON",
                      "docs/voice/stt-comparison.md; telephony/vapi.py DEFAULT_TRANSCRIBER")),
    Profile("B", "B · Vapi + Speechmatics", "Vapis indbyggede Speechmatics-integration, dansk, med navneordbog",
            None, None, "Vapi (startSpeakingPlan)", needs=("speechmatics_api_key",),
            live='VAPI_TRANSCRIBER_JSON={"provider":"speechmatics","language":"da"}',
            notes="Vapi eksponerer ikke den bagvedliggende model; den skrives ikke ind i konfigurationen. Vapis "
                  "dokumentation nævner ikke Agent STT/Linden for den native integration.",
            matrix=_m("ukendt (Vapi vælger)", V + " (da)", V + " (customVocabulary)", T, V + " (Vapis startSpeakingPlan)", T, T,
                      "VAPI_TRANSCRIBER_JSON", "docs.vapi.ai/providers/transcriber/speechmatics (3/11 2026)")),
    Profile("C", "C · Direkte Realtime (Enhanced)", "Speechmatics Realtime direkte med model enhanced eksplicit, samme ordbog som B",
            "speechmatics-rt", "enhanced", "Speechmatics (EndOfUtterance) / replay-flush",
            needs=("speechmatics_api_key",), live="Kun replay (kontrol mod B); ingen egen samtalebro",
            notes="Lille transskriptionsadapter, ingen agentplatform. Adskiller integrationens effekt fra et modelskift. C+ (Direkte Enhanced) er ikke en separat profil: C sender allerede modellen `enhanced` eksplicit med samme opsætning, så C+ ville være en dobbeltkørsel; det anmodede modelnavn registreres i hver kørsel.",
            matrix=_m("enhanced (RT)", V + " (da)", V + " (additional_vocab, sounds_like)",
                      V + " (AddTranscript/AddPartialTranscript)", V + " (EndOfUtterance, ForceEndOfUtterance)",
                      V + " (diarization)", V + " (SDK-standard wss://eu2.rt.speechmatics.com/v2; SPEECHMATICS_RT_URL overstyrer)", "TranscriptionConfig",
                      "speechmatics-rt 1.2.2 (installeret SDK)")),
    Profile("D", "D · Direkte Agent STT (Linden)", "Speechmatics linden-1 via /v2/agent: genkendelse og samtaleforløb",
            "speechmatics-agent", "linden-1", "Speechmatics (VAD, EndOfTurn) / replay-flush (external)",
            needs=("speechmatics_api_key",),
            live='VAPI_TRANSCRIBER_JSON={"provider":"custom-transcriber"} (broen i telephony/linden.py)',
            notes="Bevares ved siden af Enhanced; Linden antages ikke at genkende dansk bedre. Den indbyggede VAD kan ikke "
                  "konfigureres. I live-opkald lukker Vapi turen; broen sender kun delvis/endelig tekst.",
            matrix=_m("linden-1", V + " (da)", V + " (additional_vocab, ≤1000)", V + " (AddSegment/AddPartialSegment)",
                      V + " (vad | external, ForceEndOfUtterance)", V + " (labels S1/S2 er sessionslokale)",
                      V + " (som C: eu2 som standard, SPEECHMATICS_RT_URL overstyrer)", "TranscriptionConfig + TurnConfig; ikke max_delay",
                      "speechmatics-agent-stt 0.3.0; docs.speechmatics.com/speech-to-text/agent-stt")),
    Profile("E", "E · Direkte Soniox", "Soniox (samme model som telefonbroen: SONIOX_MODEL, ellers stt-rt-v5) med dansk og kontekst/ordliste",
            "soniox", None, "Soniox (semantisk endpoint, <end>) / replay-finalize",
            needs=("soniox_api_key",), live="Gennem broen med ?stt=soniox (Vapi lukker turen)",
            notes="<end> og <fin> er kontroltokens og kommer aldrig i kundens tekst. Aggressiv endpointing kan koste "
                  "nøjagtighed (Soniox' egen advarsel); standardværdier bruges, intet tunes uden måling. Modellen er "
                  "den, broen kører (SONIOX_MODEL, ellers stt-rt-v5); STEMMETEST_SONIOX_MODEL overstyrer KUN replayet "
                  "(test af fx stt-rt-v6 uden at røre opkald). Den anmodede model står på hver kørsel.",
            matrix=_m("SONIOX_MODEL, ellers stt-rt-v5 (v5 udfases 15/12 2026 iflg. docs.soniox.com/stt/models); v6 via STEMMETEST_SONIOX_MODEL", V + " (language_hints=[da])", V + " (context.terms, op til 8000 tokens)",
                      V + " (final/non-final tokens)", V + " (enable_endpoint_detection → <end>; finalize → <fin>)",
                      V + " (enable_speaker_diarization; ikke brugt)", T + " (Soniox data residency er ikke undersøgt)",
                      "start-besked + control-beskeder", "docs.soniox.com/stt/api-reference/websocket-api (3/11 2026)")),
    Profile("F", "F · Direkte ElevenLabs STT", "ElevenLabs scribe_v2_realtime (talegenkendelse – ikke stemmegenerering)",
            "elevenlabs-scribe", "scribe_v2_realtime", "lokal regel (VAD-commit) / replay-commit",
            needs=("elevenlabs_api_key",), live="Gennem broen med ?stt=elevenlabs (Vapi lukker turen)",
            notes="Et committed_transcript er ikke bevis for, at kunden er færdig. Rå committed-tekst scores; "
                  "transcript_edit bruges aldrig. Keyterms koster +20 % og er højst 50.",
            matrix=_m("scribe_v2_realtime", V + " (language_code=da)", V + " (keyterms, højst 50)",
                      V + " (partial/committed_transcript)", V + " (commit_strategy vad | manual; turn_prediction findes, bruges ikke)",
                      N + " (ikke brugt)", T + " (region er ikke undersøgt)", "forespørgselsparametre + input_audio_chunk",
                      "elevenlabs.io/docs/api-reference/speech-to-text/v-1-speech-to-text-realtime (3/11 2026)")),
)

BY_ID = {p.id: p for p in PROFILES}
ENV_NAMES = {"speechmatics_api_key": "SPEECHMATICS_API_KEY", "soniox_api_key": "SONIOX_API_KEY",
             "elevenlabs_api_key": "ELEVENLABS_API_KEY"}


def access(p: Profile) -> dict:
    """{status: 'klar' | 'mangler_adgang', missing: [...]} – read from settings, values never returned."""
    from app.config import get_settings

    s = get_settings()
    missing = [ENV_NAMES.get(n, n) for n in p.needs if not getattr(s, n, None)]
    if p.adapter is None:
        return {"status": "ikke_replaybar", "missing": missing,
                "reason": "Produktionsruten via Vapi; kan ikke få injiceret en optagelse. Måles i live-opkald/browser."}
    if missing:
        return {"status": "mangler_adgang", "missing": missing, "reason": "Mangler " + ", ".join(missing)}
    return {"status": "klar", "missing": [], "reason": ""}


def effective_model(p: Profile) -> str | None:
    """The model a replay of this profile requests right now. E follows the bridge (SONIOX_MODEL, else stt-rt-v5)
    unless STEMMETEST_SONIOX_MODEL overrides it for the test alone."""
    if p.adapter == "soniox":
        from app.config import get_settings

        s = get_settings()
        return s.stemmetest_soniox_model or s.soniox_model or "stt-rt-v5"
    return p.model


def describe(p: Profile) -> dict:
    return {"id": p.id, "label": p.label, "purpose": p.purpose, "adapter": p.adapter, "model": effective_model(p),
            "turn_owner": p.turn_owner, "live": p.live, "notes": p.notes, "capabilities": p.matrix, "access": access(p)}


def adapter_for(p: Profile) -> type[adapters.Adapter]:
    return adapters.ADAPTERS[p.adapter]  # raises KeyError for A/B – they are not direct profiles
