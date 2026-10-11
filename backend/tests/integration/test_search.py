"""F013 global search API integration tests (A1-A12, I-11/I-12/I-13).

Requires a real PostgreSQL database via ``TEST_DATABASE_URL`` (DB-D10 guard in
``conftest``). GIN/``EXPLAIN`` evidence lives in ``test_search_constraints.py``.
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


def _service(client, resource, name="ssh", **overrides):
    body = {"resource": resource, "name": name}
    body.update(overrides)
    resp = client.post("/api/v1/services", json=body)
    assert resp.status_code == 201, resp.text
    return resp.json()["service"]


def _network(client, cluster, name="net", cidr="10.0.0.0/24", **overrides):
    body = {"cluster": cluster, "name": name, "cidr": cidr}
    body.update(overrides)
    resp = client.post("/api/v1/networks", json=body)
    assert resp.status_code == 201, resp.text
    return resp.json()["network"]


def _interface(client, resource, name="eth0"):
    resp = client.post(
        "/api/v1/interfaces", json={"resource": resource, "name": name}
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["interface"]


def _ip(client, network, address, **overrides):
    body = {"network": network, "address": address}
    body.update(overrides)
    resp = client.post("/api/v1/ip-addresses", json=body)
    assert resp.status_code == 201, resp.text
    return resp.json()["ip_address"]


def _bind(client, ip, interface, version=1):
    resp = client.patch(
        f"/api/v1/ip-addresses/{ip['id']}",
        json={"version": version, "interface": interface["id"]},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["ip_address"]


def _search(client, q, **params):
    return client.get("/api/v1/search", params={"q": q, **params})


def _types(body):
    return [item["object_type"] for item in body["items"]]


# --- A1/A2/A3/A10: hostname search, normalisation, stable id ------------------


def test_hostname_substring_and_normalisation(role_client_factory):
    editor, _, _ = role_client_factory("EDITOR")
    c1 = _cluster(editor, code="C1")
    r1 = _resource(editor, c1["code"], hostname="gpu0701")

    body = _search(editor, "gpu07").json()
    assert body["total"] == 1
    item = body["items"][0]
    assert item["object_type"] == "resource"
    assert item["matched_field"] == "hostname"
    assert item["matched_value"] == "gpu0701"
    assert item["id"] == r1["id"]
    assert item["resource"]["hostname"] == "gpu0701"
    assert item["resource"]["cluster"] == {
        "id": c1["id"],
        "code": "C1",
        "name": "Cluster",
    }
    assert item["cluster"] is None
    assert item["ip_address"] is None
    assert item["service"] is None

    # A3: ASCII case-insensitive and surrounding whitespace trimmed.
    assert _search(editor, "GPU0701").json()["total"] == 1
    assert _search(editor, "  gpu0701  ").json()["total"] == 1


def test_similarity_exact_match_ranks_first(role_client_factory):
    editor, _, _ = role_client_factory("EDITOR")
    c1 = _cluster(editor, code="C1")
    _resource(editor, c1["code"], hostname="srv-alpha")
    _resource(editor, c1["code"], hostname="srv-alpha-2")

    body = _search(editor, "srv-alpha").json()
    assert body["total"] == 2
    assert body["items"][0]["matched_value"] == "srv-alpha"


# --- A4/A5: IP exact match, interface -> resource, unbound --------------------


def test_ip_exact_match_binds_resource(role_client_factory):
    editor, _, _ = role_client_factory("EDITOR")
    c1 = _cluster(editor, code="C1")
    res = _resource(editor, c1["code"], hostname="host-ip")
    net = _network(editor, c1["code"], name="mgmt")
    iface = _interface(editor, res["id"])
    ip = _ip(editor, net["id"], "10.0.0.5")
    _bind(editor, ip, iface)

    body = _search(editor, "10.0.0.5").json()
    assert body["total"] == 1
    item = body["items"][0]
    assert item["object_type"] == "ip_address"
    assert item["matched_field"] == "address"
    assert item["ip_address"]["address"] == "10.0.0.5"
    assert item["ip_address"]["network"] == {"id": net["id"], "name": "mgmt"}
    assert item["ip_address"]["interface"] == {"id": iface["id"], "name": "eth0"}
    assert item["resource"]["id"] == res["id"]
    assert item["resource"]["hostname"] == "host-ip"

    # Non-integer / partial IP forms do not produce ip_address rows (A5, §2.4).
    assert _search(editor, "10.0.0").json()["total"] == 0
    assert _search(editor, "10.0.0.5/24").json()["total"] == 0


def test_ip_unbound_has_null_resource(role_client_factory):
    editor, _, _ = role_client_factory("EDITOR")
    c1 = _cluster(editor, code="C1")
    net = _network(editor, c1["code"])
    _ip(editor, net["id"], "10.0.0.9")

    item = _search(editor, "10.0.0.9").json()["items"][0]
    assert item["object_type"] == "ip_address"
    assert item["ip_address"]["interface"] is None
    assert item["resource"] is None


# --- A6: Cluster code/name ----------------------------------------------------


def test_cluster_code_and_name_matching(role_client_factory):
    editor, _, _ = role_client_factory("EDITOR")
    c1 = _cluster(editor, code="CN001", name="Cluster North")
    _resource(editor, c1["code"], hostname="inside-host")

    by_code = _search(editor, "cn001").json()
    assert by_code["total"] == 1
    item = by_code["items"][0]
    assert item["object_type"] == "cluster"
    assert item["matched_field"] == "code"
    assert item["matched_value"] == "CN001"
    assert item["cluster"]["status"] == "ACTIVE"
    # I-12: a Cluster hit does not expand its Resources.
    assert "resource" not in _types(by_code)

    by_name = _search(editor, "north").json()["items"][0]
    assert by_name["object_type"] == "cluster"
    assert by_name["matched_field"] == "name"
    assert by_name["matched_value"] == "Cluster North"


# --- A7: Service -> embedding resource ---------------------------------------


def test_service_match_embeds_resource(role_client_factory):
    editor, _, _ = role_client_factory("EDITOR")
    c1 = _cluster(editor, code="C1")
    res = _resource(editor, c1["code"], hostname="svc-host")
    svc = _service(editor, res["id"], name="SSH Daemon")

    body = _search(editor, "ssh").json()
    assert body["total"] == 1
    item = body["items"][0]
    assert item["object_type"] == "service"
    assert item["matched_field"] == "name"
    assert item["matched_value"] == "SSH Daemon"
    assert item["service"] == {"id": svc["id"], "name": "SSH Daemon", "status": "UNKNOWN"}
    assert item["resource"]["id"] == res["id"]


# --- A8/A23: soft delete visibility -----------------------------------------


def test_soft_delete_exclude_include_only(role_client_factory):
    admin, _, _ = role_client_factory("ADMIN")
    viewer, _, _ = role_client_factory("VIEWER")
    c1 = _cluster(admin, code="C1")
    res = _resource(admin, c1["code"], hostname="to-delete")

    resp = admin.delete(
        f"/api/v1/resources/{res['id']}", params={"version": 1}
    )
    assert resp.status_code == 204, resp.text

    # default excludes
    assert _search(admin, "to-delete").json()["total"] == 0
    # viewer may not include deleted -> 403
    forbidden = _search(viewer, "to-delete", deleted="include")
    assert forbidden.status_code == 403
    assert forbidden.json()["error"]["details"] == {"reason": "permission"}
    # ADMIN include / only
    included = _search(admin, "to-delete", deleted="include").json()
    assert included["total"] == 1
    only = _search(admin, "to-delete", deleted="only").json()
    assert only["total"] == 1
    assert only["items"][0]["resource"]["hostname"] == "to-delete"


# --- A9/I-13: empty and over-long q ------------------------------------------


@pytest.mark.parametrize("q", ["", "   "])
def test_empty_query_is_422(role_client_factory, q):
    editor, _, _ = role_client_factory("EDITOR")
    resp = _search(editor, q)
    assert resp.status_code == 422, resp.text
    fields = resp.json()["error"]["details"]["fields"]
    assert fields[0]["field"] == "q"


def test_missing_query_is_422(role_client_factory):
    editor, _, _ = role_client_factory("EDITOR")
    resp = editor.get("/api/v1/search")
    assert resp.status_code == 422
    assert resp.json()["error"]["details"]["fields"][0]["field"] == "q"


def test_overlong_query_is_422(role_client_factory):
    editor, _, _ = role_client_factory("EDITOR")
    resp = _search(editor, "a" * 256)
    assert resp.status_code == 422
    assert resp.json()["error"]["details"]["fields"][0]["field"] == "q"


# --- parameter validation ----------------------------------------------------


def test_invalid_parameters_are_422(role_client_factory):
    editor, _, _ = role_client_factory("EDITOR")
    assert _search(editor, "x", type="bogus").status_code == 422
    assert _search(editor, "x", deleted="bogus").status_code == 422
    assert _search(editor, "x", page=0).status_code == 422
    assert _search(editor, "x", page_size=101).status_code == 422
    assert _search(editor, "x", page="abc").status_code == 422


def test_type_filter_narrows_results(role_client_factory):
    editor, _, _ = role_client_factory("EDITOR")
    c1 = _cluster(editor, code="C1")
    res = _resource(editor, c1["code"], hostname="match-host")
    _service(editor, res["id"], name="match-service")

    body = _search(editor, "match").json()
    assert set(_types(body)) == {"resource", "service"}
    only_service = _search(editor, "match", type="service").json()
    assert _types(only_service) == ["service"]


# --- I-11: pagination / full ordering ---------------------------------------


def test_pagination_is_stable_and_total_is_exact(role_client_factory):
    editor, _, _ = role_client_factory("EDITOR")
    c1 = _cluster(editor, code="C1")
    for index in range(5):
        _resource(editor, c1["code"], hostname=f"page-host-{index}")

    first = _search(editor, "page-host", page=1, page_size=2).json()
    second = _search(editor, "page-host", page=2, page_size=2).json()
    third = _search(editor, "page-host", page=3, page_size=2).json()
    assert first["total"] == second["total"] == third["total"] == 5
    assert len(first["items"]) == len(second["items"]) == 2
    assert len(third["items"]) == 1
    ids = [i["id"] for i in first["items"] + second["items"] + third["items"]]
    assert len(set(ids)) == 5


def test_empty_result_is_200(role_client_factory):
    editor, _, _ = role_client_factory("EDITOR")
    resp = _search(editor, "does-not-exist-xyz")
    assert resp.status_code == 200
    assert resp.json() == {"items": [], "page": 1, "page_size": 20, "total": 0}


# --- A21/A22: read-only / unauthenticated -----------------------------------


def test_unauthenticated_is_401(auth_app):
    with TestClient(auth_app) as client:
        resp = client.get("/api/v1/search", params={"q": "anything"})
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "AUTH_REQUIRED"


def test_search_writes_no_audit(role_client_factory, auth_session_factory):
    editor, _, _ = role_client_factory("EDITOR")
    c1 = _cluster(editor, code="C1")
    _resource(editor, c1["code"], hostname="audit-host")

    with auth_session_factory() as session:
        before = session.execute(
            text("SELECT count(*) FROM audit_logs")
        ).scalar_one()
    assert _search(editor, "audit-host").status_code == 200
    with auth_session_factory() as session:
        after = session.execute(text("SELECT count(*) FROM audit_logs")).scalar_one()
    assert after == before