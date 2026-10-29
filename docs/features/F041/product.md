# F041 对象选择控件候选完整性（R04）— PRODUCT 阶段报告

- **状态**：READY FOR ARCHITECT
- **版本**：v1（2026-10-29）；FEATURE / P1 / M30；分支 `feature/F041-candidate-completeness`，交付线 `v3.4`，start_commit `d5c0a4c9aa5bd1036dd9acf087d210a22f43571d`；plan revision 25；requirements revision 16
- **角色产物**：product-manager 只读产出，协调器持久化
- **Basis（均 CONFIRMED / 已批准）**：requirements **revision 16** §28.1（新增条款）+ §31 **T127–T129** + §32 追加句 + §23.2 / §21 / §22 / §9 / §13.4（T54–T58 明确不并入）/ §17.1；用户 2026-10-29 裁定 **AQ-1 = A** 并「批准并执行」（§35.1 revision 16 行留痕）；契约基线 `docs/api/F003.md` §4/§6.1（clusters `q`=code/name ILIKE、`page_size` 1–100）、`docs/api/F004.md` §4（resources `q`=hostname ILIKE、`cluster_id`/`type` 过滤、`page_size` 1–100）、`docs/api/F013.md` §1.4/§6（列表 `q` 冻结 ILIKE）；`docs/features/F006/implementation.md` §4（100 条截断限制的既有记录）；plan revision 25 F041（`layers={database:false,backend:false,frontend:true}`、`api_required=false`、`depends_on: [F003,F004,F006]`、`blocking_decisions: []`）及三条硬约束
- **前端现状（只读核对）**：`VirtualMachineFields.tsx:99` 一次性 `listResources({cluster_id, type:"BARE_METAL", page_size:100, sort:"hostname"})` 无 `q`/无分页；`ResourceCreatePage.tsx:63` 一次性 `listClusters({page:1,page_size:100,sort:"code"})`；`ui/controls.tsx:114` 的共享 `Select` 为 `showSearch` + `optionFilterProp="label"`（仅过滤已加载选项）；`api/resources.ts` / `api/clusters.ts` 客户端类型**已含** `q`/`page`/`page_size`；`frontend/src` 无 debounce 工具

## 1. 性质：实现已确认条款，不扩大不收窄

需求 §28.1 已 CONFIRMED（revision 16），本 Feature 只实现该条款。领域对象/状态/唯一性/生命周期/权限**零变更**；契约**零变更**（`q`/`page`/`page_size`/`cluster_id`/`type`/`sort`/`order` 均为 F003/F004 既有参数，前端客户端类型已具备）；Schema 零变更。

**不扩大**：不推广到 Interface / Network / IP Pool / IP Address / Service / Service Endpoint 等其余控件。
**不收窄**：不得以「编辑时 Cluster 只读」「未选集群为空闲态」等实现细节削弱 T127/T128；两个覆盖控件在**所有可达路径**（新增与编辑）都必须满足候选完整性。

## 2. 当前问题与范围

- 问题事实：两处下拉只取第 1 页（`page_size=100`）并在已加载选项内前端过滤，按既有排序位于第 101 位及之后的 Host/Cluster 无法检索、无法选定；已显示截断提示，故不属静默截断或新发现的需求违约。
- **范围（严格两处）**：① VM 表单 Host 选择（`GET /api/v1/resources`，同 Cluster `BARE_METAL`，`deleted` 默认 exclude；含新增与编辑换 Host）；② Resource 创建页 Cluster 选择（`GET /api/v1/clusters`；编辑时 Cluster 只读，不涉及候选）。
- 不纳入：其余对象选择控件留作后续评估（不表示永久排除）。
- 依赖：服务端能力由 F003/F004/F006/F027 既有实现提供，F041 不扩写服务端。

## 3. 可验收标准（映射 T127–T129）

### T127 候选完整性由服务端检索与分页提供

| ID | 断言 |
| --- | --- |
| A1 | 可重复夹具：≥101 个同 Cluster 未删除 `BARE_METAL` 与 ≥101 个未删除 Cluster 后，两处候选均能通过输入检索到排序名次 ≥101 的目标对象、可选中并**提交被服务端接受**（落库的 `host_resource_id` / `cluster` 为所选对象）——非手工抽样 |
| A2 | 单页上限：候选请求携带 `page`/`page_size`，任一请求 `page_size ≤ 100`，任一成功响应 `items.length ≤ 100` |
| A3 | 不全量加载：单次交互候选请求次数与候选总量无关（154 与 1540 同量级），不得提高 `page_size` 越过 100、不得循环抓取全部分页 |
| A4 | 无前端全量缓存：候选项只来自最近一次服务端响应；服务端只返回 N 条时不出现第 N+1 条历史条目；输入变化后旧结果不残留 |

### T128 沿用既有范围、可见性与状态呈现

| ID | 断言 |
| --- | --- |
| A5 | 软删排除：已软删 `BARE_METAL` / Cluster 不出现在候选且检索不到；`deleted` 取默认 exclude，不发 `include`/`only` |
| A6 | §23.2 范围：非 ADMIN 候选仅含授权集群对象；未授权集群对象不出现，且 `total`、超限提示与空结果统计**只计可见对象**（全库 120 个 Cluster、授权 3 个时提示总数为 3） |
| A7 | 四态显式区分：加载中 / 加载失败 / 空闲（VM 新增未选集群）/ 空结果，四态文案与可访问语义互不相同 |
| A8 | 失败可重试且不伪装为空：失败显示错误并提供重试，重试成功恢复候选；失败态不得渲染为「无匹配/暂无数据」 |
| A9 | 超限显式提示：`total` > 已加载条数时提示总数与分页边界，不静默截断 |
| A10 | 提交拒绝语义不变：绕过候选直接提交未授权 Cluster / 跨 Cluster Host / 已软删 Host / `VIRTUAL_MACHINE` 类型 Host / 不存在引用，仍返回既有 401/403/404/409/422，前端按既有方式呈现 |

### T129 零契约与零回归

| ID | 断言 |
| --- | --- |
| A11 | 零契约 diff：F003 §4/§6.1、F004 §4 无 diff；无新端点/查询参数/权限项/错误码 |
| A12 | `q` 仍 ILIKE：各域列表 `q` 仍大小写不敏感子串（F013 §1.4/§6），未改 pg_trgm；候选命中集合与列表页同一 `q` 一致，顺序仍由既有 `sort` 决定 |
| A13 | 共享 `Select` 语义不变：`ui/controls.tsx` 既有调用点行为逐字等价；新行为仅由新组件或 opt-in props 承载 |
| A14 | 关系/默认值/流程不回归：T01/T02、T08/T09、T19（换 Host 审计）、T37；VM 与 Resource 全流程、列表页、§13.4 IP 候选（T54–T58）无回归 |
| A15 | 候选读取无写副作用：不产生 Audit/Activity（§22） |
| A16 | 编辑态不回填丢失：编辑 VM 时当前 Host 不在当前页仍正确显示，可直接提交或改选；改选后按 T19 记审计 |

不在验收范围：其余控件、列表/全局搜索改善、后端与 Schema、性能指标、浏览器 E2E 新依赖、F045 整体验收。

## 4. 明确不做（禁止清单）

| # | 禁止 | 依据 |
| --- | --- | --- |
| N1 | 不新增端点/查询参数/权限项/错误码；不建专用选项接口 | §28.1；T129；plan 硬约束① |
| N2 | 不以「一次加载全部」实现（提高 `page_size` >100、循环抓全部分页、前端全量缓存） | §28.1；T127 |
| N3 | 不改列表 `q` 匹配实现（不引入 pg_trgm） | §28.1；F013 §1.4/§6；T129 |
| N4 | 不改 `page_size` 上限 100 | §28.1；T127 |
| N5 | 不改共享 `Select` 全局语义（新组件或 opt-in props 承载） | §28.1；plan 硬约束②；A13 |
| N6 | 不改 §13.4 IP 候选语义、不改 §17/§17.1 全局搜索 | §28.1；A14 |
| N7 | 候选可选中≠服务端接受；不改唯一性/关系/状态/软删/审计/版本冲突 | §28.1；A10 |
| N8 | 不扩大到其余对象选择控件 | §28.1；AQ-1=A |
| N9 | 不改 `docs/product/**`、`docs/api/**`、`docs/database/**`、`backend/**` | plan `not_required`；`api_required=false` |
| N10 | 不新增候选专属过滤规则（如给 Host 候选加 `status`、给 Cluster 候选加 `ACTIVE`） | §28.1「不定义新的候选过滤规则」 |
| N11 | 不引入新框架/依赖（不引入下拉搜索库或 debounce 依赖） | AGENTS §2.6；§29 |

## 5. 关系与既有规则不变

§9/T08/T09（VM 必须关联未删除 `BARE_METAL` 且同 Cluster，判定权在服务端）／T19（换 Host 审计）／T01/T02（同 Cluster hostname 唯一）／T37（创建默认可选字段值）／§23/§23.2（角色矩阵与范围，候选读取是 READ 且受范围约束，不新增权限项）／§21/§22（软删默认 exclude、读无 Audit）／契约冻结（F003 §4/§6.1、F004 §4、F013 §1.4/§6 零 diff）。

## 6. Blocking Questions

**无。** §28.1 与 T127–T129 已确认并落稿（revision 16，§35.1 留痕），AQ-1=A 已裁定本期恰为两处控件；覆盖范围、判定标准、可见性与权限口径、四态、超限提示与禁止清单均已在 §28.1 明确。残留歧义均属技术设计（见 §7）。

## 7. Non-blocking 观察（交 Architect / Tester）

| ID | 观察 | 归属 |
| --- | --- | --- |
| ON-1 | 组件形态：新增可复用 `SearchableSelect`（服务端检索+分页）vs 给 `Select` 加 opt-in props；倾向新组件（保证 A13） | Architect |
| ON-2 | 是否新增/复用 `useDebounce`：现无 debounce 工具；须在 N11 内决定（内联定时器/hook/输入事件节流） | Architect / Frontend |
| ON-3 | ≥101 对象夹具：真实 PG 批量插入 vs 复用 API helper；须保证可重复与稳定排序，且不得用 mock 替代 A1 的「提交被服务端接受」 | Tester / Architect |
| ON-4 | 空闲态与切换集群：未选集群 → idle；切换集群须清空旧候选并重新加载 | Architect / Frontend |
| ON-5 | 编辑态 `currentHost` 回填：pin 当前选中项或按 id 精确补一条，保证 A16 | Architect / Frontend |
| ON-6 | 候选分页交互：输入即检索（推荐）vs 下拉内「加载更多」；须同时满足 A3/A4/A9 | Architect |
| ON-7 | 请求竞态与取消：沿用既有 `cancelled` 标志丢弃陈旧响应（关联 A4） | Frontend |
| ON-8 | 可重复测试入口：AQ-4=B 限定组件/逻辑级 + 请求断言（mock fetch 断言 URL 参数与响应处理），不引入 Playwright | Tester |
| ON-9 | smoke 基线：新增用例会改变通过项数量，应更新基线而非放宽断言 | Tester |
| ON-10 | 误用风险：新组件若被顺带用于 §13.4 IP 候选或列表筛选将构成 N6/N5 违约；Review 需检查调用点集合 | Review / Architect |
| ON-11 | 超限提示文案与 `total` 语义：须同时表达总数与分页边界，且只统计可见对象 | Architect |

## 8. 后续文档更新

需求 / 领域模型 / `docs/api/**` / `docs/database/**` / `backend/**` 均**零 diff**；`docs/features/F041/architecture.md` 由 Architect 新建（组件形态、数据流、状态机、测试入口、ON-1–ON-11 落定）；Test Design/Report 记录 T127–T129 真实证据（未执行不得写 PASS）。
