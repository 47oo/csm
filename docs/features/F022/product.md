# F022 Resource 详情页 IP Addresses 区域 — PRODUCT 阶段报告

- **状态**：READY FOR ARCHITECT
- **版本**：v1
- **上游依据**：`docs/product/requirements-v3.md` revision 7 §18（Resource Detail 含 IP Addresses；Interfaces 显示 IP / Network）、§32（详情显示 … IP / Network）、§13/§13.3/§13.4（IP–Interface–Resource 关系）、§14（同 Cluster）、§12（ip_pool 分配来源可空）、§21（软删默认隐藏）、§23（READ 全角色）、§17.1（关联展示排序口径类比）；`docs/api/F010.md` v1 §3/§4；`docs/features/F019/product.md`；用户 2026-10-15 输入。
- **复用说明**：复用 product-manager 2026-10-15 的 F022 澄清报告（结论 `READY FOR ARCHITECT`，无 Blocking Questions）。协调器核验：确认证据覆盖范围与验收；Architect 评估 database/backend/contract 无变更；无未决业务问题。

---

## 1. 目标与范围

补齐 requirements §18 已确认但尚未交付的 **Resource Detail「IP Addresses」区域**（`frontend/src/pages/ResourceDetailPage.tsx` 现仅为占位「IP 地址与分配明细，后续 Feature 提供」）。该区域只读展示该 Resource 经其各 Interface 绑定的 IP 明细。

字段最小集（均取自已确认实体属性）：
- `address`
- `network`（`name` + `cidr`）
- `interface.name`（所属接口）
- `ip_pool.name`（分配来源；池外为 null 时显示「池外（手动）」）
- `description`

不显示 `cluster`（Overview 已有；同 Resource 的 IP 必同 Cluster）。

规则：
- 仅展示该 Resource 各**未删除 Interface** 绑定的**未删除 IP**；不展示未绑定 IP（无 Resource 归属）；不展示已删除 IP（`deleted=exclude`）；默认也不显示绑定到已软删 Interface 的 IP。
- 排序：`interface.name ASC → IP 地址数值 ASC → id ASC`（确定性全序，口径类比 §17.1）。
- 权限：READ 全角色，VIEWER / EDITOR / ADMIN 内容一致。
- 无写入口（编辑/绑定/解绑/转移/释放/分配均不在本区域）。
- 空态 / 错误态 / 加载态显式区分；超单页上限显式提示总数，不静默截断。
- 不改变 F019 每接口「已绑定 IP」展示。

## 2. 明确不做

- 不提供任何写操作入口（分配/绑定/解绑/转移/释放）。
- 不修改或移除 F019 的每接口「已绑定 IP」展示。
- 不新增实体/字段/状态/权限/错误码；不做 IPv6、监控、自动发现。
- 不展示未绑定 IP、已删 IP；默认不展示绑定到已软删 Interface 的 IP。
- 不做 cluster 列、不做已删开关（VIEW_DELETED）。

## 3. 验收标准（映射 §18/§32）

| # | 用户可观察行为 |
| --- | --- |
| A1 | Resource 详情「IP 地址（IP）」区域列出其各 Interface 绑定的 IP：address、Network（name/cidr）、所属 Interface、分配来源（ip_pool，池外显示「池外（手动）」）、description |
| A2 | 跨接口多 IP 全部正确展开，按 interface.name ASC → IP 数值 ASC → id ASC 确定性排序 |
| A3 | 无任何绑定 IP 时显示明确空态，不伪装成错误 |
| A4 | 不展示未绑定 IP，不展示已删除 IP（默认 exclude），默认不展示绑定到已软删 Interface 的 IP |
| A5 | 只读：无编辑/绑定/解绑/转移/释放/分配入口；VIEWER 与 EDITOR 内容一致（READ） |
| A6 | 加载失败显式报错且可重试，不伪装为空列表；超单页上限显式提示总数、不静默截断 |
| A7 | F019 每接口「已绑定 IP」行为无回归 |

> 验收标准未执行；本报告仅定义可验证行为。

## 4. 领域与数据影响

无新实体/关系/状态/唯一性/生命周期；仅跨接口只读聚合展示既有 IPAddress 属性；默认 exclude 已删；无写入、无 Audit。

## 5. Blocking Questions

无。非阻塞默认（绑定到已软删 Interface 的 IP 不显示、只读、保留 F019、字段最小集）已确认。

## 6. 受影响 Feature 与承接

F004（Resource Detail 挂载点）、F007（接口数据源）、F010（IP 数据源）、F013（曾声明免责）、F019（每接口已绑定 IP）为复用对象，不改写交付历史；本变更由新 Feature **F022** 承接。