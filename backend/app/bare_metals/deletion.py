"""BareMetal 模块的活跃子资源检查声明与父资源侧检查实现（F002 / F006 / F014）。

两件事：

1. ``BARE_METAL_ACTIVE_CHILD_CHECKS``：BareMetal **自身**删除前必须执行的活跃子资源
   检查元组。F006 起包含「该宿主下是否存在活跃 VirtualMachine」检查
   （``has_active_virtual_machines``），使 ``DELETE /api/bare-metals/{id}`` 在宿主有活跃
   VM 时返回 ``409``（R-VM-005 / R-DELETE-004 / AC-28）。后续 F004 / F007 / F008
   落地时在此继续追加各自检查。
2. ``has_active_bare_metals``：供 **Cluster** 删除路径消费的「该 Cluster 下是否存在
   活跃 BareMetal」检查，被 ``app/clusters/deletion.py`` 的
   ``CLUSTER_ACTIVE_CHILD_CHECKS`` 引用（R-DELETE-004 / AC-23 / AC-27）。

子资源模块提供检查函数（``app.virtual_machines.deletion.has_active_virtual_machines``），
父资源模块声明；``app.bare_metals.deletion → app.virtual_machines.deletion →
app.models.virtual_machine``，无循环导入。
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.active import active_filter
from app.deletion.checks import ActiveChildCheck
from app.models.bare_metal import BareMetal
from app.virtual_machines.deletion import has_active_virtual_machines

#: BareMetal 自身的活跃子资源检查（F006 起包含活跃 VirtualMachine）。
BARE_METAL_ACTIVE_CHILD_CHECKS: tuple[ActiveChildCheck, ...] = (has_active_virtual_machines,)


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
