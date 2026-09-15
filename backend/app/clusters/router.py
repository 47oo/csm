"""Cluster HTTP 路由（5 个产品端点，docs/api/f001-cluster.md §3）。

- ``by-name`` 路由**声明在** ``/{cluster_id}`` **之前**（防御性约定）。
- **不注册** ``DELETE /api/clusters/{id}``（删除语义属 F014）。
- 所有端点位于 ``/api`` 前缀下（由 ``app.main`` 挂载），供 F013 的
  ``/api/*`` 认证中间件自动覆盖，无需白名单。
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Path, status
from sqlalchemy.orm import Session

from app.api.deps import get_db_session
from app.clusters import service
from app.clusters.schemas import ClusterCreate, ClusterRead, ClusterUpdate
from app.common.pagination import Page, PageParams, page_params

router = APIRouter(prefix="/clusters", tags=["clusters"])

SessionDep = Annotated[Session, Depends(get_db_session)]
PageDep = Annotated[PageParams, Depends(page_params)]
ClusterId = Annotated[int, Path(description="Cluster 代理主键 id")]


@router.post("", response_model=ClusterRead, status_code=status.HTTP_201_CREATED)
def create_cluster(payload: ClusterCreate, session: SessionDep) -> ClusterRead:
    cluster = service.create_cluster(session, payload.name)
    return ClusterRead.model_validate(cluster)


@router.get("", response_model=Page[ClusterRead])
def list_clusters(session: SessionDep, params: PageDep) -> Page[ClusterRead]:
    items, total = service.list_clusters(session, params)
    return Page[ClusterRead](
        items=[ClusterRead.model_validate(item) for item in items],
        total=total,
        page=params.page,
        page_size=params.page_size,
    )


# 只读名称别名：必须声明在 /{cluster_id} 之前。
@router.get("/by-name/{cluster_name}", response_model=ClusterRead)
def get_cluster_by_name(cluster_name: str, session: SessionDep) -> ClusterRead:
    return ClusterRead.model_validate(service.get_cluster_by_name(session, cluster_name))


@router.get("/{cluster_id}", response_model=ClusterRead)
def get_cluster(cluster_id: ClusterId, session: SessionDep) -> ClusterRead:
    return ClusterRead.model_validate(service.get_cluster_by_id(session, cluster_id))


@router.patch("/{cluster_id}", response_model=ClusterRead)
def update_cluster(
    cluster_id: ClusterId, payload: ClusterUpdate, session: SessionDep
) -> ClusterRead:
    cluster = service.update_cluster(session, cluster_id, payload.name)
    return ClusterRead.model_validate(cluster)
