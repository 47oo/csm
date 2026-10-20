# F025 采集脚本增强：参数补全 / 打印 / API 推送 — PRODUCT 阶段报告

- **状态**：READY FOR ARCHITECT
- **版本**：v1
- **上游依据**：`docs/product/requirements-v3.md` **revision 10** §24.3（含 §35.1 revision 10 确认记录）、§24、§23.1、§31（T79–T84）；`docs/project/project-plan.yaml` revision 13（F025）；用户 2026-10-20 回复「按推荐执行并实施」。

---

## 1. 目标与范围

在 F024 离线采集脚本上增强，使维护人员无需手工编辑 CSV 即可补全业务字段，并可选择打印或经 API Key 推送。

范围内（CONFIRMED）：
- **参数补全**：`--cluster`、`--resource-type`、`--role`、`--status`、`--host`、`--network` 写入对应列；`--resource-type` 同时写入该列并决定类型专属列；未提供字段仍留空。
- **打印**：`--print` 输出 stdout；默认含表头，`--no-header` 不带；默认仍写文件。
- **API 推送**：`--push` 经 API Key（HTTP `Authorization` Bearer，复用 F017/§23.1）按 **§24 两步流程**调用 F023 导入端点：先 `POST /imports/resource-interfaces-ips/validate` 展示，经 `--yes` 确认后 `POST /imports/resource-interfaces-ips` 写入。
- 仅标准库 `urllib`；默认行为仍离线只读，仅 `--push` 时连接。

## 2. 明确不做

- 不修改/扩展 F014/F023 模板与契约；不新增平台 API。
- 不创建 Network / IP Pool / Cluster / Host；不触发自动分配；不绕过 Service Layer。
- 不持久化 API Key；不把 Key 写入日志/输出。
- 不改写 F024 历史交付。

## 3. 验收标准（映射 T79–T84）

| # | 用户可观察行为 | 映射 |
| --- | --- | --- |
| A1 | 参数补全后无需手改文件即可通过预校验（除仍无法获得字段）；未提供字段留空 | T79 |
| A2 | `--resource-type` 写入该列且仅填对应类型列 | T80 |
| A3 | `--print` 输出 stdout 不写文件；默认写文件；默认含表头、`--no-header` 首行为数据；列名/序仍为冻结 26 列 | T81 |
| A4 | `--push` 先预校验后确认写入；确认前无写入；写入整批原子 | T82 |
| A5 | API Key 缺失/无效/过期 → 401 且非零退出；Key 不外泄、不落盘 | T83 |
| A6 | 默认（无 `--push`）零网络请求；F024 既有行为无回归 | T84 |

## 4. Blocking Questions

无。BQ6–BQ10 已 CONFIRMED（`decisions_required` 与需求 §35.1 revision 10）。

## 5. 受影响 Feature 与承接

F024 已 DONE，行为变化由新 Feature **F025** 承接，不重写 F024 证据；消费 F023 契约与 F017 机器凭据。