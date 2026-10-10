"""IPAddress REST endpoints (Contract §6, eight routes) + capacity endpoint.

Routes stay thin: query/body validation, permission checks and response shaping;
all business rules live in :mod:`app.services.ip_address` and
:mod:`app.services.ip_capacity`.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from app.core.auth import Operator
from app.core.db import get_db
from app.core.errors import Forbidden, NotFound
from app.core.permissions import Permission, require_permission, role_has_permission
from app.schemas.cluster import (
    ActivityItem,
    ActivityListResponse,
    build_activity_item,
)
from app.schemas.ip_address import (
    AutoPoolCapacityBlock,
    CapacityIpPoolNested,
    CapacityNetworkNested,
    DeletedMode,
    IPAddressAutoAllocateRequest,
    IPAddressCreateRequest,
    IPAddressEnvelope,
    IPAddressListResponse,
    IPAddressOut,
    IPAddressUpdateRequest,
    NetworkCapacityBlock,
    NetworkCapacityResponse,
    SortField,
    SortOrder,
    build_ip_address_out,
)
from app.services import ip_address as ip_address_service
from app.services import ip_capacity as ip_capacity_service
from app.services import network as network_service

router = APIRouter(prefix="/ip-addresses", tags=["ip-addresses"])
capacity_router = APIRouter(prefix="/networks", tags=["ip-addresses"])


def _parse_uuid(value: str) -> uuid.UUID:
    """A non-UUID path segment is reported as 404 (Contract §6)."""
    try:
        return uuid.UUID(value)
    except (ValueError, AttributeError, TypeError) as exc:
        raise NotFound() from exc


def _require_view_deleted(operator: Operator) -> None:
    if not role_has_permission(operator.role, Permission.VIEW_DELETED):
        raise Forbidden(reason="permission")


def _build_out(db: Session, ip_addresses: list) -> list[IPAddressOut]:
    network_map = ip_address_service.networks_for(
        db, [ip.network_id for ip in ip_addresses]
    )
    cluster_map = ip_address_service.clusters_for(
        db, [ip.cluster_id for ip in ip_addresses]
    )
    interface_map = ip_address_service.interfaces_for(
        db, [ip.interface_id for ip in ip_addresses]
    )
    resource_map = ip_address_service.resources_for(
        db, [iface.resource_id for iface in interface_map.values()]
    )
    pool_map = ip_address_service.ip_pools_for(
        db, [ip.ip_pool_id for ip in ip_addresses]
    )
    out: list[IPAddressOut] = []
    for ip in ip_addresses:
        interface = interface_map.get(ip.interface_id) if ip.interface_id else None
        resource = (
            resource_map.get(interface.resource_id)
            if interface is not None
            else None
        )
        pool = pool_map.get(ip.ip_pool_id) if ip.ip_pool_id else None
        out.append(
            build_ip_address_out(
                ip,
                network_map.get(ip.network_id),
                cluster_map.get(ip.cluster_id),
                interface,
                resource,
                pool,
            )
        )
    return out


@router.get("", response_model=IPAddressListResponse)
def list_ip_addresses(
    network_id: uuid.UUID | None = Query(default=None),
    cluster_id: uuid.UUID | None = Query(default=None),
    interface_id: uuid.UUID | None = Query(default=None),
    ip_pool_id: uuid.UUID | None = Query(default=None),
    address: str | None = Query(default=None),
    bound: bool | None = Query(default=None),
    q: str | None = Query(default=None),
    deleted: DeletedMode = Query(default="exclude"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    sort: SortField = Query(default="created_at"),
    order: SortOrder = Query(default="desc"),
    operator: Operator = Depends(require_permission(Permission.READ)),
    db: Session = Depends(get_db),
) -> IPAddressListResponse:
    """List ip addresses with combined filters/sorting/pagination (§4)."""
    if deleted in ("include", "only"):
        _require_view_deleted(operator)
    items, total = ip_address_service.list_ip_addresses(
        db,
        network_id=network_id,
        cluster_id=cluster_id,
        interface_id=interface_id,
        ip_pool_id=ip_pool_id,
        address=address,
        bound=bound,
        q=q,
        deleted=deleted,
        page=page,
        page_size=page_size,
        sort=sort,
        order=order,
    )
    return IPAddressListResponse(
        items=_build_out(db, items), page=page, page_size=page_size, total=total
    )


@router.post("", response_model=IPAddressEnvelope, status_code=201)
def create_ip_address(
    payload: IPAddressCreateRequest,
    operator: Operator = Depends(require_permission(Permission.WRITE)),
    db: Session = Depends(get_db),
) -> IPAddressEnvelope:
    """Manual allocation (201); creates an unbound IP + CREATE audit row."""
    ip_address = ip_address_service.create_ip_address(
        db,
        operator,
        network=payload.network,
        address=payload.address,
        description=payload.description,
    )
    return IPAddressEnvelope(ip_address=_build_out(db, [ip_address])[0])


@router.post("/auto-allocate", response_model=IPAddressEnvelope, status_code=201)
def auto_allocate_ip_address(
    payload: IPAddressAutoAllocateRequest,
    operator: Operator = Depends(require_permission(Permission.WRITE)),
    db: Session = Depends(get_db),
) -> IPAddressEnvelope:
    """Automatic allocation from an AUTO pool (201) + CREATE audit row."""
    ip_address = ip_address_service.auto_allocate_ip_address(
        db,
        operator,
        network=payload.network,
        ip_pool=payload.ip_pool,
        description=payload.description,
    )
    return IPAddressEnvelope(ip_address=_build_out(db, [ip_address])[0])


@router.get("/{ip_address_id}", response_model=IPAddressEnvelope)
def get_ip_address_detail(
    ip_address_id: str,
    deleted: bool = Query(default=False),
    operator: Operator = Depends(require_permission(Permission.READ)),
    db: Session = Depends(get_db),
) -> IPAddressEnvelope:
    """IPAddress detail; soft-deleted needs ``deleted=true`` + VIEW_DELETED."""
    ip_uuid = _parse_uuid(ip_address_id)
    if deleted:
        _require_view_deleted(operator)
    ip_address = ip_address_service.get_ip_address(
        db, ip_uuid, include_deleted=deleted
    )
    if ip_address is None:
        raise NotFound()
    return IPAddressEnvelope(ip_address=_build_out(db, [ip_address])[0])


@router.patch("/{ip_address_id}", response_model=IPAddressEnvelope)
def update_ip_address(
    ip_address_id: str,
    payload: IPAddressUpdateRequest,
    operator: Operator = Depends(require_permission(Permission.WRITE)),
    db: Session = Depends(get_db),
) -> IPAddressEnvelope:
    """Bind/unbind/transfer an Interface or edit ``description`` (WRITE)."""
    ip_uuid = _parse_uuid(ip_address_id)
    changes = payload.model_dump(exclude_unset=True)
    changes.pop("version", None)
    ip_address = ip_address_service.update_ip_address(
        db, operator, ip_uuid, expected_version=payload.version, changes=changes
    )
    return IPAddressEnvelope(ip_address=_build_out(db, [ip_address])[0])


@router.delete("/{ip_address_id}", status_code=204)
def delete_ip_address(
    ip_address_id: str,
    version: int = Query(ge=1),
    operator: Operator = Depends(require_permission(Permission.RELEASE_IP)),
    db: Session = Depends(get_db),
) -> Response:
    """Release an IP = soft delete (ADMIN / RELEASE_IP)."""
    ip_uuid = _parse_uuid(ip_address_id)
    ip_address_service.delete_ip_address(
        db, operator, ip_uuid, expected_version=version
    )
    return Response(status_code=204)


@router.post("/{ip_address_id}/restore", response_model=IPAddressEnvelope)
def restore_ip_address(
    ip_address_id: str,
    version: int = Query(ge=1),
    operator: Operator = Depends(require_permission(Permission.RESTORE)),
    db: Session = Depends(get_db),
) -> IPAddressEnvelope:
    """Restore a soft-deleted IPAddress; writes a RESTORE audit row."""
    ip_uuid = _parse_uuid(ip_address_id)
    ip_address = ip_address_service.restore_ip_address(
        db, operator, ip_uuid, expected_version=version
    )
    return IPAddressEnvelope(ip_address=_build_out(db, [ip_address])[0])


@router.get("/{ip_address_id}/activity", response_model=ActivityListResponse)
def ip_address_activity(
    ip_address_id: str,
    deleted: bool = Query(default=False),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    operator: Operator = Depends(require_permission(Permission.VIEW_ACTIVITY)),
    db: Session = Depends(get_db),
) -> ActivityListResponse:
    """Object activity (all roles); soft-deleted needs ``deleted=true``."""
    ip_uuid = _parse_uuid(ip_address_id)
    if deleted:
        _require_view_deleted(operator)
    ip_address = ip_address_service.get_ip_address(
        db, ip_uuid, include_deleted=deleted
    )
    if ip_address is None:
        raise NotFound()
    rows, total = ip_address_service.list_activity(
        db, ip_uuid, page=page, page_size=page_size
    )
    items: list[ActivityItem] = [build_activity_item(row) for row in rows]
    return ActivityListResponse(
        items=items, page=page, page_size=page_size, total=total
    )


@capacity_router.get(
    "/{network_id}/capacity", response_model=NetworkCapacityResponse
)
def network_capacity(
    network_id: str,
    operator: Operator = Depends(require_permission(Permission.READ)),
    db: Session = Depends(get_db),
) -> NetworkCapacityResponse:
    """§20 capacity data for a Network; soft-deleted Network returns 404."""
    network_uuid = _parse_uuid(network_id)
    network = network_service.get_network(db, network_uuid)
    if network is None:
        raise NotFound()

    capacity = ip_capacity_service.network_capacity(db, network)
    auto_pools = ip_capacity_service.auto_pools_capacity(db, network)
    return NetworkCapacityResponse(
        network_capacity=NetworkCapacityBlock(
            network=CapacityNetworkNested(
                id=network.id,
                name=network.name,
                cidr=str(network.cidr),
                status=network.status,
                auto_allocate=network.auto_allocate,
            ),
            allocatable_total=capacity["allocatable_total"],
            occupied=capacity["occupied"],
            remaining=capacity["remaining"],
        ),
        auto_pools=[
            AutoPoolCapacityBlock(
                ip_pool=CapacityIpPoolNested(
                    id=pool["ip_pool"].id,
                    name=pool["ip_pool"].name,
                    start_address=str(pool["ip_pool"].start_address),
                    end_address=str(pool["ip_pool"].end_address),
                ),
                allocatable_total=pool["allocatable_total"],
                occupied=pool["occupied"],
                remaining=pool["remaining"],
            )
            for pool in auto_pools
        ],
    )