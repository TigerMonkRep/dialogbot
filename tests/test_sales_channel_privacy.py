"""Internal sales channel, phase 4: recordings, retention and data subject rights."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import httpx
import pytest
from sqlalchemy import select

from app.config import get_settings
from app.models import (
    Call,
    CallRecording,
    CampaignContact,
    ConversationMessage,
    SalesBlockList,
    SalesContact,
    SalesMediaAccessLog,
    User,
)
from app.modules.sales import privacy, recordings
from app.worker import runner
from tests.sales_fixtures import SECRET, TEST_NUMBER

MSGS = [{"role": "bot", "message": "Hej, det er Peter."}, {"role": "user", "message": "Hej, det er Bo."},
        {"role": "bot", "message": "Hvad sker der med opkaldene?"}, {"role": "user", "message": "Vi ringer tilbage."}]


class Bucket:
    def __init__(self):
        self.files: dict[str, bytes] = {}

    def put(self, key, data, content_type):
        self.files[key] = data

    def signed_url(self, key, seconds, download):
        return f"https://storage.invalid/{key}?expires={seconds}"

    def delete(self, key):
        self.files.pop(key, None)


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


def _record_on(monkeypatch):
    monkeypatch.setenv("SALES_RECORDING_STORAGE", "supabase")
    monkeypatch.setenv("SUPABASE_URL", "https://project.supabase.invalid")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "service-role-test")
    get_settings.cache_clear()


def _test_call(api, ring, record=False) -> dict:
    r = api.post(ring["op"], "/operator/salg/test-calls", {"company_id": str(ring["company"].id),
                                                           "script_id": str(ring["script"].id), "phone": TEST_NUMBER,
                                                           "accepted_test": True, "record": record})
    assert r.status_code == 201, r.text
    return r.json()


def _report(client, call_id, messages=MSGS):
    return client.post("/api/v1/webhooks/vapi", headers={"authorization": f"Bearer {SECRET}"}, json={"message": {
        "type": "end-of-call-report", "endedReason": "customer-ended-call", "durationSeconds": 95,
        "call": {"id": call_id, "phoneNumberId": "pn_sales", "type": "outboundPhoneCall",
                 "customer": {"number": TEST_NUMBER}}, "artifact": {"messages": messages}}}).json()


def _tool(client, call_id, name):
    return client.post("/api/v1/webhooks/vapi", headers={"authorization": f"Bearer {SECRET}"}, json={"message": {
        "type": "tool-calls", "call": {"id": call_id, "phoneNumberId": "pn_sales"},
        "toolCallList": [{"id": "t1", "function": {"name": name, "arguments": {}}}]}}).json()["results"][0]["result"]


def test_calls_are_not_recorded_unless_storage_and_campaign_say_so(api, ring, db, client, media):
    out = _test_call(api, ring, record=True)  # asked for, but SALES_RECORDING_STORAGE=none
    a = ring["calls"][0]["assistant"]
    assert a["artifactPlan"] == {"recordingEnabled": False}  # Vapi's default would be to record
    assert recordings.DISCLOSURE not in a["firstMessage"]
    assert "stop_optagelse" not in {t["function"]["name"] for t in a["model"]["tools"] if t["type"] == "function"}
    _report(client, out["provider_call_id"])
    runner.drain()
    call = db.scalar(select(Call).where(Call.provider_call_id == out["provider_call_id"]))
    assert call.recording_status == "NOT_RECORDED" and media["bucket"].files == {}
    assert api.get(ring["op"], f"/operator/salg/calls/{out['campaign_contact_id']}/audio").status_code == 409


def test_recording_is_disclosed_stored_privately_played_logged_and_retained(api, ring, db, client, media, monkeypatch):
    _record_on(monkeypatch)
    op = ring["op"]
    out = _test_call(api, ring, record=True)
    a = ring["calls"][0]["assistant"]
    assert a["artifactPlan"] == {"recordingEnabled": True} and recordings.DISCLOSURE in a["firstMessage"]
    _report(client, out["provider_call_id"])
    runner.drain()
    db.expire_all()
    call = db.scalar(select(Call).where(Call.provider_call_id == out["provider_call_id"]))
    rec = db.scalar(select(CallRecording).where(CallRecording.call_id == call.id))
    assert rec.status == "AVAILABLE" and call.recording_status == "AVAILABLE"
    assert rec.storage_key == f"sales/calls/{call.id}.wav" and media["bucket"].files[rec.storage_key] == b"RIFFfake-wav"
    assert ("GET", f"/call/{out['provider_call_id']}/mono-recording") in media["vapi"]
    r = api.get(op, f"/operator/salg/calls/{out['campaign_contact_id']}/audio")
    assert r.status_code == 200 and r.json()["expires_in"] <= 600
    assert api.get(op, f"/operator/salg/calls/{out['campaign_contact_id']}/audio?export=true").status_code == 403
    user = db.scalar(select(User).where(User.email_normalized == "operator@testmail.dk"))
    user.can_export_media = True
    db.commit()
    assert api.get(op, f"/operator/salg/calls/{out['campaign_contact_id']}/audio?export=true").status_code == 200
    assert [x.kind for x in db.scalars(select(SalesMediaAccessLog).order_by(SalesMediaAccessLog.at))] == ["play", "export"]
    detail = api.get(op, f"/operator/salg/calls/{out['campaign_contact_id']}").json()
    assert detail["recording"]["status"] == "AVAILABLE"
    # retention: audio after SALES_RETENTION_AUDIO_DAYS, transcript after SALES_RETENTION_TRANSCRIPT_DAYS
    rec.available_at = datetime.now(UTC) - timedelta(days=31)
    call.started_at = datetime.now(UTC) - timedelta(days=91)
    db.commit()
    done = privacy.run_retention(db)
    assert done["audio"] == 1 and done["transcripts"] == 1
    db.expire_all()
    assert db.get(CallRecording, rec.id).status == "DELETED" and media["bucket"].files == {}
    cc = db.get(CampaignContact, out["campaign_contact_id"])
    texts = db.scalars(select(ConversationMessage.text).where(ConversationMessage.conversation_id == cc.conversation_id)).all()
    assert texts and set(texts) == {"[slettet]"}
    assert ("DELETE", f"/call/{out['provider_call_id']}") in media["vapi"]
    detail = api.get(op, f"/operator/salg/calls/{out['campaign_contact_id']}").json()
    assert detail["call"]["transcript_status"] == "DELETED" and detail["recording"]["status"] == "DELETED"


def test_an_objection_to_recording_means_the_file_is_never_kept(api, ring, db, client, media, monkeypatch):
    _record_on(monkeypatch)
    out = _test_call(api, ring, record=True)
    assert "slettes" in _tool(client, out["provider_call_id"], "stop_optagelse")
    _report(client, out["provider_call_id"])
    runner.drain()
    call = db.scalar(select(Call).where(Call.provider_call_id == out["provider_call_id"]))
    rec = db.scalar(select(CallRecording).where(CallRecording.call_id == call.id))
    assert rec.status == "DELETED" and rec.delete_reason == "objection" and media["bucket"].files == {}
    assert ("DELETE", f"/call/{out['provider_call_id']}") in media["vapi"]
    assert not [p for m, p in media["vapi"] if p.endswith("/mono-recording")]


def test_access_erasure_and_objection(api, ring, db, client, media):
    op = ring["op"]
    out = _test_call(api, ring)
    _report(client, out["provider_call_id"])
    r = api.post(op, "/operator/salg/data-requests", {"subject": "phone", "value": "20 30 40 50", "kind": "access"})
    assert r.status_code == 201, r.text
    data = r.json()["result"]
    assert data["value"] == TEST_NUMBER and data["calls"] and data["calls"][0]["transcript"]
    assert any(c["phone"] == TEST_NUMBER for c in data["contacts"])
    bad = api.post(op, "/operator/salg/data-requests", {"subject": "phone", "value": TEST_NUMBER, "kind": "erasure"})
    assert bad.status_code == 422
    r = api.post(op, "/operator/salg/data-requests", {"subject": "phone", "value": TEST_NUMBER, "kind": "erasure",
                                                     "confirm": True})
    assert r.status_code == 201, r.text
    res = r.json()["result"]
    assert res["calls_anonymised"] == 1 and res["contacts_deleted"] >= 1 and res["blocked"] == [TEST_NUMBER]
    db.expire_all()
    assert db.scalar(select(SalesContact).where(SalesContact.phone_e164 == TEST_NUMBER)) is None
    assert db.scalar(select(SalesBlockList).where(SalesBlockList.value == TEST_NUMBER)) is not None
    cc = db.get(CampaignContact, out["campaign_contact_id"])
    assert set(db.scalars(select(ConversationMessage.text).where(ConversationMessage.conversation_id == cc.conversation_id))) == {"[slettet]"}
    r = api.post(op, "/operator/salg/data-requests", {"subject": "cvr", "value": "12345678", "kind": "objection"})
    assert r.status_code == 201 and r.json()["result"]["blocked"] == ["12345678"]
    assert len(api.get(op, "/operator/salg/data-requests").json()["items"]) == 3
    plain = api.user("udenfor@testmail.dk")
    assert api.post(plain, "/operator/salg/data-requests", {"subject": "cvr", "value": "12345678",
                                                            "kind": "objection"}).status_code == 403
