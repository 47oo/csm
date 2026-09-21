"""IPAddressRange 资源 ORM 模型（F020 的显式资源表，由 migration ``0009`` 建立）。

严格对应 ``docs/database/f020-ip-address-range-migration.md`` 的 ``ip_address_ranges``
表：

- 列：``id`` / ``cluster_id`` / ``start_ip`` / ``end_ip`` / ``created_at`` /
  ``updated_at`` / ``deleted_at``（共 **7 列**）；**无** ``status`` / ``name`` /
  ``description`` / CIDR / IPv6 / 分配类列；
- 约束：``pk_ip_address_ranges``、``fk_ip_address_ranges_cluster``
  （``RESTRICT`` / ``RESTRICT``）、``ck_ip_address_ranges_bounds``（数值域 +
  ``start_ip <= end_ip``）、``ex_ip_address_ranges_active_no_overlap``
  （``EXCLUDE USING gist``，partial ``WHERE deleted_at IS NULL``）；
- 索引：``ix_ip_address_ranges_cluster_id``（btree）。

``start_ip`` / ``end_ip`` 以 IPv4 canonical 数值（``BIGINT``，``0..4294967295``）存储；
API 层渲染为 dotted-quad。规范化由 ``app/ip_address_ranges/ipv4.py`` 的单一纯函数实现。
``EXCLUDE`` 为「同 Cluster 活跃范围段不重叠」的**数据库最终权威**（ADR-0002）；
本模型以等价的 :class:`~sqlalchemy.dialects.postgresql.ExcludeConstraint` 声明，
确保 ``alembic check`` 无漂移（F-6）。
"""

from __future__ import annotations

from sqlalchemy import BigInteger, CheckConstraint, ForeignKeyConstraint, Index, func, text
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
        # R-IP-004：同 Cluster 活跃范围段不得重叠（跨 Cluster 可重复）的最终权威。
        ExcludeConstraint(
            ("cluster_id", "="),
            (func.int8range(text("start_ip"), text("end_ip"), text("'[]'")), "&&"),
            using="gist",
            name="ex_ip_address_ranges_active_no_overlap",
            where=text("deleted_at IS NULL"),
        ),
        Index("ix_ip_address_ranges_cluster_id", "cluster_id"),
    )

    def __repr__(self) -> str:  # pragma: no cover - 调试辅助
        return (
            f"IpAddressRange(id={self.id!r}, cluster_id={self.cluster_id!r}, "
            f"start_ip={self.start_ip!r}, end_ip={self.end_ip!r})"
        )
