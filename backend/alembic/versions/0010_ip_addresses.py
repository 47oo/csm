"""ip_addresses for F010.

Revision ID: 0010_ip_addresses
Revises: 0009_ip_pools
Create Date: 2026-10-09

Schema per docs/database/f010-ip-address.md v1 (DB-D111..DB-D127). Constraint,
index and trigger names are written explicitly / wrapped in ``op.f()`` so the
``Base.metadata`` naming convention is NOT re-applied (see ``0004_resources``).

Key points:
- ``ip_addresses`` is an independent addressable object (own UUID PK/version/
  soft-delete/restore/Activity); ``network_id`` and ``cluster_id`` are ordinary
  ``NOT NULL`` FKs ``ON DELETE RESTRICT``. ``cluster_id`` is a redundant carrier
  for the same-Cluster uniqueness scope (``networks.cluster_id``); its
  consistency is enforced by ``trg_ip_addresses_cluster_consistent``.
- ``address`` is a PG ``inet`` IPv4 host address (``family=4 AND masklen=32``),
  never in a §11.1 disabled range (``ck_ip_addresses_address_host`` /
  ``ck_ip_addresses_address_not_disabled``); CIDR containment / non
  network-broadcast is the ``trg_ip_addresses_cidr_contains`` backstop.
- ``uq_ip_addresses_cluster_id_address`` is a *partial* unique index
  ``(cluster_id, address) WHERE deleted_at IS NULL``: same-Cluster addresses are
  unique among undeleted rows, cross-Cluster duplicates allowed, soft delete
  releases the address and a restore re-enters the index.
- ``trg_ip_addresses_interface_cluster`` requires a bound Interface's Resource
  to share the IP's Cluster (soft-delete validity stays an application concern).
- ``ip_pool_id`` is a nullable FK carrying the allocation-source history
  (F009 DB-D105): pool delete/shrink never reclaims the IP (§12/§21 exception).
- No backfill (the table is new); symmetric downgrade that does NOT drop
  btree_gist (F001 DB-D4). Address data is not recoverable on downgrade
  (production rollback uses a F001 full-database backup, DB-D127).
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import INET, UUID

revision = "0010_ip_addresses"
down_revision = "0009_ip_pools"
branch_labels = None
depends_on = None

# The redundant ``cluster_id`` consistency backstop (DB-D121). Mirrors F009's
# ``fn_ip_pools_cidr_contains`` shape: lock the owning networks row ``FOR KEY
# SHARE`` so it serialises with ``_lock_network`` (FOR UPDATE).
_CLUSTER_CONSISTENT_FUNCTION = """
CREATE OR REPLACE FUNCTION fn_ip_addresses_cluster_consistent()
RETURNS trigger AS $$
DECLARE
    net_cluster uuid;
BEGIN
    SELECT n.cluster_id INTO net_cluster
      FROM networks n
     WHERE n.id = NEW.network_id
     FOR KEY SHARE;
    IF NOT FOUND THEN
        -- Network row missing: let the FK report the error.
        RETURN NEW;
    END IF;
    IF NEW.cluster_id IS DISTINCT FROM net_cluster THEN
        RAISE EXCEPTION
            'ip_addresses.cluster_id must equal the owning network cluster'
            USING ERRCODE = 'restrict_violation';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql
"""

# The cross-table CIDR containment / non network-broadcast backstop (DB-D120).
# ``<<=`` so a /32 Network accepts its single address; /31 both addresses are
# usable; /0-/30 exclude the network and broadcast addresses.
_CIDR_CONTAINS_FUNCTION = """
CREATE OR REPLACE FUNCTION fn_ip_addresses_cidr_contains()
RETURNS trigger AS $$
DECLARE
    net_cidr cidr;
BEGIN
    SELECT n.cidr INTO net_cidr
      FROM networks n
     WHERE n.id = NEW.network_id
     FOR KEY SHARE;
    IF NOT FOUND THEN
        -- Network row missing: let the FK report the error.
        RETURN NEW;
    END IF;
    IF NOT (NEW.address <<= net_cidr::inet) THEN
        RAISE EXCEPTION
            'ip_addresses.address must belong to the owning network CIDR'
            USING ERRCODE = 'restrict_violation';
    END IF;
    IF masklen(net_cidr) <= 30
       AND (NEW.address = host(network(net_cidr))::inet
            OR NEW.address = host(broadcast(net_cidr))::inet) THEN
        RAISE EXCEPTION
            'ip_addresses.address must not be the network/broadcast address'
            USING ERRCODE = 'restrict_violation';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql
"""

# The bound-Interface Cluster consistency backstop (DB-D122); soft-deleted
# Interfaces are an application concern (422 dependency/reference checks).
_INTERFACE_CLUSTER_FUNCTION = """
CREATE OR REPLACE FUNCTION fn_ip_addresses_interface_cluster()
RETURNS trigger AS $$
DECLARE
    res_cluster uuid;
BEGIN
    IF NEW.interface_id IS NULL THEN
        RETURN NEW;
    END IF;
    SELECT r.cluster_id INTO res_cluster
      FROM interfaces i
      JOIN resources r ON r.id = i.resource_id
     WHERE i.id = NEW.interface_id;
    IF NOT FOUND THEN
        -- Interface row missing: let the FK report the error.
        RETURN NEW;
    END IF;
    IF res_cluster IS DISTINCT FROM NEW.cluster_id THEN
        RAISE EXCEPTION
            'bound interface resource must be in the same cluster as the IP'
            USING ERRCODE = 'restrict_violation';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql
"""


def upgrade() -> None:
    # ① Table: columns + PK + 4 FK + 3 CHECK.
    op.create_table(
        "ip_addresses",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("network_id", UUID(as_uuid=True), nullable=False),
        sa.Column("cluster_id", UUID(as_uuid=True), nullable=False),
        sa.Column("address", INET(), nullable=False),
        sa.Column("interface_id", UUID(as_uuid=True), nullable=True),
        sa.Column("ip_pool_id", UUID(as_uuid=True), nullable=True),
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
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ip_addresses")),
        sa.ForeignKeyConstraint(
            ["network_id"],
            ["networks.id"],
            name=op.f("fk_ip_addresses_network_id_networks"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["cluster_id"],
            ["clusters.id"],
            name=op.f("fk_ip_addresses_cluster_id_clusters"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["interface_id"],
            ["interfaces.id"],
            name=op.f("fk_ip_addresses_interface_id_interfaces"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["ip_pool_id"],
            ["ip_pools.id"],
            name=op.f("fk_ip_addresses_ip_pool_id_ip_pools"),
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "family(address) = 4 AND masklen(address) = 32",
            name=op.f("ck_ip_addresses_address_host"),
        ),
        sa.CheckConstraint(
            "NOT ("
            "address << '0.0.0.0/8'::inet "
            "OR address << '127.0.0.0/8'::inet "
            "OR address << '169.254.0.0/16'::inet "
            "OR address << '224.0.0.0/4'::inet "
            "OR address << '240.0.0.0/4'::inet)",
            name=op.f("ck_ip_addresses_address_not_disabled"),
        ),
        sa.CheckConstraint("version >= 1", name=op.f("ck_ip_addresses_version")),
    )

    # ② Partial unique: same-Cluster address is unique only among undeleted rows.
    op.create_index(
        "uq_ip_addresses_cluster_id_address",
        "ip_addresses",
        ["cluster_id", "address"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )

    # ③ Filter/FK indexes. No pg_trgm/GIN, no address single-column B-tree
    #    (DB-D124).
    op.create_index("ix_ip_addresses_network_id", "ip_addresses", ["network_id"])
    op.create_index("ix_ip_addresses_cluster_id", "ip_addresses", ["cluster_id"])
    op.create_index("ix_ip_addresses_interface_id", "ip_addresses", ["interface_id"])
    op.create_index("ix_ip_addresses_ip_pool_id", "ip_addresses", ["ip_pool_id"])
    op.create_index("ix_ip_addresses_deleted_at", "ip_addresses", ["deleted_at"])

    # ④ Cluster consistency backstop.
    op.execute(_CLUSTER_CONSISTENT_FUNCTION)
    op.execute(
        "CREATE TRIGGER trg_ip_addresses_cluster_consistent "
        "BEFORE INSERT OR UPDATE ON ip_addresses "
        "FOR EACH ROW EXECUTE FUNCTION fn_ip_addresses_cluster_consistent()"
    )

    # ⑤ CIDR containment / non network-broadcast backstop.
    op.execute(_CIDR_CONTAINS_FUNCTION)
    op.execute(
        "CREATE TRIGGER trg_ip_addresses_cidr_contains "
        "BEFORE INSERT OR UPDATE ON ip_addresses "
        "FOR EACH ROW EXECUTE FUNCTION fn_ip_addresses_cidr_contains()"
    )

    # ⑥ Bound-Interface Cluster consistency backstop.
    op.execute(_INTERFACE_CLUSTER_FUNCTION)
    op.execute(
        "CREATE TRIGGER trg_ip_addresses_interface_cluster "
        "BEFORE INSERT OR UPDATE ON ip_addresses "
        "FOR EACH ROW EXECUTE FUNCTION fn_ip_addresses_interface_cluster()"
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_ip_addresses_interface_cluster ON ip_addresses")
    op.execute("DROP FUNCTION IF EXISTS fn_ip_addresses_interface_cluster()")
    op.execute("DROP TRIGGER IF EXISTS trg_ip_addresses_cidr_contains ON ip_addresses")
    op.execute("DROP FUNCTION IF EXISTS fn_ip_addresses_cidr_contains()")
    op.execute("DROP TRIGGER IF EXISTS trg_ip_addresses_cluster_consistent ON ip_addresses")
    op.execute("DROP FUNCTION IF EXISTS fn_ip_addresses_cluster_consistent()")
    op.drop_index("ix_ip_addresses_deleted_at", table_name="ip_addresses")
    op.drop_index("ix_ip_addresses_ip_pool_id", table_name="ip_addresses")
    op.drop_index("ix_ip_addresses_interface_id", table_name="ip_addresses")
    op.drop_index("ix_ip_addresses_cluster_id", table_name="ip_addresses")
    op.drop_index("ix_ip_addresses_network_id", table_name="ip_addresses")
    op.drop_index("uq_ip_addresses_cluster_id_address", table_name="ip_addresses")
    op.drop_table("ip_addresses")
    # btree_gist / pg_trgm are intentionally NOT dropped (F001 DB-D4); shared.