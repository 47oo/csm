# F022 Resource 详情页 IP Addresses 区域 — ARCHITECTURE 阶段报告

- **Task**：F022（FEATURE，P1，M13）— Architect，Feature 设计模式
- **阶段**：ARCHITECTURE；**结论**：`READY FOR DESIGN`（2026-10-15）
- **Basis**：`docs/product/requirements-v3.md` revision 7 §18/§32/§13/§13.3/§13.4/§14/§12/§21/§23/§17.1；`docs/features/F022/product.md` v1（A1–A7）；`docs/project/project-plan.yaml` revision 10（F022：`layers{database:false,backend:false,frontend:true}`、`api_required:false`）；`docs/api/F007.md` v1 §4/§6.1、`docs/api/F010.md` v1 §3/§4/§5/§6.1；现有 `ResourceDetailPage.tsx`、`InterfacesPanel.tsx`、`interfaceIpSelection.ts`、`api/ipAddresses.ts`、`api/interfaces.ts`、`docs/architecture/d01-conventions.md` v11 §5.9。

## 1. 方案摘要、边界与明确不做

F022 是**纯前端只读聚合**：把 F004 `ResourceDetailPage` 中现为占位（`PLACEHOLDER_AREAS`：`IP 地址（IP）`）的区域替换为真实展示（需求 §18 IP Addresses）。

1. **逐接口查询（方案 a）**：`GET /interfaces?resource_id=<id>&deleted=exclude&sort=name&order=asc`（F007 §6.1）取未删接口；再对每个未删接口 `GET /ip-addresses?interface_id=<id>&deleted=exclude&sort=address&order=asc&page_size=100`（F010 §6.1，复用 `buildInterfaceBoundIpsQuery`）。
2. **合并 + 全序排序**：按 `interface.name ASC → IP 数值 ASC → id ASC`（§17.1 类比）；新纯逻辑模块承担。
3. **字段**：`address`、`network{name,cidr}`、`interface.name`、`ip_pool.name`（null→「池外（手动）」）、`description`（null→「—」）；不显示 `cluster`。
4. **状态**：Loading / Empty / Error（可重试，不伪装空）/ 截断提示（单接口 IP `total>items` 显式提示）。
5. **只读、全角色一致**：READ；无写入口；内容对 VIEWER/EDITOR/ADMIN 一致。
6. **零后端 / 零 Schema / 零契约**：`backend=false`、`database=false`、`api_required=false`。

明确不做：不新增端点/参数/嵌套响应、不改 F007/F010 契约；无写入口；不修改/合并 F019 每接口「已绑定 IP」展示；不展示未绑定 IP、已删 IP（默认 exclude）；不显示 `cluster` 列、不提供 VIEW_DELETED 开关；不做 IPv6/监控/自动发现；无表/列/约束/索引/迁移。

```yaml
layers: {database: false, backend: false, frontend: true}
api_required: false
```

## 2. Design Requirements（DR-382–DR-400）

| ID | 决策 | 状态 |
| --- | --- | --- |
| DR-382 | 逐接口查询：`GET /interfaces?resource_id&deleted=exclude&sort=name&order=asc` + 每接口 `GET /ip-addresses?interface_id&deleted=exclude&sort=address&order=asc&page_size=100`（复用 `buildInterfaceBoundIpsQuery`）。 | CONFIRMED |
| DR-383 | 接口列表分页 `page_size≤100`，逐页取全（page 递增至覆盖 `total`），不静默遗漏；安全上限（≤50 页）超限显式提示。 | CONFIRMED（上限值 PROPOSED） |
| DR-384 | 新增 `frontend/src/components/resourceIpAddresses.ts`（纯逻辑，无 JSX/React，供 smoke 加载）：查询构造、合并行、比较器、边界判定、部分失败汇总。 | CONFIRMED |
| DR-385 | 总排序 `interface.name ASC`（字符串码序，同 F007 `sort=name`）→ IP 数值 ASC → `id` ASC（确定性全序）。 | CONFIRMED |
| DR-386 | 字段最小集：`address`、`network{name,cidr}`、`interface.name`、`ip_pool.name`（null→「池外（手动）」）、`description`（null→「—」）；不显示 `cluster`。 | CONFIRMED |
| DR-387 | Loading/Empty/Error 三态显式区分；错误可重试，不伪装空列表。 | CONFIRMED |
| DR-388 | 单接口 IP `total>items` 显式提示总数，不静默截断；复用 `interfaceIpTotalBoundary`。 | CONFIRMED |
| DR-389 | 部分失败：全部失败→ErrorState（可重试）；部分失败→展示已加载行 + 警告提示失败接口；重试重取全部；不静默丢弃。 | PROPOSED（默认采纳） |
| DR-390 | 只读与权限：无写入口；查询 READ 全角色；内容一致；服务端权威（401 先于 403）。 | CONFIRMED |
| DR-391 | 软删口径：接口/IP 均 `deleted=exclude`；绑定到已软删 Interface 的 IP 因只查未删接口自然不出现；不依赖 VIEW_DELETED、不提供已删开关。 | CONFIRMED |
| DR-392 | 与 F019 关系：保留、不合并、不改动其组件/请求/缓存；独立请求、不共享缓存（避免回归 F019、提升耦合）。 | CONFIRMED（不共享缓存 PROPOSED） |
| DR-393 | 挂载点：`ResourceDetailPage` 从 `PLACEHOLDER_AREAS` 移除 `IP 地址（IP）`，改为 `<ResourceIpAddressesPanel resource user />`；占位容器为空时移除。 | CONFIRMED |
| DR-394 | Contract `NOT_REQUIRED`；复用 F007/F010；最小使用说明落本文件 §5 与 implementation.md。 | CONFIRMED |
| DR-395 | Database NOT_REQUIRED：命中既有 `ix_interfaces_resource_id`、`ix_ip_addresses_interface_id`。 | CONFIRMED |
| DR-396 | Backend NOT_REQUIRED：仅复用既有 GET。 | CONFIRMED |
| DR-397 | 可冒烟性：纯逻辑集中于 `resourceIpAddresses.ts`，供 smoke 断言查询串/合并/排序/边界/部分失败。 | CONFIRMED |
| DR-398 | 逐接口 IP 请求并发有界（≤6）。 | PROPOSED |
| DR-399 | 不显示未绑定 IP、已删 IP、`cluster` 列、VIEW_DELETED 开关、`version`/时间戳等非验收字段。 | CONFIRMED |
| DR-400 | 命名/文件冻结：`ResourceIpAddressesPanel.tsx` + `resourceIpAddresses.ts`；数值比较器本地实现，**不修改** F019 `interfaceIpSelection.ts`（仅 import 两个既有导出）。 | PROPOSED |

## 3. Domain / Data Impact

| 影响面 | 关系/来源 | 作用域 | 生命周期 | 依据 | 裁定 |
| --- | --- | --- | --- | --- | --- |
| 只读聚合视图（派生） | Resource 1:N Interface 1:N IPAddress | 单 Resource | 不落库 | §4/§13/§18 | DR-382/384 |
| 排序口径 | 类比 §17.1 | 展示层 | 不落库 | §17.1/§18 | DR-385 |
| 软删可见性 | `interfaces.deleted_at`、`ip_addresses.deleted_at` | 全流程 exclude | 软删隐藏 | §21 | DR-391 |
| 未绑定 IP | `interface_id IS NULL` | 排除 | — | §13/§18 | DR-382/399 |

无新实体/关系/状态/唯一性/生命周期/权限/错误码；无写入、无 Audit；无 Schema/迁移；无需 Database 角色核对。

## 4. Frontend / Backend Work

### Backend — NOT_REQUIRED
复用 `GET /api/v1/interfaces`（F007 §6.1）与 `GET /api/v1/ip-addresses`（F010 §6.1）；不新增路由/Schema/服务层；不改契约。

### Frontend — REQUIRED
1. **`frontend/src/components/resourceIpAddresses.ts`（新增，纯逻辑）**：`buildResourceInterfacesQuery(resourceId)`、`buildResourceInterfaceIpsQuery(interfaceId)`（复用 `buildInterfaceBoundIpsQuery`）、`mergeResourceIpRows(interfaces, ipsByInterfaceId)`、`compareResourceIpRows`、边界/部分失败汇总。
2. **`frontend/src/components/ResourceIpAddressesPanel.tsx`（新增，组件）**：挂载时取接口（翻页取全）→ 逐接口取 IP（有界并发）→ 合并排序 → 渲染 `DataTable`；状态机 loading/success(empty/truncated/partial)/error；字段按 DR-386；无写按钮、无 cluster 列。
3. **`frontend/src/pages/ResourceDetailPage.tsx`（改）**：移除 IP 占位，挂载新组件。
4. API client 复用 `listInterfaces`/`listIpAddresses`，不新增 client 函数。
5. UI 复用 `ui/*` + Ant Design；Tailwind 布局。

## 5. Contract 引用与状态

**NOT_REQUIRED**（`api_required=false`）。无 `docs/api/F022.md`；不修订 F007/F010。

| 复用条款 | 用途 | 最小使用说明 |
| --- | --- | --- |
| F007 §4/§6.1 | 接口列表 | `resource_id&deleted=exclude&sort=name&order=asc&page&page_size=100`；`{items,page,page_size,total}` |
| F010 §3 | 响应对象 | `address`、`network{id,name,cidr}`、`interface{id,name,resource}|null`、`ip_pool{id,name}|null`、`description|null` |
| F010 §4/§6.1 | IP 列表过滤 | `interface_id&deleted=exclude&sort=address&order=asc&page=1&page_size=100`；page_size 1–100 |
| F010 §5 | 软删可见性 | 默认 exclude；不请求 include/only（不需 VIEW_DELETED） |
| F010 §1.2/§1.3 | 只读语义 | 列表=READ；401 先于 403 |

## 6. Test Work

### 6.1 验收映射（A1–A7）
| 验收 | 判据 | 层次 |
| --- | --- | --- |
| A1 | 列出 address/network(name,cidr)/interface/ip_pool（null→池外手动）/description | 真 PG + 机制级 + 浏览器 |
| A2 | 跨接口多 IP 全展开、确定性排序 | 机制级 + 真 PG |
| A3 | 无绑定 IP 显式空态 | 机制级 + 浏览器 |
| A4 | 不展示未绑定/已删 IP；默认不展示已软删 Interface 上的 IP | 真 PG |
| A5 | 只读无写入口；VIEWER/EDITOR 内容一致 | 静态 + 机制级 |
| A6 | 失败可重试不伪装空；超上限显式提示 | 机制级 + 浏览器 |
| A7 | F019 无回归 | 静态 + 真 PG 回归 |

### 6.2 分层
- 静态：`ResourceDetailPage` 无 IP 占位、含新组件；新组件无写控件/cluster 列/已删开关；未修改 `interfaceIpSelection.ts`/`InterfacesPanel.tsx`。
- 机制级 smoke：`resourceIpAddresses.ts` 查询串、合并行数、排序（大小写/数值序/id 兜底）、ip_pool null 文案、description null 占位、边界 truncated/complete/empty、部分失败汇总。
- 真 PG：构造跨接口多 IP、未绑定 IP、已删 IP、已软删 Interface 绑定 IP；断言可见集合；只读无副作用。
- 人工浏览器：区域渲染、空/错/加载/截断、无写入口、VIEWER/EDITOR 一致。

### 6.3 无 DOM 工具替代
仓库无 DOM/E2E 工具：浏览器交互标记 NOT TESTED；替代 = 机制级 smoke + typecheck + build + 静态核对 + 真 PG。

### 6.4 不回归集
F019 每接口「已绑定 IP」；F007 接口列表；F010 IP 列表；`ResourceDetailPage` 其它区域。

## 7. 决策、风险与 Implementation Layers

决策：DR-382–388、390–391、393–397、399 CONFIRMED；DR-383 上限值、DR-389、DR-392 不共享缓存、DR-398 并发度、DR-400 命名/不修改 F019 为 PROPOSED（默认采纳）。

风险：接口数×单接口请求放大（中，有界并发+逐页）；与 F019 重复拉取（低，接受）；部分失败误读为空（中，显式警告/错误态）；排序口径不一致（低，机制级断言）；超上限截断误认为完整（低，显式提示）；改 F019 模块回归（低，DR-400 不改）。

```yaml
layers: {database: false, backend: false, frontend: true}
api_required: false
```
实现顺序：`resourceIpAddresses.ts` → `ResourceIpAddressesPanel.tsx` → `ResourceDetailPage` 挂载替换 → smoke + 真 PG + 人工浏览器。

## 8. 验证策略与不可验证项

验证：`typecheck`/`build`/`smoke:client`；真 PG 集成（接口/IP exclude、只读无副作用、F019 回归）；人工浏览器。
不可验证（如实标记）：真实浏览器 DOM 渲染/布局/可访问性；浏览器驱动端到端；大接口数/大 IP 数性能基线；PROPOSED 项按可观察行为判定不锁定数字。

## 9. 结论
需求依据充分，无 Blocking Questions；纯前端只读聚合；Backend/Database/Contract 均 NOT_REQUIRED；`READY FOR DESIGN`。

GIT: NONE
---

## 10. 最终设计签核（CONTRACT Gate）

- **签核者**：Architect；**结果**：`READY FOR IMPLEMENTATION`
- **签核版本**：F022 Design v1（本文件）；Contract `NOT_REQUIRED`
- **核对的 Database / Backend**：均 `NOT_REQUIRED`（查询命中既有 `ix_interfaces_resource_id`、`ix_ip_addresses_interface_id`；无服务端改动）
- **核对的 Test Design**：`docs/features/F022/test-report.md` TD-1
- **上游依据**：requirements-v3.md revision 7 §18/§32/§13/§14/§12/§21/§23/§17.1；F022 product v1（A1–A7）；project-plan.yaml revision 10（用户 2026-10-15 批准）
- **覆盖 Feature**：F022
- **一致性**：A1–A7 ↔ §18/§32 ↔ DR-382–DR-400 ↔ T01–T07 无缺口/矛盾；Contract/Database/Backend NOT_REQUIRED 成立；PROPOSED 项不影响正确性与可验收性。
