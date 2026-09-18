"""NetworkInterface 资源 ORM 模型（F004 的显式资源表，由 migration ``0005`` 建立）。

严格对应 ``docs/database/f004-network-interface-migration.md`` 的 ``network_interfaces`` 表：

- 列：``id`` / ``bare_metal_id`` / ``name`` / ``technology_type`` / ``purpose`` /
  ``created_at`` / ``updated_at`` / ``deleted_at``（共 **8 列**）；
- 约束：``pk_network_interfaces``、``fk_network_interfaces_bare_metal``
  （``RESTRICT`` / ``RESTRICT``）、``ck_network_interfaces_technology_type``、
  ``ck_network_interfaces_purpose``；
- 索引：``ix_network_interfaces_bare_metal_id``（**唯一索引集合为空**）。

NetworkInterface → BareMetal 为 N:1 mandatory（R-NIC-003）；Cluster 归属由宿主推导、
**不落列**。``name`` 无任何长度 / trim / 字符 / ``/`` 约束（未定义约束「不实现」）。
本模型**无** ``status`` 列、**无** IP / MAC / 速率 / MTU 列、**无**载体多态列，
也不表达任何 NIC 名称唯一性（NQ-2 未确认）。
"""

from __future__ import annotations

from sqlalchemy import BigInteger, CheckConstraint, ForeignKeyConstraint, Index, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdMixin, SoftDeleteMixin, TimestampMixin


class NetworkInterface(IdMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "network_interfaces"

    # R-NIC-003：宿主 BareMetal，必选、恰好一个。
    bare_metal_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    # 接口名（eth0 / ib0 …）；无长度 / trim / 空串 / 字符 / "/" 约束。
    name: Mapped[str] = mapped_column(Text, nullable=False)
    # R-NIC-001：封闭四值。
    technology_type: Mapped[str] = mapped_column(Text, nullable=False)
    # R-NIC-002：封闭七值。
    purpose: Mapped[str] = mapped_column(Text, nullable=False)

    __table_args__ = (
        ForeignKeyConstraint(
            ["bare_metal_id"],
            ["bare_metals.id"],
            ondelete="RESTRICT",
            onupdate="RESTRICT",
            name="fk_network_interfaces_bare_metal",
        ),
        # 命名约定 "ck" = "ck_%(table_name)s_%(constraint_name)s"，故此处传入裸名。
        CheckConstraint(
            "technology_type IN ('Ethernet', 'InfiniBand', 'RoCE', 'Other')",
            name="technology_type",
        ),
        CheckConstraint(
            "purpose IN ('BMC', 'Management', 'Business', 'Compute', "
            "'Storage', 'DataTransfer', 'Other')",
            name="purpose",
        ),
        Index("ix_network_interfaces_bare_metal_id", "bare_metal_id"),
    )

    def __repr__(self) -> str:  # pragma: no cover - 调试辅助
        return (
            f"NetworkInterface(id={self.id!r}, bare_metal_id={self.bare_metal_id!r}, "
            f"name={self.name!r})"
        )
