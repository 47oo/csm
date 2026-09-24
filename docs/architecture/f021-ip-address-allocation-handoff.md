# Architecture Handoff — F021 IP 地址自动 / 手动分配

> Status: `READY FOR IMPLEMENTATION`
> Author Role: architect（协调器持久化）
> Date: 2026-09-21
> Feature: **F021 — IP 地址自动 / 手动分配**（E02，P1，`depends_on: [F020, F005, F004, F002]`，均 DONE）
> Product Source: `docs/product/handoffs/f021-ip-address-allocation.md`（`READY FOR ARCHITECT`）；`requirements.md` §12 **R-IP-005 ~ R-IP-010**（R-IP-001 ~ R-IP-004 不变）；`domain-model.md` §5.7 / §8 / §9；用户 2026-09-20 DEC-023 第 7~13 项裁定 + 2026-09-21 PR-01 裁定
> 依赖 ADR: `adr-0002`（数据库最终权威 / 无触发器）、`adr-0003`（标识与寻址 / 错误契约）、`adr-0004`（软删与唯一性释放）、`adr-0005`（认证）
> 同级权威（本 Feature）：`docs/api/f021-ip-address-allocation.md`（API Contract，Status = READY）；被修订契约：`docs/api/f005-ip-address.md` §10（两处非目标立场）

---

## Feature

IP 地址自动 / 手动分配：在 F020 已登记的某个 Cluster 的**活跃 IP 地址范围段（地址池）**之上，为**指定活跃 NetworkInterface** 创建一条绑定该 NIC 的**现有 IPAddress**。自动分配取该 Cluster 全部活跃范围段**并集**内**数值最小的未占用 IPv4**；手动分配要求输入为**合法 IPv4**、**数值落在某活跃范围内**且**未占用**（合法但非规范输入先规范化再写入，非法格式拒绝）。

- `layers = {database: false, backend: true, frontend: true}`
- `Contract = REQUIRED` → 本次落盘 `docs/api/f021-ip-address-allocation.md`，**Status = READY**
- 依赖 F020（范围段 / `ipv4.py` 纯函数）、F005（IPAddress / R-IP-001 partial unique / 受控 `cluster_id` 写入路径 / 软删立场）、F004（NIC）、F002（NIC→BareMetal→Cluster 推导链）

---

## Context

### 目标

把「选地址 + 建 IPAddress」从人工脑力活变成系统可判定、可重复、可并发安全的操作，**不引入第二套分配事实**、**不新增超出 R-IP-001 的唯一性**。

### 对现有系统的影响（已核实于 HEAD `07caa2f`）

- **已有**：`backend/app/ip_addresses/**`（CRUD、`derivation.py::derive_cluster_id` 单一受控推导、`repository.py::IpAddressRepository.create` 单一 `cluster_id` 写入点、`ux_ip_addresses_cluster_ip_active`）；`backend/app/ip_address_ranges/**`（`ipv4.py` 纯函数 `parse_ipv4` / `format_ipv4` / `extract_ipv4_for_guard`、`repository.py` 活跃读取、`deletion.py`）；`backend/app/deletion/service.py::soft_delete`（系统内**唯一**写 `deleted_at` 的路径）；`backend/app/common/sqlstate.py`（SQLSTATE 单一映射：`23505→409 DUPLICATE`、`23503→409 REFERENCE`、`23P01→409 OVERLAP`）；`backend/app/db/active.py`；migration head `0009_f020_ip_address_ranges`；前端 `IpAddressListPage.vue` / `IpAddressFormDialog.vue` / `api/ipAddresses.ts`；既有 guard 套件（`tests/test_ip_addresses_guards.py`、`tests/test_ip_address_ranges_guards.py`、`tests/test_structure_guard.py`、`tests/database/**`）。
- **不存在**：任何分配 / 预留实体、表、列、状态、端点，或分配前端入口；`ip_addresses` 无范围外键、无状态、无格式约束；`ip_address_ranges` 无分配列。
- **本次新增**：新模块 `backend/app/ip_allocations/**`（schemas / repository / service / router）；两个分配端点；契约 `docs/api/f021-ip-address-allocation.md`；F005 契约 §10 两处非目标精确修订；F021 静态 guard 新增 + 一处既有 guard 精确演进。
- **本次不修改**：`ip_addresses` / `ip_address_ranges` 的任何列 / 约束 / 索引 / 语义；`app/ip_addresses/**` 源码语义（仅 guard 测试的期望集合按新增合法调用点演进）；R-IP-001 ~ R-IP-004；`ip_address` 自由文本立场；F005 `POST /api/ip-addresses` 端点行为。

### 方案要点

1. **两个端点，新模块承载**：`POST /api/ip-addresses/allocate`（自动）与 `POST /api/ip-addresses/allocate-manual`（手动），由新模块 `app/ip_allocations/` 的独立 router 提供（P-01）。
2. **产物仍是 IPAddress**：成功 `201`，响应复用 F005 的 `IpAddressRead`（恰 5 字段，无 `cluster_id`）。
3. **单一写入路径**：分配选定地址后，经 `app/ip_addresses/service.py::create_ip_address` 落库——`cluster_id` 仍只由 `derive_cluster_id` 推导、只经 `IpAddressRepository.create` 写入。
4. **复用 F020 纯函数**：范围归属 / 规范化 / 枚举全部使用 `app/ip_address_ranges/ipv4.py`，**不复制第二份解析**。
5. **并发不新增约束**：以既有 `ux_ip_addresses_cluster_ip_active`（R-IP-001，predicate `deleted_at IS NULL`）为**最终权威**；不加新唯一索引 / 新维度列 / 触发器 / CASCADE；并发落败方返回既有 `409 CONFLICT + DUPLICATE`。
6. **无数据库变更**：不新增表 / 列 / 索引 / 约束 / migration（`database: false`）。

---

## Domain Impact

- **不新增领域对象**：分配**不是**独立领域对象，其唯一产物是一条现有 `IPAddress`（R-IP-005）。不存在分配 / 预留实体、表、列、状态、独立端点。
- **不新增资源关系**：仍为 `IPAddress → NetworkInterface`（N:1 必选）与 `Cluster 1─N IPAddressRange`；分配不建立新的持久关系。
- **不修改**任何既有领域对象、状态模型、唯一性规则：R-IP-001 ~ R-IP-004 原样不变；R-IP-005 ~ R-IP-010 为本次落地。
- **比较边界（R-IP-007）**：范围归属按 IPv4 **数值**；占用 / 唯一性按 `ip_address` **字面**。二者在实现中严格分层，不得混用。

---

## Data Layer Impact

**不需要任何数据库设计 / Schema 变更，`database: false`，无 migration。**

依据（逐项核实）：

- **表复用**：产物写入既有 `ip_addresses`；候选范围读取既有 `ip_address_ranges`。不新增表 / 列（无分配对象 / 分配时间 / 回收状态 / 保留地址 / 优先级列）。
- **唯一性复用**：R-IP-010 明确不得新增超出 R-IP-001 的唯一性；既有 `ux_ip_addresses_cluster_ip_active` 即最终权威，无需新索引。
- **索引足够**：分配的两条读取——活跃范围段 `WHERE cluster_id = ? AND deleted_at IS NULL`（走 `ix_ip_address_ranges_cluster_id`）与活跃占用字面 `WHERE cluster_id = ? AND deleted_at IS NULL`（走 `ix_ip_addresses_cluster_id`）——在已确认规模下无需新增部分索引；不引入「未来可能有用」的索引。
- **范围不重叠权威复用**：既有排他约束 `ex_ip_address_ranges_active_no_overlap` 保持不变，分配不写范围表。
- **无 migration**：migration head 仍为 `0009_f020_ip_address_ranges`（保持单一线性 head）。**明确否定**为「可能未来需要」而预建分配表 / 列。
- requirement：`project-plan.yaml` `features[F021].layers.database` 由初步 `true` 定稿为 **`false`**。

---

## Backend Work

新增 `backend/app/ip_allocations/**`（`__init__.py` / `schemas.py` / `repository.py` / `service.py` / `router.py`），并做一处既有集成。

1. **请求 schema（`schemas.py`，`extra="forbid"`，字段封闭）**
   - `IpAddressAutoAllocateRequest`：`{network_interface_id: int}`（恰 1 字段）。
   - `IpAddressManualAllocateRequest`：`{network_interface_id: int, ip_address: str}`（恰 2 字段）。
   - **响应 schema 复用** `app.ip_addresses.schemas.IpAddressRead`（不新建响应类型；无 `cluster_id` / `status` / `deleted_at`）。
   - **不在 Pydantic 层约束 IPv4**（与 F020 一致）：`ip_address: str` 不做 pattern / 长度 / trim，由 service 用 `parse_ipv4` 裁决并给出 `details[].field`。
2. **数据访问（`repository.py`，纯只读）**
   - `list_active_ranges(session, cluster_id) -> list[tuple[int, int]]`：`select(IpAddressRange.start_ip, IpAddressRange.end_ip).where(active_filter(...), cluster_id==).order_by(start_ip)`。
   - `active_ip_literals(session, cluster_id) -> set[str]`：`select(IpAddress.ip_address).where(active_filter(...), cluster_id==)`。
   - 经 `app/db/active.py` 的 `active_filter` 表达活跃；**无任何写入方法**。
3. **领域服务（`service.py`）**
   - `allocate_ip_auto(session, payload)`：
     1. `cluster_id = derive_cluster_id(session, payload.network_interface_id)`；未命中 → `404 NOT_FOUND`。
     2. `ranges = repository.list_active_ranges(cluster_id)`。
     3. `occupied = repository.active_ip_literals(cluster_id)`。
     4. `candidate = select_first_free(ranges, occupied)`：按范围数值升序扫描，取第一个 `format_ipv4(v) not in occupied` 的 `v`；**不跳过**网络 / 广播 / 网关 / 端点。`candidate is None` → `ConflictError` + `details[].code = "NO_AVAILABLE_IP"`，**在任何写入之前**抛出。
     5. `return create_ip_address(session, IpAddressCreate(network_interface_id=..., ip_address=format_ipv4(candidate)))`。
   - `allocate_ip_manual(session, payload)`：
     1. `value = parse_ipv4(payload.ip_address)`；非法 → `400 VALIDATION_ERROR`，`details[].field = "ip_address"`、`code = "INVALID"`。
     2. `cluster_id = derive_cluster_id(session, payload.network_interface_id)`；未命中 → `404 NOT_FOUND`。
     3. 范围归属：`any(start <= value <= end for (start, end) in list_active_ranges(cluster_id))` 为假 → `ConflictError` + `details[].code = "OUT_OF_RANGE"`。
     4. `canonical = format_ipv4(value)`；`canonical in active_ip_literals(cluster_id)` → `ConflictError` + `details[].code = "DUPLICATE"`。
     5. `return create_ip_address(session, IpAddressCreate(network_interface_id=..., ip_address=canonical))`。
   - `select_first_free`：纯函数，输入已排序 `(start,end)` 与 `occupied` 字面集合，返回 `int | None`；不依赖 DB / HTTP。
4. **路由（`router.py`）**：`APIRouter(prefix="/ip-addresses", tags=["ip-address-allocations"])`，两个 `POST`，`status_code=201`，`response_model=IpAddressRead`。
5. **集成（唯一既有文件改动）**：`app/main.py` 导入并 `include_router(ip_allocations_router, prefix="/api")`（紧邻 `ip_addresses_router` 注册；两条 `POST` 静态路径不与 F005 的 `/ip-addresses/{ip_address_id}` 冲突，Starlette 优先完整匹配）。
6. **复用与禁止**
   - **复用** `derive_cluster_id`、`create_ip_address`、`app.ip_address_ranges.ipv4` 的 `parse_ipv4` / `format_ipv4`。
   - **不实现**：第二处写 `cluster_id`；任何写 `deleted_at` 的路径；新 SQLSTATE 映射；新唯一索引 / 触发器 / CASCADE；CIDR / IPv6 / 保留地址跳过；回收 / 审计 / 批量；对 `ip_addresses.ip_address` 的写入侧格式约束。
   - `app/ip_addresses/**` 与 `app/ip_address_ranges/**` 的**源码语义零改动**。

---

## Frontend Work

复用既有外壳（`IpAddressListPage.vue` / `IpAddressFormDialog.vue` / `api/ipAddresses.ts` / `ApiError` 分支）新增**分配入口与结果呈现**：

- **入口落点**：
  - `NetworkInterface` 上下文（NIC 详情 / NIC 限定的 `IpAddressListPage`，`networkInterfaceId` 已就绪）提供「自动分配 IP」与「手动分配 IP」两个动作；
  - `IpAddressListPage.vue`（全局）提供「分配 IP」入口，先选择目标 NIC（调用既有 `GET /api/network-interfaces` 选择器），再选自动 / 手动。
- **自动分配**：只发送 `{ network_interface_id }`；成功后刷新列表并在结果区展示新 `ip_address` 与 `id`。
- **手动分配**：发送 `{ network_interface_id, ip_address }`；输入框仅做**基础必填 / 类型**提示，**不做 IPv4 格式 / trim / 范围 / 占用预判**（§21；业务裁决全在服务端）。
- **三态**：
  - Loading：提交中禁用按钮 / 对话框，禁止重复提交；
  - Empty：分配动作的 Empty 即「尚未分配结果」，展示引导文案（与 Loading / Error 互异）；NIC 限定列表的 Empty 沿用既有语义；
  - Error：按 `error.code` 分支，必要时结合 `details[].code`，**不解析 `message`**。
- **错误分支（按稳定判别值）**：
  - `400 VALIDATION_ERROR` → 字段级提示（`details[].field`）；
  - `401 UNAUTHENTICATED` → 既有登录跳转；
  - `404 NOT_FOUND` → 「目标 NIC 不存在或已停用」；
  - `409 CONFLICT + details[].code === "NO_AVAILABLE_IP"` → 「该集群地址池已无可用 IP」；
  - `409 CONFLICT + details[].code === "OUT_OF_RANGE"` → 「该地址不在任何活跃地址范围内」；
  - `409 CONFLICT + details[].code === "DUPLICATE"` → 「该地址已被占用或并发冲突，可重试」。
- **不做**：客户端业务校验、客户端唯一性预检、客户端回填 `cluster_id`、禁用入口以「预防」服务端错误。

---

## API Contract

### Status

```text
READY
```

### Contract

完整契约正文：**`docs/api/f021-ip-address-allocation.md`**（Status = READY）。摘要：

| 端点 | Method | 用途 | 请求（封闭） | 成功 |
|---|---|---|---|---|
| `/api/ip-addresses/allocate` | `POST` | 自动分配（并集全局最小未占用 IPv4） | `{network_interface_id}` | `201` + IPAddress 表示 |
| `/api/ip-addresses/allocate-manual` | `POST` | 手动分配（范围内 + 未占用；规范化写入） | `{network_interface_id, ip_address}` | `201` + IPAddress 表示 |

资源表示（复用 F005，恰 5 字段，无 `cluster_id` / `status` / `deleted_at`）：

```json
{ "id": 41, "network_interface_id": 12, "ip_address": "10.0.0.5",
  "created_at": "2026-09-21T10:00:00Z", "updated_at": "2026-09-21T10:00:00Z" }
```

稳定错误判别值：

| HTTP | `error.code` | `details[].code` | 触发（本契约） |
|---|---|---|---|
| 400 | `VALIDATION_ERROR` | `INVALID` | 缺字段 / 非整数 / `null` / 非法 IPv4 / 未识别字段（含 `cluster_id`、`status`） |
| 401 | `UNAUTHENTICATED` | — | 未认证 |
| 404 | `NOT_FOUND` | — | NIC 不存在 / 已软删 / 宿主 BareMetal 不活跃 |
| 409 | `CONFLICT` | `NO_AVAILABLE_IP` | 自动：并集耗尽或无活跃范围段 |
| 409 | `CONFLICT` | `OUT_OF_RANGE` | 手动：合法 IPv4 不落在任何活跃范围段 |
| 409 | `CONFLICT` | `DUPLICATE` | 手动：范围内但已占用；或并发生成冲突落败方 |
| 500 | `INTERNAL_ERROR` | — | 未预期 |

F005 契约非目标修订（精确文本见附录 B），仅改两处立场；`ip_address` 自由文本立场不变。

---

## Test Work

Testing Agent 必须验证（至少）：

**契约与字段封闭**
- AC-01 ~ AC-33 逐条（认证 / 响应恰为 F005 表示 / 请求字段封闭 / NIC 必选且活跃 / Cluster 受控推导 / 漂移 0 / 自动并集全局最小 / 跳过已占用 / 规范化 / 无隐式保留地址 / 字面占用 / 字面不同不占用 / 软删释放 / 字面 vs 数值 / 跨 Cluster / 手动范围内成功 / 规范化 / 范围外拒绝 / 已占用拒绝 / 非法格式 400 / F005 不拦截 / 耗尽 / 无范围段 / 不新增唯一性 / 并发 / 最终权威 / 既有语义不变 / 边界 / 前端三态）。
- 成功响应字段集合**恰为** `{id, network_interface_id, ip_address, created_at, updated_at}`。
- 请求携带 `cluster_id` / `status` / `deleted_at` / `reserved_addresses` / 用途 / 分配对象等 → `400`，且**不产生记录**。
- 错误 `409` 的 `details[].code` 与契约逐字一致；`400` 的 `details[].field` 正确。

**自动分配**
- 多范围段 `[10.0.0.10,10.0.0.12]` + `[10.0.0.1,10.0.0.3]` → `10.0.0.1`。
- `10.0.0.1` 已占用 → `10.0.0.2`；范围 `[10.0.0.0,10.0.0.255]` 空缺 → `10.0.0.0`。
- 写入 canonical；无活跃范围段 / 并集全占用 → `409 NO_AVAILABLE_IP`，无新增行。

**手动分配**
- `010.0.0.5` → 写入并返回 `10.0.0.5`。
- 非法格式 → `400`，无写入；范围外 → `409 OUT_OF_RANGE`；已占用 → `409 DUPLICATE`。
- F005 `POST /api/ip-addresses` 对范围外字面仍 `201`。

**必须独立证伪项（绕应用层直连 DB / 真实并发线程 / 复用 R-IP-001）**
1. **直连 DB** 插入同 Cluster 两条活跃且字面相同的 `ip_address` → 必须抛 `23505`。
2. **直连 DB** 同 Cluster 插入字面不同但数值相同的两条（`010.0.0.1` 与 `10.0.0.1`）→ **均成功**（R-IP-007）。
3. **真实线程并发**两条自动分配 → 恰一条 `201`，另一条 `409 DUPLICATE`，无 5xx；结束时该字面活跃行 ≤ 1。
4. **真实线程并发**自动 / 手动选同一地址，或分配 × F005 登记 → 不变式同上。
5. **耗尽原子性**：填满范围后自动分配 → `409 NO_AVAILABLE_IP`，`ip_addresses` 行数前后不变。
6. **漂移查询为 0**；正常分配后新 IP 的 `cluster_id` = 其 NIC 宿主 BareMetal 的 `cluster_id`。
7. **范围覆盖**：正常路径下新分配 IP 数值落于该 Cluster 某活跃范围段内。
8. **结构证伪**：`information_schema` / `pg_indexes` / `pg_constraint` 证明**未新增**表、列、唯一索引、排他约束、触发器；`ip_addresses` 唯一索引集合仍恰为 `{ux_ip_addresses_cluster_ip_active}`。
9. **静态 guard 不减弱**：既有 F005 / F020 / 结构 / 迁移 guard 全量通过；断言 `cluster_id` **写入**位置仍唯一；`deleted_at` 写入仍唯一；端点集合/表集合仅按新增合法成员精确演进。
10. **新 F021 guard 可失败**（注入式复证）：端点面恰 2、请求 schema 封闭、分配模块零 `deleted_at` 写入 / 零 `IpAddress(cluster_id=...)`、`SQLSTATE_MAP` 键集合不变、migration head 仍 `0009`、复用 `app.ip_address_ranges.ipv4`（不出现第二份解析器）。
11. **契约一致性**：`docs/api/f021-ip-address-allocation.md` 落盘且 `Status: READY`；`docs/api/f005-ip-address.md` §10 两处已修订；无分裂（AC-29）。

---

## Technical Decisions

### CONFIRMED

- **C-01** 产物为一条现有 IPAddress；不新建分配 / 预留实体 / 表 / 列 / 状态（R-IP-005）。
- **C-02** 目标 NIC 必选且活跃；`NIC → BareMetal → Cluster` 受控推导；请求 / 响应无 `cluster_id`（R-IP-005）。
- **C-03** 自动取并集内数值最小未占用 IPv4；无隐式保留地址（R-IP-006）。
- **C-04** 已占用 = 同 Cluster 活跃且 `ip_address` 字面相同；软删释放（R-IP-007）。
- **C-05** 手动须合法 IPv4 + 数值落在某活跃范围 + 未占用；范围外仍走 F005 登记（R-IP-008）。
- **C-06** 耗尽返回非 500，不创建任何 IP（R-IP-009）。
- **C-07** 不新增超出 R-IP-001 的唯一性；`ux_ip_addresses_cluster_ip_active` 最终权威（R-IP-010）。
- **C-08** 手动非规范输入规范化后写入；非法格式不允许输入（R-IP-008；PR-01 A）。
- **C-09** 范围归属按数值、占用 / 唯一性按字面，不得混用（R-IP-007）。
- **C-10** 无数据库变更（`database: false`，无 migration）。

### REQUIRED

- **R-01** 分配写入必须经 F005 的**单一受控 `cluster_id` 写入路径**（`create_ip_address` → `IpAddressRepository.create`）；不得出现第二处写 `cluster_id`。
- **R-02** 写 `deleted_at` 的路径仍**唯一**为 `app/deletion/service.py::soft_delete`；分配不新增；释放唯一途径为 F005 `DELETE /api/ip-addresses/{id}`。
- **R-03** 唯一性最终权威必须是**数据库**约束（既有 R-IP-001 partial unique）；并发冲突 `23505` → `409 DUPLICATE`，**永不 500**。
- **R-04** 复用 `app/ip_address_ranges/ipv4.py` 纯函数；**不得复制第二份**解析器。
- **R-05** 请求 schema 必须 `extra="forbid"`；不得接受未确认字段。
- **R-06** 所有 `400` / `404` / `409` 情形**不得产生任何写入**（耗尽在任何写入之前判定）。
- **R-07** 不得修改 `ip_addresses` / `ip_address_ranges` 表结构、既有端点行为、R-IP-001 ~ R-IP-004、`ip_address` 自由文本立场；`SQLSTATE_MAP` 键集合不变。
- **R-08** 不得新增触发器 / `CASCADE` / 第二套 SQLSTATE 映射 / 新唯一索引 / 第二维度列。

### PROPOSED

- **P-01（端点形态）**：两个端点（`/allocate`、`/allocate-manual`），而非单一端点带 `mode`。理由：两者请求字段集合不同，分离可用 `extra="forbid"` 表达各自封闭集合，共享同一 service 写入路径与响应表示。
- **P-02（错误码）**：耗尽 `409 + NO_AVAILABLE_IP`；手动范围外 `409 + OUT_OF_RANGE`；手动已占用复用 `409 + DUPLICATE`；非法 IPv4 `400 + INVALID`；NIC 不存在 / 已删 / 宿主不活跃 `404 NOT_FOUND`；未识别字段 `400`。
- **P-03（并发实现）**：**不新增锁、不自动重试**。单请求事务内：`derive_cluster_id`（父 NIC 行 `FOR SHARE`）→ 读活跃范围段与占用字面（无锁快照）→ 选候选 → 经 `create_ip_address` 插入（partial unique 最终权威）。并发落败方 `409 DUPLICATE`。完全满足 R-IP-010。
- **P-04（模块边界）**：分配逻辑置于新模块 `app/ip_allocations/**`，不并入 `app/ip_addresses/**`。理由：① `app/ip_addresses/**` 有静态 guard 断言不得出现 `ip_address_ranges` / `parse_ipv4` / `extract_ipv4_for_guard`（G-F020-8），并入会破坏 F005 的隔离性；② 独立模块让 F005 / F020 guard 几乎原样保留。代价：`derive_cluster_id` 调用点由 1 处变为 3 处（只读推导调用点的增加，`cluster_id` 写入路径仍唯一）；对应 guard 需按**精确新集合**演进（不得放宽）。
- **P-05（读取范围 / 占用）**：一次性读入「活跃范围段列表 + 活跃占用字面集合」后在 Python 求最小候选。理由：已确认规模下扫描上界可接受；无新增索引需求。

### OPEN

- 见 Open Technical Questions（均 Non-blocking）。

---

## Risks

- **风险 1**：并发自动分配落败方得到 `409 DUPLICATE` 而非自动再取下一个。R-IP-010 / AC-25 明确允许；前端提示可重试。可选后续改进（TQ-1）。
- **风险 2**：Python 侧枚举候选，扫描上界为「Cluster 活跃占用数 + 范围数」；已确认规模内可接受。
- **风险 3**：耗尽判定的读快照竞态（读后并发软删）可能瞬时返回 `NO_AVAILABLE_IP`；可重试，不引入额外锁（R-IP-010 禁止新约束）。
- **风险 4**：`test_g9_derive_cluster_id_call_is_unique` 必须按完整新集合精确演进，不得放宽断言语义，否则削弱 `cluster_id` 写入路径保护。
- **风险 5**：若 F005 §10 未按精确文本修订，会出现「F005 契约禁止分配、F021 实现却有」。缓解：已给精确修订文本并落盘。

---

## Constraints

1. **不得**新增表 / 列 / 索引 / 唯一约束 / 排他约束 / 触发器 / `CASCADE`；**不得**新增 migration（`database: false`）。
2. **不得**出现第二处写 `cluster_id`；分配写入只能经 `app/ip_addresses/service.py::create_ip_address`。
3. **不得**新增写 `deleted_at` 的路径；释放唯一途径为 F005。
4. **不得**复制 IPv4 解析 / 规范化实现；必须复用 `app/ip_address_ranges/ipv4.py`。
5. **不得**修改 `app/ip_addresses/**` 与 `app/ip_address_ranges/**` 的源码语义；F005 `POST /api/ip-addresses` 行为不变；`ip_address` 自由文本立场不变（格式拒绝**仅**作用于分配路径）。
6. **不得**修改 `common/sqlstate.py` 的键集合。
7. **不得**在分配中对既有 `ip_address` 字面做归一化 / trim / 折叠；占用判定按字面。
8. **不得**实现 CIDR / IPv6 / 保留地址跳过 / 回收工作流 / 审计 / 批量 / DHCP / DNS / 外部同步。
9. **不得**在客户端实现 IPv4 校验 / 范围 / 占用 / 唯一性预检（§21）。
10. **静态 guard 只增勿弱**：允许按新合法成员**精确演进**期望集合，禁止放宽为子集 / 前缀 / 包含式断言；`cluster_id` 写入路径 guard 与 `deleted_at` 写入路径 guard 的期望值不得改变。
11. 契约一致性：`docs/api/f021-ip-address-allocation.md` 必须落盘且 `Status: READY`；`docs/api/f005-ip-address.md` §10 按附录 B 精确修订。

---

## Open Technical Questions

### Blocking

**无。**

### Non-blocking

- **TQ-1（自动分配是否需有界重试）**：当前不重试，落败方 `409 DUPLICATE`。未来可在不改契约（错误值不变）的前提下增加有界重试。不阻塞。
- **TQ-2（耗尽快照竞态）**：见风险 3。当前不消除；若要求与并发软删串行，属新增并发约束，需重评 R-IP-010 边界。
- **TQ-3（模块 / 端点命名）**：`app/ip_allocations/` 与路径 `/allocate`、`/allocate-manual`。命名属实现约定，不改契约语义。
- **TQ-4（手动范围外的状态码 409 vs 400）**：定稿 `409 + OUT_OF_RANGE`。若产品倾向 `400`，属契约取值调整；当前无此要求。
- **TQ-5（响应是否回显 Cluster 归属）**：定稿不回显（沿用 F005 表示）。聚合呈现归 F010。

---

## Implementation Layers

```text
database: false   # 复用 ip_addresses / ip_address_ranges；无新列 / 新索引 / 新约束 / migration（head 仍 0009）
backend:  true    # app/ip_allocations/** + main.py 挂载；复用 F005 写入路径与 F020 ipv4 纯函数
frontend: true    # 分配入口（自动 / 手动）+ 结果呈现 + error.code / details[].code 分支
```

分支范围：

- **database**：**无**（`project-plan.yaml` 的 `layers.database` 由初步 `true` 定稿为 `false`）。
- **backend**：新增 `app/ip_allocations/**`；`app/main.py` 追加导入与 `include_router`；新增 F021 guard；精确演进 `tests/test_ip_addresses_guards.py::test_g9_derive_cluster_id_call_is_unique` 的期望集合。不改其它模块源码。
- **frontend**：`ipAddresses.ts` 追加两个 API 客户端函数；新增分配对话框 / 动作组件并接入 NIC 上下文与全局 IP 列表；不改其它资源页面。

---

## Implementation Order

```text
Architecture + API Contract（本 Handoff + docs/api/f021-ip-address-allocation.md，Status READY）
  ├─ Frontend（仅需 READY 契约，可与 Backend 并行）
  └─ Backend（无需 Database Design：database=false）
        ↓ 所有必需实现分支完成
     Tester → Reviewer
```

- 无数据库分支，因此不存在「Database Design → Backend」等待链；Backend 与 Frontend 可直接并行。
- Frontend 的三态与错误分支由契约的稳定判别值确定，可先行。

---

## Verification Strategy

1. **契约验证**：两个端点的全部状态码 / `error.code` / `details[].code` 与契约逐字一致；响应 / 请求字段封闭。
2. **功能验证**：AC-01 ~ AC-33 逐条。
3. **约束证伪（绕应用层）**：直连 DB 重复活跃字面 → `23505`；数值相同字面不同可共存；证明无新增表 / 列 / 索引 / 约束 / 触发器。
4. **并发验证（真实线程）**：并发自动 / 手动 / 与 F005 竞争同一地址 → 至多一条 201，其余 `409 DUPLICATE`，无 5xx，最终活跃行 ≤ 1。
5. **不变式回归**：`cluster_id` 漂移 = 0；正常分配结果落在某活跃范围内；`deleted_at` 写入路径唯一。
6. **既有语义不变**：F005 / F020 全量测试与 guard 通过；`ip_addresses` 无新增格式约束；F005 契约仅按两处修订。
7. **静态 guard**：F021 新 guard 存在且可失败（注入式复证）；`cluster_id` 写入路径 guard 期望值未改变。
8. **迁移**：无新 migration；head 仍 `0009_f020_ip_address_ranges`。
9. **文档一致性**：F021 契约 `Status: READY`；F005 §10 修订已落盘。

---

## Handoff Status

```text
READY FOR IMPLEMENTATION
```

（API Contract Status = `READY`；无 Blocking Open Technical Question。）

---

## 附录 A — API 契约正文

见 `docs/api/f021-ip-address-allocation.md`（**单一权威**，本 Handoff 不重复）。

---

## 附录 B — `docs/api/f005-ip-address.md` §10 精确修订文本（已应用）

### B.1 修订一

**原文（删除）**（§10 第一条中段）：

> 本契约仍**不包含**：CIDR / 子网 / 网关 / 使用率统计 / 冲突扫描 / **IP 分配与回收工作流**（分配属 F021，当前 BLOCKED；F020 只做范围段管理，不含分配）。

**新文本（替换为）**：

> 本契约仍**不包含** CIDR / 子网 / 网关 / 使用率统计 / 冲突扫描。**受 Cluster 活跃范围约束的 IP 自动 / 手动分配**已由独立的 F021 特征交付，权威正文为 `docs/api/f021-ip-address-allocation.md`；分配**不新建**分配 / 预留实体，其唯一产物是一条由本契约资源表示描述的 IPAddress，且**不替换、不改版**本契约的 `POST /api/ip-addresses`。**IP 的回收没有独立工作流**：释放唯一途径是对本契约的 IPAddress 执行 `DELETE /api/ip-addresses/{ip_address_id}`（R-DELETE-006）。

同条末句保持不变：

> `ip_address` 的**自由文本登记立场不变**：范围段与分配能力的引入**不新增**对 `ip_address` 的格式校验 / 归一化 / trim。

### B.2 修订二

**原文（删除）**（§10 独立一条）：

> DHCP / DNS / 自动资产发现 / 外部平台同步 / 自动生成 IP（§23）。

**新文本（替换为）**：

> DHCP / DNS / 自动资产发现 / 外部平台同步 / **不受 Cluster 活跃范围约束**的自动生成 IP（§23）；受范围约束的自动分配见上一条（F021，权威正文 `docs/api/f021-ip-address-allocation.md`）。

> 说明：修订仅澄清「F005 端点本身不自动生成 IP，但 F021 的受范围约束分配作为独立能力存在」，消除「契约禁止、实现却有」的分裂；未改变 F005 的字段封闭集合、唯一性边界与 `ip_address` 自由文本立场。

---

## 附录 C — 需同步的产品 / 计划文档

- `docs/product/domain-model.md` / `docs/product/domain-model.yaml`：Product 已同步。
- `docs/project/v1/project-plan.yaml`：`features[F021].layers.database` 由初步 `true` 定稿为 **`false`**，并登记本次架构结论（由协调器执行）。
- 新增文档：`docs/api/f021-ip-address-allocation.md`、`docs/architecture/f021-ip-address-allocation-handoff.md`。
- 修订文档：`docs/api/f005-ip-address.md` §10（附录 B 两处）。