"""Cluster 资源 ORM 模型（F001 的显式资源表，由 F012 基线建立）。

严格对应 ``docs/database/csm-v1-schema-design.md`` 的 ``clusters`` 表：

- 列：``id`` / ``name`` / ``created_at`` / ``updated_at`` / ``deleted_at``
- 约束：``pk_clusters``、``ck_clusters_name_no_slash``
- 索引：``ux_clusters_name_active``（partial unique，``WHERE deleted_at IS NULL``）

F012 只提供表与约束；Cluster 的领域校验 / CRUD / ``by-name`` 属 F001。
"""

from __future__ import annotations

from sqlalchemy import CheckConstraint, Index, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdMixin, SoftDeleteMixin, TimestampMixin


class Cluster(IdMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "clusters"

    name: Mapped[str] = mapped_column(Text, nullable=False)

    __table_args__ = (
        CheckConstraint("strpos(name, '/') = 0", name="name_no_slash"),
        Index(
            "ux_clusters_name_active",
            "name",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )

    def __repr__(self) -> str:  # pragma: no cover - 调试辅助
        return f"Cluster(id={self.id!r}, name={self.name!r})"
