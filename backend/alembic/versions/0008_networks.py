"""networks for F008.

Revision ID: 0008_networks
Revises: 0007_interfaces
Create Date: 2026-10-09

Schema per docs/database/f008-network.md v1 (DB-D80..DB-D94). Constraint, index
and exclusion names are wrapped in ``op.f()``/written explicitly so the
``Base.metadata`` naming convention is NOT re-applied (see ``0004_resources``).
Autogenerate does not detect CHECK constraints or exclusion constraints, so the
full object set is written explicitly.

Key points:
- ``networks`` is an independent addressable object (own UUID PK/version/
  soft-delete/restore/Activity); ``cluster_id`` is an ordinary ``NOT NULL`` FK
  to ``clusters(id)`` ``ON DELETE RESTRICT`` plus ``ix_networks_cluster_id``.
- ``name_key`` is ``ASCII_lower(btrim(name))`` (only ASCII A-Z folded; DB uses
  ``translate``, never ``lower()``), enforced by ``ck_networks_name_key_matches``.
- ``uq_networks_cluster_id_name_key`` is a *partial* unique index
  ``(cluster_id, name_key) WHERE deleted_at IS NULL``: same-Cluster names are
  unique among undeleted rows, cross-Cluster duplicates allowed, soft delete
  releases the name.
- ``cidr`` uses the native PostgreSQL ``cidr`` type (only IPv4 via
  ``ck_networks_cidr_ipv4``); host bits are normalised to the network address by
  the type. ``excl_networks_cluster_id_cidr`` is
  ``EXCLUDE USING gist (cluster_id WITH =, cidr inet_ops WITH &&) WHERE
  (deleted_at IS NULL)``: same-Cluster undeleted CIDRs must not overlap
  (INACTIVE participates, soft-deleted rows do not). ``cluster_id WITH =`` needs
  **btree_gist**, which this migration enables for the first time (DB-D2
  predesignated F008/F009). The ``cidr`` element explicitly selects the built-in
  ``inet_ops`` GiST opclass for ``&&``: installing btree_gist shadows the default
  ``cidr`` GiST opclass with ``gist_cidr_ops`` (equality only), so an explicit
  opclass is required for the overlap operator.
- ``gateway`` is nullable ``inet`` with a pure-SQL ``ck_networks_gateway``
  backstop (belongs to the CIDR's basic usable addresses and is not in a §11.1
  disabled range); the application returns 422 first.
- No backfill (the table is new); structurally symmetric downgrade that does NOT
  drop btree_gist (same as F001 DB-D4). Network data is not recoverable on
  downgrade (production rollback uses a F001 full-database backup, DB-D94).
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import CIDR, INET, JSONB, UUID

revision = "0008_networks"
down_revision = "0007_interfaces"
branch_labels = None
depends_on = None

# §11.1 disabled gateway ranges (CONFIRMED). Mirrors
# app.services.normalization.DISABLED_GATEWAY_NETWORKS and docs/api/F008.md.
_GATEWAY_CHECK = (
    "gateway IS NULL OR ("
    "family(gateway) = 4 AND masklen(cidr) <= 31 AND gateway << cidr::inet "
    "AND (masklen(cidr) = 31 OR (gateway <> network(cidr)::inet "
    "AND gateway <> broadcast(cidr))) "
    "AND NOT (gateway << '0.0.0.0/8'::inet OR gateway << '127.0.0.0/8'::inet "
    "OR gateway << '169.254.0.0/16'::inet OR gateway << '224.0.0.0/4'::inet "
    "OR gateway << '240.0.0.0/4'::inet))"
)


def upgrade() -> None:
    # ① btree_gist is required by the ``cluster_id WITH =`` exclusion below and
    #    is enabled here for the first time (DB-D2/DB-D88). Idempotent.
    op.execute("CREATE EXTENSION IF NOT EXISTS btree_gist WITH SCHEMA public")

    # ② Table: columns + PK + FK + all CHECKs.
    op.create_table(
        "networks",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("cluster_id", UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("name_key", sa.String(length=255), nullable=False),
        sa.Column("cidr", CIDR(), nullable=False),
        sa.Column("gateway", INET(), nullable=True),
        sa.Column(
            "status",
            sa.String(length=16),
            server_default=sa.text("'ACTIVE'"),
            nullable=False,
        ),
        sa.Column(
            "auto_allocate",
            sa.Boolean(),
            server_default=sa.text("false"),
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
        sa.PrimaryKeyConstraint("id", name=op.f("pk_networks")),
        sa.ForeignKeyConstraint(
            ["cluster_id"],
            ["clusters.id"],
            name=op.f("fk_networks_cluster_id_clusters"),
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "btrim(name) <> ''", name=op.f("ck_networks_name_not_blank")
        ),
        sa.CheckConstraint("name = btrim(name)", name=op.f("ck_networks_name_trimmed")),
        sa.CheckConstraint(
            "name !~ '[[:cntrl:]]'", name=op.f("ck_networks_name_no_control")
        ),
        sa.CheckConstraint(
            "char_length(name) BETWEEN 1 AND 255",
            name=op.f("ck_networks_name_length"),
        ),
        sa.CheckConstraint(
            "name_key = translate(btrim(name), "
            "'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz')",
            name=op.f("ck_networks_name_key_matches"),
        ),
        sa.CheckConstraint("family(cidr) = 4", name=op.f("ck_networks_cidr_ipv4")),
        sa.CheckConstraint(_GATEWAY_CHECK, name=op.f("ck_networks_gateway")),
        sa.CheckConstraint(
            "status IN ('ACTIVE','INACTIVE')", name=op.f("ck_networks_status")
        ),
        sa.CheckConstraint(
            "jsonb_typeof(metadata) = 'object'",
            name=op.f("ck_networks_metadata_object"),
        ),
        sa.CheckConstraint("version >= 1", name=op.f("ck_networks_version")),
    )

    # ③ Partial unique: same-Cluster name is unique only among undeleted rows.
    op.create_index(
        "uq_networks_cluster_id_name_key",
        "networks",
        ["cluster_id", "name_key"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )

    # ④ Filter / FK indexes.
    op.create_index("ix_networks_cluster_id", "networks", ["cluster_id"])
    op.create_index("ix_networks_status", "networks", ["status"])
    op.create_index("ix_networks_deleted_at", "networks", ["deleted_at"])

    # ⑤ CIDR no-overlap exclusion (needs btree_gist for cluster_id WITH =).
    op.execute(
        "ALTER TABLE networks ADD CONSTRAINT excl_networks_cluster_id_cidr "
        "EXCLUDE USING gist (cluster_id WITH =, cidr inet_ops WITH &&) "
        "WHERE (deleted_at IS NULL)"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE networks DROP CONSTRAINT IF EXISTS excl_networks_cluster_id_cidr"
    )
    op.drop_index("ix_networks_deleted_at", table_name="networks")
    op.drop_index("ix_networks_status", table_name="networks")
    op.drop_index("ix_networks_cluster_id", table_name="networks")
    op.drop_index("uq_networks_cluster_id_name_key", table_name="networks")
    op.drop_table("networks")
    # btree_gist is intentionally NOT dropped (F001 DB-D4); it may be shared.