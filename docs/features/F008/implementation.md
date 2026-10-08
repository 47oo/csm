# F008 Network 网络管理 — IMPLEMENTATION 阶段记录

- **状态**：BACKEND COMPLETE；**FRONTEND PENDING**（子代理连续两次超时，未产出文件）
- **Contract**：docs/api/F008.md v1（READY，Architect 2026-10-09）
- **Database 设计**：docs/database/f008-network.md v1（DB-D80–D94）
- **D01**：docs/architecture/d01-conventions.md v7（§3/§5.2/§5.7）
- **角色**：Backend（backend/**，完成）；Frontend（frontend/**，待续）

## 1. Backend 改动文件清单
新增：`backend/alembic/versions/0008_networks.py`（networks 表/全 CHECK/FK RESTRICT/部分唯一/3 索引/排他约束；首次 CREATE EXTENSION IF NOT EXISTS btree_gist；down 逆序不 drop 扩展）；`backend/app/models/network.py`；`backend/app/schemas/network.py`；`backend/app/services/network.py`（name_key ASCII 折叠、cidr 归一化、gateway 取值域、重叠→range_overlap、名称→unique_conflict、引用检查器注册初始空集、DR-96 FOR UPDATE、软删/恢复重检、乐观锁、审计）；`backend/app/api/v1/networks.py`（7 端点）；`backend/tests/integration/test_networks.py`（20）、`test_network_constraints.py`（10）。
修改：`core/errors.py`（Conflict.range_overlap）、`services/normalization.py`（normalize_network_name/network_name_key/normalize_cidr/normalize_gateway + 禁用段常量，禁 str.lower）、`services/audit.py`（network 白名单）、`services/cluster.py`（公共 resolve_cluster）、`services/resource.py`（委托）、`api/v1/router.py`；回归适配 head 0007→0008（test_migrations/test_bare_metal_constraints/test_virtual_machine_constraints/test_interface_constraints）。

## 2. Contract/设计符合性
7 端点；错误码 range_overlap details {field:"cidr",conflicts:[{object_type,object_id,label}]}；unique_conflict{field:"name"}；reference_exists；权限矩阵；软删默认过滤；恢复重检顺序（name→cluster→CIDR）；Activity 升序；审计白名单/同事务；校验顺序（create cluster→name→cidr/gateway→overlap；patch version→cluster→name→cidr/gateway→references→overlap；delete object→version→references）；DR-96 改 cidr/cluster 与删除事务内 FOR UPDATE + 引用检查器初始空集；metadata Network 自有。

## 3. 验证证据（Backend）
容器 `csm-f007-test` + PG `f002test-db`：`pytest -q` → **247 passed, 1 skipped**（skip=F001 V3b 非 superuser 环境性）；F008 专属 30（20 API + 10 约束/迁移）；`alembic heads` → 0008_networks。

## 4. 实现侧发现（文档需跟进，非阻塞）
1. **排他约束需显式 opclass**：btree_gist 安装后 cidr 默认 GiST opclass 为 `gist_cidr_ops`（不含 `&&`），实际需 `EXCLUDE USING gist (cluster_id WITH =, cidr inet_ops WITH &&) WHERE (deleted_at IS NULL)`。语义同 DB-D88，建议数据库文档补注。
2. **host 位归一化归属**：PostgreSQL `cidr` 类型拒绝带 host 位输入（`10.1.0.5/24` 报错），并非类型归一化；Backend 在 Service 用 `ipaddress(strict=False)` 归一化后落库。DB-D83 措辞「由 cidr 类型归一化」与真库不符，建议补注。
3. schema 仅形状/类型，cidr/gateway 格式/取值域校验在 Service（保 Contract §6 顺序，仍 422 点路径）。

## 5. 未验证项与风险
- **FRONTEND 未实现**（Networks 页面/表单/API client/smoke）：子代理超时，待续。
- 真实前后端集成（Nginx）待实现完成后进行。
- I-3 禁用范围建网限制需用户裁定；I-5 占用 gateway 归 F009/F010；引用检查器 F009/F010 实体待注册。

## 6. 提交
- Backend 提交见检查点；implementation 记录由协调器写入。
