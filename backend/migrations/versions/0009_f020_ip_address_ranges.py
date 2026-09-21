"""F020：``ip_address_ranges`` 范围段表 + 排它约束不重叠（增量）。

Revision ID: 0009_f020_ip_address_ranges
Revises: 0008_f008_services
Create Date: 2026-09-20

严格对应 ``docs/database/f020-ip-address-range-migration.md`` §3 / §4 DDL 与
``docs/architecture/f020-ip-address-range-handoff.md`` 的裁定：

- **不修改** ``0001``–``0008``；本表是本次**唯一**新增表；
- ``CREATE EXTENSION IF NOT EXISTS btree_gist``（本 Feature 首次引入的 extension，
  使 GiST 支持 ``bigint`` 等值；幂等；**downgrade 不 DROP**，extension 是数据库级
  共享对象，见 F-4）；
- ``ip_address_ranges``：**7 列**（``id`` / ``cluster_id`` / ``start_ip`` /
  ``end_ip`` / ``created_at`` / ``updated_at`` / ``deleted_at``）+ ``pk`` +
  ``fk RESTRICT/RESTRICT`` + ``ck_ip_address_ranges_bounds``；**无** ``status`` /
  ``name`` / ``description`` / CIDR / IPv6 / 分配类列；
- 同 Cluster 活跃范围段不得重叠：``EXCLUDE USING gist``（partial ``WHERE
  deleted_at IS NULL``）为**数据库最终权威**（R-03 / ADR-0002）。``EXCLUDE`` 无法用
  ``sa.CheckConstraint`` 表达，经 ``op.execute`` 以原生 DDL 落地；``ex_`` 不在
  ``NAMING_CONVENTION`` 中，约束名**按字面**使用（F-2）；
- ``ix_ip_address_ranges_cluster_id`` btree 索引（FK 引用完整性检查 + 含已删行的按
  Cluster 查询；partial GiST 索引不能替代，F-3）；
- **无** 触发器 / 生成列 / ``CASCADE`` / 复合外键 / 数据迁移；**无** 第二条写
  ``deleted_at`` 的路径。

CHECK 约束传**裸名** ``"bounds"``，由命名约定生成 ``ck_ip_address_ranges_bounds``；
直接传全名会产生双重前缀（F-1）。
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0009_f020_ip_address_ranges"
down_revision: str | None = "0008_f008_services"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 0) 扩展：GiST 上支持 bigint 等值（幂等；必须先于 EXCLUDE）。
    op.execute("CREATE EXTENSION IF NOT EXISTS btree_gist")

    # 1) 表（7 列；PK + FK RESTRICT/RESTRICT + CHECK）。
    op.create_table(
        "ip_address_ranges",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        # 归属 Cluster（R-IP-004：恰属一个活跃 Cluster）。
        sa.Column("cluster_id", sa.BigInteger(), nullable=False),
        # IPv4 canonical 数值（0..4294967295），闭区间含端点（P-01）。
        sa.Column("start_ip", sa.BigInteger(), nullable=False),
        sa.Column("end_ip", sa.BigInteger(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_ip_address_ranges"),
        sa.ForeignKeyConstraint(
            ["cluster_id"],
            ["clusters.id"],
            name="fk_ip_address_ranges_cluster",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
        sa.CheckConstraint(
            "start_ip BETWEEN 0 AND 4294967295 "
            "AND end_ip BETWEEN 0 AND 4294967295 "
            "AND start_ip <= end_ip",
            name="bounds",
        ),
    )

    # 2) 同 Cluster 活跃范围段不得重叠（数据库最终权威；partial predicate 释放软删行）。
    op.execute(
        "ALTER TABLE ip_address_ranges "
        "ADD CONSTRAINT ex_ip_address_ranges_active_no_overlap "
        "EXCLUDE USING gist ("
        "cluster_id WITH =, "
        "(int8range(start_ip, end_ip, '[]')) WITH &&"
        ") WHERE (deleted_at IS NULL)"
    )

    # 3) FK 引用完整性检查 + 按 Cluster 读取（含已删行）。
    op.create_index("ix_ip_address_ranges_cluster_id", "ip_address_ranges", ["cluster_id"])


def downgrade() -> None:
    # 与 upgrade 严格逆序；破坏性（丢失全部范围段登记历史），生产禁止。
    op.drop_index("ix_ip_address_ranges_cluster_id", table_name="ip_address_ranges")
    # drop_table 连带删除 PK / FK / CHECK / EXCLUDE 及其 backing GiST 索引。
    op.drop_table("ip_address_ranges")
    # 不 DROP EXTENSION btree_gist（F-4）：extension 为数据库级共享对象。
