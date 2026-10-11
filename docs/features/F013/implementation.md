# F013 全局搜索与 Dashboard — IMPLEMENTATION 阶段记录

- **状态**：BACKEND COMPLETE；FRONTEND COMPLETE
- **Contract**：docs/api/F013.md v1（READY，Architect 2026-10-13）
- **Database 设计**：docs/database/f013-search-index.md v1（DB-D157–D166）
- **D01**：v11（无变更）
- **角色**：Backend（backend/**）；Frontend（frontend/**）

## 1. Backend 改动文件清单
新增：`backend/alembic/versions/0013_search_indexes.py`（down_revision=0012_service_endpoints；4 条非 partial GIN `gin_trgm_ops`：resources.hostname、clusters.code_key、clusters.name、services.name_key；不建 IP 索引；不含扩展 DDL；down 对称 DROP，不 DROP 扩展）；`backend/app/schemas/search.py`、`services/search.py`、`api/v1/search.py`；`backend/app/schemas/dashboard.py`、`services/dashboard.py`、`api/v1/dashboard.py`；`backend/tests/integration/test_search.py`、`test_dashboard.py`、`test_search_constraints.py`。
修改：`app/api/v1/router.py`（挂载 search/dashboard）；`app/models/{resource,cluster,service}.py`（GIN `Index(...)` 同步声明）；8 个约束测试 head 硬编码 0012→0013；`test_resource_constraints.py`（改断言 `ix_resources_hostname_trgm` 存在）；`test_service_constraints.py`（`SERVICE_INDEXES` 加入 `ix_services_name_key_trgm`，GIN 断言与单列 btree 断言分离）。

## 2. Contract/设计符合性
- **搜索** `/api/v1/search`：四类 typed 行（resource/cluster/ip_address/service）；匹配 hostname/code_key/name_key 归一化（仅 ASCII 折叠），Cluster name 原样，IP 精确等值（非整址不参与）；去重 `(object_type,id)`；typed 行方案（IP/Service 命中嵌入 resource，不另生 resource 行）；排序 similarity DESC→object_type 固定序→id ASC；软删 exclude/include/only（include/only 需 VIEW_DELETED→403）；分页 1–100；空 q→422 field="q"，长度 1–255；type/deleted/page 非法 422；Cluster 不展开。
- **Dashboard** `/api/v1/dashboard`：counts 未删含 INACTIVE、不受分页影响；networks 按 created_at DESC,id ASC 分页；容量**复用** `ip_capacity.network_capacity`/`auto_pools_capacity`，remaining 负值原样；软删 Network 不出现、INACTIVE 不清零；无全局合计、无 deleted/cluster_id 参数。
- 校验顺序 401→403→422→200；只读、无 Audit、无新增 error code/reason。
- **DR-189 errata/断言同步**：GIN 引入点 F013；既有 no-GIN 断言与 head 断言已同步（语义不变，不改各域行为）。

## 3. Migration 影响
新 head `0013_search_indexes`（down_revision=0012_service_endpoints），单一 head；仅 4 条 GIN trigram 索引，无表/列/约束变更、无回填、无扩展启用/删除；down 只 DROP 索引。既有「无 GIN」桩测试按 DB 设计 §7-E4 同步。

## 4. Frontend 改动文件清单
新增：`frontend/src/api/search.ts`、`dashboard.ts`；`components/globalSearchForm.ts`（纯逻辑：q trim/1–255、type 校验、空输入不发请求、422 点路径、高亮）；`components/GlobalSearch.tsx`（首页搜索框 + 类型下拉 + typed 结果列表 + 四态 + 分页 + VIEW_DELETED 开关）；`components/DashboardPanel.tsx`（Counts 5 卡片 + per-Network 容量表 + AUTO 池 + status/auto_allocate 独立列，负 remaining 原样）。
修改：`HomePage.tsx`（集成搜索 + Dashboard）；`IpAddressesPage.tsx`（可选 initialNetworkId，供未绑定 IP 跳转定位）；`index.css`；`scripts/smoke-client.mjs`（+13 F013 机制级用例）。
说明：未绑定 IP 的「所属 Network」跳转目标为 IP Addresses 列表页按网络过滤（一期无独立 Network Detail）；不伪造 Resource 归属。§18/§19 详情区域归各域 Feature，F013 仅作为导航目标。

## 5. 验证证据
- Backend（容器 `csm-f007-test` + PG `f002test-db`）：`pytest tests -q` → **473 passed, 1 skipped**（skip=F001 环境性 superuser）；`test_search_constraints.py` 真库迁移 up/down/up、单 head、4 条索引 `USING gin`+`gin_trgm_ops` 非唯一非 partial、`ip_addresses` 无 GIN、`EXPLAIN (ANALYZE)` q≥3 命中 `Bitmap Index Scan`（对应 4 索引）。
- Frontend：`npm run typecheck` 通过；`npm run build` 通过（79 modules）；`npm run smoke:client` → **224 passed, 0 failed**（F013 +13）。
- 真实 API 集成/权限/模糊行为经入口待 TEST 阶段。

## 6. 未验证项
- `q` 长度 <3 的 GIN 退化（pg_trgm 固有，未强制断言）。
- 跨 Cluster 全局 IP 精确查询索引支撑（DB-D163 已识别非阻塞性能项，未追加迁移）。
- 真实浏览器渲染/交互与 Compose 启动（机制级 + 真实 PG；集成由 TEST 阶段验证）。