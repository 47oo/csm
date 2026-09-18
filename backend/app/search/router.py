"""F018 集群内资源关键字搜索 HTTP 路由（``docs/api/f018-cluster-keyword-search.md``）。

只注册**一条**只读端点 ``GET /api/clusters/{cluster_id}/search``（由
``app.main`` 以 ``/api`` 前缀挂载），供 F013 的 ``/api/*`` 认证中间件自动覆盖。

- 参数封闭：``cluster_id``（path）+ ``keyword``（必填）+ ``page`` / ``page_size``。
- 状态优先级：401（中间件，先于路由）> 400（空 / 仅空白 keyword，先于 404）>
  404（Cluster 解析）> 200（含无命中 Empty）。
- **不提供** 写 / 删除 / 恢复端点；**不** 给任何既有端点追加 ``keyword``。
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query
from sqlalchemy.orm import Session

from app.api.deps import get_db_session
from app.common.errors import ValidationError
from app.common.pagination import Page, PageParams, page_params
from app.search import service
from app.search.schemas import SearchResultItem

router = APIRouter(prefix="/clusters", tags=["search"])

SessionDep = Annotated[Session, Depends(get_db_session)]
PageDep = Annotated[PageParams, Depends(page_params)]
ClusterId = Annotated[int, Path(description="Cluster 代理主键 id")]
Keyword = Annotated[str, Query(description="关键字（必填，非空且非仅空白）")]


@router.get("/{cluster_id}/search", response_model=Page[SearchResultItem])
def search_cluster_resources(
    cluster_id: ClusterId,
    keyword: Keyword,
    session: SessionDep,
    params: PageDep,
) -> Page[SearchResultItem]:
    """在单个 Cluster 内按关键字搜索；空 / 仅空白关键字 → 400（先于 404）。"""
    if keyword.strip() == "":
        raise ValidationError(
            details=[{"field": "keyword", "code": "INVALID", "message": "关键字不能为空"}]
        )
    items, total = service.search_cluster_resources(session, cluster_id, keyword, params)
    return Page[SearchResultItem](
        items=items, total=total, page=params.page, page_size=params.page_size
    )
