"""Resource business service (Contract §4–§9, DR-34..DR-45; F005 hardware §2.4).

All Resource rules live here: cluster resolution, hostname normalisation, list
filtering/sorting/pagination, optimistic-lock conditional UPDATE, soft delete /
restore, uniqueness re-checks, the cluster reference/dependency checkers, the
BareMetal ``hardware`` 1:1 detail upsert (same transaction) and the audit trail
(same Session, same commit). Routes only translate HTTP.

Soft-delete semantics (Contract §5): the Session-level ``with_loader_criteria``
filter hides ``deleted_at IS NOT NULL`` rows by default; callers opt in with
``include_deleted=True``.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy import false, func, select, update
from sqlalchemy.exc import IntegrityError

from app.core.errors import (
    AppError,
    Conflict,
    NotFound,
    ValidationError,
    VersionConflict,
)
from app.models.bare_metal_detail import (
    INT_FIELDS,
    NON_NEGATIVE_INT_FIELDS,
    POSITIVE_INT_FIELDS,
    STRING_FIELDS,
    BareMetalDetail,
)
from app.models.cluster import Cluster
from app.models.resource import Resource
from app.services import audit, normalization
from app.services import cluster as cluster_service

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from app.core.auth import Operator

OBJECT_TYPE = "resource"
VALID_RESOURCE_TYPES = ("BARE_METAL", "VIRTUAL_MACHINE")
VALID_ROLES = ("COMPUTE", "LOGIN", "MANAGEMENT", "STORAGE", "SERVICE", "GPU", "OTHER")
VALID_STATUSES = ("IDLE", "ALLOC", "DOWN", "UNKNOWN")
DELETED_MODES = ("exclude", "include", "only")
SORT_FIELDS = ("hostname", "resource_type", "role", "status", "created_at", "updated_at")
ORDERS = ("asc", "desc")

# BareMetal hardware (Contract §2.4, D01 §5.4, DB-D46).
HARDWARE_INT_MAX = 2147483647

_SORT_COLUMNS = {
    "hostname": Resource.hostname_key,
    "resource_type": Resource.resource_type,
    "role": Resource.role,
    "status": Resource.status,
    "created_at": Resource.created_at,
    "updated_at": Resource.updated_at,
}


# --- helpers ----------------------------------------------------------------


def _field_error(field: str, message: str) -> ValidationError:
    return ValidationError(details={"fields": [{"field": field, "message": message}]})


def _validate_resource_type(resource_type: Any) -> str:
    if resource_type not in VALID_RESOURCE_TYPES:
        raise _field_error(
            "resource_type",
            "resource_type must be BARE_METAL or VIRTUAL_MACHINE",
        )
    return resource_type


def _validate_role(role: Any) -> str:
    if role not in VALID_ROLES:
        raise _field_error(
            "role",
            "role must be one of COMPUTE, LOGIN, MANAGEMENT, STORAGE, "
            "SERVICE, GPU, OTHER",
        )
    return role


def _validate_status(status: Any) -> str:
    if status not in VALID_STATUSES:
        raise _field_error("status", "status must be IDLE, ALLOC, DOWN or UNKNOWN")
    return status


def _validate_metadata(metadata: Any) -> dict:
    if not isinstance(metadata, dict):
        raise _field_error("metadata", "metadata must be a JSON object")
    return metadata


def _validate_hardware_int(field: str, value: Any, *, minimum: int) -> int | None:
    """Strict integer range check; ``bool`` is not an ``int`` here."""
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise _field_error(field, f"{field} must be an integer")
    if value < minimum or value > HARDWARE_INT_MAX:
        raise _field_error(
            field, f"{field} must be between {minimum} and {HARDWARE_INT_MAX}"
        )
    return value


def validate_hardware(hardware: dict, *, partial: bool) -> dict[str, Any]:
    """Validate/normalise a hardware object.

    ``partial=False`` (create) fills every absent field with ``None`` and an
    absent ``metadata`` with ``{}``; ``partial=True`` (PATCH) keeps only the keys
    the caller actually supplied, so omitted sub-fields are preserved. Empty
    strings/whitespace, ``cpu_sockets``/``cpu_cores``/``memory_mb`` <= 0 and
    ``gpu_count`` < 0 all raise 422 ``VALIDATION_ERROR`` with a
    ``hardware.<field>`` path.
    """
    if not isinstance(hardware, dict):
        raise _field_error("hardware", "hardware must be a JSON object")

    values: dict[str, Any] = {}
    for field in STRING_FIELDS:
        if field not in hardware:
            if not partial:
                values[field] = None
            continue
        value = hardware[field]
        values[field] = (
            None
            if value is None
            else normalization.validate_hardware_string(f"hardware.{field}", value)
        )
    for field in POSITIVE_INT_FIELDS:
        if field not in hardware:
            if not partial:
                values[field] = None
            continue
        values[field] = _validate_hardware_int(
            f"hardware.{field}", hardware[field], minimum=1
        )
    for field in NON_NEGATIVE_INT_FIELDS:
        if field not in hardware:
            if not partial:
                values[field] = None
            continue
        values[field] = _validate_hardware_int(
            f"hardware.{field}", hardware[field], minimum=0
        )

    if "metadata" not in hardware:
        if not partial:
            values["metadata"] = {}
    else:
        metadata = hardware["metadata"]
        if not isinstance(metadata, dict):
            raise _field_error(
                "hardware.metadata", "hardware.metadata must be a JSON object"
            )
        values["metadata"] = metadata
    return values


def _hardware_snapshot(resource: Resource) -> dict[str, Any] | None:
    """Audit snapshot for the nested ``hardware`` field (VM -> None)."""
    if resource.resource_type != "BARE_METAL":
        return None
    detail = resource.bare_metal_detail
    if detail is None:
        return {**{field: None for field in STRING_FIELDS + INT_FIELDS}, "metadata": {}}
    return {
        **{field: getattr(detail, field) for field in STRING_FIELDS + INT_FIELDS},
        "metadata": detail.meta,
    }


def resource_snapshot(resource: Resource) -> dict[str, Any]:
    """Whitelisted snapshot handed to :mod:`app.services.audit`.

    ``cluster_id`` is stringified so the JSONB snapshot stays JSON-serialisable.
    ``hardware`` is a nested object for BARE_METAL and ``null`` for VMs (F005 §8).
    """
    return {
        "cluster_id": str(resource.cluster_id),
        "hostname": resource.hostname,
        "resource_type": resource.resource_type,
        "role": resource.role,
        "status": resource.status,
        "description": resource.description,
        "metadata": resource.meta,
        "hardware": _hardware_snapshot(resource),
    }


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _query_options(include_deleted: bool) -> dict[str, Any]:
    return {"include_deleted": True} if include_deleted else {}


def _translate_integrity_error(exc: IntegrityError) -> AppError:
    """Map an unexpected database integrity failure to a clean app error.

    A ``uq_resources_cluster_id_hostname_key`` partial-unique violation is the
    documented concurrent-create race and becomes 409
    ``Conflict{unique_conflict, field:"hostname"}``. Any other CHECK/FK/trigger
    failure means application validation and the database diverged; it is
    surfaced as a clean 422 instead of an unhandled 500. The caller must have
    rolled back first.
    """
    diag = getattr(getattr(exc, "orig", None), "diag", None)
    constraint = getattr(diag, "constraint_name", None) or ""
    if "uq_resources_cluster_id_hostname_key" in constraint or (
        "uq_resources_cluster_id_hostname_key" in str(exc)
    ):
        return Conflict.unique_conflict("hostname")
    return ValidationError(message="resource write rejected by a database constraint")


def _resolve_cluster(db: "Session", reference: Any) -> Cluster:
    """Resolve a POST ``cluster`` (UUID or code) to an undeleted Cluster.

    Missing/nonexistent/soft-deleted all yield 422 with ``field:"cluster"``
    (Contract §6.2). The lookup deliberately includes soft-deleted rows so a
    deleted cluster is reported as a field error rather than silently ignored.
    """
    if not isinstance(reference, str) or not reference.strip():
        raise _field_error("cluster", "cluster is required")

    value = reference.strip()
    cluster: Cluster | None = None
    try:
        cluster_id = uuid.UUID(value)
    except (ValueError, AttributeError, TypeError):
        cluster_id = None

    if cluster_id is not None:
        cluster = db.execute(
            select(Cluster).where(Cluster.id == cluster_id),
            execution_options={"include_deleted": True},
        ).scalars().first()
    else:
        try:
            normalized_code = normalization.normalize_code(value)
        except AppError as exc:
            raise _field_error("cluster", "cluster could not be resolved") from exc
        key = normalization.code_key(normalized_code)
        cluster = db.execute(
            select(Cluster).where(Cluster.code_key == key),
            execution_options={"include_deleted": True},
        ).scalars().first()

    if cluster is None or cluster.deleted_at is not None:
        raise _field_error("cluster", "cluster does not exist or is not selectable")
    return cluster


def _resolve_cluster_code_filter(db: "Session", code: str) -> uuid.UUID | None:
    """Resolve a list ``cluster=<code>`` filter; ``None`` means no match (empty)."""
    try:
        normalized_code = normalization.normalize_code(code)
    except AppError as exc:
        raise _field_error("cluster", "cluster filter is not a valid code") from exc
    key = normalization.code_key(normalized_code)
    return db.execute(
        select(Cluster.id).where(Cluster.code_key == key),
        execution_options={"include_deleted": True},
    ).scalar_one_or_none()


# --- reference / dependency checker registration (DR-40) --------------------
# F004 registers the first cross-object checker: an undeleted Resource blocks
# deletion of its Cluster (requirements §21). A Resource itself is referenced by
# nobody in F004 (interfaces/VMs/services arrive in F007+), so its own reference
# set is empty; restore must still verify its owning cluster is not deleted.


def _undeleted_resource_references(db: "Session", cluster_id: uuid.UUID) -> list[dict]:
    rows = db.execute(
        select(Resource.id, Resource.hostname).where(
            Resource.cluster_id == cluster_id,
            Resource.deleted_at.is_(None),
        )
    ).all()
    return [
        {"object_type": "resource", "object_id": str(row.id), "label": row.hostname}
        for row in rows
    ]


def _cluster_dependency(db: "Session", resource_id: uuid.UUID) -> list[dict]:
    row = db.execute(
        select(Resource.cluster_id).where(Resource.id == resource_id),
        execution_options={"include_deleted": True},
    ).first()
    if row is None:
        return []
    cluster = db.execute(
        select(Cluster).where(Cluster.id == row[0]),
        execution_options={"include_deleted": True},
    ).scalars().first()
    if cluster is None or cluster.deleted_at is None:
        return []
    return [{"object_type": "cluster", "object_id": str(cluster.id)}]


cluster_service.register_reference_checker("cluster", _undeleted_resource_references)
cluster_service.register_dependency_checker(OBJECT_TYPE, _cluster_dependency)


# --- reads ------------------------------------------------------------------


def clusters_for(
    db: "Session", cluster_ids: list[uuid.UUID]
) -> dict[uuid.UUID, Cluster]:
    """Batch-load owning clusters (including soft-deleted) for serialisation."""
    ids = set(cluster_ids)
    if not ids:
        return {}
    rows = db.execute(
        select(Cluster).where(Cluster.id.in_(ids)),
        execution_options={"include_deleted": True},
    ).scalars().all()
    return {row.id: row for row in rows}


def details_for(
    db: "Session", resource_ids: list[uuid.UUID]
) -> dict[uuid.UUID, BareMetalDetail]:
    """Batch-load hardware detail rows for response assembly (F005)."""
    ids = set(resource_ids)
    if not ids:
        return {}
    rows = db.execute(
        select(BareMetalDetail).where(BareMetalDetail.resource_id.in_(ids))
    ).scalars().all()
    return {row.resource_id: row for row in rows}


def list_resources(
    db: "Session",
    *,
    q: str | None = None,
    cluster: str | None = None,
    cluster_id: uuid.UUID | None = None,
    resource_type: str | None = None,
    role: str | None = None,
    status: str | None = None,
    deleted: str = "exclude",
    page: int = 1,
    page_size: int = 20,
    sort: str = "created_at",
    order: str = "desc",
) -> tuple[list[Resource], int]:
    """Return the visible page of resources plus the filtered total."""
    if deleted not in DELETED_MODES:
        raise _field_error("deleted", "deleted must be exclude, include or only")
    if sort not in SORT_FIELDS:
        raise _field_error("sort", "unsupported sort field")
    if order not in ORDERS:
        raise _field_error("order", "order must be asc or desc")
    if resource_type is not None:
        _validate_resource_type(resource_type)
    if role is not None:
        _validate_role(role)
    if status is not None:
        _validate_status(status)

    filters = []
    if cluster is not None:
        resolved = _resolve_cluster_code_filter(db, cluster)
        if resolved is None:
            filters.append(false())
        else:
            filters.append(Resource.cluster_id == resolved)
    if cluster_id is not None:
        filters.append(Resource.cluster_id == cluster_id)
    if resource_type is not None:
        filters.append(Resource.resource_type == resource_type)
    if role is not None:
        filters.append(Resource.role == role)
    if status is not None:
        filters.append(Resource.status == status)
    if q:
        pattern = f"%{_escape_like(q)}%"
        filters.append(Resource.hostname.ilike(pattern, escape="\\"))
    if deleted == "only":
        filters.append(Resource.deleted_at.is_not(None))

    include_deleted = deleted in ("include", "only")
    execution_options = _query_options(include_deleted)

    sort_column = _SORT_COLUMNS[sort]
    ordered = sort_column.desc() if order == "desc" else sort_column.asc()
    offset = (page - 1) * page_size

    statement = (
        select(Resource)
        .where(*filters)
        .order_by(ordered, Resource.id.asc())
        .offset(offset)
        .limit(page_size)
    )
    total_statement = select(func.count()).select_from(Resource).where(*filters)

    items = list(
        db.execute(statement, execution_options=execution_options).scalars().all()
    )
    total = int(
        db.execute(total_statement, execution_options=execution_options).scalar_one()
    )
    return items, total


def get_resource(
    db: "Session", resource_id: uuid.UUID, *, include_deleted: bool = False
) -> Resource | None:
    """Return a resource, hidden by the soft-delete filter unless requested."""
    statement = select(Resource).where(Resource.id == resource_id)
    return (
        db.execute(statement, execution_options=_query_options(include_deleted))
        .scalars()
        .first()
    )


def list_activity(
    db: "Session",
    resource_id: uuid.UUID,
    *,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list, int]:
    """Return this resource's audit rows (ascending by created_at then id)."""
    from app.models.audit_log import AuditLog

    filters = [
        AuditLog.object_type == OBJECT_TYPE,
        AuditLog.object_id == resource_id,
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


def _attach_hardware(resource: Resource, values: dict[str, Any]) -> BareMetalDetail:
    """Attach a new 1:1 hardware detail to ``resource`` (same Session)."""
    detail = BareMetalDetail(
        meta=values["metadata"],
        **{field: values[field] for field in STRING_FIELDS + INT_FIELDS},
    )
    resource.bare_metal_detail = detail
    return detail


def create_resource(
    db: "Session",
    operator: "Operator | None",
    *,
    cluster: str,
    hostname: str,
    resource_type: str,
    role: str = "OTHER",
    status: str = "UNKNOWN",
    description: str | None = None,
    metadata: dict | None = None,
    hardware: dict | None = None,
) -> Resource:
    """Create a resource; same-cluster hostname is unique among undeleted rows.

    A BARE_METAL resource always gets its 1:1 ``bare_metal_details`` row in the
    same transaction (all-null when ``hardware`` is omitted). A VIRTUAL_MACHINE
    request that carries ``hardware`` is rejected with 422 (DR-51).
    """
    resolved_cluster = _resolve_cluster(db, cluster)
    normalized_hostname = normalization.normalize_hostname(hostname)
    key = normalization.hostname_key(normalized_hostname)
    _validate_resource_type(resource_type)
    _validate_role(role)
    _validate_status(status)
    meta = _validate_metadata({} if metadata is None else metadata)

    hardware_values: dict[str, Any] | None = None
    if resource_type == "VIRTUAL_MACHINE":
        if hardware is not None:
            raise _field_error(
                "hardware", "hardware is only valid for BARE_METAL resources"
            )
    else:
        hardware_values = validate_hardware(hardware or {}, partial=False)

    existing = db.execute(
        select(Resource.id).where(
            Resource.cluster_id == resolved_cluster.id,
            Resource.hostname_key == key,
            Resource.deleted_at.is_(None),
        )
    ).first()
    if existing is not None:
        raise Conflict.unique_conflict("hostname")

    resource = Resource(
        cluster_id=resolved_cluster.id,
        hostname=normalized_hostname,
        hostname_key=key,
        resource_type=resource_type,
        role=role,
        status=status,
        description=description,
        meta=meta,
    )
    db.add(resource)
    try:
        db.flush()
    except IntegrityError as exc:  # concurrent create lost the race
        db.rollback()
        raise _translate_integrity_error(exc) from exc

    if hardware_values is not None:
        _attach_hardware(resource, hardware_values)
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
        object_id=resource.id,
        before=None,
        after=resource_snapshot(resource),
    )
    db.commit()
    return resource


def update_resource(
    db: "Session",
    operator: "Operator | None",
    resource_id: uuid.UUID,
    *,
    expected_version: int,
    changes: dict[str, Any],
    hardware: dict | None = None,
) -> Resource:
    """Partial update with optimistic locking; cluster/resource_type immutable.

    ``hardware`` (when not ``None``) is a sub-field-level patch: only the supplied
    keys are applied, an explicit ``null`` clears that nullable sub-field, and a
    non-BARE_METAL resource rejects any hardware with 422. The detail write and
    the Resource update share one transaction.
    """
    resource = get_resource(db, resource_id)
    if resource is None:
        raise NotFound()
    if resource.version != expected_version:
        raise VersionConflict(resource.version)

    hardware_values: dict[str, Any] | None = None
    if hardware is not None:
        if resource.resource_type != "BARE_METAL":
            raise _field_error(
                "hardware", "hardware is only valid for BARE_METAL resources"
            )
        hardware_values = validate_hardware(hardware, partial=True)

    values: dict[str, Any] = {}
    if "hostname" in changes:
        normalized_hostname = normalization.normalize_hostname(changes["hostname"])
        key = normalization.hostname_key(normalized_hostname)
        duplicate = db.execute(
            select(Resource.id).where(
                Resource.cluster_id == resource.cluster_id,
                Resource.hostname_key == key,
                Resource.deleted_at.is_(None),
                Resource.id != resource_id,
            )
        ).first()
        if duplicate is not None:
            raise Conflict.unique_conflict("hostname")
        values["hostname"] = normalized_hostname
        values["hostname_key"] = key
    if "role" in changes:
        values["role"] = _validate_role(changes["role"])
    if "status" in changes:
        values["status"] = _validate_status(changes["status"])
    if "description" in changes:
        values["description"] = changes["description"]
    if "metadata" in changes:
        values["meta"] = _validate_metadata(changes["metadata"])

    before = resource_snapshot(resource)
    values["version"] = Resource.version + 1
    values["updated_at"] = func.now()

    try:
        result = db.execute(
            update(Resource)
            .where(
                Resource.id == resource_id,
                Resource.version == expected_version,
                Resource.deleted_at.is_(None),
            )
            .values(**values)
        )
        if result.rowcount == 0:
            _raise_update_conflict(db, resource_id)

        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise _translate_integrity_error(exc) from exc

    if hardware_values is not None:
        detail = resource.bare_metal_detail
        if detail is None:  # application invariant repair; normally present
            detail = BareMetalDetail(meta={})
            resource.bare_metal_detail = detail
        for field in STRING_FIELDS + INT_FIELDS:
            if field in hardware_values:
                setattr(detail, field, hardware_values[field])
        if "metadata" in hardware_values:
            detail.meta = hardware_values["metadata"]
        try:
            db.flush()
        except IntegrityError as exc:
            db.rollback()
            raise _translate_integrity_error(exc) from exc

    db.refresh(resource)
    audit.record(
        db,
        operator,
        action="UPDATE",
        object_type=OBJECT_TYPE,
        object_id=resource.id,
        before=before,
        after=resource_snapshot(resource),
    )
    db.commit()
    return resource


def delete_resource(
    db: "Session",
    operator: "Operator | None",
    resource_id: uuid.UUID,
    *,
    expected_version: int,
) -> None:
    """Soft delete (no cascade); blocked by undeleted references (F004: none)."""
    resource = get_resource(db, resource_id)
    if resource is None:
        raise NotFound()
    if resource.version != expected_version:
        raise VersionConflict(resource.version)

    references = cluster_service.check_references(db, OBJECT_TYPE, resource_id)
    if references:
        raise Conflict.reference_exists(references)

    before = resource_snapshot(resource)
    result = db.execute(
        update(Resource)
        .where(
            Resource.id == resource_id,
            Resource.version == expected_version,
            Resource.deleted_at.is_(None),
        )
        .values(
            deleted_at=func.now(),
            version=Resource.version + 1,
            updated_at=func.now(),
        )
    )
    if result.rowcount == 0:
        _raise_update_conflict(db, resource_id)

    db.flush()
    db.refresh(resource)
    audit.record(
        db,
        operator,
        action="DELETE",
        object_type=OBJECT_TYPE,
        object_id=resource.id,
        before=before,
        after=None,
    )
    db.commit()


def restore_resource(
    db: "Session",
    operator: "Operator | None",
    resource_id: uuid.UUID,
    *,
    expected_version: int,
) -> Resource:
    """Restore a soft-deleted resource; rechecks dependencies and uniqueness."""
    resource = get_resource(db, resource_id, include_deleted=True)
    if resource is None:
        raise NotFound()
    if resource.deleted_at is None:
        raise Conflict.not_deleted()
    if resource.version != expected_version:
        raise VersionConflict(resource.version)

    dependency_conflicts = cluster_service.check_dependencies(
        db, OBJECT_TYPE, resource_id
    )
    if dependency_conflicts:
        raise Conflict.dependency_deleted(dependency_conflicts)

    duplicate = db.execute(
        select(Resource.id).where(
            Resource.cluster_id == resource.cluster_id,
            Resource.hostname_key == resource.hostname_key,
            Resource.deleted_at.is_(None),
            Resource.id != resource_id,
        )
    ).first()
    if duplicate is not None:
        raise Conflict.unique_conflict("hostname")

    before = resource_snapshot(resource)
    try:
        result = db.execute(
            update(Resource)
            .where(
                Resource.id == resource_id,
                Resource.version == expected_version,
                Resource.deleted_at.is_not(None),
            )
            .values(
                deleted_at=None,
                version=Resource.version + 1,
                updated_at=func.now(),
            )
        )
        if result.rowcount == 0:
            _raise_update_conflict(db, resource_id, include_deleted=True)

        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise _translate_integrity_error(exc) from exc
    db.refresh(resource)
    audit.record(
        db,
        operator,
        action="RESTORE",
        object_type=OBJECT_TYPE,
        object_id=resource.id,
        before=before,
        after=resource_snapshot(resource),
    )
    db.commit()
    return resource


def _raise_update_conflict(
    db: "Session", resource_id: uuid.UUID, *, include_deleted: bool = True
) -> None:
    """Translate a conditional-UPDATE rowcount of 0 into 404 or 409."""
    current_version = db.execute(
        select(Resource.version).where(Resource.id == resource_id),
        execution_options=_query_options(include_deleted),
    ).scalar_one_or_none()
    if current_version is None:
        raise NotFound()
    raise VersionConflict(int(current_version))