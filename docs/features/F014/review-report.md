# F014 CSV / Excel 批量导入 — Review Report

- **Feature 分支**：feature/F014-import
- **Base（v3）**：48ca02fcc440761ab74be586e1c48e901708d8af（= start_commit = merge-base）
- **批准 HEAD（候选）**：8ba6ac32fcec421bb9150482cb195f903e918daf
- **正式结果**：**APPROVED WITH FOLLOW-UP**（两轮：Round 1 CHANGES REQUIRED → Round 2 APPROVED）
- **独立验证**：后端全量 529 passed/1 skipped；F014 独立验收/性能 17/17；前端 typecheck/build（82 modules）/smoke 241；nginx `client_max_body_size 6m` 真实转发验证（1/3/5.5 MiB→200，6.1 MiB→413）。

## Round 1 — CHANGES REQUIRED（首审候选 4840e2e）

| ID | 级别 | 层 | 位置 | 说明 | Owner | 阻塞 |
| --- | --- | --- | --- | --- | --- | --- |
| RV-F014-01 | MEDIUM | 部署 | `deploy/nginx/nginx.conf` | 入口默认 `client_max_body_size` 1 MiB，未达 D03 签核 5 MiB；1–5 MiB 上传被 nginx 以 HTML 413 拒绝，签核上限在交付部署不生效。 | Backend/协调器 | 是 |
| RV-F014-02 | LOW | Backend | `resource_import.py::parse_and_validate` | 行数上限(413) 应在表头/列(422) 之前；实现顺序相反。 | Backend | 否 |

## 修复（有限修复第 1 轮）
- RV-F014-01：`deploy/nginx/nginx.conf` `/api/` 增加 `client_max_body_size 6m` 与 `proxy_read_timeout/proxy_send_timeout 180s`；`nginx -t` 通过；真实转发验证 5.5 MiB 可达后端。
- RV-F014-02：`parse_and_validate` 调整顺序为 parse→行数上限(413)→表头/列(422)→逐行；补回归用例。

## Round 2 — APPROVED WITH FOLLOW-UP（修复后候选 8ba6ac3）

- **旧缺陷复核**：RV-F014-01 CLOSED（独立 nginx 转发验证）；RV-F014-02 CLOSED（顺序与 Contract §2 一致，回归通过）。
- **适用层结论**：产品/领域、架构/依赖、数据(NOT_REQUIRED)、API/实现、标识符、前端、测试、安全/范围/变更批准均 PASS。

### Findings（Round 2）

| ID | 级别 | 层 | 位置 | 说明 | Owner | 阻塞 |
| --- | --- | --- | --- | --- | --- | --- |
| RV-F014-03 | NOTE | Plan | project-plan.yaml F014 | 缺 `git` 块；Merge/DONE 前必须补齐（start_commit=48ca02f）。 | 协调器 | 否 |
| RV-F014-04 | NOTE | 部署 | nginx.conf | >6 MiB 由 nginx 返回 HTML 413（非契约信封）；契约上限 5 MiB，无验收影响。 | 协调器/Architect/Frontend | 否 |
| RV-F014-05 | NOTE | 测试/范围 | test-report A19/B20 | 单模板/单文件契约下混合批结构性不可达；安全不变量由先校验后插入保证（DB 不兜底）。 | Architect/Product | 否 |

### 正式结果
**APPROVED WITH FOLLOW-UP** — 批准仅对候选 HEAD `8ba6ac32fcec421bb9150482cb195f903e918daf` 与 Base `48ca02fcc440761ab74be586e1c48e901708d8af` 有效。无 BLOCKER/HIGH/必须修复 MEDIUM。

## Follow-ups
1. 补齐 F014 `git` 块（RV-F014-03）。
2. >6 MiB 信封呈现（RV-F014-04，可选）。
3. A19/B20 设计风险记录（RV-F014-05）。
4. 真实浏览器 DOM E2E、Compose 全链路、§31/§32 归 F016。

## 未审查项
- 真实浏览器 DOM E2E；完整 Compose 全链路；§31/§32 跨功能与一期整体验收（F016）。

```text
GIT: NONE
```