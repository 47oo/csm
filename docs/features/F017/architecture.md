# F017 API Key 机器凭据 — ARCHITECTURE 阶段报告

- **Task**：F017（FEATURE，P0，M8 API 机器访问）— Architect，Feature 设计模式
- **阶段**：ARCHITECTURE；**结论**：`READY FOR DESIGN`（2026-10-14）
- **Basis**：
  - `docs/product/requirements-v3.md` revision 4（§22、§23、§23.1、§25、§26、§27、§28、§31 T42–T49、§32、§35.1）
  - `docs/features/F017/product.md`（PRODUCT `READY FOR ARCHITECT`，A1–A8 ↔ T42–T49，无 Blocking Questions）
  - `docs/api/F002.md` v1（§1.1–§1.3、§1.2.1、§2、§2.1、§3、§4–§5）；`docs/architecture/d01-conventions.md` v11（§1 稳定 ID、§2 时间、§5.2 长度口径）
  - `docs/database/f002-auth.md` v1（DB-D13–DB-D19）；`docs/features/F002/architecture.md`（DR-07–DR-16）
  - `docs/features/F015/architecture.md`（DR-213–DR-227）、`docs/api/F015.md` v1（§2.1/§2.2/§6 object_type 登记、AuditRow 形态）
  - 现有实现：`backend/app/core/{auth,permissions,csrf,security,config,errors,logging}.py`、`backend/app/models/{user,session,audit_log,base}.py`、`backend/app/api/v1/{auth,users,router}.py`、`backend/app/services/{auth,audit,user}.py`、`backend/app/main.py`、`backend/alembic/versions/`（head `0013_search_indexes`）、`frontend/src/pages/SystemPage.tsx`、`frontend/src/components/AccountManagementPanel.tsx`、`frontend/src/api/`
  - `.pi/skills/data-integrity/SKILL.md`、`docs/project/{handoff,change-control,project-state,implementation-rules}.md`
- **DR 编号**：接续 F015 DR-227 / F016 DR-228–DR-246，自 **DR-301** 起。
- **Property**：本报告为设计输入，交 DATABASE / TEST_DESIGN Gate 核对；Contract 草案在 CONTRACT Gate 定稿签核。DR 状态区分 `CONFIRMED+DESIGN`（产品已确认、设计已定）、`PROPOSED→DATABASE`、`PROPOSED→CONTRACT`、`OPEN`。不改写 F001–F016 已 DONE 范围（§36）。

---

## 1. 方案摘要

F017 在已交付的请求级认证横切上新增第二类凭据（机器凭据），不改业务对象语义：

1. **单一认证 seam 扩展**：`app/core/auth.py` 的 `get_current_operator` 是所有受保护端点的唯一认证入口（`require_permission` 依赖它）。F017 只在此处扩展「Cookie **或** API Key」二选一解析，不新增并行鉴权路径；所有既有业务端点自动同时接受两种载体（A1/A2）。
2. **机器凭据载体**：`Authorization: Bearer csm_ak_<token>`。API Key 为高熵随机串（`secrets.token_urlsafe(32)`），DB 仅存 SHA-256 hex，明文仅在 201 创建响应返回一次。Bearer 与 Cookie 并存；Bearer 优先且忽略 Cookie；Bearer 请求免除浏览器同源（CSRF）校验。Cookie 路径行为逐字不变（A8/T49）。
3. **生命周期对象**：新表 `api_keys`（所属账号、标签、哈希、创建时间、过期时间、吊销时间、创建人），采用**吊销**语义，**不**继承 `SoftDeleteMixin`。
4. **管理入口**：`/api/v1/api-keys`（创建 / 列表 / 详情 / 吊销），复用 `Permission.USER_ADMIN`（仅 ADMIN），不新增权限项、不新增角色。
5. **审计**：`audit_logs` 新增可空列 `api_key_label`；`Operator` 上下文扩展 `api_key_label`；`audit.record` 写入该列。创建/吊销 Key 各写一条 `object_type="api_key"` 审计（白名单不含哈希/明文）；用 Key 的写操作 operator 为绑定账号 username + Key 标签（A4/T45）。
6. **即时失效**：认证查询逐请求读取已提交状态（无缓存、无惰性清理）；`revoked_at IS NULL`、`expires_at > now()`、`users.status='ACTIVE'` 三个条件任一不满足即 401（A3/A6、T44/T47）。
7. **交付面**：迁移 `0014_api_keys`；后端解析/端点/服务/审计；前端 System 页「API Key 管理」Tab；`docs/api/F002.md` 修订 v2 + 新增 `docs/api/F017.md`。

### 1.1 边界（不做）

- 不新增角色 / 账号类型 / 服务账号 / 匿名账号；不 OAuth/OIDC/SSO；不做 scope-down；不做 Cluster/实例级 RBAC（§23.1 明确排除）。
- 不改 Cookie 登录/登出/过期/CSRF/401-403 语义；不引入 §29 禁用基础设施（无 Redis 等）；不做后台清理任务。
- API Key 不纳入 §21 软删/恢复；不提供「永不过期」；不做浏览器交互登录；不提供 Key 更新（label/有效期不可改）。
- 不实现登录/机器凭据限流（本期 NOT_REQUIRED，沿用 F002）。

### 1.2 Domain / Data Impact

| 影响面 | 内容 | 依据 |
| --- | --- | --- |
| 新持久对象 | `api_keys` 表；不属 §21 业务对象集合，无 `deleted_at`/`version` | §23.1、§21 |
| 既有表增列 | `audit_logs.api_key_label`（nullable snapshot，无 FK） | §22、§23.1 |
| 领域语义 | 无新权限项/角色；API Key 权限 = 绑定账号 `ROLE_PERMISSIONS`；operator 语义扩展为「username + Key 标签」 | §23、§23.1 |
| 认证载体 | `csm_session` Cookie **或** `Authorization: Bearer`；F002 原「不使用 Authorization: Bearer」被本 Feature 修订为「预留 Bearer 给 API Key」 | §23.1、T49 |
| `object_type` 登记 | 新增 `api_key`（varchar，无 CHECK，无需迁移；登记于 F017 契约并同步 F015 注册表） | F015 DB-D167 |
| D01 | 稳定 ID 沿用 PG UUID `gen_random_uuid()`；时间沿用 timestamptz/UTC；`label` 非业务对象名，不并入 D01 §5 名称表 | D01 §1/§2 |

---

## 2. Design Requirements（DR-301–DR-318）

| ID | 决策 | 状态 |
| --- | --- | --- |
| DR-301 | **认证解析 seam**：扩展 `get_current_operator`（`app/core/auth.py`）为「Bearer → API Key 解析；否则 Cookie → 会话解析」的单一入口；不改 `require_permission` 形态与调用点。`resolve_operator`（Cookie）保持原样，新增 `resolve_operator_from_api_key`。所有受保护端点自动双载体。 | CONFIRMED+DESIGN |
| DR-302 | **凭据头/格式与优先级**：`Authorization: Bearer csm_ak_<token>`（token=`secrets.token_urlsafe(32)`，256-bit）。请求含 Bearer（scheme 大小写不敏感、token 非空）→ 走 API Key 路径且**忽略 Cookie**；否则走 Cookie 路径（非 Bearer 的 Authorization 头原样忽略，保持既有行为）。缺失/格式非法/哈希不匹配一律 401。 | PROPOSED→CONTRACT |
| DR-303 | **与 Cookie 并存及 CSRF**：同一 API 集合同时接受两种载体。`CsrfMiddleware` 条件收紧为「不安全方法 **且** 携带 `csm_session` **且 无 Bearer** 且非同源 → 403」。Bearer 请求不自动携带于跨站浏览器请求，故免同源校验；纯 Cookie 请求的 CSRF 行为逐字不变（T49）。 | PROPOSED→CONTRACT + CONFIRMED 边界 |
| DR-304 | **401/403 语义**：**复用 `AUTH_REQUIRED`，不新增错误码**。API Key 缺失/格式非法/哈希不匹配/已吊销/已过期（及绑定账号 DISABLED）一律 401 `AUTH_REQUIRED`，响应等价、不泄露凭据或账号存在性；已认证但缺权限为 403 `FORBIDDEN{reason:"permission"}`；未认证 401 先于 403。修订 F002 §1.2 `AUTH_REQUIRED` 语义为「无有效凭据（Cookie 或 API Key）」。 | CONFIRMED+DESIGN |
| DR-305 | **`api_keys` Schema 要点**：列 `id/user_id/label/key_hash/created_by/created_at/expires_at/revoked_at`；`user_id`、`created_by` 为 `users.id` FK `ON DELETE RESTRICT`；`key_hash` UNIQUE + `^[0-9a-f]{64}$` CHECK；`label` NOT NULL + not-blank；`expires_at > created_at`；`revoked_at IS NULL OR revoked_at >= created_at`；索引 `ix_api_keys_user_id`、`ix_api_keys_created_by`。**无** `deleted_at`/`version`/`last_used_at`。 | PROPOSED→DATABASE |
| DR-306 | **`audit_logs` 可空 Key 标签列**：新增 `api_key_label varchar(255) NULL`（operator 的 key 标签快照，无 FK；Cookie/system 操作为 NULL）；既有行回填 NULL；不改 append-only 触发器与既有索引。 | PROPOSED→DATABASE |
| DR-307 | **吊销 / 停用即时失效**：吊销 = 置 `revoked_at=now()`（同事务）；停用 = 由认证查询 `join users` 要求 `status='ACTIVE'` 即时失效。认证逐请求读取已提交状态，无缓存/无惰性清理；并发请求在吊销提交后被后续认证读取即 401。创建/吊销与审计同事务提交。 | CONFIRMED+DESIGN |
| DR-308 | **有效期**：创建请求 `validity_days` 可选，缺省 90；整数 1..365（含端点）；显式 `null`/`0`/负/`>365`/非整数 → 422。服务端由 `now()` 计算 `expires_at`；不提供永不过期。DB 侧 `expires_at <= created_at + interval '365 days'` backstop（含时钟偏差容忍，具体由 Database 定稿）。 | PROPOSED→CONTRACT（见 F017-OPEN-2） |
| DR-309 | **哈希算法与一次性明文**：token=`csm_ak_` + `secrets.token_urlsafe(32)`；DB 仅存 `hashlib.sha256` hex（同 F002 会话令牌范式）。因输入为高熵随机串，SHA-256 足够、无需慢 KDF（argon2 保留给低熵密码）。明文仅在 201 响应 `plaintext` 字段返回一次，其余任何出口不含明文或哈希。 | CONFIRMED+DESIGN |
| DR-310 | **日志/响应脱敏**：`SENSITIVE_FIELDS` 增补 `api_key`、`api_key_hash`、`key_hash`、`plaintext`、`bearer`（`authorization` 已存在；不加入过宽的裸 `key`）。响应 schema 永不包含 `key_hash`/明文；`api-keys` 端点不记录请求体。 | CONFIRMED+DESIGN |
| DR-311 | **仅 ADMIN 端点与权限门**：`/api/v1/api-keys` 四端点全部挂 `require_permission(Permission.USER_ADMIN)`（复用，不新增权限项）；服务端强制，VIEWER/EDITOR 403。创建仅可为存在且 ACTIVE 的账号。 | CONFIRMED+DESIGN |
| DR-312 | **前端落点**：`SystemPage` 新增第三个 Tab「API Key 管理」（`USER_ADMIN` 门控，与「账号管理」同权）；新组件 `ApiKeyManagementPanel.tsx`；一次性明文用一次性展示面板（复制后不可再取）。列表四态（Loading/Empty/Error/Success）。 | PROPOSED→CONTRACT |
| DR-313 | **F002 契约修订**：`docs/api/F002.md` v1→v2：§1 载体改为「Cookie 或 Bearer API Key」；§1.2 `AUTH_REQUIRED` 扩义；§1.2.1 登记新 `CONFLICT` reason `already_revoked`；§2.1 CSRF 增加 Bearer 豁免；§3 注明 API Key 继承绑定账号角色。**Cookie/登录/登出/CSRF/401-403 语义不变**。 | CONFIRMED+DESIGN |
| DR-314 | **迁移与回滚**：新增 `0014_api_keys`（down_revision=`0013_search_indexes`，单一 head）：upgrade 建 `api_keys` + `audit_logs` 增列；downgrade 逆序 drop 列、drop 表；真库 up/down/up。降级丢弃 F017 自有数据（新列仅 F017 写入），按 DB-D7 记录破坏性边界。 | PROPOSED→DATABASE |
| DR-315 | **Operator 上下文扩展**：`Operator` 增 `api_key_label: str | None = None`；`resolve_operator_from_api_key` 填入该 Key 的 `label`；`audit.record` 将 `operator.api_key_label` 写入 `audit_logs.api_key_label`（Cookie 路径为 None）。 | PROPOSED→CONTRACT |
| DR-316 | **审计登记**：`object_type="api_key"`；`AUDITABLE_FIELDS["api_key"]=("user_id","label","expires_at","revoked_at")`（不含 `key_hash`/明文）；创建 action=`CREATE`、吊销 action=`UPDATE`（revoked_at 状态变更；不新增 §22 action 取值）；同事务。`api_key` 值登记同步 F015 object_type 注册表。 | PROPOSED→CONTRACT |
| DR-317 | **账号停用后再启用**（F017-OPEN-1）：停用期间 Key 即时失效；PROPOSED 默认=重新启用后 Key 恢复可用（除非已吊销），不自动吊销。属新增业务行为，交 Product 确认；架构两条路径均可支持。 | PROPOSED / OPEN |
| DR-318 | **吊销幂等/重复语义**：吊销未知 id → 404；吊销已吊销 Key → 409 `CONFLICT{reason:"already_revoked"}`（与 F003/F015 `not_deleted` 显式状态变更范式一致）；吊销 EXPIRED 未吊销 Key → 允许，置 `revoked_at`。reason 登记入 F002 §1.2.1 共享注册表。 | PROPOSED→CONTRACT |

---

## 3. layers 与 api_required

```yaml
layers:
  database: true    # 新表 api_keys + audit_logs 增列 + 迁移 0014
  backend: true     # 认证 seam 扩展、端点、服务、审计、日志脱敏
  frontend: true    # System 页「API Key 管理」Tab
api_required: true  # /api/v1/api-keys（create/list/detail/revoke）
```

评估结论：三项 `true` 与 `api_required=true` **成立**，与既定输入一致，无需调整（无 API 则无法在无浏览器下创建/吊销凭据；无 DB 则凭据不可持久化；无前端则不满足 product §3「ADMIN 管理界面」可观察要求）。

---

## 4. API 草案（Contract 草案；定稿于 CONTRACT Gate，落点 `docs/api/F017.md`）

### 4.1 通用约定

- Base path `/api/v1`，挂同一 `api_v1_router`；认证载体为 `csm_session` Cookie **或** `Authorization: Bearer <API Key>`（DR-302）。
- 错误信封复用 F002 §1.1；**不新增 error code**；新 `CONFLICT` reason `already_revoked` 登记于 F002 §1.2.1。
- 时间 ISO-8601 UTC；分页基线 `page`≥1 默认 1、`page_size` 1–100 默认 20；非法 422 `VALIDATION_ERROR{fields}`。
- `GET` 免 CSRF；`POST` 仅在携带 Cookie 时执行 F002 §2.1 同源校验（Bearer 请求豁免，DR-303）。

### 4.2 权限矩阵（§23，复用，不新增项）

| 端点 | Capability | VIEWER | EDITOR | ADMIN |
| --- | --- | --- | --- | --- |
| `GET /api/v1/api-keys` | `USER_ADMIN` | 拒绝 | 拒绝 | 允许 |
| `GET /api/v1/api-keys/{id}` | `USER_ADMIN` | 拒绝 | 拒绝 | 允许 |
| `POST /api/v1/api-keys` | `USER_ADMIN` | 拒绝 | 拒绝 | 允许 |
| `POST /api/v1/api-keys/{id}/revoke` | `USER_ADMIN` | 拒绝 | 拒绝 | 允许 |
| 任意受保护业务端点（带 API Key） | 绑定账号对应 Capability | 按 VIEWER | 按 EDITOR | 按 ADMIN |

认证解析后按绑定账号角色逐行执行；401 先于 403。

### 4.3 `GET /api/v1/api-keys` — 列表

查询参数：`user_id`（UUID，可选）、`status`（`ACTIVE|REVOKED|EXPIRED`，可选）、`q`（label 大小写不敏感子串，trim 后空/超 255 → 422）、`page`、`page_size`、`sort∈{created_at,expires_at,label}` 默认 `created_at`、`order∈{asc,desc}` 默认 `desc`。

响应 200：

```json
{"items":[{
  "id":"…uuid","user_id":"…uuid","username":"user01","label":"ci-runner",
  "status":"ACTIVE","created_at":"2026-10-14T08:00:00+00:00",
  "expires_at":"2027-01-12T08:00:00+00:00","revoked_at":null,
  "created_by":"…uuid","created_by_username":"admin"
}],"page":1,"page_size":20,"total":3}
```

**ApiKeyRow**：`id`(UUID)、`user_id`(UUID)、`username`(string，绑定账号)、`label`(string)、`status`(enum，派生：`revoked_at≠null`→`REVOKED` > `expires_at≤now`→`EXPIRED` > `ACTIVE`)、`created_at`、`expires_at`、`revoked_at`(ISO\|null)、`created_by`(UUID)、`created_by_username`(string)。**绝不包含 `key_hash` 或明文**。空结果 200 `{items:[],…,total:0}`。

### 4.4 `GET /api/v1/api-keys/{id}` — 详情

`id` 非 UUID 或不存在 → 404 `NOT_FOUND`（同 F015 §4.2）。成功 200 `{"api_key": ApiKeyRow}`。不含哈希/明文。

### 4.5 `POST /api/v1/api-keys` — 创建（201）

Request：

| 字段 | 类型 | nullable | 必填 | 规则 |
| --- | --- | --- | --- | --- |
| `user_id` | string(UUID) | 否 | 是 | 须引用存在且 `status='ACTIVE'` 的账号；不存在/非 ACTIVE → 422 `VALIDATION_ERROR{fields:[{field:"user_id",…}]}` |
| `label` | string | 否 | 是 | trim 后非空、禁控制字符（Cc/Cf）、长度 1..255 code point；空/纯空白 → 422；不要求唯一 |
| `validity_days` | integer | 否 | 否（缺省=90） | 1..365（含）；显式 `null`/0/负/>365/非整数 → 422；无「永不过期」值 |

响应 201：

```json
{"api_key":{
  "id":"…uuid","user_id":"…uuid","username":"user01","label":"ci-runner",
  "plaintext":"csm_ak_…",
  "status":"ACTIVE","created_at":"…","expires_at":"…","revoked_at":null,
  "created_by":"…uuid","created_by_username":"admin"
}}
```

- `plaintext`：**唯一一次**返回明文；此后列表/详情/日志/审计/错误响应均不含。
- 同事务写 `object_type="api_key"` / `action="CREATE"` 审计（after=`{user_id,label,expires_at,revoked_at:null}`，无哈希/明文）。
- 错误：401 `AUTH_REQUIRED`（无有效凭据）；403 `FORBIDDEN{permission}`；422；500。

### 4.6 `POST /api/v1/api-keys/{id}/revoke` — 吊销（无请求体）

- 成功 200 `{"api_key": ApiKeyRow}`（`revoked_at` 已置、`status="REVOKED"`）；同事务写 `object_type="api_key"` / `action="UPDATE"` 审计（before/after 仅 `revoked_at` 差异）。
- 未知/非 UUID id → 404 `NOT_FOUND`。
- 已吊销 → 409 `CONFLICT{reason:"already_revoked"}`（不写审计、不改状态）。
- 不提供重新启用端点；不提供更新/删除端点（`PATCH`/`DELETE` → 404/405）。
- 错误：401/403/404/409/500。

### 4.7 业务边界

- 缺 Key、格式非法、哈希不匹配、已吊销、已过期、账号 DISABLED → 一律 401 `AUTH_REQUIRED`，响应等价（T44）。
- 401 先于 403：带无效 Key 调 ADMIN 端点 → 401（非 403）。
- 使用 API Key 的受保护请求身份等于绑定账号；`/auth/me` 亦然（A1）。
- `POST /auth/login`、`POST /auth/logout` 仍为 Cookie 流程；API Key 调用 `logout` 为无害 no-op（清理 Cookie，不影响 Key）。

---

## 5. Database 影响（详细交 DATABASE Gate）

### 5.1 新表 `api_keys`（DR-305）

| 列 | 类型 | 空 | 默认 | 约束 |
| --- | --- | --- | --- | --- |
| id | UUID | NOT NULL | gen_random_uuid() | PK `pk_api_keys` |
| user_id | UUID | NOT NULL | — | FK `fk_api_keys_user_id_users` → users.id ON DELETE RESTRICT |
| label | varchar(255) | NOT NULL | — | CHECK `ck_api_keys_label_not_blank`（`btrim(label) <> ''`） |
| key_hash | varchar(64) | NOT NULL | — | UNIQUE `uq_api_keys_key_hash`；CHECK `ck_api_keys_key_hash_format`（`^[0-9a-f]{64}$`） |
| created_by | UUID | NOT NULL | — | FK `fk_api_keys_created_by_users` → users.id ON DELETE RESTRICT |
| created_at | timestamptz | NOT NULL | now() | UTC |
| expires_at | timestamptz | NOT NULL | — | CHECK `ck_api_keys_expires_after_created`（`expires_at > created_at`）；CHECK `ck_api_keys_expires_within_max`（`expires_at <= created_at + interval '365 days'`，容忍见下） |
| revoked_at | timestamptz | NULL | — | CHECK `ck_api_keys_revoked_after_created`（`revoked_at IS NULL OR revoked_at >= created_at`） |

索引：`ix_api_keys_user_id`（列表/账号维度；PG 不自动建 FK 索引）、`ix_api_keys_created_by`。`uq_api_keys_key_hash` 承载认证 O(1) 查询。**无** `deleted_at`（非 §21 对象）、无 `version`、无 `last_used_at`（未要求，不预建）。

### 5.2 `audit_logs` 增列（DR-306）

| 列 | 类型 | 空 | 默认 | 说明 |
| --- | --- | --- | --- | --- |
| api_key_label | varchar(255) | NULL | — | operator 的 API Key 标签快照；Cookie/system 操作为 NULL；无 FK（快照语义，Key 行不删）；既有行回填 NULL |

append-only 触发器与既有索引不变；`ALTER TABLE ... ADD COLUMN`（nullable、无 default）不触发行级触发器。

### 5.3 迁移 `0014_api_keys`（DR-314）

- revision `0014_api_keys`，down_revision `0013_search_indexes`，单一 head；手写 DDL（CHECK 全名，autogenerate 不识别）。
- upgrade：先 `create_table api_keys`（含约束/索引），再 `audit_logs` 增列。
- downgrade：先 drop `audit_logs.api_key_label`，再逆序 drop `api_keys`（索引随表）。
- 可逆性：up/down 对称；downgrade 丢弃仅 F017 写入的列与表数据，按 DB-D7 记录为可接受破坏性变更。

### 5.4 交 Database 签核清单

1. 列名/类型/长度/默认值与约束命名（遵循 DB-D6）；`label` 长度上限 255 与 `audit_logs.api_key_label` 一致性。
2. `ck_api_keys_expires_within_max` 的 365 天边界与 `created_at`（DB `now()`）vs 应用 `now()` 的时钟偏差容忍口径（建议显式 small interval 或改由 DB 计算）。
3. 两个 FK 的 `ON DELETE RESTRICT` 是否与 §21/§22 一致；是否需为 `created_by` 建立索引。
4. `audit_logs.api_key_label` 是否需 not-blank CHECK；是否有理由加索引（预期 NOT_REQUIRED）。
5. 迁移 revision id / 单 head / up-down-up 在真实 PG 上验证；append-only 触发器在增列后仍拒绝 UPDATE/DELETE。
6. 认证查询计划（`key_hash` 唯一索引命中）与是否需要额外部分索引（预期不需要）。

### 5.5 真实 PostgreSQL 验证要点

- up/down/up 幂等、单一 head、无残留。
- CHECK 拒绝：非法 `key_hash`、空 label、`expires_at <= created_at`、超 365 天、`revoked_at < created_at`。
- `uq_api_keys_key_hash` 重复插入失败。
- 删除有 Key 的 user 被 FK RESTRICT 拒绝（虽无删除路径）。
- 增列后 `audit_logs` UPDATE/DELETE 仍被 append-only 触发器拒绝；既有行 `api_key_label` 为 NULL。
- `gen_random_uuid()` 默认生效（PG16 核心）。

---

## 6. Test Work（交 TEST_DESIGN Gate）

### 6.1 验收映射（A1–A8 ↔ T42–T49）

| 验收 | 用例要点 | 类型 |
| --- | --- | --- |
| A1/T42 | 无 Cookie + 有效 Key：读端点 200、写端点 200/201；`/auth/me` 身份=绑定账号 | 真 HTTP + 真 PG |
| A2/T43 | VIEWER Key 写 403；EDITOR Key 可写、删除/释放/恢复 403；ADMIN Key 执行 ADMIN 行；任意 Key 不越权 | 三角色矩阵（真 HTTP） |
| A3/T44 | 缺失/格式非法/哈希不匹配/已吊销/已过期一律 401 且响应等价；401 先于 403 | 真 PG（构造各状态行） |
| A4/T45 | Key 写操作审计 operator=绑定 username 且 `api_key_label`=标签；创建/吊销各一条审计 | 真 PG 查 `audit_logs` |
| A5/T46 | 明文仅 201 出现一次；列表/详情/审计/错误无明文；DB 仅 `key_hash`；日志扫描无明文 | 真 PG + 日志捕获 |
| A6/T47 | 吊销后**后续**请求 401；停用后全部 Key 401 | 真 PG（提交后新请求） |
| A7/T48 | 缺省 90 天；`validity_days=365` 成功、`366`/`0`/负/`null` 失败；无永不过期 | 真 HTTP |
| A8/T49 | 登录/登出/`/auth/me`、CSRF 同源口径、401/403 语义与 F002 契约一致；原有用例全通过 | F002 回归集 + 真 PG |

### 6.2 边界与并发/即时性

- **即时性**：吊销/停用提交后，新连接新请求立即 401（不做缓存命中测试；验证无缓存层）。并发场景：`POST .../revoke` 与另一请求的认证读取并行，验证不出现「已提交吊销却仍 200」的可重复一致结果（以提交后可观察状态为准）。
- **创建无重复**：并发创建产生不同 `key_hash`；唯一约束兜底。
- **状态派生边界**：`REVOKED` 优先于 `EXPIRED`；`expires_at == now()` 视为过期。
- **引用边界**：`user_id` 不存在 / DISABLED → 422；创建 Key 不改变账号状态。
- **重复吊销**：第二次 409 `already_revoked`，审计不新增。
- **明文一次性**：创建后再次 list/detail 无 `plaintext`/`key_hash`。
- **Cookie 回归（T49）**：F002 既有登录/登出/me、CSRF 同源/跨源 403、401/403 语义用例必须全绿；新增「带 Cookie + 无 Authorization」行为与 F002 完全一致；新增「带 Bearer」跳过 CSRF 的断言。

### 6.3 真实 PG 验证建议

约束/唯一/FK/迁移/append-only 仅以真实 PostgreSQL 为证据（Mock/SQLite 不作数）；日志脱敏与响应扫描在真 HTTP 链路上执行。

---

## 7. Frontend / Backend Work

### 7.1 Backend

- `app/core/auth.py`：新增 `resolve_operator_from_api_key`；`get_current_operator` 按 DR-302 分流；`Operator` 增 `api_key_label`（DR-315）。
- `app/core/csrf.py`：Bearer 豁免条件（DR-303）。
- `app/core/security.py`：`generate_api_key()`（前缀 + token）、`hash_api_key()`（SHA-256 hex）。
- `app/core/logging.py`：`SENSITIVE_FIELDS` 增补（DR-310）。
- `app/models/api_key.py` + `app/models/audit_log.py`（新列）+ `app/models/__init__.py`。
- `app/schemas/api_keys.py`；`app/services/api_key.py`（创建/列表/详情/吊销 + 同事务审计）；`app/services/audit.py` 增 `AUDITABLE_FIELDS["api_key"]`（DR-316）。
- `app/api/v1/api_keys.py` + `router.py` 挂载。
- 迁移 `0014_api_keys`。
- 测试：`backend/tests/integration/` 下真实 PG 用例（DR-305/306/307 断言的实现侧证据）。

### 7.2 Frontend

- `pages/SystemPage.tsx`：新增 Tab「API Key 管理」（`USER_ADMIN` 门控）。
- `components/ApiKeyManagementPanel.tsx`：列表（user_id/status/q 过滤 + 分页 + 排序）、创建（选账号 + label + 有效期，默认 90）、一次性明文展示（复制提示、关闭后不再可见）、吊销确认；四态显式区分，403/404/409/422 明确呈现，不静默重试。
- `api/apiKeys.ts`：契约调用与错误解析（复用 `client.ts` 信封处理）。
- 可选入口：`AccountManagementPanel` 行内「管理 API Key」跳转到该 Tab 并按账号过滤。

### 7.3 文档

- 新增 `docs/api/F017.md`；修订 `docs/api/F002.md` → v2（DR-313）；修订 `docs/api/F015.md`（AuditRow 增 `api_key_label`、object_type 注册表登记 `api_key`）→ v2；需求与测试集更新由协调器按 change-control 处理。

---

## 8. 风险与待核对项

### 8.1 待核对（Database）

- DB-D 编号（F017 段）：Schema、约束命名、365 天 backstop 时钟偏差口径、FK/索引、迁移可逆性、append-only 交互（§5.4/§5.5）。

### 8.2 待核对（Test Design）

- A1–A8 可执行判据、并发/即时性口径、Cookie 回归集、真实 PG 证据边界。

### 8.3 OPEN（非阻塞，交 Product）

- **F017-OPEN-1 / DR-317**：账号停用后再启用，其未吊销 API Key 是否恢复可用。PROPOSED 默认=恢复可用（停用期间失效）。若 Product 要求永久失效，则在停用同事务批量置 `revoked_at`，架构无需改动。
- **F017-OPEN-2 / DR-308**：T48「缺少有效期…创建失败」与 §23.1/ A7「默认 90 天」措辞张力。本设计按 product A7 采用「缺省=90、显式 null/越界=422、无永不过期」；已由协调器在 requirements T48 收敛为「省略时默认 90 天」，与本设计一致。
- **F017-OPEN-3**：`label` 是否需账号内唯一（当前 PROPOSED=不唯一）。

### 8.4 风险

- **R1（LOW）**：在途请求提交前读取旧状态属数据库隔离固有窗口，语义与 F002 会话一致，不属于缺陷。
- **R2（LOW）**：认证失败时序不泄露账号/凭据存在性（token 高熵，哈希查找无有效枚举面）。
- **R3（LOW）**：`audit_logs` 降级丢列属破坏性变更，须按 DB-D7 明确记录。
- **R4（NOTE）**：`api_key` object_type 登记为契约枚举变更，不触发 Schema 变更（F015 DB-D167）。

---

## 9. Contract 引用与状态

| Contract | 状态 | 说明 |
| --- | --- | --- |
| `docs/api/F017.md`（新） | **DRAFT（本条为草案）** | Endpoint/Schema/错误/分页权限正文见 §4；READY 待 Database 与 Test Design 核对后由 Architect 定稿签核 |
| `docs/api/F002.md` | **待修订 v2** | §1 载体、§1.2 `AUTH_REQUIRED` 扩义、§1.2.1 增 `already_revoked`、§2.1 CSRF Bearer 豁免、§3 角色继承说明；Cookie 语义不变 |
| `docs/api/F015.md` | **待修订 v2** | AuditRow 增 `api_key_label`；object_type 注册表增 `api_key` |

---

## 10. 结论与下一步

DR-301–DR-318 覆盖认证解析 seam 扩展、Bearer 头/格式/优先级、Cookie 并存与 CSRF 交互、复用 `AUTH_REQUIRED` 的 401/403 语义、`api_keys` Schema、`audit_logs` 增列、吊销/停用即时失效、有效期 1..365、SHA-256 + 一次性明文、日志脱敏、仅 ADMIN 权限门、前端落点、F002/F015 契约修订与 fresh 迁移回滚。

- **layers**：`database/backend/frontend=true`；**api_required=true**（评估确认，无需调整）。
- **Blocking Questions**：无。
- **结论**：**`READY FOR DESIGN`**。下一步：DATABASE Gate（§5.4/§5.5 签核）与 TEST_DESIGN Gate（§6 判据）→ CONTRACT Gate 定稿 `docs/api/F017.md` 与 F002/F015 修订 → `READY FOR IMPLEMENTATION`。