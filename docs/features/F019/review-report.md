# F019 接口侧选择并绑定 IP — REVIEW 报告

- **Task**：F019（FEATURE，P1，M10）— Reviewer，独立正式 Review
- **结论**：`APPROVED WITH FOLLOW-UP`（无 BLOCKER / HIGH / 必须修复 MEDIUM）
- **日期**：2026-10-15

## 审查范围

| 项 | 值 |
| --- | --- |
| Feature 分支 | `feature/F019-interface-ip-binding` |
| Base 分支 | `codex/v3.1`（SHA `0db1832`） |
| Base SHA / start_commit / merge-base | `0db18320fd59ac48cef1c3f86dd41b783b2b2ddd` |
| 首次批准 HEAD | `b4ad16c` |
| 最终批准 HEAD | `f270d28`（相对 `b4ad16c` 仅 docs/project/* 状态元数据，见「基线变更确认」） |
| 合并提交 | `2b53e04`（父：`0db1832`、`f270d28`；集成树与批准 HEAD 一致） |
| 审查范围 | `git diff codex/v3.1...f270d28`，14 文件 |

## 分层结论

- **需求与领域（PASS）**：纯前端编排，未新增实体/关系/状态/唯一性/生命周期/权限/错误码；AC1–AC7 与 §13.4 逐条一致。候选=同 Cluster/未绑定/未删由服务端过滤承担；绑定仅逐条 PATCH，产生 `ip_address` UPDATE Audit；仅绑定、不解绑/转移、不新建/自动分配；并发后到者 409。
- **架构与依赖（PASS）**：严格复用 F010 `GET /api/v1/ip-addresses`（§6.1）与 `PATCH /api/v1/ip-addresses/{id}`（§6.5）；`backend/app`、`backend/alembic`、`docs/api` 零改动；`layers{database:false,backend:false,frontend:true}`、`api_required:false` 与实际一致，`NOT_REQUIRED` 成立。
- **数据与 Migration（PASS）**：无 Schema/索引/迁移；绑定仅置既有可空列 `interface_id`；既有约束/触发器/乐观锁在真 PG 复验。
- **API 与实现（PASS）**：载荷恰 `{version,interface}`；查询参数与错误语义复用 F010，无自造映射。
- **前端（PASS）**：`interfaceIpSelection.ts` 纯逻辑正确（跨页保留、查询参数、address 数值升序串行、不重试、部分成功汇总、total 边界、门控）；面板 Loading/Empty/Error 显式区分、`total>items` 提示、提交后重取候选页；`InterfacesPanel.tsx` 懒加载按 interface_id 缓存、绑定后失效、入口门控；`ui/controls.tsx` 仅 1 行 `aria-label` 透传。
- **测试充分性（PASS）**：AC↔测试映射完整；真 PG 集成 + 机制级 + 静态核对分层合理；浏览器 DOM/E2E（F019-UNV-1/2/4）明确 NOT TESTED，未以构建通过替代，未降低验收。
- **安全与范围（PASS）**：无新增依赖、无无关变更、无敏感信息。

## Verification（独立复跑）

| 命令 | 结果 |
| --- | --- |
| `npm run typecheck` | 通过 |
| `npm run smoke:client` | 293 passed, 0 failed |
| 真 PG `pytest tests/integration/test_f019_interface_ip_binding.py -q` | 14 passed |
| 真 PG `pytest test_ip_addresses.py test_interfaces.py test_f019_…py -q` | 73 passed |

环境：`csm-backend-f019test` 镜像 + `csmtest_default` 网络 + 真实 PostgreSQL 16（`csm_test`，DB-D10 守卫满足）。

## Findings

| ID | Severity | Layer | 证据 | 期望 vs 实际 | Owner | 必须修复 |
| --- | --- | --- | --- | --- | --- | --- |
| REV-F019-1 | NOTE | Backend（F010） | `update_ip_address` 在 `interface` 变更时调用引用检查器；F019 候选必无 Endpoint 引用，返回空集 | AC5 满足；不误拒 | Architect（F010 边界） | 否 |
| REV-F019-2 | NOTE | Frontend | `interfaceIpTotalBoundary` 对异常形状 `total>0,items=0` 返回 `empty` | 防御性边界，正常分页不触发 | Frontend | 否 |
| REV-F019-3 | FOLLOW-UP | Frontend/Browser | F019-UNV-1/2/4 NOT TESTED | 无 DOM/E2E 工具；已用机制级 + typecheck + build + 静态核对替代并诚实标注 | 协调器 | 否 |

## Follow-ups

1. 引入浏览器 DOM/E2E 工具后补验 F019-UNV-1/2/4（Modal 交互、跨页多选渲染、部分成功渲染、懒加载/缓存失效、空/错/边界提示、大列表性能）。
2. 若未来需在契约层区分「绑定/解绑」的 Endpoint 引用检查语义，由 Architect 在 F010 边界内评估（REV-F019-1），不在 F019 范围。

## 未审查项

- 后端全量回归 `664 passed, 2 skipped` 未独立复跑（仅复跑 F019/F010/F007 相关 73 例及前端命令）；`2 skipped` 为既有 F016/migration 跳过。
- `npm run build` 未独立复跑（typecheck + smoke 已通过）。

## 基线变更确认（b4ad16c → f270d28）

协调器将 F019 状态由 `IN_PROGRESS` 修正为 `IN_REVIEW`（对齐测试放行状态机）并记录 Review 结果。`git diff b4ad16c..f270d28 --name-only` 仅含 `docs/project/{project-plan.yaml,backlog.md,milestones.md}`，无实现/测试/产品/架构/契约变更。Reviewer 确认此前结论与证据在新 HEAD 上依然成立，无需重新执行实现级 Review。

## 裁定

**`APPROVED WITH FOLLOW-UP`**，对 HEAD `f270d28`（Base `codex/v3.1`=`0db1832`）有效。Merge/DONE 由协调器按 `docs/project/git-workflow.md` 执行。