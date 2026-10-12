"""Shared helpers and fixtures for the F015 integration tests.

Not a test module (no ``test_`` prefix): it only defines a role-scoped client
factory and small API helpers reused by ``test_audit_query`` / ``test_deleted`` /
``test_users`` / ``test_f015_constraints``.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


def _login_client(app, make_user, role: str, username: str | None):
    user, password = make_user(role=role, username=username)
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
    """Yield a factory creating logged-in clients per role (cleaned up)."""
    clients: list[TestClient] = []

    def _make(role: str, username: str | None = None):
        client, user, password = _login_client(auth_app, make_user, role, username)
        clients.append(client)
        return client, user, password

    yield _make
    for client in clients:
        client.__exit__(None, None, None)


# --- domain object helpers (real API, ADMIN/EDITOR client) --------------------


def _ok(resp, status):
    assert resp.status_code == status, resp.text
    return resp.json()


def create_cluster(client, code: str, name: str = "Cluster"):
    return _ok(client.post("/api/v1/clusters", json={"code": code, "name": name}), 201)[
        "cluster"
    ]


def create_resource(client, cluster: str, hostname: str):
    return _ok(
        client.post(
            "/api/v1/resources",
            json={
                "cluster": cluster,
                "hostname": hostname,
                "resource_type": "BARE_METAL",
            },
        ),
        201,
    )["resource"]


def create_interface(client, resource_id: str, name: str = "eth0"):
    return _ok(
        client.post("/api/v1/interfaces", json={"resource": resource_id, "name": name}),
        201,
    )["interface"]


def create_network(client, cluster: str, name: str = "net", cidr: str = "10.0.0.0/24"):
    return _ok(
        client.post(
            "/api/v1/networks", json={"cluster": cluster, "name": name, "cidr": cidr}
        ),
        201,
    )["network"]


def create_pool(
    client,
    network_id: str,
    name: str = "pool",
    start: str = "10.0.0.10",
    end: str = "10.0.0.20",
):
    return _ok(
        client.post(
            "/api/v1/ip-pools",
            json={
                "network": network_id,
                "name": name,
                "start_address": start,
                "end_address": end,
            },
        ),
        201,
    )["ip_pool"]


def create_ip(client, network_id: str, address: str):
    return _ok(
        client.post(
            "/api/v1/ip-addresses", json={"network": network_id, "address": address}
        ),
        201,
    )["ip_address"]


def bind(client, ip, interface, version: int = 1):
    return _ok(
        client.patch(
            f"/api/v1/ip-addresses/{ip['id']}",
            json={"version": version, "interface": interface["id"]},
        ),
        200,
    )["ip_address"]


def create_service(client, resource_id: str, name: str = "svc"):
    return _ok(
        client.post("/api/v1/services", json={"resource": resource_id, "name": name}),
        201,
    )["service"]


def create_endpoint(client, service_id: str, ip_id: str, protocol="TCP", port=22):
    return _ok(
        client.post(
            "/api/v1/service-endpoints",
            json={
                "service": service_id,
                "ip_address": ip_id,
                "protocol": protocol,
                "port": port,
            },
        ),
        201,
    )["service_endpoint"]


def soft_delete(client, path: str, version: int):
    resp = client.delete(f"{path}?version={version}")
    assert resp.status_code == 204, resp.text


DELETED_TYPES = (
    "cluster",
    "resource",
    "interface",
    "network",
    "ip_pool",
    "ip_address",
    "service",
    "service_endpoint",
)


def build_deleted_set(client) -> dict[str, dict]:
    """Create and soft-delete exactly one object of each of the eight types.

    Returns ``{object_type: object_payload}``; every object is independent so its
    delete is not blocked by an undeleted reference.
    """
    result: dict[str, dict] = {}

    c = create_cluster(client, "DELC", "Deleted Cluster")
    soft_delete(client, f"/api/v1/clusters/{c['id']}", 1)
    result["cluster"] = c

    create_cluster(client, "KEEPC1")
    r = create_resource(client, "KEEPC1", "del-host1")
    soft_delete(client, f"/api/v1/resources/{r['id']}", 1)
    result["resource"] = r

    create_cluster(client, "KEEPC2")
    ir = create_resource(client, "KEEPC2", "iface-host")
    iface = create_interface(client, ir["id"], name="eth-del")
    soft_delete(client, f"/api/v1/interfaces/{iface['id']}", 1)
    result["interface"] = iface

    create_cluster(client, "KEEPC3")
    net = create_network(client, "KEEPC3", name="net-del")
    soft_delete(client, f"/api/v1/networks/{net['id']}", 1)
    result["network"] = net

    create_cluster(client, "KEEPC4")
    pnet = create_network(client, "KEEPC4", name="pool-net", cidr="10.10.0.0/24")
    pool = create_pool(
        client, pnet["id"], name="pool-del", start="10.10.0.10", end="10.10.0.20"
    )
    soft_delete(client, f"/api/v1/ip-pools/{pool['id']}", 1)
    result["ip_pool"] = pool

    create_cluster(client, "KEEPC5")
    anet = create_network(client, "KEEPC5", name="addr-net", cidr="10.20.0.0/24")
    ip = create_ip(client, anet["id"], "10.20.0.5")
    soft_delete(client, f"/api/v1/ip-addresses/{ip['id']}", 1)
    result["ip_address"] = ip

    create_cluster(client, "KEEPC6")
    sr = create_resource(client, "KEEPC6", "svc-host")
    svc = create_service(client, sr["id"], name="svc-del")
    soft_delete(client, f"/api/v1/services/{svc['id']}", 1)
    result["service"] = svc

    create_cluster(client, "KEEPC7")
    er = create_resource(client, "KEEPC7", "ep-host")
    eiface = create_interface(client, er["id"], name="ep-eth")
    enet = create_network(client, "KEEPC7", name="ep-net", cidr="10.30.0.0/24")
    eip = create_ip(client, enet["id"], "10.30.0.5")
    bind(client, eip, eiface)
    esvc = create_service(client, er["id"], name="ep-svc")
    ep = create_endpoint(client, esvc["id"], eip["id"], protocol="TCP", port=2222)
    soft_delete(client, f"/api/v1/service-endpoints/{ep['id']}", 1)
    result["service_endpoint"] = ep

    return result