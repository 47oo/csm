# F045 A9 — 六份 Review 报告的 NOT TESTED / BLOCKED 逐条归类

- **依据**：A9（`docs/features/F045/product.md` v1）+ architecture §7 A9；读取 `docs/features/{F037,F038,F039,F040,F041,F043}/review-report.md` 的「未审查项 / NOT TESTED / BLOCKED / FOLLOW-UP」段
- **归类口径**：「本轮复核」= 本轮 F045 有本轮实测证据（附证据文件）；「如实重记」= 仍无法验证或仍开放，本轮不主张 PASS；「不适用（附依据）」= 该 Feature 声明范围外/已由本轮他项完整覆盖的依据充分项
- **禁止**：不以文件存在、局部通过或他人报告数值替代复核；不复用旧 PASS 作为新验收证据
- **结论**：无「以未验证冒充通过」的残留；**F039 唯一 BLOCKED 项本轮已转实测 PASS（`a09-f016-acceptance.log`：40 passed）**；余下 NOT TESTED 项均如实重记，不影响 A1–A8 判定

## 1. F037（`review-report.md` §2.5 / §3 / §4 / §5）

| # | 原项 | 归类 | 依据 / 本轮证据 |
| --- | --- | --- | --- |
| 1 | 无 lxml（`openpyxl.LXML=False`）环境 `u15`/`u4` False 分支 **NOT TESTED**（FU-06） | 如实重记 | 本轮环境 `openpyxl 3.1.5 LXML=True`、`lxml 5.2.1`（env.md §1），False 分支仍未触发；A2 只证明 True 分支 |
| 2 | 真实内存耗尽不可测（`OPEN-T4` NOT TESTED） | 如实重记 | 属 architecture §3 允许排除类「真实 OOM/资源上限」；本轮未制造 OOM |
| 3 | `LargeZipFile` / `NotImplementedError` / `InvalidFileException` 真实可达性未验证 | 如实重记 | 未新增产品测试（N2/§6）；A2 只覆盖既有断言可达的 8 类 |
| 4 | `EOFError` 可达性未裁定（REV-F037-04） | 如实重记 | 未裁定即为开放；A2 未覆盖，不主张 PASS |
| 5 | 未审查：前端、Schema/Migration、`pg_locks` 直接观测 | 不适用 | 前端由本轮 A5 独立实测（352/14）；Schema 零 DDL（`layers.database=false`）故 `pg_locks` 不在 F037 可观察面；F037 授权范围仅后端解析路径 |
| 6 | F045 整体验收未做 | 本轮复核 | 本报告 §2（A1–A9）即该项执行结果 |

## 2. F038（§3 F-1/F-2 / §4 未审查项）

| # | 原项 | 归类 | 依据 / 本轮证据 |
| --- | --- | --- | --- |
| 1 | 真实 OOM / 无 lxml / S-W2 原规模 NOT TESTED | 如实重记 | 同 F037-1/2；属 §3 允许排除类，未实测 |
| 2 | 5000 行写入端点与 S-W2b 单侧断言 NOT TESTED | 如实重记 | A1 全量未覆盖该端到端规模场景；不新增产品测试 |
| 3 | **F-1**：§13.9 两例（无 `<dimension>` / `dimension` 不一致）未实现且未登记 | 如实重记 | 仍未实现；本轮 A1 只运行既有用例，未补产品测试；**记录缺口仍在**，Owner 仍为 Tester/协调器 |
| 4 | **F-2**（LOW）：测试模块 3× ruff F811 | 本轮复核（**仍存在**） | 本轮实测 `ruff check backend/tests/integration/test_f038_parse_bounds.py` → `Found 3 errors`（`role_client_factory` 重名）；非产品代码缺陷，未修复（写入范围外） |
| 5 | 未跑 Compose / 前端（`layers.frontend=false`，归 F045） | 本轮复核 | A5 + A7（Compose 真实栈 + nginx 真实 HTTP）已执行 |
| 6 | S 层静态守卫（F038 自身） | 本轮复核 → **DEF-1 已修复并复测通过** | A1 中 `test_td_f038_s1_zero_diff_and_frozen_contract` / `test_td_f038_s6_change_surface_is_two_services` 失败，见本报告 DEF-1 |

## 3. F039（§2 旧缺陷复核 2 / §4 未审查项 / FOLLOW-UP）

| # | 原项 | 归类 | 依据 / 本轮证据 |
| --- | --- | --- | --- |
| 1 | **`F016_ACCEPTANCE=1` BLOCKED**（活动 HTTP 栈不可用，`ConnectError`，记 `BLOCKED / NOT TESTED`） | **本轮复核（PASS）** | 本轮 Compose 栈可用：`F016_ACCEPTANCE=1 F016_BASE_URL=http://localhost:18080 pytest tests/integration/test_f016_acceptance.py` → **40 passed**；`test_f028_acceptance.py` → **4 passed**（`a09-f016-acceptance.log`） |
| 2 | FOLLOW-UP：F045 须覆盖 F039 计数与 EXPLAIN 证据 | 本轮复核（PASS） | A3：`test_f039_query_count.py` + `test_f039_scope.py` + `test_dashboard.py` → 27 passed（含 A8 断言 EXPLAIN 无 `Seq Scan` 与索引存在、A3 `real_scope` 用例）；`a03-capacity.log` |
| 3 | 未审查：响应耗时/性能（N7）、前端 UI 交互 | 不适用 | 性能阈值不在 F045 验收范围（product §7「不做性能调优与新 NFR 阈值」）；前端交互由 A5 独立实测 |

## 4. F040（§6 缺陷 / §7 未审查项）

| # | 原项 | 归类 | 依据 / 本轮证据 |
| --- | --- | --- | --- |
| 1 | **F-02**：8 个 `.log` 证据被 `.gitignore` 命中未入库 | 本轮复核（**已闭环**） | `git ls-files docs/features/F040/artifacts \| grep '\.log$'` → 8 条已跟踪（build/npm-ci/smoke/typecheck 及 te-* 3 条）；本轮 F045 自身沿用同一处理（见本报告需 `git add -f` 清单） |
| 2 | 未验证 registry 长期可用性、`--offline` 变体、非 linux-x64 optional 条目 | 如实重记 | 本轮未做 registry 可用性/跨平台验证；构建未使用 `--offline`；平台固定 linux-x64 |
| 3 | 浏览器/视觉/全页巡检、真实前后端集成、§31–33 整体验收 NOT_REQUIRED（归 F045） | 本轮复核（部分） | 真实前后端集成与 §32 关键路径已执行（A7）；**浏览器视觉/全页巡检未执行 → 如实重记 NOT TESTED**（AQ-4=B 禁浏览器依赖） |
| 4 | F-01/F-03/F-04/F-05 等文档与记账类 LOW/NOTE | 不适用 | 文档措辞/记账项不属可执行验证；本轮不改他人文档（写入范围仅 F045） |

## 5. F041（§8 未审查项 / §6 FOLLOW-UP）

| # | 原项 | 归类 | 依据 / 本轮证据 |
| --- | --- | --- | --- |
| 1 | 真实浏览器视觉、人眼复核、屏幕阅读器播报、antd 虚拟滚动与完整键盘矩阵、300ms debounce 真实时序 | 如实重记 | AQ-4=B 不引入浏览器/E2E；本轮只有逻辑层入口（A5 的 14 例）与真实 API（A7） |
| 2 | 真实前后端端到端点击流（F016 栈 `:18080` = `000`） | 本轮复核（PASS，替代口径） | 本轮 `:18080` 栈可用：A7 42 步 + round-2 15 步经 nginx 真实 HTTP；F016 验收 40 passed。**真实浏览器点击仍 NOT TESTED**（同上） |
| 3 | 其余回归组（F023/F034/F037/imports 等）本次仅重跑部分 | 本轮复核（PASS） | A1 全量 `tests/`（第二轮终态：969 passed + 6 skipped；第一轮 967 passed + 6 skipped + 2 FAIL 即 DEF-1）覆盖全部既有回归组；A2 单独 147 passed |
| 4 | 需求 §31–§33 一期整体验收（归 F045） | 本轮复核 | §32 关键路径见本报告 A7；§33 场景由 A7-23…A7-27（hostname/IP/Cluster/Service 查询）覆盖；整体结论见本报告状态 |
| 5 | FU-1（DR-F041-09 Product 追认留痕）、FU-2/FU-3 文档勘误、FU-5 记账 | 不适用 | 属 Product/Architect/协调器的文档追认与勘误，非可执行验证项；本轮不改其文档 |

## 6. F043（§3 未审查项 / §1 第 4 行 / §2 NOTE）

| # | 原项 | 归类 | 依据 / 本轮证据 |
| --- | --- | --- | --- |
| 1 | `npm run build` 未复跑 | 本轮复核（PASS） | A5 `npm run build` → 退出 0（`frontend-build.log`） |
| 2 | 浏览器/DOM 真实行为、真实 ≥101 对象落库、服务端 409 真路径 NOT TESTED | 如实重记（服务端部分本轮复核） | 服务端候选分页/超限由 A4（`test_f041_candidate_scope.py` I-11/I-15）实测；**浏览器 DOM 行为与「真实 ≥101 对象经 UI 选定」未复核 → NOT TESTED** |
| 3 | X4（`App.tsx`）三份文档一致标 NOT TESTED | 如实重记 | A5 只跑 typecheck/build/两入口，未对 `App.tsx` 交互做运行时观测 |
| 4 | 重复性仅 2 次抽样 | 本轮复核（PASS） | `npm run test:interactions` 本轮执行 **2 次**，均 `14 passed, 0 failed`（`frontend-interactions.log` run#1/run#2） |

## 7. 本轮得出的新问题（不属于旧 Review 项）

- **DEF-1（HIGH）**：`backend/tests/integration/test_f038_parse_bounds.py` 两个 S 层静态守卫以 `START_COMMIT=8e609ca`（F038 自身起点）为基线断言「零 diff / 仅两 service 有实现 diff」，在合并后基线上必然失败。**终态：已修复**（新增 `F038_MERGE_COMMIT=adef87a` 钉住 F038 区间，断言未放宽），`pytest tests/integration/test_f038_parse_bounds.py` 复跑全绿（76 passed），Reviewer 独立重跑两例 2 passed。
