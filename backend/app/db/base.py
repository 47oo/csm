"""Declarative base、横切列 mixin 与命名约定。

模块边界基座（架构 Backend Work #2）：
- 每类资源 = 独立模块 + 独立表；
- 仅允许 ``id`` / ``created_at`` / ``updated_at`` / ``deleted_at`` 这类横切列的
  mixin 复用，**不**建立通用 Resource ORM 基类。
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Identity, MetaData, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# 与 docs/database/f012-baseline-migration.md §5.2 完全一致的命名约定。
NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "ux_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_N_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class IdMixin:
    """不可变代理主键（ADR-0003）。"""

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)


class TimestampMixin:
    """登记 / 更新时间。``updated_at`` 由应用层维护（DB 设计决策 8）。

    数据库列只有 ``DEFAULT now()``，无触发器；``onupdate`` 由 SQLAlchemy 在 ORM
    UPDATE 时发出 ``now()``。因此绕过 ORM 的裸 SQL 写入不会更新 ``updated_at``，
    ``updated_at`` 不得作为审计或并发控制依据。
    """

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class SoftDeleteMixin:
    """逻辑删除标记（ADR-0004）：``deleted_at IS NULL`` 表示活跃。"""

    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
