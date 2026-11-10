"""QA R03 [DB-018] (voice-qa): "Requested-callback configuration, offered time windows, verification and
queue/results."

Two doors lead to a call-back: the web widget's "Bliv kontaktet" (webchat/public.py → leads.callback windows) and a
phone call where Peter says "en medarbejder ringer tilbage" (the end-of-call report → telephony.vapi._after_report).
Both are exercised offline; no call or SMS is placed."""
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from sqlalchemy import select

from app.models import Lead, Task
from app.modules.telephony import vapi as vapi_mod
from tests.test_telephony import _post, _setup, configured  # noqa: F401
from tests.test_webchat import PUB, _say, _start, fake, live  # noqa: F401

TZ = ZoneInfo("Europe/Copenhagen")


# --------------------------------------------------------------------------- web widget: windows → queue (pass)

def test_r03_webchat_callback_window_becomes_the_leads_period_and_the_tasks_due_time(client, live, db):  # noqa: F811
    key = live["key"]
    conv = _start(client, key).json()
    assert _say(client, key, conv, "Kan I ringe mig op om et tilbud?").status_code == 200
    opts = client.get(f"{PUB}/{key}/callback-windows").json()
    assert opts["timezone"] == "Europe/Copenhagen" and opts["options"][0]["key"] == "asap"
    keys = [o["key"] for o in opts["options"]]
    assert "next_am" in keys
    url = f"{PUB}/{key}/conversations/{conv['conversation_id']}/contact"
    h = {"x-visitor-token": conv["visitor_token"], "origin": "http://localhost:8000"}
    body = {"name": "Mette Hansen", "phone": "20 30 40 50", "window": "next_am", "consent": True}
    assert client.post(url, json=body | {"phone": None, "email": "m@testmail.dk"}, headers=h).status_code == 422
    assert client.post(url, json=body | {"window": "sunday_night"}, headers=h).status_code == 422
    assert client.post(url, json=body | {"consent": False}, headers=h).status_code == 422
    r = client.post(url, json=body, headers=h)
    assert r.status_code == 200, r.text
    lead = db.scalar(select(Lead).where(Lead.workspace_id == uuid.UUID(live["ws_a"])))
    task = db.scalar(select(Task).where(Task.lead_id == lead.id))
    start = lead.callback_from.astimezone(TZ)
    assert start.hour == 8 and start.weekday() < 5 and lead.callback_to.astimezone(TZ).hour == 12
    assert task.due_at == lead.callback_from and "formiddag (8–12)" in task.title


# --------------------------------------------------------------------------- phone: the call-back promise (F-VQ-08/09)

def _report(call_id, caller, turns, ended="2026-11-10T09:05:00Z"):
    return {"type": "end-of-call-report", "endedReason": "customer-ended-call",
            "call": {"id": call_id, "phoneNumberId": "pn_123", **({"customer": {"number": caller}} if caller else {})},
            "startedAt": "2026-11-10T09:00:00Z", "endedAt": ended,
            "analysis": {"summary": "Kunden vil ringes op om et tilbud på afslibning."},
            "artifact": {"messages": [{"role": r, "message": m} for r, m in turns]}}


WITHHELD = [
    ("bot", "Hej, du har ringet til Fjord Gulvservice. Hvad kan jeg hjælpe med?"),
    ("user", "Jeg vil gerne have et tilbud på afslibning, kan I ringe mig op?"),
    ("bot", "Ja, selvfølgelig. Dit nummer er skjult – hvilket nummer skal vi ringe på?"),
    ("user", "Tyve, tredive, fyrre, halvtreds."),
    ("bot", "Tyve, tredive, fyrre, halvtreds – er det rigtigt?"),
    ("user", "Ja."),
    ("bot", "Tak. En medarbejder ringer tilbage. Hav en god dag."),
]


def test_r03_a_callback_promised_to_a_withheld_number_reaches_the_queue(client, api, two_workspaces, configured, db):  # noqa: F811
    """The prompt (ai.service.known_number_section, withheld number) makes Peter collect the number pair by pair and
    promise "En medarbejder ringer tilbage". That promise must end up as a lead + call-back task with that number."""
    _setup(api, two_workspaces)
    assert _post(client, _report("call_withheld", None, WITHHELD)).json()["outcome"] == "applied"
    leads = db.scalars(select(Lead)).all()
    tasks = db.scalars(select(Task)).all()
    assert leads and tasks, "the caller was promised a call-back, but no lead and no task were created"
    assert leads[0].contact_phone in ("+4520304050", "20304050", "20 30 40 50")


def test_r03_a_callback_to_another_number_uses_that_number(client, api, two_workspaces, configured, db):  # noqa: F811
    """known_number_section: "Vil kunden hellere ringes op på et andet nummer, så tag det …". The task must then say
    which number to ring – not the caller id."""
    _setup(api, two_workspaces)
    turns = [("bot", "Hej, du har ringet til Fjord Gulvservice."),
             ("user", "Kan I ringe mig op i morgen? Men ring hellere på mit arbejdsnummer, enogtyve, enogtredive, "
                      "enogfyrre, enoghalvtreds."),
             ("bot", "Enogtyve, enogtredive, enogfyrre, enoghalvtreds – er det rigtigt?"), ("user", "Ja."),
             ("bot", "Så ringer en medarbejder på det nummer. Hav en god dag.")]
    _post(client, _report("call_other", "+4520304050", turns))
    lead = db.scalar(select(Lead))
    task = db.scalar(select(Task))
    assert lead is not None and task is not None
    shown = f"{lead.contact_phone} | {task.title}"
    assert "21314151" in shown.replace(" ", "").replace("+45", ""), f"call-back goes to the caller id instead: {shown}"


def test_r03_a_phone_callback_is_due_in_working_hours(client, api, two_workspaces, configured, db, monkeypatch):  # noqa: F811
    """A call at 22:30 on a Friday that ends with "en medarbejder ringer tilbage": the task is due now + 4 h (02:30
    Saturday night), and no window is offered or stored for a phone call-back (lead.callback_from stays empty)."""
    fixed = datetime(2026, 11, 13, 21, 30, tzinfo=UTC)  # Friday 22:30 in Copenhagen

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return fixed if tz else fixed.replace(tzinfo=None)

    monkeypatch.setattr(vapi_mod, "datetime", Clock)
    _setup(api, two_workspaces)
    turns = [("bot", "Hej, du har ringet til Fjord Gulvservice."),
             ("user", "Kan I ringe mig op mandag formiddag om et tilbud?"),
             ("bot", "Ja. Skal vi ringe på det nummer, du ringer fra – det, der ender på fyrre halvtreds?"),
             ("user", "Ja."), ("bot", "Så ringer en medarbejder tilbage. Hav en god dag.")]
    _post(client, _report("call_late", "+4520304050", turns, ended="2026-11-13T21:31:00Z"))
    task = db.scalar(select(Task))
    lead = db.scalar(select(Lead))
    due = task.due_at.astimezone(TZ)
    problems = []
    if not (due.weekday() < 5 and 8 <= due.hour < 16):
        problems.append(f"task due {due:%A %H:%M} local")
    if lead.callback_from is None:
        problems.append("no call-back window stored on the lead (the caller asked for Monday morning)")
    assert not problems, "; ".join(problems)
