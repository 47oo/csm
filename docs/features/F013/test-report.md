# F013 全局搜索与 Dashboard — Test Report

本文件同时承载 TEST_DESIGN 与 TEST（TEST 阶段在同一文件追加执行结果）。两阶段分别记录版本、结论与证据；TEST_DESIGN 不填充执行 PASS。

---

## Test Design

- **版本**：TD-1
- **日期**：2026-10-12
- **角色**：Tester（TEST_DESIGN 模式）
- **结论**：`TEST DESIGN READY`（TD-1）
- **依据**：
  - `docs/product/requirements-v3.md` revision 3（§4、§4.1、§5、§7、§11.1、§12、§13、§14、§15、§17、§18、§19、§20、§21、§22、§23、§25、§26、§28、§31 T32/T33、§32、§33、§35.2 Q02-A/Q04-A/Q04-B/Q10-B、§35.3 D01/D02）
  - `docs/features/F013/product.md`（PRODUCT `READY FOR ARCHITECT`；A1–A24、I-1–I-10、OPEN I-11–I-18、明确排除项）
  - `docs/features/F013/architecture.md`（ARCHITECTURE `READY FOR DESIGN` 2026-10-09；DR-171–DR-189、§4 结果模型/去重/排序/空查询、§5 Dashboard 模型、§6 pg_trgm/GIN 引入点与候选索引集合、§7 列表契约收敛、§9 数据库影响、§10 验证策略、§12 待遇核对项）
  - `docs/api/F013.md`（**草案 v0，未签核**）：`GET /api/v1/search`、`GET /api/v1/dashboard` 参数/字段/错误/权限/软删/分页/去重排序/容量口径
  - `docs/api/F010.md` v1 §6.9（`GET /api/v1/networks/{id}/capacity` 容量口径与 `remaining` 负值不截断，DR-130）
  - `docs/api/F003.md` v2（列表基线/分页/错误/软删）、`docs/api/F002.md` §1.1/§1.2/§1.2.1（错误信封与注册表）
  - `docs/architecture/d01-conventions.md` v11（§4 省略语义、§5 归一化、错误码、分页）
  - `backend/app/services/ip_capacity.py`（`network_capacity` / `auto_pools_capacity` / `base_usable_intervals` / `subtract_intervals` 权威口径实现）
  - `backend/tests/conftest.py`（`test_database_url` / `pg_engine` / `db_session` / `committed_engine` / `alembic_runner` / `auth_app` / `api_client` / `bootstrap_admin` / `make_user` / `role_client_factory`）
  - 既有「无 pg_trgm/GIN」断言测试：`backend/tests/integration/test_resource_constraints.py:300`、`test_service_constraints.py:45/210/225/233`、`test_cluster_constraints.py:45/310`、`test_ip_address_constraints.py:43/284`、`test_network_constraints.py:221`、`test_ip_pool_constraints.py:245`、`test_interface_constraints.py:226`、`test_service_endpoint_constraints.py:302`、`test_migrations.py`
  - `docs/project/handoff.md`、`docs/project/implementation-rules.md`、`.pi/skills/data-integrity/SKILL.md`、`AGENTS.md`
  - `docs/project/project-plan.yaml` plan_revision 4 F013（`current_stage: DATABASE`，`next_action: DATABASE + TEST_DESIGN 并行`，layers=database/backend/frontend，api_required=true，F013 依赖 F001–F012 均已 DONE）
- **状态属性**：TD-1 `READY` 仅表示 A1–A24 已映射到可观察判据、边界/并发场景可执行、夹具与可验证性检查已建立；**不代表测试已运行、不填充执行 PASS、不批准实现或合并**。`docs/database/f013-search-index.md` **尚未产出**（DATABASE Gate 未定稿），`docs/api/F013.md` 仍为**草案 v0**，OPEN I-11–I-18 仅由 architecture 给出 PROPOSED→CONTRACT 默认；GIN 索引集合、`type`/`q` 长度上限、去重/排序定稿等判据按 architecture §4–§6 的候选假设建立，§7 OPEN 逐项待 CONTRACT/DATABASE 定稿后由 TD-2 关闭。**不因 DATABASE/Contract 未定稿而直接 BLOCKED**（architecture §1/§4/§5/§6 已给出可执行的命中语义、Dashboard 结构与候选索引；容量口径由 F010 已 DONE 的 `ip_capacity.py` 提供）。

### 版本记录

| 版本 | 日期 | 变更 |
| --- | --- | --- |
| TD-1 | 2026-10-12 | 初版：A1–A24 映射 V1–V24（补充 V25–V33）、V-DB-1…V-DB-8；边界/并发 B1–B30；夹具/环境设计；pg_trgm/GIN 真库 EXPLAIN 判据；各域列表 `q` 契约收敛回归；DR-189 既有 no-GIN 断言更新范围；§7 OPEN 待 CONTRACT/DATABASE 关闭。 |

> **复核基线（待 TD-2）**：`docs/database/f013-search-index.md`（未产出）、`docs/api/F013.md` v1（草案 v0 未签核）。TD-1 的索引名/opclass/表达式/迁移编号 0013/去重排序规则/`q` 长度上限/校验顺序均按 architecture §4–§6 与 Contract v0 假设，TD-2 逐项核对后方可作执行依据。

---

### 0. 数据完整性对应表（F013 范围）

方法依据 `.pi/skills/data-integrity/SKILL.md`。F013 为**只读派生视图**，无写入入口、无新实体/字段/状态；下表聚焦「读取口径」与「库层支撑（索引）」。

| 规则依据及版本 | 作用域/读取入口 | 数据库保证（架构候选，待签核） | 业务层保证 | 并发/生命周期边界 | 验证与证据 |
| --- | --- | --- | --- | --- | --- |
| §21 未删过滤 | `/search` 默认、`/dashboard` `counts` 与 `networks` | 查询条件 `deleted_at IS NULL`；索引（含 GIN）是否 partial 由 Database 裁定 | 搜索默认 `deleted=exclude`；`include/only` 需 VIEW_DELETED；Dashboard 恒为未删 | 软删后即消失、恢复后重现；软删 Network 不参与容量 | A8/A23、V8/V23、V-DB-1/B14/B18/B24 |
| §20/T32 容量口径 | `/dashboard` per-Network 与 AUTO 池 | 无（只读消费 `ip_capacity.py`） | 直接调用 `network_capacity`/`auto_pools_capacity`，不改写、不截断负值 | 与 `/api/v1/networks/{id}/capacity` 逐项一致；停用不清零 | A14–A20、V14–V20、V-DB-4…V-DB-7 |
| §4.1/§7/D01 §5 归一化 | hostname / Cluster code / Service name 匹配 | 归一化键列 `resources.hostname`(ASCII 小写)、`clusters.code_key`(ASCII 大写)、`services.name_key`(ASCII 小写) | 查询先归一化（trim + ASCII 折叠），与唯一性同口径 | 大小写/首尾空白不影响命中；中文/内部空格保留 | A3、V3、B2 |
| §26/§17 pg_trgm 模糊 | `/search` | GIN `gin_trgm_ops` 索引（候选集合待 Database 签核）；`pg_trgm` 由 0001 已启用 | 匹配正确性不依赖索引（仅性能）；缺失迁移功能仍正确 | 迁移 0013 加索引不改表结构、对称可逆 | A12、V12、V-DB-2/V-DB-8/B25 |
| §4 稳定 ID | 结果跳转 | PK UUID | 结果携带 `id`；跳转 Resource/Cluster Detail | 改名不改 id | A10、V10 |
| §23 权限 | `/search`、`/dashboard` | 无 | READ 全角色；`deleted=include/only` 需 VIEW_DELETED（F003 口径） | 401 先于 403 先于 422 | A8/A22、V22、B13 |
| §22 只读 | `/search`、`/dashboard` | 无写 | 无写端点、不写 Audit、无副作用 | 重复调用幂等 | A21、V21/B14 |

---

## 1. 验收映射（product.md A1–A24 → 验证项）

执行环境：`真实 PG` = 独立测试库（库名含 `test`）；`后端集成` = ASGI 应用 + 真实 PG（非 SQLite）；`约束/索引` = 真实 PG raw SQL / `pg_indexes` / `EXPLAIN`；`真提交` = `committed_engine`；`静态` = 路由清单/源码检查；`前端` = 构建 + `smoke:client` 机制级（真实 API 集成经入口 Nginx）。

> **分界声明（关键）**：
> - **F013 独立可验证**：A1–A24 全部（搜索 4 类命中、软删、分页/排序/去重、Dashboard 计数与容量、pg_trgm/GIN、权限、只读）；§31 **T32**（Dashboard 容量）与 **T33**（全局搜索/§33 目标查询）的核心闭环在本 Feature 闭合。
> - **F013 消费 F010 已 DONE 口径**：A14–A20 的容量正确性依赖 `ip_capacity.py`（F010 已交付）；F013 只验证「透传/逐项一致 + 展示规则（负值、状态/许可分列）」，不重验 F010 公式实现（该部分归 F010 TE）。
> - **§18 Resource Detail / §19 Cluster Detail 正文**：F013 仅作为**跳转目标**（A10）；详情页字段与区域由 F003/F004 等维护，F013 不重复定义（product §8）。
> - **完整跨功能 §31/§32 集成验收（F016）**：F013 只承载搜索与 Dashboard 入口；**不得以 F013 局部 PASS 拼接整体通过**。
> - **A24 为排除项**：以「不存在 SN/MAC/Role/GPU Model 匹配入口 + 静态无对应字段」判为 PASS，不作为功能验收。

| 验收（product.md） | 验证项 | 测试类型 | 前置数据 | 可观察判据（PASS / FAIL） |
| --- | --- | --- | --- | --- |
| A1 首页统一搜索入口，同一次查询接受 hostname/IP/Cluster/Service | **V1**；**V33** | 后端集成 + 前端 | 跨 Cluster 的 Resource（hostname `gpu0701`）、绑定 IP、Cluster、Service | PASS：一次 `GET /api/v1/search?q=…` 可返回多类 `object_type`；`type` 缺省时四类均可命中；前端首页存在统一入口且输入+下拉均可输入/模糊。FAIL：仅支持单一类型、需多接口拼装 |
| A2 模糊 hostname：`gpu07` 命中 `gpu0701/gpu0702/gpu0725` 并返回对应 Resource | **V2** | 后端集成 + 真实 PG | 同 Cluster 建 `gpu0701/gpu0702/gpu0725/gpu0801` Resource | PASS：`q=gpu07` 返回三条 `object_type=resource`（0701/0702/0725），不含 `gpu0801`；`matched_field="hostname"`。FAIL：子串未命中、命中无关行 |
| A3 hostname 归一化：大小写/首尾空白不影响命中 | **V3** | 后端集成 | Resource `hostname="CN001"`（归一化键 `cn001`） | PASS：`q=cn001`、`q=CN001`、`q=" cn001 "` 均命中同一 Resource 且结果一致。FAIL：大小写敏感、首尾空白导致未命中 |
| A4 输入 IP 命中所属 Interface→Resource，返回 Resource（含 cluster 归属） | **V4** | 后端集成 + 真实 PG | Cluster→Resource→Interface（已绑定 IP `10.10.1.10`） | PASS：`q=10.10.1.10` 返回 `object_type=ip_address`，嵌入 `resource.hostname` 与 `resource.cluster{id,code,name}`；`ip_address.interface` 非空。FAIL：resource 为空、归属错 |
| A5 输入未绑定 Interface 的 IP 命中该 IPAddress，Resource 归属为空 | **V5** | 后端集成 + 真实 PG | Network 内 `interface_id IS NULL` 的未删 IP | PASS：命中 `object_type=ip_address` 且 `resource=null`；不伪造归属。FAIL：报错、伪造 resource、漏命中 |
| A6 输入 Cluster（code 或 name）命中该 Cluster 并可跳转 Detail | **V6** | 后端集成 | Cluster `code="N96P"`、`name="集群A"` | PASS：`q=n96p`（code 不敏感）与 `q=集群A`（name 模糊）均命中 `object_type=cluster`，嵌入 `cluster{id,code,name,status}`，`id` 可跳转 §19。FAIL：code 大小写敏感、无稳定 id |
| A7 输入 Service 名命中其承载 Resource | **V7** | 后端集成 | Service `name="Prometheus"` 属某 Resource | PASS：`q=prometheus`（不敏感）命中 `object_type=service`，嵌入 `service{id,name,status}` 与承载 `resource`。FAIL：无 resource、大小写敏感 |
| A8 搜索默认不含软删；ADMIN 可显式 `deleted=include/only` | **V8**；**V-DB-1** | 后端集成 + 真实 PG | 软删/未软 R、Cluster、Service、IP 各若干 | PASS：默认结果不含软删对象；ADMIN `include` 同时含未删+已删、`only` 仅已删；非 ADMIN `include/only`→403。FAIL：软删泄漏、权限未拦 |
| A9 空/纯空白查询按 CONTRACT 处理（PROPOSED 422 field="q"），不返回全量/不 500 | **V9** | 后端集成 | 任意可命中数据 | PASS：`q=""`、`q="   "`、缺 `q`→422 `VALIDATION_ERROR{fields:[{field:"q"}]}`；非整数/超长（>255）→422 field="q"；无 200 全量、无 500。FAIL：返回全量、500 |
| A10 每条结果暴露稳定 ID 与 object_type，跳转目标正确（Resource→§18，Cluster→§19） | **V10** | 后端集成 + 前端 | 上述各对象 | PASS：每 item 含非空 UUID `id` 与 `object_type`；同名对象改名后 `id` 不变；前端跳 Resource/Cluster Detail 用 `id` 而非字符串键。FAIL：缺字段、按名称跳转 |
| A11 搜索结果分页/排序（缺省 page=1/page_size=20，1..100，越界 422） | **V11** | 后端集成 | 可产生 >20 条结果的查询 | PASS：缺省 `{page:1,page_size:20}`；`page_size=1`(下界)/`100`(上界) 接受；`page=0`、`page_size=0/101`、非整数→422 field；`total` 与匹配总数一致。FAIL：越界被接受、分页错位 |
| A12 模糊搜索由 pg_trgm 支撑，索引方案经 Database 签核（GIN 建议） | **V12**；**V-DB-2/V-DB-8** | 约束/索引 + 真实 PG | 迁移 0013 已 upgrade head | PASS：`pg_extension` 含 `pg_trgm`；`pg_indexes` 含签核后的 GIN `gin_trgm_ops` 索引（候选 `ix_resources_hostname_trgm`/`ix_clusters_code_key_trgm`/`ix_clusters_name_trgm`/`ix_services_name_key_trgm`，以 DATABASE 定稿为准）；`EXPLAIN` 相关模糊查询命中 GIN。FAIL：无 GIN、未签核即视为不作数 |
| A13 Dashboard 展示 Cluster/Resource/BareMetal/VM/Network 数量，未软删（含 INACTIVE） | **V13**；**V-DB-3** | 后端集成 + 真实 PG | 含 INACTIVE Cluster/Network、软删各对象、BARE_METAL + VM 混合 | PASS：`counts` 五值分别等于 `deleted=exclude` 各列表 `total`（无其它过滤）；`clusters`/`networks` 含 INACTIVE；软删不计；`resources = bare_metal + virtual_machines`（仅两类型）。FAIL：停用被排除、软删计入 |
| A14 Dashboard per-Network 展示可分配总量/已占用/剩余 | **V14** | 后端集成 + 真实 PG | 多 Network（含 gateway/RESERVED/禁用/池外手动 IP） | PASS：`networks.items[].capacity` 三值存在且为整数；口径见 V16/V17/V20。FAIL：缺字段、以 CIDR 大小替代池容量 |
| A15 Dashboard per-AUTO 池展示可分配总量/剩余（`|池范围 ∩ 可分配集合|`） | **V15** | 后端集成 + 真实 PG | Network 含 0..N 个 AUTO 池 | PASS：每个未删 AUTO 池一项 `{ip_pool,allocatable_total,occupied,remaining}`；`allocatable_total` = 交集大小；无 AUTO 池时 `auto_pools=[]`。FAIL：含软删池、口径错 |
| A16 容量排除 gateway/RESERVED/禁用，且集合去重（gateway 在 RESERVED 时不重复扣减） | **V16**；**V-DB-4** | 后端集成 + 真实 PG | 构造 gateway 落在 RESERVED 池范围内、含禁用地址段 | PASS：与 `network_allocatable_intervals` 一致；gateway∩RESERVED 只扣一次；禁用地址被排除。FAIL：重复扣减、禁用未排除 |
| A17 占用=未删 IP（含未绑定、含池外手动）；软删 IP 不计；`remaining` 可为负不截断 | **V17**；**V-DB-5** | 后端集成 + 真实 PG | 未绑定 IP、池外手动 IP、软删 IP、使占用>总量的存量 IP | PASS：`occupied` 含未绑定与池外手动、不含软删；`remaining=allocatable_total−occupied`，占用超量时返回负值原样。FAIL：软删计入、负值被 clamp 为 0 |
| A18 AUTO 池占用按当前地址所在范围（非历史来源）；Network 口径含池外手动 | **V18** | 后端集成 + 真实 PG | 一个 IP 原属 AUTO 池经迁移/手动落于池范围外、以及池内地址 | PASS：AUTO `occupied` 仅统计当前地址落在池∩可分配集合的未删 IP；Network `occupied` 含池外手动、不受 `ip_pool_id` 来源影响。FAIL：按来源统计、漏池外 |
| A19 容量与 ACTIVE/INACTIVE、auto_allocate 许可分别展示；Network 停用不清零 | **V19** | 后端集成 + 真实 PG | INACTIVE Network、`auto_allocate=false` Network | PASS：`network.status`/`auto_allocate` 与容量三值分别字段呈现；INACTIVE 不使 capacity 归零；`auto_allocate=false` 不影响容量。FAIL：停用清零、字段耦合 |
| A20 IP 使用情况与 F010 `/api/v1/networks/{id}/capacity` 逐项一致 | **V20** | 后端集成 + 真实 PG | 同一批 Network/IP 数据 | PASS：对每个未删 Network，Dashboard `capacity`/`auto_pools` 与 `GET /api/v1/networks/{id}/capacity` 的 `network_capacity`/`auto_pools` **数值逐项相等**（`allocatable_total`/`occupied`/`remaining`）。FAIL：任一数值不一致、字段名不符 |
| A21 搜索/Dashboard 只读：无写入口、不写 Audit、无副作用 | **V21**；**V33** | 后端集成 + 静态 | 已有 `audit_logs` | PASS：路由无 POST/PATCH/DELETE/restore；调用前后 `audit_logs` 行数不变、无业务列变更；重复调用幂等。FAIL：存在写路由、产生 audit |
| A22 权限：三基础角色均可读；未认证 401；查看已删/恢复限 ADMIN | **V22** | 后端集成 + 前端 | VIEWER/EDITOR/ADMIN 用户 | PASS：三角色 GET `/search`、`/dashboard`→200；未认证→401；`deleted=include/only` 非 ADMIN→403 `FORBIDDEN{reason:"permission"}`；无写按钮/入口（前端），服务端 `require_permission` 强制（静态）。FAIL：越权成功、仅前端隐藏 |
| A23 已软删 Network 不计入计数/容量；软删 IP/对象不计入搜索/计数 | **V23** | 后端集成 + 真实 PG | 软删 Network、软删 IP/Resource/Cluster/Service | PASS：软删 Network 不在 `counts.networks` 也不在 `networks.items`；软删 IP 不计 occupied；软删对象默认不出现在搜索。FAIL：软删泄漏 |
| A24 SN/MAC/Role/GPU Model 搜索不作为本期验收项 | **V24** | 静态 | — | PASS：`matched_field` 枚举仅 `hostname/address/code/name`；无 SN/MAC/Role/GPU Model 匹配路径或 `type` 值。FAIL：意外引入承诺外字段（记 NOTE，不判 FAIL 功能缺陷） |

补充验证项（非直接 A 映射）：

| 验证项 | 内容 | 测试类型 | 判据 |
| --- | --- | --- | --- |
| **V25** 响应契约 | SearchItem 信封与 Dashboard 结构 | 后端集成 | PASS：SearchItem 含 `object_type/id/matched_field/matched_value` + `resource/cluster/ip_address/service`（按类型填充、其余 null）；字段集不因查询变化；Dashboard 含 `counts`（5 键）与 `networks{items,page,page_size,total}`；`network` 含 `id/name/cidr/status/auto_allocate/cluster`。FAIL：字段缺失/类型错/按类型裁剪字段 |
| **V26** 校验顺序 | 401→403→参数 422→查询→200 | 后端集成 | PASS：未认证 401 先于权限；`deleted=include` 且未认证→401、认证非 ADMIN→403；非法 `type`/`page`/`q`→422；无参数合法时 200。FAIL：顺序颠倒、403 先于 401 |
| **V27** 去重 | 同 Resource 经 hostname 与 Service、绑定 IP 多路径 | 后端集成 | PASS：去重键 `(object_type,id)` 唯一；不合成额外 `resource` 行（service/ip_address 行各自嵌入 resource）；hostname 直接命中才产生独立 resource 行；不同 Cluster 同名/同值地址不去重。FAIL：重复行、跨 Cluster 误去重 |
| **V28** 排序全序与稳定分页 | 相似度 → object_type 序 → id | 后端集成 | PASS：`similarity DESC`→`resource<cluster<ip_address<service`→`id ASC`；同分不丢/不重；翻页拼接后与一次性大页集合一致、无重复无遗漏。FAIL：排序不稳定、翻页重复/丢失 |
| **V29** Cluster 不展开（I-12） | `q` 命中 Cluster | 后端集成 | PASS：仅返回 `cluster` 行、不附带其下 Resources（无 resource 行由 cluster 命中产生）；导航交 §19。FAIL：自动展开、结果集爆炸 |
| **V30** IP 前缀/trigram 兜底（PROPOSED） | 非合法整址输入（如 `10.10.1`） | 后端集成 | PASS（若 CONTRACT 采纳）：精确优先，前缀/trigram 兜底返回匹配 IP；若 CONTRACT 裁定仅精确，则非整址→空结果 200。判据以 CONTRACT 定稿为准（OPEN-4）。FAIL：未定义行为/500 |
| **V31** 无跨 Network 全局合计（I-16） | Dashboard 响应 | 后端集成 | PASS：响应无全局合计字段；`networks.items` 受分页、`counts` 与每行 capacity 不受分页影响。FAIL：新增未定义全局合计、counts 随分页变化 |
| **V32** 迁移 0013 | Alembic up/down/up、单 head、无回填 | 真实 PG | PASS：`alembic heads` 单一 `0013_search_indexes`（`down_revision=0012_service_endpoints`）；up 仅加 GIN 索引、无表结构变更；down 仅 DROP 索引且 0012 对象保留；re-up 一致；`pg_trgm`/`btree_gist` 不被 drop、不重复 `CREATE EXTENSION`；无回填。FAIL：多 head、drop 扩展、表结构变更 |
| **V33** 前端搜索/Dashboard 状态与集成 | Loading/Success/Empty/Error(Unknown) | 前端 + 真实 API | PASS：搜索框空输入不发请求；结果按 `object_type` 标签、模糊高亮基于 `matched_field`、跳转正确；Dashboard 卡片区（5 计数 + per-Network 容量表 + AUTO 池 + status/auto_allocate 标识）；`remaining` 负值原样呈现；未知 `object_type`/错误码不伪装为空列表。FAIL：空输入发请求、错误显示为空、负值被美化 |

**索引/迁移机制级验证项（V-DB，真实 PG）**：

| 编号 | 内容 | 映射 |
| --- | --- | --- |
| **V-DB-1** | 软删过滤：默认排除、`include/only` 含已删；软删后搜索/计数消失、恢复后重现 | A8/A23/V8/V23/B14/B18/B24 |
| **V-DB-2** | GIN `gin_trgm_ops` 索引存在（候选集合以 DATABASE 定稿为准）；`pg_trgm` 扩展存在；`EXPLAIN` 模糊查询命中 GIN（非 seq scan，数据量足够时） | A12/V12/B25 |
| **V-DB-3** | 计数口径：`counts` 与各域列表 `deleted=exclude` 的 `total` 等价；含 INACTIVE；`resources = bare_metal + virtual_machines` | A13/V13/B15 |
| **V-DB-4** | 容量排除与去重：gateway、RESERVED 池（未删）、禁用地址被排除；gateway∩RESERVED 只扣一次；与 `base_usable_intervals`/`subtract_intervals` 一致 | A16/V16/B18 |
| **V-DB-5** | `remaining` 负值：占用 > 总量时按公式返回负值，不 clamp | A17/V17/B20 |
| **V-DB-6** | 软删 Network/IP 隔离：软删 Network 不代表 capacity；软删 IP 不计 occupied | A23/V23/B24/B19 |
| **V-DB-7** | Dashboard 与 F010 端点逐项一致（同数据、同会话/同库） | A20/V20/B22 |
| **V-DB-8** | 迁移 0013 up/down/up、单 head、无回填、扩展不重复启用/不 drop；既有 0012 对象保留 | A12/V32/B26 |

---

## 2. 边界与并发场景（B 编号，TEST 阶段执行）

| 编号 | 场景 | 步骤 | 判据 |
| --- | --- | --- | --- |
| B1 | `q` 缺失/空/纯空白 | 省略 `q`；`q=""`；`q="   "`；`q="\t\n"` | 均 422 `VALIDATION_ERROR{field:"q"}`；无 200 全量、无 500；不返回全量 |
| B2 | `q` 归一化 | `q=CN001`/`q=cn001`/`q=" cn001 "`；中文/内部空格 | 大小写与首尾空白等价命中；中文与内部普通空格保留（不合并） |
| B3 | `q` 超长 | `q` 长度 255（接受）、256（422）；Unicode code point 计数 | 255→正常；256→422 field="q" |
| B4 | `type` 非法 | `type=foo`、`type=RESOURCE`（大小写）、重复/空 | 均 422 field="type"；合法四值收窄结果正确 |
| B5 | `deleted` 非法 | `deleted=all`、`deleted=true` | 422 field="deleted"；`exclude/only` 因无 `include` 视场景判定 |
| B6 | 分页参数非法/边界 | `page=0`/`-1`/`1.5`/`x`；`page_size=0`/`101`/`1.5`/`x`；`page_size=1`/`100` | 非法/越界→422 field；1 与 100→接受 |
| B7 | 空结果 | 无命中的 `q` | 200 `{items:[],page,page_size,total:0}`；不 404/500 |
| B8 | 去重 | 同 Resource 同时被 hostname、其 Service、其绑定 IP 命中；两 Cluster 同名 Resource/同值 IP | 按 `(object_type,id)` 去重；不合成额外 resource 行；跨 Cluster 不去重 |
| B9 | 排序全序/稳定分页 | 构造相似度同分多对象；`page_size=1` 翻多页 | 按 `similarity→object_type→id`；翻页无重复无遗漏 |
| B10 | Cluster 不展开 | `q=cluster-code` | 仅 cluster 行，无其下 Resources |
| B11 | 未绑定 IP | `q=<未绑定 IP 地址>` | `object_type=ip_address`、`resource=null` |
| B12 | IP 前缀/兜底 | `q=10.10.1`（非整址） | 依 CONTRACT：前缀/trigram 兜底命中或空结果（OPEN-4） |
| B13 | 权限顺序 401/403 | 未认证请求；认证非 ADMIN `deleted=include/only` | 未认证 401（先于一切）；非 ADMIN→403 `FORBIDDEN{reason:"permission"}` |
| B14 | 只读无副作用/幂等 | 重复 GET 搜索/Dashboard；比对 `audit_logs` 行数与业务表 | 无新 audit 行、无业务写；两次结果一致 |
| B15 | Dashboard 计数口径 | 含 INACTIVE Cluster/Network、软删各对象、BARE_METAL+VM | `counts` 与各域列表 default `total` 等价；含 INACTIVE、不含软删 |
| B16 | per-Network 容量 | gateway/RESERVED/禁用/池外手动 IP | 三值正确；不以 CIDR 大小替代 |
| B17 | AUTO 池容量 | 0..N 个 AUTO 池，含软删 AUTO 池 | 每未删池一项；软删池排除；`allocatable_total`=池∩可分配集合 |
| B18 | 排除与去重 | gateway 落在 RESERVED 池内；禁用地址段 | 只扣一次；禁用被排除 |
| B19 | 占用含未绑定/池外手动、软删不计 | 未绑定 IP、池外手动 IP、软删 IP | occupied 含前两者、不含软删 |
| B20 | 负值不截断 | 存量 IP 落入新增 RESERVED/gateway/禁用范围使占用>总量 | `remaining` 为负原样返回；不 clamp、不隐藏 |
| B21 | INACTIVE 不清零/许可分列 | INACTIVE Network、`auto_allocate=false` | capacity 非零；`status`/`auto_allocate` 与容量分列 |
| B22 | 与 F010 `/capacity` 一致 | 同一批 Network 分别取两接口 | `capacity`/`auto_pools` 数值逐项相等 |
| B23 | 无全局合计/分页关系 | Dashboard `networks.items` 分页 | 无合计字段；`counts` 与每行 capacity 不随分页变化 |
| B24 | 软删 Network | 软删 Network（先清空其 IP/池或先软删） | `counts.networks` 不含；`networks.items` 不含；其 IP 不参与占用 |
| B25 | GIN 命中（真 PG EXPLAIN） | 迁移 0013 后，对资源/集群/服务表做 `EXPLAIN (ANALYZE, BUFFERS)` 模糊查询 | 计划命中对应 `gin_trgm_ops` 索引（数据量足够时）；签核索引缺失→OPEN/BLOCKED |
| B26 | 迁移 0013 往返 | `upgrade head`→`downgrade 0012_service_endpoints`→`upgrade head` | 各步 0；单一 head；down 后仅 GIN 索引消失、0012 对象保留；re-up 一致；扩展不变 |
| B27 | 前端搜索状态 | 首页搜索：空输入、命中、无命中、后端 422/500 | 空输入不发请求；Loading/Success/Empty/Error 正确；错误不伪装为空列表 |
| B28 | 前端 Dashboard 状态 | 计数、per-Network 表、AUTO 池、负值 | 正确渲染；负值原样；状态/许可分列；Error 状态明确 |
| B29 | 各域列表 `q` 回归（I-17） | F003/F004/F008/F009/F010/F011/F012 各列表 `q` 过滤 | 行为与 F013 前**完全一致**（保持 ILIKE 子串）；不被 F013 追溯修改 |
| B30 | 未知值处理（前端/契约） | 未知 `object_type`、未知 error code、`matched_field` 越界值 | 前端不崩溃、按通用呈现；不静默当成功 |

并发说明：F013 为只读，**不涉及写并发/约束竞争**；相关并发（IP 分配、乐观锁、部分唯一）归已 DONE 的 F008–F012。F013 唯一需真库机制级的是 **GIN 索引与 EXPLAIN（B25/V-DB-2）** 与 **迁移往返（B26/V-DB-8）**，均须真实 PostgreSQL（SQLite/Mock 不作证据）。

---

## 3. 夹具 / 环境设计

**复用 F001–F012 `backend/tests/conftest.py`（不改其护栏语义）**：
- `test_database_url`：独立测试库 + 安全护栏（库名含 `test`、`TEST_DATABASE_URL != DATABASE_URL`）；未设置则 skip 并告警，不静默改 SQLite。
- `pg_engine`：会话级 `DROP SCHEMA public CASCADE` + `CREATE SCHEMA public` + `alembic upgrade head`（含 0013）；会话结束清理。F013 GIN/EXPLAIN 证据必须经此真实 PG。
- `db_session`：函数级外层事务 + savepoint，回滚不跨用例污染（只读用例足够）。
- `committed_engine`：真实提交用例（Dashboard 数据准备、EXPLAIN、目录/索引断言），teardown `TRUNCATE`；新开连接断言最终数据。
- `alembic_runner`：迁移 up/down/up（V32/B26）。
- 认证/权限 fixture（`auth_app`/`api_client`/`bootstrap_admin`/`make_user`/`role_client_factory`）：权限与只读证据使用**真实业务端点** `/api/v1/search`、`/api/v1/dashboard`。
- F003/F004/F008/F009/F010/F011/F012 helper（`_create_cluster`/`_network`/`_pool`/`_resource`/`_interface`/`_ip`/`_service`/`_endpoint`、raw `insert_*`、软删）直接复用。

**F013 新增测试侧夹具/断言（Tester 落地于测试侧）**：
- `search_scenario_factory`：一次构建跨 Cluster 的 Cluster/Resource（含 `gpu0701/0702/0725`、`CN001`）/Interface（绑定 IP）/未绑定 IP/Service，返回组合；覆盖 A1–A7、B8、B10、B11。
- `dashboard_scenario_factory`：构建含 gateway、RESERVED 池、AUTO 池、禁用地址、池外手动 IP、未绑定 IP、软删 IP、INACTIVE Network 的 Network 组合；覆盖 A13–A20、B15–B21。
- `assert_search_envelope(item, object_type, expected)`：断言 SearchItem 字段集、按类型填充、其余 null（V25）。
- `assert_search_order(items)`：断言 `similarity→object_type→id` 全序（V28/B9）。
- `assert_capacity_matches_f010(role_client, network_id, dash_row)`：逐项比对 Dashboard 行与 `GET /api/v1/networks/{id}/capacity`（V20/B22）。
- `assert_gin_index(engine, table, index_name)`、`assert_trgm_explain(engine, sql, params)`：目录断言 + `EXPLAIN` 命中（V-DB-2/B25）。
- 各域 `q` 回归：直接复用 F003/F004/F008/F009/F010/F011/F012 的列表 `q` 用例（B29）。

**环境**：Docker / Compose 可用（F001–F012 TE 已证）；真实 PG 经 Compose `db`（`postgres:16`）。`pg_trgm` 由 0001、`btree_gist` 由 0008 已启用；0013 不重复启用扩展。

### 3.1 当前环境可执行性评估

| 验证项 | 环境要求 | 当前评估 | 降级/替代 |
| --- | --- | --- | --- |
| V1–V11、V13–V31、V33、B1–B24、B27–B30 | 真实 PG + 后端集成（+ 前端构建） | 经 Compose `db` 可满足（F001–F012 已证）；**依赖 `/api/v1/search`、`/api/v1/dashboard` 实现落地** | 实现未落地→BLOCKED；**不得**用 SQLite 替代约束/EXPLAIN 证据 |
| V12/V-DB-2/B25、V32/B26（GIN + 迁移 0013） | Alembic + 真实 PG | 环境可执行；**依赖 `docs/database/f013-search-index.md` 与迁移 0013 定稿** | DATABASE 未定稿→相关断言 BLOCKED/OPEN（不降验收） |
| A14–A20/V14–V20/V-DB-4…7（容量） | `ip_capacity.py`（已 DONE）+ 真实 PG | 可执行 | 无 PG→BLOCKED |
| B29 各域 `q` 回归 | 各域端点（已 DONE）+ 真实 PG | 可执行 | 无 PG→BLOCKED |
| B27/B28 前端机制级/真实 API 集成 | Node 22 + 构建；Compose 入口 | 可执行 | 真实浏览器 DOM 渲染非必要判据；镜像/端口问题记 BLOCKED |
| §31/§32 完整跨功能回归 | F016 交付 | **不可执行** | 标 `NOT TESTED / 归 F016` |

---

## 4. 可验证性检查

| 项 | 判定 | 说明 |
| --- | --- | --- |
| A1–A7 四类命中/归一化 | **可验证（API + DB）** | V1–V7 + B2/B8/B10/B11；真实端点 + 归一化键 |
| A8 软删可见性 | **可验证（API + DB）** | V8 + V-DB-1 + B13/B14/B24；`deleted` 三值 + VIEW_DELETED |
| A9 空 q | **可验证（API）** | V9 + B1/B3；422 field="q" |
| A10/A11 稳定 ID/分页排序 | **可验证（API）** | V10/V11/V28 + B6/B9/B12 |
| A12 pg_trgm/GIN | **可验证（索引 + 真库 EXPLAIN）** | V12 + V-DB-2 + B25；**须 DATABASE 签核，否则 OPEN** |
| A13/A23 计数口径 | **可验证（API + DB）** | V13/V23 + V-DB-3/V-DB-6 + B15/B24 |
| A14–A20 容量 | **可验证（API + DB）** | V14–V20 + V-DB-4…7 + B16–B22；逐项比对 F010 |
| A21 只读 | **可验证（API + 静态）** | V21 + B14；audit 行数 + 路由清单 |
| A22 权限 | **可验证（API + 前端 + 静态）** | V22 + B13 |
| A24 排除项 | **可验证（静态）** | V24；枚举/字段核对 |
| V25/V26 契约/顺序 | **可验证（API）** | 依赖 Contract 定稿（OPEN-1/OPEN-3） |
| V27 去重 | **可验证（API）** | 依赖 I-11 定稿（OPEN-2） |
| V29/V30/V31 展开/兜底/合计 | **可验证（API）** | 依赖 I-12/I-16 定稿（OPEN-2/OPEN-5） |
| V32/V-DB-8 迁移 0013 | **可验证（DB）** | 依赖迁移定稿；未定稿→BLOCKED |
| V33 前端状态/集成 | **可验证（前端 + 真实 API）** | 构建 + `smoke:client` 机制级 |

口径明确记录：**A12 的「索引方案经 Database 签核」在签核前不得判 PASS**；**A14–A20 只验证透传/一致/展示规则，不重验 F010 公式实现**；**§31 T32/T33 的 F013 部分在本 Feature 闭合，完整 §31/§32 归 F016**。

---

## 5. 范围与不适用项声明

- **各域实体/列表/详情（F003/F004/F005/F006/F008/F009/F010/F011/F012）**：F013 不实现；仅消费其数据与其 `q` 行为（B29 回归）。
- **容量公式实现（F010 `ip_capacity.py`）**：F013 不重验公式本身；只验证透传 F010 口径 + 展示规则（A20 逐项一致）。
- **§18 Resource Detail / §19 Cluster Detail 正文**：F013 仅作跳转目标；字段/区域归对应 Feature。
- **§24 导入（F014）、完整 Audit 查询页（F015）、§31/§32 整体集成验收（F016）**：不在本 Feature。
- **明确排除项**：不是监控面板（无 CPU/内存/流量/可达性/健康）；SN/MAC/Role/GPU Model 搜索不强制；不做 IPv6/全文检索/自然语言/跨 Cluster IP 合并；不用 ElasticSearch，模糊用 pg_trgm；不引入 Redis/Celery。
- **写/恢复/删除**：搜索与 Dashboard 无任何写入口（A21/A22）。
- **真实浏览器 DOM 渲染**：非 F013 必要判据，前端以构建 + `smoke:client` 机制级为准。
- **完整 §31/§32 回归**：F013 仅承载搜索与 Dashboard 入口；**不声明整体通过**。

---

## 6. pg_trgm / GIN 与 DR-189（既有 no-GIN 断言更新范围）

### 6.1 GIN 验证设计（V12/V-DB-2/B25）

- **扩展**：`pg_trgm` 已由 `0001_baseline` 启用（`EXTENSIONS = [("pg_trgm","public")]`）；F013 只新增迁移 `0013_search_indexes`（仅 GIN 索引、无表结构变更），不重复 `CREATE EXTENSION`、不 drop。
- **候选索引集合**（architecture §6，**待 Database 在 DATABASE Gate 签核**）：
  - `ix_resources_hostname_trgm` — `resources (hostname gin_trgm_ops)`（列已存 ASCII 小写归一化值）
  - `ix_clusters_code_key_trgm` — `clusters (code_key gin_trgm_ops)`
  - `ix_clusters_name_trgm` — `clusters (name gin_trgm_ops)`
  - `ix_services_name_key_trgm` — `services (name_key gin_trgm_ops)`
  - （候选）`ix_ip_addresses_host_trgm` 或 `host(address)` 表达式索引 — IP 前缀/模糊兜底，是否建由 Database 评估
- **EXPLAIN 判据**：`EXPLAIN (ANALYZE, BUFFERS)` 对归一化模糊查询（如 `hostname % 'gpu07'` 或 `hostname ILIKE '%gpu07%'`，算子以定稿为准）在数据量足够时命中对应 GIN 索引；小表 seq scan 可接受，但须证明索引**可被使用**（可临时 `SET enable_seqscan = off` 或构造足量行）。仅断言「索引存在」不足以证明 A12，须给 EXPLAIN 计划证据。
- **OPEN 条件**：`docs/database/f013-search-index.md` 不存在 → 索引名/opclass/表达式/是否 partial/`host(address)` 取舍均未签核；B25 与 V-DB-2 的精确断言列为 OPEN-6，待定稿后由 TD-2 固定。

### 6.2 DR-189：既有「无 pg_trgm/GIN」断言更新范围

F013 在 `resources`/`clusters`/`services` 引入 GIN 后，以下**既有测试断言失效，须在实现阶段由 Backend/Tester 同步**（表/行号为本工作区基线）：

| 文件:行 | 现有断言 | 必须的变更 | 影响 |
| --- | --- | --- | --- |
| `backend/tests/integration/test_resource_constraints.py:300` `test_no_pg_trgm_gin_on_resources` | `resources` 的 `USING gin` 索引集为空 | 删除/改写：改断言签核后的 `ix_resources_hostname_trgm`（GIN）**存在**；其余资源索引集合 `RESOURCE_INDEX_NAMES`（:38）不含 GIN | 直接失效，必改 |
| `backend/tests/integration/test_service_constraints.py:225`（`test_table_catalogue_columns_constraints_indexes`） | `services` 的 `USING gin` 为空（:225） | 改写：断言签核后的 `ix_services_name_key_trgm`（GIN）存在 | 直接失效，必改 |
| `backend/tests/integration/test_service_constraints.py:233` | `indexdef ILIKE '%(name)%' OR '%(name_key)%'` 的索引集为空（禁 name/name_key 单列 B-tree） | **注意**：trigram 索引 indexdef 含 `(name_key) gin_trgm_ops` 会误命中；须改为「排除 GIN 后的 btree 集为空」或限定 `amname='btree'` | 隐性失效，必改 |
| `backend/tests/integration/test_service_constraints.py:45` `SERVICE_INDEXES` | 固定索引集合，用于 `indexes == SERVICE_INDEXES` | 视定稿是否 partial/追加：若断言为相等集，需加入 `ix_services_name_key_trgm` | 视定稿 |
| `backend/tests/integration/test_cluster_constraints.py:45` `INDEX_NAMES` | `INDEX_NAMES <= indexes`（子集断言，无 no-GIN 断言） | 子集断言不会失败；但应补入 `ix_clusters_code_key_trgm`/`ix_clusters_name_trgm` 以覆盖；`docs/database/f003-cluster.md` DB-D30 errata | 不破坏，建议补 |
| `backend/tests/integration/test_ip_address_constraints.py:43/284`（DB-D124） | `ip_addresses` 无 GIN、无 address 单列 B-tree | **仅当** Database 裁定建 `ix_ip_addresses_host_trgm`/`host(address)` 时才失效；否则保持有效 | 条件性（OPEN-6） |
| `backend/tests/integration/test_migrations.py` | head 相关；`_declared_baseline_extensions()`/`_extensions()` | head 由 0012 变 0013；扩展断言不变（仍只 pg_trgm+btree_gist）；建议新增 0013 往返断言 | 需补迁移覆盖 |

**保持有效、不得改动**（F013 未对这些表加 GIN）：
`test_network_constraints.py:221`（DB-D89）、`test_ip_pool_constraints.py:245`（DB-D106）、`test_interface_constraints.py:226`（DB-D77）、`test_service_endpoint_constraints.py:302`（DB-D152），以及 `test_ip_address_constraints.py`（除非 DATABASE 采纳）。

**DB 文档 errata（交 Database）**：`docs/database/f003-cluster.md` DB-D30、`f004-resource.md` DB-D38/DB-D41、`f008-network.md` DB-D89、`f010-ip-address.md` DB-D124、`f011-service.md` DB-D137 等「不建 pg_trgm/GIN」表述需以 errata 明确 F013 引入点（DR-189）；不改各域业务行为。

---

## 7. OPEN 复核项（TD-1 提出，待 CONTRACT / DATABASE 定稿后由 TD-2 关闭）

> TD-1 `READY` 表示方案可验证，下列假设未经逐项核对；**READY 不代表测试已执行、不批准实现或合并**。`docs/database/f013-search-index.md` 未产出、`docs/api/F013.md` 为草案 v0。

| # | TD-1 待复核假设 | 影响验证项 | Owner |
| --- | --- | --- | --- |
| OPEN-1 | 错误码/信封与校验顺序：`VALIDATION_ERROR{fields:[{field,message}]}`、`AUTH_REQUIRED`、`FORBIDDEN{reason:"permission"}`；401→403→422→200 | V9/V22/V26、B1/B3/B4/B5/B6/B13 | Contract |
| OPEN-2 | I-11 去重/排序定稿：typed 行（DR-174）vs product PROPOSED 折叠为 Resource；排序 `similarity→object_type→id`；相似度不暴露 | V27/V28、B8/B9 | Product/Architect（Contract） |
| OPEN-3 | I-13 空查询与 `q` 长度上限（trim 后 1–255；空白→422 field="q"） | V9、B1/B3 | Product/Architect（Contract） |
| OPEN-4 | IP 非整址前缀/trigram 兜底的精确算子与阈值（Contract §6） | V30、B12 | Architect/Database（Contract） |
| OPEN-5 | I-12 Cluster 不展开（DR-176）、I-16 无全局合计（DR-183）、I-8 不默认按 Cluster 过滤（DR-188） | V29/V31、B10/B23 | Product/Architect（Contract） |
| OPEN-6 | **pg_trgm/GIN 索引集合/opclass/表达式/是否 partial**、`host(address)` 取舍、迁移 `0013_search_indexes` 命名与 `down_revision=0012_service_endpoints`（architecture §6 候选） | V12/V32、V-DB-2/V-DB-8、B25/B26、§6.2 全部 | Database（DATABASE Gate） |
| OPEN-7 | DR-189 既有 no-GIN 断言更新范围与 DB 文档 errata（§6.2） | V12/V-DB-2、B25 | Database / Backend / Tester |
| OPEN-8 | Dashboard 路径 `/api/v1/dashboard` 与 I-14、`networks` 分页字段、`counts` 全局口径（DR-181/DR-182） | V13–V25、B15/B23 | Architect（Contract） |
| OPEN-9 | I-17 各域列表 `q` 不追溯修改（保持 ILIKE），F013 仅新增 `/search` | B29 | Architect（Contract） |
| OPEN-10 | `docs/api/F013.md` 草案 v0 未签核（含上游 F013 Contract 状态一致性）；推进 Gate 前须定稿为 v1 并核对与 architecture/DB 一致 | 全部 | 协调器 / Contract |

TD-1 结论：**`TEST DESIGN READY`** —— A1–A24 已映射到可观察判据（V1–V33、V-DB-1…V-DB-8），边界/并发/环境场景（空/纯空白/超长 `q`、`type`/`deleted`/`page` 非法、分页全序稳定、去重、Cluster 不展开、IP 未绑定、软删 exclude/include/only + VIEW_DELETED、401/403 顺序、Dashboard 计数/容量/排除去重/未绑定计占用/软删不计/负值不截断/与 F010 逐项一致/状态与许可分列、GIN 真库 EXPLAIN、各域列表 `q` 回归、既有 no-GIN 断言更新范围）可执行；夹具与可验证性已与 architecture §4–§6、§10 与 Contract v0 建立对应；真实 PostgreSQL + `committed_engine` + `EXPLAIN` 口径固定。**DATABASE 未定稿、Contract 为草案，§7 OPEN-1–10 未经逐项核对；READY 不等于测试通过，不批准实现或合并。** 定稿后由 TD-2 关闭 §7 并固定执行判据。

---

## 8. 版本记录（续）

| 版本 | 日期 | 变更 |
| --- | --- | --- |
| TD-1 | 2026-10-12 | 初版 Test Design（见 §Test Design）。 |

> **TD-1 Git 记录**：
> ```text
> GIT: git status --short
> GIT: git rev-parse --short HEAD
> GIT: git branch --show-current
> ```

---

## TD-2 Test Design Closure（版本 TD-2）

- **版本**：TD-2
- **日期**：2026-10-13
- **角色**：Tester（TEST_DESIGN 模式，TD-2 关闭）
- **结论**：`TEST DESIGN READY`（TD-2）
- **定稿输入（已核对）**：
  - `docs/api/F013.md` v1（READY，Architect 2026-10-13；§2.3/§2.4/§2.5/§3/§6/§7 裁定）
  - `docs/database/f013-search-index.md` v1（DB-D157–DB-D166；迁移 `0013_search_indexes`）
  - `docs/architecture/d01-conventions.md` v11（**无变更**，Contract §8 声明）
  - `docs/features/F013/implementation.md`（BACKEND/FRONTEND COMPLETE）
  - errata：`docs/database/f003-cluster.md` DB-D30、`f004-resource.md` DB-D41（**非** DB-D38）、`f011-service.md` DB-D137；`f008/f009/f010/f012` 交叉引用；architecture DR-189 已更正 `DB-D38→DB-D41`。
- **状态属性**：TD-2 `READY` 表示 TD-1 §7 OPEN 已逐项关闭、执行判据已固定为 Contract/DB 定稿值；**不填充执行 PASS、不批准实现或合并**。

### TD-2.1 TD-1 §7 OPEN-1–10 关闭

| OPEN | TD-1 待复核假设 | 定稿判据（Contract v1 / DB v1） | 关闭 |
| --- | --- | --- | --- |
| OPEN-1 | 错误信封/校验顺序 | 复用 F002 信封；401 `AUTH_REQUIRED`→403 `FORBIDDEN{reason:"permission"}`→422 `VALIDATION_ERROR{fields:[{field,message}]}`→200；field 用查询参数名 | ✅ 关闭（Contract §1.2/§1.3） |
| OPEN-2 | 去重/排序 | **typed 行**（不折叠为 Resource）；去重键 `(object_type,id)`；排序 `similarity DESC → object_type 固定序 resource<cluster<ip_address<service → id ASC`；相似度不暴露 | ✅ 关闭（Contract §2.3；DR-174/175） |
| OPEN-3 | 空查询/长度 | `q` trim 后 1–255（Unicode code point）；空/纯空白→422 field=`"q"`；>255→422 field=`"q"` | ✅ 关闭（Contract §2.5；DR-177） |
| OPEN-4 | IP 非整址兜底 | **不采纳**前缀/trigram 兜底，仅精确匹配；非整址/带掩码/IPv6 不产生 `ip_address` 结果且不报错 | ✅ 关闭（Contract §2.4/§7/§8.5；DB-D163） |
| OPEN-5 | I-12 不展开 / I-16 无全局合计 | Cluster 命中仅 `cluster` 行；Dashboard 无跨 Network 合计；`counts` 全局不受分页影响 | ✅ 关闭（Contract §2.7/§3.4/§7） |
| OPEN-6 | GIN 索引集合/opclass/partial/迁移 | 4 条**非 partial、非唯一** `gin_trgm_ops` GIN：`ix_resources_hostname_trgm`(hostname)、`ix_clusters_code_key_trgm`(code_key)、`ix_clusters_name_trgm`(name)、`ix_services_name_key_trgm`(name_key)；`ip_addresses` 不建索引；迁移 `0013_search_indexes`(`down_revision=0012_service_endpoints`) | ✅ 关闭（DB v1 §2–§6；DB-D157–163） |
| OPEN-7 | DR-189 no-GIN 断言/errata | 修订 DB-D30/DB-D41/DB-D137；澄清 DB-D89/DB-D124/DB-D77/DB-D106/DB-D152；更正 DB-D38→DB-D41；受影响断言同步（§7-E4） | ✅ 关闭（DB v1 §7） |
| OPEN-8 | Dashboard 路径/字段 | `GET /api/v1/dashboard`；无 `deleted`/`cluster_id` 参数；`networks.items` 行序 `created_at DESC, id ASC`；`counts` 5 键 | ✅ 关闭（Contract §3；DR-181–183/188） |
| OPEN-9 | I-17 列表 `q` | F013 仅新增 `/search`；各 DONE 域列表 `q` 保持 ILIKE 子串，不追溯修改 | ✅ 关闭（Contract §1.4；DR-185） |
| OPEN-10 | Contract 草案未签核 | `docs/api/F013.md` v1 READY（2026-10-13），与 architecture/DB 一致 | ✅ 关闭 |

### TD-2.2 并入的执行判据（相对 TD-1 §6 候选的固定化）

- **去重/排序**：TD-1 V27/V28 的排序候选固定为 `similarity DESC → object_type(resource,cluster,ip_address,service) → id ASC` 全序；typed 行方案确定，**不**折叠为单一 Resource；相似度值不进入响应。
- **空 `q`**：TD-1 V9/B1 的 PROPOSED 422 固定为定稿：field=`"q"`，长度 1–255。
- **IP**：TD-1 V30/B12 的 OPEN-4 固定为**仅精确匹配**；非整址无 `ip_address` 结果（空结果 200）。
- **Dashboard**：TD-1 V31 固定路径 `/api/v1/dashboard`，无 `deleted`/`cluster_id` 参数，`networks` 行序 `created_at DESC, id ASC`；容量只消费 `ip_capacity.py`。
- **GIN/迁移**：TD-1 §6.1 候选索引集合固定为 DB v1 的 4 条（无 IP 索引）；pg_trgm 引入点 F013，扩展由 0001 启用、0013 不含扩展 DDL。
- **I-17**：各域列表 `q` 行为不变的回归判据（B29）固定。

### TD-2.3 版本记录

| 版本 | 日期 | 变更 |
| --- | --- | --- |
| TD-2 | 2026-10-13 | 关闭 TD-1 §7 OPEN-1–10；按 Contract v1 / DB v1 / D01 v11 固定去重排序、空 q、IP 精确、Dashboard 路径与行序、GIN 集合、I-17 判据；确认 errata（DB-D30/41/137，DB-D38→DB-D41）。 |

> **TD-2 Git 记录**：`GIT: NONE`（TD-2 为文档定稿复核，无 Git 命令）。

TD-2 结论：**`TEST DESIGN READY`** —— 执行判据已全部固定为已签核 Contract/DB 值，可进入 TEST。

---

## TE-1 独立测试执行（版本 TE-1）

- **版本**：TE-1
- **日期**：2026-10-13
- **角色**：Tester（TEST 模式）
- **执行基线**：分支 `feature/F013-global-search-dashboard`，`HEAD=0c1d80d`（工作区除本 Tester 新增测试文件外 clean）。
- **结论**：**`READY FOR REVIEW`** —— A1–A24、V-DB-139–144、B1–B30 全部适用项 PASS，无必须修复缺陷。
- **独立性声明**：本次未复制开发者执行结果。全部测试由 Tester 在本机独立运行；迁移/索引/EXPLAIN 在**独立验证库**（`f013_verify_test`，与开发者/常规测试库 `csm_test` 分离）重建并逐条核对；TD-2 已先复核 Contract/DB 定稿与 errata。开发者实现的测试属 Review 对象，Tester 另行以 probe 覆盖其未覆盖的验收项（A16 gateway∩RESERVED 去重、A17 软删 IP 不计占用、B17 软删池、V28 id 全序、V26 401 先于 422、V25/V31 响应形状、B12 非整址/IPv6）。

### 环境

| 项 | 值 |
| --- | --- |
| PostgreSQL | 容器 `f002test-db`（`postgres:16`），网络 `f002test-net`，用户 `csm` |
| 常规测试库 | `csm_test`（库名含 `test`，DB-D10 护栏通过） |
| 独立验证库 | `f013_verify_test`（Tester 新建，用毕 DROP） |
| 后端镜像 | `csm-f007-test`（未 `docker build`） |
| 后端依赖 | 真实 PG + ASGI 应用（`TestClient`），非 SQLite/Mock |
| 前端 | 本机 Node 22；`npm run typecheck` / `build` / `smoke:client` |
| 未执行 | Compose/Nginx 入口（无运行入口且不允许 `docker build`）；真实浏览器 DOM 渲染 |

### 命令与输出

```text
# 1) F013 专属后端测试
$ docker run --rm --network f002test-net -v "$PWD/backend:/app" \
    -e TEST_DATABASE_URL="postgresql+psycopg://csm:change-me@f002test-db:5432/csm_test" \
    -w /app csm-f007-test python -m pytest tests/integration/test_search.py \
    tests/integration/test_dashboard.py tests/integration/test_search_constraints.py -q
=> 35 passed, 1 warning in 21.32s

# 2) 后端全量回归（含开发者 F013 测试）
$ docker run ... -w /app csm-f007-test python -m pytest tests -q
=> 473 passed, 1 skipped, 1 warning in 246.39s
   (skip=tests/integration/test_migrations.py:105 superuser 环境性跳过，与 F013 无关)

# 3) Tester 独立验收补充（新增 test_f013_tester_acceptance.py）
$ docker run ... python -m pytest tests/integration/test_f013_tester_acceptance.py -q
=> 10 passed in 7.32s

# 4) 后端全量回归（含 Tester 补充后）
$ docker run ... python -m pytest tests -q
=> 482 passed, 1 skipped, 1 warning in 247.37s

# 5) 独立验证库：迁移 up（真实 PG）
$ docker run ... -e DATABASE_URL=".../f013_verify_test" python -m alembic upgrade head
=> 0001_baseline .. 0012_service_endpoints -> 0013_search_indexes 全链成功

# 6) 单 head
$ python -m alembic heads        => 0013_search_indexes (head)
$ SELECT version_num FROM alembic_version;  => 0013_search_indexes

# 7) 4 条 GIN 索引目录
$ SELECT indexname,indexdef FROM pg_indexes WHERE ...
ix_resources_hostname_trgm | ... USING gin (hostname gin_trgm_ops)
ix_clusters_code_key_trgm  | ... USING gin (code_key gin_trgm_ops)
ix_clusters_name_trgm      | ... USING gin (name gin_trgm_ops)
ix_services_name_key_trgm  | ... USING gin (name_key gin_trgm_ops)
$ indisunique=f / indisvalid=t / indpred=NULL（4/4 非唯一、非 partial）
$ ip_addresses 上 USING gin 索引数 = 0

# 8) down/up 往返
$ alembic downgrade 0012_service_endpoints  => 4 索引消失，resources/clusters/services/ip_addresses 保留
$ extensions: btree_gist,pg_trgm,plpgsql（前后一致）
$ alembic upgrade head                      => 4 索引恢复，extensions 不变
$ 0013 源码: 无 'CREATE EXTENSION'/'DROP EXTENSION'；down_revision="0012_service_endpoints"

# 9) EXPLAIN (ANALYZE) q>=3 命中 GIN（真实 PG，5 万行/表）
resources.hostname ILIKE '%needlexyz%'   => Bitmap Index Scan on ix_resources_hostname_trgm
clusters.code_key ILIKE '%needlecn%'     => Bitmap Index Scan on ix_clusters_code_key_trgm
clusters.name ILIKE '%needle cluster%'   => Bitmap Index Scan on ix_clusters_name_trgm
services.name_key ILIKE '%needle service%' => Bitmap Index Scan on ix_services_name_key_trgm
# ADMIN only 路径（deleted_at IS NOT NULL）亦可走 GIN（非 partial 的意义）
resources ... AND deleted_at IS NOT NULL => Bitmap Index Scan on ix_resources_hostname_trgm

# 10) 前端
$ cd frontend && npm run typecheck   => 通过
$ npm run build                      => ✓ 79 modules transformed, built in 6.00s
$ npm run smoke:client               => 224 passed, 0 failed（F013 +16）
```

### A1–A24 验收结果

| 验收 | 验证项 | 结果 | 证据 |
| --- | --- | --- | --- |
| A1 统一入口四类 | V1/V33 | **PASS** | `test_search.py` 四类命中用例；`smoke:client` F013 搜索入口/typed 行解析 |
| A2 hostname 模糊 | V2 | **PASS** | `test_hostname_substring_and_normalisation` |
| A3 归一化大小写/空白 | V3 | **PASS** | 同上（GPU0701 / `  gpu0701  `）；`V-DB-142` 归一化等价 |
| A4 IP→Interface→Resource | V4 | **PASS** | `test_ip_exact_match_binds_resource` |
| A5 未绑定 IP resource=null | V5 | **PASS** | `test_ip_unbound_has_null_resource` |
| A6 Cluster code/name | V6 | **PASS** | `test_cluster_code_and_name_matching`；probe `test_probe_cluster_code_wins`（code 优先） |
| A7 Service→Resource | V7 | **PASS** | `test_service_match_embeds_resource` |
| A8 软删 exclude/include/only + 403 | V8/V-DB-1 | **PASS** | `test_soft_delete_exclude_include_only` |
| A9 空 q→422 | V9 | **PASS** | `test_empty_query_is_422`、`test_missing_query_is_422`、`test_overlong_query_is_422` |
| A10 稳定 ID/object_type | V10 | **PASS** | 各用例断言 `id`/`object_type`；`smoke` 跳转目标解析 |
| A11 分页/边界 | V11 | **PASS** | `test_pagination_is_stable_and_total_is_exact`、`test_invalid_parameters_are_422`、probe `test_probe_parameter_bounds` |
| A12 pg_trgm/GIN 签核 | V12/V-DB-2 | **PASS** | §命令 5–9：4 索引 + EXPLAIN 命中四查询 |
| A13 counts 未删含 INACTIVE | V13/V-DB-3 | **PASS** | `test_counts_scope_and_inactive`、`test_counts_match_domain_list_totals` |
| A14 per-Network 容量 | V14 | **PASS** | `test_network_capacity_matches_f010_capacity_endpoint` |
| A15 AUTO 池容量 | V15 | **PASS** | 同上；probe `test_probe_soft_deleted_pools` |
| A16 排除 gateway/RESERVED/禁用 + 去重 | V16/V-DB-4 | **PASS** | probe `test_probe_gateway_inside_reserved_dedup`（244 非 243）、`test_probe_soft_deleted_pools` |
| A17 占用含未绑定/池外、软删不计、负值不截断 | V17/V-DB-5 | **PASS** | `test_network_capacity...`（池外 10.10.0.200 计入）、`test_negative_remaining_not_clamped`、probe `test_probe_soft_deleted_ip_not_occupied` |
| A18 AUTO 占用按当前地址/Network 含池外 | V18 | **PASS** | `test_network_capacity...`；`ip_capacity.auto_pools_capacity` 按当前地址计数（NOTE 见下） |
| A19 状态/许可分列、INACTIVE 不清零 | V19 | **PASS** | `test_counts_scope_and_inactive`（INACTIVE 容量 >0） |
| A20 与 F010 逐项一致 | V20/V-DB-7 | **PASS** | `test_network_capacity_matches_f010_capacity_endpoint`（三项 + auto_pools 逐项相等） |
| A21 只读/无 Audit/幂等 | V21 | **PASS** | `test_search_writes_no_audit`、`test_dashboard_writes_no_audit`；静态路由仅 `GET` |
| A22 权限 401/403/全角色 | V22 | **PASS** | `test_all_roles_can_read_dashboard`、`test_unauthenticated_*`、`test_soft_delete...`(403) |
| A23 软删 Network/IP/对象隔离 | V23/V-DB-6 | **PASS** | `test_soft_deleted_excluded_from_counts_and_networks`、probe 软删 IP/池 |
| A24 SN/MAC/Role/GPU Model 排除 | V24 | **PASS**（静态） | `SearchItem.matched_field` 枚举仅 hostname/address/code/name；`type` 无 SN/MAC 值 |

### V-DB-139–V-DB-144 结果

| 编号 | 内容 | 结果 | 证据 |
| --- | --- | --- | --- |
| V-DB-139 | 迁移 up/down/up、单 head、down_revision | **PASS** | 独立库 §命令 5–8；`test_migration_0013_up_down_up_single_head` |
| V-DB-140 | 4 条 GIN `gin_trgm_ops`，非唯一、非 partial、valid | **PASS** | §命令 7；`test_trgm_indexes_are_non_partial_gin`；`indisunique=f`/`indpred=NULL` |
| V-DB-141 | include/only 覆盖、非 partial 可走 GIN | **PASS** | 独立库 EXPLAIN `deleted_at IS NOT NULL` → GIN 命中 |
| V-DB-142 | EXPLAIN q≥3 命中 GIN（四类） | **PASS** | §命令 9（四条 Bitmap Index Scan） |
| V-DB-143 | 无扩展 DDL、扩展前后一致、单 head | **PASS** | `test_migration_0013_has_no_extension_ddl`；独立库扩展 `btree_gist,pg_trgm,plpgsql` 前后一致 |
| V-DB-144 | 既有 no-GIN/head 断言同步后复跑 | **PASS** | 全量 482 passed（`test_resource_constraints`/`test_service_constraints`/8 个 head 硬编码 → `0013_search_indexes`） |

### V1–V33 补充验证项

V1–V24 已并入上表；V25（响应契约）PASS（probe `test_probe_response_shape_and_ignored_params`）；V26（401→403→422 顺序）PASS（`test_soft_delete...`、probe `test_probe_unauthenticated_precedes_validation`）；V27（去重）PASS（probe `test_probe_typed_rows_no_synthesised_resource`）；V28（全序/稳定分页）PASS（`test_pagination...`、probe `test_probe_equal_similarity_id_asc_stable_paging`）；V29（Cluster 不展开）PASS（`test_cluster_code_and_name_matching`）；V30（IP 兜底）PASS（定稿仅精确；probe `test_probe_ip_non_integer_forms`）；V31（无全局合计）PASS（probe 响应键集合）；V32（迁移 0013）PASS（同 V-DB-139）；V33（前端状态/集成）PASS（`smoke:client` 机制级）。

### B1–B30 边界场景结果

| 编号 | 场景 | 结果 | 证据 |
| --- | --- | --- | --- |
| B1 | q 缺失/空/纯空白 | **PASS** | `test_empty_query_is_422`、`test_missing_query_is_422` |
| B2 | 归一化 | **PASS** | `test_hostname_substring_and_normalisation` |
| B3 | q 255/256 | **PASS** | probe `test_probe_parameter_bounds`（255→200，256→422） |
| B4 | type 非法/大小写 | **PASS** | `test_invalid_parameters_are_422`、probe（`RESOURCE`→422） |
| B5 | deleted 非法 | **PASS** | `test_invalid_parameters_are_422` |
| B6 | 分页非法/边界 | **PASS** | `test_invalid_parameters_are_422`、probe（1/100 接受，0/101/1.5 拒） |
| B7 | 空结果 200 | **PASS** | `test_empty_result_is_200` |
| B8 | 去重 | **PASS** | probe typed 行；probe 同分跨 Cluster 各一条 |
| B9 | 全序/稳定分页 | **PASS** | `test_pagination...`、probe id-ASC 翻页无重复遗漏 |
| B10 | Cluster 不展开 | **PASS** | `test_cluster_code_and_name_matching` |
| B11 | 未绑定 IP | **PASS** | `test_ip_unbound_has_null_resource` |
| B12 | IP 非整址 | **PASS** | probe `test_probe_ip_non_integer_forms`（前缀/掩码/IPv6/非法 均空结果 200） |
| B13 | 401/403 顺序 | **PASS** | `test_soft_delete...`、probe 401 先于 422 |
| B14 | 只读/幂等 | **PASS** | `test_search_writes_no_audit`、`test_dashboard_writes_no_audit` |
| B15 | counts 口径 | **PASS** | `test_counts_scope_and_inactive`、`test_counts_match_domain_list_totals` |
| B16 | per-Network 容量 | **PASS** | `test_network_capacity_matches_f010_capacity_endpoint` |
| B17 | AUTO 池含软删池 | **PASS** | probe `test_probe_soft_deleted_pools`（软删 AUTO 消失、软删 RESERVED 不再排除） |
| B18 | 排除与去重 | **PASS** | probe gateway∩RESERVED 只扣一次 |
| B19 | 占用含未绑定/池外、软删不计 | **PASS** | `test_network_capacity...`、probe 软删 IP |
| B20 | 负值不截断 | **PASS** | `test_negative_remaining_not_clamped`（remaining=-1） |
| B21 | INACTIVE 不清零/许可分列 | **PASS** | `test_counts_scope_and_inactive` |
| B22 | 与 F010 一致 | **PASS** | `test_network_capacity_matches_f010_capacity_endpoint` |
| B23 | 无全局合计/分页关系 | **PASS** | `test_networks_pagination_does_not_affect_counts`、probe 响应键 |
| B24 | 软删 Network | **PASS** | `test_soft_deleted_excluded_from_counts_and_networks` |
| B25 | GIN EXPLAIN（真 PG） | **PASS** | §命令 9 |
| B26 | 迁移 0013 往返 | **PASS** | §命令 8 |
| B27 | 前端搜索状态 | **PASS**（机制级） | `smoke:client` search/空结果/错误描述 |
| B28 | 前端 Dashboard 状态 | **PASS**（机制级） | `smoke:client` dashboard 解析/负值原样/错误描述 |
| B29 | 各域列表 q 回归 | **PASS** | 全量套件中 `test_clusters/test_resources/test_services` 等 q 过滤用例通过 |
| B30 | 未知值处理 | **PASS**（机制级） | `smoke:client` 未知 reason/error code 不伪装为空列表 |

### Defects

无。未发现必须修复的实现缺陷、Contract/DB 偏差或安全/权限问题。

### 未验证项与 NOTE

- **NOTE-1（非阻塞性能，归 F010/后续）**：`ip_capacity.auto_pools_capacity` 的 AUTO `occupied` 按池原始地址范围计数（`_count_ips(pool_lo..pool_hi)`），而 Contract §3.3/§20 表述为「位于池∩可分配集合的未删 IP」。仅当池范围内存在 gateway/RESERVED/禁用地址且该地址上有存量 IP 时两者才可能不一致；而 API 拒绝将 gateway 设为被占用地址、也拒绝在 gateway 上创建 IP，故该差异经 API **不可达**。F013 按 A20 只验证「逐项复用 F010 口径」并已通过；公式本身归 F010，按 TD-1 范围声明不在 F013 重验。
- **NOTE-2（前端集成层级）**：真实浏览器 DOM 渲染与 Compose/Nginx 入口级前后端集成未执行（无运行入口且任务禁止 `docker build`）。按 TD-1 §3.1/§5 与 architecture §8，F013 前端判据为 `typecheck + build + smoke:client` 机制级，故不降验收；后端真实 API（ASGI + 真实 PG）已由集成测试覆盖。
- **NOTE-3（pg_trgm 固有）**：`q` 长度 <3 时 GIN 可能退化为顺序扫描；不影响正确性（Contract §6）。未作强制断言。
- **NOTE-4（DB-D163）**：跨 Cluster 全局 IP 精确查询无专用索引（已识别的非阻塞性能项），未追加迁移。
- **§31/§32 完整跨功能验收**：`NOT TESTED`，归 F016；本报告不声明整体通过。

### TE-1 结论

**`READY FOR REVIEW`**：A1–A24、V-DB-139–144、B1–B30 全部适用项 PASS；无必须修复问题；数据完整性（只读派生、未删过滤、容量口径、归一化、稳定 ID、权限、只读无 Audit）逐项有真实 PG + 真实 API 证据。NOTE-1–4 均为非阻塞说明，不构成缺陷。Tester 新增 `backend/tests/integration/test_f013_tester_acceptance.py`（10 用例，Tester 补充覆盖，属 Review 范围）。

---

## 9. 总版本记录

| 版本 | 日期 | 角色 | 结论 |
| --- | --- | --- | --- |
| TD-1 | 2026-10-12 | Tester (TEST_DESIGN) | `TEST DESIGN READY`（OPEN-1–10 待关闭） |
| TD-2 | 2026-10-13 | Tester (TEST_DESIGN) | `TEST DESIGN READY`（OPEN-1–10 已关闭） |
| TE-1 | 2026-10-13 | Tester (TEST) | `READY FOR REVIEW`（482 passed / 1 skipped；前端 224 passed） |

---

GIT: git rev-parse --short HEAD
GIT: git status --porcelain
GIT: git branch --show-current
GIT: git log --oneline -3
GIT: git status --short
GIT: git diff --stat HEAD
GIT: git mv backend/tests/integration/test_f013_probe_tmp.py backend/tests/integration/test_f013_tester_acceptance.py （该命令在对未跟踪文件执行时失败退出，未改变 Git 状态；随后以文件系统 `mv` 完成重命名）