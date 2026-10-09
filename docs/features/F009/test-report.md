# F009 IP Pool 地址池 — Test Report

本文件同时承载 TEST_DESIGN 与 TEST（TEST 阶段在同一文件追加执行结果）。两阶段分别记录版本、结论与证据；TEST_DESIGN 不填充执行 PASS。

---

## Test Design

- **版本**：TD-1
- **日期**：2026-10-09
- **角色**：Tester（TEST_DESIGN 模式）
- **结论**：`TEST DESIGN READY`（TD-1）
- **依据**：
  - `docs/product/requirements-v3.md` revision 3（§4、§4.1、§11、§11.1、§12、§12.1、§14、§20、§21、§22、§23、§25–§27、§28、§31 T15/T24/T25/T26/T31/T33/T34/T35/T40/T41、§35.2 Q04-A/Q04-B/Q10-A/Q10-B、§35.3 D01/D02）
  - `docs/features/F009/product.md`（PRODUCT `READY FOR ARCHITECT`，2026-10-09；A1–A23、I-1–I-6、明确排除项）
  - `docs/features/F009/architecture.md`（ARCHITECTURE `READY FOR DESIGN`，2026-10-09；§6 占用冲突跨 Feature 方案、§9 验证策略、DR-102–DR-117）
  - `docs/api/F009.md` 草案 v0（CONTRACT DRAFT，目标 READY；7 端点、字段契约 §2、错误码 §1.2 新增 `address_in_use`、分页排序过滤 §4、软删/恢复 §5/§6、校验顺序 §6、并发 §7、审计白名单 §8）
  - `docs/database/f009-ip-pool.md`（**尚未产出**，DATABASE Gate 未定稿；TD-1 按 architecture §7 草案假设）
  - `docs/architecture/d01-conventions.md` v7（§5/§5.8 待 v8 签核）
  - `docs/database/f008-network.md` v1（DB-D80–D94；F009 依赖的 Network 行锁域、引用检查器落点、gateway 语义）
  - `docs/api/F008.md` v1、`docs/features/F008/test-report.md`（TD-2/TE-2：TD 模式、夹具/环境口径、`committed_engine` 真提交模式）
  - `docs/features/F007/test-report.md`（TD 模式、夹具/环境、机制级证据边界）
  - `docs/project/handoff.md`、`docs/project/implementation-rules.md`、`.pi/skills/data-integrity/SKILL.md`、`AGENTS.md`
  - `docs/project/project-plan.yaml` plan_revision 4 F009 条目（`current_stage: DATABASE`，`next_action: DATABASE 与 TEST_DESIGN Gate`）
- **状态属性**：TD-1 `READY` 仅表示 A1–A23 已映射到可观察判据、边界/并发场景可执行、夹具与可验证性检查已建立；**不代表测试已运行、不填充执行 PASS、不批准实现或合并**。DATABASE 设计（`docs/database/f009-ip-pool.md`）与 CONTRACT（`docs/api/F009.md`）尚未定稿、D01 v8 未签核；§8 列 OPEN 待 DATABASE / CONTRACT Gate 后由 TD-2 逐项关闭。**不因 DATABASE 未定稿而直接 BLOCKED**（architecture §6/§9 已给出可执行的占用桩与并发方案）。跨功能完整 §31 回归与 §32 上线验收不在本 Feature（见 §5）。

### 版本记录

| 版本 | 日期 | 变更 |
| --- | --- | --- |
| TD-1 | 2026-10-09 | 初版：A1–A23 映射 V1–V30，边界/并发 B1–B44，夹具/环境设计，F009 独立/占用桩/留待 F010 三类分界，§8 OPEN 复核项（待 DATABASE/CONTRACT/D01 v8 后由 TD-2 关闭）。 |

> 复核基线（待 TD-2）：`docs/database/f009-ip-pool.md`（DATABASE Gate，未定稿）、`docs/api/F009.md` v0（CONTRACT Gate，未定稿）、`d01-conventions.md` v8 §5.8（未签核）。TD-1 的表名/列名/约束名/FK/生成列/排他约束形态/错误路径/占用结构/并发机制均按 architecture §6/§7 草案假设，TD-2 逐项核对后方可作为执行依据。

---

### 0. 数据完整性对应表（F009 范围）

方法依据 `.pi/skills/data-integrity/SKILL.md`；DB 列/约束以 DATABASE Gate 定稿为准（TD-1 为草案）。

| 规则依据及版本 | 作用域/写入入口 | 数据库保证（草案，待签核） | 业务层保证 | 并发/生命周期边界 | 验证与证据 |
| --- | --- | --- | --- | --- | --- |
| §4.1/§12/§27/DR-103 Pool 名称同 Network 未删唯一 | POST/PATCH/POST restore `/api/v1/ip-pools` | 部分唯一 `uq_ip_pools_network_id_name_key UNIQUE(network_id,name_key) WHERE deleted_at IS NULL` + `name_key` CHECK（translate 口径）+ name 长度/trim/非空/Cc 控制 CHECK | trim；逐码位 ASCII 折叠；冲突→409 `unique_conflict{field:"name"}`；内部普通空格保留不合并 | 索引仲裁；软删释放；恢复冲突拒 | V1/V2/V3/V16/V20/V21、B1–B8/B34；真实 PG |
| §12/§27/DR-104 起止属 Network CIDR、起≤止 | POST/PATCH | `start_address/end_address inet`；CHECK `start<=end`、`family=4`；跨表 CIDR 包含为应用主校验 +（待裁定的）触发 backstop | 越界/非 IPv4/逆序→422 field="start_address"/"end_address" | 无跨行并发 | V5/V6、B9–B14；真实 PG |
| §12/§27/DR-106 池范围同 Network 未删不重叠（含 RESERVED；INACTIVE 参与） | POST/PATCH/restore | `address_range int8range` 生成列（闭区间 `[]`）+ `EXCLUDE USING gist (network_id WITH =, address_range WITH &&) WHERE (deleted_at IS NULL)`（btree_gist 已由 0008 启用） | 先查冲突→409 `range_overlap{field:"start_address"|"end_address",conflicts}`；软删释放；恢复重检 | 排他约束原子兜底；并发双会话 B35；恢复重检 B34 | V7/V20、B15–B18/B35；真实 PG |
| §12/T15 allocation_mode 默认/取值 | POST/PATCH | `allocation_mode varchar(16) NOT NULL DEFAULT 'MANUAL'` + CHECK∈3 值 | 省略→MANUAL；非法/显式 null→422；保存并暴露 | — | V8/V9、B19–B21；真实 PG |
| §12/§14 IP 分配来源例外（删池不回收、来源历史保留） | DELETE/PATCH(缩小) | 池软删保行；F010 `ip_addresses.ip_pool_id` FK RESTRICT（F009 侧不建检查） | Pool 删除/缩小不做 IP 引用检查、不级联、不回收 | 软删后来源引用仍有效；F010 端到端 B/T34 | V14（结构层）、B29/B30；端到端归 F010 |
| §11.1/§12.1/T33 保留范围/网关占用冲突 | POST/PATCH(含 Network gateway) | 无（IP 数据在 F010） | `IpOccupancyProvider` 注册表；409 `address_in_use{field,conflict_count,conflicts,conflicts_truncated}`（含未绑定） | 与 F010 分配共用 `_lock_network`（networks 行 FOR UPDATE） | V10/V11/V12/V28（桩）、B22–B25/B37；端到端归 F010 |
| §21/§27 软删/恢复/引用 | DELETE/POST restore | `deleted_at`；部分唯一 + 排他约束谓词排除软删；FK RESTRICT | 恢复重检 name/Network 有效/范围不重叠/(RESERVED)占用；失败不覆盖；Network 侧引用检查（未删 Pool 阻止 Network 删/改 cidr/cluster） | 不级联；不回收；恢复与并发重建竞争 B36 | V15/V16/V30、B26–B31/B36 |
| §22 CREATE/UPDATE/DELETE/RESTORE 写 Audit 同事务 | Service `AuditService.record` | 复用 `audit_logs` append-only | `object_type="ip_pool"`；白名单 `{network_id,name,start_address,end_address,allocation_mode,description}`；异常同回滚 | 版本冲突无静默重试 | V18、B32/B33；真提交 |
| §23 权限矩阵；乐观锁 | `/api/v1/ip-pools*` | 复用 `version integer NOT NULL DEFAULT 1 CHECK >=1` | `require_permission`；条件 UPDATE `WHERE version=:expected`；rowcount=0→409 | 两连接同 version 仅一成功 | V17/V23、B38/B39；真提交 |
| §27/DR-114 迁移 0009 | Alembic `0009_ip_pools` | `down_revision=0008_networks`；全表新建无回填；单一 head；对称可逆 | — | 真库 up/down/up | V27、B40–B44 |

---

## 1. 验收映射（product.md A1–A23 → 验证项）

执行环境：`真实 PG` = 独立测试库（库名含 `test`）；`后端集成` = ASGI 应用 + 真实 PG（非 SQLite）；`真提交` = `committed_engine`（真实连接 + 真实提交 + TRUNCATE teardown）；`静态` = 路由清单/源码检查；`前端` = 构建 + client 机制级（真实 API 集成以入口 Nginx 为准）。**占用桩** = F009 注册的 `NullIpOccupancyProvider` 被测试侧替换为返回固定占用集的假 provider。

> **分界声明（关键）**：
> - **F009 独立可验证（不依赖 F010 数据）**：A1–A9、A13、A15 的范围/名称部分、A16–A21、A23；对应 §31 T15、T40、T41 的 F009 子集。
> - **F009 + 占用桩（可验证结构/数量/并发互斥，不能证明真实 IP 数据语义）**：A10–A12、A22 的冲突返回结构与数量、`_lock_network` 并发互斥。
> - **必须留待 F010 / F009+F010 端到端（F009 局部 PASS 无法覆盖）**：A10–A12、A14、A22 的真实 IP 占用端到端与 T33/T34/T35，以及容量 T32。
> - **不得以 F009 局部 PASS 拼接整条 T33/T35 通过**；端到端结论只能在 F010 交付后由集成测试给出。

| 验收（product.md） | 验证项 | 执行环境 | 可观察判据（PASS / FAIL） |
| --- | --- | --- | --- |
| A1 名称 trim/空名/控制字符拒；中文与内部普通空格允许且不合并 | **V1**；**V20** DB | 后端集成 + 真实 PG | PASS：`"  Web 1 "`→201 落库 `Web 1`；`""`/`"   "`/含 Cc/Cf→422；`"web 1"`/`"web  1"`/中文名→201 且内部普通空格原样保留（不合并）；raw 直插未 trim/空/超长被 CHECK 拒。FAIL：不 trim、内部空格被合并、空名落库、CHECK 缺失 |
| A2 同 Network 大小写不敏感重名拒（409 `unique_conflict{field:"name"}`）；跨 Network 同名允许 | **V2**；**V20** | 后端集成 + 真实 PG | PASS：同 network `WEB`/`web` 第二次 POST→409 `CONFLICT{reason:"unique_conflict",field:"name"}`；不同 network 同名→均 201；raw 直插同 `(network_id,name_key)` 未删被部分唯一拒。FAIL：重名成功、跨 Network 被拒、无兜底 |
| A3 软删后同名可重建；存活同名存在时创建失败；名称被复用时旧 Pool 恢复失败且不覆盖新对象 | **V3**；**V16** | 后端集成 + 真实 PG | PASS：软删同名→重建 201（新 id）；存活同名→创建失败；旧对象 restore→409 且新对象不被覆盖、旧对象保持软删。FAIL：软删后仍拒、覆盖新对象 |
| A4 缺 network/name/start/end 创建失败（422）；network 不存在/已软删→422 | **V4** | 后端集成 + 真实 PG | PASS：省略/`null`/`""` 各必填→422；随机 UUID→422；指向软删 Network→422 field="network"；无 Pool 行。FAIL：任一被接受 |
| A5 起止任一不属于 Network CIDR（越界）拒（422）；非 IPv4/非法地址拒（422） | **V5** | 后端集成 + 真实 PG | PASS：`10.0.0.300`、`999.1.1.1`、`not-an-ip`、CIDR 形式 `10.0.0.0/24`、IPv6→422；CIDR 外地址→422 field="start_address"/"end_address"；合法→201。FAIL：非法/越界被接受 |
| A6 start>end 逆序拒（422）；start=end（单地址池）允许 | **V6** | 后端集成 + 真实 PG | PASS：`start>end`→422；`start==end`→201；raw CHECK `start<=end` 拒逆序。FAIL：逆序落库、单地址池被拒 |
| A7 同 Network 与未删 Pool 范围重叠（闭区间相交，含完全相同、共享端点）拒（409 `range_overlap`） | **V7**；**V20** | 后端集成 + 真实 PG | PASS：完全包含/被包含/部分重叠/共享端点（如 `1.2–1.10` 与 `1.10–1.20`）→409 `CONFLICT{reason:"range_overlap",field,conflicts:[{object_type:"ip_pool",object_id,label,start_address,end_address}]}`；跨 Network 不拦；软删后同范围可建；raw 直插被排他约束拒。FAIL：重叠成功、共享端点漏判、跨 Network 被误拦 |
| A8 allocation_mode 省略→MANUAL；显式按值保存；非法/null→422 | **V8** | 后端集成 + 真实 PG | PASS：省略→`MANUAL`；显式 `AUTO`/`RESERVED` 落库；`"auto"`/`""`/`null`/其它→422；raw CHECK 拒非法。FAIL：默认错、非法落库 |
| A9 allocation_mode 语义正确保存并暴露（AUTO/MANUAL/RESERVED 分配行为归 F010） | **V9**；F010 | 后端集成 + 静态 | PASS（F009 侧）：响应/DB 正确暴露枚举值；静态核对 F009 无自动分配入口、不据 mode 自动创建 IP；语义消费归 F010。FAIL：F009 实现分配或值被改写 |
| A10 新建/扩大 RESERVED，变更后范围内存在未删除 IP（含未绑定）时拒，返回数量与可查询明细 | **V10**（桩）；**F010 端到端** | 后端集成 + 真实 PG + 占用桩 | PASS（桩）：注册返回固定占用集（含 `bound=false`）的假 provider 后，新建/扩大 RESERVED→409 `address_in_use{field:"allocation_mode"|"start_address"|"end_address",conflict_count,conflicts[],conflicts_truncated}`，`conflict_count` 与占用数一致。**真实 IP 占用端到端归 F010（T33）**。FAIL：占用被忽略、明细字段缺失、数量不符 |
| A11 AUTO/MANUAL 改为 RESERVED，范围内存在未删除 IP 时拒，返回数量与明细 | **V11**（桩）；**F010 端到端** | 后端集成 + 真实 PG + 占用桩 | PASS（桩）：`field="allocation_mode"`；数量/明细与桩一致；改为 AUTO/MANUAL 不触发拒绝。真实端到端归 F010（T33）。FAIL：改 RESERVED 成功、field 错误、数量不符 |
| A12 将已占用地址设为 gateway（Network PATCH）被拒（含未绑定），返回数量与明细 | **V12**（桩）；**F010 端到端** | 后端集成 + 真实 PG + 占用桩 | PASS（桩）：`network.update_network` gateway 变更且非空时经 provider 拒绝→409 `address_in_use{field:"gateway"}`；未占用 gateway 通过。真实端到端归 F010（T33）。FAIL：占用 gateway 被接受、无数量/明细 |
| A13 AUTO↔MANUAL 互换、RESERVED→AUTO/MANUAL 满足其它约束后允许，不改变已有 IP | **V13**；**F010 端到端** | 后端集成 + 真实 PG | PASS（F009 侧）：AUTO↔MANUAL、RESERVED→AUTO/MANUAL 均 200 且仅 mode 变更；F009 不触碰 IP（结构核对）。真实「不改已有 IP」端到端归 F010（T34）。FAIL：被误拒、连带改范围/IP |
| A14 删除或缩小 Pool（含 RESERVED）成功；已分配 IP 继续占用、不删除不释放，来源历史保留 | **V14**（结构层）；**F010 端到端** | 后端集成 + 真实 PG | PASS（F009 侧）：DELETE 与 PATCH 缩小范围→成功且写 audit；F009 不做 IP 引用检查、不级联（静态 + 桩核对）。真实 IP 保留与来源历史归 F010（T34）。FAIL：删池报 IP 引用冲突、级联删 IP |
| A15 RESERVED 恢复重检范围重叠与占用冲突；AUTO/MANUAL 恢复重检范围重叠；恢复不自动恢复 IP；失败不覆盖 | **V15**；**V16** | 后端集成 + 真实 PG + 占用桩 | PASS：RESERVED restore 时范围重叠→409 `range_overlap`、占用（桩）→409 `address_in_use`；AUTO/MANUAL restore 仅重检重叠；失败保持软删且不覆盖；恢复不创建 IP（静态 + 桩）。FAIL：restore 绕过占用、覆盖新对象 |
| A16 Pool 恢复重检名称唯一、Network 有效性、范围不重叠；失败不覆盖新对象 | **V16** | 后端集成 + 真实 PG | PASS：name 被复用→409 `unique_conflict`；Network 仍软删→409 `dependency_deleted{conflicts:[{object_type:"network",object_id}]}`；范围重叠→409 `range_overlap`；失败保持软删、新对象不被覆盖。FAIL：顺序/错误码不符、覆盖 |
| A17 权限：VIEWER 只读；EDITOR 增改；删除/查看已删/恢复 ADMIN | **V17** | 后端集成 + 前端 + Compose | PASS：VIEWER POST/PATCH→403、GET 200；EDITOR POST/PATCH 201/200、DELETE/restore 403；ADMIN 成功；未认证 401；`deleted=include|only` 非 VIEW_DELETED→403；服务端强制（静态核对）。FAIL：越权成功、仅前端隐藏 |
| A18 CREATE/UPDATE/DELETE/RESTORE 写 Audit 同事务；Activity 全角色 | **V18** | 后端集成 + 真实 PG（真提交） | PASS：四 action 各一条 `audit_logs`（`object_type="ip_pool"`、`object_id`=UUID、UPDATE 含 before/after、白名单字段）；`GET /activity` 对三角色 200；注入 audit 失败时业务与 audit 同回滚。FAIL：缺 action、不同事务、Activity 限权 |
| A19 默认列表隐藏软删、按 network 与 allocation_mode 过滤；分页/排序/过滤/模糊符合基线 | **V19** | 后端集成 + 真实 PG | PASS：默认无软删；`network_id`/`allocation_mode`/`q`/`deleted` 过滤正确；分页 `total/page/page_size` 边界正确；`sort∈{name,start_address,end_address,allocation_mode,created_at,updated_at}`+`order` 生效且附 `id` 稳定；非法参数→422。FAIL：软删泄漏、过滤/分页/排序错 |
| A20 DB 对同 Network 未删名称（归一化键）唯一与池范围不重叠兜底，真实 PG 验证 | **V20** | 真实 PG + 静态 | PASS：`pg_constraint`/`pg_indexes` 含部分唯一 `(network_id,name_key) WHERE deleted_at IS NULL` 与排他约束 `(network_id=,address_range&&) WHERE deleted_at IS NULL`；raw 直插存活重名/重叠被拒、软删后同名/同范围可插。FAIL：缺约束、全量唯一、仅 ORM 层 |
| A21 名称归一化在 API / 导入（F014）/ 搜索（F013）/ DB 间一致；仅未删参与唯一 | **V21**；F014/F013 | 后端集成 + 真实 PG + 静态 | PASS（F009 侧）：应用 `name_key` 与 DB `translate(btrim(name))` 逐项一致（仅 ASCII A–Z→a–z，中文/非 ASCII 原样）；软删不参与唯一；向 F014/F013 暴露同口径（静态核对）。F014/F013 执行各自一致性。FAIL：折叠口径不一致、软删参与 |
| A22 保留范围/网关变更与并发 IP 分配不能同时成功形成冲突；事务失败不留部分变更或错误容量 | **V22**（桩并发）；**F010 端到端** | 后端集成 + 真实 PG + 占用桩（真提交） | PASS（桩）：RESERVED 变更事务内 `_lock_network`（networks 行 FOR UPDATE）与「假分配」会话互斥，至多一方成功，断言最终持久化无「RESERVED 范围 + 冲突占用」共存；失败无部分变更。真实 IP 分配互斥与容量归 F010（T35/T32）。FAIL：双成功、留部分变更 |
| A23 乐观锁：过期版本编辑被拒（409 `VERSION_CONFLICT`），无静默覆盖 | **V23** | 后端集成 + 真实 PG（真提交） | PASS：两独立连接同 version PATCH，一方 200 且 `version+1`，另一方 409 `VERSION_CONFLICT{current_version}`；最终库值来自成功方。FAIL：双成功、无 409 |

补充验证项（非直接 A 映射）：

| 验证项 | 内容 | 环境 | 判据 |
| --- | --- | --- | --- |
| **V24** PATCH exclude_unset / 不可变 | 省略字段保持；显式 null 仅清 nullable（description）；必填显式 null（network/name/start/end/allocation_mode）→422；`network`/`network_id`/`id`/`name_key`/`metadata`/只读字段出现→422；未知字段→422 | 后端集成 | PASS：逐项符合 D01 §4 与 Contract §2.4；被拒请求不改库值与 `version` |
| **V25** 校验顺序 | POST/PATCH/DELETE/restore 优先级 | 后端集成 | PASS：POST 401→403→body(422)→network(422)→地址(422)→name 唯一(409)→范围重叠(409)→RESERVED 占用(409)→写+Audit→201；PATCH 401→403→body(422)→可见性(404)→version(409)→地址(422)→name 唯一(409)→重叠(409)→占用(409)→写+Audit→200；DELETE 401→403→对象(404)→version(422)→版本(409)→软删；restore name→network→重叠→占用 |
| **V26** 响应契约 | IPPool 响应字段/嵌套 | 后端集成 | PASS：含 `id、network{id,name,cidr}、name、start_address、end_address、allocation_mode、description|null、version、created_at/updated_at、deleted_at`；列表 `{items,page,page_size,total}`；不含 `name_key`/`address_range`/`metadata` |
| **V27** 迁移 0009 | Alembic up/down/up + 单一 head + 无回填 | 真实 PG | PASS：`alembic heads` 单一 `0009_ip_pools`（`down_revision=0008_networks`）；up 建表/约束/生成列/排他约束/索引；down 逆序且 0008 对象保留、不 drop btree_gist；re-up 集合一致；无回填 |
| **V28** 占用提供者注册表 | F009 注册 `NullIpOccupancyProvider`（空集为默认）；F010 注册真实提供者 | 后端集成 + 静态 | PASS：默认空集不误报；注册返回占用集的假 provider 后 A10–A12/A22 生效；调用点存在且与 `_lock_network` 组合 |
| **V29** FK 物理语义（机制级） | raw 物理 `DELETE FROM networks`（被未删 Pool 引用） | 真实 PG | PASS：被 FK RESTRICT 阻止（`confdeltype='r'`）；报告标注机制级（API 无物理删除路径） |
| **V30** Network 侧引用检查器 | F009 注册「未删 ip_pool 引用 Network」检查器 | 后端集成 + 真实 PG | PASS：有未删 Pool 的 Network DELETE/PATCH cidr/cluster→409 `reference_exists`+`references:[{object_type:"ip_pool",object_id,label}]`；软删 Pool 后 Network 可改/可删。FAIL：无 references、误拦 |

---

## 2. 边界与并发场景（B 编号，TEST 阶段执行）

| 编号 | 场景 | 步骤 | 判据 |
| --- | --- | --- | --- |
| B1 | 名称首尾空白 trim | `"  web  "`、`"\tweb\n"` | 201；落库 `web`；`name_key` 基于 trim 值 |
| B2 | 大小写不敏感重名 | 同 network `WEB`/`web`/`Web` | 后续均 409 `unique_conflict{field:"name"}`；首条 name 原样保留 |
| B3 | 非 ASCII 不折叠 | 中文名、含 `ß`/`İ` | 各自独立；仅 ASCII A–Z 折叠 |
| B4 | 内部普通空格不合并 | `"web 1"`、`"web  1"` | 201 且内部空格原样保留（不合并） |
| B5 | 空名/纯空白/控制字符 | `""`、`"   "`、含 `\x00`/`\x1f`/`\u200b` | 均 422；raw CHECK 拒 |
| B6 | name 长度 | 255 字符、256 字符 | 255 成功；256→422 / `varchar(255)` 拒 |
| B7 | 跨 Network 同名 | 两 network 各建同名 | 均 201（唯一作用域=同 network） |
| B8 | 软删后复用 | 软删同名→重建同名 | 201，新 id；部分唯一仅约束未删 |
| B9 | 起止格式/越界 | 非 IPv4、CIDR 形式、IPv6、CIDR 外地址 | 均 422 field="start_address"/"end_address" |
| B10 | 起止边界 | start=end；start=CIDR 网络地址；end=CIDR 广播地址 | start=end 201；网络/广播地址仍属 CIDR（I-3 不新增限制）→201 |
| B11 | 逆序 | start>end（含仅 end<start） | 422；raw CHECK 拒 |
| B12 | 逆序/越界同时出现 | 非 IPv4 且逆序 | 按 Contract §6 校验顺序出现首个 422；不落库 |
| B13 | start/end 在 CIDR 边界内但属禁用段 | 起止落在 `0/8`、`127/8`、`169.254/16`、`224/4`、`240/4` | F009 不新增禁用限制（I-3/DR-117）：仅校验属 CIDR 与起≤止，允许；禁用由 F010 分配集合排除 |
| B14 | 不同 Network 同地址范围 | 两 network 各建相同 `[x,y]` | 均 201（跨 Network 不拦） |
| B15 | 同 Network 重叠/相同 | 建 `[1,10]` 后建 `[5,20]`、`[1,10]`、`[10,20]`（共享端点） | 均 409 `range_overlap`；`conflicts[]` 含冲突 pool |
| B16 | INACTIVE Network 的池参与重叠 | INACTIVE Network 下池与新建重叠 | 409（INACTIVE 仍参与） |
| B17 | 软删不参与重叠 | 软删 A 后建同范围 B | 201；恢复 A 时重叠→409 |
| B18 | 缩小范围释放重叠 | A `[1,20]`、B `[30,40]`；PATCH A 为 `[1,10]` | 200；不回收 IP；无重叠 |
| B19 | mode 语义 | 省略 / `MANUAL` / `AUTO` / `RESERVED` / `"manual"` / `null` | 省略→MANUAL；显式保存；非法/null→422 |
| B20 | 非法 mode raw | raw 直插 `allocation_mode='OTHER'` | CHECK 拒 |
| B21 | mode 互转（无占用） | AUTO↔MANUAL、RESERVED→AUTO/MANUAL | 均 200；仅 mode 变、version+1 |
| B22 | 桩占用：新建 RESERVED 命中 | 注册占用集 `{a,b}` 含 `bound=false`；新建 RESERVED 覆盖之 | 409 `address_in_use`，`conflict_count=2`，`conflicts[]` 含 `bound:false`；`conflicts_truncated` 正确 |
| B23 | 桩占用：扩大 RESERVED 命中 | 已存在 RESERVED `[1,5]`，PATCH 扩大到 `[1,20]`，桩占用含 `[6,20]` 内地址 | 409 `address_in_use`；`field` 按触发字段（start/end） |
| B24 | 桩占用：AUTO/MANUAL→RESERVED 命中 | 桩占用在范围内；PATCH mode→RESERVED | 409 `address_in_use{field:"allocation_mode"}` |
| B25 | 桩占用：gateway 已占用 | 桩占用含某地址；Network PATCH 设该地址为 gateway | 409 `address_in_use{field:"gateway"}`，含未绑定明细；未占用 gateway 通过 |
| B26 | RESERVED 恢复命中占用 | 软删 RESERVED 后桩占用出现该范围；restore | 409 `address_in_use`；保持软删、不覆盖 |
| B27 | 恢复成功 | 软删→restore（name/Network/范围均有效） | 200；`deleted_at=null`；不创建 IP |
| B28 | 恢复依赖失效 | name 被复用 / Network 软删 / 范围被占 | 分别 409 `unique_conflict`/`dependency_deleted`/`range_overlap`；保持软删 |
| B29 | 删除/缩小不回收（结构层） | DELETE 池、PATCH 缩小 | 204/200；F009 不检查 IP 引用、不级联；写 audit |
| B30 | 来源历史（结构层） | 静态 + 桩核对 | F009 不删除/释放 IP；F010 持 `ip_pool_id` FK RESTRICT；端到端归 F010 |
| B31 | 软删默认隐藏 | 软删后 GET 详情/列表（默认） | 404/不在列表；`deleted` 过滤按 Contract 可见性 |
| B32 | 四 action Audit | CREATE/UPDATE/DELETE/RESTORE | 各一条 `object_type="ip_pool"`；UPDATE 含 before/after；Activity 全角色 200 |
| B33 | 审计同事务回滚 | 注入 audit 失败（创建/更新/删除/恢复） | 业务与 audit 同回滚；最终持久化为旧值/无新行 |
| B34 | 部分唯一 raw 兜底 | raw 直插同 `(network_id,name_key)` 未删；软删后同名 | 存活重名被 `uq_ip_pools_network_id_name_key` 拒；软删后同名成功 |
| B35 | **范围重叠并发双会话（真提交）** | `committed_engine` 两独立连接几乎同时 POST 同 Network 重叠范围 | 排他约束原子兜底，至多一方 201、另一方 409 `range_overlap`；最终库中同 Network 无重叠；断言最终持久化，不仅「未抛异常」 |
| B36 | **恢复与并发重建竞争（真提交）** | 软删 A 后并发：会话 1 restore A、会话 2 建同范围/同名 B | 至多一方成功；部分唯一/排他约束闭环；无两存活同名或重叠 |
| B37 | **保留范围变更 vs 假分配并发（真提交，桩）** | 会话 1 PATCH 池为 RESERVED（持 `_lock_network`），会话 2 以同一锁协议「假分配」写占用并提交 | 至多一方成功；最终持久化无「RESERVED 范围 + 冲突占用」共存；失败无部分变更；证明 A22 的锁域串行化（真实 IP 归 F010） |
| B38 | 权限矩阵 | 逐端点 VIEWER/EDITOR/ADMIN/未认证 | 符合 §23；服务端强制 |
| B39 | 乐观锁并发（真提交） | `committed_engine` 两连接同 version PATCH | 一方 200 且 version+1；另一方 409 `VERSION_CONFLICT`；无丢失更新 |
| B40 | PATCH exclude_unset / 显式 null / 不可变 | 省略保持；显式 null 仅清 description；必填/ network 显式 null→422；`network`/`name_key`/`metadata`→422 | 符合 D01 §4 与 Contract §2.4 |
| B41 | 校验顺序 | V25 各端点优先级 | 符合 Contract §6 |
| B42 | 响应契约/排序 | V19/V26 全参数组合 | 分页/排序/过滤正确；非 UUID/越界→422 |
| B43 | Network 侧引用保护端到端 | 有未删 Pool 的 Network DELETE/改 cidr/改 cluster | 409 `reference_exists`+references 含 ip_pool；软删后可改/可删 |
| B44 | 迁移 0009 up/down/up | `upgrade head`→`downgrade 0008`→`upgrade head`；`alembic heads` | 各步 0；单一 head `0009_ip_pools`；down 后表/约束消失、0008/btree_gist 保留；re-up 一致 |

并发说明：B33/B35/B36/B37/B39 及任何「失败不留痕/并发」用例必须使用 `committed_engine`（真实连接真实提交）或显式事务控制，断言**最终持久化状态 + 关系图**，不仅「未抛异常」。涉及部分唯一、排他约束、生成列、CHECK、FK、迁移的断言必须在真实 PostgreSQL 执行（SQLite / Mock 不作约束/并发证据）。占用冲突（A10–A12/A22）在 F009 阶段只能以桩 provider 断言结构与数量；**真实 IP 占用的端到端结果不得由桩用例推断**。

---

## 3. 夹具 / 环境设计

**复用 F001–F008 `backend/tests/conftest.py`（不改其护栏语义）**：
- `test_database_url`：独立测试库 + 安全护栏（库名含 `test`、`TEST_DATABASE_URL != DATABASE_URL`）；未设置则 skip 并告警，不静默改 SQLite。
- `pg_engine`：会话级 `DROP SCHEMA public CASCADE` + `CREATE SCHEMA public` + `alembic upgrade head`（含 0009），会话结束清理。
- `db_session`：函数级外层事务 + savepoint，回滚不跨用例污染（单事务用例）。
- `committed_engine`：真实提交用例（B33/B35/B36/B37/B39 及持久断言），teardown `TRUNCATE` 清理（排除 `alembic_version`；确认 `ip_pools` 在动态清理清单内），新开连接断言最终持久化。
- `alembic_runner`：迁移 up/down/up 用例（V27/B44）。
- 认证/权限 fixture（`auth_session_factory`/`auth_app`/`api_client`/`bootstrap_admin`/`make_user`/`login`）：F009 权限/审计证据使用**真实业务端点** `/api/v1/ip-pools*`（含 Network gateway PATCH `/api/v1/networks/{id}`）。
- F003/F004/F008 helper：`_create_cluster`、`network_factory`、`role_client_factory`、raw `insert_*`、软删/恢复、乐观锁 `two-session`、raw SQL 约束断言模式直接复用。

**F009 新增测试侧夹具/断言（由 Tester 落地于测试侧，实现阶段由 Backend 提供接口）**：
- `ip_pool_factory`：创建 IPPool（`network_id` + 可选 name/start/end/allocation_mode/description），返回对象与 `version`；供 A1–A23、B1–B44 复用。
- `IP_POOL_NAME_CASES`：表驱动名称数据（trim/大小写/中文/内部普通空格/控制字符/长度 1/255/256），确保 API 与 DB 同一口径（V1–V3/V20/V21、B1–B8）。
- `IP_POOL_ADDRESS_CASES`：表驱动起止数据（合法/越界/非 IPv4/CIDR 形式/IPv6/start=end/逆序/CIDR 网络·广播地址/禁用段），供 V5/V6 与 B9–B14。
- `IP_POOL_MODE_CASES`：mode 省略/合法值/非法/null（V8、B19/B20）。
- `assert_ip_pool_row(engine, id, expected)`：raw SQL 断言 `ip_pools` 各列值/`IS NULL`（含 `name_key`、生成列 `address_range` 语义）。
- `assert_partial_unique_ip_pool(engine, network_id, name_key, deleted)`：raw 直插断言部分唯一仅在 `deleted_at IS NULL` 生效（A2/A3/V20/B34）。
- `assert_addr_range_exclusion(engine, network_id, start, end, deleted)`：raw 直插断言同 Network 未删闭区间 `[start,end]` 被排他约束拒（含完全相同、共享端点），跨 Network/软删成功（A7/V20/B15–B18）。
- `assert_cidr_backstop(engine, ...)`：若 DATABASE 定稿加 CIDR 包含触发 backstop，raw 直插越界地址断言被拒；若裁定仅应用层，则记录为不适用并只做 API 断言（§8 OPEN-3）。
- `occupancy_stub`（fixture）：将 `NullIpOccupancyProvider` 替换为返回固定占用集（含 `bound=false`、`interface_id=null`、`resource_id=null`）的假 provider，teardown 恢复默认；供 A10–A12/A15/A22/V28 与 B22–B26/B37。
- `assert_address_in_use(engine_or_client, expected_count, fields)`：断言 409 `address_in_use` 的 `field`、`conflict_count`、`conflicts[]` 形状（`object_type/object_id/address/bound/interface_id/resource_id/resource_hostname`）、`conflicts_truncated` 及 `CONFLICT_PREVIEW_LIMIT` 截断行为。
- `assert_reference_protection(client, ...)`：端到端断言 Network↔Pool 的 409 `reference_exists`+references（V30/B43）。
- `assert_restore_recheck(...)`：恢复重检 name/Network/范围/(RESERVED)占用（A15/A16/B26–B28）。
- `assert_audit_same_txn(...)`：注入 audit 失败断言双回滚（V18/B33）。
- `two_session_overlap_insert` / `two_session_restore_vs_recreate` / `two_session_version_conflict` / `two_session_reserved_vs_fake_allocate`（复用 F004/F008 模式）：真实提交并发，供 B35/B36/B39/B37；后者须显式经 `_lock_network`（networks 行 FOR UPDATE）复现锁序。
- **F009 前端夹具**：复用 F005–F008 `smoke:client` 机制，新增 Pool 表单（Network 选择器不可改、起止 IPv4、allocation_mode、description）、已删开关与 ADMIN 恢复、422 点路径映射、`range_overlap`/`address_in_use` 明细呈现，供 A17/A19 与前端机制级用例。

**环境**：Docker / Compose 可用（F001–F008 TE 已证）；真实 PG 经 Compose `db`（`postgres:16`）。btree_gist 由 0008 已启用，0009 直接使用。

### 3.1 当前环境可执行性评估

| 验证项 | 环境要求 | 当前评估 | 降级/替代 |
| --- | --- | --- | --- |
| V1–V26、B1–B34/B38–B43 | 真实 PG + 后端集成 | 经 Compose `db` 可满足（F001–F008 已证） | 无 PG 时 skip 并标 BLOCKED，**不得**用 SQLite 替代约束/并发证据 |
| V27/B44 迁移 0009 | Alembic + 真实 PG | 可执行；依赖 0009 定稿 | 迁移未定稿则相关断言 BLOCKED，不降验收 |
| V28/A10–A12/B22–B26/B37 占用桩 | F009 已注册占用接口 | architecture §6 已定义接口；F009 实现后可用测试侧假 provider | 若接口未落地则 BLOCKED，不降验收 |
| B33/B35/B36/B37/B39 并发 | 真实并发提交 fixture | 可执行（复用 `committed_engine`） | 无 PG 时 BLOCKED；不得以顺序调用替代并发证据 |
| 前端机制级 / 真实 API 集成 | Node 22 + 构建；Compose 入口 | 可执行 | 真实浏览器 DOM 渲染非必要判据；镜像/端口问题记 BLOCKED |
| 真实 IP 占用端到端（T33/T34/T35）/容量 T32 | F010 交付 | **不可执行** | 标 `NOT TESTED / 归 F010`，不以 F009 桩 PASS 代替 |

---

## 4. 可验证性检查

| 项 | 判定 | 说明 |
| --- | --- | --- |
| A1/A2/A3 name 唯一/大小写/归一化/复用 | **可验证（API + DB）** | V1–V3/V16/V20/V21 + B1–B8/B34；部分唯一 + 应用检查双路径，真实 PG |
| A4 network 归属 | **可验证（API + DB）** | V4 + B9–B14 归属；FK + 应用校验 |
| A5/A6 地址格式/越界/逆序 | **可验证（API + DB）** | V5/V6 + B9–B13；PG inet/CHECK；CIDR 包含 DB backstop 待裁定（§8 OPEN-3） |
| A7 范围不重叠 | **可验证（API + DB）** | V7/V20 + B15–B18/B35；排他约束 + 应用映射 `range_overlap`；真提交并发 |
| A8/A9 mode 默认/语义暴露 | **可验证（API + DB + 静态）** | V8/V9 + B19–B21；默认值落库 + 静态核对无分配入口 |
| A10–A12 占用冲突 | **桩可验证结构/数量；端到端归 F010** | V10–V12/V28 + B22–B25；真实 IP 端到端（T33）F010 |
| A13/A14 池变更不回收 | **结构层可验证；端到端归 F010** | V13/V14 + B21/B29/B30；真实 IP 保留与来源历史（T34）F010 |
| A15/A16 恢复重检 | **可验证（端到端 + 桩）** | V15/V16 + B26–B28；真实端到端 409 |
| A17 权限矩阵 | **可验证（端到端 + 静态）** | V17 + B38；真实端点 + 服务端强制 |
| A18 审计 | **可验证（端到端 + 真提交）** | V18 + B32/B33；四 action + 同事务回滚 |
| A19 列表 | **可验证（端到端）** | V19 + B42；软删/过滤/分页/排序 |
| A20 DB 兜底 | **可验证（DB）** | V20 + B34/B35；真实 PG raw 直插 |
| A21 归一化一致 | **可验证（F009 侧）** | V21；API 与 DB 口径一致 + 软删不参与；F014/F013 执行各自 |
| A22 并发互斥 | **桩可验证互斥；真实分配端到端归 F010** | V22 + B37；断言最终持久化无冲突共存 |
| A23 乐观锁 | **可验证（真提交）** | V23 + B39；两连接同 version |
| V27/B44 迁移 0009 | **可验证（DB）** | 真实 PG up/down/up + 单一 head |
| B35/B36/B37/B39 并发 | **可验证（真提交）** | 复用 `committed_engine`，断言最终关系图 |
| V29 FK 物理语义 | **机制级** | API 无物理删除路径；raw SQL 验证 `confdeltype`，报告须显式标注 |

口径明确记录：**A10–A12/A15/A22 的占用部分在 F009 为桩 provider 结构与数量断言**；**A20/B34/B35/V29 为真实 PG raw SQL 机制级**；**A10–A12/A14/A22/T33/T34/T35 真实端到端与容量 T32 为 F010 不适用项**；**T15/T40/T41 的 F009 子集**（Pool 越界/逆序/重叠、名称规范/唯一/复用/恢复重检）在本 Feature 验证；**T24/T25/T26/T31 的完整回归不在本 Feature**，不得以 F009 局部 PASS 拼成整条通过。

---

## 5. 范围与不适用项声明

- **IP 自动/手动分配、解绑、释放、绑定 Interface、IP 唯一性、地址合法性执行、未绑定占用（§13/§14，F010）**：F009 不实现；仅提供池范围与 `allocation_mode`、占用检查接口/注册表、冲突返回结构、`_lock_network` 锁域、gateway 占用挂钩。真实 IP 占用端到端归 **F010**。
- **Network / AUTO 池容量数值与可分配/占用/剩余展示（§20，F010/F013）**：F009 不返回容量数值；`T32` 归 **F010/F013**。
- **Endpoint、Service 及关系（§15/§16，F011/F012）**：F009 不涉及。
- **CSV / Excel 导入（§24，F014）**：Pool 导入模板与执行归 **F014**；F009 仅提供字段口径供复用（A21 子集）。
- **全局搜索 / Dashboard / 列表聚合 / pg_trgm（§17/§19/§20/§28，F013）**：F009 仅承载 `/api/v1/ip-pools` 列表/过滤/排序（A19）与字段口径。
- **完整 Audit 查询页（§22，F015）**：F009 仅验证四 action 的资源级 Activity 快照。
- **IPv6、DHCP、路由、防火墙、VLAN 划分、网段自动发现、实时监控**：明确排除。
- **Pool 不落 metadata/status/auto_allocate/IP 列表**：明确排除；不因 RESERVED 自动创建 IP 或 Endpoint；不由名称/范围推断地址分类。
- **I-3 禁用范围建池限制**：architecture §11/DR-117 采纳「不新增建池范围限制」（仅属 CIDR 与起≤止）；是否收紧属新增业务限定，须用户裁定；TD-1 不生成对应 FAIL 判据（B13 仅记录现状允许）。
- **完整 T15/T24/T25/T26/T31/T33/T34/T35/T40/T41 回归与 §32 上线验收**：F009 仅承载 Pool 相关子集；跨 Feature 完整回归归 F016。**不声明上述条款完整通过**。
- **真实浏览器 DOM 渲染**：非 F009 必要判据，前端以构建 + client 机制级为准。

---

## 6. 风险与待核对项总结

| 项 | 评估 | 处理 |
| --- | --- | --- |
| V1–V26、B1–B34/B38–B43（真实 PG + 后端集成） | Docker/Compose 可用（F001–F008 已证）；**可执行** | 无 PG 时相关项 BLOCKED，不降验收 |
| V27/B44 迁移 0009 + 排他约束/生成列 | DATABASE Gate 未定稿 | 定稿后由 TD-2 核对；未定稿则相关断言 BLOCKED |
| A10–A12/A22 占用冲突 | F009 仅到达桩；真实 IP 在 F010 | F009 验结构与数量 + 并发互斥；端到端明确标注 `NOT TESTED / 归 F010`，不拼成 T33/T35 通过 |
| B35/B36/B37/B39 并发 | 需真实并发提交 fixture | 复用 `committed_engine`；断言最终关系图 |
| V29 物理 FK RESTRICT | API 无物理删除路径 | raw SQL 机制级验证 `confdeltype`，报告显式标注 |
| CIDR 包含 DB backstop | architecture §6/DR-104 标注待 Database 裁定（纯 SQL 触发 vs 应用主导） | TD-2 依 DATABASE 定稿核对 V5/B9–B13 断言层级（§8 OPEN-3） |
| `address_in_use`/`range_overlap` details 形状 | Contract 草案 §1.2 未定稿 | TD-2 依 Contract v1 固定 V7/V10–V12 判据（§8 OPEN-9/10） |
| D01 v8 §5.8 未签核 | name 长度 1–255、折叠、地址语义、mode 默认 | TD-2 依 D01 v8 核对（§8 OPEN-12） |
| DATABASE/CONTRACT/D01 v8 定稿状态 | **未定稿** | TD-1 §8 列全部待复核项；TD-2 逐项关闭 |

---

## 7. 独立性与执行口径（TEST 阶段适用）

- Backend pytest 由 Tester 独立重跑，不复用实现者数字。
- 迁移、生成列、排他约束、CHECK、FK、部分唯一、btree_gist 由 Tester 在独立库（库名含 `test`）以 Alembic / raw SQL 直接执行；不连接生产或未知数据库。
- 接口验证响应内容、类型、业务边界、非法输入与错误语义；只读功能（GET/activity）确认无业务写副作用。
- 占用冲突：F009 阶段以测试侧注册的假 `IpOccupancyProvider` 断言结构与数量；**明确标注桩证据边界，真实 IP 占用执行归 F010**，不以桩结果声称 T33/T35 通过。
- 前端验证状态、交互、错误与未知值处理；已批准范围要求真实前后端集成时经入口 Nginx 验证真实 API，不以 Mock 代替。
- 修复后按影响重测；首次设计检查与最终验收分别记录版本与证据。

---

## 8. OPEN 复核项（TD-1 提出，待 DATABASE / CONTRACT / D01 v8 定稿后由 TD-2 关闭）

> TD-1 `READY` 表示方案可验证，下列假设均未经逐项核对；**READY 不代表测试已执行、不批准实现或合并**。定稿后由 TD-2 关闭并固定执行判据。

### 8.1 待 DATABASE 定稿（`docs/database/f009-ip-pool.md`）

| # | TD-1 待复核假设 | 影响验证项 | Owner |
| --- | --- | --- | --- |
| OPEN-1 | 表名 `ip_pools`、列名/类型（`id`/`network_id`/`name varchar(255)`/`name_key varchar(255)`/`start_address inet`/`end_address inet`/`address_range int8range` 生成列/`allocation_mode varchar(16)`/`description text`/`version`/时间戳/`deleted_at`） | V1–V26、B1–B34 | Database |
| OPEN-2 | 约束/索引名：`pk_ip_pools`、`fk_ip_pools_network_id_networks`、`uq_ip_pools_network_id_name_key`、`excl_ip_pools_network_id_address_range`、name/name_key/mode/version/地址 CHECK 名、`ix_ip_pools_network_id/_allocation_mode/_deleted_at` | V3/V7/V8/V20/V26、B5/B15/B20/B34/B35 | Database |
| OPEN-3 | **排他约束精确形态** `EXCLUDE USING gist (network_id WITH =, address_range WITH &&) WHERE (deleted_at IS NULL)`；`address_range` 为 `int8range(...,'[]')` 生成列（或等价不可变表达式）；btree_gist opclass 依赖；跨表 CIDR 包含是否加触发 backstop（纯 SQL vs 应用主导） | V5/V7/V20/V27、B9–B18/B35/B44 | Database |
| OPEN-4 | name_key 口径 = `ASCII_lower(btrim(name))`（DB `translate`，禁 `lower()`）；name 长度 1–255 | V1/V2/V20/V21、B1–B6/B34 | Database / D01 v8 |
| OPEN-5 | 生成列 `address_range` 与 `start/end` 的 `family()=4`、`start<=end` CHECK 表达与不可变性 | V5/V6/V27、B9–B14 | Database |
| OPEN-6 | 迁移 `0009_ip_pools`（`down_revision=0008_networks`）单 head、全表新建无回填、对称可逆、不重复启用 btree_gist | V27、B44 | Database |
| OPEN-7 | FK `network_id → networks(id) ON DELETE RESTRICT`；索引集合（不建 pg_trgm/GIN） | V29/V30、B43/B44 | Database |
| OPEN-8 | 软删/恢复与约束交互（谓词排除软删；恢复置 null 重新受约束）；分配来源历史在 F010 的 FK 落点（F009 侧不建检查） | V14/V15/V16、B17/B26–B30 | Database / 跨 Feature |

### 8.2 待 CONTRACT 定稿（`docs/api/F009.md`）

| # | TD-1 待复核假设 | 影响验证项 | Owner |
| --- | --- | --- | --- |
| OPEN-9 | `address_in_use` 形状：`field∈{start_address,end_address,allocation_mode,gateway}`、`conflict_count`、`conflicts[]`（`object_type:"ip_address"`、`object_id`、`address`、`bound`、`interface_id`、`resource_id`、`resource_hostname`）、`conflicts_truncated`、`CONFLICT_PREVIEW_LIMIT`（建议默认 100） | A10–A12/A22/V10–V12、B22–B26 | Contract |
| OPEN-10 | `range_overlap` 复用登记（object_type `ip_pool`；`field∈{start_address,end_address}`；`conflicts[{object_type,object_id,label,start_address,end_address}]`）；顺带闭合 F008-REV-03 | A7/V7/V20、B15–B18 | Contract |
| OPEN-11 | 校验顺序 POST/PATCH/DELETE/restore（§6）与错误码层级（401→403→body→network→地址→name→重叠→占用→写+Audit） | V25、B41 | Contract |
| OPEN-12 | D01 v8 §5.8 签核：name 1–255、仅 ASCII 折叠、内部普通空格不合并；start/end 单主机 IPv4 属 CIDR 且起≤止；allocation_mode 默认 MANUAL；description text 无上限 | V1/V5/V8/V21、B1–B6/B9–B13 | Contract / D01 |
| OPEN-13 | `network` 创建必填、创建后不可改（PATCH 出现→422，DR-107/I-2） | V24、B40 | Contract |
| OPEN-14 | 软删可见性/恢复重检错误码优先级（name 复用 > Network 依赖 > 范围重叠 > RESERVED 占用）；`dependency_deleted` 形状 | A15/A16/V15/V16、B26–B28 | Contract |
| OPEN-15 | 列表 Query 参数集（`network_id/allocation_mode/q/deleted/page/page_size/sort/order`）与 `q` 口径、`deleted` 语义、`sort`/`order` 集合 | A19/V19、B42 | Contract |
| OPEN-16 | 占用检查触发条件（PATCH：mode→RESERVED、扩大范围、AUTO/MANUAL→RESERVED 才检查；缩小/RESERVED→AUTO/MANUAL 不拒绝）与 `field` 规则 | A10–A12/A13/V10–V13、B21–B24 | Contract |
| OPEN-17 | 跨 Feature 协议：F010 须复用 `_lock_network` 并注册真实 `IpOccupancyProvider`；F009 空集默认不误报 | V28/A22、B37 | Architect / 跨 Feature |

TD-1 结论：**`TEST DESIGN READY`** —— A1–A23 已映射到可观察判据，边界/并发场景可执行，夹具与可验证性已与 architecture §6/§9 草案建立对应；A10–A12/A22 在 F009 以占用桩断言结构与数量，真实端到端与容量明确留待 F010。**DATABASE / CONTRACT / D01 v8 尚未定稿，以上 OPEN 未经逐项核对；READY 不等于测试通过，不批准实现或合并。** 定稿后由 TD-2 关闭 §8 并固定执行判据。
---

## 9. TEST_DESIGN TD-2 — OPEN 复核关闭（依 Database v1 / Contract v1 / D01 v8）

- **版本**：TD-2
- **日期**：2026-10-09
- **角色**：Tester（TEST_DESIGN 模式）
- **结论**：`TEST DESIGN READY`（TD-2）。TD-1 全部假设已与定稿设计逐项核对，§8 OPEN-1…17 全部关闭；因 Database v1 设计产生的判据调整 D.3-A…G 已并入执行判据。TD-2 仍只是方案可验证声明，不代表测试通过、不批准实现或合并。
- **上游输入**：`docs/database/f009-ip-pool.md` v1（DB-D95–D110）、`docs/api/F009.md` v1（READY，ARCHITECT 2026-10-09）、`docs/architecture/d01-conventions.md` v8 §5.8、`docs/features/F009/architecture.md`（DR-102–DR-117）、`docs/api/F002.md` §1.2.1、`docs/features/F009/implementation.md`（BACKEND+FRONTEND COMPLETE）。

### 9.1 OPEN-1…17 关闭表

| # | 定稿结论（依据） | 判定 |
| --- | --- | --- |
| OPEN-1 | 表名 `ip_pools`；列 `id uuid pk`、`network_id uuid NOT NULL`、`name varchar(255) NOT NULL`、`name_key varchar(255) NOT NULL`、`start_address/end_address inet NOT NULL`、`address_range int8range NOT NULL`（生成列 STORED）、`allocation_mode varchar(16) NOT NULL DEFAULT 'MANUAL'`、`description text NULL`、`version int NOT NULL DEFAULT 1`、`created_at/updated_at timestamptz NOT NULL now()`、`deleted_at timestamptz NULL`（Database v1 §2）。TD-1 全部假设成立。 | CLOSED |
| OPEN-2 | 约束/索引名与 TD-1 一致：`pk_ip_pools`、`fk_ip_pools_network_id_networks`、`uq_ip_pools_network_id_name_key`、`excl_ip_pools_network_id_address_range`、`ck_ip_pools_{name_not_blank,name_trimmed,name_no_control,name_length,name_key_matches,start_address_host,end_address_host,address_order,allocation_mode,version}`、`ix_ip_pools_{network_id,allocation_mode,deleted_at}`（Database v1 §2）。 | CLOSED |
| OPEN-3 | 排他约束固定 `EXCLUDE USING gist (network_id WITH =, address_range WITH &&) WHERE (deleted_at IS NULL)`；`address_range` 为 `int8range(...,'[]')` 生成存储列；`network_id WITH =` 依赖 btree_gist（0008 已启用，0009 不重复启用）；跨表 CIDR 包含采纳**触发器 backstop**（DB-D104）。判据并入 D.3-B/D.3-C/D.3-F。 | CLOSED |
| OPEN-4 | `name_key = ASCII_lower(btrim(name))`，DB `translate('ABC…','abc…')`、禁 `lower()`；name 长度 1–255（`ck_ip_pools_name_key_matches` / `ck_ip_pools_name_length`；D01 v8 §5.8）。 | CLOSED |
| OPEN-5 | 生成列表达式 `int8range(set_masklen(x,32)-'0.0.0.0'::inet, …, '[]')`；`ck_start/end_address_host`=`family=4 AND masklen=32`；不可变性以 `pg_proc.provolatile='i'` 断言。判据 = D.3-A/D.3-C。 | CLOSED |
| OPEN-6 | 迁移 `0009_ip_pools`、`down_revision=0008_networks`、单一 head、全表新建无回填、对称可逆、不重复启用 btree_gist/pg_trgm（Database v1 §4）。判据 = D.3-F。 | CLOSED |
| OPEN-7 | FK `network_id → networks(id) ON DELETE RESTRICT`（`confdeltype='r'`）；索引仅 3 个普通索引 + 部分唯一 + 排他；不建 pg_trgm/GIN、不建单列 B-tree（DB-D106）。 | CLOSED |
| OPEN-8 | 软删/恢复：部分唯一与排他约束均带 `WHERE deleted_at IS NULL`；恢复置 null 重新受约束；F009 侧不建 IP 来源检查，来源历史由 F010 `ip_addresses.ip_pool_id` FK RESTRICT 承接（DB-D105/§3.6）。 | CLOSED |
| OPEN-9 | `address_in_use` 形状固定为 Contract §1.2：`field∈{start_address,end_address,allocation_mode,gateway}`、`conflict_count`（总数）、`conflicts[{object_type:"ip_address",object_id,address,bound,interface_id,resource_id,resource_hostname}]`、`conflicts_truncated`；`CONFLICT_PREVIEW_LIMIT=100`（可配置）。 | CLOSED |
| OPEN-10 | `range_overlap` 复用并登记至 F002 §1.2.1；`object_type:"ip_pool"`、`field∈{start_address,end_address}`、`conflicts[{object_type,object_id,label,start_address,end_address}]`；F008-REV-03 由 F002 §1.2.1 登记闭合。 | CLOSED |
| OPEN-11 | 校验顺序固定（Contract §6）：POST 401→403→body→network→`_lock_network`→地址→name→overlap→RESERVED 占用→写+Audit；PATCH 含 version/可见性→取锁→地址→name→overlap→占用；DELETE object→version→软删；RESTORE 见 OPEN-14。判据 = V25/B41。 | CLOSED |
| OPEN-12 | D01 v8 §5.8 已签核：name 1–255 仅 ASCII 折叠、内部普通空格不合并；start/end 单主机 IPv4 属 CIDR 且起≤止；allocation_mode 默认 MANUAL；description 无上限；不落 metadata/status/auto_allocate/容量。 | CLOSED |
| OPEN-13 | `network` 创建必填、创建后不可改（PATCH 出现 `network`/`network_id`/`id`/`name_key`/`address_range`/`metadata`/未知字段→422，DR-107/I-2）。 | CLOSED |
| OPEN-14 | RESTORE 错误码优先级固定（Contract §6.6）：查找(含软删 404)→`not_deleted`(409)→版本(409)→name 唯一(409)→Network 依赖 `dependency_deleted`(409)→**CIDR 包含重检 422 `VALIDATION_ERROR{field:start_address|end_address}`**→范围重叠(409)→RESERVED 占用(409)。判据 = D.3-D + 新增强化用例。 | CLOSED |
| OPEN-15 | 列表 Query 集固定：`network_id/allocation_mode/q/deleted/page/page_size/sort/order`；`deleted∈{exclude,include,only}` 默认 exclude；`sort∈{name,start_address,end_address,allocation_mode,created_at,updated_at}`、`order∈{asc,desc}`；`q` 为 name 大小写不敏感子串（trim 后空视为未提供，不用 pg_trgm）。 | CLOSED |
| OPEN-16 | 占用触发条件与 `field` 规则固定（Contract §6.4）：变更后 mode≠RESERVED 不拒绝；mode→RESERVED `field="allocation_mode"`；原 RESERVED 仅扩大 start→`start_address`、仅扩大 end→`end_address`；缩小/RESERVED→AUTO/MANUAL/AUTO↔MANUAL 不拒绝。 | CLOSED |
| OPEN-17 | 跨 Feature 协议固定（Contract §7/§9）：F009 默认 `NullIpOccupancyProvider` 空集不误报；F010 必须复用 `_lock_network`（networks 行 FOR UPDATE）并注册真实 `IpOccupancyProvider`；F009 只负机制级互斥，真实占用端到端归 F010（I-5）。 | CLOSED（F010 义务保留） |

### 9.2 因 Database v1 产生的判据调整（D.3-A…G，Architect CONTRACT 定稿已确认）

| 编号 | 调整后判据 | 对应执行 |
| --- | --- | --- |
| **D.3-A** | `start/end` CHECK 为 `family=4 AND masklen=32`；带掩码/CIDR 形式被 DB CHECK **拒**，API 仍返回 422。TD-1 的「CIDR 形式→422」在 DB 层升格为 CHECK 拒绝，不再仅是 `inet` 解析。 | V-DB-90、`test_address_domain`、`test_address_validation`、独立库 raw masked insert 拒绝 |
| **D.3-B** | CIDR 包含 DB 触发器 `trg_ip_pools_cidr_contains`（BEFORE INSERT/UPDATE）**已启用**：raw 越界直插/更新被拒；`/32` Network 内 `start=end` 通过；与 Network 改 cidr 经 `FOR KEY SHARE` 串行。 | V-DB-89、`test_cidr_contains_trigger`、独立库 raw 越界 INSERT/UPDATE 拒绝 + /32 通过 |
| **D.3-C** | `address_range` 为 `GENERATED ALWAYS AS (...) STORED` 生成列：UPDATE start/end 重算、单地址池 `[x,x]`、闭区间 `'[]'`、`provolatile='i'`。 | V-DB-87、`test_exclusion_overlap_and_generated_column`、独立库生成列表达式/重算/`provolatile` |
| **D.3-D** | Network cidr 变更致软删池越界的 RESTORE 固定为 **422 `VALIDATION_ERROR{field:start_address|end_address}`**；整体优先级 not_deleted→版本→name 唯一→network 依赖→CIDR 包含(422)→范围重叠→RESERVED 占用。 | Contract §6.6、`test_restore_cidr_recheck`、`test_restore_priority_precedence` |
| **D.3-E** | 触发器对 INSERT/UPDATE（含软删 UPDATE）生效；越界幽灵池的软删被拒属预期副作用。 | 独立库 raw：Network cidr 移走后软删越界池被拒 |
| **D.3-F** | 0009 不重复启用扩展；`pg_extension` 在 up/down/up 前后无新增（btree_gist 属 0008、pg_trgm 属 0001）。 | V-DB-82/94、`test_migration_up_down_up_and_single_head`、独立库 `pg_extension` 前后比对 |
| **D.3-G** | F008-REV-01/02 为 F008 文档 errata，不改变 F009 判据（0008 迁移已用正确写法）；F008-REV-03（`range_overlap` 登记）已由 F002 §1.2.1 闭合。 | 静态核对 `0008_networks.py`、`docs/api/F002.md` §1.2.1 |

TD-2 结论：**`TEST DESIGN READY`（TD-2）** —— OPEN-1…17 全部关闭，D.3-A…G 已并入执行判据；不批准实现或合并，测试结果见 §10。

---

## 10. TEST TE-1 — 独立执行

- **版本**：TE-1
- **日期**：2026-10-09
- **角色**：Tester（TEST 模式）
- **代码基线**：`da121db`（分支 `feature/F009-ip-pool`，工作区 clean；测试基线 HEAD=da121db）
- **测试基线**：TD-2 固定判据 / Database v1 / Contract v1 / D01 v8 §5.8
- **独立性声明**：Backend pytest、迁移 up/down/up、独立库 raw 结构/约束/触发器/并发、前端 typecheck/build/smoke 均由 Tester 独立重跑；未复用实现者数字。Tester 未修改任何业务实现、Schema、迁移或产品/设计文档；仅新增/强化测试代码（`test_ip_pools.py`、`test_ip_pool_constraints.py`）。任何「失败不留痕/并发」断言使用真实连接真实提交并断言**最终持久化状态**。

### 10.1 环境与命令

| 项 | 内容 |
| --- | --- |
| PG | 容器 `f002test-db`（`postgres:16`，网络 `f002test-net`），用户 `csm`，测试库 `csm_test`；独立验证库 `csm_ip_verify_test` |
| 后端镜像 | `csm-f007-test:latest`（源码挂载 `backend:/app`，未重建） |
| 全量后端 | `docker run --rm --network f002test-net -v "$PWD/backend:/app" -e TEST_DATABASE_URL="postgresql+psycopg://csm:change-me@f002test-db:5432/csm_test" -w /app csm-f007-test python -m pytest tests -q` |
| F009 专属 | 同镜像 `python -m pytest tests/integration/test_ip_pools.py tests/integration/test_ip_pool_constraints.py -q` |
| 独立库 | 独立脚本 `verify_db.py`：`DROP SCHEMA public` → `alembic upgrade head` → 结构/raw/并发核对 → `downgrade 0008` → `upgrade head`；连接 `csm_ip_verify_test` |
| 前端 | `cd frontend && npm run typecheck && npm run build && npm run smoke:client`（Node 22） |

### 10.2 执行结果（原始输出摘要）

```text
# 全量后端
292 passed, 1 skipped, 1 warning in 100.75s
# skip = tests/integration/test_migrations.py:105（F001 V3b：连接角色为 superuser，环境性，非 F009）

# F009 专属（test_ip_pools.py 30 + test_ip_pool_constraints.py 13 = 43）
43 passed, 1 warning in 19.38s

# 独立验证库（csm_ip_verify_test）
TOTAL 27 checks, 0 failed

# 前端
typecheck: 通过
build: 通过（61 modules，dist 产物生成）
smoke:client: 133 passed, 0 failed（含 F009 机制级用例）
```

> 注：实现者报告称全量 286 passed / F009 37 passed；Tester 独立基线因新增/强化测试代码高于该数（全量 292、F009 43），差异来自 Tester 新增的 A13/B13/B16/B26/A16 优先级/A22 互斥用例与独立库核对，非覆盖实现缺陷。

### 10.3 验收映射 A1–A23（TE-1）

| 验收 | 结果 | 证据 | 边界声明 |
| --- | --- | --- | --- |
| A1 名称 trim/空/控制字符/中文/内部普通空格 | **PASS** | `test_name_normalisation_and_uniqueness`（201 落库 trim；`""`/空白/`\x01`/`\u200b`/256→422 field=name；内部空格保留）、`test_name_boundaries_and_name_key`（raw CHECK 拒 `""`/空白/`x ` /` x`/控制/256，接受 255） | F009 独立 |
| A2 同 Network 大小写不敏感重名 409；跨 Network 同名允许 | **PASS** | `test_name_normalisation_and_uniqueness`（`POOL`→409 `unique_conflict{field:name}`；跨 network 201）、`test_partial_unique_name`（raw 同 `(network_id,name_key)` 未删被拒；跨 network 允许） | F009 独立 |
| A3 软删后同名可重建；存活同名拒；复用后旧对象恢复失败不覆盖 | **PASS** | `test_name_soft_delete_and_restore_reuse`（软删→重建 201 新 id；旧 restore→409 unique；新对象未被覆盖） | F009 独立 |
| A4 缺 network/name/start/end→422；network 不存在/软删→422 | **PASS** | `test_network_resolution`（`None`/`""`/非 UUID/随机 UUID→422 field=network；软删 Network→422）、`test_readonly_and_unknown_fields` | F009 独立 |
| A5 越界/非 IPv4/非法/CIDR 形式→422 | **PASS** | `test_address_validation`（`not-an-ip`/`10.0.0.1/24`/`::1`/CIDR 外→422 field=start/end）、`test_address_domain`（IPv6、带掩码 raw 拒） | F009 独立；DB backstop = D.3-A/B |
| A6 start>end→422；start=end 允许 | **PASS** | `test_address_validation`（单地址 201、逆序 422）、`test_address_domain`（raw 逆序拒）、独立库 `/32` start=end 通过 | F009 独立 |
| A7 同 Network 未删池闭区间重叠（含完全相同、共享端点）409 | **PASS** | `test_range_overlap_and_soft_delete_release`（contained/identical/share-start/share-end→409 `range_overlap` + conflicts 明细；相邻 201；跨 network 201；软删释放）、`test_inactive_network_pool_participates_in_overlap`、独立库 raw 排他+并发 | F009 独立 |
| A8 mode 默认 MANUAL；按值保存；非法/null→422 | **PASS** | `test_create_defaults_and_response_shape`（省略→MANUAL）、`test_allocation_mode`（三值保存；`"active"`/`""`/`NOPE`/`null`→422）、`test_defaults_and_not_null`（raw CHECK 拒） | F009 独立 |
| A9 mode 语义保存并暴露；F009 不实现分配 | **PASS（F009 侧）** | 响应/DB 暴露枚举（上述）；静态：F009 无自动分配入口、不据 mode 创建 IP；语义消费归 F010 | F009 独立 |
| A10 新建/扩大 RESERVED 命中占用→409 + 数量/明细 | **PASS（桩结构/数量）** | `test_occupancy_reserved_create_and_patch`（`conflict_count=2`、`conflicts[{bound:false}]`、field=allocation_mode）、`test_occupancy_patch_expansion_field_rules`、`test_occupancy_truncation`（`conflicts_truncated=true`） | 真实 IP 端到端 **NOT TESTED / 归 F010（T33）** |
| A11 AUTO/MANUAL→RESERVED 命中占用拒，明细 | **PASS（桩结构/数量）** | `test_occupancy_reserved_create_and_patch`（PATCH→RESERVED field=allocation_mode）、`test_occupancy_patch_expansion_field_rules` | 真实端到端 **NOT TESTED / 归 F010（T33）** |
| A12 gateway 设已占用地址被拒（含未绑定） | **PASS（桩结构/数量）** | `test_network_gateway_occupancy_hook`（field=gateway、conflict_count=1、bound=false；空 provider 通过） | 真实端到端 **NOT TESTED / 归 F010（T33）** |
| A13 AUTO↔MANUAL、RESERVED→AUTO/MANUAL 允许，不改已有 IP | **PASS（F009 侧）** | `test_allocation_mode_transitions`（AUTO↔MANUAL、RESERVED→AUTO/MANUAL 均 200 且仅 mode 变、不咨询占用）、`test_patch_exclude_unset_and_non_nullable`（范围/名称保持）；结构核对 F009 不触碰 IP | 真实「不改已有 IP」端到端 **NOT TESTED / 归 F010（T34）** |
| A14 删除/缩小 Pool 成功，已分配 IP 保留 | **PASS（F009 侧）** | `test_pool_delete_registers_no_reference_checker`（池软删 204、不查 IP 来源）、`test_patch_exclude_unset_and_non_nullable`（缩小 200）、`test_fk_restrict_and_soft_delete_retention`（软删保行） | 真实 IP 保留与来源历史 **NOT TESTED / 归 F010（T34）** |
| A15 RESERVED 恢复重检重叠/占用；AUTO/MANUAL 仅重检重叠；不自动恢复 IP | **PASS（桩）** | `test_restore_overlap_recheck`、`test_reserved_restore_rechecks_occupancy`（409 address_in_use，失败保持软删）、`test_restore_priority_precedence` | 真实占用端到端 **NOT TESTED / 归 F010** |
| A16 恢复重检 name/Network/范围；失败不覆盖 | **PASS** | `test_name_soft_delete_and_restore_reuse`、`test_restore_dependency_deleted`、`test_restore_overlap_recheck`、`test_restore_cidr_recheck`、`test_restore_priority_precedence` | F009 独立 |
| A17 权限矩阵 | **PASS** | `test_permission_matrix`（VIEWER POST/PATCH/DELETE 403、GET/activity 200；EDITOR POST/PATCH 201/200、DELETE/restore 403；ADMIN 全通；未认证 401；`deleted=include` 非 VIEW_DELETED→403）；服务端 `require_permission` 强制（静态） | 真实 ASGI + 真实 PG；入口 Nginx/Compose 未执行（见 §10.7） |
| A18 四 action Audit 同事务；Activity 全角色 | **PASS** | `test_audit_four_actions_and_activity`（四 action、object_type=ip_pool、UPDATE before/after 白名单、Activity 全角色 200）、`test_audit_rolls_back_with_the_transaction`（注入 audit 失败业务同回滚、无 BOGUS 行） | 真提交 |
| A19 默认隐藏软删；过滤/分页/排序 | **PASS** | `test_soft_delete_visibility_and_restore_priority`、`test_list_filters_sorting_pagination`（network_id/allocation_mode/q/deleted、分页 total/page/page_size、sort+order+id 稳定、非法→422） | F009 独立 |
| A20 DB 未删名称唯一/范围不重叠兜底 | **PASS** | `test_partial_unique_name`、`test_exclusion_overlap_and_generated_column`、独立库 raw 直插/`pg_indexes`/`pg_constraint` | 真实 PG raw |
| A21 归一化口径一致（仅未删参与唯一） | **PASS（F009 侧）** | `test_name_boundaries_and_name_key`（`ABC`+name_key`ABC` 被 `ck_name_key_matches` 拒=必须 translate；非 ASCII `网ß` 原样）、`test_name_normalisation_and_uniqueness` | F014/F013 执行各自一致性 |
| A22 保留范围/网关变更与并发分配互斥，无部分变更 | **PASS（机制级互斥）** | `test_network_row_lock_serialises_reserved_change_and_fake_allocate`（networks 行 FOR UPDATE 互斥，第二会话阻塞直至持有者提交）、`test_concurrent_overlapping_insert`（至多一方成功，最终库无重叠） | 真实 IP 分配互斥与容量 **NOT TESTED / 归 F010（T35/T32）** |
| A23 乐观锁过期被拒，无静默覆盖 | **PASS** | `test_optimistic_lock_two_sessions`（两连接同 version：一方 200/version+1，另一方 409 VERSION_CONFLICT{current_version:2}，最终值来自成功方）、`test_validation_order`（version 先于 name） | 真提交 |

### 10.4 V-DB-82…V-DB-94（真实 PG / 独立库）

| 验证项 | 结果 | 证据 |
| --- | --- | --- |
| V-DB-82 迁移 up/down/up、单一 head、`down_revision=0008_networks`、无回填、btree_gist 未重复启用 | **PASS** | `test_migration_up_down_up_and_single_head`；独立库 `TOTAL 27 checks, 0 failed` 中 single head / downgrade / `pg_extension` 前后一致 |
| V-DB-83 name 边界（0/空/首尾/控制/256 拒；1–255 接受；内部空格/中文保留） | **PASS** | `test_name_boundaries_and_name_key` |
| V-DB-84 name_key CHECK 与 translate 一致（`Web`/`WEB` 同键、`ß`/非 ASCII 原样） | **PASS** | `test_name_boundaries_and_name_key` |
| V-DB-85 部分唯一（同 Network 重名拒/跨 Network/软删释放/存活拒/恢复冲突） | **PASS** | `test_partial_unique_name`、`test_name_soft_delete_and_restore_reuse` |
| V-DB-86 排他约束（重叠/相同/共享端点拒；跨 Network 允许；INACTIVE 参与；软删释放） | **PASS** | `test_exclusion_overlap_and_generated_column`、`test_inactive_network_pool_participates_in_overlap` |
| V-DB-87 生成列（`[x,x]`、闭区间、UPDATE 重算、`set_masklen`、`provolatile='i'`） | **PASS** | `test_exclusion_overlap_and_generated_column`；独立库生成列 `attgenerated='s'`、表达式、重算、`provolatile` |
| V-DB-88 恢复重检（重叠时置 `deleted_at=null` 被排他拒） | **PASS** | `test_restore_recheck_overlap_rejected`；独立库 raw restore overlap 拒绝 |
| V-DB-89 CIDR 触发器（越界 INSERT/UPDATE 拒；/32 相等通过；start=end 通过；Network 缺失交 FK） | **PASS** | `test_cidr_contains_trigger`、`test_address_domain`；独立库 raw 越界 INSERT/UPDATE 拒、/32 通过 |
| V-DB-90 逆序拒/start=end 允许；IPv6/带掩码拒 | **PASS** | `test_address_domain`；独立库 raw masked insert 拒 |
| V-DB-91 FK RESTRICT（物理删有 Pool 的 Network 拒；软删 Pool 行仍在） | **PASS** | `test_fk_restrict_and_soft_delete_retention`；独立库 `confdeltype='r'` |
| V-DB-92 mode 默认/非法/显式 null；NOT NULL；network 变更无 DB 触发器 | **PASS** | `test_defaults_and_not_null`、`test_network_id_has_no_immutability_trigger` |
| V-DB-93 version 默认 1、<1 拒；乐观锁双会话仅一成功 | **PASS** | `test_defaults_and_not_null`、`test_optimistic_lock_two_sessions` |
| V-DB-94 对象目录（生成列/排他/部分唯一/触发器/3 索引；无 pg_trgm GIN；btree_gist 属 0008） | **PASS** | `test_table_catalogue_columns_constraints_indexes_triggers`；独立库列/约束/索引/触发器/扩展目录 |

### 10.5 边界/并发场景 B1–B44（TE-1）

| 编号 | 结果 | 证据 / 说明 |
| --- | --- | --- |
| B1 名称 trim | PASS | `test_name_normalisation_and_uniqueness` |
| B2 大小写不敏感重名 | PASS | 同上（`POOL`/`DUP`） |
| B3 非 ASCII 不折叠 | PASS | `test_name_boundaries_and_name_key`（`网ß`） |
| B4 内部普通空格不合并 | PASS | `test_name_normalisation_and_uniqueness`（`po ol`/`po  ol`） |
| B5 空名/纯空白/控制字符 | PASS | API 422 + raw CHECK 拒 |
| B6 name 长度 255/256 | PASS | `test_name_boundaries_and_name_key` |
| B7 跨 Network 同名 | PASS | `test_name_normalisation_and_uniqueness` |
| B8 软删后复用 | PASS | `test_name_soft_delete_and_restore_reuse` |
| B9 起止格式/越界 | PASS | `test_address_validation` |
| B10 起止边界 start=end / 网络·广播地址 | PASS（start=end、/32）；网络/广播地址未单列用例，由「属 CIDR 且起≤止」同一路径覆盖 | `test_address_validation`、独立库 `/32` |
| B11 逆序 | PASS | `test_address_validation`、`test_address_domain` |
| B12 逆序/越界同时出现取首个 422 | PASS | `test_validation_order`（地址先于 name 唯一） |
| B13 禁用段不新增限制 | PASS | `test_disabled_segments_not_restricted`（0/8、127/8、169.254/16、224/4、240/4 建池 201） |
| B14 不同 Network 同范围 | PASS | `test_range_overlap_and_soft_delete_release` |
| B15 同 Network 重叠/相同/共享端点 | PASS | 同上 |
| B16 INACTIVE Network 池参与重叠 | PASS | `test_inactive_network_pool_participates_in_overlap` |
| B17 软删不参与重叠 | PASS | `test_range_overlap_and_soft_delete_release` |
| B18 缩小范围释放重叠 | PASS | `test_occupancy_patch_expansion_field_rules`（纯缩小 200）、`test_patch_exclude_unset_and_non_nullable` |
| B19 mode 语义 | PASS | `test_allocation_mode` |
| B20 非法 mode raw | PASS | `test_defaults_and_not_null` |
| B21 mode 互转（无占用） | PASS | `test_allocation_mode_transitions` |
| B22 桩占用：新建 RESERVED 命中 | PASS | `test_occupancy_reserved_create_and_patch`（`bound=false` 明细） |
| B23 桩占用：扩大 RESERVED 命中 | PASS | `test_occupancy_patch_expansion_field_rules`（field=start/end） |
| B24 桩占用：AUTO/MANUAL→RESERVED | PASS | `test_occupancy_reserved_create_and_patch` |
| B25 桩占用：gateway 已占用 | PASS | `test_network_gateway_occupancy_hook` |
| B26 RESERVED 恢复命中占用 | PASS | `test_reserved_restore_rechecks_occupancy`（失败保持软删） |
| B27 恢复成功 | PASS | `test_soft_delete_visibility_and_restore_priority`（deleted_at=null，不创建 IP） |
| B28 恢复依赖失效 | PASS | `test_name_soft_delete_and_restore_reuse`/`test_restore_dependency_deleted`/`test_restore_overlap_recheck` |
| B29 删除/缩小不回收（结构层） | PASS | `test_pool_delete_registers_no_reference_checker` + 缩小 |
| B30 来源历史（结构层） | PASS | `test_fk_restrict_and_soft_delete_retention`（软删保行/FK RESTRICT）；真实来源历史归 F010 |
| B31 软删默认隐藏 | PASS | `test_soft_delete_visibility_and_restore_priority` |
| B32 四 action Audit | PASS | `test_audit_four_actions_and_activity` |
| B33 审计同事务回滚 | PASS | `test_audit_rolls_back_with_the_transaction` |
| B34 部分唯一 raw 兜底 | PASS | `test_partial_unique_name` |
| B35 范围重叠并发双会话 | PASS | `test_concurrent_overlapping_insert`（最终库仅 1 行） |
| B36 恢复与并发重建竞争 | **NOT TESTED（无两会话并发用例）** | 机制闭环由部分唯一 + 排他约束 + 恢复重检覆盖（B34/B35/B28）；未构造「软删 A 后并发 restore A vs 建同范围 B」的真提交双会话用例 |
| B37 保留范围变更 vs 假分配并发 | PASS（机制级） | `test_network_row_lock_serialises_reserved_change_and_fake_allocate`（锁互斥/阻塞）；真实 IP 分配归 F010 |
| B38 权限矩阵 | PASS | `test_permission_matrix` |
| B39 乐观锁并发 | PASS | `test_optimistic_lock_two_sessions` |
| B40 exclude_unset/显式 null/不可变 | PASS | `test_patch_exclude_unset_and_non_nullable`、`test_readonly_and_unknown_fields` |
| B41 校验顺序 | PASS | `test_validation_order`、`test_restore_priority_precedence` |
| B42 响应契约/排序 | PASS | `test_create_defaults_and_response_shape`、`test_list_filters_sorting_pagination` |
| B43 Network 侧引用保护端到端 | PASS | `test_reference_checker_blocks_network_change_and_delete` |
| B44 迁移 0009 up/down/up | PASS | `test_migration_up_down_up_and_single_head`、独立库 |

### 10.6 数据库 / 接口 / 前端 / 集成结果

- **数据库**：`f009-ip-pool.md` v1 与 D01 v8 §5.8 逐项核对通过；`pg_constraint`/`pg_indexes`/`pg_attribute`/`pg_proc`/`pg_trigger`/`pg_extension` 目录与设计一致；raw 直插验证 CHECK/部分唯一/排他/生成列/触发器/FK RESTRICT；迁移 up/down/up 对称、无回填、单一 head；独立库 27 项全 PASS。
- **接口**：7 端点契约（字段/类型/状态码/错误语义/分页排序过滤/软删可见性/恢复优先级/乐观锁/审计）由真实 ASGI + 真实 PG 覆盖；只读端点（GET 列表/详情/activity）为纯 SELECT，无业务写副作用。
- **前端**：`npm run typecheck` 通过；`npm run build` 通过（61 modules）；`npm run smoke:client` 133 passed / 0 failed，含 F009 机制级 24 用例（API URL/method/body、错误码含 `address_in_use`/`range_overlap`/`dependency_deleted`/`not_deleted`、表单解析与 exclude_unset 载荷、点路径映射）。
- **集成**：`F009 + 占用桩` 的冲突结构/数量与 `_lock_network` 互斥由真实 PG + 真提交覆盖；**F009 + F010 真实 IP 占用端到端未执行**（见 §10.7）。

### 10.7 Defects、未验证项与结论

**Defects（公共分级）**：无。TE-1 未发现业务实现缺陷、Schema 缺陷或契约偏差。

**NOTE（非缺陷）**：
1. `dependency_deleted` 与 name 复用/范围重叠在业务上不可同时成立（存在存活 Pool 的 Network 无法软删），故 OPEN-14 优先级中这两组 pair 不具备可构造执行场景；已在 `test_restore_priority_precedence` 注明。
2. `test_migration_up_down_up_and_single_head` 中 F001 V3b 因连接角色 superuser 跳过（环境性，非 F009）。
3. 入口 Nginx / Compose 全链路未执行：本任务不重建镜像；权限矩阵与接口已按同 F007/F008-TE-1 口径以真实 ASGI 业务端点 + 真实 PG 覆盖，不降验收。

**未验证项（明确不声明通过）**：
- A10–A12、A14、A22 的真实 IP 占用端到端；T33、T34、T35；容量 T32 —— **NOT TESTED / 归 F010 / F013**。F009 仅以占用桩与 `_lock_network` 机制级证据支持，**不得据此拼接整条 T33/T34/T35 通过**。
- B36（恢复 vs 并发重建）真提交双会话未执行（机制闭环已由部分唯一/排他/恢复重检覆盖）。
- B10 中 CIDR 网络地址/广播地址作为池起止的单列用例未单列（同一「属 CIDR 且起≤止」路径覆盖）。
- T24/T25/T26/T31 完整跨 Feature 回归与 §32 上线验收不在本 Feature，归 F016。

**TE-1 结论**：**`READY FOR REVIEW`** —— A1–A23 与 V-DB-82…V-DB-94 在 F009 范围内全部 PASS，B1–B44 除 B36（NOT TESTED，机制已闭环）外均 PASS，无必须修复问题；F010 端到端项已显式标注 NOT TESTED，未以局部 PASS 拼接整条 T 条款通过。

---

## 11. 版本记录（续）

| 版本 | 日期 | 变更 |
| --- | --- | --- |
| TD-1 | 2026-10-09 | 初版 Test Design（见 §Test Design）。 |
| TD-2 | 2026-10-09 | 依 Database v1 / Contract v1 / D01 v8 逐项关闭 OPEN-1…17；并入 D.3-A…G 判据调整；结论 `TEST DESIGN READY`。 |
| TE-1 | 2026-10-09 | 独立执行 A1–A23 / V-DB-82–94 / B1–B44；新增/强化测试代码（A13/B13/B16/B26/A16 优先级/A22 互斥）；全量后端 292 passed/1 skipped、F009 43 passed、独立库 27/27、前端 typecheck+build+smoke 133 passed；结论 `READY FOR REVIEW`，无 Defects。 |

> 保留 TD-1 全文作为历史；TE-1 未复用实现者数字。测试代码变更：`backend/tests/integration/test_ip_pools.py`、`backend/tests/integration/test_ip_pool_constraints.py`（新增：`test_restore_priority_precedence`、`test_allocation_mode_transitions`、`test_disabled_segments_not_restricted`、`test_inactive_network_pool_participates_in_overlap`、`test_reserved_restore_rechecks_occupancy`、`test_network_row_lock_serialises_reserved_change_and_fake_allocate`）。

GIT: git log --oneline -8
GIT: git status --short
GIT: git rev-parse --short HEAD
GIT: git diff --stat
