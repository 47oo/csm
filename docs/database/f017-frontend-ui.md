# F017 前端 UI 体系改造（Ant Design + Tailwind CSS）— DATABASE 阶段报告

- **Task**：F017 前端 UI 体系改造（Ant Design + Tailwind CSS）— Database（Feature 设计模式），范围 = 数据模型/约束/索引/迁移裁定。
- **Status**：`READY FOR DATABASE IMPLEMENTATION`（无数据库实现工作；本 Feature `database: NOT_REQUIRED`）
- **Basis**：
  - `docs/product/requirements-v3.md` revision 4 CONFIRMED（§26 PostgreSQL / SQLAlchemy 2.x / Alembic 为已确认技术输入；§28/§29 前端展示层；§30 部署）。
  - `docs/features/F017/architecture.md`（2026-10-15，`READY FOR DESIGN`；§4 layers `database:false`、`api_required=false`；§2.2 `backend/**`、`docs/database/**` 不改动；§6.3 Rollback 无 DB Migration）。
  - `docs/features/F017/product.md`（`READY FOR ARCHITECT`；§1.4 明确排除项：无 Schema/Migration；§2.2 不改变业务规则）。
  - `docs/project/project-plan.yaml` plan_revision 5（用户 2026-10-12 批准；F017 `layers={database:false,backend:false,frontend:true}`、`implementation.database=NOT_REQUIRED`、`not_required.database=纯展示层改造，无新表/列/约束/索引/迁移`）。
  - 现状（只读）：`backend/alembic/versions/`（13 个版本，单 head `0013_search_indexes`）；`frontend/src/**` F017 影响清单（架构 §2.1）。
- **设计检查输入**：Product `READY FOR ARCHITECT` + Architect `READY FOR DESIGN` 已具备；无阻塞，可作 NOT_REQUIRED 裁定。
- **完整性方法**：`.pi/skills/data-integrity/SKILL.md`（本 Feature 无约束到实现映射需求）。

## 1. 裁定结论

F017 为**纯展示层前端改造**，经复核**无新表 / 新列 / 新约束 / 新索引 / 新触发器 / 新迁移**，不涉及已有数据升级、回填或兼容性破坏。裁定 **`database: NOT_REQUIRED`**，与 plan_revision 5 `layers.database=false` 及架构 §4 一致。

## 2. 逐项核对（DB-D177–DB-D180）

| ID | 核对项 | 结论 | 依据 |
| --- | --- | --- | --- |
| DB-D177 | 新增/变更表、列、类型、必填性、默认值 | 无 | 架构 §2.1 文件清单仅含前端文件；§2.2 未列 `backend/**`；product §1.4 排除 Schema |
| DB-D178 | 新增/变更 PK/FK/UNIQUE/CHECK/NOT NULL、触发器、函数 | 无 | 同上；无领域对象变化（product §2.3 无领域影响） |
| DB-D179 | 新增/变更索引 | 无 | 同上；`frontend/src/api/*.ts` 冻结，不改查询形状 |
| DB-D180 | Alembic 迁移链 / 单 head 受影响 | 不受影响，保持单 head `0013_search_indexes` | 见 §3 |

## 3. 迁移链复核（DB-D180）

- `backend/alembic/versions/` 共 13 个版本，构成**单一线性链**：
  `0001_baseline → 0002_users_sessions → 0003_clusters_audit → 0004_resources → 0005_bare_metal_details → 0006_virtual_machine_details → 0007_interfaces → 0008_networks → 0009_ip_pools → 0010_ip_addresses → 0011_services → 0012_service_endpoints → 0013_search_indexes`。
- 无任何版本的 `down_revision` 指向 `0013_search_indexes`，即**单 head = `0013_search_indexes`，线性无分叉**。
- F017 不新增/修改任何版本文件，不触发 `upgrade`/`downgrade`/回填；`alembic current` 与 `alembic heads` 结果不受本 Feature 影响。

## 4. 生命周期、约束与并发影响

- 无领域对象、关系、状态、唯一性或生命周期变更（product §2.3；requirements §4–§24 不变），故无引用删除限制、类型明细生命周期、Pool 来源关系或恢复冲突的新裁定。
- 架构 §6.3 Rollback：无 DB Migration、无数据恢复动作，回滚仅撤销 F017 前端提交并重部署上一 `dist`。
- 并发/乐观锁/软删除/导入等持久化语义全部不变；`frontend/src/api/` 零改动（F-UI-4d）。

## 5. Backend / Frontend 可依赖的保证

- 数据库 Schema 与 F001–F015 已签核设计**完全一致**；F017 期间及之后无 DDL 变更，无向后兼容顾虑。
- 前端不引入任何直连数据库假设；接口契约零变更（`api_required=false`）。
- 现有迁移链单 head 可作为 F018 复验基线，无需迁移操作。

## 6. 验证计划（本设计无 PASS，只读裁定）

- V-DB-F017-1：`alembic heads` 输出单 head=`0013_search_indexes`；`backend/alembic/versions/` 无新增文件。
- V-DB-F017-2：`git diff` 范围内无 `backend/**`、`docs/database/**` 之外的数据层改动（F017 文件清单限定于前端）。
- V-DB-F017-3：Schema 不变断言（无新增/变更表、列、约束、索引、触发器）。
- 说明：以上为计划验证项；F017 无数据库执行工作，不产生 Schema 变更 PASS。

## 7. 未决 / 交核

- None（Database 侧无 Blocking）。后续若 F017 实施中意图改动任何数据库对象或迁移，须停止并返回架构/变更控制重新评估（架构 §6.2 R7、AGENTS §6）。

## 8. 设计版本历史

| 版本 | 日期 | 变更 |
| --- | --- | --- |
| v1 | 2026-10-15 | 初次裁定：`database: NOT_REQUIRED`；DB-D177–DB-D180；依据架构 v1 / plan_revision 5。 |