# F039 Dashboard 容量查询批量化与查询计数基准（R10）— TEST REPORT

- **状态**：TEST_DESIGN 完成（`TEST DESIGN READY`）；**仅 §1 本轮产出**，未执行正式 TEST
- **版本**：v1（2026-10-29）| 分支 `feature/F039-dashboard-queries`，start_commit `f66d1f3`，本轮 HEAD `f09387a`
- **依据**：`docs/features/F039/product.md` v1（A1–A8 / N1–N7 / ON-1..5）、`docs/api/F013.md` §3.3、requirements §20 / §23.2 / §31 T32·T88、`docs/project/implementation-rules.md`
- **Environment（实测）**：PostgreSQL **16.15**（`127.0.0.1:55432`，user `csm`，superuser/createdb）；库 `csm_f037_test`（DB-D10 guard：名称含 `test`）；Python **3.12.7**、pytest **7.4.4**、SQLAlchemy **2.0.34**、psycopg **3.2.13**。本轮探针另行建一次性库 `csm_f039_probe_test` / `csm_f039_lit_test` 并在结束时 `DROP DATABASE`（无残留）；未对 `DATABASE_URL` 指向的库做任何操作。

## 1. TEST DESIGN（TD-F039）

### 1.1 度量定义（落地 ON-2 / ON-5）

- **计数器**：`event.listen(engine, "before_cursor_execute", listener)`，`finally: event.remove(...)`（先例 `backend/tests/integration/test_search_related_tester_acceptance.py:315-327`）；只统计 `statement.lstrip().upper().startswith("SELECT")`，因此 **BEGIN / COMMIT / SAVEPOINT / DDL / DML 天然不计**。
- **两个度量点（计数窗口只包住单次被测请求，最多一次丢弃的 warm-up）**：
  - `q_svc(N)` = `app.services.dashboard.get_dashboard(session, page=1, page_size=N, scope=None)`：**不计认证、不计 §23.2 范围解析**，隔离聚合路径本身（主判据）。
  - `q_http(N)` = `client.get("/api/v1/dashboard", params={"page_size": N})`：含请求级固定开销 `C`。**认证不计**（`role_client_factory` 在 fixture 建立时已 login，位于计数窗口外）。
- **常数上界判定式**：以严格相等为主（`q(1) == q(10) == q(50)`），另加与 N/P 无关的绝对封顶 `q_svc(50) <= K`，`K = 20`（= 常量部分 8 + 批量开销余量 12）。K 为实现后首次实测再钉死的**字面量**；**不得**写成 `a + b*N` 之类与规模相关的表达式。HTTP 侧用差值式：`q_http(N) - q_svc(N) == C` 且 `C` 在 N=1/10/50 上相同（单集群夹具，使授权解析与 N 无关）。
- **基线不复用**：start_commit 实测 14 / 68 / 308（§1.4），同一断言在基线上必须失败；**禁止以估算值充当实测**（ON-5 / N7），未实测项只能记 FAIL / BLOCKED / NOT TESTED。

### 1.2 用例映射 A1–A8

层：U=纯函数 / I=真 PG+TestClient 集成 / M=插桩计数（真 PG）/ S=套件·diff 级。测试模块：`backend/tests/integration/test_f039_query_count.py`（A1/A2/A4/A5，**不 import `app.core.access_scope`**，故不带 `real_scope`）与 `test_f039_scope.py`（A3，必须 `pytestmark = pytest.mark.real_scope`，否则 `test_f030_test_harness.py` AST 守卫失败）。

| ID | 层 | 前置夹具 | 命令 | 判定表达式（要点） | 证据落点 | A / T |
| --- | --- | --- | --- | --- | --- | --- |
| TD-F039-1a | M | 1 Cluster + 50 Network ×（1 RESERVED + 2 AUTO + 4 IP），真实 API 建（复制 `test_dashboard.py` 的 `_cluster/_network/_pool/_ip`） | `pytest tests/integration/test_f039_query_count.py -q -k query_count_network` | `q_svc(1) == q_svc(10) == q_svc(50) <= K(=20)` | 本文件 §2（实现轮）+ 测试断言 | A1 |
| TD-F039-1b | M | 1 Network，AUTO 池 P=0→4 逐个追加 | 同上 `-k query_count_pool` | `q_svc(P=0) == … == q_svc(P=4)`，且每步 `len(row["auto_pools"]) == P` | 同上 | A1 |
| TD-F039-1c | M | 同 1a 夹具，HTTP 侧 | 同上 `-k query_count_http` | `q_http(N) - q_svc(N) == C`，`C` 在 N=1/10/50 相同；`q_http(50) <= K + C` | 同上 | A1 |
| TD-F039-1d | M | start_commit 基线（§1.4/§1.6 方案） | `PYTHONPATH=<基线树>/backend python docs/features/F039/scripts/query_count_baseline.py` | 输出 `N → queries` 表，与 §1.4 一致（±0） | 本文件 §1.4（本轮）+ §2（实现轮同法复测） | A1 / A8 / ON-5 |
| TD-F039-2a | I | §20 边界矩阵：dedup / AUTO+池外手动 / INACTIVE / 禁用段 4 个网络 | `pytest … -k capacity_equivalent` | 见 §1.5 判定式（逐项 dict 相等 vs `/networks/{id}/capacity`，池按 `ip_pool.id` 映射） | 测试断言 | A2 / T32 |
| TD-F039-2b | I | 同 2a | 同上 | 硬编码字面量（不依赖端点自证）：dedup 244/0/244；AUTO `.100-.110` + 未绑定 `.100` + 池外 `.200` → 池 11/1/10、网络 244/2/242；INACTIVE 不清零；`240.0.0.0/24` → 0/0/0；`/31` → 2、`/32` → 1（后三者本轮实测，见 §1.5） | 测试断言 | A2 / T30·T32 |
| TD-F039-2c | I | 池占用按当前地址：raw SQL 使 AUTO 区间内 IP 的 `ip_pool_id` 指向 MANUAL 池 | 同上 | 该池 `occupied == 1`（不按分配来源） | 测试断言 | A2 / T32 |
| TD-F039-2d | U | 无 DB | `pytest tests/unit -q -k capacity_disabled`（或同模块纯函数用例） | `subtract_intervals(base_usable_intervals("240.0.0.0/24"), _DISABLED_INTERVALS) == []` | 测试断言 | A2 |
| TD-F039-3a | I | `real_scope`：A/B/C 三集群各 1 网络；VIEWER 仅授权 A、B；无授权用户；ADMIN | `pytest tests/integration/test_f039_scope.py -q` | VIEWER：`counts` 仅含 A+B、`items` 仅 A/B、`total` 为可见数、C 的 id/name 不在 `resp.text`；零授权：`counts` 全 0 + `items == []` + `total == 0`；ADMIN 含 C | 测试断言 | A3 / T88·T85–T87·T93 |
| TD-F039-4a | I | `/30` + 2 IP + gateway（raw SQL 写入 gateway，同 `test_dashboard.py` 模式） | 同 2a 模块 | `remaining == -1` 且 `== capacity["network_capacity"]["remaining"]`；不截断、不下限 0 | 测试断言 | A4 |
| TD-F039-5a | I | 固定夹具（2 页数据） | 同模块 | 字段名/类型 key set 精确相等、`items` 顺序 `created_at desc, id asc`、分页不改变 `counts`、`401→403→422→200` 顺序与 `error.code` / `reason` 逐字不变（现状取自本轮 12 passed 的运行，不新造口径） | 测试断言 | A5 |
| TD-F039-5b | S | — | `git diff --stat f66d1f3 -- docs/api` | 输出为空（契约零 diff；唯一例外须有 Architect 澄清附注时才允许非空并单独记录） | 命令输出 | A5 / N6 |
| TD-F039-6a | S | — | §1.6 回归命令 | 不低于本轮基线：`test_dashboard.py` 12 passed；六套件 33 passed / 5 skipped（skip 原因仍为 `F016_ACCEPTANCE` 未启用） | 命令输出 | A6 |
| TD-F039-7a | S | — | `git diff --stat f66d1f3 -- frontend`；`cd frontend && npm run typecheck` | diff 为空 + typecheck 通过；**UI 交互验证 = NOT_REQUIRED**（plan `layers.frontend=false`，响应面零变更） | 命令输出 | A7 |
| TD-F039-8a | M | 批量语句 | `EXPLAIN`（实现轮在真 PG 上对新增 SQL 执行，非 `EXPLAIN ANALYZE` 猜测） | 聚合语句使用既有 `ix_ip_pools_network_id` / `ix_ip_addresses_network_id` 或 PK；无 `Seq Scan on ip_addresses|ip_pools|networks` 退化；并断言 `dashboard.py` 仍调用 `ip_capacity.network_capacity/auto_pools_capacity`（公式单点，薄包装） | `docs/features/F039/**` 证据文件 + 测试断言 | A8 / ON-4 |

### 1.3 TD-F039-1 构造方式与基线取得（可执行方案）

- **N 轴**：只建一套 50 Network 夹具，N 由 `page_size ∈ {1,10,50}` 切换（≤100 上限、单页内），避免三套数据造成夹具差异；每 Network `10.{i}.0.0/24`、gateway `.1`、RESERVED `.2-.10`、AUTO `.100-.120` 与 `.130-.140`、未绑定 IP `.100/.101/.130/.200`。数据决定性，不使用随机种子（ON-3）。
- **P 轴**：单 Network 上逐个追加 AUTO 池，每步同法计数（每追加 1 池即多 1 次占用计数 → 该轴单独证明「不随 AUTO 池数增长」）。
- **start_commit 基线取得方式（本轮已执行，非估算）**：本轮实测时工作树已与 start_commit 等价——`git hash-object` 与 `git rev-parse f66d1f3:<path>` 相等（`dashboard.py` `f0ca4d28…`、`ip_capacity.py` `7e01365c…`），且 `git diff --stat f66d1f3 -- backend` 为空 ⇒ §1.4 数值即基线，报告记录 commit + blob 供追溯。实现后若需复测基线：`git archive f66d1f3 backend | tar -x -C /tmp/f039_base`（只读导出，不改变 Git 状态）后 `PYTHONPATH=/tmp/f039_base/backend python <探针>`；探针自建库→`alembic upgrade head`→API 造数→计数→`DROP DATABASE`。

### 1.4 本轮实测基线（start_commit `f66d1f3`，真 PG）

构造：1 Cluster、50 Network（各 1 RESERVED + 2 AUTO 池、4 个未绑定 IP）；`networks.total=50`、首行 `capacity={allocatable_total:244, occupied:4, remaining:240}`、`auto_pools` 长度 2。

| N (`page_size`) | `q_svc`（get_dashboard, scope=None） | `q_http`（GET /api/v1/dashboard） |
| --- | --- | --- |
| 1 | 14 | 15 |
| 10 | 68 | 69 |
| 50 | 308 | 309 |

- 斜率 **+6 / Network**（= 4 + 2 AUTO 池），常量部分 **8**，`q_http = q_svc + 1`；`delta(N=10)-delta(N=1)=54`、`delta(N=50)-delta(N=1)=294`，per-network slope `6.00`。
- 池轴（N=1，AUTO 池数 2/3/4/5/6）→ `14/15/16/17/18`，**+1 / 池**。
- 结论：基线与 product §2 静态估算 `8 + 4×网络数 + AUTO池数` 一致；上述值即 A1 修订前的对照证据，`q_svc(1)==q_svc(50)` 在基线为 **假**（14 ≠ 308）。

### 1.5 A2/A3/A4 等价性与范围断言细则

```python
# A2 逐项等价（对每个网络行；池按 id 映射，避免顺序差造成假 FAIL）
assert row["capacity"] == {k: cap["network_capacity"][k]
                           for k in ("allocatable_total", "occupied", "remaining")}
assert {(p["ip_pool"]["id"], p["allocatable_total"], p["occupied"], p["remaining"])
        for p in row["auto_pools"]} == {(p["ip_pool"]["id"], p["allocatable_total"],
        p["occupied"], p["remaining"]) for p in cap["auto_pools"]}
# 顺序另证（§3.3 口径，均来自同一 ip_capacity）
assert [p["ip_pool"]["id"] for p in row["auto_pools"]] == \
       [p["ip_pool"]["id"] for p in cap["auto_pools"]]
```

- **A2 + T32 覆盖点**：gateway∩RESERVED 不重复扣减、未绑定 IP 计占用、池外手动 IP 计 Network 占用、AUTO 池 `|池范围 ∩ 可分配集合|`、池占用按当前地址、INACTIVE 不清零、§11.1 禁用段（本轮实测：`240.0.0.0/24` **可创建**、`allocatable_total=0`，`240/4` 内 IP 创建 **422**，故禁用段扣减可通过 API 夹具覆盖）；边界 `/31→2`、`/32→1`（本轮实测）。**加硬编码字面量**，不依赖「端点与 Dashboard 同源于 `ip_capacity`」这一自证循环。
- **A3**：`real_scope` 模块（不回退 legacy unrestricted shim）；未授权集群的对象 id/name 不在响应文本、`counts`/`total` 不泄露规模；零授权全 0 + 空列表；ADMIN 不受限。
- **A4**：`/30` + 2 IP + gateway ⇒ `remaining == -1`，与端点一致，不截断。
- **只读性**：A2/A3 用例内顺带断言 `audit_logs` 计数前后不变（复用 `test_dashboard_writes_no_audit` 口径），确认无业务写副作用。数据完整性：F039 无 Schema/唯一性/生命周期/Migration 变更，故不触发表结构或迁移验证（`data-integrity` 结论：仅只读聚合口径）。

### 1.6 命令、降级规则与未验证项

```bash
cd backend && export TEST_DATABASE_URL='postgresql+psycopg://csm:csmtest@127.0.0.1:55432/csm_f037_test'
python -m pytest tests/integration/test_dashboard.py -q                     # 本轮 12 passed / 10.59s
python -m pytest tests/integration/test_f039_query_count.py tests/integration/test_f039_scope.py -q
python -m pytest tests/integration/test_f013_tester_acceptance.py tests/integration/test_f016_acceptance.py \
  tests/integration/test_f027_access_scope.py tests/integration/test_f028_acceptance.py \
  tests/integration/test_search_related_tester_acceptance.py tests/integration/test_f030_test_harness.py -q
  # 本轮基线 33 passed, 5 skipped / 55.73s
git diff --stat f66d1f3 -- backend docs/api frontend                         # 本轮空，0 文件
```

- **降级规则**：计数只认 `before_cursor_execute` 实测；PG / pytest / SQLAlchemy 版本变化必须重测并在 §2 记录版本。任何「应为 N 次」的推导、静态估算、耗时推断都不得进入 PASS（N7：不得把未测得耗时写成「已优化/已修复慢查询」）。
- **本轮实测阻塞项**：`F016_ACCEPTANCE=1 python -m pytest tests/integration/test_f016_acceptance.py -q -k "t32 or dashboard"` → `E httpx.ConnectError: [Errno 111] Connection refused`（F016 整体验收需活动 HTTP 栈）。该路径下的 T32 / T88 整体验收用例记 **BLOCKED（不计 PASS）**；本 Feature 的 T32/T88 由 TD-F039-2a/2b/3a 在真 PG 本地套件承担。
- **NOT_REQUIRED**：前端 UI 交互与真实前端↔API 集成（plan `layers.frontend=false`、响应面零变更；仅以 `frontend/` 零 diff + `npm run typecheck` 作 A7 证据）。**NOT TESTED（本轮）**：EXPLAIN 计划与 K 的最终值（实现轮 TD-F039-8a / 1a）。
- **范围外**：性能/耗时、缓存、索引与 Schema（N4/N5）、F045 整体验收。

### 1.7 结论

A1–A8 均已映射到可执行用例与判定式；A1 的计数范围、N/P 构造、常数上界与 start_commit 基线数值已**实测**（14/68/308，非估算）。**`TEST DESIGN READY`** — 该结论仅表示方案可验证，**不是测试通过**，不批准实现或合并。实现完成后按同一 Test Design 执行 TEST；若 Architect 采用 ON-1 的「新增批量入口」并追加 F013 §3.3 澄清附注，定稿前需回看 TD-F039-2a/2b 等价性口径、TD-F039-5b 契约 diff 例外与 TD-F039-8a 公式单点断言。

GIT: git status --short
GIT: git rev-parse --short HEAD
GIT: git branch --show-current
GIT: git log --oneline -8
GIT: git rev-parse f66d1f3 f09387a
GIT: git rev-parse f66d1f3:backend/app/services/dashboard.py f66d1f3:backend/app/services/ip_capacity.py
GIT: git hash-object backend/app/services/dashboard.py backend/app/services/ip_capacity.py
GIT: git diff --stat f66d1f3 -- backend docs/api frontend
GIT: git diff --stat f66d1f3
GIT: git diff --name-only f66d1f3 -- backend docs/api frontend | wc -l
GIT: git status --porcelain
