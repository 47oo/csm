"""F006 virtual_machine_details database constraint / trigger / migration tests.

Real PostgreSQL only (DB-D10): SQLite cannot prove CHECK / FK CASCADE/RESTRICT /
trigger / migration behaviour. Raw SQL is used deliberately so the evidence does
not depend on ORM validation. Covers V-DB-40..V-DB-52.
"""

from __future__ import annotations

import threading
import time
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

VM_CONSTRAINTS = {
    "pk_virtual_machine_details",
    "fk_virtual_machine_details_resource_id_resources",
    "fk_virtual_machine_details_host_resource_id_resources",
    "ck_virtual_machine_details_vcpu_range",
    "ck_virtual_machine_details_memory_mb_range",
    "ck_virtual_machine_details_disk_gb_range",
    "ck_virtual_machine_details_hypervisor_format",
}

VM_COLUMNS = {
    "resource_id",
    "host_resource_id",
    "vcpu",
    "memory_mb",
    "disk_gb",
    "hypervisor",
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


def insert_vm(conn, resource_id: uuid.UUID, host_id: uuid.UUID, **cols) -> None:
    columns = {"resource_id": resource_id, "host_resource_id": host_id}
    columns.update(cols)
    names = ", ".join(columns)
    placeholders = ", ".join(f":{name}" for name in columns)
    conn.execute(
        text(
            f"INSERT INTO virtual_machine_details ({names}) "
            f"VALUES ({placeholders})"
        ),
        columns,
    )


def make_vm(conn, cluster_id, tag: str) -> uuid.UUID:
    hostname = f"vm-{tag}"
    return insert_resource(
        conn,
        cluster_id,
        hostname=hostname,
        hostname_key=hostname,
        resource_type="VIRTUAL_MACHINE",
    )


# --- V-DB-49: object catalogue and columns ------------------------------------


def test_table_shape_constraints_indexes_and_triggers(committed_engine):
    engine = committed_engine
    with engine.connect() as conn:
        columns = {
            row[0]
            for row in conn.execute(
                text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_schema = 'public' AND table_name = 'virtual_machine_details'"
                )
            )
        }
        assert columns == VM_COLUMNS
        # no metadata column (DR-69) and no soft-delete/version/timestamp columns
        assert not (
            {"metadata", "deleted_at", "version", "created_at", "updated_at"} & columns
        )

        found = set(
            conn.execute(
                text(
                    "SELECT conname FROM pg_constraint c "
                    "JOIN pg_class t ON c.conrelid = t.oid "
                    "WHERE t.relname = 'virtual_machine_details'"
                )
            ).scalars()
        )
        assert found == VM_CONSTRAINTS

        triggers = set(
            conn.execute(
                text(
                    "SELECT tgname FROM pg_trigger WHERE NOT tgisinternal "
                    "AND tgrelid = 'virtual_machine_details'::regclass"
                )
            ).scalars()
        )
        assert triggers == {
            "trg_virtual_machine_details_type_match",
            "trg_virtual_machine_details_host_valid",
        }

        indexes = set(
            conn.execute(
                text(
                    "SELECT indexname FROM pg_indexes WHERE schemaname = 'public' "
                    "AND tablename = 'virtual_machine_details'"
                )
            ).scalars()
        )
        assert indexes == {
            "pk_virtual_machine_details",
            "ix_virtual_machine_details_host_resource_id",
        }

        host_col = conn.execute(
            text(
                "SELECT is_nullable FROM information_schema.columns "
                "WHERE table_name = 'virtual_machine_details' AND column_name = 'host_resource_id'"
            )
        ).scalar_one()
        assert host_col == "NO"

        hypervisor_type = conn.execute(
            text(
                "SELECT data_type, character_maximum_length FROM information_schema.columns "
                "WHERE table_name = 'virtual_machine_details' AND column_name = 'hypervisor'"
            )
        ).one()
        assert hypervisor_type[0] == "character varying"
        assert hypervisor_type[1] == 255

        delete_types = dict(
            conn.execute(
                text(
                    "SELECT conname, confdeltype FROM pg_constraint "
                    "WHERE conname IN ('fk_virtual_machine_details_resource_id_resources', "
                    "'fk_virtual_machine_details_host_resource_id_resources')"
                )
            ).all()
        )
        assert delete_types["fk_virtual_machine_details_resource_id_resources"] == "c"
        assert delete_types["fk_virtual_machine_details_host_resource_id_resources"] == "r"


# --- helpers for constraint cases --------------------------------------------


def _seed(engine, tag: str):
    """Commit a cluster + BARE_METAL host + VM owner; return their ids."""
    code = f"CC-{tag}".upper()
    with engine.begin() as conn:
        cid = insert_cluster(conn, code=code, code_key=code, name=tag)
        host = insert_resource(
            conn, cid, hostname=f"host-{tag}", hostname_key=f"host-{tag}"
        )
        vm = make_vm(conn, cid, tag)
    return cid, host, vm


# --- V-DB-42/43: numeric ranges and disk 0 vs null ---------------------------


def test_numeric_ranges_and_disk_zero_vs_null(committed_engine):
    engine = committed_engine
    cid, host, _ = _seed(engine, "num")
    with engine.begin() as conn:
        zero = make_vm(conn, cid, "zero")
        unknown = make_vm(conn, cid, "unknown")
        edge = make_vm(conn, cid, "edge")
        insert_vm(conn, zero, host, disk_gb=0, vcpu=1, memory_mb=1)
        insert_vm(conn, unknown, host)
        insert_vm(
            conn, edge, host, vcpu=2147483647, memory_mb=2147483647, disk_gb=2147483647
        )

    for column in ("vcpu", "memory_mb"):
        for bad in (0, -1):
            _, host2, owner = _seed(engine, f"n{column}{bad}")
            _expect_violation(
                engine,
                f"INSERT INTO virtual_machine_details (resource_id, host_resource_id, {column}) "
                "VALUES (:rid, :hid, :value)",
                {"rid": owner, "hid": host2, "value": bad},
            )
    _, host3, owner3 = _seed(engine, "diskneg")
    _expect_violation(
        engine,
        "INSERT INTO virtual_machine_details (resource_id, host_resource_id, disk_gb) "
        "VALUES (:rid, :hid, -1)",
        {"rid": owner3, "hid": host3},
    )

    with engine.connect() as conn:
        zero_val = conn.execute(
            text(
                "SELECT disk_gb FROM virtual_machine_details WHERE resource_id = :id"
            ),
            {"id": zero},
        ).scalar_one()
        unknown_val = conn.execute(
            text(
                "SELECT disk_gb FROM virtual_machine_details WHERE resource_id = :id"
            ),
            {"id": unknown},
        ).scalar_one()
    assert zero_val == 0
    assert unknown_val is None
    assert zero_val != unknown_val


def test_hypervisor_format(committed_engine):
    engine = committed_engine
    cid, host, _ = _seed(engine, "hv")
    with engine.begin() as conn:
        ok = make_vm(conn, cid, "hv-ok")
        insert_vm(conn, ok, host, hypervisor="Proxmox")
        length_ok = make_vm(conn, cid, "hv-255")
        insert_vm(conn, length_ok, host, hypervisor="m" * 255)

    for i, bad in enumerate(("", "   ", " trailing", "leading ", "m" * 256)):
        _, host2, owner = _seed(engine, f"hvb{i}")
        _expect_violation(
            engine,
            "INSERT INTO virtual_machine_details (resource_id, host_resource_id, hypervisor) "
            "VALUES (:rid, :hid, :value)",
            {"rid": owner, "hid": host2, "value": bad},
        )


# --- V-DB-45/46/48: type_match + host_valid triggers + PK ---------------------


def test_type_match_trigger(committed_engine):
    engine = committed_engine
    cid, bare, vm = _seed(engine, "tm")
    with engine.begin() as conn:
        insert_vm(conn, vm, bare)

    # detail owner must be a VIRTUAL_MACHINE (bare owns its own detail attempt)
    _expect_violation(
        engine,
        "INSERT INTO virtual_machine_details (resource_id, host_resource_id) "
        "VALUES (:rid, :hid)",
        {"rid": bare, "hid": bare},
    )
    # UPDATE moving a VM detail onto a BARE_METAL resource is rejected
    _expect_violation(
        engine,
        "UPDATE virtual_machine_details SET resource_id = :bare WHERE resource_id = :vm",
        {"bare": bare, "vm": vm},
    )
    # missing owner row left to the FK
    _expect_violation(
        engine,
        "INSERT INTO virtual_machine_details (resource_id, host_resource_id) "
        "VALUES (:rid, :hid)",
        {"rid": uuid.uuid4(), "hid": bare},
    )


def test_host_valid_trigger(committed_engine):
    engine = committed_engine
    with engine.begin() as conn:
        cid = insert_cluster(conn, code="HV1", code_key="HV1", name="hv1")
        other = insert_cluster(conn, code="HV2", code_key="HV2", name="hv2")
        bare = insert_resource(conn, cid, hostname="hv-bare", hostname_key="hv-bare")
        foreign = insert_resource(
            conn, other, hostname="hv-foreign", hostname_key="hv-foreign"
        )
        vm_host = make_vm(conn, cid, "hv-vmhost")
        soft = insert_resource(
            conn, cid, hostname="hv-soft", hostname_key="hv-soft"
        )
        conn.execute(
            text("UPDATE resources SET deleted_at = now() WHERE id = :id"), {"id": soft}
        )
        valid_owner = make_vm(conn, cid, "hv-valid")
        insert_vm(conn, valid_owner, bare)  # valid: undeleted same-cluster BARE_METAL

    for tag, host_candidate in (
        ("vmhost", vm_host),
        ("cross", foreign),
        ("soft", soft),
    ):
        with engine.begin() as conn:
            owner = make_vm(conn, cid, f"hv-target-{tag}")
        _expect_violation(
            engine,
            "INSERT INTO virtual_machine_details (resource_id, host_resource_id) "
            "VALUES (:rid, :hid)",
            {"rid": owner, "hid": host_candidate},
        )

    # missing host left to the FK
    with engine.begin() as conn:
        owner = make_vm(conn, cid, "hv-missing")
    _expect_violation(
        engine,
        "INSERT INTO virtual_machine_details (resource_id, host_resource_id) "
        "VALUES (:rid, :hid)",
        {"rid": owner, "hid": uuid.uuid4()},
    )


def test_pk_single_row_per_resource(committed_engine):
    engine = committed_engine
    cid, host, vm = _seed(engine, "pk")
    with engine.begin() as conn:
        insert_vm(conn, vm, host, vcpu=2)
    _expect_violation(
        engine,
        "INSERT INTO virtual_machine_details (resource_id, host_resource_id, vcpu) "
        "VALUES (:rid, :hid, 4)",
        {"rid": vm, "hid": host},
    )


# --- V-DB-47: FK CASCADE / RESTRICT / soft delete -----------------------------


def test_fk_cascade_restrict_and_soft_delete(committed_engine):
    engine = committed_engine
    cid, host, vm = _seed(engine, "fk")
    with engine.begin() as conn:
        insert_vm(conn, vm, host)

    # physical delete of the referenced Host is RESTRICTed
    _expect_violation(engine, "DELETE FROM resources WHERE id = :id", {"id": host})

    # soft delete of the VM keeps the detail row
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE resources SET deleted_at = now() WHERE id = :id"), {"id": vm}
        )
        assert conn.execute(
            text("SELECT count(*) FROM virtual_machine_details WHERE resource_id = :id"),
            {"id": vm},
        ).scalar_one() == 1

    # physical delete of the VM CASCADEs the detail; then the Host can go
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM resources WHERE id = :id"), {"id": vm})
        assert conn.execute(
            text("SELECT count(*) FROM virtual_machine_details WHERE resource_id = :id"),
            {"id": vm},
        ).scalar_one() == 0
        conn.execute(text("DELETE FROM resources WHERE id = :id"), {"id": host})


# --- V-DB-50: host_resource_id index -----------------------------------------


def test_host_resource_id_index_exists_and_used(committed_engine):
    engine = committed_engine
    cid, host, _ = _seed(engine, "idx")
    with engine.begin() as conn:
        for i in range(3):
            vm = make_vm(conn, cid, f"idx{i}")
            insert_vm(conn, vm, host)
        conn.execute(text("SET LOCAL enable_seqscan = off"))
        plan = "\n".join(
            row[0]
            for row in conn.execute(
                text(
                    "EXPLAIN SELECT resource_id FROM virtual_machine_details "
                    "WHERE host_resource_id = :host"
                ),
                {"host": host},
            ).all()
        )
    assert "ix_virtual_machine_details_host_resource_id" in plan


# --- V-DB-51: true concurrency physical delete vs insert ----------------------


def test_physical_delete_concurrent_with_insert(committed_engine):
    """A committed insert referencing the Host blocks a physical DELETE; once
    committed the DELETE is refused by the FK RESTRICT (V-DB-51/B25)."""
    engine = committed_engine
    cid, host, vm = _seed(engine, "conc51")

    result: dict = {}

    def deleter():
        try:
            with engine.begin() as conn:
                conn.execute(text("DELETE FROM resources WHERE id = :id"), {"id": host})
            result["ok"] = True
        except Exception as exc:
            result["error"] = type(exc).__name__

    conn = engine.connect()
    txn = conn.begin()
    try:
        # Uncommitted insert referencing the Host holds the FK key-share lock.
        insert_vm(conn, vm, host)
        thread = threading.Thread(target=deleter)
        thread.start()
        time.sleep(0.6)
        assert thread.is_alive(), "physical delete must block on the FK lock"
        txn.commit()
    finally:
        conn.close()
    thread.join(timeout=15)
    assert not thread.is_alive()
    assert result.get("ok") is not True
    assert "error" in result


# --- V-DB-40/41: migration up/down/up and backfill guard ----------------------


def test_migration_single_head_and_up_down_up(pg_engine, alembic_runner):
    assert alembic_runner.head_revision() == "0007_interfaces"
    assert _alembic_versions(pg_engine) == ["0007_interfaces"]
    assert "virtual_machine_details" in _tables(pg_engine)

    alembic_runner.downgrade("0005_bare_metal_details")
    remaining = _tables(pg_engine)
    assert "virtual_machine_details" not in remaining
    assert "bare_metal_details" in remaining
    with pg_engine.connect() as conn:
        funcs = set(
            conn.execute(
                text(
                    "SELECT proname FROM pg_proc "
                    "WHERE proname LIKE 'fn_virtual_machine%'"
                )
            ).scalars()
        )
    assert funcs == set()
    assert _alembic_versions(pg_engine) == ["0005_bare_metal_details"]

    alembic_runner.upgrade("head")
    assert {"bare_metal_details", "virtual_machine_details"} <= _tables(pg_engine)
    assert _alembic_versions(pg_engine) == ["0007_interfaces"]


def test_backfill_guard(pg_engine, alembic_runner):
    """V-DB-41: undeleted VM refuses upgrade; soft-deleted / none passes."""
    try:
        # Case 1: undeleted VIRTUAL_MACHINE -> upgrade aborts, no detail synthesized.
        alembic_runner.downgrade("0005_bare_metal_details")
        with pg_engine.begin() as conn:
            cid = insert_cluster(conn, code="BG", code_key="BG", name="bg")
            vm = make_vm(conn, cid, "bg")

        with pytest.raises(Exception) as excinfo:
            alembic_runner.upgrade("head")
        assert "VIRTUAL_MACHINE" in str(excinfo.value)
        assert "virtual_machine_details" not in _tables(pg_engine)
        assert _alembic_versions(pg_engine) == ["0005_bare_metal_details"]
        with pg_engine.connect() as conn:
            assert (
                conn.execute(
                    text("SELECT deleted_at FROM resources WHERE id = :id"), {"id": vm}
                ).scalar_one()
                is None
            )

        # Case 2: soft-deleted VM -> upgrade passes and creates no detail row.
        with pg_engine.begin() as conn:
            conn.execute(
                text("UPDATE resources SET deleted_at = now() WHERE id = :id"),
                {"id": vm},
            )
        alembic_runner.upgrade("head")
        assert _alembic_versions(pg_engine) == ["0007_interfaces"]
        with pg_engine.connect() as conn:
            assert (
                conn.execute(
                    text("SELECT count(*) FROM virtual_machine_details")
                ).scalar_one()
                == 0
            )

        # Case 3: no VM -> downgrade/upgrade is a clean no-op guard.
        with pg_engine.begin() as conn:
            conn.execute(text("DELETE FROM resources WHERE id = :id"), {"id": vm})
            conn.execute(text("DELETE FROM clusters WHERE code = 'BG'"))
        alembic_runner.downgrade("0005_bare_metal_details")
        alembic_runner.upgrade("head")
        assert _alembic_versions(pg_engine) == ["0007_interfaces"]
    finally:
        if _alembic_versions(pg_engine) != ["0007_interfaces"]:
            alembic_runner.upgrade("head")