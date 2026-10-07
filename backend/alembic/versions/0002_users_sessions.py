"""users and user_sessions for F002 auth.

Revision ID: 0002_users_sessions
Revises: 0001_baseline
Create Date: 2026-10-06

Schema per docs/database/f002-auth.md v1 (DB-D13..DB-D19). Constraint names
are wrapped in ``op.f()`` so the ``Base.metadata`` naming convention is NOT
re-applied on top of the fully-qualified names from the database design
(``op.create_table`` would otherwise expand named CHECK constraints to e.g.
``ck_users_ck_users_role``). The migration only creates schema; it never writes
business data (DR-12) — the initial ADMIN is created by
``app.cli.bootstrap_admin``.
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "0002_users_sessions"
down_revision = "0001_baseline"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("username", sa.String(length=64), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column(
            "status",
            sa.String(length=16),
            server_default=sa.text("'ACTIVE'"),
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
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
        sa.UniqueConstraint("username", name=op.f("uq_users_username")),
        sa.CheckConstraint(
            "username ~ '^[a-z0-9._-]{3,64}$'",
            name=op.f("ck_users_username_format"),
        ),
        sa.CheckConstraint(
            "role IN ('VIEWER','EDITOR','ADMIN')", name=op.f("ck_users_role")
        ),
        sa.CheckConstraint(
            "status IN ('ACTIVE','DISABLED')", name=op.f("ck_users_status")
        ),
        sa.CheckConstraint("version >= 1", name=op.f("ck_users_version")),
        sa.CheckConstraint(
            "length(btrim(password_hash)) > 0",
            name=op.f("ck_users_password_hash_nonempty"),
        ),
    )
    op.create_table(
        "user_sessions",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("user_id", UUID(as_uuid=True), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_user_sessions")),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_user_sessions_user_id_users"),
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("token_hash", name=op.f("uq_user_sessions_token_hash")),
        sa.CheckConstraint(
            "token_hash ~ '^[0-9a-f]{64}$'",
            name=op.f("ck_user_sessions_token_hash_format"),
        ),
        sa.CheckConstraint(
            "expires_at > created_at",
            name=op.f("ck_user_sessions_expires_after_created"),
        ),
    )
    op.create_index("ix_user_sessions_user_id", "user_sessions", ["user_id"])
    op.create_index("ix_user_sessions_expires_at", "user_sessions", ["expires_at"])


def downgrade() -> None:
    op.drop_index("ix_user_sessions_expires_at", table_name="user_sessions")
    op.drop_index("ix_user_sessions_user_id", table_name="user_sessions")
    op.drop_table("user_sessions")
    op.drop_table("users")