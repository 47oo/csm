# F005 BareMetal 硬件与容量 — PRODUCT 阶段报告

- **Feature**：F005 BareMetal 硬件与容量（FEATURE，P0，M2，deps [F004]）
- **阶段**：PRODUCT；**结论**：`READY FOR ARCHITECT`（2026-10-08）
- **依据**：requirements-v3.md revision 3（§4.1、§8、§18、§21、§27、§31 T38/T39、§35）；plan_revision 4 F005 条目（用户 2026-10-06 批准）；d01-conventions.md v3；Product Manager 阶段交接（协调器核验后持久化）。

## 确认条款

§8 硬件字段/可空/未知 null/SN 无全局唯一/数值定义表、§4.1 默认与省略语义、§18 Hardware 展示、§21 明细跟随 Resource 生命周期、§26/§27 结构化 vs JSONB 与完整性、§31 T38/T39、§35.2 Q10-A 均 CONFIRMED。无 Blocking Questions；D01（字段格式/存储上限/JSONB 结构）为设计输入，非产品待决。

## 必须遵守的已确认约束

- 硬件字段（§8）：manufacturer、model、serial_number、cpu_model、cpu_sockets、cpu_cores、memory_mb、gpu_model、gpu_count；公共属性在 Resource 不重复。
- 可空与未知值（§8/§4.1）：均可空；未知存 null 不以 0 表示；默认仅创建省略时生效；PATCH 省略=保持；显式 null 仅清空 nullable，对非 nullable 显式 null→422。
- 数值合法值（§8）：cpu_sockets 正整数或 null；cpu_cores 整机物理核心总数不含超线程、正整数或 null；memory_mb 单位 MiB、正整数或 null；gpu_count 非负整数或 null，0 表示明确无 GPU。
- 单位（§8/d01 v3 §3）：MiB/GiB，1 GiB=1024 MiB，不混用 MB/GB；界面/导入显式标注。
- 存储（§8/§26）：常查询/排序/统计数据结构化；厂商特有或低频可用 JSONB；列级方案交 DATABASE。
- SN 一期不设全局唯一（§8/Q10）。
- 生命周期（§21）：BareMetalDetail 跟随 Resource 生命周期，无独立删除/恢复入口，不作为阻止 Resource 删除的独立子对象。
- 展示（§18）：Hardware 区域显示 CPU/Memory/GPU/Manufacturer/Model/SN。
- 完整性（§27）：DB 与业务层共同保证，真实 PostgreSQL 验证。
- 权限/审计（§22/§23）：硬件随 Resource 编辑（EDITOR），删除/恢复随 Resource（ADMIN）；变更写 Audit。

## 可观察验收标准

| # | 标准 | 映射 |
| --- | --- | --- |
| A1 | 硬件字段省略/null 保存 null 并在详情返回 null 不返回 0 | §8、T38 |
| A2 | gpu_count=0 接受并存 0，展示"明确无 GPU"，与未知 null 可区分 | §8、T38 |
| A3 | cpu_sockets/cpu_cores/memory_mb 为 0 或负数被拒 422；gpu_count 负数被拒；正整数/非负整数按 §8 接受 | §8、T38 |
| A4 | memory_mb 以 MiB 存/展示：1536 GiB→1572864，转换一致，不按 MB 解释 | §8、T38、d01 §3 |
| A5 | cpu_cores 整机物理核心不含超线程：2×EPYC 192 物理核→192（非 384）；不自动探测，只按人工登记校验 | §8、T39 |
| A6 | 相同 serial_number 可登记，无唯一冲突 | §8、Q10 |
| A7 | Detail Hardware 区域显示 CPU/Memory/GPU/Manufacturer/Model/SN | §18 |
| A8 | 硬件创建/修改变更进 Audit；权限 §23（EDITOR 可改，VIEWER 只读） | §22、§23 |
| A9 | BareMetalDetail 无独立删除/恢复入口；删除/恢复只作用于 Resource，明细跟随且不阻止 Resource 删除 | §21、T23 |
| A10 | 结构化字段可查询/排序/统计；厂商特有/低频入 JSONB 不破坏结构化查询 | §8、§26 |

## 边界（不宣称）

VM 容量与 Host 校验（F006）；完整 T37/T38/T39（T37 默认值随 F004、T39 VM 侧随 F006，本 Feature 只承载硬件侧）；CSV/Excel 导入（F014）；列表/统计页面与 Dashboard（F013）；全局搜索 SN/MAC/GPU Model（后续扩展 §17）。

## 结论与下一步

无 Blocking Questions，无待用户裁定事项。下一步：ARCHITECTURE Gate——BareMetalDetail 方案、layers、api_required，并在 CONTRACT 签核 D01 本域字段契约（数值范围/单位/JSONB metadata）。
