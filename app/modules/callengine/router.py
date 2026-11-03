"""Routes for Dialogbot's own call engine.

Webhooks (Twilio): POST /webhooks/engine/twiml?t=… (an inbound number pointed at the engine) and the media stream
WebSocket /webhooks/engine/stream.

Operator (platform operators only, audited): status, a test call that rings a phone from one of our numbers, the
simulator (a recording plays the caller – no phone rings), recordings, recent engine calls, and moving a number's
incoming calls to the engine. Moving a number is never automatic; `/operator/telephony/numbers/{id}/inbound` moves
it back to Vapi."""
from __future__ import annotations

import re
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, Request, Response, UploadFile, WebSocket
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session as OrmSession

from app.config import get_settings
from app.core.audit import record_audit
from app.core.auth import Principal
from app.core.errors import NotFound, NotImplementedYet, ValidationFailed
from app.db import get_db
from app.models import Call, PhoneNumber
from app.modules.callengine import call as engine_call
from app.modules.voices.operator_router import operator

webhook_router = APIRouter(prefix="/webhooks/engine", tags=["webhooks"])
router = APIRouter(prefix="/operator/telephony/engine", tags=["telephony-operator"])

E164 = re.compile(r"^\+[1-9]\d{6,14}$")
FIXTURES = Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "linden"
SIM_PREFIX = "platform/engine-sim"


# --------------------------------------------------------------------------- Twilio

@webhook_router.post("/twiml")
async def twiml(request: Request):
    """Twilio's voice webhook for a number pointed at the engine. The signed token in the URL names the number."""
    tok = engine_call.verify(request.query_params.get("t"))
    if tok is None or tok.get("m") != "inbound":
        return Response('<?xml version="1.0" encoding="UTF-8"?><Response><Reject/></Response>', media_type="text/xml")
    form = await request.form()
    caller = str(form.get("From") or "") or None
    return Response(engine_call.twiml(request.query_params["t"], caller), media_type="text/xml")


@webhook_router.websocket("/stream")
async def stream(socket: WebSocket):
    await engine_call.serve(socket)


# --------------------------------------------------------------------------- operator

def _audit(db, request, principal, ws_id, action: str, after: dict) -> None:
    record_audit(db, workspace_id=ws_id, actor_user_id=principal.user.id, action=action, object_type="phone_number",
                 object_id=ws_id, after=after, request_id=request.state.request_id)


def _twilio():
    from app.modules.telephony import providers

    pair = providers.providers()
    if pair is None:
        raise NotImplementedYet("Platformtelefoni er ikke sat op (Twilio-nøgler mangler)", code="telephony_not_configured")
    return pair[0]


def _number(db: OrmSession, number_id: uuid.UUID | None) -> PhoneNumber:
    n = db.get(PhoneNumber, number_id) if number_id else db.scalar(
        select(PhoneNumber).where(PhoneNumber.active.is_(True)).order_by(PhoneNumber.created_at))
    if n is None:
        raise NotFound("Nummeret findes ikke")
    return n


def _ready() -> None:
    from app.modules.callengine import providers

    missing = [k for k, ok in providers.configured().items() if not ok]
    if missing:
        raise NotImplementedYet(f"Motoren mangler nøgler: {', '.join(missing)}", code="engine_not_configured")


@router.get("")
def status(_: Principal = Depends(operator), db: OrmSession = Depends(get_db)):
    from app.modules.callengine import providers

    calls = db.scalars(select(Call).where(Call.provider == engine_call.PROVIDER).order_by(Call.created_at.desc())
                       .limit(20)).all()
    s = get_settings()
    return {"configured": providers.configured(), "model": s.engine_model or s.vapi_model or providers.DEFAULT_MODEL,
            "calls": [{"call_sid": c.provider_call_id, "started_at": c.started_at, "duration_seconds": c.duration_seconds,
                       "ended_reason": c.ended_reason, "summary": c.summary, "conversation_id": c.conversation_id,
                       "recording": f"/api/v1/operator/telephony/engine/calls/{c.provider_call_id}/recording.wav"}
                      for c in calls]}


class EngineTestCallIn(BaseModel):
    to: str = Field(..., description="Det nummer, Peter skal ringe til (E.164, fx +4512345678)")
    number_id: uuid.UUID | None = Field(default=None, description="Vores nummer, der ringer ud (standard: det første aktive)")


@router.post("/test-call")
def test_call(body: EngineTestCallIn, request: Request, principal: Principal = Depends(operator),
              db: OrmSession = Depends(get_db)):
    """Peter rings `to` from one of our numbers and runs the call on the engine – the number's incoming calls are not
    touched. Uses the number's own greeting, knowledge, tools and voice; the call is stored without creating a lead."""
    _ready()
    to = re.sub(r"[\s()-]", "", body.to)
    if not E164.match(to):
        raise ValidationFailed("Ugyldigt telefonnummer – brug +45…", field_errors=[{"field": "to"}])
    n = _number(db, body.number_id)
    twilio = _twilio()
    found = twilio.find_by_e164(n.e164)
    if found is None:
        raise NotFound(f"{n.e164} findes ikke på Dialogbots Twilio-konto", code="number_not_on_twilio")
    account_sid, _number_sid = found
    sid = twilio.create_call(account_sid, to, n.e164, engine_call.twiml(engine_call.sign(n.id, "test", engine_call.TEST_TTL_S)))
    _audit(db, request, principal, n.workspace_id, "telephony.engine_test_call", {"to": to, "from": n.e164, "call_sid": sid})
    db.commit()
    return {"call_sid": sid, "from": n.e164, "to": to,
            "recording": f"/api/v1/operator/telephony/engine/calls/{sid}/recording.wav"}


@router.get("/calls/{call_sid}/recording.wav")
def call_recording(call_sid: str, _: Principal = Depends(operator)):
    from app.modules.voices import storage

    if not re.fullmatch(r"CA[0-9a-fA-F]{32}", call_sid):
        raise NotFound("Ukendt opkald")
    data = storage.get(engine_call.recording_key(call_sid))
    if data is None:
        raise NotFound("Optagelsen findes ikke (endnu)", code="no_recording")
    return Response(data, media_type="audio/wav",
                    headers={"content-disposition": f"attachment; filename=opkald-{call_sid}.wav"})


@router.post("/simulate")
async def simulate(request: Request, file: UploadFile | None = File(default=None), fixture: str | None = Form(default=None),
                   number_id: uuid.UUID | None = Form(default=None), principal: Principal = Depends(operator),
                   db: OrmSession = Depends(get_db)):
    """A recording (16-bit WAV, any rate) plays the caller; the real engine answers on a virtual line at real speed.
    Returns the turn-by-turn log with latencies, and a two-track recording (left: caller, right: Peter).
    `fixture` names a known recording from tests/fixtures/linden instead of an upload. No phone rings."""
    import asyncio

    from app.modules.callengine import audio
    from app.modules.callengine import simulate as sim
    from app.modules.callengine.engine import CallEngine
    from app.modules.voices import storage

    _ready()
    if fixture:
        name = re.sub(r"[^a-z0-9_]", "", fixture.lower())
        path = FIXTURES / f"{name}.wav"
        if not path.is_file():
            raise NotFound(f"Ukendt testlyd: {name}", code="fixture_not_found")
        raw = path.read_bytes()
    elif file is not None:
        raw = await file.read()
    else:
        raise ValidationFailed("Vedhæft en WAV eller angiv fixture", field_errors=[{"field": "file"}])
    try:
        caller = audio.wav_to_ulaw8k(raw)
    except Exception as e:  # noqa: BLE001
        raise ValidationFailed(f"Kunne ikke læse lyden: {e}", field_errors=[{"field": "file"}]) from e
    if len(caller) > 120 * audio.RATE:
        raise ValidationFailed("Højst 2 minutters lyd", field_errors=[{"field": "file"}])
    n = _number(db, number_id)
    setup = await asyncio.to_thread(engine_call.build, n.id, None)
    sim_id = uuid.uuid4().hex[:16]

    def factory(line):
        stt, llm, tts = engine_call.make_providers(setup)
        return CallEngine(engine_call.call_config(setup), stt, llm, tts, line,
                          run_tool=engine_call.tool_runner(setup, None, f"sim-{sim_id}"))

    out = await sim.run(factory, caller)
    res = sim.result(out, sim_id)
    await asyncio.to_thread(storage.put, f"{SIM_PREFIX}/{sim_id}.wav", out["recording"].wav(), "audio/wav")
    res["recording"] = f"/api/v1/operator/telephony/engine/simulations/{sim_id}.wav"
    _audit(db, request, principal, n.workspace_id, "telephony.engine_simulated",
           {"simulation": sim_id, "fixture": fixture, **res["summary"]})
    db.commit()
    return res


@router.get("/simulations/{sim_id}.wav")
def simulation_recording(sim_id: str, _: Principal = Depends(operator)):
    from app.modules.voices import storage

    if not re.fullmatch(r"[0-9a-f]{16}", sim_id):
        raise NotFound("Ukendt simulering")
    data = storage.get(f"{SIM_PREFIX}/{sim_id}.wav")
    if data is None:
        raise NotFound("Optagelsen findes ikke")
    return Response(data, media_type="audio/wav", headers={"content-disposition": f"attachment; filename=sim-{sim_id}.wav"})


class EngineRouteIn(BaseModel):
    confirm: bool = Field(False, description="Skal være true: alle indgående opkald på nummeret flyttes til motoren")


@router.post("/numbers/{number_id}/inbound")
def route_to_engine(number_id: uuid.UUID, body: EngineRouteIn, request: Request, principal: Principal = Depends(operator),
                    db: OrmSession = Depends(get_db)):
    """Point a number's incoming calls at the engine (Twilio voice webhook → our TwiML). Undo:
    POST /operator/telephony/numbers/{id}/inbound puts it back on Vapi."""
    _ready()
    if not body.confirm:
        raise ValidationFailed("Bekræft med confirm=true – alle indgående opkald flyttes", field_errors=[{"field": "confirm"}])
    n = _number(db, number_id)
    twilio = _twilio()
    found = twilio.find_by_e164(n.e164)
    if found is None:
        raise NotFound(f"{n.e164} findes ikke på Dialogbots Twilio-konto", code="number_not_on_twilio")
    url = f"{get_settings().public_base_url.rstrip('/')}/api/v1/webhooks/engine/twiml?t={engine_call.sign(n.id, 'inbound')}"
    twilio.set_voice_url(found[0], found[1], url)
    _audit(db, request, principal, n.workspace_id, "telephony.inbound_routed", {"e164": n.e164, "engine": "dialogbot"})
    db.commit()
    return {"e164": n.e164, "engine": "dialogbot"}
