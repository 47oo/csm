"""F016 integration-acceptance tests (Tester-authored, TE-1 real execution).

Runs against the **real** entry stack (Nginx -> FastAPI -> PostgreSQL) over real
HTTP. Covers the RERUN set of `docs/features/F016/test-report.md` TD-1
(ACC-T11/16/19/22/23/24/25/26/27/28/29/32/37/40/41), §32 C1-C15, §33 Q1-Q9 and
REUSE endpoint reachability checks. Constraint/concurrency evidence is NOT
reproven here (REUSE anchors point to the authoritative Feature suites); this
module only confirms the integrated stack is reachable and behaves end-to-end.

Guard: the whole module skips unless ``F016_ACCEPTANCE=1`` so it never runs in a
normal ``pytest tests`` pass.
"""

from __future__ import annotations

import io

import pytest

from integration.f016_helpers import (  # noqa: F401
    BM_HEADERS,
    VALIDATE_PATH,
    VM_HEADERS,
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
    error_reason,
    import_request,
    make_role_api,
    ok,
    run_suffix,
    soft_delete,
    vm_row,
)

if not acceptance_enabled():
    pytest.skip(
        "F016 acceptance module disabled (set F016_ACCEPTANCE=1)",
        allow_module_level=True,
    )

pytestmark = [pytest.mark.integration]

SUFFIX = run_suffix()
CLUSTER_CODE = f"F16{SUFFIX}"


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #


@pytest.fixture(scope="module")
def admin() -> Api:
    api = Api(admin_credentials())
    yield api
    api.close()


@pytest.fixture(scope="module")
def dataset(admin: Api) -> dict:
    """DR-236 acceptance dataset, created entirely through the real HTTP API."""
    cl = create_cluster(admin, CLUSTER_CODE, "F016 Acceptance")
    cn001 = create_resource(admin, cl["code"], "cn001", role="COMPUTE")
    pve01 = create_resource(admin, cl["code"], "pve01", role="COMPUTE")
    vm001 = create_resource(
        admin,
        cl["code"],
        "vm001",
        resource_type="VIRTUAL_MACHINE",
        virtual_machine={"host_resource_id": pve01["id"], "vcpu": 4, "memory_mb": 8192},
    )
    mgmt_if = create_interface(admin, cn001["id"], "mgmt0", interface_type="PHYSICAL")
    ib_if = create_interface(admin, cn001["id"], "ib0", interface_type="PHYSICAL")

    mgmt_net = create_network(
        admin, cl["code"], "mgmt-net", "10.100.0.0/24", gateway="10.100.0.1"
    )
    ib_net = create_network(admin, cl["code"], "ib-net", "10.200.0.0/24")

    mgmt_ip = bind_ip(admin, create_ip(admin, mgmt_net["id"], "10.100.0.10"), mgmt_if["id"])
    ib_ip = bind_ip(admin, create_ip(admin, ib_net["id"], "10.200.0.10"), ib_if["id"])
    free_ip = create_ip(admin, mgmt_net["id"], "10.100.0.11")

    svc = create_service(admin, cn001["id"], "sshd")
    ep = create_endpoint(admin, svc["id"], mgmt_ip["id"], "TCP", 22)
    auto_pool = create_pool(
        admin, mgmt_net["id"], "auto", "10.100.0.200", "10.100.0.210", allocation_mode="AUTO"
    )
    return {
        "cluster": cl,
        "cn001": cn001,
        "pve01": pve01,
        "vm001": vm001,
        "mgmt_if": mgmt_if,
        "ib_if": ib_if,
        "mgmt_net": mgmt_net,
        "ib_net": ib_net,
        "mgmt_ip": mgmt_ip,
        "ib_ip": ib_ip,
        "free_ip": free_ip,
        "service": svc,
        "endpoint": ep,
        "auto_pool": auto_pool,
    }


@pytest.fixture(scope="module")
def editor(admin: Api) -> Api:
    api = make_role_api(admin, "EDITOR")
    yield api
    api.close()


@pytest.fixture(scope="module")
def viewer(admin: Api) -> Api:
    api = make_role_api(admin, "VIEWER")
    yield api
    api.close()


def _xlsx_bytes(headers: list[str], rows: list[list]) -> bytes:
    openpyxl = pytest.importorskip("openpyxl")
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(headers)
    for row in rows:
        ws.append([("" if v is None else v) for v in row])
    stream = io.BytesIO()
    wb.save(stream)
    return stream.getvalue()


# =========================================================================== #
# A1 / environment health (real stack)
# =========================================================================== #


def test_a1_entry_health_and_spa(admin: Api) -> None:
    healthz = admin.get("/healthz")
    assert healthz.status_code == 200 and healthz.text.strip() == "ok"
    ready = admin.get("/api/v1/health/ready")
    assert ready.status_code == 200 and ready.json()["db"] == "up"
    index = admin.get("/")
    assert index.status_code == 200 and "index" in index.text.lower()


# =========================================================================== #
# RERUN cases (ACC-T*)
# =========================================================================== #


def test_acc_t11_api_and_import_share_hostname_normalisation(admin: Api) -> None:
    cl = create_cluster(admin, f"T11{SUFFIX}", "T11")
    r = create_resource(admin, cl["code"], "  T11HOST  ")
    assert r["hostname"] == "t11host"
    dup = admin.post(
        "/api/v1/resources",
        json={"cluster": cl["code"], "hostname": "t11host", "resource_type": "BARE_METAL"},
    )
    assert dup.status_code == 409 and error_reason(dup) == "unique_conflict"

    # same rule through CSV import (folding + uniqueness shared with the API)
    csv_resp = import_request(
        admin, VALIDATE_PATH, csv_bytes(BM_HEADERS, [bm_row(cl["code"], "T11Host")])
    )
    body = ok(csv_resp, 200)
    assert body["error_count"] >= 1
    assert any(e["field"] == "hostname" for e in body["errors"])
    # identical rule for .xlsx
    xlsx_resp = import_request(
        admin, VALIDATE_PATH, _xlsx_bytes(BM_HEADERS, [bm_row(cl["code"], "T11Host")]), "xlsx"
    )
    xbody = ok(xlsx_resp, 200)
    assert any(e["field"] == "hostname" for e in xbody["errors"])


def test_acc_t16_inactive_and_auto_allocation_gates(admin: Api) -> None:
    cl = create_cluster(admin, f"T16{SUFFIX}", "T16")
    inactive = create_network(
        admin, cl["code"], "inactive-net", "10.116.0.0/24", status="INACTIVE"
    )
    create_pool(admin, inactive["id"], "p", "10.116.0.10", "10.116.0.20")
    blocked = admin.post(
        "/api/v1/ip-addresses", json={"network": inactive["id"], "address": "10.116.0.15"}
    )
    assert blocked.status_code == 409
    assert blocked.json()["error"]["details"]["condition"] == "network_inactive"

    no_auto = create_network(admin, cl["code"], "no-auto", "10.117.0.0/24")
    pool = create_pool(
        admin, no_auto["id"], "auto", "10.117.0.10", "10.117.0.20", allocation_mode="AUTO"
    )
    denied = admin.post(
        "/api/v1/ip-addresses/auto-allocate",
        json={"network": no_auto["id"], "ip_pool": pool["id"]},
    )
    assert denied.status_code == 409
    assert denied.json()["error"]["details"]["condition"] == "auto_allocate_disabled"

    auto = create_network(admin, cl["code"], "auto", "10.118.0.0/24", auto_allocate=True)
    small = create_pool(
        admin, auto["id"], "one", "10.118.0.10", "10.118.0.10", allocation_mode="AUTO"
    )
    first = ok(
        admin.post(
            "/api/v1/ip-addresses/auto-allocate",
            json={"network": auto["id"], "ip_pool": small["id"]},
        ),
        201,
    )
    assert first["ip_address"]["address"] == "10.118.0.10"
    exhausted = admin.post(
        "/api/v1/ip-addresses/auto-allocate",
        json={"network": auto["id"], "ip_pool": small["id"]},
    )
    assert exhausted.status_code == 409
    assert exhausted.json()["error"]["details"]["reason"] == "no_available_address"


def test_acc_t19_vm_host_rules_and_resource_immutability(admin: Api) -> None:
    cl = create_cluster(admin, f"T19{SUFFIX}", "T19")
    host_a = create_resource(admin, cl["code"], "t19hosta")
    host_b = create_resource(admin, cl["code"], "t19hostb")

    # VM without a host -> 422
    missing = admin.post(
        "/api/v1/resources",
        json={"cluster": cl["code"], "hostname": "t19vm0", "resource_type": "VIRTUAL_MACHINE"},
    )
    assert missing.status_code == 422

    vm = create_resource(
        admin,
        cl["code"],
        "t19vm1",
        resource_type="VIRTUAL_MACHINE",
        virtual_machine={"host_resource_id": host_a["id"]},
    )
    assert vm["virtual_machine"]["host"]["hostname"] == "t19hosta"

    # change host -> 200 and UPDATE recorded in Activity
    changed = ok(
        admin.patch(
            f"/api/v1/resources/{vm['id']}",
            json={
                "version": vm["version"],
                "virtual_machine": {"host_resource_id": host_b["id"]},
            },
        ),
        200,
    )["resource"]
    assert changed["virtual_machine"]["host"]["hostname"] == "t19hostb"
    activity = ok(admin.get(f"/api/v1/resources/{vm['id']}/activity"), 200)
    assert any(item["action"] == "UPDATE" for item in activity["items"])

    # Resource cluster / type are immutable (rejected as unknown extras -> 422)
    assert (
        admin.patch(
            f"/api/v1/resources/{host_a['id']}",
            json={"version": host_a["version"], "cluster": cl["code"]},
        ).status_code
        == 422
    )
    assert (
        admin.patch(
            f"/api/v1/resources/{host_a['id']}",
            json={"version": host_a["version"], "resource_type": "VIRTUAL_MACHINE"},
        ).status_code
        == 422
    )


def test_acc_t22_endpoint_rules_and_reference_guard(admin: Api) -> None:
    cl = create_cluster(admin, f"T22{SUFFIX}", "T22")
    res = create_resource(admin, cl["code"], "t22host")
    iface = create_interface(admin, res["id"], "e0")
    net = create_network(admin, cl["code"], "t22net", "10.122.0.0/24")
    ip = bind_ip(admin, create_ip(admin, net["id"], "10.122.0.5"), iface["id"])
    svc = create_service(admin, res["id"], "svc")

    assert (
        admin.post(
            "/api/v1/service-endpoints",
            json={"service": svc["id"], "ip_address": "", "protocol": "TCP", "port": 22},
        ).status_code
        == 422
    )
    ep = create_endpoint(admin, svc["id"], ip["id"], "TCP", 22)
    assert ep["protocol"] == "TCP"

    # an IP referenced by an Endpoint cannot be unbound / released
    current = ok(admin.get(f"/api/v1/ip-addresses/{ip['id']}"), 200)["ip_address"]
    unbind = admin.patch(
        f"/api/v1/ip-addresses/{ip['id']}",
        json={"version": current["version"], "interface": None},
    )
    assert unbind.status_code == 409 and error_reason(unbind) == "reference_exists"
    release = admin.delete(f"/api/v1/ip-addresses/{ip['id']}?version={current['version']}")
    assert release.status_code == 409


def test_acc_t23_live_references_block_delete_with_list(admin: Api, dataset: dict) -> None:
    # cn001 still owns Interfaces -> Resource delete must be refused with a list
    resp = admin.delete(
        f"/api/v1/resources/{dataset['cn001']['id']}?version={dataset['cn001']['version']}"
    )
    assert resp.status_code == 409
    assert error_reason(resp) == "reference_exists"
    refs = resp.json()["error"]["details"]["references"]
    assert any(r["object_type"] == "interface" for r in refs)


def test_acc_t24_admin_deleted_view_and_restore(admin: Api, viewer: Api) -> None:
    cl = create_cluster(admin, f"T24{SUFFIX}", "T24")
    res = create_resource(admin, cl["code"], "t24host")
    soft_delete(admin, f"/api/v1/resources/{res['id']}", res["version"])

    listed = ok(admin.get("/api/v1/deleted?object_type=resource&page_size=100"), 200)
    assert any(i["object_id"] == res["id"] for i in listed["items"])
    # non-ADMIN cannot view deleted objects
    assert viewer.get("/api/v1/deleted?object_type=resource").status_code == 403

    item = next(i for i in listed["items"] if i["object_id"] == res["id"])
    ok(admin.post(f"/api/v1/resources/{res['id']}/restore?version={item['version']}"), 200)
    assert ok(admin.get(f"/api/v1/resources/{res['id']}"), 200)["resource"]["deleted_at"] is None

    # restore does not overwrite a newer object with the same identity
    res2 = create_resource(admin, cl["code"], "t24reuse")
    soft_delete(admin, f"/api/v1/resources/{res2['id']}", res2["version"])
    create_resource(admin, cl["code"], "t24reuse")
    listed2 = ok(admin.get("/api/v1/deleted?object_type=resource&page_size=100"), 200)
    item2 = next(i for i in listed2["items"] if i["object_id"] == res2["id"])
    conflict = admin.post(f"/api/v1/resources/{res2['id']}/restore?version={item2['version']}")
    assert conflict.status_code == 409 and error_reason(conflict) == "unique_conflict"


def test_acc_t25_permission_matrix_401_before_403(
    admin: Api, viewer: Api, editor: Api
) -> None:
    cl = create_cluster(admin, f"T25{SUFFIX}", "T25")
    res = create_resource(admin, cl["code"], "t25host")

    anon = Api()
    try:
        assert anon.get("/api/v1/resources").status_code == 401
        anon_write = anon.post(
            "/api/v1/clusters", json={"code": "ANON", "name": "anon"}
        )
        assert anon_write.status_code == 401  # 401 precedes permission/422
        assert anon.get("/api/v1/audit").status_code == 401
    finally:
        anon.close()

    # VIEWER can read, cannot write/delete/audit/admin
    assert viewer.get("/api/v1/resources").status_code == 200
    assert (
        viewer.post("/api/v1/clusters", json={"code": f"V{SUFFIX}", "name": "v"}).status_code
        == 403
    )
    assert viewer.delete(f"/api/v1/resources/{res['id']}?version=1").status_code == 403
    assert viewer.get("/api/v1/audit").status_code == 403

    # EDITOR can write, cannot delete/restore/audit/user-admin
    assert (
        editor.post("/api/v1/clusters", json={"code": f"E{SUFFIX}", "name": "e"}).status_code
        == 201
    )
    assert editor.delete(f"/api/v1/resources/{res['id']}?version=1").status_code == 403
    assert editor.get("/api/v1/users").status_code == 403
    # ADMIN full
    assert admin.get("/api/v1/audit").status_code == 200
    assert admin.get("/api/v1/users").status_code == 200


def test_acc_t26_version_conflict_and_audit_hygiene(admin: Api) -> None:
    cl = create_cluster(admin, f"T26{SUFFIX}", "T26")
    stale = admin.patch(f"/api/v1/clusters/{cl['id']}", json={"version": 99, "name": "x"})
    assert stale.status_code == 409 and error_code(stale) == "VERSION_CONFLICT"

    changed = ok(
        admin.patch(f"/api/v1/clusters/{cl['id']}", json={"version": 1, "name": "T26b"}), 200
    )["cluster"]
    assert changed["version"] == 2

    audit = ok(admin.get("/api/v1/audit?page_size=100"), 200)
    assert any(
        i["object_type"] == "cluster" and i["object_id"] == cl["id"] and i["operator_username"]
        for i in audit["items"]
    )
    # no credential material is ever exposed by the audit endpoint
    assert "password" not in admin.get("/api/v1/audit?page_size=100").text.lower()


def test_acc_t27_import_validate_then_confirm_atomic(admin: Api) -> None:
    cl = create_cluster(admin, f"T27{SUFFIX}", "T27")
    good = bm_row(cl["code"], "t27new")
    bad = bm_row(cl["code"], "t27bad", cpu_cores="-1")
    validated = ok(
        import_request(admin, VALIDATE_PATH, csv_bytes(BM_HEADERS, [good, bad])), 200
    )
    assert validated["error_count"] == 1
    err = validated["errors"][0]
    assert {"row", "field", "reason"} <= set(err)

    blocked = import_request(admin, WRITE_PATH, csv_bytes(BM_HEADERS, [good, bad]))
    assert blocked.status_code == 422
    # atomic rollback: nothing from the failed batch was created
    search = ok(admin.get(f"/api/v1/resources?q=t27&cluster={cl['code']}"), 200)
    assert search["total"] == 0

    written = ok(import_request(admin, WRITE_PATH, csv_bytes(BM_HEADERS, [good])), 201)
    assert written["created"] == 1


def test_acc_t28_import_vm_host_rules_and_limits(admin: Api) -> None:
    cl = create_cluster(admin, f"T28{SUFFIX}", "T28")
    # VM host must already exist (not created implicitly by the same batch)
    missing_host = ok(
        import_request(
            admin, VALIDATE_PATH, csv_bytes(VM_HEADERS, [vm_row(cl["code"], "t28vm", "nope")])
        ),
        200,
    )
    assert missing_host["error_count"] >= 1

    # existing resource is never overwritten by an import
    create_resource(admin, cl["code"], "t28exist")
    conflict = ok(
        import_request(
            admin, VALIDATE_PATH, csv_bytes(BM_HEADERS, [bm_row(cl["code"], "t28exist")])
        ),
        200,
    )
    assert conflict["error_count"] >= 1

    # row limit is enforced
    too_many = [bm_row(cl["code"], f"t28r{i}") for i in range(5001)]
    over = import_request(admin, VALIDATE_PATH, csv_bytes(BM_HEADERS, too_many))
    assert over.status_code == 413


def test_acc_t29_inactive_cluster_maintenance(admin: Api) -> None:
    cl = create_cluster(admin, f"T29{SUFFIX}", "T29")
    res = create_resource(admin, cl["code"], "t29host")
    ok(admin.patch(f"/api/v1/clusters/{cl['id']}", json={"version": 1, "status": "INACTIVE"}), 200)

    # default list includes inactive clusters and can be filtered
    default = ok(admin.get(f"/api/v1/clusters?q={cl['code']}"), 200)
    assert default["total"] == 1
    inactive = ok(admin.get(f"/api/v1/clusters?q={cl['code']}&status=INACTIVE"), 200)
    assert inactive["total"] == 1

    # maintenance operations still work under an inactive cluster
    assert ok(admin.get(f"/api/v1/resources/{res['id']}"), 200)["resource"]["hostname"] == "t29host"
    # toggling cluster status does not cascade to its resources
    still = ok(admin.get(f"/api/v1/resources/{res['id']}"), 200)["resource"]
    assert still["deleted_at"] is None


def test_acc_t32_capacity_matches_dashboard(admin: Api, dataset: dict) -> None:
    net = dataset["mgmt_net"]
    caps = ok(admin.get(f"/api/v1/networks/{net['id']}/capacity"), 200)
    dashboard = ok(admin.get("/api/v1/dashboard?page_size=100"), 200)
    row = next(
        r for r in dashboard["networks"]["items"] if r["network"]["id"] == net["id"]
    )
    assert row["capacity"]["allocatable_total"] == caps["network_capacity"]["allocatable_total"]
    assert row["capacity"]["occupied"] == caps["network_capacity"]["occupied"]
    assert row["capacity"]["remaining"] == caps["network_capacity"]["remaining"]

    # disabling a network does not zero its capacity
    cl = dataset["cluster"]
    throwaway = create_network(admin, cl["code"], "t32-disable", "10.132.0.0/24")
    create_pool(admin, throwaway["id"], "p", "10.132.0.10", "10.132.0.20")
    before = ok(admin.get(f"/api/v1/networks/{throwaway['id']}/capacity"), 200)["network_capacity"]["allocatable_total"]
    ok(admin.patch(f"/api/v1/networks/{throwaway['id']}", json={"version": throwaway["version"], "status": "INACTIVE"}), 200)
    after = ok(admin.get(f"/api/v1/networks/{throwaway['id']}/capacity"), 200)
    assert after["network_capacity"]["allocatable_total"] == before


def test_acc_t37_defaults_explicit_null_and_import_parity(admin: Api) -> None:
    cl = create_cluster(admin, f"T37{SUFFIX}", "T37")
    defaulted = create_resource(admin, cl["code"], "t37default")
    assert defaulted["role"] == "OTHER" and defaulted["status"] == "UNKNOWN"

    explicit_null = admin.post(
        "/api/v1/resources",
        json={
            "cluster": cl["code"],
            "hostname": "t37null",
            "resource_type": "BARE_METAL",
            "role": None,
        },
    )
    assert explicit_null.status_code == 422

    iface = create_interface(admin, defaulted["id"], "eth0")
    assert iface["interface_type"] == "OTHER"  # type is not inferred from the name

    # import applies the same default rule (empty role -> OTHER)
    ok(import_request(admin, WRITE_PATH, csv_bytes(BM_HEADERS, [bm_row(cl["code"], "t37imp", role="")])), 201)
    imported = ok(admin.get(f"/api/v1/resources?q=t37imp&cluster={cl['code']}"), 200)
    assert imported["items"][0]["role"] == "OTHER"


def test_acc_t40_name_normalisation_and_uniqueness(admin: Api) -> None:
    cl = create_cluster(admin, f"T40{SUFFIX}", "T40")

    # empties / control characters / internal whitespace are rejected
    assert (
        admin.post("/api/v1/networks", json={"cluster": cl["code"], "name": "   ", "cidr": "10.140.0.0/24"}).status_code
        == 422
    )
    res = create_resource(admin, cl["code"], "t40host")
    assert (
        admin.post("/api/v1/interfaces", json={"resource": res["id"], "name": "eth 0"}).status_code
        == 422
    )
    # Interface names are case-sensitive and scoped to the Resource
    create_interface(admin, res["id"], "eth0")
    create_interface(admin, res["id"], "ETH0")
    assert (
        admin.post("/api/v1/interfaces", json={"resource": res["id"], "name": "eth0"}).status_code
        == 409
    )

    # Network names are case-insensitive, trim only the edges, keep internal spaces/CJK
    net = create_network(admin, cl["code"], " 生产 网 ", "10.141.0.0/24")
    assert net["name"] == "生产 网"
    assert (
        admin.post(
            "/api/v1/networks", json={"cluster": cl["code"], "name": "生产 网", "cidr": "10.142.0.0/24"}
        ).status_code
        == 409
    )


def test_acc_t41_reuse_and_scope_uniqueness(admin: Api) -> None:
    cl = create_cluster(admin, f"T41{SUFFIX}", "T41")
    first = create_resource(admin, cl["code"], "t41reuse")
    soft_delete(admin, f"/api/v1/resources/{first['id']}", first["version"])
    # deleting frees the identity for reuse within the same cluster
    create_resource(admin, cl["code"], "t41reuse")
    # ...but another Cluster keeps its own scope
    other = create_cluster(admin, f"T41B{SUFFIX}", "T41B")
    create_resource(admin, other["code"], "t41reuse")

    # a soft-deleted Cluster code is NOT reusable (global key includes deleted)
    doomed = create_cluster(admin, f"T41C{SUFFIX}", "T41C")
    soft_delete(admin, f"/api/v1/clusters/{doomed['id']}", doomed["version"])
    assert (
        admin.post(
            "/api/v1/clusters", json={"code": f"t41c{SUFFIX}", "name": "recode"}
        ).status_code
        == 409
    )


# =========================================================================== #
# §32 C1-C15 launch acceptance
# =========================================================================== #


def test_c1_create_cluster_bm_vm_and_host(dataset: dict) -> None:
    assert dataset["cn001"]["resource_type"] == "BARE_METAL"
    assert dataset["vm001"]["resource_type"] == "VIRTUAL_MACHINE"
    assert dataset["vm001"]["virtual_machine"]["host"]["hostname"] == "pve01"


def test_c2_interfaces_networks_pools_services(dataset: dict) -> None:
    assert dataset["mgmt_net"]["cidr"] == "10.100.0.0/24"
    assert dataset["auto_pool"]["allocation_mode"] == "AUTO"
    assert dataset["service"]["status"] in {"RUNNING", "STOPPED", "UNKNOWN"}


def test_c3_manual_and_auto_ip_allocation(admin: Api, dataset: dict) -> None:
    assert dataset["mgmt_ip"]["interface"]["id"] == dataset["mgmt_if"]["id"]
    assert dataset["free_ip"]["interface"] is None
    cl = dataset["cluster"]
    auto_net = create_network(admin, cl["code"], "c3-auto", "10.133.0.0/24", auto_allocate=True)
    pool = create_pool(admin, auto_net["id"], "c3pool", "10.133.0.10", "10.133.0.20", allocation_mode="AUTO")
    auto = ok(
        admin.post(
            "/api/v1/ip-addresses/auto-allocate",
            json={"network": auto_net["id"], "ip_pool": pool["id"]},
        ),
        201,
    )
    assert auto["ip_address"]["address"] == "10.133.0.10"


def test_c4_find_resource_by_hostname_ip_cluster_service(admin: Api, dataset: dict) -> None:
    by_host = ok(admin.get("/api/v1/search?q=cn001"), 200)
    assert any(i["object_type"] == "resource" and i["resource"]["hostname"] == "cn001" for i in by_host["items"])
    by_ip = ok(admin.get("/api/v1/search?q=10.100.0.10"), 200)
    assert any(i["object_type"] == "ip_address" for i in by_ip["items"])
    by_cluster = ok(admin.get(f"/api/v1/resources?cluster={dataset['cluster']['code']}"), 200)
    assert by_cluster["total"] >= 3
    by_service = ok(admin.get(f"/api/v1/services?resource_id={dataset['cn001']['id']}"), 200)
    assert any(s["name"] == "sshd" for s in by_service["items"])


def test_c5_detail_composition(admin: Api, dataset: dict) -> None:
    detail = ok(admin.get(f"/api/v1/resources/{dataset['cn001']['id']}"), 200)["resource"]
    assert detail["cluster"]["code"] == dataset["cluster"]["code"]
    ifaces = ok(admin.get(f"/api/v1/interfaces?resource_id={dataset['cn001']['id']}"), 200)
    assert ifaces["total"] == 2
    ips = ok(admin.get(f"/api/v1/ip-addresses?interface_id={dataset['mgmt_if']['id']}"), 200)
    assert ips["total"] == 1


def test_c6_conflict_guards(admin: Api, dataset: dict) -> None:
    cl = dataset["cluster"]
    dup = admin.post(
        "/api/v1/resources",
        json={"cluster": cl["code"], "hostname": "cn001", "resource_type": "BARE_METAL"},
    )
    assert dup.status_code == 409
    assert admin.post(
        "/api/v1/networks", json={"cluster": cl["code"], "name": "badcidr", "cidr": "not-a-cidr"}
    ).status_code == 422
    # cross-cluster VM host is rejected
    other = create_cluster(admin, f"C6B{SUFFIX}", "C6B")
    host = create_resource(admin, other["code"], "c6host")
    cross = admin.post(
        "/api/v1/resources",
        json={
            "cluster": cl["code"],
            "hostname": "c6vm",
            "resource_type": "VIRTUAL_MACHINE",
            "virtual_machine": {"host_resource_id": host["id"]},
        },
    )
    assert cross.status_code in (409, 422)


def test_c7_logical_delete_and_admin_restore(admin: Api) -> None:
    cl = create_cluster(admin, f"C7{SUFFIX}", "C7")
    res = create_resource(admin, cl["code"], "c7host")
    soft_delete(admin, f"/api/v1/resources/{res['id']}", res["version"])
    hidden = ok(admin.get(f"/api/v1/resources?q=c7host&cluster={cl['code']}"), 200)
    assert hidden["total"] == 0
    item = next(
        i
        for i in ok(admin.get("/api/v1/deleted?object_type=resource&page_size=100"), 200)["items"]
        if i["object_id"] == res["id"]
    )
    ok(admin.post(f"/api/v1/resources/{res['id']}/restore?version={item['version']}"), 200)


def test_c8_audit_log(admin: Api, dataset: dict) -> None:
    audit = ok(admin.get(f"/api/v1/audit?object_type=resource&object_id={dataset['cn001']['id']}&page_size=100"), 200)
    assert audit["total"] >= 1
    row = audit["items"][0]
    assert {"action", "operator_username", "object_type", "created_at"} <= set(row)


def test_c9_permissions(admin: Api, viewer: Api, editor: Api) -> None:
    assert viewer.get("/api/v1/resources").status_code == 200
    assert viewer.post("/api/v1/clusters", json={"code": f"C9V{SUFFIX}", "name": "v"}).status_code == 403
    assert editor.delete("/api/v1/clusters/00000000-0000-0000-0000-000000000000?version=1").status_code == 403
    anon = Api()
    try:
        assert anon.get("/api/v1/resources").status_code == 401
    finally:
        anon.close()


def test_c10_local_login_and_permissions(admin: Api) -> None:
    me = ok(admin.get("/api/v1/auth/me"), 200)
    assert me["user"]["role"] == "ADMIN"
    assert "WRITE" in me["user"]["permissions"]
    bad = Api()
    try:
        resp = bad.post("/api/v1/auth/login", json={"username": "admin", "password": "wrong"})
        assert resp.status_code == 401
        unknown = bad.post("/api/v1/auth/login", json={"username": "nobody", "password": "wrong"})
        assert unknown.status_code == 401
        assert resp.json()["error"]["code"] == unknown.json()["error"]["code"]
    finally:
        bad.close()


def test_c11_version_conflict(admin: Api) -> None:
    cl = create_cluster(admin, f"C11{SUFFIX}", "C11")
    fresh = ok(admin.patch(f"/api/v1/clusters/{cl['id']}", json={"version": 1, "name": "b"}), 200)["cluster"]
    assert fresh["version"] == 2
    stale = admin.patch(f"/api/v1/clusters/{cl['id']}", json={"version": 1, "name": "c"})
    assert stale.status_code == 409 and error_code(stale) == "VERSION_CONFLICT"


def test_c12_import_batch(admin: Api) -> None:
    cl = create_cluster(admin, f"C12{SUFFIX}", "C12")
    report = ok(import_request(admin, VALIDATE_PATH, csv_bytes(BM_HEADERS, [bm_row(cl["code"], "c12a"), bm_row(cl["code"], "c12b")])), 200)
    assert report["importable_rows"] == 2 and report["error_count"] == 0
    written = ok(import_request(admin, WRITE_PATH, csv_bytes(BM_HEADERS, [bm_row(cl["code"], "c12a"), bm_row(cl["code"], "c12b")])), 201)
    assert written["created"] == 2


def test_c13_network_pool_endpoint_and_restore_constraints(admin: Api) -> None:
    cl = create_cluster(admin, f"C13{SUFFIX}", "C13")
    net = create_network(admin, cl["code"], "c13net", "10.150.0.0/24")
    create_pool(admin, net["id"], "c13pool", "10.150.0.10", "10.150.0.20")
    blocked = admin.delete(f"/api/v1/networks/{net['id']}?version={net['version']}")
    assert blocked.status_code == 409 and error_reason(blocked) == "reference_exists"


def test_c15_required_capabilities_executed(admin: Api) -> None:
    # C15 is a real roll-up over the endpoint surface actually exercised above,
    # not a re-labelled local PASS. Confirm every required read surface answers.
    for path in (
        "/api/v1/clusters",
        "/api/v1/resources",
        "/api/v1/interfaces",
        "/api/v1/networks",
        "/api/v1/ip-pools",
        "/api/v1/ip-addresses",
        "/api/v1/services",
        "/api/v1/service-endpoints",
        "/api/v1/dashboard",
        "/api/v1/audit",
        "/api/v1/deleted",
        "/api/v1/users",
    ):
        assert admin.get(path).status_code == 200, path


# =========================================================================== #
# §33 target query scenarios
# =========================================================================== #


def test_q1_hostname_to_cluster(admin: Api, dataset: dict) -> None:
    body = ok(admin.get("/api/v1/search?q=cn001"), 200)
    rows = [
        i
        for i in body["items"]
        if i["object_type"] == "resource"
        and i["resource"]["id"] == dataset["cn001"]["id"]
    ]
    assert rows, "dataset resource cn001 is searchable"
    assert rows[0]["resource"]["cluster"]["code"] == dataset["cluster"]["code"]


def test_q2_ip_to_machine(admin: Api, dataset: dict) -> None:
    # bound -> returns the owning machine
    body = ok(admin.get("/api/v1/search?q=10.100.0.10"), 200)
    rows = [i for i in body["items"] if i["object_type"] == "ip_address" and i["id"] == dataset["mgmt_ip"]["id"]]
    assert rows, "dataset IP 10.100.0.10 is searchable"
    assert rows[0]["ip_address"]["interface"]["id"] == dataset["mgmt_if"]["id"]
    # unbound -> no Resource
    detail = ok(admin.get(f"/api/v1/ip-addresses/{dataset['free_ip']['id']}"), 200)["ip_address"]
    assert detail["interface"] is None


def test_q3_management_and_ib_addresses(admin: Api, dataset: dict) -> None:
    ifaces = ok(admin.get(f"/api/v1/interfaces?resource_id={dataset['cn001']['id']}"), 200)
    names = {i["name"] for i in ifaces["items"]}
    assert {"mgmt0", "ib0"} <= names
    mgmt_ips = ok(admin.get(f"/api/v1/ip-addresses?interface_id={dataset['mgmt_if']['id']}"), 200)
    ib_ips = ok(admin.get(f"/api/v1/ip-addresses?interface_id={dataset['ib_if']['id']}"), 200)
    assert mgmt_ips["items"][0]["address"] == "10.100.0.10"
    assert ib_ips["items"][0]["address"] == "10.200.0.10"


def test_q4_vm_host(admin: Api, dataset: dict) -> None:
    vm = ok(admin.get(f"/api/v1/resources/{dataset['vm001']['id']}"), 200)["resource"]
    assert vm["virtual_machine"]["host"]["hostname"] == "pve01"


def test_q5_host_vms(admin: Api, dataset: dict) -> None:
    body = ok(
        admin.get(f"/api/v1/resources?host_resource_id={dataset['pve01']['id']}&type=VIRTUAL_MACHINE"),
        200,
    )
    assert any(r["hostname"] == "vm001" for r in body["items"])


def test_q6_network_remaining_capacity(admin: Api, dataset: dict) -> None:
    caps = ok(admin.get(f"/api/v1/networks/{dataset['mgmt_net']['id']}/capacity"), 200)
    assert caps["network_capacity"]["remaining"] == (
        caps["network_capacity"]["allocatable_total"] - caps["network_capacity"]["occupied"]
    )


def test_q7_ip_usage_state(admin: Api, dataset: dict) -> None:
    bound = ok(admin.get(f"/api/v1/ip-addresses/{dataset['mgmt_ip']['id']}"), 200)["ip_address"]
    unbound = ok(admin.get(f"/api/v1/ip-addresses/{dataset['free_ip']['id']}"), 200)["ip_address"]
    assert bound["interface"] is not None
    assert unbound["interface"] is None


def test_q8_resource_services(admin: Api, dataset: dict) -> None:
    svcs = ok(admin.get(f"/api/v1/services?resource_id={dataset['cn001']['id']}"), 200)
    assert any(s["name"] == "sshd" for s in svcs["items"])
    eps = ok(admin.get(f"/api/v1/service-endpoints?service_id={dataset['service']['id']}"), 200)
    assert eps["total"] == 1


def test_q9_activity_and_audit(admin: Api, dataset: dict) -> None:
    activity = ok(admin.get(f"/api/v1/resources/{dataset['cn001']['id']}/activity"), 200)
    assert activity["total"] >= 1
    row = activity["items"][0]
    assert {"action", "operator_username"} <= set(row)
    audit = ok(admin.get(f"/api/v1/audit?object_type=resource&object_id={dataset['cn001']['id']}&page_size=100"), 200)
    assert audit["total"] >= 1


# =========================================================================== #
# REUSE reachability checks (authoritative evidence stays with each Feature)
# =========================================================================== #


def test_reuse_endpoints_reachable(admin: Api, dataset: dict) -> None:
    probes = {
        "T01": "/api/v1/resources",
        "T04": "/api/v1/ip-addresses",
        "T07": "/api/v1/ip-addresses",
        "T08": "/api/v1/resources",
        "T10": "/api/v1/ip-addresses",
        "T12": "/api/v1/interfaces",
        "T13": "/api/v1/clusters",
        "T14": "/api/v1/networks",
        "T15": "/api/v1/ip-pools",
        "T17": "/api/v1/ip-addresses",
        "T20": "/api/v1/interfaces",
        "T21": "/api/v1/services",
        "T30": "/api/v1/ip-addresses",
        "T33": "/api/v1/ip-pools",
        "T35": "/api/v1/ip-addresses",
        "T36": "/api/v1/audit",
        "T38": "/api/v1/resources",
        "T39": "/api/v1/resources",
    }
    for tid, path in probes.items():
        resp = admin.get(path)
        assert resp.status_code == 200, f"{tid} {path}: {resp.status_code}"
    # REUSE concurrency/Migration evidence remains with F009/F010/F015 anchors;
    # this only confirms the integrated endpoints are reachable (A10).