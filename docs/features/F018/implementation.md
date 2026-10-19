# F018 全局搜索字段组合展示 — 实现报告（Backend / Frontend）

- **状态**：BACKEND COMPLETE + FRONTEND COMPLETE（2026-10-15）
- **Basis**：`docs/api/F013.md` v2（§2.2、§2.9、§4、§5）；`docs/features/F018/architecture.md`（DR-319–DR-331）；`docs/features/F018/product.md`（A1–A12）；`docs/features/F018/test-report.md` TD-1；`docs/api/F007.md`（interface_type 七值）；`docs/project/implementation-rules.md`。
- **角色**：Backend（`backend/**`）；Frontend（`frontend/**`）；协调器持久化本记录。

## Backend

### 实现范围（backend/**）

1. `backend/app/schemas/search.py`：新增 `SearchRelatedInterface`、`SearchRelatedIPAddress`、`SearchResourceRelated`；`SearchResourceObject` 增加 `related`、`related_total`（非 resource 行为 `null`）。
2. `backend/app/services/search.py`：新增 `RELATED_LIMIT = 10` 与 `_load_related()`；`_build_items()` 增加 `deleted` 参数，仅对 resource 结果行注入关联。
   - 分段批量 JOIN（`interfaces → ip_addresses → networks`，`WHERE resource_id IN (...)`），无 N+1。
   - 排序 `Interface.name COLLATE "C" ASC → IPAddress.address`（`inet` 数值序）`→ IPAddress.id ASC`；每 resource 取前 10，`related_total` 为截断前总数。
   - 软删严格随查询模式：`exclude` 显式 `deleted_at IS NULL`（三表）；`include`/`only` 施加 `include_deleted=True` 展示；未复用无条件 `include_deleted=True` 的嵌入 loader（DR-323）。
3. `backend/tests/integration/test_search_related.py`（新增）：24 用例，覆盖 V1–V10、B1–B13、B20、B21。

`app/api/v1/search.py` 未改动（无必要）。

### 验证（实际执行）

真实 PostgreSQL 16.15（`TEST_DATABASE_URL`）：

- `pytest tests/integration/test_search_related.py -q` → 24 passed。
- `pytest tests/integration/test_search.py test_search_constraints.py test_f013_tester_acceptance.py test_dashboard.py test_search_related.py -q` → 69 passed。
- `pytest -q`（全套后端集成）→ 641 passed, 2 skipped。
- `ruff check` → All checks passed。

结果：`BACKEND COMPLETE`。

## Frontend

### 实现范围（frontend/**）

| 文件 | 变更 |
| --- | --- |
| `src/api/search.ts` | 新增 `SearchResourceRelated`；`SearchResourceRef` 增补 `related`/`related_total`（可选 + null，容忍旧响应）。 |
| `src/components/globalSearchFields.ts`（新增） | 纯逻辑模块：九字段白名单；localStorage（键 `csm.globalSearch.fields.v1`）读写与静默回退；默认组合 = F013 现有展示；`remainingRelatedCount`；关联安全访问；`fieldSelectionAppliesTo`。 |
| `src/components/GlobalSearch.tsx` | 字段选择器（九字段多选，仅作用 resource 行）；resource 行按生效字段渲染；`RelatedSection` 每已绑定 IP 一行 + 超限提示「还有 N 条」；related 缺失时静默省略；非 resource 行不变。 |
| `src/index.css` | F018 最小样式（选择器/关联列表/提示）。 |
| `scripts/smoke-client.mjs` | 追加 9 个机制级用例（v2 解析 + F1–F8）。 |

契约符合：`related`/`related_total` 挂嵌套 `resource`；非 resource 行恒 `null`；只加法兼容；字段选择不进入请求；上限与总数、软删/权限由服务端权威。

### 验证（实际执行）

- `npm run typecheck` → 通过。
- `npm run build` → 通过。
- `npm run smoke:client` → 285 passed, 0 failed（新增 9 例）。

未验证：浏览器级交互（勾选持久化跨真实刷新、窄屏、焦点）与真实 API 集成，由 TEST 阶段处理。

结果：`FRONTEND COMPLETE`。

## 未决与后续

- F018-TD-OPEN-4 的 localStorage 键名/编码已按 DR-326 落定为 `csm.globalSearch.fields.v1`（JSON 白名单数组）。
- 交 TEST：复用 `test_search_related.py` 与前端 smoke 作为证据，并由 Tester 独立复跑与补充真实集成。