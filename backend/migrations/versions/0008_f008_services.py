"""F008：``services`` 资源表 + ``service_carriers`` N:M 多态绑定关系表（增量）。

Revision ID: 0008_f008_services
Revises: 0007_f007_containers
Create Date: 2026-09-20

严格对应 ``docs/database/f008-service-migration.md`` §3 DDL 与
``docs/architecture/f008-service-handoff.md`` §1 / §2 / §8 裁定：

- **不修改** ``0001``–``0007``；
- ``services``：**11 列**，**0 个 CHECK**，仅 ``pk_services``；
  ``ux_services_name_active`` 为 partial unique（``WHERE deleted_at IS NULL``，
  大小写敏感，不声明 ``COLLATE``、不使用 ``lower()``）；
- ``service_carriers``：**5 列**，``pk_service_carriers`` +
  ``ck_service_carriers_exactly_one_carrier``（``num_nonnulls(三列) = 1``）+
  4 条真实 FK（全部 ``RESTRICT`` / ``RESTRICT``，禁止 CASCADE）；
- 集合语义由 3 条 partial unique（``(service_id, <carrier_col>)
  WHERE <carrier_col> IS NOT NULL``）表达；另有 3 条载体列索引 +
  ``ix_service_carriers_service_id``；
- **无** 触发器 / 生成列 / extension / 数据迁移；**无释放写入**（绑定表无
  ``deleted_at`` / 时间戳，释放由 ``services.deleted_at`` 派生）。
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0008_f008_services"
down_revision: str | None = "0007_f007_containers"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # --- services（11 列，仅 PK，无 CHECK）-------------------------------------
    op.create_table(
        "services",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        # R-SVC-008：身份标识；无长度 / trim / 空串 / 字符约束。
        sa.Column("name", sa.Text(), nullable=False),
        # R-SVC-001 / R-SVC-007：6 个可选纯文本字段，允许 NULL、不结构化。
        sa.Column("service_type", sa.Text(), nullable=True),
        sa.Column("url", sa.Text(), nullable=True),
        sa.Column("port", sa.Text(), nullable=True),
        sa.Column("protocol", sa.Text(), nullable=True),
        sa.Column("owner", sa.Text(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
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
        sa.PrimaryKeyConstraint("id", name="pk_services"),
    )

    op.create_index(
        "ux_services_name_active",
        "services",
        ["name"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )

    # --- service_carriers（5 列，PK + 1 CHECK + 4 FK RESTRICT）--------------------
    op.create_table(
        "service_carriers",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("service_id", sa.BigInteger(), nullable=False),
        sa.Column("bare_metal_id", sa.BigInteger(), nullable=True),
        sa.Column("virtual_machine_id", sa.BigInteger(), nullable=True),
        sa.Column("container_id", sa.BigInteger(), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_service_carriers"),
        sa.CheckConstraint(
            "num_nonnulls(bare_metal_id, virtual_machine_id, container_id) = 1",
            name="exactly_one_carrier",
        ),
        sa.ForeignKeyConstraint(
            ["service_id"],
            ["services.id"],
            name="fk_service_carriers_service",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["bare_metal_id"],
            ["bare_metals.id"],
            name="fk_service_carriers_bare_metal",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["virtual_machine_id"],
            ["virtual_machines.id"],
            name="fk_service_carriers_virtual_machine",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["container_id"],
            ["containers.id"],
            name="fk_service_carriers_container",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
    )

    # 集合语义：同一 Service 内不得重复绑定同一载体（每载体列一条 partial unique）。
    op.create_index(
        "ux_service_carriers_service_bare_metal",
        "service_carriers",
        ["service_id", "bare_metal_id"],
        unique=True,
        postgresql_where=sa.text("bare_metal_id IS NOT NULL"),
    )
    op.create_index(
        "ux_service_carriers_service_virtual_machine",
        "service_carriers",
        ["service_id", "virtual_machine_id"],
        unique=True,
        postgresql_where=sa.text("virtual_machine_id IS NOT NULL"),
    )
    op.create_index(
        "ux_service_carriers_service_container",
        "service_carriers",
        ["service_id", "container_id"],
        unique=True,
        postgresql_where=sa.text("container_id IS NOT NULL"),
    )

    # 按载体反查 Service（AC-17 / AC-19 / AC-31）与载体集合装配（AC-16）。
    op.create_index("ix_service_carriers_bare_metal_id", "service_carriers", ["bare_metal_id"])
    op.create_index(
        "ix_service_carriers_virtual_machine_id", "service_carriers", ["virtual_machine_id"]
    )
    op.create_index("ix_service_carriers_container_id", "service_carriers", ["container_id"])
    op.create_index("ix_service_carriers_service_id", "service_carriers", ["service_id"])


def downgrade() -> None:
    # 与 upgrade 严格逆序；破坏性（丢失全部 Service 登记与绑定历史），生产禁止。
    op.drop_index("ix_service_carriers_service_id", table_name="service_carriers")
    op.drop_index("ix_service_carriers_container_id", table_name="service_carriers")
    op.drop_index("ix_service_carriers_virtual_machine_id", table_name="service_carriers")
    op.drop_index("ix_service_carriers_bare_metal_id", table_name="service_carriers")
    op.drop_index("ux_service_carriers_service_container", table_name="service_carriers")
    op.drop_index("ux_service_carriers_service_virtual_machine", table_name="service_carriers")
    op.drop_index("ux_service_carriers_service_bare_metal", table_name="service_carriers")
    op.drop_table("service_carriers")
    op.drop_index("ux_services_name_active", table_name="services")
    op.drop_table("services")
