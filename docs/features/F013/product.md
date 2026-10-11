# F013 全局搜索与 Dashboard — PRODUCT 阶段报告

- **Feature**：F013 全局搜索与 Dashboard（FEATURE，P1，M6 检索、导入与系统功能；deps F003、F004、F005、F006、F008、F009、F010、F011）
- **阶段**：PRODUCT；**结论**：`READY FOR ARCHITECT`
- **依据**：requirements-v3.md revision 3（§4、§4.1、§5、§7、§11/§11.1、§12、§13/§13.1–13.3、§14、§15、§16、§17、§18、§19、§20、§21、§22、§23、§25、§26、§27、§28、§31 T32、§32、§33、§35.2 Q02-A/Q04-A/Q04-B/Q10-B、§35.3 D01/D02）；plan_revision 4 F013（用户 2026-10-06 批准）；已完成 Feature 产品/契约 F003/F004/F005/F006/F008/F009/F010/F011/F012；`docs/features/F010/product.md`（§20 容量数据口径，A20/A26、I-7）与 `docs/api/F010.md` v1 §6.9（`/api/v1/networks/{id}/capacity`）；`docs/architecture/d01-conventions.md` v11；`docs/product/domain-model.md`；`.pi/skills/resource-domain/SKILL.md`。

## 1. 目标与范围

### 1.1 目标
在已交付的各资源域（Cluster / Resource / BareMetal / VM / Interface / Network / IPPool / IPAddress / Service / ServiceEndpoint）之上，提供两项跨域只读能力：
1. **首页统一全局搜索**（§17/§33）：以 hostname、IP、Cluster、Service 为入口，支持输入与模糊匹配，并能定位到对应 Resource 或跳转到相应详情页。
2. **Dashboard 汇总**（§20）：集中展示 Cluster / Resource / BareMetal / VM / Network 数量与 IP 使用情况（Network 与 AUTO 池的可分配总量 / 已占用 / 剩余），供运维人员快速掌握资源总览。

本 Feature 是查询与汇总的聚合入口，不引入新的资源实体、字段或业务状态；Dashboard 不是监控面板（§3、§20）。

### 1.2 本次范围（CONFIRMED，除标注 PROPOSED 外）
- **全局搜索入口**（§17）：首页统一搜索入口；搜索框与下拉选择均允许输入与模糊搜索；至少支持 hostname、IP、Cluster、Service；能定位到对应 Resource（§17/§33）；模糊搜索使用 pg_trgm（§26）。
- **搜索结果类型与定位**（§17/§33，命中定义见 §2.2）：hostname 命中 Resource；IP 命中其所绑 Interface → Resource（未绑定 IP 无 Resource，见 I-6）；Cluster 命中该 Cluster；Service 命中承载该 Service 的 Resource。
- **默认软删隐藏**（§21）：搜索默认排除已软删对象。
- **Dashboard 计数**（§20）：Cluster / Resource / BareMetal / VM / Network 数量。
- **Dashboard IP 使用情况**（§20/T32）：按 Network 显示可分配总量、已占用量、剩余可用量；按 AUTO 池显示可分配总量与剩余可用量；口径见 §3.2。
- **权限/可见性**（§23）：VIEWER / EDITOR / ADMIN 均可搜索与查看 Dashboard；不得出现新增/修改/删除入口；查看已删/恢复仍限 ADMIN。
- **只读**（§22）：搜索与 Dashboard 为查询操作，不写 Audit；无副作用。

### 1.3 使用者
VIEWER / EDITOR / ADMIN 全体基础角色。运维人员据搜索回答 §33「hostname 属于哪个集群」「某 IP 是哪台机器」「机器运行哪些 Service」「vm001 的宿主机」等；据 Dashboard 快速查看资源规模与 IP 使用/剩余，判断是否需要扩容或整理。

## 2. 搜索行为定义（§17/§33）

### 2.1 CONFIRMED 行为
- 首页统一搜索入口；搜索框与下拉选择均允许输入和模糊搜索（§17）。例如 `gpu07` 命中 `gpu0701`、`gpu0702`、`gpu0725`。
- 至少支持 hostname、IP、Cluster、Service 四类（§17），并能找到对应 Resource（§17/§33）。
- SN、MAC、Role、GPU Model 搜索为后续扩展，**本期不强制**（§17，PROPOSED 不计入验收）。
- 数据库使用 pg_trgm 支持模糊搜索（§26）；GIN 索引为建议方案，具体索引在数据库设计中签核（§26/§17）。
- 默认隐藏已软删对象（§21）；名称/地址匹配使用与唯一性一致的归一化规则（§4.1/§7，D01 §5），如 hostname 大小写不敏感、去首尾空白。

### 2.2 「命中对应 Resource」的精确定义（CONFIRMED 目的 + PROPOSED 返回形态）
§17 要求「能找到对应 Resource」，但未逐类规定返回形态。下表给出可实施定义；**返回对象集合与展开范围整体记为 OPEN（I-5/I-6），默认按 PROPOSED 列执行**，交 Product / Architect 在 CONTRACT 确认：

| 查询类型 | 匹配对象与字段 | 命中返回（PROPOSED 默认） | 依据/状态 |
| --- | --- | --- | --- |
| hostname | Resource.hostname（归一化：trim + ASCII 小写，§7） | 直接返回该 Resource（object_type=`resource`，含 cluster 归属） | §17/§33 CONFIRMED 目的 |
| IP | IPAddress.address（IPv4，精确优先，允许前缀/模糊） | 返回 IPAddress；若已绑 Interface →（经 Interface）返回其所属 Resource；若未绑定 → 返回 IPAddress 结果但**无 Resource 归属** | §17/§33、§13（未绑定 IP 存在） |
| Cluster | Cluster.code / name（code 不敏感，§5；name 模糊） | 返回该 Cluster（object_type=`cluster`），可从结果跳转 Cluster Detail；**是否同时展开该 Cluster 下 Resources 记为 OPEN（I-5）** | §17/§19 |
| Service | Service.name（归一化：trim + ASCII 小写，§4.1） | 返回承载该 Service 的 Resource（Service 属 Resource，§15；object_type=`resource`，可附 service 摘要） | §17/§33 |

- 单条结果至少暴露稳定 ID 与 object_type 以支撑跳转（§4；Resource→§18 Resource Detail，Cluster→§19 Cluster Detail）。
- 去重（PROPOSED，I-5）：同一 Resource 被多条路径命中（如 hostname 与 Service 同属一个 Resource、IP 经 Interface 回到同一 Resource）时，**按 Resource 身份去重**，避免重复展示；不同 Cluster 的相同 IP/名称是不同对象（§7/§14），不去重。
- 排序（PROPOSED，I-5）：未定义；默认按匹配相似度降序、同分按 object_type 分组与稳定 ID 次序；最终排序交 Architect/CONTRACT 裁定。

### 2.3 模糊匹配实现边界
- pg_trgm（§26）为已确认要求；匹配算子（`ILIKE`、`similarity`/`%`、`word_similarity`）、相似度阈值与 GIN 索引表达式属**数据库设计签核项**（§26/§17；plan F013「pg_trgm 索引引入点 F004 或 F013 由首个需要模糊查询的 Feature Contract + D02 裁定」）。
- 归一化后比较，与 §4.1/§7/D01 §5 一致：hostname、Cluster code、Service name 大小写不敏感；中文与内部普通空格保留；不自动合并空格。
- IP 匹配属地址串匹配，不参与名称归一化；是否使用 pg_trgm 或前缀匹配交设计（PROPOSED：精确匹配优先，前缀/trigram 兜底）。

## 3. Dashboard 行为定义（§20）

### 3.1 计数（CONFIRMED）
- 展示 Cluster / Resource / BareMetal / VM / Network 数量（§20）。
- 计数口径（PROPOSED 默认，交 CONTRACT 确认，依据 §20 + §21）：
  - Cluster 数 = 未软删 Cluster 数（**含 INACTIVE**，§5/§21）。
  - Resource 数 = 未软删 Resource 总数（BARE_METAL + VIRTUAL_MACHINE，§6）。
  - BareMetal 数 = 未软删 `resource_type = BARE_METAL` 数。
  - VM 数 = 未软删 `resource_type = VIRTUAL_MACHINE` 数。
  - Network 数 = 未软删 Network 数（**含 INACTIVE**，§11/§21）。
- 全局口径（PROPOSED，I-8）：展示跨全部 Cluster 的全局总数；是否提供按 Cluster 过滤记为 OPEN，不默认新增。

### 3.2 IP 使用情况与容量口径（§20 / T32，CONFIRMED 公式）
按 `docs/api/F010.md` v1 §6.9 / requirements §20 公式展示，F013 只消费不改口径：

```text
基础可用地址集合：按 CIDR 前缀（§11.1）
  可分配集合 = 基础可用地址集合 − gateway − RESERVED 池范围 − 禁用地址   （按集合去重）
  Network 可分配总量 = |可分配集合|
  Network 已占用量   = 该 Network 下未删除 IP 数量（含未绑定 Interface 的 IP；含池外手动地址）
  Network 剩余可用量 = Network 可分配总量 − Network 已占用量
  AUTO 池可分配总量 = |该池范围 ∩ Network 可分配集合|
  AUTO 池剩余可用量 = AUTO 池可分配总量 − 当前位于该交集的未删除 IP 数量
```

必须满足的展示规则（CONFIRMED，§20/T32）：
1. **排除项**：gateway、RESERVED 池范围、禁用地址从可分配范围排除；gateway 同时位于 RESERVED 池时不重复扣减（集合去重）。
2. **占用**：未删 IP 记录，**包含尚未绑定 Interface 的 IP**；软删除 IP 不计占用。
3. **Network 口径**：包括允许手动分配的**池外地址**；不以整个 CIDR 大小替代池容量。
4. **AUTO 口径**：仅计该池范围与 Network 可分配集合的交集；占用按**当前地址所在范围**计算，不按历史分配来源。
5. **分别展示**：容量与 ACTIVE / INACTIVE、auto_allocate 操作许可分别展示；停用不会把容量或占用清零。
6. **负值**（F010 DR-130 已裁定，复用）：`remaining` 按公式直接相减，不设下限 0、不截断，可为负并原样呈现。
7. **展示形态**（PROPOSED，I-7）：Dashboard 以 **per-Network 行**展示 Network 容量，并在每行下/旁展示该 Network 的 AUTO 池容量；是否再提供跨 Network 的汇总合计记为 OPEN（§20 未定义全局合计口径，且不同 Cluster 可含相同地址，全局相加易误导，**不默认新增**）。

### 3.3 只读与权限
- 搜索与 Dashboard 均为读操作：不产生 Audit 记录（§22 仅关键数据修改写 Audit），无任何写副作用（I-4）。
- §23 权限矩阵：查询、搜索、详情对所有基础角色允许；Dashboard 属查询，VIEWER/EDITOR/ADMIN 均可访问；不得出现新增/修改/删除/恢复入口；查看已删与恢复仍限 ADMIN。

## 4. 领域影响分析

| 对象/视图 | 关系 | 作用域 | 生命周期 | 依据及状态 | 未决/影响 |
| --- | --- | --- | --- | --- | --- |
| 搜索结果（派生视图，非新实体） | 跨 Resource/Cluster/IPAddress/Interface/Service | 全局只读 | 无（不落库） | §17/§33 CONFIRMED 目的；返回形态 PROPOSED | 去重/排序/展开范围 OPEN（I-5） |
| Dashboard 计数（派生视图） | 聚合 Cluster/Resource/Network 未删记录 | 全局只读 | 无 | §20 CONFIRMED | 全局 vs 按 Cluster 过滤 OPEN（I-8） |
| Dashboard 容量（派生视图，消费 F010 口径） | 按 Network 与 AUTO 池聚合未删 IP | 每 Network | 无；随底层数据变化 | §20/§11.1/T32 CONFIRMED；F010 DR-130 | 全局合计 OPEN（I-7） |
| IP→Resource 定位 | IPAddress→Interface→Resource（1:N，未绑定可空） | Cluster 内 | 无 | §13/§14 CONFIRMED | 未绑定 IP 无 Resource 的展示 OPEN（I-6） |
| Service→Resource 定位 | Service→Resource（N:1） | Resource | 无 | §15 CONFIRMED | 无 |
| Cluster 命中展开 | Cluster→Resource（1:N） | Cluster | 无 | §17/§19 | 是否展开 Resources OPEN（I-5） |

数据完整性对应表（只读视图，无写入约束；引用 `.pi/skills/data-integrity/SKILL.md`）：

| 规则依据及版本 | 作用域 | 记录/不变量 | 验证方向 |
| --- | --- | --- | --- |
| §21 未删过滤 | 搜索与所有计数 | 仅未软删对象参与；ADMIN 可选含已删 | 软删后搜索/计数消失 |
| §20/T32 容量口径 | Network/AUTO 池容量 | 与 F010 §6.9 输出一致，不改写 | 与容量端点逐项对齐 |
| §4.1/§7 归一化 | hostname/Cluster/Service 匹配 | 同一归一化键 | 大小写/空白用例 |
| §4 稳定 ID | 结果跳转 | 结果携带稳定 ID | 跳转目标正确 |
| §23 权限 | 搜索/Dashboard | 全角色可读；无写入口 | 权限矩阵用例 |

## 5. 必须遵守的已确认约束
- §17：首页统一入口；至少 hostname/IP/Cluster/Service；搜索框与下拉允许输入+模糊；能定位 Resource；pg_trgm；GIN 为建议、由数据库设计签核；SN/MAC/Role/GPU Model 本期不强制。
- §33：必须能回答「hostname 属于哪个集群」「某 IP 是哪台机器」「机器运行哪些 Service」「vm001 的宿主机」等目标查询。
- §20：Dashboard 仅展示 Cluster/Resource/BareMetal/VM/Network 数量与 IP 使用情况，不是监控面板；容量公式与口径（§3.2）；排除 gateway/RESERVED/禁用；未绑定 IP 计占用；软删不计；Network 含池外手动、AUTO 仅池内；占用按当前地址；去重；与状态/许可分别展示。
- §11.1/§12：基础可用地址、RESERVED/gateway/禁用边界与池交集口径的权威定义（F008/F009/F010 已落地）。
- §21：默认隐藏已软删；查看已删/恢复限 ADMIN。
- §18/§19：Resource Detail（Overview/Hardware/Interfaces/IP Addresses/Virtual Machines/Services/Activity）与 Cluster Detail（Resources/Networks/IP Addresses/VMs/Services，支持组合过滤 N96P+COMPUTE+IDLE）为搜索结果导航目标与展示区域，正文由 F003/F004 等已交付 Feature 维护；F013 不重复定义其字段。
- §22：只读操作不写 Audit；不展示敏感内容。
- §23：查询、搜索、详情全角色允许；无写操作。
- §25：REST 前缀 `/api/v1/`；核心路径含 `/api/v1/search`；组合过滤不按场景另建接口。
- §26：PostgreSQL / SQLAlchemy 2.x / Alembic；pg_trgm；GIN 建议。
- §28：列表页至少分页、排序、过滤、模糊搜索。
- §4/§4.1：内部关联用稳定 ID；名称归一化统一（D01 §5/§7）。

## 6. 可观察验收标准

| # | 验收标准 | 映射 |
| --- | --- | --- |
| A1 | 首页存在统一搜索入口，可在同一次查询中接受 hostname/IP/Cluster/Service 输入并返回结果 | §17 |
| A2 | 模糊 hostname 搜索：`gpu07` 命中 `gpu0701`、`gpu0702`、`gpu0725`，并返回对应 Resource | §17/§33 |
| A3 | hostname 归一化：大小写、首尾空白不影响命中（`CN001`/` cn001 ` 与 `cn001` 等同，§7） | §7/§4.1/T11 |
| A4 | 输入 IP 命中其所属 Interface→Resource，返回该 Resource（含 cluster 归属） | §17/§13/§33 |
| A5 | 输入未绑定 Interface 的 IP 能命中该 IPAddress；展示不伪造 Resource 归属（无 Resource 时明确为空） | §13/§21 |
| A6 | 输入 Cluster（code 或 name）命中该 Cluster 并可跳转 Cluster Detail | §17/§19 |
| A7 | 输入 Service 名命中其承载 Resource（Service 属 Resource） | §15/§17/§33 |
| A8 | 搜索结果默认不含已软删对象；ADMIN 可显式包含已删（deleted=include/only） | §21/§23 |
| A9 | 空/纯空白查询按 CONTRACT 定义处理（PROPOSED：422 field="q"），不返回全量或不产生 500 | §25/§28（PROPOSED 形态） |
| A10 | 每条结果暴露稳定 ID 与 object_type，跳转目标正确（Resource→§18，Cluster→§19） | §4/§18/§19 |
| A11 | 搜索结果分页/排序（沿用既有列表基线：缺省 page=1/page_size=20，1..100；越界 422） | §28 |
| A12 | 模糊搜索由 pg_trgm 支撑，索引方案经 Database 签核（GIN 建议） | §26/§17 |
| A13 | Dashboard 展示 Cluster / Resource / BareMetal / VM / Network 数量，口径为未软删（含 INACTIVE） | §20/§21/§5/§11 |
| A14 | Dashboard 按 Network 展示可分配总量 / 已占用量 / 剩余可用量 | §20/T32 |
| A15 | Dashboard 按 AUTO 池展示可分配总量 / 剩余可用量（`|池范围 ∩ 可分配集合|` 口径） | §20/T32 |
| A16 | 容量计算排除 gateway / RESERVED 池范围 / 禁用地址，且集合去重（gateway 在 RESERVED 时不重复扣减） | §20/§11.1/T32 |
| A17 | 占用=该 Network 下未删 IP（含未绑定 Interface、含池外手动）；软删 IP 不计；`remaining` 可为负且不截断 | §20/T32/§13 |
| A18 | AUTO 池占用按当前地址所在范围（非历史来源）；Network 口径含池外手动地址 | §20/T32/§12 |
| A19 | 容量与 ACTIVE/INACTIVE、auto_allocate 操作许可分别展示；Network 停用不清零容量或占用 | §20/§5/§11 |
| A20 | IP 使用情况与 F010 `/api/v1/networks/{id}/capacity` 输出逐项一致（同口径、无改写） | §20/F010 §6.9/T32 |
| A21 | 搜索与 Dashboard 均只读：无新增/修改/删除/恢复入口，不产生 Audit 记录，无副作用 | §22/§20 |
| A22 | 权限：VIEWER/EDITOR/ADMIN 均可搜索与查看 Dashboard；未认证 401；查看已删/恢复仍限 ADMIN | §23/T25 |
| A23 | 已软删 Network 不参与计数与容量；已软删 IP/对象不参与搜索与计数 | §21 |
| A24 | SN / MAC / Role / GPU Model 搜索不作为本期验收项（本期不强制） | §17 |

## 7. 不变量（I-1…）
- **I-1 软删隔离**：搜索与 Dashboard 计数/容量默认仅基于未软删对象；软删不进入默认结果与计数（§21）。ADMIN 可用 `deleted=include/only` 显式查看已删（搜索侧），但 Dashboard 计数默认不含已删。
- **I-2 分页与上限**：搜索结果沿用既有列表分页基线（缺省 page=1、page_size=20，接受 1..100，越界/非法 422）；存在结果集上限，防止无界返回（§28；具体上限交 CONTRACT）。
- **I-3 空结果**：无命中时返回 HTTP 200 与空列表 `{items: [], total: 0}`，不返回 404/500。
- **I-4 只读无副作用**：搜索与 Dashboard 不写业务数据、不写 Audit、不改任何对象状态；重复调用幂等（§22/§20）。
- **I-5 归一化一致**：hostname / Cluster code / Service name 匹配使用与唯一性一致的归一化（§4.1/§7，D01 §5）；大小写不敏感口径与对象一致；中文与内部普通空格保留。
- **I-6 IP 定位边界**：IP 命中经 Interface 定位 Resource；未绑定 IP 命中返回 IPAddress 且 Resource 归属为空，不臆造归属（§13）。
- **I-7 容量口径不可改写**：Dashboard 只消费 §20/F010 容量的权威口径；不自行重算、不截断负值、不以 CIDR 大小替代池容量（§20/T32）。
- **I-8 计数全局且含停用**：Dashboard 计数为全局未软删口径，含 INACTIVE Cluster/Network；状态不改变计数（§5/§11/§20）。
- **I-9 稳定 ID**：所有结果与跳转使用稳定 UUID，不依赖 hostname/name/code 字符串拼接（§4）。
- **I-10 权限边界**：搜索与 Dashboard 无写能力；查看已删/恢复限 ADMIN（§23）。

## 8. 明确排除项
- **不是监控面板**：不展示实时 CPU/内存/流量/可达性/健康状态，不承担 Grafana 职责（§3/§20）。
- **本期不强制**：SN、MAC、Role、GPU Model 搜索为后续扩展（§17）。
- **不重复定义各域列表**：各实体列表的组合过滤 / 排序 / 分页已属各域 Feature（F003/F004/F008/F009/F010/F011/F012），本 Feature 不做重复定义；F013 只提供全局搜索与 Dashboard 汇总（plan F013）。
- **不重复定义详情页内容**：§18 Resource Detail、§19 Cluster Detail 的字段与区域由对应 Feature 维护；F013 仅作为搜索结果导航目标。
- **不做写操作**：不提供新增/修改/删除/恢复/导入入口，不改任何对象状态。
- **不做 CSV/Excel 导入**（F014）；**不做完整 Audit 查询页与已删除对象统一管理**（F015）；**不做一期集成验收**（F016）。
- **不引入新资源字段/实体**：不新增 CDN/SN/型号等搜索字段，不改各域 Schema 语义。
- **不引入禁引入技术**（§29）：不用 ElasticSearch；模糊搜索用 pg_trgm；不引入 Redis/Celery 等。
- 不做 IPv6 搜索、全文检索、自然语言查询、跨 Cluster IP 合并。

## 9. 依赖与未决问题
依赖（CONFIRMED）：F003（Cluster、列表基线）、F004（Resource）、F005（BareMetal）、F006（VM）、F008（Network）、F009（IPPool）、F010（IPAddress + 容量口径 + `/api/v1/networks/{id}/capacity`）、F011（Service）、F012（ServiceEndpoint）均已 DONE；F001（pg_trgm 基线、真实 PG 测试基线）；D01 v11 归一化/时间/省略语义；D02 索引/查询专业设计在本 Feature CONTRACT 签核 pg_trgm/GIN 引入点。

BLOCKING：无。

CONFIRMED：§17 全部；§20 全部与 T32；§33；§21 默认隐藏；§23 读权限；§25 前缀与 `/api/v1/search`；§26 pg_trgm；§28 列表基线；§4/§4.1/§7 归一化；Q02-A/Q04-A/Q04-B/Q10-B。

PROPOSED/OPEN（非阻塞，均给可实施默认，交 Architect/CONTRACT 或 Product 确认，不自行设为永久规则）：
- **I-11（OPEN，产品/设计，非阻塞）— 结果去重与排序**：§17 未定义。**PROPOSED**：按 Resource 身份去重（同 Resource 多路径命中合并）；排序按相似度降序、同分按 object_type 分组与稳定 ID。Owner：Product/Architect → CONTRACT。
- **I-12（OPEN，产品/设计，非阻塞）— Cluster 命中的展开范围**：§17/§19 未明确返回该 Cluster 还是其下 Resources。**PROPOSED**：默认返回 Cluster 结果并可跳转 Cluster Detail；是否附带展开 Resources 由 CONTRACT 裁定（避免结果集爆炸，默认不展开）。Owner：Product/Architect。
- **I-13（OPEN，产品/设计，非阻塞）— 空查询处理**：§17 未定义。**PROPOSED**：空白 `q` → 422 VALIDATION_ERROR{field:"q"}，不返回全量。Owner：Product/Architect。
- **I-14（OPEN，设计，非阻塞）— Dashboard API 路径**：§25 列出 `/api/v1/search`，未列 Dashboard。**PROPOSED**：新增只读 `/api/v1/dashboard`（或 `/api/v1/dashboard/summary`）挂同一 `api_v1_router`，全角色可读。Owner：Architect → CONTRACT。
- **I-15（OPEN，数据库，非阻塞）— pg_trgm/GIN 引入点**：plan F013 明确「pg_trgm 索引引入点 F004 或 F013 由首个需要模糊查询的 Feature Contract + D02 裁定」。**PROPOSED**：本 Feature 为全局跨对象模糊搜索，在 F013 CONTRACT 定 DM 语句与索引集合，由 Database 在 DATABASE Gate 签核（`gin_trgm_ops`），索引集合覆盖 hostname、Cluster code/name、Service name。Owner：Architect/Database。
- **I-16（OPEN，产品/设计，非阻塞）— Dashboard 全局合计**：§20 未定义跨 Network 汇总合计。**PROPOSED**：只展示 per-Network（及各自 AUTO 池）容量，不默认新增全局合计（不同 Cluster 可有相同地址，相加易误导）。Owner：Product/Architect。
- **I-17（OPEN，契约收敛）— 搜索与各域列表 `q` 口径**：既有各域列表已用 `ILIKE` 实现 `q`（如 F003/F004 TD-2，未用 pg_trgm）。plan F013 要求「列表契约收敛」。**PROPOSED**：F013 CONTRACT 明确 `/api/v1/search` 使用 pg_trgm，并记录与各域列表 `q` 的关系（是否统一升级为 pg_trgm），不追溯修改已 DONE 域的行为语义。Owner：Architect/协调器。
- **I-18（NOTE）— 计划字段**：`project-plan.yaml` F013 未填 `layers`/`api_required`，ARCHITECTURE 阶段补齐（预期 api_required=true，layers 含 backend/frontend，database 取决于 pg_trgm/GIN 落地裁定）。

## 10. 交 Architect 的输入
1. **API**：`/api/v1/search`（§25 已确认路径）+ PROPOSED `/api/v1/dashboard`；契约含查询参数（q、类型下拉、page/page_size）、结果结构（object_type、稳定 ID、命中字段、可跳转信息）、空结果与分页边界；沿用 D01 §4 省略语义与既有 422/401/403 错误口径。
2. **搜索实现**：pg_trgm 匹配与 GIN 索引方案（I-15）交 Database 签核；归一化与唯一性一致（§4.1/§7/D01 §5）；默认软删过滤 + ADMIN `deleted` 参数（§21）。
3. **命中定义落地**（§2.2）：hostname→Resource；IP→Interface→Resource（未绑定则无 Resource）；Cluster→Cluster；Service→Resource；去重与排序（I-11）、Cluster 展开范围（I-12）。
4. **Dashboard**：计数查询（未软删、含 INACTIVE，I-8）；容量消费 F010 `/api/v1/networks/{id}/capacity` 口径，per-Network + AUTO 池展示，`remaining` 负值原样（I-7/§20/T32）；只读、不写 Audit（I-4）。
5. **权限**：搜索与 Dashboard 读=全角色（§23）；无写端点。
6. **前端**：首页搜索框/下拉 + 结果列表（类型标签、模糊高亮、跳转 §18/§19）+ Dashboard 卡片区（计数 + per-Network 容量 + AUTO 池容量 + 状态/许可标识）；§28 列表基线。
7. **待裁定**：I-11 去重/排序、I-12 Cluster 展开、I-13 空查询、I-14 Dashboard 路径、I-15 GIN 引入点、I-16 全局合计、I-17 列表契约收敛、I-18 计划字段。
8. **边界**：不改各域 Schema 语义；不重复定义各域列表/详情；不做监控/导入/完整 Audit/一期验收。

## 11. 结论与下一步
无 Blocking Questions，无待用户裁定事项。**READY FOR ARCHITECT**。下一步 ARCHITECTURE：定义 `/api/v1/search` 与 Dashboard 端点、结果结构与去重/排序（裁定 I-11/I-12/I-13/I-14）、layers 与 api_required；CONTRACT 收敛列表契约与 pg_trgm/GIN 引入点（I-15/I-17），由 Database 签核索引；Frontend 承接首页搜索与 Dashboard 展示。