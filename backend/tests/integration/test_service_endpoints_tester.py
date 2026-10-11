"""Independent F012 TE-1 verification tests (Tester-authored).

Written and executed by the Tester, independently of the implementation
report's numbers. They deliberately target acceptance points that the
implementation suite covers only indirectly or at a different layer:

- A16/B28 audit same-transaction rollback for CREATE/UPDATE/DELETE/RESTORE
  (service layer, real committed sessions);
- A17/B31 optimistic lock across two real committed sessions (service layer);
- A14/B41 restore vs concurrent recreate (real partial-unique arbitration);
- A14/B22 restore priority: listener uniqueness precedes dependency checks;
- A17/B32 stale version on an invisible (soft-deleted) object resolves to 404;
- A5 cross-**Cluster** attribution (the implementation suite only proves
  cross-Resource within one Cluster);
- A18/B29 list parameter rejection and out-of-range pagination;
- V22 response contract shape (nested references, no raw FK columns);
- A12/B14 the IP-side provider returns *all* undeleted endpoints with the
  canonical ``object_type`` and ``protocol/port`` labels.

Real PostgreSQL only (``TEST_DATABASE_URL`` / DB-D10 guard in conftest); no
SQLite and no mocks for constraint/concurrency evidence.
"""

from __future__ import annotations

import threading
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.core.auth import Operator
from app.core.errors import VersionConflict
from app.core.permissions import Role
from app.services import service_endpoint as se_service

# --- seeding helpers (mirror the implementation suite; Tester-owned copy) -----


def _maker(app, make_user, role: str):
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
        client, user, password = _maker(auth_app, make_user, role)
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


def _network(client, cluster, name="net", cidr="10.0.0.0/24"):
    resp = client.post(
        "/api/v1/networks", json={"cluster": cluster, "name": name, "cidr": cidr}
    )
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
    resp = client.post("/api/v1/interfaces", json={"resource": resource, "name": name})
    assert resp.status_code == 201, resp.text
    return resp.json()["interface"]


def _ip(client, network, address):
    resp = client.post(
        "/api/v1/ip-addresses", json={"network": network, "address": address}
    )
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
    resp = client.post("/api/v1/services", json={"resource": resource, "name": name})
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


def _bound_service_ip(client, cluster, *, address="10.0.0.5", resource_name="host1"):
    res = _resource(client, cluster, hostname=resource_name)
    iface = _interface(client, res["id"])
    net = _network(client, cluster, name=f"net-{resource_name}")
    ip = _bind(client, _ip(client, net["id"], address), iface)
    service = _service(client, res["id"], name=f"svc-{resource_name}")
    return service, ip, res, iface, net


# --- A16/B28: audit same-transaction rollback --------------------------------


def test_audit_failure_rolls_back_endpoint_writes(
    role_client_factory, auth_session_factory, monkeypatch
):
    """A rejected audit write rolls back the endpoint write for all four actions."""
    from app.services import audit as audit_service

    admin, admin_user, _ = role_client_factory("ADMIN")
    c1 = _cluster(admin)
    service, ip, *_ = _bound_service_ip(admin, c1["id"])
    op = _operator(admin_user)

    def boom(*args, **kwargs):
        raise RuntimeError("audit failure injected")

    # CREATE: no row survives.
    monkeypatch.setattr(audit_service, "record", boom)
    with auth_session_factory() as session:
        with pytest.raises(RuntimeError):
            se_service.create_service_endpoint(
                session,
                op,
                service=service["id"],
                ip_address=ip["id"],
                protocol="TCP",
                port=22,
            )
        session.rollback()
    with auth_session_factory() as session:
        assert session.execute(
            text(
                "SELECT count(*) FROM service_endpoints "
                "WHERE ip_address_id = :ipid AND protocol = 'TCP' AND port = 22"
            ),
            {"ipid": ip["id"]},
        ).scalar_one() == 0

    # Seed one live endpoint (audit intact).
    monkeypatch.undo()
    live = _endpoint(admin, service, ip, "TCP", 22)

    # UPDATE: value/version unchanged.
    monkeypatch.setattr(audit_service, "record", boom)
    with auth_session_factory() as session:
        with pytest.raises(RuntimeError):
            se_service.update_service_endpoint(
                session, op, uuid.UUID(live["id"]), expected_version=1,
                changes={"port": 2222},
            )
        session.rollback()
    with auth_session_factory() as session:
        row = session.execute(
            text("SELECT port, version FROM service_endpoints WHERE id = :id"),
            {"id": live["id"]},
        ).mappings().one()
        assert row["port"] == 22 and row["version"] == 1

    # DELETE: stays undeleted.
    with auth_session_factory() as session:
        with pytest.raises(RuntimeError):
            se_service.delete_service_endpoint(
                session, op, uuid.UUID(live["id"]), expected_version=1
            )
        session.rollback()
    with auth_session_factory() as session:
        assert session.execute(
            text("SELECT deleted_at FROM service_endpoints WHERE id = :id"),
            {"id": live["id"]},
        ).scalar_one() is None

    # RESTORE: stays soft-deleted.
    monkeypatch.undo()
    admin.delete(f"/api/v1/service-endpoints/{live['id']}", params={"version": 1})
    monkeypatch.setattr(audit_service, "record", boom)
    with auth_session_factory() as session:
        with pytest.raises(RuntimeError):
            se_service.restore_service_endpoint(
                session, op, uuid.UUID(live["id"]), expected_version=2
            )
        session.rollback()
    with auth_session_factory() as session:
        assert session.execute(
            text("SELECT deleted_at FROM service_endpoints WHERE id = :id"),
            {"id": live["id"]},
        ).scalar_one() is not None


# --- A17/B31: optimistic lock across two committed sessions ------------------


def test_optimistic_lock_two_sessions(role_client_factory, auth_session_factory):
    admin, admin_user, _ = role_client_factory("ADMIN")
    c1 = _cluster(admin)
    service, ip, *_ = _bound_service_ip(admin, c1["id"])
    created = _endpoint(admin, service, ip, "TCP", 22)
    op = _operator(admin_user)

    first = auth_session_factory()
    second = auth_session_factory()
    try:
        se_service.update_service_endpoint(
            first, op, uuid.UUID(created["id"]), expected_version=1,
            changes={"port": 2222},
        )
        with pytest.raises(VersionConflict) as exc:
            se_service.update_service_endpoint(
                second, op, uuid.UUID(created["id"]), expected_version=1,
                changes={"port": 3333},
            )
        assert exc.value.details == {"current_version": 2}
        second.rollback()
    finally:
        first.close()
        second.close()

    with auth_session_factory() as verify:
        row = verify.execute(
            text("SELECT port, version FROM service_endpoints WHERE id = :id"),
            {"id": created["id"]},
        ).mappings().one()
        assert row["port"] == 2222 and row["version"] == 2


# --- A14/B41: restore vs concurrent recreate ---------------------------------


def test_restore_vs_recreate_concurrency(
    role_client_factory, auth_session_factory, committed_engine
):
    admin, admin_user, _ = role_client_factory("ADMIN")
    c1 = _cluster(admin)
    service, ip, *_ = _bound_service_ip(admin, c1["id"])
    created = _endpoint(admin, service, ip, "TCP", 22)
    admin.delete(f"/api/v1/service-endpoints/{created['id']}", params={"version": 1})
    op = _operator(admin_user)

    barrier = threading.Barrier(2)
    outcomes: list[str] = []
    lock = threading.Lock()

    def restorer() -> None:
        session = auth_session_factory()
        try:
            barrier.wait(timeout=10)
            se_service.restore_service_endpoint(
                session, op, uuid.UUID(created["id"]), expected_version=2
            )
            with lock:
                outcomes.append("restore-ok")
        except Exception:
            session.rollback()
            with lock:
                outcomes.append("restore-error")
        finally:
            session.close()

    def recreator() -> None:
        session = auth_session_factory()
        try:
            barrier.wait(timeout=10)
            se_service.create_service_endpoint(
                session, op, service=service["id"], ip_address=ip["id"],
                protocol="TCP", port=22,
            )
            with lock:
                outcomes.append("create-ok")
        except Exception:
            session.rollback()
            with lock:
                outcomes.append("create-error")
        finally:
            session.close()

    threads = [threading.Thread(target=restorer), threading.Thread(target=recreator)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=20)

    with committed_engine.connect() as conn:
        undeleted = conn.execute(
            text(
                "SELECT count(*) FROM service_endpoints WHERE ip_address_id = :ipid "
                "AND protocol = 'TCP' AND port = 22 AND deleted_at IS NULL"
            ),
            {"ipid": ip["id"]},
        ).scalar_one()
    assert undeleted == 1, outcomes
    assert sorted(o.split("-")[1] for o in outcomes) == ["error", "ok"], outcomes


# --- A14/B22: restore priority (uniqueness before dependency) ----------------


def test_restore_priority_uniqueness_before_dependency(role_client_factory):
    admin, _, _ = role_client_factory("ADMIN")
    c1 = _cluster(admin)
    service, ip, *_ = _bound_service_ip(admin, c1["id"])
    old = _endpoint(admin, service, ip, "TCP", 22)
    admin.delete(f"/api/v1/service-endpoints/{old['id']}", params={"version": 1})
    # occupy the listener and soft-delete the owning Service
    _endpoint(admin, service, ip, "TCP", 22)
    admin.delete(f"/api/v1/services/{service['id']}", params={"version": 1})

    resp = admin.post(
        f"/api/v1/service-endpoints/{old['id']}/restore", params={"version": 2}
    )
    assert resp.status_code == 409, resp.text
    assert resp.json()["error"]["details"]["reason"] == "unique_conflict"


# --- A17/B32: stale version on an invisible object ---------------------------


def test_stale_version_on_soft_deleted_is_404(role_client_factory):
    admin, _, _ = role_client_factory("ADMIN")
    c1 = _cluster(admin)
    service, ip, *_ = _bound_service_ip(admin, c1["id"])
    endpoint = _endpoint(admin, service, ip, "TCP", 22)
    admin.delete(f"/api/v1/service-endpoints/{endpoint['id']}", params={"version": 1})

    # Default view hides the soft-deleted row: PATCH resolves to 404, not 409.
    resp = admin.patch(
        f"/api/v1/service-endpoints/{endpoint['id']}",
        json={"version": 1, "port": 80},
    )
    assert resp.status_code == 404, resp.text


# --- A5: cross-Cluster attribution -------------------------------------------


def test_attribution_cross_cluster_rejected(role_client_factory):
    admin, _, _ = role_client_factory("ADMIN")
    c1 = _cluster(admin, code="C1", name="one")
    c2 = _cluster(admin, code="C2", name="two")
    res1 = _resource(admin, c1["id"], hostname="r1")
    service = _service(admin, res1["id"], name="svc")

    # IP lives in Cluster 2, bound to a Cluster 2 Resource's interface.
    res2 = _resource(admin, c2["id"], hostname="r2")
    iface2 = _interface(admin, res2["id"], name="eth0")
    net2 = _network(admin, c2["id"], name="n2", cidr="10.1.0.0/24")
    cross = _bind(admin, _ip(admin, net2["id"], "10.1.0.5"), iface2)

    resp = _endpoint_post(admin, service, cross)
    assert resp.status_code == 422, resp.text
    assert resp.json()["error"]["details"]["fields"][0]["field"] == "ip_address"


# --- A18/B29: list parameter rejection ---------------------------------------


def test_list_parameter_validation(role_client_factory):
    admin, _, _ = role_client_factory("ADMIN")
    for params in (
        {"page": 0},
        {"page_size": 0},
        {"page_size": 101},
        {"protocol": "tcp"},
        {"service_id": "not-a-uuid"},
        {"ip_address_id": "not-a-uuid"},
        {"sort": "bogus"},
        {"order": "sideways"},
        {"deleted": "bogus"},
    ):
        resp = admin.get("/api/v1/service-endpoints", params=params)
        assert resp.status_code == 422, (params, resp.text)


# --- A21/V22: response contract shape ----------------------------------------


def test_response_contract_shape(role_client_factory):
    admin, _, _ = role_client_factory("ADMIN")
    c1 = _cluster(admin)
    service, ip, res, iface, net = _bound_service_ip(admin, c1["id"])
    endpoint = _endpoint(admin, service, ip, "TCP", 443, description="web")

    assert set(endpoint) == {
        "id", "service", "ip_address", "protocol", "port", "description",
        "version", "created_at", "updated_at", "deleted_at",
    }
    assert set(endpoint["service"]) == {"id", "name", "resource"}
    assert set(endpoint["service"]["resource"]) == {"id", "hostname"}
    assert set(endpoint["ip_address"]) == {"id", "address", "network", "interface"}
    assert set(endpoint["ip_address"]["network"]) == {"id", "name"}
    assert set(endpoint["ip_address"]["interface"]) == {"id", "name"}
    assert "service_id" not in endpoint and "ip_address_id" not in endpoint
    assert "metadata" not in endpoint
    assert endpoint["ip_address"]["interface"]["id"] == iface["id"]
    assert endpoint["ip_address"]["network"]["id"] == net["id"]
    assert endpoint["service"]["resource"]["id"] == res["id"]


# --- A12/B14: IP-side provider returns all undeleted endpoints ---------------


def test_ip_reference_list_all_undeleted_with_labels(role_client_factory):
    admin, _, _ = role_client_factory("ADMIN")
    c1 = _cluster(admin)
    service, ip, *_ = _bound_service_ip(admin, c1["id"])
    _endpoint(admin, service, ip, "TCP", 22)
    _endpoint(admin, service, ip, "UDP", 53)
    gone = _endpoint(admin, service, ip, "TCP", 8080)
    admin.delete(f"/api/v1/service-endpoints/{gone['id']}", params={"version": 1})

    resp = admin.patch(
        f"/api/v1/ip-addresses/{ip['id']}",
        json={"version": ip["version"], "interface": None},
    )
    assert resp.status_code == 409, resp.text
    refs = resp.json()["error"]["details"]["references"]
    labels = sorted(ref["label"] for ref in refs)
    assert labels == ["TCP/22", "UDP/53"]
    assert {ref["object_type"] for ref in refs} == {"service_endpoint"}


# --- V24/B45: reads have no business write side effects ----------------------


def test_read_only_has_no_side_effects(role_client_factory, committed_engine):
    admin, _, _ = role_client_factory("ADMIN")
    c1 = _cluster(admin)
    service, ip, *_ = _bound_service_ip(admin, c1["id"])
    endpoint = _endpoint(admin, service, ip, "TCP", 22)

    def snapshot():
        with committed_engine.connect() as conn:
            audit = conn.execute(
                text(
                    "SELECT count(*) FROM audit_logs "
                    "WHERE object_type = 'service_endpoint'"
                )
            ).scalar_one()
            row = conn.execute(
                text(
                    "SELECT version, updated_at FROM service_endpoints WHERE id = :id"
                ),
                {"id": endpoint["id"]},
            ).one()
        return audit, tuple(row)

    before = snapshot()
    for _ in range(3):
        assert admin.get("/api/v1/service-endpoints").status_code == 200
        assert admin.get(
            f"/api/v1/service-endpoints/{endpoint['id']}"
        ).status_code == 200
        assert admin.get(
            f"/api/v1/service-endpoints/{endpoint['id']}/activity"
        ).status_code == 200
    assert snapshot() == before