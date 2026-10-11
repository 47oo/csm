"""F008 ``networks`` database constraint / exclusion / migration tests.

Real PostgreSQL only (DB-D10): SQLite cannot prove CHECK / FK RESTRICT / partial
unique / EXCLUDE / JSONB / migration behaviour. Raw SQL is used deliberately so
the evidence does not depend on ORM validation. Covers V-DB-68..V-DB-81.
"""

from __future__ import annotations

import json
import threading
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

NETWORK_CONSTRAINTS = {
    "pk_networks",
    "fk_networks_cluster_id_clusters",
    "ck_networks_name_not_blank",
    "ck_networks_name_trimmed",
    "ck_networks_name_no_control",
    "ck_networks_name_length",
    "ck_networks_name_key_matches",
    "ck_networks_cidr_ipv4",
    "ck_networks_gateway",
    "ck_networks_status",
    "ck_networks_metadata_object",
    "ck_networks_version",
    "excl_networks_cluster_id_cidr",
}

NETWORK_COLUMNS = {
    "id",
    "cluster_id",
    "name",
    "name_key",
    "cidr",
    "gateway",
    "status",
    "auto_allocate",
    "description",
    "metadata",
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
        "cidr": "10.0.0.0/24",
    }
    columns.update(cols)
    names: list[str] = []
    placeholders: list[str] = []
    params: dict = {}
    for name, value in columns.items():
        names.append(name)
        if name == "metadata" and isinstance(value, (dict, list)):
            params[name] = json.dumps(value)
            placeholders.append(f"CAST(:{name} AS jsonb)")
        else:
            params[name] = value
            placeholders.append(f":{name}")
    return conn.execute(
        text(
            f"INSERT INTO networks ({', '.join(names)}) "
            f"VALUES ({', '.join(placeholders)}) RETURNING id"
        ),
        params,
    ).scalar_one()


def _seed(engine, tag: str) -> uuid.UUID:
    code = f"NW-{tag}".upper()
    with engine.begin() as conn:
        return insert_cluster(conn, code=code, code_key=code, name=tag)


# --- V-DB-81: migration up/down/up + object catalogue ------------------------


def test_migration_up_down_up_and_single_head(pg_engine, alembic_runner):
    assert alembic_runner.head_revision() == "0013_search_indexes"
    assert _alembic_versions(pg_engine) == ["0013_search_indexes"]
    assert "networks" in _tables(pg_engine)
    assert "btree_gist" in _extensions(pg_engine)

    alembic_runner.downgrade("0007_interfaces")
    remaining = _tables(pg_engine)
    assert "networks" not in remaining
    assert "interfaces" in remaining
    assert _alembic_versions(pg_engine) == ["0007_interfaces"]
    # btree_gist must survive the 0008 downgrade (F001 DB-D4 / DB-D94).
    assert "btree_gist" in _extensions(pg_engine)

    alembic_runner.upgrade("head")
    assert "networks" in _tables(pg_engine)
    assert _alembic_versions(pg_engine) == ["0013_search_indexes"]


def test_table_catalogue_columns_constraints_indexes(committed_engine):
    """V-DB-81: columns, constraints, indexes and FK/partial/exclusion shapes."""
    engine = committed_engine
    with engine.connect() as conn:
        columns = {
            row[0]
            for row in conn.execute(
                text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_schema = 'public' AND table_name = 'networks'"
                )
            )
        }
        assert columns == NETWORK_COLUMNS

        found = set(
            conn.execute(
                text(
                    "SELECT conname FROM pg_constraint c "
                    "JOIN pg_class t ON c.conrelid = t.oid "
                    "WHERE t.relname = 'networks'"
                )
            ).scalars()
        )
        assert found == NETWORK_CONSTRAINTS

        # The exclusion constraint must use the gist access method and the
        # (cluster_id WITH =, cidr WITH &&) operator pair.
        excl = conn.execute(
            text(
                "SELECT pg_get_constraintdef(oid) FROM pg_constraint "
                "WHERE conname = 'excl_networks_cluster_id_cidr'"
            )
        ).scalar_one()
        assert "EXCLUDE USING gist" in excl
        assert "cluster_id WITH =" in excl
        assert "cidr inet_ops WITH &&" in excl
        assert "deleted_at IS NULL" in excl

        delete_types = dict(
            conn.execute(
                text(
                    "SELECT conname, confdeltype FROM pg_constraint "
                    "WHERE conname = 'fk_networks_cluster_id_clusters'"
                )
            ).all()
        )
        assert delete_types["fk_networks_cluster_id_clusters"] == "r"

        indexes = set(
            conn.execute(
                text(
                    "SELECT indexname FROM pg_indexes WHERE schemaname = 'public' "
                    "AND tablename = 'networks'"
                )
            ).scalars()
        )
        assert {
            "pk_networks",
            "uq_networks_cluster_id_name_key",
            "ix_networks_cluster_id",
            "ix_networks_status",
            "ix_networks_deleted_at",
            "excl_networks_cluster_id_cidr",
        } == indexes

        partial = conn.execute(
            text(
                "SELECT indexdef FROM pg_indexes WHERE schemaname = 'public' "
                "AND indexname = 'uq_networks_cluster_id_name_key'"
            )
        ).scalar_one()
        assert "UNIQUE" in partial
        assert "deleted_at IS NULL" in partial

        # No pg_trgm/GIN indexes (DB-D89).
        gin = conn.execute(
            text(
                "SELECT indexname FROM pg_indexes WHERE schemaname = 'public' "
                "AND tablename = 'networks' AND indexdef ILIKE '%USING gin%'"
            )
        ).scalars().all()
        assert gin == []


def test_defaults_and_not_null(committed_engine):
    engine = committed_engine
    cid = _seed(engine, "def")
    with engine.begin() as conn:
        nid = insert_network(conn, cid)
    with engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT name, cidr, gateway, status, auto_allocate, description, "
                "metadata, version, created_at, updated_at, deleted_at "
                "FROM networks WHERE id = :id"
            ),
            {"id": nid},
        ).mappings().one()
    assert str(row["cidr"]) == "10.0.0.0/24"
    assert row["gateway"] is None
    assert row["status"] == "ACTIVE"
    assert row["auto_allocate"] is False
    assert row["description"] is None
    assert row["metadata"] == {}
    assert row["version"] == 1
    assert row["created_at"] is not None and row["updated_at"] is not None
    assert row["deleted_at"] is None

    _expect_violation(
        engine,
        "INSERT INTO networks (cluster_id, name, name_key, cidr) "
        "VALUES (NULL, 'x', 'x', '10.0.0.0/24')",
    )
    _expect_violation(
        engine,
        "INSERT INTO networks (cluster_id, name, name_key) "
        "VALUES (:cid, 'x', 'x')",
        {"cid": cid},
    )


# --- V-DB-68/69: name boundaries + name_key CHECK ----------------------------


def test_name_boundaries_and_name_key(committed_engine):
    engine = committed_engine
    cid = _seed(engine, "name")
    with engine.begin() as conn:
        ok255 = insert_network(conn, cid, name="a" * 255, name_key="a" * 255)
        spaced = insert_network(
            conn, cid, name="MG  MT", name_key="mg  mt", cidr="10.1.0.0/24"
        )
        mixed = insert_network(
            conn, cid, name="MGmt", name_key="mgmt", cidr="10.2.0.0/24"
        )
        nonascii = insert_network(
            conn, cid, name="网ß", name_key="网ß", cidr="10.3.0.0/24"
        )
    with engine.connect() as conn:
        assert conn.execute(
            text("SELECT name FROM networks WHERE id = :id"), {"id": spaced}
        ).scalar_one() == "MG  MT"  # internal spaces preserved, not collapsed
        assert conn.execute(
            text("SELECT name_key FROM networks WHERE id = :id"), {"id": mixed}
        ).scalar_one() == "mgmt"  # ASCII A-Z folded only
        assert conn.execute(
            text("SELECT name_key FROM networks WHERE id = :id"), {"id": nonascii}
        ).scalar_one() == "网ß"  # non-ASCII kept verbatim

    for bad in ("", "   ", " x", "x ", "x\ty", "x\ny", "a" * 256, "x\x01y"):
        _expect_violation(
            engine,
            "INSERT INTO networks (cluster_id, name, name_key, cidr) "
            "VALUES (:cid, :name, :name, '10.9.0.0/24')",
            {"cid": cid, "name": bad},
        )
    # name_key must match translate(btrim(name)): 'ABC' -> 'abc' is valid,
    # while keeping the display case in name_key is rejected.
    _expect_violation(
        engine,
        "INSERT INTO networks (cluster_id, name, name_key, cidr) "
        "VALUES (:cid, 'ABC', 'ABC', '10.9.0.0/24')",
        {"cid": cid},
    )
    assert ok255


# --- V-DB-70: partial unique name --------------------------------------------


def test_partial_unique_name(committed_engine):
    engine = committed_engine
    c1 = _seed(engine, "u1")
    c2 = _seed(engine, "u2")
    with engine.begin() as conn:
        insert_network(conn, c1, name="MGMT", name_key="mgmt")
        insert_network(conn, c1, name="MGMT-2", name_key="mgmt-2", cidr="10.1.0.0/24")
        # cross-cluster same key allowed
        insert_network(conn, c2, name="mgmt", name_key="mgmt")

    # case-insensitive duplicate (same name_key) refused
    _expect_violation(
        engine,
        "INSERT INTO networks (cluster_id, name, name_key, cidr) "
        "VALUES (:cid, 'mgmt', 'mgmt', '10.2.0.0/24')",
        {"cid": c1},
    )
    # soft delete releases the key
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE networks SET deleted_at = now() WHERE name_key = 'mgmt'")
        )
        conn.execute(
            text(
                "INSERT INTO networks (cluster_id, name, name_key, cidr) "
                "VALUES (:cid, 'mgmt', 'mgmt', '10.2.0.0/24')"
            ),
            {"cid": c1},
        )
    _expect_violation(
        engine,
        "INSERT INTO networks (cluster_id, name, name_key, cidr) "
        "VALUES (:cid, 'MGMT', 'mgmt', '10.3.0.0/24')",
        {"cid": c1},
    )


# --- V-DB-71/72: exclusion constraint + cidr normalisation --------------------


def test_exclusion_overlap_and_cidr_normalisation(committed_engine):
    engine = committed_engine
    c1 = _seed(engine, "o1")
    c2 = _seed(engine, "o2")
    with engine.begin() as conn:
        insert_network(conn, c1, name="a", name_key="a", cidr="10.0.0.0/16")
        # PostgreSQL ``cidr`` stores the network address only; the application
        # normalises host bits (10.1.0.5/24 -> 10.1.0.0/24) before insert.
        normalised = insert_network(
            conn, c1, name="b", name_key="b", cidr="10.1.0.0/24"
        )
        # cross-cluster overlap allowed
        insert_network(conn, c2, name="a", name_key="a", cidr="10.0.0.0/16")
    with engine.connect() as conn:
        assert str(
            conn.execute(
                text("SELECT cidr FROM networks WHERE id = :id"), {"id": normalised}
            ).scalar_one()
        ) == "10.1.0.0/24"
    # raw host-bit input is rejected by the cidr type (application normalises)
    _expect_violation(
        engine,
        "INSERT INTO networks (cluster_id, name, name_key, cidr) "
        "VALUES (:cid, 'hostbits', 'hostbits', '10.1.0.5/24')",
        {"cid": c1},
    )

    # same-cluster overlap (contained) refused
    _expect_violation(
        engine,
        "INSERT INTO networks (cluster_id, name, name_key, cidr) "
        "VALUES (:cid, 'c', 'c', '10.0.0.0/24')",
        {"cid": c1},
    )
    # identical CIDR refused
    _expect_violation(
        engine,
        "INSERT INTO networks (cluster_id, name, name_key, cidr) "
        "VALUES (:cid, 'd', 'd', '10.0.0.0/16')",
        {"cid": c1},
    )
    # INACTIVE still participates
    with engine.begin() as conn:
        insert_network(
            conn,
            c1,
            name="inactive",
            name_key="inactive",
            cidr="10.4.0.0/24",
            status="INACTIVE",
        )
    _expect_violation(
        engine,
        "INSERT INTO networks (cluster_id, name, name_key, cidr) "
        "VALUES (:cid, 'e', 'e', '10.4.0.0/25')",
        {"cid": c1},
    )
    # soft-deleted does not participate
    with engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE networks SET deleted_at = now() "
                "WHERE cluster_id = :cid AND cidr = '10.0.0.0/16'"
            ),
            {"cid": c1},
        )
        insert_network(conn, c1, name="f", name_key="f", cidr="10.0.0.0/16")

    # non-IPv4 / illegal cidr refused
    for bad in ("::1/128", "2001:db8::/32"):
        _expect_violation(
            engine,
            "INSERT INTO networks (cluster_id, name, name_key, cidr) "
            "VALUES (:cid, 'g', 'g', :cidr)",
            {"cid": c1, "cidr": bad},
        )


# --- V-DB-73: gateway value domain -------------------------------------------


def test_gateway_boundaries(committed_engine):
    engine = committed_engine
    cid = _seed(engine, "gw")
    with engine.begin() as conn:
        insert_network(conn, cid, name="null", name_key="null", gateway=None)
        insert_network(
            conn, cid, name="ok", name_key="ok", cidr="10.10.0.0/24",
            gateway="10.10.0.1",
        )
        # /31 both addresses usable
        insert_network(
            conn, cid, name="31a", name_key="31a", cidr="10.11.0.0/31",
            gateway="10.11.0.0",
        )
        insert_network(
            conn, cid, name="31b", name_key="31b", cidr="10.12.0.0/31",
            gateway="10.12.0.1",
        )
        insert_network(conn, cid, name="32", name_key="32", cidr="10.13.0.1/32")

    # Each rejected case uses its own CIDR so the *exclusion* constraint can
    # never be the (unknowable) reason the insert fails: the gateway CHECK must
    # do the rejecting. Disabled-range cases put the gateway inside its own CIDR
    # and outside the network/broadcast addresses so only the disabled guard can
    # reject them.
    bad = [
        ("10.20.0.0/24", "10.20.0.0", "network address"),
        ("10.21.0.0/24", "10.21.0.255", "broadcast address"),
        ("10.22.0.0/24", "10.23.0.1", "outside cidr"),
        ("0.0.0.0/8", "0.0.0.1", "disabled 0.0.0.0/8"),
        ("127.0.0.0/8", "127.0.0.1", "disabled 127.0.0.0/8"),
        ("169.254.0.0/16", "169.254.0.1", "disabled 169.254.0.0/16"),
        ("224.0.0.0/4", "224.0.0.1", "disabled 224.0.0.0/4"),
        ("240.0.0.0/4", "240.0.0.1", "disabled 240.0.0.0/4"),
    ]
    for network, address, label in bad:
        _expect_violation(
            engine,
            "INSERT INTO networks (cluster_id, name, name_key, cidr, gateway) "
            "VALUES (:cid, :name, :name, :cidr, :gw)",
            {"cid": cid, "name": label, "cidr": network, "gw": address},
        )
    # /32 must have no gateway (own CIDR, distinct from the accepted /32 above)
    _expect_violation(
        engine,
        "INSERT INTO networks (cluster_id, name, name_key, cidr, gateway) "
        "VALUES (:cid, 'x32', 'x32', '10.24.0.1/32', '10.24.0.1')",
        {"cid": cid},
    )


# --- V-DB-74/76: status / auto_allocate / metadata ---------------------------


def test_status_auto_allocate_and_metadata(committed_engine):
    engine = committed_engine
    cid = _seed(engine, "meta")
    with engine.begin() as conn:
        insert_network(
            conn, cid, name="inc", name_key="inc", cidr="10.20.0.0/24",
            status="INACTIVE", auto_allocate=True, metadata={"a": 1},
        )
    _expect_violation(
        engine,
        "INSERT INTO networks (cluster_id, name, name_key, cidr, status) "
        "VALUES (:cid, 's', 's', '10.21.0.0/24', 'active')",
        {"cid": cid},
    )
    for bad in ("[]", "1", '"x"', "null"):
        _expect_violation(
            engine,
            "INSERT INTO networks (cluster_id, name, name_key, cidr, metadata) "
            f"VALUES (:cid, 'm-{bad}', 'm-{bad}', '10.22.0.0/24', '{bad}'::jsonb)",
            {"cid": cid},
        )
    _expect_violation(
        engine,
        "INSERT INTO networks (cluster_id, name, name_key, cidr, version) "
        "VALUES (:cid, 'v', 'v', '10.23.0.0/24', 0)",
        {"cid": cid},
    )


# --- V-DB-77: FK RESTRICT + soft-delete retention ----------------------------


def test_fk_restrict_and_soft_delete_retention(committed_engine):
    engine = committed_engine
    cid = _seed(engine, "fk")
    with engine.begin() as conn:
        insert_network(conn, cid, name="n", name_key="n")

    _expect_violation(engine, "DELETE FROM clusters WHERE id = :id", {"id": cid})

    with engine.begin() as conn:
        conn.execute(
            text("UPDATE clusters SET deleted_at = now() WHERE id = :id"), {"id": cid}
        )
        assert conn.execute(
            text("SELECT count(*) FROM networks WHERE cluster_id = :id"), {"id": cid}
        ).scalar_one() == 1

    with engine.begin() as conn:
        conn.execute(text("DELETE FROM networks WHERE cluster_id = :id"), {"id": cid})
        conn.execute(text("DELETE FROM clusters WHERE id = :id"), {"id": cid})


# --- V-DB-80: concurrent overlapping insert ----------------------------------


def test_concurrent_overlapping_insert(committed_engine):
    """B33: two concurrent same-cluster overlapping inserts -> exactly one wins."""
    engine = committed_engine
    cid = _seed(engine, "conc")

    barrier = threading.Barrier(2)
    results: list[str] = []
    lock = threading.Lock()

    def worker(name: str, cidr: str) -> None:
        try:
            barrier.wait(timeout=10)
            with engine.begin() as conn:
                insert_network(conn, cid, name=name, name_key=name, cidr=cidr)
            with lock:
                results.append("ok")
        except Exception:
            with lock:
                results.append("error")

    threads = [
        threading.Thread(target=worker, args=("r1", "10.30.0.0/16")),
        threading.Thread(target=worker, args=("r2", "10.30.1.0/24")),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=20)

    assert sorted(results) == ["error", "ok"], results
    with engine.connect() as conn:
        assert conn.execute(
            text("SELECT count(*) FROM networks WHERE cluster_id = :id"), {"id": cid}
        ).scalar_one() == 1


def test_concurrent_restore_vs_recreate(committed_engine):
    """B34: restoring a soft-deleted Network races a re-create of the same
    CIDR/name; the partial unique index and exclusion constraint must let at
    most one survive and leave no two live rows with the same name or overlap.
    """
    engine = committed_engine
    cid = _seed(engine, "restore")
    with engine.begin() as conn:
        aid = insert_network(
            conn, cid, name="dup", name_key="dup", cidr="10.40.0.0/24"
        )
        conn.execute(
            text("UPDATE networks SET deleted_at = now() WHERE id = :id"),
            {"id": aid},
        )

    barrier = threading.Barrier(2)
    results: list[str] = []
    lock = threading.Lock()

    def restore() -> None:
        try:
            barrier.wait(timeout=10)
            with engine.begin() as conn:
                conn.execute(
                    text(
                        "UPDATE networks SET deleted_at = NULL, version = version + 1 "
                        "WHERE id = :id AND deleted_at IS NOT NULL"
                    ),
                    {"id": aid},
                )
            with lock:
                results.append("restore")
        except Exception:
            with lock:
                results.append("restore-error")

    def recreate() -> None:
        try:
            barrier.wait(timeout=10)
            with engine.begin() as conn:
                insert_network(
                    conn, cid, name="dup", name_key="dup", cidr="10.40.0.0/24"
                )
            with lock:
                results.append("create")
        except Exception:
            with lock:
                results.append("create-error")

    threads = [threading.Thread(target=restore), threading.Thread(target=recreate)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=20)

    winners = [r for r in results if r in ("restore", "create")]
    assert len(winners) == 1, results
    with engine.connect() as conn:
        live = conn.execute(
            text(
                "SELECT count(*) FROM networks "
                "WHERE cluster_id = :id AND deleted_at IS NULL"
            ),
            {"id": cid},
        ).scalar_one()
        assert live == 1