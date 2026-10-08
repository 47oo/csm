"""F007 Interface API integration tests (A1-A19, V1-V30, B1-B52).

Requires a real PostgreSQL database via ``TEST_DATABASE_URL`` (DB-D10 guard in
``conftest``). Raw-SQL database/trigger/migration evidence lives in
``test_interface_constraints.py``.
"""

from __future__ import annotations

import threading
import time
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text

from app.core.auth import Operator
from app.core.errors import ValidationError, VersionConflict
from app.core.permissions import Role
from app.models.audit_log import AuditLog
from app.services import cluster as cluster_service
from app.services import interface as interface_service
from app.services import resource as resource_service

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


def _cluster(client, code="CL-001", name="Cluster"):
    resp = client.post("/api/v1/clusters", json={"code": code, "name": name})
    assert resp.status_code == 201, resp.text
    return resp.json()["cluster"]


def _bare_metal(client, cluster, hostname="host01", **overrides):
    body = {
        "cluster": cluster,
        "hostname": hostname,
        "resource_type": "BARE_METAL",
    }
    body.update(overrides)
    resp = client.post("/api/v1/resources", json=body)
    assert resp.status_code == 201, resp.text
    return resp.json()["resource"]


def _create_interface(client, resource_id, name="eth0", **overrides):
    body = {"resource": resource_id, "name": name}
    body.update(overrides)
    return client.post("/api/v1/interfaces", json=body)


def _interface(client, resource_id, name="eth0", **overrides):
    resp = _create_interface(client, resource_id, name=name, **overrides)
    assert resp.status_code == 201, resp.text
    return resp.json()["interface"]


def _operator(user) -> Operator:
    return Operator(user_id=user.id, username=user.username, role=Role(user.role))


def _row(session, interface_id):
    return session.execute(
        text(
            "SELECT resource_id, name, interface_type, mac_address, speed_mbps, "
            "mtu, parent_interface_id, enabled, description, metadata, version, "
            "deleted_at FROM interfaces WHERE id = :id"
        ),
        {"id": uuid.UUID(str(interface_id))},
    ).mappings().first()


# --- A2/A5/A6/V29: defaults and response shape --------------------------------


def test_create_defaults_and_response_shape(role_client_factory, auth_session_factory):
    client, _, _ = role_client_factory("EDITOR")
    c1 = _cluster(client, code="C1")
    res = _bare_metal(client, c1["code"], hostname="host-a")

    created = _interface(client, res["id"], name="bond0")
    assert created["resource"] == {"id": res["id"], "hostname": "host-a"}
    assert created["interface_type"] == "OTHER"  # not inferred from "bond0"
    assert created["enabled"] is True
    assert created["mac_address"] is None
    assert created["speed_mbps"] is None
    assert created["mtu"] is None
    assert created["parent_interface"] is None
    assert created["description"] is None
    assert created["metadata"] == {}
    assert created["version"] == 1
    assert created["deleted_at"] is None
    assert created["created_at"] and created["updated_at"]

    with auth_session_factory() as session:
        row = _row(session, created["id"])
        assert row["interface_type"] == "OTHER"
        assert row["enabled"] is True
        assert row["metadata"] == {}
        assert row["version"] == 1


def test_create_explicit_values(role_client_factory, auth_session_factory):
    client, _, _ = role_client_factory("EDITOR")
    c1 = _cluster(client, code="C1")
    res = _bare_metal(client, c1["code"])
    created = _interface(
        client,
        res["id"],
        name="eth1",
        interface_type="PHYSICAL",
        mac_address=" AA:BB:CC:DD:EE:FF ",
        speed_mbps=10000,
        mtu=9000,
        enabled=False,
        description="d",
        metadata={"a": 1},
    )
    assert created["interface_type"] == "PHYSICAL"
    assert created["mac_address"] == "AA:BB:CC:DD:EE:FF"  # trimmed, case kept
    assert created["speed_mbps"] == 10000 and created["mtu"] == 9000
    assert created["enabled"] is False
    assert created["description"] == "d" and created["metadata"] == {"a": 1}


# --- A1/A2/A3/A4: name normalisation and uniqueness ---------------------------


def test_name_normalisation_case_and_length(role_client_factory, auth_session_factory):
    client, _, _ = role_client_factory("EDITOR")
    c1 = _cluster(client, code="C1")
    res = _bare_metal(client, c1["code"])

    trimmed = _interface(client, res["id"], name="  eth0  ")
    assert trimmed["name"] == "eth0"
    upper = _interface(client, res["id"], name="ETH0")
    assert upper["name"] == "ETH0"
    max_len = _interface(client, res["id"], name="a" * 64)
    assert max_len["name"] == "a" * 64

    for bad in ("", "   ", "eth 0", "eth\t0", "eth\n0", "a" * 65, "e\x01th"):
        resp = _create_interface(client, res["id"], name=bad)
        assert resp.status_code == 422, (bad, resp.text)
        assert resp.json()["error"]["details"]["fields"][0]["field"] == "name"


def test_name_unique_partial_and_reuse(role_client_factory, auth_session_factory):
    admin, _, _ = role_client_factory("ADMIN")
    editor, _, _ = role_client_factory("EDITOR")
    c1 = _cluster(admin, code="C1")
    c2 = _cluster(admin, code="C2")
    r1 = _bare_metal(admin, c1["code"], hostname="r1")
    r2 = _bare_metal(admin, c2["code"], hostname="r2")

    first = _interface(editor, r1["id"], name="eth0")
    dup = _create_interface(editor, r1["id"], name="eth0")
    assert dup.status_code == 409, dup.text
    body = dup.json()["error"]
    assert body["code"] == "CONFLICT"
    assert body["details"] == {"reason": "unique_conflict", "field": "name"}
    # case-sensitive: ETH0 is allowed
    _interface(editor, r1["id"], name="ETH0")
    # cross-resource same name allowed
    _interface(editor, r2["id"], name="eth0")

    # soft delete releases the name
    assert admin.delete(
        f"/api/v1/interfaces/{first['id']}", params={"version": 1}
    ).status_code == 204
    recreated = _interface(editor, r1["id"], name="eth0")
    assert recreated["id"] != first["id"]


# --- A7/A10: type/mac/speed/mtu ----------------------------------------------


def test_type_mac_speed_mtu_validation(role_client_factory):
    client, _, _ = role_client_factory("EDITOR")
    c1 = _cluster(client, code="C1")
    res = _bare_metal(client, c1["code"])

    for bad in ("ETHERNET", "", None):
        resp = _create_interface(client, res["id"], name="t1", interface_type=bad)
        assert resp.status_code == 422, (bad, resp.text)
    for value in ("PHYSICAL", "VIRTUAL", "BOND", "BRIDGE", "VLAN", "LOOPBACK", "OTHER"):
        _interface(client, res["id"], name=f"type-{value}", interface_type=value)

    _interface(client, res["id"], name="mac-omitted")
    _interface(client, res["id"], name="mac-null", mac_address=None)
    _interface(client, res["id"], name="mac-a", mac_address="AA:BB:CC:DD:EE:FF")
    _interface(client, res["id"], name="mac-b", mac_address="AA:BB:CC:DD:EE:FF")
    for bad in ("", "   "):
        assert _create_interface(client, res["id"], name="mb", mac_address=bad).status_code == 422
    assert _create_interface(
        client, res["id"], name="mb2", mac_address="m" * 65
    ).status_code == 422

    for field in ("speed_mbps", "mtu"):
        _interface(client, res["id"], name=f"{field}-null", **{field: None})
        _interface(client, res["id"], name=f"{field}-1", **{field: 1})
        _interface(client, res["id"], name=f"{field}-max", **{field: 2147483647})
        for bad in (0, -1, 2147483648, "100", True):
            resp = _create_interface(client, res["id"], name=f"b-{field}-{bad}", **{field: bad})
            assert resp.status_code == 422, (field, bad, resp.text)


# --- A11: resource validation -------------------------------------------------


def test_resource_validation(role_client_factory, auth_session_factory):
    admin, _, _ = role_client_factory("ADMIN")
    editor, _, _ = role_client_factory("EDITOR")
    c1 = _cluster(admin, code="C1")
    res = _bare_metal(admin, c1["code"], hostname="r1")

    # missing / null / empty / random
    assert editor.post("/api/v1/interfaces", json={"name": "x"}).status_code == 422
    for bad in (None, "", "not-a-uuid"):
        resp = editor.post(
            "/api/v1/interfaces", json={"resource": bad, "name": "x"}
        )
        assert resp.status_code == 422, (bad, resp.text)
    resp = _create_interface(editor, str(uuid.uuid4()), name="x")
    assert resp.status_code == 422
    assert resp.json()["error"]["details"]["fields"][0]["field"] == "resource"

    # soft-deleted resource
    assert admin.delete(f"/api/v1/resources/{res['id']}", params={"version": 1}).status_code == 204
    resp = _create_interface(editor, res["id"], name="x")
    assert resp.status_code == 422
    assert resp.json()["error"]["details"]["fields"][0]["field"] == "resource"


# --- A8/A9: parent validation -------------------------------------------------


def test_parent_validation(role_client_factory):
    editor, _, _ = role_client_factory("EDITOR")
    admin, _, _ = role_client_factory("ADMIN")
    c1 = _cluster(editor, code="C1")
    c2 = _cluster(editor, code="C2")
    r1 = _bare_metal(editor, c1["code"], hostname="r1")
    r2 = _bare_metal(editor, c2["code"], hostname="r2")

    a = _interface(editor, r1["id"], name="a")
    b = _interface(editor, r1["id"], name="b")
    c = _interface(editor, r1["id"], name="c")
    foreign = _interface(editor, r2["id"], name="foreign")

    # omitted/null parent allowed
    _interface(editor, r1["id"], name="root1")
    _interface(editor, r1["id"], name="root2", parent_interface=None)

    # cross-resource
    resp = _create_interface(editor, r1["id"], name="x1", parent_interface=foreign["id"])
    assert resp.status_code == 422
    assert resp.json()["error"]["details"]["fields"][0]["field"] == "parent_interface"
    # nonexistent
    assert _create_interface(
        editor, r1["id"], name="x2", parent_interface=str(uuid.uuid4())
    ).status_code == 422
    # self-reference via PATCH
    assert editor.patch(
        f"/api/v1/interfaces/{a['id']}",
        json={"version": 1, "parent_interface": a["id"]},
    ).status_code == 422

    # 2-node cycle: a -> b then b -> a
    assert editor.patch(
        f"/api/v1/interfaces/{a['id']}",
        json={"version": 1, "parent_interface": b["id"]},
    ).status_code == 200
    assert editor.patch(
        f"/api/v1/interfaces/{b['id']}",
        json={"version": 1, "parent_interface": a["id"]},
    ).status_code == 422

    # 3-node cycle: b -> c then c -> a (a -> b -> c)
    assert editor.patch(
        f"/api/v1/interfaces/{b['id']}",
        json={"version": 1, "parent_interface": c["id"]},
    ).status_code == 200
    assert editor.patch(
        f"/api/v1/interfaces/{c['id']}",
        json={"version": 1, "parent_interface": a["id"]},
    ).status_code == 422

    # soft-deleted parent rejected
    assert admin.delete(
        f"/api/v1/interfaces/{foreign['id']}", params={"version": 1}
    ).status_code == 204
    resp = editor.patch(
        f"/api/v1/interfaces/{c['id']}",
        json={"version": 1, "parent_interface": foreign["id"]},
    )
    assert resp.status_code == 422

    # clear a parent back to root
    cleared = editor.patch(
        f"/api/v1/interfaces/{a['id']}",
        json={"version": 2, "parent_interface": None},
    )
    assert cleared.status_code == 200
    assert cleared.json()["interface"]["parent_interface"] is None


# --- V20/B43-B46: PATCH exclude_unset / immutable -----------------------------


def test_patch_exclude_unset_and_immutable(role_client_factory):
    editor, _, _ = role_client_factory("EDITOR")
    c1 = _cluster(editor, code="C1")
    res = _bare_metal(editor, c1["code"])
    created = _interface(
        editor,
        res["id"],
        name="p0",
        interface_type="PHYSICAL",
        mac_address="AA:BB",
        speed_mbps=1000,
        mtu=1500,
        description="keep",
        metadata={"a": 1},
    )
    assert created["version"] == 1

    # omitted fields keep their value
    updated = editor.patch(
        f"/api/v1/interfaces/{created['id']}",
        json={"version": 1, "mtu": 9000},
    )
    assert updated.status_code == 200, updated.text
    body = updated.json()["interface"]
    assert body["mtu"] == 9000
    assert body["name"] == "p0" and body["mac_address"] == "AA:BB"
    assert body["speed_mbps"] == 1000 and body["description"] == "keep"
    assert body["metadata"] == {"a": 1}
    assert body["version"] == 2

    # explicit null clears nullable fields
    cleared = editor.patch(
        f"/api/v1/interfaces/{created['id']}",
        json={
            "version": 2,
            "mac_address": None,
            "speed_mbps": None,
            "mtu": None,
            "parent_interface": None,
            "description": None,
        },
    ).json()["interface"]
    assert cleared["mac_address"] is None and cleared["speed_mbps"] is None
    assert cleared["mtu"] is None and cleared["parent_interface"] is None
    assert cleared["description"] is None

    # explicit null on non-nullable -> 422
    for field in ("name", "interface_type", "enabled", "metadata"):
        assert editor.patch(
            f"/api/v1/interfaces/{created['id']}",
            json={"version": 3, field: None},
        ).status_code == 422, field
    # metadata replacement semantics
    replaced = editor.patch(
        f"/api/v1/interfaces/{created['id']}",
        json={"version": 3, "metadata": {"b": 2}},
    ).json()["interface"]
    assert replaced["metadata"] == {"b": 2}
    assert editor.patch(
        f"/api/v1/interfaces/{created['id']}",
        json={"version": 4, "metadata": [1, 2]},
    ).status_code == 422

    # immutable / read-only / unknown fields -> 422
    for payload in (
        {"version": 4, "resource": res["id"]},
        {"version": 4, "id": str(uuid.uuid4())},
        {"version": 4, "created_at": "2026-01-01T00:00:00+00:00"},
        {"version": 4, "unknown": 1},
        {"resource": res["id"]},  # version missing
    ):
        assert editor.patch(
            f"/api/v1/interfaces/{created['id']}", json=payload
        ).status_code == 422, payload


# --- V21/B47: list filters / sorting / pagination -----------------------------


def test_list_filters_sorting_pagination(role_client_factory, auth_session_factory):
    editor, _, _ = role_client_factory("EDITOR")
    admin, _, _ = role_client_factory("ADMIN")
    c1 = _cluster(editor, code="C1")
    r1 = _bare_metal(editor, c1["code"], hostname="r1")
    r2 = _bare_metal(editor, c1["code"], hostname="r2")

    parent = _interface(editor, r1["id"], name="parent")
    _interface(editor, r1["id"], name="eth0", interface_type="PHYSICAL", enabled=True)
    _interface(editor, r1["id"], name="ETH0", interface_type="VIRTUAL", enabled=False)
    _interface(editor, r1["id"], name="child", parent_interface=parent["id"])
    _interface(editor, r2["id"], name="eth0")

    listed = editor.get("/api/v1/interfaces", params={"resource_id": r1["id"]}).json()
    assert listed["total"] == 4
    assert all(i["resource"]["id"] == r1["id"] for i in listed["items"])

    # interface_type filter
    phys = editor.get("/api/v1/interfaces", params={"interface_type": "PHYSICAL"}).json()
    assert {i["name"] for i in phys["items"]} == {"eth0"}
    assert editor.get("/api/v1/interfaces", params={"interface_type": "NOPE"}).status_code == 422

    # enabled filter
    disabled = editor.get("/api/v1/interfaces", params={"enabled": "false"}).json()
    assert {i["name"] for i in disabled["items"]} == {"ETH0"}
    assert editor.get("/api/v1/interfaces", params={"enabled": "maybe"}).status_code == 422

    # case-sensitive substring q
    lower = editor.get("/api/v1/interfaces", params={"q": "eth"}).json()
    upper = editor.get("/api/v1/interfaces", params={"q": "ETH"}).json()
    assert {i["name"] for i in lower["items"]} == {"eth0"}
    assert {i["name"] for i in upper["items"]} == {"ETH0"}

    # parent filter + non-UUID -> 422
    children = editor.get(
        "/api/v1/interfaces", params={"parent_interface_id": parent["id"]}
    ).json()
    assert {i["name"] for i in children["items"]} == {"child"}
    assert editor.get(
        "/api/v1/interfaces", params={"parent_interface_id": "nope"}
    ).status_code == 422
    assert editor.get("/api/v1/interfaces", params={"resource_id": "nope"}).status_code == 422

    # sort name ascending (raw-value key; compare against the database order)
    listed_names = [
        i["name"]
        for i in editor.get(
            "/api/v1/interfaces", params={"sort": "name", "order": "asc", "page_size": 100}
        ).json()["items"]
    ]
    with auth_session_factory() as session:
        expected_names = [
            row[0]
            for row in session.execute(
                text(
                    "SELECT name FROM interfaces WHERE deleted_at IS NULL "
                    "ORDER BY name ASC, id ASC"
                )
            ).all()
        ]
    assert listed_names == expected_names
    assert set(listed_names) == {"parent", "eth0", "ETH0", "child"}

    # pagination
    page = editor.get(
        "/api/v1/interfaces", params={"page": 1, "page_size": 2, "sort": "name", "order": "asc"}
    ).json()
    assert page["total"] == 5 and len(page["items"]) == 2

    # deleted include needs VIEW_DELETED
    assert editor.get("/api/v1/interfaces", params={"deleted": "include"}).status_code == 403
    assert admin.get("/api/v1/interfaces", params={"deleted": "include"}).status_code == 200
    assert editor.get("/api/v1/interfaces", params={"deleted": "nope"}).status_code == 422


# --- A12/A13/V12/V13/V26/V27: lifecycle + references --------------------------


def test_soft_delete_visibility_and_restore(role_client_factory):
    admin, _, _ = role_client_factory("ADMIN")
    editor, _, _ = role_client_factory("EDITOR")
    c1 = _cluster(admin, code="C1")
    res = _bare_metal(admin, c1["code"], hostname="r1")
    iface = _interface(admin, res["id"], name="eth0")

    resp = admin.delete(f"/api/v1/interfaces/{iface['id']}", params={"version": 1})
    assert resp.status_code == 204
    assert editor.get(f"/api/v1/interfaces/{iface['id']}").status_code == 404
    assert editor.get(
        f"/api/v1/interfaces/{iface['id']}", params={"deleted": "true"}
    ).status_code == 403
    detail = admin.get(
        f"/api/v1/interfaces/{iface['id']}", params={"deleted": "true"}
    ).json()["interface"]
    assert detail["deleted_at"] is not None

    # restore: not_deleted when already live
    assert admin.post(
        f"/api/v1/interfaces/{iface['id']}/restore", params={"version": 2}
    ).status_code == 200
    assert admin.post(
        f"/api/v1/interfaces/{iface['id']}/restore", params={"version": 3}
    ).status_code == 409
    body = admin.post(
        f"/api/v1/interfaces/{iface['id']}/restore", params={"version": 3}
    ).json()["error"]
    assert body["details"]["reason"] == "not_deleted"


def test_restore_rechecks_name(role_client_factory):
    admin, _, _ = role_client_factory("ADMIN")
    c1 = _cluster(admin, code="C1")
    res = _bare_metal(admin, c1["code"])
    a = _interface(admin, res["id"], name="eth0")
    assert admin.delete(
        f"/api/v1/interfaces/{a['id']}", params={"version": 1}
    ).status_code == 204
    b = _interface(admin, res["id"], name="eth0")  # reuse the released name
    resp = admin.post(f"/api/v1/interfaces/{a['id']}/restore", params={"version": 2})
    assert resp.status_code == 409, resp.text
    assert resp.json()["error"]["details"]["reason"] == "unique_conflict"
    # b is untouched; a stays soft-deleted
    assert admin.get(f"/api/v1/interfaces/{b['id']}").status_code == 200
    assert admin.get(f"/api/v1/interfaces/{a['id']}").status_code == 404


def test_restore_rechecks_resource_and_parent(role_client_factory):
    admin, _, _ = role_client_factory("ADMIN")
    c1 = _cluster(admin, code="C1")
    res = _bare_metal(admin, c1["code"])
    parent = _interface(admin, res["id"], name="parent")
    child = _interface(admin, res["id"], name="child", parent_interface=parent["id"])

    # child restore after the parent is soft-deleted -> dependency_deleted(interface)
    assert admin.delete(
        f"/api/v1/interfaces/{child['id']}", params={"version": 1}
    ).status_code == 204
    assert admin.delete(
        f"/api/v1/interfaces/{parent['id']}", params={"version": 1}
    ).status_code == 204
    resp = admin.post(
        f"/api/v1/interfaces/{child['id']}/restore", params={"version": 2}
    )
    assert resp.status_code == 409
    conflicts = resp.json()["error"]["details"]["conflicts"]
    assert conflicts == [{"object_type": "interface", "object_id": parent["id"]}]

    # restore the parent, then the child
    assert admin.post(
        f"/api/v1/interfaces/{parent['id']}/restore", params={"version": 2}
    ).status_code == 200
    assert admin.post(
        f"/api/v1/interfaces/{child['id']}/restore", params={"version": 2}
    ).status_code == 200

    # resource dependency: soft-delete the child, soft-delete the resource,
    # restore the child -> dependency_deleted(resource)
    orphan = _interface(admin, res["id"], name="orphan")
    assert admin.delete(
        f"/api/v1/interfaces/{orphan['id']}", params={"version": 1}
    ).status_code == 204
    # delete every live interface so the resource can be soft-deleted
    for iid, version in ((child["id"], 3), (parent["id"], 3)):
        assert admin.delete(f"/api/v1/interfaces/{iid}", params={"version": version}).status_code == 204
    assert admin.delete(f"/api/v1/resources/{res['id']}", params={"version": 1}).status_code == 204
    resp = admin.post(
        f"/api/v1/interfaces/{orphan['id']}/restore", params={"version": 2}
    )
    assert resp.status_code == 409
    conflicts = resp.json()["error"]["details"]["conflicts"]
    assert conflicts == [{"object_type": "resource", "object_id": res["id"]}]


def test_delete_reference_protection(role_client_factory):
    admin, _, _ = role_client_factory("ADMIN")
    c1 = _cluster(admin, code="C1")
    res = _bare_metal(admin, c1["code"], hostname="host-ref")
    parent = _interface(admin, res["id"], name="parent")
    child = _interface(admin, res["id"], name="child", parent_interface=parent["id"])

    # parent delete blocked by an undeleted child (DR-80)
    resp = admin.delete(f"/api/v1/interfaces/{parent['id']}", params={"version": 1})
    assert resp.status_code == 409, resp.text
    body = resp.json()["error"]
    assert body["details"]["reason"] == "reference_exists"
    assert body["details"]["references"] == [
        {"object_type": "interface", "object_id": child["id"], "label": "child"}
    ]

    # Resource delete blocked by an undeleted Interface (F007 narrows F004)
    resp = admin.delete(f"/api/v1/resources/{res['id']}", params={"version": 1})
    assert resp.status_code == 409
    refs = resp.json()["error"]["details"]["references"]
    assert {r["object_id"] for r in refs} == {parent["id"], child["id"]}

    # child then parent can be deleted; then the resource
    assert admin.delete(f"/api/v1/interfaces/{child['id']}", params={"version": 1}).status_code == 204
    assert admin.delete(f"/api/v1/interfaces/{parent['id']}", params={"version": 1}).status_code == 204
    assert admin.delete(f"/api/v1/resources/{res['id']}", params={"version": 1}).status_code == 204


def test_f010_ip_reference_checker_is_reserved_empty():
    """The F010 interface<-IPAddress checker exists and returns an empty set."""
    assert (
        interface_service._undeleted_ip_address_references(None, uuid.uuid4()) == []
    )


# --- A15/V15/B40: audit and activity ------------------------------------------


def test_audit_four_actions_and_activity(role_client_factory, auth_session_factory):
    admin, _, _ = role_client_factory("ADMIN")
    viewer, _, _ = role_client_factory("VIEWER")
    c1 = _cluster(admin, code="C1")
    res = _bare_metal(admin, c1["code"])
    iface = _interface(admin, res["id"], name="eth0", speed_mbps=1000)
    edited = admin.patch(
        f"/api/v1/interfaces/{iface['id']}",
        json={"version": 1, "mtu": 1500},
    )
    assert edited.status_code == 200
    assert admin.delete(
        f"/api/v1/interfaces/{iface['id']}", params={"version": 2}
    ).status_code == 204
    assert admin.post(
        f"/api/v1/interfaces/{iface['id']}/restore", params={"version": 3}
    ).status_code == 200

    with auth_session_factory() as session:
        rows = (
            session.execute(
                select(AuditLog)
                .where(AuditLog.object_id == uuid.UUID(iface["id"]))
                .order_by(AuditLog.created_at, AuditLog.id)
            )
            .scalars()
            .all()
        )
        assert [r.action for r in rows] == ["CREATE", "UPDATE", "DELETE", "RESTORE"]
        assert all(r.object_type == "interface" for r in rows)
        update = rows[1]
        assert set(update.before_data) == {
            "resource_id",
            "name",
            "interface_type",
            "mac_address",
            "speed_mbps",
            "mtu",
            "parent_interface_id",
            "enabled",
            "description",
            "metadata",
        }
        assert update.before_data["mtu"] is None and update.after_data["mtu"] == 1500
        assert rows[2].after_data is None  # DELETE snapshot

    # activity is READ/VIEW_ACTIVITY for all roles and ascending
    for client in (viewer, admin):
        activity = client.get(f"/api/v1/interfaces/{iface['id']}/activity")
        assert activity.status_code == 200, activity.text
        assert [i["action"] for i in activity.json()["items"]] == [
            "CREATE",
            "UPDATE",
            "DELETE",
            "RESTORE",
        ]


def test_audit_rolls_back_with_the_transaction(auth_session_factory, make_user, monkeypatch):
    user, _ = make_user(role="EDITOR")
    operator = _operator(user)
    with auth_session_factory() as session:
        cluster_service.create_cluster(session, operator, code="RB", name="rb")
    with auth_session_factory() as session:
        res = resource_service.create_resource(
            session, operator, cluster="RB", hostname="rbh", resource_type="BARE_METAL"
        )
        res_id = res.id
    with auth_session_factory() as session:
        iface = interface_service.create_interface(
            session, operator, resource=res_id, name="eth0", mtu=1000
        )
        iface_id = iface.id

    original = interface_service.audit.record

    def corrupt(*args, **kwargs):
        row = original(*args, **kwargs)
        row.action = "BOGUS"  # violates the audit_logs action CHECK
        return row

    monkeypatch.setattr(interface_service.audit, "record", corrupt)
    with auth_session_factory() as session:
        with pytest.raises(Exception):
            interface_service.update_interface(
                session, operator, iface_id, expected_version=1, changes={"mtu": 9000}
            )
        session.rollback()

    with auth_session_factory() as session:
        assert _row(session, iface_id)["mtu"] == 1000  # rolled back
        assert (
            session.execute(select(AuditLog).where(AuditLog.action == "BOGUS"))
            .scalars()
            .all()
            == []
        )


# --- A14: permission matrix ---------------------------------------------------


def test_permission_matrix(role_client_factory, auth_app):
    admin, _, _ = role_client_factory("ADMIN")
    editor, _, _ = role_client_factory("EDITOR")
    viewer, _, _ = role_client_factory("VIEWER")
    c1 = _cluster(admin, code="C1")
    res = _bare_metal(admin, c1["code"])
    iface = _interface(admin, res["id"], name="perm")

    assert viewer.get(f"/api/v1/interfaces/{iface['id']}").status_code == 200
    assert viewer.get(f"/api/v1/interfaces/{iface['id']}/activity").status_code == 200
    assert viewer.post(
        "/api/v1/interfaces", json={"resource": res["id"], "name": "v"}
    ).status_code == 403
    assert viewer.patch(
        f"/api/v1/interfaces/{iface['id']}", json={"version": 1, "mtu": 100}
    ).status_code == 403
    assert viewer.delete(
        f"/api/v1/interfaces/{iface['id']}", params={"version": 1}
    ).status_code == 403

    assert editor.patch(
        f"/api/v1/interfaces/{iface['id']}", json={"version": 1, "mtu": 100}
    ).status_code == 200
    assert editor.delete(
        f"/api/v1/interfaces/{iface['id']}", params={"version": 2}
    ).status_code == 403

    assert admin.delete(
        f"/api/v1/interfaces/{iface['id']}", params={"version": 2}
    ).status_code == 204
    assert admin.post(
        f"/api/v1/interfaces/{iface['id']}/restore", params={"version": 3}
    ).status_code == 200

    # unauthenticated -> 401 before permission
    with TestClient(auth_app) as anon:
        assert anon.get("/api/v1/interfaces").status_code == 401


# --- V24/V30/B42: optimistic lock + validation order --------------------------


def test_optimistic_lock_two_sessions(auth_session_factory, make_user):
    user, _ = make_user(role="EDITOR")
    operator = _operator(user)
    with auth_session_factory() as session:
        cluster_service.create_cluster(session, operator, code="LK", name="lk")
    with auth_session_factory() as session:
        res = resource_service.create_resource(
            session, operator, cluster="LK", hostname="lkh", resource_type="BARE_METAL"
        )
        res_id = res.id
    with auth_session_factory() as session:
        iface = interface_service.create_interface(
            session, operator, resource=res_id, name="eth0", mtu=1000
        )
        iface_id = iface.id

    first = auth_session_factory()
    second = auth_session_factory()
    try:
        interface_service.update_interface(
            first, operator, iface_id, expected_version=1, changes={"mtu": 2000}
        )
        with pytest.raises(VersionConflict) as exc:
            interface_service.update_interface(
                second, operator, iface_id, expected_version=1, changes={"mtu": 3000}
            )
        assert exc.value.details == {"current_version": 2}
        second.rollback()
    finally:
        first.close()
        second.close()

    with auth_session_factory() as session:
        assert _row(session, iface_id)["mtu"] == 2000


def test_patch_validation_order(role_client_factory):
    editor, _, _ = role_client_factory("EDITOR")
    c1 = _cluster(editor, code="C1")
    res = _bare_metal(editor, c1["code"])
    a = _interface(editor, res["id"], name="a")
    _interface(editor, res["id"], name="b")

    # POST: invalid resource beats invalid parent
    resp = _create_interface(
        editor,
        str(uuid.uuid4()),
        name="x",
        parent_interface=str(uuid.uuid4()),
    )
    assert resp.status_code == 422
    assert resp.json()["error"]["details"]["fields"][0]["field"] == "resource"

    # PATCH: parent validation beats the version check
    resp = editor.patch(
        f"/api/v1/interfaces/{a['id']}",
        json={"version": 99, "parent_interface": str(uuid.uuid4())},
    )
    assert resp.status_code == 422
    assert resp.json()["error"]["details"]["fields"][0]["field"] == "parent_interface"

    # PATCH: version beats the name-uniqueness check
    resp = editor.patch(
        f"/api/v1/interfaces/{a['id']}",
        json={"version": 99, "name": "b"},
    )
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "VERSION_CONFLICT"


# --- DR-85/B50: parent cycle concurrency --------------------------------------


def _service_seed(auth_session_factory, make_user, code: str):
    user, _ = make_user(role="EDITOR")
    operator = _operator(user)
    with auth_session_factory() as session:
        cluster_service.create_cluster(session, operator, code=code, name=code)
    with auth_session_factory() as session:
        res = resource_service.create_resource(
            session,
            operator,
            cluster=code,
            hostname=f"{code.lower()}-h",
            resource_type="BARE_METAL",
        )
        res_id = res.id
    with auth_session_factory() as session:
        a = interface_service.create_interface(
            session, operator, resource=res_id, name="a"
        )
        b = interface_service.create_interface(
            session, operator, resource=res_id, name="b"
        )
        return operator, res_id, a.id, b.id


def test_parent_cycle_concurrency_serialised_by_resource_lock(
    auth_session_factory, make_user
):
    """DR-85/B50: two concurrent parent changes serialise on the Resource row and
    at most one succeeds; the final graph has no cycle."""
    operator, _res_id, a_id, b_id = _service_seed(auth_session_factory, make_user, "CONC")

    barrier = threading.Barrier(2)
    outcomes: list[str] = []
    lock = threading.Lock()

    def worker(child_id, parent_id):
        session = auth_session_factory()
        try:
            barrier.wait(timeout=10)
            interface_service.update_interface(
                session,
                operator,
                child_id,
                expected_version=1,
                changes={"parent_interface": parent_id},
            )
            with lock:
                outcomes.append("ok")
        except ValidationError:
            session.rollback()
            with lock:
                outcomes.append("cycle")
        except VersionConflict:
            session.rollback()
            with lock:
                outcomes.append("version")
        except Exception as exc:  # pragma: no cover - surfaced via assertion
            session.rollback()
            with lock:
                outcomes.append(f"error:{type(exc).__name__}")
        finally:
            session.close()

    threads = [
        threading.Thread(target=worker, args=(a_id, b_id)),
        threading.Thread(target=worker, args=(b_id, a_id)),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=20)

    assert "ok" in outcomes, outcomes
    assert sum(1 for o in outcomes if o == "ok") == 1, outcomes
    assert all(o in {"ok", "cycle", "version"} for o in outcomes), outcomes

    # final persisted graph must be acyclic
    with auth_session_factory() as session:
        rows = session.execute(
            text("SELECT id, parent_interface_id FROM interfaces")
        ).all()
        graph = {row[0]: row[1] for row in rows}
        for start in graph:
            seen = set()
            current = start
            while current is not None:
                assert current not in seen, "cycle persisted"
                seen.add(current)
                current = graph.get(current)


# --- DR-85/B51: resource soft delete vs interface create ----------------------


def test_resource_delete_vs_interface_create_concurrency(
    role_client_factory, committed_engine
):
    """A Resource soft delete serialises with an Interface create on the same
    Resource row: the create sees the deleted Resource and returns 422."""
    client, _, _ = role_client_factory("ADMIN")
    c1 = _cluster(client, code="CONC2")
    res = _bare_metal(client, c1["code"], hostname="conc2-host")
    res_id = uuid.UUID(res["id"])

    result: dict = {}

    def worker():
        try:
            resp = client.post(
                "/api/v1/interfaces",
                json={"resource": res["id"], "name": "race"},
            )
            result["status"] = resp.status_code
        except Exception as exc:  # pragma: no cover - surfaced via assertion
            result["error"] = repr(exc)

    conn = committed_engine.connect()
    txn = conn.begin()
    try:
        conn.execute(
            text("SELECT id FROM resources WHERE id = :id FOR UPDATE"), {"id": res_id}
        )
        thread = threading.Thread(target=worker)
        thread.start()
        time.sleep(0.6)
        assert thread.is_alive(), "create must block on the Resource row lock (DR-85)"
        conn.execute(
            text(
                "UPDATE resources SET deleted_at = now(), version = version + 1 "
                "WHERE id = :id"
            ),
            {"id": res_id},
        )
        txn.commit()
    finally:
        conn.close()
    thread.join(timeout=15)
    assert not thread.is_alive()
    assert result.get("status") == 422, result
    with committed_engine.connect() as check:
        assert check.execute(
            text("SELECT count(*) FROM interfaces WHERE resource_id = :id"),
            {"id": res_id},
        ).scalar_one() == 0