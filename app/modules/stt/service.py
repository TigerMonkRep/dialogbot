"""Creating, executing and summarising Stemmetest runs (operator only, replay channel)."""
from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session as OrmSession

from app.core.errors import Conflict, NotFound, ValidationFailed
from app.models import SttTestRun, Workspace
from app.modules.stt import adapters, manifest, metrics, profiles, replay

# Uploaded audio is held in memory for the one run that uses it and never stored (no recording retention question).
_UPLOADS: dict[uuid.UUID, tuple[bytes, int]] = {}
MODES = ("controlled", "natural")
FACTORY: Callable[..., adapters.Adapter] | None = None  # tests inject fakes here


def _vocabulary(db: OrmSession, ws: Workspace | None) -> list[dict]:
    if ws is None:
        return manifest.vocabulary()
    from app.modules.telephony import linden

    return [{"content": v["content"], **({"sounds_like": v["sounds_like"]} if v.get("sounds_like") else {})}
            for v in linden.additional_vocab(db, ws, [])]


def create_run(db: OrmSession, *, user_id: uuid.UUID | None, profile_id: str, mode: str, case_id: str | None,
               workspace_id: uuid.UUID | None, upload: tuple[bytes, int] | None = None, reference: str = "",
               expected: list[dict] | None = None) -> SttTestRun:
    p = profiles.BY_ID.get(profile_id)
    if p is None:
        raise NotFound("Profilen findes ikke")
    if mode not in MODES:
        raise ValidationFailed("Ukendt tilstand", field_errors={"mode": "controlled eller natural"})
    if p.adapter is None:
        raise Conflict(profiles.access(p)["reason"], code="profile_not_replayable")
    ws = db.get(Workspace, workspace_id) if workspace_id else None
    if workspace_id and ws is None:
        raise NotFound("Arbejdsrummet findes ikke")
    case = None
    reference_alts: list[str] = []
    if upload is None:
        case = manifest.get(case_id or "")
        if case is None or case["kind"] != "kort":
            raise NotFound("Testcasen findes ikke")
        if manifest.audio_path(case) is None:
            raise Conflict("Der mangler en menneskeindtalt optagelse til denne case", code="recording_missing")
        reference, expected = case["text"], case["entities"]
        reference_alts = case.get("reference_alts") or []
    run = SttTestRun(workspace_id=workspace_id, started_by=user_id, profile_id=p.id, actual_profile=p.id,
                     channel="replay", mode=mode, case_id=case["id"] if case else None,
                     split=case["split"] if case else None, source="manifest" if case else "upload",
                     reference=reference, status="kører",
                     config={"profile": p.id, "model": p.model, "turn_owner": p.turn_owner, "mode": mode,
                             "synthetic": bool(case and manifest.is_synthetic(case)), "expected": expected or [],
                             "reference_alts": reference_alts,
                             "workspace": str(workspace_id) if workspace_id else None})
    acc = profiles.access(p)
    if acc["status"] == "mangler_adgang":
        run.status, run.finished_at = "mangler_adgang", datetime.now(UTC)
        run.result = {"status": "mangler_adgang", "error": acc["reason"], "missing": acc["missing"]}
    db.add(run)
    db.flush()
    if upload is not None and run.status == "kører":
        _UPLOADS[run.id] = upload
    return run


MAX_BATCH = 400


def create_batch(db: OrmSession, *, user_id: uuid.UUID | None, profile_ids: list[str], case_ids: list[str] | str,
                 mode: str, workspace_id: uuid.UUID | None) -> dict[str, list[uuid.UUID]]:
    """One run per (profile, case) for every replayable profile and every case that has audio. Returns the ids that
    still have to be executed, per profile (a profile without access is recorded as `mangler_adgang` and skipped)."""
    cases = [c for c in manifest.cases() if manifest.audio_path(c)] if case_ids in ("alle", "all") else [
        c for c in (manifest.get(i) for i in case_ids) if c and c["kind"] == "kort" and manifest.audio_path(c)]
    if not cases:
        raise ValidationFailed("Ingen af de valgte cases har lyd", field_errors={"cases": "ingen lyd"})
    if len(profile_ids) * len(cases) > MAX_BATCH:
        raise ValidationFailed("For mange kørsler på én gang", field_errors={"cases": f"højst {MAX_BATCH}"})
    todo: dict[str, list[uuid.UUID]] = {}
    for pid in profile_ids:
        for c in cases:
            run = create_run(db, user_id=user_id, profile_id=pid, mode=mode, case_id=c["id"], workspace_id=workspace_id)
            if run.status == "kører":
                todo.setdefault(pid, []).append(run.id)
    return todo


async def execute_batch(todo: dict[str, list[uuid.UUID]]) -> None:
    """Profiles run side by side, but each profile runs its cases one after the other: one open provider connection
    per profile at a time, so a batch never trips a provider's concurrency limit (and never burns more than one
    real-time stream per provider)."""
    import asyncio

    async def one(ids: list[uuid.UUID]) -> None:
        for rid in ids:
            await execute(rid)

    await asyncio.gather(*(one(ids) for ids in todo.values()))


async def execute(run_id: uuid.UUID) -> None:
    """Background body: replay in real time, store the result. Never raises – a failure is a recorded `fejl`."""
    from app.db import get_session_factory

    db = get_session_factory()()
    try:
        run = db.get(SttTestRun, run_id)
        if run is None or run.status != "kører":
            return
        p = profiles.BY_ID[run.profile_id]
        try:
            if run.source == "upload":
                pcm, rate = _UPLOADS.pop(run.id)
            else:
                pcm, rate = manifest.read_wav(manifest.audio_path(manifest.get(run.case_id)))
            ws = db.get(Workspace, run.workspace_id) if run.workspace_id else None
            result = await replay.run_audio(p, pcm, rate, reference=run.reference, expected=run.config.get("expected", []),
                                            vocabulary=_vocabulary(db, ws), mode=run.mode, factory=FACTORY,
                                            reference_alts=run.config.get("reference_alts") or None)
        except Exception as e:  # noqa: BLE001
            result = {"status": "fejl", "error": f"{type(e).__name__}: {str(e)[:200]}"}
        run.result = result
        run.transcript_raw = result.get("transcript_raw", "")
        run.status = result["status"] if result["status"] in ("ok", "fejl", "mangler_adgang") else "fejl"
        run.finished_at = datetime.now(UTC)
        db.commit()
    finally:
        db.close()


def run_out(r: SttTestRun, detail: bool = False) -> dict:
    res = r.result or {}
    out = {"id": str(r.id), "profile": r.profile_id, "actual_profile": r.actual_profile, "channel": r.channel,
           "mode": r.mode, "case_id": r.case_id, "split": r.split, "source": r.source, "status": r.status,
           "workspace_id": str(r.workspace_id) if r.workspace_id else None, "reference": r.reference,
           "transcript_raw": r.transcript_raw, "synthetic": r.config.get("synthetic", False),
           "created_at": r.created_at.isoformat(), "error": res.get("error"),
           "wer": res.get("wer"), "entities": res.get("entities"), "timing": res.get("timing"),
           "turn_count": res.get("turn_count"), "premature_split": res.get("premature_split"),
           "requested_model": res.get("requested_model"), "reported_model": res.get("reported_model")}
    if detail:
        out.update({"config": r.config, "turns": res.get("turns"), "events": res.get("events"),
                    "events_total": res.get("events_total"), "sdk": res.get("sdk"), "turn_owner": res.get("turn_owner"),
                    "vocabulary": res.get("vocabulary"), "price": res.get("price"),
                    "audio_seconds": res.get("audio_seconds"), "audio_rate": res.get("audio_rate"),
                    "session_id": res.get("session_id")})
    return out


def _by_group(runs: list[dict]) -> dict[str, dict]:
    """Same measures per case group (tal_telefon, tal_tid, navne, stoej_tal …): where a recogniser is weak, not one
    blended number. Every group keeps its own denominators."""
    groups: dict[str, list[dict]] = {}
    for r in runs:
        case = manifest.get(r["case_id"] or "")
        if case:
            groups.setdefault(case["group"], []).append(r)
    return {g: metrics.aggregate(rs) for g, rs in sorted(groups.items())}


def summary(db: OrmSession, split: str | None, mode: str | None) -> list[dict]:
    """One row per profile. Only finished `ok` replay runs on the profile's OWN recogniser count (a fallback run
    would carry another actual_profile). Profiles with nothing measured say so, with the reason."""
    rows = []
    for p in profiles.PROFILES:
        acc = profiles.access(p)
        q = select(SttTestRun).where(SttTestRun.profile_id == p.id, SttTestRun.actual_profile == p.id,
                                     SttTestRun.channel == "replay", SttTestRun.status == "ok")
        if split:
            q = q.where(SttTestRun.split == split)
        if mode:
            q = q.where(SttTestRun.mode == mode)
        runs = [run_out(r) for r in db.scalars(q)]
        row = {"profile": p.id, "label": p.label, "model": p.model, "turn_owner": p.turn_owner, "access": acc}
        if runs:
            real = [r for r in runs if not r["synthetic"]]
            row["measured"] = metrics.aggregate(runs)
            row["by_group"] = _by_group(runs)
            row["human_cases"] = len(real)
            row["note"] = (None if real else "kun syntetisk tale (Peters stemme): dialekt og telefonkvalitet er uafklaret")
            row["status"] = "målt"
        else:
            row["status"] = {"ikke_replaybar": "Ikke replaybar – måles i live-opkald",
                             "mangler_adgang": "Mangler adgang", "klar": "Ikke testet"}[acc["status"]]
        rows.append(row)
    return rows
