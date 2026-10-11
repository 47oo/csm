# F011 Service 服务登记 — IMPLEMENTATION 阶段记录

- **状态**：BACKEND COMPLETE；FRONTEND COMPLETE
- **Contract**：docs/api/F011.md v1（READY，Architect 2026-10-09）
- **Database 设计**：docs/database/f011-service.md v1（DB-D128–D141）
- **D01**：docs/architecture/d01-conventions.md v10（§5/§5.2/§5.10）
- **角色**：Backend（backend/**）；Frontend（frontend/**）

## 1. Backend 改动文件清单
新增：`backend/alembic/versions/0011_services.py`（services 表、PK、FK RESTRICT、8 CHECK（name trim/非空/ASCII 控制/长度/name_key translate、status 默认 UNKNOWN、metadata object、version）、部分唯一 `uq_services_resource_id_name_key UNIQUE(resource_id,name_key) WHERE deleted_at IS NULL`、3 索引；down_revision=0010_ip_addresses；不重复启用扩展；down 对称）；`backend/app/models/service.py`；`backend/app/schemas/service.py`；`backend/app/services/service.py`（name_key 归一化、status/metadata 校验、软删/恢复重检、乐观锁、Activity、审计）；`backend/app/services/service_reference.py`（`register_service_reference_checker`/`check_service_references` 默认空集）；`backend/app/api/v1/services.py`；`backend/tests/integration/test_services.py`、`test_service_constraints.py`。
修改：`app/api/v1/router.py`、`app/models/__init__.py`、`app/services/audit.py`（service 白名单 `{resource_id,name,status,description,metadata}`）、`app/services/normalization.py`（`normalize_service_name`/`service_name_key`，逐码位 ASCII 折叠）、`app/services/resource.py`（导入 service 完成 Resource←Service 引用检查器注册）；6 个既有 migration 约束测试 head 字面量 0010→0011。

## 2. Contract/设计符合性
7 端点；字段契约（resource{id,hostname}；name_key 不暴露）；校验顺序（POST：401→403→body→resource→name 规范→name 唯一→写+Audit；PATCH version→可见性→name 唯一；DELETE 引用检查→软删；RESTORE name 唯一→Resource 依赖）；错误码复用 `unique_conflict{field:"name"}`/`not_deleted`/`dependency_deleted{conflicts:[{object_type:"resource"}]}`/`reference_exists`（F011 空集，F012 注册真实）；status 默认 UNKNOWN 人工维护；metadata Service 自有 JSONB；resource 创建必填不可改；Resource←未删 Service 引用检查器；审计白名单/`object_type="service"`；乐观锁；软删可见性/Activity。无新增 reason。

## 3. Migration 影响
新 head `0011_services`（down_revision=0010_ip_addresses），单一 head；不重复启用扩展；无回填；downgrade 丢弃 services 数据不可逆（DB-D141），生产回滚用 F001 全库备份。

## 4. Frontend 改动文件清单
新增：`frontend/src/api/services.ts`（7 端点 + 类型 + `describeServiceActionError`）；`frontend/src/components/serviceForm.ts`（纯逻辑：name 校验/status 默认/metadata/PATCH exclude_unset/点路径）；`frontend/src/components/ServiceForm.tsx`；`frontend/src/components/ServicesPanel.tsx`（Resource Detail Services 区域）；`frontend/src/pages/ServicesPage.tsx`（列表过滤/排序/分页、创建/编辑/删除/恢复/Activity、冲突呈现）。修改：`frontend/src/pages/HomePage.tsx`（Services 导航）、`frontend/src/pages/ResourceDetailPage.tsx`（接入 ServicesPanel）、`frontend/scripts/smoke-client.mjs`（F011 机制级 27 用例）。

## 5. 验证证据
- Backend（容器 `csm-f007-test` + PG `f002test-db`，源码挂载）：`pytest tests -q` → **382 passed, 1 skipped**（skip=F001 V3b superuser 环境性）；F011 专属 `test_services.py`（23）+ `test_service_constraints.py`（13）→ **36 passed**（含 V-DB-112–125、并发部分唯一、Resource←Service 引用、乐观锁、审计回滚）。
- Frontend：`npm run typecheck` 通过；`npm run build` 通过（70 modules）；`npm run smoke:client` → **187 passed, 0 failed**（F011 新增 27）。
- 真实 API 集成经入口 Nginx 待 TEST 阶段；Service↔Endpoint 端到端（T23）归 F012；§17/§19/Dashboard 归 F013。

## 6. 提交
Backend / Frontend 提交见检查点；implementation 记录由协调器写入。