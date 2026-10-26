# F036 F032–F035 Review 跟进项收敛 — IMPLEMENTATION 阶段报告

- **版本**：v1（2026-10-26）；plan revision 22；需求 revision 14（不变）
- **状态**：DATABASE `NOT_REQUIRED` 已确认；BACKEND / FRONTEND 待实施（见 §1、§2 占位）。

## 1. Backend

（待实施后填写：DR-F036-01 `_app_error_field` 词表映射、DR-F036-07 T79 CLI 用例、DR-F036-08 测试产物落点、DR-F036-10 注释）

## 2. Frontend

（待实施后填写：DR-F036-02 载体切回 file 清空、DR-F036-03 记忆化、DR-F036-04 placeholder 常量、DR-F036-05 窄屏焦点环、smoke 期望同步）

## 3. Database（NOT_REQUIRED 确认）

Database（2026-10-26，F036 DATABASE Gate）结论 **`DATABASE NOT_REQUIRED CONFIRMED`**（`layers.database=false`），四项判定：

1. **零表/列/索引/约束/触发器/Migration**：唯一后端改动为 `_app_error_field` 词表 +1（`"resource": "hostname"`，纯字符串映射）；`_lock_resource` / `_attribute_integrity` / `_acquire_locks` 零 diff；`alembic head` 仍 `0015`（守卫归 V14）。
2. **词表不需 DB 支持**：`RowError.field` 是响应字段取值（冻结模板列名），DB 不参与归因；23505 / CHECK / 触发器仍由 `_attribute_integrity` 按 `diag.constraint_name` + 消息口径归因（F023-DB-02 不变）。
3. **并发软删由既有行锁 + 读侧校验兜底，归因属应用层**：`_lock_resource` 以 `include_deleted=True` 取 `FOR UPDATE`，获锁后重读 `deleted_at` → `_field_error("resource", …)` → 整批 422。DB 提供的是既有 PK 行锁的串行化与 READ COMMITTED 获锁后重读语义，非新增对象。不能表达为数据库不变式的理由：`resources.deleted_at` 经软删入口合法变更；FK RESTRICT 只证行存在（软删行仍在）；部分唯一索引只约束未删行标识唯一；CHECK/触发器无法区分「宿主随后被合法软删」与「追加非法」——与 `docs/database/f023-import.md` §5.5 同型（入口级行为规则）。
4. **足以支撑 V2 断言**：422 来自应用层 AppError 路径；零写入由 `write_import` 的 `db.rollback()`(:1539，T123) 保证；三条部分唯一索引（均 `WHERE deleted_at IS NULL`）只仲裁 23505 身份冲突，与本场景正交。

无回填、无升级动作、无回滚风险（退回仅撤销词表一行，无数据状态需还原）；无新索引（§5.6 查询谓词与既有部分唯一索引完全匹配）。

**Issue 状态**（`docs/database/f023-import.md` §5.9）：`F023-DB-01` CLOSED（不变，`_acquire_locks` 零 diff）；`F023-DB-02` / `F023-DB-03` 继续有效；`F035-DB-NOTE-01` 继续有效；**新增 `F036-DB-NOTE-01`**（NOTE）：`RowError.field` 的并发软删归因标签 `resource` → `hostname` 属应用层/契约层措辞修正（F023 v2 §11 澄清），不改 DB 对象、不改约束归因口径、不引入新不变量。

**环境前提（交 Tester）**：V2 的 422 期望以 PG 默认 **READ COMMITTED** 为前提（`core/db.py` 未设 `isolation_level`）；若测试会话为 REPEATABLE READ，同一竞争返回 40001 → 500 `INTERNAL_ERROR`（既有行为，F036 未改），V2 须记录隔离级别。

**观察项（非阻塞，交 Architect）**：`docs/database/f023-import.md` §5.7 第 6 项字面「预校验→写入间宿主被软删 ⇒ 报错需要 DB 侧支持」与 F035 已交付实现（既有 `FOR UPDATE` + 读侧校验，无需 DDL，§5.8 已如此记载）存在读法差异；建议在 CONTRACT §12 记录该读法。两种读法下 F036 均零 DDL。
