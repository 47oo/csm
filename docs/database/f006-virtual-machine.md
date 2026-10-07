# F006 虚拟机登记 — DATABASE 设计

- **签核**：Database；设计版本 v1（2026-10-09）
- **上游依据**：requirements-v3.md revision 3（§4、§4.1、§6、§8、§9、§21、§22、§27、§31 T08/T09/T19/T38/T39、§35.2 Q10-A/Q10-B、§35.3 D01）；docs/features/F006/product.md（A1–A17、I-1–I-4）；docs/features/F006/architecture.md（§6、DR-57–DR-70）；docs/database/f004-resource.md v1；docs/database/f005-bare-metal.md v1；docs/database/f001-baseline.md（DB-D6/DB-D7）；docs/architecture/d01-conventions.md v4
- **覆盖**：virtual_machine_details 表、约束、索引、宿主正确性双触发器、FK 语义、迁移 0006、回填守卫、Backend 可依赖保证与测试项。不覆盖 docs/api/F004.md v3（Architect/CONTRACT）、D01 v5 §5.5、TEST 执行。

## 1. 设计决策汇总（DB-D53–DB-D63）

| ID | 决定 | 状态 |
| --- | --- | --- |
| DB-D53 | resource_id UUID PK pk_virtual_machine_details，FK→resources(id) ON DELETE CASCADE；1:1 依附 Resource，软删不影响行 | CONFIRMED（§21）+DESIGN |
| DB-D54 | host_resource_id UUID NOT NULL + FK fk_virtual_machine_details_host_resource_id_resources→resources(id) ON DELETE RESTRICT + 索引 ix_virtual_machine_details_host_resource_id | CONFIRMED（§9/§27）+DESIGN |
| DB-D55 | vcpu/memory_mb integer NULL CHECK 1..2147483647；disk_gb integer NULL CHECK 0..2147483647（0=明确无磁盘） | CONFIRMED（§8/§9/D01 §3）+DESIGN |
| DB-D56 | hypervisor varchar(255) NULL + trim/非空 backstop CHECK；一期无枚举；Cc/Cf 应用责任（DB ASCII backstop） | CONFIRMED（§9）+DESIGN（无枚举 I-2 PROPOSED） |
| DB-D57 | 不建 detail 级 metadata 列（I-3 裁定：归 Resource 公共 resources.metadata） | DESIGN（I-3 PROPOSED→CONTRACT） |
| DB-D58 | 宿主正确性双触发器 trg_..._type_match + trg_..._host_valid（BEFORE INSERT OR UPDATE），违约 restrict_violation；缺失被引用行交 FK | DESIGN（§27/DR-66） |
| DB-D59 | 不加 resources 软删守卫触发器（已评估否决）；Host 软删保护沿用应用引用检查器（DR-62），记录残余并发窗口 | DESIGN |
| DB-D60 | detail 不设 deleted_at/version/created_at/updated_at | CONFIRMED（§21）+DESIGN |
| DB-D61 | 迁移 0006_virtual_machine_details，down_revision=0005；up 建表→约束→FK→索引→触发器/函数→回填守卫；down 逆序；对称可逆、单一 head、真库 up/down/up | DESIGN（DB-D7） |
| DB-D62 | 回填守卫：存在未删除 VIRTUAL_MACHINE Resource 时 upgrade 中止并诊断；不合成/不编造 detail 行 | DESIGN（DR-68） |
| DB-D63 | detail 无业务唯一性/归一化键；不建 metadata GIN、无容量索引 | CONFIRMED（§7/§27）+DESIGN |

## 2. virtual_machine_details 表

| 列 | 类型 | 空 | 默认 | 约束 |
| --- | --- | --- | --- | --- |
| resource_id | UUID | NOT NULL | — | PK pk_virtual_machine_details；FK fk_virtual_machine_details_resource_id_resources→resources(id) ON DELETE CASCADE |
| host_resource_id | UUID | NOT NULL | — | FK fk_virtual_machine_details_host_resource_id_resources→resources(id) ON DELETE RESTRICT；ix_virtual_machine_details_host_resource_id |
| vcpu | integer | NULL | — | ck_virtual_machine_details_vcpu_range：NULL 或 1..2147483647 |
| memory_mb | integer | NULL | — | ck_virtual_machine_details_memory_mb_range：NULL 或 1..2147483647（MiB，原样存储不换算） |
| disk_gb | integer | NULL | — | ck_virtual_machine_details_disk_gb_range：NULL 或 0..2147483647（GiB；0=明确无磁盘） |
| hypervisor | varchar(255) | NULL | — | ck_virtual_machine_details_hypervisor_format：NULL 或（= btrim(hypervisor) AND btrim(hypervisor) <> ''） |

- 无 metadata 列（DB-D57）、无 deleted_at/version/时间戳列（DB-D60）。
- varchar(255) 按 Unicode code point；非空/已 trim backstop，Cc/Cf 应用拦截（F003 I-6/F004 I-4 已知差异）。
- 数值列 IS NULL OR (...)：NULL 合法；正整数列 0/负拒；disk_gb 0 合法且与 NULL 可区分。

## 3. 交核裁定

1. **metadata 列（I-3/DR-69）**：不建。§9 的 metadata 是 Resource 公共属性；VM 即 Resource（1:1），resources.metadata（F004 DB-D35）已承载；再建会产生两套语义。契约侧 virtual_machine 嵌套对象不暴露独立 metadata 键。备选（仅当 CONTRACT 裁定为 VM 级）：加 metadata jsonb NOT NULL DEFAULT '{}' + object CHECK。
2. **宿主正确性双触发器（DR-66）**：type_match（resource_id 须 VIRTUAL_MACHINE）；host_valid（host_resource_id 须指未软删 BARE_METAL 且 host.cluster_id=vm.cluster_id）；违约 restrict_violation；缺失被引用行交 FK。resource_type/cluster_id 不可改（F004 DB-D40）故无需反向触发器；UPDATE 分支覆盖换 Host。
3. **resources 软删守卫触发器：不加（DB-D59）**。§21/DR-62 保护机制是应用引用检查器（409 reference_exists+references）；resources 侧 trigger 只能抛 restrict_violation（500 语义）且属 F004 已签核表。**残余风险**：Host 软删与 VM 新建并发存在检查后写入窗口（I-3），交 Backend 事务串行化（如 Host 行 SELECT ... FOR UPDATE）化解；若不可接受再由 Architect 走变更控制。
4. **FK 语义**：resource_id CASCADE（1:1 生命周期从属，§21）；host_resource_id RESTRICT（Host 是被引用独立对象，物理删除先清 detail，软删保护由应用检查器）。与 F005 DB-D45、F004 DB-D39 一致。
5. **索引**：ix_virtual_machine_details_host_resource_id（列表过滤 host_resource_id + 引用检查 + FK RESTRICT；PG 不为 FK 引用列自动建索引）。resource_id PK 覆盖其 FK 列；无容量过滤/排序契约，不建 metadata GIN。
6. **迁移与回填守卫**：见 §4。

## 4. 迁移 0006_virtual_machine_details

- revision="0006_virtual_machine_details"、down_revision="0005_bare_metal_details"；单一 head。
- upgrade：①回填守卫（DO 块）→②create_table（列+PK+双 FK+4 CHECK）→③create_index→④两函数与两触发器。约束/触发器名用 op.f() 显式全给。
- **回填守卫（DR-68）**：host_resource_id NOT NULL 且 F004 允许无 Host 的 VM → 无安全回填值，不合成 detail 行。upgrade 开头：
  ```sql
  DO $$ DECLARE n bigint; BEGIN
    SELECT count(*) INTO n FROM resources
      WHERE resource_type='VIRTUAL_MACHINE' AND deleted_at IS NULL;
    IF n > 0 THEN RAISE EXCEPTION
      'cannot apply 0006: % undeleted VIRTUAL_MACHINE resource(s) exist without a host; no safe backfill (DR-68).', n
      USING ERRCODE='raise_exception'; END IF;
  END $$;
  ```
  仅守卫未删除 VM；不修改既有行。无遗留数据环境（V3 一期）n=0，守卫空操作，升级干净。
- downgrade：逆序 DROP TRIGGER→FUNCTION→INDEX→TABLE；结构可逆、单一 head。数据不可逆（丢弃 detail），生产回滚用 F001 全库备份。
- 全表新建，无「可空→回填→置 NOT NULL」需求。
- 交付时真库执行 up/down/up（V-DB-40）。

## 5. 数据完整性对应表

| 规则 | 作用域 | DB 保证 | 业务层保证 | 并发/生命周期 | 验证 |
| --- | --- | --- | --- | --- | --- |
| §9/§27 Host 类型 | create/PATCH virtual_machine；换 Host | trg_type_match（resource_id 须 VM） | 422 virtual_machine.host_resource_id | resource_type 不可改 | V-DB-45 |
| §9/§27 Host 归属+未删+同 Cluster | 同上 | trg_host_valid（写入时未软删/BARE_METAL/同 Cluster） | 统一校验函数 422；换 Host 审计 | Host 之后软删由应用检查器；见 I-3 | V-DB-46 |
| §4.1/§9 Host 必填 | create/PATCH | host_resource_id NOT NULL | 省略/显式 null→422 | — | V-DB-42 |
| §9/§21 Host 引用删除保护 | DELETE Host | FK RESTRICT（物理）；软删无 DB 兜底 | resource←VM 检查器→409 reference_exists+references；VM 软删放行 | 软删并发窗口交事务设计 | V-DB-47/51/52 |
| §8/§9/D01 §3 数值 | create/PATCH | ck_*_range | 0/负对正整数列 422 | — | V-DB-42 |
| §8 unknown=null 非 0 | 同上 | 列可空 | 省略/显式 null 存 null 不写 0 | — | V-DB-42/43 |
| §8/D01 §3 单位 | 同上 | integer 原样不换算 | MiB/GiB；1 GiB=1024 MiB | — | V-DB-42 |
| §9/T39 不校验超额 | 同上 | 无跨字段/容量 CHECK | 不与 Host 容量比较 | — | A12 集成 |
| §9 hypervisor 无枚举 | 同上 | varchar(255)+trim/非空 backstop | trim→非空→禁 Cc/Cf→≤255；空/纯空白 422 | — | V-DB-44 |
| §21 明细随生命周期 | DELETE/RESTORE Resource | 无 deleted_at；软删不删行；物理删 CASCADE | 默认过滤；无独立删除入口 | 不级联、不阻止 Resource 删除 | V-DB-47 |
| §21/T24 恢复重检 Host | RESTORE VM | 无 detail 级约束 | 依赖检查器：Host 软删/缺失→409 dependency_deleted；不覆盖 | 标识重用天然不覆盖 | A14 集成 |
| §27 1:1 至多一行 | detail 写入 | resource_id PK | 单行 upsert；同事务建 Resource+detail | resources.version 兜底 | V-DB-48 |
| §22/§23 审计/乐观锁 | create/PATCH | detail 无 version | 同事务；回滚不留痕；条件 UPDATE rowcount=0→409 | 真并发 | F004 + F006 集成 |
| §27 真实 PG | 迁移/约束 | up/down/up、单一 head、回填守卫 | — | — | V-DB-40/41 |

## 6. Backend 可依赖保证与测试项

保证：resource_id 唯一且指向存在 Resource（PK+FK），每 Resource 至多一行；物理删 Resource 级联删 detail；host_resource_id 非空指向存在 Resource，物理删被引用 Host 被 RESTRICT 拒；detail 行仅 VM Resource 可有（type_match）；写入/更新时 host_resource_id 指未软删 BARE_METAL 且同 Cluster（host_valid），否则 restrict_violation；vcpu/memory_mb null 或 ≥1、disk_gb null 或 ≥0 且 0 与 null 可区分；hypervisor null 或已 trim 非空 ≤255；detail 无独立 deleted_at/version/时间戳；软删 Resource 不删 detail；索引存在；0006 有真实 downgrade、单一 head、回填守卫。

不保证：detail 写入后 Host 不再被软删（Host 软删无 DB 兜底，应用检查器+事务串行化负责，残余窗口 I-3）；「VM 必有 detail 行」（应用同事务写入）；hypervisor 的 Unicode Cc/Cf（DB ASCII backstop）；VM 级 metadata 列（归 Resource）。

计划测试项（真实 PG，无 PASS）：V-DB-40 迁移 up/down/up 一致、down_revision=0005、单一 head、含守卫与两触发器；V-DB-41 回填守卫（未删除 VM→中止；软删 VM→通过且不生成其行；无 VM→干净）；V-DB-42 数值边界；V-DB-43 disk_gb 0 vs NULL；V-DB-44 hypervisor 边界；V-DB-45 type_match 三例；V-DB-46 host_valid 四例；V-DB-47 FK 级联/RESTRICT/软删；V-DB-48 PK 第二行拒；V-DB-49 对象存在断言（PK/FK/ondelete/4 CHECK/索引/两触发器、无 metadata 列、无额外索引）；V-DB-50 host_resource_id 索引 EXPLAIN；V-DB-51 真并发物理删/插入；V-DB-52 Host 软删并发窗口验证 Backend 缓解。

## 7. 未验证项与风险

- I-1（LOW，交 Architect/CONTRACT）：D01 v5 §5.5 与 hypervisor ≤255 待签核。
- I-2（LOW，交 Product/用户）：hypervisor 无枚举按可空描述性字符串；新增枚举属新业务规则。
- I-3（MEDIUM，交 Architect/Backend）：Host 软删与 VM 新建检查后写入并发窗口无 DB 兜底（DB-D59）；须事务串行化，或经变更控制追加触发器。不阻塞表结构，但须在 BACKEND 实现前裁定。
- I-4（LOW，交 Backend）：引用删除、恢复重检 Host、审计同事务实现；DB CHECK 仅 backstop。
- I-5（已知差异）：hypervisor Cc/Cf DB 为 ASCII backstop。
- I-6（NOTE）：downgrade 丢弃 detail 数据不可逆，回滚用全库备份。
- I-7（NOTE）：metadata 归属交 CONTRACT（DR-69/I-3）固定。
- 只读签核，全部为计划验证无 PASS。

## 8. 设计版本历史

| 版本 | 日期 | 变更 |
| --- | --- | --- |
| v1 | 2026-10-09 | 初次签核（DB-D53–D63）；virtual_machine_details 首次建表、数值/字符串 CHECK、宿主双触发器、FK CASCADE/RESTRICT、host_resource_id 索引、迁移 0006 与回填守卫；六项交核裁定。 |