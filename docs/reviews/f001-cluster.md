# Review Report — F001 Cluster 登记与管理

> Review Status: `APPROVED WITH FOLLOW-UP`
> Author Role: reviewer
> Date: 2026-09-15
> Feature: F001（E01，P0，`depends_on: [F012]`）
> Reviewed Branch: `feature/F001-cluster`
> Base（develop）: `7a99745fbd2c03497a4377d4086f2b3dae30f27a`
> Candidate HEAD: `fe36e1ab80d99eaec15afd6464413a4fc9633075`
> Merge Commit: `5a96ad0c4c7c749a4b6df65cde84b491e3545c6c`

---

## Feature

F001 — Cluster 登记与管理（E01，P0）。Stage 6 独立 Review。

## Scope Reviewed

| 项 | 值 |
|---|---|
| Feature Branch | `feature/F001-cluster` |
| Base Branch | `develop` = `7a99745fbd2c03497a4377d4086f2b3dae30f27a` |
| Candidate HEAD | `fe36e1ab80d99eaec15afd6464413a4fc9633075` |
| merge-base(develop, HEAD) | `7a99745…`（= start_commit，祖先关系正确） |
| 工作区 | `git status --short` 空；`git ls-files --others --exclude-standard` 空；无 staged/unstaged |
| 差异规模 | 45 文件 / +3435 −789 |

**实际执行的只读命令与结果摘要**

- `git status --short` → 空；`git branch --show-current` → `feature/F001-cluster`
- `git rev-parse HEAD` → `fe36e1a…`；`git rev-parse develop` → `7a99745…`；`git merge-base develop HEAD` → `7a99745…`
- `git log --oneline develop..HEAD` → 7 commits（`691419e` start → `fe36e1a` test），无遗漏
- `git diff --stat / --name-status / git diff 7a99745...fe36e1a`（通读全部 45 文件差异）
- `git diff --stat`、`git diff --cached --stat`、`git ls-files --others --exclude-standard` → 全空
- `git diff --stat 7a99745...fe36e1a -- tests/database/` → 仅新增 `test_g2_schema_guard.py`，T1~T7 **未被改动**

**独立复现（Reviewer 自建环境，非依赖 Tester 结论）**

- 用 `pgserver` 新建真实 PostgreSQL 实例（`/tmp/rev-f001`）→ `.venv/bin/python -m pytest -q` → **77 passed**（含 `tests/database/*`、API、guard）
- `npm run typecheck` → exit 0；`npm run test` → **8 files / 56 tests passed**
- `.venv/bin/python -m ruff check backend tests` → All checks passed；`ruff format --check` → 43 files already formatted
- `alembic check`（真实库）→ No new upgrade operations detected（无 ORM/Schema drift）
- 静态扫描 `backend/app/**`：`.deleted_at =` 赋值 **0 处**；`_foundation` 字符串 **0 处**；`app/foundation/` 目录不存在
- 用不落盘的 Python 探针独立复现两处 guard 缺口（见 REV-1 / REV-2）

审查后已按 PID 精确 kill 启动的 postgres 并删除 `/tmp/rev-f001`；工作区保持 clean。

## Product Compliance

实现忠实满足 F001 的产品边界：**无删除能力**（`DELETE /api/clusters/{id}` 未注册）、**无状态字段**、**无位置/上级字段**、**未实现 `name` 的任何未定义约束**、**未越界到 F002/F009/F010/F013/F014**。`R-CLUSTER-004` 未在 F001 强行构造结构（不建表、不加列、不加嵌套端点、不加计数），符合问题 D。未发现 Scope Creep。

## Architecture Compliance

Architecture Handoff 的 REQUIRED #1 ~ #9 逐条成立（见下）。F012 判据 4/5/6 的验证力由产品端点接管，`tests/database/*` T1~T7 原样保留且全部通过，`test_structure_guard.py::test_only_expected_tables_registered` 仍断言 `{"clusters"}`。**判据 4/5/6 未被降低**（判据 5 的 "soft delete" 一段改为绕应用层数据层直写 + API 读取排除，属已裁定的等价替代，见 REV-4 NOTE）。

## Database Review

无 Schema / Migration / 索引变更。`clusters` 表、`ck_clusters_name_no_slash`、`ux_clusters_name_active` 全部由 F012 基线提供且未被触碰。`alembic check` 无漂移；CHECK 集合恰为 `{ck_clusters_name_no_slash}`，列集合恰为 `{id,name,created_at,updated_at,deleted_at}`（G2）。未新增 `COLLATE` / 触发器 / 扩展 / 新列。**结论：通过。**

## Backend Review

- 分层清晰：`router → service → repository`，`validation.py` 为唯一领域校验入口。无 Router 内业务逻辑、无重复查询逻辑、无无意义抽象。
- 读取路径**只**经 `app/db/active.py`（`active_filter` / `select_active`）；`backend/app/**` 中 `deleted_at.is_(None)` 仅出现在 `active.py` 一处，**无第二份谓词**（REQUIRED #2 ✔）。
- **无任何写入 `deleted_at` 的代码路径**；无 `DELETE` 路由（REQUIRED #1 ✔）。
- `/` 禁令在 `validation.py` 唯一实现，**位于 `repository.create/update`（数据库写入）之前**，POST/PATCH 共享；无 schema 层重复（REQUIRED #3 ✔）。已用 grep 确认 `"/" in name` 仅一处。
- 唯一性：应用层预检 → 友好 `409`；`ux_clusters_name_active` 为最终权威，`23505 → 409 CONFLICT` + `field=name`（A04 monkeypatch 绕过预检后仍 409，独立复现 ✔，REQUIRED #4）。
- 事务边界复用 F012 `deps.py`；`flush()` 使 DB 约束在请求内抛出；`IntegrityError` 经通用 handler → 回滚 + 契约信封。
- **结论：通过。**

## Frontend Review

- `api/clusters.ts` 严格按契约 §2/§3 建模，字段封闭（无 `deleted_at` / 状态 / 位置），`getClusterByName` 仅做 RFC 3986 编码、不做 trim / 归一化。未新建请求层，复用 `http.ts`。
- 列表页 `data-state` Loading/Empty/Error 互斥且渲染不同；Error 只读 `error.code`（`ErrorState` switch），不解析 `message`。详情页 `not-found`（404）与列表 `empty` 状态标识与文案均不同。
- 未偷偷增加删除入口 / CRUD 越界；无 `vue-router` 新依赖；`DevSelfCheckPage.vue`、`api/foundation.ts` 已删除。
- **结论：通过。**

## Test Review

- AC-01 ~ AC-14 均有对应用例（A01~A16 / G1~G3 / T8′ / T9′ / T13′），非恒真：G2（CHECK 精确集合）、G3（字节级 canary）、A10/A11（列/字段否定性断言）、A14（404 + 静态源码）、A15（运行时 + 静态）、A04（monkeypatch 证明 DB 权威）都会在违约时失败。
- 测试隔离良好：`upgrade_to_head` 每用例重建 schema，无执行顺序依赖；AC-07/A08 使用**绕过应用层**的原始 psycopg 连接，真实校验软删过滤。
- Tester 的注入还原可信：`git diff` 全空、工作区 clean、`cmp` 逐字节还原声明与 clean tree 一致。
- 两处 guard 覆盖缺口经独立探针确认（见 REV-1 / REV-2）；其为**加固建议**，不改变当前测试对 AC 的有效性。
- **结论：测试可信，覆盖充分。**

---

## Findings

### REV-1 — G1 未覆盖 Pydantic config 级 `str_max_length` / `str_min_length`

```text
Severity: LOW
Layer:    Backend / Tests（guard 加固）
Location: tests/test_clusters_guards.py::_name_constraint_flags
Problem:  guard 只检查字段 metadata 属性与 config 的 str_strip_whitespace/str_to_lower/str_to_upper，
          不检查 model_config 中的 str_max_length / str_min_length。
Evidence: 独立探针（未修改仓库文件）：
          - ClusterCreate 基线 → _name_constraint_flags == set()
          - 子类注入 model_config = ConfigDict(str_max_length=10) → guard 仍返回 set()（未捕获），
            但 Injected(name='A'*11) 抛 ValidationError（行为确实改变）。
          - str_min_length=3 同理。
Impact:   未来可通过最惯用的 config 写法静默引入「长度」这一 undefined_constraint，guard 不失败。
Expected: G1 增加对 model_config 中 str_max_length / str_min_length 的断言。
Owner:    Backend
```

### REV-2 — A15 静态 guard 未覆盖 `values(deleted_at=...)` 等非 `.deleted_at =` 写法

```text
Severity: LOW
Layer:    Backend / Tests（guard 加固）
Location: tests/test_clusters_guards.py::test_a15_no_deleted_at_assignment_in_app_source
Problem:  判据为 `".deleted_at" in line and "=" in line`，SQLAlchemy Core 的
          `update(Cluster).values(deleted_at=func.now())`、`{"deleted_at": ...}`、`setattr` 形式不含 `.deleted_at`。
Evidence: 独立谓词验证：`values(deleted_at=...)` → caught=False；dict 形式 → caught=False。
          当前 `backend/app/**` 中实际赋值数为 0（grep 确认），故无现行违约。
Impact:   未来可能引入未被静态 guard 捕获的第二条软删写入（ADR-0004 §1/§3、AC-13、Risk R4）。
          运行时 A15 仍能捕获任何经 DELETE 路由暴露的软删，残余暴露面较窄。
Expected: 正则 / AST 覆盖 `values(deleted_at=`、`setattr(...,"deleted_at"`、dict 键形式。
Owner:    Backend（**应在 F014 落地前收紧** —— F014 本就要重写该 guard 以允许统一软删服务模块）
```

### REV-3 — `project-plan.yaml` 的 `git.head_commit` 与 COMPLETE 标注陈旧

```text
Severity: LOW
Layer:    Project metadata
Problem:  head_commit 仍为 7a99745（= start_commit），而实际候选 HEAD 为 fe36e1a；
          implementation.* 标注 # cb7f992，但测试交付在 fe36e1a。
Impact:    计划元数据与真实 HEAD 不一致，削弱审计可追溯性。不影响实现正确性。
处置:      ✅ 已在合并后的状态提交中修正。
```

### NOTE（REV-4）— F012 判据 5 的 "soft delete" 一段不再经应用端点

F012 判据 5 原文为 `create → list → get → update → soft delete` 端到端。F001 无删除端点（已裁定推迟 F014），该段改为绕应用层数据层直写 `deleted_at` + API 读取排除（A08），并由 F012 数据层 T5 原样保留。**可观察行为（删除后不出现在 list）验证力保持**，写入侧路径验证力随自检面删除而转移，属已批准的架构取舍（核心问题 2），非缺陷。

### NOTE（REV-5）— `CSM_ENVIRONMENT` 现为惰性配置

移除 `foundation_enabled` 后，`Settings.environment` 不再被任何运行时逻辑读取（grep 确认），仅作标签展示。非缺陷；F013 / F015 可复用。

## Existing Defects（独立复核）

| Tester ID | Tester 评级 | Reviewer 复核 | 结论 |
|---|---|---|---|
| F001-T1（G1 config 级缺口） | LOW | **维持 LOW，不升级** | 见下 |
| F001-T2（A15 `values()` 缺口） | LOW | **维持 LOW，不升级** | 见下 |
| F-01（405 → `INTERNAL_ERROR`） | LOW（继承 F012） | **维持 LOW，不阻塞** | 架构 Handoff 明确 F001 不修改通用映射表；A15 只断状态码 |

**为何不升级（正面回答）**

1. **无现行产品行为违约**：`backend/app/**` 中未定义约束数为 0、`deleted_at` 写入数为 0；全部 AC 在不触发缺口的情况下成立。
2. **实现与架构写明的 guard 机制一致**：架构 Handoff 问题 8 的 G1 明确以「字段 metadata + validator」为断言对象，问题 2 的 A15 静态 guard 明确写为「正则 `\.deleted_at\s*=`」。当前实现满足（且略多于）该书面规格；两处缺口属**超出书面规格的隐蔽注入向量**。
3. **残余风险窄**：任何「顺手」补上的软删端点都会被运行时 A15 捕获；config 级长度约束需显式新增配置才会触发。
4. 因此二者是**测试加固**，而非必须在本 Feature 修复的 MEDIUM。

**建议时点**：REV-2 应在 **F014 落地前**收紧（F014 本就要重写该 guard）；REV-1 可随 F001 后续小改或不晚于 **F011**（Excel 导入复用同一 schema）前完成。

## Non-blocking Follow-ups

1. REV-1 / REV-2 guard 加固（Backend）。
2. ✅ REV-3 计划元数据更新（协调器，已在本状态提交中完成）。
3. F-01 通用 4xx `error.code` 映射（Backend / F012 follow-up，继承）。
4. F012 Review 的 F-03（自检面 fail-open）→ **已由 F001 彻底移除自检面而消解**。
5. 若产品确认 PROPOSED-1（拒绝空串 / 空白 / 超长），须走新增产品规则 + 增量 migration，并同步修改 G1 / G2 / G3（Product）。

## Unreviewed Areas

1. **浏览器级 DOM / 视觉 E2E** 与 **URL 直达详情 404 的整页导航**（无 `vue-router`，无 Playwright）。
2. **`npm run build`** 未由 Reviewer 独立重跑（避免生成 `frontend/dist` 产物）；`typecheck` 与 56 项测试已独立通过。
3. **真实多连接并发名称竞争压测**（架构已明示由 partial unique index 兜底，A04 以 monkeypatch 证明 DB 权威）。
4. **F013 认证覆盖后**的 `/api/clusters*` 访问控制行为。
5. **生产部署 locale 固定**（F015）。

## Review Verdict

不存在 BLOCKER / HIGH；不存在必须在本 Feature 修复的 MEDIUM；REV-1 / REV-2 经独立判断维持 LOW。AC-01 ~ AC-14 全部满足；架构 REQUIRED #1 ~ #9 逐条成立；测试可信且经真实数据库独立复现；实现未超范围、未越界 F001 之外的能力。

**`APPROVED WITH FOLLOW-UP`**