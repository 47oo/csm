# F036 F032–F035 Review 跟进项收敛 — REVIEW 阶段报告

- **状态**：**APPROVED WITH FOLLOW-UP**
- **版本**：v1（2026-10-26）；plan revision 22；需求 revision 14（不变）；Reviewer
- **审查基线**：分支 `feature/F036-review-followup-closeout`；start_commit `a2e91949cb2d812c1e0ab48f9f957718fdba2e81`；候选 **HEAD `224291bc15ee31d563c7bb1e5460272d053ac9ec`**；Base **`refs/heads/v3.3` = `a2e9194`**（未使用同名 tag `v3.3` = `3ca634b`，其为 branch 祖先）；merge-base 同 Base（无分叉）；完整范围 `a2e9194..224291b` = 9 commits / 46 files（+5986/−479）；工作区 clean、暂存区空、无非忽略未跟踪文件。
- **输入**：CHG-014（APPROVED）；`docs/features/F036/{product.md v1, architecture.md v2（§12 TD-I-1…TD-I-10 定稿）, implementation.md v1, test-report.md（TD-F036-1 / TE-F036-2 / §2.1）, evidence-notes.md v1}`；`docs/api/F023.md` v2 §11 + §17；`docs/database/f023-import.md` §5.9；`docs/features/F032/artifacts/real-validate/REDACTION.md`；F032–F035 审查报告对应条目；`AGENTS.md`、`docs/project/{handoff,git-workflow,change-control,project-state}.md`、`.pi/skills/{data-integrity,frontend-ui}/SKILL.md`。

## 1. 范围符合性（CHG-014 §1 第 1–11 项）

| # | 条目 | 结论 | 复核点 |
| --- | --- | --- | --- |
| 1 | F034-RV-01 载体切回 file 清空旧文件 | 落地 | 两 form 补丁 3 键含 `file:null`；复用既有 `changeInput` 复位；`importTargetKey→null` ⇒ 门控不可用；smoke 期望同步 + 浏览器证据（375×812：input 空、两结果区空态、按钮 disabled） |
| 2 | F035-FU-01 `field="hostname"` | 落地 | `_app_error_field` 词表 +1 条；`interface.py`/`service.py`/`resource_import.py` 零 diff；真实 PG 双会话 + `pg_blocking_pids` 交错 + 显式 READ COMMITTED；`row==2`（单行）/`row∈{2,3}`（多行组，TD-I-4）；`reason` 只断子串（TD-I-3） |
| 3 | F032-RV-03 MAC 脱敏 | 落地 | 5 个被跟踪文件 / 20 处 → 0；仅 `mac_address` 后 4 组替换；CSV 4×26+BOM、`.log` 159/352 行不变；`REDACTION.md` 含规则/矩阵/`git add -f` 事实/边界 |
| 4 | F033-RV-03 窄屏焦点环 | 落地 | `outline 3px + offset -3px`、删除 `box-shadow` 覆盖；无新断点、44px 零 diff；375/1023 几何 JSON + 截图 + 视口/日期；负向对照（offset `+3px` 时环越界）证明判据有区分力 |
| 5 | F033-RV-01 smoke 基线 | 落地 | 实测 340（Reviewer 复跑一致）；322/328 仅作历史值 |
| 6 | F034-RV-03 placeholder | 落地 | 两常量同主体、首行「片段」、示例 3 列（TD-I-7 ≤4）、无 26 列 `join(",")`、无 `...` |
| 7 | F034-RV-04 / F032-RV-06 | 落地 | 入库集合与忽略集合并列（`git ls-files` / `check-ignore -v`）；口令明文全仓 0 命中（含 `backend/tests`） |
| 8 | F034-RV-06 记忆化 | 落地 | `useMemo` 依赖恰为四要素；指纹算法/位数零变更；F034 等价性 60 例 PASS |
| 9 | F034-RV-09 测试洁净 | 落地 | `artifact_dir()` / `write_artifact()` 落 `/tmp`（可 `CSM_TEST_ARTIFACT_DIR` 覆盖），不可写即 `skip` 且不回退仓库；跑后 `git status` clean |
| 10 | F032-RV-02 T79 CLI 用例 | 落地 | 真子进程 + 临时 cwd；六参数写列、其余留空、缺 `--resource-type` 非零退出且零文件副作用；计数 83 → 84 |
| 11 | 11a–11e 记载 | 落地 | `collect_host_info.py` 两处 docstring；11c/11d/11e 见 `architecture` §7 R-10/11/12 与 `evidence-notes` §2，均可 grep |

**未越界**：错误码 / `IMPORT_INVALID_FILE.details.reason` 枚举 / 响应字段 / 26 列模板与列序 / 上限 / 权限与 §23.2 / 端点 / Schema 全部零 diff（`alembic heads` = 0015）；零新依赖；**F034-RV-02 未被宣称关闭**（全部 F036 文档核过）。

## 2. 分层结论

产品与领域 PASS（无新对象/关系/状态/唯一性/生命周期规则；需求 revision 14 不变）；数据完整性 PASS（`_lock_resource` 的 `FOR UPDATE` + `include_deleted` + `deleted_at` 读侧校验、`_attribute_integrity`、`_acquire_locks` 零 diff，未弱化；并发软删仍整批 422 + 四表计数与窗口内 `CREATE` Audit 不变）；架构与依赖 PASS（唯一后端改动为错误标签词表 +1；`database=false` 成立；`frontend/src/api/**`、26 列常量零 diff）；数据与 Migration `NOT_REQUIRED` 确认；API 与实现 PASS（F023 §11 澄清 + §17「不升版」行，正文仍 v2；`reason` 自由文本、`related_row=null`、1-based 行号、整批 422）；标识符 PASS（`hostname` 为冻结模板组键列）；前端 PASS + 1 LOW；测试 PASS；安全与范围 PASS（MAC 全目录免 ignore 0 命中、口令全仓 0 命中、判据 B 用不入库临时 pattern）；变更与批准 PASS + 1 LOW 字段。

## 3. 缺陷

| ID | Severity | Layer | Location | 证据 | 期望 vs 实际 | 影响 | Owner | 必须修复 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| RV-F036-01 | LOW | Docs/Evidence | `test-report.md` 版本表 / TE-1；`f036-ui-browser-check.json.head` | 报告 pin `8b8f594`；交付 HEAD `224291b`（+423 行测试文件） | 报告须记录最终候选 HEAD | 证据链与审批对象不一致（Reviewer 已在 `224291b` 复跑 10 passed，delta 仅测试） | 协调器/Tester | 否（FU-01） |
| RV-F036-02 | LOW | Test | `smoke-client.mjs:8919-8952`；`tester-u-layer.log:V1.2a` | 改前 2 键补丁在 `textState`(file:null) 前置下门控断言仍通过；真实序列改前 `importTargetKey` NON-NULL | 新门控断言应能证伪未修实现；实际仅 `deepEqual` 有区分力 | 门控后果缺独立证伪覆盖 | Frontend/Tester | 否（FU-02） |
| RV-F036-03 | LOW | Docs/Evidence | `test-report.md` TE-2 证据列 / TE-7 尾句 | `git ls-files docs/features/F036/` = 10 项；`.log` 命中 `.gitignore:124` 未入库 | 入库描述应与 `ls-files` 一致 | Merge 后引用路径失效（JSON/PNG 已入库 + Reviewer 复跑） | 协调器 | 否（FU-03，本报告 §11 已补正） |
| RV-F036-04 | LOW | Test | `test_f036_attribution.py:279` | `assert …, producers` 中 `producers` 未定义 | 失败应给差异；实际 `NameError` | 守卫失败丢诊断 | Backend | 否（FU-04） |
| RV-F036-05 | LOW | 文档 | `test-report.md` TD-1/TD-9、`architecture.md` §12 | 实际 53 条，汇总写 47（TE-3 已自纠） | 单一正确计数 | 覆盖规模误判 | Tester/Architect | 否（FU-05） |
| RV-F036-06 | LOW | 计划字段 | `project-plan.yaml` F036 | `status: IN_PROGRESS` + `current_stage: REVIEW`；`start_commit` 短 SHA；`head_commit: null`；`repair_rounds: 0` | project-state.md 要求 IN_REVIEW；Git Workflow §2 要求完整 SHA | 字段语义不符 | 协调器 | 否（FU-06，本 Feature 状态提交已按 IN_REVIEW→DONE 链执行） |
| RV-F036-07 | NOTE | 报告形式 | `test-report.md` 三处 Git 声明 | 一份交接三份声明（F035-RV-03 同类） | 一份交接一份声明 | 核验易漏 | Tester/协调器 | 否（FU-07） |
| RV-F036-08 | NOTE | 契约表述 | F023 §11 首句 + `_app_error_field` | 守卫仅覆盖 `_field_error("resource",…)`；未知点路径原样返回 | 一般性断言仅部分可守卫 | 未来非模板列字段会泄漏 | Architect/Backend | 否（FU-08） |
| RV-F036-09 | NOTE | 设计措辞 | `test-report.md` §1 `V2.4`（TD-I-11） | 实测：不存在 ⇒ 新建 `created==1`；跨 Cluster ⇒ `field="host"` | §1 期望文字与 §8.1 矛盾（实现正确） | 误读验收口径 | Architect | 否（FU-09） |
| RV-F036-10 | NOTE | 掩码副作用 | F031/F034 报告被掩码检索词 | `grep -rl *** = 0` 等命令不再可执行 | TD-I-2 授权范围内；可复核性下降 | 需注记 | 协调器 | 否（FU-10） |
| RV-F036-11 | NOTE | 既有残留 | `docs/features/F034/test-report.md` §2.10 | 修正落在 F036 报告（DR-F036-09 / §8） | 只看 F034 仍误判 | 低 | 协调器 | 否（FU-11） |

**分级统计**：BLOCKER 0 / HIGH 0 / MEDIUM 0 / LOW 6 / NOTE 5。**必须修复：0。**

## 4. 独立验证（Reviewer 实际执行）

真实 PG 16.15（`127.0.0.1:55432/csm_test`，`DATABASE_URL` unset，DB-D10 双守卫）：

| 命令 | 结果 |
| --- | --- |
| `pytest tests/integration/test_f036_attribution.py tests/integration/test_f036_tester_independent.py -q` | **10 passed** |
| 负向对照（`/tmp` 插件还原改前 `_app_error_field`） | **2 failed**，报文 `field='resource'` ⇒ 缺陷真实、V2 用例有区分力 |
| `pytest test_f023_resource_interface_ip_import.py test_f034_csv_text_carrier{,_scope}.py -q` | **59 passed**（28+31） |
| `pytest test_f035_append_interface_ip_import.py test_f035_tester_acceptance.py test_f035_append_scope.py -q` | **38 passed**（20+16+2） |
| 11 文件零回归集 `-q` | **186 passed**（未复现 `OBS-F036-TE-03` flake） |
| `python3 -m pytest scripts/test_collect_host_info.py -q` | **84 passed** |
| `npm run smoke:client` | **340 passed, 0 failed** |
| 跑测试后 `git status --porcelain -uall` | clean；产物落 `/tmp/csm-test-artifacts/f034/` |
| `python3 -m alembic heads` | `0015_user_cluster_authorizations (head)` |
| MAC 免 ignore 扫描 / CSV 结构 / `.log` 行数 / `REDACTION.md` | 0 命中；4×26+BOM；159/352 不变；无完整 MAC |
| 口令明文扫描（不入库临时 pattern） | `docs/` / `backend/` / `frontend/` / `scripts/` / `git grep` 全 0 |
| Node 负向对照（改前 2 键 `importCarrierPatch`） | 真实序列改前 `importTargetKey` NON-NULL；修复后 `file===null` / `key===null` / `text` 保留 |
| `python3 scripts/validate_project_state.py` | `PROJECT STATE VALID` |

## 5. 旧缺陷复核

`DEF-F036-TE-01`（A3 MAC）→ **CLOSED 成立**；`DEF-F036-TE-02`（A7 口令）→ **CLOSED 成立**（判据 A 仅 `csm:***`；判据 B 四目录 + `git grep` 全 0；`.env.test` 未跟踪）；`OBS-F036-TE-03`（`test_ip_addresses::test_concurrent_gateway_change_and_allocation` flaky）→ Reviewer 单轮全量 186 passed 未复现，与 F036 diff 无交集，**另立跟进**；`TD-I-11` → 降为 NOTE（RV-F036-09）。

## 6. Follow-ups（非阻塞）

| ID | 内容 | Owner | 时点 |
| --- | --- | --- | --- |
| FU-01 | 候选 HEAD 以 `224291b` 记录（本报告 §11 已固定） | 协调器 | 已处理 |
| FU-02 | 用含真实 `File` 的 file→text→file 前置复算门控断言 | Frontend/Tester | 下个触及导入面板的 Feature |
| FU-03 | `.log` 证据入库口径：本报告 §11 已声明为「本地未入库（`.gitignore:124`），入库证据为 JSON/PNG 与报告」 | 协调器 | 已处理 |
| FU-04 | 修 `assert …, producers` 未定义变量 | Backend | 下次触碰该测试文件 |
| FU-05 | 统一用例计数为 53 | Tester/Architect | 下轮文档维护 |
| FU-06 | 计划置 `IN_REVIEW` + 完整 SHA + `repair_rounds` | 协调器 | 已处理（§12 状态链） |
| FU-07 | 合并为一份 Git 声明 | Tester/协调器 | 下轮交接 |
| FU-08 | 契约守卫扩到全部 `_field_error` 产生点 | Architect/Backend | 下一次契约修订 |
| FU-09 | 修订 §1 `V2.4` 措辞 | Architect | 下一次设计修订 |
| FU-10 | 掩码检索词补注记 | 协调器 | 下次文档维护 |
| FU-11 | 独立维护时修正 F034 §2.10 logs 描述 | 协调器 | 下次 F034 文档修订 |
| FU-12 | 既有 flaky 用例 `test_ip_addresses::test_concurrent_gateway_change_and_allocation` 单独跟进（非 F036 回归） | Tester | 下个相关 Feature |

## 7. 未审查项

REPEATABLE READ 分支（`NOT TESTED`）；5000 行纯追加性能（`NOT TESTED`，R-12 触发条件已登记）；需求 §31–33 整体验收（不在本 Feature 范围）；`useMemo` 运行时收益（非语义保证）；B 层链路为 `vite preview` + 真实后端代理（报告已披露，未在 `csmtest` 真实栈重做）；多浏览器/多视口；F001–F031 无关既有代码；F032–F035 报告仅核对本次字面掩码/脱敏行。

## 8. 结论

**APPROVED WITH FOLLOW-UP**。CHG-014 §1 第 1–11 项全部落地且未越界（错误码 / `reason` 枚举 / 响应字段 / 模板 / 上限 / 权限 / 端点 / Schema 零变更，`alembic head` = 0015，零新依赖）；F034-RV-01 与 F035-FU-01 的修复经负向对照证明真实生效且未弱化并发软删检测；回归计数全部达到或超过基线（smoke 340、F035 20/18、F023 28、零回归 186、F034 31、CLI 84、F036 归因 10）；F034-RV-02 未被宣称关闭。**无 BLOCKER / HIGH / 必须修复 MEDIUM，无未决产品问题**。批准仅对候选 HEAD `224291b` 与 Base `refs/heads/v3.3` = `a2e9194` 有效。

## 11. Merge 记录与证据入库口径（协调器补记，2026-10-26）

- Merge：`git switch v3.3` → `git merge --no-ff feature/F036-review-followup-closeout`，Merge SHA **`a50f0ea`**（父 `a2e9194` + `5481c92`）；无冲突、无额外实现改动。
- `git.head_commit` 记录为批准 HEAD `224291b`（RV-F036-06 / FU-01 关闭）。
- **证据入库口径（RV-F036-03 / FU-03）**：`docs/features/F036/artifacts/` 下 `.log` 文件命中 `.gitignore:124 *.log`，故**本地生成、不入库**；入库证据为 JSON（`f036-live-*.json` / `f036-browser-*.json` / 静态扫描 JSON）、截图 PNG 与 `test-report.md` / 本报告。引用 `.log` 的复跑命令均在报告中可重建，不作为可追溯入库路径。

- **批准 HEAD 与合并 HEAD 的差异（透明记录）**：批准候选 HEAD 为 `224291b`；merge 前另有一个**纯文档**提交 `5481c92`（本审查报告 + 计划状态置 `IN_REVIEW`），`git diff --name-only 224291b..5481c92` 仅含 `docs/`（4 文件，零实现/零测试/零契约变更），已核验 `grep -v '^docs/' | wc -l` = 0。因此集成树与批准候选在实现层面完全一致。
