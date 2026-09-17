# Product Handoff — F005 IPAddress 管理

> Status: `READY FOR ARCHITECT`
> Author Role: product-manager
> Date: 2026-09-16
> Feature: F005（E02，P1，`depends_on: [F004]` = DONE）
> Product Source: `requirements.md` §12（R-IP-001~003）、§15、§16、§17、§21、§22、§23、Q-002=B；`domain-model.md` §5.7/§6/§7.2/§8/§9；`domain-model.yaml > resources[IPAddress] / relationships[IPAddress-to-NetworkInterface] / uniqueness_rules[R-IP-001]`；`docs/database/csm-v1-schema-design.md` `ip_addresses` 段 + 关键设计决策 #3；ADR-0001~0005

---

## Feature

IPAddress 管理（F005）— CSM V1 网络资源链的**末端资源**：IP 地址的人工登记、查询、字面值修正、逻辑删除，**IPAddress → NetworkInterface 必选绑定**的真实落地，**Cluster 内 IP 唯一性**的保存前阻止，**`cluster_id` 受控推导与漂移归零**，以及 **F014 父删子拦**在 `NetworkInterface` 上的端到端。

## Problem

F004 让「某台机器上有哪些网卡、各自什么用途」成为可信事实。但运维人员真正关心的是**地址**：「这个 IP 被谁占用了？」今天答案散落在 Excel、配置文件、口头约定中，同一个 Cluster 内重复分配 IP 是 HPC / AI 集群最常见的实际事故来源（§12 首句）。

产品价值：**让「Cluster 内每个 IP 只被登记一次」成为由后端与数据库共同保证、可查询、可维护的事实**，并把「IP 属于哪个 Cluster」变成一个**推导值**而非可被人为写错的字段——这正是 F005 相对一张 Excel 表不可替代之处。

**本 Feature 不新增、不修改任何领域对象、字段、关系、状态或唯一性规则。**

---

## Confirmed Requirements

1. IPAddress 属 Network Resource（§5 Taxonomy），V1 支持**人工登记与查询**（§1、§26）。
2. **唯一性边界是 Cluster，不是全系统**：同一 Cluster 内 IP 必须唯一，**不得存在两个当前有效资源同时占用完全相同 IP**（R-IP-001）；**不同 Cluster 之间允许相同 IP**（R-IP-002；Cluster-A / Cluster-B 均为 `10.0.0.10` 合法）。
3. **V1 不考虑 VRF / 网络命名空间**；唯一性按 `cluster + ip_address` 理解（R-IP-003）。
4. **IPAddress → NetworkInterface 绑定为必选（Mandatory，N:1）**：不存在无主 IP。该必选性已于 **2026-09-15 由用户明确裁定**（§15 + 顶部变更记录；`domain-model.yaml` `binding_state: CONFIRMED / confirmed_by: user`）。**§15 原「必选性须由对应 Feature 确认」一句已不再适用于该关系** —— F005 是履行方，不是裁定方，不得重开。
5. **一个 NetworkInterface 可以挂多个 IP 地址**（`domain-model.md` §5.7）。
6. **登记字段只有 `ip_address`**（`domain-model.md` §5.7；`domain-model.yaml` 仅列 `ip_address`，`required: true`、`is_identifier: true`）。**没有其他已确认字段**。
7. **IPAddress 在 V1 不设状态**（Q-002=B）。
8. **关键冲突必须在保存前阻止**（同 Cluster IP 重复、非法资源关系），不得只依赖 UI 校验（§21）。
9. **`cluster_id` 是受控写入的推导值**：取值必须由领域服务从 `network_interface_id` 沿 `NIC → BareMetal → Cluster` 推导，**不得由调用方直接赋值**；数据库层不保证该链路一致（不引入复合外键、不使用触发器，ADR-0002），**一致性由受控写入路径 + 漂移检测查询（0 行）保证**。
10. **逻辑删除语义**（§17；R-DELETE-001~006）：不得物理删除；已删不出现在常规查询；无 Undelete / Restore；**已删记录不继续占用唯一性**（软删后可重新登记同一字面值）；不级联；单条 `deleted_at` 写入路径由 F014 统一软删领域服务提供（ADR-0004）。
11. **父资源存在活跃子资源时不得删除父资源**（R-DELETE-004）：**NIC 存在活跃 IP 时不得删除该 NIC**；属 §21「保存前必须阻止」。
12. **查询必须区分 Resource Not Found（404）与 Empty Relationship（200 + 空集合）**（R-QUERY-004）。
13. **API 契约与寻址**：写操作一律走 `id`；删除成功 `204`；不存在或已删 `404 NOT_FOUND`；业务冲突 `409 CONFLICT`；`deleted_at` 不对外暴露（ADR-0003 §2）。
14. **认证边界**：`/api/*`（登录除外）要求认证；V1 无角色 / 权限 / RBAC（ADR-0005）。任何已认证用户都可登记 / 修改 / 删除 IP。
15. **F014 交接义务（已确认）**：F004 已交付显式声明点 `NETWORK_INTERFACE_ACTIVE_CHILD_CHECKS`（当前空元组）并真实传入 NIC 删除路径；**F005 必须向该声明点追加「活跃 IPAddress」检查并补端到端测试**（F004 AC-30 / NQ-9）。
16. **F005 是 F010 / F011 的依赖方**；F011 的导入必须执行与页面人工录入**同一套**领域校验，**不得通过导入绕过「IP 冲突」**（R-IMPORT-002）。

---

## Confirmed Domain Rules

| 规则 / 原则 | 内容 | 来源 |
|---|---|---|
| R-IP-001 | 同一 Cluster 内 IP 必须唯一；不得存在两个当前有效资源同时占用完全相同 IP | §12 |
| R-IP-002 | 不同 Cluster 之间允许相同 IP；唯一性边界为 Cluster 而非全系统 | §12 |
| R-IP-003 | 当前不考虑 VRF / 网络命名空间；V1 按 `cluster + ip_address` 理解唯一性 | §12 |
| IP→NIC 绑定 | N:1、**必选**、`binding_state: CONFIRMED`、`confirmed_by: user`（2026-09-15） | §15 + 变更记录；`domain-model.yaml` |
| IP 登记字段 | 仅 `ip_address`（必填、标识字段），示例 `10.0.1.1/16` | `domain-model.md` §5.7 |
| Q-002=B | IPAddress 在 V1 不设状态 | 变更记录；`domain-model.md` §7.2 |
| §21 | 同 Cluster IP 重复 / 非法资源关系必须在保存前阻止 | §21 |
| §22 | 大小写敏感是默认立场；改为不敏感必须显式修改产品规则 | §22 |
| R-DELETE-001~006 | 软删不物理删；无恢复；父有活跃子不得删父；不级联；已删释放唯一性 | §17；ADR-0004 |
| `cluster_id` 受控推导 | 从 NIC→BareMetal→Cluster 推导后写入；调用方不得赋值；靠受控写入 + 漂移检测（0 行）保证 | `csm-v1-schema-design.md` 关键决策 #3；ADR-0002 |
| 唯一性冲突落地 | partial unique index（predicate `deleted_at IS NULL`）为最终权威；应用层预检仅为体验优化 | ADR-0002 §3；ADR-0004 §2/§7 |
| 寻址与状态码 | 写走 `id`；`204` / `404 NOT_FOUND` / `409 CONFLICT` / `400 VALIDATION_ERROR` | ADR-0003 §2 |

---

## Scope

### 本次包含

1. **登记**：`network_interface_id` + `ip_address` 必填；请求 schema **封闭**（不接受 `cluster_id`、不接受多父 / 载体类型选择器、不接受 `status`）。
2. **`cluster_id` 受控推导**：写入时由领域服务沿 `NIC → BareMetal → Cluster` 推导；调用方**无法**赋值。
3. **Cluster 内唯一性保存前阻止**：同 Cluster 内已存在活跃且字面相同的 `ip_address` → 拒绝、不产生写入；跨 Cluster 同 IP 允许。
4. **查询与维护**：列表（分页）+ 详情 + 按 NIC 限定读取（Empty / Not Found 可区分）；**PATCH 允许修正 `ip_address` 字面值**并重新执行唯一性校验；父绑定不可变。
5. **逻辑删除**：委托 F014 唯一软删领域服务；软删释放唯一性；不级联。
6. **F014 父删子拦端到端**：向 `NETWORK_INTERFACE_ACTIVE_CHILD_CHECKS` **追加**「活跃 IPAddress」检查；NIC 有活跃 IP → `409 CONFLICT` + `details[].code == "ACTIVE_CHILDREN_EXIST"`。
7. **漂移检测与回归断言**：交付「存储 `cluster_id` ≠ 推导 `cluster_id`」查询必须返回 **0 行**的回归断言，并交付**反例用例**证明该检测有效。
8. **无状态落地**：无 `status` 字段 / 枚举 / 默认值 / 过滤 / 端点。
9. **无 VRF 落地**：无 `vrf` / 租户 / 命名空间列、字段、参数、过滤或端点。
10. **格式规则「不实现、不承诺」**：不发明任何 `ip_address` 合法性规则；不实现格式校验、不实现归一化。
11. **前端**：列表 / 详情 / 登记 / 修正 / 删除入口；三态与 Empty / Not Found 可区分；错误按 `error.code`；不重复实现业务守卫。
12. **复用既有基座**：统一错误信封与 SQLSTATE→HTTP 映射、单一软删路径、活跃过滤原语、分页与请求级事务边界。

### 本次明确不包含

1. **IP 的状态**（Q-002=B）。
2. **VRF / 网络命名空间**（R-IP-003）。
3. **`ip_address` 的格式 / 归一化规则**（未确认，NQ-1）。不得因「IP 系统通常都校验格式」而引入。
4. **除 `ip_address` 之外的任何字段**：用途 / 备注 / 负责人 / 绑定对象 / 回收状态 / 分配时间（未确认；PROPOSED-F005-2）。
5. **IP 池 / 网段 / 子网 / 分配与回收工作流 / 使用率统计 / 冲突扫描**（无任何已确认需求）。
6. **DHCP / DNS / 自动资产发现 / 外部平台同步 / 自动生成 IP**（§23）。
7. **IP 不绑定 NIC 的形态**：不存在无主 IP、不接受以 BareMetal / VM / Container / Cluster / Service 为父、不提供载体类型选择器。
8. **物理删除 / Undelete / Restore / 回收站 / 软删级联 / 批量删除**。
9. **`by-name` 只读别名**：`ip_address` 仅按 Cluster 唯一、**不是全局唯一**（PROPOSED-F005-1 建议不提供）。
10. **Excel 批量导入**（归 F011）。
11. **Cluster 视角页面 / 关联聚合视图 / 计数统计**（归 F009 / F010）。
12. **其他资源自身的 CRUD 与端点**。
13. **审计 / 历史 / 操作人 / 导出 / 高级筛选 / 排序 / 批量操作**。
14. **BareMetal 跨 Cluster 迁移**（F002 NQ-1，UNCONFIRMED；见 NQ-5）。

### 本次未涉及

- `ip_address` 的格式校验与归一化（NQ-1）；是否允许「语义等价但字面不同」共存；
- IP 的父绑定与字面值的登记后可变性边界（NQ-2 / NQ-3）；
- BareMetal 跨 Cluster 迁移时 IP `cluster_id` 是否随之重推导（NQ-5，属未来 Feature）；
- Cluster 限定的 IP 读取是否形成独立别名端点（NQ-6）；
- 按 Cluster / NIC / IP 前缀的关键字筛选与排序；
- 已删 IP 的查询出口、保留期限、最终清理策略；
- IP 与 Service / Container / VM 的间接关联呈现（归 F010）。

---

## 需求条目

| 编号 | 条目 | 依据 |
|---|---|---|
| F005-R1 | IP 可人工登记，必填 `network_interface_id` + `ip_address`；请求 schema 封闭 | R-IP-001；§15；§21 |
| F005-R2 | `cluster_id` 由领域服务从 NIC→BareMetal→Cluster 推导；调用方不得赋值 | `csm-v1-schema-design.md` #3；ADR-0002 |
| F005-R3 | 同 Cluster 内活跃 IP 字面唯一；跨 Cluster 可重复；保存前阻止 | R-IP-001~003；§21 |
| F005-R4 | 查询（列表 / 详情 / 按 NIC）；可修正 `ip_address`；父绑定不可变 | R-QUERY-004；`domain-model.md` §9 |
| F005-R5 | 逻辑删除委托 F014 唯一路径；释放唯一性；不级联 | R-DELETE-001/002/003/005/006；ADR-0004 |
| F005-R6 | NIC 有活跃 IP 时不得删除 NIC；追加 `NETWORK_INTERFACE_ACTIVE_CHILD_CHECKS` | R-DELETE-004；§21；F004 AC-30 |
| F005-R7 | 漂移检测查询 0 行 + 反例证明 | `csm-v1-schema-design.md` #3 |
| F005-R8 | 不设状态 | Q-002=B |
| F005-R9 | 不引入 VRF / 网络命名空间 | R-IP-003 |
| F005-R10 | 不实现、不承诺 `ip_address` 格式规则 | 未定义约束；AGENTS.md §2.2 |

---

## Acceptance Criteria

### 登记与父绑定

- **AC-01（登记成功，字段集合封闭）**：`POST /api/ip-addresses` 携带活跃 NIC 标识 + `ip_address` → `201`；响应字段集合**恰为** `{id, network_interface_id, ip_address, created_at, updated_at}`（`cluster_id` 是否作为**只读**派生值暴露由 Architecture 裁定；若暴露必须只读且不可由请求设置）；不含 `deleted_at` / `status` / VRF / 用途 / 负责人等字段。
- **AC-02（`ip_address` 必填）**：缺失或非字符串 → `400 VALIDATION_ERROR` + `details[].field == "ip_address"`，不产生记录。
- **AC-03（父 NIC 必填）**：缺失或非整数父标识 → `400 VALIDATION_ERROR` + `details[].field`，不产生记录。
- **AC-04（父必须有效且活跃）**：引用不存在**或已逻辑删除**的 NIC → 写入被阻止、不产生记录、**不得 5xx**（响应码见 NQ-7）。
- **AC-05（绑定恰好一个 NIC，schema 封闭）**：不接受多父、不接受以 BareMetal / VM / Container / Cluster / Service 为父、不接受载体类型选择器；DB 父列 `NOT NULL` + FK `ON DELETE RESTRICT`。
- **AC-06（一个 NIC 多个 IP）**：同一 NIC 下连续登记 2 个不同 `ip_address` → 均 `201`。
- **AC-07（`cluster_id` 不被接受）**：请求体携带 `cluster_id`（或任何 VRF / Cluster 选择字段）→ `400 VALIDATION_ERROR`，不产生记录；**不存在**任何产品路径允许调用方指定 IP 的 Cluster 归属。

### 唯一性

- **AC-08（同 Cluster 内唯一，保存前阻止）**：Cluster A 内已存在活跃 `10.0.0.10`，再登记 `10.0.0.10`（**无论挂在 A 下哪台 BareMetal 的哪张 NIC**）→ 写入被阻止、不产生第二条活跃记录、不 5xx；`409 CONFLICT` 且 `details[]` 指向 `ip_address`。
- **AC-09（跨 Cluster 可重复）**：Cluster A 与 B 各自登记 `10.0.0.10` → 均 `201`，两条不同记录（R-IP-002）。
- **AC-10（字面精确，不折叠、不 trim、不归一化）**：同 Cluster 内两条字面**完全相同**的字符串视为冲突（AC-08）；字面**不同**的字符串可共存，包括 IPv6 十六进制大小写不同的写法（如 `2001:DB8::1` 与 `2001:db8::1`）→ 均 `201`；不引入 `lower()` 折叠、不引入 collation 变更（§22；`case_sensitive: true`；schema design #1/#2）。
- **AC-11（唯一性由数据库最终保证）**：绕过应用层预检直接向数据层写入同 Cluster 重复 IP 被数据库拒绝（`23505` → 统一映射为 `409 CONFLICT`，**永不 500**）；`ux_ip_addresses_cluster_ip_active` 的 predicate 为 `deleted_at IS NULL` 且与常规查询过滤一致。
- **AC-12（格式规则不实现，不得被解读为已确认）**：不存在的 IP 字面值（`not-an-ip`、空串、含首尾空白、超长）**不被本 Feature 拒绝**，按字面值存取与往返；本 AC 记录的是「未确认即不实现」的后果，**不得**被解读为「任意字符串都是合法 IP」是已确认规则（F005-R10；NQ-1）。

### 无状态 / 无 VRF

- **AC-13（无状态）**：请求 / 响应 / 数据表 / 端点 / 查询参数中不存在 `status` 字段、枚举、默认值或过滤。
- **AC-14（无 VRF / 网络命名空间）**：不存在 `vrf` / `vrf_id` / `tenant` / `namespace` 列、字段、查询参数、过滤或端点；同 Cluster 内不存在任何可绕过唯一性的第二维度。
- **AC-15（无未确认字段）**：不存在用途 / 备注 / 负责人 / 分配对象 / 回收状态等字段或端点；不存在 DHCP / DNS / 自动发现 / 外部平台 id / 凭据字段或端点（§23）。

### 查询

- **AC-16（列表、分页、Empty）**：`GET /api/ip-addresses` → `200` + `{items,total,page,page_size}`；无活跃 IP 时 `items == []`、`total == 0`，不得 `404`。
- **AC-17（详情 Not Found）**：不存在或已逻辑删除的 `id` → `404 NOT_FOUND`（不区分）；重复删除已删记录 → `404`。
- **AC-18（按 NIC 限定读取，Empty 与 Not Found 可区分）**：NIC 不存在或已删 → `404 NOT_FOUND`；NIC 存在但无活跃 IP → `200` + `items == []`；只返回该 NIC 的活跃 IP（R-QUERY-004；路由形态见 NQ-6）。
- **AC-19（列表 / 详情排除已删）**：绕过应用层预置 `deleted_at` 非空的行 → 不出现在 `items` / `total`；按 `id` → `404`。

### 维护

- **AC-20（`ip_address` 字面值可修正）**：`PATCH` 携带新的 `ip_address` → `200` 返回新值；再次读取得同一值；`network_interface_id` / `created_at` / `cluster_id`（若暴露）不变。
- **AC-21（修正后重校验唯一性）**：修正为目标 Cluster 内已存在的活跃字面值 → 被阻止（`409`，无部分写入）；修正为另一 Cluster 已有但目标 Cluster 未占用的同一字面值 → 成功。
- **AC-22（更新 schema 封闭）**：`PATCH` 含未识别字段（含 `id` / `deleted_at` / `network_interface_id` / `cluster_id` / `created_at`）→ `400`；空 body → `400`；父绑定**不可变**。

### 删除与生命周期

- **AC-23（IP 逻辑删除）**：`DELETE`（活跃行）→ `204` 无响应体；该行**仍物理存在**且 `deleted_at` 非空；不出现在列表 / 详情。
- **AC-24（软删释放唯一性）**：软删 Cluster A 内的 `10.0.0.10` 后，可在 Cluster A 内重新登记 `10.0.0.10` → `201`；旧已删行保留且 `deleted_at` 未被改写。
- **AC-25（删除不级联）**：删除 IP 后，其父 NIC 的 `deleted_at` / `updated_at` / `name` / `technology_type` / `purpose` / `bare_metal_id` **逐字段不变**；其宿主 BareMetal 与 Cluster 的各字段同样不变；无任何其他行被修改或物理删除。
- **AC-26（无恢复 / 无批量）**：不存在 restore / undelete / purge / 批量删除 / `include_deleted` / 回收站入口或参数。

### F014 父删子拦真实端到端

- **AC-27（NIC 有活跃 IP → 拒绝删除 NIC）**：`DELETE /api/network-interfaces/{id}` → `409 CONFLICT` + `details[].code == "ACTIVE_CHILDREN_EXIST"`；该 NIC 的 `deleted_at` **仍为 NULL**（无部分写入）。
- **AC-28（软删 IP 后 NIC 可删）**：先软删该 NIC 全部活跃 IP（及其它活跃子资源）再 `DELETE` → `204`；可证明 IP 是阻断来源。
- **AC-29（链条延伸的守卫）**：NIC 有活跃 IP 时，其宿主 BareMetal 亦不可删（经既有「活跃 NIC」检查间接成立）→ `DELETE /api/bare-metals/{id}` → `409`；确认删除守卫链条 `Cluster → BareMetal → NIC → IP` 在 F005 后仍闭合。
- **AC-30（`NETWORK_INTERFACE_ACTIVE_CHILD_CHECKS` 被追加且被真实消费）**：该声明点由「显式空元组」演进为**非空**且包含「活跃 IPAddress」检查；NIC 删除路径真实消费它（可失败 guard + AC-27 的行为断言）。
- **AC-31（并发孤立记录不变式 = 0 行）**：并发「创建 IP」与「删除其父 NIC」结束后，`SELECT count(*) FROM ip_addresses ip JOIN network_interfaces nic ON nic.id = ip.network_interface_id WHERE ip.deleted_at IS NULL AND nic.deleted_at IS NOT NULL` 必须为 **0**。
- **AC-32（创建侧对父 NIC 行取共享锁）**：创建 IP 时必须在同一事务内对父 NIC 行取共享锁并确认活跃（且其上游链活跃）；未命中 → 拒绝创建。锁序须与 F004 / F014 既有协议一致，不得引入新的死锁序。

### `cluster_id` 受控推导与漂移归零

- **AC-33（推导正确）**：在 Cluster A 的 BareMetal 下建立 NIC，通过产品路径创建 IP → 断言该行 `cluster_id == A.id`（由 `NIC → BareMetal` 推导，**不是**请求提供的值）。
- **AC-34（漂移检测查询 = 0 行，回归断言）**：

  ```sql
  SELECT ip.id, ip.cluster_id AS stored_cluster, bm.cluster_id AS derived_cluster
  FROM ip_addresses ip
  JOIN network_interfaces nic ON nic.id = ip.network_interface_id
  JOIN bare_metals        bm  ON bm.id  = nic.bare_metal_id
  WHERE ip.cluster_id <> bm.cluster_id;   -- 期望 0 行
  ```

- **AC-35（反例证明检测有效）**：测试**绕过领域服务**直接向数据层插入一条 `cluster_id` 与推导结果不一致的 IP（数据库**不会**拒绝，ADR-0002 的已知取舍）→ 该行**必须被 AC-34 的漂移查询发现**（返回 1 行），证明一致性测试有效而非约束有效。
- **AC-36（漂移即唯一性静默漏洞，须被证明）**：Cluster A 已有 `10.0.0.10`；构造一条真实属于 A、但存储 `cluster_id = B` 的 IP 行，字面值为 `10.0.0.10` → 唯一索引**不会**阻止（索引看到 `(B, 10.0.0.10)`）→ 漂移查询必须发现它。证明 F005-R7 是 R-IP-001 的必需保障。
- **AC-37（`cluster_id` 写入路径唯一）**：系统内不存在第二条写入 `ip_addresses.cluster_id` 的产品路径；所有写入经领域服务推导（可由静态可失败 guard 断言）。

### 边界与前端

- **AC-38（不越界到 F009 / F010 / F011）**：不注册 Cluster 视角 / 关联聚合 / 计数统计端点；不实现 Excel 导入；`ip_address` 的领域校验随后由 F011 复用时必须与本 Feature 完全一致。
- **AC-39（无格式 / 无自动发现的结构性 guard）**：以可失败 guard 固定「不存在 `ip_address` 格式校验 / 归一化」与「不存在 DHCP / DNS / 自动发现 / 外部同步字段或端点」。
- **AC-40（认证边界）**：未认证访问任意 `/api/ip-addresses*` → `401 UNAUTHENTICATED` 且不返回 / 不修改任何数据；已认证用户即可登记 / 修改 / 删除（无需角色）。
- **AC-41（前端三态与 Empty / Not Found 可区分）**：三态互不相同；Empty 与 Not Found 可区分；错误按 `error.code` 分支（不解析 `message`）；`409` / `404` / `401` 分别处理；前端**不得**自行实现「同 Cluster IP 唯一」等业务守卫。
- **AC-42（不得预留未确认能力）**：schema / 契约 / 前端**不得**为 VRF、IP 状态、IP 池、多态父载体、`cluster_id` 可写、格式归一化预留字段、参数或分支。

---

## 与既有 Feature 的边界

| Feature | 边界与依赖方向 |
|---|---|
| F001 Cluster | IP 的 Cluster 归属是**推导值**，F005 不读写 Cluster 端点；推导只在数据库层读 `bare_metals.cluster_id`。Cluster 的删除守卫经 BareMetal→NIC 间接生效（AC-29）。 |
| F002 BareMetal | F005 消费「BareMetal 存在且活跃」这一事实（经 NIC 链）；`bare_metals.cluster_id` 在当前产品路径上不可变，因此不触发重推导（NQ-5）。 |
| F004 NetworkInterface | F005 的**直接父**。F005 履行 F004 留出的两项义务：向 `NETWORK_INTERFACE_ACTIVE_CHILD_CHECKS` 追加活跃 IPAddress 检查 + 补端到端。F005 复用 F004 交付的 `GET /api/network-interfaces?bare_metal_id=` 做上游链溯源，**不重写**过滤。 |
| F009 Cluster 视角查询 | 归 F009；F005 不提供 Cluster 视角或统计。 |
| F010 关联查询 | 聚合呈现归 F010；F005 交付「按 NIC 限定读取」+ 可复用的领域校验，F010 必须复用。 |
| F011 Excel 导入 | 归 F011；导入必须复用 F005 同一套领域校验，不得绕过 IP 冲突（R-IMPORT-002）。 |
| F014 逻辑删除 | 机制与唯一软删路径归 F014；F005 是**消费方**与**义务方**。F014 明确声明 `ip_address.cluster_id` 一致性治理无法在 F014 交付，须在 F005 落地——F005 履行之。 |
| F006 / F007 / F008 | 无直接关系。IP 不绑定 VM / Container / Service。 |
| F012 / F013 | 基座与认证；F005 复用，不重做。 |

---

## Assumptions

1. F004 / F002 / F001 / F012 / F013 / F014 已交付；`ip_addresses` 表尚不存在，**无历史数据、无数据迁移**。
2. F005 **新增** `ip_addresses` 表与增量 migration（实际版本号由 Database 裁定），**不改既有基线 migration**；`database: true`。
3. **PATCH 可变字段集合 = `{ip_address}`**：依据 `domain-model.md` §9「资源记录仅支持更新」，登记事实的修正应有产品路径；**父绑定 `network_interface_id` 不可变**，与 F004 / F002 先例一致。若确认父绑定可变，则必须同事务重推导 `cluster_id` 并在目标 Cluster 内重校验唯一性（NQ-2）。
4. 父引用以 NIC `id` 表达；分页沿用 `page_size` 默认 50 / 上限 200。
5. 「同 Cluster 内某 IP 前缀 CIDR 不同但主机位相同」是否冲突，取决于 NQ-1；未确认前按**字面值**比较（AC-10 / AC-12）。
6. 前端沿用无 `vue-router` 现状。
7. 契约落点为**新增** `docs/api/f005-ip-address.md`。

---

## Proposed Rules

- **PROPOSED-F005-1（需用户裁定）**：**不提供 IP 的 `by-name` 别名**（`ip_address` 非全局唯一；ADR-0003 §2 只为全局唯一名称授予别名）。
- **PROPOSED-F005-2（需用户裁定）**：是否在 IP 上记录用途 / 备注 / 负责人 / 分配对象。产品文档均未列；F005 **不实现**。
- **PROPOSED-F005-3（需用户裁定）**：`ip_address` 的最小字符约束（空串 / 首尾空白 / 长度上限 / 非 IP 字面值）。当前为**未定义**，F005 不得实现。
- **PROPOSED-F005-4（需用户裁定）**：`ip_address` 是否应归一化后再比较（`10.0.1.1` vs `10.0.1.1/16`、IPv6 大小写）。当前 V1 为字面精确比较；若确认归一化，属**新增产品规则**且需数据迁移策略。
- **PROPOSED-F005-5（需用户裁定，属未来 Feature）**：若未来允许 BareMetal 跨 Cluster 迁移，是否连带重推导该机器全部 NIC 的全部 IP 的 `cluster_id` 并在目标 Cluster 重校验唯一性。F005 **不实现、不预留**。

---

## Open Questions

### Blocking

**None。**

| 候选问题 | 为何不阻塞 |
|---|---|
| NQ-1 格式 / 归一化 | 未确认时默认行为**单值**——「不实现、不承诺」字面校验与归一化（F005-R10 / AC-12）；唯一性语义由 `case_sensitive: true` + ADR-0002 的 `TEXT` 字面比较固定（AC-10）。若未来确认归一化，属新增规则 + 迁移，加性、可逆。 |
| NQ-2 IP 父绑定可变性 | 不属任何已确认要求；F005 边界由已确认的 `IP→NIC` N:1 Mandatory 唯一确定。未确认时默认不提供（AC-22），行为单值。 |
| NQ-3 `ip_address` 登记后可变性 | 默认提供「修正字面值」并重校验唯一性（AC-20/21）；若确认不可变，只是**移除**一条能力。 |
| NQ-4 `cluster_id` 是否在响应暴露 | 属**契约表示细节**（Architecture 裁定）。无论暴露与否，AC-07 与 AC-33~37 均可判定。 |
| NQ-5 BareMetal 跨 Cluster 迁移重推导 | F002 已把该能力列为 UNCONFIRMED 且**不在 PATCH 内**；F004 也已把 NIC 的 `bare_metal_id` 设为不可变。因此 V1 **不存在**改属产品路径 → 触发条件不可达，行为单值。 |
| NQ-6 按 NIC 读取路由形态 | F005 承诺提供该能力并满足 R-QUERY-004（AC-18）；形态与归属由 Architecture 裁定。 |
| NQ-7 精确响应码 | 已确认要求是「写入必须被阻止 + 非 5xx + 保存前阻止」；建议沿用已裁定先例（父不存在 / 已删 → `404`；唯一性 → `409` + `details[].code = "DUPLICATE"`）。AC 表述已按「被阻止 + 无写入 + 非 5xx」固定，不依赖该裁定。 |

### Non-blocking

- **NQ-1（格式与归一化）— 最高关注**：若确认格式校验，会在**保存路径**引入拒绝；若确认归一化，会改变唯一性语义并需数据迁移。建议 V1 保持「字面精确比较 + 不校验格式」，把格式校验作为**新增产品需求**单独确认。
- **NQ-2（父绑定可变性）**：默认不可变（假设 3 / AC-22）。
- **NQ-3（`ip_address` 可变性）**：默认可变并重校验唯一性。
- **NQ-4（响应是否暴露 `cluster_id`）**：由 Architecture 裁定；请求侧均不接受。
- **NQ-5（BareMetal 迁移重推导）**：属未来 Feature。F005 的记录：**若该能力落地，必须在同一事务内重推导受影响 IP 的 `cluster_id` 并对目标 Cluster 重校验唯一性；否则漂移查询将 > 0 行**。F005 不实现、不预留。
- **NQ-6（按 NIC 读取路由）**：建议 Architecture 裁定为 `GET /api/ip-addresses?network_interface_id=`（与 F002/F004 对称，不新增端点），F010 必须复用。
- **NQ-7（响应码取值）**：建议父不存在 / 已删 → `404`；唯一性 → `409` + `DUPLICATE`；与 F002/F004 一致。
- **NQ-8（`by-name` 别名）**：建议不提供（PROPOSED-F005-1）。
- **NQ-9（F011 复用校验）**：F011 的 IP 行导入必须复用同一套领域校验，不得绕过 IP 冲突。
- **NQ-10（文档与计划元数据漂移同步）**：见「变更影响」。

---

## 变更影响

**对既有已确认产品规则：None。**

结构性影响（需 Architect / 协调器一并落盘）：

1. **`NETWORK_INTERFACE_ACTIVE_CHILD_CHECKS` 由「显式空元组」演进为非空**，追加「活跃 IPAddress」检查。这是履行 F004 AC-30 / NQ-9 的**已确认义务**；既有的 `BARE_METAL_ACTIVE_CHILD_CHECKS`（含活跃 VM + 活跃 NIC）与 `CLUSTER_ACTIVE_CHILD_CHECKS` 必须保留。
2. **新增 `ip_addresses` 表** → 表集合 guard、无 `ON DELETE CASCADE` guard、唯一软删写入路径 guard 应**增表演进**而非删除。
3. **文档漂移（须同步，不改规则）**：
   - `csm-v1-schema-design.md` 关键设计决策 #3 把 `cluster_id` 受控写入路径的归属写为「必须由 F014 领域服务强制」，而 F014 已裁定该表不存在、归属**迁移至 F005**。正文与实际归属需对齐。
   - `domain-model.md` §8 / `domain-model.yaml > resources[IPAddress]` 建议显式补「唯一性边界为 Cluster、绑定 NIC 必选」的交叉引用。
   - `project-plan.yaml > F005` 的 `requirements` 建议补 `§15` / `§16` / `§17` / `§21` / `§22`；`open_questions` 承接 NQ-1 ~ NQ-9；`contract` 按 Architecture 判定（预计新增 `docs/api/f005-ip-address.md`）。
4. **删除守卫链条延伸**：`Cluster → BareMetal → NIC → IP` 四层在 F005 后闭合（AC-29）。

---

## Architecture Handoff

1. **`ip_addresses` Schema 与增量 migration**：`network_interface_id BIGINT NOT NULL` + FK RESTRICT/RESTRICT；`cluster_id BIGINT NOT NULL` + FK RESTRICT/RESTRICT（反规范化，承载唯一性边界）；`ip_address TEXT NOT NULL`（**不声明 collation、不加 `COLLATE`、不加 `lower()` 表达式索引**）；`deleted_at`；**无 `status` 列**；**无 VRF / 命名空间列**；**无 `ip_address` 格式 `CHECK`**；`ux_ip_addresses_cluster_ip_active (cluster_id, ip_address) WHERE deleted_at IS NULL`；`ix_ip_addresses_cluster_id` + `ix_ip_addresses_network_interface_id`。同步 `csm-v1-schema-design.md` 实际 migration 版本号。
2. **端点集合与契约落点**：确认端点集合与**封闭字段集合**（AC-01）；新建 `docs/api/f005-ip-address.md`；明确 PATCH 可变字段与不可变字段；明确 `cluster_id` 是否作为只读派生值出现在响应中（NQ-4），且请求侧**永不接受**（AC-07）。
3. **`cluster_id` 受控推导落点**：定义「唯一允许写入 `ip_addresses.cluster_id` 的领域服务」——从 `network_interface_id` 沿 NIC→BareMetal→Cluster 推导；创建 / 更新路径必须经该服务；以**可失败 guard** 阻止第二条写入路径（AC-37）。**不得**引入触发器、复合外键或把业务规则藏进 Schema（ADR-0002）。
4. **漂移检测与回归测试**：把 AC-34 的漂移查询固化为持续回归断言（0 行）；交付 AC-35 反例用例与 AC-36「漂移破坏唯一性」证明用例。这是 F014 移交的已确认义务，不得省略或降级。
5. **F014 义务落点（父删子拦）**：向 `NETWORK_INTERFACE_ACTIVE_CHILD_CHECKS` 追加活跃 IPAddress 检查；交付 AC-27/28/31/32 端到端与并发测试；处理 `docs/reviews/f014-soft-delete.md` NOTE-01 的「活跃子检查非空断言」演进；锁序须与 F004 / F014 一致。
6. **创建路径的父链存在性 / 活跃性与并发协议**：对父 NIC 行取 `FOR SHARE` 并同事务确认活跃；是否需要一并锁 BareMetal / Cluster 行以稳定推导由 Architect 裁定；FK 违规与「父不存在 / 已删」的响应码（NQ-7）；并发孤立记录不变式（AC-31/32）。
7. **唯一性冲突落地与最终权威**：应用层预检仅为体验优化；`ux_ip_addresses_cluster_ip_active` 是最终权威（§21；ADR-0002 §3）；`23505` 经既有通用映射 → `409 CONFLICT` + `details[].code = "DUPLICATE"`，**永不 500**。
8. **「不实现」的结构性保障**：以可失败 guard 固定——不存在 `ip_address` 格式校验 / trim / 归一化 / 空串拒绝；不存在 `status` 列 / 端点 / 过滤；不存在 VRF / 命名空间 / IP 池 / DHCP / DNS / 自动发现字段或端点；不存在为未确认能力预留的参数或分支（AC-13/14/15/38/39/42）。
9. **按 NIC 限定读取的路由形态与归属**（NQ-6）：决定 `?network_interface_id=` 与 / 或嵌套路径，明确 Empty / Not Found 判定位置，保证 R-QUERY-004 且 F010 可复用。
10. **删除端点注册与依赖方向**：委托 F014 统一软删服务；不引入第二条软删路径、restore 或批量能力；读取路径复用 `app/db/active.py`。
11. **前端接线**：列表 / 详情 / 登记 / 修正 / 删除入口；三态与 Empty / Not Found；错误按 `error.code`；不重复实现唯一性与父删子拦守卫。
12. **交付层判定与既有 guard 演进**：确认 `database: true` 与 backend / frontend 层；`project-plan.yaml > F005` 的 `layers` / `contract` / `implementation` / `requirements` / `open_questions` 落盘；表集合 guard 随新表演进。
13. **禁止预留**：schema / 契约 / 前端不得为 VRF、IP 状态、IP 池、多态父载体、`cluster_id` 可写、格式归一化、Excel 导入预留字段、参数或分支（AC-42）。

---

## Handoff Status

`READY FOR ARCHITECT`

无 Blocking 问题。题面列出的 6 个要点均已给出明确产品结论：

1. 登记 / 查询 / 维护 / 逻辑删除范围 → F005-R1 ~ R10 + AC-01~26；字段集合仅 `ip_address`，格式规则**不发明**（NQ-1 / AC-12）。
2. 唯一性边界 → Cluster 内唯一、跨 Cluster 可重复、字面精确比较（AC-08/09/10/11）；大小写与归一化语义取证自 `domain-model.yaml` + ADR-0002。
3. IP→NIC 绑定 → **必选（2026-09-15 用户裁定）**，非本次待裁；Cluster 归属**由宿主推导**而非调用方提供（F005-R2 / AC-07 / AC-33）。未发现产品文档冲突。
4. Cluster 归属漂移 → 归属是推导值；V1 中两级父绑定均不可变，故无产品路径触发改属；漂移必须由 F005 的受控写入 + 0 行检测保证（AC-33~37）。
5. NIC 有活跃 IP 不得删 NIC → AC-27/28/30；IP 软删不级联 → AC-25。
6. F010 / F011 / F009 边界 → 见边界表；IP 无状态、无 VRF（AC-13/14）。

NQ-1 ~ NQ-9 经逐条对照阻塞判定标准，全部判定为 **Non-blocking**：未确认项的默认行为均为单值（不实现 / 不承诺 / 不预留），全部 AC 不依赖其答案。

GIT: NONE
