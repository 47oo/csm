"""认证边界：ASGI 中间件（F013，核心问题 #1）。

**fail-closed 默认保护**：在**路由之前**拦截 ``path == "/api"`` 或
``path.startswith("/api/")``；豁免名单为**精确 ``(method, path)`` 元组匹配**，
唯一成员为 ``("POST", "/api/auth/login")``。

- 未认证访问任何其他 ``/api/*``（含 ``GET /api/auth/login``、``/api/auth/login/``、
  未知路径、未来新增端点、``GET /api/health``）→ ``401 UNAUTHENTICATED``；
- 认证成功 → 写 ``request.state.current_user``；
- 不使用逐路由依赖（那样新端点会 fail-open）。

**不引入** CORS 中间件（契约 §3 的 CSRF 缓解前提）。
"""

from __future__ import annotations

import json
from typing import Any

from starlette.concurrency import run_in_threadpool
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.auth.repository import AuthRepository
from app.auth.schemas import AuthenticatedUser
from app.auth.tokens import hash_session_token
from app.common.errors import error_envelope

COOKIE_NAME = "csm_session"
SESSION_MAX_AGE = 28800  # 与会话绝对有效期一致（8 小时，单位秒）

EXEMPT: set[tuple[str, str]] = {("POST", "/api/auth/login")}

_UNAUTHENTICATED_BODY = json.dumps(error_envelope("UNAUTHENTICATED", "未认证或会话无效")).encode(
    "utf-8"
)


def is_protected_path(path: str) -> bool:
    """``/api`` 前缀下的全部路径均受保护。"""
    return path == "/api" or path.startswith("/api/")


def _parse_cookie(scope: Scope, name: str) -> str | None:
    for key, value in scope.get("headers", []):
        if key == b"cookie":
            for part in value.decode("latin-1").split(";"):
                cookie_name, _, cookie_value = part.strip().partition("=")
                if cookie_name == name:
                    return cookie_value or None
    return None


class AuthMiddleware:
    """纯 ASGI 认证中间件（路由前生效）。"""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope["path"]
        method = scope["method"]
        if not is_protected_path(path) or (method, path) in EXEMPT:
            await self.app(scope, receive, send)
            return

        token = _parse_cookie(scope, COOKIE_NAME)
        current_user: AuthenticatedUser | None = None
        if token:
            current_user = await run_in_threadpool(self._load_user, scope, token)
        if current_user is None:
            await self._send_unauthenticated(send)
            return

        scope.setdefault("state", {})["current_user"] = current_user
        await self.app(scope, receive, send)

    @staticmethod
    def _load_user(scope: Scope, token: str) -> AuthenticatedUser | None:
        session_factory = scope["app"].state.db_sessionmaker
        session = session_factory()
        try:
            user = AuthRepository(session).get_active_user_by_session_token_hash(
                hash_session_token(token)
            )
            if user is None:
                return None
            return AuthenticatedUser(id=user.id, username=user.username)
        finally:
            session.close()

    @staticmethod
    async def _send_unauthenticated(send: Send) -> None:
        message: Message = {
            "type": "http.response.start",
            "status": 401,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(_UNAUTHENTICATED_BODY)).encode("ascii")),
            ],
        }
        await send(message)
        await send({"type": "http.response.body", "body": _UNAUTHENTICATED_BODY})


def current_user_from_state(scope_or_request: Any) -> AuthenticatedUser | None:
    """从 ``request.state`` 读取中间件写入的当前用户（供路由使用）。"""
    return getattr(scope_or_request.state, "current_user", None)
