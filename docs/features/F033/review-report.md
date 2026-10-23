# F033 前端布局与 CSS 质量优化 — REVIEW 报告

- **状态**：**APPROVED WITH FOLLOW-UP**
- **版本**：v1
- **Reviewer**：Reviewer（独立审查），2026-10-23
- **候选基线**：Branch `feature/F033-layout-css-refresh`；Base `refs/heads/v3.3` = `b7412402125112f9188617803af05d1efda26cfc`；候选 HEAD `1ec018ae5c8296df810961fa9697e577679d8f9e`；merge-base `b741240`；完整范围 `b741240..1ec018a`（93 files / +6622 −152）。
- **状态提交**：`a141379` 仅 plan/派生视图元数据，无实现或证据改动。
- **批准边界**：仅对候选 HEAD `1ec018a` 与 Base `b741240` 有效；Merge/DONE 由协调器按 Git Workflow 判定。

## 1. Basis

- `docs/product/requirements-v3.md` revision 12 §28（CONFIRMED：运维控制台，快速/清晰/高效/低操作成本，不追求复杂视觉效果）。
- `docs/features/F033/product.md` v1（A1–A11）；`architecture.md` v1 §9（DR-F033-01..11，Contract NOT_REQUIRED）；`test-report.md` TD-1 + TEST-1（READY FOR REVIEW）。
- `docs/architecture/frontend-ui-stack.md` §5 + §5.1；F028 前端基线。
- `docs/project/project-plan.yaml` plan_revision 19；用户 2026-10-23 布局/CSS 要求；`pending_changes: []`。

## 2. Scope Reviewed

| 项 | 值 |
| --- | --- |
| Branch | `feature/F033-layout-css-refresh` |
| start_commit | `b741240` |
| 候选 HEAD | `1ec018a` |
| 当前状态提交 | `a141379`（仅计划元数据） |
| Base | `refs/heads/v3.3` = `b741240` |
| merge-base | `b741240` |
| 完整范围 | 93 files；代码仅 5 文件（`index.css`/`HomePage.tsx`/`App.tsx`/`GlobalSearch.tsx`/`ClusterAuthorizationPanel.tsx`），其余为 F033 文档/前端基线文档/计划视图/artifacts |
| 工作区 | clean；状态脚本 VALID；派生视图 VALID |

## 3. 分层结论

| 层 | 结论 |
| --- | --- |
| 产品/领域 | **PASS**：零业务语义变化；`GlobalSearch` 仅折叠结构，`selectedFields`/localStorage/请求参数未动；`HomePage` 仅去重 header、eyebrow aria-hidden、nav ref/scrollIntoView；授权面板仅移除 inline style；App 仅加 boot class。 |
| 数据完整性 | **NOT_REQUIRED**：`database=false`，backend/docs/database 零 diff。 |
| 架构/依赖 | **PASS**：DR-01..11 落位；sticky/scroll-padding、≤1023 rail、44px、授权单列、details、末卡跨列、表格自身滚动、min-width:0；未改 main.tsx/package/components/ui。 |
| API/Contract | **PASS（NOT_REQUIRED）**：docs/api、backend 零 diff；请求参数逐字不变；错误/确认/分页排序过滤以零 diff + smoke + 真实 401/409/422 覆盖。 |
| 前端实现 | **PASS**：token 单一来源（45 定义/45 引用/0 未定义，hex 仅在 :root，rgb 仅 2 token）；无 `.ant-*`；无 workspace-location；无授权 inline style；4 处 `<main>` 均有容器类；断点几何自洽。 |
| 测试充分性 | **PASS**：438 条指标（434 PASS / 1 FAIL LOW / 3 NOT TESTED）；40 格页面无横向溢出；宽表 12/12；375 壳层 176px；nav 44px；授权 1/1/2/2 轨道；details 0/9；Dashboard 末卡 1.00；sticky 与焦点遮挡通过；独立复跑 typecheck exit 0、smoke 328 passed。 |
| 安全/范围 | **PASS**：无新增依赖/敏感信息；测试只读，resources total 7→7；临时 Vite/Playwright 在仓库外。 |
| 变更/批准 | **PASS**：plan_revision 19 覆盖 F033；pending_changes 空；状态脚本 VALID；head_commit 与候选一致，a141379 仅元数据。 |
| 历史交付安全 | **PASS**：未改 F002–F032 历史证据；frontend-ui-stack 仅 §5 增补；main.tsx/package/components/ui/backend/docs/api 零 diff。 |

## 4. Findings

| ID | Severity | Layer | 说明 | Owner | 必须修复 |
| --- | --- | --- | --- | --- | --- |
| F033-RV-01 | LOW | 报告/证据 | smoke 基线引用 322（F028/F029 旧基线），F033 实际 base 为 328；命令 exit 0 且计数无回归 | Tester（后续） | 否 |
| F033-RV-02 | LOW | 设计-实现一致性 | 实现把 scroll-padding 改为 `header-offset + 8px` + scroll-margin 8px（避免 144px 叠加），并给 `.workspace-content` 加 15px 字阶；仅记录在 implementation，未回写 architecture errata | Architect | 否 |
| F033-RV-03 | NOTE | Frontend CSS | ≤1023 导航项 focus-visible 的 outline/shadow 仍被 `overflow-x:auto` 裁切左/右 3px；焦点态下激活项的左侧 current 条被 focus 样式替换；注释“完整可见”不成立（与 D-F033-01 同源） | Frontend（后续） | 否 |
| F033-RV-04 | NOTE | 证据 | `375x667-system-authorizations-selected.png` 与未选中版 MD5 相同；375 选中结果在折叠线下，数值证据仍有效 | Tester/协调器 | 否 |
| F033-RV-05 | NOTE | 测试账目 | `ui-metrics.json` 的 3 条 NOT_TESTED（1440/1024 nav rail N/A ×2 + 冷启动 Tab ×1）与 TE-8 列的三项（非 ADMIN/403/A8.5）集合不同，计数巧合 | Tester | 否 |
| F033-RV-06 | NOTE | Frontend CSS | `mark { border-radius:3px }` 未走 radius token 阶梯 | Frontend | 否 |
| F033-RV-07 | NOTE | 安全既有项 | 8 份历史报告含明文测试口令，均在 base 已存在；F033 已脱敏 | 协调器（范围外） | 否 |
| F033-RV-08 | NOTE | 流程 | `.gitignore *.log` 与 artifacts 证据冲突，需 `git add -f`；建议增加 docs artifacts 例外 | 协调器 | 否 |

**BLOCKER 0 / HIGH 0 / MEDIUM 0 / LOW 2 / NOTE 6；无必须修复项。**

## 5. 旧缺陷复核

| ID | 原判 | 复核 |
| --- | --- | --- |
| D-F033-01 | LOW | 维持 LOW；焦点仍三边可见 + 背景 + aria-current，不影响 A3；与 RV-03 同源，后续一并修。 |
| NOTE-01（mark 3px） | NOTE | 确认，= RV-06。 |
| NOTE-02（headless 焦点起点） | NOTE | skip-link 在 base/HEAD 相同，非 F033 引入。 |
| NOTE-03（§5.1 未点名授权按钮作用域） | NOTE | 确认，建议并入 RV-02 errata。 |

## 6. Follow-ups

1. **Architect**：补 DR-02 scroll-padding 口径、`.workspace-content` 字阶、授权按钮作用域到 architecture errata / frontend-ui-stack §5.1（RV-02 + NOTE-03）。
2. **Tester**：后续以 base 实测 smoke 计数为基线；分离 N/A 与 NOT TESTED 账目；处理重复 375 截图（RV-01/04/05）。
3. **Frontend（可选）**：修正导航 focus ring 与激活条叠加/裁切，修改误导注释（RV-03 / D-F033-01）。
4. **协调器**：评估 `docs/**/artifacts/*.log` gitignore 例外；另行整顿历史报告明文口令（RV-07/08）。

## 7. 未审查项

| 项 | 原因 |
| --- | --- |
| 71 张截图主观视觉比对 | Reviewer 无图像识别能力；以几何指标、token 计算值、静态核对与人工抽查建议替代 |
| `npm run build` 独立复跑 | 会写 `frontend/dist`；已审阅 `build.log`（exit 0）并独立复跑 typecheck/smoke |
| `/tmp` Playwright 脚本逐行审计 | 脚本未入库；以指标自洽、独立自查数值互证、原始截图/日志交叉验证 |
| `prefers-reduced-motion`、Safari/Firefox 差异 | 超出本次 TD-1 视口/浏览器矩阵 |
| §31–33 项目整体验收 | 协调器职责 |

## 8. 结论

**APPROVED WITH FOLLOW-UP**。A1–A11 满足，验证可信，无 BLOCKER/HIGH/必须修复 MEDIUM；范围严格限定于 5 个前端呈现层文件 + 文档；仅余非阻塞跟进项。Merge/DONE 由协调器按 Git Workflow 判定。
