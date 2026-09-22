"""F022 补充独立测试：DB 兜底路径（绕过应用层 name 预检）→ 23505 → 409 DUPLICATE。

契约 §4.2 明确记录：应用层预检先行，partial unique index 为最终权威；绕过预检写入
同 Cluster 活跃同名 name 时触发 SQLSTATE ``23505``，经既有 ``app/common/sqlstate.py``
通用映射返回 ``409 CONFLICT`` + ``details[].code = "DUPLICATE"``，**永不 500**。

本文件由 Tester 为 F022 Stage 5 独立验收补充（Architecture Test Work「`23505` …
→ 409，永不 500」），不改动任何生产实现。
"""

from __future__ import annotations


def _cluster(client, name: str) -> int:
    response = client.post("/api/clusters", json={"name": name})
    assert response.status_code == 201, response.text
    return response.json()["id"]


def _create(client, cluster_id: int, start: str, end: str, **meta):
    return client.post(
        "/api/ip-address-ranges",
        json={"cluster_id": cluster_id, "start_ip": start, "end_ip": end, **meta},
    )


def test_db_fallback_duplicate_name_maps_to_409(auth_client_and_raw, monkeypatch):
    client, _ = auth_client_and_raw
    cluster_id = _cluster(client, "fb-dup")
    assert _create(client, cluster_id, "10.0.0.1", "10.0.0.10", name="业务网").status_code == 201

    # 绕过应用层友好预检，迫使 partial unique index 成为唯一防线。
    monkeypatch.setattr(
        "app.ip_address_ranges.repository.IpAddressRangeRepository.active_name_exists",
        lambda *args, **kwargs: False,
    )
    response = _create(client, cluster_id, "10.0.0.20", "10.0.0.30", name="业务网")
    assert response.status_code == 409, response.text
    error = response.json()["error"]
    assert error["code"] == "CONFLICT"
    assert any(detail.get("code") == "DUPLICATE" for detail in error["details"])
    assert response.status_code != 500


def test_db_fallback_vlan_check_via_application_returns_400(auth_client_and_raw):
    """正常路径：应用层 VLAN 校验先于 DB，越界 → 400 且无写入。"""
    client, _ = auth_client_and_raw
    cluster_id = _cluster(client, "fb-vlan")

    response = _create(client, cluster_id, "10.1.0.1", "10.1.0.10", vlan=0)
    assert response.status_code == 400, response.text
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
