"""F027 server-side access-scope enforcement (real PostgreSQL).

Every business endpoint is exercised through the production app with only
``get_db`` overridden.  Non-ADMIN users are granted Cluster A/B; Cluster C is
never granted.  The same assertions are also made for an API Key bound to the
granted user, and for grant revocation / role change on the next request.
"""

from __future__ import annotations

import csv
import io
import uuid

from sqlalchemy import func, select

from integration.api_keys_helpers import bearer_client, create_key  # noqa: F401
from integration.f015_helpers import (  # noqa: F401
    bind,
    create_cluster,
    create_endpoint,
    create_interface,
    create_ip,
    create_network,
    create_pool,
    create_resource,
    create_service,
    role_client_factory,
)

LISTS = {
    "clusters": "/api/v1/clusters",
    "resources": "/api/v1/resources",
    "networks": "/api/v1/networks",
    "ip_addresses": "/api/v1/ip-addresses",
    "ip_pools": "/api/v1/ip-pools",
    "interfaces": "/api/v1/interfaces",
    "services": "/api/v1/services",
    "service_endpoints": "/api/v1/service-endpoints",
}
DETAIL_PATHS = {
    "clusters": "/api/v1/clusters/{id}",
    "resources": "/api/v1/resources/{id}",
    "networks": "/api/v1/networks/{id}",
    "ip_addresses": "/api/v1/ip-addresses/{id}",
    "ip_pools": "/api/v1/ip-pools/{id}",
    "interfaces": "/api/v1/interfaces/{id}",
    "services": "/api/v1/services/{id}",
    "service_endpoints": "/api/v1/service-endpoints/{id}",
}
WRITE_PATHS = {
    "resources": "/api/v1/resources/{id}",
    "networks": "/api/v1/networks/{id}",
    "ip_addresses": "/api/v1/ip-addresses/{id}",
    "ip_pools": "/api/v1/ip-pools/{id}",
    "interfaces": "/api/v1/interfaces/{id}",
    "services": "/api/v1/services/{id}",
    "service_endpoints": "/api/v1/service-endpoints/{id}",
}


def _grant(admin, user_id, cluster_id):
    resp = admin.post(
        f"/api/v1/users/{user_id}/cluster-authorizations",
        json={"cluster_id": str(cluster_id)},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["cluster_authorization"]


def _revoke(admin, authorization_id):
    resp = admin.post(f"/api/v1/cluster-authorizations/{authorization_id}/revoke")
    assert resp.status_code == 200, resp.text


def _ids(resp):
    assert resp.status_code == 200, resp.text
    return [item["id"] for item in resp.json()["items"]]


def _create_cluster_objects(admin, code: str, hostname: str, cidr: str):
    cluster = create_cluster(admin, code, f"F027 {code}")
    resource = create_resource(admin, code, hostname)
    interface = create_interface(admin, resource["id"], name=f"{hostname}-eth0")
    network = create_network(admin, code, name=f"{hostname}-net", cidr=cidr)
    pool = create_pool(
        admin,
        network["id"],
        name=f"{hostname}-pool",
        start=cidr.rsplit(".", 1)[0] + ".10",
        end=cidr.rsplit(".", 1)[0] + ".20",
    )
    ip = create_ip(admin, network["id"], cidr.rsplit(".", 1)[0] + ".5")
    ip = bind(admin, ip, interface, ip["version"])
    service = create_service(admin, resource["id"], name=f"{hostname}-svc")
    endpoint = create_endpoint(admin, service["id"], ip["id"], port=2200)
    return {
        "cluster": cluster,
        "resource": resource,
        "interface": interface,
        "network": network,
        "ip_pool": pool,
        "ip_address": ip,
        "service": service,
        "service_endpoint": endpoint,
    }


def _setup(admin):
    a = _create_cluster_objects(admin, "F27A", "f27-a-host", "10.71.0.0/24")
    b = _create_cluster_objects(admin, "F27B", "f27-b-host", "10.72.0.0/24")
    c = _create_cluster_objects(admin, "F27C", "f27-c-host", "10.73.0.0/24")
    return a, b, c


def _csv_bytes(headers, rows):
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(headers)
    for row in rows:
        writer.writerow(["" if row.get(h) is None else str(row.get(h, "")) for h in headers])
    return buf.getvalue().encode("utf-8")


def _post_import(client, path, data):
    return client.post(
        path,
        files={"file": ("f027.csv", data, "text/csv")},
        data={"format": "csv"},
    )


BM_HEADERS = [
    "cluster",
    "hostname",
    "resource_type",
    "role",
    "status",
    "manufacturer",
    "model",
    "serial_number",
    "cpu_model",
    "cpu_sockets",
    "cpu_cores",
    "memory_mb",
    "gpu_model",
    "gpu_count",
]
UNIFIED_HEADERS = [
    "cluster",
    "hostname",
    "resource_type",
    "role",
    "status",
    "host",
    "vcpu",
    "memory_mb",
    "disk_gb",
    "hypervisor",
    "manufacturer",
    "model",
    "serial_number",
    "cpu_model",
    "cpu_sockets",
    "cpu_cores",
    "gpu_model",
    "gpu_count",
    "name",
    "interface_type",
    "mac_address",
    "speed_mbps",
    "mtu",
    "enabled",
    "network",
    "ip",
]


def test_lists_details_activity_and_totals_are_scoped(
    api_client, role_client_factory, make_user
):
    admin, _, _ = role_client_factory("ADMIN")
    a, b, c = _setup(admin)
    viewer, viewer_user, _ = role_client_factory("VIEWER", username="f027.viewer")
    _grant(admin, viewer_user.id, a["cluster"]["id"])
    _grant(admin, viewer_user.id, b["cluster"]["id"])

    expected_visible = {
        "clusters": {a["cluster"]["id"], b["cluster"]["id"]},
        "resources": {a["resource"]["id"], b["resource"]["id"]},
        "networks": {a["network"]["id"], b["network"]["id"]},
        "ip_addresses": {a["ip_address"]["id"], b["ip_address"]["id"]},
        "ip_pools": {a["ip_pool"]["id"], b["ip_pool"]["id"]},
        "interfaces": {a["interface"]["id"], b["interface"]["id"]},
        "services": {a["service"]["id"], b["service"]["id"]},
        "service_endpoints": {a["service_endpoint"]["id"], b["service_endpoint"]["id"]},
    }
    c_ids = {
        "clusters": c["cluster"]["id"],
        "resources": c["resource"]["id"],
        "networks": c["network"]["id"],
        "ip_addresses": c["ip_address"]["id"],
        "ip_pools": c["ip_pool"]["id"],
        "interfaces": c["interface"]["id"],
        "services": c["service"]["id"],
        "service_endpoints": c["service_endpoint"]["id"],
    }
    for name, path in LISTS.items():
        resp = viewer.get(path, params={"page_size": 100})
        assert resp.status_code == 200, (name, resp.text)
        body = resp.json()
        assert body["total"] == 2, (name, body)
        assert len(body["items"]) == 2, (name, body)
        assert {item["id"] for item in body["items"]} == expected_visible[name]
        assert c_ids[name] not in _ids(resp)

        unauthorized_filter = viewer.get(
            path,
            params={"page_size": 100, "cluster_id": c["cluster"]["id"]},
        )
        if name in ("resources", "networks", "ip_addresses"):
            assert unauthorized_filter.status_code == 200
            assert unauthorized_filter.json()["total"] == 0

    # Explicit filter by an unauthorized cluster code -> empty 200 (clusters).
    by_code = viewer.get("/api/v1/clusters", params={"code": "F27C"})
    assert by_code.status_code == 200 and by_code.json()["total"] == 0

    # Details and Activity for every C object are 404 (no field leak).
    c_objects = {
        "clusters": c["cluster"],
        "resources": c["resource"],
        "networks": c["network"],
        "ip_addresses": c["ip_address"],
        "ip_pools": c["ip_pool"],
        "interfaces": c["interface"],
        "services": c["service"],
        "service_endpoints": c["service_endpoint"],
    }
    for name, template in DETAIL_PATHS.items():
        object_id = c_objects[name]["id"]
        detail = viewer.get(template.format(id=object_id))
        assert detail.status_code == 404, (name, detail.text)
        assert detail.json()["error"]["code"] == "NOT_FOUND"
        activity = viewer.get(template.format(id=object_id) + "/activity")
        assert activity.status_code == 404, (name, activity.text)

    # ADMIN is unrestricted (the test file may run after suites that leave DB rows).
    admin_clusters = admin.get(
        "/api/v1/clusters", params={"q": "F27", "page_size": 100}
    ).json()
    assert {item["id"] for item in admin_clusters["items"]} == {
        a["cluster"]["id"],
        b["cluster"]["id"],
        c["cluster"]["id"],
    }
    for name, template in DETAIL_PATHS.items():
        assert admin.get(template.format(id=c_objects[name]["id"])).status_code == 200


def test_zero_grants_deny_by_default(role_client_factory):
    admin, _, _ = role_client_factory("ADMIN")
    _, _, c = _setup(admin)
    nobody, _, _ = role_client_factory("VIEWER", username="f027.nobody")

    for name, path in LISTS.items():
        resp = nobody.get(path, params={"page_size": 100})
        assert resp.status_code == 200, (name, resp.text)
        assert resp.json() == {
            "items": [],
            "page": 1,
            "page_size": 100,
            "total": 0,
        } if name == "clusters" else resp.json()["total"] == 0

    assert nobody.get(f"/api/v1/clusters/{c['cluster']['id']}").status_code == 404
    assert nobody.get(f"/api/v1/resources/{c['resource']['id']}").status_code == 404

    dashboard = nobody.get("/api/v1/dashboard")
    assert dashboard.status_code == 200, dashboard.text
    body = dashboard.json()
    assert body["counts"] == {
        "clusters": 0,
        "resources": 0,
        "bare_metal": 0,
        "virtual_machines": 0,
        "networks": 0,
    }
    assert body["networks"]["items"] == [] and body["networks"]["total"] == 0


def test_unscoped_writes_are_rejected_without_state_or_audit(
    role_client_factory, auth_session_factory
):
    from app.models.audit_log import AuditLog

    admin, _, _ = role_client_factory("ADMIN")
    a, _, c = _setup(admin)
    editor, editor_user, _ = role_client_factory(
        "EDITOR", username="f027.editor"
    )
    _grant(admin, editor_user.id, a["cluster"]["id"])

    with auth_session_factory() as session:
        before_audit = int(
            session.execute(select(func.count()).select_from(AuditLog)).scalar_one()
        )
    before_version = admin.get(f"/api/v1/resources/{c['resource']['id']}").json()[
        "resource"
    ]["version"]

    # Body Cluster / parent references -> 422 and no leak of C identifiers.
    create_cases = [
        ("/api/v1/networks", {"cluster": "F27C", "name": "f27-x", "cidr": "10.79.0.0/24"}),
        (
            "/api/v1/resources",
            {"cluster": "F27C", "hostname": "f27-x", "resource_type": "BARE_METAL"},
        ),
        ("/api/v1/interfaces", {"resource": c["resource"]["id"], "name": "x"}),
        ("/api/v1/services", {"resource": c["resource"]["id"], "name": "x"}),
        ("/api/v1/ip-pools", {"network": c["network"]["id"], "name": "x", "start_address": "10.73.0.30", "end_address": "10.73.0.40"}),
        ("/api/v1/ip-addresses", {"network": c["network"]["id"], "address": "10.73.0.30"}),
        (
            "/api/v1/service-endpoints",
            {"service": c["service"]["id"], "ip_address": c["ip_address"]["id"], "protocol": "TCP", "port": 2288},
        ),
    ]
    for path, payload in create_cases:
        resp = editor.post(path, json=payload)
        assert resp.status_code == 422, (path, resp.text)
        fields = resp.json()["error"]["details"].get("fields", [])
        assert fields, (path, resp.text)
        assert "F27C" not in resp.text
        assert c["cluster"]["id"] not in resp.text

    # Path objects that are not visible -> 404 (before version/uniqueness/409).
    c_write_objects = {
        "resources": c["resource"],
        "networks": c["network"],
        "ip_addresses": c["ip_address"],
        "ip_pools": c["ip_pool"],
        "interfaces": c["interface"],
        "services": c["service"],
        "service_endpoints": c["service_endpoint"],
    }
    for name, template in WRITE_PATHS.items():
        object_id = c_write_objects[name]["id"]
        body = {"version": c_write_objects[name]["version"], "description": "x"}
        resp = editor.patch(template.format(id=object_id), json=body)
        assert resp.status_code == 404, (name, resp.text)

    after_version = admin.get(f"/api/v1/resources/{c['resource']['id']}").json()[
        "resource"
    ]["version"]
    assert after_version == before_version
    with auth_session_factory() as session:
        after_audit = int(
            session.execute(select(func.count()).select_from(AuditLog)).scalar_one()
        )
    assert after_audit == before_audit

    # Transfer to an unauthorized Interface -> 422 (current IP is visible).
    extra = create_ip(admin, a["network"]["id"], "10.71.0.6")
    transfer = editor.patch(
        f"/api/v1/ip-addresses/{extra['id']}",
        json={"version": extra["version"], "interface": c["interface"]["id"]},
    )
    assert transfer.status_code == 422, transfer.text
    assert transfer.json()["error"]["details"]["fields"][0]["field"] == "interface"

    # Visible bind/unbind keeps working.
    bound = editor.patch(
        f"/api/v1/ip-addresses/{extra['id']}",
        json={"version": extra["version"], "interface": a["interface"]["id"]},
    )
    assert bound.status_code == 200, bound.text
    unbound = editor.patch(
        f"/api/v1/ip-addresses/{extra['id']}",
        json={"version": bound.json()["ip_address"]["version"], "interface": None},
    )
    assert unbound.status_code == 200, unbound.text


def test_search_dashboard_and_related_rows_are_scoped(role_client_factory):
    admin, _, _ = role_client_factory("ADMIN")
    a, b, c = _setup(admin)
    viewer, viewer_user, _ = role_client_factory("VIEWER", username="f027.search")
    _grant(admin, viewer_user.id, a["cluster"]["id"])
    _grant(admin, viewer_user.id, b["cluster"]["id"])

    for object_type in ("resource", "cluster", "ip_address", "service"):
        q = "f27" if object_type != "ip_address" else "10.73.0.5"
        viewer_resp = viewer.get(
            "/api/v1/search",
            params={"q": q, "type": object_type, "page_size": 100},
        )
        assert viewer_resp.status_code == 200, viewer_resp.text
        viewer_body = viewer_resp.json()
        admin_resp = admin.get(
            "/api/v1/search",
            params={"q": q, "type": object_type, "page_size": 100},
        )
        assert admin_resp.status_code == 200, admin_resp.text
        admin_body = admin_resp.json()
        if object_type == "ip_address":
            assert viewer_body["total"] == 0
            assert [i["id"] for i in admin_body["items"]] == [c["ip_address"]["id"]]
        else:
            assert viewer_body["total"] == 2, (object_type, viewer_body)
            assert admin_body["total"] == 3, (object_type, admin_body)
            assert c["cluster"]["id"] not in viewer_resp.text
            assert c["resource"]["id"] not in viewer_resp.text

    related = viewer.get(
        "/api/v1/search",
        params={"q": "f27-a-host", "type": "resource", "page_size": 100},
    )
    assert related.status_code == 200, related.text
    item = related.json()["items"][0]
    assert item["resource"]["related_total"] == 1
    assert [r["ip_address"]["id"] for r in item["resource"]["related"]] == [
        a["ip_address"]["id"]
    ]

    dashboard = viewer.get("/api/v1/dashboard", params={"page_size": 100})
    assert dashboard.status_code == 200, dashboard.text
    body = dashboard.json()
    assert body["counts"] == {
        "clusters": 2,
        "resources": 2,
        "bare_metal": 2,
        "virtual_machines": 0,
        "networks": 2,
    }
    assert body["networks"]["total"] == 2
    assert {item["network"]["id"] for item in body["networks"]["items"]} == {
        a["network"]["id"],
        b["network"]["id"],
    }
    assert c["network"]["id"] not in dashboard.text


def test_revoke_and_role_change_apply_on_next_request_including_api_key(
    auth_app, role_client_factory, make_user
):
    admin, _, _ = role_client_factory("ADMIN")
    a, b, _ = _setup(admin)
    viewer, viewer_user, password = role_client_factory(
        "VIEWER", username="f027.live"
    )
    first = _grant(admin, viewer_user.id, a["cluster"]["id"])
    second = _grant(admin, viewer_user.id, b["cluster"]["id"])

    key = create_key(admin, bound_user_id=str(viewer_user.id), label="f027")
    assert key.status_code == 201, key.text
    plaintext = key.json()["api_key"]["plaintext"]
    with bearer_client(auth_app, plaintext) as key_client:
        assert key_client.get("/api/v1/clusters").json()["total"] == 2
        _revoke(admin, second["id"])
        assert viewer.get("/api/v1/clusters").json()["total"] == 1
        assert key_client.get("/api/v1/clusters").json()["total"] == 1

    # Role upgrade is resolved per request: the same cookie/API key now sees all.
    current = admin.get(f"/api/v1/users/{viewer_user.id}").json()["user"]
    upgraded = admin.patch(
        f"/api/v1/users/{viewer_user.id}",
        json={"version": current["version"], "role": "ADMIN"},
    )
    assert upgraded.status_code == 200, upgraded.text
    assert (
        viewer.get("/api/v1/clusters", params={"q": "F27", "page_size": 100})
        .json()["total"]
        == 3
    )
    with bearer_client(auth_app, plaintext) as key_client:
        assert (
            key_client.get("/api/v1/clusters", params={"q": "F27", "page_size": 100})
            .json()["total"]
            == 3
        )


def test_soft_deleted_cluster_scope_and_restore(role_client_factory):
    admin, _, _ = role_client_factory("ADMIN")
    viewer, viewer_user, _ = role_client_factory("VIEWER", username="f027.life")
    empty = create_cluster(admin, "F27E", "F027 empty")
    _grant(admin, viewer_user.id, empty["id"])
    assert viewer.get("/api/v1/clusters").json()["total"] == 1

    deleted = admin.delete(f"/api/v1/clusters/{empty['id']}?version={empty['version']}")
    assert deleted.status_code == 204, deleted.text
    assert viewer.get("/api/v1/clusters").json()["total"] == 0
    assert viewer.get(f"/api/v1/clusters/{empty['id']}").status_code == 404

    restored = admin.post(f"/api/v1/clusters/{empty['id']}/restore?version=2")
    assert restored.status_code == 200, restored.text
    assert viewer.get("/api/v1/clusters").json()["total"] == 1


def test_error_precedence_and_admin_deleted_behavior(api_client, role_client_factory):
    admin, _, _ = role_client_factory("ADMIN")
    a, _, c = _setup(admin)
    viewer, viewer_user, _ = role_client_factory("VIEWER", username="f027.order")
    editor, editor_user, _ = role_client_factory("EDITOR", username="f027.editor2")
    _grant(admin, viewer_user.id, a["cluster"]["id"])
    _grant(admin, editor_user.id, a["cluster"]["id"])

    path = f"/api/v1/clusters/{c['cluster']['id']}"
    assert api_client.get(path).status_code == 401
    assert viewer.delete(f"{path}?version=1").status_code == 403
    assert viewer.get(path).status_code == 404
    assert editor.patch(
        f"/api/v1/resources/{c['resource']['id']}",
        json={"version": 1, "description": "x"},
    ).status_code == 404
    assert editor.patch(
        f"/api/v1/resources/{a['resource']['id']}",
        json={"version": 999, "description": "x"},
    ).status_code == 409
    assert viewer.get("/api/v1/clusters", params={"deleted": "include"}).status_code == 403
    assert admin.get("/api/v1/clusters", params={"deleted": "include"}).status_code == 200


def test_f014_import_row_scope_error_fails_whole_batch_without_residue(
    role_client_factory, auth_session_factory
):
    from app.models.resource import Resource

    admin, _, _ = role_client_factory("ADMIN")
    a, b, c = _setup(admin)
    editor, editor_user, _ = role_client_factory("EDITOR", username="f027.import")
    _grant(admin, editor_user.id, a["cluster"]["id"])
    _grant(admin, editor_user.id, b["cluster"]["id"])

    data = _csv_bytes(
        BM_HEADERS,
        [
            {"cluster": "F27B", "hostname": "f27-imp-ok", "resource_type": "BARE_METAL"},
            {"cluster": "F27C", "hostname": "f27-imp-bad", "resource_type": "BARE_METAL"},
        ],
    )
    validate = _post_import(editor, "/api/v1/imports/resources/validate", data)
    assert validate.status_code == 200, validate.text
    body = validate.json()
    assert body["total_rows"] == 2
    assert body["importable_rows"] == 1
    assert body["error_count"] == 1
    assert body["errors"][0]["row"] == 3
    assert body["errors"][0]["field"] == "cluster"
    assert "F27C" not in str(body["errors"])

    with auth_session_factory() as session:
        before = int(
            session.execute(select(func.count()).select_from(Resource)).scalar_one()
        )
    write = _post_import(editor, "/api/v1/imports/resources", data)
    assert write.status_code == 422, write.text
    details = write.json()["error"]["details"]
    assert details["error_count"] == 1
    assert details["errors"][0]["field"] == "cluster"
    with auth_session_factory() as session:
        after = int(
            session.execute(select(func.count()).select_from(Resource)).scalar_one()
        )
        imported = session.execute(
            select(Resource.id).where(Resource.hostname == "f27-imp-ok")
        ).first()
    assert after == before
    assert imported is None


def test_f023_import_row_scope_error_fails_whole_batch_without_residue(
    role_client_factory, auth_session_factory
):
    from app.models.interface import Interface
    from app.models.ip_address import IPAddress
    from app.models.resource import Resource

    admin, _, _ = role_client_factory("ADMIN")
    a, b, c = _setup(admin)
    editor, editor_user, _ = role_client_factory("EDITOR", username="f027.import2")
    _grant(admin, editor_user.id, a["cluster"]["id"])
    _grant(admin, editor_user.id, b["cluster"]["id"])

    def row(cluster, hostname, ip, network):
        return {
            "cluster": cluster,
            "hostname": hostname,
            "resource_type": "BARE_METAL",
            "name": "eth9",
            "network": network,
            "ip": ip,
        }

    data = _csv_bytes(
        UNIFIED_HEADERS,
        [
            row("F27B", "f27-u-ok", "10.72.0.90", b["network"]["name"]),
            row("F27C", "f27-u-bad", "10.73.0.90", c["network"]["name"]),
        ],
    )
    validate = _post_import(
        editor, "/api/v1/imports/resource-interfaces-ips/validate", data
    )
    assert validate.status_code == 200, validate.text
    body = validate.json()
    assert body["total_rows"] == 2
    assert body["importable_rows"] == 1
    assert body["error_count"] == 1
    assert body["errors"][0]["row"] == 3
    assert body["errors"][0]["field"] == "cluster"

    with auth_session_factory() as session:
        before = {
            "resources": int(session.execute(select(func.count()).select_from(Resource)).scalar_one()),
            "interfaces": int(session.execute(select(func.count()).select_from(Interface)).scalar_one()),
            "ips": int(session.execute(select(func.count()).select_from(IPAddress)).scalar_one()),
        }
    write = _post_import(editor, "/api/v1/imports/resource-interfaces-ips", data)
    assert write.status_code == 422, write.text
    with auth_session_factory() as session:
        after = {
            "resources": int(session.execute(select(func.count()).select_from(Resource)).scalar_one()),
            "interfaces": int(session.execute(select(func.count()).select_from(Interface)).scalar_one()),
            "ips": int(session.execute(select(func.count()).select_from(IPAddress)).scalar_one()),
        }
        residue = session.execute(
            select(Resource.id).where(Resource.hostname == "f27-u-ok")
        ).first()
    assert before == after
    assert residue is None


def test_hidden_interface_error_is_indistinguishable_from_missing(
    api_client, role_client_factory, make_user
):
    """F027-R1: an unauthorized parent must not leak existence via 422 text."""
    admin, _, _ = role_client_factory("ADMIN")
    a = _create_cluster_objects(admin, "F27H", "f27-h-host", "10.74.0.0/24")
    c = _create_cluster_objects(admin, "F27I", "f27-i-host", "10.75.0.0/24")
    editor, editor_user, _ = role_client_factory("EDITOR", username="f027.hidden")
    _grant(admin, editor_user.id, a["cluster"]["id"])

    hidden = editor.patch(
        f"/api/v1/ip-addresses/{a['ip_address']['id']}",
        json={
            "version": a["ip_address"]["version"],
            "interface": c["interface"]["id"],
        },
    )
    missing = editor.patch(
        f"/api/v1/ip-addresses/{a['ip_address']['id']}",
        json={
            "version": a["ip_address"]["version"],
            "interface": str(uuid.uuid4()),
        },
    )
    assert hidden.status_code == missing.status_code == 422
    hidden_field = hidden.json()["error"]["details"]["fields"][0]
    missing_field = missing.json()["error"]["details"]["fields"][0]
    assert hidden_field == missing_field
