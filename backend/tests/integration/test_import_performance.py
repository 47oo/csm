"""F014 D03 real-PostgreSQL performance evidence (Contract F014 §10).

Contract §10 places a performance-verification obligation on TEST: with real
PostgreSQL produce (1) an import time / memory baseline at the near-maximum row
count, (2) the rejection latency at the signed-off caps together with the
"no partial import" guarantee, and (3) the error-preview truncation behaviour
at the default ``import_error_preview_limit``.

These tests do not introduce a product threshold; the caps themselves are the
contract values (5,242,880 bytes / 5000 rows / 1000 preview errors). Bounds
asserted here are deliberately generous sanity ceilings (the observed baseline
is an order of magnitude below them) so the evidence is stable on a shared CI
host while still catching a catastrophic regression. Observed numbers are
printed so the test report can quote them.
"""

from __future__ import annotations

import csv
import io
import time
import tracemalloc

import pytest
from sqlalchemy import text

from app.core.config import Settings
from app.core.errors import ImportFileTooLarge, ImportRowLimitExceeded
from app.services import cluster as cluster_service
from app.services import resource_import

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

CLUSTER_CODE = "PERF"
MAX_ROWS = 5000
DEFAULT_LIMIT_BYTES = 5_242_880
DEFAULT_PREVIEW_LIMIT = 1000


def _bm_csv(rows: list[list[str]]) -> bytes:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(BM_HEADERS)
    for row in rows:
        writer.writerow(row)
    return buffer.getvalue().encode("utf-8")


def _bm_row(hostname: str, cluster: str = CLUSTER_CODE) -> list[str]:
    return [
        cluster,
        hostname,
        "BARE_METAL",
        "",
        "",
        "Dell",
        "PowerEdge R750",
        f"SN-{hostname}",
        "Xeon Platinum 8358",
        "2",
        "64",
        "262144",
        "A100",
        "0",
    ]


def _create_cluster(session_factory) -> None:
    with session_factory() as session:
        cluster_service.create_cluster(session, None, code=CLUSTER_CODE, name="Perf")


def _counts(session_factory) -> dict[str, int]:
    tables = ("resources", "bare_metal_details", "virtual_machine_details", "audit_logs")
    with session_factory() as session:
        return {
            table: int(session.execute(text(f"SELECT count(*) FROM {table}")).scalar_one())
            for table in tables
        }


def test_import_near_max_rows_baseline(committed_engine, auth_session_factory):
    """D03 ①: near-5000-row import time / memory baseline (real PG)."""
    _create_cluster(auth_session_factory)
    baseline = _counts(auth_session_factory)
    rows = [_bm_row(f"perf{i:05d}") for i in range(MAX_ROWS)]
    data = _bm_csv(rows)
    settings = Settings(_env_file=None)

    # Read-only pre-validate baseline (no writes).
    session = auth_session_factory()
    tracemalloc.start()
    started = time.perf_counter()
    result = resource_import.validate_import(session, data, "csv", settings)
    validate_seconds = time.perf_counter() - started
    _, validate_peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    session.close()
    assert result.total_rows == MAX_ROWS
    assert result.error_count == 0

    # Atomic write baseline.
    session = auth_session_factory()
    tracemalloc.start()
    started = time.perf_counter()
    created, total = resource_import.write_import(session, None, data, "csv", settings)
    write_seconds = time.perf_counter() - started
    _, write_peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    session.close()

    print(
        f"\n[D03-1] file={len(data)}B rows={MAX_ROWS} "
        f"validate={validate_seconds:.2f}s validate_peak={validate_peak / 1e6:.1f}MB "
        f"write={write_seconds:.2f}s write_peak={write_peak / 1e6:.1f}MB"
    )
    assert (created, total) == (MAX_ROWS, MAX_ROWS)
    after = _counts(auth_session_factory)
    assert after["resources"] == baseline["resources"] + MAX_ROWS
    assert after["bare_metal_details"] == baseline["bare_metal_details"] + MAX_ROWS
    # One CREATE audit per imported row on top of the cluster-creation audit.
    assert after["audit_logs"] == baseline["audit_logs"] + MAX_ROWS
    # Generous sanity ceiling (observed baseline ~43s on the test host).
    assert write_seconds < 180, write_seconds


def test_row_limit_rejection_latency_and_no_partial_import(
    committed_engine, auth_session_factory
):
    """D03 ②: row cap rejected before validation, no partial import."""
    _create_cluster(auth_session_factory)
    baseline = _counts(auth_session_factory)
    rows = [_bm_row(f"over{i:05d}") for i in range(MAX_ROWS + 1)]
    data = _bm_csv(rows)
    settings = Settings(_env_file=None)

    session = auth_session_factory()
    started = time.perf_counter()
    with pytest.raises(ImportRowLimitExceeded) as excinfo:
        resource_import.write_import(session, None, data, "csv", settings)
    seconds = time.perf_counter() - started
    session.close()

    print(f"\n[D03-2a] rows={MAX_ROWS + 1} rejected in {seconds:.3f}s")
    assert excinfo.value.details == {"limit_rows": MAX_ROWS}
    assert _counts(auth_session_factory) == baseline


def test_file_size_rejection_latency_and_no_partial_import(
    committed_engine, auth_session_factory
):
    """D03 ②: file-byte cap rejected before parsing, no partial import."""
    _create_cluster(auth_session_factory)
    baseline = _counts(auth_session_factory)
    data = b"x" * (DEFAULT_LIMIT_BYTES + 1)
    settings = Settings(_env_file=None)

    session = auth_session_factory()
    started = time.perf_counter()
    with pytest.raises(ImportFileTooLarge) as excinfo:
        resource_import.write_import(session, None, data, "csv", settings)
    seconds = time.perf_counter() - started
    session.close()

    print(
        f"\n[D03-2b] bytes={len(data)} rejected in {seconds:.4f}s "
        f"(cap {DEFAULT_LIMIT_BYTES})"
    )
    assert excinfo.value.details == {"limit_bytes": DEFAULT_LIMIT_BYTES}
    assert _counts(auth_session_factory) == baseline


def test_error_preview_truncation_at_default_limit(
    committed_engine, auth_session_factory
):
    """D03 ③: >1000 errors -> bounded preview, full count (default limit)."""
    _create_cluster(auth_session_factory)
    baseline = _counts(auth_session_factory)
    error_rows = DEFAULT_PREVIEW_LIMIT + 100
    rows = [_bm_row(f"err{i:05d}", cluster="MISSING") for i in range(error_rows)]
    data = _bm_csv(rows)
    settings = Settings(_env_file=None)

    session = auth_session_factory()
    started = time.perf_counter()
    result = resource_import.validate_import(session, data, "csv", settings)
    payload = resource_import.result_payload(result, settings)
    seconds = time.perf_counter() - started
    session.close()

    print(
        f"\n[D03-3] rows={error_rows} error_count={payload['error_count']} "
        f"preview={len(payload['errors'])} in {seconds:.2f}s"
    )
    assert payload["total_rows"] == error_rows
    assert payload["error_count"] == error_rows
    assert payload["errors_truncated"] is True
    assert len(payload["errors"]) == DEFAULT_PREVIEW_LIMIT
    # Truncation is a read-only path: nothing written.
    assert _counts(auth_session_factory) == baseline