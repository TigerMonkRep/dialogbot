"""Real integration runs: one known recording through each recogniser that has a key in the environment.

Skipped without keys (nothing is mocked here, nothing is invented). Passing means the connection, the wire format and our
adapter work end to end and Danish text came back; it does NOT rank the providers – that is `python -m app.modules.stt.cli`
on human recordings."""
from __future__ import annotations

import asyncio
import os

import pytest

from app.config import get_settings
from app.modules.stt import manifest, profiles, replay

CASE = manifest.get("S03")


@pytest.mark.skipif(not os.environ.get("RUN_LIVE_STT"), reason="sæt RUN_LIVE_STT=1 og udbydernes nøgler for rigtige kørsler")
@pytest.mark.parametrize("pid", ["C", "D", "E", "F"])
def test_known_recording_through_the_real_service(pid):
    get_settings.cache_clear()
    p = profiles.BY_ID[pid]
    if profiles.access(p)["status"] != "klar":
        pytest.skip(profiles.access(p)["reason"])
    pcm, rate = manifest.read_wav(manifest.audio_path(CASE))
    r = asyncio.run(replay.run_audio(p, pcm, rate, reference=CASE["text"], expected=CASE["entities"],
                                     vocabulary=manifest.vocabulary(), mode="controlled"))
    assert r["status"] == "ok", r.get("error")
    assert r["transcript_raw"].strip() and r["wer"]["wer"] is not None
    assert r["timing"]["final_after_audio_s"] is not None
    print(pid, r["requested_model"], r["reported_model"], r["sdk"], round(r["wer"]["wer"], 3))
