# F005 BareMetal 硬件与容量 — ARCHITECTURE 阶段报告

- **Task**：F005（FEATURE，P0，M2，deps [F004]）— Architect，Feature 设计模式
- **Status**：`READY FOR DESIGN`（2026-10-08；协调器核验后持久化）
- **Basis**：requirements-v3.md revision 3（§4.1、§6、§8、§18、§21、§26–§27、§31 T38/T39、§35.2 Q10-A、§35.3 D01/D02）；F005 product.md（A1–A10）；F004 architecture/api/F004/database/f004-resource；d01-conventions.md v3；plan_revision 4 F005 条目。
- **结论属性**：设计输入，交 DATABASE/TEST_DESIGN；Contract 草案供 CONTRACT 定稿。

## 1. 方案摘要

### 1.1 BareMetalDetail 实体（1:1 依附 Resource）

| 字段 | 类型 | 空 | 默认 | 说明 |
| --- | --- | --- | --- | --- |
| resource_id | UUID PK/FK→resources | 否 | — | 1:1；BARE_METAL 有且仅一行，VM 无行 |
| manufacturer | string | 是 | null | 厂商 |
| model | string | 是 | null | 型号 |
| serial_number | string | 是 | null | SN，一期无唯一约束（§8/Q10-A） |
| cpu_model | string | 是 | null | CPU 型号 |
| cpu_sockets | int | 是 | null | 插槽数，正整数 |
| cpu_cores | int | 是 | null | 整机物理核心总数，不含超线程，正整数 |
| memory_mb | int | 是 | null | 单位 MiB，正整数 |
| gpu_model | string | 是 | null | GPU 型号 |
| gpu_count | int | 是 | null | 非负整数；0=明确无 GPU，null=未知 |
| metadata | jsonb | 否 | {} | 厂商特有/低频；object CHECK |

全部硬件参数可空；未知存 null 绝不以 0 代替；gpu_count=0 与 null 语义可区分。resource_type 创建后不可改，硬件适用性创建时确定。

### 1.2 API 暴露方式（裁定）

硬件字段作为 Resource create/PATCH 的嵌套 `hardware` 对象 + Resource 响应嵌套 `hardware`；不新增独立端点（§21 明细无独立入口；§18 硬件是 Resource Detail 区域）。BARE_METAL：hardware 对象存在（未登记字段 null）；VIRTUAL_MACHINE：响应 hardware 恒为 null；VM 请求体出现 hardware→422（不静默忽略，DR-51）。

### 1.3 数值/单位/校验

cpu_sockets/cpu_cores/memory_mb：≥1 或 null（CHECK 1..2147483647）；gpu_count：≥0 或 null（CHECK 0..2147483647）；字符串：trim 非空或 null，长度 ≤255 code point（PROPOSED）。memory_mb 单位 MiB（1536 GiB=1572864）；不混用 MB/GB，不自动换算。0/负数对正整数列 422；gpu_count 负 422、0 接受。SN 无唯一性校验。

### 1.4 结构化 vs JSONB

9 字段全部结构化列（可查询/排序/统计）；厂商特有/低频扩展入 hardware.metadata JSONB（NOT NULL DEFAULT '{}' + object CHECK）。不为每厂商建列。

### 1.5 生命周期

BareMetalDetail 完全随 Resource：软删/恢复/乐观锁/审计只作用于 Resource；无独立 deleted_at/version/端点（§21）。

## 2. Implementation Layers

database=true；backend=true；frontend=true；api_required=true（扩展 docs/api/F004.md→v2，不新建 F005 Contract）。

## 3. API 草案（扩展 F004→v2）

POST /resources 新增可选 hardware 对象（仅 BARE_METAL；省略→全 null）。PATCH /resources/{id} hardware 为子字段级 exclude_unset（省略子字段保持原值；显式 null 清空该 nullable 子字段；hardware 整体显式 null/非对象/未知键→422）。响应 Resource 增 hardware:object|null（BARE_METAL 对象、VM null）。
错误：422 VALIDATION_ERROR（VM 提交 hardware；非对象/未知键；cpu_sockets/cpu_cores/memory_mb ≤0 或非整数；gpu_count<0；字符串空/纯空白/超长；metadata 非 object）；复用 F004 的 CONFLICT/VERSION_CONFLICT（SN 无唯一）。校验顺序沿用 F004 §3.5。
权限/审计：硬件读写复用 Resource WRITE/READ；硬件变更并入 Resource CREATE/UPDATE 审计（object_type="resource"，快照白名单扩 hardware）；删除/恢复随 Resource（ADMIN）。
Hardware 区域数据：详情 hardware 直接驱动 §18（CPU/Memory/GPU/Manufacturer/Model/SN；VM 不渲染）。

## 4. 数据库影响（交 DATABASE Gate）

表 bare_metal_details：resource_id UUID PK `pk_bare_metal_details` + FK→resources(id) ON DELETE CASCADE；manufacturer/model/serial_number/cpu_model/gpu_model varchar(255) NULL（非空文字 backstop）；cpu_sockets/cpu_cores/memory_mb integer NULL + CHECK 1..2147483647；gpu_count integer NULL + CHECK 0..2147483647；metadata jsonb NOT NULL DEFAULT '{}' + object CHECK（ORM 属性 meta）。
裁定：**不设 deleted_at/version/created_at/updated_at**（完全随 Resource，历史由 Resource 审计承载；避免冗余与第二套并发控制）——created_at 若 Database 认为有查询价值可在 DATABASE Gate 评估，但不改变无 deleted_at/version。
1:1 存在性：resource_id PK 保证至多一行；"BARE_METAL 必有、VM 必无"由应用保证（跨表条件无法纯 DB 声明）；可选类型匹配触发器交 Database 裁定。
迁移 0005_bare_metal_details：down_revision="0004_resources"，单一 head；up 建表→约束→FK→（可选触发器）；down 逆序；对称可逆、真库 up/down/up。**回填**：INSERT ... SELECT id FROM resources WHERE resource_type='BARE_METAL'（全 null 行）。生产回滚用 F001 全库备份。
索引：本 Feature 无硬件过滤/排序契约，不新增查询索引。

## 5. 验证策略（A1–A10，真实 PG）

A1 省略/null→存 null 返回 null 非 0；A2 gpu_count=0 存 0 与 null 区分；A3 0/负整数 422、合法值 201/200；A4 MiB 一致（1536 GiB→1572864）；A5 cpu_cores 整机物理核不含 HT（192 非 384）；A6 同 SN 可重复；A7 Hardware 区域六要素；A8 硬件变更进 Audit+权限；A9 无独立删除/恢复、随 Resource；A10 结构化列可 SQL 查询/排序、metadata 不破坏。补充：0005 真库 up/down/up；回填断言；VM 提交 hardware→422；PATCH 子字段省略保持/显式 null 清空；硬件变更乐观锁与审计同事务回滚不留痕。

## 6. 技术决策（DR-46–DR-56）

DR-46 BareMetalDetail 1:1（resource_id PK/FK CASCADE，BARE_METAL 一行、VM 无行，应用保证存在性，迁移回填）；DR-47 硬件嵌套于 Resource 请求/响应，不新增端点，VM hardware=null（PROPOSED）；DR-48 9 字段结构化列 + metadata JSONB；DR-49 全部 nullable、未知 null 不写 0、gpu_count=0=无 GPU；DR-50 数值 CHECK 上限；DR-51 非 BARE_METAL 提交 hardware→422；DR-52 字符串 trim 非空 ≤255（PROPOSED）；DR-53 硬件变更并入 Resource 审计快照；DR-54 detail 无独立 deleted_at/version/端点；DR-55 迁移 0005 对称可逆+回填；DR-56 扩展 F004→v2。

## 7. 风险与待核对项

交 Database：字符串长度 255/空串 backstop；metadata object CHECK；FK CASCADE 与 F003/F004 删除语义；是否加类型匹配触发器；回填 SQL；0005 up/down/up；无硬件索引裁定。
交 Tester：A1–A10；迁移回填断言；PATCH 子字段 exclude_unset；VM→422；审计快照与回滚。
交 CONTRACT：F004→v2 增量冻结；VM hardware=null vs 省略；DR-51/52/56 固定；字符串长度。
I-1（MEDIUM，范围）：A10 列表级硬件过滤/排序参数是否属 F005——**协调器裁定：不在已批准 F005 范围**（计划 scope 未含）；A10 由结构化列数据层满足；如需列表参数走变更控制，不阻塞。
I-2（LOW，交 Database）：detail 无时间戳裁定是否接受。
跨 Feature：F006 VM 容量独立（不复用本表）；F014 导入复用硬件字段校验与单位口径。

## 8. 结论与下一步

Status READY FOR DESIGN，无 Blocking Questions。下一步：DATABASE Gate 定稿 docs/database/f005-bare-metal.md；TEST_DESIGN 核对 A1–A10；CONTRACT 定稿 docs/api/F004.md v2 并签核 D01 BareMetal 域字段契约；完成后出 READY FOR IMPLEMENTATION。
