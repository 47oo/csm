"""T8 — 字段校验失败 → 400 + VALIDATION_ERROR + details[].field（AC-06）。

不访问数据库：参数 / 请求体校验在数据库访问之前完成。
"""

from __future__ import annotations


def test_missing_body_field_returns_field_level_error(offline_client):
    response = offline_client.post("/_foundation/clusters", json={})
    assert response.status_code == 400

    body = response.json()
    assert body["error"]["code"] == "VALIDATION_ERROR"
    fields = [detail["field"] for detail in body["error"]["details"]]
    assert "name" in fields


def test_wrong_type_returns_field_level_error(offline_client):
    response = offline_client.post("/_foundation/clusters", json={"name": 123})
    assert response.status_code == 400
    body = response.json()
    assert body["error"]["code"] == "VALIDATION_ERROR"
    assert any(detail["field"] == "name" for detail in body["error"]["details"])


def test_invalid_pagination_returns_field_level_error(offline_client):
    response = offline_client.get("/_foundation/clusters", params={"page": 0})
    assert response.status_code == 400
    body = response.json()
    assert body["error"]["code"] == "VALIDATION_ERROR"
    assert any(detail["field"] == "page" for detail in body["error"]["details"])

    response = offline_client.get("/_foundation/clusters", params={"page_size": 9999})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_foundation_error_endpoint_uses_envelope(offline_client):
    response = offline_client.get("/_foundation/error")
    assert response.status_code == 500
    body = response.json()
    assert body["error"]["code"] == "INTERNAL_ERROR"
    assert body["error"]["details"] == []
