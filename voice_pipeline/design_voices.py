"""Designed voices: Danish voices that belong to no one person, blended from several NST speakers.

    python -m voice_pipeline.design_voices scan --out /data/nst                     # speaker metadata (no audio)
    python -m voice_pipeline.design_voices build --catalog voice_pipeline/designed/catalog.json \
        --nst /data/nst --out /data/designed [--only designet-jysk-mand]

Source: alexandrainst/nst-da (CC0-1.0) at a pinned revision. Every NST speaker has sex, age and region ("dialect")
recorded by the corpus. A designed voice is built from 4–10 speakers of one group:
- the speaker embedding is the mean of the speakers' embeddings,
- the decoder's x-vector is the mean of the speakers' x-vectors,
- the prompt audio is equal slices of every speaker, so no one speaker dominates.
The result is saved as a Chatterbox `Conditionals` file (conds.pt) that the TTS service loads directly.

Distinctness gate: a sample of the designed voice is compared (speaker-encoder cosine similarity) with held-out
clips of every source speaker. It must not be closer to any of them than two different real speakers of the group
are to each other, plus DISTINCT_MARGIN, and never above DISTINCT_CEILING (same policy as the API check). A voice
that fails is retried with more speakers and otherwise not written.

The description is generated only from the recorded metadata and measurements (pitch, tempo). The region is where
the source speakers come from; whether the designed voice sounds regional is for listeners to judge, so `dialect`
stays unknown until a listening test with speakers of that dialect. Model: the TTS service's default (Røst-v3).
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import random
import statistics
import sys
from pathlib import Path

REPO = "alexandrainst/nst-da"
REVISION = "0f14ad2005e0aab8f56cf3213b7689da1faf23c2"
DISTINCT_MARGIN = 0.03
DISTINCT_CEILING = 0.90
CLIPS_PER_SPEAKER = 25
BUILD_CLIPS = 15  # clips 0–14 build the voice, 15–24 are held out for the distinctness check
SAMPLE_TEXT = "Hej, du taler med Dialogbot. Vi har en ledig tid torsdag kl. 10.30 – den koster 1.495 kr."
TOOL_VERSION = 1


# --------------------------------------------------------------------------- metadata and audio

def scan(out: Path) -> dict:
    import pyarrow.parquet as pq
    from huggingface_hub import HfApi, HfFileSystem

    files = sorted(s.rfilename for s in HfApi().dataset_info(REPO, revision=REVISION).siblings
                   if s.rfilename.startswith("data/"))
    fs, speakers = HfFileSystem(), {}
    for f in files:
        with fs.open(f"datasets/{REPO}@{REVISION}/{f}") as fh:
            rows = pq.ParquetFile(fh).read(columns=["speaker_id", "age", "sex", "dialect"]).to_pylist()
        for r in rows:
            s = speakers.setdefault(str(r["speaker_id"]), {**r, "speaker_id": str(r["speaker_id"]), "n": 0, "files": []})
            s["n"] += 1
            if f not in s["files"]:
                s["files"].append(f)
    out.mkdir(parents=True, exist_ok=True)
    data = {"repo": REPO, "revision": REVISION, "speakers": speakers}
    (out / "speakers.json").write_text(json.dumps(data, ensure_ascii=False))
    return data


def pick_speakers(speakers: dict, spec: dict, n: int, rng: random.Random) -> list[dict]:
    lo, hi = spec["age"]
    pool = [s for s in speakers.values() if s["sex"] == spec["sex"] and lo <= (s["age"] or -1) <= hi
            and s["dialect"] in spec["regions"] and s["n"] >= CLIPS_PER_SPEAKER]
    pool.sort(key=lambda s: (s["age"], s["speaker_id"]))
    if len(pool) < n:
        return pool
    # spread over the age range: take every k-th speaker, then fill randomly
    step = len(pool) / n
    chosen = [pool[int(i * step)] for i in range(n)]
    return sorted(chosen, key=lambda s: s["speaker_id"])


def fetch_clips(nst: Path, speaker_ids: list[str], speakers: dict) -> dict[str, list[dict]]:
    import numpy as np
    import pyarrow.parquet as pq
    import soundfile as sf
    from huggingface_hub import hf_hub_download

    cache = nst / "clips.json"
    have = json.loads(cache.read_text()) if cache.exists() else {}
    need = [k for k in speaker_ids if len(have.get(k, [])) < CLIPS_PER_SPEAKER]
    shards = sorted({f for k in need for f in speakers[k]["files"]})
    for f in shards:
        p = hf_hub_download(REPO, f, repo_type="dataset", revision=REVISION)
        table = pq.read_table(p, columns=["audio", "speaker_id"])
        for row, (audio, sid) in enumerate(zip(table["audio"].to_pylist(), table["speaker_id"].to_pylist(), strict=True)):
            k = str(sid)
            if k not in need or len(have.get(k, [])) >= CLIPS_PER_SPEAKER:
                continue
            x, sr = sf.read(io.BytesIO(audio["bytes"]), dtype="float32", always_2d=True)
            x = x.mean(axis=1)
            if not 2.5 <= len(x) / sr <= 9 or float(np.abs(x).max()) > 0.99:
                continue
            i = len(have.get(k, []))
            wav = nst / "wav" / k / f"{i:02d}.wav"
            wav.parent.mkdir(parents=True, exist_ok=True)
            sf.write(wav, x, sr, subtype="PCM_16")
            have.setdefault(k, []).append({"wav": str(wav.relative_to(nst)), "shard": f, "row": row,
                                           "sha256": hashlib.sha256(audio["bytes"]).hexdigest()})
    cache.write_text(json.dumps(have, ensure_ascii=False, indent=1))
    return have


# --------------------------------------------------------------------------- building and measuring

class Designer:
    def __init__(self, model_dir: str | None = None, device: str = "cpu"):
        import torch
        from chatterbox.mtl_tts import ChatterboxMultilingualTTS

        torch.set_num_threads(max(1, torch.get_num_threads()))
        if model_dir is None:
            from huggingface_hub import snapshot_download

            from tts_service.engines import BASE_FILES, DEFAULT_REPO, DEFAULT_T3

            model_dir = snapshot_download(DEFAULT_REPO, revision=ROEST_REVISION, allow_patterns=[*BASE_FILES, DEFAULT_T3])
        self.model_dir = model_dir
        self.m = ChatterboxMultilingualTTS.from_local(model_dir, device)
        self.device = device

    def _load(self, path: Path, sr: int):
        import librosa

        x, _ = librosa.load(str(path), sr=sr)
        y, _ = librosa.effects.trim(x, top_db=35)
        return y

    def embed(self, wavs16) -> object:
        import numpy as np
        from chatterbox.models.s3tokenizer import S3_SR

        e = self.m.ve.embeds_from_wavs(list(wavs16), sample_rate=S3_SR).mean(0)
        return e / np.linalg.norm(e)

    def build(self, nst: Path, clips: dict, speaker_ids: list[str]):
        import numpy as np
        import torch
        from chatterbox.models.s3gen import S3GEN_SR
        from chatterbox.models.s3tokenizer import S3_SR
        from chatterbox.models.t3.modules.cond_enc import T3Cond
        from chatterbox.mtl_tts import Conditionals

        n = len(speaker_ids)
        t3_parts, s3_parts, ves, xvecs = [], [], [], []
        for k in speaker_ids:
            c16 = [self._load(nst / c["wav"], S3_SR) for c in clips[k][:BUILD_CLIPS]]
            ves.append(self.embed(c16))
            t3_parts.append(np.concatenate(c16)[: int(6 * S3_SR / n)])
            c24 = np.concatenate([self._load(nst / c["wav"], S3GEN_SR) for c in clips[k][:4]])
            s3_parts.append(c24[: int(10 * S3GEN_SR / n)])
            xvecs.append(self.m.s3gen.embed_ref(torch.from_numpy(c24[: 10 * S3GEN_SR]), S3GEN_SR, device=self.device)["embedding"])
        ref_dict = self.m.s3gen.embed_ref(torch.from_numpy(np.concatenate(s3_parts)[: 10 * S3GEN_SR]), S3GEN_SR,
                                          device=self.device)
        ref_dict["embedding"] = torch.stack(xvecs).mean(0)
        toks, _ = self.m.s3gen.tokenizer.forward([np.concatenate(t3_parts)[: 6 * S3_SR]],
                                                 max_len=self.m.t3.hp.speech_cond_prompt_len)
        spk = np.mean(ves, 0)
        spk = spk / np.linalg.norm(spk)
        t3 = T3Cond(speaker_emb=torch.from_numpy(spk).float().unsqueeze(0).to(self.device),
                    cond_prompt_speech_tokens=torch.atleast_2d(toks).to(self.device),
                    emotion_adv=0.5 * torch.ones(1, 1, 1, device=self.device))
        return Conditionals(t3, ref_dict)

    def speak(self, conds, text: str, seed: int = 1):
        import torch

        from app.modules.voices import danish
        from tts_service.engines import DEFAULT_SETTINGS, clean

        self.m.conds = conds
        torch.manual_seed(seed)
        w = self.m.generate(danish.normalize(text), language_id="da", **DEFAULT_SETTINGS).squeeze(0).cpu().numpy()
        return clean(w, self.m.sr), self.m.sr

    def measure(self, nst: Path, clips: dict, speaker_ids: list[str], wav, sr: int, text: str) -> dict:
        import librosa
        import numpy as np
        from chatterbox.models.s3tokenizer import S3_SR

        from app.modules.voices import danish

        a = librosa.resample(wav, orig_sr=sr, target_sr=S3_SR)
        e = self.embed([a])
        held = {k: self.embed([self._load(nst / c["wav"], S3_SR) for c in clips[k][BUILD_CLIPS:CLIPS_PER_SPEAKER]])
                for k in speaker_ids}
        sims = {k: round(float(e @ h), 3) for k, h in held.items()}
        pairs = [float(held[a_] @ held[b_]) for i, a_ in enumerate(speaker_ids) for b_ in speaker_ids[i + 1:]]
        f0, voiced, _ = librosa.pyin(a, fmin=60, fmax=400, sr=S3_SR)
        f0 = f0[voiced]
        nearest = max(sims, key=sims.get)
        real_max = round(max(pairs), 3) if pairs else 0.0
        limit = round(min(DISTINCT_CEILING, real_max + DISTINCT_MARGIN), 3)
        chars = len(danish.normalize(text).replace(" ", ""))
        return {"distinctness": {"max_similarity_to_source": sims[nearest], "nearest_source": nearest,
                                 "real_speaker_pairs_max": real_max, "real_speaker_pairs_mean": round(statistics.mean(pairs), 3) if pairs else None,
                                 "limit": limit, "passed": sims[nearest] <= limit, "per_source": sims,
                                 "measure": "Chatterbox VoiceEncoder cosine similarity; held-out clips 15–24 per source"},
                "measurements": {"f0_median_hz": round(float(np.median(f0))) if len(f0) else None,
                                 "f0_iqr_hz": [round(float(q)) for q in np.percentile(f0, [25, 75])] if len(f0) else None,
                                 "chars_per_second": round(chars / (len(wav) / sr), 1), "sample_seconds": round(len(wav) / sr, 2)}}


ROEST_REVISION = "7ce205cea6b3b36d9f60f18abb88ff21fa04ea0d"


def describe(spec: dict, sources: list[dict], meas: dict) -> tuple[str, str | None]:
    f0 = meas.get("f0_median_hz") or 0
    male = spec["sex"] == "Male"
    pitch = (("dyb" if f0 < 105 else "mellemdyb" if f0 < 130 else "lys") if male
             else ("dyb" if f0 < 185 else "mellemlys" if f0 < 215 else "lys"))
    cps = meas.get("chars_per_second") or 0
    tempo = "roligt" if cps < 12.5 else "jævnt" if cps < 15 else "hurtigt"
    ages = [s["age"] for s in sources]
    regions = sorted({s["dialect"] for s in sources})
    region_txt = ", ".join(regions[:-1]) + (" og " if len(regions) > 1 else "") + regions[-1]
    who = "mænd" if male else "kvinder"
    timbre = f"{pitch} stemme, {tempo} tempo"
    text = (f"{'Mandestemme' if male else 'Kvindestemme'} med {pitch} klang og {tempo} tempo. Designet ud fra "
            f"{len(sources)} {who} fra {region_txt} i alderen {min(ages)}–{max(ages)} år. Stemmen tilhører ingen "
            f"bestemt person. Om den lyder regional, er endnu ikke vurderet af lyttere.")
    return text, timbre


def build_catalog(catalog: Path, nst: Path, out: Path, only: list[str] | None = None) -> list[dict]:
    import soundfile as sf
    import torch

    cat = json.loads(catalog.read_text(encoding="utf-8"))
    speakers = json.loads((nst / "speakers.json").read_text())["speakers"]
    designer = Designer()
    results = []
    for spec in cat["voices"]:
        if only and spec["slug"] not in only:
            continue
        rng = random.Random(spec["slug"])
        n = spec.get("speakers", 8)
        result = None
        while n <= spec.get("max_speakers", 12):
            chosen = pick_speakers(speakers, spec, n, rng)
            if len(chosen) < 4:
                break
            ids = [s["speaker_id"] for s in chosen]
            clips = fetch_clips(nst, ids, speakers)
            conds = designer.build(nst, clips, ids)
            wav, sr = designer.speak(conds, SAMPLE_TEXT)
            m = designer.measure(nst, clips, ids, wav, sr, SAMPLE_TEXT)
            print(spec["slug"], n, "speakers → nearest", m["distinctness"]["max_similarity_to_source"], "limit",
                  m["distinctness"]["limit"], flush=True)
            if m["distinctness"]["passed"]:
                result = (chosen, clips, conds, wav, sr, m)
                break
            if len(chosen) < n:
                break
            n += 2
        if result is None:
            print(spec["slug"], "FAILED the distinctness gate – not written", flush=True)
            results.append({"slug": spec["slug"], "passed": False})
            continue
        chosen, clips, conds, wav, sr, m = result
        d = out / spec["slug"]
        d.mkdir(parents=True, exist_ok=True)
        conds.save(d / "conds.pt")
        sf.write(d / "sample.wav", wav, sr, subtype="PCM_16")
        description, timbre = describe(spec, chosen, m["measurements"])
        prov = {"dataset": REPO, "dataset_revision": REVISION, "model": "CoRal-project/roest-v3-chatterbox-500m",
                "model_revision": ROEST_REVISION, "tool": f"voice_pipeline.design_voices v{TOOL_VERSION}",
                "group": {"sex": spec["sex"], "age": spec["age"], "regions": spec["regions"]},
                "sources": [{"speaker_id": s["speaker_id"], "sex": s["sex"], "age": s["age"], "region": s["dialect"],
                             "clips": [{"shard": c["shard"], "row": c["row"], "sha256": c["sha256"]}
                                       for c in clips[s["speaker_id"]][:BUILD_CLIPS]]} for s in chosen],
                **m, "checkpoint_sha256": hashlib.sha256((d / "conds.pt").read_bytes()).hexdigest()}
        voice = {"slug": spec["slug"], "display_name": spec["display_name"],
                 "gender": "male" if spec["sex"] == "Male" else "female",
                 "age_description": f"{min(s['age'] for s in chosen)}–{max(s['age'] for s in chosen)} år (kildepersoner)",
                 "timbre": timbre, "description": description, "origin": "designed", "dialect": None,
                 "dialect_basis": "Kildepersonerne kommer fra " + ", ".join(spec["regions"]) + " (NST's registrering). "
                                  "Om stemmen lyder regional, er ikke vurderet af lyttere endnu.",
                 "sample_text": SAMPLE_TEXT, "provenance": prov}
        (d / "voice.json").write_text(json.dumps(voice, ensure_ascii=False, indent=1))
        results.append({"slug": spec["slug"], "passed": True, **m["distinctness"], **m["measurements"]})
        del conds
        torch.cuda.empty_cache() if torch.cuda.is_available() else None
    (out / "build_report.json").write_text(json.dumps(results, ensure_ascii=False, indent=1))
    return results


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("scan")
    s.add_argument("--out", required=True, type=Path)
    b = sub.add_parser("build")
    b.add_argument("--catalog", required=True, type=Path)
    b.add_argument("--nst", required=True, type=Path)
    b.add_argument("--out", required=True, type=Path)
    b.add_argument("--only", nargs="*")
    a = ap.parse_args(argv)
    if a.cmd == "scan":
        d = scan(a.out)
        print(len(d["speakers"]), "speakers")
    else:
        for r in build_catalog(a.catalog, a.nst, a.out, a.only):
            print(json.dumps(r, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
