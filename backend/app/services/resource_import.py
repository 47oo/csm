"""CSV / ``.xlsx`` resource bulk import (Contract F014, DR-190..DR-212).

Two-phase import on top of the ordinary Resource Service Layer (DR-202):

* :func:`validate_import` — read-only, idempotent, no Audit/locks; aggregates
  every row error (row/field/reason, optional ``related_row``).
* :func:`write_import` — re-validates against the current transaction state and
  inserts inside a single transaction with per-row SAVEPOINT attribution; any
  error rolls the whole batch back (DR-203).

The module owns the frozen template definitions (DR-198), CSV/xlsx parsing
(DR-194/DR-207), the aggregation-friendly per-row validation orchestration and
the batch write. Row values are validated by the *same* Service Layer primitives
used by ``POST /resources`` (cluster resolution, hostname normalisation,
hardware/VM value validation, the VM Host four conditions); only the write is
staged through :func:`app.services.resource.stage_resource` — there is no direct
SQL/ORM bypass (A14/V-SL-1).
"""

from __future__ import annotations

import csv
import io
import re
import uuid
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.core.errors import (
    AppError,
    ImportFileTooLarge,
    ImportInvalidFile,
    ImportRowLimitExceeded,
    ImportValidationFailed,
)
from app.models.resource import Resource
from app.services import cluster as cluster_service
from app.services import normalization
from app.services import resource as resource_service

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from app.core.auth import Operator
    from app.core.config import Settings

BARE_METAL = "BARE_METAL"
VIRTUAL_MACHINE = "VIRTUAL_MACHINE"

_INT_RE = re.compile(r"[+-]?[0-9]+")


@dataclass(frozen=True)
class ImportColumn:
    name: str
    required: bool
    target: str
    type: str
    description: str
    example: str
    unit: str | None = None
    enum: tuple[str, ...] | None = None


@dataclass(frozen=True)
class ImportTemplate:
    resource_type: str
    columns: tuple[ImportColumn, ...]

    @property
    def names(self) -> list[str]:
        return [column.name for column in self.columns]


_CLUSTER_COLUMN = ImportColumn(
    name="cluster",
    required=True,
    target="resource.cluster",
    type="string",
    unit=None,
    enum=None,
    description=(
        "Cluster code (case-insensitive) or UUID; must exist and be undeleted"
    ),
    example="N96P",
)
_HOSTNAME_COLUMN = ImportColumn(
    name="hostname",
    required=True,
    target="resource.hostname",
    type="string",
    unit=None,
    enum=None,
    description=(
        "Resource hostname; trimmed and ASCII-folded to lower case; unique per "
        "cluster among undeleted resources"
    ),
    example="cn001",
)
_ROLE_COLUMN = ImportColumn(
    name="role",
    required=False,
    target="resource.role",
    type="enum",
    unit=None,
    enum=("COMPUTE", "LOGIN", "MANAGEMENT", "STORAGE", "SERVICE", "GPU", "OTHER"),
    description="Resource role; empty = OTHER",
    example="COMPUTE",
)
_STATUS_COLUMN = ImportColumn(
    name="status",
    required=False,
    target="resource.status",
    type="enum",
    unit=None,
    enum=("IDLE", "ALLOC", "DOWN", "UNKNOWN"),
    description="Resource status; empty = UNKNOWN",
    example="IDLE",
)

_BM_TEMPLATE = ImportTemplate(
    resource_type=BARE_METAL,
    columns=(
        _CLUSTER_COLUMN,
        _HOSTNAME_COLUMN,
        ImportColumn(
            name="resource_type",
            required=True,
            target="resource.resource_type",
            type="enum",
            unit=None,
            enum=(BARE_METAL,),
            description="Fixed value BARE_METAL for this template",
            example=BARE_METAL,
        ),
        _ROLE_COLUMN,
        _STATUS_COLUMN,
        ImportColumn(
            name="manufacturer",
            required=False,
            target="hardware.manufacturer",
            type="string",
            unit=None,
            enum=None,
            description="Hardware manufacturer; empty = unknown (null)",
            example="Dell",
        ),
        ImportColumn(
            name="model",
            required=False,
            target="hardware.model",
            type="string",
            unit=None,
            enum=None,
            description="Hardware model; empty = unknown (null)",
            example="PowerEdge R750",
        ),
        ImportColumn(
            name="serial_number",
            required=False,
            target="hardware.serial_number",
            type="string",
            unit=None,
            enum=None,
            description="Hardware serial number; empty = unknown (null)",
            example="SN-12345",
        ),
        ImportColumn(
            name="cpu_model",
            required=False,
            target="hardware.cpu_model",
            type="string",
            unit=None,
            enum=None,
            description="CPU model; empty = unknown (null)",
            example="Xeon Platinum 8358",
        ),
        ImportColumn(
            name="cpu_sockets",
            required=False,
            target="hardware.cpu_sockets",
            type="integer",
            unit=None,
            enum=None,
            description="Physical CPU sockets (positive integer); empty = unknown (null)",
            example="2",
        ),
        ImportColumn(
            name="cpu_cores",
            required=False,
            target="hardware.cpu_cores",
            type="integer",
            unit=None,
            enum=None,
            description=(
                "Physical CPU cores (positive integer, no hyper-threading); "
                "empty = unknown (null)"
            ),
            example="64",
        ),
        ImportColumn(
            name="memory_mb",
            required=False,
            target="hardware.memory_mb",
            type="integer",
            unit="MiB",
            enum=None,
            description="Physical memory (MiB, positive integer); empty = unknown (null)",
            example="262144",
        ),
        ImportColumn(
            name="gpu_model",
            required=False,
            target="hardware.gpu_model",
            type="string",
            unit=None,
            enum=None,
            description="GPU model; empty = unknown (null)",
            example="A100",
        ),
        ImportColumn(
            name="gpu_count",
            required=False,
            target="hardware.gpu_count",
            type="integer",
            unit=None,
            enum=None,
            description=(
                "GPU count (non-negative integer; 0 = explicitly none, empty = unknown)"
            ),
            example="8",
        ),
    ),
)

_VM_TEMPLATE = ImportTemplate(
    resource_type=VIRTUAL_MACHINE,
    columns=(
        _CLUSTER_COLUMN,
        _HOSTNAME_COLUMN,
        ImportColumn(
            name="resource_type",
            required=True,
            target="resource.resource_type",
            type="enum",
            unit=None,
            enum=(VIRTUAL_MACHINE,),
            description="Fixed value VIRTUAL_MACHINE for this template",
            example=VIRTUAL_MACHINE,
        ),
        _ROLE_COLUMN,
        _STATUS_COLUMN,
        ImportColumn(
            name="host",
            required=True,
            target="virtual_machine.host_resource_id",
            type="string",
            unit=None,
            enum=None,
            description=(
                "Hostname (or UUID) of an existing, undeleted BARE_METAL host in "
                "the same cluster; must exist before the batch starts"
            ),
            example="cn001",
        ),
        ImportColumn(
            name="vcpu",
            required=False,
            target="virtual_machine.vcpu",
            type="integer",
            unit=None,
            enum=None,
            description="vCPU count (positive integer); empty = unknown (null)",
            example="8",
        ),
        ImportColumn(
            name="memory_mb",
            required=False,
            target="virtual_machine.memory_mb",
            type="integer",
            unit="MiB",
            enum=None,
            description="Allocated memory (MiB, positive integer); empty = unknown (null)",
            example="16384",
        ),
        ImportColumn(
            name="disk_gb",
            required=False,
            target="virtual_machine.disk_gb",
            type="integer",
            unit="GiB",
            enum=None,
            description=(
                "Disk capacity (GiB, non-negative integer; 0 = explicitly none, "
                "empty = unknown)"
            ),
            example="100",
        ),
        ImportColumn(
            name="hypervisor",
            required=False,
            target="virtual_machine.hypervisor",
            type="string",
            unit=None,
            enum=None,
            description="Hypervisor name; empty = unknown (null)",
            example="KVM",
        ),
    ),
)

TEMPLATES: tuple[ImportTemplate, ...] = (_BM_TEMPLATE, _VM_TEMPLATE)

# VM capacity columns parsed as integers (the ``host`` column is resolved
# separately against pre-batch state).
_VM_CAPACITY_COLUMNS = ("vcpu", "memory_mb", "disk_gb")


@dataclass
class RowError:
    """One aggregated import row error (Contract §1.2)."""

    row: int
    field: str
    reason: str
    related_row: int | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "row": self.row,
            "field": self.field,
            "reason": self.reason,
            "related_row": self.related_row,
        }


@dataclass
class PreparedRow:
    """A validated import row ready to be staged."""

    row: int
    prepared: resource_service.PreparedResource


@dataclass
class ImportResult:
    """Outcome of parsing + row validation (create-phase independent)."""

    format: str
    total_rows: int
    prepared: list[PreparedRow] = field(default_factory=list)
    errors: list[RowError] = field(default_factory=list)

    @property
    def error_count(self) -> int:
        return len(self.errors)

    @property
    def error_rows(self) -> int:
        return len({error.row for error in self.errors})

    @property
    def importable_rows(self) -> int:
        return self.total_rows - self.error_rows


# --- template helpers -------------------------------------------------------


def templates_payload() -> list[dict[str, Any]]:
    """Serialise the frozen templates for ``GET /imports/resources/templates``."""
    payload: list[dict[str, Any]] = []
    for template in TEMPLATES:
        payload.append(
            {
                "resource_type": template.resource_type,
                "columns": [
                    {
                        "name": column.name,
                        "required": column.required,
                        "target": column.target,
                        "type": column.type,
                        "unit": column.unit,
                        "enum": list(column.enum) if column.enum is not None else None,
                        "description": column.description,
                        "example": column.example,
                    }
                    for column in template.columns
                ],
            }
        )
    return payload


# --- parsing ----------------------------------------------------------------


def _cell_text(value: Any) -> str:
    """Normalise a parsed CSV/xlsx cell to text (xlsx numbers are floats)."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if value.is_integer():
            return str(int(value))
        return repr(value)
    return str(value)


def _parse_csv(data: bytes) -> list[list[str]]:
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ImportInvalidFile("unreadable") from exc
    reader = csv.reader(io.StringIO(text, newline=""))
    return [[_cell_text(cell) for cell in row] for row in reader]


def _parse_xlsx(data: bytes) -> list[list[str]]:
    if not data.startswith(b"PK\x03\x04"):
        # Non-OOXML payload (.xls OLE2, plain text, ...).
        raise ImportInvalidFile("unsupported_format")
    try:
        from openpyxl import load_workbook
    except ImportError as exc:  # pragma: no cover - dependency guaranteed
        raise ImportInvalidFile("unsupported_format") from exc

    try:
        workbook = load_workbook(
            io.BytesIO(data), read_only=True, data_only=True
        )
    except Exception as exc:  # noqa: BLE001 - any xlsx corruption is user input
        raise ImportInvalidFile("unreadable") from exc
    try:
        if not workbook.worksheets:
            raise ImportInvalidFile("empty_file")
        worksheet = workbook.worksheets[0]
        return [
            [_cell_text(cell) for cell in row]
            for row in worksheet.iter_rows(values_only=True)
        ]
    finally:
        workbook.close()


def parse_records(data: bytes, fmt: str) -> list[list[str]]:
    """Parse CSV/xlsx bytes into logical rows (header is record 1)."""
    if not data:
        raise ImportInvalidFile("empty_file")
    return _parse_csv(data) if fmt == "csv" else _parse_xlsx(data)


def _resolve_template(header: list[str]) -> ImportTemplate:
    """Match the header row against a frozen template (DR-195/DR-198).

    Returns the exact-match template or raises :class:`ImportInvalidFile` with
    the precise reason/details.
    """
    if not header or all(cell == "" for cell in header):
        raise ImportInvalidFile("header_missing")

    for template in TEMPLATES:
        if header == template.names:
            return template

    header_set = set(header)
    if header_set == set(_BM_TEMPLATE.names) or header_set == set(_VM_TEMPLATE.names):
        raise ImportInvalidFile("column_order")

    def _diff(template: ImportTemplate) -> tuple[list[str], list[str]]:
        names = set(template.names)
        missing = [name for name in template.names if name not in header_set]
        unknown = [cell for cell in header if cell not in names]
        return missing, unknown

    bm_missing, bm_unknown = _diff(_BM_TEMPLATE)
    vm_missing, vm_unknown = _diff(_VM_TEMPLATE)
    if len(bm_missing) + len(bm_unknown) <= len(vm_missing) + len(vm_unknown):
        missing, unknown = bm_missing, bm_unknown
    else:
        missing, unknown = vm_missing, vm_unknown

    if unknown and not missing:
        raise ImportInvalidFile(
            "unknown_columns", unknown_columns=unknown
        )
    if missing and not unknown:
        raise ImportInvalidFile("missing_columns", missing_columns=missing)
    raise ImportInvalidFile(
        "unknown_columns", missing_columns=missing, unknown_columns=unknown
    )


# --- row helpers ------------------------------------------------------------


def _error_message(exc: AppError) -> str:
    fields = exc.details.get("fields") or []
    if fields:
        return str(fields[0].get("message") or exc.message)
    return exc.message


def _raw_field(exc: AppError) -> str | None:
    fields = exc.details.get("fields") or []
    if fields:
        return str(fields[0].get("field") or "") or None
    return None


def _template_field(raw: str | None) -> str:
    """Map a Service-Layer point path onto the frozen template column name."""
    if not raw:
        return "resource_type"
    if raw == "virtual_machine.host_resource_id":
        return "host"
    for prefix in ("hardware.", "virtual_machine."):
        if raw.startswith(prefix):
            return raw[len(prefix) :]
    return raw


def _parse_int(field_name: str, text: str) -> int:
    candidate = text.strip()
    if not _INT_RE.fullmatch(candidate):
        raise ValueError(f"{field_name} must be an integer")
    return int(candidate)


def _find_host(
    db: "Session", cluster_id: uuid.UUID, reference: str
) -> Resource | None:
    """Resolve a VM ``host`` cell to an undeleted same-cluster BARE_METAL row.

    Reads only committed/pre-batch state (validation runs before any insert in
    the batch), so a BARE_METAL row created earlier in this file is never a
    valid host (DR-205/I-9).
    """
    value = reference.strip()
    if not value:
        return None
    statement = select(Resource).where(Resource.cluster_id == cluster_id)
    try:
        host_id = uuid.UUID(value)
    except (ValueError, AttributeError, TypeError):
        host_id = None
    if host_id is not None:
        statement = statement.where(Resource.id == host_id)
    else:
        try:
            normalized = normalization.normalize_hostname(value)
        except AppError:
            return None
        statement = statement.where(
            Resource.hostname_key == normalization.hostname_key(normalized)
        )
    statement = statement.where(
        Resource.resource_type == BARE_METAL,
        Resource.deleted_at.is_(None),
    )
    return db.execute(statement).scalars().first()


# --- per-row validation -----------------------------------------------------


def _validate_record(
    db: "Session",
    template: ImportTemplate,
    cells: list[str],
    row: int,
    *,
    seen: dict[tuple[uuid.UUID, str], int],
    cluster_cache: dict[str, Any],
) -> tuple[PreparedRow | None, list[RowError]]:
    """Validate one data record; returns a prepared row or aggregated errors."""
    errors: list[RowError] = []

    def add(field_name: str, reason: str, related_row: int | None = None) -> None:
        errors.append(
            RowError(row=row, field=field_name, reason=reason, related_row=related_row)
        )

    n = len(template.columns)
    padded = list(cells) + [""] * (n - len(cells)) if len(cells) < n else list(cells)
    cell = {column.name: padded[index] for index, column in enumerate(template.columns)}

    # --- base scalars ---
    type_cell = cell["resource_type"].strip()
    if type_cell == "":
        add("resource_type", "resource_type is required")
    elif type_cell != template.resource_type:
        add(
            "resource_type",
            f"resource_type must be {template.resource_type}",
        )

    cluster = None
    cluster_ref = cell["cluster"].strip()
    if not cluster_ref:
        add("cluster", "cluster is required")
    elif cluster_ref in cluster_cache:
        cached = cluster_cache[cluster_ref]
        if isinstance(cached, AppError):
            add("cluster", _error_message(cached))
        else:
            cluster = cached
    else:
        try:
            cluster = cluster_service.resolve_cluster(db, cluster_ref)
        except AppError as exc:
            cluster_cache[cluster_ref] = exc
            add("cluster", _error_message(exc))
        else:
            cluster_cache[cluster_ref] = cluster

    hostname: str | None = None
    hostname_key: str | None = None
    hostname_ref = cell["hostname"]
    if not hostname_ref.strip():
        add("hostname", "hostname is required")
    else:
        try:
            hostname = normalization.normalize_hostname(hostname_ref)
            hostname_key = normalization.hostname_key(hostname)
        except AppError as exc:
            add("hostname", _error_message(exc))

    role = "OTHER"
    if cell["role"].strip():
        try:
            role = resource_service._validate_role(cell["role"].strip())
        except AppError as exc:
            add("role", _error_message(exc))

    status = "UNKNOWN"
    if cell["status"].strip():
        try:
            status = resource_service._validate_status(cell["status"].strip())
        except AppError as exc:
            add("status", _error_message(exc))

    # --- type-specific detail ---
    hardware_values: dict[str, Any] | None = None
    virtual_machine_values: dict[str, Any] | None = None

    if template.resource_type == BARE_METAL:
        hardware: dict[str, Any] = {}
        for column in template.columns:
            if not column.target.startswith("hardware."):
                continue
            text = cell[column.name]
            if not text.strip():
                continue
            if column.type == "integer":
                try:
                    hardware[column.name] = _parse_int(column.name, text)
                except ValueError as exc:
                    add(column.name, str(exc))
            else:
                hardware[column.name] = text
        try:
            hardware_values = resource_service.validate_hardware(
                hardware, partial=False
            )
        except AppError as exc:
            add(_template_field(_raw_field(exc)), _error_message(exc))
    else:
        vm: dict[str, Any] = {}
        host_ref = cell["host"].strip()
        host: Resource | None = None
        if not host_ref:
            add("host", "host is required")
        elif cluster is not None:
            host = _find_host(db, cluster.id, host_ref)
            if host is None:
                add(
                    "host",
                    "host must be an existing, undeleted BARE_METAL resource "
                    "in the same cluster",
                )
            else:
                vm["host_resource_id"] = host.id
        for column in template.columns:
            if column.name in _VM_CAPACITY_COLUMNS:
                text = cell[column.name]
                if not text.strip():
                    continue
                try:
                    vm[column.name] = _parse_int(column.name, text)
                except ValueError as exc:
                    add(column.name, str(exc))
            elif column.name == "hypervisor":
                text = cell[column.name]
                if text.strip():
                    vm["hypervisor"] = text
        if host is not None:
            try:
                virtual_machine_values = (
                    resource_service.validate_virtual_machine_values(
                        vm, partial=False
                    )
                )
            except AppError as exc:
                add(_template_field(_raw_field(exc)), _error_message(exc))
                virtual_machine_values = None
            if virtual_machine_values is not None:
                try:
                    resource_service.validate_virtual_machine(
                        db,
                        virtual_machine_values["host_resource_id"],
                        cluster_id=cluster.id,
                        lock=False,
                    )
                except AppError as exc:
                    add("host", _error_message(exc))
                    virtual_machine_values = None

    # --- existing conflict + intra-file duplicate (need cluster + key) ---
    if cluster is not None and hostname_key is not None:
        existing = db.execute(
            select(Resource.id).where(
                Resource.cluster_id == cluster.id,
                Resource.hostname_key == hostname_key,
                Resource.deleted_at.is_(None),
            )
        ).first()
        if existing is not None:
            add("hostname", "hostname already exists in this cluster")

        duplicate_row = seen.get((cluster.id, hostname_key))
        if duplicate_row is not None:
            add(
                "hostname",
                f"duplicate hostname within file (also at row {duplicate_row})",
                related_row=duplicate_row,
            )
        else:
            seen[(cluster.id, hostname_key)] = row

    if errors:
        return None, errors
    assert cluster is not None and hostname is not None and hostname_key is not None
    prepared = resource_service.PreparedResource(
        cluster=cluster,
        hostname=hostname,
        hostname_key=hostname_key,
        resource_type=template.resource_type,
        role=role,
        status=status,
        description=None,
        meta={},
        hardware=hardware_values,
        virtual_machine=virtual_machine_values,
    )
    return PreparedRow(row=row, prepared=prepared), []


# --- public service ---------------------------------------------------------


def parse_and_validate(
    db: "Session",
    data: bytes,
    fmt: str,
    *,
    max_file_bytes: int,
    max_rows: int,
) -> ImportResult:
    """Parse + validate a whole file; enforce the file/row caps (DR-196)."""
    if len(data) > max_file_bytes:
        raise ImportFileTooLarge(max_file_bytes)

    records = parse_records(data, fmt)
    if not records:
        raise ImportInvalidFile("empty_file")

    data_records = list(records[1:])
    # Drop trailing blank records (trailing newlines / xlsx used-range artifacts)
    # without shifting the 1-based file row numbers of real data rows.
    while data_records and all(cell == "" for cell in data_records[-1]):
        data_records.pop()
    # Row-count cap precedes header/column validation (Contract §2: parse ->
    # row limit -> header/columns -> per-row).
    if len(data_records) > max_rows:
        raise ImportRowLimitExceeded(max_rows)

    if not records[0] or all(cell == "" for cell in records[0]):
        raise ImportInvalidFile("header_missing")

    template = _resolve_template(records[0])
    if not data_records:
        raise ImportInvalidFile("empty_file")

    seen: dict[tuple[uuid.UUID, str], int] = {}
    cluster_cache: dict[str, Any] = {}
    result = ImportResult(format=fmt, total_rows=len(data_records))
    for index, record in enumerate(data_records):
        row_number = index + 2  # header is file row 1
        prepared, row_errors = _validate_record(
            db,
            template,
            record,
            row_number,
            seen=seen,
            cluster_cache=cluster_cache,
        )
        if prepared is not None:
            result.prepared.append(prepared)
        result.errors.extend(row_errors)
    return result


def validate_import(
    db: "Session", data: bytes, fmt: str, settings: "Settings"
) -> ImportResult:
    """Read-only pre-validate (Contract §3); no writes, no Audit, no locks."""
    return parse_and_validate(
        db,
        data,
        fmt,
        max_file_bytes=settings.import_max_file_bytes,
        max_rows=settings.import_max_rows,
    )


def result_payload(result: ImportResult, settings: "Settings") -> dict[str, Any]:
    """Render a pre-validate response body with a bounded error preview."""
    limit = settings.import_error_preview_limit
    truncated = result.error_count > limit
    errors = [error.as_dict() for error in result.errors[:limit]]
    return {
        "format": result.format,
        "total_rows": result.total_rows,
        "importable_rows": max(result.importable_rows, 0),
        "error_count": result.error_count,
        "errors": errors,
        "errors_truncated": truncated,
    }


def write_import(
    db: "Session",
    operator: "Operator | None",
    data: bytes,
    fmt: str,
    settings: "Settings",
) -> tuple[int, int]:
    """Validate then insert the batch atomically (Contract §4, DR-203).

    Returns ``(created, total_rows)`` on success. Any validation or
    concurrency/DB error rolls the whole batch back and raises
    :class:`ImportValidationFailed`.
    """
    result = parse_and_validate(
        db,
        data,
        fmt,
        max_file_bytes=settings.import_max_file_bytes,
        max_rows=settings.import_max_rows,
    )
    if result.errors:
        _raise_validation_failed(db, result, settings)

    created = 0
    runtime_errors: list[RowError] = []
    try:
        for prepared_row in result.prepared:
            try:
                with db.begin_nested():
                    vm_values = prepared_row.prepared.virtual_machine
                    if vm_values is not None:
                        # Re-check + lock the host inside the write transaction.
                        resource_service.validate_virtual_machine(
                            db,
                            vm_values["host_resource_id"],
                            cluster_id=prepared_row.prepared.cluster.id,
                            lock=True,
                        )
                    resource_service.stage_resource(
                        db, operator, prepared_row.prepared
                    )
            except IntegrityError as exc:
                runtime_errors.append(_attribute_integrity(prepared_row, exc))
            except AppError as exc:
                runtime_errors.append(
                    RowError(
                        row=prepared_row.row,
                        field="host",
                        reason=_error_message(exc),
                    )
                )
            else:
                created += 1

        if runtime_errors:
            db.rollback()
            failed = ImportResult(
                format=result.format,
                total_rows=result.total_rows,
                errors=runtime_errors,
            )
            _raise_validation_failed(db, failed, settings)
        db.commit()
    except AppError:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        raise
    return created, result.total_rows


def _attribute_integrity(prepared_row: PreparedRow, exc: IntegrityError) -> RowError:
    """Map a SAVEPOINT ``IntegrityError`` to the offending template column."""
    diag = getattr(getattr(exc, "orig", None), "diag", None)
    constraint = getattr(diag, "constraint_name", None) or ""
    text = f"{constraint} {exc}"
    if "uq_resources_cluster_id_hostname_key" in text:
        return RowError(
            row=prepared_row.row,
            field="hostname",
            reason="hostname already exists in this cluster",
        )
    if "host_valid" in text or "host_resource_id" in text:
        return RowError(
            row=prepared_row.row,
            field="host",
            reason=(
                "host must be an existing, undeleted BARE_METAL resource "
                "in the same cluster"
            ),
        )
    return RowError(
        row=prepared_row.row,
        field="resource_type",
        reason="resource write rejected by a database constraint",
    )


def _raise_validation_failed(
    db: "Session", result: ImportResult, settings: "Settings"
) -> None:
    payload = result_payload(result, settings)
    raise ImportValidationFailed(
        total_rows=payload["total_rows"],
        importable_rows=payload["importable_rows"],
        error_count=payload["error_count"],
        errors=payload["errors"],
        errors_truncated=payload["errors_truncated"],
    )