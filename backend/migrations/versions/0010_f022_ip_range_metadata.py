"""F022：``ip_address_ranges`` 元数据字段（``name`` / ``subnet_mask`` / ``vlan``）。

Revision ID: 0010_f022_ip_range_metadata
Revises: 0009_f020_ip_address_ranges
Create Date: 2026-09-21

严格对应 ``docs/database/f022-ip-address-range-metadata-migration.md`` §3 / §4 DDL：

- **纯增量扩展既有表**：``ALTER TABLE ip_address_ranges ADD COLUMN`` 3 个可空列
  （``name TEXT NULL`` / ``subnet_mask TEXT NULL`` / ``vlan INTEGER NULL``）；既有行
  取 ``NULL``，**无回填、无数据迁移**；``ADD COLUMN … NULL`` 为元数据级操作；
- ``name`` 同 Cluster 活跃唯一：``CREATE UNIQUE INDEX
  ux_ip_address_ranges_cluster_name_active ON ip_address_ranges (cluster_id, name)
  WHERE deleted_at IS NULL AND name IS NOT NULL``（大小写敏感，**不**声明 ``COLLATE``、
  **不**用 ``lower()``）——最终权威（ADR-0002 / ADR-0004）；
- ``vlan`` 限域：``ck_ip_address_ranges_vlan_range CHECK (vlan IS NULL OR (vlan
  BETWEEN 1 AND 4094))``；``name`` / ``subnet_mask`` **不**加格式 / 长度 / 字符集 CHECK；
- **不修改** ``0001``–``0009``、既有列 / 约束 / 索引、其它表；**无** extension / 触发器 /
  ``CASCADE`` / 生成列 / 第二条写 ``deleted_at`` 的路径；
- ``downgrade`` 严格逆序（丢弃 3 个元数据列的值，核心范围段行保留）。

CHECK 约束传**裸名** ``"vlan_range"``，由命名约定生成 ``ck_ip_address_ranges_vlan_range``；
直接传全名会产生双重前缀（F-1）。``ux_`` 前缀**按字面**使用，不经过 ``uq`` 命名约定。
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0010_f022_ip_range_metadata"
down_revision: str | None = "0009_f020_ip_address_ranges"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1) 3 个可空列（元数据级 ALTER，不重写表；既有行取 NULL，无回填；不设 server_default）。
    op.add_column("ip_address_ranges", sa.Column("name", sa.Text(), nullable=True))
    op.add_column("ip_address_ranges", sa.Column("subnet_mask", sa.Text(), nullable=True))
    op.add_column("ip_address_ranges", sa.Column("vlan", sa.Integer(), nullable=True))

    # 2) 同 Cluster 活跃范围段 name 唯一（区分大小写；软删 / 未命名行释放）。
    op.create_index(
        "ux_ip_address_ranges_cluster_name_active",
        "ip_address_ranges",
        ["cluster_id", "name"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL AND name IS NOT NULL"),
    )

    # 3) vlan 限域兜底（应用层另有 400）。裸名 "vlan_range" → ck_ip_address_ranges_vlan_range。
    op.create_check_constraint(
        "vlan_range",
        "ip_address_ranges",
        "vlan IS NULL OR (vlan BETWEEN 1 AND 4094)",
    )


def downgrade() -> None:
    # 与 upgrade 严格逆序；破坏性（丢失 3 个元数据列的值），生产禁止。
    op.drop_index("ux_ip_address_ranges_cluster_name_active", table_name="ip_address_ranges")
    # drop_constraint 同 create_check_constraint 一样应用命名约定：传**裸名** ``"vlan_range"``
    # 生成 ``ck_ip_address_ranges_vlan_range``；传全名会产生双重前缀。
    op.drop_constraint("vlan_range", "ip_address_ranges", type_="check")
    op.drop_column("ip_address_ranges", "vlan")
    op.drop_column("ip_address_ranges", "subnet_mask")
    op.drop_column("ip_address_ranges", "name")
    # 不 DROP EXTENSION btree_gist：F020 引入的数据库级共享对象保持不动。