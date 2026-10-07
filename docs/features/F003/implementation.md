# F003 Cluster 管理与持久化横切首落地 — 实现报告

实现提交记录于 feature/F003-cluster-management。本文件由协调器持久化实现交接，作为 implementation 证据。

---

## Backend 实现报告（BACKEND COMPLETE）

### 实现范围（backend/**）

- 迁移 `alembic/versions/0003_clusters_audit.py`：clusters + audit_logs（列/约束/索引/触发器；down_revision=0002_users_sessions；up/down 对称）。
- 模型：`app/models/base.py` 新增 SoftDeleteMixin；`app/models/cluster.py`（meta 映射列 metadata）；`app/models/audit_log.py`；`app/models/__init__.py`。
- 软删过滤：`app/core/db.py` Session 上 do_orm_execute + with_loader_criteria(SoftDeleteMixin, deleted_at IS NULL, include_aliases=True)；execution_options(include_deleted=True) 绕过；对 users/audit_logs 无影响。
- 归一化：`app/services/normalization.py`（code trim/非空/无内部空白与控制字符/≤64，code_key=仅 ASCII 字母折叠（`translate`，locale 无关；v2 修复 F003-REV-1）；name trim/非空/无控制/≤255，保留内部空格大小写）。
- 审计：`app/services/audit.py`（同 Session；operator→operator_user_id+operator_username 快照；白名单快照；JSONB none_as_null 保证无快照存 SQL NULL）。
- Cluster Service：`app/services/cluster.py`（CRUD、列表过滤/排序/分页/模糊、全量唯一、条件 UPDATE 乐观锁、软删/恢复、引用与依赖检查注册表（空集）、Activity）。
- 错误：`app/core/errors.py` 新增 Conflict（409，reason 枚举 + field/references/conflicts）。
- Schema/API：`app/schemas/cluster.py`、`app/api/v1/clusters.py`（7 端点）、router 挂载。
- 测试：`tests/integration/test_clusters.py`、`test_cluster_constraints.py`；泛化 F002 迁移 head 断言。

### Contract 符合情况

- code：trim 存展示列、code_key 仅 ASCII 字母折叠（`translate`）全量唯一（含软删）、不可改（PATCH 含 code→422 + DB 触发器 trg_clusters_code_immutable 兜底）、允许中文。
- name：trim/非空/无控制字符/允许内部空格与重复；PATCH 省略保持、显式 null→422、description 显式 null 清空、metadata 整值替换。
- 列表：status/code/q AND；sort∈{code,name,status,created_at,updated_at}（code 按 code_key）；order；page/page_size 边界 422；id 升序稳定；默认含未删 ACTIVE+INACTIVE。
- 软删可见性：deleted=exclude|include|only，include/only 需 VIEW_DELETED 否则 403；详情/Activity 已删需 ?deleted=true+VIEW_DELETED 否则 404。
- 权限：READ/WRITE/DELETE_OBJECT/VIEW_DELETED/RESTORE/VIEW_ACTIVITY；未认证先于权限 401。
- 乐观锁：PATCH/DELETE/restore 条件 UPDATE WHERE id AND version=:expected，rowcount=0→409 VERSION_CONFLICT{current_version}/404。
- 错误信封扩展 CONFLICT；操作者取 request.state.operator。

### 迁移影响

0003_clusters_audit（单一 head）：先 clusters（索引+code 不可改触发器）后 audit_logs（FK→users RESTRICT + append-only 触发器）；down 逆序。无回填；生产回滚用 F001 备份（迁移 docstring 记录）。

### 验证证据（实际执行）

- docker build --target test 成功；真实 PG `pytest tests -v` → **76 passed, 1 skipped**（skip=F001 V3b 非 superuser 扩展，环境限制）。
- 独立迁移库：alembic heads → 0003 (head)；upgrade head→downgrade 0002→downgrade base→upgrade head，current=0003 (head)，各步 OK。
- 覆盖 TD-1 A1–A9/B1–B42 子集：code 大小写/空白重复与软删重建 409、PATCH code 422、name 规则、status/列表/排序/分页/模糊/非法 422、软删默认隐藏与权限 403/404、ADMIN 恢复与 not_deleted 409、Audit 四 action+同事务回滚不留痕+Activity、乐观锁两会话 409、RAW SQL 约束/索引/触发器/FK/UUID 断言、引用/依赖检查机制级、迁移 up/down/up。

### 未验证项

F003 无 ORM 关系，TD-1 B41（软删过滤覆盖关系加载）无适用对象；恢复冲突 unique_conflict/dependency_deleted 为机制级；未执行 Compose 全链路/前端 V14/入口 Nginx 真实 API 集成；并发为 service 层两真实会话非两路 HTTP；V3b skip。不等同完整 T24/T25/T26 通过。

Git 声明（只读）：git branch --show-current、git status --short、git diff --stat、git ls-files --others --exclude-standard。

---

## Frontend 实现报告（FRONTEND COMPLETE）

（待前端实现完成后由协调器补全）
