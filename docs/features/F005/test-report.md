# F005 BareMetal 硬件与容量 — Test Report

本文件同时承载 TEST_DESIGN 与 TEST（TEST 阶段在同一文件追加执行结果）。两阶段分别记录版本、结论与证据；TEST_DESIGN 不填充执行 PASS。

---

## Test Design

- **版本**：TD-2（当前）；TD-1（2026-10-09）
- **日期**：TD-2 2026-10-09；TD-1 2026-10-09
- **角色**：Tester（TEST_DESIGN 模式）
- **结论**：`TEST DESIGN READY`
- **TD-2 变更（2026-10-09）**：DATABASE Gate（`docs/database/f005-bare-metal.md` v1，2026-10-08）、CONTRACT Gate（`docs/api/F004.md` v2，2026-10-09，含 §2.4 hardware 字段契约与 §8 审计白名单）与 `d01-conventions.md` v4（§3/§5.2/§5.4）已定稿。
  1. 依据定稿 Contract v2 §2.4/§6/§8、DB v1（DB-D45–D52）、D01 v4、实现记录，关闭 TD-1 §8 全部 10 项 OPEN 复核项（见 §8-A）。
  2. 修正 **F005-TD-1-01（文档缺陷，LOW）**：TD-1 §5 将 FK 约束名写作 `fk_bare_metal_details_resource_id`，定稿 DB v1 为 `fk_bare_metal_details_resource_id_resources`；TD-2 已改正，验收判据（`ON DELETE CASCADE`/`confdeltype='c'`）不变。
- **依据**：
  - `docs/product/requirements-v3.md` revision 3（§4.1、§8、§18、§21、§22、§23、§26、§27、§31 T38/T39、§32、§35.2 Q10-A、§35.3 D01）
  - `docs/features/F005/product.md`（PRODUCT；A1–A10 与边界）
  - `docs/features/F005/architecture.md` §9（CONTRACT Gate `READY FOR IMPLEMENTATION`，2026-10-09；DR-46–DR-56）
  - `docs/database/f005-bare-metal.md` v1（DB-D45–D52；表/约束/触发器/迁移 0005/回填）
  - `docs/features/F005/implementation.md`（BACKEND + FRONTEND COMPLETE，2026-10-09）
  - `docs/features/F004/test-report.md`（TD-2/TE-1：fixture 模式、机制级口径、真实 PG/Compose 环境证据）
  - `docs/architecture/d01-conventions.md` v4（§3 数值上限、§5.2 长度 255、§5.4 BareMetal hardware 口径）
  - `docs/database/f004-resource.md` v1（resources 表、约束、迁移 0004，作为 0005 的 down_revision 基座）
  - `docs/api/F004.md` v2（READY，Architect 2026-10-09；§2.4 hardware、§3 响应、§6 POST/PATCH、§8 审计白名单）
  - `docs/project/project-plan.yaml` plan_revision 4，F005 条目（`status=IN_PROGRESS`、`current_stage=TEST`）
  - `docs/project/handoff.md`、`docs/project/implementation-rules.md`、`AGENTS.md`、`.pi/skills/data-integrity/SKILL.md`
- **状态属性**：TD-2 READY 仅表示 A1–A10 可映射到可观察判据、边界/并发场景可执行、夹具与可验证性已与定稿 Contract/DB/D01 逐项核对；**不批准实现或合并，TD-2 本身不填充执行 PASS，也不表示 T38/T39 完整通过**（T38 的 VM 容量、T39 的 VM 侧与 speed_mbps 分别归 F006/F007+，见 §6）。执行结果见本文件 TE-1。
- **TD-1 生效范围**：A1–A10 映射、V1–V16、B1–B29、夹具/环境设计、可验证性检查在本轮仍有效（除 F005-TD-1-01 的 FK 名文本）；TD-1「对 DATABASE/CONTRACT 草案保留假设」不再作为执行依据，TEST 以定稿 Contract/DB/D01 为准。

### 版本记录

| 版本 | 日期 | 变更 |
| --- | --- | --- |
| TD-1 | 2026-10-09 | 初版：A1–A10 映射 V1–V16，边界/并发 B1–B29，夹具/环境设计，可验证性检查，不适用项；对 DATABASE/CONTRACT 保留 10 项待复核假设（见 §8）。 |
| TD-2 | 2026-10-09 | 依据 DATABASE v1 / CONTRACT v2 / D01 v4 关闭 §8 全部 10 项 OPEN；修正 F005-TD-1-01（FK 约束名）；验收判据不变。 |

> 复核基线（TD-2）：`docs/api/F004.md` v2（CONTRACT Gate，2026-10-09）、`docs/database/f005-bare-metal.md` v1（2026-10-08，DB-D45–D52）、`docs/architecture/d01-conventions.md` v4。表名/约束名/FK/`hardware` 嵌套结构/错误语义/字符串长度/`metadata` 暴露均已按定稿核对（见 §8-A），不再保留「草案待闭合」假设。

---

### 0. 数据完整性对应表（F005 范围）

仅列 F005 已确认且在实现后需验证的完整性/持久化项；方法依据 `.pi/skills/data-integrity/SKILL.md`。数据库列/约束以 `docs/database/f005-bare-metal.md` v1 定稿（DB-D45–D52）为准（TD-2 已核对）。

| 规则依据及版本 | 作用域/写入入口 | 数据库保证（草案，待 DB Gate） | 业务层保证 | 并发/生命周期边界 | 验证与证据 |
| --- | --- | --- | --- | --- | --- |
| §8 / §4.1 / Q10-A（硬件全部 nullable、未知存 null 不写 0；gpu_count=0≠null） | `POST/PATCH /resources` 的 `hardware` | 9 列全部 nullable、无 NOT NULL、无默认 0；`gpu_count` CHECK 含 0 | Pydantic 可选字段；省略→不写；显式 null 清空 nullable | 未登记 BARE_METAL 行为全 null 行；VM 无行 | V1/V2/V13、B1–B3/B14；计划验证 |
| §8（cpu_sockets/cpu_cores/memory_mb 正整数；gpu_count 非负） | `POST/PATCH /resources` | `ck_bare_metal_details_*` INTEGER 范围 CHECK（正整数 1..2147483647；gpu_count 0..2147483647） | Pydantic `ge` + Service 校验；越界/非整数→422 `VALIDATION_ERROR` | 无跨字段推导 | V3/V13、B4–B7；计划验证 |
| §8 / d01 v3 §3（memory_mb 单位 MiB，1 GiB=1024 MiB，不混用 MB/GB） | `POST/PATCH /resources`；界面展示 | 列名 `memory_mb`、整数原样存储（不换算） | 应用不做 ×1000/÷1024 隐式换算；展示标注单位 | — | V4、B8；计划验证 |
| §8 / T39（cpu_cores=整机物理核总数，不含超线程；不自动探测） | `POST/PATCH /resources`；静态实现 | INTEGER 存储（无派生列） | 仅人工登记校验；无主机探测/自动计算 | — | V5、B9；计划验证 |
| §8 / Q10-A（SN 一期无全局唯一） | `POST/PATCH /resources`；raw SQL | 无 unique 索引/约束 | 服务端不做 SN 唯一校验 | 重复 SN 允许 | V6/V13、B10；计划验证 |
| §8 / §26 / §27（常查/排序/统计结构化；厂商特有入 JSONB） | `POST/PATCH /resources`；raw SQL | 9 结构化列可索引/查询；`metadata jsonb NOT NULL DEFAULT '{}'` + `jsonb_typeof='object'` CHECK | metadata 整值替换；非 object→422 | JSONB 不破坏结构化查询 | V10/V13、B19/B28；计划验证 |
| §21（明细随 Resource 生命周期；无独立删除/恢复入口；不阻止 Resource 删除；物理级联） | Resource 端点（无 detail 独立端点）；raw SQL 物理删除 | `resource_id UUID PK` + FK→resources(id) **ON DELETE CASCADE**；无 `deleted_at`/`version` | 应用保证「BARE_METAL 必有、VM 必无」行；软删随 Resource 过滤 | 软删 Resource 隐藏明细；restore 后明细不变；物理删除级联 | V9/V13/V14、B24–B25；计划验证 |
| §22 / §23（硬件变更并入 Resource 审计；权限随 Resource WRITE；乐观锁） | `POST/PATCH /resources`、Activity | 复用 `resources.version` 与 `audit_logs`（无 detail 级并发列） | `require_permission`；快照白名单扩 `hardware`；条件 UPDATE version | 两会话仅一方成功；回滚不留 audit | V8/V11、B20–B23；计划验证 |
| §4.1 / DR-51（VM 无 hardware） | `POST/PATCH /resources`（VM） | 无 VM detail 行；应用层拒绝 | VM 请求体出现 `hardware`→422；响应 `hardware=null` | — | V12、B13/B14；计划验证 |

---

## 1. 验收映射（product.md A1–A10 → 验证项）

执行环境：`Compose` = 干净环境 `docker compose up -d`（含 `migrate`/`bootstrap` 一次性服务）；`真实 PG` = 经 Compose `db` 或本机 PostgreSQL 的独立测试库（DB-D10，库名含 `test`）；`后端集成` = ASGI 应用 + 真实 PG 测试库（非 SQLite）；`静态` = 仓库/路由清单静态检查；`文档` = 签核记录核对；`前端` = 构建 + client 机制级用例（与真实 API 集成时以入口 Nginx 为准）。

| 验收（product.md） | 验证项 | 执行环境 | 可观察判据（PASS / FAIL） |
| --- | --- | --- | --- |
| A1 硬件字段省略/null 保存 null 并在详情返回 null 不返回 0 | **V1** 省略/null→null + **V16** PATCH 子字段语义 + **V13** DB 断言 | 后端集成 + 真实 PG | PASS：POST BARE_METAL 省略 `hardware` → 201 且响应 `hardware` 为对象、9 字段全 `null`；显式传 `hardware:{cpu_cores:null,...}` 同样全 `null`；raw DB 断言各列为 `IS NULL`（非 0）；详情 `GET` 返回 `null`。FAIL：任一字段落库/返回为 `0`、`hardware` 缺失、未知值伪装为 0 |
| A2 gpu_count=0 接受并存 0，展示"明确无 GPU"，与未知 null 可区分 | **V2** 0 vs null | 后端集成 + 真实 PG + 前端 | PASS：`gpu_count=0` → 201，响应/库为 `0`；不传 `gpu_count` → `null`；两者在详情可区分；前端 GPU 区域对 0 显示「明确无 GPU」、对 null 显示未知占位（非 0）。FAIL：0 被拒或被转 null、null 被写 0、前端把两者同渲染 |
| A3 cpu_sockets/cpu_cores/memory_mb 为 0 或负数被拒 422；gpu_count 负数被拒；正整数/非负整数按 §8 接受 | **V3** 数值范围 | 后端集成 + 真实 PG | PASS：`cpu_sockets/cpu_cores/memory_mb ∈ {0,-1}`、`gpu_count=-1` → 422 `VALIDATION_ERROR`；正例 `cpu_sockets=2,cpu_cores=192,memory_mb=1572864,gpu_count=0/8` → 201/200；raw DB 断言对应 CHECK 拒绝越界直插。FAIL：非法值创建成功、错误码非 422、DB CHECK 缺失 |
| A4 memory_mb 以 MiB 存/展示：1536 GiB→1572864，转换一致，不按 MB 解释 | **V4** 单位一致性 | 后端集成 + 真实 PG + 前端 | PASS：登记 `memory_mb=1572864` 存/返回 `1572864`（不做 ×1000 或 ×1024 隐式换算）；`GiB×1024=MiB` 展示一致（1536 GiB）；若契约提供展示转换，`1572864 MiB = 1536 GiB`。FAIL：存/返回被换算、按 MB 解释、单位标签缺失或错误 |
| A5 cpu_cores 整机物理核心不含超线程：2×EPYC 192 物理核→192（非 384）；不自动探测，只按人工登记校验 | **V5** 物理核语义 + 静态 | 后端集成 + 真实 PG + 静态 | PASS：登记 `cpu_sockets=2,cpu_cores=192` 存/返回 `192`；系统不实现主机探测/自动计算（静态核对无 host probe，`cpu_cores` 无派生）；`cpu_cores=384` 作为正整数亦被接受（系统不做 sockets×cores 交叉推导）。FAIL：落库被改、存在自动探测、以 384 强制覆盖 |
| A6 相同 serial_number 可登记，无唯一冲突 | **V6** SN 无唯一 | 后端集成 + 真实 PG | PASS：两个 BARE_METAL Resource 使用同一 `serial_number` 均 201；raw DB 插入重复 SN 成功（无 unique 索引）；PATCH 修改 SN 不触发 409。FAIL：出现 409 `unique_conflict`、存在 SN 唯一约束 |
| A7 Detail Hardware 区域显示 CPU/Memory/GPU/Manufacturer/Model/SN | **V7** 响应数据 + **V15** 前端区域 | 后端集成 + 前端 | PASS：`GET /resources/{id}`（BARE_METAL）`hardware` 含 `cpu_model/cpu_sockets/cpu_cores`（CPU）、`memory_mb`（Memory）、`gpu_model/gpu_count`（GPU）、`manufacturer/model/serial_number`；前端 Hardware 区域按 §18 展示六类，未知显示占位而非伪造值。FAIL：字段缺失、区域未渲染、VM 渲染 Hardware、未知伪装成 0/空 |
| A8 硬件创建/修改变更进 Audit；权限 §23（EDITOR 可改，VIEWER 只读） | **V8** 审计 + **V11** 权限 | 后端集成 + 真实 PG + 前端 | PASS：创建含硬件→CREATE audit 快照含 `hardware`；PATCH 硬件→UPDATE audit `before/after` 含硬件白名单字段；VIEWER GET 200、写/提交 hardware 403 `FORBIDDEN{reason:permission}`；EDITOR 可创建/修改硬件；未认证 401；服务端强制（前端隐藏不替代）。FAIL：硬件变更无 audit、快照缺硬件、角色越权成功、仅前端隐藏而服务端放行 |
| A9 BareMetalDetail 无独立删除/恢复入口；删除/恢复只作用于 Resource，明细跟随且不阻止 Resource 删除 | **V9** 生命周期 + **V13** CASCADE 机制级 | 后端集成 + 真实 PG + 静态 | PASS：路由清单无 `.../hardware`、`/bare-metal-details` 等独立端点；Resource 软删后明细随详情隐藏、restore 后硬件数据不变；物理删除 Resource（raw SQL）级联删除明细行（机制级）；明细不作为阻止 Resource 删除的独立子对象（Resource 删除始终成功，无 detail 引用检查）。FAIL：存在独立删除/恢复入口、明细阻止 Resource 删除、软删/恢复不同步、FK 非 CASCADE |
| A10 结构化字段可查询/排序/统计；厂商特有/低频入 JSONB 不破坏结构化查询 | **V10** 结构化查询 + **V13** DB 列/约束 | 真实 PG + 静态 | PASS：raw SQL 对 `cpu_cores/memory_mb/gpu_count` 做 `WHERE`/`ORDER BY`/`count()`/`avg()` 可用；9 字段为结构化列（非 JSONB）；`metadata` 为 object JSONB 且不影响结构化查询；确认未引入列表级 hardware 过滤参数（I-1，不在范围）。FAIL：关键字段落入 JSONB、结构化查询不可用、metadata 破坏查询、擅自新增列表硬件过滤 |
| （A7/A8 前端 + 集成） | **V15** Hardware 区域与状态 + 集成 | 前端 + Compose | PASS：BARE_METAL 详情 Hardware 区域六要素、单位标注、Loading/Success/Empty/Error 与未知值占位；编辑表单携带 `version`、409 冲突明确提示且不静默重试；VM 详情不渲染 Hardware；经入口 Nginx 真实 API 集成。FAIL：状态缺失、错误伪装空、VM 渲染硬件、409 静默覆盖 |

补充验证项（非直接 A 映射，但属实现后必须执行）：

| 验证项 | 内容 | 执行环境 | 判据 |
| --- | --- | --- | --- |
| **V12** VM 拒绝 hardware | VM 提交/响应语义 | 后端集成 + 真实 PG | PASS：`POST/PATCH` VIRTUAL_MACHINE 含 `hardware` → 422（不静默忽略，DR-51）；VM 详情 `hardware` 恒为 `null`；raw DB 无 VM detail 行。FAIL：静默忽略、VM 产生 detail 行、响应返回对象 |
| **V13** DB 约束/列集合（raw PG） | 表结构、CHECK、FK、列完整性 | 真实 PG | PASS：`bare_metal_details.resource_id` 为 PK 且 FK `ON DELETE CASCADE`；9 列 nullable；范围 CHECK 生效；`metadata` object CHECK；无 `deleted_at/version/created_at/updated_at`（按架构裁定，若 Database 追加 `created_at` 以定稿为准）。FAIL：缺约束、列类型/可空性不符、引入并发/软删列 |
| **V14** 迁移 0005 up/down/up + 回填 | Alembic + 真实 PG | 真实 PG | PASS：`alembic heads` 单一 head `0005_bare_metal_details`（`down_revision=0004_resources`）；up 建表→约束→FK；down 后表/约束/FK 消失且 0004 对象保留；re-up 集合一致；回填 `INSERT ... SELECT id FROM resources WHERE resource_type='BARE_METAL'` 后每个既有 BARE_METAL 有全 null 行、VM 无行、重复 up 不重复。FAIL：多个 head、不对称、回填缺失/重复、误建 VM 行 |
| **V16** PATCH 子字段语义 | `exclude_unset` 语义 | 后端集成 + 真实 PG | PASS：PATCH `hardware` 仅含子字段时其他子字段保持原值；显式 `null` 清空该 nullable 子字段；`hardware` 整体显式 `null`/非对象/含未知键 → 422。FAIL：省略被重置、显式 null 被忽略或写 0、整体 null 被接受 |

---

## 2. 边界与并发场景（B 编号，TEST 阶段执行）

| 编号 | 场景 | 步骤 | 判据 |
| --- | --- | --- | --- |
| B1 | hardware 省略 | POST BARE_METAL 不带 `hardware` | 201；`bare_metal_details` 恰一行、9 列全 `IS NULL`；响应 `hardware` 为对象且各字段 `null` |
| B2 | hardware 各字段显式 null | POST/PATCH 逐个传 `null` | 201/200；对应列 `IS NULL`；响应 `null`（非 0） |
| B3 | 部分字段登记、其余未知 | POST `hardware:{manufacturer:"Dell",cpu_cores:192}`，其余省略 | 已登记落值、其余 `IS NULL`；响应一致 |
| B4 | gpu_count=0 vs null | 分别 POST `gpu_count=0` 与不传 | 前者存/返回 `0`；后者 `null`；两者在详情可区分；raw 断言 `=0` vs `IS NULL` |
| B5 | 正整数非正值拒绝 | `cpu_sockets/cpu_cores/memory_mb ∈ {0,-1,-100}` | 均 422 `VALIDATION_ERROR`；raw SQL 直插同值被对应 CHECK 拒 |
| B6 | gpu_count 负值/零边界 | `gpu_count=-1` 与 `gpu_count=0` | `-1`→422；`0`→201；raw `-1` 被 CHECK 拒 |
| B7 | 非整数/类型错误 | `cpu_cores="192"`(字符串)、`=true`、`=1.5`、`gpu_count=[]` | 422（严格整数语义，不静默转换）；库值不变 |
| B8 | 数值上限 | `cpu_cores=2147483647` 与 `2147483648` | 上限内接受；超限 422 或 raw DB CHECK 拒绝（以定稿范围为准） |
| B9 | memory_mb MiB 一致 | 登记 `memory_mb=1572864`；对 1536 GiB 场景核对展示 | 存/返回 `1572864`；不出现 `1572864000`（×1000）或 `1536`（÷1024）；展示 `1536 GiB` 与 `1572864 MiB` 等价（1 GiB=1024 MiB） |
| B10 | cpu_cores 物理核不含 HT | `cpu_sockets=2,cpu_cores=192`；另建 `cpu_cores=384` | 192 存/返回 192；384 作为正整数亦被接受（无 sockets×cores 推导）；静态核对无主机探测/HT 计数逻辑 |
| B11 | SN 可重复 | 两 BARE_METAL 同 `serial_number`；raw SQL 直插重复 SN | 均成功；无 unique 索引/约束；`pg_indexes` 无 SN 唯一项 |
| B12 | 字符串 trim/空/超长 | `manufacturer="  Dell  "`、`=""`、`="   "`、256 字符 | trim 后非空存储（长度上限 255 PROPOSED，待 Contract）；空/纯空白/超长 → 422（具体以定稿为准）；raw 直插超长被列长/CHECK 拒 |
| B13 | hardware 整体非法 | `hardware=[]`、`="x"`、`=null`、`{unknown_key:1}` | 均 422（非对象/整体 null/未知键）；不静默忽略未知键 |
| B14 | VM 提交 hardware | POST/PATCH VIRTUAL_MACHINE 含 `hardware` | 422（DR-51）；VM 详情 `hardware` 恒 `null`；raw 断言 VM 无 detail 行 |
| B15 | BARE_METAL 行存在性 | 建 BARE_METAL；再建 VM；raw 查询两表 | 每个 BARE_METAL 恰一行 detail（`resource_id` PK 保证至多一行，应用保证至少一行）；VM 无行 |
| B16 | PATCH 子字段省略保持 | 先登记 `manufacturer/cpu_cores`，PATCH 仅 `hardware:{gpu_count:8}` | 其余子字段保持原值（`exclude_unset`）；库中旧值不变 |
| B17 | PATCH 子字段显式 null 清空 | PATCH `hardware:{manufacturer:null}` | 该列变 `NULL`；其他子字段保持；响应 `null` |
| B18 | PATCH hardware 整体 null/非对象 | PATCH `hardware:null`、`hardware:"x"` | 422；库值不变（hardware 本身不可清空） |
| B19 | metadata JSONB object | raw 直插 `metadata='[]'`/`'"x"'`/`'null'`；PATCH `hardware:{metadata:{...}}` | 非法非 object 被 `ck_*_metadata_object` 拒；合法 object 存储；整值替换语义（旧键消失） |
| B20 | 硬件变更审计 | 创建含硬件→PATCH 改 `memory_mb/gpu_count` | CREATE audit 快照含硬件；UPDATE audit `before/after` 含硬件白名单字段；`object_type="resource"`、`object_id` 为 Resource UUID；无敏感字段 |
| B21 | 权限矩阵（硬件随 Resource） | VIEWER/EDITOR/ADMIN 对 Resource 硬件创建/修改/读取 | VIEWER 读 200、写 403 `FORBIDDEN{reason:permission}`；EDITOR 写 201/200；未认证 401；服务端强制（静态核对无绕过） |
| B22 | 乐观锁并发（真提交） | `committed_engine` 两独立连接读同 `version`，各自 PATCH `hardware` | 一方 200 且 `version+1`；另一方 409 `VERSION_CONFLICT{current_version}`；最终库值来自成功方，无丢失更新 |
| B23 | 硬件变更同事务回滚 | 在硬件 PATCH 事务内注入失败使 commit 失败 | 明细列变更与 audit 行同事务双回滚，无残留（断言最终持久化状态，非仅未抛异常） |
| B24 | 生命周期随 Resource | Resource 软删；无参数 GET 详情；restore；静态路由清单 | 软删后详情 404/不可见（明细不单独泄露）；restore 后硬件数据不变；路由清单无独立 detail 删除/恢复端点；Resource 删除始终成功（detail 不阻止） |
| B25 | FK CASCADE（物理级联，机制级） | raw SQL 物理 `DELETE FROM resources WHERE id=...` | 对应 `bare_metal_details` 行被级联删除（`confdeltype='c'`）；VM 无行可级联；软删不走物理删除 |
| B26 | 迁移 0005 up/down/up | `upgrade head` → `downgrade 0004_resources` → `upgrade head`；`alembic heads` | 各步 0；单一 head `0005_bare_metal_details`；down 后 detail 表/约束/FK 消失、0004 `resources` 保留；re-up 对象集合一致 |
| B27 | 迁移回填断言 | 迁移前建 BARE_METAL + VM 资源；执行 0005 up | 每个既有 BARE_METAL 有全 null detail 行；VM 无行；再次 up 不重复插入 |
| B28 | 结构化列可查询/排序/统计 | raw SQL 对 `cpu_cores/memory_mb/gpu_count` `WHERE`/`ORDER BY`/`count`/`avg`；含 `metadata` 行 | 结构化查询返回正确结果；metadata 存在不影响；9 字段在结构化列而非 JSONB |
| B29 | detail 列集合与时间戳裁定 | raw 查询 `information_schema.columns` | 无 `deleted_at/version`（架构裁定）；`metadata NOT NULL DEFAULT '{}'`；若 Database 追加 `created_at` 以定稿为准并核对 |

并发说明：B22/B23 及任何「失败不留痕/并发不重复」用例必须使用 `committed_engine`（真实连接真实提交）或显式事务控制，断言**最终持久化状态**，不仅「未抛异常」。B5/B6/B8/B12/B19/B25/B29 必须在真实 PostgreSQL 执行（SQLite 不作 CHECK/FK/CASCADE/JSONB 证据）。

---

## 3. 夹具 / 环境设计

**复用 F001 `backend/tests/conftest.py`（不改其护栏语义）**：
- `test_database_url`：DB-D10 独立测试库 + 安全护栏（库名含 `test`、`TEST_DATABASE_URL != DATABASE_URL`）；未设置则 skip 并告警，不静默改 SQLite。
- `pg_engine`：会话级 `DROP SCHEMA public CASCADE` + `CREATE SCHEMA public` + `alembic upgrade head`（含 0005），会话结束清理。
- `db_session`：函数级外层事务 + savepoint，回滚不跨用例污染（用于 B1–B21/B24/B28/B29 等单事务用例）。
- `committed_engine`：真实提交用例（B22/B23/B25 及回填后持久断言），teardown `TRUNCATE` 清理（排除 `alembic_version`；F005 需确认 `bare_metal_details` 已在 `pg_tables` 动态清单内），新开连接断言最终持久化。
- `alembic_runner`：迁移 up/down/up 用例（V14/B26/B27）。

**复用 F002 认证/权限 fixture（`auth_session_factory`/`auth_app`/`api_client`/`bootstrap_admin`/`make_user`/`login`）**：
- `make_user(role, status=ACTIVE)` 生成 VIEWER/EDITOR/ADMIN；`login` 复用同一 Cookie 罐；`api_client` 命中真实 ASGI 应用。
- F005 的权限/审计证据使用**真实业务端点** `/api/v1/resources*`（创建/详情/PATCH/activity），A8/A9 端到端。

**复用 F003/F004 的 Cluster/Resource fixture 模式（现集中在 `backend/tests/conftest.py`；F004 测试内以 helper 建对象）**：
- F005 复用 F004 `test_resources.py` 的 `_create_cluster`/`_create` 与 `test_resource_constraints.py` 的 `insert_cluster`/`insert_resource` raw 辅助模式。
- `role_client_factory`（F004 已落地）：按角色返回已登录 client，供 B21。
- F004 的软删/恢复、乐观锁 `two-session`、raw SQL 约束断言模式直接复用。

**F005 新增测试侧夹具/断言（由 Tester 落地于测试侧，实现阶段由 Backend 提供接口）**：
- `bare_metal_factory`：创建 BARE_METAL Resource 并可附 `hardware` 参数，返回对象与 `version`；供 A1–A10、B1–B24 复用。
- `vm_factory`：创建 VIRTUAL_MACHINE Resource（F005 仅用于 `hardware` 拒绝与 `hardware=null` 断言，VM 容量字段归 F006）。
- `HARDWARE_CASES`：表驱动数据（省略/全 null/部分/边界 0/-1/上限/超限/非整数/字符串长度/未知键/非对象/整体 null/metadata 非 object），供 V1–V6/V13/V16 与 B1–B13/B19 共用，确保 API 与 DB 同一口径。
- `assert_hardware_row(engine, resource_id, expected)`：以 raw SQL 断言 9 列值/`IS NULL`，供 V13/B1–B8/B29。
- `assert_hardware_backfill(alembic_runner, engine)`：迁移前造 BARE_METAL+VM，up 后断言 BARE_METAL 全 null 行、VM 无行、幂等，供 V14/B27。
- `assert_vm_rejects_hardware(client, ...)`：VM POST/PATCH `hardware` 断言 422 与详情 `hardware=null`，供 V12/B14。
- `assert_cascade_delete(engine, resource_id)`：raw 物理删除 Resource 断言 detail 级联删除，供 V9/B25。
- `two_session_version_conflict`（复用 F004 模式）：真实提交并发 PATCH hardware，供 B22。

**环境**：Docker / Compose 可用（F001–F004 TE 已证）；真实 PG 经 Compose `db`（`postgres:16`）。宿主机无 `psql`/`pg_dump` 不影响本 Feature（DB 断言经 SQLAlchemy 或容器内 psql）。前端 V15 以构建 + client 机制级为主；若要求真实前后端集成，经入口 Nginx 验证，不以 Mock 代替（`implementation-rules.md` §4）。**环境风险（承 F003 D-TE-1 / F004 TE-1）**：若以非默认入口端口运行 Compose，F005 写端点（POST/PATCH）需覆盖同源 CSRF 行为；应在与既有修复一致的 Nginx 配置下执行，或在报告标注该环境限制。

### 3.1 当前环境可执行性评估

| 验证项 | 环境要求 | 当前评估 | 降级/替代 |
| --- | --- | --- | --- |
| V1–V13、B1–B25/B28/B29 | 真实 PostgreSQL 实例 + 后端集成 | 经 Compose `db` 可满足（F001–F004 已证） | 无 PG 时 skip 并标 BLOCKED，**不得**用 SQLite 替代约束/并发/JSONB/CASCADE 证据 |
| V14/B26/B27 迁移 up/down/up + 回填 | Alembic + 真实 PG（含既有 BARE_METAL 数据） | 可执行；依赖 0005 定稿 | 迁移未定稿则相关断言 BLOCKED，不降验收 |
| V15 前端 | Node 22 + 构建 | 可执行（F001–F004 smoke:client 已证） | 真实浏览器 DOM 渲染非必要判据（同 F001–F004） |
| Compose 冒烟 / 真实 API 集成 | Docker 可用、端口可用 | 可执行 | 镜像/端口问题记 BLOCKED 并说明 |

---

## 4. 可验证性检查

| 项 | 判定 | 说明 |
| --- | --- | --- |
| A1/A2 未知值 null 与 0 的区分 | **可验证（API + DB）** | V1/V2 + B1–B4 以响应与 raw `IS NULL`/`=0` 双路径断言；前端展示区分在 V15。 |
| A3 数值范围 | **可验证（API + DB）** | V3 + B5–B8 双路径（Pydantic 422 + DB CHECK），真实 PG。 |
| A4 单位一致性 | **可验证（API + DB + 前端）** | V4 + B9；存储原样整数、展示标注单位；不依赖隐式换算。 |
| A5 cpu_cores 物理核语义 | **可验证（API + 静态）** | V5 + B10；存储值断言 + 静态核对无自动探测/推导（架构 §1.3「只按人工登记校验」）。 |
| A6 SN 无唯一 | **可验证（API + DB）** | V6 + B11；无 unique 索引为可观察事实。 |
| A7 Hardware 展示 | **可验证（后端 + 前端）** | V7 响应字段 + V15 前端区域；VM 不渲染。 |
| A8 审计 + 权限 | **可验证（端到端）** | V8/V11 + B20/B21；真实 `/resources*` 端点与被扩展的资源快照白名单。 |
| A9 生命周期 / 无独立端点 | **可验证（静态 + 端到端 + 机制级）** | 路由清单静态核对无 detail 端点；Resource 软删/恢复端到端；**物理 CASCADE 为机制级**（API 无物理删除路径，仅 raw SQL 验证 FK `ON DELETE CASCADE`），报告须显式标注证据边界，不得表述为独立端到端。 |
| A10 结构化可查询 / JSONB 不破坏 | **可验证（DB + 静态）** | V10/V13 + B28；raw SQL 结构化查询；**列表级 hardware 过滤参数不在 F005 范围（I-1）**，不新增、不断言，仅验证数据层可查询。 |
| V12 VM 拒绝 hardware | **可验证（端到端）** | V12 + B14；VM 请求 422、响应 null、无 detail 行。 |
| V14 迁移 + 回填 | **可验证（DB）** | V14 + B26/B27；真实 PG 含既有数据。 |
| 审计回滚不留痕 / 并发无丢失更新 | **可验证（真提交）** | B22/B23 使用 `committed_engine`，断言最终持久化。 |
| Hardware 未知值前端占位 | **可验证（前端）** | V15 断言未知不伪装为 0/空列表。 |
| 时间/稳定 ID 契约 | **可复用 F004 证据** | F005 detail 不新增时间戳/version 列（架构 §4 裁定）；Resource 稳定 ID 与时间契约由 F004 TE-1 已证，F005 不重复声明完整回归。 |

口径明确记录：**A8 权限与审计为真实业务端点端到端**；**A9 的物理级联为机制级**（API 无物理删除入口）；**A10 仅数据层结构化查询**，列表级硬件过滤走变更控制；**T38 的 VM 容量与 T39 的 VM 侧/speed_mbps 不在本 Feature**，不得以 F005 局部 PASS 拼成 T38/T39 完整通过。

---

## 5. 范围与前置核对（TD-2：DATABASE/CONTRACT 已定稿）

> **TD-2 状态：全部核对完成。** 下表各项已与定稿 `docs/api/F004.md` v2 §2.4/§3/§6/§8、`docs/database/f005-bare-metal.md` v1、`d01-conventions.md` v4 及实现记录逐项核对；无判据差异（除 F005-TD-1-01 FK 名文本笔误，已于 TD-2 修正）。保留原「待定稿核对」列以记录 TD-1 假设与定稿的对应关系。

| 项 | TD-1 假设（据 architecture.md 草案） | 定稿核对结论 |
| --- | --- | --- |
| 表名/列名/约束名 | `bare_metal_details`；`pk_bare_metal_details`、`fk_bare_metal_details_resource_id`、范围 CHECK、`metadata` object CHECK | **CLOSED（DB v1 §2/DB-D46/47/48）**：`pk_bare_metal_details`、FK 实际名 `fk_bare_metal_details_resource_id_resources`、5 个 `ck_*_format`、4 个 `ck_*_range`、`ck_bare_metal_details_metadata_object`；均与迁移 0005 一致（F005-TD-1-01 修正 FK 名） |
| `hardware` 嵌套结构 | POST/PATCH 请求与响应含 `hardware` 对象；BARE_METAL 对象、VM `null`（DR-47，PROPOSED） | **CLOSED（Contract v2 §2.4/§3）**：BARE_METAL 响应=对象、VM=`null`；请求含 `hardware` 仅对 BARE_METAL 有效 |
| PATCH 子字段语义 | `exclude_unset`：省略保持、显式 null 清空 nullable、整体 null/非对象/未知键 422 | **CLOSED（Contract v2 §2.4）**：硬件子字段级 exclude_unset；与 Resource `metadata` 整值替换分开 |
| 错误 reason / code | 422 `VALIDATION_ERROR`（范围/类型/非对象/未知键/字符串）；复用 F004 `CONFLICT`/`VERSION_CONFLICT`；SN 无 `unique_conflict` | **CLOSED（Contract v2 §1.2/§2.4）**：`fields[].field` 点路径（`hardware.cpu_cores` 等）；无 SN `unique_conflict` |
| 字符串长度与空值 | trim 非空或 null；长度 ≤255 code point（DR-52，PROPOSED）；空/纯空白 → 422 | **CLOSED（Contract v2 §2.4；D01 v4 §5.4；DB-D46）**：≤255 code point；空/纯空白→422（不转 null）；DB 非空+已 trim backstop |
| `metadata` 暴露方式 | `hardware.metadata` JSONB object，默认 `{}`（架构 §1.4/§4） | **CLOSED（Contract v2 §2.4；DB-D47）**：请求/响应暴露 `hardware.metadata`，整值替换；DB `NOT NULL DEFAULT '{}'` + object CHECK |
| detail 时间戳列 | 不设 `deleted_at/version`；`created_at` 可选交 Database（架构 §4，若加不改无软删/无 version） | **CLOSED（DB-D48）**：`deleted_at/version/created_at/updated_at` 全不设 |
| CASCADE / 类型匹配 | FK `ON DELETE CASCADE`；「BARE_METAL 必有、VM 必无」由应用保证；类型匹配触发器待 Database 裁定 | **CLOSED（DB-D49；DB v1 §3.2/§3.3）**：FK `confdeltype='c'`；新增 `trg_bare_metal_details_type_match` 禁止 VM 行；「BARE_METAL 必有」仍由应用保证 |
| 迁移 0005 | `0005_bare_metal_details`，`down_revision=0004_resources`，单一 head；回填 `INSERT ... SELECT WHERE resource_type='BARE_METAL'` | **CLOSED（DB-D51；0005 迁移文件）**：单一 head；回填 SQL 与 TD-1 假设一致 |
| 数值 CHECK 上限 | `cpu_sockets/cpu_cores/memory_mb` 1..2147483647；`gpu_count` 0..2147483647 | **CLOSED（DB-D46；Contract v2 §2.4）**：与迁移 CHECK 一致 |
| 乐观锁/审计白名单 | 硬件变更并入 Resource CREATE/UPDATE 审计快照，白名单扩 `hardware`；权限随 Resource WRITE/READ | **CLOSED（Contract v2 §8/§1.3）**：快照白名单扩 `hardware`（VM 为 null）；权限随 Resource WRITE/READ |

---

## 6. 不适用项与边界声明

- **VM 容量与 Host 校验（§9）**：`host_resource_id/vcpu/disk_gb/hypervisor`、Host 类型/同 Cluster、换 Host 审计、Host 删除阻止、VM 容量单位 `disk_gb` 及 T38 VM 侧/T39 VM 侧归 **F006**；F005 仅在 B14/V12 验证「VM 不携带 hardware」。
- **CSV / Excel 导入（§24）**：硬件字段导入、单位在导入模板的一致性、API 与导入共用校验口径的执行归 **F014**；F005 只固化字段校验与 MiB 口径供复用，不执行导入用例。
- **列表级硬件过滤/排序/统计参数**：架构 §7 I-1 协调器裁定**不在已批准 F005 范围**（计划 scope 未含）；A10 仅由结构化列数据层满足（V10/B28）。新增列表参数走变更控制。
- **完整 T38/T39**：T38 的「VM 容量未知为 null、disk_gb 单位」与 T39 的「VM 登记不因超容量被拒、speed_mbps 标称速率」分别归 F006/F007+；F005 仅承载硬件侧（T38 硬件字段、T39 cpu_cores 物理核）。**不声明 T38/T39 完整通过**。
- **完整 T37**：默认值/Role 显式 null/接口类型不推断中，Resource 部分由 F004 覆盖；F005 不新增默认值语义（硬件无默认，省略即 null），不声明 T37 完整通过。
- **T23/T24 完整回归**：类型明细跟随 Resource 的删除/恢复在 F005 仅覆盖 BareMetalDetail 子集；Interface/VM/Service 明细归 F007+；不声明完整 T23/T24 通过。
- **完整 §31 跨功能回归与 §32 上线验收**：归后续 Feature / 上线验收（F016）；Feature 通过 ≠ 上线授权。
- **SN 全局搜索 / 模糊搜索**：§17 全局搜索、pg_trgm/GIN 归 F013；F005 不引入、不断言 SN 搜索。
- **真实浏览器 DOM 渲染**：非 F005 必要判据（同 F001–F004），前端以构建 + client 机制级 +（如要求）入口真实 API 集成为准。

---

## 7. 环境可执行性评估与风险

| 项 | 评估 | 处理 |
| --- | --- | --- |
| V1–V13、B1–B25/B28/B29（真实 PG + 后端集成） | Docker/Compose 可用（F001–F004 已证）；**可执行** | 无 PG 时相关项 BLOCKED，不降验收 |
| V14/B26/B27 迁移（0005 定稿） | DATABASE Gate v1 已定稿 | TE-1 已实际执行（真实 PG up/down/up + 回填）；结果见 TE-1 |
| B22/B23 并发与回滚 | 需真实并发提交 fixture | 复用 `committed_engine`；断言最终持久化与 `current_version` |
| B25 物理 CASCADE | API 无物理删除路径 | raw SQL 机制级验证 FK `confdeltype='c'`，报告显式标注 |
| V15 前端 | 构建 + client 机制级 | 若真实前后端集成要求，经入口 Nginx 验证；CSRF 端口风险承 F004 TE-1 |
| DATABASE/CONTRACT 定稿状态 | **已解除**：DB v1 / Contract v2 / D01 v4 均已定稿并经 TD-2 逐项核对 | 风险关闭；差异仅 F005-TD-1-01 FK 名文本，已修正 |
| 字符串长度/空串语义（DR-52 定稿） | **已解除**：Contract v2 §2.4 + D01 v4 §5.4 固定空/纯空白→422（不转 null）、≤255 code point | B12 按定稿执行（TE-1） |
| `created_at` 是否加入 detail | **已解除**：DB-D48 明确不设任何时间戳列 | V13/B29 按“无时间戳列”执行（TE-1） |

---

## 8. OPEN 复核项（TD-1 提出，TD-2 全部关闭）

> **TD-2（2026-10-09）状态：全部 CLOSED。** DATABASE Gate（`docs/database/f005-bare-metal.md` v1）、CONTRACT Gate（`docs/api/F004.md` v2）与 D01 v4 已定稿；下表各假设逐项与定稿核对，无判据差异（除 F005-TD-1-01 FK 名文本，已于 TD-2 修正）。TD-1 的「待定稿假设」不再作为执行依据，TEST 以定稿 Contract/DB/D01 为准。

### 8-A. OPEN 关闭记录

| # | TD-1 假设 | 状态 | 定稿核对（依据 / 影响） |
| --- | --- | --- | --- |
| 1 | 表 `bare_metal_details` 列/约束名/FK（§0/V13/B5–B8/B19/B25/B29） | **CLOSED** | DB v1 §2 + 0005 迁移：`pk_bare_metal_details`、`fk_bare_metal_details_resource_id_resources`、5 `ck_*_format`、4 `ck_*_range`、`ck_bare_metal_details_metadata_object`；FK 名修正（F005-TD-1-01） |
| 2 | 9 字段全部 nullable、未知存 null 不写 0；`gpu_count=0` 语义（A1–A3） | **CLOSED** | DB-D46/DB-D49；Contract v2 §2.4；9 列 nullable，未知 null，`gpu_count=0` 接受且可区分 |
| 3 | 数值 CHECK 上限（1..2147483647 / 0..2147483647）（B8） | **CLOSED** | DB-D46；0005 CHECK 逐字一致 |
| 4 | 字符串 trim 非空 ≤255、空/纯空白 422 vs null（DR-52，B12） | **CLOSED** | Contract v2 §2.4；D01 v4 §5.4：≤255 code point，空/纯空白→422（不转 null）；DB 为 backstop |
| 5 | `hardware` 嵌套结构、VM `null`、整体 null→422（DR-47/DR-51，A7/V12/B13/B14/B18） | **CLOSED** | Contract v2 §2.4/§3/§6：BARE_METAL 对象、VM `null`；VM 请求含 hardware→422；整体 null/非对象/未知键→422 |
| 6 | PATCH 子字段 `exclude_unset` 语义（V16/B16/B17） | **CLOSED** | Contract v2 §2.4/§6.4：子字段级省略=保持、显式 null=清空 |
| 7 | `metadata` JSONB object、默认 `{}`、整值替换与请求暴露（B19） | **CLOSED** | DB-D47；Contract v2 §2.4：`hardware.metadata` 暴露、整值替换、默认 `{}`、object CHECK |
| 8 | detail 无 `deleted_at/version`；`created_at` 可选（V13/B29） | **CLOSED** | DB-D48：`deleted_at/version/created_at/updated_at` 全不设 |
| 9 | 迁移 `0005_bare_metal_details` 单 head、回填 `WHERE resource_type='BARE_METAL'`（V14/B26/B27） | **CLOSED** | DB-D51；0005 迁移：单一 head、回填 SQL 一致；TE-1 实际验证 |
| 10 | 硬件变更并入 Resource 审计快照、白名单扩 `hardware`、权限随 Resource（V8/B20/B21） | **CLOSED** | Contract v2 §8/§1.3：快照白名单扩 `hardware`（VM=null）；硬件读写随 Resource WRITE/READ |

TD-1 未闭合项已由 TD-2 关闭；实现与 Contract 未发生导致判据差异的后续变更。

---

## Test Execution

- **版本**：TE-1
- **日期**：2026-10-09
- **角色**：Tester（TEST 模式）
- **结论**：`READY FOR REVIEW`
- **执行基线**：Contract `docs/api/F004.md` v2（2026-10-09）、DATABASE `docs/database/f005-bare-metal.md` v1（2026-10-08）、D01 `d01-conventions.md` v4、architecture §9 `READY FOR IMPLEMENTATION`、implementation.md（BACKEND + FRONTEND COMPLETE）；TD-2（含 F005-TD-1-01 修正）。
- **代码基线**：`feature/F005-baremetal-hardware`，HEAD `8f5dabe`（backend/frontend COMPLETE 检查点），起始工作区干净。
- **独立性声明**：Backend pytest 由 Tester 独立重跑（不复用实现者数字）；迁移、约束、结构化查询由 Tester 在独立库（`csm_verify`/`csm_test`）以 raw SQL / Alembic 直接执行；Compose 集成由 Tester 经入口 Nginx `127.0.0.1:18098` 独立 curl。

### 环境

| 项 | 值 |
| --- | --- |
| 后端测试镜像 | `docker build --target test -t csm-backend-f005te1 ./backend`（Python 3.12.15，pytest 8.4.2） |
| 数据库 | 独立容器 `f005te1-db`（`postgres:16`），网络 `f005te1-net`；测试库 `csm_test`、独立验证库 `csm_verify` |
| 集成（后端） | `TEST_DATABASE_URL=postgresql+psycopg://csm:change-me@f005te1-db:5432/csm_test`（DB-D10 护栏：库名含 `test`、≠ `DATABASE_URL`） |
| 前端 | Node v22.23.2 / npm 12.0.2；`npm run typecheck`、`npm run build`、`npm run smoke:client` |
| Compose 全链路 | `docker compose -p f005te1`（独立项目名/卷），入口 Nginx `127.0.0.1:18098`（非默认端口；`deploy/nginx/nginx.conf` 保留 `Host` 端口以使同源 CSRF 生效） |
| 清理 | `compose -p f005te1 down -v`、`docker rm -f f005te1-db`、`docker network rm f005te1-net`、删临时镜像 `csm-backend-f005te1`、`f005te1-*`；残留检查无 f005 容器/网络/镜像 |

### 实际执行命令与输出摘要

| # | 命令 | 结果 |
| --- | --- | --- |
| 1 | `pytest tests -q`（真实 PG `csm_test`） | **151 passed, 1 skipped**（skip=`test_migrations.py:101` 非 superuser 扩展假设：连接角色 `csm` 为 superuser 的环境限制，非 F005 缺陷；与 F004 基线相同） |
| 2 | `pytest tests/integration/test_bare_metal.py tests/integration/test_bare_metal_constraints.py -v` | **32 passed**（19 API + 13 constraint/migration F005 专属用例，逐条 PASS） |
| 3 | 独立库 `csm_verify`：`alembic heads` / `upgrade head` / `current` | `0005_bare_metal_details (head)` 单一 head；升级 0001→0005 全部 Running；`current` = `0005_bare_metal_details (head)` |
| 4 | 独立 `downgrade 0004_resources`→`upgrade head` + 预置 BARE_METAL/VM 回填 | down 后 `bare_metal_details` 及触发器函数消失、0004 对象（resources/clusters/audit_logs/users/user_sessions）保留；up 后 BARE_METAL 得全 null detail 行（`metadata={}`）、VM 无行；重复 `upgrade head` 幂等（detail 计数保持 1） |
| 5 | 独立 raw SQL 结构/约束探测（`csm_verify`/`csm_test`） | 11 列（`resource_id` PK + 9 硬件 nullable + `metadata` NOT NULL DEFAULT `'{}'`，无时间戳）；约束集 12 项；仅 PK 索引；PK+FK `confdeltype='c'`；类型触发器拒 VM/不存在资源；负例 CHECK/manufacturer untrimmed/metadata array 均拒；物理 DELETE 级联；`gpu_count=0` vs NULL 可区分 |
| 6 | 结构化查询（`csm_test` raw SQL） | `WHERE cpu_cores>=64 ORDER BY memory_mb DESC`、`count/avg/sum` 均正确；含非空 `metadata` 行不破坏结构化查询；9 字段为 varchar/integer 列、仅 `metadata` 为 jsonb |
| 7 | `npm run typecheck` / `npm run build` / `npm run smoke:client` | typecheck 0 错误；build 通过（47 modules）；smoke **52 passed, 0 failed**（F005 新增 9 项） |
| 8 | Compose/Nginx 全链路 curl（18098） | 登录→建 Cluster→建 BARE_METAL（硬件）→省略/null→VM→PATCH→错误语义→activity；状态码与错误信封符合 Contract（详见下） |
| 9 | `python3 scripts/validate_project_state.py` | `PROJECT STATE VALID`（结构校验；批准/Git 证据另行核对，非本报告结论） |

### V1–V16 执行结果（TD-2 → TE-1）

| 验证项 | 结果 | 证据 / 说明 |
| --- | --- | --- |
| V1 省略/null → null | **PASS** | 用例 1/2/8；POST 省略 `hardware` 与显式各子字段 `null` 均 201，响应 9 字段全 `null`、`metadata={}`；raw DB 各列 `IS NULL`（非 0） |
| V2 gpu_count 0 vs null | **PASS** | 用例 2/5/8；`gpu_count=0`→201 存/返回 `0`；不传→`null`；raw `=0` vs `IS NULL` 可区分；前端 0 显示「明确无 GPU」、null 显示占位 |
| V3 数值范围 422 | **PASS** | 用例 2/5/8；`cpu_sockets/cpu_cores/memory_mb∈{0,-1,-100}`、`gpu_count=-1`→422 `VALIDATION_ERROR`；正例（`cpu_cores=2147483647`、`gpu_count=0`）201；raw CHECK 拒越界 |
| V4 MiB 单位一致 | **PASS** | 用例 2/5/8；`memory_mb=1572864` 原样存/返回（无 ×1000/÷1024）；前端 `1572864 MiB（= 1536 GiB）`（1 GiB=1024 MiB） |
| V5 cpu_cores 物理核 + 静态 | **PASS** | 用例 2/8；`cpu_sockets=2,cpu_cores=192` 存/返回 192；`cpu_cores=384` 亦被接受（无 sockets×cores 推导）；源码核对无主机探测/自动计算、无派生列 |
| V6 SN 无唯一 | **PASS** | 用例 2/5/8；两 BARE_METAL 同 SN 均 201；PATCH SN 无 409；`pg_indexes` 无 SN unique 索引 |
| V7 响应字段 + 前端区域 | **PASS** | 用例 2/5/7/8；`hardware` 含 CPU（cpu_model/sockets/cores）、Memory（memory_mb）、GPU（gpu_model/count）、Manufacturer/Model/SN；前端 HardwarePanel 仅 BARE_METAL 渲染、未知「—（未知）」 |
| V8 审计 + 权限 | **PASS** | 用例 2/8；CREATE/UPDATE/DELETE/RESTORE 各一行 audit，快照含 `hardware`；VIEWER 读 200/写 403 `FORBIDDEN{permission}`、EDITOR 写 200、未认证 401；服务端强制（跨源写 403 `csrf`） |
| V9 生命周期 + V13 CASCADE 机制级 | **PASS** | 用例 2/5/8；路由清单无 `.../hardware`、`/bare-metal-details`（404）；软删后默认 404、`deleted=true` 可见、restore 后硬件不变；raw 物理 DELETE 级联（`confdeltype='c'`）；**物理级联为机制级**（API 无物理删除路径） |
| V10 结构化查询 + V13 列/约束 | **PASS** | 用例 5/6；`WHERE/ORDER BY/count/avg/sum` 可用；9 字段为结构化列而非 JSONB；`metadata` object CHECK 且不破坏结构化查询；未新增列表级 hardware 过滤参数（I-1） |
| V12 VM 拒绝 hardware | **PASS** | 用例 2/8；VM POST/PATCH 含 `hardware`（含显式 `null`）→422（不静默忽略，DR-51）；VM 响应 `hardware=null`；raw 无 VM detail 行（触发器 AND 应用双保证） |
| V13 DB 约束/列集合 | **PASS** | 用例 2/5；`resource_id` 为 PK+FK `ON DELETE CASCADE`（`confdeltype='c'`）；9 列 nullable；4 范围 CHECK + 5 格式 CHECK + object CHECK；无 `deleted_at/version/created_at/updated_at`；仅 PK 索引 |
| V14 迁移 0005 up/down/up + 回填 | **PASS** | 用例 3/4；`alembic heads` 单一 `0005_bare_metal_details`；down 后表/触发器/函数消失且 0004 对象保留；re-up 集合一致；回填每个既有 BARE_METAL 得全 null 行、VM 无行、重复 up 不重复 |
| V15 Hardware 区域与状态 + 集成 | **PASS**（构建+机制级+入口集成） | 用例 7/8；typecheck/build 通过；smoke 52/52；经入口 Nginx 真实 API 往返（创建/读取/编辑/错误）；Loading/Success/Empty/Error 与未知占位经源码核对；真实浏览器 DOM 非本 Feature 必要判据 |
| V16 PATCH 子字段语义 | **PASS** | 用例 2/8；PATCH 仅含子字段时其余保持原值；显式 `null` 清空该 nullable 子字段；`hardware` 整体 `null`/非对象/含未知键 →422；metadata 整值替换 |

### B1–B29 执行结果

| 编号 | 结果 | 证据摘要 |
| --- | --- | --- |
| B1 hardware 省略 | PASS | 用例 2/5/8；恰一行、9 列全 `IS NULL`/`metadata={}`、响应全 null |
| B2 各字段显式 null | PASS | 用例 2/5；对应列 `IS NULL`、响应 null（非 0） |
| B3 部分登记其余未知 | PASS | 用例 2；已登记落值、其余 `IS NULL` |
| B4 gpu_count=0 vs null | PASS | 用例 2/5/8；存/返回可区分 |
| B5 正整数非正值拒绝 | PASS | 用例 2/5；API 422 + raw CHECK 拒 0/负 |
| B6 gpu_count 负值/零边界 | PASS | 用例 2/5；`-1`→422、`0`→201；raw `-1` 被 CHECK 拒 |
| B7 非整数/类型错误 | PASS | 用例 2；`"192"`/`true`/`1.5`/`[]`/`{}` →422（严格整数，不静默转换） |
| B8 数值上限 | PASS | 用例 2/5；`2147483647` 接受、`2147483648`→422；raw CHECK 上限内 |
| B9 memory_mb MiB 一致 | PASS | 用例 2/5/8；`1572864` 原样；展示 `1536 GiB` 等价 |
| B10 cpu_cores 物理核 | PASS | 用例 2/8；192 存 192；384 亦接受（无推导）；静态无 HT 计数 |
| B11 SN 可重复 | PASS | 用例 2/5/8；同 SN 均成功；无 unique 索引 |
| B12 字符串 trim/空/超长 | PASS | 用例 2/5；`"  Dell  "`→`Dell`；`""`/纯空白/256 字符→422；255 字符→201；raw 未 trim/空/超长被 CHECK 拒 |
| B13 hardware 整体非法 | PASS | 用例 2/8；`[]`/`"x"`/`null`/`{unknown_key:1}` →422 |
| B14 VM 提交 hardware | PASS | 用例 2/5/8；POST/PATCH→422；详情 `hardware=null`；raw VM 无 detail 行 |
| B15 BARE_METAL 行存在性 | PASS | 用例 2/5；每个 BARE_METAL 恰一行（PK），VM 无行 |
| B16 PATCH 子字段省略保持 | PASS | 用例 2/8；PATCH 仅 `gpu_count` 后其它子字段保持 |
| B17 PATCH 显式 null 清空 | PASS | 用例 2/8；`manufacturer:null` 后该列为 NULL，其余保持 |
| B18 PATCH hardware 整体 null/非对象 | PASS | 用例 2/8；422；库值不变（hardware 不可清空） |
| B19 metadata JSONB object | PASS | 用例 2/5；raw `[]`/`"x"`/`null`/`1` 被 CHECK 拒；合法 object 存储；整值替换（旧键消失） |
| B20 硬件变更审计 | PASS | 用例 2/8；CREATE 快照含硬件；UPDATE `before/after` 含硬件字段；`object_type="resource"`、object_id=Resource UUID；VM 快照 `hardware=null` |
| B21 权限矩阵（硬件随 Resource） | PASS | 用例 2/8；VIEWER 读 200/写 403 `permission`；EDITOR 写 201/200；未认证 401；服务端强制 |
| B22 乐观锁并发（真提交） | PASS | 用例 2；两独立会话同 version，一方 200 且 `version+1`、另一方 409 `VERSION_CONFLICT{current_version:2}`；最终库值来自成功方 |
| B23 硬件变更同事务回滚 | PASS | 用例 2；注入 audit 失败后明细列变更与 audit 同事务双回滚，持久状态断言为旧值 |
| B24 生命周期随 Resource | PASS | 用例 2/8；软删后详情默认 404、`deleted=true` 可见、restore 后数据不变；路由清单无独立端点；Resource 删除始终成功 |
| B25 FK CASCADE（机制级） | PASS | 用例 2/5；raw 物理 `DELETE` 后 detail 行级联删除；软删不删行 |
| B26 迁移 up/down/up | PASS | 用例 3/4；单一 head、各步 0、down 与 re-up 对象集合一致 |
| B27 迁移回填断言 | PASS | 用例 4；预置 BARE_METAL 得全 null 行、VM 无行、再次 up 不重复 |
| B28 结构化列查询/排序/统计 | PASS | 用例 6；`WHERE/ORDER BY/count/avg/sum` 正确；含 `metadata` 行不破坏；9 字段在结构化列 |
| B29 detail 列集合与时间戳裁定 | PASS | 用例 5；无 `deleted_at/version/created_at/updated_at`；`metadata NOT NULL DEFAULT '{}'` |

### 数据库 / 接口 / 前端 / 集成结果

- **数据库（真实 PG，`csm_verify` raw SQL + `csm_test` pytest）**：`bare_metal_details` 列/约束/触发器与 DB v1 逐项一致；FK `ON DELETE CASCADE`（`confdeltype='c'`）；类型触发器 `trg_bare_metal_details_type_match` 拒 VM 与不存在资源；范围/格式/JSONB object CHECK 生效；`gpu_count=0` 与 `null` 可区分；仅 PK 索引、无 SN unique；迁移 0005 对称可逆、单一 head、回填正确且幂等。**PASS**
- **接口（ASGI + 全链路 Nginx 18098）**：POST/PATCH 硬件响应内容、类型、nullable、业务边界、非法输入、错误语义符合 Contract；`VALIDATION_ERROR`（`hardware`/`hardware.<field>`）/`FORBIDDEN{permission|csrf}`/`AUTH_REQUIRED`；字符串 trim（`  Dell  `→`Dell`）、严格整数、范围 422；VM 提交 hardware→422 且响应 null；未认证 401。只读端点无业务写副作用。**PASS**
- **前端**：typecheck/build 通过；client 机制级 52 项通过；HardwarePanel 仅 BARE_METAL、未知占位、`gpu_count=0`「明确无 GPU」、MiB/GiB 标注、表单子字段级 PATCH 经源码与 smoke 核对。真实浏览器 DOM 非本 Feature 必要判据。**PASS**
- **集成（Compose 经入口 Nginx）**：`migrate`/`bootstrap` Exited(0)，`alembic_version=0005_bare_metal_details`，backend healthy；登录→建 Cluster→建 BARE_METAL（硬件）→省略/null→VM 拒绝→PATCH 子字段→activity 快照全链路符合 Contract；VIEWER 读 200/写 403、EDITOR 写 200 经真实 HTTP 与 audit operator 核对。**PASS**

### 验收映射 A1–A10 结论

| # | 结论 | 证据 |
| --- | --- | --- |
| A1 | **PASS** | V1/V16/V13；B1–B3 |
| A2 | **PASS**（前端展示 + 后端/DB） | V2/V15；B4 |
| A3 | **PASS** | V3；B5–B8 |
| A4 | **PASS** | V4/V15；B9 |
| A5 | **PASS** | V5；B10 |
| A6 | **PASS** | V6；B11 |
| A7 | **PASS**（后端 + 前端机制级） | V7/V15 |
| A8 | **PASS**（端到端审计 + 权限） | V8/V11；B20/B21 |
| A9 | **PASS**（端到端软删/恢复 + 物理 CASCADE 机制级） | V9/V13；B24/B25 |
| A10 | **PASS**（数据层结构化查询；列表级过滤不在范围） | V10/V13；B28 |

### Defects

| ID | Severity | Layer | Location | 证据 / 期望与实际 | 影响 | Owner | 必须修复 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| F005-TD-1-01 | LOW（已关闭） | 文档（Test Design） | `test-report.md` TD-1 §5 | TD-1 将 FK 约束名写作 `fk_bare_metal_details_resource_id`，DB v1 定稿为 `fk_bare_metal_details_resource_id_resources`；TD-2 已改正，验收判据（`ON DELETE CASCADE`/`confdeltype='c'`）不变 | 仅文档笔误，无实现影响 | Tester | 是（已在 TD-2 修复） |

未发现新的实现缺陷。

### 未验证项与口径声明

- **B25 物理 FK CASCADE 为机制级**：API 无物理删除 Resource 路径（删除为软删），CASCADE 仅经 raw SQL 物理 `DELETE` 验证；软删随 Resource 隐藏/恢复为端到端。不得表述为独立端到端。
- **B23 审计回滚**：以 monkeypatch 注入 audit 失败制造同事务失败，断言最终持久化；非真实进程崩溃注入。
- **真实浏览器 DOM 渲染**：未自动化；前端以 typecheck + build + client 机制级 + 入口 Nginx 真实 API 集成为准（同 F001–F004）。
- **A2/A7 前端展示**：以 smoke 机制级 + 源码核对为准，未做真实浏览器 E2E。
- **数据完整性映射**：`.pi/skills/data-integrity/SKILL.md` 对应表全部适用项已在 §0 与本节覆盖；Unicode Cc/Cf 仅应用层保证、DB 为 ASCII backstop（DB I-3 已知差异，非本 Feature 缺陷）。
- **完整 T38/T39/T37/T23/T24/T25/T26**：F005 仅承载硬件侧（T38 硬件字段、T39 cpu_cores 物理核）与 BareMetalDetail 子集；VM 容量/Host 校验、VM 侧与 speed_mbps、Interface/Network/Pool、跨 Feature 权限/审计回归归 F006/F007+/上线验收。**不声明上述条款完整通过**。
- **导入（§24）**：硬件字段导入与单位一致性归 F014；F005 仅固化校验与 MiB 口径。
- **列表级 hardware 过滤/排序**：不在已批准 F005 范围（I-1）；A10 仅数据层。
- **完整 §31 跨功能回归与 §32 上线验收**：不在本 Feature；Feature 通过 ≠ 上线授权。

---

### Git 声明

```text
GIT: NONE
```

本次活动（TD-2 文档更新 + TE-1 独立测试执行）仅写入 `docs/features/F005/test-report.md`，未修改 backend/frontend 业务实现，未暂存/提交/切换分支。`feature/F005-baremetal-hardware` 工作区在本次开始前 `git status --short` 为空，结束时仅该报告文件为 modified。