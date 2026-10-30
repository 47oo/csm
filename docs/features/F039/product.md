# F039 Dashboard 容量查询批量化与查询计数基准（R10）— PRODUCT 阶段报告

- **状态**：READY FOR ARCHITECT
- **版本**：v1（2026-10-29）；FEATURE / P2 / M30 非功能改进；分支 `feature/F039-dashboard-queries`，交付线 `v3.4`，start_commit `f66d1f33eb95fd54504e6c600ad32e7bc89ad9bd`；plan revision 25；requirements revision 16
- **角色产物**：product-manager 只读产出，协调器持久化
- **Basis**：AQ-5 = A（纳入 R10）；requirements revision 16 §20（容量公式 CONFIRMED）/ §23.2 / §31 T32、T88 / §32；`docs/api/F013.md` §3.3（实现复用 `ip_capacity.py` 的 `network_capacity`/`auto_pools_capacity`，不自行重算）/ §3.5；`backend/app/services/dashboard.py`、`backend/app/services/ip_capacity.py`；`/tmp/csm-review-2026-10-29.md` §R10（静态路径分析）；plan F039（`layers={database:false,backend:true,frontend:false}`、`api_required=false`、`depends_on` F010/F013/F027 均 DONE）

## 1. 性质：非功能改进，零业务规则变更

目标：消除 Dashboard 聚合路径随网络数/AUTO 池数线性增长的显式查询，并留下可重复的查询计数与规模基准证据。可观察行为**零差异**（响应字段与取值、§20 容量口径、范围过滤、分页、权限、错误码逐字不变）；允许改变的只有该请求发出的显式 SQL 查询次数与其组织方式。需求正文零变更；契约零 diff（唯一例外：Architect 判定需 §3.3 澄清附注）。

## 2. 事实基础（代码事实 + 静态估算）

- `dashboard.py` 对分页返回的每个 Network 逐个调用 `ip_capacity.network_capacity` 与 `auto_pools_capacity`。
- `ip_capacity.py` 中 `network_allocatable_intervals` 每次重新查询 RESERVED 池区间（`:139` 附近）；`auto_pools_capacity` 重复该查询（`:151` 附近）并对每个 AUTO 池各发一次占用计数。
- 每请求约 `8 + 4×网络数 + AUTO池数` 次显式查询（静态估算，不含认证/范围解析/ORM 附带行为）。
- **未做真实性能测试**，无耗时数据；只引用「查询次数」这一可计数事实，**不得表述为已测得慢查询**。
- 无索引/Schema/Migration 影响；如需新索引另走 DATABASE Gate。

## 3. 领域影响

Network / IPPool / IPAddress 的只读容量聚合视图：无新增/变更关系；§23.2 可见集群口径不变；不涉创建/变更/删除；依据 §20、§23.2、F013 §3.3（CONFIRMED）；无未决问题（仅改取数组织方式）。

## 4. 验收标准（A1–A8）

| ID | 断言 |
| --- | --- |
| A1 | 查询计数有界：`before_cursor_execute` 计数 SELECT，真实 PG 上 N=1/10/50 Network 时聚合查询次数为同一常数上界，不随网络数或 AUTO 池数线性增长；start_commit 同法基线作为对照入库 |
| A2 | §20 容量口径逐项不变（T32）：`allocatable_total`/`occupied`/`remaining` 与 `GET /networks/{id}/capacity` 逐项一致；gateway、RESERVED 范围、禁用地址去重（gateway∩RESERVED 不重复扣减）、未绑定 IP 计占用、池外手动 IP 计 Network 占用、AUTO 池 `|池范围 ∩ 可分配集合|`、池占用按当前地址而非分配来源、INACTIVE 不清零，全部不变 |
| A3 | §23.2 范围与零授权行为不变（T88）：非 ADMIN 仅见授权集群计数与网络行，未授权不出现且 `total`/计数不泄露规模；零授权返回 0 与空 `networks`；ADMIN 不受限 |
| A4 | 负 `remaining` 语义不变：可构造负值时原样返回，不截断、不下限 0 |
| A5 | 响应面零变更：字段名/类型、`networks.items` 顺序与分页、`counts` 全局口径、端点、`401→403→422→200` 顺序、错误码与 `reason` 全零 diff |
| A6 | 既有回归全绿：`backend/tests/integration/test_dashboard.py` 及其它 Dashboard / F010 容量相关套件无回归 |
| A7 | Dashboard 页面无回归（响应不变前提下渲染无变化）；`frontend/` 零 diff |
| A8 | 证据入库：查询计数断言（含 N=1/10/50 常数上界、新查询命中原有索引的 `EXPLAIN`、无顺序扫描退化说明）、规模基准脚本与实测值、可重复命令，落 `docs/features/F039/**`；`ip_capacity.py` 仍为公式单点（薄包装）并有代码与断言证据 |

不在验收范围：容量定义/统计口径变化、缓存、索引与 Schema 变更、F045 整体验收。

## 5. 明确不做

N1 不改 §20 公式、不新增统计口径、不改 gateway/RESERVED/禁用地址/AUTO 交集判定。N2 不复制公式（`network_capacity`/`auto_pools_capacity` 保持公式单点，可作薄包装；绕过或改写须先出 F013 §3.3 澄清附注并经 Architect 签核）。N3 不改响应字段/分页/权限/错误码/reason/端点。N4 不引入缓存基础设施。N5 不新增索引与 Schema/Migration。N6 不改 `docs/api/F013.md`（除 Architect 判定的澄清附注）、不改 `frontend/`、不回填 F010/F013/F027 的 DONE 证据。N7 不把「未测得耗时」写成「已优化/已修复慢查询」。

## 6. Blocking Questions

**无。** 目标由已确认的 §20 / §23.2 / T32 / T88 与 F013 §3.3 完全确定；AQ-5=A 已锁定范围；无新对象/状态/权限冲突；残留选择均为技术设计（§7）。

## 7. Non-blocking 观察（交 Architect）

| ID | 观察 |
| --- | --- |
| ON-1 | 批量化形态：保留 `network_capacity`/`auto_pools_capacity` 为薄包装（推荐，零契约影响）vs 新增批量入口（须出 F013 §3.3 澄清附注）；均不得复制公式 |
| ON-2 | 查询计数实现：参考 `test_search_related_tester_acceptance.py` 的 `before_cursor_execute`（含 `event.remove` 清理）；须定义计数范围（是否排除认证/范围解析/BEGIN）与「常数上界」具体值 |
| ON-3 | 代表性规模：N=1/10/50 的 Network 构造、每网络 AUTO 池数与 IP 占用量分布、基准是否需独立脚本与固定种子 |
| ON-4 | 批量加载后占用计数等价实现（按区间聚合 vs 逐池计数）须逐项保持 A2/A4 且不引入顺序扫描退化，须给 `EXPLAIN` 证据 |
| ON-5 | 基线先行：先记录 start_commit 的查询计数与规模曲线，再改实现同法复测；不得用估算值充当实测 |

## 8. 文档更新建议

需求 / 领域模型 / `docs/database/*` 零变更；`docs/api/F013.md` 默认零 diff（仅在 Architect 判定需澄清批量化入口时追加附注）。
