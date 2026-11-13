"""Structured JSON logging with request IDs. Tokens are never logged."""
from __future__ import annotations

import logging
import re
import sys
import uuid

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

_REDACT_HEADERS = {"authorization", "cookie", "x-api-key"}


def configure_logging(level: str = "INFO") -> None:
    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=level.upper())
    # httpx logs every request URL at INFO — including query strings, which for Meta's Graph API carry the access
    # token. Nothing we need; warnings and errors still come through.
    for name in ("httpx", "httpcore"):
        logging.getLogger(name).setLevel(logging.WARNING)
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.getLevelName(level.upper())),
        logger_factory=structlog.PrintLoggerFactory(sys.stdout),
        cache_logger_on_first_use=False,
    )


log = structlog.get_logger("dialogbot")


# Path parts that are bearer secrets – whoever has one gets in: calendar feeds (Privat and bookings), Privat list
# invitations by token or short code, group join links, team invitations, sales offers, parent consent links and the
# customer's own links (callback page and booking management, W09/W13, F-VER1113-06). The
# part is never written to the log (F-PS-04). Only the path is logged, never the query string.
_SECRET_PATHS = re.compile(
    r"(/privat/calendar/feed/|/privat/invites/by-code/|/privat/invites/(?!by-code/)|/privat/group-invites/by-code/"
    r"|^(?:/api/v1)?/invitations/(?!accept/?$)|/public/offers/|/public/calendar/|/public/ambassadors/parent-consent/"
    r"|/public/customer/callback/|/public/booking/manage/)"
    r"[^/]+")


def redact_path(path: str) -> str:
    return _SECRET_PATHS.sub(r"\1***", path)


class RequestIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("x-request-id") or uuid.uuid4().hex
        request.state.request_id = request_id
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=request_id, path=redact_path(request.url.path),
                                               method=request.method)
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        log.info("request", status=response.status_code)
        return response
