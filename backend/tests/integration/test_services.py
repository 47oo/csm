"""F011 Service API / business-service integration tests (A1-A18 F011 items).

Requires a real PostgreSQL database via ``TEST_DATABASE_URL`` (DB-D10 guard in
``conftest``). Raw-SQL constraint/partial-unique/FK/migration evidence lives in
``test_service_constraints.py``. The ServiceEndpoint reference data source is
F012; here the F011 default empty reference set plus a deterministic stub prove
the delete call chain without rewiring the registry.
"""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

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
    clients: list[TestClient] = []

    def _make(role: str):
        client, user, password = _login_client(auth_app, make_user, role)
        clients.append(client)
        return client, user, password

    yield _make
    for client in clients:
        client.__exit__(None, None, None)


def _cluster(client, code="C1", name="Cluster"):
    resp = client.post("/api/v1/clusters", json={"code": code, "name": name})
    assert resp.status_code == 201, resp.text
    return resp.json()["cluster"]


def _resource(client, cluster, hostname="host1", **overrides):
    body = {
        "cluster": cluster,
        "hostname": hostname,
        "resource_type": "BARE_METAL",
    }
    body.update(overrides)
    resp = client.post("/api/v1/resources", json=body)
    assert resp.status_code == 201, resp.text
    return resp.json()["resource"]


def _create_service(client, resource, name="ssh", **overrides):
    body = {"resource": resource, "name": name}
    body.update(overrides)
    return client.post("/api/v1/services", json=body)


def _service(client, resource, name="ssh", **overrides):
    resp = _create_service(client, resource, name=name, **overrides)
    assert resp.status_code == 201, resp.text
    return resp.json()["service"]


def _admin_setup(role_client_factory):
    client, user, password = role_client_factory("ADMIN")
    cluster = _cluster(client)
    resource = _resource(client, cluster["code"])
    return client, resource


# --- create defaults / response shape ----------------------------------------


def test_create_defaults_and_response_shape(role_client_factory, auth_session_factory):
    client, resource = _admin_setup(role_client_factory)
    created = _service(client, resource["id"], name="SSH")

    assert created["resource"] == {"id": resource["id"], "hostname": resource["hostname"]}
    assert created["name"] == "SSH"
    assert created["status"] == "UNKNOWN"
    assert created["description"] is None
    assert created["metadata"] == {}
    assert created["version"] == 1
    assert created["deleted_at"] is None
    assert created["created_at"] and created["updated_at"]
    assert "name_key" not in created

    with auth_session_factory() as session:
        row = session.execute(
            text("SELECT name_key, status FROM services WHERE id = :id"),
            {"id": uuid.UUID(created["id"])},
        ).mappings().one()
        assert row["name_key"] == "ssh"
        assert row["status"] == "UNKNOWN"


def test_audit_whitelist_row(role_client_factory, auth_session_factory):
    client, resource = _admin_setup(role_client_factory)
    created = _service(
        client, resource["id"], name="ssh", description="d", metadata={"a": 1}
    )
    with auth_session_factory() as session:
        row = session.execute(
            text(
                "SELECT object_type, action, after_data FROM audit_logs "
                "WHERE object_id = :id"
            ),
            {"id": uuid.UUID(created["id"])},
        ).mappings().one()
    assert row["object_type"] == "service"
    assert row["action"] == "CREATE"
    assert set(row["after_data"].keys()) == {
        "resource_id",
        "name",
        "status",
        "description",
        "metadata",
    }
    assert row["after_data"]["resource_id"] == resource["id"]


# --- A1: name normalisation ---------------------------------------------------


def test_name_trim_and_control_characters(role_client_factory):
    client, resource = _admin_setup(role_client_factory)
    assert _service(client, resource["id"], name="  ssh  ")["name"] == "ssh"
    # internal ordinary spaces + CJK preserved, not collapsed
    assert _service(client, resource["id"], name="web 服务")["name"] == "web 服务"

    for bad in ("", "   ", "\x01bad", "a\tb"):
        resp = _create_service(client, resource["id"], name=bad)
        assert resp.status_code == 422, (bad, resp.text)
        fields = resp.json()["error"]["details"]["fields"]
        assert fields[0]["field"] == "name"


# --- A2/A16: same-resource case-insensitive uniqueness ------------------------


def test_same_resource_name_unique_case_insensitive(role_client_factory):
    client, resource = _admin_setup(role_client_factory)
    other = _resource(client, _cluster(client, code="C2", name="C2")["code"], hostname="h2")
    _service(client, resource["id"], name="SSH")
    dup = _create_service(client, resource["id"], name="ssh")
    assert dup.status_code == 409, dup.text
    details = dup.json()["error"]["details"]
    assert details["reason"] == "unique_conflict"
    assert details["field"] == "name"
    # cross-resource same name allowed
    assert _service(client, other["id"], name="ssh")["name"] == "ssh"
    # ß is not ASCII-folded to ss: distinct from "ss"
    assert _service(client, resource["id"], name="ß")["name"] == "ß"
    assert _service(client, resource["id"], name="ss")["name"] == "ss"


# --- A3: soft-delete reuse + restore re-check ---------------------------------


def test_soft_delete_reuse_and_restore_conflict(role_client_factory):
    client, resource = _admin_setup(role_client_factory)
    original = _service(client, resource["id"], name="web")

    deleted = client.delete(
        f"/api/v1/services/{original['id']}", params={"version": original["version"]}
    )
    assert deleted.status_code == 204, deleted.text

    rebuilt = _service(client, resource["id"], name="web")
    assert rebuilt["id"] != original["id"]
    assert rebuilt["version"] == 1

    # restoring the old object conflicts with the live rebuilt name.
    conflict = client.post(
        f"/api/v1/services/{original['id']}/restore",
        params={"version": original["version"] + 1},
    )
    assert conflict.status_code == 409, conflict.text
    details = conflict.json()["error"]["details"]
    assert details["reason"] == "unique_conflict"
    assert details["field"] == "name"

    # the newer object is untouched
    detail = client.get(f"/api/v1/services/{rebuilt['id']}")
    assert detail.status_code == 200
    assert detail.json()["service"]["name"] == "web"


# --- A4: resource resolution --------------------------------------------------


def test_resource_required_and_must_exist(role_client_factory):
    client, resource = _admin_setup(role_client_factory)

    missing = client.post("/api/v1/services", json={"name": "x"})
    assert missing.status_code == 422
    assert any(
        f["field"] == "resource" for f in missing.json()["error"]["details"]["fields"]
    )

    ghost = _create_service(client, str(uuid.uuid4()), name="x")
    assert ghost.status_code == 422
    assert ghost.json()["error"]["details"]["fields"][0]["field"] == "resource"

    # soft-deleted resource is not selectable
    deleted = client.delete(
        f"/api/v1/resources/{resource['id']}", params={"version": resource["version"]}
    )
    assert deleted.status_code == 204, deleted.text
    resp = _create_service(client, resource["id"], name="x")
    assert resp.status_code == 422
    assert resp.json()["error"]["details"]["fields"][0]["field"] == "resource"


# --- A5/A6: status ------------------------------------------------------------


def test_status_default_and_values(role_client_factory):
    client, resource = _admin_setup(role_client_factory)
    # A6: a service registered as "slurmd" is not auto-derived to RUNNING.
    assert _service(client, resource["id"], name="slurmd")["status"] == "UNKNOWN"

    for status in ("RUNNING", "STOPPED", "UNKNOWN"):
        created = _service(client, resource["id"], name=f"s-{status}", status=status)
        assert created["status"] == status

    invalid = _create_service(client, resource["id"], name="bad", status="ACTIVE")
    assert invalid.status_code == 422
    assert invalid.json()["error"]["details"]["fields"][0]["field"] == "status"

    explicit_null = _create_service(client, resource["id"], name="null", status=None)
    assert explicit_null.status_code == 422

    created = _service(client, resource["id"], name="patch")
    null_patch = client.patch(
        f"/api/v1/services/{created['id']}",
        json={"version": created["version"], "status": None},
    )
    assert null_patch.status_code == 422
    assert null_patch.json()["error"]["details"]["fields"][0]["field"] == "status"


# --- A7: description ----------------------------------------------------------


def test_description_nullable_and_preserved(role_client_factory):
    client, resource = _admin_setup(role_client_factory)
    created = _service(client, resource["id"], name="d", description="hello")
    assert created["description"] == "hello"

    # omitted description keeps its value (exclude_unset)
    kept = client.patch(
        f"/api/v1/services/{created['id']}",
        json={"version": created["version"], "status": "RUNNING"},
    )
    assert kept.status_code == 200, kept.text
    assert kept.json()["service"]["description"] == "hello"

    # explicit null clears it
    cleared = client.patch(
        f"/api/v1/services/{created['id']}",
        json={"version": kept.json()["service"]["version"], "description": None},
    )
    assert cleared.status_code == 200, cleared.text
    assert cleared.json()["service"]["description"] is None


# --- A8: metadata -------------------------------------------------------------


def test_metadata_whole_replacement(role_client_factory):
    client, resource = _admin_setup(role_client_factory)
    created = _service(client, resource["id"], name="m", metadata={"a": 1, "b": 2})
    assert created["metadata"] == {"a": 1, "b": 2}

    replaced = client.patch(
        f"/api/v1/services/{created['id']}",
        json={"version": created["version"], "metadata": {"c": 3}},
    )
    assert replaced.status_code == 200, replaced.text
    assert replaced.json()["service"]["metadata"] == {"c": 3}

    for bad in (None, [1, 2], "str"):
        resp = client.patch(
            f"/api/v1/services/{created['id']}",
            json={"version": replaced.json()["service"]["version"], "metadata": bad},
        )
        assert resp.status_code == 422, (bad, resp.text)
        assert resp.json()["error"]["details"]["fields"][0]["field"] == "metadata"

    create_bad = _create_service(client, resource["id"], name="mb", metadata=[1])
    assert create_bad.status_code == 422


# --- A9: resource immutable ---------------------------------------------------


def test_resource_immutable(role_client_factory):
    client, resource = _admin_setup(role_client_factory)
    other = _resource(client, _cluster(client, code="C3", name="C3")["code"], hostname="h3")
    created = _service(client, resource["id"], name="imm")

    for field in ("resource", "resource_id", "id", "name_key"):
        resp = client.patch(
            f"/api/v1/services/{created['id']}",
            json={"version": created["version"], field: str(other["id"])},
        )
        assert resp.status_code == 422, (field, resp.text)


# --- A10: delete reference-check call chain (F011 empty set + stub) -----------


def test_delete_default_empty_reference_set(role_client_factory):
    from app.services import service_reference

    client, resource = _admin_setup(role_client_factory)
    created = _service(client, resource["id"], name="del")
    assert service_reference.check_service_references.__module__ == (
        "app.services.service_reference"
    )
    deleted = client.delete(
        f"/api/v1/services/{created['id']}", params={"version": created["version"]}
    )
    assert deleted.status_code == 204, deleted.text


def test_delete_reference_checker_stub_blocks(role_client_factory, monkeypatch):
    from app.services import service_reference

    client, resource = _admin_setup(role_client_factory)
    created = _service(client, resource["id"], name="blocked")
    endpoint_id = str(uuid.uuid4())
    monkeypatch.setattr(
        service_reference,
        "_CHECKERS",
        [
            lambda db, sid: [
                {
                    "object_type": "service_endpoint",
                    "object_id": endpoint_id,
                    "label": "tcp/22",
                }
            ]
        ],
    )
    resp = client.delete(
        f"/api/v1/services/{created['id']}", params={"version": created["version"]}
    )
    assert resp.status_code == 409, resp.text
    details = resp.json()["error"]["details"]
    assert details["reason"] == "reference_exists"
    assert details["references"][0]["object_type"] == "service_endpoint"
    assert details["references"][0]["object_id"] == endpoint_id


def test_undeleted_service_blocks_resource_delete(role_client_factory):
    client, resource = _admin_setup(role_client_factory)
    created = _service(client, resource["id"], name="hold")
    resp = client.delete(
        f"/api/v1/resources/{resource['id']}", params={"version": resource["version"]}
    )
    assert resp.status_code == 409, resp.text
    details = resp.json()["error"]["details"]
    assert details["reason"] == "reference_exists"
    refs = details["references"]
    assert any(r["object_type"] == "service" for r in refs)
    assert any(r["object_id"] == created["id"] for r in refs)


# --- A11: restore re-checks ---------------------------------------------------


def test_restore_dependency_resource_deleted(role_client_factory):
    client, resource = _admin_setup(role_client_factory)
    created = _service(client, resource["id"], name="dep")

    assert client.delete(
        f"/api/v1/services/{created['id']}", params={"version": created["version"]}
    ).status_code == 204
    # now the Resource has no undeleted Service, so it can be soft-deleted.
    assert client.delete(
        f"/api/v1/resources/{resource['id']}", params={"version": resource["version"]}
    ).status_code == 204

    resp = client.post(
        f"/api/v1/services/{created['id']}/restore",
        params={"version": created["version"] + 1},
    )
    assert resp.status_code == 409, resp.text
    details = resp.json()["error"]["details"]
    assert details["reason"] == "dependency_deleted"
    assert details["conflicts"][0]["object_type"] == "resource"


def test_restore_not_deleted(role_client_factory):
    client, resource = _admin_setup(role_client_factory)
    created = _service(client, resource["id"], name="live")
    resp = client.post(
        f"/api/v1/services/{created['id']}/restore",
        params={"version": created["version"]},
    )
    assert resp.status_code == 409
    assert resp.json()["error"]["details"]["reason"] == "not_deleted"


def test_restore_success_and_audit(role_client_factory):
    client, resource = _admin_setup(role_client_factory)
    created = _service(client, resource["id"], name="rest")
    client.delete(
        f"/api/v1/services/{created['id']}", params={"version": created["version"]}
    )
    resp = client.post(
        f"/api/v1/services/{created['id']}/restore",
        params={"version": created["version"] + 1},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["service"]["deleted_at"] is None
    assert resp.json()["service"]["version"] == created["version"] + 2


# --- A12: permissions ---------------------------------------------------------


def test_permissions(role_client_factory):
    admin, _, _ = role_client_factory("ADMIN")
    editor, _, _ = role_client_factory("EDITOR")
    viewer, _, _ = role_client_factory("VIEWER")

    cluster = _cluster(admin)
    resource = _resource(admin, cluster["code"])

    # VIEWER can read but not create / delete / restore / view deleted
    assert viewer.get("/api/v1/services").status_code == 200
    assert _create_service(viewer, resource["id"], name="v").status_code == 403
    created = _service(admin, resource["id"], name="perm")
    assert viewer.delete(
        f"/api/v1/services/{created['id']}", params={"version": 1}
    ).status_code == 403
    assert viewer.post(
        f"/api/v1/services/{created['id']}/restore", params={"version": 1}
    ).status_code == 403
    assert viewer.get("/api/v1/services?deleted=include").status_code == 403

    # EDITOR can create/update but not delete
    editor_created = _service(editor, resource["id"], name="edit")
    assert editor.delete(
        f"/api/v1/services/{editor_created['id']}", params={"version": 1}
    ).status_code == 403

    # unauthenticated first
    assert admin.get("/api/v1/services").status_code == 200


def test_view_deleted_and_detail(role_client_factory):
    admin, resource = _admin_setup(role_client_factory)
    created = _service(admin, resource["id"], name="vd")
    admin.delete(f"/api/v1/services/{created['id']}", params={"version": 1})

    # default detail of a soft-deleted service is 404
    assert admin.get(f"/api/v1/services/{created['id']}").status_code == 404
    detail = admin.get(
        f"/api/v1/services/{created['id']}", params={"deleted": "true"}
    )
    assert detail.status_code == 200
    assert detail.json()["service"]["deleted_at"] is not None


# --- A13: activity ------------------------------------------------------------


def test_activity_trail(role_client_factory, auth_session_factory):
    client, resource = _admin_setup(role_client_factory)
    created = _service(client, resource["id"], name="act")
    updated = client.patch(
        f"/api/v1/services/{created['id']}",
        json={"version": created["version"], "status": "RUNNING"},
    )
    assert updated.status_code == 200
    version = updated.json()["service"]["version"]
    assert client.delete(
        f"/api/v1/services/{created['id']}", params={"version": version}
    ).status_code == 204
    assert client.post(
        f"/api/v1/services/{created['id']}/restore", params={"version": version + 1}
    ).status_code == 200

    activity = client.get(f"/api/v1/services/{created['id']}/activity")
    assert activity.status_code == 200, activity.text
    body = activity.json()
    assert body["total"] == 4
    assert [item["action"] for item in body["items"]] == [
        "CREATE",
        "UPDATE",
        "DELETE",
        "RESTORE",
    ]


# --- A14: list filters / sort / pagination ------------------------------------


def test_list_filters_and_pagination(role_client_factory):
    client, resource = _admin_setup(role_client_factory)
    other = _resource(client, _cluster(client, code="C4", name="C4")["code"], hostname="h4")
    for name in ("alpha", "beta", "gamma"):
        _service(client, resource["id"], name=name, status="RUNNING")
    gone = _service(client, resource["id"], name="gone")
    client.delete(f"/api/v1/services/{gone['id']}", params={"version": 1})
    _service(client, other["id"], name="alpha-other", status="STOPPED")

    # default hides soft-deleted
    default = client.get("/api/v1/services", params={"page_size": 100}).json()
    assert default["total"] == 4
    assert all(item["deleted_at"] is None for item in default["items"])

    only_deleted = client.get(
        "/api/v1/services", params={"deleted": "only", "page_size": 100}
    ).json()
    assert only_deleted["total"] == 1
    assert only_deleted["items"][0]["name"] == "gone"

    by_resource = client.get(
        "/api/v1/services", params={"resource_id": other["id"], "page_size": 100}
    ).json()
    assert by_resource["total"] == 1
    assert by_resource["items"][0]["name"] == "alpha-other"

    by_status = client.get(
        "/api/v1/services", params={"status": "STOPPED", "page_size": 100}
    ).json()
    assert by_status["total"] == 1

    q = client.get("/api/v1/services", params={"q": "ALP", "page_size": 100}).json()
    assert q["total"] == 2

    paged = client.get(
        "/api/v1/services",
        params={"sort": "name", "order": "asc", "page": 1, "page_size": 2},
    ).json()
    assert len(paged["items"]) == 2
    assert paged["total"] == 4

    # invalid query parameters
    assert client.get("/api/v1/services", params={"deleted": "bad"}).status_code == 422
    assert client.get("/api/v1/services", params={"sort": "bogus"}).status_code == 422
    assert client.get("/api/v1/services", params={"status": "bogus"}).status_code == 422
    assert client.get(
        "/api/v1/services", params={"resource_id": "not-a-uuid"}
    ).status_code == 422


# --- A17: optimistic locking --------------------------------------------------


def test_optimistic_lock(role_client_factory):
    client, resource = _admin_setup(role_client_factory)
    created = _service(client, resource["id"], name="lock")
    first = client.patch(
        f"/api/v1/services/{created['id']}",
        json={"version": 1, "status": "RUNNING"},
    )
    assert first.status_code == 200
    assert first.json()["service"]["version"] == 2

    stale = client.patch(
        f"/api/v1/services/{created['id']}",
        json={"version": 1, "status": "STOPPED"},
    )
    assert stale.status_code == 409, stale.text
    details = stale.json()["error"]["details"]
    assert details["current_version"] == 2


# --- A18: nested resource -----------------------------------------------------


def test_nested_resource_and_query(role_client_factory):
    client, resource = _admin_setup(role_client_factory)
    _service(client, resource["id"], name="nested")
    listed = client.get("/api/v1/services").json()
    assert listed["items"][0]["resource"] == {
        "id": resource["id"],
        "hostname": resource["hostname"],
    }


# --- non-UUID path / 404 ------------------------------------------------------


def test_non_uuid_id_is_404(role_client_factory):
    client, _ = _admin_setup(role_client_factory)
    assert client.get("/api/v1/services/not-a-uuid").status_code == 404
    assert client.delete(
        "/api/v1/services/not-a-uuid", params={"version": 1}
    ).status_code == 404