"""Customers' own call recordings: off by default (and then Vapi is told not to record), the caller is told when it is
on, the audio is fetched into the private bucket, the customer listens under «Opkald» through a short-lived link,
can delete it, and it goes by itself after the number's retention."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import httpx
import pytest
from sqlalchemy import select

from app.config import get_settings
from app.models import Call, CallRecording, SalesMediaAccessLog
from app.modules.sales import recordings
from app.modules.telephony import call_recordings
from app.worker import runner
from tests.test_sales_channel_privacy import Bucket
from tests.test_telephony import SECRET, _post, _report, _setup


@pytest.fixture
def configured(monkeypatch):
    monkeypatch.setenv("VAPI_SERVER_SECRET", SECRET)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def media(monkeypatch):
    bucket, vapi_calls = Bucket(), []

    def fake_vapi(method, path, **kw):
        vapi_calls.append((method, path))
        if path.endswith("/mono-recording"):
            return httpx.Response(200, content=b"RIFFfake-wav", headers={"content-type": "audio/wav"})
        return httpx.Response(200, json={})

    recordings.set_backend_override(bucket)
    recordings.set_vapi_override(fake_vapi)
    yield {"bucket": bucket, "vapi": vapi_calls}
    recordings.set_backend_override(None)
    recordings.set_vapi_override(None)


@pytest.fixture
def storage(monkeypatch):
    monkeypatch.setenv("SALES_RECORDING_STORAGE", "supabase")
    monkeypatch.setenv("SUPABASE_URL", "https://project.supabase.invalid")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "service-role-test")
    monkeypatch.setenv("VAPI_API_KEY", "vapi-private-test")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _assistant(client, call_id="c"):
    return _post(client, {"type": "assistant-request", "call": {"id": call_id, "phoneNumberId": "pn_123"}}).json()["assistant"]


def _turn_on(api, t, n, **kw):
    return api.patch(t["tok_a"], f"/workspaces/{t['ws_a']}/phone-numbers/{n['id']}", {"record_calls": True, **kw})


def test_off_by_default_vapi_is_told_not_to_record_and_no_link_is_kept(client, api, two_workspaces, configured, db,
                                                                        media):
    n = _setup(api, two_workspaces)
    assert n["record_calls"] is False and n["recording_retention_days"] == 90
    a = _assistant(client)
    assert a["artifactPlan"] == {"recordingEnabled": False} and "optaget" not in a["firstMessage"]
    rep = _report()
    rep["artifact"]["recordingUrl"] = "https://storage.vapi.ai/x.wav"
    _post(client, rep)
    call = db.scalar(select(Call))
    assert call.recording_url is None and call.recording_status == "NOT_RECORDED"
    runner.drain()
    assert media["bucket"].files == {} and not any(p.endswith("/mono-recording") for _m, p in media["vapi"])
    t = two_workspaces
    detail = api.get(t["tok_a"], f"/workspaces/{t['ws_a']}/conversations/{call.conversation_id}").json()
    assert detail["call"]["recording"]["status"] == "NOT_RECORDED"
    r = api.get(t["tok_a"], f"/workspaces/{t['ws_a']}/calls/{call.id}/recording")
    assert r.status_code == 409 and r.json()["message"] == "Opkaldet blev ikke optaget"


def test_cannot_turn_on_without_storage(api, two_workspaces, configured):
    n = _setup(api, two_workspaces)
    r = _turn_on(api, two_workspaces, n)
    assert r.status_code == 409 and r.json()["code"] == "recording_not_configured"


def test_recorded_call_is_disclosed_fetched_played_and_deleted(client, api, two_workspaces, configured, storage, db,
                                                               media):
    t = two_workspaces
    n = _setup(api, t)
    assert _turn_on(api, t, n, recording_retention_days=12).status_code == 422  # only the offered choices
    on = _turn_on(api, t, n, recording_retention_days=30).json()
    assert on["record_calls"] is True and on["recording_retention_days"] == 30 and on["recording_available"] is True
    a = _assistant(client)
    assert a["artifactPlan"] == {"recordingEnabled": True}
    assert "Samtalen bliver også optaget. Hvad kan jeg hjælpe med?" in a["firstMessage"]

    _post(client, _report())
    call = db.scalar(select(Call))
    assert call.recording_status == "PENDING"
    runner.drain()
    db.expire_all()
    rec = db.scalar(select(CallRecording))
    assert rec.status == "AVAILABLE" and rec.storage_key == f"calls/{t['ws_a']}/{call.id}.wav"
    assert media["bucket"].files[rec.storage_key] == b"RIFFfake-wav"

    detail = api.get(t["tok_a"], f"/workspaces/{t['ws_a']}/conversations/{call.conversation_id}").json()
    assert detail["call"]["recording"]["status"] == "AVAILABLE" and detail["call"]["recording"]["delete_after"]
    assert "storage_key" not in str(detail) and "storage.vapi.ai" not in str(detail)
    play = api.get(t["tok_a"], f"/workspaces/{t['ws_a']}/calls/{call.id}/recording").json()
    assert play["url"].startswith("https://storage.invalid/calls/") and play["expires_in"] == 600
    assert db.scalar(select(SalesMediaAccessLog.kind)) == "play"
    # another workspace can neither listen nor delete
    assert api.get(t["tok_b"], f"/workspaces/{t['ws_b']}/calls/{call.id}/recording").status_code == 404
    assert api.delete(t["tok_b"], f"/workspaces/{t['ws_b']}/calls/{call.id}/recording").status_code == 404

    gone = api.delete(t["tok_a"], f"/workspaces/{t['ws_a']}/calls/{call.id}/recording")
    assert gone.status_code == 200 and gone.json()["status"] == "DELETED"
    assert media["bucket"].files == {} and ("DELETE", f"/call/{call.provider_call_id}") in media["vapi"]
    assert api.get(t["tok_a"], f"/workspaces/{t['ws_a']}/calls/{call.id}/recording").json()["message"] == \
        "Optagelsen er slettet"


def test_retention_deletes_after_the_numbers_days(client, api, two_workspaces, configured, storage, db, media):
    t = two_workspaces
    _turn_on(api, t, _setup(api, t), recording_retention_days=7)
    _post(client, _report())
    runner.drain()
    db.expire_all()
    rec = db.scalar(select(CallRecording))
    assert call_recordings.run_retention(db, now=datetime.now(UTC) + timedelta(days=6)) == 0
    assert call_recordings.run_retention(db, now=datetime.now(UTC) + timedelta(days=8)) == 1
    db.expire_all()
    assert db.get(CallRecording, rec.id).status == "DELETED" and media["bucket"].files == {}


def test_disclosure_placement():
    w = call_recordings.with_disclosure
    assert w("Hej, du har ringet til Fjord. Hvad kan jeg hjælpe med?", "da") == \
        "Hej, du har ringet til Fjord. Samtalen bliver også optaget. Hvad kan jeg hjælpe med?"
    assert w("Velkommen til Fjord", "da") == "Velkommen til Fjord. Samtalen bliver også optaget."
    assert w("Hej! Samtalen optages. Hvad vil du?", "da") == "Hej! Samtalen optages. Hvad vil du?"
    assert w("Hello, you've reached Fjord. How can I help?", "en") == \
        "Hello, you've reached Fjord. This call is also recorded. How can I help?"


def test_every_vapi_assistant_says_whether_it_records():
    """Vapi records unless told not to: every assistant config in the code sets artifactPlan."""
    import pathlib
    import re

    root = pathlib.Path(__file__).resolve().parents[1] / "app"
    missing = []
    for f in root.rglob("*.py"):
        src = f.read_text()
        for m in re.finditer(r'"firstMessage": ', src):
            window = src[max(0, m.start() - 600): m.start() + 600]
            if "artifactPlan" not in window and "base |" not in window and 'assistant["firstMessage"]' not in window \
                    and "out[\"assistant\"]" not in window and "cfg" not in window and "call[\"assistant\"]" not in window:
                missing.append(f"{f.relative_to(root)}:{src[:m.start()].count(chr(10)) + 1}")
    assert missing == []
