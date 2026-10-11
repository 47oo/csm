"""GIN trigram search indexes for F013.

Revision ID: 0013_search_indexes
Revises: 0012_service_endpoints
Create Date: 2026-10-13

Schema per docs/database/f013-search-index.md v1 (DB-D157..DB-D166).

Key points:
- ``pg_trgm`` is already enabled by ``0001_baseline`` (DB-D2); this migration
  performs **no** extension DDL (no ``CREATE``/``DROP`` of extensions, DB-D164).
- Four **non-partial** GIN trigram indexes on already-normalised columns.
  Non-partial so the ADMIN ``deleted=include|only`` path (F013 Contract §2)
  can still use the index (DB-D162).
- ``ip_addresses`` gets **no** index (DB-D163): ``inet`` cannot use
  ``gin_trgm_ops`` and IP matching is exact-only in F013.
- No table/column/constraint/trigger changes, no backfill; structurally
  symmetric ``downgrade`` drops only the four indexes.
"""

from __future__ import annotations

from alembic import op

revision = "0013_search_indexes"
down_revision = "0012_service_endpoints"
branch_labels = None
depends_on = None


# (index name, table, column) for the four DB-D158..DB-D161 indexes.
_TRGM_INDEXES: tuple[tuple[str, str, str], ...] = (
    ("ix_resources_hostname_trgm", "resources", "hostname"),
    ("ix_clusters_code_key_trgm", "clusters", "code_key"),
    ("ix_clusters_name_trgm", "clusters", "name"),
    ("ix_services_name_key_trgm", "services", "name_key"),
)


def upgrade() -> None:
    for name, table, column in _TRGM_INDEXES:
        op.create_index(
            name,
            table,
            [column],
            unique=False,
            postgresql_using="gin",
            postgresql_ops={column: "gin_trgm_ops"},
        )


def downgrade() -> None:
    for name, table, _column in reversed(_TRGM_INDEXES):
        op.drop_index(name, table_name=table)
    # pg_trgm / btree_gist are intentionally NOT dropped (F001 DB-D4); shared.