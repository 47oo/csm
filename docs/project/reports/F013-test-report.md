# F013 用户与角色管理 — Test Report

> Status: READY FOR REVIEW
> Document Type: Test Report（独立验证）
> Feature: F013（Epic E8，P0）
> 候选 HEAD：`206261e`（前端），后端提交 `b99e619`
> 分支：`feature/F013-user-role-management`
> 测试日期：2026-09-25
> 依据：`requirements-v2.md` §4.9/§10 场景 72–81、§11.1 BQ-V/BQ-W/BQ-X；`docs/api/F013.md`；`docs/architecture/F013-user-role-management.md`；`docs/database/F013.md`

## 环境
宿主机无 pip/PostgreSQL；使用 Docker（postgres:16 独立容器/网络）、Node 22 + pnpm。所有临时容器/网络测试后删除。

## 实际执行与结果
| 命令/验证 | 结果 |
| --- | --- |
| 后端 `pytest`（真实 PostgreSQL） | **39 passed** |
| 独立探针（TestClient + 真实 PG） | **21/21 PASS**（另有 54 项探针，1 项为探针自身错误，修正后确认实现正确） |
| DB Schema 逐项核对（`\d`） | 与 `docs/database/F013.md` 一致（列/约束/索引/FK/触发器） |
| 真实 `uvicorn` + `curl` 全链路 | 符合 Contract（HttpOnly Cookie 无 Secure；problem+json 字段级；LAST_ADMIN/VERSION_CONFLICT/USERNAME_TAKEN 等） |
| `init_db.py` 重复执行 | 幂等（admin=1、bootstrap 审计=1） |
| 前端 `pnpm test` | **Test Files 5 passed / Tests 82 passed** |
| 前端 `pnpm build` | 成功（仅 chunk>500kB 警告） |

## 场景覆盖
场景 **72–81 全部 PASS**，覆盖：登录/未知/错误口令、禁用登录、登出失效、创建与用户名规则（仅字母数字 1–128、大小写敏感）、角色修改即时生效且用户名不可改、删除与用户名不复用、最后启用 admin 不可删/不可禁、改密/重置与会话撤销、越权 403 数据不变、审计 append-only。

## 缺陷 / 风险
| ID | Severity | 说明 | 状态 |
| --- | --- | --- | --- |
| F013-T-01 | MEDIUM | `backend/README.md` 的 docker 测试命令因 `.dockerignore` 排除 `tests/` 而收集 0 测试；需改为挂载源码或独立 test 镜像。不影响产品行为。 | 待修（文档） |
| F013-T-02 | MEDIUM（产品/架构风险） | 最后一个启用 admin 可经 `PATCH /users/{id}` 改角色为 viewer，导致启用 admin=0；Contract/BQ-X 仅禁止**删除/禁用**最后管理员，未禁止改角色。实现符合已批准 Contract，但与「系统至少保留一个可登录管理员」立意存在缺口。 | **需用户裁定** |
| F013-T-03 | NOTE | 协调器提交把计划状态改动漏提交（工作区曾非 clean）；本报告落稿一并修正。 | 已处理 |
| F013-T-04 | NOTE | `get_current_user` 每请求更新 `sessions.last_seen_at`（技术性写，非业务数据）。 | 接受 |
| F013-T-05 | NOTE | 最后 admin + 过期 version 返回 LAST_ADMIN 而非 VERSION_CONFLICT（Contract 未规定优先级）。 | 接受 |

## 未验证项
- 浏览器端真实点击流（无 headless browser）；以真实 HTTP API 冒烟 + 前端契约路径审查替代。
- `docker compose up` 整体编排未启动验证（仅分别验证 init 与 uvicorn）。
- P95 性能目标未压测（超出本 Feature 功能验收）。

## 结论
场景 72–81 全部通过；Contract 边界与 DB 约束经独立核验通过；前端 82 测试与构建通过。**READY FOR REVIEW**。

## Git（只读）
`git status`、`git log`、`git rev-parse`、`git branch`、`git diff`（只读；无写操作）。