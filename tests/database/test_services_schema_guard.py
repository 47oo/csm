"""F008 Service 数据库结构 guard（绕过应用层，直接断言迁移后的实际 Schema）。

- ``services`` 列集合**恰为** 11 列；``service_carriers`` 恰为 5 列；
- ``services`` 约束**恰为 1 个**（``pk_services``，**无 CHECK**）；
- ``service_carriers`` CHECK 恰为 ``{ck_service_carriers_exactly_one_carrier}``；
- FK 集合精确（4 条 ``RESTRICT`` / ``RESTRICT``）；PK 名精确；
- 3 条 partial unique predicate 含对应载体列 ``IS NOT NULL`` 且**不用** ``lower()``；
- ``ux_services_name_active`` predicate 含 ``deleted_at IS NULL`` 且不用 ``lower()``；
- ``service_carriers`` **无** ``deleted_at`` / 时间戳 / 判别列；
- 所有列 ``collation_name IS NULL``；无触发器；
- 既有表结构未被本 migration 改变。
"""

from __future__ import annotations

EXPECTED_SERVICES_COLUMNS = {
    "id",
    "name",
    "service_type",
    "url",
    "port",
    "protocol",
    "owner",
    "description",
    "created_at",
    "updated_at",
    "deleted_at",
}

EXPECTED_SERVICE_CARRIERS_COLUMNS = {
    "id",
    "service_id",
    "bare_metal_id",
    "virtual_machine_id",
    "container_id",
}

OPTIONAL_FIELDS = ("service_type", "url", "port", "protocol", "owner", "description")


def _columns(raw_conn, table: str) -> set[str]:
    return {
        row[0]
        for row in raw_conn.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = 'public' AND table_name = %s",
            (table,),
        ).fetchall()
    }


# --------------------------------------------------------------------------- #
# 列集合
# --------------------------------------------------------------------------- #
def test_services_column_set_is_exactly_eleven(raw_conn):
    assert _columns(raw_conn, "services") == EXPECTED_SERVICES_COLUMNS


def test_service_carriers_column_set_is_exactly_five(raw_conn):
    assert _columns(raw_conn, "service_carriers") == EXPECTED_SERVICE_CARRIERS_COLUMNS


def test_no_status_or_cluster_or_carrier_columns(raw_conn):
    services = _columns(raw_conn, "services")
    assert "status" not in services
    assert "state" not in services
    assert not any("cluster" in column for column in services)
    assert not any(
        column in services for column in ("bare_metal_id", "virtual_machine_id", "container_id")
    )

    carriers = _columns(raw_conn, "service_carriers")
    assert "deleted_at" not in carriers
    assert "created_at" not in carriers
    assert "updated_at" not in carriers
    assert "carrier_type" not in carriers
    assert "status" not in carriers


def test_service_carriers_has_no_soft_delete_or_timestamps(raw_conn):
    """绑定表是关系表：无 ``deleted_at``、无时间戳（释放由 services.deleted_at 派生）。"""
    carriers = _columns(raw_conn, "service_carriers")
    assert carriers.isdisjoint({"deleted_at", "created_at", "updated_at"})


# --------------------------------------------------------------------------- #
# 约束集合（services 恰 1 个约束 = PK，0 CHECK；carriers 恰 1 CHECK + 4 FK + PK）
# --------------------------------------------------------------------------- #
def test_services_has_exactly_one_constraint_pk_and_no_check(raw_conn):
    constraints = raw_conn.execute(
        "SELECT conname, contype FROM pg_constraint WHERE conrelid = 'services'::regclass"
    ).fetchall()
    assert [row[0] for row in constraints] == ["pk_services"]
    assert [row[1] for row in constraints] == ["p"]

    checks = raw_conn.execute(
        "SELECT conname FROM pg_constraint WHERE conrelid = 'services'::regclass AND contype = 'c'"
    ).fetchall()
    assert checks == [], "services 不得有任何 CHECK"


def test_service_carriers_check_set_is_exactly_exactly_one_carrier(raw_conn):
    checks = {
        row[0]: row[1]
        for row in raw_conn.execute(
            "SELECT conname, pg_get_constraintdef(oid) FROM pg_constraint "
            "WHERE conrelid = 'service_carriers'::regclass AND contype = 'c'"
        ).fetchall()
    }
    assert set(checks) == {"ck_service_carriers_exactly_one_carrier"}
    definition = checks["ck_service_carriers_exactly_one_carrier"]
    assert "num_nonnulls" in definition
    for column in ("bare_metal_id", "virtual_machine_id", "container_id"):
        assert column in definition


def test_service_carriers_foreign_keys_are_exactly_four_restrict(raw_conn):
    fks = raw_conn.execute(
        "SELECT conname, confdeltype, confupdtype FROM pg_constraint "
        "WHERE conrelid = 'service_carriers'::regclass AND contype = 'f'"
    ).fetchall()
    assert {row[0] for row in fks} == {
        "fk_service_carriers_service",
        "fk_service_carriers_bare_metal",
        "fk_service_carriers_virtual_machine",
        "fk_service_carriers_container",
    }
    for _, confdel, confupd in fks:
        assert (confdel, confupd) == ("r", "r"), "FK 必须为 RESTRICT / RESTRICT（禁止 CASCADE）"


def test_primary_keys_are_expected(raw_conn):
    services_pk = raw_conn.execute(
        "SELECT conname FROM pg_constraint WHERE conrelid='services'::regclass AND contype='p'"
    ).fetchall()
    carriers_pk = raw_conn.execute(
        "SELECT conname FROM pg_constraint "
        "WHERE conrelid='service_carriers'::regclass AND contype='p'"
    ).fetchall()
    assert [row[0] for row in services_pk] == ["pk_services"]
    assert [row[0] for row in carriers_pk] == ["pk_service_carriers"]


# --------------------------------------------------------------------------- #
# 索引存在性与 predicate
# --------------------------------------------------------------------------- #
def test_services_name_partial_unique_index(raw_conn):
    row = raw_conn.execute(
        "SELECT indexdef FROM pg_indexes WHERE schemaname='public' "
        "AND indexname='ux_services_name_active'"
    ).fetchone()
    assert row is not None
    definition = row[0]
    assert "UNIQUE" in definition
    assert "deleted_at IS NULL" in definition
    assert "lower(" not in definition.lower()


def test_service_carriers_partial_unique_and_plain_indexes(raw_conn):
    for index_name, carrier_column in (
        ("ux_service_carriers_service_bare_metal", "bare_metal_id"),
        ("ux_service_carriers_service_virtual_machine", "virtual_machine_id"),
        ("ux_service_carriers_service_container", "container_id"),
    ):
        row = raw_conn.execute(
            "SELECT indexdef FROM pg_indexes WHERE schemaname='public' AND indexname=%s",
            (index_name,),
        ).fetchone()
        assert row is not None, f"{index_name} 缺失"
        definition = row[0]
        assert "UNIQUE" in definition
        assert "service_id" in definition
        assert carrier_column in definition
        assert f"{carrier_column} IS NOT NULL" in definition
        assert "lower(" not in definition.lower()

    for index_name, carrier_column in (
        ("ix_service_carriers_bare_metal_id", "bare_metal_id"),
        ("ix_service_carriers_virtual_machine_id", "virtual_machine_id"),
        ("ix_service_carriers_container_id", "container_id"),
    ):
        row = raw_conn.execute(
            "SELECT indexdef FROM pg_indexes WHERE schemaname='public' AND indexname=%s",
            (index_name,),
        ).fetchone()
        assert row is not None, f"{index_name} 缺失"
        assert carrier_column in row[0]

    row = raw_conn.execute(
        "SELECT indexdef FROM pg_indexes WHERE schemaname='public' "
        "AND indexname='ix_service_carriers_service_id'"
    ).fetchone()
    assert row is not None and "service_id" in row[0]


# --------------------------------------------------------------------------- #
# 无 collation / 无触发器 / 未定义约束不实现
# --------------------------------------------------------------------------- #
def test_no_explicit_collation(raw_conn):
    rows = raw_conn.execute(
        "SELECT table_name, column_name FROM information_schema.columns "
        "WHERE table_schema='public' AND table_name IN ('services', 'service_carriers') "
        "AND collation_name IS NOT NULL"
    ).fetchall()
    assert rows == [], f"不应声明列级 collation：{rows}"


def test_no_triggers(raw_conn):
    for table in ("services", "service_carriers"):
        triggers = raw_conn.execute(
            "SELECT tgname FROM pg_trigger WHERE tgrelid = %s::regclass AND NOT tgisinternal",
            (table,),
        ).fetchall()
        assert triggers == [], f"{table} 不得使用触发器：{triggers}"


def test_no_undefined_field_checks(raw_conn):
    definitions = raw_conn.execute(
        "SELECT pg_get_constraintdef(oid) FROM pg_constraint "
        "WHERE conrelid = 'services'::regclass AND contype = 'c'"
    ).fetchall()
    combined = " ".join(row[0] for row in definitions)
    for forbidden in ("length(", "trim(", "strpos("):
        assert forbidden not in combined


def test_name_and_optional_columns_are_text_without_length(raw_conn):
    rows = dict(
        raw_conn.execute(
            "SELECT column_name, character_maximum_length FROM information_schema.columns "
            "WHERE table_schema='public' AND table_name='services'"
        ).fetchall()
    )
    for field in ("name", *OPTIONAL_FIELDS):
        assert rows[field] is None, f"{field} 不得声明长度上限"


def test_not_null_and_nullability(raw_conn):
    rows = dict(
        raw_conn.execute(
            "SELECT column_name, is_nullable FROM information_schema.columns "
            "WHERE table_schema='public' AND table_name='services'"
        ).fetchall()
    )
    assert rows["id"] == "NO"
    assert rows["name"] == "NO"
    assert rows["created_at"] == "NO"
    assert rows["updated_at"] == "NO"
    assert rows["deleted_at"] == "YES"
    for field in OPTIONAL_FIELDS:
        assert rows[field] == "YES", f"{field} 必须允许 NULL"

    carrier_rows = dict(
        raw_conn.execute(
            "SELECT column_name, is_nullable FROM information_schema.columns "
            "WHERE table_schema='public' AND table_name='service_carriers'"
        ).fetchall()
    )
    assert carrier_rows["service_id"] == "NO"
    for column in ("bare_metal_id", "virtual_machine_id", "container_id"):
        assert carrier_rows[column] == "YES", column


# --------------------------------------------------------------------------- #
# 既有表结构未被本 migration 改变
# --------------------------------------------------------------------------- #
def test_existing_tables_structure_unchanged(raw_conn):
    expected = {
        "clusters": {"id", "name", "created_at", "updated_at", "deleted_at"},
        "bare_metals": {
            "id",
            "cluster_id",
            "hostname",
            "status",
            "vendor",
            "model",
            "serial_number",
            "cpu",
            "memory",
            "gpu",
            "storage",
            "created_at",
            "updated_at",
            "deleted_at",
        },
        "virtual_machines": {
            "id",
            "bare_metal_id",
            "name",
            "cpu",
            "memory",
            "disk",
            "os",
            "hypervisor",
            "owner",
            "created_at",
            "updated_at",
            "deleted_at",
        },
        "containers": {
            "id",
            "bare_metal_id",
            "virtual_machine_id",
            "name",
            "image",
            "cpu",
            "memory",
            "owner",
            "created_at",
            "updated_at",
            "deleted_at",
        },
    }
    for table, columns in expected.items():
        assert _columns(raw_conn, table) == columns, f"{table} 列集合被改变"
