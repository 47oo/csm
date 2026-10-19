"""F023 资源+网卡+IP 三元组批量导入 — 独立验收集成测试（TEST 模式）。

验证 `docs/api/F023.md` v1（§6 26 列模板、§9 Network 解析、§12 原子性/锁序/归因）、
`docs/features/F023/product.md` A1–A10 与 `requirements-v3.md` revision 8 §24/§24.1
（T64–T72）。真实 PostgreSQL（`TEST_DATABASE_URL`，DB-D10 guard），复用 conftest 的
`auth_app`/`auth_session_factory`/`committed_engine`/`make_user` 与 F007/F010 的
helper。不复制开发者结果，独立断言可观察行为。

覆盖 PG-01…PG-14 与 U-01…U-07（纯逻辑直调）以及上限/性能（PERF）。
"""

from __future__ import annotations

import csv
import io
import ipaddress
import threading
import time
import tracemalloc

import pytest
from openpyxl import Workbook
from sqlalchemy import func, select, text

from app.api.v1 import imports as imports_api
from app.core.config import Settings
from app.core.errors import ImportInvalidFile, ImportValidationFailed
from app.models.audit_log import AuditLog
from app.services import resource_import
from app.services import resource_interface_ip_import as unified
from integration.test_ip_addresses import (  # noqa: F401  (reused helper/fixture)
    _cluster,
    _interface,
    _ip,
    _network,
    _operator,
    _pool,
    _resource,
    role_client_factory,
)

VALIDATE = "/api/v1/imports/resource-interfaces-ips/validate"
WRITE = "/api/v1/imports/resource-interfaces-ips"
TEMPLATES = "/api/v1/imports/resource-interfaces-ips/templates"

BM = "BARE_METAL"
VM = "VIRTUAL_MACHINE"

# Frozen 26-column order (Contract §6 / D03).
HEADERS = [
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

COUNT_TABLES = (
    "clusters",
    "resources",
    "bare_metal_details",
    "virtual_machine_details",
    "interfaces",
    "ip_addresses",
    "audit_logs",
)


# --- helpers -----------------------------------------------------------------


def _row(**values) -> list[str]:
    return ["" if values.get(h) is None else str(values.get(h)) for h in HEADERS]


def _csv_bytes(rows: list[list[str]], headers: list[str] | None = None) -> bytes:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(headers if headers is not None else HEADERS)
    for row in rows:
        writer.writerow(row)
    return buffer.getvalue().encode("utf-8")


def _xlsx_bytes(rows: list[list[str]], headers: list[str] | None = None) -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(headers if headers is not None else HEADERS)
    for row in rows:
        sheet.append(row)
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def _post(client, path, data, fmt="csv"):
    return client.post(
        path,
        files={"file": (f"import.{fmt}", data, "application/octet-stream")},
        data={"format": fmt},
    )


def _validate(client, rows, fmt="csv", headers=None):
    return _post(client, VALIDATE, _csv_bytes(rows, headers) if fmt == "csv" else _xlsx_bytes(rows, headers), fmt)


def _write(client, rows, fmt="csv", headers=None):
    return _post(client, WRITE, _csv_bytes(rows, headers) if fmt == "csv" else _xlsx_bytes(rows, headers), fmt)


def _counts(session) -> dict[str, int]:
    return {
        table: int(session.execute(text(f"SELECT count(*) FROM {table}")).scalar_one())
        for table in COUNT_TABLES
    }


def _find_error(payload: dict, field: str, row: int | None = None) -> dict | None:
    for error in payload["errors"]:
        if error["field"] == field and (row is None or error["row"] == row):
            return error
    return None


def _api_resource(client, cluster_code, hostname, resource_type="BARE_METAL", **overrides):
    body = {"cluster": cluster_code, "hostname": hostname, "resource_type": resource_type}
    body.update(overrides)
    resp = client.post("/api/v1/resources", json=body)
    assert resp.status_code == 201, resp.text
    return resp.json()["resource"]


def _ip_bindings(session):
    """Return {address: (interface_name, resource_hostname, network_id)} for undeleted IPs."""
    rows = session.execute(
        text(
            "SELECT host(ip.address), i.name, r.hostname, ip.network_id, "
            "masklen(ip.address) FROM ip_addresses ip "
            "LEFT JOIN interfaces i ON i.id = ip.interface_id "
            "LEFT JOIN resources r ON r.id = i.resource_id "
            "WHERE ip.deleted_at IS NULL ORDER BY host(ip.address)"
        )
    ).all()
    return {
        row[0]: {
            "interface": row[1],
            "resource": row[2],
            "network_id": str(row[3]),
            "masklen": row[4],
        }
        for row in rows
    }


# --- PG-01: multi-node / multi-row happy path --------------------------------


def test_pg01_multi_node_multi_row_happy_path(role_client_factory, auth_session_factory):
    editor, _, _ = role_client_factory("EDITOR")
    c = _cluster(editor, code="C1")
    net = _network(editor, c["id"], name="mgmt", cidr="10.0.0.0/24")

    rows = [
        _row(cluster=c["code"], hostname="node1", resource_type=BM, name="eth0", network="mgmt", ip="10.0.0.11"),
        _row(cluster=c["code"], hostname="node1", resource_type=BM, name="eth1", network="mgmt", ip="10.0.0.12"),
        _row(cluster=c["code"], hostname="node2", resource_type=BM, name="eth0", network="mgmt", ip="10.0.0.13/24"),
    ]
    with auth_session_factory() as session:
        before = _counts(session)
    resp = _write(editor, rows)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["created"] == 2
    assert body["total_rows"] == 3
    assert body["interfaces_created"] == 3
    assert body["ip_addresses_created"] == 3

    with auth_session_factory() as session:
        after = _counts(session)
        assert after["resources"] == before["resources"] + 2
        assert after["interfaces"] == before["interfaces"] + 3
        assert after["ip_addresses"] == before["ip_addresses"] + 3
        # one CREATE audit per created object: 2 resources + 3 interfaces + 3 ips
        assert after["audit_logs"] == before["audit_logs"] + 8

        bindings = _ip_bindings(session)
        assert bindings["10.0.0.11"]["interface"] == "eth0"
        assert bindings["10.0.0.11"]["resource"] == "node1"
        assert bindings["10.0.0.12"]["interface"] == "eth1"
        assert bindings["10.0.0.13"]["resource"] == "node2"
        # resolved Network is the template-referenced one; mask stripped on store
        for address in ("10.0.0.11", "10.0.0.12", "10.0.0.13"):
            assert bindings[address]["network_id"] == net["id"]
            assert bindings[address]["masklen"] == 32

        creates = session.execute(
            select(AuditLog.object_type, func.count())
            .where(AuditLog.action == "CREATE")
            .group_by(AuditLog.object_type)
        ).all()
        by_type = {row[0]: row[1] for row in creates}
        assert by_type.get("resource") == 2
        assert by_type.get("interface") == 3
        assert by_type.get("ip_address") == 3


# --- PG-02: csv / xlsx identical ---------------------------------------------


def test_pg02_csv_xlsx_identical(role_client_factory):
    editor, _, _ = role_client_factory("EDITOR")
    c = _cluster(editor, code="C1")
    net = _network(editor, c["id"], name="mgmt", cidr="10.0.0.0/24")

    valid = [
        _row(cluster=c["code"], hostname="n1", resource_type=BM, name="eth0", network="mgmt", ip="10.0.0.11"),
        _row(cluster=c["code"], hostname="n2", resource_type=BM, name="eth0", network="mgmt", ip="10.0.0.99"),
    ]
    csv_payload = _validate(editor, valid, "csv").json()
    xlsx_payload = _validate(editor, valid, "xlsx").json()
    assert csv_payload["format"] == "csv" and xlsx_payload["format"] == "xlsx"
    assert {k: v for k, v in csv_payload.items() if k != "format"} == {
        k: v for k, v in xlsx_payload.items() if k != "format"
    }

    # error parity: an out-of-CIDR row gives the same error shape in both formats
    error_rows = [
        _row(cluster=c["code"], hostname="n3", resource_type=BM, name="eth0", network="mgmt", ip="10.9.9.9")
    ]
    csv_err = _validate(editor, error_rows, "csv").json()
    xlsx_err = _validate(editor, error_rows, "xlsx").json()
    assert {k: v for k, v in csv_err.items() if k != "format"} == {
        k: v for k, v in xlsx_err.items() if k != "format"
    }
    assert _find_error(csv_err, "ip", 2) is not None

    assert _write(editor, valid, "csv").status_code == 201
    xlsx_valid = [
        _row(cluster=c["code"], hostname="n4", resource_type=BM, name="eth0", network="mgmt", ip="10.0.0.21")
    ]
    assert _write(editor, xlsx_valid, "xlsx").status_code == 201
    listing = editor.get("/api/v1/resources").json()
    assert {i["hostname"] for i in listing["items"]} == {"n1", "n2", "n4"}


# --- PG-03: IP ownership and cross-Cluster -----------------------------------


def test_pg03_ip_ownership_and_cross_cluster(role_client_factory):
    editor, _, _ = role_client_factory("EDITOR")
    c1 = _cluster(editor, code="C1")
    c2 = _cluster(editor, code="C2")
    _network(editor, c1["id"], name="net1", cidr="10.0.0.0/24")
    _network(editor, c2["id"], name="net2", cidr="10.1.0.0/24")

    # in-CIDR: ok; out-of-CIDR: error ip; foreign network name: error network
    rows = [
        _row(cluster=c1["code"], hostname="ok1", resource_type=BM, name="eth0", network="net1", ip="10.0.0.11"),
        _row(cluster=c1["code"], hostname="bad1", resource_type=BM, name="eth0", network="net1", ip="10.1.0.11"),
        _row(cluster=c1["code"], hostname="bad2", resource_type=BM, name="eth0", network="net2", ip="10.0.0.12"),
    ]
    payload = _validate(editor, rows).json()
    assert _find_error(payload, "ip", 3) is not None
    assert _find_error(payload, "network", 4) is not None

    # /mask resolved in another cluster does not match this cluster -> ip error
    foreign_mask = _validate(
        editor,
        [_row(cluster=c1["code"], hostname="bad3", resource_type=BM, name="eth0", ip="10.1.0.11/24")],
    ).json()
    assert _find_error(foreign_mask, "ip", 2) is not None

    resp = _write(
        editor,
        [_row(cluster=c1["code"], hostname="ok1", resource_type=BM, name="eth0", network="net1", ip="10.0.0.11")],
    )
    assert resp.status_code == 201
    listed = editor.get("/api/v1/ip-addresses", params={"address": "10.0.0.11"}).json()
    item = listed["items"][0]
    assert item["cluster"]["code"] == "C1"
    assert item["network"]["cidr"] == "10.0.0.0/24"


# --- PG-04: Network resolution matrix ----------------------------------------


def test_pg04_network_resolution_matrix(role_client_factory):
    editor, _, _ = role_client_factory("EDITOR")
    admin, _, _ = role_client_factory("ADMIN")
    c = _cluster(editor, code="C1")
    by_name = _network(editor, c["id"], name="MGMT", cidr="10.0.0.0/16")
    by_cidr = _network(editor, c["id"], name="net-cidr", cidr="10.1.0.0/24")
    by_mask = _network(editor, c["id"], name="net-mask", cidr="10.2.0.0/24")
    inactive = _network(editor, c["id"], name="inactive", cidr="10.3.0.0/24", status="INACTIVE")
    soft = _network(editor, c["id"], name="deleted", cidr="10.4.0.0/24")
    assert admin.delete(
        f"/api/v1/networks/{soft['id']}", params={"version": soft["version"]}
    ).status_code == 204

    # name (case-insensitive) / CIDR / /mask all resolve
    payload = _validate(
        editor,
        [
            _row(cluster=c["code"], hostname="a", resource_type=BM, name="eth0", network="mgmt", ip="10.0.0.5"),
            _row(cluster=c["code"], hostname="b", resource_type=BM, name="eth0", network="10.1.0.0/24", ip="10.1.0.5"),
            _row(cluster=c["code"], hostname="d", resource_type=BM, name="eth0", ip="10.2.0.5/24"),
        ],
    ).json()
    assert payload["error_count"] == 0, payload["errors"]
    assert _write(
        editor,
        [
            _row(cluster=c["code"], hostname="a", resource_type=BM, name="eth0", network="mgmt", ip="10.0.0.5"),
            _row(cluster=c["code"], hostname="b", resource_type=BM, name="eth0", network="10.1.0.0/24", ip="10.1.0.5"),
            _row(cluster=c["code"], hostname="d", resource_type=BM, name="eth0", ip="10.2.0.5/24"),
        ],
    ).status_code == 201

    # INACTIVE / soft-deleted / missing network / no mask -> row errors
    errors = _validate(
        editor,
        [
            _row(cluster=c["code"], hostname="e", resource_type=BM, name="eth0", network="inactive", ip="10.3.0.5"),
            _row(cluster=c["code"], hostname="f", resource_type=BM, name="eth0", network="deleted", ip="10.4.0.5"),
            _row(cluster=c["code"], hostname="g", resource_type=BM, name="eth0", ip="10.0.0.6"),
            _row(cluster=c["code"], hostname="h", resource_type=BM, name="eth0", network="does-not-exist", ip="10.0.0.7"),
        ],
    ).json()
    assert _find_error(errors, "network", 2) is not None  # INACTIVE
    assert _find_error(errors, "network", 3) is not None  # soft deleted
    assert _find_error(errors, "network", 4) is not None  # no network, no mask
    assert _find_error(errors, "network", 5) is not None  # name missing, no fallback


def test_pg04b_network_column_priority_over_mask(role_client_factory, auth_session_factory):
    """A2/§9: a non-empty ``network`` column is authoritative; no /mask fallback."""
    editor, _, _ = role_client_factory("EDITOR")
    c = _cluster(editor, code="C1")
    net_a = _network(editor, c["id"], name="a", cidr="10.0.0.0/16")
    _network(editor, c["id"], name="b", cidr="10.5.0.0/24")

    # ``network`` column names 'a'; the /mask would denote a non-existent
    # 10.0.5.0/24, yet resolution succeeds via the name (name is authoritative).
    rows = [
        _row(cluster=c["code"], hostname="prio", resource_type=BM, name="eth0", network="a", ip="10.0.5.5/24"),
    ]
    assert _write(editor, rows).status_code == 201
    with auth_session_factory() as session:
        network_id = session.execute(
            text(
                "SELECT ip.network_id FROM ip_addresses ip "
                "JOIN interfaces i ON i.id = ip.interface_id "
                "JOIN resources r ON r.id = i.resource_id WHERE r.hostname='prio'"
            )
        ).scalar_one()
    assert str(network_id) == net_a["id"]  # resolved by name 'a', not the /mask

    # name not found -> error, even though the /mask matches an existing network
    errors = _validate(
        editor,
        [_row(cluster=c["code"], hostname="prio2", resource_type=BM, name="eth0", network="missing", ip="10.5.0.9/24")],
    ).json()
    assert _find_error(errors, "network", 2) is not None


# --- PG-05: concurrent overlap (hostname / IP) -------------------------------


def _write_service(session, operator, rows):
    data = _csv_bytes(rows)
    return unified.write_import(session, operator, data, "csv", Settings(_env_file=None))


def _run_pair(fn_a, fn_b):
    barrier = threading.Barrier(2)
    results: list[object] = []
    lock = threading.Lock()

    def runner(fn):
        barrier.wait(timeout=10)
        try:
            outcome = fn()
        except Exception as exc:  # noqa: BLE001 - collect outcome
            outcome = exc
        with lock:
            results.append(outcome)

    threads = [threading.Thread(target=runner, args=(fn,)) for fn in (fn_a, fn_b)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=60)
    return results


def test_pg05a_concurrent_overlapping_hostname(role_client_factory, auth_session_factory):
    admin, user, _ = role_client_factory("ADMIN")
    c = _cluster(admin, code="C1")
    _network(admin, c["id"], name="mgmt", cidr="10.0.0.0/24")
    operator = _operator(user)

    def make(ip):
        def _fn():
            session = auth_session_factory()
            try:
                return _write_service(
                    session,
                    operator,
                    [_row(cluster=c["code"], hostname="cnDup", resource_type=BM, name="eth0", network="mgmt", ip=ip)],
                )
            finally:
                session.close()

        return _fn

    results = _run_pair(make("10.0.0.11"), make("10.0.0.12"))
    successes = [r for r in results if isinstance(r, tuple)]
    failures = [r for r in results if isinstance(r, ImportValidationFailed)]
    assert len(successes) == 1, results
    assert len(failures) == 1, results
    assert _find_error(failures[0].details, "hostname") is not None

    with auth_session_factory() as session:
        counts = _counts(session)
    assert counts["resources"] == 1
    assert counts["ip_addresses"] == 1
    assert counts["interfaces"] == 1


def test_pg05b_concurrent_overlapping_ip(role_client_factory, auth_session_factory):
    admin, user, _ = role_client_factory("ADMIN")
    c = _cluster(admin, code="C1")
    _network(admin, c["id"], name="mgmt", cidr="10.0.0.0/24")
    operator = _operator(user)

    def make(hostname):
        def _fn():
            session = auth_session_factory()
            try:
                return _write_service(
                    session,
                    operator,
                    [_row(cluster=c["code"], hostname=hostname, resource_type=BM, name="eth0", network="mgmt", ip="10.0.0.50")],
                )
            finally:
                session.close()

        return _fn

    with auth_session_factory() as session:
        baseline = _counts(session)
    results = _run_pair(make("cnA"), make("cnB"))
    successes = [r for r in results if isinstance(r, tuple)]
    failures = [r for r in results if isinstance(r, ImportValidationFailed)]
    assert len(successes) == 1, results
    assert len(failures) == 1, results

    with auth_session_factory() as session:
        counts = _counts(session)
    assert counts["resources"] == baseline["resources"] + 1
    assert counts["interfaces"] == baseline["interfaces"] + 1
    assert counts["ip_addresses"] == baseline["ip_addresses"] + 1
    assert counts["audit_logs"] == baseline["audit_logs"] + 3  # one winner only


def test_pg05c_concurrent_ip_loser_attribution(role_client_factory, auth_session_factory):
    """PG-05/§11/DR-422: the losing overlapping-IP batch must report ``field=ip``.

    The concurrent loser is rejected inside the SAVEPOINT by
    ``prepare_ip_address`` raising ``Conflict.unique_conflict("address")``; the
    import layer must attribute it to the template ``ip`` column.
    """
    admin, user, _ = role_client_factory("ADMIN")
    c = _cluster(admin, code="C1")
    _network(admin, c["id"], name="mgmt", cidr="10.0.0.0/24")
    operator = _operator(user)

    def make(hostname):
        def _fn():
            session = auth_session_factory()
            try:
                return _write_service(
                    session,
                    operator,
                    [_row(cluster=c["code"], hostname=hostname, resource_type=BM, name="eth0", network="mgmt", ip="10.0.0.51")],
                )
            finally:
                session.close()

        return _fn

    results = _run_pair(make("cnC"), make("cnD"))
    failures = [r for r in results if isinstance(r, ImportValidationFailed)]
    assert len(failures) == 1, results
    assert _find_error(failures[0].details, "ip") is not None, failures[0].details


# --- PG-06: uniqueness and §11.1 boundaries ----------------------------------


def test_pg06_uniqueness_and_allocatable_boundaries(role_client_factory, auth_session_factory):
    editor, _, _ = role_client_factory("EDITOR")
    c = _cluster(editor, code="C1")
    net = _network(editor, c["id"], name="mgmt", cidr="10.0.0.0/24")
    # existing conflicts
    _api_resource(editor, c["code"], "existing")
    _ip(editor, net["id"], "10.0.0.50")

    payload = _validate(
        editor,
        [
            # file-internal duplicate ip
            _row(cluster=c["code"], hostname="dup1", resource_type=BM, name="eth0", network="mgmt", ip="10.0.0.20"),
            _row(cluster=c["code"], hostname="dup2", resource_type=BM, name="eth0", network="mgmt", ip="10.0.0.20"),
            # existing hostname conflict
            _row(cluster=c["code"], hostname="existing", resource_type=BM, name="eth0", network="mgmt", ip="10.0.0.21"),
            # existing ip conflict
            _row(cluster=c["code"], hostname="new1", resource_type=BM, name="eth0", network="mgmt", ip="10.0.0.50"),
        ],
    ).json()
    dup = _find_error(payload, "ip", 3)
    assert dup is not None and dup["related_row"] == 2
    assert _find_error(payload, "hostname", 4) is not None
    assert _find_error(payload, "ip", 5) is not None

    # case folding: CN001 / cn001 merge into one resource (non-error)
    case_payload = _validate(
        editor,
        [
            _row(cluster=c["code"], hostname="CN001", resource_type=BM, name="eth0", network="mgmt", ip="10.0.0.31"),
            _row(cluster=c["code"], hostname="cn001", resource_type=BM, name="eth1", network="mgmt", ip="10.0.0.32"),
        ],
    ).json()
    assert case_payload["error_count"] == 0

    # /30 network/broadcast rejected, usable accepted
    n30 = _network(editor, c["id"], name="n30", cidr="10.10.0.0/30")
    b30 = _validate(
        editor,
        [
            _row(cluster=c["code"], hostname="t30", resource_type=BM, name="eth0", network="n30", ip="10.10.0.1"),
            _row(cluster=c["code"], hostname="b30", resource_type=BM, name="eth0", network="n30", ip="10.10.0.0"),
            _row(cluster=c["code"], hostname="b30b", resource_type=BM, name="eth0", network="n30", ip="10.10.0.3"),
        ],
    ).json()
    assert _find_error(b30, "ip", 2) is None
    assert _find_error(b30, "ip", 3) is not None
    assert _find_error(b30, "ip", 4) is not None

    # /31 both addresses usable; /32 single address usable
    n31 = _network(editor, c["id"], name="n31", cidr="10.11.0.0/31")
    n32 = _network(editor, c["id"], name="n32", cidr="10.12.0.0/32")
    small = _validate(
        editor,
        [
            _row(cluster=c["code"], hostname="t31", resource_type=BM, name="eth0", network="n31", ip="10.11.0.1"),
            _row(cluster=c["code"], hostname="t32", resource_type=BM, name="eth0", network="n32", ip="10.12.0.0"),
        ],
    ).json()
    assert small["error_count"] == 0, small["errors"]

    # gateway excluded; next address accepted
    ngw = _network(editor, c["id"], name="ngw", cidr="10.13.0.0/24", gateway="10.13.0.1")
    gw = _validate(
        editor,
        [
            _row(cluster=c["code"], hostname="gw", resource_type=BM, name="eth0", network="ngw", ip="10.13.0.1"),
            _row(cluster=c["code"], hostname="gw2", resource_type=BM, name="eth0", network="ngw", ip="10.13.0.2"),
        ],
    ).json()
    assert _find_error(gw, "ip", 2) is not None
    assert _find_error(gw, "ip", 3) is None

    # RESERVED pool range excluded; outside accepted
    nres = _network(editor, c["id"], name="nres", cidr="10.14.0.0/24")
    _pool(editor, nres["id"], name="res", start="10.14.0.10", end="10.14.0.20", allocation_mode="RESERVED")
    res = _validate(
        editor,
        [
            _row(cluster=c["code"], hostname="res1", resource_type=BM, name="eth0", network="nres", ip="10.14.0.10"),
            _row(cluster=c["code"], hostname="res2", resource_type=BM, name="eth0", network="nres", ip="10.14.0.30"),
        ],
    ).json()
    assert _find_error(res, "ip", 2) is not None
    assert _find_error(res, "ip", 3) is None


# --- PG-07: VM Host four conditions + batch-external snapshot ----------------


def test_pg07_vm_host_conditions_and_batch_external(role_client_factory, auth_session_factory):
    editor, _, _ = role_client_factory("EDITOR")
    admin, _, _ = role_client_factory("ADMIN")
    c1 = _cluster(editor, code="C1")
    c2 = _cluster(editor, code="C2")
    _network(editor, c1["id"], name="mgmt", cidr="10.0.0.0/24")
    bm = _api_resource(editor, c1["code"], "bm1")
    other_bm = _api_resource(editor, c2["code"], "bm2")
    vm_host = _api_resource(
        editor, c1["code"], "vmhost", resource_type=VM, virtual_machine={"host_resource_id": bm["id"]}
    )
    deleted = _api_resource(editor, c1["code"], "bm3")
    assert admin.delete(
        f"/api/v1/resources/{deleted['id']}", params={"version": deleted["version"]}
    ).status_code == 204

    payload = _validate(
        editor,
        [
            _row(cluster=c1["code"], hostname="v1", resource_type=VM, host="missing", name="eth0", network="mgmt", ip="10.0.0.11"),
            _row(cluster=c1["code"], hostname="v2", resource_type=VM, host=other_bm["id"], name="eth0", network="mgmt", ip="10.0.0.12"),
            _row(cluster=c1["code"], hostname="v3", resource_type=VM, host=vm_host["id"], name="eth0", network="mgmt", ip="10.0.0.13"),
            _row(cluster=c1["code"], hostname="v4", resource_type=VM, host="bm3", name="eth0", network="mgmt", ip="10.0.0.14"),
        ],
    ).json()
    for index in (2, 3, 4, 5):
        assert _find_error(payload, "host", index) is not None, (index, payload["errors"])

    # valid VM referencing a pre-existing BM host succeeds
    ok = _write(
        editor,
        [_row(cluster=c1["code"], hostname="vok", resource_type=VM, host="bm1", name="eth0", network="mgmt", ip="10.0.0.21")],
    )
    assert ok.status_code == 201, ok.text

    # a BM row created inside the same file cannot be a host (batch-external snapshot)
    same_file = [
        _row(cluster=c1["code"], hostname="cn100", resource_type=BM, name="eth0", network="mgmt", ip="10.0.0.31"),
        _row(cluster=c1["code"], hostname="vm100", resource_type=VM, host="cn100", name="eth0", network="mgmt", ip="10.0.0.32"),
    ]
    resp = _write(editor, same_file)
    assert resp.status_code == 422
    assert _find_error(resp.json()["error"]["details"], "host", 3) is not None
    assert editor.get("/api/v1/resources", params={"q": "cn100"}).json()["total"] == 0
    assert editor.get("/api/v1/resources", params={"q": "vm100"}).json()["total"] == 0


# --- PG-08: file-internal duplicate / existing conflict two-phase ------------


def test_pg08_two_phase_consistency(role_client_factory, auth_session_factory):
    editor, _, _ = role_client_factory("EDITOR")
    c = _cluster(editor, code="C1")
    _network(editor, c["id"], name="mgmt", cidr="10.0.0.0/24")
    existing = _api_resource(editor, c["code"], "cn001")

    dup_rows = [
        _row(cluster=c["code"], hostname="d1", resource_type=BM, name="eth0", network="mgmt", ip="10.0.0.11"),
        _row(cluster=c["code"], hostname="d2", resource_type=BM, name="eth0", network="mgmt", ip="10.0.0.11"),
    ]
    validate_payload = _validate(editor, dup_rows).json()
    write_details = _write(editor, dup_rows).json()["error"]["details"]
    v_dup = _find_error(validate_payload, "ip", 3)
    w_dup = _find_error(write_details, "ip", 3)
    assert v_dup is not None and w_dup is not None
    assert v_dup["related_row"] == w_dup["related_row"] == 2

    conflict_rows = [
        _row(cluster=c["code"], hostname="cn001", resource_type=BM, role="GPU", name="eth0", network="mgmt", ip="10.0.0.12"),
    ]
    v_conf = _validate(editor, conflict_rows).json()
    w_conf = _write(editor, conflict_rows).json()["error"]["details"]
    assert _find_error(v_conf, "hostname", 2) is not None
    assert _find_error(w_conf, "hostname", 2) is not None
    with auth_session_factory() as session:
        row = session.execute(
            text("SELECT role, version FROM resources WHERE id = :id"), {"id": existing["id"]}
        ).one()
        assert row[0] == "OTHER" and row[1] == 1
        updates = session.execute(
            text("SELECT count(*) FROM audit_logs WHERE action = 'UPDATE'")
        ).scalar_one()
        assert updates == 0


# --- PG-09: disabled-segment real boundary -----------------------------------


def test_pg09_disabled_segments_boundary(role_client_factory):
    editor, _, _ = role_client_factory("EDITOR")
    c = _cluster(editor, code="C1")
    _network(editor, c["id"], name="loop", cidr="127.0.0.0/24")
    _network(editor, c["id"], name="link", cidr="169.254.0.0/16")
    _network(editor, c["id"], name="mcast", cidr="224.0.0.0/24")

    payload = _validate(
        editor,
        [
            _row(cluster=c["code"], hostname="d1", resource_type=BM, name="eth0", network="loop", ip="127.0.0.5"),
            _row(cluster=c["code"], hostname="d2", resource_type=BM, name="eth0", network="link", ip="169.254.0.5"),
            _row(cluster=c["code"], hostname="d3", resource_type=BM, name="eth0", network="mcast", ip="224.0.0.5"),
        ],
    ).json()
    for index in (2, 3, 4):
        error = _find_error(payload, "ip", index)
        assert error is not None, (index, payload["errors"])
    # whole batch rejected; nothing written
    assert _write(
        editor,
        [_row(cluster=c["code"], hostname="d1", resource_type=BM, name="eth0", network="loop", ip="127.0.0.5")],
    ).status_code == 422


# --- PG-10: whole-batch rollback zero residue --------------------------------


def test_pg10_whole_batch_rollback_zero_residue(role_client_factory, auth_session_factory):
    editor, _, _ = role_client_factory("EDITOR")
    c = _cluster(editor, code="C1")
    _network(editor, c["id"], name="mgmt", cidr="10.0.0.0/24")

    rows = [
        _row(cluster=c["code"], hostname="good1", resource_type=BM, name="eth0", network="mgmt", ip="10.0.0.11"),
        _row(cluster=c["code"], hostname="good2", resource_type=BM, name="eth0", network="mgmt", ip="10.0.0.12"),
        _row(cluster="MISSING", hostname="bad", resource_type=BM, name="eth0", network="mgmt", ip="10.0.0.13"),
    ]
    with auth_session_factory() as session:
        before = _counts(session)
    resp = _write(editor, rows)
    assert resp.status_code == 422
    details = resp.json()["error"]["details"]
    assert details["total_rows"] == 3
    assert details["importable_rows"] == 2
    assert details["error_count"] == 1
    with auth_session_factory() as session:
        after = _counts(session)
    assert before == after


# --- PG-11: write-time re-validation -----------------------------------------


def test_pg11_write_revalidates_after_state_change(role_client_factory):
    editor, _, _ = role_client_factory("EDITOR")
    c = _cluster(editor, code="C1")
    _network(editor, c["id"], name="mgmt", cidr="10.0.0.0/24")
    rows = [
        _row(cluster=c["code"], hostname="cn001", resource_type=BM, name="eth0", network="mgmt", ip="10.0.0.11")
    ]
    assert _validate(editor, rows).json()["errors"] == []

    # external actor occupies the hostname between validate and write
    _api_resource(editor, c["code"], "cn001")

    resp = _write(editor, rows)
    assert resp.status_code == 422
    details = resp.json()["error"]["details"]
    assert _find_error(details, "hostname", 2) is not None
    assert editor.get("/api/v1/resources", params={"q": "cn001"}).json()["total"] == 1


def test_pg11b_write_revalidates_ip_conflict(role_client_factory):
    editor, _, _ = role_client_factory("EDITOR")
    c = _cluster(editor, code="C1")
    net = _network(editor, c["id"], name="mgmt", cidr="10.0.0.0/24")
    rows = [
        _row(cluster=c["code"], hostname="cn010", resource_type=BM, name="eth0", network="mgmt", ip="10.0.0.11")
    ]
    assert _validate(editor, rows).json()["errors"] == []
    _ip(editor, net["id"], "10.0.0.11")
    resp = _write(editor, rows)
    assert resp.status_code == 422
    assert _find_error(resp.json()["error"]["details"], "ip", 2) is not None
    assert editor.get("/api/v1/resources", params={"q": "cn010"}).json()["total"] == 0


# --- PG-12: normalisation / Service Layer consistency (A8/T71) ----------------


def test_pg12_import_matches_api_uniqueness(role_client_factory, auth_session_factory):
    editor, _, _ = role_client_factory("EDITOR")
    c = _cluster(editor, code="C1")
    net = _network(editor, c["id"], name="mgmt", cidr="10.0.0.0/24")

    # hostname normalisation: mixed case + surrounding spaces stored folded
    ok = _write(
        editor,
        [_row(cluster=c["code"], hostname="  NODE-A  ", resource_type=BM, name="eth0", network="mgmt", ip="10.0.0.11")],
    )
    assert ok.status_code == 201, ok.text
    created = editor.get("/api/v1/resources", params={"q": "node-a"}).json()["items"][0]
    assert created["hostname"] == "node-a"

    # API create on the same hostname now conflicts (same uniqueness scope)
    dup = editor.post(
        "/api/v1/resources",
        json={"cluster": c["code"], "hostname": "NODE-A", "resource_type": "BARE_METAL"},
    )
    assert dup.status_code == 409

    # interface name uniqueness: import created eth0; API same-name -> 409
    iface = editor.get("/api/v1/interfaces", params={"resource_id": created["id"]}).json()["items"][0]
    assert iface["name"] == "eth0"
    dup_iface = editor.post("/api/v1/interfaces", json={"resource": created["id"], "name": "eth0"})
    assert dup_iface.status_code == 409

    # ip uniqueness: API allocating the imported address -> 409
    dup_ip = editor.post("/api/v1/ip-addresses", json={"network": net["id"], "address": "10.0.0.11"})
    assert dup_ip.status_code == 409


# --- PG-13: group merge consistency ------------------------------------------


def test_pg13_group_merge_consistency(role_client_factory):
    editor, _, _ = role_client_factory("EDITOR")
    c = _cluster(editor, code="C1")
    _network(editor, c["id"], name="mgmt", cidr="10.0.0.0/24")

    # resource-level conflict: role differs across rows of the same hostname
    role_rows = [
        _row(cluster=c["code"], hostname="m1", resource_type=BM, role="COMPUTE", name="eth0", network="mgmt", ip="10.0.0.11"),
        _row(cluster=c["code"], hostname="m1", resource_type=BM, role="STORAGE", name="eth1", network="mgmt", ip="10.0.0.12"),
    ]
    payload = _validate(editor, role_rows).json()
    conflict = _find_error(payload, "role", 3)
    assert conflict is not None and conflict["related_row"] == 2

    # interface-level conflict: mtu differs across rows sharing an interface name
    iface_rows = [
        _row(cluster=c["code"], hostname="m2", resource_type=BM, name="eth0", mtu="9000", network="mgmt", ip="10.0.0.21"),
        _row(cluster=c["code"], hostname="m2", resource_type=BM, name="eth0", mtu="1500", network="mgmt", ip="10.0.0.22"),
    ]
    payload2 = _validate(editor, iface_rows).json()
    iface_conflict = _find_error(payload2, "mtu", 3)
    assert iface_conflict is not None and iface_conflict["related_row"] == 2

    # resource_type within a group must be consistent (both rows valid so the
    # group-level conflict is aggregated)
    host = _api_resource(editor, c["code"], "hostm3")
    type_rows = [
        _row(cluster=c["code"], hostname="m3", resource_type=BM, name="eth0", network="mgmt", ip="10.0.0.31"),
        _row(cluster=c["code"], hostname="m3", resource_type=VM, host="hostm3", name="eth1", network="mgmt", ip="10.0.0.32"),
    ]
    payload3 = _validate(editor, type_rows).json()
    assert _find_error(payload3, "resource_type", 3) is not None

    # same value on both rows / only one row -> accepted, merge
    ok_rows = [
        _row(cluster=c["code"], hostname="m4", resource_type=BM, role="COMPUTE", name="eth0", network="mgmt", ip="10.0.0.41"),
        _row(cluster=c["code"], hostname="m4", resource_type=BM, name="eth0", network="mgmt", ip="10.0.0.42"),
    ]
    assert _validate(editor, ok_rows).json()["error_count"] == 0
    assert _write(editor, ok_rows).status_code == 201


# --- PG-14: permissions / templates / request shape --------------------------


def test_pg14_permissions_templates_shape(role_client_factory, auth_app, monkeypatch):
    from fastapi.testclient import TestClient

    valid = _csv_bytes([_row(cluster="C1", hostname="h", resource_type=BM, name="eth0", ip="10.0.0.1")])

    with TestClient(auth_app) as anon:
        assert _post(anon, VALIDATE, valid).status_code == 401
        assert _post(anon, WRITE, valid).status_code == 401
        assert anon.get(TEMPLATES).status_code == 401

    viewer, _, _ = role_client_factory("VIEWER")
    assert _post(viewer, VALIDATE, valid).status_code == 403
    assert _post(viewer, WRITE, valid).status_code == 403
    assert _post(viewer, VALIDATE, valid).json()["error"]["details"] == {"reason": "permission"}

    templates = viewer.get(TEMPLATES)
    assert templates.status_code == 200
    template = templates.json()["template"]
    assert template["key"] == "resource_interfaces_ips"
    columns = template["columns"]
    assert [c["name"] for c in columns] == HEADERS
    assert len(columns) == 26
    cluster_col = columns[0]
    assert cluster_col["required"] is True
    assert set(cluster_col["applies_to"]) == {BM, VM}
    host_col = next(c for c in columns if c["name"] == "host")
    assert host_col["required"] is True and host_col["applies_to"] == [VM]
    memory = next(c for c in columns if c["name"] == "memory_mb")
    assert memory["unit"] == "MiB" and set(memory["applies_to"]) == {BM, VM}
    ip_col = next(c for c in columns if c["name"] == "ip")
    assert ip_col["required"] is True
    name_col = next(c for c in columns if c["name"] == "name")
    assert name_col["required"] is True

    editor, _, _ = role_client_factory("EDITOR")
    _cluster(editor, code="C1")

    # format shape -> 422 VALIDATION_ERROR field=format
    bad = editor.post(
        WRITE,
        files={"file": ("x.xls", valid, "application/octet-stream")},
        data={"format": "xls"},
    )
    assert bad.status_code == 422
    assert bad.json()["error"]["code"] == "VALIDATION_ERROR"
    assert bad.json()["error"]["details"]["fields"][0]["field"] == "format"

    # header errors
    unknown = _validate(editor, [], headers=HEADERS + ["bogus"])
    assert unknown.status_code == 422
    assert unknown.json()["error"]["code"] == "IMPORT_INVALID_FILE"
    assert unknown.json()["error"]["details"]["reason"] == "unknown_columns"
    missing = _validate(editor, [], headers=[h for h in HEADERS if h != "ip"])
    assert missing.json()["error"]["details"]["reason"] == "missing_columns"
    reorder = _validate(editor, [], headers=list(reversed(HEADERS)))
    assert reorder.json()["error"]["details"]["reason"] == "column_order"

    # 413 file size / row limit (no partial import)
    small = Settings(_env_file=None, import_max_file_bytes=10)
    monkeypatch.setattr(imports_api, "get_settings", lambda: small)
    too_large = _write(editor, [_row(cluster="C1", hostname="h", resource_type=BM, name="eth0", ip="10.0.0.1")])
    assert too_large.status_code == 413
    assert too_large.json()["error"]["code"] == "IMPORT_FILE_TOO_LARGE"

    limited = Settings(_env_file=None, import_max_rows=1)
    monkeypatch.setattr(imports_api, "get_settings", lambda: limited)
    two = [
        _row(cluster="C1", hostname="h1", resource_type=BM, name="eth0", ip="10.0.0.1"),
        _row(cluster="C1", hostname="h2", resource_type=BM, name="eth0", ip="10.0.0.2"),
    ]
    over = _write(editor, two)
    assert over.status_code == 413
    assert over.json()["error"]["code"] == "IMPORT_ROW_LIMIT_EXCEEDED"

    # undefined path / method
    assert editor.get("/api/v1/imports/resource-interfaces-ips/nope").status_code == 404
    assert editor.get(VALIDATE).status_code == 405
    assert editor.get(WRITE).status_code == 405
    assert editor.post(TEMPLATES).status_code == 405


# =============================================================================
# U-01…U-07: pure-logic direct calls (no DB required)
# =============================================================================


def test_u01_header_matching():
    """U-01: strict header match against the frozen 26 columns."""
    assert unified.COLUMN_NAMES == tuple(HEADERS)
    unified._resolve_header(HEADERS)  # exact match: no raise
    with pytest.raises(ImportInvalidFile) as blank:
        unified._resolve_header([""] * 26)
    assert blank.value.details["reason"] == "header_missing"
    with pytest.raises(ImportInvalidFile) as order:
        unified._resolve_header(list(reversed(HEADERS)))
    assert order.value.details["reason"] == "column_order"
    with pytest.raises(ImportInvalidFile) as unknown:
        unified._resolve_header(HEADERS + ["extra"])
    assert unknown.value.details["reason"] == "unknown_columns"
    with pytest.raises(ImportInvalidFile) as missing:
        unified._resolve_header([h for h in HEADERS if h != "ip"])
    assert missing.value.details["reason"] == "missing_columns"


def test_u03_ip_cell_parsing_and_mask_stripping():
    """U-03: /mask is used only for resolution; stored address is bare host."""
    bare, hint = unified._parse_ip_cell("10.0.0.5/24")
    assert bare == "10.0.0.5"
    assert str(hint) == "10.0.0.0/24"
    bare2, hint2 = unified._parse_ip_cell(" 10.0.0.5 ")
    assert bare2 == "10.0.0.5" and hint2 is None
    for bad in ("", "not-an-ip", "10.0.0.300", "::1", "10.0.0.5/33"):
        with pytest.raises(unified._RowProblem) as exc:
            unified._parse_ip_cell(bad)
        assert exc.value.field == "ip"


def test_u07_int_bool_enum_parsing():
    """U-07: integer / boolean / enum parsing."""
    assert resource_import._parse_int("memory_mb", " 42 ") == 42
    for bad in ("1.5", "abc", "0x10", ""):
        with pytest.raises(ValueError):
            resource_import._parse_int("memory_mb", bad)
    assert unified._parse_bool("enabled", "TRUE") is True
    assert unified._parse_bool("enabled", "0") is False
    with pytest.raises(unified._RowProblem):
        unified._parse_bool("enabled", "yes")
    assert unified._validate_resource_type(BM) == BM
    from app.core.errors import ValidationError

    with pytest.raises(ValidationError):
        unified._validate_resource_type("CONTAINER")


class _DummyCluster:
    def __init__(self):
        import uuid

        self.id = uuid.uuid4()


def test_u02_u04_u05_grouping_merge_duplicate_consistency():
    """U-02/U-04/U-05: grouping, canonical merge, file-internal duplicate, group conflicts."""
    cluster = _DummyCluster()
    rows = [
        unified.ParsedRow(2, cluster, "h", "h", BM, "10.0.0.1", None, "eth0", {"role": "COMPUTE"}, {}),
        unified.ParsedRow(3, cluster, "h", "h", BM, "10.0.0.2", None, "eth0", {}, {}),
    ]
    grouped = unified._group_by_resource(rows)
    assert len(grouped) == 1
    assert len(unified._group_by_interface(list(grouped.values())[0])) == 1

    canonical, conflicts = unified._canonicalize(rows, "resource_cells")
    assert canonical == {"role": "COMPUTE"} and conflicts == []

    # interface conflict
    iface_rows = [
        unified.ParsedRow(2, cluster, "h", "h", BM, "10.0.0.1", None, "eth0", {}, {"mtu": 9000}),
        unified.ParsedRow(3, cluster, "h", "h", BM, "10.0.0.2", None, "eth0", {}, {"mtu": 1500}),
    ]
    _, iface_conflicts = unified._canonicalize(iface_rows, "interface_cells")
    assert iface_conflicts == [(3, "mtu", 2)]

    # file-internal duplicate ip
    dup_rows = [
        unified.ParsedRow(2, cluster, "h1", "h1", BM, "10.0.0.9", None, "eth0", {}, {}),
        unified.ParsedRow(3, cluster, "h2", "h2", BM, "10.0.0.9", None, "eth0", {}, {}),
    ]
    errors = unified._merge_and_check(dup_rows)
    duplicate = [e for e in errors if e.field == "ip" and e.related_row == 2]
    assert len(duplicate) == 1 and duplicate[0].row == 3


def test_u06_constraint_attribution():
    """U-06: DR-422 constraint-name and trigger-message attribution."""
    class _Diag:
        def __init__(self, name):
            self.constraint_name = name

    class _Orig:
        def __init__(self, name):
            self.diag = _Diag(name)

    class _Exc:
        def __init__(self, name="", message=""):
            self.orig = _Orig(name)
            self._message = message

        def __str__(self):
            return self._message

    cases = [
        ("uq_resources_cluster_id_hostname_key", "hostname"),
        ("uq_interfaces_resource_id_name", "name"),
        ("uq_ip_addresses_cluster_id_address", "ip"),
        ("ck_ip_addresses_address_host", "ip"),
        ("ck_ip_addresses_address_not_disabled", "ip"),
    ]
    for constraint, field in cases:
        assert unified._attribute_integrity(_Exc(constraint), 5).field == field

    trigger_cases = [
        ("ip_addresses.address must belong to the owning network CIDR", "ip"),
        ("ip_addresses.address must not be the network/broadcast address", "ip"),
        ("ip_addresses.cluster_id must equal the owning network cluster", "network"),
        ("bound interface resource must be in the same cluster as the IP", "name"),
    ]
    for message, field in trigger_cases:
        assert unified._attribute_integrity(_Exc("", message), 5).field == field

    unknown = unified._attribute_integrity(_Exc("some_unknown_constraint"), 5)
    assert unknown.field == "resource_type"


# =============================================================================
# REG / STATIC: no direct write SQL; route inventory
# =============================================================================


def test_reg01_no_direct_write_sql():
    """A8/T71/V-SL-1: F023 stages through the Service Layer, no ORM/SQL bypass."""
    from pathlib import Path

    source = Path("app/services/resource_interface_ip_import.py").read_text()
    lowered = source.lower()
    for forbidden in ("insert into", "update resources", "delete from"):
        assert forbidden not in lowered, forbidden
    for required in (
        "resource_service.stage_resource",
        "interface_service.prepare_interface",
        "interface_service.stage_interface",
        "ip_address_service.prepare_ip_address",
        "ip_address_service.stage_ip_address",
        "resource_service.validate_hardware",
        "resource_service.validate_virtual_machine_values",
        "normalization.normalize_hostname",
    ):
        assert required in source, required
    # unlockable/unknown constraint attribution stays explicit (DR-422).
    assert "_attribute_integrity" in source


def test_reg02_route_inventory(auth_app):
    """T22/REG: the three F023 routes exist and the F014 routes are unchanged."""
    paths = auth_app.openapi()["paths"]
    assert set(paths["/api/v1/imports/resource-interfaces-ips"]) >= {"post"}
    assert set(paths["/api/v1/imports/resource-interfaces-ips/validate"]) >= {"post"}
    assert set(paths["/api/v1/imports/resource-interfaces-ips/templates"]) >= {"get"}
    for legacy in (
        "/api/v1/imports/resources",
        "/api/v1/imports/resources/validate",
        "/api/v1/imports/resources/templates",
    ):
        assert legacy in paths


# =============================================================================
# PERF: caps, near-5000 baseline, preview truncation
# =============================================================================


def test_perf01_caps_rejection_latency_no_partial(role_client_factory, auth_session_factory, monkeypatch):
    editor, _, _ = role_client_factory("EDITOR")
    c = _cluster(editor, code="C1")
    _network(editor, c["id"], name="mgmt", cidr="10.0.0.0/24")
    with auth_session_factory() as session:
        baseline = _counts(session)

    # row cap: 5001 rows rejected (413) before any write
    rows = [
        _row(cluster=c["code"], hostname=f"perf{i:05d}", resource_type=BM, name="eth0", network="mgmt", ip=f"10.0.{i // 250}.{i % 250 + 1}")
        for i in range(5001)
    ]
    started = time.perf_counter()
    over = _write(editor, rows)
    elapsed = time.perf_counter() - started
    print(f"\n[PERF-01] 5001 rows rejected in {elapsed:.3f}s")
    assert over.status_code == 413
    assert over.json()["error"]["code"] == "IMPORT_ROW_LIMIT_EXCEEDED"
    with auth_session_factory() as session:
        assert _counts(session) == baseline

    # file-byte cap rejected before parsing
    monkey_patch = Settings(_env_file=None, import_max_file_bytes=10)
    monkeypatch.setattr(imports_api, "get_settings", lambda: monkey_patch)
    started = time.perf_counter()
    big = _write(editor, [_row(cluster=c["code"], hostname="x", resource_type=BM, name="eth0", network="mgmt", ip="10.0.0.1")])
    elapsed = time.perf_counter() - started
    print(f"\n[PERF-01b] over-size file rejected in {elapsed:.4f}s")
    assert big.status_code == 413
    assert big.json()["error"]["code"] == "IMPORT_FILE_TOO_LARGE"
    with auth_session_factory() as session:
        assert _counts(session) == baseline


def test_perf02_preview_truncation(role_client_factory, monkeypatch):
    editor, _, _ = role_client_factory("EDITOR")
    small = Settings(_env_file=None, import_error_preview_limit=2)
    monkeypatch.setattr(imports_api, "get_settings", lambda: small)
    rows = [
        _row(cluster="MISSING", hostname=f"e{i}", resource_type=BM, name="eth0", ip="10.0.0.1")
        for i in range(3)
    ]
    payload = _validate(editor, rows).json()
    assert payload["total_rows"] == 3
    assert payload["error_count"] == 3
    assert payload["errors_truncated"] is True
    assert len(payload["errors"]) == 2


def test_perf03_near_max_rows_baseline(role_client_factory, auth_session_factory):
    """PERF-03: near-5000-row import time / memory baseline (real PG, 3 tables/row)."""
    editor, _, _ = role_client_factory("EDITOR")
    c = _cluster(editor, code="C1")
    _network(editor, c["id"], name="big", cidr="10.0.0.0/16")
    settings = Settings(_env_file=None)

    total = 5000
    rows = [
        _row(cluster=c["code"], hostname=f"perf{i:05d}", resource_type=BM, name="eth0", network="big", ip=str(ipaddress.IPv4Address(int(ipaddress.IPv4Address("10.0.0.0")) + i + 1)))
        for i in range(total)
    ]
    data = _csv_bytes(rows)
    assert len(data) < settings.import_max_file_bytes

    with auth_session_factory() as session:
        baseline = _counts(session)

    session = auth_session_factory()
    try:
        tracemalloc.start()
        started = time.perf_counter()
        result = unified.validate_import(session, data, "csv", settings)
        validate_seconds = time.perf_counter() - started
        _, validate_peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        assert result.total_rows == total
        assert result.error_count == 0
    finally:
        session.close()

    session = auth_session_factory()
    try:
        tracemalloc.start()
        started = time.perf_counter()
        created, interfaces, ips, total_rows = unified.write_import(
            session, None, data, "csv", settings
        )
        write_seconds = time.perf_counter() - started
        _, write_peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
    finally:
        session.close()
    print(
        f"\n[PERF-03] file={len(data)}B rows={total} "
        f"validate={validate_seconds:.2f}s validate_peak={validate_peak / 1e6:.1f}MB "
        f"write={write_seconds:.2f}s write_peak={write_peak / 1e6:.1f}MB"
    )
    assert (created, interfaces, ips, total_rows) == (total, total, total, total)
    with auth_session_factory() as session:
        after = _counts(session)
    assert after["resources"] == baseline["resources"] + total
    assert after["interfaces"] == baseline["interfaces"] + total
    assert after["ip_addresses"] == baseline["ip_addresses"] + total
    assert after["audit_logs"] == baseline["audit_logs"] + total * 3
    # generous sanity ceiling; observed baseline is printed above
    assert write_seconds < 600, write_seconds