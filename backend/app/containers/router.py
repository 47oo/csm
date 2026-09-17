"""Container HTTP 路由（``docs/api/f007-container.md`` §4）。

5 个端点：``POST`` / ``GET`` / ``GET {id}`` / ``PATCH {id}`` / ``DELETE {id}``。
所有端点位于 ``/api`` 前缀下（由 ``app.main`` 挂载），供 F013 的 ``/api/*``
认证中间件自动覆盖，无需白名单。

- ``GET`` 支持成对 ``carrier_type`` + ``carrier_id`` 载体限定读取（R-QUERY-003 的
  F007 侧 canonical 能力；供 F010 复用）。
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
from app.containers import service
from app.containers.schemas import (
    CarrierType,
    ContainerCreate,
    ContainerRead,
    ContainerUpdate,
)

router = APIRouter(prefix="/containers", tags=["containers"])

SessionDep = Annotated[Session, Depends(get_db_session)]
PageDep = Annotated[PageParams, Depends(page_params)]
ContainerId = Annotated[int, Path(description="Container 代理主键 id")]
CarrierTypeQuery = Annotated[
    CarrierType | None, Query(description="载体类型；必须与 carrier_id 成对提供")
]
CarrierIdQuery = Annotated[int | None, Query(description="载体 id；必须与 carrier_type 成对提供")]


@router.post("", response_model=ContainerRead, status_code=status.HTTP_201_CREATED)
def create_container(payload: ContainerCreate, session: SessionDep) -> ContainerRead:
    container = service.create_container(session, payload)
    return ContainerRead.from_model(container)


@router.get("", response_model=Page[ContainerRead])
def list_containers(
    session: SessionDep,
    params: PageDep,
    carrier_type: CarrierTypeQuery = None,
    carrier_id: CarrierIdQuery = None,
) -> Page[ContainerRead]:
    items, total = service.list_containers(
        session, params, carrier_type=carrier_type, carrier_id=carrier_id
    )
    return Page[ContainerRead](
        items=[ContainerRead.from_model(item) for item in items],
        total=total,
        page=params.page,
        page_size=params.page_size,
    )


@router.get("/{container_id}", response_model=ContainerRead)
def get_container(container_id: ContainerId, session: SessionDep) -> ContainerRead:
    return ContainerRead.from_model(service.get_container_by_id(session, container_id))


@router.patch("/{container_id}", response_model=ContainerRead)
def update_container(
    container_id: ContainerId,
    payload: ContainerUpdate,
    session: SessionDep,
) -> ContainerRead:
    container = service.update_container(session, container_id, payload)
    return ContainerRead.from_model(container)


# F014：逻辑删除，成功 204（无响应体）。删除守卫由后端裁决（§21）。
@router.delete("/{container_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_container(container_id: ContainerId, session: SessionDep) -> None:
    service.delete_container(session, container_id)
