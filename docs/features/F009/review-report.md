# F009 IP Pool 地址池 — Review Report

- **版本**：REV-1
- **日期**：2026-10-09
- **角色**：Reviewer（正式 Review）
- **结论**：`APPROVED WITH FOLLOW-UP`
- **依据**：requirements-v3.md revision 3（§4/§4.1、§11/§11.1、§12/§12.1、§14、§20–§23、§25–§28、§31 T15/T24/T25/T26/T33–T35/T40/T41、§35.2 Q04-A/Q04-B/Q10-A/Q10-B、§35.3 D01/D02）；docs/features/F009/product.md（A1–A23、I-1–I-6）；architecture.md（DR-102–DR-117）；docs/database/f009-ip-pool.md v1（DB-D95–D110）；docs/api/F009.md v1；docs/architecture/d01-conventions.md v8 §5.8；docs/api/F002.md §1.2.1；docs/api/F008.md v1；docs/features/F009/implementation.md、test-report.md（TD-1/TD-2/TE-1）；.pi/skills/data-integrity/SKILL.md；docs/project/implementation-rules.md。批准核验：plan_revision 4 全部 16 Feature（用户 2026-10-06），F009 无命中 pending_changes。

## Scope Reviewed

| 项 | 值 |
| --- | --- |
| Feature Branch | `feature/F009-ip-pool` |
| start_commit | `ce40befd55706dfe0c0f0e73aeb877c68587f083` |
| Base（v3） | `ce40befd55706dfe0c0f0e73aeb877c68587f083`（= start_commit） |
| merge-base | `ce40befd55706dfe0c0f0e73aeb877c68587f083` |
| 候选 HEAD | `7a0b3a3791deb4f1edf59d2f1e12d5e1b388c4c9` |
| 完整范围 | `git diff v3...HEAD`：37 files，+7855/−49；7 commits（c77443a→7a0b3a3） |
| 工作区 | clean |

独立复跑：后端全量 **292 passed, 1 skipped**；F009 专属 **43 passed**；前端 typecheck/build 通过、smoke **133 passed**；`validate_project_state.py --feature F009` VALID。

## 适用层结论

- **产品与领域（PASS）**：§12/§12.1/§4.1/§21/§11.1/§20/§22/§23 落地；A1–A23 满足；范围未扩张；I-3 正确不新增建池限制；allocation_mode 仅保存/暴露。
- **数据完整性（PASS）**：`name_key` CHECK + 部分唯一、`address_range` 生成列 + `int8range` 排他约束、CIDR 包含触发器、host CHECK、FK RESTRICT、软删/恢复重检、`_lock_network` 锁域，均真实 PG 验证。
- **架构与依赖（PASS）**：独立表、`network` 不可改、占用提供者注册表（F009 空集）、引用检查器、gateway 挂钩。
- **Database/Migration（PASS）**：`0009_ip_pools` 单 head、无回填、对称可逆、不 drop 扩展。
- **API 与实现（PASS）**：7 端点、错误码、校验顺序、软删可见性、恢复优先级、乐观锁、审计符合 Contract v1。
- **标识符（PASS）**：中文/非 ASCII 原样、内部普通空格保留不合并；API/DB 归一化一致。
- **前端（PASS）**：network 编辑只读、exclude_unset、各冲突 reason 明文呈现、未知 reason 通用呈现。
- **测试充分性（PASS）**：独立重跑一致；真实 PG raw/并发证据；未见迎合实现或假阳性；未以桩 PASS 拼 T33/T35。
- **安全与范围（PASS）**：Diff 聚焦、无新增依赖、无无关重构。

## Findings

| ID | 严重度 | 层 | 位置 | 说明 | Owner | 阻塞 |
| --- | --- | --- | --- | --- | --- | --- |
| F009-REV-01 | LOW | Project State | project-plan.yaml F009 条目 | 缺 `git.base_branch/branch/start_commit/head_commit/merge_commit`；须在 Merge/DONE 前补记。已在最终状态提交补齐。 | 协调器 | 否 |
| F009-CON-01 | LOW | Contract（跨 Feature） | docs/api/F008.md §1.2/§6.4/§7 | F009 使 Network PATCH 在 gateway 已占用时返回 409 `address_in_use{field:"gateway"}`（F009 空集不可达，F010 可达）；F008 错误集未含该 reason。 | Architect/协调器（F010 订正） | 否 |
| F009-CON-02 | LOW | Contract（跨 Feature） | docs/api/F003.md §1.2 | 交叉引用应指向 F002 §1.2.1；`unique_conflict` 措辞易误读。 | Architect/协调器 | 否 |
| F008-REV-01/02 | NOTE | Database doc | docs/database/f008-network.md §3.3/DB-D83/DB-D88 | F008 文档 errata（已在 f009-ip-pool.md §7 记录；0008 已用正确写法，不影响 F009）。 | 协调器 | 否 |
| F009-REV-02 | NOTE | Backend | services/ip_pool.py `_translate_integrity_error` | 排他并发兜底 `range_overlap` 的 `conflicts` 为空数组（罕见竞争路径，轻微 UX 降级）。 | Backend（可选） | 否 |
| B36 | LOW | Test | test-report §10.5 | 「恢复 vs 并发重建」双会话用例 NOT TESTED；机制由部分唯一 + 排他 + 恢复重检闭环。 | Tester | 否 |
| 入口 Nginx/Compose | NOTE | Integration | — | 全链路未运行；权限矩阵以真实 ASGI + 真实 PG 覆盖（同 F007/F008）；Compose 归 F016。 | 协调器 | 否 |
| 测试注释 | NOTE | Test | test_occupancy_patch_expansion_field_rules | 中间注释误导（断言正确）。 | Tester | 否 |

无 BLOCKER / HIGH / 必须修复 MEDIUM。

## 旧缺陷复核

- TE-1 Defects：无；独立重跑未发现业务实现、Schema 或契约偏差。
- B36 维持 LOW（机制闭环）；A10–A12/A14/A22/T33/T34/T35/T32 确认为 F010/F013 归属；Nginx/Compose 为环境限制 NOTE。

## Follow-ups

1. 协调器：Merge/DONE 前补 F009 git 块（已在最终状态提交完成）。
2. Architect/协调器：F010 落地真实占用时订正 F008 gateway 错误集（F009-CON-01）与 F003 §1.2 交叉引用（F009-CON-02）。
3. 协调器：按 change-control 择机处理 F008 文档 errata（F008-REV-01/02）。
4. Tester（可选）：补 B36 双会话用例；润色测试注释。
5. Backend（可选）：并发竞争路径填充 `range_overlap.conflicts`。

## 未审查项

- F010/F013 的 IP 分配、容量公式等（不在 F009 范围）；F014/F015/F016；真实浏览器 DOM；F001–F008 实现本体（仅涉交叉点）。

## 正式结果

**APPROVED WITH FOLLOW-UP** — A1–A23 核心验收满足，V-DB-82–94 与关键边界/并发在真实 PG 独立复现通过，无 BLOCKER/HIGH/必须修复 MEDIUM，无未决产品问题。批准仅对候选 HEAD `7a0b3a3791deb4f1edf59d2f1e12d5e1b388c4c9` 与 Base `ce40befd55706dfe0c0f0e73aeb877c68587f083` 有效。

```text
GIT: NONE
```

本次 Review 仅只读核对与在独立容器/测试库复跑；未修改仓库文件，未暂存/提交/切换分支/合并。报告由协调器按 Git Workflow 持久化。