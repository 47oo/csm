"""IPAddress 资源 ORM 模型（F005 的显式资源表，由 migration ``0006`` 建立）。

严格对应 ``docs/database/f005-ip-address-migration.md`` 的 ``ip_addresses`` 表：

- 列：``id`` / ``network_interface_id`` / ``cluster_id`` / ``ip_address`` /
  ``created_at`` / ``updated_at`` / ``deleted_at``（共 **7 列**）；
- 约束：``pk_ip_addresses``、``fk_ip_addresses_network_interface``
  （``RESTRICT`` / ``RESTRICT``）、``fk_ip_addresses_cluster``
  （``RESTRICT`` / ``RESTRICT``）；**CHECK 约束集合为空**；
- 索引：``ux_ip_addresses_cluster_ip_active``（partial unique，
  ``(cluster_id, ip_address) WHERE deleted_at IS NULL``）、
  ``ix_ip_addresses_cluster_id``、``ix_ip_addresses_network_interface_id``。

IPAddress → NetworkInterface 为 N:1 mandatory（用户 2026-09-15 裁定）。``cluster_id``
是**受控推导的反规范化列**：只能由 ``app/ip_addresses/derivation.py::derive_cluster_id``
推导、经 ``IpAddressRepository.create`` 写入；数据库层**不**保证其与链路一致
（ADR-0002 已知取舍，由漂移检测回归保证）。``ip_address`` 无任何长度 / trim / 格式 /
归一化约束（NQ-1「不实现」）。本模型**无** ``status`` 列、**无** VRF / IP 池 /
DHCP / DNS / 自动发现 / 载体多态列。
"""

from __future__ import annotations

from sqlalchemy import BigInteger, ForeignKeyConstraint, Index, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdMixin, SoftDeleteMixin, TimestampMixin


class IpAddress(IdMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "ip_addresses"

    # 直接父 NetworkInterface，必选、恰好一个（N:1 mandatory）。
    network_interface_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    # 反规范化：唯一性边界（ADR-0002）；由领域服务推导写入，调用方不可赋值。
    cluster_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    # IP 字面值；无长度 / trim / 空串 / 格式 / 归一化约束。
    ip_address: Mapped[str] = mapped_column(Text, nullable=False)

    __table_args__ = (
        ForeignKeyConstraint(
            ["network_interface_id"],
            ["network_interfaces.id"],
            ondelete="RESTRICT",
            onupdate="RESTRICT",
            name="fk_ip_addresses_network_interface",
        ),
        ForeignKeyConstraint(
            ["cluster_id"],
            ["clusters.id"],
            ondelete="RESTRICT",
            onupdate="RESTRICT",
            name="fk_ip_addresses_cluster",
        ),
        # R-IP-001：同 Cluster 内字面唯一（活跃范围内）。
        Index(
            "ux_ip_addresses_cluster_ip_active",
            "cluster_id",
            "ip_address",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index("ix_ip_addresses_cluster_id", "cluster_id"),
        Index("ix_ip_addresses_network_interface_id", "network_interface_id"),
    )

    def __repr__(self) -> str:  # pragma: no cover - 调试辅助
        return (
            f"IpAddress(id={self.id!r}, network_interface_id={self.network_interface_id!r}, "
            f"ip_address={self.ip_address!r})"
        )
