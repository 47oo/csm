# F013 用户与角色管理 — Review Report

> Status: APPROVED WITH FOLLOW-UP
> Document Type: Feature Review Report
> Feature: F013（Epic E8，P0，根 Feature）
> Branch: `feature/F013-user-role-management`；Base `v2` = `e6999213a54eb2cab4f1b4f420c6e2a4158fe60f`
> start_commit：`e6999213a54eb2cab4f1b4f420c6e2a4158fe60f`
> merge-base(v2, HEAD)：`e6999213a54eb2cab4f1b4f420c6e2a4158fe60f`
> 候选 HEAD（approved）：`a4eac3a1367e7d9bd360b43134f30dfea2296b88`
> 完整范围 `v2...HEAD`：9 commits、67 files、+8583 / −28；工作区 clean
> Review 日期：2026-09-25

## 依据
`requirements-v2.md` §2.1/§4.9/§9.1/§10 场景 72–81/§11.1 BQ-V/W/X/Y；`docs/api/F013.md`；`docs/architecture/F013-user-role-management.md` 与 ADR-001…005；`docs/database/F013.md`；`docs/project/reports/F013-test-report.md`；`project-plan.yaml` F013。

## 独立验证（实际执行）
| 验证 | 结果 |
| --- | --- |
| 后端 pytest（真实 postgres:16） | **41 passed** |
| 前端 `pnpm test` | **5 files / 88 passed** |
| 前端 `pnpm build` | 成功 |
| 补充 HTTP 探针（真实 PG） | 边界与错误码符合 Contract |
| 自删审计探针 | 204；`user.delete` 审计保留、`actor_user_id=NULL`、`reserved_usernames` 保留 |

## 分层结论
- **产品与领域：PASS**。§4.9、场景 72–81 全部满足；BQ-V/W/X/Y 实现并验证；未静默新增规则；用户/角色不纳入受管资源与资源历史。
- **架构/依赖：PASS**。符合 ADR-001…005 与 F013 架构；模块边界清晰；`get_current_user` 每请求读库，角色/状态即时生效。
- **数据/Schema：PASS**。5 表与 `docs/database/F013.md` 一致（生成列唯一键、CHECK、乐观锁、reserved 只增、audit append-only 含 SET NULL 豁免、sessions CASCADE）。
- **API/Contract：PASS（1 项 LOW）**。12 端点齐全；错误码、problem+json 字段级、offset 分页、乐观锁、空列表/404/409 语义正确。
- **前端：PASS**。契约错误未隐藏；守卫与强制改密不可绕过；前端权限仅交互提示，服务端为最终边界。
- **安全：PASS（NOTE）**。HttpOnly Cookie（无 Secure，ADR-004）、SameSite=Lax、Argon2id、token 仅存 SHA-256、越权服务端校验。
- **测试充分性：PASS**。真实 PostgreSQL/HTTP 集成、边界与反向断言，无执行顺序依赖；未测项如实声明。

## 缺陷
| ID | Severity | 说明 | 必须修复 |
| --- | --- | --- | --- |
| F013-R-01 | LOW | 登录空字符串用户名/口令返回 `401` 而非 Contract §2.1 的 `422`（缺字段/null 仍 422）。无安全/数据影响，不影响验收。 | 否 |
| F013-R-02 | NOTE | 架构 §4.2 的 CSRF Origin/自定义头为 PROPOSED 未实现，仅依赖 SameSite=Lax。 | 否 |
| F013-R-03 | NOTE | `get_current_user` 每请求更新 `last_seen_at`（技术性写）。 | 否 |
| F013-R-04 | NOTE | 非绿地升级路径下 `admin` 若非内置则保护不生效；绿地 P0 不受影响。 | 否 |
| F013-R-05 | NOTE | `docs/database/F013.md` 个别旧措辞（btrim/约束名）与实现表述不一致，无行为差异。 | 否 |
| F013-R-06 | NOTE | 前端以 `username==='admin'` 判定内置账号，服务端以 `is_builtin` 为权威，固定账号一致。 | 否 |

无 BLOCKER / HIGH / 必须修复 MEDIUM；无未决产品问题。

## 旧缺陷复核
F013-T-01、F013-T-02 **已关闭**；F013-T-06/T-07 维持 NOTE（同 R-04/R-06）。

## 结论
各层均满足已确认需求与已批准决策，独立真实 PostgreSQL + HTTP 复核通过。**APPROVED WITH FOLLOW-UP**（候选 `a4eac3a`，Base `e699921`）。

## Follow-ups（非阻塞）
1. F013-R-01（空串登录 422）下一 Feature 或余量处理；Owner Backend。
2. F013-R-02 CSRF 增强（如需要）；Owner Architect→Backend。
3. F013-R-04 升级路径 `is_builtin` 回填策略文档。
4. 浏览器点击流与 `docker compose up` 端到端可择机补齐。

## 未审查项
浏览器真实点击流；`docker compose up` 整体编排；P95 压测（均超功能验收范围）。批准仅对候选 `a4eac3a` 与 Base `e699921` 有效。