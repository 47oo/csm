# F019 接口侧选择并绑定 IP — ARCHITECTURE 阶段报告

- **Task**：F019（FEATURE，P1，M10 接口侧 IP 绑定）— Architect，Feature 设计模式
- **阶段**：ARCHITECTURE；**结论**：`READY FOR DESIGN`（2026-10-15）
- **Basis**：
  - `docs/product/requirements-v3.md` revision 6（§13.4、§13.3、§14、§16、§21、§22、§23、§28；§31 T54–T58）
  - `docs/features/F019/product.md`（PRODUCT `READY FOR ARCHITECT`，AC1–AC7，无 Blocking Questions）
  - `docs/project/project-plan.yaml` revision 7（F019：`layers{database:false,backend:false,frontend:true}`、`api_required:false`）
  - `docs/api/F010.md` v1（§1.2/§1.3/§4/§5/§6.1/§6.5/§7/§8）、`docs/api/F007.md` v1（§1.3/§4/§5/§6.1/§6.4）
  - 现有实现：`frontend/src/components/InterfacesPanel.tsx`、`frontend/src/api/ipAddresses.ts`、`frontend/src/components/ui/`；`docs/architecture/d01-conventions.md` v11
  - 规划轻量评估结论（复用）：复用既有 GET/PATCH，无 Schema/索引/迁移、无契约修订；接口侧已绑定 IP 懒加载；逐条 PATCH 允许部分成功、乐观锁兜并发

---

## 1. 方案摘要与边界

### 1.1 方案摘要

F019 是**纯前端编排**：在已交付的 Interface（F007）与 IPAddress（F010）之上，于 Resource Detail 的 Interfaces 区域内提供「接口侧选择并绑定 IP」。不新增服务端端点、参数、Schema 或契约；候选与绑定分别复用既有 `GET /api/v1/ip-addresses?cluster_id=…&bound=false&deleted=exclude&q=…&page=…` 与 `PATCH /api/v1/ip-addresses/{id}`（`interface` + `version`）。

1. **候选取数**：`resource.cluster.id` 限定同 Cluster、`bound=false` 限定未绑定、`deleted=exclude` 限定未删；`q` 搜索 `address`、服务端分页/排序。
2. **分页/搜索/跨页多选**：选择身份 = IPAddress `id`；跨页保留 `{id, address, version}`；服务端 `total` 驱动边界提示，不静默截断。
3. **逐条绑定与部分成功**：对每个选中 IP 单独 `PATCH interface=<iface.id>, version`；逐条独立呈现成功/失败及原因，部分成功不显示为整体成功，不静默重试/覆盖。
4. **接口侧已绑定展示（懒加载/有界）**：`GET /api/v1/ip-addresses?interface_id=<id>&deleted=exclude` 按需拉取并缓存，避免 N+1。
5. **权限/软删/并发**：候选 READ（全角色），绑定 WRITE（VIEWER 隐藏入口且服务端 403）；软删恒 `exclude`；并发由 F010 乐观锁保证后到者 409。
6. **零后端 / 零 Schema**：`backend=false`、`database=false`、`api_required=false`。

### 1.2 明确不做

- 不新增端点、查询参数、Interface 嵌套 IP 响应、批量事务端点。
- 不提供接口侧手动输入新 IP、自动分配、解绑 / 转移。
- 不显示跨 Cluster / 已绑定其它 Interface / 已删除的 IP。
- 不新增实体、关系、状态、权限、错误码；不改 F007/F010 契约。
- 无表/列/约束/索引/迁移。
- 不把 Interface 创建与 IP 绑定合并为同一操作；不在创建表单内预选 IP。

### 1.3 layers 与 api_required

```yaml
layers:
  database: false
  backend: false
  frontend: true
api_required: false
```

与已批准计划 revision 7 一致，无需调整。

---

## 2. Design Requirements（DR-332–DR-345）

| ID | 决策 | 状态 |
| --- | --- | --- |
| DR-332 | **候选取数**：`GET /api/v1/ip-addresses`，固定 `cluster_id=<resource.cluster.id>`、`bound=false`、`deleted=exclude`；可选 `q`/`page`/`page_size≤100`/`sort=address`/`order=asc`。不新增端点/参数。 | CONFIRMED（§13.4/T54） |
| DR-333 | **分页/搜索/跨页多选**：选择身份 = IPAddress `id`，会话内跨页保留 `{id,address,version}`；切页/改搜索不清空；`total>items` 显式提示，不静默截断。 | CONFIRMED（T54/T56） |
| DR-334 | **逐条绑定与部分成功**：每项单独 `PATCH {interface,version}`；串行提交（§7），单项失败不中止其余；逐项结果列表；不静默重试/覆盖。 | CONFIRMED（T55） |
| DR-335 | **接口侧已绑定展示**：`GET /api/v1/ip-addresses?interface_id=<id>&deleted=exclude&sort=address&order=asc`，按需触发、按接口缓存、绑定后失效；禁止逐行 N+1。 | CONFIRMED（T54） |
| DR-336 | **错误映射**：`409 VERSION_CONFLICT`、`422 field=interface`、`404`、`403`、`401`；复用 `describeIpAddressActionError`。 | CONFIRMED（F010 §1.2） |
| DR-337 | **权限**：候选/已绑定 = READ；绑定 = WRITE；VIEWER 隐藏入口且服务端 403；401 先于 403。 | CONFIRMED（§23/T57） |
| DR-338 | **软删口径**：候选与已绑定展示固定 `deleted=exclude`；不依赖 VIEW_DELETED；已删 PATCH→404；恢复后重现。 | CONFIRMED（§21/T54） |
| DR-339 | **只读/无审计边界**：候选/搜索/已绑定展示只读无 Audit；唯一写入为逐条 PATCH，各产生 `ip_address` UPDATE Audit；绑定不改占用/address/Network，不触发 Endpoint 引用拒绝。 | CONFIRMED（§22/T55/T57） |
| DR-340 | **无新端点/参数/Contract**：仅复用 GET/PATCH；`api_required=false`→Contract `NOT_REQUIRED`；最小使用说明落本文件 §5 与 implementation.md。 | CONFIRMED（plan F019） |
| DR-341 | **绑定时点与失败呈现**：绑定在 Interface 创建成功之后独立进行；创建失败无绑定；创建成功而绑定失败时保留 Interface 并逐条提示。 | CONFIRMED（§13.4/AC7） |
| DR-342 | **并发与乐观锁**：以快照 `version` 提交；并发后到者 409，无静默重试。 | CONFIRMED（T58/F010 §7） |
| DR-343 | **Database NOT_REQUIRED**：无 Schema/索引/迁移；复用既有索引/约束/触发器。 | CONFIRMED（plan F019） |
| DR-344 | **UI 复用与组件边界**：复用 `ui/` 适配层与 Ant Design；复用 `listIpAddresses`/`updateIpAddress`；新增纯逻辑模块便于 smoke。 | CONFIRMED（frontend-ui） |
| DR-345 | **绑定后刷新与失效**：绑定成功后重取当前候选页并失效目标接口已绑定缓存。 | PROPOSED |

---

## 3. Domain / Data Impact

| 影响面 | 关系/来源 | 作用域 | 生命周期 | 依据及状态 | 裁定 |
| --- | --- | --- | --- | --- | --- |
| 绑定关系（既有） | Interface 1:N IPAddress（`interface_id` 可空） | 同 Cluster | PATCH 置 `interface_id`；解绑/释放仍 IP 侧 | §13.3/§13.4/§14 | DR-332/334/342 |
| 候选视图（派生） | 同 Cluster 且 `interface_id IS NULL` 且未删 | 接口视图 | 不落库 | §13.4/T54 | DR-332/333 |
| 已绑定视图（派生） | `interface_id = <id>` 且未删 | 每 Interface 按需 | 不落库 | §13.4/T54 | DR-335 |
| 软删可见性 | `ip_addresses.deleted_at` | 全流程 `exclude` | 软删隐藏；恢复重现 | §21/T54 | DR-338 |
| 审计 | `audit_logs`（`ip_address` UPDATE） | 每次成功 PATCH | 持续保留 | §22/T55/F010 §8 | DR-339 |

**数据完整性对应表**（无新约束，引用既有保证）

| 规则依据 | 写入入口 | 数据库保证 | 业务层保证 | 验证 |
| --- | --- | --- | --- | --- |
| §14 IP 归属（F010 §2.2/§7） | PATCH interface | FK + `trg_ip_addresses_interface_cluster` | F010 §6.5 → 422 field=interface | F019-T57/T58（真 PG） |
| §14/§13 同 Cluster 唯一 | 仅改 `interface_id` | `uq_ip_addresses_cluster_id_address` | 绑定不改 address/cluster_id | 回归 |
| §21 软删（F010 §5） | 候选/已绑定查询 | 默认 `deleted_at IS NULL` | 固定 exclude；已删 404 | F019-T54/T57 |
| §22 Audit（F010 §8） | 成功 PATCH | 业务同事务写 audit_logs | 每次 1 行 UPDATE | F019-T55 |
| 版本冲突（F010 §7） | PATCH version | 条件 UPDATE，rowcount=0→409/404 | 无静默重试 | F019-T58（并发） |

---

## 4. Frontend / Backend Work

### Backend — NOT_REQUIRED
无服务端改动；复用 `GET /api/v1/ip-addresses`（F010 §6.1）与 `PATCH /api/v1/ip-addresses/{id}`（F010 §6.5）；不新增路由/Schema/序列化/服务层；不改 F007/F010 契约。

### Frontend — REQUIRED
1. **InterfacesPanel.tsx（改）**：未删接口行新增「绑定 IP」操作（仅 `WRITE` 渲染）；每行「已绑定 IP」懒加载展示（`listIpAddresses({interface_id, deleted:"exclude", sort:"address", order:"asc", page_size:100})`），按接口缓存、绑定后失效；`total>items` 显式提示。
2. **InterfaceIpBindingPanel.tsx（新增，Modal/Drawer）**：候选 `listIpAddresses({cluster_id, bound:false, deleted:"exclude", q, page, page_size, sort:"address", order:"asc"})`；跨页多选以 `id` 为键维护 `Map<id,{address,version}>`；逐条串行 `updateIpAddress(id,{interface,version})`；逐项结果 + `describeIpAddressActionError`；空/错/加载态显式区分，无手动输入/自动分配/解绑/转移入口。
3. **interfaceIpSelection.ts（新增纯逻辑）**：选择集合增删、候选查询参数构造、部分成功汇总、`total` 边界；供 `scripts/smoke-client.mjs` 机制级冒烟。
4. **API client**：复用 `listIpAddresses`/`updateIpAddress`/`describeIpAddressActionError`，不新增 client 函数。
5. **UI 复用**：`ui/`(controls/feedback/surfaces) + Ant Design；Tailwind 负责布局。

---

## 5. Contract 引用与状态

- **状态：`NOT_REQUIRED`**（`api_required=false`）。无 `docs/api/F019.md`；不修订 F007/F010。

| 复用条款 | 用途 | 最小使用说明 |
| --- | --- | --- |
| F010 §4/§6.1 | 候选/已绑定展示 | `cluster_id`+`bound=false`+`deleted=exclude`；或 `interface_id`+`deleted=exclude`；`sort=address&order=asc`，`page_size≤100` |
| F010 §6.5 | 逐条绑定 | `PATCH {interface, version}`；`exclude_unset`；关系编辑不受 INACTIVE 限制 |
| F010 §1.2 | 错误语义 | 409 VERSION_CONFLICT / 422 field=interface / 404 / 403 / 401 |
| F010 §1.3 | 权限 | 列表=READ；绑定=WRITE；服务端权威 |
| F010 §5/§8/§7 | 软删/Audit/并发 | exclude；每次成功 1 行 UPDATE Audit；乐观锁后到者 409 |
| F007 §1.3/§6.1/§6.4 | 接口上下文 | 仅用接口 id/resource 归属；不改接口契约 |

---

## 6. Test Work

### 6.1 验收映射（AC1–AC7 / T54–T58）

| 验收 | 判据 | 层次 |
| --- | --- | --- |
| AC1/T54 | 候选仅同 Cluster、未绑定、未删 | 集成（真 PG）+ 前端机制 |
| AC2/T55 | 多选绑定后关系一致，各产生 UPDATE Audit | 集成 |
| AC3/T55 | 部分失败逐条呈现，不整体成功、不静默重试 | 前端机制 + 集成 |
| AC4/T56 | 空态/错误态显式、`total>items` 提示 | 前端机制 + 集成 |
| AC5/T57 | VIEWER 403；绑定不改占用/address/Network，不触发 Endpoint 引用拒绝 | 集成 |
| AC6/T58 | 仅绑定；并发后到者 409，无重复绑定 | 集成（并发） |
| AC7/§13.4 | 创建失败无绑定；创建成功绑定失败保留 Interface 并提示 | 集成 |

### 6.2 边界用例
候选空/1 项/跨页多选；`q` 后保留已选；部分成功（409+422+404+成功）；并发同 version（恰一成功一 409，无重复绑定）；VIEWER 403 / 401 先于 403；已删 IP 404、软删接口 422；既有 IP 侧行为无回归；候选/已绑定列表不产生 Audit。

### 6.3 必须真实 PostgreSQL / 真实浏览器
- **真 PG**：候选过滤、绑定持久化、乐观锁并发、Audit 行数与内容、Cluster 一致性 422、权限 403。
- **真实浏览器/DOM**：Modal/Drawer 交互、跨页多选、部分成功渲染、懒加载与缓存失效、空/错/边界提示。缺环境时**明确标记未验证**，不以构建通过替代交互验证。

---

## 7. 技术决策、风险与 Implementation Layers

### 7.1 技术决策
1. 候选 = `GET /api/v1/ip-addresses?cluster_id&bound=false&deleted=exclude`（CONFIRMED）
2. 绑定 = 逐条 `PATCH {interface,version}`，允许部分成功（CONFIRMED）
3. 候选 READ；绑定 WRITE；服务端权威（CONFIRMED）
4. 软删恒 `exclude`（CONFIRMED）
5. 无新端点/参数/契约；无 Schema/迁移（CONFIRMED）
6. 接口侧解绑/转移、手输新 IP、自动分配不在本流程（CONFIRMED）
7. 并发由 F010 乐观锁保证，后到者 409，无静默重试（CONFIRMED）
8. 已绑定 IP 懒加载、按接口缓存、绑定后失效（PROPOSED）
9. 提交顺序：按 `address` 升序串行（PROPOSED）
10. 选择身份 = IPAddress `id`，跨页保留 `{id,address,version}`（PROPOSED）
11. 入口形态：行「绑定 IP」按钮（PROPOSED）
12. 新增纯逻辑模块承载选择/汇总（PROPOSED）

### 7.2 风险
| 风险 | 级别 | 缓解 |
| --- | --- | --- |
| 逐行请求已绑定 IP 致 N+1 | 中 | DR-335 懒加载 + 缓存 |
| 选择会话过长致 version 过期 | 中 | 逐项 409 明确提示刷新重选 |
| 部分成功 UX 复杂误读 | 中 | 逐条结果 + 成功/失败计数 |
| 候选量大跨页多选状态丢失 | 低 | 以 id 为键跨页保留 |
| 依赖既有 F010 行为 | 低 | 真 PG 集成验证 |
| 单页上限 100 边界提示 | 低 | 显式 total + 分页提示 |

### 7.3 Implementation Layers
```yaml
layers: {database: false, backend: false, frontend: true}
```
实现顺序：纯逻辑模块 → 候选选择器组件 → InterfacesPanel 集成 → 机制级冒烟 + 真 PG 集成验证。无 Migration、无后端、无 Contract 文件。

### 7.4 验证策略
- 前端：`npm run typecheck && npm run build && npm run smoke:client`。
- 真实后端集成（test 环境/真 PG）：候选过滤、逐条绑定与 Audit、部分成功、并发 409、VIEWER 403、软删 404、AC7。
- 真实浏览器：交互与状态渲染；无环境时如实标记未验证。

---

## 8. 待核对项（均非阻塞）
入口形态（行按钮）、提交顺序（地址升序串行）、已绑定 IP 展示位置（行展开按需加载）、组件命名（`InterfaceIpBindingPanel.tsx` + `interfaceIpSelection.ts`）。

**结论**：无 Blocking Questions；`READY FOR DESIGN`。下一步 TEST_DESIGN；无 Database Gate；Contract `NOT_REQUIRED`。

GIT: NONE
---

## 9. 最终设计签核（CONTRACT Gate）

- **签核者**：Architect
- **结果**：`READY FOR IMPLEMENTATION`
- **签核版本**：F019 Design v1（本文件）；Contract `NOT_REQUIRED`
- **核对的 Database**：`NOT_REQUIRED`（无 Schema/Migration；数据行为由 F010 v1 既有约束/触发器承担）
- **核对的 Test Design**：`docs/features/F019/test-report.md` TD-1
- **上游依据**：requirements-v3.md revision 6 §13.4（T54–T58）；F019 product v1（AC1–AC7）；project-plan.yaml revision 7（用户 2026-10-15 批准）
- **覆盖 Feature**：F019
- **一致性**：AC1–AC7 ↔ T54–T58 ↔ DR-332–DR-345 ↔ F019-T01–T13 无缺口/矛盾；Contract=NOT_REQUIRED、Database=NOT_REQUIRED、Backend=NOT_REQUIRED 均成立；PROPOSED 项不影响正确性与可验收性。
