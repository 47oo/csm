---
description: 规划 V3 项目或需求变更，记录用户批准并维护计划基线，不自动启动实现
argument-hint: "[规划目标、变更说明或批准的提案/revision]"
---

# Project Planning

用户输入：$ARGUMENTS

1. 读取 `AGENTS.md`、`docs/project/project-state.md`、`docs/project/change-control.md` 和 `.pi/agents/project-manager.md`；涉及 Git 时先读 Git Workflow。默认需求来源为 `docs/product/requirements-v3.md`，用户明确指定来源优先。首次规划盘点现有 V3 成果，缺失文档按 AGENTS §1.1 处理。
2. 先由 product-manager 澄清影响当前规划的需求，再由 project-manager 初步拆分能力。首次规划由 architect 做轻量全局评估，必要时邀请 database 核对核心关系，明确共享规则、技术前提、公共 API 约定、事务边界与验证/部署基础。此阶段不要求完整接口/Schema，不标记 Feature 设计已完成。所有角色调用使用 `agentScope: project`，由协调器逐段核验，不用 chain 跨 Gate。
3. project-manager 根据评估修订依赖和里程碑。核对 Feature 有可验收价值、依赖无环、需求覆盖完整、状态有证据。未批准的重大架构前提进入 decisions_required；普通已批准边界内设计由专业角色签核。
4. Project Manager 维护 Plan，协调器执行 `python3 scripts/render_project_views.py --write` 生成统计及派生视图，再用不带 --write 的命令检查一致性。已有批准范围变化按 Change Control 生成提案及候选计划；重大变更按 Git Workflow 建立 proposal 分支并登记暂停范围。保留执行检查点及历史交付证据，未批准候选不覆盖执行基线。
5. 先完成可审阅的需求差异、影响评估和候选计划，再输出 `PROJECT PLAN READY FOR APPROVAL` 及待裁定项。信息不足则输出 `PROJECT PLAN BLOCKED`。已有明确批准时直接处理第 6 步，不重复索取。
6. 收到用户批准后，由协调器核对被批准的具体 revision/内容版本与 Feature 范围，按 Change Control 保存确认依据和 `project.approval`；初始 DRAFT 改为 ACCEPTED，进行中项目保留 IN_PROGRESS。只批准部分时仅纳入明确批准范围，未决项保留阻塞；涉及已完成项目新增范围时重新进入 ACCEPTED。同步视图并运行状态校验，按 Git Workflow 提交/合入批准基线；失败不宣称已生效。
7. 输出批准记录、基线变更与证据。计划批准不自动启动实施；用户同次已明确要求实施时，在批准落地后按其执行范围进入 implement-project，不再次询问相同授权。

## V3 一期规划核对

按需求 §3、§31–33 建立范围到 Feature / 验收的映射，覆盖资源关系、IPv4 IPAM、搜索/详情、基础权限、审计、逻辑删除、CSV / Excel 导入及 Compose 部署；不能只规划 CRUD 后就宣布一期范围完整。

需求 §35.1 的确认记录直接作为输入；§35.2 的六项业务决策已确认，保留来源索引，不再作为阻塞项或重复请求裁定。§35.3 的 OPEN 专业设计输入进入 decisions_required 并关联受影响 Feature；软件版本及普通设计按职责签核。后续新发现的业务问题由 Product / 用户按变更控制消解，不把完整字段契约尚缺等同于已确认规则仍未决。

只做提示/流程维护时，允许保留 DRAFT / incomplete 空骨架；自动生成的空视图明确显示尚未规划，不生成虚假的 Feature、签核或完成记录。本期排除的自动化不拆成实施任务，优先级也不能把本期必需能力改为可选。

规划按可运行的完整功能安排：最小工程/数据库/测试/Compose 基础 → Cluster 与 BareMetal 闭环 → VM/Host 与 Interface → Network/Pool/手动 IP 与并发自动分配 → Service/Endpoint → 完善搜索、导入、Dashboard 和系统功能 → 一期整体验收。此顺序是规划参考，真实依赖由评估确定，不直接登记为获批计划。基础搜索/详情、权限/审计/软删除随相关功能接入，不统一推迟到收尾。

首次计划必须为需求 §31–33 的整体验收安排承接 Feature / 里程碑，覆盖跨功能查询、权限、审计、导入和真实部署。各 Feature DONE 不自动代替一期整体验收，也不自动授权发布。
