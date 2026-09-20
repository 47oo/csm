# CSM Backlog

> Status: 由 `docs/project/project-plan.yaml` **生成**（人类可读视图，不构成机器状态的唯一来源）
> Source of Truth: `docs/project/project-plan.yaml`
> Generated: 2026-09-20（增量更新：用户批准 F019 / DEC-022 / M9 增量计划，`project.status = ACCEPTED`）
> 生成依据：`project.status = ACCEPTED`；计数 `{'READY': 0, 'IN_PROGRESS': 0, 'BLOCKED': 0, 'DRAFT': 1, 'DONE': 16, 'CANCELLED': 1}`

**2026-09-18（五）增量**：收到未获批准输入「将搜索的内容进行聚合，比如输入ip地址，显示裸金属 cn001,ip xxx,网卡eth0 等等」。
据此**新增** F019（搜索结果聚合视图，DRAFT）、DEC-022（OPEN）与 M9，`project.status` 由 DONE 转 **DRAFT**（待用户批准）。
该输入与已确认的 R-QUERY-005「单一混合列表（不按资源类型分组）」「除结果总数外不提供统计 / 聚合」直接冲突，语义未确认。
**既有一律不变**：16 DONE + 1 CANCELLED、M1–M8、全部 merge SHA / Tester / Review 证据与各 Feature 的 git 元数据均原样保留。

**重建说明**：本文件由 `project-plan.yaml` 重新生成，取代此前陈旧的正文（旧版仍写「Feature 总数 14 / DONE 10 / F007 READY / M4 进行中」等）。
历史结论（F011 取消、M5 的实际结局、各 Feature 的 merge SHA、各条 follow-up）均按计划原样保留，未因重建而丢失。

需求基线：`docs/product/requirements.md`（CONFIRMED BASELINE，**62 条规则**，含 2026-09-18 新增的 R-QUERY-005）。
领域模型：`docs/product/domain-model.md` / `domain-model.yaml`。
架构：`docs/architecture/`（ADR-0001 ~ ADR-0005 全部 ACCEPTED），`docs/api/api-conventions.md`。

## 汇总

| 维度 | 值 |
|---|---|
| Feature 总数 | 18 |
| P0 | 7（F012、F013、F014、F015、F001、F002、F009） |
| P1 | 10（F004、F005、F006、F007、F008、F010、F011、F016、F018、F019） |
| P2 | 1（F017） |
| DONE | 16 |
| CANCELLED | 1（F011） |
| BLOCKED | 0 |
| READY / IN_PROGRESS / DRAFT | 0 / 0 / 1（F019） |
| Decisions 总数 | 22（OPEN **1**：DEC-022） |

## 按 Epic

### E01 基础资源管理

| ID | Feature | Priority | 状态 | 依赖 | Contract | Merge |
|---|---|---|---|---|---|---|
| F001 | Cluster 登记与管理 | P0 | **DONE** | F012 | READY | 5a96ad0c |
| F002 | BareMetal 登记与管理 | P0 | **DONE** | F001 | READY | ef39557f |
| F016 | Cluster 登记与改名 UI | P1 | **DONE** | F001, F013, F014 | READY | 93729191 |

### E02 网络资源管理

| ID | Feature | Priority | 状态 | 依赖 | Contract | Merge |
|---|---|---|---|---|---|---|
| F004 | NetworkInterface 管理 | P1 | **DONE** | F002 | READY | 4a99fa00 |
| F005 | IPAddress 管理 | P1 | **DONE** | F004 | READY | 7beb6e72 |

### E03 虚拟资源管理

| ID | Feature | Priority | 状态 | 依赖 | Contract | Merge |
|---|---|---|---|---|---|---|
| F006 | VirtualMachine 登记与管理 | P1 | **DONE** | F002 | READY | 01077bed |
| F007 | Container 资源模型与登记 | P1 | **DONE** | F006, F002 | READY | ff347be7 |

### E04 服务资源管理

| ID | Feature | Priority | 状态 | 依赖 | Contract | Merge |
|---|---|---|---|---|---|---|
| F008 | Service 资源管理与 Cluster 共享关联 | P1 | **DONE** | F001, F002, F006, F007 | READY | f7733783 |

### E05 资源查询与视图

| ID | Feature | Priority | 状态 | 依赖 | Contract | Merge |
|---|---|---|---|---|---|---|
| F009 | Cluster 视角资源查询 | P0 | **DONE** | F001, F002 | READY | 6529b0dc |
| F010 | 资源详情与关联查询 | P1 | **DONE** | F001, F002, F004, F005, F006, F007, F008 | READY | 334b4ca3 |
| F018 | 集群内资源关键字搜索 | P1 | **DONE** | F001, F002, F004, F005, F006, F007, F008 | READY | f1ac71b1 |
| F019 | 搜索结果聚合视图 | P1 | **DRAFT** | F018 | REQUIRED | — |

### E06 数据导入

| ID | Feature | Priority | 状态 | 依赖 | Contract | Merge |
|---|---|---|---|---|---|---|
| F011 | Excel 模板与批量导入 | P1 | **CANCELLED** | F001, F002, F004, F005, F006, F007, F008 | — | — |

### E07 平台基础能力

| ID | Feature | Priority | 状态 | 依赖 | Contract | Merge |
|---|---|---|---|---|---|---|
| F012 | 项目基础框架与运行环境 | P0 | **DONE** | — | READY | 3b8646c7 |
| F013 | 本地账号认证与会话 | P0 | **DONE** | F012 | READY | 4d2e48c7 |
| F014 | 逻辑删除与数据一致性治理 | P0 | **DONE** | F012 | READY | 184ee61f |
| F015 | 内网部署与运行环境 | P0 | **DONE** | F012, F013 | NOT_REQUIRED | 06e655a2 |
| F017 | 应用外壳侧边栏导航 | P2 | **DONE** | F012, F013, F001, F002, F004, F005, F006, F007, F008, F010 | NOT_REQUIRED | 8fc88324 |

## Milestones

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
| M9 | 搜索结果聚合视图 | F019 | **DRAFT（待批准）** |

`M5` 的实际结局：`F010` DONE、`F011` **由用户于 2026-09-18 取消**（批量导入不在 V1 交付范围；`requirements.md` §18 的 R-IMPORT-001~004 规则文本按原样保留但标注为不交付）——该里程碑除批量导入外已达成。

## Blocking Decisions

| ID | type | 状态 | 影响 Feature |
|---|---|---|---|
| DEC-001 | product | RESOLVED | F001, F002, F009, F010, F011 |
| DEC-002 | product | RESOLVED | F011 |
| DEC-003 | product | RESOLVED | F008, F010, F011 |
| DEC-004 | product | RESOLVED | F006, F007, F010, F011 |
| DEC-005 | product | RESOLVED | F007, F010, F011 |
| DEC-006 | product | RESOLVED | F004, F005, F006, F007, F008 |
| DEC-007 | product | RESOLVED | F001 |
| DEC-008 | architecture | RESOLVED | F006, F007, F008 |
| DEC-009 | architecture | RESOLVED | F001, F002, F004, F005, F006, F007, F008, F009, F010, F011, F012, F013, F014, F015 |
| DEC-010 | database | RESOLVED | F004, F005, F006, F007, F008, F012, F015 |
| DEC-011 | architecture | RESOLVED | F001, F002, F004, F005, F006, F007, F008, F009, F010, F011, F012 |
| DEC-012 | database | RESOLVED | F014, F001, F002, F004, F005, F006, F007, F008 |
| DEC-013 | architecture | RESOLVED | F013, F015 |
| DEC-014 | architecture | RESOLVED | F001, F002, F004, F005, F006, F007, F008, F009, F010, F011, F012 |
| DEC-015 | process | RESOLVED | F012, F015 |
| DEC-017 | product | RESOLVED | — |
| DEC-018 | product | RESOLVED | — |
| DEC-019 | product | RESOLVED | — |
| DEC-016 | architecture | RESOLVED | F015 |
| DEC-020 | product | RESOLVED | F017 |
| DEC-021 | product | RESOLVED | F018, F002, F005, F009, F010 |
| DEC-022 | product | **OPEN** | F019, F018 |

`DEC-020`（侧边栏）与 `DEC-021`（关键字搜索）均已 RESOLVED。
`DEC-022`（搜索结果聚合语义 vs R-QUERY-005 扁列表 / 不提供聚合条款）**OPEN**，待用户 / Product 裁定；完整歧义见下方 Open Questions。

## Open Questions（阻塞项，权威见计划 `features[].open_questions`）

### F019 搜索结果聚合视图（status: DRAFT；**NQ-1 ~ NQ-8 均为 blocking，未确认前不得实现**）

| 编号 | 一句话 | blocking |
|---|---|---|
| NQ-1 | 聚合的**分组单位**是什么（按关联 BareMetal / 主机分组？按命中项的关联链分组？还是仅补充上下文不真正分组？） | true |
| NQ-2 | 是否做**关系扩展**（把自身字段不匹配但相关的资源，如 cn001 / eth0，也纳入结果）？ | true |
| NQ-3 | 聚合结果的**信封 / 呈现形态**（每组含哪些资源、字段结构、UI 如何呈现）？ | true |
| NQ-4 | **未关联到任何 BareMetal** 的命中资源如何处置？ | true |
| NQ-5 | **跨组重复资源如何去重**（同一资源与多个主机相关时）？ | true |
| NQ-6 | **排序与分页语义**（组级 vs 条目级；R-QUERY-005 明文不承诺排序）？ | true |
| NQ-7 | **是否保留 F018 的扁平列表，或以其完全取代**（与 R-QUERY-005 直接冲突）？ | true |
| NQ-8 | **产品规则落点**：Product 修订 R-QUERY-005 或新增聚合规则，F019 才能挂 requirement ID | true |
| NQ-9 | 入口与前置条件是否沿用 F018（外壳全局搜索 + 先选定单一 Cluster）？ | false |

## Follow-ups（聚合；权威见计划 `planning_status.follow_ups`）

- **from_f016_review**：REV-1, REV-4, REV-5, REV-6, F016-T-01, REV-2 / REV-3
- **from_f018_review**：F018-LOW-1, F018-NOTE-1, F018-NOTE-3, F018-NOTE-4, F018-NOTE-5
- **from_f017_review**：F017-LOW-2, F017-NOTE-4
- **from_f016_test**：F016-T-01
- **from_f010_review**：REV-2, REV-3, Framework OPEN#6（承）
- **from_f008_review**：REV-F008-2, REV-F008-3, F004 REV-2（承）
- **from_f007_review**：REV-2, REV-3, F014 残余风险（承）
- **from_f005_review**：REV-3
- **from_f004_review**：REV-2
- **from_f006_review**：REV-3 / F007 预期演进点
- **from_f002_review**：F002-T-01 / REV-2, REV-3, REV-5, REV-6
- **from_f015_review**：REV-01, NOTE-01, NOTE-02, NOTE-03, NOTE-04, NOTE-05
- **from_f014_review**：F014-T-01, NOTE-01, NOTE-02
- **from_f013_review**：REV-01, REV-03, REV-04, F013-F-01
- **from_f001_review**：REV-1, REV-2, F-01
- **from_f012_review**：F-03, F-01, F-02, N-01
