# F003 Cluster 管理与持久化横切首落地 — PRODUCT 阶段报告

- **Feature**：F003 Cluster 管理与持久化横切首落地（FEATURE，P0，M2）
- **阶段**：PRODUCT；**结论**：`READY FOR ARCHITECT`（2026-10-06）
- **依据**：requirements-v3.md revision 3（§4、§4.1、§5、§19、§21、§22、§23、§25、§27、§28、§31、§35）；plan_revision 4 F003 条目（用户 2026-10-06 批准）；Product Manager 阶段交接（协调器核验后持久化）。

## 确认条款

§5 Cluster code/name/status 规则、§4.1 名称归一化与作用域、§4 稳定 ID、§21 软删/恢复/引用检查/code 不重用、§22 Audit 内容与同事务、§19 Cluster Detail、§25 API 前缀与组合过滤、§27 完整性、§28 前端列表基线，均 CONFIRMED。§35.2 六项决策已关闭；D01 共享约定基座与 D02 审计一致性为 OPEN 设计输入，在本 Feature CONTRACT 由 Architect/Database 签核，非产品阻塞。

## 必须遵守的已确认约束

- Cluster code：全局唯一、大小写不敏感、创建后不可改、软删后不重用；全量唯一索引由 PostgreSQL 兜底（§5、§27）。
- Cluster name：可改、允许中文、不强制唯一；去首尾空白、禁空/控制字符（§5、§4.1）。
- Cluster status：ACTIVE/INACTIVE，默认 ACTIVE，人工维护，不级联、不释放 IP；INACTIVE 仍按既有权限维护；默认查询含停用并可过滤（§5）。
- 稳定 ID；名称归一化统一供 API/导入/搜索/唯一性使用（§4、§4.1）。
- 软删 deleted_at 默认隐藏；ADMIN 查看/恢复；引用检查与恢复重检冲突；不做隐式级联；code 不重用（§21）。
- Audit：operator/action/object_type/object_id/before_data/after_data/created_at，CREATE/UPDATE/DELETE/RESTORE，与业务同事务，Activity 全角色可见、完整查询限 ADMIN、不记敏感内容、持续保留（§22）。
- Cluster Detail 与列表过滤、组合条件（§19）；列表分页/排序/过滤/模糊搜索（§28）；`/api/v1/clusters` 组合过滤（§25）。
- 权限：读全角色，写 EDITOR/ADMIN，删除/查看已删除/恢复 ADMIN（§23）。
- 本 Feature 仅落地持久化横切于首个对象 Cluster；其它对象软删/审计回归、完整 T24/T40/T41/T25/T26、用户管理 UI 不在此范围。

## 可观察验收标准

| # | 标准 | 映射 |
| --- | --- | --- |
| A1 | code 大小写不敏感唯一、软删后不重用、创建后不可改 | §5、T13、§27 |
| A2 | name 允许中文/可改/不强制唯一；去首尾空白；空名/控制字符拒绝 | §4.1 |
| A3 | status 默认 ACTIVE、可切换、不级联、INACTIVE 仍可按权限维护 | §5、T29 |
| A4 | 默认列表含未删除停用集群；状态过滤；组合过滤/排序/分页/模糊搜索 | §5、§28、§19 |
| A5 | 默认隐藏已软删；ADMIN 可列出并查看；EDITOR/VIEWER 不可见 | §21、T24 首对象 |
| A6 | ADMIN 恢复；code 被重用或依赖仍删除时恢复失败不覆盖；不自动恢复关联 | §21、T24 首对象 |
| A7 | CREATE/UPDATE/DELETE/RESTORE 写 Audit 且与业务同事务；回滚不留痕；Activity 全角色可见、完整 Audit 限 ADMIN；不记敏感内容 | §22、T26 部分 |
| A8 | 过期版本更新 409 且无静默覆盖/重试 | §23、T26 |
| A9 | code/name 变更不改对象身份；内部关联用稳定 ID | §4 |
| A10 | 名称归一化与稳定 ID 固化为共享契约（D01 基座），API 与后续导入共用 | §4.1、T40 部分 |
| A11 | D01 基座与 D02 审计一致性在本 Feature CONTRACT 由 Architect/Database 签核 | 计划 acceptance 末项 |

## 边界（不宣称）

其它对象软删/审计回归、完整 T24/T40/T41、T25/T26 完整回归（跨 Feature）、用户管理 UI（F015）；§19 关联区域与组合过滤线随依赖对象 Feature（F004+）接入，F003 仅交付 Cluster 基础详情与页面/接口基线；不含上线验收批准（§32）。

## 结论与下一步

无 Blocking Questions，无待用户裁定事项。下一步：ARCHITECTURE Gate——Cluster 实体方案、layers、api_required，并在 CONTRACT 签核 D01（Cluster 域字段契约、code 归一化键列与全量唯一约束、稳定 ID、时间契约、nullable/省略语义）与 D02 审计一致性部分（同事务写路径、乐观锁版本列、错误语义）。
