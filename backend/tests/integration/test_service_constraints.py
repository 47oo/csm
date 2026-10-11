"""F011 ``services`` database constraint / partial-unique / FK / migration tests.

Real PostgreSQL only (DB-D10): SQLite cannot prove CHECK / FK RESTRICT / partial
unique / migration behaviour. Raw SQL is used deliberately so the evidence does
not depend on ORM validation. Covers V-DB-112..V-DB-125.
"""

from __future__ import annotations

import threading
import uuid
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

SERVICE_CONSTRAINTS = {
    "pk_services",
    "fk_services_resource_id_resources",
    "ck_services_name_not_blank",
    "ck_services_name_trimmed",
    "ck_services_name_no_control",
    "ck_services_name_length",
    "ck_services_name_key_matches",
    "ck_services_status",
    "ck_services_metadata_object",
    "ck_services_version",
}

SERVICE_COLUMNS = {
    "id",
    "resource_id",
    "name",
    "name_key",
    "status",
    "description",
    "metadata",
    "version",
    "created_at",
    "updated_at",
    "deleted_at",
}

SERVICE_INDEXES = {
    "pk_services",
    "uq_services_resource_id_name_key",
    "ix_services_resource_id",
    "ix_services_status",
    "ix_services_deleted_at",
}


def _expect_violation(engine, sql: str, params: dict | None = None) -> None:
    with pytest.raises(DBAPIError):
        with engine.begin() as conn:
            conn.execute(text(sql), params or {})


def _tables(engine) -> set[str]:
    with engine.connect() as conn:
        return set(
            conn.execute(
                text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
            ).scalars()
        )


def _alembic_versions(engine) -> list[str]:
    with engine.connect() as conn:
        return list(
            conn.execute(text("SELECT version_num FROM alembic_version")).scalars()
        )


def _extensions(engine) -> set[str]:
    with engine.connect() as conn:
        return set(conn.execute(text("SELECT extname FROM pg_extension")).scalars())


def insert_cluster(conn, **cols) -> uuid.UUID:
    columns = {"code": "SVC", "code_key": "SVC", "name": "svc"}
    columns.update(cols)
    names = ", ".join(columns)
    placeholders = ", ".join(f":{name}" for name in columns)
    return conn.execute(
        text(f"INSERT INTO clusters ({names}) VALUES ({placeholders}) RETURNING id"),
        columns,
    ).scalar_one()


def insert_resource(conn, cluster_id: uuid.UUID, **cols) -> uuid.UUID:
    columns = {
        "cluster_id": cluster_id,
        "hostname": "host",
        "hostname_key": "host",
        "resource_type": "BARE_METAL",
    }
    columns.update(cols)
    names = ", ".join(columns)
    placeholders = ", ".join(f":{name}" for name in columns)
    return conn.execute(
        text(f"INSERT INTO resources ({names}) VALUES ({placeholders}) RETURNING id"),
        columns,
    ).scalar_one()


def insert_service(conn, resource_id: uuid.UUID, **cols) -> uuid.UUID:
    columns = {"resource_id": resource_id, "name": "svc", "name_key": "svc"}
    columns.update(cols)
    names = ", ".join(columns)
    placeholders = ", ".join(f":{name}" for name in columns)
    return conn.execute(
        text(f"INSERT INTO services ({names}) VALUES ({placeholders}) RETURNING id"),
        columns,
    ).scalar_one()


def _seed(engine, tag: str) -> tuple[uuid.UUID, uuid.UUID]:
    code = f"SVC-{tag}".upper()
    with engine.begin() as conn:
        cid = insert_cluster(conn, code=code, code_key=code, name=tag)
        rid = insert_resource(
            conn, cid, hostname=f"host-{tag}", hostname_key=f"host-{tag}"
        )
    return cid, rid


# --- V-DB-112/125: migration up/down/up + object catalogue -------------------


def test_migration_up_down_up_and_single_head(pg_engine, alembic_runner):
    # F011 appended 0011_services to the single head chain (0010 -> 0011).
    assert alembic_runner.head_revision() == "0011_services"
    assert _alembic_versions(pg_engine) == ["0011_services"]
    assert "services" in _tables(pg_engine)
    extensions_before = _extensions(pg_engine)

    alembic_runner.downgrade("0010_ip_addresses")
    remaining = _tables(pg_engine)
    assert "services" not in remaining
    assert "ip_addresses" in remaining
    assert _alembic_versions(pg_engine) == ["0010_ip_addresses"]
    # 0011 must not enable/disable any extension; btree_gist stays from 0008.
    assert _extensions(pg_engine) == extensions_before
    assert "btree_gist" in _extensions(pg_engine)

    alembic_runner.upgrade("head")
    assert "services" in _tables(pg_engine)
    assert _alembic_versions(pg_engine) == ["0011_services"]


def test_migration_0011_has_no_create_extension():
    """V-DB-125: 0011 must not re-enable/disable any extension."""
    source = (
        Path(__file__).resolve().parents[2]
        / "alembic"
        / "versions"
        / "0011_services.py"
    ).read_text()
    assert "CREATE EXTENSION" not in source.upper()
    assert "DROP EXTENSION" not in source.upper()
    assert 'down_revision = "0010_ip_addresses"' in source


def test_table_catalogue_columns_constraints_indexes(committed_engine):
    """V-DB-112/122: columns, constraints, partial unique and index collection."""
    engine = committed_engine
    with engine.connect() as conn:
        columns = {
            row[0]
            for row in conn.execute(
                text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_schema = 'public' AND table_name = 'services'"
                )
            )
        }
        assert columns == SERVICE_COLUMNS

        found = set(
            conn.execute(
                text(
                    "SELECT conname FROM pg_constraint c "
                    "JOIN pg_class t ON c.conrelid = t.oid "
                    "WHERE t.relname = 'services'"
                )
            ).scalars()
        )
        assert found == SERVICE_CONSTRAINTS

        delete_types = dict(
            conn.execute(
                text(
                    "SELECT conname, confdeltype FROM pg_constraint "
                    "WHERE conname = 'fk_services_resource_id_resources'"
                )
            ).all()
        )
        assert delete_types["fk_services_resource_id_resources"] == "r"

        indexes = set(
            conn.execute(
                text(
                    "SELECT indexname FROM pg_indexes WHERE schemaname = 'public' "
                    "AND tablename = 'services'"
                )
            ).scalars()
        )
        assert indexes == SERVICE_INDEXES

        partial = conn.execute(
            text(
                "SELECT indexdef FROM pg_indexes WHERE schemaname = 'public' "
                "AND indexname = 'uq_services_resource_id_name_key'"
            )
        ).scalar_one()
        assert "UNIQUE" in partial
        assert "deleted_at IS NULL" in partial

        # No pg_trgm/GIN, no name/name_key single-column B-tree (DB-D137).
        gin = conn.execute(
            text(
                "SELECT indexname FROM pg_indexes WHERE schemaname = 'public' "
                "AND tablename = 'services' AND indexdef ILIKE '%USING gin%'"
            )
        ).scalars().all()
        assert gin == []
        name_indexes = conn.execute(
            text(
                "SELECT indexname FROM pg_indexes WHERE schemaname = 'public' "
                "AND tablename = 'services' AND ("
                "indexdef ILIKE '%(name)%' OR indexdef ILIKE '%(name_key)%')"
            )
        ).scalars().all()
        assert name_indexes == []

        # No immutable trigger (DB-D136).
        triggers = set(
            conn.execute(
                text(
                    "SELECT tgname FROM pg_trigger "
                    "WHERE tgrelid = 'services'::regclass AND NOT tgisinternal"
                )
            ).scalars()
        )
        assert triggers == set()


# --- V-DB-113/117/118/119: defaults / not-null / status / metadata / version --


def test_defaults_and_not_null(committed_engine):
    engine = committed_engine
    _, rid = _seed(engine, "def")
    with engine.begin() as conn:
        sid = insert_service(conn, rid)
    with engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT status, description, metadata, version, created_at, "
                "updated_at, deleted_at FROM services WHERE id = :id"
            ),
            {"id": sid},
        ).mappings().one()
    assert row["status"] == "UNKNOWN"
    assert row["description"] is None
    assert row["metadata"] == {}
    assert row["version"] == 1
    assert row["created_at"] is not None and row["updated_at"] is not None
    assert row["deleted_at"] is None

    # resource_id / name / name_key are NOT NULL.
    _expect_violation(
        engine,
        "INSERT INTO services (resource_id, name, name_key) "
        "VALUES (NULL, 'n', 'n')",
    )
    _expect_violation(
        engine,
        "INSERT INTO services (resource_id, name, name_key) "
        "VALUES (:rid, NULL, 'n')",
        {"rid": rid},
    )
    _expect_violation(
        engine,
        "INSERT INTO services (resource_id, name, name_key) "
        "VALUES (:rid, 'n', NULL)",
        {"rid": rid},
    )

    _expect_violation(
        engine,
        "INSERT INTO services (resource_id, name, name_key, version) "
        "VALUES (:rid, 'v0', 'v0', 0)",
        {"rid": rid},
    )


def test_status_check_and_default(committed_engine):
    engine = committed_engine
    _, rid = _seed(engine, "status")
    with engine.begin() as conn:
        for i, status in enumerate(("RUNNING", "STOPPED", "UNKNOWN")):
            insert_service(conn, rid, name=f"s{i}", name_key=f"s{i}", status=status)
    for bad in ("running", "", "RUNNING ", "ACTIVE"):
        _expect_violation(
            engine,
            "INSERT INTO services (resource_id, name, name_key, status) "
            "VALUES (:rid, :name, :name, :status)",
            {"rid": rid, "name": f"b-{bad or 'empty'}", "status": bad},
        )
    _expect_violation(
        engine,
        "INSERT INTO services (resource_id, name, name_key, status) "
        "VALUES (:rid, 'nullstatus', 'nullstatus', NULL)",
        {"rid": rid},
    )


def test_metadata_object_check(committed_engine):
    engine = committed_engine
    _, rid = _seed(engine, "meta")
    with engine.begin() as conn:
        sid = conn.execute(
            text(
                "INSERT INTO services (resource_id, name, name_key, metadata) "
                "VALUES (:rid, 'm', 'm', CAST(:meta AS jsonb)) RETURNING id"
            ),
            {"rid": rid, "meta": '{"k": "v"}'},
        ).scalar_one()
    with engine.connect() as conn:
        assert conn.execute(
            text("SELECT metadata FROM services WHERE id = :id"), {"id": sid}
        ).scalar_one() == {"k": "v"}
    # Whole-value replacement.
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE services SET metadata = CAST(:m AS jsonb) WHERE id = :id"),
            {"m": '{"new": 1}', "id": sid},
        )
    with engine.connect() as conn:
        assert conn.execute(
            text("SELECT metadata FROM services WHERE id = :id"), {"id": sid}
        ).scalar_one() == {"new": 1}
    for bad in ("[1,2]", '"str"', "1"):
        _expect_violation(
            engine,
            "INSERT INTO services (resource_id, name, name_key, metadata) "
            "VALUES (:rid, :name, :name, CAST(:meta AS jsonb))",
            {"rid": rid, "name": f"mm-{bad}", "meta": bad},
        )
    _expect_violation(
        engine,
        "INSERT INTO services (resource_id, name, name_key, metadata) "
        "VALUES (:rid, 'nullmeta', 'nullmeta', NULL)",
        {"rid": rid},
    )


# --- V-DB-114/115: name boundaries + name_key CHECK --------------------------


def test_name_boundaries_and_name_key(committed_engine):
    engine = committed_engine
    _, rid = _seed(engine, "name")
    with engine.begin() as conn:
        insert_service(conn, rid, name="a", name_key="a")
        insert_service(conn, rid, name="b" * 255, name_key="b" * 255)
        spaced = insert_service(conn, rid, name="SSH 服务", name_key="ssh 服务")
    with engine.connect() as conn:
        assert conn.execute(
            text("SELECT name FROM services WHERE id = :id"), {"id": spaced}
        ).scalar_one() == "SSH 服务"  # internal space + case + CJK preserved

    for bad in ("", "   ", " x", "x ", "x\ty", "a" * 256, "x\x01y"):
        _expect_violation(
            engine,
            "INSERT INTO services (resource_id, name, name_key) "
            "VALUES (:rid, :name, :name)",
            {"rid": rid, "name": bad},
        )

    # name_key must be translate(btrim(name)): 'ABC' -> 'abc', not 'ABC'.
    _expect_violation(
        engine,
        "INSERT INTO services (resource_id, name, name_key) "
        "VALUES (:rid, 'ABC', 'ABC')",
        {"rid": rid},
    )
    # ß / ﬁ are not ASCII-folded (kept verbatim, never 'ss'/'fi').
    with engine.begin() as conn:
        ligature = insert_service(conn, rid, name="ﬁß", name_key="ﬁß")
    assert ligature


# --- V-DB-116/123: partial unique name + restore re-check --------------------


def test_partial_unique_name(committed_engine):
    engine = committed_engine
    _, r1 = _seed(engine, "u1")
    _, r2 = _seed(engine, "u2")
    with engine.begin() as conn:
        insert_service(conn, r1, name="SSH", name_key="ssh")
        insert_service(conn, r1, name="ssh2", name_key="ssh2")
        insert_service(conn, r2, name="ssh", name_key="ssh")  # cross-resource ok

    _expect_violation(
        engine,
        "INSERT INTO services (resource_id, name, name_key) VALUES (:r1, 'ssh', 'ssh')",
        {"r1": r1},
    )
    # soft delete releases the key
    with engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE services SET deleted_at = now() "
                "WHERE name_key = 'ssh' AND resource_id = :r1"
            ),
            {"r1": r1},
        )
        insert_service(conn, r1, name="ssh", name_key="ssh")
    _expect_violation(
        engine,
        "INSERT INTO services (resource_id, name, name_key) VALUES (:r1, 'SSH', 'ssh')",
        {"r1": r1},
    )


def test_restore_recheck_partial_unique(committed_engine):
    engine = committed_engine
    _, r1 = _seed(engine, "re")
    with engine.begin() as conn:
        sid = insert_service(conn, r1, name="web", name_key="web")
        conn.execute(
            text("UPDATE services SET deleted_at = now() WHERE id = :id"), {"id": sid}
        )
        insert_service(conn, r1, name="web", name_key="web")
    # restoring re-enters the partial unique index and is rejected.
    _expect_violation(
        engine,
        "UPDATE services SET deleted_at = NULL WHERE id = :id",
        {"id": sid},
    )


def test_concurrent_same_name_insert(committed_engine):
    engine = committed_engine
    _, rid = _seed(engine, "conc")

    barrier = threading.Barrier(2)
    results: list[str] = []
    lock = threading.Lock()

    def worker(name: str) -> None:
        try:
            barrier.wait(timeout=10)
            with engine.begin() as conn:
                insert_service(conn, rid, name=name, name_key=name)
            with lock:
                results.append("ok")
        except Exception:
            with lock:
                results.append("error")

    threads = [
        threading.Thread(target=worker, args=("svc",)),
        threading.Thread(target=worker, args=("svc",)),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=20)

    assert sorted(results) == ["error", "ok"], results
    with engine.connect() as conn:
        assert conn.execute(
            text("SELECT count(*) FROM services WHERE resource_id = :id"), {"id": rid}
        ).scalar_one() == 1


# --- V-DB-120/121/124: FK RESTRICT + resource immutability + delete set ------


def test_fk_restrict_and_soft_delete_retention(committed_engine):
    engine = committed_engine
    cid, rid = _seed(engine, "fk")
    with engine.begin() as conn:
        sid = insert_service(conn, rid, name="n", name_key="n")

    _expect_violation(engine, "DELETE FROM resources WHERE id = :id", {"id": rid})

    with engine.begin() as conn:
        conn.execute(
            text("UPDATE resources SET deleted_at = now() WHERE id = :id"), {"id": rid}
        )
        assert conn.execute(
            text("SELECT count(*) FROM services WHERE resource_id = :id"),
            {"id": rid},
        ).scalar_one() == 1
        # Service soft delete keeps the physical row.
        conn.execute(
            text("UPDATE services SET deleted_at = now() WHERE id = :id"), {"id": sid}
        )
        assert conn.execute(
            text("SELECT count(*) FROM services WHERE id = :id"), {"id": sid}
        ).scalar_one() == 1

    with engine.begin() as conn:
        conn.execute(text("DELETE FROM services WHERE resource_id = :id"), {"id": rid})
        conn.execute(text("DELETE FROM resources WHERE id = :id"), {"id": rid})
        conn.execute(text("DELETE FROM clusters WHERE id = :id"), {"id": cid})


def test_resource_id_has_no_immutability_trigger(committed_engine):
    """V-DB-121: resource immutability is application-level; no DB trigger."""
    engine = committed_engine
    _, r1 = _seed(engine, "im1")
    _, r2 = _seed(engine, "im2")
    with engine.begin() as conn:
        sid = insert_service(conn, r1, name="p", name_key="p")
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE services SET resource_id = :r2 WHERE id = :id"),
            {"r2": r2, "id": sid},
        )
    with engine.connect() as conn:
        assert str(
            conn.execute(
                text("SELECT resource_id FROM services WHERE id = :id"), {"id": sid}
            ).scalar_one()
        ) == str(r2)


def test_service_delete_reference_set_has_no_db_constraint(committed_engine):
    """V-DB-124: the Service delete reference set is application-owned (F011 empty)."""
    engine = committed_engine
    _, rid = _seed(engine, "del")
    with engine.begin() as conn:
        sid = insert_service(conn, rid, name="d", name_key="d")
        # DB imposes no constraint blocking a Service soft delete.
        conn.execute(
            text("UPDATE services SET deleted_at = now() WHERE id = :id"), {"id": sid}
        )
    with engine.connect() as conn:
        assert conn.execute(
            text("SELECT deleted_at FROM services WHERE id = :id"), {"id": sid}
        ).scalar_one() is not None