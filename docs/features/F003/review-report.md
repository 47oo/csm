# F003 Cluster 管理与持久化横切首落地 — 正式 Review Report

- **Feature**：F003（FEATURE，P0，M2）
- **角色**：Reviewer（只读）
- **日期**：2026-10-07
- **Status**：`CHANGES REQUIRED`（1 项必须修复 MEDIUM；其余非阻塞）

## Scope Reviewed

| 项 | 值 |
| --- | --- |
| Feature Branch | `feature/F003-cluster-management` |
| start_commit / Base | `v3` = `b34805189304c0ac6d009ce2e6cbba8bb4b20914` |
| merge-base | `b348051`（= start_commit） |
| 候选 HEAD | `c959013` |
| 完整范围 | `b348051..c959013`，14 commits，36 files，+5411/−51；工作区 clean |
| 测试有效性 | TE-1 在 `6615eff` 执行；`git diff c959013 -- backend frontend` 为空 → 被测实现与候选 HEAD 一致 |
| 批准链 | plan_revision 4 F003 获批；pending_changes 无命中；state valid |

独立复现：临时 PG（en_US.utf8）跑 0003，验证 code 全量唯一、code 不可变触发器、audit append-only、metadata/status CHECK、乐观锁双会话 409、audit 同事务。

## 适用层结论

- 数据库：Schema/Migration/Database v1 一致；uq_clusters_code_key 全量唯一（无 deleted_at 谓词）；触发器/FK 生效；0003 up/down 对称。除 REV-1 归一化不一致外可信。
- 后端：CRUD/软删可见性/权限/错误语义/乐观锁/Audit 白名单与同事务/引用依赖检查均与 Contract 一致。REV-1 使部分 Contract 允许的 code 返回 500。
- 前端：列表/详情/表单/软删恢复/错误语义/不静默重试，与 Contract 一致。

## Findings

### F003-REV-1 · MEDIUM · 必须修复（Owner: Backend；Database/Architect 对齐）
- Location：`backend/app/services/normalization.py::code_key`（`code.strip().upper()`）对 `0003` 的 `ck_clusters_code_key_matches (code_key = upper(btrim(code)))`；`app/services/cluster.py::create_cluster` 的 IntegrityError 分支。
- 复现：对 `straße`/`ﬁle` 等，Python `str.upper()` 多码位映射（`STRASSE`/`FILE`），PG `upper()`（en_US.utf8）返回 `STRAßE`/`ﬁLE` → CheckViolation；服务层抛未捕获 IntegrityError，HTTP 映射为 500 INTERNAL_ERROR。`山河3`/`N96P` 正常。
- 期望：Contract 允许的 code 成功（201）或干净语义错误；应用与 DB 同一归一化口径；IntegrityError 不得以 500 暴露。
- 影响：合法输入不可用且失败模式为 500；F014 导入将复用同一 normalization 扩散。无数据损坏/安全问题。
- 修复须附回归用例（含多码位大写 Unicode code）。

### F003-REV-2 · LOW · 非阻塞 · Database
DB `[:cntrl:]`/`[:space:]` 在 locale 下仅覆盖 ASCII/有限范围，弱于应用的 Unicode Cc/Cf 校验；API 路径由应用拦截，无绕过；仅「DB 兜底等于应用规则」表述偏强。

### F003-REV-3 · NOTE · 非阻塞 · Contract 文档
`docs/api/F003.md` §5「否则 404」与 §6.3「显式 deleted=true 无 VIEW_DELETED → 403」措辞不一致；实现遵循 §6.3（403）。建议 Architect 统一。

### F003-REV-4 · LOW · 非阻塞 · 文档
`docs/api/F002.md` §1.2 未登记 F003 新增 `CONFLICT`（N-1 未闭合）。纯文档。

### F003-REV-5 · NOTE · 非阻塞 · Backend
PATCH 仅带 version（无字段变化）仍 UPDATE/version+1/写 before==after audit。Contract 未禁止，前端不发起。

## 旧缺陷复核

D-TE-F003-1（Contract §5/§6.3 措辞 NOTE）确认成立，非实现缺陷，不阻塞。

## Follow-ups（非阻塞）

1. REV-1 修复时确保 DB CheckViolation 不再以 500 暴露（映射 422/409）；补 Unicode 归一化回归。
2. REV-2 收紧/记录 DB 兜底范围与 Cc/Cf 差异。
3. REV-3/REV-4 Architect 统一 Contract §5/§6.3 并在 F002 §1.2 登记 CONFLICT。
4. B41（软删过滤关系加载传播）待 F004+ 有真实 ORM 关系时回归。

## 未审查项

未重跑完整 pytest/Compose（依据 TE-1 + 关键项独立复现）；未逐一验证 name/status/created_at/updated_at 端到端排序（B13 仅 code）；未验证全部 collation 变体（en_US.utf8 已复现 REV-1）；真实浏览器 DOM 未执行。

## 正式结果

**`CHANGES REQUIRED`**（Owner：Backend F003-REV-1；Database/Architect 对齐）。批准仅对候选 `c959013` 与 Base `b348051` 有效；REV-1 修复后需重新测试并重新 Review，Merge/DONE 由协调器按 Git Workflow 判定。

## 建议修复方向（协调器记录，交 Backend/Architect 落实）

将 `code_key` 大小写折叠定义为**仅 ASCII 字母折叠**（非 ASCII 原样保留），使应用与 DB 完全一致且与 locale 无关：应用端对 `[a-z]`→`[A-Z]`、其余不变；DB CHECK 用 `translate(btrim(code), 'abcdefghijklmnopqrstuvwxyz','ABCDEFGHIJKLMNOPQRSTUVWXYZ')`。中文无大小写不受影响；`ß`/`ﬁ` 等保持原样、不再触发不一致。同步更新 D01 §5.1 与 Contract §2.1 措辞；IntegrityError 统一映射为干净错误。
