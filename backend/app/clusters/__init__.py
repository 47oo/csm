"""Cluster 资源模块（F001）。

分层：``router`` → ``service`` → ``validation`` / ``repository``。

- 领域校验（``/`` 禁令 + 活跃唯一性预检）唯一实现于 ``validation.py``，
  ``POST`` 与 ``PATCH`` 共用（R-CLUSTER-005、R-CLUSTER-002）。
- 读取路径复用 F012 的 ``app/db/active.py`` 活跃过滤原语，不重写第二份
  ``deleted_at IS NULL`` 谓词（ADR-0004 §3）。
- 本模块**不存在**任何写入 ``deleted_at`` 的路径（删除领域语义属 F014）。
"""
