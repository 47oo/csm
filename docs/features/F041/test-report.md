# F041 对象选择控件候选完整性（R04）— TEST REPORT

- **状态**：§1 **TEST DESIGN READY（TD-F041-1）**（历史记录，判定式已按 T1–T11 更正，见 §1.16）；§2 **TEST EXECUTION = `READY FOR REVIEW`（TE-F041-1，2026-10-29）**：I/F/S 三层与回归全部实际执行，A1–A16 全部 PASS。
- **版本**：TD-F041-1 v1（2026-10-29）+ §1.16 更正登记；TE-F041-1 v1（2026-10-29）；角色 tester；Feature F041（FEATURE / P1 / M30，`layers={database:false,backend:false,frontend:true}`、`api_required=false`、`depends_on=[F003,F004,F006]`、`blocking_decisions=[]`）
- **分支 / 基线**：`feature/F041-candidate-completeness`；`start_commit=d5c0a4c9aa5bd1036dd9acf087d210a22f43571d`；TEST 执行时 `HEAD=698f11b`（`docs(F041): ARCHITECTURE + CONTRACT signed`），F041 实现为工作树未提交改动；plan revision 25；requirements revision 16
- **Basis（均 CONFIRMED / 已批准）**：`docs/features/F041/product.md` v1（A1–A16、N1–N11、ON-1..ON-11）；`docs/product/requirements-v3.md` revision 16 §28.1 + §31 T127–T129 + §32 追加句 + §35.1 revision 16 留痕；契约基线 `docs/api/F003.md` v2 §4/§6.1（`q`=code/name ILIKE、`page_size` 1–100、`sort=code` 按 code_key、附 id 升序）、`docs/api/F004.md` v3 §4/§6.1/§2.5（`q`=hostname ILIKE、`cluster_id`/`type` 过滤、`page_size` 1–100、`sort=hostname` 按 hostname_key、宿主四条件 422 `field=virtual_machine.host_resource_id`）、`docs/api/F013.md` §1.4/§6（列表 `q` 冻结 ILIKE，不改 pg_trgm）；F027 范围语义增补节（非 ADMIN 仅授权集群，`items`/`total` 同谓词，请求体未授权引用 422）；`docs/project/implementation-rules.md`「验证与交付」；`docs/project/handoff.md`（交接/缺陷格式）；`.pi/skills/data-integrity/SKILL.md`
- **写权限说明**：本次只写本文件 §1。未修改生产实现、契约、Schema、`docs/product/**`、`docs/project/**`；未执行任何 Git 写操作；探测脚本仅落在 `/tmp`（真实数据库探测后已重置 schema，见 §1.3）。

---

## 1. TEST DESIGN

### 1.1 范围、分层与不适用项

| 项 | 判定 | 依据 |
| --- | --- | --- |
| 数据库设计 / Migration | `NOT_REQUIRED` | plan F041 `layers.database=false`、`not_required.database`；无表/列/索引/约束/Migration 变更（§1.3 P4 实测零 diff） |
| 后端实现 / 契约变更 | `NOT_REQUIRED` | `layers.backend=false`、`api_required=false`；仅复用既有列表端点与既有 `q`/分页参数（§28.1、T129、plan 硬约束①） |
| 真实前后端集成（端到端浏览器点击） | `NOT_REQUIRED`（附降级，§1.12） | AQ-4=B 明确限定「仅组件/逻辑级可重复入口，不引入浏览器依赖」；服务端语义由 I 层真实 PG 覆盖，请求构造由 F 层与真实契约对齐，二者组合替代 E2E 点击 |
| 真实浏览器视觉 / 可访问性 DOM / 手工全页巡检 | `NOT_TESTED`（声明为已知缺口） | 同上；F 层只能断言纯逻辑态与文案（§1.10），渲染层仅有 `tsc`/`build` 与代码审读 |
| 性能指标（检索时延、请求体积） | `NOT_REQUIRED` | product §3「不在验收范围：性能指标」；A3 只约束「请求次数与总量无关」，不设时延阈值 |
| 一期整体验收（§31–§33 跨功能场景） | `NOT_REQUIRED`（本 Feature） | 由 F045 变更集整体回归承接；不得用 F041 局部 PASS 拼成整体 PASS |
| 可验证层 | **I**（真实 PostgreSQL + 生产 app）、**F**（`frontend/scripts/smoke-client.mjs` 扩展，mock fetch，无 DOM）、**S**（静态/Git 零 diff） | 三层均可在仓库内重复执行；I 层需 `TEST_DATABASE_URL` 指向真实 PG；F/S 层无外部环境依赖 |

三层职责不重叠：**I 层证明服务端语义与「提交被接受」的事实**；**F 层证明前端请求形状、响应处理、状态与文案**；**S 层证明零契约/零依赖/零调用点漂移**。任何一层缺失都不能被另一层替代（尤其 A1 的「服务端接受」不得用 F 层 mock 替代，见 §1.9）。

### 1.2 输入基线与待核对项

| # | 输入 | 核对结果 |
| --- | --- | --- |
| B1 | product A1–A16 / N1–N11 / ON-1..ON-11 | 已逐条展开为 §1.4 用例；N1–N11 转为 S 层零 diff 与「调用点集合」断言（S-01..S-06） |
| B2 | §28.1 六段 CONFIRMED 条款 | 覆盖：服务端检索与分页（`q`/`page`/`page_size`）、范围与可见性（§23/§23.2/§21）、完整性判定线（第 101 位之后可检索并提交）、四态、两处控件范围、明确不做清单 |
| B3 | T127 / T128 / T129 | T127→A1–A4；T128→A5–A10；T129→A11–A14（+A15/A16 为 product 增量可观察项，同属 T128/T129 语义延伸） |
| B4 | F003 §4/§6.1、F004 §4/§6.1/§2.5 | 候选仅用 `q`/`cluster_id`/`type`/`page`/`page_size`/`sort`/`order`，无新参数；`page_size` 上限 100；`sort=hostname`→hostname_key、`sort=code`→code_key，均附 id 升序稳定；宿主四条件 422 字段固定 |
| B5 | F013 §1.4/§6 | 列表 `q` 保持 ILIKE 子串；`pg_trgm` 仅服务于 `/search`，候选不得改用（A12 → I-16 + S-06） |
| B6 | F027 范围增补节 | 非 ADMIN `items`/`total` 同谓词；未授权引用 422；`deleted=include/only` 需 VIEW_DELETED 否则 403（A6/A10 → I-12..I-14） |
| B7 | `backend/tests/conftest.py` | 真实 PG（`TEST_DATABASE_URL`，含「库名必须含 `test`」与「不得等于 `DATABASE_URL`」双守卫）；session 级重建 `public` + `alembic upgrade head`；`committed_engine` 为真实提交，teardown TRUNCATE 全表；`auth_app` 默认注入**测试专用 unrestricted AccessScope**，加 `pytestmark = pytest.mark.real_scope` 才走生产范围语义 |
| B8 | `backend/tests/integration/test_f030_test_harness.py` | 触碰 scope 符号而未标记 `real_scope` 即失败；`KNOWN_MARKED` 为**子集**校验，新增 `real_scope` 模块合规（§1.6 模块 B） |
| B9 | `frontend/scripts/smoke-client.mjs` | 既有模式：替换 `globalThis.fetch` 为受控响应、记录 `calls[]`（含 `url`/`init`）、`test()` 计数、`340 passed / 0 failed` 基线；可直接加载 `src/api/*.ts` 与**无 JSX 的纯逻辑模块**（Node ≥22.18 type stripping），**不能**加载 `.tsx` |
| B10 | `VirtualMachineFields.tsx:99` / `ResourceCreatePage.tsx:63` | 当前实现各自一次 `page_size=100` 无 `q`/无分页（缺陷事实）；`ResourceForm.tsx:281` 为 create 模式 Cluster 下拉的实际渲染点，`VirtualMachineFields.tsx:99` 为 Host 候选加载点；两者均为 `.tsx`（F 层不可直接加载 → §1.10/§1.14） |
| B11 | `ui/controls.tsx:114` | 共享 `Select`：`showSearch` + `optionFilterProp="label"`（仅过滤已加载选项）；`<Select` 调用点基线 = **60 处 / 23 个文件**（S-03/S-04 对照基线） |
| B12 | `docs/features/F041/architecture.md` | **尚未建立**（ARCHITECTURE 阶段 PENDING）→ §1.14 列出必须在 TEST 前核对的实现接缝；Final Test Design 以定稿后的 architecture 为准 |

### 1.3 环境探测（TEST_DESIGN 阶段实测，真实输出摘录）

探测日期 2026-10-29；工作目录 `/home/hanhao/github/47oo/csm`；真实 PG：`export TEST_DATABASE_URL='postgresql+psycopg://csm:csmtest@127.0.0.1:55432/csm_f037_test'`。

| # | 探测 | 命令 | 实测结果 |
| --- | --- | --- | --- |
| P1 | Node / npm | `node --version` / `npm --version` | `v22.23.3` / `10.9.9`（满足 `smoke:client` 的原生 type stripping 要求） |
| P2 | **F 层基线** | `cd frontend && npm run smoke:client 2>&1 \| tail -3` | 末行 `340 passed, 0 failed`；上一条 `PASS: F034 陈旧结果防护（T116）…`。**当前通过数基线 = 340**（写入 §1.13 规则） |
| P3 | `frontend/src` + `docs/api` + `backend` 零 diff | `git diff --stat d5c0a4c -- frontend/src docs/api backend` | **空输出，exit 0**（实现未开始，符合预期；TEST 阶段须重跑并据实记录） |
| P4 | Schema / 依赖零 diff | `git diff --stat d5c0a4c -- docs/database frontend/package.json` | 空输出（→ 数据库层 `NOT_REQUIRED` 有据；N11 无新依赖的前置状态） |
| P5 | 工作树干净 | `git status --porcelain` | 空输出 |
| P6 | 后端收集基线 | `cd backend && python3 -m pytest --collect-only -q tests/integration \| tail -2` | `SKIPPED [1] tests/integration/test_f016_acceptance.py:50: F016 acceptance module disabled (set F016_ACCEPTANCE=1)` / **`930 tests collected in 4.63s`** |
| P7 | 真实 PG 可用性 | `python3 -m pytest tests/integration/test_health.py tests/integration/test_clusters.py -q` | `24 passed in 24.60s`（session 级 schema 重建 + `alembic upgrade head` 生效；`psql` 二进制**不存在**，故以 pytest 真实连接作为连通性证据） |
| P8 | 单模块耗时分解 | `pytest tests/integration/test_health.py -q` ；`pytest tests/integration/test_clusters.py -q` | `3 passed in 3.61s`（≈ session 建立成本 3s）；`21 passed in 25.50s`（≈ 1.1s/test，主因每用例 argon2 登录） |
| P9 | **≥101 夹具耗时（探针）** | `python3 /tmp/f041_probe.py` | `alembic upgrade head: 1.16s`；**`bulk insert 150 clusters + 151 resources: 0.075s`**；`visible BARE_METAL in cluster: 150`；`rank of f41n-0100/0101/0110: [('f41n-0100', 100), ('f41n-0101', 101), ('f41n-0110', 110)]`；`page2 first/last: f41n-0101 f41n-0150 len 50`；`q=f41n-0110 matches: 1`；`cluster rank of F41C-0110 (code_key asc): 110`；末尾 `schema reset; probe done` |
| P10 | **跨层接受性（探针）** | `python3 /tmp/f041_probe_api.py` | `total 150 \| page1 has target: False \| page2 idx of target: 9`；`VM create: 201`（响应 `host.hostname=f41n-0110`，0.146s）；`cluster q search: 200 1 ['F41C-0110']`；`cluster total 150 \| page1 has target: False \| page2 idx: 9`；`resource in rank-110 cluster: 201 {'code': 'F41C-0110'}`；`VM rehost: 200`（host→`f41n-0120`）；`VM activity actions: ['CREATE','UPDATE']`（UPDATE 的 `before_data.virtual_machine.host_resource_id` = 旧 host）；**`audit rows before/after 10 candidate reads: 4 4`**；`cross-cluster host -> 422`（`field=virtual_machine.host_resource_id`）；`VM-type host -> 422`；`missing host -> 422`；`hostname unique conflict -> 409 {'reason':'unique_conflict','field':'hostname'}` |
| P11 | **§23.2 范围与错误语义（探针）** | `python3 /tmp/f041_probe_scope.py` | `soft-delete host -> 204`；`VM on soft-deleted host -> 422`（同固定 field）；`candidate q for deleted host -> 0`；`candidate q with deleted=include -> 1`；`editor clusters total/items: 3 3`（全库 120）；`editor cluster q F41C-0010 (unauthorized) -> 0`；**`editor resources total/items: 119 100`**；`editor write unauthorized cluster -> 422`（`field=cluster, message=cluster does not exist or is not selectable`）；`editor deleted=include -> 403`（resources/clusters 同）；`viewer POST resource -> 403 {'reason':'permission'}`；`viewer 404 detail -> 404`；`anon list -> 401`；`admin page_size=101 -> 422`；`admin page_size=100 -> 100`；`admin sort=code asc page2 first -> F41C-0101` |
| P12 | 前端类型基线 | `cd frontend && npx tsc --noEmit` | 无输出（通过），10.1s |
| P13 | 静态基线 | `grep -rn "<Select" src --include=*.tsx \| wc -l`；`wc -l scripts/smoke-client.mjs` | `<Select` **60** 处 / **23** 个文件；`smoke-client.mjs` **9210** 行 |
| P14 | F016 真实栈（可选集成入口） | `curl -s -m 3 -o /dev/null -w "%{http_code}" http://127.0.0.1:18080/api/v1/health` | `000`（**不可达**）→ 该入口本环境不可用，`F016_ACCEPTANCE=1` 路径按 §1.12 记为 `NOT_TESTED`（不作为 A1 证据） |

**探测写操作说明（如实记录）**：P9–P11 的探针为 `/tmp` 下一次性脚本（非仓库文件），对**专用测试库** `csm_f037_test` 执行了 schema 重建、`alembic upgrade head`、批量夹具插入与探针写入；每个探针结束时执行 `DROP SCHEMA public CASCADE; CREATE SCHEMA public` 复位，且 `tests/conftest.py` 在 session 起止各重建一次 `public`。未触碰任何非测试数据库；未在仓库内留下文件。

### 1.4 验收映射总表（A1–A16 → 用例）

| 验收 | 用例 ID | 层 | 一句话判定 |
| --- | --- | --- | --- |
| A1 | I-01, I-02, I-03, I-04, I-05, I-06, I-07；F-11 | I（事实）/ F（载荷） | ≥101 对象下：名次 ≥101 的目标按既有排序不在第 1 页、可被 `q` 检索命中；提交后**服务端 201 接受**且落库引用为该对象（VM `host_resource_id` / Resource `cluster_id`），换 Host 记 UPDATE 审计 |
| A2 | I-08, I-09；F-01, F-02, F-03 | I / F | 候选查询携带 `page`/`page_size`，任一请求 `page_size ≤ 100`，任一响应 `items.length ≤ 100`；服务端 `page_size=101 → 422` |
| A3 | F-03；S-02 | F / S | 单次交互候选请求数 = 1（输入即检索），total=154 与 total=1540 同次数；`page` 恒为 1、不循环抓取；无 `page_size>100` |
| A4 | I-09；F-04, F-05 | I / F | 候选项仅来自最近一次响应：服务端只返回 N 条时无第 N+1 条历史条目；输入变化后旧结果不残留；陈旧响应被序号门控丢弃 |
| A5 | I-10, I-11；F-01, F-02 | I / F | 软删对象不在候选且检索不到（默认 `deleted=exclude`）；候选请求**不含** `include`/`only`；软删 Host 提交 422 |
| A6 | I-12, I-13, I-15；F-09 | I / F | 非 ADMIN 候选 `total` 只计授权集群（全库 120 / 授权 3 → `total=3`）；未授权 `q` 命中 0；写未授权 Cluster → 422；超限提示总数取响应 `total`（3），不含全库规模 |
| A7 | F-06；S-04 | F / S | 四态（loading/error/idle/empty）`kind` 与文案两两不同；error 文案不落入「无匹配/暂无数据」；各态语义 `role` 互异；idle 仅在 VM 未选集群可达 |
| A8 | F-07 | F | 失败显示错误 + 可重试标志；失败不自动重试（fetch 次数不增）；触发重试恰好再发 1 次；重试成功恢复候选；失败态不被渲染为空 |
| A9 | I-15；F-08 | I / F | `total > items.length` 时提示文本含**总数**与**分页边界**（100）；`total == items.length` 或 `total == 0` 时不提示；不静默截断 |
| A10 | I-11, I-13, I-14；F-12 | I / F | 绕过候选直提交：未授权 Cluster 422 / 跨 Cluster Host 422 / 软删 Host 422 / VM 类型 Host 422 / 不存在 Host 422 / hostname 唯一 409 / 缺权限 403 / 匿名 401 / 不存在对象 404；前端沿用既有 `describe*ActionError`，候选态不被提交错误吞并 |
| A11 | S-01, S-02, S-05, S-06 | S | `docs/api`、`docs/product`、`docs/database`、`backend`、`frontend/package.json(+lock)` 相对 `d5c0a4c` 零 diff；`api/*.ts` 端点与查询参数集合不变 |
| A12 | I-16；S-06 | I / S | `q` 仍 ILIKE 子串（大小写不敏感、中段子串命中）；候选命中集合与同参数列表页 `total` 一致；后端零 diff（未引入 pg_trgm 变化） |
| A13 | S-03, S-04 | S | 共享 `Select` 既有调用点逐处未变（`d5c0a4c` 60 处/23 文件 → 定稿 58 处/22 文件，仅两个 F041 载体减少，T3）；新行为仅由新组件或 opt-in props 承载；新组件未被用于其他控件 |
| A14 | I-07, I-18；S-07 | I / S | T01/T02、T08/T09、T19、T37 及既有创建/编辑/列表流程无回归：既有 `test_resources.py`/`test_clusters.py` 全通过 + `npm run build` 通过 + 既有 340 条 smoke 用例全通过 |
| A15 | I-17 | I | 候选读取前后 `audit_logs` 计数不变（本轮探针实测 4 → 4），不产生 Audit/Activity |
| A16 | F-10；I-07 | F / I | 编辑态当前 Host 不在当前页时仍呈现为可选项且不重复；可直接提交或改选；改选后服务端记录 UPDATE 审计（before/after host） |

### 1.5 ≥101 夹具设计（ON-3）

**规模与理由**：取 **150** 个 Cluster + **150** 个同 Cluster `BARE_METAL` Host（+2 个辅助对象），不是 101。理由：① 需两个不同名次的目标（名次 110 用于「检索→提交」，名次 120 用于「换 Host」）且都远离边界，避免 off-by-one 争议；② `page=2`（ranks 101–150）需要足够行数验证窗口；③ A2 需要「可见对象 > 单页上限」的稳定状态。实测成本 ≈ **0.075s**（P9），150 与 101 无成本差异。

**方案：真实 PostgreSQL 一条 `INSERT ... SELECT generate_series`**（沿用 `test_search_constraints.py` / `test_ip_address_constraints.py` 既有模式），不走 300 次 API 调用：

```sql
-- 1) Cluster：150 条，code = F41C-0001..F41C-0150（code_key 由 ASCII 折叠口径同值）
INSERT INTO clusters (code, code_key, name)
SELECT 'F41C-' || lpad(g::text, 4, '0'),
       'F41C-' || lpad(g::text, 4, '0'),
       'F041 bulk cluster ' || g
FROM generate_series(1, 150) AS g;

-- 2) Host：150 条 BARE_METAL，同 Cluster（hostname = hostname_key = f41n-0001..f41n-0150）
INSERT INTO resources (cluster_id, hostname, hostname_key, resource_type)
SELECT (SELECT id FROM clusters WHERE code = 'F41C-0001'),
       'f41n-' || lpad(g::text, 4, '0'),
       'f41n-' || lpad(g::text, 4, '0'),
       'BARE_METAL'
FROM generate_series(1, 150) AS g;
```

**辅助对象（A5/A10 需要，走 API 以便留审计基线）**：

| 对象 | 构造 | 用途 |
| --- | --- | --- |
| 软删 BARE_METAL `f41del-0001` | API 创建后 `DELETE ...?version=1`（204） | A5：默认候选 `q=f41del` → `total=0`；`deleted=include`（ADMIN）→ `total=1` |
| VM 类型资源 `f41vm-0001` | API `POST /resources`（`VIRTUAL_MACHINE`，host=`f41n-0001`） | A10：将其作为 host 引用 → 422 |
| 独立 Cluster `F41C-OTHER` | API 创建 | A10：跨 Cluster Host → 422；A1 提交目标 Cluster 用于创建 BARE_METAL |

**可重复性 / 清理 / 排序稳定 / 名次判定**：

| 维度 | 设计 |
| --- | --- |
| 可重复 | 名称确定性（不掺随机后缀，避免名次漂移）；每次 TEST 会话由 `conftest.py` 重建 `public` + `alembic upgrade head`；SQL 插入幂等前提 = 表空（`committed_engine` teardown 已 `TRUNCATE` 全部非 `alembic_version` 表），故**每个用例自建自清**，重跑无残留 |
| 清理 | 依赖 `committed_engine` fixture 的 teardown TRUNCATE（既有机制，不新增清理代码）；session 结束 `public` 重建 |
| 排序稳定 | Host 用 `sort=hostname&order=asc`（Contract §4：hostname_key 排序 + id 升序稳定；`f41n-0001..f41n-0150` 互不相同）；Cluster 用 `sort=code&order=asc`（code_key + id 升序稳定）。禁止用 `created_at`（同刻批量插入无序）作为名次依据 |
| **名次判定（不硬编码 id）** | 辅助函数 `rank_by_server_order(client, path, params, target_id)`：以 `page_size=100` 逐页请求**既有列表端点**，按返回顺序累计偏移，返回目标 1-based 名次（找不到返回 `None`）。断言 `rank is not None and rank >= 101`，并断言 `page=1&page_size=100` 的 `items` **不含**该 id（等价于「不在单页上限内」）。目标 id 本身由服务端发现：`q=<唯一子串>` → `items[0].id`；名次与 id 双向均不写死 |
| 交叉核对（可选） | SQL `row_number() OVER (ORDER BY hostname_key ASC, id ASC)` 与 API 名次一致（P9 实测均为 110），用于确认测试助手未误算；不作为主要判定 |

**实测校准值**（P9/P10，仅作参照，不写死进断言）：目标 Host `f41n-0110` 名次 110、`f41n-0120` 名次 120；Cluster `F41C-0110` 名次 110；`page=2` 窗口首/末 = `f41n-0101`/`f41n-0150`（50 条）。

### 1.6 I 层用例（真实 PostgreSQL + 生产 app；后端 pytest 断言端点行为）

新增三个**测试专用**文件（不触碰生产实现）：`backend/tests/integration/f041_helpers.py`（夹具 + `rank_by_server_order` + 计数助手）、`backend/tests/integration/test_f041_candidate_completeness.py`（模块 A：**不**声明 `real_scope`，沿用 legacy unrestricted 范围，只用于非范围语义）、`backend/tests/integration/test_f041_candidate_scope.py`（模块 B：`pytestmark = pytest.mark.real_scope`，走生产 §23.2 语义）。**T4 更正**：`backend` 零 diff 判定收窄为「生产代码/配置零 diff」，`git status --porcelain -- backend` 仅允许 `?? backend/tests/integration/f041_*.py`（DR-F041-09）。

公共前置：`auth_app`（仅覆盖 `get_db`，真实 PG）、`role_client_factory`（ADMIN / EDITOR / VIEWER 各自真实登录）、`committed_engine`（批量夹具）、`auth_session_factory`（DB 侧落库核对与计数）。

| ID | 验收 | 前置夹具 | 步骤 | 判定表达式（断言） | 证据落点 |
| --- | --- | --- | --- | --- | --- |
| **I-01** | A1 | ADMIN；150 Hosts | ① `GET /resources?cluster_id=<C1>&type=BARE_METAL&q=f41n-0110&page=1&page_size=100&sort=hostname&order=asc` 取目标 id；② `page=1`（同上无 `q`）看是否含目标；③ `rank_by_server_order(...)` | `found.status==200 and found.json()["total"]>=1 and found.json()["items"][0]["id"]==target_id`；`target_id not in [i["id"] for i in page1["items"]]`；`rank is not None and rank>=101` | `docs/features/F041/artifacts/pytest-f041.log`（TEST 阶段落盘）+ 本文件 §2 |
| **I-02** | A1 | ADMIN；150 Clusters | 同 I-01，域改为 clusters（`q=F41C-0110`、`sort=code&order=asc`） | `cluster_found.json()["total"]==1 and items[0]["id"]==target_cluster_id`；`target_cluster_id not in page1.items`；`rank>=101` | 同上 |
| **I-03** | A1/A2 | ADMIN | 在 I-01 的响应上补充边界断言 | `len(found.json()["items"])<=100`；`found.json()["page_size"]==100`；`found.json()["page"]==1` | 同上 |
| **I-04** | A2 | ADMIN | `GET /resources?page_size=101`；`GET /clusters?page_size=101`；各取 `page_size=100` 的成功响应 | 两个越界请求 `status==422` 且 `error.code=="VALIDATION_ERROR"`；成功响应 `page_size==100 and len(items)<=100`（总 >100 时 `len(items)==100`） | 同上 |
| **I-05** | **A1（关键）** | ADMIN + 150 Clusters | `POST /resources {"cluster":"F41C-0110","hostname":"f41-target-cluster-host","resource_type":"BARE_METAL"}`；随后 `GET /resources/{id}`；再用 `auth_session_factory` 查 `resources.cluster_id` | `status==201`；`resp["resource"]["cluster"]["id"]==target_cluster_id`；详情 `cluster.id` 同；**DB `resources.cluster_id == target_cluster_id`** | 同上 + §1.9 |
| **I-06** | **A1（关键）** | ADMIN + 150 Hosts | `POST /resources {"cluster":"F41C-0001","hostname":"f41-vm-1","resource_type":"VIRTUAL_MACHINE","virtual_machine":{"host_resource_id":<rank110 host id>}}`；`GET` 详情；DB 查 `virtual_machine_details.host_resource_id` | `status==201`；`resp["resource"]["virtual_machine"]["host_resource_id"]==rank110_host_id`；`resp["resource"]["virtual_machine"]["host"]["hostname"]=="f41n-0110"`；**DB `virtual_machine_details.host_resource_id == rank110_host_id`** | 同上 + §1.9 |
| **I-07** | A1/A16/A14(T19) | I-06 的 VM | `PATCH /resources/{vm} {"version":1,"virtual_machine":{"host_resource_id":<rank120 host id>}}`；`GET /resources/{vm}/activity` | `status==200`；`virtual_machine.host_resource_id==rank120_id`；activity `["CREATE","UPDATE"]`；UPDATE 行 `after_data["virtual_machine"]["host_resource_id"]==rank120_id` 且 `before_data[...]==rank110_id` | 同上 |
| **I-08** | A2/A4 | ADMIN + 150 Hosts | 在 I-01 的两个查询上取响应 | 两域 `len(items)<=100`；Host 域成功响应 `len(items)==100 and total==150`（含辅助对象时为 `total>=150`，以夹具实测值为准并记录） | 同上 |
| **I-09** | A5 | ADMIN + 软删 Host | ① `q=f41del`（默认）② `q=f41del&deleted=include` ③ 无 `q` 的候选查询 | ① `total==0 and items==[]`；② `total==1`（ADMIN 具 VIEW_DELETED）；③ 结果与 `deleted=exclude` 等价（默认不泄露已删） | 同上 |
| **I-10** | A5/A10 | ADMIN + 软删 Host | `POST /resources` 建 VM，`host_resource_id` = 软删 Host | `status==422`；`error.details.fields[0].field=="virtual_machine.host_resource_id"` | 同上 |
| **I-11** | A6 | **模块 B**：120 Clusters + 120 Hosts（同 C1）；EDITOR 授予 C1..C3 | ① EDITOR `GET /clusters?page=1&page_size=100&sort=code&order=asc` ② `q=F41C-0010`（未授权） ③ EDITOR `GET /resources?type=BARE_METAL&page_size=100` | ① `total==3 and len(items)==3`；② `total==0 and items==[]`；③ `total==119 and len(items)==100`（只计可见对象，且体现 `total>items.length`） | 同上 |
| **I-12** | A6/A10 | 模块 B：EDITOR | `POST /resources {"cluster":"F41C-0010", ...}` | `status==422`；`details.fields[0].field=="cluster"`（不返回 403/404，不泄露存在性） | 同上 |
| **I-13** | A10 | ADMIN / EDITOR / VIEWER / 匿名 | 逐项：匿名 `GET /resources`；EDITOR `deleted=include`（resources 与 clusters）；VIEWER `POST /resources`；`GET /clusters/<随机UUID>` | `401` / `403 FORBIDDEN{reason:"permission"}` ×2 / `403 FORBIDDEN{reason:"permission"}` / `404 NOT_FOUND` | 同上 |
| **I-14** | A10 | ADMIN + 全夹具 | 五类非法 host 引用：跨 Cluster Host、VM 类型资源、不存在 UUID、软删 Host、以及 hostname 唯一冲突 | 前四类 `422`（`field=virtual_machine.host_resource_id`）；hostname 冲突 `409 CONFLICT{reason:"unique_conflict",field:"hostname"}` | 同上 |
| **I-15** | A9/A2 | ADMIN + 全夹具 / 模块 B | 断言 `total` 与 `items.length` 关系：Host 域 `total(>=150) > 100 == len(items)`；模块 B `total==119 > len(items)==100` | `total > len(items) == page_size` 成立（= 前端超限提示的数据前提）；`total==len(items)` 情形（授权 3 个 Cluster）不产生超限语义 | 同上 |
| **I-16** | A12 | ADMIN + 150 Hosts | ① `q=f41n-0110` ② `q=F41N-0110` ③ `q=n-0110`（中段子串） ④ 同参数列表页（无 `q`）`total` 对照 | ①②③ 均 `total==1` 且 `items[0].id` 相同（ILIKE 大小写不敏感 + 子串）；`q=n-01` `total>=10`（子串命中多条）；候选查询与列表页在同一参数组合下 `total` 相同 | 同上 |
| **I-17** | A15 | ADMIN + 全夹具 | 连续 10 次候选读取（两域各 5 次，含 `q`）前后统计 `SELECT count(*) FROM audit_logs` | `before == after`（本轮探针 P10 实测 4→4，作为机制佐证） | 同上 |
| **I-18** | A14 | 无 F041 夹具 | `python3 -m pytest tests/integration/test_resources.py tests/integration/test_clusters.py tests/integration/test_interfaces.py -q`（回归复用，不改动用例） | 全通过、无新增 skip；收集数与 `d5c0a4c` 基线一致 | `artifacts/pytest-regression-f041.log` |

**I 层判定口径要点**（避免断言落空）：

- 一律用 `page_size=100` 的**既有**列表端点做候选语义验证，不新增任何端点/参数（S-01/S-02 另行证明）。
- 所有「名次 ≥101」判定走 `rank_by_server_order`，**不**用 `created_at`、**不**硬编码 UUID。
- 提交接受性同时校验三层证据：HTTP `201`、响应字段、**DB 行**（`resources.cluster_id` / `virtual_machine_details.host_resource_id`），避免只信响应体。
- 模块 B 必须带 `pytestmark = pytest.mark.real_scope`（否则 `test_f030_test_harness.py` 会判违规，且断言会落在 legacy unrestricted shim 上而失真）。模块 A 用 legacy shim 时不得对 §23.2 范围下结论。

### 1.7 F 层用例（`frontend/scripts/smoke-client.mjs` 扩展；mock fetch，无 DOM/浏览器）

**运行方式**：沿用既有模式——`globalThis.fetch` 替换为受控响应，`calls[]` 记录 `{url, init}`，`test(name, fn)` 计数；`npm run smoke:client` 的末行 `N passed, M failed` 与 exit code 0 为门禁。新增用例只**追加**，不改动既有 340 条。

**可加载性前提**：`.tsx` 无法被 Node type stripping 加载，因此 F 层断言对象必须是**无 JSX 的纯逻辑模块**（既有先例：`hardware.ts`、`virtualMachine.ts`、`authorizationCandidates.ts`、`interfaceIpSelection.ts`、`resourceIpAddresses.ts`）+ 既有 `src/api/{resources,clusters}.ts`（已验证可在 Node 加载）。该模块的必需导出面见 §1.14（提交前必须与 `architecture.md` 定稿核对；用例 ID 不变，仅导入名/形参名按其定义替换）。

| ID | 验收 | 前置（mock 响应/输入） | 步骤 | 判定表达式（断言） | 证据落点 |
| --- | --- | --- | --- | --- | --- |
| **F-01** | A2/A5（Host 域） | `respond` 返回 `{items:[...100],page:1,page_size:100,total:154}` | 用候选查询构造器生成 Host 域查询（`clusterId="c-1"`, `q="f41n-0110"`）→ 取 `buildCandidateQuery(...).query`（T6）→ 经 `listResources` 发送 | URL 路径 `/api/v1/resources`；`searchParams.get("cluster_id")=="c-1"`；`type=="BARE_METAL"`；`page=="1"`；`page_size=="100"`；`sort=="hostname"`；`order=="asc"`；`q=="f41n-0110"`；**参数名集合精确等于** `{cluster_id,type,q,page,page_size,sort,order}`（无多余键）；`!/[?&](include|only)(=|&|$)/.test(url)` 且 `!url.includes("deleted=include") && !url.includes("deleted=only")` | `docs/features/F041/artifacts/frontend-smoke.log` + §2 |
| **F-02** | A2/A5（Cluster 域） | 同上（clusters 响应） | 生成 Cluster 域查询（`.query`，T6）→ 经 `listClusters` 发送 | `/api/v1/clusters`；`page=="1"`；`page_size=="100"`；`sort=="code"`；`order=="asc"`；有 `q`；参数名集合精确等于 `{q,page,page_size,sort,order}`；无 `deleted=include|only`、无 `include`/`only` 键 | 同上 |
| **F-03** | A2/A3 | 两轮独立运行：`total=154` 与 `total=1540`（均返回 100 条 items） | 每轮清空 `calls` 后驱动**一次**输入检索 | ① 每轮 `calls.length == 1`（输入即检索，无「加载更多」循环）；② `calls.length(154) === calls.length(1540)`（次数与总量无关）；③ 每次 `Number(searchParams.get("page_size")) <= 100` 且 `page == "1"`；④ 不存在 `ceil(total/100)` 量级的请求序列 | 同上 |
| **F-04** | A4 | 第 1 次输入响应 `{items:[3 条], total:154}`；第 2 次输入响应 `{items:[2 条], total:154}` | 依次驱动两次检索，检查候选集合 | 第 1 次后 `candidates.length === 3`（**不出现**第 4 条历史/占位条目）；第 2 次后 `candidates.length === 2` 且集合恰等于第 2 次响应 id 集（无并集、无残留） | 同上 |
| **F-05** | A4/ON-7 | 两次输入；先发请求的响应**后**返回（受控 promise 顺序倒置） | 交错 resolve：`req1.resolve(旧结果)` 晚于 `req2.resolve(新结果)` | 最终候选 = 新结果 id 集；旧响应被序号/epoch 门控丢弃（`candidates` 不含旧 id）；`state.kind==="success"` 且 `total` 取新响应值 | 同上 |
| **F-06** | A7 | 构造四态输入：`idle`（`clusterId===""`）、`loading`（未 resolve）、`error`（reject/500）、`empty`（`{items:[],total:0}`） | 取各态视图（`kind` + 文案 + 语义 `role`/`canRetry` 标志） | 四个 `kind` 互不相同；四段文案两两不相等（`new Set(texts).size===4`，且每段非空）；`errorView.canRetry===true` 且 `errorView.role!=="note"`；**error 文案不含** `"无匹配"` 与 `"暂无数据"`；`emptyView` 文案 ≠ `errorView` 文案 ≠ `idleView` 文案；`idle` 仅在 `clusterId===""` 时可达（`clusterId` 非空时最小态为 `loading`） | 同上 |
| **F-07** | A8 | 第一次 `respond` 返回 500 `{error:{code:"INTERNAL_ERROR",...}}`；重试后返回正常 items | 触发检索 → 断言失败态 → **不触发重试**等待一拍 → 触发重试 | 失败后：`view.kind==="error"`、`view.canRetry===true`、文案非空；**失败后未自动重试**：`calls.length===1`；触发重试后 `calls.length===2`（恰 +1）；重试成功：`state.kind==="success"` **且** `candidateView(state,"host").kind==="ready"`（T2/T9；视图投影无 `success` 值）且 `candidates` 恢复为响应 items；全程 `view.kind` 从未为 `empty` | 同上 |
| **F-08** | A9/ON-11 | 三组：`{total:154,items:100}`、`{total:3,items:3}`、`{total:0,items:0}` | 取超限提示视图 | 组 1：`truncated===true`，文案同时命中 `/154/` **与** `/100/`（总数 + 分页边界）且文案含「分页/边界」语义词（`/(分页|上限|前)/`）；组 2、组 3：`truncated===false` 且无提示文案（`null`/空串） | 同上 |
| **F-09** | A6（F 侧）/A9 | `{total:3,items:3}`（模拟全库 120、授权 3）与 `{total:3,items:1}` | 取提示视图 | 前者无超限提示；后者文案含 `"3"`（响应 total）且**不含** `"120"`（不得用全库规模）；文案不出现「全部」「共 120」等未授权规模信息 | 同上 |
| **F-10** | A16 | 编辑态：`currentHost={id:"pinned-1",hostname:"f41n-0110"}`；响应 items 不含该 id；再构造响应包含该 id | 取选项集合；并断言提交载荷构造 | 不含时：选项含 pinned 恰好 1 次（label 含 hostname，`value==="pinned-1"`）；含时：**不重复**（`options.filter(o=>o.value==="pinned-1").length===1`）；`buildVirtualMachineCreateInput`/`updateResource` 载荷 `virtual_machine.host_resource_id==="pinned-1"`；改选后载荷为**新** id | 同上 |
| **F-11** | **A1（载荷侧）** | `respond` 返回 201 `{resource:{id:"vm-1",virtual_machine:{host_resource_id:"late-110"}}}` | 模拟「选中名次 ≥101 的对象」→ 生成提交载荷 → `createResource`；另模拟 Cluster 选择 → `createResource({cluster:<目标 id>})` | VM 提交 `JSON.parse(calls[0].init.body).virtual_machine.host_resource_id === "late-110"`；Cluster 提交 `body.cluster === "<目标 cluster id>"`（**传 id，不退化为 code/序号**）；`calls.length===1`（不重试）。**该用例只证明载荷传递，不证明服务端接受**（见 §1.9） | 同上 |
| **F-12** | A10（F 侧） | 候选成功后，提交返回 422 `{details:{fields:[{field:"virtual_machine.host_resource_id",...}]}}` / 409 / 403 / 404 | 提交失败后检查候选态与错误呈现 | 候选态仍为 `success` 且 `candidates` 未被清空或改成 `empty`；错误经既有 `describeResourceActionError` 呈现（`fields["virtual_machine.host_resource_id"]` 非空 / `versionConflict` 语义不变）；`calls.length===1`（不自动重试） | 同上 |

**F 层不做什么**（边界声明）：不渲染 React 组件、不读 DOM、不断言 Ant Design 行为、不引入 Playwright/Vitest/jsdom（AQ-4=B、N11）。渲染层等价性由 S-03/S-04 的零 diff 与代码审读承载，并在 §1.12 明确列为未验证项。

### 1.8 S 层用例（静态 / Git 零 diff / 调用点集合）

| ID | 验收 | 命令（相对 `d5c0a4c`） | 判定表达式 |
| --- | --- | --- | --- |
| **S-01** | A11/N9 | `git diff --stat d5c0a4c -- docs/api docs/product docs/database backend` | 空输出（exit 0）。**TEST 阶段必须重跑**；若前端实现顺带改了上述任一目录 → 直接 FAIL（N9） |
| **S-02** | A11/N1 | `git diff d5c0a4c -- frontend/src/api` + `grep -rn "/api/v1/" frontend/src/api \| sort` | 端点字符串集合不变；`ListResourcesQuery`/`ListClustersQuery` 无新增键（`q`/`cluster_id`/`type`/`page`/`page_size`/`sort`/`order` 均为既有）。若 `api/*.ts` 出现 diff，则须逐行说明「仅类型注释/无 wire 变更」，否则 FAIL |
| **S-03** | A13/N5 | `git diff --stat d5c0a4c -- frontend/src/components/ui/controls.tsx`；`grep -rn "<Select" frontend/src --include=*.tsx \| wc -l` | **方案 A（定稿：新增 `CandidateSelect`，T5）**：`controls.tsx` diff 为空；`<Select` 计数基线由 **60 处 / 23 文件 → 58 处 / 22 文件**（T3：两个 F041 载体按 §1.1/§1.4 必须改为 `<CandidateSelect`，`grep "<Select"` 不匹配它，故必然 60−2 / 23−1），实质判定改为**逐文件对照**：除两个载体外其余文件 `<Select` 计数逐处不变。**方案 B（给 `Select` 加 opt-in props）**：允许 `controls.tsx` 出现 diff，但①60 处既有 `<Select` 调用点（23 个文件，P13 基线）除两处 F041 载体外逐处未变（`git diff` 中 `+`/`-` 行不得落在其它文件的 `<Select` 块）；②新 props 缺省时行为与 `d5c0a4c` 等价（审读 `optionFilterProp`/`showSearch`/`onChange` 三处未改）。两方案都不允许改变既有调用的默认语义 |
| **S-04** | A13/N5/N6/ON-10 | `grep -rn "CandidateSelect" frontend/src`（T5：定稿组件名） | 引用点集合 ⊆ {`components/CandidateSelect.tsx`（定义）, `VirtualMachineFields.tsx`, `ResourceForm.tsx`, `ResourceCreatePage.tsx`（**仅文档注释**，非渲染/导入）}；**不得**出现在 `IpAddressesPage.tsx`/`IpAddressForm.tsx`/§13.4 IP 候选链（`interfaceIpSelection.ts` 调用方）、`ResourcesPage.tsx` 等列表筛选、`GlobalSearch.tsx`、其余 `*Form.tsx` |
| **S-05** | A11/N11 | `git diff --stat d5c0a4c -- frontend/package.json frontend/package-lock.json`；`grep -n "debounce\|downshift\|react-select\|vitest\|jsdom\|playwright" frontend/package.json` | 两文件零 diff；无新依赖、无新 devDependency、无新 `scripts`（`smoke:client` 保持唯一前端测试入口） |
| **S-06** | A12/N3 | `git diff --stat d5c0a4c -- backend` | 空输出 → 未改 `q` 匹配实现、未引入 pg_trgm 变化（行为侧另由 I-16 断言） |
| **S-07** | A14/N11 | `cd frontend && npm run build`（= `tsc --noEmit` + `vite build`） | 退出码 0；无类型错误。chunk 体积警告按 F040 结论不计缺陷 |
| **S-08** | 状态一致性 | `python3 scripts/validate_project_state.py --feature F041`（只读；若协调器改了 `project-plan.yaml` 另按 `docs/project/project-state.md` 追加 `--previous` 快照校验） | 结构校验通过（**不代表**批准来源、Git SHA、报告内容或测试结果真实性） |

### 1.9 A1 的关键判定：如何证明「检索到第 101 位之后的对象并**提交被服务端接受**」

A1 是全 Feature 的核心事实，必须由**真实服务端**证明；mock 只能证明载荷，不能证明接受。承载方式如下（三段互补，缺一不可）：

| 段 | 承担的命题 | 用例 | 证据形式 |
| --- | --- | --- | --- |
| ① 名次真实存在且超出单页 | 「按既有排序，目标稳定位于 ≥101 位」 | I-01（Host）、I-02（Cluster） | 真实 PG + 生产 app：`page=1&page_size=100` 不含目标；`rank_by_server_order` 返回 ≥101；SQL `row_number()` 交叉核对（P9 实测 110） |
| ② 可被输入检索 | 「`q` 使目标进入单页（≤100）」 | I-01/I-02 的 `q` 检索分支 + I-16（ILIKE 语义不变） | 真实 app：`total>=1`、`items[0].id == target_id`、`items.length<=100` |
| ③ **提交被服务端接受** | 「选中该对象后，服务端按既有规则接受并落库」 | **I-05**（Resource→名次 110 的 Cluster）、**I-06**（VM→名次 110 的 Host）、I-07（换 Host 到名次 120 并记审计） | 三重证据：HTTP `201` + 响应字段指向该对象 + **DB 行核对**（`resources.cluster_id` / `virtual_machine_details.host_resource_id`）+ Activity 审计（T19） |
| ④ 前端只是把用户选择传到线上 | 「选中 → 载荷携带所选 id（不退化为 code/序号/首页项）」 | **F-11**（mock fetch 断言提交 body） | 仅 wire 证据；**明确不作为接受性证明** |

**禁止的替代做法（写死为 TEST 阶段红线）**：
1. 不得以 F 层 mock 的 201 响应替代 I-05/I-06（mock 的 201 是自造事实）。
2. 不得只断言「候选项里出现了目标」而不提交（那只是 ①②，不含 ③）。
3. 不得用「先 API 创建 101 个对象再逐条断言」以外的抽样式验证；必须按名次判定，禁止 `items[0]`/固定 UUID 硬编码。
4. 不得在已授权集群之外验证 A6；也不得用 legacy unrestricted 模块对 `total` 只计可见对象下结论（必须模块 B + `real_scope`）。
5. 不得用 `psql`/直接 SQL 断言替代端点行为断言（SQL 仅作交叉核对与 DB 落库核对）。

### 1.10 无浏览器条件下如何断言四态与提示文案（AQ-4=B）

| 观察对象 | 无 DOM 的承载方式 | 断言形态 |
| --- | --- | --- |
| 四态（loading/error/idle/empty） | 候选状态机 + 视图投影纯函数（`kind` / 文案 / `canRetry` / 语义 `role`）；与 F030 `authorizationCandidates.ts` 同构先例 | 纯函数返回值断言：`kind` 四值互异、文案四段两两不等、`error.canRetry===true`、`error` 文案不含「无匹配/暂无数据」、`idle` 仅由 `clusterId===""` 产生（F-06） |
| 失败可重试、不自动重试 | 受控 `fetch` 计数器 + 状态机 | `error` 后 `calls.length` 不变；重试 +1；重试成功回到 `success`（F-07） |
| 超限提示（总数 + 分页边界） | 提示投影纯函数（输入 = `{total, items.length, page_size}`） | 文案字符串断言含总数与 `100`；`total<=items.length` 时无提示（F-08）；total 取响应值（F-09） |
| 「旧结果不残留」/竞态 | 状态机 epoch/请求序号门控 | 倒置 resolve 后候选集合只含最新响应 id（F-05）；响应条数减少后集合随之减少（F-04） |
| 编辑态当前 Host 回填 | 选项合成纯函数（items + pinned） | pinned 恰出现一次、无重复；载荷用其 id（F-10） |
| 请求参数正确性（`q`/`page_size`/`cluster_id`/`type`，无 `include`/`only`） | 查询构造器 + 既有 `listResources`/`listClusters` 序列化（真实代码路径） | URL 字符串/`URLSearchParams` 精确断言（F-01/F-02/F-03） |
| 真实 DOM 上的 role/aria、Ant Select 下拉渲染、键盘可达、debounce 实际时延 | **无浏览器依赖下不可断言** | 降级为 `tsc`/`build` + 代码审读；在 §1.12 记为 `NOT_TESTED`，不计 PASS |

**可验证性要求（对 Architect 的接缝要求，属测试质量而非产品规则）**：上述「状态机 / 提示投影 / 选项合成 / 查询构造 / epoch 门控」必须落在**无 JSX、无 React、无 antd 依赖**的纯逻辑模块中（`.tsx` 无法被 `node` type stripping 加载）。若最终实现把这些逻辑内嵌在 `.tsx` 组件内，则 A4/A7/A9/A16 在 AQ-4=B 下**没有可执行证据**，TEST 阶段只能判 `TEST BLOCKED`，不得降级为「只跑 I/S 层并写 PASS」。

### 1.11 数据完整性对应表（引用 `implementation-rules.md` / `data-integrity` Skill）

本 Feature **无 Schema / Migration 变更**，下表只登记「被触及但不得改变」的既有保证与验证落点：

| 规则依据及版本 | 作用域/写入入口 | 数据库保证（现状，不变） | 业务层保证（现状，不变） | 并发/生命周期边界 | 验证与证据（本次） |
| --- | --- | --- | --- | --- | --- |
| §9 / T01 / T02（同 Cluster hostname 唯一，contract F004 §7） | `POST/PATCH /resources` | 部分唯一索引 `uq_resources_cluster_id_hostname_key`（`deleted_at IS NULL`） | 服务端 409 `unique_conflict{field:"hostname"}` | 软删后 hostname 可复用 | I-14（409 断言）、I-18（F004 回归）；**D 层 NOT_REQUIRED**（无 Schema 变更） |
| §9 / T08 / T09（VM Host 必须同 Cluster、未软删、`BARE_METAL`） | `POST/PATCH /resources`（`virtual_machine.host_resource_id`） | FK + 触发器不变；类型/所属域由业务层保证 | 四条件统一 422 `field=virtual_machine.host_resource_id`；Host 写路径 `FOR UPDATE`（DR-71） | 宿主软删后详情仍展开；恢复重检 | I-06（接受）、I-10/I-14（五类拒绝：软删/跨 Cluster/VM 类型/不存在/越权）；P11 探针已实证 |
| §21（软删默认排除、不泄露存在性） | 候选读取（`GET /resources`、`GET /clusters`） | `deleted_at` 谓词 | 默认 `exclude`；`include/only` 需 VIEW_DELETED（403） | 恢复/软删不级联 | I-09、I-11、I-13 |
| §23 / §23.2（角色矩阵与集群范围） | 候选读取 + 提交 | 无新增约束（范围在查询谓词） | `items`/`total` 同谓词；未授权引用 422；写未授权 422 | 授权撤销即时生效（F030 既有） | I-11、I-12、I-15（模块 B，`real_scope`） |
| §22（读无 Audit） | 候选读取 | `audit_logs` append-only | 读路径不写审计 | — | I-17（计数不变；P10 实测 4→4） |
| 夹具直写（`INSERT ... generate_series`） | 测试专用数据构造 | 满足全部 CHECK/FK（`hostname=translate(...)`、`hostname_key=btrim(...)`、`resource_type` 枚举、`cluster_id` FK）——P9 插入成功即证明 | 不经过 Service Layer，**仅用于数据构造，不作为写入路径验证证据** | 每用例自建自清 | P9（150+151 行 0.075s，无约束违反） |

### 1.12 未验证项与降级（计划阶段声明；TEST 阶段按实际执行结果更新）

| # | 未验证/降级项 | 原因 | 降级口径 | 影响 |
| --- | --- | --- | --- | --- |
| U1 | 真实浏览器视觉、下拉面板渲染、虚拟滚动、键盘可达、屏幕阅读器语义 | AQ-4=B：不引入浏览器依赖；仓库无 Playwright/jsdom/Vitest（S-05 保证不新增） | 结论改为：状态与文案由 F 层纯函数断言；渲染层仅 `tsc`/`build` + 代码审读；**不计 PASS**，记 `NOT_TESTED` | A7 的「可访问语义」只在「`kind`/`role` 声明互异」粒度成立；真实 aria 呈现未证 |
| U2 | Ant Design `Select` 的 `showSearch`/`onSearch` 真实交互时序、debounce 实际时延与用户可感知延迟 | 同上（需 DOM 与真实输入事件） | 只断言「输入即检索的请求次数与参数」（F-03/F-05），不断言时延；product 明确排除性能指标 | 不影响 A2/A3/A4 判定；「输入即检索 vs 加载更多」（ON-6）由 architecture 决定并据其调整 F-03 期望请求次数 |
| U3 | 跨页面手工巡检（真人在真实浏览器点击新增 VM / 创建 Resource 全流程） | 无浏览器依赖；F016 真实栈入口本环境不可达（P14 `000`） | `NOT_REQUIRED`（AQ-4=B）；A1 的「提交被接受」改由 I-05/I-06 真实 PG + 生产 app 证明（§1.9） | 若协调器后续提供可用的真实栈（`F016_ACCEPTANCE=1` + `F016_BASE_URL`），可追加为补充证据，但不是本 Feature 的必需门禁 |
| U4 | `deleted=include/only` 与候选的交互（前端是否存在任何路径发送 include/only） | 候选必须默认 exclude（A5）；前端不应有该路径 | 由 F-01/F-02 负向断言覆盖；真实服务端行为由 I-09/I-13 覆盖 | — |
| U5 | 名次判定的「全库其它数据干扰」 | 每个用例 `TRUNCATE` 后自建夹具，名次确定但断言只取 `>=101` | 断言用不等式 + 第 1 页排除，不写死 110/120 | 若未来夹具与其它数据共存，断言仍成立 |
| U6 | 需求 §31–§33 的跨功能整体验收 | 属 F045 变更集整体回归 | `NOT_REQUIRED`（本 Feature）；**不得**用 F041 局部 PASS 拼成整体 PASS | — |

### 1.13 基线更新规则（ON-9）

| 基线 | 当前实测值（`d5c0a4c`/`af8cc71` 工作树） | 更新规则 |
| --- | --- | --- |
| `npm run smoke:client` | `340 passed, 0 failed`（P2，`d5c0a4c` 基线）；**T7 更正后目标基线 = `352 passed, 0 failed`**（340 + F-01..F-12 共 12 条，`await test(` 实测 352） | TEST 阶段要求：`failed == 0`、`exit code == 0`、`passed == 340 + N`，其中 `N` = 本报告 §1.7 实际新增用例数（以文件内 `await test(` 计数核对；T7 实测 `N = 12`）。**只允许通过追加新用例提高基线**：不得删除、`skip`、放宽既有 340 条断言来「让数字对上」。若出现 `failed > 0` 或 `passed < 340`，判 FAIL 并回溯。基线新值写入 §2 并成为后续 Feature 起点 |
| `pytest` 收集数 | **930 collected**（`tests/integration`，P6）；T11 更正后 = `930 + M`（`M` = 本次新增 F041 测试函数数，实测值见 §2） | 追加后要求：`collected == 930 + M`（`M` = F041 新增测试函数数）；`SKIPPED` 仍只有 F016 一条（既有环境开关）。不得靠 skip/xfail 通过 |
| 回归套件 | `test_resources.py` + `test_clusters.py` 24 passed（P7） | 要求 TEST 阶段全通过且用例数不减少 |
| `tsc`/`build` | `tsc --noEmit` 通过（P12） | 要求 `npm run build` 退出码 0 |
| 文档/契约零 diff | P3/P4 空输出 | 要求 TEST 阶段 `git diff --stat d5c0a4c -- docs/api docs/product docs/database backend frontend/package.json frontend/package-lock.json` 仍为空（S-01/S-05/S-06） |

### 1.14 与 `architecture.md` 的待核对接缝（TEST 前置条件，Final Test Design 收口项）

`docs/features/F041/architecture.md` 尚未建立（plan `implementation.architecture=PENDING`）。下列接缝**必须在 TEST 阶段开始前**与定稿 architecture 核对；核对结果只允许调整**导入名/形参名/请求次数期望**，不允许放宽 A1–A16 判定或把 §1.9 的 ③ 段替换为 mock：

| # | 待核对项 | 本设计的假设 | 若 architecture 不同 |
| --- | --- | --- | --- |
| R1 | 组件形态（ON-1） | 定稿（T5）：新增 `CandidateSelect` + 纯逻辑模块 `candidateSelectModel.ts`，`ui/controls.tsx` 零 diff | 若选 opt-in props：S-03 走方案 B 分支（既有 60 处调用点逐处不变） |
| R2 | 候选逻辑的纯模块边界 | 存在**无 JSX** 模块 `src/components/candidateSelectModel.ts`（T1），导出：`buildCandidateQuery(domain,{clusterId,search})`→`{domain,query}`（T6）、状态机（`idle/loading/success/error` + `items/total/message`）、`candidateView(state,domain)`（`kind/text/canRetry/role`）、`candidateTruncation(state,domain)`（`truncated/text`）、`candidateOptions(state,pinned)`、epoch 门控 `isStaleCandidateResponse`/`applyCandidateResponse`；另含 `initialCandidateState(domain,clusterId)`、`CandidateOutcome`、`resourceCandidateItems`/`clusterCandidateItems`（T8） | 若未抽出纯模块 → A4/A7/A9/A16 无 AQ-4=B 可执行证据 → **TEST BLOCKED**（§1.10） |
| R3 | 检索交互形态（ON-6） | 输入即检索：每次 settle 一次请求，`page` 恒 1 | 若含「加载更多」：F-03 期望改为「初始 1 次 + 每次显式加载更多 +1，且不等于 `ceil(total/100)`」，仍须证明次数与总量无关 |
| R4 | debounce 方案（ON-2/N11） | 内联定时器或 hook，无新依赖（S-05） | F 层用受控 promise 驱动，不依赖定时器真实延时（U2） |
| R5 | 空闲态/切集群（ON-4） | `clusterId===""` → idle；换集群清空旧候选并置 loading | 若引入额外 `empty` 前置，须保证 F-06 四态仍互异 |
| R6 | 编辑态 `currentHost`（ON-5） | pin 当前选中项（或按 id 精确补一条），不重复 | F-10 按实际选项合成函数调整断言形态，判定不变 |
| R7 | 超限提示文案（ON-11） | 文案含总数 + 分页边界（100），total 只取响应值 | F-08/F-09 按定稿文案调整正则，判定不变 |
| R8 | 请求竞态（ON-7） | `cancelled` 标志或 epoch 序号，陈旧响应丢弃 | F-05 断言「最终集合属于最新响应」不变 |
| R9 | 2 个载体的落点 | Host 在 `VirtualMachineFields.tsx`；Cluster 在 create 分支（`ResourceForm.tsx` + `ResourceCreatePage.tsx` 加载态） | S-04 的「允许引用点集合」按定稿调整，仍禁止扩散到 §13.4/列表筛选 |

### 1.15 结论（TEST DESIGN）

- **结论：`TEST DESIGN READY`（TD-F041-1 v1）**。A1–A16 全部有可执行、可重复、可在仓库内独立运行的映射；三层分工明确（I=服务端事实、F=前端请求/状态、S=零 diff）；≥101 夹具方案已在真实 PG 上实测可行（150+151 行 0.075s，名次判定 110 可复现，提交被服务端接受 201 已探针验证）；四态与提示文案在无 DOM 前提下有明确断言方式（§1.10）；基线值与环境限制已如实记录（§1.3、§1.12、§1.13）。
- **前置条件（TEST 阶段开始前必须完成）**：① `docs/features/F041/architecture.md` 定稿且 §1.14 R1–R9 核对完成；② 前端实现完成（F 层用例依赖其纯模块导出面）；③ 协调器确认 `TEST_DATABASE_URL` 指向专用测试库（`csm_f037_test`，库名含 `test` 已满足 conftest 守卫）。
- **声明**：本结论仅表示「方案可验证」，**不是测试通过**，**不批准实现**，**不放行合并或 Review**。A1–A16 当前一律为 `PLANNED / NOT TESTED`，不得计为 PASS；§2 TEST EXECUTION 尚未产出任何证据。
- **已知残余风险**：若实现把状态机/文案内嵌在 `.tsx`，A4/A7/A9/A16 将失去 AQ-4=B 下的可执行证据（只能 `TEST BLOCKED`）；若实现以「循环抓全部分页」或 `page_size>100` 换完整性，F-03/I-04 会立刻 FAIL。

### 1.16 TD 判定式更正登记（T1–T11，TEST 阶段核对 `architecture.md` §3 后落地）

原则：只改**导入名 / 形态 / 基线值**，不改验收判定强度（A1–A16 一条不削）。逐条证据见 §2。

| # | 对象（TD 位置） | 原判定式 | 更正后判定式 | 依据 |
| --- | --- | --- | --- | --- |
| T1 | §1.7/§1.14 R2 模块名 | `src/components/candidateSearch.ts`（暂记） | `frontend/src/components/candidateSelectModel.ts` | architecture §1.2/DR-F041-01；实测文件存在 |
| T2 | §1.7 F-07、§1.10 | `view.kind==="success"` | `state.kind==="success"` **且** `candidateView(state,domain).kind==="ready"`（视图投影无 `success` 值） | `candidateSelectModel.ts` 导出面 |
| T3 | §1.8 S-03、§1.4 A13 | `<Select` 仍 **60 处 / 23 文件** | 基线 **58 处 / 22 文件**（两个 F041 载体改为 `<CandidateSelect`）；实质判定 = `controls.tsx` 零 diff + **逐文件对照其余 21 文件计数不变** | architecture 文字算术不自洽（方案 A 必然 −2/−1）；实测 `git grep -c` 逐文件 diff 仅两载体变化 |
| T4 | §1.6/§1.8 S-01/S-06 | `git diff d5c0a4c -- backend` 必须完全空 | 收窄为**生产代码/配置零 diff**：`git diff --stat 698f11b -- backend` 空 + `git status --porcelain -- backend` 仅允许 `?? backend/tests/integration/f041_*.py` | architecture §3 T4 / DR-F041-09 |
| T5 | §1.8 S-04 | `<新组件名>`（`SearchableSelect`） | `CandidateSelect`；引用集合白名单 = 定义文件 + `VirtualMachineFields.tsx` + `ResourceForm.tsx`（+ `ResourceCreatePage.tsx` **仅文档注释**） | architecture §1.1/§1.4 |
| T6 | §1.7 F-01/F-02 | `buildCandidateQuery(...)` 直接产出查询对象 | 返回 `{ domain, query }`；用例取 `.query` 传给**既有** `listResources`/`listClusters` | `candidateSelectModel.ts` 签名；URL 断言不变 |
| T7 | §1.13 smoke 基线 | `340 passed, 0 failed` | **`352 passed, 0 failed`**；`await test(` 计数 352（340 + 新增 12），只允许追加 | architecture §1.8 L4/§3 T7；实测 |
| T8 | §1.7 F-06/F-10 导入面 | 仅 `idleCandidateState`/`loadingCandidateState` | 另含 `initialCandidateState(domain,clusterId)`、`CandidateOutcome`、`resourceCandidateItems`/`clusterCandidateItems`（响应项→候选项映射）；idle 可达性用 `initialCandidateState` 判定 | 纯模块导出面（R2 要求逻辑不出 `.tsx`） |
| T9 | §1.7 F-06/F-08/F-09/F-10 | `candidateView(state)`、`candidateTruncation(state)` | `candidateView(state, domain)`、`candidateTruncation(state, domain)`、`candidateOptions(state, pinned)`；文案正则与判定不变 | 同上 |
| T10 | §1.7 F-06 | 「`clusterId` 非空时最小态为 loading」（文字） | 机械判定：`initialCandidateState("cluster", "")`、`initialCandidateState("host", "c-1")` → `loading`；`initialCandidateState("host", "")` → `idle`（cluster 域 idle **不可达**） | architecture §3 T10 / DR-F041-02 |
| T11 | §1.13 pytest 基线 / §1.3 P10–P11 参照值 | `930 collected`；探针绝对值（audit `4→4`、名次 110/120、`total 119`） | `collected == 930 + M`（本次 `M = 18` → **948**，`SKIPPED` 仍仅 F016 一条）；探针值只作参照**不写死**：名次断言 `>=101` + 第 1 页排除，audit 断言 `before == after`，`total` 由夹具实数推导并与 ADMIN 全量对照 | TD §1.6 判定口径 / §1.12 U5 |

**未削弱项确认**：A1「提交被服务端接受」仍由真实服务端 + DB 行核对（I-05/I-06/I-07）承载，未改由 mock 承担；A6 仍在 `real_scope` 模块 B 判定；A2/A3 的 `page_size ≤ 100`、`page` 恒 1、请求次数与总量无关全部保留。

---

## 2. TEST EXECUTION

**TE-F041-1 v1；执行日期 2026-10-29；角色 tester（独立执行，未复用开发者结果）**。依据：§1 TD-F041-1（含 §1.16 更正）、`docs/features/F041/architecture.md` v1、`docs/features/F041/implementation.md`（Frontend，仅用于**比对**，不作证据来源）。

### 2.1 Environment（环境与数据来源）

| 项 | 值 |
| --- | --- |
| 仓库 / 分支 | `/home/hanhao/github/47oo/csm`；`feature/F041-candidate-completeness` |
| HEAD（TEST 执行时） | `698f11b`（`docs(F041): ARCHITECTURE + CONTRACT signed`）；`start_commit=d5c0a4c` |
| 被测改动形态 | F041 前端实现为**工作树未提交**改动（4 修改 + 2 新建），另本次 Tester 新增 3 个 `backend/tests/integration/f041_*.py` |
| 数据库 | **真实 PostgreSQL**，容器 `csm-f037-pg`，`TEST_DATABASE_URL=postgresql+psycopg://csm:csmtest@127.0.0.1:55432/csm_f037_test`（库名含 `test`，且 ≠ `DATABASE_URL`，满足 `tests/conftest.py` DB-D10 双守卫）；未触碰任何非测试库 |
| Schema 基线 | 每次 pytest session 由 `conftest.py` 重建 `public` + `alembic upgrade head`；用例间由 `committed_engine` teardown `TRUNCATE` 全部非 `alembic_version` 表 |
| 运行时 | Python 3.12.7 / pytest 7.4.4；Node **v22.23.3** / npm **10.9.9**（满足 `smoke:client` 原生 type stripping） |
| 后端应用形态 | 生产 `create_app()`（仅 `get_db` 被覆盖）；模块 A 走 legacy unrestricted scope shim，模块 B 带 `pytestmark = pytest.mark.real_scope`（生产 §23.2 范围） |
| 真实栈（F016） | `http://127.0.0.1:18080/api/v1/health` → `000`（不可达）→ 端到端入口 `NOT_TESTED`（不影响 I/F 层判定，见 §2.9 U3） |
| 产物目录 | `docs/features/F041/artifacts/`（`.txt`，仓库 `.gitignore` 忽略 `*.log`，故改用 `.txt`）；本次写权限外的文件均未修改 |

### 2.2 I 层：真实 PostgreSQL + 生产 app（新增测试资产）

新增（DR-F041-09 允许的测试资产，未改生产代码）：

| 文件 | 内容 |
| --- | --- |
| `backend/tests/integration/f041_helpers.py` | `seed_clusters`/`seed_bare_metal_hosts`（`INSERT ... SELECT generate_series`，150 Cluster + 150 同 Cluster `BARE_METAL`，名称确定性）/ `rank_by_server_order`（按既有 `sort` 逐页求 1-based 名次，**不硬编码 UUID、不用 `created_at`**）/ `id_by_query`（服务端 `q` 发现目标 id）/ `resource_cluster_id`、`vm_host_resource_id`（DB 行核对）/ `table_count` |
| `backend/tests/integration/test_f041_candidate_completeness.py` | 模块 A（未标记 `real_scope`）：I-01..I-10、I-13（401/403/404 部分）、I-14、I-16、I-17 — **14 个用例** |
| `backend/tests/integration/test_f041_candidate_scope.py` | 模块 B（`real_scope`）：I-11、I-12、I-13（VIEW_DELETED 部分）、I-15 — **4 个用例** |

执行：`cd backend && python3 -m pytest tests/integration/test_f041_candidate_completeness.py tests/integration/test_f041_candidate_scope.py -v` → **`18 passed`，exit 0**（日志 `artifacts/pytest-f041-i-layer.txt`）。夹具规模与名次：150 Cluster（`F41C-0001..0150`）、150 Host（`f41n-0001..0150`）；名次由 `rank_by_server_order` 按既有 `sort` 现场逐页求得，断言只写 `>=101` + 第 1 页排除（不写死数字，T11）；按夹具构造（`F41C-0001..0150`、`f41n-0001..0150`，用例内无其它同类对象）目标 `F41C-0110`/`f41n-0110` 为该域的确定性第 110 位、`f41n-0120` 为第 120 位。

| 用例 | 关键实际结果（真实输出） | 判定 |
| --- | --- | --- |
| I-01 | `page1.total=150`、目标 **不在** 第 1 页、`rank>=101`（构造上为 110）、`q=f41n-0110` → `total=1`、`items[0].id=目标` | PASS |
| I-02 | `page1.total=150`、`F41C-0110` 不在第 1 页、`rank>=101`（构造上为 110）、`q=F41C-0110` → `total=1` | PASS |
| I-03 | 响应 `page=1`/`page_size=100`；`total=150` 时 `len(items)=100`；`len(items) ≤ 100` | PASS |
| I-04 | `page_size=101`（resources 与 clusters）→ **422 `VALIDATION_ERROR`**，`fields` 含 `page_size`；`page_size=100` → 200；`page=0` → 422 | PASS |
| I-05 | `POST /resources {cluster:F41C-0110}` → **201**，响应 `cluster.id=目标`，详情一致，**DB `resources.cluster_id=目标`** | PASS |
| I-06 | `POST /resources` VM `host_resource_id=f41n-0110` → **201**，`virtual_machine.host.hostname=f41n-0110`，**DB `virtual_machine_details.host_resource_id=目标`** | PASS |
| I-07 | `PATCH` 换至 `f41n-0120` → 200 + DB 新值；activity `["CREATE","UPDATE"]`，UPDATE 的 `before=110`/`after=120`（T19） | PASS |
| I-08 | 候选集 `total=150`、全部 `BARE_METAL` 且属 C1；同集群去 `type` → `total=151`（VM 被排除）；邻集群 Host 不在其中 | PASS |
| I-09 | 软删 Host：`q` → `total=0/items=[]`；默认与 `deleted=exclude` 结果逐项相等且不含该 id；ADMIN `deleted=include` → `total=1`；软删 Cluster 同理 `total=0` | PASS |
| I-10 | 软删 Host 提交 → **422** `field=virtual_machine.host_resource_id` | PASS |
| I-13 | 匿名 `GET /resources?page_size=101` → **401**（`AUTH_REQUIRED`，鉴权先于参数校验）；VIEWER `POST /resources` 非法体 → **403**（`reason=permission`）；VIEWER 读取候选仍 200；随机 UUID 详情 → **404** | PASS |
| I-14 | 跨 Cluster Host / VM 类型资源 / 不存在 UUID → **422** 同固定 field；hostname 重复 → **409** `CONFLICT{reason:unique_conflict, field:hostname}` | PASS |
| I-16 | `f41n-0110` / `F41N-0110` / `n-0110` 均 `total=1` 且同一对象；`q=n-01` → `total>=10` 且 items 全部命中该子串（构造上为 `f41n-0100..0150` 共 51 条）；Cluster `q` 大小写不敏感（code/name ILIKE）；候选查询与同参数列表页 `total` 相等 | PASS |
| I-17 | 15 次候选读取（两域各 5 次含 `q`）前后 `audit_logs` 与 `resources` 计数**完全不变** | PASS |
| I-11（模块 B） | EDITOR（授权 C1..C3，全库 120 Cluster）候选 `total=3 == len(items)`；未授权 `q=F41C-0010` → `total=0`（响应不含该 code）；C1 Host 候选 `total=120`、`len(items)=100`；未加集群过滤的候选 `total=120`，而 ADMIN 同请求 `total=150` → **不可见的 30 个 Host 不计入 total** | PASS |
| I-12（模块 B） | EDITOR 向未授权 Cluster 建资源 → **422** `field=cluster`，响应不泄露 `F41C-0010` | PASS |
| I-13（模块 B） | EDITOR `deleted=include`/`only`（resources 与 clusters）→ **403** `FORBIDDEN{reason:permission}` | PASS |
| I-15（模块 B） | Host 域 `total=120 > len(items)=100 == page_size`（超限提示数据前提成立）；Cluster 域 `total=len(items)=3`（不产生超限语义） | PASS |

补充基线检查：`pytest --collect-only -q tests/integration` → **`948 tests collected`**（= 930 + 18，T11），`SKIPPED` 仍仅 `test_f016_acceptance.py` 一条（既有环境开关）；`test_f030_test_harness.py` 3 条守卫（legacy canary / marker AST 扫描 / 非空洞扫描）全部 PASS → 模块 B 的 `real_scope` 合规、模块 A 未污染范围语义。

### 2.3 F 层：`npm run smoke:client`（mock fetch，无 DOM）

`cd frontend && npm run smoke:client` → **`352 passed, 0 failed`，exit 0**（日志 `artifacts/frontend-smoke.txt`）；`grep -c "await test(" scripts/smoke-client.mjs` = **352**（既有 340 + 新增 12，T7）；日志中 `PASS: F041 …` 恰 **12** 条：

| 用例 | 覆盖 | 判定 |
| --- | --- | --- |
| F-01 | Host 域 URL：`/api/v1/resources`，`q`（首尾 trim 后）/`cluster_id`/`type=BARE_METAL`/`page=1`/`page_size=100`/`sort=hostname`/`order=asc`；**参数名集合精确等于 7 项**；`deleted`/`include`/`only` 负向断言 | PASS |
| F-02 | Cluster 域 URL：`q`/`page=1`/`page_size=100`/`sort=code`/`order=asc`，集合精确 5 项；无 `deleted`/`cluster_id`/`type`；label=`code — name` | PASS |
| F-03 | `total=154` 与 `total=1540` 均 **1 次请求**；`page` 恒 `1`、`page_size ≤ 100`；无 `ceil(total/100)` 量级序列 | PASS |
| F-04 | 响应 3→2 条时候选随之为 2 条且**等于本次响应 id 集**（无历史残留、无并集） | PASS |
| F-05 | 倒置 resolve：旧响应后到被 epoch 丢弃（`applyCandidateResponse` 返回**同一状态引用**），候选=最新响应 id | PASS |
| F-06 | 四态 `kind`=`idle/loading/error/empty`、`role`=`note/status/alert/log`、四段文案 `Set.size=4` 且非空；`error.canRetry=true`、含「可重试」、**不含**「无匹配」「暂无数据」；`initialCandidateState` 证 idle 仅 host+空集群可达（T10） | PASS |
| F-07 | 失败态 → `calls.length=1` 且等待后仍 1（不自动重试）→ 显式重试 `=2`（恰 +1）→ `state.kind=success` **且** `view.kind=ready`（T2）；全程 `view.kind` 未出现 `empty` | PASS |
| F-08 | `{154,100}` → `truncated=true` 且文案含 `154` 与 `100`；`{3,3}`、`{0,0}` → `truncated=false`、文案 `null` | PASS |
| F-09 | `{total:3,items:3}` 无提示；`{total:3,items:1}` 文案含 `3` 且**不含** `120` | PASS |
| F-10 | pinned 在不含/含两分支均**恰一次**；loading/error/empty 态仍保留为唯一选项；载荷 `virtual_machine.host_resource_id=pinned-1`，改选后为新 id | PASS |
| F-11 | 选中 id 原样进 body（VM `host_resource_id`、Resource `cluster` 传 id 不退化为 code）；`calls.length=1` | PASS |
| F-12 | 提交 422/409/403/404 后候选态仍 `success`、未被清空/未变 `empty`；错误经既有描述器呈现；不重试 | PASS |

`smoke:client` 为唯一前端测试入口（无新 script/依赖），断言对象是纯逻辑模块 `candidateSelectModel.ts` + 既有 `api/{resources,clusters}.ts`（T1/T6）；未渲染 React、未读 DOM（AQ-4=B）。

### 2.4 S 层：零 diff / 调用点集合 / 构建 / 状态一致性

日志：`artifacts/static-s-layer.txt`、`artifacts/frontend-build.txt`。

| ID | 命令 | 实际结果 | 判定 |
| --- | --- | --- | --- |
| S-01/S-05/S-06 | `git diff --stat 698f11b -- backend docs/api docs/product docs/database frontend/src/components/ui/controls.tsx frontend/src/api frontend/package.json frontend/package-lock.json`；同命令对 `d5c0a4c` 再执行一次 | **两次均空输出，exit 0** | PASS |
| T4 backend 边界 | `git status --porcelain -- backend` | 仅 `?? backend/tests/integration/f041_helpers.py`、`?? …/test_f041_candidate_completeness.py`、`?? …/test_f041_candidate_scope.py` | PASS |
| S-02 | 含于上一行（`frontend/src/api` 零 diff） | API 端点/查询参数集合未变（无新端点、无 `include`/`only`） | PASS |
| S-03 | `grep -rn "<Select" frontend/src --include=*.tsx \| wc -l` = **58**；文件数 **22**；`git grep -c` 逐文件对照 `698f11b` vs 工作树 | 仅两处 F041 载体变化：`ResourceForm.tsx 4→3`、`VirtualMachineFields.tsx 1→0`；**其余 21 文件计数逐个不变**；`controls.tsx` 零 diff（T3） | PASS |
| S-04 | `grep -rn "CandidateSelect" frontend/src` | 引用集合 = 定义文件 + `VirtualMachineFields.tsx`（import+渲染）+ `ResourceForm.tsx`（import+渲染）+ `ResourceCreatePage.tsx:33`（**仅文档注释**）；`IpAddressesPage`/`GlobalSearch`/`ResourcesPage`/其余 `*Form` 均 **0** 命中（T5） | PASS |
| S-07 | `cd frontend && npm run build` | **exit 0**、`✓ built in 24.33s`、`error TS` = 0（chunk 体积警告为 F040 既有结论，不计缺陷） | PASS |
| S-08 | `python3 scripts/validate_project_state.py --feature F041` | `PROJECT STATE VALID (structure/gates/files; verify approval truth and Git/test evidence separately)`，exit 0（结构通过 ≠ 批准或证据有效） | PASS |

A3 的「不循环翻页 / 不前端全量缓存」另有代码审读证据：`buildCandidateQuery` 中 `page` 为常量 1、`CandidateSelect.tsx` 的请求触发点唯一（`[domain, clusterId, committedSearch, retryToken]`），`applyCandidateResponse` 整体替换且陈旧响应原样返回。

### 2.5 回归（独立执行，不改动用例）

| 组 | 命令 | 结果 |
| --- | --- | --- |
| 指定回归 | `pytest tests/integration/test_f037_import_parse_errors.py tests/integration/test_imports.py -q` | **81 passed**，exit 0（`artifacts/pytest-regression-f041.txt`） |
| I-18（A14） | `pytest tests/integration/test_resources.py tests/integration/test_clusters.py tests/integration/test_interfaces.py -q` | **72 passed**，exit 0（`artifacts/pytest-regression-i18.txt`）；无新增 skip/fail |
| F023/F034 | `pytest tests/integration/test_f023_resource_interface_ip_import.py tests/integration/test_f034_csv_text_carrier.py tests/integration/test_f034_csv_text_carrier_scope.py -q` | **59 passed**，exit 0（`artifacts/pytest-regression-f023-f034.txt`） |
| T08/T09/T19 + 列表 `q` | `pytest tests/integration/test_virtual_machine.py tests/integration/test_search.py -q` | **38 passed**，exit 0（`artifacts/pytest-regression-vm-search.txt`） |
| 既有前端用例 | `npm run smoke:client` 中的 340 条既有 F001–F040 用例 | 全部 PASS（352 = 340 + 12，既有块零删改） |

### 2.6 验收映射 A1–A16（逐项结论）

| 验收 | 用例（实际执行） | 结论 |
| --- | --- | --- |
| A1 名次 ≥101 可检索且提交被接受 | I-01、I-02、I-03、I-05、I-06、I-07（真实 PG + 生产 app + DB 行 + T19 审计）；F-11（载荷） | **PASS** |
| A2 单页上限 | I-03、I-04、I-08；F-01、F-02、F-03 | **PASS** |
| A3 不全量加载 | F-03（154 与 1540 均 1 次、`page=1`、`page_size≤100`）；S 层代码审读（无循环翻页、无累积） | **PASS** |
| A4 无全量缓存 / 旧结果不残留 | I-09（软删即时从候选消失）；F-04、F-05（整体替换 + epoch 丢弃） | **PASS** |
| A5 软删排除、不发 `include`/`only` | I-09、I-10；F-01、F-02（负向断言） | **PASS** |
| A6 §23.2 范围与 `total` 只计可见 | I-11（全库 120/授权 3 → `total=3`；Host 可见 120 vs 全库 150）、I-12、I-15；F-09 | **PASS** |
| A7 四态显式区分 | F-06（kind/role/文案两两互异、error 不伪装为空）；补充浏览器（临时脚本）实测 idle/loading/error/empty 渲染 | **PASS**（真实 DOM aria 细节见 §2.9 U1） |
| A8 失败可重试、不伪装为空 | F-07（不自动重试、重试恰 +1、恢复候选）；补充浏览器实测失败态 alert + 重试 | **PASS** |
| A9 超限显式提示 | I-15（`total > items.length == page_size` 数据前提）；F-08（文案含 total 与 100） | **PASS** |
| A10 提交拒绝语义不变 | I-10（软删 Host 422）、I-12（未授权 422 `cluster`）、I-13（401/403/404）、I-14（跨 Cluster/VM 类型/不存在 422、唯一冲突 409）；F-12 | **PASS** |
| A11 零契约 diff | S-01/S-02/S-05/S-06（两份基线均空输出）；I 层仅用既有参数 | **PASS** |
| A12 `q` 仍 ILIKE | I-16（大小写/中段子串、候选与列表页 `total` 一致）；S-06（backend 零 diff，未引入 pg_trgm 变化） | **PASS** |
| A13 共享 `Select` 语义不变 | S-03（`controls.tsx` 零 diff；58/22 基线 + 逐文件对照仅两载体）；S-04（新组件引用白名单） | **PASS** |
| A14 关系/默认值/流程不回归 | I-07（T19）、I-18（72 passed）、T08/T09 套件（38 passed）、F023/F034（59 passed）、F037/imports（81 passed）、`npm run build` exit 0、既有 340 条 smoke 全通过 | **PASS** |
| A15 候选读取无写副作用 | I-17（`audit_logs`/`resources` 计数不变） | **PASS** |
| A16 编辑态不回填丢失 | F-10（pinned 恰一次、载荷 id 不变）；I-07（换 Host 服务端接受 + UPDATE 审计 before/after）；补充浏览器（下拉首项为 pinned） | **PASS** |

### 2.7 与 Frontend 自检（`implementation.md` §3–§4）比对

| 项 | Frontend 自检 | Tester 独立结果 | 一致 |
| --- | --- | --- | --- |
| `tsc` / `npm run build` | 通过（§3.1） | 通过（exit 0，§2.4 S-07） | 是 |
| `smoke:client` | 352 passed / 0 failed（§3.1） | **352 passed / 0 failed，exit 0**，`await test(` = 352（§2.3） | 是 |
| `<Select` 计数 | 58 处 / 22 文件（§7.1，并指出架构文字 60/23 算术不自洽） | 复核一致，并补逐文件 diff 证明其余 21 文件不变（T3/§2.4） | 是（已登记为 T3） |
| `CandidateSelect` 引用集合 | 定义 + 两载体 + 一处注释（§2.5） | 一致（S-04） | 是 |
| 零 diff（契约/Schema/后端/依赖/共享控件） | 空（§3.2/§5） | 复核为空（S-01/S-05/S-06 ×2 基线） | 是 |
| 浏览器 23 项 + 断点 4 项 | 23 passed / 4 passed（§4，`/tmp` 脚本，非仓库入口） | 以同一临时脚本复跑：**23 passed / 4 passed**（`artifacts/browser-supplementary.txt`、`browser-layout-supplementary.txt`）；**仅作补充，不计入仓库内门禁**，也不构成真实 API 集成证据 | 是（证据强度有限，见 §2.9 U2） |
| 未验证项 | U1–U5（§7.4） | 采纳并在 §2.9 重述 + 补充两处 NOT_TESTED | 是 |

差异（不构成缺陷）：Frontend §7.3 记录 antd 关闭下拉会触发一次 `onSearch("")` 的基准请求；Tester 在代码中确认该路径（`showSearch.onSearch` → `setSearchInput` → debounce 提交空串 → 1 次请求），因其**与候选总量无关**，不影响 A3/A4；见 §2.9 NOTE-1。

### 2.8 Defects / 观察

| ID | Severity | 层 | 位置 | 证据 / 期望与实际 | 影响 | Owner | 是否必须修复 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| — | — | — | — | **无 BLOCKER / HIGH / MEDIUM 缺陷；全部断言按 TD 原判定通过，未修改期望值或放宽断言** | — | — | — |
| NOTE-1 | NOTE | Frontend | `CandidateSelect.tsx` 的 `showSearch.onSearch` | 关闭下拉时组件库回灌空检索词 → 额外 1 次不带 `q` 的基准请求（实现 §7.3 已记录）；请求次数仍与候选总量无关 | 无（A3/A4 判定不受影响）；一次点击可能产生 2 次请求 | Architect / Frontend（记录即可） | 否 |
| NOTE-2 | NOTE | Docs | `architecture.md` §1.9/§3 T3 与 `implementation.md` §7.1 | 架构文字「方案 A 下 `<Select` 仍 60/23」算术不自洽；实测 58/22，其余 21 文件逐处不变 | 无（不属验收判定）；已按 T3 更新 TEST 基线，但 `docs/architecture/**` 不在 Tester 写权限，交由协调器/Architect 决定是否勘误 | Architect | 否 |
| NOTE-3 | NOTE | Test | TD §1.6 I-11/I-15 的探针参照值（`total=119`、audit `4→4`） | 探针值为 P11 序列副产物；本次改用干净夹具：可见 Host 120 精确相等，并与 ADMIN 全量 150 对照；audit 断言改为 `before==after`（T11） | 无（判定强度提升：由导出值精确相等替代探针数字） | Tester（已自纠） | 否 |
| NOTE-4 | NOTE | Test infra | 仓库 `.gitignore:124` `*.log` | TD 约定的 `artifacts/*.log` 不会被 Git 追踪；本次产物改为 `.txt`（F040 的 `.log` 为历史已追踪文件） | 无；协调器提交时无需 `-f` | 协调器 | 否 |

### 2.9 未验证项（NOT_TESTED，均不计 PASS）

| # | 项 | 原因 | 替代证据 | 影响 |
| --- | --- | --- | --- | --- |
| U1 | 真实屏幕阅读器播报、Ant Select 虚拟滚动与完整键盘可达矩阵 | 仓库无 Playwright/jsdom/Vitest，AQ-4=B 明确不引入浏览器依赖 | F-06 的 `kind`/`role`/文案断言 + 临时脚本（仓库外）实测 `role=combobox`、`label[for]`、a11y 镜像 `aria-label`、`role=alert` | A7 仅在「状态与语义声明互异」粒度判定；真实播报未证 |
| U2 | antd 下拉关闭回灌空检索词的真实时序、debounce 300ms 的用户可感知时延 | 需真实输入事件与 DOM 计时 | 代码审读 + 临时脚本（每次交互 1 次请求、显式重试恰 +1） | 不影响 A2/A3/A4/A8；已记 NOTE-1 |
| U3 | 真实前后端端到端（F016 真实栈点击流） | `127.0.0.1:18080` 不可达（`/api/v1/health` → `000`）；AQ-4=B 列为 `NOT_REQUIRED` | A1 的「提交被接受」由 I-05/I-06/I-07 真实 PG + 生产 app 承载；前端请求形状由 F 层断言 | 无（本 Feature 非必需门禁） |
| U4 | 性能指标（检索时延、请求体积、大列表渲染性能） | product §3 明确不在验收范围 | — | 无 |
| U5 | 需求 §31–§33 跨功能整体验收 | 属 F045 变更集整体回归；本 Feature 不得拼成整体 PASS | — | 无（本 Feature） |
| U6 | 临时浏览器脚本（`/tmp/f041_browser.py`、`/tmp/f041_layout.py`）为 Frontend 编写、以 `page.route` mock API，且不在仓库内 | 非 Tester 独立资产、非真实 API、无仓库门禁 | 仅作补充记录，**不改 U1–U3 的 NOT_TESTED 判定** | 无 |

### 2.10 基线更新（供后续 Feature 使用）

| 基线 | 旧值 | 新值（TE-F041-1 实测） |
| --- | --- | --- |
| `npm run smoke:client` | 340 passed / 0 failed | **352 passed / 0 failed**（`await test(` = 352，exit 0） |
| `pytest tests/integration` 收集数 | 930 | **948**（+ 18 个 F041 用例；`SKIPPED` 仍仅 F016 一条） |
| `<Select` 调用点 | 60 处 / 23 文件 | **58 处 / 22 文件**（两个 F041 载体改 `CandidateSelect`） |
| 回归套件 | test_resources + test_clusters 24 passed | test_resources/test_clusters/test_interfaces **72 passed**（无 fail/skip 变化） |

**结论：`READY FOR REVIEW`（TE-F041-1，2026-10-29）**。I 层 18 个用例（真实 PostgreSQL + 生产 app）、F 层 `smoke:client` 352/0、S 层零 diff 与构建、回归 5 组套件全部实际执行并通过；A1–A16 全部 PASS，无 BLOCKER/HIGH/MEDIUM 缺陷。详见 §2.1–§2.10。

GIT: git rev-parse --short HEAD
GIT: git status --porcelain (×3：全仓库 / `-- backend` / `--untracked-files=all -- docs/features/F041`)
GIT: git log --oneline -6
GIT: git branch --show-current
GIT: git diff --stat 698f11b -- backend docs/api docs/product docs/database frontend/src/components/ui/controls.tsx frontend/src/api frontend/package.json frontend/package-lock.json
GIT: git diff --stat d5c0a4c -- backend docs/api docs/product docs/database frontend/src/components/ui/controls.tsx frontend/src/api frontend/package.json frontend/package-lock.json
GIT: git grep -c "<Select" 698f11b -- 'frontend/src/**/*.tsx'
GIT: git grep -c "<Select" -- 'frontend/src/**/*.tsx'
GIT: git check-ignore -v docs/features/F041/artifacts/frontend-smoke.log
GIT: git ls-files docs/features/F040/artifacts
