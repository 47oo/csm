# F007 Interface 接口管理 — Test Report

本文件同时承载 TEST_DESIGN 与 TEST（TEST 阶段在同一文件追加执行结果）。两阶段分别记录版本、结论与证据；TEST_DESIGN 不填充执行 PASS。

---

## Test Design

- **版本**：TD-2（当前）；TD-1（2026-10-09）
- **日期**：TD-2 2026-10-09；TD-1 2026-10-09
- **角色**：Tester（TEST_DESIGN 模式）
- **结论**：`TEST DESIGN READY`
- **TD-2 变更（2026-10-09）**：DATABASE Gate（`docs/database/f007-interface.md` v1，DB-D64–D79）、CONTRACT Gate（`docs/api/F007.md` v1，含字段契约 §2、错误码 §1.2、分页排序过滤 §4、软删/恢复 §5/§6、Activity、审计白名单 §8、校验顺序 §6、并发 §7）与 `d01-conventions.md` v6（§3/§5.2/§5.6 Interface 字段口径）已定稿，`implementation.md`（BACKEND + FRONTEND COMPLETE）已提供。
  1. 依据定稿 Contract v1、DB v1（DB-D64–D79）、D01 v6 §5.6、implementation.md，关闭 TD-1 §8 全部 17 项 OPEN 复核项（见 §8-A）。
  2. TD-1 的表名/列名/约束名/FK 名/触发器全名与语义/嵌套键/错误路径/数值与字符串口径/迁移与单一 head/并发机制假设均与定稿一致。**OPEN-1 已裁定**：同 Resource 未删重名统一 **409 `CONFLICT{reason:"unique_conflict",field:"name"}`**（product A1 的 422 表述以 Contract 权威为准，Contract §1.2/§10 明确 A1 修正为 409）——TD-2 据此固定 V1/B1/B53 错误码判据。
  3. DR-85 parent 环并发由应用层 `SELECT ... FOR UPDATE`（resources 行）串行化 + 递归祖先校验 + DB `trg_interfaces_parent_valid` 兜底落定，TD-2 固定 B50/B51/B52 并发口径；验收判据除 OPEN-1 错误码外均不变。
- **依据**：
  - `docs/product/requirements-v3.md` revision 3（§4、§4.1、§10、§13、§18、§21、§22、§23、§27、§31 T12/T20/T23/T37/T39/T40/T41、§35.2 Q10-B、§35.3 D01）
  - `docs/features/F007/product.md`（PRODUCT `READY FOR ARCHITECT`，2026-10-09；A1–A19、I-1–I-5、明确排除项）
  - `docs/features/F007/architecture.md`（ARCHITECTURE `READY FOR DESIGN`，2026-10-09；§5 验证策略、DR-72–DR-88）
  - `docs/api/F007.md` v1（READY，Architect 2026-10-09；7 端点、字段契约、错误码、分页排序过滤、软删/恢复、Activity、审计、校验顺序、并发）
  - `docs/database/f007-interface.md` v1（DB-D64–D79；表/约束/索引/双触发器/FK/迁移 0007/I-2/I-3/I-5 落地）
  - `docs/architecture/d01-conventions.md` v6（§3/§5.2/§5.6 Interface 字段口径，签核 DR-87）
  - `docs/features/F007/implementation.md`（BACKEND + FRONTEND COMPLETE，2026-10-09）
  - `docs/api/F004.md` v3（复用错误码/权限/软删可见性/引用检查/恢复重检/审计口径）
  - `docs/database/f004-resource.md` v1、`docs/database/f005-bare-metal.md` v1、`docs/database/f006-virtual-machine.md` v1（迁移 0004/0005/0006 基座）
  - `docs/features/F006/test-report.md`（TD-2/TE-1：TD 模式、夹具/环境、机制级口径）
  - `docs/features/F004/test-report.md`、`docs/features/F005/test-report.md`（fixture 模式、真实 PG/Compose 证据）
  - `docs/project/project-plan.yaml` plan_revision 4，F007 条目（`current_stage: DATABASE`，`next_action: database 设计 interfaces；并行 tester 测试设计`）
  - `docs/project/handoff.md`、`docs/project/implementation-rules.md`、`AGENTS.md`、`.pi/skills/data-integrity/SKILL.md`
- **状态属性**：TD-2 READY 仅表示 A1–A19 可映射到可观察判据、边界/并发场景可执行、夹具与可验证性已与定稿 Contract v1/DB v1/D01 v6 逐项核对；**不代表测试已运行、不填充执行 PASS、不批准实现或合并**。TD-1 对 DATABASE/CONTRACT/D01 的待复核假设已由 TD-2 逐项关闭（§8-A），不再作为执行依据。F007 完整 §31 跨功能回归与 §32 上线验收不在本 Feature（见 §5）。执行结果见本文件 Test Execution（TE-1）。
- **TD-1 生效范围**：A1–A19 映射、V1–V30、B1–B54、夹具/环境设计、可验证性检查在本轮仍有效；TD-1「对 DATABASE/CONTRACT/D01 草案保留假设」不再作为执行依据，TEST 以定稿 Contract v1/DB v1/D01 v6 为准。

### 版本记录

| 版本 | 日期 | 变更 |
| --- | --- | --- |
| TD-1 | 2026-10-09 | 初版：A1–A19 映射 V1–V19 + 补充 V20–V30，边界/并发 B1–B54，夹具/环境设计，可验证性检查，不适用项；对 DATABASE/CONTRACT/D01 保留待复核假设（§8，17 项）。 |
| TD-2 | 2026-10-09 | 依据 DATABASE v1 / CONTRACT v1 / D01 v6 / implementation.md 关闭 §8 全部 17 项 OPEN（含裁定 OPEN-1 = 409 unique_conflict）；固定 DR-85 并发口径与 B50/B51/B52 断言；验收判据除 A1 错误码外不变。 |

> 复核基线（TD-2）：`docs/api/F007.md` v1（CONTRACT Gate，2026-10-09）、`docs/database/f007-interface.md` v1（2026-10-09，DB-D64–D79）、`docs/architecture/d01-conventions.md` v6、`docs/features/F007/implementation.md`。表名/约束名/FK/触发器/迁移名/嵌套键/错误路径/CONFLICT details/数值与字符串口径均已按定稿核对（见 §8-A），不再保留「草案待闭合」假设。

---

### 0. 数据完整性对应表（F007 范围）

仅列 F007 已确认且在实现后需验证的完整性/持久化项；方法依据 `.pi/skills/data-integrity/SKILL.md`。数据库列/约束以 `docs/database/f007-interface.md` v1（DB-D64–D79）定稿为准（TD-2 已逐项核对，见 §8-A）。

| 规则依据及版本 | 作用域/写入入口 | 数据库保证（DB v1 定稿） | 业务层保证 | 并发/生命周期边界 | 验证与证据 |
| --- | --- | --- | --- | --- | --- |
| §4.1/§10/§27（同 Resource 未删 name 唯一；区分大小写；禁内部空白；删除后可复用） | POST/PATCH `/api/v1/interfaces` | 部分唯一 `uq_interfaces_resource_id_name UNIQUE(resource_id,name) WHERE deleted_at IS NULL`；`ck_interfaces_name_not_blank/_trimmed/_no_ws_control/_length`；`name varchar(64)` | trim→非空→禁 Cc/Cf/内部空白；不折叠大小写；同 Resource 未删冲突 → 409 `CONFLICT{unique_conflict,field:"name"}` | 软删放行复用；恢复重检；唯一由 PG 兜底 | V1–V4/V18、B1–B10/B53；TE-1 已验证 |
| §10/T37（interface_type 默认 OTHER，不由 name 推断） | POST/PATCH | `interface_type varchar(16) NOT NULL DEFAULT 'OTHER'` + 7 值 CHECK | Pydantic 枚举默认 OTHER；不据 name 推断 | 无 | V5、B10–B12；计划验证 |
| §10/T37（enabled 默认 true） | POST/PATCH | `enabled boolean NOT NULL DEFAULT true` | 省略→true；显式 false 保存；显式 null→422 | 无 | V6、B13；计划验证 |
| §10/T39（speed_mbps 标称速率，正整数或 null） | POST/PATCH | `speed_mbps integer NULL CHECK 1..2147483647` | 可选严格整数；0/负/超限→422；null 合法 | 与实时流量无关，无换算 | V7、B14；计划验证 |
| §10/I-2（mtu 可空正整数，未知 null 非 0） | POST/PATCH | `mtu integer NULL CHECK 1..2147483647` | 可选严格整数；0/负/超限→422；null 合法 | 待 D01/Product 裁定范围（OPEN-6） | V7、B15；计划验证 |
| §10/T20（mac 可空无全局唯一） | POST/PATCH | `mac_address varchar(64) NULL` + trim/非空 CHECK；无 UNIQUE | trim 后非空或 null；空串/纯空白→422；保留大小写；不设唯一/正则（I-1） | 同 MAC 允许 | V10、B16/B17；计划验证 |
| §4.1/§21（resource 创建必填、须存在未删；创建后不可改） | POST/PATCH；DDL | `resource_id UUID NOT NULL FK→resources ON DELETE RESTRICT` + `ix_interfaces_resource_id`；不可改触发器 `trg_interfaces_immutable_resource` | 创建缺省/不存在/软删→422；PATCH resource_id→422 | 与 Resource 软删并发串行化（DR-85） | V11/V17、B18–B21/B31/B51；计划验证 |
| §10/T20（parent 同 Resource、禁自引用/循环） | POST/PATCH；DDL | 自关联 FK RESTRICT + `ck` 非自引用 + 触发器 `trg_interfaces_parent_valid`（拒跨 Resource/递归 CTE 断环）+ `ix_interfaces_parent_interface_id` | 应用层递归祖先校验 + resources 行 `SELECT ... FOR UPDATE`（DR-71 复用）→422 field=parent_interface_id | 触发器无法单独闭并发窗口；双会话用例 B50 | V8/V9、B22–B30/B50；计划验证 |
| §21（软删/恢复；恢复重检） | DELETE/POST restore | `deleted_at timestamptz NULL`；默认过滤 | ADMIN 恢复；重检 name 唯一/Resource 未删/parent 有效；失败不覆盖新对象 | 恢复与并发重建标识竞争 | V13、B32–B34；计划验证 |
| §21/§13/T23（删除引用检查；不隐式级联） | DELETE `/api/v1/interfaces/{id}` | 无独立物理删除路径；FK RESTRICT 兜底 | resource←未删 Interface（F007 注册，收窄 F004 DELETE resources）；interface←未删 IPAddress（F010 注册，F007 预留空集）；interface←未删子 Interface（DR-80 PROPOSED）→409 reference_exists | 引用列表 labels/明细 | V12、B35–B38；计划验证 |
| §22（CREATE/UPDATE/DELETE/RESTORE 写 Audit 同事务） | Service 层 `AuditService.record` | 复用 `audit_logs` append-only | object_type="interface"；白名单 {resource_id,name,interface_type,mac_address,speed_mbps,mtu,parent_interface_id,enabled,description,metadata}；异常同回滚 | 版本冲突无静默重试；并发一方成功 | V15、B40/B41；计划验证 |
| §23（权限矩阵；乐观锁） | `/api/v1/interfaces*` | 复用 `version integer NOT NULL DEFAULT 1 CHECK >=1` | `require_permission`；条件 UPDATE `WHERE version=:expected`；rowcount=0→409 | 两会话同 version 仅一成功 | V14、B39/B42；计划验证 |
| §10（metadata Interface 自有 JSONB） | POST/PATCH | `metadata jsonb NOT NULL DEFAULT '{}'` + object CHECK | object 校验；整值替换（DR-83） | 与 Resource metadata 解耦 | V23、B49；计划验证 |
| §27/DR-86（迁移 0007） | Alembic `0007_interfaces` | `down_revision=0006`，全表新建无回填，单一 head，对称可逆 | — | 真库 up/down/up | V22、B48；计划验证 |

---

## 1. 验收映射（product.md A1–A19 → 验证项）

执行环境：`Compose` = 干净环境 `docker compose up -d`（含 `migrate`/`bootstrap` 一次性服务）；`真实 PG` = 经 Compose `db` 或本机 PostgreSQL 的独立测试库（库名含 `test`）；`后端集成` = ASGI 应用 + 真实 PG 测试库（非 SQLite）；`静态` = 仓库/路由清单/源码静态检查；`前端` = 构建 + client 机制级用例（真实 API 集成以入口 Nginx 为准）。

| 验收（product.md） | 验证项 | 执行环境 | 可观察判据（PASS / FAIL） |
| --- | --- | --- | --- |
| A1 同 Resource 创建重名 Interface（大小写完全相同）被拒 | **V1**；**V18** DB 兜底 | 后端集成 + 真实 PG | PASS：同 resource 第二次同 name POST → 409 `CONFLICT{reason:"unique_conflict",field:"name"}`（Contract §1.2/§10 裁定，OPEN-1 已关闭）且库中仅一行；raw SQL 直插同 (resource_id,name) 未删被 `uq_interfaces_resource_id_name` 拒。FAIL：创建成功、落库两行、无部分唯一兜底 |
| A2 同 Resource 内 eth0 与 ETH0 视为不同名称并存 | **V2** | 后端集成 + 真实 PG | PASS：同 resource POST `eth0`、`ETH0` 均 201；raw 断言两行且 name 原样保留大小写。FAIL：第二个被拒、name 被折叠为小写 |
| A3 名称含内部空白被拒；首尾空白 trim；空名/控制字符拒 | **V3** | 后端集成 + 真实 PG | PASS：`"  eth0  "` → 201 且落库 `eth0`；`"eth 0"`（普通空格/Unicode 空白）、`""`、`"   "`、含 `\t`/`\x00`/Cf → 422；raw 直插未 trim/空/内部空白被 `ck_interfaces_name_format` 拒。FAIL：内部空白被接受、不 trim、空名落库、CHECK 缺失 |
| A4 软删后同名可重建；存活同名存在时创建失败 | **V4**；**V18** | 后端集成 + 真实 PG | PASS：软删同名后重建 201（新 id）；存活同名存在时创建被拒；raw 部分唯一仅约束 `deleted_at IS NULL`。FAIL：软删后仍被拒、存活重名成功 |
| A5 interface_type 省略→OTHER；name=bond0 类型省略仍 OTHER，不推断 BOND | **V5** | 后端集成 + 真实 PG | PASS：POST 省略 interface_type → 响应/落库 `OTHER`；`name="bond0"` 省略类型 → `OTHER`（非 BOND）；静态核对无据 name 推断逻辑。FAIL：默认值错误、按名称推断类型 |
| A6 enabled 省略→true；显式设置按值保存 | **V6** | 后端集成 + 真实 PG | PASS：省略 → true；显式 `true`/`false` 落库一致；raw 列默认 `true`。FAIL：省略为 false/null、显式值被忽略 |
| A7 speed_mbps 正整数接受、0/负拒（422）、可空 null | **V7**；**V18** | 后端集成 + 真实 PG | PASS：`speed_mbps=10000`/`null` 接受；`0`/`-1`/`2147483648` → 422；raw CHECK `1..2147483647` 拒越界。FAIL：0/负被接受、null 被转 0、CHECK 缺失 |
| A8 parent_interface 空允许；指向其它 Resource 的 Interface 拒（422） | **V8** | 后端集成 + 真实 PG | PASS：省略/`null` parent → 201；parent 指向另一 Resource 的 Interface → 422 `field="parent_interface_id"`；raw 直插跨 Resource 被 `trg_interfaces_parent_valid` 拒。FAIL：跨 Resource parent 被接受 |
| A9 parent_interface 自引用拒；A→B→A 环路拒（422） | **V9** | 后端集成 + 真实 PG | PASS：`parent_interface_id=自身 id`（PATCH）→ 422；建 A→B 后 PATCH A.parent=B 且 B.parent=A → 422；raw 触发器拒自引用/2 节点/3 节点环。FAIL：自引用/环被接受 |
| A10 mac_address 空可登记；两 Interface 同 MAC 均允许 | **V10** | 后端集成 + 真实 PG | PASS：mac 省略/`null` → 201；两条同 MAC 记录均 201 且落库同值；raw 无 UNIQUE 约束。FAIL：空 mac 被拒、同 MAC 第二个被拒 |
| A11 resource 缺失/不存在/已软删时创建失败（422） | **V11** | 后端集成 + 真实 PG | PASS：省略 resource、`null`、`""` → 422；随机 UUID → 422；指向已软删 Resource → 422（同字段语义）；响应无 Interface 行。FAIL：任一被接受 |
| A12 存在未删除 IP 引用时删除被拒并返回引用列表；不隐式级联；无引用可软删 | **V12**；**V26** | 后端集成 + 真实 PG | PASS：DELETE 无引用 Interface → 204 且写 DELETE audit；有未删子 Interface（DR-80）→ 409 `CONFLICT{reason:"reference_exists"}`，`details.references` 含子 `{object_type:"interface",object_id,label}`；IP 引用集在 F010 前为空集（预留调用点）；删除不级联子接口/不释放 IP。FAIL：被误删、无 references、隐式级联 |
| A13 恢复重检名称唯一与 Resource 有效性；名称被复用/Resource 仍删时恢复失败不覆盖 | **V13** | 后端集成 + 真实 PG | PASS：软删 Interface → restore → 200；name 被新对象复用 → 409（`unique_conflict` 或 `dependency_deleted`，按 Contract）；Resource 仍软删 → 409 `dependency_deleted`，`details.conflicts` 含 resource；旧对象保持软删、新对象不被覆盖。FAIL：restore 成功、覆盖新对象 |
| A14 权限：EDITOR 增改；VIEWER 只读；删除/恢复 ADMIN | **V14** | 后端集成 + 前端 + Compose | PASS：VIEWER POST/PATCH → 403 `FORBIDDEN{permission}`、GET 200；EDITOR POST/PATCH 201/200、DELETE/restore 403；ADMIN 成功；未认证 401；服务端强制（静态核对无绕过）。FAIL：越权成功、仅前端隐藏而服务端放行 |
| A15 CREATE/UPDATE/DELETE/RESTORE 写 Audit 且同事务；Activity 全角色 | **V15** | 后端集成 + 真实 PG | PASS：四 action 各产生一条 `audit_logs`（`object_type="interface"`、`object_id`=Interface UUID、UPDATE 含 before/after、白名单字段）；GET `/activity` 对 VIEWER/EDITOR/ADMIN 均 200；注入失败时业务变更与 audit 同回滚。FAIL：缺 action、不同事务、Activity 限权 |
| A16 一个 Interface 可绑定多个 IPAddress；解绑仅移除关系不释放（关系承载，执行 F010） | **V16**（静态）+ F010 | 静态/跨 Feature | PASS（F007 侧）：Interface 表不存 IP/CIDR，IP 侧持 `interface_id` 引用；F007 预留 interface 引用集调用点为空实现；不新增解绑/释放端点。F010 执行绑定/解绑/释放与 1:N 端到端。FAIL：F007 落 IP 字段、越权实现分配 |
| A17 类型不定义网卡分类；管理/业务/存储/IB 经 IPAddress→Network；Interface 不存 IP/CIDR/VLAN ID | **V17** | 静态 + 真实 PG | PASS：`interfaces` 列集合无 `ip`/`cidr`/`vlan_id`/`network_id`/`category` 类列；无据 type 推导分类逻辑；类型仅 7 值枚举。FAIL：出现这些列或分类推导 |
| A18 DB 对同 Resource 未删除 name 部分唯一兜底，真实 PG 验证 | **V18** | 真实 PG + 静态 | PASS：`pg_indexes`/`pg_constraint` 存在 `uq_interfaces_resource_id_name UNIQUE(resource_id,name) WHERE deleted_at IS NULL`；raw 直插存活重名被拒、软删后同名可插；MD5/普通索引清单一致。FAIL：缺部分唯一、为全量唯一、仅 ORM 层保证 |
| A19 Resource Detail Interfaces 区域可展示 Interface/MAC/Speed/MTU/IP/Network | **V19**（数据侧）+ F013 | 后端集成 + 前端 | PASS（F007 侧）：`GET /api/v1/interfaces?resource_id=<id>` 返回该 Resource 的 Interface 列表（含 mac/speed/mtu/interface_type、可展开 IP/Network 供聚合）；Resource Detail 展示实现归 F013。FAIL：接口不返回所需字段、过滤不生效。**聚合展示为 F013 不适用项** |

补充验证项（非直接 A 映射，但属实现后必须执行）：

| 验证项 | 内容 | 执行环境 | 判据 |
| --- | --- | --- | --- |
| **V20** PATCH exclude_unset / 不可变字段 | `resource_id` PATCH → 422；省略子字段保持；显式 null 仅清 nullable（mac/speed/mtu/parent/description）；必填显式 null→422；未知/只读字段→422 | 后端集成 + 真实 PG | PASS：语义逐项符合 D01 §4 与 Contract；库值/`version` 不变于被拒请求。FAIL：省略被重置、显式 null 被忽略、resource_id 被改 |
| **V21** 列表分页/排序/过滤 | Query `resource_id/interface_type/enabled/q/parent_interface_id/deleted/page/page_size/sort/order` | 后端集成 + 真实 PG | PASS：分页 total/边界正确；`sort∈{name,interface_type,speed_mbps,mtu,created_at,updated_at}` 生效；过滤组合正确；非 UUID 参数→422；`q` 子串大小写策略按 DR-88/Contract。FAIL：分页/排序/过滤错误 |
| **V22** 迁移 0007 | Alembic up/down/up + 单一 head | 真实 PG | PASS：`alembic heads` 单一 `0007_interfaces`（`down_revision=0006`）；up 建表/约束/索引/函数触发器；down 逆序且 0006 对象保留；re-up 集合一致；无回填。FAIL：多 head、不对称 |
| **V23** metadata JSONB | object CHECK / 整值替换 / 非法类型 | 后端集成 + 真实 PG | PASS：`{}` 默认；object 接受；`[]`/标量→422；raw 非 object 被 CHECK 拒；PATCH metadata 整值替换。FAIL：非法类型落库、合并语义 |
| **V24** 乐观锁并发 | 两独立连接同 version PATCH | 后端集成 + 真实 PG（真提交） | PASS：一方 200 且 `version+1`；另一方 409 `VERSION_CONFLICT{current_version}`；最终库值来自成功方，无丢失更新。FAIL：双成功、无 409 |
| **V25** 审计同事务回滚 | 注入 audit 失败 | 后端集成 + 真实 PG（真提交） | PASS：业务列与 audit 行同事务双回滚，最终持久化为旧值/无新行。FAIL：半提交、回滚留痕 |
| **V26** Resource 侧引用保护端到端 | F007 注册 resource←未删 Interface 检查器 | 后端集成 + 真实 PG | PASS：有未删 Interface 的 Resource DELETE → 409 `reference_exists`，references 含 interface；软删 Interface 后 Resource 可删。FAIL：Resource 被误删/无 references |
| **V27** parent 删除保护 | 有未删子 Interface 的父接口 DELETE | 后端集成 + 真实 PG | PASS：409 `reference_exists`，references 含子 interface；删子后可删父（DR-80）。FAIL：父被误删、无引用列表 |
| **V28** 归属固定（resource 不可变） | PATCH resource_id / DB 触发兜底 | 后端集成 + 真实 PG | PASS：API 422；raw UPDATE `resource_id` 被 `trg_interfaces_immutable_resource` 拒（`restrict_violation`）。FAIL：可改归属 |
| **V29** 响应契约 | Interface 响应字段/嵌套 | 后端集成 | PASS：含 `id、resource{id,hostname}、name、interface_type、mac_address、speed_mbps、mtu、parent_interface{id,name}|null、enabled、description、metadata、version、created_at/updated_at、deleted_at`。FAIL：字段缺失/命名错误/嵌套形态错误 |
| **V30** 校验顺序 | POST/PATCH 校验优先级 | 后端集成 | PASS：POST 401→403→body(422)→resource(422)→parent(422)→name 唯一(409)→写+Audit→201；PATCH 401→403→body(422)→可见性(404)→parent(422)→version(409)→name 唯一(409)→写+Audit→200。FAIL：顺序错误（如版本冲突先于 parent 校验） |

---

## 2. 边界与并发场景（B 编号，TEST 阶段执行）

| 编号 | 场景 | 步骤 | 判据 |
| --- | --- | --- | --- |
| B1 | 同 Resource 精确重名 | 同 resource 两次 POST 同 name | 第二次被拒（V1，错误码按 CONTRACT）；库中一行 |
| B2 | 大小写区分 | 同 resource `eth0`、`ETH0` | 均 201；两行；name 原样 |
| B3 | 首尾空白 trim | `"  eth0  "`、`"\teth1\n"` | 201；落库 `eth0`/`eth1` |
| B4 | 内部空白 | `"eth 0"`、`"eth\u00a00"`（Unicode 空白）、`"eth  0"` | 均 422；raw CHECK 拒 |
| B5 | 空名/纯空白 | `""`、`"   "` | 422 |
| B6 | 控制字符 | 含 `Cc`（`\x00`/`\x1f`）、`Cf`（`\u200b`） | 422 |
| B7 | name 长度 | 64 字符、65 字符 | 64 成功；65→422/`varchar(64)` 拒 |
| B8 | 软删后复用 | 软删同名→重建同名 | 201，新 id |
| B9 | 恢复重检名称冲突 | A 软删→重建同名 B→restore A | restore 失败（409）；B 不被覆盖；A 保持软删 |
| B10 | 类型省略默认 | POST 省略 interface_type | 201 `OTHER` |
| B11 | 不据名推断 | `name="bond0"`/`"vlan100"`/`"br0"` 省略类型 | 均 `OTHER` |
| B12 | 非法类型值 | `interface_type="ETHERNET"`/`""`/`null` | 422；raw CHECK 拒 |
| B13 | enabled 语义 | 省略 / `true` / `false` / `null` | 省略→true；显式值保存；`null`→422 |
| B14 | speed_mbps 边界 | `null`/`1`/`10000`/`2147483647`/`0`/`-1`/`2147483648`/`"100"` | 正例接受；0/负/超限/字符串→422；raw CHECK 拒 |
| B15 | mtu 边界 | 同 B14（可空正整数） | 同上；未知 null 不为 0 |
| B16 | mac 语义 | 省略 / `null` / `"AA:BB:CC:DD:EE:FF"`（保留大小写）/ `""` / `"   "` | null 合法；格式原样；空串/纯空白→422 |
| B17 | mac 长度/重复 | 64 字符、65 字符；两条同 MAC | 64 成功；65→422；同 MAC 均允许（无唯一） |
| B18 | resource 缺失 | 省略 resource / `null` / `""` | 均 422 |
| B19 | resource 不存在 | 随机 UUID | 422；无行 |
| B20 | resource 已软删 | 软删 Resource 后创建 Interface | 422（同字段语义） |
| B21 | resource 类型无限制 | BARE_METAL 与 VIRTUAL_MACHINE 各建 Interface | 均 201（无类型限制） |
| B22 | parent 空 | 省略 / `null` parent | 201 |
| B23 | parent 跨 Resource | parent 指向另一 Resource 的 Interface | 422；raw 触发器拒 |
| B24 | parent 自引用 | PATCH parent=自身 id；raw 直插自引用 | 422（API）；触发器拒 |
| B25 | parent 2 节点环 | A→B，再 PATCH A.parent=B 使 B.parent=A（或 A.parent=B→B.parent=A） | 422；触发器拒 |
| B26 | parent 3 节点环 | A→B→C，再 PATCH C.parent=A | 422；触发器拒 |
| B27 | parent 不存在/软删 | parent 随机 UUID；软删 parent 后引用 | 422；库值不变 |
| B28 | parent 改父成环 | 通过 PATCH parent_interface_id 制造环 | 422；库值/`version` 不变 |
| B29 | DDL 触发器负例（raw） | raw 直插/更新：自引用、跨 Resource parent、2/3 节点环 | 均被 `trg_interfaces_parent_valid` 拒；合法插入成功 |
| B30 | 归属不可变触发器（raw） | raw UPDATE `resource_id` | 被 `trg_interfaces_immutable_resource` 拒（`restrict_violation`） |
| B31 | resource_id PATCH | PATCH `resource_id`（含同值） | 422（不可变字段）；库值不变 |
| B32 | 软删默认隐藏 | 软删后 GET 详情/列表（默认） | 404/不在列表；`deleted` 过滤按 Contract 可见性 |
| B33 | 恢复成功 | 软删→restore（name/Resource/parent 均有效） | 200；数据不变；`deleted_at=null` |
| B34 | 恢复依赖失效 | Resource 软删后 restore Interface | 409 `dependency_deleted`，conflicts 含 resource；保持软删 |
| B35 | 无引用软删 | DELETE 无子接口/无 IP 引用 | 204；写 DELETE audit；行保留 `deleted_at` |
| B36 | 子接口引用删除保护 | DELETE 父（有未删子） | 409 `reference_exists`，references 含子 interface（DR-80） |
| B37 | Resource 侧引用保护 | DELETE 有未删 Interface 的 Resource | 409 `reference_exists`，references 含 interface（F007 检查器）；软删后可删 |
| B38 | IP 引用集预留（F010） | 调用 interface 引用集检查 | F010 落地前为空集，不误报；预留调用点存在（静态核对） |
| B39 | 权限矩阵 | 逐端点 VIEWER/EDITOR/ADMIN/未认证 | 符合 §23；服务端强制 |
| B40 | 四 action Audit | CREATE/UPDATE/DELETE/RESTORE | 各一条；`object_type="interface"`；UPDATE 含 before/after 白名单字段；Activity 全角色 200 |
| B41 | 审计同事务回滚 | 注入 audit 失败（创建/更新/删除） | 业务与 audit 同回滚；最终持久化为旧值/无新行 |
| B42 | 乐观锁并发（真提交） | `committed_engine` 两连接同 version PATCH | 一方 200 且 version+1；另一方 409 `VERSION_CONFLICT`；无丢失更新 |
| B43 | PATCH exclude_unset | 仅含部分字段；整体 `null`/非对象/未知键 | 省略保持、整体非法→422 |
| B44 | 显式 null 清空 nullable | PATCH mac/speed/mtu/parent/description 为 null | 清空为 null |
| B45 | 必填显式 null | PATCH/create name=null、resource=null、interface_type=null、enabled=null | 422 |
| B46 | 未知/只读字段 | body 含 `id`/`version`/`created_at` 等 | 422 |
| B47 | 列表分页/排序/过滤/q | V21 全参数组合 | 分页 total/排序/过滤正确；非 UUID→422 |
| B48 | 迁移 0007 up/down/up | `upgrade head`→`downgrade 0006`→`upgrade head`；`alembic heads` | 各步 0；单一 head `0007_interfaces`；down 后表/函数消失、0006 对象保留；re-up 一致 |
| B49 | metadata JSONB | `{}`/object/list/标量/整值替换；raw 非 object | object 接受；非 object→422/CHECK 拒；整值替换 |
| B50 | **parent 环并发双会话（DR-85）** | 两独立连接（真提交）：会话 A `SELECT ... FOR UPDATE` resources 行后 PATCH A.parent=B，会话 B 同 resource 反向 PATCH B.parent=A，并发提交 | 因 resources 行锁序串行化，至多一方成功；最终持久化无环（递归查询无环）；失败方 422；断言最终库图，不仅“未抛异常” |
| B51 | **resource 软删与 Interface 创建并发（DR-85）** | 一会话软删 Resource，另一会话并发 POST Interface 指向该 Resource | 串行化后二者不共存：或创建成功而软删被引用检查拒绝（409 reference_exists），或软删成功而创建 422；断言最终持久化一致（不存在「已软删 Resource + 未删 Interface」） |
| B52 | 恢复与并发重建标识 | 软删 A 后并发：会话 1 restore A、会话 2 创建同名 B | 至多一方成功；部分唯一/应用检查不产生双存活同名 |
| B53 | 部分唯一 raw 兜底 | raw 直插同 (resource_id,name) 未删；软删后同名 | 存活重名被 `uq_interfaces_resource_id_name` 拒；软删后同名成功 |
| B54 | FK 物理语义（机制级） | raw 物理 `DELETE FROM resources`（被 Interface 引用）；物理删父接口（被引用） | 被 FK RESTRICT 阻止（`confdeltype='r'`）；报告标注机制级（API 无物理删除路径） |

并发说明：B41/B42/B50/B51/B52 及任何「失败不留痕/并发」用例必须使用 `committed_engine`（真实连接真实提交）或显式事务控制，断言**最终持久化状态+最终关系图**，不仅「未抛异常」。B1–B38/B43–B48/B53/B54 中涉及部分唯一、CHECK、FK、触发器、JSONB、迁移的断言必须在真实 PostgreSQL 执行（SQLite/Mock 不作约束/并发/触发器证据）。

---

## 3. 夹具 / 环境设计

**复用 F001/F004/F005/F006 `backend/tests/conftest.py`（不改其护栏语义）**：
- `test_database_url`：独立测试库 + 安全护栏（库名含 `test`、`TEST_DATABASE_URL != DATABASE_URL`）；未设置则 skip 并告警，不静默改 SQLite。
- `pg_engine`：会话级 `DROP SCHEMA public CASCADE` + `CREATE SCHEMA public` + `alembic upgrade head`（含 0007），会话结束清理。
- `db_session`：函数级外层事务 + savepoint，回滚不跨用例污染（用于单事务用例）。
- `committed_engine`：真实提交用例（B41/B42/B50/B51/B52 及持久断言），teardown `TRUNCATE` 清理（排除 `alembic_version`；确认 `interfaces` 在动态清理清单内），新开连接断言最终持久化。
- `alembic_runner`：迁移 up/down/up 用例（V22/B48）。

**复用 F002 认证/权限 fixture（`auth_session_factory`/`auth_app`/`api_client`/`bootstrap_admin`/`make_user`/`login`）**：`make_user(role, status=ACTIVE)`；`login` 复用 Cookie 罐；`api_client` 命中真实 ASGI 应用。F007 权限/审计证据使用**真实业务端点** `/api/v1/interfaces*`。

**复用 F004 的 Cluster/Resource helper 与约束断言模式**：`role_client_factory`、`_create_cluster`、`_create`（`test_resources.py`）；`insert_cluster`/`insert_resource` raw 辅助（`test_resource_constraints.py`）；F004/F005/F006 的软删/恢复、乐观锁 `two-session`、raw SQL 约束断言模式直接复用。B37/V26 需在 F004 `DELETE /resources` 上验证 F007 注册的检查器。

**F007 新增测试侧夹具/断言（由 Tester 落地于测试侧，实现阶段由 Backend 提供接口）**：
- `resource_factory`：创建 BARE_METAL / VIRTUAL_MACHINE Resource（可附 detail），返回对象与 `version`；供 resource 归属用例复用。
- `interface_factory`：创建 Interface（`resource_id` + 可选字段），返回对象与 `version`；供 A1–A19、B1–B54 复用。
- `INTERFACE_CASES`：表驱动数据（name trim/大小写/内部空白/控制字符/长度、type 省略/非法、enabled 省略/显式/null、speed/mtu 边界、mac 空/大小写/重复/长度、resource 缺失/不存在/软删），供 V1–V11/V18/V20 与 B1–B21 共用，确保 API 与 DB 同一口径。
- `PARENT_CASES`：parent 空/跨 Resource/自引用/2 节点环/3 节点环/不存在/软删/改父成环，供 V8/V9 与 B22–B30。
- `assert_interface_row(engine, id, expected)`：raw SQL 断言 `interfaces` 各列值/`IS NULL`，供 V5–V11/V17/V23 与边界用例。
- `assert_partial_unique(engine, resource_id, name, deleted)`：raw 直插断言部分唯一仅在 `deleted_at IS NULL` 生效，供 A1/A4/V18/B53。
- `assert_parent_trigger(engine, ...)`：raw SQL 直插四类非法 parent（自引用/跨 Resource/2 节点环/3 节点环）断言被 `trg_interfaces_parent_valid` 拒，合法插入成功，供 A8/A9/B29。
- `assert_immutable_resource_trigger(engine, id)`：raw UPDATE `resource_id` 断言被 `trg_interfaces_immutable_resource` 拒，供 V28/B30。
- `assert_reference_protection(client, ...)`：端到端断言 Resource↔Interface 与 parent←子接口 409 `reference_exists`+references，供 V12/V26/V27/B36/B37。
- `assert_restore_recheck(...)`：恢复重检 name/Resource/parent，供 A13/B9/B34。
- `assert_audit_same_txn(...)`：注入 audit 失败断言双回滚，供 V15/V25/B41。
- `two_session_version_conflict` / `two_session_parent_cycle` / `two_session_resource_vs_interface`（复用 F004 模式）：真实提交并发，供 B42/B50/B51/B52。
- `two_session_parent_cycle` 必须显式获取 resources 行锁（复现 DR-85 锁序）以验证串行化，而非仅顺序调用。

**F007 前端夹具**：复用 F005/F006 `smoke:client` 机制，新增 Interface 表单（类型下拉、parent 选择器、enabled、mac/speed/mtu）、已删开关与 ADMIN 恢复、422 点路径映射、`resource_id` 列表调用断言，供 V19 数据侧与前端机制级用例。

**环境**：Docker / Compose 可用（F001–F006 TE 已证）；真实 PG 经 Compose `db`（`postgres:16`）。若以非默认入口端口运行 Compose，F007 写端点（POST/PATCH）需覆盖同源 CSRF 行为；应在与既有修复一致的 Nginx 配置下执行，或在报告标注该环境限制。

### 3.1 当前环境可执行性评估

| 验证项 | 环境要求 | 当前评估 | 降级/替代 |
| --- | --- | --- | --- |
| V1–V29、B1–B47/B49/B53/B54 | 真实 PostgreSQL 实例 + 后端集成 | 经 Compose `db` 可满足（F001–F006 已证） | 无 PG 时 skip 并标 BLOCKED，**不得**用 SQLite 替代约束/并发/触发器证据 |
| V22/B48 迁移 up/down/up | Alembic + 真实 PG | 可执行；依赖 0007 定稿 | 迁移未定稿则相关断言 BLOCKED，不降验收 |
| V19 前端数据侧 | Node 22 + 构建 | 可执行（F001–F006 smoke:client 已证） | 真实浏览器 DOM 渲染非必要判据（同 F001–F006） |
| B50/B51/B52 并发 | 真实并发提交 fixture | 可执行（复用 `committed_engine`） | 无 PG 时 BLOCKED；不得以顺序调用替代并发证据 |
| Compose 冒烟 / 真实 API 集成 | Docker 可用、端口可用 | 可执行 | 镜像/端口问题记 BLOCKED 并说明 |

---

## 4. 可验证性检查

| 项 | 判定 | 说明 |
| --- | --- | --- |
| A1/A2/A4 name 唯一与大小写 | **可验证（API + DB）** | V1/V2/V4/V18 + B1–B9/B53；部分唯一 + 应用检查双路径，真实 PG |
| A3 name 归一化/控制字符 | **可验证（API + DB）** | V3 + B3–B7；422 与 CHECK backstop 双路径 |
| A5/A6 默认值/不推断 | **可验证（API + 静态）** | V5/V6 + B10–B13；默认值落库 + 静态核对无名称推断 |
| A7 speed/mtu 数值 | **可验证（API + DB）** | V7 + B14/B15；响应 + raw CHECK |
| A8/A9 parent 约束 | **可验证（API + DB）** | V8/V9 + B22–B30；应用递归 + 触发器 + raw 负例 |
| A10 mac | **可验证（API + DB）** | V10 + B16/B17；无唯一约束 raw 断言 |
| A11 resource 归属 | **可验证（API + DB）** | V11 + B18–B21/B31；FK + 应用校验 |
| A12/A13 生命周期/引用/恢复 | **可验证（端到端）** | V12/V13/V26/V27 + B32–B38/B9/B34；真实端到端 409 |
| A14 权限矩阵 | **可验证（端到端 + 静态）** | V14 + B39；真实端点 + 服务端强制 |
| A15 审计 | **可验证（端到端 + 真提交）** | V15/V25 + B40/B41；四 action + 同事务回滚 |
| A16 1:N 关系 | **不适用（F010）** | F007 侧仅静态核对不落 IP 字段 + 预留调用点空集（V16/B38）；端到端归 F010 |
| A17 不落 IP/CIDR/VLAN/分类 | **可验证（静态 + DB）** | V17；列集合 raw 断言 + 源码静态检查 |
| A18 DB 部分唯一兜底 | **可验证（DB）** | V18 + B53；真实 PG raw 直插 |
| A19 聚合展示 | **不适用（F013）** | F007 侧仅验数据端点（V19）；Resource Detail 聚合归 F013 |
| V22/B48 迁移 0007 | **可验证（DB）** | 真实 PG up/down/up + 单一 head |
| B50/B51/B52 并发 | **可验证（真提交）** | 复用 `committed_engine`，断言最终关系图 |
| B54 FK 物理语义 | **机制级** | API 无物理删除路径；raw SQL 验证 `confdeltype`，报告须显式标注证据边界 |
| 时间/稳定 ID 契约 | **可复用 F004 证据** | F007 复用 Resource 时间/ID/乐观锁基座；不重复声明完整回归，仅新增 B42 |

口径明确记录：**A12/A13/V26/V27/B36/B37 为真实业务端点端到端**；**A18/B29/B30/B53/B54 为真实 PG raw SQL 机制级**；**A16/A19 为跨 Feature 不适用项**；**T12/T40/T41 的 F007 子集**（Interface 名称唯一/复用/区分大小写/内部空白/恢复重检）在本 Feature 验证；**T20 的 F007 子集**（parent 跨 Resource/自引用/环、MAC 可空）在本 Feature 验证；**T37 的 F007 子集**（interface_type 默认 OTHER 不推断、enabled 默认 true）在本 Feature 验证；**T39 的 F007 子集**（speed_mbps 标称速率）在本 Feature 验证；**T23/T24/T25 的完整回归不在本 Feature**，不得以 F007 局部 PASS 拼成整条通过。

---

## 5. 范围与不适用项声明

- **IP 绑定/分配/解绑/释放/容量（§13/§14/§20，F008–F010）**：F007 不落 IP/CIDR/VLAN ID/所属 Network；IP↔Interface 的 1:N、解绑不释放、删除 IP 引用保护归 **F010**。F007 仅预留 interface 引用集调用点（空集）并静态核对。
- **列表/搜索/Dashboard/Cluster Detail 聚合（§17/§19/§20/§28，F013）**：完整列表、模糊搜索/pg_trgm、Dashboard、Cluster Detail 聚合、Resource Detail Interfaces 展示区域归 **F013**；F007 仅承载 `/api/v1/interfaces` 列表/过滤/排序（A19 数据侧）与接口详情的 IP/Network 展开数据源。
- **CSV / Excel 导入（§24，F014）**：Interface 导入模板、导入与 API 共用校验口径的执行归 **F014**；F007 仅供复用字段口径，不执行导入用例。
- **完整 Audit 查询页（§22，F015）**：归 **F015**；F007 仅验证 Interface 四 action 的资源级 Activity 快照。
- **Service/ServiceEndpoint（§15/§16，F011–F012）**：F007 不涉及。
- **Bond/Bridge/VLAN 完整拓扑、链路聚合、VLAN 划分建模**：明确排除；parent 仅基本父子关系并禁环。
- **MAC 全局唯一、自动发现、实时速率/流量/状态采集、监控/调度（§34）**：明确排除；speed_mbps/enabled 为登记值非实时。
- **据接口名推断 interface_type / 由类型推导网卡分类或 IP 归属**：明确排除（T37）。
- **完整 T12/T20/T23/T24/T25/T37/T39/T40/T41 回归与 §32 上线验收**：F007 仅承载 Interface 相关子集；跨 Feature 权限/审计完整回归与 §32 验收归 F016。**不声明上述条款完整通过**。
- **真实浏览器 DOM 渲染**：非 F007 必要判据（同 F001–F006），前端以构建 + client 机制级 +（如要求）入口真实 API 集成为准。
- **I-2/I-4/I-5**：架构 §9 已裁定（I-2 范围 1..2147483647 不限定取值域、I-4 环检测应用+触发器+行锁且归属不可改、I-5 metadata 为 Interface 自有）；若 CONTRACT/D01 v6 或用户裁定变更则升 TD-2 调整 V17/V23/B30/B49。

---

## 6. 风险与待核对项总结

| 项 | 评估 | 处理 |
| --- | --- | --- |
| V1–V29、B1–B47/B49/B53/B54（真实 PG + 后端集成） | Docker/Compose 可用（F001–F006 已证）；**可执行** | 无 PG 时相关项 BLOCKED，不降验收 |
| V22/B48 迁移 0007 | DATABASE Gate v1 已定稿 | TE-1 已实际执行（真实 PG up/down/up + 单一 head）；结果见 Test Execution 命令 3 |
| B50/B51/B52 并发 | 需真实并发提交 fixture + resources 行锁 | 复用 `committed_engine`；断言最终关系图 |
| B54 物理 FK RESTRICT | API 无物理删除路径 | raw SQL 机制级验证 `confdeltype`，报告显式标注 |
| V19 前端 | 构建 + client 机制级 | 若要求真实前后端集成，经入口 Nginx 验证；CSRF 端口风险承 F004/F005/F006 TE |
| DATABASE/CONTRACT/D01 定稿状态 | **已定稿**（DB v1 / Contract v1 / D01 v6） | TD-2 已逐项核对（§8-A）；TE-1 已按定稿执行 |
| A1 错误码 409 vs 422 | 已裁定：统一 **409 `unique_conflict{field:"name"}`** | OPEN-1 已关闭；V1/B1/B53 按 409 断言（TE-1 已验证） |
| 触发器/约束命名与 I-3 键列 | DB v1 定稿已核对（OPEN-2/3/4/5 已关闭） | 见 §8-A；TE-1 命令 4/5/6 已在真实 PG 核验 |

---

## 7. 独立性与执行口径（TEST 阶段适用）

- Backend pytest 由 Tester 独立重跑，不复用实现者数字。
- 迁移、约束、触发器、CHECK、FK、部分唯一、JSONB 由 Tester 在独立库（库名含 `test`）以 Alembic / raw SQL 直接执行；不连接生产或未知数据库。
- 接口验证响应内容、类型、业务边界、非法输入与错误语义；只读功能（GET/activity）确认无业务写副作用。
- 前端验证状态、交互、错误与未知值处理；已批准范围要求真实前后端集成时经入口 Nginx 验证真实 API，不以 Mock 代替。
- 修复后按影响重测；首次设计检查与最终验收分别记录版本与证据。

---

## 8. OPEN 复核项（TD-1 提出，TD-2 全部关闭）

> **TD-2（2026-10-09）状态：全部 CLOSED。** DATABASE Gate（`docs/database/f007-interface.md` v1，DB-D64–D79）、CONTRACT Gate（`docs/api/F007.md` v1）与 `d01-conventions.md` v6 §5.6 已定稿；下表各假设逐项与定稿核对，**无判据差异**（OPEN-1 由 Contract 裁定为 409 unique_conflict，已更新 V1/B1/B53 判据）。TD-1 的「待定稿假设」不再作为执行依据，TEST 以定稿 Contract v1/DB v1/D01 v6 为准。

| # | TD-1 假设（待复核） | 影响验证项 | Owner | 状态 |
| --- | --- | --- | --- | --- |
| OPEN-1 | A1 重名错误码：product A1 写 422，architecture §2 写 409 `unique_conflict{field:"name"}` | V1/B1/B53 | Architect/Product（Contract） | CLOSED（裁定 409，见 §8-A） |
| OPEN-2 | 表名 `interfaces`、列名/类型（`resource_id`/`name varchar(64)`/`interface_type varchar(16)`/`mac_address varchar(64)`/`speed_mbps`/`mtu`/`parent_interface_id`/`enabled`/`description`/`metadata jsonb`/`version`/时间戳/`deleted_at`） | V5–V11/V17/V18/V23/V29、B14–B17/B49 | Database | CLOSED |
| OPEN-3 | 约束/索引名：`uq_interfaces_resource_id_name`、`ck_interfaces_name_format`、`ix_interfaces_resource_id`、`ix_interfaces_parent_interface_id`、7 值 CHECK、非自引用 CHECK、metadata object CHECK | V3/V7/V8/V17/V18、B4/B12/B14/B15/B29/B49 | Database | CLOSED（约束名细化为 `ck_interfaces_name_not_blank/_trimmed/_no_ws_control/_length` 等） |
| OPEN-4 | 触发器全名与语义：`trg_interfaces_parent_valid`（拒自引用/跨 Resource/递归 CTE 断环）、`trg_interfaces_immutable_resource`（resource_id 变更 `restrict_violation`） | V8/V9/V28、B24–B30 | Database | CLOSED |
| OPEN-5 | I-3 归一化键列：架构建议不建独立列，直接对 `name` 建部分唯一（无折叠 + `CHECK name=btrim(name)`） | V1/V2/V4/V18、B53 | Database | CLOSED（DB-D65，不建 name_key） |
| OPEN-6 | I-2 mtu 范围：架构 PROPOSED 1..2147483647、不限定 1500/9000 取值域 | V7、B15 | Product/D01 | CLOSED（DB-D69/D01 v6 §5.6，不限取值域） |
| OPEN-7 | I-1 name 长度 64、mac_address 长度 ≤64/无正则、speed_mbps 上限 2147483647 | V3/B7、V10/B16/B17、V7/B14 | Architect/Database（D01 v6 §5.6） | CLOSED |
| OPEN-8 | resource_id 创建后不可改（PATCH 422 + DB 触发器兜底，DR-79 PROPOSED） | V20/V28、B30/B31 | Contract/Database | CLOSED（DB-D74，DR-79 固定） |
| OPEN-9 | parent 删除保护（DR-80 PROPOSED）：有未删子接口时删父 → 409 `reference_exists` 返回子列表 | A12/V27、B36 | Contract | CLOSED（Contract §1.2/§6.5，DR-80 固定） |
| OPEN-10 | metadata 归属：架构 DR-83 CONFIRMED 为 Interface 自有；product I-5 为 PROPOSED（归 Resource） | V23/B49/V17 | Contract | CLOSED（DB-D72/D01 v6 §5.6，Interface 自有） |
| OPEN-11 | 列表过滤/排序/q 大小写（DR-88 PROPOSED）：`resource_id/interface_type/enabled/q/parent_interface_id/deleted/page/page_size/sort/order`；q 子串大小写敏感 | V21、B47 | Contract | CLOSED（Contract §4，DR-88 固定） |
| OPEN-12 | 恢复失败错误码优先级：name 被复用（`unique_conflict`）vs Resource 仍删（`dependency_deleted`） | A13/V13、B9/B34 | Contract | CLOSED（Contract §6.6，name 复用优先） |
| OPEN-13 | F010 预留：interface←未删 IPAddress 引用集调用点存在且落地为空集；F007 不实现 IP 关系 | A12/V16、B38 | Architect/Backend（跨 Feature） | CLOSED（Contract §6.5/§9，预留空集） |
| OPEN-14 | 迁移 `0007_interfaces`（`down_revision=0006`）单 head、对称可逆、无回填；down 后对象消失、0006 保留 | V22、B48 | Database | CLOSED（DB-D78） |
| OPEN-15 | 列表 `q` 索引策略（pg_trgm/GIN 是否启用）；架构建议不建 metadata GIN/pg_trgm | V21 | Database | CLOSED（DB-D77，不建 q/metadata 索引；pg_trgm 为 F001 基线扩展，非 F007 引入） |
| OPEN-16 | `resource_id` FK 动作：架构为 ON DELETE RESTRICT（非 CASCADE） | B54/V17 | Database | CLOSED（DB-D64/DB-D76） |
| OPEN-17 | 校验顺序（POST/PATCH 优先级）与 CONFLICT details 结构（`references[]`/`conflicts[]` 字段与 label） | V30/V1/V12/V26/V27 | Contract | CLOSED（Contract §1.2/§6） |

### 8-A. OPEN 关闭记录（逐项核对依据）

| # | 定稿核对结论 | 依据 |
| --- | --- |
| OPEN-1 | **重名统一 409 `CONFLICT{reason:"unique_conflict",field:"name"}`**（创建/PATCH/恢复重检）；product A1 的 422 表述以 Contract 权威口径修正 | Contract §1.2/§6.2/§6.4/§6.6/§10；F007 product §1.2 |
| OPEN-2 | 表 `interfaces` 15 列，ORM 属性 `metadata` 物理列 `metadata`（实现 `meta` 属性映射细节见 implementation.md）；列名/类型与 TD-1 一致 | DB v1 §2；0007；TE-1 命令 6 |
| OPEN-3 | `pk_interfaces`、`fk_interfaces_resource_id_resources`、`fk_interfaces_parent_interface_id_interfaces`、`uq_interfaces_resource_id_name`、`ix_interfaces_resource_id`、`ix_interfaces_parent_interface_id`；CHECK 名细化为 `ck_interfaces_name_not_blank/_trimmed/_no_ws_control/_length`、`ck_interfaces_interface_type`、`ck_interfaces_mac_address_format`、`ck_interfaces_speed_mbps_range`、`ck_interfaces_mtu_range`、`ck_interfaces_parent_not_self`、`ck_interfaces_metadata_object`、`ck_interfaces_version` | DB v1 §2；TE-1 命令 6 |
| OPEN-4 | `trg_interfaces_parent_valid`（BEFORE INSERT/UPDATE；拒自引用/跨 Resource/软删父/递归断环）、`trg_interfaces_immutable_resource`（BEFORE UPDATE id/resource_id→restrict_violation） | DB-D74/DB-D75；TE-1 命令 6/7 |
| OPEN-5 | 不建归一化键列；`ck_interfaces_name_trimmed` 保证存储值恒等归一化键；部分唯一 `(resource_id,name) WHERE deleted_at IS NULL` | DB-D65/DB-D66 |
| OPEN-6 | mtu `integer NULL CHECK 1..2147483647`，不限取值域、未知存 null | DB-D69；D01 v6 §3/§5.6 |
| OPEN-7 | name 1–64、mac_address ≤64 无正则无唯一、speed_mbps 1..2147483647 | D01 v6 §5.2/§5.6；Contract §2.2/§2.3 |
| OPEN-8 | resource 创建必填、创建后不可改（PATCH 出现含同值→422）；DB 触发器兜底 | Contract §2.2/§6.4；DB-D74 |
| OPEN-9 | 有未删子→409 `CONFLICT{reference_exists,references:[{object_type:"interface",object_id,label}]}` | Contract §1.2/§6.5；DB-D76 |
| OPEN-10 | metadata 为 Interface 自有 jsonb NOT NULL DEFAULT '{}' + object CHECK；覆盖 product I-5 PROPOSED | DB-D72；D01 v6 §5.6；Contract §2.2 |
| OPEN-11 | Query `resource_id/interface_type/enabled/q/parent_interface_id/deleted/page/page_size/sort/order`；`q` 对 name 大小写敏感子串、特殊字符字面量转义；非法→422 | Contract §4 |
| OPEN-12 | 恢复顺序：name 唯一（409 unique_conflict）→ resource 依赖（409 dependency_deleted）→ parent 依赖（409 dependency_deleted）；name 复用优先 | Contract §6.6 |
| OPEN-13 | 接口引用集调用点存在；F010 落地前为空集，不误报 | Contract §6.5/§9；TE-1 命令 2 `test_f010_ip_reference_checker_is_reserved_empty` |
| OPEN-14 | `revision="0007_interfaces"`、`down_revision="0006_virtual_machine_details"`、单一 head、无回填、对称可逆 | DB-D78；TE-1 命令 3/4 |
| OPEN-15 | 不建 interface_type/deleted_at/q(pg_trgm) 索引；pg_trgm 为 F001 基线扩展（DB-D2），F007 未新增 GIN/pg_trgm 索引 | DB-D77；Contract §9；TE-1 命令 6 |
| OPEN-16 | `resource_id` 与 `parent_interface_id` 均 `ON DELETE RESTRICT`（`confdeltype='r'`） | DB-D64/DB-D76；TE-1 命令 6 |
| OPEN-17 | POST：401→403→body(422)→resource(422)→parent(422)→name 唯一(409)→写+Audit→201；PATCH：401→403→body(422)→可见性(404)→parent(422)→version(409)→name 唯一(409)→写+Audit→200；CONFLICT details 含 `references[]`/`conflicts[]` | Contract §6.2/§6.4；TE-1 命令 2 `test_patch_validation_order` |

TD-1 未闭合项已由 TD-2 关闭；实现与 Contract 未发生导致判据差异的后续变更。

---

## Test Execution

- **版本**：TE-1
- **日期**：2026-10-09
- **角色**：Tester（TEST 模式）
- **结论**：`TEST PASS`（角色术语：READY FOR REVIEW）
- **执行基线**：Contract `docs/api/F007.md` v1（2026-10-09）、DATABASE `docs/database/f007-interface.md` v1（2026-10-09，DB-D64–D79）、D01 `d01-conventions.md` v6 §5.6、`docs/features/F007/implementation.md`（BACKEND + FRONTEND COMPLETE）、TD-2。
- **代码基线**：HEAD `b1c1949`，起始工作区干净（`git status --short` 为空）。
- **独立性声明**：Backend pytest 由 Tester 独立重跑（不复用实现者数字）；迁移、约束、触发器、CHECK、FK、部分唯一、JSONB 由 Tester 在独立库（`csm_test`/`csm_verify_test`）以 Alembic / raw SQL 直接执行；Compose 集成由 Tester 经入口 Nginx `127.0.0.1:18097` 独立 curl。

### 环境

| 项 | 值 |
| --- | --- |
| 后端测试镜像 | `docker build --target test -t csm-backend-f007te1 ./backend`（Python 3.12，pytest 8.4.2） |
| 数据库 | 独立容器 `f007te1-db`（`postgres:16.15`），网络 `f007te1-net`；测试库 `csm_test`、独立验证库 `csm_verify_test` |
| 集成（后端） | `TEST_DATABASE_URL=postgresql+psycopg://csm:change-me@f007te1-db:5432/csm_test`（DB-D10 护栏：库名含 `test`、≠ `DATABASE_URL`） |
| 前端 | Node v22.23.2 / npm 12.0.2；`npm run typecheck`、`npm run build`、`npm run smoke:client` |
| Compose 全链路 | `docker compose -p f007te1i`（独立项目名/卷），入口 Nginx `127.0.0.1:18097`（非默认端口；`deploy/nginx/nginx.conf` 保留 `Host` 端口以使同源 CSRF 生效） |
| 清理 | `compose -p f007te1i down -v`、`docker rm -f f007te1-db`、`docker network rm f007te1-net`、删临时镜像 `csm-backend-f007te1` 与 `f007te1i-*`；残留检查无 f007te1 容器/网络/卷/镜像 |

### 实际执行命令与输出摘要

| # | 命令 | 结果 |
| --- | --- | --- |
| 1 | `pytest tests -q`（真实 PG `csm_test`） | **217 passed, 1 skipped**（skip=`test_migrations.py:101` 非 superuser 扩展假设，连接角色 `csm` 为 superuser 的环境限制，与 F001–F006 基线相同，非 F007 缺陷） |
| 2 | `pytest tests/integration/test_interfaces.py tests/integration/test_interface_constraints.py -v` | **34 passed**（21 API + 13 constraint/migration F007 专属用例，逐条 PASS） |
| 3 | 独立库 `csm_verify_test`：`alembic heads` / `upgrade head` / `current` | `0007_interfaces (head)` 单一 head；升级 0001→0007 全部 Running；`current`=`0007_interfaces (head)`；`downgrade 0006_virtual_machine_details` 后 `interfaces` 表与 `fn_interfaces%` 函数消失、`virtual_machine_details` 保留；re-upgrade 后 `alembic_version` 单值 `0007_interfaces`，表集合一致 |
| 4 | raw 结构探测（`csm_verify_test`） | 15 列（`interface_type` DEFAULT `'OTHER'`、`enabled` DEFAULT true、`metadata` DEFAULT `'{}'`、`version` DEFAULT 1、`gen_random_uuid()`）；14 约束（1 PK + 2 FK + 11 CHECK）；4 索引；2 触发器；FK `confdeltype`：`resource_id='r'`、`parent_interface_id='r'`；无 GIN 索引（pg_trgm 为 F001 基线扩展，F007 未新增） |
| 5 | raw 约束负例/正例探测 | 空/纯空白/未 trim/内部空白/真实 tab → CHECK 拒；65 字符 → `varchar(64)` 拒；64 字符 OK；类型非法/null → 拒；`speed_mbps`/`mtu` 0/负/2147483648 → CHECK/整型拒；`mac_address` 空/未 trim → 拒，null OK；`metadata` 非 object → CHECK 拒；`version=0` → 拒；未知 resource FK → 拒 |
| 6 | raw parent/不可变/FK 探测 | 自引用（INSERT/UPDATE）、跨 Resource、软删父、2 节点环、未知 UUID（FK）均拒；合法父 OK；UPDATE `resource_id`/`id` → `interfaces.id/resource_id are immutable`；物理 `DELETE` 被引用 resource/parent → FK RESTRICT 拒；`metadata` 整值替换，非 object → CHECK 拒 |
| 7 | 真实并发：部分唯一仲裁 | 两独立会话并发插入同 `(resource_id,name)`：一方成功、另一方 `duplicate key ... uq_interfaces_resource_id_name`；最终 `count=1` |
| 8 | 真实并发：resources 行锁序（DR-85） | 会话 A `SELECT ... FOR UPDATE` 持锁，会话 B 同资源 `FOR UPDATE` 阻塞至 A 提交后才获得锁（实测阻塞 >4s），验证同 Resource 串行化 |
| 9 | `npm run typecheck` / `npm run build` / `npm run smoke:client` | typecheck 0 错误；build 通过（**53 modules**）；smoke **86 passed, 0 failed**（F007 新增 33：类型默认/父选择/409 unique_conflict/reference_exists/dependency_deleted/not_deleted、403/404、422 点路径、表单解析与 exclude_unset） |
| 10 | Compose/Nginx 全链路 curl（18097） | `migrate`/`bootstrap` Exited(0)，backend healthy；登录→建 Cluster→建 BARE_METAL→建 Interface（默认 OTHER/enabled true）→形状校验→重名 409 `unique_conflict` → eth0/ETH0 并存→trim→内部空白/空名/speed 0/mtu 0/mac 空/非法类型 422→mac 重复 201→跨 Resource/自引用/环 parent 422→`resource` 不可变 422→enabled null 422→列表分页/`q`/非法参数→删父有子 409 `reference_exists`（含子 label）→软删 404/`deleted=true`/`deleted=only`→restore 200→标识复用 restore 409 `unique_conflict` 不覆盖→activity `CREATE/UPDATE/DELETE/RESTORE`（UPDATE before/after 白名单）→Resource 删除 409 `reference_exists`（含接口列表）→软删 Resource 后 restore 接口 409 `dependency_deleted`→metadata 整值替换/非 object 422→过期 version 409 `VERSION_CONFLICT{current_version}`；`id` 非 UUID→404；未认证/CSRF 由 F002 中间件（本报告命令 10 均带同源 Origin） |
| 11 | `python3 scripts/validate_project_state.py` | `PROJECT STATE VALID`（结构校验；批准/Git 证据另行核对，非本报告结论） |

### V1–V30 执行结果（TD-2 → TE-1）

| 验证项 | 结果 | 证据 / 说明 |
| --- | --- | --- |
| V1 同 Resource 重名拒（409 unique_conflict）+ DB 兜底 | **PASS** | 命令 2 `test_name_unique_partial_and_reuse`；命令 6 raw 部分唯一拒；命令 7 并发仅一成功；命令 10 409 `unique_conflict{field:name}` |
| V2 大小写区分 `eth0`/`ETH0` 并存 | **PASS** | 命令 2/10；raw `uq_...(resource_id,name)` 对大小写敏感；name 原样保留 |
| V3 名称 trim/内部空白/空名/控制字符 | **PASS** | 命令 2 `test_name_normalisation_case_and_length`；命令 5/6 raw CHECK；命令 10 trim 201、内部空白/空名 422 |
| V4 软删后同名可重建；存活同名拒 | **PASS** | 命令 2/6 raw 部分唯一 `WHERE deleted_at IS NULL`；命令 10 |
| V5 类型省略→OTHER；`bond0` 不推断 | **PASS** | 命令 2 `test_create_defaults_and_response_shape`；命令 10 响应 `OTHER` |
| V6 enabled 省略→true；显式 false 保存；null→422 | **PASS** | 命令 2；命令 10 omitted=true、false=201、null 422 |
| V7 speed_mbps/mtu 正整数/null；0/负/超限 422 | **PASS** | 命令 2 `test_type_mac_speed_mtu_validation`；命令 5 raw CHECK |
| V8 parent 空允许；跨 Resource 拒 | **PASS** | 命令 2 `test_parent_validation`；命令 6 raw 触发器；命令 10 422 `field=parent_interface` |
| V9 parent 自引用/2/3 节点环拒 | **PASS** | 命令 2/6/10；raw 触发器断环 |
| V10 mac 空允许；同 MAC 均允许 | **PASS** | 命令 2；命令 5 raw 无 UNIQUE；命令 10 重复 MAC 201 |
| V11 resource 缺失/不存在/软删 422 | **PASS** | 命令 2 `test_resource_validation`；命令 10；raw 未知 FK 拒；软删 Resource DB 层面允许但应用 422（见 B20 注） |
| V12 删除引用检查 references + 不级联 | **PASS** | 命令 2 `test_delete_reference_protection`；命令 10 409 `reference_exists`+子 label |
| V13 恢复重检 name/Resource/parent，不覆盖 | **PASS** | 命令 2 `test_restore_rechecks_name`/`..._resource_and_parent`；命令 10 name 复用 409、Resource 仍删 409 `dependency_deleted` |
| V14 权限矩阵（EDITOR/VIEWER/ADMIN/未认证） | **PASS**（ASGI 真实端点 + 真实 PG） | 命令 2 `test_permission_matrix`；VIEWER 写 403 `FORBIDDEN{permission}`/读 200；EDITOR 写 201/200、删/恢复 403；ADMIN 成功；未认证 401；服务端强制（无绕过）；Nginx 角色限制见 F007-TE-1-02 |
| V15 四 action Audit 同事务；Activity 全角色 | **PASS** | 命令 2 `test_audit_four_actions_and_activity`/`test_audit_rolls_back_with_the_transaction`；命令 10 `CREATE/UPDATE/DELETE/RESTORE`、before/after 白名单 |
| V16 IP 1:N（F007 侧静态 + 预留空集） | **PASS**（F010 端到端不适用） | 命令 2 `test_f010_ip_reference_checker_is_reserved_empty`；interfaces 无 IP 列；不新增解绑/释放端点 |
| V17 不落 IP/CIDR/VLAN/分类 | **PASS** | 命令 4 列集合无 `ip`/`cidr`/`vlan_id`/`network_id`/`category` 类列；类型仅 7 值 |
| V18 DB 部分唯一真实 PG 兜底 | **PASS** | 命令 4 `uq_interfaces_resource_id_name ... WHERE (deleted_at IS NULL)`；命令 6/7 raw 拒 |
| V19 Resource Detail 数据侧（聚合归 F013） | **PASS**（F013 聚合不适用） | 命令 2 `test_list_filters_sorting_pagination`；命令 10 `GET /interfaces?resource_id=` 返回含 mac/speed/mtu/type；命令 9 frontend smoke |
| V20 PATCH exclude_unset / 不可变字段 | **PASS** | 命令 2 `test_patch_exclude_unset_and_immutable`；命令 10 `resource` 422、显式 null 清空 |
| V21 列表分页/排序/过滤/q | **PASS** | 命令 2；命令 10 分页 total/items、`q`、非 UUID 422、非法 type/deleted 422 |
| V22 迁移 0007 up/down/up + 单一 head | **PASS** | 命令 2 `test_migration_up_down_up_and_single_head`；命令 3 独立复现 |
| V23 metadata JSONB object/整值替换 | **PASS** | 命令 2 `test_metadata_object_check`；命令 5/6 raw；命令 10 整值替换、非 object 422 |
| V24 乐观锁并发（真提交） | **PASS** | 命令 2 `test_optimistic_lock_two_sessions`；命令 10 过期 version 409 `VERSION_CONFLICT{current_version}` |
| V25 审计同事务回滚 | **PASS** | 命令 2 `test_audit_rolls_back_with_the_transaction`；断言最终持久化为旧值/无新行 |
| V26 Resource 侧引用保护端到端 | **PASS** | 命令 2 `test_delete_reference_protection`；命令 10 DELETE `/resources` 409 `reference_exists`+接口列表；软删接口后放行 |
| V27 parent 删除保护 | **PASS** | 命令 2；命令 10 有未删子 409 含子 `{object_type:interface,object_id,label}` |
| V28 归属不可变（API + DB 触发器） | **PASS** | 命令 2；命令 6 raw `interfaces.id/resource_id are immutable` |
| V29 响应契约（字段/嵌套） | **PASS** | 命令 2 `test_create_defaults_and_response_shape`；命令 10 响应含 `id/resource{id,hostname}/name/interface_type/mac_address/speed_mbps/mtu/parent_interface{id,name}|null/enabled/description/metadata/version/created_at/updated_at/deleted_at` |
| V30 校验顺序 | **PASS** | 命令 2 `test_patch_validation_order`（POST resource 优先；PATCH parent 优先于 version；version 优先于 name 唯一） |

### B1–B54 执行结果

| 编号 | 结果 | 证据摘要 |
| --- | --- | --- |
| B1 同 Resource 精确重名 | PASS | 命令 2/6/7/10；第二次 409 `unique_conflict`；库中一行 |
| B2 大小写区分 | PASS | 命令 2/10；均 201；两行；name 原样 |
| B3 首尾空白 trim | PASS | 命令 2/10；`"  eth1  "`→`eth1` |
| B4 内部空白 | PASS | 命令 2/5/10；普通空格/Unicode 空白 422；raw CHECK `no_ws_control` 拒 |
| B5 空名/纯空白 | PASS | 命令 2/5/10；422；raw `name_length`/`no_ws_control` 拒 |
| B6 控制字符 Cc/Cf | PASS（应用层） | 命令 2 `test_name_normalisation_case_and_length`；真实 tab raw CHECK 拒；**Cc/Cf 非 ASCII 仅应用层保证，DB 为 ASCII backstop（设计已声明，见未验证项）** |
| B7 name 长度 64/65 | PASS | 命令 2/5；64 成功；65 `varchar(64)`/422 |
| B8 软删后复用 | PASS | 命令 2/6/10；201 新 id |
| B9 恢复重检名称冲突 | PASS | 命令 2 `test_restore_rechecks_name`；命令 10 409；新对象不被覆盖、旧对象保持软删 |
| B10 类型省略默认 | PASS | 命令 2/10；`OTHER` |
| B11 不据名推断 | PASS | 命令 2；`bond0`/`vlan100`/`br0` 均 `OTHER` |
| B12 非法类型值 | PASS | 命令 2/5/10；`ETHERNET`/`""`/null 422；raw CHECK 拒 |
| B13 enabled 语义 | PASS | 命令 2/10；省略→true；显式值保存；null→422 |
| B14 speed_mbps 边界 | PASS | 命令 2/5/10；正例接受；0/负/超限/字符串 422；raw CHECK 拒 |
| B15 mtu 边界 | PASS | 命令 2/5/10；同上；未知 null 不为 0 |
| B16 mac 语义 | PASS | 命令 2/5/10；null 合法；大小写原样；空串/纯空白 422 |
| B17 mac 长度/重复 | PASS | 命令 2/5/10；64 成功；65 422；同 MAC 均允许 |
| B18 resource 缺失 | PASS | 命令 2/10；省略/null/`""` 均 422 |
| B19 resource 不存在 | PASS | 命令 2/10；随机 UUID 422；无行 |
| B20 resource 已软删 | PASS | 命令 2 `test_resource_validation`；API 422；**DB 层 FK 不检查 `deleted_at`，软删可见性为应用责任（DB-D76 已声明）** |
| B21 resource 类型无限制 | PASS | 命令 2；BARE_METAL 与 VIRTUAL_MACHINE 各建 Interface 均 201 |
| B22 parent 空 | PASS | 命令 2/10；省略/null→201 |
| B23 parent 跨 Resource | PASS | 命令 2/6/10；API 422；raw 触发器拒 |
| B24 parent 自引用 | PASS | 命令 2/6/10；API 422；raw 触发器拒 |
| B25 parent 2 节点环 | PASS | 命令 2/6/10；API 422；raw 触发器拒 |
| B26 parent 3 节点环 | PASS | 命令 2/6；raw 触发器拒 |
| B27 parent 不存在/软删 | PASS | 命令 2/6；随机 UUID FK 拒、软删父触发器拒；库值不变 |
| B28 parent 改父成环 | PASS | 命令 2/10；422；库值/`version` 不变 |
| B29 DDL 触发器负例（raw） | PASS | 命令 6；自引用/跨 Resource/软删父/2、3 节点环均拒；合法插入成功 |
| B30 归属不可变触发器（raw） | PASS | 命令 6；`restrict_violation` |
| B31 resource_id PATCH | PASS | 命令 2/10；422；库值不变 |
| B32 软删默认隐藏 | PASS | 命令 2/10；详情 404、不在默认列表；`deleted=true`/`only` 可见 |
| B33 恢复成功 | PASS | 命令 2/10；200；`deleted_at=null` |
| B34 恢复依赖失效 | PASS | 命令 2/10；409 `dependency_deleted`，conflicts 含 resource；保持软删 |
| B35 无引用软删 | PASS | 命令 2 `test_soft_delete_visibility_and_restore`；204；写 DELETE audit；行保留 `deleted_at` |
| B36 子接口引用删除保护 | PASS | 命令 2/10；409 `reference_exists`+子 interface |
| B37 Resource 侧引用保护 | PASS | 命令 2/10；409 `reference_exists`+interface；软删后可删 |
| B38 IP 引用集预留（F010） | PASS | 命令 2 `test_f010_ip_reference_checker_is_reserved_empty`；预留空集不误报 |
| B39 权限矩阵 | PASS（ASGI 真实端点 + 真实 PG） | 命令 2 `test_permission_matrix`；服务端强制；参见 F007-TE-1-02 |
| B40 四 action Audit | PASS | 命令 2/10；各一条 `object_type=interface`；UPDATE before/after 白名单；Activity 全角色 200 |
| B41 审计同事务回滚 | PASS | 命令 2 `test_audit_rolls_back_with_the_transaction`；断言最终持久化 |
| B42 乐观锁并发（真提交） | PASS | 命令 2 `test_optimistic_lock_two_sessions`；一方 200 `version+1`、另一方 409 `VERSION_CONFLICT{current_version}`；无丢失更新 |
| B43 PATCH exclude_unset | PASS | 命令 2 `test_patch_exclude_unset_and_immutable`；省略保持、整体非法 422 |
| B44 显式 null 清空 nullable | PASS | 命令 2/10；`mac/speed/mtu/parent/description` 清空 |
| B45 必填显式 null | PASS | 命令 2；name/resource/interface_type/enabled null 422 |
| B46 未知/只读字段 | PASS | 命令 2/10；`id`/`version`/`created_at` 等 422 |
| B47 列表分页/排序/过滤/q | PASS | 命令 2/10；全参数组合正确；非 UUID 422 |
| B48 迁移 0007 up/down/up | PASS | 命令 2/3；单一 head；down 后表/函数消失、0006 对象保留；re-up 一致 |
| B49 metadata JSONB | PASS | 命令 2/5/6/10；object 接受、非 object 422/CHECK 拒、整值替换 |
| B50 parent 环并发双会话（DR-85） | PASS | 命令 2 `test_parent_cycle_concurrency_serialised_by_resource_lock`（线程 barrier + 真提交，断言最终图无环）；命令 8 raw 行锁阻塞复现锁序 |
| B51 resource 软删 vs Interface 创建并发（DR-85） | PASS | 命令 2 `test_resource_delete_vs_interface_create_concurrency`（删除持锁→创建阻塞→看到软删返回 422）；反向由命令 8 行锁串行化 + 引用检查覆盖（见未验证项） |
| B52 恢复与并发重建标识 | PASS | 命令 2；B9 + 部分唯一（命令 7）保证不产生双存活同名 |
| B53 部分唯一 raw 兜底 | PASS | 命令 6/7；存活重名被 `uq_interfaces_resource_id_name` 拒；软删后同名成功 |
| B54 FK 物理语义（机制级） | PASS（机制级） | 命令 6；`DELETE resources`/父接口被 FK RESTRICT 阻止（`confdeltype='r'`）；**API 无物理删除路径，报告标注机制级** |

### 数据库 / 接口 / 前端 / 集成结果

- **数据库（真实 PG，`csm_verify_test` raw SQL + `csm_test` pytest）**：`interfaces` 15 列/11 CHECK/双 FK RESTRICT/部分唯一/2 索引/2 触发器与 DB v1 逐项一致；`interface_type` DEFAULT OTHER、`enabled` DEFAULT true、`metadata` DEFAULT '{}' 且 object CHECK、`version` DEFAULT 1；name/速度/MTU/mac/metadata/version 边界与触发器负例全部符合；迁移 0007 对称可逆、单一 head、无回填。**PASS**
- **接口（ASGI + 全链路 Nginx 18097）**：7 端点响应内容、类型、nullable、name 归一化与大小写、类型默认不推断、enabled/speed/mtu/mac/metadata 边界、resource/parent 校验、删除/恢复、可见性、分页/排序/过滤/q、错误码 `unique_conflict`/`reference_exists`/`dependency_deleted`/`not_deleted`/`VERSION_CONFLICT`/`VALIDATION_ERROR` 符合 Contract；未认证 401、未定义路径 404；只读端点无业务写副作用。**PASS**
- **前端**：typecheck 0 错误、build 53 modules、client 机制级 86 项通过；Interface 表单（类型下拉/parent 选择器/enabled/mac/speed/mtu）、已删开关与 ADMIN 恢复、409 各 reason 文案与不静默重试、422 点路径映射、`resource_id` 列表调用经源码与 smoke 核对；经入口 Nginx 真实 API 往返。**PASS**
- **集成（Compose 经入口 Nginx）**：`migrate`/`bootstrap` Exited(0)、backend healthy；从登录到 Interface 全生命周期（创建/重名/trim/大小写/边界/parent/删除保护/软删可见性/恢复/恢复冲突/审计/乐观锁/引用保护/依赖检查）符合 Contract。**PASS**

### 验收映射 A1–A19 结论

| # | 结论 | 证据 |
| --- | --- | --- |
| A1 | **PASS**（409 unique_conflict，Contract 裁定） | V1/V18；B1/B53；命令 10 |
| A2 | **PASS** | V2；B2 |
| A3 | **PASS** | V3；B3–B7 |
| A4 | **PASS** | V4/V18；B8/B53 |
| A5 | **PASS** | V5；B10/B11 |
| A6 | **PASS** | V6；B13 |
| A7 | **PASS** | V7/V18；B14/B15 |
| A8 | **PASS** | V8；B22/B23/B27 |
| A9 | **PASS** | V9；B24–B30 |
| A10 | **PASS** | V10；B16/B17 |
| A11 | **PASS** | V11；B18–B21 |
| A12 | **PASS**（端到端） | V12/V26/V27；B35–B38 |
| A13 | **PASS**（端到端） | V13；B9/B33/B34 |
| A14 | **PASS**（ASGI 真实端点 + 真实 PG） | V14；B39；参见 F007-TE-1-02 |
| A15 | **PASS** | V15/V25；B40/B41 |
| A16 | **PASS**（F007 侧静态；端到端归 F010） | V16；B38 |
| A17 | **PASS** | V17；命令 4 |
| A18 | **PASS**（真实 PG raw SQL） | V18；B53；命令 6/7 |
| A19 | **PASS**（数据侧；聚合展示归 F013） | V19；命令 9/10 |

### Defects

未发现必须修复的实现缺陷。以下为观察（NOTE，非缺陷）：

| ID | Severity | Layer | Location | 证据 / 期望与实际 | 影响 | Owner | 必须修复 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| F007-TE-1-01 | NOTE | 数据完整性（Unicode） | Interface name Cc/Cf | ASCII 控制字符由 DB CHECK 兜底；非 ASCII Cc/Cf（如 U+200B）仅应用层保证，DB 为 ASCII backstop | 与 D01 v6 §5.6/DB-D65 声明的已知边界一致；应用层已拒，无落库风险 | Backend/Database | 否 |
| F007-TE-1-02 | NOTE | 集成测试范围 | Compose/Nginx | 一期无用户管理 HTTP 端点（F015），无法经 Nginx 以 VIEWER/EDITOR 真实登录验证 A14/B39 角色矩阵；已由 `role_client_factory` + 真实 ASGI + 真实 PG 的业务端点覆盖 | 环境限制，非实现缺陷 | 协调器/F015 | 否 |
| F007-TE-1-03 | NOTE | 并发测试范围 | DR-85/B51 | B51 现覆盖「Resource 软删持锁→Interface 创建阻塞→422」方向；反向「创建持锁→删除等待→引用检查 409」由行锁串行化（命令 8）+ 引用检查端到端（命令 10）间接覆盖 | 覆盖充分；如后续要求可补双向线程化用例 | Tester | 否 |

### 未验证项与口径声明

- **B54/A12 物理 FK RESTRICT 为机制级**：API 无物理删除 Resource/Interface 路径（删除为软删），RESTRICT 仅经 raw SQL 物理 `DELETE` 验证；软删引用保护为端到端。不得表述为独立端到端。
- **Cc/Cf（非 ASCII）**：仅应用层保证，DB 为 ASCII backstop（F007-TE-1-01），与 F003–F006 同源边界。
- **B20 软删 Resource 的 Interface 创建**：API 422 已验；DB FK 不检查 `deleted_at`（DB-D76 声明应用责任），并发即时一致性属设计不保证项。
- **A15/V14/B39 角色矩阵经 Nginx**：见 F007-TE-1-02；权限由真实业务端点（ASGI）+真实 PG 覆盖，服务端强制，非仅前端隐藏。
- **DR-85 并发**：以真实连接持行锁 + 后台线程/会话竞争与真提交验证；断言最终持久化关系图，未做大规模压测。
- **B41 审计回滚**：以 monkeypatch 注入 audit 失败制造同事务失败，断言最终持久化；非真实进程崩溃注入。
- **真实浏览器 DOM 渲染**：未自动化；前端以 typecheck + build + client 机制级 + 入口 Nginx 真实 API 集成为准（同 F001–F006）。
- **数据完整性映射**：`.pi/skills/data-integrity/SKILL.md` 对应表全部适用项已在 §0 与本节覆盖；不适用/跨 Feature 项见 §5。
- **跨 Feature**：A16 IP↔Interface 端到端归 F010；A19 聚合展示归 F013；列表/搜索/Dashboard 归 F013；导入归 F14；完整 Audit 查询页归 F015；跨 Feature 权限/审计完整回归与 §32 上线验收归 F016。**不声明上述条款完整通过**，不以 F007 局部 PASS 拼成整条 T12/T20/T23/T24/T25/T37/T39/T40/T41 通过。

---

### Git 声明

```text
GIT: NONE
```

本次（TD-2 + TE-1）仅写入 `docs/features/F007/test-report.md`（更新 Test Design 关闭 OPEN 并追加 Test Execution），未修改 backend/frontend 业务实现或其它仓库文件；未暂存/提交/切换分支。测试与迁移均在临时容器/独立测试库中执行，不影响仓库状态。