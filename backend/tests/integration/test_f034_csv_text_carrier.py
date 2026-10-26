"""F034 CSV text carrier — independent TEST execution (real PostgreSQL).

Covers `docs/features/F034/test-report.md` §1 TEST DESIGN v1.1 cases
`TD3-T107.* … TD3-T116.*` and `TD3-ATOM.*` that are observable over HTTP.

The F034 change is frontend-only (`layers.backend=false`), so every assertion
here exercises the *unchanged* production endpoints with a payload whose bytes
are identical to what the frontend text carrier produces
(`docs/features/F034/artifacts/corpus/F-xx.csv` vs `F-xx.txt`). The single
server-visible difference between the two carriers is the multipart filename +
`text/csv;charset=utf-8` content type, which the server must ignore entirely
(TD-5 equivalence, requirements §24.5).

Corpus: `docs/features/F034/artifacts/corpus/gen-corpus.mjs` (single source of
truth; `.txt` bytes and `.csv` bytes are byte-identical by construction).

Scope-restricted cases (T115.3 / ATOM.3, real F027 access scope) live in
`test_f034_csv_text_carrier_scope.py` because the legacy integration scope shim
would otherwise mask the row-level Cluster rejection.
"""

from __future__ import annotations

import json
import tempfile
import threading
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text

from app.api.v1 import imports as imports_api
from app.core.config import Settings

from integration.f015_helpers import (  # noqa: F401
    create_cluster,
    create_network,
    create_resource,
    role_client_factory,
)

BACKEND_DIR = Path(__file__).resolve().parents[2]
REPO_ROOT = BACKEND_DIR.parent
CORPUS = REPO_ROOT / "docs/features/F034/artifacts/corpus"
ARTIFACTS = REPO_ROOT / "docs/features/F034/artifacts"

R_VALIDATE = "/api/v1/imports/resources/validate"
R_WRITE = "/api/v1/imports/resources"
W_VALIDATE = "/api/v1/imports/resource-interfaces-ips/validate"
W_WRITE = "/api/v1/imports/resource-interfaces-ips"

# The exact constants the frontend text carrier uses (importCarrier.ts).
PASTED_FILE_NAME = "csm-pasted-import.csv"
PASTED_MIME = "text/csv;charset=utf-8"
# A plain file-carrier upload name (deliberately different, must be irrelevant).
FILE_NAME = "f034-file-carrier.csv"
FILE_MIME = "text/csv"

CLUSTER = "F34A"
NET_NAME = "f34-net"
NET_CIDR = "10.34.0.0/24"
MARKER = "F034-MARKER-8a1f4c0d-6f4f-4ef3-9d4a-9f7f3c1b2e55"

COUNT_TABLES = (
    "clusters",
    "resources",
    "bare_metal_details",
    "virtual_machine_details",
    "interfaces",
    "ip_addresses",
    "audit_logs",
)

BM_HEADERS = [
    "cluster", "hostname", "resource_type", "role", "status", "manufacturer",
    "model", "serial_number", "cpu_model", "cpu_sockets", "cpu_cores",
    "memory_mb", "gpu_model", "gpu_count",
]
W26_HEADERS = [
    "cluster", "hostname", "resource_type", "role", "status", "host", "vcpu",
    "memory_mb", "disk_gb", "hypervisor", "manufacturer", "model",
    "serial_number", "cpu_model", "cpu_sockets", "cpu_cores", "gpu_model",
    "gpu_count", "name", "interface_type", "mac_address", "speed_mbps", "mtu",
    "enabled", "network", "ip",
]

def _row(headers: list[str], **values) -> str:
    """Build one CSV line for `headers` from keyword values."""
    return ",".join("" if values.get(name) is None else str(values.get(name)) for name in headers)


def _csv(headers: list[str], rows: list[dict]) -> bytes:
    return ("\n".join([",".join(headers), *(_row(headers, **r) for r in rows)]) + "\n").encode(
        "utf-8"
    )


SIGNED_REASONS = {
    "unreadable",
    "unsupported_format",
    "header_missing",
    "missing_columns",
    "unknown_columns",
    "column_order",
    "empty_file",
}
HEADER_CLASS_REASONS = {"header_missing", "missing_columns", "unknown_columns"}


# --- corpus helpers ---------------------------------------------------------


def text_bytes(name: str) -> bytes:
    """Bytes the text carrier would submit for fixture ``name``.

    Mirrors `Buffer.from(text, "utf8")`: decode the UTF-8 `.txt`, re-encode it.
    """
    return (CORPUS / f"{name}.txt").read_bytes().decode("utf-8").encode("utf-8")


def file_bytes(name: str) -> bytes:
    """Bytes the file carrier submits for fixture ``name`` (`.csv` copy)."""
    return (CORPUS / f"{name}.csv").read_bytes()


def post(client, path: str, data: bytes, carrier: str):
    """POST with either the file-carrier or text-carrier multipart shape."""
    if carrier == "file":
        files = {"file": (FILE_NAME, data, FILE_MIME)}
    elif carrier == "text":
        files = {"file": (PASTED_FILE_NAME, data, PASTED_MIME)}
    else:  # pragma: no cover - test bug guard
        raise AssertionError(f"unknown carrier {carrier!r}")
    return client.post(path, files=files, data={"format": "csv"})


def both(client, path: str, name: str):
    """Submit fixture ``name`` through both carriers (same bytes)."""
    assert file_bytes(name) == text_bytes(name), f"{name}: corpus bytes diverged"
    return (
        post(client, path, file_bytes(name), "file"),
        post(client, path, text_bytes(name), "text"),
    )


def assert_equivalent(name: str, path: str, file_resp, text_resp):
    """TD-5: identical status + deep-equal body for identical bytes."""
    assert file_resp.status_code == text_resp.status_code, (
        f"{name} {path}: carrier divergence status "
        f"file={file_resp.status_code} text={text_resp.status_code}\n"
        f"file={file_resp.text[:600]}\ntext={text_resp.text[:600]}"
    )
    assert file_resp.json() == text_resp.json(), (
        f"{name} {path}: carrier divergence body\n"
        f"file={json.dumps(file_resp.json(), ensure_ascii=False)[:900]}\n"
        f"text={json.dumps(text_resp.json(), ensure_ascii=False)[:900]}"
    )
    return file_resp


def expect_eq(client, path: str, name: str, expected_status: int):
    file_resp, text_resp = both(client, path, name)
    resp = assert_equivalent(name, path, file_resp, text_resp)
    assert resp.status_code == expected_status, f"{name} {path}: {resp.text[:800]}"
    return resp


# --- database helpers -------------------------------------------------------


def counts(session) -> dict[str, int]:
    return {
        table: int(session.execute(text(f"SELECT count(*) FROM {table}")).scalar_one())
        for table in COUNT_TABLES
    }


def find_error(payload: dict, field: str, row: int | None = None) -> dict | None:
    for error in payload["errors"]:
        if error["field"] == field and (row is None or error["row"] == row):
            return error
    return None


def public_tables(session) -> set[str]:
    return set(
        session.execute(
            text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
        ).scalars()
    )


@pytest.fixture
def seeded(role_client_factory):
    """EDITOR client plus the Cluster/Network/resource baseline the corpus needs."""
    editor, user, _ = role_client_factory("EDITOR", username="f034.editor")
    cluster = create_cluster(editor, CLUSTER, "F034 cluster")
    network = create_network(editor, CLUSTER, name=NET_NAME, cidr=NET_CIDR)
    # F-02 `host` reference and F-20 "existing conflict" row.
    create_resource(editor, CLUSTER, "f34-pre")
    create_resource(editor, CLUSTER, "f34-exists")
    return {"client": editor, "user": user, "cluster": cluster, "network": network}


# ===========================================================================
# TD-5 — equivalence matrix over the whole corpus (core criterion)
# ===========================================================================


@pytest.mark.parametrize(
    "path", [R_VALIDATE, W_VALIDATE], ids=["resources", "interface-ips"]
)
def test_td5_equivalence_matrix_all_corpus(seeded, path):
    """TD-5 (2): every applicable corpus file, both carriers, both entry points."""
    client = seeded["client"]
    names = sorted(p.stem for p in CORPUS.glob("F-*.txt"))
    assert len(names) >= 28, names
    observations = {}
    for name in names:
        file_resp, text_resp = both(client, path, name)
        resp = assert_equivalent(name, path, file_resp, text_resp)
        body = resp.json()
        if "error" in body:
            record = {"status": resp.status_code, "error": body["error"]}
        else:
            record = {
                "status": resp.status_code,
                "format": body.get("format"),
                "total_rows": body.get("total_rows"),
                "importable_rows": body.get("importable_rows"),
                "error_count": body.get("error_count"),
                "errors_truncated": body.get("errors_truncated"),
                "errors": body.get("errors"),
            }
        observations[f"{path}|{name}"] = record

    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    out = ARTIFACTS / f"equivalence-observations{'' if path == R_VALIDATE else '-interface-ips'}.json"
    out.write_text(json.dumps(observations, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    # Spot-check that the corpus actually exercises both outcomes (anti-vacuity).
    statuses = {record["status"] for record in observations.values()}
    assert 200 in statuses and 422 in statuses, statuses


def test_td5_write_error_equivalence(seeded):
    """TD-5 (3) / TD3-T109.4: error-path write responses are identical."""
    resp = expect_eq(seeded["client"], R_WRITE, "F-20", 422)
    error = resp.json()["error"]
    assert error["code"] == "IMPORT_VALIDATION_FAILED"
    assert error["details"]["error_count"] >= 6


def test_td6_atom2_duplicate_import_rejected_whole_batch(seeded, auth_session_factory):
    """TD3-ATOM.2: identical bytes cannot be imported twice; no UPDATE audit."""
    client = seeded["client"]
    first = post(client, R_WRITE, text_bytes("F-01"), "text")
    assert first.status_code == 201, first.text
    with auth_session_factory() as session:
        after_first = counts(session)

    second = post(client, R_WRITE, text_bytes("F-01"), "text")
    assert second.status_code == 422, second.text
    assert second.json()["error"]["code"] == "IMPORT_VALIDATION_FAILED"
    details = second.json()["error"]["details"]
    assert details["error_count"] == 2
    assert {e["field"] for e in details["errors"]} == {"hostname"}

    with auth_session_factory() as session:
        after_second = counts(session)
        updates = session.execute(
            text("SELECT count(*) FROM audit_logs WHERE action <> 'CREATE'")
        ).scalar_one()
    assert after_second == after_first, "second (rejected) import left residue"
    assert updates == 0, "no UPDATE/DELETE audit may be produced by a rejected import"


# ===========================================================================
# T108 — legal text two-step flow / row numbering / envelope
# ===========================================================================


def test_td3_t108_2_valid_text_validate(seeded):
    """TD3-T108.2: legal text -> 200 with exact counters (BM / VM / 26-col)."""
    client = seeded["client"]
    for name, expected in (
        ("F-01", {"total_rows": 2, "importable_rows": 2, "error_count": 0}),
        ("F-02", {"total_rows": 1, "importable_rows": 1, "error_count": 0}),
    ):
        resp = expect_eq(client, R_VALIDATE, name, 200)
        body = resp.json()
        assert body["format"] == "csv"
        for key, value in expected.items():
            assert body[key] == value, f"{name} {key}={body[key]!r}"

    resp = expect_eq(client, W_VALIDATE, "F-03", 200)
    body = resp.json()
    assert (body["total_rows"], body["importable_rows"], body["error_count"]) == (3, 3, 0)


def test_td3_t108_3_error_batch_rejected_on_write(seeded, auth_session_factory):
    """TD3-T108.3: error_count>0 -> write rejected 422, DB unchanged."""
    client = seeded["client"]
    validate = expect_eq(client, R_VALIDATE, "F-20", 200)
    expected_error_count = validate.json()["error_count"]

    with auth_session_factory() as session:
        before = counts(session)
    write = expect_eq(client, R_WRITE, "F-20", 422)
    details = write.json()["error"]["details"]
    assert details["error_count"] == expected_error_count
    assert details["importable_rows"] == validate.json()["importable_rows"]
    with auth_session_factory() as session:
        assert counts(session) == before


def test_td3_t108_5_t116_8_write_revalidates_after_state_change(
    seeded, auth_session_factory
):
    """TD3-T108.5 / TD3-T116.8: server re-validates the identical bytes on write."""
    client = seeded["client"]
    data = text_bytes("F-01")
    assert post(client, R_VALIDATE, data, "text").status_code == 200

    # External state change after a green pre-validation.
    create_resource(client, CLUSTER, "f34-h1")

    with auth_session_factory() as session:
        before = counts(session)
    write = post(client, R_WRITE, data, "text")
    assert write.status_code == 422, write.text
    details = write.json()["error"]["details"]
    assert details["error_count"] == 1
    assert details["errors"][0]["row"] == 2
    assert details["errors"][0]["field"] == "hostname"
    with auth_session_factory() as session:
        assert counts(session) == before


def test_td3_t108_6_t113_5_row_numbering_and_trailing_blank_lines(seeded):
    """TD3-T108.6 / TD3-T113.5: header is row 1; trailing blank records ignored."""
    client = seeded["client"]

    resp = expect_eq(client, R_VALIDATE, "F-10b", 200)
    body = resp.json()
    assert body["total_rows"] == 3
    assert body["error_count"] == 1
    assert body["errors"][0]["row"] == 4, body["errors"]

    with_blank = expect_eq(client, R_VALIDATE, "F-10", 200)
    without_blank = expect_eq(client, R_VALIDATE, "F-01", 200)
    assert with_blank.json()["total_rows"] == without_blank.json()["total_rows"] == 2
    assert with_blank.json()["error_count"] == without_blank.json()["error_count"] == 0


def test_td3_t108_7_t116_7_validate_idempotent_no_side_effects(
    seeded, auth_session_factory
):
    """TD3-T108.7: repeated pre-validation is identical and writes nothing."""
    client = seeded["client"]
    with auth_session_factory() as session:
        before = counts(session)
    first = post(client, R_VALIDATE, text_bytes("F-01"), "text")
    second = post(client, R_VALIDATE, text_bytes("F-01"), "text")
    assert first.status_code == second.status_code == 200
    assert first.json() == second.json()
    with auth_session_factory() as session:
        assert counts(session) == before


def test_td3_t108_8_26col_write_envelope_parity(seeded, auth_session_factory):
    """TD3-T108.8 / TD-5 (3): text vs file carrier write envelopes agree."""
    client = seeded["client"]
    with auth_session_factory() as session:
        before = counts(session)

    text_resp = post(client, W_WRITE, text_bytes("F-03"), "text")
    assert text_resp.status_code == 201, text_resp.text
    text_body = text_resp.json()

    file_resp = post(client, W_WRITE, file_bytes("F-03f"), "file")
    assert file_resp.status_code == 201, file_resp.text
    file_body = file_resp.json()

    assert set(text_body) == set(file_body) == {
        "created",
        "total_rows",
        "interfaces_created",
        "ip_addresses_created",
    }
    assert text_body == file_body == {
        "created": 2,
        "total_rows": 3,
        "interfaces_created": 3,
        "ip_addresses_created": 3,
    }

    with auth_session_factory() as session:
        after = counts(session)
    assert after["resources"] - before["resources"] == 4
    assert after["interfaces"] - before["interfaces"] == 6
    assert after["ip_addresses"] - before["ip_addresses"] == 6


# ===========================================================================
# T109 — row errors keep shape/content, no fail-fast
# ===========================================================================


def test_td3_t109_error_matrix_shape_and_no_failfast(seeded):
    """TD3-T109.1/2/4: six error classes aggregated, RowError shape intact."""
    client = seeded["client"]
    resp = expect_eq(client, R_VALIDATE, "F-20", 200)
    body = resp.json()

    assert body["total_rows"] == 7
    assert body["error_count"] == 6, body["errors"]
    assert len(body["errors"]) == 6
    assert body["importable_rows"] == 1

    by_row = {error["row"]: error for error in body["errors"]}
    assert by_row[2]["field"] == "role"
    assert by_row[3]["field"] == "memory_mb"
    assert by_row[4]["field"] == "manufacturer"
    assert by_row[6]["field"] == "hostname"
    assert by_row[6]["related_row"] == 5
    assert by_row[7]["field"] == "hostname"
    assert by_row[8]["field"] == "cluster"

    for error in body["errors"]:
        assert set(error) == {"row", "field", "reason", "related_row"}
        assert isinstance(error["row"], int) and error["row"] >= 2
        assert isinstance(error["field"], str) and error["field"]
        assert error["field"] in BM_HEADERS, error
        assert isinstance(error["reason"], str) and error["reason"].strip()
        assert error["related_row"] is None or isinstance(error["related_row"], int)


def test_td3_t109_3_f023_error_matrix(seeded):
    """TD3-T109.3: 26-column variant keeps duplicate/network/applicability shape."""
    client = seeded["client"]
    resp = expect_eq(client, W_VALIDATE, "F-20w", 200)
    body = resp.json()
    assert body["total_rows"] == 4
    assert body["error_count"] == 3, body["errors"]
    assert body["importable_rows"] == 1

    by_row = {error["row"]: error for error in body["errors"]}
    assert by_row[3]["field"] == "ip"
    assert by_row[3]["related_row"] == 2
    assert by_row[4]["field"] == "network"
    assert by_row[5]["field"] == "vcpu"
    for error in body["errors"]:
        assert error["field"] in W26_HEADERS


# ===========================================================================
# T110 — empty / whitespace-only / header-only
# ===========================================================================


def test_td3_t110_header_only_empty_file_no_residue(seeded, auth_session_factory):
    """TD3-T110.3/4: header-only text -> 422 empty_file, zero residue."""
    client = seeded["client"]
    with auth_session_factory() as session:
        before = counts(session)
    for path, name in ((R_VALIDATE, "F-06a"), (W_VALIDATE, "F-06b")):
        resp = expect_eq(client, path, name, 422)
        assert resp.json()["error"]["code"] == "IMPORT_INVALID_FILE"
        assert resp.json()["error"]["details"] == {"reason": "empty_file"}
    for path, name in ((R_WRITE, "F-06a"), (W_WRITE, "F-06b")):
        expect_eq(client, path, name, 422)
    with auth_session_factory() as session:
        assert counts(session) == before


def test_td3_t110_5_nonblank_without_header(seeded):
    """TD3-T110.5: non-blank text with no usable header -> header_missing."""
    resp = expect_eq(seeded["client"], R_VALIDATE, "F-05b", 422)
    assert resp.json()["error"]["details"]["reason"] == "header_missing"


def test_td3_t110_6_bom_only_text(seeded, auth_session_factory):
    """TD3-T110.6 / TD-I-5: BOM-only text is rejected and writes nothing.

    The frontend blocks it locally (`trim()` treats U+FEFF as blank, F034-FE-01);
    the server branch is `IMPORT_INVALID_FILE{empty_file}`. Both are acceptable
    per TD-I-5 — recorded branch: server 422 empty_file, no write.
    """
    client = seeded["client"]
    with auth_session_factory() as session:
        before = counts(session)
    resp = expect_eq(client, R_VALIDATE, "F-24", 422)
    assert resp.json()["error"]["details"]["reason"] == "empty_file"
    expect_eq(client, R_WRITE, "F-24", 422)
    with auth_session_factory() as session:
        assert counts(session) == before


# ===========================================================================
# T111 — UTF-8 byte cap / row cap
# ===========================================================================


def test_td3_t111_5_server_byte_cap_strictly_greater(seeded, monkeypatch):
    """TD3-T111.5: server compares UTF-8 bytes; strictly greater rejects."""
    client = seeded["client"]
    exact = len(text_bytes("F-01"))  # 356

    limited = Settings(_env_file=None, import_max_file_bytes=exact - 1)
    monkeypatch.setattr(imports_api, "get_settings", lambda: limited)
    resp = expect_eq(client, R_VALIDATE, "F-01", 413)
    assert resp.json()["error"] == {
        "code": "IMPORT_FILE_TOO_LARGE",
        "message": "Import file too large",
        "details": {"limit_bytes": exact - 1},
    }

    at_limit = Settings(_env_file=None, import_max_file_bytes=exact)
    monkeypatch.setattr(imports_api, "get_settings", lambda: at_limit)
    resp = expect_eq(client, R_VALIDATE, "F-01", 200)
    assert resp.json()["error_count"] == 0


def _bm_rows(count: int, cluster: str) -> bytes:
    return _csv(
        BM_HEADERS,
        [
            {
                "cluster": cluster,
                "hostname": f"f34-bulk-{index}",
                "resource_type": "BARE_METAL",
                "role": "COMPUTE",
                "status": "IDLE",
            }
            for index in range(count)
        ],
    )


def test_td3_t111_6_row_cap_5001_rejected_without_partial_import(
    seeded, auth_session_factory
):
    """TD3-T111.6 / ATOM.6: 5001 data rows -> 413, no partial import."""
    client = seeded["client"]
    data = _bm_rows(5001, CLUSTER)
    assert data.count(b"\n") == 5002

    with auth_session_factory() as session:
        before = counts(session)
    for path, carrier in ((R_VALIDATE, "text"), (R_WRITE, "text")):
        resp = post(client, path, data, carrier)
        assert resp.status_code == 413, resp.text[:400]
        assert resp.json()["error"] == {
            "code": "IMPORT_ROW_LIMIT_EXCEEDED",
            "message": "Import row limit exceeded",
            "details": {"limit_rows": 5000},
        }
    file_resp = post(client, R_VALIDATE, data, "file")
    assert file_resp.status_code == 413
    with auth_session_factory() as session:
        assert counts(session) == before


def test_td3_t111_7_read_side_5000_rows_truncated_preview(seeded):
    """TD3-T111.7: 5000 data rows -> 200, errors_truncated, 1000-row preview."""
    client = seeded["client"]
    data = _bm_rows(5000, "F34MISSING")
    resp = post(client, R_VALIDATE, data, "text")
    assert resp.status_code == 200, resp.text[:400]
    body = resp.json()
    assert body["total_rows"] == 5000
    assert body["error_count"] == 5000
    assert body["importable_rows"] == 0
    assert body["errors_truncated"] is True
    assert len(body["errors"]) == 1000

    file_resp = post(client, R_VALIDATE, data, "file")
    assert file_resp.status_code == 200
    assert file_resp.json() == body


def test_td3_t111_9_t114_non_ascii_roundtrip(seeded, auth_session_factory):
    """TD3-T111.9: Chinese + emoji values survive byte-exact."""
    client = seeded["client"]
    resp = expect_eq(client, R_VALIDATE, "F-26", 200)
    assert resp.json()["error_count"] == 0, resp.json()

    write = post(client, R_WRITE, text_bytes("F-26"), "text")
    assert write.status_code == 201, write.text
    listing = client.get("/api/v1/resources", params={"q": "f34-utf8"})
    assert listing.status_code == 200
    item = next(i for i in listing.json()["items"] if i["hostname"] == "f34-utf8")
    assert item["hardware"]["manufacturer"] == "戴尔, Inc.", item
    assert item["hardware"]["gpu_model"] == "A100-🚀", item

    with auth_session_factory() as session:
        stored = session.execute(
            text(
                "SELECT manufacturer, gpu_model FROM bare_metal_details d "
                "JOIN resources r ON r.id = d.resource_id WHERE r.hostname = :h"
            ),
            {"h": "f34-utf8"},
        ).one()
    assert stored[0] == "戴尔, Inc."
    assert stored[1] == "A100-🚀"


# ===========================================================================
# T112 — header strictness
# ===========================================================================


def test_td3_t112_header_matrix(seeded):
    """TD3-T112.1/2/3/4/5/6/8: strict header rules + carrier equivalence."""
    client = seeded["client"]

    missing = expect_eq(client, R_VALIDATE, "F-16", 422)
    assert missing.json()["error"]["details"] == {
        "reason": "missing_columns",
        "missing_columns": ["hostname"],
    }

    unknown = expect_eq(client, R_VALIDATE, "F-17", 422)
    assert unknown.json()["error"]["details"] == {
        "reason": "unknown_columns",
        "unknown_columns": ["interface_name"],
    }

    for name in ("F-18a", "F-18b"):
        resp = expect_eq(client, R_VALIDATE, name, 422)
        assert resp.json()["error"]["details"]["reason"] == "column_order", name

    case = expect_eq(client, R_VALIDATE, "F-19", 422)
    assert case.json()["error"]["details"]["reason"] in HEADER_CLASS_REASONS

    no_header = expect_eq(client, R_VALIDATE, "F-15a", 422)
    assert no_header.json()["error"]["details"]["reason"] == "header_missing"

    # TD3-T112.7: a data row is never promoted to a header.
    data_first = expect_eq(client, R_VALIDATE, "F-15", 422)
    assert data_first.json()["error"]["details"]["reason"] in HEADER_CLASS_REASONS

    # TD3-T112.6: tab-separated text is rejected; reason only fixed as a class.
    tabs = expect_eq(client, R_VALIDATE, "F-14", 422)
    assert tabs.json()["error"]["code"] == "IMPORT_INVALID_FILE"
    assert tabs.json()["error"]["details"]["reason"] in SIGNED_REASONS, tabs.json()


def test_td3_t112_6_tab_separated_no_write(seeded, auth_session_factory):
    """TD3-T112.6: tab-separated content never reaches a write."""
    client = seeded["client"]
    with auth_session_factory() as session:
        before = counts(session)
    for path in (R_VALIDATE, R_WRITE):
        expect_eq(client, path, "F-14", 422)
    with auth_session_factory() as session:
        assert counts(session) == before


# ===========================================================================
# T113 — BOM / line endings / trailing blanks
# ===========================================================================


def test_td3_t113_bom_and_line_endings(seeded):
    """TD3-T113.2/3: BOM, CRLF, LF and mixed endings behave identically."""
    client = seeded["client"]
    baseline = expect_eq(client, R_VALIDATE, "F-01", 200).json()

    bom = expect_eq(client, R_VALIDATE, "F-07", 200).json()
    assert bom == baseline
    assert text_bytes("F-07").startswith(b"\xef\xbb\xbf")

    for name in ("F-08", "F-09"):
        body = expect_eq(client, R_VALIDATE, name, 200).json()
        assert body["total_rows"] == baseline["total_rows"], name
        assert body["error_count"] == baseline["error_count"], name
        assert body["errors"] == baseline["errors"], name


# ===========================================================================
# T114 — CSV field boundaries (equivalence-only judgement, TD-I-1)
# ===========================================================================


def test_td3_t114_field_boundaries(seeded, auth_session_factory):
    """TD3-T114.1/2/3/4: commas, escaped quotes, embedded newlines, unclosed quote."""
    client = seeded["client"]

    quoted_newline = expect_eq(client, R_VALIDATE, "F-11", 200)
    body = quoted_newline.json()
    # Logical records: the quoted newline does not create an extra data row.
    assert body["total_rows"] == 2
    hostname_error = find_error(body, "hostname")
    assert hostname_error is not None, body["errors"]
    assert hostname_error["row"] == 3, body["errors"]
    # Existing F014 rule (unchanged by F034): control characters in a text field
    # are rejected, so the quoted-newline VALUE is reported at its own row too.
    control = find_error(body, "manufacturer")
    assert control is not None and control["row"] == 2, body["errors"]
    assert "control character" in control["reason"], control

    write = post(client, R_WRITE, text_bytes("F-12"), "text")
    assert write.status_code == 201, write.text
    listing = client.get("/api/v1/resources", params={"q": "f34-q2"})
    q2 = next(i for i in listing.json()["items"] if i["hostname"] == "f34-q2")
    assert q2["hardware"]["manufacturer"] == "Dell, Inc.", q2
    listing3 = client.get("/api/v1/resources", params={"q": "f34-q3"})
    q3 = next(i for i in listing3.json()["items"] if i["hostname"] == "f34-q3")
    assert q3["hardware"]["manufacturer"] == 'Manu"facturer', q3

    # F-13 unclosed quote: judge EQUIVALENCE only (architecture §12 / TD-I-1).
    file_resp, text_resp = both(client, R_VALIDATE, "F-13")
    assert_equivalent("F-13", R_VALIDATE, file_resp, text_resp)
    observed = file_resp.json()
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    (ARTIFACTS / "t114-unclosed-quote-observation.json").write_text(
        json.dumps(
            {
                "fixture": "F-13",
                "carrier_equivalence": "identical status + body",
                "status": file_resp.status_code,
                "body": observed,
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )


# ===========================================================================
# T115 — permissions / audit / no trace
# ===========================================================================


def test_td3_t115_1_t115_2_permissions(seeded, role_client_factory, auth_app):
    """TD3-T115.1/2: VIEWER 403, unauthenticated 401 (401 before 403)."""
    data = text_bytes("F-01")

    unauth = TestClient(auth_app)
    unauth.__enter__()
    try:
        for path in (R_VALIDATE, W_VALIDATE, R_WRITE, W_WRITE):
            resp = post(unauth, path, data, "text")
            assert resp.status_code == 401, (path, resp.status_code, resp.text[:200])
            assert resp.json()["error"]["code"] == "AUTH_REQUIRED"
    finally:
        unauth.__exit__(None, None, None)

    viewer, _, _ = role_client_factory("VIEWER")
    for path in (R_VALIDATE, W_VALIDATE, R_WRITE, W_WRITE):
        resp = post(viewer, path, data, "text")
        assert resp.status_code == 403, (path, resp.status_code, resp.text[:200])
        assert resp.json()["error"] == {
            "code": "FORBIDDEN",
            "message": "Forbidden",
            "details": {"reason": "permission"},
        }


def test_td3_t115_4_audit_parity(seeded, auth_session_factory):
    """TD3-T115.4: one CREATE audit per object, operator = current user, same shape."""
    client = seeded["client"]
    with auth_session_factory() as session:
        before = counts(session)

    text_write = post(client, R_WRITE, text_bytes("F-01"), "text")
    assert text_write.status_code == 201, text_write.text
    with auth_session_factory() as session:
        after_text = counts(session)
        rows = session.execute(
            text(
                "SELECT action, object_type, operator_username, "
                "before_data IS NULL AS before_null, after_data IS NULL AS after_null "
                "FROM audit_logs WHERE object_id IN ("
                "  SELECT id FROM resources WHERE hostname IN ('f34-h1','f34-h2'))"
            )
        ).all()
    created = after_text["audit_logs"] - before["audit_logs"]
    assert created == 2, created
    assert len(rows) == 2
    for row in rows:
        assert row.action == "CREATE"
        assert row.object_type == "resource"
        assert row.operator_username == seeded["user"].username
        assert row.before_null is True and row.after_null is False

    # Same shape from the file carrier with different objects.
    file_write = post(client, R_WRITE, _bm_rows_alt(), "file")
    assert file_write.status_code == 201, file_write.text
    with auth_session_factory() as session:
        after_file = counts(session)
        rows_file = session.execute(
            text(
                "SELECT action, object_type, operator_username, "
                "before_data IS NULL, after_data IS NULL FROM audit_logs "
                "WHERE object_id IN (SELECT id FROM resources WHERE hostname LIKE 'f34-file-%')"
            )
        ).all()
    assert after_file["audit_logs"] - after_text["audit_logs"] == 2
    assert {tuple(r) for r in rows_file} == {tuple(r) for r in rows}


def _bm_rows_alt() -> bytes:
    """Two legal BM rows with file-carrier-specific hostnames."""
    return _csv(
        BM_HEADERS,
        [
            {
                "cluster": CLUSTER,
                "hostname": f"f34-file-{index}",
                "resource_type": "BARE_METAL",
                "role": "COMPUTE",
                "status": "IDLE",
            }
            for index in (1, 2)
        ],
    )


def test_td3_t115_5_no_trace_in_response_audit_or_schema(
    seeded, auth_session_factory
):
    """TD3-T115.5: no raw pasted content in responses/audit; no staging table."""
    client = seeded["client"]
    raw = text_bytes("F-25").decode("utf-8")

    with auth_session_factory() as session:
        tables_before = public_tables(session)

    write = post(client, R_WRITE, text_bytes("F-25"), "text")
    assert write.status_code == 201, write.text
    body_text = write.text
    assert raw not in body_text, "response echoed the whole pasted text"
    assert raw.splitlines()[0] not in body_text, "response echoed the header line"

    # An invalid variant exercises the error body as well.
    error_resp = post(client, R_WRITE, text_bytes("F-25").replace(b"f34-marker", b"BAD HOST!"), "text")
    assert error_resp.status_code == 422, error_resp.text
    assert raw not in error_resp.text

    with auth_session_factory() as session:
        hit = session.execute(
            text("SELECT count(*) FROM audit_logs WHERE after_data::text LIKE :p"),
            {"p": f"%{raw.splitlines()[0]}%"},
        ).scalar_one()
        assert hit == 0, "audit_logs contains the pasted header/text"
        tables_after = public_tables(session)
    assert tables_after == tables_before, f"unexpected new tables: {tables_after - tables_before}"


def test_td3_t115_9_no_application_temp_files(seeded):
    """TD3-T115.9: <=1 MiB text carrier leaves no application temp file."""
    client = seeded["client"]
    tmpdir = Path(tempfile.gettempdir())

    def snapshot() -> set[str]:
        return {p.name for p in tmpdir.iterdir() if "import" in p.name.lower() or p.suffix in {".csv", ".tsv"}}

    before = snapshot()
    assert post(client, R_VALIDATE, text_bytes("F-01"), "text").status_code == 200
    assert post(client, R_VALIDATE, text_bytes("F-20"), "text").status_code == 200
    after = snapshot()
    assert after == before, f"new temp artifacts: {after - before}"


# ===========================================================================
# ATOMICITY — whole-batch rollback, concurrency
# ===========================================================================


def test_td3_atom1_whole_batch_rollback_no_residue(seeded, auth_session_factory):
    """TD3-ATOM.1: one bad row rolls back the whole batch (both entry points)."""
    client = seeded["client"]

    bm_bytes = _csv(
        BM_HEADERS,
        [
            {"cluster": CLUSTER, "hostname": "f34-ok-1", "resource_type": "BARE_METAL", "role": "COMPUTE", "status": "IDLE"},
            {"cluster": CLUSTER, "hostname": "f34-ok-2", "resource_type": "BARE_METAL", "role": "COMPUTE", "status": "IDLE"},
            {"cluster": "F34MISSING", "hostname": "f34-bad-1", "resource_type": "BARE_METAL", "role": "COMPUTE", "status": "IDLE"},
        ],
    )

    with auth_session_factory() as session:
        before = counts(session)
    resp = post(client, R_WRITE, bm_bytes, "text")
    assert resp.status_code == 422, resp.text[:400]
    details = resp.json()["error"]["details"]
    assert details["errors"][0]["row"] == 4
    assert details["errors"][0]["field"] == "cluster"
    with auth_session_factory() as session:
        after = counts(session)
        residue = session.execute(
            text("SELECT count(*) FROM resources WHERE hostname LIKE 'f34-ok-%'")
        ).scalar_one()
    assert after == before
    assert residue == 0

    # 26-column variant: interfaces / ip_addresses must roll back too.
    w26_bytes = _csv(
        W26_HEADERS,
        [
            {"cluster": CLUSTER, "hostname": "f34-w-ok", "resource_type": "BARE_METAL", "role": "COMPUTE", "status": "IDLE", "name": "eth0", "interface_type": "PHYSICAL", "network": NET_NAME, "ip": "10.34.2.11"},
            {"cluster": "F34MISSING", "hostname": "f34-w-bad", "resource_type": "BARE_METAL", "role": "COMPUTE", "status": "IDLE", "name": "eth0", "interface_type": "PHYSICAL", "network": NET_NAME, "ip": "10.34.2.12"},
        ],
    )
    resp = post(client, W_WRITE, w26_bytes, "text")
    assert resp.status_code == 422, resp.text[:400]
    with auth_session_factory() as session:
        after_w = counts(session)
        residue_w = session.execute(
            text(
                "SELECT (SELECT count(*) FROM resources WHERE hostname LIKE 'f34-w-%') "
                "+ (SELECT count(*) FROM interfaces WHERE name = 'eth0' AND resource_id IN "
                "(SELECT id FROM resources WHERE hostname LIKE 'f34-w-%'))"
            )
        ).scalar_one()
    assert after_w == before
    assert residue_w == 0


def test_td3_atom4_concurrent_same_bytes(
    seeded, role_client_factory, auth_session_factory
):
    """TD3-ATOM.4: two concurrent identical imports -> exactly one wins, no 500."""
    clients = []
    for index in (1, 2):
        client, _, _ = role_client_factory("EDITOR", username=f"f034.race{index}")
        clients.append(client)

    payload = _csv(
        BM_HEADERS,
        [
            {
                "cluster": CLUSTER,
                "hostname": "f34-race",
                "resource_type": "BARE_METAL",
                "role": "COMPUTE",
                "status": "IDLE",
            }
        ],
    )

    barrier = threading.Barrier(2)
    results: list[tuple[int, str]] = []
    lock = threading.Lock()

    def run(client):
        barrier.wait(timeout=10)
        response = post(client, R_WRITE, payload, "text")
        with lock:
            results.append((response.status_code, response.text[:300]))

    threads = [threading.Thread(target=run, args=(client,)) for client in clients]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
    assert all(not thread.is_alive() for thread in threads)

    statuses = sorted(status for status, _ in results)
    assert statuses[0] == 201, results
    assert 400 <= statuses[1] < 500, f"loser must be a 4xx, got {results}"

    with auth_session_factory() as session:
        rows = session.execute(
            text("SELECT count(*) FROM resources WHERE hostname = 'f34-race'")
        ).scalar_one()
        audits = session.execute(
            text(
                "SELECT count(*) FROM audit_logs WHERE object_id IN "
                "(SELECT id FROM resources WHERE hostname = 'f34-race')"
            )
        ).scalar_one()
    assert rows == 1, f"duplicate rows: {rows}"
    assert audits == 1, f"audit rows must equal created objects, got {audits}"
