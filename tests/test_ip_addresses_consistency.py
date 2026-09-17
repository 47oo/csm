"""F005 ``cluster_id`` 受控推导与漂移检测三件套（T-33 ~ T-37 数据库侧 / AC-33~AC-37）。

- T-33：经产品路径创建 IP → 直读 DB 断言 ``cluster_id == 宿主 BareMetal 的 cluster_id``。
- T-34：漂移检测**回归** —— 仅经产品路径产生的数据恒为 0 行（跨 Cluster 重复字面值、
  软删 IP / NIC 后仍为 0 行）。
- T-35：**反例证明** —— 绕过领域服务直插不一致行 → 漂移查询必须返回 **1 行**。
- T-36：**唯一性漏洞证明** —— Cluster A 已有 ``10.0.0.10``，直插真实属于 A 但
  ``cluster_id = B`` 的 ``10.0.0.10``（partial unique 不会阻止）→ 漂移查询必须发现它。
- T-37：``PATCH`` 前后 ``cluster_id`` 逐字节不变（写入路径唯一性另见
  ``tests/test_ip_addresses_guards.py`` 的 G-9 静态 guard）。

数据库断言使用 ``auth_client_and_raw`` 的**绕过应用层**原始 psycopg 连接。
"""

from __future__ import annotations

from tests.ip_address_drift_helpers import DRIFT_QUERY, find_drift


def _create_cluster(client, name: str) -> int:
    response = client.post("/api/clusters", json={"name": name})
    assert response.status_code == 201, response.text
    return response.json()["id"]


def _create_bm(client, cluster_id: int, hostname: str) -> int:
    response = client.post(
        "/api/bare-metals", json={"cluster_id": cluster_id, "hostname": hostname}
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def _create_nic(client, bare_metal_id: int, name: str = "eth0") -> int:
    response = client.post(
        "/api/network-interfaces",
        json={
            "bare_metal_id": bare_metal_id,
            "name": name,
            "technology_type": "Ethernet",
            "purpose": "Business",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def _create_ip(client, network_interface_id: int, ip_address: str) -> dict:
    response = client.post(
        "/api/ip-addresses",
        json={"network_interface_id": network_interface_id, "ip_address": ip_address},
    )
    assert response.status_code == 201, response.text
    return response.json()


def _stored_cluster(conn, ip_address_id: int) -> int:
    return conn.execute(
        "SELECT cluster_id FROM ip_addresses WHERE id = %s", (ip_address_id,)
    ).fetchone()[0]


# --------------------------------------------------------------------------- #
# T-33 / AC-33：推导正确（不是请求提供的值）
# --------------------------------------------------------------------------- #
def test_t33_cluster_id_derived_from_nic_chain(auth_client_and_raw):
    client, conn = auth_client_and_raw
    cluster_a = _create_cluster(client, "cluster-a")
    host = _create_bm(client, cluster_a, "n1")
    nic = _create_nic(client, host)

    created = _create_ip(client, nic, "10.0.0.1")

    assert _stored_cluster(conn, created["id"]) == cluster_a


def test_t33_derivation_follows_bare_metal_not_request(auth_client_and_raw):
    """请求体不接受 cluster_id；归属只能来自 NIC→BareMetal 链路。"""
    client, conn = auth_client_and_raw
    cluster_a = _create_cluster(client, "cluster-a")
    cluster_b = _create_cluster(client, "cluster-b")
    host = _create_bm(client, cluster_a, "n1")
    nic = _create_nic(client, host)

    # 即使请求携带 cluster_id=b，也被 schema 拒绝且不产生记录。
    rejected = client.post(
        "/api/ip-addresses",
        json={"network_interface_id": nic, "ip_address": "10.0.0.2", "cluster_id": cluster_b},
    )
    assert rejected.status_code == 400
    assert conn.execute("SELECT count(*) FROM ip_addresses").fetchone()[0] == 0

    created = _create_ip(client, nic, "10.0.0.3")
    assert _stored_cluster(conn, created["id"]) == cluster_a


# --------------------------------------------------------------------------- #
# T-34 / AC-34：产品路径漂移恒为 0 行（含跨 Cluster 重复 / 软删后）
# --------------------------------------------------------------------------- #
def test_t34_no_drift_on_product_path(auth_client_and_raw):
    client, conn = auth_client_and_raw
    cluster_a = _create_cluster(client, "cluster-a")
    cluster_b = _create_cluster(client, "cluster-b")

    host_a1 = _create_bm(client, cluster_a, "a1")
    host_a2 = _create_bm(client, cluster_a, "a2")
    host_b = _create_bm(client, cluster_b, "b1")
    nic_a1 = _create_nic(client, host_a1, "a1-eth0")
    nic_a2 = _create_nic(client, host_a2, "a2-eth0")
    nic_b = _create_nic(client, host_b, "b-eth0")

    ip_a1 = _create_ip(client, nic_a1, "10.0.0.10")
    # 同 Cluster A 的**另一台 BM / 另一张 NIC** 用不同字面值（不冲突）。
    ip_a2 = _create_ip(client, nic_a2, "10.0.0.11")
    # 跨 Cluster 重复字面值（R-IP-002 合法）。
    ip_b = _create_ip(client, nic_b, "10.0.0.10")
    assert find_drift(conn) == []

    # 软删 IP 后仍为 0 行。
    assert client.delete(f"/api/ip-addresses/{ip_a1['id']}").status_code == 204
    assert find_drift(conn) == []

    # 软删一张 NIC（先软删其全部活跃 IP）后仍为 0 行。
    assert client.delete(f"/api/ip-addresses/{ip_a2['id']}").status_code == 204
    assert client.delete(f"/api/network-interfaces/{nic_a2}").status_code == 204
    assert find_drift(conn) == []

    # 全部经产品路径写入的行确实存在。
    total = conn.execute("SELECT count(*) FROM ip_addresses").fetchone()[0]
    assert total == 3
    assert {ip_a1["id"], ip_a2["id"], ip_b["id"]} == {
        row[0] for row in conn.execute("SELECT id FROM ip_addresses").fetchall()
    }


# --------------------------------------------------------------------------- #
# T-35 / AC-35：反例证明 —— 直插不一致行必须被查出（1 行）
# --------------------------------------------------------------------------- #
def test_t35_bypass_insert_drift_is_detected(auth_client_and_raw):
    client, conn = auth_client_and_raw
    cluster_a = _create_cluster(client, "cluster-a")
    cluster_b = _create_cluster(client, "cluster-b")
    host = _create_bm(client, cluster_a, "n1")
    nic = _create_nic(client, host)

    # 数据库**不会**拒绝：cluster_id 与链路不一致（ADR-0002 已知取舍）。
    conn.execute(
        "INSERT INTO ip_addresses (network_interface_id, cluster_id, ip_address) "
        "VALUES (%s, %s, '10.9.9.9')",
        (nic, cluster_b),
    )

    drift = find_drift(conn)
    assert len(drift) == 1, f"漂移检测必须发现绕过领域服务写入的不一致行：{drift}"
    assert drift[0][1] == cluster_b  # stored
    assert drift[0][2] == cluster_a  # derived


# --------------------------------------------------------------------------- #
# T-36 / AC-36：漂移即唯一性静默漏洞，必须被证明
# --------------------------------------------------------------------------- #
def test_t36_drift_is_the_uniqueness_silent_hole(auth_client_and_raw):
    client, conn = auth_client_and_raw
    cluster_a = _create_cluster(client, "cluster-a")
    cluster_b = _create_cluster(client, "cluster-b")
    host = _create_bm(client, cluster_a, "n1")
    nic = _create_nic(client, host)

    # Cluster A 已有活跃 10.0.0.10（经产品路径）。
    _create_ip(client, nic, "10.0.0.10")

    # 直插一条**真实属于 A**、但存储 cluster_id = B 的 10.0.0.10 行。
    # partial unique index 看到的是 (B, 10.0.0.10)，**不会**阻止（R-IP-001 被绕过）。
    conn.execute(
        "INSERT INTO ip_addresses (network_interface_id, cluster_id, ip_address) "
        "VALUES (%s, %s, '10.0.0.10')",
        (nic, cluster_b),
    )

    # A 内现在有两条活跃 10.0.0.10，索引未阻止 —— 这正是漂移查询存在的理由。
    active_a_dupes = conn.execute(
        "SELECT count(*) FROM ip_addresses ip "
        "JOIN network_interfaces nic ON nic.id = ip.network_interface_id "
        "JOIN bare_metals bm ON bm.id = nic.bare_metal_id "
        "WHERE bm.cluster_id = %s AND ip.ip_address = '10.0.0.10' AND ip.deleted_at IS NULL",
        (cluster_a,),
    ).fetchone()[0]
    assert active_a_dupes == 2, "唯一索引在错误 Cluster 边界判断，未阻止重复"

    drift = find_drift(conn)
    assert len(drift) == 1, f"漂移查询必须发现该静默漏洞：{drift}"
    assert drift[0][1] == cluster_b
    assert drift[0][2] == cluster_a
    assert DRIFT_QUERY.strip().startswith("SELECT ip.id")


# --------------------------------------------------------------------------- #
# T-37 / AC-37：PATCH 前后 cluster_id 逐字节不变
# --------------------------------------------------------------------------- #
def test_t37_patch_never_touches_cluster_id(auth_client_and_raw):
    client, conn = auth_client_and_raw
    cluster_a = _create_cluster(client, "cluster-a")
    host = _create_bm(client, cluster_a, "n1")
    nic = _create_nic(client, host)
    created = _create_ip(client, nic, "10.0.0.1")

    before = conn.execute(
        "SELECT cluster_id, network_interface_id FROM ip_addresses WHERE id = %s",
        (created["id"],),
    ).fetchone()

    patched = client.patch(f"/api/ip-addresses/{created['id']}", json={"ip_address": "10.0.0.2"})
    assert patched.status_code == 200, patched.text
    assert patched.json()["ip_address"] == "10.0.0.2"

    after = conn.execute(
        "SELECT cluster_id, network_interface_id FROM ip_addresses WHERE id = %s",
        (created["id"],),
    ).fetchone()
    assert after == before, "PATCH 不得改动 cluster_id / network_interface_id"
    assert find_drift(conn) == []
