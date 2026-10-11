"""F009 ``ip_pools`` database constraint / exclusion / trigger / migration tests.

Real PostgreSQL only (DB-D10): SQLite cannot prove CHECK / FK RESTRICT / partial
unique / EXCLUDE / generated columns / trigger / migration behaviour. Raw SQL is
used deliberately so the evidence does not depend on ORM validation. Covers
V-DB-82..V-DB-94.
"""

from __future__ import annotations

import threading
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

IPPOOL_CONSTRAINTS = {
    "pk_ip_pools",
    "fk_ip_pools_network_id_networks",
    "ck_ip_pools_name_not_blank",
    "ck_ip_pools_name_trimmed",
    "ck_ip_pools_name_no_control",
    "ck_ip_pools_name_length",
    "ck_ip_pools_name_key_matches",
    "ck_ip_pools_start_address_host",
    "ck_ip_pools_end_address_host",
    "ck_ip_pools_address_order",
    "ck_ip_pools_allocation_mode",
    "ck_ip_pools_version",
    "excl_ip_pools_network_id_address_range",
}

IPPOOL_COLUMNS = {
    "id",
    "network_id",
    "name",
    "name_key",
    "start_address",
    "end_address",
    "address_range",
    "allocation_mode",
    "description",
    "version",
    "created_at",
    "updated_at",
    "deleted_at",
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
    columns = {"code": "C", "code_key": "C", "name": "n"}
    columns.update(cols)
    names = ", ".join(columns)
    placeholders = ", ".join(f":{name}" for name in columns)
    return conn.execute(
        text(f"INSERT INTO clusters ({names}) VALUES ({placeholders}) RETURNING id"),
        columns,
    ).scalar_one()


def insert_network(conn, cluster_id: uuid.UUID, **cols) -> uuid.UUID:
    columns = {
        "cluster_id": cluster_id,
        "name": "net",
        "name_key": "net",
        "cidr": "10.0.0.0/8",
    }
    columns.update(cols)
    names = ", ".join(columns)
    placeholders = ", ".join(f":{name}" for name in columns)
    return conn.execute(
        text(
            f"INSERT INTO networks ({names}) VALUES ({placeholders}) RETURNING id"
        ),
        columns,
    ).scalar_one()


def insert_ip_pool(conn, network_id: uuid.UUID, **cols) -> uuid.UUID:
    columns = {
        "network_id": network_id,
        "name": "pool",
        "name_key": "pool",
        "start_address": "10.0.0.1",
        "end_address": "10.0.0.9",
    }
    columns.update(cols)
    names = ", ".join(columns)
    placeholders = ", ".join(f":{name}" for name in columns)
    return conn.execute(
        text(
            f"INSERT INTO ip_pools ({names}) VALUES ({placeholders}) RETURNING id"
        ),
        columns,
    ).scalar_one()


def _seed(engine, tag: str) -> tuple[uuid.UUID, uuid.UUID]:
    code = f"IP-{tag}".upper()
    with engine.begin() as conn:
        cid = insert_cluster(conn, code=code, code_key=code, name=tag)
        nid = insert_network(conn, cid, name=f"net-{tag}", name_key=f"net-{tag}")
    return cid, nid


# --- V-DB-82/94: migration up/down/up + object catalogue ---------------------


def test_migration_up_down_up_and_single_head(pg_engine, alembic_runner):
    # F011 appended 0011_services to the single head chain (0010 -> 0011).
    assert alembic_runner.head_revision() == "0012_service_endpoints"
    assert _alembic_versions(pg_engine) == ["0012_service_endpoints"]
    assert "ip_pools" in _tables(pg_engine)
    extensions_before = _extensions(pg_engine)

    alembic_runner.downgrade("0008_networks")
    remaining = _tables(pg_engine)
    assert "ip_pools" not in remaining
    assert "networks" in remaining
    with pg_engine.connect() as conn:
        funcs = set(
            conn.execute(
                text(
                    "SELECT proname FROM pg_proc "
                    "WHERE proname = 'fn_ip_pools_cidr_contains'"
                )
            ).scalars()
        )
    assert funcs == set()
    assert _alembic_versions(pg_engine) == ["0008_networks"]
    # 0009 must not enable/disable any extension; btree_gist stays from 0008.
    assert _extensions(pg_engine) == extensions_before
    assert "btree_gist" in _extensions(pg_engine)

    # Upgrade just the F009 revision to prove 0009 is still intact in the chain.
    alembic_runner.upgrade("0009_ip_pools")
    assert "ip_pools" in _tables(pg_engine)
    assert _alembic_versions(pg_engine) == ["0009_ip_pools"]

    alembic_runner.upgrade("head")
    assert _alembic_versions(pg_engine) == ["0012_service_endpoints"]


def test_table_catalogue_columns_constraints_indexes_triggers(committed_engine):
    """V-DB-94: columns, constraints, indexes, generated column and trigger."""
    engine = committed_engine
    with engine.connect() as conn:
        columns = {
            row[0]
            for row in conn.execute(
                text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_schema = 'public' AND table_name = 'ip_pools'"
                )
            )
        }
        assert columns == IPPOOL_COLUMNS

        found = set(
            conn.execute(
                text(
                    "SELECT conname FROM pg_constraint c "
                    "JOIN pg_class t ON c.conrelid = t.oid "
                    "WHERE t.relname = 'ip_pools'"
                )
            ).scalars()
        )
        assert found == IPPOOL_CONSTRAINTS

        excl = conn.execute(
            text(
                "SELECT pg_get_constraintdef(oid) FROM pg_constraint "
                "WHERE conname = 'excl_ip_pools_network_id_address_range'"
            )
        ).scalar_one()
        assert "EXCLUDE USING gist" in excl
        assert "network_id WITH =" in excl
        assert "address_range WITH &&" in excl
        assert "deleted_at IS NULL" in excl

        delete_types = dict(
            conn.execute(
                text(
                    "SELECT conname, confdeltype FROM pg_constraint "
                    "WHERE conname = 'fk_ip_pools_network_id_networks'"
                )
            ).all()
        )
        assert delete_types["fk_ip_pools_network_id_networks"] == "r"

        indexes = set(
            conn.execute(
                text(
                    "SELECT indexname FROM pg_indexes WHERE schemaname = 'public' "
                    "AND tablename = 'ip_pools'"
                )
            ).scalars()
        )
        assert {
            "pk_ip_pools",
            "uq_ip_pools_network_id_name_key",
            "ix_ip_pools_network_id",
            "ix_ip_pools_allocation_mode",
            "ix_ip_pools_deleted_at",
            "excl_ip_pools_network_id_address_range",
        } == indexes

        partial = conn.execute(
            text(
                "SELECT indexdef FROM pg_indexes WHERE schemaname = 'public' "
                "AND indexname = 'uq_ip_pools_network_id_name_key'"
            )
        ).scalar_one()
        assert "UNIQUE" in partial
        assert "deleted_at IS NULL" in partial

        # No pg_trgm/GIN indexes (DB-D106).
        gin = conn.execute(
            text(
                "SELECT indexname FROM pg_indexes WHERE schemaname = 'public' "
                "AND tablename = 'ip_pools' AND indexdef ILIKE '%USING gin%'"
            )
        ).scalars().all()
        assert gin == []

        # Generated stored column over the immutable integer mapping.
        generated = conn.execute(
            text(
                "SELECT attgenerated FROM pg_attribute "
                "WHERE attrelid = 'ip_pools'::regclass AND attname = 'address_range'"
            )
        ).scalar_one()
        assert generated == "s"
        expr = conn.execute(
            text(
                "SELECT pg_get_expr(adbin, adrelid) FROM pg_attrdef d "
                "JOIN pg_attribute a ON a.attrelid = d.adrelid "
                "AND a.attnum = d.adnum "
                "WHERE d.adrelid = 'ip_pools'::regclass AND a.attname = 'address_range'"
            )
        ).scalar_one()
        assert "int8range" in expr and "set_masklen" in expr and "'[]'" in expr

        provolatile = dict(
            conn.execute(
                text(
                    "SELECT proname, provolatile FROM pg_proc "
                    "WHERE proname IN ('inetmi','set_masklen')"
                )
            ).all()
        )
        assert provolatile.get("inetmi") == "i"
        assert provolatile.get("set_masklen") == "i"

        triggers = set(
            conn.execute(
                text(
                    "SELECT tgname FROM pg_trigger "
                    "WHERE tgrelid = 'ip_pools'::regclass AND NOT tgisinternal"
                )
            ).scalars()
        )
        assert triggers == {"trg_ip_pools_cidr_contains"}


# --- V-DB-92/93: defaults / not-null / mode / version ------------------------


def test_defaults_and_not_null(committed_engine):
    engine = committed_engine
    _, nid = _seed(engine, "def")
    with engine.begin() as conn:
        pid = insert_ip_pool(conn, nid)
    with engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT name, allocation_mode, description, version, "
                "created_at, updated_at, deleted_at, address_range::text "
                "FROM ip_pools WHERE id = :id"
            ),
            {"id": pid},
        ).mappings().one()
    assert row["allocation_mode"] == "MANUAL"
    assert row["description"] is None
    assert row["version"] == 1
    assert row["created_at"] is not None and row["updated_at"] is not None
    assert row["deleted_at"] is None
    assert row["address_range"] == "[167772161,167772170)"

    for bad in ("active", "", "MANUAL "):
        _expect_violation(
            engine,
            "INSERT INTO ip_pools "
            "(network_id, name, name_key, start_address, end_address, allocation_mode) "
            "VALUES (:nid, :name, :name, '10.0.1.1', '10.0.1.2', :mode)",
            {"nid": nid, "name": f"m-{bad}", "mode": bad},
        )
    _expect_violation(
        engine,
        "INSERT INTO ip_pools "
        "(network_id, name, name_key, start_address, end_address, allocation_mode) "
        "VALUES (:nid, 'nullmode', 'nullmode', '10.0.1.3', '10.0.1.4', NULL)",
        {"nid": nid},
    )
    _expect_violation(
        engine,
        "INSERT INTO ip_pools "
        "(network_id, name, name_key, start_address, end_address, version) "
        "VALUES (:nid, 'v0', 'v0', '10.0.1.5', '10.0.1.6', 0)",
        {"nid": nid},
    )


# --- V-DB-83/84: name boundaries + name_key CHECK ----------------------------


def test_name_boundaries_and_name_key(committed_engine):
    engine = committed_engine
    _, nid = _seed(engine, "name")
    with engine.begin() as conn:
        ok255 = insert_ip_pool(
            conn, nid, name="a" * 255, name_key="a" * 255,
            start_address="10.0.1.1", end_address="10.0.1.2",
        )
        spaced = insert_ip_pool(
            conn, nid, name="PO  OL", name_key="po  ol",
            start_address="10.0.1.3", end_address="10.0.1.4",
        )
        nonascii = insert_ip_pool(
            conn, nid, name="网ß", name_key="网ß",
            start_address="10.0.1.5", end_address="10.0.1.6",
        )
    with engine.connect() as conn:
        assert conn.execute(
            text("SELECT name FROM ip_pools WHERE id = :id"), {"id": spaced}
        ).scalar_one() == "PO  OL"  # internal spaces preserved
        assert conn.execute(
            text("SELECT name_key FROM ip_pools WHERE id = :id"), {"id": nonascii}
        ).scalar_one() == "网ß"  # non-ASCII kept verbatim

    for bad in ("", "   ", " x", "x ", "x\ty", "a" * 256, "x\x01y"):
        _expect_violation(
            engine,
            "INSERT INTO ip_pools (network_id, name, name_key, start_address, end_address) "
            "VALUES (:nid, :name, :name, '10.0.9.1', '10.0.9.2')",
            {"nid": nid, "name": bad},
        )
    # name_key must be translate(btrim(name)): 'ABC' -> 'abc', not 'ABC'.
    _expect_violation(
        engine,
        "INSERT INTO ip_pools (network_id, name, name_key, start_address, end_address) "
        "VALUES (:nid, 'ABC', 'ABC', '10.0.9.3', '10.0.9.4')",
        {"nid": nid},
    )
    assert ok255


# --- V-DB-85: partial unique name --------------------------------------------


def test_partial_unique_name(committed_engine):
    engine = committed_engine
    _, n1 = _seed(engine, "u1")
    _, n2 = _seed(engine, "u2")
    with engine.begin() as conn:
        insert_ip_pool(conn, n1, name="POOL", name_key="pool")
        insert_ip_pool(conn, n1, name="pool2", name_key="pool2", start_address="10.0.2.1", end_address="10.0.2.2")
        insert_ip_pool(conn, n2, name="pool", name_key="pool")  # cross-network ok

    _expect_violation(
        engine,
        "INSERT INTO ip_pools (network_id, name, name_key, start_address, end_address) "
        "VALUES (:nid, 'pool', 'pool', '10.0.3.1', '10.0.3.2')",
        {"nid": n1},
    )
    # soft delete releases the key
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE ip_pools SET deleted_at = now() WHERE name_key = 'pool' AND network_id = :nid"),
            {"nid": n1},
        )
        insert_ip_pool(conn, n1, name="pool", name_key="pool", start_address="10.0.3.1", end_address="10.0.3.2")
    _expect_violation(
        engine,
        "INSERT INTO ip_pools (network_id, name, name_key, start_address, end_address) "
        "VALUES (:nid, 'POOL', 'pool', '10.0.4.1', '10.0.4.2')",
        {"nid": n1},
    )


# --- V-DB-86/87/88: exclusion + generated column + restore recheck -----------


def test_exclusion_overlap_and_generated_column(committed_engine):
    engine = committed_engine
    _, n1 = _seed(engine, "o1")
    _, n2 = _seed(engine, "o2")
    with engine.begin() as conn:
        base = insert_ip_pool(
            conn, n1, name="a", name_key="a",
            start_address="10.0.0.10", end_address="10.0.0.20",
        )
        insert_ip_pool(
            conn, n1, name="ad", name_key="ad",
            start_address="10.0.0.21", end_address="10.0.0.30",
        )
        insert_ip_pool(  # cross-network overlap allowed
            conn, n2, name="a", name_key="a",
            start_address="10.0.0.10", end_address="10.0.0.20",
        )
    with engine.connect() as conn:
        assert conn.execute(
            text("SELECT address_range::text FROM ip_pools WHERE id = :id"),
            {"id": base},
        ).scalar_one() == "[167772170,167772181)"

    # contained / identical / shared endpoints all refused
    for name, start, end in (
        ("b", "10.0.0.12", "10.0.0.15"),
        ("c", "10.0.0.10", "10.0.0.20"),
        ("d", "10.0.0.5", "10.0.0.10"),
        ("e", "10.0.0.20", "10.0.0.25"),
    ):
        _expect_violation(
            engine,
            "INSERT INTO ip_pools "
            "(network_id, name, name_key, start_address, end_address) "
            "VALUES (:nid, :name, :name, :start, :end)",
            {"nid": n1, "name": name, "start": start, "end": end},
        )

    # the generated column recomputes when the range changes
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE ip_pools SET end_address = '10.0.0.15' WHERE id = :id"),
            {"id": base},
        )
    with engine.connect() as conn:
        assert conn.execute(
            text("SELECT address_range::text FROM ip_pools WHERE id = :id"),
            {"id": base},
        ).scalar_one() == "[167772170,167772176)"

    # soft delete releases the range
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE ip_pools SET deleted_at = now() WHERE id = :id"), {"id": base}
        )
        insert_ip_pool(
            conn, n1, name="reuse", name_key="reuse",
            start_address="10.0.0.10", end_address="10.0.0.20",
        )


def test_restore_recheck_overlap_rejected(committed_engine):
    engine = committed_engine
    _, n1 = _seed(engine, "re")
    with engine.begin() as conn:
        pid = insert_ip_pool(
            conn, n1, name="p", name_key="p",
            start_address="10.0.0.1", end_address="10.0.0.5",
        )
        conn.execute(
            text("UPDATE ip_pools SET deleted_at = now() WHERE id = :id"), {"id": pid}
        )
        insert_ip_pool(
            conn, n1, name="other", name_key="other",
            start_address="10.0.0.3", end_address="10.0.0.7",
        )
    # restoring re-enters the exclusion index and is rejected
    _expect_violation(
        engine,
        "UPDATE ip_pools SET deleted_at = NULL WHERE id = :id",
        {"id": pid},
    )


# --- V-DB-89/90: CIDR containment trigger + address domain -------------------


def test_address_domain(committed_engine):
    engine = committed_engine
    _, nid = _seed(engine, "addr")
    with engine.begin() as conn:
        insert_ip_pool(
            conn, nid, name="single", name_key="single",
            start_address="10.0.0.5", end_address="10.0.0.5",
        )
    # reverse order refused
    _expect_violation(
        engine,
        "INSERT INTO ip_pools (network_id, name, name_key, start_address, end_address) "
        "VALUES (:nid, 'rev', 'rev', '10.0.0.9', '10.0.0.1')",
        {"nid": nid},
    )
    # IPv6 refused
    _expect_violation(
        engine,
        "INSERT INTO ip_pools (network_id, name, name_key, start_address, end_address) "
        "VALUES (:nid, 'v6a', 'v6a', '::1', '::1')",
        {"nid": nid},
    )
    # masked host address (masklen != 32) refused by the host CHECK
    _expect_violation(
        engine,
        "INSERT INTO ip_pools (network_id, name, name_key, start_address, end_address) "
        "VALUES (:nid, 'mask', 'mask', '10.0.0.1/24', '10.0.0.2/24')",
        {"nid": nid},
    )


def test_cidr_contains_trigger(committed_engine):
    engine = committed_engine
    _, nid = _seed(engine, "cidr")
    # /32 Network accepts start = end = the address
    with engine.begin() as conn:
        code = "IP-SLASH32"
        cid = insert_cluster(conn, code=code, code_key=code, name="slash32")
        slash32 = insert_network(
            conn, cid, name="slash32", name_key="slash32", cidr="192.168.1.5/32"
        )
        insert_ip_pool(
            conn, slash32, name="p32", name_key="p32",
            start_address="192.168.1.5", end_address="192.168.1.5",
        )
        single = insert_ip_pool(
            conn, nid, name="single", name_key="single",
            start_address="10.0.0.1", end_address="10.0.0.1",
        )
    assert single

    # start/end outside the Network CIDR are refused on INSERT
    _expect_violation(
        engine,
        "INSERT INTO ip_pools (network_id, name, name_key, start_address, end_address) "
        "VALUES (:nid, 'out', 'out', '11.0.1.1', '11.0.1.5')",
        {"nid": nid},
    )
    # ... and on UPDATE
    with engine.begin() as conn:
        pid = insert_ip_pool(
            conn, nid, name="in", name_key="in",
            start_address="10.0.0.10", end_address="10.0.0.12",
        )
    _expect_violation(
        engine,
        "UPDATE ip_pools SET end_address = '11.0.1.1' WHERE id = :id",
        {"id": pid},
    )
    # missing Network row is reported by the FK (trigger returns NEW)
    _expect_violation(
        engine,
        "INSERT INTO ip_pools (network_id, name, name_key, start_address, end_address) "
        "VALUES (:nid, 'ghost', 'ghost', '10.0.0.1', '10.0.0.2')",
        {"nid": str(uuid.uuid4())},
    )


# --- V-DB-91/92: FK RESTRICT + network immutability (no trigger) -------------


def test_fk_restrict_and_soft_delete_retention(committed_engine):
    engine = committed_engine
    cid, nid = _seed(engine, "fk")
    with engine.begin() as conn:
        pid = insert_ip_pool(conn, nid, name="n", name_key="n")

    _expect_violation(engine, "DELETE FROM networks WHERE id = :id", {"id": nid})

    with engine.begin() as conn:
        conn.execute(
            text("UPDATE networks SET deleted_at = now() WHERE id = :id"), {"id": nid}
        )
        assert conn.execute(
            text("SELECT count(*) FROM ip_pools WHERE network_id = :id"), {"id": nid}
        ).scalar_one() == 1
        # Pool soft delete keeps the physical row (source history preserved).
        conn.execute(
            text("UPDATE ip_pools SET deleted_at = now() WHERE id = :id"), {"id": pid}
        )
        assert conn.execute(
            text("SELECT count(*) FROM ip_pools WHERE id = :id"), {"id": pid}
        ).scalar_one() == 1

    with engine.begin() as conn:
        conn.execute(text("DELETE FROM ip_pools WHERE network_id = :id"), {"id": nid})
        conn.execute(text("DELETE FROM networks WHERE id = :id"), {"id": nid})
        conn.execute(text("DELETE FROM clusters WHERE id = :id"), {"id": cid})


def test_network_id_has_no_immutability_trigger(committed_engine):
    """V-DB-92: network immutability is application-level; no DB trigger exists."""
    engine = committed_engine
    _, n1 = _seed(engine, "im1")
    _, n2 = _seed(engine, "im2")
    with engine.begin() as conn:
        pid = insert_ip_pool(conn, n1, name="p", name_key="p")
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE ip_pools SET network_id = :n2 WHERE id = :id"),
            {"n2": n2, "id": pid},
        )
    with engine.connect() as conn:
        assert str(
            conn.execute(
                text("SELECT network_id FROM ip_pools WHERE id = :id"), {"id": pid}
            ).scalar_one()
        ) == str(n2)


# --- concurrency --------------------------------------------------------------


def test_concurrent_overlapping_insert(committed_engine):
    """Two concurrent same-network overlapping inserts -> exactly one wins."""
    engine = committed_engine
    _, nid = _seed(engine, "conc")

    barrier = threading.Barrier(2)
    results: list[str] = []
    lock = threading.Lock()

    def worker(name: str, start: str, end: str) -> None:
        try:
            barrier.wait(timeout=10)
            with engine.begin() as conn:
                insert_ip_pool(
                    conn, nid, name=name, name_key=name,
                    start_address=start, end_address=end,
                )
            with lock:
                results.append("ok")
        except Exception:
            with lock:
                results.append("error")

    threads = [
        threading.Thread(target=worker, args=("r1", "10.0.0.1", "10.0.0.10")),
        threading.Thread(target=worker, args=("r2", "10.0.0.5", "10.0.0.15")),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=20)

    assert sorted(results) == ["error", "ok"], results
    with engine.connect() as conn:
        assert conn.execute(
            text("SELECT count(*) FROM ip_pools WHERE network_id = :id"), {"id": nid}
        ).scalar_one() == 1

def test_network_row_lock_serialises_reserved_change_and_fake_allocate(
    committed_engine,
):
    """A22/DR-109: ``_lock_network`` (networks row FOR UPDATE) is mutually exclusive.

    F009 takes the lock for any RESERVED/range change; F010 must take the same
    lock for IP allocation. Here a "fake allocation" session tries to take the
    same row lock while a RESERVED-change session holds it: the second must block
    until the first commits, proving the serialisation domain (no partial state
    can coexist). The real IP allocation end-to-end remains F010 (T33/T35).
    """
    import time

    engine = committed_engine
    _, nid = _seed(engine, "lock")

    holder = engine.connect()
    waiter = engine.connect()
    started: list[float] = []
    finished: list[float] = []
    try:
        holder_tx = holder.begin()
        holder.execute(
            text("SELECT id FROM networks WHERE id = :id FOR UPDATE"), {"id": nid}
        )

        def try_lock():
            started.append(time.monotonic())
            waiter_tx = waiter.begin()
            try:
                waiter.execute(
                    text("SELECT id FROM networks WHERE id = :id FOR UPDATE"),
                    {"id": nid},
                )
                finished.append(time.monotonic())
            finally:
                waiter_tx.rollback()

        thread = threading.Thread(target=try_lock)
        thread.start()
        time.sleep(0.6)
        # The second session must still be blocked while the first holds the lock.
        assert finished == [], "second session acquired the lock while it was held"
        holder_tx.commit()
        thread.join(timeout=10)
        assert finished, "second session never acquired the lock after release"
        assert finished[0] - started[0] >= 0.3, (started, finished)
    finally:
        holder.close()
        waiter.close()
