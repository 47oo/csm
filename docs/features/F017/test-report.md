# F017 API Key 机器凭据 — Test Report

> 本文件同时承载 TEST DESIGN 与后续 TEST 结果；TEST DESIGN 仅表示方案可验证，不代表测试通过。

## Test Design

- **版本**：TD-1
- **日期**：2026-10-14
- **角色**：Tester（TEST_DESIGN 模式）
- **结论**：`TEST DESIGN READY`（TD-1）
- **依据**：
  - `docs/product/requirements-v3.md` revision 4（§22、§23、§23.1、§25、§26、§27、§31 T42–T49、§32、§35.1）
  - `docs/features/F017/product.md`（A1–A8）
  - `docs/features/F017/architecture.md`（DR-301–DR-318、§4 API 草案、§5 Database 影响、§6 Test Work）
  - `docs/database/f017-api-key.md` v1（DB-D301–DB-D316）
  - `docs/api/F002.md` v1（§1.1 信封、§1.2 错误码、§1.2.1 CONFLICT reason 注册表、§2.1 CSRF、§3 权限矩阵、§4 auth 端点）
  - `docs/project/handoff.md`、`docs/project/implementation-rules.md`、`.pi/skills/data-integrity/SKILL.md`
  - 现有测试基础设施：`backend/tests/conftest.py`、`backend/tests/integration/f015_helpers.py`、`backend/tests/integration/test_auth.py`、`backend/tests/integration/test_migrations.py`

### 被测版本输入（TD-1 基线）

| 输入 | 版本 / 状态 | 说明 |
| --- | --- | --- |
| 产品需求 | revision 4（§23.1、T42–T49 已 CONFIRMED） | 验收权威来源 |
| Feature 验收 | `docs/features/F017/product.md` A1–A8 | 无 Blocking Questions |
| 架构设计 | `docs/features/F017/architecture.md`，DR-301–DR-318 | DR-302/303/308/312/315/316/318 为 PROPOSED→CONTRACT；DR-305/306/314 为 PROPOSED→DATABASE |
| API Contract | `docs/api/F017.md`（CONTRACT Gate 定稿） | TD-1 采用 architecture §4 草案；TD-2 逐项核对 |
| Database 设计 | `docs/database/f017-api-key.md` v1 | READY FOR DATABASE IMPLEMENTATION |
| 实现 | 尚未实现（无 `api_keys` 表、无 `0014` 迁移、无前端面板） | TEST_DESIGN 阶段正常状态 |

### 复核基线（TD-2）

`docs/api/F017.md` v1 READY + `docs/api/F002.md` v2 / `docs/api/F015.md` v2 修订定稿后，核对端点/字段/错误/默认值与 365 天口径，固定 V-DB-F017-* 与 B8/B15/CONFLICT 字面判据，方可作为 TEST 执行依据。

---

### 0. 数据完整性对应表（F017 范围）

| 规则依据及版本 | 作用域/写入入口 | 数据库保证 | 业务层保证 | 并发/生命周期边界 | 验证与证据 |
| --- | --- | --- | --- | --- | --- |
| §23.1 / DR-305 | `api_keys.key_hash` | UNIQUE + `^[0-9a-f]{64}$` CHECK | 高熵 token，仅存 SHA-256 hex | 并发创建唯一约束兜底 | V-DB-F017-2、B10 |
| §23.1 / DR-305 | `api_keys.label` | `btrim(label) <> ''` CHECK | trim 后非空、1..255、禁控制字符 | 无唯一性要求（F017-OPEN-3） | V-DB-F017-3、V9 |
| §23.1 / DR-305 | `api_keys.expires_at` | `> created_at`、`<= created_at+365d+5min` | `validity_days` 1..365，缺省 90 | 服务端 `now()` 计算；DB backstop | V7、B12、V-DB-F017-4 |
| §23.1 / DR-305 | `api_keys.revoked_at` | NULL 或 `>= created_at` | 吊销置 `now()`，同事务审计；不重新启用 | 逐请求读取已提交状态 | V-DB-F017-5、V6a、B2/B4 |
| §23.1 / DR-305/307 | `api_keys.user_id`/`created_by` | FK→`users.id` RESTRICT；无 `deleted_at`/`version` | 创建要求账号存在且 ACTIVE | 停用经 join `status='ACTIVE'` 即时失效 | V-DB-F017-6、V6b、B3 |
| §22 / DR-306 | `audit_logs.api_key_label` | 新增 nullable 列，无 FK；append-only 触发器不变 | 仅快照标签；不含 hash/明文 | ADD COLUMN 不触发行触发器 | V-DB-F017-7、V4、B18 |
| §22 / DR-316 | `object_type="api_key"` 审计 | `varchar` 无 CHECK；白名单 | CREATE/UPDATE 各一条，同事务 | 失败回滚零残留 | V4、V-DB-F017-1、B18/B19 |
| §23 / DR-311 | 仅 ADMIN 端点 | 无（应用层） | `require_permission(USER_ADMIN)`；401 先于 403 | 前端隐藏不替代服务端 | V2、V3、V13 |
| D01 §1/§2 | 稳定 ID / 时间 | PK UUID `gen_random_uuid()`；timestamptz UTC | 目标定位用 UUID | 改名/复用不影响 | V9、V-DB-F017-8 |
| §27 / DR-314 | 迁移 `0014_api_keys` | upgrade 建表+增列；downgrade 逆序 | 无应用侧绕过 | 单 head、up/down/up | V-DB-F017-1…10 |

---

### 1. 验收映射（A1–A8 ↔ T42–T49）

执行环境代号：`真HTTP` = ASGI 应用 + `TestClient`；`真PG集成` = 真实 PostgreSQL + 真 HTTP；`真PG约束` = 真实 PG raw SQL / catalog 断言；`真PG并发` = `committed_engine` 两真实连接；`F002回归` = 既有 `test_auth.py`；`日志捕获` = `caplog`；`前端` = 构建 + 真实 API 集成。

| 验收 | 验证项 | 测试层 | 环境与数据 | PASS / FAIL 判据 |
| --- | --- | --- | --- | --- |
| **A1 / T42** | **V1** | 真HTTP + 真PG集成 | ADMIN 账号 + ACTIVE 目标账号；经 ADMIN 端点创建 Key；客户端清除 Cookie，仅发 `Authorization: Bearer` | PASS：读端点 200、写端点 201、`/auth/me` 身份=绑定账号且无 Cookie。FAIL：任一 401/403、身份不符、依赖 Cookie |
| **A2 / T43** | **V2** | 真HTTP + 真PG集成 | VIEWER/EDITOR/ADMIN 各绑 1 Key；构造可删/可释放对象 | PASS：VIEWER 写 403；EDITOR 写 201、删除/释放/恢复 403；ADMIN 全通过；逐格与 `ROLE_PERMISSIONS` 一致。FAIL：任一越权 |
| **A3 / T44** | **V3** | 真PG集成 | 构造缺失/空 token/格式非法/未知 hash/已吊销/已过期/账号 DISABLED | PASS：7 类一律 401 `AUTH_REQUIRED`，`details=={}`、响应等价、无泄露；无效 Key 调 ADMIN 端点 → 401（先于 403）。FAIL：任一非 401、可区分原因、泄露存在性 |
| **A4 / T45** | **V4** | 真PG集成 + 真PG约束 | 创建 Key 绑定 user01 → 用 Key 写操作 → 吊销；查 `audit_logs` | PASS：写审计 `operator_username`=user01、`api_key_label`=标签、`action=CREATE`；创建/吊销各一条 `object_type=api_key`；失败无残留。FAIL：operator 记错、缺标签、缺审计、含明文/hash |
| **A5 / T46** | **V5** | 真PG集成 + 真PG约束 + 日志捕获 | 捕获 201 明文；随后 list/detail/错误/吊销 | PASS：201 含一次性 `plaintext`；其余响应/审计/日志无明文/hash；`key_hash == sha256(明文)`；库内无明文列。FAIL：明文再现、可还原存储 |
| **A6 / T47** | **V6a/V6b** | 真PG集成 + 真PG并发 | 账号含 ≥2 Key；吊销其一；另经 `PATCH /users` 停用账号 | PASS：吊销提交后下一新请求立即 401；停用后全部 Key 401。FAIL：仍 2xx、需等待、部分失效 |
| **A7 / T48** | **V7** | 真HTTP + 真PG集成 | `validity_days` = 省略/1/90/365/366/0/-1/null/非整数 | PASS：省略→201 且 ≈90 天；1/90/365→201；366/0/-1/null/非整数→422；无永不过期路径；DB 拒绝 >365d。FAIL：缺省非 90、越界放行 |
| **A8 / T49** | **V8** | F002回归 + 真PG集成 | 运行 `test_auth.py` 全量 + 新增载体隔离用例 | PASS：F002 既有用例全绿；Cookie+无 Authorization 行为不变；纯 Bearer 豁免 CSRF；Bearer 忽略 Cookie。FAIL：任一回归、CSRF 口径变化 |

**补充验证项**

| 编号 | 项目 | 测试层 | 判据 |
| --- | --- | --- | --- |
| **V9** | 列表/详情契约形态、过滤/排序/分页、404/422 | 真PG集成 | 字段/类型/ISO-8601 正确；响应永不含 `key_hash`/明文；`q` 空或 >255→422 |
| **V10** | 仅 ADMIN 门 | 真PG集成 + 前端 | VIEWER/EDITOR→403；无凭据→401；服务端强制 |
| **V11** | 创建引用边界 | 真PG集成 + 真PG约束 | `user_id` 不存在/非 ACTIVE→422；`label` 非法→422；`label` 不唯一允许 |
| **V12** | 排除端点/方法 | 真PG集成 + 静态 | 无 PATCH/DELETE/重新启用；未定义方法→404/405 |
| **V13** | 吊销幂等语义 | 真PG集成 + 真PG约束 | 未知 id→404；已吊销→409 `already_revoked` 且不写审计；EXPIRED 未吊销→200 |
| **V14** | 认证响应等价性 | 真PG集成 | 多种无效凭据 401 响应体等价，不泄露存在性 |
| **V15** | 只读端点无写副作用 | 真PG集成 + 真PG约束 | 调用前后行数与内容不变；`logout` 带 Key 为无害 no-op |

---

### 2. 边界与并发 / 即时性用例

| 编号 | 场景 | 环境 | 判据 |
| --- | --- | --- | --- |
| **B1** | 吊销后立即 401 | 真PG并发 | 吊销提交后同一 Key 下一请求立即 401，无等待/缓存。FAIL：仍 200 |
| **B2** | 并发吊销 + 认证读取 | 真PG并发 | 吊销提交后可稳定观察 401，无「已吊销仍 200」 |
| **B3** | 账号停用 → 全部 Key 即时失效 | 真PG并发 | 停用提交后 Key1/Key2 均 401；`revoked_at` 保持 NULL |
| **B4** | 重复吊销 → 409 | 真PG集成 | 第二次 409 `already_revoked`；审计不新增、`revoked_at` 不变 |
| **B5** | 状态派生 | 真PG集成 | `REVOKED` 优先于 `EXPIRED`；过滤与派生一致 |
| **B6** | `expires_at == now()` | 真PG集成 | 视为过期 |
| **B7** | 有效期边界 1..365 | 真HTTP + 真PG集成 | 1/365 成功；366 失败；0/负/null/非整数 422 |
| **B8** | 缺省 90 天 | 真HTTP + 真PG集成 | 省略 → ≈90 天 |
| **B9** | 明文一次性 | 真PG集成 | 再次创建生成不同明文；响应无 `plaintext`/`key_hash` |
| **B10** | 创建并发唯一性 | 真PG并发 | 并发创建 hash 两两不同；重复 hash 被唯一约束拒绝 |
| **B11** | 401 先于 403 | 真PG集成 | 无效 Key→401；有效不足权限→403 |
| **B12** | Bearer 优先 | 真PG集成 | 有效 Cookie + 无效 Bearer→401；有效 Bearer + 他账号 Cookie→Bearer 身份 |
| **B13** | 非 Bearer Authorization 忽略 | 真PG集成 | `Authorization: Basic` + 有效 Cookie → 走 Cookie |
| **B14** | 格式非法前缀 | 真PG集成 | 空 token/无前缀/含非法字符 → 401 等价 |
| **B15** | 账号停用后再启用（F017-OPEN-1） | 真PG集成 | 待 Product 裁定；TD-1 记条件用例 |
| **B16** | 创建不改变账号 | 真PG集成 | user `status`/`version`/`updated_at` 不变 |
| **B17** | 列表/详情只读 | 真PG约束 | 前后行数与内容不变 |
| **B18** | 审计同事务原子性 | 真PG并发 | 成功同提交可见；失败零残留 |
| **B19** | 用 Key 写操作审计归属 | 真PG集成 | operator=绑定账号、标签=Key 标签；Cookie 路径标签 NULL |
| **B20** | 仅 ADMIN 为 ACTIVE 账号创建 | 真PG集成 | DISABLED 账号→422 |
| **B21** | GET 免 CSRF / POST 同源 | 真PG集成 | Cookie POST 跨源→403 csrf；Bearer POST 跨源放行；Cookie+Bearer 走 Bearer |
| **B22** | 降级/回滚边界 | 真PG约束 | downgrade 丢列/表；up/down/up 单 head、无残留 |

---

### 3. Cookie 认证回归清单（T49 / V8）

| 回归项 | 判据 |
| --- | --- |
| 登录成功建会话 | 200 + `csm_session`（HttpOnly/SameSite=Lax/Path=/） |
| 登录失败不可区分 | 未知用户/密码错/停用均 401 `AUTH_INVALID_CREDENTIALS` |
| 无注册端点 | `/auth/register|/signup` 404 |
| 权限矩阵（机制级） | 逐角色与 `ROLE_PERMISSIONS` 一致 |
| 停用账号登录与旧会话 | 登录 401；旧会话 401 |
| 会话过期无滑动 | 过期后 401，不续期 |
| 登出删会话 | 204 + `Max-Age=0`；`user_sessions` 行删除 |
| Cookie 属性 / 生产 Secure | 不被 F017 改变 |
| 敏感信息不泄露 | 响应/日志无 password/token/hash；新增 Key 明文/hash 亦不出现 |
| CSRF 同源口径 | Origin/Sec-Fetch-Site/allowlist 三类行为一致；Bearer 豁免为新增断言 |
| 401/403 语义 | 语义与信封不变 |
| 登录/登出流程隔离 | login/logout 仍为 Cookie 流程；带 Key 调 logout 无害 no-op |

---

### 4. 真实 PostgreSQL 证据边界与日志脱敏

- 约束/唯一/FK/CHECK/迁移/append-only 仅以真实 PostgreSQL 为证据，SQLite/Mock 不作数。
- 迁移：`upgrade head` → `downgrade 0013` → `upgrade head`，收敛单一 head，无残留。
- 约束负例 raw SQL 直插断言抛错。
- append-only：增列后 UPDATE/DELETE 仍被拒；既有行 `api_key_label` 为 NULL。
- 认证查询计划 `EXPLAIN` 命中 `uq_api_keys_key_hash`（预期）。
- 并发用 `committed_engine` 真实两连接 + 提交后最终持久化断言。
- 脱敏验证：断言 `SENSITIVE_FIELDS` 含 `api_key`/`api_key_hash`/`key_hash`/`plaintext`/`bearer`/`authorization`；`caplog` 捕获无明文/hash；响应全文扫描；审计快照扫描；DB 无明文列。

---

### 5. 环境、夹具与可观察结果

- 环境：真实 PostgreSQL + Alembic head + 生产 `create_app`（仅覆写 `get_db`）的 ASGI `TestClient`。
- 复用夹具：`test_database_url`、`pg_engine`、`db_session`、`committed_engine`、`auth_session_factory`、`auth_app`、`api_client`、`bootstrap_admin`、`make_user`、`login`、`role_client_factory` 及领域 helper。
- 拟新增夹具（实现后由 Tester 添加，属测试基础设施）：`api_key_factory`、`bearer_client`、`insert_api_key(session, **状态覆盖)`。
- 可观察结果：HTTP 状态+错误码+details；`/auth/me` 身份；状态派生；审计行字段；`api_keys` 持久化；响应/日志/审计脱敏；前端四态与一次性明文面板。

---

### 6. 未决 / 待核对项

| 编号 | 事项 | 责任 | 影响 |
| --- | --- | --- | --- |
| F017-OPEN-1（DR-317） | 停用后再启用未吊销 Key 是否恢复可用 | Product | 影响 B15；不阻塞 A6 |
| F017-OPEN-2 | 有效期措辞张力 | Product/Architect | 已收敛为「省略默认 90、显式 null/越界 422」 |
| F017-OPEN-3 | `label` 是否账号内唯一 | Product/Architect | 不影响 A1–A8；默认不唯一 |
| Contract 待定稿 | `docs/api/F017.md` 与 F002/F015 v2 | Architect | 影响 V9/V13 字面判据；TD-2 核对 |

### 7. 结论

A1–A8 ↔ T42–T49 已逐条映射到可执行判据、测试层、真 PG 环境与数据、明确 FAIL 判据；边界/并发/即时性（B1–B22）、Cookie 回归清单、真 PG 证据边界、日志脱敏、夹具与可观察结果均已建立。

**`TEST DESIGN READY`（TD-1）**。本结论仅表示方案可验证，不是测试通过，不批准实现或合并。

---

## Test Execution

- **角色**：Tester（TEST 模式，独立执行）
- **日期**：2026-10-15
- **被测版本**：`5f370b0`（`feat(F017): implement API key machine credential`），工作区干净
- **依据**：`docs/api/F017.md` v1；`docs/database/f017-api-key.md` v1（DB-D301–DB-D316）；`docs/features/F017/{product,architecture}.md`（A1–A8、DR-301–DR-318）；TD-1（V1–V15、B1–B22）；`docs/project/implementation-rules.md`；`.pi/skills/data-integrity/SKILL.md`；`docs/project/handoff.md`。
- **结论**：`READY FOR REVIEW`

### 1. 环境

| 项 | 值 |
| --- | --- |
| 数据库 | 真实 PostgreSQL **16.15**（`docker run postgres:16`，库名 `csm_test`，端口 55432，`TEST_DATABASE_URL` 指向） |
| 迁移 | Alembic head = `0014_api_keys`；会话夹具重建 `public` schema 后 `upgrade head` |
| 应用 | 生产 `create_app()`，仅覆写 `get_db`；ASGI `TestClient`（真 HTTP） |
| Python | 3.12 / SQLAlchemy 2.0.34 / psycopg 3.2.13 / alembic 1.14.1 / pytest 7.4.4 |
| Node | v24.14.0 / npm 11.9.0（Vite 5.4 / TypeScript 5.6） |
| 证据边界 | 约束/唯一/FK/CHECK/append-only/迁移/认证矩阵断言只以真 PG 执行，未使用 Mock/SQLite |

### 2. 命令与结果（独立复跑，不复用开发者结果）

| 命令 | 结果 |
| --- | --- |
| `pytest tests/integration/test_api_keys.py tests/integration/test_api_key_constraints.py` | 20 passed |
| `pytest tests/integration/test_migrations.py` | 4 passed, 1 skipped |
| `pytest tests/integration/test_f017_migrations.py`（新增，0014 专属） | 1 passed |
| `pytest tests/integration/test_f017_tester_acceptance.py`（新增，独立验收） | 15 passed（连跑 3 次稳定） |
| `pytest tests/integration/test_auth.py` + F017 全集（F002 Cookie 回归） | 62 passed |
| **`pytest -q`（后端全量）** | **617 passed, 2 skipped**（2 次全量 + 1 次含新增用例；skip 为既有：F016 已禁用、V3b 因连接角色为 superuser） |
| `npm run typecheck` | 通过（0 错误） |
| `npm run build` | 通过 |
| `npm run smoke:client` | 276 passed, 0 failed（含 F017 机制级 15 例；既有 261 例无回归） |

> 新增测试代码（属 Tester 范围，`backend/tests/**`）：`test_f017_tester_acceptance.py`、`test_f017_migrations.py`。未修改业务实现、Schema、契约或产品文档。

### 3. 验收映射（A1–A8 ↔ T42–T49 / V1–V15）

| 验收 | V | 判据要点 | 证据（真 PG + 真 HTTP） | 结果 |
| --- | --- | --- | --- | --- |
| A1/T42 | V1 | 无 Cookie + 有效 Bearer → 读 200 / 写 201；`/auth/me` 身份=绑定账号 | test_api_keys.py::test_bearer_identity_and_ignores_cookie；test_f017_tester_acceptance.py::test_bearer_priority_over_cookie | **PASS** |
| A2/T43 | V2 | VIEWER/EDITOR/ADMIN 逐格与 `ROLE_PERMISSIONS` 一致；越权 403 | test_api_keys.py::test_api_keys_permission_matrix（EDITOR 写 201、`/audit` 403） | **PASS** |
| A3/T44 | V3 | 缺失/空/格式非法/未知 hash/已吊销/已过期/账号 DISABLED → 401 且等价；无效 Key→401 先于 403 | test_api_keys.py::test_invalid_and_revoked_keys_are_equivalent_401、test_expired_and_disabled_bound_account_are_401；tester::test_auth_error_responses_are_equivalent_and_401_before_403 | **PASS** |
| A4/T45 | V4 | Key 写审计 operator=绑定账号+标签；创建/吊销各一条 `object_type=api_key` | test_api_keys.py::test_audit_semantics | **PASS** |
| A5/T46 | V5 | 明文仅 201 一次；库仅 `key_hash`；其余出口无明文/hash；日志无泄露 | test_api_keys.py::test_create_returns_plaintext_once；tester::test_responses_and_logs_never_expose_plaintext_or_hash、test_database_has_no_plaintext_column | **PASS** |
| A6/T47 | V6a/V6b | 吊销提交后下一请求即 401；停用后全部 Key 401 | test_api_keys.py::test_invalid_and_revoked_keys_are_equivalent_401、test_expired_and_disabled_bound_account_are_401；tester::test_reenable_account_restores_unrevoked_key | **PASS** |
| A7/T48 | V7 | 省略→≈90；1/90/365→201；0/负/null/366/非整数→422；DB 拒 >365d | test_api_keys.py::test_create_validation、test_default_validity_is_90_days；constraints::test_api_key_check_constraints | **PASS** |
| A8/T49 | V8 | F002 用例全绿；Cookie 行为不变；Bearer 免 CSRF；Bearer 忽略 Cookie | test_auth.py 全绿；test_api_keys.py::test_bearer_requests_are_csrf_exempt；见 §6 | **PASS** |

| 补充 | 判据要点 | 证据 | 结果 |
| --- | --- | --- | --- |
| V9 | 列表/详情形态、过滤/排序/分页、404/422；永不含 hash/明文 | test_api_keys.py::test_list_filters_sort_and_detail；tester::test_responses_and_logs_never_expose_plaintext_or_hash | **PASS** |
| V10 | 仅 ADMIN；VIEWER/EDITOR 403、匿名 401 | test_api_keys.py::test_api_keys_permission_matrix | **PASS** |
| V11 | `user_id` 不存在/DISABLED/非 UUID→422；label 非法→422；label 不唯一允许 | test_api_keys.py::test_create_validation | **PASS** |
| V12 | 无 PATCH/DELETE/restore/enable（404/405） | test_api_keys.py::test_no_update_delete_restore_endpoints | **PASS** |
| V13 | 未知 id→404；重复吊销→409 `already_revoked` 且不写审计；EXPIRED 可吊销 | test_api_keys.py::test_revoke_semantics；tester::test_concurrent_revoke_yields_single_success | **PASS** |
| V14 | 多种无效凭据 401 响应体等价，不泄露存在性 | tester::test_auth_error_responses_are_equivalent_and_401_before_403 | **PASS** |
| V15 | 只读端点无写副作用；带 Key `logout` 无害 no-op | tester::test_read_only_endpoints_have_no_write_side_effects | **PASS** |

### 4. 边界与并发/即时性（B1–B22）

| 编号 | 场景 | 证据 | 结果 |
| --- | --- | --- | --- |
| B1 | 吊销后立即 401 | test_api_keys.py::test_invalid_and_revoked_keys_are_equivalent_401 | **PASS** |
| B2 | 并发吊销 + 认证读取 | tester::test_concurrent_revoke_yields_single_success（两真连接：恰一 200、一 409；UPDATE 审计仅 1 条） | **PASS** |
| B3 | 账号停用 → 全部 Key 即时失效，`revoked_at` 保持 NULL | test_expired_and_disabled_bound_account_are_401；tester::test_reenable_account_restores_unrevoked_key（断言 `revoked_at IS NULL`） | **PASS** |
| B4 | 重复吊销 → 409，审计不新增、`revoked_at` 不变 | test_revoke_semantics；tester::test_concurrent_revoke_yields_single_success | **PASS** |
| B5 | 状态派生 REVOKED 优先于 EXPIRED；过滤一致 | tester::test_status_derivation_revoked_priority_and_expiry_boundary | **PASS** |
| B6 | `expires_at <= now` 视为过期 | tester::test_expires_at_equals_now_is_expired（详情 EXPIRED + Bearer 401） | **PASS** |
| B7 | 有效期边界 1/365 成功；366/0/负/null/非整数 422 | test_create_validation | **PASS** |
| B8 | 缺省 90 天 | test_default_validity_is_90_days（`expires-created == 90d`） | **PASS** |
| B9 | 明文一次性；再次创建生成不同明文 | test_create_returns_plaintext_once；tester 脱敏用例 | **PASS** |
| B10 | 并发创建 hash 两两不同；重复 hash 被唯一约束拒 | tester::test_concurrent_create_produces_distinct_hashes（5 真连接）；constraints::test_api_key_key_hash_unique | **PASS** |
| B11 | 401 先于 403 | test_invalid_key_is_401_before_403；tester V14 | **PASS** |
| B12 | Bearer 优先；有效 Cookie+无效 Bearer→401；有效 Bearer+他账号 Cookie→Bearer 身份 | tester::test_bearer_priority_over_cookie；test_bearer_identity_and_ignores_cookie | **PASS** |
| B13 | 非 Bearer Authorization 忽略，走 Cookie | tester::test_non_bearer_authorization_falls_back_to_cookie | **PASS** |
| B14 | 空 token/无前缀/非法字符 → 401 等价 | tester V14；test_invalid_and_revoked_keys_are_equivalent_401 | **PASS** |
| B15 | 停用后再启用（F017-OPEN-1 默认）：未吊销 Key 恢复可用、不自动吊销 | tester::test_reenable_account_restores_unrevoked_key | **PASS** |
| B16 | 创建不改变账号 `status`/`version`/`updated_at` | tester::test_create_does_not_change_account | **PASS** |
| B17 | 列表/详情只读，行数内容不变 | tester::test_read_only_endpoints_have_no_write_side_effects | **PASS** |
| B18 | 审计同事务原子性：成功同提交可见；失败零残留 | test_audit_semantics（成功）；tester::test_failed_create_leaves_zero_residue、test_concurrent_revoke_yields_single_success | **PASS** |
| B19 | 用 Key 写操作审计 operator=绑定账号、标签=Key 标签；Cookie 路径 NULL | test_audit_semantics | **PASS** |
| B20 | DISABLED 账号创建→422 | test_create_validation | **PASS** |
| B21 | GET 免 CSRF；Cookie 跨源 403 csrf；Bearer 跨源放行 | test_bearer_requests_are_csrf_exempt；test_auth.py::test_csrf_rejects_cross_origin 等 | **PASS** |
| B22 | downgrade 丢列/表；up/down/up 单 head 无残留 | test_f017_migrations.py（0013 窄降级）；test_migrations.py（全链 up/down/up） | **PASS** |

### 5. 数据库 / 约束 / 迁移结果（真 PG）

- **约束拒绝（V-DB-F017-2）**：非法 `key_hash` 格式/长度、空/纯空白 `label`、`expires_at <= created_at`、`expires_at > created_at+366d`、`revoked_at < created_at` 均抛 `DBAPIError`；合法边界（`+365 days`、`revoked_at == created_at`、255 字符 label）通过 → **PASS**。
- **唯一/FK（V-DB-F017-3/4）**：重复 `key_hash` 被 `uq_api_keys_key_hash` 拒；删除持 Key 用户被 FK RESTRICT 拒 → **PASS**。
- **append-only + 增列（V-DB-F017-5/7/8）**：NULL `api_key_label` 允许、空串/纯空白被 CHECK 拒；增列后 `UPDATE`/`DELETE audit_logs` 仍被触发器拒；`object_type='api_key'` 可插入；`id` 默认 UUID → **PASS**。
- **索引与无多余索引（V-DB-F017-9）**：`ix_api_keys_user_id`、`ix_api_keys_created_by` 存在；无 `expires_at`/`label` 索引；`EXPLAIN` 在禁用 seqscan 时命中 `uq_api_keys_key_hash` 等值 → **PASS**。
- **迁移（V-DB-F017-1/B22）**：`alembic heads` 唯一 `0014_api_keys`；`downgrade 0013_search_indexes` 后 `api_keys` 表、两条索引、`audit_logs.api_key_label` 列与 CHECK 全部消失且既有对象保留；re-upgrade 恢复 → **PASS**。
- 未验证：认证计划在**代表性大数据量**下的 `EXPLAIN (ANALYZE)` 成本基线（TD-1 §4 预期项）本次仅在 50 行小表 + `enable_seqscan=off` 下验证索引可用，未做规模基线。

### 6. Cookie 认证回归（T49 / V8）

`test_auth.py`（18 用例）在真 PG + 真 HTTP 下全绿：登录建会话、登录失败不可区分、无注册端点、逐角色权限矩阵、停用账号登录/旧会话、会话过期无滑动、登出删会话、Cookie 属性/生产 Secure、敏感信息不泄露、CSRF 同源/Sec-Fetch-Site/allowlist、401/403 信封。新增断言：纯 Cookie POST 跨源仍 403 `csrf`；Bearer POST 跨源放行；同一请求有效 Cookie + 无效 Bearer → 401（Bearer 优先、不回退 Cookie）。**Cookie 行为与 F002 契约一致，无回归 → PASS**。

### 7. 接口 / 前端 / 集成结果

- **接口**：四端点（list/detail/create/revoke）成功/错误/权限/分页/排序/过滤/48x 语义与 `docs/api/F017.md` v1 逐项一致；响应 `ApiKeyRow` 字段与类型、ISO-8601 UTC 正确；`key_hash`/明文从不出现 → **PASS**。
- **脱敏**：`SENSITIVE_FIELDS` 含 `api_key/api_key_hash/key_hash/plaintext/bearer/authorization`；201 明文与 `sha256(明文)` 在 list/detail/revoke/错误响应全文及 `caplog` 捕获文本中均未出现；DB 无明文列 → **PASS**。
- **前端**：`typecheck`/`build`/`smoke:client`（276 passed）通过；创建响应 `plaintext` 仅创建面板一次性展示（`navigator.clipboard` 复制，无 `localStorage`/`console` 持久化或打印）；错误解析覆盖 401/403/404/409/422 且 409 `already_revoked` 不静默重试 → **PASS（机制级）**。
- **集成**：后端真 PG 端到端（真 HTTP + DB 终态）已覆盖；前端 `smoke:client` 为契约级 Mock 客户端，非真实 API。

### 8. Defects

| ID | Severity | Layer | Location | 证据 | 期望 vs 实际 | Owner | 必须修复 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| OBS-F017-1 | LOW（非 F017 缺陷） | Test/DB 并发 | `backend/tests/integration/test_ip_addresses.py::test_concurrent_gateway_change_and_allocation` | 首次全量运行 1 failed；单跑 3/3 通过、该文件单跑 38/38 通过、随后两次全量均 617 passed | 期望并发用例稳定；实际为偶发 `['gateway','allocated']` 双成功 | 既有 IP 分配并发用例（非本 Feature 改动文件，`git show --stat 5f370b0` 未触及） | 否（不阻塞 F017；建议独立跟进 flaky） |

- F017 范围内**未发现必须修复的实现缺陷**。

### 9. 未验证项

| 项 | 状态 | 理由 / 替代证据 |
| --- | --- | --- |
| 真实浏览器 DOM/E2E（弹层焦点、剪贴板、窄屏、一次性明文关闭即清除的视觉行为） | **NOT TESTED** | 环境无浏览器/无 Playwright 驱动；替代证据：`typecheck`/`build`/`smoke:client` 机制级断言 + 后端契约集成。 |
| 前端对真实后端的端到端联调 | **NOT TESTED** | `smoke:client` 使用 Mock 客户端；后端四端点已由真 PG 集成覆盖，跨端契约一致性由同一 Contract 判据保证，但未启动真实前后端串联。 |
| 认证查询计划规模基线 `EXPLAIN (ANALYZE)` | **NOT TESTED** | 仅小表验证索引可用；未构造代表性数据量。 |
| V3b `pg_trgm` 非 superuser 安装路径 | **SKIPPED（既有）** | 本次连接角色为 superuser，`test_migrations.py` 按既有规则 skip；与 F017 无关。 |
| 前端 `user_id`/`status` 过滤与服务端真实组合 | **PARTIAL** | 机制级断言覆盖查询串构造；服务端组合过滤由后端 `test_list_filters_sort_and_detail` 覆盖，未做前端→真实 API 串联。 |

### 10. 结论

A1–A8（T42–T49）/ V1–V15 在真实 PostgreSQL + 真 HTTP 下逐项 **PASS**；B1–B22 全部 **PASS**；F002 Cookie 回归无回归；约束/唯一/FK/append-only/迁移以真 PG 为证据；日志/响应/审计/DB 脱敏成立。无必须修复缺陷；未验证项已明确列出且不影响 F017 验收（浏览器 DOM 与真实前后端串联为替代证据已说明）。

**`READY FOR REVIEW`**。本报告不批准合并；Merge Gate 由协调器按 `docs/project/git-workflow.md` 执行。

### 11. Git 声明

本次仅执行以下**只读** Git 命令，未执行任何 `add`/`commit`/`switch`/`merge` 或其他改变 Git 状态的命令：

```text
GIT: git rev-parse --short HEAD
GIT: git status --short
GIT: git log --oneline -3
GIT: git show --stat HEAD
```
