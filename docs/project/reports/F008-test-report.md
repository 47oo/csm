# F008 统一模糊搜索与下拉交互 — Test Report

> Status: READY FOR REVIEW
> Document Type: Test Report（独立验证）
> Feature: F008（Epic E6，P0，M2）
> 候选 HEAD：`1be29f4`；分支 `feature/F008-unified-search`；base `v2`（start `ce20ae9`）
> 测试日期：2026-09-28
> 依据：`requirements-v2.md` §7.5/§8.1/§8.2/§8.3、§9.2/§9.4、§10 场景 41/37/38/35/36/39/56；`docs/api/F008.md`、`F001.md` §2.1、`F003.md` §2.1、`F005.md` §2.1、`F006.md` §3.1；`docs/architecture/F008-unified-search.md`

## 环境
独立 postgres:16 容器/网络（测试库 + 探针库，未触碰生产库）；`python:3.12-slim` 后端镜像；Node 22 + pnpm 11。本 Feature 无数据库层。

## 实际执行与结果
| 命令/验证 | 结果 |
| --- | --- |
| 后端 `pytest`（真实 PostgreSQL，全量） | **196 passed**（含 19 新增） |
| 独立 HTTP 探针（真实 uvicorn + PG，40 断言） | **40/40 PASS** |
| 前端 `pnpm test`（修复轮 1 后，连续 3 次） | **28 files / 534 tests passed** |
| 前端 `pnpm build` | 成功 |
| Schema/端点不变式 | 13 张表；无 `lookup`/`search` 新端点、无新错误码；无 Migration |

## 场景覆盖（PASS）
- §8.2：集群 q 完全(code/name)>前缀>包含、同级 `sort=name`+`id`；网段 q 名称/CIDR(`192.168`)/用途/技术类型；`%`/`_`/`\` 字面量；去空格/大小写不敏感；空/空白 q 回初始。
- §8.2/§8.3：资源 q 回归（名称/纯数字 ID/本集群 IPv4 部分、跨集群隔离、权重）；服务端全量匹配 + 分页、`total` 完整、跨页无重复。
- §8.3/§4.1：前端 300ms 防抖、回车立即、加载态、旧请求不覆盖、键盘上下/回车/Esc/清空、无结果「没有匹配项」、清空回初始、稳定 ID 提交、未匹配不创建、仅仍存对象。
- §8.1 固定枚举：中文展示名/英文代码匹配（EnumSelect/enumSearch）。
- 场景 38/39/41/56（资源页侧）适用部分 PASS。

## 缺陷与修复
| ID | Severity | 说明 | 状态 |
| --- | --- | --- | --- |
| D-F008-01 | MEDIUM | 资源表单「网络范围」下拉未支持技术类型匹配；`FuzzySelect` 未被任何 view 接入。属 F008 已确认范围（§8.1）。 | **修复轮 1 已闭环**：接入 `FuzzySelect` + `searchOptions` 网段适配器（服务端 q、cluster_id 作用域、`sort=name`），保留选择/带出只读字段/切集群清理/可空保存语义；新增 14 项测试。 |
| — | NOTE | 首轮前端复跑在一次并发负载下出现既有测试偶发超时；随后连续 3 次 534 passed。 | 观察项，非必须修复 |

无 BLOCKER/HIGH/未闭环 MEDIUM。

## 未验证项
- 真实浏览器 E2E（jsdom 单测 + Mock；归 F011）。
- 键盘 ↑/↓ 高亮位移（交由 Element Plus 原生，未逐帧断言）。
- §9.2 性能 P95 基准（架构 `OPEN`，非阻塞）。
- 场景 35/36（宿主去重）与 F007/F010 适配点（非 F008 交付）。

## 结论
F008 明确定义交付项全部通过（后端 196、前端 534、探针 40/40，build 通过）；D-F008-01 已闭环；无端点/字段/错误码/Schema 变更。**READY FOR REVIEW**。

## Git（只读）
`git rev-parse`/`status`/`branch`/`log`/`diff`（无写操作）。