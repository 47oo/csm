"""IPAddress 模块的活跃子资源检查声明与父资源侧检查实现（F005 / F014）。

两件事：

1. ``IP_ADDRESS_ACTIVE_CHILD_CHECKS``：IPAddress **自身**删除前必须执行的活跃子资源
   检查元组。IPAddress 是 V1 **叶子资源**，故**显式**声明为空元组，而不是由统一软删
   服务假定「无子资源」；显式声明由 ``== ()`` 的 guard 固定，防止「顺手」发明子资源。
2. ``has_active_ip_addresses``：供 **NetworkInterface** 删除路径消费的「该 NIC 下是否
   存在活跃 IPAddress」检查，被 ``app/network_interfaces/deletion.py`` 的
   ``NETWORK_INTERFACE_ACTIVE_CHILD_CHECKS`` 引用（R-IP-001 绑定 / R-DELETE-004 / AC-27）。
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.active import active_filter
from app.deletion.checks import ActiveChildCheck
from app.models.ip_address import IpAddress

#: IPAddress 自身的活跃子资源检查（V1 叶子资源：显式空元组）。
IP_ADDRESS_ACTIVE_CHILD_CHECKS: tuple[ActiveChildCheck, ...] = ()


def has_active_ip_addresses(session: Session, network_interface_id: int) -> bool:
    """``network_interface_id`` 下是否存在 ``deleted_at IS NULL`` 的 IPAddress。

    复用活跃过滤原语；以 ``EXISTS`` 语义（``LIMIT 1``）表达，不取回整行。
    """
    stmt = (
        select(IpAddress.id)
        .where(
            active_filter(IpAddress),
            IpAddress.network_interface_id == network_interface_id,
        )
        .limit(1)
    )
    return session.scalars(stmt).first() is not None
