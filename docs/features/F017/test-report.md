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

_（待 IMPLEMENTATION 完成后由 Tester 的 TEST 模式填充；当前未执行。）_