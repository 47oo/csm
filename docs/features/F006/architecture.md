# F006 虚拟机登记 — ARCHITECTURE 阶段报告

- **Task**：F006（FEATURE，P0，M3，deps [F004]）— Architect，Feature 设计模式
- **Status**：`READY FOR DESIGN`（2026-10-09；协调器核验后持久化）
- **Basis**：requirements-v3.md revision 3（§4、§4.1、§6、§8、§9、§18、§21、§22、§23、§27、§31 T08/T09/T19/T38/T39、§35.2/§35.3）；docs/features/F006/product.md（A1–A17、I-1–I-4）；docs/api/F004.md v2；docs/database/f004-resource.md v1、f005-bare-metal.md v1；d01-conventions.md v4；plan_revision 4 F006。
- **结论属性**：设计输入，交 DATABASE/TEST_DESIGN；Contract 草案供 CONTRACT 定稿（扩展 F004→v3）。

## 1. 方案摘要

### 1.1 VirtualMachineDetail 实体（1:1 依附 Resource）

`VirtualMachineDetail` 是 `resource_type=VIRTUAL_MACHINE` 的 1:1 从属明细，**PK=外键等于 Resource.id**（同 F005 bare_metal_details）。

| 字段 | 类型 | 空 | 创建默认 | 单位 | 合法值/语义 |
| --- | --- | --- | --- | --- | --- |
| resource_id | UUID PK/FK→resources | 否 | — | — | 每 VM 至多一行 |
| host_resource_id | UUID FK→resources | **否** | — | — | 引用存在、未软删、BARE_METAL 且与 VM 同 Cluster；创建必填 |
| vcpu | int | 是 | null | 个 | 正整数或 null（1..2147483647）；0/负非法 |
| memory_mb | int | 是 | null | **MiB** | 正整数或 null（1..2147483647）；1 GiB=1024 MiB；未知 null 不以 0 代替 |
| disk_gb | int | 是 | null | **GiB** | 非负整数或 null（0..2147483647）；**0=明确无磁盘**，与未知 null 可区分 |
| hypervisor | string | 是 | null | — | trim 后非空或 null，≤255 code point；**一期无枚举**；不得据值推导行为 |
| (metadata) | — | — | — | — | **不建 VM 级列**（I-3 PROPOSED：归 Resource.metadata） |

要点：host_resource_id 非空（API+DB 强制）；容量三字段各自独立可空、无跨字段规则、不与 Host 容量比较（§9/T39）；结构化列；不引入归一化键/额外业务唯一性；detail **不设 deleted_at/version/时间戳**（同 DR-54）。

### 1.2 生命周期与宿主关系
- VM 与 Host 多对一；Host 必须未删除 BARE_METAL 且同 Cluster。
- 同 Cluster 内可换 Host，写 Audit（UPDATE 含 before/after host_resource_id）；不真实迁移。
- 有未删除 VM 引用时 Host 不可删除，返回引用列表；VM 软删后 Host 可删。
- detail 无独立删除/恢复入口，随 Resource；恢复 VM 重检 Host 有效性。

## 2. API 暴露方式（DR-59，PROPOSED→CONTRACT）

VM 专有字段作为 Resource create/PATCH 的**嵌套对象 `virtual_machine`** + 响应嵌套 `virtual_machine`；**不新增独立端点**（对齐 F005 hardware）。纳入 docs/api/F004.md 增量（→v3），不新建 F006 Contract。

- POST：`resource_type=VIRTUAL_MACHINE` 时 `virtual_machine` 必须出现、`host_resource_id` 必填非 null；`vcpu/memory_mb/disk_gb/hypervisor` 可选省略/null→null；未知键→422；**不接收 metadata**。`BARE_METAL` 携带 `virtual_machine`（含显式 null）→ **422**（镜像 F005）。
- PATCH：仅 VM 合法；BARE_METAL 携带→422。子字段 exclude_unset（省略=保持；host_resource_id 显式 null→422；容量/hypervisor 显式 null=清空；整体 null/非对象/未知键→422）。改 host_resource_id=换 Host（同 Cluster、未软删 BARE_METAL），写 UPDATE Audit。
- 响应：`virtual_machine` = object（VM）| null（BARE_METAL）；对象含 host_resource_id、host{id,hostname}（支持 §18，精确形态交 CONTRACT）、vcpu、memory_mb、disk_gb、hypervisor；无独立 metadata 键。
- **列表过滤（DR-67）**：`GET /resources` 增可选 `host_resource_id=<UUID>`（非 UUID→422；不存在→空），配 `type=VIRTUAL_MACHINE` 支持 BareMetal Detail 列出其 VM；不新增端点。
- 字段路径：`virtual_machine.host_resource_id`/`vcpu`/`memory_mb`/`disk_gb`/`hypervisor`。
- 互斥：BARE_METAL↔hardware、VIRTUAL_MACHINE↔virtual_machine；另一方出现（含显式 null）→422；两对象不共存。
- 校验顺序建议：POST 401→403→body 形状/互斥(422)→cluster(422)→Host 校验(422)→hostname 唯一(409)→写 resource+detail 同事务→Audit→201；PATCH 401→403→body(422)→可见性(404)→Host 校验若变更(422)→version(409)→hostname 唯一(409)→写→Audit→200（交 CONTRACT 固定）。

## 3. 宿主校验（DR-60，CONFIRMED §9/§27）

对 host_resource_id 指向的 Resource，须同时满足：存在、未软删、resource_type=BARE_METAL、与 VM 同 Cluster。失败统一 **422**，`fields[].field="virtual_machine.host_resource_id"`（不区分码，仅 message）。创建与换 Host 走同一校验函数。VM 的 cluster/resource_type 不可改（F004 触发器兜底）。**无容量超额校验**（§9/A12/T39）。

## 4. Host 引用删除保护（DR-62，CONFIRMED §21）

沿用 F003/F004 引用检查注册表（DR-30）。F006 为 object_type="resource" 注册**首个 resource←VM 反向检查器**，收窄 F004 `DELETE /resources/{id}`。删除 Host 时若存在未删除 VM → **409 CONFLICT**，details.reason="reference_exists"，references=[{object_type:"resource",object_id:<vm-uuid>,label:<vm-hostname>}]；VM 软删后放行。detail 自身不作为阻止 VM 删除的独立子对象。

## 5. 生命周期（DR-65，CONFIRMED §21）

detail 无 deleted_at/version/独立端点；乐观锁复用 resources.version；软删不物理删 detail；恢复重检 Host。**恢复 VM（DR-63）**：注册 object_type="resource" dependency checker；若 host_resource_id 指向的 Resource 已软删/缺失→**409 CONFLICT**，details.reason="dependency_deleted"，conflicts=[{object_type:"resource",object_id:<host-uuid>}]，不覆盖新对象（标识重用场景天然不覆盖）。换 Host 审计 before/after host_resource_id；CREATE/DELETE/RESTORE 随 Resource 四 action 同事务、回滚不留痕。

## 6. 数据库影响（交 DATABASE）

表 `virtual_machine_details`：
- resource_id UUID PK `pk_virtual_machine_details` + FK `fk_virtual_machine_details_resource_id_resources`→resources **ON DELETE CASCADE**。
- host_resource_id UUID **NOT NULL** + FK `fk_virtual_machine_details_host_resource_id_resources`→resources **ON DELETE RESTRICT** + 索引 `ix_virtual_machine_details_host_resource_id`。
- vcpu/memory_mb integer NULL CHECK 1..2147483647；disk_gb integer NULL CHECK 0..2147483647；hypervisor varchar(255) NULL + trim/非空 backstop CHECK。
- metadata 列**不建**（I-3 归 Resource；若裁定为 VM 级则加 metadata jsonb NOT NULL DEFAULT '{}' + object CHECK）。
- FK 语义：resource_id CASCADE（1:1 从属）；host_resource_id RESTRICT（Host 是被引用独立对象，物理删除阻止；软删保护由应用检查器承担）。
- **宿主正确性双触发器（DR-66）**：type_match（resource_id 须为 VIRTUAL_MACHINE）；host_valid（host_resource_id 须指未软删 BARE_METAL 且 host.cluster_id==vm.cluster_id）。写时校验；删除时保护由应用检查器。DATABASE 可评估额外 resources 软删守卫触发器（默认不强制）。
- 迁移 `0006_virtual_machine_details`，down_revision="0005_bare_metal_details"；up 建表→CHECK/PK/FK→索引→触发器/函数；down 逆序；单一 head、对称可逆、真库 up/down/up。
- **回填（DR-68，交 DATABASE 裁定）**：host_resource_id NOT NULL 且 F004 允许创建无 Host 的 VM → **无安全回填值**。PROPOSED：不合成 detail 行 + 前置守卫（若存在未删除 VIRTUAL_MACHINE Resource 则 upgrade 明确中止并诊断），不静默丢弃/编造；V3 一期无生产数据可干净升级。备选（不推荐）：host_resource_id 设 NULL 削弱 §9 保证。

## 7. D01 补齐（→v5，交 CONTRACT）

新增 §5.5 VirtualMachine 字段口径；§3 追加 VM 数值/单位引用；§5.2 追加 hypervisor 长度 255。版本 v4→v5，签核者 Architect（CONTRACT Gate）。§5.5 内容：vcpu/memory_mb 正整数或 null（1..2147483647）、disk_gb 非负或 null（0..2147483647，0=明确无磁盘）；未知存 null 绝不写 0；memory_mb MiB、disk_gb GiB 原样存储不换算；host_resource_id 非空、引用未删除 BARE_METAL 且同 Cluster；hypervisor trim→非空→禁 Cc/Cf→≤255，空/纯空白 422 不转 null，无枚举、不据值推导；无跨字段规则；metadata 归 Resource；镜像 DB/API 引用。

## 8. 验证策略（A1–A17，真实 PG）

A1 host 非 BARE_METAL→422+DB 触发器拒（T08）；A2 跨 Cluster→422+触发器拒（T09）；A3 省略/空 host→422+NOT NULL；A4 host 不存在/软删→422；A5 合法→201/detail 1:1；A6 换 Host→200+Audit before/after，跨 Cluster/软删→422（T19）；A7 删有未删 VM 的 Host→409 reference_exists；VM 软删后可删（T19/T23）；A8 容量省略/null→null 非 0；A9 vcpu/memory_mb 0/负→422（T38）；A10 memory_mb MiB 1536 GiB→1572864（T38）；A11 disk_gb=0 接受且区分「无磁盘」，负→422（T38）；A12 超 Host 容量登记成功（T39）；A13 无独立删除/恢复入口（T23）；A14 恢复重检 Host→409 dependency_deleted 不覆盖（T24）；A15 权限矩阵（T25）；A16 VM 展示 Host + BareMetal Detail 列 VM（响应 host + host_resource_id 过滤）；A17 DB 类型+Cluster 兜底（T08/T09）。
补充 DB/集成：0006 真库 up/down/up、单一 head；回填守卫断言；触发器四负例；FK RESTRICT/CASCADE；CHECK 边界；hypervisor 空/纯空白/255/256；索引存在；PATCH exclude_unset、host 显式 null→422、整体 null→422；换 Host 乐观锁并发；审计回滚不留痕；互斥 422 对称；resource←VM 引用检查端到端。

## 9. 裁定 I-2 / I-3（PROPOSED，不新增未确认业务规则）

- **I-2 hypervisor**：PROPOSED 不设枚举、可空描述性字符串（§9 未给枚举；新增枚举属新业务规则，须用户裁定）。口径 trim 非空或 null、≤255、区分大小写。若用户要求枚举走变更控制，不阻塞。
- **I-3 metadata**：PROPOSED 归 Resource 公共 metadata，F006 不新增 VM 级列（VM 即 Resource，resources.metadata 已承载，避免两套语义）。备选：加 virtual_machine_details.metadata + object CHECK 并在嵌套对象暴露；交 CONTRACT 确认，不阻塞。

## 10. Implementation Layers 与分工

layers.database=true、backend=true、frontend=true；api_required=true（扩展 F004→v3，不新建 F006 Contract）。
- Database：docs/database/f006-virtual-machine.md（表/约束/索引/双触发器/FK 语义/迁移 0006/回填守卫裁定）。
- Backend：models/virtual_machine_detail.py；schemas 增 VirtualMachineIn/Patch/Out、build_virtual_machine_out；services/resource.py 增 validate_virtual_machine、_attach_virtual_machine、快照增 virtual_machine、注册 resource←VM reference checker 与 host dependency checker；audit.py 白名单扩 virtual_machine；api/v1/resources.py 组装/传参+列表 host_resource_id 过滤；迁移 0006 落地。
- Frontend：Resource 创建/编辑表单（VM 显示 host 选择器+容量/hypervisor；单位 MiB/GiB、未知「—」非 0、disk_gb=0「明确无磁盘」）；Detail 的 Virtual Machines 区域与 VM 的 Host 展示；host_resource_id 列表调用；422 点路径映射。
- Contract：F004 v3 增量冻结嵌套键名、响应 host 形态、列表过滤、错误路径、CONFLICT details；签核 D01 v5 §5.5。

## 11. 技术决策（DR-57–DR-70）

| ID | 决策 | 状态 |
| --- | --- | --- |
| DR-57 | VirtualMachineDetail 1:1（resource_id PK/FK CASCADE）；迁移 0006 | DESIGN |
| DR-58 | host_resource_id UUID NOT NULL + FK RESTRICT + 索引 | DESIGN（§9/§27） |
| DR-59 | VM 字段以 virtual_machine 嵌套于 Resource；不新增端点；响应含 host{id,hostname} | PROPOSED→CONTRACT |
| DR-60 | 宿主校验：存在+未软删+BARE_METAL+同 Cluster，违约 422 | CONFIRMED（§9/§27） |
| DR-61 | 换 Host 经 PATCH；同 Cluster；写 UPDATE Audit；乐观锁 | CONFIRMED（§9/§22） |
| DR-62 | Host 删除保护：resource←未删 VM 检查器→409 reference_exists+references；VM 软删放行 | CONFIRMED（§21） |
| DR-63 | 恢复 VM 重检 Host：软删/缺失→409 dependency_deleted，不覆盖 | CONFIRMED（§21/T24） |
| DR-64 | 数值 CHECK + hypervisor trim/非空/≤255（D01 v5 §5.5） | DESIGN |
| DR-65 | detail 无 deleted_at/version/时间戳/独立端点 | CONFIRMED（§21）+DESIGN |
| DR-66 | DB 宿主正确性双触发器（type_match + host_valid） | DESIGN（§27） |
| DR-67 | 列表增 host_resource_id 过滤；不新增端点 | PROPOSED→CONTRACT |
| DR-68 | 迁移 0006 对称可逆；host 无安全回填→前置守卫 | PROPOSED→DATABASE |
| DR-69 | metadata 归 Resource（I-3）；不新增 VM 级列 | PROPOSED→CONTRACT |
| DR-70 | 扩展 F004 Contract→v3；对齐 F005 DR-56 | PROPOSED→CONTRACT |

## 12. 风险与待核对项

交 DATABASE：0006 回填守卫与可逆性；双触发器与 restrict_violation；FK RESTRICT vs CASCADE；host_resource_id 索引与列表过滤/引用检查性能；字符串长度与 Cc/Cf backstop；metadata 列是否新增（I-3）；是否加 resources 软删守卫触发器。
交 TEST_DESIGN：A1–A17；DB/触发/FK/CHECK/迁移/并发/审计回滚/互斥；resource←VM 检查端到端；A14 恢复重检；T08/T09/T19/T38/T39 的 F006 子集。
交 CONTRACT：嵌套键名、响应 host 形态、列表过滤命名、422 字段路径与顺序、CONFLICT details、I-2/I-3 固定、D01 v5 §5.5。
跨 Feature：F004 DELETE /resources/{id} 行为随 F006 收窄；F014 VM 导入走同一 Service Layer 校验与 Host 已存在规则；F013 复用 host_resource_id。
风险：F004 允许无 Host 的 VM 与 F006 后置不变量冲突 → 迁移守卫+新路径强制 Host 化解。

## 13. 结论与下一步

Status **READY FOR DESIGN**，无 Blocking Questions。下一步：DATABASE 出 docs/database/f006-virtual-machine.md；TEST_DESIGN 核对 A1–A17；CONTRACT 定稿 F004 v3 + D01 v5 §5.5、固定 DR-59/67/69/70 与 I-2/I-3；完成后出 READY FOR IMPLEMENTATION。
## 14. 最终设计定稿（CONTRACT Gate）

- **Status**：`READY FOR IMPLEMENTATION`（2026-10-09）
- **签核**：Architect；Contract docs/api/F004.md v3；D01 d01-conventions.md v5（§3/§5.2/§5.5）
- **核对版本**：database/f006-virtual-machine.md v1（DB-D53–D63）；test-report.md TD-1（§8 全部 12 项 OPEN 由本 Contract 闭合，TD-2 由 Tester 发布）。
- **裁定固定**：DR-59（virtual_machine 嵌套，不新增端点）、DR-67（列表 host_resource_id 过滤）、DR-69（metadata 归 Resource，virtual_machine 不含独立 metadata 键）、DR-70（扩展 F004→v3）；I-2 hypervisor 无枚举固定；**DR-71（I-3 MEDIUM）Host 软删并发窗口采用应用层 `SELECT ... FOR UPDATE` 行级串行化，不加 DB 触发器（遵从 DB-D59）**：创建/换 Host 事务在读取宿主前锁目标 Host 行；Host 软删路径先锁 Host 行再跑引用检查（检查器只普通 SELECT，不锁 VM 行，避免死锁）；任一方先提交后另一方读到已提交结果（Host 先→创建/换 Host 422；VM 先→Host 软删 409 reference_exists）。属技术机制，Architect 在已批准边界内专业签核，非业务规则变更。
- **实现前置**：Backend 实现须落实 DR-71 锁序；Tester 在 TEST 执行前发布 TD-2（引用 F004 v3 / D01 v5 / DB v1）。
- **实现分工**：Backend（model/migration 0006、VirtualMachineIn/Patch/Out、validate_virtual_machine、_attach_virtual_machine、resource←VM 引用检查器、VM restore 依赖检查器、audit 白名单扩 virtual_machine、列表 host_resource_id 过滤、DR-71 锁序）；Frontend（VM 表单 host 选择器+容量/hypervisor、Detail Virtual Machines 区域与 Host 展示、BareMetal 列 VM、422 点路径映射）。
- **边界（不宣称）**：容量超额校验明确不做（§9）；导入 F014；列表/Dashboard F013；完整 T08/T09/T19/T23/T24/T25/T38/T39 与 §32 上线验收不在本 Feature。
