"""统一错误响应：application/problem+json（ADR-003 / Contract）。"""

from __future__ import annotations

from typing import Any


class ProblemException(Exception):
    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        errors: list[dict[str, Any]] | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.errors = errors
        self.headers = headers or {}


def problem(
    status_code: int,
    code: str,
    message: str,
    errors: list[dict[str, Any]] | None = None,
    headers: dict[str, str] | None = None,
) -> ProblemException:
    return ProblemException(status_code, code, message, errors, headers)


def problem_body(problem_exc: ProblemException) -> dict[str, Any]:
    body: dict[str, Any] = {
        "type": "about:blank",
        "title": problem_exc.code,
        "status": problem_exc.status_code,
        "code": problem_exc.code,
        "message": problem_exc.message,
    }
    if problem_exc.errors is not None:
        body["errors"] = problem_exc.errors
    return body