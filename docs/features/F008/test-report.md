# F008 Network 网络管理 — Test Report

本文件同时承载 TEST_DESIGN 与 TEST（TEST 阶段在同一文件追加执行结果）。两阶段分别记录版本、结论与证据；TEST_DESIGN 不填充执行 PASS。

---

## Test Design

- **版本**：TD-1 → **TD-2（当前）**
- **日期**：2026-10-09
- **角色**：Tester（TEST_DESIGN 模式）
- **结论**：`TEST DESIGN READY`（TD-2）

> **TD-2（当前）**：在 TD-1 基础上逐项核对并关闭 §8 OPEN-1–15（依据 DATABASE `docs/database/f008-network.md` v1、Contract `docs/api/F008.md` v1、D01 `d01-conventions.md` v7 §5.7 与真库结构，见 §8A）。TD-1 的结论、版本记录与全部验证项设计保留于下文，不删除。TD-2 仅表示方案可验证、OPEN 已关闭，**不表示测试已执行**；执行结果见 Test Execution（TE-1）。TD-2 发现 1 个数据库约束实现缺陷（DEF-F008-TE1-01，见 TE-1），已转 Backend 修复。

- **依据**：
  - `docs/product/requirements-v3.md` revision 3（§4、§4.1、§11、§11.1、§12.1、§13、§14、§18、§20–§23、§25–§28、§31 T14/T16/T24/T25/T29/T30/T37/T38/T40/T41、§35.2 Q02-A/Q04-A/Q04-B/Q10-A/Q10-B、§35.3 D01/D02）
  - `docs/features/F008/product.md`（`READY FOR ARCHITECT`；A1–A22、I-1–I-6、明确排除项）
  - `docs/features/F008/architecture.md`（`READY FOR DESIGN`；§2 API 裁定、§3 约束、§4 DB 影响、§5 D01 补齐、§6 验证策略、DR-89–DR-101）
  - `docs/architecture/d01-conventions.md` v6（§3/§5/§5.2/§5.6/§6/§7；Network 字段口径待 v7 §5.7）
  - `docs/api/F004.md` v3（错误码/权限/软删可见性/引用检查/恢复重检/审计口径）
  - `docs/database/f001-baseline.md`（DB-D2 btree_gist 推迟；F008/F009 承担启用）、`docs/database/f003-cluster.md` v2、`docs/database/f004-resource.md` v1
  - `docs/features/F007/test-report.md`（TD 模式、夹具/环境、机制级口径）
  - `docs/project/handoff.md`、`docs/project/implementation-rules.md`、`.pi/skills/data-integrity/SKILL.md`、`AGENTS.md`
- **状态属性**：TD-1 READY 仅表示 A1–A22 已映射到可观察判据、边界/并发场景可执行、夹具与可验证性检查已建立；**不代表测试已运行、不填充执行 PASS、不批准实现或合并**。数据库设计（`docs/database/f008-network.md`）与 API Contract（`docs/api/F008.md`）尚未定稿，§8 列 OPEN 待 DATABASE/CONTRACT Gate 后由 TD-2 逐项关闭。跨功能完整 §31 回归与 §32 上线验收不在本 Feature（见 §5）。

### 版本记录

| 版本 | 日期 | 变更 |
| --- | --- | --- |
| TD-1 | 2026-10-09 | 初版：A1–A22 映射 V1–V30，边界/并发 B1–B36，夹具/环境设计，可验证性检查，不适用项，§8 OPEN 复核项（待 DATABASE/CONTRACT/D01 v7 定稿后由 TD-2 关闭）。 |
| TD-2 | 2026-10-09 | 逐项核对 DATABASE v1 / Contract v1 / D01 v7 §5.7 与真库结构，关闭 §8 OPEN-1–15；记录 2 项数据库文档补注（排他约束 `inet_ops`、host 位归一化归属）；发现 1 个 DB gateway CHECK 缺陷。 |

> 待复核基线：`docs/database/f008-network.md`（DATABASE Gate，未定稿）、`docs/api/F008.md`（CONTRACT Gate，未定稿）、`d01-conventions.md` v7 §5.7（DR-101，未定稿）。TD-1 的表名/列名/约束名/错误路径/并发机制均按 architecture 草案假设，TD-2 逐项核对后方可作为执行依据。

---

### 0. 数据完整性对应表（F008 范围）

方法依据 `.pi/skills/data-integrity/SKILL.md`；DB 列/约束以 DATABASE Gate 定稿为准（TD-1 为草案）。

| 规则依据 | 作用域/写入入口 | 数据库保证（草案，待签核） | 业务层保证 | 并发/生命周期边界 | 验证 |
| --- | --- | --- | --- | --- | --- |
| §4.1/§11（同 Cluster 未删 name 大小写不敏感唯一，删除后复用） | POST/PATCH `/api/v1/networks` | `uq_networks_cluster_id_name_key UNIQUE(cluster_id,name_key) WHERE deleted_at IS NULL`；`name varchar(255)` + trim/非空/Cc-Cf CHECK | `name_key=ASCII_lower(btrim(name))`；冲突→409 `unique_conflict(field:"name")` | 软删放行复用；恢复重检；PG 兜底 | V1/V2/V4/V20、B1–B8/B30 |
| §11/§27（同 Cluster 未删 CIDR 不重叠，INACTIVE 参与） | POST/PATCH `/api/v1/networks` | `EXCLUDE USING gist (cluster_id WITH =, cidr WITH &&) WHERE (deleted_at IS NULL)`；`cidr cidr`；首次启用 btree_gist | 重叠映射 409 `range_overlap(field:"cidr",conflicts[])` | 排他约束写入原子兜底；恢复置 deleted_at=null 重受约束 | V5/V6/V23、B9–B12/B31/B34 |
| §11/§4.1（cluster 创建必填、存在未软删） | POST；DDL | `cluster_id UUID NOT NULL FK→clusters ON DELETE RESTRICT` + `ix_networks_cluster_id` | 缺失/不存在/软删→422 | 与 Cluster 软删并发（跨 Feature，见 B33） | V8、B13–B14/B33 |
| §11/§11.1（gateway 属 CIDR 基础可用地址、非禁用、/32 必空、排除可分配） | POST/PATCH | `gateway inet NULL`；应用主导 + DB CHECK backstop（可行性待 Database） | 基础可用 + 非禁用，否则 422；供下游排除 | 改 CIDR 时重检 gateway | V10/V11/V22、B15–B17 |
| §11/T37（status 默认 ACTIVE 2 值；auto_allocate 默认 false） | POST/PATCH | `status varchar(16) NOT NULL DEFAULT 'ACTIVE'` + CHECK；`auto_allocate boolean NOT NULL DEFAULT false` | 省略→默认；非法→422 | INACTIVE 仍参与重叠检查 | V12/V13/V14、B18–B20 |
| §21/§27（软删/恢复；有未删 Pool/IP 引用禁删禁改 CIDR/Cluster；不级联） | DELETE/PATCH/POST restore | 复用 F003/F004 软删与引用检查；FK RESTRICT；F008 依赖检查器注册表（初始空集） | 有引用→409 `reference_exists(references[])`；改 cidr/cluster 对 networks 行 `FOR UPDATE` | 恢复重检名称/Cluster/CIDR/引用，失败不覆盖 | V9/V15/V16、B21–B25/B32/B34/B36 |
| §22（CREATE/UPDATE/DELETE/RESTORE 写 Audit 同事务） | Service `AuditService.record` | 复用 `audit_logs` append-only | `object_type="network"`；白名单字段；异常同回滚 | 版本冲突无静默重试 | V18、B27 |
| §23（权限矩阵；乐观锁） | `/api/v1/networks*` | 复用 `version integer NOT NULL DEFAULT 1 CHECK >=1` | `require_permission`；条件 UPDATE `WHERE version=:expected`，rowcount=0→409 | 两连接同 version 仅一成功 | V17、B26/B28 |
| §11/DR-95（metadata Network 自有 JSONB） | POST/PATCH | `metadata jsonb NOT NULL DEFAULT '{}'` + object CHECK | object 校验；整值替换 | 与 Resource metadata 解耦 | V24、B29 |
| §27/DR-100（迁移 0008） | Alembic `0008_networks` | `down_revision=0007`，首次 `CREATE EXTENSION IF NOT EXISTS btree_gist`，全表新建无回填，对称可逆 | — | 真库 up/down/up | V23、B35 |

---

## 1. 验收映射（product.md A1–A22 → 验证项）

执行环境：`Compose` = 干净环境 `docker compose up -d`；`真实 PG` = 独立测试库（库名含 `test`）；`后端集成` = ASGI 应用 + 真实 PG（非 SQLite）；`静态` = 仓库/路由清单/源码检查；`前端` = 构建 + client 机制级（真实 API 集成以入口 Nginx 为准）。

| 验收 | 验证项 | 环境 | 可观察判据（PASS / FAIL） |
| --- | --- | --- | --- |
| A1 同 Cluster 名大小写不敏感重名拒（409） | **V1**；**V20** DB | 后端集成 + 真实 PG | PASS：同 cluster `MGMT`/`mgmt` 第二次 POST→409 `CONFLICT{reason:"unique_conflict",field:"name"}`；库中一行；raw 直插同 `(cluster_id,name_key)` 未删被部分唯一拒。FAIL：创建成功、落库两行、无兜底 |
| A2 不同 Cluster 同名允许 | **V2** | 后端集成 + 真实 PG | PASS：两 cluster 各建同名→均 201，两行。FAIL：第二个被拒 |
| A3 trim/空名/控制字符拒；内部普通空格保留不合并 | **V3** | 后端集成 + 真实 PG | PASS：`"  MGMT  "`→201 落库 `MGMT`；`""`/`"   "`/含 Cc/Cf→422；`"MG MT"`/`"MG  MT"`（普通空格）→201 且内部空格原样保留（不合并）。FAIL：不 trim、内部空格被合并或被误拒、空名落库 |
| A4 软删后同名可重建；存活同名失败；复用后恢复失败不覆盖 | **V4**；**V16** | 后端集成 + 真实 PG | PASS：软删同名→重建 201（新 id）；存活同名→创建失败；旧对象 restore→409 且新对象不被覆盖、旧对象保持软删。FAIL：软删后仍拒、覆盖新对象 |
| A5 同 Cluster CIDR 重叠（含完全相同）拒；跨 Cluster 允许 | **V5**；**V20** | 后端集成 + 真实 PG | PASS：同 cluster 重叠/相同 CIDR→409 `range_overlap(field:"cidr")`；跨 cluster 同 CIDR→201；raw 直插重叠被排他约束拒。FAIL：重叠成功、跨 cluster 被拒 |
| A6 INACTIVE 仍参与重叠检查 | **V6** | 后端集成 + 真实 PG | PASS：INACTIVE 未删 Network 与新建重叠→409；与软删对象重叠→允许。FAIL：INACTIVE 被排除、软删参与 |
| A7 非 IPv4/非法 CIDR →422 | **V7** | 后端集成 + 真实 PG | PASS：`10.0.0.0/33`、`10.0.0.256/24`、`not-a-cidr`、IPv6、裸 `10.0.0.1`（无掩码）→422；合法→201。FAIL：非法被接受 |
| A8 cluster 缺失/不存在/软删→422 | **V8** | 后端集成 + 真实 PG | PASS：省略/`null`/`""`→422；随机 UUID→422；指向软删 Cluster→422；无 Network 行。FAIL：任一被接受 |
| A9 有未删 Pool/IP 改 cidr/cluster 拒并返回引用；无引用按约束允许并重检 | **V9**；**V30** | 后端集成 + 真实 PG | PASS：注册非空引用（测试桩）时 PATCH cidr/cluster→409 `reference_exists` + `references[]`；无引用时改名/改 cidr 依重叠/名称约束允许且重检目标 Cluster。FAIL：有引用被改、无引用被误拒 |
| A10 gateway 空允许；不属于 CIDR 基础可用地址或禁用范围→422 | **V10** | 后端集成 + 真实 PG | PASS：省略/`null`→201；网络地址/广播地址→422；`0.0.0.0`、`127.x`、`169.254.x`、`224.x`、`240.x`（禁用）→422；/32 gateway 非空→422。FAIL：越界或禁用地址被接受 |
| A11 gateway 从可分配集合排除，容量不计 | **V11**；**V22** | 后端集成 + 静态/F009 | PASS（F008 侧）：导出/定义的基础可用集合接口在给定 gateway 时排除该地址；容量/分配共用同一边界（静态核对与下游 F009/F010 契约一致）。FAIL：gateway 仍计入可分配。**容量数值归 F013** |
| A12 status 省略→ACTIVE；显式按值；非法→422 | **V12** | 后端集成 + 真实 PG | PASS：省略→`ACTIVE`；显式 `INACTIVE` 落库；`ACTIVE` 合法；`"active"`/`""`/`null`/其它→422；raw CHECK 拒非法。FAIL：默认错、非法落库 |
| A13 auto_allocate 省略→false；显式按值；不绕过约束 | **V13** | 后端集成 + 真实 PG | PASS：省略→`false`；显式 `true`/`false` 落库一致；`null`→422；静态核对无据 auto_allocate 绕过状态/地址约束。FAIL：默认 true、被忽略、绕过 |
| A14 INACTIVE 允许查询/释放已有 IP、禁新增分配；auto_allocate 不能绕过 | **V14**；F010 | 后端集成 + 静态 | PASS（F008 侧）：INACTIVE Network GET 200；F008 提供状态语义给下游，静态核对无自动分配入口。F010 执行「禁新增分配/允许释放」。FAIL：F008 内实现分配或状态被绕过 |
| A15 有未删 Pool/IP 引用删除拒并返回列表；不级联；无引用可软删 | **V15**；**V30** | 后端集成 + 真实 PG | PASS：DELETE 无引用→204 且写 DELETE audit；有未删引用（注册桩）→409 `reference_exists` + `references[{object_type:"ip_pool"|"ip_address",object_id,label}]`；不级联；软删仅置 `deleted_at`。FAIL：误删、无 references、隐式级联 |
| A16 恢复重检名称唯一/Cluster 有效/CIDR 不重叠/引用；失败不覆盖 | **V16** | 后端集成 + 真实 PG | PASS：软删→restore→200；name 被复用→409 `unique_conflict`；Cluster 仍软删→409 `dependency_deleted`；CIDR 重叠→409 `range_overlap`；失败保持软删且不覆盖新对象。FAIL：restore 成功、覆盖 |
| A17 权限：VIEWER 只读；EDITOR 增改；删/查看已删/恢复 ADMIN | **V17** | 后端集成 + 前端 + Compose | PASS：VIEWER POST/PATCH→403 `permission`、GET 200；EDITOR POST/PATCH 201/200、DELETE/restore 403；ADMIN 成功；未认证 401；服务端强制（静态核对无绕过）。FAIL：越权成功、仅前端隐藏 |
| A18 CREATE/UPDATE/DELETE/RESTORE 写 Audit 同事务；Activity 全角色 | **V18** | 后端集成 + 真实 PG | PASS：四 action 各一条 `audit_logs`（`object_type="network"`、`object_id`=UUID、UPDATE 含 before/after、白名单字段）；GET `/activity` 对三角色均 200；注入 audit 失败时业务与 audit 同回滚。FAIL：缺 action、不同事务、Activity 限权 |
| A19 默认隐藏软删、含 INACTIVE 并可状态过滤；分页/排序/过滤/模糊 | **V19** | 后端集成 + 真实 PG | PASS：默认列表无软删、含 INACTIVE；`status`/`auto_allocate`/`cluster_id`/`q`/`deleted` 过滤正确；分页 `total/page/page_size` 边界正确；`sort∈{name,cidr,status,created_at,updated_at}`+`order` 生效且加 `id` 稳定；非法参数→422。FAIL：软删泄漏、分页/排序/过滤错 |
| A20 DB 对同 Cluster 未删 name（归一化键）唯一与 CIDR 不重叠兜底 | **V20** | 真实 PG + 静态 | PASS：`pg_constraint`/`pg_indexes` 含部分唯一 `(cluster_id,name_key) WHERE deleted_at IS NULL` 与排他约束 `(cluster_id=,cidr&&) WHERE deleted_at IS NULL`；raw 直插存活重名/重叠被拒、软删后同名/同 CIDR 可插。FAIL：缺约束、全量唯一、仅 ORM 层 |
| A21 归一化在 API/导入(F014)/搜索(F013)/DB 一致；仅未删参与唯一 | **V21**；F014/F013 | 后端集成 + 真实 PG + 静态 | PASS（F008 侧）：API 与 DB `name_key` 口径一致（仅 ASCII A-Z→a-z，locale 无关）；软删不参与唯一；向 F014/F013 暴露同口径（静态核对）。F014/F013 执行各自一致性。FAIL：折叠口径不一致、软删参与 |
| A22 CIDR/gateway 边界作为下游 Pool 越界/IP 属于 CIDR/容量共同输入 | **V22**；F009/F010/F013 | 静态 + 跨 Feature | PASS（F008 侧）：F008 暴露基础可用/可分配集合边界供下游复用；不在本 Feature 实现分配或容量数值。FAIL：边界语义不可复用或与下游不一致。**执行归 F009/F010/F013** |

补充验证项（非直接 A 映射）：

| 验证项 | 内容 | 环境 | 判据 |
| --- | --- | --- | --- |
| **V23** 迁移 0008 | Alembic up/down/up + 单一 head + btree_gist 幂等启用 | 真实 PG | PASS：`alembic heads` 单一 `0008_networks`（`down_revision=0007`）；up 建表/约束/索引/扩展；down 逆序且 0007 对象保留、不 drop 扩展；re-up 集合一致；无回填。FAIL：多 head、不对称、扩展重复报错 |
| **V24** metadata JSONB | object CHECK / 整值替换 / 非法类型 | 后端集成 + 真实 PG | PASS：`{}` 默认；object 接受；`[]`/标量→422；raw 非 object 被 CHECK 拒；PATCH 整值替换。FAIL：非法落库、合并语义 |
| **V25** 乐观锁并发 | 两独立连接同 version PATCH | 后端集成 + 真实 PG（真提交） | PASS：一方 200 且 version+1；另一方 409 `VERSION_CONFLICT{current_version}`；最终库值来自成功方，无丢失更新。FAIL：双成功 |
| **V26** PATCH exclude_unset / 不可变 | 省略子字段保持；显式 null 仅清 nullable（gateway/description）；必填显式 null→422；未知/只读字段→422 | 后端集成 | PASS：逐项符合 D01 §4 与 Contract；被拒请求不改库值与 version。FAIL：省略被重置、只读字段被改 |
| **V27** 校验顺序 | POST/PATCH/DELETE/restore 优先级 | 后端集成 | PASS：POST 401→403→body(422)→cluster(422)→name 唯一(409)→cidr/gateway(422)→重叠(409)→写+Audit→201；PATCH 401→403→body(422)→可见性(404)→version(409)→name 唯一(409)→cidr/gateway(422)→引用(409)→重叠(409)→写+Audit→200；DELETE 401→403→对象(404)→version(422)→版本(409)→引用(409)→软删。FAIL：顺序错误 |
| **V28** 响应契约 | Network 响应字段/嵌套 | 后端集成 | PASS：含 `id、cluster{id,code,name}、name、cidr、gateway|null、status、auto_allocate、description|null、metadata、version、created_at/updated_at、deleted_at`；列表 `{items,page,page_size,total}`。FAIL：字段缺失/命名错/嵌套形态错 |
| **V29** FK 物理语义（机制级） | raw 物理 `DELETE FROM clusters`（被 Network 引用） | 真实 PG | PASS：被 FK RESTRICT 阻止（`confdeltype='r'`）。报告标注机制级（API 无物理删除路径） |
| **V30** 引用检查器注册表 | F008 注册 Network 引用集调用点；F009/F010 前为空集 | 后端集成 + 静态 | PASS：调用点存在且落地为空集，不误报；注册非空桩后 V9/V15 生效。FAIL：无调用点、空集误报 |

---

## 2. 边界与并发场景（B 编号，TEST 阶段执行）

| 编号 | 场景 | 步骤 | 判据 |
| --- | --- | --- | --- |
| B1 | 同 Cluster 精确重名 | 同 cluster 两次 POST 同 name | 第二次 409 `unique_conflict(field:"name")`；一行 |
| B2 | 大小写不敏感重名 | `MGMT`/`mgmt`/`MgMt` | 后续均 409；首条 name 原样保留 |
| B3 | 非 ASCII 大小写不折叠 | 中文名与含 `ß`/`İ`（无 ASCII 折叠） | 各自独立；仅 ASCII A-Z 折叠 |
| B4 | 首尾空白 trim | `"  MGMT  "`、`"\tmgmt\n"` | 201；落库 `MGMT`/`mgmt`；`name_key` 基于 trim 值 |
| B5 | 内部普通空格不合并 | `"MG MT"`、`"MG  MT"`、`"MG\u00a0MT"`（Unicode 空格） | 普通空格 201 且原样；是否 Unicode 空格按 D01 口径（待 CONTRACT） |
| B6 | 空名/纯空白/控制字符 | `""`、`"   "`、含 `\x00`/`\x1f`/`\u200b` | 均 422；raw CHECK 拒 |
| B7 | name 长度 | 255 字符、256 字符 | 255 成功；256→422/`varchar(255)` 拒 |
| B8 | 软删后复用 | 软删同名→重建同名 | 201，新 id；部分唯一仅约束未删 |
| B9 | 同 Cluster CIDR 重叠/相同 | 建 `10.0.0.0/16` 后建 `10.0.0.0/24`、`10.0.0.0/16` | 均 409 `range_overlap(field:"cidr")`，`conflicts[]` 含冲突 network |
| B10 | 跨 Cluster 同 CIDR | 两 cluster 各建 `10.0.0.0/16` | 均 201 |
| B11 | INACTIVE 参与重叠 | INACTIVE Network 与新 Network 重叠 | 409 |
| B12 | 软删不参与重叠 | 软删 A 后建同 CIDR B | 201；恢复 A 时重叠→409 |
| B13 | cluster 缺失/不存在/软删 | 省略/`null`/随机 UUID/软删 Cluster | 均 422；无行 |
| B14 | 同名跨 Cluster | 同名不同 cluster | 均 201（唯一作用域=同 cluster） |
| B15 | CIDR 含 host 位 | `10.0.0.5/24` | 接受并归一化为 `10.0.0.0/24`（PG cidr 语义，待 CONTRACT/I-2） |
| B16 | 非法/非 IPv4 CIDR | `/33`、`256`、IPv6、裸 IP、空 | 422 |
| B17 | gateway 边界 | 省略/null/网络地址/广播地址/`/31` 两端/`/32`+非空/禁用段 | 空 201；网络/广播 422；`/31` 两端 201；`/32` 非空 422；禁用 422 |
| B18 | status 语义 | 省略/`ACTIVE`/`INACTIVE`/`"active"`/`null` | 省略→ACTIVE；显式保存；非法 422；raw CHECK 拒 |
| B19 | auto_allocate 语义 | 省略/`true`/`false`/`null` | 省略→false；显式保存；`null`→422 |
| B20 | INACTIVE 查询/重叠 | GET INACTIVE；INACTIVE 与新建重叠 | GET 200；重叠 409 |
| B21 | 无引用改 cidr/cluster | PATCH cidr/cluster（引用集空） | 按名称/重叠约束允许并重检；重叠→409 |
| B22 | 有引用改 cidr/cluster | 注册非空引用桩后 PATCH cidr/cluster | 409 `reference_exists` + `references[]`；库值不变 |
| B23 | 无引用软删 | DELETE（空引用集） | 204；写 DELETE audit；`deleted_at` 非空 |
| B24 | 有引用软删 | DELETE（注册桩） | 409 `reference_exists`；不级联 |
| B25 | 恢复依赖失效 | Cluster 软删→restore；CIDR 被占→restore；name 被复用→restore | 分别 409 `dependency_deleted`/`range_overlap`/`unique_conflict`；保持软删 |
| B26 | 乐观锁并发（真提交） | `committed_engine` 两连接同 version PATCH | 一方 200 且 version+1；另一方 409 `VERSION_CONFLICT`；无丢失更新 |
| B27 | 审计同事务回滚 | 注入 audit 失败（创建/更新/删除/恢复） | 业务与 audit 同回滚；最终持久化为旧值/无新行 |
| B28 | 权限矩阵 | 逐端点 VIEWER/EDITOR/ADMIN/未认证 | 符合 §23；服务端强制 |
| B29 | metadata JSONB | `{}`/object/list/标量/整值替换；raw 非 object | object 接受；非 object 422/CHECK 拒；整值替换 |
| B30 | 部分唯一 raw 兜底 | raw 直插同 `(cluster_id,name_key)` 未删；软删后同名 | 存活重名被 `uq_networks_cluster_id_name_key` 拒；软删后同名成功 |
| B31 | 排他约束 raw 兜底 | raw 直插同 cluster 重叠 CIDR；软删后同 CIDR | 存活重叠被 EXCLUDE 拒；软删后成功 |
| B32 | 软删默认隐藏 | 软删后 GET 详情/列表（默认） | 404/不在列表；`deleted` 过滤按 Contract 可见性 |
| B33 | **CIDR 重叠并发双会话** | null；两独立连接几乎同时 POST 同 cluster 重叠 CIDR，真提交 | 排他约束原子兜底，至多一方 201、另一方 409 `range_overlap`；最终库中同 cluster 无重叠；断言最终持久化，不仅「未抛异常」 |
| B34 | **恢复与并发重建竞争** | 软删 A（CIDR X）后并发：会话 1 restore A、会话 2 建同 CIDR/同名 B | 至多一方成功；部分唯一/排他约束闭环；无两存活同名或重叠 |
| B35 | 迁移 0008 up/down/up | `upgrade head`→`downgrade 0007`→`upgrade head`；`alembic heads` | 各步 0；单一 head `0008_networks`；down 后表/约束消失、0007/扩展保留；re-up 一致 |
| B36 | FK 物理语义（机制级） | raw 物理 `DELETE FROM clusters`（被 Network 引用） | FK RESTRICT 阻止；报告标注机制级 |

并发说明：B26/B27/B33/B34 及任何「失败不留痕/并发」用例必须使用 `committed_engine`（真实连接真实提交）或显式事务控制，断言**最终持久化状态+关系图**，不仅「未抛异常」。涉及部分唯一、排他约束、CHECK、FK、JSONB、迁移的断言必须在真实 PostgreSQL 执行（SQLite/Mock 不作约束/并发证据）。

---

## 3. 夹具 / 环境设计

**复用 F001/F004 `backend/tests/conftest.py`（不改其护栏语义）**：
- `test_database_url`：独立测试库 + 安全护栏（库名含 `test`、`TEST_DATABASE_URL != DATABASE_URL`）；未设置则 skip 并告警，不静默改 SQLite。
- `pg_engine`：会话级 `DROP SCHEMA public CASCADE` + `CREATE SCHEMA public` + `alembic upgrade head`（含 0008），会话结束清理。
- `db_session`：函数级外层事务 + savepoint，回滚不跨用例污染（单事务用例）。
- `committed_engine`：真实提交用例（B26/B27/B33/B34 及持久断言），teardown `TRUNCATE` 清理（排除 `alembic_version`；确认 `networks` 在动态清理清单内），新开连接断言最终持久化。
- `alembic_runner`：迁移 up/down/up 用例（V23/B35）。

**复用 F002 认证/权限 fixture（`auth_session_factory`/`auth_app`/`api_client`/`bootstrap_admin`/`make_user`/`login`）**：F008 权限/审计证据使用**真实业务端点** `/api/v1/networks*`。

**复用 F003/F004 helper**：`_create_cluster`、`role_client_factory`、`insert_cluster` raw 辅助；软删/恢复、乐观锁 `two-session`、raw SQL 约束断言模式直接复用。

**F008 新增测试侧夹具/断言（由 Tester 落地于测试侧，实现阶段由 Backend 提供接口）**：
- `network_factory`：创建 Network（`cluster_id` + 可选字段），返回对象与 `version`；供 A1–A22、B1–B36 复用。
- `NETWORK_CASES`：表驱动数据（name trim/大小写/内部空格/控制字符/长度，cidr 合法/非法/host 位，gateway 空/越界/禁用//32，status 省略/非法，auto_allocate 省略/非法，cluster 缺失/不存在/软删），供 V1–V13/V20 与 B1–B19 共用，确保 API 与 DB 同一口径。
- `assert_network_row(engine, id, expected)`：raw SQL 断言 `networks` 各列值/`IS NULL`。
- `assert_partial_unique(engine, cluster_id, name_key, deleted)`：raw 直插断言部分唯一仅在 `deleted_at IS NULL` 生效（A1/A4/V20/B30）。
- `assert_cidr_overlap(engine, ...)`：raw 直插同 cluster 重叠/相同 CIDR 断言被 EXCLUDE 约束拒、跨 cluster/软删成功（A5/A6/V20/B9–B12/B31）。
- `assert_gateway_boundary(...)`：网络地址/广播/`/31`/`/32`/禁用段逐项断言（A10/V10/B17）。
- `assert_allocatable_boundary(...)`：给定 CIDR+gateway 断言基础可用/可分配集合排除 gateway（A11/V11/V22，F008 侧）。
- `assert_reference_protection(client, ...)`：端到端断言改 cidr/cluster 与删除的 409 `reference_exists`+references（V9/V15/B22/B24）。
- `assert_restore_recheck(...)`：恢复重检 name/Cluster/CIDR，供 A16/B25。
- `assert_audit_same_txn(...)`：注入 audit 失败断言双回滚（V18/B27）。
- `two_session_cidr_overlap` / `two_session_restore_vs_create` / `two_session_version_conflict`（复用 F004 模式）：真实提交并发，供 B33/B34/B26。
- **F008 前端夹具**：复用 F005/F006/F007 `smoke:client` 机制，新增 Network 表单（cluster 选择器、cidr/gateway 校验、status、auto_allocate）、已删开关与 ADMIN 恢复、422 点路径映射，供 A17/A19 与前端机制级用例。

**环境**：Docker / Compose 可用（F001–F007 TE 已证）；真实 PG 经 Compose `db`（`postgres:16`）。btree_gist 为 PG13+ trusted 扩展，迁移需目标库 CREATE 权限。

### 3.1 当前环境可执行性评估

| 验证项 | 环境要求 | 当前评估 | 降级/替代 |
| --- | --- | --- | --- |
| V1–V30、B1–B32/B36 | 真实 PG + 后端集成 | 经 Compose `db` 可满足（F001–F007 已证） | 无 PG 时 skip 并标 BLOCKED，**不得**用 SQLite 替代约束/并发证据 |
| V23/B35 迁移 up/down/up | Alembic + 真实 PG + btree_gist | 可执行；依赖 0008 定稿 | 迁移未定稿则相关断言 BLOCKED，不降验收 |
| B26/B27/B33/B34 并发 | 真实并发提交 fixture | 可执行（复用 `committed_engine`） | 无 PG 时 BLOCKED；不得以顺序调用替代并发证据 |
| 前端机制级 / 真实 API 集成 | Node 22 + 构建；Compose 入口 | 可执行 | 真实浏览器 DOM 渲染非必要判据；镜像/端口问题记 BLOCKED |

---

## 4. 可验证性检查

| 项 | 判定 | 说明 |
| --- | --- | --- |
| A1/A2/A4 name 唯一与大小写 | **可验证（API + DB）** | V1/V2/V4/V16/V20 + B1–B8/B30；部分唯一 + 应用检查双路径，真实 PG |
| A3 name 归一化/控制字符/内部空格 | **可验证（API + DB）** | V3 + B3–B7；422 与 CHECK backstop 双路径 |
| A5/A6 CIDR 不重叠 | **可验证（API + DB）** | V5/V6/V20 + B9–B12/B31/B33；排他约束 + 应用映射 range_overlap |
| A7 CIDR 格式 | **可验证（API）** | V7 + B16；PG cidr 类型 |
| A8 cluster 归属 | **可验证（API + DB）** | V8 + B13；FK + 应用校验 |
| A9/A15 引用检查与删除 | **可验证（端到端 + 机制）** | V9/V15/V30 + B21–B24/B36；注册表空集 + 桩；FK RESTRICT 机制级 |
| A10/A11 gateway 边界 | **可验证（API + DB + 静态）** | V10/V11/V22 + B17；DB CHECK 可行性待 Database（§8） |
| A12/A13/A14 状态与 auto_allocate | **可验证（API + DB + 静态）** | V12/V13/V14 + B18–B20；默认值落库 + 静态核对无绕过 |
| A16 恢复重检 | **可验证（端到端）** | V16 + B25/B34；真实端到端 409 |
| A17 权限矩阵 | **可验证（端到端 + 静态）** | V17 + B28；真实端点 + 服务端强制 |
| A18 审计 | **可验证（端到端 + 真提交）** | V18 + B27；四 action + 同事务回滚 |
| A19 列表 | **可验证（端到端）** | V19 + B32；软删/INACTIVE/过滤/分页/排序 |
| A20 DB 兜底 | **可验证（DB）** | V20 + B30/B31；真实 PG raw 直插 |
| A21 归一化一致 | **可验证（F008 侧）** | V21；API 与 DB 口径一致 + 软删不参与；F014/F013 执行各自 |
| A22 边界语义下游共用 | **不适用（F009/F010/F013）** | F008 侧仅 V11/V22 静态核对；执行与容量归下游 |
| V23/B35 迁移 0008 | **可验证（DB）** | 真实 PG up/down/up + 单一 head + btree_gist |
| B33/B34/B26 并发 | **可验证（真提交）** | 复用 `committed_engine`，断言最终关系图 |
| B36 FK 物理语义 | **机制级** | API 无物理删除路径；raw SQL 验证 `confdeltype`，报告须显式标注 |

口径明确记录：**A9/A15/V9/V15 为真实业务端点端到端（F009/F010 前用注册桩）**；**A20/B30/B31/B36 为真实 PG raw SQL 机制级**；**A22 为跨 Feature 不适用项**；**T14 的 F008 子集**（同 Cluster CIDR 重叠/跨 Cluster/INACTIVE 参与/有 Pool/IP 禁改）在本 Feature 验证；**T16 的 F008 子集**（INACTIVE 禁新增分配语义、auto_allocate 默认）在本 Feature 验证；**T24/T25/T29/T30/T37/T38/T40/T41 的完整回归不在本 Feature**，不得以 F008 局部 PASS 拼成整条通过。

---

## 5. 范围与不适用项声明

- **IPPool 起止地址/allocation_mode/池互不重叠/RESERVED 冲突（§12/§12.1，F009）**：F008 不落 Pool 字段、不实现池重叠与保留范围；「已占用 IP 设为 gateway 拒绝」归 **F009/F010**（I-5）。F008 仅保证 gateway 边界语义可被下游复用。
- **IP 自动/手动分配、解绑、释放、IP 唯一性、地址边界执行、容量数值（§13/§14/§20，F010/F013）**：F008 仅提供 CIDR/gateway 边界语义；A11 容量数值、A22 执行归下游。
- **全局搜索/Dashboard/列表聚合/pg_trgm（§17/§19/§20/§28，F013）**：完整列表聚合与搜索归 F013；F008 仅承载 `/api/v1/networks` 列表/过滤/排序（A19）与边界语义。
- **CSV/Excel 导入（§24，F014）**：Network 导入模板与执行归 F014；F008 仅提供字段口径供复用（A21 子集）。
- **完整 Audit 查询页（§22，F015）**：归 F015；F008 仅验证 Network 四 action 的资源级 Activity 快照。
- **Interface（F007）、Service/ServiceEndpoint（F011/F012）**：F008 不涉及。
- **VLAN ID/网络分类（管理/业务/存储/IB）/Pool 或 IP 列表/VLAN 数值字段**：明确不落 Network（§11）；VLAN 仅 Interface 枚举值。
- **IPv6、DHCP/路由/防火墙/VLAN 划分/网段自动发现、实时网络状态/流量/可达性监控**：明确排除。
- **I-3 禁用范围建网限制**：基线不据 §11.1 新增建网限制（architecture §8 I-3）；是否禁止 CIDR 完全落在禁用范围的 Network 属新业务限定，须用户裁定；TD-1 不生成对应 FAIL 判据。
- **完整 T14/T16/T24/T25/T29/T30/T37/T38/T40/T41 回归与 §32 上线验收**：F008 仅承载 Network 相关子集；跨 Feature 完整回归归 F016。**不声明上述条款完整通过**。
- **真实浏览器 DOM 渲染**：非 F008 必要判据，前端以构建 + client 机制级为准。

---

## 6. 风险与待核对项总结

| 项 | 评估 | 处理 |
| --- | --- | --- |
| V1–V30、B1–B32/B36（真实 PG + 后端集成） | Docker/Compose 可用（F001–F007 已证）；**可执行** | 无 PG 时相关项 BLOCKED，不降验收 |
| V23/B35 迁移 0008 + btree_gist | DATABASE Gate 未定稿 | 定稿后由 TD-2 核对；未定稿则 BLOCKED |
| B33/B34 并发 | 需真实并发提交 fixture | 复用 `committed_engine`；断言最终关系图 |
| B36 物理 FK RESTRICT | API 无物理删除路径 | raw SQL 机制级验证 `confdeltype`，报告显式标注 |
| gateway DB CHECK 可行性 | architecture §4 标注可能仅应用主导 + backstop | TD-2 依 DATABASE 定稿核对 V10/B17 断言层级 |
| F009/F010 引用注册与子对象锁协议 | 跨 Feature，F008 建表时子表不存在 | F008 侧预留调用点空集（V30/B22/B24）；跨 Feature 协议在 F009/F010 验证 |
| DATABASE/CONTRACT/D01 v7 定稿状态 | **未定稿** | TD-1 §8 列全部待复核项；TD-2 逐项关闭 |

---

## 7. 独立性与执行口径（TEST 阶段适用）

- Backend pytest 由 Tester 独立重跑，不复用实现者数字。
- 迁移、约束、排他约束、CHECK、FK、部分唯一、JSONB、btree_gist 由 Tester 在独立库（库名含 `test`）以 Alembic / raw SQL 直接执行；不连接生产或未知数据库。
- 接口验证响应内容、类型、业务边界、非法输入与错误语义；只读功能（GET/activity）确认无业务写副作用。
- 前端验证状态、交互、错误与未知值处理；已批准范围要求真实前后端集成时经入口 Nginx 验证真实 API，不以 Mock 代替。
- 修复后按影响重测；首次设计检查与最终验收分别记录版本与证据。

---

## 8. OPEN 复核项（TD-1 提出，待 DATABASE/CONTRACT/D01 v7 定稿后由 TD-2 关闭）

| # | TD-1 待复核假设 | 影响验证项 | Owner |
| --- | --- | --- | --- |
| OPEN-1 | 表名 `networks`、列名/类型（`id`/`cluster_id`/`name varchar(255)`/`name_key`/`cidr cidr`/`gateway inet`/`status varchar(16)`/`auto_allocate bool`/`description`/`metadata jsonb`/`version`/时间戳/`deleted_at`） | V1–V29、B1–B32 | Database |
| OPEN-2 | 约束/索引名：`pk_networks`、`uq_networks_cluster_id_name_key`、排他约束名、`ix_networks_cluster_id/status/deleted_at`、CHECK 名（name/name_key/status/metadata/version/gateway） | V3/V5/V12/V20/V24、B6/B9/B30/B31 | Database |
| OPEN-3 | 排他约束精确形态 `EXCLUDE USING gist (cluster_id WITH =, cidr WITH &&) WHERE (deleted_at IS NULL)`；btree_gist 首次启用（IF NOT EXISTS）与操作符类 | V5/V6/V20/V23、B9/B31/B33/B35 | Database |
| OPEN-4 | name_key 口径 = `ASCII_lower(btrim(name))`；name 长度 1–255（I-2 PROPOSED 镜像 Cluster name） | V1/V3/V21、B3/B5/B7 | Architect/Database（D01 v7 §5.7） |
| OPEN-5 | CIDR 含 host 位接受并归一化为网络地址（PG cidr 语义）；非 IPv4 拒绝 | V7、B15/B16 | Contract/D01 |
| OPEN-6 | gateway 取值域与 DB CHECK 可行性（纯 SQL 表达 vs 应用主导 + backstop）；`/31`、`/32` 口径 | V10/V11、B17 | Database/D01 |
| OPEN-7 | `range_overlap` details 形状 `conflicts:[{object_type,object_id,label}]`；`reference_exists` details `references[]` | V5/V9/V15/V16、B9/B22/B24/B25 | Contract |
| OPEN-8 | 校验顺序与错误码层级（401→403→body→cluster→name→cidr/gateway→重叠→写+Audit） | V27 | Contract |
| OPEN-9 | 引用检查器注册表落点与空集初始语义；改 cidr/cluster 的 `FOR UPDATE` 锁序与 F009/F010 协议（I-4） | V9/V15/V30、B22/B24/B33 | Architect/Database |
| OPEN-10 | 迁移 `0008_networks`（`down_revision=0007`）单 head、对称可逆、无回填、不 drop 扩展 | V23、B35 | Database |
| OPEN-11 | metadata 归属 Network 自有（I-6 PROPOSED）；object CHECK | V24、B29 | Contract/D01 |
| OPEN-12 | 列表 Query 参数集与 `q` 大小写不敏感子串口径、`deleted` 语义、`sort`/`order` 集合 | V19、B32 | Contract |
| OPEN-13 | 恢复失败错误码优先级（name 复用 > Cluster 失效 > CIDR 重叠）；`dependency_deleted` 形状 | V16、B25/B34 | Contract |
| OPEN-14 | 响应嵌套 `cluster{id,code,name}` 与字段/命名 | V28 | Contract |
| OPEN-15 | I-3：是否禁止 CIDR 完全落在 §11.1 禁用范围的 Network（当前不新增限制） | （无 FAIL 判据） | Product/用户 |

TD-1 结论：**TEST DESIGN READY** —— A1–A22 可映射到可观察判据，边界/并发场景可执行，夹具与可验证性已与 architecture 草案建立对应。**但 DATABASE/CONTRACT/D01 v7 尚未定稿，以上 OPEN 未经逐项核对；READY 不等于测试通过，不批准实现或合并。** 定稿后由 TD-2 关闭 §8 并固定执行判据。

---

## 8A. TD-2 — §8 OPEN-1–15 逐项关闭（2026-10-09）

核对依据：`docs/database/f008-network.md` v1（DB-D80–D94）、`docs/api/F008.md` v1、`docs/architecture/d01-conventions.md` v7 §5.7、真库结构（独立库 `csm_verify_test`，PostgreSQL 16.15）。命令编号见 Test Execution §B。

| # | TD-1 待复核假设 | 核对结论（真库/文档） | 关闭 / 去向 |
| --- | --- | --- | --- |
| OPEN-1 | 表名/列名/类型 | 真库 `networks` 14 列与 DB v1 §2 完全一致（C3）；Contract §3 响应字段一致 | **CLOSED** |
| OPEN-2 | 约束/索引名 | 真库 13 约束：`pk_networks`、`fk_networks_cluster_id_clusters`、`ck_networks_name_not_blank/_trimmed/_no_control/_length/_name_key_matches`、`ck_networks_cidr_ipv4`、`ck_networks_gateway`、`ck_networks_status`、`ck_networks_metadata_object`、`ck_networks_version`、`excl_networks_cluster_id_cidr`；索引 `uq_networks_cluster_id_name_key`、`ix_networks_cluster_id/_status/_deleted_at`（C3） | **CLOSED** |
| OPEN-3 | 排他约束形态 + btree_gist | 真库定义 `EXCLUDE USING gist (cluster_id WITH =, cidr inet_ops WITH &&) WHERE (deleted_at IS NULL)`；`btree_gist` 由 0008 `CREATE EXTENSION IF NOT EXISTS` 启用（C1/C3）。DB-D88 未写显式 `inet_ops` | **CLOSED**，NOTE-DB-1 |
| OPEN-4 | name_key 口径 = ASCII_lower(btrim(name))，name 1–255 | D01 v7 §5.7、Contract §2.1、DB-D81 与真库 `ck_networks_name_key_matches = translate(btrim(name), 'A-Z','a-z')` 一致（C3）；应用 `network_name_key` 逐码位，不用 `str.lower()` | **CLOSED** |
| OPEN-5 | CIDR host 位归一化 / 非 IPv4 拒 | Contract §2.2 接受并归一化；真库 `cidr` 类型**拒绝**裸 host 位（C4：`invalid cidr value: "10.1.0.5/24" ... Value has bits set to right of mask`），归一化实际由 Service `ipaddress(strict=False)` 完成。DB-D83「由 cidr 类型归一化」措辞与真库不符 | **CLOSED**，NOTE-DB-2 |
| OPEN-6 | gateway 取值域与 DB CHECK 可行性 | Contract §2.2 / D01 §5.7 固定取值域；DB CHECK `ck_networks_gateway` 存在，但真库验证**未拒绝网络/广播地址**（C7） | **CLOSED（Contract）**；DB CHECK 缺陷 → **DEF-F008-TE1-01** |
| OPEN-7 | `range_overlap`/`reference_exists` details 形状 | Contract §1.2：`{field:"cidr",conflicts:[{object_type,object_id,label}]}`、`references[{object_type,object_id,label}]`；API/桩测试命中（E8/E12） | **CLOSED** |
| OPEN-8 | 校验顺序与错误码层级 | Contract §6 POST/PATCH/DELETE/restore；`test_validation_order` 通过（E10） | **CLOSED** |
| OPEN-9 | 引用检查器注册表 + FOR UPDATE | Contract §7、DB-D90；实现注册空集调用点，改 cidr/cluster/删除事务内 `FOR UPDATE`；空集与桩均验证（E13/E12） | **CLOSED** |
| OPEN-10 | 迁移 0008 单 head / 对称可逆 / 无回填 / 不 drop 扩展 | 独立库 up→down→up；`alembic heads` 单一 `0008_networks`、`down_revision=0007_interfaces`；down 后 networks/约束消失、interfaces 与 btree_gist 保留；re-up 一致（C1/C2） | **CLOSED** |
| OPEN-11 | metadata Network 自有 + object CHECK | Contract §2.2、DB-D86、D01 v7；真库 `ck_networks_metadata_object`（C3、C5 非 object 拒） | **CLOSED** |
| OPEN-12 | 列表 Query 参数集 / q 口径 / deleted / sort / order | Contract §4；`test_list_filters_sorting_pagination` 通过（E9） | **CLOSED** |
| OPEN-13 | 恢复错误码优先级 name > Cluster > CIDR | Contract §6.6；`test_restore_rechecks_name_cluster_cidr` 通过（E11） | **CLOSED** |
| OPEN-14 | 响应嵌套 `cluster{id,code,name}` 与字段命名 | Contract §3；`test_create_defaults_and_response_shape` 通过（E1） | **CLOSED** |
| OPEN-15 | I-3 是否禁止 CIDR 完全落在 §11.1 禁用范围的 Network | architecture §8 I-3：不新增建网限制；无 FAIL 判据；仍为 Product/用户新增业务限定的观察项 | **CLOSED（记录，非阻塞）** |

**TD-2 记录的数据库文档补注（NOTE，非必须修复缺陷；由协调器/Database 决定是否补文）**

| 编号 | 观察 | 证据 |
| --- | --- | --- |
| NOTE-DB-1 | DB-D88 的排他约束描述 `(cluster_id WITH =, cidr WITH &&)` 未提及显式操作符类。真库必须写 `cidr inet_ops WITH &&`：安装 btree_gist 后 `cidr` 默认 GiST 操作符类为 `gist_cidr_ops`（仅等值），不加 `inet_ops` 会报 `operator &&(inet,inet) is not a member of operator family "gist_cidr_ops"`（C6）。建议 DB 文档补注。 | C6 |
| NOTE-DB-2 | DB-D83 措辞「host 位由 cidr 类型归一化为网络地址」与真库不符：PG `cidr` 类型拒绝带 host 位输入，归一化由 Service `ipaddress(strict=False)` 完成；API/Contract 行为不变（B15 通过）。建议 DB 文档补注。 | C4 |

TD-2 结论：`TEST DESIGN READY`（OPEN-1–15 已逐项关闭；2 项文档补注；1 项 DB 约束缺陷转实现）。该结论仍不代表测试通过或批准合并。

---

## Test Execution

> TE-1（首轮执行）与 TE-2（有限修复第 1 轮后的 TEST 复核）均记录于本节。**当前结论以 TE-2 为准**。

### TE-1（首次执行，历史记录）

- **版本**：TE-1
- **日期**：2026-10-09
- **角色**：Tester（TEST 模式）
- **结论**：**`RETURN TO IMPLEMENTATION`** —— 发现 1 个必须修复的数据库约束实现缺陷（DEF-F008-TE1-01）；其余 A1–A22 / V1–V30 / B1–B36 可验证项通过。
- **执行基线**：HEAD `9bc9835`（分支 `feature/F008-network-management`）；Contract `docs/api/F008.md` v1；Database `docs/database/f008-network.md` v1；D01 v7；implementation `BACKEND+FRONTEND COMPLETE`；Test Design TD-2。
- **独立性声明**：后端 pytest 由 Tester 独立重跑（非复用实现者数字）；迁移、约束、排他约束、CHECK、FK、部分唯一、JSONB 在独立库 `csm_verify_test`（库名含 test）以 Alembic / raw SQL 直接执行；未连接生产或未知数据库；前端 typecheck/build/smoke 独立重跑。

---

### A. 执行环境

| 项 | 值 |
| --- | --- |
| 日期/时间（UTC） | 2026-10-09T07:17Z 起 |
| PostgreSQL | `f002test-db` 容器 `postgres:16.15`（Debian 16.15-1.pgdg13+2），网络 `f002test-net` |
| 测试库 | `csm_test`（pytest，用户 csm）；独立验证库 `csm_verify_test` |
| 后端测试镜像 | `csm-f007-test:latest`（pytest 8.4.2 / Python 3.12.15），源码以 volume 挂载 |
| 前端 | Node v22.23.2 / npm 12.0.2，`frontend/node_modules` 就绪 |
| Compose / Nginx 全链路 | 未执行（环境限制，见未验证项）；权限矩阵以真实 ASGI 业务端点 + 真实 PG 覆盖（同 F007-TE-1-02 口径） |

### B. 实际执行命令（编号引用）

| 编号 | 命令 | 结果摘要 |
| --- | --- | --- |
| C1 | `DROP/CREATE csm_verify_test` → `alembic upgrade head` → `alembic heads` → `SELECT version_num` | upgrade 0001→0008 全部 OK；单一 head `0008_networks (head)`；version=`0008_networks` |
| C2 | `alembic downgrade 0007_interfaces` → 查对象 → `alembic upgrade head` | downgrade 后 version=`0007_interfaces`；`to_regclass('public.networks')`=NULL、`interfaces` 存在、`btree_gist` 存在；re-up 后 `networks` 存在、version=`0008_networks` |
| C3 | `SELECT conname, pg_get_constraintdef ... FROM pg_constraint`、`pg_indexes`、`pg_extension` | 13 约束 + 6 索引与 DB v1 §2 一致；排他约束含 `cidr inet_ops WITH &&`；`btree_gist` 存在（OPEN-1/2/3） |
| C4 | raw `INSERT INTO scratch_hostbits (cidr) VALUES ('10.1.0.5/24')` | `ERROR: invalid cidr value ... Value has bits set to right of mask`（NOTE-DB-2） |
| C5 | raw 直插：同 cluster 同 `name_key`、重叠 CIDR、非 object metadata | 分别被 `uq_networks_cluster_id_name_key`、`excl_networks_cluster_id_cidr`、`ck_networks_metadata_object` 拒（A1/A5/A20/V20/V24） |
| C6 | scratch 表 `EXCLUDE USING gist (cluster_id WITH =, cidr WITH &&)` vs `cidr inet_ops WITH &&` | 无 opclass：`ERROR: operator &&(inet,inet) is not a member of operator family "gist_cidr_ops"`；加 `inet_ops` 成功（NOTE-DB-1） |
| C7 | raw 直插 gateway：网络地址/广播/越界/禁用 5 段//32//31/合法 | **网络地址与广播地址被接受（DEF-01）**；越界、禁用 5 段、`/32`+非空被拒；`/31` 两端与合法值接受 |
| C8 | 后端全量 `python -m pytest tests -q`（独立重跑） | **1 failed, 248 passed, 1 skipped**（失败=DEF-01 新增回归测试；skip=F001 V3b 非 superuser 环境性） |
| C9 | 后端 F008 专属 `pytest tests/integration/test_networks.py tests/integration/test_network_constraints.py -q` | **1 failed, 31 passed**（32 用例） |
| C10 | 前端 `npm run typecheck` → `npm run build` → `npm run smoke:client` | typecheck 通过；vite build 通过；smoke **108 passed, 0 failed**（含 F008 机制级 23 用例） |

### D. 验收映射执行结果（A1–A22）

| 验收 | 状态 | 证据 |
| --- | --- | --- |
| A1 同 Cluster 名大小写不敏感重名拒 | **PASS** | `test_name_uniqueness_case_insensitive_and_reuse`；C5 raw 部分唯一 |
| A2 跨 Cluster 同名允许 | **PASS** | 同上 |
| A3 trim/空名/控制字符/内部空格 | **PASS** | `test_name_trim_boundaries_and_internal_spaces`；`test_name_boundaries_and_name_key` |
| A4 软删后重建/存活同名拒/恢复不覆盖 | **PASS** | `test_name_uniqueness_case_insensitive_and_reuse`；`test_restore_rechecks_name_cluster_cidr` |
| A5 同 Cluster CIDR 重叠/相同拒，跨 Cluster 允许 | **PASS** | `test_cidr_overlap_and_inactive`；`test_exclusion_overlap_and_cidr_normalisation` |
| A6 INACTIVE 参与重叠 | **PASS** | 同上 |
| A7 非 IPv4/非法 CIDR 422 | **PASS** | `test_cidr_validation_and_normalisation`；DB 非 IPv4 拒 |
| A8 cluster 缺失/不存在/软删 422 | **PASS** | `test_cluster_validation` |
| A9 有引用改 cidr/cluster 拒；无引用按约束允许并重检 | **PASS** | `test_reference_checker_blocks_change_and_delete`（注册桩→409 reference_exists + references[]）；`test_patch_cluster_rechecks_target` |
| A10 gateway 空允许/越界禁用 422//32 必空 | **PASS（API 可观察）**；**DB 后盾缺陷** | `test_gateway_boundaries`（API）通过；C7 证明 DB CHECK 对网络/广播失效 → **DEF-01** |
| A11 gateway 从可分配集合排除，容量不计 | **PASS（F008 侧）** | Contract §2.2/D01 §5.7 静态核对；容量数值归 F013 |
| A12 status 默认/显式/非法 | **PASS** | `test_status_auto_allocate_metadata`；`test_status_auto_allocate_and_metadata` |
| A13 auto_allocate 默认/显式/不绕过 | **PASS** | 同上 |
| A14 INACTIVE 查询/禁新增分配语义 | **PASS（F008 侧）** | GET INACTIVE 200；F008 无分配入口；执行归 F010 |
| A15 有引用删除拒+引用列表；不级联；无引用软删 | **PASS** | `test_reference_checker_blocks_change_and_delete`；`test_soft_delete_visibility_and_restore` |
| A16 恢复重检 name/Cluster/CIDR；失败不覆盖 | **PASS** | `test_restore_rechecks_name_cluster_cidr` |
| A17 权限矩阵（真实 ASGI + 真实 PG） | **PASS** | `test_permission_matrix`（VIEWER/EDITOR/ADMIN/未认证逐端点）；Compose/Nginx 入口未执行（见未验证项） |
| A18 四 action Audit 同事务；Activity 全角色 | **PASS** | `test_audit_four_actions_and_activity`；`test_audit_rolls_back_with_the_transaction` |
| A19 列表软删隐藏/含 INACTIVE/过滤分页排序 | **PASS** | `test_list_filters_sorting_pagination`；`test_soft_delete_visibility_and_restore` |
| A20 DB 部分唯一 + 排他约束兜底 | **PASS** | C5 raw；`test_partial_unique_name`；`test_exclusion_overlap_and_cidr_normalisation` |
| A21 归一化 API/DB 一致，仅未删参与唯一 | **PASS（F008 侧）** | 应用 `network_name_key` 与 DB `translate(btrim(name))` 逐项一致；F014/F013 执行各自 |
| A22 CIDR/gateway 边界作为下游共同输入 | **PASS（F008 侧静态）/ 执行帰下游 NOT TESTED** | Contract §9；F009/F010/F013 执行 |

### E. 补充验证项（V1–V30）

| 验证项 | 状态 | 说明 |
| --- | --- | --- |
| V1–V9 | **PASS** | 见 A1–A9 证据 |
| V10 gateway 边界 | **PASS（API）/ DB CHECK 缺陷** | API `test_gateway_boundaries` 通过；DB `test_gateway_boundaries`（约束）**FAIL** → DEF-01 |
| V11–V20 | **PASS** | 见对应 A 证据；C5 |
| V21 归一化一致 | **PASS（F008 侧）** | 应用/DB CHECK 同口径 |
| V22 边界语义下游共用 | **PASS（F008 侧静态）/ 下游 NOT TESTED** | — |
| V23 迁移 0008 | **PASS** | C1/C2；`test_migration_up_down_up_and_single_head` |
| V24 metadata JSONB | **PASS** | `test_status_auto_allocate_metadata`；C5 raw 非 object 拒 |
| V25 乐观锁并发 | **PASS** | `test_optimistic_lock_two_sessions`（两 Session 真提交） |
| V26 PATCH exclude_unset/不可变 | **PASS** | `test_patch_exclude_unset_and_non_nullable` |
| V27 校验顺序 | **PASS** | `test_validation_order` |
| V28 响应契约 | **PASS** | `test_create_defaults_and_response_shape` |
| V29 FK 物理语义（机制级） | **PASS** | `test_fk_restrict_and_soft_delete_retention`（`confdeltype='r'`） |
| V30 引用检查器注册表 | **PASS** | `test_reference_checker_registry_empty`（空集无误报）+ `test_reference_checker_blocks_change_and_delete`（桩生效） |

### F. 边界与并发场景（B1–B36）

全部 **PASS**，证据：B1–B8 `test_name_*`/`test_name_boundaries_and_name_key`/`test_partial_unique_name`；B9–B12 `test_cidr_overlap_and_inactive`/`test_exclusion_overlap_and_cidr_normalisation`；B13–B14 `test_cluster_validation`；B15–B16 `test_cidr_validation_and_normalisation`/C4；B17 `test_gateway_boundaries`（API）/ C7（DB 网络·广播部分 DEF-01）；B18–B20 `test_status_*`；B21–B24 `test_patch_cidr_and_gateway_recheck`/`test_patch_cluster_rechecks_target`/`test_reference_checker_blocks_change_and_delete`；B25 `test_restore_rechecks_name_cluster_cidr`；B26 `test_optimistic_lock_two_sessions`；B27 `test_audit_rolls_back_with_the_transaction`；B28 `test_permission_matrix`；B29 `test_status_auto_allocate_metadata`；B30–B31 C5/`test_partial_unique_name`/`test_exclusion_overlap_and_cidr_normalisation`；B32 `test_soft_delete_visibility_and_restore`；B33 `test_concurrent_overlapping_insert`；B34 `test_concurrent_restore_vs_recreate`；B35 C2/`test_migration_up_down_up_and_single_head`；B36 `test_fk_restrict_and_soft_delete_retention`。

- **B5 NOTE**：TD-1 待核对的 Unicode 空格口径：D01 v7 §5.7 / Contract §2.1 仅固定「允许内部普通空格且不合并」，未规定 Unicode 空格（如 NBSP）行为；实现仅拒 Cc/Cf，保留其它 Unicode 空格。这与已确认规则不冲突，不判 FAIL；如后续要收紧需 Product/D01 裁定。
- **B34 首次补充执行**：TD-1 计划但实现阶段未落地的「恢复 vs 并发重建」真提交并发用例已由 Tester 新增（`test_concurrent_restore_vs_recreate`），排他约束/部分唯一闭环使至多一方存活，PASS。

### G. Defects

| ID | Severity | Layer | Location | 证据/复现 | 期望 vs 实际 | 影响 | Owner | 必须修复 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| DEF-F008-TE1-01 | **HIGH** | Backend / Database（约束实现） | `backend/alembic/versions/0008_networks.py` 的 `ck_networks_gateway`（docs/database/f008-network.md DB-D84） | C7：独立库 raw 直插 `cidr=10.70.0.0/24, gateway=10.70.0.0`（网络地址）与 `cidr=10.71.0.0/24, gateway=10.71.0.255`（广播地址）**成功**；修正后的 `test_gateway_boundaries`（test_network_constraints.py）FAIL；越界/禁用 5 段//32 均正确拒绝。根因：`network(cidr)::inet` 与 `broadcast(cidr)::inet` 保留前缀长度（如 /24），而 `gateway` 为隐含 /32 主机地址，PostgreSQL `inet` `<>` 比较含掩码长度，故 `gateway <> network(cidr)::inet` 恒为真，网络/广播排除分支失效。 | 期望：DB CHECK 作为 backstop 拒绝网络/广播地址。实际：接受（仅应用层 `normalize_gateway` 拦截）。 | 设计 DB-D84 声明的纯 SQL backstop 未实现；直接 DB 写入可落非法 gateway，且原 DB 验证用例为假阳性（其 bad 用例同 CIDR 被排他约束先阻，未真正到达 CHECK）。API 可观察验收 A10/B17 仍通过（无用户可见失败）。 | Backend（修 CHECK，如 `gateway <> host(network(cidr))` 或 `gateway << cidr AND masklen(cidr)<>32 AND ...` 等价写法）；Database（可同步 DB-D88/DB-D84 措辞） | **是** |

**测试侧修正（Tester 职责内，非业务规则变更）**：
1. `test_network_constraints.py::test_gateway_boundaries` 改为每个负例使用独立 CIDR 且 gateway 位于其 CIDR 内，确保只有 `ck_networks_gateway` 能使插入失败；修正后该用例暴露 DEF-01。
2. `test_networks.py::test_audit_four_actions_and_activity` 原先硬编码 `[CREATE,UPDATE,DELETE,RESTORE]` 顺序，在 `created_at` 同刻时按 Contract §6.7 的 `id` 平局顺序会偶然不符（全量跑中偶发失败）；已改为校验 action 集合 + UPDATE before/after，并与 raw 行顺序一致性对齐，消除 flaky（非产品缺陷）。
3. 新增 `test_reference_checker_blocks_change_and_delete`（注册桩覆盖 A9/A15/V9/V15/B22/B24 的 409 reference_exists 端到端路径）与 `test_concurrent_restore_vs_recreate`（B34）。

### H. 未验证项

| 项 | 原因 | 影响 |
| --- | --- | --- |
| A17 经入口 Nginx + Compose 全链路 | 环境限制（本任务不重建镜像；`docker build` 可能鉴权超时） | 已按同 F007-TE-1-02 口径以真实 ASGI 业务端点 + 真实 PG 覆盖权限矩阵；未以入口验证，标 NOTE 不降验收 |
| A22 / V22 下游执行（F009 IPPool、F010 IPAddress、F013 容量） | 跨 Feature，未实现 | F008 侧仅静态核对边界语义可复用；下游执行帰对应 Feature |
| A11 容量数值 | 归 F013 | F008 仅提供可分配边界语义 |
| I-3 禁用范围建网限制 | 属新增业务限定，待用户裁定 | 无 FAIL 判据；不阻塞本 Feature |
| 真实浏览器 DOM 渲染 | 非 F008 必要判据 | 前端以构建 + client 机制级为准 |
| DB gateway CHECK 网络/广播后盾 | **FAIL（DEF-01）** | 修复并重测后重新评定 |

### I. 结论

TD-2 已逐项关闭 §8 OPEN-1–15（2 项 DB 文档补注 NOTE）。TE-1 执行：A/V/B 均已在真实 PostgreSQL 上独立验证，发现 **1 个必须修复的 HIGH 缺陷 DEF-F008-TE1-01**（DB gateway CHECK 未拒网络/广播地址，且原验证用例为假阳性）。因此结论为 **`RETURN TO IMPLEMENTATION`**，Owner **Backend**（约束实现）+ 可选 **Database**（文档措辞）；修复并修复后按影响重测（C7/C8/C9）后才能进入正式 Review。

---

**TE-1 Git 声明**

```text
GIT: git rev-parse --short HEAD
GIT: git status --porcelain
GIT: git branch --show-current
GIT: git diff --stat
```

---

### TE-2（有限修复第 1 轮后 TEST 复核，当前）

- **版本**：TE-2
- **日期**：2026-10-09
- **角色**：Tester（TEST 模式，复核）
- **结论**：**`READY FOR REVIEW`** —— DEF-F008-TE1-01 已关闭；受影响项与必要回归独立重测通过，无必须修复问题。
- **候选交付说明**：本轮验证对象为**工作区候选交付**，包含 HEAD `9bc9835` **加上未提交的 backend 修复与测试改动**。具体未提交文件：`backend/alembic/versions/0008_networks.py`、`backend/app/models/network.py`（Backend 修复）、`backend/tests/integration/test_network_constraints.py`、`backend/tests/integration/test_networks.py`（测试侧）、`docs/features/F008/test-report.md`（本报告）。**本轮测试有效性仅针对该工作区组合，不代表任一已提交基线单独通过。**
- **修复内容核对**：`ck_networks_gateway` 由 `gateway <> network(cidr)::inet` / `gateway <> broadcast(cidr)` 改为 `gateway <> host(network(cidr))::inet` / `gateway <> host(broadcast(cidr))::inet`（移除保留前缀长度，使比较两侧均为隐含 /32 主机地址）；`backend/app/models/network.py` 同步。真库 CHECK 定义已确认新写法（见 R3）。
- **代码基线**：HEAD `9bc9835` + 上述未提交修复；分支 `feature/F008-network-management`；Test Design TD-2；Contract/Database/D01 版本同 TE-1。
- **独立性声明**：focused/full pytest 与真库 raw SQL 均由 Tester 独立重跑，不复用 Backend 数字；raw SQL 在重建后的独立库 `csm_verify_test`（库名含 test）以 Alembic `upgrade head` 建表后直接执行，未连接生产或未知数据库。

#### TE-2 A. 执行命令与结果

| 编号 | 命令 | 结果摘要 |
| --- | --- | --- |
| R1 | `pytest tests/integration/test_network_constraints.py tests/integration/test_networks.py -q`（docker + f002test-net + `TEST_DATABASE_URL=csm_test`） | **32 passed, 1 warning in 12.04s**（TE-1 为 1 failed, 31 passed） |
| R2 | `pytest tests -q`（全量） | **249 passed, 1 skipped, 1 warning in 77.01s**（TE-1 为 1 failed, 248 passed, 1 skipped；skip 仍为 `test_migrations.py` superuser 环境性 V3b） |
| R3 | 独立库 `csm_verify_test`：`DROP DATABASE ... WITH (FORCE)` → `CREATE DATABASE` → `alembic upgrade head` → 读回 `pg_get_constraintdef(ck_networks_gateway)` | upgrade 0001→0008 全部 OK；单一 head `0008_networks`；CHECK 定义确认为 `... gateway <> (host(network((cidr)::inet))::inet) ... AND gateway <> (host(broadcast((cidr)::inet)))::inet ...` |
| R4 | 真库 raw SQL 直插 `networks`（真实 `ck_networks_gateway`，非 scratch 表；先建合法 cluster 满足 FK） | 见下表 |

**R4 逐项结果（独立验证库 `csm_verify_test`，真实约束）**

| 用例 | cidr / gateway | 预期 | 实际 | 判定 |
| --- | --- | --- | --- | --- |
| 网络地址 | `10.70.0.0/24` / `10.70.0.0` | 拒 | `REJECTED (ck_networks_gateway)` | **PASS** |
| 广播地址 | `10.71.0.0/24` / `10.71.0.255` | 拒 | `REJECTED (ck_networks_gateway)` | **PASS** |
| `/31` 下端 | `10.72.0.0/31` / `10.72.0.0` | 接受 | `ACCEPTED` | **PASS** |
| `/31` 上端 | `10.72.0.2/31` / `10.72.0.3` | 接受 | `ACCEPTED` | **PASS** |
| `/32` 非空 | `10.73.0.5/32` / `10.73.0.5` | 拒 | `REJECTED (ck_networks_gateway)` | **PASS** |
| 禁用 `0.0.0.0/8` | `10.74.0.0/24` / `10.0.0.1` | 拒 | `REJECTED (ck_networks_gateway)` | **PASS** |
| 禁用 `127/8` | `127.1.0.0/24` / `127.1.0.1` | 拒 | `REJECTED (ck_networks_gateway)` | **PASS** |
| 禁用 `169.254/16` | `169.254.5.0/24` / `169.254.5.7` | 拒 | `REJECTED (ck_networks_gateway)` | **PASS** |
| 禁用 `224/4` | `224.5.0.0/24` / `224.5.0.1` | 拒 | `REJECTED (ck_networks_gateway)` | **PASS** |
| 禁用 `240/4` | `240.5.0.0/24` / `240.5.0.1` | 拒 | `REJECTED (ck_networks_gateway)` | **PASS** |
| 合法 host | `10.75.0.0/24` / `10.75.0.10` | 接受 | `ACCEPTED` | **PASS** |
| CIDR 外越界 | `10.76.0.0/24` / `10.77.0.1` | 拒 | `REJECTED (ck_networks_gateway)` | **PASS** |

#### TE-2 B. 受影响验收/验证项状态更新

| 项 | TE-1 | TE-2 | 证据 |
| --- | --- | --- | --- |
| A10 gateway 空允许/越界禁用 422//32 必空 | PASS（API）+ DB 后盾缺陷 | **PASS（API + DB）** | API `test_gateway_boundaries`；R4 真库 CHECK 网络/广播拒 |
| V10 gateway 边界 | PASS（API）/ DB CHECK FAIL | **PASS（API + DB）** | 同上；R1/R3/R4 |
| B17 gateway 边界 | 网络/广播部分 DEF-01 | **PASS** | R4 全项；`/31` 两端接受、`/32` 非空拒、禁用 5 段拒、合法 host 接受 |
| 全量回归 | 1 failed, 248 passed, 1 skipped | **249 passed, 1 skipped** | R2 |

其余 A/V/B 项在本轮无受影响变更，TE-1 结论继续有效（均基于真实 PG 独立验证）。前端未变更，`npm run typecheck/build/smoke:client` 结果沿用 TE-1 C10（不再重跑）。

#### TE-2 C. Defects

| ID | Severity | Layer | Location | 证据/复现 | 状态 |
| --- | --- | --- | --- | --- | --- |
| DEF-F008-TE1-01 | HIGH | Backend / Database | `backend/alembic/versions/0008_networks.py` `ck_networks_gateway` | TE-1 C7；本轮 R3/R4 | **CLOSED（已修复并独立重测通过）** |

#### TE-2 D. 未验证项

| 项 | 原因 | 影响 |
| --- | --- | --- |
| A17 经入口 Nginx + Compose 全链路 | 同 TE-1 环境限制 | 仍以真实 ASGI 业务端点 + 真实 PG 覆盖权限矩阵；不降验收（沿用 TE-1） |
| A22/V22 下游、A11 容量数值 | 跨 Feature（F009/F010/F013） | 归对应 Feature，非本 Feature 阻塞 |
| I-3 禁用范围建网限制 | 待用户裁定 | 无 FAIL 判据 |
| 真实浏览器 DOM 渲染 | 非 F008 必要判据 | 前端以构建 + client 机制级为准 |

#### TE-2 E. 结论

DEF-F008-TE1-01 已关闭；R1 focused 32 passed、R2 全量 249 passed/1 skipped、R3+R4 真库 `ck_networks_gateway` 逐项符合预期。受影响 A10/V10/B17 及全量回归通过，无必须修复问题。**结论：`READY FOR REVIEW`。** 本次候选交付包含未提交的 backend 修复与测试改动，本轮测试有效性针对该工作区组合。

---

**TE-2 Git 声明**

```text
GIT: git status --porcelain
GIT: git rev-parse --short HEAD
GIT: git branch --show-current
GIT: git diff -- backend/alembic/versions/0008_networks.py backend/app/models/network.py
GIT: git diff --stat -- backend/tests/
GIT: git rev-parse --short HEAD
GIT: git status --porcelain
GIT: git diff --stat
```