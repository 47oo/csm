# F010 IP 地址分配与容量 — Review Report

本文件记录 F010 正式 Review 两轮：Round 1 `CHANGES REQUIRED`（发现并修复 `F010-REV-01`），Round 2 `APPROVED WITH FOLLOW-UP`。

- **Feature 分支**：feature/F010-ip-address-allocation
- **Base（v3）**：a4b8de947f7a3aac96807c4615adbdc371420b91（= start_commit = merge-base）
- **批准 HEAD（候选）**：96603640a6b5e36a03a624eb785230dd94fb0911
- **Merge SHA**：77f47bf2ce8566d322e2d8ead42f111605ea9e2d

---

## Round 1 — CHANGES REQUIRED（首审候选 3c8e1ec）

- **结论**：`CHANGES REQUIRED`（1 个必须修复 HIGH）
- **依据**：requirements-v3.md revision 3（§11.1、§12.1、§13/§13.1/§13.2/§13.3、§14、§16、§20、§21、§22、§23、§27、§31）；F010 product（A1–A26）/architecture（DR-118–DR-139）；docs/database/f010-ip-address.md v1；docs/api/F010.md v1；d01-conventions v9 §5.9；docs/api/F002 §1.2.1；F008 errata-01；F003 errata-01。
- **独立复跑**：后端全量 344 passed/1 skipped；F010 专属 52 passed；前端 typecheck/build/smoke 163 passed。
- **适用层结论**：产品/架构/数据/API/前端/测试/安全/批准均基本 PASS；**恢复边界不符合 §11.1**。

### Findings（Round 1）

| ID | 严重度 | 层 | 位置 | 说明 | Owner | 必须修复 |
| --- | --- | --- | --- | --- | --- | --- |
| **F010-REV-01** | **HIGH** | Backend / Contract | `services/ip_address.py::restore_ip_address`；`docs/api/F010.md` §6.7；architecture DR-128 | 恢复仅重检 CIDR/唯一/Cluster/Interface，未重检「地址当前为 gateway 或在 RESERVED 池范围」；独立复现：软删后设 gateway/RESERVED→restore 成功，产生「gateway == 未删 IP」「未删 IP 落 RESERVED 范围」非法状态。requirements §11.1（CONFIRMED）要求恢复与自动/手动/容量共用可分配集合；§31 T34 同。原 product A22/DR-128/Contract §6.7 清单遗漏。 | Backend + Architect；Tester 补回归 | 是 |
| F010-REV-02 | NOTE | Frontend/Scope | `IpAddressForm.tsx` 自动分配表单容量最小展示 | architecture 写「容量显示归 F013」；实际在分配表单内消费容量端点做最小提示，非 Dashboard 页面、不构成范围扩张。 | Frontend（记录） | 否 |
| F010-REV-03 | NOTE | 协调器/状态 | `project-plan.yaml` F010 git 块 | 缺 `git.base_branch/branch/start_commit/head_commit`，须在 MERGE/DONE 前补齐。 | 协调器 | 否 |

- 旧缺陷/备注复核：D-F010-01（AUTO 池 occupied 交集措辞，NOTE，API 可达状态恒等）、D-F010-02（EXPLAIN 断言偏弱，LOW）、D-F010-03（Nginx 未跑，NOTE）均非阻塞。I-10 errata 落地正确且未改变 DONE 行为。

---

## Round 2 — APPROVED WITH FOLLOW-UP（修复后重审候选 9660364）

- **结论**：`APPROVED WITH FOLLOW-UP`
- **修正**：`F010-REV-01` 修复——Contract/architecture/product 对齐（errata-02）；`restore_ip_address` 在 CIDR 重检后复用 `ip_capacity.network_allocatable_intervals` + `interval_contains` 重检可分配边界，失败 422 `field:"address"`；优先级 唯一(409)→依赖(409)→CIDR(422)→可分配边界(422)→恢复；不覆盖新对象。Tester TE-2 复核关闭。
- **独立验证**：后端 F010 专属 54 passed；全量 346 passed/1 skipped；独立临时用例 6/6（gateway/RESERVED 命中 422 且 deleted_at/version 不变；合法 200；唯一/依赖优先）；前端 typecheck/build/smoke 163 passed。
- **适用层结论**：产品/架构/数据与 Migration/API/前端/测试/安全/范围/变更批准均 PASS。

### Findings（Round 2）

| ID | 严重度 | 层 | 位置 | 说明 | Owner | 阻塞 |
| --- | --- | --- | --- | --- | --- | --- |
| N-01 | NOTE | Project-state | `project-plan.yaml` F010 | `repair_rounds`/`last_result` 元数据滞后（已在本轮状态提交同步为 1 / TE-2 346 passed）。 | 协调器 | 否 |
| N-02 | NOTE | Backup | `test_ip_address_constraints.py::test_occupancy_query_uses_partial_unique_index` | EXPLAIN 断言过宽（同 D-F010-02）；索引存在与并发单胜已由独立 raw 证明。 | Tester/Backend（可选） | 否 |
| N-03 | NOTE | Integration | Nginx/Compose | 未 `docker build` 全栈；真实 API 已由 uvicorn E2E 覆盖。 | 协调器 | 否 |

- **旧缺陷复核**：F010-REV-01（HIGH）**CLOSED**（独立复现 6/6）；D-F010-01/02/03 仍非阻塞；F010-REV-02/03 已在本文件 Round 1 补齐文本闭环。

### Follow-ups

1. 协调器：同步 `repair_rounds`/`last_result`/git 块（已在最终状态提交完成）；持久化两轮 Review Report。
2. Tester/Backend：可选收紧 N-02 EXPLAIN 断言。
3. 后续 Feature：T22/T23（真实 Endpoint 端到端）→ F012；T32 显示 → F013；§32 整体验收 → F016。

### 未审查项

- T22/T23 真实 Endpoint 端到端（F012）；T32 Dashboard 显示（F013）；生产 Nginx/Compose 全栈与真实浏览器 DOM（N-03）；完整 §31 跨功能回归与 §32 一期验收（F016）。

### 正式结果

**APPROVED WITH FOLLOW-UP** — 核心验收 A1–A26 满足，F010-REV-01 关闭，无 BLOCKER/HIGH/必须修复 MEDIUM，仅有非阻塞跟进项。批准仅对候选 HEAD `96603640a6b5e36a03a624eb785230dd94fb0911` 与 Base `a4b8de947f7a3aac96807c4615adbdc371420b91` 有效。

```text
GIT: NONE
```

本次 Review 仅只读核对与独立复跑；未修改仓库文件。报告由协调器按 Git Workflow 持久化。