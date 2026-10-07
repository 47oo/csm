# F006 虚拟机登记 — Test Report

本文件同时承载 TEST_DESIGN 与 TEST（TEST 阶段在同一文件追加执行结果）。两阶段分别记录版本、结论与证据；TEST_DESIGN 不填充执行 PASS。

---

## Test Design

- **版本**：TD-1（当前）
- **日期**：2026-10-09
- **角色**：Tester（TEST_DESIGN 模式）
- **结论**：`TEST DESIGN READY`
- **依据**：
  - `docs/product/requirements-v3.md` revision 3（§4、§4.1、§6、§8、§9、§18、§21、§22、§23、§27、§31 T08/T09/T19/T23/T24/T25/T38/T39、§35.2 Q10-A、§35.3 D01）
  - `docs/features/F006/product.md`（PRODUCT `READY FOR ARCHITECT`，2026-10-09；A1–A17、I-1–I-4、明确排除项）
  - `docs/features/F006/architecture.md`（ARCHITECTURE `READY FOR DESIGN`，2026-10-09；§8 验证策略、DR-57–DR-70）
  - `docs/api/F004.md` v2（CONTRACT；F006 将扩展为 v3，**尚未定稿**）
  - `docs/database/f004-resource.md` v1、`docs/database/f005-bare-metal.md` v1（迁移 0004/0005 基座；F006 `f006-virtual-machine.md` **尚未建立**）
  - `docs/architecture/d01-conventions.md` v4（F006 将补 §5.5 升 v5，**尚未签核**）
  - `docs/features/F005/test-report.md`（TD-2/TE-1：fixture 模式、机制级口径、真实 PG/Compose 环境证据）
  - `docs/features/F004/test-report.md`（TD-2/TE-1：resources 基座、`_create_cluster`/`_create` 与约束断言模式）
  - `docs/project/project-plan.yaml` plan_revision 4，F006 条目
  - `docs/project/handoff.md`、`docs/project/implementation-rules.md`、`AGENTS.md`、`.pi/skills/data-integrity/SKILL.md`
- **状态属性**：READY 仅表示 A1–A17 可映射到可观察判据、边界/并发场景可执行、夹具与可验证性已与已确认需求/架构草案核对；**不代表测试已运行、不填充执行 PASS、不批准实现或合并**。F006 完整 §31 跨功能回归与 §32 上线验收不在本 Feature（见 §6）。执行结果见本文件 Test Execution。
- **前置状态说明**：DATABASE Gate（`docs/database/f006-virtual-machine.md`）与 CONTRACT Gate（`docs/api/F004.md` v3）**尚未定稿**，D01 v5 §5.5 尚未签核。本 TD-1 以 `architecture.md` §6/§7/DR-57–DR-70 的 Schema/契约草案为设计输入核对可验证性。TEST 执行前须以两 Gate 定稿逐项复核，差异处升 TD-2 并注明失效范围（见 §5、§8）。

### 版本记录

| 版本 | 日期 | 变更 |
| --- | --- | --- |
| TD-1 | 2026-10-09 | 初版：A1–A17 映射 V1–V20，边界/并发 B1–B36，夹具/环境设计，可验证性检查，不适用项；对 DATABASE/CONTRACT/D01 保留 10 项待复核假设（见 §8）。 |

> 复核基线（TD-1）：`docs/features/F006/architecture.md`（ARCHITECTURE Gate，`READY FOR DESIGN`，2026-10-09）。表名/约束名/FK/触发器/迁移/嵌套键名/错误路径/CONFLICT details 均以架构草案为准，标记为待 DATABASE/CONTRACT Gate 定稿闭合。

---

### 0. 数据完整性对应表（F006 范围）

仅列 F006 已确认且在实现后需验证的完整性/持久化项；方法依据 `.pi/skills/data-integrity/SKILL.md`。数据库列/约束以架构 §6 草案为准（待 DATABASE Gate 定稿核对）。

| 规则依据及版本 | 作用域/写入入口 | 数据库保证（草案，待 DB Gate） | 业务层保证 | 并发/生命周期边界 | 验证与证据 |
| --- | --- | --- | --- | --- | --- |
| §9 / §27（VM 必须关联未删 BARE_METAL 且同 Cluster） | POST/PATCH `/resources` 的 `virtual_machine.host_resource_id` | `host_valid` 触发器（host 须未软删 BARE_METAL 且 `host.cluster_id==vm.cluster_id`）；`host_resource_id UUID NOT NULL` | `validate_virtual_machine`：存在+未软删+BARE_METAL+同 Cluster，违约统一 422 `field:virtual_machine.host_resource_id` | 创建与换 Host 走同一校验函数；无超额校验 | V1/V2/V3/V4/V5/V15、B1–B11/B24；计划验证 |
| §9（resource_type 一致性） | POST/PATCH `/resources` | `type_match` 触发器（`resource_id` 须为 VIRTUAL_MACHINE） | 应用仅在 VM 创建/更新 detail；BARE_METAL 携带 VM→422 | 与硬件互斥；不改 resource_type（F004 触发器） | V1/V15/V17、B1/B24/B30；计划验证 |
| §4/D01 §1（稳定 UUID；1:1 依附） | POST `/resources` | `resource_id UUID PK` + FK→resources **ON DELETE CASCADE** | 每 VM 至多一行；随 Resource 创建 | 软删不物理删行；物理删除级联 | V4/V11/V15、B8/B22/B23/B25；计划验证 |
| §21（Host 引用删除保护；返回引用列表） | DELETE `/resources/{host_id}` | 无独立 DB 约束（应用引用检查 + `host_resource_id` FK RESTRICT 共同保证） | 注册 `resource←未删 VM` 反向检查器→409 `CONFLICT{reason:reference_exists, references:[{object_type:"resource",object_id,label}]}`；VM 软删后放行 | 未删 VM 阻止 Host 删除；无隐式级联 | V6、B12/B13；计划验证 |
| §21 / T24（恢复 VM 重检 Host；不覆盖新对象） | restore `/resources/{vm_id}` | 无独立 DB 约束（应用依赖检查器） | 注册 `resource` 依赖检查器：host 软删/缺失→409 `CONFLICT{reason:dependency_deleted, conflicts:[{object_type:"resource",object_id}]}` | 标识重用不覆盖新对象 | V12、B14/B15；计划验证 |
| §9（容量可空；未知 null 非 0；正整数/非负整数） | POST/PATCH `/resources` 的 `virtual_machine.{vcpu,memory_mb,disk_gb}` | `vcpu/memory_mb integer NULL CHECK 1..2147483647`；`disk_gb integer NULL CHECK 0..2147483647` | Pydantic 可选严格整数 + Service 校验；越界/0（vcpu/memory_mb）/负数→422 | 三字段各自独立可空、无跨字段规则、不与 Host 容量比较 | V7/V8/V15、B16–B19/B21/B26；计划验证 |
| §8/D01 §3（memory_mb=MiB、disk_gb=GiB；1 GiB=1024 MiB） | POST/PATCH `/resources`；界面展示 | 整数原样存储（不换算） | 应用不做 ×1000/÷1024 隐式换算；展示标注单位 | — | V9/V20、B20；计划验证 |
| §9/D01 §5.5（hypervisor trim/非空或 null/≤255；无枚举） | POST/PATCH `/resources` 的 `virtual_machine.hypervisor` | `varchar(255) NULL` + trim/非空 backstop | trim→非空或 null；空串/纯空白→422（不转 null）；≤255；无枚举、不据值推导 | 区分大小写、保留展示 | V15/V20、B27；计划验证 |
| §22（换 Host / 创建 / 删除 / 恢复写 Audit 同事务；回滚不留痕） | Service 层 `AuditService.record`（同 Session 同 commit） | 复用 `audit_logs` append-only | 快照白名单扩 `virtual_machine`（含 host_resource_id）；换 Host 记 UPDATE `before/after`；异常一起 rollback | 版本冲突无静默重试；并发一方成功 | V5/V19、B9/B33/B34；计划验证 |
| §23（读全角色；写 EDITOR/ADMIN；删除/恢复 ADMIN；乐观锁） | `/resources*` 各端点 | 复用 `resources.version`（detail 无 version） | `require_permission`；条件 UPDATE `WHERE version=:expected`；`rowcount=0`→409 | 两会话同 version 仅一成功 | V13、B34；计划验证 |
| §21 / DR-68（迁移回填；host 无安全回填值） | Alembic `0006_virtual_machine_details` | `host_resource_id NOT NULL`；无安全回填 → 前置守卫：存在未删 VM Resource 则 upgrade 中止 | 不静默丢弃/编造 detail；新写入路径强制 Host | 一期无生产数据；可干净升级 | V16、B28/B29；计划验证 |

---

## 1. 验收映射（product.md A1–A17 → 验证项）

执行环境：`Compose` = 干净环境 `docker compose up -d`（含 `migrate`/`bootstrap` 一次性服务）；`真实 PG` = 经 Compose `db` 或本机 PostgreSQL 的独立测试库（DB-D10，库名含 `test`）；`后端集成` = ASGI 应用 + 真实 PG 测试库（非 SQLite）；`静态` = 仓库/路由清单/源码静态检查；`文档` = 签核记录核对；`前端` = 构建 + client 机制级用例（与真实 API 集成时以入口 Nginx 为准）。

| 验收（product.md） | 验证项 | 执行环境 | 可观察判据（PASS / FAIL） |
| --- | --- | --- | --- |
| A1 创建 VM 时 host_resource_id 指向 VIRTUAL_MACHINE，被拒（422） | **V1**；**V15** DB 触发 | 后端集成 + 真实 PG | PASS：POST VM `virtual_machine.host_resource_id` 指向另一 VM → 422 `VALIDATION_ERROR`，`fields[].field="virtual_machine.host_resource_id"`；raw SQL 直插被 `type_match` 触发拒绝；库中无 detail 行。FAIL：创建成功、错误码非 422、无 DB 触发兜底 |
| A2 创建 VM 时 Host 与 VM 不同 Cluster，被拒（422） | **V2**；**V15** | 后端集成 + 真实 PG | PASS：Host 属 C2、VM 属 C1 → 422；Host 与 VM 同 Cluster 合法；raw SQL 直插跨 Cluster 被 `host_valid` 触发拒绝。FAIL：跨 Cluster 创建成功、无 DB 兜底 |
| A3 创建 VM 时省略/为空 host_resource_id，被拒（422） | **V3** | 后端集成 + 真实 PG | PASS：VM 缺 `virtual_machine` / `host_resource_id` 省略 / 显式 `null` / 空串 → 422；raw SQL 直插 NULL 被 `NOT NULL` 拒绝。FAIL：任一被接受、落库 NULL |
| A4 创建 VM 时 Host 不存在或已软删，被拒（422） | **V3**；**V15** | 后端集成 + 真实 PG | PASS：host 指向不存在 UUID → 422；host 指向已软删 BARE_METAL → 422（同字段语义）；raw SQL 直插软删 host 被 `host_valid` 拒绝。FAIL：不存在/软删 host 创建成功 |
| A5 创建 VM 时 Host 为未删除 BARE_METAL 且同 Cluster，成功 | **V4** | 后端集成 + 真实 PG | PASS：POST VM（合法 host）→ 201，响应 `virtual_machine` 对象含 `host_resource_id` 与 `host{id,hostname}`、容量/hypervisor 按入参；raw 断言 `virtual_machine_details` 恰一行且列值一致。FAIL：201 但无 detail 行、字段缺失、host 解析错误 |
| A6 同 Cluster 换 Host 成功，Audit 记 before/after host_resource_id；跨 Cluster/软删 Host 被拒 | **V5**；**V19** | 后端集成 + 真实 PG | PASS：PATCH `virtual_machine.host_resource_id` 换同 Cluster host → 200，响应新 host；UPDATE audit `before_data/after_data` 的 `virtual_machine.host_resource_id` 为旧/新值；跨 Cluster 或软删 host → 422 且库值不变。FAIL：无 audit、before/after 缺失、跨 Cluster 被接受 |
| A7 有未删 VM 引用时删 Host 被拒并返回引用列表；VM 软删后 Host 可删 | **V6** | 后端集成 + 真实 PG | PASS：DELETE Host（有未删 VM）→ 409 `CONFLICT{reason:"reference_exists"}`，`details.references` 含该 VM `{object_type:"resource",object_id,label}`；软删 VM 后 DELETE Host 成功（204）并写 DELETE audit。FAIL：Host 被误删、无 references、VM 软删后仍被拒 |
| A8 vcpu/memory_mb/disk_gb 省略或 null 保存 null，详情返回 null 不返回 0 | **V7** | 后端集成 + 真实 PG | PASS：POST VM 省略三字段 → 201 响应三字段 `null`；显式各字段 `null` 同样 `null`；raw DB 断言各列 `IS NULL`（非 0）；详情返回 `null`。FAIL：任一字段落库/返回为 `0`、字段缺失 |
| A9 vcpu=0 或负数被拒（422）；正整数接受；memory_mb 同规则 | **V8**；**V15** | 后端集成 + 真实 PG | PASS：`vcpu∈{0,-1}`、`memory_mb∈{0,-1}` → 422；正例 `vcpu=4,memory_mb=8192` → 201/200；raw SQL 直插同值被对应 CHECK 拒绝。FAIL：非法值创建成功、错误码非 422、DB CHECK 缺失 |
| A10 memory_mb 以 MiB 存/展：1536 GiB→1572864，转换一致，不按 MB 解释 | **V9**；**V20** | 后端集成 + 真实 PG + 前端 | PASS：登记 `memory_mb=1572864` 存/返回 `1572864`（不 ×1000/÷1024）；展示 `1572864 MiB（= 1536 GiB）`（1 GiB=1024 MiB）；`disk_gb` 同理按 GiB 原样。FAIL：存/返回被换算、按 MB 解释、单位标签缺失或错误 |
| A11 disk_gb=0 接受并存 0，展示「明确无磁盘」，与未知 null 可区分；disk_gb 负数被拒 | **V8**；**V9**；**V20** | 后端集成 + 真实 PG + 前端 | PASS：`disk_gb=0` → 201 存/返回 `0`；不传 → `null`；raw `=0` vs `IS NULL` 可区分；前端 0 显示「明确无磁盘」、null 显示未知占位（非 0）；`disk_gb=-1` → 422/CHECK 拒。FAIL：0 被拒或被转 null、null 写 0、负数被接受、前端同渲染 |
| A12 VM 总 vCPU/内存超 Host 容量时登记仍成功，不因超额被拒 | **V10** | 后端集成 + 真实 PG | PASS：Host 容量 `cpu_cores=16,memory_mb=32768`，建 VM `vcpu=64,memory_mb=262144` → 201；PATCH 提高容量亦 200；无容量准入/校验路径（静态核对无 Host 容量比较逻辑，§9/T39）。FAIL：因超额 422/409、引入容量准入 |
| A13 VirtualMachineDetail 无独立删除/恢复入口；删除/恢复 Resource 时明细跟随，明细不阻止其 Resource 删除 | **V11**；**V15** CASCADE 机制级 | 后端集成 + 真实 PG + 静态 | PASS：路由清单无 `.../virtual-machine`、`/virtual-machine-details` 等独立端点；软删 VM 后详情随 Resource 隐藏、restore 后容量/host 数据不变；物理删除 Resource（raw SQL）级联删除 detail 行（`confdeltype='c'`）；Resource 删除无 VM detail 反向检查阻止。FAIL：存在独立端点、明细阻止 Resource 删除、软删/恢复不同步、FK 非 CASCADE |
| A14 恢复 VM 重检 Host；Host 仍被删除或标识被重用时恢复失败且不覆盖新对象 | **V12** | 后端集成 + 真实 PG | PASS：VM 软删→其 Host 软删/删除→restore VM → 409 `CONFLICT{reason:"dependency_deleted"}`，`details.conflicts` 含 host `{object_type:"resource",object_id}`；VM 保持软删、库中无 detail 覆盖、新对象不受影响。FAIL：restore 成功、未重检 Host、覆盖新对象 |
| A15 权限：EDITOR 可创建/修改/换 Host；VIEWER 只读；删除/恢复限 ADMIN | **V13** | 后端集成 + 前端 + Compose | PASS：VIEWER POST/PATCH（含换 Host）→ 403 `FORBIDDEN{reason:permission}`、GET 200；EDITOR 创建/持久化/换 Host 201/200、DELETE/restore 403；ADMIN 成功；未认证 401；服务端强制（前端隐藏不替代，静态核对无绕过）。FAIL：越权成功、仅前端隐藏而服务端放行 |
| A16 Resource Detail 中 VM 展示其 Host；BareMetal Detail 列出其 VM | **V14**；**V20** | 后端集成 + 前端 | PASS：`GET /resources/{vm}` 响应 `virtual_machine.host{id,hostname}` 可供详情展示 Host；`GET /resources?type=VIRTUAL_MACHINE&host_resource_id=<host-uuid>` 返回该 Host 下 VM（分页/total 正确），非 UUID→422、不存在→空；前端 VM 详情展示 Host、BareMetal 详情 Virtual Machines 区域列出 VM。FAIL：host 未展开、列表过滤不生效、错误参数未 422 |
| A17 DB 层对 Host 类型及 Cluster 一致性有兜底约束，真实 PostgreSQL 验证 | **V15** | 真实 PG + 静态 | PASS：`virtual_machine_details` 表含 `type_match` 与 `host_valid` 双触发器；`host_resource_id NOT NULL` + FK RESTRICT + 索引；raw SQL 直插四类非法（VM 作为 host、跨 Cluster host、软删 host、非 VM resource_id）均被拒；合法插入成功。FAIL：缺触发器、约束未在真库生效、只由应用层保证 |

补充验证项（非直接 A 映射，但属实现后必须执行）：

| 验证项 | 内容 | 执行环境 | 判据 |
| --- | --- | --- | --- |
| **V17** 互斥 422 | BARE_METAL↔hardware、VIRTUAL_MACHINE↔virtual_machine 互斥 | 后端集成 + 真实 PG | PASS：POST/PATCH BARE_METAL 携带 `virtual_machine`（含显式 `null`）→ 422（不静默忽略）；VM 携带 `hardware`（含显式 `null`）→ 422；两对象不共存；raw 断言对应 detail 行不存在。FAIL：静默忽略、两 detail 行共存 |
| **V18** PATCH exclude_unset | `virtual_machine` 子字段级省略/显式 null | 后端集成 + 真实 PG | PASS：PATCH 仅含部分子字段时其余保持原值；显式 `null` 清空 nullable（vcpu/memory_mb/disk_gb/hypervisor）；显式 `null` host_resource_id → 422；整体 `null`/非对象/未知键 → 422。FAIL：省略被重置、显式 null 被忽略、host 显式 null 写 NULL |
| **V19** 审计同事务回滚 | VM 创建/换 Host 与 Audit 同事务 | 后端集成 + 真实 PG | PASS：注入失败使 commit 失败后，detail 列变更与 audit 行同事务双回滚，最终持久化状态为旧值/无新行（断言持久化状态，非仅未抛异常）。FAIL：audit 或 detail 半提交、回滚留痕 |
| **V16** 迁移 0006 + 回填守卫 | Alembic up/down/up + 回填 | 真实 PG | PASS：`alembic heads` 单一 head `0006_virtual_machine_details`（`down_revision=0005_bare_metal_details`）；up 建表→CHECK/PK/FK→索引→触发器/函数；down 逆序且 0005 对象保留；re-up 集合一致；回填守卫：存在未删 VM Resource 时 upgrade 明确中止并诊断，不合成/不丢弃 detail。FAIL：多个 head、不对称、无守卫或静默丢弃 VM |
| **V15** DB 约束/列集合（raw PG） | 表结构、CHECK、FK、触发器、索引 | 真实 PG | PASS：`resource_id` PK+FK CASCADE（`confdeltype='c'`）；`host_resource_id` NOT NULL+FK RESTRICT（`confdeltype='r'`）+ 索引 `ix_virtual_machine_details_host_resource_id`；容量 CHECK 上限；`hypervisor varchar(255)`；无 `deleted_at/version/created_at/updated_at`；无 VM 级 `metadata` 列（I-3 PROPOSED，若裁定为 VM 级则以定稿为准）。FAIL：约束类型/可空性不符、引入并发/软删/时间戳列 |
| **V20** 前端 VM 区域与状态 + 集成 | 表单/详情/单位/未知值/错误 | 前端 + Compose | PASS：Resource 创建/编辑表单 VM 显示 Host 选择器 + 容量/hypervisor；单位标注 MiB/GiB、未知「—」非 0、disk_gb=0「明确无磁盘」；Detail VM 展示 Host、BareMetal 列 VM；Loading/Success/Empty/Error 状态；携带 `version`，409 提示且不静默重试；422 点路径映射；经入口 Nginx 真实 API 往返。FAIL：状态缺失、未知伪装 0/空、409 静默覆盖、VM 渲染 Hardware 或反之 |

---

## 2. 边界与并发场景（B 编号，TEST 阶段执行）

| 编号 | 场景 | 步骤 | 判据 |
| --- | --- | --- | --- |
| B1 | host 类型错误 | POST VM `host_resource_id` 指向另一 VM；raw SQL 直插同 | 422 `field:virtual_machine.host_resource_id`；`type_match` 触发拒绝；无 detail 行 |
| B2 | host 跨 Cluster | Host 属 C2、VM 属 C1；raw SQL 直插同 | 422；`host_valid` 触发拒绝；库值不变 |
| B3 | host 不存在 | `host_resource_id` 传随机 UUID | 422（同字段语义）；无 detail 行 |
| B4 | host 已软删 | Host 软删后创建 VM；raw SQL 直插软删 host | 422；`host_valid` 拒绝 |
| B5 | host 创建省略/显式 null | 分别省略 `virtual_machine`、省略 host_resource_id、`host_resource_id:null`、`""` | 均 422；raw NULL 被 NOT NULL 拒 |
| B6 | host PATCH 显式 null | PATCH `virtual_machine:{host_resource_id:null}` | 422；库值/`version` 不变 |
| B7 | 合法 host 创建 | 同 Cluster 未删 BARE_METAL 作 host | 201；`virtual_machine_details` 恰一行、字段一致；响应含 `host{id,hostname}` |
| B8 | 1:1 依附 | 建 VM 后 raw 查询 detail；重复创建同 resource_id | 每 VM 至多一行（PK 保证）；无重复行 |
| B9 | 换 Host（同 Cluster）+ Audit | Host A→Host B（均 C1） | 200；detail.host_resource_id=B；UPDATE audit `before/after host_resource_id`=A/B；`object_type="resource"`、object_id=VM UUID |
| B10 | 换 Host 跨 Cluster | Host C2 换入 VM（C1） | 422；库值不变 |
| B11 | 换 Host 指向软删/不存在 | Host 软删后换入或不存在的 UUID | 422；库值不变 |
| B12 | Host 引用删除保护 | 删有未删 VM 的 Host | 409 `CONFLICT{reason:"reference_exists"}`；`details.references` 含 VM `{object_type:"resource",object_id,label}`；Host 仍存在 |
| B13 | VM 软删后 Host 可删 | 软删 VM 后删 Host | 204；写 DELETE audit；detail 行保留但随 VM 隐藏 |
| B14 | 恢复 VM 重检 Host（依赖被删） | VM 软删→Host 软删/删除→restore VM | 409 `CONFLICT{reason:"dependency_deleted"}`，`details.conflicts` 含 host；VM 保持软删、不覆盖 |
| B15 | 恢复 VM 标识重用 | VM 软删→同 hostname 重建新 VM→restore 旧 VM | 恢复失败（409 `unique_conflict` 或 dependency 语义，按 Contract）；新对象不被覆盖 |
| B16 | vcpu 边界 | `vcpu∈{0,-1}` 与 `1`/`2147483647`/`2147483648` | 0/负/超限→422；1..上限接受；raw CHECK 拒越界 |
| B17 | memory_mb 边界 | `memory_mb∈{0,-1}`、`1`、`2147483647`、`2147483648` | 同上；不按 MB 解释 |
| B18 | disk_gb 边界 | `disk_gb∈{-1}`、`0`、`2147483647`、`2147483648`、省略 | `-1`/超限→422；`0`→201 存 0；省略→null；raw `=0` vs `IS NULL` 可区分 |
| B19 | 容量省略/null | 三字段省略、显式 null、部分登记其余省略 | 已登记落值、其余 `IS NULL`（非 0）；响应一致 |
| B20 | 单位一致 | 登记 `memory_mb=1572864`、`disk_gb=100` | 原样存/返回；不出现 ×1000/÷1024；展示 `1536 GiB`/`100 GiB` 等价 |
| B21 | 超 Host 容量不拒 | Host 小容量，VM `vcpu`/`memory_mb` 超其值 | 201；无准入/拒绝路径（§9/T39） |
| B22 | detail 无独立端点 | 静态路由清单；请求 `.../virtual-machine`、`/virtual-machine-details` | 无独立删除/恢复端点；未定义路径 404/405 |
| B23 | 生命周期随 Resource | 软删 VM→默认详情 404；restore→数据不变；Resource 删除成功（无 detail 反向阻止） | 明细不单独泄露、不阻止 Resource 删除 |
| B24 | DB 双触发器四负例 | raw SQL 直插：非 VM 的 resource_id / VM 作 host / 跨 Cluster host / 软删 host | 均被拒；合法插入成功 |
| B25 | FK 语义 | raw SQL 物理 `DELETE FROM resources WHERE id=<vm>`；删除被引用 Host（物理） | `resource_id` FK CASCADE 删 detail（`confdeltype='c'`）；`host_resource_id` FK RESTRICT 阻止物理删 host（`confdeltype='r'`） |
| B26 | CHECK 边界（raw） | raw 直插越界 `vcpu/memory_mb`/`disk_gb`；合法边界值 | 越界被 CHECK 拒；边界值成功 |
| B27 | hypervisor 字符串 | `"  Proxmox  "`、`""`、`"   "`、255 字符、256 字符、`null` | trim 后非空；空/纯空白/超长→422（不转 null）；255 成功；raw 未 trim/空/超长被 backstop 拒 |
| B28 | 迁移 0006 up/down/up | `upgrade head`→`downgrade 0005`→`upgrade head`；`alembic heads` | 各步 0；单一 head `0006_virtual_machine_details`；down 后表/触发器/函数消失、0005 对象保留；re-up 集合一致 |
| B29 | 回填守卫断言 | 迁移前预置未删 VIRTUAL_MACHINE Resource（无 detail）→ 执行 0006 up | upgrade 明确中止并给诊断（或按定稿裁定），不静默丢弃/编造 detail；无未删 VM 时可干净升级 |
| B30 | 互斥 422 对称 | POST/PATCH BARE_METAL 携带 `virtual_machine`（含 null）；VM 携带 `hardware`（含 null） | 均 422；两 detail 行不共存；raw 断言对应行不存在 |
| B31 | 列表 host_resource_id 过滤 | `GET /resources?type=VIRTUAL_MACHINE&host_resource_id=<uuid>`；非 UUID；不存在 UUID | 返回该 Host 下 VM（分页/total 正确）；非 UUID→422；不存在→空结果（非 404） |
| B32 | PATCH exclude_unset 语义 | PATCH 仅含部分子字段；逐个显式 null；整体 null/非对象/未知键 | 省略保持、显式 null 清空 nullable、host 显式 null→422、整体非法→422 |
| B33 | 审计同事务回滚 | monkeypatch 注入 audit 失败制造同事务失败（换 Host 场景） | detail 变更与 audit 同事务双回滚；最终持久化为旧 host；无 audit 残留 |
| B34 | 乐观锁并发（真提交） | `committed_engine` 两独立连接读同 `version`，各自 PATCH 换 Host | 一方 200 且 `version+1`；另一方 409 `VERSION_CONFLICT{current_version}`；最终库值来自成功方，无丢失更新 |
| B35 | host_resource_id 索引 | raw 查询 `pg_indexes` | 存在 `ix_virtual_machine_details_host_resource_id`；无额外业务唯一约束 |
| B36 | 无 VM 级 metadata 列 | raw 查询 `information_schema.columns` | 按 I-3 PROPOSED 无 `virtual_machine_details.metadata`；若 CONTRACT 裁定为 VM 级则改按定稿断言 |

并发说明：B33/B34 及任何「失败不留痕/并发」用例必须使用 `committed_engine`（真实连接真实提交）或显式事务控制，断言**最终持久化状态**，不仅「未抛异常」。B16–B18/B24–B29/B35/B36 必须在真实 PostgreSQL 执行（SQLite 不作 CHECK/FK/CASCADE/触发器/JSONB 证据）。

---

## 3. 夹具 / 环境设计

**复用 F001/F004/F005 `backend/tests/conftest.py`（不改其护栏语义）**：
- `test_database_url`：DB-D10 独立测试库 + 安全护栏（库名含 `test`、`TEST_DATABASE_URL != DATABASE_URL`）；未设置则 skip 并告警，不静默改 SQLite。
- `pg_engine`：会话级 `DROP SCHEMA public CASCADE` + `CREATE SCHEMA public` + `alembic upgrade head`（含 0006），会话结束清理。
- `db_session`：函数级外层事务 + savepoint，回滚不跨用例污染（用于 B1–B23/B26/B27/B31/B32/B35/B36 等单事务用例）。
- `committed_engine`：真实提交用例（B33/B34/B25 及回填后持久断言），teardown `TRUNCATE` 清理（排除 `alembic_version`；F006 需确认 `virtual_machine_details` 已在 `pg_tables` 动态清单内），新开连接断言最终持久化。
- `alembic_runner`：迁移 up/down/up 用例（V16/B28/B29）。

**复用 F002 认证/权限 fixture（`auth_session_factory`/`auth_app`/`api_client`/`bootstrap_admin`/`make_user`/`login`）**：`make_user(role, status=ACTIVE)`；`login` 复用 Cookie 罐；`api_client` 命中真实 ASGI 应用。F006 权限/审计证据使用**真实业务端点** `/api/v1/resources*`。

**复用 F004 的 Cluster/Resource helper 与约束断言模式**：`role_client_factory`、`_create_cluster`、`_create`（`test_resources.py`）；`insert_cluster`/`insert_resource` raw 辅助（`test_resource_constraints.py`）；F004/F005 的软删/恢复、乐观锁 `two-session`、raw SQL 约束断言模式直接复用。

**F006 新增测试侧夹具/断言（由 Tester 落地于测试侧，实现阶段由 Backend 提供接口）**：
- `bare_metal_factory`：创建 BARE_METAL Resource（可附 hardware）作为 Host，返回对象与 `version`。
- `vm_factory`：创建 VIRTUAL_MACHINE Resource（`virtual_machine` 入参），返回对象与 `version`；供 A1–A16、B1–B36 复用。
- `VM_CASES`：表驱动数据（host 类型/跨 Cluster/不存在/软删、host 省略/null、容量省略/null/0/负/上限/超限/非整数、disk_gb 0、hypervisor trim/空/超长/单位），供 V1–V10/V15/V18 与 B1–B11/B16–B21/B27/B32 共用，确保 API 与 DB 同一口径。
- `assert_vm_row(engine, vm_id, expected)`：raw SQL 断言 `virtual_machine_details` 各列值/`IS NULL`，供 V15/B7/B19 等。
- `assert_vm_host_validation(engine, vm_id, host_id)`：raw SQL 直插四类非法（非 VM resource_id、VM 作 host、跨 Cluster、软删 host）断言被双触发器拒绝，供 A17/B1/B2/B4/B24。
- `assert_host_delete_protection(client, host_id)` 与 `assert_vm_restore_dependency(...)`：端到端断言 409 `reference_exists`+references 与 `dependency_deleted`+conflicts，供 A7/A14/B12/B14/B15。
- `assert_vm_cascade(engine, vm_id)`：raw 物理删除 Resource 断言 detail 级联删除、断 FK `confdeltype`（`c` for resource_id、`r` for host_resource_id），供 A13/B25。
- `assert_vm_backfill_guard(alembic_runner, engine)`：迁移前造未删 VM（无 detail），up 断言守卫中止/无未删 VM 时干净升级，供 V16/B29。
- `assert_vm_units(...)`、`assert_vm_no_overcapacity(...)`：单位不换算与超容量仍成功的断言，供 V9/V10/B20/B21。
- `two_session_version_conflict`（复用 F004 模式）：真实提交并发 PATCH 换 Host，供 B34。

**F006 前端夹具**：复用 F005 `smoke:client` 机制，新增 VM 表单/详情/单位/未知占位/Host 选择器/`host_resource_id` 列表调用断言，供 V20。

**环境**：Docker / Compose 可用（F001–F005 TE 已证）；真实 PG 经 Compose `db`（`postgres:16`）。若以非默认入口端口运行 Compose，F006 写端点（POST/PATCH）需覆盖同源 CSRF 行为；应在与既有修复一致的 Nginx 配置下执行，或在报告标注该环境限制。

### 3.1 当前环境可执行性评估

| 验证项 | 环境要求 | 当前评估 | 降级/替代 |
| --- | --- | --- | --- |
| V1–V15/V17–V20、B1–B27/B30–B36 | 真实 PostgreSQL 实例 + 后端集成 | 经 Compose `db` 可满足（F001–F005 已证） | 无 PG 时 skip 并标 BLOCKED，**不得**用 SQLite 替代约束/并发/触发器/CASCADE 证据 |
| V16/B28/B29 迁移 up/down/up + 回填守卫 | Alembic + 真实 PG | 可执行；依赖 0006 定稿 | 迁移未定稿则相关断言 BLOCKED，不降验收 |
| V20 前端 | Node 22 + 构建 | 可执行（F001–F005 smoke:client 已证） | 真实浏览器 DOM 渲染非必要判据（同 F001–F005） |
| Compose 冒烟 / 真实 API 集成 | Docker 可用、端口可用 | 可执行 | 镜像/端口问题记 BLOCKED 并说明 |

---

## 4. 可验证性检查

| 项 | 判定 | 说明 |
| --- | --- | --- |
| A1/A2/A4 宿主三条件 + 同 Cluster | **可验证（API + DB）** | V1/V2/V3/V15 + B1–B4/B24 双路径（422 + 触发器），真实 PG。 |
| A3/A4 host 必填/非空 | **可验证（API + DB）** | V3；Pydantic + `NOT NULL`；显式 null→422。 |
| A5/A6 换 Host + Audit | **可验证（端到端）** | V4/V5/V19 + B7–B11/B33/B34；真实 `/resources*` 与扩展审计快照。 |
| A7 Host 引用删除保护 | **可验证（端到端）** | V6 + B12/B13；检查器返回 references。 |
| A8/A9/A11 容量 null/0/负 | **可验证（API + DB + 前端）** | V7/V8/V9/V15 + B16–B20/B26；响应与 raw `IS NULL`/`=0` 双路径，前端区分。 |
| A10 单位 | **可验证（API + DB + 前端）** | V9/V20 + B20；存储原样整数、展示标注单位。 |
| A12 不校验超额 | **可验证（API + 静态）** | V10 + B21；超容量登记成功 + 静态核对无准入逻辑。 |
| A13 生命周期/无独立端点 | **可验证（静态 + 端到端 + 机制级）** | V11 + B22/B23/B25；路由清单静态；Resource 软删/恢复端到端；**物理 CASCADE/RESTRICT 为机制级**（API 无物理删除路径，仅 raw SQL），报告须显式标注证据边界。 |
| A14 恢复重检 Host | **可验证（端到端）** | V12 + B14/B15；409 `dependency_deleted` 与不覆盖。 |
| A15 权限矩阵 | **可验证（端到端 + 静态）** | V13 + B34；真实端点 + 服务端强制。 |
| A16 Detail 展示 Host / BareMetal 列 VM | **可验证（后端 + 前端）** | V14/V20 + B31；响应 `host{id,hostname}` + `host_resource_id` 过滤。 |
| A17 DB 兜底 | **可验证（DB）** | V15 + B24–B26；双触发器 + FK + CHECK，真实 PG。 |
| V16 迁移 + 回填守卫 | **可验证（DB）** | V16 + B28/B29；真实 PG 含既有未删 VM 数据。 |
| 审计回滚 / 并发无丢失更新 | **可验证（真提交）** | B33/B34 使用 `committed_engine`，断言最终持久化。 |
| 时间/稳定 ID 契约 | **可复用 F004 证据** | F006 detail 不新增时间戳/version 列；Resource 稳定 ID、时间与乐观锁由 F004 TE-1 已证，F006 不重复声明完整回归（仅换 Host 并发新增 B34）。 |

口径明确记录：**A6/A7/A14/A15 为真实业务端点端到端**；**A13 的物理级联为机制级**（API 无物理删除入口）；**A17 的兜底为真实 PG raw SQL 机制级**；**T08/T09/T19 的 F006 子集**（VM Host/跨 Cluster/换 Host 审计）在本 Feature 验证，**T19 的「Resource 不能直接改 Cluster/类型」由 F004 已证**，不重复；**T23/T24/T25/T38/T39 完整回归不在本 Feature**，不得以 F006 局部 PASS 拼成整条通过。

---

## 5. 范围与前置核对（TD-1：DATABASE/CONTRACT 草案待闭合）

> **TD-1 状态：未闭合。** 下表各项以 `architecture.md` §6/§7/DR-57–DR-70 草案为假设，TEST 执行前须以 `docs/database/f006-virtual-machine.md`、`docs/api/F004.md` v3、`d01-conventions.md` v5 §5.5 定稿逐项核对并升 TD-2。

| 项 | TD-1 假设（据 architecture.md 草案） | 待定稿核对 |
| --- | --- | --- |
| 表名/列名/约束名/PK/FK | `virtual_machine_details`；`pk_virtual_machine_details`、`fk_virtual_machine_details_resource_id_resources`（CASCADE）、`fk_virtual_machine_details_host_resource_id_resources`（RESTRICT）、`ix_virtual_machine_details_host_resource_id`；容量 CHECK | 待 DATABASE Gate（`docs/database/f006-virtual-machine.md`）核对实际命名 |
| 双触发器 | `type_match`（resource_id 须 VIRTUAL_MACHINE）+ `host_valid`（host 未软删 BARE_METAL 且同 Cluster）；是否加 resources 软删守卫触发器 | 待 DATABASE Gate 核对触发器/函数命名与覆盖 |
| `virtual_machine` 嵌套结构 | POST/PATCH/响应含 `virtual_machine` 对象；VM 对象、BARE_METAL `null`（DR-59） | 待 CONTRACT v3 冻结键名与 `host{id,hostname}` 形态 |
| PATCH 子字段语义 | `exclude_unset`：省略保持、显式 null 清空 nullable、`host_resource_id` 显式 null→422、整体 null/非对象/未知键 422 | 待 CONTRACT v3 核对 |
| 错误 reason / code / 路径 | 宿主校验 422 `fields[].field="virtual_machine.host_resource_id"`；`CONFLICT{reference_exists,references}`、`CONFLICT{dependency_deleted,conflicts}`；复用 F003/F004 | 待 CONTRACT v3 冻结字段路径与 details 结构 |
| 字符串长度与空值 | hypervisor trim 非空或 null、≤255、空/纯空白 422（不转 null）、无枚举（I-2） | 待 D01 v5 §5.5 与 CONTRACT v3 签核 |
| 数值上限 | `vcpu/memory_mb` 1..2147483647；`disk_gb` 0..2147483647 | 待 D01 v5 §5.5 / DB CHECK 核对 |
| metadata 归属 | 不建 VM 级列，归 `resources.metadata`（I-3 PROPOSED） | 待 CONTRACT v3 / DB 裁定；若为 VM 级则 B36 与 V15 列集合改口径 |
| 列表过滤 | `GET /resources` 增 `host_resource_id=<UUID>`（非 UUID 422、不存在→空），配 `type=VIRTUAL_MACHINE`（DR-67） | 待 CONTRACT v3 冻结参数名与语义 |
| 迁移 0006 + 回填 | `0006_virtual_machine_details`，`down_revision=0005`，单 head、对称可逆；回填守卫：存在未删 VM 则 upgrade 中止（DR-68） | 待 DATABASE Gate 裁定守卫 vs 备选 |
| 换 Host 并发/版本 | 乐观锁复用 `resources.version`；换 Host 与 Audit 同事务（I-4） | 待 D02/CONTRACT v3 固定冲突语义与顺序 |

---

## 6. 不适用项与边界声明

- **容量超额校验**：§9/A12/T39 明确**不做**容量准入或与 Host 容量比较；V10/B21 仅验证「超额仍成功」，不新增容量校验。
- **CSV / Excel 导入（§24）**：VM Host 引用列模板、导入与 API 共用校验口径的执行归 **F014**；F006 仅固化字段校验与 MiB/GiB 口径供复用，不执行导入用例。
- **列表 / 搜索 / Dashboard / Cluster Detail 聚合（§13/§17/§19/§20/§28）**：完整列表、模糊搜索/pg_trgm、Dashboard、Cluster Detail VM 聚合归 **F013**；F006 仅承载 `host_resource_id` 过滤（A16/DR-67）与 Resource Detail 的 VM/Host 展示。
- **完整 Audit 查询页（§22）**：归 **F015**；F006 仅验证换 Host/创建/删除/恢复的资源级 Activity 快照。
- **真实 VM 迁移、电源/运行状态、快照、逐盘建模、监控/调度/自动采集（§34）**：明确排除；F006 只登记关系与容量。
- **完整 T19/T23/T24/T25/T38/T39**：F006 仅承载 VM Host 类型/跨 Cluster、换 Host 审计、Host 引用删除保护/恢复重检、VM 容量 null/数值/单位/超容量不拒等子集；Resource 不可变字段由 F004 已证、speed_mbps 与接口/网络侧归 F007+，跨 Feature 权限/审计完整回归与 §32 上线验收归 F016。**不声明上述条款完整通过**。
- **真实浏览器 DOM 渲染**：非 F006 必要判据（同 F001–F005），前端以构建 + client 机制级 +（如要求）入口真实 API 集成为准。
- **VM 级 metadata（I-3）与 hypervisor 枚举（I-2）**：按 PROPOSED 处理（metadata 归 Resource、hypervisor 无枚举）；若用户/Architect 裁定变更则升 TD-2 调整 B27/B36。

---

## 7. 环境可执行性评估与风险

| 项 | 评估 | 处理 |
| --- | --- | --- |
| V1–V15/V17–V20、B1–B27/B30–B36（真实 PG + 后端集成） | Docker/Compose 可用（F001–F005 已证）；**可执行** | 无 PG 时相关项 BLOCKED，不降验收 |
| V16/B28/B29 迁移（0006 未定稿） | 待 DATABASE Gate | 未定稿则 BLOCKED；TEST 执行前升 TD-2 |
| B33/B34 并发与回滚 | 需真实并发提交 fixture | 复用 `committed_engine`；断言最终持久化与 `current_version` |
| B25 物理 FK CASCADE/RESTRICT | API 无物理删除路径 | raw SQL 机制级验证 `confdeltype`，报告显式标注 |
| V20 前端 | 构建 + client 机制级 | 若要求真实前后端集成，经入口 Nginx 验证；CSRF 端口风险承 F004/F005 TE |
| DATABASE/CONTRACT/D01 定稿状态 | **未解除**：`f006-virtual-machine.md` 未建立、F004 v3 未定稿、D01 v5 §5.5 未签核 | TD-1 保留假设（§5/§8）；执行前升 TD-2 逐项核对 |
| I-2 hypervisor 枚举 / I-3 metadata 归属 | PROPOSED，未定稿 | 按 PROPOSED 设计用例；裁定变更时调整 B27/B36/V15 |
| 回填守卫 vs 备选（DR-68） | 交 DATABASE 裁定 | 守卫为 PROPOSED；若改为 nullable 则 B29/V16 口径调整并关联 §9 保证削弱风险 |

---

## 8. OPEN 复核项（TD-1 提出，待 DATABASE/CONTRACT/D01 定稿关闭）

> **TD-1 状态：全部 OPEN。** TEST 执行前须由 `f006-virtual-machine.md`（DATABASE Gate）、`docs/api/F004.md` v3（CONTRACT Gate）、`d01-conventions.md` v5 §5.5 逐项核对并升 TD-2；差异处注明失效范围，不得沿用 TD-1 草案假设作为执行依据。

| # | TD-1 假设 | 状态 | 待核对依据 / 影响 |
| --- | --- | --- | --- |
| 1 | 表 `virtual_machine_details` 列/约束/索引/FK 名（§0/V15/B25/B35） | **OPEN** | DATABASE Gate；FK 名/CASCADE/RESTRICT/索引名逐字核对 |
| 2 | 双触发器 `type_match`/`host_valid` 命名与覆盖（A1/A2/A17/B1/B2/B4/B24） | **OPEN** | DATABASE Gate；是否加 resources 软删守卫触发器 |
| 3 | `virtual_machine` 嵌套键名与响应 `host{id,hostname}` 形态（DR-59） | **OPEN** | CONTRACT v3 |
| 4 | PATCH 子字段 `exclude_unset`、host 显式 null→422、整体 null/非对象/未知键（V18/B32） | **OPEN** | CONTRACT v3 §API PATCH |
| 5 | 错误字段路径与 CONFLICT details（reference_exists/dependency_deleted）（A6/A7/A14） | **OPEN** | CONTRACT v3；F003/F004 CONFLICT 复用 |
| 6 | 数值上限 1..2147483647 / 0..2147483647（B16–B18/B26） | **OPEN** | D01 v5 §5.5 + DB CHECK |
| 7 | hypervisor trim/空/≤255、无枚举（I-2，B27） | **OPEN** | D01 v5 §5.5 + CONTRACT v3；枚举裁定属新业务规则 |
| 8 | metadata 归 Resource、不建 VM 级列（I-3，B36/V15） | **OPEN** | CONTRACT v3 + DB；裁定变更则改建列断言 |
| 9 | 列表 `host_resource_id` 参数名与语义（DR-67，A16/B31） | **OPEN** | CONTRACT v3 |
| 10 | 迁移 0006 单 head/可逆/回填守卫（DR-68，V16/B28/B29） | **OPEN** | DATABASE Gate；守卫 vs nullable 备选 |
| 11 | 换 Host 并发/版本冲突语义与顺序（I-4，B34） | **OPEN** | D02/CONTRACT v3 |
| 12 | Host 引用检查器注册与 `references[].label` 取值（A7/B12） | **OPEN** | CONTRACT v3 + DR-62 |

---

## Test Execution

> 预留：F006 实现完成、DATABASE/CONTRACT 定稿并升 TD-2 后，由 Tester 在 TEST 模式追加执行版本（TE-1）、环境、命令与结果、A1–A17 与 B1–B36 结论、Defects、未验证项及 Git 声明。**当前无执行结果。**

---

### Git 声明

```text
GIT: NONE
```

本次（TD-1 Test Design）仅写入 `docs/features/F006/test-report.md`，未修改 backend/frontend 业务实现或其它文件，未暂存/提交/切换分支。