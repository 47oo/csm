# F036 F032–F035 Review 跟进项收敛 — PRODUCT 阶段报告

- **状态**：READY FOR ARCHITECT
- **版本**：v1（2026-10-26）；ENABLER / P2 / M27；分支 `feature/F036-review-followup-closeout`；plan revision 22；**需求 revision 14（不变）**
- **Basis**：`docs/project/proposals/CHG-014-review-followup-closeout.md`（APPROVED，用户 2026-10-26「A B 全部按照建议做」）；缺陷原文 `docs/features/F03{2,3,4,5}/review-report.md`；plan revision 22（`layers={database:false,backend:true,frontend:true}`、`api_required=true`、`blocking_decisions: []`）；requirements revision 14 §28 / §31（T67、T71、T79、T100、T107–T126）；先例 `docs/features/F031/product.md`；`.pi/skills/frontend-ui/SKILL.md`。

## 1. 性质：收敛型 ENABLER

不新增业务规则，不改变已确认口径（对象 / 关系 / 状态 / 唯一性 / 生命周期 / 权限项 / 错误码 / `reason` 枚举 / 响应字段 / 26 列模板 / 字节与行数上限 / 端点 / Schema）；需求 revision 保持 14。全部条目均为对 F032–F035 已交付内容的缺陷修正、忠实度修正或证据/文档修正。

两项会让用户可感知行为变化，但都是把实现拉回**已被批准的口径**，不是新规则：F034-RV-01（界面状态须与提交值一致，属 §24.5 T116 陈旧结果防护的忠实度）、F035-FU-01（行错误 `field` 恒为模板列名，属 §31 T67/T119/T120 与 F023 v2 §11 的既有口径）。与已确认条款冲突时以条款为准。

## 2. 逐条映射

| # | ID | 问题 | 期望行为（可验收表述） | 来源 |
| --- | --- | --- | --- | --- |
| 1 | F034-RV-01 | 从「文本」切回「文件」后界面无文件名回显，但提交仍带切换前的旧文件 → 可能导入自己看不到的文件 | 切回「文件」即清空已选文件并重置预校验/写入结果态（与切到文本同口径）；重新选择前「确认导入」不可用；界面状态与提交值一致；有自动化断言 | F034 §4 F034-RV-01（MEDIUM）、§6 FU-1；§24.5 T116；§28 |
| 2 | F035-FU-01 | 宿主在锁定前被并发软删时行错误 `field` 显示 `resource`，无法对应模板列 | 该类失败返回 `field="hostname"`（组键列）；行号 1-based、整批 422 回滚、零写入不变；F023 v2 §11 有归因澄清且签核；补真实双会话竞态用例 | F035 §6 F035-RV-01（LOW）、§8 FU-01；§31 T67/T119/T120；CHG-014 §4 |
| 3 | F032-RV-03 | 已入库证据 CSV 与日志含真实主机 MAC | `docs/features/F032/artifacts/` 中 `real-validate/*.csv`、`setup.log`、`cli-smoke.log` 脱敏后回写并标注；仍可作为证据引用（结构/行号/结果可比对） | F032 §4 F032-RV-03（LOW） |
| 4 | F033-RV-03 | ≤1023px 导航项键盘聚焦时焦点框被横向滚动容器裁切 | 受控窄屏（375 / 1023）下 `focus-visible` 三边完整可见，激活项 `current` 标识仍可辨识；注释与实现一致；有窄屏证据 | F033 §4 F033-RV-03、§5 D-F033-01；§28 |
| 5 | F033-RV-01 | smoke 基线引用 322（陈旧计数） | 基线引用等于当前实测计数（339 起），记录实测命令与日期 | F033 §4 F033-RV-01；F035 §5 |
| 6 | F034-RV-03 | 文本载体 placeholder 形似完整表头，照抄必 422 | 两面板占位文案明确为「片段示例」，不再形似完整表头 | F034 §4 F034-RV-03；§24.5 T112 |
| 7 | F034-RV-04 / F032-RV-06 | 报告把已入库 logs 描述为被忽略；报告含明文测试库口令 | 入库范围描述与实际一致；报告与证据中口令统一掩码，仓库 grep 命中 0 | F034 §4 F034-RV-04；F032 §4 F032-RV-06 |
| 8 | F034-RV-06 | 大文本每次渲染做全量双哈希 | 哈希/字节计数记忆化；同一输入的哈希、字节数与判定结果逐字节一致 | F034 §4 F034-RV-06（NOTE） |
| 9 | F034-RV-09 | 跑测试会写回被跟踪的 artifacts 文件 | 测试输出写入临时目录；跑 F034 相关测试后已跟踪文件 `git status` clean | F034 §4 F034-RV-09 |
| 10 | F032-RV-02 | T79 仅有 CLI 人工冒烟，无自动化断言 | 新增自动化用例：`--cluster/--resource-type/--role/--status/--host/--network` 写入对应列、其余留空、缺 `--resource-type` 非零退出；通过并进入回归计数 | F032 §4 F032-RV-02；§31 T79 |
| 11a | F032-RV-05 | 任意 argparse 错误都追加三组枚举允许值 | 注释/文档明确该行为是 DR-1007「统一追加」的既有取舍与触发条件（不改提示逻辑） | F032 §4 F032-RV-05；§24.4 T100 |
| 11b | F032-RV-07 | `collect(resource_type: str \| None)` 允许 None、`_push()` 保留防御检查 | 注释/文档说明仅为单测与防御边界，CLI 仍必填 `--resource-type` | F032 §4 F032-RV-07；§24.4 T101/T105 |
| 11c | F034-RV-08 | 表头级 `details.unknown_columns` 会回显被当作表头那一行原文 | 文档注明为 F014/F023 既有 schema、两载体逐字段一致、收紧须另立变更 | F034 §4 F034-RV-08；§24.5 T112/T115 |
| 11d | F035-FU-05 | 前端证据未记视口 | 登记视口与「改追加提示区布局须补窄屏证据」的触发条件 | F035 §6 F035-RV-06、§8 FU-05 |
| 11e | F035-FU-08 | 5000 行纯追加性能 `NOT TESTED` 且无阈值 | 登记未测项与触发条件：性能回归时按 `docs/database/f023-import.md` §5.7 复核，不得放松 V11.5 锁环判据 | F035 §6 F035-RV-08、§8 FU-08 |

## 3. 边界与排除

- **不得触达**：错误码、`reason` 枚举、响应字段、26 列模板与列序、字节/行数上限、权限矩阵与 §23.2 集群范围、端点与查询参数、Schema/Migration/索引/约束、审计口径、整批原子性。
- 不重构服务层或前端架构；不新增 npm / Python 依赖；不做条目外清理；不改写 F001–F035 既有结论。
- **F034-RV-02（T114 等价性口径追认）不在本 Feature 范围**：属用户对需求正文的确认动作，F036 不实现、不宣称已关闭；需用户一句话追认后由需求 revision 15 落稿（CHG-014 §3）。
- 不承接且不宣称关闭：F032-RV-01/RV-04、F033-RV-02/04/05/06/07/08、F034-RV-05/07、F035-RV-02/03/04/07/09/10、F035-FU-02/03/04/06/07。
- 契约面仅允许 `docs/api/F023.md` §11 归因澄清行（正文 v2 不变）；`docs/api/F014.md` 无影响。

## 4. 验收线索（供 TEST DESIGN 承接）

| ID | 判据 |
| --- | --- |
| A1 | text→file 切换后：提交值文件为空（或文件名显式回显）、结果态重置、「确认导入」disabled；DOM/组件断言取得 |
| A2 | 双会话竞态（宿主在锁定前软删）→ 422、`error_count≥1`、该行 `field=="hostname"`、行号 1-based、零写入残留；F023 v2 §11 澄清行已签核 |
| A3 | `grep -rnE "([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}" docs/features/F032/artifacts/` 命中 0（或仅掩码格式）；文件仍在且含脱敏标注 |
| A4 | 受控窄屏视口（375 / 1023）聚焦导航项：焦点框三边可见（几何指标或截图 + 记录视口） |
| A5 | 文档 smoke 基线计数 == 本次实测计数，且 ≥ 339 |
| A6 | placeholder 断言：不含完整 26 列表头、含「片段」语义标识 |
| A7 | 口令 grep 命中 0；入库范围表与 `git ls-files` / `git check-ignore` 逐项一致 |
| A8 | 记忆化后同一输入哈希/字节数与改前相等；F034 等价性 60 例仍全部 deep-equal |
| A9 | 跑 F034 相关测试后已跟踪文件 `git status --porcelain` 为空 |
| A10 | 新 T79 CLI 用例 PASS，覆盖六个参数写列 + 其余留空 + 缺 `--resource-type` 非零退出 |
| A11 | 记载项可 grep 到条目 ID 与触发条件文字 |
| A12 | **回归计数不减少**：`smoke:client` ≥339、F035 `20`、F035 Tester 验收+范围 `18`、F023 `28`、零回归集 `186`、F034 集成 `31`、`scripts/test_collect_host_info.py` `83`；无新增 FAIL |
| A13 | 守卫：`alembic head` 仍 `0015`；`backend/alembic`、`frontend/src/api/**`、模板与上限常量零 diff；`typecheck`/`build` exit 0；新增依赖 0 |
| A14 | 权限与范围口径不变：零 diff + 既有 T115/T124 用例 PASS 佐证 |

## 5. 未执行项

未运行任何测试、构建或 Git 变更命令。技术方案（载体切换清空时机、竞态用例构造、记忆化点、脱敏格式）由 ARCHITECTURE / CONTRACT Gate 决定。

## 6. Questions

- **Blocking：None**（CHG-014 已批准，plan revision 22 `blocking_decisions: []`）。
- **Non-blocking**：① 掩码/脱敏格式是否上升为长期证据规范，属工程实践，PM 不裁定。② F034-RV-02 待用户追认，期间需求保持 revision 14。

**Status：READY FOR ARCHITECT**
