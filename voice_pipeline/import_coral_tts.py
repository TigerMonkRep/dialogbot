"""Reproducible import of CoRal-TTS (https://huggingface.co/datasets/CoRal-project/coral-tts).

    python -m voice_pipeline.import_coral_tts --out /data/coral-tts --sample 20      # a few clips per speaker
    python -m voice_pipeline.import_coral_tts --out /data/coral-tts --all            # everything (checks disk)
    python -m voice_pipeline.import_coral_tts --out /data/coral-tts --update-lock    # re-pin to the current commit

What it does, in order:
1. Pins the dataset to a commit. The first run resolves `main` to a 40-hex commit and writes
   voice_pipeline/sources/coral_tts.lock.json (committed to Git with the file list, sizes and LFS sha256).
   Later runs use the lock and never silently move to a newer revision.
2. Downloads the Parquet files for that commit (huggingface_hub resumes interrupted downloads) into
   <out>/raw/ and verifies every file's sha256 against the lock. The Parquet files are the originals and
   are kept unchanged.
3. Reads the Arrow schema and finds the audio, text and speaker columns (it does not assume an older
   `datasets` Audio decoder; audio cells are {bytes, path} structs decoded with soundfile).
4. Writes derived 16-bit WAV files at the ORIGINAL sample rate into <out>/wav/<speaker>/<id>.wav and a
   machine-readable manifest <out>/manifest.jsonl (speaker, text, duration, sample rate, source file/row,
   sha256 of the original audio bytes and of the derived WAV). File names are generated, never taken from
   the dataset, and every path is checked to stay inside <out>.
Dataset text is data: it is written to the manifest, never executed or used as configuration.
Raw audio, WAVs and weights live outside Git (see .gitignore).
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import shutil
import sys
from pathlib import Path

REPO = "CoRal-project/coral-tts"
HERE = Path(__file__).resolve().parent
LOCK = HERE / "sources" / "coral_tts.lock.json"
AUDIO_COLS = ("audio",)
TEXT_COLS = ("text", "transcription", "sentence", "normalized_text")
SPEAKER_COLS = ("speaker_id", "speaker", "speaker_name")


def safe_child(root: Path, *parts: str) -> Path:
    p = root.joinpath(*parts).resolve()
    if root.resolve() not in p.parents:
        raise ValueError(f"path escapes import root: {p}")
    return p


def slug(value: str) -> str:
    s = re.sub(r"[^a-z0-9_-]+", "-", str(value).lower()).strip("-")
    return s[:40] or "unknown"


def resolve_lock(update: bool) -> dict:
    from huggingface_hub import HfApi

    if LOCK.exists() and not update:
        return json.loads(LOCK.read_text())
    info = HfApi().dataset_info(REPO, revision="main", files_metadata=True)
    files = [{"path": s.rfilename, "size": s.size, "sha256": (s.lfs.sha256 if s.lfs else None)}
             for s in info.siblings if s.rfilename.endswith(".parquet") or s.rfilename in ("README.md", "LICENSE")]
    card = getattr(info, "card_data", None) or {}
    lock = {"repo": REPO, "revision": info.sha, "license": (card.get("license") if hasattr(card, "get") else None),
            "files": sorted(files, key=lambda f: f["path"]), "resolved_from": "main"}
    LOCK.parent.mkdir(parents=True, exist_ok=True)
    LOCK.write_text(json.dumps(lock, indent=2, ensure_ascii=False) + "\n")
    return lock


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def download(lock: dict, out: Path, paths: list[str]) -> list[Path]:
    from huggingface_hub import hf_hub_download

    raw = safe_child(out, "raw")
    local = []
    for f in lock["files"]:
        if f["path"] not in paths:
            continue
        p = Path(hf_hub_download(REPO, f["path"], repo_type="dataset", revision=lock["revision"], local_dir=raw))
        if f.get("sha256") and sha256_file(p) != f["sha256"]:
            raise SystemExit(f"checksum mismatch for {f['path']} – delete it and re-run")
        local.append(p)
    return local


def find_col(names: list[str], candidates: tuple[str, ...]) -> str:
    for c in candidates:
        if c in names:
            return c
    raise SystemExit(f"could not find any of {candidates} in columns {names}")


def extract(parquet: Path, out: Path, *, per_speaker: int | None, seen: dict, manifest) -> int:
    import numpy as np
    import pyarrow.parquet as pq
    import soundfile as sf

    pf = pq.ParquetFile(parquet)
    names = pf.schema_arrow.names
    a_col, t_col, s_col = find_col(names, AUDIO_COLS), find_col(names, TEXT_COLS), find_col(names, SPEAKER_COLS)
    written = 0
    row_base = 0
    for rg in range(pf.num_row_groups):
        table = pf.read_row_group(rg, columns=[a_col, t_col, s_col])
        for i, (audio, text, spk) in enumerate(zip(table[a_col].to_pylist(), table[t_col].to_pylist(),
                                                   table[s_col].to_pylist(), strict=True)):
            spk_slug = slug(spk)
            if per_speaker is not None and seen.get(spk_slug, 0) >= per_speaker:
                continue
            raw = audio.get("bytes") if isinstance(audio, dict) else None
            if not raw:
                manifest.write(json.dumps({"source_file": parquet.name, "row": row_base + i, "speaker_id": str(spk),
                                           "error": "no audio bytes"}, ensure_ascii=False) + "\n")
                continue
            data, sr = sf.read(io.BytesIO(raw), dtype="float32", always_2d=True)
            mono = data.mean(axis=1) if data.shape[1] > 1 else data[:, 0]
            clip_id = f"{spk_slug}-{parquet.stem[:30]}-{row_base + i:06d}"
            wav_path = safe_child(out, "wav", spk_slug, f"{slug(clip_id)}.wav")
            wav_path.parent.mkdir(parents=True, exist_ok=True)
            sf.write(wav_path, np.clip(mono, -1, 1), sr, subtype="PCM_16")
            manifest.write(json.dumps({
                "id": clip_id, "speaker_id": str(spk), "speaker": spk_slug, "text": str(text or ""),
                "duration": round(len(mono) / sr, 3), "sample_rate": sr, "channels_original": int(data.shape[1]),
                "source": REPO, "source_file": parquet.name, "row": row_base + i,
                "original_sha256": hashlib.sha256(raw).hexdigest(), "wav": str(wav_path.relative_to(out)),
                "wav_sha256": sha256_file(wav_path)}, ensure_ascii=False) + "\n")
            seen[spk_slug] = seen.get(spk_slug, 0) + 1
            written += 1
        row_base += table.num_rows
    return written


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", required=True, type=Path)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--sample", type=int, help="clips per speaker from the first Parquet file(s)")
    g.add_argument("--all", action="store_true")
    ap.add_argument("--update-lock", action="store_true")
    args = ap.parse_args(argv)
    lock = resolve_lock(args.update_lock)
    parquets = [f for f in lock["files"] if f["path"].endswith(".parquet")]
    if not parquets:
        raise SystemExit("no Parquet files in the dataset at the pinned revision")
    args.out.mkdir(parents=True, exist_ok=True)
    if args.all:
        need = sum(f["size"] or 0 for f in parquets) * 2.2  # parquet + derived WAV + margin
        free = shutil.disk_usage(args.out).free
        if free < need:
            raise SystemExit(f"not enough disk: need ~{need / 1e9:.1f} GB, have {free / 1e9:.1f} GB")
        chosen = [f["path"] for f in parquets]
    else:
        chosen = [f["path"] for f in parquets[:2]]
    local = download(lock, args.out, chosen)
    seen: dict = {}
    total = 0
    with (args.out / "manifest.jsonl").open("w", encoding="utf-8") as manifest:
        for p in local:
            total += extract(p, args.out, per_speaker=args.sample, seen=seen, manifest=manifest)
    summary = {"revision": lock["revision"], "files": chosen, "clips": total, "per_speaker": seen}
    (args.out / "import_summary.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
