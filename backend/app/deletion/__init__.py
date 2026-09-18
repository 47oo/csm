"""统一逻辑删除领域基座（F014）。

``app/deletion/service.py`` 的 :func:`soft_delete` 是系统内**唯一**允许写入
``deleted_at`` 的代码路径（ADR-0004 §1/§3）。各资源模块以模块级常量声明
自己的活跃子资源检查，并显式委托本服务；不得自建第二条删除路径。
"""

from __future__ import annotations

from app.deletion.checks import ActiveChildCheck
from app.deletion.service import soft_delete

__all__ = ["ActiveChildCheck", "soft_delete"]
