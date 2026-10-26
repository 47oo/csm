# F036 证据与记载项记录（DR-F036-09 / DR-F036-10）

- **版本**：v1（2026-10-26，IMPLEMENTATION Gate 协调器执行；裁定依据 `docs/features/F036/architecture.md` §12，TD-I-1 / TD-I-2）。

## 1. DR-F036-09 三项

| 子项 | 处理 | 证据 |
| --- | --- | --- |
| F033-RV-01 smoke 基线陈旧（322/328） | F036 起以**实测计数**为基线；F033 报告正文不改（历史记录） | 本次实测：`cd frontend && npm run smoke:client` → **340 passed, 0 failed**（2026-10-26，实现提交后）；基线演进：322（F028/F029）→ 328（F033）→ 337（F034）→ 339（F035）→ **340（F036，新增 placeholder 常量用例）** |
| F034-RV-04 logs 入库范围描述不准 | 以 `git ls-files` / `git check-ignore -v` 逐项列出实际入库集合，二者并列，不笼统称「logs 被忽略」 | `git ls-files docs/features/F034/artifacts` 实际含 `logs/**`（12 个文件）+ JSON/脚本；`docs/features/F032/artifacts` 含 `real-validate/setup.log`、`cli-smoke.log`（`git add -f` 入库，`git check-ignore -v` 输出为空 ⇒ 已跟踪不受忽略规则影响） |
| F032-RV-06 报告含明文测试库口令 | 全 `docs/` 范围统一掩码为 `***` | 掩码前 `grep -rl csmtestpw docs/` = 12 文件 / **18 行**；掩码后 `grep -rn csmtestpw docs/` = **0**。`***` 为测试库口令字面量（值在 `.env.test`），涉及检索命令的行仅把字面量替换为 `***`，原结论句保留 |

## 2. DR-F036-10 记载项落点

| 子项 | 落点 |
| --- | --- |
| 11a F032-RV-05 | `scripts/collect_host_info.py::build_error_hint` docstring：任意 argparse 错误统一追加三组枚举允许值是 DR-1007 既有取舍；触发点 `_ArgumentParser.error()`；收窄须另立变更 |
| 11b F032-RV-07 | `scripts/collect_host_info.py::collect` docstring：`resource_type: str \| None` 仅供 `build_rows` 单测与防御边界；CLI 仍 `--resource-type required=True`；`_push` 防御检查保留 |
| 11c F034-RV-08 | 表头级 `details.unknown_columns` / `missing_columns` 回显「被当作表头的那一行」原文属 **F014/F023 既有 schema**、两载体逐字段一致；收紧属契约变更，须另立提案（`docs/features/F036/architecture.md` §7 R-10） |
| 11d F035-FU-05 | 既有 B 层证据视口为 **1440×1000**（`docs/features/F035/artifacts/f035-browser-check.json`，不改写）；触发条件：改「追加提示区」布局 ⇒ 必须补 375 / 1023 窄屏证据（§7 R-11） |
| 11e F035-FU-08 | 5000 行纯追加性能仍 `NOT TESTED`（契约无数值阈值）；触发条件：性能回归时按 `docs/database/f023-import.md` §5.7 复核，**不得**放松 V11.5 锁环判据（§7 R-12） |

## 3. 脱敏与掩码的执行记录

- MAC 脱敏：见 `docs/features/F032/artifacts/real-validate/REDACTION.md`（5 个被跟踪文件 / 20 处 → 0；CSV 4 行 × 26 列与 `.log` 行数不变）。
- 口令掩码：`docs/` 下 12 个文件 18 行，仅字面替换，无结论句删除；`git diff` 行数与命中行数一致。

## 4. 明确不在本 Feature 范围

**F034-RV-02（T114 等价性口径追认）**：属用户对需求正文的确认动作；F036 不实现、**不宣称已关闭**，需用户一句话追认后由需求 revision 15 落稿（CHG-014 §3）。
