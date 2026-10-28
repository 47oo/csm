"""F035 向既有 Resource 追加 Interface/IP 导入 — 独立验收集成测试（TEST 模式）。

验证 `docs/api/F023.md` **v2**（§4 计数、§8.1 组键 → Resource 二态、§11 现存冲突、
§12.3 锁集合、§13 边界）与 `requirements-v3.md` revision 14 §24.6 / §31 T117–T126
（含修订后的 T67 / T71），以及 `docs/features/F035/architecture.md` §7.1 /
DR-F035-01…14 的实现约束。

真实 PostgreSQL（`TEST_DATABASE_URL`，DB-D10 guard），复用 conftest 的
`auth_app` / `auth_session_factory` / `committed_engine` 与
`integration.test_ip_addresses` 的既有 helper。断言以可观察行为为准：既有宿主
「零变化」按 F035 TD-9 的硬判据（全列快照 + `xmin` + `version` / `updated_at` +
无 `resource` UPDATE Audit + 既有子对象不变）机械判定。

覆盖：V1 / V2 / V3 / V4 / V7 / V8 / V9 / V10 / V11（真实 PG 双会话）/ V12
观察项；行级 §23.2 范围用例在 `test_f035_append_scope.py`（`real_scope`）。
"""

from __future__ import annotations

import csv
import io
import threading

from sqlalchemy import text

from app.core.config import Settings
from app.core.errors import ImportValidationFailed
from app.services import resource_interface_ip_import as unified
from integration.test_ip_addresses import (  # noqa: F401  (reused fixtures/helpers)
    _cluster,
    _interface,
    _ip,
    _network,
    _operator,
    role_client_factory,
)

VALIDATE = "/api/v1/imports/resource-interfaces-ips/validate"
WRITE = "/api/v1/imports/resource-interfaces-ips"
TEMPLATES = "/api/v1/imports/resource-interfaces-ips/templates"
F014_VALIDATE = "/api/v1/imports/resources/validate"

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

# F014 资源导入 BM 模板（14 列，BQ04=A：该入口仍报 hostname 冲突）。
F014_BM_HEADERS = [
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

COUNT_TABLES = (
    "clusters",
    "resources",
    "bare_metal_details",
    "virtual_machine_details",
    "interfaces",
    "ip_addresses",
    "audit_logs",
    "networks",
    "ip_pools",
    "services",
    "service_endpoints",
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


def _post(client, path, data, fmt="csv"):
    return client.post(
        path,
        files={"file": (f"import.{fmt}", data, "application/octet-stream")},
        data={"format": fmt},
    )


def _validate(client, rows, headers=None):
    return _post(client, VALIDATE, _csv_bytes(rows, headers))


def _write(client, rows, headers=None):
    return _post(client, WRITE, _csv_bytes(rows, headers))


def _find_error(payload: dict, field: str, row: int | None = None) -> dict | None:
    for error in payload["errors"]:
        if error["field"] == field and (row is None or error["row"] == row):
            return error
    return None


def _errors_at(payload: dict, row: int) -> list[dict]:
    return [error for error in payload["errors"] if error["row"] == row]


def _counts(session) -> dict[str, int]:
    return {
        table: int(session.execute(text(f"SELECT count(*) FROM {table}")).scalar_one())
        for table in COUNT_TABLES
    }


def _api_resource(client, cluster_code, hostname, resource_type=BM, **overrides):
    body = {"cluster": cluster_code, "hostname": hostname, "resource_type": resource_type}
    body.update(overrides)
    resp = client.post("/api/v1/resources", json=body)
    assert resp.status_code == 201, resp.text
    return resp.json()["resource"]


def _bind_ip(client, ip, interface_id):
    """Bind an existing IP to an Interface (F010 PATCH: allocation != binding)."""
    resp = client.patch(
        f"/api/v1/ip-addresses/{ip['id']}",
        json={"version": ip["version"], "interface": interface_id},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["ip_address"]


def _one(session, sql: str, params: dict | None = None) -> dict | None:
    row = session.execute(text(sql), params or {}).mappings().first()
    return dict(row) if row is not None else None


def _many(session, sql: str, params: dict | None = None) -> list[dict]:
    return [dict(r) for r in session.execute(text(sql), params or {}).mappings().all()]


def _host_state(session, host_id: str) -> dict:
    """Full-column snapshot of an existing host + its children (F035 TD-5)."""
    return {
        "resource": _one(
            session, "SELECT * FROM resources WHERE id = :id", {"id": host_id}
        ),
        "xmin": session.execute(
            text("SELECT xmin::text FROM resources WHERE id = :id"), {"id": host_id}
        ).scalar_one(),
        "bm": _one(
            session,
            "SELECT * FROM bare_metal_details WHERE resource_id = :id",
            {"id": host_id},
        ),
        "vm": _one(
            session,
            "SELECT * FROM virtual_machine_details WHERE resource_id = :id",
            {"id": host_id},
        ),
        "interfaces": _many(
            session,
            "SELECT * FROM interfaces WHERE resource_id = :id ORDER BY id",
            {"id": host_id},
        ),
        "ips": _many(
            session,
            "SELECT ip.* FROM ip_addresses ip "
            "JOIN interfaces i ON i.id = ip.interface_id "
            "WHERE i.resource_id = :id ORDER BY ip.id",
            {"id": host_id},
        ),
    }


def _assert_host_untouched(before: dict, after: dict) -> None:
    """V2 hard judgement: existing host rows are byte-identical (no UPDATE)."""
    assert after["resource"] == before["resource"], "existing Resource row changed"
    assert after["xmin"] == before["xmin"], "resources row was UPDATEd (xmin changed)"
    assert after["bm"] == before["bm"], "bare_metal_details changed"
    assert after["vm"] == before["vm"], "virtual_machine_details changed"
    for key in ("interfaces", "ips"):
        after_by_id = {str(row["id"]): row for row in after[key]}
        for row in before[key]:
            assert after_by_id.get(str(row["id"])) == row, (key, row["id"])


def _audit_action_counts(session, object_id: str) -> dict[str, int]:
    rows = session.execute(
        text(
            "SELECT object_type, action, count(*) FROM audit_logs "
            "WHERE object_id = :id GROUP BY object_type, action"
        ),
        {"id": object_id},
    ).all()
    return {(row[0], row[1]): int(row[2]) for row in rows}


def _write_service(session, operator, rows):
    return unified.write_import(
        session, operator, _csv_bytes(rows), "csv", Settings(_env_file=None)
    )


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
    assert all(not t.is_alive() for t in threads), "concurrent session did not finish"
    return results


# =============================================================================
# V1 / V2 / T117 / T118 / T124: append success + existing host zero change
# =============================================================================


def test_td3_f035_v1_1_t118_bm_append_keeps_host_untouched(
    role_client_factory, auth_session_factory
):
    """T117/T118/T124.1/T124.2: BM append, host+children untouched, created==0."""
    editor, _, _ = role_client_factory("EDITOR")
    c = _cluster(editor, code="F35A")
    net = _network(editor, c["id"], name="f35-net", cidr="10.50.0.0/24")
    host = _api_resource(
        editor,
        c["code"],
        "f35-h1",
        role="COMPUTE",
        status="IDLE",
        hardware={
            "manufacturer": "Dell",
            "model": "PowerEdge R750",
            "serial_number": "SN-1",
            "cpu_model": "Xeon 8358",
            "cpu_sockets": 2,
            "cpu_cores": 64,
            "memory_mb": 262144,
            "gpu_model": "A100",
            "gpu_count": 8,
        },
    )
    existing_iface = _interface(editor, host["id"], "eth0")
    existing_ip = _bind_ip(
        editor, _ip(editor, net["id"], "10.50.0.10"), existing_iface["id"]
    )
    assert existing_ip["interface"]["id"] == existing_iface["id"]

    rows = [
        _row(
            cluster=c["code"],
            hostname="f35-h1",
            resource_type=BM,
            name="eth1",
            interface_type="PHYSICAL",
            network="f35-net",
            ip="10.50.0.11",
        )
    ]
    with auth_session_factory() as session:
        before_counts = _counts(session)
        before_host = _host_state(session, host["id"])
        before_activity = editor.get(
            f"/api/v1/resources/{host['id']}/activity", params={"page_size": 100}
        ).json()

    validated = _validate(editor, rows)
    assert validated.status_code == 200, validated.text
    payload = validated.json()
    assert payload["error_count"] == 0, payload["errors"]
    assert payload["importable_rows"] == payload["total_rows"] == 1

    resp = _write(editor, rows)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert set(body) == {
        "created",
        "total_rows",
        "interfaces_created",
        "ip_addresses_created",
    }, "no new response field is allowed (DR-F035-04)"
    assert body["created"] == 0
    assert body["interfaces_created"] == 1
    assert body["ip_addresses_created"] == 1
    assert body["total_rows"] == 1

    with auth_session_factory() as session:
        after_counts = _counts(session)
        after_host = _host_state(session, host["id"])
        new_iface = _one(
            session,
            "SELECT * FROM interfaces WHERE name = 'eth1'",
        )
        new_ip = _one(
            session,
            "SELECT * FROM ip_addresses WHERE address = '10.50.0.11'",
        )
        iface_audit = _audit_action_counts(session, str(new_iface["id"]))
        ip_audit = _audit_action_counts(session, str(new_ip["id"]))

    # the host and its existing children are untouched (V2 hard judgement)
    _assert_host_untouched(before_host, after_host)
    assert after_host["resource"]["version"] == 1
    assert (
        str(after_host["resource"]["updated_at"])
        == str(before_host["resource"]["updated_at"])
    )
    assert after_counts["resources"] == before_counts["resources"]
    assert after_counts["bare_metal_details"] == before_counts["bare_metal_details"]
    assert after_counts["interfaces"] == before_counts["interfaces"] + 1
    assert after_counts["ip_addresses"] == before_counts["ip_addresses"] + 1

    # new children belong to the existing host / new interface
    assert str(new_iface["resource_id"]) == host["id"]
    assert str(new_ip["interface_id"]) == str(new_iface["id"])
    assert str(new_ip["network_id"]) == net["id"]

    # audits: one CREATE per new object, never a Resource UPDATE
    assert iface_audit == {("interface", "CREATE"): 1}
    assert ip_audit == {("ip_address", "CREATE"): 1}
    assert after_counts["audit_logs"] == before_counts["audit_logs"] + 2
    with auth_session_factory() as session:
        resource_updates = session.execute(
            text(
                "SELECT count(*) FROM audit_logs WHERE object_type = 'resource' "
                "AND object_id = :id AND action = 'UPDATE'"
            ),
            {"id": host["id"]},
        ).scalar_one()
    assert resource_updates == 0

    # Activity: no UPDATE item appears for the host
    after_activity = editor.get(
        f"/api/v1/resources/{host['id']}/activity", params={"page_size": 100}
    ).json()
    assert {item["action"] for item in after_activity["items"]} <= {"CREATE"}
    assert after_activity["total"] == before_activity["total"]


def test_td3_f035_v1_2_t118_5_vm_append_keeps_host_untouched(
    role_client_factory, auth_session_factory
):
    """T118.5/V1.2: VM append (``host`` must match), VM detail untouched."""
    editor, _, _ = role_client_factory("EDITOR")
    c = _cluster(editor, code="F35B")
    _network(editor, c["id"], name="f35-net", cidr="10.51.0.0/24")
    bm = _api_resource(editor, c["code"], "f35-bmh1")
    vm_host = _api_resource(
        editor,
        c["code"],
        "f35-vm1",
        resource_type=VM,
        role="COMPUTE",
        virtual_machine={
            "host_resource_id": bm["id"],
            "vcpu": 8,
            "memory_mb": 32768,
            "disk_gb": 100,
            "hypervisor": "KVM",
        },
    )

    rows = [
        _row(
            cluster=c["code"],
            hostname="f35-vm1",
            resource_type=VM,
            role="COMPUTE",
            host="f35-bmh1",
            vcpu="8",
            memory_mb="32768",
            disk_gb="100",
            hypervisor="KVM",
            name="eth0",
            network="f35-net",
            ip="10.51.0.11",
        )
    ]
    with auth_session_factory() as session:
        before_counts = _counts(session)
        before_host = _host_state(session, vm_host["id"])

    assert _validate(editor, rows).json()["error_count"] == 0
    resp = _write(editor, rows)
    assert resp.status_code == 201, resp.text
    assert resp.json()["created"] == 0

    with auth_session_factory() as session:
        after_counts = _counts(session)
        after_host = _host_state(session, vm_host["id"])
        bound = _one(
            session,
            "SELECT ip.address, i.name, i.resource_id FROM ip_addresses ip "
            "JOIN interfaces i ON i.id = ip.interface_id WHERE ip.address = '10.51.0.11'",
        )
    _assert_host_untouched(before_host, after_host)
    assert after_counts["resources"] == before_counts["resources"]
    assert after_counts["virtual_machine_details"] == before_counts[
        "virtual_machine_details"
    ]
    assert str(bound["resource_id"]) == vm_host["id"]
    assert bound["name"] == "eth0"


# =============================================================================
# V3 / T119: Resource-level column consistency with the existing host
# =============================================================================


def test_td3_f035_t119_resource_level_mismatch_attribution(
    role_client_factory, auth_session_factory
):
    """T119.1/.2/.3/.7/.8/.9: per-column ``field`` attribution, 422, zero residue."""
    editor, _, _ = role_client_factory("EDITOR")
    c = _cluster(editor, code="F35C")
    _network(editor, c["id"], name="f35-net", cidr="10.52.0.0/24")
    host = _api_resource(
        editor,
        c["code"],
        "f35-h3",
        role="COMPUTE",
        status="IDLE",
        hardware={
            "manufacturer": "Dell",
            "model": "R750",
            "cpu_cores": 64,
            "memory_mb": 262144,
            "gpu_count": 8,
        },
    )
    base = dict(
        cluster=c["code"], hostname="f35-h3", name="eth0", network="f35-net"
    )

    def validate_one(**overrides):
        row = _row(**{**base, "resource_type": BM, "ip": "10.52.0.11", **overrides})
        return _validate(editor, [row]).json()

    # resource_type: BM host vs VM row -> field=resource_type (TD-I-5)
    type_payload = validate_one(resource_type=VM, host="f35-h3")
    assert _find_error(type_payload, "resource_type", 2) is not None, type_payload

    # role / status
    role_payload = validate_one(role="GPU")
    role_error = _find_error(role_payload, "role", 2)
    assert role_error is not None
    assert role_error["related_row"] is None
    assert role_error["reason"]
    assert _find_error(validate_one(status="ALLOC"), "status", 2) is not None

    # hardware columns: one case per column family
    for column, value in (
        ("manufacturer", "HPE"),
        ("cpu_cores", "32"),
        ("gpu_count", "4"),
        ("memory_mb", "131072"),
    ):
        payload = validate_one(**{column: value})
        error = _find_error(payload, column, 2)
        assert error is not None, (column, payload["errors"])
        assert error["related_row"] is None

    # exact string comparison (no case folding) but normalising trim
    assert _find_error(validate_one(manufacturer="DELL"), "manufacturer", 2) is not None
    assert validate_one(manufacturer=" Dell ")["error_count"] == 0

    # matching values are accepted
    accepted = validate_one(
        role="COMPUTE", status="IDLE", manufacturer="Dell", cpu_cores="64",
        memory_mb="262144", gpu_count="8",
    )
    assert accepted["error_count"] == 0, accepted["errors"]

    # a mismatching batch is rejected as a whole with zero residue
    with auth_session_factory() as session:
        before_counts = _counts(session)
        before_host = _host_state(session, host["id"])
    resp = _write(
        editor,
        [_row(**{**base, "resource_type": BM, "ip": "10.52.0.11", "role": "GPU"})],
    )
    assert resp.status_code == 422
    details = resp.json()["error"]["details"]
    assert resp.json()["error"]["code"] == "IMPORT_VALIDATION_FAILED"
    assert _find_error(details, "role", 2) is not None
    with auth_session_factory() as session:
        after_counts = _counts(session)
        after_host = _host_state(session, host["id"])
    assert after_counts == before_counts
    _assert_host_untouched(before_host, after_host)


def test_td3_f035_t119_omitted_and_null_columns(
    role_client_factory, auth_session_factory
):
    """T119.5/.6: omitted columns are not compared; existing ``null`` stays null."""
    editor, _, _ = role_client_factory("EDITOR")
    c = _cluster(editor, code="F35D")
    _network(editor, c["id"], name="f35-net", cidr="10.53.0.0/24")
    rich = _api_resource(
        editor,
        c["code"],
        "f35-h4",
        role="GPU",
        status="ALLOC",
        hardware={"manufacturer": "Dell", "cpu_cores": 64, "gpu_count": 8},
    )
    sparse = _api_resource(editor, c["code"], "f35-h5")  # every hardware column null

    # (a) all Resource-level cells empty -> no comparison, no error, host untouched
    rows = [
        _row(
            cluster=c["code"],
            hostname="f35-h4",
            resource_type=BM,
            name="eth0",
            network="f35-net",
            ip="10.53.0.11",
        )
    ]
    assert _validate(editor, rows).json()["error_count"] == 0
    with auth_session_factory() as session:
        before_host = _host_state(session, rich["id"])
    resp = _write(editor, rows)
    assert resp.status_code == 201, resp.text
    with auth_session_factory() as session:
        after_host = _host_state(session, rich["id"])
    _assert_host_untouched(before_host, after_host)
    assert after_host["resource"]["role"] == "GPU"
    assert after_host["resource"]["status"] == "ALLOC"

    # (b) existing null cannot be back-filled by import
    given = _validate(
        editor,
        [
            _row(
                cluster=c["code"],
                hostname="f35-h5",
                resource_type=BM,
                cpu_cores="32",
                name="eth0",
                network="f35-net",
                ip="10.53.0.12",
            )
        ],
    ).json()
    assert _find_error(given, "cpu_cores") is not None, given["errors"]
    write_resp = _write(
        editor,
        [
            _row(
                cluster=c["code"],
                hostname="f35-h5",
                resource_type=BM,
                cpu_cores="32",
                name="eth0",
                network="f35-net",
                ip="10.53.0.12",
            )
        ],
    )
    assert write_resp.status_code == 422
    with auth_session_factory() as session:
        detail = _one(
            session,
            "SELECT cpu_cores FROM bare_metal_details WHERE resource_id = :id",
            {"id": sparse["id"]},
        )
    assert detail["cpu_cores"] is None

    # (c) omitted -> no error and the existing null is preserved
    assert (
        _validate(
            editor,
            [
                _row(
                    cluster=c["code"],
                    hostname="f35-h5",
                    resource_type=BM,
                    name="eth0",
                    network="f35-net",
                    ip="10.53.0.13",
                )
            ],
        ).json()["error_count"]
        == 0
    )
    ok = _write(
        editor,
        [
            _row(
                cluster=c["code"],
                hostname="f35-h5",
                resource_type=BM,
                name="eth0",
                network="f35-net",
                ip="10.53.0.13",
            )
        ],
    )
    assert ok.status_code == 201, ok.text
    with auth_session_factory() as session:
        detail = _one(
            session,
            "SELECT * FROM bare_metal_details WHERE resource_id = :id",
            {"id": sparse["id"]},
        )
    assert detail["cpu_cores"] is None and detail["memory_mb"] is None


def test_td3_f035_t119_11_write_revalidates_consistency(role_client_factory):
    """T119.11: pre-validate 0 errors, host changed externally -> 422, no residue."""
    editor, _, _ = role_client_factory("EDITOR")
    c = _cluster(editor, code="F35E")
    _network(editor, c["id"], name="f35-net", cidr="10.54.0.0/24")
    host = _api_resource(editor, c["code"], "f35-h6", role="COMPUTE")
    rows = [
        _row(
            cluster=c["code"],
            hostname="f35-h6",
            resource_type=BM,
            role="COMPUTE",
            name="eth0",
            network="f35-net",
            ip="10.54.0.11",
        )
    ]
    assert _validate(editor, rows).json()["errors"] == []

    patched = editor.patch(
        f"/api/v1/resources/{host['id']}", json={"version": 1, "role": "GPU"}
    )
    assert patched.status_code == 200, patched.text

    resp = _write(editor, rows)
    assert resp.status_code == 422
    details = resp.json()["error"]["details"]
    assert _find_error(details, "role", 2) is not None
    listing = editor.get("/api/v1/interfaces", params={"resource_id": host["id"]}).json()
    assert listing["total"] == 0


# =============================================================================
# V4 / T120: existing same-name Interface and same-cluster IP
# =============================================================================


def test_td3_f035_t120_existing_interface_name_and_case_sensitivity(
    role_client_factory, auth_session_factory
):
    """T120.1/.2/.5/.6: ``name`` conflict is case-sensitive, never appends IPs."""
    editor, _, _ = role_client_factory("EDITOR")
    c = _cluster(editor, code="F35F")
    net = _network(editor, c["id"], name="f35-net", cidr="10.55.0.0/24")
    host = _api_resource(editor, c["code"], "f35-h7")
    existing_iface = _interface(editor, host["id"], "Eth0")
    _bind_ip(editor, _ip(editor, net["id"], "10.55.0.10"), existing_iface["id"])

    # same name -> row error on both phases, nothing written anywhere
    conflict_rows = [
        _row(
            cluster=c["code"],
            hostname="f35-h7",
            resource_type=BM,
            name="Eth0",
            network="f35-net",
            ip="10.55.0.11",
        )
    ]
    validated = _validate(editor, conflict_rows).json()
    name_error = _find_error(validated, "name", 2)
    assert name_error is not None
    assert name_error["related_row"] is None
    with auth_session_factory() as session:
        before_counts = _counts(session)
    write_resp = _write(editor, conflict_rows)
    assert write_resp.status_code == 422
    details = write_resp.json()["error"]["details"]
    assert _find_error(details, "name", 2) is not None
    assert _find_error(details, "name", 2)["reason"] == name_error["reason"]
    with auth_session_factory() as session:
        after_counts = _counts(session)
        ips_on_existing = session.execute(
            text("SELECT count(*) FROM ip_addresses WHERE interface_id = :i"),
            {"i": existing_iface["id"]},
        ).scalar_one()
    assert after_counts == before_counts
    assert ips_on_existing == 1, "no IP may be appended to an existing Interface"

    # different case -> a distinct Interface is created next to ``Eth0``
    ok_rows = [
        _row(
            cluster=c["code"],
            hostname="f35-h7",
            resource_type=BM,
            name="eth0",
            network="f35-net",
            ip="10.55.0.11",
        )
    ]
    assert _validate(editor, ok_rows).json()["error_count"] == 0
    resp = _write(editor, ok_rows)
    assert resp.status_code == 201, resp.text
    with auth_session_factory() as session:
        names = [
            row["name"]
            for row in _many(
                session,
                "SELECT name FROM interfaces WHERE resource_id = :id ORDER BY name",
                {"id": host["id"]},
            )
        ]
    assert sorted(names) == ["Eth0", "eth0"]


def test_td3_f035_t120_existing_ip_same_cluster_only(
    role_client_factory, auth_session_factory
):
    """T120.3/.4: same-cluster existing IP -> ``ip``; another cluster is fine."""
    editor, _, _ = role_client_factory("EDITOR")
    c1 = _cluster(editor, code="F35G")
    c2 = _cluster(editor, code="F35H")
    net1 = _network(editor, c1["id"], name="f35-net1", cidr="10.56.0.0/24")
    net2 = _network(editor, c2["id"], name="f35-net2", cidr="10.56.0.0/24")
    host = _api_resource(editor, c1["code"], "f35-h8")
    _ip(editor, net1["id"], "10.56.0.30")
    _ip(editor, net2["id"], "10.56.0.20")  # same address, other cluster

    conflicting = [
        _row(
            cluster=c1["code"],
            hostname="f35-h8",
            resource_type=BM,
            name="eth0",
            network="f35-net1",
            ip="10.56.0.30",
        )
    ]
    payload = _validate(editor, conflicting).json()
    assert _find_error(payload, "ip", 2) is not None, payload["errors"]
    resp = _write(editor, conflicting)
    assert resp.status_code == 422
    assert _find_error(resp.json()["error"]["details"], "ip", 2) is not None

    # the same address in another cluster is not a conflict here
    accepted = [
        _row(
            cluster=c1["code"],
            hostname="f35-h8",
            resource_type=BM,
            name="eth0",
            network="f35-net1",
            ip="10.56.0.20",
        )
    ]
    assert _validate(editor, accepted).json()["error_count"] == 0
    ok = _write(editor, accepted)
    assert ok.status_code == 201, ok.text
    with auth_session_factory() as session:
        bound = _one(
            session,
            "SELECT i.name, i.resource_id FROM ip_addresses ip "
            "JOIN interfaces i ON i.id = ip.interface_id "
            "WHERE ip.address = '10.56.0.20' AND ip.network_id = :n",
            {"n": net1["id"]},
        )
    assert str(bound["resource_id"]) == host["id"]


# =============================================================================
# V7 / T123: mixed batch atomicity + write-time re-validation
# =============================================================================


def test_td3_f035_t123_1_mixed_batch_counts(role_client_factory, auth_session_factory):
    """T123.1: create group + append group in one batch, only the former counts."""
    editor, _, _ = role_client_factory("EDITOR")
    c = _cluster(editor, code="F35I")
    _network(editor, c["id"], name="f35-net", cidr="10.57.0.0/24")
    host = _api_resource(editor, c["code"], "f35-h9")

    rows = [
        _row(
            cluster=c["code"],
            hostname="f35-h9",
            resource_type=BM,
            name="eth0",
            network="f35-net",
            ip="10.57.0.11",
        ),
        _row(
            cluster=c["code"],
            hostname="f35-new1",
            resource_type=BM,
            name="eth0",
            network="f35-net",
            ip="10.57.0.12",
        ),
    ]
    with auth_session_factory() as session:
        before_counts = _counts(session)
        before_host = _host_state(session, host["id"])

    assert _validate(editor, rows).json()["error_count"] == 0
    resp = _write(editor, rows)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["created"] == 1
    assert body["interfaces_created"] == 2
    assert body["ip_addresses_created"] == 2
    assert body["total_rows"] == body["ip_addresses_created"]

    with auth_session_factory() as session:
        after_counts = _counts(session)
        after_host = _host_state(session, host["id"])
        appended = _one(
            session,
            "SELECT i.resource_id FROM ip_addresses ip "
            "JOIN interfaces i ON i.id = ip.interface_id WHERE ip.address = '10.57.0.11'",
        )
        created = _one(
            session, "SELECT id FROM resources WHERE hostname = 'f35-new1'"
        )
    _assert_host_untouched(before_host, after_host)
    assert after_counts["resources"] == before_counts["resources"] + 1
    assert after_counts["interfaces"] == before_counts["interfaces"] + 2
    assert after_counts["ip_addresses"] == before_counts["ip_addresses"] + 2
    assert after_counts["audit_logs"] == before_counts["audit_logs"] + 5
    assert str(appended["resource_id"]) == host["id"]
    assert str(created["id"]) != host["id"]


def test_td3_f035_t123_2_mixed_batch_rolls_back_entirely(
    role_client_factory, auth_session_factory
):
    """T123.2: one bad row rolls back the new Resource *and* the append group."""
    editor, _, _ = role_client_factory("EDITOR")
    c = _cluster(editor, code="F35J")
    net = _network(editor, c["id"], name="f35-net", cidr="10.58.0.0/24")
    host = _api_resource(editor, c["code"], "f35-h10")
    _ip(editor, net["id"], "10.58.0.99")  # occupied address -> runtime/validation error

    rows = [
        _row(
            cluster=c["code"],
            hostname="f35-h10",
            resource_type=BM,
            name="eth0",
            network="f35-net",
            ip="10.58.0.11",
        ),
        _row(
            cluster=c["code"],
            hostname="f35-new2",
            resource_type=BM,
            name="eth0",
            network="f35-net",
            ip="10.58.0.12",
        ),
        _row(
            cluster=c["code"],
            hostname="f35-new3",
            resource_type=BM,
            name="eth0",
            network="f35-net",
            ip="10.58.0.99",
        ),
    ]
    with auth_session_factory() as session:
        before_counts = _counts(session)
        before_host = _host_state(session, host["id"])

    resp = _write(editor, rows)
    assert resp.status_code == 422
    details = resp.json()["error"]["details"]
    assert _find_error(details, "ip", 4) is not None

    with auth_session_factory() as session:
        after_counts = _counts(session)
        after_host = _host_state(session, host["id"])
        leftovers = _many(
            session,
            "SELECT hostname FROM resources WHERE hostname LIKE 'f35-new%'",
        )
    assert after_counts == before_counts
    _assert_host_untouched(before_host, after_host)
    assert leftovers == []


def test_td3_f035_t123_3_write_revalidates_existing_interface(role_client_factory):
    """T123.3: same-name Interface created after pre-validate -> 422 ``name``."""
    editor, _, _ = role_client_factory("EDITOR")
    c = _cluster(editor, code="F35K")
    _network(editor, c["id"], name="f35-net", cidr="10.59.0.0/24")
    host = _api_resource(editor, c["code"], "f35-h11")
    rows = [
        _row(
            cluster=c["code"],
            hostname="f35-h11",
            resource_type=BM,
            name="eth0",
            network="f35-net",
            ip="10.59.0.11",
        )
    ]
    assert _validate(editor, rows).json()["errors"] == []
    _interface(editor, host["id"], "eth0")

    resp = _write(editor, rows)
    assert resp.status_code == 422
    assert _find_error(resp.json()["error"]["details"], "name", 2) is not None
    listed = editor.get("/api/v1/ip-addresses", params={"address": "10.59.0.11"}).json()
    assert listed["total"] == 0


def test_td3_f035_t123_5_host_soft_deleted_after_validate(role_client_factory, auth_session_factory):
    """T123.5/V12 (observation, R3): host deleted after validate -> treated as new."""
    editor, _, _ = role_client_factory("EDITOR")
    admin, _, _ = role_client_factory("ADMIN")
    c = _cluster(editor, code="F35L")
    _network(editor, c["id"], name="f35-net", cidr="10.60.0.0/24")
    host = _api_resource(editor, c["code"], "f35-h12")

    rows = [
        _row(
            cluster=c["code"],
            hostname="f35-h12",
            resource_type=BM,
            name="eth0",
            network="f35-net",
            ip="10.60.0.11",
        )
    ]
    assert _validate(editor, rows).json()["error_count"] == 0
    deleted = admin.delete(
        f"/api/v1/resources/{host['id']}", params={"version": host["version"]}
    )
    assert deleted.status_code == 204, deleted.text

    resp = _write(editor, rows)
    assert resp.status_code == 201, resp.text
    assert resp.json()["created"] == 1
    with auth_session_factory() as session:
        new_row = _one(
            session,
            "SELECT id FROM resources WHERE hostname = 'f35-h12' AND deleted_at IS NULL",
        )
        old_row = _one(
            session, "SELECT deleted_at FROM resources WHERE id = :id", {"id": host["id"]}
        )
        children = session.execute(
            text("SELECT count(*) FROM interfaces WHERE resource_id = :id"),
            {"id": host["id"]},
        ).scalar_one()
    assert str(new_row["id"]) != host["id"]
    assert old_row["deleted_at"] is not None
    assert children == 0


# =============================================================================
# V8 / T124: permissions, 401-before-403, response shape
# =============================================================================


def test_td3_f035_t124_permissions_and_templates(role_client_factory, auth_app):
    """T124.3/.4: EDITOR allowed, VIEWER 403, anonymous 401 (before 403)."""
    from fastapi.testclient import TestClient

    data = _csv_bytes(
        [_row(cluster="F35M", hostname="f35-p", resource_type=BM, name="eth0", ip="10.61.0.11")]
    )
    with TestClient(auth_app) as anon:
        assert _post(anon, VALIDATE, data).status_code == 401
        assert _post(anon, WRITE, data).status_code == 401
        assert anon.get(TEMPLATES).status_code == 401
        assert _post(anon, VALIDATE, data).json()["error"]["code"] == "AUTH_REQUIRED"

    viewer, _, _ = role_client_factory("VIEWER")
    assert _post(viewer, VALIDATE, data).status_code == 403
    assert _post(viewer, WRITE, data).status_code == 403
    assert _post(viewer, VALIDATE, data).json()["error"]["details"] == {
        "reason": "permission"
    }
    templates = viewer.get(TEMPLATES)
    assert templates.status_code == 200
    columns = templates.json()["template"]["columns"]
    assert [column["name"] for column in columns] == HEADERS
    assert len(columns) == 26


# =============================================================================
# V9 / T125: soft-deleted host + "no other objects created"
# =============================================================================


def test_td3_f035_t125_soft_deleted_host_is_absent(
    role_client_factory, auth_session_factory
):
    """T125.1/.2/.3: deleted host is not appended to, not restored, no extras."""
    editor, _, _ = role_client_factory("EDITOR")
    admin, _, _ = role_client_factory("ADMIN")
    c = _cluster(editor, code="F35N")
    _network(editor, c["id"], name="f35-net", cidr="10.62.0.0/24")
    host = _api_resource(editor, c["code"], "f35-h13")
    iface = _interface(editor, host["id"], "eth0")
    # An undeleted Interface blocks Resource deletion (F007 reference check), so
    # delete the Interface first: the deleted host keeps a soft-deleted `eth0`
    # Interface row, which is exactly the T125.2 "name reuse" case.
    assert (
        admin.delete(
            f"/api/v1/interfaces/{iface['id']}", params={"version": iface["version"]}
        ).status_code
        == 204
    )
    assert (
        admin.delete(
            f"/api/v1/resources/{host['id']}", params={"version": host["version"]}
        ).status_code
        == 204
    )

    with auth_session_factory() as session:
        before_counts = _counts(session)
        before_host = _host_state(session, host["id"])

    rows = [
        _row(
            cluster=c["code"],
            hostname="f35-h13",
            resource_type=BM,
            name="eth0",
            network="f35-net",
            ip="10.62.0.11",
        )
    ]
    assert _validate(editor, rows).json()["error_count"] == 0
    resp = _write(editor, rows)
    assert resp.status_code == 201, resp.text
    assert resp.json()["created"] == 1

    with auth_session_factory() as session:
        after_counts = _counts(session)
        after_host = _host_state(session, host["id"])
        new_host = _one(
            session,
            "SELECT id FROM resources WHERE hostname = 'f35-h13' AND deleted_at IS NULL",
        )
        new_iface = _one(
            session,
            "SELECT i.name, i.resource_id FROM interfaces i "
            "JOIN resources r ON r.id = i.resource_id "
            "WHERE r.id = :id",
            {"id": new_host["id"]},
        )
    # the deleted row and its soft-deleted child Interface stay untouched
    _assert_host_untouched(before_host, after_host)
    assert after_host["resource"]["deleted_at"] is not None
    assert str(new_host["id"]) != host["id"]
    assert new_iface["name"] == "eth0"  # per-resource uniqueness, not global
    # only a new Resource + its Interface + IP; no Cluster/Network/Pool/Service
    assert after_counts["resources"] == before_counts["resources"] + 1
    for table in ("clusters", "networks", "ip_pools", "services", "service_endpoints"):
        assert after_counts[table] == before_counts[table], table


# =============================================================================
# V10 / T126 / T67 / T71: zero regression guards
# =============================================================================


def test_td3_f035_t126_1_t67_2_f014_entry_still_conflicts(role_client_factory):
    """T126.1/T67.2 (BQ04=A): the F014 resource import still reports hostname."""
    editor, _, _ = role_client_factory("EDITOR")
    c = _cluster(editor, code="F35O")
    _network(editor, c["id"], name="f35-net", cidr="10.63.0.0/24")
    _api_resource(editor, c["code"], "f35-h14")

    rows = [
        ["F35O", "f35-h14", "BARE_METAL", "", "", "", "", "", "", "", "", "", "", ""]
    ]
    resp = _post(editor, F014_VALIDATE, _csv_bytes(rows, F014_BM_HEADERS))
    assert resp.status_code == 200, resp.text
    payload = resp.json()
    error = _find_error(payload, "hostname", 2)
    assert error is not None, payload["errors"]

    # ... while the same key on the F023 v2 entry appends instead
    ok_rows = [
        _row(
            cluster=c["code"],
            hostname="f35-h14",
            resource_type=BM,
            name="eth0",
            network="f35-net",
            ip="10.63.0.11",
        )
    ]
    assert _find_error(_validate(editor, ok_rows).json(), "hostname") is None
    assert _write(editor, ok_rows).status_code == 201


def test_td3_f035_t126_7_t71_zero_diff_guards():
    """T126.7/T71.2 static guards: no direct write SQL, no local alias shortcuts.

    The authoritative zero-diff proof is ``git diff --name-only`` over the guard
    set (recorded in the implementation report); this test keeps the
    *behavioural* part: F023 staging keeps going through the Service Layer and
    the append path adds no SQL write of its own.
    """
    from pathlib import Path

    source = Path("app/services/resource_interface_ip_import.py").read_text()
    lowered = source.lower()
    for forbidden in ("insert into", "update resources", "delete from", "update interfaces"):
        assert forbidden not in lowered, forbidden
    for required in (
        "resource_service.stage_resource",
        "interface_service.prepare_interface",
        "interface_service.stage_interface",
        "ip_address_service.prepare_ip_address",
        "ip_address_service.stage_ip_address",
        "resource_service._hardware_snapshot",
        "resource_service._virtual_machine_snapshot",
        "_load_existing_snapshots",
        "_check_existing_consistency",
        "_check_existing_interface_names",
    ):
        assert required in source, required


def test_td3_f035_t116_4_d1_templates_and_routes_unchanged(auth_app):
    """T126.6: three routes only; the F014 routes stay untouched."""
    paths = auth_app.openapi()["paths"]
    f023 = {
        path
        for path in paths
        if "/imports/resource-interfaces-ips" in path
    }
    assert f023 == {
        "/api/v1/imports/resource-interfaces-ips",
        "/api/v1/imports/resource-interfaces-ips/validate",
        "/api/v1/imports/resource-interfaces-ips/templates",
    }
    for legacy in (
        "/api/v1/imports/resources",
        "/api/v1/imports/resources/validate",
        "/api/v1/imports/resources/templates",
    ):
        assert legacy in paths


# =============================================================================
# V11: real PostgreSQL two-session concurrency
# =============================================================================


def test_td3_f035_v11_1_concurrent_appends_same_host(
    role_client_factory, auth_session_factory
):
    """V11.1: two appends to one host with different names both succeed."""
    admin, user, _ = role_client_factory("ADMIN")
    c = _cluster(admin, code="F35P")
    _network(admin, c["id"], name="f35-net", cidr="10.64.0.0/24")
    host = _api_resource(admin, c["code"], "f35-h15")
    operator = _operator(user)

    def make(name, ip):
        def _fn():
            session = auth_session_factory()
            try:
                return _write_service(
                    session,
                    operator,
                    [
                        _row(
                            cluster=c["code"],
                            hostname="f35-h15",
                            resource_type=BM,
                            name=name,
                            network="f35-net",
                            ip=ip,
                        )
                    ],
                )
            finally:
                session.close()

        return _fn

    with auth_session_factory() as session:
        before_counts = _counts(session)
        before_host = _host_state(session, host["id"])
    results = _run_pair(make("ethA", "10.64.0.11"), make("ethB", "10.64.0.12"))
    assert all(isinstance(result, tuple) for result in results), results

    with auth_session_factory() as session:
        after_counts = _counts(session)
        after_host = _host_state(session, host["id"])
        names = sorted(
            row["name"]
            for row in _many(
                session,
                "SELECT name FROM interfaces WHERE resource_id = :id",
                {"id": host["id"]},
            )
        )
    _assert_host_untouched(before_host, after_host)
    assert names == ["ethA", "ethB"]
    assert after_counts["interfaces"] == before_counts["interfaces"] + 2
    assert after_counts["ip_addresses"] == before_counts["ip_addresses"] + 2
    assert after_counts["audit_logs"] == before_counts["audit_logs"] + 4


def test_td3_f035_v11_2_concurrent_same_interface_name(
    role_client_factory, auth_session_factory
):
    """V11.2: same host + same Interface name -> exactly one winner, field=name."""
    admin, user, _ = role_client_factory("ADMIN")
    c = _cluster(admin, code="F35Q")
    _network(admin, c["id"], name="f35-net", cidr="10.65.0.0/24")
    host = _api_resource(admin, c["code"], "f35-h16")
    operator = _operator(user)

    def make(ip):
        def _fn():
            session = auth_session_factory()
            try:
                return _write_service(
                    session,
                    operator,
                    [
                        _row(
                            cluster=c["code"],
                            hostname="f35-h16",
                            resource_type=BM,
                            name="eth0",
                            network="f35-net",
                            ip=ip,
                        )
                    ],
                )
            finally:
                session.close()

        return _fn

    with auth_session_factory() as session:
        before_counts = _counts(session)
    results = _run_pair(make("10.65.0.11"), make("10.65.0.12"))
    successes = [result for result in results if isinstance(result, tuple)]
    failures = [result for result in results if isinstance(result, ImportValidationFailed)]
    assert len(successes) == 1, results
    assert len(failures) == 1, results
    assert _find_error(failures[0].details, "name") is not None, failures[0].details

    with auth_session_factory() as session:
        after_counts = _counts(session)
        new_ifaces = session.execute(
            text("SELECT count(*) FROM interfaces WHERE resource_id = :id"),
            {"id": host["id"]},
        ).scalar_one()
        new_ips = session.execute(
            text(
                "SELECT count(*) FROM ip_addresses ip JOIN interfaces i "
                "ON i.id = ip.interface_id WHERE i.resource_id = :id"
            ),
            {"id": host["id"]},
        ).scalar_one()
    assert new_ifaces == 1 and new_ips == 1
    assert after_counts["audit_logs"] == before_counts["audit_logs"] + 2


def test_td3_f035_v11_3_concurrent_same_ip_on_two_append_hosts(
    role_client_factory, auth_session_factory
):
    """V11.3: two append groups (different hosts) race for one address."""
    admin, user, _ = role_client_factory("ADMIN")
    c = _cluster(admin, code="F35S")
    _network(admin, c["id"], name="f35-net", cidr="10.67.0.0/24")
    _api_resource(admin, c["code"], "f35-h19")
    _api_resource(admin, c["code"], "f35-h20")
    operator = _operator(user)

    def make(hostname):
        def _fn():
            session = auth_session_factory()
            try:
                return _write_service(
                    session,
                    operator,
                    [
                        _row(
                            cluster=c["code"],
                            hostname=hostname,
                            resource_type=BM,
                            name="eth0",
                            network="f35-net",
                            ip="10.67.0.11",
                        )
                    ],
                )
            finally:
                session.close()

        return _fn

    with auth_session_factory() as session:
        before_counts = _counts(session)
    results = _run_pair(make("f35-h19"), make("f35-h20"))
    successes = [result for result in results if isinstance(result, tuple)]
    failures = [result for result in results if isinstance(result, ImportValidationFailed)]
    assert len(successes) == 1, results
    assert len(failures) == 1, results
    assert _find_error(failures[0].details, "ip") is not None, failures[0].details

    with auth_session_factory() as session:
        after_counts = _counts(session)
        stored = session.execute(
            text("SELECT count(*) FROM ip_addresses WHERE address = '10.67.0.11'")
        ).scalar_one()
    assert stored == 1
    assert after_counts["interfaces"] == before_counts["interfaces"] + 1
    assert after_counts["ip_addresses"] == before_counts["ip_addresses"] + 1
    assert after_counts["audit_logs"] == before_counts["audit_logs"] + 2


def test_td3_f035_v11_5_no_lock_cycle_between_vm_host_and_append_host(
    role_client_factory, auth_session_factory
):
    """V11.5 (DR-F035-03): reversed VM-host / append-host sets must not deadlock.

    Batch A creates a VM on host H1 and appends to H2; batch B creates a VM on
    H2 and appends to H1. The ``resources`` pre-lock must be one statement over
    the union in ascending id order, otherwise the two batches deadlock
    (``40P01`` -> 500 ``INTERNAL_ERROR``).
    """
    admin, user, _ = role_client_factory("ADMIN")
    c = _cluster(admin, code="F35R")
    _network(admin, c["id"], name="f35-net", cidr="10.66.0.0/24")
    h1 = _api_resource(admin, c["code"], "f35-h17")
    h2 = _api_resource(admin, c["code"], "f35-h18")
    operator = _operator(user)

    def make(vm_host, append_host, vm_ip, append_ip, interface_name):
        def _fn():
            session = auth_session_factory()
            try:
                return _write_service(
                    session,
                    operator,
                    [
                        _row(
                            cluster=c["code"],
                            hostname=f"f35-vm-{interface_name.lower()}",
                            resource_type=VM,
                            host=vm_host,
                            vcpu="2",
                            memory_mb="4096",
                            name="eth0",
                            network="f35-net",
                            ip=vm_ip,
                        ),
                        _row(
                            cluster=c["code"],
                            hostname=append_host,
                            resource_type=BM,
                            name=interface_name,
                            network="f35-net",
                            ip=append_ip,
                        ),
                    ],
                )
            finally:
                session.close()

        return _fn

    with auth_session_factory() as session:
        before_counts = _counts(session)
        before_h1 = _host_state(session, h1["id"])
        before_h2 = _host_state(session, h2["id"])
    results = _run_pair(
        make("f35-h17", "f35-h18", "10.66.0.11", "10.66.0.12", "ethA"),
        make("f35-h18", "f35-h17", "10.66.0.13", "10.66.0.14", "ethB"),
    )
    assert all(isinstance(result, tuple) for result in results), results

    with auth_session_factory() as session:
        after_counts = _counts(session)
        after_h1 = _host_state(session, h1["id"])
        after_h2 = _host_state(session, h2["id"])
    _assert_host_untouched(before_h1, after_h1)
    _assert_host_untouched(before_h2, after_h2)
    assert after_counts["resources"] == before_counts["resources"] + 2
    assert after_counts["interfaces"] == before_counts["interfaces"] + 4
    assert after_counts["ip_addresses"] == before_counts["ip_addresses"] + 4
