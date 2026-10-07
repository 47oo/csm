"""clusters and audit_logs for F003.

Revision ID: 0003_clusters_audit
Revises: 0002_users_sessions
Create Date: 2026-10-06

Schema per docs/database/f003-cluster.md v1 (DB-D20..DB-D32). Constraint names
are wrapped in ``op.f()`` so the ``Base.metadata`` naming convention is NOT
re-applied (see ``0002_users_sessions``). Autogenerate does not detect CHECK
constraints or triggers, so the full object set is written explicitly.

Triggers:
- ``trg_clusters_code_immutable``: ``code``/``code_key`` are immutable; the
  application returns 422 first, the database enforces it as a backstop.
- ``trg_audit_logs_append_only``: UPDATE/DELETE on ``audit_logs`` are rejected
  (TRUNCATE/DROP are intentionally left possible for test teardown/downgrade).

Downgrade drops objects in reverse order and is symmetric structurally; the
data-safety policy (production rollback uses a F001 backup, not downgrade) is
recorded in docs/database/f003-cluster.md §5.
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "0003_clusters_audit"
down_revision = "0002_users_sessions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "clusters",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("code_key", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column(
            "status",
            sa.String(length=16),
            server_default=sa.text("'ACTIVE'"),
            nullable=False,
        ),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "metadata",
            JSONB(),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_clusters")),
        sa.UniqueConstraint("code_key", name=op.f("uq_clusters_code_key")),
        sa.CheckConstraint("btrim(code) <> ''", name=op.f("ck_clusters_code_not_blank")),
        sa.CheckConstraint("code = btrim(code)", name=op.f("ck_clusters_code_trimmed")),
        sa.CheckConstraint(
            "code !~ '[[:space:][:cntrl:]]'",
            name=op.f("ck_clusters_code_no_ws_control"),
        ),
        sa.CheckConstraint(
            "char_length(code) BETWEEN 1 AND 64",
            name=op.f("ck_clusters_code_length"),
        ),
        sa.CheckConstraint(
            "btrim(code_key) <> ''", name=op.f("ck_clusters_code_key_not_blank")
        ),
        sa.CheckConstraint(
            "char_length(code_key) BETWEEN 1 AND 64",
            name=op.f("ck_clusters_code_key_length"),
        ),
        sa.CheckConstraint(
            "code_key = translate(btrim(code), "
            "'abcdefghijklmnopqrstuvwxyz', "
            "'ABCDEFGHIJKLMNOPQRSTUVWXYZ')",
            name=op.f("ck_clusters_code_key_matches"),
        ),
        sa.CheckConstraint("btrim(name) <> ''", name=op.f("ck_clusters_name_not_blank")),
        sa.CheckConstraint("name = btrim(name)", name=op.f("ck_clusters_name_trimmed")),
        sa.CheckConstraint(
            "name !~ '[[:cntrl:]]'", name=op.f("ck_clusters_name_no_control")
        ),
        sa.CheckConstraint(
            "status IN ('ACTIVE','INACTIVE')", name=op.f("ck_clusters_status")
        ),
        sa.CheckConstraint(
            "jsonb_typeof(metadata) = 'object'",
            name=op.f("ck_clusters_metadata_object"),
        ),
        sa.CheckConstraint("version >= 1", name=op.f("ck_clusters_version")),
    )
    op.create_index("ix_clusters_status", "clusters", ["status"])
    op.create_index("ix_clusters_deleted_at", "clusters", ["deleted_at"])

    op.execute(
        """
        CREATE OR REPLACE FUNCTION fn_clusters_code_immutable()
        RETURNS trigger AS $$
        BEGIN
            IF NEW.code IS DISTINCT FROM OLD.code
               OR NEW.code_key IS DISTINCT FROM OLD.code_key THEN
                RAISE EXCEPTION 'clusters.code is immutable'
                    USING ERRCODE = 'check_violation';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_clusters_code_immutable
        BEFORE UPDATE ON clusters
        FOR EACH ROW EXECUTE FUNCTION fn_clusters_code_immutable();
        """
    )

    op.create_table(
        "audit_logs",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("operator_user_id", UUID(as_uuid=True), nullable=True),
        sa.Column("operator_username", sa.String(length=64), nullable=False),
        sa.Column("action", sa.String(length=16), nullable=False),
        sa.Column("object_type", sa.String(length=64), nullable=False),
        sa.Column("object_id", UUID(as_uuid=True), nullable=False),
        sa.Column("before_data", JSONB(), nullable=True),
        sa.Column("after_data", JSONB(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_audit_logs")),
        sa.ForeignKeyConstraint(
            ["operator_user_id"],
            ["users.id"],
            name=op.f("fk_audit_logs_operator_user_id_users"),
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "btrim(operator_username) <> ''",
            name=op.f("ck_audit_logs_operator_username_not_blank"),
        ),
        sa.CheckConstraint(
            "action IN ('CREATE','UPDATE','DELETE','RESTORE')",
            name=op.f("ck_audit_logs_action"),
        ),
        sa.CheckConstraint(
            "before_data IS NOT NULL OR after_data IS NOT NULL",
            name=op.f("ck_audit_logs_at_least_one_snapshot"),
        ),
        sa.CheckConstraint(
            "before_data IS NULL OR jsonb_typeof(before_data) = 'object'",
            name=op.f("ck_audit_logs_before_data_object"),
        ),
        sa.CheckConstraint(
            "after_data IS NULL OR jsonb_typeof(after_data) = 'object'",
            name=op.f("ck_audit_logs_after_data_object"),
        ),
    )
    op.create_index(
        "ix_audit_logs_object_type_object_id",
        "audit_logs",
        ["object_type", "object_id", "created_at"],
    )
    op.create_index(
        "ix_audit_logs_operator_user_id", "audit_logs", ["operator_user_id"]
    )
    op.create_index("ix_audit_logs_created_at", "audit_logs", ["created_at"])

    op.execute(
        """
        CREATE OR REPLACE FUNCTION fn_audit_logs_append_only()
        RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'audit_logs is append-only'
                USING ERRCODE = 'restrict_violation';
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_audit_logs_append_only
        BEFORE UPDATE OR DELETE ON audit_logs
        FOR EACH ROW EXECUTE FUNCTION fn_audit_logs_append_only();
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_audit_logs_append_only ON audit_logs")
    op.execute("DROP FUNCTION IF EXISTS fn_audit_logs_append_only()")
    op.drop_index("ix_audit_logs_created_at", table_name="audit_logs")
    op.drop_index("ix_audit_logs_operator_user_id", table_name="audit_logs")
    op.drop_index("ix_audit_logs_object_type_object_id", table_name="audit_logs")
    op.drop_table("audit_logs")

    op.execute("DROP TRIGGER IF EXISTS trg_clusters_code_immutable ON clusters")
    op.execute("DROP FUNCTION IF EXISTS fn_clusters_code_immutable()")
    op.drop_index("ix_clusters_deleted_at", table_name="clusters")
    op.drop_index("ix_clusters_status", table_name="clusters")
    op.drop_table("clusters")