# CSM Releases

> 本文件记录 CSM 的版本边界与冻结状态。详细产品规则见 `docs/product/`；分支与提交流程见 `docs/project/git-workflow.md`；当前（v2）项目状态见 `docs/project/project-plan.yaml`；V1 计划见 `release/v1` 分支。

## v1.0.0-demo — CSM V1 Demo

- **Tag**：`v1.0.0-demo`（annotated）
- **Tag 指向**：`563eda3`（`release: align agent guidance and domain rules`）
- **冻结分支**：`release/v1`（与 tag 同一点，只读参考 / 紧急修复）
- **打 tag 日期**：2026-09-24
- **范围**：M1–M12 全部 DONE（21 DONE + 1 CANCELLED）时的 V1 交付。
- **部署形态**：内网 Internal IP + HTTP，无公网入口 / 域名 / HTTPS（R-DEPLOY-003）。
- **定位**：演示 / 参考版本；后续大跨度重构不在此线上进行。
- **注意**：`main` 的 V1 稳定线止于该 tag。M13（F024 / F025）为 tag 之后新增的 DRAFT 规划，**不在 V1 demo 范围内**。

## 版本线

| 分支 | 职责 |
|---|---|
| `main` | 稳定版本线；V1 期间止于 `v1.0.0-demo` |
| `release/v1` | V1 冻结分支，只读参考 / 紧急修复 |
| `v2` | 重构集成线，后续开发在此进行 |
| `develop` | V1 旧集成分支，已与 `main` 对齐，后续由 `v2` 取代 |
| `feature/<feature-id>-<slug>` | 单 Feature，按 `docs/project/git-workflow.md` 从当前集成分支创建 |

## v2 重构

V2 是对 V1 的大跨度重构（**领域与范围都变**，且无需迁移 V1 生产数据）。V1 已冻结，
完整保留在 `release/v1` 分支与 tag `v1.0.0-demo`，作为对照与回滚点；V2 的 Feature 计划重新立项（见 `.pi/prompts/project.md`），
不与 V1 的 `project-plan.yaml` 混用。

V2 需求见 `docs/product/requirements-v2.md`（Status: **DRAFT — AWAITING CONTENT**）；
立项前提与待澄清输入见 `docs/project/v2/planning-intake.md`。在获得 v2 需求之前不得生成 v2 计划。