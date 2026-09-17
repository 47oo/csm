"""F007：``containers`` 表 + 两条载体 FK RESTRICT + 恰好一个载体 CHECK + 两条
载体内活跃名称 partial unique index（增量）。

Revision ID: 0007_f007_containers
Revises: 0006_f005_ip_addresses
Create Date: 2026-09-18

严格对应 ``docs/database/f007-container-migration.md`` 的 ``containers`` 段与
``docs/architecture/f007-container-handoff.md`` §1 / §9 裁定：

- **不修改** ``0001_f012_baseline`` / ``0002_f013_auth`` / ``0003_f002_bare_metals`` /
  ``0004_f006_virtual_machines`` / ``0005_f004_network_interfaces`` /
  ``0006_f005_ip_addresses``；
- 一条 ``CREATE TABLE`` 建齐 **11 列**（``bare_metal_id`` / ``virtual_machine_id``
  两列可空载体引用 + ``name NOT NULL`` + 四个可空 ``TEXT`` + 时间列 + ``deleted_at``）；
  **无** ``status`` 列、**无** ``cluster_id`` 列、**无** K8s / Docker / 运行时 / 位置列；
- ``ck_containers_carrier_exactly_one``：``CHECK (num_nonnulls(bare_metal_id,
  virtual_machine_id) = 1)``（恰好一个载体由数据库保证）；
- ``fk_containers_bare_metal`` / ``fk_containers_virtual_machine``：
  ``ON DELETE RESTRICT ON UPDATE RESTRICT``（禁止 CASCADE）；
- ``ux_containers_bare_metal_name_active`` / ``ux_containers_virtual_machine_name_active``：
  两条 partial unique index（predicate ``deleted_at IS NULL``，大小写敏感，不声明
  ``COLLATE``、不使用 ``lower()``），合起来表达「载体内活跃 ``name`` 唯一」；
- ``ix_containers_bare_metal_id`` / ``ix_containers_virtual_machine_id``：FK 引用检查；
- **无** 触发器 / 生成列 / extension；**无** 数据迁移（表为首次创建）。
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0007_f007_containers"
down_revision: str | None = "0006_f005_ip_addresses"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "containers",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        # R-CONTAINER-002：运行载体二选一（BareMetal 或 VirtualMachine），恰好一个。
        sa.Column("bare_metal_id", sa.BigInteger(), nullable=True),
        sa.Column("virtual_machine_id", sa.BigInteger(), nullable=True),
        # R-CONTAINER-003：身份标识；无长度 / trim / 空串 / 字符约束。
        sa.Column("name", sa.Text(), nullable=False),
        # R-CONTAINER-004：四个可选纯文本字段，允许 NULL、不结构化。
        sa.Column("image", sa.Text(), nullable=True),
        sa.Column("cpu", sa.Text(), nullable=True),
        sa.Column("memory", sa.Text(), nullable=True),
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
        sa.PrimaryKeyConstraint("id", name="pk_containers"),
        sa.CheckConstraint(
            "num_nonnulls(bare_metal_id, virtual_machine_id) = 1",
            name="carrier_exactly_one",
        ),
        sa.ForeignKeyConstraint(
            ["bare_metal_id"],
            ["bare_metals.id"],
            name="fk_containers_bare_metal",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["virtual_machine_id"],
            ["virtual_machines.id"],
            name="fk_containers_virtual_machine",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
    )

    op.create_index(
        "ux_containers_bare_metal_name_active",
        "containers",
        ["bare_metal_id", "name"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_index(
        "ux_containers_virtual_machine_name_active",
        "containers",
        ["virtual_machine_id", "name"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_index("ix_containers_bare_metal_id", "containers", ["bare_metal_id"])
    op.create_index("ix_containers_virtual_machine_id", "containers", ["virtual_machine_id"])


def downgrade() -> None:
    # 与 upgrade 严格逆序；破坏性（丢失全部 Container 登记历史），生产禁止。
    op.drop_index("ix_containers_virtual_machine_id", table_name="containers")
    op.drop_index("ix_containers_bare_metal_id", table_name="containers")
    op.drop_index("ux_containers_virtual_machine_name_active", table_name="containers")
    op.drop_index("ux_containers_bare_metal_name_active", table_name="containers")
    op.drop_table("containers")
