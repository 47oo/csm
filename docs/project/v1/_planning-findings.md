# Stage 1/2 Findings — CSM Project Planning

## A. 现有资产盘点（Stage 1）

### 存在
| 路径 | 说明 |
|---|---|
| `AGENTS.md` | 项目全局规则 |
| `docs/product/requirements.md` | **CSM V1 需求基线（1200 行，自声明 `CONFIRMED BASELINE`）** |
| `docs/product/domain-model.md` | 领域模型，**无状态标记，含 Legacy 内容** |
| `docs/project/git-workflow.md` | Git 流程 |
| `docs/project/repository-structure.md` | 目录职责 |
| `.pi/agents/*.md` | 8 个 Agent 定义 |
| `.pi/skills/resource-domain/SKILL.md` | 领域 Skill |
| `.pi/prompts/{project,feature,implement-project}.md` | 工作流入口 |
| `.pi/extensions/subagent/` | Pi 扩展 |

### 不存在（确认）
- `docs/product/domain-model.yaml` — **用户在需求中指定，但文件不存在**
- `docs/architecture/`、`docs/architecture/adr/` — 无任何架构决策 / ADR
- `docs/database/` — 无数据库设计
- `docs/api/` — 无 API 契约
- `backend/`、`frontend/`、`tests/` — **无任何应用代码**
- `docs/project/v1/project-plan.yaml`、`backlog.md`、`dependency-map.md`、`milestones.md` — 无历史计划
- 无 Handoff、无 Test/Review 报告、无 Feature Branch
- 无 `develop` 分支；仅 `main`；git 历史仅 4 个提交，无被删除文件

**结论：本项目为 Greenfield。现有工作 = 仅文档与 Agent 基建，零实现。**
因此 `existing_work` 中**不得**出现任何 `DONE` Feature。

---

## B. 需求来源优先级（Stage 2）

1. 用户明确指令：`requirements.md` 为 Primary Requirements Source；
2. `docs/product/requirements.md`（`CONFIRMED BASELINE`）；
3. `docs/product/domain-model.md`（**部分内容与 1 冲突，按冲突处理，不得覆盖 1**）；
4. `docs/product/domain-model.yaml` — **缺失**。

---

## C. Legacy Conflict 清单（必须作为决策项记录，不得自行裁定）

### C-1 DataCenter（用户已明确）
`domain-model.md` §3/§5.1/§6/§7.4/§8/§9 仍含 DataCenter，且规定 `Cluster → DataCenter` 绑定**必选**、DataCenter 名称全局唯一、DataCenter 无状态。
`requirements.md` §6 明确：**V1 不建立 DataCenter 层级**，不得自动创建 `DataCenter → Cluster`。

→ **以 requirements.md 为准：V1 不含 DataCenter。** 同时 `domain-model.md` 需修正（任务不属于本次规划）。

### C-2 Rack / U 位（domain-model.md 完全缺失）
`requirements.md` §13 定义 Rack 与 U 位冲突**硬阻断**（R-RACK-001..004）。
`domain-model.md` taxonomy §3、关系 §6、唯一性 §8 **完全不含 Rack / U 位**。

→ requirements.md 有确认规则；domain-model.md 未同步。需决策：Rack 是否确认进入 V1 领域模型 + 领域模型文档如何同步。

### C-3 Service 关系模型（语义级冲突）
| | requirements.md §14 | domain-model.md §5.5/§6 |
|---|---|---|
| Service 归属 | Service `N:N` **Cluster**，可被多 Cluster 共享 | Service 绑定 **VM / Container / BareMetal**（运行载体） |
| 约束 | R-SVC-004：**不得**设计成强制 `service.cluster_id` | 绑定载体**必选** |
| 字段 | R-SVC-001 自由登记；字段属 OPEN-003 | 服务名称、服务 URL、绑定载体 |

**两套模型互斥**，直接影响 Service Feature 的依赖（是否依赖 VM/Container Feature）。

### C-4 VirtualMachine 绑定强制性
`requirements.md` R-VM-003：关系模型应能表达实际运行位置，但**强制性与生命周期规则不得由 Agent 推导**，须在 Feature Product 阶段确认。
`domain-model.md` §5.3/§6：`VM → BareMetal` **必选**。

→ 不得自动采用「必选」。

### C-5 Container 管理粒度与绑定
`requirements.md` §10：登记粒度、生命周期、运行关系**须在 Feature 阶段确认**；不得引入 K8s/Docker API。
`domain-model.md` §5.4/§6：`Container → VM / BareMetal` **必选**。

→ 不得自动采用「必选」。

### C-6 VM / Container / Service / NIC / IP 的状态模型（未确认）
`requirements.md` 仅确认 **BareMetal** 状态（R-BM-003/004/005）与 **Cluster 无状态**（R-CLUSTER-003）。
`requirements.md` **未定义** VM / Container / Service / NetworkInterface / IPAddress 的状态枚举。
`domain-model.md` §7.2/§7.3 定义了：
- VM/Service/Container：`IDLE/RUNNING/DOWN/UNKNOWN`，默认 `RUNNING`
- NIC/IP：`IDLE/ALLOC/SAVE/UNKNOWN`，默认 `IDLE`

→ 这些属**未确认需求**，不得升级为 CONFIRMED，也不得据此规划 Feature 的验收条件。

### C-7 Cluster 名称 `/` 规则
`domain-model.md` §5.1/§8：Cluster 名称不得含 `/`（用于 URL 路径寻址），并注明「写入校验待后续集群登记 Feature 落地」。
`requirements.md` §7/§22/§8：**未提及**该规则。

→ `/` 规则来源不明，需确认是否为已确认产品规则。

### C-8 domain-model.md 的其他独有内容
- §4「静态信息 / 动态信息」与通用 `status` 字段统一建模（requirements.md §16/§21 未如此表述）
- §6 声明「以上绑定全部为必选」——与 C-4/C-5 冲突
- §7.5 状态流转人工维护（与 R-BM-006 一致 ✓）
- §9 生命周期（与 requirements.md §17 一致 ✓）

---

## D. 一致项（可安全使用）
- Cluster 名称全局唯一、**大小写敏感**（requirements §22 / domain-model §8）
- 同一 Cluster 内 hostname 唯一、大小写敏感
- 同一 Cluster 内 IP 唯一（`cluster + ip_address`），不考虑 VRF
- BareMetal 状态 `IDLE/ALLOC/DOWN/UNKNOWN`，默认 `IDLE`，不得为 NULL
- 逻辑删除、不级联、无 Undelete、父有活跃子不可删
- taxonomy 不产生数据库继承；禁止 EAV / 通用 `resources` 表 / STI / JSONB 万能模型

---

## E. 项目中明确未确认（requirements.md §29，不得升级为 CONFIRMED）
- OPEN-001 VirtualMachine 字段
- OPEN-002 Container 管理粒度
- OPEN-003 Service 字段
- OPEN-004 BareMetal 硬件字段
- OPEN-005 Excel 部分成功导入
- OPEN-006 虚拟资源运行时集成