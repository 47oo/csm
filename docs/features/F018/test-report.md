# F018 全局搜索字段组合展示 — Test Report

> 本文件同时承载 TEST DESIGN 与后续 TEST 结果；TEST DESIGN 仅表示方案可验证，不代表测试已执行或通过。

## Test Design

- **版本**：TD-1
- **日期**：2026-10-15
- **角色**：Tester（TEST_DESIGN 模式）
- **结论**：`TEST DESIGN READY`（TD-1）
- **依据**：
  - `docs/product/requirements-v3.md` revision 5（§17、§17.1、§18、§21、§22、§23、§28、§33、§35.1；T50–T53）
  - `docs/features/F018/product.md`（A1–A12、BQ1–BQ5 已确认、无 Blocking Questions）
  - `docs/features/F018/architecture.md`（DR-319–DR-331、§4 关联模型、§5 API 草案、§6 Database NOT_REQUIRED、§7 Test Work）
  - `docs/api/F013.md` v1（§1.1 信封、§1.2 错误码、§1.3 权限、§2 搜索响应/参数/去重排序/匹配、§4 软删、§5 只读；**待 CONTRACT Gate 修订为 v2**）
  - `docs/database/f013-search-index.md` v1（DB-D157–DB-D166；F018 `database=false` 沿用既有索引）
  - 现有实现/夹具：`backend/app/services/search.py`、`backend/app/schemas/search.py`、`backend/app/api/v1/search.py`、`backend/tests/conftest.py`、`backend/tests/integration/test_search.py`、`frontend/scripts/smoke-client.mjs`
  - `docs/project/handoff.md`、`docs/project/implementation-rules.md`、`.pi/skills/data-integrity/SKILL.md`

### 被测版本输入（TD-1 基线）

| 输入 | 版本 / 状态 | 说明 |
| --- | --- | --- |
| 产品需求 | revision 5（§17.1、T50–T53 已 CONFIRMED） | 验收权威来源 |
| Feature 验收 | `docs/features/F018/product.md` A1–A12 | 无 Blocking Questions；BQ1–BQ5 CONFIRMED |
| 架构设计 | `docs/features/F018/architecture.md`，DR-319–DR-331 | DR-320/321/322/323/327/329/331 CONFIRMED；DR-328 PROPOSED→CONTRACT |
| API Contract | `docs/api/F013.md` **v1（尚未修订为 v2）** | TD-1 采用 architecture §5 草案命名；TD-2 逐项核对 |
| Database 设计 | `database=false`，无交付物 | `docs/database/f013-search-index.md` v1 不改 |
| layers / api_required | `database=false`、`backend=true`、`frontend=true`、`api_required=true` | 与已批准计划一致 |
| 实现 | 尚未实现 | TEST_DESIGN 阶段正常状态 |

- **状态属性**：TD-1 `READY` 仅表示 A1–A12 已映射到可执行判据、边界/并发/生命周期场景已设计、真 PG 与夹具边界已建立。**不表示测试已运行、不填充执行 PASS、不批准实现或合并。**
- **不因 Contract v2 未定稿而 BLOCKED**：architecture §4–§5 已给出可执行的固定超集结构、排序全序、上限/总数、软删继承与前端 localStorage 回退。

### 复核基线（TD-2）

`docs/api/F013.md` 修订为 **v2 READY** 后，TD-2 逐项核对 `related`/`related_total` 的挂载位置、非 resource 行的 nullable 形态、`SearchResourceRelated` 子结构字段名、`interface_type` 枚举、`related_total` 类型，固定判据后 TD-1 方可作为 TEST 执行依据。

---

### 0. 数据完整性对应表（F018 范围）

F018 为**纯只读派生视图**：无写入入口、无新实体/关系/状态/权限/错误码、无 Schema/索引/迁移。

| 规则依据及版本 | 作用域/读取入口 | 数据库保证 | 业务层保证 | 并发/生命周期边界 | 验证 |
| --- | --- | --- | --- | --- | --- |
| §13/§14 IP 归属 | 关联行 Interface/IP/Network 一致性（`GET /api/v1/search`） | `ip_addresses.interface_id` FK；删除 Interface 需先处理未删 IP（RESTRICT） | 仅展示 `interface_id` 非空 IP（A8） | exclude 下活跃 IP 必指向活跃 Interface/Network | V4/V5/V8、B6/B9 |
| §21 未删默认 | 关联三对象过滤（随结果行 `deleted` 模式） | 默认 loader criteria 过滤 `deleted_at` | 按模式显式过滤；**不复用** `_build_items` 中无条件 `include_deleted=True` 的 loader（DR-323） | 软删即隐藏、恢复重现 | V7、B7–B9 |
| §4 稳定 ID | 关联行身份与排序 tiebreak | PK UUID（IPAddress `id`） | 行 `id` = IPAddress id；排序末键 `id ASC` | 改名不改 id | V2/V13、B5 |
| §22 只读 | 搜索 | 无写 | 无写端点、不写 Audit、幂等 | — | V10、B11/B12 |
| §17.1 确定性排序 | `related` 行序 | 无索引依赖 | `interface.name COLLATE "C"` → `inet` 数值序 → `id ASC` 全序 | 重复查询/分页稳定 | V2、B1–B5 |
| §17.1 上限/总数 | `related` ≤10 行 + `related_total` | 无 | 截断取前 10 并恒返回截断前总数 | — | V3、B4 |

---

### 1. 验收映射（A1–A12 ↔ T50–T53）

执行环境代号：`真HTTP` = ASGI + `TestClient`；`真PG集成` = 真HTTP + 真实 PostgreSQL；`真PG约束` = raw SQL / catalog / `EXPLAIN`；`机制级` = `frontend/scripts/smoke-client.mjs`；`前端组件` = Vite 构建 + 真实 API 集成；`静态` = 路由清单/源码检查。

| 验收 | 验证项 | 测试层 | 环境与数据 | PASS / FAIL 判据 |
| --- | --- | --- | --- | --- |
| **A1 / T50** | **V1** | 真PG集成 | Cluster→Resource（1 Interface、绑定 IP、Network）；`q` 命中 | PASS：resource 行含 `related[]`（interface{id,name,interface_type}、ip_address{id,address}、network{id,name}）与 `related_total`；字段集不随查询变化。FAIL：缺字段、字段集变化 |
| **A2 / T50** | **V2** | 真PG集成 + 真PG约束 | 多 Interface `eth2`/`eth10`；IP `10.10.1.9/10`、`10.10.2.1`；raw SQL 交叉核对 | PASS：行序 == `COLLATE "C"` 名称序 + `inet` 数值序；重复 3 次一致。FAIL：字符串序、依赖默认 collation、不稳定 |
| **A3 / T50** | **V3** | 真PG集成 | 单 Resource 11/23 个 IP | PASS：`len(related)==10`、`related_total==总数`、`≥`、无关联时 `[]`/`0`。FAIL：>10、缺总数 |
| **A4 / T51** | **V4** | 真PG集成 | 2 Interface × 各 2 IP | PASS：恰 4 行、`ip_address.id` 唯一、与已绑定 IP 一一对应。FAIL：漏行/重复/折叠 |
| **A5 / T51** | **V5** | 真PG集成 | 无 Interface；有 Interface 无 IP | PASS：`related==[]`、`related_total==0`，无占位/null 元素 |
| **A6 / T51** | **V6** | 真PG集成 + 机制级 + 前端组件 | `related_total=23` | PASS：服务端 10 行 + `related_total=23`；前端「还有 13 条」 |
| **A7 / T52** | **V7** | 真PG集成 | 软删 Interface/IP/Network；ADMIN + VIEWER；三模式 | PASS：`exclude` 隐藏；ADMIN `include/only` 显示；VIEWER `include/only`→403 `permission`；VIEWER 响应无已删关联 |
| **A8 / T52** | **V8** | 真PG集成 | `interface_id IS NULL` 的未删 IP | PASS：不出现在任何 `resource.related`；仍可 `type=ip_address` 命中 |
| **A9 / T53** | **V9** | 真PG集成（F013 回归） | 多类多页结果 | PASS：结果集/去重/顶层序/分页/`total` 与 F013 一致；仅新增字段；前端选择不产生额外参数 |
| **A10 / T53** | **V10** | 真PG集成 + 真PG约束 + 静态 | 搜索前后 `audit_logs`；重复调用；路由清单 | PASS：审计无变化；幂等；仅 `GET`；无新错误码 |
| **A11 / §17.1** | **V11** | 机制级 + 前端组件 | 九字段白名单；受控 localStorage | PASS：恰九字段；合法组合写入约定键并刷新读回；非法字段被过滤 |
| **A12 / §17.1** | **V12** | 机制级 + 前端组件 + 真PG集成 | 空选择 → 默认组合 | PASS：无偏好时展示 == F013 现有展示 |

补充：V13 固定超集不随字段/查询变化；V14 非 resource 行结构不变；V15 只读路由静态检查；V16 既有错误语义不变（401→403→422）；V17 `related_total` 与顶层 `total` 区分；V18 批量取数无 N+1。

---

### 2. 边界与并发 / 生命周期用例

| 编号 | 场景 | 环境 | 判据 |
| --- | --- | --- | --- |
| **B1** | 多网卡字节序 | 真PG | 行序 == `COLLATE "C"` 字节序；raw SQL 交叉核对 |
| **B2** | 多 IP 数值序 | 真PG | `10.10.1.9 < 10.10.1.10 < 10.10.2.1`（数值非字符串） |
| **B3** | 无 IP | 真PG | `related==[]`、`related_total==0` |
| **B4** | 超上限 >10 | 真PG + 机制级 | 23 行 → 10 行 + `related_total=23` + 「还有 13 条」；边界 10/11 |
| **B5** | 同 `(name,address)` tiebreak | 真PG | 经 `include` 构造；行序由 `ip_address.id ASC` 决定；否则 raw SQL 子句佐证 |
| **B6** | `exclude` 隐藏已删关联 | 真PG | 已删关联不出现，`related_total` 不计 |
| **B7** | `include`/`only`（ADMIN） | 真PG | 显示未删+已删，结构不变 |
| **B8** | 无 `VIEW_DELETED` | 真PG | VIEWER/EDITOR→403 `permission`；响应无已删关联 |
| **B9** | 未绑定 IP 不出现 | 真PG | `interface_id IS NULL` 的 IP 不出现在关联行 |
| **B10** | 中文与空格名称 | 真PG + 机制级 | 原样返回；`COLLATE "C"` 排序确定 |
| **B11** | 只读无审计 | 真PG约束 | `audit_logs` 前后不变 |
| **B12** | 重复调用幂等 | 真PG集成 | 响应一致、不改表 |
| **B13** | 展示字段不改结果集 | 真PG回归 | 去重/序/分页/`total` 不变 |
| **B14** | 前端组合无新参数 | 机制级 + 静态 | 请求 URL 仅 `q`/`type`/`deleted`/`page`/`page_size` |
| **B15** | localStorage 损坏/不可用/写失败回退 | 机制级 | 静默回退默认组合，不抛错、不阻断搜索 |
| **B16** | 「还有 N 条」计算边界 | 机制级 | ≤10 不显示；11→1；23→13；N = `related_total` − `len(related)` |
| **B17** | 非 resource 行不变 | 机制级 + 真PG | 展示不因字段选择改变 |
| **B18** | `related_total` 与顶层 total 独立 | 真PG + 机制级 | 分别呈现不混用 |
| **B19** | 恢复重现 | 真PG | 恢复后 `exclude` 下重新出现 |
| **B20** | 分页页内关联正确 | 真PG | 每页按页内 Resource 批量取数，不串页 |
| **B21** | `interface_type` 枚举 | 真PG | ∈ 权威七值，不改写 |
| **B22** | 未选择字段 = F013 展示 | 机制级 + 前端组件 | 与 F013 既有列一致；无额外请求 |

---

### 3. 真实 PostgreSQL 证据边界

仅以真实 PostgreSQL 为证据，SQLite/Mock 不作数：

1. 排序：`COLLATE "C"`、`inet` 数值序、末键 `id ASC`（B1/B2/B5）。
2. 软删过滤：三模式实际过滤效果（B6–B8、B19），断言未复用无条件 `include_deleted=True` loader。
3. 执行计划/无 N+1：单页对 interfaces/ip_addresses/networks 为常数条 IN 批量查询；`EXPLAIN` 命中既有索引 `ix_interfaces_resource_id`、`ix_ip_addresses_interface_id`、`networks` PK；正确性不依赖索引。
4. 审计无写入；`alembic heads` 不变、索引集合相对 F013 不新增。

---

### 4. 前端机制级验证

| 编号 | 判据 |
| --- | --- |
| F1 | 字段白名单恰九字段；未知字段被过滤 |
| F2 | 选择写入约定键（建议 `csm.globalSearch.fields.v1`，JSON 数组）并刷新读回 |
| F3 | 存储抛错/键缺失/JSON 损坏/未知字段 → 静默回退，不抛错、不阻断搜索 |
| F4 | 默认组合 == F013 现有列（A12） |
| F5 | 「还有 N 条」计算（≤10 不显示；11→1；23→13） |
| F6 | 字段选择仅作用 resource 行；其余行不变 |
| F7 | 字段选择不改变 `/search` 请求 URL/参数 |
| F8 | `related`/`related_total` 解析容忍缺失/null，回退安全展示 |

---

### 5. 环境、夹具与可观察结果

- 环境：真实 PostgreSQL 测试库（库名含 `test`，异于 `DATABASE_URL`；DB-D10 guard）；`alembic upgrade head`；后端 `pytest` + `TestClient`；前端 `npm run smoke:client`。
- 夹具：沿用 `conftest.py`（`pg_engine`/`committed_engine`/`auth_app`/`api_client`/`make_user`）与 `test_search.py`（`role_client_factory`、`_cluster`/`_resource`/`_network`/`_interface`/`_ip`/`_bind`/`_search`）。
- 新增 helper（Tester 范围）：单 Resource × N Interface × M IP；23 行超限；软删关联；未绑定 IP；同 `(name,address)` tie。
- 可观察结果：`resource.related[]` 行字段与顺序；`related_total`；非 resource 行形态；`audit_logs` 行数与内容；路由/参数清单；localStorage 键；「还有 N 条」文本；请求 URL。

---

### 6. 未决 / 待核对项

| 编号 | 类型 | 说明 | Owner |
| --- | --- | --- | --- |
| F018-TD-OPEN-1 | 非阻塞 | `docs/api/F013.md` 尚未修订为 v2：挂载位置、子结构字段命名、`related_total` 类型 | Architect（CONTRACT）→ TD-2 |
| F018-TD-OPEN-2 | 非阻塞 | 非 resource 行的 `related`/`related_total` nullable 形态（建议 `null`） | CONTRACT → TD-2 |
| F018-TD-OPEN-3 | 非阻塞 | `cluster` 展示形式（code 主/name 辅，DR-328 PROPOSED→CONTRACT） | CONTRACT → 前端判据 |
| F018-TD-OPEN-4 | 非阻塞 | localStorage 键名/编码与纯逻辑模块命名 | Frontend + CONTRACT → TD-2 |
| F018-TD-OPEN-5 | 非阻塞 | 同 `(name,address)` tie 可否经公共 API 构造 | Tester（TEST 阶段） |
| F018-TD-OPEN-6 | 非阻塞 | `interface_type` 枚举一致性 | 沿用 F007 |
| F018-TD-OPEN-7 | 非阻塞 | 前端字段选择器真实 API 集成是否本期必测 | Tester（TEST 阶段按范围判定） |

无 Blocking 项：`database=false` 无 Database Gate 阻塞。

---

### 7. 结论

`TEST DESIGN READY`（TD-1）。A1–A12 ↔ T50–T53 已逐条映射到可执行判据、测试层、环境/数据与 FAIL 判据；边界与生命周期用例、真 PG 证据边界、前端机制级验证已定义。

**READY 仅表示方案可验证，不代表测试通过、不批准实现或合并。**

## Test Execution

_（待 IMPLEMENTATION 完成后由 Tester 的 TEST 模式填充；当前未执行。）_