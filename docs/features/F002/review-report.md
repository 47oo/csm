# F002 认证、初始账号与权限横切 — 正式 Review Report

- **Feature**：F002（FEATURE，P0，M1）
- **角色**：Reviewer（只读）
- **日期**：2026-10-06
- **Status**：`APPROVED WITH FOLLOW-UP`（协调器核验后持久化）

## Scope Reviewed

| 项 | 值 |
| --- | --- |
| Feature Branch | `feature/F002-auth-permissions` |
| Base / start_commit | `v3` = `549b1b581789f13144ba26db6eccc67a8153c93f` |
| merge-base | `549b1b5`（= Base） |
| 候选 HEAD（批准对象） | `529feb99fe3e131451e369512c611ee98a42d4c6` |
| 完整范围 | `549b1b5..529feb9`，44 files，+4114/−63；工作区 clean |
| 测试证据 | `docs/features/F002/test-report.md` TD-2 + TE-1 + TE-2（D-TE-1 FIXED，回归 47 passed,1 skipped） |

批准链核对：plan_revision 4 含 F002（用户 2026-10-06）；D02 认证部分签核（architecture.md CONTRACT 定稿）；docs/api/F002.md v1 READY；pending_changes 未命中 F002。

## 适用层结论

| 层 | 结论 |
| --- | --- |
| 产品与范围 | PASS（仅请求级横切、无业务对象/注册端点，A1–A7 未越界） |
| 安全 | PASS（argon2id；服务端不透明会话；令牌仅存 SHA-256；HttpOnly/SameSite/CSRF 同源守卫；响应排除 password_hash；日志脱敏；.env 未跟踪无凭据） |
| 架构与依赖 | PASS（DR-07–DR-16；仅新增 argon2-cffi 锁定；无禁用基础设施） |
| 数据与 Migration | PASS（DB-D13–D19 一致；约束名全名、gen_random_uuid、FK RESTRICT、索引；0002 up/down 对称） |
| API 与实现 | PASS（端点/字段/204/Cookie/错误码/401/403/409 与 Contract 一致；登录不泄露账号存在性；未认证先于权限） |
| 标识符一致性 | PASS（DR-14=DB-D14=服务层归一化=迁移 CHECK） |
| 前端 | PASS（登录三态；/auth/me 恢复；401 清态、403/409 显式、无静默重试） |
| 测试充分性 | PASS（真实 PG 约束/迁移、矩阵 6×3、CSRF、并发 bootstrap；D-TE-1 为未迎合实现的反例） |
| 变更与批准 | PASS |

## Findings（均非阻塞）

| ID | Severity | Location | 问题 | Owner | 必须修复 |
| --- | --- | --- | --- | --- | --- |
| R-F002-01 | LOW | DR-14/DB-D14/username CHECK | username 字符集由 D02 专业签核委派决定（非 ASCII 需放宽）；非未决产品问题 | Product/Architect（F015 前） | 否 |
| R-F002-02 | NOTE | Contract §3/test | 403 为机制级证据（无真实 ADMIN-only 端点），完整 T25 归 F003 | Architect/Tester（F003） | 否 |
| R-F002-03 | NOTE | csrf.py | Sec-Fetch-Site `same-site`（子域）被拒；与 Contract 一致，多子域需配 AUTH_ALLOWED_ORIGINS | Architect（F003+ 部署） | 否 |
| R-F002-04 | LOW | deploy/nginx/nginx.conf | TLS(443)/多级代理下 Host/X-Forwarded-Host 未端到端验证（默认/非默认 HTTP 已验证） | Backend/协调器（F003+） | 否 |
| R-F002-05 | NOTE | errors.py | _HTTP_CODE_MAP 增 405（与 Contract §5 允许一致） | Architect | 否 |
| R-F002-06 | NOTE | bootstrap_admin | 并发不同用户名理论可各建 admin（uq_users_username 兜底，同源凭据无法触发） | Backend | 否 |
| R-F002-07 | LOW | user.updated_at/session.last_seen_at | F002 无更新路径，两列未在运行中维护；F003+ 须落实 | Backend（F003/F015） | 否 |

无 BLOCKER / HIGH / 必须修复 MEDIUM。

## 旧缺陷复核

- **D-TE-1**（MEDIUM → FIXED）：确认 FIXED，判定恰当。提交 e5d99f2 的 nginx.conf 与 TE-2 被测一致，HEAD 含修复；独立复现 7 项全部符合 Contract §2.1（同源含端口放行、去端口/异源/cross-site 拒绝、默认口/无头放行）。
- TE-1 其它 NOTE（R1 机制级、登录限流 NOT_REQUIRED、B2 耗时不作统计测量、F001 V3b skip、浏览器 DOM、生产 Secure 仅 ASGI）：成立，已显式记录，未伪装通过。

## Follow-ups（非阻塞）

1. R-F002-01：F015 用户管理前由 Product 确认 username 字符集；如需非 ASCII 另开迁移放宽 CHECK（F002 无生产数据，成本低）。
2. R-F002-02：F003 首个真实 ADMIN-only 端点后回归 T25，替换机制级 403 证据。
3. R-F002-04：F003+ 引入 TLS/多级代理时补验同源写。
4. R-F002-07：F003/F015 引入用户更新路径时落实 updated_at 维护。

## 未审查项

未重跑完整集成套件与 Compose 全链路（依据 TE-1/TE-2 独立证据 + 本次关键项独立复核）；未做 B2 耗时统计测量；未端到端验证生产 TLS、浏览器 DOM；未审查 F003+ 业务权限/Audit/用户管理/限流（不在 F002 范围）。结论仅对候选 529feb9 与 Base 549b1b5 有效。

## 正式结果

**`APPROVED WITH FOLLOW-UP`** — A1–A7 满足，必要验证可信，无 BLOCKER/HIGH/必须修复 MEDIUM，无未决产品问题。Merge/DONE 由协调器按 git-workflow.md §5 判定。