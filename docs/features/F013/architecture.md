# F013 全局搜索与 Dashboard — ARCHITECTURE 阶段报告

- **Task**：F013（FEATURE，P1，M6 检索、导入与系统功能，deps [F003, F004, F005, F006, F008, F009, F010, F011, F012]）— Architect，Feature 设计模式
- **阶段**：ARCHITECTURE；**结论**：`READY FOR DESIGN`（2026-10-09）
- **Basis**：requirements-v3.md revision 3（§4、§4.1、§5、§7、§11.1、§12、§13、§14、§15、§16、§17、§18、§19、§20、§21、§22、§23、§25、§26、§27、§28、§31 T32/T33、§32、§33、§35.2 Q02-A/Q04-A/Q04-B/Q10-B、§35.3 D01/D02）；docs/features/F013/product.md（A1–A24、I-1–I-10、OPEN I-11–I-18）；docs/architecture/d01-conventions.md v11（§4 省略、§5 归一化、错误码、分页）；docs/api/F003.md v2（列表基线/分页/错误）、docs/api/F010.md v1 §6.9（容量端点）、docs/api/F011.md v1、docs/api/F012.md v1；backend/app/services/ip_capacity.py（F010 容量口径实现）；backend/alembic/versions/0001_baseline.py（pg_trgm 已在基线启用）；docs/product/domain-model.md；.pi/skills/resource-domain/SKILL.md；plan_revision 4 F013

## 1. 方案摘要

F013 在已交付资源域之上新增两个跨域**只读**通用入口，不新增资源实体、字段或业务状态，不写 Audit（§22），不提供任何写端点（§17/§20/§23；I-4）。Dashboard 不是监控面板（§3/§20）。

### 1.1 全局搜索
- 新增 `GET /api/v1/search`（§25 已确认核心路径），挂同一 `api_v1_router`，READ 全角色（§23）。
- 命中对象覆盖四类：hostname→`resource`；IP→`ip_address`（绑定 Interface 时附带所属 `resource`；未绑定为 null）；Cluster→`cluster`；Service→`service`（附带承载 `resource`）。每类结果携带稳定 UUID 与可跳转信息（§4/§17/§33/A10）。
- 模糊匹配用 pg_trgm（§26）；归一化与唯一性口径一致（§4.1/§5/§7，D01 §5）。默认隐藏软删，ADMIN 可用 `deleted=include|only`（§21/§23）。
- 去重/排序（I-11）、Cluster 展开（I-12）、空查询（I-13）在本文档给出设计裁定，状态 PROPOSED→CONTRACT。

### 1.2 Dashboard
- 新增 `GET /api/v1/dashboard`（I-14），READ 全角色（§23）。
- 返回 `counts`（Cluster / Resource / BareMetal / VM / Network 的全局未删计数，含 INACTIVE）与 `networks`（per-Network 容量 + 其 AUTO 池容量），容量口径**只消费** F010 `/api/v1/networks/{id}/capacity` 与 `backend/app/services/ip_capacity.py` 的 `network_capacity` / `auto_pools_capacity`，不自行重算、不截断负值（I-7/§20/T32/DR-130）。
- 不提供跨 Network 全局合计（I-16，不同 Cluster 可含相同地址，相加易误导），不默认按 Cluster 过滤（I-8 保持 OPEN）。

### 1.3 与既有域的边界
各域列表 `q`（F003/F004/F008/F009/F010/F011/F012）继续使用现有 ILIKE，不改语义、不追溯升级（I-17）；F013 仅新增两个只读端点，不重复定义各域列表/详情，不重复定义 §18/§19 内容（product §8）。

## 2. Design Requirements（DR-171–DR-189，接续 F012 DR-170）

| ID | 决策 | 状态 |
| --- | --- | --- |
| DR-171 | 新增独立只读端点 `GET /api/v1/search`，挂同一 `api_v1_router`；独立 Contract `docs/api/F013.md`；不新增实体/字段 | CONFIRMED（§17/§25）+DESIGN |
| DR-172 | 搜索结果为统一条目信封：`object_type∈{resource,cluster,ip_address,service}`、稳定 UUID `id`、`matched_field`/`matched_value`、可选嵌入对象 `resource`/`cluster`/`ip_address`/`service`；不落库（§4） | CONFIRMED（§4/§17）+DESIGN（I-5 目的） |
| DR-173 | 命中语义：hostname→`resource`；IP→`ip_address`（绑定→嵌入 resource，未绑定→resource=null）；Cluster→`cluster`；Service→`service`（嵌入承载 resource） | CONFIRMED（§17/§33）目的 + PROPOSED→CONTRACT（返回形态，I-5/I-6） |
| DR-174 | 去重裁定（I-11）：按 `(object_type, id)` 唯一；不为 IP/Service 命中合成额外 `resource` 行；直接 hostname 命中才产生 `resource` 行；不同 Cluster 同名/同值地址为不同对象、不去重 | PROPOSED→CONTRACT（I-11，Product/Architect） |
| DR-175 | 排序裁定（I-11）：相似度降序 → `object_type` 固定序 `resource, cluster, ip_address, service` → `id` 升序；构成全序以支持稳定分页；相似度不暴露 | PROPOSED→CONTRACT（I-11） |
| DR-176 | Cluster 命中只返回 `cluster` 行，不自动展开其下 Resources，避免结果集爆炸；需要子资源用 Cluster Detail（§19）；I-12 保持 PROPOSED 默认不展开 | PROPOSED→CONTRACT（I-12） |
| DR-177 | 空/纯空白 `q` → 422 `VALIDATION_ERROR{field:"q"}`，不返回全量、不 500（I-13）；`q` trim 后长度 1–255，超限 422 | PROPOSED→CONTRACT（I-13/A9） |
| DR-178 | 可选 `type` 过滤 ∈{resource,cluster,ip_address,service}；非法→422；缺省不过滤。搜索框与类型下拉均支持输入/模糊（§17） | PROPOSED→CONTRACT（§17） |
| DR-179 | 分页沿用列表基线：`page≥1` 默认 1、`page_size` 1–100 默认 20、越界/非整数 422；空结果 200 `{items:[],page,page_size,total:0}`（I-2/I-3/§28） | CONFIRMED（§28）+DESIGN |
| DR-180 | 软删：搜索默认 `deleted=exclude`；`include/only` 需 VIEW_DELETED，否则 403 `FORBIDDEN{reason:"permission"}`；Dashboard 计数/容量恒为未删（§21/§23/DR-130） | CONFIRMED（§21/§23）+DESIGN |
| DR-181 | Dashboard 端点 `GET /api/v1/dashboard`（I-14），READ 全角色；独立端点、不按场景另建 | PROPOSED→CONTRACT（I-14/§23/§25） |
| DR-182 | Dashboard 结构：`counts`（全局未删，含 INACTIVE，I-8）+ `networks`（per-Network `capacity` + `auto_pools`）；**消费** F010 口径，`remaining` 负值原样 | CONFIRMED（§20/T32/I-7）+DESIGN |
| DR-183 | Dashboard 不提供跨 Network 全局合计（I-16）；`networks` 行分页（page/page_size）但 `counts` 恒为全局、不受分页影响 | PROPOSED→CONTRACT（I-16） |
| DR-184 | pg_trgm/GIN 引入点落在 F013：`pg_trgm` 扩展已由 F001 `0001_baseline` 启用，F013 新增迁移 `0013_search_indexes`（仅 GIN trigram 索引，无表结构变更）；索引集合交 Database 在 DATABASE Gate 签核（I-15） | PROPOSED→CONTRACT/DATABASE（I-15/§26） |
| DR-185 | 与各域列表 `q` 契约收敛（I-17）：F013 只新增 `/api/v1/search`，不改各 DONE 域列表 `q` 行为语义（保持 ILIKE）；F013 Contract 记录两者关系；未来统一升级走变更控制，不追溯修改 | PROPOSED→CONTRACT（I-17） |
| DR-186 | 计划字段：`layers.database=true`、`layers.backend=true`、`layers.frontend=true`、`api_required=true`（I-18） | PROPOSED→CONTRACT（I-18） |
| DR-187 | 只读无副作用：无写端点、不写 Audit、重复调用幂等（I-4/§22/§20） | CONFIRMED（§22/§23）+DESIGN |
| DR-188 | Dashboard 计数全局口径（I-8），不默认按 Cluster 过滤；OPEN I-8 若后续确认，以新增可选参数扩展，不破坏现有响应 | PROPOSED→CONTRACT（I-8） |
| DR-189 | F013 引入 GIN 使既有 DB 决策与桩测试失效：DB-D30/DB-D41/DB-D89/DB-D124/DB-D137 的「不建 pg_trgm/GIN」需由 Database 以 errata 修订（原列 DB-D38 系编号误标：DB-D38 为 `uq_resources_cluster_id_hostname_key` 部分唯一决策，与 GIN 无关；resources errata 目标为 DB-D41）；`test_resource_constraints.py:300`、`test_service_constraints.py:225`、`test_cluster_*`（如有）等无-GIN 断言需 Tester/Backend 同步 | CONFIRMED+DESIGN（跨 Feature 一致性，见 §9/§12） |

> 状态语义：`CONFIRMED`+`DESIGN` = 由已确认规则必然产生的技术要求；`PROPOSED→CONTRACT` = 对 F013 product I-11–I-18（均非阻塞）给出的可实施默认，由 Product/Architect 在 CONTRACT Gate 定稿，不在此之前视为永久规则。

## 3. Domain / Data Impact

| 对象/视图 | 关系 | 作用域 | 生命周期 | 依据及状态 | 裁定 |
| --- | --- | --- | --- | --- | --- |
| 搜索结果（派生视图，非实体） | 跨 Resource/Cluster/IPAddress/Interface/Service | 全局只读 | 无（不落库） | §17/§33；返回形态 PROPOSED | DR-172–DR-176 |
| Dashboard 计数（派生视图） | 聚合 Cluster/Resource/Network 未删记录 | 全局只读 | 无 | §20 CONFIRMED | DR-182/DR-188 |
| Dashboard 容量（派生视图，消费 F010） | 按 Network 与 AUTO 池聚合未删 IP | 每 Network | 无；随底层数据变化 | §20/§11.1/T32；F010 DR-130 | DR-182 |
| IP→Resource 定位 | IPAddress→Interface→Resource（N:1，未绑定可空） | Cluster 内 | 无 | §13/§14 CONFIRMED | DR-173（未绑定 resource=null） |
| Service→Resource 定位 | Service→Resource（N:1） | Resource | 无 | §15 CONFIRMED | DR-173 |
| Cluster 命中展开 | Cluster→Resource（1:N） | Cluster | 无 | §17/§19 | DR-176（不展开） |
| GIN trigram 索引 | resources.hostname / clusters.（code_key,name）/ services.name_key | 全局 | 迁移 0013 建/删 | §26/§17；I-15 | DR-184（Database 签核） |

**数据完整性对应表**（引用 `.pi/skills/data-integrity/SKILL.md`，精简；只读视图无写入约束）

| 规则依据及版本 | 作用域/读取入口 | 数据库保证 | 业务层保证 | 并发/生命周期边界 | 验证与证据 |
| --- | --- | --- | --- | --- | --- |
| §21 未删过滤 | 搜索、计数、容量 | 查询条件 `deleted_at IS NULL`（默认）；部分唯一/索引共享 | 默认 exclude；ADMIN include/only 需 VIEW_DELETED | 软删后即消失；恢复后重现 | V-DB-TBD（F013）/A8/A23 |
| §20/T32 容量口径 | Dashboard 容量 | 无（只读消费） | 调用 F010 `network_capacity`/`auto_pools_capacity`，不改写、不截断负值 | 与 `/api/v1/networks/{id}/capacity` 逐项一致 | A14–A20 |
| §4.1/§7/D01 §5 归一化 | hostname/Cluster/Service 匹配 | 归一化键列（hostname_key/code_key/name_key） | 查询先归一化（trim+ASCII 折叠），与唯一性同口径 | 大小写/空白 | A3/A5 |
| §4 稳定 ID | 结果跳转 | PK UUID | 结果携带 `id` | 改名不改 id | A10 |
| §23 权限 | 搜索/Dashboard/已删 | 无 | READ 全角色；include/only 需 VIEW_DELETED | 401 先于 403 | A22 |
| §22 只读 | 搜索/Dashboard | 无写 | 不写 Audit、无写端点 | 幂等 | A21 |

## 4. 搜索结果模型与裁定（I-11 / I-12 / I-13）

### 4.1 条目信封（DR-172）
```json
{
  "object_type": "resource | cluster | ip_address | service",
  "id": "<UUID>",
  "matched_field": "hostname | address | code | name",
  "matched_value": "<展示值>",
  "resource":   { "id","hostname","resource_type","role","status",
                  "cluster": {"id","code","name"} } | null,
  "cluster":    { "id","code","name","status" } | null,
  "ip_address": { "id","address","network":{"id","name"},
                  "interface":{"id","name"} | null } | null,
  "service":    { "id","name","status" } | null
}
```
按 `object_type` 填充：`resource` 行仅 `resource`；`cluster` 行仅 `cluster`；`ip_address` 行 `ip_address` + `resource`（绑定）或 null（未绑定）；`service` 行 `service` + `resource`（承载）。其余字段为 null。字段集不因查询而变，便于前端判别。`matched_value` 为原展示值；模糊高亮由前端基于 `matched_field` 处理。

### 4.2 命中语义（DR-173，A1–A7）
- **hostname**：对 `resources.hostname`（归一化键）trigram/子串匹配；返回 `resource`。
- **IP**：先按裸 IPv4 精确匹配 `host(ip_addresses.address)`；若非合法整址，允许前缀/trigram 兜底（PROPOSED，交 CONTRACT）。返回 `ip_address`；经 `interface→resource` 填 `resource`，未绑定填 null（不伪造归属，A5/I-6）。
- **Cluster**：对 `clusters.code_key`（ASCII 大写归一化）与 `clusters.name` 匹配；返回 `cluster`（A6）。
- **Service**：对 `services.name_key` 匹配；返回 `service` + 承载 `resource`（A7）。
- 单次查询可同时返回多类结果；`type` 参数可收窄（DR-178）。

### 4.3 去重与排序（I-11，DR-174/DR-175）
- **去重键** `(object_type, id)`，同键只出现一次。
- 同一 Resource 被 hostname 与 Service/IP 同时命中时：Service 以 `service` 行、绑定 IP 以 `ip_address` 行表示，各自 embedding 该 Resource；**不额外合成重复 `resource` 行**。若 Resource 被 hostname 直接命中，则另有一条 `resource` 行。此裁定偏离 product §2.2 的 PROPOSED「按 Resource 身份折叠为一条」，理由：四类 typed 行信息更完整、直接回答 §33，且便于前端按类型展示；**交 CONTRACT 由 Product/Architect 确认**。
- 不同 Cluster 的同名 Resource、同值 IP 是不同对象，不去重（§7/§14）。
- **排序**：`similarity DESC`（精确命中记 1.0）→ `object_type` 序 `resource < cluster < ip_address < service` → `id ASC`。构成全序，保证分页稳定。

### 4.4 Cluster 展开（I-12，DR-176）
- 仅返回 `cluster` 行；不自动附带其下 Resources。理由：避免结果集爆炸，且 §19 Cluster Detail 已提供 Resources 列表与组合过滤。I-12 维持 PROPOSED 默认；CONTRACT 若要求展开，须另定上限与分页，不在本 ADR 预建。

### 4.5 空查询（I-13，DR-177）
- `q` 必填；服务端 trim 后非空；空/纯空白→422 `VALIDATION_ERROR{field:"q"}`；`q` trim 后长度 1–255；不返回全量、不 500。前端在空输入时不发请求。

## 5. Dashboard 模型与裁定（I-14 / I-16）

### 5.1 路径（I-14，DR-181）
`GET /api/v1/dashboard`，挂同一 `api_v1_router`；READ 全角色；只读。备选 `/api/v1/dashboard/summary` 不采用（§25 路径示例非完整契约，新增只读端点不按场景另建）。

### 5.2 计数（I-8，A13/A23）
`counts` 恒为全局未删计数，含 INACTIVE Cluster/Network，不含软删：
- `clusters` = 未删 Cluster 数（含 INACTIVE）
- `resources` = 未删 Resource 总数（BARE_METAL + VIRTUAL_MACHINE）
- `bare_metal` / `virtual_machines` = 按 `resource_type`
- `networks` = 未删 Network 数（含 INACTIVE）
与列表端点的 `total`（deleted=exclude、无其它过滤）等价，便于交叉核对。

### 5.3 容量（只消费 F010，DR-182，A14–A20）
- 每个未删 Network 一行：`network`（含 cluster 上下文、status、auto_allocate）+ `capacity`（`allocatable_total`/`occupied`/`remaining`）+ `auto_pools[]`（每 AUTO 池 `ip_pool` + 三项）。
- 后端直接调用 `ip_capacity.network_capacity(db, network)` 与 `ip_capacity.auto_pools_capacity(db, network)`（F010 已实现，DR-130）；字段名与 `/api/v1/networks/{id}/capacity` §6.9 一致。
- **`remaining` 负值原样返回，不设下限、不截断**（F010 DR-130 复用）。
- 软删 Network 不出现；Network INACTIVE 仍显示且容量不清零（§5/§11/§20）。
- AUTO 池占用按**当前地址所在范围**，不按历史来源；Network 占用含池外手动、含未绑定 IP（F010 口径，不重算）。

### 5.4 全局合计（I-16，DR-183）
不提供跨 Network 的合计字段。理由：不同 Cluster 可含相同地址，全局相加误导。`networks` 行支持分页（page/page_size，基线），`counts` 与每行 `capacity` 不受分页影响。

## 6. pg_trgm / GIN 引入点与索引集合（I-15，DR-184）

- **扩展**：`pg_trgm` 已由 F001 `0001_baseline` 以 `CREATE EXTENSION IF NOT EXISTS pg_trgm WITH SCHEMA public` 启用（DB-D2/§26）；F013 迁移**不重复启用**。
- **引入点**：F013 作为首个全局跨对象模糊搜索 Feature，新增迁移 `0013_search_indexes`（`down_revision="0012_service_endpoints"`），仅新增 GIN trigram 索引，不改表结构。
- **候选索引集合**（交 Database 在 DATABASE Gate 签核；最终 opclass/表达式/是否 partial 由 D02/Database 裁定）：
  | 候选索引 | 表/列（opclass） | 用途 | 备注 |
  | --- | --- | --- | --- |
  | `ix_resources_hostname_trgm` | `resources (hostname gin_trgm_ops)` | hostname 模糊 | 列已存 ASCII 小写归一化值 |
  | `ix_clusters_code_key_trgm` | `clusters (code_key gin_trgm_ops)` | Cluster code 模糊 | code_key=ASCII 大写归一化 |
  | `ix_clusters_name_trgm` | `clusters (name gin_trgm_ops)` | Cluster name 模糊 | 保留展示大小写 |
  | `ix_services_name_key_trgm` | `services (name_key gin_trgm_ops)` | Service name 模糊 | name_key=ASCII 小写归一化 |
  | （候选）`ix_ip_addresses_host_trgm` 或 `host(address)` btree/表达式索引 | `ip_addresses (host(address))` | IP 前缀/模糊兜底 | `inet` 不能直接 trigram，须函数表达式；精确匹配可用等值，是否建索引由 Database 评估（现 DB-D124 不建 address 单列 btree） |
- **是否 partial**：`WHERE deleted_at IS NULL` 可减小索引，但 `deleted=include/only`（ADMIN）需全量；倾向非 partial，由 Database 裁定。
- **不建**：Networks/Interfaces/IPPools/ServiceEndpoints/各类型的 name 之外列不建 trigram（§17 只要求 hostname/IP/Cluster/Service）。
- **迁移可逆性**：up 建索引、down 对称 DROP 索引；**不 DROP pg_trgm/btree_gist**（F001 DB-D4）；单 head、无回填。
- **既有 no-GIN 决策的 errata（DR-189）**：DB-D30/DB-D41/DB-D89/DB-D124/DB-D137 等「不建 pg_trgm/GIN」需 Database 在 DATABASE Gate 以 errata 或新决策修订（明确 F013 引入），并同步受影响断言测试。DB-D38 系编号误标（实为部分唯一约束决策），resources 的 errata 目标为 DB-D41。此为跨 Feature 一致性事项，不改变各域业务行为。

## 7. 与各域列表 `q` 的契约收敛（I-17，DR-185）

- 既有各域列表 `q` 实现为 `ILIKE` 子串（`services/resource.py:605`、`cluster.py:209`、`service.py:240`、`ip_address.py:369`、`ip_pool.py:312`、`network.py:234`），**F013 不改动**。
- `/api/v1/search` 使用 pg_trgm 与归一化键匹配，是全局跨对象入口；各域列表 `q` 仍是各域内单对象过滤。
- F013 Contract 明确记录两者关系（不同接口、不同匹配实现），**不追溯修改已 DONE 域的行为语义**；未来统一升级为 pg_trgm 须走 `docs/project/change-control.md`。
- 匹配正确性不依赖索引（pg_trgm 为性能优化）；迁移缺失时功能仍正确，仅性能退化。

## 8. Frontend / Backend Work

**Backend（`layers.backend=true`）**
- `app/schemas/search.py`、`app/services/search.py`：归一化查询、四类候选合并、去重/排序、软删过滤、分页、`q`/`type`/`page/page_size` 校验（空 q→422）。
- `app/api/v1/search.py` + 在 `app/api/v1/router.py` 挂载 `search.router`。
- `app/schemas/dashboard.py`、`app/services/dashboard.py`：计数查询 + 复用 `app/services/ip_capacity.py` 的 `network_capacity`/`auto_pools_capacity`，组装 `counts`/`networks`，networks 分页。
- `app/api/v1/dashboard.py` + 挂载 `dashboard.router`。
- 权限：READ 全角色；`deleted=include|only` 复用 VIEW_DELETED 检查（F003 口径）。无写端点、不写 Audit。

**Frontend（`layers.frontend=true`）**
- 首页统一搜索入口：搜索框 + 类型下拉（均支持输入/模糊）；结果列表按 `object_type` 展示类型标签、模糊高亮、跳转（Resource→§18 Resource Detail，Cluster→§19 Cluster Detail，IP/Service→其对象/所属资源）；Loading/Success/Empty/Error（Unknown）状态；空输入不发请求。
- Dashboard 卡片区：Counts（Cluster/Resource/BareMetal/VM/Network）+ per-Network 容量表（可分配/已占用/剩余，剩余可为负并原样呈现）+ 每行 AUTO 池容量 + `status`/`auto_allocate` 标识（容量与状态/许可分别展示）。
- ADMIN 已删开关（搜索侧 `deleted`）；无新增/修改/删除/恢复入口。

## 9. 数据库影响（交 DATABASE）

- 无表结构变更、无新实体/字段；仅新增迁移 `0013_search_indexes`（down_revision=`0012_service_endpoints`）：GIN trigram 索引（§6 候选集合）。
- 不重复启用 `pg_trgm`（0001 已启用），不 DROP 任何扩展。
- 对称可逆：down 仅 DROP 索引；单 head、无回填、无数据迁移。
- 必须由 Database 在 DATABASE Gate 签核：索引集合/opclass/表达式/是否 partial、`host(address)` 索引取舍、EXPLAIN 证据（`%query%` 命中 GIN）、迁移 up/down/up 真库验证。
- 既有 DB 文档「不建 pg_trgm/GIN」决策的 errata（DR-189）由 Database 处理。

## 10. 验证策略（A1–A24，真实 PG）

- **搜索**：A1–A12。空/纯空白 q→422（A9）、hostname 模糊（A2）、归一化大小写/空白（A3）、IP→Interface→Resource（A4）、未绑定 IP 无 Resource 归属（A5）、Cluster code/name（A6）、Service→Resource（A7）、软删默认排除 + ADMIN deleted（A8）、稳定 ID/跳转（A10）、分页/排序/全序（A11）、pg_trgm 索引经 Database 签核（A12）。
- **去重/排序/展开/空查询**：I-11（同 Resource 多路径不重复、对象唯一）、I-12（Cluster 不展开）、I-13（空 q 422）。
- **Dashboard**：A13–A23。计数口径（A13/A23）、per-Network 容量（A14）、AUTO 池（A15）、排除/去重（A16）、占用含未绑定与池外、软删不计、负值原样（A17）、AUTO 占用按当前地址、Network 含池外（A18）、容量与状态/许可分别展示与 INACTIVE 不清零（A19）、与 F010 `/capacity` 逐项一致（A20）。
- **只读/权限**：A21（无写端点、无 Audit）、A22（全角色可读；401；include/only 需 VIEW_DELETED）。
- **迁移**：0013 up/down/up、单 head、无回填、GIN 索引存在断言、扩展前后一致（pg_trgm/btree_gist 不变）；DB-D30/41/89/124/137 相关「无 GIN」桩测试同步更新（DR-189；原含 DB-D38 系误标）。
- **契约收敛**：各域列表 `q` 行为回归不变（I-17）。
- **排除项**：A24（SN/MAC/Role/GPU Model 不纳入验收）。
- 限制：pg_trgm/负值/GIN 必须真 PG；SQLite/Mock 不足以证明。

## 11. 计划字段 layers / api_required（I-18，DR-186）

```yaml
layers:
  database: true     # 迁移 0013_search_indexes（GIN trigram 索引）— 取决于 I-15 裁定；pg_trgm 已启用，仅索引
  backend: true
  frontend: true
api_required: true   # /api/v1/search + /api/v1/dashboard
```
`database=true` 的依据：I-15 需在 F013 落地 GIN 索引集合 + 迁移 0013，由 Database 承担实现（Layers 约定：数据库实现由 Backend 承担，本 Feature database=true 以描述 Schema/索引变更存在并有实现者）。

## 12. 风险与待核对项

- **交 DATABASE（I-15）**：GIN 索引集合/opclass/表达式/partial 取舍；`host(address)` 索引取舍；迁移 0013 up/down/up；既有 DB-D30/41/89/124/137 的 errata（原含 DB-D38 系误标）；EXPLAIN 命中证据。
- **交 TEST_DESIGN**：A1–A24 判据；去重/排序全序与稳定分页；与 F010 `/capacity` 逐项一致；真库 GIN；既有 no-GIN 断言更新范围。
- **交 CONTRACT**：I-11（去重可用 typed 行 vs product PROPOSED 折叠）、I-12、I-13、I-14、I-16、I-17 定稿；搜索条目字段/错误细节；`q` 长度上限。
- **I-8（OPEN，product）**：Dashboard 是否按 Cluster 过滤 — 本设计不默认新增；CONTRACT 若确认则加可选参数，不影响现有响应。
- **跨 Feature（DR-189）**：引入 GIN 使既有 `test_resource_constraints.py:300`、`test_service_constraints.py:225` 等「USING gin == []」断言失效，须 Backend/Tester 同步；F004/F008/F011 DB 文档 errata。
- **非阻塞**：I-11–I-18 均为 design/contract 级，给可实施默认，可在 CONTRACT 定稿后进入实现。

## 13. 结论与下一步

无 Blocking Questions。I-11–I-18 已给出设计裁定（PROPOSED→CONTRACT），DR-171–DR-189 覆盖结果结构、去重/排序、Cluster 展开、空查询、Dashboard 路径/结构/全局合计、pg_trgm/GIN 引入点与索引集合、列表契约收敛、计划字段。**Status：`READY FOR DESIGN`。**

下一步：DATABASE 出 `docs/database/f013-search-index.md`（迁移 0013 + 索引集合 + errata，签核 DR-184/DR-189）；TEST_DESIGN 给 A1–A24 判据与其 F013 独立性；CONTRACT 定稿 `docs/api/F013.md` + 裁定 I-11–I-18 → `READY FOR IMPLEMENTATION`。