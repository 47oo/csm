# F025 采集脚本增强 — REVIEW 报告

- **状态**：APPROVED WITH FOLLOW-UP（**独立 Reviewer 已复核并签署**，见 §7）
- **Base / start_commit**：`codex/v3.1` @ `692143e98be8b2c1fa4ee61612c14a6cb2e9fbd9`
- **批准候选 HEAD**：`bdc881ee5c2474003f79c71115ad51e4249f9e14`（merge `6f691f4`）
- **范围**：`feature/F025-collector-enhancements` 全部改动（`scripts/collect_host_info.py`、`scripts/test_collect_host_info.py`、`.gitignore`、F025 文档）。

## 0. 流程偏差（已关闭）

初稿记录：首次 Review 时 Subagent 运行时不可用（`pi ENOENT`），只能由实现者自审，不满足 `AGENTS §7` 角色分离。**该偏差已由独立 Reviewer 重跑复核并签署（见 §7），现已关闭。**

## 1. 审查范围

- 需求符合性：§24.3、T79–T84；范围未扩张（无平台 API/Schema/依赖变更）。
- 模板冻结：`TEMPLATE_COLUMNS` 仍为 F023 §6 26 列；漂移测试通过。
- 推送正确性：两步流程（validate→确认→write）、Bearer 认证、校验错误阻断写入、整批原子由服务端保证。
- 安全：API Key 不落盘、不打印；仅在 `Authorization` 头使用；真实 401 路径确认无泄漏。
- 测试：43 tests（F024 文件）/ 72 tests（全量）通过；真实测试栈端到端推送通过。

## 2. 结论性发现

无 BLOCKER / HIGH / 必须修复 MEDIUM；允许合并（**pending 独立复核**）。

| ID | Severity | 说明 | Owner |
| --- | --- | --- | --- |
| F025-RV-01 | LOW | `main` 在 `--push` 用法错误时仍先写出默认文件，产生副作用 | Backend/Tool |
| F025-RV-02 | NOTE | `--print` 与 `--push` 同时使用会将 CSV 与推送 JSON 混在同一 stdout | Backend/Tool |
| F025-RV-03 | NOTE | `--api-key` 会出现在进程参数中；建议优先 `CSM_API_KEY` 环境变量 | 用户/Backend |
| F025-RV-04 | NOTE | 默认 `urllib` 重定向行为未显式限制，Authorization 头在重定向下可能被转发；生产建议仅直连可信地址 | Architect |
| F025-RV-05 | NOTE | 真实物理机免 root 字段矩阵与 HTTPS 自签场景未实测（继承 F024 限制） | Tester |

## 3. 需求与回归核对

| 项 | 结果 |
| --- | --- |
| T79 参数补全 | PASS（单元） |
| T80 resource_type 写列 | PASS（单元） |
| T81 print / no-header | PASS（单元 + 冒烟） |
| T82 两步推送 | PASS（单元 + 真实端到端 created=1/interfaces=2/ips=2） |
| T83 Key 401 / 无泄漏 | PASS（单元 + 真实 401 rc=1、grep 无泄漏） |
| T84 默认离线 | PASS（单元 + 无 `--push` 不联网） |
| F024 回归 | PASS（43 tests，含 F024 既有断言按 §24.3 调整 1 条） |

## 4. Merge 前置

- 待独立 Reviewer 复核（偏差 §0）。
- 工作区清洁（`.agents/` 已 gitignore；`csm_host_info.csv` 已 gitignore）。
- 批准 Base 与候选 HEAD 一致后按 Git Workflow §5 合并。

## 5. Follow-ups

1. **优先**：runtime 恢复后由独立 Reviewer 重跑本 Feature 并签署；若发现必须修复项，依缺陷记录回退。
2. 可选：将 `--push` 用法校验前置到写文件之前（RV-01）；文档提示 `--print` 与 `--push` 分开使用（RV-02）；生产环境用 `CSM_API_KEY`（RV-03）。

## 7. 独立 Reviewer 复核（合并后签署）

- **Reviewer**：project 独立 Reviewer 角色（非实现者），环境：`codex/v3.1` 合并后工作区。
- **候选**：HEAD `bdc881e` / Base `692143e` / merge `6f691f4`。
- **结论**：**APPROVED WITH FOLLOW-UP**。无 BLOCKER / HIGH / 必须修复 MEDIUM；F025 维持 DONE，不回退。
- **独立复核证据（Reviewer 实跑）**：F024 文件 43 tests OK；全量 72 tests OK；真实测试栈（`http://localhost:18080`）新建 Cluster `F025REV` + Network，实跑两步推送：预校验 `error_count=0` 未写入 → `--yes` 写入 `created=1/interfaces=2/ips=2` → API 复核 total=1；校验错误时 `error_count=2`、`--yes` 后 API 复核 total=0（阻断写入）；无效 Key 401 rc=1 且无泄漏；`git diff bdc881e HEAD -- scripts/ .gitignore` 为空（HEAD 运行代码 == 被审候选）。
- **新发现（均非阻塞）**：F025-RV-06（merge 第二父为候选的元数据子提交，语义完整）/ RV-07（`requirements-v3.md` 页眉 revision 陈旧，本次已修正）/ RV-08（测试名与 §24.3 语义不符，仅可读性）。
- **旧自审项** RV-01..05 逐项复核维持 LOW/NOTE。

**签署**：独立 Reviewer，2026-10-20；批准仅对候选 `bdc881e` 与 Base `692143e` 有效，任一变化须重新验证。