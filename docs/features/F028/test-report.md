# F028 一期变更集成验收 — Test Report

## TEST DESIGN（TD-1）

- 结论：TEST DESIGN READY
- 环境：真实 HTTP（等价 Compose 栈，见下）；PostgreSQL 16；当前 backend 代码；构建后 frontend + nginx；同源 `http://localhost:18081`
- 输入：F028 product/architecture；F026/F027 Contract 与 Test Report；requirements §31 T85–T99
- 映射：A1→健康/迁移；A2→T85–T89 真实 HTTP；A3→T91/T93–T95；A4→T90/T92/T96/T99；A5→T97–T98；A6→T36 B1–B7；A7→前端 typecheck/build/smoke + 提示文案；A8→证据归档；A9→协调器验收
- 边界：逐域完整矩阵由 F026/F027 套件承担；F028 只做端到端/跨功能/部署与备份；Compose build 失败按环境限制记录，不写成成功

## Test Execution（TEST-1，2026-10-22）

- HEAD：`4569ee6`（feature/F028-integration-acceptance；后续状态提交除外）
- 环境：`docker compose up -d --build` 退出码 1（镜像构建成功；`bootstrap` 因未提供 INITIAL_ADMIN 凭据退出 2，日志 `compose-up.log`）；随后启动等价真实栈：`postgres:16` + 当前 `backend/` + `frontend/dist` + nginx，入口 `http://localhost:18081`
- 健康：`/healthz=200`、`/api/v1/health/ready=200`、`/ =200`、`alembic current = 0015_user_cluster_authorizations (head)`
- 真实 HTTP 验收：`4 passed`（F028 `test_f028_acceptance.py`）
  - T85/T88：8 类对象列表仅 A/B、C 详情 404、搜索/Dashboard 收敛、零授权空态
  - T86/T89：C 写 404/422、无残留；F014 导入预校验行错误 + 写入整批失败，Audit/资源计数不变
  - T91/T94：API Key 继承、撤销后下一请求收敛
  - T92/T95/T98：授权 Audit 可查、INACTIVE/软删/恢复、非 ADMIN 已删对象 403
- T36 备份/恢复：**B1–B7 all PASS**
  - 源/恢复 audit 行数 90=90；md5 一致；append-only 触发器存在；UPDATE/DELETE 被拒；alembic 版本一致且 upgrade head 幂等；恢复库健康 200
- 前端：`npm run typecheck` PASS；`npm run build` PASS；`npm run smoke:client` 322 passed；F026 System 页过期提示已移除
- 全量后端回归：依赖 F027 TEST-1/RV-1 的 `718 passed, 2 skipped`；F028 未改变后端逻辑
- 已知跳过：F016 acceptance module（未启用 `F016_ACCEPTANCE` 的独立 F016 套件）、迁移 V3b 非 superuser（测试库 owner 为 superuser，既有条件）
- 证据目录：`docs/features/F028/artifacts/`（run.log、compose-up.log、frontend-build.log、pytest.log、t36.log；原始运行目录 `scripts/acceptance/artifacts/f028-20261022T062557Z/` 为 git-ignored 临时证据）

**Status：READY FOR REVIEW**
