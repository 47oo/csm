"""F010 资源详情与关联查询 HTTP 路由（``docs/api/f010-resource-detail.md`` §2）。

只注册**一条**只读端点 ``GET /api/bare-metals/{bare_metal_id}/related``
（由 ``app.main`` 以 ``/api`` 前缀挂载），供 F013 的 ``/api/*`` 认证中间件自动
覆盖，无需白名单。

- 无请求体、无 query 参数；仅路径参数 ``bare_metal_id``。
- ``response_model`` 为 :class:`RelatedResourcesRead`（顶层五类，各 ``{items, total}``，
  元素类型复用既有 canonical ``*Read``）。
- **不提供** 写 / 删除 / 恢复 / 解绑别名；**不注册**五个子资源端点或占位。
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Path
from sqlalchemy.orm import Session

from app.api.deps import get_db_session
from app.resource_views import service
from app.resource_views.schemas import RelatedResourcesRead

router = APIRouter(prefix="/bare-metals", tags=["resource-views"])

SessionDep = Annotated[Session, Depends(get_db_session)]
BareMetalId = Annotated[int, Path(description="BareMetal 代理主键 id")]


@router.get("/{bare_metal_id}/related", response_model=RelatedResourcesRead)
def get_bare_metal_related(bare_metal_id: BareMetalId, session: SessionDep) -> RelatedResourcesRead:
    return service.get_related_resources(session, bare_metal_id)
