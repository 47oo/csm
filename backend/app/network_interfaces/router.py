"""NetworkInterface HTTP 路由（``docs/api/f004-network-interface.md`` §3）。

5 个端点：``POST`` / ``GET`` / ``GET {id}`` / ``PATCH {id}`` / ``DELETE {id}``。
所有端点位于 ``/api`` 前缀下（由 ``app.main`` 挂载），供 F013 的 ``/api/*``
认证中间件自动覆盖，无需白名单。

- ``GET`` 支持可选 ``bare_metal_id`` 宿主限定读取（R-QUERY-003 的 F004 侧
  canonical 能力；供 F010 复用）。
- **不提供** 全局 ``by-name`` 别名。
- **不提供** restore / undelete / purge / 批量删除 / ``include_deleted``。
- 写操作一律走 ``id``（ADR-0003 §2）。
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_db_session
from app.common.pagination import Page, PageParams, page_params
from app.network_interfaces import service
from app.network_interfaces.schemas import (
    NetworkInterfaceCreate,
    NetworkInterfaceRead,
    NetworkInterfaceUpdate,
)

router = APIRouter(prefix="/network-interfaces", tags=["network-interfaces"])

SessionDep = Annotated[Session, Depends(get_db_session)]
PageDep = Annotated[PageParams, Depends(page_params)]
NetworkInterfaceId = Annotated[int, Path(description="NetworkInterface 代理主键 id")]
BareMetalIdQuery = Annotated[
    int | None, Query(description="按宿主限定读取；宿主不存在 / 已删 → 404")
]


@router.post("", response_model=NetworkInterfaceRead, status_code=status.HTTP_201_CREATED)
def create_network_interface(
    payload: NetworkInterfaceCreate, session: SessionDep
) -> NetworkInterfaceRead:
    network_interface = service.create_network_interface(session, payload)
    return NetworkInterfaceRead.model_validate(network_interface)


@router.get("", response_model=Page[NetworkInterfaceRead])
def list_network_interfaces(
    session: SessionDep, params: PageDep, bare_metal_id: BareMetalIdQuery = None
) -> Page[NetworkInterfaceRead]:
    items, total = service.list_network_interfaces(session, params, bare_metal_id=bare_metal_id)
    return Page[NetworkInterfaceRead](
        items=[NetworkInterfaceRead.model_validate(item) for item in items],
        total=total,
        page=params.page,
        page_size=params.page_size,
    )


@router.get("/{network_interface_id}", response_model=NetworkInterfaceRead)
def get_network_interface(
    network_interface_id: NetworkInterfaceId, session: SessionDep
) -> NetworkInterfaceRead:
    return NetworkInterfaceRead.model_validate(
        service.get_network_interface_by_id(session, network_interface_id)
    )


@router.patch("/{network_interface_id}", response_model=NetworkInterfaceRead)
def update_network_interface(
    network_interface_id: NetworkInterfaceId,
    payload: NetworkInterfaceUpdate,
    session: SessionDep,
) -> NetworkInterfaceRead:
    network_interface = service.update_network_interface(session, network_interface_id, payload)
    return NetworkInterfaceRead.model_validate(network_interface)


# F014：逻辑删除，成功 204（无响应体）。删除守卫由后端裁决（§21）。
@router.delete("/{network_interface_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_network_interface(network_interface_id: NetworkInterfaceId, session: SessionDep) -> None:
    service.delete_network_interface(session, network_interface_id)
