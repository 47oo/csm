# F018 前端改造后一期整体验收复验 — Review Report

- **Task**：F018（FEATURE，P0，M8）— Reviewer，正式 Review。
- **Status**：`APPROVED WITH FOLLOW-UP`（唯一正式结果，见 §6）。
- **日期**：2026-10-15
- **Basis**：
  - `docs/features/F018/product.md`（PRODUCT READY FOR ARCHITECT，R-1..R-10 / AC-1..AC-10）。
  - `docs/features/F018/architecture.md` §2/§3/§4/§7（CONTRACT `NOT_REQUIRED`，Architect 2026-10-15 签核 READY FOR IMPLEMENTATION）。
  - `docs/features/F018/test-report.md` TD-1 + Test Execution TE-1（READY FOR REVIEW）。
  - `docs/database/f018-acceptance.md` v1（`NOT_REQUIRED`，单 head `0013_search_indexes`）。
  - `docs/features/F016/test-report.md` §32 C1–C15 / §33 Q1–Q9 / T36（REUSE 锚点）。
  - `docs/project/project-plan.yaml` plan_revision 5；`docs/project/{git-workflow,project-state,change-control,handoff,implementation-rules}.md`；`.pi/skills/data-integrity/SKILL.md`。

## 1. Scope Reviewed

| 项 | 值 |
| --- | --- |
| Feature Branch | `feature/F018-post-ui-acceptance` |
| start_commit | `6e695938f714ddd8bd8339855c72c0762c6fd6ce` |
| 候选 HEAD | `44ac90931312f7c6596b07e031489c22813964fa` |
| Base | `v3` = `6e695938f714ddd8bd8339855c72c0762c6fd6ce` |
| merge-base v3..HEAD | `6e695938…`（= start_commit = v3，无偏移） |
| 工作区 | clean（`git status` = nothing to commit；`git diff` / `--cached` 空；无未跟踪文件） |
| 历史范围 | 6 提交：`bfb5472` Preflight → `c037ffb` PRODUCT → `466d184` ARCH → `75d0a0b` DB+TEST_DESIGN → `344ebee` CONTRACT → `44ac909` TEST |
| 完整差异 | 11 文件 +1412/−18：3 份 F018 报告 + `docs/database/f018-acceptance.md` + 4 个 test-only 脚本 + `project-plan/backlog/milestones` 元数据 |

差异逐项核对：

- 生产层零改动：`git diff --stat v3...HEAD -- frontend backend compose.yaml deploy docs/api` **为空**；未触碰 `frontend/src/**`、`frontend/src/api/*.ts`、纯逻辑 `*.ts`、`frontend/scripts/smoke-client.mjs`、生产依赖、`compose.yaml`、`deploy/**`。
- 新增脚本全部落在 `scripts/acceptance/`（`run_f018_acceptance.sh`、`browser/f018_browser_check.mjs`、`browser/package.json`、`browser/package-lock.json`），符合 architecture §4 与 product §3 的 test-only 边界。
- 计划元数据一致：`project.status=IN_PROGRESS`、F018 `IN_REVIEW`/`current_stage: REVIEW`；`validate_project_state.py` → `PROJECT STATE VALID`；`pending_changes=[]`；计划批准 `plan_revision 5` 覆盖 F017/F018，需求 `revision 4` 匹配。

## 2. 适用层结论

| 层 | 结论 | 依据 |
| --- | --- | --- |
| Product / 领域 | 通过 | 验收复验型 Feature，未新增/变更对象、关系、状态、唯一性、生命周期；AC-1..AC-10 可观察判据齐备。 |
| Architecture / Contract | 通过 | `CONTRACT=NOT_REQUIRED` 有理由（api_required=false，仅消费既有 READY Contract）；arch §7 专业签核完整（签核者/日期/依据/覆盖范围）。 |
| Database / Migration | 通过（NOT_REQUIRED） | `f018-acceptance.md` DB-F018-1..3 复核无 Schema/迁移/约束/索引变更；迁移单 head `0013_search_indexes` 与实测 `alembic current` 一致。 |
| API / 实现 | 通过 | 无 Endpoint/字段/错误语义变更；实测 403 `FORBIDDEN`、409 `VERSION_CONFLICT{current_version}`、422 `VALIDATION_ERROR{fields}` 与既有契约一致。 |
| 前端 / 集成 | 通过 | 真实等价拓扑 Nginx→Frontend(dist)/FastAPI→PostgreSQL 内联调；SPA fallback、入口标记、真实 API 数据与真实错误态一致。 |
| 测试可信度 | 通过 | AC-1..AC-10 均有可复核产物；NOT TESTED 规则遵守；Compose 失败如实录制，未冒充 PASS。 |
| 安全 / 范围 | 通过 | 无越界改动、无生产依赖/凭据入库、无敏感信息；临时用户/数据在独立库 `csm_f018_acc` 并由清理纪律回收。 |
| 变更 / 批准 | 通过 | 计划 revision 5 与需求 revision 4 一致；无 pending_changes；执行授权覆盖 F018。 |

## 3. 证据核验（独立复核）

**AC-1**：`typecheck.log` rc=0；`build.log` rc=0；`dist` 非空 CSS=1；`smoke.log` = `264 passed, 0 failed`；`grep -c "await test("` = 264（无删减）。**可信。**

**AC-2**：`health.txt` = `/healthz`200(ok)、`ready`200、`/`200、`/clusters`200；脚本断言 `/clusters` body 与 `/` 逐字节一致（SPA fallback）。**可信。**

**AC-3**：`layer-order.json` 首现序 `properties, theme, base, antd, components, utilities`（`components` 仅能来自 `@layer` 声明，故有效层序为 `theme→base→antd→components→utilities`，无 `legacy`）；`computed-style.json` 确认 `.ant-btn` 位于 `@layer antd` 且按钮 classList 含 `ant-btn`；`utility-override.json` 探针 `px-0` → `paddingLeft=0px`；`preflight.json` body margin 0 / box-sizing border-box。**真实渲染，可信。** `properties` 为 Tailwind v4 内部层，报告 NOTE 已如实标注。

**AC-4**：viewer `/auth/me` 权限无 `AUDIT_READ/USER_ADMIN/VIEW_DELETED`，导航无 Audit/System，直接 `/audit` 未渲染审计面板；admin 导航含 Audit/System。**可信**（见 Follow-up F-2：admin System 页可达性未单独渲染）。

**AC-5**：四态齐备且为真实态——Loading（真实响应延迟 800ms，非数据改写，TD §3.3 允许）、Success（含真实种子 `F18C-<runId>`）、Empty（真实过滤 0 命中）、Error（**真实 kill `f018-backend` 容器**触发不可达，脚本 finally 重启并轮询恢复）。**可信。**

**AC-6**：401 清 Cookie → 全局回登录页；403（EDITOR 经真 API 降级为 VIEWER 后提交）、409（真 API 提升 version 后陈旧提交）、422（非法 hostname 服务端校验）均有 DOM 截图；`http-error-semantics.json` 另证 403/409/422 同源真 HTTP 状态码与错误码。**可信。**

**AC-7**：静态检索 + ADMIN 浏览器打开 Audit 页控件清单仅 `筛选/重置/排序/详情/分页/登出`，无删除/清空/修改。**可信。**

**AC-8**：`network-params.json` 过滤请求 `?type=BARE_METAL&…`、排序请求 `?…&sort=resource_type&order=asc`，两者不可互换。**可信。**

**AC-10**：`clusters-columns.json` 表头与表体首行列左偏移逐列一致（容差 ≤2px，`equal=true`）。**可信。**

**AC-9（REUSE 正当性）**：数据层锚点 `docs/features/F016/test-report.md#32-c1c15-上线验收` / `#33-目标查询场景` 存在且为 F016 TE-1 真 HTTP 执行证据（`40 passed`）；C15 = `test_c15_required_capabilities_executed`（对全部必需读端点实际回包 200 的**实际汇总**，非局部拼接）。**REUSE 适当，未把局部 PASS 拼成整体 PASS。** 见 Follow-up F-1（界面呈现为抽样）。

**Compose 诚实性**：`compose-up.log` 记录真实失败（`auth.docker.io` token i/o timeout，`EXIT_CODE=1`）并切换 F016 §2.2 等价替代栈（库 `csm_f018_acc`、入口 18080、未改动 `deploy/nginx/nginx.conf`），差异声明完整，**未伪造 Compose PASS**。

**清理纪律**：`run.log` 显示 `DONE … failures=0`（typecheck/build/smoke/browser 全 0）与 cleanup 阶段；`docker ps -a/network ls/volume ls` 残留检查输出 `none`；`browser-libs` 删除。**遵守。**

**NOT TESTED 规则**：`browser-summary.json` = `executed 19 / passed 19 / failed 0 / notTested 0`；机读产物与截图（15 PNG + JSON）均存在且与报告叙述一致；未将机制证据冒充渲染结论。**遵守。**

## 4. Findings

| ID | Severity | Layer | Location | 证据 / 说明 | 期望与实际 | 影响 | Owner | 必须修复 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| F-1 | LOW | Test / 呈现 | `test-report.md` AC-9；`browser-summary.json` "AC-9 key pages render" | 界面呈现证据为 Clusters/Resources/Audit 三页抽样（有真实数据即 PASS），未逐项渲染 §32 C1–C15 与 §33 Q1–Q9 的前端场景 | 期望：呈现复核范围与 AC-9 措辞对齐；实际：抽样呈现 + 数据层 REUSE | 与 architecture §3「REUSE（数据层）+ 人工（呈现）」映射一致，未虚报；不阻塞 | Tester / 后续验收 | 否 |
| F-2 | LOW | Frontend / 权限门控 | `browser-summary.json` "AC-4 admin nav visible" | AC-4 要求「带权限时可见可访问」；admin 仅验证导航可见，`/audit` 可达由 AC-7/AC-9 覆盖，`System` 页可达性未单独渲染验证 | 期望：admin 对 Audit/System 均可访问；实际：Audit 可达已验证，System 仅导航可见 | 门控隐藏/不可达方向已验证；可见可访问仅覆盖 Audit，风险低 | Tester | 否 |
| F-3 | NOTE | 项目状态 | `project-plan.yaml` F018.git | 缺 `git.head_commit` 字段（`base_branch/branch/start_commit` 已记）；候选 HEAD 记于 Test Report §TE-1 / 本报告 | 期望：IN_REVIEW/DONE 的 `head_commit` 记录最近交付检查点；实际：待合并时补记 | 不影响候选/Base 固定与 Merge Gate（报告已记录候选 HEAD）；协调器合并时补 `head_commit`/`merge_commit` | 协调器 | 否 |
| F-4 | NOTE | 测试基线 | `run.log` `HEAD=344ebee…` vs 候选 `44ac909…` | 脚本运行时 HEAD=父提交 `344ebee`（脚本当时未跟踪），候选 HEAD `44ac909` 仅新增 test-only 脚本 + 报告 + 计划元数据；生产代码（frontend/backend）在两提交间完全一致 | 期望：测试对候选内容有效；实际：无生产实现差异，证据有效 | 无实现变化，无需重测；仅记录审阅判断 | Reviewer / 协调器 | 否 |

无 BLOCKER / HIGH / 必须修复 MEDIUM。产品无未决问题（product §6 Blocking Questions = None）。

## 5. 旧缺陷复核

F018 为首次 Review，无同 Feature 旧缺陷可复核。F017 遗留的 R-1 / D-4 视觉确认由 AC-10 承接并已通过（`clusters-columns.json`），未发现回归；F017 Review 的 Follow-up 未被本 Feature 静默改动。

## 6. 正式结果

**`APPROVED WITH FOLLOW-UP`**

- 核心验收 AC-1..AC-10 满足，必要验证（真实等价拓扑 + 真实浏览器 19/19 + 真 HTTP 数据层 REUSE）可信。
- 无 BLOCKER / HIGH / 必须修复 MEDIUM；无未决产品问题。
- 仅有 F-1..F-4 明确非阻塞项及跟进安排（见 §4）。

> 批准仅对候选 HEAD `44ac90931312f7c6596b07e031489c22813964fa` 与 Base `v3=6e695938f714ddd8bd8339855c72c0762c6fd6ce` 有效。Merge / DONE 由协调器按 git-workflow §5 判定；本报告不授予 Merge 权限。

## 7. Follow-ups

| ID | 内容 | Owner | 时机 |
| --- | --- | --- | --- |
| FU-1 | AC-9 呈现可在后续整体验收中以逐场景浏览器复核补强（非本次合并门槛） | Tester / 协调器 | 网络/工具可用后 |
| FU-2 | 如需更完整门控证据，补 admin `System` 页真实可达渲染（当前导航门控已足） | Tester | 后续 |
| FU-3 | Merge 前按 git-workflow 在计划补记 F018 `git.head_commit`（批准 HEAD）与合并后 `git.merge_commit` | 协调器 | Merge Gate |
| FU-4 | Compose 首选路径待网络可达后按 `run_f018_acceptance.sh` 复跑（环境性，非缺陷） | 协调器 | 环境恢复后 |

## 8. 未审查项

- F001–F016 后端/数据库/API/备份证据的复验（F018 明确排除；本报告仅核验其 REUSE 锚点存在且为真 HTTP 证据）。
- §31 T01–T41 后端侧的重新执行。
- 未提交/未跟踪产物：无（工作区 clean；`scripts/acceptance/artifacts/**` 为 git-ignored 运行产物，仅作只读证据核对，不属交付）。
- 生产环境部署与发布验证（超出 F018 范围）。

GIT: git status --short
GIT: git rev-parse HEAD
GIT: git rev-parse v3
GIT: git merge-base v3 HEAD
GIT: git log --oneline v3..HEAD
GIT: git diff --stat v3...HEAD
GIT: git ls-files --others --exclude-standard
GIT: git branch --show-current
GIT: git diff --name-status v3...HEAD
GIT: git status --porcelain=v1 --untracked-files=all
GIT: git diff --name-only 6e695938f714ddd8bd8339855c72c0762c6fd6ce..HEAD -- frontend/ backend/ compose.yaml deploy/ api/
GIT: git log --oneline --name-status v3..HEAD
GIT: git log --oneline --diff-filter=A -- scripts/acceptance/run_f018_acceptance.sh scripts/acceptance/browser/f018_browser_check.mjs
GIT: git diff v3...HEAD -- docs/project/project-plan.yaml docs/project/backlog.md docs/project/milestones.md
GIT: git diff --stat v3...HEAD -- frontend backend compose.yaml deploy docs/api
GIT: git diff
GIT: git diff --cached
GIT: git status
