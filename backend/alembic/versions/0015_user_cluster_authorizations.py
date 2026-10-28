"""user_cluster_authorizations table and backfill for F026.

Revision ID: 0015_user_cluster_authorizations
Revises: 0014_api_keys
Create Date: 2026-10-21

Schema per docs/database/f026-cluster-authorization.md v1 (DB-D401..DB-D420).
Hand-written DDL: autogenerate does not recognise the partial unique index,
``gen_random_uuid()``, CHECK expressions or triggers. The partial unique index
enforces "at most one active row per (user, cluster)"; historical revoked rows
remain. Backfill grants every existing non-ADMIN account every existing Cluster
(including soft-deleted Clusters and DISABLED accounts) and asserts the expected
counts; any mismatch aborts the migration and rolls back atomically.

Downgrade is destructive: it drops the F026-owned table (all grant/revoke
history). Production rollback uses an F001 backup; ``downgrade`` is for
development/test up/down/up only (DB-D417).
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "0015_user_cluster_authorizations"
down_revision = "0014_api_keys"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_cluster_authorizations",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("user_id", UUID(as_uuid=True), nullable=False),
        sa.Column("cluster_id", UUID(as_uuid=True), nullable=False),
        sa.Column(
            "granted_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("granted_by", UUID(as_uuid=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_by", UUID(as_uuid=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_user_cluster_authorizations")),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_user_cluster_authorizations_user_id_users"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["cluster_id"],
            ["clusters.id"],
            name=op.f("fk_user_cluster_authorizations_cluster_id_clusters"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["granted_by"],
            ["users.id"],
            name=op.f("fk_user_cluster_authorizations_granted_by_users"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["revoked_by"],
            ["users.id"],
            name=op.f("fk_user_cluster_authorizations_revoked_by_users"),
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "(revoked_at IS NULL) = (revoked_by IS NULL)",
            name=op.f("ck_user_cluster_authorizations_revoked_pair"),
        ),
        sa.CheckConstraint(
            "revoked_at IS NULL OR revoked_at >= granted_at",
            name=op.f("ck_user_cluster_authorizations_revoked_after_granted"),
        ),
    )

    op.create_index(
        "uq_user_cluster_authorizations_user_id_cluster_id",
        "user_cluster_authorizations",
        ["user_id", "cluster_id"],
        unique=True,
        postgresql_where=sa.text("revoked_at IS NULL"),
    )
    op.create_index(
        "ix_user_cluster_authorizations_user_id",
        "user_cluster_authorizations",
        ["user_id"],
    )
    op.create_index(
        "ix_user_cluster_authorizations_cluster_id",
        "user_cluster_authorizations",
        ["cluster_id"],
    )

    op.execute(
        """
        CREATE OR REPLACE FUNCTION fn_user_cluster_authorizations_immutable()
        RETURNS trigger AS $$
        BEGIN
            IF NEW.id IS DISTINCT FROM OLD.id
               OR NEW.user_id IS DISTINCT FROM OLD.user_id
               OR NEW.cluster_id IS DISTINCT FROM OLD.cluster_id
               OR NEW.granted_at IS DISTINCT FROM OLD.granted_at
               OR NEW.granted_by IS DISTINCT FROM OLD.granted_by THEN
                RAISE EXCEPTION 'user_cluster_authorizations attribution and grant facts are immutable'
                    USING ERRCODE = 'check_violation';
            END IF;

            IF OLD.revoked_at IS NOT NULL THEN
                RAISE EXCEPTION 'user_cluster_authorizations is already revoked'
                    USING ERRCODE = 'check_violation';
            END IF;

            IF NEW.revoked_at IS NULL THEN
                RAISE EXCEPTION 'user_cluster_authorizations.revoked_at may only transition NULL -> NOT NULL'
                    USING ERRCODE = 'check_violation';
            END IF;

            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_user_cluster_authorizations_immutable
        BEFORE UPDATE ON user_cluster_authorizations
        FOR EACH ROW EXECUTE FUNCTION fn_user_cluster_authorizations_immutable();
        """
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION fn_user_cluster_authorizations_no_delete()
        RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'user_cluster_authorizations is append-only; revoke instead of delete'
                USING ERRCODE = 'restrict_violation';
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_user_cluster_authorizations_no_delete
        BEFORE DELETE ON user_cluster_authorizations
        FOR EACH ROW EXECUTE FUNCTION fn_user_cluster_authorizations_no_delete();
        """
    )

    # Backfill: all existing non-ADMIN accounts x all existing Clusters
    # (including soft-deleted Clusters and DISABLED accounts). NOT EXISTS uses
    # any-state rows so re-running never resurrects a revoked grant.
    op.execute(
        """
        INSERT INTO user_cluster_authorizations
            (user_id, cluster_id, granted_at, granted_by, revoked_at, revoked_by)
        SELECT u.id, c.id, now(), NULL, NULL, NULL
        FROM users u
        CROSS JOIN clusters c
        WHERE u.role <> 'ADMIN'
          AND NOT EXISTS (
              SELECT 1 FROM user_cluster_authorizations a
              WHERE a.user_id = u.id AND a.cluster_id = c.id
          )
        ON CONFLICT (user_id, cluster_id) WHERE revoked_at IS NULL DO NOTHING;
        """
    )

    bind = op.get_bind()
    expected_pairs = bind.execute(
        sa.text(
            """
            SELECT (SELECT count(*) FROM users WHERE role <> 'ADMIN')
                 * (SELECT count(*) FROM clusters)
            """
        )
    ).scalar_one()
    total_rows = bind.execute(
        sa.text("SELECT count(*) FROM user_cluster_authorizations")
    ).scalar_one()
    active_rows = bind.execute(
        sa.text(
            "SELECT count(*) FROM user_cluster_authorizations WHERE revoked_at IS NULL"
        )
    ).scalar_one()
    revoked_rows = bind.execute(
        sa.text(
            "SELECT count(*) FROM user_cluster_authorizations WHERE revoked_at IS NOT NULL"
        )
    ).scalar_one()
    admin_rows = bind.execute(
        sa.text(
            """
            SELECT count(*) FROM user_cluster_authorizations a
            JOIN users u ON u.id = a.user_id
            WHERE u.role = 'ADMIN'
            """
        )
    ).scalar_one()
    missing_pairs = bind.execute(
        sa.text(
            """
            SELECT count(*) FROM users u CROSS JOIN clusters c
            WHERE u.role <> 'ADMIN'
              AND NOT EXISTS (
                  SELECT 1 FROM user_cluster_authorizations a
                  WHERE a.user_id = u.id AND a.cluster_id = c.id
              )
            """
        )
    ).scalar_one()
    duplicate_active = bind.execute(
        sa.text(
            """
            SELECT count(*) FROM (
                SELECT user_id, cluster_id
                FROM user_cluster_authorizations
                WHERE revoked_at IS NULL
                GROUP BY user_id, cluster_id
                HAVING count(*) > 1
            ) d
            """
        )
    ).scalar_one()

    if admin_rows != 0 or missing_pairs != 0 or duplicate_active != 0:
        raise RuntimeError(
            "F026 backfill assertion failed: admin/missing/duplicate rows detected"
        )
    if revoked_rows == 0 and (
        total_rows != expected_pairs or active_rows != expected_pairs
    ):
        raise RuntimeError(
            "F026 backfill count mismatch: "
            f"expected {expected_pairs}, total {total_rows}, active {active_rows}"
        )


def downgrade() -> None:
    op.execute(
        "DROP TRIGGER IF EXISTS trg_user_cluster_authorizations_no_delete "
        "ON user_cluster_authorizations"
    )
    op.execute(
        "DROP TRIGGER IF EXISTS trg_user_cluster_authorizations_immutable "
        "ON user_cluster_authorizations"
    )
    op.execute("DROP FUNCTION IF EXISTS fn_user_cluster_authorizations_no_delete()")
    op.execute(
        "DROP FUNCTION IF EXISTS fn_user_cluster_authorizations_immutable()"
    )
    op.drop_index(
        "ix_user_cluster_authorizations_cluster_id",
        table_name="user_cluster_authorizations",
    )
    op.drop_index(
        "ix_user_cluster_authorizations_user_id",
        table_name="user_cluster_authorizations",
    )
    op.drop_index(
        "uq_user_cluster_authorizations_user_id_cluster_id",
        table_name="user_cluster_authorizations",
    )
    op.drop_table("user_cluster_authorizations")
