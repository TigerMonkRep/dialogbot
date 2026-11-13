"""H01/M06 decisions (Fürster 13/11): billing tickets only for admin and owner; a new ticket is announced to Dialogbot's
support inbox with number, subject and workspace only; support files go with their rows (a deleted ticket or a deleted
workspace) – the database queues the storage keys, the worker removes the objects. Role matrix and tenant isolation."""
from __future__ import annotations

import os

import pytest
from alembic.config import Config
from sqlalchemy import select, text

from alembic import command
from app.config import get_settings
from app.models import OutboxEvent, StorageDeletion, SupportAttachment, SupportTicket
from app.modules.support.attachments import sweep_deletions
from app.worker import runner

PDF = b"%PDF-1.4\n%test\n"


@pytest.fixture(autouse=True)
def _storage(tmp_path, monkeypatch):
    monkeypatch.setenv("VOICE_STORAGE_DIR", str(tmp_path / "store"))
    get_settings.cache_clear()
    yield tmp_path / "store"
    get_settings.cache_clear()


def _create(api, tok, ws, category="billing", subject="Fakturaen for oktober er forkert", files=None):
    return api.c.post(f"/api/v1/workspaces/{ws}/support/tickets",
                      data={"subject": subject, "body": "Hans Hansen, hans@kunde.dk, ring 20304050", "category": category},
                      files=files or None, headers=api.h(tok))


def test_billing_tickets_only_for_admin_and_owner(api, two_workspaces):
    t = two_workspaces
    ws = t["ws_a"]
    admin = api.add_member(t["tok_a"], ws, "admin-a@testmail.dk", "admin")
    staff = api.add_member(t["tok_a"], ws, "staff-a@testmail.dk", "staff")
    reader = api.add_member(t["tok_a"], ws, "reader-a@testmail.dk", "reader")
    owner_t = _create(api, t["tok_a"], ws, files=[("files", ("faktura.pdf", PDF, "application/pdf"))])
    assert owner_t.status_code == 201, owner_t.text
    att = owner_t.json()["messages"][0]["attachments"][0]["id"]
    assert _create(api, admin, ws).status_code == 201  # #2, billing, by an admin
    assert _create(api, staff, ws, category="calendar", subject="Kalenderen fejler").status_code == 201  # #3
    # staff cannot open a billing ticket (they could not see it afterwards) and do not see the existing ones
    r = _create(api, staff, ws)
    assert r.status_code == 403 and r.json()["code"] == "insufficient_role"
    lst = api.get(staff, f"/workspaces/{ws}/support/tickets").json()
    assert [i["number"] for i in lst["items"]] == [3] and "billing" not in lst["categories"]
    for n in (1, 2):
        assert api.get(staff, f"/workspaces/{ws}/support/tickets/{n}").status_code == 404
        assert api.c.post(f"/api/v1/workspaces/{ws}/support/tickets/{n}/messages", data={"body": "hej"},
                          headers=api.h(staff)).status_code == 404
        assert api.post(staff, f"/workspaces/{ws}/support/tickets/{n}/resolve").status_code == 404
    assert api.get(staff, f"/workspaces/{ws}/support/tickets/1/attachments/{att}").status_code == 404
    # a reader sees no tickets at all (as before)
    assert api.get(reader, f"/workspaces/{ws}/support/tickets").status_code == 403
    # admin and owner see all three, billing included
    for tok in (admin, t["tok_a"]):
        lst = api.get(tok, f"/workspaces/{ws}/support/tickets").json()
        assert sorted(i["number"] for i in lst["items"]) == [1, 2, 3] and "billing" in lst["categories"]
        assert api.get(tok, f"/workspaces/{ws}/support/tickets/1").status_code == 200
    assert api.get(admin, f"/workspaces/{ws}/support/tickets/1/attachments/{att}").content == PDF
    # tenant isolation: B's owner reaches nothing of A's
    assert api.get(t["tok_b"], f"/workspaces/{ws}/support/tickets/1").status_code == 404


def test_operator_moving_a_ticket_to_billing_hides_it_from_staff(api, two_workspaces, db):
    t = two_workspaces
    ws = t["ws_a"]
    staff = api.add_member(t["tok_a"], ws, "staff-a@testmail.dk", "staff")
    assert _create(api, staff, ws, category="other", subject="Spørgsmål").status_code == 201
    db.execute(text("update support_tickets set category = 'billing'"))
    db.commit()
    assert api.get(staff, f"/workspaces/{ws}/support/tickets").json()["items"] == []
    assert api.get(staff, f"/workspaces/{ws}/support/tickets/1").status_code == 404
    # the reply mail would link to a page the staff member cannot open: it is not sent
    from app.modules.support import service as svc

    tk = db.scalar(select(SupportTicket))
    assert svc.notify_customer(db, tk, tk.id) is False


def test_a_new_ticket_is_announced_to_the_support_inbox_without_personal_data(api, two_workspaces, db):
    t = two_workspaces
    r = _create(api, t["tok_a"], t["ws_a"], category="calendar", subject="Kalenderen viser ikke aftaler")
    assert r.status_code == 201
    ev = db.scalar(select(OutboxEvent).where(OutboxEvent.dedupe_key.startswith("support-new:")))
    assert ev is not None and ev.payload["to_email"] == "info@dialogbot.dk"
    mail = ev.payload["email"]
    import json

    raw = json.dumps(mail, ensure_ascii=False)
    assert "#1" in mail["subject"] and "Kalenderen viser ikke aftaler" in raw
    ws_name = api.get(t["tok_a"], f"/workspaces/{t['ws_a']}").json()["name"]
    assert ws_name in raw
    me = api.get(t["tok_a"], "/auth/me").json()
    for private in (me["email"], me["display_name"], "Hans Hansen", "hans@kunde.dk", "20304050"):
        assert private not in raw, private  # no creator, no description
    runner.drain()
    from app.models import EmailDelivery

    d = db.scalar(select(EmailDelivery).where(EmailDelivery.outbox_event_id == ev.id))
    assert d is not None and d.to_email == "info@dialogbot.dk" and "Ny supportsag #1" in d.subject
    assert me["email"] not in d.body_text and "hans@kunde.dk" not in d.body_text
    # one mail per ticket: a reply does not announce again
    api.c.post(f"/api/v1/workspaces/{t['ws_a']}/support/tickets/1/messages", data={"body": "Tilføjelse"},
               headers=api.h(t["tok_a"]))
    assert db.query(OutboxEvent).filter(OutboxEvent.dedupe_key.startswith("support-new:")).count() == 1


def _files(root):
    return sorted(p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()) if root.exists() else []


def test_support_files_are_deleted_with_their_ticket_and_with_the_workspace(api, two_workspaces, db, _storage):
    t = two_workspaces
    for tok, ws in ((t["tok_a"], t["ws_a"]), (t["tok_a"], t["ws_a"]), (t["tok_b"], t["ws_b"])):
        assert _create(api, tok, ws, category="other", files=[("files", ("x.pdf", PDF, "application/pdf"))]).status_code == 201
    keys = {a.storage_key for a in db.scalars(select(SupportAttachment))}
    assert len(_files(_storage)) == 3 and all(k.startswith("ws/") and "/support/" in k for k in keys)
    # a ticket deleted: its file goes, nothing else
    db.execute(text("delete from support_tickets where workspace_id = :w and number = 1"), {"w": t["ws_a"]})
    db.commit()
    assert sweep_deletions(db) == 1
    assert len(_files(_storage)) == 2
    # a workspace deleted (the delete cascades to tickets, messages, attachments): all of its support files go
    db.execute(text("delete from workspaces where id = :w"), {"w": t["ws_a"]})
    db.commit()
    assert sweep_deletions(db) == 1
    left = _files(_storage)
    assert len(left) == 1 and left[0].startswith(f"ws/{t['ws_b']}/support/")  # B's file is untouched
    assert all(r.done_at is not None for r in db.scalars(select(StorageDeletion)))
    assert sweep_deletions(db) == 0  # nothing pending twice


def test_a_failed_file_deletion_is_retried(db, monkeypatch):
    from app.modules.voices import storage

    db.add(StorageDeletion(storage_key="ws/00000000-0000-0000-0000-000000000000/support/t/a.pdf", reason="support_attachment"))
    db.commit()

    def boom(keys):
        raise RuntimeError("storage down")

    monkeypatch.setattr(storage, "delete", boom)
    assert sweep_deletions(db) == 0
    row = db.scalar(select(StorageDeletion))
    assert row.done_at is None and row.attempts == 1 and "storage down" in row.last_error
    monkeypatch.undo()
    assert sweep_deletions(db) == 1


def test_migration_down_and_up(db):
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    cfg = Config(os.path.join(root, "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(root, "alembic"))
    db.close()
    command.downgrade(cfg, "c5e1f7a3d9b2")
    try:
        with db.bind.connect() as conn:
            for tbl in ("sms_usage", "storage_deletions"):
                assert conn.execute(text(f"select to_regclass('{tbl}')")).scalar() is None
            assert conn.execute(text("select count(*) from pg_trigger where tgname = 'trg_support_attachments_deleted'")).scalar() == 0
    finally:
        command.upgrade(cfg, "head")
    with db.bind.connect() as conn:
        assert conn.execute(text("select to_regclass('storage_deletions')")).scalar() == "storage_deletions"
        assert conn.execute(text("select count(*) from pg_trigger where tgname = 'trg_support_attachments_deleted'")).scalar() == 1
