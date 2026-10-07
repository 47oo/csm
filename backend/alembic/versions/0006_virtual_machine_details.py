"""virtual_machine_details for F006.

Revision ID: 0006_virtual_machine_details
Revises: 0005_bare_metal_details
Create Date: 2026-10-09

Schema per docs/database/f006-virtual-machine.md v1 (DB-D53..DB-D63).
Constraint/index/trigger names are wrapped in ``op.f()`` so the
``Base.metadata`` naming convention is NOT re-applied (see ``0004_resources``).
Autogenerate does not detect CHECK constraints or triggers, so the full object
set is written explicitly.

Key points:
- ``resource_id`` is both the primary key (1:1, at most one detail row per
  Resource) and an FK to ``resources(id)`` ``ON DELETE CASCADE`` (a physical
  delete of the Resource removes the detail; logical deletes never do).
- ``host_resource_id`` is ``UUID NOT NULL`` with an FK to ``resources(id)``
  ``ON DELETE RESTRICT`` (a Host is an independent referenced object; a physical
  delete is refused while a detail still points at it) plus index
  ``ix_virtual_machine_details_host_resource_id`` (list filter + reference
  check + FK RESTRICT; PostgreSQL does not auto-index FK referencing columns).
- Numeric columns are ``integer NULL``: ``vcpu``/``memory_mb`` CHECK 1..max,
  ``disk_gb`` CHECK 0..max (0 means "explicitly no disk"; NULL means unknown).
- ``hypervisor`` is ``varchar(255) NULL`` with a trim/non-empty backstop CHECK
  (Unicode Cc/Cf is an application responsibility; DB backstop is ASCII-only);
  no enum in phase 1.
- No ``metadata`` column (DB-D57 / DR-69: VM metadata is the Resource's public
  ``resources.metadata``), and no ``deleted_at`` / ``version`` / timestamp
  columns (DB-D60): the detail is a lifecycle-bound 1:1 child.
- Two BEFORE INSERT OR UPDATE triggers (DR-66):
  ``trg_virtual_machine_details_type_match`` (``resource_id`` must be a
  ``VIRTUAL_MACHINE`` Resource) and
  ``trg_virtual_machine_details_host_valid`` (``host_resource_id`` must point at
  an undeleted ``BARE_METAL`` Resource in the same cluster). A missing referenced
  row is left to the FK so it is reported as a foreign-key violation. The
  ``cluster_id``/``resource_type`` immutability on ``resources`` (0004 trigger)
  means no reverse trigger is needed.
- Backfill guard (DR-68): ``host_resource_id`` is NOT NULL and F004 allowed a
  VIRTUAL_MACHINE Resource with no Host, so there is no safe backfill value.
  ``upgrade`` raises before creating the table when an undeleted
  VIRTUAL_MACHINE Resource exists; it neither synthesises nor discards detail
  rows. V3 phase 1 has no production data, so the guard is normally a no-op.

Downgrade drops objects in reverse order; structurally symmetric, but detail
data is not recoverable (production rollback uses a F001 full-database backup,
docs/database/f006-virtual-machine.md §7/I-6).
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "0006_virtual_machine_details"
down_revision = "0005_bare_metal_details"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ① Backfill guard (DR-68): refuse a clean-looking upgrade when an undeleted
    # VIRTUAL_MACHINE Resource exists, because host_resource_id is NOT NULL and
    # there is no safe value to backfill.
    op.execute(
        """
        DO $$ DECLARE n bigint; BEGIN
            SELECT count(*) INTO n FROM resources
              WHERE resource_type = 'VIRTUAL_MACHINE' AND deleted_at IS NULL;
            IF n > 0 THEN
                RAISE EXCEPTION
                    'cannot apply 0006: % undeleted VIRTUAL_MACHINE resource(s) exist without a host; no safe backfill (DR-68).', n
                    USING ERRCODE = 'raise_exception';
            END IF;
        END $$;
        """
    )

    # ② Table: columns + PK + two FKs + four CHECKs.
    op.create_table(
        "virtual_machine_details",
        sa.Column("resource_id", UUID(as_uuid=True), nullable=False),
        sa.Column("host_resource_id", UUID(as_uuid=True), nullable=False),
        sa.Column("vcpu", sa.Integer(), nullable=True),
        sa.Column("memory_mb", sa.Integer(), nullable=True),
        sa.Column("disk_gb", sa.Integer(), nullable=True),
        sa.Column("hypervisor", sa.String(length=255), nullable=True),
        sa.PrimaryKeyConstraint("resource_id", name=op.f("pk_virtual_machine_details")),
        sa.ForeignKeyConstraint(
            ["resource_id"],
            ["resources.id"],
            name=op.f("fk_virtual_machine_details_resource_id_resources"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["host_resource_id"],
            ["resources.id"],
            name=op.f("fk_virtual_machine_details_host_resource_id_resources"),
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "vcpu IS NULL OR (vcpu >= 1 AND vcpu <= 2147483647)",
            name=op.f("ck_virtual_machine_details_vcpu_range"),
        ),
        sa.CheckConstraint(
            "memory_mb IS NULL OR (memory_mb >= 1 AND memory_mb <= 2147483647)",
            name=op.f("ck_virtual_machine_details_memory_mb_range"),
        ),
        sa.CheckConstraint(
            "disk_gb IS NULL OR (disk_gb >= 0 AND disk_gb <= 2147483647)",
            name=op.f("ck_virtual_machine_details_disk_gb_range"),
        ),
        sa.CheckConstraint(
            "hypervisor IS NULL OR "
            "(hypervisor = btrim(hypervisor) AND btrim(hypervisor) <> '')",
            name=op.f("ck_virtual_machine_details_hypervisor_format"),
        ),
    )

    # ③ Index on the host FK (list filter + reference check + FK RESTRICT).
    op.create_index(
        "ix_virtual_machine_details_host_resource_id",
        "virtual_machine_details",
        ["host_resource_id"],
    )

    # ④ Trigger functions and triggers.
    op.execute(
        """
        CREATE OR REPLACE FUNCTION fn_virtual_machine_details_type_match()
        RETURNS trigger AS $$
        BEGIN
            IF EXISTS (SELECT 1 FROM resources WHERE id = NEW.resource_id)
               AND NOT EXISTS (
                   SELECT 1 FROM resources
                   WHERE id = NEW.resource_id AND resource_type = 'VIRTUAL_MACHINE'
               ) THEN
                RAISE EXCEPTION 'virtual_machine_details requires a VIRTUAL_MACHINE resource'
                    USING ERRCODE = 'restrict_violation';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_virtual_machine_details_type_match
        BEFORE INSERT OR UPDATE ON virtual_machine_details
        FOR EACH ROW EXECUTE FUNCTION fn_virtual_machine_details_type_match();
        """
    )

    op.execute(
        """
        CREATE OR REPLACE FUNCTION fn_virtual_machine_details_host_valid()
        RETURNS trigger AS $$
        BEGIN
            -- Leave a missing referenced row to the FK so it is reported as a
            -- foreign-key violation rather than masked here.
            IF EXISTS (SELECT 1 FROM resources WHERE id = NEW.resource_id)
               AND EXISTS (SELECT 1 FROM resources WHERE id = NEW.host_resource_id)
               AND NOT EXISTS (
                   SELECT 1
                   FROM resources h
                   JOIN resources v ON v.id = NEW.resource_id
                   WHERE h.id = NEW.host_resource_id
                     AND h.resource_type = 'BARE_METAL'
                     AND h.deleted_at IS NULL
                     AND h.cluster_id = v.cluster_id
               ) THEN
                RAISE EXCEPTION 'virtual_machine_details host must be an undeleted BARE_METAL resource in the same cluster'
                    USING ERRCODE = 'restrict_violation';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_virtual_machine_details_host_valid
        BEFORE INSERT OR UPDATE ON virtual_machine_details
        FOR EACH ROW EXECUTE FUNCTION fn_virtual_machine_details_host_valid();
        """
    )


def downgrade() -> None:
    op.execute(
        "DROP TRIGGER IF EXISTS trg_virtual_machine_details_host_valid "
        "ON virtual_machine_details"
    )
    op.execute(
        "DROP TRIGGER IF EXISTS trg_virtual_machine_details_type_match "
        "ON virtual_machine_details"
    )
    op.execute("DROP FUNCTION IF EXISTS fn_virtual_machine_details_host_valid()")
    op.execute("DROP FUNCTION IF EXISTS fn_virtual_machine_details_type_match()")
    op.drop_index(
        "ix_virtual_machine_details_host_resource_id",
        table_name="virtual_machine_details",
    )
    op.drop_table("virtual_machine_details")