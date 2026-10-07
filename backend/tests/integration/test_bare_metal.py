"""F005 BareMetal hardware API integration tests (A1-A10, V1-V16, B1-B24).

Requires a real PostgreSQL database via ``TEST_DATABASE_URL`` (DB-D10 guard in
``conftest``). Raw-SQL database assertions live in
``test_bare_metal_constraints.py``; migration/backfill evidence too.
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
from app.models.resource import Resource
from app.services import cluster as cluster_service
from app.services import resource as resource_service

HARDWARE_FIELDS = (
    "manufacturer",
    "model",
    "serial_number",
    "cpu_model",
    "gpu_model",
    "cpu_sockets",
    "cpu_cores",
    "memory_mb",
    "gpu_count",
    "metadata",
)


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


def _operator(user) -> Operator:
    return Operator(user_id=user.id, username=user.username, role=Role(user.role))


def _hardware_row(session, resource_id):
    return session.execute(
        text(
            "SELECT manufacturer, model, serial_number, cpu_model, gpu_model, "
            "cpu_sockets, cpu_cores, memory_mb, gpu_count, metadata "
            "FROM bare_metal_details WHERE resource_id = :id"
        ),
        {"id": uuid.UUID(str(resource_id))},
    ).mappings().first()


def _detail_rows(session, resource_id) -> int:
    return session.execute(
        text("SELECT count(*) FROM bare_metal_details WHERE resource_id = :id"),
        {"id": uuid.UUID(str(resource_id))},
    ).scalar_one()


# --- A1/A2/B1-B4: unknown vs 0, null semantics --------------------------------


def test_create_omitted_and_explicit_null_are_null(role_client_factory, auth_session_factory):
    client, _, _ = role_client_factory("EDITOR")
    c1 = _cluster(client, code="C1")

    omitted = _resource(client, c1["code"], hostname="omitted")
    assert omitted["hardware"] == {field: ({} if field == "metadata" else None) for field in HARDWARE_FIELDS}

    explicit = _resource(
        client,
        c1["code"],
        hostname="explicit",
        hardware={field: None for field in HARDWARE_FIELDS if field != "metadata"},
    )
    assert explicit["hardware"] == {field: ({} if field == "metadata" else None) for field in HARDWARE_FIELDS}

    with auth_session_factory() as session:
        for resource in (omitted, explicit):
            row = _hardware_row(session, resource["id"])
            assert row is not None
            for field in HARDWARE_FIELDS[:-1]:
                assert row[field] is None, (resource["hostname"], field)
            assert row["metadata"] == {}


def test_gpu_count_zero_vs_null(role_client_factory, auth_session_factory):
    client, _, _ = role_client_factory("EDITOR")
    c1 = _cluster(client, code="C1")
    zero = _resource(client, c1["code"], hostname="gpu0", hardware={"gpu_count": 0})
    unknown = _resource(client, c1["code"], hostname="gpunull")
    assert zero["hardware"]["gpu_count"] == 0
    assert unknown["hardware"]["gpu_count"] is None

    with auth_session_factory() as session:
        assert _hardware_row(session, zero["id"])["gpu_count"] == 0
        assert _hardware_row(session, unknown["id"])["gpu_count"] is None


def test_partial_registration_leaves_other_unknown(role_client_factory, auth_session_factory):
    client, _, _ = role_client_factory("EDITOR")
    c1 = _cluster(client, code="C1")
    created = _resource(
        client,
        c1["code"],
        hostname="partial",
        hardware={"manufacturer": "Dell", "cpu_cores": 192},
    )
    hw = created["hardware"]
    assert hw["manufacturer"] == "Dell" and hw["cpu_cores"] == 192
    assert hw["model"] is None and hw["gpu_count"] is None and hw["metadata"] == {}
    with auth_session_factory() as session:
        row = _hardware_row(session, created["id"])
        assert row["manufacturer"] == "Dell" and row["cpu_cores"] == 192
        assert row["model"] is None


# --- A3/B5-B8: numeric ranges and strict integers -----------------------------


def test_positive_integer_range_and_strict_types(role_client_factory):
    client, _, _ = role_client_factory("EDITOR")
    c1 = _cluster(client, code="C1")

    for field in ("cpu_sockets", "cpu_cores", "memory_mb"):
        for bad in (0, -1, -100):
            resp = _create(client, c1["code"], hostname=f"bad-{field}-{bad}", hardware={field: bad})
            assert resp.status_code == 422, (field, bad, resp.text)
    assert _create(client, c1["code"], hostname="gpuneg", hardware={"gpu_count": -1}).status_code == 422

    # strict: string / bool / float / list all rejected
    for bad in ("192", True, 1.5, [192], {}):
        resp = _create(client, c1["code"], hostname=f"strict-{type(bad).__name__}", hardware={"cpu_cores": bad})
        assert resp.status_code == 422, (bad, resp.text)

    ok = _resource(
        client,
        c1["code"],
        hostname="edge",
        hardware={
            "cpu_sockets": 2,
            "cpu_cores": 2147483647,
            "memory_mb": 1,
            "gpu_count": 0,
        },
    )
    assert ok["hardware"]["cpu_cores"] == 2147483647
    assert ok["hardware"]["gpu_count"] == 0
    assert (
        _create(client, c1["code"], hostname="overflow", hardware={"cpu_cores": 2147483648}).status_code
        == 422
    )


# --- A4/A5/B9/B10: units and physical cores -----------------------------------


def test_memory_mb_and_cpu_cores_are_stored_verbatim(role_client_factory, auth_session_factory):
    client, _, _ = role_client_factory("EDITOR")
    c1 = _cluster(client, code="C1")
    created = _resource(
        client,
        c1["code"],
        hostname="srv1",
        hardware={"cpu_sockets": 2, "cpu_cores": 192, "memory_mb": 1572864},
    )
    hw = created["hardware"]
    # 1536 GiB * 1024 = 1572864 MiB, stored as-is (no *1000 / /1024)
    assert hw["memory_mb"] == 1572864
    assert hw["cpu_cores"] == 192
    with auth_session_factory() as session:
        row = _hardware_row(session, created["id"])
        assert row["memory_mb"] == 1572864
        assert row["cpu_cores"] == 192
    # no sockets x cores derivation: 384 is accepted as a plain positive integer
    other = _resource(client, c1["code"], hostname="srv2", hardware={"cpu_sockets": 2, "cpu_cores": 384})
    assert other["hardware"]["cpu_cores"] == 384


# --- A6/B11: SN has no uniqueness ---------------------------------------------


def test_serial_number_can_repeat(role_client_factory, auth_session_factory):
    client, _, _ = role_client_factory("EDITOR")
    c1 = _cluster(client, code="C1")
    first = _resource(client, c1["code"], hostname="sn1", hardware={"serial_number": "SN-1"})
    second = _resource(client, c1["code"], hostname="sn2", hardware={"serial_number": "SN-1"})
    assert first["hardware"]["serial_number"] == second["hardware"]["serial_number"] == "SN-1"

    updated = client.patch(
        f"/api/v1/resources/{second['id']}",
        json={"version": 1, "hardware": {"serial_number": "SN-1"}},
    )
    assert updated.status_code == 200, updated.text

    with auth_session_factory() as session:
        unique_on_sn = session.execute(
            text(
                "SELECT indexdef FROM pg_indexes WHERE schemaname='public' "
                "AND tablename='bare_metal_details' AND indexdef ILIKE '%serial_number%'"
            )
        ).scalars().all()
    assert unique_on_sn == []


# --- A7/B15: detail contains all six hardware groups --------------------------


def test_detail_hardware_fields_and_single_row(role_client_factory, auth_session_factory):
    client, _, _ = role_client_factory("EDITOR")
    c1 = _cluster(client, code="C1")
    created = _resource(
        client,
        c1["code"],
        hostname="full",
        hardware={
            "manufacturer": "Dell",
            "model": "R760",
            "serial_number": "ABC123",
            "cpu_model": "EPYC 9654",
            "cpu_sockets": 2,
            "cpu_cores": 192,
            "memory_mb": 1572864,
            "gpu_model": "H100",
            "gpu_count": 8,
            "metadata": {"vendor_tag": "x"},
        },
    )
    detail = client.get(f"/api/v1/resources/{created['id']}").json()["resource"]
    hw = detail["hardware"]
    assert hw["manufacturer"] == "Dell"
    assert hw["model"] == "R760"
    assert hw["serial_number"] == "ABC123"
    assert hw["cpu_model"] == "EPYC 9654"
    assert hw["cpu_sockets"] == 2 and hw["cpu_cores"] == 192
    assert hw["memory_mb"] == 1572864
    assert hw["gpu_model"] == "H100" and hw["gpu_count"] == 8
    assert hw["metadata"] == {"vendor_tag": "x"}

    vm = _resource(client, c1["code"], hostname="vm1", resource_type="VIRTUAL_MACHINE")
    with auth_session_factory() as session:
        assert _detail_rows(session, created["id"]) == 1
        assert _detail_rows(session, vm["id"]) == 0


# --- B12/B13: strings and whole-object validity -------------------------------


def test_hardware_string_trim_and_rejection(role_client_factory, auth_session_factory):
    client, _, _ = role_client_factory("EDITOR")
    c1 = _cluster(client, code="C1")
    trimmed = _resource(client, c1["code"], hostname="trim", hardware={"manufacturer": "  Dell  "})
    assert trimmed["hardware"]["manufacturer"] == "Dell"

    for bad in ("", "   ", "a" * 256, "bad\x01name"):
        resp = _create(client, c1["code"], hostname=f"bstr-{len(bad)}", hardware={"manufacturer": bad})
        assert resp.status_code == 422, (bad, resp.text)
    assert _create(client, c1["code"], hostname="len255", hardware={"model": "m" * 255}).status_code == 201


def test_hardware_whole_object_invalid(role_client_factory):
    client, _, _ = role_client_factory("EDITOR")
    c1 = _cluster(client, code="C1")
    for bad in ([], "x", None, 5, {"unknown_key": 1}):
        resp = _create(client, c1["code"], hostname=f"whole-{type(bad).__name__}", hardware=bad)
        assert resp.status_code == 422, (bad, resp.text)


# --- V12/B14: VM never carries hardware ---------------------------------------


def test_vm_rejects_hardware_and_returns_null(role_client_factory, auth_session_factory):
    client, _, _ = role_client_factory("EDITOR")
    c1 = _cluster(client, code="C1")
    vm = _resource(client, c1["code"], hostname="vm-null", resource_type="VIRTUAL_MACHINE")
    assert vm["hardware"] is None

    for bad in ({}, {"cpu_cores": 8}, None):
        resp = _create(client, c1["code"], hostname=f"vm-{len(str(bad))}", resource_type="VIRTUAL_MACHINE", hardware=bad)
        assert resp.status_code == 422, (bad, resp.text)

    patched = client.patch(
        f"/api/v1/resources/{vm['id']}", json={"version": 1, "hardware": {"cpu_cores": 8}}
    )
    assert patched.status_code == 422
    with auth_session_factory() as session:
        assert _detail_rows(session, vm["id"]) == 0


# --- A8/B16-B20: PATCH semantics, metadata, audit -----------------------------


def test_patch_subfield_omit_keeps_and_null_clears(role_client_factory, auth_session_factory):
    client, _, _ = role_client_factory("EDITOR")
    c1 = _cluster(client, code="C1")
    created = _resource(
        client,
        c1["code"],
        hostname="patch1",
        hardware={"manufacturer": "Dell", "cpu_cores": 192, "memory_mb": 1024},
    )
    # omit keeps original values, only gpu_count changes
    updated = client.patch(
        f"/api/v1/resources/{created['id']}",
        json={"version": 1, "hardware": {"gpu_count": 8}},
    )
    assert updated.status_code == 200, updated.text
    hw = updated.json()["resource"]["hardware"]
    assert hw["manufacturer"] == "Dell"
    assert hw["cpu_cores"] == 192
    assert hw["memory_mb"] == 1024
    assert hw["gpu_count"] == 8

    # explicit null clears a nullable sub-field, others stay
    cleared = client.patch(
        f"/api/v1/resources/{created['id']}",
        json={"version": 2, "hardware": {"manufacturer": None}},
    ).json()["resource"]["hardware"]
    assert cleared["manufacturer"] is None
    assert cleared["cpu_cores"] == 192 and cleared["gpu_count"] == 8

    # hardware itself cannot be nulled
    bad = client.patch(
        f"/api/v1/resources/{created['id']}", json={"version": 3, "hardware": None}
    )
    assert bad.status_code == 422
    with auth_session_factory() as session:
        row = _hardware_row(session, created["id"])
        assert row["manufacturer"] is None and row["cpu_cores"] == 192


def test_patch_hardware_metadata_whole_replacement(role_client_factory, auth_session_factory):
    client, _, _ = role_client_factory("EDITOR")
    c1 = _cluster(client, code="C1")
    created = _resource(
        client,
        c1["code"],
        hostname="hmeta",
        hardware={"metadata": {"a": 1, "b": 2}},
    )
    replaced = client.patch(
        f"/api/v1/resources/{created['id']}",
        json={"version": 1, "hardware": {"metadata": {"c": 3}}},
    ).json()["resource"]["hardware"]
    assert replaced["metadata"] == {"c": 3}
    assert (
        client.patch(
            f"/api/v1/resources/{created['id']}",
            json={"version": 2, "hardware": {"metadata": [1, 2]}},
        ).status_code
        == 422
    )


def test_hardware_audit_snapshots(role_client_factory, auth_session_factory):
    admin, _, _ = role_client_factory("ADMIN")
    c1 = _cluster(admin, code="C1")
    created = _resource(
        admin,
        c1["code"],
        hostname="audit-hw",
        hardware={"cpu_cores": 64, "metadata": {"rack": "R1"}},
    )
    rid = uuid.UUID(created["id"])
    assert (
        admin.patch(
            f"/api/v1/resources/{rid}", json={"version": 1, "hardware": {"memory_mb": 512}}
        ).status_code
        == 200
    )
    assert admin.delete(f"/api/v1/resources/{rid}", params={"version": 2}).status_code == 204
    assert admin.post(f"/api/v1/resources/{rid}/restore", params={"version": 3}).status_code == 200

    with auth_session_factory() as session:
        rows = (
            session.execute(
                select(AuditLog).where(AuditLog.object_id == rid).order_by(AuditLog.created_at)
            )
            .scalars()
            .all()
        )
        assert [r.action for r in rows] == ["CREATE", "UPDATE", "DELETE", "RESTORE"]
        assert rows[0].after_data["hardware"]["cpu_cores"] == 64
        assert rows[0].after_data["hardware"]["metadata"] == {"rack": "R1"}
        assert rows[1].before_data["hardware"]["cpu_cores"] == 64
        assert rows[1].after_data["hardware"]["memory_mb"] == 512
        # VM snapshots carry hardware = null
        vm = _resource(admin, c1["code"], hostname="vm-audit", resource_type="VIRTUAL_MACHINE")
        vm_row = (
            session.execute(
                select(AuditLog).where(AuditLog.object_id == uuid.UUID(vm["id"]))
            ).scalars().one()
        )
        assert vm_row.after_data["hardware"] is None


def test_hardware_update_rolls_back_with_audit(
    role_client_factory, auth_session_factory, monkeypatch
):
    _, admin_user, _ = role_client_factory("ADMIN")
    operator = _operator(admin_user)
    with auth_session_factory() as session:
        cluster_service.create_cluster(session, operator, code="RBH", name="rbh")
    with auth_session_factory() as session:
        created = resource_service.create_resource(
            session,
            operator,
            cluster="RBH",
            hostname="rbh",
            resource_type="BARE_METAL",
            hardware={"memory_mb": 1024},
        )
        rid = created.id

    original_record = resource_service.audit.record

    def corrupt_record(*args, **kwargs):
        row = original_record(*args, **kwargs)
        row.action = "BOGUS"
        return row

    monkeypatch.setattr(resource_service.audit, "record", corrupt_record)
    with auth_session_factory() as session:
        with pytest.raises(Exception):
            resource_service.update_resource(
                session, operator, rid, expected_version=1, changes={}, hardware={"memory_mb": 2048}
            )
        session.rollback()

    with auth_session_factory() as session:
        row = _hardware_row(session, rid)
        assert row["memory_mb"] == 1024  # rolled back
        assert (
            session.execute(select(AuditLog).where(AuditLog.action == "BOGUS"))
            .scalars()
            .all()
            == []
        )


# --- A9/B24: lifecycle follows the Resource -----------------------------------


def test_soft_delete_and_restore_keep_hardware(role_client_factory):
    admin, _, _ = role_client_factory("ADMIN")
    c1 = _cluster(admin, code="C1")
    created = _resource(admin, c1["code"], hostname="life", hardware={"cpu_cores": 32})
    rid = created["id"]
    assert admin.delete(f"/api/v1/resources/{rid}", params={"version": 1}).status_code == 204
    # hidden from the default view, visible with deleted=true
    assert admin.get(f"/api/v1/resources/{rid}").status_code == 404
    deleted = admin.get(f"/api/v1/resources/{rid}", params={"deleted": "true"}).json()["resource"]
    assert deleted["hardware"]["cpu_cores"] == 32
    assert (
        admin.post(f"/api/v1/resources/{rid}/restore", params={"version": 2}).status_code == 200
    )
    restored = admin.get(f"/api/v1/resources/{rid}").json()["resource"]
    assert restored["hardware"]["cpu_cores"] == 32


# --- B21: permissions follow the Resource -------------------------------------


def test_hardware_permission_matrix(role_client_factory):
    admin, _, _ = role_client_factory("ADMIN")
    c1 = _cluster(admin, code="C1")
    created = _resource(admin, c1["code"], hostname="perm-hw", hardware={"cpu_cores": 8})

    viewer, _, _ = role_client_factory("VIEWER")
    editor, _, _ = role_client_factory("EDITOR")
    assert viewer.get(f"/api/v1/resources/{created['id']}").status_code == 200
    assert (
        viewer.post(
            "/api/v1/resources",
            json={"cluster": c1["code"], "hostname": "v", "resource_type": "BARE_METAL", "hardware": {"cpu_cores": 4}},
        ).status_code
        == 403
    )
    assert (
        viewer.patch(
            f"/api/v1/resources/{created['id']}", json={"version": 1, "hardware": {"cpu_cores": 16}}
        ).status_code
        == 403
    )
    assert (
        editor.patch(
            f"/api/v1/resources/{created['id']}", json={"version": 1, "hardware": {"cpu_cores": 16}}
        ).status_code
        == 200
    )


# --- B22: optimistic locking across two real sessions -------------------------


def test_hardware_optimistic_lock_two_sessions(auth_session_factory, make_user):
    user, _ = make_user(role="EDITOR")
    operator = _operator(user)
    with auth_session_factory() as setup:
        cluster_service.create_cluster(setup, operator, code="LOCKH", name="lockh")
    with auth_session_factory() as setup:
        created = resource_service.create_resource(
            setup,
            operator,
            cluster="LOCKH",
            hostname="lockh",
            resource_type="BARE_METAL",
            hardware={"cpu_cores": 8},
        )
        rid = created.id

    first = auth_session_factory()
    second = auth_session_factory()
    try:
        resource_service.update_resource(
            first, operator, rid, expected_version=1, changes={}, hardware={"cpu_cores": 16}
        )
        with pytest.raises(VersionConflict) as exc:
            resource_service.update_resource(
                second, operator, rid, expected_version=1, changes={}, hardware={"cpu_cores": 32}
            )
        assert exc.value.details == {"current_version": 2}
        second.rollback()
    finally:
        first.close()
        second.close()

    with auth_session_factory() as verify:
        final = resource_service.get_resource(verify, rid)
        assert final.version == 2
        assert final.bare_metal_detail.cpu_cores == 16


# --- list response carries hardware / null ------------------------------------


def test_list_includes_hardware_and_vm_null(role_client_factory):
    client, _, _ = role_client_factory("EDITOR")
    c1 = _cluster(client, code="C1")
    _resource(client, c1["code"], hostname="bare", hardware={"gpu_count": 4})
    _resource(client, c1["code"], hostname="virt", resource_type="VIRTUAL_MACHINE")
    items = {i["hostname"]: i for i in client.get("/api/v1/resources").json()["items"]}
    assert items["bare"]["hardware"]["gpu_count"] == 4
    assert items["virt"]["hardware"] is None


def test_no_independent_hardware_route(role_client_factory):
    client, _, _ = role_client_factory("ADMIN")
    c1 = _cluster(client, code="C1")
    created = _resource(client, c1["code"], hostname="noroute")
    for path in (
        f"/api/v1/resources/{created['id']}/hardware",
        f"/api/v1/resources/{created['id']}/bare-metal-details",
        "/api/v1/bare-metal-details",
    ):
        assert client.get(path).status_code == 404, path