"""IdempotencyGuard: insert-first reservation, replay, payload mismatch, and atomic takeover of an abandoned
reservation (QA F-VR-03-X11, F-VR-04-X11)."""
from __future__ import annotations

import threading
import time
import uuid
from datetime import UTC, datetime, timedelta

from app.core.errors import Conflict
from app.core.idempotency import IN_PROGRESS, IdempotencyGuard, payload_hash
from app.db import get_session_factory
from app.models import IdempotencyKey


def _cleanup(scope: str) -> None:
    with get_session_factory()() as s:
        s.query(IdempotencyKey).filter(IdempotencyKey.scope == scope).delete()
        s.commit()


def test_reserve_store_replay_and_mismatch():
    scope, key = f"test:{uuid.uuid4()}", "k1"
    try:
        with get_session_factory()() as s:
            g = IdempotencyGuard(s, scope, key, {"a": 1})
            assert g.replay is None
            g.store(201, {"ok": True})
            s.commit()
        with get_session_factory()() as s:
            assert IdempotencyGuard(s, scope, key, {"a": 1}).replay == (201, {"ok": True})
            try:
                IdempotencyGuard(s, scope, key, {"a": 2})
                raise AssertionError("payload mismatch was accepted")
            except Conflict as e:
                assert e.code == "idempotency_payload_mismatch"
    finally:
        _cleanup(scope)


def test_two_concurrent_takeovers_of_an_abandoned_reservation_have_one_winner():
    scope, key = f"test:{uuid.uuid4()}", "stale"
    with get_session_factory()() as s:
        s.add(IdempotencyKey(scope=scope, key=key, payload_hash=payload_hash({"same": True}), response_status=IN_PROGRESS, response_body={},
                             created_at=datetime.now(UTC) - timedelta(minutes=10)))
        s.commit()
    barrier = threading.Barrier(2)
    results: list[str] = []

    def go():
        with get_session_factory()() as s:
            barrier.wait()
            try:
                g = IdempotencyGuard(s, scope, key, {"same": True})
                if g.replay is not None:  # the other one already finished: its answer is replayed
                    results.append("replay")
                    return
                results.append("won")
                time.sleep(0.3)  # hold the row while the other request tries
                g.store(200, {"done": True})
                s.commit()
            except Conflict as e:
                s.rollback()
                results.append(e.code)

    threads = [threading.Thread(target=go) for _ in range(2)]
    try:
        [t.start() for t in threads]
        [t.join() for t in threads]
        # exactly one request takes the abandoned reservation over; the other waits for it and then gets a 409
        # (still in progress) or the stored answer (finished) – never a second run and never a 500
        assert results.count("won") == 1 and len(results) == 2, results
        assert set(results) - {"won"} <= {"idempotency_in_progress", "replay"}, results
        with get_session_factory()() as s:
            row = s.query(IdempotencyKey).filter_by(scope=scope, key=key).one()
            assert (row.response_status, row.response_body) == (200, {"done": True})
    finally:
        _cleanup(scope)
