"""活跃子资源检查的声明类型（ADR-0004 §5 / F014 问题 2）。

资源模块以模块级常量声明自己在删除前必须执行的活跃子资源检查元组
（如 ``app/clusters/deletion.py`` 的 ``CLUSTER_ACTIVE_CHILD_CHECKS``），并在调用
:func:`app.deletion.service.soft_delete` 时**显式**传入。

统一软删服务不硬编码「某个资源有没有子资源」；新增子资源只需在父资源的声明处
追加一个检查，服务核心逻辑零改动。
"""

from __future__ import annotations

from collections.abc import Callable

from sqlalchemy.orm import Session

#: 活跃子资源检查：``(session, parent_id) -> bool``。
#:
#: 返回 True 表示该父行下存在 ``deleted_at IS NULL`` 的子资源，删除必须被拒。
#: 实现方负责用 ``EXISTS`` 之类的查询表达「活跃子行」语义（通常是
#: ``deleted_at IS NULL``），并复用 ``app/db/active.py`` 的过滤原语。
ActiveChildCheck = Callable[[Session, int], bool]
