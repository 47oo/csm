# F010 IP 地址分配与容量 — Test Report

本文件同时承载 TEST_DESIGN 与 TEST（TEST 阶段在同一文件追加执行结果）。两阶段分别记录版本、结论与证据；TEST_DESIGN 不填充执行 PASS。

---

## Test Design

- **版本**：TD-1
- **日期**：2026-10-09
- **角色**：Tester（TEST_DESIGN 模式）
- **结论**：`TEST DESIGN READY`（TD-1）
- **依据**：
  - `docs/product/requirements-v3.md` revision 3（§4、§4.1、§10、§11、§11.1、§12、§12.1、§13/§13.1/§13.2/§13.3、§14、§16、§18、§20、§21、§22、§23、§25、§27、§28、§31 T04–T07/T10/T16/T17/T18/T22/T23/T24/T25/T26/T30/T31/T32/T34/T35/T37/T38/T40/T41、§35.2 Q04-A/Q04-B/Q07-A/Q10-A/Q10-B、§35.3 D01/D02）
  - `docs/features/F010/product.md`（PRODUCT `READY FOR ARCHITECT`，2026-10-09；A1–A26、I-1–I-10、明确排除项）
  - `docs/features/F010/architecture.md`（ARCHITECTURE `READY FOR DESIGN`，2026-10-09；§5 唯一/边界/不可变、§6 分配/并发/引用、§7 容量、§9 验证策略、DR-118–DR-139）
  - `docs/api/F010.md` 草案 v0（CONTRACT DRAFT，目标 READY；9 端点、字段契约 §2、错误码 §1.2 新增 `allocation_not_allowed`/`no_available_address`、分页排序过滤 §4、软删/恢复 §5/§6、校验顺序 §6、并发 §7、审计白名单 §8、容量 §6.9、跨 Feature §9）
  - `docs/database/f010-ip-address.md`（**尚未产出**，DATABASE Gate 未定稿；TD-1 按 architecture §1/§5/§12 草案假设）
  - `docs/architecture/d01-conventions.md` v8（§5/§5.9 待 v9 签核；§3 地址字段、§4 省略语义、§5.8 IPPool 口径）
  - `docs/api/F009.md` v1、`docs/database/f009-ip-pool.md` v1（DB-D95–D110；`IpOccupancyProvider` 注册表、`address_in_use` 形状、`_lock_network`、来源 FK RESTRICT）
  - `docs/api/F008.md` v1、`docs/database/f008-network.md` v1（DB-D80–D94；gateway 语义、Network 引用检查器、`_lock_network` 锁域）
  - `docs/api/F007.md` v1、`docs/database/f007-interface.md` v1（Interface 实体、Resource 归属、`interface←IPAddress` 引用检查预留点）
  - `docs/features/F009/test-report.md`（TD/TE 模板、夹具/环境、`committed_engine` 真提交口径）、`docs/features/F008/test-report.md`（TD-2/TE-1：机制级证据边界、真库结构核对模式）
  - `docs/project/handoff.md`、`docs/project/implementation-rules.md`、`.pi/skills/data-integrity/SKILL.md`、`AGENTS.md`
  - `docs/project/project-plan.yaml` plan_revision 4 F010 条目
- **状态属性**：TD-1 `READY` 仅表示 A1–A26 已映射到可观察判据、边界/并发场景可执行、夹具与可验证性检查已建立；**不代表测试已运行、不填充执行 PASS、不批准实现或合并**。DATABASE 设计（`docs/database/f010-ip-address.md`）与 CONTRACT（`docs/api/F010.md`）尚未定稿、D01 v9 §5.9 未签核；§8 列 OPEN 待 DATABASE / CONTRACT / D01 定稿后由 TD-2 逐项关闭。**不因 DATABASE 未定稿而直接 BLOCKED**（architecture §5/§6/§7/§9 已给出可执行的唯一/边界/锁/容量方案）。跨功能完整 §31 回归与 §32 上线验收不在本 Feature（见 §5）。

### 版本记录

| 版本 | 日期 | 变更 |
| --- | --- | --- |
| TD-1 | 2026-10-09 | 初版：A1–A26 映射 V1–V26（补充 V27–V35），边界/并发 B1–B50，夹具/环境设计，F010 独立 / F010+桩 / 留待 F012/F013 三类分界，§8 OPEN 复核项（待 DATABASE/CONTRACT/D01 v9 后由 TD-2 关闭）。 |

> 复核基线（待 TD-2）：`docs/database/f010-ip-address.md`（DATABASE Gate，未定稿）、`docs/api/F010.md` v0（CONTRACT Gate，未定稿）、`d01-conventions.md` v9 §5.9（未签核）。TD-1 的表名/列名/约束名/FK/触发 backstop/索引/迁移 0010 编号/错误路径/并发机制均按 architecture §1/§5/§6/§7/§12 草案假设，TD-2 逐项核对后方可作为执行依据。

---

### 0. 数据完整性对应表（F010 范围）

方法依据 `.pi/skills/data-integrity/SKILL.md`；DB 列/约束以 DATABASE Gate 定稿为准（TD-1 为草案，行内 `（架构草案）` 标注）。

| 规则依据及版本 | 作用域/写入入口 | 数据库保证（架构草案，待签核） | 业务层保证 | 并发/生命周期边界 | 验证与证据 |
| --- | --- | --- | --- | --- | --- |
| §14/§27/DR-119 同 Cluster 未删地址唯一 | POST（手动/自动）、RESTORE | 冗余 `cluster_id` + 部分唯一 `uq_ip_addresses_cluster_id_address UNIQUE(cluster_id,address) WHERE deleted_at IS NULL`；`cluster_id` 一致性触发 backstop（`FOR KEY SHARE`） | 409 `unique_conflict{field:"address"}` | 索引仲裁；软删释放；恢复重检；不同 Cluster 可重复 | V14/V26、B29–B31/B41/B56；真实 PG |
| §13.1/§27/DR-126 自动分配不重复、升序 | POST `/auto-allocate` | 唯一兜底 + 行锁；升序不依赖全量展开 | `_lock_network`（networks 行 FOR UPDATE）+ 升序选择；耗尽不切换 | T07 双会话 B40；T35 与保留/网关互斥 B42/B43 | V5–V8、B14–B20/B40/B42/B43；真提交 |
| §11.1/§13.2/§14/DR-120/DR-124 属 CIDR、非网络/广播/禁用/gateway/RESERVED | POST（手动） | `address inet` CHECK `family=4 AND masklen=32`；CIDR 包含触发 backstop；gateway/RESERVED/禁用为跨表应用主校验 | 422 field="address" | 与 Network 改 cidr 经 `FOR KEY SHARE` 串行 | V2/V3/V16/V17、B1–B10、DB catalogue；真实 PG |
| §14/DR-121 绑定 Cluster 一致 | PATCH（绑定/转移） | 触发 backstop（跨 Resource/Network）；无跨表 FK 可表达 | 422 field="interface" | 绑定/解绑/转移重检 | V11/V15、B23/B24/B32 |
| §13.3/§16/DR-139 Endpoint 引用 | PATCH/DELETE | —（引用在 F012） | 引用检查器 → 409 `reference_exists`；F010 默认空集挂钩 | F012 注册真实检查器 | V18（桩）、B52/B53；端到端归 F012 |
| §12.1/§11.1/DR-126 保留范围/gateway vs 并发分配 | Pool/Network 变更 + 分配 | 无（跨表）；共享 `_lock_network` + `IpAddressOccupancyProvider` | 409 `address_in_use`（F009/F008 经真实 provider 可达） | T33 真实占用；T35 双会话 B42/B43 | V21/V28、B54/B42/B43；真提交 |
| §21/§27/DR-128 软删/恢复 | DELETE/restore | `deleted_at` + 部分唯一 | 恢复重检 CIDR/唯一/Cluster/Interface；失败不覆盖 | 不级联；只恢复自身 | V22、B27/B28/B44 |
| §23 乐观锁 | PATCH/DELETE/restore | `version` + 条件 UPDATE | rowcount=0 → 409 `VERSION_CONFLICT` | 真并发双会话 | V26、B45；真提交 |
| §20/DR-130 容量口径 | GET `/networks/{id}/capacity` | 无（查询期计算） | `IpCapacityProvider`：可分配集合、占用、剩余；集合去重 | 停用不清零；按当前地址不按来源 | V23、B34–B39 |
| §12/§21/DR-122 来源历史例外 | Pool 删除/缩小 | `ip_addresses.ip_pool_id` FK RESTRICT（物理）；池软删保行 | 不注册 IP 来源检查器、不回收、不级联 | 软删后来源 FK 仍有效 | V20、B54；真实 PG |
| §27/DR-132 迁移 0010 | Alembic `0010_ip_addresses` | `down_revision=0009_ip_pools`；全表新建无回填；单一 head；对称可逆 | — | 真库 up/down/up | V27、B50 |

---

## 1. 验收映射（product.md A1–A26 → 验证项）

执行环境：`真实 PG` = 独立测试库（库名含 `test`）；`后端集成` = ASGI 应用 + 真实 PG（非 SQLite）；`真提交` = `committed_engine`（真实连接 + 真实提交 + TRUNCATE teardown）；`机制级` = 真实 PG raw SQL 直接验证；`静态` = 路由清单/源码检查；`前端` = 构建 + client 机制级（真实 API 集成以入口 Nginx 为准）。**Endpoint 桩** = 经 F010 `register_ip_address_reference_checker` 注册返回固定引用集的测试侧检查器。

> **分界声明（关键）**：
> - **F010 独立可验证（不依赖 F012 数据）**：A1–A17、A19、A20、A21、A22、A23（数值）、A24、A25、A26；对应 §31 T04–T07/T10/T16/T17/T24/T25/T26/T30/T31/T32（数值）/T33（真实占用）/T34/T35 的 F010 子集。
> - **F010 + Endpoint 桩（可验证契约与挂钩、引用拦截路径，不能证明真实 Endpoint 数据语义）**：A18 的引用检查注册点、`register_ip_address_reference_checker` 挂钩、解绑/转移/释放被未删 Endpoint 引用时 409 `reference_exists`。
> - **必须留待 F012 / F013（F010 局部 PASS 无法覆盖）**：含 Endpoint 的端到端（T22/T23 的真实 Endpoint 数据）；T32 的 Dashboard 显示（数值计算在 F010，页面显示归 F013）。
> - **不得以 F010 局部 PASS 拼接整条 T22/T23/T32 通过**；完整集成结论只能在 F012/F013 交付后由对应端到端测试给出。

| 验收（product.md） | 验证项 | 执行环境 | 可观察判据（PASS / FAIL） |
| --- | --- | --- | --- |
| A1 手动分配合法且属 ACTIVE Network CIDR 的可分配地址成功并占用 | **V1** | 后端集成 + 真实 PG | PASS：ACTIVE Network 内合法地址（AUTO 池内、MANUAL 池内、池外各一）POST `/api/v1/ip-addresses`→201，响应对应 `ip_pool`（池内=所属池、池外=null），DB 新增一行未删 IP；占用后再手动分配同址→409。FAIL：池外被拒、ip_pool 推导错、未落库 |
| A2 地址不属 CIDR 或非法/非 IPv4 → 拒（422） | **V2** | 后端集成 + 真实 PG | PASS：CIDR 外、`10.0.0.1/24`（带掩码）、`::1`、`not-an-ip`、`10.0.0.300`、空→422 field="address"；raw 带掩码/越界直插被 CHECK/触发拒。FAIL：任一被接受 |
| A3 手动分配 gateway、RESERVED 池范围、禁用地址 → 拒 | **V3** | 后端集成 + 真实 PG | PASS：Network gateway 地址、RESERVED 池内地址、禁用 5 段地址→422 field="address"；无 IP 行。FAIL：任一被接受、落库 |
| A4 auto_allocate 关闭或地址属 MANUAL 池时手动仍允许；AUTO 池亦允许 | **V4** | 后端集成 + 真实 PG | PASS：auto_allocate=false 的 Network 手动→201；MANUAL 池内、AUTO 池内手动→201；不因 mode 拒绝手动。FAIL：以 mode/auto_allocate 误拒手动 |
| A5 自动分配仅在 ACTIVE + auto_allocate=true + 指定池 AUTO 时成功；其余明确拒绝，不降级手动 | **V5** | 后端集成 + 真实 PG | PASS：四条件满足→201，`ip_pool`=指定池；INACTIVE→409 `allocation_not_allowed{condition:"network_inactive"}`；auto_allocate=false→`auto_allocate_disabled`；MANUAL/RESERVED 池→`pool_not_auto`；均无 IP 行、不改用其它池。FAIL：降级手动、创建成功、reason/condition 错 |
| A6 自动分配在指定池内按地址升序选第一个符合全部约束的可用地址 | **V6** | 后端集成 + 真实 PG | PASS：池 `[x..y]` 内中间地址已被占用/被 gateway/RESERVED/禁用时，返回第一个合法且未占用地址；重复调用依次升序占用。FAIL：非升序、跳过非法/占用失败 |
| A7 指定 AUTO 池无可用地址 → 返回“无可用地址”，不改用其它池/Network | **V7** | 后端集成 + 真实 PG | PASS：池内地址全部占用后→409 `no_available_address{network_id,ip_pool_id}`，无 IP 行；同 Network 其它 AUTO 池仍有空位时也不切换。FAIL：切换池、静默成功 |
| A8 并发自动分配不产生重复 IP，最终持久化无重复占用 | **V8** | 后端集成 + 真实 PG（真提交） | PASS：`committed_engine` 两独立连接对同 Network/池并发 auto-allocate→至多一方 201、另一方 `no_available_address`/重试成功但地址不同；最终库中同 Cluster 无重复地址；断言最终持久化（非仅未抛异常）。FAIL：双成功同址 |
| A9 interface 为空的 IP 仍占用，不作为可用地址再次分配 | **V9** | 后端集成 + 真实 PG | PASS：未绑定 IP 存在后，手动同址→409 `unique_conflict`；自动分配跳过该地址；容量 `occupied` 计入。FAIL：未绑定被当作可用、重复分配 |
| A10 解绑只移除 Interface 关系，IP 记录继续占用、不释放 | **V10** | 后端集成 + 真实 PG | PASS：PATCH `interface:null`→200，`deleted_at` 保持 null、`interface` 为 null、`ip_pool` 不变；随后同址再分配→409；IP 仍计占用。FAIL：解绑被当释放、记录被软删 |
| A11 转移=改绑到另一 Interface（同 Cluster）允许；改绑到不属 Network Cluster 的 Interface 被拒 | **V11** | 后端集成 + 真实 PG | PASS：同 Cluster 另一 Interface PATCH→200，`interface` 更新且 version+1；跨 Cluster Interface→422 field="interface"，原绑定不变。FAIL：跨 Cluster 成功、误拒同 Cluster |
| A12 释放=软删 IP，仅 ADMIN；EDITOR 解绑不能隐式释放 | **V12** | 后端集成 + 真实 PG | PASS：ADMIN DELETE（带 version）→204，`deleted_at` 非空；EDITOR DELETE→403；EDITOR PATCH `interface:null` 后 `deleted_at` 仍 null。FAIL：EDITOR 释放成功、解绑隐式软删 |
| A13 释放后同址可在同 Cluster 重新分配；恢复旧 IP 重检冲突，不覆盖新占用 | **V13** | 后端集成 + 真实 PG | PASS：释放后同址新建→201（新 id）；对旧对象 restore 当同址已有新占用→409 `unique_conflict{field:"address"}`，旧对象保持软删、新对象不变。FAIL：恢复覆盖新对象、释放后仍拒 |
| A14 同 Cluster 重复 IP（含不同 Network/Pool、未绑定）失败；不同 Cluster 同址允许 | **V14**；**V32** DB | 后端集成 + 真实 PG | PASS：同 Cluster 经不同 Network 与不同 Pool 的重复（均未绑定）→409 `unique_conflict`；不同 Cluster 同址→均 201；raw 直插同 `(cluster_id,address)` 未删被部分唯一拒、跨 Cluster/软删后成功。FAIL：跨 Cluster 被误拦、重复成功 |
| A15 绑定 Interface 时 Resource 与 Network 不同 Cluster 被拒；未绑定 IP 仍校验 CIDR/唯一/Cluster 一致性 | **V15** | 后端集成 + 真实 PG | PASS：跨 Cluster 绑定→422；未绑定 IP 在创建/恢复时仍走 CIDR 属主/唯一/Cluster 校验（越界、重复、Cluster 不一致各自失败）。FAIL：未绑定豁免校验 |
| A16 /0–/30 排网络/广播；/31 两址可用；/32 唯一地址可用且 gateway 必空；自动、手动、恢复共用边界 | **V16** | 后端集成 + 真实 PG | PASS：/24 网络/广播地址手动→422；/31 两端均可手动分配；/32 唯一地址可分配且该 Network gateway 必为 null（非空→422）；自动分配与 restore 采用同一边界（同一可分配集合函数）。FAIL：网络/广播可分配、/31 被误拒、/32 特例失效 |
| A17 禁用 5 段边界地址禁分配及作 gateway；普通私网/公网允许；LOOPBACK 接口可登记但 127.x 不入台账 | **V17** | 后端集成 + 真实 PG | PASS：`0.0.0.0/8`、`127.0.0.0/8`、`169.254.0.0/16`、`224.0.0.0/4`、`240.0.0.0/4` 各段边界地址手动→422、设为 gateway→422；合法私网/公网→201；127.x.x.x 分配→422；LOOPBACK Interface 登记本身成功。FAIL：禁用段被接受、普通地址被误拒 |
| A18 IP 被未删 Endpoint 引用时解绑/转移/释放被拒并返回引用列表，无隐式级联（F010 交付检查契约与挂钩；端到端随 F012） | **V18**（桩）；F012 端到端 | 后端集成 + 真实 PG + Endpoint 桩 | PASS（桩）：注册返回固定引用 `[{object_type:"endpoint",object_id,label}]` 的测试检查器后，PATCH（解绑/转移）与 DELETE→409 `CONFLICT{reference_exists,references[]}`，库中 `interface`/`deleted_at` 不变；**含真实 Endpoint 的端到端归 F012（T22/T23）**。FAIL：引用被忽略、无 references、级联 |
| A19 有未删 IP 引用时 Network/Interface 删除被拒并返回引用列表；IPPool 来源为例外 | **V19** | 后端集成 + 真实 PG | PASS：存在未删 IP 时 `DELETE /api/v1/networks/{id}` 与 `DELETE /api/v1/interfaces/{id}`→409 `reference_exists` + `references[{object_type:"ip_address",...}]`；软删 IP 后可删；软删/缩小来源 IPPool 不阻止、不回收、不级联。FAIL：无 references、误删、级联删 IP |
| A20 IP 记录保留分配来源 Pool；删除/缩小池不删除/不释放已分配 IP，来源历史保留 | **V20** | 后端集成 + 真实 PG | PASS：自动分配 IP `ip_pool`=指定池、池内手动=所属池；软删来源池与缩小其范围后 IP 仍存在、`ip_pool_id` 不变、未回收；池软删后 IP 详情仍可解析来源（或按 Contract 处理）。FAIL：池操作回收/置空来源、级联删 IP |
| A21 保留范围/网关变更与并发 IP 分配不能同时成功形成冲突；事务失败不留部分变更或错误容量 | **V21** | 后端集成 + 真实 PG（真提交） | PASS：`committed_engine` 双会话——(a) 会话 1 为该 Network 建/扩 RESERVED 覆盖某地址持 `_lock_network`，会话 2 同址并发分配：至多一方成功，失败方 409 `address_in_use`/`unique_conflict`；(b) gateway 变更 vs 分配同理；最终库中无「RESERVED 范围/占用 gateway 与已分配 IP 冲突」共存；失败无部分变更、容量无错误。FAIL：双成功、留部分变更 |
| A22 ADMIN 恢复已删 IP；恢复只恢复自身、重检属 CIDR/同 Cluster 唯一/Cluster 一致/引用有效；失败不覆盖新对象 | **V22** | 后端集成 + 真实 PG | PASS：ADMIN restore→200，`deleted_at=null`、不恢复 Interface 关系；同址被新占用→409 `unique_conflict`；Network 软删→409 `dependency_deleted`；Network cidr 变更致越界→422；bind Interface 已软删→409 `dependency_deleted`；失败保持软删且不覆盖新对象。FAIL：restore 成功、顺序/错误码不符、自动恢复关系 |
| A23 Network 可分配总量/已占用/剩余与 AUTO 池可分配总量/剩余按 §20 集合公式；去重、未绑定计占用、池外计 Network、按当前地址不按来源、停用不清零 | **V23** | 后端集成 + 真实 PG | PASS：`GET /api/v1/networks/{id}/capacity` 逐项核对——`allocatable_total`=基础可用−gateway−RESERVED−禁用（去重）；`occupied` 含未绑定与池外手动；`remaining` 差额；AUTO 池 `allocatable_total=|池范围∩可分配集合|`、`occupied` 按当前地址非来源、`remaining` 差额；INACTIVE 不清零。FAIL：口径、去重、计数、来源依赖错 |
| A24 权限：VIEWER 只读；EDITOR 分配/解绑/转移；释放/查看已删/恢复 ADMIN；分配/绑定/解绑/转移/释放/恢复写 Audit 且同事务；Activity 全角色 | **V24** | 后端集成 + 前端 + 真实 PG（真提交） | PASS：逐端点 VIEWER/EDITOR/ADMIN/未认证 401/403/200/201/204；五类 action 各一条 `audit_logs`（`object_type="ip_address"`、白名单、UPDATE 含 before/after）；注入 audit 失败时业务同回滚；`GET .../activity` 全角色 200；`deleted=include|only` 非 VIEW_DELETED→403。FAIL：越权、不同事务、缺 action |
| A25 创建缺失 network/address→422；省略非必填→默认/null；PATCH 省略=保持；不可变/只读/未知字段→422 | **V25** | 后端集成 | PASS：省略 `network`/`address`/显式 null→422；省略 `description`/`interface`→null；PATCH 省略字段保持；`network`/`address`/`cluster_id`/`ip_pool`/`id`/`metadata`/未知字段→422；被拒请求不改库值与 version。FAIL：任一被接受或静默改写 |
| A26 同 Cluster 未删 IP 唯一由 PostgreSQL 兜底、真实 PG 验证；过期版本编辑 409 无静默覆盖 | **V26**；**V32** DB | 后端集成 + 真实 PG（真提交） | PASS：部分唯一 `uq_ip_addresses_cluster_id_address ... WHERE deleted_at IS NULL` 存在且 raw 直插生效；两连接同 version PATCH，一方 200/version+1、另一方 409 `VERSION_CONFLICT{current_version}`，最终值来自成功方。FAIL：无约束、丢失更新 |

补充验证项（非直接 A 映射）：

| 验证项 | 内容 | 环境 | 判据 |
| --- | --- | --- | --- |
| **V27** 迁移 0010 | Alembic up/down/up + 单一 head + 无回填 | 真实 PG | PASS：`alembic heads` 单一 `0010_ip_addresses`（`down_revision=0009_ip_pools`）；up 建表/约束/部分唯一/触发 backstop/索引；down 逆序且 0009 对象保留；re-up 集合一致；无回填 |
| **V28** 真实占用提供者注册（T33） | F010 注册 `IpAddressOccupancyProvider`（替换 F009 空集） | 后端集成 + 真实 PG（真提交） | PASS：创建真实未删 IP 后，新建/扩大 RESERVED 覆盖之→409 `address_in_use{field,conflict_count,conflicts[]}`（含 `bound:false`）；Network PATCH 设已占用 gateway→409 `address_in_use{field:"gateway"}`；未占用通过。FAIL：占用被忽略、真实 provider 未注册 |
| **V29** 引用检查器注册与挂钩 | F010 注册 Network←IP、Interface←IP 引用检查器；提供 `register_ip_address_reference_checker`（默认空集） | 后端集成 + 静态 | PASS：未删 IP 阻止 Network/Interface 删除（V19）；解绑/转移/释放调用点存在；默认空集不误报；注册桩后 A18 生效。FAIL：无调用点、空集误报 |
| **V30** 响应契约 | IPAddress 响应字段/嵌套 | 后端集成 | PASS：含 `id、network{id,name,cidr}、cluster{id,code,name}、address、interface{id,name,resource{id,hostname}}|null、ip_pool{id,name}|null、description|null、version、created_at/updated_at、deleted_at`；列表 `{items,page,page_size,total}`；不含 metadata/`cluster_id`/`network_id` 原始列 |
| **V31** 校验顺序 | POST/PATCH/DELETE/restore/auto-allocate 优先级 | 后端集成 | PASS：按 Contract §6 固定顺序（POST 401→403→body(422)→network(422)→`_lock_network`→Active(409)→地址(422)→唯一(409)→写+Audit→201；auto-allocate 追加池存在/模式(422/409)→耗尽(409)；PATCH 可见性→version→interface→引用；DELETE 对象→version 校验→版本→引用；restore 唯一→依赖→CIDR→恢复） |
| **V32** 表/约束目录（机制级） | raw PG 目录断言 | 真实 PG | PASS：`pg_constraint`/`pg_indexes`/`pg_attribute`/`pg_trigger` 含 `family=4 AND masklen=32` CHECK、`uq_ip_addresses_cluster_id_address ... WHERE deleted_at IS NULL`、`cluster_id` 一致性触发、CIDR 包含触发、FK RESTRICT、约定索引；无 pg_trgm/GIN 新增 |
| **V33** FK 物理语义（机制级） | raw 物理 `DELETE FROM networks`（被未删 IP 引用） | 真实 PG | PASS：被 FK RESTRICT 阻止（`confdeltype='r'`）；报告标注机制级（API 无物理删除路径） |
| **V34** `cluster_id` 冗余一致性 backstop（机制级） | raw 直插 `network_id` 与 `cluster_id` 所属 Network 不一致的行 | 真实 PG | PASS：被触发 backstop 拒（或按 DATABASE 定稿的等价保证拒）；应用创建取锁定 Network 的 cluster，恒等。FAIL：不一致落库 |
| **V35** 列表/软删可见性 | 默认隐藏软删；过滤/分页/排序 | 后端集成 + 真实 PG | PASS：默认无软删；`network_id`/`cluster_id`/`interface_id`/`ip_pool_id`/`address`/`bound`/`q`/`deleted` 过滤正确；分页边界正确；`sort∈{address,created_at,updated_at}`+`order` 生效且附 `id` 稳定；非法参数→422；`deleted=include|only` 非 VIEW_DELETED→403 |

---

## 2. 边界与并发场景（B 编号，TEST 阶段执行）

| 编号 | 场景 | 步骤 | 判据 |
| --- | --- | --- | --- |
| B1 | 手动分配位置 | AUTO 池内 / MANUAL 池内 / 池外 | 均 201；`ip_pool` 分别=池 / 池 / null |
| B2 | 手动地址格式 | 非 IPv4、带掩码 `a.b.c.d/24`、CIDR 形式、IPv6、超范围、空 | 均 422 field="address"；无行 |
| B3 | /24 网络与广播地址 | CIDR 首地址与末地址手动 | 422；raw 触发 backstop 拒 |
| B4 | /31 点对点 | /31 两端分别手动分配 | 均 201（§11.1 /31 两址可用） |
| B5 | /32 唯一地址 | /32 Network 分配唯一地址；gateway 非空→422 | 分配 201；gateway 非空 422；gateway 空合法 |
| B6 | /0–/30 排除 | /30 网络与广播地址 | 422 |
| B7 | 禁用 5 段 | `0.1.1.1`、`127.0.0.1`、`169.254.1.1`、`224.0.0.1`、`240.0.0.1` 及段边界 | 手动与 gateway 均 422 |
| B8 | 普通合法地址 | 私网 `10.10.1.20`、公网 `8.8.8.8`（属 CIDR 时） | 201（不以公网可达性判断合法性） |
| B9 | 127.x 不入台账 | 127.0.0.1 分配；LOOPBACK Interface 登记 | 分配 422；LOOPBACK 登记成功 |
| B10 | gateway 排除手动 | 分配 Network gateway 地址 | 422 field="address"；无行 |
| B11 | RESERVED 排除手动 | 分配 RESERVED 池内地址 | 422 field="address" |
| B12 | auto_allocate 关闭手动 | auto_allocate=false 上手动池外合法地址 | 201（auto_allocate 不代替手动校验） |
| B13 | AUTO 池手动 | 在 AUTO 池内手动分配 | 201；`ip_pool`=该池 |
| B14 | 自动条件：INACTIVE | INACTIVE Network auto-allocate | 409 `allocation_not_allowed{condition:"network_inactive"}` |
| B15 | 自动条件：auto_allocate 关闭 | ACTIVE 且 auto_allocate=false | 409 `allocation_not_allowed{condition:"auto_allocate_disabled"}` |
| B16 | 自动条件：池非 AUTO | 指定 MANUAL/RESERVED 池 | 409 `allocation_not_allowed{condition:"pool_not_auto"}` |
| B17 | 自动升序 | 池内低地址已被占用/禁用/gateway/RESERVED | 返回第一个合法未占用地址；连续调用升序 |
| B18 | 自动耗尽 | 池内全占用 | 409 `no_available_address{network_id,ip_pool_id}`；不切换 |
| B19 | 分配与绑定分离 | auto-allocate / POST 体含 interface | 422（DR-137；分配创建未绑定） |
| B20 | 未绑定占用 | 未绑定 IP 存在 | 手动同址 409；自动跳过；容量占用+1（V9） |
| B21 | 解绑 | PATCH interface:null | 200；未释放；再分配 409 |
| B22 | 同 Cluster 转移 | 改绑同 Cluster 另一 Interface | 200；interface 更新；version+1 |
| B23 | 跨 Cluster 转移 | 改绑异 Cluster Interface | 422 field="interface"；原绑定不变 |
| B24 | 跨 Cluster 创建绑定 | 未绑定 IP 创建后 PATCH 异 Cluster Interface | 422 |
| B25 | 释放权限 | ADMIN DELETE；EDITOR DELETE | 204 / 403 |
| B26 | 解绑非释放 | EDITOR PATCH interface:null | 200；`deleted_at` 仍 null |
| B27 | 释放后可重用 | 释放地址后同址新建 | 201 新 id |
| B28 | 恢复重检冲突 | 同址已被新占用时 restore 旧对象 | 409 `unique_conflict`；旧保持软删、新不变 |
| B29 | 恢复依赖失效 | Network 软删 / cidr 变更越界 / 绑定 Interface 软删 | 409 `dependency_deleted` / 422 field="address" / 409 `dependency_deleted` |
| B30 | 恢复不级联 | 恢复软删 IP（其 interface_id 非空且 Interface 仍有效） | 200；不自动恢复/创建其它关系 |
| B31 | 同 Cluster 重复（跨 Network/Pool） | 两 Network 或两 Pool 分配同址（未绑定） | 第二次 409 `unique_conflict{field:"address"}` |
| B32 | Clusters 差异 | 不同 Cluster 同址 | 均 201（唯一作用域=同 Cluster） |
| B33 | 未绑定不豁免 | 未绑定 IP 越界/重复/跨 Cluster 绑定 | 分别 422/409/422 |
| B34 | 容量基础 | 构造 gateway + RESERVED + 若干占用 | `allocatable_total`=基础可用−去重排除；`occupied`=未删 IP 数；`remaining`=差额 |
| B35 | 容量去重 | gateway 同时位于 RESERVED 池 | 只扣一次（集合去重） |
| B36 | 容量未绑定/池外 | 未绑定 IP、池外手动 IP | 均计入 Network `occupied` |
| B37 | 容量来源无关 | IP 来源池 A，地址现落于池 B 范围 | AUTO 池 B `occupied` 计入（按当前地址不按来源） |
| B38 | 容量停用不清零 | Network INACTIVE | 容量与占用数值不变 |
| B39 | 负值容量 NOTE | 存量 IP 落入现已保留范围 | 记录实际行为（Contract 定稿口径）；TD-1 不预设下限 0 |
| B40 | **T07 并发自动分配（真提交）** | `committed_engine` 两独立连接同 Network/池并发 auto-allocate | 至多一方 201，另一方成功则地址不同，或 `no_available_address`；最终库同 Cluster 无重复；断言最终持久化 |
| B41 | **同 Cluster 唯一并发（真提交）** | 两独立连接并发手动分配同址（跨 Network） | 部分唯一原子兜底，至多一方 201，另一方 409 `unique_conflict`；最终库仅一行 |
| B42 | **T35 保留范围 vs 并发分配（真提交）** | 会话 1 扩 RESERVED 覆盖某地址持 `_lock_network`；会话 2 同址并发分配 | 至多一方成功；失败方 409 `address_in_use`/`unique_conflict`；无冲突共存；无部分变更 |
| B43 | **T35 gateway vs 并发分配（真提交）** | 会话 1 PATCH gateway 设为某地址；会话 2 同址分配 | 至多一方成功；无「gateway 被占用」共存 |
| B44 | **恢复 vs 并发重建（真提交）** | 软删 IP 后并发：会话 1 restore 旧对象、会话 2 同址新建 | 至多一方存活；部分唯一闭环；无两存活同址 |
| B45 | **乐观锁并发（真提交）** | 两连接同 version PATCH | 一方 200 且 version+1；另一方 409 `VERSION_CONFLICT`；无丢失更新 |
| B46 | 权限矩阵 | 逐端点 VIEWER/EDITOR/ADMIN/未认证 | 符合 §23；服务端强制 |
| B47 | 五 action Audit 同事务 | CREATE/UPDATE（绑定/解绑/转移）/DELETE/RESTORE | 各一条 `object_type="ip_address"`；UPDATE 含 before/after；`activity` 全角色 200 |
| B48 | 审计同事务回滚 | 注入 audit 失败（创建/更新/释放/恢复） | 业务与 audit 同回滚；最终持久化为旧值/无新行 |
| B49 | 校验顺序 | V31 各端点优先级 | 符合 Contract §6 |
| B50 | 迁移 0010 up/down/up | `upgrade head`→`downgrade 0009`→`upgrade head` | 各步 0；单一 head；down 后表/约束/触发消失、0009 对象保留；re-up 一致 |
| B51 | Network/Interface 引用保护端到端 | 有未删 IP 的 Network/Interface DELETE | 409 `reference_exists` + references 含 ip_address；软删 IP 后可删 |
| B52 | **Endpoint 桩引用拦截** | 注册返回固定 endpoint 引用的桩检查器后 PATCH 解绑/转移、DELETE | 409 `reference_exists` + references；库值不变；无级联 |
| B53 | Endpoint 挂钩默认空集 | 未注册真实检查器时解绑/转移/释放 | 正常成功（空集不误报） |
| B54 | **T33 真实占用** | 真实未删 IP 阻碍 RESERVED 新建/扩大、AUTO/MANUAL→RESERVED、gateway 设置 | 409 `address_in_use` + `conflict_count`/`conflicts[]`（含未绑定）；合法释放后可重试 |
| B55 | 来源 FK 例外 | 软删/缩小来源 IPPool；物理删被引用池 | 软删/缩小成功且不回收 IP；物理删被 FK RESTRICT 拒（机制级） |
| B56 | cluster_id 一致性 raw | raw 直插 network/cluster 不一致 | 触发 backstop 拒（或 DATABASE 定稿等价保证） |
| B57 | 只读无副作用 | GET 列表/详情/capacity/activity | 无业务写、无 audit 行、version 不变 |
| B58 | exclude_unset / 显式 null / 只读 | PATCH 省略保持；显式 null 仅清 interface/description；必填/只读/未知→422 | 符合 D01 §4 与 Contract §2.4 |
| B59 | 软删默认隐藏 / 已删查看 | 软删后 GET 详情/列表默认；`deleted=true`（ADMIN） | 404/不在列表；ADMIN 可查看 |
| B60 | 容量 /31 /32 | /31 两端可分配总量、/32 单址容量 | 按 §11.1 前缀口径正确 |

并发说明：B40–B45/B48 及任何「失败不留痕/并发」用例必须使用 `committed_engine`（真实连接、真实提交）或显式事务控制，断言**最终持久化状态 + 关系图**，不仅「未抛异常」。涉及部分唯一、CHECK、触发 backstop、FK、迁移、容量计数的断言必须在真实 PostgreSQL 执行（SQLite / Mock 不作约束/并发证据）。T35 并发用例必须显式以「同 Network 行 `FOR UPDATE`（`_lock_network`）」构造两会话竞争，复现并验证锁域串行化。

---

## 3. 夹具 / 环境设计

**复用 F001–F009 `backend/tests/conftest.py`（不改其护栏语义）**：
- `test_database_url`：独立测试库 + 安全护栏（库名含 `test`、`TEST_DATABASE_URL != DATABASE_URL`）；未设置则 skip 并告警，不静默改 SQLite。
- `pg_engine`：会话级 `DROP SCHEMA public CASCADE` + `CREATE SCHEMA public` + `alembic upgrade head`（含 0010），会话结束清理。
- `db_session`：函数级外层事务 + savepoint，回滚不跨用例污染（单事务用例）。
- `committed_engine`：真实提交用例（B40–B45/B48 及持久断言），teardown `TRUNCATE` 清理（排除 `alembic_version`；确认 `ip_addresses` 在动态清理清单内），新开连接断言最终持久化。
- `alembic_runner`：迁移 up/down/up 用例（V27/B50）。
- 认证/权限 fixture（`auth_session_factory`/`auth_app`/`api_client`/`bootstrap_admin`/`make_user`/`login`）：F010 权限/审计证据使用**真实业务端点** `/api/v1/ip-addresses*` 与 `/api/v1/networks/{id}/capacity`，以及 `/api/v1/networks/{id}`、`/api/v1/interfaces/{id}`。
- F003/F004/F007/F008/F009 helper：`_create_cluster`、`network_factory`、`interface_factory`、`ip_pool_factory`、`role_client_factory`、raw `insert_*`、软删/恢复、乐观锁 `two-session`、raw SQL 约束断言模式、占用桩模式直接复用。

**F010 新增测试侧夹具/断言（由 Tester 落地于测试侧，实现阶段由 Backend 提供接口）**：
- `ip_address_factory`：创建 IPAddress（`network_id` + `address` + 可选 `interface_id`/`description`），返回对象与 `version`；供 A1–A26、B1–B60 复用；失败路径覆盖只读字段被拒。
- `manual_allocate` / `auto_allocate`：封装两个分配入口，返回 `(status, payload)`；`bind_address` / `unbind_address` / `transfer_address` / `release_address` / `restore_address`：封装关系与生命周期操作。
- `IP_ADDRESS_CASES`：表驱动地址数据（合法池内/池外、网络/广播、/31 两端、/32、禁用 5 段边界、127.x、gateway、RESERVED、越界、带掩码、IPv6、非法），确保 API 与 DB 同一口径（V2/V3/V16/V17、B1–B10）。
- `CAPACITY_CASES`：表驱动容量场景（基础/去重/未绑定/池外/来源无关/停用/负值），供 V23、B34–B39/B60。
- `assert_ip_address_row(engine, id, expected)`：raw SQL 断言 `ip_addresses` 各列值/`IS NULL`（含 `network_id`/`cluster_id`/`address`/`interface_id`/`ip_pool_id`/version/`deleted_at`）。
- `assert_partial_unique_ip_address(engine, cluster_id, address, deleted)`：raw 直插断言部分唯一仅在 `deleted_at IS NULL` 生效（A14/A26/V14/V32/B31/B41）。
- `assert_capacity(client, network_id, expected_network, expected_pools)`：断言容量端点数值与集合口径（A23/V23/B34–B39）。
- `occupancy_real_assert(...)` / `occupancy_stub`（fixture）：验证 F010 注册的**真实** `IpAddressOccupancyProvider`（V28/B54）与测试侧假 provider 结构/数量断言（F009/F008 路径）。
- `endpoint_reference_stub`（fixture）：经 `register_ip_address_reference_checker` 注册返回固定引用集的检查器，teardown 恢复空集；供 A18/V18/B52/B53（**标注桩证据边界**）。
- `assert_reference_protection(client, ...)`：端到端断言 Network/Interface 的 409 `reference_exists`+references（A19/V19/B51）。
- `assert_audit_same_txn(...)`：注入 audit 失败断言双回滚（A24/V24/B48）。
- 真提交并发夹具（复用 F004/F008/F009 `committed_engine` 模式）：`two_session_concurrent_auto_allocate`、`two_session_unique_create`、`two_session_reserved_vs_allocate`、`two_session_gateway_vs_allocate`、`two_session_restore_vs_reallocate`、`two_session_version_conflict`；后者须显式经 `_lock_network`（networks 行 FOR UPDATE）复现锁序，供 B40–B45。
- **F010 前端夹具**：复用 F005–F009 `smoke:client` 机制，新增 IPAM 列表/详情（network/cluster/interface/池与 bound/address 过滤）、手动/自动分配表单、绑定/解绑/转移、释放（ADMIN 二次确认）、恢复、Activity、409 冲突呈现（`unique_conflict`/`reference_exists`/`allocation_not_allowed`/`no_available_address`/`address_in_use`）与未知 reason 通用呈现；容量显示归 F013。

**环境**：Docker / Compose 可用（F001–F009 TE 已证）；真实 PG 经 Compose `db`（`postgres:16`）。btree_gist 由 0008 已启用、pg_trgm 由 0001 启用；0010 不重复启用。

### 3.1 当前环境可执行性评估

| 验证项 | 环境要求 | 当前评估 | 降级/替代 |
| --- | --- | --- | --- |
| V1–V26、B1–B39/B46–B49/B51–B59 | 真实 PG + 后端集成 | 经 Compose `db` 可满足（F001–F009 已证） | 无 PG 时 skip 并标 BLOCKED，**不得**用 SQLite 替代约束/并发证据 |
| V27/B50 迁移 0010 | Alembic + 真实 PG | 可执行；依赖 0010 定稿 | 迁移未定稿则相关断言 BLOCKED，不降验收 |
| V28/V32–V34 真实占用/目录/触发 backstop | F010 已注册真实 provider + DB 定稿 | architecture §6/DR-138 已定义接口；F010 实现后可用 | 若接口未落地则 BLOCKED，不降验收 |
| V18/B52/B53 Endpoint 桩 | F010 挂钩存在 | architecture §7.1/DR-139 已定义；F010 交付空集挂钩 | 挂钩未落地则 BLOCKED；真实 Endpoint 端到端**不可执行**（归 F012） |
| B40–B45/B48 并发 | 真实并发提交 fixture | 可执行（复用 `committed_engine`） | 无 PG 时 BLOCKED；不得以顺序调用替代并发证据 |
| 前端机制级 / 真实 API 集成 | Node 22 + 构建；Compose 入口 | 可执行 | 真实浏览器 DOM 渲染非必要判据；镜像/端口问题记 BLOCKED |
| T32 Dashboard 显示 | F013 交付 | **不可执行** | 标 `NOT TESTED / 归 F013`；F010 仅验证容量数值 |
| T22/T23 真实 Endpoint 端到端 | F012 交付 | **不可执行** | 标 `NOT TESTED / 归 F012`；F010 仅验证契约/挂钩/桩 |

---

## 4. 可验证性检查

| 项 | 判定 | 说明 |
| --- | --- | --- |
| A1–A4 手动分配 | **可验证（API + DB）** | V1–V4 + B1–B13；可分配集合校验 + 池推导 |
| A5–A8 自动分配与并发 | **可验证（API + DB + 真提交）** | V5–V8 + B14–B20/B40；`_lock_network` + 部分唯一 |
| A9/A10 未绑定与解绑 | **可验证（API + DB）** | V9/V10 + B20/B21 |
| A11/A15 绑定/转移一致性 | **可验证（API + DB）** | V11/V15 + B22–B24/B32/B33；应用校验 + 触发 backstop |
| A12/A13 释放/恢复/重用 | **可验证（API + DB + 真提交）** | V12/V13 + B25–B30/B44 |
| A14/A26 同 Cluster 唯一兜底 | **可验证（API + DB + 真提交）** | V14/V26 + B31/B41/B56；真实 PG raw 部分唯一 |
| A16/A17 地址边界与禁用 | **可验证（API + DB）** | V16/V17 + B3–B9；共享可分配集合函数 |
| A18 Endpoint 引用 | **桩可验证契约/挂钩；端到端归 F012** | V18/V29 + B52/B53 |
| A19 引用保护 | **可验证（端到端 + 机制）** | V19 + B51/B55 |
| A20 来源历史例外 | **可验证（API + DB）** | V20 + B54/B55 |
| A21/T35 并发互斥 | **可验证（真提交）** | V21 + B42/B43；断言最终持久化无冲突共存 |
| A22 恢复重检 | **可验证（端到端）** | V22 + B28/B29/B30/B44 |
| A23/T32 容量计算 | **可验证（端到端）；显示归 F013** | V23 + B34–B39/B60 |
| A24 权限/审计 | **可验证（端到端 + 真提交）** | V24 + B46–B48 |
| A25 D01 语义 | **可验证（端到端）** | V25 + B58 |
| V27/B50 迁移 0010 | **可验证（DB）** | 真实 PG up/down/up + 单一 head |
| V28 真实占用提供者（T33） | **可验证（端到端 + 真提交）** | V28 + B54；F009/F008 的 `address_in_use` 真实可达 |
| V32–V34 DB 目录/触发/FK | **可验证（DB 机制级）** | 真实 PG raw SQL |
| B40–B45 并发 | **可验证（真提交）** | 复用 `committed_engine`，断言最终关系图 |

口径明确记录：**A18/V18/B52/B53 为 Endpoint 桩的结构与引用拦截断言**，真实 Endpoint 端到端（T22/T23）归 F012；**A23/V23 在 F010 验证容量数值**，Dashboard 显示（T32）归 F013；**T33 真实占用、T34 真实「不回收/来源历史」、T35 真实并发互斥在本 Feature 验证**；**T04/T05/T06/T07/T10/T16/T17/T24/T25/T26/T30/T31 的 F010 子集**在本 Feature 验证；**完整 T22/T23/T32 与 §32 上线验收不在本 Feature**，不得以 F010 局部 PASS 拼成整条通过。

---

## 5. 范围与不适用项声明

- **Endpoint / Service 实体与关系（§15/§16，F011/F012）**：F010 仅交付 `register_ip_address_reference_checker` 挂钩（默认空集）与解绑/转移/释放前的调用点；**含真实 Endpoint 的端到端（T22/T23）归 F012**。
- **Dashboard 显示 / 全局搜索 / 列表聚合（§17/§19/§20/§28，F013）**：F010 仅提供 `GET /api/v1/networks/{id}/capacity` 与 `IpCapacityProvider`；**T32 的页面显示归 F013**。
- **IPPool 本体（范围、allocation_mode 语义、池重叠、RESERVED 冲突）**：归 F009；F010 只注册真实占用提供者并消费其冲突契约。
- **Network CIDR/网关/状态/auto_allocate 本体与 CIDR 重叠**：归 F008；F010 消费其边界。
- **Interface 本体与父接口规则**：归 F007；F010 消费其 Resource 归属与引用检查点。
- **CSV / Excel 导入（§24，F014）**、**完整 Audit 查询页（§22，F015）**、**一期集成验收（§32/F016）**：不在本 Feature。
- **IPv6、DHCP、路由、防火墙、VLAN 划分、网段自动发现、实时可达性/流量监控**：明确排除。
- **不由地址推断 Resource/Service/角色/网络分类；不自动创建 Endpoint/Service；不进行 DNS 登记**：明确排除。
- **IPAddress 不落 metadata/name/status/实时探测状态**：明确排除（I-3/DR-123）。
- **完整 T04–T07/T10/T16/T17/T18/T22–T26/T30–T32/T34/T35/T37/T38/T40/T41 回归与 §32 上线验收**：F010 仅承载 IP 相关子集；跨 Feature 完整回归归 F016。**不声明上述条款完整通过**。
- **真实浏览器 DOM 渲染**：非 F010 必要判据，前端以构建 + client 机制级为准。

---

## 6. 风险与待核对项总结

| 项 | 评估 | 处理 |
| --- | --- | --- |
| V1–V26、B1–B39/B46–B60（真实 PG + 后端集成） | Docker/Compose 可用（F001–F009 已证）；**可执行** | 无 PG 时相关项 BLOCKED，不降验收 |
| V27/B50 迁移 0010 + 触发 backstop/部分唯一 | DATABASE Gate 未定稿 | 定稿后由 TD-2 核对；未定稿则相关断言 BLOCKED |
| A18 引用检查与挂钩 | F010 仅到达桩；真实 Endpoint 在 F012 | F010 验契约/挂钩/桩拦截；端到端明确标注 `NOT TESTED / 归 F012`，不拼成 T22/T23 通过 |
| T32 容量显示 | F013 | F010 验容量数值；显示标注 `NOT TESTED / 归 F013` |
| B40–B45 并发 | 需真实并发提交 fixture | 复用 `committed_engine`；断言最终关系图；T35 显式 `_lock_network` 锁序 |
| `cluster_id` 冗余一致性 backstop | 架构标注待 DATABASE 裁定（触发 backstop 形态） | TD-2 依 DATABASE 定稿核对 V34/B56 断言层级 |
| `remaining` 负值口径 | Contract 草案 NOTE（未定下限 0） | TD-2 依 Contract 定稿固定 B39 判据 |
| 新 reason/`conflicts` 形状/D01 v9 §5.9 | Contract 草案 v0 未定稿 | TD-2 依 Contract v1 与 D01 v9 核对 §8 OPEN |
| DATABASE/CONTRACT/D01 v9 定稿状态 | **未定稿** | TD-1 §8 列全部待复核项；TD-2 逐项关闭 |

---

## 7. 独立性与执行口径（TEST 阶段适用）

- Backend pytest 由 Tester 独立重跑，不复用实现者数字。
- 迁移、部分唯一、CHECK、触发 backstop、FK 由 Tester 在独立库（库名含 `test`）以 Alembic / raw SQL 直接执行；不连接生产或未知数据库。
- 接口验证响应内容、类型、业务边界、非法输入与错误语义；只读功能（GET 列表/详情/capacity/activity）确认无业务写副作用。
- 占用冲突：F009/F008 的 `address_in_use` 经 F010 **真实** `IpAddressOccupancyProvider` 端到端验证；Endpoint 引用为测试侧桩并**明确标注桩证据边界**，真实端到端归 F012。
- 前端验证状态、交互、错误与未知值处理；已批准范围要求真实前后端集成时经入口 Nginx 验证真实 API，不以 Mock 代替。
- 修复后按影响重测；首次设计检查与最终验收分别记录版本与证据。

---

## 8. OPEN 复核项（TD-1 提出，待 DATABASE / CONTRACT / D01 v9 定稿后由 TD-2 关闭）

> TD-1 `READY` 表示方案可验证，下列假设均未经逐项核对；**READY 不代表测试已执行、不批准实现或合并**。定稿后由 TD-2 关闭并固定执行判据。

### 8.1 待 DATABASE 定稿（`docs/database/f010-ip-address.md`，未产出）

| # | TD-1 待复核假设 | 影响验证项 | Owner |
| --- | --- | --- | --- |
| OPEN-1 | 表名 `ip_addresses`、列名/类型（`id uuid`、`network_id uuid NOT NULL`、`cluster_id uuid NOT NULL`、`address inet`、`interface_id uuid NULL`、`ip_pool_id uuid NULL`、`description text NULL`、`version int`、时间戳、`deleted_at`） | V1–V35、B1–B60 | Database |
| OPEN-2 | 约束/索引名：`pk_ip_addresses`、`fk_ip_addresses_{network_id,cluster_id,interface_id,ip_pool_id}_*`、`uq_ip_addresses_cluster_id_address`（部分唯一）、`ck_ip_addresses_address_host`（family=4 且 masklen=32）、version/address CHECK、`ix_ip_addresses_{network_id,cluster_id,interface_id,ip_pool_id,deleted_at}` | V14/V26/V32、B31/B41 | Database |
| OPEN-3 | **`cluster_id` 冗余一致性保证**：BEFORE 触发 backstop（`FOR KEY SHARE` 取 Network.cluster 比对）或等价机制；`cluster_id` 创建取锁定 Network 的 cluster、不可改 | V34、B56 | Database |
| OPEN-4 | **同 Cluster 未删唯一**部分唯一精确形态 `UNIQUE(cluster_id,address) WHERE deleted_at IS NULL`；软删释放、恢复重检、跨 Network/Pool 生效 | V14/V26、B31/B41/B44 | Database |
| OPEN-5 | **CIDR 包含触发 backstop**（`address <<= networks.cidr`，`FOR KEY SHARE`）与「非网络/广播、非禁用」的 DB 覆盖层级（应用主导 vs 触发/SQL 函数）；`family/masklen` CHECK 表达 | V2/V3/V16/V17/V32、B2–B10 | Database |
| OPEN-6 | 迁移 `0010_ip_addresses`（`down_revision=0009_ip_pools`）单 head、全表新建无回填、对称可逆、不重复启用 btree_gist/pg_trgm | V27、B50 | Database |
| OPEN-7 | FK `network_id → networks(id)`、`cluster_id → clusters(id)`、`interface_id → interfaces(id)`、`ip_pool_id → ip_pools(id)` 均 `ON DELETE RESTRICT`；来源历史例外在 DB 层的落点 | V19/V20/V33、B51/B55 | Database |
| OPEN-8 | 软删/恢复与约束交互（部分唯一/触发谓词排除软删；恢复置 null 重新受约束）；占用提供者查询索引支撑 | V22/V28、B28/B29/B30/B44/B54 | Database / Backend |
| OPEN-9 | 绑定 Cluster 一致的 DB backstop 形态（跨 interfaces(resource)→resources(cluster) 与 networks(cluster) 触发）或明确仅应用主校验 | V15/V32、B23/B24/B33 | Database |

### 8.2 待 CONTRACT 定稿（`docs/api/F010.md` v0）

| # | TD-1 待复核假设 | 影响验证项 | Owner |
| --- | --- | --- | --- |
| OPEN-10 | 新 reason `allocation_not_allowed{condition∈network_inactive|auto_allocate_disabled|pool_not_auto}` 与 `no_available_address{network_id,ip_pool_id}` 登记 F002 §1.2.1 的最终形状 | A5/A7/V5/V7、B14–B18 | Contract |
| OPEN-11 | 复用 reason `unique_conflict{field:"address"}`、`reference_exists{references[]}`、`dependency_deleted{conflicts[]}`、`not_deleted`、`address_in_use{field:"gateway",conflict_count,conflicts,conflicts_truncated}` 的最终 details | A3/A12/A18/A19/V3/V18/V19/V28、B10/B51/B52/B54 | Contract |
| OPEN-12 | 校验顺序与错误码层级（POST/auto-allocate/PATCH/DELETE/restore；§6 各端点） | V31、B49 | Contract |
| OPEN-13 | D01 v9 §5.9 签核：address 单主机 IPv4/属 CIDR/非网络广播禁用 gateway RESERVED；network/address 创建必填不可改；interface 可空同 Cluster；ip_pool 只读来源；description 无上限；不落 metadata/name/status | V25、B58 | Contract / D01 |
| OPEN-14 | `ip_pool` 设置口径（自动=指定池；手动=地址所属未删池或 null；请求体出现→422；创建后不可改） | A1/A20/V1/V20、B1/B37/B55 | Contract |
| OPEN-15 | 恢复错误码优先级（唯一 > 依赖 > CIDR 包含 422 > 恢复）与 `dependency_deleted`/越界形状 | A22/V22、B28/B29 | Contract |
| OPEN-16 | 列表 Query 参数集（`network_id/cluster_id/interface_id/ip_pool_id/address/bound/q/deleted/page/page_size/sort/order`）、`sort=address` 数值口径、`deleted` 语义 | V35、B57/B59 | Contract |
| OPEN-17 | 容量端点响应形状与 `remaining` 负值口径（是否下限 0）、AUTO 池交集口径、停用不清零 | A23/V23、B34–B39/B60 | Contract |
| OPEN-18 | 权限映射（分配/绑定/解绑/转移=WRITE；释放=RELEASE_IP；查看已删=VIEW_DELETED；恢复=RESTORE；Activity 全角色）与审计白名单 `{network_id,cluster_id,address,interface_id,ip_pool_id,description}` | A24/V24、B46–B48 | Contract |
| OPEN-19 | 跨 Feature 协议：F010 必须复用 `_lock_network` 并注册真实 `IpAddressOccupancyProvider`；`register_ip_address_reference_checker` 默认空集、F012 注册；容量供 F013 | A18/A21/A23/V18/V21/V28、B42/B43/B52/B53 | Architect / 跨 Feature |
| OPEN-20 | I-10 F008/F003 Contract errata（gateway `address_in_use`）是否在 F010 CONTRACT 一并订正 | V28、B54 | 协调器 |

TD-1 结论：**`TEST DESIGN READY`** —— A1–A26 已映射到可观察判据，边界/并发场景（含 T07/B40、T35/B42–B43、同 Cluster 唯一并发 B41、恢复重检 B28/B44、容量公式 B34–B39、未绑定占用 B20、绑定 Cluster 一致性 B23/B33、禁用与 /31 /32 边界 B3–B9）可执行，夹具与可验证性已与 architecture §5/§6/§7/§9 草案建立对应；A18 在 F010 以 Endpoint 桩断言契约与挂钩，T33/T34/T35 与容量数值在 F010 真实端到端，T32 显示与 Endpoint 端到端明确留待 F013/F012。**DATABASE / CONTRACT / D01 v9 尚未定稿，以上 OPEN 未经逐项核对；READY 不等于测试通过，不批准实现或合并。** 定稿后由 TD-2 关闭 §8 并固定执行判据。