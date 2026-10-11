"""F014 independent acceptance checks (Tester TE-1, real PG / real app).

These complement the developer integration tests with checks the Tester ran
independently to close specific acceptance items (A1/A14/A19/A20/A21/A22/A26 and
the contract's format/path/numeric boundary clauses). They deliberately avoid
re-asserting the developer's cases and target gaps:

* ``format`` is case-insensitive and shape errors use ``VALIDATION_ERROR``;
* unknown path/method return 404/405;
* numeric boundaries (negative / fractional) map to the template column;
* Activity is observable after a successful batch and absent after a rollback;
* CSV/xlsx pre-validate is identical for VM data (developer covered BM only);
* a mixed BM+VM header is rejected, which is why the A19 "same-batch BM" file
  is structurally impossible under the frozen single-template contract;
* the import service contains no direct write SQL (V-SL-1).
"""

from __future__ import annotations

import csv
import io
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.core.config import Settings
from app.services import cluster as cluster_service
from app.services import resource_import

VALIDATE = "/api/v1/imports/resources/validate"
WRITE = "/api/v1/imports/resources"
TEMPLATES = "/api/v1/imports/resources/templates"

BM_HEADERS = [
    "cluster", "hostname", "resource_type", "role", "status", "manufacturer",
    "model", "serial_number", "cpu_model", "cpu_sockets", "cpu_cores",
    "memory_mb", "gpu_model", "gpu_count",
]
VM_HEADERS = [
    "cluster", "hostname", "resource_type", "role", "status", "host", "vcpu",
    "memory_mb", "disk_gb", "hypervisor",
]


@pytest.fixture
def role_client_factory(auth_app, make_user):
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
        return client

    yield _make
    for client in clients:
        client.__exit__(None, None, None)


def _csv_bytes(headers, rows):
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(headers)
    for row in rows:
        writer.writerow([("" if v is None else str(v)) for v in row])
    return buffer.getvalue().encode("utf-8")


def _post(client, path, data, fmt="csv"):
    return client.post(
        path,
        files={"file": (f"x.{fmt}", data, "application/octet-stream")},
        data={"format": fmt},
    )


def _bm(cluster, hostname, **extra):
    row = {"cluster": cluster, "hostname": hostname, "resource_type": "BARE_METAL"}
    row.update(extra)
    return [row.get(h, "") for h in BM_HEADERS]


def _cluster(client, code="C1"):
    return client.post("/api/v1/clusters", json={"code": code, "name": code}).json()[
        "cluster"
    ]


def test_format_case_insensitive_and_shape(role_client_factory):
    """Contract §2: format is case-insensitive; bad shape -> VALIDATION_ERROR."""
    editor = role_client_factory("EDITOR")
    c = _cluster(editor)
    data = _csv_bytes(BM_HEADERS, [_bm(c["code"], "h1")])

    for value in ("CSV", "csv", "CsV"):
        resp = _post(editor, VALIDATE, data, value)
        assert resp.status_code == 200, (value, resp.text)
        assert resp.json()["format"] == "csv"

    bad = editor.post(
        WRITE, files={"file": ("x.xls", data, "application/octet-stream")}, data={"format": "xls"}
    )
    assert bad.status_code == 422
    assert bad.json()["error"]["code"] == "VALIDATION_ERROR"
    assert bad.json()["error"]["details"]["fields"][0]["field"] == "format"


def test_unknown_path_and_method(role_client_factory):
    """Contract §9: undefined paths 404; wrong method on a known path 405."""
    editor = role_client_factory("EDITOR")
    assert editor.get("/api/v1/imports/nope").status_code == 404
    assert editor.get(VALIDATE).status_code == 405
    assert editor.get(WRITE).status_code == 405
    assert editor.post(TEMPLATES).status_code == 405


def test_numeric_boundaries_map_to_template_columns(role_client_factory):
    """A10/A17/B26: negative/fractional values rejected on the exact column."""
    editor = role_client_factory("EDITOR")
    c = _cluster(editor)
    rows = [
        _bm(c["code"], "h1", cpu_cores="-4"),
        _bm(c["code"], "h2", memory_mb="-5"),
        _bm(c["code"], "h3", cpu_sockets="2.5"),
    ]
    payload = _post(editor, VALIDATE, _csv_bytes(BM_HEADERS, rows)).json()
    assert payload["error_count"] == 3
    for index, field in zip((2, 3, 4), ("cpu_cores", "memory_mb", "cpu_sockets")):
        assert any(
            e["field"] == field and e["row"] == index for e in payload["errors"]
        ), payload["errors"]

    # disk_gb=0 is explicitly "none" and accepted; negative rejected.
    host = editor.post(
        "/api/v1/resources",
        json={"cluster": c["code"], "hostname": "host1", "resource_type": "BARE_METAL"},
    ).json()["resource"]
    ok = _post(
        editor,
        VALIDATE,
        _csv_bytes(
            VM_HEADERS,
            [[c["code"], "v1", "VIRTUAL_MACHINE", "", "", "host1", "", "", "0", ""]],
        ),
    ).json()
    assert ok["error_count"] == 0, ok
    bad = _post(
        editor,
        VALIDATE,
        _csv_bytes(
            VM_HEADERS,
            [[c["code"], "v2", "VIRTUAL_MACHINE", "", "", "host1", "", "", "-1", ""]],
        ),
    ).json()
    assert any(e["field"] == "disk_gb" and e["row"] == 2 for e in bad["errors"]), bad


def test_activity_after_success_and_absent_after_rollback(role_client_factory):
    """A6/A7: successful batch visible in Activity; rolled-back batch invisible."""
    editor = role_client_factory("EDITOR")
    c = _cluster(editor)

    good = _csv_bytes(BM_HEADERS, [_bm(c["code"], "keepme")])
    assert _post(editor, WRITE, good).status_code == 201
    listing = editor.get("/api/v1/resources", params={"q": "keepme"}).json()
    assert listing["total"] == 1
    resource_id = listing["items"][0]["id"]
    activity = editor.get(f"/api/v1/resources/{resource_id}/activity").json()
    assert activity["total"] >= 1
    assert any(item["action"] == "CREATE" for item in activity["items"])

    # A mixed batch with one valid row must leave no trace for that row.
    mixed = _csv_bytes(BM_HEADERS, [_bm(c["code"], "ghostrow"), _bm("MISSING", "badrow")])
    assert _post(editor, WRITE, mixed).status_code == 422
    assert editor.get("/api/v1/resources", params={"q": "ghostrow"}).json()["total"] == 0


def test_csv_xlsx_vm_validate_identical(role_client_factory):
    """A1/V1: CSV and xlsx give the same pre-validate result for VM data."""
    from openpyxl import Workbook

    editor = role_client_factory("EDITOR")
    c = _cluster(editor)
    editor.post(
        "/api/v1/resources",
        json={"cluster": c["code"], "hostname": "host9", "resource_type": "BARE_METAL"},
    )
    rows = [
        [c["code"], "v1", "VIRTUAL_MACHINE", "", "", "host9", "4", "8192", "100", "KVM"],
        [c["code"], "v2", "VIRTUAL_MACHINE", "", "", "nope", "4", "", "", ""],
    ]
    csv_payload = _post(editor, VALIDATE, _csv_bytes(VM_HEADERS, rows)).json()

    workbook = Workbook()
    sheet = workbook.active
    sheet.append(VM_HEADERS)
    for row in rows:
        sheet.append(row)
    buffer = io.BytesIO()
    workbook.save(buffer)
    xlsx_payload = _post(editor, VALIDATE, buffer.getvalue(), "xlsx").json()

    assert csv_payload["format"] == "csv" and xlsx_payload["format"] == "xlsx"
    assert {k: v for k, v in csv_payload.items() if k != "format"} == {
        k: v for k, v in xlsx_payload.items() if k != "format"
    }


def test_mixed_role_template_header_rejected(role_client_factory):
    """A19 context: a batch file is homogeneous, so BM+VM cannot share a batch."""
    editor = role_client_factory("EDITOR")
    mixed = ["cluster", "hostname", "resource_type", "role", "status", "host",
             "manufacturer", "vcpu", "memory_mb", "disk_gb", "hypervisor",
             "cpu_model", "serial_number", "cpu_sockets", "cpu_cores", "gpu_model",
             "gpu_count"]
    resp = _post(editor, VALIDATE, _csv_bytes(mixed, []))
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "IMPORT_INVALID_FILE"
    assert resp.json()["error"]["details"]["reason"] in {
        "unknown_columns",
        "missing_columns",
        "column_order",
    }


def test_import_service_has_no_direct_write_sql():
    """V-SL-1/A14: the import service stages writes via the Service Layer."""
    source = Path("app/services/resource_import.py").read_text()
    lowered = source.lower()
    for forbidden in ("insert into", "update resources", "delete from"):
        assert forbidden not in lowered, forbidden
    assert "resource_service.stage_resource" in source
    # Parsing/validation must not bypass the shared Service Layer validators.
    assert "resource_service.validate_hardware" in source
    assert "resource_service.validate_virtual_machine_values" in source
    assert "normalization.normalize_hostname" in source


def test_same_hostname_allowed_across_clusters(role_client_factory, auth_session_factory):
    """V-DB-F014-4: partial unique is per (cluster_id, hostname_key)."""
    editor = role_client_factory("EDITOR")
    c1 = _cluster(editor, "CL-A")
    c2 = _cluster(editor, "CL-B")
    for code in (c1["code"], c2["code"]):
        resp = _post(editor, WRITE, _csv_bytes(BM_HEADERS, [_bm(code, "shared")]))
        assert resp.status_code == 201, resp.text
    with auth_session_factory() as session:
        live = session.execute(
            text(
                "SELECT count(*) FROM resources "
                "WHERE hostname_key='shared' AND deleted_at IS NULL"
            )
        ).scalar_one()
        assert live == 2


def test_import_adds_no_catalog_objects(committed_engine, auth_session_factory):
    """V-DB-F014-8: runtime import neither adds nor drops DB objects."""
    with auth_session_factory() as session:
        cluster_service.create_cluster(session, None, code="CAT", name="Cat")

    def catalog(conn) -> dict[str, int]:
        return {
            "relations": conn.execute(
                text(
                    "SELECT count(*) FROM pg_class c JOIN pg_namespace n "
                    "ON n.oid=c.relnamespace WHERE n.nspname='public' "
                    "AND c.relkind IN ('r','i','p')"
                )
            ).scalar_one(),
            "triggers": conn.execute(
                text(
                    "SELECT count(*) FROM pg_trigger t JOIN pg_class c "
                    "ON c.oid=t.tgrelid JOIN pg_namespace n ON n.oid=c.relnamespace "
                    "WHERE n.nspname='public' AND NOT t.tgisinternal"
                )
            ).scalar_one(),
        }

    data = _csv_bytes(BM_HEADERS, [_bm("CAT", "cat1")])
    with committed_engine.connect() as conn:
        before = catalog(conn)
        # Existing objects the import depends on must be present.
        assert conn.execute(
            text(
                "SELECT count(*) FROM pg_indexes "
                "WHERE indexname='uq_resources_cluster_id_hostname_key'"
            )
        ).scalar_one() == 1
        assert conn.execute(
            text(
                "SELECT count(*) FROM pg_trigger WHERE tgname LIKE '%host_valid%'"
            )
        ).scalar_one() == 1

    with auth_session_factory() as session:
        resource_import.write_import(session, None, data, "csv", Settings(_env_file=None))

    with committed_engine.connect() as conn:
        assert catalog(conn) == before