"""F035 追加导入 — TEST 阶段 Tester 独立补充用例。

补齐 `docs/features/F035/test-report.md` §1（TD-F035-1）中、由 Backend 用例未直接
覆盖或需 Tester 独立复述的判据：

* `TD3-F035-T118.*`（V2 硬判据独立复述：全列快照 + `xmin` + `version` /
  `updated_at` + 既有子对象 + 无 `resource` UPDATE Audit + Activity + 计数）
* `TD3-F035-T117.3`（csv / xlsx 载体追加结果一致）
* `TD3-F035-T119.3/.4`（逐列不一致 → 模板列名归因，BM 与 VM 各一组）
* `TD3-F035-T119.*` 的 `TD-I-4` (a)–(d) 行号集合与 `TD-I-5` 附加错误：**只登记**
* `TD3-F035-T121.1–.5`（V5 Interface 追加规则：默认值、格式、组内同名聚合、列默认）
* `TD3-F035-T122.1/.2/.4/.5/.6`（V6 IP 追加规则：可分配边界、手动分配、不触发
  自动分配、Network 状态/软删）
* `TD3-F035-T123.4`（预校验通过后目标 IP 被外部占用 → 422 `field="ip"`，零残留）
* `TD3-F035-T67.1`（追加路径上文件内重复 IP / 现存 IP 仍报错，已存在 hostname 不报错）
* `TD3-F035-V11.4`（真实 PG 双会话并发新建同 hostname：恰一成功，败方
  `field="hostname"`）

真实 PostgreSQL（`TEST_DATABASE_URL`，DB-D10 守卫）。夹具与写库纪律沿用
`tests/conftest.py`（`auth_app` / `auth_session_factory` / `committed_engine`
函数级 `TRUNCATE`）；hostname / IP 统一前缀 `f35t-` 避免与 Backend 用例撞键。
"""

from __future__ import annotations

import csv
import io
import json
import threading

from openpyxl import Workbook
from sqlalchemy import text

from app.core.config import Settings
from app.core.errors import ImportValidationFailed
from app.services import resource_interface_ip_import as unified
from integration.test_ip_addresses import (  # noqa: F401  (reused fixtures)
    _cluster,
    _interface,
    _ip,
    _network,
    _operator,
    _pool,
    role_client_factory,
)

VALIDATE = "/api/v1/imports/resource-interfaces-ips/validate"
WRITE = "/api/v1/imports/resource-interfaces-ips"

BM = "BARE_METAL"
VM = "VIRTUAL_MACHINE"

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
    "networks",
    "ip_pools",
    "services",
    "service_endpoints",
    "audit_logs",
)


# --- helpers ----------------------------------------------------------------


def _row(**values) -> list[str]:
    return ["" if values.get(h) is None else str(values.get(h)) for h in HEADERS]


def _csv_bytes(rows: list[list[str]]) -> bytes:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(HEADERS)
    for row in rows:
        writer.writerow(row)
    return buffer.getvalue().encode("utf-8")


def _xlsx_bytes(rows: list[list[str]]) -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(HEADERS)
    for row in rows:
        sheet.append(row)
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def _post(client, path: str, data: bytes, fmt: str = "csv"):
    return client.post(
        path,
        files={"file": (f"import.{fmt}", data, "application/octet-stream")},
        data={"format": fmt},
    )


def _validate(client, rows, fmt: str = "csv"):
    payload = _csv_bytes(rows) if fmt == "csv" else _xlsx_bytes(rows)
    return _post(client, VALIDATE, payload, fmt)


def _write(client, rows, fmt: str = "csv"):
    payload = _csv_bytes(rows) if fmt == "csv" else _xlsx_bytes(rows)
    return _post(client, WRITE, payload, fmt)


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


def _one(session, sql: str, params: dict | None = None) -> dict | None:
    row = session.execute(text(sql), params or {}).mappings().first()
    return dict(row) if row is not None else None


def _many(session, sql: str, params: dict | None = None) -> list[dict]:
    return [dict(r) for r in session.execute(text(sql), params or {}).mappings().all()]


def _host_state(session, host_id: str) -> dict:
    """Full-column snapshot of a host Resource and its existing children."""
    return {
        "resource": _one(session, "SELECT * FROM resources WHERE id = :id", {"id": host_id}),
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
            "SELECT ip.* FROM ip_addresses ip JOIN interfaces i ON i.id = ip.interface_id "
            "WHERE i.resource_id = :id ORDER BY ip.id",
            {"id": host_id},
        ),
    }


def _assert_host_untouched(before: dict, after: dict) -> None:
    assert after["resource"] == before["resource"], "existing Resource row changed"
    assert after["xmin"] == before["xmin"], "resources row was UPDATEd (xmin changed)"
    assert after["bm"] == before["bm"], "bare_metal_details changed"
    assert after["vm"] == before["vm"], "virtual_machine_details changed"
    for key in ("interfaces", "ips"):
        after_by_id = {str(row["id"]): row for row in after[key]}
        for row in before[key]:
            assert after_by_id.get(str(row["id"])) == row, (key, row["id"])


def _audit_by_object(session, object_id: str) -> dict[tuple[str, str], int]:
    rows = session.execute(
        text(
            "SELECT object_type, action, count(*) FROM audit_logs "
            "WHERE object_id = :id GROUP BY object_type, action"
        ),
        {"id": object_id},
    ).all()
    return {(row[0], row[1]): int(row[2]) for row in rows}


def _write_service(session, operator, rows) -> tuple:
    return unified.write_import(
        session, operator, _csv_bytes(rows), "csv", Settings(_env_file=None)
    )


def _residue_free(session, before: dict, after: dict) -> None:
    assert after == before, f"batch left residue: {before} -> {after}"


def _run_pair(fn_a, fn_b):
    barrier = threading.Barrier(2)
    results: list[object] = []
    lock = threading.Lock()

    def runner(fn):
        barrier.wait(timeout=10)
        try:
            outcome = fn()
        except Exception as exc:  # noqa: BLE001 - collected as the outcome
            outcome = exc
        with lock:
            results.append(outcome)

    threads = [threading.Thread(target=runner, args=(fn,)) for fn in (fn_a, fn_b)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)
    assert all(not thread.is_alive() for thread in threads), "concurrent session hung"
    return results


# =============================================================================
# T118 / V2 — Tester independent restatement of the "host untouched" gate
# =============================================================================


def test_td3_f035_t118_full_zero_change_gate_on_bm_host(
    role_client_factory, auth_session_factory
):
    """T118.1-.4 / T125.3: append leaves host + existing children byte-identical."""
    editor, _, _ = role_client_factory("EDITOR")
    c = _cluster(editor, code="F35TA")
    net = _network(editor, c["id"], name="f35t-net", cidr="10.80.0.0/24")
    host = _api_resource(
        editor,
        c["code"],
        "f35t-h1",
        role="COMPUTE",
        status="IDLE",
        hardware={
            "manufacturer": "Dell",
            "model": "PowerEdge R750",
            "serial_number": "SN-T-1",
            "cpu_model": "Xeon 8358",
            "cpu_sockets": 2,
            "cpu_cores": 64,
            "memory_mb": 262144,
            "gpu_model": "A100",
            "gpu_count": 8,
        },
    )
    existing_iface = _interface(editor, host["id"], "eth0")
    existing_ip = _ip(editor, net["id"], "10.80.0.10")
    bound = editor.patch(
        f"/api/v1/ip-addresses/{existing_ip['id']}",
        json={"version": existing_ip["version"], "interface": existing_iface["id"]},
    )
    assert bound.status_code == 200, bound.text
    assert bound.json()["ip_address"]["interface"]["id"] == existing_iface["id"]

    rows = [
        _row(
            cluster=c["code"],
            hostname="f35t-h1",
            resource_type=BM,
            role="COMPUTE",
            status="IDLE",
            manufacturer="Dell",
            name="eth1",
            interface_type="PHYSICAL",
            network="f35t-net",
            ip="10.80.0.11",
        ),
        _row(
            cluster=c["code"],
            hostname="f35t-h1",
            resource_type=BM,
            role="COMPUTE",
            status="IDLE",
            manufacturer="Dell",
            name="eth2",
            network="f35t-net",
            ip="10.80.0.12",
        ),
    ]
    with auth_session_factory() as session:
        before_counts = _counts(session)
        before_host = _host_state(session, host["id"])
        # Fixture setup legitimately writes UPDATE audits (e.g. F010 IP binding),
        # so the "no non-CREATE audit" check below is a delta, not an absolute.
        before_non_create = session.execute(
            text("SELECT count(*) FROM audit_logs WHERE action <> 'CREATE'")
        ).scalar_one()
    before_activity = editor.get(
        f"/api/v1/resources/{host['id']}/activity", params={"page_size": 100}
    ).json()

    assert _validate(editor, rows).json()["error_count"] == 0
    resp = _write(editor, rows)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert set(body) == {
        "created",
        "total_rows",
        "interfaces_created",
        "ip_addresses_created",
    }, "T124.2: response key set must stay exactly 4"
    assert (body["created"], body["total_rows"], body["interfaces_created"]) == (0, 2, 2)
    assert body["ip_addresses_created"] == 2

    with auth_session_factory() as session:
        after_counts = _counts(session)
        after_host = _host_state(session, host["id"])
        new_ifaces = _many(
            session,
            "SELECT * FROM interfaces WHERE resource_id = :id ORDER BY name",
            {"id": host["id"]},
        )
        new_ips = _many(
            session,
            "SELECT ip.* FROM ip_addresses ip JOIN interfaces i ON i.id = ip.interface_id "
            "WHERE i.resource_id = :id ORDER BY ip.address::text",
            {"id": host["id"]},
        )
        resource_updates = session.execute(
            text(
                "SELECT count(*) FROM audit_logs WHERE object_type = 'resource' "
                "AND object_id = :id AND action = 'UPDATE'"
            ),
            {"id": host["id"]},
        ).scalar_one()
        non_create = session.execute(
            text("SELECT count(*) FROM audit_logs WHERE action <> 'CREATE'")
        ).scalar_one()
        before_ids = {
            str(row["id"]) for row in before_host["interfaces"] + before_host["ips"]
        }
        added_ips = [row for row in new_ips if str(row["id"]) not in before_ids]
        added_ifaces = [row for row in new_ifaces if str(row["id"]) not in before_ids]
        audits = {
            str(row["id"]): _audit_by_object(session, str(row["id"])) for row in added_ips
        }
        iface_audits = {
            str(row["id"]): _audit_by_object(session, str(row["id"]))
            for row in added_ifaces
        }

    _assert_host_untouched(before_host, after_host)
    assert after_host["resource"]["version"] == 1
    assert str(after_host["resource"]["updated_at"]) == str(before_host["resource"]["updated_at"])
    assert resource_updates == 0
    assert non_create == before_non_create, "the append batch must not write UPDATE/DELETE audits"

    # 1 new Interface + 2 new IPs, each with exactly one CREATE audit
    assert [row["name"] for row in new_ifaces] == ["eth0", "eth1", "eth2"]
    assert after_counts["interfaces"] == before_counts["interfaces"] + 2
    assert after_counts["ip_addresses"] == before_counts["ip_addresses"] + 2
    assert after_counts["audit_logs"] == before_counts["audit_logs"] + 4
    assert after_counts["resources"] == before_counts["resources"]
    assert after_counts["bare_metal_details"] == before_counts["bare_metal_details"]
    for table in ("clusters", "networks", "ip_pools", "services", "service_endpoints"):
        assert after_counts[table] == before_counts[table], f"{table} changed (T125.3)"
    assert len(iface_audits) == 2 and len(audits) == 2, (iface_audits, audits)
    for iface_id, actions in iface_audits.items():
        assert actions == {("interface", "CREATE"): 1}, (iface_id, actions)
    for ip_id, actions in audits.items():
        assert actions == {("ip_address", "CREATE"): 1}, (ip_id, actions)

    # Activity: no UPDATE / DELETE / RESTORE item, total unchanged
    after_activity = editor.get(
        f"/api/v1/resources/{host['id']}/activity", params={"page_size": 100}
    ).json()
    assert {item["action"] for item in after_activity["items"]} <= {"CREATE"}
    assert after_activity["total"] == before_activity["total"]


# =============================================================================
# A1 / A2 / A5 — zero Schema drift (`docs/database/f023-import.md` §5.2)
# =============================================================================


def test_td3_f035_a1_a2_a5_zero_schema_drift(db_session, alembic_runner):
    """A1 no new migration, A2 partial unique indexes intact, A5 immutability trigger."""
    from pathlib import Path

    head = alembic_runner.head_revision()
    assert head == "0015_user_cluster_authorizations", head
    versions = Path(alembic_runner._config().get_main_option("script_location")) / "versions"
    files = sorted(path.name for path in versions.iterdir() if path.suffix == ".py")
    assert len(files) == 15, files  # 0001..0015 (F023 基线不变，F035 零新迁移)
    assert all("f035" not in name.lower() for name in files), "F035 must add no migration"

    def indexdef(name: str) -> str:
        return db_session.execute(
            text("SELECT indexdef FROM pg_indexes WHERE schemaname = 'public' AND indexname = :n"),
            {"n": name},
        ).scalar_one()

    for name in (
        "uq_resources_cluster_id_hostname_key",
        "uq_interfaces_resource_id_name",
        "uq_ip_addresses_cluster_id_address",
    ):
        definition = indexdef(name)
        assert "UNIQUE INDEX" in definition, definition
        assert "deleted_at IS NULL" in definition, definition

    trigger = db_session.execute(
        text(
            "SELECT pg_get_triggerdef(oid) FROM pg_trigger "
            "WHERE tgname = 'trg_resources_immutable_fields'"
        )
    ).scalar_one()
    assert "BEFORE UPDATE" in trigger.upper(), trigger

    expected_tables = {
        "alembic_version",
        "users",
        "user_sessions",
        "clusters",
        "audit_logs",
        "resources",
        "bare_metal_details",
        "virtual_machine_details",
        "interfaces",
        "networks",
        "ip_pools",
        "ip_addresses",
        "services",
        "service_endpoints",
        "api_keys",
        "user_cluster_authorizations",
    }
    tables = set(
        db_session.execute(
            text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
        ).scalars()
    )
    assert tables == expected_tables, tables ^ expected_tables


# =============================================================================
# T117.3 — carriers (csv / xlsx) append identically
# =============================================================================


def test_td3_f035_t117_3_csv_and_xlsx_append_identically(
    role_client_factory, auth_session_factory
):
    """T117.3: the same rows append identically through csv and xlsx carriers."""
    editor, _, _ = role_client_factory("EDITOR")
    c = _cluster(editor, code="F35TB")
    net = _network(editor, c["id"], name="f35t-net", cidr="10.81.0.0/24")
    host_csv = _api_resource(editor, c["code"], "f35t-hcsv")
    host_xlsx = _api_resource(editor, c["code"], "f35t-hxlsx")

    def rows_for(hostname: str, ip: str):
        return [
            _row(
                cluster=c["code"],
                hostname=hostname,
                resource_type=BM,
                name="bond0",
                interface_type="BOND",
                mac_address="AA:bb:CC:00:11:22",
                speed_mbps="10000",
                mtu="9000",
                enabled="1",
                network="f35t-net",
                ip=ip,
            )
        ]

    csv_rows = rows_for("f35t-hcsv", "10.81.0.11")
    xlsx_rows = rows_for("f35t-hxlsx", "10.81.0.12")

    csv_valid = _validate(editor, csv_rows, "csv").json()
    xlsx_valid = _validate(editor, xlsx_rows, "xlsx").json()
    assert csv_valid["error_count"] == 0 and xlsx_valid["error_count"] == 0
    assert (csv_valid["total_rows"], csv_valid["importable_rows"]) == (1, 1)
    assert (xlsx_valid["total_rows"], xlsx_valid["importable_rows"]) == (1, 1)

    assert _write(editor, csv_rows, "csv").status_code == 201
    assert _write(editor, xlsx_rows, "xlsx").status_code == 201

    with auth_session_factory() as session:
        projections = {}
        for label, host_id in (("csv", host_csv["id"]), ("xlsx", host_xlsx["id"])):
            projections[label] = _many(
                session,
                "SELECT i.resource_id, i.name, i.interface_type, i.mac_address, "
                "i.speed_mbps, i.mtu, i.enabled, ip.address::text AS address, "
                "ip.network_id, ip.cluster_id "
                "FROM interfaces i JOIN ip_addresses ip ON ip.interface_id = i.id "
                "WHERE i.resource_id = :id",
                {"id": host_id},
            )
    assert len(projections["csv"]) == len(projections["xlsx"]) == 1
    csv_row, xlsx_row = projections["csv"][0], projections["xlsx"][0]
    for key in ("name", "interface_type", "mac_address", "speed_mbps", "mtu", "enabled", "network_id", "cluster_id"):
        assert csv_row[key] == xlsx_row[key], key
    assert csv_row["name"] == "bond0"
    assert csv_row["interface_type"] == "BOND"
    assert csv_row["mac_address"] == "AA:bb:CC:00:11:22"
    assert csv_row["enabled"] is True
    assert csv_row["address"] == "10.81.0.11/32"
    assert xlsx_row["address"] == "10.81.0.12/32"
    assert str(csv_row["resource_id"]) == host_csv["id"]
    assert str(xlsx_row["resource_id"]) == host_xlsx["id"]


# =============================================================================
# T119.3 / T119.4 — per-column attribution (BM and VM hardware columns)
# =============================================================================


def test_td3_f035_t119_3_bm_hardware_column_attribution(
    role_client_factory, auth_session_factory
):
    """T119.3: each BM hardware column mismatch is attributed to its template column."""
    editor, _, _ = role_client_factory("EDITOR")
    c = _cluster(editor, code="F35TC")
    net = _network(editor, c["id"], name="f35t-net", cidr="10.82.0.0/24")
    _api_resource(
        editor,
        c["code"],
        "f35t-hbm",
        role="COMPUTE",
        status="IDLE",
        hardware={
            "manufacturer": "Dell",
            "model": "PowerEdge R750",
            "serial_number": "SN-C-1",
            "cpu_model": "Xeon 8358",
            "cpu_sockets": 2,
            "cpu_cores": 64,
            "memory_mb": 262144,
            "gpu_model": "A100",
            "gpu_count": 8,
        },
    )
    cases = {
        "manufacturer": "HPE",
        "cpu_cores": "32",
        "gpu_count": "4",
        "memory_mb": "131072",
        "model": "PowerEdge R650",
        "serial_number": "SN-C-2",
        "cpu_model": "Xeon 6338",
        "cpu_sockets": "1",
        "gpu_model": "H100",
    }
    with auth_session_factory() as session:
        before = _counts(session)
    for column, value in cases.items():
        payload = _validate(
            editor,
            [
                _row(
                    cluster=c["code"],
                    hostname="f35t-hbm",
                    resource_type=BM,
                    **{column: value},
                    name="eth9",
                    network="f35t-net",
                    ip="10.82.0.11",
                )
            ],
        ).json()
        error = _find_error(payload, column, 2)
        assert error is not None, (column, payload["errors"])
        assert error["related_row"] is None, (column, error)
        assert error["reason"], (column, error)
        assert payload["error_count"] >= 1
        write = _write(
            editor,
            [
                _row(
                    cluster=c["code"],
                    hostname="f35t-hbm",
                    resource_type=BM,
                    **{column: value},
                    name="eth9",
                    network="f35t-net",
                    ip="10.82.0.11",
                )
            ],
        )
        assert write.status_code == 422, (column, write.text)
        assert write.json()["error"]["code"] == "IMPORT_VALIDATION_FAILED"
        assert _find_error(write.json()["error"]["details"], column) is not None
    with auth_session_factory() as session:
        after = _counts(session)
    _residue_free(session, before, after)


def test_td3_f035_t119_4_vm_column_attribution(role_client_factory, auth_session_factory):
    """T119.4: VM columns (vcpu / disk_gb / hypervisor / memory_mb / host)."""
    editor, _, _ = role_client_factory("EDITOR")
    c = _cluster(editor, code="F35TD")
    net = _network(editor, c["id"], name="f35t-net", cidr="10.83.0.0/24")
    bm = _api_resource(editor, c["code"], "f35t-bm1")
    other_bm = _api_resource(editor, c["code"], "f35t-bm2")
    vm = _api_resource(
        editor,
        c["code"],
        "f35t-vm1",
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
    cases = {
        "vcpu": "16",
        "disk_gb": "200",
        "hypervisor": "VMware",
        "memory_mb": "65536",
        "host": "f35t-bm2",
    }
    with auth_session_factory() as session:
        before = _counts(session)
        before_host = _host_state(session, vm["id"])
    for column, value in cases.items():
        cells = {
            "cluster": c["code"],
            "hostname": "f35t-vm1",
            "resource_type": VM,
            "host": "f35t-bm1",
            "vcpu": "8",
            "memory_mb": "32768",
            "disk_gb": "100",
            "hypervisor": "KVM",
            "name": "eth3",
            "network": "f35t-net",
            "ip": "10.83.0.11",
        }
        cells[column] = value
        payload = _validate(editor, [_row(**cells)]).json()
        error = _find_error(payload, column, 2)
        assert error is not None, (column, payload["errors"])
        assert error["related_row"] is None
        assert _write(editor, [_row(**cells)]).status_code == 422, column
    with auth_session_factory() as session:
        after = _counts(session)
        after_host = _host_state(session, vm["id"])
    _residue_free(session, before, after)
    _assert_host_untouched(before_host, after_host)
    assert other_bm["id"] != bm["id"]


# =============================================================================
# TD-I-4 / TD-I-5 — recorded implementation freedom (not pass/fail criteria)
# =============================================================================


def test_td3_f035_t119_tdi4_tdi5_recorded_row_sets(
    role_client_factory, auth_session_factory, capsys
):
    """TD-I-4 (a)-(d) + TD-I-5: assert the mandated minimum, record the rest."""
    editor, _, _ = role_client_factory("EDITOR")
    c = _cluster(editor, code="F35TE")
    net = _network(editor, c["id"], name="f35t-net", cidr="10.84.0.0/24")
    _api_resource(editor, c["code"], "f35t-h4", role="COMPUTE", status="IDLE")
    other_bm = _api_resource(editor, c["code"], "f35t-bm4")

    # --- TD-I-4: three rows of one group all supply a differing role ---------
    payload = _validate(
        editor,
        [
            _row(
                cluster=c["code"],
                hostname="f35t-h4",
                resource_type=BM,
                role="GPU",
                name=f"eth{i}",
                network="f35t-net",
                ip=f"10.84.0.1{i}",
            )
            for i in (1, 2, 3)
        ],
    ).json()
    role_errors = [e for e in payload["errors"] if e["field"] == "role"]
    rows_reported = sorted(error["row"] for error in role_errors)
    print("TD-I-4 role mismatch rows:", json.dumps(rows_reported))
    assert rows_reported, "at least one row of the group must report field=role (T119)"
    assert all(error["related_row"] is None for error in role_errors)
    keys = [(error["row"], error["field"]) for error in payload["errors"]]
    assert len(keys) == len(set(keys)), "duplicate (row, field) error"
    assert set(rows_reported) <= {2, 3, 4}

    # --- TD-I-5: resource_type mismatch on a BM host -------------------------
    vm_rows = [
        _row(
            cluster=c["code"],
            hostname="f35t-h4",
            resource_type=VM,
            host="f35t-bm4",
            vcpu="4",
            memory_mb="8192",
            name="eth5",
            network="f35t-net",
            ip="10.84.0.15",
        )
    ]
    vm_payload = _validate(editor, vm_rows).json()
    print("TD-I-5 error fields:", json.dumps(sorted({e["field"] for e in vm_payload["errors"]})))
    assert _find_error(vm_payload, "resource_type") is not None, vm_payload["errors"]
    with auth_session_factory() as session:
        before = _counts(session)
    write = _write(editor, vm_rows)
    assert write.status_code == 422, write.text
    details = write.json()["error"]["details"]
    assert _find_error(details, "resource_type") is not None
    with auth_session_factory() as session:
        after = _counts(session)
    _residue_free(session, before, after)
    assert other_bm["id"]  # referenced host exists (row itself parsed fine)


# =============================================================================
# T121 / V5 — Interface append rules
# =============================================================================


def test_td3_f035_t121_1_2_3_interface_defaults_and_formats(
    role_client_factory, auth_session_factory
):
    """T121.1/.2/.3: defaults (OTHER / enabled=true), mac case, speed/mtu, invalid."""
    editor, _, _ = role_client_factory("EDITOR")
    c = _cluster(editor, code="F35TF")
    net = _network(editor, c["id"], name="f35t-net", cidr="10.85.0.0/24")
    host = _api_resource(editor, c["code"], "f35t-h5")
    _interface(editor, host["id"], "eth0")

    rows = [
        _row(
            cluster=c["code"],
            hostname="f35t-h5",
            resource_type=BM,
            name="f35t-plain",
            network="f35t-net",
            ip="10.85.0.11",
        ),
        _row(
            cluster=c["code"],
            hostname="f35t-h5",
            resource_type=BM,
            name="f35t-off1",
            enabled="0",
            network="f35t-net",
            ip="10.85.0.12",
        ),
        _row(
            cluster=c["code"],
            hostname="f35t-h5",
            resource_type=BM,
            name="f35t-off2",
            enabled="false",
            network="f35t-net",
            ip="10.85.0.13",
        ),
        _row(
            cluster=c["code"],
            hostname="f35t-h5",
            resource_type=BM,
            name="f35t-mac",
            mac_address="AA:bb:CC:00:11:22",
            speed_mbps="10000",
            mtu="9000",
            network="f35t-net",
            ip="10.85.0.14",
        ),
    ]
    assert _validate(editor, rows).json()["error_count"] == 0
    resp = _write(editor, rows)
    assert resp.status_code == 201, resp.text
    assert resp.json()["interfaces_created"] == 4

    with auth_session_factory() as session:
        stored = {
            row["name"]: row
            for row in _many(
                session,
                "SELECT * FROM interfaces WHERE resource_id = :id",
                {"id": host["id"]},
            )
        }
    plain = stored["f35t-plain"]
    assert plain["interface_type"] == "OTHER" and plain["enabled"] is True
    assert plain["mac_address"] is None and plain["speed_mbps"] is None
    assert plain["mtu"] is None and plain["parent_interface_id"] is None
    assert plain["description"] is None and plain["metadata"] == {}
    assert stored["f35t-off1"]["enabled"] is False
    assert stored["f35t-off2"]["enabled"] is False
    mac = stored["f35t-mac"]
    assert mac["mac_address"] == "AA:bb:CC:00:11:22", "case must be preserved"
    assert mac["speed_mbps"] == 10000 and mac["mtu"] == 9000

    # invalid values are row errors on the append path (整批回滚)
    for column, value in (("mtu", "0"), ("speed_mbps", "abc"), ("mtu", "-1")):
        bad = [
            _row(
                cluster=c["code"],
                hostname="f35t-h5",
                resource_type=BM,
                name="f35t-bad",
                network="f35t-net",
                ip="10.85.0.20",
                **{column: value},
            )
        ]
        payload = _validate(editor, bad).json()
        assert _find_error(payload, column) is not None, (column, value, payload["errors"])
        with auth_session_factory() as session:
            before = _counts(session)
        assert _write(editor, bad).status_code == 422
        with auth_session_factory() as session:
            after = _counts(session)
        _residue_free(session, before, after)


def test_td3_f035_t121_4_5_same_name_group_in_one_interface(
    role_client_factory, auth_session_factory
):
    """T121.4/.5: same name in one group -> 1 Interface, 2 IPs, sane defaults."""
    editor, _, _ = role_client_factory("EDITOR")
    c = _cluster(editor, code="F35TG")
    net = _network(editor, c["id"], name="f35t-net", cidr="10.86.0.0/24")
    host = _api_resource(editor, c["code"], "f35t-h6")

    rows = [
        _row(
            cluster=c["code"],
            hostname="f35t-h6",
            resource_type=BM,
            name="f35t-bond",
            network="f35t-net",
            ip="10.86.0.11",
        ),
        _row(
            cluster=c["code"],
            hostname="f35t-h6",
            resource_type=BM,
            name="f35t-bond",
            network="f35t-net",
            ip="10.86.0.12",
        ),
    ]
    assert _validate(editor, rows).json()["error_count"] == 0
    resp = _write(editor, rows)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert (body["interfaces_created"], body["ip_addresses_created"]) == (1, 2)
    assert body["created"] == 0

    with auth_session_factory() as session:
        ifaces = _many(
            session,
            "SELECT * FROM interfaces WHERE resource_id = :id",
            {"id": host["id"]},
        )
        ips = _many(
            session,
            "SELECT address::text, interface_id FROM ip_addresses "
            "WHERE interface_id = :id ORDER BY address",
            {"id": ifaces[0]["id"]},
        )
    assert len(ifaces) == 1
    assert ifaces[0]["parent_interface_id"] is None
    assert ifaces[0]["description"] is None
    assert ifaces[0]["metadata"] == {}
    assert len(ips) == 2
    assert {row["address"] for row in ips} == {"10.86.0.11/32", "10.86.0.12/32"}


# =============================================================================
# T122 / V6 — IP append rules
# =============================================================================


def test_td3_f035_t122_1_allocatable_boundaries_on_append_path(
    role_client_factory, auth_session_factory
):
    """T122.1: CIDR / §11.1 boundaries are enforced for append rows too."""
    editor, _, _ = role_client_factory("EDITOR")
    c = _cluster(editor, code="F35TH")
    host = _api_resource(editor, c["code"], "f35t-h7")
    n30 = _network(editor, c["id"], name="f35t-n30", cidr="10.87.0.0/30")
    ngw = _network(editor, c["id"], name="f35t-ngw", cidr="10.88.0.0/24", gateway="10.88.0.1")
    nres = _network(editor, c["id"], name="f35t-nres", cidr="10.89.0.0/24")
    _pool(
        editor,
        nres["id"],
        name="f35t-res",
        start="10.89.0.10",
        end="10.89.0.20",
        allocation_mode="RESERVED",
    )

    def check(network, address, expect_error: bool):
        rows = [
            _row(
                cluster=c["code"],
                hostname="f35t-h7",
                resource_type=BM,
                name="f35t-ip",
                network=network,
                ip=address,
            )
        ]
        payload = _validate(editor, rows).json()
        error = _find_error(payload, "ip")
        if expect_error:
            assert error is not None, (network, address, payload["errors"])
            with auth_session_factory() as session:
                before = _counts(session)
            assert _write(editor, rows).status_code == 422, (network, address)
            with auth_session_factory() as session:
                after = _counts(session)
            _residue_free(session, before, after)
        else:
            assert payload["error_count"] == 0, (network, address, payload["errors"])

    check("f35t-n30", "10.87.0.0", True)  # network address
    check("f35t-n30", "10.87.0.3", True)  # broadcast address
    check("f35t-n30", "10.87.0.1", False)
    check("f35t-ngw", "10.88.0.1", True)  # gateway
    check("f35t-ngw", "10.88.0.2", False)
    check("f35t-nres", "10.89.0.10", True)  # RESERVED pool range
    check("f35t-nres", "10.89.0.30", False)
    # address outside the resolved network is rejected (CIDR containment)
    check("f35t-nres", "10.90.0.5", True)

    # §11.1 disabled ranges: Network creation may or may not be allowed, but an
    # address inside a disabled range must never be allocatable via the import.
    for name, cidr, address in (
        ("f35t-ndis1", "127.0.0.0/8", "127.0.0.55"),
        ("f35t-ndis2", "169.254.0.0/16", "169.254.1.5"),
        ("f35t-ndis3", "224.0.0.0/4", "224.0.1.5"),
    ):
        response = editor.post("/api/v1/networks", json={"cluster": c["id"], "name": name, "cidr": cidr})
        if response.status_code != 201:
            print(f"NOTE {cidr}: Network creation rejected ({response.status_code})")
            continue
        check(name, address, True)
    assert n30["cidr"].startswith("10.87.0.0")


def test_td3_f035_t122_4_5_manual_allocation_without_auto(
    role_client_factory, auth_session_factory
):
    """T122.4/.5: pool id derived, pool untouched, no automatic allocation."""
    editor, _, _ = role_client_factory("EDITOR")
    c = _cluster(editor, code="F35TI")
    net = _network(editor, c["id"], name="f35t-nauto", cidr="10.91.0.0/24")
    pool = _pool(
        editor,
        net["id"],
        name="f35t-auto",
        start="10.91.0.10",
        end="10.91.0.20",
        allocation_mode="AUTO",
    )
    host = _api_resource(editor, c["code"], "f35t-h8")
    with auth_session_factory() as session:
        before_pool = _one(session, "SELECT * FROM ip_pools WHERE id = :id", {"id": pool["id"]})
        before = _counts(session)

    rows = [
        _row(
            cluster=c["code"],
            hostname="f35t-h8",
            resource_type=BM,
            name="f35t-eth",
            network="f35t-nauto",
            ip="10.91.0.15",
        )
    ]
    resp = _write(editor, rows)
    assert resp.status_code == 201, resp.text
    assert resp.json()["ip_addresses_created"] == 1

    with auth_session_factory() as session:
        after = _counts(session)
        created = _many(
            session,
            "SELECT * FROM ip_addresses WHERE address = '10.91.0.15/32'",
        )
        after_pool = _one(session, "SELECT * FROM ip_pools WHERE id = :id", {"id": pool["id"]})
    assert len(created) == 1
    assert str(created[0]["ip_pool_id"]) == pool["id"], "覆盖该地址的 Pool id 必须落库"
    assert after_pool == before_pool, "pool row must be untouched"
    assert after_pool["allocation_mode"] == "AUTO"
    assert after["ip_addresses"] == before["ip_addresses"] + 1, "no extra auto allocation"
    assert after["ip_pools"] == before["ip_pools"]
    assert after["networks"] == before["networks"]


def test_td3_f035_t122_6_network_state_and_soft_delete(
    role_client_factory, auth_session_factory
):
    """T122.6: INACTIVE / soft-deleted Network is a row error on the append path."""
    admin, _, _ = role_client_factory("ADMIN")
    c = _cluster(admin, code="F35TJ")
    _api_resource(admin, c["code"], "f35t-h9")
    inactive = _network(
        admin, c["id"], name="f35t-ninact", cidr="10.92.0.0/24", status="INACTIVE"
    )
    deleted = _network(admin, c["id"], name="f35t-ndel", cidr="10.93.0.0/24")
    assert admin.delete(f"/api/v1/networks/{deleted['id']}", params={"version": 1}).status_code == 204

    def rows(network, address):
        return [
            _row(
                cluster=c["code"],
                hostname="f35t-h9",
                resource_type=BM,
                name="f35t-eth9",
                network=network,
                ip=address,
            )
        ]

    for network, address in (("f35t-ninact", "10.92.0.11"), ("f35t-ndel", "10.93.0.11")):
        payload = _validate(admin, rows(network, address)).json()
        assert payload["error_count"] >= 1, (network, payload)
        assert {
            error["field"] for error in payload["errors"]
        } & {"network", "ip"}, payload["errors"]
        with auth_session_factory() as session:
            before = _counts(session)
        assert _write(admin, rows(network, address)).status_code == 422
        with auth_session_factory() as session:
            after = _counts(session)
        _residue_free(session, before, after)
    assert inactive["status"] == "INACTIVE"


# =============================================================================
# T123.4 / T67.1 — write-time revalidation + conflict attribution on append
# =============================================================================


def test_td3_f035_t123_4_write_revalidates_ip_on_append_path(
    role_client_factory, auth_session_factory
):
    """T123.4: pre-validate clear, IP taken externally -> 422 field=ip, no residue."""
    editor, _, _ = role_client_factory("EDITOR")
    c = _cluster(editor, code="F35TK")
    net = _network(editor, c["id"], name="f35t-net", cidr="10.94.0.0/24")
    host = _api_resource(editor, c["code"], "f35t-h10")
    rows = [
        _row(
            cluster=c["code"],
            hostname="f35t-h10",
            resource_type=BM,
            name="f35t-eth10",
            network="f35t-net",
            ip="10.94.0.11",
        )
    ]
    assert _validate(editor, rows).json()["error_count"] == 0
    _ip(editor, net["id"], "10.94.0.11")  # external allocation after pre-validate

    with auth_session_factory() as session:
        before = _counts(session)
        before_host = _host_state(session, host["id"])
    write = _write(editor, rows)
    assert write.status_code == 422, write.text
    details = write.json()["error"]["details"]
    assert write.json()["error"]["code"] == "IMPORT_VALIDATION_FAILED"
    assert _find_error(details, "ip") is not None, details
    with auth_session_factory() as session:
        after = _counts(session)
        after_host = _host_state(session, host["id"])
    assert after["interfaces"] == before["interfaces"]
    assert after["ip_addresses"] == before["ip_addresses"] + 0
    assert after["audit_logs"] == before["audit_logs"]
    assert after["resources"] == before["resources"]
    _assert_host_untouched(before_host, after_host)


def test_td3_f035_t67_1_file_duplicates_and_existing_ip_still_reported(
    role_client_factory, auth_session_factory
):
    """T67.1: in-file duplicate IP and existing IP still error; existing host does not."""
    editor, _, _ = role_client_factory("EDITOR")
    c = _cluster(editor, code="F35TL")
    net = _network(editor, c["id"], name="f35t-net", cidr="10.95.0.0/24")
    host = _api_resource(editor, c["code"], "f35t-h11")
    other = _api_resource(editor, c["code"], "f35t-h12")
    _ip(editor, net["id"], "10.95.0.50")

    payload = _validate(
        editor,
        [
            _row(
                cluster=c["code"],
                hostname="f35t-h11",
                resource_type=BM,
                name="f35t-a",
                network="f35t-net",
                ip="10.95.0.20",
            ),
            _row(
                cluster=c["code"],
                hostname="f35t-h12",
                resource_type=BM,
                name="f35t-b",
                network="f35t-net",
                ip="10.95.0.20",
            ),
            _row(
                cluster=c["code"],
                hostname="f35t-h11",
                resource_type=BM,
                name="f35t-c",
                network="f35t-net",
                ip="10.95.0.50",
            ),
        ],
    ).json()
    duplicate = _find_error(payload, "ip", 3)
    assert duplicate is not None and duplicate["related_row"] == 2, payload["errors"]
    assert _find_error(payload, "ip", 4) is not None, payload["errors"]
    assert _find_error(payload, "hostname") is None, "existing hostname is not a conflict"
    assert payload["error_count"] == 2, payload["errors"]
    assert other["id"] != host["id"]


def test_td3_f035_t122_3_cross_cluster_binding_on_append_path(
    role_client_factory, auth_session_factory
):
    """T122.3: foreign Cluster Network (by name / by mask) is a row error, no residue."""
    editor, _, _ = role_client_factory("EDITOR")
    a = _cluster(editor, code="F35TN")
    b = _cluster(editor, code="F35TO")
    net_a = _network(editor, a["id"], name="f35tn-net", cidr="10.97.0.0/24")
    _network(editor, b["id"], name="f35to-net", cidr="10.98.0.0/24")
    host = _api_resource(editor, a["code"], "f35t-hn")

    def rows(**overrides):
        cells = {
            "cluster": a["code"],
            "hostname": "f35t-hn",
            "resource_type": BM,
            "name": "f35t-ethn",
        }
        cells.update(overrides)
        return [_row(**cells)]

    with auth_session_factory() as session:
        before = _counts(session)
    # foreign Network name (lookup is Cluster-scoped -> not found)
    payload = _validate(editor, rows(network="f35to-net", ip="10.97.0.11")).json()
    assert _find_error(payload, "network") is not None, payload["errors"]
    # /mask resolved to a foreign Cluster CIDR -> ip error
    payload = _validate(editor, rows(ip="10.98.0.11/24")).json()
    assert _find_error(payload, "ip") is not None, payload["errors"]
    for bad in (rows(network="f35to-net", ip="10.97.0.11"), rows(ip="10.98.0.11/24")):
        assert _write(editor, bad).status_code == 422
    with auth_session_factory() as session:
        after = _counts(session)
    _residue_free(session, before, after)
    assert net_a["cluster"]["code"] == a["code"] and host["id"]


def test_td3_f035_t71_1_api_uniqueness_scopes_after_append(role_client_factory):
    """T71.1: import-created rows obey the same API uniqueness scopes (409)."""
    editor, _, _ = role_client_factory("EDITOR")
    c = _cluster(editor, code="F35TP")
    net = _network(editor, c["id"], name="f35tp-net", cidr="10.99.0.0/24")
    host = _api_resource(editor, c["code"], "f35t-hp")

    append_rows = [
        _row(
            cluster=c["code"],
            hostname="f35t-hp",
            resource_type=BM,
            name="f35t-ethp",
            network="f35tp-net",
            ip="10.99.0.11",
        )
    ]
    assert _write(editor, append_rows).status_code == 201

    duplicate_iface = editor.post(
        "/api/v1/interfaces", json={"resource": host["id"], "name": "f35t-ethp"}
    )
    assert duplicate_iface.status_code == 409, duplicate_iface.text
    duplicate_ip = editor.post(
        "/api/v1/ip-addresses", json={"network": net["id"], "address": "10.99.0.11"}
    )
    assert duplicate_ip.status_code == 409, duplicate_ip.text


# =============================================================================
# V11.4 — concurrent create of the same hostname (DB backstop attribution)
# =============================================================================


def test_td3_f035_v11_4_concurrent_same_hostname_create(
    role_client_factory, auth_session_factory
):
    """V11.4: two batches create the same hostname; loser reports field=hostname."""
    admin, user, _ = role_client_factory("ADMIN")
    c = _cluster(admin, code="F35TM")
    _network(admin, c["id"], name="f35t-net", cidr="10.96.0.0/24")
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
                            hostname="f35t-race",
                            resource_type=BM,
                            name="f35t-eth",
                            network="f35t-net",
                            ip=ip,
                        )
                    ],
                )
            finally:
                session.close()

        return _fn

    with auth_session_factory() as session:
        before = _counts(session)
    results = _run_pair(make("10.96.0.11"), make("10.96.0.12"))
    successes = [result for result in results if isinstance(result, tuple)]
    failures = [result for result in results if isinstance(result, ImportValidationFailed)]
    assert len(successes) == 1, results
    assert len(failures) == 1, results
    assert _find_error(failures[0].details, "hostname") is not None, failures[0].details

    with auth_session_factory() as session:
        after = _counts(session)
        stored = session.execute(
            text("SELECT count(*) FROM resources WHERE hostname = 'f35t-race'")
        ).scalar_one()
    assert stored == 1
    assert after["resources"] == before["resources"] + 1
    assert after["interfaces"] == before["interfaces"] + 1
    assert after["ip_addresses"] == before["ip_addresses"] + 1
    assert after["audit_logs"] == before["audit_logs"] + 3
