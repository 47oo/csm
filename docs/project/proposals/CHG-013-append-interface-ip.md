# CHG-013 向既有 Resource 追加 Interface / IP 导入

- **状态**：READY FOR PLAN APPROVAL（需求内容待用户裁定 CHG013-BQ01–BQ08；候选计划 revision 21 尚未批准）
- **来源**：用户 2026-10-26 提出「自己提交 csv 格式的数据可能遇见这类情况，同一个机器有多个 IP 的情况，这种情况也允许录入」，并给出同一 hostname `luck` 的三行 26 列 CSV（`eth0/10.10.10.23`、`eth6/192.168.10.221`、`eth4/10.100.24.88`）。
- **影响对象**：`docs/product/requirements-v3.md` revision 13 → 14（拟新增 §24.6、T117–T126，修订 §24 / §31 T67、T71）；`docs/api/F023.md` v1 → v2（正文升版，替代 §11/§13 负面边界与 §8.1/`created` 口径）；新 Feature **F035**；F023 已 DONE 的交付行为由 F035 承接，**不回写**其历史证据。
- **不改动**：26 列模板与列序、端点与方法、错误码与 `reason` 集合、两步流程、行号口径、5 MiB / 5000 行上限、`IMPORT` 权限矩阵与 §23.2 集群范围、每新建对象 CREATE Audit、软删/恢复规则、F014 资源导入（BM 14 / VM 10 模板）行为、采集脚本 F024/F032、数据库 Schema。
- **角色输入**：Product Manager 需求澄清（含 BQ1–BQ4 与 T117–T126 草案）、Architect 轻量全局评估（`ARCHITECTURE ASSESSMENT COMPLETE`，含 OPEN-P1–P6）、Project Manager 能力拆分与候选计划 revision 21。

---

## 0. 协调器实测证据（裁定依据，2026-10-26，测试环境 `http://localhost:18080` 集群 `N96P`）

将用户三行样本文本以 F034 粘贴载体提交 `POST /api/v1/imports/resource-interfaces-ips/validate`：

```
total_rows=3, importable_rows=0, error_count=6
row2 ip       : ip is not allocatable in the resolved network (...)
row2 hostname : hostname already exists in this cluster
row3 hostname : hostname already exists in this cluster
row3 ip       : ip already exists in this cluster
row4 ip       : ip is not allocatable in the resolved network (...)
row4 hostname : hostname already exists in this cluster
```

集群现状：Resource `luck` **已存在**（BARE_METAL / ALLOC），已有 1 个 Interface `eth6`（mac `d8:b3:2f:5f:a8:1f`）与 1 个 IP `192.168.10.221`；Network 仅有 `TEST = 192.168.10.0/24`、`TESTNET = 10.100.24.0/24`（无 `10.10.10.0/24`）。

**归因（6 条错误全部闭合）**：

| 错误 | 根因 | 归类 |
| --- | --- | --- |
| 3 条 `hostname already exists` | Resource `luck` 已存在；`docs/api/F023.md` §11/§13 明确「不向既有 Resource 追加」 | **本次新需求**（唯一真实缺口） |
| 1 条 `ip already exists` | `192.168.10.221` 早前已导入 | 既有口径（BQ-3 需裁定是否保持） |
| 2 条 `ip not allocatable` | 三行都把 `network` 写成 `TEST`（=192.168.10.0/24），但 IP 属其它网段；`network` 非空即以显式引用解析、不回退 `/mask` | **数据填写问题**（行为正确） |

**关键结论**：用户字面诉求「同机多 IP」在**首次新建**路径**已经支持**（§24.1：同 hostname 多行合并为一个 Resource、每行一个 Interface + IP；T64/T66 已覆盖，实测 `eth6` + `192.168.10.221` 即由该路径写入）。真正缺口是**向已存在的 Resource 追加 Interface/IP**。

---

## 1. BQ-1 目标能力范围

| 选项 | 内容 |
| --- | --- |
| A | 仅澄清用法，不改系统（告知「多 IP 需在同一批首次导入中提供」；既有 Resource 请用单对象入口逐条补录） |
| **B（推荐）** | 允许向既有 Resource 追加 Interface/IP，**且不修改既有 Resource 的任何字段**、不覆盖既有 Interface/IP |
| C | B + 追加时同时更新既有 Resource 的 Resource 级字段（等同按 hostname 更新，需版本冲突检查与 UPDATE Audit） |

**推荐 B 的依据**：①与实测阻塞点一一对应；②「只新增子对象、不动既有对象字段」不构成 §24 所禁止的「自动更新或覆盖现有资源」；③C 直接推翻 §24 已确认条款且显著扩大范围（版本冲突 + UPDATE Audit），应另立提案。

**待裁定者**：用户（范围决策）。

---

## 2. BQ-2 追加行 Resource 级列语义

26 列模板中 `resource_type`/`role`/`status`/`host`/`vcpu`/`memory_mb`/`disk_gb`/`hypervisor`/硬件 8 列为 Resource 级字段。追加方（尤其采集脚本产出）可能整行照抄。

| 选项 | 内容 |
| --- | --- |
| A | 追加行 Resource 级列**必须留空**，填了即行错误 |
| **B（推荐）** | 可填，但**必须与现存规范化值完全一致**；任何差异（含「现存 null 而 CSV 有值」）→ 行错误，不覆盖 |
| C | 允许用 CSV 补齐现存为 null 的字段（= 修改既有 Resource，需 UPDATE Audit） |
| D | 允许覆盖（等同推翻 §24 基线） |

**推荐 B 的依据**：保持「导入只新增、不改既有对象」，与 §24 一致。副作用：既有硬件字段为 null 时无法经导入补填，只能走 Resource 编辑（见 BQ-7）。

---

## 3. BQ-3 重复提交与已存在子对象

| 选项 | 内容 |
| --- | --- |
| **A（推荐）** | 维持报错：既有 Interface 名、同 Cluster 既有 IP 一律行错误（现状口径） |
| B | 完全相同即幂等跳过，以「跳过计数」呈现，不视为错误 |
| C | 仅 Interface/IP 存在即跳过，但 IP 已绑定其它 Interface 或属性不同仍报错（需定义「完全相同」判据） |

**推荐 A 的依据**：零新增规则、不触碰原子性与结果语义；B/C 需额外定义比较字段集（mac/mtu/enabled/speed/network/掩码）与新结果呈现，风险高于收益。

---

## 4. BQ-4 一致性范围

| 选项 | 内容 |
| --- | --- |
| **A（推荐）** | 仅「资源+网卡+IP」导入（F023）允许追加；资源导入（F014，不含 Interface/IP）维持「冲突即报错」，并在界面文案说明差异 |
| B | 两入口同步放宽（F014 模板不含 Interface/IP，追加只剩「无写入的复用」，业务价值低且需改动已冻结基线） |
| C | 两入口都维持现状（= BQ-1 选 A） |

---

## 5. BQ-5 同一网卡多 IP

**背景**（Architect OPEN-P3，用户真实场景关键）：BQ-1=B + BQ-3=A 下，**既有 Interface 不能接收新 IP**（同批次新建的 Interface 才可多 IP）。若用户「同机多 IP」实际指「同一张网卡配多个地址」（如 `eth6` 再加一个 IP），当前推荐组合**不满足**该场景。

| 选项 | 内容 |
| --- | --- |
| **A（推荐，范围最小）** | 不允许向既有 Interface 追加 IP；同一网卡多地址请在同一批首次导入中提供，或经 IP 侧单对象入口绑定 |
| B | 允许：追加行 `name` 命中既有未软删 Interface 时，把该行 IP 绑定到既有 Interface（需新增「同资源同名 Interface 已存在」的语义：由「错误」改为「复用宿主」） |

**推荐 A 的理由**：B 需要额外规则（何时复用、何时报错、与 BQ-3 的关系、并发语义），且会把 F023 §13 的负面边界扩大解释；若用户真实场景是「一张网卡多个地址」，应明确选 B 并由 Architect 补充设计。

---

## 6. BQ-6 响应计数口径

现 `docs/api/F023.md` §4：`created` = 新建 Resource 数；`interfaces_created` / `ip_addresses_created` = 新建子对象数；`total_rows == ip_addresses_created`。

| 选项 | 内容 |
| --- | --- |
| **C1（推荐）** | `created` 保持「新建 Resource 数」，纯追加批次为 **0**；不新增字段 |
| C3 | 新增响应字段（如 `resources_reused`），`created` 仍按 C1 |

**推荐 C1**：零响应 Schema 变更；代价是「批次成功但 `created=0`」，前端文案需说明「新建资源 N 个、追加到既有资源 M 个」（M 由前端按行推导或暂不展示）。C3 属**新增响应字段**，需用户批准。

---

## 7. BQ-7 留空列语义

| 选项 | 内容 |
| --- | --- |
| **A（推荐）** | 追加行中留空的 Resource 级列视为**中性、不参与比较**（沿用「空=省略」既有口径） |
| B | 留空亦须与现存值一致（留空视为 null）——除未知字段外几乎无法追加，且与 §8.2「均省略→默认」冲突 |

**关联说明（Architect OPEN-P2）**：因 BQ-2=B，既有值为 `NULL` 的列**不能**经导入补填，只能走 Resource 编辑；此项属预期行为，请在批准时确认可接受。

---

## 8. BQ-8 重复提交可用路径

**背景**（PM 核对新发现，必须让用户知情）：在 BQ-1=B + BQ-3=A + 整批原子回滚之下，用户实测的「把同一批 3 行再提交一次」**仍会整批失败**（既有 `eth6`/`192.168.10.221` 冲突）。可用路径是「CSV 只含新增行」。

| 选项 | 内容 |
| --- | --- |
| **A（推荐）** | 接受「只提交新增行」为唯一可用路径，并在 §24.6 与前端文案明写该约束 |
| B | 要求重复行自动忽略（= BQ-3 选 B），或要求部分成功（违反整批原子性，会成为独立变更） |

---

## 9. 需求正文差异（PROPOSED，裁定后落稿）

| 位置 | 差异 | 前置 |
| --- | --- | --- |
| 新增 **§24.6 向既有 Resource 追加 Interface / IPAddress（revision 14）** | 适用入口与载体（含 §24.5 文本载体）；组键 `(cluster, hostname)` **已存在则复用为宿主**；Resource 级列一致性（BQ-2）；既有子对象口径（BQ-3）；同 NIC 多 IP（BQ-5）；响应计数（BQ-6）；留空语义（BQ-7）；仍整批原子回滚、同一 Service Layer、同一错误/行号口径；每新建子对象各写 CREATE Audit，既有 Resource 不写 UPDATE Audit；权限与集群范围不变；明确不做：修改既有 Resource 字段、按 hostname 通用更新、删除/覆盖既有子对象、创建 Network/Host/Cluster/Pool、触发自动分配 | BQ-1=B |
| §24 首段 | 「不按 hostname 自动更新或覆盖现有资源」→ 补限定：「**不更新或覆盖既有 Resource 字段与既有子对象**；允许在同一批次内向既有 Resource 新增 Interface/IP（§24.6）」 | BQ-1=B |
| §24.1「明确边界」 | 增加指向 §24.6 的引用（不改冻结基线 bullet） | BQ-1=B |
| §24.5 | 「不用文本更新或覆盖现存对象」补一句：「不更新既有对象**字段**；按 §24.6 新增子对象不在此限」 | BQ-1=B |
| **§31 T67（必改）** | 「同 Cluster hostname 现存」不再报错；改为「同资源 interface name / 同 Cluster IP 的现存重复仍报错；`(cluster,hostname)` 现存按 §24.6 追加」 | BQ-1=B |
| §31 T71 | 注明「追加不新建 Resource，故不产生 hostname 唯一性判定」 | BQ-1=B |
| §31 新增 | **T117–T126**（追加成功/既有零变化/Resource 级列不一致/既有子对象报错/Interface 与 IP 口径沿用/混合批次原子/权限与范围/无 UPDATE Audit/软删视为不存在/F014 与文本载体零回归） | 裁定后 |
| §32 | 上线验收追加一句「导入支持向已存在 Resource 追加 Interface/IP，且不修改既有 Resource 字段」 | BQ-1=B |
| §35.1 / §36 / domain-model | 新增 revision 14 确认记录（用户原文 + BQ 裁定组合）、基线更新、§24.6 索引 | 裁定后 |

## 10. 契约变更（Architect 专业签核，不在本次批准范围逐份审批）

`docs/api/F023.md` **v1 → v2（正文升版，不使用增补节）**：因 BQ-1=B 直接否定现文 §13「不向既有 Resource 追加 Interface/IP」、§11「现存 `(cluster,hostname)` → 行错误 `field="hostname"`」、§8.1 组键→Resource 单一语义与 §4 `created` 口径、§12.3 锁集合，增补节会与正文并存矛盾。v2 须列出被替代条款（显式替代关系）、版本历史、签核记录与上游 revision。

Architect 评估已明确的技术前提（专业签核范围，不改业务边界）：方案采用「改造现有写入路径」（组键不存在→新建、存在→复用为宿主），零新增端点；既有 Resource 并入 `resources` 预锁名单（同表同序、SAVEPOINT 外取齐），锁序仍 `resources → networks`；追加组不执行任何 `UPDATE`、不写 UPDATE Audit；预校验新增只读检查（既有 Resource 内未软删同名 Interface）；`layers = {database: false, backend: true, frontend: true}`、`api_required: true`（仅 F023 正文升版）。

---

## 11. 影响评估

| 对象 | 状态 | 影响 | 处置 |
| --- | --- | --- | --- |
| **F023** 资源+网卡+IP 导入 | DONE | 重影响：§4 计数、§8.1 组键语义、§11 冲突口径、§12 锁集合、§13 边界 | 由 **F035** 承接；F023 只做契约升版与勘误，历史证据不改写 |
| **F014** 资源导入 | DONE | BQ-4=A 下零改动（仅界面文案说明差异） | 零改动 + 回归 |
| **F007 / F010** Interface / IPAddress 单对象 API | DONE | 追加复用既有 `prepare_/stage_` 核心，语义不变 | 零改动 + 回归 |
| **F034** 文本载体 | DONE | 载体零 diff；若 C3 则新增响应字段（需批准） | C1 下零改动 |
| **F024 / F032** 采集脚本 | DONE | 全量 `--push` 在目标已存在时的错误形态由 hostname 变为 ip/name（BQ-3=A） | 零 diff；F035 test-report 记录 |
| **F026–F028** 集群范围 | DONE | 追加行仍逐行范围校验，整批失败口径不变 | 零改动 + T89/T115 回归 |
| 已交付证据 | — | `backend/tests/integration/test_f023_resource_interface_ip_import.py`（existing hostname conflict 用例）、`frontend/scripts/smoke-client.mjs` 同口径断言需在 F035 内更新期望 | 记入 F035 交付，不改写 F023 证据 |

**风险**：①F023 证据不得改写；②§31 T67 与 F023 §11 必须与实现同批修订，否则留下两处矛盾正文；③契约必须升版并标注替代关系，不得静默改负面边界；④即使用户批准 BQ-1=B，其原始「重提整批」场景仍需改为只提交新增行（BQ-8）；⑤回归面较宽（F014/F023/F034/F027/F024/F032）。

---

## 12. 候选计划（revision 21）

文件：`docs/project/proposals/CHG-013-candidate-plan.yaml`（活动基线 `docs/project/project-plan.yaml` 未改动）。

| 字段 | 现值 | 候选 |
| --- | --- | --- |
| `project.plan_revision` | 20 | **21** |
| `project.requirements.revision` | 13 | **14**（待裁定后落稿） |
| `project.status` | DONE | DRAFT（批准后由协调器写 ACCEPTED） |
| `project.approval` | plan 20 / F001–F034 | null |
| `project.acceptance.status` | COMPLETE | PENDING（evidence 保留） |
| `features` | F001–F034 | + **F035**（DRAFT，P1，`M26 导入追加网卡/IP`，depends_on F023，blocking_decisions CHG013-BQ01–BQ08） |
| `pending_changes` | `[]` | `CHG-013` → affects F023, F035 |
| `decisions_required` | — | + CHG013-BQ01–BQ08（OPEN，owner 用户） |

---

## 13. 待批准与后续

批准后可进行：落稿需求 revision 14（§24.6 + T117–T126 + §24/§31/§32/§35.1/§36/domain-model）→ 应用候选计划 revision 21（项目 DONE → ACCEPTED、acceptance → PENDING、F035 纳入批准范围）→ 解除 CHG-013 暂停标记 → 校验并提交基线。

批准前不修改实现、不签核 F023 v2、不合并到 `v3.3`、不启动实施。
