"""F006 VirtualMachine 数据库结构 guard（G-1 / G-2 / G-8，V-1 ~ V-8、V-14，绕过应用层）。

直接对 PostgreSQL 执行 SQL，证明 ``virtual_machines`` 的结构来自 migration
而非应用逻辑：

- 列集合**恰为** 12 列；无 ``status`` / ``cluster_id``；
- CHECK 集合为空；PK / FK 集合精确；FK 为 ``RESTRICT`` / ``RESTRICT``；
- partial unique predicate 含 ``deleted_at IS NULL`` 且**不使用** ``lower()``；
- ``ix_virtual_machines_bare_metal_id`` 存在；
- 所有列 ``collation_name IS NULL``；无触发器；
- ``name`` / 六个可选字段无长度 / trim / 字符 / ``/`` 未定义约束；
- 既有表结构未被本 migration 改变。
"""

from __future__ import annotations

EXPECTED_VM_COLUMNS = {
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
}

OPTIONAL_FIELDS = ("cpu", "memory", "disk", "os", "hypervisor", "owner")


def _vm_columns(raw_conn) -> set[str]:
    return {
        row[0]
        for row in raw_conn.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = 'public' AND table_name = 'virtual_machines'"
        ).fetchall()
    }


# --------------------------------------------------------------------------- #
# V-1 / G-1：列集合恰为 12 列；无 status / cluster_id
# --------------------------------------------------------------------------- #
def test_v1_column_set_is_exactly_twelve(raw_conn):
    assert _vm_columns(raw_conn) == EXPECTED_VM_COLUMNS


def test_v1_no_status_or_cluster_columns(raw_conn):
    columns = _vm_columns(raw_conn)
    assert "status" not in columns
    assert "cluster_id" not in columns
    assert not any("cluster" in column for column in columns)


# --------------------------------------------------------------------------- #
# V-2 / G-1：CHECK / FK / PK 集合精确
# --------------------------------------------------------------------------- #
def test_v2_check_set_is_empty(raw_conn):
    checks = {
        row[0]
        for row in raw_conn.execute(
            "SELECT conname FROM pg_constraint "
            "WHERE conrelid = 'virtual_machines'::regclass AND contype = 'c'"
        ).fetchall()
    }
    assert checks == set()


def test_v2_foreign_key_is_exactly_restrict(raw_conn):
    fks = raw_conn.execute(
        "SELECT conname, confdeltype, confupdtype FROM pg_constraint "
        "WHERE conrelid = 'virtual_machines'::regclass AND contype = 'f'"
    ).fetchall()
    assert len(fks) == 1
    name, confdel, confupd = fks[0]
    assert name == "fk_virtual_machines_bare_metal"
    assert (confdel, confupd) == ("r", "r"), "FK 必须为 RESTRICT / RESTRICT（禁止 CASCADE）"


def test_v2_primary_key_is_pk_virtual_machines(raw_conn):
    pk = raw_conn.execute(
        "SELECT conname FROM pg_constraint "
        "WHERE conrelid = 'virtual_machines'::regclass AND contype = 'p'"
    ).fetchall()
    assert [row[0] for row in pk] == ["pk_virtual_machines"]


# --------------------------------------------------------------------------- #
# V-3 / G-2：索引存在性与 predicate
# --------------------------------------------------------------------------- #
def test_v3_partial_unique_name_index(raw_conn):
    row = raw_conn.execute(
        "SELECT indexdef FROM pg_indexes "
        "WHERE schemaname = 'public' AND indexname = 'ux_virtual_machines_name_active'"
    ).fetchone()
    assert row is not None, "ux_virtual_machines_name_active 缺失"
    definition = row[0]
    assert "UNIQUE" in definition
    assert "deleted_at IS NULL" in definition
    # 大小写敏感：不得使用 lower() 表达式索引。
    assert "lower(" not in definition.lower()


def test_v3_bare_metal_id_index_exists(raw_conn):
    row = raw_conn.execute(
        "SELECT indexdef FROM pg_indexes "
        "WHERE schemaname = 'public' AND indexname = 'ix_virtual_machines_bare_metal_id'"
    ).fetchone()
    assert row is not None, "ix_virtual_machines_bare_metal_id 缺失"
    assert "bare_metal_id" in row[0]


# --------------------------------------------------------------------------- #
# V-7 / V-8 / G-8：无 collation / 无触发器 / 全库无 CASCADE
# --------------------------------------------------------------------------- #
def test_v7_no_explicit_collation(raw_conn):
    rows = raw_conn.execute(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_schema = 'public' AND table_name = 'virtual_machines' "
        "AND collation_name IS NOT NULL"
    ).fetchall()
    assert rows == [], f"不应声明列级 collation：{rows}"


def test_v8_no_triggers_on_virtual_machines(raw_conn):
    triggers = raw_conn.execute(
        "SELECT tgname FROM pg_trigger "
        "WHERE tgrelid = 'virtual_machines'::regclass AND NOT tgisinternal"
    ).fetchall()
    assert triggers == [], f"不得使用触发器：{triggers}"


def test_g8_no_cascade_foreign_keys_globally(raw_conn):
    cascades = raw_conn.execute(
        "SELECT conrelid::regclass::text, conname FROM pg_constraint "
        "WHERE contype = 'f' AND confdeltype = 'c'"
    ).fetchall()
    assert cascades == [], f"禁止 ON DELETE CASCADE 外键：{cascades}"


# --------------------------------------------------------------------------- #
# G-7：未定义约束「不实现」（无 name / 六字段长度 / trim / 字符 / "/" CHECK）
# --------------------------------------------------------------------------- #
def test_g7_no_undefined_name_or_optional_checks(raw_conn):
    definitions = raw_conn.execute(
        "SELECT pg_get_constraintdef(oid) FROM pg_constraint "
        "WHERE conrelid = 'virtual_machines'::regclass AND contype = 'c'"
    ).fetchall()
    combined = " ".join(row[0] for row in definitions)
    for forbidden in (
        "name",
        "cpu",
        "memory",
        "disk",
        "hypervisor",
        "owner",
        "length(",
        "trim(",
        "strpos(",
    ):
        assert forbidden not in combined, f"不得对字段施加未定义约束：{forbidden}"


def test_g7_name_and_optional_columns_are_text_without_length(raw_conn):
    rows = dict(
        raw_conn.execute(
            "SELECT column_name, character_maximum_length "
            "FROM information_schema.columns "
            "WHERE table_schema = 'public' AND table_name = 'virtual_machines'"
        ).fetchall()
    )
    for field in ("name", *OPTIONAL_FIELDS):
        assert rows[field] is None, f"{field} 不得声明长度上限"


def test_v5_not_null_and_nullability(raw_conn):
    rows = dict(
        raw_conn.execute(
            "SELECT column_name, is_nullable FROM information_schema.columns "
            "WHERE table_schema = 'public' AND table_name = 'virtual_machines'"
        ).fetchall()
    )
    assert rows["id"] == "NO"
    assert rows["bare_metal_id"] == "NO"
    assert rows["name"] == "NO"
    assert rows["created_at"] == "NO"
    assert rows["updated_at"] == "NO"
    assert rows["deleted_at"] == "YES"
    for field in OPTIONAL_FIELDS:
        assert rows[field] == "YES", f"{field} 必须允许 NULL（R-VM-006）"


# --------------------------------------------------------------------------- #
# V-14：既有表结构未被本 migration 改变
# --------------------------------------------------------------------------- #
def test_v14_existing_tables_structure_unchanged(raw_conn):
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
