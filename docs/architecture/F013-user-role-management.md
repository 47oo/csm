# F013 用户与角色管理 — 架构方案

> Status: READY FOR IMPLEMENTATION
> Document Type: Feature Architecture
> Feature: F013（Epic E8，P0，根 Feature）
> 依据：`requirements-v2.md` §2.1/§3.1/§4.9/§9.1、§10 场景 72–81（BQ-V/BQ-W）；
>      `domain-model.md` §2.1；ADR-001…ADR-005
> 关联 Contract：`docs/api/F013.md`
> 创建日期：2026-09-25

本文件只记录实现层面的架构方案。产品/领域事实以 `docs/product/` 为准；技术栈、数据库、API、部署、历史审计载体以 ADR 为准。标记：`CONFIRMED` / `PROPOSED` / `OPEN`。

---

## 1. 方案摘要

F013 在既有 ADR 架构内新增一个横向模块「平台访问控制」，不引入新框架，不新增受管资源。交付物：

1. 平台自建用户与角色的增删改、单一角色分配、启/禁用、删除；
2. 登录/登出/会话，自助改密与管理员重置；
3. 口令策略与哈希；
4. 用户/角色管理操作审计（append-only，不并入受管资源历史）；
5. 初始化建表 + 首个平台管理员预置；
6. 供 F001/F002/F005/F006/F007/F012 复用的**统一「角色 / 操作者解析 + 会话」基础**（FastAPI 依赖项）。

用户与角色是平台访问控制主体，**不属于受管资源**（`domain-model.md` §2.1）：无集群归属、不参与资源唯一性/分配/逐项先删规则，不写资源历史，只写操作审计。

---

## 2. 模块边界

### 2.1 后端模块（Python 3.12 + FastAPI，ADR-001）

| 模块 | 职责 | 明确的非职责 |
| --- | --- | --- |
| `app.auth`（认证/会话） | 登录、登出、当前用户、会话建立/失效；`csm_session` Cookie 管理；解析当前操作者 | 不承载用户维护；不做组织认证（P0 排除） |
| `app.users`（用户与角色） | 用户列表/新增/详情/修改（用户名、角色）/删除；禁用/启用；重置口令；角色枚举 | 不做登录会话；不改产品规则 |
| `app.security.password`（口令） | 口令策略校验、Argon2id 哈希与校验 | 不做找回/过期/MFA（P0 排除） |
| `app.audit`（审计） | append-only 审计写入接口（被用户/角色操作调用） | 不写/不查**受管资源历史**；F013 不提供审计查询 API |
| `app.bootstrap`（初始化预置） | 幂等初始化建表入口 + 首个管理员预置 + 方案保留用户名 | 不做迁移（P0 无 Alembic，ADR-002） |
| `app.security.principal`（复用基础） | `get_current_user` / `require_roles(*roles)` 依赖；`Principal` 值对象 | 不实现各受管对象的业务授权（由各对象 Feature 实施） |

模块依赖方向：`users → security.password`、`users → audit`、`auth → security.principal`、`auth → security.password`、`bootstrap → users/security/audit`。禁止受管对象模块反向依赖 `users`（只依赖 `security.principal`）。

### 2.2 复用基础（供 F001/F002/F005/F006/F007/F012）`CONFIRMED`（F013 scope）

后端暴露稳定接口，不通过复制实现：

- `Principal`：`{ user_id:int, username:str, role:Literal["viewer","maintainer","admin"], must_change_password:bool, status:Literal["enabled","disabled"] }`。
- `get_current_user(request) -> Principal`：每个受保护请求从会话解析操作者；**角色与状态每次从数据库解析，不从 token 缓存**，保证「角色分配后新操作按新角色鉴权」「禁用后不再可用」（§4.9.4）。
- `require_roles(*roles) -> Dependency`：给定角色集合，越权返回 403。
- `require_password_changed`：`must_change_password=true` 时拦截非改密类接口（见 §4.4）。
- `audit.write(...)`：append-only 写入函数签名稳定（见 §2.3）。

各受管对象 Feature 直接依赖上述接口实施本对象鉴权与操作者解析，**不自行实现登录/会话/角色判定**（避免重复与漂移）。

### 2.3 审计写入接口（被跨 Feature 复用）

`app.audit.write(actor: Principal | None, action: str, target_type: str, target_id: str | None, target_key_snapshot: str | None, change: dict, result: "success"|"failure")`

- `actor=None` 仅用于初始化预置等系统动作；此时 `actor_username_snapshot` 记 `"system"`。
- 审计行 append-only，绝不 update/delete（ADR-005）。
- 用户/角色管理动作约定 `target_type="user"`。

### 2.4 前端页面 / 路由 / 状态（Vue 3 + TS + Vite + Element Plus，ADR-001）

| 区域 | 内容 |
| --- | --- |
| 登录页 `/login` | 用户名 + 口令；错误提示；已登录访问则跳转首页 |
| 首登改密页 `/change-password`（强制） | `must_change_password=true` 时不可绕过进入其它页面 |
| 自助改密 | 可从用户菜单进入，复用改密表单组件 |
| 用户管理页 `/admin/users` | 列表（分页/筛选）、新增、编辑（角色/用户名）、删除、重置口令、禁用/启用；仅管理员可见可进 |
| 路由守卫 | 未登录跳 `/login`；非管理员访问 `/admin/*` 拒绝；`must_change_password` 强制跳改密页 |
| Pinia `useAuthStore` | 当前用户/角色/`must_change_password`；登录、登出、刷新 `me` |
| axios | 携带 Cookie（`withCredentials`）；统一处理 401→跳登录、403→提示、problem+json 字段级错误、409→保留输入提示刷新 |

前端权限仅用于导航/隐藏，**不作为安全边界**；最终由服务端校验。

### 2.5 与后续 Feature 的接口边界

- F001–F012 复用 §2.2 依赖与 §2.3 审计写入；不修改 F013 表结构即可接入。
- 角色取值固定为 `viewer/maintainer/admin`（§2.1）；后续 Feature 不新增角色（如需新增角色须走产品确认）。
- F013 **不**提供审计查询 API、不提供资源历史 API（F012/F007 负责）。

---

## 3. 数据影响（Architect 声明的数据行为，Schema 由 Database 设计）

> 下表声明**必须保障的行为与约束**，具体列类型/索引名/DDL 由 Database 在 `docs/database/` 设计并交 Backend 实现。F013 需要数据库设计（`layers.database=true`）。

| 表（建议名） | 需要保障的行为 | 依据 |
| --- | --- | --- |
| `users` | 平台用户；`id` 稳定主键；`username`（仅字母与数字、长度 1–128、区分大小写、**创建后不可修改**）；`role` 单一角色；`status ∈ {enabled, disabled}`；`must_change_password`；`version` 乐观锁；`created_at/updated_at` | §4.9.2/4/6/7/11、BQ-X |
| `users` 唯一性 | **仍存用户**内 `username` 唯一，**仅字母与数字、长度 1–128**、区分大小写；创建后不可修改。数据库对该唯一键建约束 | §4.9.3、BQ-W、BQ-X |
| `users_login_key`（可并入 `users`） | 存 `username` 作为判重键（仅字母数字、无空格）；唯一约束作用于该键 | BQ-W、BQ-X |
| `reserved_usernames`（保留标识表） | **永不删除**，主键为用户名比较键；用户**仅创建时**写入（用户名不可修改）；删除用户不删除。保证「用户名不复用」，独立于 `users` 是否存在 | §4.9.7、BQ-X、ADR-002 |
| `user_credentials`（1:1，或并入 `users`） | 每个用户当前口令哈希（Argon2id 编码串，含算法与参数）；改密/重置只替换哈希；随用户删除而删除（历史由审计承载） | §4.9.8 |
| `sessions` | 服务端会话：`token_hash`（不存明文 token）、`user_id`、`created_at`、`expires_at`、`revoked_at`、可选 `last_seen_at`；登出/删除用户/禁用/改密时使其失效 | §4.9.5/6/7 |
| `audit_log` | **append-only**；`occurred_at`、`actor_user_id`(nullable)、`actor_username_snapshot`、`action`、`target_type`、`target_id`、`target_key_snapshot`、`change`(JSON)、`result`；**不使用仅指向 `users` 的 FK 级联删除**，用户删除后审计仍可读 | §4.9.10、ADR-005 |

必须由数据库保证的关键完整性（`REQUIRED`，依据 §9.3、ADR-002）：

1. `users_login_key` 唯一（仍存用户内用户名唯一，去首尾空格、大小写敏感）。
2. `reserved_usernames` 主键唯一且只增不删 → 用户名跨删除不复用。
3. `sessions.user_id` 指向 `users`，用户删除时（显式事务内）删除其会话；不依赖隐式级联语义以外的规则。
4. `role` / `status` 取值受 CHECK/枚举约束（固定三角色）。
5. `version` 用于乐观锁，更新必须 `WHERE version = :expected` 且自增；不匹配即冲突。

行为说明（非 Schema 细节）：

- **用户名不复用如何持久化**：创建/改名时以比较键插入 `reserved_usernames`；同名（含曾经删除者）等价即拒绝。删除用户只删 `users`/`user_credentials`/`sessions`，`reserved_usernames` 与 `audit_log` 保留。
- **删除是否物理删行**：`users` 行可真实删除（ADR-002「不预设直接删行」）；但 `reserved_usernames` 与 `audit_log` 保证语义不受影响。Database 可自行选择保留 `users` 行 + 标记的方式，只要满足「不能登录、用户名不复用、审计保留」；本架构不预设删行。
- **角色变更即时生效**：`get_current_user` 每请求读库，无需额外失效机制。

### 3.1 初始化建表如何交付（P0 无迁移工具，ADR-002）

- 提供一个幂等的**初始化脚本**（如 `scripts/init_db.py`），在一个事务内：①按 ORM 元数据/`schema.sql` 创建全部表与约束；②若无任何 `admin` 用户则执行首个管理员预置。重复执行不报错、不覆盖已有数据。
- 部署时执行一次（Docker Compose 启动前/启动钩子）。
- 首个管理员预置：读取 `CSM_INITIAL_ADMIN_USERNAME` / `CSM_INITIAL_ADMIN_PASSWORD` 环境变量；未提供口令时生成随机口令并打印到部署日志（一次性）；创建用户 `role=admin`、`status=enabled`、`must_change_password=true`，并写入 `reserved_usernames`。
- 无 Alembic/无迁移；后续表结构变更仍须按 AGENTS §6 显式评估并单独记录（P0 不改 schema）。

---

## 4. 会话与安全设计

### 4.1 登录流程

1. `POST /auth/login`，服务端：规范化用户名比较键 → 查用户 → 校验 `status=enabled` → Argon2id 校验口令。
2. 失败：未知账号/口令错误 → `401 INVALID_CREDENTIALS`（统一文案，避免账号枚举）；账号存在且口令正确但已禁用 → `403 ACCOUNT_DISABLED`（映射场景 73）。
3. 成功：生成高熵随机不透明 token，仅存 `token_hash` 于 `sessions`，设置 Cookie。
4. 返回 `CurrentUser`（含 `must_change_password`）。

### 4.2 会话载体：Cookie（推荐）而非 Bearer Token

- `Set-Cookie: csm_session=<opaque>; Path=/; HttpOnly; SameSite=Lax`。因 **HTTP-only**（ADR-004/BQ-V）**不设置 `Secure`**。
- **推荐理由**：HttpOnly 使前端 JS 无法读取会话密文，显著降低 XSS 窃取会话风险；浏览器自动携带，前端无需管理 token 生命周期；服务端持有会话状态，登出/禁用/删除可即时失效。Bearer Token 若存 localStorage 则暴露于 XSS，且 HTTP 明文同样可见，并不更安全。
- **CSRF 缓解**（HTTP 下必需）：`SameSite=Lax` 阻止跨站携带 Cookie 的写请求；后端对状态变更请求额外校验 `Origin`/`Referer` 或要求自定义请求头（PROPOSED 实现细节，不改变产品规则）。
- Cookie 值不透明、不承载角色；服务端 `token_hash` 查会话。

### 4.3 口令哈希

- **Argon2id**（`argon2-cffi` / `passlib[argon2]`），单字段编码串保存算法+参数+salt+hash，便于将来调参。
- 策略：长度 ≥ 8，且**同时含至少一个英文字母与一个数字**（`PROPOSED` 明确「字母」按 `[A-Za-z]`、「数字」按 `[0-9]` 解释；若需 Unicode 字母须产品确认）。P0 无过期、无找回（§4.9.8）。
- 策略在创建、自助改密、管理员重置三处统一由 `app.security.password` 校验。

### 4.4 首登改密

- 预置首个管理员设 `must_change_password=true`（§4.9.11，`CONFIRMED`）。
- 登录成功后：`require_password_changed` 只放行 `GET /auth/me`、`POST /auth/change-password`、`POST /auth/logout`；其它接口返回 `403 PASSWORD_CHANGE_REQUIRED`。改密成功后清除标记并**失效该用户其它会话**。
- `PROPOSED`（非产品强制）：管理员新增用户或重置口令时同样置 `must_change_password=true`；若产品不希望，可关闭此行为，不影响已确认范围。

### 4.5 会话失效

| 触发 | 行为 |
| --- | --- |
| 登出 | 撤销当前会话，清 Cookie；幂等（§4.9.5） |
| 口令变更/重置 | 撤销该用户全部会话（含其它端）；`PROPOSED` 安全增强 |
| 禁用账号 | 该用户现有会话立即不可用（每请求读库校验 `status`）；`PROPOSED` 一致化，确保禁用后不能产生操作 |
| 删除用户 | 删除其会话；不能登录 |
| TTL | 服务端绝对 TTL（配置项，默认 12h，`PROPOSED` 技术默认）；到期即失效。产品未规定会话时长，属架构细节 |

### 4.6 失败与枚举

- 登录失败不区分账号是否存在，避免枚举；不创建/修改任何业务数据（场景 72）。
- 越权（非管理员调用用户管理）：服务端 `403 FORBIDDEN`，数据不变（场景 80）。
- P0 不引入登录限流框架；`PROPOSED` 可在反向代理层加重试限制（不属本期必需）。
- **最后一个管理员保护（BQ-X）**：删除或禁用前，在同一事务内校验「启用中的 `admin` 用户数 > 1」；若目标为最后一个启用中的管理员，拒绝返回 `409 LAST_ADMIN`，不改变任何数据（系统始终至少保留一个可登录管理员）。

---

## 5. API Contract（摘要；唯一字段清单见 `docs/api/F013.md`）

Contract 状态 **READY**（依据 ADR-003 已批准）。Base：`/api/v1`；错误统一 `application/problem+json`。

| # | Method | Path | 说明 | 角色 |
| --- | --- | --- | --- | --- |
| 1 | POST | `/auth/login` | 登录建立会话 | 匿名 |
| 2 | POST | `/auth/logout` | 登出 | 任意已登录 |
| 3 | GET | `/auth/me` | 当前操作者 | 任意已登录 |
| 4 | POST | `/auth/change-password` | 自助改密 | 任意已登录 |
| 5 | GET | `/users` | 用户列表（分页/筛选） | admin |
| 6 | POST | `/users` | 新增用户 | admin |
| 7 | GET | `/users/{user_id}` | 用户详情 | admin |
| 8 | PATCH | `/users/{user_id}` | 修改角色（用户名不可改；乐观锁） | admin |
| 9 | DELETE | `/users/{user_id}` | 删除用户 | admin |
| 10 | POST | `/users/{user_id}/disable` | 禁用 | admin |
| 11 | POST | `/users/{user_id}/enable` | 启用 | admin |
| 12 | POST | `/users/{user_id}/reset-password` | 重置口令 | admin |

- **角色表达**：固定枚举 `viewer | maintainer | admin`，直接作为字段值；不设独立角色表/接口（NOT_REQUIRED，理由：三角色由产品固定）。中文展示名由前端映射。
- 错误码：`400 INVALID_REQUEST`、`422 VALIDATION_ERROR`（含 `errors[]`）、`401 INVALID_CREDENTIALS`/`UNAUTHENTICATED`、`403 FORBIDDEN`/`ACCOUNT_DISABLED`/`PASSWORD_CHANGE_REQUIRED`、`404 USER_NOT_FOUND`、`409 USERNAME_TAKEN`/`VERSION_CONFLICT`。
- 边界：空列表返回 `200` + `items: []` + `total: 0`；详情/操作不存在用户 `404`；用户名（含已删除）冲突 `409`。

---

## 6. Frontend / Backend 工作拆分

**Backend**：`app.auth`、`app.users`、`app.security.password`、`app.audit`、`app.bootstrap`、`app.security.principal`；路由与 Pydantic 模型；`create_all` 初始化脚本；审计写入；唯一约束冲突→409 映射；单元/集成测试。

**Frontend**：登录/改密/用户管理页与路由守卫；`useAuthStore`；axios 拦截（401/403/409/problem+json）；首登强制改密；用户列表分页筛选、角色/状态选择、删除与重置确认。

**Database**：按 §3 设计 `users`、`user_credentials`、`sessions`、`reserved_usernames`、`audit_log` 的字段/约束/索引；交付初始化建表说明。实现由 Backend 承担。

---

## 7. Test Work

- 后端集成（pytest + httpx）：场景 72–81 全覆盖；口令策略边界（7 位/纯字母/纯数字/恰好 8 位含字母数字）；用户名去首尾空格、大小写敏感、纯空白拒绝、删除后不复用；禁用≠删除；角色变更即时生效；首登改密强制；越权 403 数据不变；登出后会话失效；401/403/404/409 语义。
- 数据库约束测试：用户名唯一、`reserved_usernames` 只增不删、`sessions` 随用户删除清理、`audit_log` append-only。
- 前端 Vitest：路由守卫、表单校验、错误映射、冲突保留输入。
- 端到端/联验：场景 40/48/57/61/64/71 的 F013 participant（角色/操作者解析与管理员判定）由 F009/F011/F012/F001 联验，F013 自身仅闭环 72–81。

---

## 8. 技术决策与风险

**已确认（依据）**：栈 ADR-001；PostgreSQL 唯一性 DB 保证、真删+保留标识、无迁移工具 ADR-002；REST/problem+json/乐观锁 409/offset 分页 ADR-003；HTTP-only/无备份 ADR-004；审计 append-only ADR-005；自建用户与三角色 BQ-V。

**PROPOSED（架构建议，非产品规则）**：① Cookie 会话 + SameSite/Origin 校验；② Argon2id；③ 会话默认 TTL 12h；④ 改密/重置/禁用即失效会话；⑤ 新增/重置也置首登改密；⑥ 字母=ASCII。

**OPEN / 关注**：
- `D-USERNAME-RENAME`（已裁定，BQ-X）：用户名**创建后不可修改**；`PATCH /users/{id}` 仅修改角色；`reserved_usernames` 仅创建时写入。
- `D-LAST-ADMIN`（已裁定，BQ-X）：禁止删除或禁用**最后一个启用中的平台管理员**；删除/禁用事务内校验，拒绝返回 `409 LAST_ADMIN`。
- 用户名长度/字符集（已裁定，BQ-X）：**仅字母与数字、长度 1–128**；由 Contract/DB CHECK 与前端校验共同保证。
- 明文 HTTP 下口令与会话可能被内网嗅探（BQ-V 已接受）；无备份意味着数据不可恢复（BQ-V 已接受）。

---

## 9. Implementation Layers

| Layer | 需要 | 说明 |
| --- | --- | --- |
| database | **true** | 5 张表/约束/索引 + 初始化建表脚本；Database 设计、Backend 实现 |
| backend | **true** | 认证/会话/用户/口令/审计/初始化/复用基础 |
| frontend | **true** | 登录/改密/用户管理/路由守卫/状态 |

结论：**READY FOR IMPLEMENTATION**（无未决架构/产品阻塞；实现仍须通过独立 Database Design 与 Contract Gate）。