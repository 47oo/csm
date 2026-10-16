# F019 接口侧选择并绑定 IP — PRODUCT 阶段报告

- **状态**：READY FOR ARCHITECT
- **版本**：v1
- **上游依据**：`docs/product/requirements-v3.md` **revision 6** §13.4（含 §35.1 revision 6 确认记录）、§13.3、§14、§16、§21、§22、§23、§28、§31（T54–T58）；`docs/project/project-plan.yaml` revision 7（F019）；用户 2026-10-15 对 BQ1–BQ5 的裁定「按推荐执行」。
- **复用说明**：本报告复用 product-manager 2026-10-15 的 F019 需求澄清报告（原结论 `NOT READY FOR ARCHITECT`，阻塞项 BQ1–BQ5）。协调器核验条件：① 确认证据覆盖本 Feature 范围与验收（§13.4 + T54–T58）；② 实现基线无失效变化（Architect 轻量评估判定 database/backend/contract 均无变更）；③ 无未决业务问题（BQ1–BQ5 已 CONFIRMED）。故产品阶段判为复用完成，不重复调用该角色。

---

## 1. 目标与范围

在 Interface 创建成功后，允许用户在该 Interface 的视图内（Resource Detail 的 Interfaces 区域 / 接口列表）直接选择 IP 地址并绑定，减少在接口页面与 IP 页面之间跳转。

范围内（CONFIRMED，requirements §13.4）：
- 候选集合仅「与 Interface 所属 Resource 同 Cluster、当前未绑定任何 Interface（`interface` 为空）且未删除」的 IPAddress。
- 绑定时点为 Interface 创建成功后在接口视图中就地进行；不在创建表单内预先选择，不把 Interface 创建与 IP 绑定合并为同一操作。
- 仅绑定已存在的未绑定 IP；不在该流程内手动输入新 IP 或发起自动分配。
- 一次可选择多个候选；绑定逐条提交，允许部分成功，界面逐条呈现成功与失败及原因，不静默重试、不静默覆盖。
- 绑定仍按 §23 需 `WRITE`；同 Cluster（§14）、未删除唯一性、Endpoint 引用检查（§16 / §21）与软删口径不因入口方向改变。
- 绑定只编辑 Interface 关系，不改变 IP 的占用、`address` 与 Network。

## 2. 明确不做（CONFIRMED，requirements §13.4）

- 不提供从接口侧解绑或转移到其它 Interface；解绑 / 转移仍从 IP 侧发起（§13.3）。
- 不在该流程内手动输入新 IP 或自动分配（分配入口仍为 §13.1 / §13.2）。
- 不显示跨 Cluster IP，不显示已绑定到其它 Interface 的 IP，不显示已删除 IP。
- 不新增实体、关系、状态、权限或错误码。

## 3. 验收标准（映射 T54–T58）

| # | 用户可观察行为 | 映射 |
| --- | --- | --- |
| AC1 | 接口创建成功后，接口侧候选仅包含同 Cluster、未绑定（`interface` 为空）且未删除的 IP；跨 Cluster / 已绑定 / 已删 IP 不出现 | T54 |
| AC2 | 多选候选并提交后，各 IP 的绑定关系与提交一致，且各产生 UPDATE Audit | T55 |
| AC3 | 批量部分失败时逐条呈现成功项与失败项及原因；部分成功不显示为整体成功，不静默重试 | T55 |
| AC4 | 候选为空显示明确空状态；候选加载失败可重试且不伪装为空列表；超出单页上限显式提示，不静默截断 | T56 |
| AC5 | VIEWER 不显示绑定入口，直接调用绑定仍被服务端拒绝；绑定不改变 IP 占用 / `address` / Network，且不触发 Endpoint 引用拒绝 | T57 |
| AC6 | 接口侧流程仅绑定：不提供手动输入新 IP、自动分配、接口侧解绑 / 转移；并发绑定同一候选不产生重复绑定，后到者 409 VERSION_CONFLICT | T58 |
| AC7 | 接口创建失败不产生任何绑定；创建成功而绑定失败时 Interface 保留并明确提示绑定失败 | §13.4 |

> 验收标准未执行；本报告仅定义可验证行为。

## 4. 领域与数据影响

- 不新增实体 / 关系 / 状态 / 唯一性规则 / 生命周期行为。
- 复用既有关系：Resource 1:N Interface、Interface 1:N IPAddress（`interface_id` 可空）、IPAddress 绑定约束 `IPAddress.cluster == Interface.Resource.cluster`（§14）。
- 绑定操作产生 `ip_address` 的 UPDATE Audit（§22），与发起入口无关。

## 5. Blocking Questions

无。§35.2 六项业务决策均已关闭；BQ1–BQ5 已由用户 CONFIRMED。

## 6. 受影响 Feature 与承接

- F007（Interface，DONE）/ F010（IP Address，DONE）/ F013（Resource Detail 聚合展示，DONE）为复用对象，不改写其交付历史。
- 本变更由新 Feature **F019** 承接。