"""T2 — 迁移后表集合白名单 + 约束 / 索引存在性 + 无显式 COLLATE。"""

from __future__ import annotations

from sqlalchemy import text

from tests.database.helpers import upgrade_to_head

EXPECTED_TABLES = {
    "alembic_version",
    "clusters",
    "users",
    "sessions",
    "bare_metals",
    "virtual_machines",
    "network_interfaces",
}


def test_expected_table_whitelist(database_url):
    engine = upgrade_to_head(database_url)
    try:
        with engine.connect() as conn:
            tables = set(
                conn.execute(
                    text(
                        "SELECT table_name FROM information_schema.tables "
                        "WHERE table_schema = 'public'"
                    )
                ).scalars()
            )
        # 白名单：不得出现 resources 等非预期表。
        assert tables == EXPECTED_TABLES
    finally:
        engine.dispose()


def test_partial_unique_index_exists_with_predicate(database_url):
    engine = upgrade_to_head(database_url)
    try:
        with engine.connect() as conn:
            row = conn.execute(
                text(
                    "SELECT indexdef FROM pg_indexes "
                    "WHERE schemaname = 'public' AND indexname = 'ux_clusters_name_active'"
                )
            ).scalar()
        assert row is not None, "ux_clusters_name_active 缺失"
        assert "UNIQUE" in row
        assert "deleted_at IS NULL" in row
    finally:
        engine.dispose()


def test_check_constraint_exists(database_url):
    engine = upgrade_to_head(database_url)
    try:
        with engine.connect() as conn:
            definition = conn.execute(
                text(
                    "SELECT pg_get_constraintdef(oid) FROM pg_constraint "
                    "WHERE conname = 'ck_clusters_name_no_slash'"
                )
            ).scalar()
        assert definition is not None, "ck_clusters_name_no_slash 缺失"
        assert "strpos" in definition
    finally:
        engine.dispose()


def test_no_explicit_collation_on_clusters_columns(database_url):
    engine = upgrade_to_head(database_url)
    try:
        with engine.connect() as conn:
            rows = (
                conn.execute(
                    text(
                        "SELECT column_name, collation_name FROM information_schema.columns "
                        "WHERE table_schema = 'public' AND table_name = 'clusters' "
                        "AND collation_name IS NOT NULL"
                    )
                )
                .mappings()
                .all()
            )
        assert rows == [], f"不应声明列级 collation：{rows}"
    finally:
        engine.dispose()
