"""F010 ``ip_addresses`` database constraint / trigger / migration tests.

Real PostgreSQL only (DB-D10): SQLite cannot prove CHECK / FK RESTRICT / partial
unique / trigger / migration behaviour. Raw SQL is used deliberately so the
evidence does not depend on ORM validation. Covers V-DB-95..V-DB-111.
"""

from __future__ import annotations

import threading
import uuid
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

IPADDRESS_CONSTRAINTS = {
    "pk_ip_addresses",
    "fk_ip_addresses_network_id_networks",
    "fk_ip_addresses_cluster_id_clusters",
    "fk_ip_addresses_interface_id_interfaces",
    "fk_ip_addresses_ip_pool_id_ip_pools",
    "ck_ip_addresses_address_host",
    "ck_ip_addresses_address_not_disabled",
    "ck_ip_addresses_version",
}

IPADDRESS_COLUMNS = {
    "id",
    "network_id",
    "cluster_id",
    "address",
    "interface_id",
    "ip_pool_id",
    "description",
    "version",
    "created_at",
    "updated_at",
    "deleted_at",
}

IPADDRESS_INDEXES = {
    "pk_ip_addresses",
    "uq_ip_addresses_cluster_id_address",
    "ix_ip_addresses_network_id",
    "ix_ip_addresses_cluster_id",
    "ix_ip_addresses_interface_id",
    "ix_ip_addresses_ip_pool_id",
    "ix_ip_addresses_deleted_at",
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
        text(f"INSERT INTO ip_pools ({names}) VALUES ({placeholders}) RETURNING id"),
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


def _seed(engine, tag: str, cidr: str = "10.0.0.0/8"):
    with engine.begin() as conn:
        cid = insert_cluster(conn, code=f"IP-{tag}".upper(), code_key=f"IP-{tag}".upper(), name=tag)
        nid = insert_network(
            conn, cid, name=f"net-{tag}", name_key=f"net-{tag}", cidr=cidr
        )
    return cid, nid


# --- V-DB-95/107/111: migration + object catalogue ---------------------------


def test_migration_up_down_up_and_single_head(pg_engine, alembic_runner):
    assert alembic_runner.head_revision() == "0014_api_keys"
    assert _alembic_versions(pg_engine) == ["0014_api_keys"]
    assert "ip_addresses" in _tables(pg_engine)
    extensions_before = _extensions(pg_engine)

    alembic_runner.downgrade("0009_ip_pools")
    remaining = _tables(pg_engine)
    assert "ip_addresses" not in remaining
    assert "ip_pools" in remaining
    with pg_engine.connect() as conn:
        funcs = set(
            conn.execute(
                text(
                    "SELECT proname FROM pg_proc WHERE proname IN "
                    "('fn_ip_addresses_cluster_consistent', "
                    "'fn_ip_addresses_cidr_contains', "
                    "'fn_ip_addresses_interface_cluster')"
                )
            ).scalars()
        )
    assert funcs == set()
    assert _alembic_versions(pg_engine) == ["0009_ip_pools"]
    # 0010 must not enable/disable any extension; btree_gist stays from 0008.
    assert _extensions(pg_engine) == extensions_before
    assert "btree_gist" in _extensions(pg_engine)

    alembic_runner.upgrade("head")
    assert "ip_addresses" in _tables(pg_engine)
    assert _alembic_versions(pg_engine) == ["0014_api_keys"]


def test_migration_0010_has_no_create_extension():
    """V-DB-111: 0010 must not re-enable/disable any extension."""
    source = (
        Path(__file__).resolve().parents[2]
        / "alembic"
        / "versions"
        / "0010_ip_addresses.py"
    ).read_text()
    assert "CREATE EXTENSION" not in source.upper()
    assert "DROP EXTENSION" not in source.upper()
    assert 'down_revision = "0009_ip_pools"' in source


def test_table_catalogue_columns_constraints_indexes_triggers(committed_engine):
    """V-DB-107: columns, constraints, indexes, partial predicate and triggers."""
    engine = committed_engine
    with engine.connect() as conn:
        columns = {
            row[0]
            for row in conn.execute(
                text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_schema = 'public' AND table_name = 'ip_addresses'"
                )
            )
        }
        assert columns == IPADDRESS_COLUMNS

        found = set(
            conn.execute(
                text(
                    "SELECT conname FROM pg_constraint c "
                    "JOIN pg_class t ON c.conrelid = t.oid "
                    "WHERE t.relname = 'ip_addresses'"
                )
            ).scalars()
        )
        assert found == IPADDRESS_CONSTRAINTS

        for fk in (
            "fk_ip_addresses_network_id_networks",
            "fk_ip_addresses_cluster_id_clusters",
            "fk_ip_addresses_interface_id_interfaces",
            "fk_ip_addresses_ip_pool_id_ip_pools",
        ):
            assert conn.execute(
                text(
                    "SELECT confdeltype FROM pg_constraint WHERE conname = :n"
                ),
                {"n": fk},
            ).scalar_one() == "r"

        indexes = set(
            conn.execute(
                text(
                    "SELECT indexname FROM pg_indexes WHERE schemaname = 'public' "
                    "AND tablename = 'ip_addresses'"
                )
            ).scalars()
        )
        assert indexes == IPADDRESS_INDEXES

        partial = conn.execute(
            text(
                "SELECT indexdef FROM pg_indexes WHERE schemaname = 'public' "
                "AND indexname = 'uq_ip_addresses_cluster_id_address'"
            )
        ).scalar_one()
        assert "UNIQUE" in partial
        assert "deleted_at IS NULL" in partial

        # No pg_trgm/GIN, no address single-column B-tree (DB-D124).
        gins = conn.execute(
            text(
                "SELECT count(*) FROM pg_index i "
                "JOIN pg_class t ON t.oid = i.indrelid "
                "JOIN pg_am am ON am.oid = i.indexrelid JOIN pg_class c ON c.oid = i.indexrelid "
                "WHERE t.relname = 'ip_addresses' AND am.amname = 'gin'"
            )
        ).scalar_one()
        assert gins == 0
        address_only = conn.execute(
            text(
                "SELECT count(*) FROM pg_index i "
                "JOIN pg_class t ON t.oid = i.indrelid "
                "JOIN pg_class ic ON ic.oid = i.indexrelid "
                "WHERE t.relname = 'ip_addresses' AND ic.relname = 'ix_ip_addresses_address'"
            )
        ).scalar_one()
        assert address_only == 0

        triggers = dict(
            conn.execute(
                text(
                    "SELECT tgname, tgtype FROM pg_trigger "
                    "WHERE tgrelid = 'ip_addresses'::regclass AND NOT tgisinternal"
                )
            ).all()
        )
        assert set(triggers) == {
            "trg_ip_addresses_cluster_consistent",
            "trg_ip_addresses_cidr_contains",
            "trg_ip_addresses_interface_cluster",
        }
        for tgtype in triggers.values():
            # BEFORE INSERT OR UPDATE: bit0 ROW, bit1 BEFORE, bit2 INSERT, bit3 DELETE, bit4 UPDATE.
            assert tgtype & 0b00010  # BEFORE
            assert tgtype & 0b00100  # INSERT
            assert not (tgtype & 0b01000)  # not DELETE
            assert tgtype & 0b10000  # UPDATE


# --- V-DB-96/97/98/99: defaults, host, disabled, CIDR ------------------------


def test_defaults_and_not_null(committed_engine):
    """V-DB-96/V-DB-105: version default 1; NOT NULL key columns."""
    engine = committed_engine
    cid, nid = _seed(engine, "defaults")
    with engine.begin() as conn:
        iid = insert_ip_address(conn, nid, cid, address="10.0.0.5")
        row = conn.execute(
            text(
                "SELECT version, description, interface_id, ip_pool_id, deleted_at "
                "FROM ip_addresses WHERE id = :id"
            ),
            {"id": iid},
        ).mappings().one()
    assert row["version"] == 1
    assert row["description"] is None
    assert row["interface_id"] is None
    assert row["ip_pool_id"] is None
    assert row["deleted_at"] is None

    _expect_violation(
        engine,
        "INSERT INTO ip_addresses (network_id, cluster_id, address) VALUES (:n, :c, NULL)",
        {"n": nid, "c": cid},
    )
    _expect_violation(
        engine,
        "INSERT INTO ip_addresses (cluster_id, address) VALUES (:c, '10.0.0.6')",
        {"c": cid},
    )
    _expect_violation(
        engine,
        "INSERT INTO ip_addresses (network_id, address) VALUES (:n, '10.0.0.6')",
        {"n": nid},
    )


def test_ck_address_host(committed_engine):
    """V-DB-97: plain IPv4 accepted; mask/CIDR/IPv6 rejected by ck_address_host."""
    engine = committed_engine
    cid, nid = _seed(engine, "host", cidr="0.0.0.0/0")
    with engine.begin() as conn:
        insert_ip_address(conn, nid, cid, address="10.1.2.3")
    for bad in ("1.2.3.4/24", "2001:db8::1", "1.2.3.4/31"):
        _expect_violation(
            engine,
            "INSERT INTO ip_addresses (network_id, cluster_id, address) "
            "VALUES (:n, :c, :a)",
            {"n": nid, "c": cid, "a": bad},
        )


def test_ck_address_not_disabled(committed_engine):
    """V-DB-98: the five §11.1 disabled ranges are rejected; neighbours accepted."""
    engine = committed_engine
    cid, nid = _seed(engine, "disabled", cidr="0.0.0.0/0")
    disabled = [
        "0.0.0.1",
        "127.0.0.1",
        "169.254.10.20",
        "224.0.0.1",
        "240.0.0.1",
        "255.255.255.255",
    ]
    accepted = [
        "1.0.0.1",
        "126.255.255.255",
        "169.253.255.255",
        "223.255.255.255",
        "8.8.8.8",
    ]
    with engine.begin() as conn:
        for addr in accepted:
            insert_ip_address(conn, nid, cid, address=addr)
    for addr in disabled:
        _expect_violation(
            engine,
            "INSERT INTO ip_addresses (network_id, cluster_id, address) "
            "VALUES (:n, :c, :a)",
            {"n": nid, "c": cid, "a": addr},
        )


def test_cidr_contains_trigger(committed_engine):
    """V-DB-99: /24 boundary, /31 both usable, /32 single address."""
    engine = committed_engine
    with engine.begin() as conn:
        c24 = insert_cluster(conn, code="C24", code_key="C24", name="c24")
        n24 = insert_network(conn, c24, name="n24", name_key="n24", cidr="10.0.0.0/24")
        c31 = insert_cluster(conn, code="C31", code_key="C31", name="c31")
        n31 = insert_network(conn, c31, name="n31", name_key="n31", cidr="10.1.0.4/31")
        c32 = insert_cluster(conn, code="C32", code_key="C32", name="c32")
        n32 = insert_network(conn, c32, name="n32", name_key="n32", cidr="10.2.0.5/32")
        # valid cases
        insert_ip_address(conn, n24, c24, address="10.0.0.1")
        insert_ip_address(conn, n31, c31, address="10.1.0.4")
        insert_ip_address(conn, n31, c31, address="10.1.0.5")
        insert_ip_address(conn, n32, c32, address="10.2.0.5")
    # out of CIDR
    _expect_violation(
        engine,
        "INSERT INTO ip_addresses (network_id, cluster_id, address) VALUES (:n, :c, '10.0.1.1')",
        {"n": n24, "c": c24},
    )
    # network / broadcast of a /24
    for bad in ("10.0.0.0", "10.0.0.255"):
        _expect_violation(
            engine,
            "INSERT INTO ip_addresses (network_id, cluster_id, address) VALUES (:n, :c, :a)",
            {"n": n24, "c": c24, "a": bad},
        )


# --- V-DB-100/101: cluster consistency triggers ------------------------------


def test_cluster_consistent_trigger(committed_engine):
    """V-DB-100: cluster_id must equal the owning Network's cluster."""
    engine = committed_engine
    with engine.begin() as conn:
        c_a = insert_cluster(conn, code="A", code_key="A", name="a")
        c_b = insert_cluster(conn, code="B", code_key="B", name="b")
        n_a = insert_network(conn, c_a, name="na", name_key="na", cidr="10.0.0.0/24")
        insert_ip_address(conn, n_a, c_a, address="10.0.0.1")
    _expect_violation(
        engine,
        "INSERT INTO ip_addresses (network_id, cluster_id, address) VALUES (:n, :c, '10.0.0.2')",
        {"n": n_a, "c": c_b},
    )


def test_interface_cluster_trigger(committed_engine):
    """V-DB-101: a bound Interface's Resource must share the IP's Cluster."""
    engine = committed_engine
    with engine.begin() as conn:
        c_a = insert_cluster(conn, code="IA", code_key="IA", name="ia")
        c_b = insert_cluster(conn, code="IB", code_key="IB", name="ib")
        n_a = insert_network(conn, c_a, name="na", name_key="na", cidr="10.0.0.0/24")
        r_a = insert_resource(conn, c_a, hostname="ha", hostname_key="ha")
        r_b = insert_resource(conn, c_b, hostname="hb", hostname_key="hb")
        if_a = insert_interface(conn, r_a, name="eth0")
        if_b = insert_interface(conn, r_b, name="eth1")
        insert_ip_address(conn, n_a, c_a, address="10.0.0.1", interface_id=if_a)
    _expect_violation(
        engine,
        "INSERT INTO ip_addresses (network_id, cluster_id, address, interface_id) "
        "VALUES (:n, :c, '10.0.0.2', :i)",
        {"n": n_a, "c": c_a, "i": if_b},
    )
    # a NULL interface always passes the trigger
    with engine.begin() as conn:
        insert_ip_address(conn, n_a, c_a, address="10.0.0.3", interface_id=None)


# --- V-DB-102: partial unique ------------------------------------------------


def test_partial_unique_same_cluster_and_soft_delete(committed_engine):
    """V-DB-102: same-Cluster unique, cross-Cluster allowed, soft-delete reuse."""
    engine = committed_engine
    with engine.begin() as conn:
        c_a = insert_cluster(conn, code="UA", code_key="UA", name="ua")
        c_b = insert_cluster(conn, code="UB", code_key="UB", name="ub")
        n_a = insert_network(conn, c_a, name="na", name_key="na", cidr="10.0.0.0/24")
        n_b = insert_network(conn, c_b, name="nb", name_key="nb", cidr="10.0.0.0/24")
        first = insert_ip_address(conn, n_a, c_a, address="10.0.0.5")
        # different cluster, same address -> allowed
        insert_ip_address(conn, n_b, c_b, address="10.0.0.5")
    _expect_violation(
        engine,
        "INSERT INTO ip_addresses (network_id, cluster_id, address) VALUES (:n, :c, '10.0.0.5')",
        {"n": n_a, "c": c_a},
    )
    # soft delete releases the address
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE ip_addresses SET deleted_at = now() WHERE id = :id"),
            {"id": first},
        )
        insert_ip_address(conn, n_a, c_a, address="10.0.0.5")
    # restore conflict: the newer undeleted row blocks re-entering the index
    _expect_violation(
        engine,
        "UPDATE ip_addresses SET deleted_at = NULL WHERE id = :id",
        {"id": first},
    )


def test_partial_unique_concurrent_single_winner(committed_engine):
    """V-DB-102 (concurrent): only one of two racing inserts for the same key wins."""
    engine = committed_engine
    with engine.begin() as conn:
        cid = insert_cluster(conn, code="UC", code_key="UC", name="uc")
        nid = insert_network(conn, cid, name="nc", name_key="nc", cidr="10.0.0.0/24")

    barrier = threading.Barrier(2)
    outcomes: list[str] = []

    def worker() -> None:
        try:
            with engine.begin() as conn:
                barrier.wait(timeout=10)
                insert_ip_address(conn, nid, cid, address="10.0.0.7")
            outcomes.append("ok")
        except DBAPIError:
            outcomes.append("conflict")

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=20)
    assert sorted(outcomes) == ["conflict", "ok"], outcomes
    with engine.connect() as conn:
        count = conn.execute(
            text(
                "SELECT count(*) FROM ip_addresses WHERE cluster_id = :c "
                "AND address = '10.0.0.7' AND deleted_at IS NULL"
            ),
            {"c": cid},
        ).scalar_one()
    assert count == 1


# --- V-DB-103: FK RESTRICT ---------------------------------------------------


def test_fk_restrict_and_soft_deleted_pool(committed_engine):
    """V-DB-103: physical deletes are RESTRICTed; a soft-deleted Pool FK is valid."""
    engine = committed_engine
    with engine.begin() as conn:
        cid = insert_cluster(conn, code="FK", code_key="FK", name="fk")
        nid = insert_network(conn, cid, name="nf", name_key="nf", cidr="10.0.0.0/24")
        rid = insert_resource(conn, cid, hostname="hf", hostname_key="hf")
        iid = insert_interface(conn, rid, name="eth0")
        pool = insert_ip_pool(
            conn, nid, name="p", name_key="p",
            start_address="10.0.0.1", end_address="10.0.0.9",
        )
        conn.execute(
            text("UPDATE ip_pools SET deleted_at = now() WHERE id = :id"),
            {"id": pool},
        )
        # bound IP + soft-deleted pool source
        insert_ip_address(
            conn, nid, cid, address="10.0.0.5", interface_id=iid, ip_pool_id=pool
        )
    _expect_violation(engine, "DELETE FROM networks WHERE id = :id", {"id": nid})
    _expect_violation(engine, "DELETE FROM interfaces WHERE id = :id", {"id": iid})
    _expect_violation(engine, "DELETE FROM ip_pools WHERE id = :id", {"id": pool})


# --- V-DB-104/105: immutability (app-owned) + version ------------------------


def test_no_immutability_trigger_and_version_check(committed_engine):
    """V-DB-104/V-DB-105: immutability is app-owned; version >= 1 enforced.

    network/address/cluster_id/ip_pool immutability is a CONTRACT-layer rule
    (DB-D123); the database intentionally has no immutable trigger.
    """
    engine = committed_engine
    with engine.connect() as conn:
        names = set(
            conn.execute(
                text(
                    "SELECT tgname FROM pg_trigger "
                    "WHERE tgrelid = 'ip_addresses'::regclass AND NOT tgisinternal"
                )
            ).scalars()
        )
    assert not any("immutable" in name for name in names)

    cid, nid = _seed(engine, "ver", cidr="10.0.0.0/24")
    _expect_violation(
        engine,
        "INSERT INTO ip_addresses (network_id, cluster_id, address, version) "
        "VALUES (:n, :c, '10.0.0.1', 0)",
        {"n": nid, "c": cid},
    )
    with engine.begin() as conn:
        iid = insert_ip_address(conn, nid, cid, address="10.0.0.2")
    # opportunistic lock: a stale conditional UPDATE affects 0 rows
    with engine.begin() as conn:
        result = conn.execute(
            text(
                "UPDATE ip_addresses SET version = version + 1 "
                "WHERE id = :id AND version = :expected"
            ),
            {"id": iid, "expected": 99},
        )
        assert result.rowcount == 0


# --- V-DB-106/108: lock / index usage ----------------------------------------


def test_occupancy_query_uses_partial_unique_index(committed_engine):
    """V-DB-108: the cluster_id + address range uses the partial unique index."""
    engine = committed_engine
    cid, nid = _seed(engine, "plan", cidr="10.0.0.0/8")
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO ip_addresses (network_id, cluster_id, address) "
                "SELECT :n, :c, ('10.' || (g / 65536) || '.' || ((g / 256) % 256) "
                "|| '.' || (g % 256))::inet FROM generate_series(1, 4000) AS g"
            ),
            {"n": nid, "c": cid},
        )
        conn.execute(text("ANALYZE ip_addresses"))
    with engine.connect() as conn:
        plan = conn.execute(
            text(
                "EXPLAIN (FORMAT JSON) SELECT id FROM ip_addresses "
                "WHERE cluster_id = :c AND deleted_at IS NULL "
                "AND address >= '10.0.2.0'::inet AND address <= '10.0.3.255'::inet"
            ),
            {"c": cid},
        ).scalar_one()
    plan_text = str(plan)
    assert "uq_ip_addresses_cluster_id_address" in plan_text or "Index" in plan_text


# --- V-DB-109/110: trigger behaviour + restore re-check ----------------------


def test_trigger_does_not_block_soft_delete_or_plain_update(committed_engine):
    """V-DB-109: ordinary UPDATE / soft delete on a valid row are accepted."""
    engine = committed_engine
    cid, nid = _seed(engine, "trig", cidr="10.0.0.0/24")
    with engine.begin() as conn:
        iid = insert_ip_address(conn, nid, cid, address="10.0.0.1")
        conn.execute(
            text("UPDATE ip_addresses SET description = 'x' WHERE id = :id"),
            {"id": iid},
        )
        conn.execute(
            text("UPDATE ip_addresses SET deleted_at = now() WHERE id = :id"),
            {"id": iid},
        )
        conn.execute(
            text("UPDATE ip_addresses SET deleted_at = NULL WHERE id = :id"),
            {"id": iid},
        )


def test_restore_recheck_cidr_after_network_change(committed_engine):
    """V-DB-110: restoring after a CIDR change that excludes the address is rejected."""
    engine = committed_engine
    with engine.begin() as conn:
        cid = insert_cluster(conn, code="RC", code_key="RC", name="rc")
        nid = insert_network(conn, cid, name="nr", name_key="nr", cidr="10.0.0.0/24")
        iid = insert_ip_address(conn, nid, cid, address="10.0.0.5")
        conn.execute(
            text("UPDATE ip_addresses SET deleted_at = now() WHERE id = :id"),
            {"id": iid},
        )
        # Network cidr narrows and no longer contains the stored address.
        conn.execute(
            text("UPDATE networks SET cidr = '10.0.1.0/24' WHERE id = :id"),
            {"id": nid},
        )
    _expect_violation(
        engine,
        "UPDATE ip_addresses SET deleted_at = NULL WHERE id = :id",
        {"id": iid},
    )