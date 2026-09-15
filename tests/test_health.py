"""T14 — ``GET /api/health`` → 200（AC-02，含轻量数据库探测）。"""

from __future__ import annotations


def test_health_returns_ok_with_database(app_client):
    response = app_client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok"}


def test_health_returns_internal_error_when_database_unreachable(offline_client):
    response = offline_client.get("/api/health")
    assert response.status_code == 500
    assert response.json()["error"]["code"] == "INTERNAL_ERROR"
