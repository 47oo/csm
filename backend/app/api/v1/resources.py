"""Resource REST endpoints (Contract §6, seven routes).

Routes stay thin: query/body validation, permission checks and response shaping;
all business rules live in :mod:`app.services.resource`.
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
from app.schemas.resource import (
    DeletedMode,
    ResourceCreateRequest,
    ResourceEnvelope,
    ResourceListResponse,
    ResourceOut,
    ResourceType,
    ResourceUpdateRequest,
    SortField,
    SortOrder,
    build_hardware_out,
    build_resource_out,
    build_virtual_machine_out,
)
from app.services import resource as resource_service

router = APIRouter(prefix="/resources", tags=["resources"])

# Non-nullable fields that must not receive an explicit JSON null in PATCH.
_NON_NULLABLE_PATCH_FIELDS = ("hostname", "role", "status", "metadata")


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


def _build_out(db: Session, resources: list) -> list[ResourceOut]:
    cluster_map = resource_service.clusters_for(
        db, [resource.cluster_id for resource in resources]
    )
    detail_map = resource_service.details_for(db, [resource.id for resource in resources])
    vm_detail_map = resource_service.virtual_machine_details_for(
        db, [resource.id for resource in resources]
    )
    host_map = resource_service.hosts_for(
        db, [detail.host_resource_id for detail in vm_detail_map.values()]
    )
    output: list[ResourceOut] = []
    for resource in resources:
        hardware = (
            build_hardware_out(detail_map.get(resource.id))
            if resource.resource_type == "BARE_METAL"
            else None
        )
        virtual_machine = None
        if resource.resource_type == "VIRTUAL_MACHINE":
            vm_detail = vm_detail_map.get(resource.id)
            virtual_machine = build_virtual_machine_out(
                vm_detail,
                host_map.get(vm_detail.host_resource_id) if vm_detail else None,
            )
        output.append(
            build_resource_out(
                resource,
                cluster_map[resource.cluster_id],
                hardware=hardware,
                virtual_machine=virtual_machine,
            )
        )
    return output


@router.get("", response_model=ResourceListResponse)
def list_resources(
    q: str | None = Query(default=None),
    cluster: str | None = Query(default=None),
    cluster_id: uuid.UUID | None = Query(default=None),
    host_resource_id: uuid.UUID | None = Query(default=None),
    type: ResourceType | None = Query(default=None),
    role: str | None = Query(default=None),
    status: str | None = Query(default=None),
    deleted: DeletedMode = Query(default="exclude"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    sort: SortField = Query(default="created_at"),
    order: SortOrder = Query(default="desc"),
    operator: Operator = Depends(require_permission(Permission.READ)),
    db: Session = Depends(get_db),
) -> ResourceListResponse:
    """List resources with combined filters/sorting/pagination (§4)."""
    if deleted in ("include", "only"):
        _require_view_deleted(operator)
    items, total = resource_service.list_resources(
        db,
        q=q,
        cluster=cluster,
        cluster_id=cluster_id,
        host_resource_id=host_resource_id,
        resource_type=type,
        role=role,
        status=status,
        deleted=deleted,
        page=page,
        page_size=page_size,
        sort=sort,
        order=order,
    )
    return ResourceListResponse(
        items=_build_out(db, items),
        page=page,
        page_size=page_size,
        total=total,
    )


@router.post("", response_model=ResourceEnvelope, status_code=201)
def create_resource(
    payload: ResourceCreateRequest,
    operator: Operator = Depends(require_permission(Permission.WRITE)),
    db: Session = Depends(get_db),
) -> ResourceEnvelope:
    """Create a resource (201) and write a CREATE audit row."""
    hardware = (
        payload.hardware.model_dump()
        if "hardware" in payload.model_fields_set
        else None
    )
    virtual_machine = (
        payload.virtual_machine.model_dump()
        if payload.virtual_machine is not None
        else None
    )
    resource = resource_service.create_resource(
        db,
        operator,
        cluster=payload.cluster,
        hostname=payload.hostname,
        resource_type=payload.resource_type,
        role=payload.role,
        status=payload.status,
        description=payload.description,
        metadata=payload.metadata,
        hardware=hardware,
        virtual_machine=virtual_machine,
        virtual_machine_present="virtual_machine" in payload.model_fields_set,
    )
    return ResourceEnvelope(resource=_build_out(db, [resource])[0])


@router.get("/{resource_id}", response_model=ResourceEnvelope)
def get_resource_detail(
    resource_id: str,
    deleted: bool = Query(default=False),
    operator: Operator = Depends(require_permission(Permission.READ)),
    db: Session = Depends(get_db),
) -> ResourceEnvelope:
    """Resource detail; a soft-deleted row needs ``deleted=true`` + VIEW_DELETED."""
    resource_uuid = _parse_uuid(resource_id)
    if deleted:
        _require_view_deleted(operator)
    resource = resource_service.get_resource(
        db, resource_uuid, include_deleted=deleted
    )
    if resource is None:
        raise NotFound()
    return ResourceEnvelope(resource=_build_out(db, [resource])[0])


@router.patch("/{resource_id}", response_model=ResourceEnvelope)
def update_resource(
    resource_id: str,
    payload: ResourceUpdateRequest,
    operator: Operator = Depends(require_permission(Permission.WRITE)),
    db: Session = Depends(get_db),
) -> ResourceEnvelope:
    """Partial update with mandatory ``version``; immutable fields rejected (422)."""
    resource_uuid = _parse_uuid(resource_id)
    changes = payload.model_dump(exclude_unset=True)
    changes.pop("version", None)
    hardware = changes.pop("hardware", None)
    if "hardware" in payload.model_fields_set:
        if payload.hardware is None:
            raise _validation_field_error(
                "hardware", "hardware may not be null in a partial update"
            )
        hardware = payload.hardware.model_dump(exclude_unset=True)
    virtual_machine = changes.pop("virtual_machine", None)
    if "virtual_machine" in payload.model_fields_set:
        if payload.virtual_machine is None:
            raise _validation_field_error(
                "virtual_machine",
                "virtual_machine may not be null in a partial update",
            )
        virtual_machine = payload.virtual_machine.model_dump(exclude_unset=True)
        if (
            "host_resource_id" in virtual_machine
            and virtual_machine["host_resource_id"] is None
        ):
            raise _validation_field_error(
                "virtual_machine.host_resource_id",
                "host_resource_id may not be null in a partial update",
            )
    for field in _NON_NULLABLE_PATCH_FIELDS:
        if field in changes and changes[field] is None:
            raise _validation_field_error(
                field, f"{field} may not be null in a partial update"
            )
    resource = resource_service.update_resource(
        db,
        operator,
        resource_uuid,
        expected_version=payload.version,
        changes=changes,
        hardware=hardware,
        virtual_machine=virtual_machine,
    )
    return ResourceEnvelope(resource=_build_out(db, [resource])[0])


@router.delete("/{resource_id}", status_code=204)
def delete_resource(
    resource_id: str,
    version: int = Query(ge=1),
    operator: Operator = Depends(require_permission(Permission.DELETE_OBJECT)),
    db: Session = Depends(get_db),
) -> Response:
    """Soft delete (no cascade); writes a DELETE audit row."""
    resource_uuid = _parse_uuid(resource_id)
    resource_service.delete_resource(
        db, operator, resource_uuid, expected_version=version
    )
    return Response(status_code=204)


@router.post("/{resource_id}/restore", response_model=ResourceEnvelope)
def restore_resource(
    resource_id: str,
    version: int = Query(ge=1),
    operator: Operator = Depends(require_permission(Permission.RESTORE)),
    db: Session = Depends(get_db),
) -> ResourceEnvelope:
    """Restore a soft-deleted resource; writes a RESTORE audit row."""
    resource_uuid = _parse_uuid(resource_id)
    resource = resource_service.restore_resource(
        db, operator, resource_uuid, expected_version=version
    )
    return ResourceEnvelope(resource=_build_out(db, [resource])[0])


@router.get("/{resource_id}/activity", response_model=ActivityListResponse)
def resource_activity(
    resource_id: str,
    deleted: bool = Query(default=False),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    operator: Operator = Depends(require_permission(Permission.VIEW_ACTIVITY)),
    db: Session = Depends(get_db),
) -> ActivityListResponse:
    """Object activity (all roles); soft-deleted needs ``deleted=true``."""
    resource_uuid = _parse_uuid(resource_id)
    if deleted:
        _require_view_deleted(operator)
    resource = resource_service.get_resource(
        db, resource_uuid, include_deleted=deleted
    )
    if resource is None:
        raise NotFound()
    rows, total = resource_service.list_activity(
        db, resource_uuid, page=page, page_size=page_size
    )
    items: list[ActivityItem] = [build_activity_item(row) for row in rows]
    return ActivityListResponse(
        items=items, page=page, page_size=page_size, total=total
    )