# F012 Service Endpoint 监听端点 — ARCHITECTURE 阶段报告

- **Task**：F012（FEATURE，P1，M5 服务与端点，deps [F010, F011]）— Architect，Feature 设计模式
- **阶段**：ARCHITECTURE；**结论**：`READY FOR DESIGN`（2026-10-09）
- **Basis**：requirements-v3.md revision 3（§13/§13.3、§14、§15、§16、§17、§18、§19、§21、§22、§23、§25、§26、§27、§28、§31 T22/T23/T24/T25/T26/T37/T40/T41、§32、§33、§35.2 Q06/Q10-A、§35.3 D01/D02）；docs/features/F012/product.md（A1–A21、I-1–I-7）；docs/features/F010/architecture.md（DR-118–DR-139）、docs/api/F010.md v1、docs/database/f010-ip-address.md v1（DB-D111–D127）；docs/features/F011/architecture.md（DR-140–DR-154）、docs/api/F011.md v1、docs/database/f011-service.md v1（DB-D128–D141）；docs/architecture/d01-conventions.md v10；backend/app/services/ip_address_reference.py、service_reference.py；plan_revision 4 F012

## 1. 方案摘要

### 1.1 ServiceEndpoint 实体（独立表，PK=UUID）
ServiceEndpoint 是独立可寻址对象（§21 软删清单含 ServiceEndpoint；自身 UUID/version/软删/恢复/Activity），非 Service 或 IPAddress 的 1:1 明细，故 PK 为自身 UUID，`service_id` 与 `ip_address_id` 为普通 FK（RESTRICT）。ServiceEndpoint 是 `Resource → Service → ServiceEndpoint` 事实关系的叶子，承载「某 Service 在某 IP 上以某协议/端口监听」的权威数据，并被 §17/§18/§19 展示消费（展示归 F013）。

| 字段 | 类型 | 空 | 默认 | 语义 |
| --- | --- | --- | --- | --- |
| id | UUID | 否 | gen_random_uuid() | PK pk_service_endpoints |
| service_id | UUID | 否 | — | FK→services(id) ON DELETE RESTRICT；创建必填；引用须存在、未软删；创建后不可改（DR-157） |
| ip_address_id | UUID | 否 | — | FK→ip_addresses(id) ON DELETE RESTRICT；创建必填；引用须存在、未软删、已绑定 Interface 且该 Interface 属 Service 所属 Resource；创建后不可改（DR-157/DR-158） |
| protocol | varchar(8) | 否 | — | TCP\|UDP；CHECK∈2 值；仅接受大写规范值，存储大写（DR-160） |
| port | integer | 否 | — | 1–65535（含端点）；CHECK 1..65535（DR-160） |
| description | text | 是 | null | 描述性自由文本，无长度上限 |
| version | integer | 否 | 1 | 乐观锁 CHECK ≥1 |
| created_at/updated_at | timestamptz | 否 | now() | UTC；updated_at 应用维护 |
| deleted_at | timestamptz | 是 | null | 软删 |

省略语义（§4.1/D01 §4）：创建省略非必填→默认/null；PATCH 省略=保持（exclude_unset）；显式 null 仅清空 nullable（description）；必填/非 nullable（service/ip_address/protocol/port）显式 null→422；不可变/只读字段（service/service_id/ip_address/ip_address_id/id）出现在请求体→422；未知字段→422；请求含 metadata→422、响应不含（DR-156）。不落字段（§16）：metadata、name、status、listen_address 文本、Unix Socket、端口范围/列表、VIP 标识、URL/路径/TLS、实时探测/健康状态、部署/同步标记。

### 1.2 关系
- ServiceEndpoint 多对一依附 Service（`service_id`）；一个 Service 可有多个 Endpoint。
- ServiceEndpoint 多对一引用 IPAddress（`ip_address_id`）；该 IP 须已绑定 Interface，且 `interfaces.resource_id == services.resource_id`（同 Resource ⇒ 同 Cluster，§14/§16）。
- ServiceEndpoint 经 Service 间接归属 Resource / Cluster；经 IPAddress→Interface→Resource 关联到同一 Resource。
- 有未删除 Endpoint 引用时禁删 Service（F011 `register_service_reference_checker` 扩展点，F012 注册真实 provider）与禁 IP 解绑/转移/释放（F010 `register_ip_address_reference_checker` 挂钩，F012 注册真实 provider）；均不级联。
- 监听唯一作用域为同一 IPAddress；不同 IP 对象（含不同 Cluster 的同值地址）各自独立。
- 无子对象引用 Endpoint，删除不级联。

## 2. Domain / Data Impact

| 对象 | 关系 | 作用域 | 生命周期 | 依据 | 裁定 |
| --- | --- | --- | --- | --- | --- |
| ServiceEndpoint | 多对一 Service；多对一 IPAddress | 监听唯一=同 IPAddress | 创建/改 protocol·port·description/软删/恢复 | §16/§21 | service/ip_address 不可改（DR-157） |
| ServiceEndpoint→Service | N:1，创建必填，引用须存活 | 随 Service | 有未删 Endpoint 禁删 Service；不级联 | §16/§21 | 引用检查扩展点（DR-161） |
| ServiceEndpoint→IPAddress | N:1，创建必填，引用须存活且已绑定同 Resource 的 Interface | 随 IPAddress | 有未删 Endpoint 禁 IP 解绑/转移/释放 | §13.3/§14/§16/§21 | 引用检查挂钩（DR-161） |
| 归属一致性 | ip.interface 非空且 interface.resource_id == service.resource_id | Resource/Cluster | 创建/恢复重检 | §13/§14/§16/§27 | 应用主校验 422 field="ip_address"（DR-158） |
| 监听唯一 | (ip_address_id, protocol, port) 未删唯一 | IPAddress | 软删释放；恢复重检 | §16/§27 | 部分唯一（DR-159） |
| protocol/port 取值域 | TCP/UDP；1–65535 | 本对象 | 创建/PATCH | §16 | CHECK + 应用 422（DR-160） |
| 展示/查询 | §18 Services、§19 Cluster Detail、§17、§33 | 随 Service/Resource/Cluster | — | §17/§18/§19/§33 | 页面聚合归 F013 |

**数据完整性对应表**（引用 `.pi/skills/data-integrity/SKILL.md`，精简；Database/Backend/Tester 补保证与证据）

| 规则依据及版本 | 作用域/写入入口 | 数据库保证 | 业务层保证 | 并发/生命周期边界 | 验证与证据 |
| --- | --- | --- | --- | --- | --- |
| §16/§27/DR-159 同 IP 未删 (protocol,port) 唯一 | 创建/改 protocol·port/恢复 | 部分唯一 (ip_address_id,protocol,port) WHERE deleted_at IS NULL | 409 `unique_conflict{field:"port"}` | 索引仲裁；软删释放；恢复重检 | V-DB-TBD（F012） |
| §16/DR-158 ip_address 须已绑定且属 Service.Resource | 创建/恢复 | 跨表（service/ip_address/interface/resource）应用主校验；DB backstop 触发由 Database 裁定 | 422 field="ip_address" | 绑定/转移在 IP 事务内校验 | V-DB-TBD |
| §16/DR-160 protocol/port 取值域 | 创建/PATCH | CHECK protocol∈{TCP,UDP}、port 1–65535 | 422 field="protocol"/"port" | — | V-DB-TBD |
| §13.3/§16/§21 Endpoint 引用 IP | IP 解绑/转移/释放 | — | F010 `check_ip_address_references` → F012 provider → 409 `reference_exists` | 不级联 | F012 端到端（T22） |
| §16/§21 Endpoint 引用 Service | Service 删除 | — | F011 `check_service_references` → F012 provider → 409 `reference_exists` | 不级联 | F012 端到端（T23） |
| §21/§27 软删/恢复 | 删除/恢复 | deleted_at + 部分唯一 | 恢复重检 service/IP 存活、归属、监听唯一；失败不覆盖 | 索引仲裁 | V-DB-TBD |
| §23 乐观锁 | PATCH/DELETE/restore | version + 条件 UPDATE | rowcount=0→409 VERSION_CONFLICT | 真并发 | V-DB-TBD |

## 3. Frontend / Backend Work

**Backend（`layers.backend=true`）**
- `app/models/service_endpoint.py`：ORM 映射（`service_id`/`ip_address_id` FK、protocol、port、description、version、deleted_at、部分唯一索引）。
- `app/schemas/service_endpoint.py`：POST/PATCH/响应 schema；exclude_unset；点路径 422。
- `app/services/service_endpoint.py`：归属校验、监听唯一、软删过滤、乐观锁、Activity、审计、restore 重检。
- **引用检查 provider（新）**：`app/services/endpoint_reference.py`，注册两个真实 provider：
  - `register_ip_address_reference_checker(_undeleted_endpoints_for_ip)` → `[{object_type:"service_endpoint",object_id,label}]`（IP 侧，DR-161）；
  - `register_service_reference_checker(_undeleted_endpoints_for_service)` → 同 shape（Service 侧，DR-161）。
  - 导入时注册（启动导入链），保证 provider 生效。
- **审计白名单**：`service_endpoint` 快照 `{service_id,ip_address_id,protocol,port,description}`；`object_type="service_endpoint"`；四类 action 同事务。
- `app/api/v1/service_endpoints.py` + router 挂载；迁移 `0012_service_endpoints`（down_revision=`0011_services`）。

**Frontend（`layers.frontend=true`，DR-170）**
- Service Detail 内的 Endpoints 管理区（列表/新增/编辑/删除/恢复/Activity）。
- 创建/编辑表单：Service 选择器（创建后不可改）、IPAddress 选择器（过滤为该 Service 同 Resource 且已绑定的未删 IP）、protocol、port、description；422 点路径展示。
- 409 呈现：`unique_conflict`、`reference_exists`、`dependency_deleted`、`not_deleted` 与未知 reason 通用呈现；已删开关与 ADMIN 恢复入口。
- **边界（DR-170）**：F012 拥有 Endpoint 管理 UI；§18 Resource Detail Services 区域聚合、§19 Cluster Detail、§17 全局搜索、§20 Dashboard 归 F013。

**Database（`layers.database=true`，由 Database 承担）**：见 §7。

## 4. API 裁定与 Contract 要点
裁定（DR-163）：新建独立端点 `/api/v1/service-endpoints` + 独立 Contract `docs/api/F012.md`。

7 端点：`GET/POST /api/v1/service-endpoints`；`GET/PATCH/DELETE /api/v1/service-endpoints/{id}`；`POST /api/v1/service-endpoints/{id}/restore`；`GET /api/v1/service-endpoints/{id}/activity`。

响应 ServiceEndpoint：id、service{id,name,resource{id,hostname}}、ip_address{id,address,network{id,name},interface{id,name}}、protocol、port、description|null、version、created_at/updated_at、deleted_at。列表 {items,page,page_size,total}。

过滤/排序：service_id、ip_address_id、protocol、deleted∈{exclude,include,only} 默认 exclude；page/page_size；sort∈{protocol,port,created_at,updated_at} 默认 created_at、order∈{asc,desc} 默认 desc。不新增 cluster/resource 过滤参数。

错误码：复用 F002/F003/F010/F011，不新增 reason。`unique_conflict{field:"port",ip_address_id,protocol,port}`、`not_deleted`、`dependency_deleted{conflicts:[{object_type:"service"|"ip_address"|"interface",object_id}]}`、`reference_exists{references:[{object_type:"service_endpoint",object_id,label}]}`。

审计白名单：`{service_id,ip_address_id,protocol,port,description}`；`object_type="service_endpoint"`。

## 5. 归属校验、不可变与监听唯一（I-1/I-2）
### 5.1 不落 metadata（DR-156）
§16 字段清单未列举 metadata → 不落；请求含→422；响应不含；D01 §5.11 固定。无 name（§4.1 名称规则不适用）、无 status/listen_address。
### 5.2 归属校验（DR-158）
创建/恢复校验：service 存在未软删；ip_address 存在未软删；`ip_address.interface_id` 非空；该 Interface 存在未软删且 `interfaces.resource_id == services.resource_id`（同 Resource ⇒ 同 Cluster）；违反→422 field="service"/"ip_address"。
**DB backstop 要求（交 Database 裁定）**：归属为跨表规则；Database 至少须保证部分唯一；是否加 BEFORE INSERT/UPDATE 触发 backstop（模式同 F010 `trg_ip_addresses_interface_cluster`）由 Database 裁定。应用必须做主校验并映射 422；触发（若加）对任意 UPDATE 生效、不检查软删。因 `interfaces.resource_id`/`resources.cluster_id` 不可变，链路值稳定；IP 解绑/转移与 Endpoint 创建/恢复的窗口由应用在 IP 事务内校验。
### 5.3 监听唯一（DR-159）
部分唯一 `uq_service_endpoints_ip_protocol_port UNIQUE(ip_address_id, protocol, port) WHERE deleted_at IS NULL`；同 IP 未删 (protocol,port) 不重复；不同 IP 对象各自独立；软删释放；恢复重检被部分唯一拒绝→409 `unique_conflict`，不覆盖。冲突 details 携带 `{field:"port", ip_address_id, protocol, port}`。
### 5.4 不可变与可变字段（DR-157）
`service`/`ip_address` 创建必填、创建后不可改（PATCH 出现→422，含同值）；`protocol`/`port` 可 PATCH 并重检监听唯一；`description` 可改、显式 null 清空、省略保持。
### 5.5 protocol/port 取值（DR-160）
protocol ∈{TCP,UDP}（仅大写规范值，存储大写）；port 整数 1–65535；显式 null/非法→422；边界 1、65535 接受。

## 6. 引用检查与跨 Feature 落点（I-4/I-5）
### 6.1 双 provider 注册（DR-161）
F012 启动注册两个真实 provider：
- IP 侧：`register_ip_address_reference_checker(_undeleted_endpoints_for_ip)`（`service_endpoints WHERE ip_address_id=:id AND deleted_at IS NULL`）；F010 在解绑/转移/释放前调用。
- Service 侧：`register_service_reference_checker(_undeleted_endpoints_for_service)`（`WHERE service_id=:id AND deleted_at IS NULL`）；F011 `delete_service` 已调用。
- `label`=`f"{protocol}/{port}"`。F010/F011 挂钩已就绪，F012 只需注册。
### 6.2 object_type 命名统一（DR-162）— 跨 Feature 一致性订正
现状：F010 文档/桩测试用 `"endpoint"`，F011 用 `"service_endpoint"`。统一 canonical=`"service_endpoint"`。
**F010 errata-03**：`docs/api/F010.md` §1.2 `reference_exists` details `object_type:"endpoint"`→`"service_endpoint"`；§11 追加 errata-03；桩测试 `test_ip_addresses.py`（约 410/430/1331/1342 行）同步。**不影响 F010 DONE 行为**（F010 provider 当时为空集，生产路径从不产生 `"endpoint"`）。由 CONTRACT 落地、Backend/Tester 同步。
### 6.3 恢复依赖与引用保护（DR-166）
恢复重检：service 未软删、ip_address 未软删、归属成立、监听唯一，失败不覆盖；不级联。DB FK 均 RESTRICT（物理兜底）；软删引用保护由应用 provider 承担。

## 7. 数据库影响（交 DATABASE）
表 `service_endpoints`：id UUID PK；service_id NOT NULL FK RESTRICT + ix；ip_address_id NOT NULL FK RESTRICT + ix；protocol varchar(8) NOT NULL + CHECK∈{TCP,UDP}；port integer NOT NULL + CHECK 1..65535；description text NULL；version integer NOT NULL DEFAULT 1 CHECK≥1；时间戳；deleted_at。
约束/索引：`uq_service_endpoints_ip_protocol_port UNIQUE(ip_address_id,protocol,port) WHERE deleted_at IS NULL`；`ix_service_endpoints_service_id`、`ix_service_endpoints_ip_address_id`、`ix_service_endpoints_deleted_at`（+可选 protocol）；不建 pg_trgm/GIN。
归属 backstop：交 Database 裁定是否加触发（模式同 F010）。监听唯一必须由部分唯一兜底（§27）。
迁移 `0012_service_endpoints`（down_revision=`0011_services`）；全表新建无回填、对称可逆、单 head、不重复启用扩展；真库 up/down/up。

## 8. D01 v10→v11 补齐（I-3，DR-169）
新增 §5.11 ServiceEndpoint 字段口径：service/ip_address 创建必填、引用须存活、创建后不可改；ip_address 须已绑定 Interface 且属 Service 所属 Resource；protocol∈{TCP,UDP}（大写）；port 1–65535；description 可空无上限；不落 metadata/name/status/listen_address；§5 名称归一化表不适用；唯一同 IPAddress 未删 (ip_address_id,protocol,port) 部分唯一；§8 记 v11。交 CONTRACT/D01 签核。

## 9. 验证策略（A1–A21，真实 PG）
- 必填/省略/未知字段（A1/A21）；引用 service/ip 存在未软删（A2/A3）；归属未绑定/跨 Resource（A4/A5/T22）；protocol/port 边界（A6/A7）；监听唯一（A8/A9）；一 Service 多 Endpoint（A10）；description（A11）；引用保护（A12/T22、A13/T23）；软删/恢复（A14/T24）；权限（A15/T25）；审计（A16/T25/T26）；乐观锁（A17/T26）；列表（A18）；非法监听形式（A19）；部分唯一并发（A20/T22）。
- 迁移：0012 up/down/up、单 head、无回填、约束/索引断言。
- **F012 独立**：A1–A21（除展示聚合）、T22/T23/T24/T25/T26/T37/T40/T41（Endpoint 部分）。
- **留待 F013**：§18/§19/§17/§20 展示聚合。

## 10. 技术决策（DR-155–DR-170，接续 F011 DR-154）

| ID | 决策 | 状态 |
| --- | --- | --- |
| DR-155 | ServiceEndpoint 独立表 PK=UUID；`service_id` FK→services(id) RESTRICT；`ip_address_id` FK→ip_addresses(id) RESTRICT | CONFIRMED（§16/§21）+DESIGN |
| DR-156 | 不落 metadata（I-1）；`description` text 可空无上限；无 name/status/listen_address | PROPOSED→CONTRACT/D01 §5.11 |
| DR-157 | `service`/`ip_address` 创建必填、创建后不可改；`protocol`/`port` 可 PATCH 并重检监听唯一；`description` 可改 | PROPOSED→CONTRACT（I-2） |
| DR-158 | 归属校验：service 未软删；ip_address 未软删且已绑定 Interface 且 `interfaces.resource_id == services.resource_id`；违反 422 field="ip_address"；DB backstop 交 Database | CONFIRMED（§14/§16/§27）+DESIGN |
| DR-159 | 监听唯一 = 部分唯一 `UNIQUE(ip_address_id,protocol,port) WHERE deleted_at IS NULL`；软删释放、恢复重检 | PROPOSED→CONTRACT/DATABASE（I-2） |
| DR-160 | `protocol` varchar(8) CHECK∈{TCP,UDP}（仅大写规范值）；`port` integer CHECK 1–65535 | CONFIRMED（§16）+DESIGN |
| DR-161 | F012 注册两个真实 provider：IP 侧（F010 挂钩）+ Service 侧（F011 扩展点）；完成 T22/T23 端到端 | CONFIRMED（§16/§21）+DESIGN（I-5） |
| DR-162 | 引用列表 `object_type` canonical 统一为 `"service_endpoint"`；F010 Contract/桩测试 errata；不影响 F010 DONE 行为 | CONFIRMED+DESIGN（I-4） |
| DR-163 | API 独立 `/api/v1/service-endpoints` + 新建 `docs/api/F012.md`；7 端点 | PROPOSED→CONTRACT |
| DR-164 | 审计白名单 `{service_id,ip_address_id,protocol,port,description}`；`object_type="service_endpoint"`；四类 action 同事务 | CONFIRMED（§22）+DESIGN |
| DR-165 | 迁移 `0012_service_endpoints`（down_revision=`0011_services`）；全表新建无回填、对称可逆、单 head | DESIGN→DATABASE |
| DR-166 | 软删/恢复；恢复重检 service/IP 存活、归属、监听唯一；不级联；失败不覆盖 | CONFIRMED（§21）+DESIGN |
| DR-167 | 列表过滤 service_id/ip_address_id/protocol/deleted，排序 protocol/port/created_at/updated_at；不新增 cluster 过滤 | PROPOSED→CONTRACT |
| DR-168 | 错误码复用 `unique_conflict`/`reference_exists`/`not_deleted`/`dependency_deleted`；F012 不新增 reason | CONFIRMED+DESIGN |
| DR-169 | D01 v10→v11 新增 §5.11 ServiceEndpoint 字段口径；§8 记 v11 | PROPOSED→CONTRACT/D01（I-3） |
| DR-170 | 补 layers.database/backend/frontend=true、api_required=true；Frontend 归属本 Feature（Endpoint 管理 UI），§18/§19/§17/Dashboard 聚合归 F013 | PROPOSED→CONTRACT（I-6） |

## 11. 裁定 I-1–I-7（PROPOSED→设计决定）
- **I-1（DR-156）**：不落 metadata；D01 §5.11。
- **I-2（DR-157）**：service/ip_address 不可改；protocol/port 可 PATCH 并重检监听唯一；description 可改。
- **I-3（DR-169）**：D01 新增 §5.11。
- **I-4（DR-162）**：object_type 统一 `"service_endpoint"`；F010 errata；不影响 F010 DONE 行为。
- **I-5（DR-161）**：F012 注册两个真实 provider，完成 T22/T23 端到端。
- **I-6（DR-170）**：补 layers/api_required；Frontend 归属本 Feature，展示聚合归 F013。
- **I-7**：名称规则不适用于 ServiceEndpoint。

## 12. 风险与待核对项
- **交 DATABASE**：部分唯一 `(ip_address_id,protocol,port) WHERE deleted_at IS NULL`；protocol/port CHECK；是否加归属 backstop 触发；索引集合；迁移 0012 up/down/up；恢复重检。
- **交 TEST_DESIGN**：A1–A21 的 F012 独立判据与 F013 展示分界；监听唯一并发双会话；真实 PG 约束；T22/T23 端到端（含 F010 errata 后 `"service_endpoint"` 断言）。
- **交 CONTRACT**：`unique_conflict` 的 field/details 形态（元组）；D01 v11 §5.11 签核；F010 errata 落地；无新 reason。
- **跨 Feature（I-4/I-5）**：F012 须调用两个注册函数并注册真实 Endpoint provider，否则 T22/T23 无法闭合；F010 文档/桩测试口径订正后与 F011 一致。
- **F013 承接**：§18/§19/§17/Dashboard 展示经 service_id/ip_address_id 集合或后续契约扩展（NOTE，非阻塞）。

## 13. Layers 与分工
```yaml
layers:
  database: true
  backend: true
  frontend: true
api_required: true
```
- Database：`docs/database/f012-service-endpoint.md`；裁定 DR-155/158/159/160/165。
- Backend：models/schemas/services `service_endpoint`；`endpoint_reference.py`（两个 provider）+ 启动注册；审计白名单；`api/v1/service_endpoints.py`+router；迁移 0012。
- Frontend：Service Detail Endpoints 管理区。
- Contract：`docs/api/F012.md` 置 READY；签核 D01 v11 §5.11；落地 F010 errata；固定 DR-157/159/161/163/164/167/168/170。

## 14. 结论与下一步
无 Blocking Questions；I-1…I-7 已裁定。**Status：`READY FOR DESIGN`。**

下一步：DATABASE 出 `docs/database/f012-service-endpoint.md`；TEST_DESIGN 给判据（F012 独立 vs F013）；CONTRACT 定稿 `docs/api/F012.md` + D01 v11 §5.11 + F010 errata → `READY FOR IMPLEMENTATION`。