# F035 向既有 Resource 追加 Interface/IP 导入 — REVIEW 阶段报告

- **状态**：**APPROVED WITH FOLLOW-UP**（v1，2026-10-26；候选 HEAD `d3b5bd0`，Base `refs/heads/v3.3 = 76d8410`）
- **批准边界**：仅对候选 HEAD `d3b5bd06d03bf31efdf818664faa94499429e62f` 与 Base `76d8410ef02c06e10c4c268cf08a4221a269ef62` 有效；Base / HEAD / F023 v2 / requirements revision 14 / plan_revision 21 任一变化须重新 Review。Merge / DONE 由协调器按 `git-workflow.md` §5 判定。

## 1. 依据与批准来源

| 对象 | 版本 / 状态 |
| --- | --- |
| `docs/product/requirements-v3.md` | **revision 14**：§24.6、修订后的 §24 / §24.1 / §24.5、§31 T117–T126 与 T67/T71、§32、§35.1 revision 14（用户 2026-10-26「按推荐执行」，落稿于 `76d8410`） |
| 裁定组合 | CHG013-BQ01=B / BQ02=B / BQ03=A / BQ04=A / BQ05=A / BQ06=C1 / BQ07=A / BQ08=A（CONFIRMED） |
| 计划 | plan_revision 21、`project.approval` 含 F035、`execution.authorization.feature_ids=[F035]`、`pending_changes: []` |
| 契约 | `docs/api/F023.md` **v2**（Architect 签核 2026-10-26，替代 v1 五处条款 + 增补节衔接段）；`docs/api/F014.md` 仅事实补注（正文 v1、行为零变更） |
| 设计 / 数据 / 测试 | `docs/features/F035/architecture.md` §12（READY FOR IMPLEMENTATION，含 §12.4 裁定）；`docs/database/f023-import.md` §5（NOT_REQUIRED，A1–A5）；`docs/features/F035/test-report.md` §1/§2 |

## 2. 审查范围

分支 `feature/F035-append-interface-ip`；start_commit = Base = `76d8410`；候选 HEAD `d3b5bd0`；merge-base `76d8410`；完整范围 `76d8410..d3b5bd0` = 5 提交 / 23 文件 / +6048 −490（`5a4f4c1` PRODUCT、`9e80a7c` ARCHITECTURE+F023 v2+Database、`65827ea` TEST_DESIGN+CONTRACT、`187ddf3` 实现+前端+测试、`d3b5bd0` Tester 独立用例+H/B 证据+Test Report）；工作区 clean、无未跟踪交付物。

## 3. 分层结论

产品与领域（T117–T126 + T67/T71）符合；架构与依赖符合（DR-F035-01…14 落地、零新端点）；数据与 Migration 符合（零 Schema 漂移、alembic head 仍 `0015`、15 个迁移文件、models/alembic 零 diff、三条部分唯一索引兜底）；API 与实现符合（端点/字段/响应 4 键/错误码/`reason` 枚举/26 列模板/行号/上限/权限/原子性零变更，纯追加 201 且 `created=0`）；T118 零 UPDATE 有物理层证据；锁序单语句并集 + `ORDER BY id` + SAVEPOINT 外 + `resources → networks`；一致性比较口径 = canonical `resource_cells` 键集 + 服务端归一化标量 + 留空不比较不置空 + 模板列名归因 + `related_row=null` + 去重；错误归因删除 hostname 业务冲突但保留 DB 兜底（V11.4 / `test_pg05a` 双证）；前端文案覆盖 §7.3 十项、零 wire 变更；测试充分；安全与范围符合；变更与批准符合。

## 4. 关键核对

- **T118**：`write_import` 追加组跳过 `stage_resource`、不计数、不对既有 ORM 实例赋值；`_load_existing_snapshots` 只读投影后转 frozen dataclass（identity map 无 dirty ⇒ 无 autoflush UPDATE）；只写子对象 INSERT + 各一条 CREATE Audit；I 层实测全列快照 + `xmin::text` + `version` + `updated_at` 相等、`resource` UPDATE Audit = 0、Activity 无 UPDATE。
- **锁序/并发**：`_acquire_locks` 单条 `SELECT … IN (…) ORDER BY id FOR UPDATE`（VM Host ∪ 追加宿主）、SAVEPOINT 外；V11 五场景真实双会话通过（含 V11.5 反向集合锁环回归），无 `40P01`。
- **F023 用例 3 处更新**：`test_pg06`（改为「行 4 无错误」并保留其余断言）、`test_pg08`（`field` → `role` + 新增 `related_row is None` 与 hostname 不报 + 保留 `version==1`/无 UPDATE Audit）、`test_pg11`（改 `name` 冲突 + 新增零残留断言）；用例数 28→28，`test_pg05a/b/c` 原样保留。

## 5. Reviewer 独立验证

真实 PG 16.15（`csm_test` @ `127.0.0.1:55432`）复现：F035 `20 passed`、Tester 验收+范围 `18 passed`、F023 `28 passed`（含 5000 行 PERF）、零回归集 `186 passed`、`scripts/test_collect_host_info.py` `83 passed`；前端 `typecheck` exit 0、`build` 通过、`smoke:client` **339 passed 0 failed**；`validate_project_state.py` = `PROJECT STATE VALID`；容器内 service 文件 md5 与工作区一致、前端产物 `assets/index-TYGZNgB0.js` 与容器产物同名同哈希（PR-2 佐证）；零 diff 守卫空输出；alembic 15 个文件/head `0015`。

未重跑：H 层 29 checks、B 层 29 checks（重跑会写入真实栈并改写已提交产物，改以 JSON 逐项 + 容器 md5/产物哈希 + I 层等价判据三角核对）；5000 行纯追加性能（`NOT TESTED`）；多浏览器/多视口。

## 6. 缺陷

| ID | Severity | Layer | Location | 期望 vs 实际 | 影响 | Owner | 必须修复 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| F035-RV-01 | LOW | I（Backend） | `resource_interface_ip_import.py`（`_load_existing_snapshots` 的 `deleted_at IS NULL` 过滤 + `_check_existing_consistency` 的 `snapshot is None: continue`；`prepare_interface._lock_resource` 的 `_field_error("resource", …)`） | 极窄并发软删竞态下 `RowError.field="resource"` 而非模板列名；数据行为正确（整批 422 回滚、零写入） | 仅错误标签不合契约，无数据风险 | Backend | 否（FU-01） |
| F035-RV-02 | NOTE | 协调器 | `project-plan.yaml` F035 `git.head_commit: null` | Merge Gate 前须补已批准 HEAD（已在最终状态提交补记 `d3b5bd0`） | 记录完整性 | 协调器 | 否 |
| F035-RV-03 | LOW | 文档（Tester） | `test-report.md` 末尾两段 Git 声明；TE-1 记 `187ddf3` | 一份交接一份 Git 声明、记录最终候选 HEAD（`187ddf3..d3b5bd0` 实现代码零 diff，已在 `d3b5bd0` 复现） | 格式与可追溯性 | Tester/协调器 | 否（FU-02） |
| F035-RV-04 | LOW | 文档（Architect） | `architecture.md` 头部 `READY FOR DESIGN` vs §12 `READY FOR IMPLEMENTATION` | 头部状态应指向 §12 定稿 | 阅读易误判 | Architect | 否（FU-03） |
| F035-RV-05 | NOTE | 契约表述 | F023 v2 头部「不新增 `reason` 取值」vs 新增自由文本 `RowError.reason` | 不违反（`RowError.reason` 为自由 `str`，枚举仅约束 `IMPORT_INVALID_FILE.details.reason`）；建议加一句澄清 | 表述 | Architect | 否（FU-04） |
| F035-RV-06 | NOTE | 前端证据 | `f035-browser-check.json` 未记视口（B 层 1440×1000） | 纯文案改动，响应式风险低；后续改布局须补窄屏证据 | 证据完备性 | Frontend/Tester | 否（FU-05） |
| F035-RV-07 | NOTE | 证据可达性 | `artifacts/*.log`、`logs/**` 被 `.gitignore` 忽略 | 计划 evidence 引用的 `test-report.md#2-test-execution` 已入库，JSON 与脚本已入库；与 F034 先例一致 | — | 协调器/Tester | 否 |
| F035-RV-08 | NOTE | 性能 | 5000 行纯追加批 | `NOT TESTED`，契约无数值阈值 | — | Tester/Backend | 否 |
| F035-RV-09 | NOTE | U（Backend） | `_build_groups` 用裸 `assert len(group_hosts)==1` | 不变量由缓存键保证、实际不可达；`-O` 下移除断言行不变 | — | Backend | 否 |
| F035-RV-10 | NOTE | S（测试强度） | `test_td3_f035_t126_7_t71_zero_diff_guards` 子串扫描 | 真实保证来自 V2 `xmin`/Audit 断言 + Reviewer `git diff` 零 diff | — | Tester | 否 |

**分级统计**：BLOCKER 0 / HIGH 0 / MEDIUM 0 / LOW 3 / NOTE 7。**必须修复：0。**

## 7. 旧缺陷复核

`F035-TEST-NOTE-01`（前端注释仍写 v1）仍存在但不阻塞（→FU-06）；`-02` 性能未测（=RV-08）；`-03` 真实栈残留软删对象（→FU-07）；`-04/-05` 与 §12.4 裁定一致；`TD-I-3` 已关闭（`docs/database/f023-import.md` §5）；`TD-I-6`/`TD-I-7` 与实现一致；`PR-1`/`PR-2` 已解决。

## 8. Follow-ups（非阻塞）

| ID | 内容 | Owner |
| --- | --- | --- |
| FU-01 | 追加路径 `_lock_resource` 失败的 `field` 映射为模板列名，或在契约 §11 明示该竞态归因 | Backend / Architect |
| FU-02 | Test Report 合并 Git 声明并补记候选 HEAD `d3b5bd0` | Tester / 协调器 |
| FU-03 | 修正 `architecture.md` 头部状态指向 §12 | Architect |
| FU-04 | F023 v2 加一句「`RowError.reason` 为自由文本」澄清 | Architect |
| FU-05 | 若改追加提示区布局，补窄屏浏览器证据 | Frontend / Tester |
| FU-06 | `frontend/src/api/imports.ts`、`resourceInterfaceIpImportForm.ts` 注释契约引用升为 v2 | Frontend |
| FU-07 | 决定是否物理清理真实栈 F035 自测软删对象（`f35th-*` / `f35b-*` / `F35T*` / `F35B*`） | 协调器 |
| FU-08 | 性能回归时按 `docs/database/f023-import.md` §5.7 复核 5000 行追加批（不得放松 V11.5 锁环判据） | Tester / Backend |

## 9. 未审查项

H 层与 B 层未由 Reviewer 重跑（三角核对替代）；5000 行纯追加性能未测；未做 §32 整体上线验收与全局矩阵；未做多浏览器/多视口；未审查无关既有 Feature 代码；未在 H/B 层复测 VIEWER/EDITOR（I 层已覆盖 403/401/行级范围）。

## 10. 结论

**APPROVED WITH FOLLOW-UP**。T117–T126（含 T67/T71）全部实现且证据可信；T118 零 UPDATE 有物理层证据；锁序与并发符合 §12.3；一致性比较口径符合 BQ02/BQ07；未发现静默新增或放宽业务规则；错误码/`reason` 枚举/响应字段/模板/上限/权限/端点/Schema 零变更；F014 与 F023 新建路径零回归。无 BLOCKER / HIGH / 必须修复 MEDIUM。

## 11. Merge 记录（协调器补记）

- Merge：`git switch v3.3` → `git merge --no-ff feature/F035-append-interface-ip`，Merge SHA **`8feebc565e75fc0575ceaeb769a6c525f62c94e0`**，父提交 `76d8410`（批准 Base）与 `d3b5bd0`（批准 HEAD），无冲突、无额外实现改动。
- `git.head_commit` 已补记为批准 HEAD `d3b5bd0`（RV-02 关闭）。
