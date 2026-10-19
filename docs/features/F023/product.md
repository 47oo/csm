# F023 资源+网卡+IP 批量导入 — PRODUCT 阶段报告

- **状态**：READY FOR ARCHITECT
- **版本**：v1
- **上游依据**：`docs/product/requirements-v3.md` **revision 8** §24、**§24.1**（含 §35.1 revision 8 确认记录）、§10、§11、§11.1、§12、§13.2、§14、§21、§23、§27、§31（T64–T72）；`docs/project/project-plan.yaml` revision 11（F023）；用户 2026-10-15 对 BQ1–BQ7 的裁定「按推荐执行」与「1. 是 2. 是」。
- **复用说明**：复用 product-manager 2026-10-15 的 F023 澄清报告（原结论 `NOT READY FOR ARCHITECT`，阻塞项 BQ1–BQ7）。协调器核验：确认证据覆盖范围与验收（§24.1 + T64–T72）；Architect 评估 database=false/backend=true/frontend=true、api_required=true；BQ1–BQ7 全部 CONFIRMED。故产品阶段判为复用完成。

---

## 1. 目标与范围

在既有资源新增导入（F014）之上，扩展支持「资源 + 网卡 + IP」三元组批量导入（§24.1），以固定模板一次登记多节点及其网卡、IP，示例行 `vm001,eth0,192.168.1.1/24`。

范围内（CONFIRMED）：
- 模板结构：每行一个「资源+网卡+IP」三元组；同一 `hostname` 多行合并为**一个** Resource；同一资源 Interface 按 `name` 去重；同一 Interface 多行=多 IP。三元组**均必填**（仅资源导入仍用 F014 既有模板）。
- Network：模板须唯一确定 IP 所属 Network（名称/CIDR 列，或 IP 的 `/mask` 在同 Cluster 内唯一匹配已存在 Network）；IP 必须落在该 CIDR 内并满足 §11.1 边界；Network 必须已存在，不存在整批失败；**不创建** Network/Pool/Cluster/Host。
- IP：导入内**新建并绑定** IP（手动分配语义 §13.2/§14 校验：属 CIDR、非 gateway、非 RESERVED、禁用段排除、同 Cluster 唯一、绑定同 Cluster）；**不触发**自动分配（§13.1）。
- Interface：导入内创建（复用 §4.1/§10 名称归一化与同资源唯一、大小写区分）；`interface_type` 默认 `OTHER`（不按名称推断）；一期**不纳入** `parent_interface`。
- 跨对象原子性：Resource + Interface + IPAddress 整批成功或整批回滚，无部分成功、无残留 Audit/Activity。
- 沿用 §24：两步流程（预校验→确认→写入再校验）、错误含行号/字段/原因、VM Host 必须已存在且满足 §9（不在同批次隐式创建 Host）、同一 Service Layer、`IMPORT` 权限、同步与大小/行数上限。
- 新增**独立第三套模板**，不改动 F014 已冻结 BM 14 / VM 10 模板与历史行为。

## 2. 明确不做

- 不含 Service / Endpoint / Cluster 导入。
- 不创建或导入 Network / IP Pool。
- 不改动 F014 既有模板、端点行为与契约。
- 不触发自动分配；不引入新实体/关系/状态/唯一性/权限/错误码。

## 3. 验收标准（映射 T64–T72）

| # | 用户可观察行为 | 映射 |
| --- | --- | --- |
| A1 | 一次提交多节点多行，每个节点正确生成 Resource、其 `eth0` Interface 与 `192.168.1.1/24` IP，且 IP 绑定到该 Interface | T64 |
| A2 | 生成的 IP 属模板引用的正确 Network 且与 Resource 同 Cluster；IP 不在 CIDR 内或跨 Cluster 时整批失败 | T65 |
| A3 | 同 hostname 多行=一个 Resource 多 Interface/多 IP；同 Interface 多行=一个 Interface 多 IP，去重正确 | T66 |
| A4 | 重复（同 Cluster hostname、同资源 interface name、同 Cluster IP）或非法行报错，错误含行号/字段/原因 | T67 |
| A5 | 任一行写入失败时整批回滚，无部分成功、无 Resource/Interface/IP/Audit 残留 | T68 |
| A6 | 预校验→确认→写入前再次校验；预校验后状态变化导致冲突时写入失败（不静默覆盖） | T69 |
| A7 | VM 行 Host 必须已存在且同 Cluster；不存在时整批失败，不隐式创建 Host/Network/Pool/Cluster | T70 |
| A8 | 导入与普通 API 对 hostname/interface name/IP 唯一性结果一致（同一 Service Layer，不得绕过） | T71 |
| A9 | 无 `IMPORT` 权限拒绝；未定义列/缺列/列序 422；超限 413 | T72 |
| A10 | F014 既有 BM/VM 模板与历史导入行为无回归 | — |

> 验收标准未执行；本报告仅定义可验证行为。

## 4. 领域与数据影响

- 无新对象/关系/状态；新增的是既有对象（Resource/Interface/IPAddress）的导入入口与跨对象写入组合。
- 唯一性/完整性复用既有规则（§4.1/§10/§11/§13/§14/§21）；不因导入放宽。
- 新增关键约束：Resource+Interface+IPAddress 跨对象整批原子性（写入需求 §24.1 与验收 T68）。

## 5. Blocking Questions

无。BQ1–BQ7 已由用户 CONFIRMED；新模板三元组均必填（设计层默认）。

## 6. 受影响 Feature 与承接

F004/F007/F008/F009/F010/F014 为复用对象，不改写交付历史；本变更由新 Feature **F023** 承接。