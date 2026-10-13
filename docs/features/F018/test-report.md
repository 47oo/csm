# F018 前端改造后一期整体验收复验 — Test Report

本文件承载 TEST_DESIGN 与后续 TEST（TE 阶段在同一文件追加执行结果）。TEST_DESIGN **不填充执行 PASS**、不写 `project.acceptance`；执行结果全部标 `待执行（TE-1）`。

---

## Test Design

- **版本**：TD-1
- **日期**：2026-10-13
- **角色**：Tester（TEST_DESIGN 模式）
- **结论**：`TEST DESIGN READY`（TD-1）
- **依据**：
  - `docs/features/F018/product.md`（PRODUCT `READY FOR ARCHITECT`；R-1..R-10 / AC-1..AC-10 / §5 环境与限制）。
  - `docs/features/F018/architecture.md`（ARCHITECTURE `READY FOR DESIGN`；§1 验收架构、§1.5 环境限制与浏览器工具批准、§3 映射、§4 测试脚本、§5 风险、§6 待核对）。
  - `docs/features/F016/test-report.md`（TD-1/TD-2/TE-1；§2.2 等价替代栈、§2.4 差异声明、§7 清理纪律、§8 环境；REUSE 锚点 `#32-c1c15-上线验收` / `#33-目标查询场景`）。
  - `docs/features/F017/architecture.md` §5 V5–V7 / §1.2–1.3（layer 顺序 `theme, base, antd, components, utilities`；`StyleProvider layer`）；`docs/features/F017/review-report.md` §6 Follow-ups（F-018、D-4 视觉确认）。
  - `docs/product/requirements-v3.md` revision 4 CONFIRMED：§28/§29/§30/§31/§32/§33。
  - `docs/project/{handoff,implementation-rules,project-state,change-control,git-workflow}.md`；`.pi/skills/data-integrity/SKILL.md`。
  - `docs/project/project-plan.yaml` F018（plan_revision 5；`layers={database:false,backend:false,frontend:false}`、`api_required=false`、`test_design: PENDING`）。
  - 落地资产：`scripts/acceptance/{run_acceptance.sh,verify_audit_backup.sh,README.md,.gitignore}`、`backend/tests/integration/f016_helpers.py`、`deploy/nginx/nginx.conf`、`frontend/nginx.conf`、`frontend/package.json`、`frontend/src/index.css`、`frontend/src/main.tsx`。
- **状态属性**：TD-1 `READY` 仅表示 R-1..R-10 / AC-1..AC-10 已映射到可观察判据、栈启动（Compose 尝试 + 失败录制 + 等价替代栈）与差异声明、浏览器工具引入范围与 NOT TESTED 规则、脚本/夹具落点与清理纪律、环境与不可验证项已建立并可在 TE-1 执行；**不代表测试已运行、不填充执行 PASS、不批准实现或合并，也不构成 `project.acceptance=COMPLETE`**。

### 版本记录

| 版本 | 日期 | 变更 |
| --- | --- | --- |
| TD-1 | 2026-10-13 | 初版：AC-1..AC-10 可执行映射（自动/人工）；F018 等价替代栈与 Compose 尝试/差异声明；浏览器工具引入裁决（test-only playwright-core + 缓存 Chromium + 非 root 本地库抽取）与 NOT TESTED 规则；`run_f018_acceptance.sh` / `f018_browser_check.mjs` 落点与复用；清理纪律；环境与不可验证项；结论。 |

### 0. 数据完整性对应表（F018 范围）

方法依据 `.pi/skills/data-integrity/SKILL.md`。F018 为**验收复验型 Feature**：不新增/变更任何对象、关系、状态、唯一性、生命周期、Schema、Migration 或索引（与 plan_revision 5 `layers.database=false`、architecture §2 一致）。

| 规则依据及版本 | 作用域 | 数据库保证（既有） | 业务层保证 | 并发/生命周期边界 | 验证与证据 |
| --- | --- | --- | --- | --- | --- |
| F018 无新增 | — | 无 Schema/迁移/约束/索引变更 | 仅复验既有前端证据 | 不涉及 | `docs/database/f016-acceptance.md`（NOT_REQUIRED）；F018 复核 `alembic current` 无新增 head（TE-1 记录） |

> 说明：F018 不复验、不回写 F001–F016 后端/数据库/API/备份证据；本表仅登记「F018 无数据层交付」。数据完整性结论 `NOT_REQUIRED`（expected），由 Database 角色在定稿阶段确认，Tester 不代替签核。

---

## 1. 验收映射与可执行步骤（R-1..R-10 / AC-1..AC-10）

执行环境代号：`Compose`＝`docker compose -p csm_f018 up -d --build`（§30，入口 :80）；`替代栈`＝F016 §2.2 等价真实栈（入口 `http://localhost:18080`）；`真HTTP`＝经入口 Nginx 的真实 HTTP（非 Mock / 非 TestClient）；`浏览器`＝TD §3 裁决的 test-only headless Chromium；`静态`＝源码/Git 范围检查；`协调器`＝非 Tester 执行项。结果列 TE-1 填充，TD-1 一律标 `待执行（TE-1）`。

| R / AC | 执行步骤（可执行） | 可观察判据（PASS/FAIL） | 自动/人工 | 结果 |
| --- | --- | --- | --- | --- |
| R-1 / AC-1 | `cd frontend && npm run typecheck`；`npm run build`；`find frontend/dist -name '*.css' -size +0c \| wc -l`（>0）；`npm run smoke:client`；`grep -c "await test(" frontend/scripts/smoke-client.mjs` | typecheck/build 退出码 0；dist 非空 CSS ≥1；smoke 输出 `N passed, 0 failed` 且 `N ≥ 264`；断言计数 ≥264（无删减） | **自动** | 待执行（TE-1） |
| R-2 / AC-2 | 经入口 `curl -fsS -o /dev/null -w '%{http_code}'` 依次 `/healthz`、`/api/v1/health/ready`、`/`、`/clusters`；`curl -fsS /` 与 `/clusters` 比对 | `/healthz`=200、`/api/v1/health/ready`=200、`/`=200 且含入口标记 `<div id="root"></div>`（含 `<title>CSM</title>`）；`/clusters`=200 且返回与 `/` 同一入口（SPA fallback 生效） | **自动** | 待执行（TE-1） |
| R-3 / AC-3 | 浏览器加载 `http://localhost:18080/`：读取 `document.styleSheets` 的 `@layer` 顺序；断言 AntD 组件（如 `Button`）computed style 来自 `antd` 层；断言 Tailwind utility 类覆盖 AntD；断言 preflight 未破版（`body` margin 0、标题/列表默认样式受控）；截图 + computed style JSON | layer 顺序含 `theme, base, antd, components, utilities`（无 `legacy`）；AntD 样式生效；utility 覆盖 AntD；preflight 未破坏布局；证据含截图或 computed style | **人工（浏览器）** | 待执行（TE-1） |
| R-4 / AC-4 | 经 `真HTTP`（ADMIN）创建无 `AUDIT_READ` 用户、无 `USER_ADMIN`/`VIEW_DELETED` 用户；浏览器分别登录，断言 Audit(`AUDIT_READ`) / System(`USER_ADMIN`\|`VIEW_DELETED`) 入口显隐与可达性（无权限时入口不显示，直接导航不可访问） | 无权限入口不显示且不可访问；带权限入口可见可访问；判据含截图/DOM 断言 | **人工（浏览器）** + 真HTTP 数据 | 待执行（TE-1） |
| R-5 / AC-5 | 浏览器抽查列表/详情（Clusters 列表、Resource 详情、Audit 列表）四态：Loading（请求进行中）、Success（有行）、Empty（真实过滤命中 0）、Error（真实请求非 2xx，如详情不存在/后端不可达）；观测与真实请求状态一致 | 每个抽查页分别呈现 Loading / Success / Empty / Error 且与实际请求状态一致；不得以 Mock 数据替代真实 API 成功态 | **人工（浏览器）** | 待执行（TE-1） |
| R-6 / AC-6 | `真HTTP` 触发 401（无 Cookie）、403（VIEWER/EDITOR 越权）、409（陈旧 `version` PATCH）、422（非法输入）；浏览器观测呈现 | 401→全局回登录页；403→错误提示；409→`VERSION_CONFLICT` 提示；422→字段校验错误；语义与迁移前一致 | **半自动**（HTTP 自动 + DOM 人工） | 待执行（TE-1） |
| R-7 / AC-7 | `静态`检索 `frontend/src/pages/AuditPage.tsx`、`frontend/src/components/AuditQueryPanel.tsx` 无修改/删除/清空控件与处理器；浏览器打开 Audit 页核验仅查询控件 | Audit 界面无修改/删除/清空控件与入口；仅查询能力（含 ADMIN） | **半自动** | 待执行（TE-1） |
| R-8 / AC-8 | 浏览器执行分页/排序/过滤/模糊搜索，抓取网络请求；断言参数名：过滤用 `type`、排序用 `resource_type`，两者不可互换；对照 F016/契约既有请求实参 | 分页/排序/过滤/模糊搜索可用；请求参数与迁移前逐一致（`type` 过滤名、`resource_type` 排序字段） | **半自动**（浏览器网络日志） | 待执行（TE-1） |
| R-9 / AC-9 | §32 C1–C15、§33 Q1–Q9 的**数据层**：`REUSE` F016 TE 真 HTTP 证据锚点（`docs/features/F016/test-report.md#32-c1c15-上线验收`、`#33-目标查询场景`）；**界面呈现**：浏览器复核相应页面；C15 为跨 F018 复验项 + F016 证据的实际汇总 | 数据层锚点存在且指向真 HTTP 证据；界面呈现有浏览器证据；C15 为实际汇总（非局部拼接），缺证据项标 `NOT TESTED` | **REUSE（数据层）+ 人工（呈现）** | 待执行（TE-1） |
| R-10 / AC-10 | 浏览器核验 ClustersPage 表头/表体列对齐（`version`/`created_at`/`updated_at`）；抽查 Resources/Networks/Services/IpAddresses 等列表无同类列错位 | ClustersPage 列对齐修正无误；抽查其余页面无同类列错位；证据含截图/列结构比对 | **人工（浏览器）** | 待执行（TE-1） |

**NOT TESTED 标注规则（TD-1 固定）**：

1. 任一未在真实渲染中执行的 DOM 判据（AC-3/4/5/6/7/8/10）一律标 `NOT TESTED`，不得写 PASS。
2. 机制证据（`typecheck`/`build`/`smoke:client`/`curl`）不得替代运行时渲染与 DOM 结论。
3. Compose 未成功须录制并声明替代栈，不得写 Compose PASS。
4. 缺证据项（§32/§33 未复核的呈现项）不得拼成整体 PASS。
5. `smoke:client` 断言与用例数不得删减；`typecheck`/`build` 不得为过而改源码。

---

## 2. 等价替代栈与 Compose 尝试 / 差异声明

### 2.1 首选 Compose 尝试与失败录制（复用 F016 TD §2.1）

1. **Preflight（只读）**：`git rev-parse HEAD`、`git status --porcelain`；确认 `docker`、`node`、镜像 `postgres:16` / `nginx:1.27-alpine` / `csm-f007-test`；准备独立项目名 `csm_f018` 与库 `csm_f018_acc`（凭据经环境变量，不入库）。
2. **尝试**：`docker compose -p csm_f018 up -d --build 2>&1 | tee scripts/acceptance/artifacts/run-<utc>/compose-up.log`，记录 `EXIT_CODE=`；失败后 `docker compose -p csm_f018 down -v`。
3. **结果处理**：成功则按 §2.3 健康判据验证并记录 `docker compose ps`；失败则**如实录制**退出码与日志路径后切换替代栈。**不得伪造 Compose PASS。**
4. **环境性预期**（同 F016 TE-1）：`docker build`/Compose 依赖 Docker Hub + `deb.debian.org`，本环境实测不可达，预期退出码非 0；实际路径 TE-1 录制。

### 2.2 真实等价替代栈（F016 §2.2 同构，F018 命名隔离）

`scripts/acceptance/run_f018_acceptance.sh` 固化，凭据经环境变量：

```bash
docker network create f018-acceptance-net
docker run -d --name f018-db --network f018-acceptance-net --network-alias db \
  -e POSTGRES_USER=csm -e POSTGRES_PASSWORD="$F018_PW" -e POSTGRES_DB=csm_f018_acc postgres:16
# 等待 pg_isready 后：
docker run -d --name f018-backend --network f018-acceptance-net --network-alias backend \
  -v "$PWD/backend:/app" -w /app \
  -e DATABASE_URL="postgresql+psycopg://csm:$F018_PW@db:5432/csm_f018_acc" \
  -e INITIAL_ADMIN_USERNAME="$F018_ADMIN_USER" -e INITIAL_ADMIN_PASSWORD="$F018_ADMIN_PW" \
  csm-f007-test bash -lc "pip install -q 'python-multipart>=0.0.9,<0.1' 'openpyxl>=3.1,<3.2' \
    && alembic upgrade head && python -m app.cli.bootstrap_admin \
    && exec uvicorn app.main:app --host 0.0.0.0 --port 8000"
( cd frontend && npm ci && npm run build )     # 本地构建 dist/
docker run -d --name f018-frontend --network f018-acceptance-net --network-alias frontend \
  -v "$PWD/frontend/dist:/usr/share/nginx/html:ro" \
  -v "$PWD/frontend/nginx.conf:/etc/nginx/conf.d/default.conf:ro" nginx:1.27-alpine
docker run -d --name f018-nginx --network f018-acceptance-net -p 18080:80 \
  -v "$PWD/deploy/nginx/nginx.conf:/etc/nginx/nginx.conf:ro" nginx:1.27-alpine
```

关键约束：网络别名 `db`/`backend`/`frontend` 使**未改动**的 `deploy/nginx/nginx.conf` upstream 免改解析；后端镜像挂载 `./backend` + `alembic upgrade head`（预期 head 与 F016 一致）+ `bootstrap_admin` + `uvicorn`；前端本地产物由 `nginx:1.27-alpine` 服务；同源统一经 `http://localhost:18080`（写请求 `Origin`/`Host` 同源，验证 401 先于 403）。

### 2.3 健康判据

| 判据 | 命令 | 期望 |
| --- | --- | --- |
| 入口存活 | `curl -fsS http://localhost:18080/healthz` | `200`，body `ok` |
| 就绪（经 Nginx→backend） | `curl -fsS http://localhost:18080/api/v1/health/ready` | `200` |
| 前端入口 | `curl -fsS http://localhost:18080/` | `200` 且含 `<div id="root"></div>` |
| SPA fallback | `curl -fsS http://localhost:18080/clusters` | `200` 且与 `/` 同一入口 |
| 迁移 head | `docker exec f018-backend alembic current` | 与 F016 TE-1 一致（`0013_search_indexes (head)`），无 F018 新增 head |

就绪轮询超时（建议 180s）内任一未达即记 `BLOCKED`，不得继续伪造后续用例结果。

### 2.4 与 Compose 的差异声明（同 F016 §2.4，A13）

| 维度 | Compose | F018 替代栈 | 影响 |
| --- | --- | --- | --- |
| 镜像构建 | `docker build`（backend/frontend） | 复用 `csm-f007-test` + bind-mount 代码 | 未经镜像构建固化，代码源锁定候选 HEAD |
| 代码来源 | 镜像内置 | `-v ./backend:/app` | 现场代码 = 候选 HEAD |
| 配置注入 | `.env`/`env_file` | `-e` 环境变量 | 语义等价，凭据不入库 |
| 编排时序 | `depends_on` 条件 | 脚本强制顺序 + 就绪轮询 | 无 `depends_on`，靠脚本保证 |
| 前端 | 镜像内构建产物 | 本地产物 + 静态服务 | 拓扑等价，构建在宿主 |
| 卷 | 命名卷 `pgdata` | 独立库 `csm_f018_acc`（无命名卷） | 生命周期隔离 |
| 入口路由/同源 | `deploy/nginx/nginx.conf` | 同一文件，端口 18080 | 路由与同源语义一致 |

**必须如实记录，不得以替代栈冒充 Compose。**

---

## 3. 浏览器工具引入裁决（architecture §1.5 授权范围）

### 3.1 裁决：**批准引入 test-only 浏览器 harness（受环境条件约束）**

architecture §1.5 已**批准新增 test-only 浏览器验证工具**（不入生产、不改 `frontend/src`、`frontend/api`、`smoke-client.mjs`、`package.json` production 依赖）。TD-1 据此裁决如下：

| 项 | 裁决 |
| --- | --- |
| 落点 | `scripts/acceptance/browser/`（含自有 `package.json` + `package-lock.json` + `node_modules/` 与 `f018_browser_check.mjs`）；**不修改** `frontend/package.json` / `package-lock.json` |
| 依赖 | `playwright-core`（test-only，pin 版本）；npm registry 实测可达（`npm view playwright version`→`1.64.0`），亦可优先用 npm 缓存中的 `playwright-core-1.62.1.tgz` 离线安装 |
| 浏览器可执行 | `executablePath` 指向宿主缓存 `~/.cache/ms-playwright/chromium_headless_shell-1234/chrome-headless-shell-linux64/chrome-headless-shell`（回退 `chromium-1234/chrome-linux64/chrome`）；`executablePath` 绕过版本校验 |
| 缺失系统库 | 宿主缺 `libnspr4.so`/`libnss3.so`/`libnssutil3.so`/`libasound.so.2`；**无 root、无 `sudo`**；`archive.ubuntu.com` / `security.ubuntu.com` 实测可达，`deb.debian.org` 不可达。用非 root 方式：`apt-get download libnspr4 libnss3 libnssutil3 libasound2t64` + `dpkg-deb -x <pkg>.deb scripts/acceptance/artifacts/browser-libs/`，以 `LD_LIBRARY_PATH` 前缀启动 |
| 触发时机 | TE-1 在栈就绪后执行有界尝试（启动 ≤ 1 次探测 + 有限重试）；不得无限重试 |
| 失败回退 | 若安装或启动仍不可行 → **所有 DOM 判据（AC-3/4/5/6/7/8/10）标 `NOT TESTED`**，不得以 build/机制证据冒充 PASS；需在报告显式记录失败命令、退出码与缺失项 |

### 3.2 浏览器校验范围（`f018_browser_check.mjs`）

按优先序覆盖：R-3（layer 顺序 / AntD 渲染 / utility 覆盖 / preflight）→ R-4（权限门控）→ R-10（列对齐）→ R-5（四态）→ R-6（错误呈现）→ R-7（Audit 无写入口）→ R-8（列表参数）。输出证据到 `scripts/acceptance/artifacts/run-<utc>/browser/`（截图 PNG + `layer-order.json` + `computed-style.json` + `network-params.json`）。未覆盖项在上述输出中显式列 `NOT TESTED`。

### 3.3 真实集成口径

浏览器页面必须经**真实 API**（入口 `http://localhost:18080`）加载；权限会话由 `真HTTP` 创建的用户真实登录产生；不得以 Mock/路由拦截替代成功态真实数据（implementation-rules「真实集成不能用 Mock 结果代替」）。触发 Empty/Error 态优先用真实过滤命中 0 / 真实非 2xx 请求；如确需页面态触发，仅用于「变化」而不改写成功态数据，并在报告中注明。

---

## 4. 脚本 / 夹具（允许改测试代码，不改生产实现）

### 4.1 复用

- `scripts/acceptance/run_acceptance.sh`：复用其 Preflight / Compose 尝试与失败录制 / 替代栈命名/健康/清理**模式**（F018 复制为独立脚本，命名 `f018-*`，不改 F016 脚本）。
- `scripts/acceptance/README.md`、`scripts/acceptance/.gitignore`（`artifacts/`）。
- `backend/tests/integration/f016_helpers.py`：复用其真 HTTP `Api` 客户端与数据集构建（env 驱动，`F016_BASE_URL` 指向 F018 入口）；**不使用**其直连 DB 护栏（F018 不需直连库）。

### 4.2 新增（Tester 在 TE-1 落地）

| 脚本 | 职责 |
| --- | --- |
| `scripts/acceptance/run_f018_acceptance.sh` | Preflight → Compose 尝试与失败录制 → 替代栈（库 `csm_f018_acc`）→ 健康 + 入口 + SPA fallback → 前端 `typecheck`/`build`（断言 dist CSS 非空）/`smoke:client`（断言 ≥264）→ 经真 HTTP 播种权限用户/最小数据（供浏览器）→ 有界调用浏览器 harness → 清理；产物 `artifacts/run-<utc>/` |
| `scripts/acceptance/browser/f018_browser_check.mjs` | test-only headless Chromium 校验（§3.2），输出截图/样式/DOM/网络证据；缺依赖或启动失败时整体 skip 并标 `NOT TESTED`，不写 PASS |
| `scripts/acceptance/browser/package.json`(+lock) | `playwright-core` test-only 依赖；独立于 `frontend/package.json` |

### 4.3 禁止

改动 `frontend/src/**`、`frontend/src/api/*.ts`、纯逻辑 `*.ts`、`frontend/scripts/smoke-client.mjs` 断言、`frontend/package.json` production 依赖、`backend/**` 生产实现、`compose.yaml`、`deploy/**`、`docs/api/**`、Schema/迁移、任何业务契约。F018 不新增业务规则。

---

## 5. 清理纪律

结束（除非 `F018_KEEP=1`）：

```bash
docker rm -f f018-nginx f018-frontend f018-backend f018-db
docker network rm f018-acceptance-net
docker exec f018-db psql -U csm -d postgres -c "DROP DATABASE IF EXISTS csm_f018_acc WITH (FORCE);"   # 移除容器前
rm -rf scripts/acceptance/artifacts/run-<utc>/backup scripts/acceptance/artifacts/browser-libs
```

- Compose 失败路径先 `docker compose -p csm_f018 down -v`。
- 清理后断言 `docker ps -a` / `docker network ls` / `docker volume ls` 无 `f018-*` 残留。
- `frontend/dist` 与 `scripts/acceptance/artifacts/`（含 `browser/node_modules`）为 git-ignored 构建/测试产物，不视为业务残留；`browser-libs` 为临时抽取库，须删除。

---

## 6. 环境与可验证性

| 项 | 判定 | 说明（TD-1 只读探测，2026-10-13） |
| --- | --- | --- |
| AC-1 | 可验证（自动） | `node v22.23.2` / `npm 12.0.2`；`npm run typecheck/build/smoke:client`；当前 `smoke-client.mjs` 计数 264 |
| AC-2 | 可验证（自动） | 替代栈 + 未改动 `deploy/nginx/nginx.conf`、`frontend/nginx.conf`（SPA `try_files … /index.html`）；入口标记 `<div id="root"></div>` |
| AC-3/4/5/6/7/8/10 | **条件可验证** | 浏览器工具按 §3 裁决尝试；宿主缓存 Chromium 存在但缺 4 个系统库；`archive.ubuntu.com` 可达可非 root 抽取；npm registry 可达装 `playwright-core`；失败则 `NOT TESTED` |
| AC-9 数据层 | 可验证（REUSE） | `docs/features/F016/test-report.md#32-c1c15-上线验收` / `#33-目标查询场景`（TE-1：真 HTTP，40 passed） |
| AC-9 呈现 | **条件可验证** | 同 AC-3 浏览器条件 |
| Compose 首选路径 | **预期 BLOCKED（已录制，非缺陷）** | Docker Hub + `deb.debian.org` 不可达（同 F016 TE-1）；如实录制后走替代栈 |
| 数据库 / Migration | `NOT_REQUIRED` | F018 无 Schema/迁移；`alembic current` 仅作入口就绪旁证（Database 角色定稿确认） |
| 并发 / 备份 / T01–T41 后端侧 | 不在范围 | 由 F001–F016 已确认证据承载，F018 不复验、不回写 |
| `project-state` 一致性 | 条件 | 项目状态文件有变更时运行 `scripts/validate_project_state.py`；结构通过不代表批准或 Git 证据有效 |

**不可验证 / 受限项（TD-1 预列，TE-1 据实更新）**：

1. Compose 首选路径（环境网络限制）→ BLOCKED，走等价替代栈并声明差异。
2. DOM 运行时渲染（若无浏览器工具）→ NOT TESTED，仅保留 build/smoke/HTTP 机制证据。
3. F018 不对 F001–F016 后端/数据库/API/备份证据负责复验。

---

## 7. OPEN 清单（TD-1，不阻塞 READY，TE-1 前/中核对）

| OPEN | 说明 | 影响 | Owner |
| --- | --- | --- | --- |
| F018-OPEN-1 | Compose 是否可构建取决于环境网络；TD-1 预期走替代栈，实际路径 TE-1 录制 | AC-2 | Tester/协调器 |
| F018-OPEN-2 | 浏览器运行时库非 root 抽取 + `playwright-core` 安装/启动能否成功；失败则 DOM 判据 `NOT TESTED` | AC-3/4/5/6/7/8/10 | Tester/协调器 |
| F018-OPEN-3 | 浏览器校验所需权限用户/最小数据集的真实 HTTP 播种细节（复用 `f016_helpers`） | AC-4/5/8 | Tester |
| F018-OPEN-4 | §32/§33 呈现项中哪些可在无浏览器时以机制证据记录、哪些必须 `NOT TESTED` 的逐项清单 | AC-9 | Tester |
| F018-OPEN-5 | `project.acceptance.evidence` 锚点与 COMPLETE 写入时机（Tester 不写） | 交接 | 协调器 |
| F018-OPEN-6 | 若 Test Design 判定浏览器工具落在 `frontend/scripts/`，仍属 TEST 基础设施、不改产品 layer；TD-1 裁决落在 `scripts/acceptance/browser/` | layer 声明 | Tester/Architect |

---

## 8. 缺陷路由

发现实现缺陷 → 按 Severity/Layer 记录，Owner 指向 F001–F017 对应责任 Feature；不静默修改业务实现/Schema/契约。测试基础设施缺陷 → 协调器。业务/架构歧义 → Product/Architect。修复后按 `feature.md` 有限修复循环重跑受影响项。

---

## 9. 结论

`TEST DESIGN READY`（TD-1）——R-1..R-10 / AC-1..AC-10 已逐条映射到可观察判据与自动/人工执行步骤；Compose 尝试+失败录制与等价替代栈、健康判据、差异声明已定；浏览器工具引入范围（test-only `playwright-core` + 缓存 Chromium + 非 root 本地库抽取）与 **NOT TESTED 规则**已固定；`run_f018_acceptance.sh` / `f018_browser_check.mjs` 落点与复用、清理纪律、环境与不可验证项明确。**READY 仅表示方案可验证，不代表测试已运行、不填充执行 PASS、不批准实现或合并、不构成 `project.acceptance=COMPLETE`。**

GIT: NONE

---

## Test Execution

- **版本**：TE-1（2026-10-13）
- **角色**：Tester（TEST 模式）
- **结论**：`READY FOR REVIEW`
- **Basis**：`docs/features/F018/{product,architecture}.md`（architecture §1/§3/§4/§7；CONTRACT `NOT_REQUIRED`）；本文件 `#test-design`（TD-1）；`docs/database/f018-acceptance.md` v1（`NOT_REQUIRED`，单 head `0013_search_indexes`）；`docs/features/F016/test-report.md`（等价替代栈 §2.2/§2.4、REUSE 锚点 `#32-c1c15-上线验收`/`#33-目标查询场景`）；`docs/project/{handoff,implementation-rules,project-state,git-workflow}.md`；`.pi/skills/data-integrity/SKILL.md`。
- **工作区/基线**：分支 `feature/F018-post-ui-acceptance`，HEAD `344ebeebd28afc58b220fe2ca46f1b3b5385625c`（只读核对）。
- **产物**：`scripts/acceptance/run_f018_acceptance.sh`、`scripts/acceptance/browser/{f018_browser_check.mjs,package.json,package-lock.json}`（test-only，未改生产代码）；运行产物 `scripts/acceptance/artifacts/run-20261013T062456Z/`（`compose-up.log`、`typecheck.log`、`build.log`、`smoke.log`、`health.txt`、`browser/`）。

### 环境

- 宿主：Ubuntu 24.04，`docker 29.8.0`、`node v22.23.2`/`npm 12.0.2`。
- 镜像（已缓存，无需 pull）：`postgres:16`、`nginx:1.27-alpine`、`csm-f007-test`。
- 网络限制：Docker Hub 不可达（`auth.docker.io` token i/o timeout）→ `docker build`/Compose 不可用（实测，见下）；改用 architecture §1.2 等价替代栈。
- 浏览器：宿主缓存 Playwright Chromium `chromium_headless_shell-1234`，缺 4 个系统库（`libnspr4.so`/`libnss3.so`/`libnssutil3.so`/`libasound.so.2`）；非 root 经 `apt-get download libnspr4 libnss3 libasound2t64` + `dpkg-deb -x` 抽取并以 `LD_LIBRARY_PATH` 启动；`playwright-core@1.64.0` 装在 `scripts/acceptance/browser/node_modules`（git-ignored）。无 root、无 `sudo`。

### 栈启动结果（Compose 尝试 + 等价替代栈 + 差异声明）

| 步骤 | 命令 | 结果 |
| --- | --- | --- |
| Compose 尝试 | `docker compose -p csm_f018 up -d --build` | **退出码 1**（`failed to fetch anonymous token … dial tcp … i/o timeout`），归档 `scripts/acceptance/artifacts/run-20261013T062456Z/compose-up.log`（含 `EXIT_CODE=1`）；随后 `docker compose -p csm_f018 down -v` |
| 等价替代栈 | network `f018-acceptance-net`；`postgres:16`（库 `csm_f018_acc`，别名 `db`）→ `csm-f007-test` 挂 `./backend` + `alembic upgrade head` + `bootstrap_admin` + `uvicorn`（别名 `backend`）→ 本地 `npm run build` 产物由 `nginx:1.27-alpine` 服务（别名 `frontend`）→ 入口 `nginx:1.27-alpine -p 18080:80` 挂**未改动**的 `deploy/nginx/nginx.conf` | 全部启动成功 |
| 健康/入口 | `/healthz`=200(body `ok`)、`/api/v1/health/ready`=200、`/`=200、`/clusters`=200 且与 `/` 同一入口（SPA fallback）；`alembic current`=`0013_search_indexes (head)` | **PASS**（`health.txt`） |

**与 Compose 的差异声明**（A13 同构，未以替代栈冒充 Compose）：镜像构建（复用缓存镜像 + bind-mount vs `docker build`）；代码来源（现场挂载候选 HEAD vs 镜像内置）；配置注入（`-e` vs `.env`）；编排（脚本时序 + 就绪轮询 vs `depends_on`）；前端（本地产物 + 静态服务 vs 镜像内构建）；卷（独立库 `csm_f018_acc` 无命名卷 vs `pgdata` 命名卷）；入口路由/同源（同一 `deploy/nginx/nginx.conf`，端口 18080，语义一致）。

### 验收映射 AC-1..AC-10（TE-1 结果）

| AC | 结果 | 证据 |
| --- | --- | --- |
| AC-1 | **PASS** | `npm run typecheck` rc=0（`typecheck.log`）；`npm run build` rc=0（`build.log`）；`find frontend/dist -name '*.css' -size +0c`=1；`npm run smoke:client`=`264 passed, 0 failed`（`smoke.log`）；`grep -c "await test(" smoke-client.mjs`=264（断言无删减） |
| AC-2 | **PASS** | 经入口真 HTTP：`/healthz`=200 `ok`、`/api/v1/health/ready`=200、`/`=200 含 `<div id="root"></div>` 与 `<title>CSM</title>`、`/clusters`=200 且 body 与 `/` 逐字节一致（SPA fallback 生效） |
| AC-3 | **PASS（浏览器真实渲染）** | layer 唯一序 `properties, theme, base, antd, components, utilities`（5 个共享层相对序正确，无 `legacy`；`properties` 为 Tailwind v4 内部层，位于最前）；`.ant-btn` 规则确在 `@layer antd` 内且按钮 classList 含 `ant-btn`（`computed-style.json`）；注入 `class="ant-btn px-0"` 探针 `padding-left=0px` → utilities 覆盖 antd（`utility-override.json`）；preflight `body{margin:0px;box-sizing:border-box}`（`preflight.json`）；截图 `ac3-layer-order.png` |
| AC-4 | **PASS（浏览器真实渲染）** | VIEWER 会话：`/auth/me` permissions 无 `AUDIT_READ`/`USER_ADMIN`/`VIEW_DELETED`，导航无 Audit/System，直接访问 `/audit` 仅回到应用壳未渲染 Audit 面板；ADMIN 会话导航含 Audit/System；截图 `ac4-viewer-nav.png`/`ac4-admin-nav.png` |
| AC-5 | **PASS（浏览器真实渲染，四态齐）** | Loading（真实响应延迟 800ms 后仍成功）`ac5-loading.png`；Success（真实行含种子 cluster `F18C-<runId>`）`ac5-success.png`；Empty（真实过滤命中 0，AntD Empty 文案）`ac5-empty.png`；Error（**真实杀掉 `f018-backend` 容器**触发的真实不可达错误，Alert `加载集群列表失败…`）`ac5-error.png`；均与实际请求状态一致 |
| AC-6 | **PASS（浏览器 + 真 HTTP）** | 401：清 Cookie 后触发受保护请求 → 全局回登录页（`input[autocomplete=username]` 出现，`ac6-401-relogin.png`）；403：EDITOR 提交前经真 API 降级为 VIEWER → 表单呈现「没有权限执行该操作…FORBIDDEN」（`ac6-403-forbidden.png`）；409：真 API 提升 version 后提交陈旧编辑 → 呈现「该资源已被其他人修改…」（`ac6-409-version-conflict.png`）；422：提交内含空格的非法 hostname（本地校验仅拦空值）→ 服务端 `VALIDATION_ERROR` 字段错误呈现（`ac6-422-validation.png`）；同源真 HTTP 另确认 403/409/422 状态码与错误码（`http-error-semantics.json`） |
| AC-7 | **PASS** | 静态：`frontend/src/pages/AuditPage.tsx`/`components/AuditQueryPanel.tsx` 无修改/删除/清空控件与处理器；浏览器 ADMIN 打开 Audit 页，交互控件仅为查询/重置/排序/详情/分页，无删除/清空/修改控件（`audit-controls.json`，`ac7-audit-page.png`） |
| AC-8 | **PASS** | 浏览器网络日志：类型过滤请求 `…/resources?type=BARE_METAL&deleted=exclude&page=1&page_size=20&sort=created_at&order=desc`；点击「类型」表头排序请求 `…&sort=resource_type&order=asc`；`type` 过滤名与 `resource_type` 排序字段不可互换（`network-params.json`，`ac8-resources-params.png`） |
| AC-9 | **PASS（数据层 REUSE + 界面抽样）** | 数据层：`REUSE` `docs/features/F016/test-report.md#32-c1c15-上线验收` / `#33-目标查询场景`（F016 TE-1 真 HTTP 执行，C1–C15 + Q1–Q9 数据层，`40 passed`）；界面呈现：浏览器确认 Clusters 列表、Resources 列表、Audit 查询页均经真实 API 渲染有数据（`ac9-pages.png`）。C15 为 F016 实际执行汇总（非局部拼接） |
| AC-10 | **PASS** | ClustersPage 表头与表体首行列左偏移逐列一致（`heads ['code','name','status','创建时间 ▼','更新时间','version','操作']` vs `cells [193,302,490,573,859,1144,1219]`，容差 ≤2px，`equal=true`）；F017 R-1/D-4 的 `version`/`created_at`/`updated_at` 列对齐修正确认（`clusters-columns.json`，`ac10-clusters.png`） |

### 数据库 / 接口 / 前端 / 集成结果

- **数据库**：F018 无 Schema/迁移/约束/索引变更；`alembic current`=`0013_search_indexes (head)`（无新增 head），与 `docs/database/f018-acceptance.md` `NOT_REQUIRED` 一致。无破坏性变更、无既有数据影响。
- **接口**：无新增/变更 Endpoint；浏览器全部经入口真 HTTP（`Origin=http://localhost:18080` 同源写请求，CSRF 同源口径实际生效）；错误语义 403 `FORBIDDEN`、409 `VERSION_CONFLICT{current_version}`、422 `VALIDATION_ERROR{fields}` 与契约一致。
- **前端**：`typecheck`/`build`/`smoke:client`（264/264）机制层 + 19 项真实渲染 DOM 校验全绿（`browser/browser-summary.json`：executed 19 / passed 19 / failed 0 / NOT TESTED 0）。
- **集成**：Nginx 入口 → Frontend(dist) / FastAPI → PostgreSQL 在一次真实拓扑内联调；SPA fallback、入口标记、真实 API 数据、真实错误/异常态一致。

### Cleanup 纪律执行结果

- 脚本结束（无 `F018_KEEP=1`）自动执行：`DROP DATABASE csm_f018_acc` → `docker rm -f f018-nginx f018-frontend f018-backend f018-db` → `docker network rm f018-acceptance-net` → 删除 `run-<utc>/browser-libs`。
- 断言：`docker ps -a` / `docker network ls` / `docker volume ls` 均无 `f018-*` 残留（实测输出 `none`）。`frontend/dist` 与 `scripts/acceptance/artifacts/**`（含 `browser/node_modules`）为 git-ignored 构建/测试产物；`browser-libs` 已删除。
- 本轮实际清理运行：`run-20261013T062456Z`（失败 Compose 路径先 `docker compose -p csm_f018 down -v`）。

### 未执行 / Blocked

| 项 | 状态 | 原因 / 条件 | 责任者 | 恢复动作 |
| --- | --- | --- | --- | --- |
| `docker build` / `docker compose up -d` 首选路径 | **BLOCKED（已录制，非缺陷）** | Docker Hub 不可达（token i/o timeout） | 环境 / 协调器 | 网络可达后按 `scripts/acceptance/run_f018_acceptance.sh` 首选路径复跑 |

无其他 NOT TESTED 项：AC-3..AC-10 的浏览器判据均已在真实渲染中执行并给出截图/JSON 证据。

### Defects

无。全部自动项与浏览器 DOM 项通过，未发现实现缺陷；无阻塞/必须修复问题。

**NOTE（非缺陷观察）**：编译产物中出现 Tailwind v4 内部 `@layer properties`，位于 `theme` 之前；5 个共享层（`theme→base→antd→components→utilities`）相对顺序正确且无 `legacy`，utility 覆盖 AntD 已由运行时探针验证，不影响 D04-7 语义，仅作记录。

### 项目状态一致性

本轮未修改 `docs/project/project-plan.yaml` 等状态文件，未触发 `scripts/validate_project_state.py`；`project.acceptance` 由协调器核验后写入，Tester 不写（A11/§5.5）。

### 结论

`READY FOR REVIEW`——TE-1 在真实等价部署拓扑上独立执行：Compose 失败已如实录制并切换替代栈并附差异声明；AC-1/AC-2 机制与入口项通过；AC-3..AC-10 全部在真实浏览器渲染中执行并通过（19/19），无 NOT TESTED 遗留（除环境性 Compose 首选路径 BLOCKED）；数据层 C1–C15/Q1–Q9 按 TD 以 F016 TE-1 真 HTTP 证据 REUSE。**本报告供协调器核验后写 `project.acceptance.evidence`；`COMPLETE` 由协调器写入，COMPLETE≠发布授权。**

GIT: NONE