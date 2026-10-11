# F012 Service Endpoint 监听端点 — Test Report

本文件同时承载 TEST_DESIGN 与 TEST（TEST 阶段在同一文件追加执行结果）。两阶段分别记录版本、结论与证据；TEST_DESIGN 不填充执行 PASS。

---

## Test Design

- **版本**：TD-1
- **日期**：2026-10-11
- **角色**：Tester（TEST_DESIGN 模式）
- **结论**：`TEST DESIGN READY`（TD-1）
- **依据**：
  - `docs/product/requirements-v3.md` revision 3（§4、§4.1、§5、§13/§13.3、§14、§15、§16、§17、§18、§19、§20、§21、§22、§23、§25–§28、§31 T22/T23/T24/T25/T26/T37/T40/T41、§32、§33、§35.2 Q06/Q10-A、§35.3 D01/D02）
  - `docs/features/F012/product.md`（PRODUCT `READY FOR ARCHITECT`；A1–A21、I-1–I-7、明确排除项）
  - `docs/features/F012/architecture.md`（ARCHITECTURE `READY FOR DESIGN`；§1 实体、§2 数据完整性、§3 分工、§4 API 裁定、§5 归属/唯一、§6 引用检查、§7 数据库影响、§8 D01 v11、§9 验证策略、DR-155–DR-170）
  - `docs/api/F012.md`（文件头标 **READY v1**（Architect 2026-10-09）；7 端点、字段契约 §2、错误码 §1.2 复用无新 reason、分页排序过滤 §4、软删/恢复 §5/§6、校验顺序 §6、并发 §7、审计白名单 §8、双 provider 与 `object_type` 统一 §1.2/§9）
  - `docs/api/F010.md` v1（`register_ip_address_reference_checker` 挂钩、引用列表口径；**errata-03 未落地**：§1.2 仍为 `object_type:"endpoint"`）、`docs/api/F011.md` v1（`register_service_reference_checker` 扩展点、`object_type:"service_endpoint"`）
  - `docs/database/f010-ip-address.md` v1（DB-D111–D127）、`docs/database/f011-service.md` v1（DB-D128–D141）
  - `docs/architecture/d01-conventions.md` v10（§4 省略语义、§5.10 Service；**§5.11 ServiceEndpoint 未新增，仍为 v10**）
  - `docs/features/F010/test-report.md`、`docs/features/F011/test-report.md`（TD/TE 模板、夹具/环境、`committed_engine` 真提交口径、桩证据边界声明）
  - `backend/tests/conftest.py`（`test_database_url`/`pg_engine`/`db_session`/`committed_engine`/`alembic_runner`/`auth_app`/`api_client`/`bootstrap_admin`/`make_user`/`role_client_factory`）；`backend/app/services/ip_address_reference.py`、`backend/app/services/service_reference.py`（两个注册函数与默认空集）
  - `docs/project/handoff.md`、`docs/project/implementation-rules.md`、`.pi/skills/data-integrity/SKILL.md`、`AGENTS.md`
  - `docs/project/project-plan.yaml` plan_revision 4 F012 条目（`current_stage: DATABASE`，`next_action: DATABASE 与 TEST_DESIGN Gate（可并行）`，layers=database/backend/frontend，api_required=true）
- **状态属性**：TD-1 `READY` 仅表示 A1–A21 已映射到可观察判据、边界/并发场景可执行、夹具与可验证性检查已建立；**不代表测试已运行、不填充执行 PASS、不批准实现或合并**。DATABASE（`docs/database/f012-service-endpoint.md`，未产出）、D01 v11 §5.11（未签核）、F010 errata-03（未落地）尚未定稿；§8 列 OPEN 待定稿后由 TD-2 逐项关闭。**不因 DATABASE 未定稿而直接 BLOCKED**（architecture §1/§5/§6/§7/§9 已给出可执行的实体、约束、引用检查与并发方案）。跨功能完整 §31 回归与 §32 上线验收不在本 Feature（见 §5）。
- **一致性观察（NOTE）**：`docs/api/F012.md` 文件头标 READY v1 并引用 `docs/database/f012-service-endpoint.md v1` 与 `d01-conventions.md v11（§5.11）`，但当前工作区上述两份上游均不存在（数据库目录无 f012 文档、D01 为 v10、无 0012 迁移、无 service_endpoint 后端代码），F010 errata-03 亦未落地。TD-1 因此按「Contract 内容可读、其上游依赖未定稿」处理，§8 OPEN 逐项待 TD-2 核对；这不改变 TD-1 的可验证性结论，但协调器应在推进 Gate 前修正 Contract 状态与其真实上游的一致性。

### 版本记录

| 版本 | 日期 | 变更 |
| --- | --- | --- |
| TD-1 | 2026-10-11 | 初版：A1–A21 映射 V1–V21（补充 V22–V28）、V-DB-1…V-DB-9；边界/并发 B1–B45；夹具/环境设计；F012 独立 / 留待 F013（展示聚合）三类分界；§8 OPEN 复核项（待 DATABASE/CONTRACT/D01 v11/F010 errata 后由 TD-2 关闭）。 |

> **复核基线（待 TD-2）**：`docs/database/f012-service-endpoint.md`（DATABASE Gate，未产出）、`d01-conventions.md` v11 §5.11（未签核）、`docs/api/F010.md` errata-03（未落地）。TD-1 的表名/列名/约束名/FK/触发 backstop/索引/迁移 0012 编号/错误路径/`reference_exists` details 形状/校验顺序均按 architecture §1/§4/§5/§6/§7 与 Contract v1 草案假设，TD-2 逐项核对后方可作为执行依据。

---

### 0. 数据完整性对应表（F012 范围）

方法依据 `.pi/skills/data-integrity/SKILL.md`；DB 列/约束以 DATABASE Gate 定稿为准（TD-1 为草案，行内标注「架构草案/待签核」）。

| 规则依据及版本 | 作用域/写入入口 | 数据库保证（架构草案，待签核） | 业务层保证 | 并发/生命周期边界 | 验证与证据 |
| --- | --- | --- | --- | --- | --- |
| §16/§27/DR-159 同 IP 未删 (protocol,port) 唯一 | POST / PATCH(protocol·port) / RESTORE `/api/v1/service-endpoints` | 部分唯一 `uq_service_endpoints_ip_protocol_port UNIQUE(ip_address_id,protocol,port) WHERE deleted_at IS NULL` | 409 `unique_conflict{field:"port",ip_address_id,protocol,port}` | 索引仲裁；软删释放；恢复重检；不同 IP 对象各自独立 | V8/V9/V20、V-DB-1/V-DB-7、B8/B9/B20/B21/B28；真实 PG |
| §16/§14/DR-158 ip_address 须已绑定且属 Service.Resource | POST / RESTORE | 跨表（service/ip_address/interface/resource）**应用主校验**；是否加 DB BEFORE 触发 backstop 由 Database 裁定 | 422 field="ip_address" | 绑定/转移在 IP 事务内校验；链路列不可变 | V4/V5/V14、V-DB-5、B4/B5/B6/B22/B23；真实 PG |
| §16/DR-160 protocol/port 取值域 | POST / PATCH | `ck_service_endpoints_protocol` ∈{TCP,UDP}；`ck_service_endpoints_port` 1–65535 | 422 field="protocol"/"port" | — | V6/V7、V-DB-2、B6/B7；真实 PG |
| §13.3/§16/§21/DR-161 Endpoint 引用 IP（解绑/转移/释放） | F010 PATCH 解绑/转移、DELETE 释放 | —（引用检查在应用） | F010 `check_ip_address_references` → F012 注册真实 provider → 409 `reference_exists{references:[{object_type:"service_endpoint",...}]}`；不级联 | IP 事务内检查；软删 Endpoint 不阻塞 | V12、B11/B12/B13/B14/B38；端到端 T22 |
| §16/§21/DR-161 Endpoint 引用 Service（删除） | F011 DELETE Service | — | F011 `check_service_references` → F012 注册真实 provider → 409 `reference_exists`；不级联 | 软删 Endpoint 不阻塞 | V13、B15/B16/B17；端到端 T23 |
| §21/§27/DR-166 软删/恢复 | DELETE / restore | deleted_at + 部分唯一 | 恢复重检 service/IP 存活、归属、监听唯一；失败不覆盖；不级联 | 索引仲裁；恢复 vs 并发重建 | V14/V27、V-DB-7、B22/B23/B24/B25/B26/B41 |
| §23/DR-? 乐观锁 | PATCH / DELETE / restore | `version` + 条件 UPDATE | rowcount=0 → 409 `VERSION_CONFLICT{current_version}` | 真并发双会话仅一成功 | V17、V-DB-4、B31/B32；真提交 |
| §22/DR-164 四 action Audit 同事务 | Endpoint 业务服务 | 复用 `audit_logs`（append-only） | `object_type="service_endpoint"`；白名单 `{service_id,ip_address_id,protocol,port,description}`；异常同回滚 | 无静默重试 | V16、B33/B34；真提交 |
| §26/§27/DR-165 迁移 0012 | Alembic `0012_service_endpoints` | `down_revision=0011_services`；全表新建无回填；单一 head；对称可逆；不重复启用扩展 | — | 真库 up/down/up | V28、V-DB-8；真实 PG |

---

## 1. 验收映射（product.md A1–A21 → 验证项）

执行环境：`真实 PG` = 独立测试库（库名含 `test`）；`后端集成` = ASGI 应用 + 真实 PG（非 SQLite）；`真提交` = `committed_engine`（真实连接 + 真实提交 + TRUNCATE teardown）；`机制级` = 真实 PG raw SQL 直接验证；`静态` = 路由清单/源码检查；`前端` = 构建 + client 机制级（真实 API 集成以入口 Nginx 为准）。

> **分界声明（关键）**：
> - **F012 独立可验证（不依赖 F013 数据）**：A1–A21（除 A12/A13 的展示部分与「数据供 F013 消费」的页面行为），即 A1–A11、A14–A21 全部与 A12/A13 的引用拦截语义；对应 §31 **T22/T23 的完整端到端**（F012 注册两个真实 provider 后，含真实 Endpoint 的引用保护在 F012 闭合）、T24/T25/T26/T37/T40/T41 的 Endpoint 子集。
> - **必须留待 F013（F012 局部 PASS 无法覆盖）**：§18 Resource Detail Services 区域、§19 Cluster Detail、§17 全局搜索、§20 Dashboard 的**页面/聚合展示**；F012 仅提供 Endpoint 数据与 `/api/v1/service-endpoints` 列表/详情。
> - **完整跨功能回归与 §32 上线验收（F016）**：F012 只承载 Endpoint 子集，**不得以 F012 局部 PASS 拼接整条 T22–T26/§32 通过**；T22/T23 的 Endpoint 端到端可在 F012 给出，但跨对象整体结论仍由 F016 的 Compose 集成给出。

| 验收（product.md） | 验证项 | 执行环境 | 可观察判据（PASS / FAIL） |
| --- | --- | --- | --- |
| A1 创建缺失 service/ip_address/protocol/port 任一必填→422；未知/只读字段→422 | **V1**；**V-DB-3** | 后端集成 + 真实 PG | PASS：逐一省略必填→422 `field` 为对应点路径；`service`/`ip_address`/`protocol`/`port` 显式 null→422；请求体含 `id`/`service_id`/`ip_address_id`/`metadata`/未知字段→422；无 Endpoint 行。FAIL：必填缺失被接受、未知字段被忽略 |
| A2 service 不存在/已软删→422 field="service" | **V2** | 后端集成 + 真实 PG | PASS：随机 UUID、指向已软删 Service→422 field="service"；无 Endpoint 行。FAIL：引用失效被接受 |
| A3 ip_address 不存在/已软删→422 field="ip_address" | **V3** | 后端集成 + 真实 PG | PASS：随机 UUID、指向已软删 IPAddress→422 field="ip_address"；无 Endpoint 行。FAIL：引用失效被接受 |
| A4 ip_address 未绑定 Interface（interface 为空）→422 field="ip_address"；未绑定 IP 不能登记 Endpoint | **V4** | 后端集成 + 真实 PG | PASS：引用 `interface_id IS NULL` 的未删 IP→422 field="ip_address"；无 Endpoint 行。FAIL：未绑定 IP 被接受 |
| A5 ip_address 绑定的 Interface 不属 Service 所属 Resource（跨 Resource/跨 Cluster VIP）→422 field="ip_address" | **V5** | 后端集成 + 真实 PG | PASS：同 Cluster 不同 Resource 的 Interface、不同 Cluster 的 Interface→均 422 field="ip_address"；无 Endpoint 行。FAIL：跨 Resource/Cluster 被接受 |
| A6 protocol 非 TCP/UDP（含显式 null）→422；TCP、UDP 正常登记 | **V6**；**V-DB-2** | 后端集成 + 真实 PG | PASS：`TCP`/`UDP`→201；`"tcp"`/`"udp"`/`"SCTP"`/`""`/显式 null→422 field="protocol"；raw 直插非枚举被 CHECK 拒。FAIL：小写被接受、非法落库 |
| A7 port 为 0、65536、负数、非整数或显式 null→422；1 与 65535 边界接受 | **V7**；**V-DB-2** | 后端集成 + 真实 PG | PASS：`1`/`65535`→201；`0`/`65536`/`-1`/`1.5`/`"80"`/显式 null→422 field="port"；raw CHECK 拒越界。FAIL：边界被拒、越界落库 |
| A8 同一未删除 IP 上重复 (protocol,port) →409 CONFLICT{unique_conflict}；含同一 Service 的重复 Endpoint | **V8**；**V-DB-1** | 后端集成 + 真实 PG | PASS：同 IP 第二次同 `(protocol,port)`（同一 Service 或不同 Service）→409 `CONFLICT{reason:"unique_conflict",field:"port",ip_address_id,protocol,port}`；无第二行。FAIL：重复成功、details 形状错 |
| A9 不同 IP 对象可有相同 (protocol,port)，含不同 Cluster 的同值地址；不同 IP 的监听互不冲突 | **V9**；**V-DB-1** | 后端集成 + 真实 PG | PASS：两个不同 IP（同 Cluster 不同地址、不同 Cluster 同值地址）同 `(protocol,port)`→均 201；raw 直插不同 `ip_address_id` 允许。FAIL：跨 IP 被误拦 |
| A10 一个 Service 可有多个 Endpoint（同 IP 不同端口，或不同 IP 不同端口） | **V10** | 后端集成 + 真实 PG | PASS：同 Service 同 IP 不同 port、同 Service 不同 IP 不同 port→均 201；列表按 `service_id` 取回全部。FAIL：被唯一性误拦 |
| A11 description 可空、PATCH 显式 null 清空、PATCH 省略保持 | **V11** | 后端集成 + 真实 PG | PASS：创建省略/显式 null→响应 `null`；给值保存；PATCH 省略→保持；PATCH 显式 null→清空；被拒请求不改库值。FAIL：null 未清空、省略被重置 |
| A12 有未删除 Endpoint 引用时，IP 解绑/转移/释放被拒并返回 references（F010 检查器 + F012 注册的 Endpoint provider）；不隐式级联、不自动删除 Endpoint | **V12**；**T22 端到端** | 后端集成 + 真实 PG（真提交） | PASS：用真实创建且未删的 Endpoint 引用某绑定 IP 后，ADMIN PATCH 解绑/转移、DELETE 释放→均 409 `CONFLICT{reason:"reference_exists",references:[{object_type:"service_endpoint",object_id,label}]}`；IP 的 `interface_id`/`deleted_at`/version 不变；Endpoint 行未被删除或修改。FAIL：拦截失效、object_type 非 `service_endpoint`、级联 |
| A13 有未删除 Endpoint 引用时 Service 删除被拒并返回 references（F011 检查器 + F012 注册的 provider）；不隐式级联 | **V13**；**T23 端到端** | 后端集成 + 真实 PG（真提交） | PASS：有未删 Endpoint 的 Service `DELETE /api/v1/services/{id}`→409 `reference_exists`+`references:[{object_type:"service_endpoint",...}]`；Service `deleted_at` 仍 null、version 不变；Endpoint 未被级联删除。FAIL：拦截失效、无 references、级联 |
| A14 Endpoint 软删；默认列表/详情隐藏已删；ADMIN 可查看已删与恢复；恢复重检 service 及 ip_address 未软删、IP 仍绑定且属 Service 所属 Resource、监听唯一，失败不覆盖新对象，不级联恢复 | **V14**；**V-DB-7** | 后端集成 + 真实 PG（真提交） | PASS：软删后默认列表/详情 404/不在列表；`deleted=only`（ADMIN）可见；restore 分别覆盖：service 软删→409 `dependency_deleted{conflicts:[{object_type:"service"}]}`、ip 软删→`ip_address`、IP 已解绑或归属失效→422 field="ip_address"、(protocol,port) 被新对象占用→409 `unique_conflict`；失败保持软删且新对象不被覆盖；恢复只恢复自身、不恢复 Service/IP/Interface。FAIL：覆盖、级联、错误码错 |
| A15 权限：VIEWER 只读；EDITOR 新增/修改 Endpoint；删除/查看已删/恢复 ADMIN；服务端执行 | **V15** | 后端集成 + 前端 + Compose | PASS：VIEWER GET→200、POST/PATCH→403；EDITOR POST/PATCH 201/200、DELETE/restore→403；ADMIN 成功；未认证 401；`deleted=include|only`、`?deleted=true` 非 VIEW_DELETED→403；`require_permission` 服务端强制（静态核对）。FAIL：越权成功、仅前端隐藏 |
| A16 CREATE/UPDATE/DELETE/RESTORE 写 Audit 且同事务，object_type="service_endpoint"；Activity 全角色可见；不记敏感内容 | **V16** | 后端集成 + 真实 PG（真提交） | PASS：四 action 各一条 `audit_logs`（`object_type="service_endpoint"`、`object_id`=Endpoint UUID、UPDATE 含 before/after、白名单 `{service_id,ip_address_id,protocol,port,description}`）；`GET /activity` 对三角色 200；注入 audit 失败时业务与 audit 同回滚、无残留行；快照不含敏感内容。FAIL：缺 action、不同事务、Activity 限权 |
| A17 乐观锁：过期版本编辑被拒（409 VERSION_CONFLICT），无静默覆盖 | **V17**；**V-DB-4** | 后端集成 + 真实 PG（真提交） | PASS：两独立连接同 version PATCH，一方 200 且 `version+1`，另一方 409 `VERSION_CONFLICT{current_version}`；最终库值来自成功方；DELETE/restore 同样拒绝过期版本。FAIL：双成功、无 409 |
| A18 默认列表隐藏软删；按 service、ip_address、protocol 过滤，分页/排序符合列表基线 | **V18** | 后端集成 + 真实 PG | PASS：默认无软删；`service_id`/`ip_address_id`/`protocol`/`deleted` 过滤正确；分页 `total/page/page_size` 边界正确；`sort∈{protocol,port,created_at,updated_at}`+`order` 生效、附 `id` 稳定；`sort=port` 按数值；非法参数→422。FAIL：软删泄漏、过滤/分页/排序错 |
| A19 输入 0.0.0.0、空监听地址、Unix Socket、端口范围/列表、空 host 等非法监听形式被拒（不支持通配/Unix Socket/共享 VIP） | **V19** | 后端集成 + 真实 PG | PASS：请求体含 `listen_address`/`host`/`socket`/`port_range`/`port` 数组等未知字段→422；无「通配/VIP/Unix Socket/范围」字段落库（静态核对响应与 ORM 无此类列）；§16 排除项未以任何可写路径进入。FAIL：存在通配/范围入参或字段 |
| A20 同 IP 未删 (protocol,port) 唯一由 PostgreSQL 部分唯一兜底，真实 PG 验证；并发创建仅一成功 | **V20**；**V-DB-1** | 真实 PG + 真提交 | PASS：`pg_indexes` 含部分唯一 `(ip_address_id,protocol,port) WHERE deleted_at IS NULL`；raw 直插存活重复被拒、软删后同名（同 protocol/port）成功；`committed_engine` 两独立连接并发 POST 同 `(ip_address_id,protocol,port)`→至多一方 201、另一方 409 `unique_conflict`；最终库中同 IP 该 (protocol,port) 仅一未删行。FAIL：缺约束、双成功 |
| A21 字段省略语义按 D01 §4：创建省略非必填→默认/null；PATCH 省略=保持；显式 null 仅清空 description；不可变/只读/未知字段→422 | **V21** | 后端集成 + 真实 PG | PASS：逐项符合 D01 §4 与 Contract §2.5；PATCH 出现 `service`/`service_id`/`ip_address`/`ip_address_id`/`id`（含同值）→422；`metadata`→422；被拒请求不改库值与 version。FAIL：不可变字段被改写、省略被重置 |

补充验证项（非直接 A 映射）：

| 验证项 | 内容 | 环境 | 判据 |
| --- | --- | --- | --- |
| **V22** 响应契约 | Endpoint 响应字段/嵌套 | 后端集成 | PASS：含 `id、service{id,name,resource{id,hostname}}、ip_address{id,address,network{id,name},interface{id,name}}、protocol、port、description|null、version、created_at/updated_at、deleted_at`；列表 `{items,page,page_size,total}`；不含 `metadata`/原始 `service_id`/`ip_address_id` |
| **V23** 校验顺序 | POST/PATCH/DELETE/restore 优先级 | 后端集成 | PASS：POST 401→403→body(422)→service(422)→ip_address 存在/未删(422)→归属(422)→protocol(422)→port(422)→唯一(409)→写+Audit→201；PATCH 401→403→body→可见性(404)→version(409)→取值(422)→唯一重检(409)→写→200；DELETE 401→403→404→version 校验(422)→版本(409)→软删；restore 按 Contract §6.6 确定性优先级 |
| **V24** 只读无副作用 | GET 列表/详情/activity | 后端集成 | PASS：纯 SELECT，无业务写、无 audit 行、version 不变 |
| **V25** PATCH exclude_unset / 只读 / 未知 | 省略保持；显式 null 仅清 description；`service`/`ip_address`/`metadata` 等→422 | 后端集成 | PASS：逐项符合 D01 §4；被拒请求不改库值与 version |
| **V26** FK 物理语义（机制级） | raw 物理删除被 Endpoint 引用的 Service/IPAddress | 真实 PG | PASS：被 FK RESTRICT 阻止（`confdeltype='r'`）；报告标注机制级（API 无物理删除路径） |
| **V27** 恢复 vs 并发重建竞争（真提交） | 软删后并发 restore 与新建同 `(ip_address_id,protocol,port)` | 真实 PG（真提交） | PASS：至多一方存活；部分唯一闭环；无两未删同键；失败方保持软删 |
| **V28** 迁移 0012 | Alembic up/down/up + 单一 head + 无回填 | 真实 PG | PASS：`alembic heads` 单一 `0012_service_endpoints`（`down_revision=0011_services`）；up 建表/约束/部分唯一/索引；down 逆序且 0011 对象保留；re-up 集合一致；无回填、不重复启用扩展 |

**数据库机制级验证项（V-DB，真实 PG raw SQL）**：

| 编号 | 内容 | 映射 |
| --- | --- | --- |
| **V-DB-1** | 部分唯一 `uq_service_endpoints_ip_protocol_port UNIQUE(ip_address_id,protocol,port) WHERE deleted_at IS NULL`：同 IP 重复拒、不同 IP 允许、软删释放、恢复冲突 | A8/A9/A14/A20/V8/V9/V14/V20/B8/B9/B20/B21/B28/B41 |
| **V-DB-2** | `ck_service_endpoints_protocol` ∈{TCP,UDP}；`ck_service_endpoints_port` 1–65535；raw 非法拒 | A6/A7/V6/V7/B6/B7 |
| **V-DB-3** | `service_id`/`ip_address_id`/`protocol`/`port` NOT NULL；两个 FK RESTRICT；`ix_service_endpoints_{service_id,ip_address_id,deleted_at}` | A1/A2/A3/V1/V2/V3/V26 |
| **V-DB-4** | `version` DEFAULT 1、CHECK ≥1；时间戳列；`deleted_at` 可空；条件 UPDATE 语义 | A17/V17/B31/B32 |
| **V-DB-5** | 归属 backstop（若 Database 裁定加 BEFORE INSERT/UPDATE 触发）：`interface_id` 非空且 `interfaces.resource_id == services.resource_id`；对任意 UPDATE 生效、不检查软删 | A4/A5/V4/V5/B4/B5 |
| **V-DB-6** | 表/约束/索引目录断言：`pg_constraint`/`pg_indexes`/`pg_attribute` 与设计逐项一致；无 pg_trgm/GIN；不新增扩展 | V22/V-DB-1…5 |
| **V-DB-7** | 软删/恢复与部分唯一交互（恢复置 `deleted_at=null` 重新受约束） | A14/A20/V14/V20/B20/B21/B41 |
| **V-DB-8** | 迁移 0012 up/down/up、单 head、无回填、扩展未重复启用 | V28/B44 |
| **V-DB-9** | FK RESTRICT 机制级（物理删被 Endpoint 引用的 Service/IPAddress） | V26/B42 |

---

## 2. 边界与并发场景（B 编号，TEST 阶段执行）

| 编号 | 场景 | 步骤 | 判据 |
| --- | --- | --- | --- |
| B1 | 必填缺失 | 逐一省略 `service`/`ip_address`/`protocol`/`port` | 均 422，`fields[].field` 为对应点路径；无 Endpoint 行 |
| B2 | 必填显式 null | 每个非 nullable 字段显式 `null` | 均 422；无 Endpoint 行 |
| B3 | 只读/未知字段 | 请求含 `id`/`service_id`/`ip_address_id`/`metadata`/`foo` | 均 422；无 Endpoint 行 |
| B4 | service 引用边界 | 随机 UUID / 软删 Service | 均 422 field="service"；无 Endpoint 行 |
| B5 | ip_address 引用边界 | 随机 UUID / 软删 IP / 未绑定 IP | 均 422 field="ip_address"；无 Endpoint 行 |
| B6 | 归属跨 Resource/Cluster | Service.Resource=A；IP 绑定在 Resource B 的 Interface（同 Cluster）；再试不同 Cluster Interface | 均 422 field="ip_address"；无 Endpoint 行 |
| B7 | protocol 取值 | `TCP`/`UDP`/`tcp`/`udp`/`Sctp`/`""`/`null` | 仅 `TCP`/`UDP`→201；其余 422；raw CHECK 拒 |
| B8 | port 边界 | `1`/`65535`/`0`/`65536`/`-1`/`1.5`/`"80"`/`null` | 1 与 65535→201；其余 422；raw CHECK 拒 |
| B9 | 同 IP 重复监听 | 同 IP 同 Service 同 `(protocol,port)`；同 IP 不同 Service 同 `(protocol,port)` | 均 409 `unique_conflict`；details 含 `field:"port"`、`ip_address_id`、`protocol`、`port` |
| B10 | 跨 IP 同名监听 | 同 Cluster 两 IP、不同 Cluster 同值地址两 IP，各建同 `(protocol,port)` | 均 201；互不冲突 |
| B11 | 一 Service 多 Endpoint | 同 Service 同 IP 不同 port；同 Service 不同 IP 不同 port | 均 201；列表取回全部 |
| B12 | **IP 引用保护端到端（真实 Endpoint）** | 建未删 Endpoint 引用绑定 IP；ADMIN PATCH 解绑、PATCH 转移、DELETE 释放 | 均 409 `reference_exists`+`references:[{object_type:"service_endpoint",object_id,label}]`；IP 绑定/deleted_at/version 不变；Endpoint 未变 |
| B13 | 软删 Endpoint 不阻塞 IP 操作 | 软删引用 IP 的 Endpoint 后解绑/转移/释放该 IP | 成功；证明 provider 仅返回未删 Endpoint |
| B14 | IP 引用列表形状 | 多个未删 Endpoint 引用同一 IP | `references` 含全部、`label`=`"<protocol>/<port>"`、`object_type` 恒 `"service_endpoint"`（**F010 errata 后断言**） |
| B15 | **Service 引用保护端到端（真实 Endpoint）** | 有未删 Endpoint 的 Service `DELETE /api/v1/services/{id}` | 409 `reference_exists`+`references:[{object_type:"service_endpoint",...}]`；Service 未软删、version 不变 |
| B16 | 软删 Endpoint 后可删 Service | 软删全部引用 Endpoint 后删 Service | 204 软删；无级联 |
| B17 | 删除不级联（结构层） | DELETE Endpoint（无子引用） | 204；仅 `deleted_at`/version/updated_at 变更；静态 + 断言 F012 不触碰 Service/IP/Interface |
| B18 | 软删默认隐藏 | 软删后 GET 详情/列表（默认） | 404/不在列表；`deleted=only`（ADMIN）可见 |
| B19 | 恢复成功 | 软删→restore（service/IP/归属/唯一均有效） | 200；`deleted_at=null`；不级联恢复 Service/IP/Interface |
| B20 | 恢复唯一冲突 | 软删 A 后建同 `(ip_address_id,protocol,port)` B；restore A | 409 `unique_conflict`；A 保持软删、B 不变、不被覆盖 |
| B21 | 恢复依赖失效 | service 软删 / ip 软删 / IP 已解绑 / 归属不再成立 | 分别 409 `dependency_deleted{conflicts:[{object_type:"service"/"ip_address"/"interface"}]}` 或 422 field="ip_address"；保持软删 |
| B22 | 恢复顺序确定性 | 同时存在唯一冲突与依赖失效 | 按 Contract §6.6：监听唯一(409) 优先于依赖(409) 优先于归属(422) |
| B23 | 恢复不级联 | restore 软删 Endpoint | 200；不自动恢复 Service/IP/Interface；仅自身 |
| B24 | restore 未软删对象 | 对未软删 Endpoint restore | 409 `not_deleted` |
| B25 | 权限矩阵 | 逐端点 VIEWER/EDITOR/ADMIN/未认证 | 符合 §23；服务端强制；未认证 401 先于 403 |
| B26 | 查看已删权限 | VIEWER/EDITOR `deleted=include|only`、`?deleted=true` | 403 `FORBIDDEN{reason:"permission"}`；ADMIN 200 |
| B27 | 四 action Audit | CREATE/UPDATE/DELETE/RESTORE | 各一条 `object_type="service_endpoint"`；UPDATE 含 before/after；白名单；`activity` 全角色 200；无敏感内容 |
| B28 | 审计同事务回滚 | 注入 audit 失败（创建/更新/删除/恢复） | 业务与 audit 同回滚；最终持久化为旧值/无新行 |
| B29 | 列表过滤/分页/排序 | `service_id`/`ip_address_id`/`protocol`/`deleted` 组合；分页边界；`sort`+`order` | 过滤正确；分页 `total/page/page_size` 正确；排序附 `id` 稳定；`sort=port` 数值；非法参数→422 |
| B30 | 列表软删泄漏 | 软删后默认列表 | 不含软删；`deleted=include` 可见 |
| B31 | **乐观锁并发（真提交）** | `committed_engine` 两连接同 version PATCH（及 DELETE/restore） | 一方 200 且 version+1；另一方 409 `VERSION_CONFLICT{current_version}`；最终值来自成功方；无静默重试 |
| B32 | 乐观锁不可见语义 | 过期 version 且对象不可见/不存在 | 404（不可见/不存在）；可见过期→409 |
| B33 | PATCH 可变字段 | 改 `protocol`/`port`/`description`；PATCH 省略保持；显式 null 清 description | 符合 Contract §2/§6.4；version+1 |
| B34 | PATCH 重检唯一 | 改 protocol/port 撞同 IP 既有未删 `(protocol,port)` | 409 `unique_conflict`；库值不变、version 不变 |
| B35 | PATCH 不可变字段 | PATCH 含 `service`/`service_id`/`ip_address`/`ip_address_id`/`id`（含同值） | 均 422；库值与 version 不变 |
| B36 | 非法监听形式 | 请求含 `listen_address`/`host`/`socket`/`port_range`/`ports` 数组 | 均 422（未知字段）；响应/ORM 无此类列（静态） |
| B37 | **部分唯一 raw 兜底** | raw 直插同 `(ip_address_id,protocol,port)` 未删；软删后同键 | 存活重复被 `uq_service_endpoints_ip_protocol_port` 拒；软删后成功 |
| B38 | **部分唯一并发双会话（真提交）** | `committed_engine` 两独立连接对同 IP 并发 POST 同 `(ip_address_id,protocol,port)` | 至多一方 201、另一方 409 `unique_conflict`；最终库中同键仅一未删行；断言最终持久化（非仅未抛异常） |
| B39 | 归属校验恒成立（并发/窗口） | IP 绑定/解绑与 Endpoint 创建交叉；归属经同一 IP 事务校验 | 归属在创建/恢复时点成立；跨 Resource 被拒；无幽灵绑定 Endpoint |
| B40 | 解绑/转移在 Endpoint 事务窗口 | F010 绑定关系可 PATCH；Endpoint 创建时校验时点归属 | 符合 §14/§16；若归属在创建后被解绑，Endpoint 不被自动删除（后续 IP 解绑被引用保护拦截） |
| B41 | **恢复 vs 并发重建竞争（真提交）** | 软删 A 后并发：会话 1 restore A、会话 2 建同 `(ip_address_id,protocol,port)` B | 至多一方存活；部分唯一闭环；无两未删同键；失败保持软删 |
| B42 | FK RESTRICT 机制级 | raw 物理删除被未删 Endpoint 引用的 Service/IPAddress | 被 FK RESTRICT 拒（`confdeltype='r'`）；报告标注机制级 |
| B43 | 校验顺序 | V23 各端点优先级 | 符合 Contract §6 |
| B44 | 迁移 0012 up/down/up | `upgrade head`→`downgrade 0011`→`upgrade head`；`alembic heads` | 各步 0；单一 head `0012_service_endpoints`；down 后表/约束/索引消失、0011 对象保留；re-up 一致 |
| B45 | 只读无副作用 | GET 列表/详情/activity | 无业务写、无 audit 行、version 不变 |

并发说明：B12/B15/B27/B28/B31/B38/B41 及任何「失败不留痕/并发」用例必须使用 `committed_engine`（真实连接、真实提交）或显式事务控制，断言**最终持久化状态 + 关系图**，不仅「未抛异常」。涉及部分唯一、CHECK、FK、迁移的断言必须在真实 PostgreSQL 执行（SQLite / Mock 不作约束/并发证据）。**双 provider 端到端（B12/B14/B15）必须在 F012 完成真实注册后以真实 Endpoint 数据断言，`object_type` 恒为 `"service_endpoint"`（F010 errata-03 落地后 F010 侧文档/桩同步）。**

---

## 3. 夹具 / 环境设计

**复用 F001–F011 `backend/tests/conftest.py`（不改其护栏语义）**：
- `test_database_url`：独立测试库 + 安全护栏（库名含 `test`、`TEST_DATABASE_URL != DATABASE_URL`）；未设置则 skip 并告警，不静默改 SQLite。
- `pg_engine`：会话级 `DROP SCHEMA public CASCADE` + `CREATE SCHEMA public` + `alembic upgrade head`（含 0012），会话结束清理。
- `db_session`：函数级外层事务 + savepoint，回滚不跨用例污染（单事务用例）。
- `committed_engine`：真实提交用例（B12/B15/B27/B28/B31/B38/B41/B42 及持久断言），teardown `TRUNCATE`（排除 `alembic_version`；确认 `service_endpoints` 在动态清理清单内），新开连接断言最终持久化。
- `alembic_runner`：迁移 up/down/up 用例（V28/B44）。
- 认证/权限 fixture（`auth_session_factory`/`auth_app`/`api_client`/`bootstrap_admin`/`make_user`/`role_client_factory`）：权限/审计证据使用**真实业务端点** `/api/v1/service-endpoints*` 与 `/api/v1/services/{id}`、`/api/v1/ip-addresses/{id}`。
- F003/F004/F008/F009/F010/F011 helper：`_create_cluster`/`_network`/`_pool`/`_resource`/`_interface`/`_ip`/`_allocate`、`_create_service`/`_service`、raw `insert_*`、软删/恢复、乐观锁 `two-session`、raw SQL 约束断言模式、引用检查器桩模式直接复用。

**F012 新增测试侧夹具/断言（由 Tester 落地于测试侧，实现阶段由 Backend 提供接口）**：
- `service_endpoint_factory`：创建 Endpoint（`service_id`/`ip_address_id`/`protocol`/`port`/`description`），返回对象与 `version`；供 A1–A21、B1–B45 复用；失败路径覆盖只读字段被拒。
- `endpoint_scenario_factory`（IP/Service/Interface 组合）：在同一 Cluster 建 Resource A（Service 所属）与 Resource B，各建 Interface；为 A 的 Interface 分配/绑定 IP（bound）、另建未绑定 IP；返回 `{service_a, interface_a, ip_bound_a, ip_unbound, interface_b, ip_bound_b}` 组合，一次覆盖 A2–A5/B4–B6 归属边界。
- `SERVICE_ENDPOINT_PROTOCOL_CASES`：`TCP`/`UDP`/`tcp`/`udp`/非法/空/null（V6、B7）。
- `SERVICE_ENDPOINT_PORT_CASES`：1/65535/0/-1/65536/非整数/null（V7、B8）。
- `assert_service_endpoint_row(engine, id, expected)`：raw SQL 断言 `service_endpoints` 各列值/`IS NULL`（含 `service_id`/`ip_address_id`/`protocol`/`port`/`description`/version/`deleted_at`）。
- `assert_partial_unique_service_endpoint(engine, ip_id, protocol, port, deleted)`：raw 直插断言部分唯一仅在 `deleted_at IS NULL` 生效（A8/A9/A20/V8/V9/V20/B9/B10/B37/B38）。
- `assert_endpoint_provider_object_type(...)`：断言 `register_ip_address_reference_checker`/`register_service_reference_checker` 注册的真实 provider 返回 `references[].object_type == "service_endpoint"` 且 `label == "<protocol>/<port>"`（A12/A13/V12/V13、B12/B14/B15；**F010 errata 后**）。
- `assert_endpoint_reference_protection(...)`：真实 Endpoint 端到端断言 IP 解绑/转移/释放与 Service 删除的 409 `reference_exists`+references（V12/V13、B12/B15）。
- `assert_restore_recheck_service_endpoint(...)`：恢复重检 service/IP 存活、归属、唯一；失败不覆盖、不级联（A14/V14/B19–B24/B41）。
- `assert_audit_same_txn(...)`：注入 audit 失败断言双回滚（V16/B28）。
- 真提交并发夹具（复用 F010/F011 `committed_engine` 模式）：`two_session_partial_unique_service_endpoint_create`、`two_session_restore_vs_recreate_endpoint`、`two_session_version_conflict_endpoint`，供 B31/B38/B41。
- **F012 前端夹具**：复用 F005–F011 `smoke:client` 机制，新增 Service Detail 内 Endpoints 管理区（列表/新增/编辑/删除/恢复/Activity）、创建/编辑表单（Service 选择器创建后不可改、IPAddress 选择器过滤为该 Service 同 Resource 且已绑定的未删 IP、protocol/port/description）、422 点路径映射、409 冲突呈现（`unique_conflict`/`reference_exists`/`dependency_deleted`/`not_deleted` 与未知 reason 通用呈现）、已删开关与 ADMIN 恢复入口，供 A15/A18 前端机制级用例。

**环境**：Docker / Compose 可用（F001–F011 TE 已证）；真实 PG 经 Compose `db`（`postgres:16`）。btree_gist 由 0008、pg_trgm 由 0001 已启用；0012 不重复启用扩展。

### 3.1 当前环境可执行性评估

| 验证项 | 环境要求 | 当前评估 | 降级/替代 |
| --- | --- | --- | --- |
| V1–V21、V22–V27、B1–B45（除迁移/机制级） | 真实 PG + 后端集成 | 经 Compose `db` 可满足（F001–F011 已证） | 无 PG 时 skip 并标 BLOCKED，**不得**用 SQLite 替代约束/并发证据 |
| V-DB-1…V-DB-9、V28/B44（迁移 0012） | Alembic + 真实 PG | 可执行；依赖 0012 定稿 | 迁移未定稿则相关断言 BLOCKED，不降验收 |
| A12/V12/B12/B14（IP 侧双 provider 端到端） | F012 provider 注册 + F010 errata | F010 挂钩已就绪（`register_ip_address_reference_checker`）；F012 实现注册后可用 | 接口未落地则 BLOCKED；**`object_type` 断言在 errata-03 落地前会与 F010 现存桩测试 `"endpoint"` 冲突**，需先订正 |
| A13/V13/B15/B16（Service 侧双 provider 端到端） | F012 provider 注册 | F011 挂钩已就绪（`register_service_reference_checker`，默认空集） | 未落地则 BLOCKED |
| B31/B38/B41 并发 | 真实并发提交 fixture | 可执行（复用 `committed_engine`） | 无 PG 时 BLOCKED；不得以顺序调用替代并发证据 |
| 前端机制级 / 真实 API 集成 | Node 22 + 构建；Compose 入口 | 可执行 | 真实浏览器 DOM 渲染非必要判据；镜像/端口问题记 BLOCKED |
| §18/§19/§17/§20 展示聚合 | F013 交付 | **不可执行** | 标 `NOT TESTED / 归 F013` |
| T22–T26 完整跨功能回归与 §32 上线验收 | F016 交付 | **不可执行** | F012 仅承载 Endpoint 子集；不声明整条通过 |

---

## 4. 可验证性检查

| 项 | 判定 | 说明 |
| --- | --- | --- |
| A1/A21 必填/省略/未知/只读 | **可验证（API + DB）** | V1/V21 + V-DB-3 + B1–B3/B35；422 点路径 + NOT NULL |
| A2/A3 service/ip 引用存活 | **可验证（API + DB）** | V2/V3 + V-DB-3 + B4/B5；应用 422 + FK |
| A4/A5 归属（未绑定/跨 Resource） | **可验证（API + DB）** | V4/V5 + V-DB-5 + B6；应用主校验（+ 可选 DB backstop） |
| A6/A7 protocol/port 边界 | **可验证（API + DB）** | V6/V7 + V-DB-2 + B7/B8；CHECK + 422 |
| A8/A9 监听唯一作用域 | **可验证（API + DB）** | V8/V9 + V-DB-1 + B9/B10/B37；部分唯一 + 应用 409 |
| A10 一 Service 多 Endpoint | **可验证（API）** | V10 + B11 |
| A11 description | **可验证（API）** | V11 + B33；D01 §4 省略语义 |
| A12/A13 引用保护端到端 | **可验证（端到端 + 真提交）** | V12/V13 + B12/B14/B15/B16/B17；F012 注册真实 provider 后闭合 T22/T23 的 Endpoint 部分 |
| A14 软删/恢复重检 | **可验证（端到端 + 真提交）** | V14 + V-DB-7 + B18–B24/B41；失败不覆盖 |
| A15 权限矩阵 | **可验证（端到端 + 静态）** | V15 + B25/B26；真实端点 + 服务端强制 |
| A16 审计 | **可验证（端到端 + 真提交）** | V16 + B27/B28；四 action + 同事务回滚 |
| A17 乐观锁 | **可验证（真提交）** | V17 + V-DB-4 + B31/B32；两连接同 version |
| A18 列表 | **可验证（端到端）** | V18 + B29/B30；软删/过滤/分页/排序 |
| A19 非法监听形式 | **可验证（API + 静态）** | V19 + B36；未知字段 422 + 无对应字段 |
| A20 DB 兜底 + 并发 | **可验证（DB 机制级 + 真提交）** | V20 + V-DB-1 + B37/B38；真实 PG raw + 双会话 |
| V28/V-DB-8 迁移/目录 | **可验证（DB）** | 真实 PG up/down/up + 单一 head + 目录断言 |
| V26/B42 FK 物理语义 | **机制级** | API 无物理删除路径；raw SQL 验证 `confdeltype`，报告须显式标注 |

口径明确记录：**A12/A13 的端到端在 F012 由真实 provider 闭合（T22/T23 的 Endpoint 部分）**，不得再以桩替代；**§18/§19/§17/§20 展示聚合明确归 F013**；**T22–T26 完整跨功能回归与 §32 上线验收归 F016**。

---

## 5. 范围与不适用项声明

- **Service 本体与 `/api/v1/services`（F011）**：F012 不实现；仅消费 Service 与 `register_service_reference_checker` 扩展点。
- **IPAddress 本体、分配/解绑/转移/释放与容量（F010）**：F012 不实现；仅注册 Endpoint 引用 provider，不改 F010 规则；F012 不验证 IP 唯一/CIDR/绑定本身（归 F010）。
- **§18 Resource Detail Services 区域、§19 Cluster Detail、§17 全局搜索、§20 Dashboard（F013）**：F012 仅承载 `/api/v1/service-endpoints` 列表/详情与 Endpoint 数据；页面与聚合展示归 F013，标 `NOT TESTED / 归 F013`。
- **CSV / Excel 导入（§24，F014）**：Endpoint 导入不在本 Feature。
- **完整 Audit 查询页（§22，F015/F016）**：F012 仅验证四 action 的资源级 Activity 快照。
- **不支持项**：通配地址 0.0.0.0 / 空监听地址、Unix Socket、跨资源共享 VIP、端口范围/列表、IPv6、URL/路径、TLS/证书、代理/转发、健康检查/存活探测、端口实开探测、自动发现监听；不落 metadata/name/status/listen_address/实时探测状态/部署或同步标记；登记 Endpoint 不触发部署、监控或状态同步。
- **T40/T41**：ServiceEndpoint 无 name 字段，§4.1 名称归一化表不适用；本 Feature 不重复名称规则。
- **完整 T22–T26 回归与 §32 上线验收**：F012 仅承载 Endpoint 子集；跨 Feature 完整回归归 F016。**不声明上述条款完整通过**。
- **真实浏览器 DOM 渲染**：非 F012 必要判据，前端以构建 + client 机制级为准。

---

## 6. 风险与待核对项总结

| 项 | 评估 | 处理 |
| --- | --- | --- |
| V1–V21、V22–V27、B1–B45（真实 PG + 后端集成） | Docker/Compose 可用（F001–F011 已证）；**可执行** | 无 PG 时相关项 BLOCKED，不降验收 |
| V-DB-1…V-DB-9、V28 迁移 0012 + 部分唯一/CHECK/FK | DATABASE Gate 未定稿（`f012-service-endpoint.md` 未产出） | 定稿后由 TD-2 核对；未定稿则相关断言 BLOCKED |
| A12/A13 双 provider 端到端 | F010/F011 挂钩已就绪；F012 实现注册后可达 | F012 验真实端到端；**F010 errata-03 未落地，`object_type` 现为 `"endpoint"` 与目标 `"service_endpoint"` 冲突**，须先订正 F010 文档/桩测试 |
| `unique_conflict` details 形状（field:"port" + 元组） | Contract v1 已固定，DB Gate 未核对 | TD-2 依 DATABASE 定稿核对 V8/B9/B34 |
| 归属是否加 DB backstop 触发 | architecture 交 Database 裁定 | TD-2 据 DATABASE 定稿固定 V-DB-5/B6/B39 |
| 列表参数集/校验顺序/审计白名单/响应契约 | Contract v1 已固定（READY），但 D01 v11/F010 errata 未落地 | TD-2 依定稿核对 V18/V22/V23/V25/B29/B35 |
| D01 v11 §5.11 未签核 | ServiceEndpoint 字段口径未进 D01 | TD-2 依 v11 核对 V1/V6/V7/V21 |
| Contract READY 标注引用缺失的上游 | 见 Test Design 一致性观察 | 协调器推进 Gate 前修正 Contract 状态；TD-2 以实际定稿为准 |
| A19 非法监听形式 | §16 排除项，无正式字段 | 以「未知字段 422 + 静态无对应列」判定；若 CONTRACT 澄清具体输入形态，回归 TD |

---

## 7. 独立性与执行口径（TEST 阶段适用）

- Backend pytest 由 Tester 独立重跑，不复用实现者数字。
- 迁移、部分唯一、CHECK、FK 约束由 Tester 在独立库（库名含 `test`）以 Alembic / raw SQL 直接执行；不连接生产或未知数据库。
- 接口验证响应内容、类型、业务边界、非法输入与错误语义；只读功能（GET 列表/详情/activity）确认无业务写副作用。
- 引用冲突：F012 为**真实 provider 端到端**（注册 `register_ip_address_reference_checker` 与 `register_service_reference_checker` 后，以真实 Endpoint 数据断言 409 `reference_exists` 且 `object_type="service_endpoint"`）；不再以桩替代。F010 errata-03 落地前，F010 侧现存桩测试的 `"endpoint"` 断言须同步订正，避免 T22/T23 口径分歧。
- 前端验证状态、交互、错误与未知值处理；已批准范围要求真实前后端集成时经入口 Nginx 验证真实 API，不以 Mock 代替。
- 修复后按影响重测；首次设计检查与最终验收分别记录版本和证据。

---

## 8. OPEN 复核项（TD-1 提出，待 DATABASE / CONTRACT / D01 v11 / F010 errata 定稿后由 TD-2 关闭）

> TD-1 `READY` 表示方案可验证，下列假设均未经逐项核对；**READY 不代表测试已执行、不批准实现或合并**。定稿后由 TD-2 关闭并固定执行判据。

### 8.1 待 DATABASE 定稿（`docs/database/f012-service-endpoint.md`，未产出）

| # | TD-1 待复核假设 | 影响验证项 | Owner |
| --- | --- | --- | --- |
| OPEN-1 | 表名 `service_endpoints`、列名/类型（`id uuid pk gen_random_uuid()`、`service_id uuid NOT NULL`、`ip_address_id uuid NOT NULL`、`protocol varchar(8) NOT NULL`、`port integer NOT NULL`、`description text NULL`、`version int NOT NULL DEFAULT 1`、`created_at/updated_at timestamptz NOT NULL now()`、`deleted_at timestamptz NULL`） | V1–V28、B1–B45 | Database |
| OPEN-2 | 约束/索引名：`pk_service_endpoints`、`fk_service_endpoints_service_id_services`、`fk_service_endpoints_ip_address_id_ip_addresses`、`uq_service_endpoints_ip_protocol_port`、`ck_service_endpoints_{protocol,port,version}`、`ix_service_endpoints_{service_id,ip_address_id,deleted_at}` | V6/V7/V20/V-DB-1…6、B7/B8/B37/B38 | Database |
| OPEN-3 | **部分唯一精确形态** `UNIQUE(ip_address_id,protocol,port) WHERE deleted_at IS NULL`；软删释放、恢复重检、不同 IP 允许 | A8/A9/A20/V8/V9/V20、V-DB-1/V-DB-7、B9/B10/B20/B37/B38/B41 | Database |
| OPEN-4 | `protocol` CHECK∈{TCP,UDP}；`port` CHECK 1–65535 | A6/A7/V6/V7、V-DB-2、B7/B8 | Database |
| OPEN-5 | **归属是否加 DB BEFORE INSERT/UPDATE backstop 触发**（模式同 F010 `trg_ip_addresses_interface_cluster`）：`interfaces.resource_id == services.resource_id`；对任意 UPDATE 生效、不检查软删；架构交 Database 裁定 | A4/A5/V4/V5、V-DB-5、B6/B39 | Database |
| OPEN-6 | `service_id`/`ip_address_id` FK `ON DELETE RESTRICT`；`service`/`ip_address` 不可变仅为应用 422（无不可变触发器）或等价机制 | A2/A3/A21/V2/V3/V21、V-DB-3、B35/B42 | Database |
| OPEN-7 | 索引集合（不建 pg_trgm/GIN、不重复启用扩展）；provider 查询（按 `ip_address_id`/`service_id` + `deleted_at IS NULL`）索引支撑 | V20、V-DB-6、B12/B15 | Database / Backend |
| OPEN-8 | `version` DEFAULT 1、CHECK ≥1；时间戳列；`deleted_at`；软删/恢复与部分唯一交互 | A17/V17、V-DB-4/V-DB-7、B31/B32 | Database |
| OPEN-9 | 迁移 `0012_service_endpoints`（`down_revision=0011_services`）单 head、全表新建无回填、对称可逆、不重复启用扩展 | V28、V-DB-8、B44 | Database |
| OPEN-10 | 恢复重检 DB 层（部分唯一重新入索引；归属触发重跑；越界/依赖交应用） | A14/V14、V-DB-7、B19–B24/B41 | Database / Backend |

### 8.2 待 CONTRACT / D01 v11 / F010 errata 定稿

| # | TD-1 待复核假设 | 影响验证项 | Owner |
| --- | --- | --- | --- |
| OPEN-11 | 错误码复用集：`unique_conflict{field:"port",ip_address_id,protocol,port}`、`not_deleted`、`dependency_deleted{conflicts:[{object_type:"service"|"ip_address"|"interface",object_id}]}`、`reference_exists{references:[{object_type:"service_endpoint",object_id,label}]}`；F012 **不新增** code/reason | A8/A12/A13/A14/V8/V12/V13/V14、B9/B12/B14/B15/B21/B24 | Contract |
| OPEN-12 | **`object_type` canonical=`"service_endpoint"` + F010 errata-03**（`docs/api/F010.md` §1.2 `"endpoint"`→`"service_endpoint"`，桩测试 `test_ip_addresses.py` 同步；不影响 F010 DONE 行为） | A12/V12/B12/B14 | Contract / F010 errata |
| OPEN-13 | 校验顺序与错误码层级（POST/PATCH/DELETE/restore；Contract §6.2/§6.4/§6.5/§6.6，尤其 restore 确定性优先级） | V23、B22/B43 | Contract |
| OPEN-14 | 列表 Query 参数集（`service_id/ip_address_id/protocol/deleted/page/page_size/sort/order`）、`deleted∈{exclude,include,only}`、`sort∈{protocol,port,created_at,updated_at}`、`sort=port` 按数值、不新增 cluster/resource 过滤 | A18/V18、B29/B30 | Contract |
| OPEN-15 | **D01 v11 §5.11 签核**：service/ip_address 创建必填、引用须存活、创建后不可改；ip_address 须已绑定且属 Service.Resource；protocol∈{TCP,UDP}（大写）；port 1–65535；description 可空无上限；不落 metadata/name/status；§5 名称表不适用；§8 记 v11 | A1–A7/A11/A21/V1–V7/V11/V21、B1–B8/B33/B35 | Contract / D01 v11 |
| OPEN-16 | 权限映射（增改=WRITE；删除=DELETE_OBJECT；查看已删=VIEW_DELETED；恢复=RESTORE；Activity=VIEW_ACTIVITY 全角色）与审计白名单 `{service_id,ip_address_id,protocol,port,description}`、`object_type="service_endpoint"` | A15/A16/V15/V16、B25–B28 | Contract |
| OPEN-17 | 响应契约：`service{id,name,resource{id,hostname}}`、`ip_address{id,address,network{id,name},interface{id,name}}` 嵌套；不含 `metadata`/原始 `service_id`/`ip_address_id`；列表 `{items,page,page_size,total}`；软删可见性语义 | A18/A21/V18/V22/V25、B18/B29/B30 | Contract |
| OPEN-18 | 双 provider 落点：F012 注册两个真实 provider（IP 侧 `register_ip_address_reference_checker`、Service 侧 `register_service_reference_checker`）；启动导入链保证生效；`label=protocol/port` | A12/A13/V12/V13、B12–B17/B38/B40 | Architect / Backend |
| OPEN-19 | I-2 字段可变性：CONTRACT 固定 `service`/`ip_address` 创建后不可改（PATCH 出现含同值→422）；`protocol`/`port` 可 PATCH 并重检唯一；`description` 可改；若改判须回归 TD | A21/V21/V25/B33/B35 | Product / Contract |
| OPEN-20 | Contract 状态一致性（NOTE）：`docs/api/F012.md` 标 READY v1 且引用不存在的 `database/f012-service-endpoint.md v1`、`d01-conventions.md v11`；F010 errata-03 未落地。TD-2 以实际定稿文件为准，协调器推进 Gate 前修正标注 | 全部 | 协调器 / Contract |

TD-1 结论：**`TEST DESIGN READY`** —— A1–A21 已映射到可观察判据，边界/并发场景（归属校验 B4–B6/B39/B40、监听唯一部分唯一双会话 B9/B10/B37/B38/B41、protocol/port 边界 B7/B8、**双 provider 端到端 B12/B14/B15/B16/B17**、软删/恢复重检 B18–B24、乐观锁 B31/B32）可执行，夹具与可验证性已与 architecture §1/§5/§6/§7/§9 及 Contract v1 建立对应；真实 PostgreSQL + `committed_engine` 真提交口径固定；三分界明确（F012 独立 / 留待 F013 展示聚合 / F016 整体回归）。**DATABASE / D01 v11 / F010 errata 尚未定稿，§8 OPEN-1–20 未经逐项核对；READY 不等于测试通过，不批准实现或合并。** 定稿后由 TD-2 关闭 §8 并固定执行判据。

---

## 9. 版本记录（续）

| 版本 | 日期 | 变更 |
| --- | --- | --- |
| TD-1 | 2026-10-11 | 初版 Test Design（见 §Test Design）。 |
| TD-2 | 2026-10-12 | 依 Database v1、Contract v1、D01 v11 §5.11、F010 errata-03 逐项关闭 §8 OPEN-1–20，并入 Architect 定稿判据调整（见 §10）。 |
| TE-1 | 2026-10-12 | 首次独立执行（基线 HEAD=e5c1504）：A1–A21、V-DB-126–138、B1–B45 结果与证据；新增 Tester 独立套件 10 项（见 §11）。结论 `READY FOR REVIEW`。 |
| TE-2 | 2026-10-12 | 有限修复第 1 轮复核：F012-RV-01（`port` 未用 StrictInt，lax 接受 `"80"`/`true`）关闭；独立重跑全量 `438 passed/1 skipped`（F012 合计 44）；真实 API 探针 `"80"`/`True`/`22.5`→422 field="port"、`1`/`65535`→201/200（POST/PATCH）。基线 HEAD=c93b47a + 未提交修复。见 §12。 |

> **TD-1 Git 记录**：
> ```text
> GIT: git rev-parse --short HEAD
> GIT: git branch --show-current
> GIT: git status --porcelain
> ```

---

## 10. Test Design 复核（TD-2）

- **版本**：TD-2
- **日期**：2026-10-12
- **角色**：Tester（TEST_DESIGN 模式复核）
- **结论**：`TEST DESIGN READY`（TD-2；§8 OPEN-1–20 全部关闭，未验证项保持明确标注）
- **复核依据（已定稿）**：
  - `docs/database/f012-service-endpoint.md` v1（Database 2026-10-09，DB-D142–DB-D156）
  - `docs/api/F012.md` v1（Contract READY，Architect 2026-10-09）
  - `docs/architecture/d01-conventions.md` v11（§5.2、§5.11、§8 修订记录）
  - `docs/api/F010.md` v1 + **errata-03**（2026-10-09，`object_type` `"endpoint"`→`"service_endpoint"`，桩测试同步）
  - `docs/features/F012/{product,architecture,implementation}.md`（A1–A21、DR-155–DR-170）
- **状态属性**：TD-2 `READY` 仅表示 A1–A21 判据已与定稿设计逐项对齐、可执行；不代表测试已运行、不批准实现或合并。测试执行见 §11（TE-1）。

### 10.1 §8 OPEN-1–20 关闭结论

| # | 定稿结论（判据固定） | 关闭依据 |
| --- | --- | --- |
| OPEN-1 | 表 `service_endpoints`；列/类型/必填/默认与 DB v1 §2 一致（`id uuid pk gen_random_uuid()`、`service_id uuid NOT NULL`、`ip_address_id uuid NOT NULL`、`protocol varchar(8) NOT NULL`、`port integer NOT NULL`、`description text NULL`、`version int NOT NULL DEFAULT 1`、`created_at/updated_at timestamptz NOT NULL now()`、`deleted_at timestamptz NULL`） | DB v1 §2；V-DB-126/127；实测目录 + 独立库 raw SQL 一致 |
| OPEN-2 | 约束/索引名：`pk_service_endpoints`、`fk_service_endpoints_service_id_services`、`fk_service_endpoints_ip_address_id_ip_addresses`、`ck_service_endpoints_{protocol,port,version}`、`uq_service_endpoints_ip_protocol_port`、`ix_service_endpoints_{service_id,ip_address_id,deleted_at}` | DB v1 §2；V-DB-126/134；实测目录一致 |
| OPEN-3 | 部分唯一精确形态 `UNIQUE(ip_address_id,protocol,port) WHERE deleted_at IS NULL`；同 IP 未删唯一、不同 IP 允许、软删释放、恢复冲突拒 | DB v1 §3.1/DB-D149；V-DB-130/136 |
| OPEN-4 | `ck_service_endpoints_protocol` ∈{TCP,UDP}；`ck_service_endpoints_port` 1–65535（含端点）；仅大写规范值存储 | DB v1 §3.2/DB-D145/146；V-DB-128/129 |
| OPEN-5 | **归属 backstop 采纳并确定存在**：`fn_service_endpoints_attribution` + `trg_service_endpoints_attribution`（BEFORE INSERT/UPDATE，逐行；**不检查软删、不加行锁**）；未绑定/跨 Resource 抛 `restrict_violation`（实测 SQLSTATE=`23001`）。V-DB-5/B6/B39 判据改为断言**触发名/时机**及 SQLSTATE；归属窗口由 F010 provider + 触发**双证**（触发器保证写入时点结构归属，F010 在 IP 事务内调用 provider 拦截解绑/转移） | DB v1 §3.3/DB-D150；V-DB-132；独立库 raw SQL（pg_trigger `tgtype=23`、SQLSTATE 23001） |
| OPEN-6 | `service_id`/`ip_address_id` NOT NULL FK `ON DELETE RESTRICT`；`service`/`ip_address` 创建后不可改**仅为应用 422**（PATCH 出现不可变字段→422）；**DB 无不可变触发器**，DB 层 `UPDATE service_id=...` 不被阻止 | DB v1 §3.4/DB-D151；V-DB-133；独立库 raw SQL（`UPDATE service_id` 成功） |
| OPEN-7 | 索引集合=部分唯一 + 3 普通 btree（`service_id`/`ip_address_id`/`deleted_at`）；**不建** pg_trgm/GIN、不建独立 `protocol` 索引、不重复启用扩展 | DB v1 §3/DB-D152；V-DB-134 |
| OPEN-8 | `version` DEFAULT 1、CHECK ≥1；时间戳列；`deleted_at` 可空；软删/恢复与部分唯一交互 | DB v1 §2/§3；V-DB-127/135/136 |
| OPEN-9 | 迁移 `0012_service_endpoints`（`down_revision=0011_services`）单 head、全表新建无回填、对称可逆、不重复启用扩展 | DB v1 §4；V-DB-126/138 |
| OPEN-10 | 恢复重检 DB 层：部分唯一重新入索引拒冲突；归属触发在恢复（UPDATE）时重跑；越界/存活/依赖交应用 | DB v1 §3.3/§5；V-DB-130/136 |
| OPEN-11 | 错误码复用集固定：`unique_conflict` details `{field:"port",ip_address_id,protocol,port}`；`not_deleted` `{}`；`dependency_deleted` `conflicts:[{object_type:"service"\|"ip_address"\|"interface",object_id}]`；`reference_exists` `references:[{object_type:"service_endpoint",object_id,label}]`；F012 **不新增** code/reason | Contract v1 §1.2/§6；V8/V12/V13/V14；B9/B12/B14/B15/B21/B24 |
| OPEN-12 | `object_type` canonical=`"service_endpoint"`；**F010 errata-03 已落地**（`docs/api/F010.md` §1.2 + 修订记录；`backend/tests/integration/test_ip_addresses.py` 4 处桩测试同步） | F010 errata-03；Contract v1 §1.2/§9；B14/`test_reference_providers_registered` |
| OPEN-13 | 校验顺序固定：POST 401→403→body(422)→service→ip_address 存在/未软删→归属→protocol→port→唯一(409)→写+Audit→201；PATCH 401→403→body→可见性(404)→version(409)→取值(422)→唯一重检(409)→写→200；DELETE 对象(404)→version 校验(422)→版本(409)→软删；**restore 确定性优先级 唯一(409)→依赖(409)→归属(422)** | Contract v1 §6；V23/B22/B43 |
| OPEN-14 | 列表 Query=`service_id/ip_address_id/protocol/deleted/page/page_size/sort/order`；`deleted∈{exclude,include,only}`；`sort∈{protocol,port,created_at,updated_at}`、`sort=port` 按数值；**不新增** cluster/resource 过滤参数 | Contract v1 §4（DR-167）；V18/B29/B30 |
| OPEN-15 | **D01 v11 §5.11 已签核**（Architect 2026-10-09）：service/ip_address 创建必填、引用须存活、创建后不可改；ip_address 须已绑定 Interface 且属 Service.Resource；protocol∈{TCP,UDP}（大写）；port 1–65535；description 可空无上限；同 IPAddress 未删部分唯一；不落 metadata/name/status；§5 名称表不适用；§8 已记 v11 | D01 v11 §5.2/§5.11/§8 |
| OPEN-16 | 权限：READ/WRITE/DELETE_OBJECT/VIEW_DELETED/RESTORE/VIEW_ACTIVITY（全角色）；审计白名单 `{service_id,ip_address_id,protocol,port,description}`、`object_type="service_endpoint"` | Contract v1 §1.3/§8；V15/V16/B25–B28 |
| OPEN-17 | 响应契约：`service{id,name,resource{id,hostname}}`、`ip_address{id,address,network{id,name},interface{id,name}}` 嵌套；不含 `metadata`/原始 `service_id`/`ip_address_id`；列表 `{items,page,page_size,total}`；软删可见性语义 | Contract v1 §3/§5；V22/B18/B29/B30 |
| OPEN-18 | 双 provider 落点：F012 在启动导入链注册两个**真实** provider（`ip_address_reference.register_ip_address_reference_checker`、`service_reference.register_service_reference_checker`，模块 `app/services/endpoint_reference.py`）；`label=f"protocol/port"`；F010/F011 未删行不参与引用 | Contract v1 §1.2/§9（DR-161）；B12/B14/B15/`test_reference_providers_registered` |
| OPEN-19 | I-2 关闭：CONTRACT 固定 `service`/`ip_address` 创建后不可改（PATCH 出现含同值→422）；`protocol`/`port` 可 PATCH 并重检监听唯一；`description` 可改（显式 null 清空、省略保持） | Contract v1 §2.1/§2.2/§2.5/§6.4；V21/V25/B33/B35 |
| OPEN-20 | **Contract 状态与上游一致性已修正**：`docs/api/F012.md` v1 现引用已存在的 `docs/database/f012-service-endpoint.md` v1 与 `d01-conventions.md` v11 §5.11；F010 errata-03 已落地；0012 迁移与后端代码已交付。TD-1 的一致性观察（NOTE）关闭 | Contract v1 文件头/§10；DB v1；D01 v11 |

### 10.2 对 TD-1 判据的调整（并入 Architect 定稿）

1. **V-DB 编号切换**：执行与报告采用 Database 的 `V-DB-126`–`V-DB-138`；TD-1 的 V-DB-1…9 为其概要等价物，逐一映射见 §11.5。
2. **归属 backstop 由「若裁定」改为确定存在**：V-DB-5/B6/B39 断言 `trg_service_endpoints_attribution` 名称、`BEFORE INSERT OR UPDATE` 时机、`restrict_violation`（SQLSTATE 23001）；软删/普通 UPDATE 不误拒；不检查软删、不加锁。
3. **不可变分层**：应用 PATCH 含 `service`/`service_id`/`ip_address`/`ip_address_id`/`id`→422；DB 无不可变触发器（`UPDATE service_id` 允许）。
4. **错误码 details 形状固定**（OPEN-11）；`dependency_deleted` 的 `object_type∈{service,ip_address,interface}`，`reference_exists` 的 `object_type="service_endpoint"`。
5. **restore 优先级**：唯一(409)→依赖(409)→归属(422)（Contract §6.6）；归属失败为 422，依赖失效为 409。
6. **列表/回退**：非法 `sort`/`order`/`deleted`/`protocol` 及越界分页→422；无 cluster/resource 过滤。
7. **A12/A13 不再以桩替代**：F012 真实 provider 端到端闭合 T22/T23 的 Endpoint 部分（F010 errata-03 已同步）。

---

## 11. TEST 执行（TE-1）

- **版本**：TE-1
- **日期**：2026-10-12
- **角色**：Tester（TEST 模式）
- **执行基线**：Git HEAD `e5c1504`，分支 `feature/F012-service-endpoint`
- **依据**：`docs/database/f012-service-endpoint.md` v1、`docs/api/F012.md` v1、`docs/architecture/d01-conventions.md` v11 §5.11、`docs/api/F010.md` v1+errata-03、`docs/features/F012/{product,architecture,implementation}.md`、TD-2（§10）
- **结论**：`READY FOR REVIEW`（F012 独立范围全部通过；无必须修复的实现缺陷；§18/§19/§17/§20 展示聚合与 F016 整体回归明确 `NOT TESTED`）

### 11.1 独立性声明

- Backend pytest 由 Tester 在本容器内独立重跑，不复用实现报告数字；实现报告称 427 passed/1 skipped（F012 33），本次独立复跑一致。
- 追加 Tester 独立套件 `backend/tests/integration/test_service_endpoints_tester.py`（10 项，Tester 编写），定向覆盖实现套件未直接断言的验收点：B28 四 action 审计同事务回滚、B31 两真实会话乐观锁、B41 恢复 vs 并发重建、B22 restore 优先级、B32 软删对象过期 version→404、A5 **跨 Cluster** 归属、B29 列表参数校验、V22 响应契约形状、B14 IP 引用列表全集与 label、V24/B45 只读无副作用。
- 迁移 up/down/up、约束/索引/触发目录、部分唯一、CHECK、FK RESTRICT、SQLSTATE 在真实 PostgreSQL（独立库 `f012_tester` 与测试库 `csm_test`）执行；未连接生产或未知数据库（`f012_tester` 为本次新建的一次性验证库，验证后 `DROP DATABASE`）。
- 只读功能（GET 列表/详情/activity）确认无业务写副作用（version/updated_at/audit 行不变）。

### 11.2 环境

| 项 | 值 |
| --- | --- |
| PostgreSQL | 容器 `f002test-db`（`postgres:16`），网络 `f002test-net`；测试库 `csm_test`（csm/change-me） |
| 后端镜像 | `csm-f007-test`，源码挂载 `-v $PWD/backend:/app`；`TEST_DATABASE_URL=postgresql+psycopg://csm:change-me@f002test-db:5432/csm_test` |
| 独立迁移验证库 | `f012_tester`（`f002test-db` 上 `CREATE DATABASE`，同一 `csm-f007-test` 镜像运行 alembic/raw SQL，验证后 `DROP DATABASE`） |
| 前端 | Node v22.23.2；`frontend/node_modules` 已存在 |
| 安全护栏 | 测试库名含 `test`；`TEST_DATABASE_URL != DATABASE_URL`（conftest DB-D10）；未使用 SQLite/Mock 作约束/并发证据 |

### 11.3 执行命令与输出

| # | 命令（要点） | 输出 |
| --- | --- | --- |
| E1 | 全量后端 `pytest tests -q`（实现基线复跑） | `427 passed, 1 skipped`（skip=`test_migrations.py` V3b superuser 环境性） |
| E2 | F012 专属 `pytest tests/integration/test_service_endpoints.py tests/integration/test_service_endpoint_constraints.py -q` | `33 passed`（18+15） |
| E3 | Tester 独立套件 `pytest tests/integration/test_service_endpoints_tester.py -q` | `10 passed` |
| E4 | 全量后端（含 Tester 10 项）`pytest tests -q` | `436 passed, 1 skipped`（F012 合计 43） |
| E5 | 独立库 `f012_tester`：`alembic upgrade head` → raw SQL → `alembic downgrade 0011_services` → `alembic upgrade head` | 单一 head `0012_service_endpoints`；up 建表/触发/索引；down 后 `service_endpoints` 与 `fn_service_endpoints_attribution` 消失、`services` 保留；re-up 恢复；扩展 `plpgsql,pg_trgm,btree_gist` 前后一致 |
| E6 | 独立库 raw SQL：`pg_trigger`/`pg_constraint`/`pg_indexes`/SQLSTATE | 触发 `tgtype=23`（BEFORE/INSERT/UPDATE）；约束 6 个（PK+2 FK+3 CHECK）；索引 5 个含 `uq_service_endpoints_ip_protocol_port ... WHERE (deleted_at IS NULL)`；未绑定/跨 Resource 抛 `SQLSTATE=23001`（restrict_violation）；`UPDATE service_id` 成功（无不可变触发器） |
| E7 | 前端 `cd frontend && npm run typecheck && npm run build && npm run smoke:client` | typecheck 通过；build 74 modules 成功；`211 passed, 0 failed` |
| E8 | `python3 scripts/validate_project_state.py --feature F012` | `PROJECT STATE VALID`（结构/Gate/文件；批准真值与 Git 证据需另行核验） |
| E9 | 静态核对：响应/ORM 无 `metadata`/`name`/`status`/`listen_address`；列表无 cluster/resource 过滤；provider 注册存在 | 通过 |

### 11.4 验收映射 A1–A21

| 验收 | 结果 | 证据（验证项 / 测试） |
| --- | --- | --- |
| A1 必填缺失/未知只读字段→422 | PASS | V1/V-DB-127；`test_create_required_and_unknown_fields`、`test_defaults_and_not_null` |
| A2 service 不存在/软删→422 field="service" | PASS | V2；`test_service_and_ip_reference_validation` |
| A3 ip_address 不存在/软删→422 field="ip_address" | PASS | V3；`test_service_and_ip_reference_validation` |
| A4 未绑定 IP→422 field="ip_address" | PASS | V4/V-DB-132；`test_attribution_unbound_and_cross_resource`、`test_attribution_trigger` |
| A5 跨 Resource/**跨 Cluster**→422 | PASS | V5/V-DB-132；`test_attribution_unbound_and_cross_resource`、`test_attribution_cross_cluster_rejected`、`test_attribution_trigger` |
| A6 protocol 非 TCP/UDP（含 null）→422；TCP/UDP 登记 | PASS | V6/V-DB-128；`test_protocol_and_port_validation`、`test_protocol_check` |
| A7 port 边界 1/65535 接受、0/65536/-1/非整数/null→422 | PASS（TE-2 复核） | V7/V-DB-129；`test_protocol_and_port_validation`（TE-2 扩展 `"80"`/`True`/`False`/`"22"`/`22.5`→422 field="port"）、`test_patch_port_strict_integer`（TE-2 新增：PATCH port 同口径 strict 1..65535）、`test_port_check` |
| A8 同 IP 重复 (protocol,port)→409 unique_conflict | PASS | V8/V-DB-130；`test_listener_uniqueness_same_ip_and_across_ips`、`test_partial_unique_listener` |
| A9 不同 IP 同 (protocol,port) 允许 | PASS | V9/V-DB-130；`test_listener_uniqueness_same_ip_and_across_ips`、`test_partial_unique_listener` |
| A10 一 Service 多 Endpoint | PASS | V10；`test_many_endpoints_and_description_semantics` |
| A11 description 省略/显式 null/保持 | PASS | V11；`test_many_endpoints_and_description_semantics` |
| A12 IP 解绑/转移/释放引用保护端到端 | PASS | V12/T22；`test_ip_reference_blocks_unbind_transfer_release`、`test_ip_reference_list_all_undeleted_with_labels` |
| A13 Service 删除引用保护端到端 | PASS | V13/T23；`test_service_reference_blocks_delete` |
| A14 软删/恢复重检、失败不覆盖、不级联 | PASS | V14/V-DB-130/136；`test_soft_delete_restore_and_dependency_rechecks`、`test_restore_uniqueness_conflict`、`test_restore_priority_uniqueness_before_dependency` |
| A15 权限矩阵（服务端） | PASS | V15；`test_permissions_matrix` |
| A16 四 action 审计同事务、object_type、白名单 | PASS | V16；`test_activity_trail_and_whitelist`、`test_failed_create_writes_no_audit`、`test_audit_failure_rolls_back_endpoint_writes`、`test_read_only_has_no_side_effects` |
| A17 乐观锁过期 409，无静默覆盖 | PASS | V17/V-DB-135；`test_optimistic_lock_and_immutable_fields`、`test_version_and_optimistic_lock`、`test_optimistic_lock_two_sessions`、`test_stale_version_on_soft_deleted_is_404` |
| A18 列表过滤/分页/排序/软删 | PASS | V18；`test_list_filters_sorting_pagination`、`test_list_parameter_validation` |
| A19 非法监听形式被拒 | PASS | V19；`test_invalid_listen_forms_rejected` + 静态 E9 |
| A20 DB 部分唯一兜底 + 并发仅一成功 | PASS | V20/V-DB-130；`test_partial_unique_listener`、`test_concurrent_same_listener_insert`、`test_restore_vs_recreate_concurrency` |
| A21 D01 §4 省略语义/不可变只读字段 422 | PASS | V21；`test_optimistic_lock_and_immutable_fields`、`test_create_required_and_unknown_fields` |

### 11.5 数据库机制级验证 V-DB-126–138

| 编号 | 结果 | 证据（TD-1 V-DB 等价） |
| --- | --- | --- |
| V-DB-126 迁移 up/down/up、单 head、对象齐全、无回填、扩展无新增 | PASS | E5/E6；`test_migration_up_down_up_and_single_head`、`test_table_catalogue_columns_constraints_indexes_triggers`（V-DB-1/2/6/8/9） |
| V-DB-127 默认/NOT NULL | PASS | `test_defaults_and_not_null`（V-DB-3/4） |
| V-DB-128 `ck_protocol`：TCP/UDP 接受，tcp/udp/SCTP/空/NULL 拒 | PASS | `test_protocol_check`（V-DB-2） |
| V-DB-129 `ck_port`：1/65535 接受，0/65536/-1/NULL 拒 | PASS | `test_port_check`（V-DB-2） |
| V-DB-130 部分唯一：同 IP 重复拒/异 protocol·port 接受/异 IP 接受/软删释放/恢复冲突/并发仅一成功 | PASS | `test_partial_unique_listener`、`test_restore_recheck_partial_unique`、`test_concurrent_same_listener_insert`、E6（V-DB-1/7） |
| V-DB-131 FK RESTRICT；软删 Service/IP 行仍在 | PASS | `test_fk_restrict_and_soft_delete_retention`（V-DB-3/9） |
| V-DB-132 归属触发：未绑定/跨 Resource→restrict_violation；匹配成功；软删/普通 UPDATE 不误拒；恢复重跑 | PASS | `test_attribution_trigger`、E6（SQLSTATE 23001）、独立库 raw SQL（V-DB-5） |
| V-DB-133 无不可变触发器；DB 层 UPDATE 不被阻止 | PASS | `test_no_immutability_trigger`、E6（V-DB-6） |
| V-DB-134 索引目录：部分唯一谓词正确；三索引存在；无 GIN/无独立 protocol 索引 | PASS | `test_table_catalogue_columns_constraints_indexes_triggers`、E6（V-DB-6） |
| V-DB-135 version 默认 1、<1 拒；乐观锁双会话仅一成功 | PASS | `test_defaults_and_not_null`、`test_version_and_optimistic_lock`、`test_optimistic_lock_two_sessions`（V-DB-4） |
| V-DB-136 恢复重检 DB 层：软删同名重建后恢复被部分唯一拒；归属触发恢复重跑 | PASS | `test_restore_recheck_partial_unique`、`test_attribution_trigger`（V-DB-7） |
| V-DB-137 引用集：DB 无 soft-delete 约束；reference_exists 由 F012 两 provider 承担 | PASS | `test_reference_set_has_no_db_constraint`、`test_reference_providers_registered`、`test_ip_reference_blocks_unbind_transfer_release`、`test_service_reference_blocks_delete` |
| V-DB-138 迁移边界：0012 不含 CREATE EXTENSION；downgrade 后再 upgrade；既有表无结构改动 | PASS | `test_migration_0012_has_no_create_extension`、`test_existing_tables_not_altered`、E5（V-DB-8） |

### 11.6 边界与并发场景 B1–B45

| 编号 | 结果 | 证据 |
| --- | --- | --- |
| B1 | PASS | `test_create_required_and_unknown_fields` |
| B2 | PASS | `test_protocol_and_port_validation`（protocol/port 显式 null）；schema `extra/required` 强制 service/ip 非 null |
| B3 | PASS | `test_create_required_and_unknown_fields` |
| B4 | PASS | `test_service_and_ip_reference_validation` |
| B5 | PASS | `test_service_and_ip_reference_validation`、`test_attribution_unbound_and_cross_resource` |
| B6 | PASS | `test_attribution_unbound_and_cross_resource`、`test_attribution_cross_cluster_rejected`、`test_attribution_trigger` |
| B7 | PASS | `test_protocol_and_port_validation`、`test_protocol_check` |
| B8 | PASS | `test_protocol_and_port_validation`、`test_port_check` |
| B9 | PASS | `test_listener_uniqueness_same_ip_and_across_ips` |
| B10 | PASS | `test_listener_uniqueness_same_ip_and_across_ips`、`test_partial_unique_listener` |
| B11 | PASS | `test_many_endpoints_and_description_semantics` |
| B12 | PASS | `test_ip_reference_blocks_unbind_transfer_release` |
| B13 | PASS | `test_ip_reference_blocks_unbind_transfer_release`（软删后解绑成功） |
| B14 | PASS | `test_ip_reference_list_all_undeleted_with_labels` |
| B15 | PASS | `test_service_reference_blocks_delete` |
| B16 | PASS | `test_service_reference_blocks_delete` |
| B17 | PASS | 软删测试仅改 `deleted_at`/version；无 Endpoint 触碰 Service/IP/Interface（静态 E9） |
| B18 | PASS | `test_permissions_matrix`、`test_list_filters_sorting_pagination` |
| B19 | PASS | `test_soft_delete_restore_and_dependency_rechecks` |
| B20 | PASS | `test_restore_uniqueness_conflict`、`test_restore_recheck_partial_unique` |
| B21 | PASS | `test_soft_delete_restore_and_dependency_rechecks`（service/ip_address/attribution） |
| B22 | PASS | `test_restore_priority_uniqueness_before_dependency` |
| B23 | PASS | `test_soft_delete_restore_and_dependency_rechecks` |
| B24 | PASS | `test_soft_delete_restore_and_dependency_rechecks`（`not_deleted`） |
| B25 | PASS | `test_permissions_matrix` |
| B26 | PASS | `test_permissions_matrix` |
| B27 | PASS | `test_activity_trail_and_whitelist` |
| B28 | PASS | `test_audit_failure_rolls_back_endpoint_writes`（四 action）、`test_failed_create_writes_no_audit` |
| B29 | PASS | `test_list_filters_sorting_pagination`、`test_list_parameter_validation` |
| B30 | PASS | `test_list_filters_sorting_pagination` |
| B31 | PASS | `test_version_and_optimistic_lock`、`test_optimistic_lock_two_sessions` |
| B32 | PASS | `test_stale_version_on_soft_deleted_is_404` |
| B33 | PASS | `test_many_endpoints_and_description_semantics`、`test_patch_listener_uniqueness` |
| B34 | PASS | `test_patch_listener_uniqueness` |
| B35 | PASS | `test_optimistic_lock_and_immutable_fields`、`test_no_immutability_trigger` |
| B36 | PASS | `test_invalid_listen_forms_rejected` + 静态 E9 |
| B37 | PASS | `test_partial_unique_listener`、`test_defaults_and_not_null` |
| B38 | PASS | `test_concurrent_same_listener_insert`（raw 双会话真提交，断言最终唯一行）；API 层 409 由 `test_listener_uniqueness_same_ip_and_across_ips` 覆盖 |
| B39 | PASS | `test_attribution_trigger` + E6（SQLSTATE 23001，触发在写入时点恒成立） |
| B40 | PASS | `test_ip_reference_blocks_unbind_transfer_release`（解绑/转移窗口由 F010 provider 拦截） |
| B41 | PASS | `test_restore_vs_recreate_concurrency`（真实部分唯一仲裁，最终仅一未删行） |
| B42 | PASS | `test_fk_restrict_and_soft_delete_retention`、目录 `confdeltype='r'`（机制级） |
| B43 | PASS | POST/PATCH/DELETE/restore 用例抽查 + Contract §6 静态核对；restore 优先级见 B22 |
| B44 | PASS | E5；`test_migration_up_down_up_and_single_head` |
| B45 | PASS | `test_read_only_has_no_side_effects` |

### 11.7 三分界声明

1. **F012 独立可验证（本次全部执行）**：A1–A21（含 A12/A13 的真实双 provider 端到端）、V-DB-126–138、B1–B45；对应 §31 T22/T23 的 **Endpoint 部分**（含真实 Endpoint 的引用保护）、T24/T25/T26/T37/T40/T41 的 Endpoint 子集。
2. **留待 F013（本 Feature 不可执行）**：§18 Resource Detail Services 区域、§19 Cluster Detail、§17 全局搜索、§20 Dashboard 的页面/聚合展示；F012 仅提供 Endpoint 数据与 `/api/v1/service-endpoints`。
3. **留待 F016（整体验收）**：T22–T26 的跨对象完整回归与 §32 上线验收；F012 局部 PASS **不得**拼成整条通过。

### 11.8 Defects

| ID | Severity | Layer | Location | 期望/实际 | Owner | 必须修复 |
| --- | --- | --- | --- | --- | --- | --- |
| F012-TE1-01 | NOTE | Backend 测试 | `backend/tests/integration/test_service_endpoints.py::test_invalid_listen_forms_rejected` | 覆盖 `"1-100"/"22,80"/0`，未逐一断言 `listen_address`/`host`/`socket`/`port_range` 等未知字段的 422；A19 其余面由 schema `extra="forbid"` + 静态核对闭合（未发现缺陷） | Backend（可选补强） | 否 |
| F012-TE1-02 | NOTE | 集成环境 | Compose/Nginx 真实前后端 | `compose.yaml` 的后端/前端需 `docker build`，本轮按任务约束未构建；前端以 `typecheck`+`build`+`smoke:client` 机制级验证。不降 F012 验收（真实浏览器 DOM 非必要判据） | 协调器 | 否 |

无 BLOCKER/HIGH/MEDIUM 缺陷；未发现必须修复的问题。

### 11.9 未验证项

| 项 | 状态 | 原因 |
| --- | --- | --- |
| §18 Resource Detail Services、§19 Cluster Detail、§17 全局搜索、§20 Dashboard 聚合展示 | `NOT TESTED / 归 F013` | F012 仅提供 Endpoint 数据与列表/详情 API |
| T22–T26 跨对象完整回归与 §32 上线验收 | `NOT TESTED / 归 F016` | 不由 F012 局部 PASS 拼接 |
| CSV/Excel 导入（§24） | `NOT TESTED / 归 F014` | 导入不在 F012 |
| 完整 Audit 查询页（§22） | `NOT TESTED / 归 F015` | F012 仅验证资源级 Activity 四 action |
| Compose 入口 Nginx 真实前后端集成 / 真实浏览器 DOM | `NOT TESTED / BLOCKED（环境）` | Compose 需构建镜像（任务禁止 `docker build`）；见 F012-TE1-02 |
| F001 `test_migrations` V3b | `SKIPPED` | 连接角色为 superuser，环境性跳过（非 F012） |

### 11.10 TE-1 结论

- F012 独立范围 A1–A21、V-DB-126–138、B1–B45 全部 PASS；无 BLOCKER/HIGH/MEDIUM，无必须修复的实现缺陷。
- 独立复跑：实现基线 `427 passed/1 skipped`（F012 33）；新增 Tester 套件 10 项，含 B28 四 action 审计同事务回滚、B31 两真实会话乐观锁、B41 恢复 vs 并发重建、B22 restore 优先级、B32 软删对象过期 version→404、A5 跨 Cluster 归属、B29 列表参数校验、V22 响应契约、B14 引用列表全集与 label、V24/B45 只读无副作用；全量 `436 passed/1 skipped`（F012 合计 43）。
- 数据库机制级：部分唯一、CHECK、FK RESTRICT、归属触发（名称/时机/SQLSTATE 23001）、无不可变触发器、迁移 0012 up/down/up 与扩展不变，均在真实 PostgreSQL 独立库验证。
- 前端 `typecheck`/`build`/`smoke:client`（211/0）通过；真实 Nginx 集成因环境（禁止构建镜像）记 `NOT TESTED / BLOCKED`，不降验收。
- §18/§19/§17/§20 与 F016 整体回归保持 `NOT TESTED`，不声明整条 §31 通过。

**结论：`READY FOR REVIEW`**

---

GIT: git rev-parse --short HEAD
GIT: git branch --show-current
GIT: git status --porcelain

---

## 12. TEST 复核（TE-2，有限修复第 1 轮）

- **版本**：TE-2
- **日期**：2026-10-12
- **角色**：Tester（TEST 模式复核）
- **复核对象**：Reviewer 缺陷 `F012-RV-01`（MEDIUM）：`port` 使用裸 `int`，pydantic lax 接受 `"80"`（201）、`true`（201）；应 `StrictInt`→422 `field="port"`。
- **代码基线**：Git HEAD `c93b47a`，分支 `feature/F012-service-endpoint`，**叠加未提交修复**。
- **候选构成（重要）**：本次复核的候选**包含未提交改动**（`git status --porcelain` 三条 `M`），未提交内容为：
  1. `backend/app/schemas/service_endpoint.py`：新增 `Port = Annotated[StrictInt, Field(ge=1, le=65535)]`，`ServiceEndpointCreateRequest.port` 与 `ServiceEndpointUpdateRequest.port` 均改用 `Port`；
  2. `backend/app/services/service_endpoint.py`：`_validate_port` 布尔守卫补防御性注释（行为不变，仅说明 API 路径已由 schema 拦截）；
  3. `backend/tests/integration/test_service_endpoints.py`：`test_protocol_and_port_validation` 的非法 port 用例扩展 `"80"`/`True`/`False`/`"22"`，并新增 `test_patch_port_strict_integer`（PATCH 端同口径 422/200 边界）。
  上述未提交改动**未 commit**；本复核结论仅对「HEAD `c93b47a` + 该未提交修复」的候选成立，协调器在正式 Review/合并前须以实际提交内容为准。
- **结论**：`READY FOR REVIEW`（`F012-RV-01` 已关闭；F012 独立范围全部通过，无必须修复的实现缺陷）

### 12.1 F012-RV-01 复核（真实 API 探针）

独立探针经真实 ASGI 应用 + 真实 PostgreSQL（`csm_test`）经 `TestClient` 逐项执行（探针文件为一次性临时文件，执行后删除，不计入仓库测试计数）：

| 端点 | 输入 `port` | 期望 | 实测 | 判定 |
| --- | --- | --- | --- | --- |
| POST /api/v1/service-endpoints | `"80"` | 422 `field="port"` | 422 `field="port"` | PASS |
| POST | `True` | 422 `field="port"` | 422 `field="port"` | PASS |
| POST | `22.5` | 422 `field="port"` | 422 `field="port"` | PASS |
| POST | `1` | 201 | 201，`port=1` | PASS |
| POST | `65535` | 201 | 201，`port=65535` | PASS |
| PATCH /api/v1/service-endpoints/{id} | `"80"` | 422 `field="port"` | 422 `field="port"` | PASS |
| PATCH | `True` | 422 `field="port"` | 422 `field="port"` | PASS |
| PATCH | `22.5` | 422 `field="port"` | 422 `field="port"` | PASS |
| PATCH | `1` | 200 | 200，`port=1` | PASS |
| PATCH | `65535` | 200 | 200，`port=65535` | PASS |

`"80"`/`True`/`22.5` 在 schema 层（pydantic `StrictInt`）即被拒，应用层 `_validate_port` 的布尔守卫保持为直接服务层调用者的纵深防御。原缺陷的 lax 接受行为未复现，**`F012-RV-01` 关闭**。

### 12.2 独立重跑命令与输出

| # | 命令（要点） | 输出 | 与 Backend 声明 |
| --- | --- | --- | --- |
| E10 | `pytest tests/integration/test_service_endpoints.py tests/integration/test_service_endpoints_tester.py tests/integration/test_service_endpoint_constraints.py -q`（真实 PG `csm_test`） | `44 passed` | 一致 |
| E11 | `pytest tests -q`（全量，真实 PG `csm_test`） | `438 passed, 1 skipped`（skip=`test_migrations.py` V3b superuser 环境性） | 与 Backend 报的 438/1 一致（Tester 独立复跑） |
| E12 | 一次性探针 `pytest tests/integration/test_te2_probe_tmp.py -q -s`（真实 API，见 §12.1；执行后已删除） | `10 passed` | 独立探针 |

F012 计数：`test_service_endpoints.py` 19 + `test_service_endpoints_tester.py` 10 + `test_service_endpoint_constraints.py` 15 = **44**。

### 12.3 A7 / B8 受影响项状态

| 项 | 状态 | 复核证据 |
| --- | --- | --- |
| A7 port 边界 1/65535 接受、0/65536/-1/非整数/null→422 | **PASS（复核更新）** | E10 `test_protocol_and_port_validation`（`"80"`/`True`/`False`/`"22"`/`22.5`→422 field="port"）、`test_patch_port_strict_integer`（PATCH 同口径）、`test_port_check`；E12 真实 API 探针 |
| B8 port 边界（含 `"80"`/非整数） | **PASS（复核更新）** | 同 A7；POST 与 PATCH 均将 `"80"`/`True`/`22.5` 判为 422 `field="port"`，`1`/`65535` 接受；raw `ck_service_endpoints_port` CHECK 仍由 `test_port_check` 覆盖 |

其余 A/V-DB/B 项未受本修复影响，维持 TE-1 结果（E10/E11 全量重跑回归通过，无新增 FAIL）。

### 12.4 计数更正

- TE-1 记录全量 `436 passed/1 skipped`（F012 合计 43）。本轮加入 `test_patch_port_strict_integer` 1 项后，F012 合计 44，**当前全量 `438 passed/1 skipped`**。
- 已同步更新 §11.4 的 A7 证据行；§11.1 / §11.3 E1/E4 / §11.10 中的 `436`/`43` 为 **TE-1 时点值**，当前有效计数以 TE-2（438/44）为准。
- TE-1 的环境、数据库机制级结论（部分唯一 / CHECK / FK RESTRICT / 归属触发 / 迁移 0012）本轮未变更，未重跑（不在修复影响面内），保持其原版本证据。

### 12.5 未验证项（TE-2 不变）

| 项 | 状态 | 原因 |
| --- | --- | --- |
| §18 Resource Detail Services、§19 Cluster Detail、§17 全局搜索、§20 Dashboard 聚合展示 | `NOT TESTED / 归 F013` | F012 仅提供 Endpoint 数据与列表/详情 API |
| T22–T26 跨对象完整回归与 §32 上线验收 | `NOT TESTED / 归 F016` | 不由 F012 局部 PASS 拼接 |
| CSV/Excel 导入（§24） | `NOT TESTED / 归 F014` | 导入不在 F012 |
| 完整 Audit 查询页（§22） | `NOT TESTED / 归 F015` | F012 仅验证资源级 Activity 四 action |
| Compose 入口 Nginx 真实前后端集成 / 真实浏览器 DOM | `NOT TESTED / BLOCKED（环境）` | 任务约束未构建镜像；沿用 F012-TE1-02 |
| F001 `test_migrations` V3b | `SKIPPED` | 连接角色为 superuser，环境性跳过（非 F012） |

### 12.6 TE-2 结论

- `F012-RV-01` **CLOSED**：POST/PATCH 的 `port` 对 `"80"`（字符串）、`True`（布尔）、`22.5`（浮点）均返回 422 `field="port"`，`1`/`65535` 正常接受，由真实 API 探针独立确认。
- 独立重跑：F012 定向 44 passed；全量 438 passed / 1 skipped；无新增 FAIL。
- 候选含**未提交**的 backend 修复与测试改动（HEAD `c93b47a` + working tree），需由协调器按 Git 流程处理后再进入正式 Review。

**结论：`READY FOR REVIEW`（TE-2；F012-RV-01 CLOSED）**

---

GIT: git status
GIT: git status --porcelain
GIT: git rev-parse --abbrev-ref HEAD
GIT: git rev-parse --short HEAD
GIT: git log --oneline -5
GIT: git diff
GIT: git ls-files --others --exclude-standard