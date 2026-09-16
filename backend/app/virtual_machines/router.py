"""VirtualMachine HTTP 路由（``docs/api/f006-virtual-machine.md`` §3）。

5 个端点：``POST`` / ``GET`` / ``GET {id}`` / ``PATCH {id}`` / ``DELETE {id}``。
所有端点位于 ``/api`` 前缀下（由 ``app.main`` 挂载），供 F013 的 ``/api/*``
认证中间件自动覆盖，无需白名单。

- ``GET`` 支持可选 ``bare_metal_id`` 宿主限定读取（R-QUERY-003 的 F006 侧
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
from app.virtual_machines import service
from app.virtual_machines.schemas import (
    VirtualMachineCreate,
    VirtualMachineRead,
    VirtualMachineUpdate,
)

router = APIRouter(prefix="/virtual-machines", tags=["virtual-machines"])

SessionDep = Annotated[Session, Depends(get_db_session)]
PageDep = Annotated[PageParams, Depends(page_params)]
VirtualMachineId = Annotated[int, Path(description="VirtualMachine 代理主键 id")]
BareMetalIdQuery = Annotated[
    int | None, Query(description="按宿主限定读取；宿主不存在 / 已删 → 404")
]


@router.post("", response_model=VirtualMachineRead, status_code=status.HTTP_201_CREATED)
def create_virtual_machine(
    payload: VirtualMachineCreate, session: SessionDep
) -> VirtualMachineRead:
    virtual_machine = service.create_virtual_machine(session, payload)
    return VirtualMachineRead.model_validate(virtual_machine)


@router.get("", response_model=Page[VirtualMachineRead])
def list_virtual_machines(
    session: SessionDep, params: PageDep, bare_metal_id: BareMetalIdQuery = None
) -> Page[VirtualMachineRead]:
    items, total = service.list_virtual_machines(session, params, bare_metal_id=bare_metal_id)
    return Page[VirtualMachineRead](
        items=[VirtualMachineRead.model_validate(item) for item in items],
        total=total,
        page=params.page,
        page_size=params.page_size,
    )


@router.get("/{virtual_machine_id}", response_model=VirtualMachineRead)
def get_virtual_machine(
    virtual_machine_id: VirtualMachineId, session: SessionDep
) -> VirtualMachineRead:
    return VirtualMachineRead.model_validate(
        service.get_virtual_machine_by_id(session, virtual_machine_id)
    )


@router.patch("/{virtual_machine_id}", response_model=VirtualMachineRead)
def update_virtual_machine(
    virtual_machine_id: VirtualMachineId,
    payload: VirtualMachineUpdate,
    session: SessionDep,
) -> VirtualMachineRead:
    virtual_machine = service.update_virtual_machine(session, virtual_machine_id, payload)
    return VirtualMachineRead.model_validate(virtual_machine)


# F014：逻辑删除，成功 204（无响应体）。删除守卫由后端裁决（§21）。
@router.delete("/{virtual_machine_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_virtual_machine(virtual_machine_id: VirtualMachineId, session: SessionDep) -> None:
    service.delete_virtual_machine(session, virtual_machine_id)
