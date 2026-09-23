"""F023 回归测试：自动分配必须显式指定一个活跃范围段。

覆盖修订后契约 ``docs/api/f021-ip-address-allocation.md`` §3.1 / §4.6 / §6.1：

- 缺 / 非整数 / ``null`` ``ip_address_range_id`` → ``400`` + ``details[].field``，无写入；
- 范围段不存在 → ``404`` + ``IP_ADDRESS_RANGE_UNAVAILABLE``，无写入；
- 范围段已逻辑删除 → ``404`` + 同 code，无写入；
- 范围段活跃但属于其它 Cluster → ``409`` + 同 code，且与 NIC ``404``（``details == []``）可区分；
- 多活跃范围段：仅在所选段内取最小未占用；不选未选段里更小的值；跳过所选段内已占用；
- 所选段耗尽 → ``409 NO_AVAILABLE_IP``，不回退、无写入。

夹具与辅助函数复用 ``tests/test_ip_allocations_api.py``，避免重复实现。
"""

from __future__ import annotations

import pytest

from tests.test_ip_allocations_api import (
    AUTO,
    _auto,
    _create_bm,
    _create_cluster,
    _create_ip,
    _create_nic,
    _create_range,
    _total_ip_count,
)


# --------------------------------------------------------------------------- #
# §3.1：缺 / 非整数 / null ip_address_range_id → 400，无写入
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("value", ["MISSING", "abc", None, 1.5])
def test_f023_missing_or_invalid_range_id_is_400(auth_client_and_raw, value):
    client, conn = auth_client_and_raw
    cluster_id = _create_cluster(client, "cluster-a")
    nic_id = _create_nic(client, _create_bm(client, cluster_id))
    payload: dict = {"network_interface_id": nic_id}
    if value != "MISSING":
        payload["ip_address_range_id"] = value

    response = client.post(AUTO, json=payload)
    assert response.status_code == 400, response.text
    body = response.json()
    assert body["error"]["code"] == "VALIDATION_ERROR"
    assert any(
        detail["field"] == "ip_address_range_id"
        for detail in body["error"]["details"]
    ), body
    assert _total_ip_count(conn) == 0


# --------------------------------------------------------------------------- #
# §4.6：范围段不存在 → 404 + IP_ADDRESS_RANGE_UNAVAILABLE，无写入
# --------------------------------------------------------------------------- #
def test_f023_nonexistent_range_is_404(auth_client_and_raw):
    client, conn = auth_client_and_raw
    cluster_id = _create_cluster(client, "cluster-a")
    nic_id = _create_nic(client, _create_bm(client, cluster_id))

    response = _auto(client, nic_id, 999999999)
    assert response.status_code == 404, response.text
    body = response.json()
    assert body["error"]["code"] == "NOT_FOUND"
    detail = body["error"]["details"][0]
    assert detail["field"] == "ip_address_range_id"
    assert detail["code"] == "IP_ADDRESS_RANGE_UNAVAILABLE"
    assert _total_ip_count(conn) == 0


# --------------------------------------------------------------------------- #
# §4.6：范围段已逻辑删除 → 404 + 同 code，无写入
# --------------------------------------------------------------------------- #
def test_f023_soft_deleted_range_is_404(auth_client_and_raw):
    client, conn = auth_client_and_raw
    cluster_id = _create_cluster(client, "cluster-a")
    nic_id = _create_nic(client, _create_bm(client, cluster_id))
    range_id = _create_range(client, cluster_id, "10.0.0.1", "10.0.0.255")
    assert client.delete(f"/api/ip-address-ranges/{range_id}").status_code == 204

    response = _auto(client, nic_id, range_id)
    assert response.status_code == 404, response.text
    body = response.json()
    assert body["error"]["code"] == "NOT_FOUND"
    detail = body["error"]["details"][0]
    assert detail["field"] == "ip_address_range_id"
    assert detail["code"] == "IP_ADDRESS_RANGE_UNAVAILABLE"
    assert _total_ip_count(conn) == 0


# --------------------------------------------------------------------------- #
# §4.6：范围段活跃但属于其它 Cluster → 409 + 同 code；与 NIC 404 可区分
# --------------------------------------------------------------------------- #
def test_f023_other_cluster_range_is_409(auth_client_and_raw):
    client, conn = auth_client_and_raw
    cluster_a = _create_cluster(client, "cluster-a")
    cluster_b = _create_cluster(client, "cluster-b")
    nic_a = _create_nic(client, _create_bm(client, cluster_a))
    range_b = _create_range(client, cluster_b, "10.0.0.1", "10.0.0.255")

    response = _auto(client, nic_a, range_b)
    assert response.status_code == 409, response.text
    body = response.json()
    assert body["error"]["code"] == "CONFLICT"
    detail = body["error"]["details"][0]
    assert detail["field"] == "ip_address_range_id"
    assert detail["code"] == "IP_ADDRESS_RANGE_UNAVAILABLE"
    assert _total_ip_count(conn) == 0

    # 与「目标 NIC 不存在」的 404（details == []）通过 details[].code 区分。
    nic_404 = _auto(client, 999999999, range_b)
    assert nic_404.status_code == 404
    assert nic_404.json()["error"]["details"] == []


# --------------------------------------------------------------------------- #
# §6.1：仅在所选段内取最小未占用；不选未选段更小值；跳过所选段内已占用
# --------------------------------------------------------------------------- #
def test_f023_selected_range_min_ignores_unselected_and_skips_occupied(
    auth_client_and_raw,
):
    client, conn = auth_client_and_raw
    cluster_id = _create_cluster(client, "cluster-a")
    nic_id = _create_nic(client, _create_bm(client, cluster_id))
    low = _create_range(client, cluster_id, "10.0.0.1", "10.0.0.3")
    high = _create_range(client, cluster_id, "10.0.0.10", "10.0.0.12")

    # 所选 high 段内占用 10.0.0.10 → 取下一个 10.0.0.11；
    # 不取未选 low 段里更小的 10.0.0.1。
    _create_ip(client, nic_id, "10.0.0.10")
    selected_high = _auto(client, nic_id, high)
    assert selected_high.status_code == 201, selected_high.text
    assert selected_high.json()["ip_address"] == "10.0.0.11"

    # 换选 low 段 → 取该段内最小未占用 10.0.0.1。
    selected_low = _auto(client, nic_id, low)
    assert selected_low.status_code == 201, selected_low.text
    assert selected_low.json()["ip_address"] == "10.0.0.1"


# --------------------------------------------------------------------------- #
# §4.1：所选段耗尽 → 409 NO_AVAILABLE_IP，不回退、无写入
# --------------------------------------------------------------------------- #
def test_f023_exhausted_selected_range_is_409_without_fallback(auth_client_and_raw):
    client, conn = auth_client_and_raw
    cluster_id = _create_cluster(client, "cluster-a")
    nic_id = _create_nic(client, _create_bm(client, cluster_id))
    full = _create_range(client, cluster_id, "10.0.0.10", "10.0.0.11")
    # 另一活跃范围段仍有可用地址，但未被选择 → 不得回退过去。
    _create_range(client, cluster_id, "10.0.0.1", "10.0.0.3")
    _create_ip(client, nic_id, "10.0.0.10")
    _create_ip(client, nic_id, "10.0.0.11")
    before = _total_ip_count(conn)

    response = _auto(client, nic_id, full)
    assert response.status_code == 409, response.text
    body = response.json()
    assert body["error"]["code"] == "CONFLICT"
    assert body["error"]["details"][0]["code"] == "NO_AVAILABLE_IP"
    assert body["error"]["details"][0]["field"] is None
    assert _total_ip_count(conn) == before