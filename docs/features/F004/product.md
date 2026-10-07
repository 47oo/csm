# F004 Resource 核心登记 — PRODUCT 阶段报告

- **Feature**：F004 Resource 核心登记（FEATURE，P0，M2，deps [F003]）
- **阶段**：PRODUCT；**结论**：`READY FOR ARCHITECT`（2026-10-07）
- **依据**：requirements-v3.md revision 3（§4、§4.1、§6、§7、§18、§21–§23、§25、§27–§28、§31、§33、§35）；plan_revision 4 F004 条目（用户 2026-10-06 批准）；d01-conventions.md v2；Product Manager 阶段交接（协调器核验后持久化）。

## 确认条款

§4 统一 Resource/稳定 ID、§4.1 必填与名称规范、§6 类型/Role/Status 与不可改、§7 hostname 唯一性与归一化、§18 Overview 五要素、§21 软删/恢复/引用检查、§22 Audit、§23 权限、§25 组合过滤、§27 完整性、§28 列表基线均 CONFIRMED。无 Blocking Questions；D01/D02 为设计输入（Architect/Database 签核），非产品待决。

## 必须遵守的已确认约束

- resource_type ∈ {BARE_METAL, VIRTUAL_MACHINE}（本期不扩展）；role ∈ {COMPUTE, LOGIN, MANAGEMENT, STORAGE, SERVICE, GPU, OTHER} 默认 OTHER、显式 null 拒绝、可扩展、一个主 Role；status ∈ {IDLE, ALLOC, DOWN, UNKNOWN} 默认 UNKNOWN、人工维护、不由名称推导（§6）。
- 同 Cluster hostname 去首尾空白转小写后唯一；跨 Cluster 允许同名；软删后可重用；短名/FQDN 按完整字符串不合并；禁空/内部空白/非法字符；API、导入、搜索、DB 唯一性共用同一归一化（§7、§4.1）。
- 所属 Cluster 创建必填；不可直接改所属 Cluster 或 resource_type（§6）。
- 软删/恢复/引用检查（§21）：默认隐藏；ADMIN 恢复；不级联；恢复重检唯一性与所属对象有效性、失败不覆盖；类型明细跟随 Resource 生命周期（F005/F006 建）。
- Audit CREATE/UPDATE/DELETE/RESTORE 同事务；Activity 全角色可见、完整审计限 ADMIN；不记敏感内容（§22）。
- 列表组合过滤 cluster/type/role/status（§25）；Resource Detail Overview 五要素（§18）；列表分页/排序/过滤/模糊（§28）；hostname 唯一由 PostgreSQL 兜底（§27）；权限矩阵（§23）。

## 可观察验收标准

| # | 标准 | 映射 |
| --- | --- | --- |
| A1 | 同 Cluster 重复 hostname 失败；跨 Cluster 同名允许 | §7、T01、T02 |
| A2 | 软删 hostname 后可重建 | §7、§21、T03 |
| A3 | cn001/CN001/" cn001 " 同 Cluster 相同；归一化规则固化为契约（导入执行在 F014） | §7、T11 |
| A4 | role/status 省略默认 OTHER/UNKNOWN；role 显式 null 拒绝 | §6、T37 |
| A5 | 创建后改 cluster/resource_type 被拒（422） | §6、T19 |
| A6 | 所属 Cluster 缺失/不存在/已软删时创建失败；hostname 空/内部空白被拒 | §4.1、§7 |
| A7 | 列表组合过滤 cluster/type/role/status 符合 §25；分页/排序 | §25、§28 |
| A8 | Detail Overview 显示 Hostname/Cluster/Type/Role/Status/Description | §18 |
| A9 | 默认隐藏软删；ADMIN 查看已删并恢复；恢复重检失败不覆盖 | §21 |
| A10 | 四类 action 写 Audit 同事务；回滚不留痕；Activity 全角色、完整审计限 ADMIN | §22 |
| A11 | VIEWER 只读；EDITOR 增改不删/恢复；ADMIN 删/恢复/查看已删 | §23 |
| A12 | hostname 基础搜索接入全局搜索入口（完整模糊在 F013） | §7、§17 |
| A13 | 归一化与稳定 ID 由 D01 承载；hostname 归一化键列与 (cluster, hostname) 部分唯一首次建表落地 | §4.1、§7、§27、D01 |

## 边界（不宣称）

BareMetal 硬件/VM 专有明细与 Hardware 区域（F005/F006）；完整 T37/T38/T39（硬件/单位归 F005/F006）；T25/T26 完整回归（跨 Feature）；CSV/Excel 导入（F014）；Network/IP/Interface/Service（F007–F012）；上线验收批准（§32）。

## 结论与下一步

无 Blocking Questions，无待用户裁定事项。下一步：ARCHITECTURE Gate——Resource 实体方案、layers、api_required，并在 CONTRACT 签核 D01 Resource 域字段契约（hostname 归一化键列与 (cluster, hostname) 部分唯一、Role/Status 枚举与默认值、422 语义）与 D02 审计一致性/乐观锁部分。
