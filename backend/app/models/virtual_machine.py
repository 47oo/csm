"""VirtualMachine 资源 ORM 模型（F006 的显式资源表，由 migration ``0004`` 建立）。

严格对应 ``docs/database/f006-virtual-machine-migration.md`` 的 ``virtual_machines`` 表：

- 列：``id`` / ``bare_metal_id`` / ``name`` / ``cpu`` / ``memory`` / ``disk`` /
  ``os`` / ``hypervisor`` / ``owner`` / ``created_at`` / ``updated_at`` / ``deleted_at``
  （共 **12 列**）；**无** ``status`` 列、**无** ``cluster_id`` 列；
- 约束：``pk_virtual_machines``、``fk_virtual_machines_bare_metal``
  （``RESTRICT`` / ``RESTRICT``）；
- 索引：``ux_virtual_machines_name_active``（partial unique，
  ``WHERE deleted_at IS NULL``，全局、大小写敏感）、``ix_virtual_machines_bare_metal_id``。

VirtualMachine → BareMetal 为 N:1 mandatory（R-VM-005）；Cluster 归属由宿主推导、
**不落列**。``name`` 与六个可选字段无任何长度 / trim / 字符 / ``/`` 约束
（R-VM-006、未定义约束「不实现」），不声明 ``COLLATE``、不使用 ``lower()``。
"""

from __future__ import annotations

from sqlalchemy import BigInteger, ForeignKeyConstraint, Index, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdMixin, SoftDeleteMixin, TimestampMixin


class VirtualMachine(IdMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "virtual_machines"

    # R-VM-005：宿主 BareMetal，必选、恰好一个。
    bare_metal_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    # R-VM-004：身份标识；无长度 / trim / 空串 / 字符 / "/" 约束。
    name: Mapped[str] = mapped_column(Text, nullable=False)

    # R-VM-006：六个可选、纯文本、允许 NULL；不结构化、不参与唯一性。
    cpu: Mapped[str | None] = mapped_column(Text, nullable=True)
    memory: Mapped[str | None] = mapped_column(Text, nullable=True)
    disk: Mapped[str | None] = mapped_column(Text, nullable=True)
    os: Mapped[str | None] = mapped_column(Text, nullable=True)
    hypervisor: Mapped[str | None] = mapped_column(Text, nullable=True)
    owner: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        ForeignKeyConstraint(
            ["bare_metal_id"],
            ["bare_metals.id"],
            ondelete="RESTRICT",
            onupdate="RESTRICT",
            name="fk_virtual_machines_bare_metal",
        ),
        Index(
            "ux_virtual_machines_name_active",
            "name",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index("ix_virtual_machines_bare_metal_id", "bare_metal_id"),
    )

    def __repr__(self) -> str:  # pragma: no cover - 调试辅助
        return (
            f"VirtualMachine(id={self.id!r}, bare_metal_id={self.bare_metal_id!r}, "
            f"name={self.name!r})"
        )
