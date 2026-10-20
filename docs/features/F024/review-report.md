# F024 离线主机信息采集脚本 — REVIEW 报告

- **状态**：APPROVED WITH FOLLOW-UP（Approve HEAD `67590f51e6adaf0c81266f7cea3b7898a604da0d`）
- **Base / start_commit**：`codex/v3.1` @ `2c3293fdfde3451eb98cf430ac8720d01a835241`
- **merge-base**：`2c3293f`（= start_commit）
- **候选范围**：`2c3293f..67590f5`，3 提交（`3938db1` 设计+实现、`1753c72` 修复、`67590f5` 状态检查点）；11 文件；未触及 F014/F023。
- **Reviewer**：独立审查（Tester/实现与 Review 由不同角色完成）。

## 第一轮（CHANGES REQUIRED）

| ID | Severity | 结论 | 处理 |
| --- | --- | --- | --- |
| F024-RV-01 | MEDIUM | `operstate != "up"` 一律判 `false` 并排除，unknown/dormant 且带 IPv4 的网卡被静默丢弃 | 修复：三态 `up→true/down→false/其余→空`，仅明确 `down` 排除；补回归测试 |
| F024-RV-02 | MEDIUM | 未采集 IPv4 掩码，偏离 §24.2「IPv4 地址/掩码」 | 修复：`ip` 列输出 `地址/掩码`；F023 可由 `/mask` 解析 Network |
| F024-RV-03 | MEDIUM | test-report 覆盖陈述高于实际（缺 GPU/VM/文本/sysfs/确定性用例） | 修复：补齐用例（30 tests）并修正报告 |
| F024-RV-04 | MEDIUM | 计划状态滞后（仍 IMPLEMENTATION/test PENDING） | 修复：推进 IN_REVIEW，记录 test evidence 与 `head_commit` |
| F024-RV-05 | MEDIUM | T77 端到端未执行 | 第二轮由 Reviewer 独立执行，PASS（见下） |
| F024-RV-06 | LOW | 计划 acceptance 要求 README，实际只有字段映射 | 修复：新增 `docs/features/F024/README.md` |
| F024-RV-07 | LOW | hostname 归一化用 Unicode `.lower()`，未去控制字符 | 修复：先 trim→去控制字符→仅 ASCII 大写折叠 |
| F024-RV-08 | NOTE | GPU 混合型号计数/VM 磁盘口径等边界观察 | 维持 NOTE，无行为偏差 |

## 第二轮（复审）

**结论**：APPROVED WITH FOLLOW-UP。RV-01/02/03/04/05/06/07 全部 CLOSED，无 BLOCKER/HIGH/必须修复 MEDIUM。

- 修复有效性经独立探针与 30 tests（F024）/ 59 tests（全量）验证。
- 模板列与 `docs/api/F023.md` §6 逐字逐序 26 列一致；业务字段恒空；只读、无第三方依赖、未改 F014/F023。

### T77 端到端真实集成（Reviewer 独立执行）

测试环境容器在运行（`compose.test.yaml`：db/backend/frontend/nginx，API `localhost:18080`）：

1. 原始采集输出（`--resource-type BARE_METAL`）经 `POST /api/v1/imports/resource-interfaces-ips/validate` → 2 行、4 错误，**仅** `cluster`/`resource_type` 必填业务字段，无表头/列/格式/枚举错误。
2. 仅补全 `cluster`/`resource_type` 并令 IP 落入既有 Network CIDR（`TST32092`，`10.77.159.0/24`，`network` 列留空）→ `error_count=0`、`importable_rows=2`。

**T77 = PASS**；同时验证 RV-02 掩码解析端到端可用。

### 本轮新发现（均为非阻塞）

| ID | Severity | 说明 | Owner |
| --- | --- | --- | --- |
| F024-RV2-01 | LOW | `--include-down` help 文案与三态语义不一致（仅明确 down 排除） | Backend/Tool |
| F024-RV2-02 | NOTE | 漂移守卫比对第二份硬编码常量而非解析 F023 正文（DR-803 已知取舍） | Tester/Architect |
| F024-RV2-03 | NOTE | hostname 未处理内部空白与 C1 控制符（内核 hostname 实际不含空白） | Backend/Tool |
| F024-RV2-04 | LOW | 工作区 `.agents/skills/**` 未跟踪影响 Merge Gate 清洁度 | Coordinator |
| F024-RV2-05 | NOTE | 第一轮 Review 报告未持久化 | Coordinator |
| F024-RV2-06 | LOW | test-report 仍标 T77 `NOT EXECUTED`（已由本轮执行） | Tester |

## Merge Gate

- 必要测试通过（59 tests OK；T77 真实集成 PASS）。
- Review APPROVED WITH FOLLOW-UP；无 BLOCKER/HIGH/必须修复 MEDIUM；无产品未决。
- 批准 Base / HEAD 与 merge 输入一致（`e6fe87e` 的两父提交为 `2c3293f` 与 `67590f5`）。
- 工作区清洁项（RV2-04）由 `.gitignore` 忽略 `.agents/` 脚手架解决。

## Follow-ups

1. 后续可选：修正 `--include-down` help 文案；增强漂移守卫解析 F023 正文；hostname 内部空白/C1 处理。
2. T77 已在本报告留证；部署到真实物理机后建议补测免 root/发行版命令矩阵。