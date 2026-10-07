"""F002 authentication API integration tests (TD-2 V1/V4/V5/V6/V8, B1-B14, B17).

Real PostgreSQL via the ``committed_engine`` fixtures; the app is the production
``create_app`` with only ``get_db`` overridden. The permission matrix (B11/A4)
is exercised by mounting test routes that reuse the production
``require_permission`` dependency (R1 mechanism-level evidence).
"""

from __future__ import annotations

import hashlib
import logging
import threading
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.permissions import ROLE_PERMISSIONS, Permission, Role, require_permission
from app.models.session import UserSession
from app.models.user import User

ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "admin-pass-123"


def _set_cookie_header(response) -> str:
    headers = response.headers.get_list("set-cookie")
    return next(h for h in headers if "csm_session=" in h)


# --- V1 / B1 -----------------------------------------------------------------


def test_login_success_creates_session(
    api_client, bootstrap_admin, auth_session_factory, login
):
    bootstrap_admin(ADMIN_USERNAME, ADMIN_PASSWORD)
    resp = login(ADMIN_USERNAME, ADMIN_PASSWORD)
    assert resp.status_code == 200, resp.text

    body = resp.json()
    assert body["user"]["username"] == ADMIN_USERNAME
    assert body["user"]["role"] == "ADMIN"
    assert body["user"]["status"] == "ACTIVE"
    assert body["user"]["permissions"] == sorted(
        p.value for p in ROLE_PERMISSIONS[Role.ADMIN]
    )
    assert "password_hash" not in resp.text

    cookie = _set_cookie_header(resp)
    assert "csm_session=" in cookie
    clear_token = api_client.cookies.get("csm_session")
    assert clear_token and len(clear_token) >= 40

    with auth_session_factory() as session:
        row = session.execute(select(UserSession)).scalars().one()
        assert len(row.token_hash) == 64
        assert row.token_hash != clear_token
        assert row.token_hash == hashlib.sha256(clear_token.encode()).hexdigest()
        assert datetime.fromisoformat(body["expires_at"]) == row.expires_at
        assert body["expires_at"].endswith("+00:00")
        assert row.expires_at > row.created_at


# --- B2 ----------------------------------------------------------------------


def test_login_failures_are_indistinct(bootstrap_admin, login, auth_session_factory):
    bootstrap_admin(ADMIN_USERNAME, ADMIN_PASSWORD)

    wrong_password = login(ADMIN_USERNAME, "not-the-password")
    unknown_user = login("nobody", "whatever-123")

    for resp in (wrong_password, unknown_user):
        assert resp.status_code == 401
        assert resp.json() == {
            "error": {
                "code": "AUTH_INVALID_CREDENTIALS",
                "message": "Invalid credentials",
                "details": {},
            }
        }

    with auth_session_factory() as session:
        assert session.execute(select(UserSession)).scalars().all() == []


# --- A3 / B13 ----------------------------------------------------------------


def test_no_registration_endpoint(auth_app, api_client):
    paths = {route.path for route in auth_app.routes}
    assert not any("register" in path or "signup" in path for path in paths)

    openapi = api_client.get("/api/v1/openapi.json").json()
    assert not any("register" in path or "signup" in path for path in openapi["paths"])

    for candidate in ("/api/v1/auth/register", "/api/v1/auth/signup"):
        resp = api_client.post(candidate)
        assert resp.status_code in (404, 405)
        assert resp.json()["error"]["code"] in ("NOT_FOUND", "METHOD_NOT_ALLOWED")


# --- V4 / B11 ----------------------------------------------------------------


def _mount_permission_routes(app: FastAPI) -> None:
    def endpoint():
        return {"ok": True}

    for permission in Permission:
        app.add_api_route(
            f"/_test/perm/{permission.value}",
            endpoint,
            methods=["GET"],
            dependencies=[Depends(require_permission(permission))],
        )


def test_permission_matrix_per_role(auth_app, make_user):
    _mount_permission_routes(auth_app)
    with TestClient(auth_app) as client:
        anon = client.get(f"/_test/perm/{Permission.READ.value}")
        assert anon.status_code == 401
        assert anon.json()["error"]["code"] == "AUTH_REQUIRED"

    for role in ("VIEWER", "EDITOR", "ADMIN"):
        user, password = make_user(role=role)
        with TestClient(auth_app) as client:
            login = client.post(
                "/api/v1/auth/login",
                json={"username": user.username, "password": password},
            )
            assert login.status_code == 200
            for permission in Permission:
                resp = client.get(f"/_test/perm/{permission.value}")
                allowed = permission in ROLE_PERMISSIONS[Role(role)]
                if allowed:
                    assert resp.status_code == 200, (role, permission, resp.text)
                else:
                    assert resp.status_code == 403, (role, permission, resp.text)
                    assert resp.json()["error"]["code"] == "FORBIDDEN"
                    assert resp.json()["error"]["details"] == {"reason": "permission"}


# --- V8 / B3-B6 --------------------------------------------------------------


def test_disabled_account_login_and_existing_session(
    api_client, make_user, login, auth_session_factory
):
    user, password = make_user(role="ADMIN")
    assert login(user.username, password).status_code == 200

    with auth_session_factory() as session:
        stored = session.get(User, user.id)
        stored.status = "DISABLED"
        session.commit()

    me = api_client.get("/api/v1/auth/me")
    assert me.status_code == 401
    assert me.json()["error"]["code"] == "AUTH_REQUIRED"

    relogin = login(user.username, password)
    assert relogin.status_code == 401
    assert relogin.json()["error"]["code"] == "AUTH_INVALID_CREDENTIALS"


def test_session_expiry_and_no_sliding(
    api_client, make_user, login, auth_session_factory
):
    user, password = make_user()
    assert login(user.username, password).status_code == 200

    # A request must not extend the absolute expiry.
    with auth_session_factory() as session:
        before = session.execute(select(UserSession)).scalars().one().expires_at
    assert api_client.get("/api/v1/auth/me").status_code == 200
    with auth_session_factory() as session:
        after = session.execute(select(UserSession)).scalars().one().expires_at
    assert before == after

    with auth_session_factory() as session:
        row = session.execute(select(UserSession)).scalars().one()
        # Shift both timestamps back so the CHECK expires_at > created_at holds
        # for a genuinely expired session.
        row.created_at = datetime.now(timezone.utc) - timedelta(hours=2)
        row.expires_at = datetime.now(timezone.utc) - timedelta(hours=1)
        session.commit()

    expired = api_client.get("/api/v1/auth/me")
    assert expired.status_code == 401
    assert expired.json()["error"]["code"] == "AUTH_REQUIRED"


def test_logout_deletes_session(api_client, make_user, login, auth_session_factory):
    user, password = make_user()
    assert login(user.username, password).status_code == 200

    resp = api_client.post("/api/v1/auth/logout")
    assert resp.status_code == 204
    assert resp.content == b""
    clear_cookie = _set_cookie_header(resp)
    assert "Max-Age=0" in clear_cookie

    with auth_session_factory() as session:
        assert session.execute(select(UserSession)).scalars().all() == []

    assert api_client.get("/api/v1/auth/me").status_code == 401
    assert api_client.post("/api/v1/auth/logout").status_code == 401


def test_cookie_attributes(api_client, make_user, login):
    user, password = make_user()
    resp = login(user.username, password)
    cookie = _set_cookie_header(resp).lower()
    assert "httponly" in cookie
    assert "samesite=lax" in cookie
    assert "path=/" in cookie
    assert "secure" not in cookie


def test_cookie_secure_in_production(api_client, make_user, login):
    from app.core.config import get_settings

    user, password = make_user(username="prod-user")
    try:
        get_settings.cache_clear()
        import os

        os.environ["APP_ENV"] = "production"
        get_settings.cache_clear()
        resp = login(user.username, password)
        assert resp.status_code == 200
        assert "secure" in _set_cookie_header(resp).lower()
    finally:
        import os

        os.environ.pop("APP_ENV", None)
        get_settings.cache_clear()


# --- V2 / B7-B8 --------------------------------------------------------------


def test_bootstrap_idempotent(
    auth_session_factory, bootstrap_admin, capsys
):
    bootstrap_admin(ADMIN_USERNAME, ADMIN_PASSWORD)
    with auth_session_factory() as session:
        first = session.execute(select(User)).scalars().all()
        assert len(first) == 1
        assert first[0].role == "ADMIN"
        assert first[0].status == "ACTIVE"
        assert first[0].version == 1
        first_id = first[0].id

    bootstrap_admin(ADMIN_USERNAME, ADMIN_PASSWORD)  # expect exit 0 (no-op)
    with auth_session_factory() as session:
        again = session.execute(select(User)).scalars().all()
        assert len(again) == 1
        assert again[0].id == first_id
    assert "nothing to do" in capsys.readouterr().out


def test_bootstrap_missing_credentials(auth_session_factory, bootstrap_admin, capsys):
    bootstrap_admin(username="", password="", expect=2)
    captured = capsys.readouterr()
    assert "INITIAL_ADMIN" in captured.err
    with auth_session_factory() as session:
        assert session.execute(select(User)).scalars().all() == []


def test_bootstrap_concurrent_is_idempotent(auth_session_factory):
    from app.cli.bootstrap_admin import run as bootstrap_run
    from app.core.config import Settings

    settings = Settings(
        _env_file=None,
        initial_admin_username=ADMIN_USERNAME,
        initial_admin_password=ADMIN_PASSWORD,
    )
    results: list[int] = []
    barrier = threading.Barrier(2)

    def worker() -> None:
        barrier.wait()
        results.append(bootstrap_run(settings=settings, session_factory=auth_session_factory))

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert results == [0, 0], results
    with auth_session_factory() as session:
        users = session.execute(select(User)).scalars().all()
    assert len(users) == 1
    assert users[0].role == "ADMIN"


# --- V5 / B12 ----------------------------------------------------------------


def test_no_sensitive_leakage_in_responses_or_logs(
    api_client, make_user, login, caplog
):
    user, password = make_user()
    with caplog.at_level(logging.DEBUG):
        success = login(user.username, password)
        me = api_client.get("/api/v1/auth/me")
        failure = login(user.username, "wrong-" + password)

    token = api_client.cookies.get("csm_session")
    assert token
    combined = success.text + me.text + failure.text
    assert password not in combined
    assert "password_hash" not in combined
    assert token not in combined

    assert password not in caplog.text
    assert "password_hash" not in caplog.text


# --- B10 / B14 / error envelope ---------------------------------------------


def test_version_conflict_and_internal_error_envelopes(auth_app):
    from app.core.errors import VersionConflict

    async def conflict() -> None:
        raise VersionConflict(7)

    async def boom() -> None:
        raise RuntimeError("top-secret-stack")

    auth_app.add_api_route("/_test/conflict", conflict, methods=["GET"])
    auth_app.add_api_route("/_test/boom", boom, methods=["GET"])

    with TestClient(auth_app, raise_server_exceptions=False) as client:
        resp = client.get("/_test/conflict")
        assert resp.status_code == 409
        assert resp.json()["error"]["code"] == "VERSION_CONFLICT"
        assert resp.json()["error"]["details"] == {"current_version": 7}

        resp500 = client.get("/_test/boom")
        assert resp500.status_code == 500
        assert resp500.json() == {
            "error": {
                "code": "INTERNAL_ERROR",
                "message": "Internal server error",
                "details": {},
            }
        }
        assert "top-secret-stack" not in resp500.text
        assert "Traceback" not in resp500.text


def test_not_found_and_validation_envelopes(api_client):
    missing = api_client.get("/api/v1/does-not-exist")
    assert missing.status_code == 404
    assert missing.json() == {
        "error": {"code": "NOT_FOUND", "message": "Not Found", "details": {}}
    }

    invalid = api_client.post(
        "/api/v1/auth/login", json={"username": "ab", "password": "x"}
    )
    assert invalid.status_code == 422
    body = invalid.json()
    assert body["error"]["code"] == "VALIDATION_ERROR"
    assert body["error"]["details"]["fields"]

    missing_field = api_client.post("/api/v1/auth/login", json={"username": "admin"})
    assert missing_field.status_code == 422
    assert missing_field.json()["error"]["code"] == "VALIDATION_ERROR"


# --- B17 CSRF ----------------------------------------------------------------


def test_csrf_rejects_cross_origin(api_client, make_user, login):
    user, password = make_user(username="csrf-user")
    assert login(user.username, password).status_code == 200

    cross = api_client.post(
        "/api/v1/auth/logout", headers={"Origin": "http://evil.example"}
    )
    assert cross.status_code == 403
    assert cross.json()["error"] == {
        "code": "FORBIDDEN",
        "message": "Forbidden",
        "details": {"reason": "csrf"},
    }

    same = api_client.post(
        "/api/v1/auth/logout", headers={"Origin": "http://testserver"}
    )
    assert same.status_code == 204


def test_csrf_sec_fetch_site(api_client, make_user, login):
    user, password = make_user(username="csrf-user-2")
    assert login(user.username, password).status_code == 200

    cross = api_client.post(
        "/api/v1/auth/logout", headers={"Sec-Fetch-Site": "cross-site"}
    )
    assert cross.status_code == 403
    assert cross.json()["error"]["details"] == {"reason": "csrf"}

    same = api_client.post(
        "/api/v1/auth/logout", headers={"Sec-Fetch-Site": "same-origin"}
    )
    assert same.status_code == 204


def test_csrf_allowed_origin(api_client, make_user, login):
    from app.core.config import get_settings

    user, password = make_user(username="csrf-user-3")
    assert login(user.username, password).status_code == 200

    get_settings.cache_clear()
    import os

    os.environ["AUTH_ALLOWED_ORIGINS"] = "http://trusted.example"
    get_settings.cache_clear()
    try:
        allowed = api_client.post(
            "/api/v1/auth/logout", headers={"Origin": "http://trusted.example"}
        )
        assert allowed.status_code == 204
    finally:
        os.environ.pop("AUTH_ALLOWED_ORIGINS", None)
        get_settings.cache_clear()