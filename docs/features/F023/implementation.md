# F023 资源+网卡+IP 批量导入 — IMPLEMENTATION 报告

- **版本**：v1（2026-10-15）
- **结论**：`BACKEND COMPLETE` + `FRONTEND COMPLETE`；Database / Contract 依各自 Gate（database NOT_REQUIRED；contract READY docs/api/F023.md）

## Backend
严格按 `docs/api/F023.md` v1 实现。

### 改动文件
| 文件 | 变更 |
| --- | --- |
| `app/services/interface.py` | 抽 `prepare_interface`（锁定 Resource、parent、同名唯一）与 `stage_interface`（add/flush + CREATE Audit staging）；`create_interface` 退化为薄包装，校验顺序/错误码/响应不变（DR-417） |
| `app/services/ip_address.py` | 抽 `prepare_ip_address`（resolve/lock Network、ACTIVE、§11.1、可选 `interface_id` 经 `_validate_interface` 同 Cluster、同 Cluster 唯一、`_derive_ip_pool_id`）与 `stage_ip_address`（CREATE Audit staging）；`create_ip_address` 退化为薄包装（DR-418） |
| `app/services/resource_interface_ip_import.py`（新） | 26 列统一宽模板（冻结列名/顺序/applies_to）、严格表头匹配、CSV/xlsx 复用 F014 原语、Network 解析（name_key→CIDR→`/mask`，不回退）、分组合并/组内一致性、文件内重复与现存冲突、写入前再校验、确定性锁序（resources→networks，id 升序，SAVEPOINT 外）、单事务 + 资源组 SAVEPOINT、DB 约束归因（含触发器按 RAISE 文本）、40P01 整批回滚 500 |
| `app/schemas/imports.py` | 新增模板/响应 schema（含 `applies_to`、`UnifiedImportWriteResponse`）；F014 schema 未改 |
| `app/api/v1/imports.py` | 新增三路由挂现有 `imports.router`：`GET .../templates`(READ)、`POST .../validate`(IMPORT)、`POST ...`(IMPORT,201)；不改 F014 端点 |

### Contract 符合性
§1/§1.1/§1.2（401→403→format→size→parse→rows→header→逐行；4 个 `IMPORT_*` + 既有码复用，不新增）；§2（multipart file+format，上限复用）；§3/§4/§5 响应；§6/§6.1/§6.2（26 列、BM/VM 逐行、三元组必填、省略/默认）；§7/§8（解析/行号/分组/组内一致性）；§9（Network 解析优先级、落库剥离）；§10/§11；§12.1–§12.5（原子性/再校验/确定性锁序/40P01/约束归因，吸收 F023-DB-01/02）；§15（F014/F007/F010 无回归）。

### 验证
| 命令 | 结果 |
| --- | --- |
| `docker build --target test -t csm-backend-f019test ./backend` | 成功 |
| 真 PG `pytest tests/ -q`（`csm_backend-f019test` + `csmtest_default`） | **672 passed, 2 skipped**（F004/F007/F010/F014 无回归；实现后与修正后各一次） |
| 端到端自检（非独立测试替代） | Happy path `(created,interfaces,ip,total)=(2,2,3,3)` 且落库剥离掩码/绑定正确；组内一致性报 `row=3,field=role,related_row=2`；越界整批回滚无残留；`/mask` 无匹配报 `field=ip`；VM 批外 Host 成功、批内新建 BM 作 Host 报 `field=host` |

### 未验证项
5000 行性能基线、并发重叠 hostname/IP、预览截断、xlsx 路径与 API 权限/CSRF 用例 → 交 TEST。

## Frontend
按契约实现第三套导入面板；不改 F014 面板行为。

### 新增
- `src/components/ResourceInterfaceIpImportPanel.tsx`：两步流程、四态、确认门控、无部分成功语义。
- `src/components/resourceInterfaceIpImportForm.ts`：纯逻辑（本地反馈/指纹/门控/26 列表头文本）。
- `src/components/ImportErrorsTable.tsx`：自 F014 逐字抽取的行错误表（共享）。

### 修改
- `src/api/imports.ts`：F023 三端点函数/类型；`describeImportError` 增可选 `scope`（默认保持 F014 文案）。
- `src/components/ResourceImportPanel.tsx`：改用共享 `ImportErrorsTable`（行为不变）。
- `src/pages/ResourcesPage.tsx`：新增「资源+网卡+IP 批量导入…」入口（仅 IMPORT）。
- `src/index.css`：模板表头最小样式。
- `scripts/smoke-client.mjs`：+13 F023 机制级用例。

### 验证
| 命令 | 结果 |
| --- | --- |
| `npm run typecheck` | 通过 |
| `npm run build` | 通过 |
| `npm run smoke:client` | **319 passed, 0 failed**（基线 306 + 13；F014 既有 17 用例回归） |

### 未验证项
浏览器 DOM/E2E（无工具）→ NOT TESTED；真实 API 端到端（联调）→ 交 TEST；templates 端点 401/500 分支由通用 client 机制覆盖。

## 备注
- 本会话工具链在工作区生成了未跟踪目录 `.agents/`（非 CSM 交付物，不纳入提交）。
- 未新增 config 设置、错误码、依赖。