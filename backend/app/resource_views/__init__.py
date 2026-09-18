"""F010 资源详情与关联查询（只读聚合读取）。

本模块只交付 ``docs/api/f010-resource-detail.md`` 定义的**唯一**端点
``GET /api/bare-metals/{bare_metal_id}/related``（由 ``app.main`` 以 ``/api`` 前缀
挂载，供 F013 的 ``/api/*`` 认证中间件自动覆盖）。

设计约束（``docs/architecture/f010-resource-detail-handoff.md``）：

- **唯一 404 网关**：先经 ``app.bare_metals.service.get_bare_metal_by_id`` 确认
  BareMetal 存在且活跃，再派生五类；子资源的缺失 / 已删绝不诱发主体 404。
- 五类成员一律经各资源既有 repository 的 canonical 过滤函数得到；本模块不出现
  第二份活跃过滤谓词（ADR-0004）。
- 深度固定 ≤3 跳、直线式组合，无递归 / 关系类型参数 / 通用关系引擎。
- **只读**：不注册任何写 / 删除 / 恢复 / 解绑端点；不注册五个子资源端点。
"""
