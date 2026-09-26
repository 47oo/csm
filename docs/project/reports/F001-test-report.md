# F001 集群登记、身份、真实删除保护与集群本体权限审计 — Test Report

> Status: READY FOR REVIEW
> Document Type: Test Report（独立验证）
> Feature: F001（Epic E1，P0）
> 候选 HEAD：`14941e4`；分支 `feature/F001-cluster-identity-and-deletion`；base `v2`
> 测试日期：2026-09-25
> 依据：`requirements-v2.md` §4.1/§4.4/§6.1/§10 场景 50/51/58/59/61/64/71/82/§11.1 BQ-M/W/Z；`docs/api/F001.md`；`docs/architecture/F001-cluster-registry.md`；`docs/database/F001.md`

## 环境
Docker（postgres:16 独立容器/网络）、Node 22 + pnpm。所有临时容器/网络测试后删除。

## 实际执行与结果
| 命令/验证 | 结果 |
| --- | --- |
| 后端 `pytest`（真实 PostgreSQL） | **61 passed** |
| 前端 `pnpm test` | **7 files / 166 tests passed** |
| 前端 `pnpm build` | 成功 |
| 独立探针（真实 uvicorn + httpx + 真实 PG） | **85/85 PASS** |

## 场景覆盖（PASS）
- `code`：去空格+大写规范化判重、`^[A-Z0-9]{1,32}$` 格式、创建后不可改、真删后不复用。
- 名称：字符集/长度、拒绝空格不裁剪、区分大小写唯一、真删后可复用。
- 权限：viewer 写/删 403；maintainer 删除允许、写 403；admin 全允许；未登录 401。
- 删除：二次确认不匹配 422 且不删除；乐观锁 409；关联保护（RESTRICT 探针）→ 409 且回滚。
- 审计与 `resource_history` 写入、删除后保留；`reserved_cluster_codes` 保留；append-only 与 DB 约束。
- 列表分页/搜索/排序/空列表；用途可改；失败路径无审计/历史残留。

## 缺陷
| ID | Severity | 说明 |
| --- | --- | --- |
| NOTE-1 | NOTE | `docs/project/reports/` 无独立 F001 实现报告；本 Test Report 与 project-plan `last_result` 作为追溯依据。 |
| NOTE-2 | LOW/NOTE | PATCH 提交与当前值相同的字段时仍自增 `version` 并写一条 `change={}` 的 audit/history；Contract 未禁止，但与 NO_FIELDS 边界存在解释空间，交后续确认。 |

无 BLOCKER/HIGH/MEDIUM 必须修复项。

## 未验证项
- 场景 51/59 关联行为侧完整闭环需 F002/F005/F007 引入真实关联表；本 Feature 仅以 RESTRICT 探针验证规则侧与 409。
- 场景 58 跨对象归属需 F007；场景 61/64 管理员历史查询需 F012；场景 50 归 F002。
- 真实浏览器前端 E2E（project-plan 未要求，前端复用 F013 拦截层单测）。

## 结论
适用验收项全部 PASS，无必须修复问题，未验证项均为后续 Feature 依赖。**READY FOR REVIEW**。

## Git（只读）
`git rev-parse`、`git branch`、`git status`、`git diff --stat`、`git log`（无写操作）。HEAD=14941e4，工作区 clean。