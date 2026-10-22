"""F028 phase-1 integration acceptance for cluster access control (real HTTP).

Runs only when ``F016_ACCEPTANCE=1`` (same guarded driver as F016), against the
equivalent real stack: Nginx -> FastAPI -> PostgreSQL. This module does not use
TestClient, mocks or SQLite. It provides F028 evidence for T85-T99; the exhaustive
per-domain matrix remains in the F026/F027 suites.
"""

from __future__ import annotations

import os
import uuid

import httpx
import pytest

from integration.f016_helpers import (  # noqa: F401
    BM_HEADERS,
    VALIDATE_PATH,
    WRITE_PATH,
    Api,
    acceptance_enabled,
    admin_credentials,
    bm_row,
    bind_ip,
    create_cluster,
    create_endpoint,
    create_interface,
    create_ip,
    create_network,
    create_pool,
    create_resource,
    create_service,
    csv_bytes,
    error_code,
    import_request,
    make_role_api,
    ok,
    run_suffix,
)

pytestmark = pytest.mark.skipif(
    not acceptance_enabled(), reason="F028 acceptance requires F016_ACCEPTANCE=1"
)


def _admin() -> Api:
    return Api(admin_credentials())


def _grant(admin: Api, user_id: str, cluster_id: str) -> dict:
    return ok(
        admin.post(
            f"/api/v1/users/{user_id}/cluster-authorizations",
            json={"cluster_id": cluster_id},
        ),
        201,
    )["cluster_authorization"]




def _role_api(admin: Api, role: str, suffix: str) -> tuple[Api, dict]:
    username = f"f028-{role.lower()}-{suffix}"
    password = "f028-pass-123"
    user = ok(admin.post("/api/v1/users", json={"username": username, "password": password, "role": role}), 201)["user"]
    return Api((username, password)), user


def _objects(admin: Api, code: str, host: str, cidr: str) -> dict:
    cluster = create_cluster(admin, code, f"F028 {code}")
    resource = create_resource(admin, code, host)
    iface = create_interface(admin, resource["id"], f"{host}-eth0")
    network = create_network(admin, code, f"{host}-net", cidr)
    prefix = cidr.split("/")[0].rsplit(".", 1)[0]
    pool = create_pool(admin, network["id"], f"{host}-pool", prefix + ".10", prefix + ".20")
    ip = create_ip(admin, network["id"], prefix + ".5")
    ip = bind_ip(admin, ip, iface["id"])
    service = create_service(admin, resource["id"], f"{host}-svc")
    endpoint = create_endpoint(admin, service["id"], ip["id"], port=2200)
    return {
        "cluster": cluster,
        "resource": resource,
        "interface": iface,
        "network": network,
        "ip_pool": pool,
        "ip_address": ip,
        "service": service,
        "service_endpoint": endpoint,
    }


def _ids(resp: httpx.Response) -> set[str]:
    body = ok(resp, 200)
    return {item["id"] for item in body["items"]}


def test_t85_t88_scope_lists_details_search_dashboard() -> None:
    admin = _admin()
    suffix = run_suffix()
    a = _objects(admin, f"F28A{suffix}", f"f28-a-{suffix}", "10.81.0.0/24")
    b = _objects(admin, f"F28B{suffix}", f"f28-b-{suffix}", "10.82.0.0/24")
    c = _objects(admin, f"F28C{suffix}", f"f28-c-{suffix}", "10.83.0.0/24")
    viewer, viewer_row = _role_api(admin, "VIEWER", suffix)
    _grant(admin, viewer_row["id"], a["cluster"]["id"])
    _grant(admin, viewer_row["id"], b["cluster"]["id"])

    for path, key in (
        ("/api/v1/clusters", "cluster"),
        ("/api/v1/resources", "resource"),
        ("/api/v1/networks", "network"),
        ("/api/v1/ip-addresses", "ip_address"),
        ("/api/v1/ip-pools", "ip_pool"),
        ("/api/v1/interfaces", "interface"),
        ("/api/v1/services", "service"),
        ("/api/v1/service-endpoints", "service_endpoint"),
    ):
        visible = _ids(viewer.get(path, params={"page_size": 100}))
        assert a[key]["id"] in visible and b[key]["id"] in visible, path
        assert c[key]["id"] not in visible, path
        detail = viewer.get(f"{path}/{c[key]['id']}")
        assert detail.status_code == 404, (path, detail.status_code, detail.text)
        assert c[key]["id"] not in detail.text

    search = ok(viewer.get("/api/v1/search", params={"q": f"f28-c-{suffix}", "page_size": 100}), 200)
    assert search["total"] == 0
    search_related = ok(
        viewer.get("/api/v1/search", params={"q": f"f28-b-{suffix}", "type": "resource", "page_size": 100}),
        200,
    )
    assert search_related["total"] >= 1

    dash = ok(viewer.get("/api/v1/dashboard", params={"page_size": 100}), 200)
    assert dash["counts"]["clusters"] == len({a["cluster"]["id"], b["cluster"]["id"]})
    assert dash["networks"]["total"] == 2
    assert c["network"]["id"] not in {n["network"]["id"] for n in dash["networks"]["items"]}

    zero, _zero_row = _role_api(admin, "VIEWER", suffix + "z")
    assert _ids(zero.get("/api/v1/resources")) == set()
    assert ok(zero.get("/api/v1/dashboard"), 200)["counts"]["clusters"] == 0
    assert zero.get(f"/api/v1/resources/{a['resource']['id']}").status_code == 404

    admin.close(); viewer.close(); zero.close()


def test_t86_t89_writes_and_import_are_scoped_without_residue() -> None:
    admin = _admin()
    suffix = run_suffix()
    a = _objects(admin, f"F28D{suffix}", f"f28-d-{suffix}", "10.84.0.0/24")
    c = _objects(admin, f"F28E{suffix}", f"f28-e-{suffix}", "10.85.0.0/24")
    editor, editor_row = _role_api(admin, "EDITOR", suffix)
    _grant(admin, editor_row["id"], a["cluster"]["id"])

    patch = editor.patch(
        f"/api/v1/resources/{c['resource']['id']}",
        json={"version": c["resource"]["version"], "description": "x"},
    )
    assert patch.status_code == 404
    delete = editor.delete(f"/api/v1/resources/{c['resource']['id']}?version={c['resource']['version']}")
    assert delete.status_code in (403, 404)
    create = editor.post(
        "/api/v1/resources",
        json={"cluster": c["cluster"]["code"], "hostname": f"f28-x-{suffix}", "resource_type": "BARE_METAL"},
    )
    assert create.status_code == 422
    assert create.json()["error"]["code"] == "VALIDATION_ERROR"

    before = ok(admin.get("/api/v1/resources", params={"page_size": 100}), 200)["total"]
    audit_before = ok(admin.get("/api/v1/audit", params={"page_size": 100}), 200)["total"]
    data = csv_bytes(BM_HEADERS, [bm_row(c["cluster"]["code"], f"f28-import-{suffix}")])
    pre = import_request(editor, VALIDATE_PATH, data)
    assert pre.status_code == 200, pre.text
    preview = pre.json()
    assert preview["error_count"] >= 1 and preview["importable_rows"] == 0
    rows = preview["errors"]
    assert rows and c["cluster"]["code"] not in str(rows)
    write = import_request(editor, WRITE_PATH, data)
    assert write.status_code == 422
    after = ok(admin.get("/api/v1/resources", params={"page_size": 100}), 200)["total"]
    audit_after = ok(admin.get("/api/v1/audit", params={"page_size": 100}), 200)["total"]
    assert after == before
    assert audit_after == audit_before

    admin.close(); editor.close()


def test_t91_t94_api_key_and_revoke_next_request() -> None:
    admin = _admin()
    suffix = run_suffix()
    a = _objects(admin, f"F28F{suffix}", f"f28-f-{suffix}", "10.86.0.0/24")
    b = _objects(admin, f"F28G{suffix}", f"f28-g-{suffix}", "10.87.0.0/24")
    viewer, row = _role_api(admin, "VIEWER", suffix)
    ga = _grant(admin, row["id"], a["cluster"]["id"])
    _grant(admin, row["id"], b["cluster"]["id"])
    key = ok(admin.post("/api/v1/api-keys", json={"user_id": row["id"], "label": "f028", "validity_days": 90}), 201)["api_key"]
    bearer = Api()
    bearer.client.headers["Authorization"] = f"Bearer {key['plaintext']}"
    assert _ids(bearer.get("/api/v1/resources", params={"page_size": 100})) == {a["resource"]["id"], b["resource"]["id"]}
    ok(admin.post(f"/api/v1/cluster-authorizations/{ga['id']}/revoke"), 200)
    assert _ids(bearer.get("/api/v1/resources", params={"page_size": 100})) == {b["resource"]["id"]}
    assert bearer.get(f"/api/v1/resources/{a['resource']['id']}").status_code == 404

    assert viewer.get(f"/api/v1/resources/{a['resource']['id']}").status_code == 404

    admin.close(); viewer.close(); bearer.close()


def test_t92_t95_t98_audit_lifecycle_and_deleted_objects() -> None:
    admin = _admin()
    suffix = run_suffix()
    a = _objects(admin, f"F28H{suffix}", f"f28-h-{suffix}", "10.88.0.0/24")
    viewer, row = _role_api(admin, "VIEWER", suffix)
    ga = _grant(admin, row["id"], a["cluster"]["id"])
    audit = ok(admin.get("/api/v1/audit", params={"object_type": "user_cluster_authorization", "page_size": 100}), 200)
    assert audit["total"] >= 1
    assert viewer.get("/api/v1/audit").status_code == 403

    ok(admin.patch(f"/api/v1/clusters/{a['cluster']['id']}", json={"version": a["cluster"]["version"], "status": "INACTIVE"}), 200)
    assert _ids(viewer.get("/api/v1/resources")) == {a["resource"]["id"]}

    life = create_cluster(admin, f"F28L{suffix}", "lifecycle")
    life_grant = _grant(admin, row["id"], life["id"])
    assert life["id"] in _ids(viewer.get("/api/v1/clusters"))
    ok(admin.delete(f"/api/v1/clusters/{life['id']}?version={life['version']}"), 204)
    assert life["id"] not in _ids(viewer.get("/api/v1/clusters"))
    ok(admin.post(f"/api/v1/clusters/{life['id']}/restore?version={life['version'] + 1}"), 200)
    assert life["id"] in _ids(viewer.get("/api/v1/clusters"))
    del life_grant

    assert viewer.get("/api/v1/resources", params={"deleted": "include"}).status_code == 403
    assert viewer.get(f"/api/v1/resources/{a['resource']['id']}", params={"deleted": "true"}).status_code == 403

    admin.close(); viewer.close()
