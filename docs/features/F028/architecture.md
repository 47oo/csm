# F028 一期变更集成验收 — Architecture

- 状态：READY FOR DESIGN；layers：database=false、backend=false、frontend=true（仅移除 F026 过期提示）、api_required=false
- 依据：F028 product；F016 acceptance 架构；F026/F027 交付

## 1. 验收拓扑

优先 `docker compose up -d`（Nginx→Frontend/FastAPI→PostgreSQL）。若 Compose 因凭据/环境不可用，按 F016 先例执行并记录 Compose 尝试，再启动等价真实栈：

- `postgres:16`（`db`）
- 当前 `backend/` 代码 + `alembic upgrade head` + bootstrap ADMIN + uvicorn
- 构建后的 `frontend/dist` 由 nginx 静态服务
- `deploy/nginx/nginx.conf` 入口，同源 `http://localhost:18081`
- 测试通过真实 HTTP（httpx）执行，不使用 TestClient/Mock/SQLite

## 2. 工作项

- 新增 `backend/tests/integration/test_f028_acceptance.py`：T85–T89、T91、T93–T98 的端到端断言。
- 新增 `scripts/acceptance/run_f028_acceptance.sh`：Compose 尝试、等价栈、健康检查、真实 HTTP pytest、T36 备份、清理。
- 复用 `scripts/acceptance/verify_audit_backup.sh`（B1–B7）验证 T36。
- 前端：移除 F026 System 页“F027 前范围尚未生效”的过期提示；其余不改。
- 证据：`scripts/acceptance/artifacts/f028-*` 日志 + Test Report。
- 无 Schema/后端逻辑/API Contract 变更。

## 3. 验证策略

- 真实 HTTP 断言列表/详情/写/搜索/Dashboard/导入/API Key/生命周期/错误顺序/不泄露。
- T36 B1–B7：源库/恢复库 audit 行数、md5、append-only 触发器、UPDATE/DELETE 拒绝、alembic 版本、恢复库健康。
- 前端 `typecheck` / `build` / `smoke:client`。
- 全量后端回归依赖 F027 TEST-1 的 718 passed / 2 skipped，并在本次执行前后记录 HEAD/迁移 head。

**Status：READY FOR DESIGN**
