"""NetworkInterface 模块的活跃子资源检查声明与宿主侧检查实现（F004 / F014 / F005）。

两件事：

1. ``NETWORK_INTERFACE_ACTIVE_CHILD_CHECKS``：NetworkInterface **自身**删除前必须执行的
   活跃子资源检查元组。F005 起包含「该 NIC 下是否存在活跃 IPAddress」检查
   （``has_active_ip_addresses``），使 ``DELETE /api/network-interfaces/{id}`` 在存在活跃
   IP 时返回 ``409``（R-IP 绑定 / R-DELETE-004 / AC-27）。后续若新增子资源在此继续追加
   （AC-30 / ADR-0004 §5）。
2. ``has_active_network_interfaces``：供 **BareMetal** 删除路径消费的「该宿主下是否存在
   活跃 NetworkInterface」检查，被 ``app/bare_metals/deletion.py`` 的
   ``BARE_METAL_ACTIVE_CHILD_CHECKS`` 引用（R-NIC-003 / R-DELETE-004 / AC-25）。
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.active import active_filter
from app.deletion.checks import ActiveChildCheck
from app.ip_addresses.deletion import has_active_ip_addresses
from app.models.network_interface import NetworkInterface

#: NetworkInterface 自身的活跃子资源检查（F005 起含活跃 IPAddress）。必须为非空元组。
NETWORK_INTERFACE_ACTIVE_CHILD_CHECKS: tuple[ActiveChildCheck, ...] = (has_active_ip_addresses,)


def has_active_network_interfaces(session: Session, bare_metal_id: int) -> bool:
    """``bare_metal_id`` 下是否存在 ``deleted_at IS NULL`` 的 NetworkInterface。

    复用活跃过滤原语；以 ``EXISTS`` 语义（``LIMIT 1``）表达，不取回整行。
    """
    stmt = (
        select(NetworkInterface.id)
        .where(
            active_filter(NetworkInterface),
            NetworkInterface.bare_metal_id == bare_metal_id,
        )
        .limit(1)
    )
    return session.scalars(stmt).first() is not None
