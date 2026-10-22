"""F023 "resource + interface + IP" bulk import (Contract F023, DR-401..DR-431).

A third, *unified wide* template (26 columns, ``resource_type`` per row) layered
on the same Service Layer as the ordinary APIs:

* :func:`validate_import` — read-only, idempotent, no Audit/locks; aggregates
  every row error (row/field/reason, optional ``related_row``).
* :func:`write_import` — re-validates against the current transaction state and
  inserts inside a single transaction with per-resource ``begin_nested()``
  SAVEPOINTs; any error rolls the whole batch back (DR-419). Locks are taken
  once, in a fixed order (``resources`` before ``networks``, each by ascending
  id), *before* any SAVEPOINT (DR-421/F023-DB-01).

Parsing, header matching, caps and the ``RowError`` shape are the F014 primitives
(Contract §15); the resource + interface + IP rows are validated by the same
non-committing Service Layer cores (``prepare/stage_resource``,
``prepare/stage_interface``, ``prepare/stage_ip_address``) so import and API stay
consistent (A8/T71). There is no direct SQL/ORM bypass.
"""

from __future__ import annotations

import ipaddress
import uuid
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from sqlalchemy import cast, select
from sqlalchemy.dialects.postgresql import CIDR, INET
from sqlalchemy.exc import IntegrityError

from app.core.errors import (
    AppError,
    ImportFileTooLarge,
    ImportInvalidFile,
    ImportRowLimitExceeded,
    ImportValidationFailed,
    InternalError,
    ValidationError,
)
from app.models.cluster import Cluster
from app.models.ip_address import IPAddress
from app.models.network import Network
from app.models.resource import Resource
from app.services import interface as interface_service
from app.services import ip_address as ip_address_service
from app.services import ip_capacity
from app.services import normalization
from app.services import resource as resource_service
from app.services import resource_import
from app.services import scope_filters
from app.services.resource_import import (
    RowError,
    _error_message,
    _find_host,
    _parse_int,
    _raw_field,
    _template_field,
)

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from app.core.auth import Operator
    from app.core.config import Settings

BARE_METAL = "BARE_METAL"
VIRTUAL_MACHINE = "VIRTUAL_MACHINE"
TEMPLATE_KEY = "resource_interfaces_ips"

# Columns #11..#18 are BARE_METAL-only; #8 ``memory_mb`` is shared by both row
# types (Contract §6/§6.1) and is therefore *not* in this set.
BM_ONLY_HARDWARE_COLUMNS = (
    "manufacturer",
    "model",
    "serial_number",
    "cpu_model",
    "cpu_sockets",
    "cpu_cores",
    "gpu_model",
    "gpu_count",
)
BM_HARDWARE_COLUMNS = BM_ONLY_HARDWARE_COLUMNS + ("memory_mb",)
BM_INT_COLUMNS = ("cpu_sockets", "cpu_cores", "memory_mb", "gpu_count")
VM_ONLY_COLUMNS = ("host", "vcpu", "disk_gb", "hypervisor")
VM_INT_COLUMNS = ("vcpu", "memory_mb", "disk_gb")


@dataclass(frozen=True)
class UnifiedColumn:
    name: str
    required: bool
    applies_to: tuple[str, ...]
    target: str
    type: str
    description: str
    example: str
    unit: str | None = None
    enum: tuple[str, ...] | None = None


# Frozen 26-column template (Contract §6, D03).
COLUMNS: tuple[UnifiedColumn, ...] = (
    UnifiedColumn(
        "cluster", True, (BARE_METAL, VIRTUAL_MACHINE), "resource.cluster", "string",
        "Cluster code (case-insensitive) or UUID; must exist and be undeleted",
        "N96P",
    ),
    UnifiedColumn(
        "hostname", True, (BARE_METAL, VIRTUAL_MACHINE), "resource.hostname", "string",
        "Resource hostname; trimmed and ASCII-folded to lower case; unique per "
        "cluster among undeleted resources",
        "cn001",
    ),
    UnifiedColumn(
        "resource_type", True, (BARE_METAL, VIRTUAL_MACHINE), "resource.resource_type",
        "enum", "BARE_METAL or VIRTUAL_MACHINE; consistent within a hostname group",
        "BARE_METAL", enum=(BARE_METAL, VIRTUAL_MACHINE),
    ),
    UnifiedColumn(
        "role", False, (BARE_METAL, VIRTUAL_MACHINE), "resource.role", "enum",
        "Resource role; empty = OTHER", "COMPUTE",
        enum=("COMPUTE", "LOGIN", "MANAGEMENT", "STORAGE", "SERVICE", "GPU", "OTHER"),
    ),
    UnifiedColumn(
        "status", False, (BARE_METAL, VIRTUAL_MACHINE), "resource.status", "enum",
        "Resource status; empty = UNKNOWN", "IDLE",
        enum=("IDLE", "ALLOC", "DOWN", "UNKNOWN"),
    ),
    UnifiedColumn(
        "host", True, (VIRTUAL_MACHINE,), "virtual_machine.host_resource_id", "string",
        "VM only: hostname (or UUID) of an existing, undeleted BARE_METAL host in "
        "the same cluster; must exist before the batch; empty for BARE_METAL",
        "cn001",
    ),
    UnifiedColumn(
        "vcpu", False, (VIRTUAL_MACHINE,), "virtual_machine.vcpu", "integer",
        "VM only: vCPU count (positive integer); empty = unknown", "8",
    ),
    UnifiedColumn(
        "memory_mb", False, (BARE_METAL, VIRTUAL_MACHINE),
        "hardware.memory_mb / virtual_machine.memory_mb", "integer",
        "Memory (MiB, positive integer); mapped by row type; empty = unknown",
        "262144", unit="MiB",
    ),
    UnifiedColumn(
        "disk_gb", False, (VIRTUAL_MACHINE,), "virtual_machine.disk_gb", "integer",
        "VM only: disk capacity (GiB, non-negative; 0 = explicitly none); empty "
        "= unknown", "100", unit="GiB",
    ),
    UnifiedColumn(
        "hypervisor", False, (VIRTUAL_MACHINE,), "virtual_machine.hypervisor", "string",
        "VM only: hypervisor name; empty = unknown", "KVM",
    ),
    UnifiedColumn(
        "manufacturer", False, (BARE_METAL,), "hardware.manufacturer", "string",
        "BARE_METAL only: hardware manufacturer; empty = unknown", "Dell",
    ),
    UnifiedColumn(
        "model", False, (BARE_METAL,), "hardware.model", "string",
        "BARE_METAL only: hardware model; empty = unknown", "PowerEdge R750",
    ),
    UnifiedColumn(
        "serial_number", False, (BARE_METAL,), "hardware.serial_number", "string",
        "BARE_METAL only: hardware serial number; empty = unknown", "SN-12345",
    ),
    UnifiedColumn(
        "cpu_model", False, (BARE_METAL,), "hardware.cpu_model", "string",
        "BARE_METAL only: CPU model; empty = unknown", "Xeon Platinum 8358",
    ),
    UnifiedColumn(
        "cpu_sockets", False, (BARE_METAL,), "hardware.cpu_sockets", "integer",
        "BARE_METAL only: physical CPU sockets (positive integer); empty = unknown",
        "2",
    ),
    UnifiedColumn(
        "cpu_cores", False, (BARE_METAL,), "hardware.cpu_cores", "integer",
        "BARE_METAL only: physical CPU cores (positive integer, no "
        "hyper-threading); empty = unknown", "64",
    ),
    UnifiedColumn(
        "gpu_model", False, (BARE_METAL,), "hardware.gpu_model", "string",
        "BARE_METAL only: GPU model; empty = unknown", "A100",
    ),
    UnifiedColumn(
        "gpu_count", False, (BARE_METAL,), "hardware.gpu_count", "integer",
        "BARE_METAL only: GPU count (non-negative; 0 = explicitly none); empty "
        "= unknown", "8",
    ),
    UnifiedColumn(
        "name", True, (BARE_METAL, VIRTUAL_MACHINE), "interface.name", "string",
        "Interface name (case-sensitive, trimmed, no internal whitespace); unique "
        "per resource among undeleted interfaces", "eth0",
    ),
    UnifiedColumn(
        "interface_type", False, (BARE_METAL, VIRTUAL_MACHINE), "interface.interface_type",
        "enum", "Interface type; empty = OTHER (never inferred from name)", "PHYSICAL",
        enum=("PHYSICAL", "VIRTUAL", "BOND", "BRIDGE", "VLAN", "LOOPBACK", "OTHER"),
    ),
    UnifiedColumn(
        "mac_address", False, (BARE_METAL, VIRTUAL_MACHINE), "interface.mac_address",
        "string", "Interface MAC address (case preserved, no format regex); empty "
        "= unknown", "00:11:22:33:44:55",
    ),
    UnifiedColumn(
        "speed_mbps", False, (BARE_METAL, VIRTUAL_MACHINE), "interface.speed_mbps",
        "integer", "Interface speed (Mbps, positive integer); empty = unknown",
        "10000", unit="Mbps",
    ),
    UnifiedColumn(
        "mtu", False, (BARE_METAL, VIRTUAL_MACHINE), "interface.mtu", "integer",
        "Interface MTU (bytes, positive integer); empty = unknown", "9000",
        unit="bytes",
    ),
    UnifiedColumn(
        "enabled", False, (BARE_METAL, VIRTUAL_MACHINE), "interface.enabled", "boolean",
        "Interface enabled; true/false (case-insensitive) or 1/0; empty = true",
        "true",
    ),
    UnifiedColumn(
        "network", False, (BARE_METAL, VIRTUAL_MACHINE), "ip_address.network", "string",
        "Network name (case-insensitive) or CIDR in the same cluster; empty falls "
        "back to the ip /mask", "mgmt",
    ),
    UnifiedColumn(
        "ip", True, (BARE_METAL, VIRTUAL_MACHINE), "ip_address.address", "string",
        "IPv4 host address, optionally with /mask for network resolution; stored "
        "without the mask and must be allocatable in the resolved Network",
        "192.168.1.1/24",
    ),
)

COLUMN_NAMES: tuple[str, ...] = tuple(column.name for column in COLUMNS)
_COLUMN_NAME_SET = frozenset(COLUMN_NAMES)


# --- result -----------------------------------------------------------------


@dataclass
class UnifiedImportResult:
    """Outcome of parsing + row validation (create-phase independent)."""

    format: str
    total_rows: int
    rows: list["ParsedRow"] = field(default_factory=list)
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


@dataclass
class ParsedRow:
    """One individually-valid data row (before grouping/merging)."""

    row: int
    cluster: Cluster
    hostname: str
    hostname_key: str
    resource_type: str
    address: str
    network: Network
    name: str
    resource_cells: dict[str, Any]
    interface_cells: dict[str, Any]


@dataclass
class PreparedIPRow:
    row: int
    address: str
    network: Network


@dataclass
class PreparedInterfaceGroup:
    name: str
    interface_type: str
    mac_address: str | None
    speed_mbps: int | None
    mtu: int | None
    enabled: bool
    first_row: int
    ips: list[PreparedIPRow]


@dataclass
class PreparedGroup:
    cluster: Cluster
    prepared: resource_service.PreparedResource
    interfaces: list[PreparedInterfaceGroup]
    first_row: int


class _RowProblem(Exception):
    """Internal carrier for a resolved row field error."""

    def __init__(self, field: str, reason: str) -> None:
        super().__init__(reason)
        self.field = field
        self.reason = reason


# --- template ---------------------------------------------------------------


def templates_payload() -> dict[str, Any]:
    """Serialise the frozen unified template for the templates endpoint."""
    return {
        "key": TEMPLATE_KEY,
        "columns": [
            {
                "name": column.name,
                "required": column.required,
                "applies_to": list(column.applies_to),
                "target": column.target,
                "type": column.type,
                "unit": column.unit,
                "enum": list(column.enum) if column.enum is not None else None,
                "description": column.description,
                "example": column.example,
            }
            for column in COLUMNS
        ],
    }


# --- parsing / header -------------------------------------------------------


def _resolve_header(header: list[str]) -> None:
    """Strict header match against the frozen 26-column template (Contract §6)."""
    if not header or all(cell == "" for cell in header):
        raise ImportInvalidFile("header_missing")
    if header == list(COLUMN_NAMES):
        return
    header_set = set(header)
    if header_set == _COLUMN_NAME_SET:
        raise ImportInvalidFile("column_order")
    missing = [name for name in COLUMN_NAMES if name not in header_set]
    unknown = [cell for cell in header if cell not in _COLUMN_NAME_SET]
    if unknown and not missing:
        raise ImportInvalidFile("unknown_columns", unknown_columns=unknown)
    if missing and not unknown:
        raise ImportInvalidFile("missing_columns", missing_columns=missing)
    raise ImportInvalidFile(
        "unknown_columns", missing_columns=missing, unknown_columns=unknown
    )


def _cells_for(record: list[str]) -> dict[str, str]:
    padded = list(record) + [""] * (len(COLUMN_NAMES) - len(record))
    return {
        column.name: padded[index] for index, column in enumerate(COLUMNS)
    }


# --- network / ip resolution (Contract §9) ----------------------------------


def _parse_ip_cell(text: str) -> tuple[str, ipaddress.IPv4Network | None]:
    """Return ``(bare_host_address, network_hint)`` for the ``ip`` cell.

    A ``/mask`` form yields the network hint used for resolution; the stored
    address is always the bare host address (masklen=32, Contract §9).
    """
    value = text.strip()
    if not value:
        raise _RowProblem("ip", "ip is required")
    try:
        if "/" in value:
            interface = ipaddress.ip_interface(value)
            if interface.version != 4:
                raise ValueError(value)
            return str(interface.ip), interface.network
        address = ipaddress.ip_address(value)
        if address.version != 4:
            raise ValueError(value)
        return str(address), None
    except ValueError as exc:
        raise _RowProblem(
            "ip", "ip must be a valid IPv4 address (optionally with /mask)"
        ) from exc


def _match_network_by_cidr(
    db: "Session", cluster_id: uuid.UUID, cidr: str
) -> Network | None:
    return (
        db.execute(
            select(Network).where(
                Network.cluster_id == cluster_id,
                Network.cidr == cast(cidr, CIDR),
                Network.deleted_at.is_(None),
            )
        )
        .scalars()
        .first()
    )


def _resolve_network(
    db: "Session",
    cluster: Cluster,
    network_text: str,
    hint: ipaddress.IPv4Network | None,
) -> Network:
    """Resolve the row's Network (Contract §9); never creates one."""
    text = network_text.strip()
    if text:
        name_key = normalization.network_name_key(text)
        by_name = (
            db.execute(
                select(Network).where(
                    Network.cluster_id == cluster.id,
                    Network.name_key == name_key,
                    Network.deleted_at.is_(None),
                )
            )
            .scalars()
            .first()
        )
        if by_name is not None:
            return by_name
        try:
            cidr = normalization.normalize_cidr(text)
        except AppError as exc:
            raise _RowProblem(
                "network",
                "network must reference an existing network by name or CIDR in "
                "the same cluster",
            ) from exc
        by_cidr = _match_network_by_cidr(db, cluster.id, cidr)
        if by_cidr is not None:
            return by_cidr
        raise _RowProblem(
            "network", "network does not exist or is not selectable in this cluster"
        )
    if hint is None:
        raise _RowProblem("network", "network is required when ip has no /mask")
    by_hint = _match_network_by_cidr(db, cluster.id, str(hint))
    if by_hint is None:
        raise _RowProblem(
            "ip", "no existing network matches the ip /mask in this cluster"
        )
    return by_hint


# --- per-row validation -----------------------------------------------------


def _parse_bool(field_name: str, text: str) -> bool:
    value = text.strip().lower()
    if value in ("true", "1"):
        return True
    if value in ("false", "0"):
        return False
    raise _RowProblem(field_name, f"{field_name} must be true/false or 1/0")


def _validate_resource_type(text: str) -> str:
    return resource_service._validate_resource_type(text)


def _parse_row(
    db: "Session",
    record: list[str],
    row: int,
    cluster_cache: dict[str, Any],
    scope=None,
) -> tuple[ParsedRow | None, list[RowError]]:
    errors: list[RowError] = []

    def add(field_name: str, reason: str, related_row: int | None = None) -> None:
        errors.append(
            RowError(row=row, field=field_name, reason=reason, related_row=related_row)
        )

    cells = _cells_for(record)

    # --- resource_type (row type is per-row) ---
    resource_type: str | None = None
    rt_text = cells["resource_type"].strip()
    if not rt_text:
        add("resource_type", "resource_type is required")
    else:
        try:
            resource_type = _validate_resource_type(rt_text)
        except AppError as exc:
            add("resource_type", _error_message(exc))

    # --- cluster ---
    cluster: Cluster | None = None
    cluster_ref = cells["cluster"].strip()
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
            cluster = resource_service._resolve_cluster(db, cluster_ref)
        except AppError as exc:
            cluster_cache[cluster_ref] = exc
            add("cluster", _error_message(exc))
        else:
            if not scope_filters.normalize(scope).allows(cluster.id):
                error = ValidationError(
                    details={
                        "fields": [
                            {
                                "field": "cluster",
                                "message": "cluster does not exist or is not selectable",
                            }
                        ]
                    }
                )
                cluster_cache[cluster_ref] = error
                add("cluster", _error_message(error))
                cluster = None
            else:
                cluster_cache[cluster_ref] = cluster

    # --- hostname ---
    hostname: str | None = None
    hostname_key: str | None = None
    if not cells["hostname"].strip():
        add("hostname", "hostname is required")
    else:
        try:
            hostname = normalization.normalize_hostname(cells["hostname"])
            hostname_key = normalization.hostname_key(hostname)
        except AppError as exc:
            add("hostname", _error_message(exc))

    # --- interface name ---
    interface_name: str | None = None
    try:
        interface_name = normalization.normalize_interface_name(cells["name"])
    except AppError as exc:
        add("name", _error_message(exc))

    # --- network + ip (need the cluster) ---
    address: str | None = None
    network: Network | None = None
    if cluster is not None:
        try:
            address, hint = _parse_ip_cell(cells["ip"])
            network = _resolve_network(db, cluster, cells["network"], hint)
        except _RowProblem as problem:
            add(problem.field, problem.reason)
        if network is not None and not scope_filters.normalize(scope).allows(
            network.cluster_id
        ):
            add("network", "network does not exist or is not selectable in this cluster")
            network = None
        if network is not None and address is not None:
            if network.status != "ACTIVE":
                add("network", "network must be ACTIVE to receive new IP addresses")
            else:
                intervals = ip_capacity.network_allocatable_intervals(db, network)
                if not ip_capacity.interval_contains(intervals, address):
                    add(
                        "ip",
                        "ip is not allocatable in the resolved network "
                        "(cidr, network/broadcast, disabled, gateway or reserved range)",
                    )

    # --- resource-level detail ---
    resource_cells: dict[str, Any] = {}
    if resource_type is not None:
        resource_cells["resource_type"] = resource_type
        if cells["role"].strip():
            try:
                resource_cells["role"] = resource_service._validate_role(
                    cells["role"].strip()
                )
            except AppError as exc:
                add("role", _error_message(exc))
        if cells["status"].strip():
            try:
                resource_cells["status"] = resource_service._validate_status(
                    cells["status"].strip()
                )
            except AppError as exc:
                add("status", _error_message(exc))

        if resource_type == BARE_METAL:
            for column in VM_ONLY_COLUMNS:
                if cells[column].strip():
                    add(column, f"{column} is not applicable to BARE_METAL")
            hardware_raw: dict[str, Any] = {}
            for column in BM_HARDWARE_COLUMNS:
                text = cells[column]
                if not text.strip():
                    continue
                if column in BM_INT_COLUMNS:
                    try:
                        hardware_raw[column] = _parse_int(column, text)
                    except ValueError as exc:
                        add(column, str(exc))
                else:
                    hardware_raw[column] = text
            try:
                hardware = resource_service.validate_hardware(
                    hardware_raw, partial=False
                )
            except AppError as exc:
                add(_template_field(_raw_field(exc)), _error_message(exc))
            else:
                for column in hardware_raw:
                    resource_cells[column] = hardware[column]
        else:
            for column in BM_ONLY_HARDWARE_COLUMNS:
                if cells[column].strip():
                    add(column, f"{column} is not applicable to VIRTUAL_MACHINE")
            vm_raw: dict[str, Any] = {}
            host: Resource | None = None
            host_error = False
            host_ref = cells["host"].strip()
            if not host_ref:
                add("host", "host is required")
                host_error = True
            elif cluster is not None:
                host = _find_host(db, cluster.id, host_ref, scope=scope)
                if host is None:
                    add(
                        "host",
                        "host must be an existing, undeleted BARE_METAL resource "
                        "in the same cluster",
                    )
                    host_error = True
                else:
                    vm_raw["host_resource_id"] = host.id
                    resource_cells["host"] = host.id
            for column in VM_INT_COLUMNS:
                text = cells[column]
                if text.strip():
                    try:
                        vm_raw[column] = _parse_int(column, text)
                    except ValueError as exc:
                        add(column, str(exc))
            if cells["hypervisor"].strip():
                vm_raw["hypervisor"] = cells["hypervisor"]
            try:
                virtual_machine = resource_service.validate_virtual_machine_values(
                    vm_raw, partial=False
                )
            except AppError as exc:
                field_name = _template_field(_raw_field(exc))
                if not (host_error and field_name == "host"):
                    add(field_name, _error_message(exc))
            else:
                for column in vm_raw:
                    if column == "host_resource_id":
                        continue
                    resource_cells[column] = virtual_machine[column]
                if host is not None:
                    try:
                        resource_service.validate_virtual_machine(
                            db,
                            virtual_machine["host_resource_id"],
                            cluster_id=cluster.id,
                            lock=False,
                        )
                    except AppError as exc:
                        add("host", _error_message(exc))

    # --- interface-level detail ---
    interface_cells: dict[str, Any] = {}
    if cells["interface_type"].strip():
        try:
            interface_cells["interface_type"] = (
                interface_service._validate_interface_type(
                    cells["interface_type"].strip()
                )
            )
        except AppError as exc:
            add("interface_type", _error_message(exc))
    if cells["mac_address"].strip():
        try:
            interface_cells["mac_address"] = normalization.normalize_mac_address(
                cells["mac_address"]
            )
        except AppError as exc:
            add("mac_address", _error_message(exc))
    for column in ("speed_mbps", "mtu"):
        text = cells[column]
        if not text.strip():
            continue
        try:
            parsed = _parse_int(column, text)
        except ValueError as exc:
            add(column, str(exc))
            continue
        try:
            interface_cells[column] = interface_service._validate_positive_int(
                column, parsed
            )
        except AppError as exc:
            add(column, _error_message(exc))
    if cells["enabled"].strip():
        try:
            interface_cells["enabled"] = _parse_bool("enabled", cells["enabled"])
        except _RowProblem as problem:
            add(problem.field, problem.reason)

    # --- existing DB conflicts (batch-external snapshot) ---
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
    if cluster is not None and address is not None:
        existing_ip = db.execute(
            select(IPAddress.id).where(
                IPAddress.cluster_id == cluster.id,
                IPAddress.address == cast(address, INET),
                IPAddress.deleted_at.is_(None),
            )
        ).first()
        if existing_ip is not None:
            add("ip", "ip already exists in this cluster")

    if (
        errors
        or cluster is None
        or hostname is None
        or hostname_key is None
        or resource_type is None
        or address is None
        or network is None
        or interface_name is None
    ):
        return None, errors
    return (
        ParsedRow(
            row=row,
            cluster=cluster,
            hostname=hostname,
            hostname_key=hostname_key,
            resource_type=resource_type,
            address=address,
            network=network,
            name=interface_name,
            resource_cells=resource_cells,
            interface_cells=interface_cells,
        ),
        [],
    )


# --- grouping / merging -----------------------------------------------------


def _group_by_resource(rows: list[ParsedRow]) -> dict[tuple, list[ParsedRow]]:
    grouped: dict[tuple, list[ParsedRow]] = {}
    for row in rows:
        grouped.setdefault((row.cluster.id, row.hostname_key), []).append(row)
    return grouped


def _group_by_interface(rows: list[ParsedRow]) -> dict[str, list[ParsedRow]]:
    grouped: dict[str, list[ParsedRow]] = {}
    for row in rows:
        grouped.setdefault(row.name, []).append(row)
    return grouped


def _canonicalize(
    rows: list[ParsedRow], cells_attr: str
) -> tuple[dict[str, Any], list[tuple[int, str, int]]]:
    """Merge group cells; return canonical values + (row, field, related_row)."""
    canonical: dict[str, Any] = {}
    first_row: dict[str, int] = {}
    conflicts: list[tuple[int, str, int]] = []
    for row in rows:
        cells = getattr(row, cells_attr)
        for column, value in cells.items():
            if column not in canonical:
                canonical[column] = value
                first_row[column] = row.row
            elif canonical[column] != value:
                conflicts.append((row.row, column, first_row[column]))
    return canonical, conflicts


def _merge_and_check(rows: list[ParsedRow]) -> list[RowError]:
    """Intra-file duplicate + group consistency errors (Contract §8/§11)."""
    errors: list[RowError] = []

    seen_ip: dict[tuple, int] = {}
    for row in rows:
        key = (row.cluster.id, row.address)
        first = seen_ip.get(key)
        if first is not None:
            errors.append(
                RowError(
                    row=row.row,
                    field="ip",
                    reason=f"duplicate ip within file (also at row {first})",
                    related_row=first,
                )
            )
        else:
            seen_ip[key] = row.row

    for group_rows in _group_by_resource(rows).values():
        resource_type = group_rows[0].resource_type
        if any(row.resource_type != resource_type for row in group_rows):
            first_row = group_rows[0].row
            for row in group_rows:
                if row.resource_type != resource_type:
                    errors.append(
                        RowError(
                            row=row.row,
                            field="resource_type",
                            reason="resource_type conflicts within the resource group",
                            related_row=first_row,
                        )
                    )
            continue
        _, conflicts = _canonicalize(group_rows, "resource_cells")
        for row_number, column, related in conflicts:
            errors.append(
                RowError(
                    row=row_number,
                    field=column,
                    reason=f"{column} conflicts within the resource group",
                    related_row=related,
                )
            )
        for interface_rows in _group_by_interface(group_rows).values():
            _, interface_conflicts = _canonicalize(interface_rows, "interface_cells")
            for row_number, column, related in interface_conflicts:
                errors.append(
                    RowError(
                        row=row_number,
                        field=column,
                        reason=f"{column} conflicts within the interface group",
                        related_row=related,
                    )
                )
    return errors


def _build_groups(rows: list[ParsedRow]) -> list[PreparedGroup]:
    """Build the write plan (only called once no validation errors remain)."""
    groups: list[PreparedGroup] = []
    for group_rows in _group_by_resource(rows).values():
        canonical, _ = _canonicalize(group_rows, "resource_cells")
        resource_type = group_rows[0].resource_type
        if resource_type == BARE_METAL:
            hardware_raw = {
                column: canonical[column]
                for column in BM_HARDWARE_COLUMNS
                if column in canonical
            }
            hardware = resource_service.validate_hardware(hardware_raw, partial=False)
            virtual_machine = None
        else:
            vm_raw: dict[str, Any] = {}
            if "host" in canonical:
                vm_raw["host_resource_id"] = canonical["host"]
            for column in VM_INT_COLUMNS:
                if column in canonical:
                    vm_raw[column] = canonical[column]
            if "hypervisor" in canonical:
                vm_raw["hypervisor"] = canonical["hypervisor"]
            virtual_machine = resource_service.validate_virtual_machine_values(
                vm_raw, partial=False
            )
            hardware = None

        prepared = resource_service.PreparedResource(
            cluster=group_rows[0].cluster,
            hostname=group_rows[0].hostname,
            hostname_key=group_rows[0].hostname_key,
            resource_type=resource_type,
            role=canonical.get("role", "OTHER"),
            status=canonical.get("status", "UNKNOWN"),
            description=None,
            meta={},
            hardware=hardware,
            virtual_machine=virtual_machine,
        )

        interfaces: list[PreparedInterfaceGroup] = []
        for interface_rows in _group_by_interface(group_rows).values():
            interface_canonical, _ = _canonicalize(
                interface_rows, "interface_cells"
            )
            interfaces.append(
                PreparedInterfaceGroup(
                    name=interface_rows[0].name,
                    interface_type=interface_canonical.get("interface_type", "OTHER"),
                    mac_address=interface_canonical.get("mac_address"),
                    speed_mbps=interface_canonical.get("speed_mbps"),
                    mtu=interface_canonical.get("mtu"),
                    enabled=interface_canonical.get("enabled", True),
                    first_row=interface_rows[0].row,
                    ips=[
                        PreparedIPRow(
                            row=row.row, address=row.address, network=row.network
                        )
                        for row in interface_rows
                    ],
                )
            )
        groups.append(
            PreparedGroup(
                cluster=group_rows[0].cluster,
                prepared=prepared,
                interfaces=interfaces,
                first_row=group_rows[0].row,
            )
        )
    return groups


# --- public service ---------------------------------------------------------


def parse_and_validate(
    db: "Session",
    data: bytes,
    fmt: str,
    *,
    max_file_bytes: int,
    max_rows: int,
    scope=None,
) -> UnifiedImportResult:
    """Parse + validate the whole file; enforce caps and group consistency."""
    if len(data) > max_file_bytes:
        raise ImportFileTooLarge(max_file_bytes)

    records = resource_import.parse_records(data, fmt)
    if not records:
        raise ImportInvalidFile("empty_file")

    data_records = list(records[1:])
    while data_records and all(cell == "" for cell in data_records[-1]):
        data_records.pop()
    if len(data_records) > max_rows:
        raise ImportRowLimitExceeded(max_rows)

    _resolve_header(records[0])
    if not data_records:
        raise ImportInvalidFile("empty_file")

    cluster_cache: dict[str, Any] = {}
    rows: list[ParsedRow] = []
    errors: list[RowError] = []
    for index, record in enumerate(data_records):
        parsed, row_errors = _parse_row(
            db, record, index + 2, cluster_cache, scope=scope
        )
        if parsed is not None:
            rows.append(parsed)
        errors.extend(row_errors)
    errors.extend(_merge_and_check(rows))
    return UnifiedImportResult(
        format=fmt, total_rows=len(data_records), rows=rows, errors=errors
    )


def validate_import(
    db: "Session", data: bytes, fmt: str, settings: "Settings", *, scope=None
) -> UnifiedImportResult:
    """Read-only pre-validate (Contract §3); no writes, no Audit, no locks."""
    return parse_and_validate(
        db,
        data,
        fmt,
        max_file_bytes=settings.import_max_file_bytes,
        max_rows=settings.import_max_rows,
        scope=scope,
    )


def result_payload(result: UnifiedImportResult, settings: "Settings") -> dict[str, Any]:
    """Render a pre-validate/validation-failure body with a bounded preview."""
    return resource_import.result_payload(result, settings)


def _raise_validation_failed(
    result: UnifiedImportResult, settings: "Settings"
) -> None:
    payload = result_payload(result, settings)
    raise ImportValidationFailed(
        total_rows=payload["total_rows"],
        importable_rows=payload["importable_rows"],
        error_count=payload["error_count"],
        errors=payload["errors"],
        errors_truncated=payload["errors_truncated"],
    )


def _acquire_locks(db: "Session", groups: list[PreparedGroup]) -> None:
    """Deterministic lock order: ``resources`` then ``networks``, id ascending.

    Taken once, before any SAVEPOINT, so all batches acquire locks in the same
    order (DR-421 / F023-DB-01).
    """
    host_ids = sorted(
        group.prepared.virtual_machine["host_resource_id"]
        for group in groups
        if group.prepared.virtual_machine is not None
    )
    network_ids = sorted(
        iprow.network.id
        for group in groups
        for interface in group.interfaces
        for iprow in interface.ips
    )
    if host_ids:
        db.execute(
            select(Resource.id)
            .where(Resource.id.in_(host_ids))
            .order_by(Resource.id.asc())
            .with_for_update()
        )
    if network_ids:
        db.execute(
            select(Network.id)
            .where(Network.id.in_(network_ids))
            .order_by(Network.id.asc())
            .with_for_update()
        )


def _app_error_field(exc: AppError) -> str:
    raw = _raw_field(exc)
    if raw is None:
        # ``Conflict.unique_conflict(field=...)`` (e.g. the concurrent loser's
        # ``unique_conflict("address")``) sets ``details["field"]`` instead of
        # the ``details["fields"]`` point-path; fall back to it (F023 local).
        details = getattr(exc, "details", None)
        if isinstance(details, dict):
            field_value = details.get("field")
            if isinstance(field_value, str) and field_value:
                raw = field_value
    if raw is None:
        return "resource_type"
    mapped = {
        "address": "ip",
        "virtual_machine.host_resource_id": "host",
        "interface": "name",
    }
    return mapped.get(raw, _template_field(raw))


def _attribute_integrity(exc: IntegrityError, row: int) -> RowError:
    """Map a SAVEPOINT ``IntegrityError`` to the offending template column.

    UNIQUE/CHECK/FK use ``diag.constraint_name``; the ``fn/trg_ip_addresses_*``
    triggers raise without one and are attributed by RAISE message / SQLSTATE
    (Contract §12.5, F023-DB-02).
    """
    diag = getattr(getattr(exc, "orig", None), "diag", None)
    constraint = getattr(diag, "constraint_name", None) or ""
    text = f"{constraint} {exc}"
    if "uq_resources_cluster_id_hostname_key" in text:
        return RowError(
            row=row,
            field="hostname",
            reason="hostname already exists in this cluster",
        )
    if "uq_interfaces_resource_id_name" in text:
        return RowError(
            row=row,
            field="name",
            reason="interface name already exists on this resource",
        )
    if "uq_ip_addresses_cluster_id_address" in text:
        return RowError(
            row=row, field="ip", reason="ip already exists in this cluster"
        )
    if (
        "ck_ip_addresses_address_host" in text
        or "ck_ip_addresses_address_not_disabled" in text
    ):
        return RowError(
            row=row, field="ip", reason="ip rejected by the address boundary"
        )
    if "host_valid" in text or "host_resource_id" in text:
        return RowError(
            row=row,
            field="host",
            reason=(
                "host must be an existing, undeleted BARE_METAL resource in the "
                "same cluster"
            ),
        )
    if (
        "must equal the owning network cluster" in text
        or "fn_ip_addresses_cluster_consistent" in text
    ):
        return RowError(
            row=row, field="network", reason="network does not match the ip cluster"
        )
    if (
        "must belong to the owning network CIDR" in text
        or "must not be the network/broadcast address" in text
        or "fn_ip_addresses_cidr_contains" in text
    ):
        return RowError(
            row=row,
            field="ip",
            reason="ip is not allocatable in the resolved network",
        )
    if (
        "same cluster as the IP" in text
        or "fn_ip_addresses_interface_cluster" in text
        or "fk_ip_addresses_interface_id_interfaces" in text
    ):
        return RowError(
            row=row,
            field="name",
            reason="interface is not in the same cluster as the ip",
        )
    if (
        "fk_ip_addresses_network_id_networks" in text
        or "network_id" in text
    ):
        return RowError(
            row=row, field="network", reason="network reference is invalid"
        )
    if "fk_virtual_machine_details_host_resource_id" in text:
        return RowError(row=row, field="host", reason="host reference is invalid")
    if "resource_id" in text:
        return RowError(
            row=row, field="hostname", reason="resource reference is invalid"
        )
    return RowError(
        row=row,
        field="resource_type",
        reason="import write rejected by a database constraint",
    )


def _is_deadlock(exc: BaseException) -> bool:
    sqlstate = getattr(getattr(exc, "orig", None), "sqlstate", None) or getattr(
        getattr(exc, "orig", None), "pgcode", None
    )
    return sqlstate == "40P01"


def write_import(
    db: "Session",
    operator: "Operator | None",
    data: bytes,
    fmt: str,
    settings: "Settings",
    *,
    scope=None,
) -> tuple[int, int, int, int]:
    """Validate then insert the batch atomically (Contract §4, DR-419).

    Returns ``(created, interfaces_created, ip_addresses_created, total_rows)``.
    Any validation, concurrency or DB error rolls the whole batch back and
    raises :class:`ImportValidationFailed`; a residual deadlock (40P01) rolls
    back and raises 500 ``INTERNAL_ERROR`` without retrying (DR-421/F023-DB-01).
    """
    result = parse_and_validate(
        db,
        data,
        fmt,
        max_file_bytes=settings.import_max_file_bytes,
        max_rows=settings.import_max_rows,
        scope=scope,
    )
    if result.errors:
        _raise_validation_failed(result, settings)

    groups = _build_groups(result.rows)
    created = 0
    interfaces_created = 0
    ip_addresses_created = 0
    runtime_errors: list[RowError] = []
    try:
        _acquire_locks(db, groups)
        for group in groups:
            failure_row = group.first_row
            try:
                with db.begin_nested():
                    if group.prepared.virtual_machine is not None:
                        resource_service.validate_virtual_machine(
                            db,
                            group.prepared.virtual_machine["host_resource_id"],
                            cluster_id=group.cluster.id,
                            lock=False,
                        )
                    resource = resource_service.stage_resource(
                        db, operator, group.prepared
                    )
                    created += 1
                    for interface_group in group.interfaces:
                        failure_row = interface_group.first_row
                        prepared_interface = interface_service.prepare_interface(
                            db,
                            resource=resource.id,
                            name=interface_group.name,
                            interface_type=interface_group.interface_type,
                            mac_address=interface_group.mac_address,
                            speed_mbps=interface_group.speed_mbps,
                            mtu=interface_group.mtu,
                            enabled=interface_group.enabled,
                            description=None,
                            metadata=None,
                        )
                        interface = interface_service.stage_interface(
                            db, operator, prepared_interface
                        )
                        interfaces_created += 1
                        for iprow in interface_group.ips:
                            failure_row = iprow.row
                            prepared_ip = ip_address_service.prepare_ip_address(
                                db,
                                network=iprow.network,
                                address=iprow.address,
                                interface_id=interface.id,
                            )
                            ip_address_service.stage_ip_address(
                                db, operator, prepared_ip
                            )
                            ip_addresses_created += 1
            except IntegrityError as exc:
                runtime_errors.append(_attribute_integrity(exc, failure_row))
            except AppError as exc:
                runtime_errors.append(
                    RowError(
                        row=failure_row,
                        field=_app_error_field(exc),
                        reason=_error_message(exc),
                    )
                )

        if runtime_errors:
            db.rollback()
            failed = UnifiedImportResult(
                format=result.format,
                total_rows=result.total_rows,
                rows=[],
                errors=runtime_errors,
            )
            _raise_validation_failed(failed, settings)
        db.commit()
    except ImportValidationFailed:
        raise
    except AppError:
        db.rollback()
        raise
    except Exception as exc:  # noqa: BLE001 - classify then re-raise
        db.rollback()
        if _is_deadlock(exc):
            raise InternalError() from exc
        raise
    return created, interfaces_created, ip_addresses_created, result.total_rows