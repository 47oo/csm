"""F009 Cluster 视角 HTTP 路由（``docs/api/f009-cluster-resource-view.md`` §3）。

只注册**一条**只读端点 ``GET /api/clusters/by-name/{cluster_name}/bare-metals``
（由 ``app.main`` 以 ``/api`` 前缀挂载），供 F013 的 ``/api/*`` 认证中间件自动
覆盖，无需白名单。

- ``response_model`` 与 canonical ``GET /api/bare-metals`` 逐字段一致
  （``Page[BareMetalRead]``）。
- **不提供** 写 / 删除 / 恢复别名；**不注册** NIC / IP / VM / Container / Service
  端点或占位。
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_db_session
from app.bare_metals.schemas import BareMetalRead
from app.cluster_views import service
from app.common.pagination import Page, PageParams, page_params

router = APIRouter(prefix="/clusters", tags=["cluster-views"])

SessionDep = Annotated[Session, Depends(get_db_session)]
PageDep = Annotated[PageParams, Depends(page_params)]


@router.get("/by-name/{cluster_name}/bare-metals", response_model=Page[BareMetalRead])
def list_cluster_bare_metals_by_name(
    cluster_name: str, session: SessionDep, params: PageDep
) -> Page[BareMetalRead]:
    items, total = service.list_cluster_bare_metals_by_name(session, params, cluster_name)
    return Page[BareMetalRead](
        items=[BareMetalRead.model_validate(item) for item in items],
        total=total,
        page=params.page,
        page_size=params.page_size,
    )
