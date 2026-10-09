"""ip_pools for F009.

Revision ID: 0009_ip_pools
Revises: 0008_networks
Create Date: 2026-10-09

Schema per docs/database/f009-ip-pool.md v1 (DB-D95..DB-D110). Constraint, index,
exclusion and trigger names are written explicitly / wrapped in ``op.f()`` so the
``Base.metadata`` naming convention is NOT re-applied (see ``0004_resources``).
Autogenerate does not detect CHECK constraints or exclusion constraints, so the
full object set is written explicitly.

Key points:
- ``ip_pools`` is an independent addressable object (own UUID PK/version/
  soft-delete/restore/Activity); ``network_id`` is an ordinary ``NOT NULL`` FK
  to ``networks(id)`` ``ON DELETE RESTRICT`` plus ``ix_ip_pools_network_id``.
- ``name_key`` is ``ASCII_lower(btrim(name))`` (only ASCII A-Z folded; DB uses
  ``translate``, never ``lower()``), enforced by ``ck_ip_pools_name_key_matches``.
- ``uq_ip_pools_network_id_name_key`` is a *partial* unique index
  ``(network_id, name_key) WHERE deleted_at IS NULL``: same-Network names are
  unique among undeleted rows, cross-Network duplicates allowed, soft delete
  releases the name.
- ``start_address``/``end_address`` are PG ``inet`` host addresses (family 4 and
  masklen 32 enforced by ``ck_ip_pools_start_address_host`` /
  ``ck_ip_pools_end_address_host``); ``ck_ip_pools_address_order`` requires
  ``start <= end``.
- ``address_range`` is a **generated stored** ``int8range`` over the closed
  interval ``[start, end]`` (``set_masklen(x, 32) - '0.0.0.0'::inet``); it is the
  carrier for the exclusion constraint and is read-only from the ORM.
- ``excl_ip_pools_network_id_address_range`` is
  ``EXCLUDE USING gist (network_id WITH =, address_range WITH &&) WHERE
  (deleted_at IS NULL)``: same-Network undeleted pool ranges must not overlap
  (INACTIVE Networks participate, soft-deleted rows do not). ``network_id WITH =``
  needs **btree_gist**, enabled by ``0008_networks``; this migration does NOT
  re-enable it (DB-D100/DB-D107). The ``int8range`` ``&&`` uses the PG core GiST
  ``range_ops`` (no btree_gist opclass needed for the range column).
- ``fn_ip_pools_cidr_contains``/``trg_ip_pools_cidr_contains`` (BEFORE INSERT OR
  UPDATE) is the cross-table backstop requiring start/end to fall within the
  owning Network CIDR (``<<=`` so a ``/32`` Network accepts ``start = end``); it
  locks the ``networks`` row ``FOR KEY SHARE`` so it serialises with
  ``_lock_network`` (FOR UPDATE) (DB-D104).
- No backfill (the table is new); structurally symmetric downgrade that does NOT
  drop btree_gist (F001 DB-D4). Pool data is not recoverable on downgrade
  (production rollback uses a F001 full-database backup, DB-D110).
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import INT8RANGE, INET, UUID

revision = "0009_ip_pools"
down_revision = "0008_networks"
branch_labels = None
depends_on = None

# Closed-interval integer range over the two host addresses (DB-D99).
_ADDRESS_RANGE = (
    "int8range("
    "set_masklen(start_address, 32) - '0.0.0.0'::inet, "
    "set_masklen(end_address, 32) - '0.0.0.0'::inet, "
    "'[]')"
)

# The cross-table CIDR containment backstop (DB-D104). ``<<=`` makes a /32
# Network accept ``start = end = the address``.
_CIDR_CONTAINS_FUNCTION = """
CREATE OR REPLACE FUNCTION fn_ip_pools_cidr_contains()
RETURNS trigger AS $$
DECLARE
    net_cidr inet;
BEGIN
    SELECT n.cidr::inet INTO net_cidr
      FROM networks n
     WHERE n.id = NEW.network_id
     FOR KEY SHARE;
    IF NOT FOUND THEN
        -- Network row missing: let the FK report the error, keeping a single
        -- error source consistent with the FK semantics.
        RETURN NEW;
    END IF;
    IF NOT (NEW.start_address <<= net_cidr)
       OR NOT (NEW.end_address <<= net_cidr) THEN
        RAISE EXCEPTION
            'ip_pools start_address/end_address must belong to the network CIDR'
            USING ERRCODE = 'restrict_violation';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql
"""


def upgrade() -> None:
    # ① Table: columns (incl. generated address_range) + PK + FK + all CHECKs.
    op.create_table(
        "ip_pools",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("network_id", UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("name_key", sa.String(length=255), nullable=False),
        sa.Column("start_address", INET(), nullable=False),
        sa.Column("end_address", INET(), nullable=False),
        sa.Column(
            "address_range",
            INT8RANGE(),
            sa.Computed(_ADDRESS_RANGE, persisted=True),
            nullable=False,
        ),
        sa.Column(
            "allocation_mode",
            sa.String(length=16),
            server_default=sa.text("'MANUAL'"),
            nullable=False,
        ),
        sa.Column("description", sa.Text(), nullable=True),
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
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ip_pools")),
        sa.ForeignKeyConstraint(
            ["network_id"],
            ["networks.id"],
            name=op.f("fk_ip_pools_network_id_networks"),
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "btrim(name) <> ''", name=op.f("ck_ip_pools_name_not_blank")
        ),
        sa.CheckConstraint(
            "name = btrim(name)", name=op.f("ck_ip_pools_name_trimmed")
        ),
        sa.CheckConstraint(
            "name !~ '[[:cntrl:]]'", name=op.f("ck_ip_pools_name_no_control")
        ),
        sa.CheckConstraint(
            "char_length(name) BETWEEN 1 AND 255",
            name=op.f("ck_ip_pools_name_length"),
        ),
        sa.CheckConstraint(
            "name_key = translate(btrim(name), "
            "'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz')",
            name=op.f("ck_ip_pools_name_key_matches"),
        ),
        sa.CheckConstraint(
            "family(start_address) = 4 AND masklen(start_address) = 32",
            name=op.f("ck_ip_pools_start_address_host"),
        ),
        sa.CheckConstraint(
            "family(end_address) = 4 AND masklen(end_address) = 32",
            name=op.f("ck_ip_pools_end_address_host"),
        ),
        sa.CheckConstraint(
            "start_address <= end_address", name=op.f("ck_ip_pools_address_order")
        ),
        sa.CheckConstraint(
            "allocation_mode IN ('MANUAL','AUTO','RESERVED')",
            name=op.f("ck_ip_pools_allocation_mode"),
        ),
        sa.CheckConstraint("version >= 1", name=op.f("ck_ip_pools_version")),
    )

    # ② Partial unique: same-Network name is unique only among undeleted rows.
    op.create_index(
        "uq_ip_pools_network_id_name_key",
        "ip_pools",
        ["network_id", "name_key"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )

    # ③ Filter indexes. No pg_trgm/GIN, no start/end B-tree (DB-D106).
    op.create_index("ix_ip_pools_network_id", "ip_pools", ["network_id"])
    op.create_index("ix_ip_pools_allocation_mode", "ip_pools", ["allocation_mode"])
    op.create_index("ix_ip_pools_deleted_at", "ip_pools", ["deleted_at"])

    # ④ Range no-overlap exclusion over the generated column. btree_gist is
    #    already enabled by 0008 (only ``network_id WITH =`` needs it).
    op.execute(
        "ALTER TABLE ip_pools ADD CONSTRAINT excl_ip_pools_network_id_address_range "
        "EXCLUDE USING gist (network_id WITH =, address_range WITH &&) "
        "WHERE (deleted_at IS NULL)"
    )

    # ⑤ Cross-table CIDR containment backstop.
    op.execute(_CIDR_CONTAINS_FUNCTION)
    op.execute(
        "CREATE TRIGGER trg_ip_pools_cidr_contains "
        "BEFORE INSERT OR UPDATE ON ip_pools "
        "FOR EACH ROW EXECUTE FUNCTION fn_ip_pools_cidr_contains()"
    )


def downgrade() -> None:
    op.execute(
        "DROP TRIGGER IF EXISTS trg_ip_pools_cidr_contains ON ip_pools"
    )
    op.execute("DROP FUNCTION IF EXISTS fn_ip_pools_cidr_contains()")
    op.execute(
        "ALTER TABLE ip_pools "
        "DROP CONSTRAINT IF EXISTS excl_ip_pools_network_id_address_range"
    )
    op.drop_index("ix_ip_pools_deleted_at", table_name="ip_pools")
    op.drop_index("ix_ip_pools_allocation_mode", table_name="ip_pools")
    op.drop_index("ix_ip_pools_network_id", table_name="ip_pools")
    op.drop_index("uq_ip_pools_network_id_name_key", table_name="ip_pools")
    op.drop_table("ip_pools")
    # btree_gist is intentionally NOT dropped (F001 DB-D4); it is shared.