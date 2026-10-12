"""F015 user / account management integration tests (A20-A26, I-9/I-10, B29-B40).

Real PostgreSQL; the app is the production ``create_app`` with only ``get_db``
overridden. Credential material never appears in a response or the audit trail.
"""

from __future__ import annotations

import uuid

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.models.session import UserSession
from integration.f015_helpers import role_client_factory  # noqa: F401


def _login(client, username: str, password: str):
    return client.post(
        "/api/v1/auth/login", json={"username": username, "password": password}
    )


# --- A26/B1/B2: permission matrix --------------------------------------------


def test_users_permissions(api_client, role_client_factory):  # noqa: F811
    anon = api_client.get("/api/v1/users")
    assert anon.status_code == 401
    assert anon.json()["error"]["code"] == "AUTH_REQUIRED"
    assert (
        api_client.get("/api/v1/users", params={"sort": "bogus"}).status_code == 401
    )

    viewer, _, _ = role_client_factory("VIEWER")
    editor, _, _ = role_client_factory("EDITOR")
    admin, admin_user, _ = role_client_factory("ADMIN")

    for client in (viewer, editor):
        for method, path in (
            ("get", "/api/v1/users"),
            ("get", "/api/v1/users/not-a-uuid"),
            ("post", "/api/v1/users"),
            ("patch", "/api/v1/users/not-a-uuid"),
        ):
            resp = getattr(client, method)(path)
            assert resp.status_code == 403, (method, path, resp.text)
            assert resp.json()["error"]["details"] == {"reason": "permission"}

    assert admin.get("/api/v1/users").status_code == 200
    assert admin.get(f"/api/v1/users/{admin_user.id}").status_code == 200


# --- A20/B29/B30/B32: create + login -----------------------------------------


def test_create_user_and_login(auth_app, role_client_factory):  # noqa: F811
    admin, _, _ = role_client_factory("ADMIN")
    resp = admin.post(
        "/api/v1/users",
        json={"username": "  New.User  ", "password": "secret-pass-1", "role": "EDITOR"},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()["user"]
    assert body["username"] == "new.user"
    assert body["role"] == "EDITOR"
    assert body["status"] == "ACTIVE"
    assert body["version"] == 1
    assert "password" not in resp.text and "password_hash" not in resp.text

    with TestClient(auth_app) as client:
        login = _login(client, "new.user", "secret-pass-1")
        assert login.status_code == 200, login.text
        assert login.json()["user"]["role"] == "EDITOR"
        # EDITOR can write but not read the full audit.
        assert client.get("/api/v1/audit").status_code == 403
        assert (
            client.post("/api/v1/clusters", json={"code": "CU1", "name": "c"}).status_code
            == 201
        )


def test_create_validation(role_client_factory):  # noqa: F811
    admin, _, _ = role_client_factory("ADMIN")

    def create(payload):
        return admin.post("/api/v1/users", json=payload)

    for username in ("ab", "bad name", "UPPER!"):
        assert create(
            {"username": username, "password": "valid-pass-1", "role": "VIEWER"}
        ).status_code == 422

    for password in ("", "short", "x" * 129):
        assert create(
            {"username": "pw.boundary", "password": password, "role": "VIEWER"}
        ).status_code == 422

    assert create(
        {"username": "role.user", "password": "valid-pass-1", "role": "SUPER"}
    ).status_code == 422

    # Unknown/read-only fields are rejected.
    assert create(
        {
            "username": "extra.user",
            "password": "valid-pass-1",
            "role": "VIEWER",
            "status": "ACTIVE",
        }
    ).status_code == 422

    assert create(
        {"username": "ok.user", "password": "valid-pass-1", "role": "VIEWER"}
    ).status_code == 201


def test_duplicate_username_is_conflict(role_client_factory):  # noqa: F811
    admin, _, _ = role_client_factory("ADMIN")
    payload = {"username": "dupe.user", "password": "valid-pass-1", "role": "VIEWER"}
    assert admin.post("/api/v1/users", json=payload).status_code == 201
    again = admin.post("/api/v1/users", json=payload)
    assert again.status_code == 409
    assert again.json()["error"] == {
        "code": "CONFLICT",
        "message": "Conflict",
        "details": {"reason": "unique_conflict", "field": "username"},
    }
    # Case/whitespace normalisation collides with the stored username.
    mixed = admin.post(
        "/api/v1/users",
        json={**payload, "username": "  DUPE.User "},
    )
    assert mixed.status_code == 409


# --- A20/B33: create audit ----------------------------------------------------


def test_create_writes_user_audit(role_client_factory, auth_session_factory):  # noqa: F811
    admin, admin_user, _ = role_client_factory("ADMIN")
    created = admin.post(
        "/api/v1/users",
        json={"username": "audit.create", "password": "valid-pass-1", "role": "VIEWER"},
    )
    assert created.status_code == 201
    user_id = uuid.UUID(created.json()["user"]["id"])

    from app.models.audit_log import AuditLog

    with auth_session_factory() as session:
        rows = (
            session.execute(
                select(AuditLog).where(
                    AuditLog.object_type == "user", AuditLog.object_id == user_id
                )
            )
            .scalars()
            .all()
        )
    assert len(rows) == 1
    assert rows[0].action == "CREATE"
    assert rows[0].operator_user_id == admin_user.id
    assert rows[0].operator_username == admin_user.username
    assert rows[0].after_data == {
        "username": "audit.create",
        "role": "VIEWER",
        "status": "ACTIVE",
    }


# --- A21/B34: role change takes effect immediately ----------------------------


def test_role_change_is_immediate(auth_app, role_client_factory):  # noqa: F811
    admin, _, _ = role_client_factory("ADMIN")
    created = admin.post(
        "/api/v1/users",
        json={"username": "role.flip", "password": "valid-pass-1", "role": "VIEWER"},
    )
    user_id = created.json()["user"]["id"]

    with TestClient(auth_app) as client:
        assert _login(client, "role.flip", "valid-pass-1").status_code == 200
        assert client.get("/api/v1/audit").status_code == 403

        patched = admin.patch(
            f"/api/v1/users/{user_id}", json={"version": 1, "role": "ADMIN"}
        )
        assert patched.status_code == 200, patched.text
        assert patched.json()["user"]["role"] == "ADMIN"
        assert patched.json()["user"]["version"] == 2

        # Existing cookie is re-evaluated against the new role.
        assert client.get("/api/v1/audit").status_code == 200


# --- A22/B35/B36: disable invalidates sessions and login ----------------------


def test_disable_invalidates_sessions_and_blocks_login(
    auth_app,
    role_client_factory,  # noqa: F811
    auth_session_factory,
):
    admin, _, _ = role_client_factory("ADMIN")
    created = admin.post(
        "/api/v1/users",
        json={"username": "disable.user", "password": "valid-pass-1", "role": "EDITOR"},
    )
    user_id = uuid.UUID(created.json()["user"]["id"])

    with TestClient(auth_app) as client:
        assert _login(client, "disable.user", "valid-pass-1").status_code == 200
        assert client.get("/api/v1/auth/me").status_code == 200

        disabled = admin.patch(
            f"/api/v1/users/{user_id}", json={"version": 1, "status": "DISABLED"}
        )
        assert disabled.status_code == 200
        assert disabled.json()["user"]["status"] == "DISABLED"

        stale = client.get("/api/v1/auth/me")
        assert stale.status_code == 401
        assert stale.json()["error"]["code"] == "AUTH_REQUIRED"

        relogin = _login(client, "disable.user", "valid-pass-1")
        assert relogin.status_code == 401
        assert relogin.json()["error"]["code"] == "AUTH_INVALID_CREDENTIALS"

    with auth_session_factory() as session:
        remaining = session.execute(
            select(func.count())
            .select_from(UserSession)
            .where(UserSession.user_id == user_id)
        ).scalar_one()
    assert remaining == 0


def test_enable_restores_login(auth_app, role_client_factory):  # noqa: F811
    admin, _, _ = role_client_factory("ADMIN")
    created = admin.post(
        "/api/v1/users",
        json={"username": "enable.user", "password": "valid-pass-1", "role": "EDITOR"},
    )
    user_id = created.json()["user"]["id"]

    disabled = admin.patch(
        f"/api/v1/users/{user_id}", json={"version": 1, "status": "DISABLED"}
    )
    assert disabled.json()["user"]["version"] == 2

    with TestClient(auth_app) as client:
        assert _login(client, "enable.user", "valid-pass-1").status_code == 401

        enabled = admin.patch(
            f"/api/v1/users/{user_id}", json={"version": 2, "status": "ACTIVE"}
        )
        assert enabled.status_code == 200
        assert enabled.json()["user"]["status"] == "ACTIVE"

        assert _login(client, "enable.user", "valid-pass-1").status_code == 200


# --- A24/I-2/B33: update audit before/after -----------------------------------


def test_update_writes_user_audit(role_client_factory, auth_session_factory):  # noqa: F811
    admin, _, _ = role_client_factory("ADMIN")
    created = admin.post(
        "/api/v1/users",
        json={"username": "audit.update", "password": "valid-pass-1", "role": "VIEWER"},
    )
    user_id = created.json()["user"]["id"]
    assert admin.patch(
        f"/api/v1/users/{user_id}", json={"version": 1, "role": "EDITOR"}
    ).status_code == 200
    assert admin.patch(
        f"/api/v1/users/{user_id}", json={"version": 2, "status": "DISABLED"}
    ).status_code == 200

    from app.models.audit_log import AuditLog

    with auth_session_factory() as session:
        audits = (
            session.execute(
                select(AuditLog)
                .where(AuditLog.object_type == "user", AuditLog.object_id == uuid.UUID(user_id))
                .order_by(AuditLog.created_at.asc(), AuditLog.id.asc())
            )
            .scalars()
            .all()
        )
    assert [a.action for a in audits] == ["CREATE", "UPDATE", "UPDATE"]
    assert audits[1].before_data["role"] == "VIEWER"
    assert audits[1].after_data["role"] == "EDITOR"
    assert audits[2].before_data["status"] == "ACTIVE"
    assert audits[2].after_data["status"] == "DISABLED"
    for audit in audits:
        for snapshot in (audit.before_data, audit.after_data):
            if snapshot is not None:
                assert set(snapshot) == {"username", "role", "status"}


# --- B38: PATCH validation and optimistic lock --------------------------------


def test_patch_validation_and_version_conflict(role_client_factory):  # noqa: F811
    admin, _, _ = role_client_factory("ADMIN")
    created = admin.post(
        "/api/v1/users",
        json={"username": "patch.user", "password": "valid-pass-1", "role": "VIEWER"},
    )
    user_id = created.json()["user"]["id"]
    path = f"/api/v1/users/{user_id}"

    # Body shape violations -> 422.
    for payload in (
        {"version": 1},  # neither role nor status
        {"role": "EDITOR"},  # missing version
        {"version": 1, "role": "VIEWER", "status": "ACTIVE", "unknown": 1},
        {"version": 1, "role": "VIEWER", "username": "renamed"},
        {"version": 1, "status": "ACTIVE", "password_hash": "x"},
    ):
        assert admin.patch(path, json=payload).status_code == 422, payload

    # 404 before 409: unknown id with a stale version is 404.
    assert (
        admin.patch(
            f"/api/v1/users/{uuid.uuid4()}", json={"version": 99, "role": "VIEWER"}
        ).status_code
        == 404
    )

    stale = admin.patch(path, json={"version": 99, "status": "DISABLED"})
    assert stale.status_code == 409
    assert stale.json()["error"] == {
        "code": "VERSION_CONFLICT",
        "message": "Version conflict",
        "details": {"current_version": 1},
    }

    assert admin.patch(path, json={"version": 1, "role": "EDITOR"}).status_code == 200
    stale_after = admin.patch(path, json={"version": 1, "status": "DISABLED"})
    assert stale_after.status_code == 409
    assert stale_after.json()["error"]["details"] == {"current_version": 2}


# --- V34: list filters, sorting, paging, detail -------------------------------


def test_list_and_detail(role_client_factory):  # noqa: F811
    admin, admin_user, _ = role_client_factory("ADMIN")
    for name, role in (
        ("alpha.one", "VIEWER"),
        ("alpha.two", "EDITOR"),
        ("beta.one", "VIEWER"),
    ):
        assert admin.post(
            "/api/v1/users",
            json={"username": name, "password": "valid-pass-1", "role": role},
        ).status_code == 201

    everyone = admin.get("/api/v1/users", params={"page_size": 100}).json()
    assert everyone["total"] >= 4
    assert "password_hash" not in admin.get(
        "/api/v1/users", params={"page_size": 100}
    ).text

    viewers = admin.get(
        "/api/v1/users", params={"role": "VIEWER", "page_size": 100}
    ).json()
    assert viewers["total"] == 2
    assert all(item["role"] == "VIEWER" for item in viewers["items"])

    alpha = admin.get("/api/v1/users", params={"q": "ALPHA", "page_size": 100}).json()
    assert alpha["total"] == 2

    ordered = admin.get(
        "/api/v1/users", params={"sort": "username", "order": "asc", "page_size": 100}
    ).json()
    assert [item["username"] for item in ordered["items"]] == sorted(
        item["username"] for item in ordered["items"]
    )

    first = admin.get("/api/v1/users", params={"page": 1, "page_size": 1}).json()
    second = admin.get("/api/v1/users", params={"page": 2, "page_size": 1}).json()
    assert first["total"] == second["total"]
    assert first["items"][0]["id"] != second["items"][0]["id"]

    for params in (
        {"role": "SUPER"},
        {"status": "OFF"},
        {"q": "   "},
        {"q": "x" * 65},
        {"sort": "password"},
        {"page_size": 0},
        {"page_size": 101},
    ):
        resp = admin.get("/api/v1/users", params=params)
        assert resp.status_code == 422, (params, resp.text)

    detail = admin.get(f"/api/v1/users/{admin_user.id}")
    assert detail.status_code == 200
    assert detail.json()["user"]["username"] == admin_user.username
    assert "password_hash" not in detail.text

    assert admin.get("/api/v1/users/not-a-uuid").status_code == 404
    assert admin.get(f"/api/v1/users/{uuid.uuid4()}").status_code == 404


# --- A25/V37/B39: no registration, no physical delete, no password change -----


def test_no_registration_delete_or_password_endpoints(
    api_client, role_client_factory  # noqa: F811
):
    admin, admin_user, _ = role_client_factory("ADMIN")

    for path in (
        "/api/v1/auth/register",
        "/api/v1/auth/signup",
        "/api/v1/users/register",
    ):
        assert admin.post(path).status_code in (404, 405)

    assert admin.delete(f"/api/v1/users/{admin_user.id}").status_code == 405

    for path in (
        f"/api/v1/users/{admin_user.id}/password",
        f"/api/v1/users/{admin_user.id}/reset-password",
        "/api/v1/auth/password",
    ):
        assert admin.post(path).status_code in (404, 405)
        assert admin.patch(path).status_code in (404, 405)


# --- A11/I-4/B27/B28: disabling preserves historical audit --------------------


def test_disable_preserves_existing_audit(
    auth_app,
    role_client_factory,  # noqa: F811
    auth_session_factory,
):
    admin, _, _ = role_client_factory("ADMIN")
    created = admin.post(
        "/api/v1/users",
        json={"username": "history.user", "password": "valid-pass-1", "role": "EDITOR"},
    )
    user_id = created.json()["user"]["id"]

    with TestClient(auth_app) as client:
        assert _login(client, "history.user", "valid-pass-1").status_code == 200
        assert (
            client.post("/api/v1/clusters", json={"code": "HU1", "name": "c"}).status_code
            == 201
        )

    scoped = {
        "operator": "history.user",
    }
    before = admin.get("/api/v1/audit", params=scoped).json()
    assert before["total"] >= 1
    row_before = before["items"][0]

    assert admin.patch(
        f"/api/v1/users/{user_id}", json={"version": 1, "status": "DISABLED"}
    ).status_code == 200

    after = admin.get("/api/v1/audit", params=scoped).json()
    assert after["total"] == before["total"]
    assert after["items"][0] == row_before
    assert after["items"][0]["operator_user_id"] == user_id
    assert after["items"][0]["operator_username"] == "history.user"