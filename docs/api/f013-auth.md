# F013 API 契约 — 本地账号认证与会话

> Status: **READY**
> Feature: F013（ENABLER，E07，P0）
> Author Role: architect
> Date: 2026-09-15
> Source: `docs/api/api-conventions.md`（`READY`）、`docs/architecture/adr/adr-0005-local-authentication-and-session.md`（`ACCEPTED`）、`docs/architecture/f013-auth-handoff.md`、`docs/product/handoffs/f013-auth.md`、`docs/product/requirements.md` §19（R-AUTH-001 ~ R-AUTH-006）
> 本文件是 F013 前后端与测试的**共同协议与单一权威**。

---

## 1. 范围与前提

1. 本契约定义 **3 个端点**：`POST /api/auth/login`（**唯一认证豁免端点**）、`POST /api/auth/logout`、`GET /api/auth/session`。
2. 通用约定（`/api` 前缀、`snake_case`、错误信封、状态码、Empty / Not Found 语义）一律遵循 `docs/api/api-conventions.md`，本文件只做认证域的具体化，**不修改**该通用规范。
3. **认证边界**：除 `POST /api/auth/login` 外，**全部 `/api/*`**（含既有 `/api/clusters*`、`GET /api/health`、未来新增端点、以及 `/api` 下不存在的路径）在未认证时返回 `401 UNAUTHENTICATED`。豁免名单**唯一成员**是登录端点；新增端点**无需**任何白名单登记。
4. 权限模型**仅两态**（已认证 / 未认证）。**不存在**角色、权限、RBAC，也不存在任何触发 `403 FORBIDDEN` 的产品路径（R-AUTH-003）。
5. 本契约**不承诺**除「口令长度 ≥ 8 位」以外的任何口令强度行为（§8）。
6. 本契约**不涉及**资源软删语义（F014）、其他资源端点（F002+）、生产部署（F015）。

---

## 2. 认证边界与豁免

| 项 | 规则 |
|---|---|
| 受保护范围 | `path == "/api"` 或 `path` 以 `/api/` 开头的一切请求 |
| 豁免成员 | **恰好一个**：`POST /api/auth/login`（**精确 method + path** 匹配） |
| `GET /api/auth/login` | **受保护**（未认证 → `401 UNAUTHENTICATED`，不是 `405`） |
| `/api/auth/login/`（尾斜杠） | **受保护**（不参与豁免匹配） |
| `GET /api/health` | **受保护**（未认证 → `401 UNAUTHENTICATED`；已认证 → `200`） |
| 未知 `/api/*` 路径 | 未认证 → `401`；已认证 → `404 NOT_FOUND`（fail-closed） |
| 失效语义 | 未携带 Cookie、无对应会话、会话已过期、已登出、账号已停用 → 一律 `401` |

认证通过后，服务端识别出当前账号身份；本契约不提供除「谁已登录」以外的任何授权信息。

---

## 3. 会话 Cookie 契约

登录成功时返回 `Set-Cookie`；登出时清除。**Cookie 值不得出现在响应体、日志或其他字段中。**

| 属性 | 值 | 说明 |
|---|---|---|
| Name | `csm_session` | 固定名称 |
| Value | 256-bit 随机不可预测不透明令牌（URL-safe） | 服务端仅存其哈希（`sessions.token_hash`） |
| `HttpOnly` | **是** | 前端 JS 不可读 |
| `SameSite` | `Lax` | 无 HTTPS 下 CSRF 的主要缓解 |
| `Secure` | **不设置** | V1 为内网 HTTP（R-DEPLOY-003）；**浏览器会丢弃带 `Secure` 的 Cookie，因此不得设置** |
| `Path` | `/api` | 作用域限定于 API；静态资源不携带 |
| `Domain` | **不设置** | host-only，不跨子域 |
| `Max-Age` | `28800`（登录）；`0`（登出） | 与会话绝对有效期一致 |

**CSRF 实际缓解（无 HTTPS 前提）**：

1. `SameSite=Lax`：跨站发起的非 GET 请求**不携带** Cookie；
2. 所有状态改变操作均为 `POST` / `PATCH` / `DELETE`，请求体为 JSON；**不存在状态改变型 GET**；
3. **不启用 CORS**，不存在携带凭证的跨源读取。

**残余风险（明确记录，不在本 Feature 处理）**：受控内网内同站攻击、XSS，以及内网明文传输本身（R-DEPLOY-003 已确认取舍）。**不得**以「Web 最佳实践」为由反向要求 HTTPS / 域名 / 公网入口。

---

## 4. 认证资源表示

登录成功与会话校验返回**同一对象结构**：

```json
{ "id": 1, "username": "admin" }
```

| 字段 | 类型 | nullable | 说明 |
|---|---|---|---|
| `id` | integer | 否 | `users.id`（不可变代理主键） |
| `username` | string | 否 | 登录名，**原样返回**（不做大小写折叠 / 归一化） |

字段集合**封闭**：不存在 `password_hash`、`active`、`role`、`permissions`、`created_at`、`last_seen_at` 等字段。

---

## 5. 端点

### 5.1 `POST /api/auth/login` — 登录（**唯一豁免端点**）

| 项 | 值 |
|---|---|
| Method | `POST` |
| Path | `/api/auth/login` |
| Path parameter | 无 |
| Query parameter | 无 |
| 认证 | **不需要**（唯一豁免成员） |

**Request body**（`Content-Type: application/json`）

```json
{ "username": "admin", "password": "correct horse battery staple" }
```

| 字段 | 类型 | 必填 | nullable | 说明 |
|---|---|---|---|---|
| `username` | string | 是 | 否 | **按原样精确匹配**（大小写敏感，R-AUTH-005）；不折叠、不 trim |
| `password` | string | 是 | 否 | 登录路径**不校验长度 / 复杂度**；仅用于与已存哈希比对 |

**Response 200**

```json
{ "id": 1, "username": "admin" }
```

同时返回 `Set-Cookie: csm_session=...`（属性见 §3）。响应体**不含**任何令牌值。

**Error Semantics**

| 情形 | HTTP | `error.code` | `details` | Set-Cookie |
|---|---|---|---|---|
| 请求体缺少 `username` / `password`，或字段为非字符串 / `null` | `400` | `VALIDATION_ERROR` | `details[].field` 为 `"username"` 或 `"password"` | 不设置 |
| **用户名不存在** | `401` | `UNAUTHENTICATED` | `[]` | 不设置 |
| **口令错误** | `401` | `UNAUTHENTICATED` | `[]` | 不设置 |
| **账号已停用**（`active = false`） | `401` | `UNAUTHENTICATED` | `[]` | 不设置 |
| 未预期错误 | `500` | `INTERNAL_ERROR` | — | 不设置 |

**统一失败语义（R-AUTH-006，产品行为要求）**：

- 上表三个 `401` 情形必须返回**完全相同**的响应：**相同状态码**、**相同 `error.code`**、**相同 `message`**、`details == []`、**均不建立会话、均不设置 Cookie**。
- 调用方**无法**据此判断用户名是否存在。
- `message` 为固定文案（例如「用户名或口令不正确」），本契约**不承诺**其具体字面值，但它对三种情形必须一致；前端按 `error.code` 分支，**不解析 `message`**。
- 请求体校验失败（`400`）与凭据失败（`401`）的区分**不泄露账号是否存在**：`400` 仅取决于请求体是否合法。

**Empty / Not Found 语义**：不适用。

---

### 5.2 `POST /api/auth/logout` — 登出

| 项 | 值 |
|---|---|
| Method | `POST` |
| Path | `/api/auth/logout` |
| Path parameter | 无 |
| Query parameter | 无 |
| Request body | 无 |
| 认证 | **需要**（受认证边界保护，**不是**豁免端点） |

**Response 204**：无响应体。服务端**删除当前会话行**（物理删除），并返回清 Cookie 的 `Set-Cookie`（`csm_session=; Max-Age=0; Path=/api; HttpOnly; SameSite=Lax`）。

**Error Semantics**

| 情形 | HTTP | `error.code` | 说明 |
|---|---|---|---|
| 会话有效 | `204` | — | 会话失效，Cookie 清除 |
| 会话缺失 / 无效 / 过期 / 已登出 / 账号已停用 | `401` | `UNAUTHENTICATED` | 由认证边界返回 |

**幂等语义（明确契约）**：

- 登出**不**增加第二个豁免端点。会话已失效时调用登出返回 `401 UNAUTHENTICATED`，**不产生额外副作用**。
- 从调用方可观察的**终态**看操作是幂等的：无论服务端返回 `204` 还是 `401`，结果都是「该客户端不再持有有效会话」。前端必须把 `204` 与 `401 UNAUTHENTICATED` 归一为**同一处理**（清理本地状态 + 跳转登录页）。
- 重复调用不会延长、恢复或创建任何会话。

**Empty / Not Found 语义**：不适用。

---

### 5.3 `GET /api/auth/session` — 读取当前会话身份

| 项 | 值 |
|---|---|
| Method | `GET` |
| Path | `/api/auth/session` |
| Path parameter | 无 |
| Query parameter | 无 |
| Request body | 无 |
| 认证 | **需要** |

**用途**：前端启动时判断「当前是否已登录」，以及在会话存续期间刷新当前身份。

**Response 200**

```json
{ "id": 1, "username": "admin" }
```

§4 的对象结构。

**Error Semantics**

| 情形 | HTTP | `error.code` | Body |
|---|---|---|---|
| 无有效会话（缺失 / 无效 / 过期 / 已登出 / 账号已停用） | `401` | `UNAUTHENTICATED` | 统一错误信封，`details == []` |
| 未预期错误 | `500` | `INTERNAL_ERROR` | 统一错误信封 |

**Empty / Not Found 语义**：不适用（本端点不是集合，也不存在「父资源不存在」情形）。

---

## 6. 状态码与错误信封汇总

所有错误响应使用 `api-conventions.md` §5 的统一信封：

```json
{
  "error": {
    "code": "UNAUTHENTICATED",
    "message": "…",
    "details": []
  }
}
```

| 状态码 | 何时出现 | `error.code` |
|---|---|---|
| `200` | 登录成功 / 会话校验成功 | — |
| `204` | 登出成功 | — |
| `400` | 登录请求体字段校验失败 | `VALIDATION_ERROR` |
| `401` | 未认证或凭据失败（本契约的核心语义） | `UNAUTHENTICATED` |
| `500` | 未预期服务端错误 | `INTERNAL_ERROR` |
| `403` | **不存在触发路径**（V1 仅两态，无授权判断；码值仅为通用契约保留） | `FORBIDDEN` |

`error.message` 为人类可读描述，可随文案调整，**不构成契约**；前端必须按 `error.code` 分支，不解析 `message`。

---

## 7. 会话生命周期（已记录的实现决策）

`adr-0005` §5 将「会话过期时间与是否滑动续期」委托给实现阶段并**要求记录**。F013 的记录如下（供 F015 部署文档引用）：

| 项 | 决策 |
|---|---|
| 绝对有效期 | **8 小时**（`expires_at = 建立时间 + 8h`） |
| 滑动续期 | **不采用**。会话在建立后即固定过期时刻，活动不延长寿命 |
| `sessions.last_seen_at` | **保留列但不写入**（数据库设计已标为 PROPOSED / OPTIONAL） |
| 会话有效条件 | `token_hash` 命中 **AND** `expires_at > now()` **AND** 对应 `users.active = true` |
| 账号停用 | **即时生效**：校验 JOIN `users.active`，无需等待会话过期（见 §9） |
| 登出 | 物理删除当前会话行 |
| 过期清理 | 登录成功时**惰性**执行 `DELETE FROM sessions WHERE expires_at <= now()`；**无后台 worker、无新增基础设施** |
| 并发会话数量 | 不限制（V1 无多设备会话管理需求；无会话列表 / 踢出功能） |

会话令牌为服务端随机不透明值；数据库仅存其哈希，因此数据库内容本身不构成可直接使用的凭证。

**本表是「实现决策记录」，不是产品规则**；变更须重新记录并同步 F015 部署文档。

---

## 8. 明确不承诺的行为（未定义 / 范围外）

| 事项 | 本契约的承诺 |
|---|---|
| 口令强度（除长度 ≥ 8 位外） | **无承诺**：不要求大小写混合 / 数字 / 符号，不做弱口令黑名单 |
| 登录路径的口令长度校验 | **无承诺**：登录不校验长度，过短口令只是「匹配失败」→ 统一 `401` |
| 口令长度校验的失败形态 | F013 **无** HTTP 建口令 / 改口令端点；`≥8` 校验只发生在服务端领域层（初始账号路径），失败为**命令失败**而非 HTTP 响应。未来若新增 HTTP 路径，必须为 `400 VALIDATION_ERROR` + `details[].field = "password"` |
| 登录失败频率限制 / 账号锁定 | **不实现、不承诺** |
| 登录审计（谁在何时登录 / 失败） | **不实现、不承诺** |
| 多设备会话管理 / 会话列表 | **不实现、不承诺** |
| 「记住我」/ 可配置会话时长 | **不实现、不承诺** |
| IP / User-Agent 记录 | **不实现、不承诺**（数据库无对应列） |
| 用户自助注册 | **不存在**（无端点、无页面） |
| 账号管理 / 口令找回 / 重置 / MFA | **不实现、不承诺** |
| LDAP / AD / OAuth / SSO | **不接入**（R-AUTH-002） |
| HTTPS / TLS | **不承诺**（R-DEPLOY-003，内网 HTTP 为已确认取舍） |

---

## 9. 账号停用（运维路径）

F013 **不提供**账号管理界面 / API。账号停用由运维通过**直接数据库操作**执行：

```sql
UPDATE users SET active = FALSE, updated_at = now() WHERE username = '<name>';
```

行为（可验证）：

1. 停用账号**无法登录**；其登录失败响应与「用户名不存在 / 口令错误」**完全相同**（R-AUTH-006），不泄露账号是否存在。
2. 停用账号**此前建立的会话立即失效**：会话校验 JOIN `users.active`，因此无需删除会话行；下一次受保护请求返回 `401 UNAUTHENTICATED`。

---

## 10. Empty / Not Found 语义汇总（本契约范围）

| 情形 | 响应 |
|---|---|
| `POST /api/auth/login`：请求体合法但凭据失败 | `401` `UNAUTHENTICATED`（**不是** `404`，**不是** `403`） |
| `GET /api/auth/session`：无有效会话 | `401` `UNAUTHENTICATED` |
| `POST /api/auth/logout`：无有效会话 | `401` `UNAUTHENTICATED` |
| 已认证访问 `/api` 下不存在的路径 | `404` `NOT_FOUND` |

`401` 的语义是「**你尚未被系统识别为已登录用户**（未携带凭证，或凭证无效 / 过期 / 已登出 / 账号已停用）」，前端应据此引导到登录页。

---

## 11. 明确不在本契约中（非目标）

- 任何资源端点（`/api/clusters*` 属 F001；F002+ 属各资源 Feature）。**本契约不定义它们的响应**，只声明它们受认证边界保护。
- `GET /api/health` 的响应结构（属 F012 契约；本契约只声明其**未认证返回 `401`**，不新增豁免）。
- 账号管理 / 注册 / 口令修改 / 找回 / 重置端点。
- 角色 / 权限 / RBAC 端点（不存在）。
- 会话管理端点（列表 / 踢出某会话）。
- 导入端点（F011）。
- API versioning、游标分页（无需求）。
- 生产部署形态、探针路径（F015）。
- 资源软删语义、父删子拦（F014）。