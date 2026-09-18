"""F005 IPAddress 数据库约束断言（V-11 ~ V-14，绕过应用层直连 PostgreSQL）。

证明唯一性 / 无格式约束 / 无一致性约束由数据库真实行为决定：

- V-11：直连插入同 Cluster 内字面相同的**活跃**两行 → ``23505``；跨 Cluster 相同字面 →
  成功；
- V-12：直连插入空串 / 含首尾空白 / ``not-an-ip`` / 超长 → **均成功**（无格式约束）；
- V-13：直连把某行 ``cluster_id`` 改成与推导链不一致的值 → **成功**（数据库不保证该
  invariant），且**漂移查询能查出**（1 行）；
- V-14：软删某行后，同 Cluster 可再次插入相同字面值的活跃行。
"""

from __future__ import annotations

import psycopg
import pytest

from tests.ip_address_drift_helpers import find_drift


def _chain(raw_conn, name: str) -> tuple[int, int]:
    """建 Cluster → BareMetal → NetworkInterface，返回 ``(cluster_id, nic_id)``。"""
    cluster_id = raw_conn.execute(
        "INSERT INTO clusters (name) VALUES (%s) RETURNING id", (name,)
    ).fetchone()[0]
    bare_metal_id = raw_conn.execute(
        "INSERT INTO bare_metals (cluster_id, hostname) VALUES (%s, 'n1') RETURNING id",
        (cluster_id,),
    ).fetchone()[0]
    nic_id = raw_conn.execute(
        "INSERT INTO network_interfaces (bare_metal_id, name, technology_type, purpose) "
        "VALUES (%s, 'eth0', 'Ethernet', 'Business') RETURNING id",
        (bare_metal_id,),
    ).fetchone()[0]
    return cluster_id, nic_id


def _insert_ip(raw_conn, nic_id: int, cluster_id: int, ip: str, *, deleted: bool = False) -> int:
    if deleted:
        return raw_conn.execute(
            "INSERT INTO ip_addresses (network_interface_id, cluster_id, ip_address, deleted_at) "
            "VALUES (%s, %s, %s, now()) RETURNING id",
            (nic_id, cluster_id, ip),
        ).fetchone()[0]
    return raw_conn.execute(
        "INSERT INTO ip_addresses (network_interface_id, cluster_id, ip_address) "
        "VALUES (%s, %s, %s) RETURNING id",
        (nic_id, cluster_id, ip),
    ).fetchone()[0]


# --------------------------------------------------------------------------- #
# V-11：同 Cluster 活跃重复 → 23505；跨 Cluster 相同字面 → 成功
# --------------------------------------------------------------------------- #
def test_v11_active_duplicate_same_cluster_rejected(raw_conn):
    cluster_id, nic_id = _chain(raw_conn, "cluster-a")
    _insert_ip(raw_conn, nic_id, cluster_id, "10.0.0.10")
    with pytest.raises(psycopg.errors.UniqueViolation) as excinfo:
        _insert_ip(raw_conn, nic_id, cluster_id, "10.0.0.10")
    assert excinfo.value.sqlstate == "23505"


def test_v11_cross_cluster_same_literal_succeeds(raw_conn):
    cluster_a, nic_a = _chain(raw_conn, "cluster-a")
    cluster_b, nic_b = _chain(raw_conn, "cluster-b")
    _insert_ip(raw_conn, nic_a, cluster_a, "10.0.0.10")
    _insert_ip(raw_conn, nic_b, cluster_b, "10.0.0.10")
    total = raw_conn.execute("SELECT count(*) FROM ip_addresses").fetchone()[0]
    assert total == 2


def test_v11_invalid_nic_fk_rejected_with_23503(raw_conn):
    cluster_id, _ = _chain(raw_conn, "cluster-a")
    with pytest.raises(psycopg.errors.ForeignKeyViolation) as excinfo:
        raw_conn.execute(
            "INSERT INTO ip_addresses (network_interface_id, cluster_id, ip_address) "
            "VALUES (999999999, %s, '10.0.0.1')",
            (cluster_id,),
        )
    assert excinfo.value.sqlstate == "23503"


# --------------------------------------------------------------------------- #
# V-12：无格式约束 —— 空串 / 首尾空白 / not-an-ip / 超长 均成功、原样存取
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("literal", ["", "  padded  ", "not-an-ip", "x" * 300, "10.0.0.1/16"])
def test_v12_format_constraints_not_enforced(raw_conn, literal):
    cluster_id, nic_id = _chain(raw_conn, f"cluster-{abs(hash(literal)) % 100000}")
    _insert_ip(raw_conn, nic_id, cluster_id, literal)
    stored = raw_conn.execute(
        "SELECT ip_address FROM ip_addresses "
        "WHERE network_interface_id = %s AND deleted_at IS NULL",
        (nic_id,),
    ).fetchone()[0]
    assert stored == literal


# --------------------------------------------------------------------------- #
# V-13：直连改 cluster_id 为不一致值 → 成功，但漂移查询能查出（1 行）
# --------------------------------------------------------------------------- #
def test_v13_inconsistent_cluster_id_is_detected_not_prevented(raw_conn):
    cluster_a, nic_a = _chain(raw_conn, "cluster-a")
    cluster_b, _ = _chain(raw_conn, "cluster-b")
    ip_id = _insert_ip(raw_conn, nic_a, cluster_a, "10.0.0.1")

    # 数据库层不阻止不一致（ADR-0002 已知取舍）。
    raw_conn.execute("UPDATE ip_addresses SET cluster_id = %s WHERE id = %s", (cluster_b, ip_id))

    drift = find_drift(raw_conn)
    assert len(drift) == 1, f"漂移查询必须查出一致性破坏：{drift}"
    assert drift[0][0] == ip_id
    assert drift[0][1] == cluster_b
    assert drift[0][2] == cluster_a


# --------------------------------------------------------------------------- #
# V-14：软删释放唯一性
# --------------------------------------------------------------------------- #
def test_v14_soft_deleted_ip_releases_uniqueness(raw_conn):
    cluster_id, nic_id = _chain(raw_conn, "cluster-a")
    deleted_id = _insert_ip(raw_conn, nic_id, cluster_id, "10.0.0.10", deleted=True)
    active_id = _insert_ip(raw_conn, nic_id, cluster_id, "10.0.0.10")
    assert active_id != deleted_id
    active = raw_conn.execute(
        "SELECT count(*) FROM ip_addresses "
        "WHERE cluster_id = %s AND ip_address = '10.0.0.10' AND deleted_at IS NULL",
        (cluster_id,),
    ).fetchone()[0]
    assert active == 1
    total = raw_conn.execute(
        "SELECT count(*) FROM ip_addresses WHERE cluster_id = %s AND ip_address = '10.0.0.10'",
        (cluster_id,),
    ).fetchone()[0]
    assert total == 2
