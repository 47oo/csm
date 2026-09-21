"""F020 IPAddressRange 数据库结构 guard + 约束证伪（V-1 ~ V-20，绕过应用层）。

直接对迁移后的 PostgreSQL 断言：列集合恰 7、无状态 / CIDR / 分配类列；PK / FK /
CHECK / EXCLUDE / extension / 索引精确；无触发器；无 CASCADE；约束由数据库真实保证
（排它约束 23P01、CHECK 23514、FK 23503、软删 predicate 释放重叠）。
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
}

FORBIDDEN_TOKENS = (
    "status",
    "state",
    "name",
    "description",
    "purpose",
    "cidr",
    "prefix_length",
    "network_address",
    "broadcast_address",
    "gateway",
    "vlan",
    "dhcp",
    "dns",
    "capacity",
    "utilization",
    "assigned_at",
    "reclaimed_at",
    "assigned_to",
)

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


def _new_range(conn, cluster_id: int, start_ip: int, end_ip: int, *, deleted: bool = False) -> int:
    if deleted:
        return conn.execute(
            "INSERT INTO ip_address_ranges (cluster_id, start_ip, end_ip, deleted_at) "
            "VALUES (%s, %s, %s, now()) RETURNING id",
            (cluster_id, start_ip, end_ip),
        ).fetchone()[0]
    return conn.execute(
        "INSERT INTO ip_address_ranges (cluster_id, start_ip, end_ip) "
        "VALUES (%s, %s, %s) RETURNING id",
        (cluster_id, start_ip, end_ip),
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
def test_v1_column_set_is_exactly_seven(raw_conn):
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


def test_v4_check_constraint(raw_conn):
    rows = {
        row[0]: row[1]
        for row in raw_conn.execute(
            "SELECT conname, pg_get_constraintdef(oid) FROM pg_constraint "
            "WHERE conrelid='ip_address_ranges'::regclass AND contype='c'"
        ).fetchall()
    }
    assert set(rows) == {"ck_ip_address_ranges_bounds"}
    definition = rows["ck_ip_address_ranges_bounds"]
    assert "start_ip" in definition and "end_ip" in definition
    assert "4294967295" in definition


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


def test_v7_plain_index_exists_and_no_unique_index(raw_conn):
    indexes = {
        row[0]
        for row in raw_conn.execute(
            "SELECT indexname FROM pg_indexes WHERE tablename='ip_address_ranges'"
        ).fetchall()
    }
    assert "ix_ip_address_ranges_cluster_id" in indexes
    assert not any(name.startswith("ux_") for name in indexes)


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
