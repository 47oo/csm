# Review Report — F006 VirtualMachine 登记与管理

> Reviewer Role: reviewer（独立审查）
> Date: 2026-09-18
> Feature: F006（E03，P1，`depends_on: [F002]` = DONE）
> Feature Branch: `feature/F006-virtual-machine`
> Base Branch: `develop` @ `f74e7ddbf369910e6f83b99758b672019b4fe4c9`
> start_commit: `f74e7ddbf369910e6f83b99758b672019b4fe4c9`
> 已审查 HEAD: `3bd2da22a9e35bd1813e57dff4c546a1baa301ad`
> merge-base(develop, HEAD): `f74e7ddbf369910e6f83b99758b672019b4fe4c9`（与 start_commit、base 一致，祖先关系成立）
> Test Report: `docs/test-reports/f006-virtual-machine.md`（末节 `New Test Status: READY FOR REVIEW`）

## Feature

VirtualMachine 登记与管理（F006）— CSM V1 虚拟资源的第一个资源：虚拟机的人工登记、
查询（含按宿主限定读取）、R-VM-006 可选配置字段维护与逻辑删除，以及
**VirtualMachine → BareMetal 必选绑定**的真实业务落地，并作为 F014
「宿主有活跃子 VM → 不得删宿主」的第二个真实端到端。F006 不新增领域对象 / 字段 /
关系 / 状态，无 VM 级 `status`、无 `cluster_id`、无平台接入、不越界 NIC / IP /
Container / Service / DataCenter。

## Review Status

**APPROVED WITH FOLLOW-UP**

可进入 Merge Gate。不存在 BLOCKER / HIGH / 需在当前 Feature 修复的 MEDIUM；
AC-01 ~ AC-32 全部满足；生产代码变更严格限于 F006 范围；测试经 Reviewer 独立复跑可信；
Tester 报告的 3 项缺陷（F006-T-01/02/03）经 Reviewer **独立复核确已彻底修复**。
仅存 2 条 LOW 与若干 NOTE 级 Follow-up（见 Findings），均不阻塞合并且不涉及运行时缺陷。

## Scope Reviewed

**独立复现的 Git 证据**

```text
git status --short                        → （空；工作区 clean，无未跟踪交付物）
git rev-parse HEAD                        → 3bd2da22a9e35bd1813e57dff4c546a1baa301ad
git rev-parse develop                     → f74e7ddbf369910e6f83b99758b672019b4fe4c9
git merge-base develop HEAD               → f74e7ddbf369910e6f83b99758b672019b4fe4c9（== base == start_commit）
git log --oneline develop..HEAD           → 9 提交
    3bd2da2 test(F006): re-verify the guard fix
    7844a17 fix(F006): restore the cross-module boundary guards
    4ec20c5 test(F006): independent acceptance finds a guard regression
    03db90a chore(F006): record the implementation checkpoint
    5d87d20 feat(F006): implement virtual machine registration
    a864cf5 docs(F006): define database design
    c345a3a docs(F006): define architecture and API contract
    b1263e1 docs(F006): define requirements
    6ad1594 chore(F006): initialize feature branch
git diff --stat develop...HEAD            → 46 files changed, 7553 insertions(+), 72 deletions(-)
git diff --cached --stat                  → （空）
git ls-files --others --exclude-standard  → （空）
git diff develop...HEAD -- backend/migrations/versions/0001..0003 → （空；基线未被改）
```

候选实现（`5d87d20`）、测试验收（`4ec20c5`）、修复（`7844a17`）与复验（`3bd2da2`）
均已提交，工作区 clean、无未跟踪交付物，Test Report 末节为 `READY FOR REVIEW`，
满足正式 Review 的 Gate 前提，**非 PARTIAL REVIEW**。

**实际检查范围**

- 完整分支差异 `git diff develop...HEAD`（46 文件）：Backend（`app/virtual_machines/**`、
  `app/models/virtual_machine.py`、`app/bare_metals/deletion.py`、
  `app/bare_metals/service.py`、`app/main.py`、`app/models/__init__.py`）、迁移 `0004`、
  测试、前端、契约 / 架构 / 产品 / 数据库文档、README、`project-plan.yaml`。
- 独立**重跑**关键测试与工程门禁（真实 PostgreSQL 16.2，临时实例，非复用 Tester 结论）：
  - F006 专项 + 演进 guard：`115 passed`（`test_virtual_machines_api/guards/concurrency`、
    `database/test_virtual_machines_constraints/schema_guard`、`test_cluster_views_guards`、
    `test_bare_metals_guards`、`database/test_migrations`、`database/test_schema`）。
  - 后端**全量**：`400 passed, 2 warnings`（无 skip）。
  - `ruff check backend tests` → All checks passed。
  - 前端 `npm run test` → `20 files / 242 tests passed`。
- 独立**对抗注入**（在内存中向真实 `create_app()` 追加越界路由，未改动任何仓库文件）：
  两条跨模块边界 guard 均检出 `POST /api/containers` 与 `POST /api/network-interfaces`（PASS）。
- 独立复核 AST guard 对「常量名仅现于 docstring」的注入的判别力（PASS）。

## Product Compliance

**满足。** AC-01 ~ AC-32 逐项对照实现与测试，无 FAIL / BLOCKED / NOT TESTED。

- 字段集合封闭恰 11 字段，无 `deleted_at` / `status` / `cluster_id` / NIC / 位置 / 平台字段（AC-01/17/18/30/31）。
- `name` 必填（AC-02）、宿主必选且活跃（AC-03/04/05）、六可选字段缺失返回 `null` 不省略（AC-06）、
  纯文本原样往返（AC-07）、未定义约束**不实现**（空串 / 首尾空白 / `/` 均不被拒绝，AC-08）。
- `name` 全局活跃唯一、跨宿主跨 Cluster、大小写敏感、软删释放、DB 为最终权威（AC-09~13）。
- 列表分页 / Empty 与详情 Not Found 区分（AC-14/15/16）。
- 维护：`PATCH` 仅六字段、`null` 清空、空 body → 400（AC-19/20）。
- 删除：`204` 行保留、不级联、无恢复 / 批量（AC-21/22/23）；宿主有活跃 VM → `409 ACTIVE_CHILDREN_EXIST`
  无部分写入、软删后可删（AC-24/25）；并发孤立记录 0 行、创建侧 `FOR SHARE`（AC-26/27）。
- F014/F007 接线（AC-28/29）与前端三态、Empty vs NotFound、`error.code` 分支、不重复守卫（AC-32）。
- **未越界**：无 NIC / IP / Container / Service / DataCenter 结构或端点；无 VM `status`；无 `cluster_id`；
  无双宿主 / 载体类型选择器；无平台客户端 / 凭据 / 同步字段；前端未重复实现业务守卫（AC-30/31/32）。

## Architecture Compliance

**符合。** 5 端点与契约一致（`POST`/`GET`/`GET {id}`/`PATCH {id}`/`DELETE {id}`）；
资源表示恰 11 字段；`?bare_metal_id=` 提供 canonical 宿主限定读取（与 F002 `?cluster_id=` 对称），
宿主不存在 / 已删 → `404 NOT_FOUND`，存在但无活跃 VM → `200 + items==[]`（Empty 与 Not Found 可区分）；
`PATCH` 仅六字段且 `extra="forbid"`；名称全局唯一 + 大小写敏感；全部复用 F012/F013/F014/F002 基座，
无新框架 / 新依赖 / vue-router / EAV / 多态 / CASCADE / 触发器 / COLLATE。与 ADR-0002/0003/0004/0005 一致。

## Database Review

**符合 Database Handoff 逐项要求。**

- migration `0004_f006_virtual_machines`（`down_revision = 0003_f002_bare_metals`，单一线性 head）：
  一条 `CREATE TABLE` 建齐 **12 列**；`id` identity；`bare_metal_id NOT NULL` +
  `fk_virtual_machines_bare_metal` `ON DELETE RESTRICT ON UPDATE RESTRICT`；`name NOT NULL`；
  六个可空 `TEXT`；时间列 `server_default now()`；`deleted_at NULL`。
- `ux_virtual_machines_name_active`：`UNIQUE (name) WHERE deleted_at IS NULL`，无 `lower()` / `COLLATE`；
  `ix_virtual_machines_bare_metal_id` 存在；CHECK 集合为空；**无 `status` / 无 `cluster_id`**。
- `0001` / `0002` / `0003` **diff 为空**，未被改；无 CASCADE / 触发器 / 扩展 / 数据迁移；
  ORM 模型与 migration 字段 / 约束 / 索引一致（`alembic check` 无漂移）。
- 与 `docs/database/csm-v1-schema-design.md` 同步（VM→BareMetal 由 UNCONFIRMED 更正为 N:M→N:1 mandatory；
  「反规范化 `cluster_id`」注记标注为已关闭）。

## Backend Review

**符合。**

- 分层清晰：`router` 仅做 HTTP 接线；`service` 承载业务（宿主 `FOR SHARE` 预检、全局重名预检、更新 / 删除）；
  `repository` 读取路径统一经 `active_filter` / `select_active`，**无第二份 `deleted_at IS NULL` 谓词**，
  无写 `deleted_at` 的方法。
- 删除委托系统内唯一软删路径 `app/deletion/service.soft_delete()`（G-9 allow-list 保持不变）。
- 错误语义正确区分「宿主不存在 / 已删 → 404」「全局重名 → 409 DUPLICATE」「Empty → 200」，
  未把不同情况塌缩为 `[]` 或 `500`。
- `app/bare_metals/deletion.py` 将 `BARE_METAL_ACTIVE_CHILD_CHECKS` 由显式空元组演进为
  `(has_active_virtual_machines,)`（fail-closed，非 fail-open），并保持既有 `delete_bare_metal`
  显式传入；`VIRTUAL_MACHINE_ACTIVE_CHILD_CHECKS` 显式声明并真实传入 VM 删除路径（F007 追加点）。
- 跨模块依赖方向 `bare_metals.deletion → virtual_machines.deletion → models.virtual_machine` 无循环导入。

## Frontend Review

**符合。** 列表 / 详情 / 登记 / 编辑 / 删除入口齐全；`VirtualMachineListPage` 的
`loading / empty / error / content` 四态互不相同；Empty（200 + `items==[]`，文案「该裸金属暂无虚拟机」）
与 Not Found（宿主 404 → `ErrorState`，`data-error-code="NOT_FOUND"`）可区分；一律按 `error.code`
（必要时 `details[].code`）分支，**不解析 `message`**；四类错误 `409/404/401/400` 分别处理；
`VirtualMachineFormDialog` 对 `name` 不做长度 / 空串 / 字符 / trim 校验，空 name / 重名仍提交由后端裁决；
删除入口不对任何行预判（`§21`）；`name` / `bare_metal_id` 不可编辑；无状态展示 / 编辑；
无 NIC / IP / Container / Service / 平台同步 UI；未引入新依赖。

## Test Review

**可信，且对抗验证充分。**

- 测试真正覆盖 AC：真实 `TestClient` + 真实 PostgreSQL，且大量断言**绕过应用层**直连 psycopg
  （预置软删行、直插重复活跃 name → 23505、无效宿主 → 23503、直查 `information_schema` / `pg_constraint` / `pg_indexes`），
  非仅验证实现自身逻辑。
- 并发测试（T-24/T-25）使用真实行锁（`FOR UPDATE NOWAIT` 断言持锁），两种交错均验证孤立记录不变式 = 0 行。
- 对抗注入（G-1~G-11）10/12 由 Tester 证明可失败，余下 G-6b 已由 F006-T-02 修复后经 Reviewer 独立复证可失败。
- 未见「迎合实现」的断言：错误分支用与展示无关的 `message` 证明前端不解析 `message`；空 name / 重名
  仍提交；删除守卫不预判。
- 既有 guard 的演进为**增补 / 加强**而非删除（见 Findings 边界复核）。

## Findings

### REV-1

Severity:
LOW

Layer:
Project metadata / Coordinator

Location:
`docs/project/project-plan.yaml`（F006 块 `git.head_commit`）

Problem:
`git.head_commit` 仍为 base commit `f74e7ddbf369910e6f83b99758b672019b4fe4c9`，
等于 `start_commit`，未指向候选 HEAD `3bd2da22a9e35bd1813e57dff4c546a1baa301ad`；
同块 `implementation.test: COMPLETE` / `backend: COMPLETE` 已就绪，HEAD 字段与之不匹配。

Evidence:
`git diff develop...HEAD -- docs/project/project-plan.yaml` 中 `head_commit: f74e7dd...`；
`git rev-parse HEAD` → `3bd2da22...`。

Impact:
仅计划元数据陈旧，不影响代码、契约、数据库或运行时行为；但会误导后续对「已审查 HEAD」的追溯。

Expected:
由协调器在 Merge Gate 前把 `git.head_commit` 更新为已审查 HEAD（或合并提交），保持一致。

Suggested Owner:
coordinator

### REV-2

Severity:
LOW

Layer:
Product docs

Location:
`docs/product/domain-model.yaml > must_not_assume`

Problem:
原先的 `虚拟机绑定裸金属是必选的` 被改写为
`虚拟机绑定裸金属是必选的（R-VM-005 已确认其为必选；本条保留仅作为「不得自动推导」的提醒，不适用于 VM→BareMetal 的强制性）`。
该条目位于 `must_not_assume` 列表，正文却断言绑定「是必选的」，语义自相矛盾，易误读。

Evidence:
`git diff develop...HEAD -- docs/product/domain-model.yaml`（`must_not_assume` 段）。

Impact:
文档可读性 / 一致性下降，无代码或契约影响。R-VM-005 的确认事实已在 `relationships` 与
`domain-model.md` §5.3 正确落定。

Expected:
建议改为「不得仅根据资源分类自动推导 VM→BareMetal 的强制性（该关系本身已由 R-VM-005 确认为必选）」
之类的澄清表述，或从 `must_not_assume` 中移除该条。

Suggested Owner:
product-manager / coordinator

### REV-3

Severity:
NOTE

Layer:
Backend / Test guards

Location:
`tests/test_virtual_machines_guards.py::test_g6_t27_vm_active_child_checks_explicitly_declared`

Problem:
该 guard 断言 `VIRTUAL_MACHINE_ACTIVE_CHILD_CHECKS == ()`。当前正确，但 F007 追加「活跃 Container」
检查后此断言必然失效，需随 Feature 演进（与既有 guard「演进而非删除」要求一致）。

Evidence:
`tests/test_virtual_machines_guards.py` L131-137。

Impact:
无当前影响；属预期内的 F007 演进点，记录以防被遗漏或误当回归。

Expected:
F007 落地时将其演进为「tuple 且含活跃 Container 检查」的正向断言。

Suggested Owner:
backend（F007）

## Existing Defects

对 Tester 已知缺陷逐项独立复核：

- **F006-T-01（MEDIUM，跨模块边界 guard 被收窄）→ 已彻底修复（agree）。**
  `git show 5d87d20` 确认实现提交曾把 `test_g009_2` 收窄为 `cluster_views_router.routes`、
  把 `test_t29` 收窄为 `path.startswith("/api/bare-metals")`（后者变为恒真）。
  `git show 7844a17` / HEAD 恢复为**全部 OpenAPI path** 全局扫描，并**仅**移除已合法化的
  `virtual-machine` / `virtual_machine` / `vm` / `virtual` token（`nic`/`ip`/`container`/`service`
  保留并**新增** `network-interface` / `network_interface`）。
  **Reviewer 独立注入验证**（内存追加越界路由，未改仓库文件）：
  `test_g009_2` 与 `test_t29` 的扫描逻辑对 `POST /api/containers`、`POST /api/network-interfaces`
  均返回 offenders（即会 FAILED）；基线路径 offenders 为空（无假阳性）。
  修复**未**把任何 guard 改成恒真，既有断言**未被净删除**（对比 base 的删行 15 行全部为受控演进：
  `0003→0004`、表集合追加 `virtual_machines`、`== ()` 改为更强的非空 + 含 VM 检查、token 集合调整）。
- **F006-T-02（LOW，VM 删除路径静态 guard 可绕过）→ 已修复（agree）。**
  修复引入 AST 辅助 `_soft_delete_active_children_args`，断言 `soft_delete(...)` 调用的
  `active_children=` 关键字**真实解析到常量**。Reviewer 独立复核该 AST 判别逻辑：
  「仅 docstring 出现常量名」时返回 `[]`（guard 会 FAILED），真实传入时解析出常量（通过）。
- **F006-T-03（LOW，`delete_bare_metal` docstring 过期）→ 已修复（agree）。**
  docstring 现为「F006 起包含『是否存在活跃 VirtualMachine』检查」，与
  `BARE_METAL_ACTIVE_CHILD_CHECKS` 实际内容一致。

Reviewer 独立判定：Tester 对三项缺陷的严重程度评估合理，均应修复；修复后无残余阻塞项。

## Non-blocking Follow-ups

1. REV-1：协调器在 Merge Gate 前同步 `project-plan.yaml > F006.git.head_commit`。
2. REV-2：澄清 `domain-model.yaml > must_not_assume` 中 VM→BareMetal 条目措辞。
3. REV-3：F007 落地时演进 `VIRTUAL_MACHINE_ACTIVE_CHILD_CHECKS` 相关 guard（预期演进，非缺陷）。
4. （承 F014 已知项）静态 guard 对动态构造的 SQL / 路由的穷举覆盖仍有限；如需，可在后续 Feature
   引入更系统的 AST / 运行时路由注册扫描。
5. 浏览器级前端 E2E / 多 worker 并发压测未执行（无产品需求；当前单机内网 V1 可接受）。

## Unreviewed Areas

- 浏览器真实 DOM / 视觉 / 网络层渲染（无浏览器自动化环境；前端行为经 vitest + happy-dom 组件测试
  与真实 API client 集成覆盖）。
- 多 uvicorn worker / 跨进程并发压测（无产品需求）。
- 静态 guard 对「动态构造 SQL / 动态注册路由」的穷举覆盖（已知残余风险，见 Follow-up 4）。

---

## Reviewer 独立判定摘要

- **Guard 修复是否彻底：是。** 两条跨模块边界 guard 现覆盖**全部** `/api/*` OpenAPI path，
  并能对越界**非 GET** 路由失败（经 Reviewer 独立注入复证）；修复仅移除已合法化的 VM token，
  未把任何 guard 改为恒真，未净删除既有断言；AST guard 对 docstring-only 绕过具备判别力。
- **是否可进入 Merge Gate：可以**（APPROVED WITH FOLLOW-UP）。无 BLOCKER / HIGH /
  需当前修复的 MEDIUM；AC-01~AC-32 全部满足；实现未超范围；测试可信。

GIT: NONE
