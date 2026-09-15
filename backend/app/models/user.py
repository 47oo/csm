"""认证账号 ORM 模型（F013，ADR-0005）。

严格对应 ``docs/database/csm-v1-schema-design.md`` 的 ``users`` 表：

- 列：``id`` / ``username`` / ``password_hash`` / ``active`` / ``created_at`` /
  ``updated_at``
- 约束：``pk_users``、``ux_users_username``（普通 UNIQUE，**不使用**
  ``lower(username)`` 表达式索引）

**认证表不是资源表**：没有 ``deleted_at``，不停用资源逻辑删除语义；账号停用由
``active`` 表达。也**没有**角色 / 权限 / RBAC 相关列（R-AUTH-003）。
"""

from __future__ import annotations

from sqlalchemy import Boolean, Text, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdMixin, TimestampMixin


class User(IdMixin, TimestampMixin, Base):
    __tablename__ = "users"

    username: Mapped[str] = mapped_column(Text, nullable=False)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))

    __table_args__ = (UniqueConstraint("username", name="ux_users_username"),)

    def __repr__(self) -> str:  # pragma: no cover - 调试辅助
        # 绝不输出 password_hash。
        return f"User(id={self.id!r}, username={self.username!r}, active={self.active!r})"
