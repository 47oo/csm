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
---

## Test Execution

- **角色**：Tester（TEST 模式，独立执行）
- **日期**：2026-10-16
- **被测版本**：`00ba98d`（`feat(F019): interface-side IP binding (frontend)`），分支 `feature/F019-interface-ip-binding`；执行前工作区干净，执行后仅新增 `backend/tests/integration/test_f019_interface_ip_binding.py`（未跟踪），无生产/Schema/契约/产品文档改动。
- **依据**：`docs/product/requirements-v3.md` revision 6 §13.4（T54–T58）；`docs/features/F019/{product,architecture,implementation}.md`（AC1–AC7、DR-332–DR-345）；`docs/api/F010.md` v1（§1.2/§1.3/§4/§5/§6.1/§6.5/§7/§8）、`docs/api/F007.md` v1；本文件 TD-1；`docs/project/implementation-rules.md`；`.pi/skills/data-integrity/SKILL.md`；`docs/project/handoff.md`。
- **结论**：`READY FOR REVIEW`

### 0. 环境

| 项 | 值 |
| --- | --- |
| 数据库 | 真实 PostgreSQL 16（容器 `csmtest-db-1`，库 `csm_test`，Compose 网络 `csmtest_default`） |
| 迁移 | 会话夹具重建 `public` schema 后 `alembic upgrade head` |
| 应用 | 生产 `create_app()`，仅覆写 `get_db`；ASGI `TestClient`（真 HTTP）；并发用例双独立会话 + `threading.Barrier(2)` |
| 后端镜像 | `csm-backend-f019test`（`docker build --target test`；含 tests 与 pytest；无挂载，避免污染工作区） |
| Python | 3.12 / SQLAlchemy 2.0 / psycopg 3 / pytest 8/9 |
| Node | v24.14.0 / npm 11.9.0（Vite 5.4 / TypeScript 5.6） |
| DB-D10 守卫 | `TEST_DATABASE_URL` 库名含 `test`（`csm_test`）且异于 `DATABASE_URL`（`csm`）；未在生产/未知库执行 |
| 证据边界 | 候选过滤、绑定持久化、乐观锁并发、Audit 行数、Cluster/软删 422/404、权限 403/401 只以真 PG 执行；未使用 Mock/SQLite |

### 1. 命令与结果（独立复跑，不复用开发者结果）

| 命令 | 结果 |
| --- | --- |
| `docker build --target test -t csm-backend-f019test ./backend` | 成功 |
| `pytest tests/integration/test_ip_addresses.py -q`（F010 基线） | **38 passed**（与任务给定基线一致） |
| `pytest tests/integration/test_f019_interface_ip_binding.py -q`（新增，F019 独立集成） | **14 passed** |
| `pytest tests/integration/test_ip_addresses.py tests/integration/test_interfaces.py tests/integration/test_f019_interface_ip_binding.py -q` | **73 passed** |
| `pytest tests/ -q`（后端全量回归） | **664 passed, 2 skipped**（skip 为既有：F016 acceptance 禁用、migration V3b 连接角色为 superuser；与本 Feature 无关） |
| `cd frontend && npm run typecheck` | 通过（0 错误） |
| `cd frontend && npm run build` | 通过（1599 modules，仅既有 chunk-size 警告） |
| `cd frontend && npm run smoke:client` | **293 passed, 0 failed**（含 F019 IP-F1–F8；既有 285 例无回归） |

> 新增测试代码（属 Tester 范围）：`backend/tests/integration/test_f019_interface_ip_binding.py`。复用 `integration.test_ip_addresses` 的 `_cluster/_network/_pool/_resource/_interface/_ip/_allocate/_auto/_operator/role_client_factory` 与 `conftest` 的 `auth_session_factory/auth_app`。未修改业务实现、Schema、契约或产品/设计文档。

### 2. 验收映射（AC1–AC7 / T54–T58 → 验证项）

| 验收 | 测试项 | 证据 | 结果 |
| --- | --- | --- | --- |
| AC1 / T54 | F019-T01 候选过滤 | `test_candidate_filtering_same_cluster_unbound_undeleted`（同 Cluster 未绑定未删出现；已绑定/已删/跨 Cluster 不出现；q 过滤；`total` 精确） | **PASS** |
| AC2 / T55 | F019-T02 多选逐条绑定 + Audit | `test_multi_bind_relationship_and_audit`（3 个候选逐个 200、version→2、`interface` 一致；各恰 1 行 `ip_address` UPDATE Audit，3 CREATE/3 UPDATE） | **PASS** |
| AC3 / T55 | F019-T03 部分成功 | `test_partial_success_mixed_statuses`（成功 + 409 VERSION_CONFLICT + 404 已删 + 422 软删接口混合，逐条独立状态；成功项已绑定、失败项未变）；前端串行/不重试/逐项汇总 `smoke IP-F5/IP-F6` | **PASS** |
| AC4 / T56 | F019-T04 空/边界 | `test_candidate_empty_state_and_pagination_boundary`（空态 total=0；total=3>items=2 显式分页；page_size=101→422）；前端 total 边界 `smoke IP-F7` | **PASS** |
| AC5 / T57 | F019-T05/T11 权限 + 不变式 | `test_permissions_401_before_403_and_viewer_403`、`test_binding_preserves_address_network_and_occupancy`、`test_binding_does_not_trigger_reference_rejection` | **PASS** |
| AC6 / T58 | F019-T06/T08 仅绑定 + 并发 | `test_concurrent_binding_same_version_one_wins`（Barrier+双会话：恰一成功一 VersionConflict，raw SQL 唯一绑定 version=2）；无手动输入/自动分配/接口侧解绑转移入口（静态核对 + `smoke IP-F8`） | **PASS** |
| AC7 / §13.4 | F019-T07 创建失败无绑定 / 创建成功绑定失败保留 Interface | `test_create_failure_no_binding_and_bind_failure_keeps_interface`（同名创建 409 后 IP 未绑定；成功创建接口后 stale-version 绑定 409，接口保留且 IP 未绑定，重试可绑定） | **PASS** |

| 补充 | 判据 | 证据 | 结果 |
| --- | --- | --- | --- |
| T09 / B10–B12 | 已删 IP 404、软删接口 422、跨 Cluster 422 | `test_deleted_ip_soft_deleted_interface_cross_cluster` | **PASS** |
| T10 | 懒加载 / 按接口缓存 / 无 N+1 | 静态核对 `InterfacesPanel.tsx`（`loadBoundIps` 仅展开触发、`boundIps` 按 interface_id 缓存、绑定成功失效重取；候选单次 effect 分页请求，无逐行请求） | **PASS（静态）** |
| T11 | 401 先于 403 | `test_permissions_401_before_403_and_viewer_403`（匿名 PATCH/GET→401 AUTH_REQUIRED，先于 VIEWER 403） | **PASS** |
| T12 | 只读无副作用 | `test_read_only_no_side_effects`（候选/已绑定查询前后 Audit 行数与 version 不变） | **PASS** |
| T13 / DR-340 | 无新端点/参数/契约 | `test_no_new_endpoint_params_or_contract`（`/interfaces/{id}/ip-addresses`、`/bind-ip`→404；未列参数忽略→200；载荷恰 `{version,interface}`） | **PASS** |

### 3. 边界与并发

| 项 | 场景 | 证据 | 结果 |
| --- | --- | --- | --- |
| B13 | VIEWER 403 / 401 先于 403 | T05/T11 | **PASS** |
| B14/B15 | 已删 IP 不出现在候选 / PATCH→404 | T01/T09 | **PASS** |
| B10–B12 | 软删接口 422、跨 Cluster 422 | T09 | **PASS** |
| B16 | 每次成功绑定各 1 行 UPDATE Audit | T02 | **PASS** |
| B6/B7 | 后到者 409 `current_version`、无静默重试 | T03（409 VERSION_CONFLICT）+ `smoke IP-F5`（逐项捕获、不重试） | **PASS** |
| 并发 | 两事务同 version 绑定同一候选 | T06/T08：恰一成功一 409，raw SQL 唯一绑定 | **PASS** |
| 边界 | 候选 0 / 部分 / total>items；page_size 上限 | T04 | **PASS** |

### 4. 数据库 / 约束 / 变更结果（真 PG）

- **无 Schema/索引/迁移变更**（DR-343 Database NOT_REQUIRED）；本 Feature 未新增表/列/约束/索引，无 Migration 需验证。
- 复用既有保证在真 PG 上成立：同 Cluster 绑定唯一（`uq_ip_addresses_cluster_id_address` 不因仅改 `interface_id` 触发）；FK/触发器 `trg_ip_addresses_interface_cluster` 使跨 Cluster 绑定被 422 `field="interface"` 拒绝；软删默认 `deleted_at IS NULL`（候选 exclude、已删 PATCH 404）；Audit 与业务写同事务；乐观锁条件 UPDATE 后到者 409。
- **已有数据影响**：绑定仅置既有可空列 `ip_addresses.interface_id`，不改 `address/network_id/cluster_id/ip_pool_id`，无破坏性/兼容性影响；T12 证明只读查询零写入。

### 5. 接口 / 前端 / 集成结果

- **接口**：全程仅复用 F010 `GET /api/v1/ip-addresses`（§6.1）与 `PATCH /api/v1/ip-addresses/{id}`（§6.5）；候选查询 `cluster_id+bound=false+deleted=exclude(+q/page/page_size/sort=address/order=asc)`，已绑定查询 `interface_id+deleted=exclude+sort=address/order=asc`，绑定载荷恰 `{version,interface}`（exclude_unset）；响应内容/类型、401/403/404/409/422 错误语义与契约一致；未列出参数被忽略（§4）；未新增端点（`/interfaces/{id}/ip-addresses` 等 404）。→ **PASS**
- **数据库写副作用**：绑定仅 1 行 `ip_address` UPDATE + 同事务 1 行 Audit；候选/已绑定列表只读无 Audit（T12）。→ **PASS**
- **前端机制级**：`typecheck`/`build`/`smoke:client`（293 passed）通过；IP-F1 跨页多选保留、IP-F2/F3 候选查询串、IP-F4 已绑定查询串、IP-F5 逐条 `{version,interface}` 按地址升序串行不中止不重试、IP-F6 部分成功汇总、IP-F7 total 边界、IP-F8 门控均 PASS。
- **前端静态核对**：入口仅 `canOpenInterfaceIpBinding(canWrite, deleted_at===null)`；面板无手动输入新地址/自动分配/解绑/转移控件；仅调用既有 `listIpAddresses/updateIpAddress/describeIpAddressActionError`。→ **PASS（静态）**
- **真实前后端集成**：前端为受控 fetch 的机制级冒烟（非浏览器→真实 API 串联）；真实服务端绑定语义由真 PG 集成覆盖；**浏览器→真实 API 端到端 NOT TESTED**（见 §7）。

### 6. Defects

| ID | Severity | Layer | Location | 证据 | 期望 vs 实际 | Owner | 必须修复 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| OBS-F019-1 | NOTE（非缺陷，既有 F010 行为） | Backend（F010） | `app/services/ip_address.py::update_ip_address` | 该函数在任何 `interface` 变更（含「绑定」未绑定 IP）时调用 `check_ip_address_references`；`test_ip_addresses.py::test_endpoint_reference_hook_blocks_unbind_and_release` 已就注入检查器的绑定路径断言 409 | §16 仅列举解绑/转移/释放需先处理 Endpoint；F019 AC5「绑定不触发 Endpoint 引用拒绝」。实际：检查器在绑定路径亦被调用，但对 F019 候选（未绑定，按 §16 不变量不存在 Endpoint 引用）返回空集，故绑定不触发拒绝 | Architect（如需区分绑定/解绑语义，属 F010 既有边界；F019 backend NOT_REQUIRED） | 否（不影响 F019 验收） |

- F019 范围内**未发现必须修复的实现缺陷**。

### 7. 未验证项

| 项 | 状态 | 理由 / 替代证据 |
| --- | --- | --- |
| F019-UNV-1 真实浏览器 DOM（Modal/Drawer 布局、复选框跨页多选渲染、部分成功结果表渲染、可访问名） | **NOT TESTED** | 仓库无 DOM/E2E 工具；替代证据：机制级 `smoke IP-F1–F8` + `typecheck`/`build` + 静态源码核对；不以构建通过替代交互验证 |
| F019-UNV-2 浏览器驱动的前后端端到端 | **NOT TESTED** | `smoke:client` 为受控 fetch 机制级；真实绑定由真 PG 集成覆盖，请求构造由机制级覆盖，但未启动真实浏览器→真实 API 串联 |
| AC4 候选加载失败态的可重试 UI（不伪装为空列表）运行时渲染 | **NOT TESTED（DOM）** | 源码存在 `ErrorState`+「重试」并区分 loading/empty/error（静态 PASS）；运行时渲染与点击未在浏览器执行 |
| F019-UNV-3 DR-345/入口形态/提交顺序/模块名 PROPOSED | **PASS（按可观察行为）** | 以「提交后候选页重取、已绑定缓存失效」等可观察行为判定，不锁定命名；不构成缺陷 |
| F019-UNV-4 浏览器内大列表性能 | **NOT TESTED** | 真 PG 仅验证 total/分页与无逐行 N+1，未做浏览器规模性能基线 |

### 8. 结论

AC1–AC7（T54–T58）在真实 PostgreSQL + 真 HTTP 下逐项 **PASS**；候选过滤、逐条绑定与 Audit、部分成功、并发 409 无重复绑定、401 先于 403、VIEWER 403、软删 404/422、跨 Cluster 422、只读无副作用、无新端点/参数/契约均以真 PG 为证据；F010/F007 与后端全量回归无回归（664 passed）；前端 `typecheck`/`build`/`smoke:client`（293 passed）通过。无必须修复缺陷；OBS-F019-1 为既有 F010 行为的 NOTE，不影响 F019 验收。F019-UNV-1/2/4 浏览器 DOM/端到端/性能为明确未验证项，不影响本 Feature 的可验收性。

**`READY FOR REVIEW`**。本结论不批准合并；Merge Gate 由协调器按 `docs/project/git-workflow.md` 执行。

### 9. Git 声明

本次仅执行以下**只读** Git 命令，未执行任何 `add`/`commit`/`branch`/`switch`/`merge` 或其他改变 Git 状态的命令：

```text
GIT: git status --short
GIT: git rev-parse --short HEAD
GIT: git branch --show-current
GIT: git log --oneline -5
GIT: git show --stat HEAD
```
