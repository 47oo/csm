"""F009 IPPool API integration tests (A1-A23 F009-independent items + stub provider).

Requires a real PostgreSQL database via ``TEST_DATABASE_URL`` (DB-D10 guard in
``conftest``). Raw-SQL constraint/exclusion/generated-column/migration evidence
lives in ``test_ip_pool_constraints.py``.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text

from app.core.auth import Operator
from app.core.errors import VersionConflict
from app.core.permissions import Role
from app.models.audit_log import AuditLog
from app.services import cluster as cluster_service
from app.services import ip_occupancy
from app.services import ip_pool as ip_pool_service
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


def _create_pool(client, network, name="pool", start="10.0.0.1", end="10.0.0.9", **kw):
    body = {
        "network": network,
        "name": name,
        "start_address": start,
        "end_address": end,
    }
    body.update(kw)
    return client.post("/api/v1/ip-pools", json=body)


def _pool(client, network, name="pool", start="10.0.0.1", end="10.0.0.9", **kw):
    resp = _create_pool(client, network, name=name, start=start, end=end, **kw)
    assert resp.status_code == 201, resp.text
    return resp.json()["ip_pool"]


def _operator(user) -> Operator:
    return Operator(user_id=user.id, username=user.username, role=Role(user.role))


def _row(session, pool_id):
    return session.execute(
        text(
            "SELECT network_id, name, name_key, start_address, end_address, "
            "allocation_mode, description, version, deleted_at, "
            "address_range::text AS address_range "
            "FROM ip_pools WHERE id = :id"
        ),
        {"id": uuid.UUID(str(pool_id))},
    ).mappings().first()


class _StubProvider:
    """Deterministic IpOccupancyProvider for the F009 structural tests."""

    def __init__(self, total: int = 0, items: list[dict] | None = None) -> None:
        self.total = total
        self.items = items or []
        self.calls: list[tuple] = []

    def occupancy(self, db, network_id, start_address, end_address, limit):
        self.calls.append((str(start_address), str(end_address), limit))
        return {"total": self.total, "items": self.items[:limit]}


@pytest.fixture
def occupancy_stub(monkeypatch):
    def _install(total: int = 0, items: list[dict] | None = None):
        stub = _StubProvider(total=total, items=items)
        monkeypatch.setattr(ip_occupancy, "_PROVIDERS", [stub])
        return stub

    return _install


def _conflict_item(address="10.0.0.5", bound=False):
    return {
        "object_type": "ip_address",
        "object_id": str(uuid.uuid4()),
        "address": address,
        "bound": bound,
        "interface_id": None if not bound else str(uuid.uuid4()),
        "resource_id": None if not bound else str(uuid.uuid4()),
        "resource_hostname": None if not bound else "host-1",
    }


# --- create defaults / response shape ----------------------------------------


def test_create_defaults_and_response_shape(role_client_factory, auth_session_factory):
    client, _, _ = role_client_factory("EDITOR")
    c1 = _cluster(client, code="C1")
    net = _network(client, c1["id"], name="MGMT", cidr="10.0.0.0/24")

    created = _pool(client, net["id"], name="pool-A", start="10.0.0.1", end="10.0.0.9")
    assert created["network"] == {"id": net["id"], "name": "MGMT", "cidr": "10.0.0.0/24"}
    assert created["name"] == "pool-A"
    assert created["start_address"] == "10.0.0.1"
    assert created["end_address"] == "10.0.0.9"
    assert created["allocation_mode"] == "MANUAL"
    assert created["description"] is None
    assert created["version"] == 1
    assert created["deleted_at"] is None
    assert created["created_at"] and created["updated_at"]
    assert "name_key" not in created and "address_range" not in created
    assert "metadata" not in created

    with auth_session_factory() as session:
        row = _row(session, created["id"])
        assert row["name_key"] == "pool-a"
        assert str(row["start_address"]) == "10.0.0.1"
        assert row["allocation_mode"] == "MANUAL"
        # Generated closed-interval integer range: 10.0.0.1 -> 10.0.0.9.
        assert row["address_range"] == "[167772161,167772170)"


# --- name normalisation / uniqueness -----------------------------------------


def test_name_normalisation_and_uniqueness(role_client_factory, auth_session_factory):
    client, _, _ = role_client_factory("EDITOR")
    c1 = _cluster(client, code="C1")
    c2 = _cluster(client, code="C2")
    n1 = _network(client, c1["id"], name="n1", cidr="10.0.0.0/24")
    n2 = _network(client, c1["id"], name="n2", cidr="10.1.0.0/24")
    n3 = _network(client, c2["id"], name="n3", cidr="10.0.0.0/24")

    trimmed = _pool(client, n1["id"], name="  pool  ", end="10.0.0.5")
    assert trimmed["name"] == "pool"
    spaced = _pool(client, n1["id"], name="po ol", start="10.0.0.10", end="10.0.0.11")
    assert spaced["name"] == "po ol"
    double = _pool(client, n1["id"], name="po  ol", start="10.0.0.12", end="10.0.0.13")
    assert double["name"] == "po  ol"  # internal spaces not collapsed

    # case-insensitive duplicate in the same network
    dup = _create_pool(client, n1["id"], name="POOL", start="10.0.0.20", end="10.0.0.21")
    assert dup.status_code == 409, dup.text
    assert dup.json()["error"]["details"] == {
        "reason": "unique_conflict",
        "field": "name",
    }
    # cross-network same name allowed
    _pool(client, n2["id"], name="pool", start="10.1.0.1", end="10.1.0.2")
    _pool(client, n3["id"], name="pool", start="10.0.0.1", end="10.0.0.2")

    for bad in ("", "   ", "a" * 256, "e\x01th", "a\u200bb"):
        resp = _create_pool(
            client, n1["id"], name=bad, start="10.0.0.30", end="10.0.0.31"
        )
        assert resp.status_code == 422, (bad, resp.text)
        assert resp.json()["error"]["details"]["fields"][0]["field"] == "name"

    with auth_session_factory() as session:
        assert _row(session, spaced["id"])["name_key"] == "po ol"


def test_name_soft_delete_and_restore_reuse(role_client_factory):
    admin, _, _ = role_client_factory("ADMIN")
    c1 = _cluster(admin, code="C1")
    net = _network(admin, c1["id"], name="n1")
    first = _pool(admin, net["id"], name="dup", start="10.0.0.1", end="10.0.0.5")

    # soft delete releases both name and range
    assert admin.delete(
        f"/api/v1/ip-pools/{first['id']}", params={"version": 1}
    ).status_code == 204
    recreated = _pool(admin, net["id"], name="DUP", start="10.0.0.1", end="10.0.0.5")
    assert recreated["id"] != first["id"]

    # restoring the original fails on the name and never overwrites the newer one
    resp = admin.post(f"/api/v1/ip-pools/{first['id']}/restore", params={"version": 2})
    assert resp.status_code == 409
    assert resp.json()["error"]["details"]["reason"] == "unique_conflict"
    live = admin.get(f"/api/v1/ip-pools/{recreated['id']}").json()["ip_pool"]
    assert live["deleted_at"] is None and live["version"] == 1


# --- address validation -------------------------------------------------------


def test_address_validation(role_client_factory):
    client, _, _ = role_client_factory("EDITOR")
    c1 = _cluster(client, code="C1")
    net = _network(client, c1["id"], name="n1", cidr="10.0.0.0/24")

    # start == end allowed (single-address pool)
    single = _pool(client, net["id"], name="single", start="10.0.0.5", end="10.0.0.5")
    assert single["start_address"] == "10.0.0.5"

    # non-IPv4 / CIDR form / out-of-cidr / reverse order
    cases = [
        ("bad", "not-an-ip", "10.0.0.9", "start_address"),
        ("cidr", "10.0.0.1/24", "10.0.0.9", "start_address"),
        ("v6", "::1", "10.0.0.9", "start_address"),
        ("outside-s", "10.0.1.1", "10.0.1.5", "start_address"),
        ("outside-e", "10.0.0.1", "10.0.1.5", "end_address"),
        ("reverse", "10.0.0.9", "10.0.0.1", "start_address"),
    ]
    for name, start, end, field in cases:
        resp = _create_pool(client, net["id"], name=name, start=start, end=end)
        assert resp.status_code == 422, (name, resp.text)
        assert resp.json()["error"]["details"]["fields"][0]["field"] == field


# --- allocation_mode ----------------------------------------------------------


def test_allocation_mode(role_client_factory):
    client, _, _ = role_client_factory("EDITOR")
    c1 = _cluster(client, code="C1")
    net = _network(client, c1["id"], name="n1")

    for mode in ("MANUAL", "AUTO", "RESERVED"):
        created = _pool(
            client,
            net["id"],
            name=f"m-{mode}",
            start=f"10.0.0.{len(mode)}",
            end=f"10.0.0.{len(mode)}",
            allocation_mode=mode,
        )
        assert created["allocation_mode"] == mode

    for bad in ("active", "", "NOPE", None):
        resp = _create_pool(
            client, net["id"], name=f"bad-{bad}", allocation_mode=bad
        )
        assert resp.status_code == 422, (bad, resp.text)
        assert resp.json()["error"]["details"]["fields"][0]["field"] == "allocation_mode"


# --- overlap ------------------------------------------------------------------


def test_range_overlap_and_soft_delete_release(role_client_factory):
    admin, _, _ = role_client_factory("ADMIN")
    editor, _, _ = role_client_factory("EDITOR")
    c1 = _cluster(admin, code="C1")
    c2 = _cluster(admin, code="C2")
    n1 = _network(admin, c1["id"], name="n1", cidr="10.0.0.0/24")
    n2 = _network(admin, c2["id"], name="n2", cidr="10.0.0.0/24")

    base = _pool(editor, n1["id"], name="base", start="10.0.0.10", end="10.0.0.20")

    # contained / identical / shared endpoint all overlap
    for name, start, end in (
        ("contained", "10.0.0.12", "10.0.0.15"),
        ("identical", "10.0.0.10", "10.0.0.20"),
        ("share-start", "10.0.0.10", "10.0.0.30"),
        ("share-end", "10.0.0.1", "10.0.0.10"),
    ):
        resp = _create_pool(editor, n1["id"], name=name, start=start, end=end)
        assert resp.status_code == 409, (name, resp.text)
        details = resp.json()["error"]["details"]
        assert details["reason"] == "range_overlap"
        assert details["field"] == "start_address"
        assert details["conflicts"][0]["object_type"] == "ip_pool"
        assert details["conflicts"][0]["object_id"] == base["id"]
        assert details["conflicts"][0]["start_address"] == "10.0.0.10"
        assert details["conflicts"][0]["end_address"] == "10.0.0.20"

    # non-overlapping adjacent is fine
    _pool(editor, n1["id"], name="adjacent", start="10.0.0.21", end="10.0.0.30")
    # cross-network overlap allowed
    _pool(editor, n2["id"], name="cross", start="10.0.0.10", end="10.0.0.20")

    # soft delete releases the range
    assert admin.delete(
        f"/api/v1/ip-pools/{base['id']}", params={"version": 1}
    ).status_code == 204
    _pool(editor, n1["id"], name="reuse", start="10.0.0.10", end="10.0.0.20")


# --- network reference --------------------------------------------------------


def test_network_resolution(role_client_factory):
    admin, _, _ = role_client_factory("ADMIN")
    editor, _, _ = role_client_factory("EDITOR")
    c1 = _cluster(admin, code="C1")
    net = _network(admin, c1["id"], name="n1")

    for bad in (None, "", "not-a-uuid", str(uuid.uuid4())):
        resp = _create_pool(editor, bad, name="x")
        assert resp.status_code == 422, (bad, resp.text)
        assert resp.json()["error"]["details"]["fields"][0]["field"] == "network"

    assert admin.delete(
        f"/api/v1/networks/{net['id']}", params={"version": 1}
    ).status_code == 204
    resp = _create_pool(editor, net["id"], name="x")
    assert resp.status_code == 422
    assert resp.json()["error"]["details"]["fields"][0]["field"] == "network"


# --- read-only / unknown fields ----------------------------------------------


def test_readonly_and_unknown_fields(role_client_factory):
    client, _, _ = role_client_factory("EDITOR")
    c1 = _cluster(client, code="C1")
    net = _network(client, c1["id"], name="n1")
    pool = _pool(client, net["id"], name="p")

    for payload in (
        {"version": 1, "network": net["id"]},
        {"version": 1, "network_id": net["id"]},
        {"version": 1, "id": str(uuid.uuid4())},
        {"version": 1, "name_key": "x"},
        {"version": 1, "address_range": "[1,2]"},
        {"version": 1, "metadata": {"a": 1}},
        {"version": 1, "unknown": 1},
        {},
    ):
        resp = client.patch(f"/api/v1/ip-pools/{pool['id']}", json=payload)
        assert resp.status_code == 422, payload

    # metadata is rejected on create too (I-6)
    resp = _create_pool(client, net["id"], name="meta", metadata={"a": 1})
    assert resp.status_code == 422


# --- PATCH --------------------------------------------------------------------


def test_patch_exclude_unset_and_non_nullable(role_client_factory):
    client, _, _ = role_client_factory("EDITOR")
    c1 = _cluster(client, code="C1")
    net = _network(client, c1["id"], name="n1")
    pool = _pool(client, net["id"], name="p", start="10.0.0.1", end="10.0.0.5", description="keep")

    updated = client.patch(
        f"/api/v1/ip-pools/{pool['id']}",
        json={"version": 1, "allocation_mode": "AUTO"},
    )
    assert updated.status_code == 200, updated.text
    body = updated.json()["ip_pool"]
    assert body["allocation_mode"] == "AUTO"
    assert body["name"] == "p" and body["start_address"] == "10.0.0.1"
    assert body["end_address"] == "10.0.0.5" and body["description"] == "keep"
    assert body["version"] == 2

    cleared = client.patch(
        f"/api/v1/ip-pools/{pool['id']}", json={"version": 2, "description": None}
    ).json()["ip_pool"]
    assert cleared["description"] is None

    for field in ("name", "start_address", "end_address", "allocation_mode"):
        resp = client.patch(
            f"/api/v1/ip-pools/{pool['id']}", json={"version": 3, field: None}
        )
        assert resp.status_code == 422, field

    # range change with overlap -> 409 range_overlap field based on changed edge
    other = _pool(client, net["id"], name="other", start="10.0.0.10", end="10.0.0.20")
    resp = client.patch(
        f"/api/v1/ip-pools/{pool['id']}",
        json={"version": 3, "end_address": "10.0.0.15"},
    )
    assert resp.status_code == 409
    assert resp.json()["error"]["details"]["field"] == "end_address"
    resp2 = client.patch(
        f"/api/v1/ip-pools/{pool['id']}",
        json={"version": 3, "start_address": "10.0.0.12", "end_address": "10.0.0.25"},
    )
    assert resp2.status_code == 409
    assert resp2.json()["error"]["details"]["field"] == "start_address"


# --- list filters / sorting / pagination -------------------------------------


def test_list_filters_sorting_pagination(role_client_factory, auth_session_factory):
    editor, _, _ = role_client_factory("EDITOR")
    admin, _, _ = role_client_factory("ADMIN")
    c1 = _cluster(editor, code="C1")
    c2 = _cluster(editor, code="C2")
    n1 = _network(editor, c1["id"], name="n1", cidr="10.0.0.0/24")
    n2 = _network(editor, c2["id"], name="n2", cidr="10.1.0.0/24")

    _pool(editor, n1["id"], name="Alpha", start="10.0.0.1", end="10.0.0.2", allocation_mode="AUTO")
    _pool(editor, n1["id"], name="beta", start="10.0.0.3", end="10.0.0.4", allocation_mode="RESERVED")
    _pool(editor, n2["id"], name="Gamma", start="10.1.0.1", end="10.1.0.2")

    listed = editor.get("/api/v1/ip-pools").json()
    assert listed["total"] == 3

    assert editor.get("/api/v1/ip-pools", params={"network_id": n1["id"]}).json()["total"] == 2
    assert editor.get("/api/v1/ip-pools", params={"allocation_mode": "AUTO"}).json()["items"][0]["name"] == "Alpha"
    assert editor.get("/api/v1/ip-pools", params={"q": "ALPH"}).json()["total"] == 1
    assert editor.get("/api/v1/ip-pools", params={"q": "   "}).json()["total"] == 3

    assert editor.get("/api/v1/ip-pools", params={"network_id": "nope"}).status_code == 422
    assert editor.get("/api/v1/ip-pools", params={"allocation_mode": "NOPE"}).status_code == 422
    assert editor.get("/api/v1/ip-pools", params={"deleted": "nope"}).status_code == 422
    assert editor.get("/api/v1/ip-pools", params={"sort": "nope"}).status_code == 422
    assert editor.get("/api/v1/ip-pools", params={"page_size": 101}).status_code == 422
    assert editor.get("/api/v1/ip-pools", params={"page": 0}).status_code == 422

    names = [
        i["name"]
        for i in editor.get(
            "/api/v1/ip-pools",
            params={"sort": "name", "order": "asc", "page_size": 100},
        ).json()["items"]
    ]
    assert names == ["Alpha", "beta", "Gamma"]

    page = editor.get(
        "/api/v1/ip-pools",
        params={"page": 1, "page_size": 2, "sort": "name", "order": "asc"},
    ).json()
    assert page["total"] == 3 and len(page["items"]) == 2

    assert editor.get("/api/v1/ip-pools", params={"deleted": "include"}).status_code == 403
    assert admin.get("/api/v1/ip-pools", params={"deleted": "include"}).status_code == 200


# --- soft delete visibility / restore rechecks --------------------------------


def test_soft_delete_visibility_and_restore_priority(role_client_factory):
    admin, _, _ = role_client_factory("ADMIN")
    editor, _, _ = role_client_factory("EDITOR")
    c1 = _cluster(admin, code="C1")
    net = _network(admin, c1["id"], name="n1", cidr="10.0.0.0/24")
    pool = _pool(admin, net["id"], name="p", start="10.0.0.1", end="10.0.0.5")

    assert admin.delete(
        f"/api/v1/ip-pools/{pool['id']}", params={"version": 1}
    ).status_code == 204
    assert editor.get(f"/api/v1/ip-pools/{pool['id']}").status_code == 404
    assert editor.get(
        f"/api/v1/ip-pools/{pool['id']}", params={"deleted": "true"}
    ).status_code == 403
    detail = admin.get(
        f"/api/v1/ip-pools/{pool['id']}", params={"deleted": "true"}
    ).json()["ip_pool"]
    assert detail["deleted_at"] is not None

    restored = admin.post(
        f"/api/v1/ip-pools/{pool['id']}/restore", params={"version": 2}
    )
    assert restored.status_code == 200, restored.text
    again = admin.post(
        f"/api/v1/ip-pools/{pool['id']}/restore", params={"version": 3}
    )
    assert again.status_code == 409
    assert again.json()["error"]["details"]["reason"] == "not_deleted"


def test_restore_dependency_deleted(role_client_factory):
    admin, _, _ = role_client_factory("ADMIN")
    c1 = _cluster(admin, code="C1")
    net = _network(admin, c1["id"], name="n1", cidr="10.0.0.0/24")

    pool = _pool(admin, net["id"], name="dep", start="10.0.0.1", end="10.0.0.5")
    assert admin.delete(
        f"/api/v1/ip-pools/{pool['id']}", params={"version": 1}
    ).status_code == 204
    assert admin.delete(
        f"/api/v1/networks/{net['id']}", params={"version": 1}
    ).status_code == 204
    resp = admin.post(
        f"/api/v1/ip-pools/{pool['id']}/restore", params={"version": 2}
    )
    assert resp.status_code == 409
    assert resp.json()["error"]["details"]["reason"] == "dependency_deleted"
    assert resp.json()["error"]["details"]["conflicts"] == [
        {"object_type": "network", "object_id": net["id"]}
    ]


def test_restore_cidr_recheck(role_client_factory):
    """A Network cidr shrink makes a soft-deleted pool out of range -> 422."""
    admin, _, _ = role_client_factory("ADMIN")
    c1 = _cluster(admin, code="C1")
    net = _network(admin, c1["id"], name="n1", cidr="10.0.0.0/24")
    pool = _pool(admin, net["id"], name="p", start="10.0.0.1", end="10.0.0.5")
    assert admin.delete(
        f"/api/v1/ip-pools/{pool['id']}", params={"version": 1}
    ).status_code == 204
    # No undeleted pool remains, so the Network cidr change is allowed.
    patched = admin.patch(
        f"/api/v1/networks/{net['id']}",
        json={"version": 1, "cidr": "10.0.0.9/32", "gateway": None},
    )
    assert patched.status_code == 200, patched.text
    resp = admin.post(
        f"/api/v1/ip-pools/{pool['id']}/restore", params={"version": 2}
    )
    assert resp.status_code == 422, resp.text
    assert resp.json()["error"]["details"]["fields"][0]["field"] in (
        "start_address",
        "end_address",
    )


def test_restore_overlap_recheck(role_client_factory):
    admin, _, _ = role_client_factory("ADMIN")
    c1 = _cluster(admin, code="C1")
    net = _network(admin, c1["id"], name="n1", cidr="10.0.0.0/24")
    pool = _pool(admin, net["id"], name="p", start="10.0.0.1", end="10.0.0.5")
    assert admin.delete(
        f"/api/v1/ip-pools/{pool['id']}", params={"version": 1}
    ).status_code == 204
    _pool(admin, net["id"], name="other", start="10.0.0.3", end="10.0.0.7")
    resp = admin.post(
        f"/api/v1/ip-pools/{pool['id']}/restore", params={"version": 2}
    )
    assert resp.status_code == 409
    assert resp.json()["error"]["details"]["reason"] == "range_overlap"


# --- occupancy (stub provider) ------------------------------------------------


def test_occupancy_reserved_create_and_patch(role_client_factory, occupancy_stub):
    client, _, _ = role_client_factory("EDITOR")
    c1 = _cluster(client, code="C1")
    net = _network(client, c1["id"], name="n1", cidr="10.0.0.0/24")

    items = [_conflict_item(address="10.0.0.5", bound=True), _conflict_item("10.0.0.6")]
    stub = occupancy_stub(total=2, items=items)

    # POST RESERVED over occupied addresses -> 409 field allocation_mode
    resp = _create_pool(
        client,
        net["id"],
        name="reserved",
        start="10.0.0.1",
        end="10.0.0.9",
        allocation_mode="RESERVED",
    )
    assert resp.status_code == 409, resp.text
    details = resp.json()["error"]["details"]
    assert details["reason"] == "address_in_use"
    assert details["field"] == "allocation_mode"
    assert details["conflict_count"] == 2
    assert len(details["conflicts"]) == 2
    assert details["conflicts"][0]["object_type"] == "ip_address"
    assert details["conflicts"][0]["bound"] is True
    assert details["conflicts_truncated"] is False
    assert stub.calls and stub.calls[0][0] == "10.0.0.1"

    # Non-RESERVED create never consults occupancy
    stub.calls.clear()
    _pool(client, net["id"], name="auto", start="10.0.0.1", end="10.0.0.4", allocation_mode="AUTO")
    assert stub.calls == []

    # MANUAL -> RESERVED on PATCH -> field allocation_mode
    pool = _pool(client, net["id"], name="p", start="10.0.0.5", end="10.0.0.9")
    resp = client.patch(
        f"/api/v1/ip-pools/{pool['id']}",
        json={"version": 1, "allocation_mode": "RESERVED"},
    )
    assert resp.status_code == 409
    assert resp.json()["error"]["details"]["field"] == "allocation_mode"


def test_occupancy_patch_expansion_field_rules(role_client_factory, occupancy_stub):
    client, _, _ = role_client_factory("EDITOR")
    c1 = _cluster(client, code="C1")
    net = _network(client, c1["id"], name="n1", cidr="10.0.0.0/24")

    pool = _pool(
        client,
        net["id"],
        name="p",
        start="10.0.0.10",
        end="10.0.0.20",
        allocation_mode="RESERVED",
    )

    # RESERVED, expand start -> field start_address
    stub = occupancy_stub(total=1, items=[_conflict_item("10.0.0.5")])
    resp = client.patch(
        f"/api/v1/ip-pools/{pool['id']}", json={"version": 1, "start_address": "10.0.0.5"}
    )
    assert resp.status_code == 409
    assert resp.json()["error"]["details"]["field"] == "start_address"

    # RESERVED, expand end only -> field end_address
    stub.calls.clear()
    resp = client.patch(
        f"/api/v1/ip-pools/{pool['id']}", json={"version": 1, "end_address": "10.0.0.30"}
    )
    assert resp.status_code == 409
    assert resp.json()["error"]["details"]["field"] == "end_address"

    # RESERVED, shrink -> no occupancy check
    stub.calls.clear()
    ok = client.patch(
        f"/api/v1/ip-pools/{pool['id']}", json={"version": 1, "end_address": "10.0.0.30", "start_address": "10.0.0.15"}
    )
    # start moves forward and end moves forward: range [15,30] vs [10,20]: start
    # expands? 15 > 10 (no), end 30 > 20 (yes) -> end_address check triggers.
    # Use a pure shrink below instead.
    assert ok.status_code == 409

    stub.calls.clear()
    shrink = client.patch(
        f"/api/v1/ip-pools/{pool['id']}", json={"version": 1, "end_address": "10.0.0.15"}
    )
    assert shrink.status_code == 200, shrink.text
    assert stub.calls == []


def test_occupancy_truncation(role_client_factory, occupancy_stub, monkeypatch):
    client, _, _ = role_client_factory("EDITOR")
    c1 = _cluster(client, code="C1")
    net = _network(client, c1["id"], name="n1", cidr="10.0.0.0/24")
    items = [_conflict_item(f"10.0.0.{i}") for i in range(1, 6)]
    occupancy_stub(total=5, items=items)
    monkeypatch.setattr(
        ip_pool_service,
        "get_settings",
        lambda: SimpleNamespace(conflict_preview_limit=2),
    )
    resp = _create_pool(
        client,
        net["id"],
        name="big",
        start="10.0.0.1",
        end="10.0.0.9",
        allocation_mode="RESERVED",
    )
    assert resp.status_code == 409
    details = resp.json()["error"]["details"]
    assert details["conflict_count"] == 5
    assert len(details["conflicts"]) == 2
    assert details["conflicts_truncated"] is True


def test_network_gateway_occupancy_hook(role_client_factory, occupancy_stub):
    client, _, _ = role_client_factory("EDITOR")
    c1 = _cluster(client, code="C1")
    net = _network(client, c1["id"], name="n1", cidr="10.0.0.0/24")

    occupancy_stub(total=1, items=[_conflict_item("10.0.0.1", bound=False)])
    resp = client.patch(
        f"/api/v1/networks/{net['id']}", json={"version": 1, "gateway": "10.0.0.1"}
    )
    assert resp.status_code == 409, resp.text
    details = resp.json()["error"]["details"]
    assert details["reason"] == "address_in_use"
    assert details["field"] == "gateway"
    assert details["conflict_count"] == 1

    # Empty provider never triggers
    occupancy_stub(total=0, items=[])
    ok = client.patch(
        f"/api/v1/networks/{net['id']}", json={"version": 1, "gateway": "10.0.0.1"}
    )
    assert ok.status_code == 200, ok.text


# --- audit / activity ---------------------------------------------------------


def test_audit_four_actions_and_activity(role_client_factory, auth_session_factory):
    admin, _, _ = role_client_factory("ADMIN")
    viewer, _, _ = role_client_factory("VIEWER")
    c1 = _cluster(admin, code="C1")
    net = _network(admin, c1["id"], name="n1", cidr="10.0.0.0/24")
    pool = _pool(admin, net["id"], name="aud", start="10.0.0.1", end="10.0.0.5")
    assert admin.patch(
        f"/api/v1/ip-pools/{pool['id']}", json={"version": 1, "allocation_mode": "AUTO"}
    ).status_code == 200
    assert admin.delete(
        f"/api/v1/ip-pools/{pool['id']}", params={"version": 2}
    ).status_code == 204
    assert admin.post(
        f"/api/v1/ip-pools/{pool['id']}/restore", params={"version": 3}
    ).status_code == 200

    with auth_session_factory() as session:
        rows = (
            session.execute(
                select(AuditLog)
                .where(AuditLog.object_id == uuid.UUID(pool["id"]))
                .order_by(AuditLog.created_at, AuditLog.id)
            )
            .scalars()
            .all()
        )
        assert {r.action for r in rows} == {"CREATE", "UPDATE", "DELETE", "RESTORE"}
        assert all(r.object_type == "ip_pool" for r in rows)
        update = next(r for r in rows if r.action == "UPDATE")
        assert set(update.before_data) == {
            "network_id",
            "name",
            "start_address",
            "end_address",
            "allocation_mode",
            "description",
        }
        assert update.before_data["allocation_mode"] == "MANUAL"
        assert update.after_data["allocation_mode"] == "AUTO"
        assert next(r for r in rows if r.action == "DELETE").after_data is None
        expected = [r.action for r in rows]

    for client in (viewer, admin):
        activity = client.get(f"/api/v1/ip-pools/{pool['id']}/activity")
        assert activity.status_code == 200, activity.text
        assert [i["action"] for i in activity.json()["items"]] == expected


def test_audit_rolls_back_with_the_transaction(
    auth_session_factory, make_user, monkeypatch
):
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
    with auth_session_factory() as session:
        pool = ip_pool_service.create_ip_pool(
            session,
            operator,
            network=str(net_id),
            name="rbpool",
            start_address="10.0.0.1",
            end_address="10.0.0.5",
        )
        pool_id = pool.id

    original = ip_pool_service.audit.record

    def corrupt(*args, **kwargs):
        row = original(*args, **kwargs)
        row.action = "BOGUS"  # violates the audit_logs action CHECK
        return row

    monkeypatch.setattr(ip_pool_service.audit, "record", corrupt)
    with auth_session_factory() as session:
        with pytest.raises(Exception):
            ip_pool_service.update_ip_pool(
                session,
                operator,
                pool_id,
                expected_version=1,
                changes={"allocation_mode": "AUTO"},
            )
        session.rollback()

    with auth_session_factory() as session:
        assert _row(session, pool_id)["allocation_mode"] == "MANUAL"
        assert (
            session.execute(select(AuditLog).where(AuditLog.action == "BOGUS"))
            .scalars()
            .all()
            == []
        )


# --- permissions --------------------------------------------------------------


def test_permission_matrix(role_client_factory, auth_app):
    admin, _, _ = role_client_factory("ADMIN")
    editor, _, _ = role_client_factory("EDITOR")
    viewer, _, _ = role_client_factory("VIEWER")
    c1 = _cluster(admin, code="C1")
    net = _network(admin, c1["id"], name="n1", cidr="10.0.0.0/24")
    pool = _pool(admin, net["id"], name="p", start="10.0.0.1", end="10.0.0.5")

    assert viewer.get(f"/api/v1/ip-pools/{pool['id']}").status_code == 200
    assert viewer.get(f"/api/v1/ip-pools/{pool['id']}/activity").status_code == 200
    assert viewer.post(
        "/api/v1/ip-pools",
        json={"network": net["id"], "name": "v", "start_address": "10.0.0.6", "end_address": "10.0.0.7"},
    ).status_code == 403
    assert viewer.patch(
        f"/api/v1/ip-pools/{pool['id']}", json={"version": 1, "allocation_mode": "AUTO"}
    ).status_code == 403
    assert viewer.delete(
        f"/api/v1/ip-pools/{pool['id']}", params={"version": 1}
    ).status_code == 403

    assert editor.patch(
        f"/api/v1/ip-pools/{pool['id']}", json={"version": 1, "allocation_mode": "AUTO"}
    ).status_code == 200
    assert editor.delete(
        f"/api/v1/ip-pools/{pool['id']}", params={"version": 2}
    ).status_code == 403
    assert admin.delete(
        f"/api/v1/ip-pools/{pool['id']}", params={"version": 2}
    ).status_code == 204
    assert admin.post(
        f"/api/v1/ip-pools/{pool['id']}/restore", params={"version": 3}
    ).status_code == 200

    with TestClient(auth_app) as anon:
        assert anon.get("/api/v1/ip-pools").status_code == 401


# --- optimistic lock ----------------------------------------------------------


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
    with auth_session_factory() as session:
        pool = ip_pool_service.create_ip_pool(
            session,
            operator,
            network=str(net_id),
            name="lkpool",
            start_address="10.0.0.1",
            end_address="10.0.0.5",
        )
        pool_id = pool.id

    first = auth_session_factory()
    second = auth_session_factory()
    try:
        ip_pool_service.update_ip_pool(
            first, operator, pool_id, expected_version=1, changes={"allocation_mode": "AUTO"}
        )
        with pytest.raises(VersionConflict) as exc:
            ip_pool_service.update_ip_pool(
                second,
                operator,
                pool_id,
                expected_version=1,
                changes={"description": "x"},
            )
        assert exc.value.details == {"current_version": 2}
        second.rollback()
    finally:
        first.close()
        second.close()

    with auth_session_factory() as session:
        row = _row(session, pool_id)
        assert row["allocation_mode"] == "AUTO" and row["description"] is None


# --- reference checker --------------------------------------------------------


def test_reference_checker_blocks_network_change_and_delete(role_client_factory):
    admin, _, _ = role_client_factory("ADMIN")
    c1 = _cluster(admin, code="RC1")
    c2 = _cluster(admin, code="RC2")
    net = _network(admin, c1["id"], name="refnet", cidr="10.0.0.0/24")
    pool = _pool(admin, net["id"], name="refpool", start="10.0.0.1", end="10.0.0.5")

    # PATCH cidr -> 409 reference_exists with an ip_pool descriptor
    resp = admin.patch(
        f"/api/v1/networks/{net['id']}",
        json={"version": 1, "cidr": "10.5.0.0/24", "gateway": None},
    )
    assert resp.status_code == 409, resp.text
    details = resp.json()["error"]["details"]
    assert details["reason"] == "reference_exists"
    assert details["references"][0]["object_type"] == "ip_pool"
    assert details["references"][0]["object_id"] == pool["id"]
    assert details["references"][0]["label"] == "refpool"

    # PATCH cluster -> 409
    resp = admin.patch(
        f"/api/v1/networks/{net['id']}", json={"version": 1, "cluster": c2["id"]}
    )
    assert resp.status_code == 409
    assert resp.json()["error"]["details"]["reason"] == "reference_exists"

    # DELETE -> 409; the network stays live
    resp = admin.delete(f"/api/v1/networks/{net['id']}", params={"version": 1})
    assert resp.status_code == 409
    assert admin.get(f"/api/v1/networks/{net['id']}").status_code == 200

    # A non-location change is not blocked
    assert admin.patch(
        f"/api/v1/networks/{net['id']}", json={"version": 1, "status": "INACTIVE"}
    ).status_code == 200

    # Soft-deleting the pool releases the block
    assert admin.delete(
        f"/api/v1/ip-pools/{pool['id']}", params={"version": 1}
    ).status_code == 204
    assert admin.delete(
        f"/api/v1/networks/{net['id']}", params={"version": 2}
    ).status_code == 204


def test_pool_delete_registers_no_reference_checker(
    role_client_factory, auth_session_factory
):
    """A Pool soft delete never consults IP-allocation sources (DR-108)."""
    admin, _, _ = role_client_factory("ADMIN")
    c1 = _cluster(admin, code="C1")
    net = _network(admin, c1["id"], name="n1")
    pool = _pool(admin, net["id"], name="p")
    assert admin.delete(
        f"/api/v1/ip-pools/{pool['id']}", params={"version": 1}
    ).status_code == 204


# --- validation order ---------------------------------------------------------


def test_validation_order(role_client_factory):
    editor, _, _ = role_client_factory("EDITOR")
    c1 = _cluster(editor, code="C1")
    net = _network(editor, c1["id"], name="n1", cidr="10.0.0.0/24")
    _pool(editor, net["id"], name="taken", start="10.0.0.1", end="10.0.0.5")

    # invalid network beats invalid address
    resp = _create_pool(editor, str(uuid.uuid4()), name="x", start="bad", end="worse")
    assert resp.status_code == 422
    assert resp.json()["error"]["details"]["fields"][0]["field"] == "network"

    # duplicate name but invalid address: Contract §6.2 checks address format
    # before same-Network name uniqueness, so the 422 wins.
    resp = _create_pool(editor, net["id"], name="taken", start="bad", end="worse")
    assert resp.status_code == 422
    assert resp.json()["error"]["details"]["fields"][0]["field"] == "start_address"

    pool = _pool(editor, net["id"], name="order", start="10.0.0.10", end="10.0.0.20")
    _pool(editor, net["id"], name="other", start="10.0.0.30", end="10.0.0.40")
    # version beats name uniqueness
    resp = editor.patch(
        f"/api/v1/ip-pools/{pool['id']}", json={"version": 99, "name": "other"}
    )
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "VERSION_CONFLICT"