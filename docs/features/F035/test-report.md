# F035 向既有 Resource 追加 Interface/IP 导入 — Test Report

> 本文件同一份报告承载 TEST_DESIGN 与 TEST 两阶段，分开记录版本、结论与证据。
> **当前状态**：§1 TEST DESIGN 为 **TD-F035-1（v1，2026-10-26，`TEST DESIGN READY`）**；§2 TEST EXECUTION **尚未编写**（实现未开始，`backend/app/**` 在 `76d8410..9e80a7c` 内零 diff）。
> `TEST DESIGN READY` 仅表示方案可验证，**不是测试通过**，也不批准实现、Contract 定稿或合并。

---

## 1. Test Design（TD-F035-1，v1，2026-10-26）

### TD-1 Task / Status / Basis

- **Task**：F035「向既有 Resource 追加 Interface / IP 批量导入」（P1 / M26）；分支 `feature/F035-append-interface-ip`（base `v3.3`，`start_commit` `76d8410`，本 TD 编写时 HEAD `9e80a7c`）；`plan_revision` 21；阶段 **TEST_DESIGN**；Tester 只读分析 + 仅写本文件。
- **Status**：`TEST DESIGN READY`（见 TD-12；2 个 TEST 前置条件与 7 条记录项不改变「可验证」结论，见 TD-10 / TD-11）。
- **范围**：只做设计检查——验收映射、边界与并发场景、夹具/环境、可观察结果与可验证性。**未执行任何验收测试**；下文所有「预期」均为待执行断言，不得读作 PASS。

**Basis（版本与上游依据）**

| 对象 | 版本 / 状态 | 本 TD 的使用方式 |
| --- | --- | --- |
| `docs/product/requirements-v3.md` | **revision 14**（2026-10-26）；§24.6 CONFIRMED 全节；§24 / §24.1 / §24.5 经 §24.6 修订的措辞；§11.1 / §13.2 / §14 / §21 / §22 / §23 / §23.2；§31 **T117–T126** 与修订后的 **T67 / T71**；§32 | 验收映射唯一上游（TD-3） |
| 用户裁定（CONFIRMED） | CHG013-**BQ01=B** / **BQ02=B** / **BQ03=A** / **BQ04=A** / **BQ05=A** / **BQ06=C1** / **BQ07=A** / **BQ08=A**；plan_revision 21；`execution.authorization.feature_ids=[F035]`（`docs/project/project-plan.yaml`） | 判定「预期行为」的裁定依据；不得据测试结果自行改写 |
| `docs/features/F035/product.md` | v1（READY FOR ARCHITECT） | §1 范围、§2 明确不做、§3 验收映射、§4 边界与风险 |
| `docs/features/F035/architecture.md` | **v1**（`READY FOR DESIGN`；§12 定稿签核待 CONTRACT） | §3 方案（组级二态 / 比较列集 / 两条只读检查 / 软删）、§4 事务与锁序、§5 完整性表、§7 逐文件工作项（含 §7.2 测试文件、§7.3 前端文案）、§8 V1–V12、§9 DR-F035-01–14、§10 R1–R7 |
| `docs/api/F023.md` | **v2**（Architect 2026-10-26 正文升版；替代 §4 计数 bullet、§8.1、§11、§12.3 第 1–2 项、§13 第 1/3 项；端点/字段/错误码/`reason` 集合/26 列模板/上限/权限/原子性零变更；含「与既有增补节的衔接」段） | 断言口径正文；重点 §1.2 错误码集合、§4 计数、§8.1 二态、§11 现存冲突、§12.3 锁集合、§12.5 归因、§13 边界 |
| 既有 Contract（继续有效） | `docs/api/F014.md` v1（+「追加能力不适用于本文件」事实补注）、`docs/api/F027.md` v1（范围语义增补节）、`docs/api/F002.md`（错误信封 / 401·403 / 错误码注册表） | 上限 5,242,880 B / 5000 行 / 1000 预览；`RowError` 形状；401/403 顺序；行级范围拒绝 |
| `docs/database/f023-import.md` | `NOT_REQUIRED`（`layers.database=false`） | 本 Feature 无 Schema 变更；本 TD 以「零 Schema 漂移」断言替代约束验证（TD-7） |
| 既有测试与证据（只作基线，不复用 PASS） | `backend/tests/integration/test_f023_resource_interface_ip_import.py`（28 passed，TR-1-R1）、`docs/features/F023/test-report.md`（并发 `Barrier` 双会话做法、`_run_pair`）、`backend/tests/integration/test_f034_csv_text_carrier*.py`、`docs/features/F034/test-report.md`（H/B 层方法）、`scripts/test_collect_host_info.py` | 夹具/并发/层级的可执行方法与回归基线 |
| 规则与方法 | `docs/project/handoff.md`、`docs/project/implementation-rules.md`、`AGENTS.md` §5–§9、`.pi/skills/data-integrity/SKILL.md` | 交接/缺陷格式；验证纪律；完整性方法 |
| 代码基线（只读核对，HEAD `9e80a7c`） | `backend/app/services/resource_interface_ip_import.py`（`_parse_row:723-745` 冲突块、`_merge_and_check`、`_build_groups`、`_acquire_locks:1017-1048`、`_attribute_integrity`、`_app_error_field`、`write_import`）、`resource.py:297-329`（`_hardware_snapshot`/`_virtual_machine_snapshot`）、`interface.py:467-566`（`prepare/stage_interface`）、`ip_address.py:588-666`、`resource_import.py:740-760`（F014 hostname 冲突块）、`backend/tests/conftest.py`、`frontend/src/components/ResourceInterfaceIpImportPanel.tsx`、`frontend/src/components/ResourceImportPanel.tsx`、`frontend/scripts/smoke-client.mjs` | 判定可观察面（字段名、归因路径、审计、锁）与断言可实现性 |

- **复用声明**：F023 / F034 / F014 既有套件仅作**回归与口径参照**执行，**不以任何既有 PASS 代替 T117–T126 验收**；F023 历史报告证据不改写（product §2）。

### TD-2 层级记号与可验证性前提

| 记号 | 层次 | 载体 | 说明 |
| --- | --- | --- | --- |
| **U** | 纯逻辑单元 | pytest，直调 `unified` 服务层纯函数/非提交核心 | `_canonicalize`、`_merge_and_check`、新增 `_check_existing_consistency`、`_build_groups`、`_attribute_integrity`/`_app_error_field` |
| **I** | 真实后端集成 | pytest + **真实 PostgreSQL 16** + 真实 `create_app`/`TestClient`（`auth_app`）+ 真提交（`auth_session_factory`） | 追加语义、零变化快照、归因、原子性、计数、权限、软删、并发 |
| **H** | 真实 HTTP（无浏览器） | 真实服务端 + `POST /validate`（只读） | 只读追加探针；**需要候选后端在跑**（见 PR-2） |
| **M** | 前端机制级 | `npm run smoke:client`（`globalThis.fetch` 受控替身） | 既有 F023/F034 段零回归；`created=0` 的 wire 解析（纯数据，无 DOM） |
| **S** | 静态守卫 | `git diff` / `grep` | 零 diff 守卫、模板/错误码/上限零变更、面板文案存在性、无「追加数 M」、无新响应字段 |
| **B** | 浏览器 | Playwright/Chromium（宿主已装）+ 候选 `frontend/dist` + 真实后端 | 面板文案、`created===0` 定性提示、错误表呈现；需 PR-2 |

**可验证性前提（如实声明）**

1. **PR-1（测试数据库，阻塞 I 层）**：现场 `csmtest-db-1`（PostgreSQL 16.15）可用，但宿主 `127.0.0.1:5432` **未开放**，且该实例内**不存在 `csm_test` 库**；`.env.test` 的 `TEST_DATABASE_URL` 指向 `localhost:5432/csm_test`。TEST 阶段开始前必须由协调器提供可达测试库（二选一：`docker run -d --name csm-f035-pg -p 55432:5432 postgres:16` + `createdb csm_test`；或 `docker exec csmtest-db-1 createdb -U csm csm_test` 后在 `csmtest_default` 网络内运行 pytest）。DB-D10 双守卫（库名含 `test`、≠ `DATABASE_URL`）保持不变。
2. **PR-2（候选构建，影响 H/B 层）**：当前 `csmtest` 栈（18080）跑的是 **F035 之前的镜像**，无法呈现追加语义。H/B 层须满足其一：(a) 用候选 HEAD 重建 `backend` + `frontend` 容器；(b) 在 `csmtest_default` 网络上以候选 `backend/app` 起一个只读后端实例（`docker run … -p 18081:8000 -v $PWD/backend/app:/app/app:ro`），并用静态服务器托管候选 `frontend/dist`、把 `/api/v1/**` 转发到该实例（沿用 F034 `f034-ui-browser-check.py` 的方法）。二者都不做时，H/B 一律如实标 `NOT TESTED`（TD-10），不得以 S+M 宣称交互正确。
3. **I 层是唯一可证明数据库行为的层次**：SQLite / Mock 不构成约束与并发证据（`implementation-rules.md`）。并发用例使用 `threading.Barrier(2)` + 两个独立 `auth_session_factory` 会话 + 真提交（复用 F023 `_run_pair` 做法），断言**最终持久化结果**，不只断言「没抛异常」。
4. **符号名以架构 §7.1 为准**（`existing_resource_id`、`_load_existing_snapshots`、`_check_existing_consistency`、`_check_existing_interface_names`、`ExistingSnapshot`）：TEST 按**语义**断言；实现采用等价改名时不判 FAIL，但缺同一语义、或语义偏离架构/契约，判 FAIL（或按 TD-11 交回 Architect），并在报告登记实际名称。
5. **不得发明领域状态或默认值**：所有预期只引用 §24.6 / F023 v2 / DR-F035-*；契约未固定的细节按 TD-11 记录项处理，不转成断言。

### TD-3 验收映射（T117–T126 + T67/T71 → 用例 ID / 层次 / 可观察断言）

记法：用例 ID = `TD3-F035-<验收>.<序号>`；TEST 阶段逐条标 `PASS / FAIL / BLOCKED / NOT TESTED` 并附命令与证据路径。

| 验收 | 用例 ID | 层 | 可观察断言（判据摘要） |
| --- | --- | --- | --- |
| **T117** | `TD3-F035-T117.1` | I | 宿主 `(cluster,hostname)` 已存在且未软删，批次仅含新增三元组行 → `POST /validate` 200 且 `error_count==0`、`importable_rows==total_rows`；`POST` 写入 201 |
| | `TD3-F035-T117.2` | I | 写入后：新 Interface 的 `resource_id == 宿主 id`；新 IP 的 `interface_id == 新 Interface id`；`resources` 表计数**不变**（`created==0`） |
| | `TD3-F035-T117.3` | I | 同批字节经 `csv` 与 `xlsx` 载体各自追加成功，落库结果一致（interface name / ip / 绑定相同） |
| | `TD3-F035-T117.4` | H | 真实服务端只读 `POST /validate`（文件载体 multipart，`format=csv`）对追加行返回 200、`error_count==0`（候选后端；PR-2） |
| | `TD3-F035-T117.5` | B | 面板上粘贴/上载追加行 → 预校验「0 错误」→「确认导入」可用 → 成功提示（PR-2） |
| **T118** | `TD3-F035-T118.1` | I | 追加前后对宿主做**全列快照**：`resources` 全列 + `bare_metal_details` / `virtual_machine_details` 全列 + `xmin::text` 逐字段相等；`version`、`updated_at` 相等 |
| | `TD3-F035-T118.2` | I | 宿主的既有 Interface / 既有 IPAddress 全列快照（含 `ip_addresses.interface_id`、`version`、`updated_at`）逐字段相等；宿主 `interfaces` 计数 +1、`ip_addresses` 计数 +N |
| | `TD3-F035-T118.3` | I | `audit_logs` 中 `object_type='resource' AND object_id=宿主 AND action='UPDATE'` 计数 **== 0**；本批 `audit_logs` 增量 == 新 Interface 数 + 新 IP 数（每对象恰 1 条 `CREATE`） |
| | `TD3-F035-T118.4` | I | `GET /api/v1/resources/{宿主}/activity` 的 `items[].action` 集合 ⊆ `{CREATE}`（无 UPDATE / DELETE / RESTORE），且 `total` 与追加前相等 |
| | `TD3-F035-T118.5` | I | 同一断言在 **VM 宿主**（`virtual_machine` 明细 + `host` 列）上复现：明细全列零变化、无 `resource` UPDATE Audit |
| **T119** | `TD3-F035-T119.1` | I | 宿主为 BM、行给 `resource_type=VIRTUAL_MACHINE` → `error.field=="resource_type"`，写入 422 且整批回滚 |
| | `TD3-F035-T119.2` | I | 宿主 `role=COMPUTE` + 行 `role=GPU` → `field=="role"`；`status` 同理 → `field=="status"` |
| | `TD3-F035-T119.3` | I | BM 硬件列逐列不一致（`manufacturer` / `cpu_cores` / `gpu_count` / `memory_mb` 各一例）→ `field` 分别为对应模板列名 |
| | `TD3-F035-T119.4` | I | VM 列逐列不一致（`vcpu` / `disk_gb` / `hypervisor` / `memory_mb` / `host`）→ `field` 为对应模板列名（`host` 指向与既有 `host_resource_id` 不同的 BM） |
| | `TD3-F035-T119.5` | I | **留空不比较、不置空**：宿主 `role=GPU`/`status=ALLOC`/硬件值非空，行全部留空 → `error_count==0`、写入 201，且宿主各列值快照不变 |
| | `TD3-F035-T119.6` | I | **既有 `null` 不能补填**：宿主 `cpu_cores`（或 BM `memory_mb`）为 `null`、(a) 行给值 → `field=="cpu_cores"` 行错误；(b) 行留空 → 无错误且仍为 `null` |
| | `TD3-F035-T119.7` | I | **精确比较不折叠**：宿主 `manufacturer="Dell"`，行 `"DELL"` → `field=="manufacturer"`；行 `"Dell"`（含首尾空格，服务端 trim 后）→ 0 错误 |
| | `TD3-F035-T119.8` | I | 一致性错误的 `related_row is None`（DR-F035-08），`reason` 非空，`field` 为模板列名 |
| | `TD3-F035-T119.9` | I | 不一致时整批 422：`resources` / `*_details` / `interfaces` / `ip_addresses` / `audit_logs` 计数与基线相等；宿主各列值不变 |
| | `TD3-F035-T119.10` | U | `_check_existing_consistency(rows, snapshots)`：比较列集 == 组内 canonical `resource_cells` 键集合（留空列不出现，故不比较）；`(row, field)` 去重；命中项归因模板列名 |
| | `TD3-F035-T119.11` | I | 预校验与写入同口径：同字节先 `/validate` → 外部改宿主 `role`（合法 API 更新）→ 写入按最新状态报 `field=="role"`、零残留（不静默覆盖） |
| **T120** | `TD3-F035-T120.1` | I | 宿主已有未软删 `eth0`，追加行 `name="eth0"` → `field=="name"`；`/validate` 200 报错 + 写入 422；不跳过、无部分成功（零残留） |
| | `TD3-F035-T120.2` | I | **大小写敏感**：宿主已有 `Eth0`，行 `name="eth0"` → 0 错误、写入 201，新 Interface `name=="eth0"` 与既有 `Eth0` 并存 |
| | `TD3-F035-T120.3` | I | 同 Cluster 已有未软删 IP `10.50.0.20`，追加行用该 IP → `field=="ip"`、422、零残留 |
| | `TD3-F035-T120.4` | I | **跨 Cluster 同地址不算冲突**：另一 Cluster 有 `10.50.0.20`（各自 Network）→ 本 Cluster 追加同地址 201 成功 |
| | `TD3-F035-T120.5` | I | 命中既有 Interface 名时**不向其追加 IP**：该 Interface 下 `ip_addresses` 计数与各行 `interface_id` 不变（BQ05=A） |
| | `TD3-F035-T120.6` | I | 上述两冲突在 `/validate`（200 + `errors`）与写入（422 `IMPORT_VALIDATION_FAILED`）中 `row`/`field`/`reason` 一致 |
| **T121** | `TD3-F035-T121.1` | I | 追加行 `interface_type` 留空 → 新 Interface `interface_type=="OTHER"`；`name="eth0"` 不推断类型 |
| | `TD3-F035-T121.2` | I | `enabled` 留空 → `true`；显式 `false`/`0` → `false` |
| | `TD3-F035-T121.3` | I | `mac_address` 保留大小写与格式（无正则）；`speed_mbps`/`mtu` 正整数落库；`mtu=0` / 非整数 → `field` 为对应列名、整批回滚 |
| | `TD3-F035-T121.4` | I | 同资源 name 唯一（本批语义）：同组两行同 `name` 不同 IP → **1 个**新 Interface、**2 个** IP 绑定到它（`interfaces_created==1`、`ip_addresses_created==2`） |
| | `TD3-F035-T121.5` | I | 新 Interface 的 `parent_interface_id IS NULL`、`description IS NULL`、`metadata == {}` |
| **T122** | `TD3-F035-T122.1` | I | 属 Network CIDR + §11.1 边界：`/30` 网络/广播地址、gateway、RESERVED 池内、禁用段（`127/8`、`169.254/16`、`224/4`）逐例 → `field=="ip"`、整批 422、零残留 |
| | `TD3-F035-T122.2` | I | 同 Cluster 唯一（串行）：既有 IP 再现在本批另一追加行中 → `field=="ip"`（并发见 V11） |
| | `TD3-F035-T122.3` | I | 绑定同 Cluster：`network` 指向**另一 Cluster** 的 Network → 行错误（`field=="network"`）；`ip` 的 `/mask` 解析到跨 Cluster 段 → `field=="ip"`；两者整批回滚 |
| | `TD3-F035-T122.4` | I | 手动分配语义：新 IP 的 `ip_pool_id` == 覆盖该地址的未删 Pool id（或 `null`）；Pool 行全列快照不变；不新增 Pool / Network |
| | `TD3-F035-T122.5` | I | 不触发自动分配：AUTO 模式的 Pool 上追加单地址 → 只产生本行 1 个 IP（无额外地址），`ip_pools.allocation_mode` / `auto_allocate` 不变 |
| | `TD3-F035-T122.6` | I | Network 必须已存在且 ACTIVE：INACTIVE → 行错误；软删 → 视为不存在 → 行错误；`networks` 计数不变 |
| **T123** | `TD3-F035-T123.1` | I | 混合批（新建组 A + 追加组 B）成功：`created==1`、`interfaces_created` / `ip_addresses_created` 按实际、`total_rows==ip_addresses_created`；新建 Resource 与追加子对象同事务落库 |
| | `TD3-F035-T123.2` | I | 混合批任一行失败 → 整批 422：新建 Resource **不留存**（按 hostname 查 `total==0`）、追加宿主无新 Interface/IP、`audit_logs` 计数与基线相等（无 Audit / Activity 残留） |
| | `TD3-F035-T123.3` | I | 预校验 0 错误后**外部在同宿主创建同名 Interface** → 写入 422 `field=="name"`、零残留、不静默覆盖 |
| | `TD3-F035-T123.4` | I | 预校验后**外部占用目标 IP** → 写入 422 `field=="ip"`、零残留（追加组变体；新建组变体沿用 F023 `test_pg11b_*`） |
| | `TD3-F035-T123.5` | I | 预校验后宿主被软删 → 按「新建」处理：`created==1`、新 Resource id ≠ 原 id、原 Resource 仍软删且其子对象不变（V12 记录项，不断言为错误） |
| **T124** | `TD3-F035-T124.1` | I | 纯追加批 `created==0`、`interfaces_created` / `ip_addresses_created` / `total_rows` 按实际计数 |
| | `TD3-F035-T124.2` | I | 响应体键集合恰为 `{created,total_rows,interfaces_created,ip_addresses_created}`（无新字段） |
| | `TD3-F035-T124.3` | I | VIEWER：`POST /validate` 与写入均 403 `FORBIDDEN{reason:"permission"}`；`GET /templates` 200 |
| | `TD3-F035-T124.4` | I | 未认证：两端点 401 `AUTH_REQUIRED`，且**先于** 403 判定（无 Cookie 且无权限） |
| | `TD3-F035-T124.5` | I（`real_scope` 模块） | 行指向未授权 Cluster → 整批失败，含 `row` + `field=="cluster"` + 权限原因，无写入、不泄露 Cluster 存在性 |
| | `TD3-F035-T124.6` | I（`real_scope` 模块） | 混合批「授权集群新建组 + 未授权集群追加组」→ 整批失败、新建组不留存（无部分成功） |
| **T125** | `TD3-F035-T125.1` | I | 宿主已软删 → 视为不存在：写入 201、`created==1`、新 Resource id ≠ 软删 id；软删行仍 `deleted_at IS NOT NULL` 且其 `reason`/子对象全列不变（不复活） |
| | `TD3-F035-T125.2` | I | 软删宿主曾用接口名 `eth0`：新 Resource 下 `eth0` 合法创建（唯一性范围是 per-resource，不因软删行残留报错） |
| | `TD3-F035-T125.3` | I | 不创建其它对象：`clusters` / `networks` / `ip_pools` / `services` / `service_endpoints` 计数不变；`resources` 仅按「新建组」增加 |
| | `TD3-F035-T125.4` | I | 不支持向既有 Interface 追加 IP（BQ05=A）：追加行命中既有 Interface 名一律 `field=="name"`；既有 IP 行 `interface_id` 不变（与 `TD3-F035-T120.1/.5` 交叉引用） |
| **T126** | `TD3-F035-T126.1` | I | F014 资源导入零回归：BM 14 / VM 10 模板不变，已存在 hostname **仍报冲突** `field=="hostname"`（`test_imports.py` / `test_import_tester_acceptance.py` 全绿 + 定向断言） |
| | `TD3-F035-T126.2` | I | F023 新建路径零回归：`test_f023_resource_interface_ip_import.py` 全绿（更新后，见 TD-6），`created>0` 语义、Network 解析、VM Host、整批回滚不变 |
| | `TD3-F035-T126.3` | I | T64–T72 覆盖保持（F023 套件内），且 T67 / T71 按 revision 14 修订措辞重述 |
| | `TD3-F035-T126.4` | I | T107–T116 零回归：`test_f034_csv_text_carrier.py` + `test_f034_csv_text_carrier_scope.py` 全绿（载体等价性、上限、范围、无痕迹） |
| | `TD3-F035-T126.5` | U | 采集脚本零回归：`scripts/test_collect_host_info.py` 全绿（T73–T84 / T100–T106，含 T106 契约零 diff） |
| | `TD3-F035-T126.6` | I+S | 模板 / 端点 / 错误码 / 上限零变更：`GET /templates` 26 列名与列序逐字一致；`/validate` / 写入 / `/templates` 三路由存在且无新增；`IMPORT_*` 码集合与 `IMPORT_INVALID_FILE.details.reason` 集合不变；`import_max_file_bytes==5_242_880`、`import_max_rows==5000` |
| | `TD3-F035-T126.7` | S | 零 diff 守卫（见 TD-7 命令 7）：`backend/app/models/**`、`backend/alembic/**`、`imports.py`、`resource_import.py`、`resource.py`、`interface.py`、`ip_address.py`、`network.py`、`ip_capacity.py`、`docs/api/F002.md` 空 diff；`docs/api/F023.md` diff 只落在 v2 声明的 §4/§8.1/§11/§12.3/§13 + 头部与修订表（§6/§14/§1.2 零改动） |
| | `TD3-F035-T126.8` | M | 前端既有 F023 / F034 smoke 段零失败，计数 ≥ 当前基线 + 新增（F034 记录基线 337 passed；TEST 以实测为准并列出新增用例名） |
| **T67** | `TD3-F035-T67.1` | I | 同资源 interface name 重复、同 Cluster IP 现存重复或非法行仍报错，`row`/`field`/`reason` 齐备；`(cluster,hostname)` 已存在**不再报错**而按 §24.6 追加（仅本入口） |
| | `TD3-F035-T67.2` | I | 资源导入入口对已存在 hostname 仍报冲突（与 `TD3-F035-T126.1` 同一证据，双侧对比断言） |
| **T71** | `TD3-F035-T71.1` | I | 追加路径复用同一 Service Layer：导入创建的 Interface / IP 在 API 侧同名、同接口同名、同 Cluster 同 IP → 409（唯一性范围一致，未绕过） |
| | `TD3-F035-T71.2` | I+S | 追加**不新建 Resource**，故无 hostname 唯一性判定：追加成功批的 `audit_logs` 中不存在 `object_type='resource'` 的 `CREATE`/`UPDATE`；源码无独立直写 SQL（沿用 `test_reg01_no_direct_write_sql` 口径，`stage_*`/`prepare_*` 命中） |

### TD-4 V1–V12 的用例化（架构 §8 → 用例 ID / 硬判据）

| V | 覆盖 | 用例 ID | 层次 | 硬判据 / 说明 |
| --- | --- | --- | --- | --- |
| **V1** | 纯追加成功（BM 与 VM 各一） | `TD3-F035-V1.1`(I, BM) / `TD3-F035-V1.2`(I, VM) | I | 201；`created==0`；宿主 id 不变；新子对象归属与绑定正确；VM 追加行 `host` 必须与既有 `host_resource_id` 一致（R5） |
| **V2** | 既有 Resource 零变化 + 无 `resource` UPDATE Audit | `TD3-F035-T118.1`–`.5` | I | **硬判据（任一不满足即 FAIL，不允许以「业务上等价」替代）**：①`resources` 全列 + `bare_metal_details`/`virtual_machine_details` 全列逐字段相等；②`SELECT xmin::text FROM resources WHERE id=:host` 前后相等（PostgreSQL 物理层无 UPDATE）；③`version`、`updated_at` 相等；④既有 `interfaces`/`ip_addresses` 全列（含 `interface_id`、`version`、`updated_at`）相等；⑤`object_type='resource' AND object_id=host AND action='UPDATE'` 计数 == 0；⑥`GET /resources/{host}/activity` 无 UPDATE 项；⑦本批 `audit_logs` 增量 == 新 Interface 数 + 新 IP 数；⑧新增 Interface / IP 各 1 条 `CREATE` |
| **V3** | 逐列不一致 → 对应 `field`；留空不比较 / 不置空；`null` 不补填 | `TD3-F035-T119.1`–`.11` | I + U | 归因 `field` = 模板列名（含 `resource_type`），`related_row is None`；留空列不出现在比较集；既有 `null` 提供值即报该列错误、留空则保持 `null`；字符串精确比较（不折叠）；不一致整批 422 且零残留 |
| **V4** | 同名 Interface 区分大小写 → `name`；同 Cluster 既有 IP → `ip` | `TD3-F035-T120.1`–`.6` | I | `Eth0` ≠ `eth0`；命中即报错、不跳过、无部分成功；`/validate` 与写入同口径 |
| **V5** | Interface 追加规则沿用 | `TD3-F035-T121.1`–`.5` | I | `interface_type` 空→`OTHER`（不推断）、`enabled` 空→`true`、mac/speed/mtu 复用 F007、同资源 name 唯一、无 `parent_interface` |
| **V6** | IP 追加规则沿用 | `TD3-F035-T122.1`–`.6` | I | 属 CIDR、§11.1 边界、非 gateway/RESERVED/禁用段、同 Cluster 唯一、绑定同 Cluster、手动分配、不触发自动分配、不合法整批回滚 |
| **V7** | 混合批原子性 + 预校验后状态变化 → 422 | `TD3-F035-T123.1`–`.4` | I | 新建组与追加组同事务；失败整批回滚零残留（含新建 Resource 不留存）；状态变化 422 `IMPORT_VALIDATION_FAILED`、不静默覆盖 |
| **V8** | 计数 C1 + 权限 / 范围 | `TD3-F035-T124.1`–`.6` | I | 纯追加 `created==0`；响应键集合恰 4 个；403 / 401（401 先于 403）；未授权集群行整批失败 |
| **V9** | 软删视为不存在；不创建其它对象；不支持向既有 Interface 追加 IP | `TD3-F035-T125.1`–`.4` | I | 软删宿主 → 新建、不复活；`clusters`/`networks`/`ip_pools`/`services`/`service_endpoints` 零 delta |
| **V10** | 零回归 | `TD3-F035-T126.1`–`.8` + `T67.1/.2` + `T71.1/.2` | I + U + M + S | 见 TD-6 命令 2–7；任一既有套件失败即 FAIL（不得以「与 F035 无关」免除，须定位到根因后才可判 NOT_RELATED 并登记） |
| **V11** | 真实 PG 双会话并发五场景 + 无 `40P01` | `TD3-F035-V11.1`–`V11.5` | I | 见下 |
| **V12** | 预校验后宿主软删 → 按新建处理 | `TD3-F035-T123.5` | I | **记录项**（R3）：断言 `created==1`、新 id、原行仍软删且子对象不变；**不得断言为错误**。若实现改为报错，登记行为差异并交 Architect（不得自行改设计） |

**V11 并发场景（`threading.Barrier(2)` + 两个独立 `auth_session_factory` 会话 + 直调 `unified.write_import`，复用 F023 `_run_pair` 结构；上限 `join(timeout=60)`）**

| ID | 场景 | 断言 |
| --- | --- | --- |
| `TD3-F035-V11.1` | 两批都追加到**同一宿主**、网卡名不同（`ethA`/`ethB`）、IP 不同 | 两批均成功；宿主全列快照与 `xmin` 不变；`interfaces` +2、`ip_addresses` +2、`audit_logs` +4；无错无残留 |
| `TD3-F035-V11.2` | 两批追加到**同一宿主**、**同网卡名**（IP 不同） | 恰一批成功、另一批 `ImportValidationFailed` 且 `field=="name"`；最终该宿主仅 1 个新 Interface、1 个新 IP；`audit_logs` 只含胜方（+2） |
| `TD3-F035-V11.3` | 两批（追加组，不同宿主）抢**同一 IP** | 恰一成功；败方 `field=="ip"`；`ip_addresses` +1；无残留 |
| `TD3-F035-V11.4` | 两批**新建**同一 hostname（保留 F023 PG-05a 兜底） | 恰一成功；败方 `field=="hostname"`（`uq_resources_cluster_id_hostname_key` 归因）；`resources`/`interfaces`/`ip_addresses` 各 +1、`audit_logs` +3 |
| `TD3-F035-V11.5` | **锁环回归**（DR-F035-03）：批 A = {VM 组 host=H1} ∪ {追加组宿主 H2}，批 B = {VM 组 host=H2} ∪ {追加组宿主 H1} | 两批**都成功**、无 `500 INTERNAL_ERROR`；若实现把「VM Host」与「追加宿主」分两条 `FOR UPDATE` 语句取锁（而非单语句同序），此例会 `40P01` → FAIL。断言最终 `resources` +2（两个 VM）、无残留 |

**并发纪律**：不重试（§12.4）；断言最终持久化结果与错误字段，不断言线程调度顺序；每例前置记录 `_counts` 基线并在断言后复核；用例间不共享 hostname / IP（统一前缀 `f35-`）。

### TD-5 夹具设计

**构造既有 Resource（前置数据一律经真实 API 建立，不走 SQL 直写）**

| 夹具 | 构造 | 用途 |
| --- | --- | --- |
| `F-35-01` `mk_bm_host(hostname, **hardware)` | `POST /api/v1/resources`（`BARE_METAL`，可指定 `role`/`status`/`hardware` 全列） | V1/V2/V3 宿主；`mk_bm_host("f35-h1", role="COMPUTE", status="IDLE", hardware={...全列...})` |
| `F-35-02` `mk_bm_host_nulls(hostname)` | 仅必填字段创建 → 硬件的 `memory_mb`/`cpu_cores`/`gpu_count` 等为 `null` | `T119.6`：「既有 null 不能补填」 |
| `F-35-03` `mk_host_with_children(hostname, iface="eth0", ip="10.50.0.20")` | 建 BM + `POST /api/v1/interfaces` + `POST /api/v1/ip-addresses`（`interface` 绑定） | `T118.2`/`T120.1`/`T120.5`：既有子对象与同名冲突 |
| `F-35-04` `mk_vm_host(hostname, host=bm_id, vcpu/memory/disk/hypervisor)` | 先建 BM（VM Host），再建 `VIRTUAL_MACHINE` Resource 并给 `virtual_machine` 明细 | V1.2 / `T118.5` / `T119.4` |
| `F-35-05` `cluster/network` 矩阵 | 主 Network `10.50.0.0/24`（ACTIVE）；`/30`、`/31`、`/32`；带 gateway；RESERVED Pool；禁用段（`127/8`、`169.254/16`、`224/4`）；另一 Cluster 的同地址 Network；INACTIVE Network；软删 Network | `T122.1/.3/.6` |
| `F-35-06` `soft_deleted_host()` | 建 BM + 子对象 → `DELETE /api/v1/resources/{id}?version=N`（ADMIN） | `T125.1/.2`、`T123.5` |
| `F-35-07` `deleted_cluster_scope()` | ADMIN 建 Cluster A / B，并只授权 EDITOR 到 A（`POST /api/v1/cluster-authorizations` 口径沿用 F027 套件） | `T124.5/.6`（`real_scope` 模块专用） |

**快照与「无 UPDATE Audit」的机械判据**

```python
COLUMNS = "SELECT * FROM {table} WHERE {where}"   # 全列 row-mapping，不做字段白名单
def snapshot(engine, host_id, child_ids):
    return {
        "resource":   row_dict(engine, "resources",           host_id),
        "resource_xmin": engine.execute(text("SELECT xmin::text FROM resources WHERE id=:i"), {"i": host_id}).scalar_one(),
        "bm":         row_dict(engine, "bare_metal_details",  f"resource_id='{host_id}'"),
        "vm":         row_dict(engine, "virtual_machine_details", f"resource_id='{host_id}'"),
        "interfaces": rows(engine, "interfaces",   f"resource_id='{host_id}' ORDER BY name"),
        "ips":        rows(engine, "ip_addresses", f"interface_id IN ({child_ids}) ORDER BY address"),
        "audit_counts": audit_count_by_object(engine, host_id, child_ids),   # {(object_type, object_id, action): n}
    }
```

- **前后深比较**：`assert snapshot_after == snapshot_before_for_host_scope`，其中 `resource` / `bm` / `vm` / `interfaces`(既有) / `ips`(既有) 必须**完全相等**；新增接口与 IP 单独以 id 集合差集核对，不混进同一次比较。
- **无 UPDATE Audit**：`SELECT count(*) FROM audit_logs WHERE object_type='resource' AND object_id=:host AND action='UPDATE'` == 0；另加 `SELECT count(*) FROM audit_logs WHERE action <> 'CREATE' AND created_at >= :baseline` == 0（防其它动作残留）。
- **Activity**：`GET /api/v1/resources/{host}/activity?page_size=100` → `{i["action"] for i in items} <= {"CREATE"}` 且 `total` 与追加前相等。
- **物理层**：`xmin::text` 相等证明宿主行未被 UPDATE（含「写入相同值也算 UPDATE」的情形）；`FOR UPDATE` 预锁不改变 `xmin`，提交后无残留 hint。
- **计数**：沿用 F023 `_counts(session)`（`clusters/resources/bare_metal_details/virtual_machine_details/interfaces/ip_addresses/audit_logs`），并补 `networks/ip_pools/services/service_endpoints` 用于 `T125.3`。

**清理与隔离**

- 一律使用 `auth_session_factory`（真提交）与 `committed_engine` 的函数级 teardown `TRUNCATE`（conftest 既有，排除 `alembic_version`）；会话级 `pg_engine` 以 `DROP SCHEMA public` + `alembic upgrade head` 起库，执行后重建（V4）。
- 并发用例的会话在线程内 `Session()` + `finally: session.close()`；线程 `join(timeout=60)` 后断言 `not thread.is_alive()`，避免悬挂会话污染后续用例。
- **不新建独立 schema、不引入第二个数据库**：`layers.database=false` 且无 Migration，无需 schema 隔离；分片靠 `f35-` 前缀 hostname/IP 段位（`10.50.x`、`10.51.x`…）避免跨用例撞唯一键。
- 前端不写业务库：B/H 层只走 `POST /validate`（只读）与登录；如 PR-2 采用重建容器，须在报告中记录镜像 tag/摘要与「未写入业务数据」。

**新增测试文件（TEST 阶段创建，本阶段未创建）**

| 文件 | 内容 |
| --- | --- |
| `backend/tests/integration/test_f035_append_interface_ip_import.py` | `TD3-F035-*` 的 U / I 用例（V1–V12 主体）+ 局部夹具（`HEADERS/_row/_csv_bytes/_post/_counts/_find_error/snapshot`，不依赖被修改的 F023 文件） |
| `backend/tests/integration/test_f035_append_scope.py` | `pytestmark = pytest.mark.real_scope`；`T124.5/.6`（沿用 F034 的 scope 分模块做法） |
| `docs/features/F035/artifacts/`（logs 被 `.gitignore` 忽略，须在报告声明） | H 层脚本与 B 层脚本、pytest/smoke 日志 |

### TD-6 既有 F023 用例更新清单（BQ01=B 引起的期望变化）

`backend/tests/integration/test_f023_resource_interface_ip_import.py` 的改动仅限「因 F023 v2 失效」的断言；**不得删除覆盖**，失效项须在 F035 套件中以等价或更强的用例承接，并在 TEST 报告中逐处登记「改前断言 → 改后断言 → 覆盖承接用例」。

| 位置（HEAD `9e80a7c`） | 现状断言 | v2 后是否失效 | 处理 |
| --- | --- | --- | --- |
| `test_pg06_uniqueness_and_allocatable_boundaries`（`_row(hostname="existing", ip="10.0.0.21")` + `_find_error(payload,"hostname",4)`） | 现存 hostname 冲突 → `field="hostname"` | **失效**（该行现在是合法追加：宿主默认 `OTHER/UNKNOWN`、BM、无既有接口） | 删除该行断言；`existing` 行的追加成功语义由 `TD3-F035-T117.1/.2` 承接。**保留**同文件「文件内重复 `ip`+`related_row`」「现存 `ip` 冲突 `field="ip"`」「大小写折叠合并」「`/30` `/31` `/32`、gateway、RESERVED」全部断言（零削弱） |
| `test_pg08_two_phase_consistency`（`conflict_rows` hostname=`cn001`, `role="GPU"` → `field="hostname"`；并断言既有 `role`/`version` 不变、无 UPDATE Audit） | 现存 hostname 冲突不覆盖 | **部分失效**：字段归因变为 `role`；「不覆盖 + 无 UPDATE Audit」判据仍必须成立 | 改为断言 `field=="role"`（宿主 `role=OTHER` vs 行 `GPU`，`related_row is None`），并**保留并加强**「既有 `role` 仍为 `OTHER`、`version==1`、`UPDATE` Audit 计数 == 0」。这两条现在由 `TD3-F035-T119.2/.9` + `T118.1/.3` 承接 |
| `test_pg11_write_revalidates_after_state_change`（预校验 0 错误 → 外部建同 hostname → 期望 422 `field="hostname"`） | 预校验后状态变化 → 失败 | **失效**（该行现在会按追加成功） | 改为两个更强用例：①外部占用 **IP** → 422 `field="ip"`（已有 `test_pg11b_*` 覆盖新建组；追加组变体见 `TD3-F035-T123.4`）；②外部在宿主上创建**同名 Interface** → 422 `field=="name"`（`TD3-F035-T123.3`）。另新增「外部建同 hostname → 按追加成功、既有 Resource 零变化」（`TD3-F035-T117.1` + `T118.*`），使 T69「再校验」语义在新口径下**不减弱** |
| `test_pg05a_concurrent_overlapping_hostname` | 两批新建同 hostname，恰一成功，败方 `field="hostname"` | **保留**（数据库兜底，架构 §3.5 / DR-F035-09） | 断言不变；F035 套件 `TD3-F035-V11.4` 复述同一判据（防止该归因被误删） |
| `test_pg05b_*` / `test_pg05c_*`（并发 IP 恰一成功、败方 `field="ip"`） | 并发唯一性归因 | **保留** | 断言不变；追加组变体见 `TD3-F035-V11.3` |
| `test_pg01/pg02/pg03/pg04/pg04b/pg07/pg09/pg10/pg12/pg13/pg14` | 新建路径、Network 解析、VM Host、整批回滚、权限/模板 | **不受影响** | 全绿即为 V10 证据；不改断言 |
| 文件 docstring / 注释（「Contract F023 v1」） | 版本引用 | 需更新 | 改为 v2 并注明 §8.1 二态（纯注释，不影响断言） |

**未被 F035 波及的既有套件（核对结论）**：`test_f034_csv_text_carrier.py` 中 3 处 `field=="hostname"` 断言（`test_td6_atom2_*`、`test_td3_t108_5_*`、`test_td3_t108_6_*`）与 `test_f034_csv_text_carrier_scope.py` 的 `field=="cluster"` 断言全部落在 **F014 资源导入端点**（`R_VALIDATE/R_WRITE = /imports/resources*`）或非法值/越权路径上，BQ04=A 下 F014 行为零变更 ⇒ **无需修改**；若 TEST 阶段出现失败，按 `TD3-F035-T126.1`/`T126.7` 判 FAIL 并定位（不得改断言绕过）。

### TD-7 数据完整性映射（data-integrity 口径）

| 规则依据及版本 | 作用域 / 入口 | 数据库保证 | 业务层保证 | 并发 / 生命周期边界 | 验证与证据 |
| --- | --- | --- | --- | --- | --- |
| §14 同 Cluster hostname 未删唯一（revision 14） | 新建组 | `uq_resources_cluster_id_hostname_key`（`deleted_at IS NULL`） | 二态判定 + `_attribute_integrity` 归因 | 预校验后并发插入 → 败方 `field="hostname"`、整批回滚 | `TD3-F035-V11.4`、`T126.2` |
| §24.6 / T120 宿主内未删同名 Interface | 追加 + 新建 | `uq_interfaces_resource_id_name` | **新增**只读批量检查（§3.3）+ `prepare_interface` | 并发同名 → 恰一成功、败方 `field="name"` | `T120.1/.2/.5`、`V11.1/.2` |
| §14 同 Cluster IP 未删唯一 | 两者 | `uq_ip_addresses_cluster_id_address` | 既有 IP 检查（保留）+ `prepare_ip_address` | 并发同 IP → 恰一成功、败方 `field="ip"` | `T120.3/.4`、`V11.3` |
| §11.1 / §9 CIDR 归属 | 两者 | `ck_ip_addresses_*`、`trg_ip_addresses_cidr_contains` | `ip_capacity` | `_lock_network` 串行化 | `T122.1/.6`、F023 `pg06/pg09` 回归 |
| §24.6 / T118 既有 Resource 零改动 | 追加组 | 无（不写即无变更） | 不 stage Resource、不赋值（避免 autoflush UPDATE） | `FOR UPDATE` 串行化 | `T118.1`–`.5`（含 `xmin`） |
| §22 每新建对象 CREATE Audit | 两者 | — | `stage_interface` / `stage_ip_address` | 回滚无残留 | `T118.3`、`T123.2` |
| BQ02 / BQ07 一致性比较 | 追加组 | 无 DB 约束（只读） | `_check_existing_consistency` | 预校验 → 写入二次比较 | `T119.1`–`.11` |
| §23.2 集群范围 | 两者 | — | 行级 `scope_filters`（沿用） | 未授权整批失败 | `T124.5/.6` |
| F023 v2 §12.3 确定性锁序（DR-F035-03） | 两者（混排） | — | 单语句 `resources` 并集 + `ORDER BY id`、SAVEPOINT 外 | 跨批反向集合不得 `40P01` | `V11.5` |

- **Database：`NOT_REQUIRED`**（架构 §5；无表/列/索引/约束/触发器/Migration）。本 TD 不主张「新增约束已验证」，改为验证 **零 Schema 漂移**：`backend/alembic/**` 与 `backend/app/models/**` 空 diff（`T126.7`）+ 既有三部分唯一索引存在性断言（`pg_indexes`/`pg_constraint` 名称在测试库中存在）。
- 追加能力**依赖**的三个部分唯一索引是本 Feature 并发兜底的唯一数据库保证；`T126.7` 与 `V11.*` 共同证明其充分性。

### TD-8 环境（设计期实测事实，非执行结果）

| 项 | 实测值（2026-10-26，本阶段只读核对） |
| --- | --- |
| 分支 / HEAD | `feature/F035-append-interface-ip`，HEAD **`9e80a7c`**（`76d8410..HEAD` 仅 docs 变更；`backend/**` 零 diff ⇒ 实现未开始） |
| 计划状态 | `project-plan.yaml`：F035 `current_stage=TEST_DESIGN`，`implementation.test_design=PENDING`，`layers={database:false,backend:true,frontend:true}`，`api_required=true`；`python3 scripts/validate_project_state.py` → `PROJECT STATE VALID` |
| PostgreSQL | `csmtest-db-1` = **PostgreSQL 16.15**，网络 `csmtest_default`；**宿主 `127.0.0.1:5432` 拒绝连接**（端口未发布） |
| 测试库 | `csmtest-db-1` 内只有 `csm` / `postgres` 库，**`csm_test` 不存在**；`.env.test` 的 `TEST_DATABASE_URL=postgresql+psycopg://csm:…@localhost:5432/csm_test` 与现场不符 → 见 PR-1 |
| 任务书所述 `csm-f026-pg` | 容器**不存在**（`docker ps -a` 无该项），任务描述的环境事实与现场不符 → TD-I-1 |
| `csmtest` 栈 | `nginx`(18080) / `backend`(healthy) / `db`(healthy) / `frontend` 均 Up；`admin`/`testadmin` 登录 **200**（ADMIN，含 `IMPORT`）；现有 Cluster `N96P`、Network `TESTNET 10.100.24.0/24` 与 `TEST 192.168.10.0/24`（ACTIVE）、Resource `luck`/`cn-ui-01`/`cn001`（均 BM）→ H 层只读追加探针有真实数据可用；**该栈为 F035 之前的镜像** ⇒ PR-2 |
| 宿主工具链 | Python 3.12.7、pytest 7.4.4、SQLAlchemy 2.0.34、FastAPI 0.115.14；Playwright(Python) + Chromium 已装（B 层可行）；`frontend/node_modules` 就绪（M 层可行） |
| 可用镜像 | `csm-csm-backend:test`、`csm-csm-frontend:test`（含 test stage，可作容器内 pytest 载体）、`postgres:16`（可作 PR-1 的独立测试实例） |
| 写入纪律 | 业务数据真实写在**仅在 `csm_test`**（pytest + `committed_engine` teardown `TRUNCATE`）；`csmtest` 栈只发登录 + 只读 `/validate`；不在生产或未知库执行测试（DB-D10 双守卫） |

**TEST 阶段命令（供 TEST 执行，本阶段未运行）**

```bash
# 1) F035 定向（真实 PG；PR-1 准备库后）
cd backend && TEST_DATABASE_URL='postgresql+psycopg://csm:<pw>@127.0.0.1:55432/csm_test' \
  PYTHONDONTWRITEBYTECODE=1 python3 -m pytest \
  tests/integration/test_f035_append_interface_ip_import.py \
  tests/integration/test_f035_append_scope.py -q -p no:cacheprovider

# 2) F023 更新后复跑（V10 / T126.2–T126.3）
… python3 -m pytest tests/integration/test_f023_resource_interface_ip_import.py -q -p no:cacheprovider

# 3) 回归定向（T126.1 / T126.4 / T126.2 / T67.2 / T71.1）
… python3 -m pytest tests/integration/test_imports.py tests/integration/test_import_tester_acceptance.py \
  tests/integration/test_import_constraints.py tests/integration/test_import_performance.py \
  tests/integration/test_f034_csv_text_carrier.py tests/integration/test_f034_csv_text_carrier_scope.py \
  tests/integration/test_f027_access_scope.py tests/integration/test_interfaces.py \
  tests/integration/test_interface_constraints.py tests/integration/test_ip_addresses.py \
  tests/integration/test_ip_address_constraints.py tests/integration/test_f019_interface_ip_binding.py \
  -q -p no:cacheprovider

# 4) 采集脚本零回归（T126.5：T73–T84 / T100–T106）
cd .. && python3 -m pytest scripts/test_collect_host_info.py -q -p no:cacheprovider

# 5) 前端三项（T126.8 / M 层）
cd frontend && npm run typecheck && npm run build && npm run smoke:client

# 6) 项目状态一致性（计划文件结构核对；不代表批准或 Git 证据有效）
cd .. && python3 scripts/validate_project_state.py

# 7) 静态零 diff 守卫（T126.7 / T71.2）
git diff --stat 76d8410..<候选HEAD> -- backend/app/models backend/alembic \
  backend/app/api/v1/imports.py backend/app/services/resource_import.py \
  backend/app/services/resource.py backend/app/services/interface.py \
  backend/app/services/ip_address.py backend/app/services/network.py \
  backend/app/services/ip_capacity.py docs/api/F002.md
git diff 76d8410..<候选HEAD> -- docs/api/F023.md | grep -E '^[-+].*(§6|import_max|IMPORT_|26 列)'

# 8) H 层真实 HTTP 只读（PR-2；脚本于 TEST 阶段新建）
CSM_BASE_URL=http://localhost:18080 CSM_USERNAME=admin CSM_PASSWORD=<test-only> \
  node docs/features/F035/artifacts/f035-live-validate.js

# 9) B 层浏览器（PR-2；沿用 F034 静态 dist + 转发真实后端方法）
python3 docs/features/F035/artifacts/f035-ui-browser-check.py
```

### TD-9 判定标准

| 结论 | 条件 |
| --- | --- |
| **PASS** | 用例实际执行并通过，断言、环境与证据（命令 + 日志/JSON）齐备；**V2/T118 类用例必须通过全部硬判据**，不接受「功能上等价」替代 |
| **FAIL** | 实测行为与 §24.6 / F023 v2 / DR-F035-* 不符（含 `field` 归因错、既有 Resource 任一列/`xmin`/`version`/`updated_at` 变化、出现 `resource` UPDATE Audit、残留数据、`40P01`、响应新增字段、模板/错误码/上限变化） |
| **BLOCKED** | 缺少必要输入或环境（PR-1 未就绪使 I 层全部不可执行；PR-2 未就绪只阻塞 H/B，**不得**因此阻塞 I 层判定） |
| **NOT TESTED** | 已设计但未执行（含无浏览器/无可达构建时的 B 层），必须写明原因与降级证据，不得折算为 PASS |
| **NOT_REQUIRED** | 仅用于本 TD 明确标注可免除项（如已批准的界面追加数展示在 DR-F035-11 下为禁止项而非免测项）；不得用于掩盖缺失验证 |

**「既有 Resource 零变化」硬判据（V2 门禁）**：①`resources` / `bare_metal_details` / `virtual_machine_details` / 既有 `interfaces` / 既有 `ip_addresses` 全列快照逐字段相等；②`xmin::text` 相等；③`version` / `updated_at` 相等；④`object_type='resource' AND action='UPDATE'` 计数 == 0；⑤`GET /resources/{host}/activity` 无 UPDATE；⑥`audit_logs` 增量恰等于新子对象数。任一条不满足 → 该用例 **FAIL**（不得整体降级为 MEDIUM 观察项）。

**写报告纪律**：每条验收给出「用例 ID → 层次 → PASS/FAIL/BLOCKED/NOT TESTED → 命令 + 证据路径」；缺陷按 `handoff.md` 格式（ID / Severity / Layer / Location / 证据 / 期望与实际 / 影响 / Owner / 是否必须修复）。

### TD-10 未验证项与降级边界（本阶段）

| 项 | 状态 | 说明 |
| --- | --- | --- |
| 全部验收测试（T117–T126 / V1–V12） | **NOT EXECUTED（设计阶段）** | 实现未开始（`backend/**` 零 diff），本阶段只做可验证性检查；不得引用为 PASS |
| I 层（真实 PG 集成） | 可行，**待 PR-1** | 需可达测试库；`TEST_DATABASE_URL` 缺失时 conftest 会 `skip`（= BLOCKED，不是 PASS） |
| H 层（真实 HTTP 只读） | 可行，**待 PR-2** | 当前栈为 F035 之前镜像；只读 `/validate` 在旧镜像上只能给出「hostname 冲突」的**基线**观察，不能作为追加证据 |
| B 层（浏览器） | 可行，**待 PR-2** | Playwright + Chromium 已在宿主；需候选 `frontend/dist` + 候选后端 |
| 5000 行性能基线（追加批） | **NOT TESTED（默认不跑）** | 契约未给数值阈值；F023 已记录新建批基线（validate≈37s / write≈219s）。F035 只在不违背「请求内加锁集合扩张」风险时按需抽测，并记录实际数字 |
| 前端「追加数 M 不展示」 | 可验证 | S：源码无追加计数变量/文案；B：成功提示文本不含 M，且 `created===0` 时显示定性说明（DR-F035-11）——两者缺一即 NOT TESTED |
| 整体上线验收（§32 跨功能） | 归后续整体验收 | 不得以 F035 局部 PASS 拼成整体 PASS（Agent 定义要求） |

### TD-11 记录项与待核对（不阻塞 TEST DESIGN，须在 TEST 报告登记实际行为）

| ID | 内容 | 处理 / Owner |
| --- | --- | --- |
| **TD-I-1** | 任务书所述环境事实与现场不符：`csm-f026-pg` 容器不存在；`csmtest-db-1` 内无 `csm_test`；宿主 5432 不可达；`.env.test` 的 `TEST_DATABASE_URL` 指向不可达地址 | 协调器在 TEST 前按 PR-1 提供测试库；本 TD 不断言具体实例，只要求「库名含 `test` 且 ≠ `DATABASE_URL`」 |
| **TD-I-2** | H/B 层需要候选后端构建在跑（当前 18080 为 F035 之前镜像） | 协调器决定重建栈或起候选只读后端（PR-2）；未获授权时 H/B 标 `NOT TESTED` |
| **TD-I-3** | `docs/database/f023-import.md` 未登记 F035 复核行（F023 v2 头部称已「定稿核对」该文件） | NOTE，Owner：Database / Architect；不影响本 TD（`layers.database=false`，以零漂移断言替代）。不在 Tester 修改范围 |
| **TD-I-4** | 组内多行**均**给出与被比较列不一致的值时，错误应落在哪些行号上，契约与 DR 未固定（DR-F035-08 只说 `(row, field)` 去重、`related_row=null`） | 断言限定为：**≥1 条** `field=<列>` 且其 `row` 属于该组，且无重复 `(row, field)`；实际行号集合登记在 TEST 报告，不据此判 FAIL，也不新增规则 |
| **TD-I-5** | `resource_type` 不一致时是否**同时**报该组其它不适用/不一致列，契约未固定（R4 已接受两套 `resource_type` 归因并存） | 只断言 `resource_type` 错误存在 + 整批 422 + 零残留；附加错误不断言、只记录 |
| **TD-I-6** | V12（预校验后宿主被软删 → 按新建）是**观察项**（R3），不是错误 | 只断言 `created==1`、新 id、原行仍软删且子对象不变；若实现改为报错，登记差异并交 Architect（不得自行改设计/断言） |
| **TD-I-7** | 实现命名可能与架构 §7.1 不同（`_check_existing_consistency` 等） | 按语义断言；缺语义或语义偏离 → FAIL 或交 Architect，并在报告登记实际符号名 |

### TD-12 结论

**`TEST DESIGN READY`**

- T117–T126（含修订后的 T67 / T71）共映射 **72** 条 `TD3-F035-*` 用例（T117–T126 = 61、T67/T71 = 4、V1 = 2、V11 并发 = 5），覆盖 U / I / H / M / S / B 六层；V1–V12 全部用例化，其中 V2 给出 6 条可机械判定的硬判据（含 PostgreSQL `xmin` 物理层证据），V11 给出 5 个真实 PG 双会话并发场景（含针对性锁环回归 `V11.5`），V10 给出 8 条零回归项与静态零 diff 守卫。
- 既有 F023 用例的 3 处期望失效已逐处列出替代方案（字段归因迁移 + 覆盖承接），2 处必须保留的加固断言（并发 hostname / IP 归因）明确保留；F034 / F027 / F014 既有断言经核对**不受影响**。
- 夹具、快照与审计判据、并发与清理策略、环境命令、降级边界与判定标准均已落定；`layers.database=false` 以零 Schema 漂移断言替代约束验证。
- 发现 2 个 TEST 前置条件（PR-1 测试库、PR-2 候选构建）与 7 条记录项（TD-I-1–7），**均不构成不可验证项**，因此不返回 `TEST DESIGN BLOCKED`；若 TEST 阶段 PR-1 未满足，I 层须整体标 `BLOCKED` 而非降级通过。
- `TEST DESIGN READY` 仅表示方案可验证；**不批准**实现、Contract 定稿或合并，也不替代 TEST 执行与正式 Review。

---

## 2. Test Execution

**NOT STARTED**（实现未开始：`76d8410..9e80a7c` 内 `backend/**`、`frontend/**` 零 diff）。本节将在实现完成、PR-1/PR-2 就绪后按 TD-8 命令与 TD-9 判定标准填写：Environment、验收映射执行结果（含数据库/接口/前端/集成）、Defects、未验证项与结论。

---

## Git

本阶段仅新建 `docs/features/F035/test-report.md`，未修改任何实现、Schema、契约、计划或既有测试；未执行任何 Git 写操作（无 `add` / commit / branch / merge）。

GIT: git rev-parse --short HEAD
GIT: git status --porcelain | head -30
GIT: git log --oneline -6
GIT: git diff --stat 76d8410..HEAD
GIT: git diff 76d8410..HEAD --stat -- backend/ docs/api/F002.md docs/api/F014.md
GIT: git diff 76d8410..HEAD -- docs/api/F023.md | grep -E "^[-+]" | grep -vE "^[-+]{3}" | head -40

（环境核对使用的非 Git 只读命令记录在 TD-8：`docker ps -a`、`docker images`、`docker exec csmtest-db-1 psql …`、`curl` 登录与 `GET /clusters|/networks|/resources`、`python3 scripts/validate_project_state.py`；均不改变 Git 或业务数据状态。）
