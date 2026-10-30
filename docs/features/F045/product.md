# F045 CHG-015 变更集整体回归与部署等价验收 — PRODUCT 阶段报告

- **状态**：READY FOR ARCHITECT
- **版本**：v1（2026-10-29）；FEATURE / P0 / M31；分支 `feature/F045-change-set-acceptance`（交付线 `v3.4`，start_commit `fa8a568b912d7aea9806a58616e98867a5786808`）；plan revision 25 / requirements revision 16
- **角色产物**：product-manager 只读产出，协调器持久化
- **Basis**：requirements rev16 §31/§32/§30/§20 及 T27、T28、T32、T72、T88、T107–T116、T126；plan rev25 F045（`depends_on=F037,F038,F039,F040,F041,F043`、`blocking_decisions=[]`、`layers` 全 false、`api_required=false`）；AQ-1=A / AQ-4=B / AQ-5=A / AQ-6=(i) 已 CONFIRMED；`project.acceptance.status=PENDING` + 52 条历史证据 + basis；六份 review-report（F037/F038/F039/F040/F041/F043 均 APPROVED WITH FOLLOW-UP、无必须修复项）
- **环境事实（协调器 2026-10-29 实测）**：Docker 29.8.2 + Compose v5.6.0 可用；仓库含 `compose.yaml` / `compose.test.yaml`；运行中容器 `csm-f037-pg`（postgres:16-alpine）；`TEST_DATABASE_URL='postgresql+psycopg://csm:csmtest@127.0.0.1:55432/csm_f037_test'`；`scripts/` 含 `test_render_project_views.py`、`test_validate_project_state.py`、`test_collect_host_info.py`

## 1. 性质

- 验收型 Feature：只验证已交付变更集，**不新增业务规则、不改契约与 Schema、不改产品代码、不回写 F001–F036 证据**。
- 验收对象仅为本变更集**实际合并**的 6 项；F042 / F044 已 CANCELLED，不纳入、不据其推断任何行为。

## 2. 变更集清单

| # | Feature | 交付要点 |
| --- | --- | --- |
| 1 | F037 | 四导入端点解析阶段异常统一归入既有 422 `IMPORT_INVALID_FILE{reason:"unreadable"}`，白名单 8 类异常 |
| 2 | F038 | 导入解压/解析内存边界加固：峰值有界、同字节输入逐字一致、零可观察上限新增 |
| 3 | F039 | Dashboard 容量查询批量化（`q_svc` 恒 11）与查询计数基准，保留公式单点，§20/T32 口径不变 |
| 4 | F040 | 前端依赖 `antd`/`tailwindcss`/`@tailwindcss/vite` 收敛为 `~` 并同步 lockfile，源码零 diff |
| 5 | F041 | VM Host 与 Resource 创建页 Cluster 候选由服务端检索分页（§28.1 / T127–T129），零契约 diff |
| 6 | F043 | 前端交互回归可重复入口（`npm run test:interactions` 14 例 + harness 去重），无浏览器依赖 |

**口径**：各 Feature `DONE` 仅覆盖其自身范围与候选 HEAD。**不等于**变更集整体验收——跨功能交互从未在同一基线、同一真实数据库、同一部署形态下整体验证过；本轮必须以合并后的基线重跑，不得拼接局部 PASS 形成整体结论。

## 3. 验收范围矩阵（A1–A12）

| ID | 断言 |
| --- | --- |
| A1 | 全量后端 pytest 对**真实 PostgreSQL** 全绿并留存原始日志（总数 / passed / failed / skipped 与每条 skip 原因）；不得以子集、mock 或 SQLite 替代 |
| A2 | 四导入端点（预校验 / 写入）× 8 例解析异常返回 422 `IMPORT_INVALID_FILE{reason:"unreadable"}`；T27、T28、T72、T107–T116、T126 回归通过 |
| A3 | §20 容量口径（T32）无回归；F039 查询计数常数上界在代表性规模（含空页、多 Pool）复核并与基准对照，结果集与总量不变 |
| A4 | §23.2 范围过滤（T88）：部分授权非 ADMIN 实测全局搜索（含 §17.1 关联行）与 Dashboard 计数仅覆盖可见集群，未授权对象不出现且不泄露规模 |
| A5 | 前端 `typecheck` / `build` / `smoke:client`（352 passed）/ `test:interactions`（14 passed）全通过；通过项变化须由新增用例解释，不得放宽断言 |
| A6 | `scripts/` 单测（`test_render_project_views.py`、`test_validate_project_state.py`、`test_collect_host_info.py`）全绿并留日志 |
| A7 | 真实 `docker compose`（`compose.yaml`）完成 §32 关键路径：创建 Cluster/BareMetal/VM 与 Host、维护 Interface/Network/Pool/Service、手动与自动分配 IP、按 hostname/IP/Cluster/Service 查询、逻辑删除与恢复、一次整批导入；Compose 不可用时以**如实记录**的等价栈执行并声明未覆盖项 |
| A8 | `validate_project_state.py` VALID、`render_project_views.py` 派生视图无漂移；alembic 迁移链 `up` 后 schema 与基线一致、head 与计划一致 |
| A9 | 六份 Review 的 NOT TESTED / BLOCKED 项逐条归类为「本轮复核」「如实重记」「不适用（附依据）」，不得以文件存在或局部通过替代复核 |
| A10 | 全部证据落 `docs/features/F045/**`（含命令、时间、基线 commit、环境变量的可追溯摘要），并由 plan F045 `evidence` 引用 |
| A11 | 未执行项标 NOT TESTED / BLOCKED 并写明原因；**禁止写 PASS**；不得用估算值代替实测 |
| A12 | 仅当 A1–A11 全部通过且无 BLOCKER / HIGH 后，由协调器核验并恢复 `project.acceptance.status=COMPLETE`，证据**追加**而不删除既有 52 条；任一 A 项不通过则保持 PENDING 并登记缺陷 |

## 4. 禁止清单

N1 不新增/修改业务规则（冲突走 change-control）。N2 不改契约、错误码、上限、Schema/Migration。N3 不为让测试通过而改产品代码（发现缺陷回退对应 Feature）。N4 不回写 F001–F036 证据与判定。N5 不把局部 PASS 拼成整体结论。N6 不用估算/他人报告数值代替实测。N7 不纳入 CANCELLED 项。N8 不跳过真实 PostgreSQL 或部署等价验证。

## 5. Blocking Questions

**无。** AQ-1/AQ-4/AQ-5/AQ-6 均已 CONFIRMED；AQ-7 对象为 `.pi/agents/*.md` 且 F044 已 CANCELLED，不属本轮验收对象，不阻塞。

## 6. Non-blocking 观察（交 Architect / Tester）

| ID | 观察 | 归属 |
| --- | --- | --- |
| ON-1 | 部署等价栈判定：何时可用 TestClient + 真实 PG 替代 Compose，须记录 Compose 不可用原因、替代栈版本与拓扑、覆盖的 §32 路径与未覆盖项；倾向要求 Nginx 入口代理、容器内迁移与首个 ADMIN 初始化必须由真实 Compose 承载 | Architect |
| ON-2 | 全量 pytest 耗时与范围裁剪规则（允许排除的类别、重跑上限）；耗时不得成为永久裁剪理由 | Architect / Tester |
| ON-3 | 证据目录结构（`artifacts/` 命名、日志 header 必含字段、`.log` 被 gitignore 时的入库处理） | Architect / 协调器 |
| ON-4 | `project.acceptance` 恢复条件与措辞（basis 如何覆盖 revision 25、证据追加顺序、最低证据类型集合） | Architect / 协调器 |
| ON-5 | 是否新增验收脚本（如 `scripts/acceptance/`）与夹具；AQ-4=B 下不得引入浏览器/E2E 依赖 | Architect |

## 7. 明确不做 / 文档更新

不做：重开或重评 F001–F036；性能调优与新 NFR 阈值；新页面/组件；浏览器 E2E 依赖；F042/F044 替代实现。`docs/product/**`、`docs/api/**`、`docs/database/**` 零 diff；`docs/features/F045/**` 记录真实证据；`project.acceptance` 由协调器核验后更新。
