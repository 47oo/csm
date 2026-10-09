"""IPPool REST endpoints (Contract §6, seven routes).

Routes stay thin: query/body validation, permission checks and response shaping;
all business rules live in :mod:`app.services.ip_pool`.
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
    build_activity_item,
)
from app.schemas.ip_pool import (
    AllocationMode,
    DeletedMode,
    IPPoolCreateRequest,
    IPPoolEnvelope,
    IPPoolListResponse,
    IPPoolOut,
    IPPoolUpdateRequest,
    SortField,
    SortOrder,
    build_ip_pool_out,
)
from app.services import ip_pool as ip_pool_service

router = APIRouter(prefix="/ip-pools", tags=["ip-pools"])

# Non-nullable fields that must not receive an explicit JSON null in PATCH.
_NON_NULLABLE_PATCH_FIELDS = (
    "name",
    "start_address",
    "end_address",
    "allocation_mode",
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


def _build_out(db: Session, ip_pools: list) -> list[IPPoolOut]:
    network_map = ip_pool_service.networks_for(
        db, [ip_pool.network_id for ip_pool in ip_pools]
    )
    return [
        build_ip_pool_out(ip_pool, network_map.get(ip_pool.network_id))
        for ip_pool in ip_pools
    ]


@router.get("", response_model=IPPoolListResponse)
def list_ip_pools(
    network_id: uuid.UUID | None = Query(default=None),
    allocation_mode: AllocationMode | None = Query(default=None),
    q: str | None = Query(default=None),
    deleted: DeletedMode = Query(default="exclude"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    sort: SortField = Query(default="created_at"),
    order: SortOrder = Query(default="desc"),
    operator: Operator = Depends(require_permission(Permission.READ)),
    db: Session = Depends(get_db),
) -> IPPoolListResponse:
    """List ip pools with combined filters/sorting/pagination (§4)."""
    if deleted in ("include", "only"):
        _require_view_deleted(operator)
    items, total = ip_pool_service.list_ip_pools(
        db,
        network_id=network_id,
        allocation_mode=allocation_mode,
        q=q,
        deleted=deleted,
        page=page,
        page_size=page_size,
        sort=sort,
        order=order,
    )
    return IPPoolListResponse(
        items=_build_out(db, items), page=page, page_size=page_size, total=total
    )


@router.post("", response_model=IPPoolEnvelope, status_code=201)
def create_ip_pool(
    payload: IPPoolCreateRequest,
    operator: Operator = Depends(require_permission(Permission.WRITE)),
    db: Session = Depends(get_db),
) -> IPPoolEnvelope:
    """Create an IPPool (201) and write a CREATE audit row."""
    ip_pool = ip_pool_service.create_ip_pool(
        db,
        operator,
        network=payload.network,
        name=payload.name,
        start_address=payload.start_address,
        end_address=payload.end_address,
        allocation_mode=payload.allocation_mode,
        description=payload.description,
    )
    return IPPoolEnvelope(ip_pool=_build_out(db, [ip_pool])[0])


@router.get("/{ip_pool_id}", response_model=IPPoolEnvelope)
def get_ip_pool_detail(
    ip_pool_id: str,
    deleted: bool = Query(default=False),
    operator: Operator = Depends(require_permission(Permission.READ)),
    db: Session = Depends(get_db),
) -> IPPoolEnvelope:
    """IPPool detail; a soft-deleted row needs ``deleted=true`` + VIEW_DELETED."""
    ip_pool_uuid = _parse_uuid(ip_pool_id)
    if deleted:
        _require_view_deleted(operator)
    ip_pool = ip_pool_service.get_ip_pool(
        db, ip_pool_uuid, include_deleted=deleted
    )
    if ip_pool is None:
        raise NotFound()
    return IPPoolEnvelope(ip_pool=_build_out(db, [ip_pool])[0])


@router.patch("/{ip_pool_id}", response_model=IPPoolEnvelope)
def update_ip_pool(
    ip_pool_id: str,
    payload: IPPoolUpdateRequest,
    operator: Operator = Depends(require_permission(Permission.WRITE)),
    db: Session = Depends(get_db),
) -> IPPoolEnvelope:
    """Partial update with mandatory ``version``; immutable fields rejected (422)."""
    ip_pool_uuid = _parse_uuid(ip_pool_id)
    changes = payload.model_dump(exclude_unset=True)
    changes.pop("version", None)
    for field in _NON_NULLABLE_PATCH_FIELDS:
        if field in changes and changes[field] is None:
            raise _validation_field_error(
                field, f"{field} may not be null in a partial update"
            )
    ip_pool = ip_pool_service.update_ip_pool(
        db, operator, ip_pool_uuid, expected_version=payload.version, changes=changes
    )
    return IPPoolEnvelope(ip_pool=_build_out(db, [ip_pool])[0])


@router.delete("/{ip_pool_id}", status_code=204)
def delete_ip_pool(
    ip_pool_id: str,
    version: int = Query(ge=1),
    operator: Operator = Depends(require_permission(Permission.DELETE_OBJECT)),
    db: Session = Depends(get_db),
) -> Response:
    """Soft delete (no cascade, no IP-source reference check; DR-108)."""
    ip_pool_uuid = _parse_uuid(ip_pool_id)
    ip_pool_service.delete_ip_pool(
        db, operator, ip_pool_uuid, expected_version=version
    )
    return Response(status_code=204)


@router.post("/{ip_pool_id}/restore", response_model=IPPoolEnvelope)
def restore_ip_pool(
    ip_pool_id: str,
    version: int = Query(ge=1),
    operator: Operator = Depends(require_permission(Permission.RESTORE)),
    db: Session = Depends(get_db),
) -> IPPoolEnvelope:
    """Restore a soft-deleted IPPool; writes a RESTORE audit row."""
    ip_pool_uuid = _parse_uuid(ip_pool_id)
    ip_pool = ip_pool_service.restore_ip_pool(
        db, operator, ip_pool_uuid, expected_version=version
    )
    return IPPoolEnvelope(ip_pool=_build_out(db, [ip_pool])[0])


@router.get("/{ip_pool_id}/activity", response_model=ActivityListResponse)
def ip_pool_activity(
    ip_pool_id: str,
    deleted: bool = Query(default=False),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    operator: Operator = Depends(require_permission(Permission.VIEW_ACTIVITY)),
    db: Session = Depends(get_db),
) -> ActivityListResponse:
    """Object activity (all roles); soft-deleted needs ``deleted=true``."""
    ip_pool_uuid = _parse_uuid(ip_pool_id)
    if deleted:
        _require_view_deleted(operator)
    ip_pool = ip_pool_service.get_ip_pool(
        db, ip_pool_uuid, include_deleted=deleted
    )
    if ip_pool is None:
        raise NotFound()
    rows, total = ip_pool_service.list_activity(
        db, ip_pool_uuid, page=page, page_size=page_size
    )
    items: list[ActivityItem] = [build_activity_item(row) for row in rows]
    return ActivityListResponse(
        items=items, page=page, page_size=page_size, total=total
    )