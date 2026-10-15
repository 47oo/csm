# F017 API Key 机器凭据 — 实现报告（Backend / Frontend）

- **状态**：BACKEND COMPLETE + FRONTEND COMPLETE（2026-10-15）
- **Basis**：`docs/api/F017.md` v1；`docs/database/f017-api-key.md` v1（DB-D301–DB-D316）；`docs/features/F017/architecture.md`（DR-301–DR-318）；`docs/api/F002.md` v2；`docs/api/F015.md` v2；`docs/features/F017/product.md`；`docs/project/implementation-rules.md`；`.pi/skills/data-integrity/SKILL.md`。
- **角色**：Backend（`backend/**`）；Frontend（`frontend/**`）；协调器持久化本记录。

## Backend

### 实现范围（backend/**）

新增：

- `backend/alembic/versions/0014_api_keys.py`（`down_revision=0013_search_indexes`，单 head；upgrade 建表→索引→`audit_logs` 增列→增 CHECK；downgrade 逆序；手写 DDL + `op.f()`）。
- `backend/app/models/api_key.py`（无 `SoftDeleteMixin`；列/约束/索引与迁移一致）。
- `backend/app/schemas/api_keys.py`（`ApiKeyRow`/创建响应、派生 status、`validity_days` strict 1..365 默认 90）。
- `backend/app/services/api_key.py`（创建/列表/详情/吊销；`expires_at` 由 DB 事务 `now()` 派生；同事务审计；同刻 `id` 升序；`already_revoked`）。
- `backend/app/api/v1/api_keys.py`（四端点，均 `USER_ADMIN`，非 UUID→404）。
- `backend/tests/integration/api_keys_helpers.py`、`test_api_keys.py`、`test_api_key_constraints.py`。

修改：

- `backend/app/core/security.py`：`generate_api_key`（`csm_ak_`+`token_urlsafe(32)`）、`hash_api_key`（sha256 hex）、`parse_bearer_authorization`。
- `backend/app/core/auth.py`：`Operator.api_key_label`、`resolve_operator_from_api_key`、`get_current_operator` Bearer 优先/Cookie 回退。
- `backend/app/core/csrf.py`：仅「不安全方法 且 有 `csm_session` 且 无 Bearer」校验。
- `backend/app/core/logging.py`：`SENSITIVE_FIELDS` += `api_key/api_key_hash/key_hash/plaintext/bearer`。
- `backend/app/models/audit_log.py`、`app/models/__init__.py`：`api_key_label` 列 + nullable-safe CHECK，注册 `ApiKey`。
- `backend/app/services/audit.py`：`AUDITABLE_FIELDS["api_key"]`，写入 `operator.api_key_label`。
- `backend/app/api/v1/router.py`：挂载 `api_keys.router`。
- `backend/app/schemas/audit.py`：`AuditRow.api_key_label` + `object_type` 增 `api_key`（F015 v2 同步）。
- 更新 11 个既有测试的 migration head 期望 `0013_search_indexes`→`0014_api_keys`，及 `test_audit_query.py` 的 `AuditRow` 字段集合。

### 验证（实际执行）

- `python -m pytest tests/integration/test_migrations.py -q` → 4 passed, 1 skipped（up/down/up、单 head）。
- `python -m pytest tests/integration/test_api_key_constraints.py -q` → 7 passed（CHECK/UNIQUE/FK/append-only/默认 UUID/索引；真 PG）。
- `python -m pytest tests/integration/test_api_keys.py -q` → 13 passed（权限矩阵、401 先于 403、Bearer 身份与忽略 Cookie、失效/过期/停用 401、一次性明文、审计 `api_key_label`、吊销 409、过滤/排序、CSRF Bearer 豁免）。
- `python -m pytest -q`（全套）→ 601 passed, 2 skipped（skip 为既有）。
- 环境：真实 PostgreSQL（`postgres:16`，库名含 `test`，`TEST_DATABASE_URL`）；约束/迁移/认证矩阵均在真 PG 执行。

结果：`BACKEND COMPLETE`。

## Frontend

### 实现范围（frontend/**）

| 文件 | 类型 | 内容 |
| --- | --- | --- |
| `frontend/src/api/apiKeys.ts` | 新增 | `ApiKeyRow`/`CreatedApiKeyRow`；四端点调用；`describeApiKeyQueryError`/`describeApiKeyActionError`（409 `already_revoked`→刷新列表，不静默重试）；复用 `client.ts`。 |
| `frontend/src/components/apiKeyForm.ts` | 新增 | 创建表单纯逻辑：账号必选、label trim/禁 Cc-Cf/≤255、`validity_days` 1..365 默认 90；422 字段映射；载荷构造。 |
| `frontend/src/components/ApiKeyManagementPanel.tsx` | 新增 | 列表（过滤/分页/排序、四态）、创建、一次性明文 Modal（关闭即清除，不写日志/本地存储）、吊销确认；不展示 key_hash/明文（除创建一次性）。 |
| `frontend/src/pages/SystemPage.tsx` | 修改 | 新增「API Key 管理」Tab（`USER_ADMIN` 门控）。 |
| `frontend/scripts/smoke-client.mjs` | 修改 | 追加 F017 机制级冒烟 15 例。 |

契约符合：端点、参数、字段/nullable、错误语义、一次性明文纪律均按 `docs/api/F017.md` v1；无契约偏差。

### 验证（实际执行）

- `npm run typecheck` → 通过（0 错误）。
- `npm run build` → 通过。
- `npm run smoke:client` → 276 passed, 0 failed（新增 15 例，既有 261 例无回归）。

未验证：组件级 DOM/E2E（弹层焦点、剪贴板、窄屏）；真实 API 集成由 TEST 阶段验证。

结果：`FRONTEND COMPLETE`。

## 未决与后续

- F017-OPEN-1（停用后再启用是否恢复）与 F017-OPEN-3（label 账号内唯一）按 Contract 的 PROPOSED 默认实现：认证逐请求要求 `users.status='ACTIVE'`；未吊销 Key 在账号重启后恢复可用、不自动吊销；`label` 不唯一。若 Product 后续裁定变更，按变更控制处理。
- 交 TEST：复用 `test_api_keys.py`/`test_api_key_constraints.py` 与前端 smoke 作为证据，并由 Tester 独立复跑与补充真实集成。