"""Leads and tasks: webchat contact form, separate qualification/pipeline/billing axes, idempotent
approval with agreement version and fee snapshot (A = 0, B = 149 kr.), roles, tenant isolation."""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select

from app.config import get_settings
from app.models import AuditLog, Lead, OutboxEvent, Task
from app.modules.ai import provider as ai_provider
from app.modules.ai.provider import FakeProvider
from app.worker import runner

SITE = "https://www.fjordgulv.example"
API = "http://localhost:8000"
PUB = "/api/v1/public/webchat"


@pytest.fixture
def fake(monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "fake")
    get_settings.cache_clear()
    p = FakeProvider(get_settings())
    ai_provider.set_provider_override(p)
    yield p
    ai_provider.set_provider_override(None)
    get_settings.cache_clear()


@pytest.fixture
def chat(api, client, two_workspaces, fake):
    """Workspace A with a live widget and one conversation with one exchange."""
    t = two_workspaces
    it = api.knowledge(t["tok_a"], t["ws_a"], "service", "Afslibning", {"price_net_minor": 14500})
    api.submit(t["tok_a"], t["ws_a"], it["open_draft"]["id"])
    api.approve(t["tok_a"], t["ws_a"], it["open_draft"]["id"])
    s = api.get(t["tok_a"], f"/workspaces/{t['ws_a']}/webchat").json()
    key = api.put(t["tok_a"], f"/workspaces/{t['ws_a']}/webchat",
                  {"expected_version": s["version"], "enabled": True, "allowed_origins": [SITE], "greeting": ""}).json()["widget_key"]
    conv = client.post(f"{PUB}/{key}/conversations", json={"host_origin": SITE}, headers={"origin": API}).json()
    client.post(f"{PUB}/{key}/conversations/{conv['conversation_id']}/messages", json={"text": "Kan I slibe 65 m²?"},
                headers={"origin": API, "x-visitor-token": conv["visitor_token"]})
    return t | {"key": key, "conv": conv}


def _contact(client, chat, **over):
    body = {"name": "Henrik", "email": "henrik@example.com", "phone": None, "note": "", "consent": True} | over
    c = chat["conv"]
    return client.post(f"{PUB}/{chat['key']}/conversations/{c['conversation_id']}/contact", json=body,
                       headers={"origin": API, "x-visitor-token": c["visitor_token"]})


def _base(chat):
    return f"/workspaces/{chat['ws_a']}"


def test_webchat_contact_creates_lead_task_and_notification(client, api, chat, db, fake):
    assert "Bliv kontaktet" in fake.last_system  # channel instructions reach the model
    r = _contact(client, chat)
    assert r.status_code == 200, r.text
    lead = db.scalar(select(Lead))
    assert (lead.source, lead.contact_name, lead.contact_email, lead.need_summary) == \
        ("webchat", "Henrik", "henrik@example.com", "Kan I slibe 65 m²?")
    assert (lead.qualification_status, lead.pipeline_status, lead.billing_status) == ("unqualified", "new", "pending")
    task = db.scalar(select(Task))
    assert task.lead_id == lead.id and task.title == "Kontakt Henrik fra webchat" and task.due_at is not None
    ev = db.scalar(select(OutboxEvent).where(OutboxEvent.event_type == "email.new_lead"))
    assert ev.payload["to_email"] == "owner-a@testmail.dk" and f"/app/leads/{lead.id}" in ev.payload["link"]
    runner.drain()
    # a second submit updates the same lead, no second task or notification
    assert _contact(client, chat, name="Henrik V.", phone="+45 20 30 40 50", note="Helst om formiddagen").status_code == 200
    db.expire_all()
    assert db.scalar(select(Lead)).contact_phone == "+45 20 30 40 50"
    assert len(db.scalars(select(Task)).all()) == 1
    assert len(db.scalars(select(OutboxEvent).where(OutboxEvent.event_type == "email.new_lead")).all()) == 1
    # the conversation shows its lead in the app
    got = api.get(chat["tok_a"], f"{_base(chat)}/conversations/{chat['conv']['conversation_id']}/lead").json()
    assert got["lead"]["contact_name"] == "Henrik V."


def test_contact_validation_and_frame_only(client, chat):
    assert _contact(client, chat, consent=False).status_code == 422
    assert _contact(client, chat, email=None, phone=None).status_code == 422
    assert _contact(client, chat, email=None, phone="ring mig").status_code == 422
    c = chat["conv"]
    r = client.post(f"{PUB}/{chat['key']}/conversations/{c['conversation_id']}/contact",
                    json={"name": "X", "email": "x@example.com", "consent": True},
                    headers={"origin": SITE, "x-visitor-token": c["visitor_token"]})
    assert r.status_code == 403


def test_axes_are_independent_and_approval_needs_qualification_and_agreement(client, api, chat, db):
    _contact(client, chat)
    tok, base = chat["tok_a"], _base(chat)
    lead = api.get(tok, f"{base}/leads").json()["items"][0]
    lid = lead["id"]
    r = api.c.patch(f"/api/v1{base}/leads/{lid}", json={"expected_version": lead["version"], "pipeline_status": "contacted"},
                    headers=api.h(tok))
    assert r.status_code == 200 and r.json()["pipeline_status"] == "contacted" and r.json()["billing_status"] == "pending"
    assert api.post(tok, f"{base}/leads/{lid}/approve").json()["code"] == "lead_not_qualified"
    v = r.json()["version"]
    r = api.c.patch(f"/api/v1{base}/leads/{lid}", json={"expected_version": v, "qualification_status": "qualified"},
                    headers=api.h(tok))
    assert r.json()["qualification_status"] == "qualified"
    stale = api.c.patch(f"/api/v1{base}/leads/{lid}", json={"expected_version": v, "pipeline_status": "won"}, headers=api.h(tok))
    assert stale.status_code == 409 and stale.json()["code"] == "version_conflict"
    assert api.post(tok, f"{base}/leads/{lid}/approve").json()["code"] == "no_agreement"


def test_model_b_approval_snapshots_fee_and_is_idempotent(client, api, chat, db):
    _contact(client, chat)
    tok, base = chat["tok_a"], _base(chat)
    lead = api.get(tok, f"{base}/leads").json()["items"][0]
    api.c.patch(f"/api/v1{base}/leads/{lead['id']}", json={"expected_version": lead["version"], "qualification_status": "qualified"},
                headers=api.h(tok))
    assert api.post(tok, f"{base}/agreement", {"model": "A"}).json()["version"] == 1
    agreement = api.post(tok, f"{base}/agreement", {"model": "B"}).json()
    assert agreement["version"] == 2 and agreement["lead_fee"]["net_minor"] == 14900
    assert agreement["lead_fee"]["gross_minor"] == 18625 and agreement["invoicing"] == "not_implemented"
    key = str(uuid.uuid4())
    first = api.post(tok, f"{base}/leads/{lead['id']}/approve", None, **{"Idempotency-Key": key})
    assert first.status_code == 200, first.text
    snap = first.json()["fee_snapshot"]
    assert (snap["net_minor"], snap["tax_minor"], snap["agreement_version"], snap["model"]) == (14900, 3725, 2, "B")
    again = api.post(tok, f"{base}/leads/{lead['id']}/approve", None, **{"Idempotency-Key": key})
    assert again.status_code == 200 and again.json() == first.json()
    assert api.post(tok, f"{base}/leads/{lead['id']}/approve").json()["code"] == "lead_billing_decided"
    # once decided, qualification is frozen; pipeline can still move
    cur = api.get(tok, f"{base}/leads/{lead['id']}").json()
    frozen = api.c.patch(f"/api/v1{base}/leads/{lead['id']}",
                         json={"expected_version": cur["version"], "qualification_status": "disqualified"}, headers=api.h(tok))
    assert frozen.json()["code"] == "lead_billing_decided"
    moved = api.c.patch(f"/api/v1{base}/leads/{lead['id']}", json={"expected_version": cur["version"], "pipeline_status": "won"},
                        headers=api.h(tok))
    assert moved.status_code == 200
    # a later agreement change never rewrites an approved lead's snapshot
    api.post(tok, f"{base}/agreement", {"model": "A"})
    assert api.get(tok, f"{base}/leads/{lead['id']}").json()["fee_snapshot"]["net_minor"] == 14900
    assert db.scalar(select(AuditLog).where(AuditLog.action == "lead.approved")) is not None


def test_model_a_approval_costs_nothing_and_reject_needs_reason(api, chat):
    tok, base = chat["tok_a"], _base(chat)
    api.post(tok, f"{base}/agreement", {"model": "A"})
    a = api.post(tok, f"{base}/leads", {"contact_name": "Manuel", "need_summary": "Ringede ind"}).json()
    assert a["source"] == "manual"
    api.c.patch(f"/api/v1{base}/leads/{a['id']}", json={"expected_version": a["version"], "qualification_status": "qualified"},
                headers=api.h(tok))
    snap = api.post(tok, f"{base}/leads/{a['id']}/approve").json()["fee_snapshot"]
    assert snap["net_minor"] == 0 and snap["model"] == "A"
    b = api.post(tok, f"{base}/leads", {"contact_name": "Spam"}).json()
    assert api.post(tok, f"{base}/leads/{b['id']}/reject", {"reason": ""}).status_code == 422
    r = api.post(tok, f"{base}/leads/{b['id']}/reject", {"reason": "Sælger, ikke kunde"})
    assert r.json()["billing_status"] == "rejected" and r.json()["fee_snapshot"] is None


def test_roles_and_tenant_isolation(client, api, chat):
    _contact(client, chat)
    tok, base = chat["tok_a"], _base(chat)
    lead = api.get(tok, f"{base}/leads").json()["items"][0]
    staff = api.add_member(tok, chat["ws_a"], "staff@testmail.dk", "staff")
    reader = api.add_member(tok, chat["ws_a"], "reader@testmail.dk", "reader")
    admin = api.add_member(tok, chat["ws_a"], "admin@testmail.dk", "admin")
    assert api.get(staff, f"{base}/leads").status_code == 200
    assert api.get(reader, f"{base}/leads").status_code == 403
    assert api.post(staff, f"{base}/leads/{lead['id']}/approve").status_code == 403
    assert api.get(staff, f"{base}/agreement").status_code == 403
    assert api.get(admin, f"{base}/agreement").status_code == 200
    assert api.post(admin, f"{base}/agreement", {"model": "B"}).status_code == 403  # owner only
    b = f"/workspaces/{chat['ws_b']}"
    assert api.get(chat["tok_b"], f"{b}/leads").json()["total"] == 0
    assert api.get(chat["tok_b"], f"{b}/leads/{lead['id']}").status_code == 404
    assert api.post(chat["tok_b"], f"{b}/leads/{lead['id']}/approve").status_code == 404
    assert api.post(chat["tok_b"], f"{b}/leads", {"conversation_id": chat["conv"]["conversation_id"]}).status_code == 404


def test_tasks_crud_assignment_and_filters(client, api, chat):
    _contact(client, chat)
    tok, base = chat["tok_a"], _base(chat)
    staff = api.add_member(tok, chat["ws_a"], "staff@testmail.dk", "staff")
    staff_id = next(m["user_id"] for m in api.get(tok, f"{base}/members").json() if m["role"] == "staff")
    lead = api.get(tok, f"{base}/leads").json()["items"][0]
    t = api.post(staff, f"{base}/tasks", {"title": "Send tilbud", "lead_id": lead["id"], "assignee_user_id": staff_id}).json()
    assert api.post(tok, f"{base}/tasks", {"title": "x", "assignee_user_id": str(uuid.uuid4())}).status_code == 422
    assert api.get(staff, f"{base}/tasks?mine=true").json()["total"] == 1
    assert api.get(tok, f"{base}/tasks").json()["total"] == 2  # + the automatic "Kontakt" task
    done = api.c.patch(f"/api/v1{base}/tasks/{t['id']}", json={"status": "done"}, headers=api.h(staff)).json()
    assert done["status"] == "done" and done["completed_at"]
    assert api.get(tok, f"{base}/tasks?status=done").json()["total"] == 1
    detail = api.get(tok, f"{base}/leads/{lead['id']}").json()
    assert {x["title"] for x in detail["tasks"]} == {"Kontakt Henrik fra webchat", "Send tilbud"}
    # one lead per conversation, also when created by staff
    r = api.post(tok, f"{base}/leads", {"conversation_id": chat["conv"]["conversation_id"]})
    assert r.status_code == 409 and r.json()["lead_id"] == lead["id"]
