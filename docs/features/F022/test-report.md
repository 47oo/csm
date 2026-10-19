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