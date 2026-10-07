# F002 认证、初始账号与权限横切 — ARCHITECTURE 阶段报告

- **Task**：F002（FEATURE，P0，M1）— Architect，Feature 设计模式
- **Status**：`READY FOR DESIGN`（2026-10-06；协调器核验后持久化）
- **Basis**：requirements-v3.md revision 3（§21–§23、§25–§27、§29–§31、§35）；docs/features/F002/product.md（A1–A7）；docs/features/F001/architecture.md（工程基线）；docs/database/f001-baseline.md（DB-D1–D12）；plan_revision 4 F002 条目（已批准）。
- **结论属性**：本报告为设计输入，交 DATABASE/TEST_DESIGN Gate；Contract 定稿与最终签核在 CONTRACT Gate。选型均为 PROPOSED（D02 认证部分），由 Architect 签核、Database 联合确认。

## 1. 方案摘要

F002 只交付请求级横切：认证、初始账号引导、权限矩阵执行、操作者上下文、401/403/409 与统一错误信封、敏感字段处理、最小登录前端。业务对象属 F003+。

### 1.1 认证机制

| 维度 | 选择 | 理由 |
| --- | --- | --- |
| 账号模型 | 本地账号 username+password | §23 CONFIRMED |
| 密码哈希 | **argon2id**（argon2-cffi，库默认参数） | PHC 推荐；无 bcrypt 72 字节截断缺陷；PHC 串自带参数可升级；库做常量时间比较 |
| 会话 | **服务端不透明会话（DB 存储）** | 一期无 Redis（§29）；可即时登出与停用即时失效（§21/§23）；无 JWT 吊销难题 |
| 令牌 | `secrets.token_urlsafe(32)`，仅存 **SHA-256 哈希** | DB 泄露不暴露可用令牌 |
| 传输 | HttpOnly + SameSite=Lax + Path=/（生产 Secure）Cookie `csm_session` | 同源经 Nginx；JS 不可读 |

会话参数：绝对过期 `expires_at`（默认 `SESSION_TTL_HOURS=12` 可配）；不做滑动续期（避免每请求写库）；登出删除会话行；请求时 join users 校验 `status='ACTIVE'`，停用立即 401。CSRF：SameSite=Lax + 不安全方法的 Origin/Sec-Fetch-Site 同源校验（PROPOSED 纵深防御）。登录限流不在本期（无 Redis，记 NOTE）。

### 1.2 端点（`/api/v1/auth/*`，沿用 F001 api_v1_router）

| Endpoint | Method | 语义 |
| --- | --- | --- |
| `/api/v1/auth/login` | POST | 校验凭据，创建会话，Set-Cookie，返回操作者；凭据错误/停用统一 401 |
| `/api/v1/auth/logout` | POST | 删除会话清 Cookie；204 |
| `/api/v1/auth/me` | GET | 当前操作者+权限集合；未认证 401 |

无注册端点（A3）。

### 1.3 初始 ADMIN 引导

- 一次性 CLI `python -m app.cli.bootstrap_admin`，Compose 一次性服务 `bootstrap` 执行（依赖 migrate 成功，backend 依赖 bootstrap 成功）。**迁移只建表不写业务数据**（DB-D7）。
- `INITIAL_ADMIN_USERNAME`/`INITIAL_ADMIN_PASSWORD` 经 .env 注入，不入仓；不硬编码默认凭据。
- 幂等：事务内"存在任何用户（含停用）→ no-op 退出 0"；空表+变量齐备→创建 ADMIN（role=ADMIN、status=ACTIVE、version=1）；空表+变量缺失→非零退出明确提示。`users.username` 唯一约束兜底并发。

### 1.4 权限矩阵服务端执行

- `Role` StrEnum {VIEWER,EDITOR,ADMIN}；DB 存 VARCHAR+CHECK（不用原生 ENUM）。
- `Permission` 能力枚举与 §23 表格逐行对应：READ、VIEW_ACTIVITY（VIEWER+）；WRITE、IMPORT（EDITOR+）；DELETE_OBJECT、RELEASE_IP、VIEW_DELETED、RESTORE、USER_ADMIN、AUDIT_READ（仅 ADMIN）。显式 frozenset 映射 `ROLE_PERMISSIONS`，不假设隐式继承；EDITOR 解绑属 WRITE，释放 IP 属 RELEASE_IP。
- 执行点：FastAPI 依赖工厂 `require_permission(permission)`——先解析会话/操作者（未认证 401），无权限 403。业务路由自 F003 起显式挂载。
- A4 的 403 证据：集成测试以生产依赖 `require_permission(USER_ADMIN)` 挂载受保护测试路由，断言 VIEWER/EDITOR 403；首个真实 ADMIN-only 业务端点在 F003/F015（风险 R1）。

### 1.5 操作者上下文

`get_current_operator` 依赖：Cookie→会话哈希→join users（ACTIVE+未过期）→`Operator{user_id, username, role}`；经 `request.state.operator` 供 F003 Audit 取 operator。操作者持久表示（user_id vs username）与 F003 Audit 表对齐（待核对项；用户停用不删行）。

### 1.6 统一错误信封（F001 预留，此处定稿基础形态）

```json
{ "error": { "code": "STRING_CODE", "message": "human readable", "details": { } } }
```

| HTTP | code | 触发 |
| --- | --- | --- |
| 401 | `AUTH_REQUIRED` | 无会话/过期 |
| 401 | `AUTH_INVALID_CREDENTIALS` | 凭据错误或停用（不区分账号存在性） |
| 403 | `FORBIDDEN` | 已认证缺权限 |
| 409 | `VERSION_CONFLICT` | 乐观锁过期（details.current_version 供刷新提示） |
| 404 | `NOT_FOUND`；422 `VALIDATION_ERROR`（字段级明细）；500 `INTERNAL_ERROR`（不含堆栈/凭据） |

409 语义：可编辑实体带整数 `version`；更新请求回传所基于 version；过期 409；不静默重试覆盖。端到端落 F003。

### 1.7 敏感字段策略

响应：ORM User 与 Schema 分离，任何响应不含 `password_hash`；登录错误不透露账号存在性。日志：`app/core/logging.py` 脱敏 Filter（SENSITIVE_FIELDS={password,token,secret,authorization,cookie,session,set-cookie,initial_admin_password}）；auth 端点绝不记录请求体；错误日志脱敏后输出。

### 1.8 前端最小接入（frontend=true）

登录页（username/password→POST /auth/login，credentials include）；启动 GET /auth/me 恢复登录态；client.ts 扩展（Cookie、错误信封解析、仅 401 清态回登录页、403/409 明确呈现、不静默重试）；登出按钮。不新增业务页面/路由库。

## 2. 技术决策

| ID | 决策 | 类别 |
| --- | --- | --- |
| DR-07 | argon2id 密码哈希 | PROPOSED（D02） |
| DR-08 | 服务端不透明会话 DB 存储，HttpOnly+SameSite=Lax Cookie，令牌仅存 SHA-256 哈希 | PROPOSED（D02） |
| DR-09 | Role+Permission 显式映射，require_permission 依赖执行 | PROPOSED |
| DR-10 | 统一错误信封与 401/403/409 语义 | PROPOSED |
| DR-11 | 整数 version 乐观锁，请求回传 version，过期 409（端到端 F003） | PROPOSED（D02） |
| DR-12 | 初始 ADMIN 由一次性 CLI+Compose bootstrap 幂等创建，迁移不写业务数据 | PROPOSED |
| DR-13 | F002 前端=最小认证壳，frontend=true | PROPOSED |
| DR-14 | 登录标识 username（3–64、小写 [a-z0-9._-]、无内部空白、大小写不敏感唯一） | PROPOSED（D02） |
| DR-15 | 新表 users/user_sessions，不触及 F003 业务横切 | PROPOSED |
| DR-16 | 连接池沿用 F001 DB-D8 骨架 | CONFIRMED（骨架） |

## 3. Implementation Layers

database=true（users/user_sessions 迁移）；backend=true（认证/会话/权限/错误/日志/bootstrap）；frontend=true（登录壳）；**api_required=true**。

## 4. API 草案（Contract 草案，定稿于 CONTRACT Gate，路径 docs/api/F002.md）

**POST /api/v1/auth/login**（无需认证）：Request `{"username": string, "password": string}`；200 `{"user": {"id": uuid, "username": string, "role": enum, "status": enum, "permissions": string[]}, "expires_at": ISO-8601}` + Set-Cookie；401 AUTH_INVALID_CREDENTIALS；422 VALIDATION_ERROR。
**POST /api/v1/auth/logout**（需认证）：204；无会话 401。
**GET /api/v1/auth/me**（需认证）：200 同 user；401。
错误统一信封；分页/排序/软删可见性不适用（账号停用非软删）。

## 5. 数据库影响（详细交 DATABASE Gate）

**users**：id UUID PK（gen_random_uuid()，PG13+ 核心；形态待与 D01/F003 稳定 ID 对齐）、username varchar(64) NOT NULL UNIQUE（服务层归一化小写存）、password_hash varchar(255) NOT NULL（argon2 PHC）、role varchar(16)+CHECK、status varchar(16) DEFAULT 'ACTIVE'+CHECK、version integer DEFAULT 1、created_at/updated_at timestamptz NOT NULL DEFAULT now()（UTC）；**无 deleted_at**（停用非软删，§21）。

**user_sessions**：id UUID PK、user_id UUID FK→users.id NOT NULL+索引、token_hash varchar(64) NOT NULL UNIQUE（SHA-256 hex）、created_at、expires_at NOT NULL、last_seen_at NULL。

命名沿用 DB-D6；downgrade 对称可逆（新表无历史数据）；真实 PG up/down/up。会话过期惰性判定+登出删除，不预建清理任务。bootstrap 在应用侧非迁移（理由：迁移仅 Schema、凭据运行时注入、幂等属业务条件、与 F001 migrate 一次性服务模式一致）。

## 6. 验证策略（A1–A7 → 方法，真实 PG）

| 验收 | 方法 |
| --- | --- |
| A1 | bootstrap 后登录成功得 Cookie；错误密码 401 非 5xx；响应/日志无凭据明文 |
| A2 | 干净库 bootstrap→恰一 ADMIN；重复 no-op；仓库无真实凭据（静态） |
| A3 | 路由清单断言无注册端点；/auth/register 404/405 |
| A4 | 未认证 401 AUTH_REQUIRED；测试挂载 require_permission(USER_ADMIN) 路由，VIEWER/EDITOR 403 |
| A5 | 捕获日志断言无 password/令牌明文；响应体扫描 |
| A6 | 机制级：过期 version→409 VERSION_CONFLICT+current_version；无静默覆盖（业务端到端 F003/T26） |
| A7 | T25/T26 认证/权限子集映射为 F002 用例；完整回归待 F003 |

补充：Compose 冒烟验证 migrate→bootstrap→backend 链路与登录；迁移 up/down/up。

## 7. 风险与待核对项

交 Database：①users.id UUID 与 D01/F003 稳定 ID 对齐；②varchar+CHECK 确认与 ck_ 命名；③user_sessions 索引/FK 删除行为；④迁移可逆性。
交 Tester：①bootstrap 幂等与空表缺凭据非零退出可测性；②httpx Cookie 断言与日志捕获；③A4 测试挂载路由作为 403 证据的充分性；④A6 机制级口径。
其它：R1（MEDIUM）F002 无真实 ADMIN-only 业务端点，403 依赖测试挂载路由（首个真实路径 F003）；R2（LOW）CSRF 残余以 SameSite+Origin 校验缓解、登录限流未实现；R3（LOW）新增 argon2-cffi 依赖需锁定。
DR-14 登录标识字符集与 SESSION_TTL 默认值属 D02 专业签核（需求未指定，无已确认规则冲突）。

## 8. Issues / Next

1. 协调器已持久化本报告并置 implementation.architecture=COMPLETE。
2. DATABASE Gate：§5 表设计+§7 Database 事项签核。
3. TEST_DESIGN Gate：A1–A7 用例可执行性、R1/A6 口径。
4. 二者完成后 CONTRACT Gate 定稿签核 docs/api/F002.md → READY FOR IMPLEMENTATION。

## 最终设计定稿（CONTRACT Gate）

- 签核者：Architect；日期：2026-10-06；设计结论：`READY FOR IMPLEMENTATION`
- 核对的 Database Design：`docs/database/f002-auth.md` v1（DB-D13–DB-D19）
- 核对的 Test Design：`docs/features/F002/test-report.md` TD-2（V1–V9 / B1–B21）
- 上游依据：requirements-v3.md revision 3；F002 product.md（A1–A7）；plan_revision 4（已批准）
- 覆盖范围：F002 请求级横切——认证机制、初始 ADMIN 引导、权限矩阵执行、操作者上下文、401/403/409 与统一错误信封、敏感字段处理、最小登录前端；users/user_sessions Schema 与迁移 0002。

### Contract

`docs/api/F002.md` v1 = **READY**（Endpoint /api/v1/auth/login|logout|me、Request/Response Schema、错误语义与统一信封、Cookie 属性、权限矩阵引用、无注册端点、401/403/409 边界）。签核：Architect，2026-10-06。

### 一致性核对（摘要）

- A1–A7 ↔ DR-07–DR-16 ↔ DB-D13–D19 ↔ TD-2 V/B 全部一致。
- UUID PK：DB-D13 先行落地 PG gen_random_uuid()，F003 起业务主键沿用。
- username：DR-14 ↔ DB-D14 单列归一化 + UNIQUE + ck_users_username_format。
- role/status：varchar + CHECK（DB-D15）。
- FK：DB-D16 ON DELETE RESTRICT + 显式索引，符合 §21。
- 迁移：DB-D17 up/down 对称、单一 head、真库 up/down/up。
- bootstrap：应用侧 CLI（DR-12/DB-D17），CLI 形态本期定稿。
- 错误码：本 Gate 定稿（AUTH_REQUIRED / AUTH_INVALID_CREDENTIALS / FORBIDDEN / VERSION_CONFLICT / VALIDATION_ERROR / NOT_FOUND / INTERNAL_ERROR）。
- CSRF：SameSite=Lax（主）+ 不安全方法同源校验（纵深），本期实现；TD-2 B17 转可执行，TD-2 不升版。
- A4/A6 维持机制级口径，真实业务端点归 F003。
- 停用账号既有会话返回 AUTH_REQUIRED；登录停用账号为 AUTH_INVALID_CREDENTIALS。

### D02 认证部分签核

认证机制（argon2id + 服务端不透明会话 + 令牌仅存 SHA-256 哈希）、初始账号（一次性 CLI 幂等引导）、版本冲突与错误语义（整数 version + 409 VERSION_CONFLICT + 统一信封）、敏感字段处理（响应排除 password_hash、日志脱敏）、乐观锁版本列（users.version）——**签核完成**。连接池沿用 F001 DB-D8（DR-16）。

### D01 稳定 ID 协调义务

F002 首次落地 PG 原生 UUID 稳定 ID 形态（DB-D13）。**F003 起业务对象主键须沿用该形态**并写入 D01 共享约定；操作者 user_id 须与 F003 Audit 对齐。建议将「稳定 ID = PG UUID（gen_random_uuid()，不启用 pgcrypto/uuid-ossp）」作为 D01 已定输入纳入 F003 设计。

### 实现范围

- **Backend**：users/user_sessions 模型与迁移 0002；argon2id 哈希；会话服务；require_permission 依赖与操作者上下文；统一错误处理器与错误码；日志脱敏 Filter；同源（CSRF）守卫；bootstrap CLI；Compose bootstrap 服务；Settings（SESSION_TTL_HOURS、INITIAL_ADMIN_*、AUTH_ALLOWED_ORIGINS、APP_ENV 控制 Secure Cookie）；认证测试夹具。
- **Frontend**：登录页；启动 GET /auth/me 恢复登录态；client.ts 扩展（credentials、错误信封解析、401 清态回登录页、403/409 明确呈现、不静默重试）；登出。

### bootstrap CLI 形态（定稿）

入口 `app/cli/bootstrap_admin.py`，函数 `run(settings=None) -> int`，`main()` 包装 `raise SystemExit(main())`；CLI `python -m app.cli.bootstrap_admin`；Compose 一次性服务 `bootstrap`（depends_on migrate completed；backend depends_on bootstrap completed）。退出码：0 创建或幂等 no-op；2 空表且凭据缺失/空白（stderr 提示不写行）；1 其它错误。幂等顺序：先判「存在任何用户→no-op exit 0」再校验凭据；并发以 uq_users_username 兜底。

### 边界

不实现业务对象端点与完整 T25/T26 回归（F003）、Audit 写路径（F003）、用户管理 UI（F015）、登录限流（本期 NOT_REQUIRED）；Feature 通过 ≠ §32 上线授权。
