"""复用的操作者解析与鉴权依赖（架构 §2.2）。

`get_current_user` 每个受保护请求从服务端会话解析操作者，并且每次从数据库
读取角色与状态，保证角色变更即时生效、禁用后立即不可用。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from fastapi import Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..errors import problem
from ..models import User, UserSession
from ..security.tokens import sha256_hex

PASSWORD_CHANGE_ALLOWED: frozenset[tuple[str, str]] = frozenset(
    {
        ("GET", "/api/v1/auth/me"),
        ("POST", "/api/v1/auth/change-password"),
        ("POST", "/api/v1/auth/logout"),
    }
)


@dataclass(frozen=True)
class Principal:
    user_id: int
    username: str
    role: str
    must_change_password: bool
    status: str


def get_current_user(request: Request, db: Session = Depends(get_db)) -> Principal:
    from ..config import settings

    token = request.cookies.get(settings.cookie_name)
    if not token:
        raise problem(401, "UNAUTHENTICATED", "未认证或会话已失效")

    token_hash = sha256_hex(token)
    now = datetime.now(timezone.utc)
    row = db.execute(
        select(UserSession, User)
        .join(User, UserSession.user_id == User.id)
        .where(
            UserSession.token_hash == token_hash,
            UserSession.revoked_at.is_(None),
            UserSession.expires_at > now,
        )
    ).first()

    if row is None:
        raise problem(401, "UNAUTHENTICATED", "未认证或会话已失效")

    user_session, user = row
    if user.status != "enabled":
        raise problem(401, "UNAUTHENTICATED", "未认证或会话已失效")

    if user.must_change_password and (
        request.method,
        request.url.path,
    ) not in PASSWORD_CHANGE_ALLOWED:
        raise problem(
            403,
            "PASSWORD_CHANGE_REQUIRED",
            "首次登录须先修改初始口令",
        )

    user_session.last_seen_at = now
    db.commit()

    return Principal(
        user_id=user.id,
        username=user.username,
        role=user.role,
        must_change_password=user.must_change_password,
        status=user.status,
    )


def require_roles(*roles: str):
    def dependency(user: Principal = Depends(get_current_user)) -> Principal:
        if user.role not in roles:
            raise problem(403, "FORBIDDEN", "权限不足")
        return user

    return dependency