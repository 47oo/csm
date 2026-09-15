# CSM V1 系统级基础架构（DEC-009 ~ DEC-014）

> Status: **NOT READY FOR IMPLEMENTATION**
> Document Type: Architecture Handoff
> Author Role: architect
> Scope: DEC-009 ~ DEC-014
> Date: 2026-09-15
>
> ⚠️ 本文件中所有技术选型与方案均为 **`PROPOSED`，尚未批准**。
> `AGENTS.md` §9 与 `.pi/agents/architect.md` §7 明确禁止默认技术栈已确定。
> 用户批准对应 ADR 后，方可转为 `CONFIRMED`。

---

## Product Source

- `docs/product/requirements.md` —— CONFIRMED BASELINE，Primary Requirements Source
- `docs/product/domain-model.md` / `docs/product/domain-model.yaml` —— CONFIRMED 领域模型
- `docs/product/domain-conflict-handoff.md` —— Status `RESOLVED`（Q-001=C / Q-002=B / Q-003=A）
- `docs/project/project-plan.yaml` —— 14 个 Feature、DEC-009 ~ DEC-014、M1 ~ M5
- `.pi/skills/resource-domain/SKILL.md`、`docs/project/git-workflow.md`、`docs/project/repository-structure.md`

---

## Architecture Summary

为 greenfield 的 CSM V1 建立**单体、单机、内网 HTTP** 的最小可维护架构，使 F012 能落地显式资源类型建模、F013 能落地本地认证、F014 能落地逻辑删除与一致性基座，并让 F001 ~ F011 全部拥有可复用的分层、数据约束与 API 契约依据。

对现有系统的影响：

| 项 | 现状 |
|---|---|
| 已有模块 | **当前不存在**（仅 `docs/`、`.pi/`、`AGENTS.md`、`README.md`） |
| 领域对象 | 产品侧已 CONFIRMED（7 类资源）；实现侧 **当前不存在** |
| 数据库 | **当前不存在**（`docs/database/` 不存在） |
| API | **当前不存在**（`docs/api/` 不存在） |
| Backend / Frontend | **当前不存在** |
| 现有架构决策 | **无任何 ADR** |

方案要点（全部 `PROPOSED`）：

1. **单体分层应用**：HTTP 层 → 校验层 → 领域服务层 → 数据访问层 → 关系数据库。每类资源是**独立模块 + 独立表**，无通用 `resources` 表、无 ORM 多态继承、无 EAV、无 JSONB 万能模型。
2. **技术栈提案**：Python + FastAPI + Pydantic + SQLAlchemy 2.x + Alembic；Vue 3 + TypeScript + Vite + Element Plus；PostgreSQL；单台内网虚拟机上 nginx + 应用进程 + 数据库。
3. **唯一性双要点**在数据库层同时成立：大小写敏感由显式 collation 保证；「已删不占唯一性」由 partial unique index（`WHERE deleted_at IS NULL`）保证。
4. **标识与寻址**：所有资源使用不可变代理主键 `id`；Cluster 额外提供**名称寻址的只读路径别名**以尊重 R-CLUSTER-005 的产品意图。
5. **软删除**：`deleted_at TIMESTAMPTZ NULL` 单一机制贯穿所有资源表；父删子拦、不级联由领域服务在同一事务内加行锁保证。
6. **认证**：服务端会话（DB 会话表 + HttpOnly Cookie）+ Argon2id 口令哈希；V1 仅「已认证 / 未认证」两种边界，不做 RBAC。
7. **API 规范**：REST + JSON + `/api` 前缀 + 稳定 `code` 的错误信封；逐行错误用 `details[].row/.field/.code` 承载 R-IMPORT-003；集合空返回 200 空数组、父不存在返回 404，落地 R-QUERY-004。

---

## Domain Impact

**不新增、不修改任何领域对象、关系、状态或唯一性规则。** 本设计只做持久化与接口形式的选择。

受以下已确认规则约束：

- 7 类资源显式建模；Cluster 为顶层，**无 DataCenter**；**无 Rack / U 位**。
- **仅 BareMetal 有状态**（`IDLE/ALLOC/DOWN/UNKNOWN`，默认 `IDLE`，非空，人工维护）→ 落为 `bare_metal` 表上一个显式 `status` 列 + CHECK 约束，**不设通用 status 表**。
- 关系：BareMetal→Cluster（必选）、NetworkInterface→BareMetal（必选）、IPAddress→NetworkInterface（必选）、Service→(BareMetal|VM|Container)（必选、多选）；Service↔Cluster 由载体**推导**，不落 `service.cluster_id`。
- **UNCONFIRMED 关系不得被固化**：VirtualMachine→BareMetal 的强制性与 Container→载体的强制性**在 DDL 中不得默认 NOT NULL**，须保持可空/待定，直到 F006 / F007 的 Product 阶段确认。

---

## Data Layer Impact

数据层需要解决的问题（详细 Schema 由 Database Agent 交付）：

1. **8 张资源表 + 2 张认证表**（`users`、`sessions`），每表独立列定义。
2. **代理主键**：所有资源表 `id` 为不可变 BIGINT identity；外键引用 `id`，不引用名称。
3. **大小写敏感唯一性（三条）**：
   - `cluster.name` 全局唯一；
   - `(cluster_id, hostname)` 在 `bare_metal` 上唯一；
   - `(cluster_id, ip_address)` 在 `ip_address` 上唯一。
   - 三条都必须表达为 **partial unique index**（`WHERE deleted_at IS NULL`）。
4. **`ip_address.cluster_id` 反规范化（REQUIRED）**：IPAddress 的直接父是 NetworkInterface，但唯一性边界是 Cluster。必须在 `ip_address` 上落一个 `cluster_id` 列（由后端从 NIC→BareMetal→Cluster 推导写入），并有机制保证其与链路上游一致，否则 §21 的「同 Cluster IP 冲突必须在保存前阻止」无法由数据库保证。
5. **逻辑删除**：`deleted_at` 列贯穿所有资源表；常规查询一律带 `deleted_at IS NULL`。
6. **状态约束**：`bare_metal.status` NOT NULL DEFAULT `'IDLE'` + CHECK IN 四值。
7. **枚举落点**：`technology_type` / `purpose` 在 V1 用 CHECK 约束或参考表表达（Database 决定），但必须能表达 `domain-model.yaml` 中已确认的完整枚举集。
8. **索引**：外键列索引；按 Cluster 的列表查询索引。
9. **Migration 策略**：版本化、向前、随代码提交；F012 建立基线 migration；破坏性变更需单独说明（`AGENTS.md` §6）。
10. **字符集**：数据库 / 表 / 连接统一 UTF-8。

---

## Backend Work

能力级描述，不含实现：

- **F012 基座**：应用骨架、配置、DB 连接池、统一请求校验、统一错误信封、分页约定、软删除过滤基座、事务边界约定、健康检查。
- **F013**：本地账号模型、口令哈希、登录 / 登出、会话建立与校验、认证中间件、初始管理员初始化方式。
- **F014**：统一逻辑删除领域服务（父有活跃子则拒绝、不级联、软删过滤）、并发安全的父子完整性检查、唯一冲突到 HTTP 语义的映射。
- **F001 ~ F010**：各资源 CRUD 与查询；每条写入路径复用与页面录入**同一套**领域校验（R-IMPORT-002 的复用前提）。
- **F011**：Excel 解析 → 行级校验管线 → 逐行错误聚合（`row` / `field` / `code`）；partial success 待 OPEN-005 确认。
- 认证保护所有 `/api/*`（登录端点除外）。

---

## Frontend Work

- 登录页（F013）：表单、认证失败提示、会话失效跳转。
- Cluster 列表 / 详情（F001、F009）：详情含 BareMetal 列表与状态；**空态与不存在态必须在 UI 上可区分**（R-QUERY-004）。
- BareMetal 列表 / 详情（F002）。
- NetworkInterface / IPAddress 管理（F004、F005）。
- VirtualMachine / Container / Service 管理（F006 ~ F008）。
- 资源详情与关联视图（F010）：不要求用户跨多个 Excel 式页面手工拼接（R-QUERY-003）。
- Excel 导入页（F011）：模板下载、上传、逐行错误展示。
- 所有页面统一处理 **Loading / Empty / Error / Forbidden / Not Found** 五态；错误用后端 `error.code` + `error.details` 渲染，**前端不重复实现业务规则**（§21）。

---

## API Contract

### Status

```text
BLOCKED
```

三项真实阻塞：

1. 本契约本身是 `PROPOSED`，需用户批准 DEC-014 后才稳定。
2. **导入端点的成功 / 部分成功语义被 OPEN-005 阻塞**（R-IMPORT-004 明确禁止自行决定）。
3. `docs/api/` 尚未完整落盘，端点集合与 DEC-009 技术栈强耦合。

通用规范见 `docs/api/api-conventions.md` 与 `docs/architecture/adr/adr-0003-resource-identity-and-api-contract.md`。

---

## Test Work

1. **大小写敏感唯一性**：`cluster-a` 与 `Cluster-A` 可共存；`cn001` 与 `CN001` 在同一 Cluster 内可共存；**直接对数据库插入（绕过应用）时同样被拒绝**。
2. **跨 Cluster 可重复**：不同 Cluster 可有相同 hostname 与相同 IP。
3. **软删除不占唯一性**：删除 `Cluster-A` 后可重新创建 `Cluster-A`（R-DELETE-006）；已删记录不出现在常规查询（R-DELETE-002）。
4. **父删子拦**：Cluster 有活跃 BareMetal 时删除返回 409；**并发场景**下不产生孤立子资源。
5. **不级联**：删除父资源不自动软删子资源（R-DELETE-005）。
6. **IP 唯一性边界**：`ip_address.cluster_id` 与链路推导结果保持一致，不一致数据应被拒绝。
7. **状态约束**：`status` 非空、默认 `IDLE`、拒绝 `null` 与非法值（R-BM-003 ~ 005）。
8. **API 契约**：Empty（200 空集合）与 Not Found（404）语义；错误信封字段；状态码映射。
9. **导入校验与页面一致**：同一非法数据经页面与经 Excel 得到同等判定；错误含 `row` / `field` / `code`（R-IMPORT-003）。
10. **中文往返**：含中文的数据写入 / 读取 / 等值比较正确。
11. **认证**：未登录访问受保护接口 401；口令哈希为 Argon2id 且明文不落库、不落日志。

---

## Technical Decisions

### CONFIRMED

- V1 不含 DataCenter；BareMetal 直接上级为 Cluster（`requirements.md` §6 / §13）。
- 仅 BareMetal 有状态；其余资源无状态字段（Q-002=B）。
- 三条唯一性规则 + 大小写敏感（§22）；Cluster 名称不得含 `/`（R-CLUSTER-005）。
- 逻辑删除六条规则（R-DELETE-001 ~ 006）。
- 禁止 EAV / 通用 `resources` 表 / STI / ORM 多态继承 / JSONB 万能模型（§4 / §24）。
- 禁止微服务化；部署为独立内网虚拟机 + Internal IP + HTTP（§20 / §23）。
- 本地账号认证，不接 LDAP / AD / OAuth / SSO，不扩大为复杂 RBAC（§19）。
- 关键唯一性 / 完整性必须在 Backend / Database 有真实保护，不能只依赖 UI（§21）。
- Excel 导入必须与页面录入执行一致校验（R-IMPORT-002）。

### REQUIRED

- 标识列必须是**大小写敏感**比较；不得依赖数据库实例默认 collation（MySQL 8 默认 `utf8mb4_0900_ai_ci` 会破坏 R-CLUSTER-002 / R-BM-002 / §22）。
- 唯一性约束必须表达为「仅对当前有效记录生效」，使 R-DELETE-006 成立。
- `ip_address` 必须持久化 Cluster 归属，才能在同一 Cluster 内保证 IP 唯一（R-IP-001 / 003）。
- 父资源删除检查与子资源创建检查必须在同一事务内、对父行加锁（R-DELETE-004 的并发正确性）。
- 所有常规查询必须显式过滤已逻辑删除记录（R-DELETE-002）。
- 数据库与连接字符集必须支持中文（UTF-8）。
- UNCONFIRMED 关系（VM→BareMetal、Container→载体）在 Schema 中不得固化为 NOT NULL。
- 错误响应必须能承载「行 + 字段 + 原因」（R-IMPORT-003）。
- 集合查询必须能区分「父不存在」与「父存在但无子资源」（R-QUERY-004）。

### PROPOSED

- 技术栈：Python + FastAPI + Pydantic + SQLAlchemy 2.x + Alembic（DEC-009）。
- 前端：Vue 3 + TypeScript + Vite + Element Plus（DEC-009）。
- 数据库：PostgreSQL（DEC-010）。
- 主键：BIGINT identity 代理主键 + 名称寻址只读别名（DEC-011）。
- 软删除：`deleted_at TIMESTAMPTZ NULL` + partial unique index（DEC-012）。
- 认证：服务端会话表 + HttpOnly Cookie + Argon2id（DEC-013）。
- API：Problem 风格错误信封 + 稳定 `code`（DEC-014）。
- 分页：`page` / `page_size` + `{items, total, page, page_size}`。
- 部署打包：systemd + nginx（备选 docker-compose）。
- 在 F012 内先交付「可运行验证骨架」（见下）。

### OPEN

- 资源规模假设未定（BQ-1）。
- 部署打包方式最终形态（BQ-4）。
- 前端组件库最终选择（若组织已有偏好可替换）。
- 是否对标识列做 Unicode NFC 规范化（当前默认不做）。
- Excel 部分成功策略（OPEN-005，产品）。
- VM / Container / Service / BareMetal 硬件字段（OPEN-001 ~ 004，产品）。

---

## Risks

1. **默认 collation 陷阱（高）**：若未显式指定大小写敏感 collation，R-CLUSTER-002 / R-BM-002 / §22 会被静默破坏。
2. **partial unique index 与数据库选型的耦合（中）**：MySQL 不支持 partial index，会使软删除 + 唯一性需要 sentinel 或生成列技巧。
3. **HTTP 明文（中）**：R-DEPLOY-003 明确接受 Internal IP + HTTP，口令与会话 Cookie 在内网明文传输。这是**已确认的产品取舍**，不是架构缺陷，但必须记录并在部署文档中提示内网边界要求。
4. **未知规模（中）**：缺少资源数量与并发假设。
5. **导入契约被 OPEN-005 阻塞（中）**：F011 无法在 M5 前定稿成功语义。
6. **产品 OPEN-001 ~ 004 影响字段范围（低~中）**：F002 / F006 / F007 / F008 为 DRAFT，DDL 字段待定；架构骨架不受影响。
7. **事务内并发完整性（中）**：父删子拦若只做「先查后删」在并发下会失效。

---

## Constraints

1. 不得引入微服务、消息队列、Redis、Event Bus、CQRS、Kubernetes、Elasticsearch —— 无任何已确认需求支撑（§23）。
2. 不得为「未来可能需要」建立通用资源抽象（`UniversalResource` / `ResourceGraph` / `GenericAssetEntity` / 万能关系引擎）。
3. 不得为 Cluster / VM / Container / Service / NetworkInterface / IPAddress 增加状态字段。
4. 不得在 Schema 中隐藏产品规则：唯一性必须显式、可查、可测。
5. 不得把 UNCONFIRMED 关系（VM→BareMetal、Container→载体）实现为必选。
6. 不得自行改写 R-CLUSTER-005、唯一性范围或删除语义。
7. 不得把 `service.cluster_id` 设计为直接归属（R-SVC-004 / 006）。
8. 不得使用违反大小写敏感的唯一性实现（如 MySQL 默认 CI collation、`lower(name)` 上的唯一索引）。
9. DB / API Contract 为单一权威来源；不得在代码中另立一套约定。
10. 本次不实现代码、不改数据库、不执行 migration。

---

## Open Technical Questions

### Blocking

- **BQ-1 规模假设缺失** —— `docs/` 与 `project-plan.yaml` 中**没有任何**资源数量或并发用户数信息。见下文假设与阈值。
- **BQ-2 技术栈与六项决策的用户批准** —— DEC-009 ~ DEC-014 全部仍为 `OPEN`。
- **BQ-3 导入 API 的失败语义**受产品 OPEN-005 阻塞。
- **BQ-4 部署打包方式**（systemd+nginx vs docker-compose）未确认；影响 F015 验收与运行文档，不影响数据模型。

### Non-blocking

- 前端组件库最终选型。
- 标识列是否需要 Unicode 规范化。
- 分页是否需要游标式（当前规模判断为不需要）。
- 是否需要 Cluster 名称寻址只读别名（DEC-011 方案 C 子项）。
- 观测性：结构化访问日志与错误日志。
- 数据库连接与备份策略。

---

## Implementation Layers

```text
database: true
backend:  true
frontend: true
```

- **database**：8 张资源表 + 2 张认证表的结构、三条 partial unique 约束、`ip_address.cluster_id` 反规范化与一致性机制、CHECK 约束、索引、F012 基线 migration。交付到 `docs/database/`。
- **backend**：应用骨架、统一校验与错误信封、软删除与完整性领域服务、认证、全部资源 CRUD 与查询、Excel 导入管线。交付到 `backend/`。
- **frontend**：登录、各资源管理页、Cluster 视角查询、资源详情关联视图、导入页，统一五态处理。交付到 `frontend/`。

---

## Implementation Order

```text
Architecture + API Contract（本 Handoff + ADR 批准）
  ├─ Frontend 基座可先行（只需契约稳定）
  └─ Database Design（F012 基线）
        └─ Backend
              ├─ F012 骨架（技术栈验证骨架）
              │     ├─ F013 认证 ─┐
              │     └─ F014 软删/一致性基座
              │                   └─ F015 内网部署
              └─ 资源 Feature：
                    F001 → F002 → F004 → F005
                                     F002 → F006 → F007 ─┐
                    F001 + F002 + F006 + F007 → F008 ────┤
                                     F001 + F002 → F009  │
                    F001..F008 → F010 ←──────────────────┘
                    F001..F008 → F011
  ↓ 全部必需分支完成
Tester → Reviewer（按 Feature 逐个走 Git Gate；DONE 判定见 git-workflow.md §6）
```

---

## Verification Strategy

1. **架构层**：ADR 落盘、API 契约落盘、DEC-009 ~ 014 状态从 `PROPOSED` 转为 `CONFIRMED`。
2. **骨架验证（F012）**：见下方「技术栈验证骨架」验收判据。
3. **约束验证**：全部唯一性 / 软删除 / 状态约束用**直接对数据库操作**的测试证明，而非仅经 API（§21）。
4. **契约验证**：前端只依赖契约字段；后端返回结构与文档一致；Empty / Not Found 语义有专门用例。
5. **一致性验证**：并发父删子建用例；`ip_address.cluster_id` 一致性用例。
6. **中文验证**：含中文名称的写入 / 查询 / 等值比较往返用例。
7. **认证验证**：未认证访问 401、会话过期行为、口令哈希算法断言。
8. **导入验证**：逐行错误结构 + 与页面校验一致性；部分成功语义在 OPEN-005 确认后补齐。

---

## 规模假设与阈值

**当前事实**：仓库中**没有任何**关于资源数量或并发用户数的信息。

选型所依据的**显式假设**（若用户给出不同量级必须重新评估）：

| 维度 | 假设量级 |
|---|---|
| Cluster | 10¹ ~ 10² |
| BareMetal | 10³ ~ 10⁴ |
| NetworkInterface | 10⁴ |
| IPAddress | 10⁴ ~ 10⁵ |
| VirtualMachine / Container / Service | 各 10³ ~ 10⁴ |
| 并发用户 | ~10 人，低频 CRUD 与查询为主 |
| 总数据量 | ≤ 10⁶ 行，单机 PostgreSQL 完全可承载 |

**阈值**：若任一资源类型预期超过约 **10⁷ 行**，或出现持续高并发写入，则需重新评估数据库选型（分区、独立 DB 主机、异步导入）。该阈值一旦被突破，DEC-010 需要重审，而那是回退代价高的决策，因此规模量级需用户确认。

---

## 关键技术机制：大小写敏感 + 已删不占唯一性

这是**两个正交机制**的组合，必须同时配置：

**1. 大小写敏感 —— 由 collation 保证，不能由应用逻辑保证**

- 标识列（或唯一索引）显式声明大小写敏感的确定性 collation，使 `cluster-a` ≠ `Cluster-A`。
- 反面教材：MySQL 8 默认 `utf8mb4_0900_ai_ci` 与 SQL Server 默认 collation 都大小写不敏感；沿用默认会**静默违反 R-CLUSTER-002 与 §22**。
- 不得使用 `lower(name)` 上的唯一索引 —— 那等于把规则改成大小写不敏感。

> **核验补充（协调器）**：PostgreSQL 的 `text` 等值比较在标准 locale 下**本身已是大小写敏感**（`'a' = 'A'` 为 false），与 MySQL 的 `ai_ci` 默认不同。因此「显式 collation」的价值是**显式化、与 locale 无关、跨环境可复现**，而不是 PG 缺省行为不正确。需要注意的副作用是：若选用 `COLLATE "C"`，排序将按 UTF-8 码点而非拼音，中文列表排序语义会变化。是否强制显式 collation、以及选哪个，请一并确认（详见 ADR-0002 §Decision 2）。

**2. 已删不占唯一性 —— 由 partial unique index 的 predicate 保证**

```sql
-- 示意，非最终实现
CREATE UNIQUE INDEX ux_cluster_name_active
  ON cluster (name) WHERE deleted_at IS NULL;
```

已逻辑删除的行不进入索引，因此同一名称可被重新创建（R-DELETE-006），同时历史行仍在表中（§25）。

两者互不干涉：collation 决定「两个字符串算不算同一个」，predicate 决定「哪些行参与约束」。

**附加注意**：

- 唯一索引的 predicate 必须与常规查询的过滤条件（`deleted_at IS NULL`）保持一致，否则会出现「查询看不到、写入却冲突」的错位。
- `ip_address` 的唯一键是 `(cluster_id, ip_address)`，而 IPAddress 的直接父是 NetworkInterface；因此必须在 `ip_address` 上**反规范化一个 `cluster_id` 列**，否则数据库无法直接约束 R-IP-001。
- Unicode 规范化（NFC / NFD）当前**不做处理**（无产品规则）。

---

## 技术栈验证骨架（F012 的验收内容，非独立 Feature）

**不属于新 Feature**，而是 F012 的验收内容之一，用于在投入资源建模前暴露技术栈风险。

**验收判据**：

1. 应用可在目标内网虚拟机（或等价环境）以 Internal IP + HTTP 启动，`GET /api/health` 返回 200。
2. 数据库连接可用，**基线 migration 可应用、可重复应用、可从空库重建**。
3. 建立一张显式资源表（建议直接用 `cluster`），验证：
   - 大小写敏感 collation 生效：`cluster-a` 与 `Cluster-A` 可共存；
   - partial unique index 生效：软删后可重建同名记录；
   - **直接对数据库插入重复数据时被拒绝**（不依赖 API）。
4. 统一错误信封生效：一次字段校验失败返回 `400` + `details[].field`。
5. 一个资源可完成 create → list → get → update → soft delete 端到端往返，删除后不出现在 list 中。
6. 前端可构建，并能调用该 API 渲染列表的 Loading / Empty / Error 三态。
7. 本地开发与运行方式有文档，可依文档在 30 分钟内启动。
8. 代码规范与最小测试可执行（lint + 一个真实断言数据库约束的测试）。

**核心目的**：第 3 与第 4 条直接验证本架构最容易「选错就难以回退」的两处 —— collation 语义与软删 / 唯一性交互。若验证失败，应在 M1 投入前修正 DEC-010 / DEC-012，而不是等到 M2。

---

## 相关 ADR

| ADR | 主题 | 覆盖决策 |
|---|---|---|
| [`adr-0001`](adr/adr-0001-tech-stack-and-deployment.md) | 技术栈、模块边界与部署形态 | DEC-009 |
| [`adr-0002`](adr/adr-0002-database-selection-and-uniqueness.md) | 数据库选型、大小写敏感唯一性与迁移策略 | DEC-010 |
| [`adr-0003`](adr/adr-0003-resource-identity-and-api-contract.md) | 资源标识、URL 寻址与 API / 错误响应契约 | DEC-011、DEC-014 |
| [`adr-0004`](adr/adr-0004-soft-delete-and-uniqueness-release.md) | 逻辑删除的持久化与唯一性释放 | DEC-012 |
| [`adr-0005`](adr/adr-0005-local-authentication-and-session.md) | 本地账号认证与会话 | DEC-013 |

---

## Handoff Status

```text
NOT READY FOR IMPLEMENTATION
```

**放行条件**：

1. 用户批准 DEC-009 ~ DEC-014，并将对应 ADR 状态由 `PROPOSED` 改为 `ACCEPTED`；
2. BQ-1（规模量级）、BQ-3（OPEN-005）、BQ-4（部署打包方式）得到回答；
3. API Contract Status 单独满足（需先解除 OPEN-005）。

满足后本 Handoff 状态可改为 `READY FOR IMPLEMENTATION`。