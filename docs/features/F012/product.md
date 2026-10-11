# F012 Service Endpoint 监听端点 — PRODUCT 阶段报告

- **Feature**：F012 Service Endpoint 监听端点（FEATURE，P1，M5 服务与端点，deps [F010, F011]）
- **阶段**：PRODUCT；**结论**：`READY FOR ARCHITECT`
- **依据**：requirements-v3.md revision 3（§3、§4.1、§5、§13/§13.3、§14、§15、§16、§18、§19、§21、§22、§23、§25、§26、§27、§28、§31 T22/T23/T24/T25/T26/T37/T40/T41、§32、§33、§35.2 Q06/Q10-A、§35.3 D01/D02）；plan_revision 4 F012；`docs/features/F010/product.md`（F010 DONE）、`docs/api/F010.md` v1、`docs/database/f010-ip-address.md` v1（DB-D111–D127，`register_ip_address_reference_checker` 挂钩）；`docs/features/F011/product.md`（F011 DONE）、`docs/api/F011.md` v1、`docs/database/f011-service.md` v1（DB-D128–D141，`register_service_reference_checker` 扩展点）；`docs/architecture/d01-conventions.md` v10；`docs/api/F009.md` v1（格式参照）。

## 1. 目标与范围

### 1.1 目标
在 F011 Service 与 F010 IPAddress 基础上，提供 ServiceEndpoint 监听端点实体：表达某个 Service 在某 IP 上以某协议/端口暴露的监听入口（如 Web 的 TCP/80、TCP/443；Grafana 的 10.10.1.20:3000），作为 `Resource → Service → ServiceEndpoint` 关系与「机器运行哪些 Service/监听哪些端口」事实数据的权威来源，并落地 §13.3/§16/§21 对 IP 解绑、转移、释放与 Service 删除的引用保护。

### 1.2 本次范围（CONFIRMED，除标注 PROPOSED 外）
- 字段（§16）：service、ip_address、protocol、port、description；标准 id/version/created_at/updated_at/deleted_at。
- 归属与关系（§16）：Endpoint 属一个 Service（1:N，一个 Service 可有多个 Endpoint）；引用一个 IPAddress；经 Service 间接归属 Resource/Cluster，经 IPAddress→Interface→Resource 关联到同一 Resource。
- IP 归属约束（§16）：ip_address 必填、未删除，且必须绑定在 Service 所属 Resource 的 Interface 上（interface 非空，且该 Interface 的 Resource == Service 的 Resource）；不支持跨资源共享 VIP。
- 协议与端口（§16）：protocol 仅 TCP/UDP；port 为 1–65535 整数。
- 监听唯一（§16）：同一有效（未删除）IP 上 (protocol, port) 不重复，包括同一 Service 的重复 Endpoint；不同 IP 对象（含不同 Cluster 的同值地址）各自独立。
- 生命周期（§21）：软删；默认查询隐藏；ADMIN 恢复/查看已删；无子对象引用 Endpoint，不级联。
- 引用保护（§13.3/§16/§21）：有未删除 Endpoint 引用时禁止 IPAddress 解绑/转移/释放（经 F010 的 `register_ip_address_reference_checker` 挂钩）；有未删除 Endpoint 引用时禁止 Service 删除（经 F011 的 `register_service_reference_checker` 扩展点）；两者均返回引用列表、不隐式级联。F012 注册这两个真实 provider。
- 权限/审计（§22/§23）：EDITOR 新增/修改；ADMIN 删除/恢复/查看已删；VIEWER 只读；CREATE/UPDATE/DELETE/RESTORE 写 Audit；Activity 全角色。
- 登记 Endpoint 不代表监控、进程探测或端口实开校验（与 §15 同理）。

### 1.3 使用者
EDITOR 登记与维护 Service 的监听入口；ADMIN 删除、恢复、查看已删；VIEWER 查询。运维人员据 Endpoint 回答「某 Service 监听哪些地址/端口」「某 IP 上是哪个 Service 的哪个端口」，并支撑 §18 Resource Detail Services 区域与 §19 Cluster Detail（F013 展示）。

## 2. 字段契约（ServiceEndpoint，补齐 D01）

| 字段 | 类型 | 可空 | 创建必填 | 单位 | 合法值/语义 |
| --- | --- | --- | --- | --- | --- |
| service | UUID | 否 | 是 | — | 引用存在、未软删 Service（§16）；创建后可否修改见 I-2（PROPOSED 不可改） |
| ip_address | UUID | 否 | 是 | — | 引用存在、未软删 IPAddress（§16）；且该 IP 必须已绑定 Interface（interface 非空）并属于 service 所属 Resource（接口 Resource == Service.Resource，Cluster 随之一致）；不满足→422 field="ip_address"（§13/§14/§16）；创建后可否修改见 I-2（PROPOSED 不可改） |
| protocol | enum | 否 | 是 | — | TCP\|UDP（§16）；显式 null/非法→422；大小写口径见 I-4/D01（PROPOSED 仅接受大写规范值，存储大写） |
| port | integer | 否 | 是 | — | 1–65535（含端点）；非整数/越界/显式 null→422（§16） |
| description | string | 是 | 否 | — | 描述性自由文本；长度交 D01（PROPOSED 无上限、text，同 F003/F004/F007/F008/F009/F010/F011） |
| id / version / created_at / updated_at / deleted_at | 标准 | — | — | — | 稳定 UUID；version 乐观锁（§23）；timestamptz UTC（D01 §2）；deleted_at 软删（§21） |

补充：
- 省略语义（§4.1/D01 §4）：创建省略非必填→默认/null；更新（PATCH）省略=保持（exclude_unset）；显式 null 仅清空 nullable（description）；必填/非 nullable（service/ip_address/protocol/port）显式 null→422；不可变/只读字段→422；未知字段→422。
- 不落字段：metadata（§16 未列举，PROPOSED 不落，见 I-1；请求含 metadata→422、响应不含）；无 name 字段（§4.1 名称归一化表不适用）；无 status、无实时探测/健康状态、无 listen_address 文本字段（监听地址由 ip_address 唯一确定）、无 Unix Socket、无端口范围、无 VIP 标识、无 URL/路径/TLS 配置。

**建议 D01 新增 §5.11 ServiceEndpoint 字段口径**（PROPOSED）：service 与 ip_address 创建必填、引用须存活；ip_address 须为已绑定且属 Service 所属 Resource 的 Interface；protocol ∈{TCP,UDP}；port 1–65535；description 可空无上限；不落 metadata/name/status。交 CONTRACT/D01 签核。

## 3. 领域影响分析

| 对象 | 关系 | 作用域 | 生命周期 | 依据 | 未决 |
| --- | --- | --- | --- | --- | --- |
| ServiceEndpoint | 多对一 Service；多对一 IPAddress | 监听唯一=同 IPAddress | 创建/改/软删/恢复 | §16/§21 | 字段可变性（I-2） |
| ServiceEndpoint→Service | N:1，创建必填，引用须存活 | 随 Service | 有未删 Endpoint 禁删 Service；不级联 | §16/§21 | 引用 provider 注册落点（I-5） |
| ServiceEndpoint→IPAddress | N:1，创建必填，引用须存活且已绑定 Service.Resource 的 Interface | IPAddress Cluster→Resource | 有未删 Endpoint 禁 IP 解绑/转移/释放 | §13.3/§14/§16/§21 | 引用 provider 注册落点（I-5） |
| 监听唯一 | (ip_address, protocol, port) 未删唯一 | IPAddress | 软删释放；恢复重检 | §16/§27 | 表示法归 Database（非产品） |
| IP↔Interface/Resource/Cluster 约束 | Endpoint 继承 IP 的绑定归属，须与 Service 同 Resource | Resource/Cluster | 创建/恢复重检 | §13/§14/§16 | 无（已确认） |
| 展示/查询 | §18 Services、§19、§33、§17（Service 搜索） | 随 Service/Resource/Cluster | — | §17/§18/§19/§33 | 页面聚合归 F013 |

数据完整性对应表（引用 `.pi/skills/data-integrity/SKILL.md`，精简；Database/Backend/Tester 补保证与证据）：

| 规则依据及版本 | 作用域/写入入口 | 数据库保证 | 业务层保证 | 并发/生命周期边界 | 验证与证据 |
| --- | --- | --- | --- | --- | --- |
| §16/§27 同 IP 未删 (protocol,port) 唯一 | 创建/恢复 | 部分唯一（(ip_address_id,protocol,port) WHERE deleted_at IS NULL，I-1） | 409 conflict | 索引仲裁；软删释放；恢复重检 | V-DB-TBD（F012） |
| §16 ip_address 必须已绑定且属 Service.Resource | 创建/恢复 | 跨表（service、ip_address、interface、resource）应用主校验；DB backstop 待 Database 裁定 | 422 field="ip_address" | — | V-DB-TBD |
| §16 protocol/port 取值域 | 创建/PATCH | CHECK protocol∈{TCP,UDP}、port 1–65535（待 Database） | 422 | — | V-DB-TBD |
| §13.3/§16/§21 Endpoint 引用 IP | IP 解绑/转移/释放 | — | F010 `check_ip_address_references` → F012 注册 provider → 409 reference_exists | 不级联 | F012 端到端（T22） |
| §16/§21 Endpoint 引用 Service | Service 删除 | — | F011 `check_service_references` → F012 注册 provider → 409 reference_exists | 不级联 | F012 端到端（T23） |
| §21/§27 软删/恢复 | 删除/恢复 | deleted_at + 部分唯一 | 恢复重检 service/IP 存活、IP 绑定归属、监听唯一；失败不覆盖 | 索引仲裁 | V-DB-TBD |
| §23 乐观锁 | PATCH/DELETE/restore | version + 条件 UPDATE | rowcount=0→409 | 真并发 | V-DB-TBD |

## 4. 必须遵守的已确认约束
- §16：`Resource → Service → ServiceEndpoint`；至少支持 service/ip_address/protocol/port/description；一个 Service 可有多个 Endpoint；IP 必填、未删除且绑定在 Service 所属 Resource 的 Interface；协议仅 TCP/UDP；端口 1–65535；同一有效 IP 上 protocol+port 不重复（含同一 Service 重复 Endpoint）；不同 Cluster 同值 IP 是不同 IP 对象；不支持 0.0.0.0、空监听地址、Unix Socket、跨资源共享 VIP；IP 解绑/转移/释放前须先处理引用它的 Endpoint。
- §13.3：解绑只移除 Interface 关系、IP 继续占用；释放=软删 IP、ADMIN 权限；解绑/转移/释放前必须先处理 Endpoint。
- §14：IP 绑定 Interface 时 Resource 与 Network 同 Cluster；Endpoint 要求 IP 的 Interface 属 Service 所属 Resource，故端点的 Service 与 IP Cluster 一致。
- §21：ServiceEndpoint 使用 deleted_at 软删、默认查询隐藏；有未删除依赖时禁删并返回引用列表、不隐式级联；ADMIN 恢复/查看已删；恢复只恢复自身、重检唯一性与所属对象有效性，失败不覆盖新对象；Audit 保留。
- §22：CREATE/UPDATE/DELETE/RESTORE 写 Audit；Activity 全角色；不记密码/令牌等敏感内容。
- §23：EDITOR 新增/修改；VIEWER 只读；删除/查看已删/恢复 ADMIN；乐观锁版本冲突检查；权限服务端执行。
- §25/§26：REST 前缀 `/api/v1/`；PostgreSQL / SQLAlchemy 2.x / Alembic；pg_trgm 属 F013。
- §27：监听唯一由 PostgreSQL 兜底、业务层共同保证；真实 PG 验证。
- §28：列表页至少分页、排序、过滤。
- §15（连带）：登记 Endpoint 不代表监控、进程探测、自动部署或端口实开校验；不由名称/外部探测推导。
- §4/§4.1：内部关联用稳定 UUID；D01 §4 省略语义与 422 口径；Endpoint 无名称字段，§4.1 名称规则不适用。
- §32/§33：上线验收要求 Endpoint 行为满足本 revision 约束；可回答「机器运行哪些 Service/监听」。

## 5. 可观察验收标准

| # | 验收标准 | 映射 |
| --- | --- | --- |
| A1 | 创建缺失 service/ip_address/protocol/port 任一必填→422；未知/只读字段→422 | §16/§4.1/T37 |
| A2 | service 不存在/已软删→422 field="service" | §16/§21 |
| A3 | ip_address 不存在/已软删→422 field="ip_address" | §16/§21 |
| A4 | ip_address 未绑定 Interface（interface 为空）→422 field="ip_address"；未绑定 IP 不能登记 Endpoint | §16 |
| A5 | ip_address 绑定的 Interface 不属于 Service 所属 Resource（跨 Resource/跨 Cluster VIP）→422 field="ip_address" | §14/§16/T22 |
| A6 | protocol 非 TCP/UDP（含显式 null）→422；TCP、UDP 正常登记 | §16/T22 |
| A7 | port 为 0、65536、负数、非整数或显式 null→422；1 与 65535 边界接受 | §16/T22 |
| A8 | 同一未删除 IP 上重复 (protocol,port) →409 CONFLICT{unique_conflict}；含同一 Service 的重复 Endpoint | §16/T22 |
| A9 | 不同 IP 对象可有相同 (protocol,port)，含不同 Cluster 的同值地址；不同 IP 的监听互不冲突 | §16/T22 |
| A10 | 一个 Service 可有多个 Endpoint（同 IP 不同端口，或不同 IP 不同端口） | §16/T22 |
| A11 | description 可空、PATCH 显式 null 清空、PATCH 省略保持 | §16/§4.1 |
| A12 | 有未删除 Endpoint 引用时，IP 解绑/转移/释放被拒并返回 references（F010 检查器 + F012 注册的 Endpoint provider）；不隐式级联、不自动删除 Endpoint | §13.3/§16/§21/T22 |
| A13 | 有未删除 Endpoint 引用时 Service 删除被拒并返回 references（F011 检查器 + F012 注册的 provider）；不隐式级联 | §16/§21/T23 |
| A14 | Endpoint 软删；默认列表/详情隐藏已删；ADMIN 可查看已删与恢复；恢复重检 service 及 ip_address 未软删、IP 仍绑定且属 Service 所属 Resource、监听唯一，失败不覆盖新对象，不级联恢复 | §21/T24 |
| A15 | 权限：VIEWER 只读；EDITOR 新增/修改 Endpoint；删除/查看已删/恢复 ADMIN；服务端执行 | §23/T25 |
| A16 | CREATE/UPDATE/DELETE/RESTORE 写 Audit 且同事务，object_type="service_endpoint"；Activity 全角色可见；不记敏感内容 | §22/T25/T26 |
| A17 | 乐观锁：过期版本编辑被拒（409 VERSION_CONFLICT），无静默覆盖 | §23/T26 |
| A18 | 默认列表隐藏软删；按 service、ip_address、protocol 过滤，分页/排序符合列表基线 | §21/§28 |
| A19 | 输入 0.0.0.0、空监听地址、Unix Socket、端口范围/列表、空 host 等非法监听形式被拒（不支持通配/Unix Socket/共享 VIP） | §16 |
| A20 | 同 IP 未删 (protocol,port) 唯一由 PostgreSQL 部分唯一兜底，真实 PG 验证；并发创建仅一成功 | §27/T22 |
| A21 | 字段省略语义按 D01 §4：创建省略非必填→默认/null；PATCH 省略=保持；显式 null 仅清空 description；不可变/只读/未知字段→422 | §4.1/D01/T37 |

说明：A12 依赖 F010 已交付的 `register_ip_address_reference_checker` 挂钩；A13 依赖 F011 已交付的 `register_service_reference_checker` 扩展点；F012 注册真实 provider 后 T22/T23 端到端成立。T40/T41（名称规则/复用）针对 Network/Pool/Service/Interface；ServiceEndpoint 无名称字段，不适用，本 Feature 不重复。

## 6. 明确排除项
- 不做 Service 本体与 `/api/v1/services` 及其名称/状态/软删（F011，DONE）。
- 不做 IPAddress 本体、分配/解绑/转移/释放与容量口径（F010，DONE）；F012 只注册 Endpoint 引用 provider，不改 F010 规则。
- 不做 Global Search、Dashboard、列表聚合与跨对象模糊搜索（F013）；F012 提供 Endpoint 数据，不建页面。
- 不做 CSV/Excel 导入（F014）；完整 Audit 查询页（F015）；一期集成验收（F016）。
- 不支持通配地址 0.0.0.0/空监听地址、Unix Socket、跨资源共享 VIP、端口范围/端口列表、IPv6、URL/路径、TLS/证书、代理/转发、健康检查/存活探测、端口实开探测、自动发现监听。
- 不落 metadata/name/status/实时探测状态/listen_address 文本/部署或同步标记（PROPOSED，I-1）。
- 不改动 F010/F011 已交付语义（IP 唯一/CIDR/Cluster 一致性；Service 名称/状态/Resource 归属）。
- 不因登记 Endpoint 触发部署、监控或状态同步。

## 7. 依赖与未决问题
依赖（CONFIRMED）：F010（IPAddress、绑定 Interface、`register_ip_address_reference_checker` 挂钩、`_lock_network`/唯一基座；DONE）；F011（Service 实体、`register_service_reference_checker` 扩展点、Resource 归属；DONE）；F001（PostgreSQL 基线、真实 PG 测试基线）；D01 共享约定（v10+）。F013 依赖本 Feature 的 Endpoint 展示数据；F015 依赖本 Feature 的删除/恢复规则。

BLOCKING：无。

CONFIRMED：§16 全部；§13.3 的 Endpoint 前置处理；§14 相关一致性；§21 软删/恢复/引用检查；§22；§23；§27；§28；Q06/Q10-A。

PROPOSED/OPEN（非阻塞）：
- **I-1（PROPOSED，非阻塞，Owner Architect/D01）**：§16 字段清单未列举 metadata。**PROPOSED**：不落 metadata（同 F010 IPAddress），仅 description 可空；请求含 metadata→422、响应不含；D01 新增 §5.11 固定。
- **I-2（OPEN，产品/设计，非阻塞）**：§16 未说明 service/ip_address/protocol/port 创建后是否可改。**PROPOSED**：service 与 ip_address 创建必填、创建后不可改（改绑定即新 Endpoint，删除重建），与 Interface.resource、Network.cluster、IPAddress.network/address 口径一致；protocol/port 允许 PATCH 并重检监听唯一；description 可空可改。若确认 protocol/port 亦不可变，则全部删除重建。Owner：Product/用户 → Architect/CONTRACT。
- **I-3（OPEN，D01，非阻塞）**：D01 尚未界定 ServiceEndpoint 字段口径。**PROPOSED**：新增 §5.11（service/ip_address 建必填活引用、ip_address 须已绑定且属 Service.Resource、protocol∈{TCP,UDP}、port 1–65535、description 无上限、不落 metadata/name/status）。Owner：Architect/Database → CONTRACT/D01。
- **I-4（OPEN，跨 Feature 契约不一致，非阻塞）**：引用列表的 `object_type` 命名不一致——`docs/api/F010.md` v1 与 `backend/tests/integration/test_ip_addresses.py` 使用 `"endpoint"`，`docs/api/F011.md` v1 与 `backend/tests/integration/test_services*.py` 使用 `"service_endpoint"`。F012 需同时注册两个 provider，须统一 canonical 值（**PROPOSED：`"service_endpoint"`**）并修正 F010 侧文档/桩测试引用列表口径，避免 T22/T23 断言分歧。Owner：Architect/协调器 → CONTRACT/F010 errata。
- **I-5（OPEN，跨 Feature 边界，非阻塞）**：T22/T23 要求含 Endpoint 的端到端引用保护。**PROPOSED**：F012 在启动时注册 `register_ip_address_reference_checker`（Endpoint 引用 IP）与 `register_service_reference_checker`（Endpoint 引用 Service）两个真实 provider，返回未删除 Endpoint 引用列表；F010/F011 的挂钩已就绪，端到端在 F012 完成。Owner：Architect/协调器。
- **I-6（NOTE，非阻塞，计划字段）**：`project-plan.yaml` F012 未填 `layers` 与 `api_required`。协调器/Architect 在 ARCHITECTURE 阶段补齐（预期 api_required=true，layers 含 database/backend，frontend 归属 F013/F012 由设计裁定）。Owner：协调器/Architect。
- **I-7（NOTE，非阻塞）**：T40/T41 的名称规则/复用不适用于 ServiceEndpoint（无 name 字段）；§4.1 名称归一化表不适用。Owner：Architect/Database（记录即可）。

## 8. 交 Architect 的输入
1. 实体方案：ServiceEndpoint 独立表 PK=UUID；FK service_id→services(id)（RESTRICT）；FK ip_address_id→ip_addresses(id)（RESTRICT）；字段同 §2。
2. 约束：service_id/ip_address_id NOT NULL；protocol CHECK∈{TCP,UDP}；port CHECK 1–65535；description text NULL；metadata 不落（I-1）；version≥1；软删 deleted_at。
3. 归属与校验：创建/恢复校验 service 未软删；ip_address 未软删且已绑定 Interface 且 `ip_addresses.interface_id→interfaces.resource_id == services.resource_id`（Cluster 随之一致）；违反 422 field="ip_address"；是否加 DB backstop 触发由 Database 裁定。
4. 监听唯一：同一未删除 IP 上 `(ip_address_id, protocol, port)` 部分唯一 `WHERE deleted_at IS NULL`（I-1/§27），软删释放、恢复重检。
5. 生命周期与引用：软删/恢复；恢复重检 service/IP 存活、绑定归属、监听唯一，失败不覆盖；F012 注册两个真实 provider：IP 侧（解绑/转移/释放拦截，F010 `register_ip_address_reference_checker`）与 Service 侧（删除拦截，F011 `register_service_reference_checker`）；引用 `object_type` 统一（I-4）。
6. API：建议 `/api/v1/service-endpoints`（或按 D01/既有路径风格裁定），契约含创建/更新/详情/列表/删除/恢复/activity；沿用 D01 §4 省略语义、422/409 错误口径、乐观锁、软删可见性；列表按 service/ip_address/protocol 过滤（§28）。
7. 权限/审计：EDITOR 增改；ADMIN 删除/恢复/查看已删；VIEWER 只读；CREATE/UPDATE/DELETE/RESTORE 写 Audit（before/after），object_type="service_endpoint"；Activity 全角色。
8. D01 补齐：新增 §5.11 ServiceEndpoint 字段口径，CONTRACT 签核（I-3）；记录 protocol 大小写口径（I-4 关联）。
9. 边界语义：向 F013 暴露 Endpoint（Service/IP/协议/端口）供 §18/§19/§17 展示；不改 F010/F011 语义；不支持通配/Unix Socket/共享 VIP/端口范围。
10. 错误码：复用 F002/F010/F011 现有 code 与 reason（`unique_conflict`、`reference_exists`、`not_deleted`、`dependency_deleted`），无新增 reason 预期。
11. 待裁定/记录：I-1（metadata）、I-2（字段可变性）、I-3（D01 §5.11）、I-4（object_type 命名统一）、I-5（双 provider 落点）、I-6（计划字段）、I-7（名称规则不适用）。

## 9. 结论与下一步
无 Blocking Questions。**READY FOR ARCHITECT**。下一步 ARCHITECTURE：ServiceEndpoint 实体/依赖方案、layers、api_required；CONTRACT 定稿 ServiceEndpoint API 与 D01 §5.11 字段口径，统一引用 `object_type`（I-4），裁定字段可变性（I-2）；注册两个引用 provider 并完成 T22/T23 端到端；DATABASE 依 D01 签核监听唯一部分唯一、protocol/port CHECK、归属校验与真实 PostgreSQL 验证方案。