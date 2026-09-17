"""IPAddress HTTP 路由（``docs/api/f005-ip-address.md`` §3）。

5 个端点：``POST`` / ``GET`` / ``GET {id}`` / ``PATCH {id}`` / ``DELETE {id}``。
所有端点位于 ``/api`` 前缀下（由 ``app.main`` 挂载），供 F013 的 ``/api/*``
认证中间件自动覆盖，无需白名单。

- ``GET`` 支持可选 ``network_interface_id`` 父限定读取（R-QUERY-004 的 F005 侧
  canonical 能力；供 F010 复用）。
- **不提供** 全局 ``by-name`` 别名（``ip_address`` 非全局唯一）。
- **不提供** restore / undelete / purge / 批量删除 / ``include_deleted``。
- **不提供** ``cluster_id`` / VRF / 状态 / IP 前缀等第二维度过滤。
- 写操作一律走 ``id``（ADR-0003 §2）。
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_db_session
from app.common.pagination import Page, PageParams, page_params
from app.ip_addresses import service
from app.ip_addresses.schemas import IpAddressCreate, IpAddressRead, IpAddressUpdate

router = APIRouter(prefix="/ip-addresses", tags=["ip-addresses"])

SessionDep = Annotated[Session, Depends(get_db_session)]
PageDep = Annotated[PageParams, Depends(page_params)]
IpAddressId = Annotated[int, Path(description="IPAddress 代理主键 id")]
NetworkInterfaceIdQuery = Annotated[
    int | None, Query(description="按父 NetworkInterface 限定读取；父不存在 / 已删 → 404")
]


@router.post("", response_model=IpAddressRead, status_code=status.HTTP_201_CREATED)
def create_ip_address(payload: IpAddressCreate, session: SessionDep) -> IpAddressRead:
    ip = service.create_ip_address(session, payload)
    return IpAddressRead.model_validate(ip)


@router.get("", response_model=Page[IpAddressRead])
def list_ip_addresses(
    session: SessionDep, params: PageDep, network_interface_id: NetworkInterfaceIdQuery = None
) -> Page[IpAddressRead]:
    items, total = service.list_ip_addresses(
        session, params, network_interface_id=network_interface_id
    )
    return Page[IpAddressRead](
        items=[IpAddressRead.model_validate(item) for item in items],
        total=total,
        page=params.page,
        page_size=params.page_size,
    )


@router.get("/{ip_address_id}", response_model=IpAddressRead)
def get_ip_address(ip_address_id: IpAddressId, session: SessionDep) -> IpAddressRead:
    return IpAddressRead.model_validate(service.get_ip_address_by_id(session, ip_address_id))


@router.patch("/{ip_address_id}", response_model=IpAddressRead)
def update_ip_address(
    ip_address_id: IpAddressId, payload: IpAddressUpdate, session: SessionDep
) -> IpAddressRead:
    ip = service.update_ip_address(session, ip_address_id, payload)
    return IpAddressRead.model_validate(ip)


# F014：逻辑删除，成功 204（无响应体）。删除守卫由后端裁决（§21）。
@router.delete("/{ip_address_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_ip_address(ip_address_id: IpAddressId, session: SessionDep) -> None:
    service.delete_ip_address(session, ip_address_id)
