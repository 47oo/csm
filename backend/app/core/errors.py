"""Unified error envelope and exception handlers (Contract §1.2, DR-10).

Every error response has the shape::

    {"error": {"code": "STRING_CODE", "message": "human readable", "details": {}}}

``message`` never contains credentials, account existence hints or stack traces.
The 500 handler deliberately logs (through the redacting filter) and returns a
fixed body.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger("csm.errors")


class AppError(Exception):
    """Base class for expected application errors mapped to the error envelope."""

    status_code: int = 500
    code: str = "INTERNAL_ERROR"
    default_message: str = "Internal server error"

    def __init__(
        self,
        message: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message or self.default_message)
        self.message = message or self.default_message
        self.details: dict[str, Any] = details or {}

    def envelope(self) -> dict[str, Any]:
        return {
            "error": {
                "code": self.code,
                "message": self.message,
                "details": self.details,
            }
        }


class AuthRequired(AppError):
    """401: no session, or an unusable/expired session (Contract §1.2)."""

    status_code = 401
    code = "AUTH_REQUIRED"
    default_message = "Authentication required"


class InvalidCredentials(AppError):
    """401: bad credentials, unknown account or disabled account (indistinct)."""

    status_code = 401
    code = "AUTH_INVALID_CREDENTIALS"
    default_message = "Invalid credentials"


class Forbidden(AppError):
    """403: authenticated but lacking permission, or a failed CSRF check."""

    status_code = 403
    code = "FORBIDDEN"
    default_message = "Forbidden"

    def __init__(self, reason: str | None = None) -> None:
        details = {"reason": reason} if reason else {}
        super().__init__(details=details)


class VersionConflict(AppError):
    """409: optimistic-lock version is stale (DR-11)."""

    status_code = 409
    code = "VERSION_CONFLICT"
    default_message = "Version conflict"

    def __init__(self, current_version: int) -> None:
        super().__init__(details={"current_version": int(current_version)})


class NotFound(AppError):
    """404: target resource/path does not exist."""

    status_code = 404
    code = "NOT_FOUND"
    default_message = "Not found"


class ValidationError(AppError):
    """422: request body/parameter validation failed."""

    status_code = 422
    code = "VALIDATION_ERROR"
    default_message = "Validation error"


class InternalError(AppError):
    """500: unexpected server error (never leaks stack/credentials)."""

    status_code = 500
    code = "INTERNAL_ERROR"
    default_message = "Internal server error"


_HTTP_CODE_MAP = {
    401: "AUTH_REQUIRED",
    403: "FORBIDDEN",
    404: "NOT_FOUND",
    405: "METHOD_NOT_ALLOWED",
    409: "VERSION_CONFLICT",
    422: "VALIDATION_ERROR",
}


def _json_error(status_code: int, code: str, message: str, details: dict | None = None):
    return JSONResponse(
        status_code=status_code,
        content={"error": {"code": code, "message": message, "details": details or {}}},
    )


def register_exception_handlers(app: FastAPI) -> None:
    """Register all error handlers on the FastAPI application."""

    @app.exception_handler(AppError)
    async def _app_error(_request: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content=exc.envelope())

    @app.exception_handler(RequestValidationError)
    async def _validation_error(
        _request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        fields: list[dict[str, str]] = []
        for error in exc.errors():
            location = [str(part) for part in error.get("loc", ())]
            if location and location[0] in {"body", "query", "path", "header", "cookie"}:
                location = location[1:]
            fields.append(
                {
                    "field": ".".join(location) or "body",
                    "message": str(error.get("msg", "invalid")),
                }
            )
        return _json_error(422, "VALIDATION_ERROR", "Validation error", {"fields": fields})

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(_request: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = _HTTP_CODE_MAP.get(exc.status_code, "HTTP_ERROR")
        response = _json_error(exc.status_code, code, str(exc.detail))
        if getattr(exc, "headers", None):
            for key, value in exc.headers.items():
                response.headers[key] = value
        return response

    @app.exception_handler(Exception)
    async def _unexpected(_request: Request, exc: Exception) -> JSONResponse:
        # Log through the redacting filter; never include the stack in the body.
        logger.exception("unhandled error: %s", type(exc).__name__)
        return _json_error(500, "INTERNAL_ERROR", "Internal server error")