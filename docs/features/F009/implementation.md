# F009 IP Pool 地址池 — IMPLEMENTATION 阶段记录

- **状态**：BACKEND COMPLETE；FRONTEND COMPLETE
- **Contract**：docs/api/F009.md v1（READY，Architect 2026-10-09）
- **Database 设计**：docs/database/f009-ip-pool.md v1（DB-D95–D110）
- **D01**：docs/architecture/d01-conventions.md v8（§3/§5.2/§5.8）
- **角色**：Backend（backend/**）；Frontend（frontend/**）

## 1. Backend 改动文件清单
新增：`backend/alembic/versions/0009_ip_pools.py`（ip_pools 表/全 CHECK/FK RESTRICT/name_key 部分唯一/`address_range` 生成列/排他约束 EXCLUDE USING gist (network_id WITH =, address_range WITH &&) WHERE deleted_at IS NULL/CIDR 包含函数与触发器/3 索引；不重复启用扩展；down 对称不 drop btree_gist）；`backend/app/models/ip_pool.py`；`backend/app/schemas/ip_pool.py`；`backend/app/services/ip_occupancy.py`（`IpOccupancyProvider` 注册表 + `NullIpOccupancyProvider` 空集）；`backend/app/services/ip_pool.py`（7 端点业务、校验顺序、占用触发与 field 规则、软删/恢复优先级、`_lock_network`、乐观锁、审计）；`backend/app/api/v1/ip_pools.py` + `router.py` 挂载；`backend/tests/integration/test_ip_pools.py`、`test_ip_pool_constraints.py`。
修改：`app/core/config.py`（`conflict_preview_limit=100`）、`app/core/errors.py`（`Conflict.address_in_use`）、`app/models/__init__.py`、`app/services/audit.py`（ip_pool 白名单）、`app/services/network.py`（gateway 变更占用挂钩）、`app/services/normalization.py`（ip_pool name/name_key/地址校验）；4 个既有 migration 约束测试 head 字面量 0008→0009。

## 2. Contract/设计符合性
7 端点；字段契约（`network{id,name,cidr}`；不暴露 `name_key`/`address_range`/`metadata`）；校验顺序（POST：401→403→body→network→取 `_lock_network`→地址→name 唯一→范围重叠→RESERVED 占用→写+Audit；PATCH 含 version→可见性→地址→name→overlap→占用；DELETE object→version→软删；RESTORE name→network 依赖→CIDR 422→overlap→RESERVED 占用）；错误码新增 `address_in_use`（field/conflict_count/conflicts/conflicts_truncated）、复用 `range_overlap`；权限/软删可见性/Activity/审计白名单/乐观锁按 Contract；Network 引用检查器（未删 Pool 阻止 Network 删除/改 cidr/cluster）；gateway occupancy 挂钩（空集不触发，F010 端到端）。

## 3. Migration 影响
新 head `0009_ip_pools`（down_revision=0008_networks），单一 head；0009 不含 `CREATE EXTENSION`（btree_gist 由 0008 启用）；无回填；downgrade 丢弃 ip_pools 数据不可逆（DB-D110），生产回滚用 F001 全库备份。

## 4. Frontend 改动文件清单
新增：`frontend/src/api/ipPools.ts`（7 端点 + 查询/载荷类型 + `describeIpPoolActionError`）；`frontend/src/components/ipPoolForm.ts`（纯逻辑：解析/载荷/exclude_unset/点路径）；`frontend/src/components/IpPoolForm.tsx`；`frontend/src/pages/IpPoolsPage.tsx`。修改：`frontend/src/pages/HomePage.tsx`（IP Pools 导航）；`frontend/scripts/smoke-client.mjs`（F009 机制级 24 用例）；`frontend/src/index.css`（mode 徽标样式）。

## 5. 验证证据
- Backend（容器 `csm-f007-test` + PG `f002test-db`，源码挂载）：`pytest tests -q` → **286 passed, 1 skipped**（skip=F001 V3b superuser 环境性）；F009 专属 `test_ip_pools.py`+`test_ip_pool_constraints.py` → **37 passed**；覆盖 V-DB-82–V-DB-94（迁移 up/down/up、生成列/`provolatile`、部分唯一、排他含共享端点/软删释放/恢复重检、CIDR 触发器、FK RESTRICT、并发、乐观锁、审计回滚；占用用桩 provider）。
- Frontend：`npm run typecheck` 通过；`npm run build` 通过（61 modules）；`npm run smoke:client` → **133 passed, 0 failed**（F009 新增 24：API URL/method/body、错误码含 occupancy 结构、表单解析与载荷）。
- 真实 API 集成经入口 Nginx 待 TEST 阶段；F010 真实占用端到端与容量 T32 归 F010/F013。

## 6. 提交
Backend / Frontend 提交见检查点；implementation 记录由协调器写入。