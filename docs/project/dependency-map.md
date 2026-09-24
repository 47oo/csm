# CSM Feature Dependency Map

> Status: 由 `docs/project/project-plan.yaml` **生成**（人类可读视图，不构成机器状态的唯一来源）
> Source of Truth: `docs/project/project-plan.yaml`
> Generated: 2026-09-24（新增 F024 / F025 / DEC-026 / DEC-027 / M13，待用户批准；`project.status = DRAFT`）
> 生成依据：`project.status = DRAFT`；计数 `{'READY': 0, 'IN_PROGRESS': 0, 'BLOCKED': 0, 'DRAFT': 2, 'DONE': 21, 'CANCELLED': 1}`

**2026-09-24（增量五）**：新增 **F024**（集群概览聚合与节点分类，depends_on F001、F002、F009）、
**F025**（搜索结果上下文展示扩展，depends_on F019）、**DEC-026 / DEC-027**（均 OPEN）与 **M13**；E05 追加 F024 / F025。
F009 当时未交付计数（非永久禁止），F019 已交付关联链聚合；仅当新诉求改变搜索单列表形态或新增统计时才与 R-QUERY-005 / R-QUERY-006 冲突。语义须由用户 / Product 裁定（2026-09-24 部分确认见下）。**既有依赖与结论一律不变**：
M1–M12、各 Feature 的 `depends_on`、merge SHA 与状态均原样保留；F009（merge 6529b0dc）/ F019（merge 292345e8）
已 DONE 的实现与结论不被推翻。**未获批准且 DEC-026 / DEC-027 未裁定前，F024 / F025 不得进入实现。**

**2026-09-24（增量五·再确认）**：用户进一步明确 URL 来源为已登记的 **Service.url**（服务可绑定裸金属 / VM / 容器）；URL 映射对象已确认，不再列为开放问题。间接服务 URL 的主机归属与多服务 / IP / URL 并存时的分行口径仍 OPEN；DEC-027 / F025 / M13 仍 OPEN / DRAFT / DRAFT，未批准计划。

**2026-09-24（增量五·续）——部分确认（当时记录）**：用户新增部分确认：「节点」**仅 BareMetal**、主机 IP / URL **取自绑定依据 / 无绑定不展示**、**多网卡 / 多 IP 分行展示**。**存疑部分仍 OPEN**：「可用」定义、分类维度 / 计数范围；「不展示」仅值还是整行、间接 Service URL 是否归属主机、多服务 / IP 与 URL 并存时如何分行 / 与 F019 对齐、单列表语义。DEC-026 / DEC-027 仍 **OPEN**，F024 / F025 仍 **DRAFT**，无 READY；依赖边 / M1–M12 / merge SHA / 证据与以前 Git 元数据一律不变。

**2026-09-22（增量四·终）**：F023 完成（merge e234908，Reviewer = APPROVED WITH FOLLOW-UP），F023 DONE（无数据库变更）。全部 V1 Feature 处置完毕（21 DONE + 1 CANCELLED）。

**2026-09-21（增量三·终）**：F022 完成（merge b467e89，Reviewer = APPROVED WITH FOLLOW-UP），F022 DONE（数据库增量：ip_address_ranges + migration 0010）。全部 V1 Feature 处置完毕（20 DONE + 1 CANCELLED）。

**2026-09-21（增量三·续）**：用户采纳 DEC-024 推荐方案，DEC-024 **RESOLVED**，F022 由 DRAFT 转 **READY**（依赖 F020 已 DONE）。

**2026-09-21（终）**：F021 完成（merge 011d05d，Reviewer = APPROVED WITH FOLLOW-UP），F021 DONE；M10 DONE。全部 V1 Feature 处置完毕（19 DONE + 1 CANCELLED）。

**2026-09-21（续）**：F021 转 IN_PROGRESS，自 develop（1942ec4）创建分支 `feature/F021-ip-address-allocation`。

**2026-09-21**：F020 完成（merge e4291a1，Reviewer = APPROVED WITH FOLLOW-UP），**F020 DONE**；F021 由 **BLOCKED 转 READY**（唯一阻塞 F020 已解除）。

**2026-09-20（二）增量**：新增 F020（IP 地址范围段管理，depends_on F001、F005）、F021（IP 自动 / 手动分配，depends_on F020、F005、F004、F002）、DEC-023 与 M10。
**2026-09-20（续）**：DEC-023 已由用户 RESOLVED；F020 转 **READY**，F021 转 **BLOCKED**（仅因依赖 F020 未 DONE）。
**既有依赖与结论一律不变**：M1–M9、各 Feature 的 `depends_on`、merge SHA 与状态均原样保留；R-IP-001 ~ R-IP-003 保持不变。

**2026-09-18（五）增量**：新增 F019（搜索结果聚合视图，depends_on F018）、DEC-022 与 M9。
**2026-09-20**：DEC-022 由用户裁定，F019 转 **READY** 并已完成 Feature Workflow（merge 292345e8）。

**重建说明**：本文件由 `project-plan.yaml` 重新生成，取代此前陈旧的正文（旧版仍写「Feature 总数 14 / DONE 10 / F007 READY / M4 进行中」等）。
历史结论（F011 取消、M5 的实际结局、各 Feature 的 merge SHA、各条 follow-up）均按计划原样保留，未因重建而丢失。

依赖仅表示**真正的实施依赖**（B 无法在 A 未 DONE 时正确实现）。依赖为 DAG，无循环。
图例：`A --> B` 表示 **B depends_on A**（A 是 B 的前置）。

## 依赖表（权威：计划 `features[].depends_on`）

| Feature | 状态 | depends_on | 层 |
|---|---|---|---|
| F012 项目基础框架与运行环境 | DONE | — | database, backend, frontend |
| F013 本地账号认证与会话 | DONE | F012 | database, backend, frontend |
| F014 逻辑删除与数据一致性治理 | DONE | F012 | backend, frontend |
| F015 内网部署与运行环境 | DONE | F012, F013 | backend, deployment |
| F001 Cluster 登记与管理 | DONE | F012 | backend, frontend |
| F002 BareMetal 登记与管理 | DONE | F001 | database, backend, frontend |
| F004 NetworkInterface 管理 | DONE | F002 | database, backend, frontend |
| F005 IPAddress 管理 | DONE | F004 | database, backend, frontend |
| F006 VirtualMachine 登记与管理 | DONE | F002 | database, backend, frontend |
| F007 Container 资源模型与登记 | DONE | F006, F002 | database, backend, frontend |
| F008 Service 资源管理与 Cluster 共享关联 | DONE | F001, F002, F006, F007 | database, backend, frontend |
| F009 Cluster 视角资源查询 | DONE | F001, F002 | backend |
| F010 资源详情与关联查询 | DONE | F001, F002, F004, F005, F006, F007, F008 | backend, frontend |
| F011 Excel 模板与批量导入 | CANCELLED | F001, F002, F004, F005, F006, F007, F008 | — |
| F016 Cluster 登记与改名 UI | DONE | F001, F013, F014 | frontend |
| F017 应用外壳侧边栏导航 | DONE | F012, F013, F001, F002, F004, F005, F006, F007, F008, F010 | frontend |
| F018 集群内资源关键字搜索 | DONE | F001, F002, F004, F005, F006, F007, F008 | backend, frontend |
| F019 搜索结果聚合视图 | DONE | F018 | backend, frontend（database: false） |
| F020 IP 地址范围段（地址池）管理 | DONE | F001, F005 | database, backend, frontend |
| F021 IP 地址自动 / 手动分配 | DONE | F020, F005, F004, F002 | backend, frontend（database: false） |
| F022 网段自定义名称 / 子网掩码 / VLAN 标注 | DONE | F020 | database, backend, frontend |
| F023 自动分配时指定 IP 地址范围段 | DONE | F020, F021 | backend, frontend（database: false） |
| F024 集群概览聚合与节点分类 | DRAFT | F009 | frontend / backend（待 Architecture 复核） |
| F025 搜索结果上下文展示扩展 | DRAFT | F019 | frontend, backend（待 Architecture 复核） |

## 全量依赖 DAG

```text
F012 项目基础框架与运行环境 (P0, DONE)
   └──> F013 本地账号认证与会话 (P0, DONE)
   └──> F014 逻辑删除与数据一致性治理 (P0, DONE)
   └──> F015 内网部署与运行环境 (P0, DONE)
   └──> F001 Cluster 登记与管理 (P0, DONE)
   └──> F017 应用外壳侧边栏导航 (P2, DONE)
```

F019（搜索结果聚合视图，P1，DONE）依赖 F018：

```text
F018 集群内资源关键字搜索 (P1, DONE)
   └──> F019 搜索结果聚合视图 (P1, DONE)  ← merge 292345e8（产品语义由 DEC-022 裁定，Reviewer = APPROVED WITH FOLLOW-UP）
```

F020 / F021 依赖既有网络资源链：

```text
F001 Cluster 登记与管理 (P0, DONE) ──┬──> F020 IP 地址范围段管理 (P1, DONE)
F005 IPAddress 管理 (P1, DONE) ──────┘        └──> F021 IP 自动 / 手动分配 (P1, DONE)
F004 NetworkInterface 管理 (P1, DONE) ─────────────> F021
F002 BareMetal 登记与管理 (P0, DONE) ───────────────> F021
```

F022 依赖 F020；F023 修订已交付 F021 的自动分配，依赖 F020 与 F021：

```text
F020 IP 地址范围段管理 (P1, DONE) ─────> F022 网段元数据标注 (P1, DONE)
F020 IP 地址范围段管理 (P1, DONE) ──┐
                                    ├─> F023 自动分配指定范围段 (P1, DONE)
F021 IP 自动 / 手动分配 (P1, DONE) ──┘
```

F024 / F025 在已交付的 Cluster 视图与搜索聚合之上扩展，彼此无依赖：

```text
F009 Cluster 视角资源查询 (P0, DONE) ──> F024 集群概览聚合与节点分类 (P1, DRAFT)
F019 搜索结果聚合视图 (P1, DONE) ──> F025 搜索结果上下文展示扩展 (P1, DRAFT)
```

> F009 已依赖 F001 / F002，不重复画边。F024 与 F025 在依赖角度可并行，但可能修改同一前端文件，实施前须划清文件所有权。两项均待 DEC-026 / DEC-027 裁定及 Product 落规则（2026-09-24 仅部分确认：「节点」仅 BareMetal、多网卡 / 多 IP 分行展示等；其余仍 OPEN）。F021 不是 F022 的前置；上述已交付功能的结论不变。

## 拓扑序（实施顺序参考）

```text
 1. F012  DONE
 2. F013  DONE
 3. F014  DONE
 4. F015  DONE
 5. F001  DONE
 6. F002  DONE
 7. F004  DONE
 8. F005  DONE
 9. F006  DONE
10. F007  DONE
11. F008  DONE
12. F009  DONE
13. F010  DONE
14. F011  CANCELLED
15. F016  DONE
16. F017  DONE
17. F018  DONE
18. F019  DONE（merge 292345e8）
19. F020  DONE（merge e4291a1）
20. F021  DONE（merge 011d05d；数据库零变更）
21. F022  DONE（merge b467e89；ip_address_ranges + migration 0010）
22. F023  DONE（merge e234908；无数据库变更）
23. F024  DRAFT（依赖 F009；待 DEC-026）
24. F025  DRAFT（依赖 F019；待 DEC-027）
```

## 可并行执行的 Feature

- 当前 **无 READY / IN_PROGRESS / BLOCKED**；21 个 V1 Feature 已 DONE、F011 已 CANCELLED；新增 F024 / F025 为 **DRAFT**（待 DEC-026 / DEC-027 裁定）。
- F024 与 F025 之间无真实依赖，但均可能修改前端视图（尤其 `frontend/src/App.vue` / `SearchResultsPage.vue` / `ClusterDetailPage.vue`），**不得并行写入同一文件**；实施前必须划清文件所有权（`docs/project/git-workflow.md` §3）。
- F020 与 F021 之间有真实依赖（F021 → F020），**不可并行**；F020 DONE 后 F021 方可启动。
- 若后续一个 Milestone 内出现多个相互无依赖的 Feature，可并行；但必须划清文件所有权（`docs/project/git-workflow.md` §3）。

## 说明

- `F019` 已 `DONE`（merge 292345e8，Reviewer = APPROVED WITH FOLLOW-UP）；产品语义由 DEC-022 裁定（2026-09-20）。F019 遗留 REV-1 / REV-2（测试覆盖回退，LOW）与 REV-4（NOTE）作为非阻塞 follow-up。
- `F018` 已 `DONE`（merge f1ac71b1）；`F017`（侧边栏）与 `F018`（搜索）无依赖边，两者对 `frontend/src/App.vue` 的所有权冲突已解除。
- `F020` / `F021` 已完成：F020 DONE（merge e4291a1）、F021 DONE（merge 011d05d）。
- `F022` 已完成：DEC-024 已 RESOLVED，扩展 `ip_address_ranges` 加 3 个可空列（name / subnet_mask / vlan）+ migration 0010（merge b467e89）。全部 V1 交付（20 DONE + 1 CANCELLED）。
- `F023` 已完成：DEC-025 已 RESOLVED，修订 R-IP-006 / R-IP-009 与 f021 契约（自动分配必须指定活跃范围段，耗尽不回退，merge e234908）；**无数据库变更**。全部 V1 交付（21 DONE + 1 CANCELLED）。
- `F011` 为 `CANCELLED`（用户 2026-09-18 决定），不在实施顺序中。
- `F024` / `F025` 为 2026-09-24 新增（DRAFT）：F024 依赖 F009，F025 依赖 F019；语义待 DEC-026 / DEC-027 裁定，2026-09-24 已**部分确认**（「节点」仅 BareMetal、IP 经 NIC、URL 来源 Service.url、无绑定值不展示、多网卡 / 多 IP 分行展示），其余仍 OPEN，**未获批准前不进入实施顺序**。
- 优先级（P0 / P1 / P2）不代表执行顺序；执行顺序以上方拓扑序为准。
