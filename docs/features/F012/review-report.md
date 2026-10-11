# F012 Service Endpoint 监听端点 — Review Report

本文件记录 F012 正式 Review 两轮：Round 1 `CHANGES REQUIRED`（发现并修复 `F012-RV-01`），Round 2 `APPROVED WITH FOLLOW-UP`。

- **Feature 分支**：feature/F012-service-endpoint
- **Base（v3）**：002730a45fd8287aed07ae9d4c510b8df6530a2b（= start_commit = merge-base）
- **批准 HEAD（候选）**：ab3e6708b73c8d89c06315f45c985b03275d10df
- **Merge SHA**：7bd0fad85ea647bc2a391a96b58871840462abf0

---

## Round 1 — CHANGES REQUIRED（首审候选 c93b47a）

- **结论**：`CHANGES REQUIRED`
- **依据**：requirements-v3.md revision 3（§13.3、§14、§15、§16、§21、§22、§23、§27、§31 T22/T23/T26）；docs/api/F012.md v1 §2.2；D01 v11 §5.11；docs/database/f012-service-endpoint.md v1。
- **独立复跑**：后端全量 437 passed/1 skipped；F012 43 passed；前端 211 passed。
- **核对通过**：T22/T23 双 provider 端到端（409 `reference_exists`，object_type=`service_endpoint`）；errata-03 落地；数据完整性（部分唯一/触发/CHECK/FK）。

### Findings（Round 1）

| ID | 级别 | 层 | 位置 | 说明 | Owner | 阻塞 |
| --- | --- | --- | --- | --- | --- | --- |
| **F012-RV-01** | **MEDIUM** | Backend | `schemas/service_endpoint.py` | `port` 裸 `int`（lax）接受 `"80"`→201、`true`→201；契约 §2.2/A7/D01 §5.11 要求非整数→422 field="port"；偏离 F005/F007 `StrictInt` 先例。 | Backend | 是 |
| F012-RV-02 | LOW | Backend 测试 | `test_protocol_and_port_validation` | 未覆盖 B8 的 `"80"`/布尔；A7 PASS 声明超出实测。 | Backend/Tester | 是（根因同 RV-01） |
| F012-RV-03 | NOTE | 文档证据 | test-report §11.3 | 全量计数 436 vs 实际 437。 | 协调器 | 否 |

---

## Round 2 — APPROVED WITH FOLLOW-UP（修复后重审候选 ab3e670）

- **结论**：`APPROVED WITH FOLLOW-UP`
- **修正**：`F012-RV-01` 修复——`port` 改 `Annotated[StrictInt, Field(ge=1, le=65535)]`（create/update）；`_validate_port` 布尔守卫补注释；补 B8 回归（`"80"`/`True`/`22.5`→422，`1`/`65535`→201/200）。Tester TE-2 复核关闭。
- **独立验证**：后端全量 438 passed/1 skipped；F012 44 passed；真实 API 探针 POST/PATCH 非法 port→422 field="port"，边界→201/200；前端 typecheck/build/smoke 211 passed。
- **适用层结论**：产品/架构/数据与 Migration/API/前端/测试/安全/范围/批准均 PASS。

### Findings（Round 2）

| ID | 级别 | 层 | 位置 | 说明 | Owner | 阻塞 |
| --- | --- | --- | --- | --- | --- | --- |
| F012-RV-N1 | NOTE | Docs | test-report §12 | TE-2 写修复「未提交」，实为已随 `ab3e670` 提交；纯措辞。 | 协调器 | 否 |
| F012-RV-N2 | NOTE | API | `port` | `StrictInt` 亦拒绝 `1.0`（略严于字面），与 F005/F007 先例一致。 | Backend | 否 |
| F012-TE1-01 | NOTE | Backend 测试 | `test_invalid_listen_forms_rejected` | A19 未逐一断言，由 `extra="forbid"` + 静态核对闭合。 | Backend（可选） | 否 |
| F012-TE1-02 | NOTE | 集成环境 | Compose/Nginx | 真实浏览器 DOM 未跑（环境）；机制级 + ASGI+PG 覆盖。 | 协调器 | 否 |

- **旧缺陷复核**：F012-RV-01 CLOSED（独立探针 422/201 符合）；F012-RV-02 CLOSED（测试补入）；F012-RV-03 CLOSED（计数修正 438/44）。

### Follow-ups

1. 协调器：更新 TE-2「未提交」措辞（已在最终状态提交/说明）；F010 test-report 历史行可加 errata-03 引用。
2. §18/§19/§17/Dashboard 聚合归 F013；T22–T26 完整回归与 §32 归 F016；导入 F014；完整 Audit F015。

### 未审查项

- Compose/入口 Nginx 真实前后端集成与真实浏览器 DOM（NOT TESTED，环境）。
- §18/§19/§17/§20 展示聚合（F013）；F014/F015/F016。

### 正式结果

**APPROVED WITH FOLLOW-UP** — 核心验收 A1–A21 满足，F012-RV-01 关闭，无 BLOCKER/HIGH/必须修复 MEDIUM，仅非阻塞 NOTE。批准仅对候选 HEAD `ab3e6708b73c8d89c06315f45c985b03275d10df` 与 Base `002730a45fd8287aed07ae9d4c510b8df6530a2b` 有效。Merge SHA `7bd0fad85ea647bc2a391a96b58871840462abf0`。

```text
GIT: NONE
```