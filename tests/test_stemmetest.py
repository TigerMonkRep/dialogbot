"""Stemmetest: the recogniser adapters, the turn assembler, the metrics, the manifest, the replay and the operator API.

Everything here is a MOCK test (provider messages are written out by hand in the documented wire format) except where a
test says "replay with a scripted adapter"; none of it proves how a provider performs on Danish. Real integration
runs need the provider keys – see docs/voice/stemmetest.md and `tests/test_stemmetest_live.py` (skipped without keys)."""
from __future__ import annotations

import array
import asyncio
import base64
import json
import math
import uuid as uuid_mod

import pytest
from sqlalchemy import select

from app.config import get_settings
from app.models import SttTestRun
from app.modules.stt import adapters, manifest, metrics, profiles, replay, service
from app.modules.stt.events import SttEvent, TurnAssembler
from app.modules.telephony import linden, vapi

from .test_telephony import SECRET


def ev(kind, text="", start=None, end=None, at=0.0, source="provider"):
    return SttEvent(kind=kind, text=text, audio_start=start, audio_end=end, at=at, source=source)


# --------------------------------------------------------------------------- the turn assembler

def test_a_partial_replaces_the_previous_partial_and_never_repeats_text():
    a = TurnAssembler()
    for t in ["vi", "vi bliver", "vi bliver fire"]:
        a.feed(ev("partial", t))
    assert a.partial == "vi bliver fire" and a.turns == []
    a.feed(ev("final", "Vi bliver fire.", 0.0, 1.2))
    assert a.partial == "" and a.open_text == "Vi bliver fire."


def test_several_finals_in_one_turn_keep_their_order_and_one_final_is_not_a_finished_turn():
    a = TurnAssembler()
    a.feed(ev("final", "Vi bliver fire", 0.0, 1.0))
    a.feed(ev("final", "nej seks personer.", 1.4, 2.6))
    assert a.turns == []  # no owner has said the customer is done
    turn = a.feed(ev("turn_ended"))
    assert turn.segments == ["Vi bliver fire", "nej seks personer."] and turn.text == "Vi bliver fire nej seks personer."


def test_a_redelivered_final_counts_once():
    a = TurnAssembler()
    for _ in range(3):
        a.feed(ev("final", "Ja.", 0.0, 0.4))
    a.close("provider")
    assert [t.segments for t in a.turns] == [["Ja."]]


def test_an_end_of_turn_with_nothing_in_it_makes_no_turn():
    a = TurnAssembler()
    a.feed(ev("partial", "hm"))
    assert a.feed(ev("turn_ended")) is None and a.turns == [] and a.partial == ""


def test_a_late_final_for_audio_the_last_turn_already_covered_is_attached_not_a_phantom_turn():
    a = TurnAssembler()
    a.feed(ev("final", "Jeg hedder Søren", 0.0, 1.5))
    a.feed(ev("turn_ended"))
    a.feed(ev("final", "Brøndum.", 1.5, 2.0))  # arrives after the close, belongs to nothing new? it is NEW audio
    assert len(a.turns) == 1 and a.open_text == "Brøndum."
    a.close("end_of_stream")
    # but text about audio the first turn already covered goes back onto it
    b = TurnAssembler()
    b.feed(ev("final", "Mit navn er", 0.0, 1.0))
    b.feed(ev("turn_ended"))
    b.feed(ev("final", "er", 0.6, 1.0))
    assert len(b.turns) == 1 and b.turns[0].late == ["er"] and b._open.segments == []


def test_unfinalised_text_is_kept_at_end_of_stream_not_lost():
    a = TurnAssembler()
    a.feed(ev("partial", "halv syv"))
    t = a.close("end_of_stream")
    assert t.text == "halv syv" and a.text == "halv syv"


# --------------------------------------------------------------------------- Speechmatics

def _feed(adapter, messages):
    out = TurnAssembler()
    adapter._sink = out.feed
    for m in messages:
        adapter.handle(m)
    return out


def _cfg(**kw):
    return adapters.AdapterConfig(**kw)


def test_agent_stt_segments_and_turns_follow_the_documented_messages():
    a = adapters.SpeechmaticsAgent(_cfg(), "k")
    asm = _feed(a, [
        {"message": "RecognitionStarted", "id": "sess-1"},
        {"message": "SpeechStarted"}, {"message": "StartOfTurn"},
        {"message": "AddPartialSegment", "segment": {"transcript": "vi bliver"}, "metadata": {"start_time": 0, "end_time": 1}},
        {"message": "AddSegment", "segment": {"transcript": "Vi bliver fire."}, "metadata": {"start_time": 0.0, "end_time": 1.4}},
        {"message": "AddSegment", "segment": {"transcript": "Nej, seks."}, "metadata": {"start_time": 1.8, "end_time": 2.6}},
        {"message": "SpeechEnded"}, {"message": "EndOfTurn"},
    ])
    assert a.requested_model == "linden-1" and a.session_id == "sess-1"
    assert a.reported_model is None  # the service does not say; never guessed
    assert len(asm.turns) == 1 and asm.turns[0].segments == ["Vi bliver fire.", "Nej, seks."]
    kinds = [e.kind for e in a.events]
    assert "speech_started" in kinds and "turn_started" in kinds and kinds.count("turn_ended") == 1


def test_agent_stt_external_mode_names_the_replay_as_the_turn_owner():
    assert "replay" in adapters.SpeechmaticsAgent(_cfg(controlled=True), "k").turn_owner
    assert "VAD" in adapters.SpeechmaticsAgent(_cfg(), "k").turn_owner


def test_realtime_transcripts_map_to_partial_final_and_end_of_utterance():
    a = adapters.SpeechmaticsRealtime(_cfg(), "k")
    asm = _feed(a, [
        {"message": "AddPartialTranscript", "metadata": {"start_time": 0, "end_time": 0.8, "transcript": "halv"}},
        {"message": "AddTranscript", "metadata": {"start_time": 0, "end_time": 1.1, "transcript": "halv syv."}},
        {"message": "EndOfUtterance"}, {"message": "EndOfTranscript"},
    ])
    assert a.requested_model == "enhanced" and a.finished.is_set()
    assert asm.turns[0].text == "halv syv."


def test_a_speechmatics_error_ends_the_session_and_is_recorded():
    a = adapters.SpeechmaticsRealtime(_cfg(), "k")
    a.handle({"message": "Error", "type": "quota_exceeded", "reason": "no quota"})
    assert a.events[-1].kind == "error" and a.finished.is_set()


# --------------------------------------------------------------------------- Soniox

def _tok(text, final=True, start=None, end=None):
    return {"text": text, "is_final": final, **({"start_ms": start} if start is not None else {}),
            **({"end_ms": end} if end is not None else {})}


def test_soniox_buffers_final_tokens_and_releases_them_at_the_end_marker_without_the_marker():
    a = adapters.Soniox(_cfg(), "k")
    asm = _feed(a, [
        {"tokens": [_tok("Vi", False), _tok(" bliver", False)]},
        {"tokens": [_tok("Vi", True, 0, 200), _tok(" bliver", True, 200, 600), _tok(" fire", False)]},
        {"tokens": [_tok(" fire", True, 600, 900), _tok("<end>", True)]},
        {"tokens": [], "finished": True},
    ])
    assert asm.turns[0].text == "Vi bliver fire"          # '<end>' never reaches the customer's text
    assert "<end>" not in asm.text
    ended = [e for e in a.events if e.kind == "turn_ended"]
    assert len(ended) == 1 and ended[0].source == "provider"
    final = next(e for e in a.events if e.kind == "final")
    assert (final.audio_start, final.audio_end) == (0.0, 0.9)
    partials = [e.text for e in a.events if e.kind == "partial"]
    assert partials[0] == "Vi bliver"  # a later partial replaces, it does not append


def test_soniox_fin_marker_is_our_own_flush_not_a_provider_turn():
    a = adapters.Soniox(_cfg(controlled=True), "k")
    asm = _feed(a, [{"tokens": [_tok("Jeg", True, 0, 100), _tok(" ved", True, 100, 300), _tok("<fin>", True)]}])
    assert asm.open_text == "Jeg ved" and asm.turns == []
    assert not [e for e in a.events if e.kind == "turn_ended"]


def test_soniox_error_response_is_an_error_event():
    a = adapters.Soniox(_cfg(), "k")
    a.handle({"tokens": [], "error_code": 503, "error_type": "service_unavailable", "error_message": "x"})
    assert a.events[-1].kind == "error" and "service_unavailable" in a.events[-1].text and a.finished.is_set()


def test_soniox_start_message_uses_the_documented_fields_and_no_test_answers():
    vocab = [{"content": "Gastro Hall"}, {"content": "Pernille"}]
    m = adapters.Soniox(_cfg(sample_rate=8000, vocabulary=vocab), "k").start_message()
    assert m["model"] == "stt-rt-v5" and m["audio_format"] == "pcm_s16le" and m["sample_rate"] == 8000
    assert m["num_channels"] == 1 and m["language_hints"] == ["da"] and m["enable_endpoint_detection"] is True
    assert m["context"]["terms"] == ["Gastro Hall", "Pernille"]
    assert "api_key" not in m  # deprecated in the start request; the key goes in the Authorization header
    assert adapters.Soniox(_cfg(controlled=True), "k").start_message()["enable_endpoint_detection"] is False
    # endpoint tuning is only sent when someone asked for it
    assert "endpoint_sensitivity" not in m
    tuned = adapters.Soniox(_cfg(soniox_endpoint={"endpoint_sensitivity": 0.3, "bogus": 1}), "k").start_message()
    assert tuned["endpoint_sensitivity"] == 0.3 and "bogus" not in tuned


# --------------------------------------------------------------------------- ElevenLabs Scribe

def test_scribe_partial_and_committed_transcripts_and_reported_model():
    a = adapters.ElevenLabsScribe(_cfg(), "k")
    asm = _feed(a, [
        {"message_type": "session_started", "session_id": "s1", "config": {"model_id": "scribe_v2_realtime"}},
        {"message_type": "partial_transcript", "text": "hello wor"},
        {"message_type": "committed_transcript", "text": "Jeg vil gerne booke."},
        {"message_type": "partial_transcript", "text": "fredag"},
        {"message_type": "committed_transcript", "text": "Fredag."},
    ])
    assert a.reported_model == "scribe_v2_realtime" and a.session_id == "s1"
    assert asm.turns == []  # a commit is not proof the customer is done: no turn without an owner
    assert asm.close("derived:første commit").text == "Jeg vil gerne booke. Fredag."


def test_scribe_errors_are_recorded_and_edited_transcripts_are_ignored():
    a = adapters.ElevenLabsScribe(_cfg(), "k")
    a.handle({"message_type": "edited_transcript", "text": "x", "edited_text": "y"})
    assert not [e for e in a.events if e.kind in ("partial", "final")]
    a.handle({"message_type": "rate_limited", "error": "slow down"})
    assert a.events[-1].kind == "error" and a.finished.is_set()


def test_scribe_url_has_the_documented_parameters_and_caps_keyterms_at_50():
    vocab = [{"content": f"Navn{i}"} for i in range(80)]
    url = adapters.ElevenLabsScribe(_cfg(sample_rate=8000, vocabulary=vocab), "k").url()
    assert url.startswith("wss://api.elevenlabs.io/v1/speech-to-text/realtime?")
    for part in ("model_id=scribe_v2_realtime", "audio_format=pcm_8000", "language_code=da", "commit_strategy=vad"):
        assert part in url
    assert url.count("keyterms=") == 50
    assert "transcript_edit" not in url and "entity_detection" not in url  # raw text is what is scored
    assert "commit_strategy=manual" in adapters.ElevenLabsScribe(_cfg(controlled=True), "k").url()


def test_scribe_sends_base64_chunks_and_flush_commits():
    sent = []

    class Ws:
        async def send(self, m):
            sent.append(json.loads(m))

    a = adapters.ElevenLabsScribe(_cfg(), "k")
    a.ws = Ws()
    asyncio.run(a.send_audio(b"\x01\x02"))
    asyncio.run(a.flush())
    assert sent[0]["message_type"] == "input_audio_chunk" and base64.b64decode(sent[0]["audio_base_64"]) == b"\x01\x02"
    assert sent[0]["commit"] is False and sent[1]["commit"] is True


def test_soniox_finish_is_an_empty_text_frame_not_empty_audio():
    sent = []

    class Ws:
        async def send(self, m):
            sent.append(m)

    a = adapters.Soniox(_cfg(), "k")
    a.ws = Ws()
    asyncio.run(a.finish())
    asyncio.run(a.flush())
    assert sent[0] == "" and json.loads(sent[1]) == {"type": "finalize"}


# --------------------------------------------------------------------------- metrics

def test_wer_uses_the_danish_normalisation_so_digits_and_words_compare_equal():
    assert metrics.wer("Mit nummer er tyve tredive fyrre halvtreds", "mit nummer er 20 30 40 50")["errors"] == 0
    w = metrics.wer("Vi bliver seks personer", "vi bliver fire personer")
    assert w["errors"] == 1 and w["ref_words"] == 4 and w["wer"] == 0.25


def test_a_wrong_digit_or_time_is_a_miss_whatever_the_rest_looks_like():
    exp = [{"type": "telefon", "value": "20 30 40 50"}, {"type": "tid", "value": "halv syv", "alt": ["klokken atten tredive"]},
           {"type": "antal", "value": "seks"}]
    ok = metrics.entities(exp, "Mit nummer er 20 30 40 50, klokken 18.30, vi er seks.")
    assert ok["by_type"] == {"telefon": {"hits": 1, "total": 1}, "tid": {"hits": 1, "total": 1}, "antal": {"hits": 1, "total": 1}}
    bad = metrics.entities(exp, "Mit nummer er 20 30 40 51, klokken 19.30, vi er fire.")
    assert bad["by_type"]["telefon"]["hits"] == 0 and bad["by_type"]["tid"]["hits"] == 0 and len(bad["missed"]) == 3


def test_a_correction_counts_only_when_the_final_value_is_heard():
    exp = [{"type": "antal", "value": "seks"}]
    assert metrics.entities(exp, "Vi bliver 4 nej 6 personer")["by_type"]["antal"]["hits"] == 1
    assert metrics.entities(exp, "Vi bliver 4 personer")["by_type"]["antal"]["hits"] == 0


def test_timing_stats_report_the_sample_size_and_flag_small_samples():
    s = metrics.stats([0.5, 0.7, 0.9, 1.5])
    assert s == {"n": 4, "median": 0.8, "p95": 1.5, "uncertain": True}
    assert metrics.stats([]) == {"n": 0, "median": None, "p95": None, "uncertain": True}
    assert metrics.stats([float(i) for i in range(1, 41)])["uncertain"] is False


def test_price_is_never_invented():
    assert metrics.price("soniox", 3600, None) == {"audio_seconds": 3600, "usd": None, "note": "pris ikke angivet"}
    assert metrics.price("soniox", 1800, '{"soniox": 0.12}')["usd"] == 0.06


# --------------------------------------------------------------------------- manifest

def test_the_manifest_has_the_required_cases_and_a_clean_tuning_final_split():
    short, scen = manifest.cases(), manifest.scenarios()
    assert len(short) >= 30 and 5 <= len(scen) <= 10
    assert {c["split"] for c in short} == {"tuning", "final"}
    assert len({c["id"] for c in [*short, *scen]}) == len(short) + len(scen)
    groups = {c["group"] for c in short}
    for g in ("steder", "navne", "rettelse_antal", "dato_tid", "telefon", "taenkepause", "variation", "stoej",
              "bekraeftelse", "afbrydelse", "rettelse_booking", "tavshed"):
        assert g in groups, g
    for name in ("Gastro Hall", "Racehall", "Aarhus", "Viby", "Højbjerg", "Dialogbot"):
        assert any(name in c["text"] for c in short)
    assert any(c["synthetic"] for c in short) and all(c["synthetic"] == bool(c["audio"]) for c in short)
    assert manifest.load()["timezone"] == "Europe/Copenhagen"


KNOWN_SYNTHETIC_K = {"K02", "K08", "K10", "K11", "K12", "K13", "K14", "K16", "K17", "K18", "K20", "K21", "K22", "K25"}


def test_cases_without_a_human_recording_say_so_instead_of_being_scored():
    over = manifest.overview()
    assert over["counts"]["kort"] == len(manifest.cases())
    missing = [c for c in over["cases"] if c["status"] == "mangler_optagelse"]
    ready = [c for c in over["cases"] if c["status"] == "klar"]
    assert missing and {"S01", "S02", "S03"} <= {c["id"] for c in ready}
    assert all(c["id"].startswith(("S", "T", "N")) or c["id"] in KNOWN_SYNTHETIC_K for c in ready)
    assert all(c["synthetic"] for c in ready)  # nothing here is a human recording yet; the page must say so


def test_the_shared_vocabulary_never_contains_a_test_answer():
    vocab = [v["content"].lower() for v in manifest.vocabulary()]
    assert len(vocab) > 100
    for c in manifest.cases():
        for e in c["entities"]:
            if e["type"] in ("telefon", "mail", "tid", "antal", "dato"):
                assert e["value"].lower() not in vocab, e
        assert c["text"].lower() not in vocab
    assert "gastro hall" in vocab[:8]  # company terms come first, so ElevenLabs' 50-keyterm cap keeps them


def test_every_known_recording_is_a_readable_wav_with_the_stated_rate():
    for c in manifest.cases():
        p = manifest.audio_path(c)
        if p:
            pcm, rate = manifest.read_wav(p)
            assert rate == c["audio_rate"] and len(pcm) > rate


# --------------------------------------------------------------------------- the broad number/time/address benchmark

def test_a_perfect_transcript_scores_full_marks_on_every_case_with_audio():
    """If the facts a case expects are not in its own reference, the benchmark would punish a perfect recogniser."""
    for c in manifest.cases():
        if not c.get("audio") or not c["text"]:
            continue
        w = metrics.wer(c["text"], c["text"], c.get("reference_alts"))
        assert w["errors"] == 0, c["id"]
        got = metrics.entities(c["entities"], c["text"])
        assert not got["missed"], (c["id"], got["missed"])


def test_a_recogniser_that_writes_digits_instead_of_words_is_not_punished_for_a_correct_reading():
    cases = {c["id"]: c for c in manifest.cases()}
    for cid, written in (("T01", "Abonnementet koster 2.495 kr. om måneden."), ("T08", "Mit nummer er 20304567."),
                         ("T11", "Mit ordrenummer er 123456."), ("T06", "Firmaet blev stiftet i 1993."),
                         ("T14", "Kan vi sige kl. 13.45?"), ("T07", "Mit nummer er 42 71 68 99."),
                         ("T03", "Beløbet er 5.722,45 kr."), ("T19", "Gulvet er 122 m².")):
        c = cases[cid]
        w = metrics.wer(c["text"], written, c.get("reference_alts"))
        assert w["errors"] == 0, (cid, w)
        assert not metrics.entities(c["entities"], written)["missed"], cid


def test_the_closest_written_form_counts_and_a_wrong_number_is_still_wrong():
    c = next(x for x in manifest.cases() if x["id"] == "T08")
    assert metrics.wer(c["text"], "Mit nummer er 20304567.", c["reference_alts"])["reference_used"] == "alt"
    wrong = "Mit nummer er 20304568."
    assert metrics.wer(c["text"], wrong, c["reference_alts"])["errors"] > 0
    assert metrics.entities(c["entities"], wrong)["missed"]
    assert metrics.wer("a b", "a b")["errors"] == 0 and "reference_used" not in metrics.wer("a b", "a b")


def test_the_broad_set_covers_numbers_times_phone_numbers_addresses_and_noise_with_clean_pairs():
    cases = {c["id"]: c for c in manifest.cases()}
    groups = {c["group"] for c in cases.values() if c.get("audio")}
    for g in ("tal_beloeb", "tal_stor", "tal_telefon", "tal_nummer", "adresse", "tal_tid", "tal_enhed", "tal_rettelse",
              "kombineret", "stoej_tal"):
        assert g in groups, g
    types = {e["type"] for c in cases.values() if c.get("audio") for e in c["entities"]}
    assert {"beløb", "procent", "telefon", "tid", "dato", "postnummer", "vejnummer", "ordrenummer", "måleenhed",
            "årstal", "antal", "navn"} <= types
    noisy = [c for c in cases.values() if c["group"] == "stoej_tal"]
    assert len(noisy) == 6
    for n in noisy:  # every noisy case has the same words as a clean one: the drop can be measured on identical text
        assert any(c["text"] == n["text"] and c["group"] != "stoej_tal" for c in cases.values()), n["id"]
    assert sum(1 for c in cases.values() if c.get("audio")) >= 44
    assert sum(1 for c in cases.values() if c.get("audio") and c["split"] == "tuning") >= 10


def test_a_human_recording_replaces_the_synthetic_stand_in_without_touching_the_manifest(tmp_path, monkeypatch):
    import shutil

    case = next(c for c in manifest.cases() if c["id"] == "T01")
    assert manifest.is_synthetic(case) and manifest.audio_path(case).parent.name == "synthetic"
    shutil.copy(manifest.audio_path(case), tmp_path / "T01.wav")
    monkeypatch.setenv("STEMMETEST_AUDIO_DIR", str(tmp_path))
    get_settings.cache_clear()
    try:
        assert manifest.audio_path(case) == tmp_path / "T01.wav" and not manifest.is_synthetic(case)
    finally:
        get_settings.cache_clear()


def test_a_batch_runs_every_case_through_every_profile_one_after_the_other(api, fake_factory):
    op = api.operator()
    r = api.post(op, "/operator/stemmetest/batch", {"profiles": ["E"], "cases": ["S03", "T16"], "mode": "controlled"})
    assert r.status_code == 202, r.text
    assert r.json() == {"runs": 2, "profiles": ["E"]}
    runs = api.get(op, "/operator/stemmetest/runs").json()["runs"]
    assert {x["case_id"] for x in runs} == {"S03", "T16"} and all(x["status"] == "ok" for x in runs)
    row = next(x for x in api.get(op, "/operator/stemmetest/summary?mode=controlled").json()["rows"] if x["profile"] == "E")
    assert row["measured"]["cases"] == 2 and set(row["by_group"]) == {"steder", "tal_tid"}
    assert row["by_group"]["tal_tid"]["cases"] == 1 and row["by_group"]["tal_tid"]["entities"]["tid"]["total"] == 2
    assert api.post(op, "/operator/stemmetest/batch", {"profiles": ["Z"], "cases": "alle"}).status_code == 404
    assert api.post(op, "/operator/stemmetest/batch", {"profiles": ["E"], "cases": ["K01"]}).status_code == 422  # no audio


def test_batch_all_expands_to_every_case_with_audio_and_a_profile_without_access_is_recorded_not_run(db, monkeypatch):
    monkeypatch.delenv("SONIOX_API_KEY", raising=False)
    get_settings.cache_clear()
    try:
        todo = service.create_batch(db, user_id=None, profile_ids=["E"], case_ids="alle", mode="controlled", workspace_id=None)
        assert todo == {}  # Soniox has no key: every run is `mangler_adgang`, nothing is started
        rows = db.scalars(select(SttTestRun).where(SttTestRun.profile_id == "E")).all()
        assert len(rows) == sum(1 for c in manifest.cases() if manifest.audio_path(c))
        assert {r.status for r in rows} == {"mangler_adgang"}
    finally:
        get_settings.cache_clear()


# --------------------------------------------------------------------------- profiles and the capability matrix

def test_profiles_cover_the_baseline_and_the_addendum_and_say_who_owns_the_turn():
    ids = [p.id for p in profiles.PROFILES]
    assert ids == ["A", "B", "C", "D", "E", "F"]
    assert profiles.BY_ID["D"].model == "linden-1" and profiles.BY_ID["E"].model == "stt-rt-v5"
    assert profiles.BY_ID["F"].model == "scribe_v2_realtime" and profiles.BY_ID["C"].model == "enhanced"
    assert all(p.turn_owner for p in profiles.PROFILES)
    assert profiles.BY_ID["A"].adapter is None and profiles.BY_ID["B"].adapter is None  # no invented Vapi replay


def test_capability_statuses_are_only_the_three_allowed_words():
    for p in profiles.PROFILES:
        for k in ("dansk", "ordliste", "segmenter", "taleture", "taleradskillelse", "region"):
            v = p.matrix[k]
            assert v.startswith((profiles.V, profiles.N, profiles.T)), (p.id, k, v)
        assert p.matrix["kontrolleret"] == "2026-11-03" and p.matrix["kilde"]


def test_missing_keys_show_as_missing_access_with_the_env_name_only(monkeypatch):
    for n in ("SPEECHMATICS_API_KEY", "SONIOX_API_KEY", "ELEVENLABS_API_KEY"):
        monkeypatch.delenv(n, raising=False)
    get_settings.cache_clear()
    acc = profiles.access(profiles.BY_ID["E"])
    assert acc == {"status": "mangler_adgang", "missing": ["SONIOX_API_KEY"], "reason": "Mangler SONIOX_API_KEY"}
    monkeypatch.setenv("SONIOX_API_KEY", "sx-secret-value")
    get_settings.cache_clear()
    assert profiles.access(profiles.BY_ID["E"])["status"] == "klar"
    assert "sx-secret-value" not in json.dumps(profiles.describe(profiles.BY_ID["E"]))
    assert profiles.access(profiles.BY_ID["A"])["status"] == "ikke_replaybar"
    get_settings.cache_clear()


# --------------------------------------------------------------------------- replay with a scripted adapter

class Scripted(adapters.Adapter):
    """Plays a script: after `n` audio chunks it emits the given events; flush() emits `on_flush`."""

    id = "scripted"

    def __init__(self, cfg, script, on_flush=(), end=(), **kw):
        super().__init__(cfg, "k", **kw)
        self.requested_model = "scripted-1"
        self.turn_owner = "test"
        self.script, self.on_flush, self.end, self.chunks = script, on_flush, end, 0

    async def open(self):
        pass

    async def send_audio(self, pcm):
        self.chunks += 1
        for after, args in self.script:
            if after == self.chunks:
                self.emit(*args[:2], **(args[2] if len(args) > 2 else {}))

    async def flush(self):
        for args in self.on_flush:
            self.emit(*args[:2], **(args[2] if len(args) > 2 else {}))

    async def finish(self):
        for args in self.end:
            self.emit(*args[:2], **(args[2] if len(args) > 2 else {}))
        self.finished.set()

    async def close(self):
        pass


def _pcm(seconds=1.0, rate=16000):
    n = int(seconds * rate)
    return array.array("h", [int(3000 * math.sin(i / 9)) for i in range(n)]).tobytes()


def _run(profile_id, adapter_factory, mode, reference, expected=()):
    p = profiles.BY_ID[profile_id]
    return asyncio.run(replay.run_audio(p, _pcm(1.0), 16000, reference=reference, expected=list(expected),
                                        vocabulary=[{"content": "Gastro Hall"}], mode=mode, realtime=False,
                                        factory=lambda _id, cfg: adapter_factory(cfg), settle_s=0.5))


def test_controlled_replay_gives_one_turn_and_scores_the_raw_text():
    def make(cfg):
        return Scripted(cfg, [(3, ("partial", "vi bliver")), (6, ("final", "Vi bliver fire nej seks.", {"start": 0, "end": 0.9}))],
                        on_flush=[("final", "personer.", {"start": 0.9, "end": 1.1})])

    r = _run("D", make, "controlled", "Vi bliver fire nej seks personer",
             [{"type": "antal", "value": "seks"}])
    assert r["status"] == "ok" and r["turn_count"] == 1 and r["premature_split"] is False
    assert r["turns"][0]["closed_by"] == "external" and r["turns"][0]["segments"] == ["Vi bliver fire nej seks.", "personer."]
    assert r["wer"]["errors"] == 0 and r["entities"]["by_type"]["antal"] == {"hits": 1, "total": 1}
    assert r["requested_model"] == "linden-1" or r["requested_model"] == "scripted-1"
    assert r["timing"]["first_partial_s"] is not None and r["timing"]["flush_sent_after_audio_s"] is not None
    assert r["vocabulary"] == {"offered": 1, "used": 1}
    assert r["price"]["usd"] is None  # no price list configured


def test_natural_replay_flags_a_premature_split_by_the_providers_own_endpointing():
    def make(cfg):
        return Scripted(cfg, [(4, ("final", "Vi skal være", {"start": 0, "end": 0.4})), (5, ("turn_ended", "")),
                              (8, ("final", "syv personer.", {"start": 0.9, "end": 1.4}))],
                        end=[("turn_ended", "")])

    r = _run("E", make, "natural", "Vi skal være syv personer")
    assert r["turn_count"] == 2 and r["premature_split"] is True
    assert [t["closed_by"] for t in r["turns"]] == ["provider", "provider"]
    assert r["wer"]["errors"] == 0  # same words; the split is reported separately, not blamed on the model


def test_a_provider_error_is_a_recorded_result_not_a_crash():
    def make(cfg):
        a = Scripted(cfg, [(2, ("error", "forbindelse tabt"))])
        return a

    r = _run("E", make, "controlled", "hej")
    assert r["status"] == "fejl" and "forbindelse" in r["error"]


def test_a_missing_key_is_missing_access_not_a_failure(monkeypatch):
    monkeypatch.delenv("SONIOX_API_KEY", raising=False)
    get_settings.cache_clear()
    p = profiles.BY_ID["E"]
    r = asyncio.run(replay.run_audio(p, _pcm(0.3), 16000, reference="x", expected=[], vocabulary=[], realtime=False))
    assert r["status"] == "mangler_adgang" and "SONIOX_API_KEY" in r["error"]
    get_settings.cache_clear()


def test_silence_that_gets_words_is_flagged_not_hidden():
    def make(cfg):
        return Scripted(cfg, [], on_flush=[("final", "tak for ordet", {"start": 0, "end": 1})])

    r = _run("F", make, "controlled", "")
    assert r["wer"]["wer"] is None and r["wer"]["errors"] == 3 and r["transcript_raw"] == "tak for ordet"


# --------------------------------------------------------------------------- the bridge and the Vapi config

@pytest.fixture
def bridge_env(monkeypatch):
    monkeypatch.setenv("VAPI_SERVER_SECRET", SECRET)
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://api.dialogbot.dk")
    yield monkeypatch
    get_settings.cache_clear()


def test_the_bridge_url_names_the_recogniser_only_when_it_is_not_linden(bridge_env):
    get_settings.cache_clear()
    assert "stt=" not in linden.transcriber_config(None, [])["server"]["url"]
    assert linden.transcriber_config(None, [], "soniox")["server"]["url"].endswith("?stt=soniox")
    assert linden.chosen("nonsense") == "speechmatics-agent"


def test_stt_in_vapi_transcriber_json_selects_the_recogniser_and_never_reaches_vapi(bridge_env, db):
    bridge_env.setenv("VAPI_TRANSCRIBER_JSON", '{"provider": "custom-transcriber", "stt": "soniox"}')
    bridge_env.setenv("SONIOX_API_KEY", "sx-test")
    get_settings.cache_clear()
    t = vapi.transcriber_for(db, None)
    assert t["provider"] == "custom-transcriber" and "stt" not in t and "stt=soniox" in t["server"]["url"]
    bridge_env.delenv("SONIOX_API_KEY")
    get_settings.cache_clear()
    assert vapi.transcriber_for(db, None)["provider"] == "deepgram"  # no key → the call stays on the production path


def test_the_bridge_forwards_text_to_vapi_but_never_turn_events(bridge_env):
    sent = []

    class Sock:
        async def send_text(self, m):
            sent.append(json.loads(m))

    async def go():
        s = linden.Session(Sock(), None, None, [], "soniox")
        for e in (ev("partial", "halv"), ev("turn_started"), ev("final", "halv syv."), ev("turn_ended"), ev("speech_ended")):
            s._on_adapter_event(e)
        await asyncio.sleep(0.05)

    asyncio.run(go())
    assert [(m["transcriptType"], m["transcription"]) for m in sent] == [("partial", "halv"), ("final", "halv syv.")]
    assert all(m["channel"] == "customer" for m in sent)


# --------------------------------------------------------------------------- operator API

@pytest.fixture
def fake_factory(monkeypatch):
    monkeypatch.setenv("SONIOX_API_KEY", "sx-secret-test-value")
    get_settings.cache_clear()
    text = ("Goddag, du har ringet til Berle Pool. Hvad kan jeg gøre for dig?")

    def factory(adapter_id, cfg):
        return Scripted(cfg, [], on_flush=[("final", text, {"start": 0, "end": 3.0})])

    monkeypatch.setattr(service, "FACTORY", factory)
    yield
    get_settings.cache_clear()


def test_only_operators_reach_the_stemmetest(api, two_workspaces):
    tok = two_workspaces["tok_a"]
    assert api.get(tok, "/operator/stemmetest").status_code == 403
    assert api.post(tok, "/operator/stemmetest/runs", {"profile": "D", "case": "S03"}).status_code == 403


def test_overview_lists_profiles_manifest_and_honest_limits_without_secrets(api, fake_factory):
    op = api.operator()
    r = api.get(op, "/operator/stemmetest")
    assert r.status_code == 200, r.text
    body = r.json()
    assert [p["id"] for p in body["profiles"]] == ["A", "B", "C", "D", "E", "F"]
    assert body["testmode"] is True and body["browser_call"]["status"] == "ikke_bygget"
    assert body["manifest"]["counts"]["med_lyd"] == sum(1 for c in manifest.cases() if manifest.audio_path(c)) >= 47
    assert "sx-secret-test-value" not in r.text
    e = next(p for p in body["profiles"] if p["id"] == "E")
    assert e["access"]["status"] == "klar"
    f = next(p for p in body["profiles"] if p["id"] == "F")
    assert f["access"]["status"] in ("klar", "mangler_adgang")


def test_a_run_replays_stores_the_raw_result_and_shows_in_the_summary(api, fake_factory):
    op = api.operator()
    r = api.post(op, "/operator/stemmetest/runs", {"profile": "E", "case": "S03", "mode": "controlled"})
    assert r.status_code == 202, r.text
    run = api.get(op, f"/operator/stemmetest/runs/{r.json()['id']}").json()
    assert run["status"] == "ok" and run["wer"]["errors"] == 0 and run["synthetic"] is True
    assert run["transcript_raw"].startswith("Goddag") and run["turns"][0]["closed_by"] == "external"
    assert run["split"] == "final" and run["actual_profile"] == "E" and run["events"]
    rows = api.get(op, "/operator/stemmetest/summary?split=final&mode=controlled").json()["rows"]
    e = next(x for x in rows if x["profile"] == "E")
    assert e["status"] == "målt" and e["measured"]["cases"] == 1 and e["measured"]["wer"] == 0.0
    assert e["human_cases"] == 0 and "syntetisk" in e["note"]
    d = next(x for x in rows if x["profile"] == "D")
    assert d["status"] in ("Mangler adgang", "Ikke testet")
    a = next(x for x in rows if x["profile"] == "A")
    assert a["status"].startswith("Ikke replaybar")


def test_tuning_and_final_results_never_mix(api, fake_factory):
    op = api.operator()
    api.post(op, "/operator/stemmetest/runs", {"profile": "E", "case": "S01", "mode": "controlled"})  # tuning
    api.post(op, "/operator/stemmetest/runs", {"profile": "E", "case": "S03", "mode": "controlled"})  # final
    tun = {x["profile"]: x for x in api.get(op, "/operator/stemmetest/summary?split=tuning").json()["rows"]}
    fin = {x["profile"]: x for x in api.get(op, "/operator/stemmetest/summary?split=final").json()["rows"]}
    assert tun["E"]["measured"]["cases"] == 1 and fin["E"]["measured"]["cases"] == 1


def test_refusals_are_concrete(api, fake_factory):
    op = api.operator()
    r = api.post(op, "/operator/stemmetest/runs", {"profile": "A", "case": "S03"})
    assert r.status_code == 409 and r.json()["code"] == "profile_not_replayable"
    r = api.post(op, "/operator/stemmetest/runs", {"profile": "E", "case": "K01"})
    assert r.status_code == 409 and r.json()["code"] == "recording_missing"
    assert api.post(op, "/operator/stemmetest/runs", {"profile": "Z", "case": "S03"}).status_code == 404
    assert api.post(op, "/operator/stemmetest/runs", {"profile": "E", "case": "SC01"}).status_code == 404  # a scenario is no clip


def test_a_profile_without_access_is_recorded_as_missing_access_and_not_as_a_result(api, monkeypatch):
    monkeypatch.delenv("SONIOX_API_KEY", raising=False)
    get_settings.cache_clear()
    op = api.operator()
    r = api.post(op, "/operator/stemmetest/runs", {"profile": "E", "case": "S03"})
    assert r.status_code == 202 and r.json()["status"] == "mangler_adgang" and "SONIOX_API_KEY" in r.json()["error"]
    row = next(x for x in api.get(op, "/operator/stemmetest/summary").json()["rows"] if x["profile"] == "E")
    assert row["status"] == "Mangler adgang" and "measured" not in row
    get_settings.cache_clear()


def test_a_fallback_run_does_not_count_for_the_original_profile(api, fake_factory, db):
    from app.models import SttTestRun

    op = api.operator()
    api.post(op, "/operator/stemmetest/runs", {"profile": "E", "case": "S03"})
    run = db.query(SttTestRun).one()
    run.actual_profile = "D"  # what a fallback would look like
    db.commit()
    row = next(x for x in api.get(op, "/operator/stemmetest/summary").json()["rows"] if x["profile"] == "E")
    assert row["status"] != "målt"


def test_an_uploaded_recording_is_scored_against_the_typed_reference_and_not_kept(api, fake_factory, tmp_path):
    import wave

    wav = tmp_path / "u.wav"
    with wave.open(str(wav), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(_pcm(1.0))
    op = api.operator()
    with open(wav, "rb") as f:
        r = api.c.post(f"{api.base}/operator/stemmetest/runs/upload", headers=api.h(op),
                       files={"file": ("u.wav", f, "audio/wav")},
                       data={"profile": "E", "reference": "Goddag, du har ringet til Berle Pool. Hvad kan jeg gøre for dig?"})
    assert r.status_code == 202, r.text
    run = api.get(op, f"/operator/stemmetest/runs/{r.json()['id']}").json()
    assert run["status"] == "ok" and run["source"] == "upload" and run["case_id"] is None and run["wer"]["errors"] == 0
    assert not service._UPLOADS  # audio is not retained
    bad = api.c.post(f"{api.base}/operator/stemmetest/runs/upload", headers=api.h(op),
                     files={"file": ("u.wav", b"not a wav", "audio/wav")}, data={"profile": "E"})
    assert bad.status_code == 422


def test_runs_carry_the_customer_they_were_made_for_and_no_other_workspace_can_read_them(api, two_workspaces, fake_factory):
    op = api.operator()
    ws = two_workspaces["ws_a"]
    r = api.post(op, "/operator/stemmetest/runs", {"profile": "E", "case": "S03", "workspace_id": ws})
    assert r.json()["workspace_id"] == ws
    owner = two_workspaces["tok_a"]
    assert api.get(owner, f"/operator/stemmetest/runs/{r.json()['id']}").status_code == 403
    assert api.get(owner, "/operator/stemmetest/runs").status_code == 403


# --------------------------------------------------------------------------- real WebSocket transport against a local fake server

def _serve(handler):
    import websockets

    async def run(client_coro):
        async with websockets.serve(handler, "127.0.0.1", 0) as server:
            port = server.sockets[0].getsockname()[1]
            return await client_coro(f"ws://127.0.0.1:{port}")

    return run


def test_soniox_over_a_real_socket_sends_header_start_message_audio_finalize_and_the_empty_text_end():
    seen = {}

    async def handler(ws):
        seen["auth"] = ws.request.headers.get("Authorization")
        seen["start"] = json.loads(await ws.recv())
        seen["audio"] = await ws.recv()
        seen["finalize"] = json.loads(await ws.recv())
        await ws.send(json.dumps({"tokens": [_tok("Hej", True, 0, 300), _tok("<fin>", True)]}))
        seen["end"] = await ws.recv()
        await ws.send(json.dumps({"tokens": [], "finished": True}))

    async def client(url):
        a = adapters.Soniox(_cfg(url=url, vocabulary=[{"content": "Viby"}], controlled=True), "sx-key")
        await a.open()
        await a.send_audio(b"\x00\x01" * 160)
        await a.flush()
        await asyncio.sleep(0.2)
        await a.finish()
        await asyncio.wait_for(a.finished.wait(), 3)
        await a.close()
        return a

    a = asyncio.run(_serve(handler)(client))
    assert seen["auth"] == "Bearer sx-key" and seen["start"]["model"] == "stt-rt-v5"
    assert seen["start"]["context"]["terms"] == ["Viby"] and isinstance(seen["audio"], bytes)
    assert seen["finalize"] == {"type": "finalize"} and seen["end"] == ""
    assert [e.text for e in a.events if e.kind == "final"] == ["Hej"]


def test_scribe_over_a_real_socket_uses_the_key_header_and_the_documented_query_and_messages():
    seen = {}

    async def handler(ws):
        seen["key"] = ws.request.headers.get("xi-api-key")
        seen["path"] = ws.request.path
        await ws.send(json.dumps({"message_type": "session_started", "session_id": "s", "config": {"model_id": "scribe_v2_realtime"}}))
        seen["chunk"] = json.loads(await ws.recv())
        seen["commit"] = json.loads(await ws.recv())
        await ws.send(json.dumps({"message_type": "committed_transcript", "text": "Jeg hedder Pernille."}))
        await asyncio.sleep(0.3)

    async def client(url):
        a = adapters.ElevenLabsScribe(_cfg(url=url, controlled=True, vocabulary=[{"content": "Pernille"}]), "el-key")
        await a.open()
        await a.send_audio(b"\x00" * 320)
        await a.flush()
        await asyncio.sleep(0.4)
        await a.close()
        return a

    a = asyncio.run(_serve(handler)(client))
    assert seen["key"] == "el-key" and "model_id=scribe_v2_realtime" in seen["path"] and "commit_strategy=manual" in seen["path"]
    assert "keyterms=Pernille" in seen["path"] and "language_code=da" in seen["path"]
    assert seen["chunk"]["commit"] is False and seen["commit"]["commit"] is True
    assert a.reported_model == "scribe_v2_realtime" and [e.text for e in a.events if e.kind == "final"] == ["Jeg hedder Pernille."]


def test_one_company_can_be_switched_to_another_recogniser_and_back_without_touching_the_rest(bridge_env, db):
    from app.models import Workspace

    a = Workspace(id=uuid_mod.uuid4(), name="A", slug="a-stt")
    b = Workspace(id=uuid_mod.uuid4(), name="B", slug="b-stt")
    db.add_all([a, b])
    db.flush()
    bridge_env.setenv("SONIOX_API_KEY", "sx-test")
    bridge_env.setenv("VAPI_STT_BY_WORKSPACE_JSON", json.dumps({str(a.id): "soniox"}))
    get_settings.cache_clear()
    ta, tb = vapi.transcriber_for(db, a), vapi.transcriber_for(db, b)
    assert ta["provider"] == "custom-transcriber" and "stt=soniox" in ta["server"]["url"] and f"ws={a.id}" in ta["server"]["url"]
    assert tb["provider"] == "deepgram"  # the other company is untouched
    bridge_env.delenv("VAPI_STT_BY_WORKSPACE_JSON")  # rollback = remove the entry
    get_settings.cache_clear()
    assert vapi.transcriber_for(db, a)["provider"] == "deepgram"
    # an opted-in company without the provider's key stays on the production path, not on a dead transcriber
    bridge_env.setenv("VAPI_STT_BY_WORKSPACE_JSON", json.dumps({str(a.id): "elevenlabs-scribe"}))
    bridge_env.delenv("ELEVENLABS_API_KEY", raising=False)
    get_settings.cache_clear()
    assert vapi.transcriber_for(db, a)["provider"] == "deepgram"
