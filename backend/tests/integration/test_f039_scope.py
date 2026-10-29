"""F039 A3 — §23.2 scope and zero-authorization behaviour of Dashboard (T88).

Real PostgreSQL, **real access scope** (``pytest.mark.real_scope``): without the
marker the suite would inject the test-only unrestricted shim (``tests/
conftest.py``, F030 §9.1) and prove nothing about §23.2. The marker requirement
is enforced by ``test_f030_test_harness.py``.

Scope behaviour must be unchanged by the F039 batching (``load_capacity_context``
receives only the rows the scoped page query returned, and the three batch
statements are keyed by those Networks' ids), so the count/total/row assertions
below are the pre-existing Contract §3 expectations.
"""

from __future__ import annotations

import pytest

from integration.f015_helpers import (  # noqa: F401
    create_cluster,
    create_ip,
    create_network,
    role_client_factory,
)

pytestmark = pytest.mark.real_scope

COUNT_KEYS = ("clusters", "resources", "bare_metal", "virtual_machines", "networks")


def _grant(admin, user_id, cluster_id) -> None:
    response = admin.post(
        f"/api/v1/users/{user_id}/cluster-authorizations",
        json={"cluster_id": str(cluster_id)},
    )
    assert response.status_code == 201, response.text


def _auto_pool(client, network_id, name, start, end):
    """Create an AUTO pool (``f015_helpers.create_pool`` has no mode arg)."""
    response = client.post(
        "/api/v1/ip-pools",
        json={
            "network": network_id,
            "name": name,
            "start_address": start,
            "end_address": end,
            "allocation_mode": "AUTO",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["ip_pool"]


def _seed(client) -> dict[str, dict[str, object]]:
    """Three Clusters (A/B/C), each with one Network carrying capacity data."""
    seeded: dict[str, dict[str, object]] = {}
    for index, code in enumerate(("A", "B", "C")):
        cluster = create_cluster(client, code=code, name=f"Cluster {code}")
        network = create_network(
            client,
            cluster=cluster["code"],
            name=f"scope-f39-{code.lower()}",
            cidr=f"10.90.{index}.0/24",
        )
        _auto_pool(
            client, network["id"], name=f"f39-{code.lower()}",
            start=f"10.90.{index}.100", end=f"10.90.{index}.110",
        )
        create_ip(client, network["id"], f"10.90.{index}.100")
        seeded[code] = {"cluster": cluster, "network": network}
    return seeded


def test_a3_viewer_sees_only_authorized_clusters(role_client_factory):
    """Non-ADMIN: only granted Clusters/Networks, no size leak for C (A3/T88)."""
    admin, _, _ = role_client_factory("ADMIN", username="f039.b.admin")
    seeded = _seed(admin)
    viewer, viewer_user, _ = role_client_factory("VIEWER", username="f039.b.viewer")
    _grant(admin, viewer_user.id, seeded["A"]["cluster"]["id"])
    _grant(admin, viewer_user.id, seeded["B"]["cluster"]["id"])

    response = viewer.get("/api/v1/dashboard", params={"page_size": 100})
    assert response.status_code == 200, response.text
    body = response.json()

    assert body["counts"] == {
        "clusters": 2,
        "resources": 0,
        "bare_metal": 0,
        "virtual_machines": 0,
        "networks": 2,
    }
    assert body["networks"]["total"] == 2
    assert {row["network"]["id"] for row in body["networks"]["items"]} == {
        seeded["A"]["network"]["id"],
        seeded["B"]["network"]["id"],
    }
    # Capacity of the visible rows is still intact (batching is scope-neutral).
    for row in body["networks"]["items"]:
        assert row["capacity"]["occupied"] == 1
        assert len(row["auto_pools"]) == 1
        assert row["auto_pools"][0]["occupied"] == 1
    # Cluster C never leaks (id or name) in any form.
    assert seeded["C"]["cluster"]["id"] not in response.text
    assert seeded["C"]["network"]["id"] not in response.text
    assert "scope-f39-c" not in response.text


def test_a3_zero_authorization_returns_empty(role_client_factory):
    """User with no grants: all counts 0 and an empty list (A3/T88)."""
    admin, _, _ = role_client_factory("ADMIN", username="f039.b.admin0")
    _seed(admin)
    unprivileged, _, _ = role_client_factory("VIEWER", username="f039.b.none")

    response = unprivileged.get("/api/v1/dashboard", params={"page_size": 100})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["counts"] == {key: 0 for key in COUNT_KEYS}
    assert body["networks"]["items"] == []
    assert body["networks"]["total"] == 0


def test_a3_admin_is_unrestricted(role_client_factory):
    """ADMIN sees every Cluster, including ungranted ones (A3)."""
    admin, _, _ = role_client_factory("ADMIN", username="f039.b.adminall")
    seeded = _seed(admin)

    body = admin.get("/api/v1/dashboard", params={"page_size": 100}).json()
    assert body["counts"]["clusters"] == 3
    assert body["counts"]["networks"] == 3
    assert body["networks"]["total"] == 3
    assert {row["network"]["id"] for row in body["networks"]["items"]} == {
        seeded[code]["network"]["id"] for code in ("A", "B", "C")
    }
