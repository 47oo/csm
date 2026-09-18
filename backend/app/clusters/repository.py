"""Cluster 数据访问。

读取路径**必须**通过 ``app/db/active.py`` 的 ``active_filter`` / ``select_active``
表达「活跃」（ADR-0004 §3 / F001 REQUIRED #2）；本模块不重写
``deleted_at.is_(None)`` 的第二份谓词。

写入只有 ``create`` 与 ``update``（改名）。**不存在**写入 ``deleted_at`` 的方法
（删除领域语义唯一归属 F014）。
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.common.pagination import PageParams
from app.db.active import active_filter, select_active
from app.models.cluster import Cluster


class ClusterRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_active(self, cluster_id: int) -> Cluster | None:
        stmt = select_active(Cluster).where(Cluster.id == cluster_id)
        return self.session.scalars(stmt).one_or_none()

    def get_active_by_name(self, name: str) -> Cluster | None:
        stmt = select_active(Cluster).where(Cluster.name == name)
        return self.session.scalars(stmt).one_or_none()

    def active_name_exists(self, name: str, *, exclude_id: int | None = None) -> bool:
        """活跃范围内是否已存在该名称（大小写敏感，字面值等值）。"""
        stmt = select_active(Cluster).where(Cluster.name == name)
        if exclude_id is not None:
            stmt = stmt.where(Cluster.id != exclude_id)
        return self.session.scalars(stmt.limit(1)).first() is not None

    def list_active(self, params: PageParams) -> tuple[list[Cluster], int]:
        total = self.session.scalar(
            select(func.count()).select_from(Cluster).where(active_filter(Cluster))
        )
        stmt = select_active(Cluster).order_by(Cluster.id).offset(params.offset).limit(params.limit)
        return list(self.session.scalars(stmt)), int(total or 0)

    def create(self, name: str) -> Cluster:
        cluster = Cluster(name=name)
        self.session.add(cluster)
        # flush 让数据库约束（partial unique / CHECK）在请求内抛出，
        # 从而经通用 SQLSTATE 映射返回契约错误（数据库为最终权威）。
        self.session.flush()
        self.session.refresh(cluster)
        return cluster

    def update(self, cluster: Cluster, name: str) -> Cluster:
        cluster.name = name
        self.session.flush()
        self.session.refresh(cluster)
        return cluster
