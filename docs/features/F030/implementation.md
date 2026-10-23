# F030 Review 跟进收敛 — Implementation

- 状态：BACKEND COMPLETE / FRONTEND COMPLETE（待 TEST）
- 依据：`docs/features/F030/product.md`、`docs/features/F030/architecture.md`（含 §16 最终设计定稿 READY FOR IMPLEMENTATION）、`docs/features/F030/test-report.md`（TD-1）
- Contract：`docs/api/F026.md` v3 + 12 份域 Contract 增补节 v1；端点/字段/错误码/权限/错误顺序不变
- Schema/Migration：无变更（Database NOT_REQUIRED；DB-D401–D420 继续有效）

## 1. Backend

### 1.1 完成项

| 项 | 文件 | 内容 |
| --- | --- | --- |
| ⑥ 注释修正 | `backend/app/services/cluster_authorization.py` | `list_authorizations` 注释改为 Contract §3/§5 P-1「路径对象优先」；删除与事实不符的 existence-oracle 结论；代码逻辑零变化 |
| ⑦ 测试规范声明 | `backend/tests/conftest.py` | `auth_app` docstring 声明：默认 legacy unrestricted、真实 scope 必须 `real_scope`、守卫文件位置；运行逻辑未变 |
| ⑦ marker 说明 | `backend/pyproject.toml` | `real_scope` marker 说明同步为 F030 §9.1 口径 |
| ③ q 边界断言 | `backend/tests/integration/test_cluster_authorizations.py` | 新增 `test_list_q_boundary_validation`：已知用户 `q=""`/空白/Cc/Cf/65 字符 → 422（field=q）；正向对照 → 200 total=1；未知用户 + 非法 q → 404；未知用户 + 未声明参数 → 422 |
| ④ 真并发 | 同上 | 新增 `test_concurrent_grant_two_connections_single_winner`：两个独立 ADMIN 客户端 + `Barrier(2)` + 请求区间相交断言；201+409；ACTIVE=1、总行=1、Audit CREATE=1 |
| ④ 非唯一完整性错误 | 同上 | 新增 `test_grant_non_unique_integrity_error_is_not_mapped_to_409`：真实 FK 违约（幽灵 `granted_by`）→ `IntegrityError`、SQLSTATE 23503、约束名正确、不被映射为 409；无行/无 Audit；真实操作者归因对照成功 |
| ⑦ marked canary | 同上 | `test_marked_module_has_no_legacy_scope_override` |
| ⑦ legacy/AST 守卫 | `backend/tests/integration/test_f030_test_harness.py`（新增） | legacy canary、AST 扫描 `offenders==[]`、扫描数 >=20、已知 marked 集合反空洞；守卫自身唯一豁免 |

### 1.2 验证

- 定向三文件：**28 passed**（基线 21 + 新增 7）
- 收集数：定向 28；全量 **733 collected + 1 module skip**
- 全量后端：**728 passed / 6 skipped**；skip 原因集合与 F029 基线一致（F016 module、F028 ×4、migrations V3b superuser）
- 并发形态：HTTP 级真并发（两个独立 ADMIN `TestClient` + 独立 session/NullPool 连接）；正式执行 1 次尝试即相交，稳定性复跑 4/4 均 `attempt 1: overlap=True`；未退回服务层、未使用顺序调用
- 未验证：端到端 500 信封（可选；证据链 = 服务层用例 + F002 既有 500 信封用例）；前端/计划/文档核对由对应角色执行

## 2. Frontend

### 2.1 完成项

| 项 | 文件 | 内容 |
| --- | --- | --- |
| ⑤ 纯逻辑候选计算 | `frontend/src/components/authorizationCandidates.ts`（新增） | `ActiveGrantLoad` / `GrantCandidates` / `computeGrantCandidates` / `canSubmitGrant` / `clusterListTruncated`；非 success 永不返回候选；truncated 双路传播；旧选中集群不可提交 |
| ⑤ 面板门控 | `frontend/src/components/ClusterAuthorizationPanel.tsx` | 加载中不渲染可选项、提交禁用；加载失败 ErrorState + 重试，不置空集；`truncated` 显式提示；集群列表截断判据改为 `total > items.length`；`already_granted` 保持模态打开、内联错误、重新加载候选；`already_revoked` 路径不变 |
| ⑤ smoke 断言 | `frontend/scripts/smoke-client.mjs` | 新增 6 组断言：loading/error/success 过滤/truncated 传播/canSubmitGrant 非 success 恒 false/旧选中集群不可提交 |

### 2.2 验证

- `npx tsc --noEmit`：exit 0，0 error
- `npm run build`：成功（既有 chunk >500 kB 告警）
- `npm run smoke:client`：**328 passed / 0 failed**（F029 基线 322 + 新增 6）
- 静态 wiring：`activeGrantIds` 旧内联过滤命中 0；旧截断判据命中 0；新模块函数使用点均 ≥1
- 未验证：真实浏览器 DOM/焦点/窄屏、键盘可达性、ACTIVE >2000 真机路径、真实后端 409 时序（TEST 阶段按 TD-2 P5 记录）

## 3. Contract / Scope 核对

- 未新增端点、HTTP 方法、参数、请求/响应字段、错误码、reason、权限项或错误顺序。
- 未修改 `backend/alembic/`；无 Schema/Migration 变更。
- 未新增前端 API 调用；候选分页仍使用已批准 `page_size=100`、`MAX_PAGES=20` 安全上限并显式提示 truncated。
- 变更文件均在 Architecture §11 / TD-2 P9.1 白名单内。

## 4. 未验证项 / Next

- TEST 阶段：Tester 按 TD-1 独立执行定向/全量/前端与文档/计划核对；真实浏览器与超量授权仍 NOT TESTED。
- TD-1 的 I-1/I-3 口径（Issue 引用与 P3.1 计数文案）由 Tester 在 TEST 报告内澄清，不阻塞实现。
