"""F007 Container 数据库结构 guard（绕过应用层，直接断言迁移后的实际 Schema）。

- 列集合**恰为** 11 列；无 ``status`` / 集群维度列 / 载体判别列；
- CHECK 集合**恰为** ``{ck_containers_carrier_exactly_one}``（``num_nonnulls``）；
- FK 集合精确（两条 ``RESTRICT`` / ``RESTRICT``）；PK 为 ``pk_containers``；
- 两条 partial unique predicate 含 ``deleted_at IS NULL`` 且**不使用** ``lower()``；
- 两条普通载体索引存在；所有列 ``collation_name IS NULL``；无触发器；
- ``name`` / 四个可选字段无长度 / trim / 字符 / 格式未定义约束；
- 既有表结构未被本 migration 改变。
"""

from __future__ import annotations

EXPECTED_CONTAINER_COLUMNS = {
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
}

OPTIONAL_FIELDS = ("image", "cpu", "memory", "owner")


def _container_columns(raw_conn) -> set[str]:
    return {
        row[0]
        for row in raw_conn.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = 'public' AND table_name = 'containers'"
        ).fetchall()
    }


# --------------------------------------------------------------------------- #
# 列集合恰为 11 列；无 status / 集群维度 / 载体判别列
# --------------------------------------------------------------------------- #
def test_column_set_is_exactly_eleven(raw_conn):
    assert _container_columns(raw_conn) == EXPECTED_CONTAINER_COLUMNS


def test_no_status_or_cluster_or_discriminator_columns(raw_conn):
    columns = _container_columns(raw_conn)
    assert "status" not in columns
    assert "state" not in columns
    assert "carrier_type" not in columns
    assert "cluster_id" not in columns
    assert "cluster" not in columns
    assert not any("cluster" in column for column in columns)


# --------------------------------------------------------------------------- #
# CHECK / FK / PK 集合精确
# --------------------------------------------------------------------------- #
def test_check_set_is_exactly_carrier_exactly_one(raw_conn):
    checks = {
        row[0]: row[1]
        for row in raw_conn.execute(
            "SELECT conname, pg_get_constraintdef(oid) FROM pg_constraint "
            "WHERE conrelid = 'containers'::regclass AND contype = 'c'"
        ).fetchall()
    }
    assert set(checks) == {"ck_containers_carrier_exactly_one"}
    assert "num_nonnulls" in checks["ck_containers_carrier_exactly_one"]
    assert "bare_metal_id" in checks["ck_containers_carrier_exactly_one"]
    assert "virtual_machine_id" in checks["ck_containers_carrier_exactly_one"]


def test_foreign_keys_are_exactly_two_restrict(raw_conn):
    fks = raw_conn.execute(
        "SELECT conname, confdeltype, confupdtype FROM pg_constraint "
        "WHERE conrelid = 'containers'::regclass AND contype = 'f'"
    ).fetchall()
    assert {row[0] for row in fks} == {
        "fk_containers_bare_metal",
        "fk_containers_virtual_machine",
    }
    for _, confdel, confupd in fks:
        assert (confdel, confupd) == ("r", "r"), "FK 必须为 RESTRICT / RESTRICT（禁止 CASCADE）"


def test_primary_key_is_pk_containers(raw_conn):
    pk = raw_conn.execute(
        "SELECT conname FROM pg_constraint "
        "WHERE conrelid = 'containers'::regclass AND contype = 'p'"
    ).fetchall()
    assert [row[0] for row in pk] == ["pk_containers"]


# --------------------------------------------------------------------------- #
# 索引存在性与 predicate
# --------------------------------------------------------------------------- #
def test_two_partial_unique_name_indexes(raw_conn):
    for index_name, carrier_column in (
        ("ux_containers_bare_metal_name_active", "bare_metal_id"),
        ("ux_containers_virtual_machine_name_active", "virtual_machine_id"),
    ):
        row = raw_conn.execute(
            "SELECT indexdef FROM pg_indexes WHERE schemaname = 'public' AND indexname = %s",
            (index_name,),
        ).fetchone()
        assert row is not None, f"{index_name} 缺失"
        definition = row[0]
        assert "UNIQUE" in definition
        assert "deleted_at IS NULL" in definition
        assert carrier_column in definition
        assert "name" in definition
        assert "lower(" not in definition.lower()


def test_two_carrier_indexes_exist(raw_conn):
    for index_name, carrier_column in (
        ("ix_containers_bare_metal_id", "bare_metal_id"),
        ("ix_containers_virtual_machine_id", "virtual_machine_id"),
    ):
        row = raw_conn.execute(
            "SELECT indexdef FROM pg_indexes WHERE schemaname = 'public' AND indexname = %s",
            (index_name,),
        ).fetchone()
        assert row is not None, f"{index_name} 缺失"
        assert carrier_column in row[0]


# --------------------------------------------------------------------------- #
# 无 collation / 无触发器
# --------------------------------------------------------------------------- #
def test_no_explicit_collation(raw_conn):
    rows = raw_conn.execute(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_schema = 'public' AND table_name = 'containers' "
        "AND collation_name IS NOT NULL"
    ).fetchall()
    assert rows == [], f"不应声明列级 collation：{rows}"


def test_no_triggers_on_containers(raw_conn):
    triggers = raw_conn.execute(
        "SELECT tgname FROM pg_trigger WHERE tgrelid = 'containers'::regclass AND NOT tgisinternal"
    ).fetchall()
    assert triggers == [], f"不得使用触发器：{triggers}"


# --------------------------------------------------------------------------- #
# 未定义约束「不实现」
# --------------------------------------------------------------------------- #
def test_no_undefined_name_or_optional_checks(raw_conn):
    definitions = raw_conn.execute(
        "SELECT pg_get_constraintdef(oid) FROM pg_constraint "
        "WHERE conrelid = 'containers'::regclass AND contype = 'c'"
    ).fetchall()
    combined = " ".join(row[0] for row in definitions)
    for forbidden in ("name", "image", "cpu", "memory", "owner", "length(", "trim(", "strpos("):
        assert forbidden not in combined, f"不得对字段施加未定义约束：{forbidden}"


def test_name_and_optional_columns_are_text_without_length(raw_conn):
    rows = dict(
        raw_conn.execute(
            "SELECT column_name, character_maximum_length "
            "FROM information_schema.columns "
            "WHERE table_schema = 'public' AND table_name = 'containers'"
        ).fetchall()
    )
    for field in ("name", *OPTIONAL_FIELDS):
        assert rows[field] is None, f"{field} 不得声明长度上限"


def test_not_null_and_nullability(raw_conn):
    rows = dict(
        raw_conn.execute(
            "SELECT column_name, is_nullable FROM information_schema.columns "
            "WHERE table_schema = 'public' AND table_name = 'containers'"
        ).fetchall()
    )
    assert rows["id"] == "NO"
    assert rows["bare_metal_id"] == "YES"
    assert rows["virtual_machine_id"] == "YES"
    assert rows["name"] == "NO"
    assert rows["created_at"] == "NO"
    assert rows["updated_at"] == "NO"
    assert rows["deleted_at"] == "YES"
    for field in OPTIONAL_FIELDS:
        assert rows[field] == "YES", f"{field} 必须允许 NULL（R-CONTAINER-004）"


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
        "ip_addresses": {
            "id",
            "network_interface_id",
            "cluster_id",
            "ip_address",
            "created_at",
            "updated_at",
            "deleted_at",
        },
    }
    for table, columns in expected.items():
        actual = {
            row[0]
            for row in raw_conn.execute(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema = 'public' AND table_name = %s",
                (table,),
            ).fetchall()
        }
        assert actual == columns, f"{table} 列集合被改变"
