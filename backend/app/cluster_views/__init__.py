"""F009 Cluster 视角资源查询（只读名称别名）。

本模块只交付 ADR-0003 §2 已确认、F001 / F002 均排除并指向 F009 的只读别名
``GET /api/clusters/by-name/{cluster_name}/bare-metals``。

设计约束（``docs/architecture/f009-cluster-resource-view-handoff.md``）：

- 名称解析复用 ``app.clusters.service.get_cluster_by_name``（字面值、大小写敏感、
  仅活跃；未命中 → ``404``）。
- 成员读取**委托** ``app.bare_metals.service.list_bare_metals``，从而与 canonical
  （``GET /api/bare-metals?cluster_id=``）共用同一父活跃复检与同一
  ``deleted_at IS NULL`` 过滤路径（ADR-0004）；本模块**不得**出现任何
  ``deleted_at`` 表达式。
- 不新增领域对象 / 字段 / 关系 / 状态；不越界到 NIC / IP / VM / Container / Service。
"""
