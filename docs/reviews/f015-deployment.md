# Review Report — F015 内网部署与运行环境

> Status: **APPROVED WITH FOLLOW-UP**
> Author Role: reviewer
> Date: 2026-09-17
> Feature: F015（ENABLER，E07，P0，`depends_on: [F012, F013]`）
> Feature Branch: `feature/F015-deployment`
> Base Branch: `develop` = `5c9ca84f94134c9bcc87c61a47fd9280ff99d411`
> start_commit: `5c9ca84f94134c9bcc87c61a47fd9280ff99d411`
> Reviewed HEAD: `f536b064826c4187f4ef422d47e517bdf10cb0bf`
> merge-base(develop, HEAD): `5c9ca84f94134c9bcc87c61a47fd9280ff99d411`（= start_commit，HEAD 为其后代）
> Tester Test Report: `docs/test-reports/f015-deployment.md`（`READY FOR REVIEW`）

---

## Feature

内网部署与运行环境（F015）— CSM V1 的可运行生产部署产物：`docker-compose`（nginx + 应用 + PostgreSQL）编排、生产前端构建接线与 nginx 入口、`prod` 环境硬化（关闭 `/docs` / `/redoc` / `/openapi.json`）、传输层存活 / 就绪探测、凭据外部注入与命名卷持久化、唯一权威部署文档与运行约束。

## Review Status

`APPROVED WITH FOLLOW-UP`

不存在 BLOCKER / HIGH / 必须在当前 Feature 修复的 MEDIUM。AC-01 ~ AC-12 均有结果且核心验收满足；测试可信且 Reviewer 已独立复现（L1 全量重跑、guard 对抗注入可失败性、L2 三容器端到端）；`database: false`、`frontend: false`、`Contract = NOT_REQUIRED` 均成立；实现未超范围、未引入未经确认的能力、未改动领域规则 / 契约 / ADR。存在 2 项 LOW（均为文档 / 计划元数据，不阻塞 Merge）与 5 项 NOTE。

## Scope Reviewed

- **完整分支差异**：`git diff develop...HEAD`（19 文件，+2317 / −20；文件清单见下），并核对 `git log develop..HEAD` 六个提交自 `start_commit` 顺序演进；工作区 `git status --short` 全程为空，无未跟踪交付物、无暂存改动。
- 审查的提交：`4dee947`（启动 + 基线）、`0c64ee5`（产品需求）、`92c7353`（架构 + 契约）、`056c054`（生产产物 + 测试）、`c82947f`（实现检查点）、`f536b06`（验收 / 部署覆盖 + 测试报告）。
- 变更范围（19 文件）：`.dockerignore`、`README.md`、`backend/Dockerfile`、`backend/app/main.py`、`deploy/env.prod.example`、`deploy/nginx/default.conf`、`docker-compose.dev.yml`、`docker-compose.prod.yml`、`docs/architecture/f015-deployment-handoff.md`、`docs/deployment/csm-v1-internal-deployment.md`、`docs/product/handoffs/f015-deployment.md`、`docs/project/{backlog.md,project-plan.yaml,repository-structure.md}`、`docs/test-reports/f015-deployment.md`、`frontend/Dockerfile`、`tests/database/test_f015_locale.py`、`tests/test_f015_deployment_guards.py`、`tests/test_f015_prod_surface.py`。
- **Reviewer 独立执行（非复用 Tester 结论）**：
  1. **L1 全量后端测试**：以全新 `pgserver` PostgreSQL 16.2 实例、独立库 `csm_rev` 运行 `.venv/bin/python -m pytest -q` → **192 passed，无 skipped**（与 Tester 报告一致）。
  2. **guard 可失败性（对抗注入，内存注入、不改工作区文件）**：以 pytest 插件按字节注入三类违规 → `cred_default` 使 `test_g02_*` FAILED、`http_probe` 使 `test_g07_probes_do_not_use_http_or_api` FAILED、`down_v` 使 `test_g04_no_destructive_commands` FAILED；注入后 `git status --short` 仍为空。证明 guard 约束产物而非描述产物。
  3. **`docker compose config`**：无 env → exit 1（`CSM_POSTGRES_USER is missing a value`）；空模板 env → exit 1；完整 env → exit 0，渲染仅 nginx `published: "18099"`（→80），`CSM_ENVIRONMENT: prod`、`CSM_DB_POOL_SIZE: "5"`、命名卷 `csm-prod_csm-prod-pgdata`。
  4. **L2 三容器端到端（从零构建镜像后实际运行）**：`up -d --build` 后三服务 `healthy`；`alembic upgrade head` ×2（第二次 no-op，`current = 0002_f013_auth (head)`）；`create-initial-admin` 幂等；经 nginx `18077`：`GET /` → 200 `text/html`，未认证 `/api/health` → 401 `UNAUTHENTICATED`，`/docs` `/redoc` `/openapi.json` → 404，登录 200 → 已认证 `/api/health` 200 `{"status":"ok","database":"ok"}` → `POST /api/clusters` 201 → `GET` 列表可见；`docker port` 中 postgres / app 为空、仅 nginx 发布；部署库直连 `C.UTF-8|C.UTF-8|UTF8`、`('cluster-a'='Cluster-A')=f`、PG `16.15`、`max_connections=100`；`stop`/`start`、`up --force-recreate`、`down`（不带 `-v`）+`up` 后 Cluster 仍可查、命名卷仍在；app 镜像 `User=csm`、`Cmd` 无 `--reload`、`Config.Env` 无任何凭据；不经 nginx 直接请求 app 容器 `:8000` 亦 `/docs` `/redoc` `/openapi.json` → 404。**复核后已 `down`（不带 `-v`）并删除镜像 / 卷，无残留容器 / 镜像 / 卷，工作区 clean。**
- 依据文档：`AGENTS.md`；`docs/product/handoffs/f015-deployment.md`；`docs/product/requirements.md` §20 / §22 / §23 / §25 / §26；`docs/architecture/f015-deployment-handoff.md`；ADR-0001 ~ 0005；`docs/api/api-conventions.md`；`docs/architecture/f012-project-foundation-handoff.md`；`docs/reviews/f012-project-foundation.md`；`docs/reviews/f013-auth.md`；`.pi/skills/resource-domain/SKILL.md`；`docs/deployment/csm-v1-internal-deployment.md`；`docs/test-reports/f015-deployment.md`。

## Product Compliance

AC-01 ~ AC-12 全部有结果，无 FAIL / BLOCKED，与产品 Handoff 的 Scope（本次包含 1~8、明确不包含 1~7）一致。

| AC | 判定 | Reviewer 结论 |
|---|---|---|
| AC-01 独立内网 VM 三组件 | PASS（L2 等价）/ 真实 VM NOT TESTED | 三容器同机运行且 healthy；未声称真实 VM 通过 |
| AC-02 内网另一台机器访问 | NOT TESTED（L3-only） | 机制等价：入口以 HTTP 监听、`GET /` 返回 SPA、无域名 / 公网；未冒充通过 |
| AC-03 Internal IP + HTTP | PASS | 无 TLS / 证书 / 域名 / 443；唯一发布端口 nginx（→80） |
| AC-04 端到端可用 | PASS | 登录页 / 登录 / Cluster 查询与登记 / 已认证 health 均独立复现 |
| AC-05 prod 与 dev-only 面不可达 | PASS | 编排硬编码 `prod`；nginx + app 双层 404；`/healthz` 亦 404；dev 下 `/openapi.json` 仍 200 |
| AC-06 认证边界与探针 | PASS | `EXEMPT == {("POST","/api/auth/login")}`；探针为 `pg_isready` / TCP / `nc`，无 HTTP、无响应体 |
| AC-07 数据持久化 | PASS | stop/start、force-recreate、down+up 后数据仍在；命名卷存在 |
| AC-08 迁移可重复、无 downgrade | PASS | `upgrade head` ×2 幂等；产物与文档无 `alembic downgrade` / `down -v` / `docker volume rm` |
| AC-09 部署文档 10 项 | PASS | 文档 §1~§13 逐项覆盖，且与编排可交叉核对 |
| AC-10 暴露面最小、无默认凭据 | PASS | 仅 nginx 发布；缺 env 时 `compose config` exit 1；镜像无凭据 |
| AC-11 无越界能力 | PASS | 负向 guard + 独立复核，无 HTTPS / K8s / 多机 / 监控 / MQ / Redis / ES |
| AC-12 文档可复现性 | PASS（L2 层面）/ 真实 VM NOT TESTED | 文档步骤在 L2 逐条可执行；未声称真实 VM |

**Product 裁定落实**：Confirmed #7（`CSM_ENVIRONMENT=prod`）、#13（`/api/health` 不豁免）、#14（探针走认证面之外、倾向 (a)）、#15（prod 关闭文档面）、#17（内网 HTTP / Cookie 无 `Secure` 写入文档）、#18（仅 nginx 入口）、#19（无默认口令）均逐条落地并可验证。**未发现越界能力，未新增产品 API 或 `/api/*` 豁免。**

## Architecture Compliance

- `Contract = NOT_REQUIRED` **成立**：`git diff develop...HEAD -- backend/app` 仅 `main.py` 一处行为变更，未新增 / 修改任何产品端点；探针取 (a) 传输层，未引入任何 HTTP 路径。
- 12 问裁定逐条落实：Q2（编排 / 仅 nginx 发布 / 命名卷 / restart / 依赖顺序）、Q3（`prod` 硬编码 + 后端关文档面 + nginx 纵深 + 可失败断言）、Q4（`pg_isready` / TCP / `nc`）、Q5（`${VAR:?}` fail-closed + 空模板）、Q6（命名卷 + 禁删卷）、Q7（显式 `run --rm --no-deps app alembic upgrade head`，非 entrypoint 自动执行）、Q8（`postgres:16` + `C.UTF-8` + 直连断言）、Q9（`5+10=15<100` 显式）、Q10（单一权威文档 + README 指向 + dev compose 措辞修正）、Q11（L1/L2/L3 证据层级）、Q12（边界声明）均符合。
- **REQUIRED #1 ~ #13 全部满足**：见上表与 Backend / Frontend 结论；未引入 HTTPS / K8s / 多机 / 监控 / MQ / Redis / ES；未改领域规则、唯一性、状态、删除语义、错误信封、契约或 ADR。
- 唯一偏差：Architecture Handoff Q2 / PROPOSED #4 文字写 nginx 构建 `context: ./frontend`（见 REV-01），与实现（仓库根）不一致；该偏差不影响任何 REQUIRED 项与 AC，属 Handoff 自身文字不自洽，见 Findings。

## Database Review

`database: false` **独立确认**：`git diff develop...HEAD -- backend/migrations/` 为空，迁移链 head 仍 `0002_f013_auth`，未修改 `0001` / `0002`，未新增 Schema / 索引 / 约束 / migration。

- 真实库（pytest `csm_rev` 与 L2 编排库）`alembic upgrade head` 可应用、第二次 no-op、`current` 稳定 head。
- L2 部署库直连：`datcollate=datctype=C.UTF-8`、`encoding=UTF8`、PG `16.15`、`max_connections=100`、`('cluster-a'='Cluster-A')=false`（§22 大小写敏感在部署库成立）。
- 编排在命名卷**首次初始化**时固定 locale（`POSTGRES_INITDB_ARGS` / `LANG` / `LC_ALL`），并以文档 §6 明确「录数据前校验、不符则重建卷」；未把 `PROPOSED` / `OPEN` 静默实现为不可逆规则。
- 未引入任何破坏性数据库动作；生产文档与产物无 downgrade / 删卷指引。

## Backend Review

- `docker diff`（develop...HEAD）中后端源码仅 `backend/app/main.py`：`docs_enabled = settings.environment != "prod"` 传入 `docs_url/redoc_url/openapi_url=None`。未触动 `AuthMiddleware`、`EXEMPT`、路由、错误信封、`/api/health` 或任何 `/api/*` 语义。
- 未给 `config.py` 增加第二个「文档开关」真相来源（符合 Q3 拒绝替代）。
- `backend/Dockerfile`：`python:3.12-slim`、仅 `requirements.txt`、非 root（`User=csm` / uid 10001）、`Cmd` 无 `--reload`、镜像内无 `CSM_*` / 凭据 / DSN（独立 `image inspect` 确认）、无 healthcheck 指令（探针由编排提供）；`COPY backend ./backend` 使 `alembic upgrade head` 与 `python -m app.auth.cli` 可在容器内运行（独立复现成功）。
- F012 / F013 / F014 行为无回归：未改动既有测试与源码，全量 192 passed。

## Frontend Review

- `frontend: false` **成立**：`git diff develop...HEAD -- frontend/` 仅新增 `frontend/Dockerfile`，`frontend/src/**` 无改动。
- 生产前端由多阶段构建（`node:22-alpine` → `npm ci` → `npm run build` → `nginx:stable-alpine`）产出 `dist/` 并由 nginx 静态服务；前端沿用同源相对 `/api`，无需 `VITE_API_BASE`。独立 `docker run` 确认镜像内 `/usr/share/nginx/html` 含 `index.html` + `assets/`，配置含 3 处 `return 404`、无 `ssl`。
- 未偷偷增加 CRUD、未混淆 Empty / Error、未错误展示领域状态、未引入不必要依赖。

## Test Review

- **覆盖真实性**：F015 新增 3 个测试文件（`test_f015_prod_surface.py` T-01 ~ T-04、`test_f015_deployment_guards.py` G-01 ~ G-08、`database/test_f015_locale.py` T-05）；未修改 / 删除任何既有测试（`git diff --name-status` 仅 `A` 三条）。Reviewer 独立全量重跑 **192 passed，无 skipped**。
- **可失败性**：Reviewer 以内存注入独立复现 guard 失败（凭据默认值 / HTTP 探针 / `down -v`），确认 guard 会真实失败，而非迎合实现。
- **L2 证据可信**：Reviewer 从零构建镜像并实际运行三容器栈，复现了 Tester 的关键断言（迁移幂等、管理员幂等、登录往返、401、docs 404 双层、仅 nginx 端口、locale / 大小写、持久化）。Tester 未把 L2 冒充 L3，`AC-02` / 真实 VM 明确 `NOT TESTED` 并附复核清单，符合 Handoff 的 L3 规则。
- **无执行顺序依赖**：T-03 以未认证 / 已认证两类夹具分离，避免夹具互相重置。
- 无「为使测试通过而弱化断言」的证据；`EXEMPT` 未被放大；`/api/health` 保持受保护。

## Findings

### REV-01

Severity:
LOW

Layer:
Architecture / Documentation

Location:
`docs/architecture/f015-deployment-handoff.md` Q2（行 226）、PROPOSED #4（行 588）、行 147

Problem:
Architecture Handoff 三处写明 nginx 服务使用 `frontend/Dockerfile` 且构建 `context = ./frontend`，但同一 Handoff 又要求该 Dockerfile 「复制 `dist` 与 `deploy/nginx/default.conf`」。`deploy/nginx/default.conf` 位于 `frontend/` 之外，`./frontend` 上下文在技术上无法完成该 COPY —— Handoff 文字自身不自洽。实现选择 `context = 仓库根`（`docker-compose.prod.yml` 中 nginx `build.context: .` + `dockerfile: frontend/Dockerfile`），是唯一自洽解。

Evidence:
`docker-compose.prod.yml` nginx 服务 `build.context: .`、`dockerfile: frontend/Dockerfile`；`frontend/Dockerfile` 含 `COPY deploy/nginx/default.conf ...`；Reviewer 以该上下文从零构建成功（镜像内 `default.conf` 含 3 处 `return 404`）。Handoff 行 147 / 226 / 588 仍写 `context: ./frontend`。

Impact:
无功能 / 安全 / 验收影响（不属任何 REQUIRED 项，无 AC 依赖）。风险在于后续读者据 Handoff 文字改动 `context` 会立即破坏构建。

Expected:
由 Architect / 协调器把 Handoff（及如涉及的 PROPOSED / Q2 文字）同步为「`context = 仓库根`」，或明确改为多阶段内自带 nginx 配置的其他自洽方案；实现无需回退。

Suggested Owner:
Architect / Coordinator

### REV-02

Severity:
LOW

Layer:
Project Metadata

Location:
`docs/project/project-plan.yaml` > `F015.git.head_commit`

Problem:
`head_commit` 记为 `056c0547…`（实现提交），而本次已审查候选 HEAD 为 `f536b064…`（测试 / 报告提交，且该提交自身更新了 `project-plan` 的 `current_stage` / `test` 字段）。计划元数据与已审查 HEAD 不一致。

Evidence:
`git rev-parse HEAD` = `f536b064826c4187f4ef422d47e517bdf10cb0bf`；`project-plan.yaml` F015 `head_commit: 056c0547b4001abbda4b3c88c22aff6f2cb2a712`。

Impact:
追溯性瑕疵：Review 结论与 Merge Gate 需要明确对应到被审查的 HEAD；元数据陈旧会使「已审查对象」含糊（与 F013 REV-02 同类）。

Expected:
Merge Gate 前由协调器把 `F015.git.head_commit` 更新为被审查 / 合并候选的 HEAD，并在合并后填 `merge_commit`。

Suggested Owner:
Coordinator

### NOTE-01

Severity:
NOTE

Layer:
Deployment / Documentation / Test

Location:
`docs/deployment/csm-v1-internal-deployment.md` §5、§10；`tests/test_f015_deployment_guards.py` G-04

Problem:
文档以「会删除数据卷的 `down` 选项（例如删除命名卷的变体）」「不要使用会删除命名卷的 `down` 变体」表述禁令，未写出确切标志 `down -v`。原因是 G-04 对 `down -v` 做字面子串断言，任何出现（即使是「禁止执行 `down -v`」的告警）都会 FAILED。

Evidence:
G-04 `FORBIDDEN_COMMANDS = ["alembic downgrade", "down -v", "docker volume rm"]`；文档 §5/§10 用迂回措辞。Reviewer 的 `down_v` 注入使 G-04 FAILED。

Impact:
无正确性影响（禁令语义完整、无破坏性指引）。运维可能不易把该措辞对应到确切命令。

Expected:
后续可把 G-04 从「字面禁止」细化为「允许出现在显式禁令上下文中」，使文档能直书 `docker compose down -v` 以便运维识别；或保持现状并接受该表述。属 Follow-up。

Suggested Owner:
Tester / Architect

### NOTE-02

Severity:
NOTE

Layer:
Test

Location:
`tests/database/test_f015_locale.py`

Problem:
`test_t05_encoding_and_locale_are_fixed` 断言 `encoding == "UTF8"` 且 `datcollate == datctype`，未断言字面值 `C.UTF-8`（Handoff T-05 原措辞为 `C.UTF-8`）。文件 docstring 说明原因为测试库可能继承宿主 locale。

Evidence:
测试源码与 docstring；生产固定值 `C.UTF-8` 由 `test_g01_postgres_locale_fixed`（编排 `POSTGRES_INITDB_ARGS`）与部署文档 §6 固定；Reviewer 在 L2 部署库直连实测 `C.UTF-8|C.UTF-8|UTF8`。

Impact:
无缺陷：该 pytest 面向本地测试库，生产 `C.UTF-8` 由静态 guard + 文档 + 部署库直连断言共同覆盖。

Expected:
无需修改；如追求更严，可在部署 E2E 中把字面 `C.UTF-8` 断言脚本化。

Suggested Owner:
Tester（可选）

### NOTE-03

Severity:
NOTE

Layer:
Backend / Deployment

Location:
`backend/Dockerfile`

Problem:
`COPY backend ./backend` 会把 `backend/Dockerfile` 一并复制进运行镜像（`/app/backend/Dockerfile`）。无害但不整洁。

Evidence:
`docker run --rm --entrypoint sh csm-prod-app -c "ls /app/backend"` → 含 `Dockerfile`。

Impact:
无功能 / 安全影响。

Expected:
可选：以更精确的 COPY 或 `.dockerignore` 排除 `backend/Dockerfile`。非必需。

Suggested Owner:
Backend（可选）

### NOTE-04

Severity:
NOTE

Layer:
Deployment / nginx

Location:
`deploy/nginx/default.conf`

Problem:
文档面阻断仅精确匹配 `/docs`、`/redoc`、`/openapi.json`；带尾斜杠或子路径的变体（如 `/docs/`、`/openapi.json/`）会落到 SPA fallback 返回 `index.html`（200 HTML）。

Evidence:
`location = /docs` 为精确匹配；`location / { try_files $uri $uri/ /index.html; }`。Reviewer L2 中精确路径均 404。

Impact:
无数据 / schema 泄露（返回的是 SPA HTML，且 app 层在 prod 下亦无这些路由），AC-05 成立。仅提示纵深防御的匹配面。

Expected:
无需修改；如需更严可加前缀匹配。属 Follow-up。

Suggested Owner:
Deployment（可选）

### NOTE-05

Severity:
NOTE

Layer:
Deployment / nginx

Location:
`deploy/nginx/default.conf`

Problem:
`proxy_set_header Cookie $http_cookie;` 与 nginx 默认转发 Cookie 行为重复。

Evidence:
nginx 默认已透传 Cookie；显式设置无副作用。

Impact:
无。

Expected:
可保留（显式声明意图）或删除。非必需。

Suggested Owner:
Deployment（可选）

## Existing Defects

Tester 报告 **无 Defects**（无 BLOCKER / HIGH / MEDIUM / LOW）。Reviewer 逐项复核其唯一记录项：

- **Tester NOTE：frontend Dockerfile build context（Handoff 写 `./frontend`，实现用仓库根）** → **判定成立，且严重程度合理（NOTE / LOW）**。Reviewer 独立验证该 Dockerfile 必须 COPY `deploy/nginx/default.conf`，`./frontend` 上下文不可行；实现选择内部自洽且构建成功，不影响任何 AC。**确认无需实现回退**；但责任落点应从「仅实现说明」上升为 **Handoff 文字需由 Architect 修正**（记为 REV-01，LOW，非阻塞）。

Reviewer 未发现 Tester 遗漏的 Defect。无严重程度被不当继承或压低。

## Non-blocking Follow-ups

1. **REV-01**：由 Architect / 协调器把 `docs/architecture/f015-deployment-handoff.md` 的 nginx 构建上下文文字同步为「仓库根」。
2. **REV-02**：Merge Gate 前由协调器更新 `project-plan.yaml > F015.git.head_commit`（被审查 / 合并候选 HEAD），合并后填 `merge_commit`。
3. **NOTE-01**：考虑细化 G-04 使部署文档可直书 `docker compose down -v` 禁令。
4. **NOTE-02 / NOTE-03 / NOTE-04 / NOTE-05**：可选工程整洁项，非必需。
5. **L3 真实验收**：由用户 / 运维按 `docs/test-reports/f015-deployment.md` 的 L3 复核清单在真实内网 VM + 另一台内网机器执行 AC-01 / AC-02 / AC-12 完整形式。

## Unreviewed Areas

1. **L3 真实独立内网虚拟机 + 另一台内网机器**（AC-02 及 AC-01 / AC-12 完整形式，T-08）：Agent 环境不可得；以 L2 等价环境为等价证据，未声称通过。
2. **真实浏览器 DOM / 视觉 / 网络**：无浏览器自动化；以返回 HTML 与 SPA fallback 判定。
3. **无 layer cache 的从零构建耗时 / 离线可构建性**：本次构建有网络与部分缓存；离线 VM 的 pip / npm 源可达性属运维前置（DR6 / NQ-4）。
4. **应用镜像层面的升级 / 回滚流程**：不在 F015 范围（NQ-7 / PROPOSED）。
5. **F012 / F013 / F014 已独立 Review 的领域实现本身**：本次仅确认无回归，未重新审查其领域语义。

---

## Review Verdict

不存在 BLOCKER / HIGH；不存在必须在当前 Feature 修复的 MEDIUM。AC-01 ~ AC-12 均有结果、核心验收满足；测试可信（Reviewer 以真实 PostgreSQL **独立全量重跑 192 passed 无 skip**、guard 对抗注入**独立确认可失败**、**从零构建并实际运行 L2 三容器端到端**并复核后清理）；`database: false` / `frontend: false` / `Contract = NOT_REQUIRED` 成立；唯一后端行为变更为 `prod` 关闭框架文档面，未触动认证 / 路由 / 错误处理，F012 / F013 / F014 无回归；实现未超范围、未引入未经确认的能力、未改动领域规则 / 契约 / ADR。

存在 2 项 LOW（REV-01 Handoff 构建上下文文字不自洽、REV-02 计划元数据陈旧，均不阻塞 Merge）与 5 项 NOTE。

**`APPROVED WITH FOLLOW-UP`** — 可进入 Merge Gate。Merge 前建议协调器处理 REV-01（Architect 更正 Handoff 文字）与 REV-02（计划元数据更新）；NOTE-01 ~ NOTE-05 可后续收口。

---

GIT: NONE
