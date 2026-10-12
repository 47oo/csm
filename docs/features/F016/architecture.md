# F016 一期集成验收与交付 — ARCHITECTURE 阶段报告

- **Task**：F016（FEATURE，P0，M7 一期整体验收，deps F001–F015 均 DONE）— Architect
- **阶段**：ARCHITECTURE；**结论**：`READY FOR DESIGN`（2026-10-06）
- **Basis**：requirements-v3.md revision 3（§22、§30、§31 T01–T41、§32 C1–C15、§33 Q1–Q9、§35）；`docs/features/F016/product.md`（A1–A14、I-1–I-9、O-1–O-4）；`docs/project/{project-state,git-workflow,handoff,implementation-rules}.md`；`compose.yaml`、`deploy/nginx/nginx.conf`、`deploy/backup/`、`backend/Dockerfile`、`frontend/{Dockerfile,nginx.conf}`；既有 `backend/tests/integration/` 证据组织。DR 接续 F015 DR-227，自 **DR-228** 起。
- **边界**：不新增业务对象/字段/状态/规则；不改 F001–F015 行为语义；不写生产代码；不执行 Git 状态变更。

## 1. 方案摘要
F016 是**验收型 Feature**：在真实部署拓扑（Nginx→Frontend/FastAPI→PostgreSQL，§30）执行 §31–§33 跨功能验收、§32 上线验收、T36 备份覆盖 Audit，产出 `project.acceptance.evidence`。**不新增业务 API/Schema/前端功能**，交付物为验收执行方案 + 夹具/脚本 + Test Report 证据。因环境无法 `docker build`（Docker Hub/deb.debian.org 不可达），设计**与 Compose 等价的真实替代栈**（既有可运行镜像 + 真实 PostgreSQL + 真实 Nginx 入口 + 本地构建前端），明示差异，不以 Mock/SQLite 伪造证据。

## 2. Design Requirements（DR-228–DR-246）
| ID | 决策 | 状态 |
| --- | --- | --- |
| DR-228 | layers `database/backend/frontend=false`，`api_required=false`，Contract NOT_REQUIRED（无新业务 API） | CONFIRMED+DESIGN |
| DR-229 | 执行阶梯：先试 `docker compose up -d`；不可用则**如实录制失败**并切替代栈；不伪装 Compose PASS | CONFIRMED+DESIGN |
| DR-230 | 替代栈拓扑：独立网络 + 别名 `db`/`backend`/`frontend`，使 `deploy/nginx/nginx.conf` 免改即可解析 | CONFIRMED+DESIGN |
| DR-231 | 后端替代：镜像 `csm-f007-test` 挂载 `./backend`，容器内 pip 装 F014 依赖 → `alembic upgrade head` → `bootstrap_admin` → `uvicorn` | CONFIRMED+DESIGN |
| DR-232 | 数据库替代：`postgres:16` 独立容器 + 独立库 `csm_f016_acc` | CONFIRMED+DESIGN |
| DR-233 | 前端替代：本地 `npm run build` → `dist/` 由 `nginx:1.27-alpine` 静态服务（别名 frontend） | CONFIRMED+DESIGN |
| DR-234 | 同源/CSRF 一致：经入口端口（18080）访问 `/` 与 `/api/`，Host/Origin 含端口一致 | CONFIRMED+DESIGN |
| DR-235 | 健康判据：`/healthz` 200、`/api/v1/health/ready` 经 Nginx 200、`/` 返回 index.html | CONFIRMED+DESIGN |
| DR-236 | 验收数据集经真实 HTTP API 构造（≥2 Cluster、cn001 BM 管理网+IB、vm001 Host=pve01、pve01 多 VM、gateway/RESERVED/禁用 Network、AUTO/MANUAL 池、绑定/未绑定 IP、Service/Endpoint、导入样例）；不新增业务规则，用后清理 | CONFIRMED+DESIGN |
| DR-237 | T01–T41 证据模型：REUSE（引用权威 Feature 真 PG/真 HTTP 证据 + 集成栈可达确认）/ RERUN（集成栈真 HTTP 端到端） | CONFIRMED+DESIGN |
| DR-238 | §32 C1–C15 证据落点（Test Report 专节） | CONFIRMED+DESIGN |
| DR-239 | §33 Q1–Q9 经既有端点组合真实 HTTP，不新增场景接口 | CONFIRMED+DESIGN |
| DR-240 | T36 备份覆盖 Audit：容器内 `pg_dump`/`restore.sh` + B1–B7 断言 | CONFIRMED+DESIGN |
| DR-241 | 脚本/夹具落点：`scripts/acceptance/` + `backend/tests/integration/{test_f016_acceptance.py,f016_helpers.py}`；不新增业务代码 | CONFIRMED+DESIGN |
| DR-242 | `project.acceptance.evidence` 协调器核验后写入/置 COMPLETE | CONFIRMED+DESIGN |
| DR-243 | 真实证据约束：约束/并发/Migration 仅真 PG；未执行标 NOT TESTED/BLOCKED | CONFIRMED+DESIGN |
| DR-244 | 缺陷路由：退回责任 Feature，不静默修 F001–F015 语义 | CONFIRMED+DESIGN |
| DR-245 | 环境清理：独立网络/端口/库/卷，结束清理无残留 | CONFIRMED+DESIGN |
| DR-246 | 验证策略：A1–A14/I-1–I-9 与 §31/§32/§33 映射，Test Design 细化 | CONFIRMED+DESIGN |

## 3. 裁定 O-1–O-4
| OPEN | 裁定 |
| --- | --- |
| O-1 | layers 全 false、api_required=false、Contract NOT_REQUIRED；验收脚本/夹具属测试基础设施 |
| O-2 | `scripts/acceptance/` + `backend/tests/integration/{test_f016_acceptance.py,f016_helpers.py}` |
| O-3 | §33 用既有 Resource/Cluster Detail/Dashboard/Search/Activity 组合真实 HTTP，不新增场景接口 |
| O-4 | 容器内 psql/pg_restore 断言 audit_logs 行数/字段一致 + append-only 触发器存在 + UPDATE/DELETE 拒绝 |

## 4. layers / api_required / Contract
```yaml
layers:
  database: false
  backend: false
  frontend: false
api_required: false
```
Contract **NOT_REQUIRED**（无新增 Endpoint/Schema/错误语义；被验收 API 来自 F001–F015 READY Contract）；不新建 `docs/api/F016.md`；`not_required.contract` 记理由。无 Migration；无 Backend/Frontend 实现分支。

## 5. 验收执行方案
### 5.1 首选真实 Compose（A1）
`docker compose up -d`（db→migrate→bootstrap→backend→frontend→nginx，入口 :80；`.env` 凭据不入库；独立项目名/库）。
### 5.2 健康判据
`/healthz` 200；`/api/v1/health/ready` 经 Nginx 200；`/` index.html；`alembic current`=head；bootstrap 后登录 200。
### 5.3 环境受限时真实替代栈
```bash
docker network create f016-acceptance-net
docker run -d --name f016-db --network f016-acceptance-net --network-alias db \
  -e POSTGRES_USER=csm -e POSTGRES_PASSWORD="$F016_PW" -e POSTGRES_DB=csm_f016_acc postgres:16
docker run -d --name f016-backend --network f016-acceptance-net --network-alias backend \
  -v "$PWD/backend:/app" -w /app -e DATABASE_URL="postgresql+psycopg://csm:$F016_PW@db:5432/csm_f016_acc" \
  -e INITIAL_ADMIN_USERNAME=admin -e INITIAL_ADMIN_PASSWORD="$F016_ADMIN_PW" \
  csm-f007-test bash -lc "pip install -q 'python-multipart>=0.0.9,<0.1' 'openpyxl>=3.1,<3.2' && alembic upgrade head && python -m app.cli.bootstrap_admin && exec uvicorn app.main:app --host 0.0.0.0 --port 8000"
( cd frontend && npm run build )
docker run -d --name f016-frontend --network f016-acceptance-net --network-alias frontend \
  -v "$PWD/frontend/dist:/usr/share/nginx/html:ro" -v "$PWD/frontend/nginx.conf:/etc/nginx/conf.d/default.conf:ro" nginx:1.27-alpine
docker run -d --name f016-nginx --network f016-acceptance-net -p 18080:80 \
  -v "$PWD/deploy/nginx/nginx.conf:/etc/nginx/nginx.conf:ro" nginx:1.27-alpine
```
**与 Compose 差异**：镜像构建（复用镜像/挂载 vs build）、代码来源（bind-mount）、配置注入（-e vs .env）、编排（手动时序 vs depends_on）、前端（本地产物 vs 镜像内）、卷（独立库 vs 命名卷）、入口路由与同源（同一 nginx.conf，语义一致）。须在 Test Report 明示，不谎报 Compose。
### 5.4 同源 CSRF
对 `http://localhost:18080` 同源访问；写请求带 `Origin: http://localhost:18080`；Host 含端口原样透传；验证 401 先于 403。

## 6. T01–T41 复用/重跑边界（DR-237）
**REUSE**（引用权威 Feature 真 PG/真 HTTP 证据 + 集成栈可达确认）：T01–T10（除 T07 并发引用）、T12–T15、T17/T18、T20/T21、T30/T31、T33/T34、T35（引用真并发）、T38/T39。
**RERUN**（集成栈真 HTTP 端到端）：T11、T16、T19、T22、T23、T24、T25、T26、T27、T28（子集）、T29、T32、T37、T40、T41。T36=复用 Audit 保留/无入口 + F016 新增备份验证。
Test Report 设 `T01–T41 Evidence Index` 逐条给 T→权威 Feature→处置→证据路径/锚点或 F016 用例 ID+环境+结果。

## 7. §32 / §33 证据落点
### 7.1 §32 C1–C15
Test Report `## §32 C1–C15 上线验收`：C1 AC-1(F003–F006)、C2 AC-2(F007–F011)、C3 AC-3(F010)、C4 AC-4(F013)、C5 AC-5(F004–F012)、C6 AC-6(F004/F006/F010)、C7 AC-7(F015)、C8 AC-8(F015)、C9 AC-9(F002/F015)、C10 AC-10(F002)、C11 AC-11(F002/F015)、C12 AC-12(F014)、C13 AC-13(F008/F009/F012/F015)、C14 AC-14(§8 T36)、C15 AC-15(汇总)。
### 7.2 §33 Q1–Q9
Test Report `## §33 目标查询场景`：Q1 搜索 hostname→Resource 含 cluster；Q2 搜索 IP→IPAddress→Interface→Resource；Q3 Resource Detail Interfaces/IP；Q4 VM Detail Host=pve01；Q5 Host VM 列表；Q6 Dashboard/capacity 一致；Q7 IP 绑定状态；Q8 Resource Services；Q9 Activity/完整 Audit。依赖浏览器 DOM 者若无 harness 以真实 HTTP + build 成功为证据并标 NOT TESTED。

## 8. T36 备份覆盖 Audit（DR-240/O-4）
容器内运行既有脚本；恢复后断言 B1 audit_logs 行数一致>0；B2 关键字段 md5 聚合源=恢复；B3 append-only 触发器存在；B4 UPDATE/DELETE 被拒；B5 alembic_version 一致/upgrade 幂等；B6 恢复库 ready 200；B7 备份产物非空。仅 B1–B7 全部有实际输出方可断言覆盖，否则标 BLOCKED/NOT TESTED。

## 9. 脚本/夹具落点（DR-241）
`scripts/acceptance/{run_acceptance.sh,verify_audit_backup.sh,README.md}`；`backend/tests/integration/{test_f016_acceptance.py,f016_helpers.py}`。约束：不改 `backend/app/**`、`frontend/src/**`、`compose.yaml`、`deploy/**`、`alembic/**`；不新增业务规则。

## 10. project.acceptance.evidence 写入与核验（DR-242/A11/I-8）
Test Report 锚点：`#test-design`、`#test-execution`、`#t01t41-evidence-index`、`#32-c1c15-上线验收`、`#33-目标查询场景`、`#t36-备份覆盖-audit`、`#未执行--blocked`。协调器核验后置 `project.acceptance.status=COMPLETE` 并写 evidence 路径列表。COMPLETE≠发布授权。

## 11. 数据完整性对应表（F016 范围）
| 规则依据及版本 | 作用域 | 数据库保证 | 业务层保证 | 验证 |
| --- | --- | --- | --- | --- |
| §22 / f003 DB-D28 | audit_logs append-only | trg_audit_logs_append_only | 无修改/删除/清空入口 | B3/B4；F015 |
| §22 / §30 | Audit 纳入备份 | pg_dump -Fc 全库含 audit_logs | 恢复默认新库 | B1/B2/B5/B7 |
| §22 | 恢复后审计完整 | 行数/字段聚合一致 | 无截断 | B1/B2/B6 |
| §27 / T07/T35 | 约束/并发证据 | 真实 PostgreSQL 事务/约束 | 不重实现 | REUSE F010/F009 |
| §21/§23 | 权限与恢复 | 沿用 F002/F015 | 401 先于 403 | T24/T25 |

## 12. 验证策略与 A/I 映射
A1/I-4/A13→§5+环境节；A2/I-6→DR-235 数据集；A3/A4→§6 Evidence Index；A5→§7.2；A6→§7.1；A7/I-7→§8 B1–B7；A8→T25/T24；A9→T27/T28；A10/I-3→T07/T35 真并发引用；A11/I-8→§10；A12/I-5→§9；I-1/I-2→未执行标 NOT TESTED/BLOCKED；I-9→COMPLETE≠发布授权。

## 13. Blocking / OPEN / 风险
- BLOCKING：无。
- 环境性（非设计阻塞，须记录）：docker build/Compose 不可用 → 首选路径预期 build 失败；替代栈为实际执行方案，差异已明示，归档 Compose 失败输出与替代栈证据，不伪装 Compose PASS。
- 替代栈残余风险：未经镜像构建、前端本地产物、无 depends_on；缓解：锁候选 HEAD 挂载、固定镜像 digest、脚本强制时序。
- OPEN（非阻塞，Test Design 细化）：浏览器 DOM E2E harness；验收数据集条目。
- 依赖：F001–F015 均 DONE；project.acceptance 当前 PENDING。

## 14. 结论与下一步
DR-228–DR-246 覆盖 layers/api_required 裁定、Compose 首选与真实替代栈、健康判据、T 复用/重跑边界、§32/§33 证据落点、T36 备份 B1–B7、脚本落点、acceptance evidence 写入与核验、真实证据与缺陷路由。无 Blocking Questions。**Status：`READY FOR DESIGN`。**

下一步：TEST_DESIGN 细化判据（不预填 PASS）；Database 裁定 NOT_REQUIRED；CONTRACT 核对后 `READY FOR IMPLEMENTATION`；TEST 执行 §5–§8 产出 test-report，协调器核验后写 project.acceptance.evidence 并置 COMPLETE。
