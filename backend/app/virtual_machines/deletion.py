"""VirtualMachine 模块的活跃子资源检查声明与宿主侧检查实现（F006 / F014 / F007）。

两件事：

1. ``VIRTUAL_MACHINE_ACTIVE_CHILD_CHECKS``：VirtualMachine **自身**删除前必须执行的
   活跃子资源检查元组。当前 Container 表尚不存在，故**显式**声明为空元组，而不是由
   统一软删服务假定「VirtualMachine 无子资源」（AC-29 / ADR-0004 §5）。**F007** 落地时
   在此追加「活跃 Container」检查（R-CONTAINER-005）。
2. ``has_active_virtual_machines``：供 **BareMetal** 删除路径消费的「该宿主下是否存在
   活跃 VirtualMachine」检查，被 ``app/bare_metals/deletion.py`` 的
   ``BARE_METAL_ACTIVE_CHILD_CHECKS`` 引用（R-VM-005 / R-DELETE-004 / AC-28）。
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.active import active_filter
from app.deletion.checks import ActiveChildCheck
from app.models.virtual_machine import VirtualMachine

#: VirtualMachine 自身的活跃子资源检查（当前显式空：Container 尚不存在；F007 追加位置）。
VIRTUAL_MACHINE_ACTIVE_CHILD_CHECKS: tuple[ActiveChildCheck, ...] = ()


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
