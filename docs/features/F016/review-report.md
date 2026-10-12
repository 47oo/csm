# F016 一期集成验收与交付 — Review Report

- **Feature 分支**：feature/F016-integration-acceptance
- **Base（v3）**：079e4adddd9d580d5b303de47bfb354ba23aae30（= start_commit = merge-base）
- **批准 HEAD（候选）**：621e1c5022f13092761b8c25edc265ec0a18e933
- **正式结果**：**APPROVED WITH FOLLOW-UP**
- **独立复现**：Reviewer 在候选 HEAD 上独立重跑 `scripts/acceptance/run_acceptance.sh`——Compose 首选失败（EXIT=1，Docker Hub timeout，已录制）；替代栈健康 `/healthz=200`、`/ready=200`、`/=200`、`alembic current=head`；`test_f016_acceptance.py` 40 passed（真 HTTP/真 PG）；T36 B1–B7 PASS（rows 97=97、聚合 md5 一致、append-only 触发器存在、UPDATE/DELETE 被拒、alembic 幂等、恢复库 ready=200、dump>0）；前端 smoke 264 passed。清理无残留。

## 适用层结论
Product/Architecture/Database(NOT_REQUIRED)/Contract(NOT_REQUIRED)/Backend/Frontend(NOT_REQUIRED)/Test/Git-State 均 PASS。未触及 backend/app、frontend/src、alembic、compose.yaml、deploy（无业务改动）；F016 仅新增测试/脚本。

## Findings

| ID | 级别 | 层 | 位置 | 说明 | Owner | 阻塞 |
| --- | --- | --- | --- | --- | --- | --- |
| R-F016-01 | LOW | Test/Report | evidence index 锚点 | F009/F010/F011/F013/F014/F015 的 `#test-execution` slug 片段不精确命中（文件路径有效）。 | Tester | 否 |
| R-F016-02 | LOW | Test/Report | T17/T18 行 | 符号名 `test_manual_allocation_in_pool` 应为 `..._in_and_out_of_pool`。 | Tester | 否 |
| R-F016-03 | LOW | Test | ACC-T16/19/22/23/24/29 | 集成层为子集覆盖；省略规则由 REUSE 的 F001–F015 权威用例覆盖，整体结论不受实质影响。 | Tester | 否 |
| R-F016-04 | MEDIUM | 环境/集成 | §30/A1 | `docker compose up -d` 因 Docker Hub 不可达未直接证明；仅等价替代栈执行（已预批准并如实录制）。网络可达时应复跑真实 Compose。 | 协调器/用户 | 否 |
| R-F016-05 | MEDIUM | Frontend | §33 Q6/DOM | 无浏览器 E2E；以真 HTTP 数据层 + build + smoke 为证据，报告如实标 NOT TESTED。 | 协调器 | 否 |
| R-F016-06 | LOW | Git-State | project-plan F016 | 缺 git 字段（Merge 时补齐）。 | 协调器 | 否 |
| R-F016-07 | NOTE | Test Infra | run_acceptance.sh | 本地默认口令（仅本地临时栈、用后清理，可接受）。 | Tester | 否 |

## 旧缺陷复核
无 TE-1 缺陷；Review 未发现 F001–F015 语义缺陷。开发迭代中的失败均为夹具问题且已闭环；最终提交 40/40 独立通过。

## Follow-ups
1. 网络可达环境复跑真实 `docker compose up -d`（R-F016-04）。
2. 接入浏览器 E2E（R-F016-05）。
3. 修正 evidence 锚点与符号名（R-F016-01/02）。
4. ACC-T16/19/22/23/24/29 标注覆盖范围或补测（R-F016-03）。
5. Merge 补 F016 git 字段（R-F016-06）。

## 未审查项
真实 Compose 构建/编排路径；浏览器 DOM 渲染/交互；超出 smoke 的前端 UX。

## 正式结果
**APPROVED WITH FOLLOW-UP** — 核心验收（T01–T41 映射、RERUN 15、§32 C1–C15、§33 Q1–Q9 数据层、T36 B1–B7、A1–A14/I-1–I-9）满足且有独立复现证据；无 BLOCKER/HIGH/必须修复 MEDIUM；残余为环境性 Compose 未执行与 DOM 未测（设计层已预先接受）。批准仅对候选 HEAD `621e1c5022f13092761b8c25edc265ec0a18e933` 与 Base `079e4adddd9d580d5b303de47bfb354ba23aae30` 有效。

```text
GIT: NONE
```