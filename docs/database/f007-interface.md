# F007 Interface 接口管理 — DATABASE 设计

- **签核**：Database；设计版本 v1（2026-10-09）
- **上游依据**：requirements-v3.md revision 3（§4、§4.1、§10、§13、§18、§21、§22、§23、§26、§27、§31 T12/T20/T37/T39/T40/T41、§35.2 Q10-B、§35.3 D01）；docs/features/F007/product.md（A1–A19、I-1–I-5）；docs/features/F007/architecture.md（§4、§6、DR-72–DR-88）；docs/database/f004-resource.md v1、f005/f006；docs/database/f001-baseline.md（DB-D6/DB-D7）；docs/architecture/d01-conventions.md v5
- **覆盖**：interfaces 表、字段/约束/索引/部分唯一、parent 正确性与 resource 不可改触发器、FK 语义、迁移 0007、Backend 可依赖保证与测试项、I-2/I-3/I-5 落地裁定。不覆盖 docs/api/F007.md、D01 v6 §5.6、TEST 执行。

## 1. 设计决策汇总（DB-D64–DB-D79）

| ID | 决定 | 状态 |
| --- | --- | --- |
| DB-D64 | interfaces 独立对象表，id UUID PK pk_interfaces 默认 gen_random_uuid()；resource_id UUID NOT NULL FK fk_interfaces_resource_id_resources→resources(id) ON DELETE RESTRICT + ix_interfaces_resource_id | CONFIRMED（§10/§27/DR-72）+DESIGN |
| DB-D65 | name varchar(64) NOT NULL + trim/非空/无内部空白与 Cc/Cf（ASCII backstop）CHECK；区分大小写保留；不建独立归一化键列（I-3） | CONFIRMED（§4.1/Q10-B）+DESIGN |
| DB-D66 | 部分唯一 uq_interfaces_resource_id_name UNIQUE(resource_id,name) WHERE deleted_at IS NULL | CONFIRMED（§4.1/§27/DR-73）+DESIGN |
| DB-D67 | interface_type varchar(16) NOT NULL DEFAULT 'OTHER' + 7 值 CHECK；不据 name 推断 | CONFIRMED（§10/DR-74）+DESIGN |
| DB-D68 | mac_address varchar(64) NULL + trim/非空/无控制字符 backstop；保留大小写；无正则无唯一 | PROPOSED（DR-75）→CONTRACT +DESIGN |
| DB-D69 | speed_mbps/mtu integer NULL CHECK 1..2147483647；MTU 不限取值域（I-2 落地） | CONFIRMED（§10/DR-76）+DESIGN |
| DB-D70 | parent_interface_id UUID NULL 自关联 FK fk_interfaces_parent_interface_id_interfaces→interfaces(id) ON DELETE RESTRICT + ix_interfaces_parent_interface_id + 非自引用 CHECK | CONFIRMED（§10/DR-78）+DESIGN |
| DB-D71 | enabled boolean NOT NULL DEFAULT true | CONFIRMED（§10/DR-77）+DESIGN |
| DB-D72 | metadata jsonb NOT NULL DEFAULT '{}' + object CHECK；物理列 metadata、ORM 属性 meta；Interface 自有（覆盖 product I-5） | CONFIRMED（§10/§26/DR-83）+DESIGN |
| DB-D73 | version integer NOT NULL DEFAULT 1 CHECK≥1；created_at/updated_at timestamptz NOT NULL now()（updated_at 应用维护无触发器）；deleted_at timestamptz NULL 软删 | DESIGN |
| DB-D74 | resource 不可改：trg_interfaces_immutable_resource（BEFORE UPDATE，id/resource_id 变更 restrict_violation），应用先 422 | PROPOSED（DR-79）→CONTRACT +DESIGN |
| DB-D75 | parent 正确性：fn/trg_interfaces_parent_valid（BEFORE INSERT/UPDATE）拒自引用/跨 Resource/指向软删父/递归 CTE 断环；缺失被引用行交 FK | CONFIRMED（§10/§27/DR-85）+DESIGN |
| DB-D76 | FK 语义：resource_id RESTRICT、parent_interface_id RESTRICT；软删保护走应用引用检查器 | DESIGN |
| DB-D77 | 索引仅 ix_interfaces_resource_id、ix_interfaces_parent_interface_id；不建 interface_type/deleted_at/q(pg_trgm) | DESIGN |
| DB-D78 | 迁移 0007_interfaces，down_revision=0006；对称可逆、单一 head、全表新建无回填、真库 up/down/up | DESIGN |
| DB-D79 | I-2/I-3/I-5 落地裁定见 §3 | DESIGN |

## 2. interfaces 表

| 列 | 类型 | 空 | 默认 | 约束 |
| --- | --- | --- | --- | --- |
| id | UUID | NOT NULL | gen_random_uuid() | PK pk_interfaces |
| resource_id | UUID | NOT NULL | — | FK fk_interfaces_resource_id_resources→resources(id) ON DELETE RESTRICT；ix_interfaces_resource_id |
| name | varchar(64) | NOT NULL | — | ck_interfaces_name_not_blank/_trimmed/_no_ws_control/_length |
| interface_type | varchar(16) | NOT NULL | 'OTHER' | ck_interfaces_interface_type：7 值 |
| mac_address | varchar(64) | NULL | — | ck_interfaces_mac_address_format：NULL 或（已 trim 非空无控制字符） |
| speed_mbps | integer | NULL | — | ck_interfaces_speed_mbps_range：NULL 或 1..2147483647 |
| mtu | integer | NULL | — | ck_interfaces_mtu_range：NULL 或 1..2147483647（不限取值域） |
| parent_interface_id | UUID | NULL | — | FK fk_interfaces_parent_interface_id_interfaces→interfaces(id) ON DELETE RESTRICT；ix_interfaces_parent_interface_id；ck_interfaces_parent_not_self |
| enabled | boolean | NOT NULL | true | — |
| description | text | NULL | — | — |
| metadata | jsonb | NOT NULL | '{}'::jsonb | ck_interfaces_metadata_object；ORM 属性 meta |
| version | integer | NOT NULL | 1 | ck_interfaces_version：≥1 |
| created_at/updated_at | timestamptz | NOT NULL | now() | UTC；updated_at 应用维护 |
| deleted_at | timestamptz | NULL | — | 软删 |

CHECK 形态：ck_name_not_blank `btrim(name)<>''`；ck_name_trimmed `name=btrim(name)`；ck_name_no_ws_control `name !~ '[[:space:][:cntrl:]]'`；ck_name_length `char_length(name) BETWEEN 1 AND 64`；ck_interface_type IN 7 值；ck_mac `mac_address IS NULL OR (mac_address=btrim(mac_address) AND btrim(mac_address)<>'' AND mac_address !~ '[[:cntrl:]]')`；ck_speed_mbps_range/ck_mtu_range `<col> IS NULL OR (<col> BETWEEN 1 AND 2147483647)`；ck_parent_not_self `parent_interface_id IS NULL OR parent_interface_id<>id`；ck_metadata_object `jsonb_typeof(metadata)='object'`；ck_version `version>=1`。name 不折叠大小写（eth0≠ETH0）。

## 3. 交核裁定

1. **I-3 归一化键列：不建（DB-D65）**。Interface name 归一化仅 trim+非空+禁空白/控制字符，不折叠大小写；ck_name_trimmed（name=btrim(name)）下存储值恒等归一化键，再建 name_key 冗余且可漂移。部分唯一 (resource_id,name) WHERE deleted_at IS NULL 已完整落实 §4.1/§27。F004 hostname_key 前提（非恒等折叠）在此不成立。若未来引入大小写不敏感，属业务变更，另加键列+迁移。
2. **I-2 MTU 落地（DB-D69）**：integer NULL CHECK 1..2147483647、单位字节、未知 null、原样存储、不限 1500/9000 取值域；限定取值域属新增业务限定须用户裁定。
3. **I-5 metadata（DB-D72）**：Interface 自有 jsonb NOT NULL DEFAULT '{}' + object CHECK（§10 权威），不并入 Resource；覆盖 product I-5 PROPOSED。
4. **parent 正确性触发器（DB-D75）**：BEFORE INSERT/UPDATE；拒①自引用②父已软删③父属不同 Resource④递归 CTE 断环；缺失被引用行交 FK。DB 提供写入时点保证；环并发窗口由应用复用 DR-71（resources 行 FOR UPDATE）闭合。
5. **resource 不可改触发器（DB-D74）**：resource_id/id UPDATE 变更抛 restrict_violation；应用先 422；软删/恢复/常规更新不受影响。
6. **FK 语义（DB-D76）**：resource_id 与 parent_interface_id 均 RESTRICT（Interface 为独立被引用对象，非 1:1 明细）。软删保护走应用检查器：F007 注册 resource←未删 Interface 与 parent←未删子 Interface；F010 注册 interface←未删 IPAddress。
7. **索引（DB-D77）**：建 ix_interfaces_resource_id（列表过滤/引用检查/FK 校验）、ix_interfaces_parent_interface_id（父过滤/引用检查/FK）；不建 interface_type（低基数）、deleted_at（非选择性）、q/pg_trgm（F013 引入）。

## 4. parent/resource 触发器

fn_interfaces_parent_valid（BEFORE INSERT OR UPDATE）：parent 非空时——parent_id=id→restrict_violation；parent 存在且（非 同 resource_id 或 已软删）→restrict_violation；从 parent 沿链上溯（WITH RECURSIVE ... UNION 去重保证有界）遇 NEW.id→restrict_violation。缺失被引用行交 FK。
fn_interfaces_immutable_resource（BEFORE UPDATE）：NEW.id 或 NEW.resource_id 与 OLD 不等→restrict_violation。
触发器名 trg_interfaces_parent_valid、trg_interfaces_immutable_resource。

## 5. 迁移 0007_interfaces

revision="0007_interfaces"、down_revision="0006_virtual_machine_details"；单一 head。
upgrade：create_table（列+PK+双 FK+全部 CHECK，op.f() 显式名）→部分唯一（unique=True, postgresql_where=sa.text("deleted_at IS NULL")）→ix_interfaces_resource_id、ix_interfaces_parent_interface_id→两函数与两触发器。
无回填（全表新建）。
downgrade：DROP TRIGGER→FUNCTION→INDEX（两个）→部分唯一索引→DROP TABLE。结构对称可逆；数据不可逆，生产回滚用 F001 全库备份。
交付时真库 up→down→up，断言 alembic heads 唯一（V-DB-53）。

## 6. 数据完整性对应表

| 规则 | 作用域 | DB 保证 | 业务层保证 | 并发/生命周期 | 验证 |
| --- | --- | --- | --- | --- | --- |
| §4.1/§27/Q10-B name 同 Resource 未删唯一 | POST/PATCH | 部分唯一（区分大小写）；name 已 trim CHECK | trim；冲突 409 unique_conflict{field:"name"} | 并发同名由索引仲裁；软删释放键；恢复冲突被拒 | V-DB-57/66 |
| §4.1/T40 name 规范 | 同上 | ck_name_* | trim→非空→禁内部空白/Cc/Cf→1–64；空/纯空白/含空白 422 | Cc/Cf 应用责任（DB ASCII backstop） | V-DB-56 |
| §10/T37 类型 | POST/PATCH | ck_interface_type + DEFAULT + NOT NULL | 省略→OTHER；不据 name 推断 | 枚举扩展走迁移 | V-DB-54/55 |
| §10/T20 MAC | 同上 | ck_mac；无 UNIQUE | 空可登记；保留大小写 | 同 MAC 允许多行 | V-DB-59 |
| §10/T39 speed | 同上 | ck_speed_mbps_range | 0/负 422；未知 null | — | V-DB-58 |
| §10/I-2 mtu | 同上 | ck_mtu_range（不限取值域） | 0/负 422；未知 null | 取值域限定须用户裁定 | V-DB-58 |
| §10/T20 parent | POST/PATCH | FK RESTRICT + ck_parent_not_self + trg_parent_valid；缺行交 FK | 应用递归校验+422 field=parent_interface_id | 环并发交应用 FOR UPDATE（DR-71）；删父由 DR-80 | V-DB-60/66 |
| §4.1/§21 resource 归属 | POST | resource_id NOT NULL + FK RESTRICT | 引用存在未软删否则 422 | 软删不删 interfaces 行；物理删 RESTRICT | V-DB-62 |
| §21/DR-79 归属不可改 | PATCH | trg_immutable_resource | 不可变字段→422 | 软删/恢复不受影响 | V-DB-61 |
| §21 软删/恢复 | DELETE/RESTORE | deleted_at + 部分唯一 | 默认过滤；恢复重检 name/Resource/parent，失败 409 不覆盖 | 不级联 | V-DB-57 |
| §21/§13/DR-82 interface←IPAddress | DELETE interface/F010 | FK（F010）RESTRICT | F010 检查器→409 reference_exists；F007 预留调用点 | IP 侧归 F010；删除不释放 IP | F010 集成 |
| §21/DR-80 parent←子 Interface | DELETE interface | FK RESTRICT | 有未删子→409 reference_exists 返回子列表 | 软删并发交事务 | V-DB-62 |
| §23 乐观锁 | PATCH/DELETE/restore | version CHECK + 条件 UPDATE | rowcount=0→409 | 真并发 | V-DB-67 |
| §22 Audit | 四 action | 复用 audit_logs | 同事务；object_type="interface"；回滚不留痕 | — | F007 集成 |
| §26/§10 metadata object | POST/PATCH | object CHECK + DEFAULT | 整值替换；非 object 422 | — | V-DB-63 |
| §27 真实 PG | 迁移/约束 | up/down/up、单一 head、无回填 | — | — | V-DB-53 |

## 7. Backend 可依赖保证与测试项

保证：id 唯一（PK）；resource_id 非空指向存在 Resource（FK）；物理删被引用 Resource 被 RESTRICT 拒；同 Resource 未删 name 唯一且区分大小写（部分唯一），软删释放、恢复冲突被拒、跨 Resource 同名允许、eth0/ETH0 并存；name 已 trim 非空无空白/ASCII 控制字符 1–64；interface_type 恒 7 值默认 OTHER；enabled 默认 true；metadata 恒 object 默认 {}；version ≥1 默认 1；mac_address NULL 或已 trim 非空 ≤64 无控制字符、无唯一；speed_mbps/mtu NULL 或 1..2147483647；parent_interface_id NULL 或指向存在同 Resource 未软删不形成环的 Interface（触发器）；resource_id/id 不可改；软删 Resource 不物理删 interfaces 行；索引 ix_interfaces_resource_id/ix_interfaces_parent_interface_id 存在、无 interface_type/deleted_at/pg_trgm 索引；0007 有真实 downgrade、单一 head、无回填。

不保证：application 层 parent 未软删首检（触发器兜底）与环并发闭合（残余窗口交事务，I-4）；Resource 归属在软删并发下的即时一致性；name/mac 的 Unicode Cc/Cf（ASCII backstop）；F010 的 interface←IPAddress；metadata 语义（仅 object）。

计划测试项（真实 PG，V-DB-53–V-DB-67）：V-DB-53 迁移 up/down/up、down_revision=0006、单一 head、对象齐全、无回填；V-DB-54 默认值/ NOT NULL；V-DB-55 类型 7 值/省略不推断；V-DB-56 name NULL/空/纯空白/首尾/内部空白/ASCII 控制/65 拒、1–64 接受、大小写保留；V-DB-57 部分唯一（重名拒/eth0 vs ETH0/跨 Resource/软删重建/存活同名失败/恢复冲突/并发仅一成功）；V-DB-58 speed/mtu 边界；V-DB-59 mac 边界；V-DB-60 parent 自引用/跨 Resource/软删父/环/缺行；V-DB-61 UPDATE resource_id/id 拒；V-DB-62 FK RESTRICT 与软删保留；V-DB-63 metadata object；V-DB-64 对象存在断言（无 MAC UNIQUE、无 trgm/GIN）；V-DB-65 索引 EXPLAIN；V-DB-66 并发（同名/环双会话/应用 FOR UPDATE 残余窗口）；V-DB-67 version 与乐观锁。

## 8. 与 F004/F005/F006 语义对照

| 项 | F004 resources | F005/F006 detail | F007 interfaces |
| --- | --- | --- | --- |
| 实体性质 | 独立对象 | 1:1 从属明细 | 独立对象 |
| PK | 自身 UUID | PK=FK=resource_id | 自身 UUID |
| resource FK | cluster_id RESTRICT | resource_id CASCADE | resource_id RESTRICT |
| 软删 | deleted_at+部分唯一 | 无 deleted_at | deleted_at+部分唯一 |
| 不可改触发器 | cluster_id/resource_type | — | resource_id（+id） |
| 附加正确性触发器 | — | type_match/host_valid | parent_valid |

## 9. 未验证项与风险

- I-1（LOW，交 CONTRACT/D01 v6）：name 1–64、mac ≤64/无正则口径待 D01 §5.6 与 docs/api/F007.md 固定。
- I-2（LOW，交 CONTRACT/Product）：MTU 正整数/null 不限取值域。
- I-3（已闭合）：不建归一化键列。
- I-4（MEDIUM，交 Backend/Architect）：DB 触发器无法单独闭 parent 环并发；须应用复用 DR-71 FOR UPDATE；不可接受走变更控制。
- I-5（NOTE，交 CONTRACT）：metadata 归 Interface 自有，需 docs/api/F007.md 固定。
- I-6（NOTE）：down 丢弃 interfaces 数据不可逆。
- I-7（NOTE，交 Tester）：软删可见性为 ORM 责任，relationship 过滤传播须验证；索引未建项断言「不存在」。
- 只读签核，全部为计划验证无 PASS。

## 10. 设计版本历史

| 版本 | 日期 | 变更 |
| --- | --- | --- |
| v1 | 2026-10-09 | 初次签核（DB-D64–D79）；interfaces 首次建表、部分唯一 (resource_id,name) WHERE deleted_at IS NULL、parent 正确性与 resource 不可改触发器、双 FK RESTRICT、索引裁定、迁移 0007；I-2/I-3/I-5 落地裁定。 |