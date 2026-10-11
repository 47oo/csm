# F011 Service 服务登记 — PRODUCT 阶段报告

- **Feature**：F011 Service 服务登记（FEATURE，P1，M5 服务与端点，deps [F004]）
- **阶段**：PRODUCT；**结论**：`READY FOR ARCHITECT`
- **依据**：requirements-v3.md revision 3（§3、§4、§4.1、§5、§15、§16、§17、§18、§19、§21、§22、§23、§25、§26、§27、§28、§31 T21/T23/T24/T25/T26/T36/T37/T40/T41、§32、§33、§35.2 Q02-A/Q06/Q10-A/Q10-B、§35.3 D01/D02）；plan_revision 4 F011；`docs/features/F004/product.md`（F004 DONE）；d01-conventions.md v9；api/F009.md v1、database/f009-ip-pool.md v1（格式参照）。

## 1. 目标与范围

### 1.1 目标
在 F004 统一 Resource 基础上，提供 Service 实体登记与维护：表达某个 Resource 上运行的逻辑服务（如 SSH、slurmd、node_exporter、DCGM Exporter）及其人工维护的运行状态，作为 F012 ServiceEndpoint 的父对象，支撑 §17 按 Service 查询、§18 Resource Detail Services 区域、§19 Cluster Detail Services 与 §33 目标查询场景。

### 1.2 本次范围（CONFIRMED）
- 字段（§15）：resource、name、status、description、metadata。
- 归属与范围（§4/§15）：Service 属一个 Resource（Resource 维护其运行的 Service）；一个 Resource 可有多个 Service；Service 经 Resource 间接归属 Cluster；无 resource_type 限制。
- 名称（§4.1）：同 Resource 内未删除唯一、大小写不敏感（保留展示）、允许中文及内部普通空格（不自动合并）、删除后可复用、恢复重检。
- status（§15/T21/T37）：RUNNING / STOPPED / UNKNOWN，默认 UNKNOWN，由人工维护；不表示系统已探测实际进程状态，不由名称或外部监控推导/自动转换。
- 生命周期（§21）：软删；默认查询隐藏；ADMIN 恢复/查看已删；有未删除 Endpoint 引用时禁删并返回引用列表（§16/§21，检查由 F012 提供数据）；无隐式级联；恢复重检名称唯一与所属 Resource 有效性，失败不覆盖新对象。
- 权限/审计（§22/§23）：EDITOR 增改；ADMIN 删/恢复/查看已删；VIEWER 只读；CREATE/UPDATE/DELETE/RESTORE 写 Audit；Activity 全角色。
- 登记 slurmd 等不代表 Slurm 自动部署或状态同步（§15）。

### 1.3 使用者
EDITOR 登记与维护 Resource 的服务清单及人工状态；ADMIN 删除、恢复、查看已删；VIEWER 查询。运维人员据 Service 清单回答「某机器运行哪些 Service」及「某 Service 位于哪个 Resource」。

## 2. 字段契约（Service，补齐 D01）

| 字段 | 类型 | 可空 | 创建必填 | 单位 | 合法值/语义 |
| --- | --- | --- | --- | --- | --- |
| resource | UUID | 否 | 是 | — | 引用存在、未软删的 Resource（§4.1/§15）；创建后可否修改见 I-2（PROPOSED 不可改） |
| name | string | 否 | 是 | — | trim 首尾；非空；禁控制字符（Cc/Cf）；仅 ASCII A-Z→a-z 折叠、非 ASCII 原样、保留展示；允许中文及内部普通空格（不自动合并）；同 Resource 未删除内唯一；长度交 D01（PROPOSED 1–255，见 I-3） |
| status | enum | 否 | 否 | — | RUNNING\|STOPPED\|UNKNOWN；默认 UNKNOWN；人工维护，非探测（§15）；显式 null/非法→422 |
| description | string | 是 | 否 | — | 描述性自由文本；长度交 D01（PROPOSED 无上限、text，同 F003/F004/F007/F008/F009） |
| metadata | object (JSONB) | 否 | 否 | — | §15 字段清单包含；PROPOSED Service 自有、object、默认 {}、整值替换；非 object/显式 null→422；归属见 I-1 |
| id / version / created_at / updated_at / deleted_at | 标准 | — | — | — | 稳定 UUID；version 乐观锁（§23）；timestamptz UTC（D01 §2）；deleted_at 软删（§21） |

补充：
- 省略语义（§4.1/D01 §4）：创建省略非必填→默认/null；更新（PATCH）省略=保持（exclude_unset）；显式 null 仅清空 nullable（description）；必填/非 nullable（resource/name/status/metadata）显式 null→422；未知/只读字段→422；结构字段（metadata）整值替换。
- 名称归一化（§4.1/D01 §5）：trim→非空→禁控制字符；唯一比较用归一化键（PROPOSED name_key=ASCII_lower(btrim(name))，应用逐码位、DB translate、禁 lower()/str.lower()）；仅未删除对象参与唯一；软删后复用；恢复重检冲突不覆盖新对象。
- 不落字段：Service 不存 IP、端口、协议、监听地址（§16 归 ServiceEndpoint/F012）；不存 cluster 直接字段（经 Resource 间接）；不存 service_type 枚举、不存实时探测状态、不存自动部署/同步标记。

## 3. 领域影响分析

| 对象 | 关系 | 作用域 | 生命周期 | 依据 | 未决 |
| --- | --- | --- | --- | --- | --- |
| Service | 多对一依附 Resource | 名称唯一=同 Resource | 创建/改名/改状态/软删/恢复 | §4/§15/§21 | resource 可变性（I-2） |
| Service→Resource | N:1，创建必填，引用须存活 | Resource 所在 Cluster（间接） | Resource 软删后其 Service 仍存但恢复受检 | §4.1/§15 | 恢复重检依赖有效性（已确认） |
| name 唯一 | 同 Resource 未删除，大小写不敏感 | Resource | 软删后复用；恢复重检 | §4.1/§21/Q10-B | D01 长度（I-3） |
| status | RUNNING/STOPPED/UNKNOWN 人工维护 | 本对象 | 默认 UNKNOWN，仅经 API 变更 | §15/Q02-A/T21 | 无（确认不探测推断） |
| Service←ServiceEndpoint | Endpoint 引用 Service，1:N | 同 Service | 有未删 Endpoint 禁删；不级联 | §16/§21 | 引用检查跨 Feature 落点（I-4） |
| metadata | PROPOSED Service 自有 JSONB | 本对象 | 整值替换 | §15/D01 | 归属待固定（I-1） |
| 展示/查询 | §18 Services、§19、§17 Service 搜索、§33 | 随 Resource/Cluster | — | §17/§18/§19/§33 | 页面聚合归 F013 |

## 4. 必须遵守的已确认约束
- §15：字段清单 resource/name/status/description/metadata；Resource 维护其运行的 Service；状态 RUNNING/STOPPED/UNKNOWN 默认 UNKNOWN、人工维护、不表示系统已探测实际进程状态；登记 slurmd 不包含 Slurm 自动部署或状态同步。
- §4.1：对象名称与所属对象创建时必填；名称 trim、禁空/控制字符、大小写不敏感、允许中文与内部普通空格且不自动合并、同 Resource 唯一、删除后复用、恢复重检。
- §4/§5：Resource → Service → ServiceEndpoint 关系；Service 经 Resource 归属 Cluster（§5 Cluster 间接拥有 Service）。
- §16：Endpoint 至少支持 service/ip_address/protocol/port/description；一个 Service 可有多个 Endpoint（F012 落地）；F011 仅提供父对象与引用检查契约。
- §21：软删默认隐藏；ADMIN 恢复/查看已删；有未删除依赖（Endpoint）禁删并返回引用列表；不隐式级联；恢复重检唯一性与所属对象有效性，标识被重用/依赖仍删时失败不覆盖新对象；Audit 保留。
- §22：CREATE/UPDATE/DELETE/RESTORE 写 Audit；Activity 全角色；不记敏感内容。
- §23：EDITOR 增改；VIEWER 只读；删除/查看已删/恢复 ADMIN；乐观锁版本冲突检查。
- §25/§26：REST 前缀 `/api/v1/`，核心路径含 `/api/v1/services`；PostgreSQL / SQLAlchemy 2.x / Alembic、JSONB、pg_trgm 为后续（F013）。
- §27：同 Resource 名称唯一由 PostgreSQL 兜底，业务层共同保证；真实 PG 验证。
- §28：列表页至少分页、排序、过滤、模糊搜索。
- §32/§33：可维护 Service；按 Service 找到 Resource；回答「机器运行哪些 Service」。
- §4/D01 §1：内部关联用稳定 UUID；D01 §4 省略语义与 422 口径。

## 5. 可观察验收标准

| # | 验收标准 | 映射 |
| --- | --- | --- |
| A1 | Service 名称首尾空白 trim；空名/控制字符拒（422）；中文与内部普通空格允许且不自动合并 | §4.1/T40 |
| A2 | 同 Resource 创建大小写不敏感重名 Service（如 SSH / ssh）被拒（409 CONFLICT{reason:"unique_conflict",field:"name"}）；不同 Resource 同名允许 | §4.1/T21/T40 |
| A3 | 软删后同名 Service 可重建；存活同名存在时创建失败；名称被复用时旧 Service 恢复失败且不覆盖新对象 | §4.1/§21/T41 |
| A4 | 缺失 resource/name 创建失败（422）；resource 不存在/已软删时创建失败（422 field="resource"） | §4.1/§15/§21 |
| A5 | status 省略→UNKNOWN；显式设置 RUNNING/STOPPED/UNKNOWN 按值保存；显式 null/非法值→422 | §15/T21/T37 |
| A6 | status 为人工维护：仅经 API 变更；不由名称（如 slurmd/node_exporter）或外部探测推导/自动转换；登记 slurmd 不触发 Slurm 部署或状态同步 | §15/T21 |
| A7 | description 可空、PATCH 显式 null 清空、PATCH 省略保持 | §15/§4.1 |
| A8 | metadata（PROPOSED）：省略→{}；整值替换；显式 null/非 object→422；响应暴露 | §15（I-1） |
| A9 | resource 创建必填；PROPOSED 创建后不可改（PATCH 出现 resource→422） | §4.1（I-2） |
| A10 | 存在未删除 Endpoint 引用时删除被拒并返回引用列表（references）；不隐式级联；无引用可软删 | §16/§21/T23 |
| A11 | Service 恢复重检名称唯一与 Resource 有效性；名称被复用/Resource 仍删时恢复失败且不覆盖新对象；恢复不自动恢复 Endpoint | §21/T24 |
| A12 | 权限：VIEWER 只读；EDITOR 增改 Service；删除/查看已删/恢复 ADMIN；服务端执行 | §23/T25 |
| A13 | CREATE/UPDATE/DELETE/RESTORE 写 Audit 且同事务；Activity 全角色可见；不记敏感内容 | §22/T25 |
| A14 | 默认列表隐藏软删；按 resource、status 过滤，按 name 模糊；分页/排序/过滤符合列表基线 | §21/§28 |
| A15 | DB 对同 Resource 未删除 name（归一化键）部分唯一兜底，真实 PG 验证 | §27/T21 |
| A16 | 名称归一化在 API、导入（F014 适用时）、搜索（F013）与 DB 间一致；仅未删除对象参与唯一 | §4.1/§27/T40/T41 |
| A17 | 乐观锁：过期版本编辑被拒（409 VERSION_CONFLICT），无静默覆盖 | §23/T26 |
| A18 | Service 经 Resource 间接归属 Cluster；Resource Detail Services 区域与 §17 Service 搜索可获得数据 | §17/§18/§33 |

说明：A10 的 Endpoint 引用数据来源于 F012；F011 交付引用检查契约与扩展点，含 Endpoint 的端到端删除拦截验证在 F011/F012 集成（T23）完成，见 §7 I-4。

## 6. 明确排除项
- 不做 ServiceEndpoint（监听地址/协议/端口/重复监听唯一性/IP 归属校验）与其 CRUD、§16 全部规则（F012）。
- 不做 Endpoint 与 IP 的绑定/解绑/转移/释放及其对 IP 的引用保护（F010/F012）。
- 不做 Global Search、Dashboard、列表聚合与跨对象模糊搜索（F013）；不做 CSV/Excel 导入（F014，Service 导入为后续扩展）；不做完整 Audit 查询页（F015）。
- 不做 Slurm 自动部署、节点加入、状态同步、实时进程探测、Prometheus/Grafana 监控、自动状态转换。
- 不做 service_type 字典/分类、不做端口/协议/监听地址字段、不做 Service 与 IP 的直接关系、不做通配/VIP/Unix Socket。
- 不改动 F004 已交付的 Resource 语义（类型、Role/Status、hostname 唯一性、cluster 不可改、软删/恢复/引用检查基座）。
- Service 不落 IP/端口/协议/监听地址/cluster 直接字段/实时探测状态/自动部署标记。

## 7. 依赖与未决问题
依赖（CONFIRMED）：F004（统一 Resource、稳定 ID、软删/恢复、引用检查器注册机制、Audit、权限、DB 唯一基座、D01 §1/§4；DONE）；F001（PostgreSQL 基线、真实 PG 测试基线）；D01 共享约定（v9+）。F012 依赖本 Feature 的 Service 父对象；F013 依赖本 Feature 的 Service 查询；F015 依赖本 Feature 的删除/恢复规则。

BLOCKING：无。

CONFIRMED：§15 全部；§4.1 名称规范与唯一；§21 软删/恢复/引用检查；§22；§23；§27；§28；§32/§33；Q02-A/Q06/Q10-A/Q10-B。

PROPOSED/OPEN（非阻塞）：
- **I-1（PROPOSED，非阻塞，Owner Architect/D01）**：§15 字段清单**已包含 metadata**，故 metadata 为 CONFIRMED 字段；其归属与存储形式 PROPOSED 为 **Service 自有 JSONB**（object、默认 {}、整值替换、非 object/null→422），与 Interface/Network/IPPool 先例一致（D01 §5.6/§5.7/§5.8），不并入 Resource 公共 metadata。D01 新增 Service 小节固定。
- **I-2（OPEN，产品/设计，非阻塞）**：§15 未说明 Service 的 resource 是否可改。**PROPOSED**：创建必填、创建后不可直接修改（迁移到其它 Resource 以删除重建表达），与 Interface/Network/IPPool 及 Resource.cluster 口径一致。若确认可变，则须重检目标 Resource 有效性。Owner：Product/用户 → Architect/CONTRACT。
- **I-3（OPEN，D01，非阻塞）**：D01 尚未界定 Service name 长度与 description 长度；PROPOSED name 1–255、description 沿用 text 无上限（同 F003/F004/F007/F008/F009）；D01 §5 表当前将「IPPool/Service name」合并一行，需为 Service 明确行与新增 §5.10 Service 字段口径小节。Owner：Architect/Database → CONTRACT/D01。
- **I-4（OPEN，跨 Feature 边界，非阻塞）**：§21 的 Service 删除引用检查依赖 ServiceEndpoint（F012）数据；F011 在 F012 之前交付，无法单独形成/验证 Endpoint 引用。**PROPOSED**：F011 定义引用检查契约与 provider 扩展点（删除 Service 时查询未删除 Endpoint），在 F012 注册真实 provider；含 Endpoint 的端到端 T23 验证在 F012 及 F011/F012 集成完成。Owner：Architect/协调器。
- **I-5（NOTE，非阻塞）**：§4.1 表述「允许中文及内部普通空格，不自动合并内部空格」，D01 §5 表 Service 行措辞已随 v8 一致化为「允许内部普通空格（不自动合并）」；实现按 D01 口径。Owner：Architect/Database。
- **I-6（NOTE，非阻塞，计划字段）**：`project-plan.yaml` F011 未填 `layers` 与 `api_required`（F001–F010 均有）。协调器/Architect 在 ARCHITECTURE 阶段依实体/API 情况补齐（依 §25 与 §18 展示，预期 api_required=true，layers 含 database/backend，frontend 归属 F013/F011 由设计裁定）。Owner：协调器/Architect。

## 8. 交 Architect 的输入
1. 实体方案：Service 独立表 PK=UUID，FK resource_id→Resource(id)；字段同 §2（resource、name、status、description、metadata）。
2. 约束：resource_id NOT NULL（引用存在未软删 Resource）；name NOT NULL 同 Resource 未删除归一化键部分唯一（I-3）；status NOT NULL DEFAULT 'UNKNOWN' CHECK∈3 值；description text NULL；metadata JSONB NOT NULL DEFAULT '{}'（I-1）；version≥1；软删 deleted_at。
3. 生命周期与引用：软删/恢复；删除前检查未删除 ServiceEndpoint 引用并返回引用列表（F012 数据，I-4）；恢复重检名称唯一与 Resource 有效性，不级联。
4. 归属与不可变性：resource 创建必填、PROPOSED 创建后不可改（I-2）；无 resource_type 限制。
5. API：`/api/v1/services` 契约（创建/更新/详情/列表/删除/恢复/activity），沿用 F004/F009 与 D01 §4 省略语义、422/409 错误口径、乐观锁、软删可见性；列表按 resource/status 过滤与 name 模糊（§28）。
6. 审计：CREATE/UPDATE/DELETE/RESTORE 写 Audit（before/after），object_type="service"；Activity 全角色。
7. D01 补齐：新增 Service 字段口径小节（name 长度与折叠、status 默认与取值、description 长度、metadata 归属），CONTRACT 签核（I-1/I-3）。
8. 边界语义：向 F012 暴露 Service 父对象与删除引用检查契约；向 F013 暴露 Service 名称与 Resource 归属供搜索/展示；不在本 Feature 定义端口/协议/监听地址。
9. 待裁定/记录：I-1（metadata 归属）、I-2（resource 可变性）、I-3（D01 字段口径）、I-4（Endpoint 引用检查跨 Feature 落点）、I-5（措辞一致性）、I-6（计划字段补齐）。

## 9. 结论与下一步
无 Blocking Questions。**READY FOR ARCHITECT**。下一步 ARCHITECTURE：Service 实体/依赖方案、layers、api_required；CONTRACT 签核 `/api/v1/services` 与 D01 新增 Service 字段口径；DATABASE 依 D01 签核同 Resource 归一化键部分唯一、status CHECK/默认、metadata JSONB、软删/恢复与引用检查（结合 F012 provider）及真实 PostgreSQL 验证方案。