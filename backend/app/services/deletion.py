"""Service 模块的活跃子资源检查声明与载体侧检查实现（F008 / F014）。

两件事：

1. ``SERVICE_ACTIVE_CHILD_CHECKS``：Service **自身**删除前必须执行的活跃子资源检查
   元组。Service 无子资源，故**显式**声明为空元组（而非隐式缺省）。
2. ``has_active_services_on_bare_metal`` /
   ``has_active_services_on_virtual_machine`` / ``has_active_services_on_container``：
   供 **BareMetal** / **VirtualMachine** / **Container** 删除路径消费的「该载体是否被
   活跃 Service 直接绑定」检查。

「释放」不需要任何写入（架构 §2）：绑定行不可变、不删除、无 ``deleted_at``；活跃性由
``services.deleted_at IS NULL`` 派生。因此检查以 ``EXISTS`` 语义 JOIN ``service_carriers``
到 ``services`` 并按 ``active_filter(Service)`` 过滤即可——Service 软删后该 EXISTS
立即为假（AC-39 自动成立）。

导入方向无环：``app.bare_metals.deletion → app.containers.deletion →
app.services.deletion → app.models.service_carrier``；本模块**不导入**其它资源模块。
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.active import active_filter
from app.deletion.checks import ActiveChildCheck
from app.models.service import Service
from app.models.service_carrier import ServiceCarrier

#: Service 自身的活跃子资源检查（显式空：Service 无子资源）。
SERVICE_ACTIVE_CHILD_CHECKS: tuple[ActiveChildCheck, ...] = ()


def _has_active_service(session: Session, condition) -> bool:
    stmt = (
        select(ServiceCarrier.id)
        .join(Service, Service.id == ServiceCarrier.service_id)
        .where(active_filter(Service), condition)
        .limit(1)
    )
    return session.scalars(stmt).first() is not None


def has_active_services_on_bare_metal(session: Session, bare_metal_id: int) -> bool:
    """``bare_metal_id`` 是否被**活跃** Service 直接绑定。"""
    return _has_active_service(session, ServiceCarrier.bare_metal_id == bare_metal_id)


def has_active_services_on_virtual_machine(session: Session, virtual_machine_id: int) -> bool:
    """``virtual_machine_id`` 是否被**活跃** Service 直接绑定。"""
    return _has_active_service(session, ServiceCarrier.virtual_machine_id == virtual_machine_id)


def has_active_services_on_container(session: Session, container_id: int) -> bool:
    """``container_id`` 是否被**活跃** Service 直接绑定。"""
    return _has_active_service(session, ServiceCarrier.container_id == container_id)
