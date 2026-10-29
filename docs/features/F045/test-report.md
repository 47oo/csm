# F045 CHG-015 整体回归与部署等价验收 — TEST REPORT

- **Task**：F045 / TEST_DESIGN + TEST（两段，同一交付）｜Tester｜分支 `feature/F045-change-set-acceptance`，start_commit `fa8a568`，head `9941f92`；plan rev25 / requirements rev16
- **Basis**：`docs/features/F045/product.md` v1（A1–A12 / N1–N8）、`architecture.md` v1（§2 部署口径、§3 pytest 规则、§4 证据结构、§6 不新增脚本、§7 命令表）；`docs/project/handoff.md`；`docs/project/implementation-rules.md`

## §1 TEST DESIGN — TD-F045-1（v1，2026-10-29）｜结论：`TEST DESIGN READY`

**可验证性前提**：真实 PG 测试库 `csm_f045_test`（`127.0.0.1:55432`，postgres:16-alpine 容器 `csm-f037-pg`）；Compose 栈经 nginx `:18080`；现有测试/脚本/前端入口零改动即可覆盖 A1–A9（无需新增脚本，§6）。TD 仅判定「方案可验证」，不构成测试通过。

| A | 判定式（全部满足才 PASS，否则 FAIL/BLOCKED） | 证据 |
| --- | --- | --- |
| A1 | `tests/` 全量（含 `smoke/`）真实 PG 执行，`-ra` 输出含总数/passed/failed/skipped 与每条 skip 原因；failed=0、error=0；排除仅限 §3 四类且逐条列 nodeid+原因 | `full-pytest.log` |
| A2 | §7 五文件全绿；四端点×8 类解析异常 = 422 `IMPORT_INVALID_FILE{reason:"unreadable"}`（断言来自既有用例） | `a02-import-parse.log` |
| A3 | §7 三文件全绿；F039 查询计数常数上界在含空页/多 Pool 场景成立，结果集与总量不变（T32） | `a03-capacity.log` |
| A4 | §7 四文件全绿；部分授权非 ADMIN 下全局搜索（含 §17.1 关联行）与 Dashboard 计数仅含可见集群，无越权对象与规模泄露（T88） | `a04-scope.log` |
| A5 | `typecheck` 退出 0；`build` 退出 0；`smoke:client` 恰 352 passed；`test:interactions` 恰 14 passed；断言不得放宽 | `frontend-*.log` |
| A6 | 3 个 `scripts/test_*.py` 全绿 | `scripts-pytest.log` |
| A7 | 真实 Compose（`--no-build` 优先）起栈，nginx `:18080` 真实 HTTP 走完 §32 全部关键路径且每步 HTTP 状态 + 关键字段断言通过；不可用时降级等价栈并逐条登记未覆盖项，不得写「Compose 通过」 | `compose-up.log`、`compose-ps.log`、`http-acceptance.log` |
| A8 | `validate_project_state.py` VALID、`render_project_views.py` 无漂移、`alembic heads`=`0015`（协调器执行，Tester 仅登记命令） | `plan-validate.log`、`plan-render.log`、`alembic.log` |
| A9 | 六份 review-report 的 NOT TESTED/BLOCKED 每条归入「本轮复核 / 如实重记 / 不适用（附依据）」，且复核项有本轮实测证据 | `a09-review-classification.md` |
| A10 | 全部证据落 `docs/features/F045/artifacts/**` 且 header 含 cmd/start_commit/head/env/timestamps/tool_versions/exit_code；`.log` 需 `git add -f` 清单 | 同目录 + `env.md` |
| A11 | 未执行项显式 NOT TESTED/BLOCKED + 原因；任何位置无估算值充当 PASS | 本报告 |
| A12 | 仅当 A1–A11 全通过且无 BLOCKER/HIGH 才由协调器改 `acceptance=COMPLETE`（追加证据，不删 52 条）；Tester 不执行 | plan diff（协调器） |

**边界/并发场景映射**：唯一性/并发由既有 `test_*_constraints.py`、`test_db_concurrency.py` 在 A1 全量内覆盖（真实 PG 提交路径），不在 A2–A4 重复发明。**可观察结果**：pytest 汇总行、前端计数行、HTTP 状态 + 响应字段。**夹具/环境风险**：R1 镜像陈旧（`csm-csm-*:test` 构建于 2026-10-27，早于基线）→ 若 `--no-build` 实测代码非基线代码则须一次 `up --build` 并如实记录；R2 `.log` 被 gitignore；R5 跨功能交互缺口标 NOT TESTED。

## §2 TEST — TEST-F045-1（v1，2026-10-29）｜结论：`TEST BLOCKED`（A1 FAIL，未达全绿；不写 PASS）

**Environment**：真实 PG `csm_f045_test`（`127.0.0.1:55432`，postgres:16-alpine，本轮新建）；Compose `csmtest`（`compose.yaml`+`compose.test.yaml`，nginx `:18080`）；版本与命令见 `artifacts/env.md`。start_commit `fa8a568` / head `9941f92`（零 diff 守卫实测为空：`backend/app`、`backend/alembic`、`frontend/src`、`frontend/package.json`、`docs/{api,product,database}`、`compose*.yaml`、`.gitignore`）。

| A | 结论 | 实测证据（日志） |
| --- | --- | --- |
| A1 | **FAIL** | `full-pytest.log`：`2 failed, 967 passed, 6 skipped in 1357.44s`（收集 975）；2 条失败按 nodeid 重跑 1 次仍 FAIL（`2 failed in 0.95s`）；6 条 skip 原文原因已入日志，并全部补充实测：`F016_ACCEPTANCE=1` → 40 passed、`test_f028_acceptance.py` → 4 passed（`a09-f016-acceptance.log`），非超级用户 DB owner 的 V3b → 1 passed（`full-pytest.log` 末段）。**无允许排除项**（失败不属 §3 四类） |
| A2 | PASS | `a02-import-parse.log`：`147 passed`（F037 解析异常 422 `IMPORT_INVALID_FILE{reason:"unreadable"}` 四端点×8 例、T27/T28/T72/T107–T116/T126 回归） |
| A3 | PASS | `a03-capacity.log`：`27 passed`（F039 `q_svc` 恒 11/空页/多 Pool、EXPLAIN 无 Seq Scan、A3 `real_scope`、Dashboard 结果集与总量不变） |
| A4 | PASS | `a04-scope.log`：`48 passed`（§23.2 部分授权非 ADMIN：全局搜索含 §17.1 关联行、Dashboard 计数、F041 候选分页/超限提示仅可见集群） |
| A5 | PASS | `frontend-typecheck.log`(0) / `frontend-build.log`(0) / `frontend-smoke.log`：`352 passed, 0 failed` / `frontend-interactions.log`：`14 passed, 0 failed`（run#1 与 run#2 一致）；断言未放宽 |
| A6 | PASS | `scripts-pytest.log`：`113 passed`（3 个 `scripts/test_*.py`） |
| A7 | PASS（Compose 真实栈） | `compose-up.log`/`compose-ps.log`/`http-acceptance.log`：`up -d --no-build` 拓扑+串序成立（db healthy → migrate exit 0 → bootstrap exit 0 → backend healthy → nginx）；因复用镜像构建于 2026-10-27 早于基线（4 个 `services/*.py` md5 不同，`a07-image-staleness.txt`），按 §2「镜像不可用」执行**一次** `up -d --build`，重建后 `backend/app/**.py` 与基线逐文件 md5 一致、前端 `dist/assets/index-*.js` 与本地 `npm run build` 产物 md5 一致；空卷重建复跑证明容器内 `alembic upgrade head` 全链 `0001→0015`（15 条）与 `bootstrap: created initial admin 'admin'`。经 nginx `:18080` 真实 HTTP 共 **61 步 0 FAIL**：§32 关键路径 42 步（登录/Cluster/BareMetal/VM+Host/Interface/Network/Pool MANUAL+AUTO/Service/Endpoint/手动+自动 IP 绑定/按 hostname·IP·Cluster·Service 查询/全局搜索/Dashboard/整批导入 created=2/Audit）+ 逻辑删除与 ADMIN 恢复 15 步（`?version=` 契约修正后）+ 空卷冒烟 4 步；重复 hostname/IP/Cluster code 409、非法 CIDR 422、跨 Cluster Host 绑定 422 均实测阻断。收尾 `down -v`（容器与卷已删） |
| A8 | **NOT TESTED（协调器执行）** | Tester 未执行；命令见 `env.md` §3。仅附只读旁证：栈内 `alembic_version=0015_user_cluster_authorizations`（`compose-ps.log`），判定权归协调器 |
| A9 | PASS | `a09-review-classification.md`：六份 review 的 NOT TESTED/BLOCKED 逐条归类；F039 唯一 BLOCKED（`F016_ACCEPTANCE=1`）本轮转实测 PASS；F040 F-02（`.log` 未入库）本轮核查已闭环；F038 F-2（3× ruff F811）本轮复核**仍存在**；余项如实重记 |
| A10 | 部分 | 证据齐全且 header 含 cmd/start_commit/head/env/timestamps/tool_versions/exit_code；`.log` 被 `.gitignore` 命中，入库需协调器 `git add -f`（见下清单）；plan `evidence` 未写（协调器） |
| A11 | 遵循 | A8 标 NOT TESTED；未执行/不可测项均标 NOT TESTED 并给原因；无估算值充当 PASS |
| A12 | **NOT TESTED** | 协调器职责，未执行 |

**执行修正（非产品缺陷）**：`http-acceptance.log` round-1 中 A7-32/33/34/36/37 的 5 个 FAIL 系我方驱动脚本签名错误（DELETE/restore 需 `?version=N`、DELETE 成功码 204，见 `docs/api/F011.md` §6.5/§6.6），修正后 round-2 15/15 PASS；已在日志内标注，不计为产品缺陷。

### Defects

| ID | Severity | Layer | Location | 期望 / 实际 | 影响 | Owner | 必修 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| DEF-1 | HIGH | 测试（非产品代码） | `backend/tests/integration/test_f038_parse_bounds.py:153,2019,2205`（`START_COMMIT="8e609ca"`） | 期望全量 pytest 在合并基线上全绿；实际 `test_td_f038_s1_zero_diff_and_frozen_contract`（`frontend/**` 被 F040/F041/F043 改动）与 `test_td_f038_s6_change_surface_is_two_services`（`backend/app/services/{dashboard,ip_capacity}.py` 由 F039 改动）必然 FAIL，重跑 1 次仍 FAIL | A1 无法达成全绿 ⇒ 整体验收阻塞（产品行为经 A2–A7 实测未见缺陷） | 协调器（授权 F038 测试资产修正；Tester 本轮写入范围不含测试文件） | 是 |
| DEF-2 | LOW | 测试 | 同上模块 `role_client_factory` 3× F811 | 期望 ruff 干净；实际 `ruff check` → `Found 3 errors`（F038 F-2 遗留） | 不影响判定，属测试代码卫生 | 协调器 | 否 |
| DEF-3 | NOTE | 环境 | 复用镜像 `csm-csm-*:test`（2026-10-27）早于 start_commit | 期望镜像即基线；实际需一次 `up --build` 才能承载变更集代码（§2 已按「镜像不可用」处理并留证） | A7 口径已按基线镜像重跑，结论不受影响 | 协调器（后续预构建镜像） | 否 |

**DEF-1 建议修法（供协调器裁定，Tester 未改动）**：把 F038 S 层守卫的 diff 断言范围收窄为「F038 自身 commit 区间 + 允许列表」，或将该二例标为基线绑定用例并在合并后跳过；不得放宽 A1 判据（N3/§3）。

### 未验证项（NOT TESTED / BLOCKED，本轮不主张 PASS）

1. **A8 / A12**：协调器执行项，Tester 未执行（NOT TESTED）。
2. **真实 OOM / 无 lxml（`openpyxl.LXML=False`）/ `LargeZipFile` / `InvalidFileException` / `EOFError` 可达性**：环境不可造（`openpyxl.LXML=True`），属 §3 允许排除类（NOT TESTED）。
3. **浏览器真实行为**：视觉/DOM/屏幕阅读器/antd 虚拟滚动/真实点击流/≥101 对象经 UI 选定（AQ-4=B 禁浏览器依赖，NOT TESTED）；真实 API 侧已由 A4/A7 覆盖。
4. **超大规模端到端**：5000 行写入端点、S-W2 原规模、真实 ≥101 对象落库 UI 选定（NOT TESTED）。
5. **性能/NFR 阈值**：不在 F045 范围（product §7）。
6. **非 linux-x64 平台 / registry 长期可用性 / `--offline` 构建**：未验证（NOT TESTED）。
7. **`.log` 入库与 plan `evidence`**：待协调器 `git add -f` 与写入（A10 部分完成）。

### 需 `git add -f` 的文件（`.gitignore` 命中 `*.log`；不得改 `.gitignore`）

`docs/features/F045/artifacts/{full-pytest,scripts-pytest,a02-import-parse,a03-capacity,a04-scope,a09-f016-acceptance,frontend-typecheck,frontend-build,frontend-smoke,frontend-interactions,compose-up,compose-ps,http-acceptance}.log`；非 `.log` 但需入库：`artifacts/{env.md,a09-review-classification.md,a07-image-staleness.txt}`、`docs/features/F045/test-report.md`。

**Issues / Next**：DEF-1 由协调器裁定并调度修复（测试资产）→ 修复后仅需重跑 A1（全量 + 失败项重跑）与本报告复核；A8/A12 由协调器执行；`.log` 入库后以 `git ls-files` 证明。**本报告不放行 Review、不批准合并、不恢复 `project.acceptance`**。
