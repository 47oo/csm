"""认证数据访问（F013）。

用户名查找**必须**是字面值等值比较：**禁止** ``lower()`` / ``ILIKE`` / 任何大小写
折叠（R-AUTH-005）。会话校验条件 = ``token_hash`` 命中 **AND** ``expires_at >
now()`` **AND** ``users.active = true``。

认证表**不是资源表**，不使用 ``deleted_at IS NULL`` 过滤原语——它们没有
``deleted_at`` 列。
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.models.session import Session as SessionModel
from app.models.user import User


class AuthRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_user_by_username(self, username: str) -> User | None:
        """按用户名**原样精确匹配**（大小写敏感，R-AUTH-005）。"""
        stmt = select(User).where(User.username == username)
        return self.session.scalars(stmt).one_or_none()

    def get_active_user_by_session_token_hash(self, token_hash: str) -> User | None:
        """返回持有该有效会话的活跃账号；否则 ``None``。

        有效条件（契约 §7）：``token_hash`` 命中 AND 未过期 AND ``active``。
        """
        stmt = (
            select(User)
            .join(SessionModel, SessionModel.user_id == User.id)
            .where(
                SessionModel.token_hash == token_hash,
                SessionModel.expires_at > func.now(),
                User.active.is_(True),
            )
        )
        return self.session.scalars(stmt).one_or_none()

    def create_session(
        self, *, user_id: int, token_hash: str, expires_at: datetime
    ) -> SessionModel:
        session_row = SessionModel(user_id=user_id, token_hash=token_hash, expires_at=expires_at)
        self.session.add(session_row)
        self.session.flush()
        return session_row

    def delete_session_by_token_hash(self, token_hash: str) -> None:
        self.session.execute(delete(SessionModel).where(SessionModel.token_hash == token_hash))

    def delete_expired_sessions(self) -> None:
        """惰性物理清理已过期会话（无后台 worker）。"""
        self.session.execute(delete(SessionModel).where(SessionModel.expires_at <= func.now()))
