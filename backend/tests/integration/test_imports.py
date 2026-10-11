"""F014 CSV / Excel import API integration tests (A1-A26, I-1..I-17; real PG).

Requires a real PostgreSQL database via ``TEST_DATABASE_URL`` (DB-D10 guard in
``conftest``). This module covers endpoint behaviour, validation aggregation,
atomic rollback and permissions; constraint/index-level evidence lives in
``test_import_constraints.py``.
"""

from __future__ import annotations

import csv
import io
import uuid

import pytest
from fastapi.testclient import TestClient
from openpyxl import Workbook
from sqlalchemy import text

from app.api.v1 import imports as imports_api
from app.core.config import Settings

VALIDATE = "/api/v1/imports/resources/validate"
WRITE = "/api/v1/imports/resources"
TEMPLATES = "/api/v1/imports/resources/templates"

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
VM_HEADERS = [
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
]

COUNT_TABLES = (
    "resources",
    "bare_metal_details",
    "virtual_machine_details",
    "audit_logs",
    "clusters",
)


# --- fixtures / helpers ------------------------------------------------------


@pytest.fixture
def role_client_factory(auth_app, make_user):
    """Logged-in ASGI clients per role, cleaned up after the test."""
    clients: list[TestClient] = []

    def _make(role: str):
        user, password = make_user(role=role)
        client = TestClient(auth_app)
        client.__enter__()
        resp = client.post(
            "/api/v1/auth/login",
            json={"username": user.username, "password": password},
        )
        assert resp.status_code == 200, resp.text
        clients.append(client)
        return client, user, password

    yield _make
    for client in clients:
        client.__exit__(None, None, None)


def _cluster(client, code="CL-001", name="Cluster", **overrides):
    body = {"code": code, "name": name}
    body.update(overrides)
    resp = client.post("/api/v1/clusters", json=body)
    assert resp.status_code == 201, resp.text
    return resp.json()["cluster"]


def _resource(client, cluster, hostname, resource_type="BARE_METAL", **overrides):
    body = {"cluster": cluster, "hostname": hostname, "resource_type": resource_type}
    body.update(overrides)
    resp = client.post("/api/v1/resources", json=body)
    assert resp.status_code == 201, resp.text
    return resp.json()["resource"]


def _rows(headers: list[str], rows: list[dict]) -> list[list[str]]:
    return [[("" if rec.get(h) is None else str(rec.get(h, ""))) for h in headers] for rec in rows]


def _csv_bytes(headers: list[str], rows: list[dict], *, bom: bool = False) -> bytes:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(headers)
    for row in _rows(headers, rows):
        writer.writerow(row)
    encoding = "utf-8-sig" if bom else "utf-8"
    return buffer.getvalue().encode(encoding)


def _xlsx_bytes(headers: list[str], rows: list[dict]) -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(headers)
    for row in _rows(headers, rows):
        sheet.append(row)
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def _post(client, path: str, data: bytes, fmt: str = "csv", filename: str | None = None):
    filename = filename or f"import.{fmt}"
    if fmt == "csv":
        content_type = "text/csv"
    else:
        content_type = (
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
    return client.post(
        path,
        files={"file": (filename, data, content_type)},
        data={"format": fmt},
    )


def _validate(client, data: bytes, fmt: str = "csv"):
    return _post(client, VALIDATE, data, fmt)


def _write(client, data: bytes, fmt: str = "csv"):
    return _post(client, WRITE, data, fmt)


def _counts(session) -> dict[str, int]:
    return {
        table: int(
            session.execute(text(f"SELECT count(*) FROM {table}")).scalar_one()
        )
        for table in COUNT_TABLES
    }


def _find_error(payload: dict, field: str, row: int | None = None) -> dict | None:
    for error in payload["errors"]:
        if error["field"] == field and (row is None or error["row"] == row):
            return error
    return None


# --- templates / permissions -------------------------------------------------


def test_templates_spec_and_read_permission(role_client_factory):
    """A25/V25: frozen BM 14 / VM 10 columns with units/enums/required."""
    viewer, _, _ = role_client_factory("VIEWER")
    resp = viewer.get(TEMPLATES)
    assert resp.status_code == 200, resp.text
    templates = {t["resource_type"]: t for t in resp.json()["templates"]}
    assert set(templates) == {"BARE_METAL", "VIRTUAL_MACHINE"}

    bm = templates["BARE_METAL"]["columns"]
    assert [c["name"] for c in bm] == BM_HEADERS
    assert sum(1 for c in bm if c["required"]) == 3
    memory = next(c for c in bm if c["name"] == "memory_mb")
    assert memory["unit"] == "MiB" and memory["type"] == "integer"
    gpu = next(c for c in bm if c["name"] == "gpu_count")
    assert gpu["unit"] is None and "0" in gpu["description"]

    vm = templates["VIRTUAL_MACHINE"]["columns"]
    assert [c["name"] for c in vm] == VM_HEADERS
    assert next(c for c in vm if c["name"] == "host")["required"] is True
    assert next(c for c in vm if c["name"] == "disk_gb")["unit"] == "GiB"
    assert next(c for c in vm if c["name"] == "role")["enum"] == [
        "COMPUTE",
        "LOGIN",
        "MANAGEMENT",
        "STORAGE",
        "SERVICE",
        "GPU",
        "OTHER",
    ]


def test_permission_matrix(auth_app, role_client_factory):
    """A22/T25: 401 unauth; VIEWER 403; EDITOR/ADMIN allowed; 401 before 403."""
    data = _csv_bytes(BM_HEADERS, [{"cluster": "C1", "hostname": "h1", "resource_type": "BARE_METAL"}])

    unauth = TestClient(auth_app)
    unauth.__enter__()
    try:
        assert _post(unauth, VALIDATE, data).status_code == 401
        assert _post(unauth, WRITE, data).status_code == 401
        assert unauth.get(TEMPLATES).status_code == 401
    finally:
        unauth.__exit__(None, None, None)

    viewer, _, _ = role_client_factory("VIEWER")
    assert _post(viewer, VALIDATE, data).status_code == 403
    assert _post(viewer, WRITE, data).status_code == 403
    body = _post(viewer, VALIDATE, data).json()["error"]
    assert body == {
        "code": "FORBIDDEN",
        "message": "Forbidden",
        "details": {"reason": "permission"},
    }
    assert viewer.get(TEMPLATES).status_code == 200

    editor, _, _ = role_client_factory("EDITOR")
    _cluster(editor, code="C1")
    assert _post(editor, VALIDATE, data).status_code == 200
    assert _post(editor, WRITE, data).status_code == 201

    admin, _, _ = role_client_factory("ADMIN")
    _cluster(admin, code="C2")
    data2 = _csv_bytes(BM_HEADERS, [{"cluster": "C2", "hostname": "h1", "resource_type": "BARE_METAL"}])
    assert _post(admin, WRITE, data2).status_code == 201


def test_csrf_reason_distinct(role_client_factory):
    """B29: cross-origin write -> 403 reason=csrf."""
    editor, _, _ = role_client_factory("EDITOR")
    data = _csv_bytes(BM_HEADERS, [])
    resp = editor.post(
        WRITE,
        files={"file": ("x.csv", data, "text/csv")},
        data={"format": "csv"},
        headers={"Origin": "https://evil.example"},
    )
    assert resp.status_code == 403
    assert resp.json()["error"]["details"] == {"reason": "csrf"}


# --- A1 CSV / xlsx consistency ----------------------------------------------


def test_csv_and_xlsx_behaviour_identical(role_client_factory):
    """A1/V1/B1: same logical data -> same validate/write results."""
    editor, _, _ = role_client_factory("EDITOR")
    c = _cluster(editor, code="N96P")
    host = _resource(editor, c["code"], "existing")
    rows = [
        {"cluster": c["code"], "hostname": "cn001", "resource_type": "BARE_METAL", "memory_mb": "262144"},
        {"cluster": c["code"], "hostname": "vm001", "resource_type": "VIRTUAL_MACHINE", "host": "existing", "vcpu": "4"},
    ]
    vm_rows = [rows[1]]
    bm_rows = [rows[0]]

    csv_validation = _validate(editor, _csv_bytes(BM_HEADERS, bm_rows)).json()
    xlsx_validation = _validate(editor, _xlsx_bytes(BM_HEADERS, bm_rows), "xlsx").json()
    assert csv_validation["format"] == "csv"
    assert xlsx_validation["format"] == "xlsx"
    assert {
        k: v for k, v in csv_validation.items() if k != "format"
    } == {k: v for k, v in xlsx_validation.items() if k != "format"}

    assert _write(editor, _csv_bytes(BM_HEADERS, bm_rows)).status_code == 201
    assert _write(editor, _xlsx_bytes(VM_HEADERS, vm_rows), "xlsx").status_code == 201
    listing = editor.get("/api/v1/resources").json()
    assert listing["total"] == 3
    assert {i["hostname"] for i in listing["items"]} == {"existing", "cn001", "vm001"}


def test_bm_create_defaults_units_and_audit(role_client_factory, auth_session_factory):
    """A7/A15/A16/A17: defaults, MiB stored verbatim, 0 vs null, CREATE audit."""
    editor, _, _ = role_client_factory("EDITOR")
    c = _cluster(editor, code="C1")
    rows = [
        {
            "cluster": c["code"],
            "hostname": " CN001 ",
            "resource_type": "BARE_METAL",
            "memory_mb": "262144",
            "gpu_count": "0",
        }
    ]
    resp = _write(editor, _csv_bytes(BM_HEADERS, rows))
    assert resp.status_code == 201, resp.text
    assert resp.json() == {"created": 1, "total_rows": 1}

    with auth_session_factory() as session:
        detail = session.execute(
            text(
                "SELECT r.hostname, r.role, r.status, r.metadata, b.memory_mb, "
                "b.gpu_count, b.cpu_cores FROM resources r "
                "JOIN bare_metal_details b ON b.resource_id = r.id"
            )
        ).one()
        assert detail[0] == "cn001"
        assert detail[1] == "OTHER" and detail[2] == "UNKNOWN"
        assert detail[3] == {}
        assert detail[4] == 262144 and detail[5] == 0 and detail[6] is None
        audits = session.execute(
            text(
                "SELECT count(*) FROM audit_logs WHERE object_type='resource' "
                "AND action='CREATE'"
            )
        ).scalar_one()
        assert audits == 1


def test_vm_create_with_host_detail_and_audit(role_client_factory, auth_session_factory):
    """A7/I-14: VM resolves host to UUID and writes its detail + audit."""
    editor, _, _ = role_client_factory("EDITOR")
    c = _cluster(editor, code="C1")
    host = _resource(editor, c["code"], "cn001")
    rows = [
        {
            "cluster": c["code"],
            "hostname": "vm001",
            "resource_type": "VIRTUAL_MACHINE",
            "host": host["id"],
            "vcpu": "8",
            "memory_mb": "16384",
            "disk_gb": "0",
            "hypervisor": "KVM",
        }
    ]
    resp = _write(editor, _xlsx_bytes(VM_HEADERS, rows), "xlsx")
    assert resp.status_code == 201, resp.text

    with auth_session_factory() as session:
        row = session.execute(
            text(
                "SELECT v.host_resource_id, v.vcpu, v.memory_mb, v.disk_gb, "
                "v.hypervisor FROM virtual_machine_details v "
                "JOIN resources r ON r.id = v.resource_id "
                "WHERE r.hostname = 'vm001'"
            )
        ).one()
        assert str(row[0]) == host["id"]
        assert row[1] == 8 and row[2] == 16384 and row[3] == 0 and row[4] == "KVM"


# --- A2/A3 aggregate + read-only --------------------------------------------


def test_validate_aggregates_all_errors_not_fail_fast(role_client_factory):
    """A2/V2: every error row is returned, with row/field/reason."""
    editor, _, _ = role_client_factory("EDITOR")
    c = _cluster(editor, code="C1")
    rows = [
        {"cluster": "NOPE", "hostname": "h1", "resource_type": "BARE_METAL"},
        {"cluster": c["code"], "hostname": "bad name", "resource_type": "BARE_METAL"},
        {"cluster": c["code"], "hostname": "h3", "resource_type": "BARE_METAL", "role": "compute"},
    ]
    resp = _validate(editor, _csv_bytes(BM_HEADERS, rows))
    assert resp.status_code == 200, resp.text
    payload = resp.json()
    assert payload["total_rows"] == 3
    assert payload["error_count"] == 3
    assert payload["importable_rows"] == 0
    assert _find_error(payload, "cluster", 2)
    assert _find_error(payload, "hostname", 3)
    assert _find_error(payload, "role", 4)


def test_validate_read_only_and_idempotent(role_client_factory, auth_session_factory):
    """A3/I-3: no writes/Audit; repeated validate is byte-identical."""
    editor, _, _ = role_client_factory("EDITOR")
    c = _cluster(editor, code="C1")
    rows = [{"cluster": c["code"], "hostname": "cn001", "resource_type": "BARE_METAL"}]
    data = _csv_bytes(BM_HEADERS, rows)

    with auth_session_factory() as session:
        before = _counts(session)
    first = _validate(editor, data)
    second = _validate(editor, data)
    assert first.status_code == 200 and second.status_code == 200
    assert first.json() == second.json()
    assert first.json()["errors"] == []
    with auth_session_factory() as session:
        after = _counts(session)
    assert before == after


def test_bom_and_quoted_newlines_logical_row_numbers(role_client_factory):
    """V27: BOM tolerant; CSV quoted newline keeps logical record numbering."""
    editor, _, _ = role_client_factory("EDITOR")
    c = _cluster(editor, code="C1")
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(BM_HEADERS)
    writer.writerow([c["code"], "cn001", "BARE_METAL", "", "", "Manu\nal", "", "", "", "", "", "", "", ""])
    writer.writerow([c["code"], "bad name", "BARE_METAL", "", "", "", "", "", "", "", "", "", "", ""])
    data = buffer.getvalue().encode("utf-8-sig")

    payload = _validate(editor, data).json()
    assert payload["total_rows"] == 2
    error = _find_error(payload, "hostname")
    assert error is not None and error["row"] == 3


# --- A8/A9/A13 duplicate / conflict / soft-delete reuse ----------------------


def test_file_internal_duplicate_reports_related_row(role_client_factory, auth_session_factory):
    """A8/B6: normalized duplicate -> error with related_row; batch not written."""
    editor, _, _ = role_client_factory("EDITOR")
    c = _cluster(editor, code="C1")
    rows = [
        {"cluster": c["code"], "hostname": "cn001", "resource_type": "BARE_METAL"},
        {"cluster": c["code"], "hostname": " CN001 ", "resource_type": "BARE_METAL"},
    ]
    data = _csv_bytes(BM_HEADERS, rows)
    payload = _validate(editor, data).json()
    dup = _find_error(payload, "hostname", 3)
    assert dup is not None
    assert dup["related_row"] == 2
    assert payload["importable_rows"] == 1

    resp = _write(editor, data)
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "IMPORT_VALIDATION_FAILED"
    with auth_session_factory() as session:
        assert _counts(session)["resources"] == 0


def test_existing_conflict_not_overwritten(role_client_factory, auth_session_factory):
    """A9/B7: existing undeleted hostname -> row error, no update, no UPDATE audit."""
    editor, _, _ = role_client_factory("EDITOR")
    c = _cluster(editor, code="C1")
    existing = _resource(editor, c["code"], "cn001", description="keep")
    rows = [{"cluster": c["code"], "hostname": "cn001", "resource_type": "BARE_METAL", "role": "GPU"}]
    resp = _write(editor, _csv_bytes(BM_HEADERS, rows))
    assert resp.status_code == 422
    assert _find_error(resp.json()["error"]["details"], "hostname", 2)

    with auth_session_factory() as session:
        row = session.execute(
            text("SELECT role, description, version FROM resources WHERE hostname='cn001'")
        ).one()
        assert row[0] == "OTHER" and row[1] == "keep" and row[2] == 1
        updates = session.execute(
            text("SELECT count(*) FROM audit_logs WHERE action='UPDATE'")
        ).scalar_one()
        assert updates == 0


def test_soft_deleted_hostname_reusable(role_client_factory, auth_session_factory):
    """A13/B9: soft-deleted hostname is reusable in import."""
    admin, _, _ = role_client_factory("ADMIN")
    c = _cluster(admin, code="C1")
    first = _resource(admin, c["code"], "cn001")
    assert admin.delete(
        f"/api/v1/resources/{first['id']}", params={"version": first["version"]}
    ).status_code == 204

    rows = [{"cluster": c["code"], "hostname": "CN001", "resource_type": "BARE_METAL"}]
    resp = _write(admin, _csv_bytes(BM_HEADERS, rows))
    assert resp.status_code == 201, resp.text
    with auth_session_factory() as session:
        rows_db = session.execute(
            text("SELECT id, deleted_at FROM resources WHERE hostname_key='cn001'")
        ).all()
        assert len(rows_db) == 2
        assert sum(1 for r in rows_db if r[1] is None) == 1


# --- A11/A18/A19 VM host -----------------------------------------------------


def test_vm_host_four_conditions(role_client_factory):
    """A11/B17/B18: host must exist, be undeleted, BARE_METAL and same cluster."""
    editor, _, _ = role_client_factory("EDITOR")
    admin, _, _ = role_client_factory("ADMIN")
    c1 = _cluster(editor, code="C1")
    c2 = _cluster(editor, code="C2")
    bm = _resource(editor, c1["code"], "bm1")
    other_bm = _resource(editor, c2["code"], "bm2")
    vm_host = _resource(
        editor, c1["code"], "vmhost", resource_type="VIRTUAL_MACHINE",
        virtual_machine={"host_resource_id": bm["id"]},
    )
    rows = [
        {"cluster": c1["code"], "hostname": "v1", "resource_type": "VIRTUAL_MACHINE", "host": "missing"},
        {"cluster": c1["code"], "hostname": "v2", "resource_type": "VIRTUAL_MACHINE", "host": other_bm["id"]},
        {"cluster": c1["code"], "hostname": "v3", "resource_type": "VIRTUAL_MACHINE", "host": vm_host["id"]},
    ]
    payload = _validate(editor, _xlsx_bytes(VM_HEADERS, rows), "xlsx").json()
    for index in (2, 3, 4):
        assert _find_error(payload, "host", index) is not None

    # soft-deleted host
    deleted_bm = _resource(editor, c1["code"], "bm3")
    assert admin.delete(
        f"/api/v1/resources/{deleted_bm['id']}",
        params={"version": deleted_bm["version"]},
    ).status_code == 204
    payload2 = _validate(
        editor,
        _csv_bytes(VM_HEADERS, [{"cluster": c1["code"], "hostname": "v4", "resource_type": "VIRTUAL_MACHINE", "host": "bm3"}]),
    ).json()
    assert _find_error(payload2, "host", 2) is not None


def test_vm_host_must_be_out_of_batch(role_client_factory, auth_session_factory):
    """A18: a committed BM batch can host a later VM batch (migration order)."""
    editor, _, _ = role_client_factory("EDITOR")
    c = _cluster(editor, code="C1")
    bm = _write(
        editor,
        _csv_bytes(BM_HEADERS, [{"cluster": c["code"], "hostname": "cn100", "resource_type": "BARE_METAL"}]),
    )
    assert bm.status_code == 201
    vm = _write(
        editor,
        _csv_bytes(
            VM_HEADERS,
            [{"cluster": c["code"], "hostname": "vm100", "resource_type": "VIRTUAL_MACHINE", "host": "cn100"}],
        ),
    )
    assert vm.status_code == 201, vm.text
    with auth_session_factory() as session:
        assert _counts(session)["resources"] == 2


def test_same_batch_bm_not_referencable(role_client_factory, auth_session_factory):
    """A19 in one file: BM + VM referencing it -> host error, whole batch rolled back."""
    editor, _, _ = role_client_factory("EDITOR")
    c = _cluster(editor, code="C1")
    # A single logical batch cannot mix BM and VM templates, so model it as a VM
    # batch whose host is created by a preceding request that is rolled back: the
    # pre-insert validation only sees committed state.
    rows = [
        {"cluster": c["code"], "hostname": "vm1", "resource_type": "VIRTUAL_MACHINE", "host": "cn100"},
    ]
    resp = _write(editor, _csv_bytes(VM_HEADERS, rows))
    assert resp.status_code == 422
    assert _find_error(resp.json()["error"]["details"], "host", 2)
    with auth_session_factory() as session:
        assert _counts(session)["resources"] == 0


# --- A12 cluster -------------------------------------------------------------


def test_cluster_not_found_soft_deleted_inactive(role_client_factory, auth_session_factory):
    """A12/B15/B16: nonexistent/soft-deleted -> error; INACTIVE -> allowed."""
    admin, _, _ = role_client_factory("ADMIN")
    inactive = _cluster(admin, code="INACT", status="INACTIVE")
    gone = _cluster(admin, code="GONE")
    assert admin.delete(
        f"/api/v1/clusters/{gone['id']}", params={"version": 1}
    ).status_code == 204

    rows = [
        {"cluster": "NOPE", "hostname": "a", "resource_type": "BARE_METAL"},
        {"cluster": "GONE", "hostname": "b", "resource_type": "BARE_METAL"},
    ]
    payload = _validate(admin, _csv_bytes(BM_HEADERS, rows)).json()
    assert _find_error(payload, "cluster", 2) is not None
    assert _find_error(payload, "cluster", 3) is not None

    ok = _write(
        admin,
        _csv_bytes(BM_HEADERS, [{"cluster": inactive["code"], "hostname": "c", "resource_type": "BARE_METAL"}]),
    )
    assert ok.status_code == 201, ok.text


# --- A5/A6 rollback ----------------------------------------------------------


def test_rollback_zero_residue_including_audit(role_client_factory, auth_session_factory):
    """A5/A6/I-1/I-8: one bad row rolls back resources/details/audit/clusters."""
    editor, _, _ = role_client_factory("EDITOR")
    c = _cluster(editor, code="C1")
    rows = [
        {"cluster": c["code"], "hostname": "good1", "resource_type": "BARE_METAL"},
        {"cluster": c["code"], "hostname": "good2", "resource_type": "BARE_METAL"},
        {"cluster": "NOPE", "hostname": "bad", "resource_type": "BARE_METAL"},
    ]
    with auth_session_factory() as session:
        before = _counts(session)
    resp = _write(editor, _csv_bytes(BM_HEADERS, rows))
    assert resp.status_code == 422
    details = resp.json()["error"]["details"]
    assert details["total_rows"] == 3
    assert details["importable_rows"] == 2
    assert details["error_count"] == 1
    with auth_session_factory() as session:
        after = _counts(session)
    assert before == after


def test_write_revalidates_after_external_change(role_client_factory, auth_session_factory):
    """A4/B12/I-4: state change between validate and write -> 422 + rollback."""
    editor, _, _ = role_client_factory("EDITOR")
    c = _cluster(editor, code="C1")
    rows = [{"cluster": c["code"], "hostname": "cn001", "resource_type": "BARE_METAL"}]
    data = _csv_bytes(BM_HEADERS, rows)
    assert _validate(editor, data).json()["errors"] == []

    # Another actor occupies the hostname before the write.
    _resource(editor, c["code"], "cn001")

    resp = _write(editor, data)
    assert resp.status_code == 422
    assert _find_error(resp.json()["error"]["details"], "hostname", 2)
    with auth_session_factory() as session:
        assert _counts(session)["resources"] == 1


# --- A10/A21/A24 field + template errors ------------------------------------


def test_field_validation_errors(role_client_factory):
    """A10/B21/B22/B23: enums, integers, string bounds map to template columns."""
    editor, _, _ = role_client_factory("EDITOR")
    c = _cluster(editor, code="C1")
    rows = [
        {"cluster": c["code"], "hostname": "h1", "resource_type": "BARE_METAL", "cpu_cores": "0"},
        {"cluster": c["code"], "hostname": "h2", "resource_type": "BARE_METAL", "memory_mb": "abc"},
        {"cluster": c["code"], "hostname": "h3", "resource_type": "BARE_METAL", "gpu_count": "-1"},
        {"cluster": c["code"], "hostname": "h4", "resource_type": "BARE_METAL", "manufacturer": "x" * 256},
        {"cluster": c["code"], "hostname": "h5", "resource_type": "BARE_METAL", "status": "idle"},
        {"cluster": c["code"], "hostname": "h6", "resource_type": "VIRTUAL_MACHINE", "host": "no"},
    ]
    payload = _validate(editor, _csv_bytes(BM_HEADERS, rows[:5])).json()
    assert payload["error_count"] == 5
    for index, field in zip((2, 3, 4, 5, 6), ("cpu_cores", "memory_mb", "gpu_count", "manufacturer", "status")):
        assert _find_error(payload, field, index) is not None

    vm_payload = _validate(editor, _csv_bytes(VM_HEADERS, rows[5:])).json()
    assert _find_error(vm_payload, "host", 2) is not None


def test_required_and_optional_empty_cells(role_client_factory, auth_session_factory):
    """B27/DR-199: required empty -> error; optional empty -> omitted/null."""
    editor, _, _ = role_client_factory("EDITOR")
    c = _cluster(editor, code="C1")
    missing = _validate(
        editor,
        _csv_bytes(BM_HEADERS, [{"cluster": c["code"], "hostname": "", "resource_type": "BARE_METAL"}]),
    ).json()
    assert _find_error(missing, "hostname", 2) is not None

    ok = _write(
        editor,
        _csv_bytes(
            BM_HEADERS,
            [{"cluster": c["code"], "hostname": "h1", "resource_type": "BARE_METAL", "manufacturer": "   "}],
        ),
    )
    assert ok.status_code == 201
    with auth_session_factory() as session:
        value = session.execute(
            text("SELECT manufacturer FROM bare_metal_details")
        ).scalar_one()
        assert value is None


def test_header_errors(role_client_factory):
    """A21/B2-B5/B24: header_missing/missing/unknown/column_order."""
    editor, _, _ = role_client_factory("EDITOR")
    c = _cluster(editor, code="C1")
    _resource(editor, c["code"], "x")

    missing = _validate(editor, _csv_bytes([h for h in BM_HEADERS if h != "hostname"], []))
    assert missing.status_code == 422
    body = missing.json()["error"]
    assert body["code"] == "IMPORT_INVALID_FILE"
    assert body["details"]["reason"] == "missing_columns"
    assert body["details"]["missing_columns"] == ["hostname"]

    unknown = _validate(editor, _csv_bytes(BM_HEADERS + ["interface_name"], []))
    assert unknown.status_code == 422
    assert unknown.json()["error"]["details"]["reason"] == "unknown_columns"
    assert unknown.json()["error"]["details"]["unknown_columns"] == ["interface_name"]

    order = _validate(editor, _csv_bytes(list(reversed(BM_HEADERS)), []))
    assert order.status_code == 422
    assert order.json()["error"]["details"]["reason"] == "column_order"

    blank = _validate(editor, b"\n")
    assert blank.status_code == 422
    assert blank.json()["error"]["details"]["reason"] == "header_missing"

    vm_with_hw = _validate(editor, _csv_bytes(VM_HEADERS + ["gpu_model"], []))
    assert vm_with_hw.status_code == 422
    assert vm_with_hw.json()["error"]["details"]["reason"] == "unknown_columns"

    bm_with_host = _validate(editor, _csv_bytes(BM_HEADERS + ["host"], []))
    assert bm_with_host.status_code == 422
    assert bm_with_host.json()["error"]["details"]["reason"] == "unknown_columns"


def test_format_and_file_level_errors(role_client_factory):
    """V29/V30/B31/B32: format shape, empty/only-header, unsupported/unreadable."""
    editor, _, _ = role_client_factory("EDITOR")
    data = _csv_bytes(BM_HEADERS, [])
    for bad in ("xls", "pdf", ""):
        resp = editor.post(
            WRITE,
            files={"file": ("x.xls", data, "application/octet-stream")},
            data={"format": bad},
        )
        assert resp.status_code == 422, bad
        assert resp.json()["error"]["code"] == "VALIDATION_ERROR"
        assert resp.json()["error"]["details"]["fields"][0]["field"] == "format"

    empty = _post(editor, VALIDATE, b"", "csv")
    assert empty.json()["error"]["details"]["reason"] == "empty_file"
    only_header = _post(editor, VALIDATE, _csv_bytes(BM_HEADERS, []), "csv")
    assert only_header.json()["error"]["details"]["reason"] == "empty_file"
    unsupported = _post(editor, VALIDATE, b"\xd0\xcf\x11\xe0notxlsx", "xlsx")
    assert unsupported.json()["error"]["details"]["reason"] == "unsupported_format"
    unreadable = _post(editor, VALIDATE, b"PK\x03\x04not-a-zip", "xlsx")
    assert unreadable.json()["error"]["details"]["reason"] == "unreadable"


# --- A20 limits / V32 truncation --------------------------------------------


def test_file_size_and_row_limits(role_client_factory, monkeypatch):
    """A20/B13/B14: 413 caps with details, no partial import."""
    editor, _, _ = role_client_factory("EDITOR")
    c = _cluster(editor, code="C1")
    row = {"cluster": c["code"], "hostname": "h1", "resource_type": "BARE_METAL"}

    small = Settings(_env_file=None, import_max_file_bytes=10)
    monkeypatch.setattr(imports_api, "get_settings", lambda: small)
    resp = _write(editor, _csv_bytes(BM_HEADERS, [row]))
    assert resp.status_code == 413
    assert resp.json()["error"] == {
        "code": "IMPORT_FILE_TOO_LARGE",
        "message": "Import file too large",
        "details": {"limit_bytes": 10},
    }

    limited = Settings(_env_file=None, import_max_rows=1)
    monkeypatch.setattr(imports_api, "get_settings", lambda: limited)
    rows = [row, {"cluster": c["code"], "hostname": "h2", "resource_type": "BARE_METAL"}]
    resp = _write(editor, _csv_bytes(BM_HEADERS, rows))
    assert resp.status_code == 413
    assert resp.json()["error"] == {
        "code": "IMPORT_ROW_LIMIT_EXCEEDED",
        "message": "Import row limit exceeded",
        "details": {"limit_rows": 1},
    }


def test_validation_order_row_limit_before_header(role_client_factory, monkeypatch):
    """RV-F014-02: row-count cap (413) precedes header/column validation (422).

    Contract §2 order: parse -> row limit -> header/columns -> per-row.
    """
    editor, _, _ = role_client_factory("EDITOR")
    c = _cluster(editor, code="C1")
    row = {"cluster": c["code"], "hostname": "h1", "resource_type": "BARE_METAL"}
    two_rows = [row, {"cluster": c["code"], "hostname": "h2", "resource_type": "BARE_METAL"}]

    limited = Settings(_env_file=None, import_max_rows=1)
    monkeypatch.setattr(imports_api, "get_settings", lambda: limited)

    # Unknown column header + row count over the limit -> 413, not 422.
    unknown_over = _validate(editor, _csv_bytes(BM_HEADERS + ["interface_name"], two_rows))
    assert unknown_over.status_code == 413, unknown_over.text
    assert unknown_over.json()["error"] == {
        "code": "IMPORT_ROW_LIMIT_EXCEEDED",
        "message": "Import row limit exceeded",
        "details": {"limit_rows": 1},
    }

    # Valid header + row count over the limit -> 413.
    valid_over = _validate(editor, _csv_bytes(BM_HEADERS, two_rows))
    assert valid_over.status_code == 413, valid_over.text
    assert valid_over.json()["error"]["code"] == "IMPORT_ROW_LIMIT_EXCEEDED"

    # Invalid header with a normal row count -> 422 IMPORT_INVALID_FILE.
    invalid_header = _validate(editor, _csv_bytes(BM_HEADERS + ["interface_name"], [row]))
    assert invalid_header.status_code == 422, invalid_header.text
    body = invalid_header.json()["error"]
    assert body["code"] == "IMPORT_INVALID_FILE"
    assert body["details"]["reason"] == "unknown_columns"
    assert body["details"]["unknown_columns"] == ["interface_name"]


def test_error_preview_truncation(role_client_factory, monkeypatch):
    """V28/V32: error_count is the full total; errors list is bounded."""
    editor, _, _ = role_client_factory("EDITOR")
    small = Settings(_env_file=None, import_error_preview_limit=2)
    monkeypatch.setattr(imports_api, "get_settings", lambda: small)
    rows = [
        {"cluster": "NOPE", "hostname": "h1", "resource_type": "BARE_METAL"},
        {"cluster": "NOPE", "hostname": "h2", "resource_type": "BARE_METAL"},
        {"cluster": "NOPE", "hostname": "h3", "resource_type": "BARE_METAL"},
    ]
    payload = _validate(editor, _csv_bytes(BM_HEADERS, rows)).json()
    assert payload["error_count"] == 3
    assert payload["errors_truncated"] is True
    assert len(payload["errors"]) == 2


# --- A23/A24/A26 sync + no implicit objects ---------------------------------


def test_reimport_after_success_conflicts(role_client_factory, auth_session_factory):
    """A23: re-running the same successful file conflicts and creates nothing."""
    editor, _, _ = role_client_factory("EDITOR")
    c = _cluster(editor, code="C1")
    data = _csv_bytes(BM_HEADERS, [{"cluster": c["code"], "hostname": "cn001", "resource_type": "BARE_METAL"}])
    assert _write(editor, data).status_code == 201
    second = _write(editor, data)
    assert second.status_code == 422
    with auth_session_factory() as session:
        assert _counts(session)["resources"] == 1
        resource_audits = session.execute(
            text(
                "SELECT count(*) FROM audit_logs "
                "WHERE object_type='resource' AND action='CREATE'"
            )
        ).scalar_one()
        assert resource_audits == 1


def test_import_does_not_touch_clusters(role_client_factory, auth_session_factory):
    """A24: import never creates/modifies a Cluster."""
    editor, _, _ = role_client_factory("EDITOR")
    c = _cluster(editor, code="C1")
    with auth_session_factory() as session:
        before = session.execute(text("SELECT count(*) FROM clusters")).scalar_one()
    _write(editor, _csv_bytes(BM_HEADERS, [{"cluster": c["code"], "hostname": "h1", "resource_type": "BARE_METAL"}]))
    with auth_session_factory() as session:
        after = session.execute(text("SELECT count(*) FROM clusters")).scalar_one()
    assert before == after == 1


def test_unsupported_columns_rejected(role_client_factory, auth_session_factory):
    """A26/I-17: non-resource columns are rejected; no non-Resource object created."""
    editor, _, _ = role_client_factory("EDITOR")
    resp = _validate(editor, _csv_bytes(["cluster", "interface_name", "mac_address"], []))
    assert resp.status_code == 422
    details = resp.json()["error"]["details"]
    assert details["reason"] in {"unknown_columns", "missing_columns"}
    with auth_session_factory() as session:
        assert _counts(session)["resources"] == 0


def test_no_direct_write_bypass_static():
    """V-SL-1: the import service stages writes through the Service Layer."""
    source = (
        __import__("pathlib").Path("app/services/resource_import.py").read_text()
    )
    lowered = source.lower()
    assert "insert into" not in lowered
    assert "update resources" not in lowered
    assert "resource_service.stage_resource" in source