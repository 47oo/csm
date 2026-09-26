# F001 集群登记、身份、真实删除保护与集群本体权限审计 — 架构方案

> Status: READY FOR IMPLEMENTATION
> Document Type: Feature Architecture
> Feature: F001（Epic E1，P0）
> 依据：`requirements-v2.md` §2.1/§3.1/§4.1/§4.4/§6.1/§9.1、§10 场景 50/51/58/59/61/64/71/82、§11.1 BQ-M/BQ-V/BQ-W/BQ-Z；
>      `domain-model.md` §1/§2/§3/§5/§6；ADR-001…ADR-005；复用 `docs/architecture/F013-user-role-management.md` §2.2/§2.3/§4；
>      `docs/project/project-plan.yaml` F001
> 关联 Contract：`docs/api/F001.md`（唯一字段清单）
> 创建日期：2026-09-25

本文件只记录实现层架构方案。产品/领域事实以 `docs/product/` 为准；技术栈、数据库、API、部署、历史审计载体以 ADR 为准。标记：`CONFIRMED` / `PROPOSED` / `OPEN`。

---

## 1. 方案摘要

F001 在 ADR 既定架构内新增一个受管对象模块「集群」，交付：

1. 集群 `code` / 名称 / 用途的登记、列表、详情与编辑（`code` 创建后不可改，名称/用途可改）；
2. 集群身份稳定：`code` 全局判重（含已真实删除者）、真实删除后永不复用；名称仍存集群内区分大小写唯一、真实删除后可复用；
3. 集群真实删除与关联保护规则（仍存计算资源/网段/服务关联须先显式处理、不级联；仅余历史已解除关联不阻止）；
4. 真实删除二次确认（BQ-Z）：须按提示输入集群名称或 `code` 匹配后才可提交；
5. 集群本体最小服务端鉴权：查看者只读；维护者/管理员可真实删除（仍受关联保护）；新增/编辑仅平台管理员；
6. 集群操作审计与删除/变更资源历史写入（append-only）；
7. 复用 F013 交付的平台角色/操作者解析与会话基础，**不自行交付登录**。

集群作为计算资源/网段/服务的归属（`cluster_id`）由后续 Feature 建 FK 引用；F001 只交付归属目标与删除保护规则侧。集群列表/选择并记住本次选择属于前端状态，不作为授权边界（§2.1）。

**复用 F013 依赖（不复制实现，`CONFIRMED`）**：
- `app.security.principal.get_current_user` → `Principal{user_id, username, role, must_change_password, status}`；
- `app.security.principal.require_roles(*roles)` → 越权 403；
- `app.audit.write(db, actor, action, target_type, target_id, target_key_snapshot, change, result)`（append-only）；
- `app.errors.problem(...)` / problem+json 统一错误体；`app.db.get_db`。

---

## 2. 模块边界

### 2.1 后端模块（Python 3.12 + FastAPI，ADR-001）

| 模块 | 职责 | 明确的非职责 |
| --- | --- | --- |
| `app.clusters`（集群本体） | 集群列表/新增/详情/编辑/真实删除；`code` 规范化与判重；名称校验与唯一；用途维护；关联保护映射；写审计与资源历史 | 不实现登录/会话/角色判定（依赖 `security.principal`）；不实现其他对象鉴权/审计（F002/F005/F006/F007）；不做聚合计数（F010）；不提供资源历史查询（F012） |
| `app.clusters.normalize`（小工具） | `normalize_cluster_code(raw)->str`：去首尾空格 + 统一大写；判重与二次确认比较统一使用 | 不改变展示形态；不做格式定义以外的业务判断 |
| `app.clusters.models` | `Cluster`、`ReservedClusterCode` 映射（Schema 由 Database 设计） | 不定义其他 Feature 的表 |
| 复用 `app.security.principal` | 操作者解析与三角色鉴权 | 见 §1 |
| 复用 `app.audit` | 操作审计写入 | 不写/不查受管资源历史查询 API |
| 复用 `app.errors` / `app.db` | 统一错误体、会话 | — |
| 共享历史载体 `resource_history`（模型由 F001 Database 设计，写入接口 `app.resource_history.write(...)`） | 受管对象删除/变更历史 append-only 写入（ADR-005） | 查询由 F012 交付；本 Feature 不提供查询 API |

模块依赖方向：`clusters → security.principal`、`clusters → audit`、`clusters → resource_history`。禁止 `clusters` 反向依赖 `users`（只依赖 `security.principal`），与 F013 §2.1 约束一致。

### 2.2 关联保护实现边界（`CONFIRMED` 规则，`PROPOSED` 机制）

- 需求 §4.1.9/§4.4 要求集群仍有关联时拒绝删除、不级联。**F001 定义规则与 409 语义**；具体关联对象由后续 Feature 建立。
- 机制（`PROPOSED`，最小实现，不预建注册框架）：每类仍存关联表（计算资源、网段、服务—集群关联等）对 `clusters(id)` 建 **`ON DELETE RESTRICT` 外键**（AGENTS §6 要求 DB 保证的重要完整性不靠应用兜底）。F001 删除时捕获 PostgreSQL `SQLSTATE 23503`（外键冲突）→ 映射 `409 CLUSTER_HAS_ASSOCIATIONS`。
- **历史载体不得对 `clusters(id)` 建阻塞外键**（`resource_history`、`audit_log` 用 `target_id text`、无 FK），保证「仅余历史已解除关联不阻止删除，历史保留」。
- F001 实现期尚无关联表，删除空关联集群必然成功（即场景 71 独立闭环）；关联保护的行为侧在 F002/F005/F007 引入引用后由各自 Feature 验收（计划 §51 最终闭环归 F007）。更细的“列出具体关联对象”提示由引入关联的 Feature 提供，F001 只保证 409 码与语义。

### 2.3 前端页面 / 路由 / 状态（Vue 3 + TS + Vite + Element Plus，ADR-001）

| 区域 | 内容 |
| --- | --- |
| 集群列表页 `/clusters` | 列表（分页、`q` 搜索、排序）、新增（仅管理员可见按钮）、编辑（名称/用途，仅管理员）、真实删除（含二次确认，维护者/管理员可见） |
| 集群选择 | 顶部/首页集群选择器；`useClusterStore` 保存“本次选择”，持久化到 `localStorage`；刷新后恢复 |
| Pinia `useClusterStore` | `clusters`（列表缓存）、`currentClusterId`；选择只改变查询作用域，**不改变角色权限**（§2.1/场景 40） |
| 路由守卫 | 复用 F013 登录态；未登录跳 `/login`；`must_change_password` 强制改密 |
| axios | 复用 F013 拦截：401→登录、403→提示、problem+json 字段级错误、409→冲突/关联保护提示、422→二次确认不一致提示 |
| 首屏集群恢复 | 记忆的 `currentClusterId` 若已不存在（被真实删除），回退为空并提示重新选择（前端行为，无服务端 API） |

前端权限仅用于导航/隐藏，**不作为安全边界**；最终由服务端校验。

---

## 3. 数据影响（Architect 声明的数据行为，Schema 由 Database 设计）

> 下表声明**必须保障的行为与约束**；列类型/索引名/DDL 由 Database 在 `docs/database/F001.md` 设计并交 Backend 实现。F001 `layers.database=true`。

### 3.1 `clusters`（集群主表）

| 行为 | 说明 | 依据 |
| --- | --- | --- |
| `id` | 稳定主键（`BIGINT`），供后续对象 `cluster_id` 引用 | §4.1.6 |
| `code` | 展示形态：**去首尾空格后的用户输入**（保留大小写，ADR-002） | ADR-002、§4.1.11 |
| `code_key` | 比较键：`upper(btrim(code))`，独立存储（生成列或应用维护，二者必须恒等）；`UNIQUE` 用于仍存集群内判重 | ADR-002、BQ-Z、§4.1.11 |
| `code_key` 格式 | `CHECK (code_key ~ '^[A-Z0-9]{1,32}$')` → 规范化后仅大写字母与数字、长度 1–32 | BQ-Z、§4.1.11、场景 50 |
| `code` 不可改 | 无更新 `code`/`code_key` 的写入路径（编辑接口拒绝 `code` 字段） | §4.1.7/11、BQ-I |
| `name` | 仅字母/中文/下划线/数字，长度 1–64；含空格（首/尾/中）直接拒绝、不裁剪；`name` 本身即比较键（大小写敏感） | §4.1.7、BQ-W、场景 50/58 |
| `name` 唯一 | 仍存集群内 `UNIQUE(name)`（区分大小写）；真实删除后行即删，名称可复用 | §4.1.7、BQ-J/BQ-K、场景 51/58 |
| `purpose` | 用途，可修改；`NOT NULL`、非空字符串 | §4.1.6/7、§6.1 |
| `version` | 乐观锁（编辑/删除条件更新） | ADR-003 |
| `created_at`/`updated_at` | `TIMESTAMPTZ`，更新时间由 Backend 刷新 | 通用 |

### 3.2 `reserved_cluster_codes`（`code` 永不复用的独立保留标识表）

| 行为 | 说明 | 依据 |
| --- | --- | --- |
| 主键 `code_key` | 规范化比较键，**只增不删**；创建集群时**同事务先插入**；冲突（含已真实删除集群用过的键）→ `409 CLUSTER_CODE_TAKEN` | §4.1.7/11/13、BQ-M/BQ-Z、ADR-002/ADR-005 |
| 删除集群不删保留行 | 保证 `code` 跨真实删除永不复用 | ADR-005、场景 51 |
| append-only | 无 UPDATE/DELETE 写入路径（可由触发器强制，`PROPOSED`，与 F013 `reserved_usernames` 同模式） | ADR-005 |

### 3.3 集群历史 / 审计写入（跨 Feature 共享载体）

| 载体 | 行为 | 依据 |
| --- | --- | --- |
| `audit_log`（F013 已建） | F001 以 `target_type="cluster"` 追加操作审计行：`action ∈ {cluster.create, cluster.update, cluster.delete}`；append-only；用户删除后仍可读 | §9.1、ADR-005 |
| `resource_history`（**F001 Database 设计并建表**，跨对象共享） | 受管对象删除/变更历史 append-only：至少操作者 + 删除/变更内容；`target_type`/`target_id`/`change(JSONB)`/`occurred_at`/actor 快照；**无对业务表的阻塞 FK**；管理员可查、长期保留、不自动到期（查询 API 由 F012） | §4.4.4/6、BQ-N/BQ-Q/BQ-V、ADR-005 |
| 写入时机 | 集群 `update` 与 `delete` 写 `resource_history`；`create` 仅写审计 | §4.4.4、场景 61/64 |
| 历史不阻塞删除 | `resource_history`/`audit_log` 不得对 `clusters(id)` 建 `RESTRICT` FK | §4.1.9、场景 51 |

### 3.4 Database 设计与 Backend 实现分工

- **Database**（`docs/database/F001.md`）：设计 `clusters`、`reserved_cluster_codes`、`resource_history` 的列/约束/索引；给出初始化建表补充（P0 无迁移工具，ADR-002）；`resource_history` append-only 表达。**不写业务实现**。
- **Backend**：ORM 映射、`normalize_cluster_code`、创建/编辑/删除事务、唯一与 FK 冲突 → 409 映射、审计与历史写入、初始化建表脚本增量。**数据库实现由 Backend 承担**。

---

## 4. 权限与审计

### 4.1 复用 F013 基础（`CONFIRMED`）

- 每个受保护端点依赖 `get_current_user`；角色与状态每请求读库，角色变更即时生效、禁用后立即不可用（F013 §2.2）。
- 角色判定使用 `require_roles(*roles)`；越权 → `403 FORBIDDEN`，数据不变。
- 首登未改密拦截由 `get_current_user` 统一处理（`403 PASSWORD_CHANGE_REQUIRED`）。

### 4.2 集群本体鉴权规则（服务端）

| 操作 | 允许角色 | 依赖实现 |
| --- | --- | --- |
| 列表 / 详情 | viewer、maintainer、admin | `get_current_user` |
| 新增（POST） | 仅 admin | `require_roles("admin")` |
| 编辑（PATCH） | 仅 admin | `require_roles("admin")` |
| 真实删除（DELETE） | maintainer、admin（仍受关联保护） | `require_roles("maintainer","admin")` |

集群选择只是查询作用域，不是授权边界；切换集群不改变角色权限（§2.1、场景 40）。

### 4.3 审计与资源历史内容

- 统一经 `app.audit.write(db, actor, action, "cluster", str(cluster.id), code, change, "success")`：
  - `cluster.create`：`change={code, name, purpose}`；
  - `cluster.update`：`change={name:{from,to}, purpose:{from,to}}`（仅记实际变化字段）；
  - `cluster.delete`：`change={code, name, purpose}`；
- `resource_history` 写入 `action ∈ {update, delete}`，含操作者快照与变更/删除内容；删除时**先写历史与审计，再执行 DELETE（同事务）**。
- 历史查询与“不自动到期”由 F012 统一提供；本 Feature 不提供查询 API。

---

## 5. API Contract（摘要；唯一字段清单见 `docs/api/F001.md`）

Contract 状态 **READY**。Base：`/api/v1`；错误统一 `application/problem+json`。

| # | Method | Path | 说明 | 角色 |
| --- | --- | --- | --- | --- |
| 1 | GET | `/clusters` | 集群列表（分页/筛选/排序） | 任意已登录 |
| 2 | POST | `/clusters` | 新增集群 | admin |
| 3 | GET | `/clusters/{cluster_id}` | 集群详情 | 任意已登录 |
| 4 | PATCH | `/clusters/{cluster_id}` | 编辑名称/用途（`code` 不可改；乐观锁） | admin |
| 5 | DELETE | `/clusters/{cluster_id}` | 真实删除（二次确认 + 乐观锁） | maintainer/admin |

- 二次确认（BQ-Z）表达为 DELETE 必填查询参数 `confirm`（值须匹配集群名称或规范化 `code`）；不匹配 → `422 DELETE_CONFIRMATION_MISMATCH`。
- 错误码：`400 INVALID_REQUEST`、`422 VALIDATION_ERROR`、`401 UNAUTHENTICATED`、`403 FORBIDDEN`、`404 CLUSTER_NOT_FOUND`、`409 CLUSTER_CODE_TAKEN`、`409 CLUSTER_NAME_TAKEN`、`409 CLUSTER_HAS_ASSOCIATIONS`、`409 VERSION_CONFLICT`、`422 DELETE_CONFIRMATION_MISMATCH`。

---

## 6. Frontend / Backend 工作拆分

**Backend**：`app.clusters`（router/schemas/service/normalize/models）；`resource_history` 写入接口；复用 `security.principal`/`audit`/`errors`/`db`；`normalize_cluster_code`；唯一与 FK 冲突→409 映射；二次确认校验；乐观锁条件更新；初始化建表增量；pytest + httpx 测试。

**Frontend**：`/clusters` 列表页；新增/编辑对话框；真实删除二次确认对话框（须输入名称或 `code`）；`useClusterStore`（选择记忆 + 持久化 + 失效回退）；axios 错误映射；Vitest 单测。

**Database**：按 §3 设计 `clusters`、`reserved_cluster_codes`、`resource_history`；实现由 Backend 承担。

---

## 7. Test Work

**后端集成（pytest + httpx）**：
- `code`：去首尾空格+统一大写判重；`^[A-Z0-9]{1,32}$` 非法拒绝；创建后编辑 `code` 被拒；创建→删除→同 `code` 重建被拒；大小写/空格等价判重。
- 名称：含空格/非法字符拒绝；`ABC` 与 `abc` 允许共存；完全相同拒绝；真实删除后同名可复用；用途可改。
- 删除保护：空关联删除成功（场景 71）；RESTRICT 外键冲突 → 409 CLUSTER_HAS_ASSOCIATIONS；仅余历史不阻止。
- 二次确认：`confirm` 匹配→204；不匹配→422 且不删除（场景 82）。
- 权限：viewer 写/删 403；maintainer 删除允许、写 403；admin 全允许；未登录 401；切换集群不改变权限。
- 审计/历史：create/update/delete 审计行；update/delete 历史行；删除后仍在。
- 乐观锁 409；分页/`q`/空列表。

**数据库约束测试**：`code_key` 唯一与格式 CHECK；`reserved_cluster_codes` 只增不删；`UNIQUE(name)`；`resource_history` append-only。

**前端（Vitest）**：列表、表单校验、删除二次确认、选择记忆与失效回退、错误映射。

**联验（非本 Feature 闭环）**：场景 50 归 F002；51 完整闭环归 F007；58 跨对象改名归属归 F007；61/64 管理员查询归 F012；59 规则侧本 Feature 提供。

---

## 8. 技术决策与风险

**已确认**：栈 ADR-001；PostgreSQL 唯一性 DB 保证、真删 + 独立保留标识表、无迁移工具 ADR-002；REST/problem+json/乐观锁 409/offset 分页 ADR-003；HTTP-only/无备份 ADR-004；审计与历史分表、append-only、管理员可查、长期 ADR-005；`code` 格式与删除确认 BQ-Z；名称口径 BQ-W；F013 复用基础。

**PROPOSED（不阻塞）**：
1. 名称字符集：字母 `[A-Za-z]`、中文 `U+4E00–U+9FFF`，正则 `^[A-Za-z0-9_\u4e00-\u9fff]{1,64}$`；
2. `purpose` 非空、长度上限 200；
3. `code` 展示保留输入形态、比较用 `code_key`；
4. 关联保护用后续表 `ON DELETE RESTRICT` + 23503→409；
5. `reserved_cluster_codes` 触发器只增不删。

**OPEN / 关注（非阻塞）**：
- 名称 Unicode 具体范围、`purpose` 必填/长度可回 Product 复核；
- 关联保护依赖后续 Feature 正确建 RESTRICT FK；
- `resource_history` 为 F001 首次引入的共享载体，F012 查询口径须一致。

---

## 9. Implementation Layers

| Layer | 需要 | 说明 |
| --- | --- | --- |
| database | **true** | `clusters`、`reserved_cluster_codes`、`resource_history` + 约束/索引 + 初始化建表增量；Database 设计、Backend 实现 |
| backend | **true** | 集群模块、规范化、鉴权复用、审计/历史写入、错误映射 |
| frontend | **true** | 集群列表/新增/编辑/删除二次确认、选择记忆、错误映射 |

结论：**READY FOR IMPLEMENTATION**（实现仍须通过独立 Database Design 与 Contract Gate）。