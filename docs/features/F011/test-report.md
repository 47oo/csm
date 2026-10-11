# F011 Service 服务登记 — Test Report

本文件同时承载 TEST_DESIGN 与 TEST（TEST 阶段在同一文件追加执行结果）。两阶段分别记录版本、结论与证据；TEST_DESIGN 不填充执行 PASS。

---

## Test Design

- **版本**：TD-1
- **日期**：2026-10-09
- **角色**：Tester（TEST_DESIGN 模式）
- **结论**：`TEST DESIGN READY`（TD-1）
- **依据**：
  - `docs/product/requirements-v3.md` revision 3（§4、§4.1、§5、§15、§16、§17、§18、§19、§21、§22、§23、§25–§28、§31 T21/T23/T24/T25/T26/T37/T40/T41、§32、§33、§35.2 Q02-A/Q06/Q10-A/Q10-B、§35.3 D01/D02）
  - `docs/features/F011/product.md`（PRODUCT `READY FOR ARCHITECT`，2026-10-09；A1–A18、I-1–I-6、明确排除项）
  - `docs/features/F011/architecture.md`（ARCHITECTURE `READY FOR DESIGN`，2026-10-09；§9 验证策略、DR-140–DR-154）
  - `docs/api/F011.md` 草案 v0（CONTRACT DRAFT，目标 READY；7 端点、字段契约 §2、错误码 §1.2 复用无新 reason、分页排序过滤 §4、软删/恢复 §5/§6、校验顺序 §6、并发 §7、审计白名单 §8、Endpoint 引用扩展点 §6/§9）
  - `docs/database/f011-service.md`（**尚未产出**，DATABASE Gate 未定稿；TD-1 按 architecture §1/§7 草案假设）
  - `docs/architecture/d01-conventions.md` v9（§5/§5.2/§5.10 待 v10 签核）
  - `docs/api/F004.md` v3、`docs/database/f004-resource.md` v1（Resource 基座、`cluster_service` 引用/依赖检查器注册表、`resource←` 反向检查机制）
  - `docs/api/F009.md` v1、`docs/database/f009-ip-pool.md` v1（`name_key` translate 口径、部分唯一、引用检查器注册先例）
  - `docs/api/F010.md` v1、`docs/database/f010-ip-address.md` v1（`register_ip_address_reference_checker` 扩展点先例、`committed_engine` 真提交口径）
  - `docs/features/F009/test-report.md`、`docs/features/F010/test-report.md`（TD-1/TD-2/TE 模板、夹具/环境、真提交口径、证据边界声明）
  - `docs/project/handoff.md`、`docs/project/implementation-rules.md`、`.pi/skills/data-integrity/SKILL.md`、`AGENTS.md`
  - `docs/project/project-plan.yaml` plan_revision 4 F011 条目（`current_stage: DATABASE`，`next_action: DATABASE 与 TEST_DESIGN Gate`，layers=database/backend/frontend，api_required=true）
- **状态属性**：TD-1 `READY` 仅表示 A1–A18 已映射到可观察判据、边界/并发场景可执行、夹具与可验证性检查已建立；**不代表测试已运行、不填充执行 PASS、不批准实现或合并**。DATABASE 设计（`docs/database/f011-service.md`）与 CONTRACT（`docs/api/F011.md`）尚未定稿、D01 v10 §5.10 未签核；§8 列 OPEN 待 DATABASE / CONTRACT Gate 后由 TD-2 逐项关闭。**不因 DATABASE 未定稿而直接 BLOCKED**（architecture §1/§7/§9 已给出可执行的实体、约束与引用检查器方案）。跨功能完整 §31 回归与 §32 上线验收不在本 Feature（见 §5）。

### 版本记录

| 版本 | 日期 | 变更 |
| --- | --- | --- |
| TD-1 | 2026-10-09 | 初版：A1–A18 映射 V1–V18，补充 V19–V27 与 V-DB-1…V-DB-9；边界/并发 B1–B40；夹具/环境设计；F011 独立 / F011+Endpoint 桩 / 留待 F012 三类分界；§8 OPEN 复核项（待 DATABASE/CONTRACT/D01 v10 后由 TD-2 关闭）。 |

> 复核基线（待 TD-2）：`docs/database/f011-service.md`（DATABASE Gate，未产出）、`docs/api/F011.md` v0（CONTRACT Gate，未定稿）、`d01-conventions.md` v10 §5.10/§5.2/§5 表（未签核）。TD-1 的表名/列名/约束名/FK/索引/迁移 0011 编号/错误路径/reference_exists details 形状均按 architecture §1/§4/§7 草案假设，TD-2 逐项核对后方可作为执行依据。

---

### 0. 数据完整性对应表（F011 范围）

方法依据 `.pi/skills/data-integrity/SKILL.md`；DB 列/约束以 DATABASE Gate 定稿为准（TD-1 为草案）。

| 规则依据及版本 | 作用域/写入入口 | 数据库保证（架构草案，待签核） | 业务层保证 | 并发/生命周期边界 | 验证与证据 |
| --- | --- | --- | --- | --- | --- |
| §4.1/§27/DR-141 Service name 同 Resource 未删唯一 | POST/PATCH/restore `/api/v1/services` | 部分唯一 `uq_services_resource_id_name_key UNIQUE(resource_id,name_key) WHERE deleted_at IS NULL` + `name_key` CHECK | trim；逐码位 ASCII 折叠；冲突→409 `unique_conflict{field:"name"}`；内部普通空格保留不合并 | 索引仲裁；软删释放；恢复重检冲突拒 | V1/V2/V3/V15/V16、B1–B9/B21/B29/B30/B34；真实 PG |
| §4.1/T40 name 规范 | POST/PATCH | `ck_services_*`（ASCII backstop + 长度 1–255） | trim→非空→禁 Cc/Cf→长度；中文/内部普通空格保留 | Cc/Cf 应用主责任 | V1、B1/B3/B4/B5/B6；真实 PG |
| §4.1/§15/DR-144 resource 引用与不可变 | POST/PATCH | `resource_id uuid NOT NULL` + FK RESTRICT | 422 field="resource"（缺失/不存在/软删）；PATCH 出现 resource/resource_id→422 | 无跨行并发 | V4/V9、B10/B11；真实 PG |
| §15/DR-142 status 默认与取值 | POST/PATCH | `status varchar(16) NOT NULL DEFAULT 'UNKNOWN'` + CHECK∈3 值 | 省略→UNKNOWN；非法/显式 null→422；仅 API 变更、不由名称推导 | 无并发 | V5/V6、B12/B13；真实 PG |
| §15/DR-143 metadata | POST/PATCH | `metadata JSONB NOT NULL DEFAULT '{}'` + CHECK `jsonb_typeof='object'` | 非 object/显式 null→422；整值替换 | 无并发 | V8、B15/B16；真实 PG |
| §21/§16/DR-146 Service←ServiceEndpoint 引用保护 | DELETE Service | 无（Endpoint 在 F012，跨表） | 引用检查注册表（F011 空集）；409 `reference_exists{references:[{object_type:"service_endpoint",...}]}`；不级联 | F012 注册真实 provider | A10 桩 + F012 端到端（T23）；V21、B17/B18/B19 |
| §21/DR-147 Resource←Service 引用 | DELETE Resource (F004) | FK `services.resource_id → resources(id) ON DELETE RESTRICT`（物理兜底） | F011 注册 `register_reference_checker("resource", _undeleted_service_references)`；未删 Service→409 `reference_exists{references:[{object_type:"service",...}]}` | 软删释放；恢复重检 | V22、B31/B32；真实 PG |
| §21/DR-148 Service 恢复重检 | restore Service | `deleted_at` + 部分唯一 | 重检 name 唯一、Resource 未软删/存在；失败不覆盖新对象；不级联、不自动恢复 Endpoint | 恢复 vs 并发重建竞争 | V3/V11、B20/B21/B22/B23/B34；真提交 |
| §22/DR-150 CREATE/UPDATE/DELETE/RESTORE 写 Audit 同事务 | Service 业务服务 | 复用 `audit_logs` append-only | `object_type="service"`；白名单 `{resource_id,name,status,description,metadata}`；异常同回滚 | 版本冲突无静默重试 | V13、B25/B26；真提交 |
| §23 乐观锁 | PATCH/DELETE/restore | 复用 `version int NOT NULL DEFAULT 1 CHECK >=1` | 条件 UPDATE `WHERE id AND version=:expected`；rowcount=0→409 `VERSION_CONFLICT{current_version}` | 两连接同 version 仅一成功 | V17、B33；真提交 |
| §27/DR-151 迁移 0011 | Alembic `0011_services` | `down_revision=0010_ip_addresses`；全表新建无回填；单一 head；对称可逆 | — | 真库 up/down/up | V19/V20、B37；真实 PG |

---

## 1. 验收映射（product.md A1–A18 → 验证项）

执行环境：`真实 PG` = 独立测试库（库名含 `test`）；`后端集成` = ASGI 应用 + 真实 PG（非 SQLite）；`真提交` = `committed_engine`（真实连接 + 真实提交 + TRUNCATE teardown）；`机制级` = 真实 PG raw SQL 直接验证；`静态` = 路由清单/源码检查；`前端` = 构建 + client 机制级（真实 API 集成以入口 Nginx 为准）。**Endpoint 桩** = 经 F011 `register_service_reference_checker` 注册返回固定引用集的测试侧检查器。

> **分界声明（关键）**：
> - **F011 独立可验证（不依赖 F012 数据）**：A1–A9、A11–A18；对应 §31 T21、T24、T25、T26、T37、T40、T41 的 Service 子集。
> - **F011 + Endpoint 桩（可验证契约、挂钩与引用拦截路径，不能证明真实 Endpoint 数据语义）**：A10 的引用检查注册点、`register_service_reference_checker` 挂钩、有未删 Endpoint 桩引用时 DELETE→409 `reference_exists`；对应 T23 的 **结构/挂钩部分**。
> - **必须留待 F012（F011 局部 PASS 无法覆盖）**：含真实 Endpoint 的端到端（T23 完整）；真实 `references:[{object_type:"service_endpoint",...}]` 数据。
> - **F011 仅提供数据、页面/聚合归 F013**：A18 的 §17 全局 Service 搜索、§19 Cluster Detail Services、§20 Dashboard 归 F013。
> - **不得以 F011 局部 PASS 拼接整条 T21/T23/T24/T25/T26/T37/T40/T41 通过**；端到端结论只能在 F012/F013 交付后由对应集成测试给出。

| 验收（product.md） | 验证项 | 执行环境 | 可观察判据（PASS / FAIL） |
| --- | --- | --- | --- |
| A1 名称 trim；空名/控制字符拒（422）；中文与内部普通空格允许且不自动合并 | **V1**；**V-DB-1/V-DB-2** | 后端集成 + 真实 PG | PASS：`"  SSH "`→201 落库 `SSH`；`""`/`"   "`/含 Cc/Cf（`\x00`/`\x1f`/`\u200b`）→422 field="name"；`"web 1"`/`"web  1"`/中文名→201 且内部普通空格原样保留（不合并）；raw 直插未 trim/空/控制/超长被 CHECK 拒。FAIL：不 trim、内部空格被合并、空名落库、CHECK 缺失 |
| A2 同 Resource 大小写不敏感重名拒（409 `unique_conflict{field:"name"}`）；跨 Resource 同名允许 | **V2**；**V-DB-3** | 后端集成 + 真实 PG | PASS：同 resource `SSH`/`ssh`/`Ssh` 第二次 POST→409 `CONFLICT{reason:"unique_conflict",field:"name"}`；不同 resource 同名→均 201；首条 name 原样保留展示；raw 直插同 `(resource_id,name_key)` 未删被部分唯一拒、跨 resource 允许。FAIL：重名成功、跨 resource 被拒、无兜底 |
| A3 软删后同名可重建；存活同名存在时创建失败；名称被复用时旧 Service 恢复失败且不覆盖新对象 | **V3**；**V-DB-3** | 后端集成 + 真实 PG | PASS：软删同名→重建 201（新 id）；存活同名→创建 409；旧对象 restore→409 `unique_conflict` 且新对象不被覆盖、旧对象保持软删。FAIL：软删后仍拒、覆盖新对象 |
| A4 缺失 resource/name 创建失败（422）；resource 不存在/已软删时创建失败（422 field="resource"） | **V4**；**V-DB-4** | 后端集成 + 真实 PG | PASS：省略/`null`/`""` resource 或 name→422；resource 随机 UUID→422 field="resource"；指向软删 Resource→422 field="resource"；无 Service 行。FAIL：任一被接受 |
| A5 status 省略→UNKNOWN；显式设置 RUNNING/STOPPED/UNKNOWN 按值保存；显式 null/非法值→422 | **V5**；**V-DB-5** | 后端集成 + 真实 PG | PASS：省略→`UNKNOWN`；显式三值落库并回显；`"running"`/`""`/`"OTHER"`/`null`→422 field="status"；raw CHECK 拒非法。FAIL：默认错、非法落库 |
| A6 status 为人工维护：仅经 API 变更；不由名称（如 slurmd/node_exporter）或外部探测推导/自动转换；登记 slurmd 不触发 Slurm 部署或状态同步 | **V6**；**静态** | 后端集成 + 静态 | PASS（F011 侧）：创建 name=`slurmd`/`node_exporter` 省略 status→UNKNOWN；无任何按 name 推断 status 的写路径；PATCH status 仅由显式请求变更；静态核对 F011 无 Slurm/监控/探测集成、无自动状态转换。FAIL：名称触发状态、存在自动转换入口 |
| A7 description 可空、PATCH 显式 null 清空、PATCH 省略保持 | **V7** | 后端集成 + 真实 PG | PASS：创建省略/显式 null→响应 `null`；创建给值→保存；PATCH 省略→保持；PATCH 显式 null→清空；被拒请求不改库值。FAIL：null 未清空、省略被重置 |
| A8 metadata（PROPOSED→设计决定）：省略→{}；整值替换；显式 null/非 object→422；响应暴露 | **V8**；**V-DB-6** | 后端集成 + 真实 PG | PASS：创建省略→`{}`；POST 非 object（`[]`/`"x"`/`1`）或显式 null→422 field="metadata"；PATCH 给新 object→整值替换（不增量合并旧键）；响应含 `metadata`；raw CHECK 拒非 object。FAIL：增量合并、非法落库、未暴露 |
| A9 resource 创建必填；PROPOSED 创建后不可改（PATCH 出现 resource→422） | **V9**；**V-DB-4/V-DB-7** | 后端集成 + 真实 PG | PASS：创建省略 resource→422；PATCH 出现 `resource`/`resource_id`（含同值）或 `id`/`name_key`→422；被拒请求不改库值与 version；无 DB 不可变触发器（应用保证）。FAIL：resource 被改、同值也被拒（正确）之外的静默改写 |
| A10 存在未删除 Endpoint 引用时删除被拒并返回引用列表（references）；不隐式级联；无引用可软删 | **V10**（桩）；**F012 端到端** | 后端集成 + 真实 PG + Endpoint 桩 | PASS（桩）：注册返回固定引用 `[{object_type:"service_endpoint",object_id,label}]` 的测试检查器后，DELETE→409 `CONFLICT{reason:"reference_exists",references[]}`，库中 Service `deleted_at` 仍 null、version 不变；无引用（默认空集）→204 软删；静态核对无级联删除 Endpoint 路径。**含真实 Endpoint 的端到端归 F012（T23）**。FAIL：引用被忽略、无 references、级联 |
| A11 Service 恢复重检名称唯一与 Resource 有效性；名称被复用/Resource 仍删时恢复失败且不覆盖新对象；恢复不自动恢复 Endpoint | **V11** | 后端集成 + 真实 PG + Endpoint 桩 | PASS：name 被复用→409 `unique_conflict{field:"name"}`；Resource 仍软删/缺失→409 `dependency_deleted{conflicts:[{object_type:"resource",object_id}]}`；失败保持软删且新对象不被覆盖；成功恢复 `deleted_at=null`、不自动恢复/创建 Endpoint；对未软删对象 restore→409 `not_deleted`。FAIL：顺序/错误码不符、覆盖、恢复关联对象 |
| A12 权限：VIEWER 只读；EDITOR 增改 Service；删除/查看已删/恢复 ADMIN；服务端执行 | **V12** | 后端集成 + 前端 + Compose | PASS：VIEWER POST/PATCH→403、GET→200；EDITOR POST/PATCH 201/200、DELETE/restore 403；ADMIN 成功；未认证 401；`deleted=include|only` 非 VIEW_DELETED→403；`require_permission` 服务端强制（静态核对）。FAIL：越权成功、仅前端隐藏 |
| A13 CREATE/UPDATE/DELETE/RESTORE 写 Audit 且同事务；Activity 全角色可见；不记敏感内容 | **V13** | 后端集成 + 真实 PG（真提交） | PASS：四 action 各一条 `audit_logs`（`object_type="service"`、`object_id`=Service UUID、UPDATE 含 before/after、白名单 `{resource_id,name,status,description,metadata}`）；`GET /activity` 对三角色 200；注入 audit 失败时业务与 audit 同回滚、无残留行；快照不含敏感内容。FAIL：缺 action、不同事务、Activity 限权 |
| A14 默认列表隐藏软删；按 resource、status 过滤，按 name 模糊；分页/排序/过滤符合列表基线 | **V14** | 后端集成 + 真实 PG | PASS：默认无软删；`resource_id`/`status`/`q`/`deleted` 过滤正确；`q` 为 name 大小写不敏感子串、trim 后空视为未提供；分页 `total/page/page_size` 边界正确；`sort∈{name,status,created_at,updated_at}`+`order` 生效、附 `id` 稳定；`sort=name` 按 name_key；非法参数→422。FAIL：软删泄漏、过滤/分页/排序错 |
| A15 DB 对同 Resource 未删除 name（归一化键）部分唯一兜底，真实 PG 验证 | **V15**；**V-DB-3** | 真实 PG + 静态 | PASS：`pg_indexes`/`pg_constraint` 含部分唯一 `(resource_id,name_key) WHERE deleted_at IS NULL`；raw 直插存活重名被拒、跨 resource/软删后同名成功；软删 Service 行仍物理存在。FAIL：缺约束、全量唯一、仅 ORM 层 |
| A16 名称归一化在 API、导入（F014 适用时）、搜索（F013）与 DB 间一致；仅未删除对象参与唯一 | **V16**；**V-DB-2/V-DB-3** | 后端集成 + 真实 PG + 静态 | PASS（F011 侧）：应用 `name_key` 与 DB `translate(btrim(name))` 逐项一致（仅 ASCII A–Z→a–z，中文/非 ASCII 原样，`ß`/`İ` 不折叠）；`name_key` 不暴露；软删不参与唯一；向 F014/F013 暴露同口径（静态核对）。F014/F013 执行各自一致性。FAIL：折叠口径不一致、软删参与 |
| A17 乐观锁：过期版本编辑被拒（409 `VERSION_CONFLICT`），无静默覆盖 | **V17** | 后端集成 + 真实 PG（真提交） | PASS：两独立连接同 version PATCH，一方 200 且 `version+1`，另一方 409 `VERSION_CONFLICT{current_version}`；最终库值来自成功方；DELETE/restore 同样拒绝过期版本。FAIL：双成功、无 409 |
| A18 Service 经 Resource 间接归属 Cluster；Resource Detail Services 区域与 §17 Service 搜索可获得数据 | **V18**；**F013** | 后端集成 + 前端 | PASS（F011 侧）：响应 `resource{id,hostname}` 可解析归属；`GET /api/v1/services?resource_id=…` 返回该 Resource 的 Service 集合，供 §18 Resource Detail Services 区域消费（前端机制级）；Service 无 cluster 直字段（静态核对）。§17 全局搜索、§19/§20 聚合展示归 F013。FAIL：归属解析错、按 resource_id 取不到数据 |

补充验证项（非直接 A 映射）：

| 验证项 | 内容 | 环境 | 判据 |
| --- | --- | --- | --- |
| **V19** 迁移 0011 | Alembic up/down/up + 单一 head + 无回填 | 真实 PG | PASS：`alembic heads` 单一 `0011_services`（`down_revision=0010_ip_addresses`）；up 建表/约束/部分唯一/索引；down 逆序且 0010 对象保留；re-up 集合一致；无回填、不重复启用扩展 |
| **V20** 表/约束/索引目录（机制级） | raw PG 目录断言 | 真实 PG | PASS：`pg_constraint`/`pg_indexes`/`pg_attribute` 含 name/name_key/status/metadata/version CHECK、`resource_id` FK RESTRICT、部分唯一、约定索引 `ix_services_{resource_id,status,deleted_at}`；无 pg_trgm/GIN 新增 |
| **V21** Service←ServiceEndpoint 引用检查扩展点 | F011 提供 `register_service_reference_checker`（默认空集）；`delete_service` 调用点存在 | 后端集成 + 静态 | PASS：默认空集不误报（无 Endpoint 数据也能删）；注册返回引用集的桩后 A10 生效；调用点位于软删前；与 F010 `ip_address_reference` 同构 |
| **V22** Resource←未删 Service 引用检查器 | F011 注册 `register_reference_checker("resource", …)`；`resource.py` 导入 service 模块 | 后端集成 + 真实 PG + 静态 | PASS：存在未删 Service 的 Resource `DELETE /api/v1/resources/{id}`→409 `reference_exists`+`references:[{object_type:"service",object_id,label}]`；软删 Service 后可删；注册由导入链保证（静态） |
| **V23** 响应契约 | Service 响应字段/嵌套 | 后端集成 | PASS：含 `id、resource{id,hostname}、name、status、description|null、metadata、version、created_at/updated_at、deleted_at`；列表 `{items,page,page_size,total}`；不含 `name_key`/`resource_id` 原始列/cluster 直字段 |
| **V24** 校验顺序 | POST/PATCH/DELETE/restore 优先级 | 后端集成 | PASS：POST 401→403→body(422)→resource(422)→name(422)→name 唯一(409)→写+Audit→201；PATCH 401→403→body(422)→可见性(404)→version(409)→name 归一化(422)→name 唯一(409)→写+Audit→200；DELETE 401→403→对象(404)→version 校验(422)→版本(409)→引用检查(409)→软删；restore 查找(404)→not_deleted(409)→版本(409)→name 唯一(409)→Resource 依赖(409)→恢复 |
| **V25** PATCH exclude_unset / 只读 / 未知 | 省略保持；显式 null 仅清 nullable（description）；必填/非 nullable 显式 null→422；`resource`/`resource_id`/`id`/`name_key`/只读/未知字段→422 | 后端集成 | PASS：逐项符合 D01 §4 与 Contract §2.4；被拒请求不改库值与 version |
| **V26** FK 物理语义（机制级） | raw 物理 `DELETE FROM resources`（被未删 Service 引用） | 真实 PG | PASS：被 FK RESTRICT 阻止（`confdeltype='r'`）；报告标注机制级（API 无物理删除路径） |
| **V27** 只读无副作用 | GET 列表/详情/activity | 后端集成 | PASS：纯 SELECT，无业务写、无 audit 行、version 不变 |

**数据库机制级验证项（V-DB，真实 PG raw SQL）**：

| 编号 | 内容 | 映射 |
| --- | --- | --- |
| **V-DB-1** | name 边界 CHECK（0/空/首尾空白未 trim/控制字符/256 拒；1–255 接受；内部普通空格/中文保留） | A1/V1/B1/B3/B4/B5/B6 |
| **V-DB-2** | name_key CHECK 与 `translate(btrim(name))` 一致（`SSH`/`ssh` 同键、`ß`/非 ASCII 原样、禁 `lower()`） | A1/A16/V1/V16/B2/B3 |
| **V-DB-3** | 部分唯一 `(resource_id,name_key) WHERE deleted_at IS NULL`（同 resource 重名拒/跨 resource 允许/软删释放/恢复冲突） | A2/A3/A15/A16/V2/V3/V15/B7/B8/B9/B29/B30/B34 |
| **V-DB-4** | `resource_id` NOT NULL + FK RESTRICT；无资源时插入被 FK 拒 | A4/A9/V4/V9/B10/B11 |
| **V-DB-5** | status NOT NULL DEFAULT 'UNKNOWN' + CHECK∈3 值；非法 raw 拒 | A5/V5/B12 |
| **V-DB-6** | metadata JSONB NOT NULL DEFAULT '{}' + CHECK `jsonb_typeof='object'`；非 object raw 拒 | A8/V8/B15 |
| **V-DB-7** | version default 1、CHECK ≥1；时间戳列；`deleted_at` 可空；对象目录/索引 | A9/A17/V17/V20 |
| **V-DB-8** | 软删/恢复与部分唯一交互（恢复置 `deleted_at=null` 重新受约束） | A3/A11/V3/V11/B8/B21/B34 |
| **V-DB-9** | 迁移 0011 up/down/up、单 head、无回填、扩展未重复启用 | V19/B37 |

---

## 2. 边界与并发场景（B 编号，TEST 阶段执行）

| 编号 | 场景 | 步骤 | 判据 |
| --- | --- | --- | --- |
| B1 | 名称首尾空白 trim | `"  SSH  "`、`"\tssh\n"` | 201；落库 `SSH`/`ssh`；`name_key` 基于 trim 值 |
| B2 | 大小写不敏感重名 | 同 resource `SSH`/`ssh`/`Ssh` | 后续均 409 `unique_conflict{field:"name"}`；首条 name 原样保留 |
| B3 | 非 ASCII 不折叠 | 中文名、含 `ß`/`İ` | 各自独立；仅 ASCII A–Z 折叠 |
| B4 | 内部普通空格不合并 | `"web 1"`、`"web  1"` | 201 且内部空格原样保留（不合并） |
| B5 | 空名/纯空白/控制字符 | `""`、`"   "`、含 `\x00`/`\x1f`/`\u200b` | 均 422；raw CHECK 拒 |
| B6 | name 长度 | 255 字符、256 字符 | 255 成功；256→422 / `varchar(255)` 拒 |
| B7 | 跨 Resource 同名 | 两 Resource 各建同名 | 均 201（唯一作用域=同 Resource） |
| B8 | 软删后复用 | 软删同名→重建同名 | 201，新 id；部分唯一仅约束未删 |
| B9 | 部分唯一并发双会话（真提交） | `committed_engine` 两独立连接对同 Resource 并发 POST 同 `(resource_id,name_key)` 名 | 部分唯一原子兜底，至多一方 201、另一方 409 `unique_conflict`；最终库中同 Resource 仅一未删行；断言最终持久化（非仅未抛异常） |
| B10 | resource 引用边界 | 省略/`null`/`""`；非 UUID；随机 UUID；软删 Resource | 均 422 field="resource"；无 Service 行 |
| B11 | resource 不可变 | PATCH 含 `resource`（异值）/`resource`（同值）/`resource_id`/`id`/`name_key` | 均 422；库值与 version 不变 |
| B12 | status 语义 | 省略 / `RUNNING` / `STOPPED` / `UNKNOWN` / `"running"` / `""` / `null` | 省略→UNKNOWN；三值保存；非法/null→422；raw CHECK 拒 |
| B13 | status 不由名称推导 | 创建 name=`slurmd`/`node_exporter`/`DCGM Exporter` 省略 status | 均 201 且 status=`UNKNOWN`；PATCH 只由显式值变更；静态核对无探测/自动转换 |
| B14 | description 语义 | 省略 / 显式 null / 给值 / PATCH 省略保持 / PATCH 显式 null 清空 | 符合 D01 §4；被拒请求不改库值 |
| B15 | metadata 形状 | 省略 / `{}` / 非 object（`[]`/`"x"`/`1`/`true`）/ 显式 null | 省略→`{}`；object 保存；非 object/null→422 field="metadata" |
| B16 | metadata 整值替换 | 原 `{"a":1,"b":2}`，PATCH `{"a":9}` | 200；结果为 `{"a":9}`（不保留 `b`）；UPDATE Audit after 反映整值 |
| B17 | Endpoint 桩：有引用禁删 | 注册返回固定 endpoint 引用的桩检查器；DELETE Service | 409 `reference_exists` + `references[{object_type:"service_endpoint",object_id,label}]`；`deleted_at` 仍 null；无级联 |
| B18 | Endpoint 桩默认空集 | 未注册真实检查器（F011 默认空集）；DELETE Service | 204 软删（空集不误报） |
| B19 | 删除不级联（结构层） | DELETE Service（无引用） | 204；仅 `deleted_at`/version/updated_at 变更；静态 + 桩核对 F011 不触碰 Endpoint/Resource |
| B20 | 恢复成功 | 软删→restore（name/Resource 均有效） | 200；`deleted_at=null`；不创建/恢复 Endpoint |
| B21 | 恢复 name 被复用 | 软删 A 后建同名 B；restore A | 409 `unique_conflict`；A 保持软删、B 不变 |
| B22 | 恢复依赖失效 | 软删 Service 后软删其 Resource；restore Service | 409 `dependency_deleted{conflicts:[{object_type:"resource",object_id}]}`；保持软删 |
| B23 | 恢复不级联 | restore 软删 Service | 200；不自动恢复其 Endpoint/Resource；仅自身 |
| B24 | 权限矩阵 | 逐端点 VIEWER/EDITOR/ADMIN/未认证 | 符合 §23；服务端强制 |
| B25 | 四 action Audit | CREATE/UPDATE/DELETE/RESTORE | 各一条 `object_type="service"`；UPDATE 含 before/after；白名单；`activity` 全角色 200 |
| B26 | 审计同事务回滚 | 注入 audit 失败（创建/更新/删除/恢复） | 业务与 audit 同回滚；最终持久化为旧值/无新行 |
| B27 | 软删默认隐藏 | 软删后 GET 详情/列表（默认） | 404/不在列表；`deleted=only`（ADMIN）可见 |
| B28 | 列表过滤/分页/排序 | `resource_id`/`status`/`q`/`deleted` 组合；分页边界；`sort`+`order` | 过滤正确；`q` 大小写不敏感子串；分页 `total/page/page_size` 正确；排序附 `id` 稳定；非法参数→422 |
| B29 | 部分唯一 raw 兜底 | raw 直插同 `(resource_id,name_key)` 未删；软删后同名 | 存活重名被 `uq_services_resource_id_name_key` 拒；软删后同名成功 |
| B30 | **部分唯一并发双会话（真提交）** | 两会话几乎同时 POST 同 Resource 同归一化名 | 至多一方 201、另一方 409 `unique_conflict`；最终库同 Resource 仅一未删行 |
| B31 | Resource←Service 引用保护端到端 | 有未删 Service 的 Resource `DELETE /api/v1/resources/{id}` | 409 `reference_exists`+`references` 含 `object_type:"service"`；Resource 未被软删 |
| B32 | 软删后可删 Resource | 软删 Service 后删 Resource | Resource 204；部分唯一释放 |
| B33 | **乐观锁并发（真提交）** | `committed_engine` 两连接同 version PATCH（及 DELETE/restore） | 一方 200 且 version+1；另一方 409 `VERSION_CONFLICT{current_version}`；最终值来自成功方 |
| B34 | **恢复 vs 并发重建竞争（真提交）** | 软删 A 后并发：会话 1 restore A、会话 2 建同名 B（同 Resource） | 至多一方存活；部分唯一闭环；无两未删同名；失败保持软删 |
| B35 | 校验顺序 | V24 各端点优先级 | 符合 Contract §6 |
| B36 | 响应契约/排序 | V23/V14 全参数组合 | 分页/排序/过滤正确；非 UUID/越界→422；`name_key` 不暴露 |
| B37 | 迁移 0011 up/down/up | `upgrade head`→`downgrade 0010`→`upgrade head`；`alembic heads` | 各步 0；单一 head `0011_services`；down 后表/约束/索引消失、0010 对象保留；re-up 一致 |
| B38 | 只读无副作用 | GET 列表/详情/activity | 无业务写、无 audit 行、version 不变 |
| B39 | FK RESTRICT 机制级 | raw 物理删除被未删 Service 引用的 Resource | 被 FK RESTRICT 拒（`confdeltype='r'`）；报告标注机制级 |
| B40 | PATCH exclude_unset / 显式 null / 不可变 | 省略保持；显式 null 仅清 description；必填/只读/未知→422 | 符合 D01 §4 与 Contract §2.4 |

并发说明：B9/B25/B26/B30/B33/B34 及任何「失败不留痕/并发」用例必须使用 `committed_engine`（真实连接、真实提交）或显式事务控制，断言**最终持久化状态 + 关系图**，不仅「未抛异常」。涉及部分唯一、CHECK、FK、迁移的断言必须在真实 PostgreSQL 执行（SQLite / Mock 不作约束/并发证据）。Endpoint 引用（A10/V10/B17/B18/B19）在 F011 阶段只能以桩检查器断言结构与调用链；**真实 Endpoint 引用的端到端结果不得由桩用例推断**。

---

## 3. 夹具 / 环境设计

**复用 F001–F010 `backend/tests/conftest.py`（不改其护栏语义）**：
- `test_database_url`：独立测试库 + 安全护栏（库名含 `test`、`TEST_DATABASE_URL != DATABASE_URL`）；未设置则 skip 并告警，不静默改 SQLite。
- `pg_engine`：会话级 `DROP SCHEMA public CASCADE` + `CREATE SCHEMA public` + `alembic upgrade head`（含 0011），会话结束清理。
- `db_session`：函数级外层事务 + savepoint，回滚不跨用例污染（单事务用例）。
- `committed_engine`：真实提交用例（B9/B25/B26/B30/B33/B34/B39 及持久断言），teardown `TRUNCATE` 清理（排除 `alembic_version`；确认 `services` 在动态清理清单内），新开连接断言最终持久化。
- `alembic_runner`：迁移 up/down/up 用例（V19/B37）。
- 认证/权限 fixture（`auth_session_factory`/`auth_app`/`api_client`/`bootstrap_admin`/`make_user`/`login`）：F011 权限/审计证据使用**真实业务端点** `/api/v1/services*` 与 `/api/v1/resources/{id}`。
- F003/F004/F008/F009/F010 helper：`_create_cluster`、`resource_factory`（裸金属/VM）、`role_client_factory`、raw `insert_*`、软删/恢复、乐观锁 `two-session`、raw SQL 约束断言模式、引用检查器桩模式直接复用。

**F011 新增测试侧夹具/断言（由 Tester 落地于测试侧，实现阶段由 Backend 提供接口）**：
- `service_factory`：创建 Service（`resource_id` + 可选 name/status/description/metadata），返回对象与 `version`；供 A1–A18、B1–B40 复用；失败路径覆盖只读字段被拒。
- `SERVICE_NAME_CASES`：表驱动名称数据（trim/大小写/中文/内部普通空格/非 ASCII/控制字符/长度 1/255/256），确保 API 与 DB 同一口径（V1–V3/V15/V16、B1–B8）。
- `SERVICE_STATUS_CASES`：status 省略/三合法值/大小写错/空/非法/`null`（V5、B12/B13）。
- `SERVICE_METADATA_CASES`：metadata 省略/object/非 object/`null`/整值替换（V8、B15/B16）。
- `assert_service_row(engine, id, expected)`：raw SQL 断言 `services` 各列值/`IS NULL`（含 `resource_id`/`name`/`name_key`/`status`/`description`/`metadata`/version/`deleted_at`）。
- `assert_partial_unique_service(engine, resource_id, name_key, deleted)`：raw 直插断言部分唯一仅在 `deleted_at IS NULL` 生效（A2/A3/A15/V2/V3/V15/B9/B29/B30）。
- `assert_service_name_key_matches(engine, ...)`：raw 断言 `name_key` 与 `translate(btrim(name))` 一致、非法 name_key 被 CHECK 拒（A1/A16/V-DB-1/V-DB-2）。
- `endpoint_reference_stub`（fixture）：经 `register_service_reference_checker` 注册返回固定引用集的检查器，teardown 恢复空集；供 A10/V10/V21/B17/B18（**标注桩证据边界**）。
- `assert_service_reference_protection(client, ...)`：端到端断言 Resource→Service 的 409 `reference_exists`+references（V22/B31/B32）。
- `assert_restore_recheck_service(...)`：恢复重检 name/Resource 有效、失败不覆盖、不自动恢复 Endpoint（A11/V11/B20–B23）。
- `assert_audit_same_txn(...)`：注入 audit 失败断言双回滚（V13/B26）。
- 真提交并发夹具（复用 F004/F009/F010 `committed_engine` 模式）：`two_session_partial_unique_create`、`two_session_restore_vs_recreate`、`two_session_version_conflict`，供 B9/B30/B33/B34。
- **F011 前端夹具**：复用 F005–F010 `smoke:client` 机制，新增 Services 列表/详情（resource/status/q 过滤、已删开关与 ADMIN 恢复）、创建/编辑表单（Resource 选择器创建后不可改、name、status、description、metadata）、422 点路径映射、409 冲突呈现（`unique_conflict`/`reference_exists`/`dependency_deleted`/`not_deleted`）与未知 reason 通用呈现，供 A12/A14/A18 前端机制级用例。

**环境**：Docker / Compose 可用（F001–F010 TE 已证）；真实 PG 经 Compose `db`（`postgres:16`）。btree_gist 由 0008 已启用、pg_trgm 由 0001 启用；0011 不重复启用。

### 3.1 当前环境可执行性评估

| 验证项 | 环境要求 | 当前评估 | 降级/替代 |
| --- | --- | --- | --- |
| V1–V18、V23–V27、B1–B8/B10–B16/B19–B29/B31–B32/B35–B40 | 真实 PG + 后端集成 | 经 Compose `db` 可满足（F001–F010 已证） | 无 PG 时 skip 并标 BLOCKED，**不得**用 SQLite 替代约束/并发证据 |
| V19/V20/V-DB-1…V-DB-9、B37（迁移 0011） | Alembic + 真实 PG | 可执行；依赖 0011 定稿 | 迁移未定稿则相关断言 BLOCKED，不降验收 |
| V10/V21/A10/B17/B18/B19 Endpoint 桩 | F011 已提供 `register_service_reference_checker` 接口 | architecture §6/§DR-146 已定义接口；F011 实现后可用测试侧假检查器 | 接口未落地则 BLOCKED，不降验收；真实 Endpoint 端到端**不可执行**（归 F012） |
| V22/B31/B32 Resource←Service 引用保护 | F011 注册检查器 | architecture §6/DR-147 已定义；F011 实现后可用 | 未落地则 BLOCKED |
| B9/B30/B33/B34 并发 | 真实并发提交 fixture | 可执行（复用 `committed_engine`） | 无 PG 时 BLOCKED；不得以顺序调用替代并发证据 |
| 前端机制级 / 真实 API 集成 | Node 22 + 构建；Compose 入口 | 可执行 | 真实浏览器 DOM 渲染非必要判据；镜像/端口问题记 BLOCKED |
| T23 真实 Endpoint 端到端 | F012 交付 | **不可执行** | 标 `NOT TESTED / 归 F012`；F011 仅验证契约/挂钩/桩 |
| T21/T24/T25/T26/T37/T40/T41 完整回归与 §32 上线验收 | F016 交付 | **不可执行** | F011 仅承载 Service 子集；不声明整条通过 |

---

## 4. 可验证性检查

| 项 | 判定 | 说明 |
| --- | --- | --- |
| A1/A2/A3 name 规范/唯一/复用/恢复 | **可验证（API + DB + 真提交）** | V1–V3/V15/V16 + V-DB-1/2/3 + B1–B9/B29/B30/B34；部分唯一 + 应用检查双路径，真实 PG |
| A4/A9 resource 引用与不可变 | **可验证（API + DB）** | V4/V9 + V-DB-4/V-DB-7 + B10/B11；应用 422 + FK |
| A5/A6 status 默认/人工维护 | **可验证（API + DB + 静态）** | V5/V6 + V-DB-5 + B12/B13；默认值落库 + 静态核对无推断 |
| A7 description | **可验证（API）** | V7 + B14；D01 §4 省略语义 |
| A8 metadata 整值替换 | **可验证（API + DB）** | V8 + V-DB-6 + B15/B16；JSONB + jsonb_typeof CHECK |
| A10 Endpoint 引用 | **桩可验证契约/挂钩；端到端归 F012** | V10/V21 + B17/B18/B19 |
| A11 恢复重检 | **可验证（端到端 + 真提交）** | V11 + B20–B23/B34；失败不覆盖 |
| A12 权限矩阵 | **可验证（端到端 + 静态）** | V12 + B24；真实端点 + 服务端强制 |
| A13 审计 | **可验证（端到端 + 真提交）** | V13 + B25/B26；四 action + 同事务回滚 |
| A14 列表 | **可验证（端到端）** | V14 + B28/B36；软删/过滤/分页/排序 |
| A15 DB 兜底 | **可验证（DB 机制级）** | V15 + V-DB-3 + B9/B29/B30；真实 PG raw 直插 |
| A16 归一化一致 | **可验证（F011 侧）** | V16 + V-DB-2/3；API 与 DB 口径一致 + 软删不参与；F014/F013 执行各自 |
| A17 乐观锁 | **可验证（真提交）** | V17 + B33；两连接同 version |
| A18 归属/查询数据 | **F011 侧可验证；搜索/聚合归 F013** | V18 + B28；元组数据可取；§17/§19/§20 归 F013 |
| V19/V20 迁移/目录 | **可验证（DB）** | 真实 PG up/down/up + 单一 head + 目录断言 |
| V21/V22 引用检查器 | **可验证（桩 + 端到端）** | V21 桩默认空集；V22 Resource←Service 真实端到端 |
| V26 FK 物理语义 | **机制级** | API 无物理删除路径；raw SQL 验证 `confdeltype`，报告须显式标注 |

口径明确记录：**A10/V10/V21/B17/B18 为 Endpoint 桩的结构与引用拦截断言**，真实 Endpoint 端到端（T23）归 F012；**A16/V16 为 F011 侧归一化一致**，F014/F013 执行各自一致性；**T21/T24/T25/T26/T37/T40/T41 的 Service 子集**在本 Feature 验证；**T23 完整端到端不在本 Feature**，不得以 F011 局部 PASS 拼成整条通过。

---

## 5. 范围与不适用项声明

- **ServiceEndpoint 本体与监听唯一性（§16，F012）**：F011 不实现；仅提供 Service 父对象、`register_service_reference_checker` 引用检查扩展点（默认空集）；**含真实 Endpoint 的端到端（T23）归 F012**。
- **Endpoint/IP 关系、IP 解绑/转移/释放的 Endpoint 保护（§13.3/§16，F010/F012）**：归 F010/F012；F011 不涉及。
- **§17 全局搜索 / §19 Cluster Detail Services / §20 Dashboard / 列表聚合（F013）**：F011 仅承载 `/api/v1/services` 列表/过滤/排序（A14）与字段口径；§17/§19/§20 归 F013。
- **CSV / Excel 导入（§24，F014）**：Service 导入模板与执行归 F014；F011 仅提供字段口径供复用（A16 子集）。
- **完整 Audit 查询页（§22，F015）**：F011 仅验证四 action 的资源级 Activity 快照。
- **Slurm 自动部署、节点加入、状态同步、实时进程探测、Prometheus/Grafana 监控、自动状态转换**：明确排除。
- **service_type 字典/分类、端口/协议/监听地址字段、Service 与 IP 的直接关系、通配/VIP/Unix Socket**：明确排除。
- **Service 不落 IP/端口/协议/监听地址/cluster 直字段/实时探测状态/自动部署标记**：明确排除；不由名称推断状态或行为。
- **完整 T21/T23/T24/T25/T26/T37/T40/T41 回归与 §32 上线验收**：F011 仅承载 Service 子集；跨 Feature 完整回归归 F016。**不声明上述条款完整通过**。
- **真实浏览器 DOM 渲染**：非 F011 必要判据，前端以构建 + client 机制级为准。

---

## 6. 风险与待核对项总结

| 项 | 评估 | 处理 |
| --- | --- | --- |
| V1–V18、V23–V27、B1–B8/B10–B16/B19–B29/B31–B32/B35–B40（真实 PG + 后端集成） | Docker/Compose 可用（F001–F010 已证）；**可执行** | 无 PG 时相关项 BLOCKED，不降验收 |
| V19/V20/V-DB-1…V-DB-9 迁移 0011 + 部分唯一/CHECK | DATABASE Gate 未定稿（`f011-service.md` 未产出） | 定稿后由 TD-2 核对；未定稿则相关断言 BLOCKED |
| A10 引用检查与挂钩 | F011 仅到达桩；真实 Endpoint 在 F012 | F011 验契约/挂钩/桩拦截；端到端明确标注 `NOT TESTED / 归 F012`，不拼成 T23 通过 |
| A16 归一化一致 | F014/F013 各自执行一致性 | F011 验应用/DB 口径一致 + 软删不参与 |
| A18 搜索/聚合 | F013 | F011 验归属数据与 §18 消费；§17/§19/§20 标 `NOT TESTED / 归 F013` |
| B9/B30/B33/B34 并发 | 需真实并发提交 fixture | 复用 `committed_engine`；断言最终关系图 |
| name_key CHECK 口径/部分唯一形态/索引集合/迁移 0011 | DATABASE 未定稿 | TD-2 依 DATABASE 定稿核对 V-DB-1…9 |
| `reference_exists` details 形状 / 列表参数 / 校验顺序 / 审计白名单 | Contract 草案 v0 未定稿 | TD-2 依 Contract v1 固定 V10/V14/V23/V24/V13 |
| D01 v10 §5.10/§5.2/§5 表未签核 | name 1–255、仅 ASCII 折叠、status 默认、metadata 归属、resource 不可变 | TD-2 依 D01 v10 核对 |
| I-2 resource 可变性（PROPOSED 不可改） | product OPEN，architecture DR-144 采纳不可改 | TD-1 按不可改设判据；若 CONTRACT 改判可变，须重检目标 Resource 并调整 V9/B11（回归 TD） |

---

## 7. 独立性与执行口径（TEST 阶段适用）

- Backend pytest 由 Tester 独立重跑，不复用实现者数字。
- 迁移、部分唯一、CHECK、FK、JSONB 约束由 Tester 在独立库（库名含 `test`）以 Alembic / raw SQL 直接执行；不连接生产或未知数据库。
- 接口验证响应内容、类型、业务边界、非法输入与错误语义；只读功能（GET 列表/详情/activity）确认无业务写副作用。
- 引用冲突：F011 阶段以测试侧注册的假 `register_service_reference_checker` 断言结构与调用链；**明确标注桩证据边界，真实 Endpoint 端到端执行归 F012**；Resource←Service 引用保护（V22/B31）为 F011 真实端到端。
- 前端验证状态、交互、错误与未知值处理；已批准范围要求真实前后端集成时经入口 Nginx 验证真实 API，不以 Mock 代替。
- 修复后按影响重测；首次设计检查与最终验收分别记录版本与证据。

---

## 8. OPEN 复核项（TD-1 提出，待 DATABASE / CONTRACT / D01 v10 定稿后由 TD-2 关闭）

> TD-1 `READY` 表示方案可验证，下列假设均未经逐项核对；**READY 不代表测试已执行、不批准实现或合并**。定稿后由 TD-2 关闭并固定执行判据。

### 8.1 待 DATABASE 定稿（`docs/database/f011-service.md`，未产出）

| # | TD-1 待复核假设 | 影响验证项 | Owner |
| --- | --- | --- | --- |
| OPEN-1 | 表名 `services`、列名/类型（`id uuid pk`、`resource_id uuid NOT NULL`、`name varchar(255) NOT NULL`、`name_key varchar(255) NOT NULL`、`status varchar(16) NOT NULL DEFAULT 'UNKNOWN'`、`description text NULL`、`metadata jsonb NOT NULL DEFAULT '{}'`、`version int NOT NULL DEFAULT 1`、`created_at/updated_at timestamptz NOT NULL now()`、`deleted_at timestamptz NULL`） | V1–V27、B1–B40 | Database |
| OPEN-2 | 约束/索引名：`pk_services`、`fk_services_resource_id_resources`、`uq_services_resource_id_name_key`、`ck_services_{name_not_blank,name_trimmed,name_no_control,name_length,name_key_matches,status,metadata_object,version}`、`ix_services_{resource_id,status,deleted_at}` | V2/V5/V8/V15/V20、B2/B5/B6/B12/B15/B29/B30 | Database |
| OPEN-3 | **name_key CHECK 口径** = `ASCII_lower(btrim(name))`（DB `translate`，禁 `lower()`）；name 长度 1–255；是否含 ASCII backstop（禁 Cc/Cf 的 DB 表达） | V1/V2/V15/V16、V-DB-1/V-DB-2、B1–B6/B29 | Database / D01 v10 |
| OPEN-4 | **部分唯一精确形态** `UNIQUE(resource_id,name_key) WHERE deleted_at IS NULL`；软删释放、恢复重检、跨 Resource 允许 | V2/V3/V15、V-DB-3/V-DB-8、B7/B8/B9/B21/B29/B30/B34 | Database |
| OPEN-5 | `status` NOT NULL DEFAULT 'UNKNOWN' + CHECK∈3 值 | V5、V-DB-5、B12 | Database |
| OPEN-6 | `metadata` JSONB NOT NULL DEFAULT '{}' + CHECK `jsonb_typeof(metadata)='object'` | V8、V-DB-6、B15/B16 | Database |
| OPEN-7 | `resource_id` FK `ON DELETE RESTRICT`；无不可变触发器（应用保证 resource 不可改）或等价机制 | V9/V22/V26、V-DB-4/V-DB-7、B11/B31/B39 | Database |
| OPEN-8 | `version` default 1、CHECK ≥1；时间戳列；`deleted_at`；软删/恢复与部分唯一交互 | V17、V-DB-7/V-DB-8、B33 | Database |
| OPEN-9 | 索引集合（不建 pg_trgm/GIN；不重复启用扩展）；引用检查器查询索引支撑 | V20、B31 | Database / Backend |
| OPEN-10 | 迁移 `0011_services`（`down_revision=0010_ip_addresses`）单 head、全表新建无回填、对称可逆 | V19、V-DB-9、B37 | Database |
| OPEN-11 | Resource←未删 Service 引用检查的 DB 落点（FK RESTRICT 物理兜底 + 应用检查器，与 F006/F007 同机制） | V22/V26、B31/B32/B39 | Database / Backend |

### 8.2 待 CONTRACT 定稿（`docs/api/F011.md` v0）

| # | TD-1 待复核假设 | 影响验证项 | Owner |
| --- | --- | --- | --- |
| OPEN-12 | 错误码复用集登记 F002 §1.2/§1.2.1：`unique_conflict{field:"name"}`、`not_deleted`、`dependency_deleted{conflicts:[{object_type:"resource",object_id}]}`、`reference_exists{references:[{object_type:"service_endpoint",object_id,label}]}`；F011 **不新增** code/reason | A2/A3/A4/A10/A11/V2/V3/V4/V10/V11、B2/B21/B22 | Contract |
| OPEN-13 | `reference_exists` 的 details 形状与 object_type（Service←ServiceEndpoint 为 `"service_endpoint"`；Resource←Service 为 `"service"`） | A10/V10/V22、B17/B31 | Contract |
| OPEN-14 | 校验顺序与错误码层级（POST/PATCH/DELETE/restore；Contract §6） | V24、B35 | Contract |
| OPEN-15 | 列表 Query 参数集（`resource_id/status/q/deleted/page/page_size/sort/order`）、`q` 口径（name 大小写不敏感子串，trim 后空视为未提供）、`deleted∈{exclude,include,only}`、`sort∈{name,status,created_at,updated_at}`、`order∈{asc,desc}`、`sort=name` 按 name_key | A14/V14、B28/B36 | Contract |
| OPEN-16 | D01 v10 §5.10 签核：name 1–255 仅 ASCII 折叠、允许内部普通空格不合并；status 默认 UNKNOWN；description 无上限；metadata Service 自有、object、整值替换；resource 创建必填不可改；§5.2 追加 Service name 255；§5 表 Service 单列一行 | V1/V5/V7/V8/V9/V16、B1–B16 | Contract / D01 v10 |
| OPEN-17 | 跨 Feature 协议：F011 提供 `register_service_reference_checker` 默认空集；F012 必须注册真实 Endpoint 检查器；F011 注册 Resource←Service 引用检查器；T23 端到端留 F012 | A10/A11/V10/V21/V22、B17/B18/B31 | Architect / 跨 Feature |
| OPEN-18 | 权限映射（增改=WRITE；删除=DELETE_OBJECT；查看已删=VIEW_DELETED；恢复=RESTORE；Activity=VIEW_ACTIVITY 全角色）与审计白名单 `{resource_id,name,status,description,metadata}`、`object_type="service"` | A12/A13/V12/V13、B24/B25/B26 | Contract |
| OPEN-19 | 响应契约：`resource{id,hostname}` 嵌套；`name_key`/`resource_id` 原始列不暴露；列表 `{items,page,page_size,total}`；`name_key` 不暴露；软删可见性语义 | A18/V18/V23、B27/B36 | Contract |
| OPEN-20 | I-2 resource 可变性：CONTRACT 是否固定「创建后不可改」（PATCH 出现 `resource`/`resource_id` 含同值→422）；若改判可变须新增目标 Resource 重检 | A9/V9、B11 | Product / Contract |

TD-1 结论：**`TEST DESIGN READY`** —— A1–A18 已映射到可观察判据，边界/并发场景（含名称归一化/部分唯一双会话 B9/B30、resource 引用与不可变 V4/V9/B10/B11、status 默认与非法 V5/V-DB-5/B12/B13、metadata 整值替换 V8/B15/B16、软删/恢复重检 V3/V11/B20–B23/B34、Resource←Service 引用保护 V22/B31/B32、乐观锁 V17/B33、列表过滤 V14/B28）可执行，夹具与可验证性已与 architecture §1/§7/§9 草案建立对应；A10 在 F011 以 Endpoint 桩断言契约与挂钩，T23 真实 Endpoint 端到端明确留待 F012；A16/A18 的搜索/导入/聚合部分明确留待 F013/F014。**DATABASE / CONTRACT / D01 v10 尚未定稿，以上 OPEN 未经逐项核对；READY 不等于测试通过，不批准实现或合并。** 定稿后由 TD-2 关闭 §8 并固定执行判据。

---

## 9. 版本记录（续）

| 版本 | 日期 | 变更 |
| --- | --- | --- |
| TD-1 | 2026-10-09 | 初版 Test Design（见 §Test Design）。 |
| TD-2 | 2026-10-09 | 依 Database v1、Contract v1、D01 v10 逐项关闭 §8 OPEN-1–20，并入 Architect 定稿的判据调整（见 §10）。 |
| TE-1 | 2026-10-09 | 首次独立执行（基线 HEAD=4f9caa4）：A1–A18、V-DB-112–125、B1–B40 结果与证据（见 §11）。结论 `READY FOR REVIEW`。 |

---

## 10. Test Design 复核（TD-2）

- **版本**：TD-2
- **日期**：2026-10-09
- **角色**：Tester（TEST_DESIGN 模式复核）
- **结论**：`TEST DESIGN READY`（TD-2；§8 OPEN-1–20 全部关闭，未验证项保持明确标注）
- **复核依据（已定稿）**：
  - `docs/database/f011-service.md` v1（Database 2026-10-09，DB-D128–DB-D141）
  - `docs/api/F011.md` v1（Contract READY，Architect 2026-10-09）
  - `docs/architecture/d01-conventions.md` v10（§5 表、§5.2、§5.10）
  - `docs/features/F011/architecture.md`、`docs/features/F011/product.md`（A1–A18）
- **状态属性**：TD-2 `READY` 仅表示 A1–A18 判据已与定稿设计逐项对齐、可执行；不代表测试已运行、不批准实现或合并。测试执行见 §11（TE-1）。

### 10.1 §8 OPEN-1–20 关闭结论

| # | 定稿结论（判据固定） | 关闭依据 |
| --- | --- | --- |
| OPEN-1 | 表 `services`；列类型/必填/默认与实现一致（`id uuid pk gen_random_uuid()`、`resource_id uuid NOT NULL`、`name/name_key varchar(255) NOT NULL`、`status varchar(16) NOT NULL DEFAULT 'UNKNOWN'`、`description text NULL`、`metadata jsonb NOT NULL DEFAULT '{}'`、`version int NOT NULL DEFAULT 1`、`created_at/updated_at timestamptz NOT NULL now()`、`deleted_at timestamptz NULL`） | DB v1 §2；V-DB-113 |
| OPEN-2 | 约束/索引名：`pk_services`、`fk_services_resource_id_resources`、`uq_services_resource_id_name_key`、`ck_services_{name_not_blank,name_trimmed,name_no_control,name_length,name_key_matches,status,metadata_object,version}`、`ix_services_{resource_id,status,deleted_at}` | DB v1 §2；V-DB-112/122；实测目录一致 |
| OPEN-3 | `name_key = translate(btrim(name))`（禁 `lower()`）；name 长度 1–255；**DB 直插负例控制字符范围收敛为 ASCII `[[:cntrl:]]`**；Unicode Cc/Cf 拒绝改在 API 级断言 | DB v1 §2/§3.1；D01 v10 §5.10；V-DB-114/115 |
| OPEN-4 | 部分唯一精确形态 `UNIQUE(resource_id,name_key) WHERE deleted_at IS NULL`；软删释放、恢复重检、跨 Resource 允许 | DB v1 §2/§3.1；V-DB-116/123 |
| OPEN-5 | `status` NOT NULL DEFAULT 'UNKNOWN' + `CHECK IN ('RUNNING','STOPPED','UNKNOWN')` | DB v1 §2/§3.2；V-DB-117 |
| OPEN-6 | `metadata` JSONB NOT NULL DEFAULT `'{}'` + `CHECK jsonb_typeof='object'` | DB v1 §2/§3.3；V-DB-118 |
| OPEN-7 | `resource_id` FK `ON DELETE RESTRICT`；**`resource_id` 不可变仅为应用 422；DB 层允许 UPDATE（无不可变触发器）** | DB v1 §3.4/DB-D136；V-DB-120/121 |
| OPEN-8 | `version` DEFAULT 1、CHECK ≥1；时间戳列；`deleted_at` 可空；软删/恢复与部分唯一交互 | DB v1 §2；V-DB-119/123 |
| OPEN-9 | 索引集合=部分唯一 + 3 普通 btree；不建 pg_trgm/GIN、不建 name/name_key 单列 B-tree；不重复启用扩展 | DB v1 §3.5/DB-D137；V-DB-122/125 |
| OPEN-10 | 迁移 `0011_services`（`down_revision=0010_ip_addresses`）单 head、全表新建无回填、对称可逆 | DB v1 §4；V-DB-112/125 |
| OPEN-11 | Resource←未删 Service 引用检查：DB 仅 FK RESTRICT（物理）兜底，应用注册检查器返回 409 `reference_exists` | DB v1 §3.6/DB-D139；V22/V-DB-120 |
| OPEN-12 | 错误码复用集：`unique_conflict{field:"name"}`、`not_deleted`、`dependency_deleted{conflicts:[{object_type:"resource"}]}`、`reference_exists`；F011 不新增 code/reason | Contract v1 §1.2 |
| OPEN-13 | **`reference_exists` object_type 固化：Service DELETE 为 `service_endpoint`；Resource DELETE 为 `service`** | Contract v1 §1.2/§6.5/§7；V10/V22 |
| OPEN-14 | 校验顺序：**POST body（含 status/metadata）→resource→name 规范→name 唯一**；PATCH 可见性→version→name 归一化→name 唯一；DELETE 对象→version→引用→软删；**restore not_deleted→version→name 唯一→Resource 依赖** | Contract v1 §6；V24 |
| OPEN-15 | 列表 Query=`resource_id/status/q/deleted/page/page_size/sort/order`；`q`=name 大小写不敏感子串（trim 后空视为未提供）；`sort=name` 按 name_key；**不新增 cluster 过滤参数** | Contract v1 §4（DR-153）；V14 |
| OPEN-16 | D01 v10 §5.10 签核：name 1–255 仅 ASCII 折叠、内部普通空格不合并；status 默认 UNKNOWN；description 无上限；metadata Service 自有 object 整值替换；resource 创建必填不可改；§5.2 已追加 Service name 255；§5 表已拆 Service 单行 | D01 v10 §5/§5.2/§5.10 |
| OPEN-17 | 跨 Feature 协议：F011 提供 `register_service_reference_checker`（默认空集）；F012 必须注册真实 Endpoint 检查器；F011 注册 Resource←Service 检查器；T23 端到端留 F012 | Contract v1 §9/DR-146；V21/V22 |
| OPEN-18 | 权限：READ/WRITE/DELETE_OBJECT/VIEW_DELETED/RESTORE/VIEW_ACTIVITY（全角色）；审计白名单 `{resource_id,name,status,description,metadata}`、`object_type="service"` | Contract v1 §1.3/§8；V12/V13 |
| OPEN-19 | 响应契约：`resource{id,hostname}` 嵌套；`name_key`/`resource_id` 原始列不暴露；列表 `{items,page,page_size,total}` | Contract v1 §3/§4；V23 |
| OPEN-20 | I-2 关闭：CONTRACT 固定「创建后不可改」（PATCH 出现 `resource`/`resource_id` 含同值→422），不新增目标 Resource 重检 | Contract v1 §2.2/§2.4；V9/V-DB-121 |

### 10.2 对 TD-1 判据的调整（并入 Architect 定稿）

1. **控制字符负例分层**：DB 直插负例仅覆盖 ASCII `[[:cntrl:]]`（`\x01`/`\t`）；Unicode Cc/Cf（`\x00`、`\u200b`、`\ufeff`、`\u00ad`）在 API 级断言 422。DB 接受 Unicode Cf 属已记录差异（DB v1 §9 LOW）。
2. **resource 不可变分层**：应用 PATCH 含 `resource`/`resource_id`/`id`/`name_key`→422；DB 无不可变触发器，`UPDATE services SET resource_id=...` 允许（机制级断言无业务触发器）。
3. **列表参数**：无 cluster 过滤参数；F013 聚合与 §17 全局搜索记 `NOT TESTED / 归 F013`。
4. **restore 优先级**：`not_deleted → version → name 唯一 → Resource 依赖`（name 唯一先于 Resource 依赖）。
5. **POST 顺序**：body（含 status/metadata）→resource→name 规范→name 唯一。
6. **`reference_exists` object_type**：Service DELETE=`service_endpoint`；Resource DELETE=`service`。
7. **V-DB 表名/约束名/索引/FK/迁移** 以 DB v1 为准。

---

## 11. TEST 执行（TE-1）

- **版本**：TE-1
- **日期**：2026-10-09
- **角色**：Tester（TEST 模式）
- **执行基线**：Git HEAD `4f9caa4`，分支 `feature/F011-service-registry`
- **依据**：`docs/database/f011-service.md` v1、`docs/api/F011.md` v1、`docs/architecture/d01-conventions.md` v10、`docs/features/F011/{product,architecture,implementation}.md`、TD-2（§10）
- **结论**：`READY FOR REVIEW`（F011 独立范围全部通过；无必须修复的实现缺陷；T23 真实 Endpoint 端到端与 F013/F014/F015/F016 范围明确 `NOT TESTED`）

### 11.1 独立性声明

- Backend pytest 由 Tester 在本容器内独立重跑，不复用实现报告数字；实现报告称 382 passed/1 skipped（F011 36），本次独立复跑一致。
- 追加独立测试 `backend/tests/integration/test_services_tester.py`（12 项，Tester 编写），定向覆盖实现套件未直接断言的验收点：B26 审计同事务回滚（CREATE/UPDATE/DELETE/RESTORE）、B33 两真实会话乐观锁、B34 恢复 vs 并发重建、A1 的 Unicode Cc/Cf（API 级）与 DB ASCII backstop 分层、A16 应用/DB `name_key` 一致、A12 未认证 401、A14 `sort=name` 按 `name_key`、A13 UPDATE 审计 before/after 内容、V27 只读无副作用、A10 公共 `register_service_reference_checker` 挂钩。
- 迁移 up/down/up、约束/索引目录、并发部分唯一、FK RESTRICT 在真实 PostgreSQL（独立库 `f011_te1` 与测试库 `csm_test`）执行；未连接生产或未知数据库（`f011_te1` 为本次新建的一次性验证库，用后删除）。

### 11.2 环境

| 项 | 值 |
| --- | --- |
| PostgreSQL | 容器 `f002test-db`（`postgres:16`），网络 `f002test-net`；测试库 `csm_test`（csm/change-me） |
| 后端镜像 | `csm-f007-test`，源码挂载 `-v $PWD/backend:/app`；`TEST_DATABASE_URL=postgresql+psycopg://csm:change-me@f002test-db:5432/csm_test` |
| 独立迁移验证库 | `f011_te1`（`f002test-db` 上 `CREATE DATABASE`，同一 `csm-f007-test` 镜像运行 alembic/raw SQL，验证后 `DROP DATABASE`） |
| 前端 | Node v22.23.2 / npm 12.0.2；`frontend/node_modules` 已存在 |
| 安全护栏 | 测试库名含 `test`；`TEST_DATABASE_URL != DATABASE_URL`（conftest DB-D10）；未使用 SQLite/Mock 作约束/并发证据 |

### 11.3 执行命令与输出

| # | 命令（要点） | 输出 |
| --- | --- | --- |
| E1 | 全量后端 `pytest tests -q`（实现基线复跑） | `382 passed, 1 skipped`（skip=`test_migrations.py` V3b superuser 环境性） |
| E2 | F011 专属 `pytest tests/integration/test_services.py tests/integration/test_service_constraints.py -v` | `36 passed`（23+13） |
| E3 | Tester 独立套件 `pytest tests/integration/test_services_tester.py -q` | `12 passed` |
| E4 | 全量后端（含 Tester 12 项）`pytest tests -q` | `394 passed, 1 skipped`（一次运行出现 2 个非 F011 失败，见 Defect F011-TE1-03） |
| E5 | 独立库迁移：`alembic upgrade head` → `alembic heads` → `alembic downgrade 0010_ip_addresses` → `alembic upgrade head` | 单一 head `0011_services`；up 后 `services` 存在、`alembic_version=0011_services`；down 后 `services` 消失、`ip_addresses` 保留、版本 `0010_ip_addresses`；re-up 后 `services` 恢复、版本 `0011_services`；扩展 `btree_gist`/`pg_trgm` 前后一致 |
| E6 | 独立库目录查询 `pg_constraint`/`pg_indexes`/`pg_extension` | 约束 10 个=PK+FK+8 CHECK；索引 `uq_services_resource_id_name_key`（`WHERE deleted_at IS NULL`）+`ix_services_{resource_id,status,deleted_at}`；无 GIN、无 name/name_key 单列 B-tree |
| E7 | 前端 `npm run typecheck && npm run build && npm run smoke:client` | typecheck 通过；build 70 modules 成功；`187 passed, 0 failed`（F011 新增 27） |
| E8 | `python3 scripts/validate_project_state.py --feature F011` | `PROJECT STATE VALID`（结构/Gate/文件） |
| E9 | 静态核对：Service 无 Slurm/监控/探测集成；无 cluster 过滤参数；`name_key` 不出现在 schema；无 Endpoint 级联删除路径 | 通过 |

### 11.4 验收映射 A1–A18

| 验收 | 结果 | 证据（验证项 / 测试） |
| --- | --- | --- |
| A1 名称 trim/空/控制字符拒；中文与内部空格保留不合并 | PASS | V1/V-DB-1/V-DB-2；`test_name_trim_and_control_characters`、`test_name_boundaries_and_name_key`、`test_name_length_and_internal_spaces_api`、`test_unicode_control_and_format_rejected_api`、`test_db_name_control_backstop_is_ascii_only` |
| A2 同 Resource 大小写不敏感重名拒；跨 Resource 允许 | PASS | V2/V-DB-3；`test_same_resource_name_unique_case_insensitive`、`test_partial_unique_name` |
| A3 软删后同名可重建；存活同名拒；恢复不覆盖新对象 | PASS | V3/V-DB-3/V-DB-8；`test_soft_delete_reuse_and_restore_conflict`、`test_restore_recheck_partial_unique` |
| A4 resource 缺失/不存在/软删→422 | PASS | V4/V-DB-4；`test_resource_required_and_must_exist` |
| A5 status 省略→UNKNOWN；三值保存；非法/null→422 | PASS | V5/V-DB-5；`test_status_default_and_values`、`test_status_check_and_default` |
| A6 status 人工维护、不由名称推导 | PASS | V6 + 静态 E9；`test_status_default_and_values`（`slurmd`→UNKNOWN） |
| A7 description 可空/清空/保持 | PASS | V7；`test_description_nullable_and_preserved` |
| A8 metadata 默认 {}/整值替换/非法拒 | PASS | V8/V-DB-6；`test_metadata_whole_replacement`、`test_metadata_object_check`、`test_update_audit_snapshot_content` |
| A9 resource 必填且创建后不可改（应用 422） | PASS | V9/V-DB-4/V-DB-7；`test_resource_immutable`、`test_resource_id_has_no_immutability_trigger` |
| A10 未删 Endpoint 引用时删除被拒返回 references；不级联；无引用可删 | PASS（桩）/ NOT TESTED（F012 端到端） | V10/V21；`test_delete_default_empty_reference_set`、`test_delete_reference_checker_stub_blocks`、`test_public_service_reference_register_hook`；真实 Endpoint 归 F012（T23） |
| A11 恢复重检名称唯一与 Resource 有效性；失败不覆盖；不级联 | PASS | V11；`test_soft_delete_reuse_and_restore_conflict`、`test_restore_dependency_resource_deleted`、`test_restore_not_deleted`、`test_restore_success_and_audit`、`test_restore_vs_recreate_concurrency` |
| A12 权限矩阵（VIEWER/EDITOR/ADMIN/未认证，服务端） | PASS | V12；`test_permissions`、`test_view_deleted_and_detail`、`test_unauthenticated_401` |
| A13 四 action 审计且同事务；Activity 全角色；白名单 | PASS | V13；`test_activity_trail`、`test_audit_whitelist_row`、`test_update_audit_snapshot_content`、`test_audit_failure_rolls_back_all_service_writes` |
| A14 默认隐藏软删；过滤/模糊/分页/排序基线 | PASS | V14；`test_list_filters_and_pagination`、`test_sort_name_uses_name_key` |
| A15 DB 部分唯一兜底 | PASS | V15/V-DB-3；`test_table_catalogue_columns_constraints_indexes`、`test_partial_unique_name`、`test_concurrent_same_name_insert` |
| A16 归一化在 API/DB 一致；仅未删参与唯一 | PASS（F011 侧）/ NOT TESTED（F014/F013） | V16/V-DB-2/V-DB-3；`test_name_key_app_db_consistency_api_to_db`、`test_partial_unique_name` |
| A17 乐观锁过期编辑 409，无静默覆盖 | PASS | V17/V-DB-119；`test_optimistic_lock`、`test_optimistic_lock_two_sessions` |
| A18 Resource 间接归属；Resource Detail 数据可取 | PASS（F011 侧）/ NOT TESTED（F013 搜索/聚合） | V18；`test_nested_resource_and_query`、`test_list_filters_and_pagination`；§17/§19/§20 归 F013 |

### 11.5 数据库机制级验证 V-DB-112–125

| 编号 | 结果 | 证据 |
| --- | --- | --- |
| V-DB-112 迁移 up/down/up、单 head、对象齐全、无回填、扩展无新增 | PASS | E5/E6；`test_migration_up_down_up_and_single_head`、`test_table_catalogue_columns_constraints_indexes` |
| V-DB-113 默认/NOT NULL | PASS | `test_defaults_and_not_null` |
| V-DB-114 name 边界 | PASS | `test_name_boundaries_and_name_key`、`test_name_length_and_internal_spaces_api` |
| V-DB-115 name_key CHECK（translate 口径） | PASS | `test_name_boundaries_and_name_key`、`test_name_key_app_db_consistency_api_to_db` |
| V-DB-116 部分唯一（重名/跨 Resource/软删释放/恢复冲突/并发） | PASS | `test_partial_unique_name`、`test_concurrent_same_name_insert`、E6 |
| V-DB-117 status 默认/取值 | PASS | `test_status_check_and_default` |
| V-DB-118 metadata object/默认/整值替换 | PASS | `test_metadata_object_check` |
| V-DB-119 version 默认≥1、乐观锁双会话 | PASS | `test_defaults_and_not_null`、`test_optimistic_lock_two_sessions` |
| V-DB-120 FK RESTRICT、软删保留行 | PASS | `test_fk_restrict_and_soft_delete_retention` |
| V-DB-121 resource 不可改：无触发器、DB 允许 UPDATE | PASS | `test_resource_id_has_no_immutability_trigger` |
| V-DB-122 索引目录（部分唯一谓词、无 GIN/无单列 B-tree） | PASS | `test_table_catalogue_columns_constraints_indexes`、E6 |
| V-DB-123 恢复重检 DB 层（部分唯一拒） | PASS | `test_restore_recheck_partial_unique` |
| V-DB-124 Service 删除引用集由应用承担（DB 无约束） | PASS | `test_service_delete_reference_set_has_no_db_constraint` |
| V-DB-125 迁移边界（无 CREATE/DROP EXTENSION） | PASS | `test_migration_0011_has_no_create_extension`、E5 |

### 11.6 边界与并发场景 B1–B40

| 编号 | 结果 | 证据 |
| --- | --- | --- |
| B1 | PASS | `test_name_trim_and_control_characters` |
| B2 | PASS | `test_same_resource_name_unique_case_insensitive` |
| B3 | PASS | `test_same_resource_name_unique_case_insensitive`（ß）、`test_name_key_app_db_consistency_api_to_db`（İ） |
| B4 | PASS | `test_name_length_and_internal_spaces_api`（`web  1`） |
| B5 | PASS | `test_unicode_control_and_format_rejected_api`、`test_db_name_control_backstop_is_ascii_only` |
| B6 | PASS | `test_name_length_and_internal_spaces_api`、`test_name_boundaries_and_name_key` |
| B7 | PASS | `test_same_resource_name_unique_case_insensitive` |
| B8 | PASS | `test_soft_delete_reuse_and_restore_conflict` |
| B9 | PASS | `test_concurrent_same_name_insert`（raw 双会话真提交，断言最终唯一行） |
| B10 | PASS | `test_resource_required_and_must_exist` |
| B11 | PASS | `test_resource_immutable` |
| B12 | PASS | `test_status_default_and_values`、`test_status_check_and_default` |
| B13 | PASS | `test_status_default_and_values` + 静态 E9 |
| B14 | PASS | `test_description_nullable_and_preserved` |
| B15 | PASS | `test_metadata_whole_replacement`、`test_metadata_object_check` |
| B16 | PASS | `test_metadata_whole_replacement`、`test_update_audit_snapshot_content`（审计 after 整值） |
| B17 | PASS | `test_delete_reference_checker_stub_blocks`、`test_public_service_reference_register_hook` |
| B18 | PASS | `test_delete_default_empty_reference_set` |
| B19 | PASS | `test_delete_default_empty_reference_set` + 静态 E9（无 Endpoint 触碰） |
| B20 | PASS | `test_restore_success_and_audit` |
| B21 | PASS | `test_soft_delete_reuse_and_restore_conflict` |
| B22 | PASS | `test_restore_dependency_resource_deleted` |
| B23 | PASS | `test_restore_success_and_audit`（仅自身恢复） |
| B24 | PASS | `test_permissions`、`test_unauthenticated_401` |
| B25 | PASS | `test_activity_trail`、`test_audit_whitelist_row`、`test_update_audit_snapshot_content` |
| B26 | PASS | `test_audit_failure_rolls_back_all_service_writes`（四 action 同回滚） |
| B27 | PASS | `test_view_deleted_and_detail`、`test_list_filters_and_pagination` |
| B28 | PASS | `test_list_filters_and_pagination` |
| B29 | PASS | `test_partial_unique_name` |
| B30 | PASS | `test_concurrent_same_name_insert`（raw 真提交） |
| B31 | PASS | `test_undeleted_service_blocks_resource_delete` |
| B32 | PASS | `test_restore_dependency_resource_deleted`（软删 Service 后 Resource 可删） |
| B33 | PASS | `test_optimistic_lock_two_sessions`（两真实会话） |
| B34 | PASS | `test_restore_vs_recreate_concurrency`（真实部分唯一仲裁，最终仅一未删行） |
| B35 | PASS | `test_restore_dependency_resource_deleted`、`test_restore_not_deleted`、`test_resource_immutable`（抽查顺序） |
| B36 | PASS | `test_list_filters_and_pagination`、`test_nested_resource_and_query` |
| B37 | PASS | E5；`test_migration_up_down_up_and_single_head` |
| B38 | PASS | `test_read_only_has_no_side_effects` |
| B39 | PASS | `test_fk_restrict_and_soft_delete_retention`（机制级） |
| B40 | PASS | `test_resource_immutable`、`test_description_nullable_and_preserved`、`test_metadata_whole_replacement` |

### 11.7 三分界声明

1. **F011 独立可验证（本次全部执行）**：A1–A9、A11–A18，V-DB-112–125，B1–B16/B19–B40。
2. **F011 + Endpoint 桩（仅结构与挂钩，不能证明真实 Endpoint 数据语义）**：A10 的 `register_service_reference_checker` 公共挂钩、默认空集、桩返回引用时 DELETE→409 `reference_exists{references:[{object_type:"service_endpoint",...}]}` 与不级联；对应 §31 T23 的结构/挂钩部分。
3. **留待 F012（本 Feature 不可执行）**：含真实 ServiceEndpoint 的端到端（T23 完整）、真实 `service_endpoint` 引用数据、Endpoint 本体与监听唯一性。F011 局部 PASS 不拼成 T23 通过。

### 11.8 Defects

| ID | Severity | Layer | Location | 期望/实际 | Owner | 必须修复 |
| --- | --- | --- | --- | --- | --- | --- |
| F011-TE1-01 | NOTE | Database 文档 | `docs/database/f011-service.md` §7 V-DB-112 | 期望“8 CHECK + 1 PK + 1 FK”；实际文案写“9 CHECK”。实现与 DB §2 表均为 8 CHECK，无功能影响 | Database | 否 |
| F011-TE1-02 | NOTE | Backend 文档 | `docs/features/F011/implementation.md` §1 | 期望准确记录注册路径；实际写“`app/services/resource.py` 导入 service 完成注册”，实为 `app/services/service.py` 模块级 `cluster_service.register_reference_checker`，经 API 路由导入生效。运行期行为正确（`test_undeleted_service_blocks_resource_delete` PASS） | Backend / 协调器 | 否 |
| F011-TE1-03 | MEDIUM（非 F011） | 测试基础设施 | `tests/integration/test_clusters.py::test_audit_four_actions_and_activity`、`tests/integration/test_ip_addresses.py::test_concurrent_gateway_change_and_allocation` | 4 次全量运行中 1 次出现这 2 项偶发失败，单独重跑与再次全量均通过；与 F011 无代码关联，表明 F003/F010 并发/审计用例存在时序性 flake | 协调器 / Backend 测试基础设施 | 否（F011 不阻塞；建议后续隔离修复） |
| F011-TE1-04 | NOTE | 集成环境 | Compose/Nginx 真实前后端 | `compose.yaml` 的后端/前端需 `docker build`，本轮按任务约束未构建；前端以 `typecheck`+`build`+`smoke:client` 机制级验证。不降 F011 验收（真实浏览器 DOM 非必要判据） | 协调器 | 否 |

### 11.9 未验证项

| 项 | 状态 | 原因 |
| --- | --- | --- |
| T23 真实 ServiceEndpoint 端到端 | `NOT TESTED / 归 F012` | Endpoint 本体（F012）未交付；F011 仅提供挂钩/默认空集 |
| §17 全局 Service 搜索、§19 Cluster Detail Services、§20 Dashboard 聚合 | `NOT TESTED / 归 F013` | 归 F013 消费 F011 数据 |
| CSV/Excel 导入一致性 | `NOT TESTED / 归 F014` | 导入归 F014；F011 仅提供字段口径 |
| 完整 Audit 查询页（§22） | `NOT TESTED / 归 F015` | F011 仅验证资源级 Activity 四 action |
| 跨功能 §31–33 整体验收 | `NOT TESTED / 归 F016` | 不由 F011 局部 PASS 拼接 |
| Compose 入口 Nginx 真实前后端集成 / 真实浏览器 DOM | `NOT TESTED / BLOCKED（环境）` | Compose 需构建镜像（任务禁止 `docker build`）；见 F011-TE1-04 |
| F001 `test_migrations` V3b | `SKIPPED` | 连接角色为 superuser，环境性跳过（非 F011） |

### 11.10 TE-1 结论

- F011 独立范围（A1–A9、A11–A18；V-DB-112–125；B 场景除 F012/F013 分界项外）全部 PASS；无必须修复的实现缺陷；F011 无 BLOCKER/HIGH。
- 新增 12 项 Tester 独立测试，其中 B26/B33/B34/A10 公共挂钩/只读无副作用为本次新增执行证据。
- 真实 Endpoint 端到端（T23）与 F013/F014/F015/F016 范围保持 `NOT TESTED`，不声明整条 §31 通过。
- 前端 typecheck/build/smoke 通过（187/0）；真实 Nginx 集成因环境（禁止构建镜像）记 `NOT TESTED / BLOCKED`，不降验收。

**结论：`READY FOR REVIEW`**

GIT: git rev-parse --short HEAD
GIT: git status --porcelain
GIT: git branch --show-current