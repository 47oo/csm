"""F006 VirtualMachine API integration tests (A1-A17, V1-V20, B1-B36).

Requires a real PostgreSQL database via ``TEST_DATABASE_URL`` (DB-D10 guard in
``conftest``). Raw-SQL database assertions live in
``test_virtual_machine_constraints.py``; migration/backfill evidence too.
"""

from __future__ import annotations

import threading
import time
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text

from app.core.auth import Operator
from app.core.errors import VersionConflict
from app.core.permissions import Role
from app.models.audit_log import AuditLog
from app.models.resource import Resource
from app.services import cluster as cluster_service
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


def _create(client, cluster, hostname="cn001", resource_type="BARE_METAL", **overrides):
    body = {"cluster": cluster, "hostname": hostname, "resource_type": resource_type}
    body.update(overrides)
    return client.post("/api/v1/resources", json=body)


def _resource(client, cluster, hostname="cn001", **overrides):
    resp = _create(client, cluster, hostname=hostname, **overrides)
    assert resp.status_code == 201, resp.text
    return resp.json()["resource"]


def _bare_metal(client, cluster, hostname="host01", **overrides):
    return _resource(client, cluster, hostname=hostname, resource_type="BARE_METAL", **overrides)


def _vm(client, cluster, host_id, hostname="vm01", **overrides):
    vm = overrides.pop("virtual_machine", {})
    vm.setdefault("host_resource_id", host_id)
    return _resource(
        client,
        cluster,
        hostname=hostname,
        resource_type="VIRTUAL_MACHINE",
        virtual_machine=vm,
        **overrides,
    )


def _operator(user) -> Operator:
    return Operator(user_id=user.id, username=user.username, role=Role(user.role))


def _vm_row(session, resource_id):
    return session.execute(
        text(
            "SELECT resource_id, host_resource_id, vcpu, memory_mb, disk_gb, "
            "hypervisor FROM virtual_machine_details WHERE resource_id = :id"
        ),
        {"id": uuid.UUID(str(resource_id))},
    ).mappings().first()


# --- A1-A4/B1-B4: host validation --------------------------------------------


def test_host_must_be_undeleted_bare_metal_in_same_cluster(role_client_factory):
    client, _, _ = role_client_factory("EDITOR")
    c1 = _cluster(client, code="C1")
    c2 = _cluster(client, code="C2")
    bare_c1 = _bare_metal(client, c1["code"], hostname="host-c1")
    bare_c2 = _bare_metal(client, c2["code"], hostname="host-c2")
    other_vm = _vm(client, c1["code"], bare_c1["id"], hostname="vm-other")

    cases = [
        ("vm-host", other_vm["id"]),              # A1 host is a VM
        ("cross", bare_c2["id"]),                  # A2 cross-cluster host
        ("missing", str(uuid.uuid4())),            # A4 missing host
    ]
    for hostname, host_id in cases:
        resp = _create(
            client,
            c1["code"],
            hostname=hostname,
            resource_type="VIRTUAL_MACHINE",
            virtual_machine={"host_resource_id": host_id},
        )
        assert resp.status_code == 422, (hostname, resp.text)
        fields = resp.json()["error"]["details"]["fields"]
        assert fields[0]["field"] == "virtual_machine.host_resource_id"

    # A4 soft-deleted host
    admin, _, _ = role_client_factory("ADMIN")
    bare_soft = _bare_metal(client, c1["code"], hostname="host-soft")
    assert admin.delete(f"/api/v1/resources/{bare_soft['id']}", params={"version": 1}).status_code == 204
    resp = _create(
        client,
        c1["code"],
        hostname="soft",
        resource_type="VIRTUAL_MACHINE",
        virtual_machine={"host_resource_id": bare_soft["id"]},
    )
    assert resp.status_code == 422


def test_host_required_and_shapes(role_client_factory):
    client, _, _ = role_client_factory("EDITOR")
    c1 = _cluster(client, code="C1")
    bare = _bare_metal(client, c1["code"])

    # A3: missing virtual_machine / missing host / explicit null / empty string
    assert _create(client, c1["code"], hostname="a", resource_type="VIRTUAL_MACHINE").status_code == 422
    assert (
        _create(
            client,
            c1["code"],
            hostname="b",
            resource_type="VIRTUAL_MACHINE",
            virtual_machine={},
        ).status_code
        == 422
    )
    assert (
        _create(
            client,
            c1["code"],
            hostname="c",
            resource_type="VIRTUAL_MACHINE",
            virtual_machine={"host_resource_id": None},
        ).status_code
        == 422
    )
    assert (
        _create(
            client,
            c1["code"],
            hostname="d",
            resource_type="VIRTUAL_MACHINE",
            virtual_machine={"host_resource_id": ""},
        ).status_code
        == 422
    )
    # false / non-object whole object
    for bad in ([], "x", 5, {"unknown_key": 1}, {"metadata": {}}, {"host_resource_id": bare["id"], "metadata": {}}):
        assert (
            _create(
                client,
                c1["code"],
                hostname=f"bad-{len(str(bad))}",
                resource_type="VIRTUAL_MACHINE",
                virtual_machine=bad,
            ).status_code
            == 422
        ), bad


# --- A5/B7: legal create, host expansion -------------------------------------


def test_create_virtual_machine_and_host_expansion(role_client_factory, auth_session_factory):
    client, _, _ = role_client_factory("EDITOR")
    c1 = _cluster(client, code="C1")
    bare = _bare_metal(client, c1["code"], hostname="HOST-A", hardware={"cpu_cores": 64})
    vm = _vm(
        client,
        c1["code"],
        bare["id"],
        hostname="VM-A",
        virtual_machine={"vcpu": 4, "memory_mb": 8192, "disk_gb": 100, "hypervisor": " Proxmox "},
    )
    assert vm["hostname"] == "vm-a"  # hostname normalised lower
    vmo = vm["virtual_machine"]
    assert vmo["host_resource_id"] == bare["id"]
    assert vmo["host"] == {"id": bare["id"], "hostname": "host-a"}
    assert vmo["vcpu"] == 4 and vmo["memory_mb"] == 8192
    assert vmo["disk_gb"] == 100 and vmo["hypervisor"] == "Proxmox"
    assert "metadata" not in vmo
    assert vm["hardware"] is None

    with auth_session_factory() as session:
        row = _vm_row(session, vm["id"])
        assert row["host_resource_id"] == uuid.UUID(bare["id"])
        assert row["vcpu"] == 4 and row["memory_mb"] == 8192
        assert row["disk_gb"] == 100 and row["hypervisor"] == "Proxmox"


# --- A8/A11/B18/B19: capacity null vs 0 vs value -----------------------------


def test_capacity_omitted_null_and_zero(role_client_factory, auth_session_factory):
    client, _, _ = role_client_factory("EDITOR")
    c1 = _cluster(client, code="C1")
    bare = _bare_metal(client, c1["code"])

    omitted = _vm(client, c1["code"], bare["id"], hostname="omitted")
    assert omitted["virtual_machine"]["vcpu"] is None
    assert omitted["virtual_machine"]["memory_mb"] is None
    assert omitted["virtual_machine"]["disk_gb"] is None

    explicit = _vm(
        client,
        c1["code"],
        bare["id"],
        hostname="explicit",
        virtual_machine={"host_resource_id": bare["id"], "vcpu": None, "memory_mb": None, "disk_gb": None, "hypervisor": None},
    )
    assert explicit["virtual_machine"]["vcpu"] is None
    assert explicit["virtual_machine"]["disk_gb"] is None

    zero = _vm(
        client,
        c1["code"],
        bare["id"],
        hostname="zerodisk",
        virtual_machine={"host_resource_id": bare["id"], "vcpu": 1, "disk_gb": 0},
    )
    assert zero["virtual_machine"]["disk_gb"] == 0
    assert zero["virtual_machine"]["vcpu"] == 1

    with auth_session_factory() as session:
        for created, expect_zero in ((omitted, False), (explicit, False), (zero, True)):
            row = _vm_row(session, created["id"])
            assert (row["disk_gb"] == 0) is expect_zero
            if not expect_zero:
                assert row["vcpu"] is None and row["memory_mb"] is None


def test_capacity_ranges_and_strict_types(role_client_factory):
    client, _, _ = role_client_factory("EDITOR")
    c1 = _cluster(client, code="C1")
    bare = _bare_metal(client, c1["code"])

    for field in ("vcpu", "memory_mb"):
        for bad in (0, -1, 2147483648):
            resp = _create(
                client,
                c1["code"],
                hostname=f"bad-{field}-{bad}",
                resource_type="VIRTUAL_MACHINE",
                virtual_machine={"host_resource_id": bare["id"], field: bad},
            )
            assert resp.status_code == 422, (field, bad, resp.text)
    assert (
        _create(
            client,
            c1["code"],
            hostname="disk-neg",
            resource_type="VIRTUAL_MACHINE",
            virtual_machine={"host_resource_id": bare["id"], "disk_gb": -1},
        ).status_code
        == 422
    )
    # strict: string / bool / float rejected
    for bad in ("4", True, 1.5):
        assert (
            _create(
                client,
                c1["code"],
                hostname=f"strict-{type(bad).__name__}",
                resource_type="VIRTUAL_MACHINE",
                virtual_machine={"host_resource_id": bare["id"], "vcpu": bad},
            ).status_code
            == 422
        ), bad

    edge = _vm(
        client,
        c1["code"],
        bare["id"],
        hostname="edge",
        virtual_machine={"host_resource_id": bare["id"], "vcpu": 2147483647, "memory_mb": 1, "disk_gb": 2147483647},
    )
    assert edge["virtual_machine"]["vcpu"] == 2147483647
    assert edge["virtual_machine"]["disk_gb"] == 2147483647


# --- A9/A10/B20: units stored verbatim ---------------------------------------


def test_memory_and_disk_units_verbatim(role_client_factory, auth_session_factory):
    client, _, _ = role_client_factory("EDITOR")
    c1 = _cluster(client, code="C1")
    bare = _bare_metal(client, c1["code"])
    vm = _vm(
        client,
        c1["code"],
        bare["id"],
        hostname="units",
        virtual_machine={"host_resource_id": bare["id"], "memory_mb": 1572864, "disk_gb": 1536},
    )
    assert vm["virtual_machine"]["memory_mb"] == 1572864
    assert vm["virtual_machine"]["disk_gb"] == 1536
    with auth_session_factory() as session:
        row = _vm_row(session, vm["id"])
        assert row["memory_mb"] == 1572864 and row["disk_gb"] == 1536


# --- A11/A12/B21: no over-capacity admission ---------------------------------


def test_no_over_capacity_check(role_client_factory):
    client, _, _ = role_client_factory("EDITOR")
    c1 = _cluster(client, code="C1")
    bare = _bare_metal(client, c1["code"], hardware={"cpu_cores": 16, "memory_mb": 32768})
    vm = _vm(
        client,
        c1["code"],
        bare["id"],
        hostname="huge",
        virtual_machine={"host_resource_id": bare["id"], "vcpu": 64, "memory_mb": 262144},
    )
    assert vm["virtual_machine"]["vcpu"] == 64
    patched = client.patch(
        f"/api/v1/resources/{vm['id']}",
        json={"version": 1, "virtual_machine": {"vcpu": 128}},
    )
    assert patched.status_code == 200


# --- V17/B30: mutual exclusion ------------------------------------------------


def test_hardware_and_virtual_machine_are_mutually_exclusive(role_client_factory, auth_session_factory):
    client, _, _ = role_client_factory("EDITOR")
    c1 = _cluster(client, code="C1")
    bare = _bare_metal(client, c1["code"])

    # BARE_METAL carrying virtual_machine (including explicit null) -> 422
    for value in ({}, {"host_resource_id": bare["id"]}, None):
        assert (
            _create(
                client,
                c1["code"],
                hostname=f"bare-{len(str(value))}",
                resource_type="BARE_METAL",
                virtual_machine=value,
            ).status_code
            == 422
        ), value
    # VIRTUAL_MACHINE carrying hardware (including explicit null via non-optional) -> 422
    for value in ({}, {"cpu_cores": 8}):
        assert (
            _create(
                client,
                c1["code"],
                hostname=f"vm-hw-{len(str(value))}",
                resource_type="VIRTUAL_MACHINE",
                virtual_machine={"host_resource_id": bare["id"]},
                hardware=value,
            ).status_code
            == 422
        ), value

    vm = _vm(client, c1["code"], bare["id"], hostname="mutex")
    assert (
        client.patch(
            f"/api/v1/resources/{vm['id']}",
            json={"version": 1, "hardware": {"cpu_cores": 8}},
        ).status_code
        == 422
    )
    assert (
        client.patch(
            f"/api/v1/resources/{bare['id']}",
            json={"version": 1, "virtual_machine": {"vcpu": 1}},
        ).status_code
        == 422
    )


# --- V18/B32: PATCH exclude_unset ---------------------------------------------


def test_patch_subfield_semantics(role_client_factory, auth_session_factory):
    client, _, _ = role_client_factory("EDITOR")
    c1 = _cluster(client, code="C1")
    bare = _bare_metal(client, c1["code"])
    vm = _vm(
        client,
        c1["code"],
        bare["id"],
        hostname="patch",
        virtual_machine={"host_resource_id": bare["id"], "vcpu": 4, "memory_mb": 8192, "disk_gb": 50, "hypervisor": "KVM"},
    )

    # omitted sub-fields keep their value
    updated = client.patch(
        f"/api/v1/resources/{vm['id']}",
        json={"version": 1, "virtual_machine": {"vcpu": 8}},
    )
    assert updated.status_code == 200, updated.text
    vmo = updated.json()["resource"]["virtual_machine"]
    assert vmo["vcpu"] == 8
    assert vmo["memory_mb"] == 8192 and vmo["disk_gb"] == 50 and vmo["hypervisor"] == "KVM"

    # explicit null clears a nullable sub-field
    cleared = client.patch(
        f"/api/v1/resources/{vm['id']}",
        json={"version": 2, "virtual_machine": {"hypervisor": None, "disk_gb": None}},
    ).json()["resource"]["virtual_machine"]
    assert cleared["hypervisor"] is None and cleared["disk_gb"] is None
    assert cleared["vcpu"] == 8 and cleared["memory_mb"] == 8192

    # host explicit null -> 422, whole object null/non-object/unknown keys -> 422
    assert (
        client.patch(
            f"/api/v1/resources/{vm['id']}",
            json={"version": 3, "virtual_machine": {"host_resource_id": None}},
        ).status_code
        == 422
    )
    assert (
        client.patch(
            f"/api/v1/resources/{vm['id']}",
            json={"version": 3, "virtual_machine": None},
        ).status_code
        == 422
    )
    assert (
        client.patch(
            f"/api/v1/resources/{vm['id']}",
            json={"version": 3, "virtual_machine": {"unknown": 1}},
        ).status_code
        == 422
    )
    with auth_session_factory() as session:
        row = _vm_row(session, vm["id"])
        assert row["vcpu"] == 8 and row["memory_mb"] == 8192
        assert row["hypervisor"] is None and row["disk_gb"] is None


# --- A6/B9-B11: rehost + audit + version -------------------------------------


def test_rehost_writes_audit_and_validates(role_client_factory, auth_session_factory):
    client, _, _ = role_client_factory("ADMIN")
    c1 = _cluster(client, code="C1")
    c2 = _cluster(client, code="C2")
    host_a = _bare_metal(client, c1["code"], hostname="host-a")
    host_b = _bare_metal(client, c1["code"], hostname="host-b")
    foreign = _bare_metal(client, c2["code"], hostname="host-c2")
    vm = _vm(client, c1["code"], host_a["id"], hostname="rehost")

    # cross-cluster rehost -> 422, unchanged
    assert (
        client.patch(
            f"/api/v1/resources/{vm['id']}",
            json={"version": 1, "virtual_machine": {"host_resource_id": foreign["id"]}},
        ).status_code
        == 422
    )
    # missing host -> 422
    assert (
        client.patch(
            f"/api/v1/resources/{vm['id']}",
            json={"version": 1, "virtual_machine": {"host_resource_id": str(uuid.uuid4())}},
        ).status_code
        == 422
    )
    with auth_session_factory() as session:
        assert _vm_row(session, vm["id"])["host_resource_id"] == uuid.UUID(host_a["id"])

    # same-cluster rehost -> 200, audit before/after host_resource_id
    resp = client.patch(
        f"/api/v1/resources/{vm['id']}",
        json={"version": 1, "virtual_machine": {"host_resource_id": host_b["id"]}},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["resource"]["virtual_machine"]["host"]["id"] == host_b["id"]

    with auth_session_factory() as session:
        assert _vm_row(session, vm["id"])["host_resource_id"] == uuid.UUID(host_b["id"])
        rows = (
            session.execute(
                select(AuditLog)
                .where(AuditLog.object_id == uuid.UUID(vm["id"]))
                .order_by(AuditLog.created_at)
            )
            .scalars()
            .all()
        )
        assert [r.action for r in rows] == ["CREATE", "UPDATE"]
        update = rows[1]
        assert update.before_data["virtual_machine"]["host_resource_id"] == host_a["id"]
        assert update.after_data["virtual_machine"]["host_resource_id"] == host_b["id"]
        assert update.before_data["hardware"] is None
        assert rows[0].after_data["virtual_machine"]["host_resource_id"] == host_a["id"]


def test_rehost_soft_deleted_host_rejected(role_client_factory):
    admin, _, _ = role_client_factory("ADMIN")
    c1 = _cluster(admin, code="C1")
    host_a = _bare_metal(admin, c1["code"], hostname="host-a")
    host_b = _bare_metal(admin, c1["code"], hostname="host-b")
    vm = _vm(admin, c1["code"], host_a["id"], hostname="rehost-soft")
    assert admin.delete(f"/api/v1/resources/{host_b['id']}", params={"version": 1}).status_code == 204
    assert (
        admin.patch(
            f"/api/v1/resources/{vm['id']}",
            json={"version": 1, "virtual_machine": {"host_resource_id": host_b["id"]}},
        ).status_code
        == 422
    )


# --- A7/B12-B13: host reference delete protection ----------------------------


def test_host_delete_protection(role_client_factory, auth_session_factory):
    admin, _, _ = role_client_factory("ADMIN")
    c1 = _cluster(admin, code="C1")
    host = _bare_metal(admin, c1["code"], hostname="host-ref")
    vm = _vm(admin, c1["code"], host["id"], hostname="vm-ref")

    resp = admin.delete(f"/api/v1/resources/{host['id']}", params={"version": 1})
    assert resp.status_code == 409, resp.text
    body = resp.json()["error"]
    assert body["code"] == "CONFLICT"
    assert body["details"]["reason"] == "reference_exists"
    refs = body["details"]["references"]
    assert refs == [
        {"object_type": "resource", "object_id": vm["id"], "label": "vm-ref"}
    ]

    # soft-delete the VM, then the Host can be deleted
    assert admin.delete(f"/api/v1/resources/{vm['id']}", params={"version": 1}).status_code == 204
    assert admin.delete(f"/api/v1/resources/{host['id']}", params={"version": 1}).status_code == 204
    with auth_session_factory() as session:
        # detail row survives the VM soft delete (lifecycle follows Resource)
        assert _vm_row(session, vm["id"]) is not None


# --- A14/B14-B15: restore re-checks host --------------------------------------


def test_restore_rechecks_host(role_client_factory):
    admin, _, _ = role_client_factory("ADMIN")
    c1 = _cluster(admin, code="C1")
    host = _bare_metal(admin, c1["code"], hostname="host-restore")
    vm = _vm(admin, c1["code"], host["id"], hostname="vm-restore")

    assert admin.delete(f"/api/v1/resources/{vm['id']}", params={"version": 1}).status_code == 204
    assert admin.delete(f"/api/v1/resources/{host['id']}", params={"version": 1}).status_code == 204

    # A soft-deleted Host is still expanded on the (deleted) VM's detail.
    detail = admin.get(
        f"/api/v1/resources/{vm['id']}", params={"deleted": "true"}
    ).json()["resource"]
    assert detail["virtual_machine"]["host"] == {
        "id": host["id"],
        "hostname": "host-restore",
    }

    resp = admin.post(f"/api/v1/resources/{vm['id']}/restore", params={"version": 2})
    assert resp.status_code == 409, resp.text
    body = resp.json()["error"]
    assert body["details"]["reason"] == "dependency_deleted"
    assert body["details"]["conflicts"] == [
        {"object_type": "resource", "object_id": host["id"]}
    ]
    # VM stays soft-deleted
    assert admin.get(f"/api/v1/resources/{vm['id']}").status_code == 404

    # restoring the Host first allows the VM restore
    assert admin.post(f"/api/v1/resources/{host['id']}/restore", params={"version": 2}).status_code == 200
    assert admin.post(f"/api/v1/resources/{vm['id']}/restore", params={"version": 2}).status_code == 200


# --- A13/B22-B23: lifecycle follows the Resource, no independent endpoint -----


def test_lifecycle_and_no_independent_endpoint(role_client_factory):
    admin, _, _ = role_client_factory("ADMIN")
    c1 = _cluster(admin, code="C1")
    host = _bare_metal(admin, c1["code"])
    vm = _vm(
        admin,
        c1["code"],
        host["id"],
        hostname="life",
        virtual_machine={"host_resource_id": host["id"], "vcpu": 2},
    )
    assert admin.delete(f"/api/v1/resources/{vm['id']}", params={"version": 1}).status_code == 204
    assert admin.get(f"/api/v1/resources/{vm['id']}").status_code == 404
    deleted = admin.get(f"/api/v1/resources/{vm['id']}", params={"deleted": "true"}).json()["resource"]
    assert deleted["virtual_machine"]["vcpu"] == 2
    assert admin.post(f"/api/v1/resources/{vm['id']}/restore", params={"version": 2}).status_code == 200

    for path in (
        f"/api/v1/resources/{vm['id']}/virtual-machine",
        f"/api/v1/resources/{vm['id']}/virtual-machine-details",
        "/api/v1/virtual-machine-details",
    ):
        assert admin.get(path).status_code == 404, path


# --- A15: permission matrix ---------------------------------------------------


def test_virtual_machine_permission_matrix(role_client_factory):
    admin, _, _ = role_client_factory("ADMIN")
    c1 = _cluster(admin, code="C1")
    host = _bare_metal(admin, c1["code"])
    vm = _vm(admin, c1["code"], host["id"], hostname="perm")

    viewer, _, _ = role_client_factory("VIEWER")
    editor, _, _ = role_client_factory("EDITOR")
    assert viewer.get(f"/api/v1/resources/{vm['id']}").status_code == 200
    assert (
        viewer.post(
            "/api/v1/resources",
            json={
                "cluster": c1["code"],
                "hostname": "v",
                "resource_type": "VIRTUAL_MACHINE",
                "virtual_machine": {"host_resource_id": host["id"]},
            },
        ).status_code
        == 403
    )
    assert (
        viewer.patch(
            f"/api/v1/resources/{vm['id']}",
            json={"version": 1, "virtual_machine": {"vcpu": 16}},
        ).status_code
        == 403
    )
    assert (
        editor.patch(
            f"/api/v1/resources/{vm['id']}",
            json={"version": 1, "virtual_machine": {"vcpu": 16}},
        ).status_code
        == 200
    )
    # delete/restore are ADMIN-only
    assert viewer.delete(f"/api/v1/resources/{vm['id']}", params={"version": 2}).status_code == 403
    assert editor.delete(f"/api/v1/resources/{vm['id']}", params={"version": 2}).status_code == 403
    assert admin.delete(f"/api/v1/resources/{vm['id']}", params={"version": 2}).status_code == 204
    assert admin.post(f"/api/v1/resources/{vm['id']}/restore", params={"version": 3}).status_code == 200


def test_patch_host_validation_precedes_version(role_client_factory):
    """Contract §2.5 PATCH order: host validation (if changed) before version."""
    client, _, _ = role_client_factory("EDITOR")
    c1 = _cluster(client, code="C1")
    host = _bare_metal(client, c1["code"])
    other = _bare_metal(client, c1["code"], hostname="other")
    vm = _vm(client, c1["code"], host["id"], hostname="order")

    # stale version + invalid host -> 422 (host) not 409 (version)
    resp = client.patch(
        f"/api/v1/resources/{vm['id']}",
        json={"version": 99, "virtual_machine": {"host_resource_id": str(uuid.uuid4())}},
    )
    assert resp.status_code == 422
    assert resp.json()["error"]["details"]["fields"][0]["field"] == (
        "virtual_machine.host_resource_id"
    )
    # stale version + valid host -> 409
    assert (
        client.patch(
            f"/api/v1/resources/{vm['id']}",
            json={"version": 99, "virtual_machine": {"host_resource_id": other["id"]}},
        ).status_code
        == 409
    )


# --- A16/B31: response host + list host_resource_id filter --------------------


def test_list_host_resource_filter(role_client_factory):
    client, _, _ = role_client_factory("EDITOR")
    c1 = _cluster(client, code="C1")
    host1 = _bare_metal(client, c1["code"], hostname="h1")
    host2 = _bare_metal(client, c1["code"], hostname="h2")
    _vm(client, c1["code"], host1["id"], hostname="v1")
    _vm(client, c1["code"], host1["id"], hostname="v2")
    _vm(client, c1["code"], host2["id"], hostname="v3")

    listed = client.get(
        "/api/v1/resources",
        params={"type": "VIRTUAL_MACHINE", "host_resource_id": host1["id"]},
    ).json()
    assert listed["total"] == 2
    assert {i["hostname"] for i in listed["items"]} == {"v1", "v2"}
    assert all(i["virtual_machine"]["host"]["id"] == host1["id"] for i in listed["items"])

    # non-UUID -> 422, nonexistent UUID -> empty
    assert client.get("/api/v1/resources", params={"host_resource_id": "nope"}).status_code == 422
    empty = client.get("/api/v1/resources", params={"host_resource_id": str(uuid.uuid4())}).json()
    assert empty["total"] == 0 and empty["items"] == []

    # BARE_METAL responses expose virtual_machine = null
    bare = client.get("/api/v1/resources", params={"type": "BARE_METAL"}).json()
    assert all(i["virtual_machine"] is None for i in bare["items"])
    assert all(i["hardware"] is not None for i in bare["items"])


# --- V19: audit shares the transaction / rollback leaves no trace -------------


def test_virtual_machine_update_rolls_back_with_audit(auth_session_factory, make_user, monkeypatch):
    user, _ = make_user(role="EDITOR")
    operator = _operator(user)
    with auth_session_factory() as session:
        cluster_service.create_cluster(session, operator, code="RBM", name="rbm")
    with auth_session_factory() as session:
        host = resource_service.create_resource(
            session, operator, cluster="RBM", hostname="rbh", resource_type="BARE_METAL"
        )
        host_id = host.id
    with auth_session_factory() as session:
        vm = resource_service.create_resource(
            session,
            operator,
            cluster="RBM",
            hostname="rbvm",
            resource_type="VIRTUAL_MACHINE",
            virtual_machine={"host_resource_id": str(host_id), "vcpu": 2},
        )
        vm_id = vm.id

    original_record = resource_service.audit.record

    def corrupt_record(*args, **kwargs):
        row = original_record(*args, **kwargs)
        row.action = "BOGUS"
        return row

    monkeypatch.setattr(resource_service.audit, "record", corrupt_record)
    with auth_session_factory() as session:
        with pytest.raises(Exception):
            resource_service.update_resource(
                session,
                operator,
                vm_id,
                expected_version=1,
                changes={},
                virtual_machine={"vcpu": 8},
            )
        session.rollback()

    with auth_session_factory() as session:
        assert _vm_row(session, vm_id)["vcpu"] == 2  # rolled back
        assert (
            session.execute(select(AuditLog).where(AuditLog.action == "BOGUS"))
            .scalars()
            .all()
            == []
        )


# --- B34: optimistic lock across two real sessions (rehost) -------------------


def test_rehost_optimistic_lock_two_sessions(auth_session_factory, make_user):
    user, _ = make_user(role="EDITOR")
    operator = _operator(user)
    with auth_session_factory() as setup:
        cluster_service.create_cluster(setup, operator, code="LKV", name="lkv")
    with auth_session_factory() as setup:
        host_a = resource_service.create_resource(
            setup, operator, cluster="LKV", hostname="lka", resource_type="BARE_METAL"
        )
        host_b = resource_service.create_resource(
            setup, operator, cluster="LKV", hostname="lkb", resource_type="BARE_METAL"
        )
        vm = resource_service.create_resource(
            setup,
            operator,
            cluster="LKV",
            hostname="lkvm",
            resource_type="VIRTUAL_MACHINE",
            virtual_machine={"host_resource_id": str(host_a.id)},
        )
        vm_id, host_a_id, host_b_id = vm.id, host_a.id, host_b.id

    first = auth_session_factory()
    second = auth_session_factory()
    try:
        resource_service.update_resource(
            first,
            operator,
            vm_id,
            expected_version=1,
            changes={},
            virtual_machine={"host_resource_id": str(host_a_id)},
        )
        with pytest.raises(VersionConflict) as exc:
            resource_service.update_resource(
                second,
                operator,
                vm_id,
                expected_version=1,
                changes={},
                virtual_machine={"host_resource_id": str(host_b_id)},
            )
        assert exc.value.details == {"current_version": 2}
        second.rollback()
    finally:
        first.close()
        second.close()

    with auth_session_factory() as verify:
        final = resource_service.get_resource(verify, vm_id)
        assert final.version == 2
        assert final.virtual_machine_detail.host_resource_id == host_a_id


# --- DR-71: concurrent lock serialisation (both directions) ------------------


def test_dr71_create_waits_for_host_delete_lock(role_client_factory, committed_engine):
    client, _, _ = role_client_factory("ADMIN")
    c1 = _cluster(client, code="DR71A")
    host = _bare_metal(client, c1["code"], hostname="dr71a-host")
    host_id = uuid.UUID(host["id"])

    result: dict = {}

    def worker():
        try:
            resp = client.post(
                "/api/v1/resources",
                json={
                    "cluster": c1["code"],
                    "hostname": "dr71a-vm",
                    "resource_type": "VIRTUAL_MACHINE",
                    "virtual_machine": {"host_resource_id": host["id"]},
                },
            )
            result["status"] = resp.status_code
        except Exception as exc:  # pragma: no cover - surfaced via assertion
            result["error"] = repr(exc)

    conn = committed_engine.connect()
    txn = conn.begin()
    try:
        conn.execute(text("SELECT id FROM resources WHERE id = :id FOR UPDATE"), {"id": host_id})
        thread = threading.Thread(target=worker)
        thread.start()
        time.sleep(0.6)
        assert thread.is_alive(), "create must block on the host row lock (DR-71)"
        conn.execute(
            text(
                "UPDATE resources SET deleted_at = now(), version = version + 1 "
                "WHERE id = :id"
            ),
            {"id": host_id},
        )
        txn.commit()
    finally:
        conn.close()
    thread.join(timeout=15)
    assert not thread.is_alive()
    assert result.get("status") == 422, result


def test_dr71_host_delete_waits_for_vm_create_lock(role_client_factory, committed_engine):
    client, _, _ = role_client_factory("ADMIN")
    c1 = _cluster(client, code="DR71B")
    host = _bare_metal(client, c1["code"], hostname="dr71b-host")
    host_id = uuid.UUID(host["id"])

    result: dict = {}

    def worker():
        try:
            resp = client.delete(f"/api/v1/resources/{host['id']}", params={"version": 1})
            result["status"] = resp.status_code
            result["body"] = resp.json() if resp.status_code != 204 else {}
        except Exception as exc:  # pragma: no cover - surfaced via assertion
            result["error"] = repr(exc)

    conn = committed_engine.connect()
    txn = conn.begin()
    try:
        conn.execute(text("SELECT id FROM resources WHERE id = :id FOR UPDATE"), {"id": host_id})
        vm_id = uuid.uuid4()
        cluster_id = conn.execute(
            text(
                "SELECT cluster_id FROM resources WHERE id = :id"
            ),
            {"id": host_id},
        ).scalar_one()
        conn.execute(
            text(
                "INSERT INTO resources (id, cluster_id, hostname, hostname_key, resource_type) "
                "VALUES (:vm, :cid, :hn, :hk, 'VIRTUAL_MACHINE')"
            ),
            {"vm": vm_id, "cid": cluster_id, "hn": "dr71b-vm", "hk": "dr71b-vm"},
        )
        conn.execute(
            text(
                "INSERT INTO virtual_machine_details (resource_id, host_resource_id) "
                "VALUES (:vm, :host)"
            ),
            {"vm": vm_id, "host": host_id},
        )
        thread = threading.Thread(target=worker)
        thread.start()
        time.sleep(0.6)
        assert thread.is_alive(), "Host delete must block on the host row lock (DR-71)"
        txn.commit()
    finally:
        conn.close()
    thread.join(timeout=15)
    assert not thread.is_alive()
    assert result.get("status") == 409, result
    assert result["body"]["error"]["details"]["reason"] == "reference_exists"