# F026 Test Report

> TEST DESIGN 与后续 TEST 结果分开记录；本节只表示方案可验证，不代表已执行或 PASS。

## Test Design

- 版本：TD-1（2026-10-21）
- 角色：Tester（TEST_DESIGN）
- 结论：TEST DESIGN READY（附 TD-2 复核条件）
- 依据：requirements revision 11 §21–§23.2/§27/§31（T85–T99）/§32；F026 product A1–A33；F026 architecture v1；`docs/database/f026-cluster-authorization.md` v1；F015/F017 test-report 格式；`backend/tests/conftest.py`（pg_engine/db_session/committed_engine/alembic_runner/role_client_factory）

### TD-1 输入基线

| 输入 | 状态 |
| --- | --- |
| 需求 | revision 11，CONFIRMED |
| Product | A1–A33，无 Blocking Questions |
| Architecture | READY FOR DESIGN |
| Database | READY FOR DATABASE IMPLEMENTATION（DB-D401–D420） |
| Contract | `docs/api/F026.md` 未建立；F002 v3 / F015 v3 errata 待定稿 |
| 实现 | 未开始 |

### TD-2 复核条件（进入 TEST 前）

1. `docs/api/F026.md` READY，冻结端点、Row 字段/nullable、列表参数、错误码/reason 字面、P-1 口径、Audit object_type/action。
2. F002 v3（`already_granted`、`already_revoked` 扩义）与 F015 v3（object_type）定稿。
3. Database / Architecture 索引差异 errata 关闭（OBS-F026-1）。
4. A-3（回填不写业务 Audit）确认；A-1/A-2 在 Contract 记录。
5. 判据字面固定后方可执行 TEST。

### 数据完整性对应

| 规则 | DB 保证 | 应用保证 | 验证 |
| --- | --- | --- | --- |
| 有效授权唯一（§23.2/A2） | 部分唯一索引 23505 | 409 `already_granted` | T-F026-02/03 |
| 归属不可变、撤销单向（§23.2） | UPDATE 触发器 23514 | 无 PATCH；仅 revoke | T-F026-05/33 |
| 历史不物理删除（§23.2） | DELETE 触发器 23001 | 无 DELETE 路径 | T-F026-33 |
| 撤销成对/时间顺序（§23.2） | 2 条 CHECK | 构造成对值 | V-DB-F026-2 |
| 引用（§21/§23.2） | FK RESTRICT | 422 非法目标 | T-F026-13/14/20 |
| 回填（§23.2/T99） | INSERT…SELECT + 计数断言 | 迁移内断言 | T-F026-29/30/31 |
| Audit 同事务（§22） | 无 Schema 变更 | audit.record 同事务 | T-F026-01/05/32/33 |
| AccessScope（§23.2） | 索引 + clusters PK | 空集默认拒绝、ADMIN 不受限、不缓存 | T-F026-21–25 |
| 迁移（§27） | 单 head、对象对称 | 手写 DDL 与 ORM 一致 | T-F026-28 |

### 环境与夹具

- 真实 PostgreSQL（`TEST_DATABASE_URL`，conftest 双重守卫拒绝非测试库）；SQLite/Mock 不作约束证据。
- 会话级 `pg_engine` 重建 schema → `upgrade head`；`db_session`（savepoint 回滚）；`committed_engine`（真实提交 + teardown TRUNCATE）。
- 身份：`bootstrap_admin`、`make_user`、`role_client_factory`、`login`；F026 helper：`grant`/`revoke`/`list_authorizations`/`insert_authorization`/`seed_cross_product`。
- 并发：`committed_engine` 两条独立连接；第三方连接做终态断言。
- 迁移/回填夹具：`downgrade("0014_api_keys")` → raw SQL 预置 users（ADMIN/VIEWER/EDITOR/DISABLED）与 clusters（ACTIVE/INACTIVE/软删）及既有 audit → `upgrade head` → 断言 → 重跑回填 SQL / downgrade→upgrade 验证幂等 → `finally` 恢复 head。
- 串行：迁移与并发用例不得并行共享 `pg_engine`。
- 前端：`npm run typecheck`、`npm run build`、`npm run smoke:client`；浏览器/Compose 归 F028。

### 验收映射（A1–A33）

| 用例 | 覆盖 | 层 | 核心断言 |
| --- | --- | --- | --- |
| T-F026-01 | A1/A30 | 真HTTP+PG | 授予 201、Row 字段齐全、effective=true、审计 1 条 CREATE 同事务 |
| T-F026-02 | A2 | 真HTTP+PG | 重复授予 409 `already_granted`、有效行 1、无新增审计 |
| T-F026-03 | A2 | 真PG并发+约束 | 两连接并发后有效行 ≤1、一方 409、审计 1 条；raw SQL 第二有效行 23505 |
| T-F026-04 | A3/A21 | 真HTTP+PG | 授予 ADMIN 422、0 行、无审计；ADMIN scope unrestricted |
| T-F026-05 | A4/A31 | 真HTTP+PG | 撤销 200、REVOKED、撤销时间/人正确、行保留、审计 UPDATE 非 DELETE |
| T-F026-06 | A5 | 真HTTP+PG | 重授新 id、旧行不变、1 有效 + N 已撤销 |
| T-F026-07 | A6 | 真HTTP+PG | 仅 ADMIN；VIEWER/EDITOR 403；匿名 401 先于 403；CSRF；无新权限项 |
| T-F026-08 | A7 | 真HTTP+PG | Row 字段/类型/nullable、effective 口径、UTC |
| T-F026-09 | A7 | 真HTTP+PG | status/cluster_id/q 过滤、sort/order、同刻 id 稳定、total 一致、空 200、只读 |
| T-F026-10 | A7 | 真HTTP+PG | 非法分页/排序/q/未知参数 422 `fields` |
| T-F026-11 | A8/P-1 | 真HTTP+PG | 路径 user/authorization 不存在或非法 → 404，无残留 |
| T-F026-12 | A8 | 真HTTP+PG | 撤销已撤销 409 `already_revoked`、状态与审计不变 |
| T-F026-13 | A14 | 真HTTP+PG | 不存在/非 UUID cluster 422 `cluster_id`、0 行、0 审计 |
| T-F026-14 | A14/A15/T96 | 真HTTP+PG | 软删 Cluster 授予 422；其上既有有效授权允许撤销；FK 无悬空 |
| T-F026-15 | A11/A12/T95 基座 | 真HTTP+PG | INACTIVE 可授予；ACTIVE⇄INACTIVE 行与 scope 不变 |
| T-F026-16 | A13/A29 | 真HTTP+PG | 软删后行保留/effective=false/scope 不含；恢复后自动生效 |
| T-F026-17 | A13 | 真HTTP+PG | 软删期间撤销 → 恢复后不生效；重新授予正常 |
| T-F026-18 | A16 | 真HTTP+PG | 新建 Cluster 0 行、scope 不变 |
| T-F026-19 | A17/A-2 | 真HTTP+PG | 升级 ADMIN 不受限且行保留；降级立即按既有行（可空） |
| T-F026-20 | A18/A-1 | 真HTTP+PG | 停用后 401、行不变；DISABLED 目标授予按 Contract；启用后恢复 |
| T-F026-21 | A19 | 真HTTP+PG | 仅 A/B 时集合精确 {A,B}；predicate 不命中 C |
| T-F026-22 | A20/T93 基座 | 真HTTP+PG | 零授权空集、predicate 恒假、不回退全量 |
| T-F026-23 | A21 | 真HTTP+PG | ADMIN unrestricted、predicate 恒真、无行 |
| T-F026-24 | A22/A23 | 真HTTP+PG | 同请求同一实例；无模块级缓存；请求内快照稳定 |
| T-F026-25 | A23/T91 基座 | 真HTTP+PG | 授予/撤销/角色变更后下一请求即时；Cookie 与 API Key 同口径 |
| T-F026-26 | A24/D-4 | 真HTTP+PG+静态 | `get_access_scope`/`AccessScope` 不被既有 api/services 引用；既有端点行为不变 |
| T-F026-27 | A24/T97 抽样 | 真HTTP+PG | 全量既有 pytest 无回归；角色矩阵与 T01–T41 关键抽样不变 |
| T-F026-28 | A25/T99 | 真PG迁移 | 单 head、up/down/up、对象对称、部分索引谓词正确、既有 Schema 不变 |
| T-F026-29 | A26/T99 | 真PG迁移 | 非 ADMIN × 全部 Cluster（含软删、DISABLED）恰 1 有效；ADMIN 0；计数；业务数据与 audit 不变 |
| T-F026-30 | A27 | 真PG迁移 | 重跑 0 行；已撤销不复活；空数据边界 |
| T-F026-31 | A28/A29 | 真PG迁移+约束 | 已有业务数据上升级成功；无失权/越权；业务数据不变；恢复软删后授权生效 |
| T-F026-32 | A30–A33/T92 | 真HTTP+PG+约束 | 审计同事务、白名单 6 键、ADMIN 可查/非 ADMIN 403、无凭据、失败无残留 |
| T-F026-33 | A4/A5/A33 | 真HTTP+PG+约束 | 无 DELETE/PATCH 路由；DELETE 23001；归属/复活 UPDATE 23514；无 DELETE 审计 |
| T-F026-34 | A9–A11 | 前端机制+Mock | Tab 仅 ADMIN；ADMIN 行禁用；候选过滤/INACTIVE 可选/50 条提示；成功/失败呈现；ConfirmDialog；三态；恒定披露 |

### 覆盖核对

A1→01；A2→02/03/33；A3→04/23；A4→05/33；A5→06/33；A6→07；A7→08/09/10；A8→11/12；A9–A11→34（浏览器级 F028）；A12→15；A13→16/17；A14/A15→13/14；A16→18；A17→19；A18→20；A19–A23→21–25；A24→26/27；A25–A29→28–31；A30–A33→01/05/32/33。

需求 §31：T90→07；T92→01/05/32；T96→13/14；T99→28–31；T91/T94/T95/T85/T93 基座→25/07/15–17/21–22/26。T85–T89、T97–T98 端到端归 F027/F028。

### 前端边界

- F026：typecheck/build/smoke（契约级 Mock）覆盖权限门控、候选过滤、409/422 内联、ConfirmDialog、三态、恒定披露。
- F028：真实浏览器 DOM、焦点/Esc/双击/窄屏、真实前后端串联、Compose。

### 显式边界

1. F026 不对既有业务端点施加范围过滤；T85–T89、T91/T94/T95 端到端、T97/T98 全量回归归 F027/F028。
2. F026 交付后至 F027 合并前，非 ADMIN 可见范围仍为现状；不得宣称范围已生效。
3. 软删/生效性在 F026 以 AccessScope 解析结果与 `effective` 字段为证据，不以业务列表过滤为证据。
4. 真实 PostgreSQL 是约束/迁移/并发/解析的唯一证据来源；SQLite/Mock 不作数。

### 观察项（非实现缺陷）

| ID | 级别 | 事项 | Owner | 阻塞 TEST |
| --- | --- | --- | --- | --- |
| OBS-F026-1 | LOW | Architecture 的 `(user_id) WHERE revoked_at IS NULL` 与 DB-D407 全量 `(user_id)` 差异 | Architect/Database errata | 否（以 DB 设计为断言依据，TD-2 复核） |
| OBS-F026-2 | MEDIUM | `docs/api/F026.md` 与 F002/F015 errata 未定稿 | Architect | 否（TD-2 关闭后 TEST） |
| OBS-F026-3 | MEDIUM | A-3 回填不写 Audit 仍 PROPOSED；A-1/A-2 未在 Contract 记录 | Product/用户 | 否（确认后固定） |
| OBS-F026-4 | MEDIUM | P-1 路径/语义错误分解与 `user_id` 非 UUID 的 404/422 未字面化 | Architect/Contract | 否（TD-2 固定） |
| OBS-F026-5 | LOW | 迁移用例与并发用例共享 `pg_engine`，须串行 | Tester | 否（执行纪律） |

### 未验证项

- A1–A33 执行结果：NOT TESTED（实现未开始）。
- Contract 字面判据：BLOCKED until TD-2。
- 浏览器 DOM / 真实串联 / Compose：NOT TESTED（F028）。
- 迁移 EXPLAIN 基线：Database 阶段证据；TEST 只核对索引存在与谓词。
- T85–T99 端到端：OUT OF SCOPE（F027/F028）。

### 下一步

1. CONTRACT Gate：`docs/api/F026.md` + F002 v3 / F015 v3 errata，关闭 OBS-2/4。
2. Database 出 OBS-1 errata；Product 关闭 A-3（OBS-3）。
3. TD-2 复核固定判据；实现完成后进入 TEST，串行执行迁移/并发，独立复跑全量后端 + 前端三命令。

**Status：TEST DESIGN READY（TD-1）**

## Test Execution

- 版本：TEST-1（2026-10-21）
- 角色：Tester（TEST，独立执行）
- 结论：**RETURN TO IMPLEMENTATION**（1 个 MEDIUM 实现缺陷；其余已执行项通过，前端 A9–A11 运行时验证留 F028）
- TD-2 复核：Contract v1、Database v1、Architecture 已定稿；OBS-F026-1/2/4 关闭；A-3 按 Contract §9.7 记录；判据以 `docs/api/F026.md` v1 第 5 节 P-1 为准。

### 1. 环境

| 项 | 值 |
| --- | --- |
| 数据库 | 真实 PostgreSQL 测试容器 `postgresql+psycopg://csm:***@127.0.0.1:55432/csm_test` |
| 环境变量 | 已 `export TEST_DATABASE_URL=…`，已 `unset DATABASE_URL` |
| Python / pytest | Python 3.12.7 / pytest 7.4.4 |
| 前端 | Node/npm（`frontend/`）；测试便利软链 `node_modules -> /home/hanhao/github/47oo/csm/frontend/node_modules`，不入仓 |
| 测试数据 | F026 集成夹具 + 独立临时探针（`/tmp/f026extra/`，未写入仓库）；未连接生产或未知数据库 |
| 执行纪律 | 迁移/并发/独立探针串行执行；全量后端与临时探针不并行访问同一测试库 |

### 2. 实际命令与结果

| # | 命令 | 结果 |
| --- | --- | --- |
| 1 | `cd backend && python3 -m pytest -q tests/integration/test_cluster_authorizations.py` | **8 passed**，8.06s |
| 2a | `cd backend && python3 -m pytest -q`（首次） | **1 failed, 707 passed, 2 skipped**，895.41s；失败 `tests/integration/test_clusters.py::test_audit_four_actions_and_activity`（`created_at` 同刻排序，非 F026 行为） |
| 2b | 单测复跑失败用例 + 整个 `test_clusters.py` | 单测 passed（2.88s）；文件 **21 passed**（14.20s）；未复现 |
| 2c | `cd backend && python3 -m pytest -q`（干净复跑） | **708 passed, 2 skipped**，1035.54s（17:15）；失败未复现 |
| 3 | `cd frontend && npm run typecheck` | **pass** |
| 3 | `cd frontend && npm run build` | **pass**（vite build，3213 modules；仅 chunk 体积提示） |
| 3 | `cd frontend && npm run smoke:client` | **322 passed, 0 failed**（含 F026 client 3 项） |
| 4 | Alembic heads 查询 | 单一 head `0015_user_cluster_authorizations` |
| 5 | 静态引用检查：`get_access_scope` / `resolve_access_scope` / `AccessScope` 在 `app/` 中除 `core/access_scope.py` 外 | **无引用**（F026 未把范围解引用接入既有端点） |

全量 2 个 skip 均为既有原因：F016 acceptance 模块未启用、DB-D11 非 superuser 用例（测试库连接角色为 superuser）。

### 3. 独立验证探针（未入仓）

| 探针 | 结果 |
| --- | --- |
| 列表路径 user 不存在 | **FAIL**：`GET /api/v1/users/{random-uuid}/cluster-authorizations` → `200 {items:[],total:0}`；Contract §3 要求 404。见 D-TEST-F026-01 |
| 审计查询 `GET /api/v1/audit?object_type=user_cluster_authorization` | PASS：ADMIN 200 且含 CREATE/UPDATE；VIEWER 403；快照仅 6 个白名单键、无密码/令牌/`csm_ak_` 明文 |
| 并发重复授予（两会话 barrier） | PASS：一方成功、一方 `Conflict:already_granted`；有效行 1、审计 1 |
| 迁移回填重跑 / 不复活 | PASS：up 后 users/clusters/audit 计数不变；手写回填 SQL 连续重跑 0 新增；已撤销行保持 REVOKED；无重复有效行 |
| ACTIVE ⇄ INACTIVE | PASS：授权行、id、`effective`、解析集合均不变 |
| ADMIN 升级 / 降级 | PASS：升级后 unrestricted 且既有行保留；降级后立即按既有行解析 |
| DISABLED 账号 | PASS：可为 DISABLED 授予；停用期间登录 401、授权行不变；启用后可登录 |
| 列表排序/分页/同刻 tie | PASS：`granted_at` asc/desc、page/page_size、`total` 与 filters 一致；同刻按 id 升序 |
| 同请求快照 / 不跨请求缓存 | PASS：同 `Request` 第二次解析返回同一实例且保持旧快照；新请求立即看到撤销 |
| 失败无残留 / CSRF | PASS：授予 ADMIN、非法 Cluster、重复授予、重复撤销均不新增行或审计；Cookie 跨站 POST → 403 `{reason:"csrf"}` |
| 既有端点不过滤（F026 边界） | PASS：无授权 VIEWER 仍正常 `GET /clusters`（total ≥2）；静态无 AccessScope 引用 |
| 新建 Cluster 不自动授权 | PASS：新建后该 VIEWER 无对应授权行 |

### 4. 验收映射（A1–A33）

| 验收 | 结果 | 证据 / 说明 |
| --- | --- | --- |
| A1 | PASS | T-F026-01：授予 201、Row 完整、ACTIVE/effective、审计 1 条 CREATE |
| A2 | PASS | T-F026-02 + 并发探针：重复 409 `already_granted`，有效行 1、审计 1 |
| A3 | PASS | T-F026-04 + 失败残留探针：授予 ADMIN 422、0 行/0 审计；ADMIN unrestricted |
| A4 | PASS | T-F026-05/33：撤销 REVOKED、保留时间/操作者、无物理删除、审计 UPDATE |
| A5 | PASS | T-F026-06/33：重授新 id；1 有效 + N 已撤销；旧行不改写 |
| A6 | PASS | T-F026-07：匿名 401 先于 403；VIEWER/EDITOR 403；CSRF 探针 403 |
| A7 | PASS | T-F026-08/09/10 + 排序 tie 探针：字段/类型/UTC、status/cluster_id/q、分页排序、空 200、非法参数 422 |
| A8 | **FAIL** | 撤销不存在 404、已撤销 409 且无审计均 PASS；但**列表路径 user 不存在返回 200 空集**，违反 Contract §3/P-1。见 D-TEST-F026-01 |
| A9 | PARTIAL | 静态：SystemPage 仅 `USER_ADMIN` 渲染 Tab；服务端矩阵已实测。无组件/浏览器运行时用例，真实交互留 F028 |
| A10 | PARTIAL | 静态：成功/失败态与 409/422 文案存在；smoke 验证 API 错误映射。无组件运行时用例，留 F028 |
| A11 | PARTIAL | 静态：Cluster 候选 `deleted=exclude`、排除已有效授权、INACTIVE 可选、50 条提示；ADMIN 目标只展示说明不允许授予。无组件运行时用例，留 F028 |
| A12 | PASS | ACTIVE⇄INACTIVE 探针：行与解析集合不变 |
| A13 | PASS | T-F026-16/17：软删保留行、effective=false、scope 排除；恢复自动生效；期间撤销恢复后仍不生效 |
| A14/A15 | PASS | T-F026-13/14：不存在/非 UUID/软删 Cluster 422，0 行/0 审计；无悬空 FK |
| A16 | PASS | 新建 Cluster 探针：不自动产生非 ADMIN 授权 |
| A17 | PASS | 升降级探针：升级 unrestricted、行保留；降级按既有行解析 |
| A18 | PASS | DISABLED 探针：停用 401、授权不变；启用后恢复 |
| A19 | PASS | T-F026-21：仅 A/B 时精确 {A,B}，C 不命中 |
| A20 | PASS | T-F026-22：零授权空集，predicate 恒假，不回退全量 |
| A21 | PASS | T-F026-23：ADMIN unrestricted，predicate 恒真 |
| A22 | PASS | 同请求探针：同一 Request 复用同一实例且快照稳定 |
| A23 | PASS | T-F026-25 + 探针：撤销后新请求即时；API Key 继承绑定账号范围 |
| A24 | PASS | 干净全量 708 passed；无 AccessScope 外部引用；无授权 VIEWER 仍可见既有列表 |
| A25 | PASS | 迁移测试 up/down/up；单 head；触发器/索引随 downgrade 对称删除 |
| A26 | PASS | T-F026-29 + 回填探针：非 ADMIN × 全部 Cluster（含软删/DISABLED）恰 1 有效；ADMIN 0；计数一致 |
| A27 | PASS | 回填重跑探针：0 新增、不复活已撤销、无重复有效行 |
| A28 | PASS | 回填前后 users/clusters/audit 计数不变；无失权/越权证据 |
| A29 | PASS | 迁移在既有业务数据+软删 Cluster 上成功；恢复后授权生效（T-F026-16/31） |
| A30 | PASS | T-F026-01 + 失败残留探针：成功授予 1 条审计且与写入同事务路径；失败 0 残留 |
| A31 | PASS | T-F026-05 + 失败残留探针：撤销 1 条 UPDATE 审计，可追溯 |
| A32 | PASS | 审计查询探针：ADMIN 200；非 ADMIN 403 |
| A33 | PASS | 无 DELETE/PATCH 路由；DELETE/归属/复活 UPDATE 被触发器拒绝；审计仅 CREATE/UPDATE、无敏感内容 |

### 5. 缺陷

| ID | Severity | Layer | Location | 期望 / 实际 | 影响 | Owner | 必须修复 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| D-TEST-F026-01 | MEDIUM | Backend API | `backend/app/api/v1/cluster_authorizations.py` 列表端点（未校验路径 user 存在） | 期望：`GET /users/{不存在 UUID}/cluster-authorizations` → 404 `NOT_FOUND`（Contract §3、§5 P-1、TD T-F026-11）。实际：200 `{items:[],page:1,page_size:20,total:0}` | 管理端查询拼错/过期账号时静默成功，违反已签核契约与统一 P-1 语义；无数据泄漏 | Backend | 是 |

复现：ADMIN 登录后请求 `GET /api/v1/users/<random-uuid>/cluster-authorizations`。修复后应收敛到 404，同时保留空结果（真实存在且无授权用户）200。

### 6. 观察项（不单列为实现缺陷）

| ID | 级别 | 事项 | Owner |
| --- | --- | --- | --- |
| OBS-TEST-F026-1 | LOW | 首次全量 `test_clusters.py::test_audit_four_actions_and_activity` 因审计 `created_at` 同刻排序失败；单测、文件复跑与干净全量均通过，未复现，判定为既有测试时序 flake，与 F026 变更无直接关联，建议后续固定 tie-breaker | 协调器/测试基础设施 |
| OBS-TEST-F026-2 | LOW | F026 未新增组件级前端测试；A9–A11 仅静态审查 + typecheck/build/smoke（client 层），真实交互归 F028 | Tester/Implementer |
| OBS-TEST-F026-3 | NOTE | 迁移测试以 `pytest.raises(Exception)` 验证触发器，未逐条断言 SQLSTATE 23001/23514；本次独立探针与 DDL 审查确认错误码，建议后续精确断言 | Tester |

### 7. 未验证 / 边界

- A9–A11 的浏览器 DOM、焦点/Esc/双击、窄屏与真实前后端串联：**NOT TESTED**，按计划归 F028。
- F027 范围强制执行（既有业务端点 404/列表/total/搜索/Dashboard/导入收敛）：**OUT OF SCOPE**；F026 交付后至 F027 合并前非 ADMIN 可见范围仍为现状。
- 真实 Compose / T85–T99 端到端：**OUT OF SCOPE**（F028）。
- 迁移 EXPLAIN 基线：Database 阶段证据；本次仅核对对象/回填/up-down-up 行为。
- 强制审计写入失败以证明回滚：**NOT TESTED**；已验证正常路径同事务与失败分支无残留。

**Status：RETURN TO IMPLEMENTATION**

GIT: NONE

---

### Repair Verification 1

- 版本：RV-1（2026-10-21），针对 D-TEST-F026-01 修复后的独立复测
- 角色：Tester（TEST）
- 结论：**READY FOR REVIEW**（本节结论取代上方 Test Execution 的 Status；历史记录按版本保留）
- 基线：`0360f7b`（`fix(F026): 404 for unknown user in authorization list`）

#### RV-1.1 修复审查（只读）

| 项 | 内容 |
| --- | --- |
| 变更范围 | `git show --stat HEAD`：`backend/app/services/cluster_authorization.py`（+3）、`backend/tests/integration/test_cluster_authorizations.py`（+3）、`docs/features/F026/test-report.md`、`docs/project/project-plan.yaml`；无 Schema/迁移/前端变更 |
| 生产改动 | `list_authorizations()` 在 sort/order/status/q 语义校验之后新增 `_get_user_or_404(db, user_id)`；进行查询前抛 `NotFound` |
| 复用既有语义 | `_get_user_or_404` 与授予端点（`grant_authorization`）同一实现，404 `NOT_FOUND` 与 Contract §3「路径 `user_id` 非 UUID 或不存在 → 404」及 §5 P-1 一致 |
| 回归断言 | `test_authorization_permissions` 新增 `_list(admin, uuid4())` → 404 且 `error.code == "NOT_FOUND"` |
| 软删口径核对 | `User` 模型无 `deleted_at`（仅 `status` ACTIVE/DISABLED），`db.get` 即完整存在性判断，不存在软删账号被误判为存在而返回 200 的缺口 |
| 参数优先级 | 契约仅固定「403 先于 422/404/409」，未规定 422 与 404 的相对次序；修复把路径存在性校验放在查询参数语义校验之后，与既有端点风格一致，不构成契约违反 |

#### RV-1.2 环境

| 项 | 值 |
| --- | --- |
| 代码 | `/home/hanhao/github/47oo/csm-chg010`，HEAD `0360f7b`（工作区除未跟踪 `frontend/node_modules` 外无改动） |
| 数据库 | 真实 PostgreSQL `postgresql+psycopg://csm@127.0.0.1:55432/csm_test`（`TEST_DATABASE_URL`），`DATABASE_URL` 已 unset；库名含 `test`，满足 DB-D10 守卫 |
| 夹具 | 生产 app + `get_db` 覆盖为测试库；Alembic upgrade head；未使用 SQLite、未使用 Mock 代替真实 API/DB |

#### RV-1.3 命令与结果

| # | 命令 | 结果 |
| --- | --- | --- |
| 1 | `python3 -m pytest -q tests/integration/test_cluster_authorizations.py` | **8 passed** in 7.39s |
| 2 | `python3 -m pytest -q tests/integration/test_users.py tests/integration/test_auth.py tests/integration/test_migrations.py tests/integration/test_f017_migrations.py` | **36 passed, 1 skipped** in 20.96s（skip：`test_migrations.py:105` 当前角色为 superuser，V3b 需非 superuser 属主，属既有环境跳过，非本次变更引入） |
| 3 | `python3 -m pytest -q`（全量回归） | **708 passed, 2 skipped** in 905.67s（额外 skip：`test_f016_acceptance.py:50` 未设 `F016_ACCEPTANCE=1`）；本轮未复现 OBS-TEST-F026-1 的审计时序 flake |

以上 3 条均为本轮实际执行。

#### RV-1.4 D-TEST-F026-01 原始探针独立复跑

临时探针文件仅存在于运行期，运行后已删除（`git status` 复核无残留）；未改动生产代码。

| 探针 | 结果 |
| --- | --- |
| ADMIN `GET /api/v1/users/{随机 UUID}/cluster-authorizations` | **404** `{"error":{"code":"NOT_FOUND","message":"Not found","details":{}}}`（修复前为 200 `{items:[],total:0}`） |
| 同上 + 合法过滤参数 `status=ACTIVE&page=2&page_size=5&order=asc` | **404 `NOT_FOUND`**：路径存在性优先于分页/过滤空结果，未退化为 200 空集 |
| 非 UUID 路径段 `GET /api/v1/users/not-a-uuid/cluster-authorizations` | **404 `NOT_FOUND`**（P-1「路径非 UUID → 404」保持） |
| 存在且无授权 VIEWER / EDITOR / ADMIN 账号 | **200** `{"items":[],"page":1,"page_size":20,"total":0}`：空结果语义未被修复破坏，ADMIN 目标亦为可查询 200 |
| VIEWER / EDITOR 访问不存在 user 的列表 | **403** `{reason:"permission"}`：403 先于 404，符合 §5 |
| 404 路径写副作用 | ADMIN 请求前后 `users/user_cluster_authorizations/audit_logs` 计数 `(1,0,0) → (1,0,0)`，只读无写入 |
| 回归断言敏感性（内存变异，未改源码） | 运行时 `monkeypatch` 将 `_get_user_or_404` 置为 no-op 后端点回到 **200** `{items:[],total:0}`，证明新增断言能捕获守卫被移除的回归 |

#### RV-1.5 验收影响

| 验收 | 结果 | 证据 |
| --- | --- | --- |
| A8（T-F026-11 列表路径 user 不存在） | **PASS（此前 FAIL）** | RV-1.4：未知 UUID → 404 `NOT_FOUND`；存在用户空集 200；非 UUID → 404 |
| A7（列表参数/空结果/422） | PASS | 文件测试 8 passed；`status=BOGUS` 仍 422；存在用户空集 200 保持 |
| A6（401 先于 403、403 先于 404） | PASS | 文件测试匿名 401、VIEWER/EDITOR 403；探针确认非 ADMIN 对未知 user 得 403 |
| A24（既有端点回归） | PASS | 全量 708 passed，无新增失败 |
| A25–A29（迁移/回填） | PASS（无变化） | `test_migrations.py`、`test_f017_migrations.py` 与全量套件通过；本次未改 Schema/迁移 |

#### RV-1.6 缺陷状态

| ID | 原 Severity | 状态 | 说明 |
| --- | --- | --- | --- |
| D-TEST-F026-01 | MEDIUM | **CLOSED（已修复）** | 修复位置由 API 层收敛到 `list_authorizations` 服务层，与授予端点共用 `_get_user_or_404`；回归断言已入仓并经验证具备行为敏感性；原始探针独立复跑通过 |

本轮未发现新的实现缺陷。

#### RV-1.7 观察项（新增，不单列缺陷）

| ID | 级别 | 事项 | Owner |
| --- | --- | --- | --- |
| OBS-TEST-F026-4 | NOTE | 未知 user 与非法查询参数同时出现时返回 422（参数校验先于路径存在性）；契约仅固定 403 优先级，未定义 422/404 次序，故非违规，但如需统一口径应在 Contract 后续版本字面化 | Architect/Contract |
| OBS-TEST-F026-1/2/3 | — | 维持上述原记录：审计时序 flake 本轮未复现；A9–A11 组件运行时留 F028；迁移触发器异常仅断言 Exception 类型 | 协调器/Tester |

#### RV-1.8 未验证 / 边界（不变）

- A9–A11 浏览器交互与真实前后端串联：**NOT TESTED**，按计划归 F028。
- F027 范围强制（业务端点 404/列表收敛）：**OUT OF SCOPE**。
- 真实 Compose / T85–T99 端到端：**OUT OF SCOPE**（F028）。
- 强制审计写入失败以证明回滚：**NOT TESTED**（本轮未涉及该路径）。

**Status：READY FOR REVIEW**

GIT: NONE
