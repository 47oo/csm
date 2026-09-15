"""FastAPI 异常处理器：把各类异常统一翻译为契约错误信封。"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.common.errors import ApiError, error_envelope
from app.common.sqlstate import map_integrity_error

logger = logging.getLogger("csm.errors")

# 路由层 HTTPException → error.code 的兜底映射。
_HTTP_STATUS_CODE_MAP: dict[int, str] = {
    400: "VALIDATION_ERROR",
    401: "UNAUTHENTICATED",
    403: "FORBIDDEN",
    404: "NOT_FOUND",
    409: "CONFLICT",
    500: "INTERNAL_ERROR",
}


def _json(status_code: int, code: str, message: str, details: list[dict[str, Any]] | None = None):
    return JSONResponse(status_code=status_code, content=error_envelope(code, message, details))


async def api_error_handler(_: Request, exc: ApiError) -> JSONResponse:
    return _json(exc.status_code, exc.code, exc.message, exc.details)


async def validation_error_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
    details: list[dict[str, Any]] = []
    for error in exc.errors():
        loc = [str(part) for part in error.get("loc", ()) if part not in ("body", "query", "path")]
        details.append(
            {
                "field": ".".join(loc) or None,
                "code": "INVALID",
                "message": error.get("msg"),
            }
        )
    return _json(400, "VALIDATION_ERROR", "请求校验失败", details)


async def integrity_error_handler(_: Request, exc: IntegrityError) -> JSONResponse:
    mapped = map_integrity_error(exc)
    if mapped is None:
        logger.exception("未识别的数据库完整性错误")
        return _json(500, "INTERNAL_ERROR", "服务端错误")
    status_code, code, details = mapped
    return _json(status_code, code, "数据完整性冲突", details)


async def http_exception_handler(_: Request, exc: StarletteHTTPException) -> JSONResponse:
    code = _HTTP_STATUS_CODE_MAP.get(exc.status_code, "INTERNAL_ERROR")
    message = exc.detail if isinstance(exc.detail, str) else code
    return _json(exc.status_code, code, message)


async def unhandled_exception_handler(_: Request, exc: Exception) -> JSONResponse:
    logger.exception("未处理异常", exc_info=exc)
    return _json(500, "INTERNAL_ERROR", "服务端错误")


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(ApiError, api_error_handler)
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    app.add_exception_handler(IntegrityError, integrity_error_handler)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)
