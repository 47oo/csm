# CSM V1 领域模型冲突澄清 — Product Handoff

> Status: **RESOLVED**（3 项 Blocking 问题已由用户裁定，产品文档已同步）
> Document Type: Product Handoff（澄清轮次记录）
> Author Role: product-manager
> Round: DEC-001 ~ DEC-008 澄清
> Baseline: `docs/product/requirements.md`（CONFIRMED BASELINE）
>
> ---
>
> ## 用户裁定结果（2026-09-15）
>
> | 问题 | 裁定 | 已落入 |
> |---|---|---|
> | **Q-001**（DEC-003）Service 关系模型 | **C** — Service 必选绑定运行载体（BareMetal / VirtualMachine / Container，可多个）；Service 与 Cluster 关联由载体归属推导 | `requirements.md` 新增 **R-SVC-005 / R-SVC-006**，§15 新增 Service→载体关系 |
> | **Q-002**（DEC-006）多资源状态模型 | **B** — V1 **仅 BareMetal 有状态**；VM / Container / Service / NetworkInterface / IPAddress 不设状态 | `domain-model.md` §7 重写（§7.1 有状态仅 BareMetal，§7.2 无状态资源；原 §7.2/§7.3 删除） |
> | **Q-003**（DEC-007）Cluster 名称 `/` 规则 | **A** — 保留为 V1 规则 | `requirements.md` 新增 **R-CLUSTER-005** |
> | **Rack**（DEC-002） | **Rack-1 — 从 V1 删除** Rack / U 位 | `requirements.md` §13 改为「V1 不管理 Rack 与 U 位」，原 **R-RACK-001 ~ R-RACK-004 全部删除**；§2 / §5 / §16 / §18 / §21 / §25 / §26 同步 |
> | **S-2**（Service 载体范围） | **F007 Container 由 P2 提升为 P1**，Service 载体完整支持三类 | `project-plan.yaml` |
> | **D-1** | 同意同步 `domain-model.md` | 已完成（DataCenter 一并移除） |
> | **D-2** | 同意关闭 OPEN-006 为「已确认排除」 | `requirements.md` §29 OPEN-006 已标记「已关闭」 |
>
> ### 裁定后的项目级决策状态
>
> - **RESOLVED**：DEC-001、DEC-002、DEC-003、DEC-006、DEC-007
> - **DEFERRED_TO_FEATURE**：DEC-004（→ F006 Product 阶段）、DEC-005（→ F007 Product 阶段）
> - **TRANSFERRED_TO_ARCHITECT**：DEC-008（统一 status 建模属架构/数据库问题）
> - **OPEN**：DEC-009 ~ DEC-014（技术栈、数据库、全局标识与寻址、逻辑删除持久化、认证范围、API 契约）
>
> > 以下为澄清当时的原始分析内容，保留作为决策依据。

---

# 原始分析：CSM V1 领域模型冲突澄清（DEC-001 ~ DEC-008）

---

## Problem

`/project` 规划已完成 15 个 Feature，但 8 项产品冲突（DEC-001 ~ DEC-008）未决，导致 F001 ~ F011 共 9 个 Feature 处于 DRAFT/BLOCKED。

冲突根源是两份产品文档之间存在**未标记状态差异**：

- `docs/product/requirements.md` 自声明 `Status: CONFIRMED BASELINE`，是 V1 需求基线；
- `docs/product/domain-model.md` **无状态标记**，仍包含 DataCenter、Service 载体绑定、多类资源状态枚举、Cluster 名称 `/` 规则等内容。

按 `AGENTS.md` §3 优先级第 2 条，两者同属「已确认产品文档」层级，但 `requirements.md` 明确自声明为确认基线，`domain-model.md` 未声明；叠加用户已明确的 V1 删除 DataCenter 指令（优先级第 1 条），可判定 `requirements.md` 为 V1 基线。

---

## Confirmed Requirements

以下结论**仅凭现有已确认文档 + 用户明确指令**即可确立，不需要新增产品决策。

### CR-1（对应 DEC-001）V1 不含 DataCenter

- **冲突事实**：
  - `requirements.md` §6：CSM V1 不建立 DataCenter 资源层级，不得自动创建 `DataCenter → Cluster`；Cluster 直接作为基础设施资源顶层管理对象；如需机房/园区模型应作为新需求重新设计。§5 Taxonomy 中 Infrastructure Resource 仅含 Cluster / BareMetal / Rack。§23 明确将「DataCenter 层」列入 V1 不做清单。
  - `domain-model.md` §3 Taxonomy 含 DataCenter；§5.1 规定「集群绑定到数据中心（必选）」；§6 关系图含 `集群 → 数据中心`（必选）；§7.4 将数据中心列为无状态资源；§8 规定数据中心名称全局唯一；§9 将数据中心列为父对象。
- **裁定结果**：V1 **不含** DataCenter。Cluster 是顶层基础设施资源，`Cluster → DataCenter` 绑定关系在 V1 不存在。
- **依据**：用户明确指令（优先级 1）+ `requirements.md` §6/§5/§23（CONFIRMED BASELINE，优先级 2）。
- **附带结论（文档性，非产品决策）**：`domain-model.md` §3/§5.1/§6/§7.4/§8/§9 中的 DataCenter 内容为 **Legacy**，应按 `AGENTS.md` §4 同步修正。

### CR-2（对应 DEC-002）Rack / U 位属于 V1 已确认范围

- **冲突事实**：
  - `requirements.md` §13 定义 R-RACK-001 ~ R-RACK-004：支持登记 Rack；BareMetal 可记录 Rack 与 U Position；**同一 Rack 内 U 位冲突必须禁止保存（硬阻断，不允许仅 Warning）**；多 U 服务器的 U 范围表达交 Architecture/Database 决定。§5 Taxonomy 的 Infrastructure Resource 明确包含 Rack。§26 能力范围明确包含「Rack / U 位管理」。
  - `domain-model.md` §3 Taxonomy、§6 关系、§8 唯一性规则**完全不含** Rack / U 位。
- **裁定结果**：Rack 属于 V1 已确认领域对象；U 位冲突硬阻断属于 V1 已确认业务规则。`domain-model.md` 的缺失属于**文档未同步**，不是产品范围冲突，也不构成「待确认」。
- **依据**：`requirements.md` §5/§13/§26（CONFIRMED BASELINE）。

### CR-3 V1 明确不包含虚拟化/容器运行时集成

`requirements.md` R-VM-002（不要求自动接入 VMware/PVE/OpenStack）、§10（不得自动引入 Kubernetes/Docker API/Container Runtime 自动发现）、§23（V1 不做清单含自动资产发现 / VMware/PVE/OpenStack 自动同步 / Kubernetes 自动同步 / Slurm 集成）三项互相印证，已无未确认空间。

**因此建议（非本文件自行生效）**：`requirements.md` §29 的 OPEN-006 应从「未确认项」移入「已确认排除」。该文档状态变更需用户批准。

### CR-4 本次不新增任何状态、关系、唯一性规则

除 CR-1 / CR-2 / CR-3 外，本 Handoff **不产生**任何新的业务规则。所有仍然存在的冲突一律进入 Open Questions，不写成 CONFIRMED。

---

## Confirmed Domain Rules

| 规则 | 来源 |
|---|---|
| Cluster 名称全局唯一，大小写敏感 | `requirements.md` §7 R-CLUSTER-002、§22；`domain-model.md` §8 |
| Cluster 不设置统一运行状态 | `requirements.md` §7 R-CLUSTER-003；`domain-model.md` §7.4 |
| 每个 BareMetal 必属于一个 Cluster | `requirements.md` §8 R-BM-001；`domain-model.md` §5.2/§6 |
| 同 Cluster 内 hostname 唯一，大小写敏感 | `requirements.md` §8 R-BM-002、§22；`domain-model.md` §8 |
| BareMetal 状态 `IDLE/ALLOC/DOWN/UNKNOWN`，默认 `IDLE`，不得为 NULL，人工维护 | `requirements.md` §8 R-BM-003~006；`domain-model.md` §7.1/§7.5 |
| 同 Cluster 内 IP 唯一，跨 Cluster 可重复，暂不考虑 VRF | `requirements.md` §12 R-IP-001~003；`domain-model.md` §5.7/§8 |
| 逻辑删除、不物理删除、不级联、无 Undelete、父有活跃子不可删、已删不占唯一性 | `requirements.md` §17；`domain-model.md` §9 |
| 同一 Rack 内 U 位冲突硬阻断 | `requirements.md` §13 R-RACK-003 |
| Taxonomy 不产生数据库继承，禁止 EAV / 通用 `resources` 表 / STI / JSONB 万能模型 | `requirements.md` §4/§24 |
| 不同资源**可以**拥有独立数据模型、属性、状态、生命周期 | `requirements.md` §4 |

> **注意**：`domain-model.md` §6 中「以上绑定全部为必选」与其他章节一致性不足，且其权威性低于 `requirements.md`，不作为已确认规则使用（见 DEC-003/004/005/008）。

---

## Scope

### 本次包含

- DEC-001 ~ DEC-008 逐项冲突事实、可裁定性判定、影响范围。
- 对 `requirements.md` §29 OPEN-001 ~ OPEN-006 的重新判定。
- 可直接驱动 Feature Product 阶段的阻塞问题（互斥选项）与非阻塞确认事项。

### 本次明确不包含

- 不实现任何代码，不设计数据库表/字段、不定义 API、不做技术选型。
- 不裁定 DEC-009 ~ DEC-014（技术栈、数据库、标识/寻址、逻辑删除持久化、认证实现、API 契约），它们不是产品决策。
- 不新增资源类型、不新增关系、不新增状态枚举、不修改任何已确认唯一性规则。

### 本次未涉及

- 导出、高级筛选、审计历史、资源变更历史视图。
- 数据中心以外的其他物理位置模型（园区、机房、楼层、房间、机柜布局图）。
- Rack 容量规划、Rack 视图可视化。
- BareMetal 硬件字段（OPEN-004）。
- 告警、监控、工单、采购、财务、容量预测。

---

## Acceptance Criteria

1. `domain-model.md` 后续修正后，全文不再出现 DataCenter 作为 V1 资源类型、关系、唯一性对象或父对象。
2. F001 的验收标准中**不包含**任何 DataCenter 选择、绑定或层级路径。
3. F002 的验收标准中，BareMetal 的直接上级只有 Cluster，无 DataCenter 层级。
4. F003 保持为 V1 范围内的正式 Feature，验收标准包含「同一 Rack 内 U 位冲突时禁止保存，而不是仅提示 Warning」。
5. F009 / F010 的查询路径不包含 DataCenter 维度。
6. F006 / F007 的 `open_questions` 中**不再出现**「虚拟资源运行时集成是否属于 V1」（OPEN-006）。
7. 被判定为 Blocking 的问题以 Q-001 ~ Q-003 形式列出，每项含互斥候选选项及其对 Feature/Milestone 的后果。
8. 本 Handoff 中任何非 CONFIRMED 结论均显式标记为 `PROPOSED` 或 `UNCONFIRMED`，无混写。

---

## Assumptions

- A-1：在 `domain-model.md` 完成同步前，与 `requirements.md` 不冲突的 `domain-model.md` 内容（§7.1 BareMetal 状态、§9 生命周期、§8 唯一性大小写）可继续作为依据引用。
- A-2：`domain-model.md` 中 DataCenter 相关内容（含 §5.1「绑定到数据中心（必选）」）在修正前视为 Legacy，不参与任何 Feature 的验收标准定义。
- A-3：`domain-model.md` §6 与 §7.2/§7.3 在 `requirements.md` 未确认的范围内（Service 载体绑定、VM/Container 绑定强制性、VM/Container/Service/NIC/IP 状态枚举）视为 **UNCONFIRMED**，不得作为设计依据。
- A-4：`domain-model.md` 缺失 Rack 视为文档滞后，F003 依据 `requirements.md` §13 继续推进。

---

## Proposed Rules

以下为 **PROPOSED**，不是 CONFIRMED，需用户或后续 Feature Product 阶段明确后才能落地：

- `PROPOSED-1`：可先按 CR-1 实施 F001/F002/F009/F010/F011 的范围裁剪，不等 `domain-model.md` 文档修正完成，避免文档维护阻塞 M2 开发。
- `PROPOSED-2`：Rack 的标识与唯一性边界建议在 F003 Product 阶段确认（Rack 是否全局唯一命名、是否归属某个 Cluster），因为 `requirements.md` 与 `domain-model.md` 均未定义。**本提案不预设答案。**
- `PROPOSED-3`：VirtualMachine 除字段外的**标识与唯一性规则**同样未被任何已确认文档定义（`domain-model.md` §8 不含 VM），建议与 OPEN-001 一并在 F006 Product 阶段确认。
- `PROPOSED-4`：OPEN-006 建议从 `requirements.md` §29 移入「已确认排除」，以保持文档状态标记准确。

---

## Open Questions

### Blocking

本轮只列 3 项（`.pi/agents/product-manager.md` §5 限制）。

#### Q-001（来自 DEC-003）Service 与 Cluster / 运行载体的关系模型

| 维度 | `requirements.md` §14 / §15 | `domain-model.md` §5.5 / §6 |
|---|---|---|
| 关系 | Service `N:N` **Cluster**（§15） | Service 绑定 **VM / Container / BareMetal**（运行载体） |
| 约束 | R-SVC-004：不得设计成强制 `service.cluster_id` | 绑定载体**必选** |
| 共享 | R-SVC-002/003：可被多 Cluster 共享，只登记一次 | 未提及 Cluster 关系 |
| 字段 | R-SVC-001：Name/Type 可自由登记 | 服务名称、服务 URL、绑定载体 |

两套关系模型语义互斥，且决定 F008 是否依赖 F006/F007。

**候选选项**

- **A（以 `requirements.md` 为准）**：Service 只与 Cluster 建立 `N:N` 关系，**不建立** Service → 运行载体关系。
  - 后果：F008 依赖收敛为 F001（Cluster）+ F012；不依赖 F002/F006/F007。F010 的 BareMetal 详情不展示 Service。`domain-model.md` §5.5/§6 的载体绑定判为 Legacy，需修正。
- **B（双关系）**：Service 与 Cluster `N:N`，**并且**可选绑定运行载体（BareMetal / VM / Container）。
  - 后果：F008 除 F001 外与 F002/F006/F007 产生**可选**依赖，依赖图更复杂；F010 需展示 Service ↔ 载体；还需追加子问题「载体绑定是否必选」（新增 UNCONFIRMED）。
- **C（以 `domain-model.md` 为准）**：Service 必选绑定运行载体，Cluster 共享通过载体的 Cluster 归属推导。
  - 后果：与 R-SVC-002/003 的「只登记一次且可被多 Cluster 共享」直接冲突，且实质重新引入单一 Cluster 归属路径；必须**显式修改 `requirements.md` §14**。F008 变为强依赖 F002/F006/F007，M4 顺序被牵动。

#### Q-002（来自 DEC-006）VM / Container / Service / NetworkInterface / IPAddress 的状态模型是否属于 V1

- `requirements.md`：仅确认 BareMetal 状态（§8 R-BM-003~005）与 Cluster 无状态（§7 R-CLUSTER-003）。**未定义** VM / Container / Service / NIC / IP 的任何状态。
- `domain-model.md`：§7.2 定义 VM/Service/Container = `IDLE/RUNNING/DOWN/UNKNOWN`，登记后默认 `RUNNING`；§7.3 定义 NIC/IP = `IDLE/ALLOC/SAVE/UNKNOWN`，登记后默认 `IDLE`。

该判定直接决定 5 个 Feature 是否要增加状态字段、状态校验与状态列导入。

**候选选项**

- **A（采纳 `domain-model.md` 枚举）**：5 类资源均带状态字段与默认值。
  - 后果：F004/F005/F006/F007/F008 均增加状态字段、默认值、非法值校验；F012 一致性基座包含状态值校验；Excel 模板（F011）需含状态列；F010 可展示非 BareMetal 资源状态。
- **B（V1 仅 BareMetal 有状态）**：VM / Container / Service / NIC / IP 与 Cluster 一致，不设状态。
  - 后果：F004/F005/F006/F007/F008 范围缩小，验收标准中不含状态；R-QUERY-003 中「资源状态展示」仅覆盖 BareMetal；`domain-model.md` §7.2/§7.3 判为 Legacy。
- **C（部分采纳）**：由用户指定哪几类资源在 V1 具备状态。
  - 后果：F004/F005/F006/F007/F008 的范围与 Excel 模板列**逐类不同**，需按类分列验收标准；F012 基座需支持「部分资源有状态」的差异化校验。

#### Q-003（来自 DEC-007）Cluster 名称不得包含 `/` 是否为 V1 产品规则

- `domain-model.md` §5.1 / §8：Cluster 名称不得包含 `/`，理由为用于 URL 路径寻址，并注明「写入校验待后续『集群登记』Feature 落地」。
- `requirements.md`：§7（Cluster 规则）、§22（大小写敏感）、§21（一致性）**均未提及**该规则。

按范围推断规则，`requirements.md` 未提及 **不等于** 已排除。

**候选选项**

- **A（保留为 V1 规则）**：Cluster 名称禁止包含 `/`，F001 写入路径强制校验并拒绝。
  - 后果：F001 验收标准新增该条校验；URL 寻址可继续依赖名称路径（与 DEC-011 无冲突）。
- **B（废除）**：Cluster 名称只受「全局唯一 + 大小写敏感」约束，`/` 合法。
  - 后果：`domain-model.md` §5.1/§8 相关表述判为 Legacy；**URL 不得依赖名称作为路径分段**，DEC-011 的资源标识/寻址方案必须在架构层相应调整。
- **C（延后到 F001 Product 阶段确认）**：本次不裁定。
  - 后果：M2 入口条件「DEC-007 已确认」未满足；F001 的验收标准中名称字符校验部分无法定稿。

### Non-blocking

- **N-1（DEC-004 / R-VM-003）** VirtualMachine 与物理宿主的绑定强制性与生命周期规则。`requirements.md` R-VM-003 明确「不得由 Agent 推导，应在对应 Feature Product 阶段进一步明确」。归属 **F006 Product 阶段**，M4 启动前解决。
- **N-2（DEC-005 / §10）** Container 登记粒度、生命周期与运行关系。归属 **F007 Product 阶段**，M4 启动前解决。
- **N-3（DEC-002 残余）** Rack 的标识与唯一性边界。`requirements.md` §13 未定义 Rack 命名/唯一性范围。归属 **F003 Product 阶段**。见 `PROPOSED-2`。
- **N-4（OPEN-001）** VirtualMachine 字段范围。归属 **F006**。另见 `PROPOSED-3`。
- **N-5（OPEN-002）** Container 管理粒度。归属 **F007**。
- **N-6（OPEN-003）** Service 字段范围。归属 **F008**。R-SVC-001 已确认 Name/Type 可自由登记，剩余字段未确认。**受 Q-001 前置约束**。
- **N-7（OPEN-004）** BareMetal 硬件字段范围。归属 **F002**，M2 启动前解决。
- **N-8（OPEN-005）** Excel 部分成功导入策略。归属 **F011**，M5 启动前解决。
- **N-9（DEC-008 的文档动作）** `domain-model.md` §4「静态/动态信息」与「统一 `status` 字段」表述、§6「全部绑定必选」的准确性。「统一 status 字段」属建模/持久化问题（转 Architect）；「全部绑定必选」已被 Q-001 与 N-1/N-2 覆盖。
- **N-10** `domain-model.md` 修正任务（DataCenter / Rack 同步），按 `AGENTS.md` §4 保持单一权威来源。

### 对 `requirements.md` §29 OPEN-001 ~ OPEN-006 的重新判定

| ID | 原表述 | 重新判定 | 理由 |
|---|---|---|---|
| OPEN-001 | VM 字段未确认 | **维持 OPEN，范围应扩大** | 无已确认文档定义 VM 字段；`domain-model.md` 亦未定义 VM 标识/唯一性，原表述未覆盖该缺口 |
| OPEN-002 | Container 粒度未确认 | **维持 OPEN，需拆分** | 「V1 允许领域模型表达 Container」（§10）与「不引入 K8s/Docker/Runtime 自动发现」（§10、§23）**已确认**；仅粒度/生命周期/运行关系未确认 |
| OPEN-003 | Service 字段未确认 | **维持 OPEN，部分已确认** | R-SVC-001 已确认 Name/Type 可自由登记；其余字段未确认。受 Q-001 前置约束 |
| OPEN-004 | BareMetal 硬件字段未确认 | **维持 OPEN** | 无已确认文档定义硬件字段范围 |
| OPEN-005 | Excel 部分导入未确认 | **维持 OPEN** | R-IMPORT-004 明确禁止自行决定 |
| OPEN-006 | 运行时集成未确认 | **建议移出 OPEN，判定为已确认排除** | R-VM-002 + §10 + §23 三项互相印证，已无未确认空间。见 `PROPOSED-4` |

---

## Architecture Handoff

1. **DEC-008**：`domain-model.md` §4「静态/动态信息」与「通用 `status` 字段」建模方式是否采用。属 Schema 与持久化设计。约束来自 `requirements.md` §4（不同资源可有独立状态模型，不要求共享基类）与 §24（禁止 EAV / 通用 `resources` 表 / STI / JSONB 万能模型）。Architect 需在 Q-002 裁定后决定各资源状态存储形式。
2. **DEC-009 ~ DEC-014**（项目级、仍是全项目阻塞）：技术栈与整体架构、数据库选型与 Migration、全局资源标识与 URL 寻址、逻辑删除持久化与「已删不占唯一性」释放语义、本地认证实现范围、API 契约与错误响应规范。
3. **R-RACK-004**：多 U 服务器实际占用 U 范围的表达方式。
4. **R-SVC-003**：Q-001 裁定后 `Service N:N Cluster`（或等价语义）的具体持久化实现形式。
5. **关系基数与可空性**：在 Q-001、Q-002 裁定及 N-1/N-2 确认后确定。确认前不得默认「必选」（`requirements.md` §15）。
6. **一致性约束落点**：`requirements.md` §21 的一致性保护具体落在数据库约束还是应用层，由 Architect / Database 决定。
7. **Q-003 与 DEC-011 的耦合**：若 Q-003 选 B（废除 `/` 禁则），URL 寻址方案不得依赖资源名称作为路径分段。Architect 不得替产品决定 Q-003。

---

## Handoff Status

`RESOLVED`（原为 `NOT READY FOR ARCHITECT`）

3 项 Blocking 产品问题（Q-001 / Q-002 / Q-003）已裁定并落入产品文档；DEC-004 / DEC-005 下放至 F006 / F007 Product 阶段，DEC-008 转交 Architect。
项目级 Blocking 仅剩 **DEC-009 ~ DEC-014**（架构与数据库决策），需通过 Architecture 流程解决。

---

## 8 项冲突分类统计

| 分类 | 数量 | 项 |
|---|---|---|
| `RESOLVABLE` | 2 | **DEC-001**（DataCenter，用户指令 + §6/§5/§23）、**DEC-002**（Rack/U 位，§5/§13/§26） |
| `NEEDS_USER_DECISION` | 5 | 阻塞 3 项：**DEC-003**（Q-001）、**DEC-006**（Q-002）、**DEC-007**（Q-003）；延后至 Feature Product 2 项：**DEC-004**（N-1）、**DEC-005**（N-2） |
| `NOT_PRODUCT` | 1 | **DEC-008**（统一 status 建模 → Architect） |

**影响范围**：
DEC-001 → F001/F002/F009/F010/F011（M2、M5）；DEC-002 → F003/F011（M3、M5）；DEC-003 → F008/F010/F011（M4、M5）；DEC-004 → F006/F007/F010/F011（M4、M5）；DEC-005 → F007/F010/F011（M4、M5）；DEC-006 → F004/F005/F006/F007/F008（M3、M4）；DEC-007 → F001（M2）；DEC-008 → F006/F007/F008（M4）。