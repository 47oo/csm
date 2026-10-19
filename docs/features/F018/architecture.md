# F018 全局搜索字段组合展示 — ARCHITECTURE 阶段报告

- **Task**：F018（FEATURE，P1，M9 搜索字段组合）— Architect，Feature 设计模式
- **阶段**：ARCHITECTURE；**结论**：`READY FOR DESIGN`（2026-10-15）
- **Basis**：
  - `docs/product/requirements-v3.md` revision 5（§17.1、T50–T53、§17、§18、§21、§22、§23、§26、§28、§35.1）
  - `docs/features/F018/product.md`（PRODUCT `READY FOR ARCHITECT`，A1–A12，BQ1–BQ5 已确认，无 Blocking Questions）
  - `docs/api/F013.md` v1（§2 搜索响应/typed 行/§2.3 去重排序/§2.6 归一化/§4 软删/§5 只读/§1.2 错误码）
  - `docs/features/F013/architecture.md`（DR-171–DR-189）、`docs/database/f013-search-index.md` v1（DB-D157–DB-D166）
  - `docs/api/F004.md`、`docs/api/F007.md`、`docs/api/F008.md`、`docs/api/F010.md`（Resource / Interface / Network / IPAddress 字段语义与基数）
  - 现有实现：`backend/app/api/v1/search.py`、`app/services/search.py`、`app/schemas/search.py`、`app/models/{resource,interface,network,ip_address}.py`、`frontend/src/components/GlobalSearch.tsx`、`frontend/src/api/search.ts`、`frontend/src/components/globalSearchForm.ts`
  - `docs/architecture/d01-conventions.md` v11（§5 ASCII 折叠、locale 无关原则）、`.pi/skills/data-integrity/SKILL.md`

---

## 1. 方案摘要与边界

### 1.1 方案摘要

F018 是**纯展示层扩展**：在已交付的 F013 全局搜索之上，使 `GET /api/v1/search` 的 `object_type="resource"` 结果行携带**固定超集**的关联展示数据（每个已绑定 IP 一行的 Interface / IPAddress / Network），使前端九个字段的任意组合无需二次请求。不改匹配语义、结果集、去重、顶层排序、分页与 `total`，仍只读、无审计。

1. **响应固定超集**：resource 行统一携带 `resource.related[]`（每 IP 一行）与 `resource.related_total`（截断前总数）；字段集不随所选字段变化。
2. **关联展开与上限**：单台 Resource 按「每个已绑定 IP 一行」展开，行内含 Interface `name`/`interface_type`、IP `address`、Network `name`；每台上限 10 行，超限时服务端返回总数、前端提示「还有 N 条」。
3. **确定性排序**：`interface.name ASC（显式 COLLATE "C"）→ IP 数值 ASC（inet 原生序）→ id ASC`，构成全序，重复查询稳定。
4. **软删/权限继承**：关联对象按结果行 `deleted` 模式过滤；`include/only` 仍需 `VIEW_DELETED`（端点既有门控）；不复用现有对嵌入对象无条件 `include_deleted=True` 的 loader。
5. **前端字段选择器 + localStorage**：九字段多选，偏好仅浏览器本地，读取/写入失败静默回退，不阻断搜索、不回退服务端；未选择时保持 F013 现有展示。
6. **零 Schema 变更**：`database=false`；关联查询命中既有索引，正确性不依赖新增索引。

### 1.2 明确不做（范围外，与 product §2.2 一致）

- 不扩展到各域列表页（仅全局搜索结果）。
- 不做导出、命名/共享视图、账号级服务端偏好。
- 不引入新实体、关系、状态、权限、错误码；不改匹配语义/结果集/去重/顶层排序/分页/`total`。
- 不新增端点、查询参数、写入口；不产生 Audit。
- 无表/列/约束/索引/迁移（`database=false`）。
- 不改变 F013 `cluster`/`ip_address`/`service` 行的结构与展示。
- 本报告不写死最终响应字段命名与 nullable 形态；由 CONTRACT Gate 依本文草案定稿。

### 1.3 layers 与 api_required（确认）

```yaml
layers:
  database: false    # 无 Schema/索引/迁移；见 §6
  backend: true      # search service/schemas 关联取数、排序、上限、软删过滤
  frontend: true     # 字段选择器 + localStorage 回退 + 多值展开
api_required: true   # 仅扩展既有 GET /api/v1/search 的 resource 行
```

评估结论：与已批准计划一致，**无需调整**。

---

## 2. Design Requirements（DR-319–DR-331，接续 F017 DR-318）

| ID | 决策 | 状态 |
| --- | --- | --- |
| DR-319 | **关联取数（分批 IN，无 N+1）**：对当前分页页内的 Resource ID 集合，按 `interfaces WHERE resource_id IN (:rids)` → `ip_addresses WHERE interface_id IN (:iids)` → `networks WHERE id IN (:nids)` 三段批量 IN 取数，再在应用层归组；严禁逐 Resource/逐 Interface 查询。单页 Resource 数 ≤ `page_size`（≤100），IN 批次有界。 | CONFIRMED（§17.1 性能边界）+DESIGN |
| DR-320 | **响应固定超集结构**：`object_type="resource"` 行统一携带 `resource.related[]`（每已绑定 IP 一行）与 `resource.related_total`（截断前总数）；字段集不随查询/所选字段变化。非 resource 行（cluster/ip_address/service）结构不变。 | CONFIRMED（§17.1/T50）+DESIGN |
| DR-321 | **每 Resource 上限 10 与截断前总数**：`related` 最多 10 行；服务端恒返回截断前总数 `related_total`；`related_total ≥ len(related)`；超限时 `related_total = 总数`、`len(related)=10`，前端提示「还有 N 条」（N = `related_total` − 展示行数），不静默截断。 | CONFIRMED（§17.1/T50/T51/A3/A6） |
| DR-322 | **确定性排序 + 显式 collation**：`related` 排序为 `interface.name ASC COLLATE "C"` → `ip_address.address ASC`（PostgreSQL `inet` 原生数值序）→ `ip_address.id ASC`（UUID）。显式 `COLLATE "C"`（字节序、locale 无关），不依赖数据库默认 collation，构成全序、分页/重复查询稳定。 | CONFIRMED（§17.1/T50/A2）+DESIGN |
| DR-323 | **软删口径继承**：关联对象（Interface / IPAddress / Network）按结果行 `deleted` 模式过滤——`exclude` 隐藏已软删关联；`include`/`only` 展示（端点既有 `VIEW_DELETED` 门控不变）；**不得复用** `services/search.py::_build_items` 中对嵌入 Interface/Network/Resource 无条件 `include_deleted=True` 的 loader，必须按模式应用默认软删过滤。无 `VIEW_DELETED` 用户不得见到任何已删关联。 | CONFIRMED（§17.1/T52/A7/A8） |
| DR-324 | **只读无审计**：仍为 `GET /api/v1/search`，无写入口、无副作用、不产生 Audit、重复调用幂等。「展示字段组合」不写入任何持久化对象。 | CONFIRMED（§17.1/T53/A10） |
| DR-325 | **兼容既有字段**：现有 `SearchItem`、嵌套 `resource`/`cluster`/`ip_address`/`service` 的字段名与语义、`matched_field`/`matched_value`、错误码、匹配语义、去重键、顶层排序、分页与 `total` 全部不变；本次**仅新增字段**（加法兼容）。 | CONFIRMED（§17.1/T53/A9/A12） |
| DR-326 | **localStorage 边界**：字段偏好仅浏览器本地，键名/编码由前端约定（建议 `csm.globalSearch.fields.v1`，JSON 字符串数组，白名单校验）；读取缺失/损坏/不可用或写入失败时静默回退会话内 F013 默认展示，不抛错、不阻断搜索、不回退服务端持久化。 | CONFIRMED（§17.1/BQ4/A11） |
| DR-327 | **选择器作用域**：字段选择器仅作用于 `object_type="resource"` 行；cluster/ip_address/service 行展示不变。 | CONFIRMED（§17.1 仅全局搜索结果）+DESIGN |
| DR-328 | **cluster 展示形式**：复用既有 `resource.cluster{id,code,name}`；选择 cluster 字段时以 `code` 为主展示（`name` 作辅助/标题），不新增 cluster 字段、不改其结构。 | PROPOSED→CONTRACT |
| DR-329 | **不新增端点/参数/权限/错误码**：仅扩展 `GET /api/v1/search` 的 `resource` 行响应；`q`/`type`/`deleted`/`page`/`page_size` 不变；权限与 401/403/422/500 语义不变；无 CSRF、无请求体。 | CONFIRMED（product §2.2 + 计划） |
| DR-330 | **Contract 修订**：`docs/api/F013.md` v1→v2，在 §2.2 增补 `resource.related`/`related_total` 字段（类型/nullable/空语义/排序/上限/总数）、记录本设计与 A1–A12 映射；既有裁定（§2.3/§2.4/§4/§5/§6）**保持不变**。 | CONFIRMED+DESIGN |
| DR-331 | **Database NOT_REQUIRED**：无 Schema/索引/迁移；关联查询命中既有索引（`ix_interfaces_resource_id`、`ix_ip_addresses_interface_id`、`networks` PK），正确性不依赖新增索引。 | CONFIRMED+DESIGN（§17.1 / `database=false`） |

---

## 3. Domain / Data Impact

| 影响面 | 关系/来源 | 作用域 | 生命周期 | 依据及状态 | 裁定 |
| --- | --- | --- | --- | --- | --- |
| 搜索结果 resource 行关联视图（派生，非实体） | Resource → Interface(N) → IPAddress(N) → Network(N:1) | 全局只读、仅 resource 行 | 无（不落库） | §17.1/T50 CONFIRMED | DR-319/DR-320 |
| Resource→Interface 基数 | 1:N（`interfaces.resource_id` NOT NULL） | 每 Resource | 无 | §10/F007 CONFIRMED | DR-319 |
| Interface→IPAddress 基数 | 1:N（`ip_addresses.interface_id` 可空；未绑定不展示） | 每 Interface | 无 | §13/F010 CONFIRMED | DR-319（A8） |
| IPAddress→Network 基数 | N:1（`ip_addresses.network_id` NOT NULL） | 每 IP | 无 | §11/F008 CONFIRMED | DR-319 |
| 软删可见性 | Interface / IPAddress / Network 的 `deleted_at` | 随结果行 `deleted` 模式 | 软删即隐藏/恢复重现 | §21/T52 CONFIRMED | DR-323 |
| GIN trigram 索引 | 不新增、不修改；F013 DB-D157–DB-D166 不变 | — | — | §17.1/database=false | DR-331 |

**数据完整性对应表**（纯只读视图，无写入约束）

| 规则依据及版本 | 作用域/读取入口 | 数据库保证 | 业务层保证 | 并发/生命周期边界 | 验证与证据 |
| --- | --- | --- | --- | --- | --- |
| §13/§14 IP 归属 | 关联行 Interface/IP/Network 一致性 | `ip_addresses.interface_id` FK + Cluster 一致性；删除 Interface 需先处理未删 IP（RESTRICT） | 仅展示 `interface_id` 非空的 IP（A8） | exclude 下活跃 IP 必指向活跃 Interface/Network（DB 引用保护） | F018-A4/A8 |
| §21 未删默认 | 关联三对象过滤 | 默认 loader criteria 过滤 `deleted_at` | 按结果行 `deleted` 模式显式过滤；不复用无条件 `include_deleted=True` loader | 软删后即消失；恢复重现 | F018-A7 |
| §4 稳定 ID | 关联行身份与排序 tiebreak | PK UUID | 行 `id` = IPAddress id；排序末键 id ASC | 改名不改 id | F018-A2 |
| §22 只读 | 搜索 | 无写 | 无写端点、不写 Audit、幂等 | — | F018-A10 |

---

## 4. 关联模型与裁定细节（A1–A9）

### 4.1 取数算法（DR-319）

设当前分页页的 Resource 候选集合为 `R`（`|R| ≤ page_size ≤ 100`；仅 `object_type="resource"` 行需要关联）：

1. `I = SELECT * FROM interfaces WHERE resource_id IN (:r_ids) [AND deleted_at IS NULL]`
2. `IP = SELECT * FROM ip_addresses WHERE interface_id IN (:i_ids) [AND deleted_at IS NULL]`（`interface_id IS NULL` 的行天然不入选 → A8）
3. `N = SELECT * FROM networks WHERE id IN (:n_ids) [AND deleted_at IS NULL]`
4. 应用层按 `resource_id` 归组，构造 `interface.name / interface.interface_type / ip.address / network.name`，按 §4.2 排序，取前 10，`related_total = 归组后总行数`。

- 软删过滤：`deleted=exclude` 施加默认过滤（不带 `include_deleted`）；`deleted∈{include,only}` 施加 `include_deleted=True`（端点已鉴权 VIEW_DELETED）。
- 不使用 ORM 关系惰性加载（避免 N+1）；不使用现有对嵌入对象的无条件 `include_deleted=True` loader（DR-323）。
- 单次 JOIN 版本在保持相同软删语义与排序时等价、可接受；推荐分段 IN 以便按模式逐表过滤、避免笛卡尔放大。

### 4.2 排序（DR-322）

`ORDER BY interfaces.name COLLATE "C" ASC, ip_addresses.address ASC, ip_addresses.id ASC`

- `COLLATE "C"`：字节序、locale 无关，避免依赖数据库默认 collation 造成跨环境不确定。
- `ip_addresses.address` 为 `inet`（`family=4 AND masklen=32`），其原生 btree 序对 IPv4 即数值序（`10.10.1.9 < 10.10.1.10`）。
- `id`（IPAddress UUID）作末键，保证同 `(name, address)` 时全序。

### 4.3 上限与总数（DR-321）

- `related` 最多 10 行；`related_total = 归组后全部行数`。
- `related_total ≥ len(related)`；当 `related_total > 10` 时 `len(related)=10`，前端显示「还有 N 条」（N = `related_total` − 10）。
- `related_total = 0` → `related = []`，不伪造占位行（A5）。

### 4.4 软删不变量（DR-323，A7）

- `exclude` 模式下，活跃 IP 必指向活跃 Interface 与活跃 Network：删除 Interface 前须先处理其未删 IP（§21 RESTRICT），删除 Network 前须先处理其未删 IP。
- 仍**显式**对三表施加 `deleted` 模式过滤（防御性 + 不依赖上述不变量）。
- `include`/`only`：展示已删关联；端点既有 `VIEW_DELETED` 检查保证无权限用户 403。
- 现有 `_build_items` 对嵌入 Interface/Network/Resource 的无条件 `include_deleted=True`（F013 既有行为）**不修改**；F018 关联取数为新增路径，独立按模式过滤。

---

## 5. API 草案（仅扩展 `GET /api/v1/search` 的 resource 行）

> `docs/api/F013.md` 由 v1 修订为 v2。以下为草案，命名/nullable 待 CONTRACT 定稿。

### 5.1 查询参数 / 权限 / 错误（不变）

- 参数：`q`（必填）、`type`、`deleted`、`page`、`page_size` — 语义、校验、默认值不变。
- 权限：READ 全角色；`deleted∈{include,only}` 需 `VIEW_DELETED`，否则 403 `FORBIDDEN{reason:"permission"}`。
- 错误：401 / 403 / 422 / 500 不新增 code / reason；校验顺序不变。

### 5.2 `resource` 行新增字段（草案）

| 字段 | 类型 | nullable | 空语义 | 排序 | 上限/总数 |
| --- | --- | --- | --- | --- | --- |
| `related` | `SearchResourceRelated[]` | 否（resource 行） | 无已绑定 IP 时为 `[]`，不伪造行 | `interface.name COLLATE "C" ASC → ip_address.address ASC → id ASC` | 最多 10 行 |
| `related_total` | int ≥ 0 | 否（resource 行） | 无关联时为 `0` | — | 截断前总数；`≥ len(related)` |

`SearchResourceRelated`（草案）：

| 字段 | 类型 | nullable | 说明 |
| --- | --- | --- | --- |
| `id` | string(UUID) | 否 | 行身份 = IPAddress id；排序末键 |
| `interface` | object | 否 | `{id(UUID), name(string), interface_type(string)}`；`interface_type∈{PHYSICAL,VIRTUAL,BOND,BRIDGE,VLAN,LOOPBACK,OTHER}` |
| `ip_address` | object | 否 | `{id(UUID), address(string 点分十进制)}` |
| `network` | object | 否 | `{id(UUID), name(string)}` |

**非 resource 行**（`cluster` / `ip_address` / `service`）响应**不变**：其嵌套 `resource` 对象是否出现 `related`/`related_total` 由 CONTRACT 定稿；推荐默认 `related=null`、`related_total=null`。

### 5.3 响应示例（草案）

```json
{
  "items": [
    {
      "object_type": "resource",
      "id": "…",
      "matched_field": "hostname",
      "matched_value": "gpu0701",
      "resource": {
        "id": "…", "hostname": "gpu0701",
        "resource_type": "BARE_METAL", "role": "COMPUTE", "status": "IDLE",
        "cluster": {"id": "…", "code": "N96P", "name": "…"},
        "related": [
          {
            "id": "…",
            "interface": {"id": "…", "name": "ib0", "interface_type": "PHYSICAL"},
            "ip_address": {"id": "…", "address": "10.10.1.9"},
            "network": {"id": "…", "name": "ib"}
          }
        ],
        "related_total": 23
      },
      "cluster": null, "ip_address": null, "service": null
    }
  ],
  "page": 1, "page_size": 20, "total": 42
}
```

---

## 6. Database 影响：无（NOT_REQUIRED）

- 无表/列/约束/索引/触发器/迁移；`database=false`，Database 无设计交付物。
- 依据：§17.1 明示不改查询语义与结果集；F018 `database=false` 已批准；关联取数为只读派生视图。
- 查询命中既有索引：`ix_interfaces_resource_id`（F007）、`ix_ip_addresses_interface_id`（F010，DB-D127）、`networks` PK（及 `uq_networks_cluster_id_name_key`）。
- 正确性不依赖索引；F013 GIN 索引与 DB-D157–DB-D166 裁定不变。

---

## 7. Test Work

### 7.1 验收映射

| 验收 | 判据 | 层次 |
| --- | --- | --- |
| A1 | resource 行返回固定超集：`related[]` 含 Interface name/interface_type、IP address、Network name | 集成（真 PG） |
| A2 | 排序 `interface.name COLLATE "C" → IP 数值 → id`；重复查询稳定全序 | 集成（真 PG） |
| A3 | 每 Resource ≤10 行且返回截断前总数；`related_total ≥ len(related)` | 集成 |
| A4 | 多网卡/多 IP 每 IP 一行；同 IP 不重复、不多造行 | 集成 |
| A5 | 无可展示关联时 `related=[]` | 集成 |
| A6 | 超限时前端显式提示「还有 N 条」 | 前端机制 + 集成 |
| A7 | `exclude` 隐藏已删关联；`include/only` 无 VIEW_DELETED 仍 403 | 集成 |
| A8 | 未绑定 Interface 的 IP 不出现 | 集成 |
| A9 | 改展示字段组合不改变结果集/去重/顶层排序/分页/`total` | 集成回归 |
| A10 | 只读：无写入口、无副作用、不写 Audit、幂等 | 集成 |
| A11 | 字段选择器九字段；偏好 localStorage 刷新后沿用 | 前端机制 |
| A12 | 未选择字段时保持 F013 展示，无回归 | 前端机制 + 集成 |

### 7.2 边界用例

- 多网卡（`COLLATE "C"` 字节序，`eth10` 与 `eth9`）；多 IP（数值序 `10.10.1.9 < 10.10.1.10`）。
- 无 IP（有 Interface 无 IP）→ `related=[]`、`related_total=0`。
- 超上限（`related_total=23` → 10 行 + 「还有 13 条」）。
- 已删关联（exclude 隐藏；include/only 且 ADMIN 可见；无权限 403）。
- 未绑定 IP（`interface_id IS NULL`）永不出现。
- 中文与空格名称原样展示、`COLLATE "C"` 排序确定。
- 同 `(name,address)` 用 `id ASC` 兜底。

### 7.3 真实 PG 要点

- `COLLATE "C"` 排序、`inet` 数值序、默认软删过滤效果、分段 IN 执行计划必须真 PG。
- 断言 `exclude` 下已删关联不入选（证明未复用 `include_deleted=True` loader）。
- 审计表在搜索前后无新增行（A10）。

### 7.4 前端机制级验证

- 纯逻辑模块承载字段白名单校验、localStorage 读写与失败回退、默认组合、「还有 N 条」计算；`scripts/smoke-client.mjs` 机制级冒烟。
- 组件层：选择器九字段、多值展开、超限提示、非 resource 行不变、存储不可用时静默回退且搜索可用。

---

## 8. Frontend / Backend Work

**Backend**
- `app/schemas/search.py`：新增 `SearchResourceRelated`（及嵌套）与 `SearchResourceObject.related`/`related_total`。
- `app/services/search.py`：resource 行按 DR-319 三段批量 IN、DR-322 排序、DR-321 截断与总数、DR-323 按 `deleted` 模式过滤。
- `app/api/v1/search.py`：路由/权限/参数不变。
- 无 Schema/迁移；无写端点；不写 Audit。

**Frontend**
- 新增字段选择器（九字段多选，仅 resource 行）与多值展开；超限提示「还有 N 条」。
- 偏好 localStorage（建议键 `csm.globalSearch.fields.v1`，JSON 白名单），读写失败静默回退。
- `frontend/src/api/search.ts`：`SearchResourceRef` 增补 `related`/`related_total`。
- 纯逻辑模块 + smoke 机制级验证；非 resource 行展示不变。

---

## 9. 风险与待核对项

| 项 | 类型 | 建议默认（待 CONTRACT 定稿） |
| --- | --- | --- |
| 选择器作用行类型 | 非阻塞 | 仅 `resource` 行；其余不变（DR-327） |
| 默认字段组合 | 非阻塞 | 未选择时 = F013 现有展示（A12） |
| 上限口径 | 非阻塞 | 上限恒 10；`related_total` 为截断前总数；N = 总数 − 展示行数（DR-321） |
| 已删上下文 | 非阻塞 | 关联随结果行 `deleted` 模式；`include/only` 需 VIEW_DELETED（DR-323） |
| collation | 非阻塞 | `interface.name COLLATE "C" ASC`；IP `inet` 数值序；末键 id ASC（DR-322） |
| cluster 展示形式 | 非阻塞 | 复用 `resource.cluster`，以 `code` 为主、`name` 为辅（DR-328） |
| 响应字段命名 / nullable | 非阻塞 | 建议 `related`/`related_total` 挂于 `resource`；非 resource 行 `null`；以 CONTRACT 为准 |

**风险**
- 中：若 CONTRACT 将 `related` 挂到顶层而非嵌套 `resource`，前端类型需相应调整（命名层，不影响取数/排序/软删裁定）。
- 低：`COLLATE "C"` 对非 ASCII 名称按字节排序，可能与「拼音序」直觉不同；全序确定，正确性不受影响。
- 低：`related_total` 与顶层 `total` 语义不同，文档与 UI 需明确区分。

**结论**：无 Blocking Questions。**Status：`READY FOR DESIGN`**。下一步：CONTRACT Gate 定稿 `docs/api/F013.md` v2；TEST_DESIGN 给 A1–A12 判据与真 PG 要点。无 Database Gate 事项（`database=false`）。