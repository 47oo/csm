"""F021 IP 地址自动 / 手动分配 API 行为测试（AC-01 ~ AC-33 的产品路径部分）。

数据库夹具 ``auth_client_and_raw`` 同时提供产品客户端与**绕过应用层**的原始 psycopg
连接，用于断言数据库侧状态、预置软删行与 R-IP-001 partial unique 的最终权威。
静态 / 结构 guard 见 ``tests/test_ip_allocations_guards.py``。
"""

from __future__ import annotations

import threading
from contextlib import contextmanager

import psycopg
import pytest
from fastapi.testclient import TestClient

from tests.conftest import AUTH_PASSWORD, AUTH_USERNAME, create_user, login
from tests.database.helpers import raw_connection_dsn, upgrade_to_head
from tests.ip_address_drift_helpers import find_drift

READ_FIELDS = {
    "id",
    "network_interface_id",
    "ip_address",
    "created_at",
    "updated_at",
}

AUTO = "/api/ip-addresses/allocate"
MANUAL = "/api/ip-addresses/allocate-manual"


# --------------------------------------------------------------------------- #
# 夹具辅助
# --------------------------------------------------------------------------- #
def _create_cluster(client, name: str) -> int:
    response = client.post("/api/clusters", json={"name": name})
    assert response.status_code == 201, response.text
    return response.json()["id"]


def _create_bm(client, cluster_id: int, hostname: str = "n1") -> int:
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


def _create_range(client, cluster_id: int, start_ip: str, end_ip: str) -> int:
    response = client.post(
        "/api/ip-address-ranges",
        json={"cluster_id": cluster_id, "start_ip": start_ip, "end_ip": end_ip},
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def _create_ip(client, network_interface_id: int, ip_address: str) -> int:
    response = client.post(
        "/api/ip-addresses",
        json={"network_interface_id": network_interface_id, "ip_address": ip_address},
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def _auto(client, network_interface_id: int, ip_address_range_id: int):
    return client.post(
        AUTO,
        json={
            "network_interface_id": network_interface_id,
            "ip_address_range_id": ip_address_range_id,
        },
    )


def _manual(client, network_interface_id: int, ip_address: str):
    return client.post(
        MANUAL,
        json={"network_interface_id": network_interface_id, "ip_address": ip_address},
    )


def _raw_cluster(conn, name: str) -> int:
    return conn.execute("INSERT INTO clusters (name) VALUES (%s) RETURNING id", (name,)).fetchone()[
        0
    ]


def _raw_bm(conn, cluster_id: int, hostname: str, *, deleted: bool = False) -> int:
    if deleted:
        return conn.execute(
            "INSERT INTO bare_metals (cluster_id, hostname, deleted_at) "
            "VALUES (%s, %s, now()) RETURNING id",
            (cluster_id, hostname),
        ).fetchone()[0]
    return conn.execute(
        "INSERT INTO bare_metals (cluster_id, hostname) VALUES (%s, %s) RETURNING id",
        (cluster_id, hostname),
    ).fetchone()[0]


def _raw_nic(conn, bare_metal_id: int, name: str = "eth0", *, deleted: bool = False) -> int:
    if deleted:
        return conn.execute(
            "INSERT INTO network_interfaces "
            "(bare_metal_id, name, technology_type, purpose, deleted_at) "
            "VALUES (%s, %s, 'Ethernet', 'Business', now()) RETURNING id",
            (bare_metal_id, name),
        ).fetchone()[0]
    return conn.execute(
        "INSERT INTO network_interfaces (bare_metal_id, name, technology_type, purpose) "
        "VALUES (%s, %s, 'Ethernet', 'Business') RETURNING id",
        (bare_metal_id, name),
    ).fetchone()[0]


def _raw_ip(
    conn, network_interface_id: int, cluster_id: int, ip_address: str, *, deleted: bool = False
) -> int:
    if deleted:
        return conn.execute(
            "INSERT INTO ip_addresses "
            "(network_interface_id, cluster_id, ip_address, deleted_at) "
            "VALUES (%s, %s, %s, now()) RETURNING id",
            (network_interface_id, cluster_id, ip_address),
        ).fetchone()[0]
    return conn.execute(
        "INSERT INTO ip_addresses (network_interface_id, cluster_id, ip_address) "
        "VALUES (%s, %s, %s) RETURNING id",
        (network_interface_id, cluster_id, ip_address),
    ).fetchone()[0]


def _active_ip_count(conn) -> int:
    return conn.execute(
        "SELECT count(*) FROM ip_addresses WHERE deleted_at IS NULL"
    ).fetchone()[0]


def _total_ip_count(conn) -> int:
    return conn.execute("SELECT count(*) FROM ip_addresses").fetchone()[0]


def _raw_chain(conn, name: str) -> tuple[int, int, int]:
    cluster_id = _raw_cluster(conn, name)
    bm_id = _raw_bm(conn, cluster_id, "n1")
    nic_id = _raw_nic(conn, bm_id)
    return cluster_id, bm_id, nic_id


@contextmanager
def _isolated_clients(database_url: str):
    """两个独立应用的已登录客户端（供真实线程并发）。"""
    from app.config import Settings
    from app.main import create_app

    upgrade_to_head(database_url)
    create_user(database_url, AUTH_USERNAME, AUTH_PASSWORD)
    apps = [
        create_app(Settings(environment="dev", database_url=database_url)) for _ in range(2)
    ]
    with (
        TestClient(apps[0], raise_server_exceptions=False) as first,
        TestClient(apps[1], raise_server_exceptions=False) as second,
    ):
        login(first)
        login(second)
        yield first, second


# --------------------------------------------------------------------------- #
# AC-01：未认证
# --------------------------------------------------------------------------- #
def test_ac01_unauthenticated_is_rejected(app_client):
    assert app_client.post(AUTO, json={"network_interface_id": 1}).status_code == 401
    assert (
        app_client.post(
            MANUAL, json={"network_interface_id": 1, "ip_address": "10.0.0.1"}
        ).status_code
        == 401
    )


# --------------------------------------------------------------------------- #
# AC-02：成功响应字段集合恰为 F005 表示（无 cluster_id / status / deleted_at）
# --------------------------------------------------------------------------- #
def test_ac02_auto_allocation_returns_closed_field_set(auth_client_and_raw):
    client, conn = auth_client_and_raw
    cluster_id = _create_cluster(client, "cluster-a")
    bm_id = _create_bm(client, cluster_id)
    nic_id = _create_nic(client, bm_id)
    range_id = _create_range(client, cluster_id, "10.0.0.1", "10.0.0.255")

    response = _auto(client, nic_id, range_id)

    assert response.status_code == 201, response.text
    body = response.json()
    assert set(body) == READ_FIELDS
    assert body["network_interface_id"] == nic_id
    assert body["ip_address"] == "10.0.0.1"
    assert _active_ip_count(conn) == 1


# --------------------------------------------------------------------------- #
# AC-03：请求字段封闭
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "extra",
    [
        {"cluster_id": 1},
        {"status": "ACTIVE"},
        {"deleted_at": None},
        {"mode": "auto"},
        {"reserved_addresses": []},
        {"purpose": "business"},
    ],
)
def test_ac03_auto_rejects_unknown_fields(auth_client_and_raw, extra):
    client, conn = auth_client_and_raw
    cluster_id = _create_cluster(client, "cluster-a")
    bm_id = _create_bm(client, cluster_id)
    nic_id = _create_nic(client, bm_id)
    range_id = _create_range(client, cluster_id, "10.0.0.1", "10.0.0.255")
    response = client.post(
        AUTO,
        json={
            "network_interface_id": nic_id,
            "ip_address_range_id": range_id,
            **extra,
        },
    )
    assert response.status_code == 400, response.text
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
    assert _total_ip_count(conn) == 0


@pytest.mark.parametrize(
    "extra",
    [
        {"cluster_id": 1},
        {"status": "ACTIVE"},
        {"deleted_at": None},
        {"mode": "manual"},
        {"reserved_addresses": []},
        {"purpose": "business"},
    ],
)
def test_ac03_manual_rejects_unknown_fields(auth_client_and_raw, extra):
    client, conn = auth_client_and_raw
    cluster_id = _create_cluster(client, "cluster-a")
    bm_id = _create_bm(client, cluster_id)
    nic_id = _create_nic(client, bm_id)
    payload = {"network_interface_id": nic_id, "ip_address": "10.0.0.1", **extra}
    response = client.post(MANUAL, json=payload)
    assert response.status_code == 400, response.text
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
    assert _total_ip_count(conn) == 0


def test_ac03_auto_rejects_ip_address_field(auth_client_and_raw):
    client, conn = auth_client_and_raw
    cluster_id = _create_cluster(client, "cluster-a")
    nic_id = _create_nic(client, _create_bm(client, cluster_id))
    range_id = _create_range(client, cluster_id, "10.0.0.1", "10.0.0.255")
    response = client.post(
        AUTO,
        json={
            "network_interface_id": nic_id,
            "ip_address_range_id": range_id,
            "ip_address": "10.0.0.1",
        },
    )
    assert response.status_code == 400, response.text
    assert _total_ip_count(conn) == 0


# --------------------------------------------------------------------------- #
# AC-04：network_interface_id 必填 / 非整数 / null
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("value", ["MISSING", "abc", None, 1.5])
@pytest.mark.parametrize("path", [AUTO, MANUAL])
def test_ac04_missing_or_invalid_nic(auth_client_and_raw, path, value):
    client, conn = auth_client_and_raw
    payload: dict = {"ip_address": "10.0.0.1"} if path == MANUAL else {}
    if value != "MISSING":
        payload["network_interface_id"] = value
    response = client.post(path, json=payload)
    assert response.status_code == 400, response.text
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
    details = response.json()["error"]["details"]
    assert any(d["field"] == "network_interface_id" for d in details), details
    assert _total_ip_count(conn) == 0


# --------------------------------------------------------------------------- #
# AC-05：NIC 不存在 / 已软删 / 宿主 BareMetal 不活跃 → 404，不写入
# --------------------------------------------------------------------------- #
def test_ac05_nonexistent_nic_is_404(auth_client_and_raw):
    client, conn = auth_client_and_raw
    cluster_id = _create_cluster(client, "cluster-a")
    range_id = _create_range(client, cluster_id, "10.0.0.1", "10.0.0.255")
    for path in (AUTO, MANUAL):
        payload = {"network_interface_id": 999999999}
        if path == AUTO:
            payload["ip_address_range_id"] = range_id
        elif path == MANUAL:
            payload["ip_address"] = "10.0.0.1"
        response = client.post(path, json=payload)
        assert response.status_code == 404, response.text
        assert response.json()["error"]["code"] == "NOT_FOUND"
    assert _total_ip_count(conn) == 0


def test_ac05_deleted_nic_is_404(auth_client_and_raw):
    client, conn = auth_client_and_raw
    cluster_id, _, bm_id = _raw_chain(conn, "cluster-a")
    deleted_nic = _raw_nic(conn, bm_id, deleted=True)
    range_id = _create_range(client, cluster_id, "10.0.0.1", "10.0.0.255")
    assert _auto(client, deleted_nic, range_id).status_code == 404
    assert _manual(client, deleted_nic, "10.0.0.1").status_code == 404
    assert _total_ip_count(conn) == 0


def test_ac05_inactive_host_bare_metal_is_404(auth_client_and_raw):
    client, conn = auth_client_and_raw
    cluster_id = _raw_cluster(conn, "cluster-a")
    bm_id = _raw_bm(conn, cluster_id, "n1", deleted=True)
    nic_id = _raw_nic(conn, bm_id)
    range_id = _create_range(client, cluster_id, "10.0.0.1", "10.0.0.255")
    assert _auto(client, nic_id, range_id).status_code == 404
    assert _manual(client, nic_id, "10.0.0.1").status_code == 404
    assert _total_ip_count(conn) == 0


# --------------------------------------------------------------------------- #
# AC-06 / AC-07：Cluster 受控推导；响应无 cluster_id；无漂移
# --------------------------------------------------------------------------- #
def test_ac06_ac07_cluster_id_derived_and_no_drift(auth_client_and_raw):
    client, conn = auth_client_and_raw
    cluster_id = _create_cluster(client, "cluster-a")
    bm_id = _create_bm(client, cluster_id)
    nic_id = _create_nic(client, bm_id)
    range_id = _create_range(client, cluster_id, "10.0.0.1", "10.0.0.255")

    body = _auto(client, nic_id, range_id).json()
    assert "cluster_id" not in body

    stored = conn.execute(
        "SELECT ip.cluster_id, bm.cluster_id FROM ip_addresses ip "
        "JOIN network_interfaces nic ON nic.id = ip.network_interface_id "
        "JOIN bare_metals bm ON bm.id = nic.bare_metal_id WHERE ip.id = %s",
        (body["id"],),
    ).fetchone()
    assert stored[0] == stored[1] == cluster_id
    assert find_drift(conn) == []


# --------------------------------------------------------------------------- #
# AC-08 ~ AC-11：自动分配语义
# --------------------------------------------------------------------------- #
def test_ac08_auto_picks_min_within_selected_range_only(auth_client_and_raw):
    # F023 新语义：自动分配仅在**所选单个**活跃范围段内取数值最小未占用；
    # **不**在未选段里取更小的值。
    client, conn = auth_client_and_raw
    cluster_id = _create_cluster(client, "cluster-a")
    nic_id = _create_nic(client, _create_bm(client, cluster_id))
    high_range = _create_range(client, cluster_id, "10.0.0.10", "10.0.0.12")
    low_range = _create_range(client, cluster_id, "10.0.0.1", "10.0.0.3")

    selected_high = _auto(client, nic_id, high_range)
    assert selected_high.status_code == 201, selected_high.text
    # 尽管另一段存在更小值 10.0.0.1，仍取所选段内最小的 10.0.0.10。
    assert selected_high.json()["ip_address"] == "10.0.0.10"

    selected_low = _auto(client, nic_id, low_range)
    assert selected_low.status_code == 201, selected_low.text
    assert selected_low.json()["ip_address"] == "10.0.0.1"


def test_ac09_auto_skips_occupied_literal(auth_client_and_raw):
    client, conn = auth_client_and_raw
    cluster_id = _create_cluster(client, "cluster-a")
    nic_id = _create_nic(client, _create_bm(client, cluster_id))
    range_id = _create_range(client, cluster_id, "10.0.0.1", "10.0.0.3")
    _create_ip(client, nic_id, "10.0.0.1")

    response = _auto(client, nic_id, range_id)
    assert response.status_code == 201, response.text
    assert response.json()["ip_address"] == "10.0.0.2"


def test_ac10_auto_writes_canonical_dotted_quad(auth_client_and_raw):
    client, conn = auth_client_and_raw
    cluster_id = _create_cluster(client, "cluster-a")
    nic_id = _create_nic(client, _create_bm(client, cluster_id))
    range_id = _create_range(client, cluster_id, "010.000.000.001", "010.000.000.003")

    body = _auto(client, nic_id, range_id).json()
    assert body["ip_address"] == "10.0.0.1"
    detail = client.get(f"/api/ip-addresses/{body['id']}").json()
    assert detail["ip_address"] == "10.0.0.1"


def test_ac11_no_implicit_reserved_address_skipped(auth_client_and_raw):
    client, conn = auth_client_and_raw
    cluster_id = _create_cluster(client, "cluster-a")
    nic_id = _create_nic(client, _create_bm(client, cluster_id))
    range_id = _create_range(client, cluster_id, "10.0.0.0", "10.0.0.255")

    response = _auto(client, nic_id, range_id)
    assert response.status_code == 201, response.text
    assert response.json()["ip_address"] == "10.0.0.0"


# --------------------------------------------------------------------------- #
# AC-12 ~ AC-16：占用判定与比较边界
# --------------------------------------------------------------------------- #
def test_ac12_active_same_literal_is_occupied(auth_client_and_raw):
    client, conn = auth_client_and_raw
    cluster_id, _, nic_id = _raw_chain(conn, "cluster-a")
    range_id = _create_range(client, cluster_id, "10.0.0.1", "10.0.0.2")
    _raw_ip(conn, nic_id, cluster_id, "10.0.0.1")

    assert _auto(client, nic_id, range_id).json()["ip_address"] == "10.0.0.2"


def test_ac13_different_literal_is_not_occupied(auth_client_and_raw):
    client, conn = auth_client_and_raw
    cluster_id, _, nic_id = _raw_chain(conn, "cluster-a")
    range_id = _create_range(client, cluster_id, "10.0.0.1", "10.0.0.2")
    _raw_ip(conn, nic_id, cluster_id, "010.0.0.1")

    response = _auto(client, nic_id, range_id)
    assert response.status_code == 201, response.text
    assert response.json()["ip_address"] == "10.0.0.1"


def test_ac14_soft_deleted_releases_literal(auth_client_and_raw):
    client, conn = auth_client_and_raw
    cluster_id, _, nic_id = _raw_chain(conn, "cluster-a")
    range_id = _create_range(client, cluster_id, "10.0.0.1", "10.0.0.2")
    _raw_ip(conn, nic_id, cluster_id, "10.0.0.1", deleted=True)

    response = _auto(client, nic_id, range_id)
    assert response.status_code == 201, response.text
    assert response.json()["ip_address"] == "10.0.0.1"


def test_ac15_literal_with_prefix_does_not_occupy(auth_client_and_raw):
    client, conn = auth_client_and_raw
    cluster_id, _, nic_id = _raw_chain(conn, "cluster-a")
    range_id = _create_range(client, cluster_id, "10.0.0.1", "10.0.0.2")
    _raw_ip(conn, nic_id, cluster_id, "10.0.0.1/16")

    response = _auto(client, nic_id, range_id)
    assert response.status_code == 201, response.text
    assert response.json()["ip_address"] == "10.0.0.1"


def test_ac16_cross_cluster_same_literal_is_allowed(auth_client_and_raw):
    client, conn = auth_client_and_raw
    cluster_a, _, nic_a = _raw_chain(conn, "cluster-a")
    cluster_b, _, nic_b = _raw_chain(conn, "cluster-b")
    _create_range(client, cluster_a, "10.0.0.1", "10.0.0.2")
    range_b = _create_range(client, cluster_b, "10.0.0.1", "10.0.0.2")
    _raw_ip(conn, nic_a, cluster_a, "10.0.0.1")

    response = _auto(client, nic_b, range_b)
    assert response.status_code == 201, response.text
    assert response.json()["ip_address"] == "10.0.0.1"


# --------------------------------------------------------------------------- #
# AC-17 / AC-17b：手动分配成功与规范化
# --------------------------------------------------------------------------- #
def test_ac17_manual_in_range_succeeds(auth_client_and_raw):
    client, conn = auth_client_and_raw
    cluster_id = _create_cluster(client, "cluster-a")
    nic_id = _create_nic(client, _create_bm(client, cluster_id))
    _create_range(client, cluster_id, "10.0.0.1", "10.0.0.255")

    response = _manual(client, nic_id, "10.0.0.5")
    assert response.status_code == 201, response.text
    assert response.json()["ip_address"] == "10.0.0.5"
    assert set(response.json()) == READ_FIELDS


def test_ac17b_manual_normalizes_non_canonical_input(auth_client_and_raw):
    client, conn = auth_client_and_raw
    cluster_id = _create_cluster(client, "cluster-a")
    nic_id = _create_nic(client, _create_bm(client, cluster_id))
    _create_range(client, cluster_id, "10.0.0.1", "10.0.0.255")

    body = _manual(client, nic_id, "010.000.000.005").json()
    assert body["ip_address"] == "10.0.0.5"
    stored = conn.execute(
        "SELECT ip_address FROM ip_addresses WHERE id = %s", (body["id"],)
    ).fetchone()[0]
    assert stored == "10.0.0.5"


# --------------------------------------------------------------------------- #
# AC-18 / AC-19：手动范围外 / 已占用
# --------------------------------------------------------------------------- #
def test_ac18_manual_out_of_range_is_409(auth_client_and_raw):
    client, conn = auth_client_and_raw
    cluster_id = _create_cluster(client, "cluster-a")
    nic_id = _create_nic(client, _create_bm(client, cluster_id))
    _create_range(client, cluster_id, "10.0.0.1", "10.0.0.10")

    response = _manual(client, nic_id, "10.0.0.20")
    assert response.status_code == 409, response.text
    body = response.json()
    assert body["error"]["code"] == "CONFLICT"
    assert body["error"]["details"][0]["code"] == "OUT_OF_RANGE"
    assert body["error"]["details"][0]["field"] == "ip_address"
    assert _total_ip_count(conn) == 0


def test_ac18_manual_with_no_active_range_is_out_of_range(auth_client_and_raw):
    client, conn = auth_client_and_raw
    cluster_id = _create_cluster(client, "cluster-a")
    nic_id = _create_nic(client, _create_bm(client, cluster_id))

    response = _manual(client, nic_id, "10.0.0.5")
    assert response.status_code == 409, response.text
    assert response.json()["error"]["details"][0]["code"] == "OUT_OF_RANGE"


def test_ac19_manual_duplicate_is_409(auth_client_and_raw):
    client, conn = auth_client_and_raw
    cluster_id = _create_cluster(client, "cluster-a")
    nic_id = _create_nic(client, _create_bm(client, cluster_id))
    _create_range(client, cluster_id, "10.0.0.1", "10.0.0.10")
    _create_ip(client, nic_id, "10.0.0.5")

    response = _manual(client, nic_id, "10.0.0.5")
    assert response.status_code == 409, response.text
    body = response.json()
    assert body["error"]["code"] == "CONFLICT"
    assert body["error"]["details"][0]["code"] == "DUPLICATE"
    assert body["error"]["details"][0]["field"] == "ip_address"
    assert _active_ip_count(conn) == 1


# --------------------------------------------------------------------------- #
# AC-20：非法 IPv4 → 400，不创建记录
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "bad",
    ["10.0.0.256", "10.0.0", "abc", "1.2.3.4/24", "2001:db8::1", "", " 10.0.0.1", "10.0.0.1 "],
)
def test_ac20_manual_invalid_ipv4_is_400(auth_client_and_raw, bad):
    client, conn = auth_client_and_raw
    cluster_id = _create_cluster(client, "cluster-a")
    nic_id = _create_nic(client, _create_bm(client, cluster_id))
    _create_range(client, cluster_id, "10.0.0.1", "10.0.0.255")

    response = _manual(client, nic_id, bad)
    assert response.status_code == 400, response.text
    body = response.json()
    assert body["error"]["code"] == "VALIDATION_ERROR"
    details = body["error"]["details"]
    assert any(d["field"] == "ip_address" and d["code"] == "INVALID" for d in details), details
    assert _total_ip_count(conn) == 0


def test_ac20_invalid_ipv4_precedes_nic_check(auth_client_and_raw):
    # 稳定顺序：非法 IPv4 先于 NIC 活跃性校验 → 400（而非 404）。
    client, conn = auth_client_and_raw
    response = _manual(client, 999999999, "10.0.0.256")
    assert response.status_code == 400, response.text


def test_ac20_valid_ipv4_with_missing_nic_precedes_range_check(auth_client_and_raw):
    # NIC 校验先于范围归属 → 404（而非 409 OUT_OF_RANGE）。
    client, conn = auth_client_and_raw
    response = _manual(client, 999999999, "10.0.0.5")
    assert response.status_code == 404, response.text


# --------------------------------------------------------------------------- #
# AC-21：范围外字面仍走 F005 登记端点（201）
# --------------------------------------------------------------------------- #
def test_ac21_f005_still_accepts_out_of_range_literal(auth_client_and_raw):
    client, conn = auth_client_and_raw
    cluster_id = _create_cluster(client, "cluster-a")
    nic_id = _create_nic(client, _create_bm(client, cluster_id))
    _create_range(client, cluster_id, "10.0.0.1", "10.0.0.10")

    response = client.post(
        "/api/ip-addresses",
        json={"network_interface_id": nic_id, "ip_address": "10.0.0.20"},
    )
    assert response.status_code == 201, response.text
    assert response.json()["ip_address"] == "10.0.0.20"


# --------------------------------------------------------------------------- #
# AC-22 / AC-23：耗尽非 500 且无写入
# --------------------------------------------------------------------------- #
def test_ac22_exhausted_pool_is_409_without_write(auth_client_and_raw):
    client, conn = auth_client_and_raw
    cluster_id = _create_cluster(client, "cluster-a")
    nic_id = _create_nic(client, _create_bm(client, cluster_id))
    range_id = _create_range(client, cluster_id, "10.0.0.1", "10.0.0.2")
    _create_ip(client, nic_id, "10.0.0.1")
    _create_ip(client, nic_id, "10.0.0.2")
    before = _total_ip_count(conn)

    response = _auto(client, nic_id, range_id)
    assert response.status_code == 409, response.text
    body = response.json()
    assert body["error"]["code"] == "CONFLICT"
    assert body["error"]["details"][0]["code"] == "NO_AVAILABLE_IP"
    assert body["error"]["details"][0]["field"] is None
    assert _total_ip_count(conn) == before


def test_ac23_no_active_range_is_not_exhausted(auth_client_and_raw):
    # F023 新语义：目标 Cluster 无任何活跃范围段时，自动分配不再是 409 耗尽，
    # 而是「无法提供有效 ip_address_range_id」：请求缺失 → 400；引用不存在 → 404。
    client, conn = auth_client_and_raw
    cluster_id = _create_cluster(client, "cluster-a")
    nic_id = _create_nic(client, _create_bm(client, cluster_id))

    missing = client.post(AUTO, json={"network_interface_id": nic_id})
    assert missing.status_code == 400, missing.text
    assert missing.json()["error"]["code"] == "VALIDATION_ERROR"
    assert any(
        detail["field"] == "ip_address_range_id"
        for detail in missing.json()["error"]["details"]
    )

    nonexistent = _auto(client, nic_id, 999999999)
    assert nonexistent.status_code == 404, nonexistent.text
    assert nonexistent.json()["error"]["code"] == "NOT_FOUND"
    assert (
        nonexistent.json()["error"]["details"][0]["code"]
        == "IP_ADDRESS_RANGE_UNAVAILABLE"
    )
    assert _total_ip_count(conn) == 0


# --------------------------------------------------------------------------- #
# AC-26：直连 DB 重复活跃字面 → 23505（R-IP-001 partial unique 最终权威）
# --------------------------------------------------------------------------- #
def test_ac26_raw_duplicate_active_literal_is_23505(auth_client_and_raw):
    client, conn = auth_client_and_raw
    cluster_id, _, nic_id = _raw_chain(conn, "cluster-a")
    _raw_ip(conn, nic_id, cluster_id, "10.0.0.5")

    with pytest.raises(psycopg.errors.UniqueViolation) as excinfo:
        _raw_ip(conn, nic_id, cluster_id, "10.0.0.5")
    assert excinfo.value.sqlstate == "23505"


def test_ac26_raw_numeric_equal_but_literal_different_both_succeed(auth_client_and_raw):
    client, conn = auth_client_and_raw
    cluster_id, _, nic_id = _raw_chain(conn, "cluster-a")
    _raw_ip(conn, nic_id, cluster_id, "010.0.0.1")
    _raw_ip(conn, nic_id, cluster_id, "10.0.0.1")
    assert conn.execute("SELECT count(*) FROM ip_addresses").fetchone()[0] == 2


# --------------------------------------------------------------------------- #
# AC-25：真实线程并发自动分配 → 恰一条 201，另一条 409 DUPLICATE
# --------------------------------------------------------------------------- #
def test_ac25_concurrent_auto_allocation_at_most_one_succeeds(database_url):
    with _isolated_clients(database_url) as (first, second):
        cluster_id = _create_cluster(first, "cluster-a")
        nic_id = _create_nic(first, _create_bm(first, cluster_id))
        range_id = _create_range(first, cluster_id, "10.0.0.1", "10.0.0.10")

        results: dict[str, object] = {}

        def worker(key: str, client: TestClient) -> None:
            response = client.post(
                AUTO,
                json={
                    "network_interface_id": nic_id,
                    "ip_address_range_id": range_id,
                },
            )
            results[key] = (response.status_code, response.json())

        threads = [
            threading.Thread(target=worker, args=("a", first)),
            threading.Thread(target=worker, args=("b", second)),
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=30)
        assert all(not thread.is_alive() for thread in threads)

        statuses = sorted(code for code, _ in results.values())
        assert statuses == [201, 409], results
        loser = next(body for code, body in results.values() if code == 409)
        assert loser["error"]["code"] == "CONFLICT"
        assert loser["error"]["details"][0]["code"] == "DUPLICATE"

        with psycopg.connect(raw_connection_dsn(database_url)) as conn:
            conn.autocommit = True
            active = conn.execute(
                "SELECT count(*) FROM ip_addresses WHERE deleted_at IS NULL"
            ).fetchone()[0]
            assert active == 1
            assert find_drift(conn) == []


def test_ac25_concurrent_auto_and_manual_same_address_at_most_one_succeeds(database_url):
    with _isolated_clients(database_url) as (first, second):
        cluster_id = _create_cluster(first, "cluster-a")
        nic_id = _create_nic(first, _create_bm(first, cluster_id))
        range_id = _create_range(first, cluster_id, "10.0.0.1", "10.0.0.10")

        results: dict[str, object] = {}

        def do_auto(client: TestClient) -> None:
            response = client.post(
                AUTO,
                json={
                    "network_interface_id": nic_id,
                    "ip_address_range_id": range_id,
                },
            )
            results["auto"] = (response.status_code, response.json())

        def do_manual(client: TestClient) -> None:
            response = client.post(
                MANUAL, json={"network_interface_id": nic_id, "ip_address": "10.0.0.1"}
            )
            results["manual"] = (response.status_code, response.json())

        threads = [
            threading.Thread(target=do_auto, args=(first,)),
            threading.Thread(target=do_manual, args=(second,)),
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=30)
        assert all(not thread.is_alive() for thread in threads)

        statuses = sorted(code for code, _ in results.values())
        assert statuses == [201, 409], results
        loser = next(body for code, body in results.values() if code == 409)
        assert loser["error"]["code"] == "CONFLICT"
        assert loser["error"]["details"][0]["code"] == "DUPLICATE"

        with psycopg.connect(raw_connection_dsn(database_url)) as conn:
            conn.autocommit = True
            active = conn.execute(
                "SELECT count(*) FROM ip_addresses WHERE deleted_at IS NULL"
            ).fetchone()[0]
            assert active == 1