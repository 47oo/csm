"""baseline: enable required extensions (no business tables).

Revision ID: 0001_baseline
Revises:
Create Date: 2026-10-06

Per DB-D1..DB-D4: the only extension enabled by the baseline is ``pg_trgm``
(DB-D2). ``btree_gist`` is intentionally NOT enabled here and is deferred to
F008/F009. ``downgrade`` is intentionally asymmetric and does NOT drop the
extension; see docs/database/f001-baseline.md §4.
"""

from __future__ import annotations

from alembic import op

revision = "0001_baseline"
down_revision = None
branch_labels = None
depends_on = None

# Baseline declared extension set = {pg_trgm} (DB-D2).
EXTENSIONS = [("pg_trgm", "public")]


def upgrade() -> None:
    for name, schema in EXTENSIONS:
        op.execute(f"CREATE EXTENSION IF NOT EXISTS {name} WITH SCHEMA {schema}")


def downgrade() -> None:
    # Intentionally asymmetric: extensions are NOT dropped here.
    # See docs/database/f001-baseline.md §4 (DB-D4).
    pass