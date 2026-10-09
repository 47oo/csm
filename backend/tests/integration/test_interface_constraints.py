"""F007 ``interfaces`` database constraint / trigger / migration tests.

Real PostgreSQL only (DB-D10): SQLite cannot prove CHECK / FK RESTRICT /
trigger / migration behaviour. Raw SQL is used deliberately so the evidence does
not depend on ORM validation. Covers V-DB-53..V-DB-67.
"""

from __future__ import annotations

import json
import threading
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

INTERFACE_CONSTRAINTS = {
    "pk_interfaces",
    "fk_interfaces_resource_id_resources",
    "fk_interfaces_parent_interface_id_interfaces",
    "ck_interfaces_name_not_blank",
    "ck_interfaces_name_trimmed",
    "ck_interfaces_name_no_ws_control",
    "ck_interfaces_name_length",
    "ck_interfaces_interface_type",
    "ck_interfaces_mac_address_format",
    "ck_interfaces_speed_mbps_range",
    "ck_interfaces_mtu_range",
    "ck_interfaces_parent_not_self",
    "ck_interfaces_metadata_object",
    "ck_interfaces_version",
}

INTERFACE_COLUMNS = {
    "id",
    "resource_id",
    "name",
    "interface_type",
    "mac_address",
    "speed_mbps",
    "mtu",
    "parent_interface_id",
    "enabled",
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


def insert_cluster(conn, **cols) -> uuid.UUID:
    columns = {"code": "C", "code_key": "C", "name": "n"}
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
            f"INSERT INTO interfaces ({', '.join(names)}) "
            f"VALUES ({', '.join(placeholders)}) RETURNING id"
        ),
        params,
    ).scalar_one()


def _seed(engine, tag: str):
    """Commit a cluster + Resource; return their ids."""
    code = f"IF-{tag}".upper()
    with engine.begin() as conn:
        cid = insert_cluster(conn, code=code, code_key=code, name=tag)
        rid = insert_resource(
            conn, cid, hostname=f"host-{tag}", hostname_key=f"host-{tag}"
        )
    return cid, rid


# --- V-DB-53: migration up/down/up + object catalogue ------------------------


def test_migration_up_down_up_and_single_head(pg_engine, alembic_runner):
    assert alembic_runner.head_revision() == "0009_ip_pools"
    assert _alembic_versions(pg_engine) == ["0009_ip_pools"]
    assert "interfaces" in _tables(pg_engine)

    alembic_runner.downgrade("0006_virtual_machine_details")
    remaining = _tables(pg_engine)
    assert "interfaces" not in remaining
    assert "virtual_machine_details" in remaining
    with pg_engine.connect() as conn:
        funcs = set(
            conn.execute(
                text("SELECT proname FROM pg_proc WHERE proname LIKE 'fn_interfaces%'")
            ).scalars()
        )
    assert funcs == set()
    assert _alembic_versions(pg_engine) == ["0006_virtual_machine_details"]

    alembic_runner.upgrade("head")
    assert "interfaces" in _tables(pg_engine)
    assert _alembic_versions(pg_engine) == ["0009_ip_pools"]


def test_table_catalogue_columns_constraints_indexes_triggers(committed_engine):
    """V-DB-54/64: object set, columns, indexes and trigger catalogue."""
    engine = committed_engine
    with engine.connect() as conn:
        columns = {
            row[0]
            for row in conn.execute(
                text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_schema = 'public' AND table_name = 'interfaces'"
                )
            )
        }
        assert columns == INTERFACE_COLUMNS
        # No IP/CIDR/VLAN/Network/category columns (A17/§9/§10/§13).
        forbidden = {
            "ip",
            "ip_address",
            "cidr",
            "vlan_id",
            "network_id",
            "category",
        }
        assert not (forbidden & columns)

        found = set(
            conn.execute(
                text(
                    "SELECT conname FROM pg_constraint c "
                    "JOIN pg_class t ON c.conrelid = t.oid "
                    "WHERE t.relname = 'interfaces'"
                )
            ).scalars()
        )
        assert found == INTERFACE_CONSTRAINTS

        triggers = set(
            conn.execute(
                text(
                    "SELECT tgname FROM pg_trigger WHERE NOT tgisinternal "
                    "AND tgrelid = 'interfaces'::regclass"
                )
            ).scalars()
        )
        assert triggers == {
            "trg_interfaces_parent_valid",
            "trg_interfaces_immutable_resource",
        }

        indexes = set(
            conn.execute(
                text(
                    "SELECT indexname FROM pg_indexes WHERE schemaname = 'public' "
                    "AND tablename = 'interfaces'"
                )
            ).scalars()
        )
        assert indexes == {
            "pk_interfaces",
            "uq_interfaces_resource_id_name",
            "ix_interfaces_resource_id",
            "ix_interfaces_parent_interface_id",
        }
        # No pg_trgm / GIN indexes (DB-D77): assert no index method is gin.
        gin_indexes = conn.execute(
            text(
                "SELECT indexname FROM pg_indexes WHERE schemaname = 'public' "
                "AND tablename = 'interfaces' AND indexdef ILIKE '%USING gin%'"
            )
        ).scalars().all()
        assert gin_indexes == []
        # No UNIQUE constraint touching mac_address.
        mac_unique = conn.execute(
            text(
                "SELECT indexdef FROM pg_indexes WHERE schemaname = 'public' "
                "AND tablename = 'interfaces' AND indexdef ILIKE '%unique%' "
                "AND indexdef ILIKE '%mac_address%'"
            )
        ).scalars().all()
        assert mac_unique == []

        delete_types = dict(
            conn.execute(
                text(
                    "SELECT conname, confdeltype FROM pg_constraint "
                    "WHERE conname IN ('fk_interfaces_resource_id_resources', "
                    "'fk_interfaces_parent_interface_id_interfaces')"
                )
            ).all()
        )
        assert delete_types["fk_interfaces_resource_id_resources"] == "r"
        assert delete_types["fk_interfaces_parent_interface_id_interfaces"] == "r"

        partial = conn.execute(
            text(
                "SELECT indexdef FROM pg_indexes WHERE schemaname = 'public' "
                "AND indexname = 'uq_interfaces_resource_id_name'"
            )
        ).scalar_one()
        assert "WHERE (deleted_at IS NULL)" in partial
        assert "UNIQUE" in partial


# --- V-DB-54: defaults + NOT NULL --------------------------------------------


def test_defaults_and_not_null(committed_engine):
    engine = committed_engine
    _, rid = _seed(engine, "def")
    with engine.begin() as conn:
        iid = insert_interface(conn, rid)
    with engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT name, interface_type, mac_address, speed_mbps, mtu, "
                "parent_interface_id, enabled, description, metadata, version, "
                "created_at, updated_at, deleted_at FROM interfaces WHERE id = :id"
            ),
            {"id": iid},
        ).mappings().one()
    assert row["interface_type"] == "OTHER"
    assert row["enabled"] is True
    assert row["metadata"] == {}
    assert row["version"] == 1
    assert row["mac_address"] is None
    assert row["speed_mbps"] is None and row["mtu"] is None
    assert row["parent_interface_id"] is None and row["description"] is None
    assert row["created_at"] is not None and row["updated_at"] is not None
    assert row["deleted_at"] is None

    # NOT NULL enforcement for resource_id / name.
    _expect_violation(
        engine, "INSERT INTO interfaces (resource_id, name) VALUES (NULL, 'x')"
    )
    _expect_violation(
        engine,
        "INSERT INTO interfaces (resource_id, name) VALUES (:rid, NULL)",
        {"rid": rid},
    )


# --- V-DB-55: interface_type 7 values ----------------------------------------


def test_interface_type_values(committed_engine):
    engine = committed_engine
    _, rid = _seed(engine, "type")
    valid = ("PHYSICAL", "VIRTUAL", "BOND", "BRIDGE", "VLAN", "LOOPBACK", "OTHER")
    with engine.begin() as conn:
        for value in valid:
            insert_interface(conn, rid, name=f"n-{value}", interface_type=value)
    for bad in ("ETHERNET", "", "other", "BOND "):
        _expect_violation(
            engine,
            "INSERT INTO interfaces (resource_id, name, interface_type) "
            "VALUES (:rid, :name, :value)",
            {"rid": rid, "name": f"bad-{bad}", "value": bad},
        )


# --- V-DB-56: name boundaries ------------------------------------------------


def test_name_format_and_length(committed_engine):
    engine = committed_engine
    _, rid = _seed(engine, "name")
    with engine.begin() as conn:
        ok64 = insert_interface(conn, rid, name="a" * 64)
        preserved = insert_interface(conn, rid, name="ETH0")
    with engine.connect() as conn:
        assert conn.execute(
            text("SELECT name FROM interfaces WHERE id = :id"), {"id": preserved}
        ).scalar_one() == "ETH0"

    for bad in (
        "",
        "   ",
        " eth0",
        "eth0 ",
        "eth 0",
        "eth\t0",
        "eth\n0",
        "a" * 65,
        "e\x01th0",
    ):
        _expect_violation(
            engine,
            "INSERT INTO interfaces (resource_id, name) VALUES (:rid, :name)",
            {"rid": rid, "name": bad},
        )
    assert ok64


# --- V-DB-57: partial unique name --------------------------------------------


def test_partial_unique_name(committed_engine):
    engine = committed_engine
    _, rid = _seed(engine, "uniq")
    _, other = _seed(engine, "uniq2")
    with engine.begin() as conn:
        insert_interface(conn, rid, name="eth0")
        insert_interface(conn, rid, name="ETH0")  # case-sensitive: allowed
        insert_interface(conn, other, name="eth0")  # cross-resource allowed

    # A live duplicate is refused.
    _expect_violation(
        engine,
        "INSERT INTO interfaces (resource_id, name) VALUES (:rid, 'eth0')",
        {"rid": rid},
    )

    # Soft delete releases the name; a new live row may reuse it.
    with engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE interfaces SET deleted_at = now() WHERE resource_id = :rid "
                "AND name = 'eth0'"
            ),
            {"rid": rid},
        )
        conn.execute(
            text("INSERT INTO interfaces (resource_id, name) VALUES (:rid, 'eth0')"),
            {"rid": rid},
        )
    # A second live duplicate is refused again (partial unique only live rows).
    _expect_violation(
        engine,
        "INSERT INTO interfaces (resource_id, name) VALUES (:rid, 'eth0')",
        {"rid": rid},
    )


# --- V-DB-58/59: speed/mtu/mac boundaries ------------------------------------


def test_speed_mtu_and_mac_boundaries(committed_engine):
    engine = committed_engine
    _, rid = _seed(engine, "num")
    with engine.begin() as conn:
        insert_interface(conn, rid, name="ok", speed_mbps=1, mtu=1)
        insert_interface(conn, rid, name="max", speed_mbps=2147483647, mtu=2147483647)
        insert_interface(conn, rid, name="mac", mac_address="AA:BB:CC:DD:EE:FF")
        insert_interface(conn, rid, name="mac2", mac_address="AA:BB:CC:DD:EE:FF")
        insert_interface(conn, rid, name="mac64", mac_address="m" * 64)

    for column in ("speed_mbps", "mtu"):
        for bad in (0, -1, 2147483648):
            _expect_violation(
                engine,
                f"INSERT INTO interfaces (resource_id, name, {column}) "
                "VALUES (:rid, :name, :value)",
                {"rid": rid, "name": f"bad-{column}-{bad}", "value": bad},
            )

    for bad in ("", " ", "m" * 65, "A\x01B"):
        _expect_violation(
            engine,
            "INSERT INTO interfaces (resource_id, name, mac_address) "
            "VALUES (:rid, :name, :value)",
            {"rid": rid, "name": f"badmac-{len(bad)}", "value": bad},
        )


# --- V-DB-60: parent trigger four negative cases + FK -------------------------


def test_parent_trigger(committed_engine):
    engine = committed_engine
    _, rid = _seed(engine, "par")
    _, other_rid = _seed(engine, "par2")
    with engine.begin() as conn:
        a = insert_interface(conn, rid, name="a")
        b = insert_interface(conn, rid, name="b")
        c = insert_interface(conn, rid, name="c")
        foreign = insert_interface(conn, other_rid, name="foreign")
        soft = insert_interface(conn, rid, name="soft")
        conn.execute(
            text("UPDATE interfaces SET parent_interface_id = :p WHERE id = :id"),
            {"p": b, "id": a},  # a -> b (valid)
        )
        conn.execute(
            text("UPDATE interfaces SET deleted_at = now() WHERE id = :id"),
            {"id": soft},
        )

    # self-reference via UPDATE (CHECK / trigger)
    _expect_violation(
        engine,
        "UPDATE interfaces SET parent_interface_id = id WHERE id = :id",
        {"id": a},
    )
    # cross-resource parent
    _expect_violation(
        engine,
        "UPDATE interfaces SET parent_interface_id = :p WHERE id = :id",
        {"p": foreign, "id": a},
    )
    # soft-deleted parent
    _expect_violation(
        engine,
        "UPDATE interfaces SET parent_interface_id = :p WHERE id = :id",
        {"p": soft, "id": a},
    )
    # 2-node cycle: b -> a while a -> b
    _expect_violation(
        engine,
        "UPDATE interfaces SET parent_interface_id = :p WHERE id = :id",
        {"p": a, "id": b},
    )
    # 3-node cycle: a -> b -> c then c -> a
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE interfaces SET parent_interface_id = :p WHERE id = :id"),
            {"p": c, "id": b},
        )
    _expect_violation(
        engine,
        "UPDATE interfaces SET parent_interface_id = :p WHERE id = :id",
        {"p": a, "id": c},
    )
    # missing referenced row is left to the FK
    _expect_violation(
        engine,
        "INSERT INTO interfaces (resource_id, name, parent_interface_id) "
        "VALUES (:rid, 'ghost', :p)",
        {"rid": rid, "p": uuid.uuid4()},
    )


# --- V-DB-61: resource_id / id immutable trigger ------------------------------


def test_immutable_resource_trigger(committed_engine):
    engine = committed_engine
    _, rid = _seed(engine, "imm")
    _, other = _seed(engine, "imm2")
    with engine.begin() as conn:
        iid = insert_interface(conn, rid, name="imm")
    _expect_violation(
        engine,
        "UPDATE interfaces SET resource_id = :other WHERE id = :id",
        {"other": other, "id": iid},
    )
    _expect_violation(
        engine,
        "UPDATE interfaces SET id = :new WHERE id = :id",
        {"new": uuid.uuid4(), "id": iid},
    )
    # Soft delete / normal update are not blocked.
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE interfaces SET deleted_at = now() WHERE id = :id"),
            {"id": iid},
        )
        conn.execute(
            text("UPDATE interfaces SET deleted_at = NULL WHERE id = :id"),
            {"id": iid},
        )


# --- V-DB-62: FK RESTRICT + soft-delete retention ----------------------------


def test_fk_restrict_and_soft_delete_retention(committed_engine):
    engine = committed_engine
    _, rid = _seed(engine, "fk")
    with engine.begin() as conn:
        parent = insert_interface(conn, rid, name="parent")
        child = insert_interface(conn, rid, name="child", parent_interface_id=parent)

    # physical delete of the referenced Resource is RESTRICTed
    _expect_violation(
        engine, "DELETE FROM resources WHERE id = :id", {"id": rid}
    )
    # physical delete of a referenced parent interface is RESTRICTed
    _expect_violation(
        engine, "DELETE FROM interfaces WHERE id = :id", {"id": parent}
    )

    # soft delete of the Resource keeps the Interface rows
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE resources SET deleted_at = now() WHERE id = :id"), {"id": rid}
        )
        assert conn.execute(
            text("SELECT count(*) FROM interfaces WHERE resource_id = :id"),
            {"id": rid},
        ).scalar_one() == 2

    # physical delete of the child frees the parent; then the Resource.
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM interfaces WHERE id = :id"), {"id": child})
        conn.execute(text("DELETE FROM interfaces WHERE id = :id"), {"id": parent})
        conn.execute(text("DELETE FROM resources WHERE id = :id"), {"id": rid})


# --- V-DB-63: metadata object CHECK ------------------------------------------


def test_metadata_object_check(committed_engine):
    engine = committed_engine
    _, rid = _seed(engine, "meta")
    with engine.begin() as conn:
        insert_interface(conn, rid, name="obj", metadata={"a": 1})
    for bad in ("[]", "1", '"x"', "null"):
        _expect_violation(
            engine,
            "INSERT INTO interfaces (resource_id, name, metadata) "
            f"VALUES (:rid, :name, '{bad}'::jsonb)",
            {"rid": rid, "name": f"bad-{bad}"},
        )


# --- V-DB-65: index usage -----------------------------------------------------


def test_indexes_are_used(committed_engine):
    engine = committed_engine
    _, rid = _seed(engine, "idx")
    with engine.begin() as conn:
        parent = insert_interface(conn, rid, name="p")
        for i in range(3):
            insert_interface(conn, rid, name=f"c{i}", parent_interface_id=parent)
        conn.execute(text("SET LOCAL enable_seqscan = off"))
        resource_plan = "\n".join(
            row[0]
            for row in conn.execute(
                text(
                    "EXPLAIN SELECT id FROM interfaces WHERE resource_id = :rid"
                ),
                {"rid": rid},
            ).all()
        )
    assert "ix_interfaces_resource_id" in resource_plan
    with engine.connect() as conn:
        conn.execute(text("SET enable_seqscan = off"))
        parent_plan = "\n".join(
            row[0]
            for row in conn.execute(
                text(
                    "EXPLAIN SELECT id FROM interfaces WHERE parent_interface_id = :p"
                ),
                {"p": parent},
            ).all()
        )
        conn.rollback()
    assert "ix_interfaces_parent_interface_id" in parent_plan


# --- V-DB-66: concurrent same-name insert ------------------------------------


def test_concurrent_same_name_insert(committed_engine):
    """Two concurrent inserts of the same (resource,name) -> exactly one wins."""
    engine = committed_engine
    _, rid = _seed(engine, "conc")

    barrier = threading.Barrier(2)
    results: list[str] = []
    lock = threading.Lock()

    def worker() -> None:
        try:
            barrier.wait(timeout=10)
            with engine.begin() as conn:
                insert_interface(conn, rid, name="race")
            with lock:
                results.append("ok")
        except Exception:
            with lock:
                results.append("error")

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=20)

    assert sorted(results) == ["error", "ok"], results
    with engine.connect() as conn:
        assert conn.execute(
            text(
                "SELECT count(*) FROM interfaces WHERE resource_id = :rid AND name = 'race'"
            ),
            {"rid": rid},
        ).scalar_one() == 1