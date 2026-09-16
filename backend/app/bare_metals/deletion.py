"""BareMetal 模块的活跃子资源检查声明与 Cluster 侧检查实现（F002 / F014）。

两件事：

1. ``BARE_METAL_ACTIVE_CHILD_CHECKS``：BareMetal **自身**删除前必须执行的活跃子资源
   检查元组。当前 NIC / VM / Container / Service 表尚不存在，故**显式**声明为空元组，
   而不是由统一软删服务假定「BareMetal 无子资源」（AC-22 / ADR-0004 §5）。后续
   F004 / F006 / F007 / F008 落地时在此追加各自检查。
2. ``has_active_bare_metals``：供 **Cluster** 删除路径消费的「该 Cluster 下是否存在
   活跃 BareMetal」检查，被 ``app/clusters/deletion.py`` 的
   ``CLUSTER_ACTIVE_CHILD_CHECKS`` 引用（R-DELETE-004 / AC-23 / AC-27）。
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.active import active_filter
from app.deletion.checks import ActiveChildCheck
from app.models.bare_metal import BareMetal

#: BareMetal 自身的活跃子资源检查（当前显式空：NIC / VM / Container / Service 尚不存在）。
BARE_METAL_ACTIVE_CHILD_CHECKS: tuple[ActiveChildCheck, ...] = ()


def has_active_bare_metals(session: Session, cluster_id: int) -> bool:
    """``cluster_id`` 下是否存在 ``deleted_at IS NULL`` 的 BareMetal。

    复用活跃过滤原语；以 ``EXISTS`` 语义（``LIMIT 1``）表达，不取回整行。
    """
    stmt = (
        select(BareMetal.id)
        .where(active_filter(BareMetal), BareMetal.cluster_id == cluster_id)
        .limit(1)
    )
    return session.scalars(stmt).first() is not None
