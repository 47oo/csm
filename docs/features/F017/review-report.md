# F017 前端 UI 体系改造（Ant Design + Tailwind CSS）— REVIEW 阶段报告

- **Task**：F017（FEATURE，P0，M8 前端 UI 改造，deps F016）— Reviewer，正式 Review（READY FOR REVIEW → 独立审查）。
- **Status**：`APPROVED WITH FOLLOW-UP`。
- **Basis**：
  - `docs/product/requirements-v3.md` revision 4 CONFIRMED（§28/§29/§31/§32/§23/§25/§22；§35.3 D04）。
  - `docs/project/project-plan.yaml` plan_revision 5（用户 2026-10-12 批准并授权实施；F017 `layers={database:false,backend:false,frontend:true}`、`api_required=false`）。
  - `docs/features/F017/product.md`（F-UI-1..7）、`architecture.md`（CONTRACT READY FOR IMPLEMENTATION，D04 定稿，§7.5 TD-1 裁定）、`implementation.md`、`test-report.md`（TD-1 + TE-1 READY FOR REVIEW）。
  - `docs/database/f017-frontend-ui.md`（NOT_REQUIRED）；`docs/architecture/d04-frontend-ui-stack.md` v2 FINAL / CONFIRMED。
  - `docs/project/change-control.md`、`AGENTS.md` §9、`docs/project/handoff.md`、`docs/project/git-workflow.md` §4。

## 1. Scope Reviewed

| 项 | 值 |
| --- | --- |
| Feature Branch | `feature/F017-frontend-ui-antd-tailwind` |
| Base / base_branch | `v3` |
| start_commit | `67770639067bd7fe11bf633de4ff7b9c31e42c5e` |
| 候选 HEAD | `a9b9274b93d66bbb807e6b52c5488089df8680bd` |
| merge-base(v3,HEAD) | `67770639067bd7fe11bf633de4ff7b9c31e42c5e`（= start_commit，线性，无基线漂移） |
| v3 SHA | `67770639067bd7fe11bf633de4ff7b9c31e42c5e` |
| 完整范围 | `start_commit..HEAD` 45 个提交；`git diff --stat v3...HEAD` = 49 文件，+9726 / −5966 |
| 工作区 | clean；无未跟踪交付物 |
| 范围组成 | 前端展示层 34 个源文件 + 15 个 `docs/` 报告与计划派生视图；无 `backend/**`、`src/api/**`、纯逻辑 `*.ts`、部署配置变更 |

## 2. 适用层结论

| 层 | 结论 | 依据 |
| --- | --- | --- |
| 产品与领域 | 通过。仅展示层迁移；未新增对象/关系/状态/唯一性/生命周期规则 | product.md §1.4/§2.2/§2.3；diff 无业务文件 |
| 架构与依赖 | 通过。antd 5.29.3 + `@ant-design/cssinjs` 1.24.0 直接依赖 + tailwindcss/@tailwindcss/vite 4.3.3；react 18.3.1 / vite 5.4.21 未升级；无 PostCSS / tailwind.config | D04 v2 FINAL；`npm ls`；构建产物层序 |
| 数据与 Migration | 不适用 / 通过。`database: NOT_REQUIRED` | `docs/database/f017-frontend-ui.md` |
| API 与实现 | 通过。`api/*.ts`（16）与纯逻辑 `components/*.ts`（11）零改动；无 `antd`/`react`/`.css` import | A11/A12 独立复现 |
| 前端行为 | 静态通过，运行时未验证（归 F018） | 源码层四态/权限/错误语义保留 |
| 测试 | 通过（可自动/静态范围）。A1–A16 独立复现 | 见 §4 |
| 安全与范围 | 通过 | diff 审查 |
| 变更与批准 | 通过。plan_revision 5 覆盖 F017；无 pending_changes 命中；D04 专业签核可核 | project-plan.yaml；change-control §1/§2 |

## 3. Findings

| ID | Severity | Layer | Location | 证据 | 期望 vs 实际 | 影响 | Owner | 必须修复 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| R-1 | NOTE | Frontend | `src/pages/ClustersPage.tsx` | base 表头/表体列序错位（version/created_at/updated_at），迁移后 `dataIndex` 对齐 | 设计声明「口径同旧版」；实际修正旧版列错位 | 仅展示正确性修正，不改数据/请求/业务语义 | Frontend / Reviewer | 否 |
| R-2 | NOTE | Test Design | `test-report.md#test-design` A7 | 实测 `color-brand` 未入 `dist`（Tailwind v4 tree-shake），layer/`--font-sans` 入产物 | 判据字面假设不符 v4 行为 | 不影响实现正确性 | Tester（可选更正） | 否 |
| R-3 | NOTE | Documentation | `architecture.md` §1.3；D04 | 文档 `layer="antd"`；实际 boolean `<StyleProvider layer>`，默认层名 `antd`，等价 | 文档写法 vs API | 无功能影响 | Architect（可选更正） | 否 |
| R-4 | NOTE | Dependency | `frontend/package.json` | `typescript: ^5.6.3` 解析为 5.9.3；base 已同 caret | D04-3「5.6.x」按解析版本理解 | 非 F017 引入（base 已如此） | 协调器（记录） | 否 |
| R-5 | NOTE | Frontend/测试边界 | 全量 UI | F-UI-2/3/4 真实可见行为本次仅静态/机制验证 | 批准效力限于静态与构建 + smoke 机制 | 属已批准设计边界（F018 承接） | F018 | 否 |

无 BLOCKER / HIGH / MEDIUM 缺陷；无必须修复项。

## 4. 独立验证证据（Review 复现）

| 检查 | 命令 | 结果 |
| --- | --- | --- |
| typecheck | `npm run typecheck` | 退出码 0 |
| build | `npm run build` | 退出码 0；dist CSS 15751 B；层序入产物 |
| smoke | `npm run smoke:client` | `264 passed, 0 failed` |
| smoke 计数 | `grep -c "await test("`（HEAD/base） | 264 == 264 |
| 硬边界 | `git diff --name-only <base> -- src/api src/components/*.ts` | 空 |
| 部署/后端/契约 | diff | 空 |
| 迁移覆盖 | grep antd in pages+components | 33/33 `.tsx`；原生主控件 0 |
| 权限门控 | grep AUDIT_READ/USER_ADMIN/VIEW_DELETED | 69 处保留 |
| Audit 写入口 | AuditPage/AuditQueryPanel | 无修改/删除/清空处理 |
| 依赖锁 | `npm ls ...` | 单版本、无 invalid/missing |
| TD-1 关闭 | architecture.md / D04 | 定稿 `@layer` 不含 `legacy` |

## 5. 旧缺陷复核（Tester D-1..D-4）

| ID | Tester 分级 | Reviewer 复核 | 结论 |
| --- | --- | --- | --- |
| D-1 | NOTE | 独立确认 HEAD/base 均为 264；更正正确 | 接受 |
| D-2 | NOTE | 确认 `color-brand` tree-shake，令牌由 seed token 承载 | 接受（=R-2） |
| D-3 | NOTE | 确认 `layer` 为 boolean，默认层名 `antd` | 接受（=R-3） |
| D-4 | LOW | 确认 base 列序错位，迁移对齐；不改语义 | 接受（=R-1）；不阻塞 |

## 6. Follow-ups

1. **F-018（主要）**：真实/等价 Compose 执行 V5–V7（权限/四态/错误呈现/Audit 无入口/列表交互/layer 优先序与 preflight/Nginx 可达与 SPA fallback），重跑 build/smoke，更新 `project.acceptance`。
2. **D-4 视觉确认（F-018）**：确认 ClustersPage 列对齐修正后无其它页面同类错位。
3. **文档修订（可选）**：更正 `StyleProvider layer="antd"` 为 boolean；更正 TD-1 A7 判据以匹配 v4 tree-shake。
4. **协调器**：确认 CI/esbuild allowScripts 策略与本地一致。

## 7. 未审查项

- AntD v5 运行时渲染与 layer 优先序、preflight 实际布局影响（归 F018）。
- UI 可见行为：权限显隐、四态、错误呈现、Audit 入口、列表交互（归 F018）。
- Nginx 入口可达性与 SPA fallback（归 F018）。
- `npm ci` 独立重跑（以 lockfile 入仓、`npm ls` 单版本、TE-1 成功 `npm ci` 作间接证据）。

## 8. 结论

F017 范围内验收（F-UI-1..7）的可自动/静态证据经独立复现成立：依赖锁定且无夹带升级、`api/` 与纯逻辑 `*.ts` 及部署/后端零改动、`index.css` 收敛为最小全局层、typecheck/build/smoke（264）全绿。未发现 BLOCKER / HIGH / 必须修复 MEDIUM，无未决产品问题，无范围扩张（R-1 为展示正确性修复）。唯一限制是 UI 运行时正确性按已批准设计交 F018 复验，属计划内 follow-up。

**正式结果：`APPROVED WITH FOLLOW-UP`。**

批准仅对候选 HEAD `a9b9274b93d66bbb807e6b52c5488089df8680bd` 与 Base `67770639067bd7fe11bf633de4ff7b9c31e42c5e` 有效；Merge / DONE 由协调器按 `git-workflow.md` §5 判定。

## 9. Git 声明

Review 期间为只读，未执行任何改变 Git 状态的命令；工作区保持 clean。逐条只读命令：

```text
GIT: git status --short
GIT: git rev-parse HEAD
GIT: git rev-parse v3
GIT: git merge-base v3 HEAD
GIT: git diff --stat v3...HEAD
GIT: git log --oneline v3..HEAD
GIT: git diff --name-only 67770639067bd7fe11bf633de4ff7b9c31e42c5e
GIT: git diff --name-only 67770639067bd7fe11bf633de4ff7b9c31e42c5e -- frontend/src/api frontend/src/components/*.ts
GIT: git diff --name-only 67770639067bd7fe11bf633de4ff7b9c31e42c5e -- frontend/Dockerfile frontend/nginx.conf compose.yaml compose.test.yaml deploy frontend/index.html frontend/tsconfig.json
GIT: git diff --name-only 67770639067bd7fe11bf633de4ff7b9c31e42c5e -- backend docs/database docs/api
GIT: git diff --exit-code 67770639067bd7fe11bf633de4ff7b9c31e42c5e -- frontend/scripts/smoke-client.mjs
GIT: git ls-files frontend/package-lock.json
GIT: git show 67770639067bd7fe11bf633de4ff7b9c31e42c5e:frontend/package.json
GIT: git show 67770639067bd7fe11bf633de4ff7b9c31e42c5e:frontend/scripts/smoke-client.mjs
GIT: git show 67770639067bd7fe11bf633de4ff7b9c31e42c5e:frontend/src/pages/ClustersPage.tsx
```