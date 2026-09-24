---
description: 根据 V2 已确认需求生成待批准项目计划，不启动实现
argument-hint: "[任务或 Feature ID]"
---

# Project Planning

用户输入：$ARGUMENTS

1. 读取 `AGENTS.md`、`docs/project/project-state.md` 和 `.pi/agents/project-manager.md`。默认需求来源为 `docs/product/requirements-v2.md`，用户明确指定来源优先。首次规划盘点现有 V2 成果，缺失文档按 AGENTS §1.1 处理。
2. 调用项目级 project-manager（`agentScope: project`），输入已确认需求及已有交付证据；涉及领域澄清先交 product-manager，不由规划者编造规则。
3. 核对 Feature 有可验收价值、真实依赖且无环、需求覆盖完整、状态有证据。未批准的架构前提进入 decisions_required；已有决策引用即可。
4. 按 Project Manager 定义生成 Plan 及派生视图。重新规划必须保留执行检查点与 Git 证据，已有批准范围变化单独待确认。
5. 输出公共交接摘要及 `PROJECT PLAN READY FOR APPROVAL`，等待用户批准。信息不足则输出 `PROJECT PLAN BLOCKED`。不得将 DRAFT 自行改为 ACCEPTED，也不自动启动实施。
