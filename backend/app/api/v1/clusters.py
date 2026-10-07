"""Cluster REST endpoints (Contract §6, seven routes).

Routes stay thin: query/body validation, permission checks and response shaping;
all business rules live in :mod:`app.services.cluster`.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from app.core.auth import Operator
from app.core.db import get_db
from app.core.errors import Forbidden, NotFound, ValidationError
from app.core.permissions import Permission, require_permission, role_has_permission
from app.schemas.cluster import (
    ActivityItem,
    ActivityListResponse,
    ClusterCreateRequest,
    ClusterEnvelope,
    ClusterListResponse,
    ClusterUpdateRequest,
    DeletedMode,
    SortField,
    SortOrder,
    build_activity_item,
    build_cluster_out,
)
from app.services import cluster as cluster_service

router = APIRouter(prefix="/clusters", tags=["clusters"])

# Fields that are non-nullable and must not receive an explicit JSON null.
_NON_NULLABLE_PATCH_FIELDS = ("name", "status", "metadata")


def _parse_uuid(value: str) -> uuid.UUID:
    """A non-UUID path segment is reported as 404 (Contract §6.3)."""
    try:
        return uuid.UUID(value)
    except (ValueError, AttributeError, TypeError) as exc:
        raise NotFound() from exc


def _require_view_deleted(operator: Operator) -> None:
    if not role_has_permission(operator.role, Permission.VIEW_DELETED):
        raise Forbidden(reason="permission")


def _validation_field_error(field: str, message: str) -> ValidationError:
    return ValidationError(details={"fields": [{"field": field, "message": message}]})


@router.get("", response_model=ClusterListResponse)
def list_clusters(
    q: str | None = Query(default=None),
    code: str | None = Query(default=None),
    status: str | None = Query(default=None),
    deleted: DeletedMode = Query(default="exclude"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    sort: SortField = Query(default="created_at"),
    order: SortOrder = Query(default="desc"),
    operator: Operator = Depends(require_permission(Permission.READ)),
    db: Session = Depends(get_db),
) -> ClusterListResponse:
    """List clusters with combined filters/sorting/pagination (§4)."""
    if deleted in ("include", "only"):
        _require_view_deleted(operator)
    items, total = cluster_service.list_clusters(
        db,
        q=q,
        code=code,
        status=status,
        deleted=deleted,
        page=page,
        page_size=page_size,
        sort=sort,
        order=order,
    )
    return ClusterListResponse(
        items=[build_cluster_out(item) for item in items],
        page=page,
        page_size=page_size,
        total=total,
    )


@router.post("", response_model=ClusterEnvelope, status_code=201)
def create_cluster(
    payload: ClusterCreateRequest,
    operator: Operator = Depends(require_permission(Permission.WRITE)),
    db: Session = Depends(get_db),
) -> ClusterEnvelope:
    """Create a cluster (201) and write a CREATE audit row."""
    cluster = cluster_service.create_cluster(
        db,
        operator,
        code=payload.code,
        name=payload.name,
        status=payload.status,
        description=payload.description,
        metadata=payload.metadata,
    )
    return ClusterEnvelope(cluster=build_cluster_out(cluster))


@router.get("/{cluster_id}", response_model=ClusterEnvelope)
def get_cluster_detail(
    cluster_id: str,
    deleted: bool = Query(default=False),
    operator: Operator = Depends(require_permission(Permission.READ)),
    db: Session = Depends(get_db),
) -> ClusterEnvelope:
    """Cluster detail; a soft-deleted row needs ``deleted=true`` + VIEW_DELETED."""
    cluster_uuid = _parse_uuid(cluster_id)
    if deleted:
        _require_view_deleted(operator)
    cluster = cluster_service.get_cluster(db, cluster_uuid, include_deleted=deleted)
    if cluster is None:
        raise NotFound()
    return ClusterEnvelope(cluster=build_cluster_out(cluster))


@router.patch("/{cluster_id}", response_model=ClusterEnvelope)
def update_cluster(
    cluster_id: str,
    payload: ClusterUpdateRequest,
    operator: Operator = Depends(require_permission(Permission.WRITE)),
    db: Session = Depends(get_db),
) -> ClusterEnvelope:
    """Partial update with mandatory ``version``; ``code`` is immutable (422)."""
    cluster_uuid = _parse_uuid(cluster_id)
    changes = payload.model_dump(exclude_unset=True)
    changes.pop("version", None)
    for field in _NON_NULLABLE_PATCH_FIELDS:
        if field in changes and changes[field] is None:
            raise _validation_field_error(
                field, f"{field} may not be null in a partial update"
            )
    cluster = cluster_service.update_cluster(
        db,
        operator,
        cluster_uuid,
        expected_version=payload.version,
        changes=changes,
    )
    return ClusterEnvelope(cluster=build_cluster_out(cluster))


@router.delete("/{cluster_id}", status_code=204)
def delete_cluster(
    cluster_id: str,
    version: int = Query(ge=1),
    operator: Operator = Depends(require_permission(Permission.DELETE_OBJECT)),
    db: Session = Depends(get_db),
) -> Response:
    """Soft delete (no cascade); writes a DELETE audit row."""
    cluster_uuid = _parse_uuid(cluster_id)
    cluster_service.delete_cluster(
        db, operator, cluster_uuid, expected_version=version
    )
    return Response(status_code=204)


@router.post("/{cluster_id}/restore", response_model=ClusterEnvelope)
def restore_cluster(
    cluster_id: str,
    version: int = Query(ge=1),
    operator: Operator = Depends(require_permission(Permission.RESTORE)),
    db: Session = Depends(get_db),
) -> ClusterEnvelope:
    """Restore a soft-deleted cluster; writes a RESTORE audit row."""
    cluster_uuid = _parse_uuid(cluster_id)
    cluster = cluster_service.restore_cluster(
        db, operator, cluster_uuid, expected_version=version
    )
    return ClusterEnvelope(cluster=build_cluster_out(cluster))


@router.get("/{cluster_id}/activity", response_model=ActivityListResponse)
def cluster_activity(
    cluster_id: str,
    deleted: bool = Query(default=False),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    operator: Operator = Depends(require_permission(Permission.VIEW_ACTIVITY)),
    db: Session = Depends(get_db),
) -> ActivityListResponse:
    """Object activity (all roles); soft-deleted needs ``deleted=true``."""
    cluster_uuid = _parse_uuid(cluster_id)
    if deleted:
        _require_view_deleted(operator)
    cluster = cluster_service.get_cluster(db, cluster_uuid, include_deleted=deleted)
    if cluster is None:
        raise NotFound()
    rows, total = cluster_service.list_activity(
        db, cluster_uuid, page=page, page_size=page_size
    )
    items: list[ActivityItem] = [build_activity_item(row) for row in rows]
    return ActivityListResponse(
        items=items, page=page, page_size=page_size, total=total
    )