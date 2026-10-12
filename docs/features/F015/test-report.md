# F015 Audit 查询、已删除对象管理与系统功能 — Test Report

本文件同时承载 TEST_DESIGN 与 TEST（TEST 阶段在同一文件追加执行结果）。两阶段分别记录版本、结论与证据；TEST_DESIGN **不填充执行 PASS**。

---

## Test Design

- **版本**：TD-1
- **日期**：2026-10-14
- **角色**：Tester（TEST_DESIGN 模式）
- **结论**：`TEST DESIGN READY`（TD-1）
- **依据**：
  - `docs/product/requirements-v3.md` revision 3（§21、§22、§23、§25、§28、§31 T24/T25/T26/T36/T41、§35.2 Q07-A/Q10-B）
  - `docs/features/F015/product.md`（PRODUCT `READY FOR ARCHITECT`；A1–A31、I-1–I-15、O-1–O-8）
  - `docs/features/F015/architecture.md`（ARCHITECTURE `READY FOR DESIGN` 2026-10-14；DR-213–DR-227、§4 图表、§6 验证策略）
  - `docs/api/F015.md`（**草案 v0，状态 DRAFT，待 CONTRACT 定稿**）：`GET /api/v1/audit`、`GET /api/v1/deleted`、`/api/v1/users`（list/detail/create/patch）、恢复复用各域端点
  - `docs/api/F002.md` v1（§1.1 信封、§1.2 错误码、§2.1 CSRF、§3 权限矩阵）、`docs/api/F003.md` v2、`docs/api/F004.md`/`F007.md`/`F008.md`/`F009.md`/`F010.md`/`F011.md`/`F012.md`（各域 restore/activity 权威）
  - `docs/database/f002-auth.md` v1（DB-D13–D19）、`docs/database/f003-cluster.md` v2（DB-D27–D29 append-only 触发器、operator 快照、`object_type` varchar(64)）
  - `backend/app/core/permissions.py`（`AUDIT_READ`/`USER_ADMIN`/`VIEW_DELETED`/`RESTORE`/`VIEW_ACTIVITY`）、`backend/app/services/audit.py`（`AUDITABLE_FIELDS` 白名单）
  - `backend/tests/conftest.py` 与既有集成夹具（`test_database_url`/`pg_engine`/`db_session`/`committed_engine`/`auth_session_factory`/`auth_app`/`api_client`/`bootstrap_admin`/`make_user`/`login`/`role_client_factory`）
  - `docs/project/handoff.md`、`docs/project/implementation-rules.md`、`.pi/skills/data-integrity/SKILL.md`、`AGENTS.md`
- **工作区/基线**：分支 `feature/F015-audit-admin`，HEAD `321e47d`（只读核对）。
- **状态属性**：TD-1 `READY` 仅表示 A1–A31 已映射到可观察判据、边界/并发场景可执行、夹具与可验证性检查已建立；**不代表测试已运行、不填充执行 PASS、不批准实现或合并**。`docs/api/F015.md` 仍为草案 v0（DRAFT），若干参数/形态为 PROPOSED→CONTRACT，索引（DR-227）为 PROPOSED→DATABASE，F015-OPEN-1（最后一个 ACTIVE ADMIN 保护）为 OPEN。以上均**不构成 BLOCKED**：architecture 与 Contract 草案已给出可执行的端点、字段、错误、分页排序、恢复路由与验证策略默认值；相关 OPEN 逐项见 §9，待 CONTRACT/DATABASE 定稿后由 TD-2 关闭并固定执行判据。

### 版本记录

| 版本 | 日期 | 变更 |
| --- | --- | --- |
| TD-1 | 2026-10-14 | 初版：A1–A31 映射 V1–V31（补充 V32–V38、V-DB-F015-1…5、V-FE-1…4、V-ST-1…3）；边界/并发 B1–B45；数据完整性对应表；真 PG 环境与可执行性评估；索引 EXPLAIN 方案（DR-227）；F015-OPEN-1 及 OPEN 处理；§9 OPEN-1…OPEN-9。 |

> **复核基线（待 TD-2）**：`docs/api/F015.md` v1 READY、`docs/database/f015*.md`（索引/登记复核结论）、`F002.md` §1.2/§3 无新增码复核、architecture F015-OPEN-1 裁定。TD-1 的端点路径、参数名、响应字段、错误形态、恢复路由、排序/分页默认值均按 architecture §2–§4 与 Contract v0 假设；TD-2 逐项核对后方可作执行依据。

---

### 0. 数据完整性对应表（F015 范围）

方法依据 `.pi/skills/data-integrity/SKILL.md`。F015 为**只读查询 + 复用既有恢复 + 账号管理写路径**；**不新增业务实体/字段/状态**，`object_type="user"` 为既有 `audit_logs.object_type`（varchar(64) 无 CHECK）多态值登记，无 Schema 语义变更。下表聚焦 F015 消费/触及的写入入口与既有约束。

| 规则依据及版本 | 作用域/写入入口 | 数据库保证（既有，architecture §4.3） | 业务层保证 | 并发/生命周期边界 | 验证与证据 |
| --- | --- | --- | --- | --- | --- |
| §22 / f003 DB-D28 | `audit_logs` append-only | `trg_audit_logs_append_only` 触发器拒绝 UPDATE/DELETE | 无修改/删除/清空端点或 UI | 查询只读；任何写入路径均无 UPDATE/DELETE | V8、V-DB-F015-1、B9/B10/B11 |
| §22 / f003 DB-D27 | `audit_logs.operator_*` | `operator_user_id` FK RESTRICT（可空）+ `operator_username` 快照 | 停用/角色变更不改写既有审计 | 账号停用后旧审计仍可解析 | V11、V-DB-F015-2、B27/B28 |
| §21/§22 | 资源恢复（复用各域） | 各域既有唯一/排他/FK/CHECK | 复用各域 restore（I-15 不复制语义） | 失败整体回滚、不级联、不覆盖 | V14–V19、B15–B26 |
| §22 | 恢复 RESTORE Audit | 同 `db_session`/事务 | 恢复成功写 Audit；失败回滚零残留 | 原子性（I-5） | V18、B24/B25 |
| §21/§23 / f002 DB-D16 | `users` | 无 `deleted_at`；`uq_users_username`；`version` 乐观锁；`status` CHECK | 停用代替删除；停用同事务删 `user_sessions` | 重复 username 409；PATCH 版本冲突 | V20–V26、V32–V35、B29–B38 |
| §22/§23 | 账号事件 Audit | 无对象 FK 多态（多态值 `user`） | `object_type="user"` + 白名单 `{username,role,status}` 不含密码；同事务 | 同 Session 同事务；失败无残留 | V10、V24、B33/B34 |
| §23 | 权限 | 无 | `require_permission`（`AUDIT_READ`/`USER_ADMIN`/`VIEW_DELETED`/`RESTORE`）；401 先于 403 | 前端隐藏不替代服务端 | V1/V26/V29、B1–B6 |
| §4 | 稳定 ID | PK UUID | 查询/恢复目标用 UUID，不用 name/code 拼接 | 改名/复用不影响定位 | V13/V14、B4 |

---

## 1. 验收映射（product.md A1–A31 → 验证项）

执行环境代号：`真PG集成` = ASGI 应用 + 真实 PostgreSQL（非 SQLite）；`真PG约束` = 真实 PG raw SQL / `pg_indexes` / 目录 / 触发器断言；`真PG并发` = `committed_engine` 真实两连接并发 + 最终持久化断言；`前端` = 构建 + 真实 API 集成（非 Mock）；`静态` = 路由清单 / 源码检查。

> **分界声明（关键）**：
> - **F015 独立可验证**：A1–A31 全部（Audit 查询/过滤/分页/只读、留存与不可变更、已删聚合与恢复复用一致性、用户账号管理、System 页、权限矩阵、不改既有语义）；§31 **T24**（恢复只恢复当前对象/不级联）、**T25**（权限矩阵）、**T26**（Audit 保留与脱敏）、**T36**（无修改/删除/清空）、**T41**（名称复用与恢复冲突）在本 Feature 闭合。
> - **F015 消费 F003–F012 已 DONE 口径**：各域删除/恢复/唯一性/依赖/Activity/Audit 写入为既有实现；F015 只验证「复用同一语义 + 新增统一入口只读聚合/权限/不改写既有行为」，**不重验各域单一恢复/删除的完整用例**（归各 Feature TE）。V19 仅作回归核对。
> - **完整跨功能 §31/§32 集成验收（F016）**：F015 只承载 Audit 查询/已删入口/账号管理；**不得以 F015 局部 PASS 拼接整体通过**。Audit 备份（§22/F016）不在本 Feature 执行。
> - **database**：无新表/新列/新约束/新触发器；`ix_audit_logs_operator_username`（DR-227）为 PROPOSED 索引，Database 可降级 `NOT_REQUIRED`；若采纳仅新增 btree 索引，不改 `audit_logs` 结构。

| 验收（product.md） | 验证项 | 测试类型 | 前置数据 | 可观察判据（PASS / FAIL） |
| --- | --- | --- | --- | --- |
| A1 `GET /audit` 仅 ADMIN；VIEWER/EDITOR 403 `FORBIDDEN{reason:"permission"}`；未认证 401 `AUTH_REQUIRED`，401 先于 403 | **V1** | 真PG集成 | 无 Cookie、VIEWER、EDITOR、ADMIN 四类客户端；库内存在审计行 | PASS：ADMIN 200；VIEWER/EDITOR 403 `FORBIDDEN{reason:"permission"}`；无 Cookie 401 `AUTH_REQUIRED` 且**先于**权限判定（无 Cookie 对任意角色路径均 401）。FAIL：任一角色越权、401/403 顺序错 |
| A2 Audit 每条含 `operator_user_id`+`operator_username`、`action`、`object_type`、`object_id`、`before_data`、`after_data`、`created_at` | **V2** | 真PG集成 | 由既有域操作产生 CREATE/UPDATE/DELETE/RESTORE 审计行（含 operator 已停用场景） | PASS：响应每条字段齐全、类型正确（UUID/null/object|null/ISO-8601 UTC）；`operator_user_id` 可空、`operator_username` 快照存在。FAIL：缺字段、operator 解析失败 |
| A3 按 `operator`/`object_type`/`object_id`/`action`/`created_from`/`created_to` 过滤，AND 组合；非法 422 | **V3** | 真PG集成 | 多操作者、多类型、多 action、跨时间点审计数据 | PASS：单条件与组合（如 `object_type`+`object_id`、`action`+时间区间）返回交集，与预期集合逐条一致；`object_id` 单独（缺 `object_type`）422；非法枚举/UUID/时间 422 `VALIDATION_ERROR{fields}`；`from>to` 422。FAIL：OR 语义、缺同现校验、非法值放行 |
| A4 分页 `page`/`page_size`（1..100）越界/非法 422；空结果 200 `{items:[],total:0}` | **V4** | 真PG集成 | 审计行数 > `page_size`；另构造零匹配过滤 | PASS：`total` 为过滤后总数、跨页无重复无遗漏；`page_size` 0/101/负数/非整数 422；空过滤 200 `items:[]`、`total:0`、分页字段齐。FAIL：越界放行、空结果 404/500、total 错 |
| A5 Audit 查询只读：不改对象、不写新 Audit、幂等 | **V5** | 真PG集成 + 真PG约束 | 调用前后统计 `audit_logs` 及业务表行数与各对象 `version`/`updated_at` | PASS：行数与内容不变、无新增 `audit_logs`；连续两次相同请求响应深比较一致。FAIL：写 Audit、返回漂移 |
| A6 资源 Activity（各域 `.../activity`）对 VIEWER/EDITOR/ADMIN 均 200，仅由 `VIEW_ACTIVITY` 控制，F015 未改变可见性 | **V6** | 真PG集成 | 三角色客户端；任一已存在对象（含已软删对象按各域契约） | PASS：三角色均 200；未认证 401；响应含该对象变更记录。FAIL：F015 收窄 Activity 角色、依赖新增权限 |
| A7 已有 Audit 行不因查询、删除/恢复、名称复用、账号停用而变化 | **V7** | 真PG集成 + 真PG约束 | 对审计行做快照 → 执行查询/删除/恢复/名称复用/账号停用 → 再快照 | PASS：目标审计行的 `before_data`/`after_data`/`created_at`/`operator_*` 逐字节不变（新操作仅追加新行）。FAIL：改写既有行 |
| A8 无任何修改/删除/批量清空 Audit 的 API 或前端入口（含 ADMIN）；候选路径/方法 404/405 | **V8**；**V-ST-1** | 真PG集成 + 静态 + 前端 | ADMIN 会话；尝试 `PUT/PATCH/DELETE /api/v1/audit*`、`DELETE /api/v1/audit`、假想 `clear` 路径 | PASS：全部 404/405，无任何成功；路由清单无修改/删除/清空端点；前端无对应控件。FAIL：存在任一可变更入口 |
| A9 Audit 不自动过期：无 TTL/清理任务；旧行长时间跨度后仍返回 | **V9**；**V-ST-2** | 真PG集成 + 静态 | 构造 `created_at` 早于远期的审计行；检查调度/任务配置 | PASS：旧行仍可被 `GET /audit` 与 Activity 返回；无 TTL 列/清理任务/归档作业。FAIL：存在过期/清理机制 |
| A10 Audit 不记录/不回显密码/令牌；用户审计仅白名单字段 | **V10** | 真PG集成 + 真PG约束 | 创建用户、角色变更、停用/启用后直接查询 `audit_logs.before_data/after_data` 与 `GET /audit` | PASS：用户事件快照仅 `{username,role,status}`；全局无 `password`/`password_hash`/token/secret 键；响应亦不含。FAIL：快照含敏感键 |
| A11 账号停用/启用不改写既有 Audit；停用后历史审计仍展示原 `operator_username` 且 `operator_user_id` 可解析 | **V11** | 真PG集成 + 真PG约束 | user A 执行操作产生审计 → 停用 A → 查询该审计；核对 `operator_user_id` | PASS：既有行不变；`operator_username` 为停用前快照；`operator_user_id` 仍指向 A（FK RESTRICT 未删）。FAIL：快照被清空、行被改写、用户被物理删除 |
| A12 ADMIN 统一入口可查看 8 类已删对象；默认查询隐藏已删，仅 `deleted=only\|include`（ADMIN）下出现 | **V12** | 真PG集成 | 8 类各构造 1 条已软删 + 1 条未删；`GET /deleted` 及各域默认列表 | PASS：`GET /deleted` 返回恰好 8 条已删（`deleted_at IS NOT NULL`）；默认域列表隐藏已删；`deleted=only/include` 仅 ADMIN 且含已删。FAIL：漏类、默认暴露已删、非 ADMIN 可见 |
| A13 统一已删列表支持过滤（至少 `object_type`）与分页；返回稳定 ID 与可跳转标识 | **V13** | 真PG集成 | 多类多条目已删对象 | PASS：`object_type` 过滤命中对应类；分页一致；每条含 `object_type`/`object_id`(UUID)/`version`/`label`/`cluster`/`deleted_at`；label 映射符合 architecture §4.2。FAIL：无稳定 ID、label 错、分页错 |
| A14 ADMIN 可从统一入口恢复任一对象；恢复后默认查询可见（`deleted_at=null`）并写 RESTORE Audit | **V14** | 真PG集成 | 8 类各 1 条已删；逐类调用对应 restore（`?version=`） | PASS：恢复 200；默认查询可见；新增 1 条对应 `object_type`/`RESTORE` Audit，operator 正确。FAIL：恢复后仍隐藏、无 Audit |
| A15 恢复只恢复当前对象、不级联：Service↛Endpoint、Interface↛Resource、Network↛IPPool/IPAddress、Resource↛Interface | **V15**；**V-ST-3** | 真PG集成 + 静态 | 分别构造含子/父级联关系的已删对象组合 | PASS：仅目标对象 `deleted_at` 置空；父/子/关联对象保持已删。FAIL：任一关联对象被连带恢复；源码无级联恢复路径 |
| A16 标识被重用或依赖仍删除时恢复失败：`409 CONFLICT{reason:"unique_conflict"}` / `{reason:"dependency_deleted"}`；新对象不被覆盖，原对象仍已删 | **V16** | 真PG集成 + 真PG约束 | Network/Pool/Service/Interface 名称或 Resource hostname 被新对象复用；或依赖仍软删 | PASS：对应 reason 409；新对象字段/`version`/`updated_at` 不变；原对象仍 `deleted_at` 非空。FAIL：覆盖新对象、误恢复原对象、reason 错 |
| A17 **T41 恢复侧**：Network/Pool/Service 名称删除后被新对象复用 → 旧对象恢复失败且新对象不变；Cluster code 不重用，无同类冲突路径 | **V17** | 真PG集成 | Network/Pool/Service 新建占用旧名；Cluster 尝试复用已删 code | PASS：旧对象 restore 409 `unique_conflict`、新对象不变；Cluster code 复用被拒（创建 409/不产生第二对象），恢复无 name 冲突路径。FAIL：复用成功、旧对象恢复成功 |
| A18 恢复后写 RESTORE Audit，同事务；恢复失败/回滚不留 Audit 残留 | **V18** | 真PG集成 + 真PG约束 | 成功恢复一次；构造失败恢复（冲突/依赖/版本） | PASS：成功：目标对象写入与 RESTORE Audit 同时可见（同事务）；失败：对象未恢复、无新增 RESTORE Audit。FAIL：Audit 先于/独立于对象写入、失败留残留 |
| A19 每类对象恢复规则沿用其自身 Feature；F015 不新增/不改变；统一入口仅按 `object_type` 路由既有恢复 | **V19** | 真PG集成 + 静态 | 逐类 restore 端点与各域契约对照；检查无 F015 独立恢复语义实现 | PASS：行为与各域契约一致（唯一性/依赖/归属/地址边界/监听唯一）；路由表与 architecture §5 一致；F015 无复制规则。FAIL：F015 覆盖/改写某域恢复语义 |
| A20 ADMIN 可创建账号（`username`/初始凭据/`role`）；创建后可登录并按角色获得 `permissions` | **V20**；**V34/V35** | 真PG集成 | ADMIN 会话；唯一 username | PASS：`POST /users` 201 `{user:UserRow}`（无 `password_hash`）；新账号可 `POST /auth/login` 200，`permissions` 与角色匹配。FAIL：创建不可登录、角色错、hash 回显 |
| A21 ADMIN 可分配/变更角色；变更后新会话/后续请求按新角色鉴权 | **V21** | 真PG集成 | 已存在账号；PATCH `role` | PASS：200 且 `role` 更新、`version+1`；新登录会话按新角色判定（如降为 VIEWER 后写端点 403）。FAIL：旧角色残留、需重登才生效 |
| A22 ADMIN 停用账号；停用后登录 401 `AUTH_INVALID_CREDENTIALS`（与未知用户/错误密码一致，不泄露存在性），现有会话失效 401 `AUTH_REQUIRED` | **V22** | 真PG集成 + 真PG约束 | 目标账号已有活跃会话；ADMIN PATCH `status=DISABLED` | PASS：目标账号后续登录 401 `AUTH_INVALID_CREDENTIALS`（响应与未知用户/错误密码不可区分）；其既有 Cookie 请求 401 `AUTH_REQUIRED`；`user_sessions` 中该 `user_id` 行被同事务删除。FAIL：停用仍可登录、旧会话仍可用、响应泄露存在性 |
| A23 ADMIN 启用已停用账号；启用后恢复登录能力 | **V23** | 真PG集成 | 已停用账号；PATCH `status=ACTIVE` | PASS：200；账号可重新登录并按其角色鉴权。FAIL：启用无效 |
| A24 创建/角色变更/停用/启用均写 Audit（同事务）；停用/启用记 `UPDATE`，含 before/after | **V24** | 真PG集成 + 真PG约束 | 依次执行 create/role-change/disable/enable | PASS：4 次操作各写 1 条 `object_type="user"` Audit（create=CREATE，其余=UPDATE）；`before_data`/`after_data` 含 `{username,role,status}` 且变化正确；失败操作无 Audit 残留。FAIL：缺 Audit、action 错、无 before/after |
| A25 不开放自行注册：无 `POST /auth/register|/signup` 或匿名建号端点；未定义路径 404 | **V25** | 真PG集成 + 静态 | 无 Cookie 尝试 `register`/`signup` 及假想匿名建号路径 | PASS：全部 404（不产生用户）；路由清单无注册端点；F002 §5 无注册声明一致。FAIL：存在匿名建号路径 |
| A26 账号管理仅 ADMIN（`USER_ADMIN`）：VIEWER/EDITOR 403，未认证 401；服务端强制 | **V26** | 真PG集成 + 前端 | 无 Cookie、VIEWER、EDITOR、ADMIN 调用 `/users` list/detail/create/patch | PASS：未认证 401（先于权限）；VIEWER/EDITOR 403 `FORBIDDEN{permission}`；ADMIN 允许；前端隐藏不替代（直连仍拦）。FAIL：任一越权 |
| A27 System 页面存在，承载账号管理（创建/角色/停用/启用）与完整 Audit 查询入口；ADMIN 可访问，非 ADMIN 不显示且后端拒绝 | **V27**；**V-FE-1/V-FE-4** | 前端 + 真PG集成 | 三角色登录前端；访问 System 页 | PASS：ADMIN 可见并可操作账号管理、入口跳转 Audit 页与已删管理区；非 ADMIN 导航/页面不显示，且直接请求后端被 403。FAIL：仅前端隐藏而后端放行、页面对非 ADMIN 可见 |
| A28 System 页面列表至少分页、排序、过滤；前端隐藏不替代服务端鉴权 | **V28**；**V-FE-2** | 前端 + 真PG集成 | 多账号/多已删对象 | PASS：用户列表与已删列表支持分页/排序/过滤，消费真实 API；Loading/Success/Empty/Error/未知态正确，错误不伪装为空列表。FAIL：仅前端过滤、无分页、错误态缺失 |
| A29 权限矩阵服务端执行：Audit/用户管理/查看已删/恢复=仅 ADMIN；Activity=全角色；可复现 | **V29** | 真PG集成 + 静态 | 三角色 × 全部 F015 端点矩阵 | PASS：逐格与服务端 `ROLE_PERMISSIONS` 一致（见 §1.1 矩阵），可重复执行结果一致。FAIL：任一格偏差、前端可绕过 |
| A30 前端不提供修改/删除/清空 Audit 入口；即使构造请求也无对应端点 | **V30**；**V-FE-3** | 前端 + 真PG集成 + 静态 | 审查 Audit 页 UI；构造修改/删除请求 | PASS：UI 无修改/删除/清空控件；构造请求 404/405。FAIL：存在入口 |
| A31 本 Feature 不改变已 DONE Feature 的行为语义（各域删除/恢复/Activity/唯一性） | **V31** | 真PG集成（回归） | 复用 F003–F014 既有测试子集 + F015 改动点回归 | PASS：既有用例全绿，各域删除/恢复/唯一性/Activity 行为与既有契约一致。FAIL：任一回归 |

**补充验证项（契约/权限/账号一致性，不直接对应单一 A）**

| 编号 | 项目 | 测试类型 | 判据 |
| --- | --- | --- | --- |
| **V32** | Audit 参数形态：`operator` trim+小写归一精确匹配；`object_type` ∈ 8 类+`user`；`sort` 仅 `created_at`、`order` asc/desc，默认 `created_at desc`；同刻 `id` 恒升序 | 真PG集成 | 归一化/枚举/排序断言；`sort` 非 `created_at` 422；同 `created_at` 行按 `id` 升序稳定 |
| **V33** | 已删参数形态：`object_type` ∈ 8 类（不含 `user`）；`sort` 仅 `deleted_at`；同刻 `object_type` 升序、`object_id` 升序；`version` ≥ 1 供 restore | 真PG集成 | 非法枚举 422；排序稳定；version 可直接用于对应 restore |
| **V34** | 用户列表/详情：`role`/`status`/`q` 过滤、`sort`∈{username,role,status,created_at,updated_at}、分页；`GET /users/{id}` 非 UUID→404、不存在→404；响应永不含 `password_hash` | 真PG集成 | 过滤/排序/分页正确；404 语义；无敏感字段 |
| **V35** | 账号创建校验：username 归一 `^[a-z0-9._-]{3,64}$` 否则 422；password 非空（长度 PROPOSED 8–128）否则 422；重复 username → 409 `CONFLICT{reason:"unique_conflict",field:"username"}`；argon2 存 hash | 真PG集成 + 真PG约束 | 正则/长度边界；重复 409；DB 唯一约束兜底；库中为 argon2 hash |
| **V36** | PATCH 乐观锁与字段：`version` 必填；`role`/`status` 至少一个（都缺 422）；未知/只读字段 422；`username`/`password_hash` 不可出现；陈旧 version → 409 `VERSION_CONFLICT{current_version}` | 真PG集成 | 校验顺序 401→403→422→404→409；陈旧版本不静默覆盖 |
| **V37** | 账号管理排除端点：无 `DELETE /users/{id}`、无改密/重置/首登强制改密；未定义路径/方法 404/405 | 真PG集成 + 静态 | 全部不可达；用户无物理删除路径 |
| **V38** | 只读端点无写副作用：`GET /audit`、`GET /deleted`、`GET /users*` 不写 Audit、不改对象、幂等 | 真PG集成 + 真PG约束 | 调用前后行数/内容不变、连续两次一致 |
| **V-DB-F015-1** | `trg_audit_logs_append_only` 存在且 `UPDATE`/`DELETE` `audit_logs` 被触发器拒绝 | 真PG约束 | `pg_trigger` 断言；raw SQL UPDATE/DELETE 抛异常 |
| **V-DB-F015-2** | `audit_logs.operator_user_id` FK `ON DELETE RESTRICT`；持审计用户不可物理删除 | 真PG约束 | 尝试删除有审计的 user 被 FK 拒绝 |
| **V-DB-F015-3** | `audit_logs.object_type` 为 varchar(64) 无枚举 CHECK → `object_type="user"` 可写入，无 Schema 变更 | 真PG约束 | 列类型/约束断言；插入 `user` 成功 |
| **V-DB-F015-4** | `ix_audit_logs_operator_username`（若 Database 采纳 DR-227）存在且 `EXPLAIN` 按 operator 过滤命中该索引 | 真PG约束 | 见 §6；未采纳则记 `NOT_REQUIRED` |
| **V-DB-F015-5** | 运行期不新增/删除 DB 对象（除本次已有迁移）；`alembic upgrade head` 后 `audit_logs`/`users` 结构符合既有设计 | 真PG约束 | `pg_class`/`pg_index` 前后一致；迁移 head 可达 |
| **V-FE-1** | System/Audit 页面权限门控与导航：非 ADMIN 不显示且后端拒绝；ADMIN 可见 | 前端 + 真PG集成 | 真实 API 集成，非 Mock |
| **V-FE-2** | 列表四态（Loading/Success/Empty/Error/未知）与分页/排序/过滤控件；错误不伪装为空列表 | 前端 | 消费真实端点 |
| **V-FE-3** | Audit 页无修改/删除/清空控件；已删管理区恢复按 `object_type` 调对应域 restore，失败 reason 明确呈现 | 前端 + 真PG集成 | 无 Audit 变更入口；409 reason 可见 |
| **V-FE-4** | 账号管理表单：创建（username/password/role）、角色变更、停用/启用；版本冲突提示；前端隐藏不替代后端 | 前端 + 真PG集成 | 真实 API 集成 |
| **V-ST-1** | 路由清单无 Audit 变更端点；无 Audit 修改/删除/清空 handler | 静态 | 源码/路由检查 |
| **V-ST-2** | 无 TTL/清理/归档任务或配置（如无 `audit_retention`/调度作业） | 静态 | 配置/任务源码检查 |
| **V-ST-3** | F015 恢复路径复用各域既有 restore，无独立级联/覆盖逻辑 | 静态 | 源码检查按 object_type 路由 |

> 说明：V34–V38 覆盖 A20–A26 未完全展开的账号字段/乐观锁/排除端点/只读无副作用；V-DB-F015-* 为真实 PG 约束证据；V-FE-* 为前端真实集成；V-ST-* 为静态核对。

---

## 2. 边界与并发场景（B 编号，TEST 阶段执行）

| # | 场景 | 输入/前置 | 预期 |
| --- | --- | --- | --- |
| B1 | 未认证先于权限 | 无 Cookie 调用 `/audit`、`/deleted`、`/users*`、restore | 401 `AUTH_REQUIRED`，绝不 403（I-11/A1） |
| B2 | 三角色矩阵 | VIEWER/EDITOR/ADMIN × 四类端点 | 仅 ADMIN 允许；VIEWER/EDITOR 403 `FORBIDDEN{reason:"permission"}`（A26/A29） |
| B3 | CSRF 与权限区分 | 跨源写请求 vs 缺权限 | `FORBIDDEN{reason:"csrf"}` vs `{reason:"permission"}`（F002 §2.1） |
| B4 | Audit 过滤 AND | `object_type`+`object_id`+`action`+时间区间组合 | 交集结果；缺 `object_type` 的单独 `object_id` 422（A3/V32） |
| B5 | 时间闭区间边界 | `created_from==created_to==某行 created_at`；`from>to` | 闭区间含端点；`from>to` 422（A3） |
| B6 | 分页边界 | `page_size`=1/100/0/101/负/非整数；`page` 越界 | 1/100 允许；0/101/负/非整数 422（A4/I-13） |
| B7 | 排序稳定 | 多行同 `created_at`；多行同 `deleted_at` | Audit 同刻 `id` 升序；已删同刻 `object_type`→`object_id` 升序（V32/V33） |
| B8 | 空结果 | 零匹配过滤 | 200 `{items:[],page,page_size,total:0}`（A4） |
| B9 | 只读幂等 | 连续相同查询 | 响应深比较一致；无写入（A5/V38） |
| B10 | append-only DB 兜底 | raw SQL `UPDATE audit_logs`/`DELETE FROM audit_logs` | 触发器拒绝异常（I-1/V-DB-F015-1） |
| B11 | 无变更端点 | `PUT/PATCH/DELETE /audit*`、假想 clear | 404/405（A8/A30） |
| B12 | 已删 8 类聚合 | 8 类各 1 条已删 + 未删 | `GET /deleted` 恰返回 8 条；默认列表隐藏已删（A12） |
| B13 | `deleted=only/include` 权限 | ADMIN 与非 ADMIN；`deleted` 非法值 | ADMIN 可见；非 ADMIN 403 或不可见已删；非法值 422（A12/I-8） |
| B14 | label/cluster 映射 | 各类已删对象含绑定 cluster / 未绑定 endpoint | 按 architecture §4.2：cluster=code、resource=hostname、interface/network/ip_pool/service=name、ip_address=address、service_endpoint=`{protocol}:{port}`；未绑定 endpoint cluster=null（A13） |
| B15 | 恢复不级联（Service/Endpoint） | 已删 Service + 已删 Endpoint | 恢复 Service 后 Endpoint 仍已删（A15） |
| B16 | 恢复不级联（Network 子项） | 已删 Network + 已删 IPPool/IPAddress | 恢复 Network 后 Pool/Address 仍已删（A15） |
| B17 | 恢复不级联（Resource/Interface） | 已删 Resource + 已删 Interface | 恢复 Resource 后 Interface 仍已删；恢复 Interface 不恢复 Resource（A15） |
| B18 | 唯一重名恢复失败 | Network/Pool/Service/Interface 名称或 Resource hostname 被新对象占用 | 409 `CONFLICT{reason:"unique_conflict"}`；新对象不变；原对象仍已删（A16/A17/T41） |
| B19 | 依赖仍删恢复失败 | 依赖对象仍软删（如 Pool 依赖 Network、Interface 依赖 Resource） | 409 `CONFLICT{reason:"dependency_deleted"}`；不覆盖（A16） |
| B20 | Cluster code 不重用 | 软删 Cluster 后尝试新建同 code | 创建被拒（409/业务规则），无第二对象；无恢复 name 冲突路径（A17） |
| B21 | 恢复版本冲突 | 传入陈旧 `version` | 既有各域 `VERSION_CONFLICT`（A19/V19） |
| B22 | 恢复成功可见性 | 逐类 restore 成功 | 默认查询可见、`deleted_at=null`（A14） |
| B23 | 恢复 RESTORE Audit | 成功恢复一次 | 同事务新增对应 `object_type`/`RESTORE` Audit（A18） |
| B24 | 恢复失败无 Audit 残留 | 冲突/依赖/版本失败 | 无 RESTORE Audit 新增，对象未恢复（A18/I-5） |
| B25 | 恢复并发 | 两真实连接同时对同一已删对象 restore（同 version 或异 version） | 仅一个成功；失败方不覆盖、不重复写 Audit、最终状态一致（I-5/I-6） |
| B26 | 名称复用后再恢复回退 | 删除 Network → 新建同名 → 恢复旧 | 旧恢复 409，新对象字段/`version`/`updated_at` 不变（A16/A17/T41） |
| B27 | 停用不改旧审计 | user A 产生审计 → 停用 A → 查询 | 旧审计行不变、`operator_username` 快照在（A11/I-4） |
| B28 | 停用后审计可解析 | 停用 A → `GET /audit?operator=a` | 命中 A 的历史审计；`operator_user_id` 仍指向 A（A11/V-DB-F015-2） |
| B29 | 创建账号成功 | ADMIN 新建唯一 username/role/password | 201 UserRow、可登录、按角色 `permissions`（A20/V20） |
| B30 | username 归一/正则边界 | 大写、首尾空白、长度 2/3/64/65、非法字符 | 归一+小写；3–64 与合法字符通过，余 422（V35） |
| B31 | 重复 username | 已存在用户名再创建 | 409 `CONFLICT{reason:"unique_conflict",field:"username"}`；DB 唯一兜底（V35/V-DB-F015-3 相邻） |
| B32 | password 边界与脱敏 | 空/超短/超长（PROPOSED 8–128）；创建成功后查库与响应、Audit | 越界 422；库中 argon2 hash；响应与 Audit 无密码（V10/V35/A10） |
| B33 | 账号事件 Audit 同事务 | create/role-change/disable/enable | 各 1 条 `user` Audit；action/before/after 正确；失败无残留（A24） |
| B34 | 角色变更即时生效 | ADMIN 将账号降级 VIEWER | 新会话/后续请求按新角色（写端点 403）；无需重登（A21） |
| B35 | 停用即时失效会话 | 账号有活跃会话 → 停用 | `user_sessions` 该 user 行被删；旧 Cookie 401 `AUTH_REQUIRED`（A22/I-9） |
| B36 | 停用后登录语义一致 | 停用账号登录 vs 未知用户/错误密码 | 均 401 `AUTH_INVALID_CREDENTIALS`，响应不可区分（不泄露存在性）（A22） |
| B37 | 启用恢复 | 已停用账号 → PATCH ACTIVE | 可重新登录；无需重建凭据（A23） |
| B38 | PATCH 乐观锁与字段校验 | 陈旧 version；`role`+`status` 都缺；未知/只读字段；`username`/`password_hash` | 顺序 401→403→422→404→409；陈旧 409 `VERSION_CONFLICT{current_version}`（V36） |
| B39 | 无注册/无物理删除 | 匿名 `register`/`signup`；`DELETE /users/{id}` | 404/405；用户无物理删除路径；FK RESTRICT 兜底（A25/V37） |
| B40 | 非 UUID 路径 | `GET /users/not-a-uuid` | 404 `NOT_FOUND`（V34） |
| B41 | 权限矩阵可复现 | 重复执行三角色矩阵 | 结果稳定一致（A29） |
| B42 | 只读无副作用 | `GET /deleted`/`/users*` 前后快照 | 无写入、幂等（V38） |
| B43 | `ix_audit_logs_operator_username`（若采纳） | 大量审计行 + `operator` 过滤 | `EXPLAIN` 命中索引（V-DB-F015-4） |
| B44 | Migration up/down/up（若采纳索引迁移） | `alembic upgrade head`/`downgrade`/`upgrade` | 索引随迁移增删、数据保留（V-DB-F015-5） |
| B45 | 前端权限门控 | 三角色前端 + 直连 API | 前端隐藏且后端拒绝；409 reason 明确呈现（V-FE-1/V-FE-3） |

并发说明：F015 的并发风险集中在**恢复**（I-5/I-6 原子性与不覆盖）与**账号 PATCH 乐观锁**。证据必须经真实 PostgreSQL（`committed_engine` + 两独立连接 + 最终持久化断言），SQLite/Mock 不构成证据。Audit/已删/用户查询为只读，不加锁，正确性由查询语义与既有约束保证。

---

## 3. 夹具 / 环境设计

**复用 `backend/tests/conftest.py`（不改其护栏语义）**：
- `test_database_url`：独立测试库 + DB-D10 安全护栏（库名含 `test`、`TEST_DATABASE_URL != DATABASE_URL`）；未设置则 skip。
- `pg_engine`：会话级重建 `public` schema + `alembic upgrade head`（F001–F014 全部迁移；F015 若无索引迁移则无新迁移）；会话结束清理。
- `db_session`：函数级外层事务 + savepoint，回滚不跨用例污染。
- `committed_engine`：真实提交用例（恢复成功/回滚/并发/账号停用会话失效证据），teardown TRUNCATE；**新开连接断言最终持久化**。
- `auth_session_factory`/`auth_app`/`api_client`/`bootstrap_admin`/`make_user`/`login`：提供 ADMIN/EDITOR/VIEWER/未认证客户端与真实 argon2 用户；`role_client_factory` 提供三角色已登录客户端。既有各域 helper（cluster/resource/interface/network/pool/address/service/endpoint 创建 + 软删）直接复用构造已删对象。

**F015 新增测试侧夹具/断言（Tester 落地于测试侧）**：
- `audit_factory(session, *, object_type, object_id, action, operator, before, after, created_at)`：直接写入/构造已知审计行（用于过滤/排序/时间边界/operator 匹配），或经既有域 API 产生真实审计。
- `call_audit(client, **params)` / `call_deleted(client, **params)` / `call_users(client, method, **kwargs)`：封装查询/写端点并断言状态码与信封。
- `assert_audit_row(resp_item, expected)`：字段齐全/类型/operator 快照断言（A2/V2）。
- `audit_snapshot(session)` / `business_snapshot(session)`：`audit_logs` 与相关业务表行数+关键列快照，用于只读/零残留断言（A5/A7/V18/V38）。
- `soft_deleted_pair(client, object_type)`：构造「已删对象 + 可选同名新对象 / 仍软删依赖」，供 B15–B20/B26。
- `session_cookie(client, user)` 与 `assert_session_gone(session, user_id)`：验证停用删会话与旧 Cookie 401（A22）。
- `two_connection_restore(committed_engine, ...)`：两真实连接并发恢复（B25）。
- `route_list(app)`：枚举注册路由用于无变更/无注册/无删除端点断言（V-ST-1/V8/V25/V37）。
- `explain(session, sql)`：`EXPLAIN (FORMAT JSON)` 断言索引命中（V-DB-F015-4）。

**环境**：Docker / Compose 可用（F001–F014 TE 已证）；真实 PG 经 Compose `db`（`postgres:16`）。F015 无业务 Schema 变更；索引随 Database Gate 结论决定是否新增迁移。

### 3.1 当前环境可执行性评估

| 验证项 | 环境要求 | 当前评估 | 降级/替代 |
| --- | --- | --- | --- |
| V1–V31、B1–B45、V-FE-* | 真实 PG + 后端/前端；**依赖 `/audit`、`/deleted`、`/users` 实现落地** | Compose `db` 可满足；实现未落地→BLOCKED | **不得**用 SQLite/Mock 替代约束/并发证据 |
| V-DB-F015-1/2/3/5 | 真实 PG（既有触发器/FK/varchar/迁移） | 环境可执行；依赖声明存在 | 无 PG→BLOCKED |
| V-DB-F015-4（索引 EXPLAIN，若采纳 DR-227） | 真实 PG + 索引迁移 | 待 Database 裁定；未采纳记 `NOT_REQUIRED` | 无 PG/未采纳→不可执行，标 NOT_REQUIRED |
| V-FE-1…V-FE-4 | Node + 构建 + 真实 API | 可执行 | 真实浏览器 DOM 非必要；镜像/端口问题记 BLOCKED |
| §31/§32 完整跨功能回归、Audit 备份 | F016 交付 | **不可执行** | 标 `NOT TESTED / 归 F016` |

---

## 4. 可验证性检查

| 项 | 判定 | 说明 |
| --- | --- | --- |
| A1/A26/A29 权限与 401 先于 403 | **可验证（API + 静态）** | V1/V26/V29、B1–B3/B41；四类客户端矩阵 |
| A2/A3/A4 Audit 字段/过滤/分页 | **可验证（API + DB）** | V2/V3/V4/V32；raw 查询比对集合 |
| A5/A7/A38 只读幂等与不可变 | **可验证（API + DB）** | V5/V7/V38、B9/B42；快照深比较 |
| A8/A30 无变更端点 | **可验证（API + 静态 + 前端）** | V8/V30/V-ST-1、B11 |
| A9 无 TTL/清理 | **可验证（静态 + API）** | V9/V-ST-2 |
| A10/I-2 脱敏白名单 | **可验证（API + DB）** | V10、B32；raw 检查 JSONB 键集 |
| A11/I-4 历史身份保留 | **可验证（API + DB）** | V11/V-DB-F015-2、B27/B28 |
| A12/A13 已删聚合/过滤/label | **可验证（API）** | V12/V13/V33、B12–B14；对照 architecture §4.2 |
| A14/A18 恢复可见性与 Audit | **可验证（API + DB）** | V14/V18、B22/B23 |
| A15/A19 不级联/不改语义 | **可验证（API + DB + 静态）** | V15/V19/V-ST-3、B15–B17 |
| A16/A17/I-6 不覆盖/409 reason（T41） | **可验证（API + DB）** | V16/V17/V33、B18–B20/B26 |
| I-5 恢复原子性/失败零残留 | **可验证（真 PG + 真实提交）** | V18、B24/B25；`committed_engine` |
| A20–A26 账号管理（创建/角色/停用/启用/无注册/脱敏） | **可验证（API + DB + 前端）** | V20–V28/V34–V37、B29–B40 |
| A24/I-2 账号审计白名单无密码 | **可验证（API + DB）** | V10/V24、B32/B33 |
| A27/A28/A30 System/Audit 页 | **可验证（前端 + 真实 API）** | V27/V28/V30/V-FE-1…4；**不得用 Mock 替代真实 API** |
| A31/I-15 不改既有语义 | **可验证（回归）** | V31；复用既有域用例 |
| V-DB-F015-1/2/3/5 append-only/FK/无 CHECK/迁移 | **可验证（真 PG）** | raw SQL + `pg_trigger`/`pg_constraint` 断言 |
| V-DB-F015-4 索引 EXPLAIN | **条件可验证（真 PG）** | 待 Database 采纳 DR-227；否则 `NOT_REQUIRED` |

口径明确记录：**F015 不重验各域单一恢复/删除完整用例**（V19 仅回归核对）；**Audit 备份与完整 §31/§32 归 F016**；**F015-OPEN-1 未裁定前不得以「最后一个 ADMIN 保护」为预期判失败**（处理见 §5）；**索引 EXPLAIN 仅在 Database 采纳 DR-227 时执行**。

---

## 5. F015-OPEN-1（最后一个 ACTIVE ADMIN 保护）与其它 OPEN 的测试处理

- **F015-OPEN-1**：`product.md`/architecture 均记为 OPEN（无已确认规则），architecture §7 的 **PROPOSED 默认=不加保护**。
  - TD-1 处理：**不生成以「拒绝停用/降级最后一个 ACTIVE ADMIN」为 PASS 的验收断言**；该行为未裁定，不作为 A20–A26 的判据。
  - 若 CONTRACT 采纳「加保护」：由 TD-2 新增验证项（停用/降级最后一个 ADMIN → 409/422，且系统仍保留至少一个可登录 ADMIN）后执行。
  - 若 CONTRACT 采纳「不加保护」（默认）：仅验证停用/降级按常规语义生效（A21/A22），**不把可致无管理员的场景记为缺陷**，仅作为 NOTE 记录。
  - Owner：Product / Architect（CONTRACT 裁定）。
- **其它 OPEN 处理**：
  - O-5（初始凭据/改密/重置）：改密/重置/首登强制改密**本期不实现**；V35/V37 只验证「初始密码创建 + 无改密端点 404/405」，密码长度按 Contract 草案 PROPOSED 8–128 建立判据，定稿后固定。
  - O-7（已删列表字段/删除操作者/`q`）：V13/V33 按 Contract 草案 `object_type/object_id/version/label/cluster/deleted_at` 建立；**不返回删除操作者**为当前默认；若 CONTRACT 新增字段/`q`，由 TD-2 追加。
  - O-4/CONTRACT 参数形态（`operator` 精确匹配、排序/时间闭区间、`deleted` 语义）：V3/V4/V32/V33 按草案建立；若最终改为子串匹配或调整参数名，TD-2 同步判据。
  - O-6/DR-222 `object_type="user"` 登记：V-DB-F015-3 验证无 Schema CHECK 阻挡；Database 若要求登记表/迁移，TD-2 按结论调整。
  - DR-227 索引：V-DB-F015-4 条件执行（见 §6）。

---

## 6. 索引（DR-227）与真实 PG 环境验证方案

- **环境**：真实 PostgreSQL 16（Compose `db`），独立测试库（库名含 `test` 且 ≠ `DATABASE_URL`）；`pg_engine` 重建 schema + `alembic upgrade head`。
- **DR-227（PROPOSED→DATABASE）**：`ix_audit_logs_operator_username`（`btree audit_logs(operator_username)`）；既有索引覆盖 `object_type`/`object_id`/`created_at`/`operator_user_id`；**不改 `audit_logs` 结构**。
- **若 Database 采纳**：
  - V-DB-F015-4：`SELECT ... FROM audit_logs WHERE operator_username = $1` 的 `EXPLAIN (FORMAT JSON)` 断言使用该索引（或断言迁移已创建且 planner 可命中）；建行数足以使 planner 选择索引。
  - B44：`alembic upgrade head` → `downgrade <prev>` → `upgrade head`，核对索引随迁移增删、既有数据保留。
  - V-DB-F015-5：`pg_indexes`/`pg_class` 断言表结构未改，仅新增索引。
- **若 Database 判 `NOT_REQUIRED`**：V-DB-F015-4 记 `NOT_REQUIRED`（附理由：既有索引已覆盖查询，或规模未达阈值），不判 FAIL；V-DB-F015-1/2/3/5 仍必做。
- **SQLite / Mock 不得**作为约束、触发器、索引、并发证据。

---

## 7. 真实 PG 与前端可验证性口径

- **约束证据**全部来自真实 PG：append-only 触发器、FK RESTRICT、用户名唯一、`object_type` 无 CHECK、迁移/索引。
- **并发证据**来自 `committed_engine` 双连接 + 最终持久化断言（恢复、账号 PATCH 乐观锁）。
- **前端**：必须经真实 API 集成（非 Mock）；若缺构建/浏览器 harness，则页面交互记 BLOCKED，不得以 Mock 断言替代 A27/A28/A30。
- **状态文件一致性**：项目状态/派生字段变更时运行 `docs/project/project-state.md` 指明的校验脚本（结构通过不代表批准或 Git 证据有效）。

---

## 8. 数据完整性对照（计划验证，不填 PASS）

| 规则依据 | 计划验证 | 环境 |
| --- | --- | --- |
| append-only（I-1/DB-D28） | V8/B10/B11 + V-DB-F015-1 | 真PG约束 |
| operator 快照/FK RESTRICT（I-4/DB-D27） | V11/B27/B28 + V-DB-F015-2 | 真PG集成/约束 |
| 恢复原子/不覆盖/不级联（I-5/I-6/I-7） | V14–V19/B15–B26 | 真PG集成/并发 |
| 用户唯一/无删除/乐观锁（I-9/DB-D16） | V20/V26/V34–V37/B29–B40 | 真PG集成/约束 |
| 账号审计脱敏/同事务（I-2） | V10/V24/B32/B33 | 真PG集成/约束 |
| 权限服务端（I-11/§23） | V1/V26/V29/B1–B3 | 真PG集成/静态 |
| 只读无副作用（I-12） | V5/V7/V38/B9/B42 | 真PG集成/约束 |

---

## 9. OPEN 复核项（TD-1 提出，待 CONTRACT / DATABASE 定稿后由 TD-2 关闭）

| OPEN | 待复核假设 | 影响验证项 | Owner |
| --- | --- | --- | --- |
| OPEN-1 | `docs/api/F015.md` 草案 v0 未签核（DRAFT）；端点路径/参数名/响应字段 details 可能调整 | 全部 | 协调器 / Architect |
| OPEN-2 | Audit 参数形态：`operator` 精确匹配 vs 子串；`object_type` 枚举全集（含 `user`）；`object_type`+`object_id` 同现；时间闭区间与排序稳定 | V3/V4/V32、B4–B7 | Architect（CONTRACT） |
| OPEN-3 | 已删列表字段（O-7）：是否返回删除操作者、是否加 `q`；label/cluster 映射最终口径 | V13/V33、B14 | Architect |
| OPEN-4 | 用户端点细节：`q`/`sort` 集合、密码长度（PROPOSED 8–128）、PATCH 校验顺序 401→403→422→404→409、`UserRow` 字段 | V20/V34–V36、B29–B38 | Architect（CONTRACT） |
| OPEN-5 | 账号初始凭据/改密（O-5）：改密/重置/首登强制改密本期不实现；无改密端点确认 | V35/V37 | Product / Architect |
| OPEN-6 | `object_type="user"` 登记（O-6/DR-222）与无 Schema 变更复核；是否需要登记表/迁移 | V-DB-F015-3/V10 | Architect / Database |
| OPEN-7 | `ix_audit_logs_operator_username`（DR-227）采纳；`layers.database` 真/假；迁移 up/down/up | V-DB-F015-4/V-DB-F015-5、B43/B44 | Database |
| OPEN-8 | F015-OPEN-1 最后一个 ACTIVE ADMIN 保护裁定（加/不加保护），决定是否新增拒绝断言 | A21/A22 边界；B34/B35/B38 | Product / Architect |
| OPEN-9 | F002 错误码/权限无新增复核（F015 复用 `AUDIT_READ`/`USER_ADMIN`/`VIEW_DELETED`/`RESTORE`/`VIEW_ACTIVITY`，不新增 error code） | 全部 | Architect（CONTRACT） |

TD-1 结论：**`TEST DESIGN READY`** —— A1–A31 已映射到可观察判据（V1–V38、V-DB-F015-1…5、V-FE-1…4、V-ST-1…3），边界/并发/环境场景（401 先于 403、Audit 过滤 AND/时间闭区间/分页排序/空结果/只读幂等/append-only/无变更端点、已删 8 类聚合与过滤/label/version/cluster、恢复复用一致性与不级联/不覆盖 409 unique_conflict/dependency_deleted/失败无 Audit 残留/并发、用户创建/重复 409/角色即时/停用登录 401+旧会话 401+会话删除/启用/无注册无删除无改密/PATCH 乐观锁、账号审计白名单无密码/停用不改旧审计/历史身份保留、权限矩阵、前端门控）可执行；夹具与可验证性已与 architecture §2–§6 及 Contract v0 建立对应；真实 PostgreSQL + `committed_engine` + 并发双连接口径固定；索引 EXPLAIN 方案已按 DR-227 条件化。**Contract 为草案 DRAFT、索引/登记待 Database、F015-OPEN-1 未裁定，§9 OPEN-1–9 未经逐项核对；READY 不等于测试通过，不批准实现或合并。** 定稿后由 TD-2 关闭 §9 并固定执行判据。

GIT: NONE