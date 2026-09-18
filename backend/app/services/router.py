"""Service HTTP 路由（``docs/api/f008-service.md`` §4）。

5 个端点：``POST`` / ``GET`` / ``GET {id}`` / ``PATCH {id}`` / ``DELETE {id}``。
所有端点位于 ``/api`` 前缀下（由 ``app.main`` 挂载），供 F013 的 ``/api/*``
认证中间件自动覆盖，无需白名单。

- ``GET`` 支持成对 ``carrier_type`` + ``carrier_id`` 载体限定读取（R-QUERY-003 的
  canonical 能力；供 F010 复用）。
- **不提供** 全局 ``by-name`` 别名、``name`` 重命名、载体解绑 / 替换 / 批量改绑。
- **不提供** restore / undelete / purge / 批量删除 / ``include_deleted``。
- 写操作一律走 ``id``（ADR-0003 §2）。
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_db_session
from app.common.pagination import Page, PageParams, page_params
from app.services import service
from app.services.repository import ServiceRepository
from app.services.schemas import (
    ServiceCarrierType,
    ServiceCreate,
    ServiceRead,
    ServiceUpdate,
)

router = APIRouter(prefix="/services", tags=["services"])

SessionDep = Annotated[Session, Depends(get_db_session)]
PageDep = Annotated[PageParams, Depends(page_params)]
ServiceId = Annotated[int, Path(description="Service 代理主键 id")]
CarrierTypeQuery = Annotated[
    ServiceCarrierType | None, Query(description="载体类型；必须与 carrier_id 成对提供")
]
CarrierIdQuery = Annotated[int | None, Query(description="载体 id；必须与 carrier_type 成对提供")]


def _read(session: Session, instance) -> ServiceRead:  # noqa: ANN001 - ORM Service
    return ServiceRead.from_model(instance, service.carriers_of(session, instance))


@router.post("", response_model=ServiceRead, status_code=status.HTTP_201_CREATED)
def create_service(payload: ServiceCreate, session: SessionDep) -> ServiceRead:
    created = service.create_service(session, payload)
    return _read(session, created)


@router.get("", response_model=Page[ServiceRead])
def list_services(
    session: SessionDep,
    params: PageDep,
    carrier_type: CarrierTypeQuery = None,
    carrier_id: CarrierIdQuery = None,
) -> Page[ServiceRead]:
    items, total = service.list_services(
        session, params, carrier_type=carrier_type, carrier_id=carrier_id
    )
    carriers_by_service = ServiceRepository(session).carriers_for_services(
        [item.id for item in items]
    )
    return Page[ServiceRead](
        items=[
            ServiceRead.from_model(item, carriers_by_service.get(item.id, [])) for item in items
        ],
        total=total,
        page=params.page,
        page_size=params.page_size,
    )


@router.get("/{service_id}", response_model=ServiceRead)
def get_service(service_id: ServiceId, session: SessionDep) -> ServiceRead:
    return _read(session, service.get_service_by_id(session, service_id))


@router.patch("/{service_id}", response_model=ServiceRead)
def update_service(
    service_id: ServiceId,
    payload: ServiceUpdate,
    session: SessionDep,
) -> ServiceRead:
    updated = service.update_service(session, service_id, payload)
    return _read(session, updated)


# F014：逻辑删除，成功 204（无响应体）。删除守卫由后端裁决（§21）。
@router.delete("/{service_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_service(service_id: ServiceId, session: SessionDep) -> None:
    service.delete_service(session, service_id)
