"""F013 Dashboard API integration tests (A13-A23, I-14/I-16).

Requires a real PostgreSQL database via ``TEST_DATABASE_URL`` (DB-D10 guard in
``conftest``). Capacity is cross-checked item-by-item against F010
``GET /api/v1/networks/{id}/capacity``.
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


def _cluster(client, code="C1", name="Cluster", **overrides):
    body = {"code": code, "name": name}
    body.update(overrides)
    resp = client.post("/api/v1/clusters", json=body)
    assert resp.status_code == 201, resp.text
    return resp.json()["cluster"]


def _resource(client, cluster, hostname="host1", resource_type="BARE_METAL", **extra):
    body = {
        "cluster": cluster,
        "hostname": hostname,
        "resource_type": resource_type,
    }
    body.update(extra)
    resp = client.post("/api/v1/resources", json=body)
    assert resp.status_code == 201, resp.text
    return resp.json()["resource"]


def _network(client, cluster, name="net", cidr="10.0.0.0/24", **overrides):
    body = {"cluster": cluster, "name": name, "cidr": cidr}
    body.update(overrides)
    resp = client.post("/api/v1/networks", json=body)
    assert resp.status_code == 201, resp.text
    return resp.json()["network"]


def _pool(client, network, name="pool", start="10.0.0.1", end="10.0.0.9", **overrides):
    body = {
        "network": network,
        "name": name,
        "start_address": start,
        "end_address": end,
    }
    body.update(overrides)
    resp = client.post("/api/v1/ip-pools", json=body)
    assert resp.status_code == 201, resp.text
    return resp.json()["ip_pool"]


def _ip(client, network, address, **overrides):
    body = {"network": network, "address": address}
    body.update(overrides)
    resp = client.post("/api/v1/ip-addresses", json=body)
    assert resp.status_code == 201, resp.text
    return resp.json()["ip_address"]


# --- A13: counts -------------------------------------------------------------


def test_counts_scope_and_inactive(role_client_factory):
    editor, _, _ = role_client_factory("EDITOR")
    c1 = _cluster(editor, code="C1")
    c2 = _cluster(editor, code="C2", name="Inactive", status="INACTIVE")
    host = _resource(editor, c1["code"], hostname="bm1", resource_type="BARE_METAL")
    _resource(
        editor,
        c1["code"],
        hostname="vm1",
        resource_type="VIRTUAL_MACHINE",
        virtual_machine={"host_resource_id": host["id"]},
    )
    _network(editor, c1["code"], name="n1")
    _network(editor, c2["code"], name="n2", status="INACTIVE")

    body = editor.get("/api/v1/dashboard").json()
    assert body["counts"] == {
        "clusters": 2,
        "resources": 2,
        "bare_metal": 1,
        "virtual_machines": 1,
        "networks": 2,
    }
    # Inactive Network still listed and capacity not zeroed (A19).
    statuses = {row["network"]["status"] for row in body["networks"]["items"]}
    assert statuses == {"ACTIVE", "INACTIVE"}
    inactive = next(
        row for row in body["networks"]["items"] if row["network"]["status"] == "INACTIVE"
    )
    assert inactive["capacity"]["allocatable_total"] > 0


def test_counts_match_domain_list_totals(role_client_factory):
    editor, _, _ = role_client_factory("EDITOR")
    c1 = _cluster(editor, code="C1")
    _resource(editor, c1["code"], hostname="a")
    host = _resource(editor, c1["code"], hostname="host-a")
    _resource(
        editor,
        c1["code"],
        hostname="b",
        resource_type="VIRTUAL_MACHINE",
        virtual_machine={"host_resource_id": host["id"]},
    )
    _network(editor, c1["code"], name="n1")

    counts = editor.get("/api/v1/dashboard").json()["counts"]
    assert counts["clusters"] == editor.get(
        "/api/v1/clusters", params={"deleted": "exclude"}
    ).json()["total"]
    assert counts["resources"] == editor.get(
        "/api/v1/resources", params={"deleted": "exclude"}
    ).json()["total"]
    assert counts["networks"] == editor.get(
        "/api/v1/networks", params={"deleted": "exclude"}
    ).json()["total"]
    assert counts["bare_metal"] == editor.get(
        "/api/v1/resources",
        params={"deleted": "exclude", "type": "BARE_METAL"},
    ).json()["total"]
    assert counts["virtual_machines"] == editor.get(
        "/api/v1/resources",
        params={"deleted": "exclude", "type": "VIRTUAL_MACHINE"},
    ).json()["total"]


# --- A14-A20: capacity item-by-item agreement with F010 ----------------------


def test_network_capacity_matches_f010_capacity_endpoint(role_client_factory):
    editor, _, _ = role_client_factory("EDITOR")
    c1 = _cluster(editor, code="C1")
    net = _network(
        editor, c1["code"], name="n1", cidr="10.10.0.0/24", gateway="10.10.0.1"
    )
    _pool(
        editor,
        net["id"],
        name="res",
        start="10.10.0.2",
        end="10.10.0.10",
        allocation_mode="RESERVED",
    )
    auto = _pool(
        editor,
        net["id"],
        name="auto",
        start="10.10.0.100",
        end="10.10.0.110",
        allocation_mode="AUTO",
    )
    _ip(editor, net["id"], "10.10.0.100")
    _ip(editor, net["id"], "10.10.0.200")

    row = editor.get("/api/v1/dashboard").json()["networks"]["items"][0]
    capacity = editor.get(f"/api/v1/networks/{net['id']}/capacity").json()

    assert row["network"]["id"] == net["id"]
    assert row["network"]["cidr"] == "10.10.0.0/24"
    assert row["network"]["auto_allocate"] is False
    assert row["network"]["cluster"] == {
        "id": c1["id"],
        "code": "C1",
        "name": "Cluster",
    }
    assert row["capacity"] == {
        "allocatable_total": capacity["network_capacity"]["allocatable_total"],
        "occupied": capacity["network_capacity"]["occupied"],
        "remaining": capacity["network_capacity"]["remaining"],
    }
    assert row["capacity"]["allocatable_total"] == 244
    assert row["capacity"]["occupied"] == 2
    assert row["capacity"]["remaining"] == 242

    assert len(row["auto_pools"]) == len(capacity["auto_pools"]) == 1
    block = row["auto_pools"][0]
    f010 = capacity["auto_pools"][0]
    assert block["ip_pool"]["id"] == auto["id"]
    assert block["allocatable_total"] == f010["allocatable_total"] == 11
    assert block["occupied"] == f010["occupied"] == 1
    assert block["remaining"] == f010["remaining"] == 10


def test_negative_remaining_not_clamped(role_client_factory, auth_session_factory):
    editor, _, _ = role_client_factory("EDITOR")
    c1 = _cluster(editor, code="C1")
    net = _network(editor, c1["code"], name="n1", cidr="10.0.0.0/30")
    with auth_session_factory() as session:
        session.execute(
            text(
                "INSERT INTO ip_addresses (network_id, cluster_id, address) "
                "VALUES (:n, :c, '10.0.0.1'), (:n, :c, '10.0.0.2')"
            ),
            {"n": uuid.UUID(net["id"]), "c": uuid.UUID(c1["id"])},
        )
        session.execute(
            text("UPDATE networks SET gateway = '10.0.0.1' WHERE id = :id"),
            {"id": uuid.UUID(net["id"])},
        )
        session.commit()

    row = editor.get("/api/v1/dashboard").json()["networks"]["items"][0]
    assert row["capacity"]["allocatable_total"] == 1
    assert row["capacity"]["occupied"] == 2
    assert row["capacity"]["remaining"] == -1


# --- soft delete / pagination ------------------------------------------------


def test_soft_deleted_excluded_from_counts_and_networks(role_client_factory):
    admin, _, _ = role_client_factory("ADMIN")
    c1 = _cluster(admin, code="C1")
    res = _resource(admin, c1["code"], hostname="gone")
    net = _network(admin, c1["code"], name="gone-net")
    assert admin.delete(
        f"/api/v1/resources/{res['id']}", params={"version": 1}
    ).status_code == 204
    assert admin.delete(
        f"/api/v1/networks/{net['id']}", params={"version": 1}
    ).status_code == 204

    body = admin.get("/api/v1/dashboard").json()
    assert body["counts"]["resources"] == 0
    assert body["counts"]["networks"] == 0
    assert body["networks"]["total"] == 0


def test_networks_pagination_does_not_affect_counts(role_client_factory):
    editor, _, _ = role_client_factory("EDITOR")
    c1 = _cluster(editor, code="C1")
    for index in range(3):
        _network(editor, c1["code"], name=f"net-{index}", cidr=f"10.0.{index}.0/24")

    first = editor.get(
        "/api/v1/dashboard", params={"page": 1, "page_size": 2}
    ).json()
    second = editor.get(
        "/api/v1/dashboard", params={"page": 2, "page_size": 2}
    ).json()
    assert first["counts"] == second["counts"]
    assert first["counts"]["networks"] == 3
    assert first["networks"]["total"] == second["networks"]["total"] == 3
    assert len(first["networks"]["items"]) == 2
    assert len(second["networks"]["items"]) == 1
    ids = [
        row["network"]["id"]
        for row in first["networks"]["items"] + second["networks"]["items"]
    ]
    assert len(set(ids)) == 3


# --- A21/A22: read-only / permissions ---------------------------------------


@pytest.mark.parametrize("role", ["VIEWER", "EDITOR", "ADMIN"])
def test_all_roles_can_read_dashboard(role_client_factory, role):
    client, _, _ = role_client_factory(role)
    resp = client.get("/api/v1/dashboard")
    assert resp.status_code == 200
    assert resp.json()["counts"]["clusters"] == 0


def test_unauthenticated_dashboard_is_401(auth_app):
    with TestClient(auth_app) as client:
        resp = client.get("/api/v1/dashboard")
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "AUTH_REQUIRED"


def test_dashboard_writes_no_audit(role_client_factory, auth_session_factory):
    editor, _, _ = role_client_factory("EDITOR")
    c1 = _cluster(editor, code="C1")
    _network(editor, c1["code"], name="n1")
    with auth_session_factory() as session:
        before = session.execute(text("SELECT count(*) FROM audit_logs")).scalar_one()
    assert editor.get("/api/v1/dashboard").status_code == 200
    with auth_session_factory() as session:
        after = session.execute(text("SELECT count(*) FROM audit_logs")).scalar_one()
    assert after == before


def test_invalid_pagination_is_422(role_client_factory):
    editor, _, _ = role_client_factory("EDITOR")
    assert editor.get("/api/v1/dashboard", params={"page": 0}).status_code == 422
    assert editor.get("/api/v1/dashboard", params={"page_size": 101}).status_code == 422
    assert (
        editor.get(
            "/api/v1/dashboard", params={"deleted": "include"}
        ).status_code
        == 200
    )