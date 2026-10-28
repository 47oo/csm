"""Network business service (Contract §2–§9, DR-89..DR-101).

All Network rules live here: name normalisation (``name_key`` ASCII folding),
CIDR normalisation (native PostgreSQL ``cidr``), gateway value-domain checks,
Cluster resolution, same-Cluster name/CIDR conflict detection (mapped to
``unique_conflict`` / ``range_overlap``), list filtering/sorting/pagination,
optimistic-lock conditional UPDATE, soft delete / restore, the reference-checker
registry call point and the audit trail (same Session, same commit). Routes only
translate HTTP.

Concurrency (DR-96): a change to ``cidr``/``cluster`` and a soft delete lock the
``networks`` row ``SELECT ... FOR UPDATE`` before the reference check, so they
serialise with each other and with F009/F010 child-object creation (cross-Feature
protocol). The ``uq_networks_cluster_id_name_key`` partial unique index and the
``excl_networks_cluster_id_cidr`` exclusion constraint arbitrate concurrent
name/CIDR races atomically.

Soft-delete semantics (Contract §5): the Session-level
``with_loader_criteria`` filter hides ``deleted_at IS NOT NULL`` rows by default;
callers opt in with ``include_deleted=True``.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy import cast, func, select, update
from sqlalchemy.dialects.postgresql import CIDR
from sqlalchemy.exc import IntegrityError

from app.core.config import get_settings
from app.core.errors import (
    AppError,
    Conflict,
    NotFound,
    ValidationError,
    VersionConflict,
)
from app.models.cluster import Cluster
from app.models.network import VALID_NETWORK_STATUSES, Network
from app.services import audit, ip_occupancy, normalization, scope_filters
from app.services import cluster as cluster_service

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from app.core.auth import Operator

OBJECT_TYPE = "network"
DELETED_MODES = ("exclude", "include", "only")
SORT_FIELDS = ("name", "cidr", "status", "created_at", "updated_at")
ORDERS = ("asc", "desc")

_SORT_COLUMNS = {
    # Contract §4: ``sort=name`` orders by the normalisation key.
    "name": Network.name_key,
    "cidr": Network.cidr,
    "status": Network.status,
    "created_at": Network.created_at,
    "updated_at": Network.updated_at,
}


# --- helpers ----------------------------------------------------------------


def _field_error(field: str, message: str) -> ValidationError:
    return ValidationError(details={"fields": [{"field": field, "message": message}]})


def _validate_status(status: Any) -> str:
    if status not in VALID_NETWORK_STATUSES:
        raise _field_error("status", "status must be ACTIVE or INACTIVE")
    return status


def _validate_auto_allocate(value: Any) -> bool:
    if not isinstance(value, bool):
        raise _field_error("auto_allocate", "auto_allocate must be a boolean")
    return value


def _validate_metadata(metadata: Any) -> dict:
    if not isinstance(metadata, dict):
        raise _field_error("metadata", "metadata must be a JSON object")
    return metadata


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _query_options(include_deleted: bool) -> dict[str, Any]:
    return {"include_deleted": True} if include_deleted else {}


def _translate_integrity_error(exc: IntegrityError) -> AppError:
    """Map an unexpected database integrity failure to a clean app error.

    A ``uq_networks_cluster_id_name_key`` violation is the documented concurrent
    same-name race (409 ``unique_conflict``); an ``excl_networks_cluster_id_cidr``
    violation is the concurrent CIDR-overlap race (409 ``range_overlap``). Any
    other CHECK/FK failure means application validation and the database
    diverged and is surfaced as a clean 422 instead of an unhandled 500. The
    caller must have rolled back first.
    """
    diag = getattr(getattr(exc, "orig", None), "diag", None)
    constraint = getattr(diag, "constraint_name", None) or ""
    if "uq_networks_cluster_id_name_key" in constraint or (
        "uq_networks_cluster_id_name_key" in str(exc)
    ):
        return Conflict.unique_conflict("name")
    if "excl_networks_cluster_id_cidr" in constraint or (
        "excl_networks_cluster_id_cidr" in str(exc)
    ):
        return Conflict.range_overlap([])
    return ValidationError(message="network write rejected by a database constraint")


def _lock_network(db: "Session", network_id: uuid.UUID) -> None:
    """Lock the ``networks`` row ``FOR UPDATE`` (DR-96).

    Serialises a cidr/cluster change and a soft delete with each other and with
    F009/F010 child-object creation (which must take the same lock). The row is
    read including soft-deleted rows so a restore path can lock it too.
    """
    db.execute(
        select(Network.id)
        .where(Network.id == network_id)
        .with_for_update(),
        execution_options={"include_deleted": True},
    ).first()


def _overlaps(
    db: "Session",
    cluster_id: uuid.UUID,
    cidr: str,
    *,
    exclude_id: uuid.UUID | None = None,
) -> list[dict[str, Any]]:
    """Return undeleted Networks in ``cluster_id`` whose CIDR overlaps ``cidr``.

    ``&&`` uses the PostgreSQL core GiST ``cidr``/``inet`` operator class (same
    operator as the ``excl_networks_cluster_id_cidr`` exclusion constraint).
    """
    filters = [
        Network.cluster_id == cluster_id,
        Network.cidr.op("&&")(cast(cidr, CIDR)),
        Network.deleted_at.is_(None),
    ]
    if exclude_id is not None:
        filters.append(Network.id != exclude_id)
    rows = db.execute(
        select(Network.id, Network.name).where(*filters)
    ).all()
    return [
        {"object_type": "network", "object_id": str(row.id), "label": row.name}
        for row in rows
    ]


def network_snapshot(network: Network) -> dict[str, Any]:
    """Whitelisted snapshot handed to :mod:`app.services.audit` (Contract §8)."""
    return {
        "cluster_id": str(network.cluster_id),
        "name": network.name,
        "cidr": str(network.cidr) if network.cidr is not None else None,
        "gateway": str(network.gateway) if network.gateway is not None else None,
        "status": network.status,
        "auto_allocate": network.auto_allocate,
        "description": network.description,
        "metadata": network.meta,
    }


# --- reference checker registration (DR-96, initial empty set) ---------------
# F008 registers the Network reference-set call point used by delete / cidr /
# cluster changes. IPPool (F009) and IPAddress (F010) will append their own
# checkers for object_type "network"; until then the set is empty and must not
# produce false positives.


def _undeleted_network_child_references(
    db: "Session", network_id: uuid.UUID
) -> list[dict]:
    """F009/F010 reserved call point: no child tables exist in F008."""
    return []


cluster_service.register_reference_checker(
    "network", _undeleted_network_child_references
)


# --- reads ------------------------------------------------------------------


def list_networks(
    db: "Session",
    *,
    cluster_id: uuid.UUID | None = None,
    status: str | None = None,
    auto_allocate: bool | None = None,
    q: str | None = None,
    deleted: str = "exclude",
    page: int = 1,
    page_size: int = 20,
    sort: str = "created_at",
    order: str = "desc",
    scope=None,
) -> tuple[list[Network], int]:
    """Return the visible page of networks plus the filtered total."""
    if deleted not in DELETED_MODES:
        raise _field_error("deleted", "deleted must be exclude, include or only")
    if sort not in SORT_FIELDS:
        raise _field_error("sort", "unsupported sort field")
    if order not in ORDERS:
        raise _field_error("order", "order must be asc or desc")
    if status is not None:
        _validate_status(status)

    filters = [scope_filters.cluster_predicate(scope, Network.cluster_id)]
    if cluster_id is not None:
        filters.append(Network.cluster_id == cluster_id)
    if status is not None:
        filters.append(Network.status == status)
    if auto_allocate is not None:
        filters.append(Network.auto_allocate.is_(auto_allocate))
    if q is not None and q.strip():
        # Case-insensitive substring on name (no pg_trgm); LIKE metacharacters
        # are escaped.
        pattern = f"%{_escape_like(q)}%"
        filters.append(Network.name.ilike(pattern, escape="\\"))
    if deleted == "only":
        filters.append(Network.deleted_at.is_not(None))

    include_deleted = deleted in ("include", "only")
    execution_options = _query_options(include_deleted)

    sort_column = _SORT_COLUMNS[sort]
    ordered = sort_column.desc() if order == "desc" else sort_column.asc()
    offset = (page - 1) * page_size

    statement = (
        select(Network)
        .where(*filters)
        .order_by(ordered, Network.id.asc())
        .offset(offset)
        .limit(page_size)
    )
    total_statement = select(func.count()).select_from(Network).where(*filters)

    items = list(
        db.execute(statement, execution_options=execution_options).scalars().all()
    )
    total = int(
        db.execute(total_statement, execution_options=execution_options).scalar_one()
    )
    return items, total


def get_network(
    db: "Session",
    network_id: uuid.UUID,
    *,
    include_deleted: bool = False,
    scope=None,
) -> Network | None:
    """Return a network, hidden by the soft-delete filter unless requested."""
    statement = select(Network).where(
        Network.id == network_id,
        scope_filters.cluster_predicate(scope, Network.cluster_id),
    )
    return (
        db.execute(statement, execution_options=_query_options(include_deleted))
        .scalars()
        .first()
    )


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


def list_activity(
    db: "Session",
    network_id: uuid.UUID,
    *,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list, int]:
    """Return this network's audit rows (ascending by created_at then id)."""
    from app.models.audit_log import AuditLog

    filters = [
        AuditLog.object_type == OBJECT_TYPE,
        AuditLog.object_id == network_id,
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


def create_network(
    db: "Session",
    operator: "Operator | None",
    *,
    scope=None,
    cluster: Any,
    name: str,
    cidr: str,
    gateway: str | None = None,
    status: str = "ACTIVE",
    auto_allocate: bool = False,
    description: str | None = None,
    metadata: dict | None = None,
) -> Network:
    """Create a Network; validated per Contract §6.2 order.

    cluster (422) -> same-Cluster undeleted name uniqueness (409) -> cidr
    format / gateway boundary (422) -> cidr overlap (409 range_overlap) -> write
    + CREATE Audit -> 201.
    """
    normalized_name = normalization.normalize_network_name(name)
    validated_status = _validate_status(status)
    validated_auto = _validate_auto_allocate(auto_allocate)
    meta = _validate_metadata({} if metadata is None else metadata)

    cluster_row = cluster_service.resolve_cluster(db, cluster, scope=scope)

    name_key = normalization.network_name_key(normalized_name)
    duplicate = db.execute(
        select(Network.id).where(
            Network.cluster_id == cluster_row.id,
            Network.name_key == name_key,
            Network.deleted_at.is_(None),
        )
    ).first()
    if duplicate is not None:
        raise Conflict.unique_conflict("name")

    normalized_cidr = normalization.normalize_cidr(cidr)
    normalized_gateway = normalization.normalize_gateway(gateway, normalized_cidr)

    conflicts = _overlaps(db, cluster_row.id, normalized_cidr)
    if conflicts:
        raise Conflict.range_overlap(conflicts)

    network = Network(
        cluster_id=cluster_row.id,
        name=normalized_name,
        name_key=name_key,
        cidr=normalized_cidr,
        gateway=normalized_gateway,
        status=validated_status,
        auto_allocate=validated_auto,
        description=description,
        meta=meta,
    )
    db.add(network)
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
        object_id=network.id,
        before=None,
        after=network_snapshot(network),
    )
    db.commit()
    return network


def update_network(
    db: "Session",
    operator: "Operator | None",
    network_id: uuid.UUID,
    *,
    expected_version: int,
    changes: dict[str, Any],
    scope=None,
) -> Network:
    """Partial update with optimistic locking.

    Contract §6.4 order: visibility (404) -> version (409) -> target Cluster
    (422) -> name uniqueness (409) -> cidr/gateway (422) -> references (409) ->
    cidr overlap (409) -> write + UPDATE Audit -> 200. A cidr/cluster change
    locks the network row ``FOR UPDATE`` before the reference check (DR-96).
    """
    network = get_network(db, network_id, scope=scope)
    if network is None:
        raise NotFound()

    changing_location = "cidr" in changes or "cluster" in changes
    # A gateway change shares the ``_lock_network`` domain with F010 allocation
    # (Contract §7/DR-109) so the occupancy check serialises with it.
    if changing_location or "gateway" in changes:
        _lock_network(db, network_id)

    if network.version != expected_version:
        raise VersionConflict(network.version)

    target_cluster_id = network.cluster_id
    if "cluster" in changes:
        target_cluster_id = cluster_service.resolve_cluster(
            db, changes["cluster"], scope=scope
        ).id

    values: dict[str, Any] = {}

    # Name uniqueness re-check (against the target Cluster when it changes).
    if "name" in changes or "cluster" in changes:
        if "name" in changes:
            normalized_name = normalization.normalize_network_name(changes["name"])
            effective_name_key = normalization.network_name_key(normalized_name)
        else:
            normalized_name = None
            effective_name_key = network.name_key
        duplicate = db.execute(
            select(Network.id).where(
                Network.cluster_id == target_cluster_id,
                Network.name_key == effective_name_key,
                Network.deleted_at.is_(None),
                Network.id != network_id,
            )
        ).first()
        if duplicate is not None:
            raise Conflict.unique_conflict("name")
        if normalized_name is not None:
            values["name"] = normalized_name
            values["name_key"] = effective_name_key

    # CIDR / gateway (re-check the stored gateway when the CIDR changes).
    current_cidr = str(network.cidr) if network.cidr is not None else None
    new_cidr = current_cidr
    if "cidr" in changes:
        new_cidr = normalization.normalize_cidr(changes["cidr"])
        values["cidr"] = new_cidr
    new_gateway: str | None = (
        str(network.gateway) if network.gateway is not None else None
    )
    if "cidr" in changes or "gateway" in changes:
        new_gateway = normalization.normalize_gateway(
            changes["gateway"] if "gateway" in changes else network.gateway,
            new_cidr,
        )
        values["gateway"] = new_gateway

    if changing_location:
        references = cluster_service.check_references(db, OBJECT_TYPE, network_id)
        if references:
            raise Conflict.reference_exists(references)

    if changing_location:
        conflicts = _overlaps(
            db, target_cluster_id, new_cidr, exclude_id=network_id
        )
        if conflicts:
            raise Conflict.range_overlap(conflicts)

    # Network gateway occupancy hook (Contract §7, DR-109/DR-110): an explicit
    # non-null gateway change consults the occupancy provider; the F009 empty
    # set never triggers, F010 provides end-to-end data.
    if "gateway" in changes and new_gateway is not None:
        limit = get_settings().conflict_preview_limit
        occupancy = ip_occupancy.check_occupancy(
            db, network_id, new_gateway, new_gateway, limit
        )
        total = int(occupancy.get("total", 0))
        if total > 0:
            items = list(occupancy.get("items", []))[:limit]
            raise Conflict.address_in_use(
                "gateway", total, items, total > len(items)
            )

    if "cluster" in changes:
        values["cluster_id"] = target_cluster_id
    if "status" in changes:
        values["status"] = _validate_status(changes["status"])
    if "auto_allocate" in changes:
        values["auto_allocate"] = _validate_auto_allocate(changes["auto_allocate"])
    if "description" in changes:
        values["description"] = changes["description"]
    if "metadata" in changes:
        values["meta"] = _validate_metadata(changes["metadata"])

    before = network_snapshot(network)
    values["version"] = Network.version + 1
    values["updated_at"] = func.now()

    try:
        result = db.execute(
            update(Network)
            .where(
                Network.id == network_id,
                Network.version == expected_version,
                Network.deleted_at.is_(None),
            )
            .values(**values)
        )
        if result.rowcount == 0:
            _raise_update_conflict(db, network_id)

        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise _translate_integrity_error(exc) from exc

    db.refresh(network)
    audit.record(
        db,
        operator,
        action="UPDATE",
        object_type=OBJECT_TYPE,
        object_id=network.id,
        before=before,
        after=network_snapshot(network),
    )
    db.commit()
    return network


def delete_network(
    db: "Session",
    operator: "Operator | None",
    network_id: uuid.UUID,
    *,
    expected_version: int,
    scope=None,
) -> None:
    """Soft delete (no cascade); blocked by undeleted references (DR-96).

    Contract §6.5 order: object (404) -> version (409) -> references (409) ->
    soft delete. The network row is locked ``FOR UPDATE`` before the reference
    check so a concurrent F009/F010 child create serialises.
    """
    network = get_network(db, network_id, scope=scope)
    if network is None:
        raise NotFound()
    if network.version != expected_version:
        raise VersionConflict(network.version)

    _lock_network(db, network_id)

    references = cluster_service.check_references(db, OBJECT_TYPE, network_id)
    if references:
        raise Conflict.reference_exists(references)

    before = network_snapshot(network)
    result = db.execute(
        update(Network)
        .where(
            Network.id == network_id,
            Network.version == expected_version,
            Network.deleted_at.is_(None),
        )
        .values(
            deleted_at=func.now(),
            version=Network.version + 1,
            updated_at=func.now(),
        )
    )
    if result.rowcount == 0:
        _raise_update_conflict(db, network_id)

    db.flush()
    db.refresh(network)
    audit.record(
        db,
        operator,
        action="DELETE",
        object_type=OBJECT_TYPE,
        object_id=network.id,
        before=before,
        after=None,
    )
    db.commit()


def restore_network(
    db: "Session",
    operator: "Operator | None",
    network_id: uuid.UUID,
    *,
    expected_version: int,
    scope=None,
) -> Network:
    """Restore a soft-deleted Network.

    Contract §6.6 order: find incl. deleted (404) -> not deleted (409) ->
    version (409) -> name uniqueness (409) -> Cluster dependency (409
    ``dependency_deleted``) -> CIDR overlap (409 ``range_overlap``) -> restore.
    A failed restore never overwrites the newer object; name reuse takes
    precedence over dependency/overlap failures.
    """
    network = get_network(db, network_id, include_deleted=True, scope=scope)
    if network is None:
        raise NotFound()
    if network.deleted_at is None:
        raise Conflict.not_deleted()
    if network.version != expected_version:
        raise VersionConflict(network.version)

    duplicate = db.execute(
        select(Network.id).where(
            Network.cluster_id == network.cluster_id,
            Network.name_key == network.name_key,
            Network.deleted_at.is_(None),
            Network.id != network_id,
        )
    ).first()
    if duplicate is not None:
        raise Conflict.unique_conflict("name")

    cluster = (
        db.execute(
            select(Cluster).where(Cluster.id == network.cluster_id),
            execution_options={"include_deleted": True},
        )
        .scalars()
        .first()
    )
    if cluster is None or cluster.deleted_at is not None:
        raise Conflict.dependency_deleted(
            [{"object_type": "cluster", "object_id": str(network.cluster_id)}]
        )

    conflicts = _overlaps(
        db,
        network.cluster_id,
        str(network.cidr),
        exclude_id=network_id,
    )
    if conflicts:
        raise Conflict.range_overlap(conflicts)

    before = network_snapshot(network)
    try:
        result = db.execute(
            update(Network)
            .where(
                Network.id == network_id,
                Network.version == expected_version,
                Network.deleted_at.is_not(None),
            )
            .values(
                deleted_at=None,
                version=Network.version + 1,
                updated_at=func.now(),
            )
        )
        if result.rowcount == 0:
            _raise_update_conflict(db, network_id, include_deleted=True)

        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise _translate_integrity_error(exc) from exc

    db.refresh(network)
    audit.record(
        db,
        operator,
        action="RESTORE",
        object_type=OBJECT_TYPE,
        object_id=network.id,
        before=before,
        after=network_snapshot(network),
    )
    db.commit()
    return network


def _raise_update_conflict(
    db: "Session", network_id: uuid.UUID, *, include_deleted: bool = True
) -> None:
    """Translate a conditional-UPDATE rowcount of 0 into 404 or 409."""
    current_version = db.execute(
        select(Network.version).where(Network.id == network_id),
        execution_options=_query_options(include_deleted),
    ).scalar_one_or_none()
    if current_version is None:
        raise NotFound()
    raise VersionConflict(int(current_version))