"""QA S07 (security-privacy, bølge 2 / M2): retention, dataeksport, sletning, lukning af konto/arbejdsrum.

Krav S07: "Retention controls, data export/request status, deletion and account/workspace closure journey."
DB-015: "Privacy policy, exports, closure and suppression need actual scoped behavior. Acceptance: Authorized exports
with configurable expiry; closure obligations explicit; callback cancellation not global opt-out; legal content stays
draft until approved."

Hvad der findes: kundens optagelser (slet + retention pr. nummer), Egen stemme (træk samtykke tilbage), salgskanalens
egne retention/indsigt/sletning (operatør). Hvad der ikke findes: kundens dataeksport, lukning/sletning af arbejdsrum
eller konto, retention af udskrifter/resuméer for kundens egne samtaler.

Kør: TEST_DATABASE_URL=…/qa_p1misc pytest -p no:cacheprovider tests/qa/test_qa_S07.py
"""
from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from sqlalchemy import select

from app.config import get_settings
from app.core.errors import ApiError
from app.models import Call, CallRecording, ConversationMessage, Workspace
from app.modules.telephony import call_recordings
from app.worker import runner
from tests.test_call_recordings import _assistant, _turn_on, configured, media, storage  # noqa: F401
from tests.test_telephony import _post, _report, _setup
from tests.test_webchat import fake  # noqa: F401  (AI provider fake for the widget)

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# --------------------------------------------------------------------------- the journey itself

@pytest.mark.xfail(strict=True, reason="F-M2-01-S07: S2 new – S07 er ikke bygget: ingen privatlivsside, ingen dataeksport, ingen lukning/sletning af arbejdsrum eller …")
def test_privacy_center_export_and_closure_exist(api, two_workspaces):
    """S07-ruten /app/settings/privacy og en selvbetjent eksport/lukning. /gdpr og /vilkår lover: «Ved opsigelse kan I
    inden for 30 dage bede om en kopi af jeres data. Derefter sletter vi dem» – intet i koden kan lave kopien eller
    slette et arbejdsrum (workspaces.status 'closing'/'closed' sættes ingen steder)."""
    t = two_workspaces
    web = os.path.join(ROOT, "web", "src", "app", "app")
    pages = [d for d, _s, f in os.walk(web) if "page.tsx" in f and any(x in d.lower() for x in ("privacy", "privatliv", "data"))]
    api_tries = {
        "GET export": api.get(t["tok_a"], f"/workspaces/{t['ws_a']}/export").status_code,
        "POST export": api.post(t["tok_a"], f"/workspaces/{t['ws_a']}/export").status_code,
        "POST data-requests": api.post(t["tok_a"], f"/workspaces/{t['ws_a']}/data-requests", {"kind": "export"}).status_code,
        "POST close": api.post(t["tok_a"], f"/workspaces/{t['ws_a']}/close").status_code,
        "DELETE workspace": api.delete(t["tok_a"], f"/workspaces/{t['ws_a']}").status_code,
        "DELETE /auth/me": api.delete(t["tok_a"], "/auth/me").status_code,
    }
    import subprocess

    setters = subprocess.run(["grep", "-rnE", r"status\s*=\s*\"(closing|closed)\"|\.status = \"clos", os.path.join(ROOT, "app")],
                             capture_output=True, text=True).stdout
    assert pages and any(s < 400 for s in api_tries.values()) and setters, (
        f"ingen privatlivs-side ({pages}), ingen eksport/lukning i API ({api_tries}), "
        f"intet sætter workspaces.status=closing/closed ({setters!r})")


@pytest.mark.xfail(strict=True, reason="F-M2-02-S07: S2 new – Et lukket arbejdsrum (status='closed') bliver ved med at besvare telefonen og webchat-widgetten og gemme …")
def test_a_closed_workspace_stops_answering_on_phone_and_widget(api, client, two_workspaces, configured, fake, db):  # noqa: F811
    """Hvis et arbejdsrum lukkes (i dag kun muligt direkte i databasen), afviser app-sessioner og public API det
    (core/auth.py:172, public_api/auth.py:71) – men telefonen og webchat-widgetten bliver ved med at svare og gemme
    nye persondata for virksomheden."""
    from tests.test_webchat import SITE, _approve, _enable

    t = two_workspaces
    _setup(api, t)
    _approve(api, t["tok_a"], t["ws_a"], "Slibning")
    en = _enable(api, t["tok_a"], t["ws_a"], origins=[SITE])
    assert en.status_code == 200, en.text
    key = en.json()["widget_key"]
    from tests.test_webchat import _start

    assert _start(client, key).status_code == 201  # works while active
    ws = db.get(Workspace, uuid.UUID(t["ws_a"]))
    ws.status = "closed"
    db.commit()
    assert api.get(t["tok_a"], f"/workspaces/{t['ws_a']}").status_code in (403, 404)  # the app already refuses
    widget = _start(client, key)
    a = _post(client, {"type": "assistant-request", "call": {"id": "closed-1", "phoneNumberId": "pn_123"}}).json()
    first = (a.get("assistant") or {}).get("firstMessage", "")
    assert widget.status_code >= 400 and "Fjord" not in first, (
        f"lukket arbejdsrum: widget {widget.status_code}, telefonen svarer stadig «{first[:60]}»")


# --------------------------------------------------------------------------- deletion really deletes (recordings)

def test_customer_deleted_recording_is_gone_everywhere(api, client, two_workspaces, configured, storage, db, media):  # noqa: F811
    t = two_workspaces
    n = _setup(api, t)
    assert _turn_on(api, t, n, recording_retention_days=30).status_code == 200
    rep = _report("del-1")
    rep["artifact"]["recordingUrl"] = "https://storage.vapi.ai/del-1.wav"
    _post(client, rep)
    runner.drain()
    db.expire_all()
    call = db.scalar(select(Call))
    rec = db.scalar(select(CallRecording))
    assert rec.status == "AVAILABLE" and media["bucket"].files
    # reader/staff may not delete; the other tenant gets 404
    reader = api.add_member(t["tok_a"], t["ws_a"], "reader-s07@testmail.dk", "reader")
    assert api.delete(reader, f"/workspaces/{t['ws_a']}/calls/{call.id}/recording").status_code in (403, 404)
    assert api.delete(t["tok_b"], f"/workspaces/{t['ws_b']}/calls/{call.id}/recording").status_code == 404
    assert api.delete(t["tok_a"], f"/workspaces/{t['ws_a']}/calls/{call.id}/recording").status_code == 200
    db.expire_all()
    call = db.get(Call, call.id)
    assert media["bucket"].files == {} and call.recording_url is None and call.recording_status == "DELETED"
    assert ("DELETE", f"/call/{call.provider_call_id}") in media["vapi"]  # Vapi's copy too
    detail = api.get(t["tok_a"], f"/workspaces/{t['ws_a']}/conversations/{call.conversation_id}").text
    assert "storage.vapi.ai" not in detail and "calls/" not in detail
    # double delete is an honest 409, not a 500
    assert api.delete(t["tok_a"], f"/workspaces/{t['ws_a']}/calls/{call.id}/recording").status_code == 409


@pytest.mark.xfail(strict=True, reason="F-M2-03-S07: S2 new – Retention af kundeoptagelser er alt-eller-intet: fejler sletning af én fil i lageret, ruller hele kørslen …")
def test_retention_is_not_blocked_by_one_recording_that_fails_to_delete(api, client, two_workspaces, configured, storage,  # noqa: F811
                                                                       db, media):  # noqa: F811
    """Retention kører i én transaktion over alle kunders optagelser (call_recordings.run_retention). Fejler sletning af
    ÉN fil i lageret, ruller hele kørslen tilbage, ingen optagelse slettes, og workeren prøver igen ved hver
    løkke (runner.py:379 sætter først _RETENTION_RAN efter succes) – én defekt fil blokerer retention for alle."""
    t = two_workspaces
    n = _setup(api, t)
    _turn_on(api, t, n, recording_retention_days=7)
    _post(client, _report("ret-a"))
    _post(client, _report("ret-b"))
    runner.drain()
    db.expire_all()
    recs = db.scalars(select(CallRecording).order_by(CallRecording.created_at)).all()
    assert len(recs) == 2 and all(r.status == "AVAILABLE" for r in recs)
    bad = recs[0].storage_key
    bucket = media["bucket"]
    real_delete = bucket.delete

    def flaky(key):
        if key == bad:
            raise ApiError("Sletning af lyd fejlede (500)", code="recording_storage_failed")
        real_delete(key)

    bucket.delete = flaky
    try:
        call_recordings.run_retention(db, now=datetime.now(UTC) + timedelta(days=8))
    except ApiError:
        db.rollback()
    db.expire_all()
    left = {r.storage_key: r.status for r in db.scalars(select(CallRecording))}
    assert left[recs[1].storage_key] == "DELETED", f"én fejlende fil blokerede retention for de andre: {left}"


@pytest.mark.xfail(strict=True, reason="F-M2-04-S07: S2 new – Udskrift og resumé af kundens egne opkald har ingen frist og ingen sletning – heller ikke når lyden …")
def test_transcript_and_summary_have_a_retention(api, client, two_workspaces, configured, storage, db, media):  # noqa: F811
    """Retention gælder kun lyd. Udskrift (conversation_messages) og resumé (calls.summary) for kundens egne opkald
    har ingen frist og ingen sletteknap – heller ikke når lyden slettes efter nummerets frist. Kravets
    «retention controls» og /gdpr's liste («En udskrift af samtalen … Den opsummering …») har ingen slettevej."""
    t = two_workspaces
    _turn_on(api, t, _setup(api, t), recording_retention_days=7)
    _post(client, _report("tr-1"))
    runner.drain()
    call_recordings.run_retention(db, now=datetime.now(UTC) + timedelta(days=400))
    db.expire_all()
    call = db.scalar(select(Call))
    lines = [m.text for m in db.scalars(select(ConversationMessage).where(ConversationMessage.conversation_id == call.conversation_id))]
    assert call.recording_status == "DELETED"
    assert not any("afslibning" in (x or "").lower() for x in lines) or not call.summary, (
        f"400 dage efter: lyd slettet, men udskrift ({len(lines)} linjer) og resumé «{call.summary[:40]}» består")


# --------------------------------------------------------------------------- Egen stemme: withdrawal

@pytest.mark.xfail(strict=True, reason="F-M2-05-S07: S2 new – Egen stemme: «Træk samtykke tilbage» sletter optagelserne, men syntetiseret tale i personens stemme bliver …")
def test_own_voice_withdrawal_also_deletes_cached_synthesis_in_cloud_storage(monkeypatch):
    """«Samtykket er trukket tilbage. Optagelserne er slettet, og stemmen bruges ikke.» Ved tilbagetrækning kalder
    own_voice.withdraw service.invalidate_cache → storage.delete_prefix('cache/ws/<ws>/<profil>'). Med Supabase
    (produktion) returnerer delete_prefix bare 0 (voices/storage.py:127) – syntetiseret tale i personens stemme
    bliver liggende i bucketten."""
    from app.modules.voices import storage as vstorage

    monkeypatch.setenv("VOICE_STORAGE", "supabase")
    monkeypatch.setenv("SUPABASE_URL", "https://project.supabase.invalid")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "service-role-test")
    get_settings.cache_clear()
    calls = []

    def fake_request(method, url, **kw):
        calls.append((method, str(url), kw.get("json")))
        if method == "POST" and "/list/" in str(url):
            return httpx.Response(200, json=[{"name": "abc.wav"}])
        return httpx.Response(200, json=[])

    monkeypatch.setattr(httpx, "request", fake_request)
    monkeypatch.setattr(httpx, "post", lambda url, **kw: fake_request("POST", url, **kw))
    try:
        prefix = f"cache/ws/{uuid.uuid4()}/{uuid.uuid4()}"
        n = vstorage.delete_prefix(prefix)
    finally:
        get_settings.cache_clear()
    assert get_settings is not None
    assert calls and n >= 0, f"delete_prefix lavede ingen kald mod lageret (returnerede {n}) – cachen slettes ikke"
