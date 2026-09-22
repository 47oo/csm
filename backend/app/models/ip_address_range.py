"""IPAddressRange 资源 ORM 模型（F020 建立，F022 扩展元数据字段）。

严格对应 ``docs/database/f020-ip-address-range-migration.md``（F020）与
``docs/database/f022-ip-address-range-metadata-migration.md``（F022）的
``ip_address_ranges`` 表：

- 列（F022 扩展后恰 **10 列**）：``id`` / ``cluster_id`` / ``start_ip`` / ``end_ip`` /
  ``created_at`` / ``updated_at`` / ``deleted_at`` + ``name`` / ``subnet_mask`` / ``vlan``；
  **无** ``status`` / ``description`` / CIDR / IPv6 / 网关 / DHCP / DNS / 使用率列；
- 约束：``pk_ip_address_ranges``、``fk_ip_address_ranges_cluster``
  （``RESTRICT`` / ``RESTRICT``）、``ck_ip_address_ranges_bounds``（数值域 +
  ``start_ip <= end_ip``）、``ck_ip_address_ranges_vlan_range``（``vlan`` 1..4094）、
  ``ex_ip_address_ranges_active_no_overlap``（``EXCLUDE USING gist``，partial
  ``WHERE deleted_at IS NULL``）；
- 索引：``ix_ip_address_ranges_cluster_id``（btree）与 ``ux_ip_address_ranges_cluster_name_active``
  （partial unique ``(cluster_id, name) WHERE deleted_at IS NULL AND name IS NOT NULL``）。

``start_ip`` / ``end_ip`` 以 IPv4 canonical 数值（``BIGINT``，``0..4294967295``）存储；
API 层渲染为 dotted-quad。规范化由 ``app/ip_address_ranges/ipv4.py`` 的单一纯函数实现。
``name`` / ``subnet_mask`` 以 ``TEXT`` 原样存取（长度 / trim / 空串 / 字符集未定义，不实现）；
``EXCLUDE`` 与 ``name`` partial unique 均为**数据库最终权威**（ADR-0002 / ADR-0004）；本模型以
等价的 SQLAlchemy 声明表达，确保 ``alembic check`` 无漂移（F-6）；**不得**让 autogenerate
误删 / 重建该 partial unique index。
"""

from __future__ import annotations

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    ForeignKeyConstraint,
    Index,
    Integer,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ExcludeConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdMixin, SoftDeleteMixin, TimestampMixin


class IpAddressRange(IdMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "ip_address_ranges"

    # 归属 Cluster（N:1 mandatory；恰属一个活跃 Cluster）。
    cluster_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    # IPv4 canonical 数值（0..4294967295），闭区间含两端。
    start_ip: Mapped[int] = mapped_column(BigInteger, nullable=False)
    end_ip: Mapped[int] = mapped_column(BigInteger, nullable=False)
    # F022 元数据：网段自定义名称（同 Cluster 活跃唯一、区分大小写、原样存取）。
    name: Mapped[str | None] = mapped_column(Text, nullable=True)
    # F022 元数据：dotted-quad IPv4 合法掩码（原样存取；合法性由应用层单实现裁决）。
    subnet_mask: Mapped[str | None] = mapped_column(Text, nullable=True)
    # F022 元数据：VLAN 标注 1..4094（不唯一；DB CHECK 兜底）。
    vlan: Mapped[int | None] = mapped_column(Integer, nullable=True)

    __table_args__ = (
        ForeignKeyConstraint(
            ["cluster_id"],
            ["clusters.id"],
            ondelete="RESTRICT",
            onupdate="RESTRICT",
            name="fk_ip_address_ranges_cluster",
        ),
        CheckConstraint(
            "start_ip BETWEEN 0 AND 4294967295 "
            "AND end_ip BETWEEN 0 AND 4294967295 "
            "AND start_ip <= end_ip",
            name="bounds",
        ),
        # F022：vlan 限域兜底；裸名 "vlan_range" → ck_ip_address_ranges_vlan_range。
        CheckConstraint(
            "vlan IS NULL OR (vlan BETWEEN 1 AND 4094)",
            name="vlan_range",
        ),
        # R-IP-004：同 Cluster 活跃范围段不得重叠（跨 Cluster 可重复）的最终权威。
        ExcludeConstraint(
            ("cluster_id", "="),
            (func.int8range(text("start_ip"), text("end_ip"), text("'[]'")), "&&"),
            using="gist",
            name="ex_ip_address_ranges_active_no_overlap",
            where=text("deleted_at IS NULL"),
        ),
        Index("ix_ip_address_ranges_cluster_id", "cluster_id"),
        # F022：同 Cluster 活跃 name 唯一（区分大小写；软删 / 未命名行释放）。
        Index(
            "ux_ip_address_ranges_cluster_name_active",
            "cluster_id",
            "name",
            unique=True,
            postgresql_where=text("deleted_at IS NULL AND name IS NOT NULL"),
        ),
    )

    def __repr__(self) -> str:  # pragma: no cover - 调试辅助
        return (
            f"IpAddressRange(id={self.id!r}, cluster_id={self.cluster_id!r}, "
            f"start_ip={self.start_ip!r}, end_ip={self.end_ip!r})"
        )
