"""F003 Cluster API integration tests (A1-A9, B1-B33; real PostgreSQL).

Requires a real PostgreSQL database via ``TEST_DATABASE_URL`` (DB-D10 guard in
``conftest``). Constraint/migration evidence is collected in
``test_cluster_constraints.py``.
"""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.core.auth import Operator
from app.core.errors import VersionConflict
from app.core.permissions import Role
from app.models.audit_log import AuditLog
from app.models.cluster import Cluster
from app.services import audit as audit_service
from app.services import cluster as cluster_service

from sqlalchemy import select

CLUSTER_KEYS = {"code", "name", "status", "description", "metadata"}


# --- helpers -----------------------------------------------------------------


def _login_client(app, make_user, role: str):
    user, password = make_user(role=role)
    client = TestClient(app)
    client.__enter__()
    resp = client.post(
        "/api/v1/auth/login",
        json={"username": user.username, "password": password},
    )
    assert resp.status_code == 200, resp.text
    return client, user, password


@pytest.fixture
def role_client_factory(auth_app, make_user):
    """Create logged-in ASGI clients per role and clean them up after the test."""
    clients: list[TestClient] = []

    def _make(role: str):
        client, user, password = _login_client(auth_app, make_user, role)
        clients.append(client)
        return client, user, password

    yield _make
    for client in clients:
        client.__exit__(None, None, None)


def _create(client, code="CL-001", name="Cluster", **overrides):
    body = {"code": code, "name": name}
    body.update(overrides)
    return client.post("/api/v1/clusters", json=body)


def _operator(user) -> Operator:
    return Operator(user_id=user.id, username=user.username, role=Role(user.role))


# --- A1/B1-B3: code rules ----------------------------------------------------


def test_create_defaults_and_get(role_client_factory, auth_session_factory):
    client, user, _ = role_client_factory("EDITOR")
    resp = _create(client, code=" N96P ", name="  N96P 集群  ")
    assert resp.status_code == 201, resp.text
    cluster = resp.json()["cluster"]
    assert cluster["code"] == "N96P"
    assert cluster["name"] == "N96P 集群"
    assert cluster["status"] == "ACTIVE"
    assert cluster["description"] is None
    assert cluster["metadata"] == {}
    assert cluster["version"] == 1
    assert cluster["deleted_at"] is None
    assert cluster["created_at"].endswith("+00:00")
    assert cluster["updated_at"].endswith("+00:00")
    assert "code_key" not in resp.text

    with auth_session_factory() as session:
        row = session.execute(select(Cluster)).scalars().one()
        assert row.code == "N96P"
        assert row.code_key == "N96P"
        audit = session.execute(select(AuditLog)).scalars().one()
        assert audit.action == "CREATE"
        assert audit.object_type == "cluster"
        assert audit.object_id == row.id
        assert audit.operator_user_id == user.id
        assert audit.operator_username == user.username
        assert audit.before_data is None
        assert set(audit.after_data) == CLUSTER_KEYS

    detail = client.get(f"/api/v1/clusters/{cluster['id']}")
    assert detail.status_code == 200
    assert detail.json()["cluster"]["id"] == cluster["id"]


def test_code_case_insensitive_uniqueness(role_client_factory, auth_session_factory):
    client, _, _ = role_client_factory("EDITOR")
    assert _create(client, code="N96P", name="first").status_code == 201
    for variant in ("n96p", "N96P", " n96p ", "n96P"):
        resp = _create(client, code=variant, name="dup")
        assert resp.status_code == 409, (variant, resp.text)
        assert resp.json()["error"] == {
            "code": "CONFLICT",
            "message": "Conflict",
            "details": {"reason": "unique_conflict", "field": "code"},
        }
    with auth_session_factory() as session:
        assert session.execute(select(Cluster)).scalars().one().code_key == "N96P"


def test_code_multicode_unicode_ascii_only_key(
    role_client_factory, auth_session_factory
):
    """F003-REV-1: multi-code-point Unicode codes succeed; code_key folds ASCII only.

    Python ``str.upper()`` maps ``ß``/``ﬁ`` to multiple/single ASCII code points
    (``STRASSE``/``FILE``) while locale-independent PostgreSQL ``upper()`` does
    not; the shared rule is now ASCII ``a-z`` only folding, so these are accepted
    and store the DB-matching key.
    """
    client, _, _ = role_client_factory("EDITOR")
    for raw in (" straße ", "ﬁle"):
        resp = _create(client, code=raw, name="unicode")
        assert resp.status_code == 201, (raw, resp.text)
        assert resp.json()["cluster"]["code"] == raw.strip()

    assert _create(client, code="山河3", name="中文").status_code == 201

    with auth_session_factory() as session:
        keys = {
            row.code: row.code_key for row in session.execute(select(Cluster)).scalars()
        }
        assert keys["straße"] == "STRAßE"
        assert keys["ﬁle"] == "ﬁLE"
        assert keys["山河3"] == "山河3"

    # ASCII folding still drives case-insensitive uniqueness.
    assert _create(client, code="N96P", name="first").status_code == 201
    for variant in ("n96p", "N96P", " n96p "):
        dup = _create(client, code=variant, name="dup")
        assert dup.status_code == 409, (variant, dup.text)
        assert dup.json()["error"]["details"] == {
            "reason": "unique_conflict",
            "field": "code",
        }


def test_integrity_error_translation_unique_vs_check():
    """F003-REV-1: DB integrity failures map to clean 409/422, never a 500."""
    from sqlalchemy.exc import IntegrityError

    from app.core.errors import Conflict, ValidationError
    from app.services.cluster import _translate_integrity_error

    def _error(constraint: str) -> IntegrityError:
        class _Diag:
            constraint_name = constraint

        class _Orig:
            diag = _Diag()

        return IntegrityError("INSERT", {}, _Orig())

    unique = _translate_integrity_error(_error("uq_clusters_code_key"))
    assert isinstance(unique, Conflict)
    assert unique.status_code == 409
    assert unique.details == {"reason": "unique_conflict", "field": "code"}

    check = _translate_integrity_error(_error("ck_clusters_code_key_matches"))
    assert isinstance(check, ValidationError)
    assert check.status_code == 422


def test_code_full_unique_survives_soft_delete(role_client_factory):
    client, _, _ = role_client_factory("ADMIN")
    created = _create(client, code="N96P", name="first").json()["cluster"]
    deleted = client.delete(
        f"/api/v1/clusters/{created['id']}", params={"version": created["version"]}
    )
    assert deleted.status_code == 204

    resp = _create(client, code="n96p", name="reborn")
    assert resp.status_code == 409
    assert resp.json()["error"]["details"]["reason"] == "unique_conflict"

    # The unique index must be full (no deleted_at predicate).
    index = client.get("/api/v1/clusters", params={"deleted": "only"})
    assert index.status_code == 200
    assert index.json()["total"] == 1


def test_patch_code_is_rejected(role_client_factory, auth_session_factory):
    client, _, _ = role_client_factory("EDITOR")
    created = _create(client, code="N96P", name="cluster").json()["cluster"]
    resp = client.patch(
        f"/api/v1/clusters/{created['id']}",
        json={"version": created["version"], "code": "OTHER"},
    )
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"

    for readonly in ("id", "created_at", "deleted_at"):
        bad = client.patch(
            f"/api/v1/clusters/{created['id']}",
            json={"version": created["version"], readonly: "x"},
        )
        assert bad.status_code == 422, (readonly, bad.text)

    with auth_session_factory() as session:
        row = session.execute(select(Cluster)).scalars().one()
        assert row.code == "N96P"
        assert row.version == 1


# --- A2/B4-B7: name rules ----------------------------------------------------


def test_name_rules(role_client_factory):
    client, _, _ = role_client_factory("EDITOR")
    assert _create(client, code="A", name="山河3集群").status_code == 201
    assert _create(client, code="B", name="N96P集群").status_code == 201
    assert _create(client, code="C", name="N96P集群").status_code == 201  # no uniqueness

    trimmed = _create(client, code="D", name="  N96P集群  ").json()["cluster"]
    assert trimmed["name"] == "N96P集群"

    for bad_name in ("", "   ", "bad\x00name", "bad\nname", "bad\x1fname"):
        resp = _create(client, code=f"BAD-{uuid.uuid4().hex[:6]}", name=bad_name)
        assert resp.status_code == 422, (bad_name, resp.text)

    # explicit null on PATCH is rejected
    created = _create(client, code="E", name="ok").json()["cluster"]
    null_patch = client.patch(
        f"/api/v1/clusters/{created['id']}",
        json={"version": created["version"], "name": None},
    )
    assert null_patch.status_code == 422


# --- A3/B8-B9: status --------------------------------------------------------


def test_status_default_and_toggle(role_client_factory):
    client, _, _ = role_client_factory("ADMIN")
    created = _create(client, code="S1", name="s1").json()["cluster"]
    assert created["status"] == "ACTIVE"

    updated = client.patch(
        f"/api/v1/clusters/{created['id']}",
        json={"version": created["version"], "status": "INACTIVE"},
    )
    assert updated.status_code == 200
    assert updated.json()["cluster"]["status"] == "INACTIVE"
    assert updated.json()["cluster"]["version"] == 2

    # INACTIVE objects remain maintainable
    assert (
        client.patch(
            f"/api/v1/clusters/{created['id']}",
            json={"version": 2, "name": "s1-renamed"},
        ).status_code
        == 200
    )
    assert (
        client.delete(
            f"/api/v1/clusters/{created['id']}", params={"version": 3}
        ).status_code
        == 204
    )

    bad = _create(client, code="S2", name="s2", status="BOGUS")
    assert bad.status_code == 422


# --- A4/B10-B16: list contract ----------------------------------------------


def test_list_filter_sort_pagination_search(role_client_factory):
    client, _, _ = role_client_factory("ADMIN")
    _create(client, code="gpu0701", name="GPU 0701", status="ACTIVE")
    _create(client, code="gpu0702", name="GPU 0702", status="INACTIVE")
    third = _create(client, code="alpha", name="Alpha").json()["cluster"]
    client.delete(f"/api/v1/clusters/{third['id']}", params={"version": 1})

    default = client.get("/api/v1/clusters").json()
    assert default["total"] == 2
    assert {item["code"] for item in default["items"]} == {"gpu0701", "gpu0702"}

    inactive = client.get("/api/v1/clusters", params={"status": "INACTIVE"}).json()
    assert [item["code"] for item in inactive["items"]] == ["gpu0702"]

    by_code = client.get("/api/v1/clusters", params={"code": "GPU0701"}).json()
    assert by_code["total"] == 1 and by_code["items"][0]["code"] == "gpu0701"

    search = client.get("/api/v1/clusters", params={"q": "gpu07"}).json()
    assert search["total"] == 2

    combined = client.get(
        "/api/v1/clusters", params={"q": "gpu", "status": "ACTIVE"}
    ).json()
    assert combined["total"] == 1 and combined["items"][0]["code"] == "gpu0701"

    asc = client.get(
        "/api/v1/clusters", params={"sort": "code", "order": "asc"}
    ).json()
    assert [item["code"] for item in asc["items"]] == ["gpu0701", "gpu0702"]

    desc = client.get(
        "/api/v1/clusters", params={"sort": "code", "order": "desc"}
    ).json()
    assert [item["code"] for item in desc["items"]] == ["gpu0702", "gpu0701"]

    page = client.get(
        "/api/v1/clusters",
        params={"page": 2, "page_size": 1, "sort": "code", "order": "asc"},
    ).json()
    assert page["page"] == 2
    assert page["page_size"] == 1
    assert page["total"] == 2
    assert page["items"][0]["code"] == "gpu0702"

    for bad_params in (
        {"page_size": 0},
        {"page_size": 101},
        {"page": 0},
        {"sort": "id"},
        {"sort": ";DROP TABLE clusters"},
        {"order": "random"},
        {"status": "BOGUS"},
        {"deleted": "sometimes"},
    ):
        resp = client.get("/api/v1/clusters", params=bad_params)
        assert resp.status_code == 422, (bad_params, resp.text)
        assert resp.json()["error"]["code"] == "VALIDATION_ERROR"


def test_list_default_page_size_and_bounds(role_client_factory):
    client, _, _ = role_client_factory("EDITOR")
    resp = client.get("/api/v1/clusters")
    assert resp.status_code == 200
    assert resp.json()["page"] == 1
    assert resp.json()["page_size"] == 20
    assert client.get("/api/v1/clusters", params={"page_size": 100}).status_code == 200


# --- A5/B17-B20: soft-delete visibility -------------------------------------


def test_soft_delete_visibility_and_permissions(
    role_client_factory, auth_session_factory
):
    admin, admin_user, _ = role_client_factory("ADMIN")
    created = _create(client=admin, code="HIDDEN", name="hidden").json()["cluster"]
    assert (
        admin.delete(
            f"/api/v1/clusters/{created['id']}", params={"version": 1}
        ).status_code
        == 204
    )

    viewer, _, _ = role_client_factory("VIEWER")
    editor, _, _ = role_client_factory("EDITOR")

    assert viewer.get("/api/v1/clusters").json()["total"] == 0
    for client in (viewer, editor):
        for mode in ("include", "only"):
            resp = client.get("/api/v1/clusters", params={"deleted": mode})
            assert resp.status_code == 403
            assert resp.json()["error"]["details"] == {"reason": "permission"}

    included = admin.get("/api/v1/clusters", params={"deleted": "include"}).json()
    assert included["total"] == 1 and included["items"][0]["deleted_at"] is not None
    only = admin.get("/api/v1/clusters", params={"deleted": "only"}).json()
    assert only["total"] == 1

    # Detail: no permission -> 404 (do not leak existence); explicit true -> 403
    assert viewer.get(f"/api/v1/clusters/{created['id']}").status_code == 404
    explicit = viewer.get(
        f"/api/v1/clusters/{created['id']}", params={"deleted": "true"}
    )
    assert explicit.status_code == 403
    visible = admin.get(
        f"/api/v1/clusters/{created['id']}", params={"deleted": "true"}
    )
    assert visible.status_code == 200

    # Audit survives the object soft delete
    assert (
        admin.get(
            f"/api/v1/clusters/{created['id']}/activity", params={"deleted": "true"}
        ).status_code
        == 200
    )

    # non-UUID id -> 404
    assert admin.get("/api/v1/clusters/not-a-uuid").status_code == 404


# --- A6/B21-B25: restore -----------------------------------------------------


def test_restore_and_not_deleted(role_client_factory):
    admin, _, _ = role_client_factory("ADMIN")
    created = _create(client=admin, code="R1", name="restore me").json()["cluster"]

    not_deleted = admin.post(
        f"/api/v1/clusters/{created['id']}/restore", params={"version": 1}
    )
    assert not_deleted.status_code == 409
    assert not_deleted.json()["error"]["details"] == {"reason": "not_deleted"}

    assert (
        admin.delete(
            f"/api/v1/clusters/{created['id']}", params={"version": 1}
        ).status_code
        == 204
    )
    restored = admin.post(
        f"/api/v1/clusters/{created['id']}/restore", params={"version": 2}
    )
    assert restored.status_code == 200
    body = restored.json()["cluster"]
    assert body["deleted_at"] is None
    assert body["version"] == 3

    # EDITOR lacks RESTORE
    editor, _, _ = role_client_factory("EDITOR")
    forbidden = editor.post(
        f"/api/v1/clusters/{created['id']}/restore", params={"version": 3}
    )
    assert forbidden.status_code == 403
    assert forbidden.json()["error"]["details"] == {"reason": "permission"}


def test_restore_missing_version_query_is_422(role_client_factory):
    admin, _, _ = role_client_factory("ADMIN")
    created = _create(client=admin, code="R2", name="x").json()["cluster"]
    assert admin.post(f"/api/v1/clusters/{created['id']}/restore").status_code == 422
    assert (
        admin.delete(f"/api/v1/clusters/{created['id']}").status_code == 422
    )


# --- A7/B26-B29: audit + activity -------------------------------------------


def test_audit_four_actions_and_activity(role_client_factory, auth_session_factory):
    admin, _, _ = role_client_factory("ADMIN")
    created = _create(client=admin, code="AUD", name="audit").json()["cluster"]
    cid = created["id"]

    assert (
        admin.patch(
            f"/api/v1/clusters/{cid}", json={"version": 1, "name": "audit-2"}
        ).status_code
        == 200
    )
    assert admin.delete(f"/api/v1/clusters/{cid}", params={"version": 2}).status_code == 204
    assert (
        admin.post(f"/api/v1/clusters/{cid}/restore", params={"version": 3}).status_code
        == 200
    )

    with auth_session_factory() as session:
        rows = (
            session.execute(
                select(AuditLog)
                .where(AuditLog.object_id == uuid.UUID(cid))
                .order_by(AuditLog.created_at)
            )
            .scalars()
            .all()
        )
        actions = [row.action for row in rows]
        assert actions == ["CREATE", "UPDATE", "DELETE", "RESTORE"]
        assert rows[0].before_data is None and rows[0].after_data is not None
        assert rows[2].after_data is None and rows[2].before_data is not None
        for row in rows:
            for snapshot in (row.before_data, row.after_data):
                if snapshot is not None:
                    assert set(snapshot) <= CLUSTER_KEYS
                    assert not ({"password", "token", "secret"} & set(snapshot))
        assert all(row.object_type == "cluster" for row in rows)

    # Activity visible to every role, scoped to this object.
    activity = admin.get(f"/api/v1/clusters/{cid}/activity")
    assert activity.status_code == 200
    body = activity.json()
    assert body["total"] == 4
    assert [item["action"] for item in body["items"]] == [
        "CREATE",
        "UPDATE",
        "DELETE",
        "RESTORE",
    ]
    assert set(body["items"][0]) == {
        "id",
        "action",
        "operator_user_id",
        "operator_username",
        "before_data",
        "after_data",
        "created_at",
    }
    for role in ("VIEWER", "EDITOR"):
        client, _, _ = role_client_factory(role)
        assert client.get(f"/api/v1/clusters/{cid}/activity").status_code == 200

    # Activity is scoped: another cluster has no rows.
    other = _create(client=admin, code="OTHER", name="other").json()["cluster"]
    assert admin.get(f"/api/v1/clusters/{other['id']}/activity").json()["total"] == 1


def test_audit_rolls_back_with_business_write(
    role_client_factory, auth_session_factory, monkeypatch
):
    _, admin_user, _ = role_client_factory("ADMIN")
    operator = _operator(admin_user)

    original_record = audit_service.record

    def corrupt_record(*args, **kwargs):
        row = original_record(*args, **kwargs)
        row.action = "BOGUS"  # violates ck_audit_logs_action at commit
        return row

    monkeypatch.setattr(cluster_service.audit, "record", corrupt_record)

    with auth_session_factory() as session:
        with pytest.raises(Exception):
            cluster_service.create_cluster(
                session, operator, code="ROLLBACK", name="will fail"
            )
        session.rollback()

    with auth_session_factory() as session:
        assert (
            session.execute(
                select(Cluster).where(Cluster.code == "ROLLBACK")
            ).scalars().all()
            == []
        )
        assert (
            session.execute(
                select(AuditLog).where(
                    AuditLog.object_type == "cluster",
                    AuditLog.action == "BOGUS",
                )
            ).scalars().all()
            == []
        )


# --- A8/B31: optimistic locking ---------------------------------------------


def test_optimistic_lock_two_sessions(auth_session_factory, make_user):
    user, _ = make_user(role="EDITOR")
    operator = _operator(user)

    with auth_session_factory() as setup:
        cluster = cluster_service.create_cluster(
            setup, operator, code="LCK", name="lock"
        )
        cluster_id = cluster.id

    first = auth_session_factory()
    second = auth_session_factory()
    try:
        c1 = cluster_service.get_cluster(first, cluster_id)
        c2 = cluster_service.get_cluster(second, cluster_id)
        assert c1.version == 1 and c2.version == 1

        cluster_service.update_cluster(
            first, operator, cluster_id, expected_version=1, changes={"name": "first"}
        )
        with pytest.raises(VersionConflict) as exc:
            cluster_service.update_cluster(
                second,
                operator,
                cluster_id,
                expected_version=1,
                changes={"name": "second"},
            )
        assert exc.value.details == {"current_version": 2}
        second.rollback()
    finally:
        first.close()
        second.close()

    with auth_session_factory() as verify:
        final = cluster_service.get_cluster(verify, cluster_id)
        assert final.version == 2
        assert final.name == "first"  # stale write did not overwrite


def test_patch_stale_version_returns_409(role_client_factory):
    admin, _, _ = role_client_factory("ADMIN")
    created = _create(client=admin, code="STALE", name="s").json()["cluster"]
    stale = admin.patch(
        f"/api/v1/clusters/{created['id']}",
        json={"version": 99, "name": "nope"},
    )
    assert stale.status_code == 409
    assert stale.json()["error"] == {
        "code": "VERSION_CONFLICT",
        "message": "Version conflict",
        "details": {"current_version": 1},
    }


# --- update semantics (D01 §4) ----------------------------------------------


def test_patch_omit_keeps_and_null_clears_and_metadata_replaced(role_client_factory):
    admin, _, _ = role_client_factory("ADMIN")
    created = _create(
        client=admin,
        code="SEM",
        name="semantics",
        description="desc",
        metadata={"a": 1, "b": 2},
    ).json()["cluster"]

    # omitted description/metadata keep their values
    kept = admin.patch(
        f"/api/v1/clusters/{created['id']}",
        json={"version": 1, "name": "renamed"},
    ).json()["cluster"]
    assert kept["description"] == "desc"
    assert kept["metadata"] == {"a": 1, "b": 2}

    # explicit null clears description; metadata is whole-value replacement
    replaced = admin.patch(
        f"/api/v1/clusters/{created['id']}",
        json={"version": 2, "description": None, "metadata": {"c": 3}},
    ).json()["cluster"]
    assert replaced["description"] is None
    assert replaced["metadata"] == {"c": 3}

    bad_meta = admin.patch(
        f"/api/v1/clusters/{created['id']}",
        json={"version": 3, "metadata": None},
    )
    assert bad_meta.status_code == 422

    bad_meta_type = _create(
        client=admin, code="META", name="x", metadata=["not", "an", "object"]
    )
    assert bad_meta_type.status_code == 422


# --- B23/B24: reference/dependency checker mechanism -------------------------


def test_reference_checker_blocks_delete(role_client_factory, monkeypatch):
    admin, _, _ = role_client_factory("ADMIN")
    created = _create(client=admin, code="REF", name="referenced").json()["cluster"]
    reference = {
        "object_type": "resource",
        "object_id": str(uuid.uuid4()),
        "label": "gpu-01",
    }
    monkeypatch.setitem(
        cluster_service._REFERENCE_CHECKERS,
        "cluster",
        [lambda db, oid: [reference]],
    )
    resp = admin.delete(f"/api/v1/clusters/{created['id']}", params={"version": 1})
    assert resp.status_code == 409
    assert resp.json()["error"] == {
        "code": "CONFLICT",
        "message": "Conflict",
        "details": {"reason": "reference_exists", "references": [reference]},
    }
    # unchanged target: still visible, version intact
    still = admin.get(f"/api/v1/clusters/{created['id']}").json()["cluster"]
    assert still["deleted_at"] is None and still["version"] == 1


def test_dependency_checker_blocks_restore(role_client_factory, monkeypatch):
    admin, _, _ = role_client_factory("ADMIN")
    created = _create(client=admin, code="DEP", name="dependent").json()["cluster"]
    assert (
        admin.delete(
            f"/api/v1/clusters/{created['id']}", params={"version": 1}
        ).status_code
        == 204
    )
    conflict = {"object_type": "resource", "object_id": str(uuid.uuid4())}
    monkeypatch.setitem(
        cluster_service._DEPENDENCY_CHECKERS,
        "cluster",
        [lambda db, oid: [conflict]],
    )
    resp = admin.post(
        f"/api/v1/clusters/{created['id']}/restore", params={"version": 2}
    )
    assert resp.status_code == 409
    assert resp.json()["error"] == {
        "code": "CONFLICT",
        "message": "Conflict",
        "details": {"reason": "dependency_deleted", "conflicts": [conflict]},
    }
    still = admin.get(
        f"/api/v1/clusters/{created['id']}", params={"deleted": "true"}
    ).json()["cluster"]
    assert still["deleted_at"] is not None and still["version"] == 2


# --- unauthenticated ---------------------------------------------------------


def test_unauthenticated_is_401(api_client):
    assert api_client.get("/api/v1/clusters").status_code == 401
    assert api_client.post("/api/v1/clusters", json={"code": "X", "name": "x"}).status_code == 401