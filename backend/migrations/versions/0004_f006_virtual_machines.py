"""F006：``virtual_machines`` 表 + FK RESTRICT + partial unique + 宿主索引（增量）。

Revision ID: 0004_f006_virtual_machines
Revises: 0003_f002_bare_metals
Create Date: 2026-09-17

严格对应 ``docs/database/f006-virtual-machine-migration.md`` 的 ``virtual_machines`` 段：

- **不修改** ``0001_f012_baseline`` / ``0002_f013_auth`` / ``0003_f002_bare_metals``；
- 一条 ``CREATE TABLE`` 建齐 **12 列**（``bare_metal_id NOT NULL`` + ``name NOT NULL``
  + 六个可空 ``TEXT`` + 时间列 + ``deleted_at``）；**无** ``status`` 列、**无** ``cluster_id`` 列；
- ``fk_virtual_machines_bare_metal``：``ON DELETE RESTRICT ON UPDATE RESTRICT``（禁止 CASCADE）；
- ``ux_virtual_machines_name_active``：partial unique，predicate ``deleted_at IS NULL``
  （全局、大小写敏感，不声明 ``COLLATE``、不使用 ``lower()``）；
- ``ix_virtual_machines_bare_metal_id``：FK 引用检查 + 按宿主读取；
- ``CHECK`` 集合为空；**无** 触发器 / ``COLLATE`` / extension；**无** 数据迁移（表为首次创建）。
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0004_f006_virtual_machines"
down_revision: str | None = "0003_f002_bare_metals"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "virtual_machines",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        # R-VM-005：宿主 BareMetal，必选、恰好一个。
        sa.Column("bare_metal_id", sa.BigInteger(), nullable=False),
        # R-VM-004：身份标识；无长度 / trim / 空串 / 字符 / "/" 约束。
        sa.Column("name", sa.Text(), nullable=False),
        # R-VM-006：六个可选纯文本字段，允许 NULL、不结构化。
        sa.Column("cpu", sa.Text(), nullable=True),
        sa.Column("memory", sa.Text(), nullable=True),
        sa.Column("disk", sa.Text(), nullable=True),
        sa.Column("os", sa.Text(), nullable=True),
        sa.Column("hypervisor", sa.Text(), nullable=True),
        sa.Column("owner", sa.Text(), nullable=True),
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
        sa.PrimaryKeyConstraint("id", name="pk_virtual_machines"),
        sa.ForeignKeyConstraint(
            ["bare_metal_id"],
            ["bare_metals.id"],
            name="fk_virtual_machines_bare_metal",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
    )

    op.create_index(
        "ux_virtual_machines_name_active",
        "virtual_machines",
        ["name"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_index("ix_virtual_machines_bare_metal_id", "virtual_machines", ["bare_metal_id"])


def downgrade() -> None:
    # 与 upgrade 逆序；破坏性，生产禁止。
    op.drop_index("ix_virtual_machines_bare_metal_id", table_name="virtual_machines")
    op.drop_index("ux_virtual_machines_name_active", table_name="virtual_machines")
    op.drop_table("virtual_machines")
