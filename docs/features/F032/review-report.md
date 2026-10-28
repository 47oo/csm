# F032 采集脚本类型必填、帮助信息与按类型生成 — REVIEW 报告

- **状态**：**APPROVED WITH FOLLOW-UP**
- **版本**：v1
- **Reviewer**：Reviewer（独立审查），2026-10-23
- **候选基线**：Branch `feature/F032-collector-help-type-import`；Base `refs/heads/v3.3` = `89a5d4ff61f9df35f8f4393887701e7015bc26d8`；候选 HEAD `b474f534f82749bdcd3e6dd610e4fa84a896f251`；merge-base = `89a5d4f`；完整范围 `89a5d4f..b474f53`（7 commits / 30 files / +2491 −78）。
- **状态提交**：`3ba5b03` 仅修改 `docs/project/project-plan.yaml`（IN_PROGRESS→IN_REVIEW、head_commit、evidence.test），无实现/测试改动。
- **批准边界**：仅对候选 HEAD `b474f53` 与 Base `89a5d4f` 有效；Merge / DONE / 整体验收由协调器按 `git-workflow.md` §5 判定。

## 1. Basis

- `docs/product/requirements-v3.md` revision 12 §24.4、修订后 §24.2/§24.3、§31 T100–T106 与 T73/T79/T84、§35.1。
- `docs/features/F032/product.md` v1；`architecture.md` v2（DR-1001–DR-1016、ON-1、§9 READY FOR IMPLEMENTATION / Contract NOT_REQUIRED）。
- `docs/database/f032-collector-cli.md`（NOT_REQUIRED）。
- `docs/api/F023.md` v1 §5/§6、`docs/api/F014.md` v1（消费，零改动）。
- `docs/features/F032/test-report.md` TD-2 + §12 TEST（READY FOR REVIEW）；`artifacts/`；`implementation.md`。
- `docs/project/project-plan.yaml` plan_revision 18；`execution.authorization` F032；`pending_changes: []`。

## 2. Scope Reviewed

| 项 | 值 |
| --- | --- |
| Feature Branch | `feature/F032-collector-help-type-import` |
| Base | `refs/heads/v3.3` = `89a5d4f` |
| 候选 HEAD | `b474f53` |
| 当前状态提交 | `3ba5b03`（仅 plan 元数据） |
| merge-base | `89a5d4f` |
| 完整范围 | `89a5d4f..b474f53` |
| 工作区 | 审查时派生视图未同步（RV-01），无 staged/untracked；已由协调器在 `2fca0a5` 关闭 |

## 3. 分层结论

| 层 | 结论 |
| --- | --- |
| 产品/领域 | **通过**：`--resource-type` 必填、严格枚举、BM/VM 适用列、默认文件名、`-o` 优先、`--print` 不落盘；未新增对象/关系/状态/唯一性/生命周期。 |
| 架构/依赖 | **通过**：DR-1001–DR-1016 与 ON-1 落位；`layers.database/backend/frontend=false`、`api_required=false`、Contract NOT_REQUIRED；无新增依赖。 |
| 数据/Migration | **通过（NOT_REQUIRED）**：无 Schema/Migration/索引/约束；`backend`/`frontend` 零 diff。 |
| API/Contract | **通过**：`docs/api/**` 零 diff；26 列、`IMPORT_PATH`、multipart filename `csm_host_info.csv` 未变。 |
| 实现正确性 | **通过**：`main()` 顺序 `build_parser → parse_args → _validate_args → collect → write/stdout → _push`，参数错误零副作用；`--print` 不调用 `write_csv`；帮助与 choices 同源。 |
| 可维护性 | **通过**：常量集中、错误提示统一、帮助离线生成。 |
| 前端 | **NOT_REQUIRED**：`frontend/` 零 diff。 |
| 测试充分性 | **通过**：独立复跑 83/83、112/112；既有断言未放宽；tempdir/chdir 隔离；5 个变异全部被捕获。 |
| 安全/范围 | **通过**：无 API Key 明文进入证据；`--push` 写入腿零 diff；改动面仅脚本/测试/F024/F025 用法与 errata/计划。 |
| 变更/批准 | **通过**：plan_revision 18 覆盖 F032；需求 revision 12；`validate_project_state.py --feature F032` 通过。 |
| 历史交付安全 | **通过**：F024/F025 test/review 零 diff；implementation 仅追加 errata；README/field-mapping 为计划授权用法更新。 |

### 真实 `/validate` 证据

`artifacts/real-validate/` 自洽可追溯：测试栈 `csmtest` / `:18080` health 200；ADMIN 登录；夹具 Cluster `F032CHK`、3×Network、BM Host `f032host`；文件 sha256；原始 JSON：BM `200/error_count=0`，VM 含 host `200/0`，VM 无 host `200/error_count=3` 且全部 `field:"host"`；`--push` 仅预校验、未写入；只读副作用核对 Resource=1（仅夹具）/IPAddress=0；清理日志记录软删/吊销。未以 Mock 冒充端到端。

## 4. Findings

| ID | Severity | Layer | 说明 | Owner | 必须修复 |
| --- | --- | --- | --- | --- | --- |
| **F032-RV-01** | MEDIUM | Plan/派生视图 | `3ba5b03` 未同步 `backlog.md`/`milestones.md`，HEAD tree 视图 stale；工作区非 clean | 协调器 | 否（Feature 内容）；Merge 前必须关闭 |
| **F032-RV-02** | LOW | 测试充分性 | TD-2 承诺的 CLI 级 `test_cli_all_manual_params_written`（T79）未实现；T79 的 CLI→列路径有 S19 人工冒烟证据，非自动化断言 | Tester/Backend 后续 | 否 |
| **F032-RV-03** | LOW | 安全/仓库内容 | `artifacts/real-validate/*.csv`、`setup.log`、`cli-smoke.log` 含真实主机 MAC；建议后续脱敏 | 协调器/Tester 后续 | 否 |
| **F032-RV-04** | NOTE | 口径记录 | `-o ""` 回落默认名、自由文本空白=未提供、`--print --push` 组合仅记录于 implementation/test-report，未写入 architecture DR/产品条款 | Architect（如需固化） | 否 |
| **F032-RV-05** | NOTE | CLI 体验 | `build_error_hint()` 对任意 argparse 错误都追加三组枚举允许值，对无关注解有噪声；DR-1007 要求统一追加 | Backend 后续 | 否 |
| **F032-RV-06** | NOTE | 安全 | `test-report.md §12.1` 明文写测试库口令；同类明文在历史报告存在；建议后续统一掩码 | 协调器 | 否 |
| **F032-RV-07** | NOTE | 类型/注释精度 | `collect(resource_type: str | None, …)` 仍允许 None（供 build_rows 单测）；`_push()` 保留防御性检查 | Backend 后续 | 否 |

**BLOCKER 0 / HIGH 0 / MEDIUM 1（RV-01，仅派生视图）/ LOW 2 / NOTE 5；Feature 内容必须修复 0。**

## 5. 旧缺陷复核

| 项 | 结论 |
| --- | --- |
| TD-D01（BM + `--host`） | **CLOSED**：DR-1015 落地；真实 CLI rc=2、stdout 空、无文件。 |
| TD-D02（空串口径） | **CLOSED**：DR-1016；`InvalidEnumTests` + `FreeTextEmptyStringTests`。 |
| TD-D03（`--print` + `--push`） | **CLOSED as ON-1**：无判据，`main()` 顺序未改。 |
| TD-D04（真实 `/validate` 环境） | **CLOSED**：真实栈执行并保留原始 JSON、夹具 UUID、清理日志；只预校验。 |
| TD-D05（`.gitignore`） | **CLOSED**：三项齐全，保留旧条目。 |
| F032-T-OB1（既有 `scripts/csm_host_info.csv`） | 仍存在且非本次产生；非阻塞。 |
| F032-T-OB2（`--yes` 真实写入腿） | 接受为设计禁止；`_push()` 零 diff + 既有 mock 用例。 |

## 6. Follow-ups

1. **协调器（Merge 前已完成）**：RV-01 由 `2fca0a5 chore(F032): sync derived views for review` 关闭；`render_project_views.py` 只读检查 `PROJECT VIEWS VALID`，工作区 clean。
2. **协调器（Merge Gate）**：以 `refs/heads/v3.3`（`89a5d4f`）为 Base、批准 HEAD `b474f53`；确认未落在 `refs/tags/v3.3`（`79e1bec`）；成功后写真实 Merge SHA。
3. **协调器**：合并后核验 `project.acceptance=COMPLETE` 证据，不以 F032 局部 PASS 代替整体验收。
4. **Tester/Backend（后续 Feature）**：补 T79 CLI 级自动化用例（RV-02）。
5. **Tester/协调器（后续）**：artifacts MAC 脱敏（RV-03）、测试口令掩码（RV-06）、清理既有忽略产物（OB-1）。

## 7. 未审查项

| 项 | 原因 |
| --- | --- |
| 真实 `/validate` 重跑 | 不重启 `csmtest`；以已提交原始 JSON、夹具 UUID、只读副作用核对与清理日志交叉验证 |
| `--push --yes` 真实写入腿 | 设计禁止（architecture §9.3），接受 NOT TESTED by design；代码零 diff + mock 用例 |
| §31–§33 跨功能整体验收 / acceptance=COMPLETE | 协调器职责 |
| F014 运行期行为 | F032 零 diff，属 F014 历史证据 |
| `strace` 零网络复核 | 沿用 `cli-smoke.log`（六场景 inet=0）+ 代码顺序/用例探针 |
| 用户批准来源真实性 | 仅核对计划记录完整性（revision 18 / feature_ids / 日期 / basis） |

## 8. Coordinator Closure

- **F032-RV-01 CLOSED**：`2fca0a5` 同步 `docs/project/backlog.md`、`docs/project/milestones.md`；提交后 `render_project_views.py` 只读检查 `PROJECT VIEWS VALID`，工作区 clean。
- 其余 RV-02–RV-07 为非阻塞跟进，保留为后续 Feature/维护项，不改变本次批准内容。

## 9. 结论

**APPROVED WITH FOLLOW-UP**。核心验收、真实 F023 `/validate` 证据、契约零 diff 与测试充分性均满足；无 BLOCKER/HIGH/必须修复 MEDIUM。RV-01 已在 Merge 前关闭；Merge/DONE 由协调器按 Git Workflow 判定。
