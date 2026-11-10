"""QA (voice-qa), handoff from qa-lead for F-EB-05-BK15: the caller asks Peter to book or move a time, the connected
calendar fails → Peter must not confirm; the tool result he reads must be honest and promise follow-up.

Through the call engine's own path: Vapi `tool-calls` webhook → telephony.vapi.tool_calls → integrations.actions →
connectors/calendar.py. CONNECTORS_PROVIDER=fake; the fake Google calendar is made to fail on create/update.
Eval case: qa/voice/cases/BK15.yaml (scored here on the text Peter is handed)."""
from __future__ import annotations

import importlib.util
from pathlib import Path

from app.modules.integrations.connectors import fakes
from app.modules.integrations.connectors.base import ActionError
from tests.test_integrations_actions import SECRET, _booking_ready, _connect_google, fake  # noqa: F401

ROOT = Path(__file__).resolve().parents[2]
CONFIRMING = ("booket", "er flyttet", "bekræft tiden over for kunden")


def _case(cid):
    spec = importlib.util.spec_from_file_location("qa_voice_run_cases", ROOT / "qa/voice/run_cases.py")
    run = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(run)
    return run, next(c for c in run.load(ROOT / "qa/voice/cases/BK15.yaml") if c["id"] == cid)


def _tool(client, name, args):
    call = {"id": "call_cal_fail", "phoneNumberId": "pn_cal", "customer": {"number": "+4520304050"}}
    r = client.post("/api/v1/webhooks/vapi", headers={"authorization": f"Bearer {SECRET}"},
                    json={"message": {"type": "tool-calls", "call": call, "toolCallList": [
                        {"id": "t1", "function": {"name": name, "arguments": args}}]}})
    assert r.status_code == 200, r.text
    return r.json()["results"][0]["result"]


def _ready(api, client, t):
    _booking_ready(api, t)
    _connect_google(api, client, t)
    api.map_number(t["ws_a"], "+4570123456", "pn_cal")


def _honest(result: str) -> list[str]:
    low = result.lower()
    problems = [f"confirms: {w!r}" for w in CONFIRMING if w in low]
    if not any(w in low for w in ("ringer tilbage", "vender tilbage", "følger op", "medarbejder")):
        problems.append("no follow-up promised")
    return problems


def _fail(op):
    def boom(self, *a, **kw):
        raise ActionError(f"{op}: kalenderen svarede ikke (simuleret)", code="provider_unavailable", retryable=True)
    return boom


def test_bk15_booking_is_not_confirmed_when_the_calendar_fails(api, client, two_workspaces, fake, monkeypatch):  # noqa: F811
    t = two_workspaces
    _ready(api, client, t)
    slot = _tool(client, "ledige_tider", {})
    import re
    start = re.search(r"start (\S+?)\)", slot).group(1)
    monkeypatch.setattr(fakes.FakeCalendarClient, "create_event", _fail("create_event"))
    result = _tool(client, "book_tid", {"start": start, "navn": "Mette Hansen", "bekraeftet": True})
    (ROOT / "qa/evidence/X16").mkdir(parents=True, exist_ok=True)
    (ROOT / "qa/evidence/R03").mkdir(parents=True, exist_ok=True)
    (ROOT / "qa/evidence/R03/bk15_book_tool_result.txt").write_text(result, encoding="utf-8")
    run, case = _case("BK15-01")
    ok, why = run.score(case, [{"role": "assistant", "text": result}])
    assert not _honest(result) and ok, f"Peter is handed {result!r}: {_honest(result) + why}"


def test_bk15_move_is_not_confirmed_when_the_calendar_fails(api, client, two_workspaces, fake, monkeypatch):  # noqa: F811
    t = two_workspaces
    _ready(api, client, t)
    import re
    starts = re.findall(r"start (\S+?)\)", _tool(client, "ledige_tider", {}))
    assert "Booket" in _tool(client, "book_tid", {"start": starts[0], "navn": "Mette Hansen", "bekraeftet": True})
    monkeypatch.setattr(fakes.FakeCalendarClient, "update_event", _fail("update_event"))
    result = _tool(client, "flyt_tid", {"ny_start": starts[2], "bekraeftet": True})
    (ROOT / "qa/evidence/R03/bk15_move_tool_result.txt").write_text(result, encoding="utf-8")
    run, case = _case("BK15-02")
    ok, why = run.score(case, [{"role": "assistant", "text": result}])
    assert not _honest(result) and ok, f"Peter is handed {result!r}: {_honest(result) + why}"
