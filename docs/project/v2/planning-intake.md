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

* V1 计划已冻结，完整保留在 `release/v1` 分支与 tag `v1.0.0-demo`；`v2` 分支内不保留副本。
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

## 4. 归档状态

V1 计划已冻结，**不保留在 v2 分支内**，完整保存在 `release/v1` 分支与 tag `v1.0.0-demo`
（可用 `git show release/v1:docs/project/project-plan.yaml` 查看）。

1. ✅ 2026-09-24 曾将 V1 计划文件 `git mv` 到 `docs/project/v1/` 并新增其 `README.md`。
2. ✅ 同日按用户要求删除 `docs/project/v1/`；V1 计划统一保留在 `release/v1`。
3. ⏳ 待 v2 需求确认后，依据需求运行 `/project`，生成 v2 的 Epic / Feature / Milestone 并写入顶层 `docs/project/project-plan.yaml`。

## 5. 备注：M13 的归属

M13（F024 / F025）的 DRAFT 规划只存在于 `develop` 分支（commit `98141bc`），**不进入 v2**，也不在 `v1.0.0-demo` 范围内。
它作为 V1 轨道上的未决增量保留在 `develop`，不丢失；是否另行处理由用户决定。

## 6. 应用代码重置（已执行）

2026-09-24，用户确认「V2 是重构且重新进行需求分析」，据此在 `v2` 分支对 V1 应用代码做一次**显式重置提交**
（不是改写历史；V1 代码完整保留在 `release/v1` 与 tag `v1.0.0-demo`）：

**已删除**（V1 应用代码与技术形态，328 个跟踪文件）：

```
backend/  frontend/  tests/  deploy/
alembic.ini  Makefile  pyproject.toml  requirements.txt  requirements-dev.txt
docker-compose.dev.yml  docker-compose.prod.yml
.env.example  .dockerignore
```

**保留**：`docs/`、`.pi/`、`AGENTS.md`、`README.md`（已改为 v2 基调）、`.gitignore`（通用，与技术栈无关）。

**理由**：① 防止 Agent 与规划流程锚定 V1 实现（`AGENTS.md` §3 需求优先于实现）；② V2 领域与范围都变，V1 代码不可直接复用；
③ V2 技术栈尚未确认，保留 Python/Vue 脚手架等于预选 ADR-0001，与重新架构矛盾。

**未做**：不改写历史、不动 `main` / `release/v1` / tag；V1 产品、架构、ADR、Review、Test 文档暂不移动，
仅视为参考，其权威性由 V2 文档取代。

## 7. V1 设计文档清空（已执行）

2026-09-24，用户进一步要求「清空 docs 里以前的需求内容，因为需求要重新做，减少干扰」。据此从 `v2` 分支移除 V1 设计文档
（共 140 个文件，完整保留在 `release/v1` 与 tag `v1.0.0-demo`）：

* `docs/product/requirements.md`、`domain-model.md`、`domain-model.yaml`、`domain-conflict-handoff.md`、`handoffs/`；
* `docs/architecture/`（含 `adr/`）、`docs/database/`、`docs/api/`、`docs/deployment/`、`docs/reviews/`、`docs/test-reports/`。

**保留**：`docs/product/requirements-v2.md`（V2 需求）、`docs/project/`（流程 + 本目录）。

**理由**：防止 V2 需求分析与架构重新引入 V1 既有规则（`AGENTS.md` §2 不得自行创造/沿用未确认规则，§3 需求优先）。

## 8. 待处理的连带项：`.pi` 与 `AGENTS.md`

下列内容仍指向已移除的 V1 文档，属 V2 立项的连带项，**尚未处理**（需要用户/角色决策，不自行修改）：

* `AGENTS.md` §3 将 `docs/product/domain-model.md` 定为权威领域模型来源；V2 领域模型建立后需重新指向。
* `.pi/skills/resource-domain/SKILL.md` 内含 V1 领域知识，可能继续向 V2 规划注入旧规则。
* `.pi/agents/*.md` 与 `.pi/prompts/*.md` 大量引用 `docs/product/`、`docs/architecture/`、`docs/database/`、`docs/api/`。

建议在启动 V2 规划前单独评估：保留 / 改写 / 归档这些引用与 V1 领域知识。

## 9. V1 计划副本删除（已执行）

2026-09-24，用户要求「将 project 的 v1 也删除」。据此删除 `docs/project/v1/`（V1 计划快照）：
`project-plan.yaml`、`backlog.md`、`dependency-map.md`、`milestones.md`、`_planning-findings.md`、`README.md`。

V1 计划完整保留在 `release/v1` 分支与 tag `v1.0.0-demo`；`v2` 分支内不再保留任何 V1 文档副本。