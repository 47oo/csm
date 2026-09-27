# F005 网段、保留地址与网段历史写入 — Test Report

> Status: READY FOR REVIEW
> Document Type: Test Report（独立验证）
> Feature: F005（Epic E4，P0）
> 候选 HEAD：`d6c3f83`；分支 `feature/F005-network-segments`；base `v2` = `dd6e22b`
> 测试日期：2026-09-25
> 依据：`requirements-v2.md` §4.6/§5/§6.5/§4.4/§2.1/§9.1/§10 场景 10/12/53/60/82/51/52/65 与 BQ-M/N/O/R/W/Z；`docs/api/F005.md`；`docs/architecture/F005-network-segments.md`；`docs/database/F005.md`

## 环境
Docker（独立 postgres:16 容器/网络，PostgreSQL 16.15）、Node 22 + pnpm。测试后清理临时资源。

## 实际执行与结果
| 命令/验证 | 结果 |
| --- | --- |
| 后端 `pytest`（真实 PostgreSQL，全量） | **91 passed** |
| Tester 独立探针（真实 HTTP + PG） | **80/80 PASS** |
| 前端 `pnpm test` | **11 files / 266 tests passed** |
| 前端 `pnpm build` | 成功 |

## 场景覆盖（PASS）
- 名称去空格/区分大小写/纯空白拒绝/跨集群同名/删除后可复用。
- CIDR 规范化与同集群唯一（`192.168.1.5/24`≡`192.168.1.0/24`）、跨集群相同 CIDR 允许、IPv6/非法 422。
- 同集群重叠仅提示允许保存（`overlaps`/`has_overlap`）。
- 场景 53 保留/网关/自动范围越界拒绝且原配置不变；自动范围成对/起≤止/在 CIDR 内。
- 删除前置：保留地址 409、网关未清 409、二次确认不匹配 422 不删除、乐观锁 409；保留地址单条真实删除；网关清空幂等。
- `auto_assignable_count`（未启用=0、网络/广播、`/31`/`/32`、自身与仍存重叠网段保留/网关排除、删后不再排除）；`allocated_count`=0。
- 权限（viewer 只读/写删 403、maintainer/admin、未登录 401）。
- 审计 `target_type='segment'` 6 类 action；`resource_history(update/delete)` 删除后保留；失败无残留。
- 场景 51 集群删除保护：含仍存网段的集群删除 → `409 CLUSTER_HAS_ASSOCIATIONS`（F005 RESTRICT FK 触发）。
- DB 约束：同集群 name/cidr_key 唯一、CHECK、FK RESTRICT、`cidr_key` 生成列、保留地址可真实删行（无 append-only 阻止）。

## 缺陷
| ID | Severity | 说明 |
| --- | --- | --- |
| INFRA-F005-01 | NOTE | `backend/.dockerignore` 排除 tests，直接 `docker run csm-backend pytest` 收集 0 项，需挂载 tests 执行（生产镜像不含测试属预期）。 |

无 BLOCKER/HIGH/MEDIUM/LOW 实现缺陷。

## 未验证项
- F002 `SEGMENT_HAS_INTERFACES`、F006 `SEGMENT_HAS_ALLOCATIONS`/`CIDR_IMMUTABLE` 端到端引用拒绝依赖后续 Feature（非 F005 闭环）。
- 场景 52/65 分配冲突端到端属 F006；场景 61/64 管理员历史查询属 F012。
- 前端真实浏览器 E2E（F005 未要求）。
- 数据库 collation 对名称大小写确定性的部署差异。

## 结论
适用验收项全部 PASS，无必须修复问题，未验证项均为后续 Feature 依赖。**READY FOR REVIEW**。

## Git（只读）
`git rev-parse`、`git branch`、`git status`、`git ls-files`（无写操作）。HEAD=d6c3f83，工作区 clean。