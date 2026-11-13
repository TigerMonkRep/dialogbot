"""ASGI app for the load test with a SIMULATED model latency (test-only harness, never deployed to production).

The fake AI provider answers instantly; a real model takes seconds, and the webchat answers inside the request. This
wraps FakeProvider.complete with a sleep of LOADTEST_AI_LATENCY_MS (default 3000) so the test shows what that does to
threads and DB connections. Run: uvicorn scripts.loadtest.slow_app:app --workers 2
"""
from __future__ import annotations

import os
import random
import time

from app.modules.ai import provider as _p

_orig = _p.FakeProvider.complete
_MS = float(os.environ.get("LOADTEST_AI_LATENCY_MS", "3000"))


def _slow(self, *a, **kw):
    time.sleep(_MS / 1000 * random.uniform(0.6, 1.4))
    return _orig(self, *a, **kw)


_p.FakeProvider.complete = _slow

from app.main import app  # noqa: E402,F401
