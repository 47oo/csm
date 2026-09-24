# Git Workflow

本文件是分支、Git 字段、提交、Review 基线、合并与中断恢复的唯一操作规范。执行者为主协调器；Subagent 安全约束与声明核验见 `AGENTS.md` §9。项目状态字段见 `docs/project/project-state.md`。

## 1. 分支与范围

* `v2`：当前版本集成分支。
* `feature/<feature-id>-<slug>`：从 v2 创建的单个 Feature 分支。
* `main`：稳定版本，只能通过独立授权的 Release 流程更新。

普通 Feature 不直接在 v2/main 实现；默认不 push、打 tag、删除分支或发布。文档维护等用户明确授权的直接操作按授权范围执行，不伪装成 Feature DONE。

同一 Feature 使用同一工作区。并行任务必须划定文件所有权，所有写入者停止后才能暂存、提交、切分支或合并；共享文件串行处理。禁止自动 stash、reset --hard、clean、强制切分支或改写历史。

## 2. Preflight 与 Git 字段

任何新 Feature 状态写入前执行：

```bash
git rev-parse --show-toplevel
git branch --show-current
git status --porcelain=v1 --untracked-files=all
git status
```

要求 HEAD 非 detached、v2 存在、暂存与工作区 clean、无未跟踪文件、无 merge/rebase/cherry-pick 等进行中操作。失败输出 `GIT PREFLIGHT BLOCKED`，不自动归档未知修改。

确认 Feature ID/slug 合法且目标分支不存在，逐条执行并检查：

```bash
git switch v2
git rev-parse HEAD
git switch -c feature/<feature-id>-<slug>
```

记录实际值：

* `git.base_branch: v2`
* `git.branch`：创建的 Feature 分支。
* `git.start_commit`：创建时 v2 的完整 SHA，之后不变。
* `git.head_commit`：最近已记录的交付或检查点提交；不是包含该字段的 YAML 提交自身哈希。其后仅状态元数据差异需核对，不递归追写 HEAD。
* `git.merge_commit`：合并前 null，成功后写真实 Merge SHA。

恢复时先比较工作区、暂存区和 `HEAD:docs/project/project-plan.yaml`，以已提交 Plan 为基线；保留未提交检查点供核对。验证记录分支、提交存在性、start_commit 祖先关系及 HEAD 差异。已有工作的 Git 字段缺失或归属不明时输出 `GIT RECONCILIATION REQUIRED`，不能重建起点。

切回 Feature 分支前必须 clean。同分支未提交工作只有明确属于当前中断任务且用户已确认继续时才保留处理；不携带未知变更切分支。命令失败停止，不推进状态。

## 3. 提交与检查点

按需求/设计、实现、测试、项目状态进行单一目的提交，无变化不创建空提交。数据库文档可等并行写入结束后提交，不为提交阻塞 Frontend。

协调器核对 diff、未跟踪文件及暂存区，使用明确文件清单 `git add -- <files>`，审查 `git diff --cached` 后提交。禁止无差别 add。推荐 `docs(Fxxx)`、`feat(Fxxx)`、`test(Fxxx)`、`chore(Fxxx)` 前缀。

阶段检查点包含 current_stage、实施结果、last_result、next_action 和证据。阻塞时可在所有写入结束后提交核对过的产物及 BLOCKED 状态；不能安全提交则保留现场并报告。未提交状态不作为已完成证据。

Review 前提交全部候选实现、测试、Handoff 与检查点，工作区 clean。测试针对提交内容有效；出现额外实现变化时重新测试。

## 4. 正式 Review 基线

Reviewer 从 Plan/协调器取得 branch、start_commit 与 base_branch，核对起点与完整范围：

```bash
git status --short
git rev-parse HEAD
git rev-parse v2
git merge-base v2 HEAD
git diff v2...HEAD
git diff --stat v2...HEAD
git log --oneline v2..HEAD
git diff
git diff --cached
git ls-files --others --exclude-standard
```

同时核对 `start_commit..HEAD` 历史，不遗漏 Feature 早期变更。未提交或未跟踪交付物阻止正式批准。报告记录候选 HEAD、Base SHA、merge-base、完整审查范围和测试证据；基线变化必须重新验证/Review。

## 5. Merge Gate 与 DONE

必须同时满足：必要测试（包括适用的真实集成）通过；Review APPROVED / APPROVED WITH FOLLOW-UP；无 BLOCKER、HIGH、必须修复 MEDIUM 或产品未决问题；全部写入者结束；工作区 clean；候选 HEAD 与批准 HEAD、v2 与批准 Base SHA 均一致。

Review 获批准后，review = COMPLETE、stage = MERGE 和报告暂存于协调器输出，不先写入工作区或提交，以免改变批准 HEAD。批准证据丢失则重新 Review。

逐条执行并检查：

```bash
git switch v2
git merge --no-ff feature/<feature-id>-<slug>
git rev-parse HEAD
```

失败或冲突输出 `GIT MERGE BLOCKED`，保留现场，不标 DONE、不自动解决冲突后沿用旧批准。成功后验证两个父提交为预期 Base 与批准 HEAD，集成树与验证过的候选一致；不一致停止重新验证。

记录 approved HEAD 到 git.head_commit、真实 Merge SHA 到 git.merge_commit；统一保存 Review Report、Follow-up、Plan 和必要派生视图，清空执行检查点、重算依赖，作为独立状态提交 `chore(Fxxx): mark feature complete`。此提交不得修改已批准实现。

只有最终状态提交成功，Feature DONE 才生效并解锁依赖。失败输出 `PROJECT STATE COMMIT BLOCKED`；即使工作区 YAML 写了 DONE，也不能继续下一个 Feature。

## 6. Merge / 最终状态提交中断恢复

优先从已提交 Plan 检查点定位 Feature，即使工作区已经清空 current_feature 也不能丢掉恢复目标。在 v2 核对 Merge SHA、父提交、批准证据、候选与状态提交。

* Merge 已完成、状态未提交：核对未提交差异归属，补保存状态，不重复 Merge。
* 状态提交已完成：核对证据后幂等继续调度。
* 仅发现分支为祖先不足以证明获批；证据不足、额外实现改动或归属不明则停止核对。

项目整体 DONE 也须提交状态与视图、核对证据并确认 clean；可包含在最后一个 Feature 状态提交中。空计划不能当作项目完成。
