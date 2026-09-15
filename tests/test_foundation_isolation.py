"""T13 — 生产配置不挂载非产品自检面 ``/_foundation/*``（返回 404）。"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from tests.conftest import OFFLINE_DSN, _client


@pytest.fixture
def prod_client():
    with _client("prod", OFFLINE_DSN) as client:
        yield client


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", "/_foundation/clusters"),
        ("POST", "/_foundation/clusters"),
        ("GET", "/_foundation/clusters/1"),
        ("PATCH", "/_foundation/clusters/1"),
        ("DELETE", "/_foundation/clusters/1"),
        ("GET", "/_foundation/error"),
    ],
)
def test_foundation_face_not_mounted_in_prod(prod_client: TestClient, method: str, path: str):
    response = prod_client.request(method, path, json={"name": "x"})
    assert response.status_code == 404, f"{method} {path} 在生产配置下必须 404"
    assert response.json()["error"]["code"] == "NOT_FOUND"


def test_health_available_in_prod(prod_client: TestClient):
    """health 是产品端点，生产也必须存在（探测失败返回 500，但路由存在）。"""
    response = prod_client.get("/api/health")
    assert response.status_code == 500  # DSN 不可达；路由存在即 500 而非 404
    assert response.json()["error"]["code"] == "INTERNAL_ERROR"
