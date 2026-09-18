"""认证 HTTP 路由（F013，docs/api/f013-auth.md §5）。

3 个端点挂载于 ``/api`` 前缀下（由 ``app.main`` 挂载）：

- ``POST /api/auth/login``：**唯一认证豁免端点**；
- ``POST /api/auth/logout``：受认证保护（失效会话返回 401）；
- ``GET /api/auth/session``：受认证保护。

Cookie 契约（契约 §3）：``csm_session`` + ``HttpOnly`` + ``SameSite=Lax`` +
**不设 ``Secure``** + ``Path=/api`` + 不设 ``Domain`` + ``Max-Age=28800``。
令牌值不得出现在响应体 / 日志中。
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy.orm import Session

from app.api.deps import get_db_session
from app.auth import service
from app.auth.middleware import (
    COOKIE_NAME,
    SESSION_MAX_AGE,
    current_user_from_state,
)
from app.auth.schemas import AuthenticatedUser, LoginRequest
from app.common.errors import UnauthenticatedError

router = APIRouter(prefix="/auth", tags=["auth"])

SessionDep = Annotated[Session, Depends(get_db_session)]


def _set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        max_age=SESSION_MAX_AGE,
        path="/api",
        httponly=True,
        samesite="lax",
        secure=False,
        # 不设 domain：host-only。
    )


def _clear_session_cookie(response: Response) -> None:
    response.delete_cookie(
        key=COOKIE_NAME,
        path="/api",
        httponly=True,
        samesite="lax",
        secure=False,
    )


@router.post("/login", response_model=AuthenticatedUser)
def login(payload: LoginRequest, response: Response, session: SessionDep) -> AuthenticatedUser:
    """登录：凭据正确 → 200 + ``Set-Cookie``；否则统一 401。"""
    user = service.authenticate(session, payload.username, payload.password)
    token = service.establish_session(session, user)
    _set_session_cookie(response, token)
    return AuthenticatedUser.model_validate(user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(request: Request, session: SessionDep) -> Response:
    """登出：物理删除当前会话行并清除 Cookie（会话失效时为 401，由中间件返回）。"""
    service.logout(session, request.cookies.get(COOKIE_NAME))
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    _clear_session_cookie(response)
    return response


@router.get("/session", response_model=AuthenticatedUser)
def get_current_session(request: Request) -> AuthenticatedUser:
    """返回当前已认证身份；无有效会话时由中间件返回 401。"""
    current_user = current_user_from_state(request)
    if current_user is None:
        # 理论上不可达（中间件已拦截）；保持 fail-closed。
        raise UnauthenticatedError()
    return current_user
