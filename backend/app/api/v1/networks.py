"""Network REST endpoints (Contract §6, seven routes).

Routes stay thin: query/body validation, permission checks and response shaping;
all business rules live in :mod:`app.services.network`.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from app.core.access_scope import AccessScope, get_access_scope
from app.core.auth import Operator
from app.core.db import get_db
from app.core.errors import Forbidden, NotFound, ValidationError
from app.core.permissions import Permission, require_permission, role_has_permission
from app.schemas.cluster import (
    ActivityItem,
    ActivityListResponse,
    build_activity_item,
)
from app.schemas.network import (
    DeletedMode,
    NetworkCreateRequest,
    NetworkEnvelope,
    NetworkListResponse,
    NetworkOut,
    NetworkStatus,
    NetworkUpdateRequest,
    SortField,
    SortOrder,
    build_network_out,
)
from app.services import network as network_service

router = APIRouter(prefix="/networks", tags=["networks"])

# Non-nullable fields that must not receive an explicit JSON null in PATCH.
_NON_NULLABLE_PATCH_FIELDS = (
    "name",
    "cluster",
    "cidr",
    "status",
    "auto_allocate",
    "metadata",
)


def _parse_uuid(value: str) -> uuid.UUID:
    """A non-UUID path segment is reported as 404 (Contract §6)."""
    try:
        return uuid.UUID(value)
    except (ValueError, AttributeError, TypeError) as exc:
        raise NotFound() from exc


def _require_view_deleted(operator: Operator) -> None:
    if not role_has_permission(operator.role, Permission.VIEW_DELETED):
        raise Forbidden(reason="permission")


def _validation_field_error(field: str, message: str) -> ValidationError:
    return ValidationError(details={"fields": [{"field": field, "message": message}]})


def _build_out(db: Session, networks: list) -> list[NetworkOut]:
    cluster_map = network_service.clusters_for(
        db, [network.cluster_id for network in networks]
    )
    return [
        build_network_out(network, cluster_map.get(network.cluster_id))
        for network in networks
    ]


@router.get("", response_model=NetworkListResponse)
def list_networks(
    cluster_id: uuid.UUID | None = Query(default=None),
    status: NetworkStatus | None = Query(default=None),
    auto_allocate: bool | None = Query(default=None),
    q: str | None = Query(default=None),
    deleted: DeletedMode = Query(default="exclude"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    sort: SortField = Query(default="created_at"),
    order: SortOrder = Query(default="desc"),
    operator: Operator = Depends(require_permission(Permission.READ)),
    scope: AccessScope = Depends(get_access_scope),
    db: Session = Depends(get_db),
) -> NetworkListResponse:
    """List networks with combined filters/sorting/pagination (§4)."""
    if deleted in ("include", "only"):
        _require_view_deleted(operator)
    items, total = network_service.list_networks(
        db,
        cluster_id=cluster_id,
        status=status,
        auto_allocate=auto_allocate,
        q=q,
        deleted=deleted,
        page=page,
        page_size=page_size,
        sort=sort,
        order=order,
        scope=scope,
    )
    return NetworkListResponse(
        items=_build_out(db, items), page=page, page_size=page_size, total=total
    )


@router.post("", response_model=NetworkEnvelope, status_code=201)
def create_network(
    payload: NetworkCreateRequest,
    operator: Operator = Depends(require_permission(Permission.WRITE)),
    scope: AccessScope = Depends(get_access_scope),
    db: Session = Depends(get_db),
) -> NetworkEnvelope:
    """Create a Network (201) and write a CREATE audit row."""
    network = network_service.create_network(
        db,
        operator,
        cluster=payload.cluster,
        name=payload.name,
        cidr=payload.cidr,
        gateway=payload.gateway,
        status=payload.status,
        auto_allocate=payload.auto_allocate,
        description=payload.description,
        metadata=payload.metadata,
        scope=scope,
    )
    return NetworkEnvelope(network=_build_out(db, [network])[0])


@router.get("/{network_id}", response_model=NetworkEnvelope)
def get_network_detail(
    network_id: str,
    deleted: bool = Query(default=False),
    operator: Operator = Depends(require_permission(Permission.READ)),
    scope: AccessScope = Depends(get_access_scope),
    db: Session = Depends(get_db),
) -> NetworkEnvelope:
    """Network detail; a soft-deleted row needs ``deleted=true`` + VIEW_DELETED."""
    network_uuid = _parse_uuid(network_id)
    if deleted:
        _require_view_deleted(operator)
    network = network_service.get_network(
        db, network_uuid, include_deleted=deleted, scope=scope
    )
    if network is None:
        raise NotFound()
    return NetworkEnvelope(network=_build_out(db, [network])[0])


@router.patch("/{network_id}", response_model=NetworkEnvelope)
def update_network(
    network_id: str,
    payload: NetworkUpdateRequest,
    operator: Operator = Depends(require_permission(Permission.WRITE)),
    scope: AccessScope = Depends(get_access_scope),
    db: Session = Depends(get_db),
) -> NetworkEnvelope:
    """Partial update with mandatory ``version``; non-nullable nulls rejected."""
    network_uuid = _parse_uuid(network_id)
    changes = payload.model_dump(exclude_unset=True)
    changes.pop("version", None)
    for field in _NON_NULLABLE_PATCH_FIELDS:
        if field in changes and changes[field] is None:
            raise _validation_field_error(
                field, f"{field} may not be null in a partial update"
            )
    network = network_service.update_network(
        db,
        operator,
        network_uuid,
        expected_version=payload.version,
        changes=changes,
        scope=scope,
    )
    return NetworkEnvelope(network=_build_out(db, [network])[0])


@router.delete("/{network_id}", status_code=204)
def delete_network(
    network_id: str,
    version: int = Query(ge=1),
    operator: Operator = Depends(require_permission(Permission.DELETE_OBJECT)),
    scope: AccessScope = Depends(get_access_scope),
    db: Session = Depends(get_db),
) -> Response:
    """Soft delete (no cascade); writes a DELETE audit row."""
    network_uuid = _parse_uuid(network_id)
    network_service.delete_network(
        db, operator, network_uuid, expected_version=version, scope=scope
    )
    return Response(status_code=204)


@router.post("/{network_id}/restore", response_model=NetworkEnvelope)
def restore_network(
    network_id: str,
    version: int = Query(ge=1),
    operator: Operator = Depends(require_permission(Permission.RESTORE)),
    scope: AccessScope = Depends(get_access_scope),
    db: Session = Depends(get_db),
) -> NetworkEnvelope:
    """Restore a soft-deleted Network; writes a RESTORE audit row."""
    network_uuid = _parse_uuid(network_id)
    network = network_service.restore_network(
        db, operator, network_uuid, expected_version=version, scope=scope
    )
    return NetworkEnvelope(network=_build_out(db, [network])[0])


@router.get("/{network_id}/activity", response_model=ActivityListResponse)
def network_activity(
    network_id: str,
    deleted: bool = Query(default=False),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    operator: Operator = Depends(require_permission(Permission.VIEW_ACTIVITY)),
    scope: AccessScope = Depends(get_access_scope),
    db: Session = Depends(get_db),
) -> ActivityListResponse:
    """Object activity (all roles); soft-deleted needs ``deleted=true``."""
    network_uuid = _parse_uuid(network_id)
    if deleted:
        _require_view_deleted(operator)
    network = network_service.get_network(
        db, network_uuid, include_deleted=deleted, scope=scope
    )
    if network is None:
        raise NotFound()
    rows, total = network_service.list_activity(
        db, network_uuid, page=page, page_size=page_size
    )
    items: list[ActivityItem] = [build_activity_item(row) for row in rows]
    return ActivityListResponse(
        items=items, page=page, page_size=page_size, total=total
    )