# F011 Service 服务登记 — Review Report

- **版本**：REV-1
- **日期**：2026-10-09
- **角色**：Reviewer（正式 Review）
- **结论**：`APPROVED WITH FOLLOW-UP`
- **依据**：requirements-v3.md revision 3（§4.1、§15、§16、§17、§18、§21、§22、§23、§25、§27、§28、§31、§35）；docs/features/F011/product.md（A1–A18）、architecture.md（DR-140–DR-154）；docs/database/f011-service.md v1（DB-D128–D141）；docs/api/F011.md v1；docs/architecture/d01-conventions.md v10 §5.10；docs/api/F002.md §1.2.1；implementation.md、test-report.md（TD-1/TD-2/TE-1）。批准核验：plan_revision 4 覆盖 F011，无 pending_changes。

## Scope Reviewed

| 项 | 值 |
| --- | --- |
| Feature Branch | `feature/F011-service-registry` |
| start_commit | `b50788357dd07a41b3ae0b817c1ed5074cdc672d` |
| Base（v3） | `b50788357dd07a41b3ae0b817c1ed5074cdc672d`（= start_commit） |
| merge-base | `b50788357dd07a41b3ae0b817c1ed5074cdc672d` |
| 候选 HEAD | `5dbea9c971878203b207a0c9096fcfd46e5f67ec` |
| 完整范围 | `git diff v3...HEAD`：38 files，+6962/−52；7 commits |
| 工作区 | clean |

独立复跑：F011 专属 48 passed；后端全量 394 passed/1 skipped；前端 typecheck/build 通过、smoke 187 passed；`validate_project_state.py --feature F011` VALID。

## 适用层结论

- **产品与领域（PASS）**：A1–A18 有实现与证据；范围未扩张；status 人工维护（slurmd→UNKNOWN）；未静默新增规则。
- **数据完整性（PASS）**：部分唯一 `(resource_id,name_key) WHERE deleted_at IS NULL`、name_key translate CHECK、status/metadata CHECK、FK RESTRICT、软删/恢复重检、Resource←Service 引用检查器、service_reference 扩展点（空集）；真实 PG + 真提交并发。
- **架构与依赖（PASS）**：符合 DR-140–DR-154；独立表 PK=UUID；`service_reference.py` 与 F010 同构。
- **API 与实现（PASS）**：7 端点、校验顺序、422/409、nullable/只读、软删可见性、Activity、审计白名单、乐观锁、不新增 reason；name_key 不暴露；sort=name 按 name_key。
- **前端（PASS）**：Services 列表/详情/表单/Resource Detail 区域；错误不伪装空列表；409/422/VERSION_CONFLICT 呈现不静默重试。
- **测试（PASS）**：真实 PG、真提交并发；A1–A18/V-DB-112–125/B1–B40 映射完整；独立 12 项补充。
- **变更与批准（PASS）**：plan_revision 4 覆盖 F011；D01 v10/Contract v1/DB v1 一致；迁移 0011 单 head、无回填、对称、不重复启用扩展。

## Findings

| ID | 级别 | 层 | 位置 | 说明 | Owner | 阻塞 |
| --- | --- | --- | --- | --- | --- | --- |
| F011-TE1-01 | NOTE | Database 文档 | f011-service.md §7 V-DB-112 | 计数笔误（“9 CHECK”→实为 8）；已在最终状态提交订正。 | Database | 否 |
| F011-TE1-02 | NOTE | Backend 文档 | implementation.md §1 | 注册路径归因（实为 `service.py` 模块级注册经导入链生效）；已在最终状态提交订正。 | Backend/协调器 | 否 |
| F011-REV-01 | NOTE | Backend | `service.py` `register_dependency_checker("service", …)` | 注册项 F011 内无调用点（`restore_service` 内联重检）；与既有 Feature 内联先例一致，可后续统一经 registry。 | Backend/Architect（可选） | 否 |
| F011-TE1-03 | MEDIUM（非 F011） | 测试基础设施 | `test_clusters.py`/`test_ip_addresses.py` | 时序 flake（F003/F010 代码）；F011 未改；单独重跑通过。 | 协调器/Backend | 否（F011 不阻塞） |
| F011-TE1-04 | NOTE | Integration | Nginx/Compose | 未跑全栈（环境，禁 docker build）；真实 API 已由 ASGI+PG 覆盖。 | 协调器 | 否 |

无 BLOCKER / HIGH / 必须修复 MEDIUM。

## 旧缺陷复核

- Tester TE-1 报告 Defects：2 文档 NOTE（已订正）、1 非 F011 flake MEDIUM（不阻塞 F011）、1 环境 NOTE。均成立且非阻塞。

## Follow-ups

1. F012 必须调用 `register_service_reference_checker` 注册真实 Endpoint provider 并闭合 T23 端到端（DR-146）。
2. 协调器隔离修复 F003/F010 时序 flake（不影响 F011）。
3. 评估 `service` 依赖检查器注册项统一经 registry 或移除（可选）。
4. §17/§19/Dashboard 归 F013；共同前置已就绪。

## 未审查项

- T23 真实 ServiceEndpoint 端到端（F012）；§17/§19/Dashboard（F013）；F014 导入；F015 完整 Audit；F016 §31–33 整体验收。
- Compose/Nginx 真实前后端集成与真实浏览器 DOM（NOT TESTED，环境）。

## 正式结果

**APPROVED WITH FOLLOW-UP** — F011 独立范围核心验收满足、必要验证可信，无 BLOCKER/HIGH/必须修复 MEDIUM，无未决产品问题；仅非阻塞文档 NOTE、非 F011 flake 与环境项。批准仅对候选 HEAD `5dbea9c971878203b207a0c9096fcfd46e5f67ec` 与 Base `b50788357dd07a41b3ae0b817c1ed5074cdc672d` 有效。Merge SHA `ddfe564d4df823b8dedb57da833357cc75d0fef7`。

```text
GIT: NONE
```