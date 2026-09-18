"""F004 NetworkInterface 数据库结构 guard（G-1 ~ G-4、G-11、V-1 ~ V-9，绕过应用层）。

直接对 PostgreSQL 执行 SQL，证明 ``network_interfaces`` 的结构来自 migration
而非应用逻辑：

- 列集合**恰为** 8 列；无 ``status`` / IP / MAC / 速率 / MTU / 载体列；
- PK / FK 集合精确；FK 为 ``RESTRICT`` / ``RESTRICT``；
- CHECK 集合恰为两个，取值逐字匹配 R-NIC-001 / R-NIC-002；
- ``ix_network_interfaces_bare_metal_id`` 存在；
- **唯一索引集合为空**（NQ-2 未确认，不得表达 NIC 名称唯一性）；
- 所有列 ``collation_name IS NULL``；无触发器；全库无 CASCADE；
- ``name`` 无长度 / trim / 字符 / ``/`` 未定义约束；
- 既有表结构未被本 migration 改变。
"""

from __future__ import annotations

EXPECTED_NIC_COLUMNS = {
    "id",
    "bare_metal_id",
    "name",
    "technology_type",
    "purpose",
    "created_at",
    "updated_at",
    "deleted_at",
}

TECHNOLOGY_TYPE_VALUES = {"Ethernet", "InfiniBand", "RoCE", "Other"}
PURPOSE_VALUES = {"BMC", "Management", "Business", "Compute", "Storage", "DataTransfer", "Other"}


def _nic_columns(raw_conn) -> set[str]:
    return {
        row[0]
        for row in raw_conn.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = 'public' AND table_name = 'network_interfaces'"
        ).fetchall()
    }


# --------------------------------------------------------------------------- #
# V-1 / G-1：列集合恰为 8 列；无 status / IP / MAC / 速率 / MTU / 载体列
# --------------------------------------------------------------------------- #
def test_v1_column_set_is_exactly_eight(raw_conn):
    assert _nic_columns(raw_conn) == EXPECTED_NIC_COLUMNS


def test_v1_no_status_ip_or_hardware_columns(raw_conn):
    columns = _nic_columns(raw_conn)
    assert "status" not in columns
    assert "cluster_id" not in columns
    for forbidden in (
        "ip",
        "ip_address",
        "ipv4",
        "ipv6",
        "prefix_len",
        "mac",
        "mac_address",
        "speed",
        "rate",
        "mtu",
        "port",
        "module",
        "transceiver",
        "discovered",
        "external_id",
        "vm_id",
        "virtual_machine_id",
        "container_id",
        "service_id",
        "carrier_type",
        "owner_type",
    ):
        assert forbidden not in columns, f"不得出现未确认列：{forbidden}"


# --------------------------------------------------------------------------- #
# V-2 / G-1：CHECK / FK / PK 集合精确
# --------------------------------------------------------------------------- #
def _check_definitions(raw_conn) -> dict[str, str]:
    rows = raw_conn.execute(
        "SELECT conname, pg_get_constraintdef(oid) FROM pg_constraint "
        "WHERE conrelid = 'network_interfaces'::regclass AND contype = 'c'"
    ).fetchall()
    return {name: definition for name, definition in rows}


def test_v2_check_set_is_exactly_two(raw_conn):
    checks = _check_definitions(raw_conn)
    assert set(checks) == {
        "ck_network_interfaces_technology_type",
        "ck_network_interfaces_purpose",
    }


def test_v2_check_values_match_closed_enums(raw_conn):
    checks = _check_definitions(raw_conn)
    tech = checks["ck_network_interfaces_technology_type"]
    purpose = checks["ck_network_interfaces_purpose"]
    for value in TECHNOLOGY_TYPE_VALUES:
        assert f"'{value}'" in tech, f"technology_type CHECK 缺 {value}"
    for value in PURPOSE_VALUES:
        assert f"'{value}'" in purpose, f"purpose CHECK 缺 {value}"


def test_v2_foreign_key_is_exactly_restrict(raw_conn):
    fks = raw_conn.execute(
        "SELECT conname, confdeltype, confupdtype FROM pg_constraint "
        "WHERE conrelid = 'network_interfaces'::regclass AND contype = 'f'"
    ).fetchall()
    assert len(fks) == 1
    name, confdel, confupd = fks[0]
    assert name == "fk_network_interfaces_bare_metal"
    assert (confdel, confupd) == ("r", "r"), "FK 必须为 RESTRICT / RESTRICT（禁止 CASCADE）"


def test_v2_primary_key_is_pk_network_interfaces(raw_conn):
    pk = raw_conn.execute(
        "SELECT conname FROM pg_constraint "
        "WHERE conrelid = 'network_interfaces'::regclass AND contype = 'p'"
    ).fetchall()
    assert [row[0] for row in pk] == ["pk_network_interfaces"]


# --------------------------------------------------------------------------- #
# V-3 / V-6 / V-7 / G-3 / G-4：索引 / 唯一性 / FK 索引
# --------------------------------------------------------------------------- #
def test_v6_bare_metal_id_index_exists(raw_conn):
    row = raw_conn.execute(
        "SELECT indexdef FROM pg_indexes "
        "WHERE schemaname = 'public' AND indexname = 'ix_network_interfaces_bare_metal_id'"
    ).fetchone()
    assert row is not None, "ix_network_interfaces_bare_metal_id 缺失"
    assert "bare_metal_id" in row[0]


def test_v7_unique_index_set_is_empty(raw_conn):
    # 主键索引天然唯一，不在此列；断言**没有额外**唯一索引（NQ-2）。
    unique = raw_conn.execute(
        "SELECT c.relname FROM pg_index i JOIN pg_class c ON c.oid = i.indexrelid "
        "WHERE i.indrelid = 'network_interfaces'::regclass "
        "AND i.indisunique AND NOT i.indisprimary"
    ).fetchall()
    names = [row[0] for row in unique]
    assert names == [], f"network_interfaces 不得有任何额外唯一索引（NQ-2）：{names}"
    assert not any(name.startswith("ux_") for name in names)


# --------------------------------------------------------------------------- #
# V-8 / V-9 / G-11：无 collation / 无触发器 / 全库无 CASCADE
# --------------------------------------------------------------------------- #
def test_v8_no_explicit_collation(raw_conn):
    rows = raw_conn.execute(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_schema = 'public' AND table_name = 'network_interfaces' "
        "AND collation_name IS NOT NULL"
    ).fetchall()
    assert rows == [], f"不应声明列级 collation：{rows}"


def test_v9_no_triggers_on_network_interfaces(raw_conn):
    triggers = raw_conn.execute(
        "SELECT tgname FROM pg_trigger "
        "WHERE tgrelid = 'network_interfaces'::regclass AND NOT tgisinternal"
    ).fetchall()
    assert triggers == [], f"不得使用触发器：{triggers}"


def test_g11_no_cascade_foreign_keys_globally(raw_conn):
    cascades = raw_conn.execute(
        "SELECT conrelid::regclass::text, conname FROM pg_constraint "
        "WHERE contype = 'f' AND confdeltype = 'c'"
    ).fetchall()
    assert cascades == [], f"禁止 ON DELETE CASCADE 外键：{cascades}"


# --------------------------------------------------------------------------- #
# G-10 / 未定义约束「不实现」：name 无长度 / trim / 字符 / "/" CHECK
# --------------------------------------------------------------------------- #
def test_g10_no_undefined_name_checks(raw_conn):
    combined = " ".join(_check_definitions(raw_conn).values())
    for forbidden in ("name", "length(", "trim(", "strpos(", "like", "collate"):
        assert forbidden not in combined.lower(), f"不得对字段施加未定义约束：{forbidden}"


def test_g10_name_column_is_text_without_length(raw_conn):
    rows = dict(
        raw_conn.execute(
            "SELECT column_name, character_maximum_length "
            "FROM information_schema.columns "
            "WHERE table_schema = 'public' AND table_name = 'network_interfaces'"
        ).fetchall()
    )
    for field in ("name", "technology_type", "purpose"):
        assert rows[field] is None, f"{field} 不得声明长度上限"


# --------------------------------------------------------------------------- #
# V-5：NOT NULL / NULL 语义
# --------------------------------------------------------------------------- #
def test_v5_not_null_and_nullability(raw_conn):
    rows = dict(
        raw_conn.execute(
            "SELECT column_name, is_nullable FROM information_schema.columns "
            "WHERE table_schema = 'public' AND table_name = 'network_interfaces'"
        ).fetchall()
    )
    for field in ("id", "bare_metal_id", "name", "technology_type", "purpose"):
        assert rows[field] == "NO", f"{field} 必须 NOT NULL"
    for field in ("created_at", "updated_at"):
        assert rows[field] == "NO"
    assert rows["deleted_at"] == "YES"


# --------------------------------------------------------------------------- #
# V-14 / V-15：既有表结构未被本 migration 改变
# --------------------------------------------------------------------------- #
def test_v14_existing_tables_structure_unchanged(raw_conn):
    expected = {
        "clusters": {"id", "name", "created_at", "updated_at", "deleted_at"},
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
