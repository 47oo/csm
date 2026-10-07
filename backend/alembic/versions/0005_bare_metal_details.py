"""bare_metal_details for F005.

Revision ID: 0005_bare_metal_details
Revises: 0004_resources
Create Date: 2026-10-09

Schema per docs/database/f005-bare-metal.md v1 (DB-D45..DB-D52). Constraint
names are wrapped in ``op.f()`` so the ``Base.metadata`` naming convention is
NOT re-applied (see ``0004_resources``). Autogenerate does not detect CHECK
constraints or triggers, so the full object set is written explicitly.

Key points:
- ``resource_id`` is both the primary key (1:1, so a Resource has at most one
  detail row) and an FK to ``resources(id)`` ``ON DELETE CASCADE`` (a physical
  delete of the Resource removes the detail; logical deletes never do).
- The only allowed owner is a ``BARE_METAL`` Resource. The trigger
  ``trg_bare_metal_details_type_match`` raises ``restrict_violation`` when the
  referenced Resource exists and is not ``BARE_METAL``. A missing
  ``resource_id`` is left to the FK so it is reported as a foreign-key
  violation (V-DB-37), not masked by the type check. ``resource_type`` is
  immutable on ``resources`` (0004 trigger), so no reverse trigger is needed.
- ``metadata`` is ``jsonb NOT NULL DEFAULT '{}'`` with an object CHECK; the ORM
  maps it to the ``meta`` attribute.
- No ``deleted_at`` / ``version`` / timestamp columns (DB-D48): the detail is a
  lifecycle-bound 1:1 child, history is carried by the Resource audit trail and
  concurrency by ``resources.version``.
- Backfill: every existing BARE_METAL Resource gets an all-null row with
  ``metadata = '{}'``; VMs get none.

Downgrade drops objects in reverse order; symmetric structurally but detail
data is not recoverable (production rollback uses a F001 full-database backup,
docs/database/f005-bare-metal.md §6/I-6).
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "0005_bare_metal_details"
down_revision = "0004_resources"
branch_labels = None
depends_on = None

_HARDWARE_STRING = ("manufacturer", "model", "serial_number", "cpu_model", "gpu_model")


def _string_format_check(column: str) -> str:
    # NULL allowed; otherwise already trimmed and non-empty. Unicode Cc/Cf is an
    # application responsibility (DB backstop is ASCII-only), per F003 I-6 /
    # F004 I-4.
    return (
        f"{column} IS NULL OR "
        f"({column} = btrim({column}) AND btrim({column}) <> '')"
    )


def upgrade() -> None:
    op.create_table(
        "bare_metal_details",
        sa.Column("resource_id", UUID(as_uuid=True), nullable=False),
        *(
            sa.Column(column, sa.String(length=255), nullable=True)
            for column in _HARDWARE_STRING
        ),
        sa.Column("cpu_sockets", sa.Integer(), nullable=True),
        sa.Column("cpu_cores", sa.Integer(), nullable=True),
        sa.Column("memory_mb", sa.Integer(), nullable=True),
        sa.Column("gpu_count", sa.Integer(), nullable=True),
        sa.Column(
            "metadata",
            JSONB(),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("resource_id", name=op.f("pk_bare_metal_details")),
        sa.ForeignKeyConstraint(
            ["resource_id"],
            ["resources.id"],
            name=op.f("fk_bare_metal_details_resource_id_resources"),
            ondelete="CASCADE",
        ),
        *(
            sa.CheckConstraint(
                _string_format_check(column),
                name=op.f(f"ck_bare_metal_details_{column}_format"),
            )
            for column in _HARDWARE_STRING
        ),
        sa.CheckConstraint(
            "cpu_sockets IS NULL OR (cpu_sockets >= 1 AND cpu_sockets <= 2147483647)",
            name=op.f("ck_bare_metal_details_cpu_sockets_range"),
        ),
        sa.CheckConstraint(
            "cpu_cores IS NULL OR (cpu_cores >= 1 AND cpu_cores <= 2147483647)",
            name=op.f("ck_bare_metal_details_cpu_cores_range"),
        ),
        sa.CheckConstraint(
            "memory_mb IS NULL OR (memory_mb >= 1 AND memory_mb <= 2147483647)",
            name=op.f("ck_bare_metal_details_memory_mb_range"),
        ),
        sa.CheckConstraint(
            "gpu_count IS NULL OR (gpu_count >= 0 AND gpu_count <= 2147483647)",
            name=op.f("ck_bare_metal_details_gpu_count_range"),
        ),
        sa.CheckConstraint(
            "jsonb_typeof(metadata) = 'object'",
            name=op.f("ck_bare_metal_details_metadata_object"),
        ),
    )

    op.execute(
        """
        CREATE OR REPLACE FUNCTION fn_bare_metal_details_type_match()
        RETURNS trigger AS $$
        BEGIN
            IF EXISTS (SELECT 1 FROM resources WHERE id = NEW.resource_id)
               AND NOT EXISTS (
                   SELECT 1 FROM resources
                   WHERE id = NEW.resource_id AND resource_type = 'BARE_METAL'
               ) THEN
                RAISE EXCEPTION 'bare_metal_details requires a BARE_METAL resource'
                    USING ERRCODE = 'restrict_violation';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_bare_metal_details_type_match
        BEFORE INSERT OR UPDATE ON bare_metal_details
        FOR EACH ROW EXECUTE FUNCTION fn_bare_metal_details_type_match();
        """
    )

    # Backfill: each pre-existing BARE_METAL Resource gets an all-null detail row.
    op.execute(
        """
        INSERT INTO bare_metal_details (resource_id)
        SELECT id FROM resources WHERE resource_type = 'BARE_METAL'
        """
    )


def downgrade() -> None:
    op.execute(
        "DROP TRIGGER IF EXISTS trg_bare_metal_details_type_match "
        "ON bare_metal_details"
    )
    op.execute("DROP FUNCTION IF EXISTS fn_bare_metal_details_type_match()")
    op.drop_table("bare_metal_details")