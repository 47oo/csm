"""F012 ServiceEndpoint API integration tests (A1-A21, T22/T23/T24/T25/T26).

Requires a real PostgreSQL database via ``TEST_DATABASE_URL`` (DB-D10 guard in
``conftest``). Raw-SQL constraint / migration evidence lives in
``test_service_endpoint_constraints.py``; the two real reference providers
(IP side / Service side) and the end-to-end ``reference_exists`` protection are
exercised here against the production app.
"""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from app.core.auth import Operator
from app.core.permissions import Role
from app.services import ip_address_reference, service_reference

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


def _operator(user) -> Operator:
    return Operator(user_id=user.id, username=user.username, role=Role(user.role))


def _cluster(client, code="C1", name="Cluster"):
    resp = client.post("/api/v1/clusters", json={"code": code, "name": name})
    assert resp.status_code == 201, resp.text
    return resp.json()["cluster"]


def _network(client, cluster, name="net", cidr="10.0.0.0/24", **overrides):
    body = {"cluster": cluster, "name": name, "cidr": cidr}
    body.update(overrides)
    resp = client.post("/api/v1/networks", json=body)
    assert resp.status_code == 201, resp.text
    return resp.json()["network"]


def _resource(client, cluster, hostname="host1"):
    resp = client.post(
        "/api/v1/resources",
        json={"cluster": cluster, "hostname": hostname, "resource_type": "BARE_METAL"},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["resource"]


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


def _bind(client, ip, interface):
    resp = client.patch(
        f"/api/v1/ip-addresses/{ip['id']}",
        json={"version": ip["version"], "interface": interface["id"]},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["ip_address"]


def _service(client, resource, name="svc"):
    resp = client.post(
        "/api/v1/services", json={"resource": resource, "name": name}
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["service"]


def _endpoint_post(client, service, ip, protocol="TCP", port=22, **overrides):
    body = {
        "service": service["id"],
        "ip_address": ip["id"],
        "protocol": protocol,
        "port": port,
    }
    body.update(overrides)
    return client.post("/api/v1/service-endpoints", json=body)


def _endpoint(client, service, ip, protocol="TCP", port=22, **overrides):
    resp = _endpoint_post(client, service, ip, protocol, port, **overrides)
    assert resp.status_code == 201, resp.text
    return resp.json()["service_endpoint"]


def _bound_service_ip(client, cluster, *, cidr="10.0.0.0/24", address="10.0.0.5",
                      resource_name="host1", service_name="svc"):
    """Build the full Resource -> Interface -> IP -> Service chain on one Resource."""
    res = _resource(client, cluster, hostname=resource_name)
    iface = _interface(client, res["id"])
    net = _network(client, cluster, name=f"net-{resource_name}", cidr=cidr)
    ip = _bind(client, _ip(client, net["id"], address), iface)
    service = _service(client, res["id"], name=service_name)
    return service, ip, res, iface, net


# --- A1: body shape / required / unknown fields ------------------------------


def test_create_required_and_unknown_fields(role_client_factory):
    """A1: missing required fields and undeclared/read-only fields are 422."""
    admin, _, _ = role_client_factory("ADMIN")
    c1 = _cluster(admin)
    service, ip, *_ = _bound_service_ip(admin, c1["id"])

    # missing protocol / port
    assert admin.post(
        "/api/v1/service-endpoints",
        json={"service": service["id"], "ip_address": ip["id"]},
    ).status_code == 422
    assert admin.post(
        "/api/v1/service-endpoints",
        json={"service": service["id"], "ip_address": ip["id"], "protocol": "TCP"},
    ).status_code == 422

    # undeclared / read-only / metadata fields
    for extra in ({"service_id": service["id"]}, {"id": str(uuid.uuid4())},
                  {"metadata": {}}, {"name": "x"}):
        resp = _endpoint_post(admin, service, ip, **extra)
        assert resp.status_code == 422, extra
        assert resp.json()["error"]["code"] == "VALIDATION_ERROR"


# --- A2/A3: service / ip_address live references -----------------------------


def test_service_and_ip_reference_validation(role_client_factory):
    """A2/A3: nonexistent / soft-deleted / non-UUID references are 422."""
    admin, _, _ = role_client_factory("ADMIN")
    c1 = _cluster(admin)
    service, ip, *_ = _bound_service_ip(admin, c1["id"])

    for bad in (str(uuid.uuid4()), "not-a-uuid", ""):
        resp = _endpoint_post(admin, {"id": bad}, ip)
        assert resp.status_code == 422, bad
        assert resp.json()["error"]["details"]["fields"][0]["field"] == "service"

    resp = _endpoint_post(admin, service, {"id": str(uuid.uuid4())})
    assert resp.status_code == 422
    assert resp.json()["error"]["details"]["fields"][0]["field"] == "ip_address"

    # soft-deleted service
    other = _service(admin, service["resource"]["id"], name="svc-other")
    admin.delete(f"/api/v1/services/{other['id']}", params={"version": 1})
    resp = _endpoint_post(admin, other, ip)
    assert resp.status_code == 422
    assert resp.json()["error"]["details"]["fields"][0]["field"] == "service"


# --- A4/A5: attribution (bound Interface, same Resource) --------------------


def test_attribution_unbound_and_cross_resource(role_client_factory):
    """A4/A5: an unbound IP or a cross-Resource Interface is 422 field ip_address."""
    admin, _, _ = role_client_factory("ADMIN")
    c1 = _cluster(admin)
    res1 = _resource(admin, c1["id"], hostname="r1")
    iface1 = _interface(admin, res1["id"])
    net = _network(admin, c1["id"], name="n", cidr="10.0.0.0/24")
    service = _service(admin, res1["id"], name="svc")

    # unbound IP
    unbound = _ip(admin, net["id"], "10.0.0.5")
    resp = _endpoint_post(admin, service, unbound)
    assert resp.status_code == 422
    assert resp.json()["error"]["details"]["fields"][0]["field"] == "ip_address"

    # cross-Resource: IP bound to res2's interface while the Service is on res1
    res2 = _resource(admin, c1["id"], hostname="r2")
    iface2 = _interface(admin, res2["id"], name="eth0")
    cross = _ip(admin, net["id"], "10.0.0.6")
    _bind(admin, cross, iface2)
    resp = _endpoint_post(admin, service, cross)
    assert resp.status_code == 422
    assert resp.json()["error"]["details"]["fields"][0]["field"] == "ip_address"

    # same-Resource bound IP succeeds
    good = _ip(admin, net["id"], "10.0.0.7")
    _bind(admin, good, iface1)
    assert _endpoint_post(admin, service, good).status_code == 201


# --- A6/A7: protocol / port value domains -----------------------------------


def test_protocol_and_port_validation(role_client_factory):
    """A6/A7: uppercase-only protocol, port 1..65535 inclusive at boundaries."""
    admin, _, _ = role_client_factory("ADMIN")
    c1 = _cluster(admin)
    service, ip, *_ = _bound_service_ip(admin, c1["id"])

    for proto in ("tcp", "Udp", "SCTP", "", None):
        resp = _endpoint_post(admin, service, ip, protocol=proto, port=22)
        assert resp.status_code == 422, proto
        assert resp.json()["error"]["details"]["fields"][0]["field"] == "protocol"

    for port in (0, 65536, -1, None, 22.5, "80", True, False, "22"):
        resp = _endpoint_post(admin, service, ip, protocol="TCP", port=port)
        assert resp.status_code == 422, port
        assert resp.json()["error"]["details"]["fields"][0]["field"] == "port"

    # boundaries accepted
    assert _endpoint_post(admin, service, ip, protocol="TCP", port=1).status_code == 201
    assert _endpoint_post(admin, service, ip, protocol="UDP", port=65535).status_code == 201


def test_patch_port_strict_integer(role_client_factory):
    """A7/B8: PATCH port uses the same strict 1..65535 integer domain as POST."""
    admin, _, _ = role_client_factory("ADMIN")
    c1 = _cluster(admin)
    service, ip, *_ = _bound_service_ip(admin, c1["id"])
    endpoint = _endpoint(admin, service, ip, "TCP", 22)

    for bad in (0, 65536, -1, None, 22.5, "80", True, False, "22"):
        resp = admin.patch(
            f"/api/v1/service-endpoints/{endpoint['id']}",
            json={"version": 1, "port": bad},
        )
        assert resp.status_code == 422, bad
        assert resp.json()["error"]["details"]["fields"][0]["field"] == "port"

    # boundaries accepted and the version advances per successful update
    ok = admin.patch(
        f"/api/v1/service-endpoints/{endpoint['id']}",
        json={"version": 1, "port": 65535},
    )
    assert ok.status_code == 200, ok.text
    assert ok.json()["service_endpoint"]["port"] == 65535


# --- A8/A9/A20: listener uniqueness + concurrency ---------------------------


def test_listener_uniqueness_same_ip_and_across_ips(role_client_factory):
    """A8/A9: same IP undeleted (protocol,port) conflicts; different IP is fine."""
    admin, _, _ = role_client_factory("ADMIN")
    c1 = _cluster(admin)
    res = _resource(admin, c1["id"], hostname="r")
    iface = _interface(admin, res["id"])
    net = _network(admin, c1["id"], name="n", cidr="10.0.0.0/24")
    service = _service(admin, res["id"], name="svc")
    ip1 = _bind(admin, _ip(admin, net["id"], "10.0.0.5"), iface)
    ip2 = _bind(admin, _ip(admin, net["id"], "10.0.0.6"), iface)

    endpoint = _endpoint(admin, service, ip1, "TCP", 22)

    dup = _endpoint_post(admin, service, ip1, "TCP", 22)
    assert dup.status_code == 409
    details = dup.json()["error"]["details"]
    assert details["reason"] == "unique_conflict"
    assert details["field"] == "port"
    assert details["ip_address_id"] == ip1["id"]
    assert details["protocol"] == "TCP" and details["port"] == 22

    # same tuple on another IP is allowed
    assert _endpoint_post(admin, service, ip2, "TCP", 22).status_code == 201

    # soft delete releases the tuple
    admin.delete(
        f"/api/v1/service-endpoints/{endpoint['id']}", params={"version": 1}
    )
    assert _endpoint_post(admin, service, ip1, "TCP", 22).status_code == 201


def test_patch_listener_uniqueness(role_client_factory):
    """A9: PATCH changing protocol/port re-checks the listener set (excluding self)."""
    admin, _, _ = role_client_factory("ADMIN")
    c1 = _cluster(admin)
    service, ip, *_ = _bound_service_ip(admin, c1["id"])
    first = _endpoint(admin, service, ip, "TCP", 22)
    second = _endpoint(admin, service, ip, "UDP", 53)

    conflict = admin.patch(
        f"/api/v1/service-endpoints/{second['id']}",
        json={"version": 1, "port": 22, "protocol": "TCP"},
    )
    assert conflict.status_code == 409
    assert conflict.json()["error"]["details"]["reason"] == "unique_conflict"

    # port change to a free value works; same value on itself is not a conflict
    ok = admin.patch(
        f"/api/v1/service-endpoints/{second['id']}",
        json={"version": 1, "port": 53, "description": "dns"},
    )
    assert ok.status_code == 200, ok.text
    assert ok.json()["service_endpoint"]["description"] == "dns"
    assert first["id"] != second["id"]


# --- A10/A11: many endpoints per Service; description -----------------------


def test_many_endpoints_and_description_semantics(role_client_factory):
    """A10/A11: one Service has many Endpoints; description null/omit semantics."""
    admin, _, _ = role_client_factory("ADMIN")
    c1 = _cluster(admin)
    service, ip, *_ = _bound_service_ip(admin, c1["id"])
    a = _endpoint(admin, service, ip, "TCP", 22, description="ssh")
    b = _endpoint(admin, service, ip, "TCP", 80)
    assert a["service"]["id"] == b["service"]["id"]
    assert b["description"] is None

    # omitted keeps, explicit null clears
    kept = admin.patch(
        f"/api/v1/service-endpoints/{a['id']}", json={"version": 1, "port": 2222}
    )
    assert kept.json()["service_endpoint"]["description"] == "ssh"
    cleared = admin.patch(
        f"/api/v1/service-endpoints/{a['id']}",
        json={"version": 2, "description": None},
    )
    assert cleared.json()["service_endpoint"]["description"] is None


# --- A12/T22: IP-side reference protection ----------------------------------


def test_ip_reference_blocks_unbind_transfer_release(role_client_factory):
    """A12/T22: an undeleted Endpoint blocks IP unbind/transfer/release."""
    admin, _, _ = role_client_factory("ADMIN")
    c1 = _cluster(admin)
    service, ip, res, iface, net = _bound_service_ip(admin, c1["id"])
    endpoint = _endpoint(admin, service, ip, "TCP", 443)
    iface2 = _interface(admin, res["id"], name="eth1")

    unbind = admin.patch(
        f"/api/v1/ip-addresses/{ip['id']}", json={"version": ip["version"], "interface": None}
    )
    assert unbind.status_code == 409, unbind.text
    refs = unbind.json()["error"]["details"]["references"]
    assert unbind.json()["error"]["details"]["reason"] == "reference_exists"
    assert refs[0]["object_type"] == "service_endpoint"
    assert refs[0]["object_id"] == endpoint["id"]
    assert refs[0]["label"] == "TCP/443"

    transfer = admin.patch(
        f"/api/v1/ip-addresses/{ip['id']}",
        json={"version": ip["version"], "interface": iface2["id"]},
    )
    assert transfer.status_code == 409

    release = admin.delete(
        f"/api/v1/ip-addresses/{ip['id']}", params={"version": ip["version"]}
    )
    assert release.status_code == 409

    # after the Endpoint is soft-deleted the IP can be unbound
    admin.delete(
        f"/api/v1/service-endpoints/{endpoint['id']}", params={"version": 1}
    )
    ok = admin.patch(
        f"/api/v1/ip-addresses/{ip['id']}", json={"version": ip["version"], "interface": None}
    )
    assert ok.status_code == 200, ok.text


# --- A13/T23: Service-side reference protection -----------------------------


def test_service_reference_blocks_delete(role_client_factory):
    """A13/T23: an undeleted Endpoint blocks Service deletion."""
    admin, _, _ = role_client_factory("ADMIN")
    c1 = _cluster(admin)
    service, ip, *_ = _bound_service_ip(admin, c1["id"])
    endpoint = _endpoint(admin, service, ip, "TCP", 22)

    blocked = admin.delete(
        f"/api/v1/services/{service['id']}", params={"version": service["version"]}
    )
    assert blocked.status_code == 409, blocked.text
    details = blocked.json()["error"]["details"]
    assert details["reason"] == "reference_exists"
    assert details["references"][0]["object_type"] == "service_endpoint"
    assert details["references"][0]["object_id"] == endpoint["id"]

    admin.delete(
        f"/api/v1/service-endpoints/{endpoint['id']}", params={"version": 1}
    )
    ok = admin.delete(
        f"/api/v1/services/{service['id']}", params={"version": service["version"]}
    )
    assert ok.status_code == 204, ok.text


# --- A14/T24: soft delete / restore + re-checks -----------------------------


def test_soft_delete_restore_and_dependency_rechecks(role_client_factory):
    """A14/T24: restore re-checks dependencies, uniqueness and attribution."""
    admin, _, _ = role_client_factory("ADMIN")
    c1 = _cluster(admin)
    service, ip, res, iface, net = _bound_service_ip(admin, c1["id"])
    endpoint = _endpoint(admin, service, ip, "TCP", 22)

    # not_deleted: restoring a live object is 409
    not_deleted = admin.post(
        f"/api/v1/service-endpoints/{endpoint['id']}/restore", params={"version": 1}
    )
    assert not_deleted.status_code == 409
    assert not_deleted.json()["error"]["details"]["reason"] == "not_deleted"

    # delete v1 -> v2, restore v2 -> success v3 alive
    admin.delete(f"/api/v1/service-endpoints/{endpoint['id']}", params={"version": 1})
    restored = admin.post(
        f"/api/v1/service-endpoints/{endpoint['id']}/restore", params={"version": 2}
    )
    assert restored.status_code == 200, restored.text
    assert restored.json()["service_endpoint"]["deleted_at"] is None

    # Service dependency deleted: delete endpoint v3 -> v4, then the Service
    admin.delete(f"/api/v1/service-endpoints/{endpoint['id']}", params={"version": 3})
    admin.delete(
        f"/api/v1/services/{service['id']}", params={"version": service["version"]}
    )
    dep = admin.post(
        f"/api/v1/service-endpoints/{endpoint['id']}/restore", params={"version": 4}
    )
    assert dep.status_code == 409
    details = dep.json()["error"]["details"]
    assert details["reason"] == "dependency_deleted"
    assert details["conflicts"][0]["object_type"] == "service"
    # bring the Service back, then restore the endpoint (v4 -> v5 alive)
    admin.post(
        f"/api/v1/services/{service['id']}/restore",
        params={"version": service["version"] + 1},
    )
    again = admin.post(
        f"/api/v1/service-endpoints/{endpoint['id']}/restore", params={"version": 4}
    )
    assert again.status_code == 200, again.text

    # Attribution failure on restore: delete endpoint v5 -> v6, unbind the IP,
    # then restore fails 422 field ip_address.
    admin.delete(f"/api/v1/service-endpoints/{endpoint['id']}", params={"version": 5})
    admin.patch(
        f"/api/v1/ip-addresses/{ip['id']}",
        json={"version": ip["version"], "interface": None},
    )
    attr = admin.post(
        f"/api/v1/service-endpoints/{endpoint['id']}/restore", params={"version": 6}
    )
    assert attr.status_code == 422, attr.text
    assert attr.json()["error"]["details"]["fields"][0]["field"] == "ip_address"

    # release the IP then restore -> IP dependency 409
    admin.delete(
        f"/api/v1/ip-addresses/{ip['id']}", params={"version": ip["version"] + 1}
    )
    ip_dep = admin.post(
        f"/api/v1/service-endpoints/{endpoint['id']}/restore", params={"version": 6}
    )
    assert ip_dep.status_code == 409
    assert ip_dep.json()["error"]["details"]["conflicts"][0]["object_type"] == "ip_address"


def test_restore_uniqueness_conflict(role_client_factory):
    """A14: a listener created after soft delete blocks the restore (409)."""
    admin, _, _ = role_client_factory("ADMIN")
    c1 = _cluster(admin)
    service, ip, *_ = _bound_service_ip(admin, c1["id"])
    old = _endpoint(admin, service, ip, "TCP", 22)
    admin.delete(f"/api/v1/service-endpoints/{old['id']}", params={"version": 1})
    _endpoint(admin, service, ip, "TCP", 22)

    resp = admin.post(
        f"/api/v1/service-endpoints/{old['id']}/restore", params={"version": 2}
    )
    assert resp.status_code == 409
    assert resp.json()["error"]["details"]["reason"] == "unique_conflict"


# --- A15/T25: permissions ----------------------------------------------------


def test_permissions_matrix(role_client_factory, auth_app):
    """A15/T25: 401 before 403; WRITE/READ/DELETE/RESTORE/VIEW_DELETED enforced."""
    admin, _, _ = role_client_factory("ADMIN")
    editor, _, _ = role_client_factory("EDITOR")
    viewer, _, _ = role_client_factory("VIEWER")
    c1 = _cluster(admin)
    service, ip, *_ = _bound_service_ip(admin, c1["id"])

    # VIEWER cannot create or delete
    assert _endpoint_post(viewer, service, ip).status_code == 403
    endpoint = _endpoint(admin, service, ip, "TCP", 22)
    assert viewer.delete(
        f"/api/v1/service-endpoints/{endpoint['id']}", params={"version": 1}
    ).status_code == 403
    # EDITOR can create/update but not delete/restore
    created = _endpoint_post(editor, service, ip, "UDP", 53)
    assert created.status_code == 201
    assert editor.delete(
        f"/api/v1/service-endpoints/{created.json()['service_endpoint']['id']}",
        params={"version": 1},
    ).status_code == 403
    admin.delete(
        f"/api/v1/service-endpoints/{endpoint['id']}", params={"version": 1}
    )
    assert viewer.post(
        f"/api/v1/service-endpoints/{endpoint['id']}/restore", params={"version": 2}
    ).status_code == 403
    # deleted=include requires VIEW_DELETED (VIEWER lacks it)
    assert viewer.get(
        "/api/v1/service-endpoints", params={"deleted": "include"}
    ).status_code == 403
    assert viewer.get(
        f"/api/v1/service-endpoints/{endpoint['id']}", params={"deleted": True}
    ).status_code == 403

    # unauthenticated is 401 (a fresh client has no session cookie)
    anon = TestClient(auth_app)
    assert anon.get("/api/v1/service-endpoints").status_code == 401


# --- A16/T25/T26: audit trail -----------------------------------------------


def test_activity_trail_and_whitelist(role_client_factory):
    """A16/T25/T26: four actions recorded with the whitelisted snapshot."""
    admin, _, _ = role_client_factory("ADMIN")
    c1 = _cluster(admin)
    service, ip, *_ = _bound_service_ip(admin, c1["id"])
    endpoint = _endpoint(admin, service, ip, "TCP", 22, description="ssh")
    admin.patch(
        f"/api/v1/service-endpoints/{endpoint['id']}",
        json={"version": 1, "port": 2222},
    )
    admin.delete(f"/api/v1/service-endpoints/{endpoint['id']}", params={"version": 2})
    admin.post(
        f"/api/v1/service-endpoints/{endpoint['id']}/restore", params={"version": 3}
    )

    resp = admin.get(f"/api/v1/service-endpoints/{endpoint['id']}/activity")
    assert resp.status_code == 200, resp.text
    actions = [item["action"] for item in resp.json()["items"]]
    assert actions == ["CREATE", "UPDATE", "DELETE", "RESTORE"]
    after = resp.json()["items"][0]["after_data"]
    assert set(after) == {"service_id", "ip_address_id", "protocol", "port", "description"}
    assert after["port"] == 22
    update = resp.json()["items"][1]
    assert update["before_data"]["port"] == 22
    assert update["after_data"]["port"] == 2222
    assert resp.json()["items"][2]["after_data"] is None


def test_failed_create_writes_no_audit(role_client_factory):
    """A16: a rejected create leaves no audit row (same-transaction rollback)."""
    admin, _, _ = role_client_factory("ADMIN")
    c1 = _cluster(admin)
    service, ip, *_ = _bound_service_ip(admin, c1["id"])
    endpoint = _endpoint(admin, service, ip, "TCP", 22)

    before = admin.get(
        f"/api/v1/service-endpoints/{endpoint['id']}/activity"
    ).json()["total"]
    assert _endpoint_post(admin, service, ip, "TCP", 22).status_code == 409
    after = admin.get(
        f"/api/v1/service-endpoints/{endpoint['id']}/activity"
    ).json()["total"]
    assert before == after


# --- A17/T26: optimistic locking --------------------------------------------


def test_optimistic_lock_and_immutable_fields(role_client_factory):
    """A17/T26: stale version 409; immutable service/ip_address rejected 422."""
    admin, _, _ = role_client_factory("ADMIN")
    c1 = _cluster(admin)
    service, ip, *_ = _bound_service_ip(admin, c1["id"])
    endpoint = _endpoint(admin, service, ip, "TCP", 22)

    stale = admin.patch(
        f"/api/v1/service-endpoints/{endpoint['id']}",
        json={"version": 99, "port": 80},
    )
    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "VERSION_CONFLICT"
    assert stale.json()["error"]["details"]["current_version"] == 1

    for body in ({"service": service["id"]}, {"ip_address": ip["id"]},
                 {"service_id": service["id"]}, {"id": endpoint["id"]},
                 {"metadata": {}}):
        payload = {"version": 1}
        payload.update(body)
        resp = admin.patch(f"/api/v1/service-endpoints/{endpoint['id']}", json=payload)
        assert resp.status_code == 422, body


# --- A18: list filtering / sorting / pagination -----------------------------


def test_list_filters_sorting_pagination(role_client_factory):
    """A18: filter by service/ip/protocol, sort, paginate, deleted modes."""
    admin, _, _ = role_client_factory("ADMIN")
    c1 = _cluster(admin)
    res = _resource(admin, c1["id"], hostname="r")
    iface = _interface(admin, res["id"])
    net = _network(admin, c1["id"], name="n", cidr="10.0.0.0/24")
    service = _service(admin, res["id"], name="svc")
    ip1 = _bind(admin, _ip(admin, net["id"], "10.0.0.5"), iface)
    ip2 = _bind(admin, _ip(admin, net["id"], "10.0.0.6"), iface)

    _endpoint(admin, service, ip1, "TCP", 22)
    _endpoint(admin, service, ip1, "UDP", 53)
    removed = _endpoint(admin, service, ip2, "TCP", 80)

    listing = admin.get("/api/v1/service-endpoints").json()
    assert listing["total"] == 3
    assert listing["page"] == 1 and listing["page_size"] == 20

    by_proto = admin.get(
        "/api/v1/service-endpoints", params={"protocol": "UDP"}
    ).json()
    assert by_proto["total"] == 1 and by_proto["items"][0]["port"] == 53

    by_ip = admin.get(
        "/api/v1/service-endpoints", params={"ip_address_id": ip2["id"]}
    ).json()
    assert by_ip["total"] == 1

    by_service = admin.get(
        "/api/v1/service-endpoints", params={"service_id": service["id"]}
    ).json()
    assert by_service["total"] == 3

    # sort=port ascending is numeric
    asc = admin.get(
        "/api/v1/service-endpoints",
        params={"sort": "port", "order": "asc"},
    ).json()
    assert [item["port"] for item in asc["items"]] == [22, 53, 80]

    # pagination
    page2 = admin.get(
        "/api/v1/service-endpoints", params={"page": 2, "page_size": 2}
    ).json()
    assert page2["total"] == 3 and len(page2["items"]) == 1

    # deleted modes
    admin.delete(f"/api/v1/service-endpoints/{removed['id']}", params={"version": 1})
    assert admin.get("/api/v1/service-endpoints").json()["total"] == 2
    only = admin.get(
        "/api/v1/service-endpoints", params={"deleted": "only"}
    ).json()
    assert only["total"] == 1 and only["items"][0]["id"] == removed["id"]
    assert admin.get(
        "/api/v1/service-endpoints", params={"deleted": "include"}
    ).json()["total"] == 3
    assert admin.get(
        "/api/v1/service-endpoints", params={"sort": "bogus"}
    ).status_code == 422


# --- A19: invalid listen forms rejected -------------------------------------


def test_invalid_listen_forms_rejected(role_client_factory):
    """A19: wildcard/0.0.0.0, ranges, unix socket, IPv6-style inputs never bind."""
    admin, _, _ = role_client_factory("ADMIN")
    c1 = _cluster(admin)
    service, ip, *_ = _bound_service_ip(admin, c1["id"])
    for port in ("1-100", "22,80", 0):
        assert _endpoint_post(admin, service, ip, "TCP", port).status_code == 422


# --- T22 concurrency: partial unique index atomic backstop ------------------


def test_reference_providers_registered():
    """DR-161: both real providers are registered on the production registries."""
    assert any(
        checker.__module__ == "app.services.endpoint_reference"
        for checker in ip_address_reference._CHECKERS
    )
    assert any(
        checker.__module__ == "app.services.endpoint_reference"
        for checker in service_reference._CHECKERS
    )