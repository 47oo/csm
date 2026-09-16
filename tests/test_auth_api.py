"""F013 认证边界 / 登录 / 会话 API 测试（T-01 ~ T-16、G-A、G-B）。

映射 Architecture Handoff Test Work 表。需要数据库的用例使用 ``*_and_raw`` 夹具，
其中 raw psycopg 连接**绕过应用层**，用于直接断言 / 预置数据库状态。
"""

from __future__ import annotations

import logging

import pytest
from fastapi.testclient import TestClient

from app.auth import tokens
from app.auth.passwords import hash_password
from tests.conftest import (
    AUTH_PASSWORD,
    AUTH_USERNAME,
    OFFLINE_DSN,
    create_user,
    login,
)

# --------------------------------------------------------------------------- #
# T-01 / AC-01 / AC-12：未认证访问全部 5 个 /api/clusters* 端点 → 401
# --------------------------------------------------------------------------- #
CLUSTER_ENDPOINTS = [
    ("GET", "/api/clusters", None),
    ("POST", "/api/clusters", {"name": "x"}),
    ("GET", "/api/clusters/1", None),
    ("GET", "/api/clusters/by-name/x", None),
    ("PATCH", "/api/clusters/1", {"name": "x"}),
]


@pytest.mark.parametrize(("method", "path", "payload"), CLUSTER_ENDPOINTS)
def test_t01_unauthenticated_cluster_endpoints_return_401(offline_client, method, path, payload):
    response = offline_client.request(method, path, json=payload)
    assert response.status_code == 401, f"{method} {path} 应 401，实际 {response.status_code}"
    assert response.status_code not in (404, 405, 500)
    body = response.json()
    assert body["error"]["code"] == "UNAUTHENTICATED"
    assert body["error"]["details"] == []
    assert body.keys() == {"error"}


# --------------------------------------------------------------------------- #
# T-02 / AC-02：登录后可读可写
# --------------------------------------------------------------------------- #
def test_t02_authenticated_client_can_read_and_write(auth_client):
    assert auth_client.get("/api/clusters").status_code == 200

    created = auth_client.post("/api/clusters", json={"name": "authed-cluster"})
    assert created.status_code == 201
    cluster_id = created.json()["id"]

    patched = auth_client.patch(f"/api/clusters/{cluster_id}", json={"name": "renamed"})
    assert patched.status_code == 200
    assert patched.json()["name"] == "renamed"


# --------------------------------------------------------------------------- #
# T-03 / AC-03 / R-AUTH-006：用户名不存在 与 口令错误 逐字节相同
# --------------------------------------------------------------------------- #
def test_t03_unknown_user_and_wrong_password_are_byte_identical(app_client_and_raw, database_url):
    client, conn = app_client_and_raw
    create_user(database_url, "victim", "victim-password-1")

    wrong = client.post(
        "/api/auth/login", json={"username": "victim", "password": "wrong-password-1"}
    )
    missing = client.post(
        "/api/auth/login", json={"username": "ghost", "password": "wrong-password-1"}
    )

    assert wrong.status_code == missing.status_code == 401
    assert wrong.content == missing.content
    assert wrong.json()["error"]["code"] == "UNAUTHENTICATED"
    assert wrong.json()["error"]["details"] == []
    assert "set-cookie" not in {key.lower() for key in wrong.headers}
    assert "set-cookie" not in {key.lower() for key in missing.headers}

    # 不建立任何会话
    assert conn.execute("SELECT count(*) FROM sessions").fetchone()[0] == 0
    assert client.get("/api/clusters").status_code == 401


# --------------------------------------------------------------------------- #
# T-04 / AC-07 / R-AUTH-006：账号停用 与 T-03 完全相同
# --------------------------------------------------------------------------- #
def test_t04_disabled_account_login_is_identical(app_client_and_raw, database_url):
    client, conn = app_client_and_raw
    create_user(database_url, "victim", "victim-password-1")
    create_user(database_url, "disabled", "disabled-password-1", active=False)

    wrong = client.post(
        "/api/auth/login", json={"username": "victim", "password": "wrong-password-1"}
    )
    disabled = client.post(
        "/api/auth/login",
        json={"username": "disabled", "password": "disabled-password-1"},
    )

    assert wrong.status_code == disabled.status_code == 401
    assert wrong.content == disabled.content
    assert disabled.json()["error"]["code"] == "UNAUTHENTICATED"
    assert conn.execute("SELECT count(*) FROM sessions").fetchone()[0] == 0


# --------------------------------------------------------------------------- #
# T-05 / AC-04：登出使会话失效；重复登出 401
# --------------------------------------------------------------------------- #
def test_t05_logout_invalidates_session(auth_client):
    assert auth_client.get("/api/clusters").status_code == 200

    response = auth_client.post("/api/auth/logout")
    assert response.status_code == 204
    assert "max-age=0" in response.headers.get("set-cookie", "").lower()

    assert auth_client.get("/api/clusters").status_code == 401
    assert auth_client.post("/api/auth/logout").status_code == 401


# --------------------------------------------------------------------------- #
# T-06：GET /api/auth/session 已认证 200 / 未认证 401
# --------------------------------------------------------------------------- #
def test_t06_session_endpoint(auth_client, offline_client):
    response = auth_client.get("/api/auth/session")
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"id", "username"}
    assert body["username"] == AUTH_USERNAME

    assert offline_client.get("/api/auth/session").status_code == 401


# --------------------------------------------------------------------------- #
# T-07 / AC-07：绕应用层停用账号 → 既有会话立即失效
# --------------------------------------------------------------------------- #
def test_t07_disabling_account_invalidates_existing_session(auth_client_and_raw):
    client, conn = auth_client_and_raw
    assert client.get("/api/clusters").status_code == 200

    conn.execute("UPDATE users SET active = FALSE WHERE username = %s", (AUTH_USERNAME,))

    assert client.get("/api/clusters").status_code == 401
    assert client.get("/api/auth/session").status_code == 401


# --------------------------------------------------------------------------- #
# T-08 / AC-08：不存在未认证可达的注册 / 建号入口
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    ("method", "path", "payload"),
    [
        ("POST", "/api/auth/register", {"username": "x", "password": "y"}),
        ("POST", "/api/users", {"username": "x"}),
        ("POST", "/api/auth/signup", {"username": "x"}),
    ],
)
def test_t08_no_registration_endpoint(offline_client, method, path, payload):
    response = offline_client.request(method, path, json=payload)
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHENTICATED"


# --------------------------------------------------------------------------- #
# T-10 / AC-10：无明文泄露
# --------------------------------------------------------------------------- #
def test_t10_hash_prefix_and_no_plaintext_in_db(app_client_and_raw, database_url):
    client, conn = app_client_and_raw
    password = "plain-secret-123"
    create_user(database_url, "logtest", password)

    stored = conn.execute("SELECT password_hash FROM users WHERE username = 'logtest'").fetchone()[
        0
    ]
    assert stored.startswith("$argon2id$")
    assert password not in stored
    # 全表不存在明文口令
    all_hashes = [row[0] for row in conn.execute("SELECT password_hash FROM users").fetchall()]
    assert all(password not in row for row in all_hashes)


def test_t10_no_plaintext_in_logs_or_short_password_response(
    app_client_and_raw, database_url, caplog
):
    client, _ = app_client_and_raw
    password = "log-secret-9999"
    create_user(database_url, "logtest", password)

    with caplog.at_level(logging.DEBUG):
        client.post("/api/auth/login", json={"username": "logtest", "password": password})
        client.post("/api/auth/login", json={"username": "logtest", "password": "wrong-value-xyz"})

    messages = " ".join(record.getMessage() for record in caplog.records)
    assert password not in messages
    assert "wrong-value-xyz" not in messages

    # 短口令（登录路径不校验长度）→ 统一 401，响应体不回显口令值
    short = client.post("/api/auth/login", json={"username": "logtest", "password": "1234567"})
    assert short.status_code == 401
    assert "1234567" not in short.text


# --------------------------------------------------------------------------- #
# T-12（补充）：/api 根路径未认证 401
# --------------------------------------------------------------------------- #
def test_t12_api_root_requires_auth(offline_client):
    assert offline_client.get("/api").status_code == 401


# --------------------------------------------------------------------------- #
# T-14 / AC-15：大小写敏感登录匹配（DB 侧断言见 tests/database/test_auth_schema.py）
# --------------------------------------------------------------------------- #
def test_t14_username_case_sensitive_login(app_client_and_raw, database_url):
    client, conn = app_client_and_raw
    create_user(database_url, "admin", "admin-password-1")
    conn.execute(
        "INSERT INTO users (username, password_hash) VALUES ('Admin', %s)",
        (hash_password("Admin-password-1"),),
    )

    # 用 Admin 的凭证登录 admin 账号 → 失败（原样精确匹配）
    mismatch = client.post(
        "/api/auth/login", json={"username": "Admin", "password": "admin-password-1"}
    )
    assert mismatch.status_code == 401

    matched = client.post(
        "/api/auth/login", json={"username": "admin", "password": "admin-password-1"}
    )
    assert matched.status_code == 200
    assert matched.json()["username"] == "admin"


# --------------------------------------------------------------------------- #
# T-15：Cookie 属性
# --------------------------------------------------------------------------- #
def test_t15_cookie_attributes(app_client_and_raw, database_url):
    client, _ = app_client_and_raw
    create_user(database_url, "cookie-user", "cookie-password-1")

    response = client.post(
        "/api/auth/login", json={"username": "cookie-user", "password": "cookie-password-1"}
    )
    assert response.status_code == 200

    set_cookie = response.headers["set-cookie"]
    lowered = set_cookie.lower()
    assert "httponly" in lowered
    assert "samesite=lax" in lowered
    assert "path=/api" in lowered
    assert "max-age=28800" in lowered
    assert "secure" not in lowered
    assert "domain" not in lowered

    # 令牌值不出现在响应体
    assert "csm_session=" not in response.text


# --------------------------------------------------------------------------- #
# T-16：会话生命周期 —— 过期会话被拒绝；登录成功惰性清理
# --------------------------------------------------------------------------- #
def test_t16_expired_session_rejected_and_lazily_cleaned(app_client_and_raw, database_url):
    client, conn = app_client_and_raw
    user_id = create_user(database_url, "expired-user", "expired-password-1")

    token = tokens.generate_session_token()
    conn.execute(
        "INSERT INTO sessions (user_id, token_hash, expires_at) "
        "VALUES (%s, %s, now() - interval '1 hour')",
        (user_id, tokens.hash_session_token(token)),
    )

    client.cookies.set("csm_session", token)
    assert client.get("/api/clusters").status_code == 401

    client.cookies.clear()
    login(client, "expired-user", "expired-password-1")

    expired_left = conn.execute(
        "SELECT count(*) FROM sessions WHERE user_id = %s AND expires_at <= now()",
        (user_id,),
    ).fetchone()[0]
    assert expired_left == 0
    assert client.get("/api/clusters").status_code == 200


# --------------------------------------------------------------------------- #
# G-A：唯一豁免 guard
# --------------------------------------------------------------------------- #
def test_g_a_exempt_set_is_exactly_login(offline_client):
    from app.auth.middleware import EXEMPT

    assert EXEMPT == {("POST", "/api/auth/login")}

    # GET 登录端点 / 尾斜杠 / 未知 /api 路径 → 401（fail-closed）
    assert offline_client.get("/api/auth/login").status_code == 401
    assert offline_client.post("/api/auth/login/").status_code == 401
    assert offline_client.get("/api/auth/login/").status_code == 401
    assert offline_client.get("/api/auth/does-not-exist").status_code == 401


# --------------------------------------------------------------------------- #
# G-B：新端点自动受保护
# --------------------------------------------------------------------------- #
def test_g_b_newly_added_endpoint_is_protected():
    from fastapi import APIRouter

    from app.config import Settings
    from app.main import create_app

    app = create_app(Settings(environment="dev", database_url=OFFLINE_DSN))

    probe = APIRouter()

    @probe.get("/__probe__")
    def _probe() -> dict[str, bool]:  # pragma: no cover - 只在认证后被调用
        return {"ok": True}

    app.include_router(probe, prefix="/api")

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/api/__probe__")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHENTICATED"


# --------------------------------------------------------------------------- #
# 登录请求体校验（400 仅取决于请求体是否合法，不泄露账号是否存在）
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "payload", [{}, {"username": "u"}, {"password": "p"}, {"username": 1, "password": "p"}]
)
def test_login_body_validation(app_client_and_raw, payload):
    client, _ = app_client_and_raw
    response = client.post("/api/auth/login", json=payload)
    assert response.status_code == 400
    body = response.json()
    assert body["error"]["code"] == "VALIDATION_ERROR"
    assert body["error"]["details"]
    assert "set-cookie" not in {key.lower() for key in response.headers}


def test_login_success_does_not_leak_token_in_body(app_client_and_raw, database_url):
    client, conn = app_client_and_raw
    create_user(database_url, "token-user", "token-password-1")

    response = client.post(
        "/api/auth/login", json={"username": "token-user", "password": "token-password-1"}
    )
    assert response.status_code == 200
    assert set(response.json()) == {"id", "username"}

    # 数据库只存哈希，不存令牌原文
    raw_token = client.cookies.get("csm_session")
    stored = conn.execute("SELECT token_hash FROM sessions").fetchone()[0]
    assert stored != raw_token
    assert stored == tokens.hash_session_token(raw_token)
    assert AUTH_PASSWORD not in response.text
