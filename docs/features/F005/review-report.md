# F005 BareMetal 硬件与容量 — REVIEW 报告

- **Task**：F005（FEATURE，P0，M2，deps [F004]）— Reviewer 独立复核
- **Status**：`APPROVED WITH FOLLOW-UP`
- **日期**：2026-10-09
- **角色**：Reviewer（只读；未修改任何文件；协调器持久化本报告）

## Basis

- requirements-v3.md revision 3（§4.1、§6、§8、§18、§21–§23、§26–§27、§31 T37–T39、§35.2 Q10-A、§35.3 D01）
- docs/api/F004.md v2（READY，Architect 2026-10-09；§2.4/§3/§6/§8）
- docs/database/f005-bare-metal.md v1（DB-D45–D52）
- docs/architecture/d01-conventions.md v4（§3/§5.2/§5.4）
- docs/features/F005/{product,architecture(§9),implementation,test-report(TD-2/TE-1)}
- 批准核验：project.approval（用户 2026-10-06 批准 plan_revision 4，覆盖 F005）；execution.authorization 含 F005；F004 v2/D01 v4 由 Architect、DB v1 由 Database 签核；pending_changes 空；validate_project_state.py VALID。

## Scope Reviewed

| 项 | 值 |
| --- | --- |
| Branch | feature/F005-baremetal-hardware |
| start_commit | d335cfac2fb56c3753472918e19d3775375d725e |
| Base | v3 = d335cfa |
| merge-base | d335cfa |
| HEAD（候选） | 2796d74（实现提交 8f5dabe） |
| 完整范围 | git diff d335cfa..2796d74，6 提交，backend+frontend+docs |
| 完整性 | 工作区 clean；无未跟踪交付物 |

> 任务描述给的 `7b8e5df..2796d74` 跨越 F004；以 Plan 记录的真实 start_commit d335cfa（=merge-base）为准。

## 适用层结论

| 层 | 结论 | 要点 |
| --- | --- | --- |
| 产品与领域 | PASS | A1–A10 落地；未新增对象/关系/状态/唯一性规则 |
| 架构/Contract | PASS | F004 v2 §2.4、D01 v4 §5.4、DR-46–DR-56 一致；无独立端点；VM=null；审计扩 hardware |
| 数据与 Migration | PASS | 0005 表/约束/触发器/回填/FK CASCADE/单一 head/downgrade 对称；detail 无 version/时间戳，并发沿 resources.version |
| 功能正确性 | PASS（1 项 LOW 顺序偏差） | 空串/纯空白→422、严格整数、超长、整体 null/非对象/未知键、PATCH exclude_unset、响应组装、点路径正确 |
| 可维护性 | PASS | 校验集中于 normalization/service；无过度抽象 |
| 前端 | PASS | 仅 BARE_METAL 渲染；未知「—」非 0；gpu_count=0「明确无 GPU」；VM 不携带/不渲染；422 点路径；409 不静默重试 |
| 测试充分性 | PASS（2 NOTE 缺口） | TE-1 证据复现；1 处后端点路径未断言、1 处迁移断言放宽 |
| 安全与范围 | PASS | extra=forbid、无敏感信息、无无关重构/新依赖；列表级硬件过滤未实现（符合 I-1） |
| 变更与批准 | PASS | Plan revision 4 覆盖 F005；签核版本匹配；无 pending_changes |

## Findings

### F005-REV-1 — PATCH VM 提交 hardware 时版本错误抢先于 422（LOW，非阻塞）
- **Layer/Location**：Backend；`backend/app/services/resource.py`（`update_resource`：先判 `resource.version != expected_version`，再判 `resource_type != "BARE_METAL"`）。
- **证据**：探针——VM+过期 version+hardware → 409 VERSION_CONFLICT；VM+正确 version+hardware → 422 `hardware is only valid for BARE_METAL resources`。
- **期望**：Contract v2 §6.4 顺序 `401→403→body(422)→可见性(404)→版本(409)`，422 含「VM 提交 hardware」。
- **影响**：仅错误码优先级；二者皆为正确拒绝，无数据/安全影响。BARE_METAL 数值/字符串 422 由 Pydantic 在解析阶段拦截，点路径正确，不受影响。
- **建议**：载入对象后先做 hardware 适用性判断（非 BARE_METAL→422），再比较 version。
- **必须修复**：否。Owner：Backend。

### F005-REV-2 — 后端未断言 hardware 422 的 `fields[].field` 点路径（NOTE，测试缺口）
- **Location**：`backend/tests/integration/test_bare_metal.py`（仅断言 status_code==422）。
- **证据**：Contract v2 §2.4 要求点路径；独立探针确认后端实际返回正确（hardware.cpu_cores/gpu_count/memory_mb/manufacturer/model/metadata/nope）。
- **影响**：契约回归缺后端直接证据。**建议**：补 `error.details.fields[].field` 断言。**必须修复**：否。Owner：Tester。

### F005-REV-3 — 迁移头断言被放宽为字符串比较（NOTE，测试质量）
- **Location**：`backend/tests/integration/test_resource_constraints.py`（`assert head >= "0004_resources"`）。
- **影响**：F005 `test_bare_metal_constraints.py::test_migration_is_single_head` 已精确断言 0005 且 alembic_version 单一，整体单一 head 仍受保证。**建议**：改为 revision 图判断。**必须修复**：否。Owner：Tester/Backend。

### F005-REV-4 — DB 设计文档上游依据仍引用 D01 v3（NOTE，文档一致性）
- **Location**：`docs/database/f005-bare-metal.md:5`。
- **影响**：无行为影响，仅引用陈旧。**建议**：补注以 D01 v4 为准。**必须修复**：否。Owner：协调器/Database。

## 旧缺陷复核

| ID | 原严重度 | 复核结论 | 证据 |
| --- | --- | --- | --- |
| F005-TD-1-01 | LOW（文档） | CLOSED | FK 实际名 fk_bare_metal_details_resource_id_resources 与迁移/ORM/DB v1 一致；约束断言通过 |

未发现 Tester 漏报的 BLOCKER/HIGH/必须修复 MEDIUM。

## Verification（独立执行）

| # | 操作 | 结果 |
| --- | --- | --- |
| 1 | docker build --target test + pytest tests -q（真实 postgres:16，csm_test） | 151 passed, 1 skipped（skip=非 superuser 扩展假设，环境性，同 F004 基线） |
| 2 | F005 专属（test_bare_metal.py 19 + test_bare_metal_constraints.py 13） | 32 全 PASS；up/down/up、回填、触发器、CHECK、FK CASCADE(confdeltype='c')、单一 head、无 SN 唯一、无额外索引 |
| 3 | 独立探针（临时挂载） | VM hardware 顺序见 REV-1；点路径见 REV-2；其余正确 |
| 4 | npm run typecheck/build/smoke:client | typecheck 0 错误；build 47 modules；smoke 52 passed, 0 failed（F005 +9） |
| 5 | validate_project_state.py | PROJECT STATE VALID |
| 6 | 迁移/约束实际 DB 结构 | 11 列；4 范围 CHECK + 5 格式 CHECK + object CHECK；PK+FK CASCADE；类型触发器；metadata NOT NULL DEFAULT '{}'；无 deleted_at/version/时间戳 |

## Follow-ups（均非阻塞）

1. F005-REV-1（Backend）：调整 PATCH 校验顺序与 Contract §6.4 一致，附回归用例（VM+hardware+过期 version→422）。
2. F005-REV-2（Tester）：补后端点路径断言。
3. F005-REV-3（Tester/Backend）：迁移头断言改 revision 图判断。
4. F005-REV-4（协调器/Database）：同步 DB 文档 D01 引用版本。

## 未审查项 / 证据边界

- 未独立重跑完整 Compose/Nginx 全链路（TE-1 已记录经入口 Nginx 真实往返与同源 CSRF）。
- 未做真实浏览器 DOM/E2E（非必要判据）。
- 前端含 JSX 组件未纳入 Node 冒烟；以 typecheck+build+源码核对为准。
- B25 物理 FK CASCADE、B23 审计回滚为机制级/monkeypatch 证据（API 无物理删除路径）。
- Cc/Cf 仅应用层保证、DB 为 ASCII backstop（DB I-3 已知差异）。

## Issues / Next

- 无 BLOCKER/HIGH/必须修复 MEDIUM；无未决产品问题；无越界端点/无关重构/新依赖。
- 结论 `APPROVED WITH FOLLOW-UP`：核心验收满足、必要验证可信。
- 下一步：由协调器判定 Merge Gate（批准仅对候选 HEAD 2796d74 与 Base d335cfa 有效）；Merge/DONE 不由本报告授予。