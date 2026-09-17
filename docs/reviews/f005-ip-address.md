# Review Report — F005 IPAddress 登记与管理

> Reviewer Role: reviewer（独立审查）
> Date: 2026-09-18
> Feature: F005（E02，P1，`depends_on: [F004]` = DONE）
> Feature Branch: `feature/F005-ip-address`
> Base Branch: `develop` @ `881ee230851c1234c705ac7e3367938f243e31ef`
> start_commit: `881ee230851c1234c705ac7e3367938f243e31ef`
> 已审查 HEAD: `01d91500a904935c44f7c3948be59fd8b9a22fb8`
> merge-base(develop, HEAD): `881ee230851c1234c705ac7e3367938f243e31ef`（与 start_commit、base 一致，祖先关系成立）
> Test Report: `docs/test-reports/f005-ip-address.md`（`READY FOR REVIEW`）

## Feature

IPAddress 管理（F005）— CSM V1 网络资源链的末端资源：IP 地址的人工登记、列表 /
详情 / 按 NIC 限定读取、`ip_address` 字面值修正与逻辑删除；**IPAddress →
NetworkInterface 必选绑定**落地；**Cluster 内 IP 唯一性**的保存前阻止（partial unique
index 为最终权威）；**`cluster_id` 受控推导与漂移归零**；以及 **F014 父删子拦**在
`NetworkInterface` 上的端到端。IPAddress **无状态、无 VRF / 命名空间、无 IP 池 /
DHCP / DNS / 自动发现、无格式校验与归一化、无多态父载体、`cluster_id` 请求侧永不
接受且响应侧不暴露**。

## Review Status

**CHANGES REQUIRED**

产品、架构、数据库、后端、前端与测试六个维度**均通过独立核验**（AC-01 ~ AC-42 全部
满足；`cluster_id` 单一写入点与漂移三件套经独立注入证明真实可失败；guard 演进为
「加强 / 仅移除已合法化 token」而非收窄），**但**发现一项由本 Feature 分支引入、
**超出 F005 范围**的破坏性文档编辑：`docs/project/project-plan.yaml` 中 **F004 的
open_questions（NQ-4 / NQ-6 / NQ-7）被 F005 内容覆盖**，并导致重复 YAML 键
（见 REV-1，MEDIUM）。该问题必须在 Merge 前由协调器修正。除此之外无 BLOCKER / HIGH，
其余为 LOW / NOTE。

**RETURN TO**：协调器（`docs/project/project-plan.yaml` 归属方）；REV-1 修正后可进入
Merge Gate，代码侧无需返工。

## Scope Reviewed

**独立复现的 Git 证据**

```text
git status --short                        → （空；工作区 clean，无未跟踪交付物）
git rev-parse HEAD                        → 01d91500a904935c44f7c3948be59fd8b9a22fb8
git rev-parse develop                     → 881ee230851c1234c705ac7e3367938f243e31ef
git merge-base develop HEAD               → 881ee230851c1234c705ac7e3367938f243e31ef（== base == start_commit）
git log --oneline develop..HEAD           → 8 提交
    01d9150 test(F005): independent acceptance confirms the drift checks bite
    512e92c chore(F005): record the implementation checkpoint
    6dadc73 feat(F005): implement ip address management
    542a18c docs(F005): define database design
    459929b docs(F005): record the three architecture-resolved questions
    ff05784 docs(F005): define architecture and API contract
    c9855d6 docs(F005): define requirements
    94bb02c chore(F005): initialize feature branch
git diff --stat develop...HEAD            → 48 files changed, 8722 insertions(+), 63 deletions(-)
git diff --cached --stat                  → （空）
git ls-files --others --exclude-standard  → （空）
git diff develop...HEAD -- 0001..0005     → （空；基线 migration 字节未改）
```

候选实现（`6dadc73`）、测试验收（`01d9150`）均已提交，工作区 clean、无未跟踪交付物，
Test Report 末节为 `READY FOR REVIEW`，满足正式 Review 的 Gate 前提，**非 PARTIAL REVIEW**。

**实际检查范围**

- 完整分支差异 `git diff develop...HEAD`（48 文件）：Backend（`app/ip_addresses/**`、
  `app/models/ip_address.py`、`app/models/__init__.py`、`app/network_interfaces/deletion.py`、
  `app/main.py`）、迁移 `0006`、测试（新增 IP API / 并发 / 一致性 / 约束 / schema guard /
  drift helpers + 既有 guard 演进）、前端（API 客户端 / 列表 / 详情 / 表单 / 删除 composable /
  `App.vue` / `NetworkInterfaceDetailPage.vue`）、契约 / 架构 / 产品 / 数据库文档、README、
  `project-plan.yaml`。
- 独立**重跑**关键测试与工程门禁（真实 PostgreSQL 16.2，临时实例 `/tmp/f005-rev-pgdata`，
  全新空库 `csm_rev`，非复用 Tester 结论；仓库未被改动，注入在 `/tmp/f005-rev` 副本内完成
  并逐字节还原）：
  - F005 专项：API `69 passed`、一致性 `6 passed`、并发 `4 passed`、guards `31 passed`、
    DB schema guard + constraints `23 passed`、migrations + schema `9 passed`。
  - 前端 F005 专项：`4 files / 73 tests passed`。
- 独立**直连 PostgreSQL 结构核查**（`information_schema` / `pg_constraint` / `pg_indexes`）：
  7 列 / 0 CHECK / 2 FK `RESTRICT`·`RESTRICT` / 恰 3 索引（1 partial unique
  `(cluster_id, ip_address) WHERE (deleted_at IS NULL)`）/ 无 COLLATE / 无触发器 /
  全库 0 CASCADE / head `0006_f005_ip_addresses`。
- 独立**对抗注入**（副本内，逐字节还原）：见「Test Review」与 Findings 证据。
- 独立**代码走查**：`derivation.py` / `service.py` / `repository.py` / `schemas.py` /
  `router.py` / `deletion.py` / `models/ip_address.py` / `migrations/0006` / 前端 F005 文件 /
  guard 演进 diff / `project-plan.yaml` diff。

## Product Compliance

**满足。** AC-01 ~ AC-42 逐项对照实现与测试，无 FAIL / BLOCKED / NOT TESTED。

- 登记：字段集合封闭恰 5 字段（无 `cluster_id` / `deleted_at` / `status` / VRF / 用途 /
  负责人，AC-01）；`ip_address` / `network_interface_id` 必填、非字符串 / 非整数 `400` +
  `details[].field`（AC-02/03）；父不存在 / 已删 `404`、无写入、非 5xx（AC-04）；绑定恰一
  个 NIC、schema 封闭、DB `NOT NULL` + FK `RESTRICT`（AC-05）；一个 NIC 多 IP（AC-06）；
  请求携带 `cluster_id` → `400` 且无记录（AC-07）。
- 唯一性：同 Cluster 跨 BM / 跨 NIC 重复 → `409` + `field=ip_address` + `code=DUPLICATE`，
  无第二条活跃记录（AC-08）；跨 Cluster 可重复（AC-09）；字面精确、IPv6 大小写可共存、
  无 `lower()` / 无 COLLATE（AC-10）；DB `23505` 最终权威、经单一映射 → `409` 永不 500、
  predicate 精确（AC-11）；格式规则**不实现**、空串 / 空白 / `not-an-ip` / 超长原样往返（AC-12）。
- 无状态 / 无 VRF / 无未确认字段（AC-13/14/15）；列表分页 Empty 200、详情 / 重复删除 404、
  按 NIC 的 Empty-vs-NotFound 可分、越界预置已删行排除（AC-16/17/18/19）。
- 维护：`ip_address` 修正 `200`、不可变字段不变（AC-20）；修正后重校验唯一性、无部分写入
  （AC-21）；PATCH 封闭、空 body / `null` → `400`、父绑定不可变（AC-22）。
- 删除与生命周期：`204` 行保留、软删释放唯一性、旧行不改写、不级联逐字段不变、无恢复 /
  批量 / `include_deleted`（AC-23/24/25/26）。
- F014 端到端：NIC 有活跃 IP → `409 ACTIVE_CHILDREN_EXIST` 且 NIC `deleted_at` 仍 NULL、
  软删后可删、链条 `Cluster→BareMetal→NIC→IP` 闭合、检查点非空且被真实消费、并发孤立记录
  0 行、创建侧父 NIC 行 `FOR SHARE`（AC-27~AC-32）。
- 推导与漂移：推导正确（AC-33）、漂移查询 0 行（AC-34）、反例证明检测有效（AC-35）、
  「漂移即唯一性静默漏洞」证明（AC-36）、`cluster_id` 写入路径唯一（AC-37）。
- 边界与前端：不越界 F009/F010/F011（AC-38）、无格式 / 无自动发现的结构性 guard（AC-39）、
  认证边界（AC-40）、前端三态 / Empty-vs-NotFound / `error.code` / 不重复业务守卫（AC-41）、
  不得预留未确认能力（AC-42）。
- **未越界**：无 `status` / VRF / 命名空间 / IP 池 / 网段 / DHCP / DNS / 自动发现 / 外部平台 /
  多态父载体 / `cluster_id` 可写 / 格式归一化字段、参数、分支或占位（含 `# TODO` 与不可达 `if`）。

## Architecture Compliance

**满足。** 13 项决策与 REQUIRED 全部落地。

- 5 端点封闭：`POST` / `GET` / `GET {id}` / `PATCH {id}` / `DELETE {id}`；`GET ""` 的
  query 参数恰为 `{page, page_size, network_interface_id}`（运行时断言 + OpenAPI 核实）。
- 资源表示恰 5 字段且**无 `cluster_id`**（决策 2 / NQ-4 裁定）：`IpAddressRead` 与 OpenAPI
  `IpAddressRead` 一致，请求侧 `extra="forbid"` 永不接受。
- `?network_interface_id=` 的 Empty-vs-NotFound：父不存在 / 已删 `404`、父存在但无活跃 IP
  `200 + items==[]`、非整数 `400`（决策 3 / NQ-6），与 F002 / F004 / F006 对称。
- 响应码：父不存在 / 已删 `404`；唯一性 `409` + `DUPLICATE`；缺字段 / 未识别字段 / 空 PATCH /
  `null` `400`；未认证 `401`（决策 4 / NQ-7）；`23505` / `23503` 均由既有单一映射处理、永不 500。
- 创建路径并发协议：`derive_cluster_id` 以**单条语句**沿
  `network_interface_id → network_interfaces.bare_metal_id → bare_metals.cluster_id` 推导，
  同语句对父 NIC 行 `FOR SHARE OF network_interfaces` 并确认父 NIC 与宿主 BareMetal 均活跃；
  **不额外锁定** BareMetal / Cluster（决策 7），未引入反向持锁。
- 「不实现」的结构性保障与交付面封闭由 G-1 ~ G-17 覆盖（见 Test Review）。
- 文档同步：`csm-v1-schema-design.md` 补 `0006_f005_ip_addresses` 版本号，并将「关键设计
  决策 #3 受控写入路径归属」由 F014 更正为 F005（规则未变，仅归属与会话落点），符合决策 1。

## Database Review

**通过。** 独立直连真实 PG 16.2 逐项核对，与 `docs/database/f005-ip-address-migration.md`
设计**逐项一致**：

- 列**恰 7 列**：`id`（bigint identity） / `network_interface_id`（bigint NOT NULL） /
  `cluster_id`（bigint NOT NULL） / `ip_address`（text NOT NULL） / `created_at` /
  `updated_at`（timestamptz NOT NULL DEFAULT now()） / `deleted_at`（timestamptz NULL）。
- **CHECK 集合为空**；`ip_address` 为 `TEXT` 且 `character_maximum_length IS NULL`、无列级
  collation。
- PK 恰 `pk_ip_addresses`；FK 恰 `fk_ip_addresses_network_interface` /
  `fk_ip_addresses_cluster`，**均 `confdeltype='r'` / `confupdtype='r'`**；全库 0 CASCADE。
- 索引恰 3 条：`ux_ip_addresses_cluster_ip_active`（UNIQUE，列序 `(cluster_id, ip_address)`，
  predicate 恰 `WHERE (deleted_at IS NULL)`，无 COLLATE / 无 `lower(`）+
  `ix_ip_addresses_cluster_id` + `ix_ip_addresses_network_interface_id`。
- 无触发器；无新 extension。
- Migration `0006_f005_ip_addresses`：`down_revision = 0005_f004_network_interfaces`；
  upgrade（建表 + 3 索引）/ downgrade（严格逆序）；`upgrade head` 幂等、可 `downgrade 0005`
  精确删除本表且既有 6 表完好、可重建；`alembic check` 无漂移。
- **`0001`–`0005` 字节未改**（`git diff` 为空）。
- `ip_addresses.cluster_id` 一致性**不由 DB 保证**（ADR-0002 已知取舍）如实记录，未以
  触发器 / 复合外键 / 生成列绕过。

## Backend Review

**通过。**

- API 层薄；Service / Repository 边界清晰：`derive_cluster_id`（推导 + 锁 + 活跃确认）→
  `active_ip_exists`（友好预检）→ `repository.create`（唯一写入）；读取一律经
  `active_filter` / `select_active`，无第二份 `deleted_at IS NULL` 谓词。
- 错误语义与契约一致；`23505` → `409` + `details[].code = "DUPLICATE"`（经 `sqlstate.py`
  单一映射，非另立映射），永不 500。
- `PATCH` 仅 `ip_address`，不触碰 `cluster_id` / `network_interface_id`；空 body / `null` → `400`。
- 删除委托系统内**唯一**软删路径 `soft_delete(..., active_children=IP_ADDRESS_ACTIVE_CHILD_CHECKS)`；
  `app/ip_addresses/**` 写 `deleted_at` 位置为 0。
- F014 接线：`NETWORK_INTERFACE_ACTIVE_CHILD_CHECKS = (has_active_ip_addresses,)`（追加，非替换），
  `BARE_METAL_ACTIVE_CHILD_CHECKS`（VM + NIC）与 `CLUSTER_ACTIVE_CHILD_CHECKS` 未削弱；NIC 删除
  路径经 AST 验证真实消费该常量。
- `app.ip_addresses.*` 不导入 `app.network_interfaces.*`（仅 `app.models.network_interface`），无循环导入。
- 无写副作用、无格式校验 / trim / 归一化方法。

**`cluster_id` 受控推导（本 Feature 最关键）— Reviewer 独立判定：通过。**

- 系统内**恰一处**推导函数 `app/ip_addresses/derivation.py::derive_cluster_id`。
- 系统内**恰一处**写入点 `app/ip_addresses/repository.py::IpAddressRepository.create`。
- `derive_cluster_id` **恰一处**调用点 `app/ip_addresses/service.py::create_ip_address`。
- 请求侧永不接受（`extra="forbid"`，携带 `cluster_id` → `400` 且无记录）；响应侧不暴露
  （`IpAddressRead` 恰 5 字段，OpenAPI 无 `cluster_id`）；`PATCH` 前后 `cluster_id` /
  `network_interface_id` 逐字节不变。
- 独立注入验证（在 `/tmp` 副本内，未改动仓库）：新增第二写入路径（`setattr(ip,"cluster_id",…)`）
  → `test_g9_cluster_id_write_path_is_unique` **FAILED**；新增第二调用点 → `test_g9_derive_cluster_id_call_is_unique`
  **FAILED**；在 IP 模块内新增第二处 `BareMetal.cluster_id` 读取 → `test_g9_cluster_chain_read_is_unique`
  **FAILED**；三种注入均逐字节还原后 guard 复绿。

## Frontend Review

**通过。**

- 严格使用契约端点与字段；`api/ipAddresses.ts` 字段封闭（无 `cluster_id`），不提供格式校验 /
  归一化 / 唯一性预检辅助。
- 列表页 `loading / empty / error / content` 四态互不相同；Empty（200 + `items==[]`）与
  Not Found（父 NIC `404` → Error 态）可区分；删除二次确认 + 提交中 Loading 防重复。
- 详情页独立 `not-found` 态；展示 5 字段；编辑仅 `ip_address`，`network_interface_id` 只读。
- 表单 `IpAddressFormDialog`：create = NIC 选择 + `ip_address` 文本；edit 仅 `ip_address`；
  **对 `ip_address` 无长度 / 空白 / 空串 / 格式 / 正则校验、无归一化**（提交按钮仅要求 create
  模式已选 NIC，非父存在性预判）；失败按 `error.code`（必要时结合 `details[].code`）渲染固定文案，
  **不解析 message**。
- 不重复实现业务守卫（空串 / 首尾空白 / 重复字面值均直接提交，由后端裁决）。
- 独立重跑 F005 前端专项：`4 files / 73 tests passed`。未引入新依赖、未引入 vue-router。

## Test Review

**可信。** Reviewer 不以「tests passed」为唯一判断，独立核验了测试自身的覆盖与判别力。

- **漂移检测三件套（T-34 / T-35 / T-36）真实、非 mock、非 vacuous**：
  - `DRIFT_QUERY` 与 AC-34 的 SQL **语义一致**（逐字采用，**不加 `deleted_at` 过滤**）；
  - T-35 / T-36 以**真实 raw psycopg** 绕过应用层写入反例（`conn.execute("INSERT …")`），非 mock；
  - 独立注入 A：把 `DRIFT_QUERY` 弱化为 `… AND ip.id < 0` → **T-35 / T-36 FAILED ×2**（证明非 vacuous）；
  - 独立注入 B：令 `derive_cluster_id` 返回 `cluster_id + 1` → **T-33（×2）/ T-34 / T-36 / T-37 FAILED**，
    而 T-35 仍通过（符合预期：raw 反例不依赖推导）；
  - 注入逐字节还原后三件套复绿。**判定：真实有效、未降级。**
- **guard 演进而非收窄（对比 base 逐行核对）**：
  - F009 `BOUNDARY_TOKENS`：**仅移除**已合法化的 `ip-address` / `ip_address`，保留
    `container` / `service`，**保持对全部 OpenAPI path 全局扫描**；
  - F002 `test_t29`：**仅移除**已合法化的 `ip` 前缀，保留 `nic` / `container` / `service` 全局覆盖；
  - F004 NIC `test_g7` / `test_g9`：由「断言两个 `ip` token 在集合中」演进为「断言二者**不在**集合中」，
    由 `NETWORK_INTERFACE_ACTIVE_CHILD_CHECKS == ()` / `"= ()"` 演进为「tuple 且**非空**且含
    `has_active_ip_addresses`」，并**保留** NIC 删除路径的 AST 真实消费断言；
  - F006 G-11 / NIC `test_g5` / `test_virtual_machines_guards` G-11：**仅更新 head 字符串**；
  - NIC `test_t30`：由「系统内无 IP 端点 / 无 `ip_addresses` 表」反转为「NIC 表 / schema 仍不携带
    IP 字段与 `cluster_id`」；
  - **无断言被净删除**：逐行核对 `git diff` 的被删行，仅为 head 字符串更新、已合法 token 移除、
    T-30 语义反转与 G-9 由空断言**加强**为非空断言；
  - 独立注入验证全局扫描未收窄：临时注册 `POST /api/vpns` 于 `main.py` → **`test_product_api_surface_is_closed` FAILED**；
    把 `ip-address` 加回 `BOUNDARY_TOKENS` → **F005 `test_g7` FAILED**（副本内，已还原）。
- **新增 allowlist `test_product_api_surface_is_closed` 为「加强」而非替换**：它对
  `/api/*` 的**首段**做 allowlist，较 `BOUNDARY_TOKENS` 的 denylist 更强，恰好补足了移除
  `ip` / `ip-address` token 后 denylist 失去的非 GET 越界路由覆盖；独立注入证实其可失败。
- 测试覆盖 AC-01 ~ AC-42 与 T-01 ~ T-42 / G-1 ~ G-17，错误路径与边界齐备；数据库断言
  绕过应用层直连 PG；并发测试使用真实线程 + 真实行锁（非 mock）。

## Findings

### REV-1

Severity:
MEDIUM

Layer:
Docs / Project Plan（协调器元数据）

Location:
`docs/project/project-plan.yaml` L526-541（F004 `open_questions` 的 NQ-4 / NQ-6 / NQ-7）；
重复键位于 L535-536（NQ-6 中出现两次 `resolved_by: architecture`）。

Problem:
本 Feature 的文档提交 `ff057842`（`docs(F005): define architecture and API contract`）在写入
F005 元数据时，**误覆盖了 F004 的 open_questions**：F004 的 NQ-4（「Other 是否需伴随自由文本 /
中文映射」）、NQ-6（「裁定为 F004 提供 `GET /api/network-interfaces?bare_metal_id=`」）、
NQ-7（「PATCH 可变字段集合固定为 `technology_type` + `purpose`」）三条 summary 被替换为
**F005 的内容**（`cluster_id` 不暴露 / F005 的按 NIC 路由 / F005 的响应码裁定），并在 NQ-6
产生**重复的 `resolved_by` YAML 键**。这是对无关 Feature 已确认记录的破坏性编辑。

Evidence:
`git diff develop...HEAD -- docs/project/project-plan.yaml` 的被删行恰为：
```text
-        summary: Other 是否需伴随自由文本 / 中文映射；R-NIC-001/002 已确认封闭集合且无伴随字段；默认不实现（PROPOSED-2）。
-        summary: 裁定为 F004 提供 GET /api/network-interfaces?bare_metal_id=（与 F002/F006 对称，不新增端点），F010 必须复用。
-        summary: PATCH 可变字段集合固定为 technology_type + purpose。
```
`git blame -L 526,541 docs/project/project-plan.yaml` 显示上述被改行来自 `ff057842`（F005 分支），
而非 base（`966c44ec`）。`git show develop:docs/project/project-plan.yaml` 的 F004 段确认原始文本。
现文件 L535-536 连续两行 `resolved_by: architecture`（重复键）。

Impact:
`docs/project/project-plan.yaml` 是项目当前执行状态的权威来源（`AGENTS.md` §4）。F004 已确认的
open-question 结论被静默替换为 F005 的内容，会误导后续 Agent（尤其 F010 / F011 等依赖
NetworkInterface 路由与 PATCH 字段集合上下文者）；重复 YAML 键为标准违规（宽松解析器取后者，
严格解析器可能报错）。属本 Feature 分支引入、超出 F005 范围的回归。

Expected:
恢复 F004 的 NQ-4 / NQ-6 / NQ-7 原文，删除重复的 `resolved_by` 键；F005 的裁定保留在 **F005 自身的
`open_questions`（L648-660）**中，不得写入 F004 段。修正后再确认 `project-plan.yaml` 可被 YAML
解析且无重复键。

Suggested Owner:
协调器（`docs/project/project-plan.yaml` 归属方）

### REV-2

Severity:
LOW

Layer:
Backend（注释 / 文档漂移）

Location:
`backend/app/network_interfaces/service.py` L103-105（`delete_network_interface` docstring）。

Problem:
docstring 仍称 `NETWORK_INTERFACE_ACTIVE_CHILD_CHECKS`「当前显式空元组」「F005 追加位置」，
而 `app/network_interfaces/deletion.py` 已演进为 `(has_active_ip_addresses,)`（非空）。消费者侧注释
未随实现同步（F005 已更新 `deletion.py` 自身 docstring，未更新该消费方 docstring）。

Evidence:
`backend/app/network_interfaces/service.py:104-105` vs
`backend/app/network_interfaces/deletion.py` 的
`NETWORK_INTERFACE_ACTIVE_CHILD_CHECKS: tuple[...] = (has_active_ip_addresses,)`。

Impact:
仅注释漂移，无功能影响（与 F006-T-03 同类）；Tester F005-T-01 已报告，Reviewer 复核**同意**，
Severity LOW 判定合理。

Expected:
更新该 docstring，使其描述 F005 起为非空且含活跃 IPAddress 检查。

Suggested Owner:
Backend

### REV-3

Severity:
LOW

Layer:
Test（静态 guard 覆盖缺口）

Location:
`tests/test_ip_addresses_guards.py::_cluster_id_write_locations`（L133 起）与
`test_g9_cluster_id_write_path_is_unique`（L395）。

Problem:
G-9「`cluster_id` 单一写入路径」静态断言仅识别三种形态：`IpAddress(... cluster_id=)` 关键字、
`setattr(obj, "cluster_id", …)`、`target.attr = …` 赋值。**不覆盖**诸如
`session.execute(update(IpAddress).values(cluster_id=…))` 的 ORM 形态，也不覆盖
`session.execute(text("UPDATE ip_addresses SET cluster_id …"))` 的裸 SQL 形态。因而「第二条
写入路径」可经这两种常见惯用法绕过该 guard 而不失败。

Evidence:
Reviewer 在 `/tmp` 副本内独立注入 `update(IpAddress).where(...).values(cluster_id=cid)` 与
裸 SQL `UPDATE ip_addresses SET cluster_id=…`，二者均**未**被 `-k g9` 检出（`4 passed`）；
注入前/后均逐字节还原。

Impact:
当前**实现**确无第二条写入路径（AC-37 在现网代码上成立），故非运行期缺陷；但 AC-37 所依赖的
「可失败静态 guard」并不穷举，存在被未来无意引入的第二写入路径绕过的残余风险。**漂移回归
（T-34）仍是真正的兜底**：任何产生漂移的第二写入路径会在 T-34 / T-35 / T-36 上暴露。

Expected:
可选加强：把写入路径判定扩展到 `update(...).values(cluster_id=…)` / `.values(dict)` 与裸 SQL
`SET cluster_id`；或明确记录该静态 guard 的已知边界，并依靠漂移回归作为一致性最终保障。

Suggested Owner:
Backend

### REV-4

Severity:
LOW

Layer:
Docs / Project Plan（协调器元数据）

Location:
`docs/project/project-plan.yaml` L561 `head_commit: 881ee230851c1234c705ac7e3367938f243e31ef`
（== `start_commit`）、`status: IN_REVIEW`、`implementation.test: COMPLETE`。

Problem:
F005 的 `git.head_commit` 仍等于 base / start_commit，未随实现与测试提交前进（实际 HEAD 为
`01d91500`）；`implementation.test` 标为 `COMPLETE` 而 `review: PENDING` 与 `IN_REVIEW` 一致，
但 `head_commit` 陈旧。

Evidence:
`grep -n head_commit docs/project/project-plan.yaml` → F005 L561 为 `881ee23…`；
`git rev-parse HEAD` → `01d91500…`。Tester「Unverified #5」已记录。

Impact:
元数据陈旧；不影响本次功能判定。历史先例（F004 Review `Non-blocking Follow-ups` #1、F006-T-02）
均按非阻塞处理。

Expected:
协调器在 Merge Gate 前后将 F005 `git.head_commit` 更新为已审查 HEAD、并填入 `merge_commit`。

Suggested Owner:
协调器

### REV-5

Severity:
NOTE

Layer:
Test / Docs

Location:
`docs/database/f012-baseline-migration.md` L182 小节标题为 `0005_f005_ip_addresses`（F005）
（应为 `0006_f005_ip_addresses`）。

Problem:
Tester F005-T-02 报告的 revision 号笔误。Reviewer 复核：该行由提交 `f3dbc6c` 引入，
**早于 F005 且不在本 Feature diff 内**（`git diff develop...HEAD` 未包含该文件）。

Impact:
纯文档，无功能影响；不属 F005 责任。

Expected:
作为独立文档修正跟进，不计入 F005。

Suggested Owner:
Database / 协调器（非 F005）

## Existing Defects

逐项独立复核 Tester 报告的 2 项缺陷：

- **F005-T-01（LOW，`delete_network_interface` docstring 仍称「显式空元组」）**：
  Reviewer 独立复现并确认存在（见 REV-2）。**同意** Tester 的 LOW 判定——纯注释漂移、无功能影响，
  不阻塞 Merge。Tester 的严重程度合理。

- **F005-T-02（LOW，`f012-baseline-migration.md` revision 号笔误，预存在）**：
  Reviewer 独立确认该笔误在 `f3dbc6c`（早于 F005）引入，**不在 F005 分支 diff 内**。**同意**其为
  非 F005 责任、LOW、非阻塞（见 REV-5）。Tester 未将其误归为 F005 缺陷，判定合理。

Tester 未报告 REV-1 / REV-3 / REV-4；它们是 Reviewer 独立发现的（REV-1 属本 Feature 引入的
超范围文档回归，是本轮唯一必须修复项）。

## Non-blocking Follow-ups

1. REV-1 修正后，协调器同步 F005 `git.head_commit` / `merge_commit` 与 `current_stage`。
2. REV-3：后续 Feature 可把 `cluster_id` 单一写入路径 guard 扩展到 `update().values(...)` 与
   裸 SQL 形态；在此之前，漂移回归（T-34 / T-35 / T-36）是一致性的最终保障。
3. REV-5：另起独立提交修正 `f012-baseline-migration.md` 的 `0005_f005` 笔误。
4. 新增 allowlist `test_product_api_surface_is_closed` 以「首段」判定，不覆盖已批准前缀下的
   嵌套未批准子路由（如 `/api/ip-addresses/pools`），denylist 亦不覆盖；当前无此路由，记录为残余边界。
5. 静态 guard 对运行期动态构造（动态 SQL / 动态路由）的穷举覆盖有限（承 F014 已知残余风险）。

## Unreviewed Areas

1. **浏览器级前端 E2E / 视觉 / 真实 DOM**：Reviewer 仅运行 vitest（happy-dom）组件测试与
   源码走查，未在真实浏览器观察渲染 / 网络 / 视觉。
2. **多 uvicorn worker / 跨进程并发压测**：Reviewer 独立复跑了单进程并发测试（真实 PG 行锁），
   未做多 worker 压测（无产品需求）。
3. **前端全量测试套件**：Reviewer 仅独立重跑 F005 专项 4 个 spec（73 tests）；未重跑全部 28 个
   前端文件（Tester 报告 380 passed，未由 Reviewer 全量复现）。
4. **后端全量测试套件**：Reviewer 独立重跑 F005 专项与 DB / migrations 相关测试；未重跑全部 686
   项（Tester 报告 686 passed 无 skip，未由 Reviewer 全量复现）。

## Reviewer 独立判定摘要

- **`cluster_id` 单一写入点：确认。** 系统内恰一处推导函数（`derivation.py::derive_cluster_id`）、
  恰一处写入点（`repository.py::IpAddressRepository.create`）、恰一处调用点
  （`service.py::create_ip_address`）；请求侧永不接受、响应侧不暴露、`PATCH` 不触碰。G-9 四条
  断言经**独立注入**（第二写入路径 / 第二调用点 / 第二链路读取）证明**真实可失败**并逐字节还原。
- **漂移三件套：确认真实有效、未降级。** `DRIFT_QUERY` 与 AC-34 SQL 语义一致且**不加
  `deleted_at` 过滤**；T-35 / T-36 使用**真实 raw psycopg 写入反例（非 mock）**；独立注入
  「弱化查询」→ T-35/T-36 失败，「推导返回错值」→ T-33/T-34/T-36/T-37 失败，证明其不 vacuous、
  不可被「改宽大」而失去判别力；漂移查询是 R-IP-001 的必需保障（T-36 证明漂移会使唯一索引在
  错误 Cluster 边界判断）。
- **数据库：通过。** 7 列 / 0 CHECK / 2 FK RESTRICT / 恰 3 索引（唯一索引列序与 predicate 精确、
  无 COLLATE / 无 `lower()`）/ 无 CASCADE / 无触发器；`0001`–`0005` 未改；migration 可重复、可
  重建、downgrade 逆序正确。
- **guard 演进：加强而非收窄。** 全 `/api/*` 全局扫描保持；新增 allowlist 为加强；
  F006-T-01 的收窄缺陷**未重犯**；对比 base 无断言被净删除。
- **唯一必须修复项：REV-1（MEDIUM）** —— F004 `open_questions` 被 F005 内容覆盖 + 重复 YAML 键，
  属本 Feature 引入的超范围文档回归。修正后即可进入 Merge Gate，代码侧无需返工。

GIT: NONE
