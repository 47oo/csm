# F006 虚拟机登记 — REVIEW 报告

- **Task**：F006（FEATURE，P0，M3，deps [F004]）— Reviewer 独立复核
- **Status**：`APPROVED WITH FOLLOW-UP`
- **日期**：2026-10-09
- **角色**：Reviewer（只读；协调器持久化本报告）

## Basis

- requirements-v3.md revision 3（§4、§4.1、§6、§8、§9、§18、§21–§23、§27、§31 T08/T09/T19/T23/T24/T25/T38/T39）
- docs/api/F004.md v3（READY；§2.5/§3/§4/§6.2–§6.6/§8）；docs/database/f006-virtual-machine.md v1（DB-D53–D63）；d01-conventions.md v5（§3/§5.2/§5.5）
- docs/features/F006/{product,architecture(§14/DR-57–DR-71),implementation,test-report(TD-2/TE-1)}
- 批准核验：project.approval（用户 2026-10-06 批准 plan_revision 4，覆盖 F006）；execution.authorization 含 F006；Contract v3 由 Architect、DB v1 由 Database 签核；pending_changes 空；validate_project_state.py VALID。TE-1 结论 TEST PASS。

## Scope Reviewed

| 项 | 值 |
| --- | --- |
| Branch | feature/F006-virtual-machine |
| start_commit | d001fc41310fd1f07edbe3a5503e7bbb059405f2 |
| Base | v3 = d001fc4 |
| merge-base | d001fc4 |
| HEAD（候选） | f9607f6（实现提交 d3b36e9） |
| 范围 | git diff d001fc4..f9607f6，7 提交；backend+frontend 23 文件 +3730/−50 |
| 完整性 | 工作区 clean；无未跟踪交付物 |

## 适用层结论

| 层 | 结论 | 要点 |
| --- | --- | --- |
| 产品与领域 | PASS | A1–A17 落地；未新增/静默改变对象、关系、状态、唯一性、生命周期；metadata 归 Resource（I-3→DR-69）有据 |
| 架构/Contract | PASS | F004 v3 §2.5、D01 v5 §5.5、DR-57–DR-71 一致；宿主四条件、换 Host 审计、Host 引用删除保护、VM 恢复重检、互斥 422、无独立端点、审计白名单扩 virtual_machine |
| 数据与 Migration | PASS | 0006 表/约束/双触发器/FK CASCADE+RESTRICT/索引/回填守卫/单一 head/downgrade 对称经真实 PG 复现；detail 无 metadata/version/时间戳 |
| 功能正确性 | PASS（1 MEDIUM 并发缺口见 Findings） | 容量口径、host 显式 null、disk_gb=0 vs null、严格整数、hypervisor 空/纯空白/超长、PATCH exclude_unset、互斥 422、点路径正确 |
| 可维护性 | PASS | 校验集中；无过度抽象、无 500/静默忽略；检查器复用注册表 |
| 前端 | PASS | Host 选择器状态齐全；未知「—」非 0；disk_gb=0「明确无磁盘」；MiB/GiB；409 不静默重试；422 点路径 |
| 测试充分性 | PASS（1 NOTE） | 独立重跑 TE-1 证据成立；F006 32 例 + 全量 183/1 通过 |
| 安全与范围 | PASS | extra=forbid、无敏感内容入审计、无无关重构/新依赖、无越权端点 |
| 变更与批准 | PASS | Plan revision 4 覆盖 F006；签核版本匹配；无 pending_changes |

## Findings

### F006-REV-1 — 恢复 VM 与 Host 软删并发存在未串行化窗口（MEDIUM，非阻塞，建议修复）
- **Layer/Location**：Backend；`backend/app/services/resource.py::restore_resource`（依赖重检 check_dependencies 为普通 SELECT，未对 Host 行加锁）与 delete_resource（Host 软删先 FOR UPDATE 再跑引用检查）。
- **证据/复现**：独立探针（真实 PG 两连接）按 restore 语句序：①restore 事务对目标 Host 非锁定读取并 check_dependencies→[]（Host 未删）；②并发 delete_resource(host) 成功提交（VM 仍软删，引用检查放行）；③restore 条件 UPDATE deleted_at=NULL 提交。最终 VM.deleted_at=None 且 HOST.deleted_at=<ts>（违反 §9「未删除 VM 须关联未删除 BARE_METAL Host」）。
- **影响**：存在未删除 VM 指向已软删 Host 的不一致（VM 的 host 详情仍展开，PATCH 容量会被 host_valid 触发器 422，需换 Host 或随 Host 恢复）；可自愈、无数据丢失/安全影响；触发需两个 ADMIN 操作窄窗口并发。
- **建议**：restore_resource 依赖重检前对 host_resource_id 指向的 Resource 行 SELECT ... FOR UPDATE（与 DR-71 同机制同锁序）；architecture §14 / Contract §2.5/§6.6 明示；或显式记录接受残余风险的理由。Owner：Architect（机制）+ Backend（落地+回归）。
- **必须修复**：否（按当前契约/设计未强制；窗口窄、可自愈、非数据丢失/安全），但强烈建议本 Feature 内或紧邻修复循环关闭以与 DR-71 一致。

### F006-REV-2 — PATCH VM 提交 hardware 时版本冲突(409)抢先于类型不适用(422)（LOW，非阻塞）
- **Location**：`backend/app/services/resource.py::update_resource`（virtual_machine 校验已前置 version，hardware 分支仍在其后）。
- **证据**：PATCH VM + hardware（对象）+ 过期 version → 409 而非 §6.4 预期 422；正确 version 时 422。
- **影响**：仅错误码优先级，两者均正确拒绝，无数据/安全影响。**建议**：hardware/virtual_machine 适用性判定一并前置 version。Owner：Backend。**必须修复**：否。

### F006-REV-3 — VM 响应 host 缺失回退 hostname=""（NOTE）
- **Location**：`backend/app/schemas/resource.py::build_virtual_machine_out`。FK RESTRICT 下不可达；建议加注释或显式内部错误。Owner：Backend。**必须修复**：否。

### F006-REV-4 — 缺 VM+hardware:null / BARE_METAL+virtual_machine:null 显式 null 直证（NOTE，测试边界）
- 行为经代码分析正确（Pydantic 解析期 422），仅缺直接断言。Owner：Tester。**必须修复**：否。

## 旧缺陷复核

| ID | 原严重度 | 复核结论 | 证据 |
| --- | --- | --- | --- |
| F005-REV-1（PATCH VM+hardware 版本抢先） | LOW | 仍存在，同类复发为 F006-REV-2（非阻塞） | 代码路径未变，virtual_machine 已前置而 hardware 未对称 |
| F006-TE-1-01 | NOTE | CLOSED | TE-1 已在 TD-2 修正 |
| F006-TE-1-02 | NOTE | 确认，非缺陷 | A15 由真实 ASGI + 真实 PG 覆盖 |
| F005-REV-2/3/4 | NOTE/LOW | 不在 F006 范围，未复发 | 未触碰对应代码 |

未发现 Tester 漏报的 BLOCKER/HIGH/必须修复 MEDIUM。

## Verification（独立执行，真实环境）

| # | 操作 | 结果 |
| --- | --- | --- |
| 1 | docker build --target test + pytest F006 专属 -q（postgres:16，独立库） | 32 passed |
| 2 | pytest tests -q | 183 passed, 1 skipped（skip 环境性） |
| 3 | 迁移/触发器/CHECK/FK/回填守卫 | 单一 head 0006；up/down/up 对称；回填守卫三例；双触发器四负例；confdeltype c/r；disk_gb=0≠NULL 均 PASS |
| 4 | npm run typecheck/build/smoke:client | 0 错误；49 modules；64 passed, 0 failed |
| 5 | F006-REV-1 并发探针（两连接真实 PG） | 复现 VM.deleted_at=None 且 HOST.deleted_at 已置 |
| 6 | validate_project_state.py | PROJECT STATE VALID |
| 7 | Git 基线 | HEAD=f9607f6；Base=v3=d001fc4；merge-base=d001fc4；工作区 clean |

## Follow-ups（均非阻塞）

1. F006-REV-1（Architect + Backend）：restore_resource 依赖重检纳入 DR-71 锁定协议（Host 行 FOR UPDATE，锁序同 create/rehost），补真实并发回归；或记录残余风险。
2. F006-REV-2（Backend）：hardware/virtual_machine 适用性判定前置 version，补 stale-version 用例。
3. F006-REV-4（Tester）：补显式 null 直证。
4. F006-REV-3（Backend）：不可达空 hostname 分支加注或改显式内部错误。

## 未审查项 / 证据边界

- 未独立重跑完整 Compose/Nginx 全链路（TE-1 已记录经入口 Nginx 真实往返与同源 CSRF）。
- 未做真实浏览器 DOM/E2E（非必要判据）。
- B25/A13 物理 FK 为 raw SQL 机制级；B33 审计回滚为 monkeypatch 注入；DR-71 并发为真实行锁竞争非大规模压测。
- Cc/Cf 仅应用层保证、DB ASCII backstop（DB I-5 已知差异）。
- 完整 T08/T09/T19/T23/T24/T25/T38/T39 与 §32 上线验收、F007+、F013/F014/F015 不在本 Feature。

## Issues / Next

- 无 BLOCKER/HIGH/必须修复 MEDIUM；无未决产品问题；无越界端点/无关重构/新依赖。
- metadata 归属由 I-3→DR-69/DB-D57/Contract v3 明示裁定为 Resource 公共字段，有据非静默。
- 结论 `APPROVED WITH FOLLOW-UP`：核心验收满足、必要验证可信，仅含明确非阻塞跟进项。
- 下一步：由协调器按 Git Workflow §5 判定 Merge Gate（批准仅对候选 HEAD f9607f6 与 Base d001fc4 有效）；Merge/DONE 不由本报告授予。