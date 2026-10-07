# F004 Resource 核心登记 — 实现报告

实现提交记录于 feature/F004-resource-core。本文件由协调器持久化实现交接，作为 implementation 证据。

---

## Backend 实现报告（BACKEND COMPLETE）

### 实现范围（backend/**）

- 迁移 `alembic/versions/0004_resources.py`（resources 表 + 约束 + 部分唯一 + 索引 + 触发器；up/down 对称、单一 head）。
- 模型 `app/models/resource.py`（复用 SoftDeleteMixin；meta 映射列 metadata）；`models/__init__.py` 注册。
- 归一化 `app/services/normalization.py` 增 normalize_hostname / hostname_key（ASCII-only translate，禁用 str.lower()）。
- Service `app/services/resource.py`（CRUD、组合过滤 cluster(code)/cluster_id/type/role/status/q(ILIKE)/deleted/分页/排序、部分唯一冲突 409 unique_conflict(field hostname)、cluster 校验 422 field:cluster、条件 UPDATE 乐观锁、软删/恢复（重检 hostname 唯一与 cluster dependency_deleted）、Activity）；`services/audit.py` 白名单新增 resource 七字段。
- 引用检查：注册 cluster←未删除 Resource 检查器（删除 Cluster→409 reference_exists + references）。
- Schema/API `app/schemas/resource.py`、`app/api/v1/resources.py`（7 端点）；router 挂载；cluster 响应嵌套 {id,code,name}。

### 设计符合

f004-resource.md §2–§5（DB-D33–D44）逐项落实：FK RESTRICT；hostname varchar(253)+CHECK（ascii_lower/key_matches/not_blank/trimmed/no_ws_control/length）；hostname_key；resource_type/role/status varchar+CHECK+默认（role OTHER、status UNKNOWN、resource_type 必填）；metadata jsonb object CHECK（ORM meta）；version；deleted_at；**部分唯一 uq_resources_cluster_id_hostname_key (cluster_id,hostname_key) WHERE deleted_at IS NULL**；6 索引含全量 ix_resources_cluster_id；trg_resources_immutable_fields。Contract §4–§6 端点/错误/权限/顺序/嵌套 cluster；cluster 缺失/不存在/软删统一 422 field:cluster；错误码复用 F002/F003。审计（D02）：四 action 同 Session 同 commit，回滚不留痕，object_type="resource"。

既有测试改动：`test_cluster_constraints.py::test_clusters_migration_up_down_up` head 断言由 ==0003 放宽为 >=0003（F004 推进单一 head 到 0004），意图不变。

### 验证证据（实际执行）

真实 PostgreSQL 16（库名含 test）：`pytest tests -q` → **119 passed, 1 skipped**（skip=F001 V3b 非 superuser 扩展，环境性）；`alembic heads` → 0004_resources (head) 单一 head；迁移 up/down/up PASS（downgrade 到 0003 后 resources 及约束/索引/触发器消失、F003 对象保留，re-up 恢复）。覆盖 TD-1 A1–A13 与 B1–B17、B19–B25、B27–B34、B37、B39–B46；B7/B8/B12–B14/B37/B39/B42–B45 经 raw SQL 真实 PG 断言。

### 未验证项

B38 真实双连接并发创建未做独立多线程竞态用例（以 DB 部分唯一 raw SQL 拒绝 + IntegrityError→409 映射单测证明）；B18/B20 过滤/排序为代表性子集；前端 V15 不在本范围；Compose 全栈/Nginx CSRF 端口场景未执行；未用 SQLite/Mock 作证据。

Git 声明（只读）：git status --short、git branch --show-current、git log --oneline -3、git diff --stat。

---

## Frontend 实现报告（FRONTEND COMPLETE）

（待前端实现完成后由协调器补全）
