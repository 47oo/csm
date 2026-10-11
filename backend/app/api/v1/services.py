"""Service REST endpoints (Contract §6, seven routes).

Routes stay thin: query/body validation, permission checks and response shaping;
all business rules live in :mod:`app.services.service`.
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
from app.schemas.service import (
    DeletedMode,
    ServiceCreateRequest,
    ServiceEnvelope,
    ServiceListResponse,
    ServiceOut,
    ServiceStatus,
    ServiceUpdateRequest,
    SortField,
    SortOrder,
    build_service_out,
)
from app.services import service as service_service

router = APIRouter(prefix="/services", tags=["services"])

# Non-nullable fields that must not receive an explicit JSON null in PATCH.
_NON_NULLABLE_PATCH_FIELDS = ("name", "status", "metadata")


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


def _build_out(db: Session, services: list) -> list[ServiceOut]:
    resource_map = service_service.resources_for(
        db, [service.resource_id for service in services]
    )
    return [
        build_service_out(service, resource_map.get(service.resource_id))
        for service in services
    ]


@router.get("", response_model=ServiceListResponse)
def list_services(
    resource_id: uuid.UUID | None = Query(default=None),
    status: ServiceStatus | None = Query(default=None),
    q: str | None = Query(default=None),
    deleted: DeletedMode = Query(default="exclude"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    sort: SortField = Query(default="created_at"),
    order: SortOrder = Query(default="desc"),
    operator: Operator = Depends(require_permission(Permission.READ)),
    db: Session = Depends(get_db),
) -> ServiceListResponse:
    """List services with combined filters/sorting/pagination (§4)."""
    if deleted in ("include", "only"):
        _require_view_deleted(operator)
    items, total = service_service.list_services(
        db,
        resource_id=resource_id,
        status=status,
        q=q,
        deleted=deleted,
        page=page,
        page_size=page_size,
        sort=sort,
        order=order,
    )
    return ServiceListResponse(
        items=_build_out(db, items), page=page, page_size=page_size, total=total
    )


@router.post("", response_model=ServiceEnvelope, status_code=201)
def create_service(
    payload: ServiceCreateRequest,
    operator: Operator = Depends(require_permission(Permission.WRITE)),
    db: Session = Depends(get_db),
) -> ServiceEnvelope:
    """Create a Service (201) and write a CREATE audit row."""
    service = service_service.create_service(
        db,
        operator,
        resource=payload.resource,
        name=payload.name,
        status=payload.status,
        description=payload.description,
        metadata=payload.metadata,
    )
    return ServiceEnvelope(service=_build_out(db, [service])[0])


@router.get("/{service_id}", response_model=ServiceEnvelope)
def get_service_detail(
    service_id: str,
    deleted: bool = Query(default=False),
    operator: Operator = Depends(require_permission(Permission.READ)),
    db: Session = Depends(get_db),
) -> ServiceEnvelope:
    """Service detail; a soft-deleted row needs ``deleted=true`` + VIEW_DELETED."""
    service_uuid = _parse_uuid(service_id)
    if deleted:
        _require_view_deleted(operator)
    service = service_service.get_service(db, service_uuid, include_deleted=deleted)
    if service is None:
        raise NotFound()
    return ServiceEnvelope(service=_build_out(db, [service])[0])


@router.patch("/{service_id}", response_model=ServiceEnvelope)
def update_service(
    service_id: str,
    payload: ServiceUpdateRequest,
    operator: Operator = Depends(require_permission(Permission.WRITE)),
    db: Session = Depends(get_db),
) -> ServiceEnvelope:
    """Partial update with mandatory ``version``; immutable fields rejected (422)."""
    service_uuid = _parse_uuid(service_id)
    changes = payload.model_dump(exclude_unset=True)
    changes.pop("version", None)
    for field in _NON_NULLABLE_PATCH_FIELDS:
        if field in changes and changes[field] is None:
            raise _validation_field_error(
                field, f"{field} may not be null in a partial update"
            )
    service = service_service.update_service(
        db, operator, service_uuid, expected_version=payload.version, changes=changes
    )
    return ServiceEnvelope(service=_build_out(db, [service])[0])


@router.delete("/{service_id}", status_code=204)
def delete_service(
    service_id: str,
    version: int = Query(ge=1),
    operator: Operator = Depends(require_permission(Permission.DELETE_OBJECT)),
    db: Session = Depends(get_db),
) -> Response:
    """Soft delete (no cascade); blocked by undeleted ServiceEndpoint references."""
    service_uuid = _parse_uuid(service_id)
    service_service.delete_service(
        db, operator, service_uuid, expected_version=version
    )
    return Response(status_code=204)


@router.post("/{service_id}/restore", response_model=ServiceEnvelope)
def restore_service(
    service_id: str,
    version: int = Query(ge=1),
    operator: Operator = Depends(require_permission(Permission.RESTORE)),
    db: Session = Depends(get_db),
) -> ServiceEnvelope:
    """Restore a soft-deleted Service; writes a RESTORE audit row."""
    service_uuid = _parse_uuid(service_id)
    service = service_service.restore_service(
        db, operator, service_uuid, expected_version=version
    )
    return ServiceEnvelope(service=_build_out(db, [service])[0])


@router.get("/{service_id}/activity", response_model=ActivityListResponse)
def service_activity(
    service_id: str,
    deleted: bool = Query(default=False),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    operator: Operator = Depends(require_permission(Permission.VIEW_ACTIVITY)),
    db: Session = Depends(get_db),
) -> ActivityListResponse:
    """Object activity (all roles); soft-deleted needs ``deleted=true``."""
    service_uuid = _parse_uuid(service_id)
    if deleted:
        _require_view_deleted(operator)
    service = service_service.get_service(db, service_uuid, include_deleted=deleted)
    if service is None:
        raise NotFound()
    rows, total = service_service.list_activity(
        db, service_uuid, page=page, page_size=page_size
    )
    items: list[ActivityItem] = [build_activity_item(row) for row in rows]
    return ActivityListResponse(
        items=items, page=page, page_size=page_size, total=total
    )