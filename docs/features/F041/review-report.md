# F041 对象选择控件候选完整性（R04）— REVIEW 报告

- **结论**：**APPROVED WITH FOLLOW-UP**（无 BLOCKER / HIGH / 必须修复 MEDIUM）
- **候选 HEAD**：`ad56072424f886d182301d39832619a93b1f1e65`；**Base**：`refs/heads/v3.4` = `d5c0a4c9aa5bd1036dd9acf087d210a22f43571d`（= `start_commit` = merge-base；线性 4 提交）
- **版本**：v1（2026-10-29，正式 Review，独立复核，reviewer 只读产出、协调器持久化）
- **范围**：26 文件（3 后端测试新增 + 15 `docs/features/F041/**` + 3 `docs/project/**` + 5 前端代码 + smoke）；工作区 clean；`validate_project_state.py --feature F041` VALID

## 1. 范围与基线（PASS）

`git diff --stat refs/heads/v3.4...HEAD -- docs/api docs/product docs/database docs/architecture frontend/src/components/ui/controls.tsx frontend/src/api frontend/package.json frontend/package-lock.json frontend/vite.config.ts frontend/src/index.css` → **空**；`backend` 仅 3 个新增测试文件（+857/−0），`git status --porcelain -- backend` 空 ⇒ **生产代码零 diff**；无 F001–F040 历史文件被改写；交付线三方一致（workflow `DELIVERY_BRANCH=v3.4` / plan `git.base_branch` / `refs/heads/v3.4`）。

## 2. A1–A16（全部 PASS，独立实测）

| 验收 | 结论 | 关键独立证据 |
| --- | --- | --- |
| A1 | PASS | 自跑 I 层 **18 passed**：名次 110 的 Cluster → `POST /resources` **201** + DB `resources.cluster_id`；名次 110 的 Host → VM **201** + DB `virtual_machine_details.host_resource_id`；换 Host 110→120 → activity `CREATE/UPDATE` 且 UPDATE `before=110/after=120`（T19）；名次由 `rank_by_server_order` 逐页现算（不硬编码） |
| A2 | PASS | I-03/I-04/I-08（`page_size=101`→422、`page=0`→422、`items≤100`）；探针 `page_size=100`、`page=1` 常量 |
| A3 | PASS（强度见 F041-R-04） | 唯一请求触发 effect（deps `[domain,clusterId,committedSearch,retryToken]`）、无 `onOpenChange`/翻页/`loadMore`；F-03（154 与 1540 均 1 次） |
| A4 | PASS | 探针：`applyCandidateResponse` 整体替换（3→1 无并集）、陈旧响应返回**同一引用**、items 复制 |
| A5 | PASS | I-09/I-10；参数名集合精确 7 项 / 5 项，负向断言无 `deleted/include/only` |
| A6 | PASS | 模块 B（`real_scope`，harness 3 条守卫 PASS）：全库 120 → EDITOR `total=3`；F-09 含 `3`、**不含** `120` |
| A7 | PASS（DOM 粒度见 F041-R-03） | 探针 36 项：5 个 view kind、5 个 role、四态文案 `Set.size=4`、idle 仅 host+空集群可达 |
| A8 | PASS | 失败 `calls.length` 不增 → 显式重试恰 +1 → 恢复 success；error 文案含「可重试」、不含「无匹配/暂无数据」；`canRetry` 仅 error |
| A9 | PASS | F-08 文案含 `154` 与 `100` 且命中 `/(分页|上限|前)/`；`total==items`/`total=0` 不提示；文案不含 `120` |
| A10 | PASS | I-10/I-12/I-13（401/403/404、`deleted=include` 403）/I-14（跨 Cluster、VM 类型、不存在 → 422 同固定 field；hostname 冲突 409） |
| A11 | PASS | 契约与 `frontend/src/api/**` 零 diff |
| A12 | PASS | I-16（`f41n-0110`/`F41N-0110`/中段 `n-0110` 均 `total=1` 同一对象；候选与同参列表页 `total` 相等）；backend 零 diff |
| A13 | PASS | `controls.tsx` 零 diff；逐文件对照：仅 `ResourceForm 4→3`、`VirtualMachineFields 1→0`，其余 21 文件计数不变 ⇒ 58/22 是方案 A 的必然后果（非越界） |
| A14 | PASS | 自跑 `test_virtual_machine.py`+`test_search.py` **38 passed**、harness 3 passed、收集 **948**（SKIPPED 仍仅 F016）、`smoke:client` **352 passed 0 failed**、`build` exit 0 |
| A15 | PASS | I-17（15 次两域读取前后 `audit_logs`/`resources` 计数不变） |
| A16 | PASS | 探针：pinned 在 success(含/不含)、loading、error、empty、idle 六种输入下**恰一次**且首项；I-07 服务端接受 + T19 |

## 3. 架构硬约束（PASS）

逻辑/视图分离成立（`candidateSelectModel.ts` 仅 2 条 `import type`，无 JSX/React/antd）；`CandidateSelect` 引用仅 3 处（定义 + VM Host + ResourceForm，IP 页/列表/全局搜索/`interfaceIpSelection.ts` 均 0 命中）；`showSearch={{filterOption:false,…}}` 经 rc-select 语义核验生效；`disabled` 仅 `submitting`；唯一 `setTimeout` 用纯模块常量、`package.json`/lock 零 diff。

## 4. TD 更正 T1–T11 与 58/22

T1–T11 **只改形态/基线、不改验收强度**（T3 换成更强的逐文件对照；T4 把 backend 零 diff 收窄为「生产代码/配置零 diff + 仅允许 F041 测试资产」）。58/22 与架构文字 60/23 的偏差**不构成违约**：`grep "<Select"` 不匹配 `<CandidateSelect`，方案 A 必然 60−2/23−1；实质要求（`controls.tsx` 零 diff + 每文件计数不变）已独立复算成立 → F041-R-05 建议勘误。

## 5. 缺陷与跟进

**无必须修复项。** F041-R-01（LOW，DR-F041-09 的 Product 编辑性追认未留痕）、F041-R-02（LOW，放行模式 `f041_*.py` 应为 `(test_)?f041_*.py`）、F041-R-03（LOW，`role:"log"` 为模型声明值，`EmptyState` 未设该 role，报告措辞略高于实测粒度）、F041-R-04（NOTE，F-03 属请求构造器级断言，A3 组件级保证由代码审读承担）、F041-N-07（NOTE，关下拉回灌空检索 → 额外 1 次基准请求，次数仍与总量无关）、F041-N-08（NOTE，`implementation.md` 行数笔误）、F041-R-06（NOTE，browser-supplementary 缺来源头）。

**旧缺陷**：Tester 的 4 条 NOTE 全部复核接受；「无 BLOCKER/HIGH/MEDIUM」自评与独立复核一致。

## 6. FOLLOW-UP（均不阻塞合并）

| ID | 内容 | Owner |
| --- | --- | --- |
| FU-1 | 就 DR-F041-09 与 product N9 的「测试资产」解读取得 Product 编辑性追认并留痕（不重开已交付范围） | Product / 协调器 |
| FU-2 | Architect 勘误：放行模式 `f041_*.py`→`(test_)?f041_*.py`；`60/23`→`58/22` 并注明实质判定 | Architect |
| FU-3 | `implementation.md` 两处措辞（`empty→EmptyState(log)`、`−129/+62`）与 `artifacts/browser-*supplementary.txt` 补来源头 | Frontend / 协调器 |
| FU-4 | 把「交互序列只发 1 次请求」「检索选中后字段标签不退化」纳入可重复前端入口（纯逻辑驱动，不新增依赖） | Tester / F043 |
| FU-5 | 在 plan 证据中登记：TE 在 `698f11b`+工作树产出、实现提交为 `ad56072`，Reviewer 已在 `ad56072` 复跑 I/F/S 且一致 | 协调器 |

## 7. 报告措辞核查

浏览器证据（`implementation.md` §4/§6、TE §2.7/§2.9）已如实标为「环境侧、`/tmp` 脚本、`page.route` mock、不入库、非门禁」；A7/A8/A16 的 PASS 同时指向 U1（真实 DOM aria/屏幕阅读器/debounce 时序 `NOT_TESTED`）；未把浏览器断言当作 A1 证据；`352/0`、`948`、`58/22`、零 diff 全部可复算一致。唯一缺口：入库的两份 `browser-*supplementary.txt` 无来源头（F041-R-06）。

## 8. 未审查项

真实浏览器视觉与人眼复核（截图在 `/tmp`，不可读图）、屏幕阅读器播报、antd 虚拟滚动与完整键盘矩阵、真实前后端端到端点击流（F016 栈 `127.0.0.1:18080` = `000`，已由 I 层 + F 层组合替代且 AQ-4=B 已裁定）、antd 关下拉回灌的真实时序与 300ms debounce 可感知时延、性能指标（不在验收范围）、需求 §31–§33 一期整体验收（归 F045）、F023/F034/F037/imports 等其余回归组（本次仅重跑 virtual_machine+search 38 与 harness 3，其余沿用 TE 记录）。

## 9. 声明

- **APPROVED WITH FOLLOW-UP**：A1–A16 全部满足且证据可信（A1 由真实 PG + 生产 app + DB 行 + T19 审计承载，非 mock）；F/I/S 三层与构建在**候选 HEAD `ad56072`** 独立重跑通过；无 BLOCKER / HIGH / 必须修复 MEDIUM。
- **可进入 Merge Gate**；批准仅对候选 HEAD `ad56072` 与 Base `refs/heads/v3.4`=`d5c0a4c` 有效；任一变化须重新 Review。
- FU-1..FU-5 与 NOTE 建议不构成产品或架构决定；F041-R-01 的 N9 解读由 Product 追认，Reviewer 不代为裁定。
