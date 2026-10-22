# F027 服务端访问范围强制执行 — Architecture

- 状态：READY FOR DESIGN（未放行编码）
- 需求：requirements revision 11 §23.2/§31 T85–T89/T91/T93–T95/T97–T98；F027 product
- 依据：F026 `AccessScope` / `docs/api/F026.md`；F013/F018、F014/F023、F019/F022、F025 契约
- layers：database=false、backend=true、frontend=false；api_required=true（范围附录 + 既有 Contract errata）

## 1. 统一接入

F027 只消费 F026 的 `AccessScope` / `get_access_scope`，不新增第二套解析、不缓存。

- 每个受保护路由新增 `scope: AccessScope = Depends(get_access_scope)`，作为 keyword 参数传入 Service。
- Service 的读/写函数接收 `scope`，在 SQL 谓词或对象取回后执行范围校验。
- `AccessScope.unrestricted=True` 时谓词为 `true()`，零授权时为 `false()`；禁止隐式全量回退。
- 列表 `items` 与 `total` 使用同一 filters + 同一范围谓词；分页/排序/过滤语义不变。
- 范围校验先于唯一性/重叠/引用检查，避免通过 409 泄露未授权对象。

## 2. 归属谓词

| 对象 | 范围谓词 |
| --- | --- |
| Cluster | `scope.cluster_predicate(Cluster.id)` |
| Resource | `scope.cluster_predicate(Resource.cluster_id)` |
| Network | `scope.cluster_predicate(Network.cluster_id)` |
| IPAddress | `scope.cluster_predicate(IPAddress.cluster_id)`（未绑定 IP 仍生效） |
| Interface | `EXISTS (SELECT 1 FROM resources r WHERE r.id=Interface.resource_id AND scope(r.cluster_id))` |
| IPPool | `EXISTS (SELECT 1 FROM networks n WHERE n.id=IPPool.network_id AND scope(n.cluster_id))` |
| Service | `EXISTS (SELECT 1 FROM resources r WHERE r.id=Service.resource_id AND scope(r.cluster_id))` |
| ServiceEndpoint | `EXISTS (SELECT 1 FROM services s JOIN resources r ON r.id=s.resource_id WHERE s.id=ServiceEndpoint.service_id AND scope(r.cluster_id))` |

关系加载的父级同样受全局软删过滤；范围谓词显式写 `deleted_at IS NULL` 仅用于授权解析（F026），业务查询保持既有软删语义。

## 3. 读路径

- 各域 `list_*`：在既有 filters 上追加范围谓词；`total` 同一谓词；`q`/`cluster_id` 等过滤值未授权时自然返回空 200。
- 各域 `get_*`：增加 `scope` 并在 SELECT 中追加范围谓词；返回 None → 路由既有 404。Activity 先按范围取对象，再列 Activity。
- Resource Detail / Cluster Detail 聚合：主对象按范围取回；子查询（hardware/VM/interface/IP/service）均通过主对象已可见保证，或显式 join 范围谓词。
- 已删除对象：非 ADMIN 的 `deleted=include|only` 仍先 403；ADMIN 不受范围限制。
- 搜索：`_resource_candidates` / `_cluster_candidates` / `_ip_candidates` / `_service_candidates` 各自追加范围谓词；关联行从已过滤结果行加载；`total`/`related_total` 基于过滤后集合。
- Dashboard：`_counts` 的每个 count 与 `_page_networks` 的 items/total 追加范围谓词；容量函数只对已过滤 Network 调用。

## 4. 写路径

- 创建：解析请求体 Cluster / 父对象（Network/Resource/Service/IP）时使用范围校验；未授权/不可选 → 422（沿用既有字段错误，消息不区分不存在/已软删/未授权）。
- 修改/删除/释放/恢复/分配/绑定/解绑/转移：先用带范围谓词的 SELECT 取对象；不存在或不可见 → 404；不产生任何写、Audit、Activity。
- 跨 Cluster 变更：同时校验当前对象归属与目标 Cluster；当前对象不可见 → 404；目标 Cluster 未授权 → 422；既有同 Cluster 完整性不变。
- 导入：在行校验中先校验行 Cluster / Network / Host / 父对象范围，再执行既有字段与完整性校验；范围错误作为行错误聚合；整批失败、无残留。F025 `--push` 走同一端点自动继承。
- 接口侧逐条绑定：每条请求按 IP / Interface 范围校验；未授权条目 404，其他条目独立。

## 5. 错误语义

- 401 → 403（角色/CSRF/VIEW_DELETED）→ 422（请求体/参数）→ 404（路径对象不存在或不可见）→ 409。
- 列表/搜索/Dashboard 零授权：200 空/0；不报错。
- 详情/写对象未授权：404，不含对象字段。
- body Cluster/父对象未授权或不可选：422，字段消息不泄露存在性。
- 不新增 error code/reason；不泄露未授权 Cluster 的 code/name/id/状态/规模。

## 6. 文件影响

- `app/core/access_scope.py`：可加 `visible_cluster_ids` / 谓词辅助（不改变 F026 语义）。
- 各域 `app/services/*.py`：list/get/activity/create/update/delete/restore/分配/绑定函数增加 `scope` 并应用谓词。
- 各域 `app/api/v1/*.py`：注入 `get_access_scope` 并传参；不改变路径/响应结构。
- `app/services/search.py`、`dashboard.py`、`resource_import.py`、`resource_interface_ip_import.py`：范围过滤/行级归因。
- `app/services/ip_capacity.py` 不改变公式；只由已过滤 Network 调用。
- 无 Migration、无新表/列/索引。

## 7. Contract / Test

- `docs/api/F027.md`：范围附录（归属谓词、404/422、列表/total、搜索、Dashboard、导入、Activity、错误顺序、不泄露），并引用/errata F002/F003/F004/F007–F025。
- Test Design：真实 PG 多角色/多 Cluster/多授权/零授权/API Key；8 类对象列表/详情/写、聚合、Activity、搜索、Dashboard、导入、错误顺序、total 一致、无残留、撤销即时、INACTIVE/软删/恢复、既有回归；F028 承接 Compose 端到端。
- 范围校验必须在既有完整性检查之前；测试需覆盖未授权对象不通过 409/唯一性错误泄露。

**Status：READY FOR DESIGN**
