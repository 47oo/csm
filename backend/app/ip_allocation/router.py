"""F006 网段已分配 IP 只读端点（Contract docs/api/F006.md §3）。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..errors import problem
from ..models import IpAddress, NetworkInterface, NetworkSegment, Resource
from ..security.principal import Principal, get_current_user
from .addressing import ipv4_to_int
from .schemas import AllocatedIpItem, PagedAllocatedIps

router = APIRouter(prefix="/network-segments", tags=["ip-allocation"])


@router.get("/{segment_id}/allocated-ips", response_model=PagedAllocatedIps)
def list_allocated_ips(
    segment_id: int,
    page: int = Query(1),
    page_size: int = Query(20),
    q: str | None = Query(None),
    db: Session = Depends(get_db),
    _user: Principal = Depends(get_current_user),
) -> PagedAllocatedIps:
    if page < 1 or page_size < 1 or page_size > 100:
        raise problem(400, "INVALID_REQUEST", "非法的分页参数")

    if db.get(NetworkSegment, segment_id) is None:
        raise problem(404, "SEGMENT_NOT_FOUND", "网段不存在")

    rows = db.execute(
        select(IpAddress, NetworkInterface, Resource)
        .join(NetworkInterface, NetworkInterface.id == IpAddress.interface_id)
        .join(Resource, Resource.id == IpAddress.resource_id)
        .where(IpAddress.segment_id == segment_id)
    ).all()

    needle = q.strip().lower() if q and q.strip() else None
    items: list[dict] = []
    for ip, interface, resource in rows:
        if needle is not None:
            haystacks = (
                ip.ip.lower(),
                resource.name.lower(),
                interface.name.lower(),
            )
            if not any(needle in value for value in haystacks):
                continue
        items.append(
            {
                "ip_id": ip.id,
                "address": ip.ip,
                "resource_id": ip.resource_id,
                "resource_name": resource.name,
                "resource_type": resource.resource_type,
                "interface_id": ip.interface_id,
                "interface_name": interface.name,
                "is_management": resource.management_ip_id == ip.id,
                "created_at": ip.created_at,
            }
        )

    items.sort(key=lambda item: ipv4_to_int(item["address"]))
    total = len(items)
    start = (page - 1) * page_size
    page_items = items[start : start + page_size]
    return PagedAllocatedIps(
        items=[AllocatedIpItem.model_validate(item) for item in page_items],
        total=total,
        page=page,
        page_size=page_size,
    )