# F003 Cluster 管理与持久化横切首落地 — 正式 Review Report（修复轮 1 后重审）

- **Feature**：F003（FEATURE，P0，M2）
- **角色**：Reviewer（只读）
- **日期**：2026-10-07
- **Status**：`APPROVED WITH FOLLOW-UP`

## Scope Reviewed

| 项 | 值 |
| --- | --- |
| Feature Branch | `feature/F003-cluster-management` |
| Base / start_commit | `v3` = `b34805189304c0ac6d009ce2e6cbba8bb4b20914` |
| merge-base | `b348051`（= start_commit） |
| 候选 HEAD（批准对象） | `690f781569da35538fc45b324a5fe983b36c1ff6` |
| 完整范围 | `b348051..690f781`，14 commits，37 files，+5757/−52；工作区 clean |
| 被测实现一致性 | `git diff 933fae4 690f781 -- backend frontend` 为空 → HEAD 实现 == TE-2 被测代码 |
| 测试证据 | `docs/features/F003/test-report.md` TD-2 + TE-2（F003-REV-1 FIXED，回归 78 passed） |
| 批准链 | plan_revision 4 F003 获批；D01 v2 / D02+Contract v2 签核；pending_changes 无命中；state valid |

独立复现：真实 PG 重跑 `pytest tests` 78 passed, 1 skipped；独立脚本比对应用 code_key 与 DB `translate(...)` 全样例一致；CHECK `pg_get_constraintdef` 含 translate 不含 upper；原始 SQL 正/负例；软删全量唯一；IntegrityError 映射。

## 适用层结论

- 数据库：`ck_clusters_code_key_matches = translate(btrim(code),'abc…','ABC…')`，应用/DB 12 组样例逐一相等，locale 无关；`straße`/`ﬁle`/`山河3` 插入成功，`STRASSE`/`FILE`/`WEISS` 被拒，软删重复仍拒；Schema 与 DB v2 一致，0003 单 head 可逆。
- 后端：REV-1 根因消除（ASCII 折叠 + IntegrityError→409/422，不再 500）；CRUD/软删/权限/乐观锁/审计同事务未受影响。
- 前端：修复轮未触及 `frontend/**`；上轮已核对。
- 契约与文档：Contract v2 §2.1/§5/§6.3、D01 v2、DB v2 与实现一致；REV-2 记为 I-6 已知差异；REV-3 已闭合；D-TE-F003-2 已同步。

## Findings（均非阻塞）

| ID | Severity | Location | 问题 | Owner | 必须修复 |
| --- | --- | --- | --- | --- | --- |
| F003-REV-6 | LOW | docs/features/F003/architecture.md（§1.3/§4.1/§5/DR-24/§9.1） | Stage 报告正文仍写 `upper(...)`，未标注已被 D01 v2/Contract v2 取代 | Architect/协调器 | 否 |
| F003-REV-7 | NOTE | services/cluster.py `_translate_integrity_error` 通用回退 | 防御性 422 details 为空 `{}` 而非 `{fields:[…]}`；API 路径不可达 | Backend | 否 |
| F003-REV-4 | LOW | docs/api/F002.md §1.2 | 错误码注册表未登记 F003 新增 `CONFLICT` | Architect/协调器 | 否 |

无 BLOCKER / HIGH / 必须修复 MEDIUM。

## 旧缺陷复核

| 旧 ID | 上轮 | 本轮 |
| --- | --- | --- |
| F003-REV-1（MEDIUM，必须修复） | 归一化不一致→500 | **FIXED**（独立复现：应用/DB 全样例一致；straße/ﬁle/山河3 201；STRASSE/FILE/WEISS 拒绝；IntegrityError→409/422 无 500；软删全量唯一保持；范围未越界） |
| F003-REV-2（LOW） | DB backstop 弱于应用 | 已作为 I-6 已知差异闭合 |
| F003-REV-3（NOTE） | Contract §5/§6.3 措辞 | 已闭合（v2 统一为 403/404） |
| F003-REV-4（LOW） | F002 §1.2 未登记 CONFLICT | 仍开放（非阻塞，本轮协调器闭合） |
| F003-REV-5（NOTE） | PATCH 仅 version 仍写 Audit | 维持 NOTE |
| D-TE-F003-2（NOTE） | implementation.md 陈旧 | 已修复 |

## Follow-ups（非阻塞）

1. F003-REV-6：architecture.md 标注 ASCII-only 取代 upper。
2. F003-REV-4：F002 §1.2 登记 CONFLICT。
3. F003-REV-7：可选完善防御性 422 details 形状。
4. B41（关系加载软删过滤）待 F004+ 回归；B13 其余排序字段为静态核对；REV-5 PATCH 空变更写 Audit 维持 NOTE。

## 未审查项

未重跑前端 build/smoke（修复轮未触及 frontend）；未起 Compose（以真实 PG pytest + 独立脚本复现 REV-1 为准）；未枚举非默认 collation（translate 与 locale 解耦）；未穷举全部 500 路径；浏览器 DOM 未执行。

## 正式结果

**`APPROVED WITH FOLLOW-UP`** — REV-1 独立复现为 FIXED，核心验收满足，验证可信，无 BLOCKER/HIGH/必须修复 MEDIUM，无未决产品问题。批准仅对候选 `690f781` 与 Base `b348051` 有效。Merge/DONE 由协调器按 Git Workflow §5 判定。
