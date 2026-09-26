"""认证与会话集成测试（场景 72–74、78 自助部分、首登改密强制）。"""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.db import SessionLocal
from app.main import app
from app.models import UserSession


def _session_count() -> int:
    with SessionLocal() as db:
        return db.scalar(select(func.count()).select_from(UserSession)) or 0


def test_scenario_72_login_success_and_failure(client, add_user, login_as) -> None:
    add_user("alice", "Passw0rd", "viewer")

    ok = login_as(client, "alice", "Passw0rd")
    assert ok.status_code == 200
    body = ok.json()
    assert body["username"] == "alice"
    assert body["role"] == "viewer"
    assert body["status"] == "enabled"
    assert body["must_change_password"] is False
    assert "csm_session" in client.cookies

    me = client.get("/api/v1/auth/me")
    assert me.status_code == 200
    assert me.json()["username"] == "alice"

    assert _session_count() == 1


def test_scenario_72_unknown_and_wrong_password_no_session(client, add_user) -> None:
    add_user("alice", "Passw0rd", "viewer")

    unknown = client.post(
        "/api/v1/auth/login", json={"username": "nobody", "password": "whatever1"}
    )
    assert unknown.status_code == 401
    assert unknown.json()["code"] == "INVALID_CREDENTIALS"
    assert unknown.headers["content-type"].startswith("application/problem+json")

    wrong = client.post(
        "/api/v1/auth/login", json={"username": "alice", "password": "Wrongp0ss"}
    )
    assert wrong.status_code == 401
    assert wrong.json()["code"] == "INVALID_CREDENTIALS"

    assert _session_count() == 0
    assert client.get("/api/v1/auth/me").status_code == 401


def test_scenario_72_validation_error(client) -> None:
    resp = client.post("/api/v1/auth/login", json={"username": "x"})
    assert resp.status_code == 422
    body = resp.json()
    assert body["code"] == "VALIDATION_ERROR"
    assert body["errors"]


def test_scenario_73_disabled_account_cannot_login(client, add_user) -> None:
    add_user("bob", "Passw0rd", "viewer", status="disabled")

    resp = client.post(
        "/api/v1/auth/login", json={"username": "bob", "password": "Passw0rd"}
    )
    assert resp.status_code == 403
    assert resp.json()["code"] == "ACCOUNT_DISABLED"
    assert _session_count() == 0


def test_scenario_74_logout_invalidates_session(client, add_user, login_as) -> None:
    add_user("carol", "Passw0rd", "viewer")
    assert login_as(client, "carol", "Passw0rd").status_code == 200
    assert client.get("/api/v1/auth/me").status_code == 200

    logout = client.post("/api/v1/auth/logout")
    assert logout.status_code == 204
    assert client.get("/api/v1/auth/me").status_code == 401

    # 幂等：无会话再登出仍 204。
    assert client.post("/api/v1/auth/logout").status_code == 204

    with SessionLocal() as db:
        session = db.scalar(select(UserSession))
        assert session is not None
        assert session.revoked_at is not None


def test_first_login_password_change_enforced(client, add_user, login_as) -> None:
    add_user("root", "Initial1", "admin", must_change=True)

    login = login_as(client, "root", "Initial1")
    assert login.status_code == 200
    assert login.json()["must_change_password"] is True

    # 除 me / change-password / logout 外被拦截。
    blocked = client.get("/api/v1/users")
    assert blocked.status_code == 403
    assert blocked.json()["code"] == "PASSWORD_CHANGE_REQUIRED"
    assert client.get("/api/v1/auth/me").status_code == 200

    # 当前口令错误。
    bad_current = client.post(
        "/api/v1/auth/change-password",
        json={"current_password": "Nope1234", "new_password": "Newpass12"},
    )
    assert bad_current.status_code == 400
    assert bad_current.json()["code"] == "INVALID_CURRENT_PASSWORD"

    # 新口令不满足策略。
    bad_policy = client.post(
        "/api/v1/auth/change-password",
        json={"current_password": "Initial1", "new_password": "onlyletters"},
    )
    assert bad_policy.status_code == 422
    assert bad_policy.json()["errors"][0]["code"] == "PASSWORD_POLICY"

    # 成功改密。
    ok = client.post(
        "/api/v1/auth/change-password",
        json={"current_password": "Initial1", "new_password": "Newpass12"},
    )
    assert ok.status_code == 204

    me = client.get("/api/v1/auth/me")
    assert me.status_code == 200
    assert me.json()["must_change_password"] is False
    assert client.get("/api/v1/users").status_code == 200


def test_scenario_78_self_change_password(client, add_user, login_as) -> None:
    add_user("dave", "Oldpass12", "viewer")
    assert login_as(client, "dave", "Oldpass12").status_code == 200

    resp = client.post(
        "/api/v1/auth/change-password",
        json={"current_password": "Oldpass12", "new_password": "Newpass34"},
    )
    assert resp.status_code == 204

    # 旧口令失效、新口令可登录。
    assert login_as(client, "dave", "Oldpass12").status_code == 401
    fresh = TestClient(app)
    assert login_as(fresh, "dave", "Newpass34").status_code == 200


def test_change_password_revokes_other_sessions(client, add_user, login_as) -> None:
    add_user("erin", "Oldpass12", "viewer")

    other = TestClient(app)
    assert login_as(client, "erin", "Oldpass12").status_code == 200
    assert login_as(other, "erin", "Oldpass12").status_code == 200

    assert (
        client.post(
            "/api/v1/auth/change-password",
            json={"current_password": "Oldpass12", "new_password": "Newpass34"},
        ).status_code
        == 204
    )

    # 当前会话保留，其它会话被撤销。
    assert client.get("/api/v1/auth/me").status_code == 200
    assert other.get("/api/v1/auth/me").status_code == 401