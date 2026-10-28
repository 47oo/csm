# CHG-014 F032–F035 Review 跟进项收敛（新增 F036）

- **状态**：**APPROVED（用户 2026-10-26「A B 全部按照建议做」）**；候选计划 revision 22，需求 revision 保持 14。
- **来源**：`docs/features/F032/review-report.md` §6、`docs/features/F033/review-report.md` §6、`docs/features/F034/review-report.md` §6、`docs/features/F035/review-report.md` §8。这些非阻塞项此前只存在于各 Feature 审查报告，计划中没有承载对象（先例：F029 / F030 / F031 为同类 ENABLER Feature）。
- **性质**：**ENABLER**，不新增业务规则、不改变任何已确认产品口径；需求文档 revision 不变。所有条目均为对已交付行为的**缺陷修正、忠实度修正或证据/文档修正**。

## 1. 范围（F036 必须交付）

| # | 条目 | 类型 | 说明 |
| --- | --- | --- | --- |
| 1 | **F034-RV-01** | 前端（MEDIUM，真实误操作风险） | 载体从文本切回「文件」时 `values.file` 保留但原生 input 已空 ⇒ 可能在看不到文件的情况下提交切换前的旧文件。改为载体切换时清空 `file` 并重置结果态（与文本载体同口径），补浏览器/机制断言 |
| 2 | **F035-FU-01** | 后端（LOW，契约归因） | 追加路径 `prepare_interface._lock_resource` 失败时 `RowError.field="resource"` 不符「`field` = 模板列名」；映射为模板列名 `hostname`（组键列），补竞态用例 |
| 3 | **F032-RV-03** | 证据安全（LOW） | 已入库 `docs/features/F032/artifacts/real-validate/*.csv`、`setup.log`、`cli-smoke.log` 含真实主机 MAC；脱敏后回写，保留证据可用性并标注脱敏 |
| 4 | **F033-RV-03** | 前端（LOW） | ≤1023px 导航项 `focus-visible` outline 被 `overflow-x:auto` 裁切；修正焦点态可见性 |
| 5 | **F033-RV-01** | 证据精度 | smoke 基线引用陈旧计数 → 以当前实测计数为基线 |
| 6 | **F034-RV-03** | 前端文案 | 文本载体 placeholder 像完整表头（照抄必 422）→ 改为明确「片段示例」 |
| 7 | **F034-RV-04** / **F032-RV-06** | 证据精度 / 安全 | 修正 test-report 中 logs 入库范围描述；测试库口令统一掩码 |
| 8 | **F034-RV-06** | 前端性能（NOTE） | 大文本每次渲染双哈希 → 加 `useMemo` 记忆化，行为不变 |
| 9 | **F034-RV-09** | 测试洁净 | `test_f034_csv_text_carrier.py` 写回被跟踪 artifacts → 改写到临时目录 |
| 10 | **F032-RV-02** | 测试补强 | 补 T79 CLI 级自动化用例（当前仅人工冒烟） |
| 11 | **F032-RV-05** / **F032-RV-07** / **F034-RV-08** / **F035-FU-05** / **F035-FU-08** | 记载 | 以文档/注释明确既有取舍与触发条件，不改行为 |

## 2. 明确不做

- 不修改任何已确认业务规则、错误码、`reason` 枚举、响应字段、模板、上限、权限、端点、Schema / Migration。
- 不重构服务层或前端架构；不做与上述条目无关的清理。
- 不新增 npm / Python 依赖。

## 3. 升级给用户的一项（不在 F036 内）

**F034-RV-02**（T114 等价性口径的追认留痕）属于**用户对需求正文的确认动作**，不是 Feature 可自行完成的交付物；已在 `requirements-v3.md` §35.1 revision 13 记录为 Architect 裁定 + 协调器编辑性澄清。F036 不宣称已关闭该项；需用户以一句话追认（或要求改需求）后由需求 revision 15 落稿。

## 4. 契约影响

`docs/api/F023.md` §11 需补一条归因澄清（`field` 恒为模板列名，含并发软删竞态的组键列 `hostname`）；正文版本 v2 不变，以增补/澄清行签署。`docs/api/F014.md` 无影响。

## 5. 计划影响

新增 Feature **F036**（ENABLER / P2 / depends_on F032, F033, F034, F035），`layers={database:false, backend:true, frontend:true}`、`api_required=true`；plan revision 22；`project.status=ACCEPTED`、`acceptance=PENDING`（历史证据与 F034/F035 跨功能验收证据保留）。
