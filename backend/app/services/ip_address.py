"""IPAddress business service (Contract §2–§9, DR-118..DR-139).

All IPAddress rules live here: IPv4 host-address normalisation, the §11.1
allocatable-set boundary (CIDR containment, non network/broadcast, disabled 5
segments, gateway, RESERVED pool ranges) shared with capacity, manual allocation
(DR-124), automatic allocation (ascending order, exhaustion without switching,
DR-125), bind/unbind/transfer (DR-121/DR-136/DR-137), release (soft delete,
DR-128), restore re-checks, optimistic locking, the object Activity trail and the
audit whitelist (DR-131).

Concurrency (DR-126): manual/auto allocation and restore lock the owning
``networks`` row ``SELECT ... FOR UPDATE`` (``_lock_network``, the F008/F009
shared protocol) before the uniqueness/boundary checks, so they serialise with a
Network cidr/cluster change and with F009 RESERVED/gateway changes. The partial
unique index ``uq_ip_addresses_cluster_id_address`` is the atomic same-Cluster
backstop and the three BEFORE triggers are the cross-table backstop.

Soft-delete semantics (Contract §5): the Session-level ``with_loader_criteria``
filter hides ``deleted_at IS NOT NULL`` rows by default; callers opt in with
``include_deleted=True``.
"""

from __future__ import annotations

import ipaddress
import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy import cast, func, select, update
from sqlalchemy.dialects.postgresql import INET
from sqlalchemy.exc import IntegrityError

from app.core.errors import (
    AppError,
    Conflict,
    NotFound,
    ValidationError,
    VersionConflict,
)
from app.models.cluster import Cluster
from app.models.interface import Interface
from app.models.ip_address import IPAddress
from app.models.ip_pool import IPPool
from app.models.network import Network
from app.models.resource import Resource
from app.services import audit, ip_address_reference, ip_capacity, normalization
from app.services.network import _lock_network

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from app.core.auth import Operator

OBJECT_TYPE = "ip_address"
DELETED_MODES = ("exclude", "include", "only")
SORT_FIELDS = ("address", "created_at", "updated_at")
ORDERS = ("asc", "desc")

_SORT_COLUMNS = {
    "address": IPAddress.address,
    "created_at": IPAddress.created_at,
    "updated_at": IPAddress.updated_at,
}


# --- helpers ----------------------------------------------------------------


def _field_error(field: str, message: str) -> ValidationError:
    return ValidationError(details={"fields": [{"field": field, "message": message}]})


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _query_options(include_deleted: bool) -> dict[str, Any]:
    return {"include_deleted": True} if include_deleted else {}


def _addr(value: Any) -> str:
    return str(value)


def _load_network(db: "Session", network_id: uuid.UUID) -> Network | None:
    return (
        db.execute(
            select(Network).where(Network.id == network_id),
            execution_options={"include_deleted": True},
        )
        .scalars()
        .first()
    )


def resolve_network(db: "Session", reference: Any) -> Network:
    """Resolve a POST/PATCH ``network`` UUID to an undeleted Network (DR-107).

    Missing / non-UUID / nonexistent / soft-deleted all yield 422 with
    ``field:"network"``. The lookup includes soft-deleted rows so a deleted
    Network is reported as a field error rather than silently ignored.
    """
    if not isinstance(reference, str) or not reference.strip():
        raise _field_error("network", "network is required")
    value = reference.strip()
    try:
        network_id = uuid.UUID(value)
    except (ValueError, AttributeError, TypeError) as exc:
        raise _field_error("network", "network must be a valid UUID") from exc
    network = _load_network(db, network_id)
    if network is None or network.deleted_at is not None:
        raise _field_error("network", "network does not exist or is not selectable")
    return network


def resolve_ip_pool(
    db: "Session", reference: Any, *, network_id: uuid.UUID
) -> IPPool:
    """Resolve a POST ``ip_pool`` UUID to an undeleted Pool of ``network_id``.

    Missing / non-UUID / nonexistent / soft-deleted / belonging to another
    Network all yield 422 with ``field:"ip_pool"`` (Contract §6.3).
    """
    if not isinstance(reference, str) or not reference.strip():
        raise _field_error("ip_pool", "ip_pool is required")
    value = reference.strip()
    try:
        pool_id = uuid.UUID(value)
    except (ValueError, AttributeError, TypeError) as exc:
        raise _field_error("ip_pool", "ip_pool must be a valid UUID") from exc
    pool = (
        db.execute(
            select(IPPool).where(IPPool.id == pool_id),
            execution_options={"include_deleted": True},
        )
        .scalars()
        .first()
    )
    if (
        pool is None
        or pool.deleted_at is not None
        or pool.network_id != network_id
    ):
        raise _field_error(
            "ip_pool",
            "ip_pool does not exist, is not selectable or does not belong to "
            "the network",
        )
    return pool


def _validate_interface(
    db: "Session", interface_id: uuid.UUID, *, cluster_id: uuid.UUID
) -> Interface:
    """Validate a bound Interface: exists, undeleted, same Cluster (DR-121)."""
    interface = (
        db.execute(
            select(Interface).where(Interface.id == interface_id),
            execution_options={"include_deleted": True},
        )
        .scalars()
        .first()
    )
    if interface is None or interface.deleted_at is not None:
        raise _field_error(
            "interface", "interface does not exist or is not selectable"
        )
    resource = (
        db.execute(
            select(Resource).where(Resource.id == interface.resource_id),
            execution_options={"include_deleted": True},
        )
        .scalars()
        .first()
    )
    if resource is None or resource.deleted_at is not None:
        raise _field_error(
            "interface", "interface resource does not exist or is not selectable"
        )
    if resource.cluster_id != cluster_id:
        raise _field_error(
            "interface",
            "interface resource must be in the same cluster as the ip address",
        )
    return interface


def _validate_cidr_membership(address: str, network: Network) -> None:
    """Require ``address`` in the Network CIDR and not network/broadcast.

    Used by restore (which re-checks CRID membership but not gateway/RESERVED
    per Contract §6.7). Maps to 422 ``field:"address"``.
    """
    cidr = ipaddress.ip_network(str(network.cidr), strict=False)
    value = ipaddress.ip_address(address)
    if value not in cidr:
        raise _field_error("address", "address must belong to the network cidr")
    if cidr.prefixlen <= 30 and value in (
        cidr.network_address,
        cidr.broadcast_address,
    ):
        raise _field_error(
            "address", "address must not be the network/broadcast address"
        )


def _raise_address_not_allocatable() -> None:
    raise _field_error(
        "address",
        "address is not allocatable (cidr, network/broadcast, disabled, "
        "gateway or reserved range)",
    )


def _duplicate_exists(
    db: "Session", cluster_id: uuid.UUID, address: str, *, exclude_id: uuid.UUID | None = None
) -> bool:
    filters = [
        IPAddress.cluster_id == cluster_id,
        IPAddress.address == cast(address, INET),
        IPAddress.deleted_at.is_(None),
    ]
    if exclude_id is not None:
        filters.append(IPAddress.id != exclude_id)
    return db.execute(select(IPAddress.id).where(*filters)).first() is not None


def _derive_ip_pool_id(
    db: "Session", network_id: uuid.UUID, address: str
) -> uuid.UUID | None:
    """Return the undeleted Pool containing ``address`` (else ``None``)."""
    row = db.execute(
        select(IPPool.id)
        .where(
            IPPool.network_id == network_id,
            IPPool.deleted_at.is_(None),
            IPPool.start_address <= cast(address, INET),
            IPPool.end_address >= cast(address, INET),
        )
        .order_by(IPPool.start_address.asc(), IPPool.id.asc())
    ).first()
    return row[0] if row is not None else None


def _translate_integrity_error(exc: IntegrityError) -> AppError:
    """Map a database integrity failure to a clean app error (caller rolled back)."""
    diag = getattr(getattr(exc, "orig", None), "diag", None)
    constraint = getattr(diag, "constraint_name", None) or ""
    text = str(exc)
    if "uq_ip_addresses_cluster_id_address" in constraint or (
        "uq_ip_addresses_cluster_id_address" in text
    ):
        return Conflict.unique_conflict("address")
    if (
        "must equal the owning network cluster" in text
        or "fn_ip_addresses_cluster_consistent" in text
        or "must belong to the owning network CIDR" in text
        or "must not be the network/broadcast address" in text
        or "fn_ip_addresses_cidr_contains" in text
    ):
        return _field_error("address", "address rejected by the network boundary")
    if (
        "same cluster as the IP" in text
        or "fn_ip_addresses_interface_cluster" in text
    ):
        return _field_error(
            "interface", "interface resource must be in the same cluster"
        )
    return ValidationError(message="ip_address write rejected by a database constraint")


def ip_address_snapshot(ip_address: IPAddress) -> dict[str, Any]:
    """Whitelisted snapshot handed to :mod:`app.services.audit` (Contract §8)."""
    return {
        "network_id": str(ip_address.network_id),
        "cluster_id": str(ip_address.cluster_id),
        "address": _addr(ip_address.address),
        "interface_id": (
            str(ip_address.interface_id)
            if ip_address.interface_id is not None
            else None
        ),
        "ip_pool_id": (
            str(ip_address.ip_pool_id)
            if ip_address.ip_pool_id is not None
            else None
        ),
        "description": ip_address.description,
    }


def _first_available(
    segments: list[tuple[int, int]], occupied: list[int]
) -> int | None:
    """Return the lowest free integer in ``segments`` not in ``occupied``.

    ``occupied`` must be sorted ascending and unique. The walk advances a single
    pointer, so it is O(segments + occupied) and never enumerates a whole range.
    """
    index = 0
    for seg_lo, seg_hi in segments:
        candidate = seg_lo
        while candidate <= seg_hi:
            while index < len(occupied) and occupied[index] < candidate:
                index += 1
            if index < len(occupied) and occupied[index] == candidate:
                candidate += 1
                continue
            return candidate
    return None


# --- reads ------------------------------------------------------------------


def list_ip_addresses(
    db: "Session",
    *,
    network_id: uuid.UUID | None = None,
    cluster_id: uuid.UUID | None = None,
    interface_id: uuid.UUID | None = None,
    ip_pool_id: uuid.UUID | None = None,
    address: str | None = None,
    bound: bool | None = None,
    q: str | None = None,
    deleted: str = "exclude",
    page: int = 1,
    page_size: int = 20,
    sort: str = "created_at",
    order: str = "desc",
) -> tuple[list[IPAddress], int]:
    """Return the visible page of ip addresses plus the filtered total."""
    if deleted not in DELETED_MODES:
        raise _field_error("deleted", "deleted must be exclude, include or only")
    if sort not in SORT_FIELDS:
        raise _field_error("sort", "unsupported sort field")
    if order not in ORDERS:
        raise _field_error("order", "order must be asc or desc")

    filters = []
    if network_id is not None:
        filters.append(IPAddress.network_id == network_id)
    if cluster_id is not None:
        filters.append(IPAddress.cluster_id == cluster_id)
    if interface_id is not None:
        filters.append(IPAddress.interface_id == interface_id)
    if ip_pool_id is not None:
        filters.append(IPAddress.ip_pool_id == ip_pool_id)
    if address is not None:
        normalized = normalization.normalize_ip_address(address)
        filters.append(IPAddress.address == cast(normalized, INET))
    if bound is not None:
        if bound:
            filters.append(IPAddress.interface_id.is_not(None))
        else:
            filters.append(IPAddress.interface_id.is_(None))
    if q is not None and q.strip():
        pattern = f"%{_escape_like(q)}%"
        filters.append(func.host(IPAddress.address).ilike(pattern, escape="\\"))
    if deleted == "only":
        filters.append(IPAddress.deleted_at.is_not(None))

    include_deleted = deleted in ("include", "only")
    execution_options = _query_options(include_deleted)

    sort_column = _SORT_COLUMNS[sort]
    ordered = sort_column.desc() if order == "desc" else sort_column.asc()
    offset = (page - 1) * page_size

    statement = (
        select(IPAddress)
        .where(*filters)
        .order_by(ordered, IPAddress.id.asc())
        .offset(offset)
        .limit(page_size)
    )
    total_statement = select(func.count()).select_from(IPAddress).where(*filters)

    items = list(
        db.execute(statement, execution_options=execution_options).scalars().all()
    )
    total = int(
        db.execute(total_statement, execution_options=execution_options).scalar_one()
    )
    return items, total


def get_ip_address(
    db: "Session", ip_address_id: uuid.UUID, *, include_deleted: bool = False
) -> IPAddress | None:
    """Return an ip address, hidden by the soft-delete filter unless requested."""
    statement = select(IPAddress).where(IPAddress.id == ip_address_id)
    return (
        db.execute(statement, execution_options=_query_options(include_deleted))
        .scalars()
        .first()
    )


def networks_for(
    db: "Session", network_ids: list[uuid.UUID]
) -> dict[uuid.UUID, Network]:
    """Batch-load owning Networks (including soft-deleted) for serialisation."""
    ids = set(network_ids)
    if not ids:
        return {}
    rows = db.execute(
        select(Network).where(Network.id.in_(ids)),
        execution_options={"include_deleted": True},
    ).scalars().all()
    return {row.id: row for row in rows}


def clusters_for(
    db: "Session", cluster_ids: list[uuid.UUID]
) -> dict[uuid.UUID, Cluster]:
    """Batch-load owning Clusters (including soft-deleted) for serialisation."""
    ids = set(cluster_ids)
    if not ids:
        return {}
    rows = db.execute(
        select(Cluster).where(Cluster.id.in_(ids)),
        execution_options={"include_deleted": True},
    ).scalars().all()
    return {row.id: row for row in rows}


def interfaces_for(
    db: "Session", interface_ids: list[uuid.UUID | None]
) -> dict[uuid.UUID, Interface]:
    """Batch-load bound Interfaces (including soft-deleted) for serialisation."""
    ids = {iid for iid in interface_ids if iid is not None}
    if not ids:
        return {}
    rows = db.execute(
        select(Interface).where(Interface.id.in_(ids)),
        execution_options={"include_deleted": True},
    ).scalars().all()
    return {row.id: row for row in rows}


def resources_for(
    db: "Session", resource_ids: list[uuid.UUID]
) -> dict[uuid.UUID, Resource]:
    """Batch-load Interfaces' Resources (including soft-deleted)."""
    ids = set(resource_ids)
    if not ids:
        return {}
    rows = db.execute(
        select(Resource).where(Resource.id.in_(ids)),
        execution_options={"include_deleted": True},
    ).scalars().all()
    return {row.id: row for row in rows}


def ip_pools_for(
    db: "Session", ip_pool_ids: list[uuid.UUID | None]
) -> dict[uuid.UUID, IPPool]:
    """Batch-load allocation-source IPPools (including soft-deleted)."""
    ids = {pid for pid in ip_pool_ids if pid is not None}
    if not ids:
        return {}
    rows = db.execute(
        select(IPPool).where(IPPool.id.in_(ids)),
        execution_options={"include_deleted": True},
    ).scalars().all()
    return {row.id: row for row in rows}


def list_activity(
    db: "Session",
    ip_address_id: uuid.UUID,
    *,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list, int]:
    """Return this ip address's audit rows (ascending by created_at then id)."""
    from app.models.audit_log import AuditLog

    filters = [
        AuditLog.object_type == OBJECT_TYPE,
        AuditLog.object_id == ip_address_id,
    ]
    statement = (
        select(AuditLog)
        .where(*filters)
        .order_by(AuditLog.created_at.asc(), AuditLog.id.asc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    total_statement = select(func.count()).select_from(AuditLog).where(*filters)
    items = list(db.execute(statement).scalars().all())
    total = int(db.execute(total_statement).scalar_one())
    return items, total


# --- writes -----------------------------------------------------------------


def create_ip_address(
    db: "Session",
    operator: "Operator | None",
    *,
    network: Any,
    address: str,
    description: str | None = None,
) -> IPAddress:
    """Manual allocation (Contract §6.2 order, DR-124).

    body (422) -> network (422) -> lock networks row -> Network ACTIVE (409
    ``allocation_not_allowed``) -> address format/boundary (422) -> same-Cluster
    uniqueness (409 ``unique_conflict``) -> derive ``ip_pool`` -> write + CREATE
    Audit -> 201.
    """
    network_row = resolve_network(db, network)
    _lock_network(db, network_row.id)

    if network_row.status != "ACTIVE":
        raise Conflict.allocation_not_allowed("network_inactive")

    normalized = normalization.normalize_ip_address(address)
    intervals = ip_capacity.network_allocatable_intervals(db, network_row)
    if not ip_capacity.interval_contains(intervals, normalized):
        _raise_address_not_allocatable()

    if _duplicate_exists(db, network_row.cluster_id, normalized):
        raise Conflict.unique_conflict("address")

    ip_pool_id = _derive_ip_pool_id(db, network_row.id, normalized)

    ip_address = IPAddress(
        network_id=network_row.id,
        cluster_id=network_row.cluster_id,
        address=normalized,
        interface_id=None,
        ip_pool_id=ip_pool_id,
        description=description,
    )
    db.add(ip_address)
    try:
        db.flush()
    except IntegrityError as exc:  # concurrent create lost the race
        db.rollback()
        raise _translate_integrity_error(exc) from exc

    audit.record(
        db,
        operator,
        action="CREATE",
        object_type=OBJECT_TYPE,
        object_id=ip_address.id,
        before=None,
        after=ip_address_snapshot(ip_address),
    )
    db.commit()
    return ip_address


def auto_allocate_ip_address(
    db: "Session",
    operator: "Operator | None",
    *,
    network: Any,
    ip_pool: Any,
    description: str | None = None,
) -> IPAddress:
    """Automatic allocation (Contract §6.3 order, DR-125).

    body (422) -> network (422) -> lock networks row -> ACTIVE (409) -> ip_pool
    lookup (422) -> ``auto_allocate`` (409) -> ``allocation_mode=AUTO`` (409) ->
    ascending first free address -> exhaustion 409 ``no_available_address`` ->
    write + CREATE Audit -> 201.
    """
    network_row = resolve_network(db, network)
    _lock_network(db, network_row.id)

    if network_row.status != "ACTIVE":
        raise Conflict.allocation_not_allowed("network_inactive")

    pool = resolve_ip_pool(db, ip_pool, network_id=network_row.id)

    if not network_row.auto_allocate:
        raise Conflict.allocation_not_allowed("auto_allocate_disabled")
    if pool.allocation_mode != "AUTO":
        raise Conflict.allocation_not_allowed("pool_not_auto")

    intervals = ip_capacity.network_allocatable_intervals(db, network_row)
    pool_lo = int(ipaddress.IPv4Address(str(pool.start_address)))
    pool_hi = int(ipaddress.IPv4Address(str(pool.end_address)))
    segments = ip_capacity.intersect_with_range(intervals, pool_lo, pool_hi)

    occupied_rows = db.execute(
        select(IPAddress.address)
        .where(
            IPAddress.cluster_id == network_row.cluster_id,
            IPAddress.deleted_at.is_(None),
            IPAddress.address >= cast(str(pool.start_address), INET),
            IPAddress.address <= cast(str(pool.end_address), INET),
        )
        .order_by(IPAddress.address.asc())
    ).scalars().all()
    occupied = sorted(int(ipaddress.IPv4Address(str(value))) for value in occupied_rows)

    candidate = _first_available(segments, occupied)
    if candidate is None:
        raise Conflict.no_available_address(network_row.id, pool.id)

    normalized = str(ipaddress.IPv4Address(candidate))
    ip_address = IPAddress(
        network_id=network_row.id,
        cluster_id=network_row.cluster_id,
        address=normalized,
        interface_id=None,
        ip_pool_id=pool.id,
        description=description,
    )
    db.add(ip_address)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise _translate_integrity_error(exc) from exc

    audit.record(
        db,
        operator,
        action="CREATE",
        object_type=OBJECT_TYPE,
        object_id=ip_address.id,
        before=None,
        after=ip_address_snapshot(ip_address),
    )
    db.commit()
    return ip_address


def update_ip_address(
    db: "Session",
    operator: "Operator | None",
    ip_address_id: uuid.UUID,
    *,
    expected_version: int,
    changes: dict[str, Any],
) -> IPAddress:
    """Bind / unbind / transfer an Interface or edit ``description`` (§6.5).

    Order: visibility (404) -> version (409) -> interface validation (422) ->
    reference check on a binding change (409 ``reference_exists``) -> write +
    UPDATE Audit -> 200. Relationship edits are not restricted by Network
    INACTIVE (DR-136).
    """
    ip_address = get_ip_address(db, ip_address_id)
    if ip_address is None:
        raise NotFound()
    if ip_address.version != expected_version:
        raise VersionConflict(ip_address.version)

    values: dict[str, Any] = {}

    if "interface" in changes:
        new_interface = changes["interface"]
        if new_interface is not None:
            if not isinstance(new_interface, uuid.UUID):
                try:
                    new_interface = uuid.UUID(str(new_interface))
                except (ValueError, AttributeError, TypeError) as exc:
                    raise _field_error(
                        "interface", "interface must be a valid UUID"
                    ) from exc
            _validate_interface(
                db, new_interface, cluster_id=ip_address.cluster_id
            )
        if new_interface != ip_address.interface_id:
            references = ip_address_reference.check_ip_address_references(
                db, ip_address_id
            )
            if references:
                raise Conflict.reference_exists(references)
            values["interface_id"] = new_interface

    if "description" in changes:
        values["description"] = changes["description"]

    before = ip_address_snapshot(ip_address)
    values["version"] = IPAddress.version + 1
    values["updated_at"] = func.now()

    try:
        result = db.execute(
            update(IPAddress)
            .where(
                IPAddress.id == ip_address_id,
                IPAddress.version == expected_version,
                IPAddress.deleted_at.is_(None),
            )
            .values(**values)
        )
        if result.rowcount == 0:
            _raise_update_conflict(db, ip_address_id)

        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise _translate_integrity_error(exc) from exc

    db.refresh(ip_address)
    audit.record(
        db,
        operator,
        action="UPDATE",
        object_type=OBJECT_TYPE,
        object_id=ip_address.id,
        before=before,
        after=ip_address_snapshot(ip_address),
    )
    db.commit()
    return ip_address


def delete_ip_address(
    db: "Session",
    operator: "Operator | None",
    ip_address_id: uuid.UUID,
    *,
    expected_version: int,
) -> None:
    """Release = soft delete (Contract §6.6 order, DR-128).

    object (404) -> version (409) -> Endpoint reference check (409
    ``reference_exists``) -> soft delete. No cascade and no auto-unbind.
    """
    ip_address = get_ip_address(db, ip_address_id)
    if ip_address is None:
        raise NotFound()
    if ip_address.version != expected_version:
        raise VersionConflict(ip_address.version)

    references = ip_address_reference.check_ip_address_references(
        db, ip_address_id
    )
    if references:
        raise Conflict.reference_exists(references)

    before = ip_address_snapshot(ip_address)
    result = db.execute(
        update(IPAddress)
        .where(
            IPAddress.id == ip_address_id,
            IPAddress.version == expected_version,
            IPAddress.deleted_at.is_(None),
        )
        .values(
            deleted_at=func.now(),
            version=IPAddress.version + 1,
            updated_at=func.now(),
        )
    )
    if result.rowcount == 0:
        _raise_update_conflict(db, ip_address_id)

    db.flush()
    db.refresh(ip_address)
    audit.record(
        db,
        operator,
        action="DELETE",
        object_type=OBJECT_TYPE,
        object_id=ip_address.id,
        before=before,
        after=None,
    )
    db.commit()


def restore_ip_address(
    db: "Session",
    operator: "Operator | None",
    ip_address_id: uuid.UUID,
    *,
    expected_version: int,
) -> IPAddress:
    """Restore a soft-deleted IPAddress (Contract §6.7 order, DR-128).

    find incl. deleted (404) -> not deleted (409) -> version (409) -> lock
    networks row -> address uniqueness (409) -> Network/Interface dependency
    (409 ``dependency_deleted``) -> CIDR containment re-check (422) -> restore.
    A failed restore never overwrites the newer object; Network ACTIVE is not
    required (DR-136).
    """
    ip_address = get_ip_address(db, ip_address_id, include_deleted=True)
    if ip_address is None:
        raise NotFound()
    if ip_address.deleted_at is None:
        raise Conflict.not_deleted()
    if ip_address.version != expected_version:
        raise VersionConflict(ip_address.version)

    _lock_network(db, ip_address.network_id)

    if _duplicate_exists(
        db,
        ip_address.cluster_id,
        _addr(ip_address.address),
        exclude_id=ip_address_id,
    ):
        raise Conflict.unique_conflict("address")

    network = _load_network(db, ip_address.network_id)
    if (
        network is None
        or network.deleted_at is not None
        or network.cluster_id != ip_address.cluster_id
    ):
        raise Conflict.dependency_deleted(
            [{"object_type": "network", "object_id": str(ip_address.network_id)}]
        )

    if ip_address.interface_id is not None:
        interface = (
            db.execute(
                select(Interface).where(Interface.id == ip_address.interface_id),
                execution_options={"include_deleted": True},
            )
            .scalars()
            .first()
        )
        resource = None
        if interface is not None:
            resource = (
                db.execute(
                    select(Resource).where(Resource.id == interface.resource_id),
                    execution_options={"include_deleted": True},
                )
                .scalars()
                .first()
            )
        if (
            interface is None
            or interface.deleted_at is not None
            or resource is None
            or resource.deleted_at is not None
            or resource.cluster_id != ip_address.cluster_id
        ):
            raise Conflict.dependency_deleted(
                [
                    {
                        "object_type": "interface",
                        "object_id": str(ip_address.interface_id),
                    }
                ]
            )

    _validate_cidr_membership(_addr(ip_address.address), network)

    before = ip_address_snapshot(ip_address)
    try:
        result = db.execute(
            update(IPAddress)
            .where(
                IPAddress.id == ip_address_id,
                IPAddress.version == expected_version,
                IPAddress.deleted_at.is_not(None),
            )
            .values(
                deleted_at=None,
                version=IPAddress.version + 1,
                updated_at=func.now(),
            )
        )
        if result.rowcount == 0:
            _raise_update_conflict(db, ip_address_id, include_deleted=True)

        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise _translate_integrity_error(exc) from exc

    db.refresh(ip_address)
    audit.record(
        db,
        operator,
        action="RESTORE",
        object_type=OBJECT_TYPE,
        object_id=ip_address.id,
        before=before,
        after=ip_address_snapshot(ip_address),
    )
    db.commit()
    return ip_address


def _raise_update_conflict(
    db: "Session", ip_address_id: uuid.UUID, *, include_deleted: bool = True
) -> None:
    """Translate a conditional-UPDATE rowcount of 0 into 404 or 409."""
    current_version = db.execute(
        select(IPAddress.version).where(IPAddress.id == ip_address_id),
        execution_options=_query_options(include_deleted),
    ).scalar_one_or_none()
    if current_version is None:
        raise NotFound()
    raise VersionConflict(int(current_version))