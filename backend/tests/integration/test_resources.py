"""F004 Resource API integration tests (A1-A13, B1-B46; real PostgreSQL).

Requires a real PostgreSQL database via ``TEST_DATABASE_URL`` (DB-D10 guard in
``conftest``). Constraint/migration evidence is collected in
``test_resource_constraints.py``.
"""

from __future__ import annotations

import json
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text

from app.core.auth import Operator
from app.core.errors import VersionConflict
from app.core.permissions import Role
from app.models.audit_log import AuditLog
from app.models.resource import Resource
from app.services import audit as audit_service
from app.services import cluster as cluster_service
from app.services import resource as resource_service

RESOURCE_AUDIT_KEYS = {
    "cluster_id",
    "hostname",
    "resource_type",
    "role",
    "status",
    "description",
    "metadata",
}


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


def _create_cluster(client, code="CL-001", name="Cluster", **overrides):
    body = {"code": code, "name": name}
    body.update(overrides)
    return client.post("/api/v1/clusters", json=body)


def _cluster(client, code="CL-001", name="Cluster"):
    resp = _create_cluster(client, code=code, name=name)
    assert resp.status_code == 201, resp.text
    return resp.json()["cluster"]


def _create(client, cluster, hostname="cn001", resource_type="BARE_METAL", **overrides):
    body = {
        "cluster": cluster,
        "hostname": hostname,
        "resource_type": resource_type,
    }
    body.update(overrides)
    return client.post("/api/v1/resources", json=body)


def _resource(client, cluster, hostname="cn001", **overrides):
    resp = _create(client, cluster, hostname=hostname, **overrides)
    assert resp.status_code == 201, resp.text
    return resp.json()["resource"]


def _operator(user) -> Operator:
    return Operator(user_id=user.id, username=user.username, role=Role(user.role))


# --- A1/B1-B3: hostname uniqueness -------------------------------------------


def test_integrity_error_translation_unique_vs_check():
    """B38: the concurrent-create race maps to 409, other DB failures to 422."""
    from sqlalchemy.exc import IntegrityError

    from app.core.errors import Conflict, ValidationError
    from app.services.resource import _translate_integrity_error

    def _error(constraint: str) -> IntegrityError:
        class _Diag:
            constraint_name = constraint

        class _Orig:
            diag = _Diag()

        return IntegrityError("INSERT", {}, _Orig())

    unique = _translate_integrity_error(_error("uq_resources_cluster_id_hostname_key"))
    assert isinstance(unique, Conflict)
    assert unique.details == {"reason": "unique_conflict", "field": "hostname"}

    check = _translate_integrity_error(_error("ck_resources_hostname_key_matches"))
    assert isinstance(check, ValidationError)
    assert check.status_code == 422


def test_create_defaults_and_unique_within_cluster(role_client_factory, auth_session_factory):
    client, user, _ = role_client_factory("EDITOR")
    c1 = _cluster(client, code="C1")
    created = _resource(client, c1["code"], hostname=" CN001 ")
    assert created["hostname"] == "cn001"
    assert created["cluster"] == {"id": c1["id"], "code": "C1", "name": "Cluster"}
    assert created["resource_type"] == "BARE_METAL"
    assert created["role"] == "OTHER"
    assert created["status"] == "UNKNOWN"
    assert created["description"] is None
    assert created["metadata"] == {}
    assert created["version"] == 1
    assert created["deleted_at"] is None
    assert created["created_at"].endswith("+00:00")
    assert "hostname_key" not in json.dumps(created)

    for variant in ("cn001", "CN001", " cn001 ", "Cn001"):
        dup = _create(client, c1["code"], hostname=variant)
        assert dup.status_code == 409, (variant, dup.text)
        assert dup.json()["error"] == {
            "code": "CONFLICT",
            "message": "Conflict",
            "details": {"reason": "unique_conflict", "field": "hostname"},
        }

    with auth_session_factory() as session:
        row = session.execute(select(Resource)).scalars().one()
        assert row.hostname == "cn001"
        assert row.hostname_key == "cn001"
        audit = session.execute(
            select(AuditLog).where(AuditLog.object_type == "resource")
        ).scalars().one()
        assert audit.action == "CREATE"
        assert audit.object_type == "resource"
        assert audit.object_id == row.id
        assert audit.operator_user_id == user.id
        assert set(audit.after_data) == RESOURCE_AUDIT_KEYS


def test_cross_cluster_same_hostname_allowed(role_client_factory):
    client, _, _ = role_client_factory("EDITOR")
    c1 = _cluster(client, code="C1")
    c2 = _cluster(client, code="C2")
    assert _create(client, c1["code"], hostname="cn001").status_code == 201
    assert _create(client, c2["code"], hostname="cn001").status_code == 201


def test_soft_delete_then_recreate(role_client_factory):
    client, _, _ = role_client_factory("ADMIN")
    c1 = _cluster(client, code="C1")
    first = _resource(client, c1["code"], hostname="cn001")
    assert (
        client.delete(
            f"/api/v1/resources/{first['id']}", params={"version": first["version"]}
        ).status_code
        == 204
    )
    second = _resource(client, c1["code"], hostname="CN001")
    assert second["id"] != first["id"]
    assert second["hostname"] == "cn001"


# --- A3/B5/B6: normalisation -------------------------------------------------


def test_hostname_ascii_only_folding(role_client_factory, auth_session_factory):
    client, _, _ = role_client_factory("EDITOR")
    c1 = _cluster(client, code="C1")
    for raw in (" straße ", "ﬁle", "山河3"):
        resp = _create(client, c1["code"], hostname=raw)
        assert resp.status_code == 201, (raw, resp.text)
        assert resp.json()["resource"]["hostname"] == raw.strip()

    # STRAßE and straße share the same key (non-ASCII not folded); STRASSE is distinct.
    assert _create(client, c1["code"], hostname="STRAßE").status_code == 409
    assert _create(client, c1["code"], hostname="STRASSE").status_code == 201

    with auth_session_factory() as session:
        keys = {
            row.hostname: row.hostname_key
            for row in session.execute(select(Resource)).scalars()
        }
    assert keys["straße"] == "straße"
    assert keys["ﬁle"] == "ﬁle"
    assert keys["山河3"] == "山河3"
    assert keys["strasse"] == "strasse"


def test_hostname_validation_errors(role_client_factory):
    client, _, _ = role_client_factory("EDITOR")
    c1 = _cluster(client, code="C1")
    for bad in ("", "   ", "c n001", "c\tn", "bad\x00name", "a\nb"):
        resp = _create(client, c1["code"], hostname=bad)
        assert resp.status_code == 422, (bad, resp.text)
    # 253 accepted, 254 rejected
    assert _create(client, c1["code"], hostname="a" * 253).status_code == 201
    assert _create(client, c1["code"], hostname="b" * 254).status_code == 422


def test_short_name_and_fqdn_are_distinct(role_client_factory):
    client, _, _ = role_client_factory("EDITOR")
    c1 = _cluster(client, code="C1")
    assert _create(client, c1["code"], hostname="cn001").status_code == 201
    assert _create(client, c1["code"], hostname="cn001.example.com").status_code == 201


# --- A4/B10-B12: enum defaults and nulls -------------------------------------


def test_enum_defaults_and_explicit_null(role_client_factory):
    client, _, _ = role_client_factory("EDITOR")
    c1 = _cluster(client, code="C1")
    created = _resource(client, c1["code"], hostname="h1")
    assert created["role"] == "OTHER" and created["status"] == "UNKNOWN"

    explicit = _resource(
        client, c1["code"], hostname="h2", role="GPU", status="IDLE"
    )
    assert explicit["role"] == "GPU" and explicit["status"] == "IDLE"

    assert _create(client, c1["code"], hostname="h3", role=None).status_code == 422
    assert _create(client, c1["code"], hostname="h4", status=None).status_code == 422
    assert (
        _create(client, c1["code"], hostname="h5", resource_type="STORAGE").status_code
        == 422
    )
    assert _create(client, c1["code"], hostname="h6", role="BOGUS").status_code == 422
    assert (
        _create(client, c1["code"], hostname="h7", status="RUNNING").status_code == 422
    )
    assert _create(client, c1["code"], hostname="h8", metadata=["x"]).status_code == 422


def test_patch_omit_keeps_null_clears_and_metadata_replaced(role_client_factory):
    client, _, _ = role_client_factory("EDITOR")
    c1 = _cluster(client, code="C1")
    created = _resource(
        client, c1["code"], hostname="h1", description="d", metadata={"a": 1}
    )
    # omitted fields keep values
    kept = client.patch(
        f"/api/v1/resources/{created['id']}",
        json={"version": 1, "role": "GPU"},
    ).json()["resource"]
    assert kept["description"] == "d"
    assert kept["metadata"] == {"a": 1}
    assert kept["role"] == "GPU"
    assert kept["status"] == "UNKNOWN"

    # metadata whole-value replacement; description null clears
    replaced = client.patch(
        f"/api/v1/resources/{created['id']}",
        json={"version": 2, "description": None, "metadata": {"c": 3}},
    ).json()["resource"]
    assert replaced["description"] is None
    assert replaced["metadata"] == {"c": 3}

    for field in ("role", "status", "metadata", "hostname"):
        bad = client.patch(
            f"/api/v1/resources/{created['id']}",
            json={"version": 3, field: None},
        )
        assert bad.status_code == 422, (field, bad.text)


# --- A5/B13-B15: immutable fields --------------------------------------------


def test_patch_immutable_and_readonly_fields(role_client_factory, auth_session_factory):
    client, _, _ = role_client_factory("EDITOR")
    c1 = _cluster(client, code="C1")
    created = _resource(client, c1["code"], hostname="h1")

    for body in (
        {"cluster": c1["code"]},
        {"cluster_id": c1["id"]},
        {"resource_type": "VIRTUAL_MACHINE"},
        {"id": str(uuid.uuid4())},
        {"created_at": "2020-01-01T00:00:00+00:00"},
        {"deleted_at": "2020-01-01T00:00:00+00:00"},
    ):
        payload = {"version": 1, **body}
        resp = client.patch(f"/api/v1/resources/{created['id']}", json=payload)
        assert resp.status_code == 422, (body, resp.text)

    with auth_session_factory() as session:
        row = session.execute(select(Resource)).scalars().one()
        assert row.resource_type == "BARE_METAL"
        assert row.version == 1


# --- A6/B16-B17: cluster ownership -------------------------------------------


def test_create_cluster_required_and_resolvable(role_client_factory):
    client, _, _ = role_client_factory("EDITOR")
    cluster = _cluster(client, code="n96p", name="N96P")

    # missing cluster
    assert (
        client.post(
            "/api/v1/resources", json={"hostname": "h", "resource_type": "BARE_METAL"}
        ).status_code
        == 422
    )
    # by UUID and by case-insensitive code resolve to the same cluster
    by_uuid = _resource(client, cluster["id"], hostname="h1")
    by_code = _resource(client, "N96P", hostname="h2")
    assert by_uuid["cluster"]["id"] == cluster["id"]
    assert by_code["cluster"]["id"] == cluster["id"]

    # nonexistent UUID / code and invalid code
    for bad in (str(uuid.uuid4()), "NOSUCH", "bad code"):
        resp = _create(client, bad, hostname="hx")
        assert resp.status_code == 422, (bad, resp.text)
        assert resp.json()["error"]["details"]["fields"][0]["field"] == "cluster"


def test_create_with_soft_deleted_cluster_rejected(role_client_factory):
    admin, _, _ = role_client_factory("ADMIN")
    cluster = _cluster(admin, code="GONE")
    assert (
        admin.delete(
            f"/api/v1/clusters/{cluster['id']}", params={"version": 1}
        ).status_code
        == 204
    )
    for ref in (cluster["id"], "GONE"):
        resp = _create(admin, ref, hostname="h")
        assert resp.status_code == 422, (ref, resp.text)
        assert resp.json()["error"]["details"]["fields"][0]["field"] == "cluster"


# --- A7/B18-B22: list contract -----------------------------------------------


def test_list_filter_sort_pagination_search(role_client_factory):
    client, _, _ = role_client_factory("ADMIN")
    c1 = _cluster(client, code="N96P")
    c2 = _cluster(client, code="N96Q")
    _resource(client, c1["code"], hostname="gpu01", resource_type="BARE_METAL", role="COMPUTE", status="IDLE")
    _resource(client, c1["code"], hostname="login01", resource_type="VIRTUAL_MACHINE", role="LOGIN", status="ALLOC")
    third = _resource(client, c2["code"], hostname="alpha")
    client.delete(f"/api/v1/resources/{third['id']}", params={"version": 1})

    default = client.get("/api/v1/resources").json()
    assert default["total"] == 2
    assert default["page"] == 1 and default["page_size"] == 20

    filtered = client.get(
        "/api/v1/resources",
        params={
            "cluster": "N96P",
            "type": "BARE_METAL",
            "role": "COMPUTE",
            "status": "IDLE",
        },
    ).json()
    assert filtered["total"] == 1 and filtered["items"][0]["hostname"] == "gpu01"

    by_id = client.get("/api/v1/resources", params={"cluster_id": c1["id"]}).json()
    assert by_id["total"] == 2

    nonexistent = client.get("/api/v1/resources", params={"cluster": "NOPE"}).json()
    assert nonexistent["total"] == 0 and nonexistent["items"] == []

    search = client.get("/api/v1/resources", params={"q": "gpu"}).json()
    assert search["total"] == 1 and search["items"][0]["hostname"] == "gpu01"

    asc = client.get("/api/v1/resources", params={"sort": "hostname", "order": "asc"}).json()
    assert [i["hostname"] for i in asc["items"]] == ["gpu01", "login01"]
    desc = client.get("/api/v1/resources", params={"sort": "hostname", "order": "desc"}).json()
    assert [i["hostname"] for i in desc["items"]] == ["login01", "gpu01"]

    page = client.get(
        "/api/v1/resources",
        params={"page": 2, "page_size": 1, "sort": "hostname", "order": "asc"},
    ).json()
    assert page["items"][0]["hostname"] == "login01"
    assert page["total"] == 2

    for bad_params in (
        {"page": 0},
        {"page_size": 0},
        {"page_size": 101},
        {"sort": "id"},
        {"order": "random"},
        {"type": "STORAGE"},
        {"role": "BOGUS"},
        {"status": "RUNNING"},
        {"deleted": "sometimes"},
        {"cluster_id": "not-a-uuid"},
        {"cluster": "bad code"},
    ):
        resp = client.get("/api/v1/resources", params=bad_params)
        assert resp.status_code == 422, (bad_params, resp.text)


def test_search_ilike_case_insensitive(role_client_factory):
    client, _, _ = role_client_factory("EDITOR")
    c1 = _cluster(client, code="C1")
    _resource(client, c1["code"], hostname="cn001")
    _resource(client, c1["code"], hostname="cn001x")
    _resource(client, c1["code"], hostname="node01")
    hit = client.get("/api/v1/resources", params={"q": "CN00"}).json()
    assert hit["total"] == 2
    assert {i["hostname"] for i in hit["items"]} == {"cn001", "cn001x"}


# --- A8: detail overview -----------------------------------------------------


def test_detail_overview(role_client_factory):
    client, _, _ = role_client_factory("EDITOR")
    c1 = _cluster(client, code="C1")
    created = _resource(client, c1["code"], hostname="cn001", description="host")
    detail = client.get(f"/api/v1/resources/{created['id']}")
    assert detail.status_code == 200
    body = detail.json()["resource"]
    assert body["hostname"] == "cn001"
    assert body["cluster"]["code"] == "C1"
    assert body["resource_type"] == "BARE_METAL"
    assert body["role"] == "OTHER"
    assert body["status"] == "UNKNOWN"
    assert body["description"] == "host"
    assert client.get("/api/v1/resources/not-a-uuid").status_code == 404


# --- A9/B23-B29: soft delete visibility and restore --------------------------


def test_soft_delete_visibility_and_permissions(role_client_factory):
    admin, _, _ = role_client_factory("ADMIN")
    c1 = _cluster(admin, code="C1")
    created = _resource(admin, c1["code"], hostname="hidden")
    assert (
        admin.delete(
            f"/api/v1/resources/{created['id']}", params={"version": 1}
        ).status_code
        == 204
    )

    viewer, _, _ = role_client_factory("VIEWER")
    editor, _, _ = role_client_factory("EDITOR")
    assert viewer.get("/api/v1/resources").json()["total"] == 0
    for client in (viewer, editor):
        for mode in ("include", "only"):
            resp = client.get("/api/v1/resources", params={"deleted": mode})
            assert resp.status_code == 403
            assert resp.json()["error"]["details"] == {"reason": "permission"}

    included = admin.get("/api/v1/resources", params={"deleted": "include"}).json()
    assert included["total"] == 1 and included["items"][0]["deleted_at"] is not None
    only = admin.get("/api/v1/resources", params={"deleted": "only"}).json()
    assert only["total"] == 1

    assert viewer.get(f"/api/v1/resources/{created['id']}").status_code == 404
    assert (
        viewer.get(
            f"/api/v1/resources/{created['id']}", params={"deleted": "true"}
        ).status_code
        == 403
    )
    assert (
        admin.get(
            f"/api/v1/resources/{created['id']}", params={"deleted": "true"}
        ).status_code
        == 200
    )


def test_restore_not_deleted(role_client_factory):
    admin, _, _ = role_client_factory("ADMIN")
    c1 = _cluster(admin, code="C1")
    created = _resource(admin, c1["code"], hostname="r1")
    resp = admin.post(
        f"/api/v1/resources/{created['id']}/restore", params={"version": 1}
    )
    assert resp.status_code == 409
    assert resp.json()["error"]["details"] == {"reason": "not_deleted"}


def test_restore_unique_conflict_after_recreate(role_client_factory):
    admin, _, _ = role_client_factory("ADMIN")
    c1 = _cluster(admin, code="C1")
    first = _resource(admin, c1["code"], hostname="cn001")
    assert (
        admin.delete(
            f"/api/v1/resources/{first['id']}", params={"version": first["version"]}
        ).status_code
        == 204
    )
    replacement = _resource(admin, c1["code"], hostname="cn001")
    assert replacement["id"] != first["id"]

    resp = admin.post(
        f"/api/v1/resources/{first['id']}/restore", params={"version": 2}
    )
    assert resp.status_code == 409
    assert resp.json()["error"]["details"] == {
        "reason": "unique_conflict",
        "field": "hostname",
    }
    still = admin.get(
        f"/api/v1/resources/{first['id']}", params={"deleted": "true"}
    ).json()["resource"]
    assert still["deleted_at"] is not None


def test_restore_dependency_deleted(role_client_factory):
    admin, _, _ = role_client_factory("ADMIN")
    c1 = _cluster(admin, code="C1")
    created = _resource(admin, c1["code"], hostname="cn001")
    assert (
        admin.delete(
            f"/api/v1/resources/{created['id']}", params={"version": 1}
        ).status_code
        == 204
    )
    # resource is soft-deleted -> cluster can now be deleted
    assert (
        admin.delete(
            f"/api/v1/clusters/{c1['id']}", params={"version": 1}
        ).status_code
        == 204
    )
    resp = admin.post(
        f"/api/v1/resources/{created['id']}/restore", params={"version": 2}
    )
    assert resp.status_code == 409
    details = resp.json()["error"]["details"]
    assert details["reason"] == "dependency_deleted"
    assert details["conflicts"] == [{"object_type": "cluster", "object_id": c1["id"]}]


def test_restore_success_does_not_cascade(role_client_factory):
    admin, _, _ = role_client_factory("ADMIN")
    c1 = _cluster(admin, code="C1")
    first = _resource(admin, c1["code"], hostname="cn001")
    second = _resource(admin, c1["code"], hostname="cn002")
    assert (
        admin.delete(
            f"/api/v1/resources/{second['id']}", params={"version": second["version"]}
        ).status_code
        == 204
    )
    assert (
        admin.delete(
            f"/api/v1/resources/{first['id']}", params={"version": first["version"]}
        ).status_code
        == 204
    )
    restored = admin.post(
        f"/api/v1/resources/{first['id']}/restore", params={"version": 2}
    )
    assert restored.status_code == 200
    assert restored.json()["resource"]["deleted_at"] is None
    # second stays deleted
    other = admin.get(
        f"/api/v1/resources/{second['id']}", params={"deleted": "true"}
    ).json()["resource"]
    assert other["deleted_at"] is not None


# --- A10/B30-B34: audit and activity -----------------------------------------


def test_audit_four_actions_activity_and_serialisable(role_client_factory, auth_session_factory):
    admin, _, _ = role_client_factory("ADMIN")
    c1 = _cluster(admin, code="C1")
    created = _resource(admin, c1["code"], hostname="aud", metadata={"a": 1})
    rid = created["id"]

    assert (
        admin.patch(
            f"/api/v1/resources/{rid}", json={"version": 1, "role": "GPU"}
        ).status_code
        == 200
    )
    assert admin.delete(f"/api/v1/resources/{rid}", params={"version": 2}).status_code == 204
    assert (
        admin.post(f"/api/v1/resources/{rid}/restore", params={"version": 3}).status_code
        == 200
    )

    with auth_session_factory() as session:
        rows = (
            session.execute(
                select(AuditLog)
                .where(AuditLog.object_id == uuid.UUID(rid))
                .order_by(AuditLog.created_at)
            )
            .scalars()
            .all()
        )
        assert [r.action for r in rows] == ["CREATE", "UPDATE", "DELETE", "RESTORE"]
        assert rows[0].before_data is None and rows[0].after_data is not None
        assert rows[2].after_data is None and rows[2].before_data is not None
        for row in rows:
            assert row.object_type == "resource"
            for snapshot in (row.before_data, row.after_data):
                if snapshot is not None:
                    assert set(snapshot) == RESOURCE_AUDIT_KEYS
                    assert not ({"password", "token", "secret"} & set(snapshot))
                    json.dumps(snapshot)  # serialisable

    activity = admin.get(f"/api/v1/resources/{rid}/activity")
    assert activity.status_code == 200
    body = activity.json()
    assert body["total"] == 4
    assert [item["action"] for item in body["items"]] == [
        "CREATE",
        "UPDATE",
        "DELETE",
        "RESTORE",
    ]
    for role in ("VIEWER", "EDITOR"):
        client, _, _ = role_client_factory(role)
        assert client.get(f"/api/v1/resources/{rid}/activity").status_code == 200


def test_audit_rolls_back_with_business_write(
    role_client_factory, auth_session_factory, monkeypatch
):
    _, admin_user, _ = role_client_factory("ADMIN")
    operator = _operator(admin_user)

    original_record = audit_service.record

    def corrupt_record(*args, **kwargs):
        row = original_record(*args, **kwargs)
        row.action = "BOGUS"
        return row

    # Create the owning cluster before corrupting the shared audit module.
    with auth_session_factory() as session:
        cluster_service.create_cluster(session, operator, code="RB", name="rb")

    monkeypatch.setattr(resource_service.audit, "record", corrupt_record)

    with auth_session_factory() as session:
        with pytest.raises(Exception):
            resource_service.create_resource(
                session, operator, cluster="RB", hostname="rollback", resource_type="BARE_METAL"
            )
        session.rollback()

    with auth_session_factory() as session:
        assert (
            session.execute(
                select(Resource).where(Resource.hostname == "rollback")
            ).scalars().all()
            == []
        )
        assert (
            session.execute(
                select(AuditLog).where(AuditLog.action == "BOGUS")
            ).scalars().all()
            == []
        )


# --- A11/B35: permissions and optimistic locking -----------------------------


def test_permission_matrix(role_client_factory):
    admin, _, _ = role_client_factory("ADMIN")
    c1 = _cluster(admin, code="C1")
    created = _resource(admin, c1["code"], hostname="perm")

    viewer, _, _ = role_client_factory("VIEWER")
    editor, _, _ = role_client_factory("EDITOR")
    assert viewer.get("/api/v1/resources").status_code == 200
    assert viewer.post("/api/v1/resources", json={"cluster": c1["code"], "hostname": "v", "resource_type": "BARE_METAL"}).status_code == 403
    assert viewer.patch(f"/api/v1/resources/{created['id']}", json={"version": 1, "role": "GPU"}).status_code == 403
    assert viewer.delete(f"/api/v1/resources/{created['id']}", params={"version": 1}).status_code == 403
    assert viewer.post(f"/api/v1/resources/{created['id']}/restore", params={"version": 1}).status_code == 403

    assert editor.patch(f"/api/v1/resources/{created['id']}", json={"version": 1, "role": "GPU"}).status_code == 200
    assert editor.delete(f"/api/v1/resources/{created['id']}", params={"version": 2}).status_code == 403
    assert editor.post(f"/api/v1/resources/{created['id']}/restore", params={"version": 2}).status_code == 403


def test_optimistic_lock_two_sessions(auth_session_factory, make_user):
    user, _ = make_user(role="EDITOR")
    operator = _operator(user)

    with auth_session_factory() as setup:
        cluster_service.create_cluster(setup, operator, code="LCK", name="lock")
    with auth_session_factory() as setup:
        resource = resource_service.create_resource(
            setup, operator, cluster="LCK", hostname="lck", resource_type="BARE_METAL"
        )
        resource_id = resource.id

    first = auth_session_factory()
    second = auth_session_factory()
    try:
        r1 = resource_service.get_resource(first, resource_id)
        r2 = resource_service.get_resource(second, resource_id)
        assert r1.version == 1 and r2.version == 1

        resource_service.update_resource(
            first, operator, resource_id, expected_version=1, changes={"role": "GPU"}
        )
        with pytest.raises(VersionConflict) as exc:
            resource_service.update_resource(
                second, operator, resource_id, expected_version=1, changes={"role": "LOGIN"}
            )
        assert exc.value.details == {"current_version": 2}
        second.rollback()
    finally:
        first.close()
        second.close()

    with auth_session_factory() as verify:
        final = resource_service.get_resource(verify, resource_id)
        assert final.version == 2
        assert final.role == "GPU"


def test_patch_stale_version_returns_409(role_client_factory):
    admin, _, _ = role_client_factory("ADMIN")
    c1 = _cluster(admin, code="C1")
    created = _resource(admin, c1["code"], hostname="s")
    stale = admin.patch(
        f"/api/v1/resources/{created['id']}",
        json={"version": 99, "role": "GPU"},
    )
    assert stale.status_code == 409
    assert stale.json()["error"] == {
        "code": "VERSION_CONFLICT",
        "message": "Version conflict",
        "details": {"current_version": 1},
    }


def test_delete_and_restore_missing_version_is_422(role_client_factory):
    admin, _, _ = role_client_factory("ADMIN")
    c1 = _cluster(admin, code="C1")
    created = _resource(admin, c1["code"], hostname="v")
    assert admin.delete(f"/api/v1/resources/{created['id']}").status_code == 422
    assert admin.post(f"/api/v1/resources/{created['id']}/restore").status_code == 422


# --- A13/B40/B41/B46: identity, references, cluster delete -------------------


def test_patch_hostname_keeps_identity(role_client_factory):
    client, _, _ = role_client_factory("EDITOR")
    c1 = _cluster(client, code="C1")
    created = _resource(client, c1["code"], hostname="old")
    updated = client.patch(
        f"/api/v1/resources/{created['id']}",
        json={"version": 1, "hostname": "NEW"},
    ).json()["resource"]
    assert updated["id"] == created["id"]
    assert updated["created_at"] == created["created_at"]
    assert updated["hostname"] == "new"
    assert updated["version"] == 2


def test_cluster_reference_blocks_delete(role_client_factory):
    admin, _, _ = role_client_factory("ADMIN")
    c1 = _cluster(admin, code="C1")
    resource = _resource(admin, c1["code"], hostname="cn001")

    blocked = admin.delete(f"/api/v1/clusters/{c1['id']}", params={"version": 1})
    assert blocked.status_code == 409
    details = blocked.json()["error"]["details"]
    assert details["reason"] == "reference_exists"
    assert details["references"] == [
        {
            "object_type": "resource",
            "object_id": resource["id"],
            "label": "cn001",
        }
    ]

    # soft-deleting the resource releases the cluster for deletion
    assert (
        admin.delete(
            f"/api/v1/resources/{resource['id']}", params={"version": 1}
        ).status_code
        == 204
    )
    assert (
        admin.delete(f"/api/v1/clusters/{c1['id']}", params={"version": 1}).status_code
        == 204
    )


def test_delete_resource_reference_set_is_empty(role_client_factory):
    """F004: Resource itself is referenced by nobody -> delete always succeeds."""
    admin, _, _ = role_client_factory("ADMIN")
    c1 = _cluster(admin, code="C1")
    resource = _resource(admin, c1["code"], hostname="cn001")
    assert (
        admin.delete(
            f"/api/v1/resources/{resource['id']}", params={"version": 1}
        ).status_code
        == 204
    )


# --- unauthenticated ---------------------------------------------------------


def test_unauthenticated_is_401(api_client):
    assert api_client.get("/api/v1/resources").status_code == 401
    assert (
        api_client.post(
            "/api/v1/resources",
            json={"cluster": "C", "hostname": "h", "resource_type": "BARE_METAL"},
        ).status_code
        == 401
    )