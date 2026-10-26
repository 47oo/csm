# CHG-012 前端 CSV 文本导入载体

- **状态**：READY FOR PLAN APPROVAL（需求内容待用户裁定 BQ-1 / BQ-2；候选计划 revision 20 尚未批准）
- **来源**：用户 2026-10-26 提出「前端除了支持使用文件导入数据，还应该支持直接使用 csv 格式的文本导入资源数据」。
- **影响对象**：`docs/product/requirements-v3.md` revision 12 → 13（拟新增 §24.5、§31 T107–T116、§35.1 revision 13 行、§36 基线）；新 Feature **F034**；F014 / F023 已 DONE 交付行为由 F034 承接扩展，**不回写**其历史证据。
- **不改动**：F014（BM 14 / VM 10 列模板）与 F023（26 列模板）已冻结模板、端点路径、`format` 取值语义、`IMPORT_*` 错误码与 `RowError` 形状、上限数值（5,242,880 B / 5000 行 / 1000 预览）、`IMPORT` 权限矩阵、§23.2 集群范围语义、§22 Audit 口径、数据库 Schema / Migration、后端导入实现、技术栈与依赖。
- **角色输入**：Product Manager 需求澄清（含 BQ 建议与验收草案）、Architect 轻量全局评估（`ARCHITECTURE ASSESSMENT COMPLETE`）、Project Manager 能力拆分与候选计划。裁定权归用户；专业设计签核在 F034 CONTRACT 阶段完成。

---

## 1. BQ-1 载体覆盖范围与入口关系

**问题**：文本载体覆盖哪些导入入口，与文件上传是并列还是替换？

**背景**：前端现有两个并列导入入口，均在 ResourcesPage：①「批量导入…」= F014 资源导入（BM 14 列 / VM 10 列，服务端按表头精确匹配模板）；②「资源+网卡+IP 批量导入…」= F023 26 列宽模板。用户原话「导入资源数据」未指明覆盖哪个入口，也未明示文件上传是否保留。

| 选项 | 内容 |
| --- | --- |
| **A（推荐）** | F014 与 F023 两个入口都新增「粘贴 CSV 文本」载体，文件上传保留并列，不替换、不削弱 |
| B | 仅 F014 资源导入新增文本载体 |
| C | 仅 F023 资源+网卡+IP 导入新增文本载体 |
| D | 用文本载体替换文件上传 |

**推荐 A 的依据**：①用户原文字面为增补语义（「除了…还应该支持」），D 与之相悖；②若只覆盖一个入口，同一页面会出现「一个导入入口能粘贴、另一个不能」的可感知不一致；③两个入口的解析 / 表头匹配 / 上限 / 错误形态本就共享同一实现口径，同时扩展的验收可复用。

**待裁定者**：用户（范围决策，`change-control.md` §1）。

---

## 2. BQ-2 文本解析口径严格度

**问题**：文本载体是否与文件导入使用完全相同的 CSV 解析口径（表头、分隔符、嗅探、补齐）？

**背景**：文件导入要求第 1 行是与冻结模板**逐字逐序一致**的表头，缺失 / 缺列 / 多列 / 列序不符一律 422 `IMPORT_INVALID_FILE`；F014 还依赖表头判定 BM/VM 模板。文本粘贴场景下存在两种放宽诉求：只粘贴数据行由前端补表头；以及从 Excel 复制得到的制表符分隔文本（TSV）。两者都会让同一份数据「文件模式失败、文本模式成功」。

| 选项 | 内容 |
| --- | --- |
| **A（推荐）** | 严格同口径：文本必须自带与冻结模板逐字逐序一致的表头；仅逗号分隔；不做分隔符嗅探、不自动补表头、不做列名映射或大小写折叠 |
| B | 允许省略表头，由前端按当前入口自动补冻结表头；其余同 A |
| C | 在 A 基础上自动识别分隔符（逗号 / 制表符） |
| D | B + C 同时放宽 |

**推荐 A 的依据**：①§24 已确认「固定模板与逐列说明」与「错误至少含行号、字段、原因」，表头 / 列序不符已是冻结的 422 口径；②B/C 会引入「同一数据两种载体结论不同」，使 T27 / T72 的一致性无法验证；③B 需要新增「文本模式如何判定目标模板」的业务规则，C 需要新增嗅探失败报错口径与行号影响，均属新业务规则，不能由实现自行决定。

**若用户确有「从 Excel 直接复制粘贴」诉求**：建议另立独立需求（TSV / 分隔符嗅探），不在本次隐式放宽。

**待裁定者**：用户（业务规则决策，`change-control.md` §1）。

---

## 3. 需求正文差异（PROPOSED，待裁定后落稿）

### 3.1 `docs/product/requirements-v3.md`

拟新增 **§24.5 前端 CSV 文本导入载体（revision 13）**，位于 §24.4 之后：

* 输入载体：既有导入面板在「选择文件」之外提供「粘贴 / 输入 CSV 文本」载体，与文件上传并列（依 BQ-1 裁定后的入口集合），不替换、不改变文件导入既有行为。
* 载体边界：文本载体仅 CSV（UTF-8，兼容 BOM）；不提供 `.xlsx` 文本载体。文本与文件是同一导入数据集的两种载体，模板列集 / 列序（§24、§24.1 与 D03 冻结值）不变。
* 口径一致（沿用既有 CONFIRMED 规则，不另立规则）：同一两步流程（预校验 → 用户确认 → 写入时再次校验）、同一 Service Layer 校验、同一错误口径（1-based 行号、表头为第 1 行、`field` 取模板列名、`related_row`）、同一 `IMPORT` 权限与 §23.2 集群范围行级校验、同一 §22 审计口径（每对象 CREATE，回滚无残留）、同一整批原子性。
* 表头与解析：文本必须包含与冻结模板逐字逐序一致的表头；缺失 / 缺列 / 未定义列 / 列序不符按既有 `IMPORT_INVALID_FILE` reason 拒绝；不静默忽略、不按名重排、不自动补表头、不做分隔符嗅探（依 BQ-2 裁定）。
* 上限：数据行数上限与文件导入一致；字节上限按文本 UTF-8 编码后的字节数适用同一 `import_max_file_bytes`；具体数值维持已签核值，不在本节重设。
* 不持久化：粘贴文本内容不落盘、不入库，不写入 Audit / 日志 / 错误响应。
* 明确不做：不用文本更新或覆盖现存对象（§24 仅新增）；不导入或创建 Network / IP Pool / Cluster / Host / Service / Endpoint；不新增权限项或角色；不改变任何已冻结模板、端点语义与错误码。

其他同步点：

| 位置 | 变更 | 性质 |
| --- | --- | --- |
| §24 首段 | 追加交叉引用「导入的输入载体（文件 / 前端粘贴文本）见 §24.5」 | 引用，不改规则 |
| §31 | 新增 T107–T116（下表） | 新增验收 |
| §31 T28 | 「文件 / 行数上限」→「文件或文本载体的字节 / 行数上限」 | 措辞澄清，限值不变 |
| §32 | 上线验收表述覆盖「文件或文本载体」 | 措辞澄清 |
| §35.1 | 追加 revision 13 / 2026-10-26 行：记录用户需求、BQ-1 / BQ-2 裁定结果、新增 §24.5 与 T107–T116，并说明不修改 F014 / F023 模板、端点语义、上限、权限与审计 | 确认记录 |
| §36 | 基线 revision 12 → 13，并修正第 3 行仍写「revision 11」的既有编辑缺陷 | 状态记录 + 编辑修正 |
| `docs/product/domain-model.md` | §24 索引追加 §24.5，依据 revision 更新 | 索引同步 |

拟新增验收（PROPOSED，编号接续 §31 现有最大编号 T106）：

| ID | 可验证行为 |
| --- | --- |
| T107 | 并列入口与文件零回归：两个导入入口同时提供「文件」与「CSV 文本」载体；文件模式既有行为不变，两模式互不替换 |
| T108 | 同一两步流程与同一模板：粘贴合法 CSV 文本 → 预校验 `total_rows` / `importable_rows` / `error_count` 正确；仅 0 错误时「确认导入」可用；写入时服务端重新校验同一内容；行号口径与文件一致 |
| T109 | 行错误口径一致：非法枚举 / 整数 / 长度、文件内重复、现存冲突、集群范围外等返回同形状行错误（`row` / `field` / `reason` / `related_row`），不 fail-fast |
| T110 | 空文本 / 纯空白不发请求并本地提示；仅表头无数据行 → 422 `IMPORT_INVALID_FILE{empty_file}`；两者均无写入、无 Audit 残留 |
| T111 | 上限：UTF-8 字节数 > 5,242,880 → 413 `IMPORT_FILE_TOO_LARGE`（或本地同口径拦截）；数据行数 > 5000 → 413 `IMPORT_ROW_LIMIT_EXCEEDED`；超限无部分导入 |
| T112 | 非法表头：缺列 / 多余未定义列 / 缺表头 / 列序不符 → 422 `IMPORT_INVALID_FILE` 对应 reason，不静默忽略、不按名重排 |
| T113 | BOM 与行尾：U+FEFF 开头照常解析；CRLF / LF 混用按同一逻辑记录切分；尾随空行忽略且不移动真实数据行号 |
| T114 | 含逗号 / 引号 / 引号内换行的字段按标准 CSV 解析；引号未闭合等字段边界错误按既有文件级错误呈现，不静默修补 |
| T115 | 权限、范围与审计不变：VIEWER 403、未认证 401；含未授权集群行整批失败并返回行号 + 权限原因；Audit 与文件导入同口径；文本内容不落盘、不入库、不写入 Audit / 日志 / 错误响应 |
| T116 | 陈旧结果防护：修改文本或在文件 / 文本载体间切换后，既有预校验与写入结果全部失效，须重新预校验；同一内容重复预校验结果一致且无副作用 |

### 3.2 契约（Architect 专业签核范围）

Architect 评估结论：文本 → CSV 字节复用既有 multipart `file` + `format=csv`，**服务端零代码变更**；但 `docs/api/F014.md` 与 `docs/api/F023.md` 声明为前后端唯一 Contract，故需各加一节「**CSV 文本载体（加法引用）**」增补节 v1（照 `F027 范围语义（加法引用）` 先例），正文版本不提升。

增补节必须写：载体只决定 multipart `file` 部分的产生方式、wire 形状不变；文本按 UTF-8 编码、不添加 BOM、不做本地归一化；表头须与冻结模板逐字逐序一致、仅逗号分隔、不嗅探、不自动补表头（BQ-2 = A）；等价性声明（同一字节 → 两种载体响应完全一致）；端点、字段、错误码与 reason 集合、上限、行号与 `RowError` 形状、权限矩阵、F027 范围语义、CSRF、无副作用、不落盘不写 Audit 全部不变；签核者 / 日期 / 覆盖范围 / 确认来源（BQ-1、BQ-2 裁定记录）。

不得写：新错误码或 reason、新请求字段、新上限、行号与 `related_row` 口径变化、两步流程变化、模板列集变化，或任何未被用户裁定的业务规则（分隔符嗅探、自动补表头、xlsx 文本载体、文本留痕）。

---

## 4. 影响评估

### 4.1 受影响已 DONE Feature（行为变化由 F034 承接，历史证据保留）

| Feature | 影响点 | 影响性质 |
| --- | --- | --- |
| F014 CSV / Excel 批量导入 | `ResourceImportPanel.tsx`、`importForm.ts`、`api/imports.ts`（载体维度、文本域、指纹扩展）；`docs/api/F014.md` 增补节 | 前端 + 契约增补节 + 测试 |
| F023 资源+网卡+IP 批量导入 | `ResourceInterfaceIpImportPanel.tsx`、`resourceInterfaceIpImportForm.ts`；`docs/api/F023.md` 增补节 | 同上 |
| F021 / F029 / F030 / F033 | 同页面共存与前端呈现基线 | 仅回归确认，不改动 |

`backend/app/**`、`docs/database/**`、`deploy/**`、`scripts/collect_host_info.py` 均不改动。

### 4.2 分层与前提（Architect 定稿，供 PM 使用）

```yaml
layers.database = false     # 无 Schema / Migration / 索引 / 约束变更
layers.backend  = false     # 无后端源码变更，故也不存在「有设计无实现」的 Schema 变更
layers.frontend = true
api_required    = true      # 仅 F014 / F023 各加一节「加法引用」增补节，正文版本不提升
```

### 4.3 关键技术约束（F034 实现输入，来自 Architect 评估）

1. 文本 → `new File([text], "<固定常量名>", { type: "text/csv;charset=utf-8" })`，**必须带 filename**（缺 filename 会得到 422 `VALIDATION_ERROR{field:"file"}` 而非导入错误语义）。
2. 字节上限按 **UTF-8 编码字节数**计量（非 JS 字符数），比较用严格大于；行数上限不在前端镜像，服务端 413 权威。
3. 空 / 纯空白本地拦截且不发请求（gate 用 trim，payload 不 trim）；服务端 `empty_file` 兜底。
4. 解析口径（BOM / CRLF / 引号内换行 / 尾随空行）全部沿用服务端，前端不重实现 CSV 解析。
5. 输入指纹由「`format:name:size:lastModified`」扩展为「`carrier + format + 内容摘要(+字节长度)`」；文件分支保持原指纹不变；摘要用同步非加密哈希（不可用异步 `crypto.subtle`）。
6. 文本内容只存组件 state，禁止写入 storage / URL / console / 错误消息；不新增 npm 依赖。
7. 文本载体固定 `format=csv`，UI 上 format 只读，切换载体重置全部结果态。

### 4.4 风险

| 级别 | 风险 | 处置 |
| --- | --- | --- |
| HIGH | 指纹未扩展 → 改了文本仍可确认导入（写入与用户预期不一致） | 指纹扩展必做 + smoke 覆盖「改 1 字节必变」 |
| HIGH | 用字符数而非 UTF-8 字节计量 → 含中文文本误放行 / 误拦截 | 测试须含非 ASCII 用例 |
| MEDIUM | part 缺 filename → 用户看到无关 `VALIDATION_ERROR` | smoke 断言 filename 存在 |
| MEDIUM | `textarea` 将 CRLF 归一为 LF，视觉相同但字节不同 | 等价性测试以同一字节序列为准，并在浏览器侧实证 |
| MEDIUM | 文本载体下仍选 xlsx → 必然 422 `unsupported_format` | format 固定只读 + 切载体重置 |
| MEDIUM | 从 Excel 复制为制表符分隔，BQ-2=A 下会反复失败 | UI 明确提示「仅逗号分隔」；嗅探诉求另行立项 |
| LOW | 「不落盘」边界（Starlette >1 MiB spool 到匿名临时文件，与既有文件上传相同） | 增补节如实表述；更强保证需另立变更 |

---

## 5. 候选计划（revision 20）

文件：`docs/project/proposals/CHG-012-candidate-plan.yaml`（活动基线 `docs/project/project-plan.yaml` 未改动）。

| 字段 | 现值 | 候选 |
| --- | --- | --- |
| `project.plan_revision` | 19 | 20 |
| `project.requirements.revision` | 12 | 13（待裁定后落稿） |
| `project.status` | DONE | DRAFT（批准后由协调器写 ACCEPTED） |
| `project.approval` | plan_revision 19 / F001–F033 | null |
| `project.acceptance.status` | COMPLETE | PENDING（evidence 保留不删） |
| `features` | F001–F033 | + F034（DRAFT，P1，`M25 导入文本载体`，depends_on F014 / F023，blocking_decisions CHG012-BQ01 / BQ02） |
| `pending_changes` | `[]` | `CHG-012` → affects F014 / F023 / F034 |
| `decisions_required` | — | + CHG012-BQ01、CHG012-BQ02（OPEN，owner 用户） |

派生统计与视图已用候选计划生成到临时目录（未写入仓库）：

```bash
python3 scripts/render_project_views.py --plan docs/project/proposals/CHG-012-candidate-plan.yaml --output-dir /tmp/csm-chg012-views --write
```

候选计划当前 `planning_status`：`status=DRAFT`、`counts.DONE=33`、`counts.DRAFT=1`、`blocked_draft_features.DRAFT=[F034]`、`plan_completeness=complete`。

**已知待补项**：F034 的 `requirements` 暂未包含拟新增的 §24.5 锚点（该节随 revision 13 落稿后才存在）；落稿时补入 `docs/product/requirements-v3.md#245-前端-csv-文本导入载体revision-13`。

---

## 6. 待批准与后续

本提案与候选计划 revision 20 需用户批准后才可：

1. 落稿需求 revision 13（§24.5、T107–T116、§35.1、§36、domain-model 索引）；
2. 将 F034 纳入批准范围，项目由 DONE 重新进入 ACCEPTED，`acceptance` 置 PENDING；
3. 启动 F034 按 Feature Gate 执行（PRODUCT → ARCHITECTURE → TEST_DESIGN → CONTRACT（含两份增补节签核）→ IMPLEMENTATION → TEST → REVIEW → MERGE）。

批准前不修改前端代码、不签核增补节、不合并到 `v3.3`、不启动实施。
