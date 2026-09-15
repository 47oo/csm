# Git Workflow

Git 是 CSM 正式开发流程的一部分：`docs/project/project-plan.yaml` 记录项目管理状态，Git 记录代码与文档的真实变更历史。状态必须能由提交、测试和 Review 证据支持。

## 1. 分支职责

* `main`：稳定版本与正式里程碑；普通 Feature 不直接开发或合并到 main。
* `develop`：当前版本的集成分支。
* `feature/<feature-id>-<slug>`：单个 Feature，例如 `feature/F005-ip-address`，从 develop 创建。

仓库初始化、master 改名及现有修改归档应单独确认；不得为通过 Gate 自动提交未知改动。
达到明确版本或 Milestone 后，由独立且明确授权的 Release 流程将 develop 合并到 main。本工作流不自动 push、打 tag 或发布。

## 2. Feature 开始与恢复

新 Feature 开始前检查 Git 状态（含暂存区和未跟踪文件），要求工作区 clean，无进行中的 merge/rebase 等操作，再从 develop 创建分支并记录起始 Commit。

恢复时核对已记录分支、起始 Commit、当前 HEAD 与阶段证据；保留阻塞分支，不自动重建、删除或覆盖。已有历史缺少 Git 元数据时停止核对，不伪造起点。

不使用自动 stash、reset --hard、clean、强制切分支或改写历史来绕过工作区问题。

## 3. Agent 与 Git

所有专业 Subagent（包括 product-manager、project-manager、architect、database、backend、frontend、tester、reviewer）只负责职责内修改、测试与报告，不得执行 Git add、Commit、Branch 切换、Merge 或其他修改 Git 状态的操作。

Git 状态管理由主协调 Agent 统一负责。Subagent 报告的 Git 声明要求（交接的验收条件）见 `AGENTS.md` §9.1。

第一版采用同一 Feature Branch、同一工作区；不引入 worktree。并行前划定文件所有权；所有写入任务停止后才能暂存、提交或切分支，防止纳入其他 Agent 未完成的工作。

## 4. Commit 原则

提交须单一目的、可理解、可回滚且只包含当前 Feature。

按产品需求、架构与 API Contract、实现、测试、项目状态分阶段提交；数据库文档可在并行任务结束后单独补交，不为提交而阻塞 Frontend。

由协调器检查 diff、未跟踪文件和暂存区，使用明确文件清单暂存，提交前检查 `git diff --cached`；禁止无差别 `git add .`，无变化则跳过空提交。

推荐提交信息：

* `docs(F005): ...`
* `feat(F005): ...`
* `test(F005): ...`
* `chore(F005): ...`

## 5. Review 范围

Reviewer 确定 Feature 起点和完整差异，不只检查未提交修改：

```bash
git status
git diff develop...HEAD
git diff --stat develop...HEAD
git log --oneline develop..HEAD
```

同时检查暂存、未暂存及未跟踪内容。

正式批准针对明确的 Feature HEAD、Base SHA 与完整变更范围；未提交的实现不能被遗漏或默认为已批准。

## 6. Merge Gate 与 Feature DONE

仅当必要测试通过，Reviewer 为 `APPROVED` 或 `APPROVED WITH FOLLOW-UP`，且不存在 BLOCKER、HIGH、必须修复的 MEDIUM、PRODUCT DECISION REQUIRED 时，协调器才可 `git merge --no-ff` 到 develop。

合并前工作区须 clean、所有写入任务已结束，Feature HEAD 和 develop 必须仍与测试/Review 基线一致；变化时重新验证并 Review，不沿用旧批准。

冲突或命令失败即停止，保留现场，不自动解决后宣称通过。

Feature 只有在 Review 批准、必要测试通过、分支成功合并进入 develop、Project Plan 与关联视图已更新并提交后才算 `DONE`，才能解锁依赖。

Review 批准仅表示可合并，不等于 DONE。失败时保留分支和执行检查点。

## 7. Prompt 入口

Git 字段语义与具体调度遵循 `.pi/prompts/implement-project.md`；生成项目计划时同步遵守 `.pi/prompts/project.md`。
