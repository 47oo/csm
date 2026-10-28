# F035 向既有 Resource 追加 Interface/IP 导入 — PRODUCT 阶段报告

- **状态**：READY FOR ARCHITECT
- **版本**：v1（2026-10-26）
- **上游依据**：
  - `docs/product/requirements-v3.md` **revision 14**：**§24.6**（CONFIRMED，全节）、§24 / §24.1 / §24.5（经 §24.6 修订的措辞）、§11.1 / §13.2 / §14 / §21 / §22 / §23 / §23.2、§31 **T117–T126** 及修订后的 T67 / T71、§32、§35.1 revision 14 记录。
  - 用户裁定（CONFIRMED，`docs/project/project-plan.yaml` `decisions_required`）：**CHG013-BQ01=B**（允许向既有 Resource 追加 Interface/IP，且不修改既有 Resource 字段、不覆盖既有子对象）、**BQ02=B**（Resource 级列可填但须与既有规范化值一致，留空=省略不比较）、**BQ03=A**（既有同名 Interface / 同 Cluster 既有 IP 仍报错，不做幂等跳过）、**BQ04=A**（仅「资源+网卡+IP」入口支持追加；资源导入入口维持冲突即报错）、**BQ05=A**（不支持向既有 Interface 追加 IP）、**BQ06=C1**（`created` 仍为新建 Resource 数，纯追加为 0，不新增响应字段）、**BQ07=A**（留空=省略不比较）、**BQ08=A**（只提交新增行为补录既有机器的唯一可用路径，须在界面说明）。
  - 计划与授权：plan_revision 21、`project.approval`（用户 2026-10-26「按推荐执行」）、`execution.authorization.feature_ids=[F035]`；F035 `depends_on` F023（DONE）；分支 `feature/F035-append-interface-ip`，start_commit `76d8410`。
  - 提案与影响评估：`docs/project/proposals/CHG-013-append-interface-ip.md`（§0 实测证据、§1–§8 BQ、§11 影响评估）、Architect 轻量全局评估（2026-10-26，`ARCHITECTURE ASSESSMENT COMPLETE`）。
  - 既有基线：`docs/api/F023.md` v1（＋F027 范围语义与 CSV 文本载体两个增补节）、`docs/features/F023/*`（DONE，证据不改写）。
- **复用记录**：本阶段不重新调用 Product Manager。依据 `feature.md` §1 的复用条件，PM 2026-10-26 的澄清结论（缺口定位、能力清单、T117–T126 草案、影响评估、风险）已由用户裁定并在需求 revision 14 §24.6 落稿为 CONFIRMED 条款；依据版本与依赖此后无变化，无未决业务问题。

---

## 1. 目标与范围

F035 让维护人员能**给已经登记过的机器批量补网卡与 IP**，而不必逐条走单对象界面。

范围内（CONFIRMED，§24.6）：

1. **追加语义**：「资源+网卡+IP」导入（26 列宽模板、文件与粘贴文本两种载体）中，组键 `(cluster, hostname)` 已存在且未软删时不再报冲突，改为在该既有 Resource 下新建 Interface 与 IPAddress 并绑定；**不新建 Resource、不修改既有 Resource 任何字段、不覆盖既有 Interface/IP**。
2. **组级判定**：同 hostname 多行仍合并为一个组；追加按**组**判定，不存在同组内部分新建/部分追加。
3. **Resource 级列一致性**（BQ-2/7）：追加行的 Resource 级列可填，但须与既有规范化值完全一致；不一致或 `resource_type` 不匹配报行错误（`field`=对应列名）；留空列视为省略、不比较、不改既有值。
4. **既有子对象仍报错**（BQ-3）：既有未软删同名 Interface → `field="name"`；同 Cluster 既有 IP → `field="ip"`；不幂等跳过、无部分成功。
5. **不支持向既有 Interface 追加 IP**（BQ-5）：同一张网卡多地址须在同一批首次导入提供，或经 IP 侧绑定入口维护。
6. **计数口径**（BQ-6/C1）：`created` = 新建 Resource 数（纯追加批为 0）；`interfaces_created` / `ip_addresses_created` = 新建子对象数；`total_rows == ip_addresses_created`；不新增响应字段。
7. **可用路径约束**（BQ-8）：含已导入行的批次整批失败，补录时应只提交新增行——须在界面说明。
8. **保留既有口径**：两步流程、同一 Service Layer、1-based 行号与 `field`/`related_row`、整批原子回滚（新建组与追加组同事务）、`IMPORT` 权限与 §23.2 行级范围、每新建子对象一条 CREATE Audit（既有对象无 UPDATE Audit、`version`/`updated_at` 不变）、5 MiB / 5000 行上限、§11.1 地址边界、Network 必须已存在、不触发自动分配。

## 2. 明确不做

- 不更新/覆盖既有 Resource、Interface、IPAddress 的任何字段；不做按 hostname 的通用 upsert。
- 不做重复导入幂等忽略、不跳过已存在行、不提供部分成功。
- 不支持向既有 Interface 追加 IP；不支持跨 Cluster 追加；不复活软删 Resource。
- 不创建 Network / IP Pool / Cluster / Host / Service / Endpoint。
- 资源导入入口（F014，BM 14 / VM 10 列模板）**零改动**，对已存在 hostname 仍报冲突。
- 不新增端点、查询参数、权限项、模板列集与列序、错误码与 `reason` 取值、上限或配置项。
- 不改写 F023 已 DONE 的历史证据（含其 existing-hostname-conflict 用例与前端 smoke 断言），期望变化由 F035 交付记录承接。

## 3. 验收映射

| 验收 | 要点 |
| --- | --- |
| T117 | 纯新增行 + 已存在 hostname → 预校验 0 错误、写入成功；新 Interface/IP 归属既有 Resource 并绑定；Resource 总数不变 |
| T118 | 既有 Resource 零变化：字段、`version`、`updated_at`、既有子对象不变；无 `resource` UPDATE Audit；新增子对象各一条 CREATE Audit |
| T119 | Resource 级列不一致 / 类型不匹配 → 行错误（对应列名）并整批回滚；留空列不比较、不置空 |
| T120 | 既有同名 Interface → `name`；同 Cluster 既有 IP → `ip`；不跳过、无部分成功 |
| T121 | Interface 追加沿用既有规则（`interface_type` 空→OTHER、`enabled` 空→true、mac/speed/mtu、同资源 name 唯一、无 `parent_interface`） |
| T122 | IP 追加沿用既有规则（属 CIDR、§11.1 边界、非 gateway/RESERVED/禁用段、同 Cluster 唯一、绑定同 Cluster、手动分配、不触发自动分配） |
| T123 | 混合批次原子性；预校验后状态变化 → 422 `IMPORT_VALIDATION_FAILED`、零残留、不静默覆盖 |
| T124 | 计数口径（纯追加 `created=0`）与权限/范围口径（403 / 401 / 未授权集群行整批失败） |
| T125 | 软删 Resource 视为不存在；不创建其它对象；不支持向既有 Interface 追加 IP |
| T126 | 零回归：资源导入入口、F023 新建路径、T64–T72、T107–T116、T73–T84 / T100–T106、模板/端点/错误码/上限不变 |
| 回归 | T67 / T71（按 revision 14 修订后的措辞） |

## 4. 边界与风险（产品视角）

- 用户原始样本仍不会「一次通过」：`eth6`/`192.168.10.221` 已存在，含该行的批次按整批原子仍失败；且 `network=TEST` 与部分 IP 网段不符属数据填写问题（§9 口径：`network` 非空即权威）。界面须说明「只提交新增行」与 network/掩码用法。
- 既有值为 `null` 的 Resource 级列不能经导入补填（BQ-2=B 的预期副作用），只能走 Resource 编辑。
- 契约必须**正文升版**（现文 §13「不向既有 Resource 追加」、§11「hostname 冲突即报错」、§4 `created` 口径被替代），不得以增补节并存矛盾正文。

## 5. 未执行项

- 未运行任何测试或构建：本阶段只固化已确认规则。
- 技术方案（写入路径二态、锁集合、比较列集、契约形态）由 ARCHITECTURE Gate 决定。
