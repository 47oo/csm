# Architecture Handoff — F010 资源详情与关联查询

> Feature: F010（E05，P1，`depends_on: [F001~F008]` 均已 DONE）
> Author Role: architect ｜ Status: `READY FOR IMPLEMENTATION`
> Product Source: `docs/product/handoffs/f010-resource-detail.md`（`READY FOR ARCHITECT`，无 Blocking；BQ-1/BQ-2 已裁定「含间接」）、`requirements.md` R-QUERY-003（含「『与 BareMetal 相关』的确切含义」小节）/ R-QUERY-004、§15/§16/§21/§22/§23
> 配套契约: `docs/api/f010-resource-detail.md`（`READY`）

---

## Feature

在既有 canonical 过滤能力之上，交付一条**只读聚合读取**：`GET /api/bare-metals/{bare_metal_id}/related`，一次返回该 BareMetal 的五类关联（NIC / IP / VM / Container / Service），统一 404 / Empty 语义、软删过滤复用、固定深度（≤3 跳）推导与「不越界」可失败 guard。**不新增领域对象 / 字段 / 关系 / 状态 / 唯一性规则，无写路径，无 schema 变更。**

## 核心裁定

| # | 问题 | 裁定 | 理由 / 否决 |
|---|---|---|---|
| 1 | **NQ-5 聚合形态** | **(a1) 单一只读聚合端点** `GET /api/bare-metals/{bare_metal_id}/related` | 见下「裁定论证」 |
| 2 | 固定深度推导落点 | 后端聚合模块内**直线式组合**调用既有 canonical 过滤原语（≤3 跳），按 `id` 去重 | 见「推导与去重」 |
| 3 | 404/Empty 判定位置 | **单点**：先 `bare_metals.service.get_bare_metal_by_id`（未命中/已删 → 404），再派生五类 | 统一主体；已软删子资源经既有 canonical 过滤传递（内部走 `app/db/active.py`）；新模块**不得出现任何 `deleted_at` 表达式** |
| 4 | AC-18 成员集合深等 | 各清单**委托**既有 canonical 过滤函数；不做本地 FK / 软删谓词 | 见「复用义务」 |
| 5 | 前端接线与三态 | `BareMetalDetailPage` 内联「关联资源」区，一次请求获知五类 + 可进入详情；沿用 `ListStates` / `ErrorState` | Empty 不渲染为错误、不触发全局 401（http 层仅对 `UNAUTHENTICATED` 触发） |
| 6 | 边界 guard | 新增 `tests/test_resource_views_guards.py`（G-010-1~8）+ `EXPECTED_GET_ROUTES` **追加** | `BOUNDARY_TOKENS` 现为 `()`（deny-list 恒真）；**真正防线是 `APPROVED_API_PREFIXES` allow-list**。本端点首段 `bare-metals` 已在 allow-list 中 → **allow-list 不变** |
| 7 | layers | `database: false` / `backend: true` / `frontend: true` | 无 schema 变更；新增后端模块 + 端点；前端新增关联区与导航 |
| 8 | NQ-1 推导 Cluster 是否展示 | **不展示**（沿用 F006 NQ-7 / F007 AC-22 / F008 PROPOSED-2） | guard：新模块源码与响应 schema 不得含 `cluster_id` / `cluster_name`；无 Cluster 维度 query 参数 |

### 裁定论证（NQ-5）

**选定 (a1)。**

1. **Product Handoff 明确要求**五类 404/Empty 判定「须在**同一读取路径 / 事务内一致**」。只有后端单一读取路径能在结构上保证（B 活跃则五类必为 200；B 不存在/已删则整体 404）；前端多请求无法提供事务一致性。
2. **AC-10~AC-12 / AC-14 / AC-16 是 API + DB 可观察语义**；单端点使其可在项目既有「绕过应用层预置 `deleted_at`」测试范式中独立验证。AC-12 的反例（令某类为空不得诱发主体漂移）在单 B 网关下**结构上不可发生**。
3. **AC-17「一次获得」的最强形态**：一次请求、各清单在同一读取路径上派生并共用同一 404 网关（**不声称**严格一致快照，见 REQUIRED #5）。
4. **AC-18 由委托保证**：聚合只编排，不重写过滤。
5. **AC-22 不违反**：主体固定 BareMetal、关系类型封闭 5 类、深度固定 ≤3、无递归 / 图 / 邻接存储 / 关系配置入口；不存在「任意资源 → 任意资源」端点。
6. **与 F009 先例一致**：F009 亦新增一条只读端点。F004/F005/F006 曾以「与 canonical 对称、不新增端点」为由否决**每类一条嵌套路由**；本裁定为**单条组合端点**，不是五条子资源端点，故不构成那种「重复实现过滤」的越界（该点已列入 AC-22 guard：仅允许 `/related` 一条二段路径）。

**否决 (a2) 五个子资源端点**：把关系类型集合的实现从「一条组合」拆成五条路由，OpenAPI / 契约 / guard 面 ×5、快照不一致，且与 F004/F005/F006「拒绝每类嵌套路由」的直接结论冲突。

**否决 (b) 前端调用既有 canonical 读取并聚合**：① 与「同一读取路径 / 事务内一致」冲突；② IP / Service 无 B 直连 canonical 端点，前端必须自行编排 `NIC→IP` / `载体→Service` 多轮请求，AC-10/AC-11「五类分别成立」退化为**页面级**而非端点级，且无法以「绕过应用层预置软删」独立验证；③ 多请求无快照，并发软删下可自相矛盾（某类 404、其余 200）；④ 经核实 `?bare_metal_id=` 的 404 语义**确实成立**（`network_interfaces/service.py`、`virtual_machines/service.py` 均在父活跃检查未命中时 `raise NotFoundError()`），故 (b) 技术上可行，但一致性弱于 (a1)；⑤ 若选 (b)，`layers.backend = false`，AC-10/11 只能由前端组件测试（mock 404）+ 既有 canonical 后端测试间接验证。

### 推导与去重（固定深度 ≤3）

设 B 为存在且活跃的 BareMetal（先经 `get_bare_metal_by_id` 单点确认）：

| 类 | 推导（跳数） | 复用原语 |
|---|---|---|
| NetworkInterface | `NIC.bare_metal_id = B.id`（1 跳） | `NetworkInterfaceRepository.list_active` |
| IPAddress | 对 B 的每个活跃 NIC `N`：`IP.network_interface_id = N.id`（2 跳；**IP 无 `bare_metal_id`**） | `IpAddressRepository.list_active` |
| VirtualMachine | `VM.bare_metal_id = B.id`（1 跳） | `VirtualMachineRepository.list_active` |
| Container | `(BARE_METAL, B.id)` ∪ 对每个活跃 VM `V`：`(VIRTUAL_MACHINE, V.id)`（1~2 跳） | `ContainerRepository.list_active` |
| Service | `R(B) = {B} ∪ {B 的活跃 VM} ∪ {Container 相关集合}`；对 `R(B)` 每个载体取绑定并集（1~3 跳） | `ServiceRepository.list_active` / `list_active_services_by_carrier` / `carriers_for_services` |

- **去重**：Container 与 Service 在多载体并集后**按资源 `id`** 去重；NIC / VM 天然唯一；IP 归属唯一 NIC。
- **确定性顺序**：各类 `items` 按 `id` 升序（与 canonical 一致）。
- **完整快照**：聚合为非分页快照；须枚举**全部**匹配活跃行（在既有分页过滤上按 `total` 取全循环，或等价 canonical 读取），**不得静默截断**。
- **为何不是通用关系引擎**：无关系类型参数、无深度参数、无递归函数、无图 / 邻接结构、无关系配置入口；五条链路是写死的直线式组合，主体固定 BareMetal，关系类型集合封闭为 5。

## Domain Impact

**使用**已有领域对象（BareMetal / NetworkInterface / IpAddress / VirtualMachine / Container / Service / ServiceCarrier）。**新增 / 修改**领域对象、字段、关系、状态、唯一性规则：**无**。

## Data Layer Impact

**无 schema 变更。**

1. 全部读取委托既有 canonical 过滤原语与既有索引（`ix_bare_metals_cluster_id`、各 `*_bare_metal_id`、`ip_addresses.network_interface_id`、`service_carriers` 三个载体列索引等）；**不新增表 / 列 / 索引 / 约束**。
2. 活跃过滤统一经 `app/db/active.py`；新模块**不含任何 `deleted_at` 表达式**（ADR-0004）。
3. 不写入任何数据；不新增 migration；`0001`–`0008` 原样不变。

## Backend Work

新增 `backend/app/resource_views/`（对齐 `cluster_views/` 结构约定）：

1. `router.py`：`APIRouter(prefix="/bare-metals", tags=["resource-views"])`；**恰一条**路由 `@router.get("/{bare_metal_id}/related", response_model=RelatedResourcesRead)`；无请求体、无 query 参数。
2. `service.py`：`get_related_resources(session, bare_metal_id) -> RelatedResources`
   1. `bare_metals.service.get_bare_metal_by_id(...)` → 未命中 / 已删 → `NotFoundError`（**唯一 404 网关**）。
   2. 按上表推导五类；**只调用既有 repository / service 的 canonical 过滤函数**；不写 `deleted_at`、不写 FK 过滤新谓词；Container / Service 并集按 `id` 去重；全部 `id` 升序。
3. `schemas.py`：`RelatedSet[ItemT] = {items: list[ItemT], total: int}`；`RelatedResourcesRead` 字段**恰为** `network_interfaces / ip_addresses / virtual_machines / containers / services`，元素类型**复用**既有 `*Read`。
4. `app/main.py`：`include_router(resource_views_router, prefix="/api")`。

**明确不做**：不注册任何写 / 删除 / 恢复 / 解绑端点；不注册五个子资源端点；不新增字段 / 状态 / 关系 / `cluster_id`；不修改既有模块行为。

## Frontend Work

1. `frontend/src/api/bareMetals.ts`：新增 `getBareMetalRelated(id)`，类型 `RelatedResources`（五类，各 `{items,total}`，元素复用既有 Read 类型）。
2. `BareMetalDetailPage.vue`：新增「关联资源」区，展示五类清单，每条自带关系依据（NIC `bare_metal_id`；IP `network_interface_id`；VM `bare_metal_id`；Container `carrier_type`+`carrier_id`；Service `carriers`）；每类遵循 `ListStates`（Loading / Empty / Error），页面级 404 走既有 `not-found` 态（`ErrorState`，`code === 'NOT_FOUND'`）。
3. 导航：从关联条目进入 `network-interface-detail` / `ip-address-detail` / `virtual-machine-detail` / `container-detail` / `service-detail`（在 `App.vue` 增加事件；保留返回上下文）。
4. **三态可区分**：Loading（骨架）/ Empty（`el-empty`）/ Not Found（页面级 404）互不相同；Empty **不得**渲染为错误、不得触发全局 401。前端**不实现任何业务过滤 / 校验**，一律消费聚合端点。

## API Contract

Status `READY`；权威正文 **`docs/api/f010-resource-detail.md`**。仅定义 `GET /api/bare-metals/{bare_metal_id}/related`。

## Test Work

| # | 测试 | 层 | AC |
|---|---|---|---|
| T-10-01 | 构造 B（2 NIC、3 IP、2 VM、直接 + 间接 Container、B/VM/Container 三载体 Service），逐类断言成员集合、条目字段与关系依据 | API+DB | AC-01~AC-08 |
| T-10-02 | 含中文 / 特殊字符的 hostname / name / ip_address 字面往返 | API | AC-09 |
| T-10-03 | 不存在的 B、绕过应用层预置 `deleted_at` 的 B（关联数据仍在）→ 聚合 404 | API+DB | AC-10 |
| T-10-04 | 五类分别构造为空（B 活跃）→ 200 且对应 `{items:[], total:0}`；不得 404 | API+DB | AC-11、AC-12 |
| T-10-05 | 逐类绕过应用层预置已软删子资源 → 该类不含该条、其余不受影响 | API+DB | AC-14 |
| T-10-06 | 逐类 `DELETE` 后重查消失、其余类不受影响、B 字段不变 | API+DB | AC-15 |
| T-10-07 | 软删 B → 聚合 404（即使子行仍在） | API+DB | AC-16 |
| T-10-08 | **AC-18 深等**：对同一数据，聚合各类 `items` 的 `id` 集合 == 对应 canonical 端点成员集合并集（NIC / VM 单端点；IP 为各 NIC 并集；Container 为 B + 各 VM 并集；Service 为 `R(B)` 各载体并集按 id 去重） | API+DB | AC-18 |
| T-10-09 | 未认证 → 401，不返回数据 | API | AC-24 |
| T-10-10 | 非整数 `bare_metal_id` → 400 | API | 契约 |
| G-010-1 | `EXPECTED_GET_ROUTES` **追加** `/api/bare-metals/{bare_metal_id}/related`，既有成员全保留 | 静态 | — |
| G-010-2 | `resource_views` 路由集合恰 `{GET /bare-metals/{bare_metal_id}/related}` | 静态 | AC-22 |
| G-010-3 | 响应 schema 键恰五类；每类 `items` schema **等于**对应 canonical `*Read`；无 `deleted_at`/`cluster_id`/`status`/`state` | 静态 | AC-21、AC-23 |
| G-010-4 | 请求无 body；参数恰 `{bare_metal_id}`；无 Cluster / `include_deleted` / `carrier_*` 参数 | 静态 | AC-19、AC-21 |
| G-010-5 | `scan_deleted_at_writes(APP_DIR / "resource_views") == {}`；全局 allow-list 仍恰 `{backend/app/deletion/service.py}` | 静态 | AC-19、ADR-0004 |
| G-010-6 | 新模块源码无 `cluster_id`/`cluster_name`/`status`/`state`；无 `graph`/`recursive`/`recurse`/`traverse`/`topology`/`adjacency`/`networkx` 等 token；AST 无自递归函数 | 静态 | AC-21、AC-22、AC-23 |
| G-010-7 | OpenAPI 中 `/api/bare-metals/{bare_metal_id}/` 二段路径**恰为** `{.../related}` | 静态 | AC-22 |
| G-010-8 | `/api/clusters/...` 路径集合与 F009 一致（未新增 Cluster 视角） | 静态 | AC-20 |
| T-FE-10 | 关联区三态互不相同；Empty 不呈现错误、不触发全局会话失效；可从条目进入对应详情 | 前端 | AC-13、AC-17 |

## Technical Decisions

### CONFIRMED
- R-QUERY-003「与 BareMetal 相关」含间接（R(B) 定义）；R-QUERY-004 区分 404 / Empty。
- ADR-0003 §2/§3/§6、ADR-0004、ADR-0005。
- F002/F004/F005/F006/F007/F008 canonical 过滤语义，及「F010 必须复用、不得另写」义务。

### REQUIRED
1. 唯一 404 网关：先确认 B 存在且活跃，再做任何派生；不得由子资源判定诱发 404（AC-10、AC-12）。
2. 五类成员一律经既有 canonical 读取原语得到；新模块**不得**出现任何 `deleted_at` 表达式或第二份 FK / 活跃过滤谓词（ADR-0004）。
3. 深度固定 ≤3、直线式组合、无递归 / 图 / 关系类型参数（AC-22）。
4. Container / Service 多载体并集**按 `id` 去重**；各类输出按 `id` 升序。
5. 单一请求 / 单一 session（事务）内完成，使五类在同一读取路径上派生且共用同一 404 网关。
   **快照强度的准确表述（F010 REV-3 更正）**：默认隔离级别为 **READ COMMITTED**，同一事务内
   各语句**各自取快照**，因此并发软删期间各清单**可能瞬时不自洽**（不会产生错误的 404 / 500，
   但某类可能少一项）。原因是 ``_snapshot`` 在既有分页过滤上按 ``total`` 取全循环，
   并发写入下 offset 分页可能跳过行（重复行会被按 id 去重吸收，**跳过不会被吸收**）。
   本 Feature **不声称**严格一致快照；若产品要求该强度，需由 Architect 裁定是否改用
   ``REPEATABLE READ``——届时须重新评估锁与重试代价。读取不写数据，故无需加锁。
6. 响应元素 schema 复用既有 `*Read`（字段集合封闭）；无 `cluster_id` / 状态 / 位置 / 发现字段。
7. `EXPECTED_GET_ROUTES` **追加**（不替换）；新增 G-010 系列；`APPROVED_API_PREFIXES` allow-list 保留且**不需改动**（首段 `bare-metals` 已批准）。
8. 新路径位于 `/api` 前缀下，由 F013 中间件自动覆盖，不新增白名单。

### PROPOSED
1. 端点形态 = 单一聚合 `GET /api/bare-metals/{bare_metal_id}/related`（a1）。
2. 响应结构 = 五类，各 `{items, total}`；非分页快照。
3. 模块布局 = 新建 `backend/app/resource_views/`。
4. 契约落点 = `docs/api/f010-resource-detail.md`。
5. layers = `database: false` / `backend: true` / `frontend: true`。
6. 前端落点 = `BareMetalDetailPage` 内联「关联资源」区 + 进入各详情导航。

### OPEN（非阻塞）
1. NQ-1 推导 Cluster 归属：不展示。
2. NQ-2 反向视图：不交付。
3. NQ-3 状态 / 计数汇总：不实现（`total` 仅为成员数，非状态汇总）。
4. NQ-4 排序 / 筛选 / 导出 / 聚合分页：不实现；本轮为按 `id` 升序的完整快照。
5. NQ-6 VM 是否拥有独立 NIC：不假设。
6. 若未来单机关联规模显著增长需要聚合级分页：属加性扩展，需产品确认。

## Risks

| # | 风险 | 缓解 |
|---|---|---|
| R1 | 新模块被写成第二份软删过滤路径 | REQUIRED #2 + G-010-5 + 强制委托既有 canonical 原语 |
| R2 | 子资源 404 渗入导致 B 活跃时误判 404 | REQUIRED #1/#5：嵌套枚举使用**不抛 404 的 repository canonical 过滤**，仅 B 网关抛 404 |
| R3 | 聚合与 canonical 语义漂移 | REQUIRED #2 + G-010-3 + T-10-08 集合深等 |
| R4 | 被误解为「五个子资源端点 / 通用关系引擎」 | G-010-2、G-010-6、G-010-7 |
| R5 | `EXPECTED_GET_ROUTES` 被删旧换新 | REQUIRED #7 + G-010-1 |
| R6 | 聚合响应无界 | 单机关联基数小；已列为 OPEN #6 |
| R7 | 前端重复实现过滤 | 契约固定只消费聚合端点 |

## Constraints

1. 不新增 / 修改任何领域对象、字段、关系、状态、唯一性规则；不引入五类之外的资源类型。
2. 无 schema 变更：不改 `0001`–`0008`；不新增表 / 列 / 索引 / 约束 / 触发器 / CASCADE / migration。
3. 只读：无写 / 删除 / 恢复 / 解绑 / 批量端点或参数；不新增第二条 `deleted_at` 写入路径。
4. 不新增任何资源的 `cluster_id` 列或 Cluster 维度过滤参数（**尤其 `service.cluster_id`**）；不返回推导出的 Cluster 归属。
5. 不引入图数据库 / 通用关系引擎 / 递归或任意深度遍历 / 自动拓扑发现 / 关系配置入口。
6. 不为 NIC / IP / VM / Container / Service 新增状态字段或状态聚合；`BareMetal.status` 语义不变。
7. 不引入新框架 / 新依赖 / 新中间件 / `vue-router` / EAV / JSONB / ORM 多态 / STI / 通用表。
8. 既有 guard 只增不减；`EXPECTED_GET_ROUTES` 追加而非替换；保留 `APPROVED_API_PREFIXES` allow-list。
9. 新端点必须在 `/api` 前缀下；不新增认证白名单。

## Open Technical Questions

### Blocking

**无。**

## Implementation Layers

```text
database: false
backend:  true
frontend: true
```

- **database: false** — 无 schema 变更、无 migration（**Database Design 分支 NOT_REQUIRED**）。
- **backend: true** — 新增 `backend/app/resource_views/**`、`main.py` 挂载、`EXPECTED_GET_ROUTES` 演进、G-010 guard 与全测试集。
- **frontend: true** — `api/bareMetals.ts` + `BareMetalDetailPage` 关联区 + `App.vue` 导航 + 三态。

**文件所有权**：Backend = `backend/**` + `tests/**`；Frontend = `frontend/**`；`docs/**` 由协调器统一落盘。

## Implementation Order

```text
Architecture + API Contract（均 READY）
  ├─ Frontend（依契约并行）
  └─ Backend（resource_views 模块 → main.py 挂载
              → EXPECTED_GET_ROUTES 演进 + G-010 guard → 全测试集）
                 ↓ 所有必需实现分支完成
              Tester → Reviewer
```

`database: false`，故无 Database 分支；Backend 与 Frontend 可依契约**并行**。

## Verification Strategy

1. **契约层**：响应五类键与元素字段集合、`{items,total}`、`id` 升序、状态码、错误信封。
2. **语义**：AC-10（不存在 / 已软删 B → 404）、AC-11/AC-12（B 活跃五类分别空 → 200）、AC-14（绕过应用层预置软删子资源）、AC-16（B 软删）。
3. **深等**：T-10-08 逐类与 canonical 成员集合深等。
4. **边界 guard**：G-010-1~8。
5. **认证**：未认证 → 401。
6. **前端**：三态可区分、Empty 不触发全局 401、可从关联条目进入详情。
7. **工程门禁**：lint 干净；既有测试全绿；allow-list 不退化。

## AC 可实现性结论（AC-01~AC-25）

| AC | 可实现 | 说明 |
|---|---|---|
| AC-01~AC-03 | ✅ | 聚合对应类，委托 canonical |
| AC-04 / AC-05-a | ✅ | Container 直接 + 经 VM（AC-05-b 作废） |
| AC-06 / AC-07-a | ✅ | Service 直接 + 经 VM / Container；按 `id` 去重（AC-07-b 作废） |
| AC-08 | ✅ | 各 Read schema 自带关系依据 |
| AC-09 | ✅ | 复用 Read，无归一化 |
| AC-10~AC-12 | ✅ | 单 B 网关 → 五类一致；单端点 404 / Empty |
| AC-13 | ✅ | 前端三态 |
| AC-14~AC-16 | ✅ | 统一经 `app/db/active.py`，委托 canonical |
| AC-17 | ✅ | 一次请求 + 前端关联区 → 可入详情 |
| AC-18 | ✅ | 委托既有过滤；T-10-08 深等 |
| AC-19~AC-25 | ✅ | 只读、无 Cluster 视角 / 列、无通用引擎、无状态、认证、无越界 |

**全部 25 条（含生效的 `-a` 分支）均可实现，无需修改产品需求。** 本 Feature **不新增任何领域规则**；无新发现的、需用户裁定的歧义。

## Handoff Status

```text
READY FOR IMPLEMENTATION
```

无阻塞。API Contract Status = `READY`。

GIT: NONE
