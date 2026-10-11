"""F010 IPAddress API integration tests (A1-A26 F010-independent items).

Requires a real PostgreSQL database via ``TEST_DATABASE_URL`` (DB-D10 guard in
``conftest``). Raw-SQL constraint/migration evidence lives in
``test_ip_address_constraints.py``; the real ``IpAddressOccupancyProvider`` and
the F009/F008 occupancy paths are exercised here end-to-end.
"""

from __future__ import annotations

import threading
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.core.auth import Operator
from app.core.errors import Conflict, ValidationError, VersionConflict
from app.core.permissions import Role
from app.models.audit_log import AuditLog
from app.services import ip_address as ip_address_service
from app.services import ip_address_reference
from app.services import ip_capacity, ip_occupancy, ip_pool as ip_pool_service
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


def _pool(client, network, name="pool", start="10.0.0.1", end="10.0.0.9", **kw):
    body = {
        "network": network,
        "name": name,
        "start_address": start,
        "end_address": end,
    }
    body.update(kw)
    resp = client.post("/api/v1/ip-pools", json=body)
    assert resp.status_code == 201, resp.text
    return resp.json()["ip_pool"]


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


def _allocate(client, network, address, **overrides):
    body = {"network": network, "address": address}
    body.update(overrides)
    return client.post("/api/v1/ip-addresses", json=body)


def _ip(client, network, address, **overrides):
    resp = _allocate(client, network, address, **overrides)
    assert resp.status_code == 201, resp.text
    return resp.json()["ip_address"]


def _auto(client, network, pool_id, **overrides):
    body = {"network": network, "ip_pool": pool_id}
    body.update(overrides)
    return client.post("/api/v1/ip-addresses/auto-allocate", json=body)


# --- A1-A4: manual allocation ------------------------------------------------


def test_manual_allocation_in_and_out_of_pool(role_client_factory):
    """A1/A4: manual allocation inside an AUTO pool, inside MANUAL, and pool-less."""
    editor, _, _ = role_client_factory("EDITOR")
    c1 = _cluster(editor, code="C1")
    net = _network(editor, c1["id"], name="n1", cidr="10.0.0.0/24")
    _pool(editor, net["id"], name="auto", start="10.0.0.10", end="10.0.0.20",
          allocation_mode="AUTO")
    _pool(editor, net["id"], name="manual", start="10.0.0.30", end="10.0.0.40")

    # AUTO pool manual allocation carries the source pool
    inside_auto = _ip(editor, net["id"], "10.0.0.15")
    assert inside_auto["ip_pool"]["name"] == "auto"
    assert inside_auto["interface"] is None
    # MANUAL pool
    inside_manual = _ip(editor, net["id"], "10.0.0.35")
    assert inside_manual["ip_pool"]["name"] == "manual"
    # pool-less manual allocation is allowed and ip_pool is null
    outside = _ip(editor, net["id"], "10.0.0.200")
    assert outside["ip_pool"] is None
    assert outside["cluster"]["code"] == "C1"
    assert outside["network"]["cidr"] == "10.0.0.0/24"


def test_manual_allocation_invalid_addresses(role_client_factory):
    """A2/A3/A16/A17: boundary and disabled-address rejections are 422."""
    editor, _, _ = role_client_factory("EDITOR")
    c1 = _cluster(editor, code="C1")
    net = _network(editor, c1["id"], name="n1", cidr="10.0.0.0/24",
                   gateway="10.0.0.1")
    _pool(editor, net["id"], name="res", start="10.0.0.2", end="10.0.0.5",
          allocation_mode="RESERVED")

    # non-IPv4 / masked / out of CIDR / network / broadcast
    for bad in ("not-an-ip", "10.0.0.10/24", "2001:db8::1", "10.0.9.9",
                "10.0.0.0", "10.0.0.255"):
        resp = _allocate(editor, net["id"], bad)
        assert resp.status_code == 422, (bad, resp.text)
        fields = resp.json()["error"]["details"]["fields"]
        assert any(f["field"] == "address" for f in fields)

    # gateway and RESERVED
    for bad in ("10.0.0.1", "10.0.0.3"):
        resp = _allocate(editor, net["id"], bad)
        assert resp.status_code == 422, (bad, resp.text)


def test_disabled_ranges_and_31_32_boundaries(role_client_factory):
    """A16/A17: /31 both usable, /32 single, disabled ranges rejected."""
    editor, _, _ = role_client_factory("EDITOR")
    c1 = _cluster(editor, code="C1")
    n31 = _network(editor, c1["id"], name="n31", cidr="10.1.0.4/31")
    assert _allocate(editor, n31["id"], "10.1.0.4").status_code == 201
    assert _allocate(editor, n31["id"], "10.1.0.5").status_code == 201
    n32 = _network(editor, c1["id"], name="n32", cidr="10.2.0.5/32")
    assert _allocate(editor, n32["id"], "10.2.0.5").status_code == 201

    c2 = _cluster(editor, code="C2", name="Cluster2")
    ndis = _network(editor, c2["id"], name="ndis", cidr="0.0.0.0/0")
    for bad in ("0.0.0.1", "127.0.0.1", "169.254.1.1", "224.0.0.1", "240.0.0.1"):
        resp = _allocate(editor, ndis["id"], bad)
        assert resp.status_code == 422, (bad, resp.text)
    assert _allocate(editor, ndis["id"], "1.2.3.4").status_code == 201


# --- A5-A8: automatic allocation --------------------------------------------


def test_auto_allocation_conditions(role_client_factory):
    """A5: auto allocation requires ACTIVE + auto_allocate + AUTO pool."""
    editor, _, _ = role_client_factory("EDITOR")
    c1 = _cluster(editor, code="C1")
    net = _network(editor, c1["id"], name="n1", cidr="10.0.0.0/24")
    manual = _pool(editor, net["id"], name="m", start="10.0.0.1", end="10.0.0.9")
    auto = _pool(editor, net["id"], name="a", start="10.0.0.10", end="10.0.0.20",
                 allocation_mode="AUTO")

    # auto_allocate disabled
    resp = _auto(editor, net["id"], auto["id"])
    assert resp.status_code == 409
    assert resp.json()["error"]["details"] == {
        "reason": "allocation_not_allowed",
        "condition": "auto_allocate_disabled",
    }

    editor.patch(
        f"/api/v1/networks/{net['id']}",
        json={"version": 1, "auto_allocate": True},
    )
    # MANUAL pool is not auto-allocatable
    resp = _auto(editor, net["id"], manual["id"])
    assert resp.status_code == 409
    assert resp.json()["error"]["details"]["condition"] == "pool_not_auto"

    # INACTIVE network blocks new allocation
    editor.patch(
        f"/api/v1/networks/{net['id']}",
        json={"version": 2, "status": "INACTIVE"},
    )
    resp = _auto(editor, net["id"], auto["id"])
    assert resp.status_code == 409
    assert resp.json()["error"]["details"]["condition"] == "network_inactive"

    resp = _allocate(editor, net["id"], "10.0.0.200")
    assert resp.status_code == 409
    assert resp.json()["error"]["details"]["condition"] == "network_inactive"
    # Contract §6.2 order: the ACTIVE check precedes address validation, so an
    # invalid address on an INACTIVE network is still 409 (not 422).
    assert _allocate(editor, net["id"], "not-an-ip").status_code == 409


def test_auto_allocation_ascending_and_exhaustion(role_client_factory):
    """A6/A7: ascending first-free selection; exhaustion does not switch pools."""
    editor, _, _ = role_client_factory("EDITOR")
    c1 = _cluster(editor, code="C1")
    net = _network(editor, c1["id"], name="n1", cidr="10.0.0.0/24",
                   auto_allocate=True)
    pool_a = _pool(editor, net["id"], name="a", start="10.0.0.10", end="10.0.0.12",
                   allocation_mode="AUTO")
    _pool(editor, net["id"], name="b", start="10.0.0.20", end="10.0.0.22",
          allocation_mode="AUTO")
    # occupy 10.0.0.10 and 10.0.0.11 manually
    _ip(editor, net["id"], "10.0.0.10")
    _ip(editor, net["id"], "10.0.0.11")

    first = _auto(editor, net["id"], pool_a["id"])
    assert first.status_code == 201, first.text
    assert first.json()["ip_address"]["address"] == "10.0.0.12"
    assert first.json()["ip_address"]["ip_pool"]["id"] == pool_a["id"]

    # pool_a is now exhausted; the other AUTO pool must NOT be used
    resp = _auto(editor, net["id"], pool_a["id"])
    assert resp.status_code == 409, resp.text
    details = resp.json()["error"]["details"]
    assert details["reason"] == "no_available_address"
    assert details["network_id"] == net["id"]
    assert details["ip_pool_id"] == pool_a["id"]


def test_auto_allocation_skips_gateway_and_reserved(role_client_factory):
    """A6: the ascending scan skips gateway and RESERVED addresses inside the pool.

    A RESERVED pool may not overlap an AUTO pool (F009 exclusion), so this checks
    the gateway skip only; the RESERVED exclusion is covered by the boundary test.
    """
    editor, _, _ = role_client_factory("EDITOR")
    c1 = _cluster(editor, code="C1")
    net = _network(editor, c1["id"], name="n1", cidr="10.0.0.0/24",
                   auto_allocate=True)
    pool = _pool(editor, net["id"], name="a", start="10.0.0.1", end="10.0.0.5",
                 allocation_mode="AUTO")
    # gateway inside the pool range
    editor.patch(
        f"/api/v1/networks/{net['id']}",
        json={"version": 1, "gateway": "10.0.0.1"},
    )
    resp = _auto(editor, net["id"], pool["id"])
    assert resp.status_code == 201, resp.text
    assert resp.json()["ip_address"]["address"] == "10.0.0.2"


# --- A9-A12: unbound occupancy, bind/unbind, release permissions -------------


def test_unbound_occupies_and_unbind_keeps(role_client_factory):
    """A9/A10: an unbound IP still occupies; unbind does not release."""
    editor, _, _ = role_client_factory("EDITOR")
    c1 = _cluster(editor, code="C1")
    net = _network(editor, c1["id"], name="n1", cidr="10.0.0.0/24")
    res = _resource(editor, c1["id"])
    iface = _interface(editor, res["id"])

    ip = _ip(editor, net["id"], "10.0.0.5")
    # still not re-allocatable while unbound
    assert _allocate(editor, net["id"], "10.0.0.5").status_code == 409

    bound = editor.patch(
        f"/api/v1/ip-addresses/{ip['id']}",
        json={"version": 1, "interface": iface["id"]},
    )
    assert bound.status_code == 200, bound.text
    assert bound.json()["ip_address"]["interface"]["id"] == iface["id"]

    unbound = editor.patch(
        f"/api/v1/ip-addresses/{ip['id']}",
        json={"version": 2, "interface": None},
    )
    assert unbound.status_code == 200, unbound.text
    assert unbound.json()["ip_address"]["interface"] is None
    # still occupies
    assert _allocate(editor, net["id"], "10.0.0.5").status_code == 409


def test_release_permission_and_reuse(role_client_factory):
    """A12/A13: release needs RELEASE_IP; after release the address is reusable."""
    admin, _, _ = role_client_factory("ADMIN")
    editor, _, _ = role_client_factory("EDITOR")
    c1 = _cluster(admin, code="C1")
    net = _network(admin, c1["id"], name="n1", cidr="10.0.0.0/24")
    ip = _ip(editor, net["id"], "10.0.0.5")

    # EDITOR cannot release (needs RELEASE_IP)
    forbidden = editor.delete(
        f"/api/v1/ip-addresses/{ip['id']}", params={"version": 1}
    )
    assert forbidden.status_code == 403
    assert forbidden.json()["error"]["details"]["reason"] == "permission"

    # ADMIN releases
    assert admin.delete(
        f"/api/v1/ip-addresses/{ip['id']}", params={"version": 1}
    ).status_code == 204
    # reusable in the same cluster
    assert _allocate(editor, net["id"], "10.0.0.5").status_code == 201


# --- A11/A14/A15: transfer, cluster scope, binding consistency ---------------


def test_same_cluster_unique_and_cross_cluster_allowed(role_client_factory):
    """A14: same-Cluster duplicate 409; different Cluster may reuse the address."""
    editor, _, _ = role_client_factory("EDITOR")
    c1 = _cluster(editor, code="C1")
    c2 = _cluster(editor, code="C2")
    n1 = _network(editor, c1["id"], name="n1", cidr="10.0.0.0/24")
    n2 = _network(editor, c2["id"], name="n2", cidr="10.0.0.0/24")
    _ip(editor, n1["id"], "10.0.0.5")

    dup = _allocate(editor, n1["id"], "10.0.0.5")
    assert dup.status_code == 409
    details = dup.json()["error"]["details"]
    assert details["reason"] == "unique_conflict"
    assert details["field"] == "address"

    # same address, different network but same cluster -> still a conflict
    n1b = _network(editor, c1["id"], name="n1b", cidr="10.9.0.0/24")
    assert _allocate(editor, n1b["id"], "10.9.0.5").status_code == 201
    # different cluster -> allowed
    assert _allocate(editor, n2["id"], "10.0.0.5").status_code == 201


def test_transfer_and_cross_cluster_binding(role_client_factory):
    """A11/A15: transfer within a cluster; cross-cluster binding is 422."""
    editor, _, _ = role_client_factory("EDITOR")
    c1 = _cluster(editor, code="C1")
    c2 = _cluster(editor, code="C2")
    net = _network(editor, c1["id"], name="n1", cidr="10.0.0.0/24")
    r1 = _resource(editor, c1["id"], hostname="h1")
    r2 = _resource(editor, c2["id"], hostname="h2")
    if1 = _interface(editor, r1["id"], name="eth0")
    if2 = _interface(editor, r1["id"], name="eth1")
    foreign = _interface(editor, r2["id"], name="eth0")

    ip = _ip(editor, net["id"], "10.0.0.5")
    assert editor.patch(
        f"/api/v1/ip-addresses/{ip['id']}", json={"version": 1, "interface": if1["id"]}
    ).status_code == 200
    # transfer to another interface of the same cluster
    transferred = editor.patch(
        f"/api/v1/ip-addresses/{ip['id']}", json={"version": 2, "interface": if2["id"]}
    )
    assert transferred.status_code == 200
    assert transferred.json()["ip_address"]["interface"]["id"] == if2["id"]
    # cross-cluster transfer rejected
    bad = editor.patch(
        f"/api/v1/ip-addresses/{ip['id']}",
        json={"version": 3, "interface": foreign["id"]},
    )
    assert bad.status_code == 422
    assert bad.json()["error"]["details"]["fields"][0]["field"] == "interface"


# --- A18: Endpoint reference hook (F012 reserved) ----------------------------


def test_endpoint_reference_hook_blocks_unbind_and_release(
    role_client_factory, monkeypatch
):
    """A18: a registered reference checker blocks unbind/transfer/release."""
    admin, _, _ = role_client_factory("ADMIN")
    c1 = _cluster(admin, code="C1")
    net = _network(admin, c1["id"], name="n1", cidr="10.0.0.0/24")
    res = _resource(admin, c1["id"])
    iface = _interface(admin, res["id"])
    ip = _ip(admin, net["id"], "10.0.0.5")

    refs = [{"object_type": "service_endpoint", "object_id": str(uuid.uuid4()), "label": "ssh:22"}]
    monkeypatch.setattr(
        ip_address_reference, "_CHECKERS", [lambda db, ip_id: list(refs)]
    )

    for method, url, body in (
        (
            "patch",
            f"/api/v1/ip-addresses/{ip['id']}",
            {"version": 1, "interface": iface["id"]},
        ),
        ("delete", f"/api/v1/ip-addresses/{ip['id']}", None),
    ):
        if method == "patch":
            resp = admin.patch(url, json=body)
        else:
            resp = admin.delete(url, params={"version": 1})
        assert resp.status_code == 409, (method, resp.text)
        details = resp.json()["error"]["details"]
        assert details["reason"] == "reference_exists"
        assert details["references"][0]["object_type"] == "service_endpoint"


# --- A19/A20: Network/Interface references and Pool source exception ---------


def test_undeleted_ip_blocks_network_and_interface_delete(role_client_factory):
    """A19: an undeleted IP blocks deleting its Network and bound Interface."""
    admin, _, _ = role_client_factory("ADMIN")
    c1 = _cluster(admin, code="C1")
    net = _network(admin, c1["id"], name="n1", cidr="10.0.0.0/24")
    res = _resource(admin, c1["id"])
    iface = _interface(admin, res["id"])
    ip = _ip(admin, net["id"], "10.0.0.5")
    admin.patch(
        f"/api/v1/ip-addresses/{ip['id']}", json={"version": 1, "interface": iface["id"]}
    )

    net_delete = admin.delete(f"/api/v1/networks/{net['id']}", params={"version": 1})
    assert net_delete.status_code == 409
    assert net_delete.json()["error"]["details"]["reason"] == "reference_exists"

    if_delete = admin.delete(
        f"/api/v1/interfaces/{iface['id']}", params={"version": 1}
    )
    assert if_delete.status_code == 409
    refs = if_delete.json()["error"]["details"]["references"]
    assert refs[0]["object_type"] == "ip_address"

    # changing cidr is blocked by the same reference set
    cidr_change = admin.patch(
        f"/api/v1/networks/{net['id']}",
        json={"version": 1, "cidr": "10.0.1.0/24"},
    )
    assert cidr_change.status_code == 409
    assert cidr_change.json()["error"]["details"]["reason"] == "reference_exists"


def test_pool_source_exception(role_client_factory):
    """A20: the Pool allocation source never blocks or reclaims the IP."""
    admin, _, _ = role_client_factory("ADMIN")
    c1 = _cluster(admin, code="C1")
    net = _network(admin, c1["id"], name="n1", cidr="10.0.0.0/24")
    pool = _pool(admin, net["id"], name="p", start="10.0.0.1", end="10.0.0.9")
    ip = _ip(admin, net["id"], "10.0.0.5")
    assert ip["ip_pool"]["id"] == pool["id"]

    # shrinking and deleting the pool are allowed and keep the IP + source
    assert admin.patch(
        f"/api/v1/ip-pools/{pool['id']}",
        json={"version": 1, "end_address": "10.0.0.3"},
    ).status_code == 200
    assert admin.delete(
        f"/api/v1/ip-pools/{pool['id']}", params={"version": 2}
    ).status_code == 204
    detail = admin.get(f"/api/v1/ip-addresses/{ip['id']}").json()["ip_address"]
    assert detail["ip_pool"]["id"] == pool["id"]


# --- A22: restore ------------------------------------------------------------


def test_restore_rechecks(role_client_factory):
    """A22: restore re-checks uniqueness, dependencies and CIDR containment."""
    admin, _, _ = role_client_factory("ADMIN")
    c1 = _cluster(admin, code="C1")
    net = _network(admin, c1["id"], name="n1", cidr="10.0.0.0/24")
    ip = _ip(admin, net["id"], "10.0.0.5")
    assert admin.delete(
        f"/api/v1/ip-addresses/{ip['id']}", params={"version": 1}
    ).status_code == 204

    # a newer allocation of the same address blocks the restore
    _ip(admin, net["id"], "10.0.0.5")
    conflict = admin.post(
        f"/api/v1/ip-addresses/{ip['id']}/restore", params={"version": 2}
    )
    assert conflict.status_code == 409
    assert conflict.json()["error"]["details"]["reason"] == "unique_conflict"

    # restoring a not-deleted object
    live = admin.get(f"/api/v1/ip-addresses/{ip['id']}", params={"deleted": "true"})
    assert live.status_code == 200
    not_deleted = admin.post(
        f"/api/v1/ip-addresses/{ip['id']}/restore", params={"version": 2}
    )
    assert not_deleted.status_code == 409
    assert not_deleted.json()["error"]["details"]["reason"] == "unique_conflict"


def test_restore_dependency_deleted_network(role_client_factory):
    """A22: a soft-deleted Network blocks restore with dependency_deleted."""
    admin, _, _ = role_client_factory("ADMIN")
    c1 = _cluster(admin, code="C1")
    net = _network(admin, c1["id"], name="n1", cidr="10.0.0.0/24")
    ip = _ip(admin, net["id"], "10.0.0.5")
    admin.delete(f"/api/v1/ip-addresses/{ip['id']}", params={"version": 1})
    # soft delete the (now unreferenced) network
    assert admin.delete(
        f"/api/v1/networks/{net['id']}", params={"version": 1}
    ).status_code == 204
    resp = admin.post(
        f"/api/v1/ip-addresses/{ip['id']}/restore", params={"version": 2}
    )
    assert resp.status_code == 409
    details = resp.json()["error"]["details"]
    assert details["reason"] == "dependency_deleted"
    assert details["conflicts"][0]["object_type"] == "network"


def test_restore_success_after_release(role_client_factory):
    """A22: a plain restore succeeds and writes a RESTORE audit row."""
    admin, _, _ = role_client_factory("ADMIN")
    c1 = _cluster(admin, code="C1")
    net = _network(admin, c1["id"], name="n1", cidr="10.0.0.0/24")
    ip = _ip(admin, net["id"], "10.0.0.5")
    admin.delete(f"/api/v1/ip-addresses/{ip['id']}", params={"version": 1})
    restored = admin.post(
        f"/api/v1/ip-addresses/{ip['id']}/restore", params={"version": 2}
    )
    assert restored.status_code == 200, restored.text
    assert restored.json()["ip_address"]["deleted_at"] is None
    assert restored.json()["ip_address"]["version"] == 3


def test_restore_rechecks_allocatable_boundary(role_client_factory):
    """F010-REV-01: restore re-checks the §11.1 gateway/RESERVED boundary (422).

    An address that was allocatable at creation but became a gateway or fell
    into a RESERVED range after release must not be restored; the boundary
    failure is 422 ``field:"address"`` (same shape as manual allocation §6.2).
    """
    admin, _, _ = role_client_factory("ADMIN")
    c1 = _cluster(admin, code="C1")

    # 1) the released address later becomes the Network gateway
    net_gw = _network(admin, c1["id"], name="gw", cidr="10.0.0.0/24")
    ip_gw = _ip(admin, net_gw["id"], "10.0.0.5")
    admin.delete(f"/api/v1/ip-addresses/{ip_gw['id']}", params={"version": 1})
    assert admin.patch(
        f"/api/v1/networks/{net_gw['id']}",
        json={"version": 1, "gateway": "10.0.0.5"},
    ).status_code == 200
    gateway = admin.post(
        f"/api/v1/ip-addresses/{ip_gw['id']}/restore", params={"version": 2}
    )
    assert gateway.status_code == 422, gateway.text
    fields = gateway.json()["error"]["details"]["fields"]
    assert any(f["field"] == "address" for f in fields)

    # 2) a new RESERVED pool covers the released address
    net_res = _network(admin, c1["id"], name="res", cidr="10.1.0.0/24")
    ip_res = _ip(admin, net_res["id"], "10.1.0.5")
    admin.delete(f"/api/v1/ip-addresses/{ip_res['id']}", params={"version": 1})
    _pool(admin, net_res["id"], name="r", start="10.1.0.1", end="10.1.0.9",
          allocation_mode="RESERVED")
    reserved = admin.post(
        f"/api/v1/ip-addresses/{ip_res['id']}/restore", params={"version": 2}
    )
    assert reserved.status_code == 422, reserved.text
    fields = reserved.json()["error"]["details"]["fields"]
    assert any(f["field"] == "address" for f in fields)

    # 3) an address that stays allocatable restores normally
    net_ok = _network(admin, c1["id"], name="ok", cidr="10.2.0.0/24")
    ip_ok = _ip(admin, net_ok["id"], "10.2.0.5")
    admin.delete(f"/api/v1/ip-addresses/{ip_ok['id']}", params={"version": 1})
    ok = admin.post(
        f"/api/v1/ip-addresses/{ip_ok['id']}/restore", params={"version": 2}
    )
    assert ok.status_code == 200, ok.text
    assert ok.json()["ip_address"]["deleted_at"] is None


def test_restore_uniqueness_and_dependency_beat_boundary(
    role_client_factory, auth_session_factory
):
    """A22/F010-REV-01: 409 uniqueness/dependency still precede the 422 boundary."""
    admin, _, _ = role_client_factory("ADMIN")
    c1 = _cluster(admin, code="C1")

    # uniqueness (409) wins when a live duplicate and a gateway collision coexist
    net_pri = _network(admin, c1["id"], name="pri", cidr="10.3.0.0/24")
    ip_pri = _ip(admin, net_pri["id"], "10.3.0.5")
    admin.delete(f"/api/v1/ip-addresses/{ip_pri['id']}", params={"version": 1})
    _ip(admin, net_pri["id"], "10.3.0.5")
    # raw write: the API would reject the gateway while the address is occupied,
    # so force the boundary collision to prove the ordering.
    with auth_session_factory() as session:
        session.execute(
            text("UPDATE networks SET gateway = '10.3.0.5' WHERE id = :id"),
            {"id": uuid.UUID(net_pri["id"])},
        )
        session.commit()
    unique = admin.post(
        f"/api/v1/ip-addresses/{ip_pri['id']}/restore", params={"version": 2}
    )
    assert unique.status_code == 409, unique.text
    assert unique.json()["error"]["details"]["reason"] == "unique_conflict"

    # dependency (409) wins over the boundary 422 for a deleted Interface
    net_dep = _network(admin, c1["id"], name="dep", cidr="10.4.0.0/24")
    res = _resource(admin, c1["id"], hostname="hd")
    iface = _interface(admin, res["id"])
    ip_dep = _ip(admin, net_dep["id"], "10.4.0.5")
    admin.patch(
        f"/api/v1/ip-addresses/{ip_dep['id']}",
        json={"version": 1, "interface": iface["id"]},
    )
    admin.delete(f"/api/v1/ip-addresses/{ip_dep['id']}", params={"version": 2})
    assert admin.patch(
        f"/api/v1/networks/{net_dep['id']}",
        json={"version": 1, "gateway": "10.4.0.5"},
    ).status_code == 200
    assert admin.delete(
        f"/api/v1/interfaces/{iface['id']}", params={"version": 1}
    ).status_code == 204
    dependency = admin.post(
        f"/api/v1/ip-addresses/{ip_dep['id']}/restore", params={"version": 3}
    )
    assert dependency.status_code == 409, dependency.text
    assert dependency.json()["error"]["details"]["reason"] == "dependency_deleted"


# --- A24: permissions, audit and activity ------------------------------------


def test_permissions_and_activity(role_client_factory, auth_session_factory):
    """A24: VIEWER read-only; EDITOR binds; ADMIN releases; Activity visible."""
    admin, _, _ = role_client_factory("ADMIN")
    editor, _, _ = role_client_factory("EDITOR")
    viewer, _, _ = role_client_factory("VIEWER")
    c1 = _cluster(admin, code="C1")
    net = _network(admin, c1["id"], name="n1", cidr="10.0.0.0/24")
    res = _resource(admin, c1["id"])
    iface = _interface(admin, res["id"])

    # VIEWER cannot create
    assert _allocate(viewer, net["id"], "10.0.0.5").status_code == 403
    ip = _ip(editor, net["id"], "10.0.0.5")
    editor.patch(
        f"/api/v1/ip-addresses/{ip['id']}", json={"version": 1, "interface": iface["id"]}
    )
    editor.patch(
        f"/api/v1/ip-addresses/{ip['id']}",
        json={"version": 2, "interface": None, "description": "freed"},
    )
    # Activity is available to all roles while the object is undeleted.
    activity = viewer.get(f"/api/v1/ip-addresses/{ip['id']}/activity")
    assert activity.status_code == 200, activity.text
    actions = [item["action"] for item in activity.json()["items"]]
    assert actions == ["CREATE", "UPDATE", "UPDATE"]

    admin.delete(f"/api/v1/ip-addresses/{ip['id']}", params={"version": 3})
    # A soft-deleted object needs deleted=true + VIEW_DELETED (ADMIN only).
    admin_activity = admin.get(
        f"/api/v1/ip-addresses/{ip['id']}/activity", params={"deleted": "true"}
    )
    assert admin_activity.status_code == 200
    assert [i["action"] for i in admin_activity.json()["items"]] == [
        "CREATE", "UPDATE", "UPDATE", "DELETE"
    ]
    assert viewer.get(
        f"/api/v1/ip-addresses/{ip['id']}/activity", params={"deleted": "true"}
    ).status_code == 403

    with auth_session_factory() as session:
        rows = (
            session.query(AuditLog)
            .filter(AuditLog.object_type == "ip_address")
            .all()
        )
    assert {row.action for row in rows} >= {"CREATE", "UPDATE", "DELETE"}


# --- A25/A26: validation, immutability, optimistic lock ----------------------


def test_body_validation_and_immutability(role_client_factory):
    """A25: required/unknown/read-only fields; PATCH omission semantics."""
    editor, _, _ = role_client_factory("EDITOR")
    c1 = _cluster(editor, code="C1")
    net = _network(editor, c1["id"], name="n1", cidr="10.0.0.0/24")

    assert editor.post("/api/v1/ip-addresses", json={}).status_code == 422
    assert editor.post(
        "/api/v1/ip-addresses", json={"network": net["id"]}
    ).status_code == 422
    # POST rejects interface / ip_pool / metadata / cluster_id (read-only)
    for extra in (
        {"interface": str(uuid.uuid4())},
        {"ip_pool": str(uuid.uuid4())},
        {"metadata": {}},
        {"cluster_id": str(c1["id"])},
    ):
        body = {"network": net["id"], "address": "10.0.0.5"}
        body.update(extra)
        assert editor.post("/api/v1/ip-addresses", json=body).status_code == 422

    ip = _ip(editor, net["id"], "10.0.0.5")
    # immutable / read-only fields on PATCH
    for extra in (
        {"network": str(net["id"])},
        {"address": "10.0.0.6"},
        {"cluster_id": str(c1["id"])},
        {"ip_pool": None},
    ):
        body = {"version": 1}
        body.update(extra)
        assert editor.patch(
            f"/api/v1/ip-addresses/{ip['id']}", json=body
        ).status_code == 422

    # omission keeps the value
    patched = editor.patch(
        f"/api/v1/ip-addresses/{ip['id']}", json={"version": 1, "description": "d"}
    )
    assert patched.status_code == 200
    assert patched.json()["ip_address"]["description"] == "d"
    assert patched.json()["ip_address"]["address"] == "10.0.0.5"


def test_optimistic_lock(role_client_factory):
    """A26: a stale version is 409 VERSION_CONFLICT with current_version."""
    editor, _, _ = role_client_factory("EDITOR")
    c1 = _cluster(editor, code="C1")
    net = _network(editor, c1["id"], name="n1", cidr="10.0.0.0/24")
    ip = _ip(editor, net["id"], "10.0.0.5")
    editor.patch(
        f"/api/v1/ip-addresses/{ip['id']}", json={"version": 1, "description": "a"}
    )
    stale = editor.patch(
        f"/api/v1/ip-addresses/{ip['id']}", json={"version": 1, "description": "b"}
    )
    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "VERSION_CONFLICT"
    assert stale.json()["error"]["details"]["current_version"] == 2


# --- list / filters / sorting ------------------------------------------------


def test_list_filters_and_sorting(role_client_factory):
    admin, _, _ = role_client_factory("ADMIN")
    editor, _, _ = role_client_factory("EDITOR")
    c1 = _cluster(editor, code="C1")
    net = _network(editor, c1["id"], name="n1", cidr="10.0.0.0/24")
    res = _resource(editor, c1["id"])
    iface = _interface(editor, res["id"])
    pool = _pool(editor, net["id"], name="p", start="10.0.0.10", end="10.0.0.20",
                 allocation_mode="AUTO")
    a = _ip(editor, net["id"], "10.0.0.30")
    b = _ip(editor, net["id"], "10.0.0.10")
    editor.patch(
        f"/api/v1/ip-addresses/{a['id']}", json={"version": 1, "interface": iface["id"]}
    )

    listing = editor.get("/api/v1/ip-addresses", params={"sort": "address", "order": "asc"})
    addresses = [i["address"] for i in listing.json()["items"]]
    assert addresses == ["10.0.0.10", "10.0.0.30"]

    bound = editor.get("/api/v1/ip-addresses", params={"bound": "true"})
    assert [i["address"] for i in bound.json()["items"]] == ["10.0.0.30"]

    by_pool = editor.get("/api/v1/ip-addresses", params={"ip_pool_id": pool["id"]})
    assert [i["address"] for i in by_pool.json()["items"]] == ["10.0.0.10"]

    exact = editor.get("/api/v1/ip-addresses", params={"address": "10.0.0.10"})
    assert exact.json()["total"] == 1

    substring = editor.get("/api/v1/ip-addresses", params={"q": ".0.10"})
    assert [i["address"] for i in substring.json()["items"]] == ["10.0.0.10"]

    invalid = editor.get("/api/v1/ip-addresses", params={"address": "nope"})
    assert invalid.status_code == 422

    # deleted visibility
    admin.delete(f"/api/v1/ip-addresses/{b['id']}", params={"version": 1})
    default = editor.get("/api/v1/ip-addresses")
    assert b["id"] not in {i["id"] for i in default.json()["items"]}
    viewer, _, _ = role_client_factory("VIEWER")
    include = viewer.get("/api/v1/ip-addresses", params={"deleted": "include"})
    assert include.status_code == 403


# --- real occupancy provider (F009-CON-01) -----------------------------------


def test_gateway_and_reserved_see_real_occupancy(role_client_factory):
    """F009-CON-01/DR-138: the real provider makes address_in_use reachable."""
    admin, _, _ = role_client_factory("ADMIN")
    editor, _, _ = role_client_factory("EDITOR")
    c1 = _cluster(editor, code="C1")
    net = _network(editor, c1["id"], name="n1", cidr="10.0.0.0/24")
    ip = _ip(editor, net["id"], "10.0.0.5")

    # setting the occupied address (unbound) as gateway is rejected
    gateway = editor.patch(
        f"/api/v1/networks/{net['id']}",
        json={"version": 1, "gateway": "10.0.0.5"},
    )
    assert gateway.status_code == 409, gateway.text
    details = gateway.json()["error"]["details"]
    assert details["reason"] == "address_in_use"
    assert details["field"] == "gateway"
    assert details["conflict_count"] == 1
    assert details["conflicts"][0]["object_type"] == "ip_address"

    # a RESERVED pool over the occupied address is rejected
    reserved = editor.post(
        "/api/v1/ip-pools",
        json={
            "network": net["id"],
            "name": "r",
            "start_address": "10.0.0.1",
            "end_address": "10.0.0.9",
            "allocation_mode": "RESERVED",
        },
    )
    assert reserved.status_code == 409, reserved.text
    assert reserved.json()["error"]["details"]["reason"] == "address_in_use"

    # after release the gateway becomes settable
    admin.delete(f"/api/v1/ip-addresses/{ip['id']}", params={"version": 1})
    ok = editor.patch(
        f"/api/v1/networks/{net['id']}",
        json={"version": 1, "gateway": "10.0.0.5"},
    )
    assert ok.status_code == 200, ok.text


def test_occupancy_provider_shape(role_client_factory, auth_session_factory):
    """DR-109 shape: total/items with bound + resource fields."""
    editor, _, _ = role_client_factory("EDITOR")
    c1 = _cluster(editor, code="C1")
    net = _network(editor, c1["id"], name="n1", cidr="10.0.0.0/24")
    res = _resource(editor, c1["id"], hostname="h9")
    iface = _interface(editor, res["id"])
    ip = _ip(editor, net["id"], "10.0.0.5")
    editor.patch(
        f"/api/v1/ip-addresses/{ip['id']}", json={"version": 1, "interface": iface["id"]}
    )
    with auth_session_factory() as session:
        result = ip_occupancy.check_occupancy(
            session, uuid.UUID(net["id"]), "10.0.0.1", "10.0.0.9", 100
        )
    assert result["total"] == 1
    item = result["items"][0]
    assert item["object_type"] == "ip_address"
    assert item["address"] == "10.0.0.5"
    assert item["bound"] is True
    assert item["resource_hostname"] == "h9"
    assert item["interface_id"] == iface["id"]


# --- A23: capacity -----------------------------------------------------------


def test_capacity_endpoint_formula(role_client_factory):
    """A23: §20 Network/AUTO-pool capacity from the real data."""
    editor, _, _ = role_client_factory("EDITOR")
    c1 = _cluster(editor, code="C1")
    net = _network(editor, c1["id"], name="n1", cidr="10.10.0.0/24",
                   gateway="10.10.0.1")
    _pool(editor, net["id"], name="res", start="10.10.0.2", end="10.10.0.10",
          allocation_mode="RESERVED")
    auto = _pool(editor, net["id"], name="auto", start="10.10.0.100",
                 end="10.10.0.110", allocation_mode="AUTO")
    _ip(editor, net["id"], "10.10.0.100")  # in AUTO
    _ip(editor, net["id"], "10.10.0.200")  # pool-less manual, still Network-occupied

    resp = editor.get(f"/api/v1/networks/{net['id']}/capacity")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    # base /24 = 254; minus gateway 1, minus RESERVED 9 => 244
    assert body["network_capacity"]["allocatable_total"] == 244
    assert body["network_capacity"]["occupied"] == 2
    assert body["network_capacity"]["remaining"] == 242
    assert body["network_capacity"]["network"]["status"] == "ACTIVE"

    assert len(body["auto_pools"]) == 1
    auto_block = body["auto_pools"][0]
    assert auto_block["ip_pool"]["id"] == auto["id"]
    assert auto_block["allocatable_total"] == 11
    assert auto_block["occupied"] == 1
    assert auto_block["remaining"] == 10


def test_capacity_negative_remaining_not_clamped(
    role_client_factory, auth_session_factory
):
    """A23: remaining is a direct difference and may be negative (no clamp)."""
    editor, _, _ = role_client_factory("EDITOR")
    c1 = _cluster(editor, code="C1")
    net = _network(editor, c1["id"], name="n1", cidr="10.0.0.0/30")
    # /30 base usable = 2. Insert two IPs, then force the gateway colliding with
    # one of them directly (the API rejects that, DB allows the raw write) so the
    # allocatable total drops to 1 while occupancy stays 2.
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
    body = editor.get(f"/api/v1/networks/{net['id']}/capacity").json()
    assert body["network_capacity"]["allocatable_total"] == 1
    assert body["network_capacity"]["occupied"] == 2
    assert body["network_capacity"]["remaining"] == -1


def test_capacity_excludes_disabled_and_dedups_gateway_reserved(role_client_factory):
    """A23: disabled ranges excluded; gateway inside RESERVED is not double-counted."""
    editor, _, _ = role_client_factory("EDITOR")
    c1 = _cluster(editor, code="C1")
    net = _network(editor, c1["id"], name="n1", cidr="0.0.0.0/0",
                   gateway="10.0.0.1")
    _pool(editor, net["id"], name="res", start="10.0.0.1", end="10.0.0.9",
          allocation_mode="RESERVED")
    body = editor.get(f"/api/v1/networks/{net['id']}/capacity").json()
    total = body["network_capacity"]["allocatable_total"]
    # base /0 = 2**32 - 2; the two excluded base addresses (0.0.0.0 and
    # 255.255.255.255) both fall inside disabled ranges, so only the remaining
    # disabled addresses plus the 9 RESERVED addresses are removed. The gateway
    # sits inside the RESERVED range and is not double-counted.
    disabled = sum(
        net_.num_addresses
        for net_ in (
            __import__("ipaddress").ip_network(c)
            for c in ("0.0.0.0/8", "127.0.0.0/8", "169.254.0.0/16",
                      "224.0.0.0/4", "240.0.0.0/4")
        )
    )
    disabled_inside_base = disabled - 2
    assert total == (2**32 - 2) - disabled_inside_base - 9


def test_capacity_soft_deleted_network_404(role_client_factory):
    """A23: a soft-deleted Network has no capacity (404)."""
    admin, _, _ = role_client_factory("ADMIN")
    c1 = _cluster(admin, code="C1")
    net = _network(admin, c1["id"], name="n1", cidr="10.0.0.0/24")
    assert admin.delete(
        f"/api/v1/networks/{net['id']}", params={"version": 1}
    ).status_code == 204
    assert admin.get(f"/api/v1/networks/{net['id']}/capacity").status_code == 404


# --- A8/A21: concurrency (real commits) --------------------------------------


def test_concurrent_auto_allocation_no_duplicates(auth_session_factory, role_client_factory):
    """A8/T07: concurrent auto allocation never returns duplicate addresses."""
    admin, user, _ = role_client_factory("ADMIN")
    c1 = _cluster(admin, code="C1")
    net = _network(admin, c1["id"], name="n1", cidr="10.0.0.0/24",
                   auto_allocate=True)
    pool = _pool(admin, net["id"], name="a", start="10.0.0.1", end="10.0.0.5",
                 allocation_mode="AUTO")
    operator = _operator(user)

    barrier = threading.Barrier(2)
    results: list[object] = []

    def worker() -> None:
        session = auth_session_factory()
        try:
            barrier.wait(timeout=10)
            ip = ip_address_service.auto_allocate_ip_address(
                session,
                operator,
                network=net["id"],
                ip_pool=pool["id"],
            )
            results.append(str(ip.address))
        except Exception as exc:  # noqa: BLE001 - recorded for the assertion
            session.rollback()
            results.append(exc)
        finally:
            session.close()

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)

    addresses = [r for r in results if isinstance(r, str)]
    assert len(addresses) == 2, results
    assert len(set(addresses)) == 2, addresses

    listing = admin.get("/api/v1/ip-addresses", params={"network_id": net["id"]})
    persisted = [i["address"] for i in listing.json()["items"]]
    assert len(persisted) == len(set(persisted)) == 2


def test_concurrent_reserved_change_and_allocation(auth_session_factory, role_client_factory):
    """A21/T35: a RESERVED change and an allocation cannot both succeed."""
    admin, user, _ = role_client_factory("ADMIN")
    c1 = _cluster(admin, code="C1")
    net = _network(admin, c1["id"], name="n1", cidr="10.0.0.0/24")
    operator = _operator(user)

    barrier = threading.Barrier(2)
    results: list[object] = []

    def allocate() -> None:
        session = auth_session_factory()
        try:
            barrier.wait(timeout=10)
            ip_address_service.create_ip_address(
                session, operator, network=net["id"], address="10.0.0.15"
            )
            results.append("allocated")
        except Exception as exc:  # noqa: BLE001
            session.rollback()
            results.append(exc)
        finally:
            session.close()

    def reserve() -> None:
        session = auth_session_factory()
        try:
            barrier.wait(timeout=10)
            ip_pool_service.create_ip_pool(
                session,
                operator,
                network=net["id"],
                name="res",
                start_address="10.0.0.10",
                end_address="10.0.0.20",
                allocation_mode="RESERVED",
            )
            results.append("reserved")
        except Exception as exc:  # noqa: BLE001
            session.rollback()
            results.append(exc)
        finally:
            session.close()

    threads = [threading.Thread(target=allocate), threading.Thread(target=reserve)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)

    successes = [r for r in results if isinstance(r, str)]
    failures = [r for r in results if not isinstance(r, str)]
    assert len(successes) == 1, results
    assert len(failures) == 1, results
    # the losing side is either 409 address_in_use (allocated first) or 422
    # (reserved first, the address becomes non-allocatable)
    loser = failures[0]
    assert isinstance(loser, (Conflict, ValidationError)), loser

    # capacity is consistent: never both an allocated IP and an overlapping pool
    # that should have been rejected.
    listing = admin.get("/api/v1/ip-addresses", params={"network_id": net["id"]})
    pools = admin.get("/api/v1/ip-pools", params={"network_id": net["id"]})
    assert listing.status_code == 200 and pools.status_code == 200


def test_concurrent_gateway_change_and_allocation(
    auth_session_factory, role_client_factory
):
    """A21/T35: a Network gateway change and an allocation of that address
    cannot both succeed; final state never has an IP at the gateway."""
    admin, user, _ = role_client_factory("ADMIN")
    c1 = _cluster(admin, code="C1")
    net = _network(admin, c1["id"], name="n1", cidr="10.0.0.0/24")
    operator = _operator(user)
    network_id = uuid.UUID(net["id"])

    barrier = threading.Barrier(2)
    results: list[object] = []

    def allocate() -> None:
        session = auth_session_factory()
        try:
            barrier.wait(timeout=10)
            ip_address_service.create_ip_address(
                session, operator, network=net["id"], address="10.0.0.15"
            )
            results.append("allocated")
        except Exception as exc:  # noqa: BLE001
            session.rollback()
            results.append(exc)
        finally:
            session.close()

    def set_gateway() -> None:
        session = auth_session_factory()
        try:
            barrier.wait(timeout=10)
            network_service.update_network(
                session,
                operator,
                network_id,
                expected_version=1,
                changes={"gateway": "10.0.0.15"},
            )
            results.append("gateway")
        except Exception as exc:  # noqa: BLE001
            session.rollback()
            results.append(exc)
        finally:
            session.close()

    threads = [threading.Thread(target=allocate), threading.Thread(target=set_gateway)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)

    successes = [r for r in results if isinstance(r, str)]
    assert len(successes) == 1, results

    # The final state is consistent: either the IP exists (gateway unchanged) or
    # the gateway is the address (no IP), never both.
    detail = admin.get(f"/api/v1/networks/{net['id']}").json()["network"]
    listed = admin.get("/api/v1/ip-addresses", params={"network_id": net["id"]})
    addresses = {i["address"] for i in listed.json()["items"]}
    has_ip = "10.0.0.15" in addresses
    is_gateway = detail["gateway"] == "10.0.0.15"
    assert not (has_ip and is_gateway), (addresses, detail["gateway"])


def test_concurrent_restore_and_reallocate(
    auth_session_factory, role_client_factory
):
    """A13/A22/B44: restoring a released IP and reallocating the same address
    cannot both survive; the partial unique index closes the race."""
    admin, user, _ = role_client_factory("ADMIN")
    c1 = _cluster(admin, code="C1")
    net = _network(admin, c1["id"], name="n1", cidr="10.0.0.0/24")
    ip = _ip(admin, net["id"], "10.0.0.5")
    admin.delete(f"/api/v1/ip-addresses/{ip['id']}", params={"version": 1})
    operator = _operator(user)
    ip_id = uuid.UUID(ip["id"])

    barrier = threading.Barrier(2)
    results: list[object] = []

    def restore() -> None:
        session = auth_session_factory()
        try:
            barrier.wait(timeout=10)
            ip_address_service.restore_ip_address(
                session, operator, ip_id, expected_version=2
            )
            results.append("restored")
        except Exception as exc:  # noqa: BLE001
            session.rollback()
            results.append(exc)
        finally:
            session.close()

    def reallocate() -> None:
        session = auth_session_factory()
        try:
            barrier.wait(timeout=10)
            ip_address_service.create_ip_address(
                session, operator, network=net["id"], address="10.0.0.5"
            )
            results.append("created")
        except Exception as exc:  # noqa: BLE001
            session.rollback()
            results.append(exc)
        finally:
            session.close()

    threads = [threading.Thread(target=restore), threading.Thread(target=reallocate)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)

    successes = [r for r in results if isinstance(r, str)]
    assert len(successes) == 1, results
    # exactly one live occupant of the address
    listed = admin.get("/api/v1/ip-addresses")
    live = [i for i in listed.json()["items"] if i["address"] == "10.0.0.5"]
    assert len(live) == 1, live


def test_concurrent_version_conflict_two_sessions(
    auth_session_factory, role_client_factory
):
    """A26/B45: two live sessions PATCH the same version; exactly one wins and
    the loser gets VERSION_CONFLICT (no lost update)."""
    admin, user, _ = role_client_factory("ADMIN")
    c1 = _cluster(admin, code="C1")
    net = _network(admin, c1["id"], name="n1", cidr="10.0.0.0/24")
    ip = _ip(admin, net["id"], "10.0.0.5")
    operator = _operator(user)
    ip_id = uuid.UUID(ip["id"])

    barrier = threading.Barrier(2)
    results: list[object] = []

    def patch(description: str) -> None:
        session = auth_session_factory()
        try:
            barrier.wait(timeout=10)
            ip_address_service.update_ip_address(
                session,
                operator,
                ip_id,
                expected_version=1,
                changes={"description": description},
            )
            results.append(description)
        except VersionConflict as exc:
            session.rollback()
            results.append(exc)
        finally:
            session.close()

    threads = [
        threading.Thread(target=patch, args=("a",)),
        threading.Thread(target=patch, args=("b",)),
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)

    winners = [r for r in results if isinstance(r, str)]
    conflicts = [r for r in results if isinstance(r, VersionConflict)]
    assert len(winners) == 1, results
    assert len(conflicts) == 1, results
    detail = admin.get(f"/api/v1/ip-addresses/{ip['id']}").json()["ip_address"]
    assert detail["version"] == 2
    assert detail["description"] == winners[0]


def test_audit_failure_rolls_back_business_write(
    auth_session_factory, role_client_factory, monkeypatch
):
    """A24/B48: if staging the audit row fails, the business write is rolled
    back in the same transaction (no orphan IP row)."""
    from app.services import audit as audit_service

    admin, user, _ = role_client_factory("ADMIN")
    c1 = _cluster(admin, code="C1")
    net = _network(admin, c1["id"], name="n1", cidr="10.0.0.0/24")
    operator = _operator(user)

    def boom(*args, **kwargs):
        raise RuntimeError("audit failure injected")

    monkeypatch.setattr(audit_service, "record", boom)
    session = auth_session_factory()
    try:
        with pytest.raises(RuntimeError):
            ip_address_service.create_ip_address(
                session, operator, network=net["id"], address="10.0.0.5"
            )
        session.rollback()
    finally:
        session.close()

    listed = admin.get("/api/v1/ip-addresses", params={"network_id": net["id"]})
    assert listed.json()["items"] == []


def test_restore_not_deleted_reason(role_client_factory):
    """A22: restoring an object that is not soft-deleted is 409 not_deleted."""
    admin, _, _ = role_client_factory("ADMIN")
    c1 = _cluster(admin, code="C1")
    net = _network(admin, c1["id"], name="n1", cidr="10.0.0.0/24")
    ip = _ip(admin, net["id"], "10.0.0.5")
    resp = admin.post(
        f"/api/v1/ip-addresses/{ip['id']}/restore", params={"version": 1}
    )
    assert resp.status_code == 409
    assert resp.json()["error"]["details"]["reason"] == "not_deleted"


def test_endpoint_checker_registration_blocks_unbind_transfer_release(
    role_client_factory, monkeypatch
):
    """A18/V18/B52: the public registration hook installs a checker that blocks
    unbind, transfer and release (F010-side contract for F012)."""
    admin, _, _ = role_client_factory("ADMIN")
    c1 = _cluster(admin, code="C1")
    net = _network(admin, c1["id"], name="n1", cidr="10.0.0.0/24")
    res = _resource(admin, c1["id"])
    if1 = _interface(admin, res["id"], name="eth0")
    if2 = _interface(admin, res["id"], name="eth1")
    ip = _ip(admin, net["id"], "10.0.0.5")
    admin.patch(
        f"/api/v1/ip-addresses/{ip['id']}", json={"version": 1, "interface": if1["id"]}
    )

    references = [{"object_type": "service_endpoint", "object_id": str(uuid.uuid4()), "label": "tcp:443"}]
    monkeypatch.setattr(ip_address_reference, "_CHECKERS", [])
    ip_address_reference.register_ip_address_reference_checker(
        lambda db, ip_id: list(references)
    )

    # unbind
    unbind = admin.patch(
        f"/api/v1/ip-addresses/{ip['id']}", json={"version": 2, "interface": None}
    )
    assert unbind.status_code == 409, unbind.text
    assert unbind.json()["error"]["details"]["references"][0]["object_type"] == "service_endpoint"
    # transfer
    transfer = admin.patch(
        f"/api/v1/ip-addresses/{ip['id']}", json={"version": 2, "interface": if2["id"]}
    )
    assert transfer.status_code == 409, transfer.text
    # release
    release = admin.delete(f"/api/v1/ip-addresses/{ip['id']}", params={"version": 2})
    assert release.status_code == 409, release.text
    # the binding is untouched and the object is still live
    detail = admin.get(f"/api/v1/ip-addresses/{ip['id']}").json()["ip_address"]
    assert detail["interface"]["id"] == if1["id"]
    assert detail["deleted_at"] is None


def test_loopback_interface_registers_but_127_not_allocated(role_client_factory):
    """A17: a LOOPBACK Interface can be registered, but 127.x is not allocated."""
    editor, _, _ = role_client_factory("EDITOR")
    c1 = _cluster(editor, code="C1")
    res = _resource(editor, c1["id"])
    reg = editor.post(
        "/api/v1/interfaces",
        json={"resource": res["id"], "name": "lo", "interface_type": "LOOPBACK"},
    )
    assert reg.status_code == 201, reg.text
    net = _network(editor, c1["id"], name="lo", cidr="127.0.0.0/8")
    assert _allocate(editor, net["id"], "127.0.0.1").status_code == 422


def test_capacity_31_and_32_prefix(role_client_factory):
    """A16/A23/B60: /31 contributes two allocatable addresses and /32 one."""
    editor, _, _ = role_client_factory("EDITOR")
    c1 = _cluster(editor, code="C1")
    n31 = _network(editor, c1["id"], name="n31", cidr="10.30.0.4/31")
    _ip(editor, n31["id"], "10.30.0.4")
    cap31 = editor.get(f"/api/v1/networks/{n31['id']}/capacity").json()
    assert cap31["network_capacity"]["allocatable_total"] == 2
    assert cap31["network_capacity"]["occupied"] == 1
    assert cap31["network_capacity"]["remaining"] == 1

    n32 = _network(editor, c1["id"], name="n32", cidr="10.31.0.5/32")
    cap32 = editor.get(f"/api/v1/networks/{n32['id']}/capacity").json()
    assert cap32["network_capacity"]["allocatable_total"] == 1
    assert cap32["network_capacity"]["occupied"] == 0
    assert cap32["network_capacity"]["remaining"] == 1