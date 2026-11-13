"""DB sampler for the load test (read-only): connections and outbox queue every N seconds -> JSON lines.

Usage: SAMPLE_DATABASE_URL=postgresql://... python -m scripts.loadtest.sample_db --every 2 --seconds 300 --out s.jsonl
Never point it at production; it only reads, but the load test it accompanies must never run there.
"""
from __future__ import annotations

import argparse
import json
import os
import time
from datetime import UTC, datetime

import psycopg

Q_CONN = """select count(*) filter (where state is not null) as total,
                   count(*) filter (where state = 'active') as active,
                   count(*) filter (where state = 'idle') as idle,
                   count(*) filter (where state like 'idle in transaction%') as idle_in_tx,
                   count(*) filter (where wait_event_type = 'Lock') as waiting_lock
            from pg_stat_activity where datname = current_database() and pid <> pg_backend_pid()"""
Q_OUTBOX = """select count(*) filter (where status = 'queued' and next_attempt_at <= now()) as due,
                     count(*) filter (where status = 'queued') as queued,
                     count(*) filter (where status = 'processing') as processing,
                     count(*) filter (where status = 'failed') as failed,
                     count(*) filter (where status = 'done') as done,
                     extract(epoch from now() - min(created_at) filter (where status = 'queued' and next_attempt_at <= now())) as oldest_due_s
              from outbox_events"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--every", type=float, default=2.0)
    ap.add_argument("--seconds", type=float, default=300)
    ap.add_argument("--schema", default="public")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    url = os.environ["SAMPLE_DATABASE_URL"].replace("postgresql+psycopg://", "postgresql://")
    stop = time.monotonic() + a.seconds
    with psycopg.connect(url, autocommit=True) as c, open(a.out, "w") as f:
        c.execute(f"set search_path to {a.schema},public")
        while time.monotonic() < stop:
            conn = c.execute(Q_CONN).fetchone()
            ob = c.execute(Q_OUTBOX).fetchone()
            row = {"t": datetime.now(UTC).isoformat(), "conn_total": conn[0], "conn_active": conn[1], "conn_idle": conn[2],
                   "conn_idle_in_tx": conn[3], "conn_waiting_lock": conn[4], "outbox_due": ob[0], "outbox_queued": ob[1],
                   "outbox_processing": ob[2], "outbox_failed": ob[3], "outbox_done": ob[4],
                   "outbox_oldest_due_s": float(ob[5]) if ob[5] is not None else None}
            f.write(json.dumps(row) + "\n")
            f.flush()
            time.sleep(a.every)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
