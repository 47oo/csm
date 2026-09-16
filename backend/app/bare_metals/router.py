"""BareMetal HTTP 路由（``docs/api/f002-bare-metal.md`` §3）。

5 个端点：``POST`` / ``GET`` / ``GET {id}`` / ``PATCH {id}`` / ``DELETE {id}``。
所有端点位于 ``/api`` 前缀下（由 ``app.main`` 挂载），供 F013 的 ``/api/*``
认证中间件自动覆盖，无需白名单。

- **不提供** 全局 ``by-name`` 别名（``hostname`` 仅按 Cluster 唯一）。
- **不提供** restore / undelete / purge / 批量删除 / ``include_deleted``。
- 写操作一律走 ``id``（ADR-0003 §2）。
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_db_session
from app.bare_metals import service
from app.bare_metals.schemas import BareMetalCreate, BareMetalRead, BareMetalUpdate
from app.common.pagination import Page, PageParams, page_params

router = APIRouter(prefix="/bare-metals", tags=["bare-metals"])

SessionDep = Annotated[Session, Depends(get_db_session)]
PageDep = Annotated[PageParams, Depends(page_params)]
BareMetalId = Annotated[int, Path(description="BareMetal 代理主键 id")]
ClusterIdQuery = Annotated[
    int | None, Query(description="按 Cluster 限定读取；Cluster 不存在 / 已删 → 404")
]


@router.post("", response_model=BareMetalRead, status_code=status.HTTP_201_CREATED)
def create_bare_metal(payload: BareMetalCreate, session: SessionDep) -> BareMetalRead:
    bare_metal = service.create_bare_metal(session, payload)
    return BareMetalRead.model_validate(bare_metal)


@router.get("", response_model=Page[BareMetalRead])
def list_bare_metals(
    session: SessionDep, params: PageDep, cluster_id: ClusterIdQuery = None
) -> Page[BareMetalRead]:
    items, total = service.list_bare_metals(session, params, cluster_id=cluster_id)
    return Page[BareMetalRead](
        items=[BareMetalRead.model_validate(item) for item in items],
        total=total,
        page=params.page,
        page_size=params.page_size,
    )


@router.get("/{bare_metal_id}", response_model=BareMetalRead)
def get_bare_metal(bare_metal_id: BareMetalId, session: SessionDep) -> BareMetalRead:
    return BareMetalRead.model_validate(service.get_bare_metal_by_id(session, bare_metal_id))


@router.patch("/{bare_metal_id}", response_model=BareMetalRead)
def update_bare_metal(
    bare_metal_id: BareMetalId, payload: BareMetalUpdate, session: SessionDep
) -> BareMetalRead:
    bare_metal = service.update_bare_metal(session, bare_metal_id, payload)
    return BareMetalRead.model_validate(bare_metal)


# F014：逻辑删除，成功 204（无响应体）。删除守卫由后端裁决（§21）。
@router.delete("/{bare_metal_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_bare_metal(bare_metal_id: BareMetalId, session: SessionDep) -> None:
    service.delete_bare_metal(session, bare_metal_id)
