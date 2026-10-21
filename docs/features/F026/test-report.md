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