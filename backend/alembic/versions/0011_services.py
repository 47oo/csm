"""services for F011.

Revision ID: 0011_services
Revises: 0010_ip_addresses
Create Date: 2026-10-09

Schema per docs/database/f011-service.md v1 (DB-D128..DB-D141). Constraint and
index names are written explicitly / wrapped in ``op.f()`` so the
``Base.metadata`` naming convention is NOT re-applied (see ``0004_resources``).
Autogenerate does not detect CHECK constraints, so the full object set is
written explicitly.

Key points:
- ``services`` is an independent addressable object (own UUID PK/version/
  soft-delete/restore/Activity, DR-140); ``resource_id`` is an ordinary
  ``NOT NULL`` FK to ``resources(id)`` ``ON DELETE RESTRICT`` plus
  ``ix_services_resource_id``. ``resource`` is immutable after creation
  (application 422, DR-144); the database deliberately builds **no** immutable
  trigger (DB-D136), matching the F008/F009/F010 precedent.
- ``name`` is trimmed, non-empty, ASCII control free (DB backstop) and 1-255
  code points; the application additionally rejects Unicode Cc/Cf. ``name_key``
  is ``ASCII_lower(btrim(name))`` (only ASCII A-Z folded; DB uses ``translate``,
  never ``lower()``), enforced by ``ck_services_name_key_matches``.
- ``uq_services_resource_id_name_key`` is a *partial* unique index
  ``(resource_id, name_key) WHERE deleted_at IS NULL`` (DR-141): same-Resource
  names are unique among undeleted rows, cross-Resource duplicates allowed,
  soft delete releases the name, and a restore re-enters the index.
- ``status`` is ``varchar(16) NOT NULL DEFAULT 'UNKNOWN'`` with
  ``ck_services_status`` constraining ``RUNNING|STOPPED|UNKNOWN`` (DR-142).
- ``metadata`` is Service-owned ``jsonb NOT NULL DEFAULT '{}'`` with
  ``ck_services_metadata_object`` (``jsonb_typeof = 'object'``, DR-143).
- No pg_trgm/GIN and no name/name_key single-column B-tree (DB-D137); the
  extension set is unchanged (this migration performs no extension DDL).
- No backfill (the table is new); structurally symmetric downgrade that does NOT
  drop pg_trgm/btree_gist (F001 DB-D4). Service data is not recoverable on
  downgrade (production rollback uses a F001 full-database backup, DB-D141).
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "0011_services"
down_revision = "0010_ip_addresses"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ① Table: columns + PK + FK + all CHECKs.
    op.create_table(
        "services",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("resource_id", UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("name_key", sa.String(length=255), nullable=False),
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
        sa.PrimaryKeyConstraint("id", name=op.f("pk_services")),
        sa.ForeignKeyConstraint(
            ["resource_id"],
            ["resources.id"],
            name=op.f("fk_services_resource_id_resources"),
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "btrim(name) <> ''", name=op.f("ck_services_name_not_blank")
        ),
        sa.CheckConstraint(
            "name = btrim(name)", name=op.f("ck_services_name_trimmed")
        ),
        sa.CheckConstraint(
            "name !~ '[[:cntrl:]]'", name=op.f("ck_services_name_no_control")
        ),
        sa.CheckConstraint(
            "char_length(name) BETWEEN 1 AND 255",
            name=op.f("ck_services_name_length"),
        ),
        sa.CheckConstraint(
            "name_key = translate(btrim(name), "
            "'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz')",
            name=op.f("ck_services_name_key_matches"),
        ),
        sa.CheckConstraint(
            "status IN ('RUNNING','STOPPED','UNKNOWN')",
            name=op.f("ck_services_status"),
        ),
        sa.CheckConstraint(
            "jsonb_typeof(metadata) = 'object'",
            name=op.f("ck_services_metadata_object"),
        ),
        sa.CheckConstraint("version >= 1", name=op.f("ck_services_version")),
    )

    # ② Partial unique: same-Resource name is unique only among undeleted rows.
    op.create_index(
        "uq_services_resource_id_name_key",
        "services",
        ["resource_id", "name_key"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )

    # ③ Filter/index collection. No pg_trgm/GIN, no name/name_key B-tree
    #    (DB-D137).
    op.create_index("ix_services_resource_id", "services", ["resource_id"])
    op.create_index("ix_services_status", "services", ["status"])
    op.create_index("ix_services_deleted_at", "services", ["deleted_at"])


def downgrade() -> None:
    op.drop_index("ix_services_deleted_at", table_name="services")
    op.drop_index("ix_services_status", table_name="services")
    op.drop_index("ix_services_resource_id", table_name="services")
    op.drop_index("uq_services_resource_id_name_key", table_name="services")
    op.drop_table("services")
    # pg_trgm / btree_gist are intentionally NOT dropped (F001 DB-D4); shared.