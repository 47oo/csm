"""统一错误信封与业务异常（docs/api/api-conventions.md §5 / §6）。

信封形状：

```json
{"error": {"code": "VALIDATION_ERROR", "message": "...", "details": []}}
```

``error.code`` 是稳定的机器可读值；前端按 ``code`` 分支，不解析 ``message``。
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ErrorDetail(BaseModel):
    """字段级 / 行级错误明细。``row`` 仅行式请求（导入）使用。"""

    row: int | None = None
    field: str | None = None
    code: str | None = None
    message: str | None = None


class ErrorBody(BaseModel):
    code: str
    message: str
    details: list[ErrorDetail] = Field(default_factory=list)


class ErrorResponse(BaseModel):
    error: ErrorBody


class ApiError(Exception):
    """携带统一信封信息的应用异常。"""

    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        details: list[dict[str, Any]] | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details or []

    def envelope(self) -> dict[str, Any]:
        return error_envelope(self.code, self.message, self.details)


def error_envelope(
    code: str, message: str, details: list[dict[str, Any]] | None = None
) -> dict[str, Any]:
    return {
        "error": {
            "code": code,
            "message": message,
            "details": details or [],
        }
    }


class NotFoundError(ApiError):
    def __init__(
        self,
        message: str = "资源不存在或已被逻辑删除",
        details: list[dict[str, Any]] | None = None,
    ) -> None:
        super().__init__(404, "NOT_FOUND", message, details)


class UnauthenticatedError(ApiError):
    """未认证：未携带凭证 / 凭证无效 / 过期 / 已登出 / 账号已停用。

    F013 的登录失败三情形（用户名不存在、口令错误、账号停用）必须使用**完全
    相同**的本异常，使调用方无法据此判断用户名是否存在（R-AUTH-006）。
    """

    def __init__(self, message: str = "用户名或口令不正确") -> None:
        super().__init__(401, "UNAUTHENTICATED", message)


class ValidationError(ApiError):
    def __init__(
        self,
        message: str = "请求校验失败",
        details: list[dict[str, Any]] | None = None,
    ) -> None:
        super().__init__(400, "VALIDATION_ERROR", message, details)


class ConflictError(ApiError):
    def __init__(
        self,
        message: str = "业务冲突",
        details: list[dict[str, Any]] | None = None,
    ) -> None:
        super().__init__(409, "CONFLICT", message, details)


class InternalError(ApiError):
    def __init__(self, message: str = "服务端错误") -> None:
        super().__init__(500, "INTERNAL_ERROR", message)
