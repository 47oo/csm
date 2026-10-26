# F022 Resource 详情页 IP Addresses 区域 — TEST REPORT

- **版本**：TD-1（TEST DESIGN）；执行结果见后续 `# Test Execution` 小节
- **日期**：2026-10-15

## TEST DESIGN

- **结论**：`TEST DESIGN READY`
- **依据**：`docs/product/requirements-v3.md` revision 7 §18/§32/§13/§14/§12/§21/§23/§17.1；`docs/features/F022/product.md` v1（A1–A7）；`docs/features/F022/architecture.md`（DR-382–DR-400；layers{database:false,backend:false,frontend:true}；api_required=false；Contract NOT_REQUIRED）；`docs/api/F007.md` §4/§6.1、`docs/api/F010.md` §3/§4/§5/§6.1；现状前端。
- READY 仅表示方案可验证，不代表测试通过、不批准实现或合并。PROPOSED 项按可观察行为判定，不锁定数字/命名。

### 0. 数据完整性（无 Schema 变更）
| 规则依据 | 入口 | 既有保证 | 验证 |
| --- | --- | --- | --- |
| §14 归属/同 Cluster | 只读 | `uq_ip_addresses_cluster_id_address`、`trg_ip_addresses_interface_cluster`（未改） | T04/T10 |
| §21 软删默认隐藏 | 接口/IP 列表 | `deleted_at` 部分索引 | T04/T08、P2–P4 |
| §13 关系 | 逐接口查询 | FK `ip_addresses.interface_id` | T04、P3 |
| §23 权限/只读 | GET 列表 | 服务端权威 | T05/T13、P7 |
| §22 Audit | 只读 | 无写入 | T10、P6 |

无表/列/约束/索引/迁移；无需 Database Gate。

### 1. 验收映射（A1–A7）
层次：STATIC / MECH（smoke）/ PG（真 PostgreSQL）/ BROWSER（人工）。
| 测试项 | 验收 | 层次 | 预期 |
| --- | --- | --- | --- |
| F022-T01 | A1 | STATIC+MECH+PG+BROWSER | 行含 address / network(name,cidr) / interface.name / ip_pool(池外「池外（手动）」) / description(「—」)；无 cluster 列 |
| F022-T02 | A2 | MECH+PG+BROWSER | 跨接口多 IP 全展开；排序 interface.name→IP 数值→id |
| F022-T03 | A3 | MECH+BROWSER | 无绑定 IP 显式空态（Empty≠Error） |
| F022-T04 | A4 | PG+MECH | 未绑定/已删 IP、已软删 Interface 上的 IP 不出现 |
| F022-T05 | A5 | STATIC+MECH+PG+BROWSER | 无写入口；VIEWER/EDITOR 内容一致（READ） |
| F022-T06 | A6 | MECH+BROWSER | 全失败 ErrorState 可重试、不伪装空；部分失败保留成功行+警告；截断显式提示 |
| F022-T07 | A7 | STATIC+PG | F019 每接口「已绑定 IP」无回归；`interfaceIpSelection.ts`/`InterfacesPanel.tsx` 未修改 |
| 补充 | T08 接口分页取全 | | 逐页取全、超安全上限显式提示 |
| 补充 | T09 部分失败 | | 不折叠为整体成功 |
| 补充 | T10 只读无副作用 | | audit_logs/version 不变 |
| 补充 | T11 无新端点/参数 | | 仅复用 F007/F010；拟新增路径 404 |
| 补充 | T12 挂载点 | | 移除 IP 占位、挂载新组件 |
| 补充 | T13 角色一致 | | 三角色同集 |
| 补充 | T14 边界三态 | | truncated/complete/empty |
| 补充 | T15 标签 | | 池外/「—」不以空串代替 |

### 2. 静态断言（S1–S5）
- S1 `ResourceDetailPage` 无 `IP 地址（IP）` 占位、含 `<ResourceIpAddressesPanel resource user />`。
- S2a 新组件无写控件（无 create/autoAllocate/update/release/restore 调用、无表单/分配按钮）；S2b 无 cluster 列；S2c 无 VIEW_DELETED 开关、仅 `deleted=exclude`。
- S3 `interfaceIpSelection.ts`、`InterfacesPanel.tsx` 与基线一致（仅 import 两个既有导出）。
- S4 `api/ipAddresses.ts`、`api/interfaces.ts` 无新增导出。
- S5 `resourceIpAddresses.ts` 无 react/JSX import，可被 Node 加载。

### 3. 机制级 smoke（M1–M7）
- M1 `buildResourceInterfacesQuery`：`resource_id`+`deleted=exclude`+`sort=name`+`order=asc`+`page_size≤100`。
- M2 逐接口 IP 查询与 `buildInterfaceBoundIpsQuery` 深相等（`interface_id`+`deleted=exclude`+`sort=address`+`order=asc`+`page_size=100`）。
- M3 合并行数 = Σ 各接口 IP 数；归属正确；软删接口不产生行。
- M4 比较器全序：interface.name 码序（含大小写）→ IP 数值（跨网段）→ id 兜底。
- M5 边界三态（复用 `interfaceIpTotalBoundary`）；聚合任一 truncated 即 truncated。
- M6 部分失败汇总：全失败→Error；部分失败→成功行+失败清单+警告；不折叠；重试重取全部。
- M7（若纯模块导出标签）ip_pool=null→「池外（手动）」、description=null→「—」。

### 4. 真 PG 集成（P1–P9）
夹具：C1/R/多 Interface（I1/I2 未删、I3 软删）、IP（a1–a3→I1、a4→I2、a5 未绑定、a6 已删绑 I1、a7 绑软删 I3）。
- P2 接口查询仅 I1/I2；P3 I1 返回 a1–a3、I2 返回 a4，a6 不出现；P4 合并 = {a1,a2,a3,a4}；P5 排序正确；P6 只读无副作用（audit_logs/version 不变）；P7 三角色一致；P8 F019 回归；P9 无新端点/参数。

### 5. 人工浏览器清单（B-1–B-8）
区域渲染与列、排序、空态、错误可重试、截断提示、无写按钮、VIEWER/EDITOR 一致、F019 展开正常。

### 6. 不可验证项
| 编号 | 项目 | 处理 |
| --- | --- | --- |
| F022-UNV-1 | 真实浏览器 DOM 渲染/布局/可访问性 | NOT TESTED；替代=机制级+typecheck+build+静态+真 PG |
| F022-UNV-2 | 浏览器驱动端到端 | NOT TESTED |
| F022-UNV-3 | DR-383/389/392/398/400 PROPOSED | 按可观察行为判定，不锁定数字/命名 |
| F022-UNV-4 | 大接口数×大 IP 数性能基线 | NOT TESTED |

### 7. 环境与夹具
前端 `typecheck`/`build`/`smoke:client`；真 PG（`compose.test.yaml` -p csmtest + `TEST_DATABASE_URL`）；复用 F019/conftest helper。

### 8. 结论
`TEST DESIGN READY`（TD-1）。无 Database Gate、Backend/Contract NOT_REQUIRED、无 Blocking 项。

---

# Test Execution

- **版本**：EXEC-1（Tester，TEST 模式）；被测实现提交 `e5ed063`
- **结论**：`READY FOR REVIEW`
- **保留上游**：TEST DESIGN TD-1 未修改（见上）。

## 1. Task / Basis

- **Task**：F022「Resource 详情页 IP Addresses 区域」独立验证（TEST），只读检查生产实现 + 新增测试/Fixture；不修改生产实现。
- **Basis**：`requirements-v3.md` revision 7 §18/§32/§13/§14/§12/§21/§22/§23/§17.1；`docs/features/F022/product.md` v1（A1–A7）；`docs/features/F022/architecture.md`（DR-382–DR-400；§10 签核 `READY FOR IMPLEMENTATION`，Contract `NOT_REQUIRED`）；`docs/features/F022/test-report.md` TD-1；`docs/api/F007.md` §4/§6.1、`docs/api/F010.md` §3/§4/§5/§6.1；实现提交 `e5ed063`。

## 2. Environment

| 项 | 值 |
| --- | --- |
| 工作区 | `/home/hanhao/github/47oo/csm`，分支 `feature/F022-resource-detail-ip-area`，HEAD `e5ed063` |
| 工作区状态 | `git status --porcelain` 仅 `?? backend/tests/integration/test_f022_resource_ip_area.py`（本 Tester 新增测试）；生产源零改动 |
| 前端 | Node v24.14.0；`typecheck`/`build`/`smoke:client`；无 vitest/jsdom/testing-library；无浏览器/E2E 工具（Playwright/Cypress 均未安装） |
| 后端 | 镜像 `csm-backend-f019test:latest`（`93eba2717ef9`，`docker build --target test`，含本测试）；真 PG `csmtest-db-1`（`postgres:16`，`PostgreSQL 16.15`，network `csmtest_default`，host `db`），库 `csm_test` |
| 安全护栏 | 测试库名含 `test`（`csm_test`）且 `TEST_DATABASE_URL != DATABASE_URL`（conftest DB-D10）；未使用 SQLite/Mock 作约束证据 |

## 3. 静态断言 S1–S5（独立执行）

| 断言 | 证据 | 结果 |
| --- | --- | --- |
| S1 | `ResourceDetailPage.tsx` 无 `IP 地址（IP）`/`PLACEHOLDER_AREAS`/`placeholder-areas`（grep 命中 0，占位容器与标题已移除）；L25 import、L674 `<ResourceIpAddressesPanel resource={state.resource} user={user} />` | PASS |
| S2a | 新组件/纯模块无写控件：`grep -nE 'createIpAddress|autoAllocate|updateIpAddress|releaseIpAddress|restoreIpAddress|<form|Form\.'` 命中 0；`<Button>` 仅 2 处，均为「重试」（`setReloadToken`），无分配/绑定/解绑/释放入口；import 仅为 `ui/controls`、`ui/feedback`、`api/*` 的 `list*` 读函数 | PASS |
| S2b | 无 cluster 列：`<thead>` 恰 5 列 = address / network / interface / ip_pool（来源）/ description；`cluster` 仅出现在注释 | PASS |
| S2c | 无 VIEW_DELETED 开关：新组件/纯模块 `grep` 无 `VIEW_DELETED` 标识符；`deleted` 仅 `"exclude"`（`resourceIpAddresses.ts:61` 等），无 `include`/`only` | PASS |
| S3 | `git diff e5ed063^ e5ed063 -- frontend/src/components/interfaceIpSelection.ts frontend/src/components/InterfacesPanel.tsx` 输出 0 行（零改动，仅 import 两个既有导出） | PASS |
| S4 | `git diff e5ed063^ e5ed063 -- frontend/src/api/` 输出 0 行；`git show --stat e5ed063` 变更文件不含 `src/api/*`（无新增导出） | PASS |
| S5 | `resourceIpAddresses.ts` grep `from "react|from 'react|\.tsx|jsx` 仅注释内 `ResourceIpAddressesPanel.tsx` 字样，无 react import/JSX；纯模块经 `smoke:client` 由 Node type stripping 直接加载 | PASS |

## 4. 前端三命令（独立复跑，`e5ed063`）

| 命令 | 结果 |
| --- | --- |
| `cd frontend && npm run typecheck` | PASS（`tsc --noEmit` 退出码 0，无输出） |
| `cd frontend && npm run build` | PASS（`✓ built in 20.60s`；`dist/assets/index-*.js` 1228.91 kB、`index-*.css` 14.11 kB） |
| `cd frontend && npm run smoke:client` | **306 passed, 0 failed** |

> 以上仅证明静态与机制级契约，不构成浏览器交互正确性证据。

### 4.1 smoke M1–M7 核对

| 用例 | 结果 |
| --- | --- |
| M1 接口查询恰含 resource_id/deleted=exclude/sort=name/order=asc/page/page_size=100，经 `listInterfaces` 序列化 | PASS |
| M2 逐接口 IP 查询与 F019 `buildInterfaceBoundIpsQuery` 深相等 | PASS |
| M3 合并行数 = Σ 各未删接口 IP 数；归属正确；软删/失败接口不产生行 | PASS |
| M4 比较器全序（interface.name 码序含大小写 → IP 数值跨网段 → id 兜底，含反对称性核对） | PASS |
| M5 边界三态 + 聚合任一 truncated 即提示 + 接口列表超安全上限即 truncated | PASS |
| M6 部分失败汇总（全失败→allFailed；部分→anyFailed；不折叠） | PASS |
| M7 ip_pool=null→「池外（手动）」、description=null→「—」 | PASS |

## 5. 真 PG 集成（P1–P9，独立执行）

新增 `backend/tests/integration/test_f022_resource_ip_area.py`（8 用例）。命令：

```
docker run --rm --network csmtest_default \
  -e TEST_DATABASE_URL='postgresql+psycopg://csm:***@db:5432/csm_test' \
  -e DATABASE_URL='postgresql+psycopg://csm:***@db:5432/csm' \
  -e PYTHONDONTWRITEBYTECODE=1 csm-backend-f019test \
  pytest tests/integration/test_f022_resource_ip_area.py -q -p no:cacheprovider
```

结果：**8 passed**（21.03s）。夹具：C1/R；I1=`eth0`/I2=`ib0` 未删、I3=`old0` 软删；a1(10.0.0.10)→I1、a2(10.0.0.9)→I1、a3(10.0.0.100)→I1、a4(10.0.0.50)→I2、a5(10.0.0.200) 未绑定、a6(10.0.0.77) 绑 I1 后软删、a7(10.0.0.88) 绑 I3 后 SQL 软删 I3。

| 项 | 断言 | 结果 |
| --- | --- | --- |
| P1 | 夹具可构造：接口 `deleted=exclude` 见 I1/I2、`deleted=only` 见 I3；a6 `deleted=true` 显示已删；a7 仍绑 I3 | PASS |
| P2 | `/interfaces?resource_id&deleted=exclude&sort=name&order=asc` total=2、items=[eth0, ib0]，I3 不出现（服务端权威） | PASS |
| P3 | `interface_id+deleted=exclude+sort=address`：I1→[a2, a1, a3]（数值升序 9<10<100）、I2→[a4]；a6 不出现；A1 字段 address/network{name,cidr}/interface{name}/ip_pool=null/description 正确 | PASS |
| P4 | 按前端算法合并可见集合 = {a1,a2,a3,a4}；a5/a6/a7 均不出现 | PASS |
| P5 | 排序 = [eth0/9, eth0/10, eth0/100, ib0/50]（interface.name→IP 数值→id） | PASS |
| P6 | 执行接口+IP+合并读路径后 `ip_address`/`interface` audit_logs 计数不变，IP a1–a4 与接口 I1–I3 的 `version` 不变 | PASS |
| P7 | VIEWER/EDITOR/ADMIN 的接口集合与合并可见集合完全一致 = {a1,a2,a3,a4} | PASS |
| P8 | F019 回归：`pytest tests/integration/test_f019_interface_ip_binding.py tests/integration/test_ip_addresses.py` → **52 passed**（69.80s） | PASS |
| P9 | 拟新增路径 `/resources/{id}/ip-addresses`、`/resources/{id}/ips`、`/interfaces/{id}/ip-addresses`、`/interfaces/{id}/bind-ip` 均 **404**；既有端点未列参数被忽略仍 200 | PASS |

### 5.1 全量后端回归（真 PG）

命令：

```
docker run --rm --network csmtest_default \
  -e TEST_DATABASE_URL='postgresql+psycopg://csm:***@db:5432/csm_test' \
  -e DATABASE_URL='postgresql+psycopg://csm:***@db:5432/csm' \
  -e PYTHONDONTWRITEBYTECODE=1 csm-backend-f019test \
  pytest tests/ -q -p no:cacheprovider
```

结果：**672 passed, 2 skipped**（813.05s）。相对 F021 报告基线（664 passed, 2 skipped）恰增本模块 8 个用例，无回归。跳过项与 F022 无关：`test_f016_acceptance.py:50`（`F016_ACCEPTANCE=1` 才启用）、`test_migrations.py:105`（连接角色 `csm` 为 superuser，DB-D11）。

## 6. 验收映射 A1–A7

层次：STATIC / MECH（smoke）/ PG（真 PG）/ BROWSER（人工，无工具）→ NOT TESTED + 替代证据。

| 验收 | 层次与证据 | 结果 |
| --- | --- | --- |
| A1 字段最小集 address/network(name,cidr)/interface/ip_pool(池外「池外（手动）」)/description | STATIC 列头（S2b）；MECH M7；PG P3 | **PASS**（B-1/B-2 NOT TESTED） |
| A2 跨接口多 IP 全展开 + 确定性排序 | MECH M3/M4；PG P4/P5 | **PASS** |
| A3 无绑定 IP 显式空态（Empty≠Error） | STATIC（`state.rows.length===0`→`EmptyState`，与 `ErrorState` 分支分离）；MECH M5（empty 边界） | **PASS**（B-3 NOT TESTED） |
| A4 不展示未绑定/已删 IP、默认不展示绑软删 Interface 的 IP | MECH M3；PG P2/P3/P4 | **PASS** |
| A5 只读无写入口；VIEWER/EDITOR 内容一致 | STATIC S2a；PG P6/P7 | **PASS**（B-6/B-7 NOT TESTED） |
| A6 全失败 Error 可重试、不伪装空；部分失败保留成功行+警告；截断显式提示 | STATIC（ErrorState+重试 / WarningState / InfoState 分支）；MECH M5/M6 | **PASS**（B-4/B-5 NOT TESTED） |
| A7 F019 每接口「已绑定 IP」无回归 | STATIC S3（零 diff）；PG P8 | **PASS**（B-8 NOT TESTED） |

## 7. 人工浏览器清单 B-1–B-8

仓库无 DOM/E2E 工具（未安装 Playwright/Cypress/jsdom/testing-library），无法执行真实浏览器验证：

| 编号 | 项目 | 结果 | 替代证据 |
| --- | --- | --- | --- |
| B-1 | 区域渲染与列 | NOT TESTED | 静态列头 S2b + MECH M7 + PG P3 字段 |
| B-2 | 排序 | NOT TESTED | MECH M4 + PG P5 |
| B-3 | 空态 | NOT TESTED | 静态 EmptyState 分支 + MECH M5 |
| B-4 | 错误可重试 | NOT TESTED | 静态 ErrorState+重试 + MECH M6 |
| B-5 | 截断提示 | NOT TESTED | 静态 InfoState + MECH M5 |
| B-6 | 无写按钮 | NOT TESTED | 静态 S2a |
| B-7 | VIEWER/EDITOR 一致 | NOT TESTED | PG P7 |
| B-8 | F019 展开正常 | NOT TESTED | 静态 S3 + PG P8 |

> 以上替代证据不构成真实浏览器 DOM/布局/可访问性证据；`F022-UNV-1`/`F022-UNV-2`/`F022-UNV-4` 维持 NOT TESTED。

## 8. Defects

无实现缺陷（None）。

| ID | Severity | Layer | Location | 证据/复现 | 期望 vs 实际 | 影响 | Owner | 必须修复 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| F022-NOTE-1 | NOTE | Frontend | `frontend/src/index.css`（`.placeholder-areas`/`.placeholder-box`） | 占位移除后成为死样式（实现报告已记录） | 期望后续统一清理 vs 当前保留 | 无功能/验收影响 | Frontend（非本 Feature 必做） | 否 |

## 9. 未验证项 / Next

- `F022-UNV-1`/`F022-UNV-2`：真实浏览器 DOM 渲染/布局/可访问性、浏览器驱动端到端 — **NOT TESTED**（无工具），替代见 §7。
- `F022-UNV-4`：大接口数×大 IP 数性能基线 — **NOT TESTED**（无基准运行）。
- `F022-UNV-3`（DR-383/389/392/398/400 PROPOSED）：按可观察行为判定，未锁定上限值/并发数/命名；P6/P9 已覆盖其可观察语义。
- Next：交协调器进入正式 Review；Review 需覆盖本测试代码（`test_f022_resource_ip_area.py`）。

## 10. 结论

`READY FOR REVIEW`（EXEC-1）：S1–S5、M1–M7、P1–P9 全部 PASS；A1–A7 全部 PASS（浏览器 B-1–B-8 因无工具显式 NOT TESTED 并以机制级/静态/真 PG 替代）；无必须修复缺陷；Backend/Database/Contract NOT_REQUIRED 已由无新端点（P9）与零 diff（S3/S4）独立佐证。

GIT: git status --porcelain
GIT: git branch --show-current
GIT: git log --oneline -12
GIT: git log --oneline -20 -- frontend/src/components/resourceIpAddresses.ts frontend/src/components/ResourceIpAddressesPanel.tsx frontend/src/pages/ResourceDetailPage.tsx
GIT: git show --stat e5ed063
GIT: git show e5ed063 -- frontend/src/components/interfaceIpSelection.ts frontend/src/components/InterfacesPanel.tsx
GIT: git show --stat e5ed063 -- frontend/src/api/
GIT: git diff e5ed063^ e5ed063 -- frontend/src/components/interfaceIpSelection.ts frontend/src/components/InterfacesPanel.tsx
GIT: git diff e5ed063^ e5ed063 -- frontend/src/api/
GIT: git rev-parse --short HEAD