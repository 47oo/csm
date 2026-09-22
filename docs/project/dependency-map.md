# CSM Feature Dependency Map

> Status: 由 `docs/project/project-plan.yaml` **生成**（人类可读视图，不构成机器状态的唯一来源）
> Source of Truth: `docs/project/project-plan.yaml`
> Generated: 2026-09-21（增量三已批准；`project.status = ACCEPTED`）
> 生成依据：`project.status = ACCEPTED`；计数 `{'READY': 1, 'IN_PROGRESS': 0, 'BLOCKED': 0, 'DRAFT': 0, 'DONE': 19, 'CANCELLED': 1}`

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
| F022 网段自定义名称 / 子网掩码 / VLAN 标注 | READY | F020 | database, backend, frontend |

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

F020 / F021（本次新增）依赖既有网络资源链：

```text
F001 Cluster 登记与管理 (P0, DONE) ──┬──> F020 IP 地址范围段（地址池）管理 (P1, DONE)  ← merge e4291a1
F005 IPAddress 管理 (P1, DONE) ──────┘        └──> F021 IP 地址自动 / 手动分配 (P1, DONE)  ← merge 011d05d

F022（网段元数据扩展，本次新增）依赖已交付的 F020：

```text
F020 IP 地址范围段（地址池）管理 (P1, DONE) ──> F022 网段自定义名称 / 子网掩码 / VLAN 标注 (P1, READY)
```

> F021 **不是** F022 的前置；若裁定要求分配按掩码 / VLAN 过滤，属对 F021 的**前向影响**，待 DEC-024 裁定后评估，不画反向依赖边。
F004 NetworkInterface 管理 (P1, DONE) ─────────┘
F002 BareMetal 登记与管理 (P0, DONE) ──────────┘
```

> F021 依赖 F020（被分配的地址范围段）、F005（IPAddress 登记 / 唯一性 / 受控 `cluster_id` 推导模型）、F004/F002（NQ-1 已裁定分配产物为绑定 NetworkInterface 的 IPAddress，故二者为真实前置）。F021 唯一阻塞 F020 已于 2026-09-21 DONE，故 F021 转 READY。

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
21. F022  READY（依赖 F020 已 DONE；DEC-024 RESOLVED，拟扩展 ip_address_ranges + migration 0010）
```

## 可并行执行的 Feature

- 当前 **READY：F022**（依赖 F020 已 DONE；DEC-024 已 RESOLVED，可进入 Feature Workflow）。
- F020 与 F021 之间有真实依赖（F021 → F020），**不可并行**；F020 DONE 后 F021 方可启动。
- 若后续一个 Milestone 内出现多个相互无依赖的 Feature，可并行；但必须划清文件所有权（`docs/project/git-workflow.md` §3）。

## 说明

- `F019` 已 `DONE`（merge 292345e8，Reviewer = APPROVED WITH FOLLOW-UP）；产品语义由 DEC-022 裁定（2026-09-20）。F019 遗留 REV-1 / REV-2（测试覆盖回退，LOW）与 REV-4（NOTE）作为非阻塞 follow-up。
- `F018` 已 `DONE`（merge f1ac71b1）；`F017`（侧边栏）与 `F018`（搜索）无依赖边，两者对 `frontend/src/App.vue` 的所有权冲突已解除。
- `F020` / `F021` 已完成：F020 DONE（merge e4291a1）、F021 DONE（merge 011d05d）。
- `F022` 为本次增量新增的 Feature（READY）：DEC-024 已 RESOLVED（2026-09-21），拟扩展 `ip_address_ranges` 加 3 个可空列（name / subnet_mask / vlan）+ migration 0010；依赖 F020（已 DONE）。全部既有 V1 交付（19 DONE + 1 CANCELLED）未被推翻。
- `F011` 为 `CANCELLED`（用户 2026-09-18 决定），不在实施顺序中。
- 优先级（P0 / P1 / P2）不代表执行顺序；执行顺序以上方拓扑序为准。
