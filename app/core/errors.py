"""Uniform API errors: {code, message, field_errors, request_id}."""
from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


class ApiError(Exception):
    status_code = 400
    code = "bad_request"

    def __init__(self, message: str, *, code: str | None = None, status_code: int | None = None,
                 field_errors: list[dict[str, Any]] | None = None, extra: dict[str, Any] | None = None):
        super().__init__(message)
        self.message = message
        if code:
            self.code = code
        if status_code:
            self.status_code = status_code
        self.field_errors = field_errors or []
        self.extra = extra or {}


class NotFound(ApiError):
    status_code = 404
    code = "not_found"


class Unauthenticated(ApiError):
    status_code = 401
    code = "unauthenticated"


class Forbidden(ApiError):
    status_code = 403
    code = "forbidden"


class Conflict(ApiError):
    status_code = 409
    code = "conflict"


class ValidationFailed(ApiError):
    status_code = 422
    code = "validation_failed"


class NotImplementedYet(ApiError):
    """A capability that is deliberately not implemented in this stage."""

    status_code = 501
    code = "not_implemented"


def _payload(request: Request, code: str, message: str, field_errors=None, extra=None) -> dict[str, Any]:
    body = {
        "code": code,
        "message": message,
        "field_errors": field_errors or [],
        "request_id": getattr(request.state, "request_id", None),
    }
    if extra:
        body.update(extra)
    return body


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _api_error(request: Request, exc: ApiError):
        return JSONResponse(
            status_code=exc.status_code,
            content=_payload(request, exc.code, exc.message, exc.field_errors, exc.extra),
        )

    @app.exception_handler(RequestValidationError)
    async def _validation(request: Request, exc: RequestValidationError):
        errors = [
            {"field": ".".join(str(p) for p in e.get("loc", [])[1:]) or str(e.get("loc")), "message": e.get("msg")}
            for e in exc.errors()
        ]
        return JSONResponse(status_code=422, content=_payload(request, "validation_failed", "Ugyldigt input", errors))

    @app.exception_handler(StarletteHTTPException)
    async def _http(request: Request, exc: StarletteHTTPException):
        code = {401: "unauthenticated", 403: "forbidden", 404: "not_found", 405: "method_not_allowed"}.get(
            exc.status_code, "http_error"
        )
        return JSONResponse(status_code=exc.status_code, content=_payload(request, code, str(exc.detail)))
