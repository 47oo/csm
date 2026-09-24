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

* V1 计划已冻结并归档到 `docs/project/v1/`（对应 tag `v1.0.0-demo`）。
* `docs/product/requirements-v2.md` 已新建，但 Status 为 **DRAFT — AWAITING CONTENT**（尚无 v2 需求正文）。
* `docs/project/project-plan.yaml` 现为 **v2 骨架**（`plan_completeness: incomplete`，`features: []`），**尚未生成任何 v2 Epic / Feature / Milestone**。

因此当前唯一阻塞是：**等待用户提供 v2 需求正文**。

## 3. 已确认的规划前提（2026-09-24 用户裁定）

1. **v2 是「领域与范围都变」**（不只是技术重构）。
2. **需求文档新建**：`docs/product/requirements-v2.md`。
3. **V1 待决增量 M13 不进入 v2**（F024 / F025）。
4. **无需迁移已部署 V1 的生产数据**。

仍待澄清（影响 v2 架构）：

5. **技术栈**：是否继续采用 ADR-0001 的 Python / FastAPI / PostgreSQL / Vue 栈，还是更换？
6. **部署形态**：是否仍为内网 Internal IP + HTTP，还是有新要求（域名 / HTTPS / 多环境）？

## 4. 归档状态（已执行）

用户已同意「把 V1 计划归档、v2 单独立项」。归档已在本分支完成：

1. ✅ 已将 V1 计划文件 `git mv` 到 `docs/project/v1/`：
   `project-plan.yaml`、`backlog.md`、`dependency-map.md`、`milestones.md`、`_planning-findings.md`。
2. ✅ 已新增 `docs/project/v1/README.md`，说明这是 `v1.0.0-demo` 的冻结快照，不再维护。
3. ✅ 已将 V1 历史文档中对 `docs/project/project-plan.yaml` 的引用更新为 `docs/project/v1/project-plan.yaml`（仅路径，内容未改）。
4. ⏳ 待 v2 需求确认后，依据需求运行 `/project`，生成 v2 的 Epic / Feature / Milestone 并写入顶层 `docs/project/project-plan.yaml`。

> 归档只涉及路径移动与引用修正，历史内容（含 Review / Test 证据）未改写。

## 5. 备注：M13 的归属

M13（F024 / F025）的 DRAFT 规划只存在于 `develop` 分支（commit `98141bc`），**不进入 v2**，也不在 `v1.0.0-demo` 范围内。
它作为 V1 轨道上的未决增量保留在 `develop`，不丢失；是否另行处理由用户决定。