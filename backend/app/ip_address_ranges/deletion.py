"""IPAddressRange 模块的活跃子资源检查声明与父资源侧检查实现（F020 / F014）。

两件事：

1. ``IP_ADDRESS_RANGE_ACTIVE_CHILD_CHECKS``：范围段**自身**删除前必须执行的活跃子资源
   检查元组——「该 Cluster 内是否存在活跃 IPAddress 字面落在范围内」。命中即
   ``409 ACTIVE_CHILDREN_EXIST`` 且**不写 ``deleted_at``**（无部分写入）。
2. ``has_active_ip_address_ranges``：供 **Cluster** 删除路径消费的「该 Cluster 下是否
   存在活跃范围段」检查，被 ``app/clusters/deletion.py`` 的
   ``CLUSTER_ACTIVE_CHILD_CHECKS`` 引用（R-DELETE-004 / AC-16 / AC-18）。

删除守卫对 ``ip_address`` 的解析语义（Product NQ-C / API §7.2）：
取字面值第一个 ``/`` 之前的地址部分严格解析为 IPv4；解析失败（``abc`` / 空串 /
前导空白 / IPv6 等）→ **跳过该行**，不得因此 500。**不构成**对 ``ip_address`` 的写入
约束（R-IP-004 显式边界）。
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.active import active_filter, select_active
from app.deletion.checks import ActiveChildCheck
from app.ip_address_ranges.ipv4 import extract_ipv4_for_guard
from app.models.ip_address import IpAddress
from app.models.ip_address_range import IpAddressRange


def has_active_ip_addresses_in_range(session: Session, ip_address_range_id: int) -> bool:
    """同 Cluster 是否存在活跃 IPAddress，其字面地址落在范围段 ``[start, end]`` 内。

    目标范围段不存在 / 已软删时返回 ``False``（统一软删服务已在加锁阶段给出 404）。
    """
    target = session.scalars(
        select_active(IpAddressRange).where(IpAddressRange.id == ip_address_range_id)
    ).one_or_none()
    if target is None:
        return False

    literals = session.scalars(
        select(IpAddress.ip_address).where(
            active_filter(IpAddress),
            IpAddress.cluster_id == target.cluster_id,
        )
    )
    for literal in literals:
        parsed = extract_ipv4_for_guard(literal)
        if parsed is not None and target.start_ip <= parsed <= target.end_ip:
            return True
    return False


def has_active_ip_address_ranges(session: Session, cluster_id: int) -> bool:
    """``cluster_id`` 下是否存在 ``deleted_at IS NULL`` 的 IPAddressRange。

    复用活跃过滤原语；以 ``EXISTS`` 语义（``LIMIT 1``）表达，不取回整行。
    """
    stmt = (
        select(IpAddressRange.id)
        .where(
            active_filter(IpAddressRange),
            IpAddressRange.cluster_id == cluster_id,
        )
        .limit(1)
    )
    return session.scalars(stmt).first() is not None


#: IPAddressRange 自身的活跃子资源检查（删除范围段前检查范围内活跃 IP）。
IP_ADDRESS_RANGE_ACTIVE_CHILD_CHECKS: tuple[ActiveChildCheck, ...] = (
    has_active_ip_addresses_in_range,
)
