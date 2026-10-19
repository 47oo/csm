# F023 资源+网卡+IP 批量导入 — ARCHITECTURE 阶段报告

- **Task**：F023（FEATURE，P1，M14，deps [F004,F007,F008,F009,F010,F014]）— Architect，Feature 设计模式
- **阶段**：ARCHITECTURE；**结论**：`READY FOR DESIGN`（2026-10-15）
- **Basis**：`docs/features/F023/product.md` v1（A1–A10）；`docs/product/requirements-v3.md` revision 8 §24/§24.1/§10/§11/§11.1/§12/§13.2/§14/§21/§23/§27/§31 T64–T72；`docs/project/project-plan.yaml` revision 11 F023（layers{database:false,backend:true,frontend:true}，api_required=true）；`docs/api/F014.md` v1；`docs/features/F014/architecture.md`（DR-190–DR-212）；后端实现 `app/services/{resource,resource_import,interface,ip_address,network,ip_capacity,audit}.py`、`app/api/v1/imports.py`、`app/schemas/imports.py`、`app/models/*`；前端 `src/api/imports.ts`、`components/ResourceImportPanel.tsx`、`components/importForm.ts`；`docs/architecture/d01-conventions.md` v11。

## 1. 方案摘要、边界与明确不做

F023 在既有域与 F014 两阶段导入之上，新增**「资源+网卡+IP」三元组批量导入**（§24.1）；不新增实体/关系/状态/字段/权限/错误码，是普通创建路径的批量编排。

- 独立第三套**统一宽模板**（`resource_type` 列区分 BM/VM 行），不改 F014 冻结的 BM 14/VM 10 模板。
- 两阶段（预校验只读 → 确认 → 写入再校验）；**单事务 + 按 `(cluster,hostname)` 资源组 SAVEPOINT**，整批成功或整批回滚。
- 逐对象复用同一 Service Layer；Interface/IPAddress 由新抽出的**非提交 staging 核心**承载，`create_interface`/`create_ip_address` 退化为「核心 + commit」薄包装，既有 API 行为不变。
- Network 必须已存在（名称/CIDR 列或 IP `/mask` 在同 Cluster 唯一解析），不创建 Network/Pool/Cluster/Host；IP 按手动分配语义新建并绑定，**不触发自动分配**。

端点（挂同一 `api_v1_router`）：
```
POST /api/v1/imports/resource-interfaces-ips/validate   # IMPORT，只读
POST /api/v1/imports/resource-interfaces-ips            # IMPORT，写入
GET  /api/v1/imports/resource-interfaces-ips/templates  # READ，模板规范
```

边界：仅新增 BM/VM Resource 及其 Interface/IPAddress；不更新/覆盖现存 Resource；`interface_type` 默认 `OTHER`、不推断；不含 `parent_interface`；三元组逐行必填；VM Host 必须批外已存在；沿用 F014 同步上限/错误口径/`IMPORT` 权限。
明确不做：不含 Service/Endpoint/Cluster 导入；不创建/导入 Network/Pool；不改 F014 模板/端点/契约；不触发自动分配；不新增实体/字段/权限/错误码；不向既有 Resource 追加 Interface/IP。

## 2. Design Requirements（DR-401–DR-431）

| ID | 决策 | 状态 |
| --- | --- | --- |
| DR-401 | 独立第三套统一宽模板 + 三端点 + 独立 Contract `docs/api/F023.md`；不改 F014；不新增实体/字段。 | CONFIRMED+DESIGN |
| DR-402 | 权限：validate/write 均 `IMPORT`；模板 `READ`；401 先于 403；CSRF 沿用 F002 §2.1。 | CONFIRMED+DESIGN |
| DR-403 | 请求 `multipart/form-data`（`file`+`format`∈{csv,xlsx}）；不落盘；写入重新上传完整重校验。 | PROPOSED→CONTRACT |
| DR-404 | 预校验 200 `{format,total_rows,importable_rows,error_count,errors:[{row,field,reason,related_row?}],errors_truncated}`；聚合不 fail-fast。 | CONFIRMED+DESIGN |
| DR-405 | 成功 201 `{created,total_rows}`；有行错误 422 `IMPORT_VALIDATION_FAILED`（聚合错误，整批回滚）；文件级 4xx 复用 F014 码。 | CONFIRMED+DESIGN |
| DR-406 | 统一宽模板 26 列（列名/顺序冻结）：cluster,hostname,resource_type,role,status,host,vcpu,memory_mb,disk_gb,hypervisor,manufacturer,model,serial_number,cpu_model,cpu_sockets,cpu_cores,gpu_model,gpu_count,name,interface_type,mac_address,speed_mbps,mtu,enabled,network,ip；`memory_mb` 按类型映射 BM/VM。 | PROPOSED→CONTRACT |
| DR-407 | 逐行适用性：BM 行的 host/vcpu/disk_gb/hypervisor 必须空；VM 行的 BM 硬件列必须空；`memory_mb` 两类均可；同一文件允许 BM/VM 混排（逐行 `resource_type`）。 | PROPOSED→CONTRACT |
| DR-408 | 三元组必填：cluster/hostname/resource_type/name/ip；可选列空=省略；枚举大写；bool 大小写不敏感（兼容 1/0）。 | CONFIRMED+DESIGN |
| DR-409 | Network 解析优先级：① `network` 列非空按同 Cluster 名称(`name_key` 折叠,不区分大小写)或 CIDR 唯一解析；② 列空用 `ip` 的 `/mask`；③ 皆缺→行错误。 | CONFIRMED+DESIGN |
| DR-410 | `/mask`：构造 `network_of(ip,m)` 在同 Cluster 未软删 Network 中按 CIDR 精确相等匹配（不重叠故唯一）；无命中→行错误；落库 `address` 剥离掩码（masklen=32）；`network` 列优先，仍校验 IP∈CIDR。 | PROPOSED→CONTRACT |
| DR-411 | Network 必须已存在且未软删；新建 IP 要求 `status=ACTIVE`；不存在/软删/INACTIVE→行错误整批失败；不创建 Network/Pool/Cluster/Host。 | CONFIRMED+DESIGN |
| DR-412 | IP 校验复用 `ip_capacity`（属 CIDR、非网络/广播、非 gateway、非 RESERVED、非禁用段）；同 Cluster 未软删唯一；绑定须同 Cluster；不触发自动分配、不消耗 Pool。 | CONFIRMED+DESIGN |
| DR-413 | Interface 校验复用 F007：`normalize_interface_name`（trim/非空/无内部空白/无控制字符/≤64，区分大小写）、同资源未软删唯一；`interface_type` 默认 OTHER；不含 parent；`enabled` 默认 true。 | CONFIRMED+DESIGN |
| DR-414 | 分组/合并：`(cluster_id,hostname_key)`→1 Resource；Resource 内 `name`→1 Interface；每行→1 IPAddress；同组多行合法。 | CONFIRMED+DESIGN |
| DR-415 | 组内一致性：同 Resource 组资源级字段、同 Interface 组接口级字段，多行给出不同规范化值→行错误（`related_row` 指前一处）；相同/仅一处给→取该值；均省略→默认；`resource_type` 不一致视为组内冲突。 | PROPOSED→CONTRACT |
| DR-416 | 文件内重复：同 `(cluster,ip)` 多行→行错误（两行号）；同 `(cluster,hostname)`、同 `(resource,name)` 非错误（合并）；现存 `(cluster,hostname)` 未软删冲突→行错误、不更新/覆盖、无 UPDATE Audit。 | CONFIRMED+DESIGN |
| DR-417 | Interface staging 重构：拆 `prepare_interface`/`stage_interface`（不提交）；`create_interface` 变薄包装（core+commit），F007 无回归。 | CONFIRMED+DESIGN |
| DR-418 | IP staging 重构：非提交核心 + 可选 `interface_id`（导入即绑定）；`create_ip_address` 变薄包装；复用 `resolve/锁定 network`、ACTIVE、§11.1、同 Cluster 唯一、派生 `ip_pool_id`、CREATE Audit、`_validate_interface`；F010 无回归。 | CONFIRMED+DESIGN |
| DR-419 | 事务与 SAVEPOINT：写入单事务「解析→再校验→插入→Audit→commit」；按资源组 `begin_nested()`；组内 Resource→Interface→IP；错误归因；任一错误 `rollback()` 整批回滚零残留。 | CONFIRMED+DESIGN |
| DR-420 | 写入前再次校验（含 Host 四条件、Network 解析、IP 边界/唯一、文件内重复）；覆盖预校验后状态变化窗口。 | CONFIRMED+DESIGN |
| DR-421 | 并发兜底：唯一索引 + `_lock_network`（`networks` 行 FOR UPDATE）+ VM Host `SELECT FOR UPDATE`；预校验只读不加锁。 | CONFIRMED+DESIGN |
| DR-422 | 错误归因（约束名→行/字段）：`uq_resources_cluster_id_hostname_key`→hostname；`uq_interfaces_resource_id_name`→name；`uq_ip_addresses_cluster_id_address`→ip；`fn_ip_addresses_cidr_contains`/`ck_ip_addresses_address_*`→ip；`fn_ip_addresses_cluster_consistent`→network/ip；`fn/trg_ip_addresses_interface_cluster`→name；FK→所属列；未知→resource_type 并整批回滚。 | CONFIRMED+DESIGN |
| DR-423 | 上限复用 F014（5 MiB/5000/1000 与 413），不新增设置。 | PROPOSED→CONTRACT |
| DR-424 | 错误码全部复用 F014/F002；不新增错误码（不改 F002 注册表）。 | CONFIRMED+DESIGN |
| DR-425 | 与 F014 兼容：F014 端点/模板/契约不变；共享解析/表头匹配/上限/错误形态可抽内部工具不改 F014 行为；`interface`/`ip_address` 薄包装重构不改既有校验顺序/错误码。 | CONFIRMED+DESIGN |
| DR-426 | 前端：新增第三套导入面板/入口，消费 templates；预校验错误表与写入整批失败共用；无部分成功 UI；类型扩展。 | PROPOSED→CONTRACT |
| DR-427 | 模板端点响应草案：`{template:{key,columns:[{name,required,applies_to,target,type,unit,enum,description,example}]}}`；只读无 Audit；列序同 DR-406。 | PROPOSED→CONTRACT |
| DR-428 | 复用 `python-multipart`/`openpyxl`，不新增依赖。 | CONFIRMED+DESIGN |
| DR-429 | D03 类签核：模板列集/列序/逐列说明、同步上限与性能依据在 CONTRACT Gate 签核；不改 D03 已签核数值。 | PROPOSED→CONTRACT |
| DR-430 | layers{database:false,backend:true,frontend:true}、api_required=true；无新表/列/索引/迁移；Database 以 NOT_REQUIRED 复核。 | PROPOSED→CONTRACT |
| DR-431 | Network 解析语义：`/mask` 仅用于解析并落库剥离；`network` 列与 `/mask` 优先级为设计默认，交 CONTRACT 定稿。 | PROPOSED→CONTRACT |

## 3. Domain / Data Impact

无新对象/关系/状态；仅通过批量入口 CREATE 既有表。全部 CREATE，无 UPDATE/DELETE/RESTORE。

| 对象 | 关系 | 作用域 | 生命周期 | 依据 | 裁定 |
| --- | --- | --- | --- | --- | --- |
| 导入文件（派生） | 1..N 行 | 按行 Cluster | 请求内处理、不落库 | §24 | DR-403–408 |
| Resource（新增） | `(cluster,hostname)`→1 | 组内 cluster | CREATE | §4/§6/§7 | DR-414/416/419 |
| BareMetalDetail/VirtualMachineDetail | 随 Resource | Resource cluster | 随 Resource | §8/§9/§21 | DR-417 |
| Interface（新增） | `(resource,name)`→1 | Resource | CREATE，parent=null | §4.1/§10 | DR-413/417 |
| IPAddress（新增） | 每行→1，绑定导入 Interface | 同 Cluster | CREATE（手动语义） | §13.2/§14/§11.1 | DR-410–412/418 |
| Network（引用） | N:1 | `name`/`cidr` 同 Cluster 唯一 | 不创建/修改；软删=不存在；INACTIVE 阻止新增 IP | §11/§11.1/§13.2 | DR-409–411 |
| IPPool（读） | RESERVED 参与可分配集合 | Network | 不创建/修改 | §12 | DR-412 |
| Cluster/Host（引用） | 组 1:1 / VM N:1 | 同 Cluster | 不创建/修改 | §5/§9 | DR-411/421 |
| Audit/Activity | 每成功对象 1 条 CREATE；失败整批无 | 三对象 | 同事务 | §22 | DR-419 |

完整性复用清单：`uq_resources_cluster_id_hostname_key`、`uq_interfaces_resource_id_name`、`uq_ip_addresses_cluster_id_address`、`ck_ip_addresses_address_host`、`ck_ip_addresses_address_not_disabled`、`trg_ip_addresses_cidr_contains`、`trg_ip_addresses_interface_cluster`、FK `host_resource_id`、`uq_networks_cluster_id_name_key`、`excl_networks_cluster_id_cidr`、`ix_networks_cluster_id`。**无 Schema 变更**（交 Database NOT_REQUIRED 复核）。

## 4. Frontend / Backend Work

### Backend（true）
- `app/services/interface.py`：抽 `prepare_interface`/`stage_interface`（非提交，含 CREATE Audit）；`create_interface` 薄包装。
- `app/services/ip_address.py`：抽非提交核心 + 可选 `interface_id`；`create_ip_address` 薄包装；复用 `resolve_network`/`_lock_network`/`ip_capacity`/`_derive_ip_pool_id`/`_validate_interface`。
- `app/services/resource_interface_ip_import.py`（新）：模板定义、CSV/xlsx 解析与表头匹配（复用 F014 原语）、Network 解析器、逐行校验与组内合并一致化、文件内重复检测、按资源组 SAVEPOINT 写入编排、DB 约束归因。
- `app/schemas/import_network.py`（新）或扩展 `schemas/imports.py`：请求/响应模型（RowError 复用 F014 形状）。
- `app/api/v1/imports.py`：新增三路由，挂现有 `imports.router`。
- `config.py`/`errors.py`/依赖：**不新增**。
- `resource.py`：复用 `prepare_resource`/`stage_resource`/`validate_*`。

### Frontend（true）
- `src/api/imports.ts`：新增 F023 函数/类型（模板 key、列 `applies_to`、复用 `describeImportError`）。
- `src/components/ResourceInterfaceIpImportPanel.tsx`（或扩展现有面板）：格式选择、模板查看/下载（26 列表头）、预校验错误表（行号/字段/原因/关联行，四态）、确认导入（0 错误且指纹一致）、写入整批失败提示（明确整批回滚）；无部分成功 UI。
- `src/components/importForm.ts`（或新纯逻辑模块）：本地快速反馈与指纹；类型扩展。

## 5. Contract 草案与状态

- api_required=true；独立 `docs/api/F023.md`；**当前 BLOCKED（待 CONTRACT Gate 定稿 READY）**。
- 端点：validate / write / templates。
- 复用 F014：错误信封与 `RowError`（F014 §1.2）、4 个 `IMPORT_*` 码与 413/422、权限 `IMPORT`/`READ`（F014 §1.1 + F002 §3）、上限值（F014 §10）、行号约定（F014 DR-194）、解析库（F014 §7/DR-207）。
- F023 需定稿：第三套模板列集/逐列说明（DR-406/407/427）、Network 解析优先级与 `/mask`（DR-409/410/431）、组内合并一致性（DR-415）、DB 约束归因（DR-422）。

## 6. Test Work（映射 A1–A10 / T64–T72）
| 验收 | 判据 | 层级 |
| --- | --- | --- |
| A1/T64 | 多节点多行→1 Resource + eth0 + IP 且绑定 | 真 PG |
| A2/T65 | IP 属正确 Network 同 Cluster；越界/跨 Cluster 整批失败 | 真 PG |
| A3/T66 | hostname 合并、同接口多 IP 去重 | 真 PG |
| A4/T67 | 重复/非法行含行号/字段/原因 | 真 PG |
| A5/T68 | 任一行失败整批回滚（各表+audit 行数不变） | 真 PG（必须） |
| A6/T69 | 预校验后状态变化写入失败不覆盖 | 真 PG |
| A7/T70 | VM Host 必须批外已存在；不隐式创建 | 真 PG |
| A8/T71 | 导入与 API 唯一性结果一致 | 真 PG + 服务层单测 |
| A9/T72 | 权限/列序/超限 403/422/413 | 真 PG + API |
| A10 | F014 既有 BM/VM 模板与行为无回归 | 回归套件 |
| Network 解析 | 名称/CIDR/mask/INACTIVE/软删 | 真 PG + 纯逻辑 |
| 并发 | 重叠 hostname/IP 仅一个成功、无残留 | 真 PG 并发 |
| 组内一致性 | 不同值→行错误+related_row | 纯逻辑+真 PG |
| 前端 / 人工浏览器 | 面板/错误表/四态/端到端 | 前端 + 人工 |

## 7. 决策、风险与 Implementation Layers

CONFIRMED：DR-401/402/404/405/408/409/411/412/413/414/416/417/418/419/420/421/422/424/425/428。
PROPOSED→CONTRACT：DR-403/406/407/410/415/423/426/427/429/430/431。

风险：合并/一致性语义歧义（CONTRACT 定稿+测试覆盖）；`/mask` 语义（精确 CIDR 匹配）；BM/VM 混排（PROPOSED）；`create_interface`/`create_ip_address` 重构回归（薄包装+回归套件）；导入创建即绑定（快照含 interface_id+触发器兜底）；预校验→写入窗口（重校验+唯一兜底+回滚）；5000 行性能（TEST 证据）。

```yaml
layers: {database: false, backend: true, frontend: true}
api_required: true
```

## 8. 需 Database 角色裁决（非阻塞，DATABASE Gate）
1. Network 解析（CIDR 精确相等 / `name_key` / `/mask` 匹配）能否由既有 `ix_networks_cluster_id` / `uq_networks_cluster_id_name_key` / `excl_networks_cluster_id_cidr` 承载，或需新索引（预期 NOT_REQUIRED）。
2. IP 创建并发锁序与 `_lock_network` 死锁风险。
3. `trg_ip_addresses_*` 在 SAVEPOINT 内归因可行性（`diag.constraint_name`）。
4. `database=false` 的 NOT_REQUIRED 复核。

## 9. 验证策略与不可验证项
验证：真 PG（原子回滚/并发/唯一性/边界/Network 解析/VM Host/再校验）；纯逻辑单测（解析/合并/归因）；API 权限/列/上限；F014 与 F007/F010 回归；前端/人工浏览器；性能基线（CONTRACT 义务）。
不可验证：5000 行性能证据待 TEST；人工浏览器受环境限制如实标注；本报告未执行测试。

## 10. 结论
DR-401–DR-431 覆盖端点/权限、统一宽模板、Network 解析、分组/合并、staging 重构、单事务+SAVEPOINT、再校验、并发兜底、约束归因、上限/错误码复用、F014 兼容、前端与数据层。无 Blocking；§8 为 Database 非阻塞裁决项。`READY FOR DESIGN`。

GIT: NONE
---

## 11. DATABASE Gate 复核结果（database=NOT_REQUIRED）

来源：`docs/database/f023-import.md`（Database，NOT_REQUIRED）。
- §8.1 Network 解析可由既有 `uq_networks_cluster_id_name_key` / `ix_networks_cluster_id` / `excl_networks_cluster_id_cidr` 承载，**不新增索引**。
- §8.2 **F023-DB-01（MEDIUM）**：跨批次存在 `40P01` 死锁窗口；CONTRACT/Backend 须定稿确定性锁序（写入前按稳定键升序、在 SAVEPOINT 之外一次性获取全部 `networks`/Host 行锁；捕获 40P01 整批回滚、可重试、不静默重试）。
- §8.3 **F023-DB-02（LOW）**：`diag.constraint_name` 仅对 UNIQUE/CHECK/FK；`fn/trg_ip_addresses_cidr_contains`/`_cluster_consistent`/`_interface_cluster` 用 `RAISE EXCEPTION` 不设 `constraint_name`，**DR-422 须订正**为按 RAISE 消息/SQLSTATE `restrict_violation` 归因（复用 `ip_address.py::_translate_integrity_error` 文本分支）。
- §8.4 `layers.database=false` / NOT_REQUIRED 成立：无新表/列/约束/触发器/索引/迁移。
- §8.3 结论：SAVEPOINT 内触发器抛错可捕获回滚、不污染外层事务。

CONTRACT Gate 须吸收 F023-DB-01/02 后定稿 `docs/api/F023.md`。
