# F014 CSV / Excel 批量导入 — PRODUCT 阶段报告

- **Feature**：F014 CSV / Excel 批量导入（FEATURE，P1，M6 检索、导入与系统功能；deps F003、F004、F005、F006）
- **阶段**：PRODUCT；**结论**：`READY FOR ARCHITECT`（无 Blocking Questions）
- **依据**：requirements-v3.md revision 3（§4、§4.1、§5、§6、§7、§8、§9、§21、§22、§23、§24、§25、§27、§31 T11/T27/T28/T37/T38、§32、§35.2 Q02-A/Q10-A/Q10-B、§35.3 D01/D03）；plan_revision 4 F014 条目（用户 2026-10-06 批准，approved_by=用户）；已完成 Feature 产品/契约 `docs/features/F003/product.md`、`docs/features/F004/product.md`、`docs/features/F005/product.md`、`docs/features/F006/product.md`、`docs/api/F004.md` v3、`docs/api/F003.md` v2、`docs/api/F002.md` v1；`docs/architecture/d01-conventions.md` v11；`docs/product/domain-model.md`；`.pi/skills/resource-domain/SKILL.md`；`docs/project/handoff.md`；`docs/project/project-plan.yaml` F014。
- **D03 定位**：CSV/.xlsx 固定模板、VM Host 引用列、逐列说明、同步导入的大小/行数上限及性能依据为 §35.3 D03 OPEN 专业设计输入，在本 Feature **CONTRACT 签核**（Owner：Architect / Backend / Tester）。本报告给出产品级要求与可实施默认建议，具体模板/上限数值/Schema/契约细节不在本阶段定稿。

## 1. 目标与范围

### 1.1 目标
在已交付的 Resource / BareMetal / VM 域（F003–F006）之上，提供 CSV 与 Excel `.xlsx` 的**资源新增批量导入**能力（§24）：以固定模板一次登记多台裸金属或虚拟机，经「预校验 → 用户确认 → 正式写入再次校验」两步，整批成功或整批回滚，替代重复手工单条创建，降低 Excel 台账迁移成本。导入不引入新的资源实体、字段或状态，只是既有创建路径的批量入口。

### 1.2 本次范围（CONFIRMED，引用需求）
- **文件格式**（§24）：支持 CSV 与 Excel `.xlsx`。
- **仅资源新增**（§24）：仅当批新增 Resource（`BARE_METAL` / `VIRTUAL_MACHINE`）及其专有明细；**不按 hostname 自动更新或覆盖现有资源**。
- **固定模板与逐列说明**（§24）：提供固定模板与逐列说明；示例列 `cluster, hostname, resource_type, role, status, manufacturer, model, cpu_model, cpu_cores, memory_mb, gpu_model, gpu_count`；**VM 模板须含 Host 引用列**；单位（MiB/GiB）显式标注（§8）；完整模板由 D03 承接。
- **两步流程**（§24-1、§24-2）：先校验并展示错误行（含行号、字段、原因）→ 用户确认 → 正式写入时**再次校验**；任一写入失败**整批回滚**，不产生部分成功。
- **错误报出**（§24-1、§31 T27）：文件内重复、现存资源冲突、非法字段/关系均报错，错误至少含行号、字段、原因。
- **VM Host 规则**（§24-3、§9、§31 T28）：VM Host 必须已存在且满足 §9（存在、未软删、`BARE_METAL`、与 VM 同 Cluster）；首次迁移先导入裸金属再导入 VM；**不在同一批次隐式创建 Host**。
- **同一 Service Layer**（§24）：导入必须走与普通 API 相同的 Service Layer 业务校验，**禁止跳过服务层直接写数据库**。
- **同步处理与上限**（§24-4）：一期同步处理；设置文件大小与行数上限；具体上限由部署资源与性能验证确定并记入契约（D03）。
- **权限**（§24-4、§23）：预校验与写入**均执行 §23 权限检查**；EDITOR / ADMIN 可导入，VIEWER 不可。
- **cluster 列校验**（§5、§24、plan F014）：cluster 列引用必须存在且未软删；INACTIVE 不阻止导入（§5/T29）。
- **回滚不留痕**（§24-2、§22）：回滚不能留下未成功创建对象的业务变更记录（无 Activity / Audit 残留）。

### 1.3 使用者
EDITOR 日常批量登记；ADMIN 批量登记与迁移；VIEWER 无导入权限（§23）。典型场景：把既有 Excel 台账首次迁入 CSM——先导入裸金属行，再导入引用这些 Host 的 VM 行。

## 2. 导入行为定义（§24）

### 2.1 模板与列（§24；完整模板/列名/顺序由 D03 定稿）

**CONFIRMED**：提供固定模板与逐列说明；示例列为 `cluster, hostname, resource_type, role, status, manufacturer, model, cpu_model, cpu_cores, memory_mb, gpu_model, gpu_count`；VM 模板须含 Host 引用列；界面/导入模板明确单位（§8，不混用 MB/GB）。

**逐列说明（产品级；具体格式/列名/是否拆分为 BM 模板与 VM 模板由 D03 定稿）**：

| 列 | 必填 | 适用类型 | 语义与校验 | 映射字段（F004 契约） |
| --- | --- | --- | --- | --- |
| cluster | 是 | 全部 | Cluster 引用，须存在且未软删；INACTIVE 允许（§5/T29）；按 code 大小写不敏感精确解析或 UUID（§5/§4）；Cluster **name 不唯一，不得作为引用** | resource.cluster（落 cluster_id） |
| hostname | 是 | 全部 | §7 归一化（去首尾空白 + ASCII 折叠小写后保存）；同 cluster 内未删唯一；禁空、内部空白、非法字符（D01 §5.3） | resource.hostname |
| resource_type | 是 | 全部 | `BARE_METAL` / `VIRTUAL_MACHINE`；创建后不可改（§6） | resource.resource_type |
| role | 否 | 全部 | ∈{COMPUTE,LOGIN,MANAGEMENT,STORAGE,SERVICE,GPU,OTHER}，缺省 OTHER（§6） | resource.role |
| status | 否 | 全部 | ∈{IDLE,ALLOC,DOWN,UNKNOWN}，缺省 UNKNOWN（§6） | resource.status |
| manufacturer | 否 | BARE_METAL | trim 后非空或空；≤255（D01 §5.4）；空=null | hardware.manufacturer |
| model | 否 | BARE_METAL | 同上 | hardware.model |
| cpu_model | 否 | BARE_METAL | 同上 | hardware.cpu_model |
| cpu_cores | 否 | BARE_METAL | 正整数或空；整机物理核心总数、不含超线程（§8/T39） | hardware.cpu_cores |
| memory_mb | 否 | 全部 | 正整数或空；单位 **MiB**（§8/§9）；BM 为硬件内存、VM 为分配内存 | hardware.memory_mb / virtual_machine.memory_mb |
| gpu_model | 否 | BARE_METAL | trim 后非空或空；≤255 | hardware.gpu_model |
| gpu_count | 否 | BARE_METAL | 非负整数或空；0=明确无 GPU，与未知 null 可区分（§8/T38） | hardware.gpu_count |
| host（VM Host 引用列） | 是（VM） | VIRTUAL_MACHINE | 引用已存在的 Host；须存在、未软删、`BARE_METAL` 且与 VM 同一 cluster（§9/§24-3）；**非本批创建** | virtual_machine.host_resource_id |
| vcpu | 否 | VIRTUAL_MACHINE | 正整数或空（§9/D01 §5.5） | virtual_machine.vcpu |
| disk_gb | 否 | VIRTUAL_MACHINE | 非负整数或空；单位 **GiB**；0=明确无磁盘（§9/T38） | virtual_machine.disk_gb |
| hypervisor | 否 | VIRTUAL_MACHINE | trim 后非空或空；≤255；一期无枚举（D01 §5.5） | virtual_machine.hypervisor |

**模板级约束（产品级）**：表头为固定列集合（列名/顺序由 D03 冻结）；缺失必填列、或出现模板未定义的列 → 报错（不静默忽略）；同一文件中一行只属于一种 `resource_type`；BARE_METAL 行出现 VM 专属列、或 VIRTUAL_MACHINE 行出现 hardware 列 → 报错（与 `docs/api/F004.md` §2.4/§2.5 互斥 422 口径一致）。

> **OPEN（非阻塞，D03）I-1**：示例列未含 §8 的 `serial_number`、`cpu_sockets`，也未含 VM 的 `vcpu/disk_gb/hypervisor`。PROPOSED 默认：D03 补齐为「BM 模板 + VM 模板」两套（或等价定稿），BM 模板可选补 `serial_number`、`cpu_sockets`，VM 模板含 `host` 与 VM 容量列，保证导入可覆盖 §8/§9 已确认字段；不新增业务规则。

> **OPEN（非阻塞，D03）I-2**：VM Host 引用列的取值形式。PROPOSED 默认：填同 cluster 内 Host 的 hostname（唯一性 §7 保证可解析），由服务端解析为 `host_resource_id`；D03 可裁定同时接受 UUID。不允许填 Cluster code/name 或任意字符串。

### 2.2 流程：预校验 → 确认 → 正式写入再次校验（§24-1、§24-2、T27）

1. **预校验（pre-validate，只读）**：
   - 执行 §23 权限检查（EDITOR/ADMIN；VIEWER 403；未认证 401）。
   - 解析文件（CSV / `.xlsx`），逐行依 §4.1/§6/§7/§8/§9 与 F004 契约校验（经同一 Service Layer，见 §2.3）。
   - **聚合返回全部错误行**（不 fail-fast），每项含 **行号、字段、原因**（§24-1、T27）。
   - 返回可读汇总（总行数、可导入行数、错误行列表）；**不写任何业务数据、不写 Audit**（无副作用、可重复）。
2. **用户确认**：用户查看错误行后确认导入。
   - 若预校验存在错误行：整批不可能成功，**不进入写入**（仍由用户修正文件后重试）；「确认」不改变该结论。
3. **正式写入（再次校验）**：
   - 执行 §23 权限检查（与预校验同口径）。
   - 在同一事务内**再次校验全部行**（防止预校验后状态变化，§24-2），逐行经同一 Service Layer 创建 Resource + 明细。
   - **整批成功或整批回滚**（§24-2）：任一行失败 → 全部回滚，回报失败原因（含行号/字段/原因），**不产生部分成功**；回滚不残留 Resource、明细、Audit、Activity（§22）。
   - 成功：整批创建，每行产生一条 CREATE Audit（§22），可在查询/详情/Activity 观察到。

> **OPEN（非阻塞，CONTRACT）I-3**：两步交互的接口形态（是否使用确认令牌 / 客户端再次上传同一文件）。PROPOSED 默认：预校验与写入为两个端点，写入端点接收同一文件并完整重校验（服务端不保存临时文件），确保「再次校验」语义；具体路径与方法由 CONTRACT 定。

### 2.3 同一 Service Layer 校验（§24，禁止旁路）

- 导入的逐行创建**必须复用普通 API `POST /api/v1/resources` 所使用的 Service Layer 校验与持久化路径**，不得为导入另建绕过服务层的直写 SQL/ORM 路径（§24）。
- 因此导入行与普通创建在以下方面必须一致：hostname 归一化与同 cluster 唯一（§7/T11）、资源类型/role/status 枚举与缺省（§6/T37）、硬件字段数值/单位/未知值 null（§8/T38）、VM Host 四条件与同 Cluster（§9/T08/T09）、cluster 存在且未软删（§4.1）、不可变字段不可隐式修改（§6）。
- 导入不得接受任何普通 API 会拒绝的组合；反之普通 API 拒绝的非法字段/关系在导入中同样报错。

### 2.4 权限（§23、§24-4、T25）

| 操作 | VIEWER | EDITOR | ADMIN |
| --- | --- | --- | --- |
| 预校验（上传即校验并展示错误行） | 不允许（403） | 允许 | 允许 |
| 正式写入导入 | 不允许（403） | 允许 | 允许 |

- 预校验与写入**均**执行服务端权限检查（§24-4）；前端隐藏按钮不替代服务端校验。
- 未认证先于权限返回 401；已认证缺权限返回 403（沿用 F002 错误语义）。
- 导入不授予删除/恢复/查看已删能力（那些仍限 ADMIN，§23）；导入写入 DELETE 不存在。

### 2.5 上限与同步处理（§24-4、T28）

- 一期**同步处理**：请求内完成预校验或写入，不引入异步任务/队列（§29 不引入 Celery 等）。
- 设置**文件大小上限**与**行数上限**：超限在解析前拒绝，返回明确错误，**不产生任何部分导入**。
- 具体数值由部署资源与性能验证确定并记入契约（D03）。

> **OPEN（非阻塞，D03）I-4**：文件大小 / 行数上限的具体数值与超限错误码（如 413/422）。PROPOSED 默认：给出保守上限（例如单文件 ≤ 若干 MB、≤ 若干千行）并在 D03 以真实 PostgreSQL 性能验证为依据定稿；产品只要求「有上限、超限拒绝、无部分导入、可验证」。

## 3. 领域影响分析

| 对象 | 关系 | 作用域 | 生命周期 | 约束依据及版本 | 未决问题/影响 |
| --- | --- | --- | --- | --- | --- |
| 导入文件（派生输入，非实体） | 含 1..N 个新增行 → Resource | 一个 Cluster 或多个 Cluster（按行 cluster 列） | 请求内一次性处理；不落库为业务对象 | §24（CONFIRMED） | 模板列/上限/接口形态（I-1..I-4，D03/CONTRACT） |
| Resource（新增） | 每行 1:1 创建；cluster 引用现存 Cluster | 行内 cluster | CREATE；无 UPDATE/DELETE/RESTORE | §4/§4.1/§6/§7（CONFIRMED） | 无新增实体/字段 |
| BareMetalDetail | 随 `BARE_METAL` Resource 同事务创建 | Resource 的 Cluster | 随 Resource | §8/§21（CONFIRMED） | 导入列子集（I-1） |
| VirtualMachineDetail | 随 `VIRTUAL_MACHINE` Resource 同事务创建；host 引用现存 BARE_METAL | Resource 的 Cluster；Host 必须同 Cluster | 随 Resource | §9/§21（CONFIRMED） | Host 引用列形式（I-2） |
| Cluster（被引用） | 1:N（一个 Cluster 下多行） | 全局唯一 code | 不被导入创建/修改/删除 | §5（CONFIRMED） | INACTIVE 仍可导入（§5/T29）；软删视为不存在 |
| Host Resource（被引用） | VM 行 N:1 指向现存 BARE_METAL | 同 Cluster | 不被导入创建/修改/删除 | §9（CONFIRMED） | 必须**批外**已存在 |
| Audit / Activity | 成功后每行 1 条 CREATE；失败整批无 | Resource | 与创建同事务 | §22（CONFIRMED） | 回滚无残留 |

数据完整性对应表（引用 `.pi/skills/data-integrity/SKILL.md`）：

| 规则依据及版本 | 作用域 | 记录/不变量 | 验证方向 |
| --- | --- | --- | --- |
| §7 / D01 §5.3 | 同 cluster hostname 唯一 | 归一化后 `(cluster_id, hostname_key)` 未删部分唯一；文件内重复与现存冲突均报错 | T01/T02/T11、文件内重复、软删复用 |
| §4.1/§6 | cluster 引用必填且有效 | 必须存在且未软删；name 不作引用 | 不存在/软删 Cluster → 行错误 |
| §8/§9、D01 §3 | 数值单位与未知值 | memory_mb=MiB、disk_gb=GiB；未知 null 非 0；gpu_count/disk_gb=0 语义 | T38 边界 |
| §9 | VM Host 正确性 | 存在、未软删、BARE_METAL、同 Cluster、非本批创建 | T08/T09/T28 |
| §24 | 整批原子性 | 全成或全回滚；失败无 Resource/明细/Audit 残留 | T27 |
| §23 | 权限 | 预校验与写入均服务端检查 | T25 |
| §22 | Audit 同事务 | 成功每行 CREATE；回滚无 Audit | 回滚后 Activity 为空 |
| §4 | 稳定 ID | cluster/host 解析为 UUID，不拼接字符串 | 关联正确 |

## 4. 必须遵守的已确认约束
- §24 全部：CSV/.xlsx；仅资源新增、不更新/覆盖；固定模板与逐列说明，示例列、VM 含 Host 引用列；预校验→确认→再次校验；整批成功或回滚、回滚无业务变更记录；文件内重复/现存冲突/非法字段/关系报错（含行号/字段/原因）；VM Host 已存在且满足 §9、不隐式创建、迁移先 BM 后 VM；走同一 Service Layer、禁止直写；同步处理、设定文件/行数上限；预校验与写入均检查权限。
- §4/§4.1：对象创建必填、稳定 ID、默认仅创建省略生效、名称去首尾空白禁空/控制字符。
- §5：Cluster code 全局唯一不重用；INACTIVE 不阻止导入；软删 Cluster 视为不存在。
- §6：类型 ∈{BARE_METAL,VIRTUAL_MACHINE}；Role/Status 枚举与缺省；创建后不可改 cluster/type。
- §7/T11：hostname 归一化一致，API 与导入不能绕过同一唯一性规则。
- §8/T38：硬件事可空、未知 null 非 0、单位 MiB、数值范围。
- §9/T08/T09：VM Host 四条件与同 Cluster；不校验容量超额。
- §21：软删对象默认隐藏、视为不存在；唯一性仅未删对象。
- §22：Audit 四类 action 同事务、Activity 全角色、回滚不留痕。
- §23/T25：权限矩阵服务端执行；EDITOR/ADMIN 可导入，VIEWER 不可。
- §25：`/api/v1/` 前缀；导入须有对应契约（路径由 CONTRACT 定）。
- §27：hostname 唯一、VM Host 类型/Cluster 正确由 DB+业务层共同保证，真实 PostgreSQL 验证。
- §32：CSV/.xlsx 整批新增导入为上线验收必要能力。

## 5. 可观察验收标准

| # | 验收标准 | 映射 |
| --- | --- | --- |
| A1 | 提供 CSV 与 `.xlsx` 两种格式的资源新增导入；两者行为一致 | §24 |
| A2 | 上传文件后先**预校验**，一次性展示**全部**错误行的**行号、字段、原因**（聚合，不 fail-fast） | §24-1、T27 |
| A3 | 预校验**不写任何业务数据、不写 Audit**；重复预校验同一文件结果一致且无副作用 | §24、§22 |
| A4 | 预校验通过后用户**确认**，再执行正式写入；写入时**再次校验**当前状态 | §24-1、§24-2、T27 |
| A5 | 正式写入任一行失败 → **整批回滚**，不产生部分成功 | §24-2、T27 |
| A6 | 回滚后无 Resource/明细残留，且**无 Audit/Activity 残留** | §24-2、§22 |
| A7 | 整批成功后每行创建对应 Resource（+BM/VM 明细），各产生一条 CREATE Audit，可在列表/详情/Activity 查询 | §22、§4 |
| A8 | 文件内重复（同一归一化 cluster+hostname）→ 报错（涉及两行行号），该批不写入 | §7、T11、T27 |
| A9 | 现存资源冲突（同 cluster+hostname 已存在未删）→ 报错，**不更新、不覆盖**现存资源，不产生 UPDATE Audit | §24、T28 |
| A10 | 非法字段（枚举、整数、单位、字符串长度/空白）→ 行错误含字段与原因；不绕过普通 API 校验 | §6/§7/§8/T37/T38 |
| A11 | 非法关系（VM Host 不存在/已软删/非 BARE_METAL/跨 Cluster）→ 行错误 | §9/T08/T09 |
| A12 | cluster 列不存在或已软删 → 行错误（软删视为不存在）；`INACTIVE` Cluster 允许导入 | §5/§21/T29 |
| A13 | 软删 hostname 可在导入中重用（不视为冲突）；恢复冲突按 §21 | §21/T03 |
| A14 | 导入与普通 API 使用**同一 Service Layer**：导入不能创建普通 API 会拒绝的对象，也不得直写绕过服务层 | §24 |
| A15 | 缺省：`role` 省略→OTHER、`status` 省略→UNKNOWN；可空字段省略→null；未知值存 null 不以 0 代替 | §6/§4.1/T37/T38 |
| A16 | 单位一致：`memory_mb` 按 MiB、`disk_gb` 按 GiB；模板/说明显式标注，不按 MB/GB 解释 | §8/T38 |
| A17 | `gpu_count=0`、`disk_gb=0` 接受并存 0（明确无），与未知 null 可区分；对应负值/零值按 §8/§9 拒绝 | §8/§9/T38 |
| A18 | **VM Host 必须已存在**且满足 §9；首次迁移先导入 BM 再导入 VM；不在同批隐式创建 Host | §24-3、§9、T28 |
| A19 | 同一批次中，**BARE_METAL 行新建的 Host 不能被本批 VM 行引用**（Host 须批外已存在）→ 行错误 | §24-3、T28 |
| A20 | 文件大小或行数超过签核上限 → 解析前拒绝并明确报错，无部分导入 | §24-4、T28 |
| A21 | 模板固定列：缺失必填列/出现未定义列报错；VM 模板含 Host 引用列；BM/VM 专属列错配报错 | §24、F004 §2.4/§2.5 |
| A22 | 预校验与写入**均**执行 §23 权限检查：VIEWER→403；EDITOR/ADMIN→允许；未认证→401 | §23/§24-4/T25 |
| A23 | 一期同步处理（请求内完成，无异步任务）；同一文件重复确认在成功后再导入因冲突报错、不产生新行 | §24-4、§24 |
| A24 | 导入不创建/修改 Cluster；cluster 仅作引用且须已存在 | §24、§5 |
| A25 | 固定模板提供**逐列说明**（含单位、枚举、必填性）供用户下载/查看 | §24 |
| A26 | 未支持对象（Interface / IPAddress / Network / Cluster / Service 等）不在本 Feature 导入；上传其数据不产生对象 | §24、§34 |

## 6. 不变量（I-1…）
- **I-1 整批原子性**：一次写入在单一事务内；全部行成功提交，任一行失败全部回滚，不存在中间态（§24-2/T27）。
- **I-2 错误聚合**：预校验一次返回全部错误行，每项含行号、字段、原因，不 fail-fast（§24-1/T27）。
- **I-3 预校验只读幂等**：预校验不写业务数据、不写 Audit、不改状态；对同一文件与同一状态重复调用结果一致（§24、§22）。
- **I-4 写入前再次校验**：写入在事务内基于最新状态重跑全部校验，覆盖「预校验后状态变化」窗口（§24-2）。
- **I-5 软删视为不存在**：软删 Cluster/Host 视为不存在；hostname 唯一性仅对未删对象；软删 hostname 可重用（§21/§7）。
- **I-6 仅新增、不更新/覆盖**：导入只有 CREATE 路径；按 (cluster, hostname) 命中现存未删资源即报错，绝不 update（§24/T28）。
- **I-7 同 Service Layer**：导入复用普通创建的服务层校验与持久化；禁止绕过服务层直写数据库（§24）。
- **I-8 失败零残留**：失败批不产生 Resource、BareMetalDetail/VirtualMachineDetail、Audit、Activity；无「部分成功」痕迹（§24-2/§22）。
- **I-9 Host 批外已存在**：VM 行的 Host 必须在本批次开始前已存在于库中；不得隐式创建，也不得引用本批（含更早行）新建的 Host（§24-3/§9）。
- **I-10 上限先于处理**：文件大小/行数上限在解析前拦截；超限直接拒绝，无部分导入（§24-4/T28）。
- **I-11 权限双重检查**：预校验与写入均执行 §23 权限检查，前端隐藏不替代服务端校验（§24-4/§23）。
- **I-12 单位与未知值**：`memory_mb`=MiB、`disk_gb`=GiB；未知存 null 不以 0 代替；`gpu_count=0`/`disk_gb=0` 表示「明确无」（§8/§9/T38）。
- **I-13 归一化一致**：导入使用与唯一性/API 相同的 hostname 归一化（trim + ASCII 小写，禁 str.lower/lower()），不新增口径（§7/§4.1/D01 §5.3）。
- **I-14 稳定 ID 引用**：cluster 与 VM Host 引用解析为稳定 UUID 落库，不依赖名称/ code 字符串拼接（§4）。
- **I-15 同步处理**：一期请求内同步完成，不引入异步任务/队列（§24-4/§29）。
- **I-16 角色/权限不变**：导入不授予 CREATE 之外的删除/恢复/查看已删能力（§23）。
- **I-17 不新增对象类型**：导入只作用于 Resource（BM/VM）及其明细，不创建 Cluster/Interface/Network/IP/Service（§24/§34）。

## 7. 明确排除项（不宣称）
- **不做更新/覆盖**：不按 hostname upsert，不提供「存在则更新」模式（§24）。
- **不做其他对象导入**：Interface、IPAddress、Network 导入为后续扩展（§24）；Cluster、IPPool、Service、ServiceEndpoint 亦不在本 Feature。
- **不做部分成功/半成功**：整批原子，无跳过错误行继续导入的选项（§24-2）。
- **不做异步/后台任务**：一期同步处理，不引入 Celery/队列/进度任务系统（§24-4/§29）。
- **不新增业务规则/字段/实体**：不改 §4–§16 的字段口径、枚举、唯一性、单位；模板内容依 §24 + D01/D03，不新增未确认字段。
- **不做一期集成验收/跨功能 T01–T41 全量回归**（F016）；**不做完整 Audit 查询页与已删除对象管理**（F015）；**不做全局搜索/Dashboard**（F013）。
- **不做导入历史/任务台账页面**：导入不是新业务对象，无独立审计对象类型（若设计需要可复用 Resource 的 Audit）。
- **不做 IPv6、CSV 分隔符/编码的多种变体、公式/宏处理、图片/附件**等（§24 未要求）。
- 不宣称上线验收批准（§32）。

## 8. 依赖与未决问题

依赖（CONFIRMED）：
- F003（Cluster：code 唯一、INACTIVE、软删/恢复、列表基线）、F004（Resource：hostname 归一化与唯一、类型/Role/Status、软删/恢复、Audit、权限、`POST /api/v1/resources` 契约）、F005（BareMetalDetail 字段口径）、F006（VirtualMachineDetail：Host 四条件、同 Cluster）均已 DONE。
- D01 v11（字段格式、归一化、单位、省略语义）为导入校验的共享权威；D03（模板/上限/性能）在本 Feature CONTRACT 签核。

**BLOCKING：无。**

CONFIRMED 清单：§24 全部；§4/§4.1；§5；§6；§7（T11）；§8/§9（T38/T39 相关）；§21；§22；§23；§25；§27；§31 T27/T28；§35.2 Q02-A/Q10-A/Q10-B。

PROPOSED / OPEN（非阻塞，均给可实施默认，交 D03 / CONTRACT 定稿，不自行设为永久规则）：
- **I-1（OPEN，D03）模板最终列集**：示例列是否补 `serial_number`/`cpu_sockets` 及 VM 容量列、BM 与 VM 是否为两套模板。PROPOSED：两套固定模板，BM 可含 `serial_number`/`cpu_sockets` 可选列，VM 含 `host` + `vcpu`/`disk_gb`/`hypervisor`。Owner：Architect/Backend。
- **I-2（OPEN，D03）Host 引用列取值形式**：PROPOSED：同 cluster 内 Host 的 hostname（可解析为 `host_resource_id`），D03 可并接受 UUID。Owner：Architect/Backend。
- **I-3（OPEN，CONTRACT）两步交互接口形态**：PROPOSED：预校验端点 + 写入端点，写入接收同一文件并完整重校验（服务端不留临时文件）。Owner：Architect。
- **I-4（OPEN，D03）文件大小/行数上限数值与超限错误码**：PROPOSED：以真实 PostgreSQL 性能验证定保守上限；超限返回明确错误（413/422 由 CONTRACT 定），无部分导入。Owner：Architect/Backend/Tester。
- **I-5（OPEN，D03/CONTRACT）空单元格语义与枚举大小写**：CSV 空串可能表示「省略」或「显式 null」。PROPOSED：空=省略（defaults 生效；非必填→null），表格导入无「显式 null」概念；`resource_type`/`role`/`status` 采用大写规范值，非规范值报错。Owner：Architect/Product 核对。
- **I-6（OPEN，D03/CONTRACT）错误响应形态与行号约定**：PROPOSED：预校验合法解析即使有行错误也返回 200 + 结构化错误列表；文件级不可解析（格式/表头/超限）→ 4xx。行号取 1-based 文件行号（表头为第 1 行）或等效数据行号，D03 冻结。Owner：Architect。
- **I-7（OPEN，设计，非阻塞）metadata / description 是否可导入**：§24 示例列未含。PROPOSED：一期导入不含 `metadata`/`description` 列，导入对象取契约默认（`metadata={}`、`description=null`）；如 D03 需要可纳入可选列，不新增业务规则。Owner：Architect/Product 核对。
- **I-8（NOTE）计划字段**：`project-plan.yaml` F014 未填 `layers`/`api_required`，ARCHITECTURE 阶段补齐（预期 `api_required=true`，layers 含 backend/frontend，database 视 D03 是否引入新表/索引而定）。
- **I-9（NOTE，D01 关闭核对）**：plan F014 acceptance 要求「D01 最终关闭核对完成」；D01（`docs/architecture/d01-conventions.md` v11）对 Resource/BM/VM 字段口径已就绪，本 Feature CONTRACT 引用其完成导入字段口径核对后，记 D01 关闭。

## 9. 交 Architect 的输入
1. **两阶段导入 API**：预校验端点与写入端点（路径/方法由 CONTRACT 定，挂 `/api/v1/`）；请求含文件与格式；响应含总行数、可导入行数、错误列表（行号/字段/原因）、写入结果（创建数量）；沿用 F002 错误信封与 401/403/422 口径。
2. **模板与解析**（D03）：CSV/.xlsx 固定模板、列名/顺序、逐列说明、单位标注、VM Host 引用列；格式/表头/未知列/类型错配的处理。
3. **逐行校验**：复用 F004 `POST /api/v1/resources` 的 Service Layer；覆盖 §4.1/§6/§7/§8/§9 全部校验与缺省；cluster→cluster_id、host→host_resource_id 解析；禁止直写。
4. **原子与并发**：单事务整批提交/回滚；写入前再次校验；对候选 (cluster, hostname) 与 VM Host 的并发冲突以 DB 唯一/约束兜底并整批回滚（§27）；回滚不留 Audit（§22 同事务）。
5. **上限与性能**（D03）：文件大小/行数上限、超限拒绝、同步处理、真实 PostgreSQL 性能验证依据。
6. **权限**：预校验与写入均服务端 §23 检查（EDITOR/ADMIN）。
7. **前端**：上传入口、模板下载/逐列说明、预校验结果展示（错误行表格：行号/字段/原因）、确认导入、写入结果与失败回滚提示；无部分成功 UI 语义。
8. **待裁定**：I-1 模板列集、I-2 Host 引用列形式、I-3 接口形态、I-4 上限数值、I-5 空值/枚举口径、I-6 错误响应与行号、I-7 metadata/description。
9. **边界**：不新增实体/字段；不更新/覆盖；不做 Interface/IP/Network 导入；同步；不引入 §29 禁止技术。

## 10. 结论与下一步
无 Blocking Questions，无待用户裁定事项。**READY FOR ARCHITECT。**

下一步 ARCHITECTURE / CONTRACT：
- 产出 F014 架构方案、layers、api_required；在 **CONTRACT 签核 D03**（固定模板、VM Host 引用列、逐列说明、同步导入文件大小/行数上限及性能验证依据，Owner：Architect/Backend/Tester）。
- 引用 D01 v11 完成导入字段口径核对，记 **D01 最终关闭**（I-9）。
- 落实 §24 整批原子、再次校验、回滚无 Audit 残留、同一 Service Layer、权限双重检查；由 Database 依 D03 签核是否需新增约束/索引并规划真实 PostgreSQL 验证。