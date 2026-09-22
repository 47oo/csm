# CSM Backlog

> Status: 由 `docs/project/project-plan.yaml` **生成**（人类可读视图，不构成机器状态的唯一来源）
> Source of Truth: `docs/project/project-plan.yaml`
> Generated: 2026-09-22（增量四登记 F023；`project.status = ACCEPTED`）
> 生成依据：`project.status = ACCEPTED`；计数 `{'READY': 1, 'IN_PROGRESS': 0, 'BLOCKED': 0, 'DRAFT': 0, 'DONE': 20, 'CANCELLED': 1}`

**2026-09-22（增量四）**：收到输入「当配置多套 IP 地址范围的时候，网卡无法选择使用哪套来自动分配 IP 地址」。
诊断结论：这是 F021 已确认规则的限制（f021 §1.6 / R-IP-006：自动分配在全部活跃范围**并集**取全局最小），
不是实现缺陷。用户就 **DEC-025** 裁定：① 自动分配**必须显式指定**一个活跃范围段（必填 `ip_address_range_id`）；
② 所选范围段耗尽 → `409 NO_AVAILABLE_IP` 且**不回退**；③ **手动分配不变**；④ 按 Feature Workflow 执行。
据此新增 **F023（自动分配时指定 IP 地址范围段，READY）**、**DEC-025（RESOLVED）** 与 **M12**；E02 追加 F023。
`project.status` 由 DONE 转 **ACCEPTED**；**既有一律不变**：20 DONE + 1 CANCELLED、M1–M11、全部 merge commit /
Tester / Review 证据与各 Feature 的 git 元数据均原样保留。**仅**按 DEC-025 修订 R-IP-006 / R-IP-009。

**2026-09-21（增量三·终）**：F022 完成（merge b467e89，Reviewer = APPROVED WITH FOLLOW-UP），**F022 DONE**；M11 DONE。
全部 V1 Feature 处置完毕：**20 DONE + 1 CANCELLED（F011）**；`project.status = DONE`。

**2026-09-21（增量三·续）**：用户**采纳 DEC-024 推荐方案**，本次增量计划获批准（`project.status` 转 **ACCEPTED**）。
裁定：为网段新增 3 个**可选**字段 `name` / `subnet_mask` / `vlan` 并修订 **R-IP-004**；name 同 Cluster 活跃唯一（大小写敏感、软删释放）；
mask 为 dotted-quad IPv4 且不强制与 start–end 自洽；vlan 为整数 1–4094 且不唯一；扩展既有 `ip_address_ranges` + migration 0010；
不推翻 F020 / F021。**DEC-024 RESOLVED**；**F022 转 READY**（可进入 Feature Workflow）。
**既有结论不变**：19 DONE + 1 CANCELLED、M1–M10、全部 merge commit / Tester / Review 证据与各 Feature 的 git 元数据均原样保留。

**2026-09-21（增量三）**：收到**未获批准**输入「为每个自定义网段增加自定义名称 / 子网掩码 / VLAN」。据此新增
**F022（网段自定义名称 / 子网掩码 / VLAN 标注，当时是 DRAFT）**、**DEC-024（当时是 OPEN）** 与 **M11**；E02 追加 F022。
该诉求直接冲突于已确认 **R-IP-004** 的字段封闭立场（明文无 name/description 字段且不动 CIDR/VLAN），须由用户 / Product 裁定。
`project.status` 曾由 DONE 暂时转 **DRAFT**（仅表示新增输入待批准，不代表既有交付被推翻）。

**2026-09-21（终）**：F021 完成（merge 011d05d，Reviewer = APPROVED WITH FOLLOW-UP），**F021 DONE**；M10 DONE。
全部 V1 Feature 处置完毕：**19 DONE + 1 CANCELLED（F011）**；`project.status = DONE`。

**2026-09-21**：F020 完成 Feature Workflow（head ca9ae73→84d5c17，merge e4291a1；Reviewer = APPROVED WITH FOLLOW-UP），**F020 DONE**；F021 由 **BLOCKED 转 READY**（唯一阻塞 F020 已解除）。M10 进度为 F020 DONE / F021 READY。

**2026-09-20（二）增量**：收到未获批准输入「对每个集群允许设定多个IP地址范围段，在分配IP的时候支持自动或者手动分配IP地址，自动分配IP的时候，默认选择当前第一个最小的IP地址」。
据此**新增** F020（IP 地址范围段管理）、F021（IP 自动 / 手动分配）、DEC-023（后已 RESOLVED）与 M10，`project.status` 由 DONE 转 **DRAFT**（待用户批准）。
**2026-09-20（续）**：用户就 DEC-023 采纳推荐方案并明确「范围内仍有活跃 IP 时禁止删除范围段」；DEC-023 RESOLVED，F020 转 READY、F021 转 BLOCKED。计划仍待批准。
该输入提出**两项此前被 F005 显式排除**的新产品能力，且严重欠定义，属新产品规则；**既有 R-IP-001 ~ R-IP-003 保持不变**，F005 已 DONE 的实现与结论不被推翻。
**既有一律不变**：17 DONE + 1 CANCELLED、M1–M9、全部 merge SHA / Tester / Review 证据与各 Feature 的 git 元数据均原样保留。

**2026-09-18（五）增量**：收到未获批准输入「将搜索的内容进行聚合，比如输入ip地址，显示裸金属 cn001,ip xxx,网卡eth0 等等」。
据此**新增** F019（搜索结果聚合视图，DRAFT）、DEC-022（OPEN）与 M9，`project.status` 由 DONE 转 **DRAFT**（待用户批准）。
该输入与已确认的 R-QUERY-005「单一混合列表（不按资源类型分组）」「除结果总数外不提供统计 / 聚合」直接冲突，语义未确认。
**既有结论不变**：16 DONE + 1 CANCELLED、M1–M8、全部 merge SHA / Tester / Review 证据与各 Feature 的 git 元数据均原样保留。

**2026-09-20**：用户批准增量计划后，就 **DEC-022** 逐一裁定（8 项 + 3 处澄清，见 DEC-022 RESOLVED）。F019 由 **DRAFT 转 READY** 并已完成 Feature Workflow（merge 292345e8），M9 DONE。

**重建说明**：本文件由 `project-plan.yaml` 重新生成，取代此前陈旧的正文（旧版仍写「Feature 总数 14 / DONE 10 / F007 READY / M4 进行中」等）。
历史结论（F011 取消、M5 的实际结局、各 Feature 的 merge SHA、各条 follow-up）均按计划原样保留，未因重建而丢失。

需求基线：`docs/product/requirements.md`（CONFIRMED BASELINE，**63 条规则**，含 2026-09-18 新增的 R-QUERY-005 与 2026-09-20 新增的 R-QUERY-006）。
领域模型：`docs/product/domain-model.md` / `domain-model.yaml`。
架构：`docs/architecture/`（ADR-0001 ~ ADR-0005 全部 ACCEPTED），`docs/api/api-conventions.md`。

## 汇总

| 维度 | 值 |
|---|---|
| Feature 总数 | 22 |
| P0 | 7（F012、F013、F014、F015、F001、F002、F009） |
| P1 | 14（F004、F005、F006、F007、F008、F010、F011、F016、F018、F019、F020、F021、F022、F023） |
| P2 | 1（F017） |
| DONE | 20 |
| CANCELLED | 1（F011） |
| DRAFT | 0 |
| READY / IN_PROGRESS / BLOCKED | 1 / 0 / 0（READY: F023） |
| Decisions 总数 | 25（OPEN **0**） |

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
| F020 | IP 地址范围段（地址池）管理 | P1 | **DONE** | F001, F005 | READY | e4291a1e |
| F021 | IP 地址自动 / 手动分配 | P1 | **DONE** | F020, F005, F004, F002 | READY | 011d05df |
| F022 | 网段自定义名称 / 子网掩码 / VLAN 标注 | P1 | **DONE** | F020 | READY | b467e891 |
| F023 | 自动分配时指定 IP 地址范围段 | P1 | **READY** | F020, F021 | REQUIRED | — |

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
| F019 | 搜索结果聚合视图 | P1 | **DONE** | F018 | READY | 292345e8 |

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
| M9 | 搜索结果聚合视图 | F019 | **DONE** |
| M10 | IP 地址范围段与自动 / 手动分配 | F020, F021 | **DONE** |
| M11 | 网段自定义名称 / 子网掩码 / VLAN | F022 | **DONE** |
| M12 | 自动分配指定 IP 地址范围段 | F023 | **待执行（F023 READY）** |

`M5` 的实际结局：`F010` DONE、`F011` **由用户于 2026-09-18 取消**（批量导入不在 V1 交付范围；`requirements.md` §18 的 R-IMPORT-001~004 规则文本按原样保留但标注为不交付）——该里程碑除批量导入外已达成。

`M10` 为本次新增输入的待批里程碑；进入条件至少含：DEC-023 由用户裁定、Product 在 §12 新增 / 修订产品规则、F005 已 DONE。详见 `milestones.md`。

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
| DEC-022 | product | RESOLVED | F019, F018 |
| DEC-023 | product | RESOLVED | F020, F021, F005 |
| DEC-024 | product | RESOLVED | F022, F020, F021, F005 |
| DEC-025 | product | RESOLVED | F023, F021, F020 |

`DEC-020`（侧边栏）、`DEC-021`（关键字搜索）与 `DEC-022`（搜索结果聚合）均已 RESOLVED。
`DEC-022` 已于 2026-09-20 由用户裁定：结果为单一扁平混合列表、按命中项关联链聚合、做关系扩展、采用方案 A（命中行 + 缩进关联行）、仅显示搜索涉及的资源、不去重、标识字段优先于描述性字段排序、取代 F018 扁列表。

`DEC-023`（IP 地址范围段 / 地址池与自动 / 手动分配）已于 2026-09-20 由用户裁定为 **RESOLVED**：范围段用 start–end（IPv4）、恰属一个 Cluster、同 Cluster 不重叠、跨 Cluster 可重复、无状态、软删，且**范围内有活跃 IP 时禁止删除**；分配沿用 IPAddress、必选绑定活跃 NIC，自动取并集内最小未占用 IPv4，占用以活跃 IPAddress 字面相等判定、软删释放，无隐式保留地址，耗尽返回非 500 错误，不新增超出 R-IP-001 的唯一性。

## Open Questions（阻塞项，权威见计划 `features[].open_questions`）

**F022 NQ-1 ~ NQ-8 已随 DEC-024 RESOLVED（2026-09-21 用户采纳推荐方案）全部解除 blocking**：修订 R-IP-004 新增 3 个可选字段；
name 可选 / 同 Cluster 活跃唯一 / 大小写敏感 / 软删释放；subnet_mask dotted-quad IPv4 且不强制与 start–end 自洽；vlan 1–4094 不唯一；
扩展既有 `ip_address_ranges` + migration 0010；不推翻 F020 / F021，F021 分配不按掩码 / VLAN 过滤。
详见 `decisions_required[DEC-024].resolution`。

F020 / F021 的 NQ 已于 2026-09-20 由用户随 **DEC-023 RESOLVED** 全部裁定（摘要见上）。
F019 的 NQ-1 ~ NQ-8 已于 2026-09-20 由用户裁定（DEC-022 RESOLVED），不再阻塞。

## Follow-ups（聚合；权威见计划 `planning_status.follow_ups`）

- **from_f022_review**：REV-1, REV-2, REV-3（均 LOW/NOTE）
- **from_f021_review**：REV-1（已修）, REV-2, REV-3（均 NOTE）
- **from_f020_review**：REV-1, REV-2（已修）, REV-3 / DEF-02, NOTE-1, DEF-01（Test Infra）
- **from_f019_review**：REV-1, REV-2, REV-3, REV-4
- **from_f018_review**：F018-LOW-1, F018-NOTE-1, F018-NOTE-3, F018-NOTE-4, F018-NOTE-5
- **from_f017_review**：F017-LOW-2, F017-NOTE-4
- **from_f016_review**：REV-1, REV-4, REV-5, REV-6, F016-T-01, REV-2 / REV-3
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
- **post_v1_maintenance**：merged 288dd42；F005 REV-3 / F010 REV-2 / F004 REV-2 / F010 REV-3 / F002-T-01（另见 still_open）
