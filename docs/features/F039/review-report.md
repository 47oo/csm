# F039 Dashboard 容量查询批量化与查询计数基准（R10）— REVIEW 报告

- **结论**：**APPROVED WITH FOLLOW-UP**（无 BLOCKER / HIGH / 必须修复 MEDIUM）
- **候选 HEAD**：`f7bd196bcc590ffa2f36b6741a3c72bb888df6e1`；**Base**：`refs/heads/v3.4` = `f66d1f33eb95fd54504e6c600ad32e7bc89ad9bd`（= start_commit = merge-base）
- **版本**：v1（2026-10-29，正式 Review，独立复核，reviewer 只读产出、协调器持久化）
- **范围**：14 文件（2 服务文件 + 2 测试 + 8 `docs/features/F039/**` + 计划派生视图）；工作区 clean；`docs/api`、`docs/product`、`docs/database`、`frontend`、`backend/alembic`、`backend/app/api`、`backend/app/models` **零 diff**

## 1. 层次结论

| 层 | 结论 | 关键证据 |
| --- | --- | --- |
| 产品/领域 | PASS | A1–A8 与 §20/§23.2/T32·T88、F013 §3.3 对齐；无新增对象/关系/状态/唯一性；只读聚合，data-integrity 不触发 |
| 架构 | PASS | 薄包装 + `CapacityContext` 预取；`dashboard.py` 仍调用 `network_capacity`/`auto_pools_capacity`，地址算术仍单点在 `ip_capacity` |
| 数据 / Migration | NOT_REQUIRED 成立 | 无 DDL、无索引变更；models/alembic 零 diff |
| Contract | NOT_REQUIRED 成立 | `docs/api/F013.md` 字节级零 diff；§3.3「复用两函数」字面满足；端点/参数/响应五字段/错误顺序/业务边界/分页排序/§23.2/软删过滤各维未变 |
| 实现正确性 | PASS | `_undeleted_ips_in_range` 为唯一谓词构造器，被 `_count_ips` 与 B1/B2/B3 共用；`context=None` 回退分支语句数不变（F010 6/7/8 = 基线） |
| A1 | PASS（非空跑） | 自跑 15 passed；自写 `/tmp` 探针复算当前树 `q_svc={1:11,10:11,50:11}`、P 轴 P=0..4 恒 11；`git archive` 导出基线树同探针得 `{1:14,10:68,50:308}`、P 轴 14→18；A1 用例在基线树 **FAILED** |
| A2/A4 | PASS | 八项谓词逐条核对；独立等价探针（软删 AUTO 池、软删 IP、gateway 落 RESERVED、未绑定、池外手动）得 context == 单对象 == Dashboard 行（245/5/240，auto 11/1/10）；A2 六网络矩阵含硬编码字面量与端点逐项相等；A4 `/30` 得 1/2/**−1** 不截断 |
| A5 | PASS | 整响应字典字面量相等；分页 `created_at desc, id asc`；`401 → 422 → 200` 信封逐字 |
| A3 | PASS | `test_f039_scope.py` 带 `real_scope`，单独跑 3 passed（VIEWER 仅见 A/B、`counts=2`，legacy shim 会得 3 ⇒ 非空跑）；harness AST 守卫通过 |
| A6/A7 | PASS | 自跑 dashboard+harness+f013+f027 → 36 passed；`frontend/` 零 diff 且 `npm run typecheck` 通过 |
| A8 | PASS | 断言 3 条语句、`enable_seqscan=off` 计划无 `Seq Scan`、引用索引名存在于 `pg_indexes`；`explain_f039.md` 给可复现命令 |
| 安全/范围 | PASS | 无新依赖、无敏感信息、无越界改动；测试不依赖执行顺序 |

## 2. 旧缺陷复核

1. **EXPLAIN 索引名与 TD/架构预设不一致**：认可 Tester 判断——实际规划器选 `excl_ip_pools_network_id_address_range`（network_id 首列，功能等价且更优），判据已改为「索引路径存在 + 索引名真实存在于 `pg_indexes`」；DATABASE `NOT_REQUIRED` / DB-D124 结论不变 ⇒ 不影响结论。
2. **F016 `F016_ACCEPTANCE=1` BLOCKED**：模块本身 `skipif` 且需活动 HTTP 栈，`ConnectError` 属环境限制；报告记 `BLOCKED / NOT TESTED`，未计 PASS，如实。
3. 测试侧 3 处夹具自洽修正（INACTIVE 建 IP 被 409、`create_pool` 无 mode、F010 按 HTTP 级计数）未改产品口径。

## 3. 缺陷与跟进

**无必须修复项。** LOW-1（Architect 文档：architecture §3/§8 与 TD-F039-8a 的索引名表述改为「network_id 前导索引（含排他约束索引）」，已在本次状态提交中勘误）；LOW-2（协调器：`execution` 检查点与 Feature 阶段不一致，已在本次状态提交刷新）；NOTE-1..5（重复 `deleted_at` 谓词、空页 `q_svc` 7 vs 预估 8、多快照读、ruff 非门禁、TE 记录 HEAD 与实现提交的记账）均非阻塞。

**FOLLOW-UP**：F045 整体回归须覆盖 F039 的计数与 EXPLAIN 证据；本报告不放行 F045 与 F016 整体验收。

## 4. 未审查项

`F016_ACCEPTANCE=1` 活动 HTTP 栈整体验收（环境不可用）；响应耗时/性能（N7，不在范围）；前端 UI 交互（`layers.frontend=false`，NOT_REQUIRED）。

## 5. 声明

可进入 Merge Gate（APPROVED WITH FOLLOW-UP）。批准仅对候选 HEAD `f7bd196` 与 Base `f66d1f33` 有效；任何实现/测试变更须重新验证与 Review。Merge 与 DONE 由协调器按 Git Workflow §5 判定。
