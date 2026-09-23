# Review Report — F023 自动分配时指定 IP 地址范围段

## Feature

F023 — 自动分配时指定 IP 地址范围段（E02，P1，`depends_on: [F020, F021]`）。
自动分配从「目标 Cluster 全部活跃范围段并集取全局最小」改为「**必须显式指定一个活跃范围段**，仅在所选单个范围段内取数值最小未占用 IPv4；耗尽 → `409 + NO_AVAILABLE_IP` 且不回退」。

---

## Review Status

```text
APPROVED WITH FOLLOW-UP
```

不存在 BLOCKER / HIGH / 必须当前修复的 MEDIUM；核心验收标准（AC-01 ~ AC-20）经独立复跑全部满足；实现未超范围；测试可信。仅有 1 项 LOW（pre-existing，跨端点约定）与若干 NOTE 作为 Follow-up，均不阻塞合并。

---

## Scope Reviewed

| 项 | 值 |
|---|---|
| Feature Branch | `feature/F023-ip-range-selection` |
| start_commit / merge-base | `dd159f3c43f97969b1f4b91106cb3c5b83d3f0d5` |
| Base Branch / SHA | `develop` = `dd159f3` |
| 候选 HEAD（已审阅实现 + 测试） | `dfe2af735388f83413854e01c0dcb1d140193c7d` |
| 审查 diff | `git diff dd159f3..dfe2af7`（26 文件，+3419/−143） |

**实际审阅内容**
- Backend：`backend/app/common/errors.py`、`backend/app/ip_allocations/{schemas.py,service.py,repository.py}`。
- Frontend：`frontend/src/api/ipAddresses.ts`、`frontend/src/components/IpAddressAllocateDialog.vue`、`frontend/src/pages/IpAddressListPage.vue`。
- Contract：`docs/api/f021-ip-address-allocation.md`（逐节比对 §2 / §3.1 / §3.2 / §4 / §6 / §8 / §9 / §10）。
- Docs：`requirements.md` R-IP-006 / R-IP-009、`domain-model.md`、`project-plan.yaml` F023 / DEC-025。
- Tests：`tests/test_f023_ip_range_selection.py`、`tests/test_f023_tester_probe.py`、`tests/test_ip_allocations_api.py`、`tests/test_ip_allocations_guards.py`、`frontend/tests/f023TesterProbe.spec.ts` 及 4 个改动的既有前端测试。

**独立复跑证据（Reviewer 亲自执行，非采信 Tester 结论）**

```text
$ PGPASSWORD=csm CSM_TEST_DATABASE_URL="postgresql+psycopg://csm:csm@localhost:55432/csm" \
    .venv/bin/python -m pytest tests/test_f023_ip_range_selection.py tests/test_ip_allocations_guards.py -q
21 passed in 13.23s

$ ... pytest tests/test_f023_tester_probe.py tests/test_ip_allocations_api.py -q
87 passed in 122.80s

$ .venv/bin/ruff check backend tests
All checks passed!

$ cd frontend && npx vitest run tests/f023TesterProbe.spec.ts tests/ipAddressAllocateDialog.spec.ts \
    tests/ipAddressAllocationApi.spec.ts tests/ipAddressAllocationNoClientValidation.spec.ts \
    tests/ipAddressListPageAllocation.spec.ts
Test Files 5 passed / Tests 65 passed

$ npm run typecheck   → 无错误
```

环境：真实 PostgreSQL 16（`csm-f020-test-pg`，`localhost:55432`）。

---

## Product Compliance

满足产品需求，且**未超范围**。

- 请求新增**必填** `ip_address_range_id`；不存在「未指定范围段也成功」路径（缺字段 → 400；封闭 schema 拒绝 `cluster_id` / `status` / `mode` / `reserved_addresses` / `ip_address`）。
- 所选范围段校验三态稳定且非 5xx、无写入：不存在 / 已逻辑删除 → `404 + NOT_FOUND + details[].code=IP_ADDRESS_RANGE_UNAVAILABLE`；活跃跨 Cluster → `409 + CONFLICT + 同 code`；与 NIC 404（`details == []`）可区分。
- 单范围取最小：仅枚举所选段；不取未选段更小值；跳过段内已占用；耗尽 → `409 + NO_AVAILABLE_IP`，不回退、不跨段 / 跨 Cluster、无部分写入。
- 既有规则语义保持：手动分配（`/allocate-manual`）与 F005 `POST /api/ip-addresses` 语义未变；占用按字面、归属按数值；软删释放；无隐式保留地址；无新增唯一性。
- 明确不包含项（CIDR / IPv6 / 保留地址 / 回收 / 审计 / 批量 / 默认范围 / 掩码 / VLAN 过滤 / 新实体）均**未实现**。
- 契约修订已落盘且 `Status: **READY**`，`ip_address_range_id` 标注 `**是**`；无「契约禁止、实现却有」分裂。

---

## Architecture Compliance

符合 `docs/architecture/f023-ip-range-selection-handoff.md` 与 ADR-0002/0003/0004/0005。

- 校验顺序稳定、拒绝先于写入：`derive_cluster_id` → `get_active(range_id)` → 归属校验 → 占用读取 → 单段枚举 → `create_ip_address`，与契约 §6.1 逐条一致。
- 复用既有能力：`IpAddressRangeRepository.get_active`（活跃谓词单一实现经 `select_active` → `active_filter`）、`app.ip_address_ranges.ipv4.format_ipv4`、`select_first_free`。无第二份 IPv4 解析。
- **既有不变式保持**：`cluster_id` 写入仍唯一经 `create_ip_address`；软删写入仍唯一经 `deletion/service.py::soft_delete`；`SQLSTATE_MAP` 键集合不变（guard G-F021-5）。
- 无新表 / 新列 / 唯一索引 / 排他约束 / 触发器 / migration；migration head 仍 `0010_f022_ip_range_metadata`。
- 前端方案 1 只读链（NIC → BareMetal → `listIpAddressRanges({cluster_id})`）与 Architecture 定稿一致；未新增后端读取面；未在客户端回填 `cluster_id`。

---

## Database Review

- `layers.database = false` 成立：`backend/migrations/**`、`backend/app/models/**` 自 `dd159f3` 零改动；`alembic heads` 单一 head `0010_f022_ip_range_metadata`。
- 结构证伪（直连 DB）：表集合不变；`ip_addresses` 列恰 7；`ip_addresses` 非主键唯一索引恰 `{ux_ip_addresses_cluster_ip_active}`；排他约束仅 F020 既有 `ex_ip_address_ranges_active_no_overlap`；无触发器。
- 唯一性最终权威仍为 R-IP-001 partial unique；`cluster_id` 漂移查询恒 0 行。

结论：**无数据库变更，与 Architecture 结论一致。**

---

## Backend Review

- `schemas.py`：`IpAddressAutoAllocateRequest` 字段集合恰 `{network_interface_id, ip_address_range_id}`，`extra="forbid"`；`IpAddressManualAllocateRequest` 未改。
- `service.py::allocate_ip_auto`：范围段 `get_active` 读取 + 归属比较 + 单段 `select_first_free` + `create_ip_address` 写入；`_RANGE_UNAVAILABLE_DETAIL` / `_NO_AVAILABLE_IP_DETAIL` 稳定判别值正确；所有拒绝发生在写入之前。
- `select_first_free` 语义未改（仍支持 range 列表，实际只传单段）。
- 无第二处写 `cluster_id`、无 `deleted_at` 写入、无 raw SQL、无新增抽象。
- **`errors.py` 改动**：`NotFoundError.__init__` 新增可选 `details`（默认 `None`），向后兼容——全部既有调用点均以 `NotFoundError()` 无参调用，行为不变；无副作用。

---

## API Contract Review

- 自动分配：请求 `{network_interface_id, ip_address_range_id}`；响应仍**恰 5 字段** `{id, network_interface_id, ip_address, created_at, updated_at}`，无回显扩展。
- 错误判别值定稿表与实现**逐条一致**：`VALIDATION_ERROR`（field）/ `NOT_FOUND`（`[]` 与 `IP_ADDRESS_RANGE_UNAVAILABLE`）/ `CONFLICT`（`IP_ADDRESS_RANGE_UNAVAILABLE` / `NO_AVAILABLE_IP` / `DUPLICATE`）。
- **逐字未改验证**：`§3.2 allocate-manual` 段落 base 与 head 完全字节相同；`docs/api/f005-ip-address.md` 整文件未改；`§2` 响应结构完全字节相同。

---

## Frontend Review

- `IpAddressAllocateDialog.vue`：auto 模式新增**必选**「目标地址范围」下拉；只读链仅用于渲染选项；未选 / Loading / Error / Empty 下均不可提交。
- 三态互异：`empty` / `loading` / `error` / `success` 以 `data-state` 与结果区 / 错误区区分；Empty 态禁用自动提交。
- 错误分支按 `error.code`（结合 `details[].code`）渲染固定文案，**不解析 `message`**；新错误码文案互异（Tester 以哨兵 `message` 验证不渲染）。
- `cluster_id` 仅作范围段查询参数，绝不回填分配请求；未新增强业务校验 / 依赖。

---

## Test Review

- **AC 覆盖**：AC-01 ~ AC-20 均有独立探针覆盖；Developer 与 Tester 测试互为交叉验证，Reviewer 全部独立通过。
- **对抗 / 边界**：缺 / `null` / `abc` / `1.5` / `[]` / `{}`；跨 Cluster 与 NIC 404 区分；字面 vs 数值边界（`010.0.0.1` / `10.0.0.1/16`）；网络地址不跳过；软删释放；范围外 F005 仍 201。
- **并发**：真实线程 auto vs manual vs F005 同一地址竞争，至多一条 201，其余 `409 DUPLICATE`，无 5xx，漂移 0。
- **结构证伪**：`information_schema` / `pg_indexes` / `pg_constraint` / `alembic_version` 证明无新增结构。
- **静态 guard 只增勿弱**：`G-F021-2` 精确演进为 `{network_interface_id, ip_address_range_id}`；前端 guard 增补白名单成员并以精确 import 名称集合钉死用途，保留全部禁止项，未删除断言。

---

## Findings

### BLOCKER

None。

### HIGH

None。

### MEDIUM

None。

### LOW

**REV-1**

```text
Severity:  LOW
Layer:     Backend / API
Location:  backend/app/ip_allocations/schemas.py:29（ip_address_range_id: int）
Problem:   Pydantic 默认 lax int 会对 JSON 数值字符串与布尔做强制转换：
           "7"→7、true→1、false→0、1.0→1 均被接受后进入范围段查找，
           而非按契约 §3.1 / AC-02 拒绝为 400。
Evidence:  '7'->ACCEPTED 7；True->ACCEPTED 1；False->ACCEPTED 0；1.0->ACCEPTED 1；
           'abc' / 1.5 / None -> REJECTED。
Impact:    与契约字段类型 integer 存在字面松紧差异；不产生数据完整性风险，
           且与既有 network_interface_id 及平台全部 id 字段行为完全一致，非 F023 引入。
Expected:  若要求 id 字段严格拒绝字符串 / 布尔，应由 Architect / Product 作为
           跨端点契约决策统一处理（F020 的 vlan 已选用 StrictInt），不在 F023 单点修改。
Suggested Owner: Architect（跨端点决策）/ Backend（如决策为严格化）
```

### NOTE

**REV-2（可接受的范围演进）**：`frontend/tests/ipAddressAllocationNoClientValidation.spec.ts` 的静态 guard 有意识地将 `getNetworkInterface` / `getBareMetal` / `listIpAddressRanges` 列入分配对话框白名单。这是 Architecture「方案 1 只读链」的预期演进，且以精确 import 名称集合断言钉死用途，未构成静默弱化。

**REV-3（已记录的并发窗口）**：范围段校验与范围段并发软删不互相串行（契约 §6.5 / R-IP-010 禁止新约束）。均为可重试瞬态，契约已明文记录不消除。

**REV-4（V1 规模上限）**：前端范围段下拉使用 `page_size=200`（`IpAddressAllocateDialog.vue`）。超过 200 个活跃范围段的 Cluster 下拉会不完整；Architecture 方案 1 明文接受 V1 规模，非缺陷。

**REV-5（证据元数据）**：Tester 报告头部记录 `HEAD: 608a695`，而测试资产提交于候选 HEAD `dfe2af7`；属报告元数据滞后，非功能缺陷。批准绑定候选 HEAD `dfe2af7`。

---

## Existing Defects

**Tester 报告 O-01（LOW，pre-existing）** — 逐项复核：

- 严重程度：**确认 LOW**。lax int 转换不产生数据完整性风险，且是全平台 id 字段既有行为，非 F023 引入。
- 是否真正符合 Contract：契约字段类型为 `integer`，严格意义下 `"7"` / `true` 属「非整数」；存在**字面松紧差异**，但不阻塞 F023。
- 是否应阻塞 Merge：**否**。改由 Architect 决定是否统一严格化（见 REV-1）。

---

## Non-blocking Follow-ups

1. **REV-1 / O-01**：由 Architect 决策是否对 id 类字段统一采用严格整数（`StrictInt`），若采纳应作为跨端点契约变更单独登记。
2. **REV-4**：范围段下拉 `page_size=200` 上限；未来若数量增长，考虑分页 / 可搜索下拉。
3. **REV-2**：静态 guard 白名单演进已记录；后续新增只读依赖须同步更新白名单并重跑组件探针。

---

## Unreviewed Areas

- **真实浏览器人工 E2E**：组件行为经真实挂载 + 真实前端 API client 集成探针覆盖（与 F021/F022 项目既有验证标准一致）。
- **全量后端 1239 / 前端 809 回归**：Reviewer 未逐条重跑全量（时间成本），已独立重跑 F023 全部后端专项 + F021 分配全量 + 全部改动的前端 spec + ruff + typecheck；全量结果采信 Tester 记录并与本次抽样一致。

---

## Verdict

```text
APPROVED WITH FOLLOW-UP
```

候选实现（`dfe2af7`）忠实满足已确认的 F023 产品需求与修订后 R-IP-006 / R-IP-009，符合 Architecture Handoff 与 ADR-0002/0003/0004/0005，无数据库变更，无超范围实现，测试可信。无 BLOCKER / HIGH / 需当前修复的 MEDIUM。

**批准仅对以下证据有效**：Base `dd159f3`、候选 HEAD `dfe2af7`、merge-base `dd159f3`。后续代码、契约或 Base 变化须重新测试 / Review。