# F029 Review 跟进项 — Test Report

## TEST DESIGN（TD-1）

- 结论：TEST DESIGN READY
- 环境：真实 PostgreSQL（`csm_test`）+ 真实 HTTP 等价栈（postgres:16 + 当前 backend + 构建后 frontend + nginx，同源 :18081）
- 输入：F026/F027/F028 Review reports；F029 implementation；requirements revision 11（无新业务规则）
- 覆盖：F026 未知用户/非法 q 顺序、撤销 409 UI、候选跨分页、IntegrityError 收窄、SQLSTATE/downgrade 对称性、管理员升降级/停用；F027 路由依赖覆盖、real_scope marker、父级谓词命名、Contract 交叉引用；F028 等价栈与 T36 回归。
- 边界：不新增业务规则、Schema、端点；F029 只验证跟进项与回归。

## Test Execution（TEST-1，2026-10-22）

- 被测 HEAD：`0e5d8fc`（实现提交；本报告为随后 docs-only 提交）
- 后端定向：`pytest -q tests/integration/test_cluster_authorizations.py tests/integration/test_f027_access_scope.py` → **21 passed**
  - 新增：未知用户 + 非法 q → 404；管理员升级/降级/停用；触发器 SQLSTATE 23514/23001/23505；0015 downgrade 对象对称性；每一条业务路由依赖 `get_access_scope`。
- 全量后端：`pytest -q` → **721 passed, 6 skipped**
  - 跳过：F016 acceptance（未启用）、F028 acceptance module（未启用 `F016_ACCEPTANCE`，单独真实栈执行）、migrations V3b（superuser owner，既有条件）。
- 等价真实栈：`4 passed`（F028 real-HTTP）+ T36 **B1–B7 全 PASS**；健康 200、alembic head `0015_user_cluster_authorizations`；Compose 尝试仍因 `bootstrap` 缺 `INITIAL_ADMIN` 退出 2（记录，不写成成功）。
- 前端：`typecheck` PASS、`build` PASS、`smoke:client` **322 passed**。
- 证据：`docs/features/F029/artifacts/`（run.log、pytest.log、t36.log、compose-up.log、frontend-build.log、frontend-smoke.log）。
- 未验证：真实浏览器 DOM/焦点/窄屏（F028 既有边界）；全量 Compose 成功启动（环境限制已记录）；并发压力（既有并发回归 + F026/F027 约束证据）。

**Status：READY FOR REVIEW**
