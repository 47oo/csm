# F027 服务端访问范围强制执行 — Product

- Feature：F027（P0，M18）；状态：READY FOR ARCHITECT
- 需求：requirements revision 11 §23.2、§5–§7、§10–§24.3、§25、§27、§28、§31 T85–T89/T91/T93–T95/T97–T98、§32–§33
- 依据：CHG-010；plan revision 14；F026 product/architecture/Contract；F013/F018、F014/F023、F019/F022、F025 契约
- 依赖：F026 DONE

## 1. 目标与边界

把 F026 的 `AccessScope` 施加到全部既有业务读写路径，使非 ADMIN 只能访问已授权 Cluster 内对象。

| 项 | F026（DONE） | F027 | F028 |
| --- | --- | --- | --- |
| 授权事实/管理 | 交付 | 只消费 | 不新增 |
| 业务端点范围 | 不施加 | 全部读写/聚合/搜索/Dashboard/导入一次性接入 | 端到端验收 |
| 证据 | 基座 | 真实 PG 集成测试 | 真实 Compose、T85–T99、关键回归 |

**不做**：新 Schema/迁移、新端点/参数/权限项、资源实例级授权、改角色矩阵、改模板/列集/导入事务、新增前端功能。

## 2. 业务规则（§23.2 CONFIRMED）

- 有效权限 = 角色矩阵 ∩ 对象所属 Cluster 在授权集合内；只收紧，不放宽完整性/唯一性/软删/状态/关系约束。
- ADMIN 不受限；非 ADMIN 零授权默认拒绝；API Key 继承绑定账号；逐请求解析、不缓存、下一请求即时生效。
- 列表/`total`/分页/过滤同谓词；未授权 Cluster 的过滤值返回空 200；不出现“空页但 total>0”。
- 详情/Activity/写路径：未授权对象 404，不返回对象字段；请求体显式引用未授权/不可选 Cluster 或父对象 422；错误顺序 401→403→422→404→409。
- 跨对象归属：Pool←Network；Interface/Service←Resource；Endpoint←Service（IP 同 Cluster）；IP←自身 cluster_id（=Network.cluster）；未绑定 IP 仍按 Cluster；父级不可见则子对象不可见。
- 搜索：4 类候选 + F018 关联行 + related_total + total 全部按范围；匹配/去重/排序/分页/字段组合不变。
- Dashboard：counts、networks、容量仅可见 Cluster；零授权全 0/空且 200；公式不变。
- 导入：预校验与写入按行范围校验，行号+字段+原因；存在范围外行整批失败、无残留；模板/上限/两步流程不变；`--push` 同口径。
- Activity 按范围收敛；非 ADMIN 已删对象仍 403；完整 Audit 仍仅 ADMIN。
- 被拒绝写操作不产生业务变更/Audit/Activity；范围校验先于唯一性/重叠/引用检查，避免通过 409 泄露。
- 响应/计数/搜索/错误/导入错误不得泄露未授权 Cluster 的 code/name/id/状态/规模。
- 全部路径在同一次合并内整体受限，不得部分端点仍全局可见。

## 3. Q1 裁定（非 ADMIN 创建 Cluster）

**结论：维持既有已确认 §23 / F003 / T25 行为（EDITOR 可创建 Cluster）。** 本 Feature 不新增角色限制，不重开 F003 契约。新 Cluster 不自动授予非 ADMIN（§23.2）；创建者的 code 唯一性 409 属既有唯一性反馈，错误仅返回 `field:"code"`，不回显其他 Cluster 的 code/name/状态/规模。该窄例外记录于 Contract；若未来要求“仅 ADMIN 创建 Cluster”，按变更控制单独裁定。

## 4. 验收（待执行，不预设 PASS）

映射 T85–T89、T91、T93–T95、T97–T98；F028 承接真实 Compose 端到端与前端表现。

- A1 ADMIN 全业务域不受限，既有行为无回归（T97）。
- A2 仅授权 A/B 的非 ADMIN 在 8 类对象列表与聚合视图只看到 A/B（T87）。
- A3 items/total/分页/过滤一致；无空页 total>0；C 的过滤值为空 200（T87）。
- A4 对 C 的对象详情/Activity 404，无字段泄露（T85）。
- A5 对 C 的创建/修改/删除/释放/恢复/分配/绑定/解绑/转移被拒，无残留（T86）。
- A6 跨对象父级派生/未绑定 IP 按归属收敛（T85/T86）。
- A7 搜索 4 类 + 关联行 + related_total + total 收敛，匹配/排序/分页不变（T88/T53）。
- A8 Dashboard counts/networks/容量收敛；零授权全 0/空 200（T88/T93）。
- A9 Activity 未授权 404；完整 Audit 非 ADMIN 403（T85/T98）。
- A10 零授权列表空/详情写拒绝，不回退全量（T93）。
- A11 撤销/角色变更下一请求即时（含 API Key），同请求稳定（T91）。
- A12 API Key 继承范围；401 先于 403 等不回归（T94）。
- A13 INACTIVE 不改变授权；软删不生效、恢复自动恢复（T95）。
- A14 非 ADMIN 已删对象仍 403；ADMIN 不变（T98）。
- A15 F014/F023 预校验/写入未授权行级错误、整批失败无残留（T89）。
- A16 `--push` 同口径，预校验阶段失败（T89/T94）。
- A17 错误顺序 401→403→422→404→409；路径 404、body Cluster 422、角色 403（T85/T86/T97）。
- A18 不泄露未授权 Cluster 信息（T87/T88）。
- A19 拒绝写无状态/关联/版本/Audit/Activity 变化；事务边界不变（T86/T89/T97）。
- A20 全部路径一次合并整体受限，无部分端点中间态。
- A21 既有角色矩阵与完整性不回归（T01–T84 适用子集；T25/T43/T57 等）（T97）。
- A22 F026 授权管理行为不变（T90/T92/T96/T99）。
- A23 既有页面正确呈现空态/404/错误，不新增功能（F028 核对）。

## 5. 未决与非阻塞

- Blocking：None（Q1 按 §3 维持既有行为）。
- N1：F019 接口侧逐条绑定按“单请求”理解，未授权条目 404，其它条目不受影响；导入是单请求整批事务，整批失败。
- N2：F026 System 页“范围尚未生效”提示在 F027 合并后移除/更新。
- N3：F013 Dashboard counts 口径 errata；各域 Contract 增加范围交叉引用；F014/F023 行错误语义。
- N4：列表过滤未授权 Cluster → 空 200。
- N5：范围校验先于唯一性/重叠/引用检查。
- N6：无 Schema/索引变更；真实 PG 计划复核。
- N7：前端无新功能；既有页面表现归 F028。

**Status：READY FOR ARCHITECT**
