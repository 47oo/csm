"""Cluster 资源模块的活跃子资源检查声明（F014 问题 2 / 问题 7）。

``clusters`` 当前**没有**子资源表（BareMetal 属 F002），因此这里**显式**声明为
空元组，而不是由统一软删服务假定「Cluster 无子资源」。

F002 落地 ``bare_metals`` 时**必须**在此追加「该 Cluster 下是否存在活跃
BareMetal（``deleted_at IS NULL``）」的检查，并将端到端场景补入 F002 的 AC
（``f014-soft-delete-handoff.md`` 问题 7）。
"""

from __future__ import annotations

from app.deletion.checks import ActiveChildCheck

CLUSTER_ACTIVE_CHILD_CHECKS: tuple[ActiveChildCheck, ...] = ()
