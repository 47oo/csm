# API Contract — F010 资源详情与关联查询

> Status: **READY**
> Feature: F010（E05，P1）
> Author Role: architect
> Source: `docs/api/api-conventions.md`、ADR-0003 §2/§6、ADR-0004、ADR-0005、`docs/api/f002-bare-metal.md`、`f004-network-interface.md`、`f005-ip-address.md`、`f006-virtual-machine.md`、`f007-container.md`、`f008-service.md`、`docs/architecture/f010-resource-detail-handoff.md`
> 本文件是 F010 前后端与测试的**共同协议与单一权威**。

---

## 1. 范围与前提

1. 本契约定义 F010 唯一新增的产品 API：**`GET /api/bare-metals/{bare_metal_id}/related`**（BareMetal 上下文五类关联的只读聚合读取），共 **1 个端点**（§2）。
2. 不重新定义任何资源表示、错误信封、状态码或 Empty / NotFound 通用语义；一律遵循 `api-conventions.md` 与各资源契约；本文件只做「聚合读取」的具体化。
3. **canonical 与聚合**：五类成员的 canonical 读取分别为 `GET /api/network-interfaces?bare_metal_id=`、`GET /api/ip-addresses?network_interface_id=`、`GET /api/virtual-machines?bare_metal_id=`、`GET /api/containers?carrier_type=&carrier_id=`、`GET /api/services?carrier_type=&carrier_id=`；本端点为它们的**只读组合**，其成员集合与 canonical 一致（各并集按 `id` 去重）。
4. **只读**：不改动任何数据，不提供任何写 / 删除 / 恢复 / 解绑能力。
5. 认证：`/api/*`（除登录）要求认证；未认证 → `401 UNAUTHENTICATED`（ADR-0005）。
6. 无新领域对象 / 字段 / 关系 / 状态 / 唯一性规则；不返回推导出的 Cluster 归属。

## 2. 端点

### `GET /api/bare-metals/{bare_metal_id}/related` — BareMetal 五类关联聚合（只读）

| 项 | 值 |
|---|---|
| Method | `GET` |
| Path | `/api/bare-metals/{bare_metal_id}/related` |
| Path parameter | `bare_metal_id`（integer） |
| Query parameter | **无** |
| Request body | 无（客户端不得发送） |
| 认证 | **必需**（§6） |

**语义（五类「与 B 相关」的定义）**

设 B 为路径所指 BareMetal。

| 类 | 定义 |
|---|---|
| `network_interfaces` | 活跃 NIC 且 `nic.bare_metal_id = B.id`（1 跳） |
| `ip_addresses` | 活跃 IP 且 `ip.network_interface_id ∈ {B 的活跃 NIC}`（2 跳；IP 无 `bare_metal_id`） |
| `virtual_machines` | 活跃 VM 且 `vm.bare_metal_id = B.id`（1 跳） |
| `containers` | 活跃 Container 且载体为 B，**或**载体为 B 的活跃 VM（1~2 跳，含间接） |
| `services` | 活跃 Service 的载体与 `R(B) = {B} ∪ {B 的活跃 VM} ∪ {载体为 B 或 B 上活跃 VM 的活跃 Container}` 有交集（1~3 跳，含间接） |

- 全部只含**活跃**资源；已逻辑删除的不出现也不计入 `total`。
- `containers` / `services` 并集**按 `id` 去重**（同一资源只出现一次）。
- 各类 `items` **按 `id` 升序**。
- 深度固定 ≤3，无递归 / 任意深度遍历。

**Response 200**

```json
{
  "network_interfaces": {
    "items": [
      { "id": 11, "bare_metal_id": 1, "name": "eth0",
        "technology_type": "Ethernet", "purpose": "Business",
        "created_at": "2026-09-18T10:00:00Z", "updated_at": "2026-09-18T10:00:00Z" }
    ],
    "total": 1
  },
  "ip_addresses": {
    "items": [
      { "id": 21, "network_interface_id": 11, "ip_address": "10.0.0.5",
        "created_at": "2026-09-18T10:00:00Z", "updated_at": "2026-09-18T10:00:00Z" }
    ],
    "total": 1
  },
  "virtual_machines": {
    "items": [
      { "id": 31, "bare_metal_id": 1, "name": "vm-a",
        "cpu": null, "memory": null, "disk": null, "os": null,
        "hypervisor": null, "owner": null,
        "created_at": "2026-09-18T10:00:00Z", "updated_at": "2026-09-18T10:00:00Z" }
    ],
    "total": 1
  },
  "containers": {
    "items": [
      { "id": 41, "carrier_type": "VIRTUAL_MACHINE", "carrier_id": 31, "name": "c-a",
        "image": null, "cpu": null, "memory": null, "owner": null,
        "created_at": "2026-09-18T10:00:00Z", "updated_at": "2026-09-18T10:00:00Z" }
    ],
    "total": 1
  },
  "services": {
    "items": [
      { "id": 51, "name": "svc-a",
        "service_type": null, "url": null, "port": null, "protocol": null,
        "owner": null, "description": null,
        "carriers": [ { "carrier_type": "VIRTUAL_MACHINE", "carrier_id": 31 } ],
        "created_at": "2026-09-18T10:00:00Z", "updated_at": "2026-09-18T10:00:00Z" }
    ],
    "total": 1
  }
}
```

- 顶层字段集合**封闭**：恰为 `network_interfaces` / `ip_addresses` / `virtual_machines` / `containers` / `services`；每类为 `{items, total}`，`total == len(items)`。
- `items` 元素 schema **逐字段等于**对应 canonical Read：`NetworkInterfaceRead`、`IpAddressRead`（**无 `cluster_id`**）、`VirtualMachineRead`、`ContainerRead`（载体以 `carrier_type`+`carrier_id`）、`ServiceRead`（含 `carriers`）。
- 不存在 `deleted_at`、Cluster 状态、推导 Cluster 归属、DataCenter / 位置、自动发现 / 实时状态源字段，也不存在五类之外的资源字段。
- 可选字段空值返回 `null` 而非省略；时间为 RFC 3339 字符串（前端作不透明字符串）。

**Error Semantics**

| 情形 | HTTP | `error.code` | `details[].field` |
|---|---|---|---|
| `{bare_metal_id}` 不存在**或**对应 BareMetal 已被逻辑删除 | `404` | `NOT_FOUND` | —（`details == []`） |
| `bare_metal_id` 非整数 | `400` | `VALIDATION_ERROR` | `"bare_metal_id"` |
| 未认证 | `401` | `UNAUTHENTICATED` | — |
| 未预期错误 | `500` | `INTERNAL_ERROR` | — |

- `404` **同时**覆盖「不存在」与「已逻辑删除」，两者不区分（`api-conventions.md` §6）。
- 五类**共用同一 404 判定**：B 不存在 / 已删 → 整体 404；任何一类为空**绝不**产生 404。

**Empty / Not Found 语义**

| 情形 | 响应 |
|---|---|
| B 不存在或已被逻辑删除 | `404 NOT_FOUND` |
| B 存在且活跃、某类（或全部类）无关联 | `200`，该类 `{ "items": [], "total": 0 }`（**Empty**） |

前端必须为 **Empty** 与 **Not Found** 渲染**不同**状态（R-QUERY-004）。Empty 不得渲染为错误、不得触发全局会话失效。

**判定顺序与一致性（REQUIRED）**

1. **先**确认 B 存在且活跃（唯一 404 网关）；**后**派生五类。
2. 各派生只经既有 canonical 过滤原语；不引入第二条 `deleted_at IS NULL` 谓词（ADR-0004）；嵌套枚举不得因某一子资源缺失 / 已删而抛出 404。
3. 全部读取在同一请求事务内完成，各清单在同一读取路径上派生并共用同一 404 网关。**不声称严格一致快照**：默认隔离级别为 READ COMMITTED，各语句各自取快照，并发软删期间某清单可能瞬时少一项（不会产生错误的 404 / 500；重复项会被按 id 去重吸收，跳过项不会）。读取不写数据，无需加锁；若产品要求严格一致快照，需单独裁定。

## 3. 错误信封

复用 `api-conventions.md` §5 的统一信封与既有实现，不另立一套。前端按 `error.code` 分支，**不解析 `message`**。

```json
{ "error": { "code": "NOT_FOUND", "message": "资源不存在", "details": [] } }
```

## 4. 状态码汇总（本契约范围）

| 状态码 | 何时出现 | `error.code` |
|---|---|---|
| `200` | 读取成功（含各类空集合） | — |
| `400` | `bare_metal_id` 非法 | `VALIDATION_ERROR` |
| `401` | 未认证 | `UNAUTHENTICATED` |
| `404` | B 不存在或已被逻辑删除 | `NOT_FOUND` |
| `500` | 未预期服务端错误 | `INTERNAL_ERROR` |
| `403` | **不存在触发路径**（V1 仅两态；码值仅为通用契约保留） | `FORBIDDEN` |

## 5. Empty / Not Found 语义汇总（本契约范围）

| 情形 | 响应 |
|---|---|
| B 不存在 | `404 NOT_FOUND` |
| B 已逻辑删除 | `404 NOT_FOUND`（与不存在不区分） |
| B 活跃、该类无活跃关联 | `200`，该类 `items == []`、`total == 0`（**Empty**） |

## 6. 认证边界

- 所有 `/api/*`（除登录）要求认证；未认证访问本端点 → `401 UNAUTHENTICATED`，且不返回任何资源数据、不改变任何数据（ADR-0005）。
- 认证成功即可访问；无需角色 / 权限（V1 无 RBAC）。
- 本端点在 `/api` 前缀下，由既有 F013 中间件自动覆盖，无需白名单成员。

## 7. 明确不提供（非目标）

- 写 / 删除 / 恢复 / 批量端点或参数；`include_deleted` / 回收站 / 查看已删资源。
- **五个子资源端点**（`/api/bare-metals/{id}/network-interfaces` 等）——关系类型集合封闭，聚合为单一端点。
- 图数据库 / 通用关系引擎 / 递归 / 任意深度遍历 / 自动拓扑发现 / 关系配置入口；不存在「任意资源 → 任意资源」端点。
- 任何资源的 `cluster_id` 列或 Cluster 维度过滤参数；推导出的 Cluster 归属字段。
- NIC / IP / VM / Container / Service 的状态字段或状态计数 / 汇总 / 健康检查。
- Cluster 为主语的任何新增关联端点（除 F009 既有 `GET /api/clusters/by-name/{cluster_name}/bare-metals`）。
- 聚合级分页 / 排序 / 关键字 / 导出（本轮为按 `id` 升序的完整快照，无已确认需求）。
- API versioning。

## 8. 与既有契约的关系

| 契约 | 关系 |
|---|---|
| `docs/api/api-conventions.md` | 通用规范来源；**不修改** |
| `f002` / `f004` / `f005` / `f006` / `f007` / `f008` 契约 | 各资源 canonical 读取与元素表示权威；本契约只**引用**其 `*Read` schema 与过滤语义，**不修改**正文 |
| `f009-cluster-resource-view.md` | Cluster 视角先例（404/Empty 与软删复用）；**不修改** |
| `f014-soft-delete.md` | 软删过滤与无恢复语义来源；**不修改** |
| `docs/api/f010-resource-detail.md` | **本文件**：F010 唯一新增端点的权威正文 |

GIT: NONE
