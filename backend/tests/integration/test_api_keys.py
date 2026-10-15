"""F017 API Key machine-credential integration tests (A1-A8/T42-T49).

Real PostgreSQL; the app is the production ``create_app`` with only ``get_db``
overridden. Covers the four endpoints, the Bearer authentication carrier, the
one-time plaintext discipline, CSRF Bearer exemption and audit semantics.
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
from sqlalchemy import select

from integration.api_keys_helpers import (  # noqa: F401
    bearer_client,
    create_key,
    key_row,
)
from integration.f015_helpers import role_client_factory  # noqa: F401


def _insert_key(
    auth_session_factory,
    *,
    user_id,
    label: str = "legacy",
    key_hash: str | None = None,
    created_delta_days: float = -1,
    expires_delta_days: float = 90,
    revoked_at=None,
):
    """Insert an api_keys row directly to reach revoked/expired states."""
    from app.core.security import hash_api_key
    from app.models.api_key import ApiKey

    plaintext = "csm_ak_" + uuid.uuid4().hex
    now = datetime.now(timezone.utc)
    with auth_session_factory() as session:
        api_key = ApiKey(
            user_id=user_id,
            label=label,
            key_hash=key_hash or hash_api_key(plaintext),
            created_by=user_id,
            created_at=now + timedelta(days=created_delta_days),
            expires_at=now + timedelta(days=expires_delta_days),
            revoked_at=revoked_at,
        )
        session.add(api_key)
        session.commit()
        session.refresh(api_key)
        return api_key, plaintext


# --- A8/B1-B2 permission matrix ----------------------------------------------


def test_api_keys_permission_matrix(api_client, role_client_factory):  # noqa: F811
    for method, path in (
        ("get", "/api/v1/api-keys"),
        ("get", "/api/v1/api-keys/not-a-uuid"),
        ("post", "/api/v1/api-keys"),
        ("post", f"/api/v1/api-keys/{uuid.uuid4()}/revoke"),
    ):
        anon = getattr(api_client, method)(path)
        assert anon.status_code == 401, (method, path, anon.text)
        assert anon.json()["error"]["code"] == "AUTH_REQUIRED"

    viewer, viewer_user, _ = role_client_factory("VIEWER")
    editor, editor_user, _ = role_client_factory("EDITOR")
    admin, admin_user, _ = role_client_factory("ADMIN")

    for client in (viewer, editor):
        for method, path in (
            ("get", "/api/v1/api-keys"),
            ("get", f"/api/v1/api-keys/{admin_user.id}"),
            ("post", "/api/v1/api-keys"),
            ("post", f"/api/v1/api-keys/{admin_user.id}/revoke"),
        ):
            resp = getattr(client, method)(path)
            assert resp.status_code == 403, (method, path, resp.text)
            assert resp.json()["error"]["details"] == {"reason": "permission"}

    assert admin.get("/api/v1/api-keys").status_code == 200


def test_invalid_key_is_401_before_403(api_client):
    """T44/A3: an invalid Bearer is 401 even on an ADMIN endpoint."""
    resp = api_client.get(
        "/api/v1/api-keys",
        headers={"Authorization": "Bearer csm_ak_not-a-real-key"},
    )
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "AUTH_REQUIRED"


# --- A5/T46 create + one-time plaintext --------------------------------------


def test_create_returns_plaintext_once(
    role_client_factory, auth_session_factory, make_user  # noqa: F811
):
    admin, admin_user, _ = role_client_factory("ADMIN")
    target, _ = make_user(role="EDITOR", username="ak.onetime")

    # A null/unknown user_id is rejected before any key is created.
    assert create_key(admin, bound_user_id=None, label="ci-runner").status_code == 422

    created = create_key(admin, bound_user_id=str(target.id), label="ci-runner")
    assert created.status_code == 201, created.text
    body = created.json()["api_key"]
    plaintext = body["plaintext"]
    assert plaintext.startswith("csm_ak_")
    assert len(plaintext) == len("csm_ak_") + 43
    assert body["status"] == "ACTIVE"
    assert body["revoked_at"] is None
    assert body["created_by"] == str(admin_user.id)
    assert body["created_by_username"] == admin_user.username
    assert "key_hash" not in created.text

    key_id = body["id"]
    # Subsequent list/detail never expose plaintext or hash.
    listing = admin.get("/api/v1/api-keys", params={"page_size": 100}).json()
    assert listing["total"] >= 1
    assert all("plaintext" not in item for item in listing["items"])
    assert "key_hash" not in admin.get(
        "/api/v1/api-keys", params={"page_size": 100}
    ).text
    detail = admin.get(f"/api/v1/api-keys/{key_id}")
    assert detail.status_code == 200
    assert "plaintext" not in detail.text and "key_hash" not in detail.text

    stored = key_row(auth_session_factory, uuid.UUID(key_id))
    assert stored.key_hash == hashlib.sha256(plaintext.encode()).hexdigest()
    assert stored.key_hash != plaintext


# --- A7/T48 validation --------------------------------------------------------


def test_create_validation(role_client_factory, make_user):  # noqa: F811
    admin, _, _ = role_client_factory("ADMIN")
    target, _ = make_user(role="EDITOR", username="ak.target")
    disabled, _ = make_user(role="EDITOR", status="DISABLED", username="ak.disabled")

    def create(**overrides):
        payload = {"user_id": str(target.id), "label": "ok-label"}
        payload.update(overrides)
        return admin.post("/api/v1/api-keys", json=payload)

    # user_id: unknown / DISABLED / non-UUID.
    assert create(user_id=str(uuid.uuid4())).status_code == 422
    assert create(user_id=str(disabled.id)).status_code == 422
    assert create(user_id="not-a-uuid").status_code == 422

    # label: blank / whitespace / control char / over-long / missing.
    for label in ("", "   ", "bad\nlabel", "x" * 256):
        assert create(label=label).status_code == 422, label
    assert admin.post(
        "/api/v1/api-keys", json={"user_id": str(target.id)}
    ).status_code == 422

    # validity_days: null / 0 / negative / >365 / non-integer.
    for value in (None, 0, -1, 366, 1.5, "90"):
        assert create(validity_days=value).status_code == 422, value

    # Boundaries 1 and 365 succeed.
    assert create(label="one-day", validity_days=1).status_code == 201
    assert create(label="full-year", validity_days=365).status_code == 201

    # Unknown/read-only fields are rejected.
    assert create(status="ACTIVE").status_code == 422


def test_default_validity_is_90_days(role_client_factory, make_user):  # noqa: F811
    admin, _, _ = role_client_factory("ADMIN")
    target, _ = make_user(role="EDITOR", username="ak.default")
    body = create_key(admin, bound_user_id=str(target.id), label="default-90").json()[
        "api_key"
    ]
    created = datetime.fromisoformat(body["created_at"])
    expires = datetime.fromisoformat(body["expires_at"])
    assert expires - created == timedelta(days=90)


# --- A1/T42 Bearer identity ---------------------------------------------------


def test_bearer_identity_and_ignores_cookie(
    auth_app, role_client_factory, make_user, auth_session_factory  # noqa: F811
):
    admin, _, _ = role_client_factory("ADMIN")
    viewer, viewer_user, viewer_password = role_client_factory("VIEWER")
    editor_user, _ = make_user(role="EDITOR", username="ak.editor")
    key = create_key(
        admin, bound_user_id=str(editor_user.id), label="editor-key"
    ).json()["api_key"]

    with bearer_client(auth_app, key["plaintext"]) as client:
        me = client.get("/api/v1/auth/me").json()["user"]
        assert me["username"] == "ak.editor"
        assert me["role"] == "EDITOR"
        # EDITOR can write but cannot read the full audit.
        assert client.get("/api/v1/audit").status_code == 403
        write = client.post("/api/v1/clusters", json={"code": "BKC1", "name": "c"})
        assert write.status_code == 201, write.text

    # Bearer takes priority and the Cookie is ignored.
    with TestClient(auth_app) as client:
        login = client.post(
            "/api/v1/auth/login",
            json={"username": viewer_user.username, "password": viewer_password},
        )
        assert login.status_code == 200
        client.headers.update({"Authorization": f"Bearer {key['plaintext']}"})
        me = client.get("/api/v1/auth/me").json()["user"]
        assert me["username"] == "ak.editor"  # not the VIEWER cookie


# --- A3/A6/T44/T47 invalid credentials ---------------------------------------


def test_invalid_and_revoked_keys_are_equivalent_401(
    auth_app, role_client_factory, auth_session_factory  # noqa: F811
):
    admin, _, _ = role_client_factory("ADMIN")
    bound, _ = make_bound_editor(auth_session_factory)
    key = create_key(admin, bound_user_id=str(bound.id), label="to-revoke").json()[
        "api_key"
    ]

    with bearer_client(auth_app, key["plaintext"]) as client:
        assert client.get("/api/v1/auth/me").status_code == 200

    # Revoke then the same key is 401 on the next request (immediate).
    assert admin.post(f"/api/v1/api-keys/{key['id']}/revoke").status_code == 200
    with bearer_client(auth_app, key["plaintext"]) as client:
        revoked = client.get("/api/v1/auth/me")
        assert revoked.status_code == 401
        assert revoked.json()["error"]["code"] == "AUTH_REQUIRED"

    # Missing / malformed / mismatched hex all yield the identical envelope.
    with TestClient(auth_app) as client:
        missing = client.get("/api/v1/auth/me")
        malformed = client.get(
            "/api/v1/auth/me", headers={"Authorization": "Bearer nope"}
        )
        basic = client.get(
            "/api/v1/auth/me", headers={"Authorization": "Basic abc"}
        )
    for resp in (missing, malformed, basic):
        assert resp.status_code == 401
        assert resp.json() == {
            "error": {
                "code": "AUTH_REQUIRED",
                "message": "Authentication required",
                "details": {},
            }
        }


def test_expired_and_disabled_bound_account_are_401(
    auth_app, role_client_factory, auth_session_factory, make_user  # noqa: F811
):
    admin, _, _ = role_client_factory("ADMIN")
    bound, _ = make_bound_editor(auth_session_factory)
    expired, expired_plaintext = _insert_key(
        auth_session_factory,
        user_id=bound.id,
        label="expired-key",
        created_delta_days=-2,
        expires_delta_days=-1,
    )
    with bearer_client(auth_app, expired_plaintext) as client:
        assert client.get("/api/v1/auth/me").status_code == 401

    # Disabling the bound account invalidates every un-revoked key.
    active_user, _ = make_user(role="EDITOR", username="ak.willdisable")
    key = create_key(admin, bound_user_id=str(active_user.id), label="dis-key").json()[
        "api_key"
    ]
    with bearer_client(auth_app, key["plaintext"]) as client:
        assert client.get("/api/v1/auth/me").status_code == 200
    with auth_session_factory() as session:
        from app.models.user import User

        row = session.get(User, active_user.id)
        row.status = "DISABLED"
        session.commit()
    with bearer_client(auth_app, key["plaintext"]) as client:
        assert client.get("/api/v1/auth/me").status_code == 401


# --- A4/T45 audit -------------------------------------------------------------


def test_audit_semantics(
    auth_app, role_client_factory, auth_session_factory  # noqa: F811
):
    from app.models.audit_log import AuditLog

    admin, admin_user, _ = role_client_factory("ADMIN")
    bound, _ = make_bound_editor(auth_session_factory, username="ak.audit")
    key = create_key(admin, bound_user_id=str(bound.id), label="audit-key").json()[
        "api_key"
    ]

    # Use the key for a business write: operator_username/api_key_label snapshot.
    with bearer_client(auth_app, key["plaintext"]) as client:
        assert (
            client.post("/api/v1/clusters", json={"code": "AKC9", "name": "ak"}).status_code
            == 201
        )

    assert admin.post(f"/api/v1/api-keys/{key['id']}/revoke").status_code == 200

    with auth_session_factory() as session:
        key_audits = (
            session.execute(
                select(AuditLog)
                .where(
                    AuditLog.object_type == "api_key",
                    AuditLog.object_id == uuid.UUID(key["id"]),
                )
                .order_by(AuditLog.created_at.asc(), AuditLog.id.asc())
            )
            .scalars()
            .all()
        )
        cluster_audits = (
            session.execute(
                select(AuditLog).where(AuditLog.object_type == "cluster")
            )
            .scalars()
            .all()
        )

    assert [a.action for a in key_audits] == ["CREATE", "UPDATE"]
    for audit in key_audits:
        assert audit.operator_username == admin_user.username
        assert audit.api_key_label is None  # created/revoked via Cookie path
        for snapshot in (audit.before_data, audit.after_data):
            if snapshot is not None:
                assert "key_hash" not in snapshot
                assert "plaintext" not in snapshot
                assert set(snapshot) <= {"user_id", "label", "expires_at", "revoked_at"}
    assert key_audits[0].after_data["label"] == "audit-key"
    assert key_audits[1].before_data["revoked_at"] is None
    assert key_audits[1].after_data["revoked_at"] is not None

    # The cluster write via the API Key carries the bound account + key label.
    used = next(a for a in cluster_audits if a.after_data.get("code") == "AKC9")
    assert used.operator_username == "ak.audit"
    assert used.api_key_label == "audit-key"


# --- A6/T47 revoke endpoint semantics ----------------------------------------


def test_revoke_semantics(role_client_factory, auth_session_factory):  # noqa: F811
    admin, _, _ = role_client_factory("ADMIN")
    bound, _ = make_bound_editor(auth_session_factory)

    # 404 for unknown / non-UUID id.
    assert admin.post(f"/api/v1/api-keys/{uuid.uuid4()}/revoke").status_code == 404
    assert admin.post("/api/v1/api-keys/not-a-uuid/revoke").status_code == 404

    key = create_key(admin, bound_user_id=str(bound.id), label="revoke-me").json()[
        "api_key"
    ]
    first = admin.post(f"/api/v1/api-keys/{key['id']}/revoke")
    assert first.status_code == 200, first.text
    assert first.json()["api_key"]["status"] == "REVOKED"
    assert first.json()["api_key"]["revoked_at"] is not None

    again = admin.post(f"/api/v1/api-keys/{key['id']}/revoke")
    assert again.status_code == 409
    assert again.json()["error"] == {
        "code": "CONFLICT",
        "message": "Conflict",
        "details": {"reason": "already_revoked"},
    }

    # An EXPIRED but un-revoked key can still be revoked.
    expired, _ = _insert_key(
        auth_session_factory,
        user_id=bound.id,
        label="expired-unrevoked",
        created_delta_days=-2,
        expires_delta_days=-1,
    )
    assert admin.post(f"/api/v1/api-keys/{expired.id}/revoke").status_code == 200


# --- A5 detail + list behaviour ----------------------------------------------


def test_list_filters_sort_and_detail(role_client_factory, make_user):  # noqa: F811
    admin, _, _ = role_client_factory("ADMIN")
    target, _ = make_user(role="EDITOR", username="ak.list")
    other, _ = make_user(role="EDITOR", username="ak.other")
    create_key(admin, bound_user_id=str(target.id), label="Alpha-key")
    create_key(admin, bound_user_id=str(target.id), label="beta-key")
    key = create_key(admin, bound_user_id=str(target.id), label="gamma-key").json()[
        "api_key"
    ]
    assert admin.post(f"/api/v1/api-keys/{key['id']}/revoke").status_code == 200

    all_keys = admin.get("/api/v1/api-keys", params={"page_size": 100}).json()
    assert all_keys["total"] >= 3

    by_user = admin.get(
        "/api/v1/api-keys", params={"user_id": str(target.id), "page_size": 100}
    ).json()
    assert all(item["user_id"] == str(target.id) for item in by_user["items"])

    revoked = admin.get(
        "/api/v1/api-keys", params={"status": "REVOKED", "page_size": 100}
    ).json()
    assert all(item["status"] == "REVOKED" for item in revoked["items"])

    active = admin.get(
        "/api/v1/api-keys", params={"status": "ACTIVE", "page_size": 100}
    ).json()
    assert all(item["status"] == "ACTIVE" for item in active["items"])

    q = admin.get("/api/v1/api-keys", params={"q": "ALPHA", "page_size": 100}).json()
    assert any(item["label"] == "Alpha-key" for item in q["items"])

    ordered = admin.get(
        "/api/v1/api-keys", params={"sort": "label", "order": "asc", "page_size": 100}
    ).json()
    labels = [item["label"] for item in ordered["items"]]
    assert labels == sorted(labels)

    for params in (
        {"status": "BOGUS"},
        {"sort": "user_id"},
        {"order": "sideways"},
        {"q": "   "},
        {"q": "x" * 256},
        {"page": 0},
        {"page_size": 101},
        {"user_id": "not-a-uuid"},
    ):
        assert admin.get("/api/v1/api-keys", params=params).status_code == 422, params

    assert admin.get("/api/v1/api-keys/not-a-uuid").status_code == 404
    assert admin.get(f"/api/v1/api-keys/{uuid.uuid4()}").status_code == 404


def test_no_update_delete_restore_endpoints(role_client_factory):  # noqa: F811
    admin, _, _ = role_client_factory("ADMIN")
    key_id = str(uuid.uuid4())
    assert admin.delete(f"/api/v1/api-keys/{key_id}").status_code in (404, 405)
    assert admin.patch(f"/api/v1/api-keys/{key_id}").status_code in (404, 405)
    assert admin.post(f"/api/v1/api-keys/{key_id}/restore").status_code in (404, 405)
    assert admin.post(f"/api/v1/api-keys/{key_id}/enable").status_code in (404, 405)


# --- A8/T49 CSRF Bearer exemption --------------------------------------------


def test_bearer_requests_are_csrf_exempt(
    auth_app, role_client_factory, auth_session_factory, make_user  # noqa: F811
):
    admin, _, _ = role_client_factory("ADMIN")
    target, _ = make_user(role="EDITOR", username="ak.csrf")
    key = create_key(admin, bound_user_id=str(target.id), label="csrf-key").json()[
        "api_key"
    ]

    # Bearer + cross-site Origin is allowed (Bearer is not sent cross-site).
    with bearer_client(auth_app, key["plaintext"]) as client:
        resp = client.post(
            "/api/v1/clusters",
            json={"code": "AKC7", "name": "c"},
            headers={"Origin": "http://evil.example"},
        )
        assert resp.status_code == 201, resp.text

    # Cookie-only cross-site request still fails with 403 csrf (unchanged).
    with TestClient(auth_app) as client:
        login = client.post(
            "/api/v1/auth/login",
            json={"username": "ak.csrf", "password": "user-pass-123"},
        )
        assert login.status_code == 200
        cross = client.post(
            "/api/v1/auth/logout", headers={"Origin": "http://evil.example"}
        )
        assert cross.status_code == 403
        assert cross.json()["error"]["details"] == {"reason": "csrf"}


# --- helpers ------------------------------------------------------------------


def make_bound_editor(auth_session_factory, username: str = "ak.bound"):
    from app.core.permissions import Role
    from app.core.security import hash_password
    from app.models.user import User, UserStatus

    with auth_session_factory() as session:
        user = User(
            username=username,
            password_hash=hash_password("user-pass-123"),
            role=Role.EDITOR.value,
            status=UserStatus.ACTIVE.value,
            version=1,
        )
        session.add(user)
        session.commit()
        session.refresh(user)
        return user, "user-pass-123"