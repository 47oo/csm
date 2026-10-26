# F035 向既有 Resource 追加 Interface/IP 导入 — IMPLEMENTATION 阶段报告

- **状态**：BACKEND COMPLETE；FRONTEND COMPLETE；DATABASE NOT_REQUIRED（Database 复核确认）
- **版本**：v1（2026-10-26）
- **上游依据**：`docs/features/F035/architecture.md`（§12 定稿 `READY FOR IMPLEMENTATION`，§12.4 裁定）、`docs/api/F023.md` **v2**（READY，2026-10-26）、`docs/features/F035/test-report.md` §1 TEST DESIGN、requirements revision 14 §24.6 与 T117–T126、`docs/database/f023-import.md` §5。

## 1. Backend（BACKEND COMPLETE）

改动：`backend/app/services/resource_interface_ip_import.py`（主改）、`backend/tests/integration/test_f035_append_interface_ip_import.py`（新增 20 用例）、`test_f035_append_scope.py`（新增 2 用例，`real_scope`）、`test_f023_resource_interface_ip_import.py`（仅 3 处因 BQ01=B 失效的期望 + docstring，`test_pg05a/b/c` 保留）。

与 §7.1 第 1–11 项逐项对应（全部落地）：`ParsedRow.existing_resource_id`；`_parse_row` 删除 hostname 业务冲突分支（保留 IP 检查与校验顺序/错误文本/行号）+ `existing_cache`；`ExistingSnapshot` + `_load_existing_snapshots`（单条 `id.in_` + `selectinload`）；`_check_existing_consistency`（列集 = canonical `resource_cells` 键集、归一化标量比较、`related_row=None`、`(row,field)` 去重）；`_check_existing_interface_names`（单语句、大小写敏感、`field="name"`）；`parse_and_validate` 接入两检查（预校验/写入同口径）；`PreparedGroup.existing_resource_id` + 组内一致断言；`_acquire_locks` 单语句并入追加宿主（`ORDER BY id`、SAVEPOINT 外）；`write_import` 组内二态（跳过 `stage_resource`、不计数、不对既有 ORM 赋值）；docstring 补二态说明；零 diff 守卫成立。

**实现自由度登记（§12.4）**：
- TD-I-4 策略：对每个追加组的每一列，凡显式给出且与既有值不同的行**全部报出**（全列同一策略），`(row, field)` 全局去重，`related_row=None`，`reason=f"{column} does not match the existing resource value"`。
- TD-I-5 行为：`resource_type` 必报且归因 `resource_type`，同时报告该组其它显式给出且不符的列（如 BM 宿主上的 VM 行额外报 `host`）；整批 422、零残留。
- TD-I-7 实际符号：`ParsedRow.existing_resource_id`、`PreparedGroup.existing_resource_id`、`ExistingSnapshot`（含 `existing_value(column)`）、`_load_existing_snapshots`、`_check_existing_consistency`、`_check_existing_interface_names`、辅助 `_as_text` / `_HARDWARE_SNAPSHOT_COLUMNS` / `_VM_SNAPSHOT_COLUMNS`；`_parse_row(..., existing_cache=None)`。

**实际执行（真实 PostgreSQL 16.15，容器 `csm-f035-pg`，`TEST_DATABASE_URL=postgresql+psycopg://csm:csmtestpw@127.0.0.1:55432/csm_test`）**：

| 命令（`cd backend`） | 结果 |
| --- | --- |
| `pytest tests/integration/test_f035_append_interface_ip_import.py -q` | **20 passed** |
| `pytest tests/integration/test_f035_append_scope.py -q` | **2 passed** |
| `pytest tests/integration/test_f023_resource_interface_ip_import.py -q` | **28 passed**（含 5000 行 PERF 基线；用例数不减少） |
| `pytest tests/integration/test_imports.py -q`（F014 零回归） | **29 passed** |
| `pytest tests/integration/test_f034_csv_text_carrier*.py -q` | **31 passed** |
| `pytest tests/integration/test_import_tester_acceptance.py -q` | **9 passed** |
| `pytest scripts/test_collect_host_info.py -q` | **83 passed** |
| `git diff --name-only` 零 diff 守卫集合（models / alembic / api / 5 个 service） | 空输出 |

**F023 用例更新（3 处，均保留强度或加强）**：`test_pg06`（既有 hostname 行改为合法追加 + 保留文件内重复/现存 IP/折叠/边界断言）、`test_pg08`（`field` 由 `hostname` 改 `role` + 新增 hostname 不再报 + 保留既有值不变/`version==1`/无 UPDATE Audit）、`test_pg11`（改为外部建宿主 + 同名 Interface → `field="name"`，并新增零残留断言）。

## 2. Frontend（FRONTEND COMPLETE）

改动 3 文件：`ResourceInterfaceIpImportPanel.tsx`（标题 + 6 条追加规则提示块（复用 `InfoState`，无新增 CSS）+ `created===0` 定性说明、契约引用 v1→v2）、`ResourceImportPanel.tsx`（一行「资源导入不支持追加」说明）、`frontend/scripts/smoke-client.mjs`（F023 段契约引用 v1→v2、新增 2 条 F035 机制用例，wire 断言零改动，用例 337→339）。

覆盖 §7.3 十项文案要点：追加语义（只新增、不改既有资源字段）、Resource 级列三态（可填须一致/区分大小写、留空=省略不比较不置空、既有 null 不能补填）、既有同名网卡与同集群既有 IP 仍报错、不支持向既有网卡再加 IP、只提交新增行、VM 追加行 `host` 必填且须一致、`created===0` 定性说明且不展示追加数 M、F014 面板差异说明、不镜像服务端规则为权威、smoke 引用升版。

**实际执行**：`npm run typecheck` PASS；`npm run build` PASS；`npm run smoke:client` **339 passed, 0 failed**。浏览器（Playwright，1440/1024/768/375px，受控 mock）64 项交互+布局断言全 PASS（含 `created===0` 文案、无「追加 N」字样、无横向溢出、控制台无 error）；mock 证据由 TEST 阶段真实栈替换。

## 3. Database（NOT_REQUIRED 确认）

Database 复核结论 `DATABASE NOT_REQUIRED CONFIRMED`：四项判定成立（无 DDL/Migration；追加只需应用层；三条部分唯一索引足以兜底含软删与大小写；锁集合扩展仅应用层）；登记于 `docs/database/f023-import.md` §5（含零 Schema 漂移断言 A1–A5、索引兜底范围、未来触发 Schema 变更的 8 个条件、`F035-DB-NOTE-01` 排序规则确定性假设）。

## 4. 零改动确认

`backend/app/api/**`、`backend/app/models/**`、`backend/app/services/{resource_import,resource,interface,ip_address,network,ip_capacity}.py`、`backend/alembic/**`、`frontend/src/api/**`、前端依赖与主题：**零 diff**；`resource_import.py` 的 F014 hostname 冲突块保留（BQ04=A）。

## 5. 未验证项（交 TEST 阶段）

1. 真实栈 H 层（候选后端的 `/validate` 与写入）与 B 层浏览器：由 Tester 在重建后的 `csmtest` 栈执行。
2. 5000 行纯追加批性能基线：`NOT TESTED`（F023 PERF 新建批已通过；追加新增 3 条只读查询）。
3. V5/V6 的追加路径独立用例：规则复用同一 Service Layer 内核，证据来自 F023 回归 + 追加用例落库断言。
