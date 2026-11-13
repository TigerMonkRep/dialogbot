"""QA M03 (e2e-erhverv instans A): operations – job/delivery status, controlled retry, no duplicates.

Krav M03 (/admin/operations → /app/operator/admin/drift): "Call/job/delivery/booking-sync status, dependency
incidents, controlled retry and suspension states without duplicate calls or bookings."
DB-007: "Persist operation identity and provider evidence; test exists/not-created/unknown; no blind new write
after timeout or reconnect."
"""
from __future__ import annotations

from sqlalchemy import select

from app.core.outbox import enqueue
from app.models import OutboxEvent
from app.worker import runner


def test_failed_job_is_visible_to_operators_only_and_without_secrets(api, two_workspaces, db):
    t = two_workspaces
    runner.FAIL_EVENT_TYPES.add("qa.m03.always_fails")
    enqueue(db, event_type="qa.m03.always_fails", dedupe_key="qa-m03-1", workspace_id=t["ws_a"], payload={"x": 1})
    db.commit()
    runner.drain()
    ev = db.scalar(select(OutboxEvent).where(OutboxEvent.dedupe_key == "qa-m03-1"))
    db.refresh(ev)
    assert ev.attempts >= 1 and "simulated failure" in (ev.last_error or "")
    ev.status = "failed"  # as after max attempts
    db.commit()
    op = api.operator()
    ops = api.get(op, "/operator/admin/operations").json()
    assert ops["schema"]["ok"] is True
    job = next(j for j in ops["failed_jobs"] if j["id"] == str(ev.id))
    assert job["workspace_id"] == t["ws_a"] and job["type"] == "qa.m03.always_fails"
    assert api.get(t["tok_a"], "/operator/admin/operations").status_code == 403
    assert "password_hash" not in str(ops)


def test_outbox_dedupe_key_prevents_duplicate_jobs(api, two_workspaces, db):
    t = two_workspaces
    enqueue(db, event_type="email.branded", dedupe_key="qa-m03-dupe", workspace_id=t["ws_a"],
            payload={"to_email": "x@testmail.dk"})
    db.commit()
    enqueue(db, event_type="email.branded", dedupe_key="qa-m03-dupe", workspace_id=t["ws_a"],
            payload={"to_email": "x@testmail.dk"})
    db.commit()
    rows = db.scalars(select(OutboxEvent).where(OutboxEvent.dedupe_key == "qa-m03-dupe")).all()
    assert len(rows) == 1


def test_controlled_retry_and_suspension_exist(api, two_workspaces, db):
    """M03 requires a controlled retry and suspension from the operations screen (operator only). The full behaviour
    (idempotency, audit, no duplicate calendar events, tenant isolation) is in tests/test_ops_m03.py."""
    t = two_workspaces
    runner.FAIL_EVENT_TYPES.add("qa.m03.retry")
    ev = enqueue(db, event_type="qa.m03.retry", dedupe_key="qa-m03-retry", workspace_id=t["ws_a"], payload={})
    db.commit()
    runner.drain()
    db.refresh(ev)
    ev.status = "failed"
    db.commit()
    op = api.operator()
    assert api.post(t["tok_a"], f"/operator/admin/operations/jobs/{ev.id}/retry", {}).status_code == 403
    r = api.post(op, f"/operator/admin/operations/jobs/{ev.id}/retry", {})
    assert r.status_code == 200 and r.json()["result"] == "queued", r.text
    assert api.post(op, f"/operator/admin/operations/jobs/{ev.id}/retry", {}).json()["result"] == "already_queued"
    s = api.post(op, f"/operator/admin/operations/workspaces/{t['ws_b']}/suspend", {"reason": "QA M03"})
    assert s.status_code == 200 and s.json()["suspended"] is True
    ops = api.get(op, "/operator/admin/operations").json()
    assert {"calls", "calendar_sync", "incidents", "suspended"} <= set(ops)
    assert [x["workspace_id"] for x in ops["suspended"]] == [t["ws_b"]]
