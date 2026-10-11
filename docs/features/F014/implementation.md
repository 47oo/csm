# F014 CSV / Excel 批量导入 — IMPLEMENTATION 阶段记录

- **状态**：BACKEND COMPLETE；FRONTEND COMPLETE
- **Contract**：docs/api/F014.md v1（READY，Architect 2026-10-13）
- **Database**：docs/database/f014-import.md v1（NOT_REQUIRED）
- **D01**：v11（已最终核对关闭，无变更）；**D03**：CONTRACT v1 §10 签核
- **角色**：Backend（backend/**）；Frontend（frontend/**）

## 1. Backend 改动文件清单
修改：`backend/pyproject.toml`（+`python-multipart>=0.0.9,<0.1`、`openpyxl>=3.1,<3.2`）；`app/core/config.py`（`import_max_file_bytes=5242880`、`import_max_rows=5000`、`import_error_preview_limit=1000`）；`app/core/errors.py`（`ImportFileTooLarge`413/`ImportRowLimitExceeded`413/`ImportInvalidFile`422/`ImportValidationFailed`422）；`app/services/resource.py`（抽取非提交核心 `PreparedResource`/`prepare_resource(lock)`/`stage_resource`/`_create_resource_core`；`create_resource` 薄包装；`validate_virtual_machine(lock=)`）；`app/api/v1/router.py`（挂载 imports）。
新增：`app/services/resource_import.py`（BM 14/VM 10 冻结模板与逐列说明、CSV/xlsx 解析、严格列序表头、上限拦截、逐行复用 Service Layer 校验、文件内重复两行号、现存冲突、Host 批外快照、单事务+逐行 SAVEPOINT 归因+整批回滚、写入前再次校验、`stage_resource` 写入无旁路）；`app/schemas/imports.py`；`app/api/v1/imports.py`（validate/resources/templates 三端点）；`tests/integration/test_imports.py`、`test_import_constraints.py`（32 用例）。

## 2. Contract/设计符合性
- 三端点：`POST /api/v1/imports/resources/validate`（IMPORT，只读）、`POST /api/v1/imports/resources`（IMPORT，单事务）、`GET /api/v1/imports/resources/templates`（READ）。校验顺序 auth(401)→permission(403)→format(422)→file size(413)→parse(422 IMPORT_INVALID_FILE)→rows(413)→header/columns(422)→逐行。
- 4 个新错误码 details 与 F002 §1.2 登记一致；`RowError`（1-based 行号/模板列名/reason/related_row）；`errors_truncated` 截断且 `error_count` 全量。
- 模板：BM 14/VM 10 列冻结，列名/顺序/必填/单位/枚举；`resource_type` 固定值列；`host` 引用同 cluster 未软删 BARE_METAL（hostname 或 UUID）；metadata/description 不导入（默认）。
- 整批原子：单事务 + 逐行 SAVEPOINT；任一行失败 `rollback` 全批，零残留（Resource/BM/VM 明细/Audit/Activity）；写入前再次校验；文件内重复两行号；现存冲突不覆盖不 UPDATE；Host 批外快照（同批 BM 不可引用）；并发由部分唯一 `uq_resources_cluster_id_hostname_key` 兜底；Host 行 `FOR UPDATE`。
- 同一 Service Layer：`resource_import` 复用 `resource.py` 非提交核心，无直写旁路。
- 未新增业务规则；未改既有 API 行为（`create_resource` 薄包装）。

## 3. Frontend 改动文件清单
新增：`frontend/src/api/imports.ts`（三端点 client + 类型 + `describeImportError` + 契约常量）；`components/importForm.ts`（纯逻辑）；`components/ResourceImportPanel.tsx`（两步流程/模板查看与逐列说明/结果四态/无部分成功语义）。
修改：`src/api/client.ts`（`requestUpload` multipart，复用 handleResponse）；`src/pages/ResourcesPage.tsx`（「批量导入…」入口，IMPORT 权限显示）；`src/index.css`；`scripts/smoke-client.mjs`（+17 F014 用例）。

## 4. 验证证据
- Backend（容器内安装新依赖后，真实 PG `f002test-db`）：`pytest tests -q` → **515 passed, 1 skipped**（skip=环境性 superuser）；F014 专属 32 passed；`resource.py` 重构回归 `test_resources/bare_metal/virtual_machine` 70 passed。覆盖 A1–A26/I-1–I-17/B 场景（CSV/xlsx 一致、错误聚合、只读幂等、文件内重复两行号、现存冲突不覆盖、软删重用、VM Host 四条件+批外+同批BM不可引用、整批回滚零残留含 Audit、写入前再次校验、413 上限、预览截断、权限矩阵/CSRF、并发重叠 hostname 仅一成功、空=省略/枚举大写/单位/未知值/缺省、BOM/引号换行行号）；真实 PostgreSQL（dump 级断言 + 双连接 + 部分唯一索引定义断言）。
- Frontend：`typecheck` 通过；`build` 通过（82 modules）；`smoke:client` → **241 passed, 0 failed**（+17）。

## 5. 未验证项
- **D03 真实 PG 性能证据**（≤5000 行耗时/内存基线、上限拒绝时延）属 TEST 阶段义务，本次未测量。
- 真实 API 端到端集成与浏览器 E2E（机制级 + 真 PG；集成由 TEST 阶段验证）。
- NOTE：`test_search_constraints.py::test_explain_uses_gin_for_long_enough_query` 为计划器依赖的易抖动断言（非 F014），交 Tester 关注。