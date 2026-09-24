# CSM v2 — Planning Intake

> Status: **AWAITING REQUIREMENTS**（等待用户提供 v2 需求）
> Owner: 用户 / Product
> 创建日期：2026-09-24
> 关联：`docs/project/releases.md`（v1.0.0-demo 边界）、`docs/project/git-workflow.md` §1.1

## 1. 背景

CSM V1 已冻结为演示版本 `v1.0.0-demo`（tag → `563eda3`，冻结分支 `release/v1`）。
用户决定后续版本（v2）跨度很大，**推翻并重构代码**，因此 v2 作为独立的开发线在 `v2` 分支进行。

## 2. 当前状态与阻塞

`AGENTS.md` §2 与 `/project` 流程（`.pi/prompts/project.md` Stage 2）要求：项目规划必须基于**已确认的完整需求来源**，
不得由 Agent 自行创造产品规则。

目前：

* `docs/product/requirements.md` 是 **CSM V1 产品需求**（CONFIRMED BASELINE），**不是 v2 需求**；
* 仓库中不存在任何 v2 / 重构需求文档；
* 因此 **v2 的 `project-plan.yaml` 尚未生成**，`docs/project/project-plan.yaml` 目前仍是 V1 计划（status `DONE`）。

在获得 v2 需求之前，**不得**凭空生成 v2 的 Epic / Feature / Milestone。

## 3. 启动 v2 规划前需要用户确认的输入

以下问题会直接决定 v2 的范围与架构，必须先由用户澄清（`AGENTS.md` §2.8）：

1. **v2 需求来源**：v2 是「领域不变、技术重构」还是「领域与范围都变化」？
2. **需求文档落点**：是否新建 `docs/product/requirements-v2.md`（或修订现有 `requirements.md`）？其权威来源是什么？
3. **V1 待决增量 M13**：`develop` 分支上存在未批准的 M13 规划（F024 集群概览聚合 / F025 搜索结果上下文展示）。
   它是否进入 v2 范围？还是先单独评估？
4. **数据连续性**：v2 是否需要迁移已部署 V1 的生产数据？若是，这是最高优先级的架构决策（影响 Schema / Migration 策略）。
5. **技术栈**：是否继续采用 ADR-0001 的 Python/FastAPI/PostgreSQL/Vue 栈，还是更换？
6. **部署形态**：是否仍为内网 Internal IP + HTTP，还是有新要求（域名 / HTTPS / 多环境）？

## 4. 待确认后执行的归档/重构步骤（尚未执行）

用户已同意「把 V1 计划归档、v2 单独立项」。为**避免现在机械移动造成跨文档引用大量损坏**
（`requirements.md` 与各 Handoff 中有大量 `docs/project/project-plan.yaml` 的精确引用），归档动作将与 v2 规划同时执行，步骤建议如下：

1. 将 V1 计划文件 `git mv` 到 `docs/project/v1/`：
   `project-plan.yaml`、`backlog.md`、`dependency-map.md`、`milestones.md`、`_planning-findings.md`。
2. 新增 `docs/project/v1/README.md`，说明这是 `v1.0.0-demo` 的冻结快照，不再维护。
3. 把 V1 产品文档中对 `docs/project/project-plan.yaml` 的引用更新为 `docs/project/v1/project-plan.yaml`。
4. 依据 v2 需求运行 `/project`，生成新的顶层 `docs/project/project-plan.yaml` 及其视图。
5. 同步 `repository-structure.md` / `releases.md` / `git-workflow.md`。

## 5. 备注：M13 的位置

M13 的 DRAFT 规划（F024 / F025）只存在于 `develop` 分支（commit `98141bc`），**不在** `v1.0.0-demo` 范围内，也不在 `v2` 分支上。
在决定其归属前，保持原样、不丢失。