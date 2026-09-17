"""Container 模块的活跃子资源检查声明与载体侧检查实现（F007 / F014）。

两件事：

1. ``CONTAINER_ACTIVE_CHILD_CHECKS``：Container **自身**删除前必须执行的活跃子资源
   检查元组。当前 Service 表尚不存在，故**显式**声明为空元组，而不是由统一软删服务
   假定「Container 无子资源」（AC-41 / ADR-0004 §5）。**F008** 落地时在此追加「活跃
   Service」检查。
2. ``has_active_containers_on_bare_metal`` / ``has_active_containers_on_virtual_machine``：
   供 **BareMetal** / **VirtualMachine** 删除路径消费的「该载体下是否存在活跃
   Container」检查，被 ``app/bare_metals/deletion.py`` 与
   ``app/virtual_machines/deletion.py`` 的活跃子声明引用（R-CONTAINER-005 /
   R-DELETE-004 / AC-33 / AC-34 / AC-39 / AC-40）。
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.active import active_filter
from app.deletion.checks import ActiveChildCheck
from app.models.container import Container

#: Container 自身的活跃子资源检查（当前显式空：Service 尚不存在；F008 追加位置）。
CONTAINER_ACTIVE_CHILD_CHECKS: tuple[ActiveChildCheck, ...] = ()


def _has_active_container(session: Session, condition) -> bool:
    stmt = select(Container.id).where(active_filter(Container), condition).limit(1)
    return session.scalars(stmt).first() is not None


def has_active_containers_on_bare_metal(session: Session, bare_metal_id: int) -> bool:
    """``bare_metal_id`` 载体下是否存在 ``deleted_at IS NULL`` 的 Container。"""
    return _has_active_container(session, Container.bare_metal_id == bare_metal_id)


def has_active_containers_on_virtual_machine(session: Session, virtual_machine_id: int) -> bool:
    """``virtual_machine_id`` 载体下是否存在 ``deleted_at IS NULL`` 的 Container。"""
    return _has_active_container(session, Container.virtual_machine_id == virtual_machine_id)
