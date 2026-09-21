"""IPAddressRange HTTP 路由（``docs/api/f020-ip-address-range.md`` §3）。

5 个端点：``POST`` / ``GET`` / ``GET {id}`` / ``PATCH {id}`` / ``DELETE {id}``。
所有端点位于 ``/api`` 前缀下（由 ``app.main`` 挂载），供 F013 的 ``/api/*``
认证中间件自动覆盖，无需白名单。

- ``GET`` 支持可选 ``cluster_id`` 父限定读取（存在但无活跃范围段 → 200 空集；
  父不存在 / 已软删 → 404，R-QUERY-004）。
- **不提供** ``by-name`` / restore / undelete / purge / 批量删除 / ``include_deleted``。
- **不提供** ``status`` / CIDR / 关键字 / 排序 / 分配状态等第二维度查询参数。
- 写操作一律走 ``id``（ADR-0003 §2）。
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_db_session
from app.common.pagination import Page, PageParams, page_params
from app.ip_address_ranges import service
from app.ip_address_ranges.schemas import (
    IpAddressRangeCreate,
    IpAddressRangeRead,
    IpAddressRangeUpdate,
)

router = APIRouter(prefix="/ip-address-ranges", tags=["ip-address-ranges"])

SessionDep = Annotated[Session, Depends(get_db_session)]
PageDep = Annotated[PageParams, Depends(page_params)]
IpAddressRangeId = Annotated[int, Path(description="IPAddressRange 代理主键 id")]
ClusterIdQuery = Annotated[
    int | None, Query(description="按所属 Cluster 限定读取；父不存在 / 已删 → 404")
]


@router.post("", response_model=IpAddressRangeRead, status_code=status.HTTP_201_CREATED)
def create_ip_address_range(
    payload: IpAddressRangeCreate, session: SessionDep
) -> IpAddressRangeRead:
    ip_address_range = service.create_ip_address_range(session, payload)
    return IpAddressRangeRead.from_model(ip_address_range)


@router.get("", response_model=Page[IpAddressRangeRead])
def list_ip_address_ranges(
    session: SessionDep, params: PageDep, cluster_id: ClusterIdQuery = None
) -> Page[IpAddressRangeRead]:
    items, total = service.list_ip_address_ranges(session, params, cluster_id=cluster_id)
    return Page[IpAddressRangeRead](
        items=[IpAddressRangeRead.from_model(item) for item in items],
        total=total,
        page=params.page,
        page_size=params.page_size,
    )


@router.get("/{ip_address_range_id}", response_model=IpAddressRangeRead)
def get_ip_address_range(
    ip_address_range_id: IpAddressRangeId, session: SessionDep
) -> IpAddressRangeRead:
    return IpAddressRangeRead.from_model(
        service.get_ip_address_range_by_id(session, ip_address_range_id)
    )


@router.patch("/{ip_address_range_id}", response_model=IpAddressRangeRead)
def update_ip_address_range(
    ip_address_range_id: IpAddressRangeId,
    payload: IpAddressRangeUpdate,
    session: SessionDep,
) -> IpAddressRangeRead:
    ip_address_range = service.update_ip_address_range(session, ip_address_range_id, payload)
    return IpAddressRangeRead.from_model(ip_address_range)


# F014：逻辑删除，成功 204（无响应体）。删除守卫由后端裁决（§21）。
@router.delete("/{ip_address_range_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_ip_address_range(ip_address_range_id: IpAddressRangeId, session: SessionDep) -> None:
    service.delete_ip_address_range(session, ip_address_range_id)
