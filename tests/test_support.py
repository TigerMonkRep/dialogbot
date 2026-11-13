"""H01 (customer support at /app/support/<number>) and M06 (operator support queue): tickets with attachments, status
and thread; queue, assignment, client-visible replies and internal notes (DB-016); role matrix and tenant isolation."""
from __future__ import annotations

import os

import pytest
from alembic.config import Config
from sqlalchemy import select, text

from alembic import command
from app.config import get_settings
from app.models import AuditLog, OutboxEvent, SupportAttachment, SupportMessage, SupportTicket
from app.worker import runner

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
PDF = b"%PDF-1.4\n%test\n"
LOG = "2026-11-13 09:15 kalender: invalid_grant – token udløbet\n".encode()
SECRET = "INTERN-M06: kunden roterede selv nøglen, ingen kompensation"


@pytest.fixture(autouse=True)
def _storage(tmp_path, monkeypatch):
    monkeypatch.setenv("VOICE_STORAGE_DIR", str(tmp_path / "store"))
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _create(api, tok, ws, subject="Kalenderen viser ikke aftaler", body="Bookinger fejler siden i går.",
            category="calendar", files=None, context=None):
    data = {"subject": subject, "body": body, "category": category}
    if context is not None:
        data["context"] = context
    return api.c.post(f"/api/v1/workspaces/{ws}/support/tickets", data=data, files=files or None, headers=api.h(tok))


def _reply(api, tok, ws, number, body, files=None):
    return api.c.post(f"/api/v1/workspaces/{ws}/support/tickets/{number}/messages", data={"body": body},
                      files=files or None, headers=api.h(tok))


def test_customer_opens_a_ticket_with_attachments_and_follows_it(api, two_workspaces):
    t = two_workspaces
    r = _create(api, t["tok_a"], t["ws_a"], context="/app/indstillinger?ark=integrationer",
                files=[("files", ("skærmbillede.png", PNG, "image/png")), ("files", ("../../etc/log.log", LOG, "text/plain"))])
    assert r.status_code == 201, r.text
    d = r.json()
    assert d["number"] == 1 and d["status"] == "open" and d["category"] == "calendar"
    assert [a["filename"] for a in d["messages"][0]["attachments"]] == ["skærmbillede.png", "log.log"]
    assert [a["content_type"] for a in d["messages"][0]["attachments"]] == ["image/png", "text/plain"]
    assert "priority" not in d and "assigned_to" not in d  # operator triage fields stay internal
    # numbering is per workspace: B's first ticket is also #1, and A's next is #2
    assert _create(api, t["tok_b"], t["ws_b"], category="billing").json()["number"] == 1
    assert _create(api, t["tok_a"], t["ws_a"], subject="Andet spørgsmål", category="other").json()["number"] == 2
    lst = api.get(t["tok_a"], f"/workspaces/{t['ws_a']}/support/tickets").json()
    assert [i["number"] for i in lst["items"]] == [2, 1] and lst["open"] == 2
    # download: the stored bytes, always as a download
    att = d["messages"][0]["attachments"][0]
    dl = api.get(t["tok_a"], f"/workspaces/{t['ws_a']}/support/tickets/1/attachments/{att['id']}")
    assert dl.status_code == 200 and dl.content == PNG
    assert dl.headers["content-disposition"].startswith("attachment;")
    assert dl.headers["x-content-type-options"] == "nosniff"
    # the customer's own actions are in the workspace's activity log, without message bodies
    audit = api.get(t["tok_a"], f"/workspaces/{t['ws_a']}/audit").text
    assert "support.ticket_created" in audit and "Bookinger fejler" not in audit


def test_attachment_rules(api, two_workspaces):
    t = two_workspaces
    exe = _create(api, t["tok_a"], t["ws_a"], files=[("files", ("virus.png", b"MZ\x90\x00\x03\x00\x00\x00", "image/png"))])
    assert exe.status_code == 422 and exe.json()["field_errors"][0]["field"] == "files"
    four = [("files", (f"f{i}.pdf", PDF, "application/pdf")) for i in range(4)]
    assert _create(api, t["tok_a"], t["ws_a"], files=four).status_code == 422
    big = b"%PDF-" + b"a" * (4 * 1024 * 1024)
    assert _create(api, t["tok_a"], t["ws_a"], files=[("files", ("stor.pdf", big, "application/pdf"))]).status_code == 422
    # nothing was created by the refused attempts
    assert api.get(t["tok_a"], f"/workspaces/{t['ws_a']}/support/tickets").json()["items"] == []
    assert _create(api, t["tok_a"], t["ws_a"], subject="x").status_code == 422  # subject too short
    assert _create(api, t["tok_a"], t["ws_a"], category="hacking").status_code == 422


def test_role_matrix(api, two_workspaces):
    t = two_workspaces
    ws = t["ws_a"]
    staff = api.add_member(t["tok_a"], ws, "staff-a@testmail.dk", "staff")
    reader = api.add_member(t["tok_a"], ws, "reader-a@testmail.dk", "reader")
    assert _create(api, staff, ws).status_code == 201
    assert api.get(staff, f"/workspaces/{ws}/support/tickets/1").status_code == 200
    # a reader sees the help page, not the tickets
    assert api.get(reader, f"/workspaces/{ws}/support/tickets").status_code == 403
    assert api.get(reader, f"/workspaces/{ws}/support/tickets/1").status_code == 403
    assert _create(api, reader, ws).status_code == 403
    assert _reply(api, reader, ws, 1, "hej").status_code == 403
    # a customer (even the owner) is not an operator
    for path in ("/operator/support/tickets", f"/operator/support/tickets/{_ticket_id(ws, 1)}"):
        r = api.get(t["tok_a"], path)
        assert r.status_code == 403 and r.json()["code"] == "operator_only"
    assert api.patch(t["tok_a"], f"/operator/support/tickets/{_ticket_id(ws, 1)}", {"status": "resolved"}).status_code == 403
    assert api.post(t["tok_a"], f"/operator/support/tickets/{_ticket_id(ws, 1)}/messages",
                    {"body": "x", "visibility": "public"}).status_code == 403


def _ticket_id(ws, number):
    from app.db import get_session_factory

    with get_session_factory()() as db:
        return str(db.scalar(select(SupportTicket.id).where(SupportTicket.workspace_id == ws, SupportTicket.number == number)))


def test_tenant_isolation(api, two_workspaces):
    t = two_workspaces
    a = _create(api, t["tok_a"], t["ws_a"], subject="Hemmeligt for B",
                files=[("files", ("a.pdf", PDF, "application/pdf"))]).json()
    _create(api, t["tok_b"], t["ws_b"], subject="B's egen sag")
    att = a["messages"][0]["attachments"][0]["id"]
    # B's #1 is B's own; A's workspace and A's attachment are unreachable for B
    assert api.get(t["tok_b"], f"/workspaces/{t['ws_b']}/support/tickets/1").json()["subject"] == "B's egen sag"
    assert api.get(t["tok_b"], f"/workspaces/{t['ws_a']}/support/tickets").status_code == 404
    assert api.get(t["tok_b"], f"/workspaces/{t['ws_a']}/support/tickets/1").status_code == 404
    assert _reply(api, t["tok_b"], t["ws_a"], 1, "indbrud").status_code == 404
    assert api.post(t["tok_b"], f"/workspaces/{t['ws_a']}/support/tickets/1/resolve").status_code == 404
    assert api.get(t["tok_b"], f"/workspaces/{t['ws_b']}/support/tickets/1/attachments/{att}").status_code == 404
    assert api.get(t["tok_b"], f"/workspaces/{t['ws_a']}/support/tickets/1/attachments/{att}").status_code == 404
    assert "Hemmeligt for B" not in api.get(t["tok_b"], f"/workspaces/{t['ws_b']}/support/tickets").text


def test_operator_queue_assignment_reply_and_internal_note(api, two_workspaces, db):
    t = two_workspaces
    _create(api, t["tok_a"], t["ws_a"], files=[("files", ("fejl.png", PNG, "image/png"))])
    _create(api, t["tok_b"], t["ws_b"], subject="Faktura for oktober", category="billing")
    op = api.operator()
    q = api.get(op, "/operator/support/tickets?status=active")
    assert q.status_code == 200
    body = q.json()
    assert body["counts"]["active"] == 2 and body["counts"]["mine"] == 0
    assert {i["workspace"]["name"] for i in body["items"]} == {"Fjord Gulvservice ApS", "Havnebord Café"}
    tid = next(i["id"] for i in body["items"] if i["workspace"]["id"] == t["ws_a"])
    op_id = api.get(op, "/auth/me").json()["id"]
    # assignment: only to an active operator
    owner_a_id = api.get(t["tok_a"], "/auth/me").json()["id"]
    assert api.patch(op, f"/operator/support/tickets/{tid}", {"assigned_to": owner_a_id}).status_code == 422
    d = api.patch(op, f"/operator/support/tickets/{tid}", {"assigned_to": op_id, "status": "in_progress",
                                                           "priority": "high"}).json()
    assert d["assigned_to"]["id"] == op_id and d["status"] == "in_progress" and d["priority"] == "high"
    assert api.get(op, "/operator/support/tickets?assigned=me").json()["counts"]["mine"] == 1
    assert [i["id"] for i in api.get(op, "/operator/support/tickets?assigned=me").json()["items"]] == [tid]
    # the operator sees the customer's attachment
    att = d["messages"][0]["attachments"][0]["id"]
    assert api.get(op, f"/operator/support/tickets/{tid}/attachments/{att}").content == PNG
    # internal note: no status change, no mail
    n = api.post(op, f"/operator/support/tickets/{tid}/messages", {"body": SECRET, "visibility": "internal"})
    assert n.status_code == 201 and n.json()["status"] == "in_progress"
    assert n.json()["messages"][-1]["visibility"] == "internal"
    # client-visible reply: «Afventer kunde» and a mail to the person who opened it
    r = api.post(op, f"/operator/support/tickets/{tid}/messages",
                 {"body": "Hej. Genforbind kalenderen under Indstillinger.", "visibility": "public"})
    assert r.status_code == 201 and r.json()["status"] == "waiting_customer"
    assert db.scalar(select(OutboxEvent).where(OutboxEvent.dedupe_key.like("support-reply:%"))) is not None
    link = api.mailbox_link(t["tok_a"], "supportsag #1", r"(/app/support/\d+)")
    assert link == "/app/support/1"
    # DB-016: the customer sees the reply, never the internal note – not in the ticket, the list or the activity log
    c = api.get(t["tok_a"], f"/workspaces/{t['ws_a']}/support/tickets/1")
    assert c.status_code == 200
    cd = c.json()
    assert [m["author_kind"] for m in cd["messages"]] == ["customer", "operator"]
    assert cd["status"] == "waiting_customer"
    assert SECRET not in c.text and "internal" not in c.text and "priority" not in cd
    assert SECRET not in api.get(t["tok_a"], f"/workspaces/{t['ws_a']}/support/tickets").text
    assert SECRET not in api.get(t["tok_a"], f"/workspaces/{t['ws_a']}/audit").text
    # operator actions are audited in operator scope, without the note's text
    rows = db.scalars(select(AuditLog).where(AuditLog.action.like("support.%"), AuditLog.workspace_id.is_(None))).all()
    assert {r.action for r in rows} >= {"support.operator_updated", "support.internal_note", "support.operator_replied"}
    assert all(SECRET not in str(r.after) for r in rows)
    # customer replies → back to Dialogbot; resolves; reopens
    assert _reply(api, t["tok_a"], t["ws_a"], 1, "Det virker nu, tak.").json()["status"] == "open"
    assert api.post(t["tok_a"], f"/workspaces/{t['ws_a']}/support/tickets/1/resolve").json()["status"] == "resolved"
    assert api.get(op, "/operator/support/tickets?status=resolved").json()["counts"]["resolved"] == 1
    assert api.post(t["tok_a"], f"/workspaces/{t['ws_a']}/support/tickets/1/reopen").json()["status"] == "open"
    assert api.post(t["tok_a"], f"/workspaces/{t['ws_a']}/support/tickets/1/reopen").status_code == 409
    # release to the common queue
    assert api.patch(op, f"/operator/support/tickets/{tid}", {"unassign": True}).json()["assigned_to"] is None


def test_attachment_on_an_internal_note_never_reaches_the_customer(api, two_workspaces, db):
    """Defence in depth for DB-016: even if an attachment hangs on an internal note, the customer's ticket, list and
    download endpoints do not expose it."""
    t = two_workspaces
    _create(api, t["tok_a"], t["ws_a"])
    op = api.operator()
    tid = _ticket_id(t["ws_a"], 1)
    api.post(op, f"/operator/support/tickets/{tid}/messages", {"body": SECRET, "visibility": "internal"})
    note = db.scalar(select(SupportMessage).where(SupportMessage.visibility == "internal"))
    from app.modules.voices import storage

    storage.put(f"ws/{t['ws_a']}/support/{tid}/intern.pdf", PDF, "application/pdf")
    a = SupportAttachment(ticket_id=note.ticket_id, message_id=note.id, workspace_id=note.workspace_id,
                          filename="intern-analyse.pdf", content_type="application/pdf", size_bytes=len(PDF), sha256="0" * 64,
                          storage_key=f"ws/{t['ws_a']}/support/{tid}/intern.pdf")
    db.add(a)
    db.commit()
    c = api.get(t["tok_a"], f"/workspaces/{t['ws_a']}/support/tickets/1")
    assert "intern-analyse" not in c.text and SECRET not in c.text
    assert api.get(t["tok_a"], f"/workspaces/{t['ws_a']}/support/tickets/1/attachments/{a.id}").status_code == 404
    assert api.get(op, f"/operator/support/tickets/{tid}/attachments/{a.id}").status_code == 200


def test_customer_messages_are_always_public(db, two_workspaces):
    """The database refuses an 'internal' message from a customer (check constraint)."""
    from sqlalchemy.exc import IntegrityError

    ws = two_workspaces["ws_a"]
    tk = SupportTicket(workspace_id=ws, number=1, subject="Test", category="other", status="open", priority="normal")
    db.add(tk)
    db.flush()
    db.add(SupportMessage(ticket_id=tk.id, workspace_id=ws, author_kind="customer", visibility="internal", body="x"))
    with pytest.raises(IntegrityError):
        db.flush()
    db.rollback()


def test_new_ticket_rate_limit(api, two_workspaces):
    t = two_workspaces
    for _ in range(10):
        assert _create(api, t["tok_a"], t["ws_a"]).status_code == 201
    r = _create(api, t["tok_a"], t["ws_a"])
    assert r.status_code == 429 and r.json()["code"] == "rate_limited"


def test_reply_mail_in_the_customers_language(api, two_workspaces, db):
    t = two_workspaces
    assert api.patch(t["tok_a"], "/auth/me", {"interface_language": "de"}).status_code == 200
    _create(api, t["tok_a"], t["ws_a"])
    op = api.operator()
    api.post(op, f"/operator/support/tickets/{_ticket_id(t['ws_a'], 1)}/messages", {"body": "Hallo", "visibility": "public"})
    ev = db.scalar(select(OutboxEvent).where(OutboxEvent.dedupe_key.like("support-reply:%")))
    assert ev.payload["to_email"] == "owner-a@testmail.dk"
    assert ev.payload["email"]["subject"] == "Antwort auf Ihre Supportanfrage #1"
    runner.drain()


def test_migration_down_and_up(db):
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    cfg = Config(os.path.join(root, "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(root, "alembic"))
    db.close()
    command.downgrade(cfg, "a7d3e9c2b5f1")
    try:
        with db.bind.connect() as conn:
            for tbl in ("support_tickets", "support_messages", "support_attachments"):
                assert conn.execute(text(f"select to_regclass('{tbl}')")).scalar() is None
    finally:
        command.upgrade(cfg, "head")
    with db.bind.connect() as conn:
        assert conn.execute(text("select to_regclass('support_tickets')")).scalar() == "support_tickets"
