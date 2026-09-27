# F002 计算资源登记、无 IP 网卡与一次原子提交基础 — Test Report

> Status: READY FOR REVIEW
> Document Type: Test Report（独立验证）
> Feature: F002（Epic E2，P0）
> 候选 HEAD：`ddde361`；分支 `feature/F002-resource-registration`；base `v2` = `93921ed`
> 测试日期：2026-09-27
> 依据：`requirements-v2.md` §2.1/§2.2/§4.1–§4.5/§6.4/§7.1–7.4/§9.1、§10 场景 2/5/6/28/29/30/34/42/46/47/48/50 与 BQ-AA/W/Z；`docs/api/F002.md`；`docs/architecture/F002-resource-registration.md`；`docs/database/F002.md`

## 环境
Docker（独立 postgres:16 容器/网络，含独立 HTTP 探针服务）、Node 22 + pnpm/vitest。测试后清理临时资源。

## 实际执行与结果
| 命令/验证 | 结果 |
| --- | --- |
| 后端 `pytest`（真实 PostgreSQL，全量） | **120 passed**（F002 专项 28） |
| Tester 独立探针（真实 HTTP + PG，60 断言） | **60/60 PASS** |
| 前端 `pnpm test` | **14 files / 329 tests passed** |
| 前端 `pnpm build` | 成功 |

## 场景覆盖（PASS）
- 名称去空格/区分大小写/裸金属与 VM 统一唯一/跨集群允许/删除后可复用。
- 同名新增 → `409 RESOURCE_NAME_EXISTS` + `existing_resource_id`/`existing_resource_type`，无第二条。
- 只读字段 `resource_type`/`cluster_id` 异值 400、同值容忍。
- 网卡增/改/删、`interfaces` 缺省/`[]`=未修改、payload 内重复接口名 422、网段不存在/跨集群 422。
- 整单原子（第二张网卡失败 → 资源与首张网卡无残留）。
- 删除前置（有网卡 409、无网卡可删、confirm 不匹配 422 不删除、乐观锁 409）。
- 权限（viewer 写/删 403、maintainer/admin、未登录 401）。
- 审计 `target_type='resource'`（create/update/delete）与 `resource_history`（update/delete，删除后保留，失败无残留）。
- 状态来源 BQ-AA（操作者 + 单一 `status_updated_at`，非状态编辑不刷新）。
- DB 约束（唯一、CHECK、复合 FK 同集群、冗余列钉住、RESTRICT）。
- F005 侧删除被网卡引用的网段 → `409 SEGMENT_HAS_INTERFACES`；F001 侧删除含资源的集群 → `409 CLUSTER_HAS_ASSOCIATIONS`。

## 缺陷
| ID | Severity | 说明 |
| --- | --- | --- |
| F002-T-01 | LOW | PATCH 提交与当前值相同的字段仍自增 `version` 并写一条 `change={}` 的 `resource_history(update)`；Contract 未禁止，前端已规避。建议 follow-up（与 F001 FU-4 / F005 NOTE-F005-3 同类）。 |
| F002-T-02 | NOTE | `docs/project/reports/` 无独立 F002 实现报告；本 Test Report 与 project-plan 作为追溯依据。 |

无 BLOCKER/HIGH/MEDIUM 实现缺陷。

## 未验证项
- 前端真实浏览器 E2E 与前后端真实联调：F002 Test Work 仅要求 Vitest（列表/详情展示属 F003）→ NOT_REQUIRED。
- 类型详情/宿主（F004）、IP/管理 IP（F006）、历史查询（F012）、统一列表（F003）、跨对象一致性（F009）属后续 Feature。
- `name` collation 部署差异（DB 设计 `OPEN`，本环境默认大小写敏感已通过）。

## 结论
适用验收项全部独立通过，无必须修复问题。**READY FOR REVIEW**。

## Git（只读）
`git status`、`git rev-parse`、`git merge-base`（无写操作）。HEAD=`ddde361`，工作区 clean。