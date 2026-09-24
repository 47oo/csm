# Review Report — F020 IP 地址范围段（地址池）管理

> Verdict: **APPROVED WITH FOLLOW-UP**
> Author Role: reviewer（独立审查）
> Date: 2026-09-21
> Feature: F020（E02，P1，`depends_on: [F001, F005]` = DONE）
> Branch: `feature/F020-ip-address-range`
> Base: `develop` = `0fe65f4707676da1d049cef6cde111349a066f5d`
> start_commit: `0fe65f4`（与 Base 相同）
> 已审查 HEAD: `84d5c17b39ccd74830ce483acce5b522993344ec`（`test(F020): add acceptance and regression coverage`）
> merge-base(develop, HEAD): `0fe65f4`
> 持久化于 Merge 之后（Reviewer 只读，报告由协调器写入；merge commit `e4291a1`）。

---

## Review Status

```text
APPROVED WITH FOLLOW-UP
```

无 BLOCKER / HIGH；无必须在当前 Feature 修复的 MEDIUM；仅 LOW / NOTE 级 follow-up。批准绑定候选 HEAD `84d5c17` 与 Base `0fe65f4`。

## Scope Reviewed

- Branch `feature/F020-ip-address-range`；Base `develop` = `0fe65f47`；start_commit `0fe65f4`；已审查 HEAD `84d5c17`。
- merge-base(develop, HEAD) = `0fe65f4` —— 祖先关系成立；`git log develop..HEAD` 共 8 个提交（docs → impl `ca9ae73` → checkpoint `bf59c59` → chore `abea25d` → test `84d5c17`）。
- 工作区：`git status --porcelain` 为空；`git diff` / `git diff --cached` / `git ls-files --others --exclude-standard` 均为空 → 交付物已全部提交，正式 Review 前提满足。
- diff 规模：59 文件，+8329 / −75；其中 `0001`–`0008` migration 逐字节未改，仅新增 `0009`。
- 独立重跑（真实 PostgreSQL 16.15，测试库 `csm`）：
  - 后端 F020 专项 `tests/test_ip_address_ranges_api.py + guards + concurrency + database/test_ip_address_ranges_schema_guard.py` → **112 passed**（2:08）
  - 前端 F020 四个 spec → **84 passed / 4 files**
- 未审查内容见 Unreviewed Areas。

## Product Compliance

逐条核对 Product Handoff **AC-01 ~ AC-29**，实现、契约、测试三者一致，**全部满足**，无 Scope Creep：
- AC-01~09（认证 / 字段封闭 / cluster_id 活跃 / start≤end / IPv4 / 规范化）满足。`extra="forbid"` + `RequestValidationError→400`；`ipv4.py` 严格解析（允许前导零、拒绝前缀/IPv6/空白/空串）并数值化存储，响应渲染 canonical dotted-quad。
- AC-10~12（重叠 / 跨 Cluster 共存 / PATCH 重校验无部分写）满足。应用层闭区间预检返回 `409 OVERLAP`；`EXCLUDE` 为最终权威；相接不算重叠。
- AC-13~18（软删 / 释放重叠 / 删除守卫 / 不级联）满足。删除委托唯一软删路径；命中 `409 ACTIVE_CHILDREN_EXIST` 且目标 `deleted_at` 仍 NULL；不级联。
- AC-19~22（无状态 / 列表 Empty / 详情 404 / 已删排除）满足。
- AC-23~24（F005 立场不变）满足。`ip_addresses` 模块零 F020 耦合，`ip_address` 无新增 CHECK。
- AC-25~27（不引入分配 / CIDR / IPv6 / 未确认能力）满足。端点恰 5 个。
- AC-29（契约已落盘 READY，无「契约禁止、实现却有」分裂）满足。

## Architecture Compliance

- 符合 Architecture Handoff 的 CONFIRMED / REQUIRED 决策：新表承载、字段封闭、无状态、软删唯一路径、跨 Cluster 可重复、`EXCLUDE` 最终权威、`ip_address` 自由文本不变、仅 IPv4。
- `app/main.py` 挂载、`CLUSTER_ACTIVE_CHILD_CHECKS` 追加、`sqlstate.py` 追加 `23P01` 三处集成为 additive。
- 无触发器、无 CASCADE、无第二条 `deleted_at` 写入路径、无生成列、无 COLLATE —— 与 ADR-0002 / ADR-0004 一致。
- 寻址一律走 `id`（ADR-0003），无业务名称 Path 字符集风险；无需 `PRODUCT DECISION REQUIRED`。
- 未修改 `package.json` / `pyproject` / lock 文件，无新增第三方依赖。

## Database Review

- Schema：`ip_address_ranges` 恰 **7 列**（`id/cluster_id/start_ip/end_ip/created_at/updated_at/deleted_at`），`start_ip/end_ip` 为 `BIGINT`，无 status/name/description/CIDR/IPv6/分配列，与 Database Handoff 一致。
- 约束：PK、FK `RESTRICT`、`ck_ip_address_ranges_bounds`、`ex_ip_address_ranges_active_no_overlap`（`EXCLUDE USING gist (cluster_id WITH =, int8range(start_ip,end_ip,'[]') WITH &&) WHERE deleted_at IS NULL`）逐字对应；`btree_gist` 存在；无触发器、无 CASCADE、无 `ux_` 唯一索引；保留 `ix_ip_address_ranges_cluster_id`。
- Migration `0009`：`down_revision="0008_f008_services"`，单一线性 head；upgrade/downgrade 顺序正确，downgrade 不 DROP EXTENSION；ORM ↔ Migration 无 drift。
- 绕应用层证伪：同 Cluster 活跃重叠 → `23P01`；跨 Cluster 相同范围成功；`start>end`/越界 → `23514`；FK/RESTRICT → `23503`；软删 predicate 释放重叠；不变式 V-17/V-18/V-19 = 0。

## Backend Review

- 分层清晰：`router` 仅 HTTP 装配；`service` 领域行为；`repository` 只读 + `create/update`；`ipv4.py` 纯函数。
- 写路径：`create` 先 `FOR SHARE` 父 Cluster 并确认活跃（未命中 `404`）；`PATCH` 对目标行 `FOR UPDATE` 后重跑解析/边界/重叠校验，失败整事务回滚；`DELETE` 委托 `soft_delete(..., active_children=IP_ADDRESS_RANGE_ACTIVE_CHILD_CHECKS)`。
- `overlap_exists` 闭区间交集仅作友好预检；`flush()` 使 DB 约束在请求内暴露并经统一 `sqlstate.py` 映射。
- `23P01 → 409 CONFLICT / details[].code=OVERLAP` 为单点映射，既有 23502/23514/23505/23503 未删除。
- 错误语义正确区分；无 500 泄漏路径；无 SQL 注入或多余副作用。

## Frontend Review

- 严格使用契约：`src/api/ipAddressRanges.ts` 只暴露 6 字段，写操作走 `id`，`DELETE` 不带 body。
- 三态互异；Empty 与 Not Found 不同状态；详情页 `not-found` 独立态。
- 按 `error.code`（结合 `details[].code`）分支，不解析 message；不重复业务校验；`cluster_id` 编辑态只读；字段封闭。

## Test Review

- 测试真实覆盖 AC 并主动证伪：绕应用层直连 DB 验证约束；monkeypatch 关闭预检证明 DB 最终权威；并发测试真实线程 + 真实 PG。
- 未发现「迎合实现」；既有 guard 演进出加法式；F002/F004/F005 立场与 guard 保留。
- 独立重跑 F020 专项 112 passed / 前端 84 passed，与 Tester 报告一致。

## Findings

### REV-1

```text
Severity: LOW
Layer: Process / Repo scope
Location: .pi/agents/{architect,backend,database,product-manager,project-manager,reviewer,tester}.md
Problem: 提交 abea25d 将 7 个 agent 配置的 model provider 从 self-hosted/… 改为 local/…，与 F020 产品能力无关。
Evidence: git diff develop...HEAD -- .pi/agents → 7 处 provider 变更（无其它改动）。
Impact: 不改变 F020 任何行为；使 Feature 分支混入无关工具链配置变更，影响 diff 可审计性。
Expected: 协调器确认该 provider 变更确为有意为之（用户选择 A2，确认）。
Suggested Owner: 主协调器
```

### REV-2

```text
Severity: LOW
Layer: Project docs consistency
Location: docs/project/v1/project-plan.yaml 与 docs/project/{backlog,dependency-map,milestones}.md
Problem: 生成视图仍显示 F020 为 IN_PROGRESS，未随状态再生。
Evidence: git diff develop...HEAD -- docs/project/…
Impact: 仅项目状态可读性/一致性问题。
Expected: 协调器在 Merge 前/最终状态提交中对齐生成视图。
Suggested Owner: 主协调器
```

### REV-3（= Tester DEF-02）

```text
Severity: LOW
Layer: Test doc
Location: tests/test_ip_address_ranges_api.py 文件头 docstring
Problem: docstring 指引查看不存在的 test_ip_address_ranges_constraints.py（实际为 test_ip_address_ranges_schema_guard.py）。
Impact: 无功能影响；仅交叉引用失效。
Expected: 修正 docstring 指向实际文件。
Suggested Owner: Backend（测试注释）
```

### NOTE-1

```text
Severity: NOTE
Layer: Tests
Location: tests/database/test_ip_address_ranges_schema_guard.py::test_v18
Problem: V-18 直插的是「已软删范围段挂在已软删 Cluster 下」，ORPHAN_QUERY 恒 0 的断言偏 vacuous。
Impact: 无功能风险；实际保护由并发测试 V-21 与 Tester raw probe 证明。
Expected: 可选补一条非 vacuous 的「伪造活跃 orphan → 查询检出」断言。
Suggested Owner: Tester（如后续补强）
```

## Existing Defects

- **DEF-01（Tester 判 MEDIUM / Test Infra，Owner 主协调器）**：全量后端 11 failed 全部为其它 Feature 的 concurrency 测试，根因 `psycopg.connect(raw_connection_dsn(conn.info.dsn))` 丢失口令。独立核对：这些文件不在 F020 变更集中；F020 自身并发测试用带口令 DSN 并通过。**判定：不属于必须在当前 Feature 修复的 MEDIUM；不应阻塞 F020。** 建议另立 Test-Infra 修复项。
- **DEF-02（LOW）**：见 REV-3。

## Non-blocking Follow-ups

1. 修正 `tests/test_ip_address_ranges_api.py` docstring 的文件引用（REV-3）。
2. `.pi/agents` provider 变更说明（REV-1；用户 A2 已确认）。
3. 对齐 `project-plan.yaml` 状态与生成视图（REV-2；本状态提交已处理）。
4. 其它 Feature concurrency 测试第二连接 DSN 缺失口令（DEF-01）作为独立 Test-Infra 任务。
5. 可选补强 V-18 的非 vacuous 断言（NOTE-1）。
6. 生产部署前落实 `btree_gist` 权限前置（Architecture Risk 1 / Database OQ-1）。

## Unreviewed Areas

- 未对生产库 `csm-prod-postgres-1` 执行任何操作；未在生产环境验证 Migration。
- 其它 Feature 的 11 个 concurrency 测试因 DEF-01 环境问题未纳入本次结论（与 F020 无交集）。
- F021（IP 自动 / 手动分配）不在本 Feature 范围，未审查。
- 未逐行审阅全部前端 spec 断言；未审阅 `docs/test-reports/assets/f020/*.py` 探针脚本全文。

---

**Verdict**：`APPROVED WITH FOLLOW-UP`（批准绑定 HEAD `84d5c17` 与 Base `0fe65f4`；无 BLOCKER/HIGH；仅 LOW/NOTE follow-up，不阻塞 Merge）。