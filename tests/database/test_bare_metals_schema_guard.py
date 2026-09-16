"""F002 数据库结构 guard（G-2 / G-5 / V-1 ~ V-5，绕过应用层）。

这些断言直接对 PostgreSQL 执行 SQL，证明 ``bare_metals`` 的结构来自 migration
而非应用逻辑：

- 列集合**恰为** 14 列（含 R-BM-007 七列）；
- CHECK 集合**恰为** ``{ck_bare_metals_status}``（未定义约束「不实现」）；
- FK / PK 集合精确；FK 为 ``RESTRICT`` / ``RESTRICT``；
- partial unique predicate 含 ``deleted_at IS NULL``；``ix_bare_metals_cluster_id`` 存在；
- 所有列 ``collation_name IS NULL``；无触发器；``serial_number`` 不参与唯一性。
"""

from __future__ import annotations

EXPECTED_COLUMNS = {
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
}


def _columns(raw_conn) -> set[str]:
    return {
        row[0]
        for row in raw_conn.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = 'public' AND table_name = 'bare_metals'"
        ).fetchall()
    }


# --------------------------------------------------------------------------- #
# V-1 / G-2：列集合恰为 14 列
# --------------------------------------------------------------------------- #
def test_v1_column_set_is_exactly_14(raw_conn):
    assert _columns(raw_conn) == EXPECTED_COLUMNS


# --------------------------------------------------------------------------- #
# V-2 / G-2：CHECK / FK / PK 集合精确
# --------------------------------------------------------------------------- #
def test_v2_check_set_is_exactly_status(raw_conn):
    checks = {
        row[0]
        for row in raw_conn.execute(
            "SELECT conname FROM pg_constraint "
            "WHERE conrelid = 'bare_metals'::regclass AND contype = 'c'"
        ).fetchall()
    }
    assert checks == {"ck_bare_metals_status"}


def test_v2_foreign_keys_are_exactly_restrict(raw_conn):
    fks = raw_conn.execute(
        "SELECT conname, confdeltype, confupdtype FROM pg_constraint "
        "WHERE conrelid = 'bare_metals'::regclass AND contype = 'f'"
    ).fetchall()
    assert len(fks) == 1
    name, confdel, confupd = fks[0]
    assert name == "fk_bare_metals_cluster"
    assert (confdel, confupd) == ("r", "r"), "FK 必须为 RESTRICT / RESTRICT（禁止 CASCADE）"


def test_v2_primary_key_is_pk_bare_metals(raw_conn):
    pk = raw_conn.execute(
        "SELECT conname FROM pg_constraint "
        "WHERE conrelid = 'bare_metals'::regclass AND contype = 'p'"
    ).fetchall()
    assert [row[0] for row in pk] == ["pk_bare_metals"]


# --------------------------------------------------------------------------- #
# V-3：索引存在性与 predicate
# --------------------------------------------------------------------------- #
def test_v3_partial_unique_hostname_index(raw_conn):
    row = raw_conn.execute(
        "SELECT indexdef FROM pg_indexes "
        "WHERE schemaname = 'public' AND indexname = 'ux_bare_metals_cluster_hostname_active'"
    ).fetchone()
    assert row is not None, "ux_bare_metals_cluster_hostname_active 缺失"
    definition = row[0]
    assert "UNIQUE" in definition
    assert "deleted_at IS NULL" in definition


def test_v3_cluster_id_index_exists(raw_conn):
    row = raw_conn.execute(
        "SELECT indexdef FROM pg_indexes "
        "WHERE schemaname = 'public' AND indexname = 'ix_bare_metals_cluster_id'"
    ).fetchone()
    assert row is not None, "ix_bare_metals_cluster_id 缺失"
    assert "cluster_id" in row[0]


# --------------------------------------------------------------------------- #
# V-4：无 collation / 无触发器 / 全库无 CASCADE
# --------------------------------------------------------------------------- #
def test_v4_no_explicit_collation_on_bare_metal_columns(raw_conn):
    rows = raw_conn.execute(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_schema = 'public' AND table_name = 'bare_metals' "
        "AND collation_name IS NOT NULL"
    ).fetchall()
    assert rows == [], f"不应声明列级 collation：{rows}"


def test_v4_no_triggers_on_bare_metals(raw_conn):
    triggers = raw_conn.execute(
        "SELECT tgname FROM pg_trigger WHERE tgrelid = 'bare_metals'::regclass AND NOT tgisinternal"
    ).fetchall()
    assert triggers == [], f"不得使用触发器：{triggers}"


def test_v4_no_cascade_foreign_keys_globally(raw_conn):
    cascades = raw_conn.execute(
        "SELECT conrelid::regclass::text, conname FROM pg_constraint "
        "WHERE contype = 'f' AND confdeltype = 'c'"
    ).fetchall()
    assert cascades == [], f"禁止 ON DELETE CASCADE 外键：{cascades}"


# --------------------------------------------------------------------------- #
# V-5 / G-5：未定义约束「不实现」 + serial_number 不唯一
# --------------------------------------------------------------------------- #
def test_v5_no_undefined_hostname_check(raw_conn):
    definitions = raw_conn.execute(
        "SELECT pg_get_constraintdef(oid) FROM pg_constraint "
        "WHERE conrelid = 'bare_metals'::regclass AND contype = 'c'"
    ).fetchall()
    combined = " ".join(row[0] for row in definitions)
    for forbidden in ("hostname", "serial_number", "length(", "trim(", "strpos("):
        assert forbidden not in combined, f"不得对字段施加未定义约束：{forbidden}"


def test_v5_serial_number_is_not_unique(raw_conn):
    # 排除主键索引（pk_bare_metals 亦为 UNIQUE）：业务唯一索引恰为 hostname partial。
    unique_indexes = raw_conn.execute(
        "SELECT indexdef FROM pg_indexes "
        "WHERE schemaname = 'public' AND tablename = 'bare_metals' "
        "AND indexdef LIKE '%UNIQUE%' AND indexname <> 'pk_bare_metals'"
    ).fetchall()
    assert len(unique_indexes) == 1, "bare_metals 上应恰好有一个业务唯一索引（hostname partial）"
    assert "serial_number" not in unique_indexes[0][0]


def test_v5_status_default_is_idle(raw_conn):
    default = raw_conn.execute(
        "SELECT column_default FROM information_schema.columns "
        "WHERE table_schema = 'public' AND table_name = 'bare_metals' AND column_name = 'status'"
    ).fetchone()[0]
    assert default is not None and "IDLE" in default


def test_v5_status_and_hostname_and_cluster_id_are_not_null(raw_conn):
    rows = dict(
        raw_conn.execute(
            "SELECT column_name, is_nullable FROM information_schema.columns "
            "WHERE table_schema = 'public' AND table_name = 'bare_metals'"
        ).fetchall()
    )
    assert rows["id"] == "NO"
    assert rows["cluster_id"] == "NO"
    assert rows["hostname"] == "NO"
    assert rows["status"] == "NO"
    for hardware in ("vendor", "model", "serial_number", "cpu", "memory", "gpu", "storage"):
        assert rows[hardware] == "YES", f"{hardware} 必须允许 NULL（R-BM-007）"
