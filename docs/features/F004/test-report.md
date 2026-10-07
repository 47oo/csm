# F004 Resource 核心登记 — Test Report

本文件同时承载 TEST_DESIGN 与 TEST（TEST 阶段在同一文件追加执行结果）。两阶段分别记录版本、结论与证据；TEST_DESIGN 不填充执行 PASS。

---

## Test Design

- **版本**：TD-2（当前）；TD-1（2026-10-07）
- **日期**：TD-2 2026-10-08；TD-1 2026-10-07
- **角色**：Tester（TEST_DESIGN 模式）
- **结论**：`TEST DESIGN READY`
- **TD-2 变更（2026-10-08）**：DATABASE Gate（`docs/database/f004-resource.md` v1，2026-10-08）与 CONTRACT Gate（`docs/api/F004.md` v1，2026-10-08）已定稿，`d01-conventions.md` 升至 v3（§5.3）。
  1. 修正 **F004-TD-1-01（文档缺陷，LOW）**：TD-1 §0 对应表与 §2/B5 的 `hostname_key` 折叠方向笔误，原写作 `translate(btrim(hostname),'abc…','ABC…')`（大写方向），与 DB-D36/Contract §2.1/D01 §5.3 的**小写**口径 `translate(btrim(hostname),'ABC…','abc…')` 相反。TD-2 已改为小写方向；TD-1 该两处的表达式文本失效，验收判据（ASCII-only 小写折叠、非 ASCII 原样、部分唯一）不变。
  2. 关闭 TD-1 §8 全部 6 项 OPEN 复核项（DATABASE/CONTRACT 已定稿，见 §8-A）。
- **TD-1 生效范围**：A1–A13 映射、B1–B46 场景、夹具/环境设计、可验证性检查在本轮仍有效（除上述表达式文本笔误）；TD-1 标记为「对 DATABASE/CONTRACT 草案保留假设」，§8 待闭合项由 TD-2 关闭，不复用 TD-1 的草案假设作为定稿依据。
- **依据**：
  - `docs/product/requirements-v3.md` revision 3（§4、§4.1、§6、§7、§18、§21、§22、§23、§25、§27、§28、§31、§33）
  - `docs/features/F004/product.md`（READY FOR ARCHITECT；A1–A13 与边界）
  - `docs/features/F004/architecture.md`（READY FOR DESIGN；§1 方案、§3 API 草案、§4 Schema 草案、§5 验证策略、§6 DR-34–DR-45、§7 分工、§8 交 Tester）
  - `docs/architecture/d01-conventions.md` v2（§1 稳定 ID、§2 时间、§4 nullable/PATCH、§5 名称归一化与作用域、§6 归属与引用）
  - `docs/features/F003/test-report.md`（TD-2/TE-1/TE-2 fixture 与机制级口径：DB-D10 独立测试库 + 安全护栏、会话级重建 schema、函数级 savepoint、`committed_engine` 真实提交、认证/权限 fixture、恢复冲突与引用检查的机制级边界）
  - `docs/product/requirements-v3.md` §35.2 Q10-A/Q10-B、§35.3 D01/D02
  - `docs/project/project-plan.yaml` plan_revision 4，F004 条目（已批准，IN_PROGRESS；`current_stage=DATABASE`，`next_action` 含「并行 tester 测试设计」）
  - `docs/project/handoff.md`、`docs/project/implementation-rules.md`、`AGENTS.md`、`.pi/skills/data-integrity/SKILL.md`
- **状态属性**：READY 仅表示 A1–A13 可映射到可观察判据、边界/并发场景可执行、夹具与可验证性已核对；**不表示测试已运行、不批准实现或合并、不表示 T01/T02/T03/T11/T19/T37 完整通过**。F004 为「Resource 首个业务对象」，仅覆盖本 Feature 子集；完整 §31 跨功能回归归后续 Feature / 上线验收（见 §6）。
- **前置状态说明**：DATABASE Gate（`docs/database/f004-resource.md`）与 CONTRACT Gate（`docs/api/F004.md`）**尚未定稿**。本 TD-1 以 `architecture.md` 的 Schema 草案（§4）与 API 草案（§3）、DR-34–DR-45（多为 PROPOSED）为设计输入核对可验证性。TEST 执行前必须以两 Gate 定稿逐项核对；差异处升 TD-2 并注明失效范围（见 §8 OPEN）。

### 版本记录

| 版本 | 日期 | 变更 |
| --- | --- | --- |
| TD-1 | 2026-10-07 | 初版：A1–A13 映射 V1–V15，边界/并发 B1–B46，夹具/环境设计，可验证性检查（A12/A13、引用集为空、D01/D02），不适用项；对 DATABASE/CONTRACT Gate 保留 6 项待复核假设（见 §8）。 |
| TD-2 | 2026-10-08 | 修正 F004-TD-1-01（§0/B5 `hostname_key` 折叠方向改为小写 `translate(btrim(hostname),'ABC…','abc…')`）；依据 DATABASE v1 / CONTRACT v1 / D01 v3 关闭 §8 全部 OPEN 项；验收判据不变。 |

> 复核基线：`docs/features/F004/architecture.md`（ARCHITECTURE Gate，2026-10-07）。DATABASE/CONTRACT 定稿前的约束名、错误 reason、恢复冲突与引用检查机制均以架构草案为准，标记为待闭合。

---

### 0. 数据完整性对应表（F004 范围）

仅列 F004 已确认且在实现后需验证的完整性/持久化项；方法依据 `.pi/skills/data-integrity/SKILL.md`。数据库列以架构草案 §4 为准（待 DATABASE Gate 定稿核对）。

| 规则依据及版本 | 作用域/写入入口 | 数据库保证（草案，待 DB Gate） | 业务层保证 | 并发/生命周期边界 | 验证与证据 |
| --- | --- | --- | --- | --- | --- |
| §7 / §4.1 / §27（hostname 同 Cluster 唯一、跨 Cluster 允许、软删可重用、归一化共用） | POST/PATCH `/resources`、未来导入(F014) | `resources.hostname_key` + `uq_resources_cluster_id_hostname_key` **部分唯一 (cluster_id, hostname_key) WHERE deleted_at IS NULL**；`ck_resources_hostname_key_matches`（`translate(btrim(hostname),'ABC…','abc…')`） | `normalization.py` hostname 归一化键（btrim→非空→禁内部空白/控制→ASCII-only 小写）；冲突 409 `unique_conflict` | 并发同名由部分唯一索引兜底；软删释放该键；跨 Cluster 不受约束；短名/FQDN 按完整字符串 | V1/V3/V13、B1–B9/B37–B39；计划验证 |
| §4.1 / §6（所属 Cluster 创建必填；cluster 有效） | POST `/resources` | `fk_resources_cluster_id_clusters ON DELETE RESTRICT` | 前置校验存在且未软删，否则 422 `field:cluster` | Cluster 软删不删 Resource 行；FK 防止悬空引用 | V6、B16/B17/B40；计划验证 |
| §6（创建后不可改 cluster / resource_type；稳定 ID） | PATCH `/resources/{id}` | `trg_resources_immutable_fields`（BEFORE UPDATE，cluster_id/resource_type 变更抛错） | PATCH 含 cluster/cluster_id/resource_type/只读字段 → 422 | 软删/恢复不受影响；改名不改 id | V5/V9、B13/B14/B15/B46；计划验证 |
| §6（resource_type 枚举、role/status 枚举与默认、显式 null 拒绝、可扩展） | POST/PATCH `/resources` | `ck_resources_resource_type`、`ck_resources_role`、`ck_resources_status`；列 `DEFAULT 'OTHER'` / `'UNKNOWN'` | 省略默认；role/status 显式 null → 422；枚举非法 → 422 | 枚举扩展走迁移；一期不新增类型 | V4、B10–B12；计划验证 |
| §21（软删 deleted_at 默认隐藏；ADMIN 查看/恢复；引用检查；不隐式级联；恢复重检） | ORM `select`；DELETE/RESTORE `/resources/{id}` | `deleted_at timestamptz NULL`；`ix_resources_deleted_at`；Session 级 `with_loader_criteria` | `deleted=exclude\|include\|only`；恢复重检唯一性/所属对象有效性，失败 409 `CONFLICT{reason}` | 恢复只恢复自身；不覆盖新对象；Resource 自身引用来源在 F007+（当前空集），cluster←Resource 首个反向检查器 | V9/V13、B4/B23–B29/B41/B45；计划验证 |
| §22（Audit 四 action、同事务、不记敏感、持续保留） | Service 层 `AuditService.record`（同 Session 同 commit） | `audit_logs` append-only（复用 F003）；`ck_audit_logs_action` | 白名单 `{cluster_id,hostname,resource_type,role,status,description,metadata}`；`object_type="resource"` | 异常一起 rollback，回滚不留 audit；并发不可能产生半行 | V10、B30–B34；计划验证 |
| §23（读全角色、写 EDITOR/ADMIN、删除/看已删除/恢复 ADMIN；乐观锁） | `/resources*` 各端点 | `resources.version integer NOT NULL DEFAULT 1 CHECK >=1`（`ck_resources_version`）；条件 UPDATE `WHERE id AND version=:expected` | `require_permission` 服务端执行；`rowcount=0`→404/409 `VERSION_CONFLICT` | 两会话同 version 仅一成功；无静默重试 | V11、B35/B36；计划验证 |
| §4 / D01 §1（稳定 ID；内部关联用 UUID） | 全部写入 | `id UUID PK DEFAULT gen_random_uuid()`（沿用 DB-D13，不启用 pgcrypto/uuid-ossp） | 关联以 UUID；`cluster` 可传 UUID 或 code，落库为 UUID | 改名/hostname 变更不改 id；审计 object_id 恒等 UUID | V9/V14、B46；计划验证 |
| §21 / DR-40（引用删除限制，首个反向检查器） | DELETE `/clusters/{id}`（F003 端点行为收窄） | 无独立 DB 约束（由业务引用检查 + FK RESTRICT 共同保证） | F004 注册 cluster←resources 未删除引用检查器；有未删 Resource → 409 `reference_exists` + 引用列表 | 未删 Resource 阻止 Cluster 删除；无隐式级联 | V13、B40/B41；计划验证 |

---

## 1. 验收映射（product.md A1–A13 → 验证项）

执行环境：`Compose` = 干净环境 `docker compose up -d`（含 `migrate`/`bootstrap` 一次性服务）；`真实 PG` = 经 Compose `db` 或本机 PostgreSQL 的独立测试库（DB-D10，库名含 `test`）；`后端集成` = ASGI 应用 + 真实 PG 测试库（非 SQLite）；`静态` = 仓库/路由清单静态检查；`文档` = 签核记录核对；`前端` = 构建 + client 机制级用例（与真实 API 集成时以入口 Nginx 为准）。

| 验收（product.md） | 验证项 | 执行环境 | 可观察判据（PASS / FAIL） |
| --- | --- | --- | --- |
| A1 同 Cluster 重复 hostname 失败；跨 Cluster 同名允许 | **V1** hostname 唯一 + **V13** DB 约束 | 后端集成 + 真实 PG | PASS：Cluster C1 创建 `cn001` 后 C1 再创建 `cn001`/`CN001`/` cn001 ` → 409 `CONFLICT{reason:unique_conflict, field:hostname}`；Cluster C2 创建 `cn001` → 201；`uq_resources_cluster_id_hostname_key` 为部分唯一（B37）。FAIL：同 Cluster 变体创建成功、跨 Cluster 被拒、唯一索引无条件缺失 |
| A2 软删 hostname 后可重建 | **V2** 软删复用 | 后端集成 + 真实 PG | PASS：软删 C1/`cn001` 后 C1 再创建 `cn001` → 201；旧行仍 `deleted_at` 非空、`hostname_key` 保留；新行独立 id。FAIL：重建 409、旧行被覆盖、软删释放未生效 |
| A3 cn001/CN001/` cn001 ` 同 Cluster 相同；归一化规则固化为契约（导入执行在 F014） | **V3** 归一化 | 后端集成 + 真实 PG + 静态 | PASS：三者落库 `hostname` 均为小写 `cn001`、`hostname_key` 相同；非 ASCII（`straße`/`ﬁle`）按 ASCII-only 折叠原样保留，应用与 DB（`translate`）不变量 violations=0；`normalization.py` 单一 hostname 实现。FAIL：大小写/空白留存、多码位 Unicode 触发 500、app 与 DB 键不一致 |
| A4 role/status 省略默认 OTHER/UNKNOWN；role 显式 null 拒绝 | **V4** 默认与 null | 后端集成 + 真实 PG | PASS：POST 省略 role/status → 响应与库默认 `OTHER`/`UNKNOWN`；显式 `role:null`/`status:null` → 422 `VALIDATION_ERROR`；PATCH 省略角色字段保持原值（不重置默认）。FAIL：默认非 OTHER/UNKNOWN、显式 null 被接受、PATCH 省略被重置为默认 |
| A5 创建后改 cluster/resource_type 被拒（422） | **V5** 不可改字段 + **V13** 触发器 | 后端集成 + 真实 PG | PASS：PATCH 含 `cluster`/`cluster_id`/`resource_type`/只读字段 → 422；库中值/`version` 不变；raw SQL `UPDATE resources SET cluster_id=…`/`SET resource_type=…` 被 `trg_resources_immutable_fields` 拒绝。FAIL：API 接受、DB 触发器不生效或误伤 name/status |
| A6 所属 Cluster 缺失/不存在/已软删时创建失败；hostname 空/内部空白被拒 | **V6** cluster 归属 + hostname 校验 | 后端集成 + 真实 PG | PASS：POST 缺 `cluster`/`cluster=不存在的UUID或code`/指向软删 Cluster → 422 `field:cluster`；`hostname=""`/`"   "`/`"c n001"`/`"bad\x00"` → 422；raw SQL 直插被对应 CHECK 拒绝。FAIL：任一非法输入创建成功、错误码非 422/字段非 cluster |
| A7 列表组合过滤 cluster/type/role/status 符合 §25；分页/排序 | **V7** 列表契约 | 后端集成 + 前端 | PASS：`GET /resources?cluster=N96P&type=BARE_METAL&role=COMPUTE&status=IDLE` 各条件 AND 生效；`cluster_id`/`q` 生效；`sort∈{hostname,resource_type,role,status,created_at,updated_at}`+`order` 生效；`page_size∈1..100` 默认 20、`total` 准确；非法参数 → 422。FAIL：过滤/排序错误、越界被接受、total 不符 |
| A8 Detail Overview 显示 Hostname/Cluster/Type/Role/Status/Description | **V8** Detail Overview + **V15** 前端 | 后端集成 + 前端 | PASS：`GET /resources/{id}` 响应含嵌套 `cluster{id,code,name}` 与 overview 六字段；前端 Detail Overview 区域展示六要素，非 Overview 区域（Hardware 等）占位且未知值不伪装为空/0。FAIL：字段缺失、cluster 未展开、占位区域伪装成空列表 |
| A9 默认隐藏软删；ADMIN 查看已删并恢复；恢复重检失败不覆盖 | **V9** 软删/恢复 + **V13** | 后端集成 + 真实 PG + 前端 | PASS：默认 `deleted=exclude` 隐藏软删；`include`/`only` ADMIN 200、EDITOR/VIEWER 403 `FORBIDDEN{reason:permission}`；软删详情无参数 404（不泄露）、无权限 `deleted=true` 403、ADMIN 200；ADMIN restore 200 + RESTORE audit；未删 restore 409 `not_deleted`；软删后重建同 hostname 再 restore 旧对象 409 `unique_conflict` 且目标不恢复；所属 Cluster 仍软删时 restore 409 `dependency_deleted`（B27/B28）。FAIL：默认泄露软删、无权限可见、恢复覆盖新对象、恢复冲突未 409 |
| A10 四类 action 写 Audit 同事务；回滚不留痕；Activity 全角色、完整审计限 ADMIN | **V10** Audit/Activity | 后端集成 + 真实 PG + 前端 | PASS：CREATE/UPDATE/DELETE/RESTORE 各产生一行 `audit_logs`，字段齐全、`object_type="resource"`、快照为白名单字段；强制业务失败后同一事务回滚，audit 无残留行（B31）；`GET /resources/{id}/activity` VIEWER/EDITOR/ADMIN 均 200 且仅含该对象、按 `created_at` 升序；快照无敏感键（B33）。FAIL：缺 action、回滚留痕、Activity 越权/跨对象、快照含敏感字段 |
| A11 VIEWER 只读；EDITOR 增改不删/恢复；ADMIN 删/恢复/查看已删 | **V11** 权限矩阵 | 后端集成 + 前端 + Compose | PASS：VIEWER POST/PATCH/DELETE/restore → 403；EDITOR POST/PATCH → 201/200，DELETE/restore → 403；ADMIN DELETE/restore/include/only → 成功；未认证写 → 401；服务端强制（前端隐藏不替代，B39 静态核对）。FAIL：角色越权成功、仅前端隐藏而服务端放行 |
| A12 hostname 基础搜索接入全局搜索入口（完整模糊在 F013） | **V12** 基础搜索 | 后端集成 + 前端 | PASS：`GET /resources?q=cn00` 经 ILIKE 命中 `cn001`/`cn001x`，不匹配项排除；未引入 pg_trgm/GIN（静态核对，B21）。FAIL：q 不生效、引入 pg_trgm、大小写不敏感缺失 |
| A13 归一化与稳定 ID 由 D01 承载；hostname 归一化键列与 (cluster, hostname) 部分唯一首次建表落地 | **V14** D01/D02 签核 + **V13** 数据层 | 文档 + 真实 PG + 静态 | PASS：CONTRACT（`docs/api/F004.md`）记录 D01 Resource 域字段契约（hostname 归一化键、部分唯一范围、Role/Status 枚举与默认、422 语义、稳定 ID、时间契约）与 D02（同事务写路径、乐观锁版本列、错误语义）签核；DATABASE（`docs/database/f004-resource.md`）记录 Schema/约束/索引/触发器；实现 `normalization.py` 与 DB `translate` 表达式一致；`gen_random_uuid()` 默认、无 pgcrypto/uuid-ossp。FAIL：签核缺失或与实现不符、键列未落地、启用 pgcrypto |
| （A7/A8/A9/A11/A12 前端） | **V15** Resources 页面基线（前端） | 前端 + Compose | PASS：Resources 列表加载/过滤/排序/分页/搜索可用；Loading/Success/Empty/Error 状态齐全；Detail Overview 六要素；创建/编辑表单携带 `version`；409 冲突明确提示且不静默重试；ADMIN 已删开关与恢复入口可见、非 ADMIN 不呈现且服务端仍 403。FAIL：状态缺失、错误伪装空列表、409 静默覆盖、仅前端隐藏而不鉴权 |

---

## 2. 边界与并发场景（B 编号，TEST 阶段执行）

| 编号 | 场景 | 步骤 | 判据 |
| --- | --- | --- | --- |
| B1 | 同 Cluster 精确重复 hostname | C1 建 `cn001`；再 POST `cn001` | 409 `CONFLICT{reason:unique_conflict, field:hostname}`；库中仅一行 |
| B2 | 同 Cluster 大小写/首尾空白变体重复 | C1 建 `cn001`；分别建 `CN001`、` cn001 `、`Cn001` | 均 409；`hostname_key='cn001'` |
| B3 | 跨 Cluster 同名允许 | C1 建 `cn001`；C2 建 `cn001` | 均 201；两行 `hostname_key` 相同但 `cluster_id` 不同 |
| B4 | 软删后重建同 hostname | C1 软删 `cn001` 后 POST `cn001`（含 `CN001` 变体） | 201；旧行保留 `deleted_at`、新行独立 id |
| B5 | 归一化落库一致 | 分别建 `CN001`、` cn001 ` | 落库 `hostname='cn001'`；`hostname_key=translate(btrim(hostname),'A..Z','a..z')` 不变量 violations=0 |
| B6 | 非 ASCII 原样（ASCII-only 折叠） | 建 `straße`、`ﬁle`、`山河3`；对比 `STRASSE`/`STRAßE` | `straße`/`ﬁle`/`山河3` 建成功；`STRAßE` 与 `straße` 同 key；`STRASSE` 为不同 key（`ß` 不折叠为 `SS`）；无 500 |
| B7 | hostname 长度边界 | 建 1 字符、253 字符、254 字符（长度上限 PROPOSED，待 DB 定稿） | 1/253 成功（或按定稿上限）；超出 → 422；raw SQL 超长被 CHECK/列长拒绝 |
| B8 | hostname 空/空白/内部空白/控制字符 | POST `""`、`"   "`、`"c n001"`、`"c\tn001"`、`"bad\x00name"`、`"a\nb"` | 均 422（业务层）+ raw SQL 直插被 CHECK 拒绝 |
| B9 | 短名与 FQDN 按完整字符串 | C1 建 `cn001` 与 `cn001.example.com` | 均成功；不被合并为同一对象/同一键（完整字符串识别） |
| B10 | role/status 默认 | POST 省略 role/status | 响应与库默认 `OTHER`/`UNKNOWN` |
| B11 | role/status 显式 null | POST/PATCH `role:null`、`status:null` | 422 `VALIDATION_ERROR`；库值不变 |
| B12 | 枚举非法 | POST/PATCH `resource_type='STORAGE'`、`role='BOGUS'`、`status='RUNNING'` | 422；raw SQL 直插被 `ck_resources_resource_type`/`role`/`status` 拒绝 |
| B13 | cluster 不可改（API + DB） | PATCH body 含 `cluster` 或 `cluster_id`（任意值/同值）；raw SQL `UPDATE cluster_id` | API 422 `VALIDATION_ERROR`；DB 触发器拒绝；库值/`version` 不变 |
| B14 | resource_type 不可改（API + DB） | PATCH body 含 `resource_type`；raw SQL `UPDATE resource_type` | API 422；DB 触发器拒绝；库值不变 |
| B15 | 只读字段拒绝 | PATCH body 含 `id`/`version`(独立只读)/`created_at`/`updated_at`/`deleted_at` | 422；库值不变 |
| B16 | cluster 缺失/不存在/软删 | POST 缺 `cluster`；传不存在 UUID/code；传软删 Cluster 的 id/code | 均 422 `field:cluster`（缺失/不存在/软删返回同一字段语义，具体 code 按 CONTRACT 定稿） |
| B17 | cluster 引用形式 | POST `cluster=<UUID>` 与 `cluster=<code>`（大小写变体 code） | 均解析为同一 uuid；非法 code/UUID → 422 |
| B18 | 组合过滤符合 §25 | 建多 Cluster × type × role × status 组合；GET `?cluster=N96P&type=BARE_METAL&role=COMPUTE&status=IDLE` | 结果集为 AND 交集；`cluster_id` 与 `cluster` 语义一致 |
| B19 | 分页边界 | `page`/`page_size`：缺省、1、100、0、101、负数、非整数 | 缺省 page=1/page_size=20；1..100 接受；0/101/负/非法 → 422；`total` 准确 |
| B20 | 排序白名单与非法 | GET 六白名单字段 × asc/desc；`?sort=id`、`?sort=;DROP`、`?order=random` | 白名单排序正确稳定；非法 → 422，无 500/注入 |
| B21 | 模糊搜索 q（ILIKE） | 建 `cn001`、`CN002`、`node01`；GET `?q=cn00` | 命中 `cn001`/`CN002`；`node01` 排除；静态确认未引入 pg_trgm/GIN |
| B22 | 非法 deleted/type 查询值 | GET `?deleted=bogus`、`?type=STORAGE` | 422 `VALIDATION_ERROR` |
| B23 | 软删默认隐藏 | 建未删+软删各一；默认 GET 列表/详情 | 默认仅返回未删；软删对象按 id 无参数 GET → 404（不泄露） |
| B24 | include/only 越权与授权 | VIEWER/EDITOR GET `?deleted=include`/`only`；ADMIN 同参数；软删详情 `?deleted=true` | 非 ADMIN 403 `FORBIDDEN{reason:permission}`；ADMIN 200（include=未删+已删、only=仅已删）；无权限 `deleted=true` 403 |
| B25 | ADMIN 恢复成功 | ADMIN `POST /resources/{id}/restore`（带 version） | 200；`deleted_at=null`、`version+1`；写 RESTORE audit |
| B26 | 恢复 not_deleted | 对未删 Resource restore | 409 `CONFLICT{reason:not_deleted}`；目标不变 |
| B27 | 恢复 unique_conflict（自然路径） | 软删 C1/`cn001` → 重建 C1/`cn001` → restore 旧对象 | 409 `CONFLICT{reason:unique_conflict,field:hostname}`；旧对象保持软删，不覆盖新对象（可复现，非机制级） |
| B28 | 恢复 dependency_deleted（自然路径） | 软删所属 Cluster（其下 Resource 先软删或按 F003 收窄删除顺序构造）→ restore Resource | 409 `CONFLICT{reason:dependency_deleted, conflicts:[{object_type:"cluster",…}]}`；目标不恢复。若删除顺序无法自然构造则记机制级并标注 |
| B29 | 恢复不级联 | 恢复一个软删 Resource，库中存在其它软删对象/关系 | 仅目标恢复；关联对象状态不变 |
| B30 | Audit 四 action | 依次 CREATE/UPDATE/DELETE/RESTORE 一个 Resource | 恰 4 行 audit（+额外 UPDATE），action 与对象匹配；CREATE 无 before、DELETE 无 after |
| B31 | 强制失败回滚不留 audit | 在业务事务内注入强制异常使 commit 失败 | 业务变更与 audit 行均回滚，`audit_logs` 无该对象残留 |
| B32 | Activity 全角色 + 隔离 + 排序 | VIEWER/EDITOR/ADMIN GET `/{id}/activity`；再查其它对象 activity | 三角色均 200；仅返回该 `("resource", object_id)`；按 `created_at` 升序、同刻 id 升序 |
| B33 | Audit 无敏感字段 | 检查 CREATE/UPDATE 快照 JSON | 白名单仅 `{cluster_id,hostname,resource_type,role,status,description,metadata}`；无 password/token/secret |
| B34 | Audit 快照可序列化 | 断言 `before_data`/`after_data` JSON 可序列化 | 无序列化异常；`metadata` 对象保留 |
| B35 | 乐观锁两会话并发 | `committed_engine` 两独立连接读同 `version`，各自 PATCH/restore 真实提交 | 一方 200 且 `version+1`；另一方 409 `VERSION_CONFLICT{current_version}`；最终库值来自成功方，无丢失更新 |
| B36 | 前端无静默重试覆盖 | client 对 409 的处理 | 不自动重试、不覆盖；明确呈现冲突；fetch 仅调用一次 |
| B37 | 部分唯一索引 WHERE 谓词 | raw SQL 直插两行同 `cluster_id,hostname_key`（一行软删）；检查 `pg_indexes`/约束定义 | 部分唯一 `WHERE deleted_at IS NULL`；未删重复被拒、软删行不参与；非全量唯一 |
| B38 | 并发同 hostname 创建 | 两条真实连接并发创建同 Cluster 同 hostname | 仅一方成功、另一方 409/IntegrityError 映射 `unique_conflict`；最终库中该键仅一条未删行 |
| B39 | hostname_key CHECK 一致性 | raw SQL 直插 `hostname`/`hostname_key` 不一致行 | `ck_resources_hostname_key_matches` 拒绝；`pg_get_constraintdef` 含 `translate(`、不含 `lower(` |
| B40 | cluster FK RESTRICT + 引用检查 | raw SQL `DELETE clusters` 有 Resource 引用；API `DELETE /clusters/{id}` 有未删 Resource | FK `confdeltype='r'` 拒绝；API 409 `CONFLICT{reason:reference_exists, references:[…]}` |
| B41 | 引用检查边界（无未删 Resource 可删） | Resource 全部软删后 `DELETE /clusters/{id}` | 允许删除（F003 cluster 删除行为随 F004 收窄后的正确边界）；软删 Resource 不阻止 |
| B42 | metadata object CHECK + 整值替换 | raw SQL 直插 `metadata='[]'`/`'"x"'`/`'null'`；PATCH `metadata` 整值替换；`metadata:null` | 非法类型被 `ck_resources_metadata_object` 拒；PATCH 为整值替换（旧键消失）；显式 null → 422 |
| B43 | version CHECK + 稳定 ID | raw SQL 直插 `version=0`；PATCH 改 hostname/role/status/description/metadata 后核对 | `ck_resources_version` 拒绝 0；`id`/`created_at` 不变、`version` 递增、`audit_logs.object_id` 恒等 UUID |
| B44 | 迁移 0004 up/down/up | `upgrade head` → `downgrade 0003_clusters_audit` → `upgrade head`；`alembic heads` | 各步 0；down 后 `resources` 及约束/索引/触发器消失、F003 对象保留；re-up 对象集合一致；单一 head `0004_resources` |
| B45 | 软删过滤覆盖关系加载 | Resource eager 加载 `cluster` 关系；软删过滤下加载 | `with_loader_criteria(include_aliases=True)` 对关系加载同样注入；无软删行泄出（F003 B41 遗留项在此回归） |
| B46 | 改名不改身份 | 记录 `id`/`created_at`；PATCH hostname 及其他允许字段 | `id`/`created_at` 不变；`version` 递增；audit object_id 稳定 |

并发说明：B31/B35/B38 及任何“失败不留痕/并发不重复”用例必须使用 `committed_engine`（真实连接真实提交）或显式事务控制，断言**最终持久化状态**，不仅“未抛异常”。V13/B12/B37–B43 必须在真实 PostgreSQL 执行（SQLite 不作 CHECK/唯一/FK/触发器/UUID 证据）。

---

## 3. 夹具 / 环境设计

**复用 F001 `backend/tests/conftest.py`（不改其护栏语义）**：
- `test_database_url`：DB-D10 独立测试库 + 安全护栏（库名含 `test`、`TEST_DATABASE_URL != DATABASE_URL`）；未设置则 skip 并告警，不静默改 SQLite。
- `pg_engine`：会话级 `DROP SCHEMA public CASCADE` + `CREATE SCHEMA public` + `alembic upgrade head`（含 0004），会话结束清理。
- `db_session`：函数级外层事务 + savepoint，回滚不跨用例污染（用于 B1–B34/B37/B39–B43 等单事务用例）。
- `committed_engine`：真实提交用例（B31/B35/B38），teardown `TRUNCATE` 清理（**排除 `alembic_version`**；F004 追加 `resources` 到清理清单，`clusters`/`audit_logs` 已在 F003 清单），新开连接断言最终持久化。
- `alembic_runner`：迁移 up/down/up 用例（V13/B44）。

**复用 F002 认证/权限 fixture（`auth_session_factory`/`auth_app`/`api_client`/`bootstrap_admin`/`make_user`/`login`）**：
- `make_user(role, status=ACTIVE)` 生成 VIEWER/EDITOR/ADMIN；`login` 复用同一 Cookie 罐获得 `csm_session`；`api_client` 命中真实 ASGI 应用。
- F004 的权限/审计证据使用**真实业务端点** `/api/v1/resources*`（含恢复、include/only、activity），A9/A10/A11 为端到端。

**复用 F003 Cluster fixture（`backend/tests/clusters/conftest.py`）**：
- `cluster_factory`：为 Resource 提供所属 Cluster（`code/name/status`），供 A1–A13、B1–B46 复用。
- `soft_deleted_cluster`：构造 `dependency_deleted` 恢复路径（B28）与 cluster 引用检查（B40/B41）。

**F004 新增 Resource fixture（建议置于 `backend/tests/resources/conftest.py`；实现阶段由 Backend 落地，Tester 可调整测试侧）**：
- `resource_factory`：ORM/API 工厂，参数 `cluster/hostname/resource_type/role/status/description/metadata`，返回对象与 `version`；供 A1–A12、B1–B46 复用。
- `soft_deleted_resource`：软删后返回实体，供 B4/B23–B29/B37/B45。
- `partial_unique_assert`：以 raw SQL 断言 `uq_resources_cluster_id_hostname_key` 定义含 `WHERE deleted_at IS NULL`、拒绝重复未删行、放行软删行（B37/B38）。
- `reference_check_e2e`：端到端构造「有未删 Resource 的 Cluster」→ 调 `DELETE /clusters/{id}` 断言 409 `reference_exists` + 引用列表；全软删后断言删除成功（B40/B41）。
- `two_session_version_conflict`：基于 `committed_engine` 开两条独立连接读取同一 `version`，暴露“各自提交/最终断言”助手；供 B35。
- `HOSTNAME_NORMALIZATION_CASES`：表驱动数据（大小写/首尾空白变体、非 ASCII `straße`/`ﬁle`/`山河3`、空/内部空白/控制字符、短名/FQDN、长度边界），供 A1/A2/A3/B2/B5–B9/B39 共用，确保 API/查询/F014 导入共用同一归一化口径。
- `raw_sql(engine)`：以 raw SQL 直插非法值验证 CHECK/部分唯一/FK/触发器/UUID 默认（B12–B14/B37/B39/B42/B43），不依赖 ORM 校验。

**环境**：Docker / Compose 可用（F001/TE-1、F002/TE-1/TE-2、F003/TE-1/TE-2 已证）；真实 PG 经 Compose `db`（`postgres:16`）。宿主机无 `psql`/`pg_dump` 不影响本 Feature（DB 断言经 SQLAlchemy 或容器内 psql）。前端 V15 以构建 + client 机制级为主；若要求真实前后端集成，经入口 Nginx 验证，不以 Mock 代替（§4）。**环境风险（承 F003 D-TE-1）**：若以非默认入口端口运行 Compose，F004 写端点（POST/PATCH/DELETE/restore）需覆盖同源 CSRF 行为；应在与既有修复一致的 Nginx 配置下执行，或在报告标注该环境限制。

### 3.1 当前环境可执行性评估

| 验证项 | 环境要求 | 当前评估 | 降级/替代 |
| --- | --- | --- | --- |
| V1–V12/V13、B1–B46 | 真实 PostgreSQL 实例 + 后端集成 | 经 Compose `db` 可满足（F001–F003 已证） | 无 PG 时 skip 并标 BLOCKED，**不得**用 SQLite 替代约束/并发证据 |
| V13/B44 迁移 up/down/up | Alembic + 真实 PG（空表） | 可执行；依赖 0004 定稿 | 迁移未定稿则相关断言 BLOCKED，不降验收 |
| V15 前端 | Node 22 + 构建 | 可执行（F002/F003 smoke:client 已证） | 真实浏览器 DOM 渲染非必要判据（同 F001–F003） |
| Compose 冒烟 | Docker 可用、端口可用 | 可执行 | 镜像/端口问题记 BLOCKED 并说明 |

---

## 4. 可验证性检查

| 项 | 判定 | 说明 |
| --- | --- | --- |
| A12 基础搜索（ILIKE）vs 完整模糊（F013） | **可验证（限定范围）** | F004 仅验证 `GET /resources?q=<hostname>` 的 ILIKE 子串匹配与大小写不敏感入口（B21）；pg_trgm / GIN / 全局搜索 `/search` 归 F013，F004 不引入、不断言，**不表述为完整 T? 全局搜索通过**。静态核对确认未新建 pg_trgm 扩展或 GIN 索引。 |
| A13 D01/D02 签核核对 | **可验证（文档）** | CONTRACT 定稿需记录 D01 Resource 域字段契约（hostname 归一化键列、`(cluster_id,hostname_key)` 部分唯一范围、Role/Status 枚举与默认、创建必填、422 语义、稳定 ID、时间契约）与 D02 审计一致性/乐观锁；核对实现 `normalization.py` 与 DB `translate` 表达式一致（V14）。 |
| 部分唯一 vs F003 全量唯一 | **可验证（DB）** | B37/B38 明确 Resource 用部分唯一 `WHERE deleted_at IS NULL`（可重用），与 Cluster code 全量唯一（不可重用）不同，防误用；真实 PG 断言索引谓词。 |
| cluster 引用检查端到端 | **可验证（端到端）** | F004 首次注册 cluster←Resource 反向检查器，B40/B41 经真实 `DELETE /clusters/{id}` 端到端验证 409 `reference_exists` + 引用列表与全软删后放行；F003 cluster 删除行为随之收窄，属 §21 必然结果。 |
| Resource 自身引用集为空（`reference_exists` 删除 Resource） | **机制级，无自然路径** | F004 的 Resource 无被引用对象（Interface/VM/Service 归 F007–F012）；删除 Resource 的 `reference_exists` 无自然端到端路径，只能经**注册检查器机制级**验证，须在报告显式标注证据边界，不得表述为完整 T23/T24 通过。 |
| 恢复冲突自然路径 vs 机制级 | **部分自然、部分机制级** | B27 `unique_conflict`（软删后重建同 hostname 再恢复旧对象）为**自然端到端**；B28 `dependency_deleted`（所属 Cluster 软删）若删除顺序可自然构造则端到端，否则记机制级并标注。 |
| 不可改字段 API 422 + DB 触发器 | **可验证（端到端 + DB）** | B13/B14 双路径（API + raw SQL 触发器），真实 PG。 |
| metadata JSONB object / 部分唯一 / FK RESTRICT / 触发器 / time | **可验证（DB）** | B37–B43 raw SQL 断言，真实 PG。 |
| 软删过滤对关系加载 | **可验证（回归 F003 B41）** | F004 有真实 `cluster` 关系，B45 覆盖 `with_loader_criteria` 对 eager 关系注入；F003 B41 遗留项在此回归。 |
| Audit 快照 JSON 可序列化 | **可验证** | B34 断言 `before_data/after_data` 可 JSON 序列化且无敏感键；`metadata` 对象保留。 |
| Detail Overview 未知值处理 | **可验证（前端）** | V8/V15 断言未知/空值不伪装为空列表或 0；`description=null`、`metadata={}`、非 Overview 区域占位展示符合契约。 |
| 时间契约（§4/D01 §2） | **可验证** | 断言 `created_at/updated_at` timestamptz UTC、`updated_at` 由业务写路径维护、响应 ISO-8601 带偏移；跨功能时间契约完整回归归上线验收。 |

口径明确记录：**F004 的权限与审计为真实业务端点端到端**；Resource 删除的 `reference_exists` 为**机制级**（引用集为空）；`dependency_deleted` 视构造条件端到端或机制级；完整 §31 T01/T02/T03/T11/T19/T37 的跨功能回归与 T38/T39 硬件单位归后续 Feature；不得以局部 PASS 拼成完整 §31 通过。

---

## 5. 范围与前置核对（交 CONTRACT/DATABASE 定稿）

| 项 | TD-1 假设（据 architecture.md 草案） | 待定稿核对 |
| --- | --- | --- |
| 错误信封与 reason | 复用 F002/F003 信封；`CONFLICT{unique_conflict\|not_deleted\|dependency_deleted\|reference_exists}`、`VERSION_CONFLICT{current_version}`、`VALIDATION_ERROR`、`FORBIDDEN{reason}`、`NOT_FOUND` | `docs/api/F004.md` 定稿确认 reason 枚举、`field`/`references`/`conflicts` 字段 |
| cluster 缺失/不存在/软删语义 | 均 422 `VALIDATION_ERROR` `field:cluster`（DR-39，PROPOSED） | CONTRACT 确认 422 vs 404 与错误 code 文本 |
| 软删查询参数 | `deleted=exclude\|include\|only`（收敛 F003 基线）；include/only 需 `VIEW_DELETED` | CONTRACT 确认默认值与权限映射 |
| 恢复端点 | `POST /api/v1/resources/{id}/restore`，必带 version | CONTRACT 确认路径、方法、错误语义 |
| DB 约束/索引/触发器名 | `uq_resources_cluster_id_hostname_key`、`ck_resources_hostname_key_matches`、`ck_resources_resource_type`/`role`/`status`/`version`/`metadata_object`、hostname CHECK、`trg_resources_immutable_fields`、`fk_resources_cluster_id_clusters`、`ix_resources_*` | `docs/database/f004-resource.md` 定稿确认名称/行为；不一致则升 TD-2 |
| hostname 长度与字符集 | PROPOSED 长度 1–253；ASCII-only 折叠；长度/字符集待 DB/Product 核对（§35.3 D01 OPEN） | DATABASE/Product 确认；影响 B7 |
| 迁移 0004 | `0004_resources`，`down_revision="0003_clusters_audit"`，单一 head；up/down 对称 | DATABASE 确认单 head、数据安全策略 |
| 乐观锁 rowcount=0 语义 | 404 或 409 `VERSION_CONFLICT` | CONTRACT 明确区分 404（已删/不存在）与 409（版本过期） |
| 引用检查框架 | `object_type→checkers` 注册表；F004 注册 cluster←resources；Resource 自身引用集为空 | DATABASE/CONTRACT 确认空集行为与机制级口径 |
| type 查询参数命名 | `type=BARE_METAL\|VIRTUAL_MACHINE`（§25 示例） | CONTRACT 固定参数名与别名 |
| pg_trgm GIN 引入点 | F004 不引入（DR-45） | DATABASE 定稿确认；影响 B21 证据强度 |

---

## 6. 不适用项与边界声明

- **BareMetal / VM 明细（Hardware 区域、硬件与容量字段）**：归 F005/F006；F004 仅 Resource 公共字段，Detail 非 Overview 区域为占位，不实现、不断言。
- **完整 T37/T38/T39**：T37（默认值/Role 显式 null/接口类型不推断）中仅 Resource 部分在 F004 覆盖（V4/B10–B12）；T37 的 Interface/Network/Pool 部分归 F007+，T38/T39（硬件单位与容量、cpu_cores 语义）归 F005/F006。F004 **不声明** T37/T38/T39 完整通过。
- **T25/T26 完整回归**：权限矩阵（T25）与版本冲突/审计（T26）在 F004 仅覆盖 Resource 对象子集；完整跨 Feature 回归归后续 Feature / 上线验收。
- **CSV/Excel 导入**：D01 归一化口径由 F004/A13 固化供复用，但导入本身归 F014；F004 不执行导入用例，只验证「API 与导入共用同一归一化」的口径在实现层可复用（静态 + `normalization.py` 单一实现）。
- **Network/IP/Interface/Service 软删/审计**：这些对象的软删、恢复、审计端到端归 F007–F013；F004 仅 Resource 首个业务对象 + cluster 引用检查。
- **§19 关联区域与组合过滤线**：Resources/Networks/IPs/VMs/Services 关联区域随 F005+ 接入；F004 不宣称完整 §19。
- **全局搜索 / pg_trgm / GIN**：归 F013；F004 仅基础 ILIKE 搜索入口（A12）。
- **完整跨对象 Audit 查询界面**：归 F015/F016；F004 仅 Resource 对象 Activity（B32）与被删除可见性。
- **§32 整体上线验收**：归 F016；Feature 通过 ≠ 上线授权。
- **真实浏览器 DOM 渲染**：非 F004 必要判据（同 F001–F003），前端以构建 + client 机制级 +（如要求）入口真实 API 集成为准。

---

## 7. 环境可执行性评估与风险

| 项 | 评估 | 处理 |
| --- | --- | --- |
| V1–V12/V13（真实 PG + 后端集成） | Docker/Compose 可用（F001–F003 已证）；**可执行** | 无 PG 时相关项 BLOCKED，不降验收 |
| V13/B44 迁移（0004 定稿） | 依赖 DATABASE Gate | 未定稿 → BLOCKED，不降验收 |
| B35/B38 并发（乐观锁、同 hostname） | 需真实并发提交 fixture | 复用 `committed_engine`；断言最终持久化与 `current_version`/`unique_conflict` |
| B28 `dependency_deleted` 恢复冲突 | 需构造「所属 Cluster 软删而 Resource 仍在」路径 | 若 F003 cluster 删除收窄使自然路径不可达，则记机制级并标注，不表述为完整 T24 |
| B31 同事务回滚 | 需可注入的业务失败点 | 以约束冲突/异常注入制造 commit 失败，断言业务与 audit 双回滚 |
| V15 前端 | 构建 + client 机制级 | 若真实前后端集成要求，经入口 Nginx 验证；CSRF 端口风险承 F003 D-TE-1 |
| DATABASE/CONTRACT 未定稿 | **MEDIUM**：约束名/reason/hostname 长度/恢复与 cluster 归属语义可能微调 | TEST 执行前逐项核对 §5；差异升 TD-2 并注明失效范围 |
| hostname 长度/字符集（§35.3 D01 OPEN） | **LOW**：若 Product 收紧 ASCII-only 可能影响命名兼容性 | 以 CONTRACT 定稿为准；B7 判据按定稿调整 |

---

## 8. OPEN 复核项（TD-1 提出，TD-2 全部关闭）

> **TD-2（2026-10-08）状态：全部 CLOSED。** DATABASE Gate（`docs/database/f004-resource.md` v1）与 CONTRACT Gate（`docs/api/F004.md` v1）已定稿，`d01-conventions.md` 升至 v3；下表各假设逐项与定稿核对，无判据差异（除 F004-TD-1-01 表达式文本笔误，已于 TD-2 修正）。TD-1 的「待定稿假设」不再作为执行依据，TEST 以定稿 Contract/DB/D01 为准。

| # | TD-1 假设 | 状态 | 定稿核对（依据 / 影响） |
| --- | --- | --- | --- |
| 1 | `resources` 列、约束名、索引、触发器（§0/V13/B12–B14/B37–B43） | **CLOSED**（DATABASE v1 §2–§4 完全一致） | 列/CHECK/索引名与 `0004_resources.py` 逐项一致；`trg_resources_immutable_fields` 存在 |
| 2 | hostname 长度与字符集、ASCII-only 折叠 | **CLOSED**（DB-D36/D37；Contract §2.1；D01 v3 §5.3） | 长度 1–253（Unicode code point）、宽松字符集、仅 ASCII A-Z→a-z 折叠（禁用 str.lower()/lower()）；B6/B7 判据按此执行 |
| 3 | 部分唯一 `WHERE deleted_at IS NULL` 与查询覆盖 | **CLOSED**（DB-D38；Contract §2.1） | `uq_resources_cluster_id_hostname_key` 部分唯一；与 F003 全量唯一相反；B37/B38 按此断言 |
| 4 | 迁移 `0004_resources` 对称可逆与单 head | **CLOSED**（DB-D42；DB §5） | `revision=0004_resources`、`down_revision=0003_clusters_audit`、单一 head；B44 按此执行 |
| 5 | `CONFLICT` reason 枚举、cluster 归属 422 语义、`VERSION_CONFLICT` 复用 | **CLOSED**（Contract §1.2/§6.2/§7） | reason 枚举 `unique_conflict`/`not_deleted`/`dependency_deleted`/`reference_exists`；cluster 缺失/不存在/软删统一 422 `field:cluster`；VERSION_CONFLICT{current_version} 复用 |
| 6 | 恢复端点路径/方法/必带 version；type 查询参数命名 | **CLOSED**（Contract §6.6/§4） | `POST /api/v1/resources/{id}/restore`，version 必填；查询参数规范名 `type`，无 `resource_type` 别名 |

TD-1 未闭合项已由 TD-2 关闭；若实现或 Contract 后续变更导致判据差异，须再升 TD-3 并注明失效范围。

---

## Test Execution

- **版本**：TE-1
- **日期**：2026-10-08
- **角色**：Tester（TEST 模式）
- **结论**：`READY FOR REVIEW`
- **执行基线**：Contract `docs/api/F004.md` v1（2026-10-08）、DATABASE `docs/database/f004-resource.md` v1（2026-10-08）、D01 v3（§5.3）、architecture §10 `READY FOR IMPLEMENTATION`；TD-2（含 F004-TD-1-01 修正）。
- **代码基线**：`feature/F004-resource-core`，HEAD `f18485c`（backend/frontend COMPLETE 检查点）。

### 环境

| 项 | 值 |
| --- | --- |
| 后端测试镜像 | `docker build --target test -t csm-backend-f004te1 ./backend`（Python 3.12，pytest 8.4.2） |
| 数据库 | 独立容器 `f004te1-db`（`postgres:16.15`，网络 `f004te1-net`，端口 55434）；测试库 `csm_test`、独立验证库 `csm_verify` |
| 集成 | `TEST_DATABASE_URL=postgresql+psycopg://csm:change-me@f004te1-db:5432/csm_test`（DB-D10 护栏：库名含 `test`、≠ `DATABASE_URL`） |
| 前端 | Node v22.23.2 / npm 12.0.2；`npm run typecheck`、`npm run build`、`npm run smoke:client` |
| Compose 全链路 | `docker compose -p f004te1`（独立项目名/卷），入口 Nginx `127.0.0.1:18097`（非默认端口） |
| 清理 | `compose -p f004te1 down -v`、`docker rm -f f004te1-db`、`docker network rm f004te1-net`、删临时镜像；残留检查无 f004 容器/网络 |

### 实际执行的命令与输出摘要（独立执行，未复用开发者结果）

| # | 命令 | 结果 |
| --- | --- | --- |
| 1 | `docker run … pytest tests -v`（真实 PG，`csm_test`） | **119 passed, 1 skipped**（skip=`test_trusted_extension_installed_by_non_superuser`：连接角色为 superuser 的环境限制，非 F004 缺陷） |
| 2 | `pytest tests/integration/test_resources.py tests/integration/test_resource_constraints.py -q` | **41 passed**（F004 专属用例） |
| 3 | 独立库 `alembic heads` / `upgrade head` / `downgrade 0003_clusters_audit` / `upgrade head` | `0004_resources (head)` 单一 head；up 建 resources；down 后 resources 及约束/索引/触发器消失、F003 对象（users/user_sessions/clusters/audit_logs）保留；re-up 恢复 |
| 4 | 独立 raw SQL + 真双连接并发脚本（Tester 编写，`csm_verify`） | **29 / 29 PASS**（约束/部分唯一谓词/触发器/FK/默认值/归一化方向/B38 真并发） |
| 5 | `npm run typecheck` / `npm run build` / `npm run smoke:client` | typecheck 通过；build 通过（46 modules）；smoke **43 passed, 0 failed** |
| 6 | Compose 全链路 curl（Nginx 18097：登录→CSRF→创建 Cluster/Resource→归一化→重复 409→跨 Cluster→cluster 引用检查→软删释放→activity） | 状态码与错误信封符合 Contract |
| 7 | `python3 scripts/validate_project_state.py` | `PROJECT STATE VALID`（结构校验；批准/Git 证据另行核对，非本报告结论） |

### V1–V15 执行结果（TD-2 → TE-1）

| 验证项 | 结果 | 证据 / 说明 |
| --- | --- | --- |
| V1 hostname 唯一 + V13 DB 约束 | **PASS** | 用例 1/2/4；同 Cluster 精确/大小写/空白变体 → 409 `CONFLICT{unique_conflict,field:hostname}`；跨 Cluster 201；部分唯一谓词含 `deleted_at IS NULL` |
| V2 软删复用 | **PASS** | 用例 2/4；软删后重建 201、旧行保留 `deleted_at`、新行独立 id；raw 软删行不参与部分唯一 |
| V3 归一化 + 静态单一实现 | **PASS** | 用例 1/2/4；`CN001`/` cn001 ` 落库 `cn001`；`normalization.py` 与 DB `translate(btrim(...),'A–Z','a–z')` 一致；非 ASCII 原样 |
| V4 默认与显式 null | **PASS** | 用例 1/2；省略 role/status 默认 OTHER/UNKNOWN（响应与库）；显式 null → 422；PATCH 省略不重置 |
| V5 不可改字段 + V13 触发器 | **PASS** | 用例 1/2/4/6；PATCH cluster/cluster_id/resource_type/只读 → 422；raw UPDATE cluster_id/resource_type 被触发器拒；库值/version 不变 |
| V6 cluster 归属 + hostname 校验 | **PASS** | 用例 2/4/6；缺失/不存在/软删 → 422 `field:cluster`；空/内部空白/控制字符/超长 → 422；raw 直插被 CHECK 拒 |
| V7 列表契约 | **PASS**（代表性子集） | 用例 2/6；组合过滤 AND、`cluster_id`、`q`、`sort`+`order`、分页与 `total`；非法参数 422（B18/B20 为代表性而非全字段组合穷举） |
| V8 Detail Overview + V15 前端 | **PASS**（DOM 非自动化） | 用例 1/2/5/6；响应含嵌套 `cluster{id,code,name}` 与六要素；前端 build + client 机制级状态/交互核对 |
| V9 软删/恢复 + V13 | **PASS** | 用例 2/4/6；默认隐藏、include/only 越权 403、软删详情默认 404、ADMIN 200；restore `not_deleted`/`unique_conflict`/`dependency_deleted` 均 409 且不覆盖 |
| V10 Audit/Activity | **PASS** | 用例 1/2/6；四 action 各一行、白名单快照、同事务回滚不留痕；Activity 全角色 200、按对象隔离、升序 |
| V11 权限矩阵 | **PASS** | 用例 1/2；VIEWER 只读、EDITOR 增改不删/恢复、ADMIN 删/恢复/查看已删；未认证 401；服务端强制 |
| V12 基础搜索 | **PASS**（限定范围） | 用例 2/6；`?q=CN00` ILIKE 命中 `cn001`；静态确认 resources 无 pg_trgm/GIN 索引；完整模糊/全局搜索归 F013 |
| V13 数据层 | **PASS** | 用例 1/2/3/4；约束/索引/触发器/部分唯一/FK RESTRICT/`gen_random_uuid()`；迁移 up/down/up |
| V14 D01/D02 签核核对 | **PASS**（文档） | Contract v1 + DB v1 + D01 v3 §5.3 记录 D01 Resource 域与 D02；实现与 DB `translate` 小写口径一致 |
| V15 Resources 页面基线 | **PASS**（构建+机制级） | 用例 5；Loading/Success/Empty/Error 显式区分、`version` 随表单、409 不静默重试（fetch 一次）、ADMIN 已删开关门控；真实浏览器 DOM 非必要判据 |

### B1–B46 执行结果

| 编号 | 结果 | 证据摘要 |
| --- | --- | --- |
| B1 同 Cluster 精确重复 | PASS | 用例 1/2/4；409 unique_conflict，库中一行 |
| B2 大小写/空白变体重复 | PASS | 用例 2/4；`CN001`/` cn001 `/`Cn001` 均 409，`hostname_key='cn001'` |
| B3 跨 Cluster 同名 | PASS | 用例 2/4/6；均 201，key 同、cluster_id 异 |
| B4 软删后重建 | PASS | 用例 2/4；旧行保留、新行独立 id |
| B5 归一化落库一致 | PASS（TD-2 修正后） | 用例 2/4；落库小写；DB `translate(btrim(...),'A–Z','a–z')` 与 `ck_resources_hostname_key_matches` 方向一致（raw 断言） |
| B6 非 ASCII 原样（ASCII-only 折叠） | PASS | 用例 2/4；`straße`/`ﬁle`/`山河3` 建成功；`STRAßE` 与 `straße` 同 key；`STRASSE` 不同 key；无 500 |
| B7 hostname 长度边界 | PASS | 用例 2/4；253 通过、254 拒（API 422 + DB 列/CHECK） |
| B8 空/空白/内部空白/控制字符 | PASS | 用例 2/4；API 422 + raw CHECK 拒 |
| B9 短名与 FQDN | PASS | 用例 2；`cn001` 与 `cn001.example.com` 均成功且不合并 |
| B10 role/status 默认 | PASS | 用例 2/4；OTHER/UNKNOWN |
| B11 role/status 显式 null | PASS | 用例 1/2；422 VALIDATION_ERROR，库值不变 |
| B12 枚举非法 | PASS | 用例 2/4；API 422 + raw CHECK 拒 |
| B13 cluster 不可改 | PASS | 用例 1/2/4；API 422 + 触发器拒，库值/version 不变 |
| B14 resource_type 不可改 | PASS | 用例 2/4；API 422 + 触发器拒 |
| B15 只读字段拒绝 | PASS | 用例 2；id/created_at/deleted_at 等 422 |
| B16 cluster 缺失/不存在/软删 | PASS | 用例 2/4/6；统一 422 `field:cluster` |
| B17 cluster 引用形式 | PASS | 用例 2；UUID 与 code（大小写变体）解析同一 uuid；非法 422 |
| B18 组合过滤 | PASS（代表性子集） | 用例 2/6；`cluster+type+role+status` AND 交集、`cluster_id` 同义 |
| B19 分页边界 | PASS | 用例 2；缺省 1/20、1..100、0/101/非法 422、total 准确 |
| B20 排序白名单与非法 | PASS（部分字段静态核对） | 用例 2；`hostname` asc/desc 端到端；其余白名单由 `Literal`+映射保证；`sort=id`/`order=random` 422，无 500/注入 |
| B21 模糊搜索 q | PASS | 用例 2/6；ILIKE 大小写不敏感；未引入 pg_trgm/GIN（用例 1 静态） |
| B22 非法 deleted/type 查询值 | PASS | 用例 2；422 VALIDATION_ERROR |
| B23 软删默认隐藏 | PASS | 用例 2/6；默认仅未删；软删无参数详情 404 |
| B24 include/only 越权与授权 | PASS | 用例 2/6；非 ADMIN 403 permission；ADMIN include/only 200；无权限 `deleted=true` 403 |
| B25 ADMIN 恢复成功 | PASS | 用例 2；200、deleted_at=null、version+1、RESTORE audit |
| B26 恢复 not_deleted | PASS | 用例 2；409 not_deleted |
| B27 恢复 unique_conflict（自然路径） | PASS | 用例 2；软删→重建→restore 旧对象 409、旧对象保持软删 |
| B28 恢复 dependency_deleted（自然路径） | PASS | 用例 2；软删 Resource→删 Cluster→restore 409 `dependency_deleted` + `conflicts:[{object_type:cluster,object_id}]`；**自然端到端可达** |
| B29 恢复不级联 | PASS | 用例 2；仅目标恢复，其它软删对象不变 |
| B30 Audit 四 action | PASS | 用例 1/2/6；恰 CREATE/UPDATE/DELETE/RESTORE，CREATE 无 before、DELETE 无 after |
| B31 强制失败回滚不留 audit | PASS | 用例 1/2；注入非法 action，业务与 audit 同事务双回滚 |
| B32 Activity 全角色 + 隔离 + 排序 | PASS | 用例 2/6；VIEWER/EDITOR/ADMIN 200、按 `(object_type,object_id)`、升序 |
| B33 Audit 无敏感字段 | PASS | 用例 2；白名单 7 字段，无 password/token/secret |
| B34 Audit 快照可序列化 | PASS | 用例 2；JSON 可序列化，metadata 对象保留 |
| B35 乐观锁两会话并发 | PASS | 用例 1/2；两条真实连接，一方 200 version+1、另一方 409 `VERSION_CONFLICT{current_version}`，最终库值来自成功方 |
| B36 前端无静默重试覆盖 | PASS | 用例 5；client 对 409 明确呈现、fetch 仅一次 |
| B37 部分唯一索引 WHERE 谓词 | PASS | 用例 1/4；`pg_indexes` 含 `UNIQUE` + `deleted_at IS NULL`；未删重复拒、软删行不参与 |
| B38 并发同 hostname 创建 | PASS（真双连接） | 用例 4（Tester 独立）；两条独立连接并发 INSERT 仅一方成功、另一方 `uq_...` 违反；service 级并发创建败方映射 409 `unique_conflict`；最终未删行仅 1 条 |
| B39 hostname_key CHECK 一致性 | PASS | 用例 1/4；raw 不一致被拒；`pg_get_constraintdef` 含 `translate(`、不含 `lower(`；折叠方向为 `'A–Z'→'a–z'` |
| B40 cluster FK RESTRICT + 引用检查 | PASS（Resource 自身引用集为空为机制级） | 用例 1/2/4/6；raw 物理 DELETE 被 FK RESTRICT 拒（`confdeltype='r'`）；API `DELETE /clusters/{id}` 有未删 Resource → 409 `reference_exists` + references；**Resource 自身被引用集为空，Resource `reference_exists` 无自然路径，仅删除始终成功（机制级）** |
| B41 引用检查边界（无未删 Resource 可删） | PASS | 用例 2/6；Resource 全部软删后 `DELETE /clusters/{id}` 204；软删不阻止 |
| B42 metadata object CHECK + 整值替换 | PASS | 用例 1/2/4；raw `[]`/`"x"` 被拒；PATCH 整值替换；显式 null 422 |
| B43 version CHECK + 稳定 ID | PASS | 用例 2/4；raw version=0 拒；改名后 id/created_at 不变、version 递增、audit object_id 恒等 |
| B44 迁移 0004 up/down/up | PASS | 用例 1/3；各步 0、单一 head、down 后 resources 消失且 F003 对象保留、re-up 恢复 |
| B45 软删过滤覆盖关系加载 | PASS | 用例 1（`test_resource_constraints`）；软删 Cluster 经 relationship 加载为 None、`cluster_id` 保留（F003 B41 遗留回归） |
| B46 改名不改身份 | PASS | 用例 2；id/created_at 不变、version 递增 |

### 数据库 / 接口 / 前端 / 集成结果

- **数据库（真实 PG，`csm_verify` raw SQL + `csm_test` pytest）**：`resources` 列/约束/索引/触发器与 DB v1 逐项一致；部分唯一 `uq_resources_cluster_id_hostname_key`（`WHERE deleted_at IS NULL`）；`ck_resources_hostname_key_matches`/`ck_resources_hostname_ascii_lower` 经 `translate` 小写折叠（无 `lower()`）；`trg_resources_immutable_fields` 生效；`fk_resources_cluster_id_clusters` RESTRICT（`confdeltype='r'`）；`gen_random_uuid()` 默认；迁移 0004 对称可逆、单一 head。**PASS**
- **接口（ASGI + 全链路 Nginx 18097）**：7 端点响应内容、类型、nullable、业务边界、非法输入、错误语义符合 Contract；错误信封 `CONFLICT`/`VERSION_CONFLICT`/`VALIDATION_ERROR`/`FORBIDDEN`/`NOT_FOUND`/`AUTH_REQUIRED`；`hostname` 归一化（` CN001 `→`cn001`）、cluster 引用检查（409 reference_exists 含 references、软删后放行）、不可改字段 422、CSRF 跨源 403、未认证 401。只读端点无业务写副作用。**PASS**
- **前端**：typecheck/build 通过；client 机制级 43 项通过；V15 状态/交互/错误/未知值经源码核对。真实浏览器 DOM 非本 Feature 必要判据。**PASS**
- **集成（Compose 经入口 Nginx）**：`migrate`/`bootstrap` Exited(0)，`alembic_version=0004_resources`；登录→创建→归一化→重复 409→跨 Cluster→引用检查→软删释放→activity 全链路符合 Contract。**PASS**

### 验收映射 A1–A13 结论

| # | 结论 | 证据 |
| --- | --- | --- |
| A1 | **PASS** | V1/V13 |
| A2 | **PASS** | V2/V13 |
| A3 | **PASS**（导入执行归 F014） | V3/V14 |
| A4 | **PASS** | V4 |
| A5 | **PASS** | V5/V13 |
| A6 | **PASS** | V6 |
| A7 | **PASS** | V7/V15（B18/B20 为代表性） |
| A8 | **PASS**（后端 + 前端机制级） | V8/V15 |
| A9 | **PASS** | V9/V13/V15 |
| A10 | **PASS**（完整跨对象审计归 F015/F016） | V10/V15 |
| A11 | **PASS**（完整 T25 跨 Feature 回归不在本 Feature） | V11/V15 |
| A12 | **PASS**（仅基础 ILIKE；完整模糊/pg_trgm 归 F013） | V12 |
| A13 | **PASS** | V14/V13 |

### Defects

| ID | Severity | Layer | Location | 证据 / 期望与实际 | 影响 | Owner | 必须修复 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| F004-TD-1-01 | LOW（已关闭） | 文档（Test Design） | `test-report.md` TD-1 §0/B5 | TD-1 将 `hostname_key` 折叠方向写作 `translate(btrim(hostname),'abc…','ABC…')`（大写），与 DB-D36/Contract §2.1/D01 §5.3 的小写口径相反；TD-2 改为 `translate(btrim(hostname),'A–Z','a–z')`（小写方向），验收判据不变 | 仅文档笔误，无实现影响 | Tester | 是（已在 TD-2 修复） |

未发现新的实现缺陷。

### 未验证项与口径声明

- **Resource 自身引用集为空（机制级）**：F004 无对象引用 Resource（Interface/VM/Service 归 F007–F012），`DELETE /resources/{id}` 的 `reference_exists` 无自然端到端路径，仅验证“删除始终成功”；不得表述为完整 T23/T24 通过。首个反向检查器 `cluster←resources` 为自然端到端 PASS。
- **完整 T37/T38/T39/T25/T26**：F004 仅覆盖 Resource 子集（默认值/显式 null、权限矩阵、版本冲突/审计）；Interface/Network/Pool 部分与硬件单位/容量、跨 Feature 权限/审计回归归后续 Feature / 上线验收，本报告不声明完整通过。
- **B18/B20 为代表性子集**：组合过滤与排序未做全字段组合穷举；白名单其余字段由类型约束与映射保证，标注为部分字段静态核对。
- **真实浏览器 DOM 渲染**：未自动化，前端以构建 + client 机制级 + 入口真实 API 集成为准（同 F001–F003）。
- **跨功能回归（§31）与上线验收（§32）**：不在本 Feature 范围。

---

### Git 声明

```text
GIT: NONE
```

本次活动（TD-2 文档修正 + TE-1 独立测试执行）仅写入 `docs/features/F004/test-report.md`，未修改业务实现、未暂存/提交/切换分支。`feature/F004-resource-core` 工作区在本次开始前 `git status --short` 为空。