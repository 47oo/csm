# F031 F030 Review 非阻塞项收尾 — Implementation

- 状态：BACKEND COMPLETE / FRONTEND COMPLETE / 文档修订完成（待 TEST）
- 依据：`docs/features/F031/architecture.md`（READY FOR IMPLEMENTATION）、`docs/features/F031/test-report.md`（TD-1）

## 1. Backend

| 项 | 文件 | 内容 |
| --- | --- | --- |
| RV-05 | `backend/app/services/cluster_authorization.py` | 仅注释：typed params 在 route/handler 前拒绝；undeclared params 由 `_reject_unknown_query` 在 handler 第一步拒绝，先于路径/语义校验；保留三条结论。AST 与 base 相同。 |
| RV-06 | `backend/tests/integration/test_cluster_authorizations.py` | `MAX_ATTEMPTS=5`；保留全部 assert、`assert overlap_observed` 失败语义；输出 `attempts used: n/5`。 |
| T03 | 同上 | 新增 `test_grant_path_internal_error_envelope_end_to_end`：真实 Contract 路径 + 测试级 `get_current_operator` override + 真实 FK 23503 → 500 精确信封；401 对照、零泄漏、无行/无 Audit、真实操作者 201 归因；无 `/_test*` 路由；override try/finally 清理。 |

验证（真实 PostgreSQL 16.15 @ localhost:55432/csm_test）：

- 定向 3 文件：**29 passed**
- 两新例：**2 passed**，`attempt 1: statuses=[409,201] overlap=True`，`attempts used: 1/5`
- 收集：**734 + 1 module skip**
- 全量：**729 passed / 6 skipped**，skip 集合不变

## 2. Frontend

| 项 | 文件 | 内容 |
| --- | --- | --- |
| RV-04 | `frontend/src/components/ClusterAuthorizationPanel.tsx` | 空态改回因中性「没有可授予的集群（已有效授权的集群不会重复出现）」；门控逻辑不变。 |
| RV-09 | 同上 | 旧选中集群注释改为「选择框不呈现该脏值且不可提交」，指向 `canSubmitGrant` 与 F030 architecture §17.1。 |
| RV-09 | `frontend/scripts/smoke-client.mjs` | 两处「架构评审 I-2」注释改为真实规则位置；断言不增删。 |

验证：`tsc --noEmit` exit 0；`npm run build` exit 0；`smoke:client` **328 passed / 0 failed**。

## 3. 文档修订

| 项 | 文件 | 内容 |
| --- | --- | --- |
| RV-03/04/05/09 | `docs/features/F030/architecture.md` | 头部 +1 行指针；文末追加 `## 17. F031 errata`（17.1 签名、17.2 文案、17.3 引用、17.4 注释、17.5 结论）；删除行 0。 |
| RV-07 | `docs/features/F030/artifacts/p3-p6-static.log` | 末尾追加 errata 块（原文逐字节保留），更正路径并附实际 grep 输出。 |
| RV-08 | `docs/api/F026.md` | 头部「上游依据」后新增 1 行历史依据说明；版本保持 v3；删除行 0。 |
| RV-10 | `docs/features/F031/test-report.md` | 记录 `real_scope` 守卫接受边界与 reopen 条件。 |

## 4. 未验证项

- 真实浏览器 DOM/焦点/窄屏：NOT TESTED（沿用 F030 范围）。
- ACTIVE>2000 真机路径、并发压力、Compose 启动：NOT TESTED。
- T03 绕过认证，仅作 500 信封证据，不作为 401/403 语义证据。

## 5. Next

Tester 执行 TEST-1，逐项核对 TD-1 P1–P10 并归档 artifacts。
