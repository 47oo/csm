# F019 接口侧选择并绑定 IP — TEST REPORT

- **版本**：TD-1（TEST DESIGN）；执行结果见后续 `# Test Execution` 小节
- **日期**：2026-10-15

## TEST DESIGN

- **结论**：`TEST DESIGN READY`
- **依据**：`docs/product/requirements-v3.md` revision 6（§13.4、§14、§16、§21、§22、§23、§31 T54–T58）；`docs/features/F019/product.md`（AC1–AC7）；`docs/features/F019/architecture.md`（DR-332–DR-345，layers{database:false,backend:false,frontend:true}，api_required=false）；`docs/api/F010.md` v1、`docs/api/F007.md` v1。
- READY 仅表示方案可验证，不代表测试通过、不批准实现或合并。

### 0. 数据完整性（无 Schema 变更，复用既有保证）

| 规则依据 | 入口 | 数据库保证 | 业务层保证 | 验证 |
| --- | --- | --- | --- | --- |
| §14 IP 归属 | PATCH interface | FK + `trg_ip_addresses_interface_cluster` | 422 `field=interface` | F019-T01/T09、B12 |
| §14 同 Cluster 唯一 | 仅改 `interface_id` | `uq_ip_addresses_cluster_id_address` | 绑定不改 address/cluster_id | T05 |
| §21 软删 | 候选/已绑定查询；已删 PATCH | 默认 `deleted_at IS NULL` | 固定 exclude；已删 404 | T01/T04/T09、B14/B15 |
| §22 Audit | 成功 PATCH | 业务与 `audit_logs` 同事务 | 每次成功 1 行 UPDATE | T02、B16 |
| §23 权限 | READ 候选 / WRITE 绑定 | 服务端权威 | VIEWER 403；401 先于 403 | T06/T11、B13 |
| 版本冲突 | PATCH version | 条件 UPDATE→409/404 | 无静默重试 | T08、B6/B7 |
| §16/§21 Endpoint 引用 | 不解绑/转移 | 引用检查器 | 绑定不触发引用拒绝 | T05 |

### 1. 验收映射（AC1–AC7 / T54–T58）

| 验收 | 测试项 | 层次 | 预期 |
| --- | --- | --- | --- |
| AC1/T54 | F019-T01 | 真PG集成+前端机制 | 候选仅同 Cluster、未绑定、未删；跨 Cluster/已绑定/已删不出现 |
| AC2/T55 | F019-T02 | 真PG集成+真PG约束 | 多选逐条绑定关系一致；各 1 行 UPDATE Audit |
| AC3/T55 | F019-T03 | 前端机制+真PG集成 | 部分失败逐条呈现；不整体成功；每项恰一次请求，无重试 |
| AC4/T56 | F019-T04 | 前端机制+真PG集成 | 空态/错误态显式；`total>items` 提示，不静默截断 |
| AC5/T57 | F019-T05 | 真PG集成+前端机制 | VIEWER 403；绑定不改 address/network/占用；不触发引用拒绝 |
| AC6/T58 | F019-T06 | 静态+前端机制+真PG集成 | 仅绑定；并发恰一成功一 409；无重复绑定 |
| AC7/§13.4 | F019-T07 | 前端机制+真PG集成 | 创建失败无 PATCH；创建成功绑定失败保留 Interface 并提示 |

补充项：T08 后到者 409（`current_version`）、T09 422/404 语义、T10 懒加载/缓存/无 N+1、T11 401 先于 403、T12 只读无副作用、T13 无新端点/参数/Contract。

### 2. 边界与并发（B1–B20）

空/单条/跨页多选；`q` 后已选保留；部分成功（409+422+404+成功混合）；两事务同 version 并发（恰一成功一 409，无重复绑定）；VIEWER 403 / 401 先于 403；已删 IP 404；软删接口 422；跨 Cluster 422；软删恢复重现；权限隐藏不替代鉴权；候选/已绑定列表无 Audit；`total` 边界 100/101；缓存失效；单条失败不阻断其余。

### 3. 环境与夹具

- 环境：`compose.test.yaml`（`-p csmtest`）+ 真实 PostgreSQL；`TEST_DATABASE_URL`（库名含 `test` 且异于 `DATABASE_URL`）；`alembic upgrade head`；不在生产/未知库执行。
- 夹具：复用 `backend/tests/integration/test_ip_addresses.py` helper（cluster/network/pool/resource/interface/ip/allocate）与 conftest（`pg_engine`/`committed_engine`/`role_client_factory`）。构造 C1/C2 跨 Cluster、已绑定/未绑定/已删 IP、软删接口、Endpoint 引用夹具、>100 候选。
- 并发方法：`threading.Barrier(2)` + 两个独立会话，同一 `expected_version` 调用 `update_ip_address`；断言恰 1 成功 1 `VersionConflict`；raw SQL 核对唯一绑定与 version 递增。

### 4. 前端可验证性

- 现有：`npm run typecheck`、`npm run build`、`npm run smoke:client`（Node type-stripping + fetch 替换，无新框架）。
- 机制级冒烟 IP-F1–F8：选择集合增删/跨页保留；候选与已绑定查询参数构造；部分成功汇总；`total` 边界；提交载荷 `{version,interface}` 且串行不中止；`describeIpAddressActionError` 映射；权限/软删门控。
- 真实浏览器 DOM（Modal/Drawer、跨页多选渲染、部分成功渲染、懒加载/缓存、空/错/边界提示）：仓库无 DOM 端到端工具 → 标记 NOT TESTED，以机制级 + typecheck + build + 静态核对为替代证据。
- 静态核对：入口仅 `canWrite && deleted_at===null`；无手动输入/自动分配/解绑/转移控件；仅调用既有 client 函数。

### 5. 不回归集

- IP 侧手动/自动分配、解绑/转移/释放/恢复（真 PG）。
- 引用检查阻止解绑/转移/释放——确认绑定方向不触发引用拒绝。
- 容量口径（绑定不改 `occupied`，`remaining` 负值不截断）。
- Interface 创建/列表/软删（F007 契约不变）。

### 6. 不可验证项

| 编号 | 项目 | 处理 |
| --- | --- | --- |
| F019-UNV-1 | 真实浏览器 DOM 交互/布局/可访问性 | NOT TESTED；替代见 §4 |
| F019-UNV-2 | 浏览器驱动的前后端端到端 | NOT TESTED；真实绑定由真 PG 集成覆盖，前端请求构造由机制级覆盖 |
| F019-UNV-3 | DR-345/入口形态/提交顺序/模块名为 PROPOSED | 按可观察行为定义判据，不锁定命名 |
| F019-UNV-4 | 浏览器内大列表性能 | NOT TESTED；真 PG 仅验证 total/分页与无 N+1 |

### 7. 结论

`TEST DESIGN READY`（TD-1）。无 Database Gate、Contract NOT_REQUIRED、无 Blocking 项。