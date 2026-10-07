# F006 虚拟机登记 — Test Report

本文件同时承载 TEST_DESIGN 与 TEST（TEST 阶段在同一文件追加执行结果）。两阶段分别记录版本、结论与证据；TEST_DESIGN 不填充执行 PASS。

---

## Test Design

- **版本**：TD-2（当前）；TD-1（2026-10-09）
- **日期**：TD-2 2026-10-09；TD-1 2026-10-09
- **角色**：Tester（TEST_DESIGN 模式）
- **结论**：`TEST DESIGN READY`
- **TD-2 变更（2026-10-09）**：DATABASE Gate（`docs/database/f006-virtual-machine.md` v1，2026-10-09，DB-D53–D63）、CONTRACT Gate（`docs/api/F004.md` v3，2026-10-09，含 §2.5 virtual_machine 字段契约、§4 host_resource_id 过滤、§6.5/§6.6 引用保护与恢复重检、§8 审计白名单）与 `d01-conventions.md` v5（§3/§5.2/§5.5）已定稿，`architecture.md` §14 固定 DR-59/DR-67/DR-69/DR-70 与 DR-71。
  1. 依据定稿 Contract v3 §2.5/§4/§6/§8、DB v1（DB-D53–D63）、D01 v5、`implementation.md`（BACKEND + FRONTEND COMPLETE），关闭 TD-1 §8 全部 12 项 OPEN 复核项（见 §8-A）。
  2. TD-1 的表名/列名/FK 名/触发器语义/嵌套键/错误路径/数值与字符串口径/迁移与回填守卫/并发机制假设均与定稿一致。文档细化两处：触发器实际全名为 `trg_virtual_machine_details_type_match`/`trg_virtual_machine_details_host_valid`（TD-1 仅写短名 `type_match`/`host_valid`）；TD-1 版本记录将 OPEN 项误记为 10 项，实为 §8 表内 12 项，TD-2 已核实并关闭全部 12 项。验收判据均不变。
  3. DR-71（Host 软删并发窗口）由应用层 `SELECT ... FOR UPDATE` 双向串行化落定，TD-2 据此固定 B 类并发用例口径。
- **依据**：
  - `docs/product/requirements-v3.md` revision 3（§4、§4.1、§6、§8、§9、§18、§21、§22、§23、§27、§31 T08/T09/T19/T23/T24/T25/T38/T39、§35.2 Q10-A、§35.3 D01）
  - `docs/features/F006/product.md`（PRODUCT `READY FOR ARCHITECT`，2026-10-09；A1–A17、I-1–I-4、明确排除项）
  - `docs/features/F006/architecture.md`（ARCHITECTURE `READY FOR DESIGN`，2026-10-09；§8 验证策略、DR-57–DR-70）
  - `docs/api/F004.md` v3（READY，Architect 2026-10-09；§2.5 virtual_machine、§4 host_resource_id 过滤、§6.5/§6.6 引用保护与恢复重检、§8 审计白名单）
  - `docs/database/f006-virtual-machine.md` v1（DB-D53–D63；表/约束/双触发器/FK/索引/迁移 0006/回填守卫）
  - `docs/database/f004-resource.md` v1、`docs/database/f005-bare-metal.md` v1（迁移 0004/0005 基座）
  - `docs/architecture/d01-conventions.md` v5（§3/§5.2/§5.5 VirtualMachine 字段口径）
  - `docs/features/F006/implementation.md`（BACKEND + FRONTEND COMPLETE，2026-10-09）
  - `docs/features/F006/architecture.md` §14（CONTRACT Gate，DR-71 并发行锁裁定）
  - `docs/features/F005/test-report.md`（TD-2/TE-1：fixture 模式、机制级口径、真实 PG/Compose 环境证据）
  - `docs/features/F004/test-report.md`（TD-2/TE-1：resources 基座、`_create_cluster`/`_create` 与约束断言模式）
  - `docs/project/project-plan.yaml` plan_revision 4，F006 条目
  - `docs/project/handoff.md`、`docs/project/implementation-rules.md`、`AGENTS.md`、`.pi/skills/data-integrity/SKILL.md`
- **状态属性**：TD-2 READY 仅表示 A1–A17 可映射到可观察判据、边界/并发场景可执行、夹具与可验证性已与定稿 Contract/DB/D01 逐项核对；**不代表测试已运行、不填充执行 PASS、不批准实现或合并**。F006 完整 §31 跨功能回归与 §32 上线验收不在本 Feature（见 §6）。执行结果见本文件 Test Execution。
- **TD-1 生效范围**：A1–A17 映射、V1–V20、B1–B36、夹具/环境设计、可验证性检查在本轮仍有效；TD-1「对 DATABASE/CONTRACT/D01 草案保留假设」不再作为执行依据，TEST 以定稿 Contract v3/DB v1/D01 v5 为准。

### 版本记录

| 版本 | 日期 | 变更 |
| --- | --- | --- |
| TD-1 | 2026-10-09 | 初版：A1–A17 映射 V1–V20，边界/并发 B1–B36，夹具/环境设计，可验证性检查，不适用项；对 DATABASE/CONTRACT/D01 保留待复核假设（§8，实际 12 项）。 |
| TD-2 | 2026-10-09 | 依据 DATABASE v1 / CONTRACT v3 / D01 v5 关闭 §8 全部 12 项 OPEN；补记 DR-71 并发口径；验收判据不变。 |

> 复核基线（TD-2）：`docs/api/F004.md` v3（CONTRACT Gate，2026-10-09）、`docs/database/f006-virtual-machine.md` v1（2026-10-09，DB-D53–D63）、`docs/architecture/d01-conventions.md` v5、`architecture.md` §14（DR-71）。表名/约束名/FK/触发器/迁移/嵌套键名/错误路径/CONFLICT details/数值与字符串口径均已按定稿核对（见 §8-A），不再保留「草案待闭合」假设。

---

### 0. 数据完整性对应表（F006 范围）

仅列 F006 已确认且在实现后需验证的完整性/持久化项；方法依据 `.pi/skills/data-integrity/SKILL.md`。数据库列/约束以 `docs/database/f006-virtual-machine.md` v1 定稿（DB-D53–D63）为准（TD-2 已核对）。

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

## 5. 范围与前置核对（TD-2：DATABASE/CONTRACT/D01 已定稿，逐项核对完成）

> **TD-2 状态：已闭合。** 下表各项已以 `docs/database/f006-virtual-machine.md` v1（DB-D53–D63）、`docs/api/F004.md` v3、`d01-conventions.md` v5 §5.5 定稿逐项核对，与 TD-1 假设一致（详见 §8-A）。

| 项 | TD-1 假设（据 architecture.md 草案） | 定稿核对（TD-2） |
| --- | --- | --- |
| 表名/列名/约束名/PK/FK | `virtual_machine_details`；`pk_virtual_machine_details`、`fk_virtual_machine_details_resource_id_resources`（CASCADE）、`fk_virtual_machine_details_host_resource_id_resources`（RESTRICT）、`ix_virtual_machine_details_host_resource_id`；容量 CHECK | **一致**：DB v1 §2 + 0006；4 CHECK（vcpu/memory_mb/disk_gb/hypervisor） |
| 双触发器 | `type_match`（resource_id 须 VIRTUAL_MACHINE）+ `host_valid`（host 未软删 BARE_METAL 且同 Cluster）；是否加 resources 软删守卫触发器 | **一致**：DB-D58；触发器全名 `trg_virtual_machine_details_type_match`/`_host_valid`；**不加** resources 软删守卫（DB-D59，采用 DR-71 行锁） |
| `virtual_machine` 嵌套结构 | POST/PATCH/响应含 `virtual_machine` 对象；VM 对象、BARE_METAL `null`（DR-59） | **一致**：Contract v3 §2.5/§3（含 `host{id,hostname}`，无 metadata 键） |
| PATCH 子字段语义 | `exclude_unset`：省略保持、显式 null 清空 nullable、`host_resource_id` 显式 null→422、整体 null/非对象/未知键 422 | **一致**：Contract v3 §2.5/§6.4 |
| 错误 reason / code / 路径 | 宿主校验 422 `fields[].field="virtual_machine.host_resource_id"`；`CONFLICT{reference_exists,references}`、`CONFLICT{dependency_deleted,conflicts}`；复用 F003/F004 | **一致**：Contract v3 §1.2/§6.5/§6.6 |
| 字符串长度与空值 | hypervisor trim 非空或 null、≤255、空/纯空白 422（不转 null）、无枚举（I-2） | **一致**：Contract v3 §2.5；D01 v5 §5.2/§5.5（I-2 无枚举固定） |
| 数值上限 | `vcpu/memory_mb` 1..2147483647；`disk_gb` 0..2147483647 | **一致**：DB-D55；D01 v5 §3/§5.5；Contract v3 §2.5 |
| metadata 归属 | 不建 VM 级列，归 `resources.metadata`（I-3 PROPOSED） | **一致**：DB-D57 + Contract v3 §2.5/§3（DR-69）；B36/V15 断言仍为无 detail metadata 列 |
| 列表过滤 | `GET /resources` 增 `host_resource_id=<UUID>`（非 UUID 422、不存在→空），配 `type=VIRTUAL_MACHINE`（DR-67） | **一致**：Contract v3 §4（DR-67） |
| 迁移 0006 + 回填 | `0006_virtual_machine_details`，`down_revision=0005`，单 head、对称可逆；回填守卫：存在未删 VM 则 upgrade 中止（DR-68） | **一致**：DB-D61/DB-D62；守卫已落定（非 nullable 备选） |
| 换 Host 并发/版本 | 乐观锁复用 `resources.version`；换 Host 与 Audit 同事务（I-4） | **一致**：Contract v3 §2.5/§7；DR-71 `SELECT ... FOR UPDATE` 双向串行化（architecture §14） |

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
| V16/B28/B29 迁移（0006 已定稿） | DATABASE Gate v1 已定稿 | TE-1 已实际执行（真实 PG up/down/up + 回填三例）；结果见 TE-1 |
| B33/B34 并发与回滚 | 需真实并发提交 fixture | 复用 `committed_engine`；断言最终持久化与 `current_version` |
| B25 物理 FK CASCADE/RESTRICT | API 无物理删除路径 | raw SQL 机制级验证 `confdeltype`，报告显式标注 |
| V20 前端 | 构建 + client 机制级 | 若要求真实前后端集成，经入口 Nginx 验证；CSRF 端口风险承 F004/F005 TE |
| DATABASE/CONTRACT/D01 定稿状态 | **已解除**：DB v1 / Contract v3 / D01 v5 均已定稿并经 TD-2 逐项核对 | 风险关闭；差异仅触发器全名与 OPEN 项计数文档细化，判据不变 |
| I-2 hypervisor 枚举 / I-3 metadata 归属 | **已裁定**：I-2 无枚举（D01 v5 §5.5）；I-3 metadata 归 Resource（DB-D57/DR-69） | B27/B36/V15 按定稿执行 |
| 回填守卫 vs 备选（DR-68） | **已裁定**：前置守卫（DB-D62），非 nullable 备选 | B29/V16 按守卫执行（TE-1 已证） |

---

## 8. OPEN 复核项（TD-1 提出，TD-2 全部关闭）

> **TD-2（2026-10-09）状态：全部 CLOSED。** DATABASE Gate（`docs/database/f006-virtual-machine.md` v1，DB-D53–D63）、CONTRACT Gate（`docs/api/F004.md` v3）与 `d01-conventions.md` v5 §5.5 已定稿；下表各假设逐项与定稿核对，无判据差异（仅触发器全名与 OPEN 项计数为文档细化，已于 §8-A 记录）。TD-1 的「待定稿假设」不再作为执行依据，TEST 以定稿 Contract v3/DB v1/D01 v5 为准。

### 8-A. OPEN 关闭记录

| # | TD-1 假设 | 状态 | 定稿核对（依据 / 影响） |
| --- | --- | --- | --- |
| 1 | 表 `virtual_machine_details` 列/约束/索引/FK 名（§0/V15/B25/B35） | **CLOSED** | DB v1 §2 + 0006：`pk_virtual_machine_details`、`fk_virtual_machine_details_resource_id_resources`（CASCADE/`confdeltype='c'`）、`fk_virtual_machine_details_host_resource_id_resources`（RESTRICT/`'r'`）、`ix_virtual_machine_details_host_resource_id`、`ck_virtual_machine_details_{vcpu,memory_mb,disk_gb}_range`、`ck_virtual_machine_details_hypervisor_format`；列集合 `resource_id/host_resource_id/vcpu/memory_mb/disk_gb/hypervisor` |
| 2 | 双触发器 `type_match`/`host_valid` 命名与覆盖（A1/A2/A17/B1/B2/B4/B24） | **CLOSED** | DB-D58：全名 `trg_virtual_machine_details_type_match`/`trg_virtual_machine_details_host_valid`（TD-1 仅写短名，已细化）；**不加** resources 软删守卫（DB-D59），并发窗口交 DR-71 |
| 3 | `virtual_machine` 嵌套键名与响应 `host{id,hostname}` 形态（DR-59） | **CLOSED** | Contract v3 §2.5/§3：对象含 `host_resource_id/host/vcpu/memory_mb/disk_gb/hypervisor`，不含独立 metadata；BARE_METAL `virtual_machine=null` |
| 4 | PATCH 子字段 `exclude_unset`、host 显式 null→422、整体 null/非对象/未知键（V18/B32） | **CLOSED** | Contract v3 §2.5/§6.4 |
| 5 | 错误字段路径与 CONFLICT details（A6/A7/A14） | **CLOSED** | Contract v3 §1.2/§6.5/§6.6：`field="virtual_machine.host_resource_id"`；`reference_exists`+`references[]`；`dependency_deleted`+`conflicts[]` |
| 6 | 数值上限 1..2147483647 / 0..2147483647（B16–B18/B26） | **CLOSED** | DB-D55；D01 v5 §3/§5.5；Contract v3 §2.5 |
| 7 | hypervisor trim/空/≤255、无枚举（I-2，B27） | **CLOSED** | DB-D56；D01 v5 §5.2/§5.5；Contract v3 §2.5；无枚举（I-2 固定） |
| 8 | metadata 归 Resource、不建 VM 级列（I-3，B36/V15） | **CLOSED** | DB-D57 + Contract v3 §2.5/§3（DR-69）；detail 无 `metadata` 列 |
| 9 | 列表 `host_resource_id` 参数名与语义（DR-67，A16/B31） | **CLOSED** | Contract v3 §4；非 UUID→422；不存在→空结果（非 404） |
| 10 | 迁移 0006 单 head/可逆/回填守卫（DR-68，V16/B28/B29） | **CLOSED** | DB-D61/DB-D62；单 head `0006_virtual_machine_details`、`down_revision=0005`、对称可逆；未删 VM→upgrade 中止 |
| 11 | 换 Host 并发/版本冲突语义与顺序（I-4，B34） | **CLOSED** | Contract v3 §2.5/§7；DR-71 `SELECT ... FOR UPDATE`；Host 先-创建/换 Host 422；VM 先-Host 软删 409 `reference_exists` |
| 12 | Host 引用检查器注册与 `references[].label` 取值（A7/B12） | **CLOSED** | Contract v3 §1.2/§6.5 + DR-62；`references=[{object_type:"resource",object_id:<vm-uuid>,label:<vm-hostname>}]` |

TD-1 未闭合项已由 TD-2 关闭；实现与 Contract 未发生导致判据差异的后续变更。

---

## Test Execution

- **版本**：TE-1
- **日期**：2026-10-09
- **角色**：Tester（TEST 模式）
- **结论**：`TEST PASS`（角色术语：READY FOR REVIEW）
- **执行基线**：Contract `docs/api/F004.md` v3（2026-10-09）、DATABASE `docs/database/f006-virtual-machine.md` v1（2026-10-09，DB-D53–D63）、D01 `d01-conventions.md` v5、`architecture.md` §14（DR-71）、`implementation.md`（BACKEND + FRONTEND COMPLETE）、TD-2。
- **代码基线**：HEAD `d3b36e9`（F006 实现检查点），起始工作区干净。
- **独立性声明**：Backend pytest 由 Tester 独立重跑（不复用实现者数字）；迁移、约束、触发器、CHECK、FK、回填守卫由 Tester 在独立库（`csm_test`/`csm_verify_test`）以 Alembic / raw SQL 直接执行；Compose 集成由 Tester 经入口 Nginx `127.0.0.1:18096` 独立 curl。

### 环境

| 项 | 值 |
| --- | --- |
| 后端测试镜像 | `docker build --target test -t csm-backend-f006te1 ./backend`（Python 3.12.15，pytest 8.4.2） |
| 数据库 | 独立容器 `f006te1-db`（`postgres:16`），网络 `f006te1-net`；测试库 `csm_test`、独立验证库 `csm_verify_test` |
| 集成（后端） | `TEST_DATABASE_URL=postgresql+psycopg://csm:change-me@f006te1-db:5432/csm_test`（DB-D10 护栏：库名含 `test`、≠ `DATABASE_URL`） |
| 前端 | Node v22.23.2 / npm 12.0.2；`npm run typecheck`、`npm run build`、`npm run smoke:client` |
| Compose 全链路 | `docker compose -p f006te1`（独立项目名/卷），入口 Nginx `127.0.0.1:18096`（非默认端口；`deploy/nginx/nginx.conf` 保留 `Host` 端口以使同源 CSRF 生效） |
| 清理 | `compose -p f006te1 down -v`、`docker rm -f f006te1-db`、`docker network rm f006te1-net`、删临时镜像 `csm-backend-f006te1` 与 `f006te1-*`；残留检查无 f006 容器/网络/镜像 |

### 实际执行命令与输出摘要

| # | 命令 | 结果 |
| --- | --- | --- |
| 1 | `pytest tests -q`（真实 PG `csm_test`） | **183 passed, 1 skipped**（skip=`test_migrations.py:101` 非 superuser 扩展假设：连接角色 `csm` 为 superuser 的环境限制，非 F006 缺陷；与 F004/F005 基线相同） |
| 2 | `pytest tests/integration/test_virtual_machine.py tests/integration/test_virtual_machine_constraints.py -v` | **32 passed**（21 API + 11 constraint/migration F006 专属用例，逐条 PASS） |
| 3 | 独立库 `csm_verify_test`：`alembic heads` / `upgrade head` / `current` | `0006_virtual_machine_details (head)` 单一 head；升级 0001→0006 全部 Running；`current`=`0006_virtual_machine_details (head)` |
| 4 | `downgrade 0005_bare_metal_details`→`upgrade head` + 对象核查 | down 后 `virtual_machine_details` 与 `fn_virtual_machine%` 函数消失、`bare_metal_details` 等 0005 对象保留；re-up 后表集合一致；alembic_version 单值 |
| 5 | 回填守卫三例（独立库，raw SQL 预置） | 例1 未删 VM→upgrade 中止：`cannot apply 0006: 1 undeleted VIRTUAL_MACHINE resource(s) exist without a host; no safe backfill (DR-68).`，表未创建；例2 软删 VM→upgrade 通过且 detail 行数 0；例3 无 VM→down/up 干净 |
| 6 | raw SQL 结构探测（`csm_verify_test`） | 7 约束（PK + 2 FK + 4 CHECK）、2 触发器（`trg_..._type_match`/`_host_valid`）、2 索引（PK + `ix_..._host_resource_id`）、列集合 6 列（`host_resource_id` NOT NULL、`hypervisor` varchar(255)，无 metadata/时间戳）；FK `confdeltype`：resource_id=`c`、host_resource_id=`r` |
| 7 | raw SQL 负例/正例探测（`csm_verify_test`） | type_match 拒 BARE_METAL owner；host_valid 拒 VM-host/跨 Cluster/软删 host；host NULL 拒；vcpu=0、disk_gb=-1、hypervisor ''/untrimmed/256 均拒；合法插入成功；物理删 host 被 FK RESTRICT 拒；物理删 VM 级联删 detail；`disk_gb=0` vs `NULL` 可区分 |
| 8 | `npm run typecheck` / `npm run build` / `npm run smoke:client` | typecheck 0 错误；build 通过（**49 modules**）；smoke **64 passed, 0 failed**（F006 新增 12 项） |
| 9 | Compose/Nginx 全链路 curl（18096） | `migrate`/`bootstrap` Exited(0)，`alembic_version=0006_virtual_machine_details`，backend healthy；登录→建 Cluster→建 Host→建 VM（容量/hypervisor trim/disk_gb=0）→详情 host 展开→列表 `host_resource_id` 过滤→换 Host + activity before/after→Host 引用删除 409→跨 Cluster 422→超额容量 201→软删 VM 后 Host 可删→restore VM 409 dependency_deleted→restore Host 后 VM restore 200→无独立端点 404；状态码与错误信封符合 Contract |
| 10 | `python3 scripts/validate_project_state.py` | `PROJECT STATE VALID`（结构校验；批准/Git 证据另行核对，非本报告结论） |

### V1–V20 执行结果（TD-2 → TE-1）

| 验证项 | 结果 | 证据 / 说明 |
| --- | --- | --- |
| V1 宿主为 VM→422 | **PASS** | 命令 2 `test_host_must_be_undeleted_bare_metal_in_same_cluster`；field=`virtual_machine.host_resource_id`；命令 7 raw type_match 拒 BARE_METAL owner |
| V2 跨 Cluster host→422 | **PASS** | 命令 2 同上；命令 9 跨 Cluster 创建 422（同字段）；命令 7 raw host_valid 拒 |
| V3 host 省略/null/空串→422 | **PASS** | 命令 2 `test_host_required_and_shapes`；raw NOT NULL 拒 |
| V4 合法创建 + host 展开 | **PASS** | 命令 2 `test_create_virtual_machine_and_host_expansion`；命令 9 详情 `host{id,hostname}`；raw detail 行一致 |
| V5 换 Host + Audit before/after | **PASS** | 命令 2 `test_rehost_writes_audit_and_validates`；命令 9 activity CREATE/UPDATE `before/after host_resource_id` |
| V6 Host 引用删除保护 409 + references | **PASS** | 命令 2 `test_host_delete_protection`；命令 9 409 `reference_exists`+references（label=vm-hostname）；VM 软删后 Host 可删 |
| V7 容量省略/null→null（非 0） | **PASS** | 命令 2 `test_capacity_omitted_null_and_zero`；raw `IS NULL` |
| V8 容量 0/负→422；正例接受 | **PASS** | 命令 2 `test_capacity_ranges_and_strict_types`；命令 7 raw CHECK 拒 |
| V9 MiB/GiB 原样不换算 | **PASS** | 命令 2 `test_memory_and_disk_units_verbatim`（memory_mb=1572864）；命令 9 详情原样；前端单位标注经 smoke |
| V10 超额不拒 | **PASS** | 命令 2 `test_no_over_capacity_check`；命令 9 vcpu=64（host 16）201，PATCH 128 200 |
| V11 无独立端点 + 明细随 Resource | **PASS** | 命令 2 `test_lifecycle_and_no_independent_endpoint`；命令 9 三个独立路径 404；raw CASCADE/RESTRICT；**物理级联为机制级** |
| V12 恢复重检 Host | **PASS** | 命令 2 `test_restore_rechecks_host`；命令 9 409 `dependency_deleted`+conflicts，VM 保持软删，restore Host 后放行 |
| V13 权限矩阵（EDITOR/VIEWER/ADMIN） | **PASS**（ASGI 真实端点 + 真实 PG） | 命令 2 `test_virtual_machine_permission_matrix`、`test_patch_host_validation_precedes_version`；VIEWER 写 403 `FORBIDDEN{permission}`/读 200；EDITOR 写 200、删/恢复 403；ADMIN 成功 |
| V14 Detail 展示 Host / 列表过滤 | **PASS** | 命令 2 `test_list_host_resource_filter`；命令 9 列表 total=1；非 UUID 422、不存在→空 |
| V15 DB 约束/列集合（raw PG） | **PASS** | 命令 2 `test_table_shape_constraints_indexes_and_triggers`；命令 6/7 raw 一致 |
| V16 迁移 0006 + 回填守卫 | **PASS** | 命令 2 `test_migration_single_head_and_up_down_up`/`test_backfill_guard`；命令 3/4/5 独立复现 |
| V17 互斥 422 | **PASS** | 命令 2 `test_hardware_and_virtual_machine_are_mutually_exclusive`；两 detail 行不共存 |
| V18 PATCH exclude_unset | **PASS** | 命令 2 `test_patch_subfield_semantics`；host 显式 null→422；整体 null/非对象/未知键→422 |
| V19 审计同事务回滚 | **PASS** | 命令 2 `test_virtual_machine_update_rolls_back_with_audit`；注入 audit 失败后 detail 与 audit 双回滚，持久状态为旧值 |
| V20 前端 VM 区域与状态 + 集成 | **PASS**（构建 + 机制级 + 入口集成） | 命令 8 typecheck/build/smoke 64/64；命令 9 经入口 Nginx 真实 API 往返；源码核对未知「—」、disk_gb=0「明确无磁盘」、MiB/GiB 标注、409 不重试、422 点路径 |

### B1–B36 执行结果

| 编号 | 结果 | 证据摘要 |
| --- | --- | --- |
| B1 host 类型错误 | PASS | 命令 2/7；422 + raw type_match 拒；无 detail 行 |
| B2 host 跨 Cluster | PASS | 命令 2/7/9；422 + raw host_valid 拒；库值不变 |
| B3 host 不存在 | PASS | 命令 2 `test_host_required_and_shapes`（missing UUID）；raw FK |
| B4 host 已软删 | PASS | 命令 2/7；422 + raw host_valid 拒 |
| B5 host 省略/显式 null | PASS | 命令 2；raw NULL 被 NOT NULL 拒 |
| B6 host PATCH 显式 null | PASS | 命令 2 `test_patch_subfield_semantics`；422，库值/version 不变 |
| B7 合法 host 创建 | PASS | 命令 2/9；201，detail 恰一行，响应含 host |
| B8 1:1 依附 | PASS | 命令 2 `test_pk_single_row_per_resource`；PK 拒第二行 |
| B9 换 Host + Audit | PASS | 命令 2/9；detail.host=B；UPDATE before/after=A/B；object_type=resource |
| B10 换 Host 跨 Cluster | PASS | 命令 2；422，库值不变 |
| B11 换 Host 指向软删/不存在 | PASS | 命令 2 `test_rehost_soft_deleted_host_rejected` 与 missing；422 |
| B12 Host 引用删除保护 | PASS | 命令 2/9；409 `reference_exists`+references；Host 仍存在 |
| B13 VM 软删后 Host 可删 | PASS | 命令 2/9；204 + DELETE audit；detail 行保留 |
| B14 恢复 VM 依赖被删 | PASS | 命令 2/9；409 `dependency_deleted`+conflicts；不覆盖 |
| B15 恢复 VM 标识重用 | PASS | 命令 2 `test_restore_rechecks_host`（host 先恢复后 VM 恢复成功；标识重用不覆盖新对象由 FK/PK 与依赖检查保证）；Contract v3 §6.6 unique_conflict/dependency 语义 |
| B16 vcpu 边界 | PASS | 命令 2/7；0/负/超限→422；1..上限接受；raw CHECK |
| B17 memory_mb 边界 | PASS | 命令 2/7；同上；不按 MB 解释 |
| B18 disk_gb 边界 | PASS | 命令 2/7/9；-1/超限→422；0→201 存 0；省略→null；raw `=0` vs `IS NULL` |
| B19 容量省略/null | PASS | 命令 2；已登记落值、其余 `IS NULL` |
| B20 单位一致 | PASS | 命令 2/8/9；原样存/返回；前端 `1536 GiB` 等价 |
| B21 超 Host 容量不拒 | PASS | 命令 2/9；201；无准入路径 |
| B22 detail 无独立端点 | PASS | 命令 2/9；路由清单无独立端点；未定义路径 404 |
| B23 生命周期随 Resource | PASS | 命令 2/9；软删默认 404、restore 数据不变；Resource 删除成功 |
| B24 DB 双触发器四负例 | PASS | 命令 2/7；非 VM owner/VM 作 host/跨 Cluster/软删 host 均拒；合法插入成功 |
| B25 FK 语义 | PASS | 命令 2/7；resource_id CASCADE（`c`）；host_resource_id RESTRICT（`r`）；**机制级（raw SQL）** |
| B26 CHECK 边界（raw） | PASS | 命令 2/7；越界被 CHECK 拒；边界值成功 |
| B27 hypervisor 字符串 | PASS | 命令 2/7；trim 非空；空/纯空白/256→422（不转 null）；255→201；raw backstop |
| B28 迁移 0006 up/down/up | PASS | 命令 2/3/4；单一 head；down 后表/函数消失、0005 对象保留；re-up 集合一致 |
| B29 回填守卫断言 | PASS | 命令 2/5；未删 VM→upgrade 中止且诊断；软删 VM→通过且不生成行；无 VM→干净 |
| B30 互斥 422 对称 | PASS | 命令 2 `test_hardware_and_virtual_machine_are_mutually_exclusive`；两 detail 行不共存 |
| B31 列表 host_resource_id 过滤 | PASS | 命令 2/9；返回该 Host 下 VM；非 UUID 422；不存在→空 |
| B32 PATCH exclude_unset 语义 | PASS | 命令 2 `test_patch_subfield_semantics`；省略保持、显式 null 清空、host null 422、整体非法 422 |
| B33 审计同事务回滚 | PASS | 命令 2 `test_virtual_machine_update_rolls_back_with_audit`；断言最终持久化旧 host、无 audit 残留 |
| B34 乐观锁并发（真提交） | PASS | 命令 2 `test_rehost_optimistic_lock_two_sessions`；一方 200 `version+1`、另一方 409 `VERSION_CONFLICT{current_version:2}`；最终库值来自成功方 |
| B35 host_resource_id 索引 | PASS | 命令 2/6；`ix_virtual_machine_details_host_resource_id` 存在且 EXPLAIN 使用；无额外业务唯一约束 |
| B36 无 VM 级 metadata 列 | PASS | 命令 2/6；`information_schema.columns` 无 `metadata`；列集合仅 6 列 |

### DR-71 并发两方向（后台执行 + raw SQL 锁竞争）

| 方向 | 结果 | 证据 |
| --- | --- | --- |
| Host 软删（持锁）↔ VM 创建等待 | **PASS** | 命令 2 `test_dr71_create_waits_for_host_delete_lock`：创建线程在 Host 行锁上阻塞，Host 先提交软删后创建返回 **422** |
| VM 创建（持锁）↔ Host 删除等待 | **PASS** | 命令 2 `test_dr71_host_delete_waits_for_vm_create_lock`：删除线程阻塞，VM 先提交后 Host 删除返回 **409 reference_exists** |

### 数据库 / 接口 / 前端 / 集成结果

- **数据库（真实 PG，`csm_verify_test` raw SQL + `csm_test` pytest）**：`virtual_machine_details` 列/约束/索引/双触发器与 DB v1 逐项一致；FK `resource_id` CASCADE（`confdeltype='c'`）、`host_resource_id` RESTRICT（`'r'`）+ `NOT NULL`；4 CHECK 生效；`disk_gb=0` 与 `null` 可区分；迁移 0006 对称可逆、单一 head、回填守卫三例正确。**PASS**
- **接口（ASGI + 全链路 Nginx 18096）**：POST/PATCH virtual_machine 响应内容、类型、nullable、宿主四条件、互斥、业务边界、非法输入、错误语义符合 Contract；`VALIDATION_ERROR`（`virtual_machine.host_resource_id`/`virtual_machine.<field>`）/`FORBIDDEN{permission|csrf}`/`AUTH_REQUIRED`/`CONFLICT{reference_exists|dependency_deleted}`/`VERSION_CONFLICT`；严格整数、trim、单位原样、`disk_gb=0≠null`；未认证 401。只读端点无业务写副作用。**PASS**
- **前端**：typecheck/build 通过；client 机制级 64 项通过；VM 表单/详情/Host 选择器/单位标注/未知「—」/`disk_gb=0`「明确无磁盘」/409 不重试/422 点路径经源码与 smoke 核对；经入口 Nginx 真实 API 往返。**PASS**
- **集成（Compose 经入口 Nginx）**：`migrate`/`bootstrap` Exited(0)，`alembic_version=0006_virtual_machine_details`，backend healthy；登录→建 Cluster→建 Host→建 VM→详情/换 Host/Activity→宿主删除保护→跨 Cluster 422→超额 201→软删/恢复→引用/恢复冲突→无独立端点 404 全链路符合 Contract。**PASS**

### 验收映射 A1–A17 结论

| # | 结论 | 证据 |
| --- | --- | --- |
| A1 | **PASS** | V1/V15；B1 |
| A2 | **PASS** | V2/V15；B2 |
| A3 | **PASS** | V3；B5 |
| A4 | **PASS** | V3/V15；B3/B4 |
| A5 | **PASS** | V4；B7/B8 |
| A6 | **PASS**（端到端 + Audit） | V5/V19；B9–B11/B33/B34 |
| A7 | **PASS**（端到端） | V6；B12/B13 |
| A8 | **PASS** | V7；B19 |
| A9 | **PASS** | V8；B16/B17/B26 |
| A10 | **PASS**（前端展示 + 后端/DB） | V9/V20；B20 |
| A11 | **PASS** | V7/V8/V9/V20；B18 |
| A12 | **PASS** | V10；B21 |
| A13 | **PASS**（端到端软删/恢复 + 物理 CASCADE 机制级） | V11；B22/B23/B25 |
| A14 | **PASS**（端到端） | V12；B14/B15 |
| A15 | **PASS**（ASGI 真实端点 + 真实 PG） | V13；见未验证项关于 Nginx 角色矩阵说明 |
| A16 | **PASS**（后端 + 前端） | V14/V20；B31 |
| A17 | **PASS**（真实 PG raw SQL） | V15；B24/B26 |

### Defects

未发现必须修复的实现缺陷。以下为观察（NOTE，非缺陷）：

| ID | Severity | Layer | Location | 证据 / 期望与实际 | 影响 | Owner | 必须修复 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| F006-TE-1-01 | NOTE | 文档（Test Design） | `test-report.md` TD-1 版本记录 | TD-1 版本记录写「10 项待复核假设」，而 §8 表实际为 12 项；TD-2 已核实并关闭全部 12 项 | 仅文档计数笔误，无实现影响 | Tester | 否（已在 TD-2 修正） |
| F006-TE-1-02 | NOTE | 集成测试范围 | Compose/Nginx | 一期无用户管理 HTTP 端点（F015），无法经 Nginx 以 VIEWER/EDITOR 真实登录验证 A15 角色矩阵；已由 `role_client_factory` + 真实 ASGI + 真实 PG 的业务端点覆盖 | 环境限制，非实现缺陷 | 协调器/F015 | 否 |

### 未验证项与口径声明

- **B25/A13 物理 FK CASCADE/RESTRICT 为机制级**：API 无物理删除 Resource 路径（删除为软删），CASCADE/RESTRICT 仅经 raw SQL 物理 `DELETE` 验证；软删随 Resource 隐藏/恢复为端到端。不得表述为独立端到端。
- **B33 审计回滚**：以 monkeypatch 注入 audit 失败制造同事务失败，断言最终持久化；非真实进程崩溃注入。
- **DR-71 并发**：以真实连接持行锁 + 后台线程阻塞竞争验证两方向；断言最终持久化为 422/409，未做大规模压测。
- **真实浏览器 DOM 渲染**：未自动化；前端以 typecheck + build + client 机制级 + 入口 Nginx 真实 API 集成为准（同 F001–F005）。
- **A15 角色矩阵经 Nginx**：见 F006-TE-1-02；权限由真实业务端点（ASGI）+真实 PG 覆盖，服务端强制，非仅前端隐藏。
- **数据完整性映射**：`.pi/skills/data-integrity/SKILL.md` 对应表全部适用项已在 §0 与本节覆盖；Unicode Cc/Cf 仅应用层保证、DB 为 ASCII backstop（DB I-5 已知差异，非本 Feature 缺陷）。
- **完整 T08/T09/T19/T23/T24/T25/T38/T39**：F006 仅承载 VM Host 类型/跨 Cluster、换 Host 审计、Host 引用删除保护/恢复重检、VM 容量 null/数值/单位/超容量不拒等子集；Resource 不可变字段由 F004 已证、speed_mbps 与接口/网络侧归 F007+，跨 Feature 权限/审计完整回归与 §32 上线验收归 F016。**不声明上述条款完整通过**。
- **导入（§24）**：VM Host 引用列模板与导入一致性归 F014；F006 仅固化校验与 MiB/GiB 口径。
- **完整列表/Dashboard/Cluster Detail 聚合（§13/§17/§19/§20/§28）**：归 F013；F006 仅 `host_resource_id` 过滤与 Resource Detail 展示。
- **完整 Audit 查询页（§22）**：归 F015；F006 仅资源级 Activity 快照。

---

### Git 声明

```text
GIT: NONE
```

本次（TD-2 + TE-1）仅写入 `docs/features/F006/test-report.md`（更新 Test Design 关闭 OPEN 并追加 Test Execution），未修改 backend/frontend 业务实现或其它仓库文件；未暂存/提交/切换分支。测试与迁移均在临时容器/独立测试库中执行，不影响仓库状态。