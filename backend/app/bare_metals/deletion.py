"""BareMetal 模块的活跃子资源检查声明与父资源侧检查实现（F002 / F006 / F004 / F014）。

两件事：

1. ``BARE_METAL_ACTIVE_CHILD_CHECKS``：BareMetal **自身**删除前必须执行的活跃子资源
   检查元组。F006 起包含「该宿主下是否存在活跃 VirtualMachine」检查
   （``has_active_virtual_machines``）；F004 起**追加**「该宿主下是否存在活跃
   NetworkInterface」检查（``has_active_network_interfaces``），使
   ``DELETE /api/bare-metals/{id}`` 在宿主有活跃 VM 或活跃 NIC 时返回 ``409``
   （R-VM-005 / R-NIC-003 / R-DELETE-004 / AC-29）。F007 起**追加**「该宿主下是否存在
   活跃 Container」检查（``has_active_containers_on_bare_metal``），F008 落地时继续追加。
2. ``has_active_bare_metals``：供 **Cluster** 删除路径消费的「该 Cluster 下是否存在
   活跃 BareMetal」检查，被 ``app/clusters/deletion.py`` 的
   ``CLUSTER_ACTIVE_CHILD_CHECKS`` 引用（R-DELETE-004 / AC-23 / AC-27）。

子资源模块提供检查函数（``app.virtual_machines.deletion.has_active_virtual_machines`` /
``app.network_interfaces.deletion.has_active_network_interfaces`` /
``app.containers.deletion.has_active_containers_on_bare_metal``），父资源模块声明；
``app.bare_metals.deletion → app.containers.deletion → app.models.container`` 无循环导入。
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.containers.deletion import has_active_containers_on_bare_metal
from app.db.active import active_filter
from app.deletion.checks import ActiveChildCheck
from app.models.bare_metal import BareMetal
from app.network_interfaces.deletion import has_active_network_interfaces
from app.services.deletion import has_active_services_on_bare_metal
from app.virtual_machines.deletion import has_active_virtual_machines

#: BareMetal 自身的活跃子资源检查（F006 起含活跃 VirtualMachine；F004 起含活跃
#: NetworkInterface；F007 起含活跃 Container；F008 起**追加**活跃 Service）。四个检查都
#: 必须保留（AC-39 / AC-44，不得丢弃任何既有检查）。
BARE_METAL_ACTIVE_CHILD_CHECKS: tuple[ActiveChildCheck, ...] = (
    has_active_virtual_machines,
    has_active_network_interfaces,
    has_active_containers_on_bare_metal,
    has_active_services_on_bare_metal,
)


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
