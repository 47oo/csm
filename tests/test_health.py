"""T14 / T-12 — ``GET /api/health`` 的认证行为（AC-02 / AC-13）。

F013 后 ``/api/health`` **不豁免**：
- 未认证 → ``401 UNAUTHENTICATED``；
- 已认证 → ``200 {"status":"ok","database":"ok"}``（F012 AC-02 仍成立）；
- 已认证且数据库不可达 → ``500 INTERNAL_ERROR``。
"""

from __future__ import annotations


def test_health_requires_authentication(app_client):
    response = app_client.get("/api/health")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHENTICATED"


def test_health_returns_ok_with_database(auth_client):
    response = auth_client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok"}


def test_health_returns_internal_error_when_database_unreachable(auth_client):
    class _BrokenEngine:
        def connect(self):  # pragma: no cover - 一定抛错
            raise RuntimeError("database unreachable")

    # 只替换健康检查使用的 engine；认证会话工厂仍绑定原 engine。
    auth_client.app.state.engine = _BrokenEngine()

    response = auth_client.get("/api/health")
    assert response.status_code == 500
    assert response.json()["error"]["code"] == "INTERNAL_ERROR"
