"""interfaces for F007.

Revision ID: 0007_interfaces
Revises: 0006_virtual_machine_details
Create Date: 2026-10-09

Schema per docs/database/f007-interface.md v1 (DB-D64..DB-D79). Constraint,
index and trigger names are wrapped in ``op.f()``/written explicitly so the
``Base.metadata`` naming convention is NOT re-applied (see ``0004_resources``).
Autogenerate does not detect CHECK constraints or triggers, so the full object
set is written explicitly.

Key points:
- ``interfaces`` is an independent addressable object: its PK is its own UUID
  and ``resource_id`` is a ``NOT NULL`` FK to ``resources(id)``
  ``ON DELETE RESTRICT`` (a physical Resource delete is refused while an
  Interface points at it) plus ``ix_interfaces_resource_id`` (list filter +
  reference check + FK; PostgreSQL does not auto-index FK referencing columns).
- ``uq_interfaces_resource_id_name`` is a *partial* unique index
  ``(resource_id, name) WHERE deleted_at IS NULL``: same-Resource names are
  unique among undeleted rows, case-sensitive, soft delete releases the name.
  No separate normalisation key column (DB-D65/I-3): ``name`` is already stored
  trimmed and case-preserving.
- ``parent_interface_id`` is a nullable self-referential FK to ``interfaces(id)``
  ``ON DELETE RESTRICT`` + ``ix_interfaces_parent_interface_id`` + a
  non-self-reference CHECK. ``trg_interfaces_parent_valid`` rejects a
  cross-Resource / soft-deleted parent and any parent chain that would form a
  cycle (recursive CTE, ``UNION`` bounded); a missing referenced row is left to
  the FK.
- ``trg_interfaces_immutable_resource`` rejects ``id``/``resource_id`` changes
  (``restrict_violation``); the application returns 422 first.
- No backfill (the table is new); structurally symmetric downgrade, but
  Interface data is not recoverable (production rollback uses a F001
  full-database backup, docs/database/f007-interface.md §5/I-6).
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "0007_interfaces"
down_revision = "0006_virtual_machine_details"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ① Table: columns + PK + two FKs + all CHECKs.
    op.create_table(
        "interfaces",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("resource_id", UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column(
            "interface_type",
            sa.String(length=16),
            server_default=sa.text("'OTHER'"),
            nullable=False,
        ),
        sa.Column("mac_address", sa.String(length=64), nullable=True),
        sa.Column("speed_mbps", sa.Integer(), nullable=True),
        sa.Column("mtu", sa.Integer(), nullable=True),
        sa.Column("parent_interface_id", UUID(as_uuid=True), nullable=True),
        sa.Column(
            "enabled",
            sa.Boolean(),
            server_default=sa.text("true"),
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
        sa.PrimaryKeyConstraint("id", name=op.f("pk_interfaces")),
        sa.ForeignKeyConstraint(
            ["resource_id"],
            ["resources.id"],
            name=op.f("fk_interfaces_resource_id_resources"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["parent_interface_id"],
            ["interfaces.id"],
            name=op.f("fk_interfaces_parent_interface_id_interfaces"),
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "btrim(name) <> ''", name=op.f("ck_interfaces_name_not_blank")
        ),
        sa.CheckConstraint(
            "name = btrim(name)", name=op.f("ck_interfaces_name_trimmed")
        ),
        sa.CheckConstraint(
            "name !~ '[[:space:][:cntrl:]]'",
            name=op.f("ck_interfaces_name_no_ws_control"),
        ),
        sa.CheckConstraint(
            "char_length(name) BETWEEN 1 AND 64",
            name=op.f("ck_interfaces_name_length"),
        ),
        sa.CheckConstraint(
            "interface_type IN ('PHYSICAL','VIRTUAL','BOND','BRIDGE',"
            "'VLAN','LOOPBACK','OTHER')",
            name=op.f("ck_interfaces_interface_type"),
        ),
        sa.CheckConstraint(
            "mac_address IS NULL OR "
            "(mac_address = btrim(mac_address) AND btrim(mac_address) <> '' "
            "AND mac_address !~ '[[:cntrl:]]')",
            name=op.f("ck_interfaces_mac_address_format"),
        ),
        sa.CheckConstraint(
            "speed_mbps IS NULL OR (speed_mbps BETWEEN 1 AND 2147483647)",
            name=op.f("ck_interfaces_speed_mbps_range"),
        ),
        sa.CheckConstraint(
            "mtu IS NULL OR (mtu BETWEEN 1 AND 2147483647)",
            name=op.f("ck_interfaces_mtu_range"),
        ),
        sa.CheckConstraint(
            "parent_interface_id IS NULL OR parent_interface_id <> id",
            name=op.f("ck_interfaces_parent_not_self"),
        ),
        sa.CheckConstraint(
            "jsonb_typeof(metadata) = 'object'",
            name=op.f("ck_interfaces_metadata_object"),
        ),
        sa.CheckConstraint("version >= 1", name=op.f("ck_interfaces_version")),
    )

    # ② Partial unique: same-Resource name is unique only among undeleted rows.
    op.create_index(
        "uq_interfaces_resource_id_name",
        "interfaces",
        ["resource_id", "name"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )

    # ③ FK / parent filter indexes.
    op.create_index("ix_interfaces_resource_id", "interfaces", ["resource_id"])
    op.create_index(
        "ix_interfaces_parent_interface_id", "interfaces", ["parent_interface_id"]
    )

    # ④ Parent correctness trigger (self-reference / cross-Resource / soft-deleted
    #    parent / cycle). A missing referenced row is left to the FK.
    op.execute(
        """
        CREATE OR REPLACE FUNCTION fn_interfaces_parent_valid()
        RETURNS trigger AS $$
        BEGIN
            IF NEW.parent_interface_id IS NOT NULL
               AND EXISTS (
                   SELECT 1 FROM interfaces WHERE id = NEW.parent_interface_id
               ) THEN
                IF NEW.parent_interface_id = NEW.id THEN
                    RAISE EXCEPTION 'interfaces.parent_interface_id must not reference itself'
                        USING ERRCODE = 'restrict_violation';
                END IF;
                IF NOT EXISTS (
                    SELECT 1 FROM interfaces
                    WHERE id = NEW.parent_interface_id
                      AND resource_id = NEW.resource_id
                      AND deleted_at IS NULL
                ) THEN
                    RAISE EXCEPTION
                        'interfaces parent must be an undeleted interface of the same resource'
                        USING ERRCODE = 'restrict_violation';
                END IF;
                IF EXISTS (
                    WITH RECURSIVE ancestors(id, parent_interface_id) AS (
                        SELECT id, parent_interface_id FROM interfaces
                         WHERE id = NEW.parent_interface_id
                        UNION
                        SELECT i.id, i.parent_interface_id
                          FROM interfaces i
                          JOIN ancestors a ON i.id = a.parent_interface_id
                    )
                    SELECT 1 FROM ancestors WHERE id = NEW.id
                ) THEN
                    RAISE EXCEPTION 'interfaces parent chain must not form a cycle'
                        USING ERRCODE = 'restrict_violation';
                END IF;
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_interfaces_parent_valid
        BEFORE INSERT OR UPDATE ON interfaces
        FOR EACH ROW EXECUTE FUNCTION fn_interfaces_parent_valid();
        """
    )

    # ⑤ Ownership immutability trigger (id/resource_id).
    op.execute(
        """
        CREATE OR REPLACE FUNCTION fn_interfaces_immutable_resource()
        RETURNS trigger AS $$
        BEGIN
            IF NEW.id IS DISTINCT FROM OLD.id
               OR NEW.resource_id IS DISTINCT FROM OLD.resource_id THEN
                RAISE EXCEPTION 'interfaces.id/resource_id are immutable'
                    USING ERRCODE = 'restrict_violation';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_interfaces_immutable_resource
        BEFORE UPDATE ON interfaces
        FOR EACH ROW EXECUTE FUNCTION fn_interfaces_immutable_resource();
        """
    )


def downgrade() -> None:
    op.execute(
        "DROP TRIGGER IF EXISTS trg_interfaces_immutable_resource ON interfaces"
    )
    op.execute("DROP FUNCTION IF EXISTS fn_interfaces_immutable_resource()")
    op.execute("DROP TRIGGER IF EXISTS trg_interfaces_parent_valid ON interfaces")
    op.execute("DROP FUNCTION IF EXISTS fn_interfaces_parent_valid()")
    op.drop_index("ix_interfaces_parent_interface_id", table_name="interfaces")
    op.drop_index("ix_interfaces_resource_id", table_name="interfaces")
    op.drop_index("uq_interfaces_resource_id_name", table_name="interfaces")
    op.drop_table("interfaces")