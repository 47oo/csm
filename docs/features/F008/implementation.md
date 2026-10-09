# F008 Network 网络管理 — IMPLEMENTATION 阶段记录

- **状态**：BACKEND COMPLETE；**FRONTEND COMPLETE**（本地验证：`npm run typecheck` + `npm run build` + `npm run smoke:client`，108 passed / 0 failed）
- **Contract**：docs/api/F008.md v1（READY，Architect 2026-10-09）
- **Database 设计**：docs/database/f008-network.md v1（DB-D80–D94）
- **D01**：docs/architecture/d01-conventions.md v7（§3/§5.2/§5.7）
- **角色**：Backend（backend/**，完成）；Frontend（frontend/**，完成）

## 1. Backend 改动文件清单
新增：`backend/alembic/versions/0008_networks.py`（networks 表/全 CHECK/FK RESTRICT/部分唯一/3 索引/排他约束；首次 CREATE EXTENSION IF NOT EXISTS btree_gist；down 逆序不 drop 扩展）；`backend/app/models/network.py`；`backend/app/schemas/network.py`；`backend/app/services/network.py`（name_key ASCII 折叠、cidr 归一化、gateway 取值域、重叠→range_overlap、名称→unique_conflict、引用检查器注册初始空集、DR-96 FOR UPDATE、软删/恢复重检、乐观锁、审计）；`backend/app/api/v1/networks.py`（7 端点）；`backend/tests/integration/test_networks.py`（20）、`test_network_constraints.py`（10）。
修改：`core/errors.py`（Conflict.range_overlap）、`services/normalization.py`（normalize_network_name/network_name_key/normalize_cidr/normalize_gateway + 禁用段常量，禁 str.lower）、`services/audit.py`（network 白名单）、`services/cluster.py`（公共 resolve_cluster）、`services/resource.py`（委托）、`api/v1/router.py`；回归适配 head 0007→0008（test_migrations/test_bare_metal_constraints/test_virtual_machine_constraints/test_interface_constraints）。

## 2. Contract/设计符合性
7 端点；错误码 range_overlap details {field:"cidr",conflicts:[{object_type,object_id,label}]}；unique_conflict{field:"name"}；reference_exists；权限矩阵；软删默认过滤；恢复重检顺序（name→cluster→CIDR）；Activity 升序；审计白名单/同事务；校验顺序（create cluster→name→cidr/gateway→overlap；patch version→cluster→name→cidr/gateway→references→overlap；delete object→version→references）；DR-96 改 cidr/cluster 与删除事务内 FOR UPDATE + 引用检查器初始空集；metadata Network 自有。前端按 Contract §4/§5/§6 实现列表过滤/排序/分页、软删可见性、创建/编辑（exclude_unset，显式 null 清空 gateway/description，可改 cluster）、删除/恢复与完整错误码呈现；权限按服务端返回 permissions 显示，隐藏不替代鉴权。

## 5. 前端改动文件清单（F008）
新增：`frontend/src/api/networks.ts`（7 端点 + 查询/载荷类型 + `describeNetworkActionError`：unique_conflict/range_overlap/reference_exists/dependency_deleted/not_deleted/VERSION_CONFLICT/422/403/404）；`frontend/src/components/networkForm.ts`（纯逻辑：name/cidr/gateway 解析、默认 ACTIVE/auto_allocate false、创建/PATCH 载荷构造、cluster 可改）；`frontend/src/components/NetworkForm.tsx`（cluster 选择器 + name/cidr/gateway/status/auto_allocate/description/metadata 表单）；`frontend/src/pages/NetworksPage.tsx`（列表过滤/排序/分页、软删可见性、创建/编辑/删除/恢复、引用与重叠明细呈现）。修改：`frontend/src/pages/HomePage.tsx`（Networks 导航入口）；`frontend/scripts/smoke-client.mjs`（F008 机制级 23 用例）。

## 6. 验证证据（Backend + Frontend）
Backend：容器 `csm-f007-test` + PG `f002test-db`：`pytest -q` → **247 passed, 1 skipped**（skip=F001 V3b 非 superuser 环境性）；F008 专属 30（20 API + 10 约束/迁移）；`alembic heads` → 0008_networks。
Frontend：`npm run typecheck`（tsc --noEmit）通过；`npm run build`（tsc + vite build）通过；`npm run smoke:client` → **108 passed, 0 failed**（含 F008 机制级 23 用例：API URL/method/body、错误码映射、表单解析与载荷构造）。

## 7. 实现侧发现（文档需跟进，非阻塞）
1. **排他约束需显式 opclass**：btree_gist 安装后 cidr 默认 GiST opclass 为 `gist_cidr_ops`（不含 `&&`），实际需 `EXCLUDE USING gist (cluster_id WITH =, cidr inet_ops WITH &&) WHERE (deleted_at IS NULL)`。语义同 DB-D88，建议数据库文档补注。
2. **host 位归一化归属**：PostgreSQL `cidr` 类型拒绝带 host 位输入（`10.1.0.5/24` 报错），并非类型归一化；Backend 在 Service 用 `ipaddress(strict=False)` 归一化后落库。DB-D83 措辞「由 cidr 类型归一化」与真库不符，建议补注。
3. schema 仅形状/类型，cidr/gateway 格式/取值域校验在 Service（保 Contract §6 顺序，仍 422 点路径）。

## 8. 未验证项与风险
- Frontend 仅完成机制级冒烟（`smoke:client`）与构建；**真实前后端集成（Nginx + 真实 API）待 TEST 阶段验证**。
- I-3 禁用范围建网限制需用户裁定；I-5 占用 gateway 归 F009/F010；引用检查器 F009/F010 实体待注册。

## 9. 提交
- Backend / Frontend 提交见检查点；implementation 记录由协调器写入。

## 10. 缺陷修复（有限修复第 1 轮）
- 来源：Tester TE-1 `DEF-F008-TE1-01`（HIGH）：`ck_networks_gateway` 用 `network(cidr)::inet` / `broadcast(cidr)` 比较保留前缀长度，网络/广播地址未被 DB CHECK 拒绝（原用例因同 CIDR 被排他约束先阻而假阳性）。应用层 `normalize_gateway` 正确，未改动。
- 修复：迁移 `0008_networks.py` 与 ORM `models/network.py` 的 gateway CHECK 改为 `host(network(cidr))::inet` / `host(broadcast(cidr))::inet`；`/31`、`/32`、禁用 5 段、IPv4-only 语义不变；未放宽其它约束。
- 验证：F008 专属 32 passed；全量 249 passed / 1 skipped；独立库 raw 复核网络/广播/`/32` 非空/禁用段/越界拒绝、`/31` 两端与合法 host 接受。
- 结果：`DEF-F008-TE1-01` CLOSED；Tester 复核 TE-2 结论 `READY FOR REVIEW`。
- 遗留 NOTE（非阻塞，待 Database 补齐设计正文措辞）：DB-D83「由 cidr 类型归一化」应记为 Service `ipaddress(strict=False)`；DB-D88 排他约束需显式 `cidr inet_ops WITH &&`。
