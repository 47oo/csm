# F010 IP 地址分配与容量 — IMPLEMENTATION 阶段记录

- **状态**：BACKEND COMPLETE；FRONTEND COMPLETE
- **Contract**：docs/api/F010.md v1（READY，Architect 2026-10-09）
- **Database 设计**：docs/database/f010-ip-address.md v1（DB-D111–D127）
- **D01**：docs/architecture/d01-conventions.md v9（§3/§5.2/§5.9）
- **角色**：Backend（backend/**）；Frontend（frontend/**）

## 1. Backend 改动文件清单
新增：`backend/alembic/versions/0010_ip_addresses.py`（ip_addresses 表、PK、4 FK RESTRICT、3 CHECK（address_host/address_not_disabled/version）、部分唯一 `uq_ip_addresses_cluster_id_address UNIQUE(cluster_id,address) WHERE deleted_at IS NULL`、5 索引、3 个 BEFORE INSERT OR UPDATE 触发 backstop：cluster 一致性/CIDR 包含与网络广播/绑定 Interface Cluster 一致；down_revision=0009_ip_pools；不重复启用扩展；down 对称不 drop btree_gist）；`backend/app/models/ip_address.py`；`backend/app/schemas/ip_address.py`；`backend/app/services/ip_address.py`（手动/自动分配、绑定/解绑/转移、释放、恢复、`_lock_network`、乐观锁、软删过滤、Activity、审计、`ip_pool_id` 服务端推导）；`backend/app/services/ip_address_reference.py`（`register_ip_address_reference_checker` 空集挂钩 + Network/Interface 引用检查器）；`backend/app/services/ip_capacity.py`（§20 容量）；`backend/app/api/v1/ip_addresses.py`（8 端点 + `/networks/{id}/capacity`）；`backend/tests/integration/test_ip_addresses.py`、`test_ip_address_constraints.py`。
修改：`app/api/v1/router.py`、`app/core/errors.py`（`allocation_not_allowed`/`no_available_address`）、`app/models/__init__.py`、`app/services/audit.py`（`ip_address` 白名单 `{network_id,cluster_id,address,interface_id,ip_pool_id,description}`）、`app/services/ip_occupancy.py`（注册真实 `IpAddressOccupancyProvider`，替换 `NullIpOccupancyProvider`）、`app/services/normalization.py`（`normalize_ip_address`）；5 个既有 migration 约束测试 head 字面量 0009→0010。

## 2. Contract/设计符合性
9 端点；字段/nested 形状；错误码 `allocation_not_allowed{condition}`/`no_available_address{network_id,ip_pool_id}`/复用 reason；校验顺序（手动：401→403→body→network→`_lock_network`→ACTIVE→地址边界→唯一→推导 ip_pool→写+Audit；自动：条件→升序→耗尽；PATCH：version→interface→引用检查；DELETE：引用检查→软删；RESTORE：唯一→依赖→CIDR 422）；绑定/解绑/转移不受 INACTIVE 限制；分配与绑定分离；`remaining` 负值不截断；容量口径 §20；审计白名单/`object_type="ip_address"`；`_lock_network` 复用；真实 `IpAddressOccupancyProvider`；Network/Interface 引用检查器；`Endpoint←IPAddress` 挂钩默认空集（F012 注册）。

## 3. Migration 影响
新 head `0010_ip_addresses`（down_revision=0009_ip_pools），单一 head；不重复启用扩展（btree_gist 属 0008、pg_trgm 属 0001）；无回填；downgrade 丢弃 ip_addresses 数据不可逆（DB-D127），生产回滚用 F001 全库备份。

## 4. Frontend 改动文件清单
新增：`frontend/src/api/ipAddresses.ts`（9 端点 + 类型 + `describeIpAddressActionError`）；`frontend/src/components/ipAddressForm.ts`（裸 IPv4 校验/载荷构造/exclude_unset/点路径）；`frontend/src/components/IpAddressForm.tsx`（手动/自动/编辑三模式、绑定同 Cluster 校验、容量最小展示）；`frontend/src/pages/IpAddressesPage.tsx`（列表过滤/排序/分页、分配/绑定/解绑/转移/释放/恢复/Activity、冲突呈现）。修改：`frontend/src/pages/HomePage.tsx`（IP Addresses 导航）；`frontend/scripts/smoke-client.mjs`（F010 机制级 26 用例）。

## 5. 验证证据
- Backend（容器 `csm-f007-test` + PG `f002test-db`，源码挂载）：`pytest tests -q` → **336 passed, 1 skipped**（skip=F001 V3b superuser 环境性）；F010 专属 `test_ip_addresses.py`+`test_ip_address_constraints.py` → **44 passed**（含 T07 并发自动分配不重复、T35 RESERVED 变更与分配互斥、真实占用提供者、容量公式、V-DB-95–111）。
- Frontend：`npm run typecheck` 通过；`npm run build` 通过（65 modules）；`npm run smoke:client` → **163 passed, 0 failed**（F010 新增 26）。
- 真实 API 集成经入口 Nginx 待 TEST 阶段；F012 Endpoint 端到端与 F013 Dashboard 显示归后续 Feature。

## 6. 提交
Backend / Frontend 提交见检查点；implementation 记录由协调器写入。