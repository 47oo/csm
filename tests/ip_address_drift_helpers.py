"""``cluster_id`` 漂移检测查询 —— **测试侧**单一常量与执行辅助（决策 6 / AC-34）。

该 SQL 逐字采用 ``docs/architecture/f005-ip-address-handoff.md`` AC-34 的漂移查询，
**不加** ``deleted_at`` 过滤（检查全部行）。它是**唯一**能从数据库侧发现
``ip_addresses.cluster_id`` 与 ``NIC → BareMetal`` 链路不一致的手段；若漂移发生，
``ux_ip_addresses_cluster_ip_active`` 会在**错误的** Cluster 边界判断唯一性，导致同
Cluster 内两条活跃相同 IP 静默通过（R-IP-001 失效）。

只存在于测试侧；**不**新增产品端点、**不**在生产代码中放未被调用的死代码。
"""

from __future__ import annotations

from typing import Any

import psycopg

#: AC-34：存储 ``cluster_id`` ≠ 推导 ``cluster_id`` 的行；期望 **0 行**。
DRIFT_QUERY = """
SELECT ip.id, ip.cluster_id AS stored_cluster, bm.cluster_id AS derived_cluster
FROM ip_addresses ip
JOIN network_interfaces nic ON nic.id = ip.network_interface_id
JOIN bare_metals        bm  ON bm.id  = nic.bare_metal_id
WHERE ip.cluster_id <> bm.cluster_id
"""


def find_drift(conn: psycopg.Connection) -> list[Any]:
    """执行漂移查询，返回全部不一致行（期望空列表）。"""
    return conn.execute(DRIFT_QUERY).fetchall()
