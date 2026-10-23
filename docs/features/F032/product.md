# F032 采集脚本类型必填、帮助信息与按类型生成 — PRODUCT 阶段报告

- **状态**：READY FOR ARCHITECT
- **版本**：v1
- **上游依据**：
  - `docs/product/requirements-v3.md` **revision 12**：§24.4（CONFIRMED，全节）、§24.2 / §24.3（经 §24.4 修订的 `--resource-type` 必填口径）、§24.1、§31 验收表 T100–T106 及修订后的 T73 / T79 / T84、§35.1 revision 12 确认记录。
  - 用户裁定（CONFIRMED，记录于 `docs/project/project-plan.yaml` `decisions_required`）：CHG011-BQ01 组合 **D**（同一 26 列模板与同一导入端点，按类型只填适用列并生成不同默认 CSV）、CHG011-BQ02 组合 **3**（`--help` 分区说明「模板必填」与「`--push` 必填」并列出枚举值与引用语义）、CHG011-BQ03 组合 **A**（非法枚举本地 fail-fast）、CHG011-BQ04（`--resource-type` 必填，替代可缺省旧口径）。
  - 计划与授权：`docs/project/project-plan.yaml` plan_revision 18，`project.approval`（用户 2026-10-23「批准 plan revision 18 并实施 F032」），F032 `depends_on` F023 / F024 / F025 均 DONE；分支 `feature/F032-collector-help-type-import`。
  - 既有实现基线：`docs/features/F024/product.md`（T73–T78）、`docs/features/F025/`（T79–T84）、`docs/api/F023.md` §6（26 列冻结列集）、`docs/api/F014.md`（BM 14 / VM 10 列模板，均不改）。
- **说明**：本报告只整理已确认规则，不新增业务规则；技术方案、测试设计与文件级改动由后续角色在已批准边界内决定。

---

## 1. 目标与范围

F032 让采集脚本在**不改变模板与导入行为**的前提下，明确告诉使用者「必须提供什么」，并保证按资源类型生成可直接预校验的导入文件。

范围内（CONFIRMED）：

1. **`--resource-type` 全局必填**：取值仅 `BARE_METAL` / `VIRTUAL_MACHINE`。任一调用形式（无参、仅 `--print`、仅 `-o`、仅 `--push`）缺失该参数时，脚本在**本地失败**：非零退出、stderr 说明缺失必填并列出允许值及 `--help` 提示；不采集、不创建或覆盖输出文件、stdout 无 CSV 行、零网络请求。
2. **取值严格匹配**：不做大小写折叠、不做短名映射、不静默回退为留空或默认值。非法 `--resource-type`（小写、短名、空串、未知值）及其它枚举参数（`--role`、`--status`）非法值同样本地 fail-fast，错误信息列出允许值，且无文件 / CSV / 网络副作用。
3. **`--help` 分两区说明，与真实行为一致**：
   - **模板必填**（与逐行导入校验一致）：`cluster`、`hostname`、`resource_type`、`name`、`ip`；`VIRTUAL_MACHINE` 行另需 `host`。脚本无法自动获得、须经参数或人工补全的模板必填项为 `cluster`（及 VM 的 `host`）。
   - **`--push` 必填**：`--api-url`、API Key（环境变量 `CSM_API_KEY` 或 `--api-key`）、`--cluster`；`--resource-type` 因全局必填自动满足。须明确「脚本必填 ≠ 模板必填」：未给 `--cluster` 仍可生成离线 CSV，仅 `--push` 被拒绝。
   - **枚举参数可填值**：`--resource-type` = `BARE_METAL` / `VIRTUAL_MACHINE`；`--role` = `COMPUTE` / `LOGIN` / `MANAGEMENT` / `STORAGE` / `SERVICE` / `GPU` / `OTHER`；`--status` = `IDLE` / `ALLOC` / `DOWN` / `UNKNOWN`（与 §24.1 / F023 §6 一致）。
   - **引用型参数语义**：`--cluster` 为 Cluster `code`（大小写不敏感）或 UUID，须存在且未软删；`--host` 为同 cluster 内已存在、未软删的 `BARE_METAL` Host 的 hostname 或 UUID；`--network` 为同 cluster Network `name` 或 CIDR，留空时由 `ip` 的 `/mask` 解析。
4. **按类型生成不同文件，但共用同一模板与端点**：仍使用 F023 §6 冻结的**同一 26 列宽模板（同一表头、同一列序）**与同一导入端点 `/api/v1/imports/resource-interfaces-ips`（预校验 `/validate`）。BM 填硬件列并保持 `host` / `vcpu` / `disk_gb` / `hypervisor` 为空；VM 填 `host` / `vcpu` / `disk_gb` / `hypervisor` 并保持硬件列为空（沿用 F023 §6.1 逐行适用性）。一次运行只产出一类行，不生成 BM/VM 混合文件。
5. **默认文件名按类型区分**：未给 `-o/--output` 时默认 `csm_host_info_bare_metal.csv` / `csm_host_info_virtual_machine.csv`；显式 `-o/--output` **优先**；`--print` 只输出 stdout、**不写文件**（即使同时给出 `-o`）；`--no-header` 语义不变。
6. **保持不变（无回归边界）**：`cluster`、`role`、`status`、`host`、`network` 未提供时仍留空；`--push` 仍为两步流程（先预校验、经 `--yes` 再写入），API Key 不落盘、不写日志或输出；默认离线只读，无 `--push` 时零网络请求；列名与列序与 F023 §6 26 列逐字一致；F014（BM 14 / VM 10 列模板）与 F023（26 列模板、端点、校验、上限、错误口径）的需求、契约与实现行为**零改动**。

## 2. 明确不做

- 不新增或修改平台 API：不新增端点、字段、枚举、错误码、上限或权限；不新建对外契约。
- 不修改 F014 / F023 的模板、列集、列序、端点、校验口径与既有导入行为；不改写 F014 / F023 / F024 / F025 的历史交付证据。
- 不修改数据库 Schema、Migration、索引或约束；不改平台 Service Layer、路由、模型与权限；无前端 UI / 组件 / 交互改动。
- 不做平台自动采集 / Agent / 常驻 / 定时 Facts 回传，不改变 §3 / §34 排除项；不创建或导入 Network / IP Pool / Cluster / Host；不触发自动 IP 分配。
- 不从主机推断 `resource_type`、`role`、`status`、`host` 等业务值；不为缺失参数写占位值或默认值。
- 不做大小写折叠、短名 / 别名映射、交互式补问或省略必填参数的「兼容模式」。
- 不做 BM/VM 混合输出文件，不在一期内提供新的列或新的 `.xlsx` 要求。

## 3. 领域与数据影响

| 对象 | 关系 | 作用域 | 生命周期 | 约束依据及版本 | 未决问题/影响 |
| --- | --- | --- | --- | --- | --- |
| 采集脚本 CLI（离线工具） | 仅生成导入文件 / 经 `--push` 调用 F023 端点 | 单次运行，参数作用域为本次运行 | 每次运行独立；失败不产生文件或平台变更 | §24.4（revision 12 CONFIRMED） | 无 |
| `resource_type` 取值 | 决定该次运行的一类行与类型专属列 | 已确认枚举 `BARE_METAL` / `VIRTUAL_MACHINE` | 由必填参数提供，不由主机推断 | §24.3 / §24.4、F023 §6 | 无 |
| 引用对象 Cluster / Host / Network | 脚本仅**引用**：须已存在且未软删；脚本不创建 | 同 cluster 作用域（`--host` / `--network`） | 不由脚本改变 | §24.1 / §24.4、§9 | 无 |

结论：不新增实体、关系、状态、唯一性规则、字段或生命周期；脚本仍是导入模板的**生产者**，导入语义与所有权仍归 F023 / F014。

## 4. 验收标准（映射 T100–T106，并承接修订后的 T73 / T79 / T84）

| # | 用户可观察行为 | 映射 |
| --- | --- | --- |
| A1 | `--help` 输出：`--resource-type` 标注必填并列出 `BARE_METAL` / `VIRTUAL_MACHINE`；`--role` / `--status` 列出全部允许值；`--cluster` / `--host` / `--network` 说明引用对象与「须已存在」语义；按「模板必填」与「`--push` 必填」分区说明，且与真实运行行为一致 | T100 |
| A2 | 缺少 `--resource-type` 的任一调用形式（无参、仅 `--print`、仅 `-o`、仅 `--push`）：非零退出；stderr 含缺失必填说明与允许值；不创建也不覆盖输出文件；stdout 无 CSV 行；零网络请求 | T101 |
| A3 | `--resource-type BARE_METAL`：`resource_type` 列为 `BARE_METAL`；硬件列可填；`host` / `vcpu` / `disk_gb` / `hypervisor` 恒为空；表头为 F023 §6 冻结 26 列且同序 | T102 |
| A4 | `--resource-type VIRTUAL_MACHINE`：`resource_type` 列为 `VIRTUAL_MACHINE`；硬件列恒为空；`--host` 未提供时 `host` 留空且不推断，提供时写入；`vcpu` / `disk_gb` / `hypervisor` 可填 | T103 |
| A5 | 默认文件名按类型区分，BM 与 VM 两次运行产出文件不同且互不覆盖；`-o/--output` 显式路径优先；`--print` 时仍不写文件（即使给了 `-o`） | T104 |
| A6 | 非法 `--resource-type`（小写、短名、空串、未知值）及其他枚举参数非法值：本地 fail-fast，非零退出、不写文件、stdout 无 CSV、零网络请求，错误信息列出允许值；不回退为留空/默认值，不做大小写折叠或短名映射 | T105 |
| A7 | 契约零 diff 与无回归：`docs/api/F023.md` §6 列集/端点/校验/上限/错误口径零改动，`docs/api/F014.md` 未改动；`--print` / `--no-header` / `-o` / `--push`（预校验→`--yes`→写入、Key 不落盘不漏出）语义不变；T75、T77、T82、T83 无回归；无 `--push` 时零网络请求 | T106 |
| A8 | 代表性 Linux 主机运行成功并产出文件；表头列名与列序与冻结模板逐字一致；无法采集的业务字段为空（`resource_type` 由必填参数提供，不写占位值） | **T73（修订后）** |
| A9 | `--cluster` / `--resource-type` / `--role` / `--status` / `--host` / `--network` 写入对应列；除 `--resource-type` 外未提供字段仍留空；参数补全后无需手工编辑文件即可通过预校验（除仍无法获得的字段） | **T79（修订后）** |
| A10 | 默认（未启用 `--push`）完全离线、不发起任何网络请求；除 §24.4 明示的 `--resource-type` 必填与按类型默认文件名外，F024 既有文件输出、表头与 T73–T78 行为无回归 | **T84（修订后）** |
| A11 | 生成的 BM / VM 真实文件经 F023 导入预校验时，只出现仍待人工补全字段的行级错误，无表头 / 列 / 格式类错误 | T77 承接（F032 范围内） |

> 以上为可验证行为定义；本阶段未执行任何验收，执行证据由 Test Report 提供。

## 5. Blocking Questions

**None。** §24.4 与 T100–T106 已确认；CHG011-BQ01–BQ04 全部 CONFIRMED（组合 D / 3 / A 及 `--resource-type` 必填），revision 12 已显式覆盖 §24.2 / §24.3 中 `--resource-type` 可缺省的旧口径，T73 / T79 / T84 已按新口径修订，无残留未决点。

## 6. 受影响 Feature 与承接

| Feature | 关系 | 处理 |
| --- | --- | --- |
| F023 | 被消费的冻结契约（26 列模板、端点、校验、上限、错误口径） | 零改动；F032 不新建 Contract |
| F014 | 被消费的冻结模板（BM 14 / VM 10 列） | 零改动 |
| F024 | 脚本与 README / field-mapping 的历史交付 | 行为按 T84 无回归；用法示例更新标注 revision 12，不改写历史证据 |
| F025 | `--push` 两步流程与 API Key 口径（T79–T84） | 语义不变，按 T106 无回归 |
| F032 | 本次承接 §24.4 与 T100–T106 | 本 Feature 交付 |

后续：交由 Architect 在已确认边界内设计；`project.acceptance=COMPLETE` 由协调器在 F032 Test Report 与 F001–F031 历史证据一并核验后置位，不以单一 Feature PASS 代替。
