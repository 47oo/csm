"""Cluster 业务行为：登记 / 列表 / 按 id 读取 / 按名称读取 / 改名。

不负责 HTTP 展示文案；不写入 ``deleted_at``（删除语义属 F014）。
领域校验统一委托 ``app.clusters.validation``（唯一实现入口）。
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.clusters import validation
from app.clusters.repository import ClusterRepository
from app.common.errors import NotFoundError
from app.common.pagination import PageParams
from app.models.cluster import Cluster


def create_cluster(session: Session, name: str) -> Cluster:
    repository = ClusterRepository(session)
    validation.validate_name_characters(name)
    validation.ensure_active_name_available(repository, name)
    return repository.create(name)


def list_clusters(session: Session, params: PageParams) -> tuple[list[Cluster], int]:
    return ClusterRepository(session).list_active(params)


def get_cluster_by_id(session: Session, cluster_id: int) -> Cluster:
    cluster = ClusterRepository(session).get_active(cluster_id)
    if cluster is None:
        # 「不存在」与「已逻辑删除」一律 404，不做区分（契约 §3.3）。
        raise NotFoundError()
    return cluster


def get_cluster_by_name(session: Session, name: str) -> Cluster:
    cluster = ClusterRepository(session).get_active_by_name(name)
    if cluster is None:
        raise NotFoundError()
    return cluster


def update_cluster(session: Session, cluster_id: int, name: str) -> Cluster:
    repository = ClusterRepository(session)
    cluster = repository.get_active(cluster_id)
    if cluster is None:
        raise NotFoundError()
    validation.validate_name_characters(name)
    validation.ensure_active_name_available(repository, name, exclude_id=cluster.id)
    return repository.update(cluster, name)
