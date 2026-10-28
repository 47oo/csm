# F029 Review 跟进项 — Implementation

- 状态：IMPLEMENTATION COMPLETE（待 TEST/Review）
- 依据：F026/F027/F028 Review follow-ups；plan revision 15；requirements revision 11（无新业务规则）
- Schema/Migration：无变更

## 1. 完成项

| 来源 | 跟进项 | 处理 |
| --- | --- | --- |
| F026-RV-01 | 未知用户 + 非法 q 的 404/422 顺序；q 控制字符未写入 Contract | `list_authorizations` 先校验路径用户（404），再校验 q/status/sort；F026 Contract v2 明确 q 规则与顺序；新增回归断言 |
| F026-RV-02 | 撤销 409 未关闭并刷新 | `ClusterAuthorizationPanel.confirmRevoke` 对 `already_revoked` 关闭对话框、提示并刷新列表；其它错误仍内联呈现 |
| F026-RV-03 | TD-1 部分用例未固化 | 新增 F026 管理员升降级、停用账号、未知用户+非法 q、0015 downgrade 对象对称性、SQLSTATE 精确断言；F027/F028 已有并发/搜索/Dashboard/导入证据 |
| F026-RV-04 | CHG-010/计划 PROPOSED 锚点 | 批准落地时已同步 CHG-010 状态、requirements §23.2 与计划锚点；本次修正 F026 product A-3 标签 |
| F026-RV-05 | evidence.test 指向旧 RETURN | 已指向 `#repair-verification-1` |
| F026-RV-06 | 候选排除仅当前分页 | 打开授予弹窗时分页加载该用户全部 ACTIVE 授权（每页 100，最多 20 页）并排除；授予后增量加入 |
| F026-RV-07 | grant IntegrityError 统一映射 409 | 仅 `uq_user_cluster_authorizations_user_id_cluster_id` 冲突映射 409；其它完整性错误原样抛出 |
| F026-RV-08 | 触发器 SQLSTATE / downgrade 对称性 | 迁移测试断言 23514/23001/23505；新增 0015 downgrade 后表/函数/触发器/索引全部移除、upgrade 后恢复的测试 |
| F026-RV-09 | Product A-1/A-2/A-3 标签滞后 | F026 product 中 A-3 由 PROPOSED 改为“已按 Contract §9.7 记录” |
| F027-R2 | 探针证据可重现 | F028 已加入真实 HTTP 验收；F029 新增路由依赖覆盖测试；高风险探针关键断言已在 F026/F027/F028 仓库测试中覆盖 |
| F027-R3 | 各域 Contract 未回写 F027 | 向 F002/F003/F004/F007/F008/F009/F010/F011/F012/F013/F014/F023 追加“F027 范围语义（加法引用）”；F013 强调 Dashboard counts/networks；F014/F023 强调导入行错误与整批失败 |
| F027-R5 | `normalize(None)` unrestricted 默认风险 | 保留内部调用语义，补充 docstring 警告；新增 `test_every_business_route_depends_on_real_scope` 静态依赖树断言，所有业务路由必须依赖 `get_access_scope` |
| F027-R6 | `auth_app` 按文件名覆盖 | 改为显式 `real_scope` pytest marker；F026/F027/F028 套件标记；`auth_app` 仅在无 marker 的 legacy 套件覆盖 |
| F027-R7 | `resource_predicate` 命名/注释偏窄 | 重命名为 `interface_parent_predicate`，注释限定 Interface；调用点同步 |
| F028-R2 | Dashboard 断言依赖顺序 | 改为基于本用例 A/B Cluster 的局部计数 |
| F028-R3 | 缺 smoke 日志 | 归档 `docs/features/F028/artifacts/frontend-smoke.log`（322 passed） |
| F028-R4 | architecture 失败原因表述 | 改为 Compose 因凭据/环境不可用，实际记录 bootstrap 缺 INITIAL_ADMIN 退出 2 |
| F028-R5 | Plan git 字段 | F028 已补 base/branch/start/head/merge |
| F028-R6 | 整体验收锚点 | `project.acceptance` 已含 F027 repair/execution 锚点；F029 完成后再次核对 |
| F028-R7 | 状态 IN_REVIEW | 最终状态提交已置 DONE |
| F028-R8 | Compose bootstrap stderr | Test Report 注明 compose-up.log 未含 bootstrap stderr，退出码 2 与缺少 INITIAL_ADMIN 一致 |
| F028-R9 | 残留 `headers_none` | 已移除 |

## 2. 文件

- Backend：`app/services/cluster_authorization.py`、`app/services/scope_filters.py`、`app/services/interface.py`
- Backend tests：`tests/integration/test_cluster_authorizations.py`、`test_f027_access_scope.py`、`conftest.py`、`pyproject.toml`
- Frontend：`src/components/ClusterAuthorizationPanel.tsx`
- Contracts：`docs/api/F026.md` v2、F002/F003/F004/F007/F008/F009/F010/F011/F012/F013/F014/F023 的 F027 引用
- Docs：F026 product A-3 标签、F028 test-report 说明、本文件

## 3. 验证

- F026+F027 定向：21 passed（含新增 lifecycle、SQLSTATE、downgrade symmetry、route coverage）
- 前端：typecheck / build / smoke 322 passed
- F028 等价真实栈：待本次 TEST 重跑并记录
- 全量后端：待本次 TEST 重跑并记录
