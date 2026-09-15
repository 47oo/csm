"""非产品自检面 ``/_foundation/*``（架构 Handoff 核心裁定层 2）。

**这不是产品契约。**
- 仅在 dev / test 配置下挂载；生产配置下不存在（404）。
- 不含任何资源领域规则（无 ``/`` 校验、无唯一性预检、无 ``by-name``、无状态、
  无父删子拦）。
- ``clusters`` 表仅作为基座验证载体使用。
- F001 交付产品 Cluster API 后应移除或降级为测试夹具（``Removal owner: F001``）。

前缀刻意置于 ``/api`` 之外，避免与资源约定及 F013 认证范围交互。
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Response, status
from sqlalchemy.orm import Session

from app.api.deps import get_db_session
from app.common.errors import InternalError, NotFoundError
from app.common.pagination import Page, PageParams, page_params
from app.foundation.repository import ClusterFixtureRepository
from app.foundation.schemas import (
    ClusterFixtureCreate,
    ClusterFixtureRead,
    ClusterFixtureUpdate,
)

router = APIRouter(prefix="/_foundation", tags=["_foundation (non-product, dev/test only)"])

SessionDep = Annotated[Session, Depends(get_db_session)]
PageDep = Annotated[PageParams, Depends(page_params)]
ClusterId = Annotated[int, Path(description="载体行 id")]


def _repo(session: Session) -> ClusterFixtureRepository:
    return ClusterFixtureRepository(session)


@router.post("/clusters", response_model=ClusterFixtureRead, status_code=status.HTTP_201_CREATED)
def create_cluster(payload: ClusterFixtureCreate, session: SessionDep) -> ClusterFixtureRead:
    cluster = _repo(session).create(payload.name)
    return ClusterFixtureRead.model_validate(cluster)


@router.get("/clusters", response_model=Page[ClusterFixtureRead])
def list_clusters(session: SessionDep, params: PageDep) -> Page[ClusterFixtureRead]:
    items, total = _repo(session).list_active(params)
    return Page[ClusterFixtureRead](
        items=[ClusterFixtureRead.model_validate(item) for item in items],
        total=total,
        page=params.page,
        page_size=params.page_size,
    )


@router.get("/clusters/{cluster_id}", response_model=ClusterFixtureRead)
def get_cluster(cluster_id: ClusterId, session: SessionDep) -> ClusterFixtureRead:
    cluster = _repo(session).get_active(cluster_id)
    if cluster is None:
        raise NotFoundError()
    return ClusterFixtureRead.model_validate(cluster)


@router.patch("/clusters/{cluster_id}", response_model=ClusterFixtureRead)
def update_cluster(
    cluster_id: ClusterId, payload: ClusterFixtureUpdate, session: SessionDep
) -> ClusterFixtureRead:
    repo = _repo(session)
    cluster = repo.get_active(cluster_id)
    if cluster is None:
        raise NotFoundError()
    return ClusterFixtureRead.model_validate(repo.update(cluster, payload.name))


@router.delete("/clusters/{cluster_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_cluster(cluster_id: ClusterId, session: SessionDep) -> Response:
    repo = _repo(session)
    cluster = repo.get_active(cluster_id)
    if cluster is None:
        raise NotFoundError()
    repo.soft_delete(cluster)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/error")
def trigger_error() -> None:
    """始终 500 INTERNAL_ERROR，供前端渲染 Error 态。"""
    raise InternalError("自检触发：确定性服务端错误")
