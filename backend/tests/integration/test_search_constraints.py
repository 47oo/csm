"""F013 search index / migration constraint evidence (DB-D157..DB-D166).

Real PostgreSQL only (DB-D10 guard in ``conftest``): migration up/down/up, the
four non-partial GIN trigram indexes and an ``EXPLAIN`` proof that a ``q`` with
>= 3 characters can use the GIN index.
"""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import text

TRGM_INDEXES = {
    "ix_resources_hostname_trgm",
    "ix_clusters_code_key_trgm",
    "ix_clusters_name_trgm",
    "ix_services_name_key_trgm",
}


def _alembic_versions(engine) -> list[str]:
    with engine.connect() as conn:
        return list(
            conn.execute(text("SELECT version_num FROM alembic_version")).scalars()
        )


def _tables(engine) -> set[str]:
    with engine.connect() as conn:
        return set(
            conn.execute(
                text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
            ).scalars()
        )


def _extensions(engine) -> set[str]:
    with engine.connect() as conn:
        return set(conn.execute(text("SELECT extname FROM pg_extension")).scalars())


def _trgm_indexes(engine) -> dict[str, dict]:
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT i.indexname, i.indexdef, ix.indisunique, ix.indisvalid "
                "FROM pg_indexes i "
                "JOIN pg_class c ON c.relname = i.indexname "
                "JOIN pg_index ix ON ix.indexrelid = c.oid "
                "WHERE i.schemaname = 'public' "
                "AND i.indexname = ANY(:names)"
            ),
            {"names": list(TRGM_INDEXES)},
        ).mappings().all()
    return {row["indexname"]: dict(row) for row in rows}


def test_migration_0013_up_down_up_single_head(pg_engine, alembic_runner):
    """V-DB-139/143: single head, symmetric up/down/up, extensions unchanged."""
    assert alembic_runner.head_revision() == "0014_api_keys"
    assert _alembic_versions(pg_engine) == ["0014_api_keys"]
    extensions_before = _extensions(pg_engine)
    assert "pg_trgm" in extensions_before
    assert set(_trgm_indexes(pg_engine)) == TRGM_INDEXES

    alembic_runner.downgrade("0012_service_endpoints")
    assert set(_trgm_indexes(pg_engine)) == set()
    assert "resources" in _tables(pg_engine)
    assert _alembic_versions(pg_engine) == ["0012_service_endpoints"]
    assert _extensions(pg_engine) == extensions_before

    alembic_runner.upgrade("head")
    assert set(_trgm_indexes(pg_engine)) == TRGM_INDEXES
    assert _alembic_versions(pg_engine) == ["0014_api_keys"]
    assert _extensions(pg_engine) == extensions_before


def test_migration_0013_has_no_extension_ddl():
    """V-DB-143: 0013 must not enable/disable any extension (DB-D164)."""
    source = (
        Path(__file__).resolve().parents[2]
        / "alembic"
        / "versions"
        / "0013_search_indexes.py"
    ).read_text()
    assert "CREATE EXTENSION" not in source.upper()
    assert "DROP EXTENSION" not in source.upper()
    assert 'down_revision = "0012_service_endpoints"' in source


def test_trgm_indexes_are_non_partial_gin(committed_engine):
    """V-DB-140: four non-unique, non-partial GIN trigram indexes (DB-D158..162)."""
    indexes = _trgm_indexes(committed_engine)
    assert set(indexes) == TRGM_INDEXES
    assert len(indexes) == 4
    for name, row in indexes.items():
        assert "USING gin" in row["indexdef"], name
        assert "gin_trgm_ops" in row["indexdef"], name
        assert row["indisunique"] is False, name
        assert row["indisvalid"] is True, name
        assert "WHERE" not in row["indexdef"].upper(), name


def test_ip_table_has_no_trgm_index(committed_engine):
    """DB-D163: F013 builds no index on ip_addresses."""
    with committed_engine.connect() as conn:
        gin = conn.execute(
            text(
                "SELECT indexname FROM pg_indexes WHERE schemaname = 'public' "
                "AND tablename = 'ip_addresses' AND indexdef ILIKE '%USING gin%'"
            )
        ).scalars().all()
    assert gin == []


def test_explain_uses_gin_for_long_enough_query(committed_engine):
    """V-DB-142: a >= 3 character pattern can use the GIN trigram index."""
    with committed_engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO clusters (code, code_key, name) "
                "VALUES ('C1', 'C1', 'c1')"
            )
        )
        conn.execute(
            text(
                "INSERT INTO resources (cluster_id, hostname, hostname_key, resource_type) "
                "SELECT (SELECT id FROM clusters WHERE code='C1'), "
                "'filler-' || lpad(g::text, 5, '0'), "
                "'filler-' || lpad(g::text, 5, '0'), 'BARE_METAL' "
                "FROM generate_series(1, 50000) AS g"
            )
        )
        conn.execute(
            text(
                "INSERT INTO resources (cluster_id, hostname, hostname_key, resource_type) "
                "SELECT (SELECT id FROM clusters WHERE code='C1'), "
                "'needle-xyz', 'needle-xyz', 'BARE_METAL'"
            )
        )
        conn.execute(text("ANALYZE resources"))
        plan = "\n".join(
            conn.execute(
                text(
                    "EXPLAIN (ANALYZE, COSTS OFF) "
                    "SELECT hostname FROM resources "
                    "WHERE hostname ILIKE '%needle-xyz%'"
                )
            ).scalars().all()
        )
    assert "Bitmap Index Scan on ix_resources_hostname_trgm" in plan, plan
    assert "Recheck Cond" in plan


def test_explain_uses_gin_for_cluster_and_service(committed_engine):
    """V-DB-142: cluster code/name and service name_key GIN indexes are usable."""
    with committed_engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO clusters (code, code_key, name) "
                "SELECT 'FIL' || lpad(g::text, 5, '0'), "
                "'FIL' || lpad(g::text, 5, '0'), "
                "'filler ' || lpad(g::text, 5, '0') "
                "FROM generate_series(1, 50000) AS g"
            )
        )
        conn.execute(
            text(
                "INSERT INTO clusters (code, code_key, name) "
                "VALUES ('NEEDLE-CN', 'NEEDLE-CN', 'needle name')"
            )
        )
        conn.execute(
            text(
                "INSERT INTO resources (cluster_id, hostname, hostname_key, resource_type) "
                "SELECT (SELECT id FROM clusters WHERE code='NEEDLE-CN'), "
                "'svc-host', 'svc-host', 'BARE_METAL'"
            )
        )
        conn.execute(
            text(
                "INSERT INTO services (resource_id, name, name_key) "
                "SELECT (SELECT id FROM resources WHERE hostname='svc-host'), "
                "'filler-svc-' || lpad(g::text, 5, '0'), "
                "'filler-svc-' || lpad(g::text, 5, '0') "
                "FROM generate_series(1, 50000) AS g"
            )
        )
        conn.execute(
            text(
                "INSERT INTO services (resource_id, name, name_key) "
                "SELECT (SELECT id FROM resources WHERE hostname='svc-host'), "
                "'Needle Service', 'needle service'"
            )
        )
        conn.execute(text("ANALYZE clusters"))
        conn.execute(text("ANALYZE services"))

        def _plain(sql: str) -> str:
            return "\n".join(
                conn.execute(text(f"EXPLAIN (ANALYZE, COSTS OFF) {sql}")).scalars().all()
            )

        code_plan = _plain("SELECT code FROM clusters WHERE code_key ILIKE '%needle-cn%'")
        name_plan = _plain("SELECT name FROM clusters WHERE name ILIKE '%needle name%'")
        svc_plan = _plain(
            "SELECT name FROM services WHERE name_key ILIKE '%needle service%'"
        )

    assert "Bitmap Index Scan on ix_clusters_code_key_trgm" in code_plan, code_plan
    assert "Bitmap Index Scan on ix_clusters_name_trgm" in name_plan, name_plan
    assert "Bitmap Index Scan on ix_services_name_key_trgm" in svc_plan, svc_plan