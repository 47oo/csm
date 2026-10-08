"""Cluster business service (Contract §4–§9, DR-19/DR-20/DR-23/DR-30).

All Cluster rules live here: normalisation, list filtering/sorting/pagination,
optimistic-lock conditional UPDATE, soft delete / restore, reference checks and
the audit trail (same Session, same commit). Routes only translate HTTP.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
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
from app.models.cluster import Cluster
from app.services import audit, normalization

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from app.core.auth import Operator

OBJECT_TYPE = "cluster"
REFERENCE_OBJECT_TYPE = "cluster"
VALID_STATUSES = ("ACTIVE", "INACTIVE")
DELETED_MODES = ("exclude", "include", "only")
SORT_FIELDS = ("code", "name", "status", "created_at", "updated_at")
ORDERS = ("asc", "desc")

_SORT_COLUMNS = {
    "code": Cluster.code_key,
    "name": Cluster.name,
    "status": Cluster.status,
    "created_at": Cluster.created_at,
    "updated_at": Cluster.updated_at,
}

# --- Reference / dependency checker registry (DR-30) -----------------------
# F003 registers none for ``cluster`` (reference set is empty); F004+ append
# checkers here. A checker returns a list of reference descriptors, each with
# object_type/object_id/label.
ReferenceChecker = Callable[["Session", uuid.UUID], list[dict[str, Any]]]
DependencyChecker = Callable[["Session", uuid.UUID], list[dict[str, Any]]]

_REFERENCE_CHECKERS: dict[str, list[ReferenceChecker]] = {}
_DEPENDENCY_CHECKERS: dict[str, list[DependencyChecker]] = {}


def register_reference_checker(object_type: str, checker: ReferenceChecker) -> None:
    _REFERENCE_CHECKERS.setdefault(object_type, []).append(checker)


def register_dependency_checker(object_type: str, checker: DependencyChecker) -> None:
    _DEPENDENCY_CHECKERS.setdefault(object_type, []).append(checker)


def check_references(db: "Session", object_type: str, object_id: uuid.UUID) -> list[dict]:
    """Return undeleted references blocking deletion (empty for F003 cluster)."""
    references: list[dict] = []
    for checker in _REFERENCE_CHECKERS.get(object_type, []):
        references.extend(checker(db, object_id))
    return references


def check_dependencies(db: "Session", object_type: str, object_id: uuid.UUID) -> list[dict]:
    """Return still-soft-deleted dependencies blocking restore (F003 empty)."""
    conflicts: list[dict] = []
    for checker in _DEPENDENCY_CHECKERS.get(object_type, []):
        conflicts.extend(checker(db, object_id))
    return conflicts


# --- helpers ----------------------------------------------------------------


def _field_error(field: str, message: str) -> ValidationError:
    return ValidationError(details={"fields": [{"field": field, "message": message}]})


def _validate_status(status: str) -> str:
    if status not in VALID_STATUSES:
        raise _field_error("status", "status must be ACTIVE or INACTIVE")
    return status


def _validate_metadata(metadata: Any) -> dict:
    if not isinstance(metadata, dict):
        raise _field_error("metadata", "metadata must be a JSON object")
    return metadata


def cluster_snapshot(cluster: Cluster) -> dict[str, Any]:
    """Whitelisted snapshot handed to :mod:`app.services.audit`."""
    return {
        "code": cluster.code,
        "name": cluster.name,
        "status": cluster.status,
        "description": cluster.description,
        "metadata": cluster.meta,
    }


def resolve_cluster(db: "Session", reference: Any) -> Cluster:
    """Resolve a POST/PATCH ``cluster`` (UUID or code) to an undeleted Cluster.

    Missing/nonexistent/soft-deleted all yield 422 with ``field:"cluster"``.
    The lookup deliberately includes soft-deleted rows so a deleted cluster is
    reported as a field error rather than silently ignored. Shared by F004
    Resource and F008 Network (D01 §5.7 / DR-89).
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


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _translate_integrity_error(exc: IntegrityError) -> AppError:
    """Map an unexpected database integrity failure to a clean app error.

    A ``uq_clusters_code_key`` violation is the documented concurrent-create
    race and becomes 409 ``Conflict{unique_conflict}``. Any other CHECK/UNIQUE
    failure means the application validation and the database constraint
    diverged; it is surfaced as a clean 422 instead of an unhandled 500 (which
    would leak a stack trace). The caller must have rolled back first.
    """
    diag = getattr(getattr(exc, "orig", None), "diag", None)
    constraint = getattr(diag, "constraint_name", None) or ""
    if "uq_clusters_code_key" in constraint or "uq_clusters_code_key" in str(exc):
        return Conflict.unique_conflict("code")
    return ValidationError(message="cluster write rejected by a database constraint")


def _query_options(include_deleted: bool) -> dict[str, Any]:
    return {"include_deleted": True} if include_deleted else {}


# --- reads ------------------------------------------------------------------


def list_clusters(
    db: "Session",
    *,
    q: str | None = None,
    code: str | None = None,
    status: str | None = None,
    deleted: str = "exclude",
    page: int = 1,
    page_size: int = 20,
    sort: str = "created_at",
    order: str = "desc",
) -> tuple[list[Cluster], int]:
    """Return the visible page of clusters plus the filtered total."""
    if deleted not in DELETED_MODES:
        raise _field_error("deleted", "deleted must be exclude, include or only")
    if sort not in SORT_FIELDS:
        raise _field_error("sort", "unsupported sort field")
    if order not in ORDERS:
        raise _field_error("order", "order must be asc or desc")
    if status is not None:
        _validate_status(status)

    filters = []
    if status is not None:
        filters.append(Cluster.status == status)
    if code is not None:
        normalized_code = normalization.normalize_code(code)
        filters.append(Cluster.code_key == normalization.code_key(normalized_code))
    if q:
        pattern = f"%{_escape_like(q)}%"
        filters.append(
            Cluster.code.ilike(pattern, escape="\\")
            | Cluster.name.ilike(pattern, escape="\\")
        )
    if deleted == "only":
        filters.append(Cluster.deleted_at.is_not(None))

    include_deleted = deleted in ("include", "only")
    execution_options = _query_options(include_deleted)

    sort_column = _SORT_COLUMNS[sort]
    ordered = sort_column.desc() if order == "desc" else sort_column.asc()
    offset = (page - 1) * page_size

    statement = (
        select(Cluster)
        .where(*filters)
        .order_by(ordered, Cluster.id.asc())
        .offset(offset)
        .limit(page_size)
    )
    total_statement = select(func.count()).select_from(Cluster).where(*filters)

    items = list(
        db.execute(statement, execution_options=execution_options).scalars().all()
    )
    total = int(
        db.execute(total_statement, execution_options=execution_options).scalar_one()
    )
    return items, total


def get_cluster(
    db: "Session", cluster_id: uuid.UUID, *, include_deleted: bool = False
) -> Cluster | None:
    """Return a cluster, hidden by the soft-delete filter unless requested."""
    statement = select(Cluster).where(Cluster.id == cluster_id)
    return (
        db.execute(
            statement, execution_options=_query_options(include_deleted)
        )
        .scalars()
        .first()
    )


def list_activity(
    db: "Session",
    cluster_id: uuid.UUID,
    *,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list, int]:
    """Return this cluster's audit rows (ascending by created_at then id)."""
    from app.models.audit_log import AuditLog

    filters = [
        AuditLog.object_type == OBJECT_TYPE,
        AuditLog.object_id == cluster_id,
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


def create_cluster(
    db: "Session",
    operator: "Operator | None",
    *,
    code: str,
    name: str,
    status: str = "ACTIVE",
    description: str | None = None,
    metadata: dict | None = None,
) -> Cluster:
    """Create a cluster; ``code`` is fully unique including soft-deleted rows."""
    normalized_code = normalization.normalize_code(code)
    normalized_name = normalization.normalize_name(name)
    _validate_status(status)
    meta = _validate_metadata({} if metadata is None else metadata)
    key = normalization.code_key(normalized_code)

    existing = db.execute(
        select(Cluster.id).where(Cluster.code_key == key),
        execution_options={"include_deleted": True},
    ).scalar_one_or_none()
    if existing is not None:
        raise Conflict.unique_conflict("code")

    cluster = Cluster(
        code=normalized_code,
        code_key=key,
        name=normalized_name,
        status=status,
        description=description,
        meta=meta,
    )
    db.add(cluster)
    try:
        db.flush()
    except IntegrityError as exc:  # concurrent create lost the race on the UNIQUE
        db.rollback()
        raise _translate_integrity_error(exc) from exc

    audit.record(
        db,
        operator,
        action="CREATE",
        object_type=OBJECT_TYPE,
        object_id=cluster.id,
        before=None,
        after=cluster_snapshot(cluster),
    )
    db.commit()
    return cluster


def update_cluster(
    db: "Session",
    operator: "Operator | None",
    cluster_id: uuid.UUID,
    *,
    expected_version: int,
    changes: dict[str, Any],
) -> Cluster:
    """Partial update with optimistic locking; ``code`` is immutable."""
    cluster = get_cluster(db, cluster_id)
    if cluster is None:
        raise NotFound()
    if cluster.version != expected_version:
        raise VersionConflict(cluster.version)

    values: dict[str, Any] = {}
    if "name" in changes:
        values["name"] = normalization.normalize_name(changes["name"])
    if "status" in changes:
        values["status"] = _validate_status(changes["status"])
    if "description" in changes:
        values["description"] = changes["description"]
    if "metadata" in changes:
        values["meta"] = _validate_metadata(changes["metadata"])

    before = cluster_snapshot(cluster)
    values["version"] = Cluster.version + 1
    values["updated_at"] = func.now()

    try:
        result = db.execute(
            update(Cluster)
            .where(
                Cluster.id == cluster_id,
                Cluster.version == expected_version,
                Cluster.deleted_at.is_(None),
            )
            .values(**values)
        )
        if result.rowcount == 0:
            _raise_update_conflict(db, cluster_id)

        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise _translate_integrity_error(exc) from exc
    db.refresh(cluster)
    audit.record(
        db,
        operator,
        action="UPDATE",
        object_type=OBJECT_TYPE,
        object_id=cluster.id,
        before=before,
        after=cluster_snapshot(cluster),
    )
    db.commit()
    return cluster


def delete_cluster(
    db: "Session",
    operator: "Operator | None",
    cluster_id: uuid.UUID,
    *,
    expected_version: int,
) -> None:
    """Soft delete (no cascade); blocked when undeleted references exist."""
    cluster = get_cluster(db, cluster_id)
    if cluster is None:
        raise NotFound()
    if cluster.version != expected_version:
        raise VersionConflict(cluster.version)

    references = check_references(db, REFERENCE_OBJECT_TYPE, cluster_id)
    if references:
        raise Conflict.reference_exists(references)

    before = cluster_snapshot(cluster)
    result = db.execute(
        update(Cluster)
        .where(
            Cluster.id == cluster_id,
            Cluster.version == expected_version,
            Cluster.deleted_at.is_(None),
        )
        .values(
            deleted_at=func.now(),
            version=Cluster.version + 1,
            updated_at=func.now(),
        )
    )
    if result.rowcount == 0:
        _raise_update_conflict(db, cluster_id)

    db.flush()
    db.refresh(cluster)
    audit.record(
        db,
        operator,
        action="DELETE",
        object_type=OBJECT_TYPE,
        object_id=cluster.id,
        before=before,
        after=None,
    )
    db.commit()


def restore_cluster(
    db: "Session",
    operator: "Operator | None",
    cluster_id: uuid.UUID,
    *,
    expected_version: int,
) -> Cluster:
    """Restore a soft-deleted cluster; rechecks uniqueness and dependencies."""
    cluster = get_cluster(db, cluster_id, include_deleted=True)
    if cluster is None:
        raise NotFound()
    if cluster.deleted_at is None:
        raise Conflict.not_deleted()
    if cluster.version != expected_version:
        raise VersionConflict(cluster.version)

    dependency_conflicts = check_dependencies(db, OBJECT_TYPE, cluster_id)
    if dependency_conflicts:
        raise Conflict.dependency_deleted(dependency_conflicts)

    before = cluster_snapshot(cluster)
    try:
        result = db.execute(
            update(Cluster)
            .where(
                Cluster.id == cluster_id,
                Cluster.version == expected_version,
                Cluster.deleted_at.is_not(None),
            )
            .values(
                deleted_at=None,
                version=Cluster.version + 1,
                updated_at=func.now(),
            )
        )
        if result.rowcount == 0:
            _raise_update_conflict(db, cluster_id, include_deleted=True)

        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise _translate_integrity_error(exc) from exc
    db.refresh(cluster)
    audit.record(
        db,
        operator,
        action="RESTORE",
        object_type=OBJECT_TYPE,
        object_id=cluster.id,
        before=before,
        after=cluster_snapshot(cluster),
    )
    db.commit()
    return cluster


def _raise_update_conflict(
    db: "Session", cluster_id: uuid.UUID, *, include_deleted: bool = True
) -> None:
    """Translate a conditional-UPDATE rowcount of 0 into 404 or 409."""
    current_version = db.execute(
        select(Cluster.version).where(Cluster.id == cluster_id),
        execution_options=_query_options(include_deleted),
    ).scalar_one_or_none()
    if current_version is None:
        raise NotFound()
    raise VersionConflict(int(current_version))