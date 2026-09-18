"""F005 IPAddress 数据库结构 guard（V-1 ~ V-10、V-18，绕过应用层）。

直接对 PostgreSQL 执行 SQL，证明 ``ip_addresses`` 的结构来自 migration ``0006``
而非应用逻辑：

- 列集合**恰为** 7 列；无 ``status`` / VRF / IP 池 / DHCP / DNS / 载体 / 备注列；
- **CHECK 约束集合为空**；``ip_address`` 为 ``TEXT`` 且无长度；
- PK 恰为 ``pk_ip_addresses``；FK 恰为 2 条，均 ``RESTRICT`` / ``RESTRICT``；
- 唯一索引集合恰为 ``{ux_ip_addresses_cluster_ip_active}``，列序 ``(cluster_id,
  ip_address)``、predicate ``WHERE (deleted_at IS NULL)``，且**不含 ``COLLATE`` /
  ``lower(``**；另两个普通索引存在；
- 所有列 ``collation_name IS NULL``；无触发器；既有表结构未被改变。
"""

from __future__ import annotations

EXPECTED_IP_COLUMNS = {
    "id",
    "network_interface_id",
    "cluster_id",
    "ip_address",
    "created_at",
    "updated_at",
    "deleted_at",
}

FORBIDDEN_COLUMNS = (
    "status",
    "vrf",
    "vrf_id",
    "tenant",
    "namespace",
    "netns",
    "vni",
    "pool",
    "pool_id",
    "subnet",
    "segment",
    "gateway",
    "vlan",
    "dhcp",
    "dns",
    "discovered",
    "external_id",
    "last_seen",
    "carrier_type",
    "owner_type",
    "parent_type",
    "bare_metal_id",
    "virtual_machine_id",
    "container_id",
    "service_id",
    "purpose",
    "note",
    "remark",
    "owner",
    "assigned_at",
    "reclaimed_at",
)


def _columns(raw_conn) -> set[str]:
    return {
        row[0]
        for row in raw_conn.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = 'public' AND table_name = 'ip_addresses'"
        ).fetchall()
    }


def _check_definitions(raw_conn) -> dict[str, str]:
    rows = raw_conn.execute(
        "SELECT conname, pg_get_constraintdef(oid) FROM pg_constraint "
        "WHERE conrelid = 'ip_addresses'::regclass AND contype = 'c'"
    ).fetchall()
    return {name: definition for name, definition in rows}


# --------------------------------------------------------------------------- #
# V-1：列集合恰为 7 列；无 status / VRF / 池 / DHCP / DNS / 载体 / 备注列
# --------------------------------------------------------------------------- #
def test_v1_column_set_is_exactly_seven(raw_conn):
    assert _columns(raw_conn) == EXPECTED_IP_COLUMNS


def test_v1_no_forbidden_columns(raw_conn):
    columns = _columns(raw_conn)
    for token in FORBIDDEN_COLUMNS:
        assert token not in columns, f"不得出现未确认列：{token}"


# --------------------------------------------------------------------------- #
# V-2：CHECK 约束集合为空
# --------------------------------------------------------------------------- #
def test_v2_check_set_is_empty(raw_conn):
    checks = _check_definitions(raw_conn)
    assert checks == {}, f"ip_addresses 不得有任何 CHECK 约束：{checks}"


# --------------------------------------------------------------------------- #
# V-3：ip_address 为 TEXT 且无长度
# --------------------------------------------------------------------------- #
def test_v3_ip_address_is_text_without_length(raw_conn):
    row = raw_conn.execute(
        "SELECT data_type, character_maximum_length FROM information_schema.columns "
        "WHERE table_schema='public' AND table_name='ip_addresses' AND column_name='ip_address'"
    ).fetchone()
    assert row[0] == "text"
    assert row[1] is None


# --------------------------------------------------------------------------- #
# V-4 / V-5：PK / FK 精确
# --------------------------------------------------------------------------- #
def test_v4_primary_key(raw_conn):
    pk = raw_conn.execute(
        "SELECT conname FROM pg_constraint "
        "WHERE conrelid = 'ip_addresses'::regclass AND contype = 'p'"
    ).fetchall()
    assert [row[0] for row in pk] == ["pk_ip_addresses"]


def test_v5_foreign_keys_exactly_two_restrict(raw_conn):
    fks = raw_conn.execute(
        "SELECT conname, confdeltype, confupdtype FROM pg_constraint "
        "WHERE conrelid = 'ip_addresses'::regclass AND contype = 'f'"
    ).fetchall()
    assert {row[0] for row in fks} == {
        "fk_ip_addresses_network_interface",
        "fk_ip_addresses_cluster",
    }
    for name, confdel, confupd in fks:
        assert (confdel, confupd) == ("r", "r"), f"{name} 必须 RESTRICT / RESTRICT"


# --------------------------------------------------------------------------- #
# V-7 / V-8：唯一索引精确；普通索引存在
# --------------------------------------------------------------------------- #
def test_v7_unique_index_set_is_exactly_one(raw_conn):
    unique = raw_conn.execute(
        "SELECT c.relname FROM pg_index i JOIN pg_class c ON c.oid = i.indexrelid "
        "WHERE i.indrelid = 'ip_addresses'::regclass AND i.indisunique AND NOT i.indisprimary"
    ).fetchall()
    assert [row[0] for row in unique] == ["ux_ip_addresses_cluster_ip_active"]


def test_v7_unique_index_definition(raw_conn):
    indexdef = raw_conn.execute(
        "SELECT indexdef FROM pg_indexes "
        "WHERE schemaname='public' AND indexname='ux_ip_addresses_cluster_ip_active'"
    ).fetchone()[0]
    assert "UNIQUE" in indexdef
    assert "cluster_id" in indexdef
    assert "ip_address" in indexdef
    assert "deleted_at IS NULL" in indexdef
    assert "(cluster_id, ip_address)" in indexdef
    assert "lower(" not in indexdef.lower()
    assert "collate" not in indexdef.lower()


def test_v8_other_indexes_exist(raw_conn):
    names = {
        row[0]
        for row in raw_conn.execute(
            "SELECT indexname FROM pg_indexes "
            "WHERE schemaname='public' AND tablename='ip_addresses'"
        ).fetchall()
    }
    assert "ix_ip_addresses_cluster_id" in names
    assert "ix_ip_addresses_network_interface_id" in names


# --------------------------------------------------------------------------- #
# V-9 / V-10：无 collation / 无触发器 / 无 CASCADE
# --------------------------------------------------------------------------- #
def test_v9_no_explicit_collation(raw_conn):
    rows = raw_conn.execute(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_schema='public' AND table_name='ip_addresses' "
        "AND collation_name IS NOT NULL"
    ).fetchall()
    assert rows == []


def test_v10_no_triggers(raw_conn):
    triggers = raw_conn.execute(
        "SELECT tgname FROM pg_trigger "
        "WHERE tgrelid = 'ip_addresses'::regclass AND NOT tgisinternal"
    ).fetchall()
    assert triggers == [], f"不得使用触发器：{triggers}"


def test_v10_no_cascade_foreign_keys_globally(raw_conn):
    cascades = raw_conn.execute(
        "SELECT conrelid::regclass::text, conname FROM pg_constraint "
        "WHERE contype='f' AND confdeltype='c'"
    ).fetchall()
    assert cascades == [], f"禁止 ON DELETE CASCADE 外键：{cascades}"


# --------------------------------------------------------------------------- #
# V-18：既有表结构未被本 migration 改变
# --------------------------------------------------------------------------- #
def test_v18_existing_tables_structure_unchanged(raw_conn):
    expected = {
        "network_interfaces": {
            "id",
            "bare_metal_id",
            "name",
            "technology_type",
            "purpose",
            "created_at",
            "updated_at",
            "deleted_at",
        },
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
        "clusters": {"id", "name", "created_at", "updated_at", "deleted_at"},
    }
    for table, columns in expected.items():
        actual = {
            row[0]
            for row in raw_conn.execute(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema='public' AND table_name=%s",
                (table,),
            ).fetchall()
        }
        assert actual == columns, f"{table} 列集合被改变"
