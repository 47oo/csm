---
description: 规划 V2 项目或需求变更，记录用户批准并维护计划基线，不自动启动实现
argument-hint: "[规划目标、变更说明或批准的提案/revision]"
---

# Project Planning

用户输入：$ARGUMENTS

1. 读取 `AGENTS.md`、`docs/project/project-state.md`、`docs/project/change-control.md` 和 `.pi/agents/project-manager.md`；涉及 Git 时先读 Git Workflow。默认需求来源为 `docs/product/requirements-v2.md`，用户明确指定来源优先。首次规划盘点现有 V2 成果，缺失文档按 AGENTS §1.1 处理。
2. 调用项目级 project-manager（`agentScope: project`），输入已确认需求及已有交付证据；涉及领域澄清先交 product-manager，不由规划者编造规则。
3. 核对 Feature 有可验收价值、真实依赖且无环、需求覆盖完整、状态有证据。未批准的架构前提进入 decisions_required；已有决策引用即可。
4. 按 Project Manager 定义生成 Plan 及派生视图。已有批准范围变化按 Change Control 生成提案及候选计划；大范围变更由协调器按 Git Workflow 建立 proposal 分支并登记暂停范围。保留执行检查点及历史交付证据，未批准候选不覆盖执行基线。
5. 先完成可审阅的需求差异、影响评估和候选计划，再输出 `PROJECT PLAN READY FOR APPROVAL` 及待裁定项。信息不足则输出 `PROJECT PLAN BLOCKED`。已有明确批准时直接处理第 6 步，不重复索取。
6. 收到用户批准后，由协调器核对被批准的具体 revision/内容版本与 Feature 范围，按 Change Control 保存确认依据和 `project.approval`；初始 DRAFT 改为 ACCEPTED，进行中项目保留 IN_PROGRESS。只批准部分时仅纳入明确批准范围，未决项保留阻塞；涉及已完成项目新增范围时重新进入 ACCEPTED。同步视图并运行状态校验，按 Git Workflow 提交/合入批准基线；失败不宣称已生效。
7. 输出批准记录、基线变更与证据。计划批准不自动启动实施；用户同次已明确要求实施时，在批准落地后按其执行范围进入 implement-project，不再次询问相同授权。
