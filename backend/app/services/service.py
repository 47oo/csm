"""Service business service (Contract §2–§9, DR-140..DR-154).

All Service rules live here: ``name_key`` normalisation (per-code-point ASCII
folding, never ``str.lower()``), status / metadata validation, Resource
resolution and the same-Resource undeleted name uniqueness (``unique_conflict``),
list filtering/sorting/pagination, optimistic-lock conditional UPDATE, soft
delete with the ServiceEndpoint reference check, restore with the deterministic
re-check priority (name uniqueness -> Resource dependency) and the audit trail
(same Session, same commit). Routes only translate HTTP.

Cross-object wiring (DR-146/DR-147/DR-148):
- an undeleted Service blocks deletion of its Resource (registered on the shared
  ``cluster_service`` reference registry);
- a Service restore fails with ``dependency_deleted`` when its Resource is still
  soft-deleted / missing (registered as a dependency checker);
- the Service <- ServiceEndpoint reference set lives in
  :mod:`app.services.service_reference` (F011 default empty set; F012 registers
  the real Endpoint provider).

Soft-delete semantics (Contract §5): the Session-level ``with_loader_criteria``
filter hides ``deleted_at IS NOT NULL`` rows by default; callers opt in with
``include_deleted=True``.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError

from app.core.errors import (
    AppError,
    Conflict,
    NotFound,
    ValidationError,
    VersionConflict,
)
from app.models.resource import Resource
from app.models.service import VALID_STATUSES, Service
from app.services import audit, normalization, scope_filters, service_reference
from app.services import cluster as cluster_service

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from app.core.auth import Operator

OBJECT_TYPE = "service"
DELETED_MODES = ("exclude", "include", "only")
SORT_FIELDS = ("name", "status", "created_at", "updated_at")
ORDERS = ("asc", "desc")

_SORT_COLUMNS = {
    # Contract §4: ``sort=name`` orders by the normalisation key.
    "name": Service.name_key,
    "status": Service.status,
    "created_at": Service.created_at,
    "updated_at": Service.updated_at,
}


# --- helpers ----------------------------------------------------------------


def _field_error(field: str, message: str) -> ValidationError:
    return ValidationError(details={"fields": [{"field": field, "message": message}]})


def _validate_status(value: Any) -> str:
    if value not in VALID_STATUSES:
        raise _field_error("status", "status must be RUNNING, STOPPED or UNKNOWN")
    return value


def _validate_metadata(metadata: Any) -> dict:
    if not isinstance(metadata, dict):
        raise _field_error("metadata", "metadata must be a JSON object")
    return metadata


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _query_options(include_deleted: bool) -> dict[str, Any]:
    return {"include_deleted": True} if include_deleted else {}


def _load_resource(db: "Session", resource_id: uuid.UUID) -> Resource | None:
    """Load a Resource including soft-deleted rows (lookup/dependency check)."""
    return (
        db.execute(
            select(Resource).where(Resource.id == resource_id),
            execution_options={"include_deleted": True},
        )
        .scalars()
        .first()
    )


def resolve_resource(db: "Session", reference: Any, *, scope=None) -> Resource:
    """Resolve a POST ``resource`` UUID to an undeleted Resource (DR-144).

    Missing / non-UUID / nonexistent / soft-deleted all yield 422 with
    ``field:"resource"``. The lookup includes soft-deleted rows so a deleted
    Resource is reported as a field error rather than silently ignored.
    """
    if not isinstance(reference, str) or not reference.strip():
        raise _field_error("resource", "resource is required")
    value = reference.strip()
    try:
        resource_id = uuid.UUID(value)
    except (ValueError, AttributeError, TypeError) as exc:
        raise _field_error("resource", "resource must be a valid UUID") from exc

    resource = _load_resource(db, resource_id)
    if (
        resource is None
        or resource.deleted_at is not None
        or not scope_filters.normalize(scope).allows(resource.cluster_id)
    ):
        raise _field_error("resource", "resource does not exist or is not selectable")
    return resource


def _translate_integrity_error(exc: IntegrityError) -> AppError:
    """Map an unexpected database integrity failure to a clean app error.

    A ``uq_services_resource_id_name_key`` violation is the documented concurrent
    same-name race (409 ``unique_conflict``). Any other CHECK/FK failure means
    application validation and the database diverged and is surfaced as a clean
    422 instead of an unhandled 500. The caller must have rolled back first.
    """
    diag = getattr(getattr(exc, "orig", None), "diag", None)
    constraint = getattr(diag, "constraint_name", None) or ""
    if "uq_services_resource_id_name_key" in constraint or (
        "uq_services_resource_id_name_key" in str(exc)
    ):
        return Conflict.unique_conflict("name")
    return ValidationError(message="service write rejected by a database constraint")


def service_snapshot(service: Service) -> dict[str, Any]:
    """Whitelisted snapshot handed to :mod:`app.services.audit` (Contract §8).

    ``resource_id`` is stringified so the JSONB snapshot stays JSON-serialisable.
    """
    return {
        "resource_id": str(service.resource_id),
        "name": service.name,
        "status": service.status,
        "description": service.description,
        "metadata": service.meta,
    }


# --- reference / dependency checker registration (DR-147/DR-148) ------------
# An undeleted Service blocks deletion of its Resource (requirements §21); the
# checker is registered on the shared ``cluster_service`` registry, matching the
# F006/F007 pattern. A Service restore re-checks that its Resource is still
# undeleted via the dependency registry.


def _undeleted_service_references(
    db: "Session", resource_id: uuid.UUID
) -> list[dict]:
    rows = db.execute(
        select(Service.id, Service.name).where(
            Service.resource_id == resource_id,
            Service.deleted_at.is_(None),
        )
    ).all()
    return [
        {"object_type": "service", "object_id": str(row.id), "label": row.name}
        for row in rows
    ]


def _service_resource_dependency(
    db: "Session", service_id: uuid.UUID
) -> list[dict]:
    service = (
        db.execute(
            select(Service).where(Service.id == service_id),
            execution_options={"include_deleted": True},
        )
        .scalars()
        .first()
    )
    if service is None:
        return []
    resource = _load_resource(db, service.resource_id)
    if resource is None or resource.deleted_at is not None:
        return [
            {"object_type": "resource", "object_id": str(service.resource_id)}
        ]
    return []


cluster_service.register_reference_checker(
    "resource", _undeleted_service_references
)
cluster_service.register_dependency_checker(
    OBJECT_TYPE, _service_resource_dependency
)


# --- reads ------------------------------------------------------------------


def list_services(
    db: "Session",
    *,
    resource_id: uuid.UUID | None = None,
    status: str | None = None,
    q: str | None = None,
    deleted: str = "exclude",
    page: int = 1,
    page_size: int = 20,
    sort: str = "created_at",
    order: str = "desc",
    scope=None,
) -> tuple[list[Service], int]:
    """Return the visible page of services plus the filtered total."""
    if deleted not in DELETED_MODES:
        raise _field_error("deleted", "deleted must be exclude, include or only")
    if sort not in SORT_FIELDS:
        raise _field_error("sort", "unsupported sort field")
    if order not in ORDERS:
        raise _field_error("order", "order must be asc or desc")
    if status is not None:
        _validate_status(status)

    filters = [scope_filters.service_parent_predicate(scope)]
    if resource_id is not None:
        filters.append(Service.resource_id == resource_id)
    if status is not None:
        filters.append(Service.status == status)
    if q is not None and q.strip():
        # Case-insensitive substring on name (no pg_trgm); LIKE metacharacters
        # are escaped.
        pattern = f"%{_escape_like(q)}%"
        filters.append(Service.name.ilike(pattern, escape="\\"))
    if deleted == "only":
        filters.append(Service.deleted_at.is_not(None))

    include_deleted = deleted in ("include", "only")
    execution_options = _query_options(include_deleted)

    sort_column = _SORT_COLUMNS[sort]
    ordered = sort_column.desc() if order == "desc" else sort_column.asc()
    offset = (page - 1) * page_size

    statement = (
        select(Service)
        .where(*filters)
        .order_by(ordered, Service.id.asc())
        .offset(offset)
        .limit(page_size)
    )
    total_statement = select(func.count()).select_from(Service).where(*filters)

    items = list(
        db.execute(statement, execution_options=execution_options).scalars().all()
    )
    total = int(
        db.execute(total_statement, execution_options=execution_options).scalar_one()
    )
    return items, total


def get_service(
    db: "Session",
    service_id: uuid.UUID,
    *,
    include_deleted: bool = False,
    scope=None,
) -> Service | None:
    """Return a service, hidden by the soft-delete filter unless requested."""
    statement = select(Service).where(
        Service.id == service_id, scope_filters.service_parent_predicate(scope)
    )
    return (
        db.execute(statement, execution_options=_query_options(include_deleted))
        .scalars()
        .first()
    )


def resources_for(
    db: "Session", resource_ids: list[uuid.UUID]
) -> dict[uuid.UUID, Resource]:
    """Batch-load owning Resources (including soft-deleted) for serialisation."""
    ids = set(resource_ids)
    if not ids:
        return {}
    rows = db.execute(
        select(Resource).where(Resource.id.in_(ids)),
        execution_options={"include_deleted": True},
    ).scalars().all()
    return {row.id: row for row in rows}


def list_activity(
    db: "Session",
    service_id: uuid.UUID,
    *,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list, int]:
    """Return this service's audit rows (ascending by created_at then id)."""
    from app.models.audit_log import AuditLog

    filters = [
        AuditLog.object_type == OBJECT_TYPE,
        AuditLog.object_id == service_id,
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


def create_service(
    db: "Session",
    operator: "Operator | None",
    *,
    resource: Any,
    name: str,
    status: str = "UNKNOWN",
    description: str | None = None,
    metadata: dict | None = None,
    scope=None,
) -> Service:
    """Create a Service; validated per Contract §6.2 order.

    body (422) -> resource (422, exists and undeleted) -> name normalisation
    (422) -> same-Resource undeleted name uniqueness (409) -> write + CREATE
    Audit -> 201. The partial unique index arbitrates a concurrent same-name
    race atomically.
    """
    validated_status = _validate_status(status)
    meta = _validate_metadata({} if metadata is None else metadata)

    resource_row = resolve_resource(db, resource, scope=scope)
    normalized_name = normalization.normalize_service_name(name)
    name_key = normalization.service_name_key(normalized_name)

    duplicate = db.execute(
        select(Service.id).where(
            Service.resource_id == resource_row.id,
            Service.name_key == name_key,
            Service.deleted_at.is_(None),
        )
    ).first()
    if duplicate is not None:
        raise Conflict.unique_conflict("name")

    service = Service(
        resource_id=resource_row.id,
        name=normalized_name,
        name_key=name_key,
        status=validated_status,
        description=description,
        meta=meta,
    )
    db.add(service)
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
        object_id=service.id,
        before=None,
        after=service_snapshot(service),
    )
    db.commit()
    return service


def update_service(
    db: "Session",
    operator: "Operator | None",
    service_id: uuid.UUID,
    *,
    expected_version: int,
    changes: dict[str, Any],
    scope=None,
) -> Service:
    """Partial update with optimistic locking; ``resource`` is immutable.

    Contract §6.4 order: visibility (404) -> version (409) -> (if renamed) name
    normalisation (422) -> name uniqueness (409) -> write + UPDATE Audit -> 200.
    """
    service = get_service(db, service_id, scope=scope)
    if service is None:
        raise NotFound()
    if service.version != expected_version:
        raise VersionConflict(service.version)

    values: dict[str, Any] = {}

    if "name" in changes:
        normalized_name = normalization.normalize_service_name(changes["name"])
        name_key = normalization.service_name_key(normalized_name)
        duplicate = db.execute(
            select(Service.id).where(
                Service.resource_id == service.resource_id,
                Service.name_key == name_key,
                Service.deleted_at.is_(None),
                Service.id != service_id,
            )
        ).first()
        if duplicate is not None:
            raise Conflict.unique_conflict("name")
        values["name"] = normalized_name
        values["name_key"] = name_key

    if "status" in changes:
        values["status"] = _validate_status(changes["status"])
    if "metadata" in changes:
        values["meta"] = _validate_metadata(changes["metadata"])
    if "description" in changes:
        values["description"] = changes["description"]

    before = service_snapshot(service)
    values["version"] = Service.version + 1
    values["updated_at"] = func.now()

    try:
        result = db.execute(
            update(Service)
            .where(
                Service.id == service_id,
                Service.version == expected_version,
                Service.deleted_at.is_(None),
            )
            .values(**values)
        )
        if result.rowcount == 0:
            _raise_update_conflict(db, service_id)

        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise _translate_integrity_error(exc) from exc

    db.refresh(service)
    audit.record(
        db,
        operator,
        action="UPDATE",
        object_type=OBJECT_TYPE,
        object_id=service.id,
        before=before,
        after=service_snapshot(service),
    )
    db.commit()
    return service


def delete_service(
    db: "Session",
    operator: "Operator | None",
    service_id: uuid.UUID,
    *,
    expected_version: int,
    scope=None,
) -> None:
    """Soft delete (no cascade); blocked by undeleted ServiceEndpoint references.

    Contract §6.5 order: object (404) -> version (409) -> reference check (409
    ``reference_exists``) -> soft delete. F011 registers no provider, so the
    reference set is empty until F012 does (DR-146).
    """
    service = get_service(db, service_id, scope=scope)
    if service is None:
        raise NotFound()
    if service.version != expected_version:
        raise VersionConflict(service.version)

    references = service_reference.check_service_references(db, service_id)
    if references:
        raise Conflict.reference_exists(references)

    before = service_snapshot(service)
    result = db.execute(
        update(Service)
        .where(
            Service.id == service_id,
            Service.version == expected_version,
            Service.deleted_at.is_(None),
        )
        .values(
            deleted_at=func.now(),
            version=Service.version + 1,
            updated_at=func.now(),
        )
    )
    if result.rowcount == 0:
        _raise_update_conflict(db, service_id)

    db.flush()
    db.refresh(service)
    audit.record(
        db,
        operator,
        action="DELETE",
        object_type=OBJECT_TYPE,
        object_id=service.id,
        before=before,
        after=None,
    )
    db.commit()


def restore_service(
    db: "Session",
    operator: "Operator | None",
    service_id: uuid.UUID,
    *,
    expected_version: int,
    scope=None,
) -> Service:
    """Restore a soft-deleted Service (Contract §6.6).

    Deterministic priority: find incl. deleted (404) -> not deleted (409) ->
    version (409) -> name uniqueness (409 ``unique_conflict``) -> Resource
    dependency (409 ``dependency_deleted``) -> restore. A failed restore never
    overwrites the newer object; name reuse precedes the Resource dependency.
    No cascade and no Endpoint restore (F012).
    """
    service = get_service(db, service_id, include_deleted=True, scope=scope)
    if service is None:
        raise NotFound()
    if service.deleted_at is None:
        raise Conflict.not_deleted()
    if service.version != expected_version:
        raise VersionConflict(service.version)

    duplicate = db.execute(
        select(Service.id).where(
            Service.resource_id == service.resource_id,
            Service.name_key == service.name_key,
            Service.deleted_at.is_(None),
            Service.id != service_id,
        )
    ).first()
    if duplicate is not None:
        raise Conflict.unique_conflict("name")

    resource = _load_resource(db, service.resource_id)
    if resource is None or resource.deleted_at is not None:
        raise Conflict.dependency_deleted(
            [{"object_type": "resource", "object_id": str(service.resource_id)}]
        )

    before = service_snapshot(service)
    try:
        result = db.execute(
            update(Service)
            .where(
                Service.id == service_id,
                Service.version == expected_version,
                Service.deleted_at.is_not(None),
            )
            .values(
                deleted_at=None,
                version=Service.version + 1,
                updated_at=func.now(),
            )
        )
        if result.rowcount == 0:
            _raise_update_conflict(db, service_id, include_deleted=True)

        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise _translate_integrity_error(exc) from exc

    db.refresh(service)
    audit.record(
        db,
        operator,
        action="RESTORE",
        object_type=OBJECT_TYPE,
        object_id=service.id,
        before=before,
        after=service_snapshot(service),
    )
    db.commit()
    return service


def _raise_update_conflict(
    db: "Session", service_id: uuid.UUID, *, include_deleted: bool = True
) -> None:
    """Translate a conditional-UPDATE rowcount of 0 into 404 or 409."""
    current_version = db.execute(
        select(Service.version).where(Service.id == service_id),
        execution_options=_query_options(include_deleted),
    ).scalar_one_or_none()
    if current_version is None:
        raise NotFound()
    raise VersionConflict(int(current_version))