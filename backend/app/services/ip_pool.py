"""IPPool business service (Contract §2–§9, DR-102..DR-117).

All IPPool rules live here: name normalisation (``name_key`` ASCII folding),
address format / CIDR-containment / ordering checks, same-Network name
uniqueness and closed-interval range overlap detection (mapped to
``unique_conflict`` / ``range_overlap``), the RESERVED / Network-gateway
occupancy trigger conditions and field mapping (DR-110), list
filtering/sorting/pagination, optimistic-lock conditional UPDATE, soft delete /
restore (with the deterministic restore re-check priority) and the audit trail
(same Session, same commit). Routes only translate HTTP.

Concurrency (DR-109): create and any range/allocation-mode change, plus restore,
lock the owning ``networks`` row ``SELECT ... FOR UPDATE`` (``_lock_network``,
the F008/F010 cross-Feature protocol) before the address/overlap/occupancy
checks, so they serialise with a Network cidr/cluster change and with F010 IP
allocation. The ``uq_ip_pools_network_id_name_key`` partial unique index and
``excl_ip_pools_network_id_address_range`` exclusion constraint arbitrate
concurrent races atomically; the ``trg_ip_pools_cidr_contains`` trigger is the
CIDR-containment backstop.

Soft-delete semantics (Contract §5): the Session-level
``with_loader_criteria`` filter hides ``deleted_at IS NOT NULL`` rows by
default; callers opt in with ``include_deleted=True``.
"""

from __future__ import annotations

import ipaddress
import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy import func, select, text, update
from sqlalchemy.exc import IntegrityError

from app.core.config import get_settings
from app.core.errors import (
    AppError,
    Conflict,
    NotFound,
    ValidationError,
    VersionConflict,
)
from app.models.ip_pool import VALID_ALLOCATION_MODES, IPPool
from app.models.network import Network
from app.services import audit, ip_occupancy, normalization, scope_filters
from app.services import cluster as cluster_service
from app.services.network import _lock_network

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from app.core.auth import Operator

OBJECT_TYPE = "ip_pool"
DELETED_MODES = ("exclude", "include", "only")
SORT_FIELDS = (
    "name",
    "start_address",
    "end_address",
    "allocation_mode",
    "created_at",
    "updated_at",
)
ORDERS = ("asc", "desc")

_SORT_COLUMNS = {
    # Contract §4: ``sort=name`` orders by the normalisation key.
    "name": IPPool.name_key,
    "start_address": IPPool.start_address,
    "end_address": IPPool.end_address,
    "allocation_mode": IPPool.allocation_mode,
    "created_at": IPPool.created_at,
    "updated_at": IPPool.updated_at,
}


# --- helpers ----------------------------------------------------------------


def _field_error(field: str, message: str) -> ValidationError:
    return ValidationError(details={"fields": [{"field": field, "message": message}]})


def _validate_allocation_mode(value: Any) -> str:
    if value not in VALID_ALLOCATION_MODES:
        raise _field_error(
            "allocation_mode",
            "allocation_mode must be one of MANUAL, AUTO, RESERVED",
        )
    return value


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _query_options(include_deleted: bool) -> dict[str, Any]:
    return {"include_deleted": True} if include_deleted else {}


def _addr(value: Any) -> str:
    return str(value)


def _range_expr(start_address: str, end_address: str):
    """Build the closed ``int8range`` for the two host addresses (DB-D99).

    The integer mapping (``int(IPv4Address)``) is identical to the generated
    column's ``set_masklen(x, 32) - '0.0.0.0'::inet``; the third ``'[]'``
    argument makes both endpoints inclusive so shared endpoints overlap.
    """
    return func.int8range(
        int(ipaddress.IPv4Address(start_address)),
        int(ipaddress.IPv4Address(end_address)),
        text("'[]'"),
    )


def _load_network(db: "Session", network_id: uuid.UUID) -> Network | None:
    """Load a Network including soft-deleted rows (serialisation/lookup)."""
    return (
        db.execute(
            select(Network).where(Network.id == network_id),
            execution_options={"include_deleted": True},
        )
        .scalars()
        .first()
    )


def resolve_network(db: "Session", reference: Any, *, scope=None) -> Network:
    """Resolve a POST/PATCH ``network`` UUID to an undeleted Network (DR-107).

    The value must be a UUID; missing / non-UUID / nonexistent / soft-deleted all
    yield 422 with ``field:"network"``. The lookup includes soft-deleted rows so
    a deleted Network is reported as a field error rather than silently ignored.
    """
    if not isinstance(reference, str) or not reference.strip():
        raise _field_error("network", "network is required")
    value = reference.strip()
    try:
        network_id = uuid.UUID(value)
    except (ValueError, AttributeError, TypeError) as exc:
        raise _field_error("network", "network must be a valid UUID") from exc

    network = _load_network(db, network_id)
    if (
        network is None
        or network.deleted_at is not None
        or not scope_filters.normalize(scope).allows(network.cluster_id)
    ):
        raise _field_error("network", "network does not exist or is not selectable")
    return network


def _translate_integrity_error(exc: IntegrityError) -> AppError:
    """Map an unexpected database integrity failure to a clean app error.

    A ``uq_ip_pools_network_id_name_key`` violation is the documented concurrent
    same-name race (409 ``unique_conflict``); an
    ``excl_ip_pools_network_id_address_range`` violation is the concurrent
    overlap race (409 ``range_overlap``). The CIDR-containment trigger and any
    other CHECK/FK failure mean application validation and the database diverged
    and is surfaced as a clean 422 instead of an unhandled 500. The caller must
    have rolled back first.
    """
    diag = getattr(getattr(exc, "orig", None), "diag", None)
    constraint = getattr(diag, "constraint_name", None) or ""
    if "uq_ip_pools_network_id_name_key" in constraint or (
        "uq_ip_pools_network_id_name_key" in str(exc)
    ):
        return Conflict.unique_conflict("name")
    if "excl_ip_pools_network_id_address_range" in constraint or (
        "excl_ip_pools_network_id_address_range" in str(exc)
    ):
        return Conflict.range_overlap([], field="start_address")
    if "belong to the network CIDR" in str(exc) or "fn_ip_pools_cidr_contains" in str(
        exc
    ):
        return _field_error(
            "start_address",
            "start_address/end_address must belong to the network cidr",
        )
    return ValidationError(message="ip_pool write rejected by a database constraint")


def _overlaps(
    db: "Session",
    network_id: uuid.UUID,
    start_address: str,
    end_address: str,
    *,
    exclude_id: uuid.UUID | None = None,
) -> list[dict[str, Any]]:
    """Return undeleted pools in ``network_id`` whose closed range overlaps.

    ``&&`` on the generated ``int8range`` mirrors the
    ``excl_ip_pools_network_id_address_range`` exclusion constraint.
    """
    filters = [
        IPPool.network_id == network_id,
        IPPool.address_range.op("&&")(_range_expr(start_address, end_address)),
        IPPool.deleted_at.is_(None),
    ]
    if exclude_id is not None:
        filters.append(IPPool.id != exclude_id)
    rows = db.execute(
        select(
            IPPool.id,
            IPPool.name,
            IPPool.start_address,
            IPPool.end_address,
        ).where(*filters)
    ).all()
    return [
        {
            "object_type": "ip_pool",
            "object_id": str(row.id),
            "label": row.name,
            "start_address": _addr(row.start_address),
            "end_address": _addr(row.end_address),
        }
        for row in rows
    ]


def _raise_if_occupied(
    db: "Session",
    network_id: uuid.UUID,
    start_address: str,
    end_address: str,
    field: str,
) -> None:
    """Raise 409 ``address_in_use`` when the range holds undeleted IPs (DR-110)."""
    limit = get_settings().conflict_preview_limit
    result = ip_occupancy.check_occupancy(
        db, network_id, start_address, end_address, limit
    )
    total = int(result.get("total", 0))
    if total <= 0:
        return
    items = list(result.get("items", []))[:limit]
    raise Conflict.address_in_use(field, total, items, total > len(items))


def ip_pool_snapshot(ip_pool: IPPool) -> dict[str, Any]:
    """Whitelisted snapshot handed to :mod:`app.services.audit` (Contract §8)."""
    return {
        "network_id": str(ip_pool.network_id),
        "name": ip_pool.name,
        "start_address": _addr(ip_pool.start_address),
        "end_address": _addr(ip_pool.end_address),
        "allocation_mode": ip_pool.allocation_mode,
        "description": ip_pool.description,
    }


# --- Network reference checker registration (DR-116) ------------------------
# An undeleted IPPool blocks deletion / cidr / cluster changes of its Network
# (Contract §7, DR-108/DR-116). Pool deletion itself registers no checker: a
# Pool soft delete never checks IP-allocation sources (§21 exception).


def _undeleted_ip_pool_references(
    db: "Session", network_id: uuid.UUID
) -> list[dict]:
    rows = db.execute(
        select(IPPool.id, IPPool.name).where(
            IPPool.network_id == network_id,
            IPPool.deleted_at.is_(None),
        )
    ).all()
    return [
        {"object_type": "ip_pool", "object_id": str(row.id), "label": row.name}
        for row in rows
    ]


cluster_service.register_reference_checker("network", _undeleted_ip_pool_references)


# --- reads ------------------------------------------------------------------


def list_ip_pools(
    db: "Session",
    *,
    network_id: uuid.UUID | None = None,
    allocation_mode: str | None = None,
    q: str | None = None,
    deleted: str = "exclude",
    page: int = 1,
    page_size: int = 20,
    sort: str = "created_at",
    order: str = "desc",
    scope=None,
) -> tuple[list[IPPool], int]:
    """Return the visible page of ip pools plus the filtered total."""
    if deleted not in DELETED_MODES:
        raise _field_error("deleted", "deleted must be exclude, include or only")
    if sort not in SORT_FIELDS:
        raise _field_error("sort", "unsupported sort field")
    if order not in ORDERS:
        raise _field_error("order", "order must be asc or desc")
    if allocation_mode is not None:
        _validate_allocation_mode(allocation_mode)

    filters = [scope_filters.pool_predicate(scope)]
    if network_id is not None:
        filters.append(IPPool.network_id == network_id)
    if allocation_mode is not None:
        filters.append(IPPool.allocation_mode == allocation_mode)
    if q is not None and q.strip():
        # Case-insensitive substring on name (no pg_trgm); LIKE metacharacters
        # are escaped.
        pattern = f"%{_escape_like(q)}%"
        filters.append(IPPool.name.ilike(pattern, escape="\\"))
    if deleted == "only":
        filters.append(IPPool.deleted_at.is_not(None))

    include_deleted = deleted in ("include", "only")
    execution_options = _query_options(include_deleted)

    sort_column = _SORT_COLUMNS[sort]
    ordered = sort_column.desc() if order == "desc" else sort_column.asc()
    offset = (page - 1) * page_size

    statement = (
        select(IPPool)
        .where(*filters)
        .order_by(ordered, IPPool.id.asc())
        .offset(offset)
        .limit(page_size)
    )
    total_statement = select(func.count()).select_from(IPPool).where(*filters)

    items = list(
        db.execute(statement, execution_options=execution_options).scalars().all()
    )
    total = int(
        db.execute(total_statement, execution_options=execution_options).scalar_one()
    )
    return items, total


def get_ip_pool(
    db: "Session",
    ip_pool_id: uuid.UUID,
    *,
    include_deleted: bool = False,
    scope=None,
) -> IPPool | None:
    """Return an ip pool, hidden by the soft-delete filter unless requested."""
    statement = select(IPPool).where(
        IPPool.id == ip_pool_id, scope_filters.pool_predicate(scope)
    )
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


def list_activity(
    db: "Session",
    ip_pool_id: uuid.UUID,
    *,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list, int]:
    """Return this ip pool's audit rows (ascending by created_at then id)."""
    from app.models.audit_log import AuditLog

    filters = [
        AuditLog.object_type == OBJECT_TYPE,
        AuditLog.object_id == ip_pool_id,
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


def create_ip_pool(
    db: "Session",
    operator: "Operator | None",
    *,
    network: Any,
    name: str,
    start_address: str,
    end_address: str,
    allocation_mode: str = "MANUAL",
    description: str | None = None,
    scope=None,
) -> IPPool:
    """Create an IPPool; validated per Contract §6.2 order.

    body (422) -> network (422) -> lock networks row -> address format / family /
    CIDR containment / order (422) -> same-Network undeleted name uniqueness
    (409) -> closed-range overlap (409 ``range_overlap``) -> RESERVED occupancy
    (409 ``address_in_use``) -> write + CREATE Audit -> 201.
    """
    normalized_name = normalization.normalize_ip_pool_name(name)
    validated_mode = _validate_allocation_mode(allocation_mode)

    network_row = resolve_network(db, network, scope=scope)
    _lock_network(db, network_row.id)

    norm_start, norm_end = normalization.normalize_ip_pool_addresses(
        start_address, end_address, str(network_row.cidr)
    )

    name_key = normalization.ip_pool_name_key(normalized_name)
    duplicate = db.execute(
        select(IPPool.id).where(
            IPPool.network_id == network_row.id,
            IPPool.name_key == name_key,
            IPPool.deleted_at.is_(None),
        )
    ).first()
    if duplicate is not None:
        raise Conflict.unique_conflict("name")

    conflicts = _overlaps(db, network_row.id, norm_start, norm_end)
    if conflicts:
        raise Conflict.range_overlap(conflicts, field="start_address")

    if validated_mode == "RESERVED":
        _raise_if_occupied(
            db, network_row.id, norm_start, norm_end, "allocation_mode"
        )

    ip_pool = IPPool(
        network_id=network_row.id,
        name=normalized_name,
        name_key=name_key,
        start_address=norm_start,
        end_address=norm_end,
        allocation_mode=validated_mode,
        description=description,
    )
    db.add(ip_pool)
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
        object_id=ip_pool.id,
        before=None,
        after=ip_pool_snapshot(ip_pool),
    )
    db.commit()
    return ip_pool


def update_ip_pool(
    db: "Session",
    operator: "Operator | None",
    ip_pool_id: uuid.UUID,
    *,
    expected_version: int,
    changes: dict[str, Any],
    scope=None,
) -> IPPool:
    """Partial update with optimistic locking; ``network`` is immutable.

    Contract §6.4 order: visibility (404) -> version (409) -> lock networks row
    when the range/allocation-mode changes -> address format / CIDR containment /
    order (422) -> name uniqueness (409) -> overlap (409) -> RESERVED occupancy
    (409) -> write + UPDATE Audit -> 200.
    """
    ip_pool = get_ip_pool(db, ip_pool_id, scope=scope)
    if ip_pool is None:
        raise NotFound()
    if ip_pool.version != expected_version:
        raise VersionConflict(ip_pool.version)

    range_changed = "start_address" in changes or "end_address" in changes
    mode_changed = "allocation_mode" in changes
    if range_changed or mode_changed:
        _lock_network(db, ip_pool.network_id)

    current_start = _addr(ip_pool.start_address)
    current_end = _addr(ip_pool.end_address)
    current_mode = ip_pool.allocation_mode
    effective_start = current_start
    effective_end = current_end

    values: dict[str, Any] = {}

    if range_changed:
        network_row = _load_network(db, ip_pool.network_id)
        cidr = str(network_row.cidr) if network_row is not None else ""
        effective_start = changes.get("start_address", current_start)
        effective_end = changes.get("end_address", current_end)
        effective_start, effective_end = normalization.normalize_ip_pool_addresses(
            effective_start, effective_end, cidr
        )
        values["start_address"] = effective_start
        values["end_address"] = effective_end

    effective_mode = current_mode
    if mode_changed:
        effective_mode = _validate_allocation_mode(changes["allocation_mode"])
        values["allocation_mode"] = effective_mode

    if "name" in changes:
        normalized_name = normalization.normalize_ip_pool_name(changes["name"])
        name_key = normalization.ip_pool_name_key(normalized_name)
        duplicate = db.execute(
            select(IPPool.id).where(
                IPPool.network_id == ip_pool.network_id,
                IPPool.name_key == name_key,
                IPPool.deleted_at.is_(None),
                IPPool.id != ip_pool_id,
            )
        ).first()
        if duplicate is not None:
            raise Conflict.unique_conflict("name")
        values["name"] = normalized_name
        values["name_key"] = name_key

    if range_changed:
        conflicts = _overlaps(
            db,
            ip_pool.network_id,
            effective_start,
            effective_end,
            exclude_id=ip_pool_id,
        )
        if conflicts:
            field = "start_address" if "start_address" in changes else "end_address"
            raise Conflict.range_overlap(conflicts, field=field)

    # Occupancy trigger conditions and field mapping (DR-110).
    if effective_mode == "RESERVED":
        transition_to_reserved = mode_changed and current_mode != "RESERVED"
        if transition_to_reserved:
            _raise_if_occupied(
                db,
                ip_pool.network_id,
                effective_start,
                effective_end,
                "allocation_mode",
            )
        elif range_changed:
            current_start_int = int(ipaddress.IPv4Address(current_start))
            current_end_int = int(ipaddress.IPv4Address(current_end))
            new_start_int = int(ipaddress.IPv4Address(effective_start))
            new_end_int = int(ipaddress.IPv4Address(effective_end))
            if new_start_int < current_start_int:
                _raise_if_occupied(
                    db,
                    ip_pool.network_id,
                    effective_start,
                    effective_end,
                    "start_address",
                )
            elif new_end_int > current_end_int:
                _raise_if_occupied(
                    db,
                    ip_pool.network_id,
                    effective_start,
                    effective_end,
                    "end_address",
                )

    if "description" in changes:
        values["description"] = changes["description"]

    before = ip_pool_snapshot(ip_pool)
    values["version"] = IPPool.version + 1
    values["updated_at"] = func.now()

    try:
        result = db.execute(
            update(IPPool)
            .where(
                IPPool.id == ip_pool_id,
                IPPool.version == expected_version,
                IPPool.deleted_at.is_(None),
            )
            .values(**values)
        )
        if result.rowcount == 0:
            _raise_update_conflict(db, ip_pool_id)

        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise _translate_integrity_error(exc) from exc

    db.refresh(ip_pool)
    audit.record(
        db,
        operator,
        action="UPDATE",
        object_type=OBJECT_TYPE,
        object_id=ip_pool.id,
        before=before,
        after=ip_pool_snapshot(ip_pool),
    )
    db.commit()
    return ip_pool


def delete_ip_pool(
    db: "Session",
    operator: "Operator | None",
    ip_pool_id: uuid.UUID,
    *,
    expected_version: int,
    scope=None,
) -> None:
    """Soft delete (no cascade, no IP-source reference check; DR-108).

    Contract §6.5 order: object (404) -> version (409) -> soft delete.
    """
    ip_pool = get_ip_pool(db, ip_pool_id, scope=scope)
    if ip_pool is None:
        raise NotFound()
    if ip_pool.version != expected_version:
        raise VersionConflict(ip_pool.version)

    before = ip_pool_snapshot(ip_pool)
    result = db.execute(
        update(IPPool)
        .where(
            IPPool.id == ip_pool_id,
            IPPool.version == expected_version,
            IPPool.deleted_at.is_(None),
        )
        .values(
            deleted_at=func.now(),
            version=IPPool.version + 1,
            updated_at=func.now(),
        )
    )
    if result.rowcount == 0:
        _raise_update_conflict(db, ip_pool_id)

    db.flush()
    db.refresh(ip_pool)
    audit.record(
        db,
        operator,
        action="DELETE",
        object_type=OBJECT_TYPE,
        object_id=ip_pool.id,
        before=before,
        after=None,
    )
    db.commit()


def restore_ip_pool(
    db: "Session",
    operator: "Operator | None",
    ip_pool_id: uuid.UUID,
    *,
    expected_version: int,
    scope=None,
) -> IPPool:
    """Restore a soft-deleted IPPool (Contract §6.6).

    Deterministic priority: find incl. deleted (404) -> not deleted (409) ->
    version (409) -> name uniqueness (409) -> Network dependency (409
    ``dependency_deleted``) -> CIDR containment re-check (422) -> overlap (409
    ``range_overlap``) -> RESERVED occupancy (409 ``address_in_use``) -> restore.
    A failed restore never overwrites the newer object; name reuse precedes
    dependency/overlap failures.
    """
    ip_pool = get_ip_pool(db, ip_pool_id, include_deleted=True, scope=scope)
    if ip_pool is None:
        raise NotFound()
    if ip_pool.deleted_at is None:
        raise Conflict.not_deleted()
    if ip_pool.version != expected_version:
        raise VersionConflict(ip_pool.version)

    _lock_network(db, ip_pool.network_id)

    duplicate = db.execute(
        select(IPPool.id).where(
            IPPool.network_id == ip_pool.network_id,
            IPPool.name_key == ip_pool.name_key,
            IPPool.deleted_at.is_(None),
            IPPool.id != ip_pool_id,
        )
    ).first()
    if duplicate is not None:
        raise Conflict.unique_conflict("name")

    network = _load_network(db, ip_pool.network_id)
    if network is None or network.deleted_at is not None:
        raise Conflict.dependency_deleted(
            [{"object_type": "network", "object_id": str(ip_pool.network_id)}]
        )

    start = _addr(ip_pool.start_address)
    end = _addr(ip_pool.end_address)
    # Re-check the stored range against the (possibly changed) Network CIDR.
    normalization.normalize_ip_pool_addresses(start, end, str(network.cidr))

    conflicts = _overlaps(
        db, ip_pool.network_id, start, end, exclude_id=ip_pool_id
    )
    if conflicts:
        raise Conflict.range_overlap(conflicts, field="start_address")

    if ip_pool.allocation_mode == "RESERVED":
        _raise_if_occupied(
            db, ip_pool.network_id, start, end, "allocation_mode"
        )

    before = ip_pool_snapshot(ip_pool)
    try:
        result = db.execute(
            update(IPPool)
            .where(
                IPPool.id == ip_pool_id,
                IPPool.version == expected_version,
                IPPool.deleted_at.is_not(None),
            )
            .values(
                deleted_at=None,
                version=IPPool.version + 1,
                updated_at=func.now(),
            )
        )
        if result.rowcount == 0:
            _raise_update_conflict(db, ip_pool_id, include_deleted=True)

        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise _translate_integrity_error(exc) from exc

    db.refresh(ip_pool)
    audit.record(
        db,
        operator,
        action="RESTORE",
        object_type=OBJECT_TYPE,
        object_id=ip_pool.id,
        before=before,
        after=ip_pool_snapshot(ip_pool),
    )
    db.commit()
    return ip_pool


def _raise_update_conflict(
    db: "Session", ip_pool_id: uuid.UUID, *, include_deleted: bool = True
) -> None:
    """Translate a conditional-UPDATE rowcount of 0 into 404 or 409."""
    current_version = db.execute(
        select(IPPool.version).where(IPPool.id == ip_pool_id),
        execution_options=_query_options(include_deleted),
    ).scalar_one_or_none()
    if current_version is None:
        raise NotFound()
    raise VersionConflict(int(current_version))