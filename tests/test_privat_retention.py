"""Dialogbot Privat – GDPR decisions of 2026-11-11 (Fürster): chats and call summaries are kept while the account exists
and can be deleted one by one; raw transcripts go after 90 days (ours and Vapi's copy); account deletion keeps a
business login and membership, revokes Google/Microsoft calendar access best effort; the export link works 7 days."""
from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import httpx

from app.models import (
    IntegrationConnection,
    Membership,
    PrivateCall,
    PrivateDataExport,
    PrivateMessage,
    PrivateTask,
    WebhookEvent,
)
from app.modules.integrations import credentials
from app.modules.privat import gdpr
from app.modules.sales import recordings
from app.worker import runner
from tests.test_privat import _propose
from tests.test_privat_gdpr import _export, _stripe


def _call_row(db, pv, tok, *, status="answered", ended_days_ago=100, vapi_id="vc_old", excerpt="Ja tak, send en mail"):
    """A finished call: a proposal via the chat, then set as if it was dialled and answered `ended_days_ago` ago."""
    pv.verify_phone(tok)
    tid = _propose(pv, tok)
    c = db.query(PrivateCall).filter_by(task_id=uuid.UUID(tid)).one()
    ended = pv.clock() - timedelta(days=ended_days_ago)
    c.status, c.result, c.vapi_call_id, c.pitch_transcript_excerpt = status, status, vapi_id, excerpt
    c.dialled_at, c.ended_at, c.business_reply = ended, ended, "Værkstedet kan tage cyklen torsdag kl. 15.30."
    db.query(PrivateTask).filter_by(id=uuid.UUID(tid)).one().status = "done"
    db.commit()
    return tid, c.id


# --------------------------------------------------------------------------- chats and summaries: kept, deletable one by one

def test_one_chat_message_can_be_deleted_and_only_ones_own(api, pv, db):
    mette = pv.account("mette@testmail.dk", "Mette Hansen")
    ole = pv.account("ole@testmail.dk", "Ole Berg")
    pv.say(mette, "Husk at købe mælk i morgen")
    msgs = api.get(mette, "/privat/messages").json()
    mine = next(m for m in msgs if m["role"] == "user")
    assert api.delete(ole, f"/privat/messages/{mine['id']}").status_code == 404  # someone else's: not found
    assert api.delete(mette, f"/privat/messages/{mine['id']}").status_code == 204
    after = api.get(mette, "/privat/messages").json()
    assert mine["id"] not in {m["id"] for m in after} and len(after) == len(msgs) - 1  # the rest is kept
    assert api.delete(mette, f"/privat/messages/{mine['id']}").status_code == 404


def test_messages_and_summaries_are_kept_without_time_limit(api, pv, db):
    """No retention job removes chats or call summaries – only the user (or deleting the account) does."""
    mette = pv.account("mette@testmail.dk", "Mette Hansen")
    tid, cid = _call_row(db, pv, mette, ended_days_ago=800)
    n = db.query(PrivateMessage).filter_by(workspace_id=pv.ws(mette)).count()
    gdpr.purge_transcripts(db)
    db.expire_all()
    c = db.get(PrivateCall, cid)
    assert c.business_reply == "Værkstedet kan tage cyklen torsdag kl. 15.30."
    assert db.query(PrivateMessage).filter_by(workspace_id=pv.ws(mette)).count() == n


def test_one_call_with_its_summary_can_be_deleted(api, pv, db, monkeypatch):
    deleted = []
    monkeypatch.setattr(recordings, "delete_at_vapi", lambda vid: deleted.append(vid) or True)
    mette = pv.account("mette@testmail.dk", "Mette Hansen")
    ole = pv.account("ole@testmail.dk", "Ole Berg")
    tid, cid = _call_row(db, pv, mette, ended_days_ago=1, vapi_id="vc_1")
    other_tid = pv.make_list(mette)
    assert api.delete(ole, f"/privat/calls/{tid}").status_code == 404
    assert api.delete(mette, f"/privat/calls/{other_tid}").status_code == 404  # not a call
    assert api.delete(mette, f"/privat/calls/{tid}").status_code == 204
    db.expire_all()
    assert db.get(PrivateCall, cid) is None and db.get(PrivateTask, uuid.UUID(tid)) is None
    assert db.query(PrivateMessage).filter(PrivateMessage.task_id == uuid.UUID(tid)).count() == 0
    assert deleted == ["vc_1"]  # Vapi's copy too
    assert pv.task(mette, other_tid).status_code == 200  # nothing else goes


def test_a_running_call_cannot_be_deleted(api, pv, db):
    mette = pv.account("mette@testmail.dk", "Mette Hansen")
    tid, cid = _call_row(db, pv, mette, ended_days_ago=0)
    c = db.get(PrivateCall, cid)
    c.status, c.result = "dialling", None
    db.commit()
    r = api.delete(mette, f"/privat/calls/{tid}")
    assert r.status_code == 409 and r.json()["code"] == "call_running"
    db.expire_all()
    assert db.get(PrivateCall, cid) is not None


# --------------------------------------------------------------------------- raw transcripts after 90 days

def test_raw_transcripts_are_deleted_after_90_days(api, pv, db, monkeypatch):
    monkeypatch.setattr(gdpr.get_settings(), "vapi_api_key", "vk_test", raising=False)
    deleted = []
    monkeypatch.setattr(recordings, "delete_at_vapi", lambda vid: deleted.append(vid) or vid != "vc_down")
    mette = pv.account("mette@testmail.dk", "Mette Hansen")
    _t1, old = _call_row(db, pv, mette, ended_days_ago=91, vapi_id="vc_old")
    _t2, new = _call_row(db, pv, mette, ended_days_ago=89, vapi_id="vc_new")
    _t3, down = _call_row(db, pv, mette, ended_days_ago=120, vapi_id="vc_down")
    # a business calling back (no private_calls id of its own): known only from its webhook row
    db.add(WebhookEvent(provider="vapi", event_id="vc_cb:end-of-call-report", event_type="end-of-call-report",
                        payload={"call_id": "vc_cb", "type": "end-of-call-report", "privat": True}, outcome="applied",
                        received_at=pv.clock() - timedelta(days=95)))
    # a business customer's call: never touched by Privat's retention
    db.add(WebhookEvent(provider="vapi", event_id="vc_biz:end-of-call-report", event_type="end-of-call-report",
                        payload={"call_id": "vc_biz", "type": "end-of-call-report"}, outcome="applied",
                        received_at=pv.clock() - timedelta(days=200)))
    db.commit()
    out = gdpr.purge_transcripts(db)
    db.expire_all()
    assert sorted(deleted) == ["vc_cb", "vc_down", "vc_old"]
    o, n, d = db.get(PrivateCall, old), db.get(PrivateCall, new), db.get(PrivateCall, down)
    assert (o.pitch_transcript_excerpt, o.vapi_call_id) == (None, None)
    assert o.business_reply  # the summary stays
    assert (n.pitch_transcript_excerpt, n.vapi_call_id) == ("Ja tak, send en mail", "vc_new")  # 89 days: kept
    assert d.pitch_transcript_excerpt is None and d.vapi_call_id == "vc_down"  # Vapi failed: tried again tomorrow
    cb = db.query(WebhookEvent).filter_by(event_id="vc_cb:end-of-call-report").one()
    assert cb.payload["transcript_deleted"] is True
    assert "transcript_deleted" not in db.query(WebhookEvent).filter_by(event_id="vc_biz:end-of-call-report").one().payload
    assert out == {"excerpts": 2, "provider": 2, "provider_failed": 1}
    deleted.clear()
    gdpr.purge_transcripts(db)  # the next day: only what failed is asked again
    assert deleted == ["vc_down"]


def test_the_worker_runs_the_transcript_purge(api, pv, db, monkeypatch):
    ran = []
    monkeypatch.setattr(gdpr, "purge_transcripts", lambda d, now=None: ran.append(1) or {})
    runner._RETENTION_RAN.pop("privat_transcripts", None)
    runner.run_schedules()
    runner.run_schedules()
    assert ran == [1]  # once a day


# --------------------------------------------------------------------------- account deletion

def _calendar(db, ws, connector, token="rt-1", simulated=False):
    conn = IntegrationConnection(workspace_id=ws, connector=connector, auth_kind="oauth", status="connected",
                                 simulated=simulated, expires_at=datetime.now(UTC) + timedelta(hours=1))
    credentials.put_secret(conn, {"access_token": "at", "refresh_token": token})
    db.add(conn)
    db.commit()


def test_deleting_the_account_revokes_calendar_access_best_effort(api, pv, db, monkeypatch):
    posts = []

    def fake_post(url, params=None, **k):
        posts.append((url, (params or {}).get("token")))
        return httpx.Response(200)

    monkeypatch.setattr(httpx, "post", fake_post)
    mette = pv.account("mette@testmail.dk", "Mette Hansen")
    ws = pv.ws(mette)
    _calendar(db, ws, "google_calendar", "rt-google")
    _calendar(db, ws, "microsoft_calendar", "rt-ms")
    _stripe(monkeypatch)
    assert api.post(mette, "/privat/account/delete", {"confirm_email": "mette@testmail.dk"}).status_code == 200
    assert posts == [("https://oauth2.googleapis.com/revoke", "rt-google")]  # Microsoft has no revocation endpoint
    from app.models import AuditLog

    a = db.query(AuditLog).filter_by(action="privat.account_deleted").one()
    assert a.after["calendar_revoke"] == {"google": "revoked", "microsoft": "unsupported"}
    assert db.query(IntegrationConnection).filter_by(workspace_id=ws).count() == 0  # tokens gone with the workspace


def test_a_provider_failure_never_blocks_the_deletion(api, pv, db, monkeypatch):
    def down(*a, **k):
        raise httpx.ConnectError("no network")

    monkeypatch.setattr(httpx, "post", down)
    mette = pv.account("mette@testmail.dk", "Mette Hansen")
    ws = pv.ws(mette)
    _calendar(db, ws, "google_calendar")
    _stripe(monkeypatch)
    r = api.post(mette, "/privat/account/delete", {"confirm_email": "mette@testmail.dk"})
    assert r.status_code == 200 and r.json()["deleted"] is True
    from app.models import AuditLog

    assert db.query(AuditLog).filter_by(action="privat.account_deleted").one().after["calendar_revoke"] == {"google": "failed"}


def test_business_member_keeps_login_membership_and_business_calendar(api, pv, db, monkeypatch):
    """Also an Erhverv member: only Privat data goes. The login, the membership and the BUSINESS workspace's own Google
    connection stay (its token is not revoked)."""
    posts = []
    monkeypatch.setattr(httpx, "post", lambda url, params=None, **k: posts.append((params or {}).get("token")) or httpx.Response(200))
    mette = pv.account("mette@testmail.dk", "Mette Hansen")
    biz = uuid.UUID(api.workspace(mette, "Mettes Frisør ApS"))
    ws, uid = pv.ws(mette), pv.uid(mette)
    _calendar(db, biz, "google_calendar", "rt-business")
    _calendar(db, ws, "google_calendar", "rt-privat")
    pv.say(mette, "Husk at købe mælk i morgen")
    _stripe(monkeypatch)
    r = api.post(mette, "/privat/account/delete", {"confirm_email": "mette@testmail.dk"})
    assert r.status_code == 200 and r.json()["login_kept"] is True
    assert posts == ["rt-privat"]
    db.expire_all()
    assert db.query(Membership).filter_by(user_id=uid, workspace_id=biz).count() == 1
    assert db.query(IntegrationConnection).filter_by(workspace_id=biz).count() == 1
    assert db.query(PrivateMessage).filter_by(workspace_id=ws).count() == 0
    tok = api.login("mette@testmail.dk")
    assert api.get(tok, f"/workspaces/{biz}").status_code == 200
    assert api.get(tok, "/privat/me").status_code == 404


# --------------------------------------------------------------------------- export link: 7 days

def test_export_link_works_for_seven_days(api, pv, db):
    from tests.privat_fixtures import WED_10

    mette = pv.account("mette@testmail.dk", "Mette Hansen")
    raw = _export(api, mette, "mette@testmail.dk")["raw"]
    row = db.query(PrivateDataExport).one()
    assert row.expires_at - row.ready_at == timedelta(days=7)
    pv.clock.at = WED_10 + timedelta(days=6, hours=23)
    assert api.get(mette, f"/privat/data-export/download?token={raw}").status_code == 200
    pv.clock.at = WED_10 + timedelta(days=7, minutes=1)
    assert api.get(mette, f"/privat/data-export/download?token={raw}").status_code == 404
