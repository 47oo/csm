# F018 前端改造后一期整体验收复验 — ARCHITECTURE 阶段报告

- **Task**：F018（FEATURE，P0，M8）— Architect，Feature 设计模式。
- **Status**：`READY FOR DESIGN`。
- **Basis**：requirements-v3.md **revision 4**（§28/§29/§30/§31/§32/§33）；`docs/features/F018/product.md`（READY FOR ARCHITECT，R-1..R-10 / AC-1..AC-10）；`docs/features/F017/architecture.md` §5 V5–V7 / §7.5；`docs/features/F017/review-report.md` §6；`docs/features/F016/test-report.md` §2.2/§2.4/§8；`docs/project/project-plan.yaml` F018（plan_revision 5）；`scripts/acceptance/{run_acceptance.sh,README.md}`。
- **Domain / Data Impact**：无。仅复核既有已确认证据，不新增/变更对象、关系、状态、唯一性、生命周期、Schema。
- **方案摘要**：在真实 Compose 首选路径或 F016 §5.3 等价替代栈上，复核 F017 前端改造后 §31/§32/§33 前端相关证据：重跑 `typecheck`/`build`/`smoke:client`，验证 Nginx 入口与 SPA fallback、AntD 运行时渲染与 layer 优先序、preflight 影响、权限门控、四态、错误呈现、Audit 无写入口、列表参数一致性、§32 C1–C15 / §33 界面呈现，并承接 F017 R-1/D-4 视觉确认。

## 1. 验收执行架构

### 1.1 首选路径（真实 Compose，§30）
`docker compose -p csm_f018 up -d --build`，拓扑 Nginx → Frontend / FastAPI → PostgreSQL，入口 `:80`。记录带时间戳 stdout/stderr 与退出码到 `scripts/acceptance/artifacts/run-<utc>/compose-up.log`；成功则按 §1.3 健康判据验证并记录 `docker compose ps`。

### 1.2 等价替代栈（F016 §5.3，镜像源不可达时）
`docker network create f018-acceptance-net`；`postgres:16`（别名 `db`，库 `csm_f018_acc`）→ `csm-f007-test` 挂 `./backend`（别名 `backend`，`alembic upgrade head` → `bootstrap_admin` → `uvicorn`）→ 本地产物 `npm run build` 由 `nginx:1.27-alpine` 静态服务（别名 `frontend`）→ 入口 `nginx:1.27-alpine -p 18080:80`，挂载**未改动**的 `deploy/nginx/nginx.conf`。同源 `http://localhost:18080`。

### 1.3 拓扑 / 端口 / 数据库 / 健康判据
- 端口：宿主 `F018_HOST_PORT`（默认 18080）→ Nginx:80；内部 backend:8000、db:5432。
- 数据库：独立库 `csm_f018_acc`（无命名卷）。
- 健康：`/healthz`=200、`/api/v1/health/ready`=200、`/`=200 且含入口标记、`/clusters`=200 且返回同一入口（SPA fallback）、`alembic current`=head。

### 1.4 清理纪律
结束 `docker rm -f f018-*`、`docker network rm f018-acceptance-net`、`DROP DATABASE csm_f018_acc`、清理临时产物；断言 `docker ps -a`/`network ls`/`volume ls` 无 `f018-*` 残留；`frontend/dist` 为 git-ignored 构建产物，不视为残留。失败路径先 `docker compose -p csm_f018 down -v`。

### 1.5 环境限制（必须如实记录，不得伪造 Compose PASS）
- `docker build` / Compose 依赖 Docker Hub + `deb.debian.org`，本环境实测不可达（同 F016 TE-1）；**Compose 尝试必须归档退出码与日志后再切替代栈**，不得以替代栈冒充 Compose，必须附 §2.4 式差异声明。
- 仓库内**无浏览器 E2E harness**。宿主缓存存在 Playwright Chromium，本 Feature **批准新增 test-only 浏览器验证工具**（不入生产、不改 `frontend/src`、`api/`、`smoke-client.mjs` 与 `package.json` production 依赖）；若安装/启动仍不可行，DOM 相关判据一律标 `NOT TESTED`，不得以 build/机制证据冒充 PASS（D04-8 / §8）。

## 2. Layers / Contract（建议）

```yaml
layers: { database: false, backend: false, frontend: false }   # 无生产交付；验收与测试基础设施不计为产品 layer
api_required: false
```

- **Contract：`NOT_REQUIRED`**。无新增/变更 Endpoint、字段、类型、nullable、错误语义、分页/排序/过滤/权限/并发；前端仅消费既有 READY Contract。不新建 `docs/api/F018.md`，本文件承担无 API 的最终设计签核载体（定稿阶段）。
- `frontend:false` 依据 plan F018 not_required；若 Test Design 判定验证工具需落在 `frontend/scripts/`，仍属 TEST 基础设施，不改变产品 layer。

## 3. 复验方法映射（R/AC → 可执行步骤与证据；自动 vs 人工）

| R / AC | 执行步骤 | 证据 | 自动/人工 |
| --- | --- | --- | --- |
| R-1 / AC-1 | `npm run typecheck`、`npm run build`（断言 `dist` CSS 非空）、`npm run smoke:client`（`N passed,0 failed`，`N≥264`，与 F017 计数比对） | 命令退出码 + 输出 + `grep -c "await test("` | 自动 |
| R-2 / AC-2 | 经入口 curl `/healthz`、`/api/v1/health/ready`、`/`、`/clusters` | 状态码 + `index.html` 入口标记 | 自动 |
| R-3 / AC-3 | 真实（headless）浏览器加载经入口页面，校验 layer 顺序 `base→antd→utilities`、AntD 组件样式生效、utility 覆盖 AntD、preflight 未破版 | 截图 / computed style / DOM 证据 | 人工（浏览器） |
| R-4 / AC-4 | 浏览器以无/有权限会话访问，核 Audit(`AUDIT_READ`) / System(`USER_ADMIN`|`VIEW_DELETED`) 入口显隐与可达性 | 截图 / DOM 断言 + 真实 HTTP 数据 | 人工（浏览器） |
| R-5 / AC-5 | 抽查各列表/详情 Loading/Success/Empty/Error 四态与实际请求一致 | 截图 / DOM 状态 | 人工（浏览器） |
| R-6 / AC-6 | 触发 401/403/409/422，核前端呈现语义与迁移前一致 | 真实 HTTP 响应 + 界面呈现 | 半自动（HTTP 自动；DOM 人工） |
| R-7 / AC-7 | 核 Audit 页面/查询面板无修改/删除/清空控件与入口 | 静态检索 + 浏览器抽查 | 半自动 |
| R-8 / AC-8 | 分页/排序/过滤/模糊搜索可用，网络请求参数与迁移前逐一致（`type` 过滤名、`resource_type` 排序字段不可互换） | 浏览器网络日志 / 真实 HTTP 请求实参 | 半自动 |
| R-9 / AC-9 | §32 C1–C15、§33 Q1–Q9 的**数据层** REUSE F016 TE 真 HTTP 证据；**界面呈现**按浏览器复核；C15 为实际汇总 | 引用 `F016/test-report.md#32-c1c15-上线验收`、`#33-目标查询场景` + 界面证据 | REUSE（数据层）+ 人工（呈现） |
| R-10 / AC-10 | ClustersPage 列对齐确认；抽查其余页面无同类列错位 | 截图 / 列结构比对（对 F017 R-1 base 差异） | 人工（浏览器） |

**NOT TESTED 标注规则**：任一未真实渲染执行者标 `NOT TESTED`，不得写 PASS；机制证据（build/smoke/HTTP）不得替代运行时渲染与 DOM 结论；Compose 未成功须记录并声明替代栈，不得写 Compose PASS；缺证据项不得拼成整体 PASS（I-2/I-8）。

## 4. 测试脚本 / 夹具（允许改测试代码，不改生产实现）

- **复用** `scripts/acceptance/`（`run_acceptance.sh` 栈启动/健康/清理纪律、`README.md`）。不修改 `compose.yaml`、`deploy/**`、`frontend/nginx.conf`、`frontend/index.html`、`tsconfig.json`。
- **建议新增（Tester 在 Test Design 定稿）**：
  1. `scripts/acceptance/run_f018_acceptance.sh`：Preflight → Compose 尝试与失败录制 → 等价替代栈（库 `csm_f018_acc`）→ 健康/入口/SPA fallback → 前端 `typecheck`/`build`/`smoke:client` → 可选浏览器步骤 → 清理；产物 `artifacts/run-<utc>/`。
  2. `scripts/acceptance/browser/f018_browser_check.mjs`：test-only headless 浏览器校验（R-3 优先，R-4..R-8/R-10 尽量覆盖），输出截图/样式证据；缺依赖时整体 skip 并标 `NOT TESTED`。
- **禁止**：改动 `frontend/src/**`、`frontend/src/api/*.ts`、纯逻辑 `*.ts`、`frontend/scripts/smoke-client.mjs` 断言、任何生产依赖与后端；F018 不新增业务规则与契约。

## 5. 验证 / 回滚 / 风险

- **验证**：§3 映射；`project.acceptance.evidence` 由协调器核验后写 `COMPLETE`（Tester 不写）。
- **回滚**：无 Schema/数据/API/部署语义变化；仅撤销 test-only 脚本与产物，无数据恢复。
- **风险**：①Compose 不可达 → 已录制 + 替代栈 + 差异声明；②浏览器工具不可用 → DOM 判据 `NOT TESTED`，不得伪造；③test-only 工具误改生产 → 边界与 Review 守门；④构建通过≠UI 正确（D04-8）→ R-3 必须真实渲染；⑤验收虚报 → NOT TESTED 规则 + 协调器核验。

## 6. 待核对事项与结论

- **Database（预期 `NOT_REQUIRED`）**：确认 F018 无 Schema/迁移/约束/索引变更，与 plan_revision 5 `layers.database=false` 一致，记录 `database: NOT_REQUIRED`。
- **Tester（TEST_DESIGN）**：①细化 §3 为可执行步骤/断言并区分自动与人工；②裁决浏览器工具引入范围，未执行项标 `NOT TESTED`；③复用 `scripts/acceptance/` 并明确清理纪律；④不填写执行 PASS、不写 `project.acceptance`；⑤`smoke:client` 断言不得删减。
- **Architect 定稿**：取得 Database（NOT_REQUIRED）与 Test Design 后核对约束/错误/事务/验收一致性，签核最终设计并给 `READY FOR IMPLEMENTATION`。

无 Blocking Questions，无新增业务规则，无 API/Schema/部署语义变更。**Status：`READY FOR DESIGN`。**

## 7. CONTRACT 最终设计签核

- **签核者**：Architect；**日期**：2026-10-15；**Status**：`READY FOR IMPLEMENTATION`。
- **Contract 状态**：`NOT_REQUIRED`（api_required=false；不新建 docs/api/F018.md，本文件即无 API 最终签核载体）。
- **上游依据**：requirements-v3.md revision 4（§28–§33）CONFIRMED；plan_revision 5（F018，layers 全 false、api_required=false、contract:NOT_REQUIRED）；product.md（READY FOR ARCHITECT）；本文件 §2–§6；F017 architecture.md §5 V5–V7 与 review-report §6；F016 test-report（等价替代栈锚点）。
- **核对输入**：docs/database/f018-acceptance.md v1（`NOT_REQUIRED`，DB-F018-1..3，单 head `0013_search_indexes`）；docs/features/F018/test-report.md#test-design（TD-1 `TEST DESIGN READY`）。
- **覆盖范围**：R-1..R-10 / AC-1..AC-10 复验设计（Compose 首选 + F016 §5.3 等价替代栈、健康/SPA fallback、前端 typecheck/build/smoke:client、浏览器 test-only 工具与 NOT TESTED 规则、脚本落点与清理纪律）。一致确认：无 Schema/迁移/约束/索引变更；无 API/字段/错误语义变更；无业务规则与 layer 变更（浏览器工具落 `scripts/acceptance/browser/`，属 TEST 基础设施）。
- **结论**：约束、错误、事务与验收一致，无 Blocking；签核最终设计，`READY FOR IMPLEMENTATION`。实现由 TEST 阶段（test-only 脚本）承担，Tester 不写 `project.acceptance`。