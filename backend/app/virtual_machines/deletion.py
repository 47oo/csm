"""VirtualMachine 模块的活跃子资源检查声明与宿主侧检查实现（F006 / F014 / F007）。

两件事：

1. ``VIRTUAL_MACHINE_ACTIVE_CHILD_CHECKS``：VirtualMachine **自身**删除前必须执行的
   活跃子资源检查元组。F006 曾**显式**声明为空元组（Container 表尚不存在），F007 落地后
   演进为**非空**，包含「活跃 Container」检查（R-CONTAINER-005 / AC-40）。F008 落地时
   可继续追加。
2. ``has_active_virtual_machines``：供 **BareMetal** 删除路径消费的「该宿主下是否存在
   活跃 VirtualMachine」检查，被 ``app/bare_metals/deletion.py`` 的
   ``BARE_METAL_ACTIVE_CHILD_CHECKS`` 引用（R-VM-005 / R-DELETE-004 / AC-28）。
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.containers.deletion import has_active_containers_on_virtual_machine
from app.db.active import active_filter
from app.deletion.checks import ActiveChildCheck
from app.models.virtual_machine import VirtualMachine

#: VirtualMachine 自身的活跃子资源检查（F007 起含活跃 Container）。必须为非空元组。
VIRTUAL_MACHINE_ACTIVE_CHILD_CHECKS: tuple[ActiveChildCheck, ...] = (
    has_active_containers_on_virtual_machine,
)


def has_active_virtual_machines(session: Session, bare_metal_id: int) -> bool:
    """``bare_metal_id`` 下是否存在 ``deleted_at IS NULL`` 的 VirtualMachine。

    复用活跃过滤原语；以 ``EXISTS`` 语义（``LIMIT 1``）表达，不取回整行。
    """
    stmt = (
        select(VirtualMachine.id)
        .where(
            active_filter(VirtualMachine),
            VirtualMachine.bare_metal_id == bare_metal_id,
        )
        .limit(1)
    )
    return session.scalars(stmt).first() is not None
