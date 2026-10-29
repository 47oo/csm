# F039 Dashboard 容量查询批量化与查询计数基准（R10）— IMPLEMENTATION（后端）

- **状态**：`BACKEND COMPLETE`（2026-10-29）| 分支 `feature/F039-dashboard-queries`，HEAD `831276e`，start_commit `f66d1f3`
- **依据**：`F039/architecture.md` v1 §2/§3/§4/§10（ON-1 薄包装 + 预取上下文、B1/B2/B3、A2 八项、K 实测）；`F039/test-report.md` v1（基线 14/68/308）；`docs/api/F013.md` v2 §3.3
- **范围**：仅 `backend/app/services/ip_capacity.py`、`backend/app/services/dashboard.py` + 本文件。零契约 diff、零 DDL、零前端、零路由/Schema 改动。

## 1. 变更清单
`ip_capacity.py`
- 新增 `CapacityContext`（frozen dataclass，**只装载数据**：`reserved` / `auto_pools[(pool, occupied)]` / `occupied`）。
- 新增 `load_capacity_context(db, networks)`：**3 条**批量语句 B1/B2/B3（空页零语句短路）；B2 用 `LEFT JOIN` 保留零占用池并按 `network_id, start_address, id` 排序（AP-F039-2）。
- 新增纯函数 `allocatable_intervals_for(network, reserved)`；`network_allocatable_intervals()` 改为委托它（语句数不变）。
- 新增谓词构造器 `_undeleted_ips_in_range()`（network_id / `deleted_at IS NULL` / 闭区间地址上下界，端点接受字面量或 `ip_pools` 列），由 `_count_ips` 与 B1/B2/B3 共用 ⇒ 计数谓词单点（AP-F039-4）。
- `network_capacity()` / `auto_pools_capacity()` 增加 keyword-only `context`，仍是唯一公开容量入口；`context=None` 回退单对象取数（F010 端点签名与语句数不变）。
- `_capacity_block()` 是 `remaining = total − occupied`（不截断）的唯一计算点；区间算术仍只在 `subtract_intervals` / `intersect_with_range` / `allocatable_intervals_for`（AP-F039-3）。

`dashboard.py`：`_page_networks` 之后一次 `load_capacity_context`，行循环传 `context=`；`counts`、分页、`_clusters_for`、响应字段未改；模块内无地址算术（N2）。

## 2. A2 八项等价（B1/B2/B3 与 `_count_ips` 同谓词、同公式）
1. gateway 扣减 — `allocatable_intervals_for` 追加单点 `(gw, gw)` 排除。
2. RESERVED 过滤逐字一致 — B1 WHERE 与 `_reserved_pool_intervals` 相同三条件。
3. gateway∩RESERVED 不重复扣减 — `subtract_intervals` 天然去重，无新逻辑。
4. 未绑定 IP 计占用 — `_undeleted_ips_in_range` 无 `interface_id` 谓词（B2/B3 共用）。
5. 池外手动 IP 计 Network 占用 — B3 无池过滤（仅 network_id + deleted_at）。
6. AUTO 总量 = |池范围 ∩ 可分配集合| — `auto_pools_capacity` 对同一 `intervals` 调 `intersect_with_range`。
7. 池占用按当前地址 — B2 join 谓词 `address >= start AND <= end`，非 `ip_pool_id`。
8. INACTIVE 不清零 — 两路径均无 `status` 谓词。

实测：50 网络逐网络 `context` 路径 vs 单对象路径 **mismatches = 0**（含 29 个零占用池块在位；软删 IP / 软删 AUTO 池不计数）。
## 3. 验证命令与真实输出
```text
$ python3 -m compileall -q app/services/ip_capacity.py app/services/dashboard.py && echo compile-ok
compile-ok
$ ruff check app/services/ip_capacity.py app/services/dashboard.py
All checks passed!
$ python3 -m pytest tests/integration/test_dashboard.py -q
12 passed in 11.93s
$ python3 -m pytest tests/integration/test_f010_ip_capacity.py -q    # 该文件不存在（本轮 TD 未建）
no tests ran in 0.00s  -> 降级:
$ python3 -m pytest tests/integration -q -k "capacity"
9 passed, 1 skipped, 939 deselected in 10.58s    (skip = F016_ACCEPTANCE 未启用)
$ python3 -m pytest tests/integration/{test_f013_tester_acceptance,test_f016_acceptance,test_f027_access_scope,
    test_f028_acceptance,test_search_related_tester_acceptance,test_f030_test_harness}.py -q
33 passed, 5 skipped in 65.43s
$ python3 -m pytest tests/integration/{test_ip_addresses,test_f019_interface_ip_binding,
    test_f023_resource_interface_ip_import}.py -q
80 passed in 439.74s
$ git diff --stat -- backend/app/services/
 backend/app/services/dashboard.py   |   7 +-
 backend/app/services/ip_capacity.py | 264 ++++++++++++++++++++++++++++++------
 2 files changed, 231 insertions(+), 40 deletions(-)
$ git diff --stat -- docs/api docs/product docs/database frontend backend/alembic backend/app/api backend/app/models backend/tests
(空输出)
```

`K` **实测钉死 = 11**（常数 8 + B1+B2+B3）。临时探针（`/tmp`，未入库，`before_cursor_execute` 计 `SELECT` 前缀、`finally: event.remove`）在真 PG 16.15 / `csm_f039_impl_test`（1 Cluster + 50 Network ×〔1 RESERVED + 2 AUTO + 3–4 IP + 软删 IP/池〕）实测；基线在同一 PG 实例用 `/tmp/f039_base_impl`（`git archive f66d1f3`）独立解释器复测，探针库结束时 `DROP`（无残留）。

| N (`page_size`) | 实现后 `q_svc` | 基线 `q_svc`（f66d1f3） |
| --- | --- | --- |
| 1 | **11** | 14 |
| 10 | **11** | 68 |
| 50 | **11** | 308 |

主判据实测：`q_svc(1) == q_svc(10) == q_svc(50) == 11`，`11 ≤ 20` ✔。P 轴（AUTO 池 2→6）：实现后恒 `11` 且 `len(auto_pools)` 同步 2→6，基线 14/15/16/17（+1/池）。`load_capacity_context` 实际语句数 **3**，`context` 路径额外语句 **0**。F010 端点路径（无 context）实测 P=2/3/4 → 6/7/8 条 = `4+P`，与改动前一致（未被本次改动增加）。

## 4. EXPLAIN 摘要（真 PG，抓取实际执行的 3 条语句后 `EXPLAIN`）
- **B1**：`Index Scan using excl_ip_pools_network_id_address_range on ip_pools`；Filter `allocation_mode='RESERVED' AND network_id = ANY(...)`。
- **B2**：`Sort(network_id, start_address, id) → GroupAggregate(Group Key ip_pools.id) → Nested Loop Left Join`；外侧 `Index Scan using excl_ip_pools_network_id_address_range on ip_pools`；内侧 `Index Scan using uq_ip_addresses_cluster_id_address on ip_addresses`（`Index Cond: address >= start AND address <= end`，`Filter: network_id = ip_pools.network_id`）。
- **B3**：`GroupAggregate(Group Key network_id) → Sort → Index Scan using ix_ip_addresses_deleted_at on ip_addresses`（`Index Cond: deleted_at IS NULL` ×2，`Filter: network_id = ANY(...)`）。
- `SET LOCAL enable_seqscan = off` 后三条计划与原始计划**逐行相同**；`networks / ip_pools / ip_addresses` 无 `Seq Scan`。
- **回报（不阻塞）**：实际索引名与 `architecture §8` / `TD-F039-8a` 期望的 `ix_ip_pools_network_id` / `ix_ip_addresses_network_id` 不同（规划器选 GiST 排他索引 / cluster+address 唯一索引 / deleted_at 索引）。无退化、无需新索引（未触发 DATABASE Gate），但 TEST 断言须按真实计划对齐，请 Architect / TD 确认。

## 5. 未验证项
- TEST 阶段用例未编写/未执行：`test_f039_query_count.py`（A1a/1b、1c `q_http` 差值、2a/2b/2c 端点逐项等值与硬编码字面量、4a 负 `remaining`）与 `test_f039_scope.py`（A3 范围，`real_scope`）。本轮只做 service 级 `q_svc`、A2 service 等价与 EXPLAIN。
- HTTP 侧 `q_http` 与常数 `C` 未测；耗时/性能未测（无 benchmark，N7）；`F016_ACCEPTANCE` 整体验收仍 `BLOCKED / NOT TESTED`（需活动 HTTP 栈），不计 PASS。

## 6. 风险观察（AP-F039-1..6）
1. 仅以计数与 EXPLAIN 判定，未测耗时，不声称「优化慢查询」。
2. B2 显式 `ORDER BY` 生效（50 网络 auto_pools 顺序与 F010 逐项一致）；公式单点成立（`dashboard.py` 无区间运算，`remaining` 只在 `_capacity_block`）。
3. 谓词单点成立：B3 计划出现重复 `deleted_at IS NULL`（Session 软删过滤 + 显式谓词叠加），语义不变、无重复计数。
4. 小夹具下原始计划已是 index scan（未落 `Seq Scan`），force-off 计划相同 ⇒ 无索引退化判据成立；B1/B2/B3 为三次快照读，未改隔离级别、未宣称更强一致性（等价由 A2 覆盖）。
- 另：`architecture §1` 预估「F010 端点 4+P → 4」未发生（§2 要求端点签名与语句数不增）；降到 4 需改 `app/api/**`，本轮禁止且非契约面。

GIT: git status --short
GIT: git rev-parse --abbrev-ref HEAD
GIT: git rev-parse --short HEAD
GIT: git archive f66d1f3 backend | tar -x -C /tmp/f039_base_impl
GIT: git rev-parse f66d1f3:backend/app/services/dashboard.py f66d1f3:backend/app/services/ip_capacity.py
GIT: git diff --stat -- backend/app/services/
GIT: git diff --stat -- docs/api docs/product docs/database frontend backend/alembic backend/app/api backend/app/models backend/tests
GIT: git diff --stat
