"""Claude through the official Anthropic SDK, for the outreach agents only.

- Every call needs a `Clearance` from the ComplianceEngine. Without one the call is refused before any request is
  built – that is what keeps blocked markets from costing a single token.
- Answers are structured: the model must finish by calling one tool whose input schema is the pydantic model, and the
  input is validated (one corrective retry on a validation error).
- Transport errors: the SDK retries 429/5xx/connection errors with exponential backoff (OUTREACH_AI_MAX_RETRIES).
- Token usage of every call is written to outreach_logs (kind llm_usage) and to the structured log.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

import structlog
from pydantic import BaseModel, ValidationError
from sqlalchemy.orm import Session as OrmSession

from app.config import get_settings
from app.core.errors import NotImplementedYet
from app.models import OutreachLog
from app.modules.outreach.compliance import Clearance, ComplianceBlocked
from app.modules.outreach.schemas import tool

log = structlog.get_logger("dialogbot.outreach.llm")
WEB_SEARCH_TOOL = {"type": "web_search_20250305", "name": "web_search", "max_uses": 4}
MAX_TURNS = 4

_client_override: Any = None


def set_client_override(client: Any) -> None:
    """Tests (and the offline dry run) swap in an object with the SDK's `messages.create(**kwargs)` shape."""
    global _client_override
    _client_override = client


class OutreachAIError(Exception):
    pass


@dataclass
class Call:
    data: BaseModel
    input_tokens: int
    output_tokens: int
    model: str


def _client():
    if _client_override is not None:
        return _client_override
    s = get_settings()
    if s.ai_provider == "fake":      # dev/test only (config refuses it elsewhere)
        from app.modules.outreach.fake import FakeClaude

        return FakeClaude()
    if s.ai_provider != "anthropic":
        raise NotImplementedYet("Outreach needs AI_PROVIDER=anthropic and ANTHROPIC_API_KEY (or --fake-ai in a dry run)",
                                code="ai_not_configured")
    import anthropic

    return anthropic.Anthropic(api_key=s.anthropic_api_key, max_retries=s.outreach_ai_max_retries, timeout=90.0)


def structured(db: OrmSession, *, clearance: Clearance, purpose: str, model: str, system: str, user: str,
               output: type[BaseModel], tool_name: str, tool_description: str, max_tokens: int = 1500,
               web_search: bool = False, lead_id=None) -> Call:
    if not isinstance(clearance, Clearance):
        raise ComplianceBlocked("no model call without a ComplianceEngine clearance")
    import anthropic

    client = _client()
    out_tool = tool(tool_name, tool_description, output)
    tools = [out_tool] + ([WEB_SEARCH_TOOL] if web_search else [])
    messages: list[dict] = [{"role": "user", "content": user}]
    force = not web_search          # with web search the model first searches, then is told to answer
    used_in = used_out = 0
    corrected = False
    for _turn in range(MAX_TURNS):
        started = time.monotonic()
        try:
            resp = client.messages.create(
                model=model, max_tokens=max_tokens, system=system, messages=messages, tools=tools,
                tool_choice={"type": "tool", "name": tool_name} if force else {"type": "auto"})
        except anthropic.APIError as e:  # after the SDK's own retries
            _log(db, lead_id, purpose, model, "error", used_in, used_out, 0, error=type(e).__name__)
            raise OutreachAIError(f"{purpose}: {type(e).__name__}") from e
        u = resp.usage
        used_in += int(getattr(u, "input_tokens", 0) or 0)
        used_out += int(getattr(u, "output_tokens", 0) or 0)
        _log(db, lead_id, purpose, str(getattr(resp, "model", model)), str(resp.stop_reason),
             int(getattr(u, "input_tokens", 0) or 0), int(getattr(u, "output_tokens", 0) or 0),
             int((time.monotonic() - started) * 1000), request_id=getattr(resp, "_request_id", None))
        call = next((b for b in resp.content if getattr(b, "type", None) == "tool_use" and b.name == tool_name), None)
        if call is not None:
            try:
                return Call(output.model_validate(call.input), used_in, used_out, str(getattr(resp, "model", model)))
            except ValidationError as e:
                if corrected:
                    raise OutreachAIError(f"{purpose}: the answer did not fit the schema") from e
                corrected = True
                messages += [{"role": "assistant", "content": resp.content},
                             {"role": "user", "content": [{"type": "tool_result", "tool_use_id": call.id, "is_error": True,
                                                           "content": f"Invalid input, call {tool_name} again: {e.errors()[:5]}"}]}]
                force = True
                continue
        messages.append({"role": "assistant", "content": resp.content})
        if resp.stop_reason != "pause_turn":   # the model stopped without answering: ask for the tool call
            messages.append({"role": "user", "content": f"Now call {tool_name} with your result."})
            force = True
    raise OutreachAIError(f"{purpose}: no structured answer after {MAX_TURNS} turns")


def _log(db, lead_id, purpose, model, outcome, tin, tout, ms, **extra) -> None:
    detail = {"purpose": purpose, "model": model, "input_tokens": tin, "output_tokens": tout, "latency_ms": ms,
              **{k: v for k, v in extra.items() if v}}
    db.add(OutreachLog(lead_id=lead_id, kind="llm_usage", outcome=outcome[:24], detail=detail))
    log.info("outreach_llm_call", lead_id=str(lead_id) if lead_id else None, **detail)
