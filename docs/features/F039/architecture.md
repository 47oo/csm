# F039 Dashboard 容量查询批量化与查询计数基准（R10）— ARCHITECTURE + CONTRACT（合并定稿）

- **状态**：`READY FOR IMPLEMENTATION`（2026-10-29，Architect 专业签核；零业务规则、零契约、零 DDL，无需用户批准）
- **版本**：v1；分支 `feature/F039-dashboard-queries`（start_commit `f66d1f3`，交付线 `v3.4`）；plan revision 25 / requirements revision 16
- **上游依据**：`F039/product.md` v1（AQ-5=A；A1–A8/N1–N7/ON-1..5；无 Blocking Questions）；`F039/test-report.md` v1（TD-F039 `TEST DESIGN READY`，实测基线 `q_svc(1)=14 / (10)=68 / (50)=308`）；requirements §20/§23.2/§31 T32·T88；`docs/api/F013.md` **v2** §3.3/§3.5；`docs/database/f013-search-index.md` v1（DB-D124：不建 address 单列 B-tree）
- **layers**：`database=false`、`backend=true`、`frontend=false`；`api_required=false`

## 1. 方案摘要

`ip_capacity.py` 提升为「一次预取 + 纯函数装配」：新增 `CapacityContext` 与 `load_capacity_context()`（3 条固定批量语句）；`network_capacity` / `auto_pools_capacity` **保留为唯一公开容量入口**（薄包装，新增 keyword-only `context`）。`dashboard.py` 取页后调用一次预取，行循环复用上下文。§20 公式（区间减法/交集/`remaining = total − occupied` 不截断）仍是 `ip_capacity` 内单一实现，`dashboard.py` 不出现地址算术。

预估值（实现后待实测，**不得**作 PASS 依据）：`q_svc = 8 + 3 = 11`（N≥1；N=0 短路 → 8）；F010 容量端点 `4+P → 4`（响应不变、语句不增）。

## 2. ON-1 裁定：保留薄包装 + 预取上下文

```python
Interval = tuple[int, int]

@dataclass(frozen=True)
class CapacityContext:                       # 只读、按 network_id 索引
    reserved: dict[uuid.UUID, list[Interval]]
    auto_pools: dict[uuid.UUID, list[tuple[IPPool, int]]]   # (池, occupied)，保持 (start_address, id) 顺序
    occupied: dict[uuid.UUID, int]

def load_capacity_context(db, networks: Sequence[Network]) -> CapacityContext
def allocatable_intervals_for(network, reserved) -> list[Interval]              # 纯函数
def network_allocatable_intervals(db, network) -> list[Interval]                # 保留；改为取区间 + 纯函数
def network_capacity(db, network, *, context: CapacityContext | None = None) -> dict[str, Any]
def auto_pools_capacity(db, network, *, context: CapacityContext | None = None) -> list[dict[str, Any]]
```

- `context is None`（F010 `GET /networks/{id}/capacity` 既有调用点，签名不变）：回退到单对象取同一份数据，**只换数据来源不改口径**，端点响应与语句数不增。
- `context` 提供时两个包装函数**零额外语句**，装配与回退分支共用同一段代码（`allocatable_intervals_for` + 池总量交集 + `total − occupied`）。
- `dashboard.py`：`_page_networks` 后 `context = ip_capacity.load_capacity_context(db, networks)`，行循环传 `context=context`；`counts`、分页、`_clusters_for` 不改。
- **不改 `docs/api/F013.md` §3.3**（薄包装保持公式单点 ⇒ 契约零 diff）。新增返回容量的批量入口会需要 §3.3 澄清附注 ⇒ **否决**（N2）。`load_capacity_context` 只装载数据、不返回容量，不构成第二个公式出口。

## 3. ON-4：批量占用计数等价实现

`load_capacity_context` 发 3 条语句（`network_ids` 为空时短路、零语句）：

- **B1 RESERVED 区间**：`SELECT network_id, start_address, end_address FROM ip_pools WHERE network_id IN :ids AND allocation_mode='RESERVED' AND deleted_at IS NULL` → 按网络分组为区间。
- **B2 AUTO 池 + 占用（一条语句替代逐池计数）**：`ip_pools p LEFT JOIN ip_addresses ip ON ip.network_id=p.network_id AND ip.deleted_at IS NULL AND ip.address BETWEEN p.start_address AND p.end_address WHERE p.network_id IN :ids AND p.allocation_mode='AUTO' AND p.deleted_at IS NULL GROUP BY p.id ORDER BY p.network_id, p.start_address, p.id`。`LEFT JOIN` 保证零占用池出行；`excl_ip_pools_network_id_address_range` 保证同网络池区间不重叠 ⇒ 每个 IP 最多命中一个池、不重复计数。
- **B3 Network 占用**：`SELECT network_id, count(*) FROM ip_addresses WHERE network_id IN :ids AND deleted_at IS NULL GROUP BY network_id`（缺失按 0）。

A2 八项逐条保持（B1/B2/B3 复用与 `_count_ips` **同一谓词集合**；建议抽 `_undeleted_ips_in_range()` 供两路共用，防语义漂移）：gateway 扣减（内存字段 + 单点排除）、RESERVED 过滤逐字一致、gateway∩RESERVED 由 `subtract_intervals` 天然去重、未绑定 IP 计占用（无 `interface_id` 谓词）、池外手动 IP 计 Network 占用（B3 无池过滤）、AUTO 总量 = `|池范围 ∩ 可分配集合|`、池占用按**当前地址**不按 `ip_pool_id`、INACTIVE 不清零（容量路径无 status 过滤）。

**EXPLAIN 证据**：对 B1/B2/B3 在真 PG 记录原始计划，并追加 `SET LOCAL enable_seqscan = off` 证明存在索引路径（**network_id 前导索引**；实测规划器选择 `excl_ip_pools_network_id_address_range` 或 `ix_ip_addresses_network_id`，存在运行间漂移，判据为「`enable_seqscan=off` 下无 `Seq Scan` 且引用索引名存在于 `pg_indexes`」）。小夹具下规划器选 `Seq Scan` 属代价决策，**断言以 `enable_seqscan=off` 计划为「无索引退化」判据**，原始计划仅记录（Architect 对 TD-F039-8a 的解释性澄清）。

## 4. ON-2 / ON-3：计数口径与夹具（与 TD 一致）

`before_cursor_execute` 计 `SELECT` 前缀语句、`finally: event.remove`；`q_svc` 窗口不含认证与 §23.2 范围解析（范围侧用差值式 `q_http − q_svc == C` 中和）。主判据 `q_svc(1)==q_svc(10)==q_svc(50)`，`< =20` 为与规模无关的绝对封顶；**K 的最终字面量由实现轮实测钉死（上限 ≤20）**；若实测 >20 → 停止并回报，不得上调 K、不得写 `a + b·N`。P 轴 `q_svc(P=0..4)` 全等且 `len(auto_pools)==P`。N 轴用决定型 50 Network 夹具（无随机种子），`page_size ∈ {1,10,50}`。

## 5. ON-5：基线先行与复测

`git archive f66d1f3 backend | tar -x -C /tmp/f039_base` 属只读导出，**接受**。基线 14/68/308 已实测并以 blob 相等证明等价，留痕为 A1 对照；实现后同一 PG 实例、同一探针分别跑基线树（`PYTHONPATH=/tmp/f039_base/backend`，独立解释器）与工作树，记录 commit+blob+版本三元组；禁同树混跑、禁用估算值。

## 6. 契约结论：`NOT_REQUIRED`（零 diff）

不新建 `docs/api/F039.md`；`docs/api/F013.md` v2 零 diff。逐项：Endpoint/Method/Path/Query 无变化；响应 Schema 与 `counts` 五字段逐字不变；错误语义与 `401→403→422→200` 顺序不变；业务边界（无跨网络合计、软删不可见、INACTIVE 不清零、`remaining` 可负）未改判；分页/排序（`created_at DESC, id ASC`）与计数语句未改；认证与 §23.2 范围未改；软删过滤未改。唯一变化是单请求显式 SQL 次数与组织方式（非契约面）。

## 7. 与 TD 一致性

A1↔1a–1d、A2↔2a–2d、A3↔3a、A4↔4a、A5↔5a–5b、A6↔6a、A7↔7a、A8↔8a，无缺项。补充：`dashboard.py` 不得出现地址区间运算（源码级断言或 spy）作为 N2 机器证据。模块边界：`test_f039_query_count.py` **不得** import `app.core.access_scope`（`test_f030_test_harness.py` AST 守卫）；A3 置于 `pytestmark = pytest.mark.real_scope` 的 `test_f039_scope.py`。**F016 BLOCKED 处置**：`F016_ACCEPTANCE=1` 需活动 HTTP 栈（`httpx.ConnectError`）→ 记 `BLOCKED / NOT TESTED`，不计 PASS、不声称整体验收完成；T32/T88 由本地真 PG + TestClient 用例承载，不阻塞 F039。

## 8. Database：`NOT_REQUIRED`

无 DDL。现有索引足够：B1/B2 过滤 `ip_pools.network_id` → network_id 前导索引（`excl_ip_pools_network_id_address_range` 或 `ix_ip_pools_network_id`，规划器按代价选择）；B3 与 B2 join 侧过滤 `ip_addresses.network_id` → `ix_ip_addresses_network_id`；行按 PK。B2 的地址区间是 join 谓词，**不新增 address 索引**（DB-D124）。若 EXPLAIN 显示确需新索引 ⇒ 立即停止走 DATABASE Gate（N5）。

## 9. 风险

| ID | 风险 | 处置 |
| --- | --- | --- |
| AP-F039-1 | B2 单语句成本可能高于逐池小计数（时间退化），无实测耗时依据 | 只以 EXPLAIN 与查询计数判定；如需耗时另立 Benchmark；禁止表述「已优化慢查询」（N7） |
| AP-F039-2 | `auto_pools` 行序变化 ⇒ A5 顺序失效 | B2 显式 `ORDER BY network_id, start_address, id`；测试按 `id` 映射比较并单独断言顺序 |
| AP-F039-3 | 公式复制风险（预取层重算区间/交集） | 区间算术只留 `allocatable_intervals_for` / `subtract_intervals` / `intersect_with_range`；源码级断言 |
| AP-F039-4 | `_count_ips` 语义漂移（把池占用改成与可分配集合交集） | A2 以端点逐项相等 + 硬编码字面量双证 |
| AP-F039-5 | 小夹具 EXPLAIN 必倾向 `Seq Scan`，宽松正则会 FALSE PASS | 以 `enable_seqscan=off` 计划为判据并精确断言索引名 |
| AP-F039-6 | 多快照读（B1/B2/B3 三条语句）可能行内轻微不一致 | 不改隔离级别、不宣称更强一致性；响应等价由 A2/A5 覆盖 |

## 10. 实施层与分工

Backend（唯一实现层）：`backend/app/services/ip_capacity.py`（`CapacityContext`、`load_capacity_context`、`allocatable_intervals_for`、薄包装 `context` 参数、谓词构造器）、`backend/app/services/dashboard.py`（一次预取 + 行循环传参）。不得改路由/Schema/响应组装字段。Frontend 无（零 diff；A7 以 `git diff --stat` + `npm run typecheck` 为证据，UI 交互 `NOT_REQUIRED`）。Database `NOT_REQUIRED`。Test：`backend/tests/integration/test_f039_query_count.py`、`test_f039_scope.py`；基准与 EXPLAIN 证据落 `docs/features/F039/**`。Domain/Data：只读聚合视图，无关系/状态/唯一性/生命周期/审计影响。

## 11. 签核

```text
签核：Architect；日期 2026-10-29。
核对：product v1（A1–A8/N1–N7）、TD-F039 v1（A1–A8 全覆盖，基线 14/68/308）、F013 v2 §3.3/§3.5、requirements 16 §20/§23.2/T32·T88、现有索引与 DB-D124 → 设计/契约/数据/验证口径一致，无阻塞。
结论：READY FOR IMPLEMENTATION（仅 F039；不放行 F045 整体验收与 F016 验收）。
放行写入：backend/app/services/dashboard.py、backend/app/services/ip_capacity.py、backend/tests/integration/test_f039_*（TEST 阶段）、docs/features/F039/**。
零 diff 禁止：docs/api/**、docs/product/**、docs/database/**、frontend/**、backend/alembic/**、backend/app/api/**、backend/app/models/**。
待决/回报：K 的最终字面量（实测钉死，上限 ≤20）；EXPLAIN 若出现不可接受退化则停工走 DATABASE Gate。
绑定版本：product v1、TD-F039 v1、F013 v2、requirements revision 16。
```
