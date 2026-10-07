# F005 BareMetal 硬件与容量 — DATABASE 设计

- **签核**：Database；设计版本 v1（2026-10-08）
- **上游依据**：requirements-v3.md revision 3（§4.1、§8、§18、§21、§22、§26–§27、§31 T38/T39、§35.2 Q10-A、§35.3 D01）；docs/features/F005/product.md；docs/features/F005/architecture.md（§4、DR-46–DR-56）；docs/database/f004-resource.md v1；docs/database/f003-cluster.md v2；docs/architecture/d01-conventions.md v3
- **覆盖**：bare_metal_details 表、约束、触发器、迁移 0005、回填、Backend 可依赖保证与测试项。不覆盖 F006 VM 明细、docs/api/F004.md v2（Architect）、TEST 执行。

## 1. 设计决策汇总（DB-D45–DB-D52）

| ID | 决定 | 状态 |
| --- | --- | --- |
| DB-D45 | bare_metal_details.resource_id UUID PK pk_bare_metal_details + FK→resources(id) ON DELETE CASCADE；1:1 依附 Resource，软删不影响行 | CONFIRMED（§21）+DESIGN |
| DB-D46 | 9 硬件字段结构化列：manufacturer/model/serial_number/cpu_model/gpu_model varchar(255) NULL（trim+非空 backstop）；cpu_sockets/cpu_cores/memory_mb integer NULL CHECK 1..2147483647；gpu_count integer NULL CHECK 0..2147483647 | CONFIRMED（§8/D01）+DESIGN |
| DB-D47 | metadata jsonb NOT NULL DEFAULT '{}' + object CHECK；物理列 metadata、ORM 属性 meta | DESIGN |
| DB-D48 | **不设 deleted_at/version/created_at/updated_at**（确认 DR-54；created_at 也不加） | CONFIRMED（§21）+DESIGN |
| DB-D49 | 类型匹配触发器 trg_bare_metal_details_type_match（BEFORE INSERT/UPDATE）要求引用 Resource 为 BARE_METAL；resource_type 不可改故无需反向触发器 | DESIGN（§27/DR-46） |
| DB-D50 | 不新增任何索引（PK 覆盖 FK 列；无硬件过滤/排序契约） | DESIGN |
| DB-D51 | 迁移 0005_bare_metal_details，down_revision=0004_resources；up 建表→约束→FK→触发器→回填；down 逆序；对称可逆、单一 head、真库 up/down/up | DESIGN（DB-D7） |
| DB-D52 | SN 一期无唯一约束；硬件字段无归一化键；trim/非空由应用保证，DB 为非空+已 trim backstop | CONFIRMED（§8/Q10-A）+DESIGN |

## 2. bare_metal_details 表

| 列 | 类型 | 空 | 默认 | 约束 |
| --- | --- | --- | --- | --- |
| resource_id | UUID | NOT NULL | — | PK pk_bare_metal_details；FK fk_bare_metal_details_resource_id_resources→resources(id) ON DELETE CASCADE |
| manufacturer | varchar(255) | NULL | — | ck_bare_metal_details_manufacturer_format |
| model | varchar(255) | NULL | — | ck_bare_metal_details_model_format |
| serial_number | varchar(255) | NULL | — | ck_bare_metal_details_serial_number_format；无 UNIQUE |
| cpu_model | varchar(255) | NULL | — | ck_bare_metal_details_cpu_model_format |
| cpu_sockets | integer | NULL | — | ck_bare_metal_details_cpu_sockets_range：NULL 或 1..2147483647 |
| cpu_cores | integer | NULL | — | ck_bare_metal_details_cpu_cores_range：NULL 或 1..2147483647（整机物理核不含超线程，语义应用保证） |
| memory_mb | integer | NULL | — | ck_bare_metal_details_memory_mb_range：NULL 或 1..2147483647（MiB） |
| gpu_model | varchar(255) | NULL | — | ck_bare_metal_details_gpu_model_format |
| gpu_count | integer | NULL | — | ck_bare_metal_details_gpu_count_range：NULL 或 0..2147483647（0=无 GPU） |
| metadata | jsonb | NOT NULL | '{}'::jsonb | ck_bare_metal_details_metadata_object；ORM 属性 meta |

字符串 CHECK 形态（<col>）：`<col> IS NULL OR (<col> = btrim(<col>) AND btrim(<col>) <> '')`。varchar(255) 按 Unicode code point。非空/已 trim backstop；Unicode Cc/Cf 为应用责任（DB backstop，已知差异，沿用 F003 I-6/F004 I-4）。数值列允许 NULL，CHECK `IS NULL OR ...`：NULL 合法、0/负对正整数列被拒、gpu_count 0 合法。

## 3. 五项交核裁定

1. **无 deleted_at/version/created_at/updated_at**（确认 DR-54，且不新增 created_at）：detail 为 1:1 从属明细随 Resource 生命周期；历史由 Resource 审计承载；并发由 Resource.version 承担；无契约要求 detail 级时间戳。
2. **类型匹配触发器**（DB-D49）：fn_bare_metal_details_type_match——NEW.resource_id 对应 Resource 的 resource_type IS DISTINCT FROM 'BARE_METAL' 时 RAISE restrict_violation；BEFORE INSERT OR UPDATE。因 resource_type 不可改（F004 DB-D40）无需反向触发器。DB 保证"VM 必无 detail 行"；"BARE_METAL 必有 detail 行"由应用创建时同步写入保证（跨表存在性无法纯 DB 声明）。
3. **FK CASCADE**：§21 删除为逻辑删除不物理删 resources 行，CASCADE 正常不触发；detail 随 Resource 软删隐藏、恢复可见。CASCADE 仅在物理 DELETE（迁移/测试/运维）清孤儿。与 F004 cluster FK RESTRICT 差异：Resource 是阻止 Cluster 物理删除的独立对象；detail 明确不是阻止 Resource 删除的独立子对象（§21 明文排除）。
4. **索引**（DB-D50）：不新增。resource_id PK 覆盖 FK 列；无硬件字段过滤/排序 API 契约；不建 metadata GIN。
5. **迁移与回填**（DB-D51）：revision="0005_bare_metal_details"、down_revision="0004_resources"；upgrade 建表→FK(CASCADE)→触发器→回填；downgrade 逆序 DROP TRIGGER→FUNCTION→TABLE。回填 `INSERT INTO bare_metal_details (resource_id) SELECT id FROM resources WHERE resource_type='BARE_METAL';`（metadata 默认 '{}'，其余 NULL）。生产回滚用 F001 全库备份（结构可逆≠数据可逆）。

## 4. 数据完整性对应表

| 规则 | 作用域 | DB 保证 | 业务层保证 | 并发/生命周期 | 验证 |
| --- | --- | --- | --- | --- | --- |
| §8/§27 字段类型 | Resource create/PATCH 嵌套 hardware | 类型 + metadata object CHECK | Pydantic 类型与 422 | — | V-DB-34/35 |
| §8/D01 §3 数值 | 同上 | ck_*_range（正整数 1..2147483647；gpu_count 0..2147483647） | 0/负对正整数列 422；gpu_count<0 422 | — | V-DB-31/32/33 |
| §8 未知=null 非0 | 同上 | 列可空+空串 backstop | 省略/显式 null 存 null 不写 0 | — | V-DB-31/33 |
| §8/Q10-A SN 无唯一 | 同上 | 无 UNIQUE | 无唯一校验、无 409 | 同 SN 可重复 | V-DB-39 |
| §8/D01 §3 MiB | create/PATCH | integer 存储（不换算） | 按 MiB 解释；1536 GiB→1572864 | — | V-DB-31 |
| §26/§8 结构化/JSONB | create/PATCH | 9 列结构化；metadata object CHECK | 整值替换 | 厂商特有入 metadata | V-DB-35 |
| §21 明细随生命周期 | DELETE/RESTORE Resource | 无 deleted_at；软删不删行 | 默认过滤；无独立入口 | 不级联、不阻止 Resource 删除 | V-DB-37 |
| §21/§27 类型关系 | detail 写入 | 类型匹配触发器（仅 BARE_METAL 可有行） | VM→422；BARE_METAL 必有行应用保证 | resource_type 不可改 | V-DB-36 |
| §27 引用完整性 | detail 写入 | FK CASCADE | 引用存在性校验 | 物理 DELETE 清孤儿 | V-DB-37 |
| §27/DR-46 1:1 至多一行 | detail 写入 | resource_id PK | 单行 upsert | 并发由 Resource version 兜底 | V-DB-38 |
| §22/§23 审计/乐观锁 | Resource create/PATCH | detail 无 version | 同事务；回滚不留痕 | 条件 UPDATE rowcount=0→409 | F004 + F005 集成 |
| §27 真实 PG | 迁移 | up/down/up、单一 head、回填 | — | — | V-DB-29/30 |

## 5. Backend 可依赖保证与测试项

保证：resource_id 唯一且必为存在的 Resource（PK+FK）；物理删除 Resource 级联删 detail；每 Resource 至多一行；仅 BARE_METAL 可有 detail 行（类型触发器）；VM 提交 hardware 由应用 422；5 字符串列可 null，非 null 时已 trim 非空 ≤255；无 SN 唯一；cpu_sockets/cpu_cores/memory_mb null 或 ≥1；gpu_count null 或 ≥0；gpu_count=0 与 null 存储层可区分；metadata 恒为 object（默认 {}）；detail 无独立 deleted_at/version/时间戳；软删 Resource 不删 detail；0005 有真实 downgrade、单一 head。不保证：BARE_METAL 必有 detail 行（应用保证）；Unicode Cc/Cf（DB ASCII backstop）。

计划测试项（真实 PG）：V-DB-29 迁移 up/down/up 一致、down_revision=0004、单一 head；V-DB-30 回填（预置 BARE_METAL 各 1 行全 null detail、metadata='{}'；VM 0 行）；V-DB-31 正整数列接受 NULL/1/2147483647 拒 0/负；V-DB-32 gpu_count NULL/0/2147483647 拒负；V-DB-33 gpu_count 0 vs NULL 可区分；V-DB-34 字符串 NULL/普通/255 接受、空/纯空白/首尾空白/256 拒；V-DB-35 metadata 拒 array/scalar/json null、默认 {}；V-DB-36 VM 插入 detail 被触发器拒、BARE_METAL 成功、UPDATE resource_id 指向 VM 拒；V-DB-37 FK 拒不存在、物理 DELETE 级联、软删 detail 仍在；V-DB-38 同 resource_id 第二行 PK 拒；V-DB-39 对象存在断言（PK/FK/CHECK/触发器）、SN 无 UNIQUE、无额外索引、ORM 列 metadata/属性 meta。

## 6. 未验证项与风险

- I-1（LOW，交 Architect/CONTRACT）：字符串长度 255、trim/非空口径（DR-52 PROPOSED）须在 docs/api/F004.md v2 与 D01 镜像。
- I-2（LOW，交 Backend）：字符串 trim、数值范围、VM→422 应用层实现，DB CHECK 仅 backstop。
- I-3（LOW）：字符串 Cc/Cf DB 为 ASCII backstop（沿用 F003 I-6/F004 I-4）。
- I-4（NOTE）：BARE_METAL 必有 detail 行无 DB 反向约束，应用保证，列入集成测试与 Review。
- I-5（NOTE）：detail 无 version，并发保护依赖 Resource.version 条件更新，须同一事务。
- I-6（NOTE）：downgrade 丢 detail 数据不可逆，生产回滚用全库备份。
- 只读签核，全部为计划验证无 PASS。

## 7. 设计版本历史

| 版本 | 日期 | 变更 |
| --- | --- | --- |
| v1 | 2026-10-08 | 初次签核（DB-D45–D52）；bare_metal_details 首次建表、类型匹配触发器、迁移 0005 与回填；五项交核裁定。 |
