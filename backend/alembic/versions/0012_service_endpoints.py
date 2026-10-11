"""service_endpoints for F012.

Revision ID: 0012_service_endpoints
Revises: 0011_services
Create Date: 2026-10-09

Schema per docs/database/f012-service-endpoint.md v1 (DB-D142..DB-D156).
Constraint and index names are written explicitly / wrapped in ``op.f()`` so
the ``Base.metadata`` naming convention is NOT re-applied (see ``0004_resources``).
Autogenerate does not detect CHECK constraints, so the full object set is
written explicitly.

Key points:
- ``service_endpoints`` is an independent addressable object (own UUID
  PK/version/soft-delete/restore/Activity, DR-155); ``service_id`` and
  ``ip_address_id`` are ordinary ``NOT NULL`` FKs with ``ON DELETE RESTRICT``
  plus ``ix_service_endpoints_service_id`` / ``ix_service_endpoints_ip_address_id``.
  Both are immutable after creation (application 422, DR-157); the database
  deliberately builds **no** immutable trigger (DB-D151).
- ``protocol`` is ``varchar(8) NOT NULL`` with ``ck_service_endpoints_protocol``
  (``TCP|UDP``, uppercase only, DR-160); ``port`` is ``integer NOT NULL`` with
  ``ck_service_endpoints_port`` (``1..65535``, DR-160).
- ``uq_service_endpoints_ip_protocol_port`` is a *partial* unique index
  ``(ip_address_id, protocol, port) WHERE deleted_at IS NULL`` (DR-159): same-IP
  undeleted listeners are unique, soft delete releases the tuple, and a restore
  re-enters the index.
- ``fn_service_endpoints_attribution`` / ``trg_service_endpoints_attribution``
  are the structural attribution backstop (DR-158/DB-D150): on any INSERT/UPDATE
  the IP must be bound to an Interface whose ``resource_id`` equals the
  Service's ``resource_id``; soft-delete state is NOT checked and no row lock is
  taken (application owns those checks).
- No pg_trgm/GIN and no standalone ``protocol`` index (DB-D152); the extension
  set is unchanged (this migration performs no extension DDL).
- No backfill (the table is new); structurally symmetric downgrade that does NOT
  drop pg_trgm/btree_gist (F001 DB-D4). Endpoint data is not recoverable on
  downgrade (production rollback uses a F001 full-database backup, DB-D156).
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "0012_service_endpoints"
down_revision = "0011_services"
branch_labels = None
depends_on = None


_ATTRIBUTION_FUNCTION = """
CREATE OR REPLACE FUNCTION fn_service_endpoints_attribution()
RETURNS trigger AS $$
DECLARE
    ip_interface  uuid;
    res_service   uuid;
    res_interface uuid;
BEGIN
    SELECT ia.interface_id INTO ip_interface
      FROM ip_addresses ia WHERE ia.id = NEW.ip_address_id;
    IF NOT FOUND THEN RETURN NEW; END IF;      -- 交 FK

    SELECT s.resource_id INTO res_service
      FROM services s WHERE s.id = NEW.service_id;
    IF NOT FOUND THEN RETURN NEW; END IF;      -- 交 FK

    IF ip_interface IS NULL THEN
        RAISE EXCEPTION
            'service_endpoints.ip_address_id must be bound to an interface'
            USING ERRCODE = 'restrict_violation';
    END IF;

    SELECT i.resource_id INTO res_interface
      FROM interfaces i WHERE i.id = ip_interface;
    IF NOT FOUND THEN RETURN NEW; END IF;

    IF res_interface IS DISTINCT FROM res_service THEN
        RAISE EXCEPTION
            'endpoint ip interface must belong to the service resource'
            USING ERRCODE = 'restrict_violation';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
"""

_ATTRIBUTION_TRIGGER = """
CREATE TRIGGER trg_service_endpoints_attribution
BEFORE INSERT OR UPDATE ON service_endpoints
FOR EACH ROW EXECUTE FUNCTION fn_service_endpoints_attribution();
"""


def upgrade() -> None:
    # ① Table: columns + PK + 2 FK + 3 CHECK.
    op.create_table(
        "service_endpoints",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("service_id", UUID(as_uuid=True), nullable=False),
        sa.Column("ip_address_id", UUID(as_uuid=True), nullable=False),
        sa.Column("protocol", sa.String(length=8), nullable=False),
        sa.Column("port", sa.Integer(), nullable=False),
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
        sa.PrimaryKeyConstraint("id", name=op.f("pk_service_endpoints")),
        sa.ForeignKeyConstraint(
            ["service_id"],
            ["services.id"],
            name=op.f("fk_service_endpoints_service_id_services"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["ip_address_id"],
            ["ip_addresses.id"],
            name=op.f("fk_service_endpoints_ip_address_id_ip_addresses"),
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "protocol IN ('TCP','UDP')",
            name=op.f("ck_service_endpoints_protocol"),
        ),
        sa.CheckConstraint(
            "port BETWEEN 1 AND 65535",
            name=op.f("ck_service_endpoints_port"),
        ),
        sa.CheckConstraint("version >= 1", name=op.f("ck_service_endpoints_version")),
    )

    # ② Partial unique: same-IP listener is unique only among undeleted rows.
    op.create_index(
        "uq_service_endpoints_ip_protocol_port",
        "service_endpoints",
        ["ip_address_id", "protocol", "port"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )

    # ③ Filter/index collection. No pg_trgm/GIN, no standalone protocol index
    #    (DB-D152).
    op.create_index(
        "ix_service_endpoints_service_id", "service_endpoints", ["service_id"]
    )
    op.create_index(
        "ix_service_endpoints_ip_address_id", "service_endpoints", ["ip_address_id"]
    )
    op.create_index(
        "ix_service_endpoints_deleted_at", "service_endpoints", ["deleted_at"]
    )

    # ④ Structural attribution backstop (DR-158/DB-D150).
    op.execute(_ATTRIBUTION_FUNCTION)
    op.execute(_ATTRIBUTION_TRIGGER)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_service_endpoints_attribution "
               "ON service_endpoints")
    op.execute("DROP FUNCTION IF EXISTS fn_service_endpoints_attribution()")
    op.drop_index("ix_service_endpoints_deleted_at", table_name="service_endpoints")
    op.drop_index("ix_service_endpoints_ip_address_id", table_name="service_endpoints")
    op.drop_index("ix_service_endpoints_service_id", table_name="service_endpoints")
    op.drop_index(
        "uq_service_endpoints_ip_protocol_port", table_name="service_endpoints"
    )
    op.drop_table("service_endpoints")
    # pg_trgm / btree_gist are intentionally NOT dropped (F001 DB-D4); shared.