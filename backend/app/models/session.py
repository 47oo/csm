"""服务端会话 ORM 模型（F013，ADR-0005）。

严格对应 ``docs/database/csm-v1-schema-design.md`` 的 ``sessions`` 表：

- 列：``id`` / ``user_id`` / ``token_hash`` / ``created_at`` / ``expires_at`` /
  ``last_seen_at``
- 约束：``pk_sessions``、``ux_sessions_token_hash``、``fk_sessions_user``
  （``ON DELETE RESTRICT``）
- 索引：``ix_sessions_user_id``、``ix_sessions_expires_at``

**不使用** ``TimestampMixin``：会话表没有 ``updated_at`` 列，也没有
``deleted_at``（登出 / 过期直接物理删除行）。``last_seen_at`` 保留但**不写入**
（F013 不采用滑动续期，见 ``docs/api/f013-auth.md`` §7）。
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdMixin


class Session(IdMixin, Base):
    __tablename__ = "sessions"

    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(
            "users.id",
            name="fk_sessions_user",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
        nullable=False,
    )
    token_hash: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        UniqueConstraint("token_hash", name="ux_sessions_token_hash"),
        Index("ix_sessions_user_id", "user_id"),
        Index("ix_sessions_expires_at", "expires_at"),
    )

    def __repr__(self) -> str:  # pragma: no cover - 调试辅助
        # 绝不输出 token_hash。
        return f"Session(id={self.id!r}, user_id={self.user_id!r})"
