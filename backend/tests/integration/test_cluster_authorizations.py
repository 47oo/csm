"""F026 cluster authorization integration tests (A1-A24, T90/T92/T96/T99 base).

Real PostgreSQL; production app with only ``get_db`` overridden. These tests
cover the authorization facts, the three ADMIN endpoints, Audit, scope
resolution and lifecycle boundaries. F026 intentionally does not filter existing
business endpoints (F027).
"""

from __future__ import annotations

import threading
import time
import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.exc import DBAPIError

from integration.f015_helpers import create_cluster, role_client_factory  # noqa: F401

pytestmark = pytest.mark.real_scope


def _grant(client, user_id, cluster_id):
    return client.post(
        f"/api/v1/users/{user_id}/cluster-authorizations",
        json={"cluster_id": str(cluster_id)},
    )


def _list(client, user_id, **params):
    return client.get(f"/api/v1/users/{user_id}/cluster-authorizations", params=params)


def _revoke(client, authorization_id):
    return client.post(f"/api/v1/cluster-authorizations/{authorization_id}/revoke")


def _operator(user, role=None):
    from app.core.auth import Operator
    from app.core.permissions import Role

    if isinstance(user, dict):
        return Operator(
            user_id=uuid.UUID(user["id"]),
            username=user["username"],
            role=Role(role or user["role"]),
        )
    return Operator(
        user_id=user.id,
        username=user.username,
        role=Role(role or user.role),
    )


def _scope(session_factory, operator):
    from app.core.access_scope import resolve_access_scope

    with session_factory() as session:
        return resolve_access_scope(session, operator)


# --- A6/T90: permission matrix and 401-before-403 ----------------------------


def test_authorization_permissions(api_client, role_client_factory):  # noqa: F811
    missing = uuid.uuid4()
    for method, path in (
        ("get", f"/api/v1/users/{missing}/cluster-authorizations"),
        ("post", f"/api/v1/users/{missing}/cluster-authorizations"),
        ("post", f"/api/v1/cluster-authorizations/{missing}/revoke"),
    ):
        anon = getattr(api_client, method)(path)
        assert anon.status_code == 401, (method, path, anon.text)
        assert anon.json()["error"]["code"] == "AUTH_REQUIRED"

    viewer, viewer_user, _ = role_client_factory("VIEWER")
    editor, editor_user, _ = role_client_factory("EDITOR")
    admin, admin_user, _ = role_client_factory("ADMIN")

    for client in (viewer, editor):
        for method, path in (
            ("get", f"/api/v1/users/{viewer_user.id}/cluster-authorizations"),
            ("post", f"/api/v1/users/{viewer_user.id}/cluster-authorizations"),
            ("post", f"/api/v1/cluster-authorizations/{uuid.uuid4()}/revoke"),
        ):
            resp = getattr(client, method)(path)
            assert resp.status_code == 403, (method, path, resp.text)
            assert resp.json()["error"]["details"] == {"reason": "permission"}

    assert _list(admin, viewer_user.id).status_code == 200
    assert _list(admin, admin_user.id).status_code == 200
    missing_user = _list(admin, uuid.uuid4())
    assert missing_user.status_code == 404, missing_user.text
    assert missing_user.json()["error"]["code"] == "NOT_FOUND"


# --- A1/A2/A4/A5/A30/A31/A33: grant, duplicate, revoke, regrant, audit -------


def test_grant_list_revoke_regrant_and_audit(
    role_client_factory, auth_session_factory, make_user  # noqa: F811
):
    from app.models.audit_log import AuditLog

    admin, admin_user, _ = role_client_factory("ADMIN")
    viewer_user, _ = make_user(role="VIEWER", username="f026.viewer")
    cluster = create_cluster(admin, "F26A", "F026 A")

    created = _grant(admin, viewer_user.id, cluster["id"])
    assert created.status_code == 201, created.text
    row = created.json()["cluster_authorization"]
    assert row["status"] == "ACTIVE"
    assert row["effective"] is True
    assert row["user"]["id"] == str(viewer_user.id)
    assert row["cluster"]["id"] == cluster["id"]
    assert row["granted_by"] == str(admin_user.id)
    assert row["granted_by_username"] == admin_user.username
    assert row["revoked_at"] is None
    assert row["granted_at"].endswith("+00:00")

    listed = _list(admin, viewer_user.id)
    assert listed.status_code == 200, listed.text
    body = listed.json()
    assert body["total"] == 1
    assert body["items"][0]["id"] == row["id"]

    duplicate = _grant(admin, viewer_user.id, cluster["id"])
    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["details"]["reason"] == "already_granted"
    assert _list(admin, viewer_user.id).json()["total"] == 1

    with auth_session_factory() as session:
        audits = list(
            session.execute(
                select(AuditLog).where(
                    AuditLog.object_type == "user_cluster_authorization",
                    AuditLog.object_id == uuid.UUID(row["id"]),
                )
            ).scalars()
        )
    assert len(audits) == 1
    assert audits[0].action == "CREATE"
    assert audits[0].operator_username == admin_user.username

    revoked = _revoke(admin, row["id"])
    assert revoked.status_code == 200, revoked.text
    revoked_row = revoked.json()["cluster_authorization"]
    assert revoked_row["status"] == "REVOKED"
    assert revoked_row["effective"] is False
    assert revoked_row["revoked_by"] == str(admin_user.id)
    assert revoked_row["revoked_at"].endswith("+00:00")
    assert _list(admin, viewer_user.id, status="REVOKED").json()["total"] == 1

    second_revoke = _revoke(admin, row["id"])
    assert second_revoke.status_code == 409
    assert second_revoke.json()["error"]["details"]["reason"] == "already_revoked"

    regranted = _grant(admin, viewer_user.id, cluster["id"])
    assert regranted.status_code == 201, regranted.text
    new_id = regranted.json()["cluster_authorization"]["id"]
    assert new_id != row["id"]
    both = _list(admin, viewer_user.id).json()
    assert both["total"] == 2
    assert {item["status"] for item in both["items"]} == {"ACTIVE", "REVOKED"}

    with auth_session_factory() as session:
        audits = list(
            session.execute(
                select(AuditLog).where(
                    AuditLog.object_type == "user_cluster_authorization",
                    AuditLog.object_id == uuid.UUID(row["id"]),
                )
            ).scalars()
        )
    assert [a.action for a in audits] == ["CREATE", "UPDATE"]
    assert audits[1].before_data["revoked_at"] is None
    assert audits[1].after_data["revoked_at"] is not None
    assert set(audits[1].after_data) == {
        "user_id",
        "cluster_id",
        "granted_at",
        "granted_by",
        "revoked_at",
        "revoked_by",
    }


def test_revoke_unknown_is_404(role_client_factory):  # noqa: F811
    admin, _, _ = role_client_factory("ADMIN")
    missing = _revoke(admin, uuid.uuid4())
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "NOT_FOUND"
    assert _revoke(admin, "not-a-uuid").status_code == 404


# --- A3/A14/A15/T96: target validation --------------------------------------


def test_grant_validation(
    role_client_factory, make_user  # noqa: F811
):
    admin, _, _ = role_client_factory("ADMIN")
    viewer_user, _ = make_user(role="VIEWER", username="f026.target")
    admin_user, _ = make_user(role="ADMIN", username="f026.admin.target")
    cluster = create_cluster(admin, "F26B", "F026 B")

    to_admin = _grant(admin, admin_user.id, cluster["id"])
    assert to_admin.status_code == 422
    field = to_admin.json()["error"]["details"]["fields"][0]["field"]
    assert field == "user_id"

    unknown_user = _grant(admin, uuid.uuid4(), cluster["id"])
    assert unknown_user.status_code == 404

    unknown_cluster = _grant(admin, viewer_user.id, uuid.uuid4())
    assert unknown_cluster.status_code == 422
    assert (
        unknown_cluster.json()["error"]["details"]["fields"][0]["field"]
        == "cluster_id"
    )

    # INACTIVE is allowed.
    patched = admin.patch(
        f"/api/v1/clusters/{cluster['id']}",
        json={"version": cluster["version"], "status": "INACTIVE"},
    )
    assert patched.status_code == 200, patched.text
    inactive = patched.json()["cluster"]
    assert _grant(admin, viewer_user.id, inactive["id"]).status_code == 201

    # Soft-deleted Cluster cannot receive a new grant (T96).
    deleted = admin.delete(
        f"/api/v1/clusters/{cluster['id']}?version={inactive['version']}"
    )
    assert deleted.status_code == 204, deleted.text
    soft_deleted = _grant(admin, viewer_user.id, cluster["id"])
    assert soft_deleted.status_code == 422
    assert soft_deleted.json()["error"]["details"]["fields"][0]["field"] == "cluster_id"


# --- A12/A13/T96: soft delete, restore, list history ------------------------


def test_soft_deleted_cluster_history_and_restore(
    role_client_factory, auth_session_factory, make_user  # noqa: F811
):
    admin, _, _ = role_client_factory("ADMIN")
    viewer_user, _ = make_user(role="VIEWER", username="f026.soft")
    cluster = create_cluster(admin, "F26C", "F026 C")
    granted = _grant(admin, viewer_user.id, cluster["id"])
    assert granted.status_code == 201
    authorization_id = granted.json()["cluster_authorization"]["id"]

    assert (
        admin.delete(f"/api/v1/clusters/{cluster['id']}?version={cluster['version']}")
        .status_code
        == 204
    )

    rows = _list(admin, viewer_user.id).json()["items"]
    assert len(rows) == 1
    assert rows[0]["cluster"]["deleted_at"] is not None
    assert rows[0]["effective"] is False
    assert rows[0]["status"] == "ACTIVE"

    scope = _scope(auth_session_factory, _operator(viewer_user))
    assert cluster["id"] not in {str(i) for i in scope.cluster_ids}

    restored = admin.post(
        f"/api/v1/clusters/{cluster['id']}/restore?version={cluster['version'] + 1}"
    )
    assert restored.status_code == 200, restored.text
    rows = _list(admin, viewer_user.id).json()["items"]
    assert rows[0]["cluster"]["deleted_at"] is None
    assert rows[0]["effective"] is True
    scope = _scope(auth_session_factory, _operator(viewer_user))
    assert uuid.UUID(cluster["id"]) in scope.cluster_ids

    # Revoke while soft-deleted: restoring must not resurrect it.
    assert (
        admin.delete(
            f"/api/v1/clusters/{cluster['id']}?version={restored.json()['cluster']['version']}"
        ).status_code
        == 204
    )
    assert _revoke(admin, authorization_id).status_code == 200
    assert (
        admin.post(
            f"/api/v1/clusters/{cluster['id']}/restore?version={restored.json()['cluster']['version'] + 1}"
        ).status_code
        == 200
    )
    rows = _list(admin, viewer_user.id).json()["items"]
    assert rows[0]["status"] == "REVOKED"
    assert rows[0]["effective"] is False
    scope = _scope(auth_session_factory, _operator(viewer_user))
    assert scope.cluster_ids == frozenset()


# --- A19-A23: AccessScope resolution ----------------------------------------


def test_access_scope_resolution(
    role_client_factory, auth_session_factory, make_user  # noqa: F811
):
    from app.core.access_scope import resolve_access_scope
    from app.core.auth import resolve_operator_from_api_key
    from app.services.api_key import create_api_key

    admin, admin_user, _ = role_client_factory("ADMIN")
    viewer_user, _ = make_user(role="VIEWER", username="f026.scope")
    cluster_a = create_cluster(admin, "F26D", "F026 D")
    cluster_b = create_cluster(admin, "F26E", "F026 E")
    cluster_c = create_cluster(admin, "F26F", "F026 F")

    assert _scope(auth_session_factory, _operator(viewer_user)).cluster_ids == frozenset()

    assert _grant(admin, viewer_user.id, cluster_a["id"]).status_code == 201
    assert _grant(admin, viewer_user.id, cluster_b["id"]).status_code == 201
    scope = _scope(auth_session_factory, _operator(viewer_user))
    assert scope.unrestricted is False
    assert scope.cluster_ids == frozenset(
        {uuid.UUID(cluster_a["id"]), uuid.UUID(cluster_b["id"])}
    )
    assert scope.allows(uuid.UUID(cluster_a["id"])) is True
    assert scope.allows(uuid.UUID(cluster_c["id"])) is False

    admin_scope = _scope(auth_session_factory, _operator(admin_user))
    assert admin_scope.unrestricted is True
    assert admin_scope.allows(uuid.UUID(cluster_c["id"])) is True

    # An API Key inherits the bound account's scope (A23 base).
    with auth_session_factory() as session:
        api_key, _, _, plaintext = create_api_key(
            session,
            _operator(admin_user),
            user_id=viewer_user.id,
            label="f026-scope",
            validity_days=90,
        )
        api_key_id = api_key.id
        resolved = resolve_operator_from_api_key(session, plaintext)
        assert resolved is not None
        assert resolved.user_id == viewer_user.id
        api_scope = resolve_access_scope(session, resolved)
        assert api_scope.cluster_ids == scope.cluster_ids
        del api_key_id

    # Revocation is visible on the next request (no cross-request cache).
    listed = _list(admin, viewer_user.id, status="ACTIVE").json()["items"]
    assert len(listed) == 2
    assert _revoke(admin, listed[0]["id"]).status_code == 200
    new_scope = _scope(auth_session_factory, _operator(viewer_user))
    assert len(new_scope.cluster_ids) == 1


# --- A7: list filters/pagination/invalid query -------------------------------


def test_list_filters_and_invalid_query(role_client_factory, make_user):  # noqa: F811
    admin, _, _ = role_client_factory("ADMIN")
    viewer_user, _ = make_user(role="VIEWER", username="f026.list")
    cluster_a = create_cluster(admin, "F26G", "F026 G")
    cluster_b = create_cluster(admin, "F26H", "F026 H")
    assert _grant(admin, viewer_user.id, cluster_a["id"]).status_code == 201
    assert _grant(admin, viewer_user.id, cluster_b["id"]).status_code == 201

    only_a = _list(admin, viewer_user.id, cluster_id=cluster_a["id"]).json()
    assert only_a["total"] == 1
    assert only_a["items"][0]["cluster"]["id"] == cluster_a["id"]

    by_code = _list(admin, viewer_user.id, q="f26g").json()
    assert by_code["total"] == 1

    assert _list(admin, viewer_user.id, page=0).status_code == 422
    assert _list(admin, viewer_user.id, page_size=101).status_code == 422
    assert _list(admin, viewer_user.id, sort="id").status_code == 422
    assert _list(admin, viewer_user.id, unexpected="x").status_code == 422
    assert _list(admin, viewer_user.id, cluster_id="not-a-uuid").status_code == 422
    assert _list(admin, viewer_user.id).status_code == 200
    # Contract P-1: path 404 wins over semantic q validation.
    assert _list(admin, uuid.uuid4(), q="").status_code == 404


# --- A17/A18: admin upgrade/downgrade and disabled account -----------------


def test_admin_upgrade_downgrade_and_disabled_account(
    role_client_factory, auth_session_factory, make_user  # noqa: F811
):
    from app.models.user_cluster_authorization import UserClusterAuthorization

    admin, _, _ = role_client_factory("ADMIN")
    viewer_user, _ = make_user(
        role="VIEWER", username="f026.lifecycle", password="f026-pass-123"
    )
    cluster = create_cluster(admin, "F26L", "F026 L")
    assert _grant(admin, viewer_user.id, cluster["id"]).status_code == 201
    assert uuid.UUID(cluster["id"]) in _scope(
        auth_session_factory, _operator(viewer_user)
    ).cluster_ids

    upgraded = admin.patch(
        f"/api/v1/users/{viewer_user.id}",
        json={"version": viewer_user.version, "role": "ADMIN"},
    )
    assert upgraded.status_code == 200, upgraded.text
    assert _scope(auth_session_factory, _operator(upgraded.json()["user"])).unrestricted is True

    downgraded = admin.patch(
        f"/api/v1/users/{viewer_user.id}",
        json={"version": upgraded.json()["user"]["version"], "role": "VIEWER"},
    )
    assert downgraded.status_code == 200, downgraded.text
    assert uuid.UUID(cluster["id"]) in _scope(
        auth_session_factory, _operator(downgraded.json()["user"])
    ).cluster_ids

    disabled = admin.patch(
        f"/api/v1/users/{viewer_user.id}",
        json={"version": downgraded.json()["user"]["version"], "status": "DISABLED"},
    )
    assert disabled.status_code == 200, disabled.text
    with auth_session_factory() as session:
        rows = list(
            session.execute(
                select(UserClusterAuthorization).where(
                    UserClusterAuthorization.user_id == viewer_user.id,
                    UserClusterAuthorization.revoked_at.is_(None),
                )
            ).scalars()
        )
    assert len(rows) == 1
    # A disabled account cannot authenticate; its grant row is retained.


# --- A25/A26/A27/A29/T99: migration and backfill ---------------------------


def test_migration_and_backfill(pg_engine, alembic_runner):
    from sqlalchemy import text

    def _counts():
        with pg_engine.connect() as conn:
            return conn.execute(
                text(
                    "SELECT count(*), count(*) FILTER (WHERE revoked_at IS NULL) "
                    "FROM user_cluster_authorizations"
                )
            ).one()

    alembic_runner.downgrade("0014_api_keys")
    with pg_engine.begin() as conn:
        # Existing data: ADMIN/VIEWER/EDITOR/DISABLED users and ACTIVE/INACTIVE/
        # soft-deleted Clusters. Raw SQL keeps this independent of F026 code.
        conn.execute(
            text(
                """
                INSERT INTO users (username, password_hash, role, status, version)
                VALUES ('f026.mig.admin', 'x', 'ADMIN', 'ACTIVE', 1),
                       ('f026.mig.viewer', 'x', 'VIEWER', 'ACTIVE', 1),
                       ('f026.mig.editor', 'x', 'EDITOR', 'ACTIVE', 1),
                       ('f026.mig.disabled', 'x', 'VIEWER', 'DISABLED', 1)
                ON CONFLICT (username) DO NOTHING
                """
            )
        )
        conn.execute(
            text(
                """
                INSERT INTO clusters (code, code_key, name, status, version)
                VALUES ('F26M1', 'F26M1', 'F026 M1', 'ACTIVE', 1),
                       ('F26M2', 'F26M2', 'F026 M2', 'INACTIVE', 1)
                ON CONFLICT (code_key) DO NOTHING
                """
            )
        )
        conn.execute(
            text(
                """
                INSERT INTO clusters (code, code_key, name, status, version, deleted_at)
                VALUES ('F26M3', 'F26M3', 'F026 M3', 'ACTIVE', 1, now())
                ON CONFLICT (code_key) DO NOTHING
                """
            )
        )

    alembic_runner.upgrade("head")
    total, active = _counts()
    assert total == 3 * 3  # three non-ADMIN users x three Clusters
    assert active == total

    with pg_engine.connect() as conn:
        admin_rows = conn.execute(
            text(
                """
                SELECT count(*) FROM user_cluster_authorizations a
                JOIN users u ON u.id = a.user_id WHERE u.role = 'ADMIN'
                """
            )
        ).scalar_one()
        disabled_rows = conn.execute(
            text(
                """
                SELECT count(*) FROM user_cluster_authorizations a
                JOIN users u ON u.id = a.user_id
                WHERE u.username = 'f026.mig.disabled'
                """
            )
        ).scalar_one()
        soft_rows = conn.execute(
            text(
                """
                SELECT count(*) FROM user_cluster_authorizations a
                JOIN clusters c ON c.id = a.cluster_id
                WHERE c.code_key = 'F26M3'
                """
            )
        ).scalar_one()
    assert admin_rows == 0
    assert disabled_rows == 3
    assert soft_rows == 3

    # Re-running upgrade/backfill must not duplicate or resurrect grants.
    alembic_runner.downgrade("0014_api_keys")
    alembic_runner.upgrade("head")
    assert _counts() == (total, active)

    # Row-level guards: attribution immutable, delete refused, active unique.
    with pg_engine.begin() as conn:
        row = conn.execute(
            text(
                "SELECT id, user_id, cluster_id FROM user_cluster_authorizations "
                "WHERE revoked_at IS NULL LIMIT 1"
            )
        ).one()
    with pytest.raises(DBAPIError) as update_exc:
        with pg_engine.begin() as conn:
            conn.execute(
                text(
                    "UPDATE user_cluster_authorizations SET cluster_id = :new "
                    "WHERE id = :id"
                ),
                {"new": uuid.uuid4(), "id": row.id},
            )
    assert update_exc.value.orig.sqlstate == "23514"
    with pytest.raises(DBAPIError) as delete_exc:
        with pg_engine.begin() as conn:
            conn.execute(
                text("DELETE FROM user_cluster_authorizations WHERE id = :id"),
                {"id": row.id},
            )
    assert delete_exc.value.orig.sqlstate == "23001"
    with pytest.raises(DBAPIError) as unique_exc:
        with pg_engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO user_cluster_authorizations (user_id, cluster_id) "
                    "VALUES (:u, :c)"
                ),
                {"u": row.user_id, "c": row.cluster_id},
            )
    assert unique_exc.value.orig.sqlstate == "23505"

    # Restore head even if an assertion above failed.
    if alembic_runner.head_revision() != "0015_user_cluster_authorizations":
        alembic_runner.upgrade("head")


def test_f026_0015_downgrade_removes_only_f026_objects(pg_engine, alembic_runner):
    """F026-RV-08: 0015 down/up object symmetry is explicit."""
    from sqlalchemy import text

    def _objects():
        with pg_engine.connect() as conn:
            tables = set(
                conn.execute(
                    text(
                        "SELECT tablename FROM pg_tables WHERE schemaname='public'"
                    )
                ).scalars()
            )
            funcs = set(
                conn.execute(
                    text(
                        "SELECT proname FROM pg_proc WHERE pronamespace='public'::regnamespace"
                    )
                ).scalars()
            )
            triggers = set(
                conn.execute(
                    text(
                        "SELECT tgname FROM pg_trigger WHERE NOT tgisinternal"
                    )
                ).scalars()
            )
            indexes = set(
                conn.execute(
                    text(
                        "SELECT indexname FROM pg_indexes WHERE schemaname='public'"
                    )
                ).scalars()
            )
        return tables, funcs, triggers, indexes

    def _f026_objects(objects):
        tables, funcs, triggers, indexes = objects
        return (
            "user_cluster_authorizations" in tables,
            "fn_user_cluster_authorizations_immutable" in funcs,
            "fn_user_cluster_authorizations_no_delete" in funcs,
            "trg_user_cluster_authorizations_immutable" in triggers,
            "trg_user_cluster_authorizations_no_delete" in triggers,
            "uq_user_cluster_authorizations_user_id_cluster_id" in indexes,
            "ix_user_cluster_authorizations_user_id" in indexes,
            "ix_user_cluster_authorizations_cluster_id" in indexes,
        )

    try:
        assert all(_f026_objects(_objects()))
        alembic_runner.downgrade("0014_api_keys")
        after_down = _objects()
        assert not any(_f026_objects(after_down))
        assert {"users", "clusters", "audit_logs"} <= after_down[0]
        alembic_runner.upgrade("head")
        assert all(_f026_objects(_objects()))
    finally:
        if alembic_runner.head_revision() != "0015_user_cluster_authorizations":
            alembic_runner.upgrade("head")


# --- F030 ③: q boundary validation (Contract §3 / §5 P-1) --------------------


def _assert_q_validation_error(resp):
    assert resp.status_code == 422, resp.text
    error = resp.json()["error"]
    assert error["code"] == "VALIDATION_ERROR", error
    fields = error["details"]["fields"]
    assert [item["field"] for item in fields] == ["q"], fields


def test_list_q_boundary_validation(role_client_factory, make_user):  # noqa: F811
    """F030 ③/F029-RV-02: both sides of the `q` rule are locked down.

    The 200 positive control and the 422 group are mutually exclusive (removing
    ``_validate_q`` turns the 422s into 200s), and the unknown-account 404 group
    fails if the path/semantic order (P-1) is swapped.
    """
    admin, _, _ = role_client_factory("ADMIN")
    viewer, _ = make_user(role="VIEWER", username="f030.qboundary")
    cluster = create_cluster(admin, "F30Q1", "F030 Q one")
    assert _grant(admin, viewer.id, cluster["id"]).status_code == 201

    # Known account + invalid free-text q -> 422 with field "q".
    for bad in ("", "   ", "a\x07b", "a\u200bb", "a" * 65):
        _assert_q_validation_error(_list(admin, viewer.id, q=bad))

    # Positive control: a valid q still succeeds (no blanket 422).
    good = _list(admin, viewer.id, q=cluster["code"].lower())
    assert good.status_code == 200, good.text
    body = good.json()
    assert body["total"] == 1, body
    assert body["items"][0]["cluster"]["id"] == cluster["id"]

    # Unknown account -> 404 before q validation (P-1: path object first).
    missing = uuid.uuid4()
    for bad in ("", "a\x07b"):
        not_found = _list(admin, missing, q=bad)
        assert not_found.status_code == 404, not_found.text
        assert not_found.json()["error"]["code"] == "NOT_FOUND"

    # Undeclared query params are rejected by the route, so 422 (not 404).
    undeclared = _list(admin, missing, unexpected="x")
    assert undeclared.status_code == 422, undeclared.text
    assert undeclared.json()["error"]["code"] == "VALIDATION_ERROR"
    assert [
        item["field"]
        for item in undeclared.json()["error"]["details"]["fields"]
    ] == ["unexpected"]

    undeclared_and_q = _list(admin, missing, unexpected="x", q="")
    assert undeclared_and_q.status_code == 422, undeclared_and_q.text
    assert "unexpected" in [
        item["field"]
        for item in undeclared_and_q.json()["error"]["details"]["fields"]
    ]


# --- F030 ④: real concurrent grant (F026-RV-03, Product N3) ------------------

# F031 ④/F030-RV-06: attempt ceiling only; the failure semantics below are
# unchanged (an attempt without interval intersection is a failure, never a skip
# and never replaced by sequential calls).
MAX_ATTEMPTS = 5


def _run_concurrent_grant(client_a, client_b, user_id, cluster_id):
    """Fire two grants from two independent clients at the same instant."""
    barrier = threading.Barrier(2, timeout=30)
    results: list[dict] = []
    lock = threading.Lock()

    def _worker(client, label):
        barrier.wait()
        started = time.monotonic()
        resp = _grant(client, user_id, cluster_id)
        finished = time.monotonic()
        with lock:
            results.append(
                {
                    "label": label,
                    "status": resp.status_code,
                    "body": resp.json(),
                    "started": started,
                    "finished": finished,
                }
            )

    threads = [
        threading.Thread(target=_worker, args=(client_a, "a")),
        threading.Thread(target=_worker, args=(client_b, "b")),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
    assert all(not thread.is_alive() for thread in threads), (
        "concurrent grant threads did not finish within 30s"
    )
    return results


def _intervals_intersect(first: dict, second: dict) -> bool:
    return max(first["started"], second["started"]) <= min(
        first["finished"], second["finished"]
    )


def test_concurrent_grant_two_connections_single_winner(
    role_client_factory, auth_session_factory, make_user  # noqa: F811
):
    """F030 ④/F026-RV-03: two real connections -> exactly one 201 and one 409.

    Each worker uses its own logged-in ADMIN ``TestClient``; every request opens
    its own session from ``auth_session_factory`` (``committed_engine`` +
    ``NullPool``), i.e. two real database connections. The request time spans
    must intersect at least once: a pair whose spans do not intersect is not
    concurrent evidence, so ``assert overlap_observed`` fails the test (never a
    skip, never a sequential call standing in for the race). Up to
    ``MAX_ATTEMPTS`` (=5) attempts are allowed because HTTP-level thread
    scheduling is timing dependent, while the DB invariants are asserted on
    every attempt.
    """
    from app.models.audit_log import AuditLog
    from app.models.user_cluster_authorization import UserClusterAuthorization

    admin_a, _, _ = role_client_factory("ADMIN", username="f030.race.admin.a")
    admin_b, _, _ = role_client_factory("ADMIN", username="f030.race.admin.b")

    attempts: list[str] = []
    overlap_observed = False
    for attempt in range(1, MAX_ATTEMPTS + 1):
        viewer, _ = make_user(role="VIEWER", username=f"f030.race.viewer{attempt}")
        cluster = create_cluster(admin_a, f"F30R{attempt}", f"F030 race {attempt}")
        cluster_id = uuid.UUID(cluster["id"])

        # Warm up both clients so the concurrent window contains only the write.
        assert _list(admin_a, viewer.id).status_code == 200
        assert _list(admin_b, viewer.id).status_code == 200

        results = _run_concurrent_grant(admin_a, admin_b, viewer.id, cluster_id)
        assert len(results) == 2, results
        assert sorted(item["status"] for item in results) == [201, 409], results

        winner = next(item for item in results if item["status"] == 201)
        loser = next(item for item in results if item["status"] == 409)
        winner_row = winner["body"]["cluster_authorization"]
        assert winner_row["status"] == "ACTIVE"
        assert winner_row["effective"] is True
        assert winner_row["cluster"]["id"] == cluster["id"]
        assert loser["body"]["error"]["code"] == "CONFLICT"
        assert loser["body"]["error"]["details"]["reason"] == "already_granted"

        with auth_session_factory() as session:
            rows = list(
                session.execute(
                    select(UserClusterAuthorization).where(
                        UserClusterAuthorization.user_id == viewer.id,
                        UserClusterAuthorization.cluster_id == cluster_id,
                    )
                ).scalars()
            )
            active = [row for row in rows if row.revoked_at is None]
            audits = list(
                session.execute(
                    select(AuditLog).where(
                        AuditLog.object_type == "user_cluster_authorization",
                        AuditLog.object_id.in_([row.id for row in rows]),
                    )
                ).scalars()
            )

        assert len(rows) == 1, [row.id for row in rows]
        assert len(active) == 1
        assert active[0].id == uuid.UUID(winner_row["id"])
        assert len(audits) == 1, [audit.action for audit in audits]
        assert audits[0].action == "CREATE"
        assert audits[0].object_id == active[0].id

        intersected = _intervals_intersect(results[0], results[1])
        attempts.append(
            f"attempt {attempt}: statuses={[item['status'] for item in results]} "
            f"overlap={intersected} spans="
            f"{[(round(item['started'], 4), round(item['finished'], 4)) for item in results]}"
        )
        if intersected:
            overlap_observed = True
            break

    print("concurrent grant evidence:", *attempts, sep="\n  ")
    print(f"attempts used: {len(attempts)}/{MAX_ATTEMPTS}")
    assert overlap_observed, attempts


# --- F030 ④: non-unique integrity error is surfaced, not mapped to 409 ------


def test_grant_non_unique_integrity_error_is_not_mapped_to_409(
    role_client_factory, auth_session_factory, make_user  # noqa: F811
):
    """F030 ④/F029-RV-08: only the partial unique index maps to 409.

    A ghost operator (``user_id`` that does not exist in ``users``) makes the
    ``granted_by`` FK fail with a real ``23503`` after validation passes; the
    service must re-raise it instead of translating it into
    ``CONFLICT{already_granted}`` and leave no row/Audit behind. The real
    operator then grants the same pair to prove attribution.
    """
    from sqlalchemy.exc import IntegrityError as SAIntegrityError

    from app.core.auth import Operator
    from app.core.errors import Conflict
    from app.core.permissions import Role
    from app.models.audit_log import AuditLog
    from app.models.user_cluster_authorization import UserClusterAuthorization
    from app.services import cluster_authorization as authorization_service

    admin, admin_user, _ = role_client_factory("ADMIN")
    viewer, _ = make_user(role="VIEWER", username="f030.integrity")
    cluster = create_cluster(admin, "F30I1", "F030 integrity")
    cluster_id = uuid.UUID(cluster["id"])
    ghost = Operator(user_id=uuid.uuid4(), username="f030.ghost", role=Role.ADMIN)

    with auth_session_factory() as session:
        with pytest.raises(SAIntegrityError) as excinfo:
            authorization_service.grant_authorization(
                session, ghost, user_id=viewer.id, cluster_id=cluster_id
            )

    error = excinfo.value
    assert not isinstance(error, Conflict)
    assert error.orig.sqlstate == "23503"
    assert (
        error.orig.diag.constraint_name
        == "fk_user_cluster_authorizations_granted_by_users"
    )

    with auth_session_factory() as session:
        rows = list(
            session.execute(
                select(UserClusterAuthorization).where(
                    UserClusterAuthorization.user_id == viewer.id,
                    UserClusterAuthorization.cluster_id == cluster_id,
                )
            ).scalars()
        )
        audits = list(
            session.execute(
                select(AuditLog).where(
                    AuditLog.object_type == "user_cluster_authorization"
                )
            ).scalars()
        )
    assert rows == []
    assert audits == []

    # Attribution control: the same pair with a real operator succeeds.
    with auth_session_factory() as session:
        row = authorization_service.grant_authorization(
            session, _operator(admin_user), user_id=viewer.id, cluster_id=cluster_id
        )
        granted = row[0]
        assert granted.granted_by == admin_user.id
        assert granted.revoked_at is None

    with auth_session_factory() as session:
        rows = list(
            session.execute(
                select(UserClusterAuthorization).where(
                    UserClusterAuthorization.user_id == viewer.id,
                    UserClusterAuthorization.cluster_id == cluster_id,
                )
            ).scalars()
        )
        audits = list(
            session.execute(
                select(AuditLog).where(
                    AuditLog.object_type == "user_cluster_authorization",
                    AuditLog.object_id == granted.id,
                )
            ).scalars()
        )
    assert len(rows) == 1
    assert rows[0].revoked_at is None
    assert [audit.action for audit in audits] == ["CREATE"]


# --- F031 ⑨/T03: grant path 500 envelope on the real Contract route ---------


def test_grant_path_internal_error_envelope_end_to_end(
    auth_app, role_client_factory, auth_session_factory, make_user  # noqa: F811
):
    """F031 ⑨/T03: the real grant route answers the exact 500 envelope.

    The operator dependency is replaced *for this test only* through
    ``auth_app.dependency_overrides[get_current_operator]``, so the request still
    rides the real Contract path (``POST /api/v1/users/{id}/cluster-authorizations``),
    the real ``require_permission``, the real service layer and the real
    database. A ghost ``user_id`` (absent from ``users``) makes ``granted_by``
    fail its foreign key with a genuine ``23503`` after all validation passes —
    the non-unique integrity failure the service re-raises instead of mapping to
    409 ``already_granted``.

    This override deliberately **bypasses authentication**: the case is evidence
    for the 500 envelope and for zero residue only. It is **not** evidence for
    401/403 semantics (the un-overridden control request below still shows
    ``401 AUTH_REQUIRED``). No test-only route is mounted and no production code
    is changed.
    """
    from fastapi.testclient import TestClient

    from app.core.auth import Operator, get_current_operator
    from app.core.permissions import Role
    from app.models.audit_log import AuditLog
    from app.models.user_cluster_authorization import UserClusterAuthorization

    admin, admin_user, _ = role_client_factory("ADMIN")
    viewer, _ = make_user(role="VIEWER", username="f031.t03.viewer")
    cluster = create_cluster(admin, "F31T03", "F031 T03")
    cluster_id = uuid.UUID(cluster["id"])
    ghost_username = "f031.t03.ghost"
    ghost = Operator(user_id=uuid.uuid4(), username=ghost_username, role=Role.ADMIN)

    with TestClient(auth_app, raise_server_exceptions=False) as client:
        # Control: without the override the very same request is a real 401.
        anon = _grant(client, viewer.id, cluster["id"])
        assert anon.status_code == 401, anon.text
        assert anon.json()["error"]["code"] == "AUTH_REQUIRED"

        auth_app.dependency_overrides[get_current_operator] = lambda: ghost
        try:
            resp = _grant(client, viewer.id, cluster["id"])
        finally:
            auth_app.dependency_overrides.pop(get_current_operator, None)

    assert resp.status_code == 500, resp.text
    assert resp.json() == {
        "error": {
            "code": "INTERNAL_ERROR",
            "message": "Internal server error",
            "details": {},
        }
    }, resp.text
    for leaked in (
        "Traceback",
        "fk_user_cluster_authorizations_granted_by_users",
        "23503",
        "IntegrityError",
        ghost_username,
        str(ghost.user_id),
    ):
        assert leaked not in resp.text, (leaked, resp.text)

    # The failed grant leaves neither an authorization row nor an Audit row.
    with auth_session_factory() as session:
        rows = list(
            session.execute(
                select(UserClusterAuthorization).where(
                    UserClusterAuthorization.user_id == viewer.id,
                    UserClusterAuthorization.cluster_id == cluster_id,
                )
            ).scalars()
        )
        audits = list(
            session.execute(
                select(AuditLog).where(
                    AuditLog.object_type == "user_cluster_authorization"
                )
            ).scalars()
        )
    assert rows == []
    assert audits == []

    # The 500 was produced on the shipped route table (no test-only routes).
    assert [
        getattr(route, "path", "")
        for route in auth_app.routes
        if getattr(route, "path", "").startswith("/_test")
    ] == []

    # Attribution control: the real operator grants the same pair -> 201.
    created = _grant(admin, viewer.id, cluster["id"])
    assert created.status_code == 201, created.text
    granted_row = created.json()["cluster_authorization"]
    assert granted_row["granted_by"] == str(admin_user.id)

    with auth_session_factory() as session:
        rows = list(
            session.execute(
                select(UserClusterAuthorization).where(
                    UserClusterAuthorization.user_id == viewer.id,
                    UserClusterAuthorization.cluster_id == cluster_id,
                )
            ).scalars()
        )
        audits = list(
            session.execute(
                select(AuditLog).where(
                    AuditLog.object_type == "user_cluster_authorization",
                    AuditLog.object_id == uuid.UUID(granted_row["id"]),
                )
            ).scalars()
        )
    assert len(rows) == 1, [row.id for row in rows]
    assert rows[0].revoked_at is None
    assert rows[0].granted_by == admin_user.id
    assert [audit.action for audit in audits] == ["CREATE"]


# --- F030 ⑦: marked-module canary -------------------------------------------


def test_marked_module_has_no_legacy_scope_override(auth_app):
    """This module declares ``real_scope``, so the legacy shim must be absent."""
    from app.core.access_scope import get_access_scope
    from app.core.db import get_db

    assert get_db in auth_app.dependency_overrides
    assert get_access_scope not in auth_app.dependency_overrides
