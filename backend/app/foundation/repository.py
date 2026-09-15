"""非产品自检面的数据访问。

使用 F012 的 ``deleted_at IS NULL`` 过滤原语；这是 **fixture-only** 的数据访问，
不是产品软删除领域服务（F014）。

``flush()`` 显式触发，使数据库约束违反（``IntegrityError``）在请求内抛出，
从而经通用 SQLSTATE 映射层返回契约错误。
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.common.pagination import PageParams
from app.db.active import active_filter
from app.models.cluster import Cluster


class ClusterFixtureRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_active(self, cluster_id: int) -> Cluster | None:
        stmt = select(Cluster).where(Cluster.id == cluster_id, active_filter(Cluster))
        return self.session.scalars(stmt).one_or_none()

    def list_active(self, params: PageParams) -> tuple[list[Cluster], int]:
        total = self.session.scalar(
            select(func.count()).select_from(Cluster).where(active_filter(Cluster))
        )
        stmt = (
            select(Cluster)
            .where(active_filter(Cluster))
            .order_by(Cluster.id)
            .offset(params.offset)
            .limit(params.limit)
        )
        return list(self.session.scalars(stmt)), int(total or 0)

    def create(self, name: str) -> Cluster:
        cluster = Cluster(name=name)
        self.session.add(cluster)
        self.session.flush()
        self.session.refresh(cluster)
        return cluster

    def update(self, cluster: Cluster, name: str) -> Cluster:
        cluster.name = name
        self.session.flush()
        self.session.refresh(cluster)
        return cluster

    def soft_delete(self, cluster: Cluster) -> None:
        """仅写 ``deleted_at`` 的自检夹具；**不是**产品软删除语义。"""
        cluster.deleted_at = datetime.now(UTC)
        self.session.flush()
