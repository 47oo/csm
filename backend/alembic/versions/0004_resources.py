"""resources for F004.

Revision ID: 0004_resources
Revises: 0003_clusters_audit
Create Date: 2026-10-08

Schema per docs/database/f004-resource.md v1 (DB-D33..DB-D44). Constraint
names are wrapped in ``op.f()`` so the ``Base.metadata`` naming convention is
NOT re-applied (see ``0003_clusters_audit``). Autogenerate does not detect
CHECK constraints, partial/expression indexes or triggers, so the full object
set is written explicitly.

Key points:
- ``uq_resources_cluster_id_hostname_key`` is a *partial* unique index
  ``(cluster_id, hostname_key) WHERE deleted_at IS NULL``: undeleted rows are
  unique per cluster, soft-deleted rows release the key, cross-cluster reuse is
  allowed (contrast with the F003 full-unique ``uq_clusters_code_key``).
- ``hostname`` stores the trimmed + ASCII-only lower display value;
  ``hostname_key`` is the redundant normalisation key, locked by
  ``ck_resources_hostname_key_matches`` using ``translate(btrim(...))`` and
  deliberately NOT ``lower()`` (locale-independent, non-ASCII preserved).
- ``trg_resources_immutable_fields`` rejects ``cluster_id``/``resource_type``
  changes (application returns 422 first).

Downgrade drops objects in reverse order; symmetric structurally. Production
rollback uses a F001 full-database backup (structure reversibility is not data
reversibility, docs/database/f004-resource.md §5/I-6).
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "0004_resources"
down_revision = "0003_clusters_audit"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "resources",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("cluster_id", UUID(as_uuid=True), nullable=False),
        sa.Column("hostname", sa.String(length=253), nullable=False),
        sa.Column("hostname_key", sa.String(length=253), nullable=False),
        sa.Column("resource_type", sa.String(length=32), nullable=False),
        sa.Column(
            "role",
            sa.String(length=16),
            server_default=sa.text("'OTHER'"),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.String(length=16),
            server_default=sa.text("'UNKNOWN'"),
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
        sa.PrimaryKeyConstraint("id", name=op.f("pk_resources")),
        sa.ForeignKeyConstraint(
            ["cluster_id"],
            ["clusters.id"],
            name=op.f("fk_resources_cluster_id_clusters"),
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "btrim(hostname) <> ''", name=op.f("ck_resources_hostname_not_blank")
        ),
        sa.CheckConstraint(
            "hostname = btrim(hostname)", name=op.f("ck_resources_hostname_trimmed")
        ),
        sa.CheckConstraint(
            "hostname !~ '[[:space:][:cntrl:]]'",
            name=op.f("ck_resources_hostname_no_ws_control"),
        ),
        sa.CheckConstraint(
            "char_length(hostname) BETWEEN 1 AND 253",
            name=op.f("ck_resources_hostname_length"),
        ),
        sa.CheckConstraint(
            "hostname = translate(hostname, "
            "'ABCDEFGHIJKLMNOPQRSTUVWXYZ', "
            "'abcdefghijklmnopqrstuvwxyz')",
            name=op.f("ck_resources_hostname_ascii_lower"),
        ),
        sa.CheckConstraint(
            "btrim(hostname_key) <> ''",
            name=op.f("ck_resources_hostname_key_not_blank"),
        ),
        sa.CheckConstraint(
            "char_length(hostname_key) BETWEEN 1 AND 253",
            name=op.f("ck_resources_hostname_key_length"),
        ),
        sa.CheckConstraint(
            "hostname_key = translate(btrim(hostname), "
            "'ABCDEFGHIJKLMNOPQRSTUVWXYZ', "
            "'abcdefghijklmnopqrstuvwxyz')",
            name=op.f("ck_resources_hostname_key_matches"),
        ),
        sa.CheckConstraint(
            "resource_type IN ('BARE_METAL','VIRTUAL_MACHINE')",
            name=op.f("ck_resources_resource_type"),
        ),
        sa.CheckConstraint(
            "role IN ('COMPUTE','LOGIN','MANAGEMENT','STORAGE','SERVICE','GPU','OTHER')",
            name=op.f("ck_resources_role"),
        ),
        sa.CheckConstraint(
            "status IN ('IDLE','ALLOC','DOWN','UNKNOWN')",
            name=op.f("ck_resources_status"),
        ),
        sa.CheckConstraint(
            "jsonb_typeof(metadata) = 'object'",
            name=op.f("ck_resources_metadata_object"),
        ),
        sa.CheckConstraint("version >= 1", name=op.f("ck_resources_version")),
    )

    # Partial unique: same-cluster hostname is unique only among undeleted rows.
    op.create_index(
        "uq_resources_cluster_id_hostname_key",
        "resources",
        ["cluster_id", "hostname_key"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_index("ix_resources_cluster_id", "resources", ["cluster_id"])
    op.create_index("ix_resources_resource_type", "resources", ["resource_type"])
    op.create_index("ix_resources_role", "resources", ["role"])
    op.create_index("ix_resources_status", "resources", ["status"])
    op.create_index("ix_resources_deleted_at", "resources", ["deleted_at"])
    op.create_index("ix_resources_hostname_key", "resources", ["hostname_key"])

    op.execute(
        """
        CREATE OR REPLACE FUNCTION fn_resources_immutable_fields()
        RETURNS trigger AS $$
        BEGIN
            IF NEW.cluster_id IS DISTINCT FROM OLD.cluster_id
               OR NEW.resource_type IS DISTINCT FROM OLD.resource_type THEN
                RAISE EXCEPTION 'resources.cluster_id/resource_type are immutable'
                    USING ERRCODE = 'restrict_violation';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_resources_immutable_fields
        BEFORE UPDATE ON resources
        FOR EACH ROW EXECUTE FUNCTION fn_resources_immutable_fields();
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_resources_immutable_fields ON resources")
    op.execute("DROP FUNCTION IF EXISTS fn_resources_immutable_fields()")
    op.drop_index("ix_resources_hostname_key", table_name="resources")
    op.drop_index("ix_resources_deleted_at", table_name="resources")
    op.drop_index("ix_resources_status", table_name="resources")
    op.drop_index("ix_resources_role", table_name="resources")
    op.drop_index("ix_resources_resource_type", table_name="resources")
    op.drop_index("ix_resources_cluster_id", table_name="resources")
    op.drop_index("uq_resources_cluster_id_hostname_key", table_name="resources")
    op.drop_table("resources")