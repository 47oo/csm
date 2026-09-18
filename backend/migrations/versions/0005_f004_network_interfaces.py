"""F004：``network_interfaces`` 表 + FK RESTRICT + 两个封闭枚举 CHECK + 宿主索引（增量）。

Revision ID: 0005_f004_network_interfaces
Revises: 0004_f006_virtual_machines
Create Date: 2026-09-17

严格对应 ``docs/database/f004-network-interface-migration.md`` 的 ``network_interfaces`` 段：

- **不修改** ``0001_f012_baseline`` / ``0002_f013_auth`` / ``0003_f002_bare_metals`` /
  ``0004_f006_virtual_machines``；
- 一条 ``CREATE TABLE`` 建齐 **8 列**（``bare_metal_id NOT NULL`` + ``name NOT NULL``
  + 两个封闭枚举列 + 时间列 + ``deleted_at``）；**无** ``status`` 列、**无** ``cluster_id`` 列；
- ``fk_network_interfaces_bare_metal``：``ON DELETE RESTRICT ON UPDATE RESTRICT``（禁止 CASCADE）；
- ``ck_network_interfaces_technology_type``：四值封闭集合 CHECK（R-NIC-001）；
- ``ck_network_interfaces_purpose``：七值封闭集合 CHECK（R-NIC-002）；
- ``ix_network_interfaces_bare_metal_id``：FK 引用检查 + 按宿主读取；
- **唯一索引集合为空**（NQ-2 未确认，不得表达 NIC 名称唯一性）；
- **无** 触发器 / ``COLLATE`` / extension；**无** 数据迁移（表为首次创建）。
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0005_f004_network_interfaces"
down_revision: str | None = "0004_f006_virtual_machines"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "network_interfaces",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        # R-NIC-003：宿主 BareMetal，必选、恰好一个。
        sa.Column("bare_metal_id", sa.BigInteger(), nullable=False),
        # 接口名（eth0 / ib0 …）；无长度 / trim / 字符 / "/" 约束。
        sa.Column("name", sa.Text(), nullable=False),
        # R-NIC-001：封闭四值。
        sa.Column("technology_type", sa.Text(), nullable=False),
        # R-NIC-002：封闭七值。
        sa.Column("purpose", sa.Text(), nullable=False),
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
        sa.PrimaryKeyConstraint("id", name="pk_network_interfaces"),
        sa.ForeignKeyConstraint(
            ["bare_metal_id"],
            ["bare_metals.id"],
            name="fk_network_interfaces_bare_metal",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
        # 命名约定 "ck" = "ck_%(table_name)s_%(constraint_name)s"，故此处传入裸名。
        sa.CheckConstraint(
            "technology_type IN ('Ethernet', 'InfiniBand', 'RoCE', 'Other')",
            name="technology_type",
        ),
        sa.CheckConstraint(
            "purpose IN ('BMC', 'Management', 'Business', 'Compute', "
            "'Storage', 'DataTransfer', 'Other')",
            name="purpose",
        ),
    )

    op.create_index("ix_network_interfaces_bare_metal_id", "network_interfaces", ["bare_metal_id"])


def downgrade() -> None:
    # 与 upgrade 逆序；破坏性，生产禁止。
    op.drop_index("ix_network_interfaces_bare_metal_id", table_name="network_interfaces")
    op.drop_table("network_interfaces")
