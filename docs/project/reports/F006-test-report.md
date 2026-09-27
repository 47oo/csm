# F006 Test Report — IPv4 分配与同一表单 IP 集成

- Task：F006（独立测试）；Tester；范围：后端 F006 IP 分配、前后端同表单 IP 集成、F005 网段保护扩展、`allocated-ips` 只读端点、审计/历史、DB 约束。
- Status：**READY FOR REVIEW**（初测 RETURN TO IMPLEMENTATION 后经修复轮 1/2 关闭）
- Basis：`docs/product/requirements-v2.md` §4.2/§4.4/§4.5/§5/§6.4/§7.1/§7.3/§7.4/§9.3、§10 场景 3/4/9/11/19–27/30/31/43/44/45/46/52/60/62/65、BQ-AB/BQ-AC/BQ-W/BQ-Z；`docs/api/F006.md`、`docs/api/F002.md`、`docs/api/F005.md`；`docs/architecture/F006-ip-allocation.md`；`docs/database/F006.md`。
- 候选版本：分支 `feature/F006-ip-allocation`，初测 HEAD `0b7038a`；修复后候选 HEAD 见文末修复轮记录；base `v2`；测试期间工作区 clean。

## Environment

| 项 | 值 |
| --- | --- |
| 后端镜像 | `docker build -t csm-backend backend` → exit 0 |
| PostgreSQL | `postgres:16` 独立容器 `csm-f006-db`，独立网络 `csm-f006-net`；`PostgreSQL 16.15` |
| 后端测试库 | `csm_test`（容器内 `pytest -q`，挂载 `backend/tests`） |
| 独立探针库/服务 | `csm_probe`；`csm-backend uvicorn` 容器 `csm-f006-api`（真实 HTTP） |
| 前端 | Node v22.23.2，pnpm 11.21.0，Vue 3 + Vite；`pnpm test` / `pnpm build` |
| 隔离说明 | 未使用宿主既有 `csm-pg`/生产数据；探针与测试均在独立网络容器内执行 |

## Commands & Results

| # | 命令 | 结果 |
| --- | --- | --- |
| 1 | `docker build -t csm-backend backend` | exit 0 |
| 2 | `docker run --rm --network csm-f006-net -e CSM_DATABASE_URL=postgresql+psycopg://csm:csm@csm-f006-db:5432/csm_test -v "$PWD/backend/tests":/app/tests csm-backend pytest -q` | **2 failed, 156 passed, 1 warning in 70.13s** |
| 3 | `cd frontend && pnpm test` | **Test Files 15 passed (15), Tests 391 passed (391)** |
| 4 | `cd frontend && pnpm build`（`vue-tsc --noEmit && vite build`） | exit 0，`✓ built in 4.53s` |
| 5 | 独立 HTTP 探针（真实 uvicorn + PG） | 49 项：**48 PASS / 1 FAIL** |
| 6 | 独立 DB 约束 + 审计/历史探针 | 19 项：**19 PASS / 0 FAIL** |

## 验收映射（独立 HTTP / DB 探针）

| 验收点 | 结果 | 证据 |
| --- | --- | --- |
| 同集群 IPv4 唯一；跨集群允许；删除后可复用 | PASS | S1.1–S1.6；D1 `23505 uq_ip_addresses_cluster_ip` |
| 一请求内第二个 IP 冲突 → 整单不残留 | PASS | S2.1/S2.2（第二个 IP `409 IP_ALREADY_IN_USE`，同名可重建、地址仍可用） |
| 手动：自动范围外、网段内可用 | PASS | S3.1 |
| 越界/保留/网关/网络/广播拒绝 | PASS | S3.2–S3.6（`IP_OUT_OF_SEGMENT`/`IP_RESERVED`/`IP_GATEWAY`/`IP_NETWORK_ADDRESS`/`IP_BROADCAST_ADDRESS`） |
| 未启用自动范围 → `AUTO_RANGE_NOT_ENABLED` | PASS | S3.7 |
| 自动：启用范围内从小到大取首个可用 | PASS | S4.1（`.20` 已用、`.21` 保留 → `.22`） |
| 耗尽 → `409 NO_AVAILABLE_ADDRESS`，不切换网段 | PASS | S5.1/S5.2 |
| `/31` 两端可用、无网络/广播排除 | PASS | S6.1 |
| `/32` 单主机地址可用 | PASS | S6.2 |
| 未选网段分配（手动/自动）→ `SEGMENT_NOT_SELECTED` | PASS | S7.1/S7.2 |
| 改网段仍有 IP → `INTERFACE_SEGMENT_CHANGE_REQUIRES_IP_RELEASE` | PASS | S8.1；同次释放并重建可改段 S8.2 |
| 删网卡仍有 IP → `409 INTERFACE_HAS_IPS` | PASS | S9.1 |
| IP 删除释放后可重新分配 | PASS | S1.5/S1.6 |
| 网段仍有已分配 IP 删除 → `409 SEGMENT_HAS_ALLOCATIONS` | **FAIL** | S11.1 + pytest `test_segment_protections`：实际返回 `SEGMENT_HAS_INTERFACES`（见 F006-T-01） |
| 有已分配 IP 改 CIDR → `409 CIDR_IMMUTABLE` | PASS | S11.2 |
| 新增保留/改网关与既有分配冲突 → `409 RESERVED_ADDRESS_CONFLICTS_ALLOCATION`/`GATEWAY_CONFLICTS_ALLOCATION` | PASS | S12.1/S12.2 |
| `auto_assignable_count` 扣同集群已分配 | PASS | S13.1（before 11 → after 10；`allocated_count=1`） |
| 管理 IP：创建指定 / 删管理 IP 未处理 422 / 显式清空 / 重选 / 删所属网卡未处理 422 / 非本资源 422 | PASS | S14.1–S14.6 |
| 未修改既有 IP 不当作冲突（且保留） | PASS | S10.1 |
| 重复提交无变化仍递增 version（BQ-AC） | PASS | S10.2 |
| 整单原子（失败不残留） | PASS | S2.2、S5.2 |
| 权限：viewer 写 403 / viewer 读 200 / 未登录 401 / viewer 可读 allocated-ips | PASS | S16.1–S16.4 |
| 审计 `resource.create/update/delete`（`target_type='resource'`） | PASS | H1 |
| `resource_history`（`target_type='resource'`，IP 变更并入 `update`，删除后保留） | PASS | H2/H3/H4（`change.interfaces` 含 deleted/created 地址） |
| DB：同集群唯一 | PASS | D1 |
| DB：复合 FK（IP 段=网卡段；冗余 resource_id 钉住） | PASS | D2/D3 |
| DB：RESTRICT（网卡/网段/管理 IP 引用） | PASS | D6/D7/D9 |
| DB：CHECK IPv4 格式（含 IPv6/前导零/缺段拒绝） | PASS | D4 |
| DB：`ip_key` 生成列恒等 | PASS | D5 |
| DB：`network_interfaces` 附加唯一约束存在 | PASS | D10 |
| DB：初始化幂等（`create_schema` 重复执行，约束不重复） | PASS | D11 |
| `allocated-ips` 分页/归属/`q` 过滤/空态/非法分页 | PASS | S19.1–S19.6 |

## 缺陷

### F006-T-01 — 删网段有已分配 IP 时返回错误的错误码（`SEGMENT_HAS_ALLOCATIONS` 不可达）
- Severity：**HIGH**
- Layer：Backend
- Location：`backend/app/network_segments/router.py::delete_segment`（依赖 `fk_delete_problem`/`ip_write_problem` 的 `23503` 约束名映射）；设计依据 `docs/database/F006.md` §4/§10.1-4。
- 复现：创建集群+网段，创建资源并在该网段分配 IP，然后 `DELETE /api/v1/network-segments/{id}`（清空网关/保留后）。
- Expected：`409 SEGMENT_HAS_ALLOCATIONS`（Contract F006 §4/§5、F005 §7）。
- Actual：`409 SEGMENT_HAS_INTERFACES`。pytest `tests/test_ip_allocation.py::test_segment_protections` 在此断言失败；独立 HTTP 探针 S11.1 复现；DB 探针 D7 观察到删除仍有 IP（且网卡引用）的网段时触发的约束为 `fk_network_interfaces_segment`，非 `fk_ip_addresses_segment`。
- 影响：任何已分配 IP 必然有同网卡的网卡引用同一网段，故 `fk_ip_addresses_segment` 在删除路径上先被 `fk_network_interfaces_segment` 抢先；`SEGMENT_HAS_ALLOCATIONS` 成为不可达分支，Contract 错误语义不满足；F006 交付的测试套件红。
- Owner：Backend
- 是否必须修复：**是**（建议在 `delete_segment` 的保留/网关前置检查之后、执行 DELETE 之前增加 `SegmentUsage.allocated_count(segment_id) > 0 → 409 SEGMENT_HAS_ALLOCATIONS` 前置检查）。

### F006-T-02 — DB 约束测试断言不可达的约束名
- Severity：**MEDIUM**
- Layer：Test（DB 约束测试）
- Location：`backend/tests/test_ip_allocation_db.py:200`（`test_interface_and_segment_restrict_fk`）
- 复现：插入网卡+IP 后，先尝试删网卡（预期失败），再删网段，断言约束名为 `fk_ip_addresses_segment`。
- Expected（测试）：`fk_ip_addresses_segment`。
- Actual：`fk_network_interfaces_segment`（因网卡仍引用该网段）。
- 影响：该测试场景无法隔离 `fk_ip_addresses_segment`（IP 存在必然伴随网卡引用同网段），断言恒失败；测试套件红且对该路径的覆盖有误导性。
- Owner：Test（Tester）/ 与 Backend 共同确认
- 是否必须修复：**是**（改为断言删除被 RESTRICT 拒绝（`23503`）或校验约束存在于 `pg_constraint`，而非绑定具体约束名）。

### F006-N-01（NOTE）— 数据库设计文档对 `fk_ip_addresses_segment` 可触达性的描述不准确
- Severity：NOTE
- Layer：Database（设计文档）
- Location：`docs/database/F006.md` §4、§10.1-4。
- 说明：该文档称 `SEGMENT_HAS_ALLOCATIONS` “由 `fk_ip_addresses_segment` 的 `23503` 直接保证”；实测该约束在“有已分配 IP”场景下不会单独触发（网卡引用先触发）。建议随 F006-T-01 一并澄清“删除前置由应用 `allocated_count` 检查保证”。
- Owner：Database / Architect
- 是否必须修复：否（文档修订，非实现阻塞）

## 未验证项

| 项 | 状态 | 原因 |
| --- | --- | --- |
| 场景 22/23 并发唯一与耗尽的千节点端到端复核 | NOT TESTED | 架构 §12 明确归 F011；本次仅验证单请求语义与 DB 唯一约束 |
| 场景 9（IPv6/非法 IPv4/前缀>32 的前端定位） | PARTIAL | HTTP 层未单独探针；由 DB CHECK（D4）与前端 `validation.test.ts`（通过）间接覆盖 |
| 场景 11（跨集群网段关联拒绝）、场景 45（同名确认进入编辑） | NOT TESTED | 属 F002 既有范围，非 F006 增量；不在本次独立探针 |
| 场景 52/62 重叠网段的保留/网关跨段排除 | PARTIAL | 由开发者后端套件通过用例覆盖（本次全量 `pytest` 一并运行且通过）；独立探针仅覆盖同网段保留/网关 |
| 场景 65 重叠网段与 `/31`/`/32` 的完整计数口径 | PARTIAL | 独立探针仅验证“扣同集群已分配”差值为 1 |
| 前端 ↔ 后端真实集成 | NOT_REQUIRED | F006 架构 §12 前端仅要求 Vitest 单测；端到端联验明确归 F011。前端 391 项 Vitest 通过，构建通过 |

## 结论

**RETURN TO IMPLEMENTATION**

- 独立 HTTP 探针 48/49 通过，独立 DB/审计探针 19/19 通过，前端 391 项测试与构建通过。
- 但存在 1 个必须修复的实现缺陷（F006-T-01，HIGH，Owner Backend）：`DELETE /network-segments/{id}` 在存在已分配 IP 时返回 `SEGMENT_HAS_INTERFACES` 而非 Contract 要求的 `SEGMENT_HAS_ALLOCATIONS`，导致 `SEGMENT_HAS_ALLOCATIONS` 不可达；交付测试套件因此红（`2 failed, 156 passed`）。
- 另有 1 个测试缺陷（F006-T-02，MEDIUM，Owner Test）与 1 个设计文档 NOTE。
- 全部验收项中仅“网段删除错误码”一项 FAIL，其余通过或已说明未验证。

GIT: git rev-parse --short HEAD
GIT: git branch --show-current
GIT: git status --porcelain
GIT: git log --oneline -15
GIT: git show --stat HEAD
---

## 修复轮 1 重测（RETURN TO IMPLEMENTATION 后）

- **F006-T-01（HIGH）已修复**：`DELETE /network-segments/{id}` 在保留/网关检查后、DELETE 前新增 `allocated_count > 0 → 409 SEGMENT_HAS_ALLOCATIONS`；仅被网卡引用（无 IP）仍 `409 SEGMENT_HAS_INTERFACES`；保留/网关前置优先。
- **F006-T-02（MEDIUM，测试）已修复**：不可隔离的 `fk_ip_addresses_segment` 行级断言改为可隔离断言（约束目录 `confdeltype='r'` + `23503` 行为）+ 新增优先序回归用例。
- **F006-N-01（NOTE）已处理**：`docs/database/F006.md` 已澄清 `SEGMENT_HAS_ALLOCATIONS` 由应用前置返回、FK 为兜底。
- 协调器独立复跑：后端 **160 passed**（基线 158 + 2 回归）；前端未改动（391 passed / build 通过）。
- 结论：缺陷关闭，重新走独立 Review。

## 修复轮 2 重测（Reviewer CHANGES REQUIRED 后）

- **F006-RV-01（MEDIUM）已修复**：`POST /resources` 并发分配到同集群同一地址返回 `500` 的问题；create 路径不再延迟该唯一约束、`db.commit()`/写入 `IntegrityError` 经 `ip_write_conflict_problem` 映射为 `409 IP_ALREADY_IN_USE`（附 `conflicts`）或自动 `409 NO_AVAILABLE_ADDRESS`；PATCH 路径映射一致补齐 `conflicts`。
- 新增 API 层并发回归用例（手动/自动 POST、手动 PATCH）：恰一个成功、另一个 409，DB 仅一行、失败方无残留。
- **F006-RV-04（NOTE）已处理**：`docs/api/F006.md` 错误表补记 `IP_INVALID` 子码。
- 协调器独立复跑：后端 **163 passed**（基线 160 + 3 回归）；前端未改动（391 passed / build 通过）。
- 结论：缺陷关闭，**READY FOR REVIEW**（重新走独立 Review）。
