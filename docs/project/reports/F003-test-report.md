# F003 计算资源统一列表、详情与服务端分页 — Test Report

> Status: READY FOR REVIEW
> Document Type: Test Report（独立验证）
> Feature: F003（Epic E2，P0）
> 候选 HEAD：`9757994`；分支 `feature/F003-resource-list-detail`；base `v2`
> 测试日期：2026-09-28
> 依据：`requirements-v2.md` §4.3/§6.2/§6.3/§8/§9.2/§9.4、§10 场景 8/32 与 BQ-AA/W；`docs/api/F003.md`、`docs/api/F002.md`、`docs/api/F006.md`；`docs/architecture/F003-resource-list-detail.md`

## 环境
Docker（独立 postgres:16 容器/网络 + 独立 uvicorn 探针服务）、Node 22 + pnpm。本 Feature 无数据库层。

## 实际执行与结果
| 命令/验证 | 结果 |
| --- | --- |
| 后端 `pytest`（真实 PostgreSQL，全量） | **177 passed**（F003 专测 14） |
| 独立 HTTP 探针（真实 uvicorn + PG，56 断言） | **56/56 PASS** |
| 前端 `pnpm test` | **20 files / 451 tests passed** |
| 前端 `pnpm build` | 成功 |

## 场景覆盖（PASS）
- 作用域：`cluster_id` 缺失/非法 400；仅返回本集群仍存资源、跨集群不串数据；`scope` 回显。
- 类型/状态筛选（全部/裸金属/虚拟机、状态）与非法值 400。
- 分页边界/`total`/跨页无重复；`sort` 白名单/非法；默认按名称。
- 搜索：名称部分/大小写不敏感/`%`_ 字面量；按 IP 部分且仅本集群；同名 IP 跨集群只返回本集群；`q` 命中 id；权重排序（完全>前缀>id>包含）。
- 列表列：`management_ip`（有/`null`）、`resource_type_label`/`status_label`、`updated_at`（RFC3339）。
- 详情复用 `GET /resources/{id}`：无 IP 网卡 `ips: []`（场景 8）、状态来源操作者、`management_ip: null`、404。
- 权限：viewer/maintainer/admin 可读、未登录 401；未新增写端点（`PATCH`/`DELETE` 405）。
- 不存在 cluster_id/空集群/超大 page → 200 空列表且 total 不变；只读无审计/历史副作用。

## 缺陷
| ID | Severity | 说明 |
| --- | --- | --- |
| F003-N-01 | NOTE | 计划 `head_commit` 落后（协调器 Merge 时更新）。 |
| F003-N-02 | NOTE | `sort=`/`resource_type=` 空串返回 400（Contract 仅定义省略=全部）；前端不发空值，不影响。 |
| F003-N-03 | NOTE | `q` 在集群内全量后 Python 侧权重排序（架构 §4.3 `PROPOSED` 允许），千台规模可接受。 |

无必须修复缺陷。

## 未验证项
- 前端↔后端真实浏览器 E2E：F003 仅要求 Vitest → NOT_REQUIRED（归 F011）。
- P95 性能（§9.2 测量方法 OPEN）；场景 56 全局 IP 查询（F010）；详情「服务」（F007）与类型摘要/专有字段（F004）。

## 结论
适用验收项全部 PASS，无必须修复问题。**READY FOR REVIEW**。

## Git（只读）
`git rev-parse`、`git status`、`git branch`、`git log`、`git merge-base`、`git diff`（无写操作）。HEAD=`9757994`，工作区 clean。