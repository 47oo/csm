"""api_keys table and audit_logs.api_key_label for F017.

Revision ID: 0014_api_keys
Revises: 0013_search_indexes
Create Date: 2026-10-14

Schema per docs/database/f017-api-key.md v1 (DB-D301..DB-D316). Constraint names
are wrapped in ``op.f()`` so the ``Base.metadata`` naming convention is NOT
re-applied on top of the fully-qualified names from the database design. Hand
written DDL (DB-D313): autogenerate does not recognise the CHECK expressions
(``~``, ``interval``, ``IS NULL OR``) nor ``gen_random_uuid()`` server defaults.

Upgrade: create ``api_keys`` (+ PK/FK/UNIQUE/CHECK) -> indexes -> add
``audit_logs.api_key_label`` -> add its nullable-safe not-blank CHECK.
Downgrade: reverse order. The downgrade is destructive (drops the F017-owned
``api_keys`` table and the F017-only ``api_key_label`` values); production
rollback uses an F001 backup, never ``downgrade`` (DB-D7 / DB-D314).
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "0014_api_keys"
down_revision = "0013_search_indexes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "api_keys",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("user_id", UUID(as_uuid=True), nullable=False),
        sa.Column("label", sa.String(length=255), nullable=False),
        sa.Column("key_hash", sa.String(length=64), nullable=False),
        sa.Column("created_by", UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_api_keys")),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_api_keys_user_id_users"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name=op.f("fk_api_keys_created_by_users"),
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("key_hash", name=op.f("uq_api_keys_key_hash")),
        sa.CheckConstraint(
            "btrim(label) <> ''", name=op.f("ck_api_keys_label_not_blank")
        ),
        sa.CheckConstraint(
            "key_hash ~ '^[0-9a-f]{64}$'",
            name=op.f("ck_api_keys_key_hash_format"),
        ),
        sa.CheckConstraint(
            "expires_at > created_at",
            name=op.f("ck_api_keys_expires_after_created"),
        ),
        sa.CheckConstraint(
            "expires_at <= created_at + interval '365 days' + interval '5 minutes'",
            name=op.f("ck_api_keys_expires_within_max"),
        ),
        sa.CheckConstraint(
            "revoked_at IS NULL OR revoked_at >= created_at",
            name=op.f("ck_api_keys_revoked_after_created"),
        ),
    )
    op.create_index("ix_api_keys_user_id", "api_keys", ["user_id"])
    op.create_index("ix_api_keys_created_by", "api_keys", ["created_by"])

    op.add_column(
        "audit_logs",
        sa.Column("api_key_label", sa.String(length=255), nullable=True),
    )
    op.create_check_constraint(
        op.f("ck_audit_logs_api_key_label_not_blank"),
        "audit_logs",
        "api_key_label IS NULL OR btrim(api_key_label) <> ''",
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("ck_audit_logs_api_key_label_not_blank"),
        "audit_logs",
        type_="check",
    )
    op.drop_column("audit_logs", "api_key_label")

    op.drop_index("ix_api_keys_created_by", table_name="api_keys")
    op.drop_index("ix_api_keys_user_id", table_name="api_keys")
    op.drop_table("api_keys")