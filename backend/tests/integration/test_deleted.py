"""F015 deleted-object aggregate integration tests (A12/A13/A14, I-8/I-12, B12-B14/B22).

Real PostgreSQL only; every object is created and soft-deleted through the real
domain APIs.
"""

from __future__ import annotations

import uuid

from sqlalchemy import text

from integration.f015_helpers import (  # noqa: F401
    DELETED_TYPES,
    build_deleted_set,
    create_cluster,
    role_client_factory,
)


def test_deleted_permissions(api_client, role_client_factory):  # noqa: F811
    anon = api_client.get("/api/v1/deleted")
    assert anon.status_code == 401
    assert anon.json()["error"]["code"] == "AUTH_REQUIRED"

    # 401 precedes validation.
    assert (
        api_client.get("/api/v1/deleted", params={"object_type": "bogus"}).status_code
        == 401
    )

    viewer, _, _ = role_client_factory("VIEWER")
    editor, _, _ = role_client_factory("EDITOR")
    admin, _, _ = role_client_factory("ADMIN")

    for client in (viewer, editor):
        resp = client.get("/api/v1/deleted")
        assert resp.status_code == 403, resp.text
        assert resp.json()["error"]["details"] == {"reason": "permission"}

    assert admin.get("/api/v1/deleted").status_code == 200


def test_aggregate_covers_eight_types(role_client_factory):  # noqa: F811
    admin, _, _ = role_client_factory("ADMIN")
    objects = build_deleted_set(admin)

    body = admin.get("/api/v1/deleted", params={"page_size": 100}).json()
    assert body["total"] == 8
    items = {item["object_type"]: item for item in body["items"]}
    assert set(items) == set(DELETED_TYPES)

    for object_type, original in objects.items():
        item = items[object_type]
        assert item["object_id"] == original["id"]
        assert item["version"] == 2  # create (1) -> soft delete (2)
        assert item["deleted_at"].endswith("+00:00")

    assert items["cluster"]["label"] == "DELC"
    assert items["resource"]["label"] == "del-host1"
    assert items["interface"]["label"] == "eth-del"
    assert items["network"]["label"] == "net-del"
    assert items["ip_pool"]["label"] == "pool-del"
    assert items["ip_address"]["label"] == "10.20.0.5"
    assert items["service"]["label"] == "svc-del"
    assert items["service_endpoint"]["label"] == "TCP:2222"

    assert items["cluster"]["cluster"] is None
    for object_type, expected_code in (
        ("resource", "KEEPC1"),
        ("interface", "KEEPC2"),
        ("network", "KEEPC3"),
        ("ip_pool", "KEEPC4"),
        ("ip_address", "KEEPC5"),
        ("service", "KEEPC6"),
        ("service_endpoint", "KEEPC7"),
    ):
        cluster = items[object_type]["cluster"]
        assert cluster is not None
        assert cluster["code"] == expected_code
        assert cluster["name"] == "Cluster"
        assert cluster["id"]


def test_filter_pagination_and_validation(role_client_factory):  # noqa: F811
    admin, _, _ = role_client_factory("ADMIN")
    build_deleted_set(admin)

    only_networks = admin.get(
        "/api/v1/deleted", params={"object_type": "network", "page_size": 100}
    ).json()
    assert only_networks["total"] == 1
    assert only_networks["items"][0]["object_type"] == "network"

    pages = []
    for page in (1, 2, 3):
        chunk = admin.get(
            "/api/v1/deleted", params={"page_size": 3, "page": page}
        ).json()
        assert chunk["total"] == 8
        pages.extend(chunk["items"])
    assert len(pages) == 8
    assert len({item["object_id"] for item in pages}) == 8
    assert sum(1 for item in pages if item["object_type"] == "service_endpoint") == 1

    for params in (
        {"object_type": "user"},  # user is not a deletable type
        {"object_type": "bogus"},
        {"sort": "id"},
        {"order": "sideways"},
        {"page": 0},
        {"page_size": 0},
        {"page_size": 101},
    ):
        resp = admin.get("/api/v1/deleted", params=params)
        assert resp.status_code == 422, (params, resp.text)
        assert resp.json()["error"]["code"] == "VALIDATION_ERROR"


def test_same_deleted_at_tie_break(role_client_factory, auth_session_factory):  # noqa: F811
    admin, _, _ = role_client_factory("ADMIN")
    objects = build_deleted_set(admin)

    instant = "2026-05-01T00:00:00+00:00"
    targets = {
        "clusters": objects["cluster"]["id"],
        "resources": objects["resource"]["id"],
        "interfaces": objects["interface"]["id"],
        "networks": objects["network"]["id"],
        "ip_pools": objects["ip_pool"]["id"],
        "ip_addresses": objects["ip_address"]["id"],
        "services": objects["service"]["id"],
        "service_endpoints": objects["service_endpoint"]["id"],
    }
    with auth_session_factory() as session:
        for table, object_id in targets.items():
            session.execute(
                text(f"UPDATE {table} SET deleted_at = :ts WHERE id = :id"),
                {"ts": instant, "id": object_id},
            )
        session.commit()

    body = admin.get(
        "/api/v1/deleted",
        params={"sort": "deleted_at", "order": "asc", "page_size": 100},
    ).json()
    types = [item["object_type"] for item in body["items"]]
    assert types == sorted(types)
    assert len(types) == 8


def test_read_only_and_stable(role_client_factory, auth_session_factory):  # noqa: F811
    admin, _, _ = role_client_factory("ADMIN")
    build_deleted_set(admin)

    with auth_session_factory() as session:
        before = session.execute(
            text("SELECT count(*) FROM clusters WHERE deleted_at IS NOT NULL")
        ).scalar_one()

    first = admin.get("/api/v1/deleted", params={"page_size": 100})
    second = admin.get("/api/v1/deleted", params={"page_size": 100})
    assert first.status_code == second.status_code == 200
    assert first.json() == second.json()

    with auth_session_factory() as session:
        after = session.execute(
            text("SELECT count(*) FROM clusters WHERE deleted_at IS NOT NULL")
        ).scalar_one()
    assert before == after


def test_version_routes_to_domain_restore(role_client_factory):  # noqa: F811
    admin, _, _ = role_client_factory("ADMIN")
    objects = build_deleted_set(admin)

    item = next(
        entry
        for entry in admin.get(
            "/api/v1/deleted", params={"object_type": "network", "page_size": 100}
        ).json()["items"]
    )
    resp = admin.post(
        f"/api/v1/networks/{item['object_id']}/restore?version={item['version']}"
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["network"]["deleted_at"] is None

    remaining = admin.get("/api/v1/deleted", params={"page_size": 100}).json()
    assert remaining["total"] == 7
    assert all(entry["object_type"] != "network" for entry in remaining["items"])
    assert objects["network"]["id"] == item["object_id"]


def test_no_unified_write_endpoint(role_client_factory):  # noqa: F811
    admin, _, _ = role_client_factory("ADMIN")
    for method in ("post", "put", "patch", "delete"):
        resp = getattr(admin, method)("/api/v1/deleted")
        assert resp.status_code in (404, 405), (method, resp.status_code)
    assert admin.post(f"/api/v1/deleted/{uuid.uuid4()}").status_code in (404, 405)