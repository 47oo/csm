# CHG-011 采集脚本：类型必填、帮助信息与按类型生成

- **状态**：READY FOR PLAN APPROVAL（需求内容已由用户确认；计划 revision 18 尚未批准）
- **来源**：用户 2026-10-23 提出「可执行脚本还需要更新，--help 针对于必填项，如果是枚举类型，应告知可以填写的类型，针对于不同的类型，应该生成不同的导入方式」，随后明确「`--resource-type` 是必填项」，并确认推荐组合 **D / 3 / A**。
- **影响对象**：`docs/product/requirements-v3.md` revision 11 → 12；新 Feature **F032**；F024 / F025 已 DONE 交付行为由 F032 承接，不回写历史证据。
- **不改动**：F014（BM 14 / VM 10 列模板）、F023（26 列统一模板、端点、校验、上限、错误口径）、数据库 Schema、平台 API、前端、权限、审计。

---

## 1. 用户确认的裁定

| ID | 裁定 | 状态 |
| --- | --- | --- |
| D | 仍使用 F023 同一 26 列模板与同一导入端点；按 BARE_METAL / VIRTUAL_MACHINE 只填适用列，生成不同默认 CSV 文件 | CONFIRMED（用户确认 D） |
| 3 | `--help` 分区说明「模板必填」与「`--push` 必填」，并列出枚举值与引用型参数语义 | CONFIRMED（用户确认 3） |
| A | 非法枚举本地 fail-fast：非零退出、不写文件、不输出 CSV、不联网、不做大小写折叠或短名映射 | CONFIRMED（用户确认 A） |
| 必填 | `--resource-type` 为全局必填参数，仅允许 `BARE_METAL` / `VIRTUAL_MACHINE` | CONFIRMED（用户明确裁定） |

---

## 2. 正文差异

### 2.1 `docs/product/requirements-v3.md`

- §24.2「输出」：补充默认文件名按 `--resource-type` 区分。
- §24.2「人工补全」：从默认留空字段中移除 `resource_type`，改由 §24.4 必填参数提供。
- §24.3「参数补全」：`--resource-type` 改为必填；除它之外的字段未提供仍留空；说明 §24.4 进一步修订。
- §24.3「打印」：补充默认文件名按类型区分；仍为同一 26 列、同序。
- §24.3「验收」：追加 T100–T106。
- 新增 §24.4「采集脚本类型必填、帮助信息与按类型生成（revision 12）」：
  - `--resource-type` 必填；缺失/非法时本地失败且无副作用。
  - `--help` 必须说明模板必填、`--push` 必填、枚举值、引用型参数语义。
  - 同一 F023 26 列模板与同一端点；BM/VM 只填适用列；一次运行只产出一类行。
  - 默认文件名 `csm_host_info_bare_metal.csv` / `csm_host_info_virtual_machine.csv`；`-o` 优先；`--print` 不写文件。
  - 非法 `--role` / `--status` 等枚举同样本地失败。
  - 保持 `--push`、`--no-header`、离线默认、API Key 不落盘等既有语义。
  - 明确不修改 F014 / F023。
- §31：修订 T73 / T79 / T84，新增 T100–T106。
- §35.1：追加 revision 12 确认记录。
- §36：需求基线更新为 revision 12。

### 2.2 领域索引

- `docs/product/domain-model.md`：导入/采集脚本索引追加 §24.4。

---

## 3. 新 Feature 候选：F032

**标题**：采集脚本类型必填、帮助信息与按类型生成

**范围**：

- `scripts/collect_host_info.py`：
  - `--resource-type` 改为 argparse `required=True`，`choices=["BARE_METAL","VIRTUAL_MACHINE"]`。
  - `--role` / `--status` 增加与 F023 §6 一致的 `choices`，非法值 argparse 失败。
  - `--help` 分区展示模板必填、`--push` 必填、枚举值、引用型参数语义。
  - 未给 `-o` 时默认文件名按类型推导；`-o` 优先；`--print` 仍只输出 stdout 不写文件。
  - 保持同一 26 列、同一 F023 端点、同一两步推送流程。
- `scripts/test_collect_host_info.py`：新增帮助/必填/枚举/默认文件名/失败无副作用/无回归用例；修订既有 3 处 `main([...])` 调用补 `--resource-type`。
- 新 Feature 文档：`docs/features/F032/product.md`、`architecture.md`、`implementation.md`、`test-report.md`、`review-report.md`（实施阶段建立）。
- 更新 `.gitignore`：增加 `csm_host_info_bare_metal.csv` / `csm_host_info_virtual_machine.csv`，保留旧 `csm_host_info.csv` 条目。
- 更新 `docs/features/F024/README.md` 与 `field-mapping.md` 的用法示例，标注 revision 12 的必填/默认文件名变化；不改写 F024 历史证据。

**验收**：T100–T106，并显式承接 revision 12 修订后的 T73 / T79 / T84，回归 T75 / T77 / T78 / T82 / T83。

**整体验收承接**：不新增独立验收 Feature。F032 test-report 须包含跨功能证据：以生成的 BM/VM CSV 调用 F023 `/api/v1/imports/resource-interfaces-ips/validate`（环境受限时如实记录替代证据），并核对 F014/F023 契约零 diff；协调器将其与 F001–F031 历史证据一并核验后置 `project.acceptance=COMPLETE`，不以单一 Feature PASS 代替。

**分层**：

```text
layers.database = false
layers.backend = false
layers.frontend = false
api_required = false
contract = NOT_REQUIRED（消费 F023 §6，不新建 Contract）
```

**依赖**：F024、F025、F023（均 DONE）。

---

## 4. 兼容性与风险

| 项 | 影响 | 处理 |
| --- | --- | --- |
| 既有无 `--resource-type` 调用 | 直接失败（退出码 2） | 属用户确认的破坏性变更；F032 文档与 usage 示例必须写清 |
| 默认文件名变化 | 旧 `csm_host_info.csv` 不再默认生成 | `-o csm_host_info.csv` 可复现旧名；`.gitignore` 增加类型化条目并保留旧条目 |
| 既有 `--role` / `--status` 任意字符串 | 非法值本地失败，不再写盘 | 与服务端枚举受理集合一致；属 A 的确认范围 |
| 帮助文本与 F023 漂移 | 用户看到错误枚举/必填说明 | 内嵌常量 + 测试逐字守卫；不运行时抓取模板端点 |
| 新默认文件污染工作区 | 未跟踪的 `csm_host_info_bare_metal.csv` / `..._virtual_machine.csv` | F032 scope 内更新 `.gitignore`，保留旧条目 |
| F024 文档与新行为冲突 | README/field-mapping 仍写 `resource_type` 可留空 | F032 scope 内更新用法示例并标注 revision 12；不改历史证据 |
| F014 / F023 回归 | 不得发生 | 契约零 diff；不新增平台 API；T78 / T106 守卫 |

---

## 5. 计划变更

- 候选 plan revision：**18**。
- `project.requirements.revision`：**12**。
- 新增 F032（DRAFT，待批准后 READY）。
- `pending_changes`：`CHG-011`，`affects: [F024, F025, F032]`。
- `decisions_required`：
  - `CHG011-BQ01`（D，CONFIRMED）
  - `CHG011-BQ02`（help 分区，CONFIRMED）
  - `CHG011-BQ03`（非法枚举 fail-fast，CONFIRMED）
  - `CHG011-BQ04`（`--resource-type` 必填，CONFIRMED）
- F024 / F025 保持 DONE，不改写历史证据；BQ9 的旧 basis 由 revision 12 替代，保留历史并追加替代说明。

---

## 6. 待批准

本提案与候选计划 revision 18 需用户批准后，才可：

1. 将需求 revision 12 合入 `v3.3`；
2. 将 F032 纳入批准范围并把项目从 DONE 重新进入 ACCEPTED；
3. 启动 F032 实施。

批准前不修改脚本、不运行实现、不合并到 `v3.3`。
