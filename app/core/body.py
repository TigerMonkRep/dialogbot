"""Request bodies as dependencies, so endpoints that touch the database can be plain `def`.

FastAPI runs a `def` endpoint in its threadpool, but an `async def` endpoint on the event loop itself. Synchronous
SQLAlchemy (or storage/HTTP calls) inside an `async def` therefore blocks the whole process – and when the pool is
empty it blocks it for up to `pool_timeout` (30 s), while the threadpool endpoints holding the connections cannot
finish (QA loadtest-2026-11-13 §1.4: lost Vapi end-of-call reports, /health/ready hanging).

The only thing those endpoints needed `async` for was `await request.body()`. These async dependencies read the body
on the loop (where reading belongs) and hand the bytes to a synchronous endpoint. Declare them *after* the auth/context
dependencies so the order of checks (401/403 before 422) stays as it was.
"""
from __future__ import annotations

from collections.abc import Awaitable, Callable

from fastapi import Request

from app.core.errors import ValidationFailed


async def raw_body(request: Request) -> bytes:
    """The whole request body (Starlette caches it, so reading it twice is fine)."""
    return await request.body()


def capped_body(cap: int, message: str, field: str) -> Callable[[Request], Awaitable[bytes]]:
    """The request body, refused (422 on `field`) as soon as it exceeds `cap` – never buffered beyond it."""

    async def read(request: Request) -> bytes:
        declared = request.headers.get("content-length")
        if declared and declared.isdigit() and int(declared) > cap:
            raise ValidationFailed(message, field_errors=[{"field": field}])
        buf = bytearray()
        async for part in request.stream():
            buf += part
            if len(buf) > cap:
                raise ValidationFailed(message, field_errors=[{"field": field}])
        return bytes(buf)

    return read
