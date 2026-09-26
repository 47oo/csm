"""FastAPI 应用入口。"""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from .auth.router import router as auth_router
from .errors import ProblemException, problem_body
from .users.router import router as users_router

logger = logging.getLogger("csm")

app = FastAPI(title="CSM API", version="0.1.0")

PROBLEM_MEDIA_TYPE = "application/problem+json"


@app.exception_handler(ProblemException)
async def problem_handler(_request: Request, exc: ProblemException) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content=problem_body(exc),
        media_type=PROBLEM_MEDIA_TYPE,
        headers=exc.headers or None,
    )


@app.exception_handler(RequestValidationError)
async def validation_handler(
    _request: Request, exc: RequestValidationError
) -> JSONResponse:
    errors = []
    for error in exc.errors():
        loc = [str(part) for part in error.get("loc", []) if part not in ("body", "query", "path")]
        field = ".".join(loc) if loc else "request"
        errors.append(
            {
                "field": field,
                "code": "INVALID",
                "message": error.get("msg", "字段校验失败"),
            }
        )
    return JSONResponse(
        status_code=422,
        content={
            "type": "about:blank",
            "title": "VALIDATION_ERROR",
            "status": 422,
            "code": "VALIDATION_ERROR",
            "message": "字段校验失败",
            "errors": errors,
        },
        media_type=PROBLEM_MEDIA_TYPE,
    )


@app.exception_handler(Exception)
async def unhandled_handler(_request: Request, exc: Exception) -> JSONResponse:
    logger.exception("unhandled error", exc_info=exc)
    return JSONResponse(
        status_code=500,
        content={
            "type": "about:blank",
            "title": "INTERNAL_ERROR",
            "status": 500,
            "code": "INTERNAL_ERROR",
            "message": "服务器内部错误",
        },
        media_type=PROBLEM_MEDIA_TYPE,
    )


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


app.include_router(auth_router, prefix="/api/v1")
app.include_router(users_router, prefix="/api/v1")