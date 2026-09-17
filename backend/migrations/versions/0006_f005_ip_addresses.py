"""F005：``ip_addresses`` 表 + 两条 FK RESTRICT + partial unique index（增量）。

Revision ID: 0006_f005_ip_addresses
Revises: 0005_f004_network_interfaces
Create Date: 2026-09-18

严格对应 ``docs/database/f005-ip-address-migration.md`` 的 ``ip_addresses`` 段与
``docs/architecture/f005-ip-address-handoff.md`` 决策 1：

- **不修改** ``0001_f012_baseline`` / ``0002_f013_auth`` / ``0003_f002_bare_metals`` /
  ``0004_f006_virtual_machines`` / ``0005_f004_network_interfaces``；
- 一条 ``CREATE TABLE`` 建齐 **7 列**（``network_interface_id NOT NULL`` +
  ``cluster_id NOT NULL``（反规范化：唯一性边界）+ ``ip_address TEXT NOT NULL``
  + 时间列 + ``deleted_at``）；**无** ``status`` 列、**无** VRF / 命名空间 / IP 池 /
  DHCP / DNS / 自动发现列、**无**载体多态列；
- **CHECK 约束集合为空**：``ip_address`` 不施加任何长度 / trim / 空串 / 格式 /
  ``COLLATE`` / ``lower()`` 约束（NQ-1 未确认，不得发明）；
- ``fk_ip_addresses_network_interface``：``ON DELETE RESTRICT ON UPDATE RESTRICT``；
- ``fk_ip_addresses_cluster``：``ON DELETE RESTRICT ON UPDATE RESTRICT``（禁止 CASCADE）；
- ``ux_ip_addresses_cluster_ip_active (cluster_id, ip_address) WHERE deleted_at IS NULL``：
  R-IP-001 同 Cluster 唯一性的**最终权威**（字面精确、大小写敏感）；
- ``ix_ip_addresses_cluster_id`` + ``ix_ip_addresses_network_interface_id``；
- **无** 触发器 / ``COLLATE`` / ``lower()`` 表达式索引 / extension；**无** 数据迁移。
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0006_f005_ip_addresses"
down_revision: str | None = "0005_f004_network_interfaces"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ip_addresses",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        # 直接父 NetworkInterface（N:1 mandatory；用户 2026-09-15 裁定）。
        sa.Column("network_interface_id", sa.BigInteger(), nullable=False),
        # 反规范化：唯一性边界（ADR-0002）；由领域服务从 NIC→BareMetal 推导写入。
        sa.Column("cluster_id", sa.BigInteger(), nullable=False),
        # 字面值；无长度 / trim / 空串 / 格式 / 归一化约束。
        sa.Column("ip_address", sa.Text(), nullable=False),
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
        sa.PrimaryKeyConstraint("id", name="pk_ip_addresses"),
        sa.ForeignKeyConstraint(
            ["network_interface_id"],
            ["network_interfaces.id"],
            name="fk_ip_addresses_network_interface",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["cluster_id"],
            ["clusters.id"],
            name="fk_ip_addresses_cluster",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
    )

    op.create_index(
        "ux_ip_addresses_cluster_ip_active",
        "ip_addresses",
        ["cluster_id", "ip_address"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_index("ix_ip_addresses_cluster_id", "ip_addresses", ["cluster_id"])
    op.create_index(
        "ix_ip_addresses_network_interface_id", "ip_addresses", ["network_interface_id"]
    )


def downgrade() -> None:
    # 与 upgrade 严格逆序；破坏性（丢失全部 IP 登记历史），生产禁止。
    op.drop_index("ix_ip_addresses_network_interface_id", table_name="ip_addresses")
    op.drop_index("ix_ip_addresses_cluster_id", table_name="ip_addresses")
    op.drop_index("ux_ip_addresses_cluster_ip_active", table_name="ip_addresses")
    op.drop_table("ip_addresses")
