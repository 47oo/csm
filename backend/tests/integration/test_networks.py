"""F008 Network API integration tests (A1-A22, V1-V30, B1-B36).

Requires a real PostgreSQL database via ``TEST_DATABASE_URL`` (DB-D10 guard in
``conftest``). Raw-SQL database/exclusion/migration evidence lives in
``test_network_constraints.py``; the concurrent exclusion test also lives there.
"""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text

from app.core.auth import Operator
from app.core.errors import VersionConflict
from app.core.permissions import Role
from app.models.audit_log import AuditLog
from app.services import cluster as cluster_service
from app.services import network as network_service

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


def _create_network(client, cluster, name="net", cidr="10.0.0.0/24", **overrides):
    body = {"cluster": cluster, "name": name, "cidr": cidr}
    body.update(overrides)
    return client.post("/api/v1/networks", json=body)


def _network(client, cluster, name="net", cidr="10.0.0.0/24", **overrides):
    resp = _create_network(client, cluster, name=name, cidr=cidr, **overrides)
    assert resp.status_code == 201, resp.text
    return resp.json()["network"]


def _operator(user) -> Operator:
    return Operator(user_id=user.id, username=user.username, role=Role(user.role))


def _row(session, network_id):
    return session.execute(
        text(
            "SELECT cluster_id, name, name_key, cidr, gateway, status, "
            "auto_allocate, description, metadata, version, deleted_at "
            "FROM networks WHERE id = :id"
        ),
        {"id": uuid.UUID(str(network_id))},
    ).mappings().first()


# --- V28/A1: defaults and response shape -------------------------------------


def test_create_defaults_and_response_shape(role_client_factory, auth_session_factory):
    client, _, _ = role_client_factory("EDITOR")
    c1 = _cluster(client, code="C1")

    created = _network(client, c1["id"], name="MGMT", cidr="10.0.0.5/24")
    assert created["cluster"] == {"id": c1["id"], "code": "C1", "name": "Cluster"}
    assert created["name"] == "MGMT"
    assert created["cidr"] == "10.0.0.0/24"  # host bits normalised
    assert created["gateway"] is None
    assert created["status"] == "ACTIVE"
    assert created["auto_allocate"] is False
    assert created["description"] is None
    assert created["metadata"] == {}
    assert created["version"] == 1
    assert created["deleted_at"] is None
    assert created["created_at"] and created["updated_at"]

    with auth_session_factory() as session:
        row = _row(session, created["id"])
        assert row["name_key"] == "mgmt"
        assert str(row["cidr"]) == "10.0.0.0/24"
        assert row["status"] == "ACTIVE" and row["auto_allocate"] is False
        assert row["metadata"] == {} and row["version"] == 1


# --- A1-A4/V1/V2/V4: name normalisation / uniqueness --------------------------


def test_name_uniqueness_case_insensitive_and_reuse(role_client_factory):
    admin, _, _ = role_client_factory("ADMIN")
    editor, _, _ = role_client_factory("EDITOR")
    c1 = _cluster(admin, code="C1")
    c2 = _cluster(admin, code="C2")

    first = _network(editor, c1["id"], name="MGMT")
    dup = _create_network(editor, c1["id"], name="mgmt")
    assert dup.status_code == 409, dup.text
    body = dup.json()["error"]
    assert body["code"] == "CONFLICT"
    assert body["details"] == {"reason": "unique_conflict", "field": "name"}
    # cross-CLUSTER same name allowed
    _network(editor, c2["id"], name="mgmt")

    # soft delete releases the name; a new object is created
    assert admin.delete(
        f"/api/v1/networks/{first['id']}", params={"version": 1}
    ).status_code == 204
    recreated = _network(editor, c1["id"], name="MGMT")
    assert recreated["id"] != first["id"]


def test_name_trim_boundaries_and_internal_spaces(role_client_factory, auth_session_factory):
    client, _, _ = role_client_factory("EDITOR")
    c1 = _cluster(client, code="C1")

    trimmed = _network(client, c1["id"], name="  MGMT  ")
    assert trimmed["name"] == "MGMT"
    spaced = _network(client, c1["id"], name="MG MT", cidr="10.1.0.0/24")
    assert spaced["name"] == "MG MT"
    double = _network(client, c1["id"], name="MG  MT", cidr="10.2.0.0/24")
    assert double["name"] == "MG  MT"  # internal spaces not collapsed
    _network(client, c1["id"], name="网MG", cidr="10.3.0.0/24")
    _network(client, c1["id"], name="a" * 255, cidr="10.4.0.0/24")

    for bad in ("", "   ", "a" * 256, "e\x01th", "a\u200bb"):
        resp = _create_network(client, c1["id"], name=bad, cidr="10.9.0.0/24")
        assert resp.status_code == 422, (bad, resp.text)
        assert resp.json()["error"]["details"]["fields"][0]["field"] == "name"
    with auth_session_factory() as session:
        assert _row(session, spaced["id"])["name_key"] == "mg mt"


# --- A7/V7: cidr format + normalisation --------------------------------------


def test_cidr_validation_and_normalisation(role_client_factory):
    client, _, _ = role_client_factory("EDITOR")
    c1 = _cluster(client, code="C1")

    host = _network(client, c1["id"], name="host", cidr="192.168.1.130/24")
    assert host["cidr"] == "192.168.1.0/24"

    for bad in ("10.0.0.0/33", "10.0.0.256/24", "not-a-cidr", "::1/128", "10.0.0.1", ""):
        resp = _create_network(client, c1["id"], name=f"b-{bad}", cidr=bad)
        assert resp.status_code == 422, (bad, resp.text)
        assert resp.json()["error"]["details"]["fields"][0]["field"] == "cidr"


# --- A5/A6/V5/V6: cidr overlap ------------------------------------------------


def test_cidr_overlap_and_inactive(role_client_factory):
    client, _, _ = role_client_factory("EDITOR")
    c1 = _cluster(client, code="C1")
    c2 = _cluster(client, code="C2")

    _network(client, c1["id"], name="a", cidr="10.0.0.0/16")
    # overlapping (contained) rejected with conflicts list
    resp = _create_network(client, c1["id"], name="b", cidr="10.0.0.0/24")
    assert resp.status_code == 409, resp.text
    body = resp.json()["error"]
    assert body["details"]["reason"] == "range_overlap"
    assert body["details"]["field"] == "cidr"
    assert [c["object_type"] for c in body["details"]["conflicts"]] == ["network"]
    # identical rejected
    assert _create_network(
        client, c1["id"], name="c", cidr="10.0.0.0/16"
    ).status_code == 409
    # cross-cluster allowed
    _network(client, c2["id"], name="a", cidr="10.0.0.0/16")
    # INACTIVE participates
    _network(client, c1["id"], name="inc", cidr="10.4.0.0/24", status="INACTIVE")
    assert _create_network(
        client, c1["id"], name="inc2", cidr="10.4.0.0/25"
    ).status_code == 409


# --- A8: cluster resolution ---------------------------------------------------


def test_cluster_validation(role_client_factory):
    admin, _, _ = role_client_factory("ADMIN")
    editor, _, _ = role_client_factory("EDITOR")
    c1 = _cluster(admin, code="C1")

    # code accepted and resolved to UUID
    by_code = _network(editor, "c1", name="bycode")
    assert by_code["cluster"]["id"] == c1["id"]

    for bad in (None, "", "does-not-exist", str(uuid.uuid4())):
        resp = _create_network(editor, bad, name="x")
        assert resp.status_code == 422, (bad, resp.text)
        assert resp.json()["error"]["details"]["fields"][0]["field"] == "cluster"

    # soft-deleted cluster rejected
    assert admin.delete(f"/api/v1/clusters/{c1['id']}", params={"version": 1}).status_code == 204
    resp = _create_network(editor, c1["id"], name="y")
    assert resp.status_code == 422
    assert resp.json()["error"]["details"]["fields"][0]["field"] == "cluster"


# --- A10/V10: gateway boundaries ---------------------------------------------


def test_gateway_boundaries(role_client_factory):
    client, _, _ = role_client_factory("EDITOR")
    c1 = _cluster(client, code="C1")

    _network(client, c1["id"], name="gw0", cidr="10.0.0.0/24")
    _network(client, c1["id"], name="gwnull", cidr="10.1.0.0/24", gateway=None)
    _network(client, c1["id"], name="gwok", cidr="10.2.0.0/24", gateway="10.2.0.1")
    _network(client, c1["id"], name="gw31", cidr="10.3.0.0/31", gateway="10.3.0.0")
    _network(client, c1["id"], name="gw31b", cidr="10.4.0.0/31", gateway="10.4.0.1")
    _network(client, c1["id"], name="gw32", cidr="10.5.0.1/32")

    for address in (
        "10.2.0.0",  # network address
        "10.2.0.255",  # broadcast address
        "10.2.1.1",  # outside cidr
        "0.0.0.0",
        "127.0.0.1",
        "169.254.1.1",
        "224.0.0.1",
        "240.0.0.1",
    ):
        resp = _create_network(
            client, c1["id"], name=f"gw-{address}", cidr="10.2.0.0/24", gateway=address
        )
        assert resp.status_code == 422, (address, resp.text)
        assert resp.json()["error"]["details"]["fields"][0]["field"] == "gateway"

    # /32 must have no gateway
    resp = _create_network(
        client, c1["id"], name="x32", cidr="10.6.0.1/32", gateway="10.6.0.1"
    )
    assert resp.status_code == 422
    assert resp.json()["error"]["details"]["fields"][0]["field"] == "gateway"


# --- A12/A13/V12/V13/V24: status / auto_allocate / metadata -------------------


def test_status_auto_allocate_metadata(role_client_factory, auth_session_factory):
    client, _, _ = role_client_factory("EDITOR")
    c1 = _cluster(client, code="C1")

    default = _network(client, c1["id"], name="d")
    assert default["status"] == "ACTIVE" and default["auto_allocate"] is False
    explicit = _network(
        client,
        c1["id"],
        name="e",
        cidr="10.1.0.0/24",
        status="INACTIVE",
        auto_allocate=True,
        metadata={"a": 1},
    )
    assert explicit["status"] == "INACTIVE" and explicit["auto_allocate"] is True
    assert explicit["metadata"] == {"a": 1}

    for bad_status in ("active", "", "NOPE"):
        resp = _create_network(client, c1["id"], name=f"s-{bad_status}", cidr="10.9.0.0/24", status=bad_status)
        assert resp.status_code == 422
    assert _create_network(
        client, c1["id"], name="snull", cidr="10.9.0.0/24", status=None
    ).status_code == 422
    for bad_auto in (None, "yes", 1):
        resp = _create_network(
            client, c1["id"], name=f"a-{bad_auto}", cidr="10.9.0.0/24", auto_allocate=bad_auto
        )
        assert resp.status_code == 422, (bad_auto, resp.text)
    for bad_meta in ([], 1, "x", None):
        resp = _create_network(
            client, c1["id"], name=f"m-{bad_meta}", cidr="10.9.0.0/24", metadata=bad_meta
        )
        assert resp.status_code == 422, (bad_meta, resp.text)


# --- V26: PATCH exclude_unset / immutable ------------------------------------


def test_patch_exclude_unset_and_non_nullable(role_client_factory):
    client, _, _ = role_client_factory("EDITOR")
    c1 = _cluster(client, code="C1")
    created = _network(
        client,
        c1["id"],
        name="p0",
        cidr="10.0.0.0/24",
        gateway="10.0.0.1",
        description="keep",
        metadata={"a": 1},
    )
    updated = client.patch(
        f"/api/v1/networks/{created['id']}",
        json={"version": 1, "status": "INACTIVE"},
    )
    assert updated.status_code == 200, updated.text
    body = updated.json()["network"]
    assert body["status"] == "INACTIVE"
    assert body["name"] == "p0" and body["cidr"] == "10.0.0.0/24"
    assert body["gateway"] == "10.0.0.1" and body["description"] == "keep"
    assert body["metadata"] == {"a": 1} and body["version"] == 2

    cleared = client.patch(
        f"/api/v1/networks/{created['id']}",
        json={"version": 2, "gateway": None, "description": None},
    ).json()["network"]
    assert cleared["gateway"] is None and cleared["description"] is None

    for field in ("name", "cluster", "cidr", "status", "auto_allocate", "metadata"):
        resp = client.patch(
            f"/api/v1/networks/{created['id']}", json={"version": 3, field: None}
        )
        assert resp.status_code == 422, field

    # unknown / read-only fields -> 422
    for payload in (
        {"version": 3, "id": str(uuid.uuid4())},
        {"version": 3, "name_key": "x"},
        {"version": 3, "created_at": "2026-01-01T00:00:00+00:00"},
        {"version": 3, "unknown": 1},
        {},  # missing version
    ):
        assert client.patch(
            f"/api/v1/networks/{created['id']}", json=payload
        ).status_code == 422, payload


def test_patch_cidr_and_gateway_recheck(role_client_factory):
    client, _, _ = role_client_factory("EDITOR")
    c1 = _cluster(client, code="C1")
    a = _network(client, c1["id"], name="a", cidr="10.0.0.0/24", gateway="10.0.0.1")
    _network(client, c1["id"], name="b", cidr="10.1.0.0/24")

    # changing cidr onto an existing one -> range_overlap (clear the now-invalid
    # gateway in the same request so the gateway 422 does not take precedence)
    resp = client.patch(
        f"/api/v1/networks/{a['id']}",
        json={"version": 1, "cidr": "10.1.0.0/24", "gateway": None},
    )
    assert resp.status_code == 409
    assert resp.json()["error"]["details"]["reason"] == "range_overlap"

    # changing cidr invalidates the stored gateway -> 422 gateway
    resp = client.patch(
        f"/api/v1/networks/{a['id']}", json={"version": 1, "cidr": "10.2.0.0/24"}
    )
    assert resp.status_code == 422
    assert resp.json()["error"]["details"]["fields"][0]["field"] == "gateway"

    # changing cidr and clearing the gateway together is accepted
    ok = client.patch(
        f"/api/v1/networks/{a['id']}",
        json={"version": 1, "cidr": "10.2.0.0/24", "gateway": None},
    )
    assert ok.status_code == 200, ok.text
    assert ok.json()["network"]["cidr"] == "10.2.0.0/24"


def test_patch_cluster_rechecks_target(role_client_factory):
    client, _, _ = role_client_factory("EDITOR")
    c1 = _cluster(client, code="C1")
    c2 = _cluster(client, code="C2")
    _network(client, c2["id"], name="taken", cidr="10.0.0.0/24")
    net = _network(client, c1["id"], name="taken", cidr="10.0.0.0/24")

    # same name already exists in the target cluster at the same CIDR
    resp = client.patch(
        f"/api/v1/networks/{net['id']}", json={"version": 1, "cluster": c2["id"]}
    )
    assert resp.status_code == 409
    assert resp.json()["error"]["details"]["reason"] == "unique_conflict"

    # rename + change cidr + change cluster succeeds
    ok = client.patch(
        f"/api/v1/networks/{net['id']}",
        json={
            "version": 1,
            "cluster": c2["id"],
            "name": "moved",
            "cidr": "10.9.0.0/24",
        },
    )
    assert ok.status_code == 200, ok.text
    assert ok.json()["network"]["cluster"]["id"] == c2["id"]


# --- A19/V19: list filters / sorting / pagination ----------------------------


def test_list_filters_sorting_pagination(role_client_factory, auth_session_factory):
    editor, _, _ = role_client_factory("EDITOR")
    admin, _, _ = role_client_factory("ADMIN")
    c1 = _cluster(editor, code="C1")
    c2 = _cluster(editor, code="C2")

    _network(editor, c1["id"], name="Alpha", cidr="10.0.0.0/24", auto_allocate=True)
    _network(editor, c1["id"], name="beta", cidr="10.1.0.0/24", status="INACTIVE")
    _network(editor, c2["id"], name="Gamma", cidr="10.2.0.0/24")

    listed = editor.get("/api/v1/networks").json()
    assert listed["total"] == 3

    assert editor.get("/api/v1/networks", params={"cluster_id": c1["id"]}).json()["total"] == 2
    assert editor.get("/api/v1/networks", params={"status": "INACTIVE"}).json()["items"][0]["name"] == "beta"
    assert editor.get("/api/v1/networks", params={"auto_allocate": "true"}).json()["items"][0]["name"] == "Alpha"
    # q is case-insensitive substring
    assert editor.get("/api/v1/networks", params={"q": "ALPH"}).json()["total"] == 1
    assert editor.get("/api/v1/networks", params={"q": "a"}).json()["total"] == 3
    # whitespace-only q is treated as not provided
    assert editor.get("/api/v1/networks", params={"q": "   "}).json()["total"] == 3

    # invalid query values -> 422
    assert editor.get("/api/v1/networks", params={"cluster_id": "nope"}).status_code == 422
    assert editor.get("/api/v1/networks", params={"status": "NOPE"}).status_code == 422
    assert editor.get("/api/v1/networks", params={"auto_allocate": "maybe"}).status_code == 422
    assert editor.get("/api/v1/networks", params={"deleted": "nope"}).status_code == 422
    assert editor.get("/api/v1/networks", params={"sort": "nope"}).status_code == 422
    assert editor.get("/api/v1/networks", params={"page_size": 101}).status_code == 422

    # sort by name (name_key) ascending
    names = [
        i["name"]
        for i in editor.get(
            "/api/v1/networks", params={"sort": "name", "order": "asc", "page_size": 100}
        ).json()["items"]
    ]
    with auth_session_factory() as session:
        expected = [
            row[0]
            for row in session.execute(
                text(
                    "SELECT name FROM networks WHERE deleted_at IS NULL "
                    "ORDER BY name_key ASC, id ASC"
                )
            ).all()
        ]
    assert names == expected

    page = editor.get(
        "/api/v1/networks", params={"page": 1, "page_size": 2, "sort": "name", "order": "asc"}
    ).json()
    assert page["total"] == 3 and len(page["items"]) == 2

    # deleted include needs VIEW_DELETED
    assert editor.get("/api/v1/networks", params={"deleted": "include"}).status_code == 403
    assert admin.get("/api/v1/networks", params={"deleted": "include"}).status_code == 200


# --- A16/V16: soft delete visibility + restore rechecks ----------------------


def test_soft_delete_visibility_and_restore(role_client_factory):
    admin, _, _ = role_client_factory("ADMIN")
    editor, _, _ = role_client_factory("EDITOR")
    c1 = _cluster(admin, code="C1")
    net = _network(admin, c1["id"], name="net")

    assert admin.delete(
        f"/api/v1/networks/{net['id']}", params={"version": 1}
    ).status_code == 204
    assert editor.get(f"/api/v1/networks/{net['id']}").status_code == 404
    assert editor.get(
        f"/api/v1/networks/{net['id']}", params={"deleted": "true"}
    ).status_code == 403
    detail = admin.get(
        f"/api/v1/networks/{net['id']}", params={"deleted": "true"}
    ).json()["network"]
    assert detail["deleted_at"] is not None

    restored = admin.post(
        f"/api/v1/networks/{net['id']}/restore", params={"version": 2}
    )
    assert restored.status_code == 200, restored.text
    # not_deleted on a live object
    again = admin.post(
        f"/api/v1/networks/{net['id']}/restore", params={"version": 3}
    )
    assert again.status_code == 409
    assert again.json()["error"]["details"]["reason"] == "not_deleted"


def test_restore_rechecks_name_cluster_cidr(role_client_factory):
    admin, _, _ = role_client_factory("ADMIN")
    c1 = _cluster(admin, code="C1")
    c2 = _cluster(admin, code="C2")

    # name reuse takes precedence
    a = _network(admin, c1["id"], name="nm", cidr="10.0.0.0/24")
    assert admin.delete(f"/api/v1/networks/{a['id']}", params={"version": 1}).status_code == 204
    _network(admin, c1["id"], name="nm", cidr="10.0.0.0/24")
    resp = admin.post(f"/api/v1/networks/{a['id']}/restore", params={"version": 2})
    assert resp.status_code == 409
    assert resp.json()["error"]["details"]["reason"] == "unique_conflict"

    # dependency_deleted when the Cluster is soft-deleted
    b = _network(admin, c2["id"], name="dep", cidr="10.1.0.0/24")
    assert admin.delete(f"/api/v1/networks/{b['id']}", params={"version": 1}).status_code == 204
    assert admin.delete(f"/api/v1/clusters/{c2['id']}", params={"version": 1}).status_code == 204
    resp = admin.post(f"/api/v1/networks/{b['id']}/restore", params={"version": 2})
    assert resp.status_code == 409
    assert resp.json()["error"]["details"]["reason"] == "dependency_deleted"
    assert resp.json()["error"]["details"]["conflicts"] == [
        {"object_type": "cluster", "object_id": c2["id"]}
    ]

    # range_overlap when another live Network occupies the CIDR
    assert admin.post(f"/api/v1/clusters/{c2['id']}/restore", params={"version": 2}).status_code == 200
    _network(admin, c2["id"], name="other", cidr="10.1.0.0/24")
    resp = admin.post(f"/api/v1/networks/{b['id']}/restore", params={"version": 2})
    assert resp.status_code == 409
    assert resp.json()["error"]["details"]["reason"] == "range_overlap"


# --- V30: reference checker registry (F008 initial empty set) -----------------


def test_reference_checker_registry_empty(auth_session_factory, make_user):
    user, _ = make_user(role="EDITOR")
    operator = _operator(user)
    with auth_session_factory() as session:
        cluster = cluster_service.create_cluster(session, operator, code="REF", name="ref")
        cluster_id = cluster.id
    with auth_session_factory() as session:
        net = network_service.create_network(
            session, operator, cluster=str(cluster_id), name="refnet", cidr="10.0.0.0/24"
        )
        net_id = net.id
    with auth_session_factory() as session:
        assert cluster_service.check_references(session, "network", net_id) == []
        assert (
            network_service._undeleted_network_child_references(session, net_id) == []
        )


def test_reference_checker_blocks_change_and_delete(
    role_client_factory, monkeypatch
):
    """V9/V15/B22/B24: a registered (non-empty) reference set blocks cidr/
    cluster changes and delete with 409 reference_exists + references[] and
    leaves the row unchanged; dropping the reference releases the block.

    F008 ships the registry with an empty set (F009/F010 append later), so a
    test-side stub is the only way to exercise the documented 409 path end to
    end (TD-1 §4).
    """
    admin, _, _ = role_client_factory("ADMIN")
    c1 = _cluster(admin, code="RC1")
    c2 = _cluster(admin, code="RC2")
    net = _network(
        admin, c1["id"], name="refnet", cidr="10.0.0.0/24", gateway="10.0.0.1"
    )

    def stub(_db, _object_id):
        return [
            {
                "object_type": "ip_pool",
                "object_id": str(uuid.uuid4()),
                "label": "pool-1",
            }
        ]

    monkeypatch.setitem(
        cluster_service._REFERENCE_CHECKERS,
        "network",
        cluster_service._REFERENCE_CHECKERS.get("network", []) + [stub],
    )

    # PATCH cidr (valid, non-overlapping) -> 409 reference_exists + references
    resp = admin.patch(
        f"/api/v1/networks/{net['id']}",
        json={"version": 1, "cidr": "10.5.0.0/24", "gateway": None},
    )
    assert resp.status_code == 409, resp.text
    details = resp.json()["error"]["details"]
    assert details["reason"] == "reference_exists"
    assert details["references"][0]["object_type"] == "ip_pool"
    assert details["references"][0]["label"] == "pool-1"

    # PATCH cluster -> 409 reference_exists
    resp = admin.patch(
        f"/api/v1/networks/{net['id']}", json={"version": 1, "cluster": c2["id"]}
    )
    assert resp.status_code == 409
    assert resp.json()["error"]["details"]["reason"] == "reference_exists"

    # DELETE -> 409; the row stays live and unchanged (no cascade/soft delete)
    resp = admin.delete(f"/api/v1/networks/{net['id']}", params={"version": 1})
    assert resp.status_code == 409
    assert resp.json()["error"]["details"]["reason"] == "reference_exists"
    live = admin.get(f"/api/v1/networks/{net['id']}")
    assert live.status_code == 200
    assert live.json()["network"]["version"] == 1
    assert live.json()["network"]["deleted_at"] is None

    # A non-location change is not blocked by the reference set
    assert admin.patch(
        f"/api/v1/networks/{net['id']}", json={"version": 1, "status": "INACTIVE"}
    ).status_code == 200

    # Removing the reference releases the block
    monkeypatch.undo()
    assert admin.delete(
        f"/api/v1/networks/{net['id']}", params={"version": 2}
    ).status_code == 204


# --- A18/V18: audit four actions + activity + rollback ------------------------


def test_audit_four_actions_and_activity(role_client_factory, auth_session_factory):
    admin, _, _ = role_client_factory("ADMIN")
    viewer, _, _ = role_client_factory("VIEWER")
    c1 = _cluster(admin, code="C1")
    net = _network(admin, c1["id"], name="aud", cidr="10.0.0.0/24", gateway="10.0.0.1")
    assert admin.patch(
        f"/api/v1/networks/{net['id']}", json={"version": 1, "status": "INACTIVE"}
    ).status_code == 200
    assert admin.delete(
        f"/api/v1/networks/{net['id']}", params={"version": 2}
    ).status_code == 204
    assert admin.post(
        f"/api/v1/networks/{net['id']}/restore", params={"version": 3}
    ).status_code == 200

    with auth_session_factory() as session:
        rows = (
            session.execute(
                select(AuditLog)
                .where(AuditLog.object_id == uuid.UUID(net["id"]))
                .order_by(AuditLog.created_at, AuditLog.id)
            )
            .scalars()
            .all()
        )
        # Contract §6.7 orders Activity by created_at then id; do not assume a
        # semantic CREATE<UPDATE<DELETE<RESTORE order when timestamps tie.
        assert {r.action for r in rows} == {"CREATE", "UPDATE", "DELETE", "RESTORE"}
        assert all(r.object_type == "network" for r in rows)
        update = next(r for r in rows if r.action == "UPDATE")
        assert set(update.before_data) == {
            "cluster_id",
            "name",
            "cidr",
            "gateway",
            "status",
            "auto_allocate",
            "description",
            "metadata",
        }
        assert update.before_data["status"] == "ACTIVE"
        assert update.after_data["status"] == "INACTIVE"
        assert next(r for r in rows if r.action == "DELETE").after_data is None
        expected_actions = [r.action for r in rows]

    for client in (viewer, admin):
        activity = client.get(f"/api/v1/networks/{net['id']}/activity")
        assert activity.status_code == 200, activity.text
        assert [i["action"] for i in activity.json()["items"]] == expected_actions


def test_audit_rolls_back_with_the_transaction(auth_session_factory, make_user, monkeypatch):
    user, _ = make_user(role="EDITOR")
    operator = _operator(user)
    with auth_session_factory() as session:
        cluster = cluster_service.create_cluster(session, operator, code="RB", name="rb")
        cluster_id = cluster.id
    with auth_session_factory() as session:
        net = network_service.create_network(
            session, operator, cluster=str(cluster_id), name="rbnet", cidr="10.0.0.0/24"
        )
        net_id = net.id

    original = network_service.audit.record

    def corrupt(*args, **kwargs):
        row = original(*args, **kwargs)
        row.action = "BOGUS"  # violates the audit_logs action CHECK
        return row

    monkeypatch.setattr(network_service.audit, "record", corrupt)
    with auth_session_factory() as session:
        with pytest.raises(Exception):
            network_service.update_network(
                session, operator, net_id, expected_version=1, changes={"status": "INACTIVE"}
            )
        session.rollback()

    with auth_session_factory() as session:
        assert _row(session, net_id)["status"] == "ACTIVE"
        assert (
            session.execute(select(AuditLog).where(AuditLog.action == "BOGUS"))
            .scalars()
            .all()
            == []
        )


# --- A17/V17: permission matrix ----------------------------------------------


def test_permission_matrix(role_client_factory, auth_app):
    admin, _, _ = role_client_factory("ADMIN")
    editor, _, _ = role_client_factory("EDITOR")
    viewer, _, _ = role_client_factory("VIEWER")
    c1 = _cluster(admin, code="C1")
    net = _network(admin, c1["id"], name="perm")

    assert viewer.get(f"/api/v1/networks/{net['id']}").status_code == 200
    assert viewer.get(f"/api/v1/networks/{net['id']}/activity").status_code == 200
    assert viewer.post(
        "/api/v1/networks", json={"cluster": c1["id"], "name": "v", "cidr": "10.9.0.0/24"}
    ).status_code == 403
    assert viewer.patch(
        f"/api/v1/networks/{net['id']}", json={"version": 1, "status": "INACTIVE"}
    ).status_code == 403
    assert viewer.delete(
        f"/api/v1/networks/{net['id']}", params={"version": 1}
    ).status_code == 403

    assert editor.patch(
        f"/api/v1/networks/{net['id']}", json={"version": 1, "status": "INACTIVE"}
    ).status_code == 200
    assert editor.delete(
        f"/api/v1/networks/{net['id']}", params={"version": 2}
    ).status_code == 403
    assert admin.delete(
        f"/api/v1/networks/{net['id']}", params={"version": 2}
    ).status_code == 204
    assert admin.post(
        f"/api/v1/networks/{net['id']}/restore", params={"version": 3}
    ).status_code == 200

    with TestClient(auth_app) as anon:
        assert anon.get("/api/v1/networks").status_code == 401


# --- V25: optimistic lock two sessions ---------------------------------------


def test_optimistic_lock_two_sessions(auth_session_factory, make_user):
    user, _ = make_user(role="EDITOR")
    operator = _operator(user)
    with auth_session_factory() as session:
        cluster = cluster_service.create_cluster(session, operator, code="LK", name="lk")
        cluster_id = cluster.id
    with auth_session_factory() as session:
        net = network_service.create_network(
            session, operator, cluster=str(cluster_id), name="lknet", cidr="10.0.0.0/24"
        )
        net_id = net.id

    first = auth_session_factory()
    second = auth_session_factory()
    try:
        network_service.update_network(
            first, operator, net_id, expected_version=1, changes={"status": "INACTIVE"}
        )
        with pytest.raises(VersionConflict) as exc:
            network_service.update_network(
                second, operator, net_id, expected_version=1, changes={"description": "x"}
            )
        assert exc.value.details == {"current_version": 2}
        second.rollback()
    finally:
        first.close()
        second.close()

    with auth_session_factory() as session:
        row = _row(session, net_id)
        assert row["status"] == "INACTIVE" and row["description"] is None


# --- V27: validation order ----------------------------------------------------


def test_validation_order(role_client_factory):
    editor, _, _ = role_client_factory("EDITOR")
    c1 = _cluster(editor, code="C1")
    _network(editor, c1["id"], name="taken", cidr="10.0.0.0/24")

    # POST: invalid cluster beats invalid cidr
    resp = _create_network(editor, str(uuid.uuid4()), name="x", cidr="not-a-cidr")
    assert resp.status_code == 422
    assert resp.json()["error"]["details"]["fields"][0]["field"] == "cluster"

    # POST: duplicate name beats an invalid cidr
    resp = _create_network(editor, c1["id"], name="taken", cidr="not-a-cidr")
    assert resp.status_code == 409
    assert resp.json()["error"]["details"]["reason"] == "unique_conflict"

    # POST: overlapping cidr is checked after format validation (format wins)
    resp = _create_network(editor, c1["id"], name="new", cidr="not-a-cidr")
    assert resp.status_code == 422

    net = _network(editor, c1["id"], name="order", cidr="10.5.0.0/24")
    _network(editor, c1["id"], name="other", cidr="10.6.0.0/24")

    # PATCH: version beats name uniqueness
    resp = editor.patch(
        f"/api/v1/networks/{net['id']}", json={"version": 99, "name": "other"}
    )
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "VERSION_CONFLICT"