"""Interface REST endpoints (Contract §6, seven routes).

Routes stay thin: query/body validation, permission checks and response shaping;
all business rules live in :mod:`app.services.interface`.
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
from app.schemas.interface import (
    DeletedMode,
    InterfaceCreateRequest,
    InterfaceEnvelope,
    InterfaceListResponse,
    InterfaceOut,
    InterfaceType,
    InterfaceUpdateRequest,
    SortField,
    SortOrder,
    build_interface_out,
)
from app.services import interface as interface_service

router = APIRouter(prefix="/interfaces", tags=["interfaces"])

# Non-nullable fields that must not receive an explicit JSON null in PATCH.
_NON_NULLABLE_PATCH_FIELDS = ("name", "interface_type", "enabled", "metadata")


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


def _build_out(db: Session, interfaces: list) -> list[InterfaceOut]:
    resource_map = interface_service.resources_for(
        db, [interface.resource_id for interface in interfaces]
    )
    parent_map = interface_service.parents_for(
        db, [interface.parent_interface_id for interface in interfaces]
    )
    return [
        build_interface_out(
            interface,
            resource_map.get(interface.resource_id),
            parent_map.get(interface.parent_interface_id)
            if interface.parent_interface_id is not None
            else None,
        )
        for interface in interfaces
    ]


@router.get("", response_model=InterfaceListResponse)
def list_interfaces(
    resource_id: uuid.UUID | None = Query(default=None),
    interface_type: InterfaceType | None = Query(default=None),
    enabled: bool | None = Query(default=None),
    q: str | None = Query(default=None),
    parent_interface_id: uuid.UUID | None = Query(default=None),
    deleted: DeletedMode = Query(default="exclude"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    sort: SortField = Query(default="created_at"),
    order: SortOrder = Query(default="desc"),
    operator: Operator = Depends(require_permission(Permission.READ)),
    scope: AccessScope = Depends(get_access_scope),
    db: Session = Depends(get_db),
) -> InterfaceListResponse:
    """List interfaces with combined filters/sorting/pagination (§4)."""
    if deleted in ("include", "only"):
        _require_view_deleted(operator)
    items, total = interface_service.list_interfaces(
        db,
        resource_id=resource_id,
        interface_type=interface_type,
        enabled=enabled,
        q=q,
        parent_interface_id=parent_interface_id,
        deleted=deleted,
        page=page,
        page_size=page_size,
        sort=sort,
        order=order,
        scope=scope,
    )
    return InterfaceListResponse(
        items=_build_out(db, items),
        page=page,
        page_size=page_size,
        total=total,
    )


@router.post("", response_model=InterfaceEnvelope, status_code=201)
def create_interface(
    payload: InterfaceCreateRequest,
    operator: Operator = Depends(require_permission(Permission.WRITE)),
    scope: AccessScope = Depends(get_access_scope),
    db: Session = Depends(get_db),
) -> InterfaceEnvelope:
    """Create an Interface (201) and write a CREATE audit row."""
    interface = interface_service.create_interface(
        db,
        operator,
        resource=payload.resource,
        name=payload.name,
        interface_type=payload.interface_type,
        mac_address=payload.mac_address,
        speed_mbps=payload.speed_mbps,
        mtu=payload.mtu,
        parent_interface=payload.parent_interface,
        enabled=payload.enabled,
        description=payload.description,
        metadata=payload.metadata,
        scope=scope,
    )
    return InterfaceEnvelope(interface=_build_out(db, [interface])[0])


@router.get("/{interface_id}", response_model=InterfaceEnvelope)
def get_interface_detail(
    interface_id: str,
    deleted: bool = Query(default=False),
    operator: Operator = Depends(require_permission(Permission.READ)),
    scope: AccessScope = Depends(get_access_scope),
    db: Session = Depends(get_db),
) -> InterfaceEnvelope:
    """Interface detail; a soft-deleted row needs ``deleted=true`` + VIEW_DELETED."""
    interface_uuid = _parse_uuid(interface_id)
    if deleted:
        _require_view_deleted(operator)
    interface = interface_service.get_interface(
        db, interface_uuid, include_deleted=deleted, scope=scope
    )
    if interface is None:
        raise NotFound()
    return InterfaceEnvelope(interface=_build_out(db, [interface])[0])


@router.patch("/{interface_id}", response_model=InterfaceEnvelope)
def update_interface(
    interface_id: str,
    payload: InterfaceUpdateRequest,
    operator: Operator = Depends(require_permission(Permission.WRITE)),
    scope: AccessScope = Depends(get_access_scope),
    db: Session = Depends(get_db),
) -> InterfaceEnvelope:
    """Partial update with mandatory ``version``; immutable fields rejected (422)."""
    interface_uuid = _parse_uuid(interface_id)
    changes = payload.model_dump(exclude_unset=True)
    changes.pop("version", None)
    for field in _NON_NULLABLE_PATCH_FIELDS:
        if field in changes and changes[field] is None:
            raise _validation_field_error(
                field, f"{field} may not be null in a partial update"
            )
    interface = interface_service.update_interface(
        db,
        operator,
        interface_uuid,
        expected_version=payload.version,
        changes=changes,
        scope=scope,
    )
    return InterfaceEnvelope(interface=_build_out(db, [interface])[0])


@router.delete("/{interface_id}", status_code=204)
def delete_interface(
    interface_id: str,
    version: int = Query(ge=1),
    operator: Operator = Depends(require_permission(Permission.DELETE_OBJECT)),
    scope: AccessScope = Depends(get_access_scope),
    db: Session = Depends(get_db),
) -> Response:
    """Soft delete (no cascade); writes a DELETE audit row."""
    interface_uuid = _parse_uuid(interface_id)
    interface_service.delete_interface(
        db, operator, interface_uuid, expected_version=version, scope=scope
    )
    return Response(status_code=204)


@router.post("/{interface_id}/restore", response_model=InterfaceEnvelope)
def restore_interface(
    interface_id: str,
    version: int = Query(ge=1),
    operator: Operator = Depends(require_permission(Permission.RESTORE)),
    scope: AccessScope = Depends(get_access_scope),
    db: Session = Depends(get_db),
) -> InterfaceEnvelope:
    """Restore a soft-deleted Interface; writes a RESTORE audit row."""
    interface_uuid = _parse_uuid(interface_id)
    interface = interface_service.restore_interface(
        db, operator, interface_uuid, expected_version=version, scope=scope
    )
    return InterfaceEnvelope(interface=_build_out(db, [interface])[0])


@router.get("/{interface_id}/activity", response_model=ActivityListResponse)
def interface_activity(
    interface_id: str,
    deleted: bool = Query(default=False),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    operator: Operator = Depends(require_permission(Permission.VIEW_ACTIVITY)),
    scope: AccessScope = Depends(get_access_scope),
    db: Session = Depends(get_db),
) -> ActivityListResponse:
    """Object activity (all roles); soft-deleted needs ``deleted=true``."""
    interface_uuid = _parse_uuid(interface_id)
    if deleted:
        _require_view_deleted(operator)
    interface = interface_service.get_interface(
        db, interface_uuid, include_deleted=deleted, scope=scope
    )
    if interface is None:
        raise NotFound()
    rows, total = interface_service.list_activity(
        db, interface_uuid, page=page, page_size=page_size
    )
    items: list[ActivityItem] = [build_activity_item(row) for row in rows]
    return ActivityListResponse(
        items=items, page=page, page_size=page_size, total=total
    )