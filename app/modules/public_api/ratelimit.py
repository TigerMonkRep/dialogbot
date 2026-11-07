"""Per-key rate limiting for the public API: token buckets, 600 reads and 60 writes per minute by default.

The middleware identifies the caller by the digest of the bearer token (the same value the key is stored under), so
it needs no database round-trip and runs before authentication; an unknown token gets its own bucket and then a 401.
Reads are GET/HEAD/OPTIONS, writes everything else. A refusal is 429 with `Retry-After` (whole seconds) and the
standard `X-RateLimit-Limit` / `X-RateLimit-Remaining` headers are on every answer.

`LIMITER` is the one object the middleware talks to. The in-process implementation keeps one bucket per key and
class per process (several API instances therefore allow several times the limit); a shared backend (Redis) only
has to implement `Limiter.take()` and be assigned to `LIMITER` at startup.
"""
from __future__ import annotations

import math
import threading
import time
from dataclasses import dataclass
from typing import Protocol

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.security import token_digest

READ_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
MAX_BUCKETS = 20_000


@dataclass(frozen=True)
class Decision:
    allowed: bool
    limit: int
    remaining: int
    retry_after: int  # seconds, 0 when allowed


class Limiter(Protocol):
    def take(self, identity: str, kind: str) -> Decision: ...


class TokenBucketLimiter:
    """Classic token bucket: `limit` tokens per 60 s, refilled continuously, burst up to `limit`."""

    def __init__(self, *, read_per_minute: int, write_per_minute: int, clock=time.monotonic):
        self.limits = {"read": read_per_minute, "write": write_per_minute}
        self._clock = clock
        self._lock = threading.Lock()
        self._buckets: dict[tuple[str, str], tuple[float, float]] = {}  # (tokens, last_refill)

    def take(self, identity: str, kind: str) -> Decision:
        limit = self.limits[kind]
        rate = limit / 60.0
        now = self._clock()
        with self._lock:
            tokens, last = self._buckets.get((identity, kind), (float(limit), now))
            tokens = min(float(limit), tokens + (now - last) * rate)
            if tokens >= 1.0:
                tokens -= 1.0
                self._buckets[(identity, kind)] = (tokens, now)
                return Decision(True, limit, int(tokens), 0)
            self._buckets[(identity, kind)] = (tokens, now)
            retry = math.ceil((1.0 - tokens) / rate)
            if len(self._buckets) > MAX_BUCKETS:
                self._prune(now, rate)
            return Decision(False, limit, 0, max(1, retry))

    def _prune(self, now: float, rate: float) -> None:
        stale = now - 120
        for k, (_t, last) in list(self._buckets.items()):
            if last < stale:
                del self._buckets[k]

    def reset(self) -> None:
        with self._lock:
            self._buckets.clear()


def default_limiter() -> TokenBucketLimiter:
    from app.config import get_settings

    s = get_settings()
    return TokenBucketLimiter(read_per_minute=s.public_api_read_rpm, write_per_minute=s.public_api_write_rpm)


LIMITER: Limiter | None = None  # created on first use (settings are not read at import time)


def limiter() -> Limiter:
    global LIMITER
    if LIMITER is None:
        LIMITER = default_limiter()
    return LIMITER


def identity_of(scope: Scope) -> str | None:
    """The digest of the bearer token, or None when there is none (the route answers 401 itself)."""
    for name, value in scope.get("headers") or ():
        if name == b"authorization":
            auth = value.decode("latin-1")
            scheme, _, token = auth.partition(" ")
            if scheme.lower() == "bearer" and token.strip():
                return token_digest(token.strip())
            return None
    return None


class RateLimitMiddleware:
    """Pure ASGI (no body buffering). Mounted on the public sub-application only."""

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        identity = identity_of(scope)
        if identity is None:
            await self.app(scope, receive, send)
            return
        kind = "read" if scope["method"] in READ_METHODS else "write"
        decision = limiter().take(identity, kind)
        headers = [(b"x-ratelimit-limit", str(decision.limit).encode()),
                   (b"x-ratelimit-remaining", str(decision.remaining).encode())]
        if not decision.allowed:
            body = (b'{"code":"rate_limited","message":"For mange kald \xe2\x80\x93 pr\xc3\xb8v igen om lidt",'
                    b'"field_errors":[],"request_id":null,"retry_after":' + str(decision.retry_after).encode() + b"}")
            await send({"type": "http.response.start", "status": 429,
                        "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode()),
                                    (b"retry-after", str(decision.retry_after).encode()), *headers]})
            await send({"type": "http.response.body", "body": body})
            return

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                message["headers"] = list(message.get("headers") or []) + headers
            await send(message)

        await self.app(scope, receive, send_with_headers)
