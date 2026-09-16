"""F015 T-01 ~ T-04：生产信息面关闭与认证边界（AC-05 / AC-06）。

T-01：``environment="prod"`` 下 ``/docs`` / ``/redoc`` / ``/openapi.json`` 均不可达。
T-02：``environment="dev"`` 下能力保留（变更被 ``prod`` 条件限定）。
T-03：认证边界与 ``/api/health`` 不变（F013 AC-01 / AC-13 不回归）。
T-04：无 dev-only 自检面、无 ``/api`` 之外的产品路由。
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.auth.middleware import EXEMPT
from app.config import Settings
from app.main import create_app
from tests.conftest import OFFLINE_DSN


def _client(environment: str) -> TestClient:
    app = create_app(Settings(environment=environment, database_url=OFFLINE_DSN))
    return TestClient(app, raise_server_exceptions=False)


# --------------------------------------------------------------------------- #
# T-01 / T-02
# --------------------------------------------------------------------------- #
def test_t01_prod_framework_docs_are_not_reachable():
    with _client("prod") as client:
        for path in ("/docs", "/redoc", "/openapi.json"):
            response = client.get(path)
            assert response.status_code == 404, (path, response.status_code, response.text)


def test_t02_dev_framework_docs_remain_available():
    with _client("dev") as client:
        response = client.get("/openapi.json")
        assert response.status_code == 200
        body = response.json()
        assert "paths" in body
        assert "/api/health" in body["paths"]


# --------------------------------------------------------------------------- #
# T-03：认证边界（未认证客户端 / 已认证客户端分别验证，避免夹具互相重置）
# --------------------------------------------------------------------------- #
def test_t03_unauthenticated_health_and_clusters_are_401(app_client):
    health = app_client.get("/api/health")
    assert health.status_code == 401
    assert health.json()["error"]["code"] == "UNAUTHENTICATED"

    clusters = app_client.get("/api/clusters")
    assert clusters.status_code == 401
    assert clusters.json()["error"]["code"] == "UNAUTHENTICATED"
    assert "items" not in clusters.text


def test_t03_authenticated_health_is_ok(auth_client):
    response = auth_client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok"}


def test_t03_exempt_set_is_unchanged():
    assert EXEMPT == {("POST", "/api/auth/login")}


# --------------------------------------------------------------------------- #
# T-04：无 dev-only 自检面 / 产品路由全在 /api 下
# --------------------------------------------------------------------------- #
def test_t04_no_dev_only_surface_and_product_routes_under_api():
    app = create_app(Settings(environment="dev", database_url=OFFLINE_DSN))
    for route in app.routes:
        assert "_foundation" not in (getattr(route, "path", None) or "")
    for path in app.openapi()["paths"]:
        assert path.startswith("/api"), f"产品路由必须在 /api 下：{path}"


@pytest.mark.parametrize("path", ["/docs", "/redoc", "/openapi.json", "/healthz"])
def test_t04_no_extra_http_probe_surface_in_prod(path):
    with _client("prod") as client:
        assert client.get(path).status_code == 404
