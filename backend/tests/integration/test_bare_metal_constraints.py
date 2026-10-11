"""F005 bare_metal_details database constraint / trigger / migration tests.

Real PostgreSQL only (DB-D10): SQLite cannot prove CHECK / FK CASCADE / JSONB /
trigger / migration behaviour. Raw SQL is used deliberately so the evidence does
not depend on ORM validation. Covers V-DB-29..V-DB-39 and V13/V14/B25-B29.
"""

from __future__ import annotations

import json
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

BARE_METAL_CONSTRAINTS = {
    "pk_bare_metal_details",
    "fk_bare_metal_details_resource_id_resources",
    "ck_bare_metal_details_manufacturer_format",
    "ck_bare_metal_details_model_format",
    "ck_bare_metal_details_serial_number_format",
    "ck_bare_metal_details_cpu_model_format",
    "ck_bare_metal_details_gpu_model_format",
    "ck_bare_metal_details_cpu_sockets_range",
    "ck_bare_metal_details_cpu_cores_range",
    "ck_bare_metal_details_memory_mb_range",
    "ck_bare_metal_details_gpu_count_range",
    "ck_bare_metal_details_metadata_object",
}

HARDWARE_COLUMNS = {
    "resource_id",
    "manufacturer",
    "model",
    "serial_number",
    "cpu_model",
    "gpu_model",
    "cpu_sockets",
    "cpu_cores",
    "memory_mb",
    "gpu_count",
    "metadata",
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
        text(
            f"INSERT INTO resources ({names}) VALUES ({placeholders}) RETURNING id"
        ),
        columns,
    ).scalar_one()


def insert_detail(conn, resource_id: uuid.UUID, **cols) -> None:
    columns = {"resource_id": resource_id}
    columns.update(cols)
    names = ", ".join(columns)
    params: dict = {}
    placeholders = []
    for name, value in columns.items():
        if name == "metadata" and isinstance(value, (dict, list)):
            params[name] = json.dumps(value)
            placeholders.append(f"CAST(:{name} AS jsonb)")
        else:
            params[name] = value
            placeholders.append(f":{name}")
    conn.execute(
        text(f"INSERT INTO bare_metal_details ({names}) VALUES ({', '.join(placeholders)})"),
        params,
    )


# --- V13/V-DB-39: object catalogue and columns --------------------------------


def test_table_shape_constraints_and_trigger(committed_engine):
    engine = committed_engine
    with engine.connect() as conn:
        columns = {
            row[0]
            for row in conn.execute(
                text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_schema = 'public' AND table_name = 'bare_metal_details'"
                )
            )
        }
        assert columns == HARDWARE_COLUMNS
        assert not ({"deleted_at", "version", "created_at", "updated_at"} & columns)

        found = set(
            conn.execute(
                text(
                    "SELECT conname FROM pg_constraint c "
                    "JOIN pg_class t ON c.conrelid = t.oid "
                    "WHERE t.relname = 'bare_metal_details'"
                )
            ).scalars()
        )
        assert found == BARE_METAL_CONSTRAINTS

        triggers = set(
            conn.execute(
                text("SELECT tgname FROM pg_trigger WHERE NOT tgisinternal")
            ).scalars()
        )
        assert "trg_bare_metal_details_type_match" in triggers

        indexes = set(
            conn.execute(
                text(
                    "SELECT indexname FROM pg_indexes WHERE schemaname = 'public' "
                    "AND tablename = 'bare_metal_details'"
                )
            ).scalars()
        )
        assert indexes == {"pk_bare_metal_details"}

        # metadata NOT NULL DEFAULT '{}'
        column_meta = conn.execute(
            text(
                "SELECT is_nullable, column_default FROM information_schema.columns "
                "WHERE table_name = 'bare_metal_details' AND column_name = 'metadata'"
            )
        ).one()
        assert column_meta[0] == "NO"
        assert "{}" in column_meta[1]

        fk_delete = conn.execute(
            text(
                "SELECT confdeltype FROM pg_constraint "
                "WHERE conname = 'fk_bare_metal_details_resource_id_resources'"
            )
        ).scalar_one()
        assert fk_delete == "c"


def test_orm_maps_metadata_column_to_meta_attribute():
    from app.models.bare_metal_detail import BareMetalDetail

    assert "metadata" in BareMetalDetail.__table__.c
    assert BareMetalDetail.meta.property.columns[0].name == "metadata"


# --- V-DB-31/32/33: numeric ranges and 0-vs-NULL ------------------------------


def test_positive_int_ranges(committed_engine):
    engine = committed_engine
    with engine.begin() as conn:
        cid = insert_cluster(conn)
        accepted = insert_resource(conn, cid, hostname="ok", hostname_key="ok")
        insert_detail(conn, accepted)
        insert_detail(
            conn,
            insert_resource(conn, cid, hostname="min", hostname_key="min"),
            cpu_sockets=1,
            cpu_cores=1,
            memory_mb=1,
            gpu_count=0,
        )
        insert_detail(
            conn,
            insert_resource(conn, cid, hostname="max", hostname_key="max"),
            cpu_sockets=2147483647,
            cpu_cores=2147483647,
            memory_mb=2147483647,
            gpu_count=2147483647,
        )

    for column in ("cpu_sockets", "cpu_cores", "memory_mb"):
        for bad in (0, -1):
            _expect_violation(
                engine,
                f"INSERT INTO bare_metal_details (resource_id, {column}) "
                "VALUES (:rid, :value)",
                {"rid": uuid.uuid4(), "value": bad},
            )


def test_gpu_count_range_and_distinction(committed_engine):
    engine = committed_engine
    with engine.begin() as conn:
        cid = insert_cluster(conn)
        zero = insert_resource(conn, cid, hostname="g0", hostname_key="g0")
        unknown = insert_resource(conn, cid, hostname="gn", hostname_key="gn")
        insert_detail(conn, zero, gpu_count=0)
        insert_detail(conn, unknown)
    _expect_violation(
        engine,
        "INSERT INTO bare_metal_details (resource_id, gpu_count) VALUES (:rid, -1)",
        {"rid": uuid.uuid4()},
    )
    with engine.connect() as conn:
        rows = dict(
            conn.execute(
                text(
                    "SELECT r.hostname, d.gpu_count FROM resources r "
                    "JOIN bare_metal_details d ON d.resource_id = r.id"
                )
            ).all()
        )
    assert rows["g0"] == 0
    assert rows["gn"] is None
    assert rows["g0"] != rows["gn"]


# --- V-DB-34: string trim / non-empty / length --------------------------------


def test_string_format_checks(committed_engine):
    engine = committed_engine
    with engine.begin() as conn:
        cid = insert_cluster(conn)
        ok = insert_resource(conn, cid, hostname="s-ok", hostname_key="s-ok")
        insert_detail(conn, ok)  # all NULL accepted
        insert_detail(
            conn,
            insert_resource(conn, cid, hostname="s-full", hostname_key="s-full"),
            manufacturer="Dell",
            model="m" * 255,
            serial_number="SN",
            cpu_model="EPYC",
            gpu_model="H100",
        )

    for bad in ("", "   ", " trailing", "leading ", "x" * 256):
        _expect_violation(
            engine,
            "INSERT INTO bare_metal_details (resource_id, manufacturer) "
            "VALUES (:rid, :value)",
            {"rid": uuid.uuid4(), "value": bad},
        )


# --- V-DB-35: metadata object JSONB -------------------------------------------


def test_metadata_object_check_and_default(committed_engine):
    engine = committed_engine
    with engine.begin() as conn:
        cid = insert_cluster(conn)
        rid = insert_resource(conn, cid, hostname="m", hostname_key="m")
        insert_detail(conn, rid)
    with engine.connect() as conn:
        assert conn.execute(
            text("SELECT metadata FROM bare_metal_details WHERE resource_id = :id"),
            {"id": rid},
        ).scalar_one() == {}

    with engine.begin() as conn:
        cid = insert_cluster(conn, code="M2", code_key="M2", name="m2")
        targets = [
            insert_resource(conn, cid, hostname=f"mbad{i}", hostname_key=f"mbad{i}")
            for i in range(4)
        ]
    for target, bad in zip(targets, ("'[]'::jsonb", "'\"x\"'::jsonb", "'null'::jsonb", "'1'::jsonb")):
        _expect_violation(
            engine,
            f"INSERT INTO bare_metal_details (resource_id, metadata) VALUES (:rid, {bad})",
            {"rid": target},
        )
    # JSON null literal is rejected by NOT NULL as well
    _expect_violation(
        engine,
        "INSERT INTO bare_metal_details (resource_id, metadata) VALUES (:rid, NULL)",
        {"rid": targets[0]},
    )


# --- V-DB-36: type-match trigger ----------------------------------------------


def test_type_match_trigger(committed_engine):
    engine = committed_engine
    with engine.begin() as conn:
        cid = insert_cluster(conn)
        bare = insert_resource(conn, cid, hostname="bare", hostname_key="bare")
        vm = insert_resource(
            conn, cid, hostname="vm", hostname_key="vm", resource_type="VIRTUAL_MACHINE"
        )
        insert_detail(conn, bare, cpu_cores=8)

    _expect_violation(
        engine,
        "INSERT INTO bare_metal_details (resource_id) VALUES (:rid)",
        {"rid": vm},
    )
    # UPDATE moving a BARE_METAL detail onto a VM is rejected too
    _expect_violation(
        engine,
        "UPDATE bare_metal_details SET resource_id = :vm WHERE resource_id = :bare",
        {"vm": vm, "bare": bare},
    )


# --- V-DB-37: FK / CASCADE / soft delete --------------------------------------


def test_fk_cascade_and_soft_delete(committed_engine):
    engine = committed_engine
    with engine.begin() as conn:
        cid = insert_cluster(conn)
        bare = insert_resource(conn, cid, hostname="bare", hostname_key="bare")
        insert_detail(conn, bare, cpu_cores=4)

    # nonexistent resource rejected (FK, not masked by the type trigger)
    _expect_violation(
        engine,
        "INSERT INTO bare_metal_details (resource_id) VALUES (:rid)",
        {"rid": uuid.uuid4()},
    )

    # soft delete keeps the detail row
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE resources SET deleted_at = now() WHERE id = :id"), {"id": bare}
        )
        assert conn.execute(
            text("SELECT count(*) FROM bare_metal_details WHERE resource_id = :id"),
            {"id": bare},
        ).scalar_one() == 1

    # physical delete cascades
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM resources WHERE id = :id"), {"id": bare})
        assert conn.execute(
            text("SELECT count(*) FROM bare_metal_details WHERE resource_id = :id"),
            {"id": bare},
        ).scalar_one() == 0


# --- V-DB-38: 1:1 PK ----------------------------------------------------------


def test_single_row_per_resource(committed_engine):
    engine = committed_engine
    with engine.begin() as conn:
        cid = insert_cluster(conn)
        bare = insert_resource(conn, cid, hostname="one", hostname_key="one")
        insert_detail(conn, bare, cpu_cores=1)
    _expect_violation(
        engine,
        "INSERT INTO bare_metal_details (resource_id, cpu_cores) VALUES (:rid, 2)",
        {"rid": bare},
    )


# --- V-DB-39: SN has no unique index / no extra indexes -----------------------


def test_no_serial_unique_and_no_extra_indexes(committed_engine):
    engine = committed_engine
    with engine.begin() as conn:
        cid = insert_cluster(conn)
        for host in ("sn1", "sn2"):
            rid = insert_resource(conn, cid, hostname=host, hostname_key=host)
            insert_detail(conn, rid, serial_number="SAME-SN")
    with engine.connect() as conn:
        sn_unique = conn.execute(
            text(
                "SELECT indexdef FROM pg_indexes WHERE schemaname='public' "
                "AND tablename='bare_metal_details' AND indexdef ILIKE '%unique%' "
                "AND indexdef ILIKE '%serial_number%'"
            )
        ).scalars().all()
        assert sn_unique == []
        # only the PK index exists (no hardware filter/sort indexes)
        assert {
            row[0]
            for row in conn.execute(
                text(
                    "SELECT indexname FROM pg_indexes WHERE schemaname='public' "
                    "AND tablename='bare_metal_details'"
                )
            )
        } == {"pk_bare_metal_details"}
        assert (
            conn.execute(
                text("SELECT count(*) FROM bare_metal_details WHERE serial_number='SAME-SN'")
            ).scalar_one()
            == 2
        )


# --- V14/B25-B29: migration up/down/up and backfill ---------------------------


def test_migration_is_single_head(pg_engine, alembic_runner):
    assert alembic_runner.head_revision() == "0011_services"
    assert _alembic_versions(pg_engine) == ["0011_services"]
    assert "bare_metal_details" in _tables(pg_engine)
    assert "virtual_machine_details" in _tables(pg_engine)


def test_migration_up_down_up(pg_engine, alembic_runner):
    assert alembic_runner.head_revision() == "0011_services"

    alembic_runner.downgrade("0004_resources")
    remaining = _tables(pg_engine)
    assert "bare_metal_details" not in remaining
    assert "virtual_machine_details" not in remaining
    # 0004 objects survive the 0005/0006 downgrade
    assert {"resources", "clusters", "audit_logs"} <= remaining
    assert _alembic_versions(pg_engine) == ["0004_resources"]

    alembic_runner.upgrade("head")
    assert {
        "resources",
        "bare_metal_details",
        "virtual_machine_details",
    } <= _tables(pg_engine)
    assert _alembic_versions(pg_engine) == ["0011_services"]


def test_backfill_existing_resources(pg_engine, alembic_runner):
    """V-DB-30/B27: pre-existing BARE_METAL gets an all-null row, VM none."""
    alembic_runner.downgrade("0004_resources")
    try:
        with pg_engine.begin() as conn:
            cid = insert_cluster(conn, code="BF", code_key="BF", name="bf")
            bare = insert_resource(
                conn, cid, hostname="bf-bare", hostname_key="bf-bare"
            )
            vm = insert_resource(
                conn,
                cid,
                hostname="bf-vm",
                hostname_key="bf-vm",
                resource_type="VIRTUAL_MACHINE",
            )
            # The F006 0006 backfill guard refuses undeleted VMs (no safe
            # host); a soft-deleted VM still exercises the 0005 backfill scope.
            conn.execute(
                text("UPDATE resources SET deleted_at = now() WHERE id = :id"),
                {"id": vm},
            )

        alembic_runner.upgrade("head")
        with pg_engine.connect() as conn:
            rows = conn.execute(
                text(
                    "SELECT resource_id, manufacturer, model, serial_number, "
                    "cpu_model, gpu_model, cpu_sockets, cpu_cores, memory_mb, "
                    "gpu_count, metadata FROM bare_metal_details"
                )
            ).mappings().all()
        assert {row["resource_id"] for row in rows} == {bare}
        row = rows[0]
        assert row["metadata"] == {}
        for column in (
            "manufacturer",
            "model",
            "serial_number",
            "cpu_model",
            "gpu_model",
            "cpu_sockets",
            "cpu_cores",
            "memory_mb",
            "gpu_count",
        ):
            assert row[column] is None
        assert vm not in {row["resource_id"] for row in rows}
    finally:
        # leave the session schema clean for later tests
        with pg_engine.begin() as conn:
            conn.execute(
                text("DELETE FROM resources WHERE hostname LIKE 'bf-%'")
            )
            conn.execute(text("DELETE FROM clusters WHERE code = 'BF'"))
        assert _alembic_versions(pg_engine) == ["0011_services"]