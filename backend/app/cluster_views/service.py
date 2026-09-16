"""F009 Cluster 视角成员读取业务行为。

判定顺序固定：**先**名称解析（未命中 / 已删 → ``404``），**后**读取该 Cluster
的活跃 BareMetal —— 成员读取**委托** F002 的 ``list_bare_metals``（其内部再次
执行父 Cluster 活跃复检），由此获得与 canonical 一致的 404-vs-Empty 判定、
并发稳定性与同一条 ``deleted_at IS NULL`` 过滤路径。

本模块刻意不出现任何 ``deleted_at`` 表达式：活跃过滤只经
``app/db/active.py`` 与既有 service 传递（ADR-0004）。
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.bare_metals import service as bare_metals_service
from app.clusters import service as clusters_service
from app.common.pagination import PageParams
from app.models.bare_metal import BareMetal


def list_cluster_bare_metals_by_name(
    session: Session, params: PageParams, cluster_name: str
) -> tuple[list[BareMetal], int]:
    """按 Cluster 名称返回其活跃 BareMetal 分页结果。

    1. ``get_cluster_by_name``：字面值等值、大小写敏感、仅活跃；未命中 → ``404``。
    2. 委托 ``list_bare_metals(cluster_id=...)``：Cluster 存在但无活跃成员 →
       ``200`` + 空集合（Empty）。
    """
    cluster = clusters_service.get_cluster_by_name(session, cluster_name)
    return bare_metals_service.list_bare_metals(session, params, cluster_id=cluster.id)
