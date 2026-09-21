# Review Report — F021 IP 地址自动 / 手动分配

> Verdict: **APPROVED WITH FOLLOW-UP**
> Author Role: reviewer（独立审查；协调器在 Merge 后持久化）
> Date: 2026-09-21
> Feature: F021（E02，P1，`depends_on: [F020, F005, F004, F002]` = DONE）
> Branch: `feature/F021-ip-address-allocation`
> Base: `develop` = `1942ec4d544675ec47df5b924ec52a35bae7c2e2`
> start_commit: `1942ec4`（= merge-base）
> 已审查 HEAD: `d9961587180211ba949447f2156181816d4aa0f0`（`test(F021): add acceptance and regression coverage`）
> merge commit（合并后）: `011d05d`（父 `1942ec4` 与 `d996158`）

---

## Review Status

```text
APPROVED WITH FOLLOW-UP
```

无 BLOCKER / HIGH / 必须当前修复的 MEDIUM；仅 NOTE 级 follow-up。批准绑定候选 HEAD `d996158` 与 Base `1942ec4`。

## Scope Reviewed

- Branch `feature/F021-ip-address-allocation`；Base `develop` = `1942ec4`；start_commit/merge-base = `1942ec4`（祖先关系已确认）。
- 提交序列：`74cf263`（start）→ `aa07063` → `07caa2f`（Product）→ `45f92ef`（Architecture + 契约）→ `f480ecc`（实现）→ `ae10140`（checkpoint）→ `d996158`（测试资产 / Test Report）。
- 工作区 clean；完整差异 32 文件 / +5255 −59。
- 独立重跑：`tests/test_ip_allocations_guards.py` 12 passed；`tests/test_ip_allocations_api.py` 58 passed；既有 guard/schema 子集 57 passed；前端 F021 5 个 spec 61 passed。
- 未在范围内重跑：后端全量 1204（采信 Tester 独立重跑 + 协调器独立复跑证据）；生产库零操作。

## Product Compliance

AC-01 ~ AC-33 逐条满足，无 Scope Creep：分配产物仅为一条现有 IPAddress（响应恰 5 字段）；NIC 必选且活跃、宿主 BareMetal 活跃；Cluster 受控推导（请求 / 响应无 `cluster_id`）；自动取并集数值最小未占用 IPv4（不跳过网络 / 广播 / 网关）；占用按字面、范围归属按数值；手动非规范规范化写入、非法格式 400、范围外 `OUT_OF_RANGE`、已占用 `DUPLICATE`；耗尽 `NO_AVAILABLE_IP` 且无部分写入；不新增超出 R-IP-001 的唯一性。明确不包含项（CIDR / IPv6 / 保留地址跳过 / DHCP·DNS·外部同步 / 回收 / 审计 / 批量）均未出现。F005 §10 两处修订逐字匹配 Architecture Handoff 附录 B，无「契约禁止、实现却有」分裂。

## Architecture Compliance

符合 C-01~C-10 / R-01~R-08：新模块 `app/ip_allocations/**`，复用 F005 `create_ip_address` 单一受控 `cluster_id` 写入路径与 F020 `ipv4` 纯函数；`derive_cluster_id` 调用点 1→3 按完整新集合精确演进 guard；无新增锁 / 重试 / 死锁序 / 触发器 / CASCADE；`database: false` 一致。

## Database Review

无 migration、无 Schema 变更（head 仍 `0009_f020_ip_address_ranges`）；无新表 / 列 / 唯一索引 / 排他约束 / 触发器 / CASCADE；`ip_addresses` 唯一索引仍恰为 `{ux_ip_addresses_cluster_ip_active}`；`SQLSTATE_MAP` 键集合不变；复用既有索引，无「未来可能有用」的索引。

## Backend Review

单一 `cluster_id` 写入路径（`app/ip_allocations/**` 零 `IpAddress(...)` / 零 `cluster_id` 写入 / 零裸 SQL 写入）；复用 F020 `parse_ipv4` / `format_ipv4`（全 app 仅一处定义）；耗尽在任何写入之前；错误语义与契约逐字一致；校验顺序稳定；`repository.py` 纯只读。Router 两条静态 `POST` 路径与 F005 动态路径不冲突。

## Frontend Review

严格使用契约（请求字段封闭）；三态互异；按 `error.code`（结合 `details[].code`）分支、不解析 `message`；不做客户端业务校验（形式 A 静态 guard + 行为探针双层覆盖）；未偷偷新增 CRUD；未混淆 Empty / Error；未引入不必要依赖。

## Test Review

Tester 新增测试真实覆盖 AC-01~AC-33；直连 DB 证伪绕过应用层（`23505`、字面 vs 数值共存、结构不变、漂移 0、head 0009）；真实线程并发断言恰 `[201,409]`、落败方 `DUPLICATE`、活跃行 ≤1、无 5xx；既有 guard 未被削弱——`test_g9_derive_cluster_id_call_is_unique` 由 1 个调用点按完整新集合精确演进为 3 个（`==` 精确相等），`test_g9_cluster_id_write_path_is_unique` 期望值未变，`test_t38` 由 2 路径精确演进为 4 路径且禁用 token 循环覆盖两条新路径；无 `.skip` / `.only` / `xfail`。

## Findings

### REV-1

```text
Severity: NOTE
Layer: Docs / Project State
Location: docs/project/project-plan.yaml (F021.next_action / last_result)；docs/test-reports/f021-ip-address-allocation.md
Problem: 计划与 Test Report 曾引用旧候选 HEAD `ae10140`；实际被审查候选 HEAD 为 `d996158`。
Impact: 仅协调元数据陈旧；不改变批准绑定对象（仍仅对 d996158 有效）。
Expected: Merge Gate 前将 Feature HEAD / next_action 更新为 d996158。
Suggested Owner: 主协调器
```

### REV-2

```text
Severity: NOTE
Layer: Backend / Style
Location: backend/app/ip_allocations/{__init__,repository,router,schemas,service}.py
Problem: 5 个新增文件缺文件末尾换行。
Impact: 无功能影响；ruff 已通过。
Expected: 可选清理；不阻塞 Merge。
Suggested Owner: Backend
```

### REV-3

```text
Severity: NOTE
Layer: Backend / Performance
Location: backend/app/ip_allocations/service.py::select_first_free
Problem: 候选枚举在活跃范围段并集上线性扫描，超大范围理论扫描上界较高。
Impact: 已确认规模下可接受；Architecture P-05 / Risk 2 已显式接受，无新增索引需求。
Expected: 维持现状；未来范围显著增大时重评。
Suggested Owner: Architect（仅作后续关注）
```

## Existing Defects

Tester 报告 Defects: None。F020 DEF-01（测试环境 `fe_sendauth`）在本轮以 `PGPASSWORD=csm` 消除（后端全量 1204 passed / 0 failed），Owner = 主协调器，属测试环境而非 F021 缺陷，评估合理，不阻塞。Tester 所述「探针连接快照滞后」已定位并修正，不计为产品缺陷。对抗注入（DROP partial unique、注释分配端点）证明关键约束与 guard 可失败且逐字节还原，证据可信。

## Non-blocking Follow-ups

1. 清理计划 / 报告 HEAD 引用，使 `next_action` 指向 `d996158`（本「mark feature complete」状态提交已更正）。
2. REV-2 末尾换行（可选）。
3. REV-3 线性扫描性能上界（Architecture 已记录，未来重评）。
4. 契约 §6.5 记录的瞬态并发窗口为已知、已记录、可重试，不在本 Feature 承诺范围。

## Unreviewed Areas

- 后端全量 1204 用例（未在 Reviewer 本机重跑，采信 Tester 独立重跑与协调器独立复跑）。
- 前端 `npm run build` / 全量 769（采信 Tester / 协调器独立执行结论）。
- 契约明确排除的能力（IPv6 / CIDR / 保留地址开关 / DHCP / DNS / 回收 / 批量 / 审计），因不在范围内未验证。

---

**Verdict**：`APPROVED WITH FOLLOW-UP`（批准绑定 HEAD `d996158` 与 Base `1942ec4`；无 BLOCKER/HIGH；仅 NOTE follow-up，不阻塞 Merge）。