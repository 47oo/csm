# F027 服务端访问范围强制执行 — TEST 报告

> 本文件包含 **TEST DESIGN（TD-1）** 与 **TEST 执行（TEST-1）** 两阶段记录。TD-1 只记录可验证性设计；TEST-1 记录独立执行结果。TD-1 READY 不等于测试通过，也不代表实现或合并获批。

## TEST DESIGN（TD-1）

- **版本**：TD-1（2026-10-21）
- **角色**：Tester（TEST_DESIGN）
- **Feature**：F027（P0，M18）
- **结论**：**TEST DESIGN READY**（附 TD-2 执行前复核条件）
- **依据**：requirements revision 11 §23.2、§5–§7、§10–§24.3、§25、§27、§28、§31 T85–T89/T91/T93–T98、§32–§33；F027 product A1–A23；F027 architecture v1；`docs/api/F027.md` v1；F026 product/architecture/Contract/implementation/test-report；F013/F018、F014/F023、F019/F022、F025 契约；`backend/tests/conftest.py`、`backend/tests/integration/f015_helpers.py`、`api_keys_helpers.py`、`test_cluster_authorizations.py`。
- **结论边界**：READY 仅表示用例、环境、断言与证据边界可执行。F027 实现完成后，必须先完成 TD-2 复核，再进入 TEST 执行。

### TD-1 输入基线

| 输入 | 状态 | 说明 |
| --- | --- | --- |
| 需求 | revision 11，CONFIRMED | §23.2、T85–T99 |
| Product | A1–A23，无 Blocking Questions | Q1 维持既有 EDITOR 可创建 Cluster |
| Architecture | READY FOR DESIGN | 统一消费 F026 `AccessScope`，无第二套解析 |
| Contract | `docs/api/F027.md` v1 READY | 范围附录 + 既有 Contract errata |
| F026 基座 | DONE | `AccessScope`、授权管理、迁移 `0015_user_cluster_authorizations` |
| F027 实现 | 未提交/无实现报告 | 工作区存在未提交实现改动；截至 TD-1 无 implementation.md |
| Database | 无 Schema/迁移变更 | 真实 PG 上验证范围谓词与既有约束不回归 |

### TD-2 执行前复核条件

1. F027 Backend 实现完成并有实现报告；所有受保护业务路由实际注入 `get_access_scope`，无遗漏端点。
2. `docs/api/F027.md` 与各域 Contract errata 的文档同步状态由 Architect 确认；测试以 F027 附录为规范依据，若字面有冲突先关闭再执行。
3. 确认 F014/F023 范围行错误的 `field` 与 `reason` 字面口径，或同意测试只断言“行号 + 字段 + 原因非空 + 不泄露”而不绑定固定文案。
4. 确认 F028 承接的 Compose/浏览器证据边界；F027 不将 F028 结果计入本报告 PASS。
5. 真实测试库 `TEST_DATABASE_URL` 可用，且通过 conftest 的 DB-D10 双重守卫；迁移 head 为 `0015_user_cluster_authorizations`，F027 不新增迁移。

## 1. 环境与夹具

### 1.1 唯一有效环境

- **真实 PostgreSQL**：`TEST_DATABASE_URL`；SQLite、Mock、内存库不得作为范围、约束、事务、并发或迁移证据。
- **安全守卫**：复用 `backend/tests/conftest.py`；数据库名须含 `test`，且 `TEST_DATABASE_URL != DATABASE_URL`；不在生产库或未知库执行。
- **应用**：生产 `create_app()` + 真实依赖 + 仅覆盖 `get_db`；使用 FastAPI `TestClient` 走真实 HTTP 语义。
- **会话夹具**：
  - `pg_engine`：会话级重建 `public` schema → `alembic upgrade head`；
  - `db_session`：外层事务 + savepoint，适合只读夹具；
  - `committed_engine` / `auth_session_factory`：真实提交，用于 Audit、Activity、版本、并发与终态断言；teardown `TRUNCATE`；
  - `alembic_runner`：仅用于迁移回归，F027 不新增迁移，但需验证 head 未变。
- **身份与授权夹具**：
  - `bootstrap_admin`、`make_user`、`role_client_factory`、`login`；
  - F026 已有 `AccessScope`/`resolve_access_scope`；授权管理复用 `test_cluster_authorizations.py` 的 `_grant`/`_revoke` 或直接写 `user_cluster_authorizations`；
  - API Key 复用 `api_keys_helpers.bearer_client` / `create_key`。
- **串行纪律**：迁移用例、真实提交用例和并发用例不得并行共享 `pg_engine`；并发用例使用 `committed_engine` 的独立连接，第三方连接做终态断言。

### 1.2 建议新增测试文件

- `backend/tests/integration/f027_helpers.py`：夹具构造、授权/撤销、跨 Cluster 对象工厂、Audit/Activity 计数、断言“无残留”。
- `backend/tests/integration/test_f027_tester_acceptance.py`：T-F027-01…33。
- F028 边界不在本文件执行；T-F027-34 仅记录委托。

### 1.3 数据基线

固定三集群夹具，避免不同用例互相影响：

| 标识 | 内容 |
| --- | --- |
| Cluster A | ACTIVE；含 Resource/Interface/Network/Pool/IP/Service/Endpoint 各至少 1；部分对象有 Audit/Activity |
| Cluster B | ACTIVE；同 A 的最小完整对象集，用于证明 A/B 均可见 |
| Cluster C | ACTIVE；同 A 的最小完整对象集；非 ADMIN 未授权 |
| INACTIVE Cluster | 用于 T95；有授权、对象可见 |
| Soft-deleted Cluster | 用于 T95；原授权存在但不生效 |
| 用户 | `admin`；`viewer-ab`；`editor-ab`；`viewer-zero`；`editor-zero`；各带 Cookie 与可选 API Key |
| 授权 | `viewer-ab`、`editor-ab` 仅授予 A/B；`zero` 用户零授权；ADMIN 不建授权行 |
| 已删对象 | 各类型至少 1 个已软删对象在 A、C；用于 T98/T24 回归 |
| API Key | 绑定 `viewer-ab`、`editor-ab`、`viewer-zero`、ADMIN；至少 1 个已吊销 Key |

## 2. 8 类对象覆盖矩阵

每个对象类型都在 **列表 / 详情 / 写 / Activity** 四层验证。T-F027-03…10 每例负责一个对象类型，执行本表对应行。

| 用例 | 对象 | 列表 | 详情 | 写（非 ADMIN 范围证据） | Activity | 归属谓词 |
| --- | --- | --- | --- | --- | --- | --- |
| T-F027-03 | Cluster | `GET /clusters`、`q/code/status/deleted`、total | `GET /clusters/{id}` | `POST /clusters` 维持 EDITOR 可建、不自动授权；`PATCH`；DELETE/restore 为 ADMIN-only，非 ADMIN 403 | `GET /clusters/{id}/activity` | `scope.cluster_predicate(Cluster.id)` |
| T-F027-04 | Resource | `GET /resources`、`cluster_id/q/type/status`、total | `GET /resources/{id}` | `POST /resources` body cluster C → 422；`PATCH` C → 404；DELETE/restore 为 ADMIN-only | `GET /resources/{id}/activity` | `Resource.cluster_id` |
| T-F027-05 | Network | `GET /networks`、`cluster_id/status/q`、total | `GET /networks/{id}` | `POST /networks` body cluster C → 422；`PATCH` C → 404；DELETE/restore 为 ADMIN-only | `GET /networks/{id}/activity` | `Network.cluster_id` |
| T-F027-06 | IPAddress | `GET /ip-addresses`、`cluster_id/network_id/interface_id/bound/q`、total | `GET /ip-addresses/{id}` | `POST` / `auto-allocate` body network C → 422；`PATCH` 绑定/解绑/转移 C → 404；release/restore 为 ADMIN-only | `GET /ip-addresses/{id}/activity` | `IPAddress.cluster_id`（未绑定 IP 仍生效） |
| T-F027-07 | Interface | `GET /interfaces`、`resource_id/q`、total | `GET /interfaces/{id}` | `POST` body resource C → 422；`PATCH` C → 404；DELETE/restore 为 ADMIN-only | `GET /interfaces/{id}/activity` | `Interface.resource_id → Resource.cluster_id` |
| T-F027-08 | IPPool | `GET /ip-pools`、`network_id/q`、total | `GET /ip-pools/{id}` | `POST` body network C → 422；`PATCH` C → 404；DELETE/restore 为 ADMIN-only | `GET /ip-pools/{id}/activity` | `IPPool.network_id → Network.cluster_id` |
| T-F027-09 | Service | `GET /services`、`resource_id/q`、total | `GET /services/{id}` | `POST` body resource C → 422；`PATCH` C → 404；DELETE/restore 为 ADMIN-only | `GET /services/{id}/activity` | `Service.resource_id → Resource.cluster_id` |
| T-F027-10 | ServiceEndpoint | `GET /service-endpoints`、`service_id/ip_address_id/q`、total | `GET /service-endpoints/{id}` | `POST` body service C 或 IP C → 422；`PATCH` C → 404；DELETE/restore 为 ADMIN-only | `GET /service-endpoints/{id}/activity` | `ServiceEndpoint.service_id → Service → Resource.cluster_id` |

**矩阵统一断言**：

1. `viewer-ab`/`editor-ab` 对 A/B 的行为与既有角色矩阵一致；对 C 的列表不出现、`total` 不计入；C 详情/Activity 为 `404 NOT_FOUND`，响应无对象字段。
2. 对 C 的 `PATCH`/WRITE 为 `404`；body 显式引用 C 的 Cluster/父对象为 `422 VALIDATION_ERROR`；不返回 C 的 code/name/id/状态/规模。
3. DELETE/RELEASE_IP/RESTORE 在 §23 中仅 ADMIN；非 ADMIN 对 C 调用先被角色门控为 `403 FORBIDDEN{reason:"permission"}`，不预期 `404`。这是既有角色矩阵先于范围的结果，不视为范围缺口；ADMIN 不受限，操作 C 正常。
4. 任一被拒绝写操作后，C 对象状态、`version`、关联、Audit、Activity 均无变化。
5. 对 A/B 的正常写仍成功，并产生既有 Audit/Activity；证明范围只收紧、不放宽/不误伤。

## 3. 验收映射（A1–A23）

| 验收 | 覆盖用例 | 层级/证据 |
| --- | --- | --- |
| A1 ADMIN 全业务域不受限，既有行为无回归 | T-F027-01/02/31/32 | 真实 PG + HTTP + 全量回归 |
| A2 仅授权 A/B 的非 ADMIN 在 8 类列表与聚合视图只看到 A/B | T-F027-01/03–11/33 | 真实 PG + HTTP |
| A3 items/total/分页/过滤一致；无空页 total>0；C 过滤值为空 200 | T-F027-11（并核对 03–10） | 真实 PG + HTTP |
| A4 对 C 的对象详情/Activity 404，无字段泄露 | T-F027-03–10/17/24 | 真实 PG + HTTP |
| A5 对 C 的创建/修改/删除/释放/恢复/分配/绑定/解绑/转移被拒，无残留 | T-F027-03–10/12/25 | 真实 PG + HTTP + DB 终态 |
| A6 跨对象父级派生、未绑定 IP 按归属收敛 | T-F027-06/08/10/12 | 真实 PG + HTTP |
| A7 搜索 4 类 + 关联行 + related_total + total 收敛，匹配/排序/分页不变 | T-F027-13/14 | 真实 PG + HTTP |
| A8 Dashboard counts/networks/容量收敛；零授权全 0/空 200 | T-F027-15/16/20 | 真实 PG + HTTP |
| A9 Activity 未授权 404；完整 Audit 非 ADMIN 403 | T-F027-17/20 | 真实 PG + HTTP |
| A10 零授权列表空/详情写拒绝，不回退全量 | T-F027-01/20（并核对 11/15/16） | 真实 PG + HTTP |
| A11 撤销/角色变更下一请求即时（含 API Key），同请求稳定 | T-F027-21/22/27 | 真实 PG + 两请求/并发 |
| A12 API Key 继承范围；401 先于 403 等不回归 | T-F027-22/30 | 真实 PG + Bearer |
| A13 INACTIVE 不改变授权；软删不生效、恢复自动恢复 | T-F027-19 | 真实 PG + HTTP |
| A14 非 ADMIN 已删对象仍 403；ADMIN 不变 | T-F027-17/18 | 真实 PG + HTTP |
| A15 F014/F023 预校验/写入未授权行级错误、整批失败无残留 | T-F027-28/29 | 真实 PG + multipart |
| A16 `--push` 同口径，预校验阶段失败 | T-F027-28/29/30 | 端点级 F027；真实 Compose 归 F028 |
| A17 错误顺序 401→403→422→404→409；路径 404、body Cluster 422、角色 403 | T-F027-23（并核对 12/22） | 真实 PG + HTTP |
| A18 不泄露未授权 Cluster 信息 | T-F027-24（并核对 11/13–17/20） | 响应全文/错误/导入错误 |
| A19 拒绝写无状态/关联/版本/Audit/Activity 变化；事务边界不变 | T-F027-25/26/27 | 真实 PG + 事务终态 |
| A20 全部路径一次合并整体受限，无部分端点中间态 | T-F027-27/32/33 | 路由清单 + 全量回归 + 并发 |
| A21 既有角色矩阵与完整性不回归 | T-F027-02/14/31/32 | T01–T84 适用子集 |
| A22 F026 授权管理行为不变 | T-F027-01/31/32 | T90/T92/T96/T99 回归 |
| A23 既有页面正确呈现空态/404/错误，不新增功能 | T-F027-34 | **F028-owned**；F027 不计 PASS |

## 4. 用例目录（T-F027-01…34）

> 以下为待执行设计。每例至少使用真实 PostgreSQL；HTTP 用例使用生产 App + TestClient。除非特别说明，`viewer-ab`/`editor-ab` 仅授权 A/B。

### T-F027-01 夹具与范围前置

- 构造 A/B/C、INACTIVE、软删 Cluster、用户、授权、API Key、已删对象。
- 断言 `resolve_access_scope`：`admin.unrestricted=True`；`viewer-ab.cluster_ids == {A,B}`；`viewer-zero.cluster_ids == ∅`；软删 Cluster 不在集合内；INACTIVE Cluster 在集合内。
- 断言 `AccessScope.cluster_predicate`：ADMIN 恒真、零授权恒假、A/B 精确命中、不命中 C。
- 记录后续用例所需 Audit/Activity 基线计数。

### T-F027-02 ADMIN 全业务域不受限

- ADMIN 对 A/B/C 的 8 类列表、详情、Activity、已删对象（`deleted=include|only`）、搜索、Dashboard 均可见。
- ADMIN 可在 C 上完成允许的写操作（含 DELETE/restore/release），行为与 F027 前一致。
- ADMIN 无授权行；范围谓词恒真，不因 C 未授权而 404/空。
- 覆盖 A1、A21、T97 的 ADMIN 部分。

### T-F027-03 Cluster 矩阵

- 列表：A/B 出现，C 不出现，`total` 只计 A/B；`q/code/status/deleted` 组合与 total 一致；`cluster_id=C` 不适用于 Cluster 列表，改用 C 的 code 过滤返回空 200。
- 详情：A/B 200；C 404 且无字段；不存在/非 UUID 仍 404。
- 写：EDITOR 创建 Cluster 维持 201；验证新 Cluster 不自动授予、创建者（非 ADMIN）随后不可见（Q1 窄例外）；EDITOR `PATCH` C → 404；DELETE/restore 非 ADMIN → 403。
- 唯一性窄例外：EDITOR 用与 C 相同的 code 创建 → 409 `CONFLICT`，details 仅 `field:"code"`；不得回显 C 的 name/status/规模。
- Activity：A/B 200；C 404。

### T-F027-04 Resource 矩阵

- 列表/详情/Activity：C 不出现、404；A/B 正常。
- 写：body `cluster=C` 创建 → 422 field `cluster`；`PATCH` C → 404；DELETE/restore 非 ADMIN 403；A/B 写入正常。
- Resource Detail 聚合（hardware/VM/interface/IP/service）不因范围产生额外泄露；主对象不可见时整体 404。

### T-F027-05 Network 矩阵

- 列表/详情/Activity：C 不出现、404；A/B 正常。
- 写：body cluster C → 422；`PATCH` C → 404；DELETE/restore 非 ADMIN 403。
- `GET /networks/{C}/capacity` → 404；A/B 容量正常（F010 §6.9）。

### T-F027-06 IPAddress 矩阵

- 列表/详情/Activity：C 不出现、404；A/B 正常。
- 分配：`POST /ip-addresses` body network C → 422；`auto-allocate` body network C → 422；A/B 正常。
- 绑定/解绑/转移：`PATCH /ip-addresses/{C}` → 404；A 的 IP body interface C → 422；C 的 IP body interface A → 404；A 的 IP 解绑/转移到 A 接口正常。
- 释放/恢复：非 ADMIN 403；ADMIN 正常。
- 未绑定 IP：仍按自身 `cluster_id` 收敛；A 的未绑定 IP 可见，C 的未绑定 IP 不可见。
- F019 逐条绑定：候选 `cluster_id=C` 返回空 200；C 条目直接 PATCH 404，A 条目独立成功。

### T-F027-07 Interface 矩阵

- 列表/详情/Activity：C 不出现、404；A/B 正常。
- 写：body resource C → 422；`PATCH` C → 404；DELETE/restore 非 ADMIN 403。
- 父 Resource 不可见时，Interface 详情/Activity 也不可见；A 的 Resource 下 Interface 正常。

### T-F027-08 IPPool 矩阵

- 列表/详情/Activity：C 不出现、404；A/B 正常。
- 写：body network C → 422；`PATCH` C → 404；DELETE/restore 非 ADMIN 403。
- 父 Network 不可见时，Pool 不可见；A 的 Pool 正常；容量/池边界既有约束不回归。

### T-F027-09 Service 矩阵

- 列表/详情/Activity：C 不出现、404；A/B 正常。
- 写：body resource C → 422；`PATCH` C → 404；DELETE/restore 非 ADMIN 403。
- 父 Resource 不可见时 Service 不可见；A 的 Service 正常。

### T-F027-10 ServiceEndpoint 矩阵

- 列表/详情/Activity：C 不出现、404；A/B 正常。
- 写：body service C 或 IP C → 422；`PATCH` C → 404；DELETE/restore 非 ADMIN 403。
- 父 Service/其 Resource 不可见时 Endpoint 不可见；A 的 Endpoint 正常；同 Cluster IP 约束不回归。

### T-F027-11 列表 items/total/分页/过滤一致性

- 对 8 类列表分别用 A/B/C 数据构造多页：`page_size=1` 翻页，断言各页 items 均可见、`total == 可见对象总数`、不出现“空页但 total>0”。
- `page` 超过总页数：空 `items`，`total` 与过滤条件一致；不是范围导致 total 虚高。
- 过滤值为 C：接受 `cluster_id`/父 ID 的列表返回空 200 `{items:[], total:0}`；不接受该参数的列表用 C 的 q/code 过滤也返回空 200。
- 同一 filters 的 items 与 total 使用同一范围谓词；排序在末页/同刻仍稳定（id ASC 或既有全序）。
- 零授权时每类列表空 200、total=0。
- 覆盖 A2、A3、A10、A18。

### T-F027-12 跨对象归属与父级派生

- Pool←Network：C 的 Network 下 Pool 不可见；body network C 创建 Pool 422。
- Interface/Service←Resource：C 的 Resource 下 Interface/Service 不可见；body resource C 422。
- Endpoint←Service：C 的 Service 下 Endpoint 不可见；body service C 422。
- Endpoint IP：body IP 与 Service 不同 Cluster → 422（既有语义）；IP C + Service A → 422 且不泄露 C；Endpoint C 路径 → 404。
- 未绑定 IP：仅按 `IPAddress.cluster_id`；不因无 Interface/Resource 而回退全量。
- 父对象软删：父不可见/已删除时子对象按既有软删语义不可见；ADMIN 仍可按既有行为查看。
- 覆盖 A6、A18。

### T-F027-13 搜索 4 类候选 + total 收敛

- 对 `q` 同时可命中 A/B/C 的 hostname、cluster code/name、IP、service name 构造数据。
- `GET /search?q=...`：只返回 A/B 对象；每类 `object_type` 候选均收敛；`total` 只计可见结果；分页不出现不可见行。
- `type=resource|cluster|ip_address|service` 四类分别验证；C 的 IP/Service/Cluster/Resource 均不出现。
- 零授权：四类均空 200、total=0，不回退全量。
- 覆盖 A7、A10、A18。

### T-F027-14 搜索关联行/related_total/字段组合/排序不变

- `resource` 行仅加载可见 Resource 的 related（Interface/IP/Network）；C 的关联不出现。
- `related_total` 只计可见关联；截断时 `len(related)=10` 与 `related_total>=10` 语义不变；不可见关联不抬高总数。
- 未绑定 IP 不出现于 related（F018 既有规则）；A/B 变化不改变 F018 字段组合、去重、顶层排序、分页与 total。
- `deleted=include|only` 非 ADMIN 仍 403（先于范围/查询）；ADMIN 行为不变。
- 只读：搜索不产生 Audit/Activity。
- 覆盖 A7、A14、A21。

### T-F027-15 Dashboard counts 收敛与零授权

- A/B/C 各有不同数量 Cluster/Resource/BM/VM/Network；非 ADMIN 的 `counts` 只等于 A+B 的未删计数。
- 修改 A/B/C 数据后 `counts` 随可见数据变化；C 的增删不影响非 ADMIN counts。
- `counts.clusters` 含 INACTIVE 但未删的可见 Cluster；已软删 Cluster 不计；C 的已删/未删均不计。
- 零授权：`counts` 全 0，HTTP 200，不回退全局。
- 覆盖 A8、A10、A18。

### T-F027-16 Dashboard networks/容量收敛

- `networks.items` 只含 A/B 未删 Network；C 不出现；`networks.total` 只计 A/B。
- 每行容量与 `GET /networks/{visible}/capacity` 逐项一致；公式不变；C 的 Network 不参与。
- INACTIVE 可见 Network 仍出现且容量不清零；软删 Network 不出现。
- 零授权：`{items:[], total:0}`，HTTP 200。
- 覆盖 A8、A10、A18。

### T-F027-17 Activity 与完整 Audit

- 8 类对象：A/B 的 Activity 200；C 的 Activity 404，无对象字段/条目泄露。
- Activity 过滤口径沿用既有 `(object_type, object_id)`；范围在取对象前生效，不先列 C 的 Audit 再 404。
- `deleted=true` 且非 ADMIN：仍先 403 `FORBIDDEN{reason:"permission"}`；ADMIN 可按既有行为查看已删对象 Activity。
- 完整 `GET /audit`：VIEWER/EDITOR 403；ADMIN 200。非 ADMIN 不因范围获得 Audit 可见性。
- 覆盖 A9、A14、A18。

### T-F027-18 已删对象、Deleted 聚合与恢复

- 非 ADMIN 对可见 A 的已删对象使用 `deleted=include|only`/`deleted=true`：仍 403（T98），不因范围放宽。
- 非 ADMIN 对 C 的已删对象：权限 403 先于范围；不能通过 404/200 区分 C 对象是否存在。
- ADMIN `GET /deleted` 可见 8 类已删对象；非 ADMIN 403。
- ADMIN 恢复 A/C 已删对象正常；非 ADMIN 恢复请求 403（RESTORE 角色门控）。恢复后 ADMIN 可查；非 ADMIN 对 A 恢复对象（若集群可见）按既有可见性；C 仍不可见。
- 恢复不自动恢复关联对象（既有 F015 行为）。
- 覆盖 A14、A13、A17。

### T-F027-19 INACTIVE、软删与恢复授权生命周期

- 将 A 置 INACTIVE：授权行不变，`viewer-ab` 仍可见 A 的对象；切换回 ACTIVE 可见集合不变。
- 软删 A：授权行保留但 scope 不含 A；`viewer-ab` 的 A 对象列表空、详情/写 404；C 仍不可见。
- 恢复 A：原授权自动生效，A 对象重新可见；无需重新授予。
- 软删期间撤销 A 授权后恢复 A：A 不再可见（F026 T-F026-17 基座）；重新授予后可见。
- INACTIVE 不自动放开 C，也不改变零授权用户。
- 覆盖 A13、A10。

### T-F027-20 零授权默认拒绝

- `viewer-zero`/`editor-zero`：8 类列表空 200、total=0；搜索空；Dashboard 全 0/空；A/B/C 详情/Activity 全部 404。
- 写：EDITOR 零授权 body A/B/C 引用 → 422；路径对象 → 404（WRITE 权限存在，范围拒绝）；DELETE/release/restore 仍 403（角色）。
- 不存在“列表空但详情可见”或“搜索空但 Dashboard 非 0”的回退。
- 覆盖 A10、A8、A9、A18。

### T-F027-21 撤销/角色变更下一请求即时

- `viewer-ab` 登录后先访问 A 成功；ADMIN 撤销 A 授权；下一请求立即看不到 A、详情 404、搜索/Dashboard 同步，无需重新登录。
- 重新授予 A；下一请求立即恢复。
- 将 `editor-ab` 降级 VIEWER：下一请求写能力按角色矩阵立即收紧（403），可见范围仍按既有授权；升回 EDITOR 立即恢复写。
- 同一请求内 scope 快照稳定（复用 F026 `request.state` 基座；F027 不新增缓存）。
- 覆盖 A11、A12。

### T-F027-22 API Key 继承与认证/授权顺序

- 用 `viewer-ab`/`editor-ab` 的 API Key 调用列表/详情/搜索/Dashboard：范围与 Cookie 一致。
- 撤销授权后，下一请求 API Key 立即收敛；角色变更同理。
- 零授权用户 API Key：列表空、详情 404。
- 缺失/非法/已吊销/过期 Key → 401 `AUTH_REQUIRED`，先于 403/404/422；失效 Key 不因目标对象存在与否产生不同响应。
- 非 ADMIN Key 调授权管理端点仍 403；ADMIN Key 可管理（F026 不回归）。
- 覆盖 A11、A12、A17。

### T-F027-23 错误顺序与状态映射

对同一路径/资源构造多类错误，断言顺序严格为 **401 → 403（角色/CSRF/VIEW_DELETED）→ 422（请求体/参数）→ 404（路径对象不存在/不可见）→ 409（唯一/版本/引用）**：

- 匿名 + C 对象 + 非法 body → 401，不泄露 C。
- VIEWER 写 C → 403（角色先于 404）；VIEWER `deleted=include` → 403。
- EDITOR body cluster C + 非法字段 → 422（请求体先于路径对象）；EDITOR body 合法 cluster C → 422（语义/范围）。
- EDITOR 路径 C 对象 + 合法 body → 404（不是 409/422）。
- 路径 C 对象不存在/非 UUID → 404；body Cluster 不存在/C 未授权 → 422。
- 范围优先于唯一性/重叠/引用：对 C 的修改即使会触发唯一/重叠/引用冲突，也返回 404；body 引用 C 不会通过 409 泄露 C 的存在。
- Q1 窄例外：EDITOR 创建 Cluster code 与隐藏 C 重复 → 409 仅 `field:"code"`，不回显 C 信息。
- 覆盖 A17、A18。

### T-F027-24 不泄露未授权 Cluster 信息

- 收集列表/详情/搜索/Dashboard/Activity/导入错误/写错误响应全文与 headers；断言不含 C 的 `id`/`code`/`name`/`status`/规模/计数/容量。
- 详情/写 404 只含统一错误信封，不含对象字段、父对象/Cluster 快照。
- 列表/搜索 `total`、Dashboard `counts`/`networks.total` 不因 C 数据规模变化。
- 导入错误只含行号/字段/原因，不回显 C 的 Cluster/Network code/name。
- 被拒绝的 Cluster 创建（Q1）仅 `field:"code"`。
- 覆盖 A18。

### T-F027-25 被拒绝写无业务/Audit/Activity 残留

- 对每类对象记录 C 目标及 A 可见父对象的 `version`、关联、Audit 计数、Activity 计数。
- 执行被拒绝的 create/update/bind/unbind/transfer/delete/release/restore（按角色可达路径）；断言：目标行与关联不变、版本不增、无新 Audit、无新 Activity、无新对象。
- 对 body 引用 C 的创建：A 中不产生任何对象，也不产生 Audit。
- 对 A 的成功写对照组：确实产生既有审计/Activity，证明检测方法有效。
- 覆盖 A19、A5。

### T-F027-26 事务边界与回滚

- 创建（含 Audit 同事务）：成功写入后业务行与 Audit 同时存在；模拟/触发失败时同时回滚，无孤儿 Audit。
- 修改/绑定/解绑：同一事务内版本、关系、Audit 一致；失败无部分变更。
- 导入：整批成功才提交；存在 C 行时整批回滚，无 Resource/Interface/IP/Audit 残留。
- 读取/搜索/Dashboard/Activity：无写副作用，不产生 Audit。
- 覆盖 A19、A20。

### T-F027-27 并发与请求边界

- 使用 `committed_engine` 两条独立连接：
  - 请求 A 已解析 scope 后，另一连接撤销授权并提交；请求 A 仍按同请求快照完成，下一请求立即拒绝（下一请求即时）。
  - 两个并发写同一对象：既有乐观锁/唯一/版本冲突语义不变；范围校验先于唯一性/重叠/引用检查，不因并发产生 409 泄露 C。
  - 并发绑定/解绑/转移：结果符合既有约束，无重复绑定/部分残留。
- 第三方连接做终态断言：版本、关联、Audit、Activity、行数一致。
- 覆盖 A19、A20、A11。

### T-F027-28 F014 资源导入范围行错误与原子性

- CSV/xlsx 含 A 行 + C 行（C 的 cluster code/name 来自夹具）：
  - `POST /imports/resources/validate`：200，`error_count>=1`，C 行有 1-based 行号、字段（`cluster`/父字段，按 Contract）、原因非空；不写 Audit/业务数据。
  - `POST /imports/resources`：422 `IMPORT_VALIDATION_FAILED`，details 同一行错误；整批失败；A 行也不落库；无 Audit/Activity 残留。
- 范围错误优先于唯一性/主机引用错误：C 行即使同时构成重复 hostname/Host 缺失，返回范围原因，不通过唯一/引用错误泄露 C。
- 合法 A/B 批次：201，created/total 正确，Audit 正常。
- 零授权 IMPORT 用户：所有行范围错误，整批失败。
- 覆盖 A15、A16（端点级）、A19。

### T-F027-29 F023 资源+网卡+IP 导入范围行错误与原子性

- 26 列模板含 A 行 + C 行（C 的 cluster/network/host 引用）：
  - `validate`：200，C 行报行号 + 字段（`cluster`/`network`/`host`/`ip` 适用字段）+ 原因；无副作用。
  - 写入：422 `IMPORT_VALIDATION_FAILED`，整批回滚；无 Resource/Interface/IPAddress/Audit 残留。
  - 范围错误优先于重复/越界/跨 Cluster 等既有行错误；错误不泄露 C 的 code/name/规模。
- 合法 A/B 批次：201，`created`/`interfaces_created`/`ip_addresses_created` 与既有口径一致。
- 零授权 IMPORT 用户：整批范围失败。
- 覆盖 A15、A16（端点级）、A19。

### T-F027-30 `--push` 同口径（端点级 + F025 契约）

- 用 API Key 走 F023 的 `validate` → 写入两步；含 C 行时 `validate` 即失败，未调用写入；API Key 继承范围，撤销授权后下一请求 401/范围失败。
- 复用 F025 既有 `--push` 单元测试，确认脚本调用同一 F023 端点、Key 不泄露、预校验失败阻断写入。
- 真实 Compose/Nginx 下的 `--push` 端到端、脚本退出码与网络行为由 **F028** 执行；F027 不把 F028 结果计入 PASS。
- 覆盖 A16、A12。

### T-F027-31 既有角色矩阵/完整性关键抽样

- 运行既有后端测试中的关键抽样（真实 PG）：
  - T01–T05 唯一性、T06–T07 IP 分配、T10 跨 Cluster 绑定、T13 Cluster code、T14–T18 Network/Pool/IP、T20 Interface、T22 Endpoint、T23 引用删除、T24 恢复；
  - T25 角色矩阵（EDITOR 可导入/解绑，不可删除/释放/恢复；VIEWER 不可 Audit）、T26 版本冲突、T29 INACTIVE、T36 Audit 不删除；
  - T42–T49 API Key、T50–T53 搜索、T54–T58 F019。
- 断言 F027 范围只收紧权限，不放宽唯一/重叠/软删/状态/关系约束；既有 409/422 语义不变。
- 覆盖 A1、A21。

### T-F027-32 全量回归与 F026 管理回归

- 运行 `python3 -m pytest -q`（真实 PG，按仓库既有命令）；F027 新增测试之外，既有后端测试全绿。
- 单独回归 F026：T90/T92/T96/T99（授权管理、审计、软删 Cluster 拒绝、迁移回填/幂等）。
- 检查迁移 head 仍为 `0015_user_cluster_authorizations`；无 F027 新迁移/新表/新索引。
- T01–T84 适用子集按第 5 节执行；T59–T63/T73–T84 不属于后端 F027 回归范围。
- 覆盖 A1、A20、A21、A22。

### T-F027-33 合并完整性/静态路由清单

- 扫描全部既有业务路由：8 类列表/详情/写/Activity、搜索、Dashboard、Deleted、Audit、F014/F023 导入均消费 `get_access_scope`/范围谓词；无端点仍全局可见。
- 不存在第二套 scope 解析、模块级缓存或隐式全量回退；`AccessScope.unrestricted` 只在 ADMIN。
- 无 Schema/迁移差异；既有 Contract 的路径/响应字段/error code 未因 F027 改变。
- 覆盖 A20、A1。

### T-F027-34 F028 前端/Compose 证据（委托，不计 F027 PASS）

- **F028-owned**：真实 Compose（Nginx/Frontend/FastAPI/PostgreSQL）、浏览器 DOM、空态/404/错误呈现、焦点/Esc/双击/窄屏、T85–T99 端到端、T01–T84 关键真实部署回归。
- F027 只提供真实 PG + 生产 App 的服务端证据；A23 不在 F027 计 PASS。
- 若合并前需要浏览器证据，由协调器按 F028 调度，本报告不代填。

## 5. T01–T84 回归子集

| 组 | 范围 | 执行归属 |
| --- | --- | --- |
| T01–T05、T10、T13 | 唯一性、跨 Cluster、Cluster code | F027 后端抽样 + 全量 |
| T06–T07、T14–T18、T30–T35 | IP 分配、Network/Pool、容量、边界 | F027 后端抽样 + 全量 |
| T08–T09、T19–T24 | VM/Host、Interface、引用删除、恢复 | F027 后端抽样 + 全量 |
| T25、T26、T29、T36 | 角色矩阵、版本、INACTIVE、Audit | F027 后端抽样 + 全量 |
| T27–T28、T37–T41 | 导入、默认值、名称归一化 | F027 后端抽样 + 全量 |
| T42–T49 | API Key | F027 后端抽样 + 全量 |
| T50–T53 | 搜索/关联字段 | F027 后端抽样 + 全量 |
| T54–T58 | F019 接口侧绑定服务端语义 | F027 后端抽样 + 全量 |
| T59–T63 | 二次确认对话框 | **F028 浏览器** |
| T64–T72 | F023 统一导入 | F027 后端抽样 + 全量 |
| T73–T84 | F025 采集脚本/`--push` | F025 回归 + **F028 Compose** |

## 6. 数据库、接口、前端、集成结果

本阶段**未执行**，以下为执行时的检查项：

| 层 | 检查项 | 结果 |
| --- | --- | --- |
| 数据库 | 真实 PG；无 F027 Schema/迁移；F026 约束/授权行不回归；范围查询正确性 | NOT TESTED（TD-1） |
| 接口 | 8 类 list/detail/write/activity；搜索；Dashboard；Deleted；Audit；导入 | NOT TESTED（TD-1） |
| 前端 | F027 无新功能；既有页面空态/404/错误 | NOT_REQUIRED（F028-owned） |
| 集成 | 生产 App + 真实 PG + Cookie/API Key；Compose/浏览器 | NOT TESTED（TD-1；F028） |

## 7. Defects

本阶段为 TEST_DESIGN，未执行实现，**无实现缺陷记录**。后续 TEST 发现的缺陷按公共规范记录 Owner 与分级。

## 8. 未验证项与观察项

| ID | 级别 | 事项 | Owner | 阻塞 TD-1 | 处理 |
| --- | --- | --- | --- | --- | --- |
| OBS-F027-1 | MEDIUM | F027 实现尚未提交且无实现报告，T-F027-01…33 均未执行 | Backend/Tester | 否（设计阶段正常） | TD-2 后执行 |
| OBS-F027-2 | MEDIUM | F027 附录声明的既有 Contract errata 是否已回写各域文档待 Architect 确认 | Architect/Contract | 否 | TD-2 关闭；以 F027 附录为测试依据 |
| OBS-F027-3 | LOW | F014/F023 范围行错误的 `reason` 字面未固定 | Architect/Contract | 否 | TD-2 固定，或按“非空+不泄露”断言 |
| OBS-F027-4 | LOW | F028 承接 Compose/浏览器与 T59–T63/T73–T84 证据 | F028/协调器 | 否 | 不计入 F027 PASS |
| OBS-F027-5 | LOW | 非 ADMIN 的 DELETE/RELEASE_IP/RESTORE 先被角色 403，无法观察范围 404；这是 §23 既有矩阵，不是缺口 | Tester | 否 | 用例按 403+无残留断言 |

## 9. 结论

- **TEST DESIGN READY**：A1–A23 均有映射；8 类对象矩阵、搜索、Dashboard、导入、API Key、零授权、生命周期、错误顺序、无泄露、无残留、并发/事务边界与回归子集均已定义。
- 本结论**不代表任何测试通过**；执行前必须满足 TD-2，且 F028 的 Compose/浏览器证据不由本报告代填。

GIT: NONE
## Test Execution（TEST-1）

- **版本**：TEST-1（2026-10-22）
- **角色**：Tester（TEST）
- **Feature**：F027（P0，M18）
- **结论**：**READY FOR REVIEW**
- **依据**：requirements revision 11 §23.2、§31 T85–T99；F027 product A1–A23；F027 architecture v1；`docs/api/F027.md` v1；F027 TD-1；`docs/features/F027/implementation.md`（BACKEND COMPLETE）；F026 基座与回归。
- **交付范围**：只写本报告。未修改业务实现、Schema、Contract 或计划；独立探针位于仓库外的 `/tmp/f027probe/`，不进入提交。

### TE-1 环境与执行基线

| 项 | 值 |
| --- | --- |
| 数据库 | 真实 PostgreSQL（`TEST_DATABASE_URL`），库名 `csm_test`（含 `test`，通过 DB-D10 双守卫）；未设置 `DATABASE_URL` |
| 迁移 head | `0015_user_cluster_authorizations`；F027 无新迁移（独立探针断言 head 未变） |
| 应用 | 生产 `create_app()` + 真实依赖，仅覆盖 `get_db`；真实 HTTP（`TestClient`） |
| 身份 | Bootstrap ADMIN、VIEWER/EDITOR、零授权账号、API Key（含已吊销 Key）；真实 Cookie/Bearer |
| 执行方式 | 串行；未与其它写任务并行；先跑目标套件，再跑全量回归，最后跑独立探针（探针在回归结束后执行，避免共享测试库冲突） |
| DB 所有者 | 连接角色 `csm` 为超级用户，`test_migrations` V3b（非超级用户 owner）按既有条件跳过 |

### TE-2 TD-2 执行前复核结论

| TD-2 项 | 结论 | 证据 |
| --- | --- | --- |
| 1 实现完成、受保护路由注入 `get_access_scope` | CLOSED | 实现报告存在；静态枚举 64 条业务路由（含 `/networks/{id}/capacity`），依赖树全部包含 `get_access_scope`；仅 2 个只读模板端点例外（无数据） |
| 2 Contract errata 同步状态 | **PARTIAL（Architect 项）** | 行为以 Architect 签核的 `docs/api/F027.md` v1 为规范依据，未发现字面冲突；但附录 §5 声明“各域 Contract 增加交叉引用”尚未回写各域文档（见 OBS-F027-T1），不阻塞行为验证 |
| 3 导入行错误文案口径 | CLOSED（采用宽松口径） | 实现后实测 `row`（1-based，含表头）、`field="cluster"`、`reason` 非空；未绑定固定文案，按 TD-2 退让条件断言 |
| 4 F028 证据边界 | CLOSED | Compose/浏览器/DOM 与 A23 仍归 F028，本报告不计 PASS |
| 5 真实测试库与迁移 head | CLOSED | 真实 PG；head `0015_user_cluster_authorizations`；F027 无新迁移 |

### TE-3 执行命令与结果

独立执行（不复制开发者结果）：

```bash
# 1) F027 目标套件 + F026 回归
export TEST_DATABASE_URL='postgresql+psycopg://csm:csmtestpw@127.0.0.1:55432/csm_test'
unset DATABASE_URL
python3 -m pytest -q tests/integration/test_f027_access_scope.py \
  tests/integration/test_cluster_authorizations.py
# 17 passed in 34.53s   (F027 9 + F026 8)

# 2) 全量回归（串行）
python3 -m pytest -q
# 717 passed, 2 skipped in 1147.50s (0:19:07)
# skipped: F016_ACCEPTANCE=1 未启用；test_migrations V3b（当前 DB owner 为超级用户）

# 3) 独立探针（仓库外，生产 App + 真实 PG）
python3 -m pytest -q /tmp/f027probe/test_f027_probe.py
# 16 passed in 45.84s
```

独立探针用例（均真实 PG + 生产 App；仓库外夹具通过模块方式加载仓库 `tests/conftest.py`，因此不触发 `tests/integration` 的兼容覆盖）：

| 探针 | 覆盖 | 结果 |
| --- | --- | --- |
| `pagination_total_and_hidden_filters` | 8 类列表 `page_size=1` 翻页、越界页空 items 且 total 稳定、隐藏 `cluster_id`/父 ID/code 过滤空 200 | PASS |
| `cluster_write_scope_and_q1_conflict` | EDITOR PATCH 隐藏 Cluster 404；Q1 code 冲突仅 `{reason:unique_conflict,field:"code"}`；EDITOR 建 Cluster 201、创建者不可见、不自动授权 | PASS |
| `capacity_and_auto_allocate_scope` | 隐藏 Network `/capacity` 404；可见 200；auto-allocate 隐藏 Network 422 `field:"network"`；可见 AUTO 池分配 201 | PASS |
| `unbound_ip_scope_and_binding` | 未绑定 IP 仅按自身 `cluster_id` 收敛；跨 Cluster 绑定 422 `field:"interface"`；同 Cluster 绑定 200 | PASS |
| `search_related_and_deleted_gate` | `related_total`/`related` 随可见绑定变化；`total==len(items)`；隐藏 code 搜索 0；`deleted=include` 非 ADMIN 403 / ADMIN 200 | PASS |
| `dashboard_counts_capacity_coherence` | `counts`/`networks.total` 仅可见；逐行容量与 `/networks/{id}/capacity` 一致；隐藏侧增删不影响，可见侧增删即时反映 | PASS |
| `import_rollback_without_audit` | F014 行错误 200（row/field/reason）、写入 422 整批回滚、Resource 与 AuditLog 计数不变、合法批次 201 且增 Audit | PASS |
| `zero_grants_everywhere` | 零授权 8 类列表空、详情/Activity 404、搜索空、Dashboard 全 0、body 引用 422、路径写 404、DELETE 403；零授权 API Key 同口径 | PASS |
| `api_key_and_auth_order` | API Key 继承范围、撤销立即收敛、吊销/非法 Key 401（AUTH_REQUIRED）、匿名隐藏详情 401（非 404）、VIEWER 写隐藏对象 403（reason=permission） | PASS |
| `error_precedence_and_lifecycle` | 422（非法 body）→404（隐藏路径，含 version 过期仍 404，不落 409）→409（可见对象 version 冲突含 `current_version`）；INACTIVE 保持可见；软删隐藏、软删期间撤销后恢复仍隐藏、重新授予恢复可见 | PASS |
| `role_gates_and_f026_management` | 非 ADMIN `/audit`、`/deleted`、`deleted=only`、`deleted=true` 均 403；ADMIN 200；F026 授权管理仅 ADMIN，授予后立即生效 | PASS |
| `static_dependency_coverage` | 探针未启用兼容覆盖（`get_access_scope` 不在 `dependency_overrides`）；64 条业务路由依赖树均含 `get_access_scope`，缺失列表为空 | PASS |
| `migration_head_unchanged` | Alembic head 仍为 `0015_user_cluster_authorizations` | PASS |
| `no_hidden_identifier_leak` | 列表/隐藏过滤/8 类详情与 Activity/搜索/Dashboard/容量/7 类 PATCH/创建 422/导入 validate 与 write 全文均不含隐藏 Cluster 的 id/code/name；404 信封仅 `error` | PASS |
| `scope_snapshot_is_per_request` | 请求内停驻时提交撤销授权：该请求仍按已解析快照返回 total=2；下一请求 total=1（逐请求解析、同请求稳定） | PASS |
| `import_with_api_key_endpoint_level` | API Key 走 F014 validate→write：隐藏行预校验 200 报错、写入 422 整批回滚无残留；合法批次 201（`--push` 端点级） | PASS |

### TE-4 验收映射（A1–A23 / T85–T99）

| 验收 | 结果 | 主要证据 |
| --- | --- | --- |
| A1 ADMIN 全业务域不受限、无回归 | PASS | F027 套件 ADMIN 三维度核对；探针 ADMIN 容量/软删/恢复/授权；全量回归 717 passed |
| A2 仅授权 A/B 的 8 类列表与聚合只含 A/B | PASS | F027 套件 + 探针列表/翻页/搜索/Dashboard |
| A3 items/total/分页/过滤一致 | PASS | 探针 `pagination_total_and_hidden_filters`（8 类） |
| A4 隐藏对象详情/Activity 404 且无字段泄露 | PASS | F027 套件 + 探针 `no_hidden_identifier_leak` |
| A5 隐藏对象的创建/修改/删除/释放/恢复/分配/绑定/解绑/转移被拒且无残留 | PASS | F027 套件写矩阵 + 探针自动分配/绑定/错误顺序 + 回归角色矩阵 |
| A6 跨对象父级派生、未绑定 IP 收敛 | PASS | F027 套件 422 矩阵 + 探针未绑定 IP/转移 |
| A7 搜索 4 类 + 关联行/`related_total`/`total` 收敛 | PASS | F027 套件四类 + 探针关联总数与 `total==len(items)` |
| A8 Dashboard counts/networks/容量收敛、零授权全 0 | PASS | 探针 `dashboard_counts_capacity_coherence`、`zero_grants_everywhere` |
| A9 Activity 404、完整 Audit 非 ADMIN 403 | PASS | F027 套件 Activity + 探针 `role_gates_and_f026_management` |
| A10 零授权默认拒绝、无回退 | PASS | 探针 `zero_grants_everywhere`（8 类 + 搜索 + Dashboard + 读写） |
| A11 撤销/角色变更下一请求生效（含 API Key）、同请求稳定 | PASS | F027 套件 + 探针 `api_key_and_auth_order`、`scope_snapshot_is_per_request` |
| A12 API Key 继承范围、401 先于 403 | PASS | 探针 `api_key_and_auth_order`（401/403/吊销/非法 Key） |
| A13 INACTIVE 不改授权、软删失效、恢复复原 | PASS | 探针 `error_precedence_and_lifecycle`、F027 套件软删/恢复 |
| A14 非 ADMIN 已删对象仍 403，ADMIN 不变 | PASS | 探针 `role_gates_and_f026_management`；全量回归 deleted/restore 套件 |
| A15 F014/F023 行级范围错误与整批回滚 | PASS | F027 套件两导入 + 探针 `import_rollback_without_audit`（含 Audit 计数不变） |
| A16 `--push` 同口径（端点级） | PASS（端点级） | 探针 `import_with_api_key_endpoint_level`；真实 Compose 归 F028 |
| A17 错误顺序 401→403→422→404→409 | PASS | F027 套件 + 探针 `error_precedence_and_lifecycle`、`api_key_and_auth_order` |
| A18 不泄露未授权 Cluster 信息 | PASS | 探针 `no_hidden_identifier_leak`（46 个响应全文） |
| A19 拒绝写无状态/版本/Audit/Activity 变化 | PASS | F027 套件（version/Audit 计数）+ 探针导入无 Audit 残留 |
| A20 全部路径一次合并整体受限 | PASS | 探针静态路由覆盖 64 条；全量回归无局部中间态失败 |
| A21 既有角色矩阵与完整性不回归 | PASS | 全量回归 717 passed（T01–T84 适用子集） |
| A22 F026 授权管理行为不变 | PASS | F026 套件 8 passed（含迁移/回填、撤销历史、软删拒绝）+ 探针角色门控 |
| A23 既有页面空态/404/错误呈现 | NOT_REQUIRED（F028-owned） | 本报告不计 PASS；F027 仅服务端证据 |

| 需求项 | 结果 | 说明 |
| --- | --- | --- |
| T85 按 ID 读 C 对象 404 不泄露 | PASS | 8 类详情/Activity 404；全响应扫描无 C id/code/name |
| T86 C 上新增/修改/删除/释放/恢复被拒，A/B 正常 | PASS | 写矩阵：路径 404、body 422、DELETE/RELEASE/RESTORE 非 ADMIN 403；A/B 写成功 |
| T87 列表与 total 仅可见、无空页 total>0 | PASS | 8 类翻页一致性探针 |
| T88 搜索（含 §17.1 关联行）与 Dashboard 仅可见 | PASS | 搜索 related/related_total/total；Dashboard counts/networks/容量 |
| T89 导入含未授权行整批失败、行号+原因、无残留 | PASS | F014/F023 套件 + 探针 Audit/Resource 计数 |
| T90 仅 ADMIN 管理授权、不新增权限项 | PASS | F026 套件 + 探针非 ADMIN 403；权限枚举未变 |
| T91 撤销即时生效、API Key 同样收敛 | PASS | 探针 Cookie 与 Bearer 双载体 |
| T92 授予/撤销写 Audit 可被 ADMIN 查询 | PASS | F026 套件 `test_grant_list_revoke_regrant_and_audit` |
| T93 零授权非 ADMIN 不回退全量 | PASS | 探针 `zero_grants_everywhere` |
| T94 API Key 继承范围、401/失效 Key 不泄露存在性 | PASS | 探针 `api_key_and_auth_order` |
| T95 INACTIVE/软删/恢复不改变授权集合 | PASS | 探针生命周期 + F027 套件软删/恢复 |
| T96 不存在/已软删 Cluster 授权被拒绝 | PASS | F026 套件 `test_soft_deleted_cluster_history_and_restore`、`test_grant_validation` |
| T97 角色矩阵与完整性不回归 | PASS | 全量回归 717 passed |
| T98 非 ADMIN 任何范围不可见已删对象 | PASS | 探针 `deleted`/`deleted=true`/`deleted=only` 403；ADMIN 200 |
| T99 迁移回填/幂等、真实 PG up/down/up | PASS（F026 基座 + head 未变） | F026 套件迁移/回填用例通过；F027 无新迁移，head 断言通过；V3b 非超级用户 owner 用例按既有条件跳过 |

### TE-5 TD-1 用例执行状态

| 用例 | 结果 | 说明 |
| --- | --- | --- |
| T-F027-01…26 | PASS | 见 TE-3/TE-4；F027 套件 9 例 + 16 个独立探针覆盖，无 BLOCKED |
| T-F027-27 并发与请求边界 | PASS（有边界说明） | 确定性快照探针（请求内撤销仍按旧快照、下一请求立即收敛）+ 全量回归既有并发/锁测试；未做高并发压测 |
| T-F027-28/29/30 导入与 `--push` 端点级 | PASS | F014/F023 套件 + 探针（Cookie 与 API Key 两种载体） |
| T-F027-31/32 角色抽样与全量回归 | PASS | 717 passed, 2 skipped；F026 8 passed |
| T-F027-33 路由清单与静态检查 | PASS | 64 条业务路由全覆盖；无第二解析器/缓存/隐式回退 |
| T-F027-34 F028 前端/Compose | NOT_REQUIRED | F028-owned，未计入 PASS |

### TE-6 数据库 / 接口 / 前端 / 集成

| 层 | 检查 | 结果 |
| --- | --- | --- |
| 数据库 | 真实 PG；无 F027 Schema/迁移；head 未变；F026 约束与授权行回归 | PASS |
| 接口 | 8 类 list/detail/write/activity、搜索、Dashboard、容量、导入、Deleted、Audit、API Key | PASS（详见 TE-3/TE-4） |
| 前端 | F027 无新功能；既有空态/404/错误呈现 | NOT_REQUIRED（F028） |
| 集成 | 生产 App + 真实 PG + Cookie/Bearer；导入两步流程；同请求快照 | PASS |
| 集成（Compose/浏览器） | Nginx/Frontend/真实部署 DOM、T85–T99 端到端 | NOT TESTED（F028） |

### TE-7 兼容覆盖与“无默认全量”核实

- `backend/tests/conftest.py:auth_app` 的 `get_access_scope` 覆盖为 **测试夹具专用**：
  - 仅当测试文件路径包含 `tests/integration` 且文件名不是 `test_cluster_authorizations.py` / `test_f027_access_scope.py` 时生效；
  - F026/F027 两套件实测按真实范围断言并通过（若被覆盖，`total` 会是 3 而非 2）；
  - 仓库外探针实测 `get_access_scope` 不在 `dependency_overrides` 中；
  - `app/` 下无任何 `dependency_overrides`，生产 `create_app()` 不含该覆盖。
- 生产无“无约束默认”：`AccessScope(unrestricted=True)` 仅出现在 `resolve_access_scope` 的 ADMIN 分支；64 条业务路由全部注入 `get_access_scope`；导入内部两处 `resolve_cluster` 未传 scope 的调用点随后显式执行 `scope.allows()` 校验。
- 观察项：`scope_filters.normalize(None)` 将 `None` 视为 unrestricted，且 `app/services` 下 82 处保留 `scope=None` 默认参数（供内部/测试直调）。当前无可达生产路径绕过范围，但遗漏传参将静默放开范围（见 OBS-F027-T2）。

### TE-8 Defects

未发现实现缺陷。无 BLOCKER / HIGH / MEDIUM 实现缺陷，无需 RETURN TO IMPLEMENTATION。

| ID | Severity | Layer | Location | 证据/期望与实际 | 影响 | Owner | 必须修复 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| OBS-F027-T1 | MEDIUM | Docs/Contract | `docs/api/F027.md` §5 与 `docs/api/F004/F007/F008/F009/F010/F011/F012/F013/F014/F023.md` | 附录声明“各域 Contract 增加交叉引用”，`grep F027 docs/api` 仅 `F026.md` 命中；F027 附录本身为签核规范且无字面冲突 | 规范分散在附录，读者可能只读旧域文档 | Architect / Contract | 否（建议合并前确认并补齐引用；不阻塞行为验证） |
| OBS-F027-T2 | LOW | Backend（防御性） | `app/services/scope_filters.py` `normalize()` 与各服务 `scope=None` 默认 | `None` 等价 unrestricted；当前所有路由均传真实 scope，无可达绕过路径 | 未来新增调用方若漏传会静默放开全量 | Backend / Architect | 否（建议改为显式必填或 sentinel） |
| OBS-F027-T3 | MEDIUM | 测试基础设施 | `backend/tests/conftest.py:auth_app` 路径后缀判定 | 覆盖按“目录 + 文件名排除”生效；新增的既有目录集成测试会自动获得 unrestricted | 未来新增测试可能掩盖范围回归 | 协调器 / Backend | 否（建议改用显式 pytest marker 或 opt-in fixture） |
| OBS-F027-T4 | LOW | 测试证据边界 | F028 范围 | Compose/Nginx/浏览器、A23、T85–T99 真实部署端到端未执行 | 无（按计划归 F028） | F028 / 协调器 | 否 |

> 说明：测试过程中观察到的以下行为均为**既有契约/既有语义**，不是缺陷：Cluster code 唯一冲突 409 的 `details` 形状为 `{reason:"unique_conflict", field:"code"}`（F003 既有，符合 F027 附录 Q1“仅返回 field:code”）；非空 Cluster 软删返回 409 `reference_exists`（既有 F003 语义，软删生命周期改用空 Cluster 验证）；自动分配需池 `allocation_mode=AUTO`（既有 F009 语义）。

### TE-9 未验证项与 F028 边界

| 项 | 原因 | 归属 |
| --- | --- | --- |
| 真实 Compose（Nginx/Frontend/FastAPI/PG）、浏览器 DOM、空态/404/错误呈现、T59–T63 对话框、T85–T99 端到端 | 不在 F027 服务端范围 | F028 |
| F025 `--push` 脚本真实网络行为/退出码 | 需真实部署环境；本次仅验证 F023 端点级与 F025 既有单测（全量回归） | F028 |
| F016 真实部署验收 | 环境未启用 `F016_ACCEPTANCE=1`，按既有条件跳过 | F016/F028 |
| `test_migrations` V3b（非超级用户 owner 的 up/down/up） | 测试库 owner 为超级用户，按既有条件跳过；F027 无新迁移 | 协调器 |
| 高并发压测（数十并发请求/争用） | 只做确定性快照竞态与既有并发套件，未做压力测试 | 后续可选 |
| 导入行错误 `reason` 固定文案 | 按 TD-2 退让条件只断言非空 + 不泄露 | 已关闭 |
| project-state 一致性校验 | 本任务未修改计划/状态文件，无需触发 | — |

### TE-10 结论

- A1–A22 全部 PASS；A23 与真实 Compose/浏览器证据按计划归 F028（NOT_REQUIRED，不计 PASS）。
- T85–T99 在 F027 服务端范围内全部 PASS；T99 的 F027 部分为“无新迁移 + head 未变 + 全量迁移/回归通过”。
- 全量回归 717 passed / 2 skipped；F026 回归 8 passed；独立探针 16 passed；未发现需修复的实现缺陷。
- 未验证项已明确列出，未将未执行检查计入 PASS。
- **Status: READY FOR REVIEW**（OBS-F027-T1/T3 为 Architect/协调器后续项，不阻塞本阶段结论）。

GIT: NONE
