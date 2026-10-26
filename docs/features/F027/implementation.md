# F027 服务端访问范围强制执行 — Implementation

- 状态：BACKEND COMPLETE
- 依据：`docs/features/F027/product.md`、`docs/features/F027/architecture.md`、`docs/api/F027.md`、requirements revision 11 §23.2
- 范围：仅后端实现与后端测试；未修改 `docs/api`、F026 语义、前端、计划或产品/架构文档
- Schema/Migration：无变更；无新端点、参数、权限项或 error code

## 1. 实现文件

新增：

- `backend/app/services/scope_filters.py`：范围谓词辅助。`scope=None` 仅供内部/测试直调，等价 ADMIN；HTTP 路径始终注入真实 `AccessScope`。
- `backend/tests/integration/test_f027_access_scope.py`：真实 PostgreSQL 的 F027 集成测试。

修改：

- `backend/app/api/v1/{clusters,resources,networks,ip_addresses,ip_pools,interfaces,services,service_endpoints,search,dashboard,imports}.py`
  - 所有相关读写端点通过 `Depends(get_access_scope)` 注入 F026 `AccessScope`，作为 keyword 传给 Service；无第二解析器/缓存。
- `backend/app/services/{cluster,resource,network,ip_address,ip_pool,interface,service,service_endpoint}.py`
  - list/get/activity/write 入口接收 `scope`，对象取回使用同一范围谓词；写路径先做范围取回（不可见 404），再做版本/唯一性/重叠/引用检查。
  - 创建/更新时请求体 Cluster / Network / Resource / Service / Interface 父对象使用范围校验；不可见按既有字段返回 422，消息不区分不存在/已删/未授权。
- `backend/app/services/search.py`
  - 四类候选查询、F018 关联行、`related_total`、`total` 全部按范围过滤；匹配、去重、排序、分页、字段组合未改。
- `backend/app/services/dashboard.py`
  - `counts`、`networks` items/total 按范围过滤；容量只对已过滤 Network 调用，公式未改；零授权返回全 0/空 200。
- `backend/app/services/resource_import.py`、`backend/app/services/resource_interface_ip_import.py`
  - 行级预校验先校验 Cluster/Network/Host 范围，再执行既有字段与完整性校验；范围错误聚合为行错误（row/field/reason），不输出未授权标识；存在范围错误时 write 整批失败、无残留。模板、列集、上限、两步流程未改。
- `backend/tests/conftest.py`
  - 对 F027 之前的集成测试套件，在 `auth_app` 中覆盖 `get_access_scope` 为 unrestricted，以保留旧 Feature 测试对“默认全量可见”的假设；F026 授权套件与 F027 范围套件不覆盖，继续断言真实范围规则。该覆盖仅为测试夹具，不改变生产行为。

## 2. 行为覆盖

- 列表：8 类对象 items 与 total 使用同一谓词；未授权 Cluster 过滤值返回空 200；无“空页 total>0”。
- 归属：Cluster/Resource/Network/IPAddress 直接按 `cluster_id`；Interface/IPPool/Service 通过父 Resource/Network EXISTS；ServiceEndpoint 通过 Service→Resource EXISTS；未绑定 IP 仍按其 `cluster_id`。
- 详情/Activity：先范围取回，不可见或不存在 404，不返回对象字段。
- 写：创建/修改/删除/释放/恢复/分配/绑定/解绑/转移先范围取回当前对象；请求体未授权 Cluster/父对象 422；未授权写不产生业务状态、Audit 或 Activity。
- 错误顺序：保持 401→403→422→404→409；范围校验先于唯一性/重叠/引用检查。
- ADMIN：`AccessScope.unrestricted=True`，不受范围限制；非 ADMIN 零授权默认拒绝。
- 授权生命周期：逐请求解析；撤销、角色变更、API Key 绑定账号变化在下一请求立即生效；INACTIVE 不改变授权；Cluster 软删后范围失效、恢复后原授权自动恢复。
- Q1：EDITOR 创建 Cluster 的既有行为未改变；新 Cluster 不自动授予非 ADMIN。

## 3. 验证

环境：

```bash
cd backend
export TEST_DATABASE_URL='postgresql+psycopg://csm:***@127.0.0.1:55432/csm_test'
unset DATABASE_URL
```

已执行：

```bash
python -m pytest tests/integration/test_cluster_authorizations.py -q
# 8 passed

python -m pytest tests/integration/test_f027_access_scope.py -q
# 9 passed

python -m pytest tests/integration/test_cluster_authorizations.py tests/integration/test_f027_access_scope.py -q
# 17 passed

python -m pytest tests -q
# 716 passed, 1 failed, 2 skipped in 1609.55s
# 唯一失败为 test_ip_addresses.py::test_concurrent_gateway_change_and_allocation 并发时序抖动；
# 单独重跑该测试：1 passed。
```

F027 集成测试覆盖：8 类对象列表/详情/Activity、items/total 一致、未授权过滤空 200、零授权全 0/空、8 类详情/写 404、创建请求体 422、搜索四类候选 + F018 related/related_total + total、Dashboard counts/networks、F014/F023 导入行错误与整批回滚无残留、API Key 继承、撤销/角色变更下一请求生效、Cluster 软删/恢复、401→403→422→404→409、拒绝写无 Audit/状态变化、ADMIN 不受限。

后续一次完整套件复跑在 80% 进度时因执行窗口超时被终止；终止前无失败输出，未将其计为完整通过证据。

## 4. 偏差与未验证项

- 为让 F027 之前的历史 Feature 测试继续验证其自身规则，新增了测试兼容 fixture（见 §1）；生产代码没有默认全量回退。
- 未修改前端；F028 的真实 Compose 端到端、页面空态/404/错误表现与 T85–T99 全量验收不在本任务执行范围。
- 未执行 F016 真实部署验收（环境中未启用 `F016_ACCEPTANCE=1`）。
- 完整套件最后一次复跑超时，最新全量通过证据以 §3 的 716 passed 记录为准。

GIT: NONE
