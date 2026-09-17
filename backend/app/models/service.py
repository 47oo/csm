"""Service 资源 ORM 模型（F008 的显式资源表，由 migration ``0008`` 建立）。

严格对应 ``docs/database/f008-service-migration.md`` 的 ``services`` 表：

- 列：``id`` / ``name`` / ``service_type`` / ``url`` / ``port`` / ``protocol`` /
  ``owner`` / ``description`` / ``created_at`` / ``updated_at`` / ``deleted_at``
  （共 **11 列**）；
- 约束：**恰有 1 个约束**（``pk_services``），**无任何 CHECK**（AC-15 未定义约束
  不落 CHECK）；
- 索引：``ux_services_name_active``（partial unique，``WHERE deleted_at IS NULL``，
  大小写敏感，不声明 ``COLLATE``、不使用 ``lower()``）。

**明确不存在**：``status`` / ``state``（Q-002=B 无状态）、``cluster_id`` /
``cluster`` / ``cluster_name``（R-SVC-004/006 归属由载体推导）、凭据 / 健康 /
监控 / 发现 / 位置列、任何载体列（载体绑定由独立关系表 ``service_carriers`` 承载）。

``name`` 与 6 个可选字段无任何长度 / trim / 空串 / 字符 / 格式约束
（R-SVC-001 / R-SVC-007 / AC-15）。
"""

from __future__ import annotations

from sqlalchemy import Index, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdMixin, SoftDeleteMixin, TimestampMixin


class Service(IdMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "services"

    # R-SVC-008：身份标识；全局活跃唯一、区分大小写；无长度 / trim / 空串约束。
    name: Mapped[str] = mapped_column(Text, nullable=False)

    # R-SVC-001 / R-SVC-007：6 个可选纯文本字段，允许 NULL、不结构化。
    service_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    url: Mapped[str | None] = mapped_column(Text, nullable=True)
    port: Mapped[str | None] = mapped_column(Text, nullable=True)
    protocol: Mapped[str | None] = mapped_column(Text, nullable=True)
    owner: Mapped[str | None] = mapped_column(Text, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        Index(
            "ux_services_name_active",
            "name",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )

    def __repr__(self) -> str:  # pragma: no cover - 调试辅助
        return f"Service(id={self.id!r}, name={self.name!r})"
