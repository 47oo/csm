"""F014 import DB constraint / concurrency tests (V-DB-1..3, B33; real PG).

Real PostgreSQL only (DB-D10): SQLite cannot prove partial-unique / trigger /
concurrency behaviour. The import path adds no Schema (database design
``NOT_REQUIRED``); these tests assert it *reuses* the existing hostname partial
unique index and that a concurrent overlapping write serialises through it.
"""

from __future__ import annotations

import csv
import io
import uuid
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.core.config import Settings
from app.core.errors import ImportValidationFailed
from app.services import cluster as cluster_service
from app.services import resource_import

BM_HEADERS = [
    "cluster",
    "hostname",
    "resource_type",
    "role",
    "status",
    "manufacturer",
    "model",
    "serial_number",
    "cpu_model",
    "cpu_sockets",
    "cpu_cores",
    "memory_mb",
    "gpu_model",
    "gpu_count",
]


def _bm_csv(cluster_code: str, hostname: str) -> bytes:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(BM_HEADERS)
    writer.writerow([cluster_code, hostname, "BARE_METAL"] + [""] * 11)
    return buffer.getvalue().encode("utf-8")


def _insert_cluster(conn, code: str = "C1") -> uuid.UUID:
    return conn.execute(
        text(
            "INSERT INTO clusters (code, code_key, name) "
            "VALUES (:code, :key, 'Cluster') RETURNING id"
        ),
        {"code": code, "key": code.upper()},
    ).scalar_one()


# --- V-DB-1: partial unique index -------------------------------------------


def test_hostname_partial_unique_index_definition(committed_engine):
    """V-DB-1: the undeleted-only partial unique index still backs imports."""
    with committed_engine.connect() as conn:
        indexdef = conn.execute(
            text(
                "SELECT indexdef FROM pg_indexes "
                "WHERE indexname = 'uq_resources_cluster_id_hostname_key'"
            )
        ).scalar_one()
    assert "UNIQUE" in indexdef
    assert "deleted_at IS NULL" in indexdef


def test_hostname_unique_backstop_and_soft_delete_reuse(committed_engine):
    """V-DB-1/A13: raw duplicate rejected; soft-deleted frees the key."""
    with committed_engine.begin() as conn:
        cluster_id = _insert_cluster(conn)
        conn.execute(
            text(
                "INSERT INTO resources (cluster_id, hostname, hostname_key, resource_type) "
                "VALUES (:c, 'cn001', 'cn001', 'BARE_METAL')"
            ),
            {"c": cluster_id},
        )

    with pytest.raises(IntegrityError):
        with committed_engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO resources (cluster_id, hostname, hostname_key, resource_type) "
                    "VALUES (:c, 'cn001', 'cn001', 'BARE_METAL')"
                ),
                {"c": cluster_id},
            )

    with committed_engine.begin() as conn:
        conn.execute(
            text("UPDATE resources SET deleted_at = now() WHERE hostname_key = 'cn001'")
        )
        conn.execute(
            text(
                "INSERT INTO resources (cluster_id, hostname, hostname_key, resource_type) "
                "VALUES (:c, 'cn001', 'cn001', 'BARE_METAL')"
            ),
            {"c": cluster_id},
        )
        live = conn.execute(
            text(
                "SELECT count(*) FROM resources "
                "WHERE hostname_key = 'cn001' AND deleted_at IS NULL"
            )
        ).scalar_one()
        assert live == 1


# --- B33 / V-DB-3: concurrent overlapping import -----------------------------


def test_concurrent_overlapping_import_one_succeeds(committed_engine, auth_session_factory):
    """B33/V-DB-3: overlapping hostname -> one batch wins, the other rolls back."""
    with auth_session_factory() as session:
        cluster_service.create_cluster(session, None, code="C1", name="Cluster")

    data = _bm_csv("C1", "cn001")
    settings = Settings(_env_file=None)
    barrier = Barrier(2)

    def worker() -> str:
        session = auth_session_factory()
        try:
            barrier.wait()
            try:
                resource_import.write_import(session, None, data, "csv", settings)
            except ImportValidationFailed:
                return "fail"
            return "ok"
        finally:
            session.close()

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: worker(), range(2)))

    assert sorted(results) == ["fail", "ok"]
    with auth_session_factory() as session:
        assert (
            session.execute(
                text("SELECT count(*) FROM resources WHERE hostname_key = 'cn001'")
            ).scalar_one()
            == 1
        )
        resource_audits = session.execute(
            text(
                "SELECT count(*) FROM audit_logs "
                "WHERE object_type='resource' AND action='CREATE'"
            )
        ).scalar_one()
        assert resource_audits == 1


# --- V-DB-2: pre-validate writes nothing -------------------------------------


def test_prevalidate_writes_nothing(committed_engine, auth_session_factory):
    """V-DB-2/I-3: validate leaves every import-affected table untouched."""
    with auth_session_factory() as session:
        cluster_service.create_cluster(session, None, code="C1", name="Cluster")

    tables = (
        "resources",
        "bare_metal_details",
        "virtual_machine_details",
        "audit_logs",
    )

    def counts(session) -> dict[str, int]:
        return {
            table: int(
                session.execute(text(f"SELECT count(*) FROM {table}")).scalar_one()
            )
            for table in tables
        }

    data = _bm_csv("C1", "cn001")
    settings = Settings(_env_file=None)
    with auth_session_factory() as session:
        before = counts(session)
        resource_import.validate_import(session, data, "csv", settings)
        resource_import.validate_import(session, data, "csv", settings)
        after = counts(session)
    assert before == after