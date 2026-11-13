"""Synchronous database work never runs on the event loop (QA loadtest-2026-11-13 §1.4).

`POST /webhooks/vapi` was `async def` with synchronous SQLAlchemy inside. When the pool was empty it waited for a
connection *on the event loop* (up to 30 s): every other request of the process – /health included – stood still,
and end-of-call reports were lost. These tests hold every pooled connection, send a report, and check that the
process keeps answering, that the report is stored once the pool frees up, and that a doubly-sent report is stored
once. A static guard keeps new `async def` + `get_db` endpoints from coming back, and the webchat must not hold a
connection while the model answers.
"""
from __future__ import annotations

import asyncio
import inspect
import threading
import time

import httpx
from fastapi.routing import APIRoute, APIWebSocketRoute
from sqlalchemy import func, select

from app.db import get_db, get_engine
from app.models import Call, Conversation, Lead, Task, WebhookEvent
from tests.test_telephony import SECRET, URL, _report, _setup, configured  # noqa: F401 – `configured` is a fixture
from tests.test_webchat import _say, _start, fake, live  # noqa: F401 – `fake`, `live` are fixtures

HEADERS = {"content-type": "application/json", "authorization": f"Bearer {SECRET}"}
HOLD_S = 2.5  # how long every pooled connection is held by the test


def _hold_whole_pool():
    """Check out every free connection of the API's pool; returns them and a function that gives them back."""
    pool = get_engine().pool
    free = pool.size() + pool._max_overflow - pool.checkedout()  # noqa: SLF001 – QueuePool has no public getter
    conns = [get_engine().connect() for _ in range(free)]
    assert pool.checkedout() == pool.size() + pool._max_overflow  # noqa: SLF001

    def release():
        for c in conns:
            c.close()

    return release


def test_a_webhook_waiting_for_the_pool_does_not_stall_the_process(app, api, two_workspaces, configured, db):  # noqa: F811
    _setup(api, two_workspaces)
    report = {"message": _report("call_pool")}

    async def scenario():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test", timeout=60) as c:
            release = _hold_whole_pool()
            # Released from a plain thread: with the old code the event loop itself is blocked and could not do it.
            timer = threading.Timer(HOLD_S, release)
            timer.start()
            try:
                t0 = time.monotonic()
                webhook = asyncio.create_task(c.post(URL, json=report, headers=HEADERS))
                await asyncio.sleep(0.3)  # the webhook is now waiting for a pooled connection
                health = await c.get("/health/live")
                # Measured from the webhook's start: with the old code the loop (and this sleep) stood still until
                # the pool was given back, so the health check came back only after ~HOLD_S.
                health_s = time.monotonic() - t0
                webhook_pending = not webhook.done()
                r = await webhook
            finally:
                timer.join()
                release()
            return health, health_s, webhook_pending, r

    health, health_s, webhook_pending, r = asyncio.run(scenario())
    assert health.status_code == 200
    assert health_s < 1.3, f"/health/live answered after {health_s:.2f} s while a webhook waited for the pool"
    assert webhook_pending, "the webhook should still have been waiting for a connection"
    assert r.status_code == 200, r.text
    assert r.json() == {"received": True, "duplicate": False, "outcome": "applied"}  # not lost
    assert db.scalar(select(func.count()).select_from(Call).where(Call.provider_call_id == "call_pool")) == 1


def test_a_report_sent_twice_at_once_is_stored_once(app, api, two_workspaces, configured, db):  # noqa: F811
    _setup(api, two_workspaces)

    async def scenario():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test", timeout=60) as c:
            out = []
            for i in range(5):  # five calls, each report sent twice concurrently (as when Vapi retries)
                body = {"message": _report(f"call_dup_{i}", caller=f"+452030405{i}")}
                out += await asyncio.gather(c.post(URL, json=body, headers=HEADERS), c.post(URL, json=body, headers=HEADERS))
            return out

    responses = asyncio.run(scenario())
    assert all(r.status_code == 200 for r in responses), [r.text for r in responses if r.status_code != 200]
    applied = [r for r in responses if r.json().get("duplicate") is False]
    assert len(applied) == 5 and len(responses) - len(applied) == 5
    for model in (Call, Conversation, Lead, Task):
        assert db.scalar(select(func.count()).select_from(model)) == 5, model.__name__
    assert db.scalar(select(func.count()).select_from(WebhookEvent).where(WebhookEvent.provider == "vapi")) == 5


# Endpoints that may stay `async def` although a dependency opens a session: they await real asynchronous work and
# push their few synchronous DB reads through the threadpool themselves.
ASYNC_WITH_DB_ALLOWED = {
    "linden_replay",  # awaits a Speechmatics session; `_ws` and the dictionary are read via run_in_threadpool
}


def _routes(routes):
    for r in routes:
        if hasattr(r, "original_router"):
            yield from _routes(r.original_router.routes)
        elif isinstance(r, APIRoute | APIWebSocketRoute):
            yield r
        elif hasattr(r, "app") and hasattr(r.app, "routes"):
            yield from _routes(r.app.routes)
        elif hasattr(r, "routes"):
            yield from _routes(r.routes)


def _uses_db(dependant) -> bool:
    return any(d.call is get_db or _uses_db(d) for d in dependant.dependencies)


def test_no_async_endpoint_does_synchronous_database_work(app):
    routes = list(_routes(app.routes))
    assert len(routes) > 100  # the walk reaches the included routers (and the mounted public API)
    offenders = sorted(f"{r.path} ({r.endpoint.__module__}.{r.endpoint.__name__})" for r in routes
                       if inspect.iscoroutinefunction(r.endpoint) and _uses_db(r.dependant)
                       and r.endpoint.__name__ not in ASYNC_WITH_DB_ALLOWED)
    assert offenders == [], ("`async def` endpoints run on the event loop; synchronous SQLAlchemy there freezes the "
                             "process when the pool is empty. Make them `def` (read the body with "
                             "app.core.body.raw_body) or use run_in_threadpool: " + ", ".join(offenders))


def test_webchat_holds_no_connection_while_the_model_answers(client, live, fake, monkeypatch):  # noqa: F811
    pool = get_engine().pool
    seen: list[int] = []
    real = fake.complete

    def complete(**kw):
        seen.append(pool.checkedout())
        return real(**kw)

    monkeypatch.setattr(fake, "complete", complete)
    conv = _start(client, live["key"]).json()
    baseline = pool.checkedout()
    r = _say(client, live["key"], conv, "Hvad koster afslibning?")
    assert r.status_code == 200, r.text
    assert r.json()["reply"]["role"] == "assistant" and r.json()["reply"]["text"]
    # Before the fix the request's own session held a connection (baseline + 1) for the whole model call.
    assert seen == [baseline], seen
    assert pool.checkedout() == baseline  # and gave it back afterwards
    history = client.get(f"/api/v1/public/webchat/{live['key']}/conversations/{conv['conversation_id']}/messages",
                         headers={"x-visitor-token": conv["visitor_token"]}).json()["messages"]
    assert [m["role"] for m in history] == ["visitor", "assistant"]  # behaviour unchanged: both turns stored
