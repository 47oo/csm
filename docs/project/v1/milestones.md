# CSM Milestones

> Status: 由 `docs/project/v1/project-plan.yaml` **生成**（人类可读视图，不构成机器状态的唯一来源）
> Source of Truth: `docs/project/v1/project-plan.yaml`
> Generated: 2026-09-22（全部 V1 Feature 处置完毕；`project.status = DONE`）
> 生成依据：`project.status = DONE`；计数 `{'READY': 0, 'IN_PROGRESS': 0, 'BLOCKED': 0, 'DRAFT': 0, 'DONE': 21, 'CANCELLED': 1}`

**2026-09-22（增量四·终）**：F023 完成（merge e234908）；M12 **DONE**；M1–M12 全部 DONE，全部 V1 Feature 处置完毕（21 DONE + 1 CANCELLED）。

**2026-09-21（增量三·终）**：F022 完成（merge b467e89）；M11 **DONE**；M1–M11 全部 DONE，全部 V1 Feature 处置完毕（20 DONE + 1 CANCELLED）。

**2026-09-21（增量三·续）**：用户采纳 DEC-024 推荐方案，DEC-024 RESOLVED；M11 进入条件已满足，F022 转 **READY**（待实现）。M1–M10 结论不变。

**2026-09-21（终）**：F021 完成（merge 011d05d）；M10 **DONE**；M1–M10 全部 DONE，全部 V1 Feature 处置完毕（19 DONE + 1 CANCELLED）。

**2026-09-21**：F020 完成（merge e4291a1，Reviewer = APPROVED WITH FOLLOW-UP）；M10 进度为 **F020 DONE / F021 READY**，F021 转入执行。

**2026-09-20（二）增量**：新增 M10（IP 地址范围段与自动 / 手动分配，只含 F020 / F021）与 F020、F021、DEC-023；`project.status` 由 DONE 转 **DRAFT**（待批准）。
**2026-09-20（续）**：DEC-023 已由用户 RESOLVED；F020 转 **READY**，F021 转 **BLOCKED**（依赖 F020 未 DONE）。
该输入提出**两项此前被 F005 显式排除**的新产品能力，且严重欠定义；R-IP-001 ~ R-IP-003 保持不变。
**既有里程碑 M1–M9 及其结论一律不变**（含各 Feature 的 merge SHA）。

**2026-09-18（五）增量**：新增 M9（搜索结果聚合视图，只含 F019）与 F019（DRAFT）、DEC-022（OPEN）；`project.status` 由 DONE 转 **DRAFT**（待批准）。
**2026-09-20**：用户批准增量计划并就 DEC-022 裁定；F019 转 **READY**，M9 已完成（merge 292345e8）。
**既有里程碑 M1–M8 及其结论一律不变**（含各 Feature 的 merge SHA）。

**重建说明**：本文件由 `project-plan.yaml` 重新生成，取代此前陈旧的正文（旧版仍写「Feature 总数 14 / DONE 10 / F007 READY / M4 进行中」等）。
历史结论（F011 取消、M5 的实际结局、各 Feature 的 merge SHA、各条 follow-up）均按计划原样保留，未因重建而丢失。

Milestone 按**产品交付能力**划分，不按 Database / Backend / Frontend 技术层划分。
完成判据统一要求：对应 Feature 的 Reviewer 为 `APPROVED` / `APPROVED WITH FOLLOW-UP`，必要测试通过，Feature Branch 已成功 merge 到 develop，项目状态已更新并提交（Git Gate 见 `docs/project/git-workflow.md`）。

## 总览

| ID | 名称 | Features | 状态 |
|---|---|---|---|
| M1 | 平台基础可运行 | F012, F013, F014, F015 | **DONE** |
| M2 | 基础资源可登记与查询 | F001, F002, F009 | **DONE** |
| M3 | 网络资源管理 | F004, F005 | **DONE** |
| M4 | 虚拟资源与共享服务 | F006, F007, F008 | **DONE** |
| M5 | 统一资源视图与批量导入 | F010, F011 | **DONE** |
| M6 | 补 F001 遗留的 Cluster 登记 UI（post-V1 缺口闭合） | F016 | **DONE** |
| M7 | 应用外壳侧边栏导航（post-V1，呈现层） | F017 | **DONE** |
| M8 | 集群内资源关键字搜索 | F018 | **DONE** |
| M9 | 搜索结果聚合视图 | F019 | **DONE** |
| M10 | IP 地址范围段与自动 / 手动分配 | F020, F021 | **DONE** |
| M11 | 网段自定义名称 / 子网掩码 / VLAN（IP 地址范围段元数据扩展） | F022 | **DONE** |
| M12 | 自动分配指定 IP 地址范围段 | F023 | **DONE** |

## M1 — 平台基础可运行 · 状态：DONE

**目标**：建立可运行、可登录的内网部署基础，并具备逻辑删除与一致性治理基座。

| ID | Feature | Priority | 状态 | Merge |
|---|---|---|---|---|
| F012 | 项目基础框架与运行环境 | P0 | **DONE** | 3b8646c7 |
| F013 | 本地账号认证与会话 | P0 | **DONE** | 4d2e48c7 |
| F014 | 逻辑删除与数据一致性治理 | P0 | **DONE** | 184ee61f |
| F015 | 内网部署与运行环境 | P0 | **DONE** | 06e655a2 |

**进入条件**
- 架构已批准（ADR-0001 ~ ADR-0005 全部 ACCEPTED）
- API 契约 READY（docs/api/api-conventions.md）
- F012 已 READY（无阻塞决策、无 depends_on）

**完成判据**
- 系统可在独立内网虚拟机以 Internal IP + HTTP 运行。
- 本地账号可登录。
- 逻辑删除语义与一致性/错误处理基座可用且有测试证据。
- Reviewer 批准并成功 merge 到 develop（Git Gate 见 docs/project/git-workflow.md）。

## M2 — 基础资源可登记与查询 · 状态：DONE

**目标**：运维人员可登记 Cluster、BareMetal，并从 Cluster 视角查询其下资源与状态。

| ID | Feature | Priority | 状态 | Merge |
|---|---|---|---|---|
| F001 | Cluster 登记与管理 | P0 | **DONE** | 5a96ad0c |
| F002 | BareMetal 登记与管理 | P0 | **DONE** | ef39557f |
| F009 | Cluster 视角资源查询 | P0 | **DONE** | 6529b0dc |

**进入条件**
- M1 完成

**完成判据**
- Cluster 全局唯一名称与 BareMetal 集群内唯一 hostname 生效。
- BareMetal 状态模型（IDLE/ALLOC/DOWN/UNKNOWN，默认 IDLE，非空）生效。
- 可从 Cluster 视角查看 BareMetal 及其状态，并区分 Not Found 与 Empty Relationship。
- Cluster 名称不得包含 `/`，登记写入路径校验生效（R-CLUSTER-005）。
- Reviewer 批准并成功 merge 到 develop。

## M3 — 网络资源管理 · 状态：DONE

**目标**：统一管理网络接口与 IP 地址，阻止同 Cluster IP 重复。

| ID | Feature | Priority | 状态 | Merge |
|---|---|---|---|---|
| F004 | NetworkInterface 管理 | P1 | **DONE** | 4a99fa00 |
| F005 | IPAddress 管理 | P1 | **DONE** | 7beb6e72 |

**进入条件**
- M2 完成

**完成判据**
- NetworkInterface 记录 technology_type 与 purpose。
- 同 Cluster 内 IP 唯一、跨 Cluster 可重复。
- NetworkInterface / IPAddress 在 V1 不设状态（Q-002=B）。
- Reviewer 批准并成功 merge 到 develop。

## M4 — 虚拟资源与共享服务 · 状态：DONE

**目标**：登记虚拟资源（VM / Container），并将共享 Service 与多个 Cluster 关联且只登记一次。

| ID | Feature | Priority | 状态 | Merge |
|---|---|---|---|---|
| F006 | VirtualMachine 登记与管理 | P1 | **DONE** | 01077bed |
| F007 | Container 资源模型与登记 | P1 | **DONE** | ff347be7 |
| F008 | Service 资源管理与 Cluster 共享关联 | P1 | **DONE** | f7733783 |

**进入条件**
- M2 完成（F006/F007/F008 依赖基础资源）
- F006 Product 阶段确认 DEC-004（VM 绑定强制性与生命周期）
- F007 Product 阶段确认 DEC-005（Container 粒度与绑定）

**完成判据**
- VirtualMachine 可人工登记与查询，不接入虚拟化平台 API。
- Container 资源模型可表达，不接入 K8s / Docker API。
- Service 必选绑定运行载体（BareMetal / VM / Container），可绑定多个；Cluster 关联由载体归属推导，只登记一次，不强制 service.cluster_id。
- Reviewer 批准并成功 merge 到 develop。

## M5 — 统一资源视图与批量导入 · 状态：DONE

**目标**：提供跨资源关联查询与 Excel 批量导入，达到替代 Excel 的 V1 目标闭环。

| ID | Feature | Priority | 状态 | Merge |
|---|---|---|---|---|
| F010 | 资源详情与关联查询 | P1 | **DONE** | 334b4ca3 |
| F011 | Excel 模板与批量导入 | P1 | **CANCELLED** | — |

**进入条件**
- M2 / M3 / M4 完成（依赖全部资源 Feature）

**完成判据**
- 可查询 BareMetal 关联的 NIC / IP / VM / Container / Service，无需跨页面手工拼接。
- 提供 Excel 模板，导入执行与人工录入一致的业务校验并逐行报告错误。
- 导入采用 All-or-Nothing：任一行失败即整体不写入，并一次性报告全部失败行（R-IMPORT-004）。
- Reviewer 批准并成功 merge 到 develop。

## M6 — 补 F001 遗留的 Cluster 登记 UI（post-V1 缺口闭合） · 状态：DONE

**目标**：为已冻结的 Cluster 写入能力补上前端入口，使「登记集群 / 改名」不再只能靠直接调 API。

| ID | Feature | Priority | 状态 | Merge |
|---|---|---|---|---|
| F016 | Cluster 登记与改名 UI | P1 | **DONE** | 93729191 |

**进入条件**
- M1 / M2 完成（F001 的登记与改名端点、F013 认证、F014 删除入口均已 DONE）。
- 用户已裁定补做（2026-09-18，范围：登记 + 改名，共用同一对话框）。

**完成判据**
- 集群列表页可发起登记、集群详情页可发起改名，两者共用同一对话框组件。
- 业务校验仍由后端裁决（`/` 禁令、活跃名称全局唯一、大小写敏感），前端不重复实现、不预判拦截。
- 后端与 API 契约零改动（docs/api/f001-cluster.md 保持冻结）；无 migration。
- Reviewer 批准并成功 merge 到 develop。

## M7 — 应用外壳侧边栏导航（post-V1，呈现层） · 状态：DONE

**目标**：在 V1 全部交付后，按用户确认把应用外壳导航由顶部横向按钮改为侧边栏；纯呈现层，不改变任何业务行为。

| ID | Feature | Priority | 状态 | Merge |
|---|---|---|---|---|
| F017 | 应用外壳侧边栏导航 | P2 | **DONE** | 8fc88324 |

**进入条件**
- 用户明确确认实施（解除 F017 NQ-1 与 DEC-020 OPEN）。
- F012 / F013 / F001 / F002 / F004 / F005 / F006 / F007 / F008 / F010 均已 DONE（已满足）。

**完成判据**
- 7 个资源区在侧边栏全部可达，当前区高亮正确。
- 用户名 / 登出、登录页与 bootstrap、既有视图切换与返回链路均不受影响。
- 无 vue-router、无新增依赖、无 API / DB / 契约改动。
- 5 个导航测试的活跃态断言（15 处）改写而非删除；typecheck + test（连跑 2 次）+ build 通过。
- Reviewer 批准并成功 merge 到 develop（Git Gate 见 docs/project/git-workflow.md）。

## M8 — 集群内资源关键字搜索 · 状态：DONE

**目标**：在选定 Cluster 范围内，通过任意关键字快速定位资源（具体范围 / 字段 / 语义待 F018 的 NQ 裁定）。

| ID | Feature | Priority | 状态 | Merge |
|---|---|---|---|---|
| F018 | 集群内资源关键字搜索 | P1 | **DONE** | f1ac71b1 |

**进入条件**
- DEC-021 裁定为「做」，且既有契约的关键字立场已按裁定修订。
- F018 的 blocking NQ-1 ~ NQ-5 全部裁定，scope / AC 由 Product 定稿，并在 requirements.md 新增 / 修订一条产品规则（NQ-8）。
- 依赖的资源 Feature（F001/F002/F004/F005/F006/F007/F008）均已 DONE（已满足）。
- 若搜索入口落在应用外壳（NQ-5），F017 须先 merge 或先划清 frontend/src/App.vue 的所有权（git-workflow §3）。

**完成判据**
- 交付范围与可判定 AC 经 Product 定稿。
- 搜索契约 READY（新增或修订既有契约）；无「契约禁止、实现却有」的分裂。
- 未认证 → 401；软删资源不出现；Cluster 不存在 / 已删 → 404 与 Empty 可区分（R-QUERY-004）。
- Reviewer 批准并成功 merge 到 develop（Git Gate 见 docs/project/git-workflow.md）。

---

## M9 — 搜索结果聚合视图 · 状态：DONE

**目标**：在 F018 搜索能力之上，按用户裁定提供搜索结果聚合呈现（DEC-022 已 RESOLVED：单一扁平混合列表 + 按命中项关联链 + 关系扩展 + 方案 A + 不去重 + 标识字段优先排序 + 取代 F018 扁列表）。

| ID | Feature | Priority | 状态 | Merge |
|---|---|---|---|---|
| F019 | 搜索结果聚合视图 | P1 | **DONE** | 292345e8 |

**进入条件**
- DEC-022 已由用户裁定（已满足，2026-09-20）。
- Product 修订 R-QUERY-005 或新增聚合产品规则，F019 scope / AC 可定稿（进行中）。
- F018 已 DONE（已满足），其搜索能力与 F010 推导作为基础。
- 搜索响应契约按裁定修订 / 新增为 READY；F019 layers（尤其 database）经 Architecture 复核。

**完成判据**
- 交付范围与可判定 AC 经 Product 定稿。
- 聚合响应契约 READY；无「契约 / 产品规则禁止、实现却有」的分裂。
- 未认证 → 401；软删资源不出现；Cluster 不存在 / 已删 → 404 与 Empty 可区分（R-QUERY-004）。
- Reviewer 批准并成功 merge 到 develop（Git Gate 见 docs/project/git-workflow.md）。

**实施结果**：M9 已完成——F019 DONE（head 4524d8e → merge 292345e8，Reviewer = APPROVED WITH FOLLOW-UP）；Product 已新增 R-QUERY-006 并修订 R-QUERY-005，Architecture / 契约已定稿为 READY。产品语义由 DEC-022 裁定，不再是阻塞。

---

## M10 — IP 地址范围段与自动 / 手动分配 · 状态：DONE

**目标**：按用户裁定为每个 Cluster 提供多个 IP 地址范围段（地址池），并在其上支持自动 / 手动 IP 分配（DEC-023 已 RESOLVED：start–end IPv4、同 Cluster 不重叠、范围内有活跃 IP 时禁止删除；分配沿用 IPAddress 且必选绑定活跃 NIC，自动取并集内最小未占用 IPv4）。

| ID | Feature | Priority | 状态 | Merge |
|---|---|---|---|---|
| F020 | IP 地址范围段（地址池）管理 | P1 | **DONE** | e4291a1e |
| F021 | IP 地址自动 / 手动分配 | P1 | **DONE** | 011d05df |

**进入条件**
- DEC-023 由用户裁定为明确结论（含范围表示 / 重叠 / 分配产物 / 最小地址选取 / 保留地址 / 耗尽行为等）。
- Product 在 requirements.md §12 新增 / 修订产品规则，F020 / F021 的 scope 与 AC 可定稿。
- F005 已 DONE（已满足）；F001 / F002 / F004 已 DONE（已满足）。
- 契约按裁定新增 / 修改为 READY；F020 / F021 的 layers（尤其 database）经 Architecture 复核。

**完成判据**
- 交付范围与可判定 AC 经 Product 定稿。
- 范围段 / 分配契约 READY；无「契约 / 产品规则禁止、实现却有」的分裂。
- 未认证 → 401；软删资源不出现；既有 R-IP-001 ~ R-IP-003 不被静默修改。
- Reviewer 批准并成功 merge 到 develop（Git Gate 见 docs/project/git-workflow.md）。

**完成情况**：DEC-023 已 RESOLVED（2026-09-20），PR-01 已由用户 2026-09-21 裁定（采纳 A）；F020 已于 2026-09-21 DONE（merge e4291a1）；F021 已于 2026-09-21 DONE（merge 011d05d）。M10 DONE。

## M11 — 网段自定义名称 / 子网掩码 / VLAN（IP 地址范围段元数据扩展） · 状态：DONE

**目标**：按用户裁定，为每个自定义网段（IP 地址范围段）补充可维护的元数据（自定义名称 / 子网掩码 / VLAN），使网段具备业务可读标识与网络参数，同时不破坏 F020 / F021 既有语义（语义待 DEC-024 与 F022 NQ 裁定）。

| ID | Feature | Priority | 状态 | Merge |
|---|---|---|---|---|
| F022 | 网段自定义名称 / 子网掩码 / VLAN 标注 | P1 | **DONE** | b467e891 |

**进入条件**
- DEC-024 由用户裁定为明确结论（含字段 / 唯一性 / 掩码表示与一致性 / VLAN 取值域 / 扩展或新实体）。
- Product 修订 R-IP-004 或新增 requirements.md §12 规则，F022 的 scope 与 AC 可定稿并可挂 requirement ID。
- F020 已 DONE（已满足）；若裁定涉及分配行为变更，F021 已 DONE（已满足）并按裁定评估修订。
- 契约按裁定修订 / 新增为 READY；F022 的 layers（尤其 database）与 migration 形态经 Architecture / Database 复核。

**完成判据**
- 交付范围与可判定 AC 经 Product 定稿。
- 网段元数据契约 READY；无「契约 / 产品规则禁止、实现却有」的分裂。
- 未认证 → 401；软删资源不出现；R-IP-001 ~ R-IP-010 及 F020 / F021 既有语义不被静默修改。
- Reviewer 批准并成功 merge 到 develop（Git Gate 见 docs/project/git-workflow.md）。

**完成情况**：DEC-024 已 RESOLVED，F022 已于 2026-09-21 DONE（merge b467e89；`ip_address_ranges` 加 3 个可空列 + migration 0010）。M11 DONE。

---

## M12 — 自动分配指定 IP 地址范围段 · 状态：DONE

**目标**：按用户裁定（DEC-025），使自动分配 IP 地址时能够且必须选择所用 IP 地址范围段，修复“多套范围段时无法选择”的规则缺口，
同时不破坏占用判定 / 唯一性 / 手动分配等既有语义。

| Feature | 名称 | 优先级 | 状态 | Merge |
|---|---|---|---|---|
| F023 | 自动分配时指定 IP 地址范围段 | P1 | **DONE** | e2349081 |

**进入条件**：
- DEC-025 已由用户裁定（必填 / 归属约束 / 耗尽不回退 / 手动不变）—— 已满足（RESOLVED，2026-09-22）。
- F020 与 F021 已 DONE（已满足）。
- Product 修订 R-IP-006 / R-IP-009；f021 契约修订为 READY。

**完成标准**：
- 自动分配请求必须携带 `ip_address_range_id`，且范围段活跃且属于目标 Cluster。
- 在所选单个范围段内取最小未占用 IPv4；耗尽 → `409 NO_AVAILABLE_IP` 且不回退、无写入。
- 手动分配、占用判定、唯一性、数据库 Schema 均不变；无「契约禁止、实现却有」分裂。
- Reviewer 批准并成功 merge 到 develop（Git Gate 见 docs/project/git-workflow.md）。

**完成情况**：DEC-025 已 RESOLVED，F023 已于 2026-09-22 DONE（merge e234908；Reviewer = APPROVED WITH FOLLOW-UP，无 BLOCKER/HIGH/MEDIUM）；AC-01 ~ AC-20 全 PASS；无数据库变更。M12 DONE。

---

达到明确 Milestone 后，是否将 develop 合并到 main 由独立授权流程决定；本计划不自动 push、打 tag 或发布（见 `docs/project/git-workflow.md` §1）。
