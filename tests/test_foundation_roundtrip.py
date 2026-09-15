"""T9 — 非产品自检面 create → list → get → update → soft-delete 往返。

属**非产品**验证面（架构判据 5）；不含任何 Cluster 领域规则。
"""

from __future__ import annotations


def test_foundation_crud_roundtrip(app_client):
    # create
    created = app_client.post("/_foundation/clusters", json={"name": "cluster-a"})
    assert created.status_code == 201
    body = created.json()
    assert body["name"] == "cluster-a"
    assert isinstance(body["id"], int)
    assert "deleted_at" not in body  # 不对外暴露
    cluster_id = body["id"]

    # list
    listed = app_client.get("/_foundation/clusters")
    assert listed.status_code == 200
    page = listed.json()
    assert page["total"] == 1
    assert page["page"] == 1
    assert page["page_size"] == 50
    assert [item["id"] for item in page["items"]] == [cluster_id]

    # get
    fetched = app_client.get(f"/_foundation/clusters/{cluster_id}")
    assert fetched.status_code == 200
    assert fetched.json()["name"] == "cluster-a"

    # update
    updated = app_client.patch(f"/_foundation/clusters/{cluster_id}", json={"name": "cluster-b"})
    assert updated.status_code == 200
    assert updated.json()["name"] == "cluster-b"

    # soft-delete
    deleted = app_client.delete(f"/_foundation/clusters/{cluster_id}")
    assert deleted.status_code == 204

    # 删除后不再出现在 list
    relisted = app_client.get("/_foundation/clusters")
    assert relisted.json()["items"] == []
    assert relisted.json()["total"] == 0

    # 已删不可 get → 404 NOT_FOUND
    missing = app_client.get(f"/_foundation/clusters/{cluster_id}")
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "NOT_FOUND"


def test_empty_list_is_200_with_empty_items(app_client):
    response = app_client.get("/_foundation/clusters")
    assert response.status_code == 200
    assert response.json()["items"] == []


def test_unknown_id_returns_404_not_found(app_client):
    response = app_client.get("/_foundation/clusters/999999")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


def test_active_duplicate_returns_409_conflict(app_client):
    """通用 SQLSTATE 23505 → 409 CONFLICT + details[].field == name。"""
    assert app_client.post("/_foundation/clusters", json={"name": "dup"}).status_code == 201
    response = app_client.post("/_foundation/clusters", json={"name": "dup"})
    assert response.status_code == 409
    body = response.json()
    assert body["error"]["code"] == "CONFLICT"
    assert any(detail["field"] == "name" for detail in body["error"]["details"])


def test_slash_name_returns_400_validation_error(app_client):
    """通用 SQLSTATE 23514 → 400 VALIDATION_ERROR（不得是 500）。"""
    response = app_client.post("/_foundation/clusters", json={"name": "a/b"})
    assert response.status_code == 400
    body = response.json()
    assert body["error"]["code"] == "VALIDATION_ERROR"
    assert any(detail["field"] == "name" for detail in body["error"]["details"])


def test_chinese_name_roundtrip_through_api(app_client):
    """T7（应用侧）— 中文经 HTTP 写入 / 读出 / 等值命中。"""
    name = "高性能计算集群-A"
    created = app_client.post("/_foundation/clusters", json={"name": name})
    assert created.status_code == 201
    assert created.json()["name"] == name

    listed = app_client.get("/_foundation/clusters")
    assert [item["name"] for item in listed.json()["items"]] == [name]
