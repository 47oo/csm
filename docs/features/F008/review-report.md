# F008 Network 网络管理 — Review Report

- **版本**：REV-1
- **日期**：2026-10-09
- **角色**：Reviewer（正式 Review）
- **结论**：`APPROVED WITH FOLLOW-UP`
- **依据**：requirements-v3.md revision 3（§4、§4.1、§11、§11.1、§12.1、§13、§18、§20–§23、§25–§28、§31 T14/T16/T24/T25/T29/T30/T37/T38/T40/T41、§35）；docs/features/F008/product.md（A1–A22）；docs/features/F008/architecture.md；docs/database/f008-network.md v1；docs/api/F008.md v1；docs/architecture/d01-conventions.md v7 §5.7；docs/features/F008/implementation.md（含 §10 修复）；docs/features/F008/test-report.md（TD-2 + TE-1 + TE-2）；docs/project/project-plan.yaml revision 4；docs/project/change-control.md；docs/project/git-workflow.md §4；.pi/skills/data-integrity/SKILL.md。

## Scope Reviewed

| 项 | 值 |
| --- | --- |
| Feature Branch | `feature/F008-network-management` |
| start_commit | `52666fb0f8091b770744a4dc5268b63398ee79b5` |
| 候选 HEAD | `efb09808d577e40ec7199a3826d21cd62f402d72` |
| Base（v3） | `52666fb0f8091b770744a4dc5268b63398ee79b5`（= start_commit） |
| merge-base | `52666fb0f8091b770744a4dc5268b63398ee79b5` |
| 完整范围 | `git diff v3...HEAD`：32 文件 / +6525 −67；`git log --oneline v3..HEAD`：9 提交（a210308 → efb0980），base 未前移 |
| 工作区 | clean，无未跟踪/未暂存文件；HEAD 非 detached |

已核对 `start_commit..HEAD` 全部提交；候选 HEAD 含 `ce68f1d`（DEF-01 修复）与 `efb0980`（TEST/TD 定稿）。独立复跑：后端 focused 32 passed、全量 249 passed/1 skipped；前端 typecheck + smoke:client 108 passed。

## 适用层结论

| 层 | 结论 | 说明 |
| --- | --- | --- |
| 产品与领域 | PASS | A1–A22 映射到可观察判据；未静默引入对象/关系/状态/唯一性/生命周期规则；I-3 仍记录为待用户裁定的新业务限定，未预建限制 |
| 数据完整性 | PASS | 部分唯一 `(cluster_id,name_key) WHERE deleted_at IS NULL`、排他约束 `(cluster_id=,cidr&&) WHERE deleted_at IS NULL`、FK RESTRICT、全部 CHECK 在真库 raw 验证；软删排除/恢复重检/并发闭环 |
| 架构与依赖 | PASS | 独立表 PK=UUID + FK RESTRICT、引用检查器注册表（初始空集）、FOR UPDATE 锁序，符合 DR-89/90/92/93/96/97/98/100/101 |
| 数据/Migration | PASS | `0008_networks` 单 head、`down_revision=0007_interfaces`、对称可逆、不 drop btree_gist、无回填；up/down/up 通过 |
| API 与实现 | PASS | 7 端点、错误码/`range_overlap` details、空结果/未找到/nullable/只读副作用、校验顺序均符合 Contract |
| 前端 | PASS | 7 端点 client、表单解析/PATCH exclude_unset 镜像、完整错误码呈现；本地校验非权威，服务端 422 透传 |
| 测试 | PASS | 真 PG + raw SQL + `committed_engine` 并发；TE-1 假阳性已修正；未发现迎合实现的新假阳性 |
| 安全与范围 | PASS | 服务端鉴权、无越权绕过；无敏感信息落 Audit；无无关大范围重构（`resolve_cluster` 提取为单一实现，行为等价，F004 回归通过） |
| 变更与批准 | PASS | plan_revision 4 批准全部 16 Feature，覆盖 F008；`pending_changes: []`；设计签核版本（DB v1 / Contract v1 / D01 v7）与实现一致 |

## Findings

| ID | 级别 | 阻塞 | Owner | 说明 |
| --- | --- | --- | --- | --- |
| F008-REV-01 | LOW（文档） | 否 | Database/Architect | `docs/database/f008-network.md` §3.3 的 gateway CHECK 示例 SQL 仍是修复前写法（`gateway <> network(cidr)::inet` / `<> broadcast(cidr)`，未套 `host()`），与实际已实现的（正确）约束不一致；DB-D83「host 位由 cidr 类型归一化」与真库不符（PG `cidr` 拒绝 host 位，实际由 Service `ipaddress(strict=False)` 归一化）；`0008_networks.py` 模块注释同措辞也需订正。DB-D84 的语义声明正确，仅示例表达式陈旧。实现/验收无缺陷，非阻塞。 |
| F008-REV-02 | LOW（文档） | 否 | Database | DB-D88 未注明排他约束必须显式写 `cidr inet_ops WITH &&`（btree_gist 安装后 `cidr` 默认 GiST opclass `gist_cidr_ops` 仅支持等值）。迁移代码注释已说明，设计正文缺注。 |
| F008-REV-03 | LOW（文档一致性） | 否 | Architect/Coordinator | `docs/api/F008.md` §1.2 声明 `range_overlap` 已「注册至 F002 §1.2 / F003 §1.2 交叉引用」，但本次变更未修改 `docs/api/F002.md`/`F003.md`，共享 CONFLICT reason 注册表仍未列出 `range_overlap`。F008.md 自身已完整定义该 reason，不影响运行，属跨文档一致性缺口。 |
| F008-REV-04 | NOTE（协调状态） | 否 | Coordinator | `project-plan.yaml` F008 缺 `git.head_commit`；`execution.last_result` 仍为 IMPLEMENTATION 数字（247 passed），未记入 TE-2 的 249 passed。已在最终状态提交补齐。 |
| F008-REV-05 | LOW/NOTE（实现边界） | 否 | Backend | `service.network._raise_update_conflict` 默认 `include_deleted=True`：PATCH/DELETE 期间若对象被并发软删，`rowcount=0` 会返回 409 `VERSION_CONFLICT`，而 Contract §7 规定「不可见→404」。窗口极窄、不在验收判据、无用户可见失败，可后续按需修正。 |

**两处遗留 NOTE 独立评定**：均认定为 LOW（非阻塞文档补注），不构成必须修复 MEDIUM——实现约束与测试均正确，已实现行为满足 A10/B17/V10 验收；F008-REV-01 因涉及签核设计正文中含可复制复现缺陷的 SQL 片段，建议在合入后尽快补文，避免 F009 复用时落入同一陷阱。

## 旧缺陷复核（DEF-F008-TE1-01）

| 项 | 结论 |
| --- | --- |
| 缺陷 | `ck_networks_gateway` 未拒绝网络/广播地址（`network(cidr)::inet`/`broadcast(cidr)` 保留掩码长度，`inet <>` 含掩码比较恒真） |
| 修复核对 | 迁移 `0008_networks.py` 与 `models/network.py` 均已改为 `gateway <> host(network(cidr))::inet` / `gateway <> host(broadcast(cidr))::inet`；`/31`、`/32`、禁用 5 段、IPv4-only 语义不变 |
| 独立验证 | 重跑 `test_network_constraints.py`+`test_networks.py`：32 passed；`test_gateway_boundaries` 用各自独立 CIDR raw 直插，网络/广播被 `ck_networks_gateway` 拒、`/31` 两端接受、`/32` 非空拒；全量 249 passed / 1 skipped；前端 108 passed |
| 假阳性复核 | 原 TE-1 用例现各自使用独立 CIDR/名称，排他/唯一约束不可能成为拒绝原因，测试真实落在 gateway CHECK 上；无新假阳性 |
| 状态 | **CLOSED**（独立确认） |

## Follow-ups

1. **Database/Architect**：订正 `docs/database/f008-network.md` §3.3 示例 SQL（加 `host()`）与 DB-D83 措辞；补注 DB-D88 的 `cidr inet_ops WITH &&`；同步 `0008_networks.py` 注释。（非阻塞）
2. **Architect/Coordinator**：将 `range_overlap` 登记进共享 CONFLICT 注册表（F002/F003 §1.2），或修正 F008 Contract 中「已注册」措辞。（非阻塞）
3. **Coordinator**：REVIEW/MERGE 转换补齐 `git.head_commit` 与 TEST 执行结果（249 passed）。（已在最终状态提交完成）
4. **Backend（可选）**：评估 `_raise_update_conflict` 对并发软删的 404/409 语义；可在 F009/F010 子对象并发协议落地时一并处理。
5. 可选增强：`test_network_constraints._expect_violation` 未来可断言具体约束名（当前独立 CIDR 已规避歧义，非必须）。

## 未审查项

- A17 经入口 Nginx + Compose 全链路（环境限制，TE-2 以真实 ASGI + 真 PG 覆盖权限矩阵）；真实浏览器 DOM 渲染（非 F008 必要判据）。
- A22/V22 下游执行、A11 容量数值（归 F009/F010/F013）。
- I-3 禁用范围建网限制（待用户裁定）、I-5 占用 IP 设为 gateway（归 F009/F010）。
- 生产环境实际部署/数据迁移演练（超出 Feature Review 范围）。

## 正式结果

**APPROVED WITH FOLLOW-UP** — 核心验收 A1–A22 满足，migration/约束/并发/API/前端独立验证可信，无 BLOCKER/HIGH/必须修复 MEDIUM，无未决产品问题；仅存在非阻塞文档与协调状态跟进项。本批准仅对候选 HEAD `efb09808d577e40ec7199a3826d21cd62f402d72` 与 Base `52666fb0f8091b770744a4dc5268b63398ee79b5`（merge-base 同）有效。

```text
GIT: NONE
```

本次 Review 仅只读核对与在独立容器/测试库中复跑验证；未修改仓库实现/测试/文档，未暂存、提交、切换分支或合并。报告由协调器按 Git Workflow 持久化。