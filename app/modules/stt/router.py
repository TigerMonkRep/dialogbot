"""Operator API for the Stemmetest (`/operator/stemmetest`). Platform operators only; every run is audited. API keys are
read from the environment on the server and never appear in any response; access is reported as 'mangler X'."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, Request, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session as OrmSession

from app.core.audit import record_audit
from app.core.auth import Principal
from app.core.errors import NotFound, ValidationFailed
from app.db import get_db
from app.models import SttTestRun, Workspace
from app.modules.stt import manifest, profiles, service
from app.modules.voices.operator_router import operator

router = APIRouter(prefix="/operator/stemmetest", tags=["stemmetest-operator"])

MAX_UPLOAD = 5 * 1024 * 1024
HONESTY = [
    "Dette er en måling på det angivne datagrundlag – ikke en leverandørs benchmark og ikke en vinder på forhånd.",
    "Replay af samme lyd (kontrolleret) måler genkendelse; en komplet samtale måles i live-opkald og er adskilt.",
    "Syntetisk tale (Peters stemme) er for let: dialekt, støj og telefonkvalitet kræver menneskeindtalte optagelser.",
]


def _audit(db, request, principal, run: SttTestRun, action: str) -> None:
    record_audit(db, workspace_id=run.workspace_id, actor_user_id=principal.user.id, action=action,
                 object_type="stt_test_run", object_id=run.id,
                 after={"profile": run.profile_id, "case": run.case_id, "mode": run.mode, "status": run.status},
                 request_id=request.state.request_id)


@router.get("")
def overview(principal: Principal = Depends(operator), db: OrmSession = Depends(get_db)):
    workspaces = [{"id": str(w.id), "name": w.name} for w in db.scalars(select(Workspace).order_by(Workspace.name))]
    return {"testmode": True, "honesty": HONESTY, "profiles": [profiles.describe(p) for p in profiles.PROFILES],
            "manifest": manifest.overview(), "workspaces": workspaces,
            "summary": {"final": service.summary(db, "final", "controlled"), "tuning": service.summary(db, "tuning", "controlled")},
            "browser_call": {"status": "ikke_bygget", "reason": "Repositoryet har ingen browser-talekanal (Vapi Web SDK + public key). "
                             "Telefon: skift VAPI_TRANSCRIBER_JSON på staging, se docs/voice/stemmetest.md."}}


@router.get("/summary")
def summary(split: str | None = None, mode: str | None = None, principal: Principal = Depends(operator),
            db: OrmSession = Depends(get_db)):
    return {"split": split, "mode": mode, "rows": service.summary(db, split, mode)}


@router.get("/runs")
def runs(profile: str | None = None, case: str | None = None, limit: int = 50, principal: Principal = Depends(operator),
         db: OrmSession = Depends(get_db)):
    q = select(SttTestRun).order_by(SttTestRun.created_at.desc()).limit(min(limit, 200))
    if profile:
        q = q.where(SttTestRun.profile_id == profile)
    if case:
        q = q.where(SttTestRun.case_id == case)
    return {"runs": [service.run_out(r) for r in db.scalars(q)]}


@router.get("/runs/{run_id}")
def run_detail(run_id: uuid.UUID, principal: Principal = Depends(operator), db: OrmSession = Depends(get_db)):
    r = db.get(SttTestRun, run_id)
    if r is None:
        raise NotFound("Kørslen findes ikke")
    return service.run_out(r, detail=True)


@router.post("/runs", status_code=202)
def start_run(request: Request, tasks: BackgroundTasks, body: dict, principal: Principal = Depends(operator),
              db: OrmSession = Depends(get_db)):
    """Body: {profile, case, mode: controlled|natural, workspace_id?}. 202 + run id; poll GET /runs/{id}.
    A profile without access is recorded as `mangler_adgang` (with what is missing) rather than failing the request."""
    ws = uuid.UUID(body["workspace_id"]) if body.get("workspace_id") else None
    run = service.create_run(db, user_id=principal.user.id, profile_id=str(body.get("profile", "")),
                             mode=str(body.get("mode", "controlled")), case_id=body.get("case"), workspace_id=ws)
    _audit(db, request, principal, run, "stemmetest.run")
    db.commit()
    if run.status == "kører":
        tasks.add_task(service.execute, run.id)
    return service.run_out(run)


@router.post("/runs/upload", status_code=202)
async def start_upload(request: Request, tasks: BackgroundTasks, file: UploadFile = File(...), profile: str = Form(...),
                       reference: str = Form(""), mode: str = Form("controlled"), workspace_id: str | None = Form(None),
                       principal: Principal = Depends(operator), db: OrmSession = Depends(get_db)):
    """Replay an uploaded 16-bit WAV (not stored) against a typed reference text. Result is stored, audio is not."""
    data = await file.read(MAX_UPLOAD + 1)
    if len(data) > MAX_UPLOAD:
        raise ValidationFailed("Filen er for stor (højst 5 MB)", field_errors={"file": "for stor"})
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "u.wav"
        path.write_bytes(data)
        try:
            pcm, rate = manifest.read_wav(path)
        except Exception as e:  # noqa: BLE001
            raise ValidationFailed("Filen skal være en 16-bit WAV", field_errors={"file": str(e)[:100]}) from e
    run = service.create_run(db, user_id=principal.user.id, profile_id=profile, mode=mode, case_id=None,
                             workspace_id=uuid.UUID(workspace_id) if workspace_id else None, upload=(pcm, rate),
                             reference=reference.strip(), expected=[])
    _audit(db, request, principal, run, "stemmetest.upload_run")
    db.commit()
    if run.status == "kører":
        tasks.add_task(service.execute, run.id)
    return service.run_out(run)
