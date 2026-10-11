# F012 Service Endpoint 监听端点 — IMPLEMENTATION 阶段记录

- **状态**：BACKEND COMPLETE；FRONTEND COMPLETE
- **Contract**：docs/api/F012.md v1（READY，Architect 2026-10-09）
- **Database 设计**：docs/database/f012-service-endpoint.md v1（DB-D142–D156）
- **D01**：docs/architecture/d01-conventions.md v11（§5.11）
- **角色**：Backend（backend/**）；Frontend（frontend/**）

## 1. Backend 改动文件清单
新增：`backend/alembic/versions/0012_service_endpoints.py`（service_endpoints 表、PK、2 FK RESTRICT、3 CHECK（protocol/port/version）、部分唯一 `uq_service_endpoints_ip_protocol_port UNIQUE(ip_address_id,protocol,port) WHERE deleted_at IS NULL`、3 索引、归属 backstop `fn_service_endpoints_attribution`+`trg_service_endpoints_attribution`（BEFORE INSERT/UPDATE，不检查软删、不加锁）；down_revision=0011_services；不重复启用扩展；down 对称）；`backend/app/models/service_endpoint.py`；`backend/app/schemas/service_endpoint.py`；`backend/app/services/service_endpoint.py`；`backend/app/services/endpoint_reference.py`（两个真实 provider 注册）；`backend/app/api/v1/service_endpoints.py`；`backend/tests/integration/test_service_endpoints.py`、`test_service_endpoint_constraints.py`。
修改：`app/api/v1/router.py`、`app/models/__init__.py`、`app/services/audit.py`（service_endpoint 白名单 `{service_id,ip_address_id,protocol,port,description}`）；**F010 errata-03**：`tests/integration/test_ip_addresses.py` 4 处 `"endpoint"`→`"service_endpoint"`；7 个既有约束测试 head 断言 0011→0012。

## 2. Contract/设计符合性
7 端点；字段契约（嵌套 service{...}/ip_address{...}）；校验顺序（POST：401→403→body→service→ip_address→归属→protocol→port→监听唯一→写+Audit；PATCH version→取值→监听唯一重检；DELETE 软删；RESTORE 唯一→依赖→归属）；错误码复用 `unique_conflict{field:"port",ip_address_id,protocol,port}`/`not_deleted`/`dependency_deleted{conflicts:[{object_type:"service"|"ip_address"|"interface",object_id}]}`/`reference_exists{references:[{object_type:"service_endpoint",...}]}`；双 provider（IP 侧 F010 挂钩 + Service 侧 F011 扩展点）注册，T22/T23 端到端；归属 backstop `restrict_violation`→422 field="ip_address"；审计/`object_type="service_endpoint"`；乐观锁；软删可见性/Activity。无新增 reason。

## 3. Migration 影响
新 head `0012_service_endpoints`（down_revision=0011_services），单一 head；不重复启用扩展；无回填；downgrade 丢弃 service_endpoints 数据不可逆（DB-D156），生产回滚用 F001 全库备份。

## 4. Frontend 改动文件清单
新增：`frontend/src/api/serviceEndpoints.ts`（7 端点 + 类型 + `describeServiceEndpointActionError`）；`frontend/src/components/serviceEndpointForm.ts`（纯逻辑：protocol 大写/port 1–65535/exclude_unset/点路径）；`frontend/src/components/ServiceEndpointForm.tsx`；`frontend/src/components/ServiceEndpointsPanel.tsx`（Service Detail Endpoints 管理区）。修改：`frontend/src/pages/ServicesPage.tsx`（接入 Endpoints）、`frontend/scripts/smoke-client.mjs`（F012 机制级用例）。

## 5. 验证证据
- Backend（容器 `csm-f007-test` + PG `f002test-db`，源码挂载）：`pytest tests -q` → **427 passed, 1 skipped**（skip=F001 V3b superuser 环境性）；F012 专属 `test_service_endpoints.py`（18）+ `test_service_endpoint_constraints.py`（15）→ **33 passed**（含 T22/T23 端到端、归属、监听唯一并发、部分唯一、迁移、乐观锁、审计回滚）。
- Frontend：`npm run typecheck` 通过；`npm run build` 通过（74 modules）；`npm run smoke:client` → **211 passed, 0 failed**（F012 新增）。
- 真实 API 集成经入口 Nginx 待 TEST 阶段；§18/§19/§17/Dashboard 展示聚合归 F013。

## 6. 提交
Backend / Frontend 提交见检查点；implementation 记录由协调器写入。