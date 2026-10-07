# F006 虚拟机登记 — PRODUCT 阶段报告

- **Feature**：F006 虚拟机登记（FEATURE，P0，M3 虚拟化与接口，deps [F004]）
- **阶段**：PRODUCT；**结论**：`READY FOR ARCHITECT`（2026-10-09）
- **依据**：requirements-v3.md revision 3（§4、§4.1、§6、§7、§8、§9、§18、§21、§22、§23、§26、§27、§31 T08/T09/T19/T38/T39、§35.2 Q10-A/Q10-B、§35.3 D01）；plan_revision 4 F006 条目（用户 2026-10-06 批准）；d01-conventions.md v4。

## 1. 目标与范围

### 1.1 目标
在 F004 统一 Resource 基础上，为 resource_type=VIRTUAL_MACHINE 的 Resource 提供专有登记明细 VirtualMachineDetail，表达 VM 的分配容量与宿主关系，支持查询、维护、换宿主审计与正确删除保护。

### 1.2 本次范围（CONFIRMED，引用需求）
- 专有属性（§9）：host_resource_id, vcpu, memory_mb, disk_gb, hypervisor, metadata。公共属性在 Resource，遵循 F004 与 §6。
- 宿主关系（§4.1、§9）：VM 创建必须关联一个**未删除的 BARE_METAL Host**；VM 与 Host **必须同 Cluster**；host_resource_id 创建时必填、非空。
- 换宿主（§9、§22）：允许在**同 Cluster 内**更换 Host 并记录 Audit；只修改登记关系，不执行真实迁移。
- 删除保护（§9、§21）：存在未删除 VM 引用时 Host 不可删除（返回引用列表，不隐式级联）；VM 自身删除/恢复随 Resource。
- 容量语义（§9、§8、D01 §3）：容量参数可空；**不校验 VM 总 vCPU/内存是否超过 Host 容量**。
- 生命周期（§21）：VirtualMachineDetail 跟随 Resource，无独立删除/恢复入口，不作为阻止 Resource 删除的独立子对象。
- 字段契约：F006 负责将 VM 字段口径补齐 D01；不新增归一化键或业务名称唯一性。

### 1.3 使用者
EDITOR 登记维护；ADMIN 删除/恢复；VIEWER 查询（§23）。

## 2. 字段契约（VM，补齐 D01）

| 字段 | 类型 | 可空 | 创建必填 | 单位 | 合法值/语义 | 依据 |
| --- | --- | --- | --- | --- | --- | --- |
| host_resource_id | UUID | 否 | 是 | — | 引用存在、未软删、resource_type=BARE_METAL 且与 VM 同 Cluster；更新省略=保持，显式 null→422 | §4.1、§9、§27 |
| vcpu | int | 是 | 否 | 个数 | 正整数或 null | §9、§8、D01 §3 |
| memory_mb | int | 是 | 否 | MiB | 正整数或 null；1 GiB=1024 MiB；未知 null 不以 0 代替 | §9、§8、D01 §3 |
| disk_gb | int | 是 | 否 | GiB | 非负整数或 null；0=明确无磁盘，与未知 null 可区分 | §9、§8、D01 §3 |
| hypervisor | string | 是 | 否 | — | 描述性字段，无已确认枚举；trim 非空或 null，长度/格式由 D01 界定；不得据值推导行为 | §9、D01 §5 |
| metadata | object (JSONB) | 是 | 否 | — | 结构字段，整值替换；归属见 I-3（PROPOSED：Resource 公共 metadata） | §9、§6、D01 §4 |

补充口径：
- 可空与 PATCH（§4.1、D01 §4）：创建省略非必填→null；更新省略=保持；显式 null 仅清空 nullable；host_resource_id 显式 null→422；不可变/只读字段→422；VM 自身 cluster/resource_type 不可直接改（§6）。
- 单位一致（§8、T38、D01 §3）：memory_mb MiB、disk_gb GiB，不混用 MB/GB。
- 零值（§8、§9、T38）：disk_gb 允许 0（明确无）；vcpu/memory_mb 的 0 非法（正整数），未知一律 null。
- 无新增唯一性（§7、§27、D01 §5）：VM 依赖 Resource 的 (cluster_id, hostname_key) 部分唯一；VMDetail 不引入额外归一化键或唯一约束，仅指向 Host 的外键与宿主正确性约束。
- 无跨字段规则：容量字段各自独立可空，不做 vcpu×?、不做与 Host 容量比较。

## 3. 领域影响分析

| 对象 | 关系 | 作用域 | 生命周期 | 依据及版本 | 未决 |
| --- | --- | --- | --- | --- | --- |
| VirtualMachineDetail | 1:1 依附 Resource(VIRTUAL_MACHINE) | 随 Resource 的 Cluster | 随 Resource 创建/软删/恢复；无独立删除入口 | §9、§21（CONFIRMED） | 字段契约交 D01（I-1） |
| VM → Host | 多对一，host_resource_id 指向 BARE_METAL | Host 与 VM 同 Cluster | 可同 Cluster 换 Host 写 Audit；不真实迁移 | §9、§22、§27（CONFIRMED） | 宿主校验落地方式（架构/DB） |
| VM 引用 → Host 删除 | 存活引用阻止删除 | 同 Cluster | Host 删除前检查；VM 未删则拒并返回引用列表 | §9、§21（CONFIRMED） | 引用列表接口属 F004/F015 契约 |
| 全量 VM 名称唯一 | 无 | — | — | §4.1、§7（CONFIRMED） | 由 Resource.hostname 承载（F004） |

## 4. 必须遵守的已确认约束
- §6：resource_type ∈ {BARE_METAL, VIRTUAL_MACHINE}；创建后不可直接改 Cluster 或 resource_type。
- §9：VM 专有属性；容量可空与数值语义；宿主三条件（存在/未删/BARE_METAL）与同 Cluster；同 Cluster 换 Host 并审计；未删除 VM 引用阻止 Host 删除；不校验超额。
- §4.1：VM Host 创建必填；默认仅创建省略时生效；PATCH 省略=保持。
- §8/D01 §3：*_mb=MiB、*_gb=GiB，1 GiB=1024 MiB；未知 null 非 0。
- §21：明细跟随 Resource，无独立删除/恢复；不隐式级联；恢复重检依赖有效性。
- §22：换 Host 写 Audit（UPDATE 含 before/after）；Activity 全角色；不记敏感内容。
- §23：EDITOR 新增/修改/换 Host；VIEWER 只读；ADMIN 删除/恢复。
- §27：VM Host 类型与 Cluster 正确性由 DB+业务层共同保证，真实 PostgreSQL 验证。
- §4/D01 §1：内部关联用稳定 UUID。

## 5. 可观察验收标准

| # | 验收标准 | 映射 |
| --- | --- | --- |
| A1 | 创建 VM 时 host_resource_id 指向 VIRTUAL_MACHINE Resource，被拒（422） | §9、T08 |
| A2 | 创建 VM 时 Host 与 VM 不同 Cluster，被拒（422） | §9、T09 |
| A3 | 创建 VM 时省略/为空 host_resource_id，被拒（422） | §4.1、§9、T38 |
| A4 | 创建 VM 时 Host 不存在或已软删，被拒（422） | §9、§21、T19 |
| A5 | 创建 VM 时 Host 为未删除 BARE_METAL 且同 Cluster，成功 | §9 |
| A6 | 同 Cluster 换 Host 成功，Audit 记录 before/after host_resource_id；跨 Cluster 或指向软删 Host 的更换被拒 | §9、§22、T19 |
| A7 | 存在未删除 VM 引用时删除其 Host 被拒并返回引用列表；VM 软删后 Host 可删除 | §9、§21、T19、T23 |
| A8 | vcpu/memory_mb/disk_gb 省略或 null 保存 null，详情返回 null 不返回 0 | §9、T38 |
| A9 | vcpu=0 或负数被拒（422）；正整数接受；memory_mb 同规则 | §9、§8、T38 |
| A10 | memory_mb 以 MiB 存/展：1536 GiB→1572864，转换一致，不按 MB 解释 | §8、§9、T38、D01 §3 |
| A11 | disk_gb=0 接受并存 0，展示「明确无磁盘」，与未知 null 可区分；disk_gb 负数被拒 | §9、§8、T38 |
| A12 | VM 总 vCPU/内存超过其 Host 容量时，登记仍成功，不因超额被拒 | §9、T39 |
| A13 | VirtualMachineDetail 无独立删除/恢复入口；删除/恢复 Resource 时明细跟随，明细不阻止其自身 Resource 删除 | §21、T23 |
| A14 | 恢复 VM 时重检 Host 有效性；Host 仍被删除或标识被重用时恢复失败且不覆盖新对象 | §21、T24 |
| A15 | 权限：EDITOR 可创建/修改/换 Host；VIEWER 只读；删除/恢复限 ADMIN | §23、T25 |
| A16 | Resource Detail 中 VM 展示其 Host；BareMetal Detail 列出其 VM | §18 |
| A17 | DB 层对 Host 类型及 Cluster 一致性有兜底约束，并在真实 PostgreSQL 验证 | §27、T08、T09 |

## 6. 明确排除项（不宣称）
- 不修改 Resource 基础字段、hostname 唯一性与归一化（F004）。
- 不做 Interface/Network/IP/Service（F007–F012）。
- 不做容量超额校验或容量准入（§9 明确排除）。
- 不做 CSV/Excel 导入及 VM Host 引用列模板（F014/D03）。
- 不做列表/搜索/Dashboard/Cluster Detail 聚合（F013）；不做完整 Audit 查询页（F015）。
- 不做真实 VM 迁移、电源/运行状态、快照、逐盘建模；VM Role/Status 沿用 Resource 人工维护。
- 不做监控、调度、自动采集（§34）。

## 7. 依赖与未决问题

依赖（CONFIRMED）：F004（统一 Resource、hostname 唯一、软删/恢复、Audit、权限、DB 唯一约束）。F005 BareMetalDetail：VM 宿主为 BARE_METAL Resource，硬件明细本身非 F006 依赖，仅 §18 展示关联。

BLOCKING：无。

CONFIRMED：§9 全部；§4.1 Host 必填；§6 不可变字段；§8 单位；§21 生命周期；§22 换 Host 审计；§23 权限；§27 完整性；Q10-A/Q10-B。

PROPOSED/OPEN（非阻塞）：
- I-1（OPEN，D01）：d01-conventions.md 尚无 VM 字段小节。需补 vcpu/memory_mb 正整数上限、disk_gb 非负上限、hypervisor trim/长度口径，CONTRACT 签核。Owner：Architect。
- I-2（OPEN，产品待定）：hypervisor 无已确认枚举。基线按「无枚举、可空描述性字符串」处理；如需限定枚举属新业务规则，须用户裁定。Owner：Product/用户。
- I-3（PROPOSED）：metadata 归属 Resource 公共字段（与 F004/F005/D01 §4 一致），F006 不新增 VM 级 metadata 列。需 Architect/Database 在 CONTRACT 确认。Owner：Architect/用户。
- I-4（OPEN，D02）：换 Host 的并发/版本冲突语义与 Audit 同事务，按 D02 由 Architect 设计。

## 8. 交 Architect 的输入
1. 实体方案：VirtualMachineDetail 1:1 依附 Resource（PK=resource_id 或独立 UUID+唯一）；字段与 §2 一致；D01 §1。
2. 约束：host_resource_id NOT NULL 外键→Resource(id)；宿主正确性（未删+BARE_METAL+同 Cluster）的 DB 兜底；无新增业务唯一性。
3. 审计与生命周期：换 Host 作为 Resource UPDATE 写 Audit（before/after host_resource_id）；明细随 Resource；Host 删除前引用检查返回引用列表；恢复 VM 重检 Host。
4. API 暴露：VM 专有字段创建/更新/详情暴露方式（嵌套 vs 平铺），扩展 F004 契约；不新增绕过 Service Layer 的写路径。
5. D01 补齐：新增 VM 字段口径小节并纳入 CONTRACT 签核。
6. 待裁定项：I-2（hypervisor 是否枚举）、I-3（metadata 归属）。

## 9. 结论与下一步
无 Blocking Questions。**READY FOR ARCHITECT**。下一步 ARCHITECTURE：VirtualMachineDetail 方案、layers、api_required、宿主约束落地方式，并在 CONTRACT 签核 VM 字段契约（补齐 D01）与换 Host 审计口径；DATABASE 依 D01 签核 VM 表约束并记录真实 PostgreSQL 验证方案。