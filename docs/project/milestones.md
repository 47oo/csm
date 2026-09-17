# CSM Milestones

> Status: DRAFT（待用户确认）
> Source of Truth: `docs/project/project-plan.yaml`
> Milestone 按**产品交付能力**划分，不按 Database / Backend / Frontend 技术层划分。
> Last updated: 2026-09-18（M2 / M3 已 DONE；M4 进行中：F006 已 DONE，F007 待完成，F008 待启动）

完成判据统一要求：对应 Feature 的 Reviewer 为 `APPROVED` / `APPROVED WITH FOLLOW-UP`，
必要测试通过，且 Feature Branch 已成功 merge 到 develop，项目状态已更新并提交
（Git Gate 见 `docs/project/git-workflow.md`）。因此每个 Milestone 的完成判据都隐含该 Git Gate。

---

## M1 平台基础可运行

> 状态：**DONE**（2026-09-16；F012 / F013 / F014 / F015 均 DONE 并合入 develop）

**目标能力**：建立可运行、可登录的内网部署基础，并具备逻辑删除与数据一致性治理基座。

**包含 Feature**

| ID | Feature | Priority |
|---|---|---|
| F012 | 项目基础框架与运行环境 (ENABLER) | P0 |
| F013 | 本地账号认证与会话 (ENABLER) | P0 |
| F014 | 逻辑删除与数据一致性治理 (ENABLER) | P0 |
| F015 | 内网部署与运行环境 (ENABLER) | P0 |

**进入条件（已全部满足）**
- 架构已批准（ADR-0001 ~ ADR-0005 全部 `ACCEPTED`）
- API 契约 READY（`docs/api/api-conventions.md`）
- F012 已 READY（无阻塞决策、无 depends_on）

**完成判据**
- 系统可在独立内网虚拟机以 Internal IP + HTTP 运行（R-DEPLOY-001..003）。
- 本地账号可登录，不接入 LDAP/AD/OAuth/SSO，未扩大为复杂 RBAC（R-AUTH-001..003）。
- 逻辑删除语义（不物理删除、隐藏、无 Undelete、父有活跃子不可删、不级联、释放唯一性）具备实现与测试证据（R-DELETE-001..006）。
- 通用校验 / 冲突错误处理基座可用（§21）。
- 资源类型采用显式建模，未引入 EAV / 通用 resources 表 / STI / JSONB 万能模型（§24）。
- 上述 Feature 全部满足统一 Git Gate 并 DONE。

---

## M2 基础资源可登记与查询

> 状态：**DONE**（2026-09-16；F001 / F002 / F009 均 DONE 并合入 develop）

**目标能力**：运维人员可登记 Cluster、BareMetal，并从 Cluster 视角查询其下资源与状态
（建立替代 Excel 的最小核心闭环）。

**包含 Feature**

| ID | Feature | Priority |
|---|---|---|
| F001 | Cluster 登记与管理 | P0 |
| F002 | BareMetal 登记与管理 | P0 |
| F009 | Cluster 视角资源查询 | P0 |

**进入条件**
- M1 完成

（DEC-001 DataCenter 冲突与 DEC-007 Cluster 名称 `/` 规则均已 RESOLVED，不再作为进入条件。）

**完成判据**
- Cluster 名称全局唯一且大小写敏感，Cluster 无运行状态（R-CLUSTER-001..003）。
- Cluster 名称不得包含 `/` 的写入校验生效（R-CLUSTER-005）。
- BareMetal 必属一个 Cluster，集群内 hostname 唯一且大小写敏感，状态取自 IDLE/ALLOC/DOWN/UNKNOWN，默认 IDLE，非空（R-BM-001..006）。
- BareMetal 直接上级只有 Cluster，不记录 Rack / U Position（requirements.md §13）。
- 可从 Cluster 视角查看 BareMetal 及状态，查询结果区分 Resource Not Found 与 Empty Relationship（R-QUERY-001/002/004）。
- 满足统一 Git Gate 并 DONE。

---

## M3 网络资源管理

> 状态：**DONE**（2026-09-18；F004 / F005 均 DONE 并合入 develop）

**目标能力**：统一管理网络接口与 IP 地址；阻止同 Cluster IP 重复。

**包含 Feature**

| ID | Feature | Priority |
|---|---|---|
| F004 | NetworkInterface 管理 | P1 |
| F005 | IPAddress 管理 | P1 |

**进入条件**
- M2 完成

（DEC-002 Rack / U 位已从 V1 删除；DEC-006 状态模型已 RESOLVED，均不再作为进入条件。）

**完成判据**
- NetworkInterface 记录 technology_type（Ethernet/InfiniBand/RoCE/Other）与 purpose（BMC/Management/Business/Compute/Storage/DataTransfer/Other），能与所属资源（BareMetal）建立关系（R-NIC-001..003）。
- 同 Cluster 内 IP 唯一，跨 Cluster 可重复，唯一性按 cluster + ip_address（R-IP-001..003）。
- NetworkInterface / IPAddress 在 V1 不设状态（Q-002=B）。
- 满足统一 Git Gate 并 DONE。

---

## M4 虚拟资源与共享服务

> 状态：**DONE**（2026-09-18；F006 / F007 / F008 均 DONE 并合入 develop）

**目标能力**：登记虚拟资源（VirtualMachine / Container），并管理必选绑定运行载体的共享 Service。

**包含 Feature**

| ID | Feature | Priority |
|---|---|---|
| F006 | VirtualMachine 登记与管理 | P1 |
| F007 | Container 资源模型与登记 | P1 |
| F008 | Service 资源管理与 Cluster 共享关联 | P1 |

**进入条件**
- M2 完成（F006/F007/F008 依赖基础资源）
- F006 Product 阶段确认 DEC-004（VM 绑定强制性与生命周期）
- F007 Product 阶段确认 DEC-005（Container 粒度与绑定）

（DEC-003 Service 关系模型、DEC-006 状态模型、DEC-008 统一 status 建模均已 RESOLVED，不再作为进入条件。）

**完成判据**
- VirtualMachine 可人工登记与查询，不接入虚拟化平台 API，关系模型能表达实际运行位置（R-VM-001..003）；V1 不设状态。
- Container 资源模型可表达，不引入 Kubernetes / Docker API（§10）；V1 不设状态。
- Service 必选绑定运行载体（BareMetal / VM / Container），可绑定多个；Cluster 关联由载体归属推导，共享服务只登记一次，不强制 service.cluster_id（R-SVC-001..006）。
- 满足统一 Git Gate 并 DONE。

---

## M5 统一资源视图与批量导入

**目标能力**：提供跨资源关联查询与 Excel 批量导入，达成替代 Excel 的 V1 目标闭环。

**包含 Feature**

| ID | Feature | Priority |
|---|---|---|
| F010 | 资源详情与关联查询 | P1 |
| F011 | Excel 模板与批量导入 | P1 |

**进入条件**
- M2 / M3 / M4 完成（依赖全部资源 Feature）

（OPEN-005 Excel 部分成功导入策略已于 2026-09-15 关闭为 All-or-Nothing，固化为 R-IMPORT-004，不再作为进入条件。）

**完成判据**
- 可查询与 BareMetal 相关的 NetworkInterface / IPAddress / VirtualMachine / Container / Service，无需跨页面手工拼接，结果区分 Resource Not Found 与 Empty Relationship（R-QUERY-003/004）。
- 提供明确的 Excel 导入模板；导入执行与人工录入一致的业务校验（唯一性 / 必填 / 资源关系 / IP 冲突 / 合法状态值）；失败时明确指出行 / 字段 / 原因（R-IMPORT-001..003）。
- 导入采用 All-or-Nothing：任一行失败即整体不写入，并一次性报告全部失败行（R-IMPORT-004）。
- 满足统一 Git Gate 并 DONE。

---

## Milestone 与 Release

达到明确 Milestone 后，是否将 develop 合并到 main 由独立授权的 Release 流程决定，
本计划不自动 push、打 tag 或发布（见 `docs/project/git-workflow.md` §1）。