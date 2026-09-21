"""Cluster 资源模块的活跃子资源检查声明（F014 问题 2 / 问题 7）。

F002 已落地 ``bare_metals``：这里把 ``CLUSTER_ACTIVE_CHILD_CHECKS`` 从空元组演进为
「该 Cluster 下是否存在活跃 BareMetal（``deleted_at IS NULL``）」，使
``DELETE /api/clusters/{id}`` 在父下有活跃 BareMetal 时返回 ``409``
（R-DELETE-004 / AC-23 / AC-27）。

子资源模块提供检查函数（``app.bare_metals.deletion.has_active_bare_metals``），
父资源模块声明；``app.clusters.deletion → app.bare_metals.deletion → app.models.*``，
无循环导入。后续子资源（NIC / VM / …）只需在此追加。

F020：追加「该 Cluster 下是否存在活跃 IPAddressRange」检查
（``app.ip_address_ranges.deletion.has_active_ip_address_ranges``）。
"""

from __future__ import annotations

from app.bare_metals.deletion import has_active_bare_metals
from app.deletion.checks import ActiveChildCheck
from app.ip_address_ranges.deletion import has_active_ip_address_ranges

CLUSTER_ACTIVE_CHILD_CHECKS: tuple[ActiveChildCheck, ...] = (
    has_active_bare_metals,
    has_active_ip_address_ranges,
)
