"""Tool-builder and action runner: the one place the phone assistant and the webchat get their function tools.

- `tools_for(db, ws, channel)` lists the actions of every *connected* connector (plus built-in ones), as
  provider-neutral `Tool`s. `to_vapi()` / `to_anthropic()` render them for the two callers.
- `execute(db, ws, name, args, ctx)` validates `args` against the action's JSON schema, refuses unconfirmed
  actions that require confirmation, runs the adapter, and writes exactly one `action_runs` row – also when the
  action fails or is refused. The returned text is what the model reads back; it never contains credentials.

Payment and knowledge are out of reach by construction: no connector declares actions on them.
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

import jsonschema
from sqlalchemy import select
from sqlalchemy.orm import Session as OrmSession

from app.models import ActionRun, Workspace
from app.modules.integrations import connectors
from app.modules.integrations.connectors.base import ActionError, ActionRefused, ActionSpec, RunContext

MAX_RESULT_CHARS = 1500
CONFIRM_FIELD = "bekraeftet"


@dataclass(frozen=True)
class Tool:
    connector: str
    spec: ActionSpec

    @property
    def name(self) -> str:
        return self.spec.name

    def schema(self) -> dict:
        s = dict(self.spec.input_schema)
        if self.spec.confirm:
            props = dict(s.get("properties") or {})
            props[CONFIRM_FIELD] = {"type": "boolean",
                                    "description": "true kun når kunden udtrykkeligt har sagt ja til præcis denne handling"}
            s["properties"] = props
            s["required"] = sorted(set(s.get("required") or []) | {CONFIRM_FIELD})
        return s

    def description(self) -> str:
        d = self.spec.description
        if self.spec.confirm:
            d += f" Kræver kundens udtrykkelige ja først; sæt {CONFIRM_FIELD}=true kun efter det."
        return d


def tools_for(db: OrmSession, ws: Workspace, channel: str) -> list[Tool]:
    """Actions the assistant may call right now on this channel. Only connectors whose status is `connected`."""
    out: list[Tool] = []
    seen: set[str] = set()
    for key, status in connectors.statuses(db, ws.id).items():
        if status["status"] != "connected":
            continue
        spec = connectors.spec(key)
        for a in spec.actions:
            # test = a person trying it from Integrationer; it may run any action the connector offers
            if (channel in a.channels or channel == "test") and a.name not in seen:
                seen.add(a.name)
                out.append(Tool(key, a))
    return out


def to_vapi(tools: list[Tool]) -> list[dict]:
    return [{"type": "function", "function": {"name": t.name, "description": t.description(), "parameters": t.schema()}}
            for t in tools]


def to_anthropic(tools: list[Tool]) -> list[dict]:
    return [{"name": t.name, "description": t.description(), "input_schema": t.schema()} for t in tools]


def prompt_section(tools: list[Tool]) -> str:
    """Text appended to the system prompt so the model knows it *can* act, and how to talk about it."""
    if not tools:
        return ""
    lines = ["Handlinger: Du kan udføre følgende handlinger i virksomhedens egne systemer med værktøjerne nedenfor. "
             "Sig altid kort, hvad du gør, og bekræft resultatet bagefter med kundens egne ord. Hvis en handling "
             "fejler, så sig det ærligt og tilbyd, at en medarbejder følger op. Opfind aldrig et resultat."]
    for t in tools:
        lines.append(f"- {t.name}: {t.spec.label}" + (" (kræver kundens ja)" if t.spec.confirm else ""))
    return "\n".join(lines)


def _validate(spec: ActionSpec, tool: Tool, args: dict) -> dict:
    if not isinstance(args, dict):
        raise ActionRefused("Ugyldigt input til handlingen", code="invalid_input")
    if spec.confirm and args.get(CONFIRM_FIELD) is not True:
        raise ActionRefused("Handlingen kræver, at kunden først siger ja. Spørg kunden, og prøv igen med "
                            f"{CONFIRM_FIELD}=true.", code="confirmation_required")
    try:
        jsonschema.validate(args, tool.schema())
    except jsonschema.ValidationError as e:
        path = ".".join(str(p) for p in e.absolute_path) or "input"
        raise ActionRefused(f"Ugyldigt input ({path}): {e.message[:120]}", code="invalid_input") from e
    return args


def execute(db: OrmSession, ws: Workspace, name: str, args: dict, ctx: RunContext) -> tuple[str, ActionRun]:
    """Run one action end to end. Returns (text for the model, the persisted run). Never raises for a failed or
    refused action – those are results the model must handle; only programming errors propagate."""
    tools = {t.name: t for t in tools_for(db, ws, ctx.channel)}
    tool = tools.get(name)
    started = time.monotonic()
    run = ActionRun(workspace_id=ws.id, conversation_id=ctx.conversation_id, channel=ctx.channel,
                    connector=tool.connector if tool else "?", action=name[:60], input={}, output={}, status="failed",
                    provider_call_id=ctx.provider_call_id)
    if tool is None:
        run.status, run.error = "refused", "Handlingen findes ikke eller er ikke forbundet"
        run.label = f"Ukendt handling: {name[:40]}"
        _finish(db, run, started)
        return "Handlingen er ikke tilgængelig. Tilbyd i stedet, at en medarbejder følger op.", run
    spec = tool.spec
    run.label = spec.label
    try:
        data = _validate(spec, tool, args or {})
        run.input = data
        adapter = connectors.adapter_for(db, ws.id, tool.connector)
        result = adapter.run(name, data, ctx)
        run.output = result.output
        run.status, run.simulated, run.provider_ref = "ok", result.simulated, result.provider_ref
        run.label = (result.label or (spec.summarize(data, result.output) if spec.summarize else "") or spec.label)[:200]
        _finish(db, run, started)
        connectors.after_action(db, ws, run)
        text = result.output.get("besked") or run.label
        return str(text)[:MAX_RESULT_CHARS] + (" (simuleret)" if result.simulated else ""), run
    except ActionRefused as e:
        run.status, run.error = "refused", e.message[:500]
        _finish(db, run, started)
        return f"Handlingen blev ikke udført: {e.message}", run
    except ActionError as e:
        run.status, run.error = "failed", e.message[:500]
        _finish(db, run, started)
        connectors.note_failure(db, ws.id, tool.connector, e)
        return f"Handlingen fejlede: {e.message} Sig det ærligt, og tilbyd at en medarbejder følger op.", run


def _finish(db: OrmSession, run: ActionRun, started: float) -> None:
    run.duration_ms = int((time.monotonic() - started) * 1000)
    db.add(run)
    db.flush()


def runs_for_conversation(db: OrmSession, conversation_id: uuid.UUID) -> list[ActionRun]:
    return list(db.scalars(select(ActionRun).where(ActionRun.conversation_id == conversation_id)
                           .order_by(ActionRun.created_at, ActionRun.id)))


def recent_runs(db: OrmSession, workspace_id: uuid.UUID, *, connector: str | None = None, limit: int = 50) -> list[ActionRun]:
    q = select(ActionRun).where(ActionRun.workspace_id == workspace_id)
    if connector:
        q = q.where(ActionRun.connector == connector)
    return list(db.scalars(q.order_by(ActionRun.created_at.desc()).limit(limit)))


def run_out(r: ActionRun) -> dict:
    return {"id": str(r.id), "conversation_id": str(r.conversation_id) if r.conversation_id else None,
            "channel": r.channel, "connector": r.connector, "action": r.action, "label": r.label, "status": r.status,
            "error": r.error, "input": r.input, "output": r.output, "duration_ms": r.duration_ms,
            "simulated": r.simulated, "provider_ref": r.provider_ref,
            "created_at": (r.created_at or datetime.now(UTC)).isoformat()}
