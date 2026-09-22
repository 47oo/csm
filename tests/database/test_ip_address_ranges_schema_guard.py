"""F020 / F022 IPAddressRange 数据库结构 guard + 约束证伪（V-1 ~ V-20，绕过应用层）。

直接对迁移后的 PostgreSQL 断言：列集合恰 10（F022 +3）、无状态 / CIDR / 分配类列；
PK / FK / CHECK / EXCLUDE / partial unique / extension / 索引精确；无触发器；无 CASCADE；
无 COLLATE；约束由数据库真实保证（排它约束 23P01、CHECK 23514、partial unique 23505、
FK 23503、软删 predicate 释放重叠与 name）。
"""

from __future__ import annotations

import psycopg
import pytest

EXPECTED_COLUMNS = {
    "id",
    "cluster_id",
    "start_ip",
    "end_ip",
    "created_at",
    "updated_at",
    "deleted_at",
    # F022 元数据字段。
    "name",
    "subnet_mask",
    "vlan",
}

# F022：本 Feature 已确认合法的 name / vlan 从禁令牌移除；其余保持不变（只增不弱）。
FORBIDDEN_TOKENS = (
    "status",
    "state",
    "description",
    "purpose",
    "cidr",
    "prefix_length",
    "network_address",
    "broadcast_address",
    "gateway",
    "dhcp",
    "dns",
    "capacity",
    "utilization",
    "assigned_at",
    "reclaimed_at",
    "assigned_to",
)

#: F022 新增约束 / 索引。
NAME_UNIQUE_INDEX = "ux_ip_address_ranges_cluster_name_active"
VLAN_CHECK = "ck_ip_address_ranges_vlan_range"

OVERLAP_QUERY = """
SELECT a.id AS a_id, b.id AS b_id
FROM ip_address_ranges a
JOIN ip_address_ranges b
  ON a.cluster_id = b.cluster_id AND a.id < b.id
 AND a.deleted_at IS NULL AND b.deleted_at IS NULL
 AND a.start_ip <= b.end_ip AND a.end_ip >= b.start_ip
"""

ORPHAN_QUERY = """
SELECT count(*) FROM ip_address_ranges r
JOIN clusters c ON c.id = r.cluster_id
WHERE r.deleted_at IS NULL AND c.deleted_at IS NOT NULL
"""

# R-4（F022）：同 Cluster 活跃同名重复——期望 0 行（由 partial unique 保证）。
NAME_DUPLICATE_QUERY = """
SELECT a.id AS a_id, b.id AS b_id, a.name
FROM ip_address_ranges a
JOIN ip_address_ranges b
  ON a.cluster_id = b.cluster_id AND a.id < b.id
 AND a.deleted_at IS NULL AND b.deleted_at IS NULL
 AND a.name IS NOT NULL AND b.name IS NOT NULL
 AND a.name = b.name
"""

# R-5（F022）：vlan 越界——期望 0 行（由 CHECK 保证）。
VLAN_OUT_OF_RANGE_QUERY = """
SELECT id FROM ip_address_ranges
WHERE vlan IS NOT NULL AND (vlan < 1 OR vlan > 4094)
"""

F005_DRIFT_QUERY = """
SELECT ip.id FROM ip_addresses ip
JOIN network_interfaces nic ON nic.id = ip.network_interface_id
JOIN bare_metals bm ON bm.id = nic.bare_metal_id
WHERE ip.cluster_id <> bm.cluster_id
"""


def _new_cluster(conn, name: str, *, deleted: bool = False) -> int:
    if deleted:
        return conn.execute(
            "INSERT INTO clusters (name, deleted_at) VALUES (%s, now()) RETURNING id", (name,)
        ).fetchone()[0]
    return conn.execute("INSERT INTO clusters (name) VALUES (%s) RETURNING id", (name,)).fetchone()[
        0
    ]


def _new_range(
    conn,
    cluster_id: int,
    start_ip: int,
    end_ip: int,
    *,
    deleted: bool = False,
    name: str | None = None,
    subnet_mask: str | None = None,
    vlan: int | None = None,
) -> int:
    columns = "cluster_id, start_ip, end_ip, name, subnet_mask, vlan"
    values: list[object] = [cluster_id, start_ip, end_ip, name, subnet_mask, vlan]
    if deleted:
        columns = f"{columns}, deleted_at"
    placeholders = ", ".join(["%s"] * len(values))
    if deleted:
        placeholders = f"{placeholders}, now()"
    return conn.execute(
        f"INSERT INTO ip_address_ranges ({columns}) VALUES ({placeholders}) RETURNING id",
        tuple(values),
    ).fetchone()[0]


def _chain(conn, name: str) -> tuple[int, int]:
    cluster_id = _new_cluster(conn, name)
    bm_id = conn.execute(
        "INSERT INTO bare_metals (cluster_id, hostname) VALUES (%s, 'n1') RETURNING id",
        (cluster_id,),
    ).fetchone()[0]
    nic_id = conn.execute(
        "INSERT INTO network_interfaces (bare_metal_id, name, technology_type, purpose) "
        "VALUES (%s, 'eth0', 'Ethernet', 'Business') RETURNING id",
        (bm_id,),
    ).fetchone()[0]
    return cluster_id, nic_id


# --------------------------------------------------------------------------- #
# 结构断言 V-1 ~ V-10
# --------------------------------------------------------------------------- #
def test_v1_column_set_is_exactly_ten(raw_conn):
    columns = {
        row[0]
        for row in raw_conn.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema='public' AND table_name='ip_address_ranges'"
        ).fetchall()
    }
    assert columns == EXPECTED_COLUMNS
    for token in FORBIDDEN_TOKENS:
        assert token not in columns, token


def test_v2_primary_key(raw_conn):
    rows = raw_conn.execute(
        "SELECT conname FROM pg_constraint "
        "WHERE conrelid='ip_address_ranges'::regclass AND contype='p'"
    ).fetchall()
    assert [row[0] for row in rows] == ["pk_ip_address_ranges"]


def test_v3_foreign_key_is_restrict(raw_conn):
    rows = raw_conn.execute(
        "SELECT conname, confdeltype, confupdtype FROM pg_constraint "
        "WHERE conrelid='ip_address_ranges'::regclass AND contype='f'"
    ).fetchall()
    assert [row[0] for row in rows] == ["fk_ip_address_ranges_cluster"]
    assert rows[0][1:] == ("r", "r")


def test_v4_check_constraints(raw_conn):
    rows = {
        row[0]: row[1]
        for row in raw_conn.execute(
            "SELECT conname, pg_get_constraintdef(oid) FROM pg_constraint "
            "WHERE conrelid='ip_address_ranges'::regclass AND contype='c'"
        ).fetchall()
    }
    assert set(rows) == {"ck_ip_address_ranges_bounds", VLAN_CHECK}
    definition = rows["ck_ip_address_ranges_bounds"]
    assert "start_ip" in definition and "end_ip" in definition
    assert "4294967295" in definition
    vlan_definition = rows[VLAN_CHECK]
    assert "vlan" in vlan_definition and "4094" in vlan_definition
    assert "IS NULL" in vlan_definition


def test_v5_exclusion_constraint(raw_conn):
    row = raw_conn.execute(
        "SELECT pg_get_constraintdef(oid) FROM pg_constraint "
        "WHERE conname='ex_ip_address_ranges_active_no_overlap' AND contype='x'"
    ).fetchone()
    assert row is not None, "排它约束缺失"
    definition = row[0]
    assert "int8range" in definition
    assert "&&" in definition
    assert "cluster_id" in definition
    assert "deleted_at IS NULL" in definition


def test_v6_btree_gist_extension(raw_conn):
    assert raw_conn.execute(
        "SELECT extname FROM pg_extension WHERE extname='btree_gist'"
    ).fetchone() == ("btree_gist",)


def test_v7_partial_unique_index_and_plain_index(raw_conn):
    indexes = {
        row[0]
        for row in raw_conn.execute(
            "SELECT indexname FROM pg_indexes WHERE tablename='ip_address_ranges'"
        ).fetchall()
    }
    assert indexes == {
        "pk_ip_address_ranges",
        "ix_ip_address_ranges_cluster_id",
        NAME_UNIQUE_INDEX,
        "ex_ip_address_ranges_active_no_overlap",
    }, indexes
    definition = raw_conn.execute(
        "SELECT indexdef FROM pg_indexes "
        "WHERE schemaname='public' AND indexname=%s",
        (NAME_UNIQUE_INDEX,),
    ).fetchone()[0]
    assert "UNIQUE" in definition
    assert "(cluster_id, name)" in definition
    assert "deleted_at IS NULL" in definition
    assert "name IS NOT NULL" in definition
    # 大小写敏感：不得 COLLATE / lower()（R-02 / §22）。
    assert "COLLATE" not in definition
    assert "lower(" not in definition


def test_v8_no_cascade_foreign_keys(raw_conn):
    rows = raw_conn.execute(
        "SELECT conname FROM pg_constraint WHERE contype='f' AND confdeltype='c'"
    ).fetchall()
    assert rows == []


def test_v9_no_triggers(raw_conn):
    count = raw_conn.execute(
        "SELECT count(*) FROM information_schema.triggers "
        "WHERE event_object_table='ip_address_ranges'"
    ).fetchone()[0]
    assert count == 0


def test_v10_no_explicit_collation(raw_conn):
    rows = raw_conn.execute(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_schema='public' AND table_name='ip_address_ranges' "
        "AND collation_name IS NOT NULL"
    ).fetchall()
    assert rows == []


# --------------------------------------------------------------------------- #
# 约束证伪 V-11 ~ V-16（绕过应用层）
# --------------------------------------------------------------------------- #
def test_v11_overlapping_active_same_cluster_rejected(raw_conn):
    cluster_id = _new_cluster(raw_conn, "cluster-a")
    _new_range(raw_conn, cluster_id, 10, 20)
    with pytest.raises(psycopg.errors.ExclusionViolation) as excinfo:
        _new_range(raw_conn, cluster_id, 20, 30)  # 共享端点
    assert excinfo.value.sqlstate == "23P01"


def test_v12_cross_cluster_identical_range_succeeds(raw_conn):
    cluster_a = _new_cluster(raw_conn, "cluster-a")
    cluster_b = _new_cluster(raw_conn, "cluster-b")
    _new_range(raw_conn, cluster_a, 10, 20)
    _new_range(raw_conn, cluster_b, 10, 20)
    assert raw_conn.execute("SELECT count(*) FROM ip_address_ranges").fetchone()[0] == 2


@pytest.mark.parametrize(
    ("start_ip", "end_ip"),
    [(20, 10), (-1, 10), (0, 4294967296)],
)
def test_v13_bounds_violations_are_23514(raw_conn, start_ip, end_ip):
    cluster_id = _new_cluster(raw_conn, f"cluster-{start_ip}-{end_ip}")
    with pytest.raises(psycopg.errors.CheckViolation) as excinfo:
        _new_range(raw_conn, cluster_id, start_ip, end_ip)
    assert excinfo.value.sqlstate == "23514"


def test_v14_soft_deleted_range_releases_overlap(raw_conn):
    cluster_id = _new_cluster(raw_conn, "cluster-a")
    deleted_id = _new_range(raw_conn, cluster_id, 10, 20, deleted=True)
    active_id = _new_range(raw_conn, cluster_id, 15, 25)
    assert active_id != deleted_id
    assert (
        raw_conn.execute(
            "SELECT count(*) FROM ip_address_ranges WHERE deleted_at IS NULL"
        ).fetchone()[0]
        == 1
    )


def test_v15_fk_and_restrict_on_physical_delete(raw_conn):
    with pytest.raises(psycopg.errors.ForeignKeyViolation) as excinfo:
        _new_range(raw_conn, 999999999, 1, 2)
    assert excinfo.value.sqlstate == "23503"

    cluster_id = _new_cluster(raw_conn, "cluster-a")
    _new_range(raw_conn, cluster_id, 1, 2, deleted=True)
    with pytest.raises(psycopg.errors.ForeignKeyViolation) as excinfo:
        raw_conn.execute("DELETE FROM clusters WHERE id=%s", (cluster_id,))
    assert excinfo.value.sqlstate == "23503", "RESTRICT 非 CASCADE，即使范围段已软删"


def test_v16_soft_deleted_row_remains_and_no_db_trigger(raw_conn):
    cluster_id = _new_cluster(raw_conn, "cluster-a")
    range_id = _new_range(raw_conn, cluster_id, 10, 20)
    before_updated_at = raw_conn.execute(
        "SELECT updated_at FROM ip_address_ranges WHERE id=%s", (range_id,)
    ).fetchone()[0]

    raw_conn.execute("UPDATE ip_address_ranges SET deleted_at=now() WHERE id=%s", (range_id,))
    row = raw_conn.execute(
        "SELECT deleted_at, updated_at FROM ip_address_ranges WHERE id=%s", (range_id,)
    ).fetchone()
    assert row[0] is not None
    # DB 无触发器：裸 SQL 不改 updated_at（updated_at 由应用层 onupdate 维护）。
    assert row[1] == before_updated_at
    assert raw_conn.execute("SELECT count(*) FROM ip_address_ranges").fetchone()[0] == 1
    # 软删释放重叠：可重建重叠的活跃范围。
    _new_range(raw_conn, cluster_id, 15, 25)


# --------------------------------------------------------------------------- #
# 不变式回归 V-17 ~ V-19（恒 0）
# --------------------------------------------------------------------------- #
def test_v17_no_active_overlap_drift(raw_conn):
    cluster_id = _new_cluster(raw_conn, "cluster-a")
    _new_range(raw_conn, cluster_id, 10, 20)
    _new_range(raw_conn, cluster_id, 21, 30)
    assert raw_conn.execute(OVERLAP_QUERY).fetchall() == []


def test_v18_no_active_range_on_deleted_cluster(raw_conn):
    deleted = _new_cluster(raw_conn, "cluster-deleted", deleted=True)
    _new_range(raw_conn, deleted, 1, 2, deleted=True)
    assert raw_conn.execute(ORPHAN_QUERY).fetchone()[0] == 0


def test_v19_f005_drift_query_still_zero(raw_conn):
    cluster_id, nic_id = _chain(raw_conn, "cluster-a")
    raw_conn.execute(
        "INSERT INTO ip_addresses (network_interface_id, cluster_id, ip_address) "
        "VALUES (%s, %s, '10.0.0.1')",
        (nic_id, cluster_id),
    )
    assert raw_conn.execute(F005_DRIFT_QUERY).fetchall() == []


# --------------------------------------------------------------------------- #
# F022 约束证伪 V-F022-1 ~ V-F022-6（绕过应用层）
# --------------------------------------------------------------------------- #
def test_v_f022_1_active_duplicate_name_is_23505(raw_conn):
    cluster_id = _new_cluster(raw_conn, "cluster-a")
    _new_range(raw_conn, cluster_id, 10, 20, name="web")
    with pytest.raises(psycopg.errors.UniqueViolation) as excinfo:
        _new_range(raw_conn, cluster_id, 21, 30, name="web")
    assert excinfo.value.sqlstate == "23505"


def test_v_f022_2_name_case_sensitive(raw_conn):
    cluster_id = _new_cluster(raw_conn, "cluster-a")
    _new_range(raw_conn, cluster_id, 10, 20, name="web")
    _new_range(raw_conn, cluster_id, 21, 30, name="Web")
    assert raw_conn.execute("SELECT count(*) FROM ip_address_ranges").fetchone()[0] == 2


def test_v_f022_3_soft_delete_and_null_name_release(raw_conn):
    cluster_id = _new_cluster(raw_conn, "cluster-a")
    _new_range(raw_conn, cluster_id, 10, 20, name="web", deleted=True)
    _new_range(raw_conn, cluster_id, 21, 30, name="web")
    # name IS NULL 的行不参与唯一性：两条未命名活跃行共存。
    _new_range(raw_conn, cluster_id, 31, 40)
    _new_range(raw_conn, cluster_id, 41, 50)
    assert raw_conn.execute("SELECT count(*) FROM ip_address_ranges").fetchone()[0] == 4


def test_v_f022_4_cross_cluster_same_name_succeeds(raw_conn):
    cluster_a = _new_cluster(raw_conn, "cluster-a")
    cluster_b = _new_cluster(raw_conn, "cluster-b")
    _new_range(raw_conn, cluster_a, 10, 20, name="web")
    _new_range(raw_conn, cluster_b, 10, 20, name="web")
    assert raw_conn.execute("SELECT count(*) FROM ip_address_ranges").fetchone()[0] == 2


@pytest.mark.parametrize("vlan", [0, 4095, 5000, -1])
def test_v_f022_5_vlan_out_of_range_is_23514(raw_conn, vlan):
    cluster_id = _new_cluster(raw_conn, f"cluster-vlan-{vlan}")
    with pytest.raises(psycopg.errors.CheckViolation) as excinfo:
        _new_range(raw_conn, cluster_id, 10, 20, vlan=vlan)
    assert excinfo.value.sqlstate == "23514"


@pytest.mark.parametrize("vlan", [1, 4094, None])
def test_v_f022_6_vlan_boundaries_and_null_succeed(raw_conn, vlan):
    cluster_id = _new_cluster(raw_conn, f"cluster-vlan-ok-{vlan}")
    _new_range(raw_conn, cluster_id, 10, 20, vlan=vlan)
    assert raw_conn.execute("SELECT count(*) FROM ip_address_ranges").fetchone()[0] == 1


def test_v_f022_7_no_backfill_metadata_null(raw_conn):
    cluster_id = _new_cluster(raw_conn, "cluster-a")
    _new_range(raw_conn, cluster_id, 10, 20)
    row = raw_conn.execute(
        "SELECT name, subnet_mask, vlan FROM ip_address_ranges"
    ).fetchone()
    assert row == (None, None, None)


def test_v_f022_8_no_active_duplicate_name_drift(raw_conn):
    cluster_id = _new_cluster(raw_conn, "cluster-a")
    _new_range(raw_conn, cluster_id, 10, 20, name="a")
    _new_range(raw_conn, cluster_id, 21, 30, name="b")
    _new_range(raw_conn, cluster_id, 31, 40, name="a", deleted=True)
    assert raw_conn.execute(NAME_DUPLICATE_QUERY).fetchall() == []
    assert raw_conn.execute(VLAN_OUT_OF_RANGE_QUERY).fetchall() == []
