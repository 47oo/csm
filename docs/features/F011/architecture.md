# F011 Service 服务登记 — ARCHITECTURE 阶段报告

- **Task**：F011（FEATURE，P1，M5 服务与端点，deps [F004]）— Architect，Feature 设计模式
- **阶段**：ARCHITECTURE；**结论**：`READY FOR DESIGN`（2026-10-09）
- **Basis**：requirements-v3.md revision 3（§4、§4.1、§5、§15、§16、§17、§18、§19、§21、§22、§23、§25、§26、§27、§28、§31 T21/T23/T24/T25/T26/T36/T37/T40/T41、§32、§33、§35.2 Q02-A/Q06/Q10-A/Q10-B、§35.3 D01/D02）；docs/features/F011/product.md（A1–A18、I-1–I-6）；docs/features/F009/architecture.md（DR-102–DR-117）；docs/features/F010/architecture.md（DR-118–DR-139）；docs/api/F004.md v3、F009.md v1、F010.md v1；docs/database/f004-resource.md v1、f009-ip-pool.md v1、f010-ip-address.md v1；docs/architecture/d01-conventions.md v9；plan_revision 4 F011

## 1. 方案摘要

### 1.1 Service 实体（独立表，PK=UUID）
Service 是独立可寻址对象（§21 软删清单含 Service；自身 UUID/version/软删/恢复/Activity），非 Resource 的 1:1 明细，故 PK 为自身 UUID，`resource_id` 为普通 FK（RESTRICT）。Service 是 F012 ServiceEndpoint 的父对象，并被 §17/§18/§19 展示消费。

| 字段 | 类型 | 空 | 默认 | 语义 |
| --- | --- | --- | --- | --- |
| id | UUID | 否 | gen_random_uuid() | PK pk_services |
| resource_id | UUID | 否 | — | FK→resources(id) ON DELETE RESTRICT；创建必填；引用须存在未软删；创建后不可改（DR-144） |
| name | varchar(255) | 否 | — | trim→非空→禁 Cc/Cf；允许中文及内部普通空格、不合并；大小写不敏感；同 Resource 未删唯一；删除后复用（DR-141） |
| name_key | varchar(255) | 否 | — | ASCII_lower(btrim(name))；部分唯一载体（DR-141） |
| status | varchar(16) | 否 | 'UNKNOWN' | RUNNING\|STOPPED\|UNKNOWN；CHECK∈3 值；人工维护、非探测（DR-142） |
| description | text | 是 | null | 描述性自由文本，无长度上限 |
| metadata | JSONB | 否 | '{}' | Service 自有、object、整值替换；非 object/null→422（DR-143） |
| version | integer | 否 | 1 | 乐观锁 CHECK ≥1 |
| created_at/updated_at | timestamptz | 否 | now() | UTC；updated_at 应用维护 |
| deleted_at | timestamptz | 是 | null | 软删 |

省略语义（§4.1/D01 §4）：创建省略非必填→默认/null；PATCH 省略=保持（exclude_unset）；显式 null 仅清空 nullable（description）；必填/非 nullable（resource/name/status/metadata）显式 null→422；不可变/只读字段（resource/resource_id/id/name_key）出现在请求体→422；未知字段→422；结构字段（metadata）整值替换。不落字段：IP/端口/协议/监听地址（§16 归 F012）、cluster 直接字段（经 Resource 间接）、service_type 枚举、实时探测状态、自动部署/同步标记。

### 1.2 关系
- Service 多对一依附 Resource（`resource_id`）；无 resource_type 限制（§15）。
- Service 经 Resource 间接归属 Cluster（§4/§5）。
- Service 1:N ServiceEndpoint（F012）；有未删除 Endpoint 引用时禁删 Service（引用数据由 F012 提供）。
- 一个 Resource 可有多个 Service；名称唯一、软删复用、恢复重检的作用域均为同 Resource。
- `status` 为人工维护的登记状态，与名称、外部探测、系统进程无关（§15/T21）。

## 2. Domain / Data Impact

| 对象 | 关系 | 作用域 | 生命周期 | 依据 | 裁定 |
| --- | --- | --- | --- | --- | --- |
| Service | 多对一 Resource；1:N ServiceEndpoint（F012） | 名称唯一=同 Resource | 创建/改名/改状态/改描述或 metadata/软删/恢复 | §4/§15/§21 | resource 不可改（DR-144） |
| Service→Resource | N:1，创建必填，引用须存活 | Resource 所在 Cluster（间接） | Resource 软删后其（软删）Service 仍存，恢复 Service 重检 Resource | §4.1/§15/§21 | 依赖检查器（DR-148） |
| name 唯一 | 同 Resource 未删除，大小写不敏感 | Resource | 软删后复用；恢复重检 | §4.1/§21/Q10-B | 部分唯一致 + name_key（DR-141） |
| status | RUNNING/STOPPED/UNKNOWN 人工维护 | 本对象 | 默认 UNKNOWN，仅经 API 变更 | §15/Q02-A/T21 | 非探测、不由名称推导（DR-142） |
| metadata | Service 自有 JSONB | 本对象 | 整值替换 | §15/D01 | 归属固定（DR-143，采纳 I-1） |
| Service←ServiceEndpoint | Endpoint 引用 Service，1:N | 同 Service | 有未删 Endpoint 禁删；不级联 | §16/§21 | 引用检查扩展点（DR-146，F012 落地） |
| Resource←Service | 未删 Service 阻塞 Resource 删除 | Resource | Resource 删除前检查 | §21（通用引用规则） | 引用检查器（DR-147，收窄 F004） |
| 展示/查询 | §18 Resource Detail Services、§19 Cluster Detail Services、§17 Service 搜索、§33 | 随 Resource/Cluster | — | §17/§18/§19/§33 | 页面聚合归 F013 |

**数据完整性对应表**（引用 `.pi/skills/data-integrity/SKILL.md`；Database/Backend/Tester 分别补保证与证据）

| 规则依据及版本 | 作用域/写入入口 | 数据库保证 | 业务层保证 | 并发/生命周期边界 | 验证与证据 |
| --- | --- | --- | --- | --- | --- |
| §4.1/§27/DR-141 Service 名称同 Resource 未删唯一 | POST/PATCH/restore | 部分唯一 `(resource_id,name_key) WHERE deleted_at IS NULL`；name_key CHECK | trim；ASCII 折叠；409 `unique_conflict{field:"name"}` | 索引仲裁；软删释放；恢复冲突拒 | V-DB-TBD（F011） |
| §4.1/T40 名称规范 | POST/PATCH | ck_*（ASCII backstop + 长度） | trim→非空→禁 Cc/Cf→1–255；内部空格保留 | Cc/Cf 应用责任 | 同上 |
| §4.1/§15/DR-144 resource 引用与不可变 | POST/PATCH | FK NOT NULL RESTRICT | 422 field="resource"（缺失/不存在/软删）；PATCH 出现 resource→422 | — | V-DB-TBD |
| §15/DR-142 status 默认与取值 | POST/PATCH | CHECK ∈3 值 + NOT NULL DEFAULT 'UNKNOWN' | 省略→UNKNOWN；非法/null→422；仅 API 变更 | — | V-DB-TBD |
| §15/DR-143 metadata | POST/PATCH | JSONB NOT NULL DEFAULT '{}'；CHECK jsonb_typeof='object' | 非 object/null→422；整值替换 | — | V-DB-TBD |
| §21/§16/DR-146 Endpoint 引用保护 | DELETE Service | 无（Endpoint 在 F012，跨表） | 引用检查注册表（F011 空集）；409 `reference_exists`；不级联 | F012 注册真实 provider | F011 桩 + F012 端到端（T23） |
| §21/DR-147 Resource←Service 引用 | DELETE Resource (F004) | FK RESTRICT（物理兜底） | F011 注册检查器；未删 Service→409 `reference_exists` | 软删释放；恢复重检 | V-DB-TBD |
| §21/DR-148 恢复重检 | restore Service | deleted_at + 部分唯一 | 重检 name 唯一、Resource 未软删；失败不覆盖 | 不级联、不恢复 Endpoint | V-DB-TBD |
| §23 乐观锁 | PATCH/DELETE/restore | version + 条件 UPDATE | rowcount=0→409 VERSION_CONFLICT | 真并发 | V-DB-TBD |

## 3. Frontend / Backend Work

**Backend（`layers.backend=true`）**
- `app/models/service.py`：ORM 映射（`resource_id` FK、`name`/`name_key`、`status`、`description`、`metadata`、version、deleted_at）。
- `app/schemas/service.py`：POST/PATCH/响应 schema；exclude_unset；点路径 422。
- `app/services/service.py`：name_key 归一化（逐码位 ASCII 折叠）、status/metadata 校验、软删过滤、乐观锁、Activity、审计、restore 重检。
- **引用检查扩展点（新）**：`app/services/service_reference.py`，与 F010 `ip_address_reference.py` 同构：`register_service_reference_checker(checker)` + `check_service_references(db, service_id)`（F011 默认空集；F012 注册真实 Endpoint provider）；`delete_service` 软删前调用。
- **注册引用检查器**：`cluster_service.register_reference_checker("resource", _undeleted_service_references)`（未删 Service 阻塞 Resource 删除 → `references:[{object_type:"service",object_id,label}]`）。
- **注册依赖检查器**：`cluster_service.register_dependency_checker("service", _service_resource_dependency)`（Service 恢复时 Resource 仍软删/缺失 → `conflicts:[{object_type:"resource",object_id}]`）。
- **导入时注册**：`resource.py` 末尾引用 service 模块，保证引用检查器注册。
- **审计白名单**：`service` 快照 `{resource_id,name,status,description,metadata}`；`object_type="service"`；四类 action 同事务。
- `app/api/v1/services.py` + router 挂载；迁移 `0011_services`（down_revision=`0010_ip_addresses`）。

**Frontend（`layers.frontend=true`）**
- Services 列表与详情页（§28）；Resource Detail 的 Services 区域（§18，`GET /api/v1/services?resource_id=…`）。
- Service 创建/编辑表单：Resource 选择器（创建后不可改）、name、status、description、metadata；422 点路径展示。
- 409 `unique_conflict{name}` / `reference_exists`（F012 起真实）/ `dependency_deleted` 呈现。
- 已删开关与 ADMIN 恢复入口；Activity。
- **归属裁定（I-6）**：`frontend=true`（§18/§28 领域 UI）；§19 Cluster Detail Services、§17 全局 Service 搜索、§20 Dashboard 归 F013。

**Database（`layers.database=true`，由 Database 承担）**：见 §7、§8。

## 4. API 裁定与 Contract 要点
裁定（DR-149）：新建独立端点 `/api/v1/services` + 独立 Contract `docs/api/F011.md`（§25 明列 services）。

7 端点：`GET/POST /api/v1/services`；`GET/PATCH/DELETE /api/v1/services/{id}`；`POST /api/v1/services/{id}/restore`；`GET /api/v1/services/{id}/activity`。

响应 Service：id、resource{id,hostname}、name、status、description|null、metadata、version、created_at/updated_at、deleted_at。列表 {items,page,page_size,total}。name_key 不暴露。

过滤/排序：resource_id、status、q（name 大小写不敏感子串）、deleted∈{exclude,include,only} 默认 exclude；page/page_size；sort∈{name,status,created_at,updated_at} 默认 created_at、order∈{asc,desc} 默认 desc；sort=name 按 name_key。不新增 cluster 过滤参数。

错误码：复用 F002/F003/F004，不新增 reason。`unique_conflict{field:"name"}`、`not_deleted`、`dependency_deleted{conflicts:[{object_type:"resource",object_id}]}`、`reference_exists{references:[{object_type:"service_endpoint",object_id,label}]}`（F011 默认空集，F012 真实）。

审计白名单：`{resource_id,name,status,description,metadata}`；`object_type="service"`。

## 5. 名称、状态与不可变（I-1/I-2/I-3，DR-141/142/143/144）
### 5.1 名称唯一（DR-141）
`name_key = ASCII_lower(btrim(name))`（仅 ASCII A-Z→a-z，非 ASCII 原样，locale 无关）；部分唯一 `UNIQUE(resource_id, name_key) WHERE deleted_at IS NULL`；内部普通空格允许且不合并；长度 1–255。跨 Resource 同名允许；软删复用；恢复重检冲突→409 `unique_conflict{field:"name"}`，不覆盖。
### 5.2 status（DR-142）
枚举 RUNNING/STOPPED/UNKNOWN，NOT NULL DEFAULT 'UNKNOWN'；显式 null/非法→422。人工维护：API 是唯一变更入口，不由名称或外部监控推导/自动转换；登记 slurmd 不触发 Slurm 部署或状态同步。
### 5.3 metadata（DR-143）
§15 字段清单包含 metadata → CONFIRMED 字段；归属 PROPOSED 为 Service 自有 JSONB（采纳）；object、默认 {}、整值替换；非 object/null→422；响应暴露。
### 5.4 resource 不可变（DR-144）
创建必填、创建后不可改（PATCH 出现 resource/resource_id 含同值→422）；迁移以删除重建表达；无 resource_type 限制。

## 6. 引用检查与跨 Feature 落点（I-4，DR-146/147/148）
- **Service←ServiceEndpoint**：`service_reference.py` 提供注册/检查；默认空集；`delete_service` 已调用；F012 注册真实 provider；T23 端到端留 F012；F011 以桩验证空集放行与调用链。
- **Resource←Service**：F011 注册，未删 Service 阻塞 Resource 删除（`references:[{object_type:"service",...}]`），与 F006/F007 同机制。
- **Service 恢复依赖**：Resource 仍软删/缺失→409 `dependency_deleted`；不覆盖；不自动恢复 Endpoint。
- **DB 侧**：`services.resource_id` FK RESTRICT（物理兜底）；软删引用保护由应用检查器承担。

## 7. 数据库影响（交 DATABASE）
表 `services`：id UUID PK；resource_id NOT NULL FK RESTRICT + ix_services_resource_id；name varchar(255) NOT NULL + ck；name_key varchar(255) NOT NULL + ck；status varchar(16) NOT NULL DEFAULT 'UNKNOWN' + CHECK；description text NULL；metadata JSONB NOT NULL DEFAULT '{}' + CHECK jsonb_typeof='object'；version integer NOT NULL DEFAULT 1 CHECK≥1；时间戳。
约束/索引：`uq_services_resource_id_name_key UNIQUE(resource_id,name_key) WHERE deleted_at IS NULL`；ix_services_resource_id、ix_services_status、ix_services_deleted_at；F011 不建 pg_trgm GIN（**F013 errata**：F013 追加 `ix_services_name_key_trgm` GIN trigram）。
迁移 `0011_services`（down_revision=0010_ip_addresses）；全表新建无回填、对称可逆；真库 up/down/up。
F011 注册 Resource←未删 Service 引用检查器。

## 8. D01 v9→v10 补齐（I-1/I-3/I-5，DR-152）
- §5 表将「IPPool/Service name」合并行拆为两行；Service name 行：唯一范围=同 Resource；大小写=不敏感（保留展示）；内部空白=允许内部普通空格（不自动合并）；归一化键=name_key=ASCII_lower(btrim(name))；部分唯一 (resource_id,name_key) WHERE deleted_at IS NULL；删除后复用=是。
- §5.2 追加 Service name 255。
- 新增 §5.10 Service 字段口径（name 1–255 仅 ASCII 折叠、status 默认 UNKNOWN、description text 无上限、metadata Service 自有、resource 创建必填不可改、不落 IP/端口/协议/cluster 直字段）。
- §8 记 v10。

## 9. 验证策略（A1–A18，真实 PG）
- 名称/唯一：trim/空/控制字符→422；中文与内部普通空格保留不合并（A1）；同 Resource 大小写不敏感重名→409 unique_conflict；跨 Resource 同名允许（A2）；软删复用/存活同名失败/恢复不覆盖（A3/A16）；name_key 归一化 API/DB 一致（A16）。
- 必填/引用：缺 resource/name→422；resource 不存在/已软删→422（A4）。
- status：省略→UNKNOWN；保存；显式 null/非法→422（A5/A6）。
- description：可空、PATCH null 清空、省略保持（A7）。
- metadata：省略→{}；整值替换；非 object/null→422（A8）。
- resource 不可变：创建必填；PATCH 出现→422（A9）。
- 删除/引用：F011 默认空集放行；结构与调用链就位；Endpoint 端到端（A10/T23）留 F012；不级联。
- 恢复：重检 name 唯一与 Resource 有效；失败不覆盖；不自动恢复 Endpoint（A11/T24）。
- 权限 A12/T25；审计 A13/T25；列表 A14；DB 兜底 A15；乐观锁 A17/T26；归属/查询 A18。
- 迁移：0011 up/down/up、单 head、无回填、约束/索引断言。
- **F011 独立**：A1–A9、A11–A18、T21/T24/T25/T26/T37/T40/T41（Service 部分）。
- **留待 F012**：A10/T23 Endpoint 引用端到端。**留待 F013**：§19/§17/Dashboard。

## 10. 技术决策（DR-140–DR-154，接续 F010 DR-139）

| ID | 决策 | 状态 |
| --- | --- | --- |
| DR-140 | Service 独立表 PK=UUID；`resource_id` FK→resources(id) ON DELETE RESTRICT | CONFIRMED+DESIGN |
| DR-141 | name varchar(255) trim/非空/禁 Cc/Cf、允许内部普通空格不合并、大小写不敏感；name_key=ASCII_lower(btrim(name))；部分唯一 (resource_id,name_key) WHERE deleted_at IS NULL | PROPOSED→CONTRACT(1–255)/D01 §5.10 |
| DR-142 | status varchar(16) NOT NULL DEFAULT 'UNKNOWN' CHECK∈3 值；人工维护、非探测、不由名称推导 | CONFIRMED（§15/T21）+DESIGN |
| DR-143 | metadata Service 自有 JSONB，object、默认 {}、整值替换；不并入 Resource 公共 metadata | PROPOSED→CONTRACT/D01（I-1） |
| DR-144 | `resource` 创建必填、创建后不可改（PATCH 含 resource/resource_id→422） | PROPOSED→CONTRACT（I-2） |
| DR-145 | 软删/恢复；恢复重检 name 唯一与 Resource 有效；不级联、不自动恢复 Endpoint；失败不覆盖 | CONFIRMED（§21）+DESIGN |
| DR-146 | Service←ServiceEndpoint 引用检查扩展点（F011 默认空集，F012 注册真实 provider）；T23 端到端留 F012 | PROPOSED→CONTRACT（I-4） |
| DR-147 | F011 注册 resource←未删 Service 引用检查器；与 F006/F007 同机制，收窄 F004 DELETE /resources | CONFIRMED（§21）+DESIGN |
| DR-148 | Service 恢复依赖检查：Resource 仍软删/缺失→409 dependency_deleted{conflicts:[{object_type:"resource"}]} | CONFIRMED（§21）+DESIGN |
| DR-149 | API 独立 /api/v1/services + 新建 docs/api/F011.md；7 端点 | PROPOSED→CONTRACT |
| DR-150 | 审计白名单 {resource_id,name,status,description,metadata}；object_type="service"；四类 action 同事务 | CONFIRMED（§22）+DESIGN |
| DR-151 | 迁移 0011_services（down_revision=0010_ip_addresses）；全表新建无回填、对称可逆、单 head | DESIGN→DATABASE |
| DR-152 | D01 v9→v10 新增 §5.10；§5.2 追加 Service name 255；§5 表 Service 单列一行；§8 记 v10 | PROPOSED→CONTRACT/D01（I-1/I-3） |
| DR-153 | 列表过滤 resource_id/status/q/deleted，排序 name/status/created_at/updated_at；不新增 cluster 过滤 | PROPOSED→CONTRACT |
| DR-154 | 错误码复用 F002/F003/F004（unique_conflict/not_deleted/dependency_deleted/reference_exists），F011 不新增 reason | CONFIRMED+DESIGN |

## 11. 裁定 I-1–I-6（PROPOSED→设计决定）
- **I-1（DR-143）**：metadata Service 自有 JSONB。D01 §5.10。
- **I-2（DR-144）**：resource 创建必填、创建后不可改。
- **I-3（DR-141/152）**：name 1–255、仅 ASCII 折叠、内部普通空格不合并；description text 无上限；D01 §5 表 Service 单列一行 + §5.10 + §5.2。
- **I-4（DR-146/147/148）**：Service←Endpoint 引用检查契约与 provider 扩展点（默认空集），F012 注册真实；T23 留 F012；同机制注册 Resource←Service 引用检查器。
- **I-5（DR-141/152）**：D01 措辞一致化。
- **I-6（DR-149/153）**：补 layers.database/backend/frontend=true、api_required=true；Frontend 归属本 Feature（§18/§28），§19/§17/Dashboard 归 F013。

## 12. 风险与待核对项
- **交 DATABASE**：name_key CHECK 口径；部分唯一 (resource_id,name_key) WHERE deleted_at IS NULL；metadata JSONB 默认/jsonb_typeof CHECK；status CHECK/默认；索引集合；迁移 0011 up/down/up；恢复重检与约束交互。
- **交 TEST_DESIGN**：A1–A18 的 F011 独立判据与 F012 端到端分界；并发部分唯一双会话；真实 PG 约束证据。
- **交 CONTRACT**：D01 v10 §5.10/§5.2/§5 表签核；reference_exists 复用登记。
- **跨 Feature（I-4）**：F012 须调用 register_service_reference_checker 并注册真实 Endpoint 检查器；否则 T23 端到端无法闭合（ISSUES，非 DESIGN BLOCK）。
- **F013 承接**：§19 Cluster Detail Services 与 §17 Service 搜索在 F011 列表无 cluster 过滤参数时由 F013 经 resource_id 集合或后续契约扩展实现（NOTE，非阻塞）。

## 13. Layers 与分工
```yaml
layers:
  database: true
  backend: true
  frontend: true
api_required: true
```
- Database：`docs/database/f011-service.md`；裁定 DR-140/141/142/143/151。
- Backend：models/schemas/service；service_reference.py + 注册 Resource←Service 引用检查器 + Service 依赖检查器；resource.py 导入；审计白名单；api/v1/services.py+router；迁移 0011。
- Frontend：Services 列表/详情；Resource Detail Services 区域；创建/编辑表单；删除/恢复/Activity；冲突呈现。
- Contract：`docs/api/F011.md` 置 READY；签核 D01 v10 §5.10；固定 DR-141/143/144/146/149/150/152/154。

## 14. 结论与下一步
无 Blocking Questions；I-1…I-6 已裁定。**Status：`READY FOR DESIGN`**。

下一步：DATABASE 出 `docs/database/f011-service.md`；TEST_DESIGN 给判据；CONTRACT 定稿 `docs/api/F011.md` + D01 v10 §5.10 → `READY FOR IMPLEMENTATION`。