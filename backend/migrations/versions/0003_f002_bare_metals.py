"""F002：``bare_metals`` 表 + FK / CHECK / partial unique index（增量）。

Revision ID: 0003_f002_bare_metals
Revises: 0002_f013_auth
Create Date: 2026-09-16

严格对应 ``docs/database/f002-bare-metal-migration.md`` 的 ``bare_metals`` 段：

- **不修改** ``0001_f012_baseline`` / ``0002_f013_auth``；
- 一条 ``CREATE TABLE`` 建齐 14 列（含 R-BM-007 七列，``TEXT NULL``）；
- ``fk_bare_metals_cluster``：``ON DELETE RESTRICT ON UPDATE RESTRICT``（禁止 CASCADE）；
- ``ck_bare_metals_status``：四值封闭集合 CHECK；
- ``ux_bare_metals_cluster_hostname_active``：partial unique，predicate ``deleted_at IS NULL``；
- ``ix_bare_metals_cluster_id``：FK 引用检查 + 含已删行的按 Cluster 查询；
- **无** 触发器 / ``COLLATE`` / extension；**无** 数据迁移（表为首次创建）。
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0003_f002_bare_metals"
down_revision: str | None = "0002_f013_auth"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "bare_metals",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("cluster_id", sa.BigInteger(), nullable=False),
        sa.Column("hostname", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), server_default=sa.text("'IDLE'"), nullable=False),
        # R-BM-007：七个硬件字段纯文本、可选、允许 NULL。
        sa.Column("vendor", sa.Text(), nullable=True),
        sa.Column("model", sa.Text(), nullable=True),
        sa.Column("serial_number", sa.Text(), nullable=True),
        sa.Column("cpu", sa.Text(), nullable=True),
        sa.Column("memory", sa.Text(), nullable=True),
        sa.Column("gpu", sa.Text(), nullable=True),
        sa.Column("storage", sa.Text(), nullable=True),
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
        sa.PrimaryKeyConstraint("id", name="pk_bare_metals"),
        sa.ForeignKeyConstraint(
            ["cluster_id"],
            ["clusters.id"],
            name="fk_bare_metals_cluster",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
        # 命名约定 "ck" = "ck_%(table_name)s_%(constraint_name)s"，故此处传入裸名。
        sa.CheckConstraint("status IN ('IDLE', 'ALLOC', 'DOWN', 'UNKNOWN')", name="status"),
    )

    op.create_index(
        "ux_bare_metals_cluster_hostname_active",
        "bare_metals",
        ["cluster_id", "hostname"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_index("ix_bare_metals_cluster_id", "bare_metals", ["cluster_id"])


def downgrade() -> None:
    # 与 upgrade 逆序；破坏性，生产禁止。
    op.drop_index("ix_bare_metals_cluster_id", table_name="bare_metals")
    op.drop_index("ux_bare_metals_cluster_hostname_active", table_name="bare_metals")
    op.drop_table("bare_metals")
