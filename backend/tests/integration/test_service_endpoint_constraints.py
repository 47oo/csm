"""F012 ``service_endpoints`` database constraint / trigger / migration tests.

Real PostgreSQL only (DB-D10): SQLite cannot prove CHECK / FK RESTRICT / partial
unique / trigger / migration behaviour. Raw SQL is used deliberately so the
evidence does not depend on ORM validation. Covers V-DB-126..V-DB-138.
"""

from __future__ import annotations

import threading
import uuid
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

SERVICE_ENDPOINT_CONSTRAINTS = {
    "pk_service_endpoints",
    "fk_service_endpoints_service_id_services",
    "fk_service_endpoints_ip_address_id_ip_addresses",
    "ck_service_endpoints_protocol",
    "ck_service_endpoints_port",
    "ck_service_endpoints_version",
}

SERVICE_ENDPOINT_COLUMNS = {
    "id",
    "service_id",
    "ip_address_id",
    "protocol",
    "port",
    "description",
    "version",
    "created_at",
    "updated_at",
    "deleted_at",
}

SERVICE_ENDPOINT_INDEXES = {
    "pk_service_endpoints",
    "uq_service_endpoints_ip_protocol_port",
    "ix_service_endpoints_service_id",
    "ix_service_endpoints_ip_address_id",
    "ix_service_endpoints_deleted_at",
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


def _functions(engine) -> set[str]:
    with engine.connect() as conn:
        return set(
            conn.execute(
                text(
                    "SELECT proname FROM pg_proc WHERE proname = "
                    "'fn_service_endpoints_attribution'"
                )
            ).scalars()
        )


# --- raw SQL seed helpers ----------------------------------------------------


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
        text(f"INSERT INTO networks ({names}) VALUES ({placeholders}) RETURNING id"),
        columns,
    ).scalar_one()


def insert_resource(conn, cluster_id: uuid.UUID, **cols) -> uuid.UUID:
    columns = {
        "cluster_id": cluster_id,
        "hostname": "h",
        "hostname_key": "h",
        "resource_type": "BARE_METAL",
    }
    columns.update(cols)
    names = ", ".join(columns)
    placeholders = ", ".join(f":{name}" for name in columns)
    return conn.execute(
        text(f"INSERT INTO resources ({names}) VALUES ({placeholders}) RETURNING id"),
        columns,
    ).scalar_one()


def insert_interface(conn, resource_id: uuid.UUID, **cols) -> uuid.UUID:
    columns = {"resource_id": resource_id, "name": "eth0"}
    columns.update(cols)
    names = ", ".join(columns)
    placeholders = ", ".join(f":{name}" for name in columns)
    return conn.execute(
        text(f"INSERT INTO interfaces ({names}) VALUES ({placeholders}) RETURNING id"),
        columns,
    ).scalar_one()


def insert_ip_address(conn, network_id: uuid.UUID, cluster_id: uuid.UUID, **cols) -> uuid.UUID:
    columns = {
        "network_id": network_id,
        "cluster_id": cluster_id,
        "address": "10.0.0.5",
    }
    columns.update(cols)
    names = ", ".join(columns)
    placeholders = ", ".join(f":{name}" for name in columns)
    return conn.execute(
        text(
            f"INSERT INTO ip_addresses ({names}) VALUES ({placeholders}) RETURNING id"
        ),
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


def insert_endpoint(conn, service_id: uuid.UUID, ip_address_id: uuid.UUID, **cols) -> uuid.UUID:
    columns = {
        "service_id": service_id,
        "ip_address_id": ip_address_id,
        "protocol": "TCP",
        "port": 22,
    }
    columns.update(cols)
    names = ", ".join(columns)
    placeholders = ", ".join(f":{name}" for name in columns)
    return conn.execute(
        text(
            f"INSERT INTO service_endpoints ({names}) "
            f"VALUES ({placeholders}) RETURNING id"
        ),
        columns,
    ).scalar_one()


def _seed(engine, tag: str):
    """Cluster/Network/Resource/Interface/Service on one Resource."""
    code = f"EP-{tag}".upper()
    with engine.begin() as conn:
        cid = insert_cluster(conn, code=code, code_key=code, name=tag)
        nid = insert_network(
            conn, cid, name=f"net-{tag}", name_key=f"net-{tag}", cidr="10.0.0.0/8"
        )
        rid = insert_resource(
            conn, cid, hostname=f"h-{tag}", hostname_key=f"h-{tag}"
        )
        iid = insert_interface(conn, rid, name="eth0")
        sid = insert_service(conn, rid, name=f"s-{tag}", name_key=f"s-{tag}")
    return cid, nid, rid, iid, sid


# --- V-DB-126/138: migration up/down/up + object catalogue -------------------


def test_migration_up_down_up_and_single_head(pg_engine, alembic_runner):
    assert alembic_runner.head_revision() == "0015_user_cluster_authorizations"
    assert _alembic_versions(pg_engine) == ["0015_user_cluster_authorizations"]
    assert "service_endpoints" in _tables(pg_engine)
    assert _functions(pg_engine) == {"fn_service_endpoints_attribution"}
    extensions_before = _extensions(pg_engine)

    alembic_runner.downgrade("0011_services")
    remaining = _tables(pg_engine)
    assert "service_endpoints" not in remaining
    assert "services" in remaining
    assert _functions(pg_engine) == set()
    assert _alembic_versions(pg_engine) == ["0011_services"]
    assert _extensions(pg_engine) == extensions_before
    assert "btree_gist" in _extensions(pg_engine)

    alembic_runner.upgrade("head")
    assert "service_endpoints" in _tables(pg_engine)
    assert _alembic_versions(pg_engine) == ["0015_user_cluster_authorizations"]


def test_migration_0012_has_no_create_extension():
    """V-DB-138: 0012 must not re-enable/disable any extension."""
    source = (
        Path(__file__).resolve().parents[2]
        / "alembic"
        / "versions"
        / "0012_service_endpoints.py"
    ).read_text()
    assert "CREATE EXTENSION" not in source.upper()
    assert "DROP EXTENSION" not in source.upper()
    assert 'down_revision = "0011_services"' in source


def test_table_catalogue_columns_constraints_indexes_triggers(committed_engine):
    """V-DB-126/134: columns, constraints, partial unique, indexes, trigger."""
    engine = committed_engine
    with engine.connect() as conn:
        columns = {
            row[0]
            for row in conn.execute(
                text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_schema = 'public' AND table_name = 'service_endpoints'"
                )
            )
        }
        assert columns == SERVICE_ENDPOINT_COLUMNS

        found = set(
            conn.execute(
                text(
                    "SELECT conname FROM pg_constraint c "
                    "JOIN pg_class t ON c.conrelid = t.oid "
                    "WHERE t.relname = 'service_endpoints'"
                )
            ).scalars()
        )
        assert found == SERVICE_ENDPOINT_CONSTRAINTS

        delete_types = dict(
            conn.execute(
                text(
                    "SELECT conname, confdeltype FROM pg_constraint WHERE conname IN "
                    "('fk_service_endpoints_service_id_services', "
                    "'fk_service_endpoints_ip_address_id_ip_addresses')"
                )
            ).all()
        )
        assert delete_types["fk_service_endpoints_service_id_services"] == "r"
        assert delete_types["fk_service_endpoints_ip_address_id_ip_addresses"] == "r"

        indexes = set(
            conn.execute(
                text(
                    "SELECT indexname FROM pg_indexes WHERE schemaname = 'public' "
                    "AND tablename = 'service_endpoints'"
                )
            ).scalars()
        )
        assert indexes == SERVICE_ENDPOINT_INDEXES

        partial = conn.execute(
            text(
                "SELECT indexdef FROM pg_indexes WHERE schemaname = 'public' "
                "AND indexname = 'uq_service_endpoints_ip_protocol_port'"
            )
        ).scalar_one()
        assert "UNIQUE" in partial
        assert "deleted_at IS NULL" in partial

        # No pg_trgm/GIN, no standalone protocol index (DB-D152).
        gin = conn.execute(
            text(
                "SELECT indexname FROM pg_indexes WHERE schemaname = 'public' "
                "AND tablename = 'service_endpoints' AND indexdef ILIKE '%USING gin%'"
            )
        ).scalars().all()
        assert gin == []
        protocol_indexes = conn.execute(
            text(
                "SELECT indexname FROM pg_indexes WHERE schemaname = 'public' "
                "AND tablename = 'service_endpoints' AND indexdef ILIKE '%(protocol)%'"
            )
        ).scalars().all()
        assert protocol_indexes == []

        triggers = set(
            conn.execute(
                text(
                    "SELECT tgname FROM pg_trigger "
                    "WHERE tgrelid = 'service_endpoints'::regclass AND NOT tgisinternal"
                )
            ).scalars()
        )
        assert triggers == {"trg_service_endpoints_attribution"}


def test_existing_tables_not_altered(committed_engine):
    """V-DB-138: the migration only adds the new table; earlier columns remain."""
    engine = committed_engine
    with engine.connect() as conn:
        services_columns = {
            row[0]
            for row in conn.execute(
                text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_schema = 'public' AND table_name = 'services'"
                )
            )
        }
    assert {"resource_id", "name", "name_key", "status", "metadata", "version"} <= (
        services_columns
    )


# --- V-DB-127: defaults / NOT NULL ------------------------------------------


def test_defaults_and_not_null(committed_engine):
    engine = committed_engine
    _, nid, rid, iid, sid = _seed(engine, "def")
    with engine.begin() as conn:
        ipid = insert_ip_address(conn, nid, _cluster_of(engine, nid), interface_id=iid)
        eid = insert_endpoint(conn, sid, ipid)
    with engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT description, version, created_at, updated_at, deleted_at "
                "FROM service_endpoints WHERE id = :id"
            ),
            {"id": eid},
        ).mappings().one()
    assert row["description"] is None
    assert row["version"] == 1
    assert row["created_at"] is not None and row["updated_at"] is not None
    assert row["deleted_at"] is None

    _expect_violation(
        engine,
        "INSERT INTO service_endpoints (service_id, ip_address_id, protocol, port) "
        "VALUES (NULL, :ipid, 'TCP', 22)",
        {"ipid": ipid},
    )
    _expect_violation(
        engine,
        "INSERT INTO service_endpoints (service_id, ip_address_id, protocol, port) "
        "VALUES (:sid, NULL, 'TCP', 22)",
        {"sid": sid},
    )
    _expect_violation(
        engine,
        "INSERT INTO service_endpoints (service_id, ip_address_id, protocol, port) "
        "VALUES (:sid, :ipid, NULL, 22)",
        {"sid": sid, "ipid": ipid},
    )
    _expect_violation(
        engine,
        "INSERT INTO service_endpoints (service_id, ip_address_id, protocol, port) "
        "VALUES (:sid, :ipid, 'TCP', NULL)",
        {"sid": sid, "ipid": ipid},
    )
    _expect_violation(
        engine,
        "INSERT INTO service_endpoints "
        "(service_id, ip_address_id, protocol, port, version) "
        "VALUES (:sid, :ipid, 'TCP', 22, 0)",
        {"sid": sid, "ipid": ipid},
    )


def _cluster_of(engine, network_id: uuid.UUID) -> uuid.UUID:
    with engine.connect() as conn:
        return conn.execute(
            text("SELECT cluster_id FROM networks WHERE id = :id"),
            {"id": network_id},
        ).scalar_one()


# --- V-DB-128/129: protocol / port CHECK ------------------------------------


def test_protocol_check(committed_engine):
    engine = committed_engine
    _, nid, rid, iid, sid = _seed(engine, "proto")
    with engine.begin() as conn:
        ipid = insert_ip_address(conn, nid, _cluster_of(engine, nid), interface_id=iid)
        insert_endpoint(conn, sid, ipid, protocol="TCP", port=22)
        insert_endpoint(conn, sid, ipid, protocol="UDP", port=53)
    for bad in ("tcp", "udp", "SCTP", "", None):
        _expect_violation(
            engine,
            "INSERT INTO service_endpoints "
            "(service_id, ip_address_id, protocol, port) "
            "VALUES (:sid, :ipid, :proto, 9999)",
            {"sid": sid, "ipid": ipid, "proto": bad},
        )


def test_port_check(committed_engine):
    engine = committed_engine
    _, nid, rid, iid, sid = _seed(engine, "port")
    with engine.begin() as conn:
        ipid = insert_ip_address(conn, nid, _cluster_of(engine, nid), interface_id=iid)
        insert_endpoint(conn, sid, ipid, protocol="TCP", port=1)
        insert_endpoint(conn, sid, ipid, protocol="TCP", port=65535)
    for bad in (0, 65536, -1, None):
        _expect_violation(
            engine,
            "INSERT INTO service_endpoints "
            "(service_id, ip_address_id, protocol, port) "
            "VALUES (:sid, :ipid, 'TCP', :port)",
            {"sid": sid, "ipid": ipid, "port": bad},
        )


# --- V-DB-130/136: partial unique + restore re-check ------------------------


def test_partial_unique_listener(committed_engine):
    engine = committed_engine
    _, nid, rid, iid, sid = _seed(engine, "uq")
    cid = _cluster_of(engine, nid)
    with engine.begin() as conn:
        ip1 = insert_ip_address(conn, nid, cid, address="10.0.0.5", interface_id=iid)
        ip2 = insert_ip_address(conn, nid, cid, address="10.0.0.6", interface_id=iid)
        insert_endpoint(conn, sid, ip1, protocol="TCP", port=22)
        insert_endpoint(conn, sid, ip1, protocol="UDP", port=22)
        insert_endpoint(conn, sid, ip2, protocol="TCP", port=22)  # different IP ok

    _expect_violation(
        engine,
        "INSERT INTO service_endpoints (service_id, ip_address_id, protocol, port) "
        "VALUES (:sid, :ipid, 'TCP', 22)",
        {"sid": sid, "ipid": ip1},
    )

    # soft delete releases the tuple
    with engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE service_endpoints SET deleted_at = now() "
                "WHERE ip_address_id = :ipid AND protocol = 'TCP' AND port = 22"
            ),
            {"ipid": ip1},
        )
        insert_endpoint(conn, sid, ip1, protocol="TCP", port=22)


def test_restore_recheck_partial_unique(committed_engine):
    engine = committed_engine
    _, nid, rid, iid, sid = _seed(engine, "re")
    cid = _cluster_of(engine, nid)
    with engine.begin() as conn:
        ipid = insert_ip_address(conn, nid, cid, interface_id=iid)
        old = insert_endpoint(conn, sid, ipid, protocol="TCP", port=22)
        conn.execute(
            text("UPDATE service_endpoints SET deleted_at = now() WHERE id = :id"),
            {"id": old},
        )
        insert_endpoint(conn, sid, ipid, protocol="TCP", port=22)
    # restoring re-enters the partial unique index and is rejected.
    _expect_violation(
        engine,
        "UPDATE service_endpoints SET deleted_at = NULL WHERE id = :id",
        {"id": old},
    )


def test_concurrent_same_listener_insert(committed_engine):
    engine = committed_engine
    _, nid, rid, iid, sid = _seed(engine, "conc")
    with engine.begin() as conn:
        ipid = insert_ip_address(conn, nid, _cluster_of(engine, nid), interface_id=iid)

    barrier = threading.Barrier(2)
    results: list[str] = []
    lock = threading.Lock()

    def worker() -> None:
        try:
            barrier.wait(timeout=10)
            with engine.begin() as conn:
                insert_endpoint(conn, sid, ipid, protocol="TCP", port=22)
            with lock:
                results.append("ok")
        except Exception:
            with lock:
                results.append("error")

    threads = [threading.Thread(target=worker), threading.Thread(target=worker)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=20)

    assert sorted(results) == ["error", "ok"], results
    with engine.connect() as conn:
        assert conn.execute(
            text(
                "SELECT count(*) FROM service_endpoints "
                "WHERE ip_address_id = :ipid AND protocol = 'TCP' AND port = 22"
            ),
            {"ipid": ipid},
        ).scalar_one() == 1


# --- V-DB-131: FK RESTRICT ---------------------------------------------------


def test_fk_restrict_and_soft_delete_retention(committed_engine):
    engine = committed_engine
    _, nid, rid, iid, sid = _seed(engine, "fk")
    with engine.begin() as conn:
        ipid = insert_ip_address(conn, nid, _cluster_of(engine, nid), interface_id=iid)
        eid = insert_endpoint(conn, sid, ipid)

    _expect_violation(engine, "DELETE FROM services WHERE id = :id", {"id": sid})
    _expect_violation(engine, "DELETE FROM ip_addresses WHERE id = :id", {"id": ipid})

    with engine.begin() as conn:
        conn.execute(
            text("UPDATE services SET deleted_at = now() WHERE id = :id"), {"id": sid}
        )
        conn.execute(
            text("UPDATE ip_addresses SET deleted_at = now() WHERE id = :id"),
            {"id": ipid},
        )
        assert conn.execute(
            text("SELECT count(*) FROM service_endpoints WHERE id = :id"), {"id": eid}
        ).scalar_one() == 1


# --- V-DB-132: attribution trigger ------------------------------------------


def test_attribution_trigger(committed_engine):
    engine = committed_engine
    _, nid, rid, iid, sid = _seed(engine, "attr")
    cid = _cluster_of(engine, nid)
    with engine.begin() as conn:
        # second resource/interface in the same cluster (cross-Resource)
        rid2 = insert_resource(
            conn, cid, hostname="h2", hostname_key="h2"
        )
        iid2 = insert_interface(conn, rid2, name="eth0")
        unbound = insert_ip_address(conn, nid, cid, address="10.0.0.7")
        cross = insert_ip_address(
            conn, nid, cid, address="10.0.0.8", interface_id=iid2
        )
        good = insert_ip_address(
            conn, nid, cid, address="10.0.0.9", interface_id=iid
        )

    # unbound IP
    _expect_violation(
        engine,
        "INSERT INTO service_endpoints (service_id, ip_address_id, protocol, port) "
        "VALUES (:sid, :ipid, 'TCP', 22)",
        {"sid": sid, "ipid": unbound},
    )
    # cross-Resource interface
    _expect_violation(
        engine,
        "INSERT INTO service_endpoints (service_id, ip_address_id, protocol, port) "
        "VALUES (:sid, :ipid, 'TCP', 22)",
        {"sid": sid, "ipid": cross},
    )
    # matching interface succeeds; soft delete / ordinary UPDATE does not misfire
    with engine.begin() as conn:
        eid = insert_endpoint(conn, sid, good)
        conn.execute(
            text("UPDATE service_endpoints SET description = 'x' WHERE id = :id"),
            {"id": eid},
        )
        conn.execute(
            text("UPDATE service_endpoints SET deleted_at = now() WHERE id = :id"),
            {"id": eid},
        )
        conn.execute(
            text("UPDATE service_endpoints SET deleted_at = NULL WHERE id = :id"),
            {"id": eid},
        )


# --- V-DB-133: no immutability trigger --------------------------------------


def test_no_immutability_trigger(committed_engine):
    """V-DB-133: service_id is immutable at the application level only."""
    engine = committed_engine
    _, nid, rid, iid, sid = _seed(engine, "im")
    with engine.begin() as conn:
        # a second Service on the SAME Resource keeps attribution valid
        sid2 = insert_service(conn, rid, name="svc2", name_key="svc2")
        ipid = insert_ip_address(conn, nid, _cluster_of(engine, nid), interface_id=iid)
        eid = insert_endpoint(conn, sid, ipid)
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE service_endpoints SET service_id = :sid2 WHERE id = :id"),
            {"sid2": sid2, "id": eid},
        )
    with engine.connect() as conn:
        assert str(
            conn.execute(
                text("SELECT service_id FROM service_endpoints WHERE id = :id"),
                {"id": eid},
            ).scalar_one()
        ) == str(sid2)


# --- V-DB-135: version / optimistic locking ---------------------------------


def test_version_and_optimistic_lock(committed_engine):
    engine = committed_engine
    _, nid, rid, iid, sid = _seed(engine, "ver")
    with engine.begin() as conn:
        ipid = insert_ip_address(conn, nid, _cluster_of(engine, nid), interface_id=iid)
        eid = insert_endpoint(conn, sid, ipid)

    with engine.connect() as conn:
        assert conn.execute(
            text("SELECT version FROM service_endpoints WHERE id = :id"), {"id": eid}
        ).scalar_one() == 1

    _expect_violation(
        engine,
        "INSERT INTO service_endpoints (service_id, ip_address_id, protocol, port, "
        "version) VALUES (:sid, :ipid, 'UDP', 53, 0)",
        {"sid": sid, "ipid": ipid},
    )

    barrier = threading.Barrier(2)
    rowcounts: list[int] = []
    lock = threading.Lock()

    def worker() -> None:
        barrier.wait(timeout=10)
        with engine.begin() as conn:
            result = conn.execute(
                text(
                    "UPDATE service_endpoints SET version = version + 1, port = 2200 "
                    "WHERE id = :id AND version = 1"
                ),
                {"id": eid},
            )
        with lock:
            rowcounts.append(result.rowcount)

    threads = [threading.Thread(target=worker), threading.Thread(target=worker)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=20)

    assert sorted(rowcounts) == [0, 1], rowcounts


# --- V-DB-137: reference set is application-owned ---------------------------


def test_reference_set_has_no_db_constraint(committed_engine):
    """V-DB-137: soft-deleting a referenced Service/IP is not blocked by the DB."""
    engine = committed_engine
    _, nid, rid, iid, sid = _seed(engine, "ref")
    with engine.begin() as conn:
        ipid = insert_ip_address(conn, nid, _cluster_of(engine, nid), interface_id=iid)
        insert_endpoint(conn, sid, ipid)
        # the DB imposes no constraint blocking a Service/IP soft delete
        conn.execute(
            text("UPDATE services SET deleted_at = now() WHERE id = :id"), {"id": sid}
        )
        conn.execute(
            text("UPDATE ip_addresses SET deleted_at = now() WHERE id = :id"),
            {"id": ipid},
        )
        assert conn.execute(
            text("SELECT count(*) FROM service_endpoints WHERE deleted_at IS NULL")
        ).scalar_one() == 1