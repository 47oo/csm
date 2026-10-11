"""F013 Tester independent acceptance coverage (TE-1).

Complements the developer suites (``test_search.py``/``test_dashboard.py``)
with the acceptance gaps identified in TD-1: full ordering (id-ASC tie-break)
and stable paging (V28/B9), typed-row de-duplication (V27/B8), A16
gateway-in-RESERVED de-dup, A17 soft-deleted IP occupancy, 401-before-422
validation order (V26/B13), parameter bounds (B3/B6), response shape (V25/V31)
and non-integer / IPv6 IP input (B12).
"""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient


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
    clients = []

    def _make(role: str):
        client, user, password = _login_client(auth_app, make_user, role)
        clients.append(client)
        return client, user, password

    yield _make
    for client in clients:
        client.__exit__(None, None, None)


def _cluster(client, code="C1", name="Cluster", **ov):
    body = {"code": code, "name": name}
    body.update(ov)
    r = client.post("/api/v1/clusters", json=body)
    assert r.status_code == 201, r.text
    return r.json()["cluster"]


def _resource(client, cluster, hostname="h", resource_type="BARE_METAL", **ex):
    body = {"cluster": cluster, "hostname": hostname, "resource_type": resource_type}
    body.update(ex)
    r = client.post("/api/v1/resources", json=body)
    assert r.status_code == 201, r.text
    return r.json()["resource"]


def _network(client, cluster, name="net", cidr="10.0.0.0/24", **ov):
    body = {"cluster": cluster, "name": name, "cidr": cidr}
    body.update(ov)
    r = client.post("/api/v1/networks", json=body)
    assert r.status_code == 201, r.text
    return r.json()["network"]


def _pool(client, network, name="p", start="10.0.0.1", end="10.0.0.9", **ov):
    body = {"network": network, "name": name, "start_address": start, "end_address": end}
    body.update(ov)
    r = client.post("/api/v1/ip-pools", json=body)
    assert r.status_code == 201, r.text
    return r.json()["ip_pool"]


def _ip(client, network, address, **ov):
    body = {"network": network, "address": address}
    body.update(ov)
    r = client.post("/api/v1/ip-addresses", json=body)
    assert r.status_code == 201, r.text
    return r.json()["ip_address"]


def _service(client, resource, name="s", **ov):
    body = {"resource": resource, "name": name}
    body.update(ov)
    r = client.post("/api/v1/services", json=body)
    assert r.status_code == 201, r.text
    return r.json()["service"]


# 1) id-ASC tie-break for equal similarity across clusters + stable page_size=1
def test_probe_equal_similarity_id_asc_stable_paging(role_client_factory):
    editor, _, _ = role_client_factory("EDITOR")
    c1 = _cluster(editor, code="A1")
    c2 = _cluster(editor, code="A2")
    r1 = _resource(editor, c1["code"], hostname="dupx")
    r2 = _resource(editor, c2["code"], hostname="dupx")
    got = []
    for page in (1, 2):
        body = editor.get(
            "/api/v1/search", params={"q": "dupx", "page": page, "page_size": 1}
        ).json()
        assert body["total"] == 2
        got.append(body["items"][0]["id"])
    assert got == sorted([r1["id"], r2["id"]]), got
    assert len(set(got)) == 2


# 2) typed-row dedup: hostname + service hit one resource -> resource row + service row
def test_probe_typed_rows_no_synthesised_resource(role_client_factory):
    editor, _, _ = role_client_factory("EDITOR")
    c1 = _cluster(editor, code="C1")
    res = _resource(editor, c1["code"], hostname="node-alpha")
    _service(editor, res["id"], name="node-service")
    body = editor.get("/api/v1/search", params={"q": "node"}).json()
    types = sorted(i["object_type"] for i in body["items"])
    assert types == ["resource", "service"], types
    # exactly one resource row (from hostname), service embeds the same resource
    resource_rows = [i for i in body["items"] if i["object_type"] == "resource"]
    service_rows = [i for i in body["items"] if i["object_type"] == "service"]
    assert len(resource_rows) == 1 and len(service_rows) == 1
    assert service_rows[0]["resource"]["id"] == res["id"]


# 3) A16: gateway inside RESERVED pool counted only once
def test_probe_gateway_inside_reserved_dedup(role_client_factory):
    editor, _, _ = role_client_factory("EDITOR")
    c1 = _cluster(editor, code="C1")
    net = _network(editor, c1["code"], cidr="10.0.0.0/24", gateway="10.0.0.5")
    # RESERVED covers .1-.10, which contains gateway .5
    _pool(editor, net["id"], name="res", start="10.0.0.1", end="10.0.0.10",
          allocation_mode="RESERVED")
    row = editor.get("/api/v1/dashboard").json()["networks"]["items"][0]
    # base usable /24 = 254; exclusions union {.1-.10} = 10 -> 244 (not 243)
    assert row["capacity"]["allocatable_total"] == 244
    assert row["capacity"]["occupied"] == 0
    assert row["capacity"]["remaining"] == 244


# 4) soft-deleted IP not counted in occupied
def test_probe_soft_deleted_ip_not_occupied(role_client_factory):
    admin, _, _ = role_client_factory("ADMIN")
    c1 = _cluster(admin, code="C1")
    net = _network(admin, c1["code"], cidr="10.0.0.0/24")
    ip = _ip(admin, net["id"], "10.0.0.9")
    before = admin.get("/api/v1/dashboard").json()["networks"]["items"][0]
    assert before["capacity"]["occupied"] == 1
    assert admin.delete(f"/api/v1/ip-addresses/{ip['id']}", params={"version": 1}).status_code == 204
    after = admin.get("/api/v1/dashboard").json()["networks"]["items"][0]
    assert after["capacity"]["occupied"] == 0
    assert after["capacity"]["remaining"] == before["capacity"]["remaining"] + 1


# 5) 401 must precede parameter 422
def test_probe_unauthenticated_precedes_validation(auth_app):
    with TestClient(auth_app) as client:
        r = client.get("/api/v1/search", params={"q": ""})
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "AUTH_REQUIRED"


# 6) page_size bounds accepted / rejected; q length 255 accepted
def test_probe_parameter_bounds(role_client_factory):
    editor, _, _ = role_client_factory("EDITOR")
    c1 = _cluster(editor, code="C1")
    _resource(editor, c1["code"], hostname="bounded")
    assert editor.get("/api/v1/search", params={"q": "b", "page_size": 1}).status_code == 200
    assert editor.get("/api/v1/search", params={"q": "b", "page_size": 100}).status_code == 200
    assert editor.get("/api/v1/search", params={"q": "b", "page_size": 0}).status_code == 422
    assert editor.get("/api/v1/search", params={"q": "b", "page_size": 1.5}).status_code == 422
    assert editor.get("/api/v1/search", params={"q": "a" * 255}).status_code == 200
    assert editor.get("/api/v1/search", params={"q": "a" * 256}).status_code == 422
    # type case-sensitivity
    assert editor.get("/api/v1/search", params={"q": "b", "type": "RESOURCE"}).status_code == 422


# 7) response shape: no global total; dashboard ignores cluster_id/deleted
def test_probe_response_shape_and_ignored_params(role_client_factory):
    editor, _, _ = role_client_factory("EDITOR")
    body = editor.get("/api/v1/dashboard").json()
    assert set(body) == {"counts", "networks"}
    assert set(body["networks"]) == {"items", "page", "page_size", "total"}
    assert set(body["counts"]) == {"clusters", "resources", "bare_metal", "virtual_machines", "networks"}
    # unknown query params are ignored (no cluster_id/deleted contract) -> 200
    assert editor.get("/api/v1/dashboard", params={"cluster_id": str(uuid.uuid4())}).status_code == 200
    assert editor.get("/api/v1/dashboard", params={"deleted": "include"}).status_code == 200
    # search matched_field limited to the contract enum
    c1 = _cluster(editor, code="C1")
    _resource(editor, c1["code"], hostname="enumme")
    items = editor.get("/api/v1/search", params={"q": "enumme"}).json()["items"]
    assert all(i["matched_field"] in {"hostname", "address", "code", "name"} for i in items)


# 8) non-address / prefix / IPv6 input yields no ip_address rows (no 500)
def test_probe_ip_non_integer_forms(role_client_factory):
    editor, _, _ = role_client_factory("EDITOR")
    c1 = _cluster(editor, code="C1")
    net = _network(editor, c1["code"], cidr="10.0.0.0/24")
    _ip(editor, net["id"], "10.0.0.5")
    for q in ("10.0.0", "10.0.0.5/24", "999.1.1.1", "::1", "not-an-ip"):
        resp = editor.get("/api/v1/search", params={"q": q})
        assert resp.status_code == 200, q
        assert all(i["object_type"] != "ip_address" for i in resp.json()["items"]), q


# 9) cluster matched_field: code wins when both code and name hit
def test_probe_cluster_code_wins(role_client_factory):
    editor, _, _ = role_client_factory("EDITOR")
    c1 = _cluster(editor, code="BOTHXY", name="Bothxy Cluster")
    body = editor.get("/api/v1/search", params={"q": "bothxy"}).json()
    assert body["total"] == 1
    assert body["items"][0]["object_type"] == "cluster"
    assert body["items"][0]["matched_field"] == "code"
    assert body["items"][0]["matched_value"] == "BOTHXY"


# 10) B17: soft-deleted AUTO pool excluded; soft-deleted RESERVED no longer excluded
def test_probe_soft_deleted_pools(role_client_factory):
    admin, _, _ = role_client_factory("ADMIN")
    c1 = _cluster(admin, code="C1")
    net = _network(admin, c1["code"], cidr="10.0.0.0/24")
    auto = _pool(
        admin, net["id"], name="auto", start="10.0.0.100", end="10.0.0.110",
        allocation_mode="AUTO",
    )
    res = _pool(
        admin, net["id"], name="res", start="10.0.0.1", end="10.0.0.10",
        allocation_mode="RESERVED",
    )
    before = admin.get("/api/v1/dashboard").json()["networks"]["items"][0]
    assert len(before["auto_pools"]) == 1
    # /24 base usable 254 - RESERVED 10 = 244
    assert before["capacity"]["allocatable_total"] == 244

    assert admin.delete(
        f"/api/v1/ip-pools/{auto['id']}", params={"version": 1}
    ).status_code == 204
    assert admin.delete(
        f"/api/v1/ip-pools/{res['id']}", params={"version": 1}
    ).status_code == 204
    after = admin.get("/api/v1/dashboard").json()["networks"]["items"][0]
    # deleted AUTO pool disappears; deleted RESERVED no longer excluded -> 254
    assert after["auto_pools"] == []
    assert after["capacity"]["allocatable_total"] == 254