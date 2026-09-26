# F001 集群登记、身份、真实删除保护与集群本体权限审计 — Review Report

> Status: APPROVED WITH FOLLOW-UP
> Document Type: Feature Review Report
> Feature: F001（Epic E1，P0）
> Branch: `feature/F001-cluster-identity-and-deletion`；Base `v2` = `1727490c1c67e9803331692ec0e242a0cf67cf8a`
> start_commit / merge-base：`1727490c1c67e9803331692ec0e242a0cf67cf8a`
> 候选 HEAD（approved）：`1db39fdcb5d12414d7b0824bd1026deeaeb387a5`
> 范围 `v2...HEAD`：27 files，+3556/−22；工作区 clean
> Review 日期：2026-09-25（第二轮，修复轮 1 后）

## 依据
`requirements-v2.md` §4.1/§4.4/§6.1/§9.1/§10 场景 50/51/58/59/61/64/71/82/§11.1 BQ-M/W/Z；`docs/api/F001.md`；`docs/architecture/F001-cluster-registry.md` 与 ADR-001…005、F013 复用基础；`docs/database/F001.md`；`docs/project/reports/F001-test-report.md`。

## 独立验证
| 验证 | 结果 |
| --- | --- |
| 后端 pytest（真实 postgres:16） | **64 passed** |
| 前端 `pnpm test` | **7 files / 166 tests passed** |
| 前端 `pnpm build` | 成功 |
| 独立探针（尾随换行、非 ASCII code、名称冲突回滚） | 通过；旧 REVIEW-1/2/NOTE-3 已消除 |

## 分层结论
- 需求与领域：PASS（§4.1.6–13、§4.4.7、§6.1、BQ-M/W/Z）。
- 架构与依赖：PASS（复用 F013，未反向依赖 users；关联保护最小机制）。
- 数据与 Migration：PASS（与 `docs/database/F001.md` 一致，append-only/生成列/约束）。
- API 与实现：PASS（5 端点、错误码、乐观锁、二次确认、关联 409）。
- 前端：PASS（列表/表单/删除二次确认/选择记忆/错误映射）。
- 测试：PASS（真实 PG 集成 + DB 约束；修复回归）。

## 缺陷
| ID | Severity | 说明 | 状态 |
| --- | --- | --- | --- |
| REVIEW-1 | MEDIUM | 名称正则 `$` 允许尾随换行 → 误报 409/500。 | 已修复（`a25a1d4`） |
| REVIEW-2 | LOW | Python/Postgres `upper` 对非 ASCII 不一致。 | 已修复（限 ASCII 输入） |
| NOTE-3 | NOTE | IntegrityError 统一误报 CODE_TAKEN。 | 已修复（按约束名映射） |
| FU-1 | LOW | 契约/需求措辞未写明 `code` 输入仅 ASCII；与实现/DB 口径漂移。 | 跟进（非阻塞，文档） |
| FU-2 | LOW | 前端 `ß` 等 Unicode upper 与服务端不一致（仅即时反馈）。 | 跟进（非阻塞，前端可选） |
| FU-3 | NOTE | 计划元数据 note/head_commit 滞后。 | 本最终状态提交处理 |
| FU-4 | NOTE | PATCH 提交同值仍自增 version 并写 `change={}`。 | 跟进（Product 确认，非阻塞） |

无 BLOCKER/HIGH/必须修复 MEDIUM。

## 结论
核心验收满足、真实集成验证可信，旧 REVIEW-1/2/NOTE-3 已消除。**APPROVED WITH FOLLOW-UP**（候选 `1db39fd`，Base `1727490`）。Merge `6ad6346` 由协调器按 Git Workflow 执行。

## Follow-ups（非阻塞）
1. FU-1 同步契约/需求措辞（`code` ASCII 输入口径）。
2. FU-2 前端镜像服务端 ASCII 校验（可选）。
3. FU-4 由 Product 确认 PATCH 同值是否记为一次变更。
4. 后续闭环：场景 50 归 F002；51/59 行为侧归 F007；58 跨对象归属归 F007；61/64 管理员历史查询归 F012。

## 未审查项
场景 61/64 的历史查询（F012）与关联行为侧完整闭环（F002/F005/F007）不在本 Feature；真实浏览器 E2E 未执行；第三方依赖供应链审计未做。