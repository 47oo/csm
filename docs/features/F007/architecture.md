# F007 Interface 接口管理 — ARCHITECTURE 阶段报告

- **Task**：F007（FEATURE，P0，M3，deps [F004]）— Architect，Feature 设计模式
- **Status**：`READY FOR DESIGN`（2026-10-09；协调器核验后持久化）
- **Basis**：requirements-v3.md revision 3（§4、§4.1、§10、§13、§18、§21、§22、§23、§25、§27、§31 T12/T20/T37/T39/T40/T41、§35.2 Q10-B、§35.3 D01）；docs/features/F007/product.md（A1–A19、I-1–I-5）；docs/api/F004.md v3；docs/database/f004/f005/f006；d01-conventions.md v5；plan_revision 4 F007。
- **结论属性**：设计输入，交 DATABASE/TEST_DESIGN；Contract 草案供 CONTRACT 定稿（新建 docs/api/F007.md）。

## 1. 方案摘要

### 1.1 Interface 实体（独立表，PK=UUID）

Interface 是**独立对象**（§21 软删清单含 Interface），非 Resource 的 1:1 从属明细，故 **PK 为自身 UUID**，resource_id 为普通 FK（区别 F005/F006 的 detail PK=FK）。

| 字段 | 类型 | 空 | 默认 | 单位 | 语义 |
| --- | --- | --- | --- | --- | --- |
| id | UUID | 否 | gen_random_uuid() | — | PK pk_interfaces |
| resource_id | UUID | 否 | — | — | FK→resources(id)；创建必填；**创建后不可改**；引用须存在未软删 |
| name | varchar(64) | 否 | — | — | trim→非空→禁内部空白/Cc/Cf；**区分大小写保留**；同 Resource 未删唯一；删除后复用 |
| interface_type | varchar(16) | 否 | 'OTHER' | — | PHYSICAL/VIRTUAL/BOND/BRIDGE/VLAN/LOOPBACK/OTHER；不由 name 推断 |
| mac_address | varchar(64) | 是 | null | — | trim 后非空或 null；保留大小写；无全局唯一 |
| speed_mbps | integer | 是 | null | Mbps | 正整数 1..2147483647 或 null；标称速率 |
| mtu | integer | 是 | null | 字节 | 正整数 1..2147483647 或 null（I-2） |
| parent_interface_id | UUID | 是 | null | — | 自关联 FK→interfaces(id)；同 Resource、禁自引用/循环；可 PATCH 改 |
| enabled | boolean | 否 | true | — | 登记状态非实时探测 |
| description | text | 是 | null | — | 描述性 |
| metadata | jsonb | 否 | '{}'::jsonb | — | **Interface 自有**；object CHECK；整值替换（DR-83） |
| version | integer | 否 | 1 | — | 乐观锁 CHECK ≥1 |
| created_at/updated_at | timestamptz | 否 | now() | — | UTC；updated_at 应用维护 |
| deleted_at | timestamptz | 是 | null | — | 软删 |

省略语义（§4.1/D01 §4）：创建省略非必填→默认/null；更新省略=保持；显式 null 仅清空 nullable（description/mac_address/speed_mbps/mtu/parent_interface_id）；必填显式 null→422；不可变/只读字段→422。**不落字段**：IP/CIDR、VLAN ID、所属 Network、管理/业务/存储分类（§4/§10/§13）。

### 1.2 名称唯一（I-3）
归一化 = 仅 trim + 非空 + 禁 Cc/Cf + 禁内部空白；**不做大小写折叠**；唯一比较用 trim 后原值。唯一范围 (resource_id, name) **部分唯一 WHERE deleted_at IS NULL**。**不建独立归一化键列（PROPOSED）**：无折叠 + CHECK name=btrim(name) 时 key 恒等 name，直接对 name 建部分唯一即满足 §27。交 DATABASE 最终裁定。

### 1.3 parent_interface（I-4）
自关联多对一，可空；须同 resource_id、非自身、无环。归属固定：resource_id 创建后不可改（PROPOSED）；parent_interface_id 可 PATCH。
**环检测（DR-85）**：应用层递归祖先校验（主，422 field=parent_interface_id）+ 复用 DR-71 锁序（对 resources 行 SELECT ... FOR UPDATE 串行化同 Resource 父变更）+ DB 触发器 trg_interfaces_parent_valid 兜底（拒自引用/跨 Resource/递归 CTE 断环；纯触发器无法单独闭并发窗口）。

### 1.4 生命周期/引用/审计
- 软删默认隐藏；ADMIN 恢复/查看已删。
- 删除引用检查：resource←未删 Interface（F007 注册，收窄 F004 DELETE /resources）；interface←未删 IPAddress（F010 注册，F007 预留调用点）；interface←未删子 Interface（父删除保护，PROPOSED）。
- 恢复重检 name 唯一、Resource 未软删、parent 有效；失败 409 不覆盖。
- 审计：CREATE/UPDATE/DELETE/RESTORE 四 action，同 Session 同 commit，object_type="interface"。

## 2. API 暴露裁定（DR-84）

**裁定：新建独立端点 `/api/v1/interfaces` + 独立 Contract `docs/api/F007.md`；不并入 F004 嵌套。** 理由：§25 明确列出该路径；Interface 有自身 ID/version/软删/恢复/Activity，是可独立寻址资源（区别 F005 hardware/F006 virtual_machine 的 1:1 明细嵌套）。

Endpoints：GET/POST /api/v1/interfaces；GET/PATCH/DELETE /api/v1/interfaces/{id}；POST /api/v1/interfaces/{id}/restore；GET /api/v1/interfaces/{id}/activity（7 端点）。权限/错误码/软删可见性复用 F004 §1；错误注册表以 F002 §1.2 为权威。
响应 Interface：id、resource{id,hostname}、name、interface_type、mac_address、speed_mbps、mtu、parent_interface{id,name}|null、enabled、description、metadata、version、created_at/updated_at、deleted_at。
列表 Query：resource_id、interface_type、enabled、q、parent_interface_id、deleted、page/page_size、sort∈{name,interface_type,speed_mbps,mtu,created_at,updated_at}、order。
错误：409 CONFLICT{unique_conflict,field:"name"} / {not_deleted} / {dependency_deleted,conflicts:[{object_type:"resource"|"interface",object_id}]} / {reference_exists,references:[{object_type,object_id,label}]}；422 见字段；VERSION_CONFLICT。
校验顺序：POST 401→403→body(422)→resource(422)→parent(422)→name 唯一(409)→写+Audit→201；PATCH 401→403→body(422)→可见性(404)→parent 变更(422)→version(409)→name 唯一(409)→写+Audit→200；DELETE/restore 见 Contract。
审计白名单 {resource_id,name,interface_type,mac_address,speed_mbps,mtu,parent_interface_id,enabled,description,metadata}。

## 3. D01 补齐（v5→v6）
新增 **§5.6 Interface 字段口径**：name trim/非空/禁内部空白与 Cc/Cf/长度 1–64/区分大小写/同 Resource 未删部分唯一；interface_type 7 值默认 OTHER；mac_address trim/非空或 null/≤64/保留大小写/无正则/无唯一；speed_mbps 正整数或 null（标称速率）；mtu 正整数或 null（不限取值域）；enabled boolean 默认 true；parent_interface 可空同 Resource 非自身无环；metadata Interface 自有；resource 创建必填创建后不可改。§3 追加数值引用、§5.2 追加 name 64、§8 记录 v6。

## 4. 数据库影响（交 DATABASE）

表 `interfaces`：id UUID PK pk_interfaces；resource_id NOT NULL FK fk_interfaces_resource_id_resources ON DELETE RESTRICT + ix_interfaces_resource_id；name varchar(64) NOT NULL + ck trim/非空/无空白；interface_type varchar(16) NOT NULL DEFAULT 'OTHER' + 7 值 CHECK；mac_address varchar(64) NULL + trim/非空 CHECK；speed_mbps/mtu integer NULL CHECK 1..2147483647；parent_interface_id UUID NULL FK fk_interfaces_parent_interface_id_interfaces ON DELETE RESTRICT + ix + ck 非自引用；enabled boolean NOT NULL DEFAULT true；description text NULL；metadata jsonb NOT NULL DEFAULT '{}' + object CHECK（ORM 属性 meta）；version integer NOT NULL DEFAULT 1 CHECK ≥1；created_at/updated_at；deleted_at。

约束/索引：部分唯一 uq_interfaces_resource_id_name UNIQUE(resource_id,name) WHERE deleted_at IS NULL；不建独立归一化键列（I-3）；ix_interfaces_resource_id、ix_interfaces_parent_interface_id；不可改触发器 trg_interfaces_immutable_resource（resource_id 变更 restrict_violation）；parent 正确性 trg_interfaces_parent_valid（拒自引用/跨 Resource/递归 CTE 断环）。不建 MAC 唯一、metadata GIN、pg_trgm。
引用检查（应用层）：F007 注册 resource←未删 Interface；F010 注册 interface←未删 IPAddress；interface←未删子 Interface（PROPOSED）。
迁移 `0007_interfaces`，down_revision=0006，单一 head，全表新建无回填，对称可逆，真库 up/down/up；生产回滚用 F001 全库备份。

## 5. 验证策略（A1–A19，真实 PG）
A1/A2/A4 部分唯一（重名 409；eth0/ETH0 并存；软删后重建；存活同名失败）；A3 name trim/空/内部空白/Cc/Cf 422+CHECK；A5 类型默认 OTHER 不推断；A6 enabled 默认 true；A7 speed_mbps 正整数/null/0负 422；A8/A9 parent 跨 Resource/自引用/环 422 + 触发器负例；A10 mac 空可登记/同 MAC 允许；A11 resource 缺失/不存在/软删 422；A12 有未删 IP 引用禁删（F010）+ resource←Interface/parent←子接口；A13 恢复重检；A14 权限矩阵；A15 四 action 同事务 Audit；A16 1:N 归 F010；A17 不存 IP/CIDR/VLAN/分类；A18 DB 部分唯一兜底；A19 聚合展示归 F013。
补充 DB/集成：0007 真库 up/down/up/单一 head；部分唯一/CHECK/触发器/索引断言；parent 四负例+应用环并发双会话；resource 软删与 Interface 创建并发串行化；PATCH exclude_unset/不可变 422；乐观锁并发；审计回滚；resource←Interface 端到端；F010 预留空集。

## 6. 技术决策（DR-72–DR-88）

| ID | 决策 | 状态 |
| --- | --- | --- |
| DR-72 | Interface 独立表 PK=UUID，resource_id FK RESTRICT（独立对象非 1:1 明细） | CONFIRMED+DESIGN |
| DR-73 | name varchar(64) trim/非空/禁内部空白与 Cc/Cf，区分大小写；部分唯一 (resource_id,name) WHERE deleted_at IS NULL；不建独立键列 | CONFIRMED+I-3 |
| DR-74 | interface_type varchar(16) 默认 OTHER + 7 值 CHECK；不据 name 推断 | CONFIRMED |
| DR-75 | mac_address varchar(64) 可空 trim/非空/无 Cc/Cf 保留大小写无唯一 | PROPOSED→CONTRACT |
| DR-76 | speed_mbps/mtu integer 可空 CHECK 1..2147483647；未知 null 0/负拒 | CONFIRMED+PROPOSED(I-2) |
| DR-77 | enabled boolean NOT NULL DEFAULT true | CONFIRMED |
| DR-78 | parent_interface_id 自关联 FK RESTRICT + 禁自引用 CHECK + 同 Resource 触发器 + 环检测 | CONFIRMED+DESIGN |
| DR-79 | resource_id 创建后不可改（PATCH 422 + DB 触发器兜底） | PROPOSED→CONTRACT |
| DR-80 | 删父接口存在未删子接口→409 reference_exists 返回子列表 | PROPOSED |
| DR-81 | 软删/恢复；恢复重检 name/Resource/parent；不覆盖新对象 | CONFIRMED |
| DR-82 | F007 注册 resource←Interface 检查器；F010 注册 interface←IPAddress；F007 预留 interface 引用集调用点 | CONFIRMED |
| DR-83 | metadata 为 Interface 自有 jsonb 列（§10 权威，覆盖 product I-5） | CONFIRMED |
| DR-84 | API 独立 /api/v1/interfaces + 新建 docs/api/F007.md | CONFIRMED |
| DR-85 | 环检测=应用层递归 + Resource 行 FOR UPDATE（复用 DR-71）+ DB 触发器兜底 | DESIGN→DATABASE |
| DR-86 | 迁移 0007_interfaces（down_revision=0006）对称可逆、单一 head、无回填 | DESIGN→DATABASE |
| DR-87 | D01 v5→v6 增 §5.6；§3/§5.2 同步 | PROPOSED→CONTRACT |
| DR-88 | 列表过滤 resource_id/interface_type/enabled/parent_interface_id/q；排序 name/type/speed/mtu/时间；q 大小写敏感子串 | PROPOSED→CONTRACT |

## 7. Layers 与分工
layers.database=true、backend=true、frontend=true、api_required=true。
- Database：docs/database/f007-interface.md（表/约束/索引/部分唯一/parent 触发器/FK/迁移 0007）；裁定 I-3、I-2 落地、q 索引；真 PG 验证项。
- Backend：models/interface.py；schemas/interface.py；services/interface.py（normalization 复用、parent 校验、FOR UPDATE 锁序、软删过滤、名称冲突）；注册 resource←Interface 检查器与 interface 引用集调用点；audit 白名单扩 interface；api/v1/interfaces.py+router；迁移 0007 落地。
- Frontend：Interfaces 区域数据源（F013 聚合消费）；Interface 创建/编辑表单（类型下拉、parent 选择器、enabled、422 点路径）；已删开关与 ADMIN 恢复。
- Contract：docs/api/F007.md 置 READY；签核 D01 v6 §5.6；固定 DR-75/79/80/84/87/88。

## 8. 风险与待核对项
交 DATABASE：I-3 键列（建议不建）；I-2 MTU 范围；parent 触发器+应用锁序闭环；resource_id FK RESTRICT vs CASCADE；部分唯一/索引集合；0007 up/down/up。
交 TEST_DESIGN：A1–A19；parent 环并发双会话；resource 软删与 Interface 创建并发；恢复重检；审计回滚；引用检查端到端。
交 CONTRACT：DR-75/79/80/84/87/88 固定；q 大小写策略；错误码/字段路径；I-2/I-4/I-5 记录。
跨 Feature：F004 DELETE /resources 随 F007 收窄；F010 承接 IP 绑定端与 interface←IPAddress；F013 承接聚合展示；F014 复用 name/mac/mtu/speed 口径。
已知不足：DB 触发器无法单独闭 parent 环并发（DR-85）；MAC 无严格正则（有意）。

## 9. 裁定 I-2 / I-4 / I-5（PROPOSED）
- **I-2（MTU）**：可空整数、单位字节、未知 null、原样存储；PROPOSED 范围 1..2147483647，不限定 1500/9000 等取值域（限定属新业务限定，须用户裁定）。
- **I-4（环检测与归属）**：环检测=应用层递归（主）+ DB 触发器兜底 + resources 行 FOR UPDATE 串行化（DR-71 复用）；归属 resource_id 创建后不可改（限制未确认操作，非新增业务规则）。
- **I-5（metadata）**：metadata 为 **Interface 自有** JSONB 列（§10 权威），不并入 Resource 公共 metadata；覆盖 product I-5 PROPOSED（其依据不足）。

## 10. 结论
Status **READY FOR DESIGN**，无 Blocking Questions。下一步：DATABASE 出 docs/database/f007-interface.md；TEST_DESIGN 核对 A1–A19；CONTRACT 定稿 docs/api/F007.md + D01 v6 §5.6 并签核 DR-84/87/88，完成后出 READY FOR IMPLEMENTATION。