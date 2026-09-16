"""F002 数据库约束断言（V-6 ~ V-11 / T-11，绕过应用层直连 PostgreSQL）。

证明唯一性 / FK / CHECK / NOT NULL / NULL 语义由数据库保证，而非应用逻辑：

- V-6：同 Cluster 大小写敏感唯一；跨 Cluster 可重；
- V-7：软删释放唯一性；
- V-8：``status`` 默认 ``IDLE``、``UNKNOWN`` 可写、``NULL`` → 23502、非法值 → 23514；
- V-9：无效 ``cluster_id`` → 23503；
- V-10：父 Cluster 有子行（含已软删）时物理删除 → 23503；
- V-11：七列缺省为 NULL；中文往返；空串 / 首尾空白原样存取。
"""

from __future__ import annotations

import psycopg
import pytest

CHINESE_HOSTNAME = "计算节点-甲"


def _new_cluster(raw_conn, name: str) -> int:
    return raw_conn.execute(
        "INSERT INTO clusters (name) VALUES (%s) RETURNING id", (name,)
    ).fetchone()[0]


# --------------------------------------------------------------------------- #
# V-6 / R-BM-002 / §22：大小写敏感、跨 Cluster 可重
# --------------------------------------------------------------------------- #
def test_v6_case_sensitive_and_cross_cluster_hostname(raw_conn):
    cluster_a = _new_cluster(raw_conn, "cluster-a")
    cluster_b = _new_cluster(raw_conn, "cluster-b")

    raw_conn.execute(
        "INSERT INTO bare_metals (cluster_id, hostname) VALUES (%s, 'cn001')", (cluster_a,)
    )
    # 同 Cluster 大小写不同 → 允许共存
    raw_conn.execute(
        "INSERT INTO bare_metals (cluster_id, hostname) VALUES (%s, 'CN001')", (cluster_a,)
    )
    # 同 Cluster 完全同名 → 23505
    with pytest.raises(psycopg.errors.UniqueViolation) as excinfo:
        raw_conn.execute(
            "INSERT INTO bare_metals (cluster_id, hostname) VALUES (%s, 'cn001')", (cluster_a,)
        )
    assert excinfo.value.sqlstate == "23505"

    # 跨 Cluster 同名 → 允许
    raw_conn.execute(
        "INSERT INTO bare_metals (cluster_id, hostname) VALUES (%s, 'cn001')", (cluster_b,)
    )

    active = raw_conn.execute(
        "SELECT count(*) FROM bare_metals WHERE cluster_id = %s AND deleted_at IS NULL",
        (cluster_a,),
    ).fetchone()[0]
    assert active == 2


# --------------------------------------------------------------------------- #
# V-7 / R-DELETE-006：软删释放唯一性
# --------------------------------------------------------------------------- #
def test_v7_soft_deleted_hostname_can_be_recreated(raw_conn):
    cluster_a = _new_cluster(raw_conn, "cluster-a")
    raw_conn.execute(
        "INSERT INTO bare_metals (cluster_id, hostname) VALUES (%s, 'cn001')", (cluster_a,)
    )
    raw_conn.execute(
        "UPDATE bare_metals SET deleted_at = now() WHERE cluster_id = %s AND hostname = 'cn001'",
        (cluster_a,),
    )
    # 已删不占唯一性 → 可重建同名
    raw_conn.execute(
        "INSERT INTO bare_metals (cluster_id, hostname) VALUES (%s, 'cn001')", (cluster_a,)
    )

    total = raw_conn.execute(
        "SELECT count(*) FROM bare_metals WHERE cluster_id = %s AND hostname = 'cn001'",
        (cluster_a,),
    ).fetchone()[0]
    active = raw_conn.execute(
        "SELECT count(*) FROM bare_metals "
        "WHERE cluster_id = %s AND hostname = 'cn001' AND deleted_at IS NULL",
        (cluster_a,),
    ).fetchone()[0]
    assert total == 2
    assert active == 1


# --------------------------------------------------------------------------- #
# V-8 / T-11 / R-BM-003~005：默认 IDLE / UNKNOWN / NULL / 非法值
# --------------------------------------------------------------------------- #
def test_v8_default_status_is_idle(raw_conn):
    cluster_a = _new_cluster(raw_conn, "cluster-a")
    status = raw_conn.execute(
        "INSERT INTO bare_metals (cluster_id, hostname) VALUES (%s, 'cn001') RETURNING status",
        (cluster_a,),
    ).fetchone()[0]
    assert status == "IDLE"


def test_v8_unknown_is_writable(raw_conn):
    cluster_a = _new_cluster(raw_conn, "cluster-a")
    status = raw_conn.execute(
        "INSERT INTO bare_metals (cluster_id, hostname, status) "
        "VALUES (%s, 'cn002', 'UNKNOWN') RETURNING status",
        (cluster_a,),
    ).fetchone()[0]
    assert status == "UNKNOWN"


def test_v8_null_status_rejected_with_23502(raw_conn):
    cluster_a = _new_cluster(raw_conn, "cluster-a")
    with pytest.raises(psycopg.errors.NotNullViolation) as excinfo:
        raw_conn.execute(
            "INSERT INTO bare_metals (cluster_id, hostname, status) VALUES (%s, 'cn003', NULL)",
            (cluster_a,),
        )
    assert excinfo.value.sqlstate == "23502"


@pytest.mark.parametrize("bad_status", ["BOGUS", "RUNNING", "idle", ""])
def test_v8_illegal_status_rejected_with_23514(raw_conn, bad_status):
    cluster_a = _new_cluster(raw_conn, "cluster-a")
    with pytest.raises(psycopg.errors.CheckViolation) as excinfo:
        raw_conn.execute(
            "INSERT INTO bare_metals (cluster_id, hostname, status) VALUES (%s, 'cn004', %s)",
            (cluster_a, bad_status),
        )
    assert excinfo.value.sqlstate == "23514"


# --------------------------------------------------------------------------- #
# V-9 / NQ-9：无效 cluster_id → 23503（FK 为第二道防线）
# --------------------------------------------------------------------------- #
def test_v9_invalid_cluster_id_rejected_with_23503(raw_conn):
    with pytest.raises(psycopg.errors.ForeignKeyViolation) as excinfo:
        raw_conn.execute(
            "INSERT INTO bare_metals (cluster_id, hostname) VALUES (999999999, 'cn001')"
        )
    assert excinfo.value.sqlstate == "23503"


# --------------------------------------------------------------------------- #
# V-10 / R-DELETE-004：父有子行（含已软删）时物理删除被 FK 拒绝
# --------------------------------------------------------------------------- #
def test_v10_parent_delete_blocked_while_children_exist(raw_conn):
    cluster_a = _new_cluster(raw_conn, "cluster-a")
    raw_conn.execute(
        "INSERT INTO bare_metals (cluster_id, hostname) VALUES (%s, 'cn001')", (cluster_a,)
    )
    raw_conn.execute(
        "INSERT INTO bare_metals (cluster_id, hostname, deleted_at) VALUES (%s, 'cn002', now())",
        (cluster_a,),
    )

    with pytest.raises(psycopg.errors.ForeignKeyViolation) as excinfo:
        raw_conn.execute("DELETE FROM clusters WHERE id = %s", (cluster_a,))
    assert excinfo.value.sqlstate == "23503"

    remaining = raw_conn.execute(
        "SELECT count(*) FROM bare_metals WHERE cluster_id = %s", (cluster_a,)
    ).fetchone()[0]
    assert remaining == 2


# --------------------------------------------------------------------------- #
# V-11 / R-BM-007：七列缺省 NULL；中文往返；空串 / 首尾空白原样
# --------------------------------------------------------------------------- #
def test_v11_hardware_columns_default_to_null(raw_conn):
    cluster_a = _new_cluster(raw_conn, "cluster-a")
    row = raw_conn.execute(
        "INSERT INTO bare_metals (cluster_id, hostname) VALUES (%s, 'cn001') "
        "RETURNING vendor, model, serial_number, cpu, memory, gpu, storage",
        (cluster_a,),
    ).fetchone()
    assert row == (None, None, None, None, None, None, None)


def test_v11_chinese_hostname_roundtrip(raw_conn):
    cluster_a = _new_cluster(raw_conn, "cluster-a")
    raw_conn.execute(
        "INSERT INTO bare_metals (cluster_id, hostname) VALUES (%s, %s)",
        (cluster_a, CHINESE_HOSTNAME),
    )
    fetched = raw_conn.execute(
        "SELECT hostname FROM bare_metals WHERE hostname = %s AND deleted_at IS NULL",
        (CHINESE_HOSTNAME,),
    ).fetchone()
    assert fetched is not None
    assert fetched[0] == CHINESE_HOSTNAME
    assert fetched[0].encode("utf-8") == CHINESE_HOSTNAME.encode("utf-8")


@pytest.mark.parametrize("hostname", ["", "  padded  ", "has/slash"])
def test_v11_hostname_is_stored_verbatim(raw_conn, hostname):
    """空串 / 首尾空白 / ``/`` 原样存取（未定义约束「不实现」）。"""
    cluster_a = _new_cluster(raw_conn, "cluster-a")
    raw_conn.execute(
        "INSERT INTO bare_metals (cluster_id, hostname) VALUES (%s, %s)",
        (cluster_a, hostname),
    )
    fetched = raw_conn.execute(
        "SELECT hostname FROM bare_metals WHERE cluster_id = %s AND deleted_at IS NULL",
        (cluster_a,),
    ).fetchone()[0]
    assert fetched == hostname
