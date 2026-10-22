"""ServiceEndpoint REST endpoints (Contract §6, seven routes).

Routes stay thin: query/body validation, permission checks and response shaping;
all business rules live in :mod:`app.services.service_endpoint`.
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
from app.schemas.service_endpoint import (
    DeletedMode,
    ServiceEndpointCreateRequest,
    ServiceEndpointEnvelope,
    ServiceEndpointListResponse,
    ServiceEndpointOut,
    ServiceEndpointUpdateRequest,
    SortField,
    SortOrder,
    build_service_endpoint_out,
)
from app.services import service_endpoint as service_endpoint_service

router = APIRouter(prefix="/service-endpoints", tags=["service-endpoints"])

# Non-nullable fields that must not receive an explicit JSON null in PATCH.
_NON_NULLABLE_PATCH_FIELDS = service_endpoint_service.NON_NULLABLE_PATCH_FIELDS


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


def _build_out(db: Session, endpoints: list) -> list[ServiceEndpointOut]:
    service_map = service_endpoint_service.services_for(
        db, [endpoint.service_id for endpoint in endpoints]
    )
    resource_map = service_endpoint_service.resources_for(
        db, [service.resource_id for service in service_map.values()]
    )
    ip_map = service_endpoint_service.ip_addresses_for(
        db, [endpoint.ip_address_id for endpoint in endpoints]
    )
    network_map = service_endpoint_service.networks_for(
        db, [ip.network_id for ip in ip_map.values()]
    )
    interface_map = service_endpoint_service.interfaces_for(
        db, [ip.interface_id for ip in ip_map.values()]
    )
    out: list[ServiceEndpointOut] = []
    for endpoint in endpoints:
        service = service_map.get(endpoint.service_id)
        resource = resource_map.get(service.resource_id) if service is not None else None
        ip = ip_map.get(endpoint.ip_address_id)
        network = network_map.get(ip.network_id) if ip is not None else None
        interface = (
            interface_map.get(ip.interface_id)
            if ip is not None and ip.interface_id is not None
            else None
        )
        out.append(
            build_service_endpoint_out(
                endpoint, service, resource, ip, network, interface
            )
        )
    return out


@router.get("", response_model=ServiceEndpointListResponse)
def list_service_endpoints(
    service_id: uuid.UUID | None = Query(default=None),
    ip_address_id: uuid.UUID | None = Query(default=None),
    protocol: str | None = Query(default=None),
    deleted: DeletedMode = Query(default="exclude"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    sort: SortField = Query(default="created_at"),
    order: SortOrder = Query(default="desc"),
    operator: Operator = Depends(require_permission(Permission.READ)),
    scope: AccessScope = Depends(get_access_scope),
    db: Session = Depends(get_db),
) -> ServiceEndpointListResponse:
    """List service endpoints with combined filters/sorting/pagination (§4)."""
    if deleted in ("include", "only"):
        _require_view_deleted(operator)
    items, total = service_endpoint_service.list_service_endpoints(
        db,
        service_id=service_id,
        ip_address_id=ip_address_id,
        protocol=protocol,
        deleted=deleted,
        page=page,
        page_size=page_size,
        sort=sort,
        order=order,
        scope=scope,
    )
    return ServiceEndpointListResponse(
        items=_build_out(db, items), page=page, page_size=page_size, total=total
    )


@router.post("", response_model=ServiceEndpointEnvelope, status_code=201)
def create_service_endpoint(
    payload: ServiceEndpointCreateRequest,
    operator: Operator = Depends(require_permission(Permission.WRITE)),
    scope: AccessScope = Depends(get_access_scope),
    db: Session = Depends(get_db),
) -> ServiceEndpointEnvelope:
    """Create a ServiceEndpoint (201) and write a CREATE audit row."""
    endpoint = service_endpoint_service.create_service_endpoint(
        db,
        operator,
        service=payload.service,
        ip_address=payload.ip_address,
        protocol=payload.protocol,
        port=payload.port,
        description=payload.description,
        scope=scope,
    )
    return ServiceEndpointEnvelope(
        service_endpoint=_build_out(db, [endpoint])[0]
    )


@router.get("/{endpoint_id}", response_model=ServiceEndpointEnvelope)
def get_service_endpoint_detail(
    endpoint_id: str,
    deleted: bool = Query(default=False),
    operator: Operator = Depends(require_permission(Permission.READ)),
    scope: AccessScope = Depends(get_access_scope),
    db: Session = Depends(get_db),
) -> ServiceEndpointEnvelope:
    """Endpoint detail; a soft-deleted row needs ``deleted=true`` + VIEW_DELETED."""
    endpoint_uuid = _parse_uuid(endpoint_id)
    if deleted:
        _require_view_deleted(operator)
    endpoint = service_endpoint_service.get_service_endpoint(
        db, endpoint_uuid, include_deleted=deleted, scope=scope
    )
    if endpoint is None:
        raise NotFound()
    return ServiceEndpointEnvelope(
        service_endpoint=_build_out(db, [endpoint])[0]
    )


@router.patch("/{endpoint_id}", response_model=ServiceEndpointEnvelope)
def update_service_endpoint(
    endpoint_id: str,
    payload: ServiceEndpointUpdateRequest,
    operator: Operator = Depends(require_permission(Permission.WRITE)),
    scope: AccessScope = Depends(get_access_scope),
    db: Session = Depends(get_db),
) -> ServiceEndpointEnvelope:
    """Partial update with mandatory ``version``; immutable fields rejected (422)."""
    endpoint_uuid = _parse_uuid(endpoint_id)
    changes = payload.model_dump(exclude_unset=True)
    changes.pop("version", None)
    for field in _NON_NULLABLE_PATCH_FIELDS:
        if field in changes and changes[field] is None:
            raise _validation_field_error(
                field, f"{field} may not be null in a partial update"
            )
    endpoint = service_endpoint_service.update_service_endpoint(
        db,
        operator,
        endpoint_uuid,
        expected_version=payload.version,
        changes=changes,
        scope=scope,
    )
    return ServiceEndpointEnvelope(
        service_endpoint=_build_out(db, [endpoint])[0]
    )


@router.delete("/{endpoint_id}", status_code=204)
def delete_service_endpoint(
    endpoint_id: str,
    version: int = Query(ge=1),
    operator: Operator = Depends(require_permission(Permission.DELETE_OBJECT)),
    scope: AccessScope = Depends(get_access_scope),
    db: Session = Depends(get_db),
) -> Response:
    """Soft delete an Endpoint (no cascade); no child object references it."""
    endpoint_uuid = _parse_uuid(endpoint_id)
    service_endpoint_service.delete_service_endpoint(
        db, operator, endpoint_uuid, expected_version=version, scope=scope
    )
    return Response(status_code=204)


@router.post("/{endpoint_id}/restore", response_model=ServiceEndpointEnvelope)
def restore_service_endpoint(
    endpoint_id: str,
    version: int = Query(ge=1),
    operator: Operator = Depends(require_permission(Permission.RESTORE)),
    scope: AccessScope = Depends(get_access_scope),
    db: Session = Depends(get_db),
) -> ServiceEndpointEnvelope:
    """Restore a soft-deleted Endpoint; writes a RESTORE audit row."""
    endpoint_uuid = _parse_uuid(endpoint_id)
    endpoint = service_endpoint_service.restore_service_endpoint(
        db, operator, endpoint_uuid, expected_version=version, scope=scope
    )
    return ServiceEndpointEnvelope(
        service_endpoint=_build_out(db, [endpoint])[0]
    )


@router.get("/{endpoint_id}/activity", response_model=ActivityListResponse)
def service_endpoint_activity(
    endpoint_id: str,
    deleted: bool = Query(default=False),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    operator: Operator = Depends(require_permission(Permission.VIEW_ACTIVITY)),
    scope: AccessScope = Depends(get_access_scope),
    db: Session = Depends(get_db),
) -> ActivityListResponse:
    """Object activity (all roles); soft-deleted needs ``deleted=true``."""
    endpoint_uuid = _parse_uuid(endpoint_id)
    if deleted:
        _require_view_deleted(operator)
    endpoint = service_endpoint_service.get_service_endpoint(
        db, endpoint_uuid, include_deleted=deleted, scope=scope
    )
    if endpoint is None:
        raise NotFound()
    rows, total = service_endpoint_service.list_activity(
        db, endpoint_uuid, page=page, page_size=page_size
    )
    items: list[ActivityItem] = [build_activity_item(row) for row in rows]
    return ActivityListResponse(
        items=items, page=page, page_size=page_size, total=total
    )