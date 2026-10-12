/**
 * F002 前端 client 机制级冒烟（对应 docs/features/F002/test-report.md TD-2 §3
 * 「前端机制级：client 对 401/403/409 的处理用例，以受控响应对 src/api/client.ts 断言」）。
 *
 * 覆盖判据：
 * - credentials: "include"（csm_session Cookie 载体，Contract §2）；
 * - 统一错误信封解析（§1.1），形状不符时回退且不伪造信封内容；
 * - 401 触发全局处理器（清登录态回登录页），403/409 携带 code/details 明确呈现；
 * - 任何失败都不自动重试（每个用例断言 fetch 恰好调用一次）。
 *
 * F003 追加（对应 docs/features/F003/test-report.md TD-1 V14 前端机制级）：
 * - src/api/clusters.ts 的 URL / method / body 构造（Contract §6：
 *   列表查询串、POST 201 信封、PATCH 仅携带变化字段、DELETE/restore 的
 *   version Query 参数）；
 * - 409 CONFLICT（unique_conflict → 字段级错误）/ VERSION_CONFLICT
 *   （→ 刷新后重改，不静默重试）/ 422 / 404 / 403 的 describeClusterActionError 语义。
 *
 * F004 追加（Contract：docs/api/F004.md v1，前端机制级）：
 * - src/api/resources.ts 的 URL / method / body 构造（Contract §6：
 *   列表查询串（过滤参数名 type / 排序字段名 resource_type 不可互换）、
 *   POST 201 信封、PATCH 仅携带变化字段、DELETE/restore version Query、activity）；
 * - 409 CONFLICT（unique_conflict → hostname 字段错误；dependency_deleted →
 *   conflicts）/ VERSION_CONFLICT（→ 刷新后重改，不静默重试）/ 422 / 404 / 403
 *   的 describeResourceActionError 语义。
 *
 * F005 追加（Contract：docs/api/F004.md v2 §2.4，前端机制级）：
 * - src/api/resources.ts 的 hardware 嵌套载荷：POST BARE_METAL 仅携带已登记
 *   子字段、VM 载荷不含 hardware 键（DR-51）、PATCH 子字段级 exclude_unset
 *   （省略=保持；显式 null=清空）；响应 hardware 解析（0 与 null 可区分）；
 * - src/components/hardware.ts（纯逻辑，无 JSX）：表单值解析（trim / 严格整数 /
 *   范围 / 未知=null）、创建 / PATCH 载荷构造语义的本地镜像。
 *   （ResourceForm.tsx 含 JSX 无法被 Node 加载，故该映射独立成纯模块。）
 *
 * F006 追加（Contract：docs/api/F004.md v3 §2.5，前端机制级，供 V20）：
 * - src/api/resources.ts 的 virtual_machine 嵌套载荷：POST VIRTUAL_MACHINE 必带
 *   virtual_machine（host_resource_id 必填）、BARE_METAL 载荷不含该键（互斥
 *   422）、PATCH 子字段级 exclude_unset（省略=保持；显式 null=清空；换 Host
 *   携带新 host_resource_id）；响应 virtual_machine 解析（host{id,hostname} 展开、
 *   0 与 null 可区分）；列表 host_resource_id 过滤（DR-67）；
 * - 409 reference_exists（宿主机被未删除 VM 引用，references 含 label）/
 *   dependency_deleted（恢复 VM 时宿主机已删，conflicts object_type=resource）
 *   的 describeResourceActionError 语义（不静默重试）；
 * - src/components/virtualMachine.ts（纯逻辑，无 JSX）：表单值解析（宿主非空 /
 *   trim / 严格整数 / 范围 / disk_gb=0 与 null 可区分）、创建 / PATCH 载荷
 *   构造语义的本地镜像。
 *
 * F007 追加（Contract：docs/api/F007.md v1，前端机制级，供 V19 数据侧）：
 * - src/api/interfaces.ts 的 URL / method / body 构造（Contract §6：列表查询串
 *   （resource_id / interface_type / enabled / q / parent_interface_id / deleted）、
 *   POST 201 信封、PATCH 仅携带变化字段、DELETE / restore 的 version Query、
 *   activity）；
 * - 409 CONFLICT（unique_conflict field="name" → 字段级错误；reference_exists
 *   → references（子接口 / IP）；dependency_deleted → conflicts（resource /
 *   interface））/ VERSION_CONFLICT（→ 刷新后重改，不静默重试）/ 422 / 404 /
 *   403 的 describeInterfaceActionError 语义；
 * - src/components/interfaceForm.ts（纯逻辑，无 JSX）：表单值解析（name trim /
 *   禁内部空白与控制字符 / ≤64、mac trim / ≤64、speed/mtu 正整数、未知=null）、
 *   创建 / PATCH 载荷构造语义的本地镜像（exclude_unset；显式 null=清空；
 *   parent_interface id 提取）。
 *
 * F008 追加（Contract：docs/api/F008.md v1，前端机制级）：
 * - src/api/networks.ts 的 URL / method / body 构造（Contract §6：列表查询串
 *   （q / cluster_id / status / auto_allocate / deleted）、POST 201 信封、PATCH
 *   仅携带变化字段、DELETE / restore 的 version Query、activity）；
 * - 409 CONFLICT（unique_conflict field="name" → 字段级错误；range_overlap
 *   field="cidr" → cidr 字段错误 + conflicts（重叠 Network）；reference_exists
 *   → references（IPPool / IPAddress）；dependency_deleted → conflicts（cluster）；
 *   not_deleted）/ VERSION_CONFLICT（→ 刷新后重改，不静默重试）/ 422 / 404 / 403
 *   的 describeNetworkActionError 语义；
 * - src/components/networkForm.ts（纯逻辑，无 JSX）：表单值解析（name trim /
 *   禁控制字符 / ≤255、cidr IPv4/CIDR 格式、gateway 可选 IPv4、空串=null /
 *   默认 ACTIVE / auto_allocate false）、创建 / PATCH 载荷构造语义的本地镜像
 *   （exclude_unset；显式 null=清空 gateway/description；可改 cluster）。
 *
 * F009 追加（Contract：docs/api/F009.md v1，前端机制级）：
 * - src/api/ipPools.ts 的 URL / method / body 构造（Contract §6：列表查询串
 *   （network_id / allocation_mode / q / deleted）、POST 201 {"ip_pool"} 信封、
 *   PATCH 仅携带变化字段（不含 network，DR-107）、DELETE / restore 的 version
 *   Query、activity）；
 * - 409 CONFLICT（unique_conflict field="name" → 字段级错误；range_overlap
 *   field="start_address"|"end_address" → 字段错误 + conflicts（重叠 IPPool 含
 *   起止地址）；address_in_use → occupancy（conflict_count 总数 + conflicts
 *   预览 + conflicts_truncated，DR-110）；dependency_deleted → conflicts
 *   （network）；not_deleted）/ VERSION_CONFLICT（→ 刷新后重改，不静默重试）/
 *   422 / 404 / 403 的 describeIpPoolActionError 语义；
 * - src/components/ipPoolForm.ts（纯逻辑，无 JSX）：表单值解析（name trim /
 *   禁控制字符 / ≤255、起止单个 IPv4 主机地址不带掩码、起≤止、属 CIDR 本地
 *   提示、默认 MANUAL、空描述=null）、创建 / PATCH 载荷构造语义的本地镜像
 *   （exclude_unset；显式 null=清空 description；network 不可改不上送）、
 *   服务端 422 点路径 → 表单键映射。
 *
 * F010 追加（Contract：docs/api/F010.md v1，前端机制级）：
 * - src/api/ipAddresses.ts 的 URL / method / body 构造（Contract §6：列表查询串
 *   （network_id/cluster_id/interface_id/ip_pool_id/address/bound/q/deleted）、
 *   POST 手动分配 201 {"ip_address"}、POST /auto-allocate（network+ip_pool）。
 *   PATCH 仅携带变化字段（不含 network/address/ip_pool，DR-120/DR-122）、
 *   DELETE（释放）/ restore 的 version Query、activity、GET /networks/{id}/capacity
 *   容量数据）；
 * - 409 CONFLICT（unique_conflict field="address" → 字段级错误；
 *   allocation_not_allowed condition=network_inactive|auto_allocate_disabled|
 *   pool_not_auto → 条件文案；no_available_address → {network_id,ip_pool_id}；
 *   reference_exists → references（endpoint）；dependency_deleted → conflicts
 *   （network/interface 文案区分）；not_deleted）/ VERSION_CONFLICT（→ 刷新后
 *   重改，不静默重试）/ 422 / 404 / 403 的 describeIpAddressActionError 语义；
 * - src/components/ipAddressForm.ts（纯逻辑，无 JSX）：表单值解析（裸 IPv4 不带
 *   掩码、属 CIDR 本地提示、auto/edit 模式不校验 address、空描述=null、空接口
 *   选=null）、手动 / 自动分配载荷构造、PATCH exclude_unset 镜像（interface 绑定/
 *   解绑/转移；network/address/ip_pool 恒不上送）、服务端 422 点路径 → 表单键映射。
 *
 * F011 追加（Contract：docs/api/F011.md v1，前端机制级）：
 * - src/api/services.ts 的 URL / method / body 构造（Contract §6：列表查询串
 *   （resource_id/status/q/deleted）、POST 201 {"service"} 信封、PATCH 仅携带
 *   变化字段（不含 resource，DR-144）、DELETE / restore 的 version Query、
 *   activity）；
 * - 409 CONFLICT（unique_conflict field="name" → 字段级错误；reference_exists
 *   → references（service_endpoint，F011 默认空集、F012 起真实，DR-146）；
 *   dependency_deleted → conflicts（resource）；not_deleted）/ VERSION_CONFLICT
 *   （→ 刷新后重改，不静默重试）/ 422 / 404 / 403 的 describeServiceActionError
 *   语义；
 * - src/components/serviceForm.ts（纯逻辑，无 JSX）：表单值解析（name trim /
 *   禁控制字符 / ≤255、允许内部空格不合并、默认 UNKNOWN、空描述=null）、
 *   创建 / PATCH 载荷构造语义的本地镜像（exclude_unset；显式 null=清空
 *   description；metadata 整值替换、非空才携带；resource 不可改不上送）、
 *   服务端 422 点路径 → 表单键映射。
 *
 * F012 追加（Contract：docs/api/F012.md v1，前端机制级）：
 * - src/api/serviceEndpoints.ts 的 URL / method / body 构造（Contract §6：列表
 *   查询串（service_id/ip_address_id/protocol/deleted）、POST 201
 *   {"service_endpoint"} 信封、PATCH 仅携带变化字段（不含 service/ip_address，
 *   DR-157）、DELETE / restore 的 version Query、activity）；
 * - 409 CONFLICT（unique_conflict field="port" → port 字段级错误（携带冲突
 *   protocol/port/ip_address_id）；dependency_deleted → conflicts（service /
 *   ip_address / interface 文案区分，DR-166）；reference_exists → references
 *   （防御，Endpoint 无子对象）；not_deleted）/ VERSION_CONFLICT（→ 刷新后
 *   重改，不静默重试）/ 422 / 404 / 403 的 describeServiceEndpointActionError
 *   语义；
 * - src/components/serviceEndpointForm.ts（纯逻辑，无 JSX）：表单值解析
 *   （protocol 仅大写 TCP/UDP 不归一化、port 严格整数 1–65535 含端点、
 *   空描述=null）、创建 / PATCH 载荷构造语义的本地镜像（exclude_unset；
 *   显式 null=清空 description；service/ip_address 不可改不上送）、
 *   服务端 422 点路径 → 表单键映射（service_id/ip_address_id 别名不映射）。
 *
 * F013 追加（Contract：docs/api/F013.md v1，前端机制级）：
 * - src/api/search.ts 的 URL 构造（Contract §2：q 必携带、type/deleted/page/
 *   page_size 序列化、空结果 200 空列表）与 typed 行响应解析（4 类嵌套对象、
 *   未绑定 IP resource=null）；describeSearchError 的 401/403（permission 与
 *   未知 reason）/ 422（fields）/ 网络层兑底语义；
 * - src/api/dashboard.ts 的 URL 构造（Contract §3：无查询串默认、page/
 *   page_size 仅作用于 networks）与 counts/networks/capacity/auto_pools 响应
 *   解析（负 remaining 原样）；describeDashboardError 的 401/403/422 语义；
 * - src/components/globalSearchForm.ts（纯逻辑，无 JSX）：q trim / 空输入
 *   不发请求（buildSearchQuery → null，I-13）/ 超长 255 code point 本地拦截、
 *   type 自由输入非法值拦截、422 点路径 → 表单键映射、高亮分段（ASCII
 *   大小写不敏感子串；非子串模糊命中不高亮）。
 *
 * F014 追加（Contract：docs/api/F014.md v1，前端机制级）：
 * - src/api/client.ts 的 requestUpload：multipart/form-data（不手动设置
 *   Content-Type，boundary 由 fetch 生成）；信封 / 401 全局处理 / 不重试与
 *   request 一致（共用 handleResponse）；
 * - src/api/imports.ts 的三端点（§3/§4/§5：POST /imports/resources/validate、
 *   POST /imports/resources（FormData：file+format）、GET /imports/resources/
 *   templates）；describeImportError 的 401/403（permission|csrf）/ 413
 *   （IMPORT_FILE_TOO_LARGE limit_bytes / IMPORT_ROW_LIMIT_EXCEEDED limit_rows）/ 422
 *   （IMPORT_INVALID_FILE reason+列清单 / IMPORT_VALIDATION_FAILED 行错误明细 /
 *   VALIDATION_ERROR field=format）/ 500 / 网络层兑底语义；details 形状不符时
 *   不伪造行错误；
 * - src/components/importForm.ts（纯逻辑，无 JSX）：空输入不发请求（file
 *   未选本地报错）、文件大小超 5 MiB 本地拦截（§10 签核值）、format=xlsx
 *   仅接受 .xlsx（大小写不敏感）、importTargetKey 输入指纹（变化即失效）、
 *   422 点路径 → 表单键（format）、模板列渲染辅助（类型·单位/枚举/必填）与
 *   表头行 CSV 生成（DR-208）。
 *
 * F015 追加（Contract：docs/api/F015.md v1，前端机制级）：
 * - src/api/audit.ts 的 URL / 查询串构造（§2：operator/object_type/object_id/
 *   action/created_from/created_to/分页/sort=created_at/order AND 组合、空串
 *   过滤项不发）与 AuditRow 响应解析（operator_user_id/before/after 可 null）；
 *   describeAuditQueryError 的 401/403/422（fields）/网络层兑底语义；
 * - src/api/deleted.ts 的 URL / 查询串构造（§3：object_type/分页/sort=
 *   deleted_at/order）与 DeletedItem 响应解析（label/version/cluster 可 null）；
 *   restoreDeletedItem 按 object_type 路由到各域既有 restore（§5 路由表，
 *   不新增统一写端点）；describeDeletedActionError 的 409 reason
 *   （unique_conflict/dependency_deleted/not_deleted）/ VERSION_CONFLICT /
 *   403 / 网络层语义；
 * - src/api/users.ts 的 URL / method / body 构造（§4：列表 role/status/q/分页/
 *   排序、POST 创建 201 {user}（body 恰含 username/password/role）、GET 详情、
 *   PATCH 仅携带变化字段 + version 乐观锁）；describeUserActionError 的 409
 *   unique_conflict（→ username 字段级错误）/ VERSION_CONFLICT（→ 刷新后重改）/
 *   422（fields）/ 403 / 404 语义；
 * - src/components/auditQueryForm.ts（纯逻辑，无 JSX）：表单值解析（operator
 *   trim / ≤64、object_id 须与 object_type 同现且为 UUID、datetime-local 按
 *   UTC 归一为 ISO-8601、from≤to 闭区间）、buildAuditQuery 参数序列化、
 *   422 点路径 → 表单键映射（snake→camel；分页/排序参数不映射）。
 *
 * 运行：npm run smoke:client（Node ≥ 22.18 内置 TypeScript type stripping，
 * 直接加载 src/api/client.ts 与 src/api/clusters.ts，无需新增测试框架；
 * 仅替换 globalThis.fetch 为受控响应）。
 */
import assert from "node:assert/strict";
import {
  getHealth,
  isApiError,
  request,
  setUnauthorizedHandler,
} from "../src/api/client.ts";
import {
  createCluster,
  deleteCluster,
  describeClusterActionError,
  getCluster,
  listClusters,
  restoreCluster,
  updateCluster,
} from "../src/api/clusters.ts";
import {
  createResource,
  deleteResource,
  describeResourceActionError,
  getResource,
  getResourceActivity,
  listResources,
  restoreResource,
  updateResource,
} from "../src/api/resources.ts";
import {
  buildHardwareCreateInput,
  buildHardwarePatch,
  emptyHardwareFormValues,
  hardwareFormValuesFromResource,
  parseHardwareFormValues,
} from "../src/components/hardware.ts";
import {
  buildVirtualMachineCreateInput,
  buildVirtualMachinePatch,
  emptyVirtualMachineFormValues,
  parseVirtualMachineFormValues,
  virtualMachineFormValuesFromResource,
} from "../src/components/virtualMachine.ts";
import {
  createInterface,
  deleteInterface,
  describeInterfaceActionError,
  getInterface,
  getInterfaceActivity,
  listInterfaces,
  restoreInterface,
  updateInterface,
} from "../src/api/interfaces.ts";
import {
  buildInterfaceCreateInput,
  buildInterfacePatch,
  emptyInterfaceFormValues,
  interfaceFormValuesFromInterface,
  parseInterfaceFormValues,
} from "../src/components/interfaceForm.ts";
import {
  createNetwork,
  deleteNetwork,
  describeNetworkActionError,
  getNetwork,
  getNetworkActivity,
  listNetworks,
  restoreNetwork,
  updateNetwork,
} from "../src/api/networks.ts";
import {
  buildNetworkCreateInput,
  buildNetworkPatch,
  emptyNetworkFormValues,
  networkFormValuesFromNetwork,
  parseNetworkFormValues,
} from "../src/components/networkForm.ts";
import {
  createIpPool,
  deleteIpPool,
  describeIpPoolActionError,
  getIpPool,
  getIpPoolActivity,
  listIpPools,
  restoreIpPool,
  updateIpPool,
} from "../src/api/ipPools.ts";
import {
  buildIpPoolCreateInput,
  buildIpPoolPatch,
  emptyIpPoolFormValues,
  ipPoolFormFieldFromPath,
  ipPoolFormValuesFromIpPool,
  parseIpPoolFormValues,
} from "../src/components/ipPoolForm.ts";
import {
  autoAllocateIpAddress,
  createIpAddress,
  describeIpAddressActionError,
  getIpAddress,
  getIpAddressActivity,
  getNetworkCapacity,
  listIpAddresses,
  releaseIpAddress,
  restoreIpAddress,
  updateIpAddress,
} from "../src/api/ipAddresses.ts";
import {
  buildAutoAllocateInput,
  buildIpAddressPatch,
  buildManualAllocateInput,
  emptyIpAddressFormValues,
  ipAddressFormFieldFromPath,
  ipAddressFormValuesFromIpAddress,
  isValidBareIpv4,
  parseIpAddressFormValues,
} from "../src/components/ipAddressForm.ts";
import {
  createService,
  deleteService,
  describeServiceActionError,
  getService,
  getServiceActivity,
  listServices,
  restoreService,
  updateService,
} from "../src/api/services.ts";
import {
  buildServiceCreateInput,
  buildServicePatch,
  emptyServiceFormValues,
  parseServiceFormValues,
  serviceFormFieldFromPath,
  serviceFormValuesFromService,
} from "../src/components/serviceForm.ts";
import {
  createServiceEndpoint,
  deleteServiceEndpoint,
  describeServiceEndpointActionError,
  getServiceEndpoint,
  getServiceEndpointActivity,
  listServiceEndpoints,
  restoreServiceEndpoint,
  updateServiceEndpoint,
} from "../src/api/serviceEndpoints.ts";
import {
  buildServiceEndpointCreateInput,
  buildServiceEndpointPatch,
  emptyServiceEndpointFormValues,
  parseServiceEndpointFormValues,
  serviceEndpointFormFieldFromPath,
  serviceEndpointFormValuesFromEndpoint,
} from "../src/components/serviceEndpointForm.ts";
import {
  describeDashboardError,
  getDashboard,
} from "../src/api/dashboard.ts";
import {
  describeSearchError,
  search,
} from "../src/api/search.ts";
import {
  buildSearchQuery,
  emptyGlobalSearchFormValues,
  highlightSegments,
  parseGlobalSearchFormValues,
  searchFormFieldFromPath,
} from "../src/components/globalSearchForm.ts";
import {
  describeImportError,
  getImportTemplates,
  IMPORT_MAX_FILE_BYTES,
  importResources,
  validateResourceImport,
} from "../src/api/imports.ts";
import {
  buildTemplateCsv,
  emptyImportFormValues,
  importFormFieldFromPath,
  importTargetKey,
  parseImportFormValues,
  templateColumnTypeLabel,
  templateColumnRequiredLabel,
} from "../src/components/importForm.ts";
import {
  describeAuditQueryError,
  listAudit,
} from "../src/api/audit.ts";
import {
  describeDeletedActionError,
  listDeleted,
  restoreDeletedItem,
} from "../src/api/deleted.ts";
import {
  createUser,
  describeUserActionError,
  getUser,
  listUsers,
  updateUser,
} from "../src/api/users.ts";
import {
  auditQueryFieldFromPath,
  buildAuditQuery,
  emptyAuditQueryFormValues,
  parseAuditQueryFormValues,
  parseIso8601UtcInput,
} from "../src/components/auditQueryForm.ts";

let respond = null;
let handlerCalls = 0;
let passed = 0;
let failed = 0;
const calls = [];

const originalFetch = globalThis.fetch;
globalThis.fetch = async (input, init) => {
  calls.push({ url: String(input), init });
  return respond(input, init);
};

function jsonResponse(status, body) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

async function expectApiError(promise) {
  try {
    await promise;
  } catch (err) {
    assert.ok(isApiError(err), `应为 ApiError，实际 ${err?.constructor?.name}`);
    return err;
  }
  throw new assert.AssertionError({ message: "应抛出 ApiError，实际 resolve" });
}

async function test(name, fn) {
  calls.length = 0;
  handlerCalls = 0;
  try {
    await fn();
    passed += 1;
    console.log(`PASS: ${name}`);
  } catch (err) {
    failed += 1;
    console.error(`FAIL: ${name}`);
    console.error(`  ${err?.stack ?? String(err)}`);
  }
}

// 统计全局 401 处理器触发次数（应用壳用它清登录态回登录页）
setUnauthorizedHandler(() => {
  handlerCalls += 1;
});

await test("GET 200：credentials=include、解析 JSON、路径 /api/v1", async () => {
  respond = () => jsonResponse(200, { status: "ok", service: "csm-backend" });
  const health = await getHealth();
  assert.equal(health.status, "ok");
  assert.equal(health.service, "csm-backend");
  assert.equal(calls.length, 1);
  assert.equal(calls[0].url, "/api/v1/health");
  assert.equal(calls[0].init.method, "GET");
  assert.equal(calls[0].init.credentials, "include");
});

await test("POST：JSON body + Content-Type + credentials=include", async () => {
  respond = () => jsonResponse(200, { user: { id: "u" } });
  await request("/auth/login", {
    method: "POST",
    body: { username: "admin", password: "secret" },
  });
  assert.equal(calls.length, 1);
  assert.equal(calls[0].init.method, "POST");
  assert.equal(calls[0].init.credentials, "include");
  assert.equal(calls[0].init.headers["Content-Type"], "application/json");
  assert.deepEqual(JSON.parse(calls[0].init.body), {
    username: "admin",
    password: "secret",
  });
});

await test("401 AUTH_REQUIRED：抛 ApiError 并触发全局 401 处理器；不重试", async () => {
  respond = () =>
    jsonResponse(401, {
      error: { code: "AUTH_REQUIRED", message: "未认证或会话已过期", details: {} },
    });
  const err = await expectApiError(request("/auth/me"));
  assert.equal(err.status, 401);
  assert.equal(err.code, "AUTH_REQUIRED");
  assert.equal(err.message, "未认证或会话已过期");
  assert.deepEqual(err.details, {});
  assert.equal(handlerCalls, 1);
  assert.equal(calls.length, 1);
});

await test("登录 401 AUTH_INVALID_CREDENTIALS：错误可呈现、不重试", async () => {
  respond = () =>
    jsonResponse(401, {
      error: { code: "AUTH_INVALID_CREDENTIALS", message: "用户名或密码错误", details: {} },
    });
  const err = await expectApiError(
    request("/auth/login", {
      method: "POST",
      body: { username: "admin", password: "wrong" },
    }),
  );
  assert.equal(err.status, 401);
  assert.equal(err.code, "AUTH_INVALID_CREDENTIALS");
  assert.equal(err.message, "用户名或密码错误");
  assert.equal(handlerCalls, 1); // 登录页已在目标页，处理器触发为无副作用
  assert.equal(calls.length, 1);
});

await test("403 FORBIDDEN（details.reason=csrf）：明确呈现、不触发 401 处理器、不重试", async () => {
  respond = () =>
    jsonResponse(403, {
      error: { code: "FORBIDDEN", message: "跨站请求被拒绝", details: { reason: "csrf" } },
    });
  const err = await expectApiError(request("/auth/logout", { method: "POST" }));
  assert.equal(err.status, 403);
  assert.equal(err.code, "FORBIDDEN");
  assert.equal(err.details.reason, "csrf");
  assert.equal(handlerCalls, 0);
  assert.equal(calls.length, 1);
});

await test("409 VERSION_CONFLICT（details.current_version）：可识别冲突信号、不静默重试", async () => {
  respond = () =>
    jsonResponse(409, {
      error: { code: "VERSION_CONFLICT", message: "数据已被他人修改", details: { current_version: 7 } },
    });
  const err = await expectApiError(
    request("/example", { method: "POST", body: { version: 6 } }),
  );
  assert.equal(err.status, 409);
  assert.equal(err.code, "VERSION_CONFLICT");
  assert.equal(err.details.current_version, 7);
  assert.equal(handlerCalls, 0);
  assert.equal(calls.length, 1);
});

await test("422 VALIDATION_ERROR：details.fields 可供字段级呈现", async () => {
  respond = () =>
    jsonResponse(422, {
      error: {
        code: "VALIDATION_ERROR",
        message: "请求参数校验失败",
        details: { fields: [{ field: "username", message: "不能为空" }] },
      },
    });
  const err = await expectApiError(
    request("/auth/login", { method: "POST", body: { username: "", password: "" } }),
  );
  assert.equal(err.status, 422);
  assert.equal(err.code, "VALIDATION_ERROR");
  assert.ok(Array.isArray(err.details.fields));
  assert.equal(err.details.fields[0].field, "username");
  assert.equal(err.details.fields[0].message, "不能为空");
});

await test("204 无正文：resolve undefined（logout 语义）", async () => {
  respond = () => new Response(null, { status: 204 });
  const result = await request("/auth/logout", { method: "POST" });
  assert.equal(result, undefined);
  assert.equal(calls.length, 1);
});

await test("非 JSON 错误体（502 网关页）：回退 HTTP 状态、code=null、不重试", async () => {
  respond = () =>
    new Response("<html>Bad Gateway</html>", {
      status: 502,
      headers: { "Content-Type": "text/html" },
    });
  const err = await expectApiError(request("/auth/me"));
  assert.equal(err.status, 502);
  assert.equal(err.code, null);
  assert.equal(err.message, "HTTP 502");
  assert.equal(calls.length, 1);
});

await test("信封形状不符（缺 code）：回退、不伪造信封内容", async () => {
  respond = () => jsonResponse(500, { error: { message: "内部错误" } });
  const err = await expectApiError(request("/auth/me"));
  assert.equal(err.status, 500);
  assert.equal(err.code, null);
  assert.equal(err.message, "HTTP 500");
});

// ---------- F003 Cluster API 机制级（Contract：docs/api/F003.md v1） ----------

await test("F003 listClusters 默认：GET /api/v1/clusters，无查询串", async () => {
  respond = () => jsonResponse(200, { items: [], page: 1, page_size: 20, total: 0 });
  const data = await listClusters();
  assert.equal(data.total, 0);
  assert.equal(calls.length, 1);
  assert.equal(calls[0].url, "/api/v1/clusters");
  assert.equal(calls[0].init.method, "GET");
  assert.equal(calls[0].init.credentials, "include");
});

await test("F003 listClusters 组合查询：q/code/status/deleted/page/page_size/sort/order（AND 组合）", async () => {
  respond = () => jsonResponse(200, { items: [], page: 2, page_size: 50, total: 0 });
  await listClusters({
    q: "gpu",
    code: "N96P",
    status: "ACTIVE",
    deleted: "only",
    page: 2,
    page_size: 50,
    sort: "code",
    order: "asc",
  });
  assert.equal(calls.length, 1);
  assert.equal(
    calls[0].url,
    "/api/v1/clusters?q=gpu&code=N96P&status=ACTIVE&deleted=only&page=2&page_size=50&sort=code&order=asc",
  );
});

await test("F003 listClusters 空串过滤项不发（q=''/code=''），status 省略不发", async () => {
  respond = () => jsonResponse(200, { items: [], page: 1, page_size: 20, total: 0 });
  await listClusters({ q: "", code: "" });
  assert.equal(calls[0].url, "/api/v1/clusters");
});

await test("F003 createCluster：POST /clusters + JSON body；201 解析 {cluster}", async () => {
  respond = () => jsonResponse(201, { cluster: { id: "c1", code: "N96P", version: 1 } });
  const { cluster } = await createCluster({ code: "N96P", name: "N96P集群" });
  assert.equal(cluster.id, "c1");
  assert.equal(calls.length, 1);
  assert.equal(calls[0].url, "/api/v1/clusters");
  assert.equal(calls[0].init.method, "POST");
  assert.deepEqual(JSON.parse(calls[0].init.body), { code: "N96P", name: "N96P集群" });
});

await test("F003 getCluster：已删对象显式 ?deleted=true；默认不带", async () => {
  respond = () => jsonResponse(200, { cluster: { id: "c1", deleted_at: "2026-10-06T12:00:00+00:00" } });
  await getCluster("c1", { deleted: true });
  await getCluster("c1");
  assert.equal(calls[0].url, "/api/v1/clusters/c1?deleted=true");
  assert.equal(calls[1].url, "/api/v1/clusters/c1");
});

await test("F003 updateCluster：PATCH 且仅携带变化字段（省略 = 不重置，Contract §6.4）", async () => {
  respond = () => jsonResponse(200, { cluster: { id: "c1", version: 4 } });
  const { cluster } = await updateCluster("c1", { version: 3, name: "新名称" });
  assert.equal(cluster.version, 4);
  assert.equal(calls.length, 1);
  assert.equal(calls[0].url, "/api/v1/clusters/c1");
  assert.equal(calls[0].init.method, "PATCH");
  // body 只含 version + 变化字段，杂散字段（status/description/metadata）不出现
  assert.deepEqual(JSON.parse(calls[0].init.body), { version: 3, name: "新名称" });
});

await test("F003 updateCluster：description 显式 null = 清空", async () => {
  respond = () => jsonResponse(200, { cluster: { id: "c1" } });
  await updateCluster("c1", { version: 3, description: null });
  assert.deepEqual(JSON.parse(calls[0].init.body), { version: 3, description: null });
});

await test("F003 deleteCluster：DELETE + version 为 Query 参数；204 → undefined", async () => {
  respond = () => new Response(null, { status: 204 });
  const result = await deleteCluster("c1", 5);
  assert.equal(result, undefined);
  assert.equal(calls.length, 1);
  assert.equal(calls[0].url, "/api/v1/clusters/c1?version=5");
  assert.equal(calls[0].init.method, "DELETE");
});

await test("F003 restoreCluster：POST /{id}/restore + version Query 参数", async () => {
  respond = () => jsonResponse(200, { cluster: { id: "c1", deleted_at: null, version: 7 } });
  const { cluster } = await restoreCluster("c1", 6);
  assert.equal(cluster.deleted_at, null);
  assert.equal(calls.length, 1);
  assert.equal(calls[0].url, "/api/v1/clusters/c1/restore?version=6");
  assert.equal(calls[0].init.method, "POST");
});

await test("F003 409 CONFLICT unique_conflict：落到 code 字段级错误；不重试", async () => {
  respond = () =>
    jsonResponse(409, {
      error: {
        code: "CONFLICT",
        message: "Conflict",
        details: { reason: "unique_conflict", field: "code" },
      },
    });
  const err = await expectApiError(createCluster({ code: "n96p", name: "x" }));
  assert.equal(err.status, 409);
  assert.equal(err.code, "CONFLICT");
  assert.equal(err.details.reason, "unique_conflict");
  const described = describeClusterActionError(err);
  assert.equal(described.versionConflict, false);
  assert.ok(described.fields.code, "unique_conflict 应落到 code 字段错误");
  assert.ok(described.fields.code.includes("不可复用"));
  assert.equal(calls.length, 1); // 不自动重试
});

await test("F003 409 VERSION_CONFLICT：标记刷新后重改、携带 current_version；不重试", async () => {
  respond = () =>
    jsonResponse(409, {
      error: {
        code: "VERSION_CONFLICT",
        message: "Version conflict",
        details: { current_version: 9 },
      },
    });
  const err = await expectApiError(updateCluster("c1", { version: 3, name: "x" }));
  assert.equal(err.details.current_version, 9);
  const described = describeClusterActionError(err);
  assert.equal(described.versionConflict, true);
  assert.equal(described.currentVersion, 9);
  assert.ok(described.message.includes("刷新"), "应提示刷新后重改");
  assert.ok(described.message.includes("不会自动重试"));
  assert.equal(calls.length, 1); // 不静默重试覆盖
});

await test("F003 409 CONFLICT reference_exists：展示引用语义", async () => {
  respond = () =>
    jsonResponse(409, {
      error: {
        code: "CONFLICT",
        message: "Conflict",
        details: {
          reason: "reference_exists",
          references: [{ object_type: "resource", object_id: "r1", label: "gpu01" }],
        },
      },
    });
  const err = await expectApiError(deleteCluster("c1", 2));
  const described = describeClusterActionError(err);
  assert.equal(described.versionConflict, false);
  assert.equal(described.references.length, 1);
  assert.equal(described.references[0].object_type, "resource");
  assert.ok(described.message.includes("无法删除"));
});

await test("F003 409 CONFLICT not_deleted：恢复未删对象的明确文案", async () => {
  respond = () =>
    jsonResponse(409, {
      error: { code: "CONFLICT", message: "Conflict", details: { reason: "not_deleted" } },
    });
  const err = await expectApiError(restoreCluster("c1", 2));
  const described = describeClusterActionError(err);
  assert.ok(described.message.includes("未处于已删除状态"));
  assert.ok(described.message.includes("CONFLICT/not_deleted"));
});

await test("F003 422 VALIDATION_ERROR：details.fields 透传为字段级错误", async () => {
  respond = () =>
    jsonResponse(422, {
      error: {
        code: "VALIDATION_ERROR",
        message: "Validation error",
        details: { fields: [{ field: "code", message: "code 不能含内部空白" }] },
      },
    });
  const err = await expectApiError(createCluster({ code: "a b", name: "x" }));
  const described = describeClusterActionError(err);
  assert.equal(described.fields.code, "code 不能含内部空白");
});

await test("F003 404 / 403：明确文案（不泄露存在性 / 权限不足）", async () => {
  respond = () =>
    jsonResponse(404, { error: { code: "NOT_FOUND", message: "Not found", details: {} } });
  const notFound = await expectApiError(getCluster("c1"));
  assert.ok(describeClusterActionError(notFound).message.includes("不存在"));

  respond = () =>
    jsonResponse(403, {
      error: { code: "FORBIDDEN", message: "Forbidden", details: { reason: "permission" } },
    });
  const forbidden = await expectApiError(deleteCluster("c1", 1));
  assert.ok(describeClusterActionError(forbidden).message.includes("权限"));
});

await test("F003 网络层错误（fetch reject）：不伪装成业务结果", async () => {
  respond = () => Promise.reject(new TypeError("Failed to fetch"));
  await assert.rejects(listClusters(), TypeError);
  assert.equal(calls.length, 1); // 失败不重发
});

// ---------- F004 Resource API 机制级（Contract：docs/api/F004.md v1） ----------

await test("F004 listResources 默认：GET /api/v1/resources，无查询串", async () => {
  respond = () => jsonResponse(200, { items: [], page: 1, page_size: 20, total: 0 });
  const data = await listResources();
  assert.equal(data.total, 0);
  assert.equal(calls.length, 1);
  assert.equal(calls[0].url, "/api/v1/resources");
  assert.equal(calls[0].init.method, "GET");
  assert.equal(calls[0].init.credentials, "include");
});

await test("F004 listResources 组合查询：q/cluster/type/role/status/deleted/分页/排序（AND 组合）", async () => {
  respond = () => jsonResponse(200, { items: [], page: 2, page_size: 50, total: 0 });
  await listResources({
    q: "cn0",
    cluster: "N96P",
    type: "BARE_METAL",
    role: "COMPUTE",
    status: "IDLE",
    deleted: "only",
    page: 2,
    page_size: 50,
    sort: "hostname",
    order: "asc",
  });
  assert.equal(calls.length, 1);
  // 过滤参数名为 type（非 resource_type 别名）；排序字段名为 resource_type，两者不可互换
  assert.equal(
    calls[0].url,
    "/api/v1/resources?q=cn0&cluster=N96P&type=BARE_METAL&role=COMPUTE&status=IDLE" +
      "&deleted=only&page=2&page_size=50&sort=hostname&order=asc",
  );
});

await test("F004 listResources cluster_id（UUID）过滤；空串项不发", async () => {
  respond = () => jsonResponse(200, { items: [], page: 1, page_size: 20, total: 0 });
  await listResources({
    cluster_id: "0b9f4c6b-8f82-4b7a-9b95-a1e93b1f0004",
    sort: "resource_type",
    q: "",
    cluster: "",
  });
  assert.equal(calls.length, 1);
  assert.equal(
    calls[0].url,
    "/api/v1/resources?cluster_id=0b9f4c6b-8f82-4b7a-9b95-a1e93b1f0004&sort=resource_type",
  );
});

await test("F004 createResource：POST /resources + JSON body；201 解析 {resource}", async () => {
  respond = () =>
    jsonResponse(201, {
      resource: {
        id: "r1",
        cluster: { id: "c1", code: "N96P", name: "N96P集群" },
        hostname: "cn001",
        resource_type: "BARE_METAL",
        role: "OTHER",
        status: "UNKNOWN",
        description: null,
        metadata: {},
        version: 1,
        created_at: "2026-10-08T08:00:00Z",
        updated_at: "2026-10-08T08:00:00Z",
        deleted_at: null,
      },
    });
  const { resource } = await createResource({
    cluster: "c1-uuid-or-code",
    hostname: "CN001",
    resource_type: "BARE_METAL",
  });
  assert.equal(resource.id, "r1");
  assert.equal(resource.cluster.code, "N96P");
  assert.equal(calls.length, 1);
  assert.equal(calls[0].url, "/api/v1/resources");
  assert.equal(calls[0].init.method, "POST");
  assert.deepEqual(JSON.parse(calls[0].init.body), {
    cluster: "c1-uuid-or-code",
    hostname: "CN001",
    resource_type: "BARE_METAL",
  });
});

await test("F004 getResource：已删对象显式 ?deleted=true；默认不带", async () => {
  respond = () =>
    jsonResponse(200, { resource: { id: "r1", deleted_at: "2026-10-08T12:00:00Z" } });
  await getResource("r1", { deleted: true });
  await getResource("r1");
  assert.equal(calls[0].url, "/api/v1/resources/r1?deleted=true");
  assert.equal(calls[1].url, "/api/v1/resources/r1");
});

await test("F004 updateResource：PATCH 且仅携带变化字段（省略 = 不重置，Contract §6.4）", async () => {
  respond = () => jsonResponse(200, { resource: { id: "r1", version: 4 } });
  const { resource } = await updateResource("r1", {
    version: 3,
    hostname: "cn002",
    role: "COMPUTE",
  });
  assert.equal(resource.version, 4);
  assert.equal(calls.length, 1);
  assert.equal(calls[0].url, "/api/v1/resources/r1");
  assert.equal(calls[0].init.method, "PATCH");
  // body 只含 version + 变化字段；cluster / resource_type 不可改不出现
  assert.deepEqual(JSON.parse(calls[0].init.body), {
    version: 3,
    hostname: "cn002",
    role: "COMPUTE",
  });
});

await test("F004 updateResource：description 显式 null = 清空", async () => {
  respond = () => jsonResponse(200, { resource: { id: "r1" } });
  await updateResource("r1", { version: 3, description: null });
  assert.deepEqual(JSON.parse(calls[0].init.body), { version: 3, description: null });
});

await test("F004 deleteResource：DELETE + version 为 Query 参数；204 → undefined", async () => {
  respond = () => new Response(null, { status: 204 });
  const result = await deleteResource("r1", 5);
  assert.equal(result, undefined);
  assert.equal(calls.length, 1);
  assert.equal(calls[0].url, "/api/v1/resources/r1?version=5");
  assert.equal(calls[0].init.method, "DELETE");
});

await test("F004 restoreResource：POST /{id}/restore + version Query 参数", async () => {
  respond = () => jsonResponse(200, { resource: { id: "r1", deleted_at: null, version: 7 } });
  const { resource } = await restoreResource("r1", 6);
  assert.equal(resource.deleted_at, null);
  assert.equal(calls.length, 1);
  assert.equal(calls[0].url, "/api/v1/resources/r1/restore?version=6");
  assert.equal(calls[0].init.method, "POST");
});

await test("F004 getResourceActivity：GET /{id}/activity + deleted/page/page_size", async () => {
  respond = () =>
    jsonResponse(200, {
      items: [
        {
          id: "a1",
          action: "CREATE",
          operator_user_id: null,
          operator_username: "bootstrap",
          before_data: null,
          after_data: { hostname: "cn001" },
          created_at: "2026-10-08T08:00:00Z",
        },
      ],
      page: 1,
      page_size: 50,
      total: 1,
    });
  const data = await getResourceActivity("r1", { deleted: true, page: 1, page_size: 50 });
  assert.equal(data.total, 1);
  assert.equal(data.items[0].action, "CREATE");
  assert.equal(calls.length, 1);
  assert.equal(calls[0].url, "/api/v1/resources/r1/activity?deleted=true&page=1&page_size=50");
});

await test("F004 409 CONFLICT unique_conflict：落到 hostname 字段级错误；不重试", async () => {
  respond = () =>
    jsonResponse(409, {
      error: {
        code: "CONFLICT",
        message: "Conflict",
        details: { reason: "unique_conflict", field: "hostname" },
      },
    });
  const err = await expectApiError(
    createResource({ cluster: "c1", hostname: "cn001", resource_type: "BARE_METAL" }),
  );
  assert.equal(err.status, 409);
  assert.equal(err.code, "CONFLICT");
  assert.equal(err.details.reason, "unique_conflict");
  const described = describeResourceActionError(err);
  assert.equal(described.versionConflict, false);
  assert.ok(described.fields.hostname, "unique_conflict 应落到 hostname 字段错误");
  assert.ok(described.fields.hostname.includes("归一化"));
  assert.equal(calls.length, 1); // 不自动重试
});

await test("F004 409 VERSION_CONFLICT：标记刷新后重改、携带 current_version；不重试", async () => {
  respond = () =>
    jsonResponse(409, {
      error: {
        code: "VERSION_CONFLICT",
        message: "Version conflict",
        details: { current_version: 9 },
      },
    });
  const err = await expectApiError(updateResource("r1", { version: 3, hostname: "x" }));
  assert.equal(err.details.current_version, 9);
  const described = describeResourceActionError(err);
  assert.equal(described.versionConflict, true);
  assert.equal(described.currentVersion, 9);
  assert.ok(described.message.includes("刷新"), "应提示刷新后重改");
  assert.ok(described.message.includes("不会自动重试"));
  assert.equal(calls.length, 1); // 不静默重试覆盖
});

await test("F004 409 CONFLICT dependency_deleted：恢复时解析 conflicts（所属 Cluster）", async () => {
  respond = () =>
    jsonResponse(409, {
      error: {
        code: "CONFLICT",
        message: "Conflict",
        details: {
          reason: "dependency_deleted",
          conflicts: [{ object_type: "cluster", object_id: "c1" }],
        },
      },
    });
  const err = await expectApiError(restoreResource("r1", 2));
  const described = describeResourceActionError(err);
  assert.equal(described.versionConflict, false);
  assert.equal(described.conflicts.length, 1);
  assert.equal(described.conflicts[0].object_type, "cluster");
  assert.equal(described.conflicts[0].object_id, "c1");
  assert.ok(described.message.includes("集群仍处于已删除状态"));
});

await test("F004 409 CONFLICT not_deleted：恢复未删对象的明确文案", async () => {
  respond = () =>
    jsonResponse(409, {
      error: { code: "CONFLICT", message: "Conflict", details: { reason: "not_deleted" } },
    });
  const err = await expectApiError(restoreResource("r1", 2));
  const described = describeResourceActionError(err);
  assert.ok(described.message.includes("未处于已删除状态"));
  assert.ok(described.message.includes("CONFLICT/not_deleted"));
});

await test("F004 422 VALIDATION_ERROR：details.fields 透传为字段级错误（含 cluster）", async () => {
  respond = () =>
    jsonResponse(422, {
      error: {
        code: "VALIDATION_ERROR",
        message: "Validation error",
        details: {
          fields: [
            { field: "cluster", message: "集群不存在或已删除" },
            { field: "hostname", message: "hostname 不能含内部空白" },
          ],
        },
      },
    });
  const err = await expectApiError(
    createResource({ cluster: "nope", hostname: "cn 001", resource_type: "BARE_METAL" }),
  );
  const described = describeResourceActionError(err);
  assert.equal(described.fields.cluster, "集群不存在或已删除");
  assert.equal(described.fields.hostname, "hostname 不能含内部空白");
});

await test("F004 404 / 403：明确文案（不泄露存在性 / 权限不足）", async () => {
  respond = () =>
    jsonResponse(404, { error: { code: "NOT_FOUND", message: "Not found", details: {} } });
  const notFound = await expectApiError(getResource("r1"));
  assert.ok(describeResourceActionError(notFound).message.includes("不存在"));

  respond = () =>
    jsonResponse(403, {
      error: { code: "FORBIDDEN", message: "Forbidden", details: { reason: "permission" } },
    });
  const forbidden = await expectApiError(deleteResource("r1", 1));
  assert.ok(describeResourceActionError(forbidden).message.includes("权限"));
});

await test("F004 网络层错误（fetch reject）：不伪装成业务结果", async () => {
  respond = () => Promise.reject(new TypeError("Failed to fetch"));
  await assert.rejects(listResources(), TypeError);
  assert.equal(calls.length, 1); // 失败不重发
});

// ---------- F005 BareMetal hardware 机制级（Contract：docs/api/F004.md v2 §2.4） ----------

/** 全部未登记（null / {}）的解析后 hardware 值，供各用例展开复用。 */
const HARDWARE_ALL_NULL = {
  manufacturer: null,
  model: null,
  serial_number: null,
  cpu_model: null,
  cpu_sockets: null,
  cpu_cores: null,
  memory_mb: null,
  gpu_model: null,
  gpu_count: null,
  metadata: {},
};

await test("F005 parseHardwareFormValues：合法值（trim / 严格整数 / 空串=null / gpu_count=0）", async () => {
  const parsed = parseHardwareFormValues({
    manufacturer: "  Dell  ",
    model: "PowerEdge R760",
    serial_number: "JH1234567X",
    cpu_model: "AMD EPYC 9654",
    cpu_sockets: "2",
    cpu_cores: "192",
    memory_mb: "1572864",
    gpu_model: "",
    gpu_count: "0",
    metadata: "", // metadata 文本由调用方经 parseMetadataText 另行解析（本函数只处理 9 字段）
  });
  assert.equal(parsed.ok, true);
  assert.deepEqual(parsed.fields, {
    manufacturer: "Dell", // 服务端同样 trim 后存储
    model: "PowerEdge R760",
    serial_number: "JH1234567X",
    cpu_model: "AMD EPYC 9654",
    cpu_sockets: 2,
    cpu_cores: 192,
    memory_mb: 1572864,
    gpu_model: null, // 空串 = 未登记（null，不以 0 代替）
    gpu_count: 0, // 0 = 明确无 GPU，与 null=未知可区分（A2）
  });
});

await test("F005 parseHardwareFormValues：非法输入 → 字段级错误（纯空白 / 超长 / 非整数 / 越界）", async () => {
  const parsed = parseHardwareFormValues({
    manufacturer: "   ",
    model: "x".repeat(256),
    serial_number: "JH1",
    cpu_model: "EPYC",
    cpu_sockets: "0",
    cpu_cores: "1.5",
    memory_mb: "-1",
    gpu_model: "H100",
    gpu_count: "-1",
    metadata: "",
  });
  assert.equal(parsed.ok, false);
  assert.ok(parsed.errors.manufacturer.includes("空白"), "纯空白字符串应报错（不转 null）");
  assert.ok(parsed.errors.model.includes("255"), "超过 255 code point 应报错");
  assert.ok(parsed.errors.cpu_sockets.includes("正整数"), "cpu_sockets=0 应报正整数错误");
  assert.ok(parsed.errors.cpu_cores.includes("整数"), "cpu_cores=1.5 应报整数错误");
  assert.ok(parsed.errors.memory_mb.includes("正整数"), "memory_mb=-1 应报正整数错误");
  assert.ok(parsed.errors.gpu_count.includes("非负整数"), "gpu_count=-1 应报非负整数错误");
});

await test("F005 buildHardwareCreateInput：仅携带已登记子字段；全空 → undefined；gpu_count=0 照常携带", async () => {
  const input = buildHardwareCreateInput({
    ...HARDWARE_ALL_NULL,
    serial_number: "JH1234567X",
    gpu_count: 0,
  });
  assert.deepEqual(input, { serial_number: "JH1234567X", gpu_count: 0 });
  // 全部留空 → 整体省略 hardware 键（等效全 null，Contract §2.4）
  assert.equal(buildHardwareCreateInput(HARDWARE_ALL_NULL), undefined);
  // 仅 metadata 有内容 → hardware 键仍需携带
  const withMetadata = buildHardwareCreateInput({
    ...HARDWARE_ALL_NULL,
    metadata: { psu: "2000W" },
  });
  assert.deepEqual(withMetadata, { metadata: { psu: "2000W" } });
});

await test("F005 buildHardwarePatch：子字段级 exclude_unset 镜像（省略=保持；null=清空；0≠null；metadata 整值替换）", async () => {
  const current = {
    manufacturer: "Dell",
    model: null,
    serial_number: "JH1234567X",
    cpu_model: "AMD EPYC 9654",
    cpu_sockets: 2,
    cpu_cores: 192,
    memory_mb: 1572864,
    gpu_model: null,
    gpu_count: null,
    metadata: { psu: "2000W" },
  };
  const sameAsCurrent = {
    ...HARDWARE_ALL_NULL,
    manufacturer: "Dell",
    serial_number: "JH1234567X",
    cpu_model: "AMD EPYC 9654",
    cpu_sockets: 2,
    cpu_cores: 192,
    memory_mb: 1572864,
    metadata: { psu: "2000W" },
  };
  // 无变化 → null（PATCH 省略 hardware 键）
  assert.equal(buildHardwarePatch(current, sameAsCurrent), null);
  // manufacturer 清空（显式 null）、gpu_count null→0（明确无 GPU）
  const patch = buildHardwarePatch(current, {
    ...sameAsCurrent,
    manufacturer: null,
    gpu_count: 0,
  });
  assert.deepEqual(patch, { manufacturer: null, gpu_count: 0 });
  // gpu_count 0→null（从“明确无 GPU”回到未知）；其余保持
  const withZero = { ...current, gpu_count: 0 };
  const patchZeroToNull = buildHardwarePatch(withZero, sameAsCurrent);
  assert.deepEqual(patchZeroToNull, { gpu_count: null });
  // metadata 整值替换（变化才携带，非 null）
  const patchMetadata = buildHardwarePatch(current, {
    ...sameAsCurrent,
    metadata: { rack: "R42" },
  });
  assert.deepEqual(patchMetadata, { metadata: { rack: "R42" } });
  // current 为 null（旧版后端响应 / 防御）→ 按“全部未登记”比较，无变化 → null
  assert.equal(buildHardwarePatch(null, HARDWARE_ALL_NULL), null);
});

await test("F005 hardwareFormValuesFromResource：null → 全空；数值 / metadata 字符串化；空 metadata → 空文本", async () => {
  assert.deepEqual(hardwareFormValuesFromResource(null), emptyHardwareFormValues());
  const values = hardwareFormValuesFromResource({
    manufacturer: "Dell",
    model: null,
    serial_number: "JH1234567X",
    cpu_model: "AMD EPYC 9654",
    cpu_sockets: 2,
    cpu_cores: 192,
    memory_mb: 1572864,
    gpu_model: null,
    gpu_count: 0,
    metadata: { psu: "2000W" },
  });
  assert.equal(values.manufacturer, "Dell");
  assert.equal(values.model, ""); // null → 空串（表单未登记）
  assert.equal(values.gpu_count, "0"); // 0 不得丢成空串（与 null 可区分）
  assert.equal(values.memory_mb, "1572864");
  assert.deepEqual(JSON.parse(values.metadata), { psu: "2000W" });
  // metadata 为空对象 → 空文本（不显示 "{}" 噪音）
  const emptyMetadata = hardwareFormValuesFromResource(HARDWARE_ALL_NULL);
  assert.equal(emptyMetadata.metadata, "");
});

await test("F005 createResource BARE_METAL：hardware 嵌套对象进 body；响应解析 hardware（0 与 null 可区分）", async () => {
  respond = () =>
    jsonResponse(201, {
      resource: {
        id: "r9",
        cluster: { id: "c1", code: "N96P", name: "N96P集群" },
        hostname: "cn009",
        resource_type: "BARE_METAL",
        role: "OTHER",
        status: "UNKNOWN",
        description: null,
        metadata: {},
        hardware: {
          manufacturer: "Dell",
          model: null,
          serial_number: "JH1234567X",
          cpu_model: "AMD EPYC 9654",
          cpu_sockets: 2,
          cpu_cores: 192,
          memory_mb: 1572864,
          gpu_model: null,
          gpu_count: 0,
          metadata: {},
        },
        version: 1,
        created_at: "2026-10-09T08:00:00Z",
        updated_at: "2026-10-09T08:00:00Z",
        deleted_at: null,
      },
    });
  const { resource } = await createResource({
    cluster: "c1",
    hostname: "cn009",
    resource_type: "BARE_METAL",
    hardware: {
      manufacturer: "Dell",
      serial_number: "JH1234567X",
      cpu_model: "AMD EPYC 9654",
      cpu_sockets: 2,
      cpu_cores: 192,
      memory_mb: 1572864,
      gpu_count: 0,
    },
  });
  assert.equal(resource.hardware.cpu_cores, 192);
  assert.equal(resource.hardware.gpu_count, 0); // A2：0 存 0
  assert.equal(resource.hardware.gpu_model, null); // A1：未登记返回 null 不返回 0
  assert.equal(calls.length, 1);
  assert.equal(calls[0].url, "/api/v1/resources");
  assert.equal(calls[0].init.method, "POST");
  assert.deepEqual(JSON.parse(calls[0].init.body), {
    cluster: "c1",
    hostname: "cn009",
    resource_type: "BARE_METAL",
    hardware: {
      manufacturer: "Dell",
      serial_number: "JH1234567X",
      cpu_model: "AMD EPYC 9654",
      cpu_sockets: 2,
      cpu_cores: 192,
      memory_mb: 1572864,
      gpu_count: 0,
    },
  });
});

await test("F005 createResource VIRTUAL_MACHINE：载荷不含 hardware 键（出现即 422，DR-51）；响应 hardware=null", async () => {
  respond = () =>
    jsonResponse(201, {
      resource: {
        id: "r10",
        cluster: { id: "c1", code: "N96P", name: "N96P集群" },
        hostname: "vm001",
        resource_type: "VIRTUAL_MACHINE",
        role: "OTHER",
        status: "UNKNOWN",
        description: null,
        metadata: {},
        hardware: null,
        version: 1,
        created_at: "2026-10-09T08:00:00Z",
        updated_at: "2026-10-09T08:00:00Z",
        deleted_at: null,
      },
    });
  const { resource } = await createResource({
    cluster: "c1",
    hostname: "vm001",
    resource_type: "VIRTUAL_MACHINE",
    // 页面对 VIRTUAL_MACHINE 不设置 hardware（undefined 经 JSON.stringify 丢弃）
    hardware: undefined,
  });
  assert.equal(resource.hardware, null);
  const body = JSON.parse(calls[0].init.body);
  assert.ok(!("hardware" in body), "VM 载荷不得携带 hardware 键（DR-51）");
});

await test("F005 updateResource：hardware 子字段级 PATCH（version + 变化子字段，含显式 null 清空）", async () => {
  respond = () => jsonResponse(200, { resource: { id: "r9", version: 4 } });
  const { resource } = await updateResource("r9", {
    version: 3,
    hardware: { manufacturer: null, gpu_count: 0, memory_mb: 1572864 },
  });
  assert.equal(resource.version, 4);
  assert.equal(calls.length, 1);
  assert.equal(calls[0].url, "/api/v1/resources/r9");
  assert.equal(calls[0].init.method, "PATCH");
  // 省略子字段 = 保持原值；显式 null = 清空（Contract §2.4/§6.4）
  assert.deepEqual(JSON.parse(calls[0].init.body), {
    version: 3,
    hardware: { manufacturer: null, gpu_count: 0, memory_mb: 1572864 },
  });
});

await test("F005 422 VALIDATION_ERROR：hardware 点路径字段错误透传（hardware.cpu_cores / hardware）", async () => {
  respond = () =>
    jsonResponse(422, {
      error: {
        code: "VALIDATION_ERROR",
        message: "Validation error",
        details: {
          fields: [
            { field: "hardware.cpu_cores", message: "cpu_cores 必须为正整数" },
            { field: "hardware", message: "VIRTUAL_MACHINE 不接受 hardware" },
          ],
        },
      },
    });
  const err = await expectApiError(
    createResource({ cluster: "c1", hostname: "cn001", resource_type: "BARE_METAL" }),
  );
  const described = describeResourceActionError(err);
  assert.equal(described.fields["hardware.cpu_cores"], "cpu_cores 必须为正整数");
  assert.equal(described.fields["hardware"], "VIRTUAL_MACHINE 不接受 hardware");
});

// ---------- F006 VirtualMachine 机制级（Contract：docs/api/F004.md v3 §2.5） ----------

/** 全部未登记（null）的解析后 virtual_machine 值，供各用例展开复用。 */
const VM_ALL_NULL = {
  host_resource_id: "h-uuid-1",
  vcpu: null,
  memory_mb: null,
  disk_gb: null,
  hypervisor: null,
};

await test("F006 parseVirtualMachineFormValues：合法值（trim / 严格整数 / 空串=null / disk_gb=0）", async () => {
  const parsed = parseVirtualMachineFormValues({
    host_resource_id: "0b9f4c6b-8f82-4b7a-9b95-a1e93b1f0101",
    vcpu: "8",
    memory_mb: " 16384 ",
    disk_gb: "0",
    hypervisor: "  VMware ESXi  ",
  });
  assert.equal(parsed.ok, true);
  assert.deepEqual(parsed.fields, {
    host_resource_id: "0b9f4c6b-8f82-4b7a-9b95-a1e93b1f0101",
    vcpu: 8,
    memory_mb: 16384, // 服务端同样 trim；单位 MiB 原样存储不换算
    disk_gb: 0, // 0 = 明确无磁盘，与 null=未知可区分（A11）
    hypervisor: "VMware ESXi", // trim 后存储
  });
});

await test("F006 parseVirtualMachineFormValues：非法输入 → 字段级错误（未选宿主 / 0 / 负 / 非整数 / 纯空白 / 超长）", async () => {
  const parsed = parseVirtualMachineFormValues({
    host_resource_id: "",
    vcpu: "0",
    memory_mb: "-1",
    disk_gb: "-1",
    hypervisor: "   ",
  });
  assert.equal(parsed.ok, false);
  assert.ok(parsed.errors.host_resource_id.includes("必须选择宿主机"), "未选宿主应报错（A3）");
  assert.ok(parsed.errors.vcpu.includes("正整数"), "vcpu=0 应报正整数错误（A9）");
  assert.ok(parsed.errors.memory_mb.includes("正整数"), "memory_mb=-1 应报正整数错误");
  assert.ok(parsed.errors.disk_gb.includes("非负整数"), "disk_gb=-1 应报非负整数错误（A11）");
  assert.ok(parsed.errors.hypervisor.includes("空白"), "纯空白 hypervisor 应报错（不转 null）");
  // 超长 hypervisor 与非整数 vcpu
  const parsed2 = parseVirtualMachineFormValues({
    host_resource_id: "h1",
    vcpu: "1.5",
    memory_mb: "",
    disk_gb: "",
    hypervisor: "x".repeat(256),
  });
  assert.equal(parsed2.ok, false);
  assert.ok(parsed2.errors.vcpu.includes("整数"), "vcpu=1.5 应报整数错误（严格整数语义）");
  assert.ok(parsed2.errors.hypervisor.includes("255"), "hypervisor 超过 255 code point 应报错");
});

await test("F006 buildVirtualMachineCreateInput：恒携带 host_resource_id；容量仅携带已登记值；disk_gb=0 照常携带", async () => {
  // 仅宿主（容量全部省略 → null，无默认 0）
  assert.deepEqual(buildVirtualMachineCreateInput(VM_ALL_NULL), {
    host_resource_id: "h-uuid-1",
  });
  // 全字段登记
  assert.deepEqual(
    buildVirtualMachineCreateInput({
      ...VM_ALL_NULL,
      vcpu: 8,
      memory_mb: 1572864,
      disk_gb: 0,
      hypervisor: "KVM",
    }),
    {
      host_resource_id: "h-uuid-1",
      vcpu: 8,
      memory_mb: 1572864,
      disk_gb: 0,
      hypervisor: "KVM",
    },
  );
});

await test("F006 buildVirtualMachinePatch：子字段级 exclude_unset 镜像（省略=保持；null=清空；换 Host；0≠null）", async () => {
  const current = {
    host_resource_id: "h-uuid-1",
    host: { id: "h-uuid-1", hostname: "cn001" },
    vcpu: 8,
    memory_mb: 16384,
    disk_gb: 0,
    hypervisor: "KVM",
  };
  const sameAsCurrent = { ...VM_ALL_NULL, vcpu: 8, memory_mb: 16384, disk_gb: 0, hypervisor: "KVM" };
  // 无变化 → null（PATCH 省略 virtual_machine 键）
  assert.equal(buildVirtualMachinePatch(current, sameAsCurrent), null);
  // 换 Host（同 Cluster 未删除 BARE_METAL 由服务端校验）+ 清空 hypervisor
  const patch = buildVirtualMachinePatch(current, {
    ...sameAsCurrent,
    host_resource_id: "h-uuid-2",
    hypervisor: null,
  });
  assert.deepEqual(patch, { host_resource_id: "h-uuid-2", hypervisor: null });
  // 容量清空（显式 null）；disk_gb 0→null（从「明确无磁盘」回到未知）
  const clearPatch = buildVirtualMachinePatch(current, {
    ...VM_ALL_NULL,
    host_resource_id: "h-uuid-1",
  });
  assert.deepEqual(clearPatch, { vcpu: null, memory_mb: null, disk_gb: null, hypervisor: null });
  // disk_gb null→0（登记「明确无磁盘」）仅携带变化子字段
  const zeroPatch = buildVirtualMachinePatch(
    { ...current, disk_gb: null, vcpu: null, memory_mb: null, hypervisor: null },
    sameAsCurrent,
  );
  assert.deepEqual(zeroPatch, { vcpu: 8, memory_mb: 16384, disk_gb: 0, hypervisor: "KVM" });
  // current 为 null（旧版后端 / 防御）→ 按“全部未登记”比较；宿主为空时无变化 → null
  // （表单本地校验保证实际调用时宿主非空，此处仅防御性镜像）
  assert.equal(
    buildVirtualMachinePatch(null, { ...VM_ALL_NULL, host_resource_id: "" }),
    null,
  );
});

await test("F006 virtualMachineFormValuesFromResource：null → 全空；数值 0 不丢成空串；null → 空串", async () => {
  assert.deepEqual(virtualMachineFormValuesFromResource(null), emptyVirtualMachineFormValues());
  const values = virtualMachineFormValuesFromResource({
    host_resource_id: "h-uuid-1",
    host: { id: "h-uuid-1", hostname: "cn001" },
    vcpu: 8,
    memory_mb: null,
    disk_gb: 0,
    hypervisor: null,
  });
  assert.equal(values.host_resource_id, "h-uuid-1");
  assert.equal(values.vcpu, "8");
  assert.equal(values.memory_mb, ""); // null → 空串（未登记）
  assert.equal(values.disk_gb, "0"); // 0 不得丢成空串（与 null 可区分，A11）
  assert.equal(values.hypervisor, "");
});

await test("F006 listResources host_resource_id 过滤（配 type=VIRTUAL_MACHINE，DR-67）；空串不发", async () => {
  respond = () => jsonResponse(200, { items: [], page: 1, page_size: 20, total: 0 });
  await listResources({
    cluster_id: "0b9f4c6b-8f82-4b7a-9b95-a1e93b1f0004",
    host_resource_id: "0b9f4c6b-8f82-4b7a-9b95-a1e93b1f0101",
    type: "VIRTUAL_MACHINE",
  });
  assert.equal(calls.length, 1);
  assert.equal(
    calls[0].url,
    "/api/v1/resources?cluster_id=0b9f4c6b-8f82-4b7a-9b95-a1e93b1f0004" +
      "&host_resource_id=0b9f4c6b-8f82-4b7a-9b95-a1e93b1f0101&type=VIRTUAL_MACHINE",
  );
  // 空串 → 不发该参数
  await listResources({ host_resource_id: "" });
  assert.equal(calls[1].url, "/api/v1/resources");
});

await test("F006 createResource VIRTUAL_MACHINE：virtual_machine 嵌套对象进 body；响应解析 host 展开（0 与 null 可区分）", async () => {
  respond = () =>
    jsonResponse(201, {
      resource: {
        id: "r20",
        cluster: { id: "c1", code: "N96P", name: "N96P集群" },
        hostname: "vm001",
        resource_type: "VIRTUAL_MACHINE",
        role: "OTHER",
        status: "UNKNOWN",
        description: null,
        metadata: {},
        hardware: null,
        virtual_machine: {
          host_resource_id: "h-uuid-1",
          host: { id: "h-uuid-1", hostname: "cn001" },
          vcpu: 8,
          memory_mb: 1572864,
          disk_gb: 0,
          hypervisor: "KVM",
        },
        version: 1,
        created_at: "2026-10-09T08:00:00Z",
        updated_at: "2026-10-09T08:00:00Z",
        deleted_at: null,
      },
    });
  const { resource } = await createResource({
    cluster: "c1",
    hostname: "vm001",
    resource_type: "VIRTUAL_MACHINE",
    virtual_machine: {
      host_resource_id: "h-uuid-1",
      vcpu: 8,
      memory_mb: 1572864,
      disk_gb: 0,
      hypervisor: "KVM",
    },
  });
  assert.equal(resource.virtual_machine.host.hostname, "cn001"); // A16：host 展开供详情展示
  assert.equal(resource.virtual_machine.disk_gb, 0); // 0 存 0（明确无磁盘）
  assert.equal(resource.hardware, null); // 互斥：VM 响应 hardware 恒为 null
  assert.equal(calls.length, 1);
  assert.equal(calls[0].url, "/api/v1/resources");
  assert.equal(calls[0].init.method, "POST");
  const body = JSON.parse(calls[0].init.body);
  assert.deepEqual(body, {
    cluster: "c1",
    hostname: "vm001",
    resource_type: "VIRTUAL_MACHINE",
    virtual_machine: {
      host_resource_id: "h-uuid-1",
      vcpu: 8,
      memory_mb: 1572864,
      disk_gb: 0,
      hypervisor: "KVM",
    },
  });
  assert.ok(!("hardware" in body), "VM 载荷不得携带 hardware 键（互斥，DR-51/§2.5）");
});

await test("F006 createResource VIRTUAL_MACHINE 最小载荷：仅 host_resource_id（容量省略 → null）", async () => {
  respond = () =>
    jsonResponse(201, {
      resource: {
        id: "r21",
        cluster: { id: "c1", code: "N96P", name: "N96P集群" },
        hostname: "vm002",
        resource_type: "VIRTUAL_MACHINE",
        role: "OTHER",
        status: "UNKNOWN",
        description: null,
        metadata: {},
        hardware: null,
        virtual_machine: {
          host_resource_id: "h-uuid-1",
          host: { id: "h-uuid-1", hostname: "cn001" },
          vcpu: null,
          memory_mb: null,
          disk_gb: null,
          hypervisor: null,
        },
        version: 1,
        created_at: "2026-10-09T08:00:00Z",
        updated_at: "2026-10-09T08:00:00Z",
        deleted_at: null,
      },
    });
  const { resource } = await createResource({
    cluster: "c1",
    hostname: "vm002",
    resource_type: "VIRTUAL_MACHINE",
    virtual_machine: { host_resource_id: "h-uuid-1" },
  });
  // A8：容量省略保存 null，详情返回 null 不返回 0
  assert.equal(resource.virtual_machine.vcpu, null);
  assert.equal(resource.virtual_machine.memory_mb, null);
  assert.equal(resource.virtual_machine.disk_gb, null);
  assert.deepEqual(JSON.parse(calls[0].init.body), {
    cluster: "c1",
    hostname: "vm002",
    resource_type: "VIRTUAL_MACHINE",
    virtual_machine: { host_resource_id: "h-uuid-1" },
  });
});

await test("F006 updateResource：virtual_machine 子字段级 PATCH（换 Host + 清空容量，version 必带）", async () => {
  respond = () => jsonResponse(200, { resource: { id: "r20", version: 4 } });
  const { resource } = await updateResource("r20", {
    version: 3,
    virtual_machine: { host_resource_id: "h-uuid-2", vcpu: null, memory_mb: 16384 },
  });
  assert.equal(resource.version, 4);
  assert.equal(calls.length, 1);
  assert.equal(calls[0].url, "/api/v1/resources/r20");
  assert.equal(calls[0].init.method, "PATCH");
  // 省略子字段 = 保持原值；显式 null = 清空；换 Host = 携带新 host_resource_id
  assert.deepEqual(JSON.parse(calls[0].init.body), {
    version: 3,
    virtual_machine: { host_resource_id: "h-uuid-2", vcpu: null, memory_mb: 16384 },
  });
});

await test("F006 422 VALIDATION_ERROR：virtual_machine 点路径字段错误透传（host 宿主校验 / vcpu）", async () => {
  respond = () =>
    jsonResponse(422, {
      error: {
        code: "VALIDATION_ERROR",
        message: "Validation error",
        details: {
          fields: [
            {
              field: "virtual_machine.host_resource_id",
              message: "宿主资源不存在、已删除、非 BARE_METAL 或与虚拟机不在同一集群",
            },
            { field: "virtual_machine.vcpu", message: "vcpu 必须为正整数" },
          ],
        },
      },
    });
  const err = await expectApiError(
    createResource({
      cluster: "c1",
      hostname: "vm003",
      resource_type: "VIRTUAL_MACHINE",
      virtual_machine: { host_resource_id: "bad-host", vcpu: 0 },
    }),
  );
  const described = describeResourceActionError(err);
  assert.equal(
    described.fields["virtual_machine.host_resource_id"],
    "宿主资源不存在、已删除、非 BARE_METAL 或与虚拟机不在同一集群",
  );
  assert.equal(described.fields["virtual_machine.vcpu"], "vcpu 必须为正整数");
});

await test("F006 409 CONFLICT reference_exists：宿主机被未删除 VM 引用，解析 references（含 label）；不重试", async () => {
  respond = () =>
    jsonResponse(409, {
      error: {
        code: "CONFLICT",
        message: "Conflict",
        details: {
          reason: "reference_exists",
          references: [
            { object_type: "resource", object_id: "vm-uuid-1", label: "vm001" },
            { object_type: "resource", object_id: "vm-uuid-2", label: "vm002" },
          ],
        },
      },
    });
  const err = await expectApiError(deleteResource("h-uuid-1", 2));
  const described = describeResourceActionError(err);
  assert.equal(described.versionConflict, false);
  assert.equal(described.references.length, 2);
  assert.equal(described.references[0].object_type, "resource");
  assert.equal(described.references[0].label, "vm001");
  assert.ok(described.message.includes("虚拟机"), "提示应指向引用宿主机的虚拟机");
  assert.ok(described.message.includes("无法删除"));
  assert.equal(calls.length, 1); // 不自动重试（不静默重试覆盖）
});

await test("F006 409 CONFLICT dependency_deleted：恢复 VM 时宿主机已删（conflicts object_type=resource）→ Host 文案", async () => {
  respond = () =>
    jsonResponse(409, {
      error: {
        code: "CONFLICT",
        message: "Conflict",
        details: {
          reason: "dependency_deleted",
          conflicts: [{ object_type: "resource", object_id: "h-uuid-1" }],
        },
      },
    });
  const err = await expectApiError(restoreResource("vm-uuid-1", 2));
  const described = describeResourceActionError(err);
  assert.equal(described.versionConflict, false);
  assert.equal(described.conflicts.length, 1);
  assert.equal(described.conflicts[0].object_type, "resource");
  assert.equal(described.conflicts[0].object_id, "h-uuid-1");
  assert.ok(described.message.includes("宿主机"), "恢复 VM 失败应提示宿主机依赖，而非集群文案");
  assert.ok(!described.message.includes("集群仍处于已删除状态"), "不得误用 F004 集群文案");
  assert.ok(described.message.includes("不会覆盖宿主机或其上新对象"), "应说明不覆盖新对象");
});

// ---------- F007 Interface 机制级（Contract：docs/api/F007.md v1） ----------

/** Interface 响应夹具（Contract §3：parent_interface 展开 / null 可区分）。 */
const ifaceFixture = {
  id: "a1b2c3d4-0000-4000-8000-0000000000f1",
  resource: { id: "0b9f4c6b-8f82-4b7a-9b95-a1e93b1f0101", hostname: "node001" },
  name: "eth0",
  interface_type: "PHYSICAL",
  mac_address: "AA:BB:CC:DD:EE:FF",
  speed_mbps: 25000,
  mtu: 9000,
  parent_interface: null,
  enabled: true,
  description: "主网卡",
  metadata: { pci_slot: "3" },
  version: 3,
  created_at: "2026-10-09T12:00:00+00:00",
  updated_at: "2026-10-09T12:00:00+00:00",
  deleted_at: null,
};

await test("F007 listInterfaces：默认 GET /api/v1/interfaces，无查询串", async () => {
  respond = () => jsonResponse(200, { items: [], page: 1, page_size: 20, total: 0 });
  const data = await listInterfaces();
  assert.equal(data.total, 0);
  assert.equal(calls.length, 1);
  assert.equal(calls[0].url, "/api/v1/interfaces");
  assert.equal(calls[0].init.method, "GET");
  assert.equal(calls[0].init.credentials, "include");
});

await test("F007 listInterfaces resource_id 过滤（V19 数据侧：Resource Detail Interfaces 区域）；空串不发", async () => {
  respond = () => jsonResponse(200, { items: [ifaceFixture], page: 1, page_size: 100, total: 1 });
  const data = await listInterfaces({
    resource_id: "0b9f4c6b-8f82-4b7a-9b95-a1e93b1f0101",
    page_size: 100,
    sort: "created_at",
    order: "desc",
  });
  assert.equal(data.items.length, 1);
  assert.equal(data.items[0].name, "eth0");
  assert.equal(data.items[0].speed_mbps, 25000);
  assert.equal(data.items[0].mtu, 9000);
  assert.equal(data.items[0].parent_interface, null);
  assert.equal(calls.length, 1);
  assert.equal(
    calls[0].url,
    "/api/v1/interfaces?resource_id=0b9f4c6b-8f82-4b7a-9b95-a1e93b1f0101" +
      "&page_size=100&sort=created_at&order=desc",
  );
  // 空串 → 不发该参数（同 F004 约定）
  await listInterfaces({ resource_id: "" });
  assert.equal(calls[1].url, "/api/v1/interfaces");
});

await test("F007 listInterfaces 组合查询：interface_type/enabled/q/parent_interface_id/deleted（AND 组合）", async () => {
  respond = () => jsonResponse(200, { items: [], page: 2, page_size: 50, total: 0 });
  await listInterfaces({
    q: "eth",
    interface_type: "PHYSICAL",
    enabled: true,
    parent_interface_id: "a1b2c3d4-0000-4000-8000-0000000000f0",
    deleted: "include",
    page: 2,
    page_size: 50,
    sort: "name",
    order: "asc",
  });
  assert.equal(calls.length, 1);
  assert.equal(
    calls[0].url,
    "/api/v1/interfaces?q=eth&interface_type=PHYSICAL&enabled=true" +
      "&parent_interface_id=a1b2c3d4-0000-4000-8000-0000000000f0" +
      "&deleted=include&page=2&page_size=50&sort=name&order=asc",
  );
});

await test("F007 createInterface：POST body（resource/name 必带，可空仅携带已登记值）；响应解析（parent 展开 / null 可区分）", async () => {
  respond = () => jsonResponse(201, { interface: ifaceFixture });
  const { interface: created } = await createInterface({
    resource: "0b9f4c6b-8f82-4b7a-9b95-a1e93b1f0101",
    name: "eth0",
    interface_type: "PHYSICAL",
    mac_address: "AA:BB:CC:DD:EE:FF",
    speed_mbps: 25000,
    mtu: 9000,
    enabled: true,
    description: "主网卡",
    metadata: { pci_slot: "3" },
  });
  assert.equal(created.id, ifaceFixture.id);
  assert.equal(created.resource.hostname, "node001");
  assert.equal(created.parent_interface, null);
  assert.equal(calls.length, 1);
  assert.equal(calls[0].url, "/api/v1/interfaces");
  assert.equal(calls[0].init.method, "POST");
  assert.deepEqual(JSON.parse(calls[0].init.body), {
    resource: "0b9f4c6b-8f82-4b7a-9b95-a1e93b1f0101",
    name: "eth0",
    interface_type: "PHYSICAL",
    mac_address: "AA:BB:CC:DD:EE:FF",
    speed_mbps: 25000,
    mtu: 9000,
    enabled: true,
    description: "主网卡",
    metadata: { pci_slot: "3" },
  });
});

await test("F007 createInterface 最小载荷：仅 resource + name（其余省略 → 服务端默认）", async () => {
  respond = () => jsonResponse(201, { interface: { ...ifaceFixture, name: "bond0", interface_type: "OTHER" } });
  await createInterface({ resource: "0b9f4c6b-8f82-4b7a-9b95-a1e93b1f0101", name: "bond0" });
  assert.deepEqual(JSON.parse(calls[0].init.body), {
    resource: "0b9f4c6b-8f82-4b7a-9b95-a1e93b1f0101",
    name: "bond0",
  });
});

await test("F007 getInterface：详情 + ?deleted=true（已删需 VIEW_DELETED）", async () => {
  respond = () => jsonResponse(200, { interface: ifaceFixture });
  await getInterface(ifaceFixture.id);
  assert.equal(calls[0].url, `/api/v1/interfaces/${ifaceFixture.id}`);
  await getInterface(ifaceFixture.id, { deleted: true });
  assert.equal(calls[1].url, `/api/v1/interfaces/${ifaceFixture.id}?deleted=true`);
});

await test("F007 updateInterface：PATCH 仅携带变化字段（version 必带，Contract §6.4）", async () => {
  respond = () => jsonResponse(200, { interface: { ...ifaceFixture, version: 4, mtu: 1500 } });
  await updateInterface(ifaceFixture.id, { version: 3, mtu: 1500 });
  assert.equal(calls[0].init.method, "PATCH");
  assert.equal(calls[0].url, `/api/v1/interfaces/${ifaceFixture.id}`);
  assert.deepEqual(JSON.parse(calls[0].init.body), { version: 3, mtu: 1500 });
});

await test("F007 deleteInterface / restoreInterface：version 为 Query 参数（Contract §6.5/§6.6）", async () => {
  respond = () => new Response(null, { status: 204 });
  await deleteInterface(ifaceFixture.id, 3);
  assert.equal(calls[0].init.method, "DELETE");
  assert.equal(calls[0].url, `/api/v1/interfaces/${ifaceFixture.id}?version=3`);
  respond = () => jsonResponse(200, { interface: { ...ifaceFixture, version: 4, deleted_at: null } });
  await restoreInterface(ifaceFixture.id, 3);
  assert.equal(calls[1].init.method, "POST");
  assert.equal(calls[1].url, `/api/v1/interfaces/${ifaceFixture.id}/restore?version=3`);
});

await test("F007 getInterfaceActivity：URL + deleted/page 查询参数（VIEW_ACTIVITY 全角色）", async () => {
  respond = () => jsonResponse(200, { items: [], page: 1, page_size: 20, total: 0 });
  await getInterfaceActivity(ifaceFixture.id, { page: 1, page_size: 20 });
  assert.equal(calls[0].url, `/api/v1/interfaces/${ifaceFixture.id}/activity?page=1&page_size=20`);
  await getInterfaceActivity(ifaceFixture.id, { deleted: true });
  assert.equal(calls[1].url, `/api/v1/interfaces/${ifaceFixture.id}/activity?deleted=true`);
});

await test("F007 409 VERSION_CONFLICT：可识别冲突信号（刷新后重改），不静默重试", async () => {
  respond = () =>
    jsonResponse(409, {
      error: {
        code: "VERSION_CONFLICT",
        message: "数据已被他人修改",
        details: { current_version: 7 },
      },
    });
  const err = await expectApiError(updateInterface(ifaceFixture.id, { version: 6, mtu: 1500 }));
  const described = describeInterfaceActionError(err);
  assert.equal(described.versionConflict, true);
  assert.equal(described.currentVersion, 7);
  assert.ok(described.message.includes("不会自动重试"));
  assert.equal(calls.length, 1); // 不重试（不静默重试覆盖）
});

await test('F007 409 CONFLICT unique_conflict（field="name"）→ name 字段级错误（同资源内唯一，区分大小写）', async () => {
  respond = () =>
    jsonResponse(409, {
      error: {
        code: "CONFLICT",
        message: "Conflict",
        details: { reason: "unique_conflict", field: "name" },
      },
    });
  const err = await expectApiError(
    createInterface({ resource: "0b9f4c6b-8f82-4b7a-9b95-a1e93b1f0101", name: "eth0" }),
  );
  const described = describeInterfaceActionError(err);
  assert.equal(described.versionConflict, false);
  assert.ok(described.fields.name, "unique_conflict 应落为 name 字段级错误");
  assert.ok(described.fields.name.includes("区分大小写"));
  assert.ok(described.message.includes("name 冲突"));
});

await test("F007 409 CONFLICT reference_exists：删除被未删子接口引用 → references（含 label）；不重试", async () => {
  respond = () =>
    jsonResponse(409, {
      error: {
        code: "CONFLICT",
        message: "Conflict",
        details: {
          reason: "reference_exists",
          references: [
            { object_type: "interface", object_id: "a1b2c3d4-0000-4000-8000-0000000000f2", label: "eth0.100" },
            { object_type: "ip_address", object_id: "c1d2e3f4-0000-4000-8000-0000000000f1", label: "10.0.0.1" },
          ],
        },
      },
    });
  const err = await expectApiError(deleteInterface(ifaceFixture.id, 3));
  const described = describeInterfaceActionError(err);
  assert.equal(described.versionConflict, false);
  assert.equal(described.references.length, 2);
  assert.equal(described.references[0].object_type, "interface");
  assert.equal(described.references[0].label, "eth0.100");
  assert.ok(described.message.includes("无法删除"));
  assert.equal(calls.length, 1); // 不自动重试
});

await test("F007 409 CONFLICT dependency_deleted：恢复时父接口仍删（object_type=interface）→ 父接口文案，不覆盖新对象", async () => {
  respond = () =>
    jsonResponse(409, {
      error: {
        code: "CONFLICT",
        message: "Conflict",
        details: {
          reason: "dependency_deleted",
          conflicts: [{ object_type: "interface", object_id: "a1b2c3d4-0000-4000-8000-0000000000f0" }],
        },
      },
    });
  const err = await expectApiError(restoreInterface(ifaceFixture.id, 3));
  const described = describeInterfaceActionError(err);
  assert.equal(described.conflicts.length, 1);
  assert.equal(described.conflicts[0].object_type, "interface");
  assert.ok(described.message.includes("父接口"), "应提示父接口依赖，而非所属资源文案");
  assert.ok(!described.message.includes("所属资源"), "不得误用 resource 文案");
  assert.ok(described.message.includes("不会覆盖父接口或其上新对象"));
});

await test("F007 409 CONFLICT dependency_deleted：恢复时所属 Resource 仍删（object_type=resource）→ 资源文案", async () => {
  respond = () =>
    jsonResponse(409, {
      error: {
        code: "CONFLICT",
        message: "Conflict",
        details: {
          reason: "dependency_deleted",
          conflicts: [{ object_type: "resource", object_id: "0b9f4c6b-8f82-4b7a-9b95-a1e93b1f0101" }],
        },
      },
    });
  const err = await expectApiError(restoreInterface(ifaceFixture.id, 3));
  const described = describeInterfaceActionError(err);
  assert.equal(described.conflicts[0].object_type, "resource");
  assert.ok(described.message.includes("所属资源"));
  assert.ok(described.message.includes("需先恢复所属资源"));
});

await test("F007 409 CONFLICT not_deleted：对未软删对象 restore 的明确文案", async () => {
  respond = () =>
    jsonResponse(409, {
      error: { code: "CONFLICT", message: "Conflict", details: { reason: "not_deleted" } },
    });
  const err = await expectApiError(restoreInterface(ifaceFixture.id, 3));
  const described = describeInterfaceActionError(err);
  assert.ok(described.message.includes("未处于已删除状态"));
});

await test("F007 422 VALIDATION_ERROR：顶层字段路径透传（name / parent_interface / resource，Contract §2.3）", async () => {
  respond = () =>
    jsonResponse(422, {
      error: {
        code: "VALIDATION_ERROR",
        message: "请求体校验失败",
        details: {
          fields: [
            { field: "parent_interface", message: "父接口属于其它资源" },
            { field: "name", message: "name 含内部空白" },
            { field: "resource", message: "资源不存在或已删除" },
          ],
        },
      },
    });
  const err = await expectApiError(
    createInterface({ resource: "0b9f4c6b-0000-4000-8000-00000000dead", name: "eth 0" }),
  );
  const described = describeInterfaceActionError(err);
  assert.equal(described.fields.parent_interface, "父接口属于其它资源");
  assert.equal(described.fields.name, "name 含内部空白");
  assert.equal(described.fields.resource, "资源不存在或已删除");
});

await test("F007 403 / 404：明确文案（权限不足 / 对象不存在，不泄露存在性细节）", async () => {
  respond = () =>
    jsonResponse(403, {
      error: { code: "FORBIDDEN", message: "没有权限", details: { reason: "permission" } },
    });
  const err403 = await expectApiError(deleteInterface(ifaceFixture.id, 3));
  const described403 = describeInterfaceActionError(err403);
  assert.ok(described403.message.includes("没有权限"));
  respond = () =>
    jsonResponse(404, { error: { code: "NOT_FOUND", message: "不存在", details: {} } });
  const err404 = await expectApiError(getInterface(ifaceFixture.id));
  const described404 = describeInterfaceActionError(err404);
  assert.ok(described404.message.includes("接口不存在"));
});

await test("F007 parseInterfaceFormValues：合法值（name trim / mac trim / 正整数 / 空串=null / parent 空串=根接口 null）", async () => {
  const parsed = parseInterfaceFormValues({
    ...emptyInterfaceFormValues(),
    name: "  eth0  ",
    interface_type: "VLAN",
    mac_address: "  AA:BB:CC:DD:EE:FF  ",
    speed_mbps: "25000",
    mtu: "9000",
    parent_interface: "a1b2c3d4-0000-4000-8000-0000000000f0",
    enabled: false,
    description: "子接口",
  });
  assert.equal(parsed.ok, true);
  assert.equal(parsed.fields.name, "eth0"); // trim 后原值（不折叠大小写）
  assert.equal(parsed.fields.mac_address, "AA:BB:CC:DD:EE:FF");
  assert.equal(parsed.fields.speed_mbps, 25000);
  assert.equal(parsed.fields.mtu, 9000);
  assert.equal(parsed.fields.parent_interface, "a1b2c3d4-0000-4000-8000-0000000000f0");
  assert.equal(parsed.fields.description, "子接口");
  assert.equal(parsed.fields.interface_type, "VLAN");
  assert.equal(parsed.fields.enabled, false);
  // 可空字段空串 → null（未知不以 0 代替）
  const emptyParsed = parseInterfaceFormValues({
    ...emptyInterfaceFormValues(),
    name: "eth1",
  });
  assert.equal(emptyParsed.ok, true);
  assert.equal(emptyParsed.fields.mac_address, null);
  assert.equal(emptyParsed.fields.speed_mbps, null);
  assert.equal(emptyParsed.fields.mtu, null);
  assert.equal(emptyParsed.fields.parent_interface, null);
  assert.equal(emptyParsed.fields.description, null);
  assert.equal(emptyParsed.fields.enabled, true); // 默认 true
});

await test("F007 parseInterfaceFormValues：非法输入 → 字段级错误（空名 / 内部空白 / 控制字符 / 超长 / mac 纯空白 / 0 与负整数）", async () => {
  const cases = [
    { values: { name: "   " }, key: "name", hint: "不能为空" },
    { values: { name: "eth 0" }, key: "name", hint: "内部空白" },
    { values: { name: "eth\u00000" }, key: "name", hint: "控制字符" },
    { values: { name: "e".repeat(65) }, key: "name", hint: "长度超过" },
    { values: { mac_address: "   " }, key: "mac_address", hint: "仅包含空白" },
    { values: { mac_address: "a".repeat(65) }, key: "mac_address", hint: "长度超过" },
    { values: { speed_mbps: "0" }, key: "speed_mbps", hint: "正整数" },
    { values: { speed_mbps: "-1" }, key: "speed_mbps", hint: "正整数" },
    { values: { speed_mbps: "1.5" }, key: "speed_mbps", hint: "整数" },
    { values: { mtu: "0" }, key: "mtu", hint: "正整数" },
    { values: { mtu: "2147483648" }, key: "mtu", hint: "正整数" },
  ];
  for (const { values, key, hint } of cases) {
    const parsed = parseInterfaceFormValues({
      ...emptyInterfaceFormValues(),
      name: "eth0",
      ...values,
    });
    assert.equal(parsed.ok, false, `应校验失败：${key}=${JSON.stringify(values[key])}`);
    if (!parsed.ok) {
      assert.ok(parsed.errors[key], `应产生 ${key} 字段错误`);
      assert.ok(
        parsed.errors[key].includes(hint),
        `${key} 错误文案应含「${hint}」，实际：${parsed.errors[key]}`,
      );
    }
  }
  // 边界值合法：1 / 2147483647 / 64 字符 name
  const boundary = parseInterfaceFormValues({
    ...emptyInterfaceFormValues(),
    name: "e".repeat(64),
    speed_mbps: "1",
    mtu: "2147483647",
  });
  assert.equal(boundary.ok, true);
});

await test("F007 buildInterfaceCreateInput：resource/name/type/enabled 恒携带；可空仅携带已登记值；空 metadata 省略", async () => {
  const parsed = parseInterfaceFormValues({
    ...emptyInterfaceFormValues(),
    name: "eth0",
    interface_type: "PHYSICAL",
  });
  assert.equal(parsed.ok, true);
  const input = buildInterfaceCreateInput("0b9f4c6b-8f82-4b7a-9b95-a1e93b1f0101", parsed.fields, {});
  assert.deepEqual(input, {
    resource: "0b9f4c6b-8f82-4b7a-9b95-a1e93b1f0101",
    name: "eth0",
    interface_type: "PHYSICAL",
    enabled: true,
  });
  const full = parseInterfaceFormValues({
    ...emptyInterfaceFormValues(),
    name: "eth0",
    mac_address: "AA:BB:CC:DD:EE:FF",
    speed_mbps: "25000",
    mtu: "9000",
    parent_interface: "a1b2c3d4-0000-4000-8000-0000000000f0",
    description: "主网卡",
    enabled: false,
  });
  assert.equal(full.ok, true);
  const fullInput = buildInterfaceCreateInput("r-uuid", full.fields, { pci_slot: "3" });
  assert.deepEqual(fullInput, {
    resource: "r-uuid",
    name: "eth0",
    interface_type: "OTHER",
    enabled: false,
    mac_address: "AA:BB:CC:DD:EE:FF",
    speed_mbps: 25000,
    mtu: 9000,
    parent_interface: "a1b2c3d4-0000-4000-8000-0000000000f0",
    description: "主网卡",
    metadata: { pci_slot: "3" },
  });
});

await test("F007 buildInterfacePatch：exclude_unset 镜像（无变化 → null；变化才携带；显式 null=清空；version 必带）", async () => {
  // 无变化 → null（不发起空更新）
  const unchanged = parseInterfaceFormValues(interfaceFormValuesFromInterface(ifaceFixture));
  assert.equal(unchanged.ok, true);
  assert.equal(
    buildInterfacePatch(ifaceFixture, unchanged.fields, ifaceFixture.metadata),
    null,
  );
  // 变化：mtu 改值 + mac 清空（显式 null）+ parent 设置（null → UUID）
  const changed = parseInterfaceFormValues({
    ...interfaceFormValuesFromInterface(ifaceFixture),
    mtu: "1500",
    mac_address: "",
    parent_interface: "a1b2c3d4-0000-4000-8000-0000000000f0",
  });
  assert.equal(changed.ok, true);
  const patch = buildInterfacePatch(ifaceFixture, changed.fields, ifaceFixture.metadata);
  assert.deepEqual(patch, {
    version: 3,
    mtu: 1500,
    mac_address: null,
    parent_interface: "a1b2c3d4-0000-4000-8000-0000000000f0",
  });
  // metadata 整值替换（变化才携带）
  const metaChanged = buildInterfacePatch(ifaceFixture, unchanged.fields, { pci_slot: "7" });
  assert.deepEqual(metaChanged, { version: 3, metadata: { pci_slot: "7" } });
});

await test("F007 interfaceFormValuesFromInterface：null → 空串；数值字符串化；parent 提取 id；metadata 空对象 → 空文本", async () => {
  const values = interfaceFormValuesFromInterface({
    ...ifaceFixture,
    parent_interface: { id: "a1b2c3d4-0000-4000-8000-0000000000f0", name: "eth0" },
    metadata: {},
  });
  assert.equal(values.name, "eth0");
  assert.equal(values.parent_interface, "a1b2c3d4-0000-4000-8000-0000000000f0");
  assert.equal(values.speed_mbps, "25000");
  assert.equal(values.mtu, "9000");
  assert.equal(values.metadata, "");
  const nullValues = interfaceFormValuesFromInterface(null);
  assert.deepEqual(nullValues, emptyInterfaceFormValues());
  // 往返：初始化 → 解析 → 无变化（与 buildInterfacePatch=null 联动）
  const roundTrip = parseInterfaceFormValues(interfaceFormValuesFromInterface(ifaceFixture));
  assert.equal(roundTrip.ok, true);
  assert.equal(buildInterfacePatch(ifaceFixture, roundTrip.fields, ifaceFixture.metadata), null);
});

// ---------- F008 Network 机制级（Contract：docs/api/F008.md v1） ----------

/** Network 响应夹具（Contract §3：cluster 展开 / gateway、description 可空）。 */
const networkFixture = {
  id: "0b9f4c6b-8f82-4b7a-9b95-a1e93b1f0801",
  cluster: { id: "0b9f4c6b-8f82-4b7a-9b95-a1e93b1f0004", code: "N96P", name: "N96P集群" },
  name: "MGMT",
  cidr: "10.0.0.0/24",
  gateway: "10.0.0.1",
  status: "ACTIVE",
  auto_allocate: false,
  description: "管理网",
  metadata: { vlan: 100 },
  version: 3,
  created_at: "2026-10-09T12:00:00+00:00",
  updated_at: "2026-10-09T12:00:00+00:00",
  deleted_at: null,
};

await test("F008 listNetworks：默认 GET /api/v1/networks，无查询串", async () => {
  respond = () => jsonResponse(200, { items: [], page: 1, page_size: 20, total: 0 });
  const data = await listNetworks();
  assert.equal(data.total, 0);
  assert.equal(calls.length, 1);
  assert.equal(calls[0].url, "/api/v1/networks");
  assert.equal(calls[0].init.method, "GET");
  assert.equal(calls[0].init.credentials, "include");
});

await test("F008 listNetworks 组合查询：q/cluster_id/status/auto_allocate/deleted/分页/排序（AND 组合）", async () => {
  respond = () => jsonResponse(200, { items: [], page: 2, page_size: 50, total: 0 });
  await listNetworks({
    q: "mgmt",
    cluster_id: "0b9f4c6b-8f82-4b7a-9b95-a1e93b1f0004",
    status: "INACTIVE",
    auto_allocate: true,
    deleted: "include",
    page: 2,
    page_size: 50,
    sort: "cidr",
    order: "asc",
  });
  assert.equal(calls.length, 1);
  assert.equal(
    calls[0].url,
    "/api/v1/networks?q=mgmt&cluster_id=0b9f4c6b-8f82-4b7a-9b95-a1e93b1f0004" +
      "&status=INACTIVE&auto_allocate=true&deleted=include&page=2&page_size=50&sort=cidr&order=asc",
  );
  // 空串过滤项不发；false 也要照常发送（不得因 falsy 丢失）
  await listNetworks({ q: "", cluster_id: "", auto_allocate: false });
  assert.equal(calls[1].url, "/api/v1/networks?auto_allocate=false");
});

await test("F008 createNetwork：POST body（cluster/name/cidr+status/auto_allocate；可空仅携带已登记值）；响应解析", async () => {
  respond = () => jsonResponse(201, { network: networkFixture });
  const { network } = await createNetwork({
    cluster: "0b9f4c6b-8f82-4b7a-9b95-a1e93b1f0004",
    name: "MGMT",
    cidr: "10.0.0.0/24",
    gateway: "10.0.0.1",
    status: "ACTIVE",
    auto_allocate: false,
    description: "管理网",
    metadata: { vlan: 100 },
  });
  assert.equal(network.id, networkFixture.id);
  assert.equal(network.cluster.code, "N96P");
  assert.equal(network.gateway, "10.0.0.1");
  assert.equal(calls.length, 1);
  assert.equal(calls[0].url, "/api/v1/networks");
  assert.equal(calls[0].init.method, "POST");
  assert.deepEqual(JSON.parse(calls[0].init.body), {
    cluster: "0b9f4c6b-8f82-4b7a-9b95-a1e93b1f0004",
    name: "MGMT",
    cidr: "10.0.0.0/24",
    gateway: "10.0.0.1",
    status: "ACTIVE",
    auto_allocate: false,
    description: "管理网",
    metadata: { vlan: 100 },
  });
});

await test("F008 createNetwork 最小载荷：仅 cluster + name + cidr（可空省略 → 服务端默认）", async () => {
  respond = () => jsonResponse(201, { network: { ...networkFixture, gateway: null, description: null } });
  const { network } = await createNetwork({
    cluster: "c1",
    name: "MGMT",
    cidr: "10.0.0.0/24",
  });
  assert.equal(network.gateway, null); // 未设置返回 null，不用空串代替
  assert.deepEqual(JSON.parse(calls[0].init.body), {
    cluster: "c1",
    name: "MGMT",
    cidr: "10.0.0.0/24",
  });
});

await test("F008 getNetwork：详情 + ?deleted=true（已删需 VIEW_DELETED）", async () => {
  respond = () => jsonResponse(200, { network: networkFixture });
  await getNetwork(networkFixture.id);
  assert.equal(calls[0].url, `/api/v1/networks/${networkFixture.id}`);
  await getNetwork(networkFixture.id, { deleted: true });
  assert.equal(calls[1].url, `/api/v1/networks/${networkFixture.id}?deleted=true`);
});

await test("F008 updateNetwork：PATCH 仅携带变化字段（version 必带，Contract §6.4）", async () => {
  respond = () => jsonResponse(200, { network: { ...networkFixture, version: 4, status: "INACTIVE" } });
  await updateNetwork(networkFixture.id, { version: 3, status: "INACTIVE" });
  assert.equal(calls[0].init.method, "PATCH");
  assert.equal(calls[0].url, `/api/v1/networks/${networkFixture.id}`);
  assert.deepEqual(JSON.parse(calls[0].init.body), { version: 3, status: "INACTIVE" });
});

await test("F008 updateNetwork：gateway/description 显式 null = 清空", async () => {
  respond = () => jsonResponse(200, { network: { ...networkFixture, gateway: null } });
  await updateNetwork(networkFixture.id, { version: 3, gateway: null, description: null });
  assert.deepEqual(JSON.parse(calls[0].init.body), {
    version: 3,
    gateway: null,
    description: null,
  });
});

await test("F008 deleteNetwork / restoreNetwork：version 为 Query 参数（Contract §6.5/§6.6）", async () => {
  respond = () => new Response(null, { status: 204 });
  await deleteNetwork(networkFixture.id, 3);
  assert.equal(calls[0].init.method, "DELETE");
  assert.equal(calls[0].url, `/api/v1/networks/${networkFixture.id}?version=3`);
  respond = () => jsonResponse(200, { network: { ...networkFixture, version: 4, deleted_at: null } });
  await restoreNetwork(networkFixture.id, 3);
  assert.equal(calls[1].init.method, "POST");
  assert.equal(calls[1].url, `/api/v1/networks/${networkFixture.id}/restore?version=3`);
});

await test("F008 getNetworkActivity：URL + deleted/page 查询参数（VIEW_ACTIVITY 全角色）", async () => {
  respond = () => jsonResponse(200, { items: [], page: 1, page_size: 20, total: 0 });
  await getNetworkActivity(networkFixture.id, { page: 1, page_size: 20 });
  assert.equal(calls[0].url, `/api/v1/networks/${networkFixture.id}/activity?page=1&page_size=20`);
  await getNetworkActivity(networkFixture.id, { deleted: true });
  assert.equal(calls[1].url, `/api/v1/networks/${networkFixture.id}/activity?deleted=true`);
});

await test("F008 409 VERSION_CONFLICT：可识别冲突信号（刷新后重改），不静默重试", async () => {
  respond = () =>
    jsonResponse(409, {
      error: {
        code: "VERSION_CONFLICT",
        message: "数据已被他人修改",
        details: { current_version: 7 },
      },
    });
  const err = await expectApiError(updateNetwork(networkFixture.id, { version: 6, status: "INACTIVE" }));
  const described = describeNetworkActionError(err);
  assert.equal(described.versionConflict, true);
  assert.equal(described.currentVersion, 7);
  assert.ok(described.message.includes("不会自动重试"));
  assert.equal(calls.length, 1); // 不重试（不静默重试覆盖）
});

await test('F008 409 CONFLICT unique_conflict（field="name"）→ name 字段级错误（同集群大小写不敏感唯一）', async () => {
  respond = () =>
    jsonResponse(409, {
      error: {
        code: "CONFLICT",
        message: "Conflict",
        details: { reason: "unique_conflict", field: "name" },
      },
    });
  const err = await expectApiError(
    createNetwork({ cluster: "c1", name: "mgmt", cidr: "10.0.0.0/24" }),
  );
  const described = describeNetworkActionError(err);
  assert.equal(described.versionConflict, false);
  assert.ok(described.fields.name, "unique_conflict 应落为 name 字段级错误");
  assert.ok(described.fields.name.includes("大小写不敏感"));
  assert.ok(described.message.includes("name 冲突"));
});

await test('F008 409 CONFLICT range_overlap（field="cidr"）→ cidr 字段级错误 + 重叠明细；不重试', async () => {
  respond = () =>
    jsonResponse(409, {
      error: {
        code: "CONFLICT",
        message: "Conflict",
        details: {
          reason: "range_overlap",
          field: "cidr",
          conflicts: [
            { object_type: "network", object_id: "n1", label: "MGMT" },
            { object_type: "network", object_id: "n2", label: null },
          ],
        },
      },
    });
  const err = await expectApiError(
    createNetwork({ cluster: "c1", name: "OTHER", cidr: "10.0.0.0/16" }),
  );
  const described = describeNetworkActionError(err);
  assert.ok(described.fields.cidr, "range_overlap 应落为 cidr 字段级错误");
  assert.ok(described.fields.cidr.includes("INACTIVE"));
  assert.equal(described.rangeConflicts.length, 2);
  assert.equal(described.rangeConflicts[0].object_type, "network");
  assert.equal(described.rangeConflicts[0].label, "MGMT");
  assert.equal(described.rangeConflicts[1].label, null); // label 缺失为 null
  assert.ok(described.message.includes("CONFLICT/range_overlap"));
  assert.equal(calls.length, 1);
});

await test("F008 409 CONFLICT reference_exists：删除/改 cidr 被未删 Pool/IP 引用 → references（含 label）；不重试", async () => {
  respond = () =>
    jsonResponse(409, {
      error: {
        code: "CONFLICT",
        message: "Conflict",
        details: {
          reason: "reference_exists",
          references: [
            { object_type: "ip_pool", object_id: "p1", label: "pool-a" },
            { object_type: "ip_address", object_id: "a1", label: "10.0.0.5" },
          ],
        },
      },
    });
  const err = await expectApiError(deleteNetwork(networkFixture.id, 3));
  const described = describeNetworkActionError(err);
  assert.equal(described.references.length, 2);
  assert.equal(described.references[0].object_type, "ip_pool");
  assert.equal(described.references[1].object_type, "ip_address");
  assert.ok(described.message.includes("无法删除"));
  assert.equal(calls.length, 1);
});

await test("F008 409 CONFLICT dependency_deleted：恢复时所属 Cluster 仍删（object_type=cluster）→ 集群文案，不覆盖新对象", async () => {
  respond = () =>
    jsonResponse(409, {
      error: {
        code: "CONFLICT",
        message: "Conflict",
        details: {
          reason: "dependency_deleted",
          conflicts: [{ object_type: "cluster", object_id: "c1" }],
        },
      },
    });
  const err = await expectApiError(restoreNetwork(networkFixture.id, 3));
  const described = describeNetworkActionError(err);
  assert.equal(described.dependencyConflicts.length, 1);
  assert.equal(described.dependencyConflicts[0].object_type, "cluster");
  assert.ok(described.message.includes("所属集群"));
  assert.ok(described.message.includes("不会覆盖集群或其上新对象"));
});

await test("F008 409 CONFLICT not_deleted：对未软删对象 restore 的明确文案", async () => {
  respond = () =>
    jsonResponse(409, {
      error: { code: "CONFLICT", message: "Conflict", details: { reason: "not_deleted" } },
    });
  const err = await expectApiError(restoreNetwork(networkFixture.id, 3));
  const described = describeNetworkActionError(err);
  assert.ok(described.message.includes("未处于已删除状态"));
});

await test("F008 422 VALIDATION_ERROR：顶层字段路径透传（name / cluster / cidr / gateway / metadata，Contract §2.3）", async () => {
  respond = () =>
    jsonResponse(422, {
      error: {
        code: "VALIDATION_ERROR",
        message: "请求体校验失败",
        details: {
          fields: [
            { field: "cluster", message: "集群不存在或已删除" },
            { field: "cidr", message: "cidr 非法" },
            { field: "gateway", message: "gateway 不属于该 CIDR 或落入禁用范围" },
            { field: "metadata", message: "metadata 必须是对象" },
          ],
        },
      },
    });
  const err = await expectApiError(
    createNetwork({ cluster: "nope", name: "MGMT", cidr: "bad" }),
  );
  const described = describeNetworkActionError(err);
  assert.equal(described.fields.cluster, "集群不存在或已删除");
  assert.equal(described.fields.cidr, "cidr 非法");
  assert.equal(described.fields.gateway, "gateway 不属于该 CIDR 或落入禁用范围");
  assert.equal(described.fields.metadata, "metadata 必须是对象");
});

await test("F008 403 / 404：明确文案（权限不足 / 对象不存在，不泄露存在性细节）", async () => {
  respond = () =>
    jsonResponse(403, {
      error: { code: "FORBIDDEN", message: "没有权限", details: { reason: "permission" } },
    });
  const err403 = await expectApiError(deleteNetwork(networkFixture.id, 3));
  assert.ok(describeNetworkActionError(err403).message.includes("没有权限"));
  respond = () =>
    jsonResponse(404, { error: { code: "NOT_FOUND", message: "不存在", details: {} } });
  const err404 = await expectApiError(getNetwork(networkFixture.id));
  assert.ok(describeNetworkActionError(err404).message.includes("网络不存在"));
});

await test("F008 parseNetworkFormValues：合法值（name trim / cidr 保留 host 位 / gateway trim / 空串=null）", async () => {
  const parsed = parseNetworkFormValues({
    ...emptyNetworkFormValues(),
    cluster: "c1",
    name: "  MGMT  ",
    cidr: " 10.0.0.5/24 ",
    gateway: " 10.0.0.1 ",
    status: "INACTIVE",
    auto_allocate: true,
    description: "管理网",
  });
  assert.equal(parsed.ok, true);
  assert.equal(parsed.fields.name, "MGMT");
  // host 位不归一化（服务端负责 10.0.0.5/24 → 10.0.0.0/24）
  assert.equal(parsed.fields.cidr, "10.0.0.5/24");
  assert.equal(parsed.fields.gateway, "10.0.0.1");
  assert.equal(parsed.fields.status, "INACTIVE");
  assert.equal(parsed.fields.auto_allocate, true);
  assert.equal(parsed.fields.description, "管理网");
  // 可空字段空串 → null
  const emptyParsed = parseNetworkFormValues({
    ...emptyNetworkFormValues(),
    cluster: "c1",
    name: "MGMT",
    cidr: "10.0.0.0/24",
  });
  assert.equal(emptyParsed.ok, true);
  assert.equal(emptyParsed.fields.gateway, null);
  assert.equal(emptyParsed.fields.description, null);
  assert.equal(emptyParsed.fields.status, "ACTIVE"); // 默认 ACTIVE
  assert.equal(emptyParsed.fields.auto_allocate, false); // 默认 false
});

await test("F008 parseNetworkFormValues：非法输入 → 字段级错误（空名 / 控制字符 / 超长 / cidr 非法或 IPv6 / gateway 非法 / 纯空白）", async () => {
  const cases = [
    { values: { name: "   " }, key: "name", hint: "不能为空" },
    { values: { name: "MG\u0000MT" }, key: "name", hint: "控制字符" },
    { values: { name: "n".repeat(256) }, key: "name", hint: "长度超过" },
    { values: { cidr: "" }, key: "cidr", hint: "不能为空" },
    { values: { cidr: "10.0.0.0" }, key: "cidr", hint: "CIDR" },
    { values: { cidr: "10.0.0.256/24" }, key: "cidr", hint: "CIDR" },
    { values: { cidr: "::1/64" }, key: "cidr", hint: "IPv4" },
    { values: { cidr: "10.0.0.0/33" }, key: "cidr", hint: "CIDR" },
    { values: { gateway: "10.0.0" }, key: "gateway", hint: "IPv4" },
    { values: { gateway: "999.1.1.1" }, key: "gateway", hint: "IPv4" },
    { values: { gateway: "   " }, key: "gateway", hint: "仅包含空白" },
  ];
  for (const { values, key, hint } of cases) {
    const parsed = parseNetworkFormValues({
      ...emptyNetworkFormValues(),
      cluster: "c1",
      name: "MGMT",
      cidr: "10.0.0.0/24",
      ...values,
    });
    assert.equal(parsed.ok, false, `应校验失败：${key}=${JSON.stringify(values[key])}`);
    if (!parsed.ok) {
      assert.ok(parsed.errors[key], `应产生 ${key} 字段错误`);
      assert.ok(
        parsed.errors[key].includes(hint),
        `${key} 错误文案应含「${hint}」，实际：${parsed.errors[key]}`,
      );
    }
  }
  // 边界值合法：name 255 字符 / /0 / /32 / host 位
  for (const cidr of ["0.0.0.0/0", "10.0.0.0/32", "172.16.8.9/20"]) {
    const boundary = parseNetworkFormValues({
      ...emptyNetworkFormValues(),
      cluster: "c1",
      name: "n".repeat(255),
      cidr,
    });
    assert.equal(boundary.ok, true, `应接受合法 cidr ${cidr}`);
  }
});

await test("F008 buildNetworkCreateInput：cluster/name/cidr/status/auto_allocate 恒携带；gateway/description 仅已登记值；空 metadata 省略", async () => {
  const parsed = parseNetworkFormValues({
    ...emptyNetworkFormValues(),
    cluster: "c1",
    name: "MGMT",
    cidr: "10.0.0.0/24",
  });
  assert.equal(parsed.ok, true);
  const input = buildNetworkCreateInput("c1", parsed.fields, {});
  assert.deepEqual(input, {
    cluster: "c1",
    name: "MGMT",
    cidr: "10.0.0.0/24",
    status: "ACTIVE",
    auto_allocate: false,
  });
  const full = parseNetworkFormValues({
    ...emptyNetworkFormValues(),
    cluster: "c1",
    name: "MGMT",
    cidr: "10.0.0.0/24",
    gateway: "10.0.0.1",
    status: "INACTIVE",
    auto_allocate: true,
    description: "管理网",
  });
  assert.equal(full.ok, true);
  const fullInput = buildNetworkCreateInput("c1", full.fields, { vlan: 100 });
  assert.deepEqual(fullInput, {
    cluster: "c1",
    name: "MGMT",
    cidr: "10.0.0.0/24",
    status: "INACTIVE",
    auto_allocate: true,
    gateway: "10.0.0.1",
    description: "管理网",
    metadata: { vlan: 100 },
  });
});

await test("F008 buildNetworkPatch：exclude_unset 镜像（无变化 → null；变化才携带；显式 null=清空 gateway/description；可改 cluster）", async () => {
  // 无变化 → null（不发起空更新）
  const unchanged = parseNetworkFormValues(networkFormValuesFromNetwork(networkFixture));
  assert.equal(unchanged.ok, true);
  assert.equal(
    buildNetworkPatch(
      networkFixture,
      networkFixture.cluster.id,
      unchanged.fields,
      networkFixture.metadata,
    ),
    null,
  );
  // 变化：status 改值 + gateway 清空 + 改 cluster
  const changed = parseNetworkFormValues({
    ...networkFormValuesFromNetwork(networkFixture),
    status: "INACTIVE",
    gateway: "",
    cluster: "c2",
  });
  assert.equal(changed.ok, true);
  const patch = buildNetworkPatch(networkFixture, "c2", changed.fields, networkFixture.metadata);
  assert.deepEqual(patch, { version: 3, status: "INACTIVE", gateway: null, cluster: "c2" });
  // description 显式 null 清空 + metadata 整值替换
  const descCleared = parseNetworkFormValues({
    ...networkFormValuesFromNetwork(networkFixture),
    description: "",
  });
  assert.equal(descCleared.ok, true);
  const descPatch = buildNetworkPatch(
    networkFixture,
    networkFixture.cluster.id,
    descCleared.fields,
    { vlan: 200 },
  );
  assert.deepEqual(descPatch, {
    version: 3,
    description: null,
    metadata: { vlan: 200 },
  });
});

await test("F008 networkFormValuesFromNetwork：null → 默认空值；gateway/description 空串；metadata 空对象 → 空文本", async () => {
  const values = networkFormValuesFromNetwork({ ...networkFixture, metadata: {} });
  assert.equal(values.cluster, networkFixture.cluster.id);
  assert.equal(values.name, "MGMT");
  assert.equal(values.cidr, "10.0.0.0/24");
  assert.equal(values.gateway, "10.0.0.1");
  assert.equal(values.metadata, "");
  const nullValues = networkFormValuesFromNetwork(null);
  assert.deepEqual(nullValues, emptyNetworkFormValues());
  // 往返：初始化 → 解析 → 无变化（与 buildNetworkPatch=null 联动）
  const roundTrip = parseNetworkFormValues(networkFormValuesFromNetwork(networkFixture));
  assert.equal(roundTrip.ok, true);
  assert.equal(
    buildNetworkPatch(
      networkFixture,
      networkFixture.cluster.id,
      roundTrip.fields,
      networkFixture.metadata,
    ),
    null,
  );
});

// ---------- F009 IP Pool 机制级（Contract：docs/api/F009.md v1） ----------

/** IPPool 响应夹具（Contract §3：network 展开 / description 可空）。 */
const ipPoolFixture = {
  id: "0b9f4c6b-8f82-4b7a-9b95-a1e93b1f0901",
  network: { id: "0b9f4c6b-8f82-4b7a-9b95-a1e93b1f0801", name: "MGMT", cidr: "10.0.0.0/24" },
  name: "MGMT-POOL",
  start_address: "10.0.0.10",
  end_address: "10.0.0.100",
  allocation_mode: "MANUAL",
  description: "管理网手动池",
  version: 3,
  created_at: "2026-10-09T12:00:00+00:00",
  updated_at: "2026-10-09T12:00:00+00:00",
  deleted_at: null,
};

await test("F009 listIpPools：默认 GET /api/v1/ip-pools，无查询串", async () => {
  respond = () => jsonResponse(200, { items: [], page: 1, page_size: 20, total: 0 });
  const data = await listIpPools();
  assert.equal(data.total, 0);
  assert.equal(calls.length, 1);
  assert.equal(calls[0].url, "/api/v1/ip-pools");
  assert.equal(calls[0].init.method, "GET");
  assert.equal(calls[0].init.credentials, "include");
});

await test("F009 listIpPools 组合查询：network_id/allocation_mode/q/deleted/分页/排序（AND 组合）", async () => {
  respond = () => jsonResponse(200, { items: [], page: 2, page_size: 50, total: 0 });
  await listIpPools({
    network_id: "0b9f4c6b-8f82-4b7a-9b95-a1e93b1f0801",
    allocation_mode: "RESERVED",
    q: "mgmt",
    deleted: "only",
    page: 2,
    page_size: 50,
    sort: "start_address",
    order: "asc",
  });
  assert.equal(calls.length, 1);
  assert.equal(
    calls[0].url,
    "/api/v1/ip-pools?network_id=0b9f4c6b-8f82-4b7a-9b95-a1e93b1f0801" +
      "&allocation_mode=RESERVED&q=mgmt&deleted=only&page=2&page_size=50&sort=start_address&order=asc",
  );
  // 空串过滤项不发（network_id='' / q=''）
  await listIpPools({ network_id: "", q: "" });
  assert.equal(calls[1].url, "/api/v1/ip-pools");
});

await test("F009 createIpPool：POST body（network/name/start/end/mode；description 仅已登记时携带）；响应解析", async () => {
  respond = () => jsonResponse(201, { ip_pool: ipPoolFixture });
  const { ip_pool } = await createIpPool({
    network: "0b9f4c6b-8f82-4b7a-9b95-a1e93b1f0801",
    name: "MGMT-POOL",
    start_address: "10.0.0.10",
    end_address: "10.0.0.100",
    allocation_mode: "MANUAL",
    description: "管理网手动池",
  });
  assert.equal(ip_pool.id, ipPoolFixture.id);
  assert.equal(ip_pool.network.cidr, "10.0.0.0/24"); // network 嵌套展开
  assert.equal(ip_pool.allocation_mode, "MANUAL");
  assert.equal(calls.length, 1);
  assert.equal(calls[0].url, "/api/v1/ip-pools");
  assert.equal(calls[0].init.method, "POST");
  assert.deepEqual(JSON.parse(calls[0].init.body), {
    network: "0b9f4c6b-8f82-4b7a-9b95-a1e93b1f0801",
    name: "MGMT-POOL",
    start_address: "10.0.0.10",
    end_address: "10.0.0.100",
    allocation_mode: "MANUAL",
    description: "管理网手动池",
  });
});

await test("F009 createIpPool 最小载荷：仅 network+name+start+end（mode 省略 → 服务端默认 MANUAL）", async () => {
  respond = () =>
    jsonResponse(201, { ip_pool: { ...ipPoolFixture, description: null } });
  const { ip_pool } = await createIpPool({
    network: "n1",
    name: "P1",
    start_address: "10.0.0.10",
    end_address: "10.0.0.20",
  });
  assert.equal(ip_pool.description, null); // 未设置返回 null，不用空串代替
  assert.deepEqual(JSON.parse(calls[0].init.body), {
    network: "n1",
    name: "P1",
    start_address: "10.0.0.10",
    end_address: "10.0.0.20",
  });
});

await test("F009 getIpPool：详情 + ?deleted=true（已删需 VIEW_DELETED）", async () => {
  respond = () => jsonResponse(200, { ip_pool: ipPoolFixture });
  await getIpPool(ipPoolFixture.id);
  assert.equal(calls[0].url, `/api/v1/ip-pools/${ipPoolFixture.id}`);
  await getIpPool(ipPoolFixture.id, { deleted: true });
  assert.equal(calls[1].url, `/api/v1/ip-pools/${ipPoolFixture.id}?deleted=true`);
});

await test("F009 updateIpPool：PATCH 仅携带变化字段（version 必带，Contract §6.4）", async () => {
  respond = () =>
    jsonResponse(200, { ip_pool: { ...ipPoolFixture, version: 4, allocation_mode: "RESERVED" } });
  await updateIpPool(ipPoolFixture.id, { version: 3, allocation_mode: "RESERVED" });
  assert.equal(calls[0].init.method, "PATCH");
  assert.equal(calls[0].url, `/api/v1/ip-pools/${ipPoolFixture.id}`);
  // body 只含 version + 变化字段；network 不可改不出现（DR-107）
  const body = JSON.parse(calls[0].init.body);
  assert.deepEqual(body, { version: 3, allocation_mode: "RESERVED" });
  assert.ok(!("network" in body), "PATCH 载荷不得携带 network 键（DR-107）");
});

await test("F009 updateIpPool：description 显式 null = 清空", async () => {
  respond = () => jsonResponse(200, { ip_pool: { ...ipPoolFixture, description: null } });
  await updateIpPool(ipPoolFixture.id, { version: 3, description: null });
  assert.deepEqual(JSON.parse(calls[0].init.body), { version: 3, description: null });
});

await test("F009 deleteIpPool / restoreIpPool：version 为 Query 参数（Contract §6.5/§6.6）", async () => {
  respond = () => new Response(null, { status: 204 });
  const result = await deleteIpPool(ipPoolFixture.id, 3);
  assert.equal(result, undefined);
  assert.equal(calls[0].init.method, "DELETE");
  assert.equal(calls[0].url, `/api/v1/ip-pools/${ipPoolFixture.id}?version=3`);
  respond = () =>
    jsonResponse(200, { ip_pool: { ...ipPoolFixture, version: 4, deleted_at: null } });
  const { ip_pool: restored } = await restoreIpPool(ipPoolFixture.id, 3);
  assert.equal(restored.deleted_at, null);
  assert.equal(calls[1].init.method, "POST");
  assert.equal(calls[1].url, `/api/v1/ip-pools/${ipPoolFixture.id}/restore?version=3`);
});

await test("F009 getIpPoolActivity：URL + deleted/page 查询参数（VIEW_ACTIVITY 全角色）", async () => {
  respond = () => jsonResponse(200, { items: [], page: 1, page_size: 20, total: 0 });
  await getIpPoolActivity(ipPoolFixture.id, { page: 1, page_size: 20 });
  assert.equal(calls[0].url, `/api/v1/ip-pools/${ipPoolFixture.id}/activity?page=1&page_size=20`);
  await getIpPoolActivity(ipPoolFixture.id, { deleted: true });
  assert.equal(calls[1].url, `/api/v1/ip-pools/${ipPoolFixture.id}/activity?deleted=true`);
});

await test("F009 409 VERSION_CONFLICT：可识别冲突信号（刷新后重改），不静默重试", async () => {
  respond = () =>
    jsonResponse(409, {
      error: {
        code: "VERSION_CONFLICT",
        message: "数据已被他人修改",
        details: { current_version: 7 },
      },
    });
  const err = await expectApiError(
    updateIpPool(ipPoolFixture.id, { version: 6, allocation_mode: "AUTO" }),
  );
  const described = describeIpPoolActionError(err);
  assert.equal(described.versionConflict, true);
  assert.equal(described.currentVersion, 7);
  assert.ok(described.message.includes("刷新"), "应提示刷新后重改");
  assert.ok(described.message.includes("不会自动重试"));
  assert.equal(calls.length, 1); // 不重试（不静默重试覆盖）
});

await test('F009 409 CONFLICT unique_conflict（field="name"）→ name 字段级错误（同网络大小写不敏感唯一）', async () => {
  respond = () =>
    jsonResponse(409, {
      error: {
        code: "CONFLICT",
        message: "Conflict",
        details: { reason: "unique_conflict", field: "name" },
      },
    });
  const err = await expectApiError(
    createIpPool({ network: "n1", name: "mgmt-pool", start_address: "10.0.0.1", end_address: "10.0.0.2" }),
  );
  const described = describeIpPoolActionError(err);
  assert.equal(described.versionConflict, false);
  assert.ok(described.fields.name, "unique_conflict 应落为 name 字段级错误");
  assert.ok(described.fields.name.includes("大小写不敏感"));
  assert.ok(described.message.includes("name 冲突"));
});

await test('F009 409 CONFLICT range_overlap（field="start_address"）→ 字段级错误 + 重叠池明细（含起止地址）；不重试', async () => {
  respond = () =>
    jsonResponse(409, {
      error: {
        code: "CONFLICT",
        message: "Conflict",
        details: {
          reason: "range_overlap",
          field: "start_address",
          conflicts: [
            {
              object_type: "ip_pool",
              object_id: "p1",
              label: "MGMT-POOL",
              start_address: "10.0.0.50",
              end_address: "10.0.0.150",
            },
            {
              object_type: "ip_pool",
              object_id: "p2",
              label: null,
              start_address: "10.0.0.10",
              end_address: "10.0.0.10",
            },
          ],
        },
      },
    });
  const err = await expectApiError(
    createIpPool({ network: "n1", name: "OTHER", start_address: "10.0.0.100", end_address: "10.0.0.200" }),
  );
  const described = describeIpPoolActionError(err);
  assert.ok(described.fields.start_address, "range_overlap 应落为 start_address 字段级错误");
  assert.ok(described.fields.start_address.includes("共享端点"));
  assert.equal(described.rangeConflicts.length, 2);
  assert.equal(described.rangeConflicts[0].object_type, "ip_pool");
  assert.equal(described.rangeConflicts[0].label, "MGMT-POOL");
  assert.equal(described.rangeConflicts[0].start_address, "10.0.0.50");
  assert.equal(described.rangeConflicts[0].end_address, "10.0.0.150");
  assert.equal(described.rangeConflicts[1].label, null); // label 缺失为 null
  assert.ok(described.message.includes("CONFLICT/range_overlap"));
  assert.equal(calls.length, 1);
});

await test("F009 409 CONFLICT address_in_use：occupancy 结构（conflict_count 总数 + conflicts 预览 + truncated，DR-110）", async () => {
  respond = () =>
    jsonResponse(409, {
      error: {
        code: "CONFLICT",
        message: "Conflict",
        details: {
          reason: "address_in_use",
          field: "allocation_mode",
          conflict_count: 3,
          conflicts: [
            {
              object_type: "ip_address",
              object_id: "a1",
              address: "10.0.0.10",
              bound: false,
              interface_id: null,
              resource_id: null,
              resource_hostname: null,
            },
            {
              object_type: "ip_address",
              object_id: "a2",
              address: "10.0.0.20",
              bound: true,
              interface_id: "iface-uuid-1",
              resource_id: "r-uuid-1",
              resource_hostname: "node001",
            },
          ],
          conflicts_truncated: true,
        },
      },
    });
  const err = await expectApiError(
    createIpPool({
      network: "n1",
      name: "RES",
      start_address: "10.0.0.1",
      end_address: "10.0.0.200",
      allocation_mode: "RESERVED",
    }),
  );
  const described = describeIpPoolActionError(err);
  assert.equal(described.versionConflict, false);
  assert.ok(described.occupancy, "address_in_use 应解析出 occupancy 结构");
  assert.equal(described.occupancy.field, "allocation_mode");
  assert.equal(described.occupancy.count, 3); // 总数（非预览条数）
  assert.equal(described.occupancy.conflicts.length, 2); // 预览明细（截断后）
  assert.equal(described.occupancy.conflicts[0].address, "10.0.0.10");
  assert.equal(described.occupancy.conflicts[0].bound, false); // 含未绑定
  assert.equal(described.occupancy.conflicts[1].bound, true);
  assert.equal(described.occupancy.conflicts[1].resource_hostname, "node001");
  assert.equal(described.occupancy.truncated, true); // 截断标记透传
  assert.ok(described.fields.allocation_mode, "应落为 allocation_mode 字段级错误");
  assert.ok(described.message.includes("CONFLICT/address_in_use"));
  assert.ok(described.message.includes("3 个未删除的 IP 地址"));
  assert.ok(described.message.includes("截断"));
  assert.equal(calls.length, 1); // 不自动重试
});

await test("F009 409 CONFLICT address_in_use：field=start_address（RESERVED 扩大范围）与字段回退", async () => {
  respond = () =>
    jsonResponse(409, {
      error: {
        code: "CONFLICT",
        message: "Conflict",
        details: {
          reason: "address_in_use",
          field: "start_address",
          conflict_count: 1,
          conflicts: [
            {
              object_type: "ip_address",
              object_id: "a3",
              address: "10.0.0.5",
              bound: false,
              interface_id: null,
              resource_id: null,
              resource_hostname: null,
            },
          ],
          conflicts_truncated: false,
        },
      },
    });
  const err = await expectApiError(
    updateIpPool(ipPoolFixture.id, { version: 3, start_address: "10.0.0.1" }),
  );
  const described = describeIpPoolActionError(err);
  assert.equal(described.occupancy.field, "start_address");
  assert.ok(described.fields.start_address);
  assert.equal(described.occupancy.truncated, false);
  // 形状不符（缺 field/count）时保守回退，不抛错、不伪造字段
  respond = () =>
    jsonResponse(409, {
      error: { code: "CONFLICT", message: "Conflict", details: { reason: "address_in_use" } },
    });
  const fallback = await expectApiError(
    updateIpPool(ipPoolFixture.id, { version: 3, allocation_mode: "RESERVED" }),
  );
  const fallbackDescribed = describeIpPoolActionError(fallback);
  assert.equal(fallbackDescribed.occupancy.field, "allocation_mode");
  assert.equal(fallbackDescribed.occupancy.count, 0); // 无明细时 count 回退为预览条数
  assert.equal(fallbackDescribed.occupancy.conflicts.length, 0);
});

await test("F009 409 CONFLICT dependency_deleted：恢复时所属 Network 仍删（object_type=network）→ 网络文案，不覆盖新对象", async () => {
  respond = () =>
    jsonResponse(409, {
      error: {
        code: "CONFLICT",
        message: "Conflict",
        details: {
          reason: "dependency_deleted",
          conflicts: [{ object_type: "network", object_id: "0b9f4c6b-8f82-4b7a-9b95-a1e93b1f0801" }],
        },
      },
    });
  const err = await expectApiError(restoreIpPool(ipPoolFixture.id, 3));
  const described = describeIpPoolActionError(err);
  assert.equal(described.dependencyConflicts.length, 1);
  assert.equal(described.dependencyConflicts[0].object_type, "network");
  assert.ok(described.message.includes("所属网络"));
  assert.ok(described.message.includes("不会覆盖网络或其上新对象"));
});

await test("F009 409 CONFLICT not_deleted：对未软删对象 restore 的明确文案", async () => {
  respond = () =>
    jsonResponse(409, {
      error: { code: "CONFLICT", message: "Conflict", details: { reason: "not_deleted" } },
    });
  const err = await expectApiError(restoreIpPool(ipPoolFixture.id, 3));
  const described = describeIpPoolActionError(err);
  assert.ok(described.message.includes("未处于已删除状态"));
  assert.ok(described.message.includes("CONFLICT/not_deleted"));
});

await test("F009 422 VALIDATION_ERROR：顶层字段路径透传（network/name/start_address/end_address/allocation_mode/description，Contract §2.3）", async () => {
  respond = () =>
    jsonResponse(422, {
      error: {
        code: "VALIDATION_ERROR",
        message: "请求体校验失败",
        details: {
          fields: [
            { field: "network", message: "网络不存在或已删除" },
            { field: "name", message: "name 不能为空" },
            { field: "start_address", message: "start_address 不属于所属网络 CIDR" },
            { field: "end_address", message: "end_address 不能小于 start_address" },
            { field: "allocation_mode", message: "allocation_mode 非法" },
            { field: "description", message: "description 必须为字符串或 null" },
          ],
        },
      },
    });
  const err = await expectApiError(
    createIpPool({ network: "nope", name: "", start_address: "10.1.0.1", end_address: "10.0.0.1" }),
  );
  const described = describeIpPoolActionError(err);
  assert.equal(described.fields.network, "网络不存在或已删除");
  assert.equal(described.fields.name, "name 不能为空");
  assert.equal(described.fields.start_address, "start_address 不属于所属网络 CIDR");
  assert.equal(described.fields.end_address, "end_address 不能小于 start_address");
  assert.equal(described.fields.allocation_mode, "allocation_mode 非法");
  assert.equal(described.fields.description, "description 必须为字符串或 null");
});

await test("F009 403 / 404：明确文案（权限不足 / 对象不存在，不泄露存在性细节）", async () => {
  respond = () =>
    jsonResponse(403, {
      error: { code: "FORBIDDEN", message: "没有权限", details: { reason: "permission" } },
    });
  const err403 = await expectApiError(deleteIpPool(ipPoolFixture.id, 3));
  assert.ok(describeIpPoolActionError(err403).message.includes("没有权限"));
  respond = () =>
    jsonResponse(404, { error: { code: "NOT_FOUND", message: "不存在", details: {} } });
  const err404 = await expectApiError(getIpPool(ipPoolFixture.id));
  assert.ok(describeIpPoolActionError(err404).message.includes("地址池不存在"));
});

await test("F009 parseIpPoolFormValues：合法值（name trim / 地址 trim / 默认 MANUAL / 空描述=null / start=end 单地址池）", async () => {
  const parsed = parseIpPoolFormValues({
    ...emptyIpPoolFormValues(),
    network: "n1",
    name: "  MGMT-POOL  ",
    start_address: " 10.0.0.10 ",
    end_address: " 10.0.0.10 ",
    description: "管理网手动池",
  });
  assert.equal(parsed.ok, true);
  assert.equal(parsed.fields.name, "MGMT-POOL"); // trim 后原值（不折叠大小写）
  assert.equal(parsed.fields.start_address, "10.0.0.10");
  assert.equal(parsed.fields.end_address, "10.0.0.10"); // start=end 允许（单地址池）
  assert.equal(parsed.fields.allocation_mode, "MANUAL"); // 默认 MANUAL
  assert.equal(parsed.fields.description, "管理网手动池");
  // 可空描述空串 → null；AUTO 透传
  const emptyDesc = parseIpPoolFormValues({
    ...emptyIpPoolFormValues(),
    network: "n1",
    name: "P1",
    start_address: "10.0.0.10",
    end_address: "10.0.0.20",
    allocation_mode: "AUTO",
  });
  assert.equal(emptyDesc.ok, true);
  assert.equal(emptyDesc.fields.description, null);
  assert.equal(emptyDesc.fields.allocation_mode, "AUTO");
});

await test("F009 parseIpPoolFormValues：非法输入 → 字段级错误（空名 / 控制字符 / 超长 / 非法 IPv4 / 带掩码 / IPv6 / 逆序）", async () => {
  const cases = [
    { values: { name: "   " }, key: "name", hint: "不能为空" },
    { values: { name: "P\u00001" }, key: "name", hint: "控制字符" },
    { values: { name: "p".repeat(256) }, key: "name", hint: "长度超过" },
    { values: { start_address: "" }, key: "start_address", hint: "不能为空" },
    { values: { start_address: "10.0.0" }, key: "start_address", hint: "IPv4" },
    { values: { start_address: "10.0.0.256" }, key: "start_address", hint: "IPv4" },
    { values: { start_address: "10.0.0.10/24" }, key: "start_address", hint: "不带掩码" },
    { values: { start_address: "::1" }, key: "start_address", hint: "IPv4" },
    { values: { end_address: "10.0.0" }, key: "end_address", hint: "IPv4" },
    { values: { end_address: "10.0.0.10/32" }, key: "end_address", hint: "不带掩码" },
  ];
  for (const { values, key, hint } of cases) {
    const parsed = parseIpPoolFormValues({
      ...emptyIpPoolFormValues(),
      network: "n1",
      name: "P1",
      start_address: "10.0.0.10",
      end_address: "10.0.0.100",
      ...values,
    });
    assert.equal(parsed.ok, false, `应校验失败：${key}=${JSON.stringify(values[key])}`);
    if (!parsed.ok) {
      assert.ok(parsed.errors[key], `应产生 ${key} 字段错误`);
      assert.ok(
        parsed.errors[key].includes(hint),
        `${key} 错误文案应含「${hint}」，实际：${parsed.errors[key]}`,
      );
    }
  }
  // 逆序：start > end → end_address 错误（服务端同样 422）
  const reversed = parseIpPoolFormValues({
    ...emptyIpPoolFormValues(),
    network: "n1",
    name: "P1",
    start_address: "10.0.0.100",
    end_address: "10.0.0.10",
  });
  assert.equal(reversed.ok, false);
  assert.ok(reversed.errors.end_address.includes("不能小于 start_address"));
});

await test("F009 parseIpPoolFormValues：属 CIDR 本地提示（服务端仍权威校验；未知 / 异常 CIDR 不伪造结论）", async () => {
  const values = {
    ...emptyIpPoolFormValues(),
    network: "n1",
    name: "P1",
    start_address: "10.1.0.5",
    end_address: "10.1.0.10",
  };
  // 未提供 CIDR（网络未选 / 未知）→ 不做本地判定
  assert.equal(parseIpPoolFormValues(values).ok, true);
  assert.equal(parseIpPoolFormValues(values, null).ok, true);
  // 提供 CIDR 且越界 → 本地提示（错误文案含 CIDR）
  const outOfCidr = parseIpPoolFormValues(values, "10.0.0.0/24");
  assert.equal(outOfCidr.ok, false);
  assert.ok(outOfCidr.errors.start_address.includes("不属于所属网络 CIDR 10.0.0.0/24"));
  assert.ok(outOfCidr.errors.end_address.includes("不属于所属网络 CIDR 10.0.0.0/24"));
  // 起止均属 CIDR（含网络 / 广播地址，不新增建池范围限制，DR-117）
  const inCidr = parseIpPoolFormValues(
    {
      ...emptyIpPoolFormValues(),
      network: "n1",
      name: "P1",
      start_address: "10.0.0.0",
      end_address: "10.0.0.255",
    },
    "10.0.0.0/24",
  );
  assert.equal(inCidr.ok, true);
  // CIDR 本身不合法 → 不做本地判定（由网络数据源 / 服务端承载）
  assert.equal(parseIpPoolFormValues(values, "not-a-cidr").ok, true);
});

await test("F009 ipPoolFormFieldFromPath：服务端 422 点路径 → 表单键（顶层直通；未知路径 → null）", async () => {
  assert.equal(ipPoolFormFieldFromPath("network"), "network");
  assert.equal(ipPoolFormFieldFromPath("name"), "name");
  assert.equal(ipPoolFormFieldFromPath("start_address"), "start_address");
  assert.equal(ipPoolFormFieldFromPath("end_address"), "end_address");
  assert.equal(ipPoolFormFieldFromPath("allocation_mode"), "allocation_mode");
  assert.equal(ipPoolFormFieldFromPath("description"), "description");
  assert.equal(ipPoolFormFieldFromPath("metadata"), null); // IPPool 无 metadata（I-6）
  assert.equal(ipPoolFormFieldFromPath("unknown.field"), null);
});

await test("F009 buildIpPoolCreateInput：network/name/start/end/mode 恒携带；description 仅已登记值", async () => {
  const parsed = parseIpPoolFormValues({
    ...emptyIpPoolFormValues(),
    network: "n1",
    name: "P1",
    start_address: "10.0.0.10",
    end_address: "10.0.0.100",
  });
  assert.equal(parsed.ok, true);
  const input = buildIpPoolCreateInput("0b9f4c6b-8f82-4b7a-9b95-a1e93b1f0801", parsed.fields);
  assert.deepEqual(input, {
    network: "0b9f4c6b-8f82-4b7a-9b95-a1e93b1f0801",
    name: "P1",
    start_address: "10.0.0.10",
    end_address: "10.0.0.100",
    allocation_mode: "MANUAL", // 默认由显式值承载
  });
  const full = parseIpPoolFormValues({
    ...emptyIpPoolFormValues(),
    network: "n1",
    name: "P1",
    start_address: "10.0.0.10",
    end_address: "10.0.0.100",
    allocation_mode: "RESERVED",
    description: "保留段",
  });
  assert.equal(full.ok, true);
  const fullInput = buildIpPoolCreateInput("n1-uuid", full.fields);
  assert.deepEqual(fullInput, {
    network: "n1-uuid",
    name: "P1",
    start_address: "10.0.0.10",
    end_address: "10.0.0.100",
    allocation_mode: "RESERVED",
    description: "保留段",
  });
});

await test("F009 buildIpPoolPatch：exclude_unset 镜像（无变化 → null；变化才携带；显式 null=清空 description；network 恒不上送，DR-107）", async () => {
  // 无变化 → null（不发起空更新）
  const unchanged = parseIpPoolFormValues(ipPoolFormValuesFromIpPool(ipPoolFixture));
  assert.equal(unchanged.ok, true);
  assert.equal(buildIpPoolPatch(ipPoolFixture, unchanged.fields), null);
  // 变化：name / start / end / mode + description 清空（显式 null）
  const changed = parseIpPoolFormValues({
    ...ipPoolFormValuesFromIpPool(ipPoolFixture),
    name: "MGMT-POOL-2",
    start_address: "10.0.0.5",
    end_address: "10.0.0.200",
    allocation_mode: "RESERVED",
    description: "",
  });
  assert.equal(changed.ok, true);
  const patch = buildIpPoolPatch(ipPoolFixture, changed.fields);
  assert.deepEqual(patch, {
    version: 3,
    name: "MGMT-POOL-2",
    start_address: "10.0.0.5",
    end_address: "10.0.0.200",
    allocation_mode: "RESERVED",
    description: null,
  });
  assert.ok(!("network" in patch), "PATCH 载荷不得携带 network 键（创建后不可改，DR-107）");
  // 仅 description 设置（null → 文本）也只携带该字段
  const descOnly = parseIpPoolFormValues({
    ...ipPoolFormValuesFromIpPool({ ...ipPoolFixture, description: null }),
    description: "新描述",
  });
  assert.equal(descOnly.ok, true);
  assert.deepEqual(buildIpPoolPatch(ipPoolFixture, descOnly.fields), {
    version: 3,
    description: "新描述",
  });
});

await test("F009 ipPoolFormValuesFromIpPool：null → 默认空值；description 空串；往返无变化（与 buildIpPoolPatch=null 联动）", async () => {
  const values = ipPoolFormValuesFromIpPool({ ...ipPoolFixture, description: null });
  assert.equal(values.network, ipPoolFixture.network.id);
  assert.equal(values.name, "MGMT-POOL");
  assert.equal(values.start_address, "10.0.0.10");
  assert.equal(values.end_address, "10.0.0.100");
  assert.equal(values.allocation_mode, "MANUAL");
  assert.equal(values.description, ""); // null → 空串（未设置）
  const nullValues = ipPoolFormValuesFromIpPool(null);
  assert.deepEqual(nullValues, emptyIpPoolFormValues());
  // 往返：初始化 → 解析 → 无变化（与 buildIpPoolPatch=null 联动）
  const roundTrip = parseIpPoolFormValues(ipPoolFormValuesFromIpPool(ipPoolFixture));
  assert.equal(roundTrip.ok, true);
  assert.equal(buildIpPoolPatch(ipPoolFixture, roundTrip.fields), null);
});

// ---------- F010 IP Address 机制级（Contract：docs/api/F010.md v1） ----------

/** IPAddress 响应夹具（Contract §3：network/cluster/interface/ip_pool 展开 / 可空）。 */
const ipAddressFixture = {
  id: "0b9f4c6b-8f82-4b7a-9b95-a1e93b1f1001",
  network: { id: "0b9f4c6b-8f82-4b7a-9b95-a1e93b1f0801", name: "MGMT", cidr: "10.0.0.0/24" },
  cluster: { id: "0b9f4c6b-8f82-4b7a-9b95-a1e93b1f0004", code: "N96P", name: "N96P集群" },
  address: "10.0.0.5",
  interface: {
    id: "a1b2c3d4-0000-4000-8000-0000000000f1",
    name: "eth0",
    resource: { id: "0b9f4c6b-8f82-4b7a-9b95-a1e93b1f0101", hostname: "node001" },
  },
  ip_pool: { id: "0b9f4c6b-8f82-4b7a-9b95-a1e93b1f0901", name: "MGMT-AUTO" },
  description: "管理网示例地址",
  version: 3,
  created_at: "2026-10-09T12:00:00+00:00",
  updated_at: "2026-10-09T12:00:00+00:00",
  deleted_at: null,
};

await test("F010 listIpAddresses：默认 GET /api/v1/ip-addresses，无查询串", async () => {
  respond = () => jsonResponse(200, { items: [], page: 1, page_size: 20, total: 0 });
  const data = await listIpAddresses();
  assert.equal(data.total, 0);
  assert.equal(calls.length, 1);
  assert.equal(calls[0].url, "/api/v1/ip-addresses");
  assert.equal(calls[0].init.method, "GET");
  assert.equal(calls[0].init.credentials, "include");
});

await test("F010 listIpAddresses 组合查询：network/cluster/interface/pool/address/bound/q/deleted/分页/排序（AND 组合）", async () => {
  respond = () => jsonResponse(200, { items: [ipAddressFixture], page: 2, page_size: 50, total: 1 });
  const data = await listIpAddresses({
    network_id: "0b9f4c6b-8f82-4b7a-9b95-a1e93b1f0801",
    cluster_id: "0b9f4c6b-8f82-4b7a-9b95-a1e93b1f0004",
    interface_id: "a1b2c3d4-0000-4000-8000-0000000000f1",
    ip_pool_id: "0b9f4c6b-8f82-4b7a-9b95-a1e93b1f0901",
    address: "10.0.0.5",
    bound: true,
    q: "10.0.0",
    deleted: "only",
    page: 2,
    page_size: 50,
    sort: "address",
    order: "asc",
  });
  assert.equal(data.items[0].address, "10.0.0.5");
  assert.equal(calls.length, 1);
  assert.equal(
    calls[0].url,
    "/api/v1/ip-addresses?network_id=0b9f4c6b-8f82-4b7a-9b95-a1e93b1f0801" +
      "&cluster_id=0b9f4c6b-8f82-4b7a-9b95-a1e93b1f0004" +
      "&interface_id=a1b2c3d4-0000-4000-8000-0000000000f1" +
      "&ip_pool_id=0b9f4c6b-8f82-4b7a-9b95-a1e93b1f0901" +
      "&address=10.0.0.5&bound=true&q=10.0.0&deleted=only" +
      "&page=2&page_size=50&sort=address&order=asc",
  );
  // bound=false 也要照常发送（不得因 falsy 丢失）；空串过滤项不发
  await listIpAddresses({ bound: false });
  assert.equal(calls[1].url, "/api/v1/ip-addresses?bound=false");
  await listIpAddresses({
    network_id: "",
    cluster_id: "",
    interface_id: "",
    ip_pool_id: "",
    address: "",
    q: "",
  });
  assert.equal(calls[2].url, "/api/v1/ip-addresses");
});

await test("F010 createIpAddress（手动分配）：POST body（network/address/description）；201 解析嵌套展开", async () => {
  respond = () => jsonResponse(201, { ip_address: ipAddressFixture });
  const { ip_address } = await createIpAddress({
    network: "0b9f4c6b-8f82-4b7a-9b95-a1e93b1f0801",
    address: "10.0.0.5",
    description: "管理网示例地址",
  });
  assert.equal(ip_address.id, ipAddressFixture.id);
  assert.equal(ip_address.network.cidr, "10.0.0.0/24"); // network 嵌套展开
  assert.equal(ip_address.cluster.code, "N96P");
  assert.equal(ip_address.interface.resource.hostname, "node001"); // interface 嵌套展开
  assert.equal(ip_address.ip_pool.name, "MGMT-AUTO");
  assert.equal(calls.length, 1);
  assert.equal(calls[0].url, "/api/v1/ip-addresses");
  assert.equal(calls[0].init.method, "POST");
  assert.deepEqual(JSON.parse(calls[0].init.body), {
    network: "0b9f4c6b-8f82-4b7a-9b95-a1e93b1f0801",
    address: "10.0.0.5",
    description: "管理网示例地址",
  });
});

await test("F010 createIpAddress 最小载荷：仅 network + address（description 省略 → null）", async () => {
  respond = () =>
    jsonResponse(201, { ip_address: { ...ipAddressFixture, description: null } });
  const { ip_address } = await createIpAddress({ network: "n1", address: "10.0.0.5" });
  assert.equal(ip_address.description, null); // 未设置返回 null，不用空串代替
  assert.deepEqual(JSON.parse(calls[0].init.body), {
    network: "n1",
    address: "10.0.0.5",
  });
});

await test("F010 autoAllocateIpAddress（自动分配）：POST /auto-allocate + network/ip_pool body；interface=null", async () => {
  respond = () =>
    jsonResponse(201, {
      ip_address: { ...ipAddressFixture, address: "10.0.0.50", interface: null },
    });
  const { ip_address } = await autoAllocateIpAddress({
    network: "0b9f4c6b-8f82-4b7a-9b95-a1e93b1f0801",
    ip_pool: "0b9f4c6b-8f82-4b7a-9b95-a1e93b1f0901",
    description: "自动分配示例",
  });
  assert.equal(ip_address.address, "10.0.0.50"); // 服务端升序选址
  assert.equal(ip_address.interface, null); // 分配与绑定分离（DR-137）
  assert.equal(ip_address.ip_pool.id, "0b9f4c6b-8f82-4b7a-9b95-a1e93b1f0901"); // 来源=指定池
  assert.equal(calls.length, 1);
  assert.equal(calls[0].url, "/api/v1/ip-addresses/auto-allocate");
  assert.equal(calls[0].init.method, "POST");
  assert.deepEqual(JSON.parse(calls[0].init.body), {
    network: "0b9f4c6b-8f82-4b7a-9b95-a1e93b1f0801",
    ip_pool: "0b9f4c6b-8f82-4b7a-9b95-a1e93b1f0901",
    description: "自动分配示例",
  });
  // 最小载荷：description 省略
  respond = () => jsonResponse(201, { ip_address: { ...ipAddressFixture, interface: null } });
  await autoAllocateIpAddress({ network: "n1", ip_pool: "p1" });
  assert.deepEqual(JSON.parse(calls[1].init.body), { network: "n1", ip_pool: "p1" });
});

await test("F010 getIpAddress：详情 + ?deleted=true（已删需 VIEW_DELETED）", async () => {
  respond = () => jsonResponse(200, { ip_address: ipAddressFixture });
  await getIpAddress(ipAddressFixture.id);
  assert.equal(calls[0].url, `/api/v1/ip-addresses/${ipAddressFixture.id}`);
  await getIpAddress(ipAddressFixture.id, { deleted: true });
  assert.equal(calls[1].url, `/api/v1/ip-addresses/${ipAddressFixture.id}?deleted=true`);
});

await test("F010 updateIpAddress：PATCH 仅携带变化字段（version 必带；不含 network/address/ip_pool，DR-120/DR-122）", async () => {
  respond = () =>
    jsonResponse(200, { ip_address: { ...ipAddressFixture, version: 4, interface: null } });
  await updateIpAddress(ipAddressFixture.id, { version: 3, interface: null });
  assert.equal(calls[0].init.method, "PATCH");
  assert.equal(calls[0].url, `/api/v1/ip-addresses/${ipAddressFixture.id}`);
  const body = JSON.parse(calls[0].init.body);
  assert.deepEqual(body, { version: 3, interface: null }); // 显式 null = 解绑（IP 继续占用）
  assert.ok(!("network" in body), "PATCH 载荷不得携带 network 键（创建后不可改，DR-120）");
  assert.ok(!("address" in body), "PATCH 载荷不得携带 address 键（创建后不可改，DR-120）");
  assert.ok(!("ip_pool" in body), "PATCH 载荷不得携带 ip_pool 键（来源不可改，DR-122）");
  // 转移（绑定到新接口）+ 描述清空（显式 null）
  respond = () => jsonResponse(200, { ip_address: ipAddressFixture });
  await updateIpAddress(ipAddressFixture.id, {
    version: 3,
    interface: "a1b2c3d4-0000-4000-8000-0000000000f2",
    description: null,
  });
  assert.deepEqual(JSON.parse(calls[1].init.body), {
    version: 3,
    interface: "a1b2c3d4-0000-4000-8000-0000000000f2",
    description: null,
  });
});

await test("F010 releaseIpAddress / restoreIpAddress：version 为 Query 参数（Contract §6.6/§6.7）", async () => {
  respond = () => new Response(null, { status: 204 });
  const result = await releaseIpAddress(ipAddressFixture.id, 3);
  assert.equal(result, undefined);
  assert.equal(calls[0].init.method, "DELETE");
  assert.equal(calls[0].url, `/api/v1/ip-addresses/${ipAddressFixture.id}?version=3`);
  respond = () =>
    jsonResponse(200, { ip_address: { ...ipAddressFixture, version: 4, deleted_at: null } });
  const { ip_address: restored } = await restoreIpAddress(ipAddressFixture.id, 3);
  assert.equal(restored.deleted_at, null);
  assert.equal(calls[1].init.method, "POST");
  assert.equal(calls[1].url, `/api/v1/ip-addresses/${ipAddressFixture.id}/restore?version=3`);
});

await test("F010 getIpAddressActivity：URL + deleted/page 查询参数（VIEW_ACTIVITY 全角色）", async () => {
  respond = () => jsonResponse(200, { items: [], page: 1, page_size: 20, total: 0 });
  await getIpAddressActivity(ipAddressFixture.id, { page: 1, page_size: 20 });
  assert.equal(
    calls[0].url,
    `/api/v1/ip-addresses/${ipAddressFixture.id}/activity?page=1&page_size=20`,
  );
  await getIpAddressActivity(ipAddressFixture.id, { deleted: true });
  assert.equal(calls[1].url, `/api/v1/ip-addresses/${ipAddressFixture.id}/activity?deleted=true`);
});

await test("F010 getNetworkCapacity：GET /networks/{id}/capacity；remaining 负值原样（不截断，DR-130）", async () => {
  respond = () =>
    jsonResponse(200, {
      network_capacity: {
        network: {
          id: "0b9f4c6b-8f82-4b7a-9b95-a1e93b1f0801",
          name: "MGMT",
          cidr: "10.10.0.0/16",
          status: "ACTIVE",
          auto_allocate: true,
        },
        allocatable_total: 65534,
        occupied: 120,
        remaining: 65414,
      },
      auto_pools: [
        {
          ip_pool: {
            id: "0b9f4c6b-8f82-4b7a-9b95-a1e93b1f0901",
            name: "MGMT-AUTO",
            start_address: "10.10.1.50",
            end_address: "10.10.1.200",
          },
          allocatable_total: 151,
          occupied: 12,
          remaining: 139,
        },
      ],
    });
  const data = await getNetworkCapacity("0b9f4c6b-8f82-4b7a-9b95-a1e93b1f0801");
  assert.equal(data.network_capacity.allocatable_total, 65534);
  assert.equal(data.network_capacity.occupied, 120);
  assert.equal(data.network_capacity.remaining, 65414);
  assert.equal(data.network_capacity.network.auto_allocate, true);
  assert.equal(data.auto_pools.length, 1);
  assert.equal(data.auto_pools[0].ip_pool.name, "MGMT-AUTO");
  assert.equal(data.auto_pools[0].remaining, 139);
  assert.equal(calls.length, 1);
  assert.equal(
    calls[0].url,
    "/api/v1/networks/0b9f4c6b-8f82-4b7a-9b95-a1e93b1f0801/capacity",
  );
  assert.equal(calls[0].init.method, "GET");
  // 负值口径：存量地址落入现已保留范围时 remaining 可为负，原样返回（DR-130 定稿）
  respond = () =>
    jsonResponse(200, {
      network_capacity: {
        network: {
          id: "n1",
          name: "MGMT",
          cidr: "10.0.0.0/24",
          status: "ACTIVE",
          auto_allocate: false,
        },
        allocatable_total: 250,
        occupied: 260,
        remaining: -10,
      },
      auto_pools: [],
    });
  const negative = await getNetworkCapacity("n1");
  assert.equal(negative.network_capacity.remaining, -10);
});

await test('F010 409 CONFLICT unique_conflict（field="address"）→ address 字段级错误（同集群唯一）；不重试', async () => {
  respond = () =>
    jsonResponse(409, {
      error: {
        code: "CONFLICT",
        message: "Conflict",
        details: { reason: "unique_conflict", field: "address" },
      },
    });
  const err = await expectApiError(
    createIpAddress({ network: "n1", address: "10.0.0.5" }),
  );
  assert.equal(err.status, 409);
  assert.equal(err.code, "CONFLICT");
  assert.equal(err.details.reason, "unique_conflict");
  const described = describeIpAddressActionError(err);
  assert.equal(described.versionConflict, false);
  assert.ok(described.fields.address, "unique_conflict 应落为 address 字段级错误");
  assert.ok(described.fields.address.includes("同集群"));
  assert.ok(described.message.includes("address 冲突"));
  assert.equal(calls.length, 1); // 不自动重试
});

await test("F010 409 CONFLICT allocation_not_allowed：三种 condition 各自文案（DR-125/DR-136）；不重试", async () => {
  const conditions = [
    {
      condition: "network_inactive",
      hints: ["INACTIVE", "network_inactive"],
    },
    {
      condition: "auto_allocate_disabled",
      hints: ["auto_allocate", "auto_allocate_disabled"],
    },
    {
      condition: "pool_not_auto",
      hints: ["AUTO", "不降级", "pool_not_auto"],
    },
  ];
  for (const { condition, hints } of conditions) {
    respond = () =>
      jsonResponse(409, {
        error: {
          code: "CONFLICT",
          message: "Conflict",
          details: { reason: "allocation_not_allowed", condition },
        },
      });
    const err = await expectApiError(
      autoAllocateIpAddress({ network: "n1", ip_pool: "p1" }),
    );
    const described = describeIpAddressActionError(err);
    assert.equal(described.versionConflict, false);
    assert.equal(described.allocationCondition, condition);
    for (const hint of hints) {
      assert.ok(
        described.message.includes(hint),
        `condition=${condition} 文案应含「${hint}」，实际：${described.message}`,
      );
    }
  }
  // 未知 condition：保守回退通用文案（携带原值），不伪造已知条件
  respond = () =>
    jsonResponse(409, {
      error: {
        code: "CONFLICT",
        message: "Conflict",
        details: { reason: "allocation_not_allowed", condition: "weird" },
      },
    });
  const unknown = await expectApiError(
    autoAllocateIpAddress({ network: "n1", ip_pool: "p1" }),
  );
  const unknownDescribed = describeIpAddressActionError(unknown);
  assert.equal(unknownDescribed.allocationCondition, null);
  assert.ok(unknownDescribed.message.includes("condition=weird"));
  assert.equal(calls.length, 4); // 每个用例恰好一次，不重试
});

await test("F010 409 CONFLICT no_available_address：解析 {network_id, ip_pool_id}；不切换其它池", async () => {
  respond = () =>
    jsonResponse(409, {
      error: {
        code: "CONFLICT",
        message: "Conflict",
        details: {
          reason: "no_available_address",
          network_id: "n1",
          ip_pool_id: "p1",
        },
      },
    });
  const err = await expectApiError(
    autoAllocateIpAddress({ network: "n1", ip_pool: "p1" }),
  );
  const described = describeIpAddressActionError(err);
  assert.equal(described.versionConflict, false);
  assert.ok(described.noAvailable, "no_available_address 应解析出池信息");
  assert.equal(described.noAvailable.network_id, "n1");
  assert.equal(described.noAvailable.ip_pool_id, "p1");
  assert.ok(described.message.includes("无可用地址"));
  assert.ok(described.message.includes("不切换"));
  assert.ok(described.message.includes("CONFLICT/no_available_address"));
  assert.equal(calls.length, 1); // 不自动重试（不静默换池）
});

await test("F010 409 CONFLICT reference_exists：解绑/转移/释放被未删 Endpoint 引用 → references；不重试", async () => {
  respond = () =>
    jsonResponse(409, {
      error: {
        code: "CONFLICT",
        message: "Conflict",
        details: {
          reason: "reference_exists",
          references: [
            { object_type: "endpoint", object_id: "e1", label: "ep-1" },
            { object_type: "endpoint", object_id: "e2", label: null },
          ],
        },
      },
    });
  const err = await expectApiError(releaseIpAddress(ipAddressFixture.id, 3));
  const described = describeIpAddressActionError(err);
  assert.equal(described.versionConflict, false);
  assert.equal(described.references.length, 2);
  assert.equal(described.references[0].object_type, "endpoint");
  assert.equal(described.references[0].label, "ep-1");
  assert.equal(described.references[1].label, null); // label 缺失为 null
  assert.ok(described.message.includes("无法解绑/转移/释放"));
  assert.equal(calls.length, 1); // 不自动重试
});

await test("F010 409 CONFLICT dependency_deleted：network→所属网络文案 / interface→绑定接口文案；不覆盖新对象", async () => {
  respond = () =>
    jsonResponse(409, {
      error: {
        code: "CONFLICT",
        message: "Conflict",
        details: {
          reason: "dependency_deleted",
          conflicts: [{ object_type: "network", object_id: "n1" }],
        },
      },
    });
  const err = await expectApiError(restoreIpAddress(ipAddressFixture.id, 3));
  const described = describeIpAddressActionError(err);
  assert.equal(described.dependencyConflicts.length, 1);
  assert.equal(described.dependencyConflicts[0].object_type, "network");
  assert.ok(described.message.includes("所属网络"));
  assert.ok(described.message.includes("不会覆盖网络或其上新对象"));
  // interface 冲突：绑定接口仍删 → 接口文案，不误用网络文案
  respond = () =>
    jsonResponse(409, {
      error: {
        code: "CONFLICT",
        message: "Conflict",
        details: {
          reason: "dependency_deleted",
          conflicts: [{ object_type: "interface", object_id: "a1b2c3d4-0000-4000-8000-0000000000f1" }],
        },
      },
    });
  const ifaceErr = await expectApiError(restoreIpAddress(ipAddressFixture.id, 3));
  const ifaceDescribed = describeIpAddressActionError(ifaceErr);
  assert.equal(ifaceDescribed.dependencyConflicts[0].object_type, "interface");
  assert.ok(ifaceDescribed.message.includes("绑定的接口"));
  assert.ok(!ifaceDescribed.message.includes("所属网络"), "不得误用 network 文案");
  assert.ok(ifaceDescribed.message.includes("不会覆盖接口或其上新对象"));
});

await test("F010 409 CONFLICT not_deleted：对未软删对象 restore 的明确文案", async () => {
  respond = () =>
    jsonResponse(409, {
      error: { code: "CONFLICT", message: "Conflict", details: { reason: "not_deleted" } },
    });
  const err = await expectApiError(restoreIpAddress(ipAddressFixture.id, 3));
  const described = describeIpAddressActionError(err);
  assert.ok(described.message.includes("未处于已删除状态"));
  assert.ok(described.message.includes("CONFLICT/not_deleted"));
});

await test("F010 409 VERSION_CONFLICT：可识别冲突信号（刷新后重改），不静默重试", async () => {
  respond = () =>
    jsonResponse(409, {
      error: {
        code: "VERSION_CONFLICT",
        message: "数据已被他人修改",
        details: { current_version: 7 },
      },
    });
  const err = await expectApiError(
    updateIpAddress(ipAddressFixture.id, { version: 6, interface: null }),
  );
  const described = describeIpAddressActionError(err);
  assert.equal(described.versionConflict, true);
  assert.equal(described.currentVersion, 7);
  assert.ok(described.message.includes("刷新"), "应提示刷新后重改");
  assert.ok(described.message.includes("不会自动重试"));
  assert.equal(calls.length, 1); // 不重试（不静默重试覆盖）
});

await test("F010 422 VALIDATION_ERROR：顶层字段路径透传（network/address/interface/description，Contract §2.3）", async () => {
  respond = () =>
    jsonResponse(422, {
      error: {
        code: "VALIDATION_ERROR",
        message: "请求体校验失败",
        details: {
          fields: [
            { field: "network", message: "网络不存在或已删除" },
            { field: "address", message: "address 为网络/广播地址，不可分配" },
            { field: "interface", message: "接口与该 IP 不在同一集群" },
            { field: "description", message: "description 必须为字符串或 null" },
          ],
        },
      },
    });
  const err = await expectApiError(
    createIpAddress({ network: "nope", address: "10.0.0.0" }),
  );
  const described = describeIpAddressActionError(err);
  assert.equal(described.fields.network, "网络不存在或已删除");
  assert.equal(described.fields.address, "address 为网络/广播地址，不可分配");
  assert.equal(described.fields.interface, "接口与该 IP 不在同一集群");
  assert.equal(described.fields.description, "description 必须为字符串或 null");
});

await test("F010 403 / 404：明确文案（权限不足 / 对象不存在，不泄露存在性细节）", async () => {
  respond = () =>
    jsonResponse(403, {
      error: { code: "FORBIDDEN", message: "没有权限", details: { reason: "permission" } },
    });
  const err403 = await expectApiError(releaseIpAddress(ipAddressFixture.id, 3));
  assert.ok(describeIpAddressActionError(err403).message.includes("没有权限"));
  respond = () =>
    jsonResponse(404, { error: { code: "NOT_FOUND", message: "不存在", details: {} } });
  const err404 = await expectApiError(getIpAddress(ipAddressFixture.id));
  assert.ok(describeIpAddressActionError(err404).message.includes("IP 地址不存在"));
});

await test("F010 网络层错误（fetch reject）：不伪装成业务结果", async () => {
  respond = () => Promise.reject(new TypeError("Failed to fetch"));
  await assert.rejects(listIpAddresses(), TypeError);
  assert.equal(calls.length, 1); // 失败不重发
  const described = describeIpAddressActionError(new TypeError("Failed to fetch"));
  assert.equal(described.message, "无法连接服务器，请稍后重试");
  assert.equal(described.versionConflict, false);
});

await test("F010 parseIpAddressFormValues（manual）：合法值（trim / 裸 IPv4 / 空描述=null / 空接口=null）", async () => {
  const parsed = parseIpAddressFormValues(
    {
      ...emptyIpAddressFormValues(),
      network: "n1",
      address: " 10.0.0.5 ",
      description: "管理网示例地址",
    },
    "manual",
  );
  assert.equal(parsed.ok, true);
  assert.equal(parsed.fields.address, "10.0.0.5"); // trim 后原值（不归一化）
  assert.equal(parsed.fields.description, "管理网示例地址");
  assert.equal(parsed.fields.interface, null); // 空选 = null（解绑）
  // 空描述 → null
  const emptyDesc = parseIpAddressFormValues(
    {
      ...emptyIpAddressFormValues(),
      network: "n1",
      address: "10.0.0.5",
    },
    "manual",
  );
  assert.equal(emptyDesc.ok, true);
  assert.equal(emptyDesc.fields.description, null);
});

await test("F010 parseIpAddressFormValues（manual）：非法输入 → 字段级错误（空 / 非 IPv4 / 带掩码 / IPv6 / 越界 octet）", async () => {
  const cases = [
    { address: "", hint: "不能为空" },
    { address: "10.0.0", hint: "IPv4" },
    { address: "10.0.0.256", hint: "IPv4" },
    { address: "10.0.0.5/24", hint: "不带掩码" },
    { address: "10.0.0.5/32", hint: "不带掩码" },
    { address: "::1", hint: "IPv4" },
    { address: "   ", hint: "不能为空" },
  ];
  for (const { address, hint } of cases) {
    const parsed = parseIpAddressFormValues(
      { ...emptyIpAddressFormValues(), network: "n1", address },
      "manual",
    );
    assert.equal(parsed.ok, false, `应校验失败：address=${JSON.stringify(address)}`);
    if (!parsed.ok) {
      assert.ok(parsed.errors.address, "应产生 address 字段错误");
      assert.ok(
        parsed.errors.address.includes(hint),
        `address 错误文案应含「${hint}」，实际：${parsed.errors.address}`,
      );
    }
  }
});

await test("F010 parseIpAddressFormValues（manual）：属 CIDR 本地提示（服务端仍权威；未知 / 异常 CIDR 不伪造结论）", async () => {
  const values = {
    ...emptyIpAddressFormValues(),
    network: "n1",
    address: "10.1.0.5",
  };
  // 未提供 CIDR（网络未选 / 未知）→ 不做本地判定
  assert.equal(parseIpAddressFormValues(values, "manual").ok, true);
  assert.equal(parseIpAddressFormValues(values, "manual", null).ok, true);
  // 提供 CIDR 且越界 → 本地提示（错误文案含 CIDR）
  const outOfCidr = parseIpAddressFormValues(values, "manual", "10.0.0.0/24");
  assert.equal(outOfCidr.ok, false);
  assert.ok(outOfCidr.errors.address.includes("不属于所属网络 CIDR 10.0.0.0/24"));
  // /31 两址可用、/32 唯一地址可用：不做本地排除（网络/广播排除由服务端权威校验）
  const boundaryOk = parseIpAddressFormValues(
    { ...emptyIpAddressFormValues(), network: "n1", address: "10.0.0.0" },
    "manual",
    "10.0.0.0/31",
  );
  assert.equal(boundaryOk.ok, true, "/31 网络地址不做本地排除（服务端权威）");
  // CIDR 本身不合法 → 不做本地判定
  assert.equal(parseIpAddressFormValues(values, "manual", "not-a-cidr").ok, true);
});

await test("F010 parseIpAddressFormValues（auto/edit）：address 不参与校验（auto 服务端选址 / edit 不可改）", async () => {
  // auto：address 输入即使非法也不校验（不参与载荷）
  const autoParsed = parseIpAddressFormValues(
    { ...emptyIpAddressFormValues(), network: "n1", ip_pool: "p1", address: "garbage/24" },
    "auto",
  );
  assert.equal(autoParsed.ok, true);
  // edit：address 为只读展示，不校验；interface 透传
  const editParsed = parseIpAddressFormValues(
    {
      ...emptyIpAddressFormValues(),
      network: "n1",
      address: "whatever",
      interface: "a1b2c3d4-0000-4000-8000-0000000000f2",
    },
    "edit",
  );
  assert.equal(editParsed.ok, true);
  assert.equal(editParsed.fields.interface, "a1b2c3d4-0000-4000-8000-0000000000f2");
});

await test("F010 isValidBareIpv4：裸 IPv4 判定（列表过滤本地校验共用）", async () => {
  assert.equal(isValidBareIpv4("10.0.0.5"), true);
  assert.equal(isValidBareIpv4("0.0.0.0"), true);
  assert.equal(isValidBareIpv4("255.255.255.255"), true);
  assert.equal(isValidBareIpv4("10.0.0.5/24"), false); // 带掩码
  assert.equal(isValidBareIpv4("10.0.0"), false);
  assert.equal(isValidBareIpv4("10.0.0.256"), false);
  assert.equal(isValidBareIpv4("::1"), false); // IPv6
  assert.equal(isValidBareIpv4(""), false);
  assert.equal(isValidBareIpv4(" 10.0.0.5 "), false); // 含空白
});

await test("F010 ipAddressFormFieldFromPath：服务端 422 点路径 → 表单键（顶层直通；未知路径 → null）", async () => {
  assert.equal(ipAddressFormFieldFromPath("network"), "network");
  assert.equal(ipAddressFormFieldFromPath("address"), "address");
  assert.equal(ipAddressFormFieldFromPath("ip_pool"), "ip_pool");
  assert.equal(ipAddressFormFieldFromPath("interface"), "interface");
  assert.equal(ipAddressFormFieldFromPath("description"), "description");
  assert.equal(ipAddressFormFieldFromPath("metadata"), null); // IPAddress 无 metadata（I-3）
  assert.equal(ipAddressFormFieldFromPath("cluster_id"), null); // 不暴露（§2.2）
  assert.equal(ipAddressFormFieldFromPath("unknown.field"), null);
});

await test("F010 buildManualAllocateInput：network/address 恒携带；description 仅已登记值；不含 interface/ip_pool", async () => {
  const parsed = parseIpAddressFormValues(
    { ...emptyIpAddressFormValues(), network: "n1", address: " 10.0.0.5 " },
    "manual",
  );
  assert.equal(parsed.ok, true);
  const input = buildManualAllocateInput("0b9f4c6b-8f82-4b7a-9b95-a1e93b1f0801", parsed.fields);
  assert.deepEqual(input, {
    network: "0b9f4c6b-8f82-4b7a-9b95-a1e93b1f0801",
    address: "10.0.0.5",
  });
  assert.ok(!("description" in input), "未设置描述时不得携带 description 键");
  assert.ok(!("interface" in input), "手动分配载荷不得携带 interface（DR-137）");
  assert.ok(!("ip_pool" in input), "手动分配载荷不得携带 ip_pool（DR-122 服务端推导）");
  const full = parseIpAddressFormValues(
    { ...emptyIpAddressFormValues(), network: "n1", address: "10.0.0.5", description: "示例" },
    "manual",
  );
  assert.equal(full.ok, true);
  assert.deepEqual(buildManualAllocateInput("n1-uuid", full.fields), {
    network: "n1-uuid",
    address: "10.0.0.5",
    description: "示例",
  });
});

await test("F010 buildAutoAllocateInput：network/ip_pool 恒携带；description 仅已登记值；不含 address/interface", async () => {
  const parsed = parseIpAddressFormValues(
    { ...emptyIpAddressFormValues(), network: "n1", ip_pool: "p1" },
    "auto",
  );
  assert.equal(parsed.ok, true);
  const input = buildAutoAllocateInput("n1-uuid", "p1-uuid", parsed.fields);
  assert.deepEqual(input, { network: "n1-uuid", ip_pool: "p1-uuid" });
  assert.ok(!("address" in input), "自动分配载荷不得携带 address（服务端升序选址）");
  assert.ok(!("interface" in input), "自动分配载荷不得携带 interface（DR-137）");
  const withDesc = parseIpAddressFormValues(
    { ...emptyIpAddressFormValues(), network: "n1", ip_pool: "p1", description: "自动" },
    "auto",
  );
  assert.equal(withDesc.ok, true);
  assert.deepEqual(buildAutoAllocateInput("n1-uuid", "p1-uuid", withDesc.fields), {
    network: "n1-uuid",
    ip_pool: "p1-uuid",
    description: "自动",
  });
});

await test("F010 buildIpAddressPatch：exclude_unset 镜像（无变化 → null；绑定/解绑/转移；network/address/ip_pool 恒不上送）", async () => {
  // 无变化 → null（不发起空更新）
  const unchanged = parseIpAddressFormValues(
    ipAddressFormValuesFromIpAddress(ipAddressFixture),
    "edit",
  );
  assert.equal(unchanged.ok, true);
  assert.equal(unchanged.fields.interface, "a1b2c3d4-0000-4000-8000-0000000000f1");
  assert.equal(buildIpAddressPatch(ipAddressFixture, unchanged.fields), null);
  // 解绑：interface 空选 → 显式 null（IP 继续占用）
  const unbound = parseIpAddressFormValues(
    { ...ipAddressFormValuesFromIpAddress(ipAddressFixture), interface: "" },
    "edit",
  );
  assert.equal(unbound.ok, true);
  const unbindPatch = buildIpAddressPatch(ipAddressFixture, unbound.fields);
  assert.deepEqual(unbindPatch, { version: 3, interface: null });
  // 转移：绑定到新接口
  const transferred = parseIpAddressFormValues(
    {
      ...ipAddressFormValuesFromIpAddress(ipAddressFixture),
      interface: "a1b2c3d4-0000-4000-8000-0000000000f2",
    },
    "edit",
  );
  const transferPatch = buildIpAddressPatch(ipAddressFixture, transferred.fields);
  assert.deepEqual(transferPatch, {
    version: 3,
    interface: "a1b2c3d4-0000-4000-8000-0000000000f2",
  });
  assert.ok(!("network" in transferPatch), "PATCH 载荷不得携带 network 键（DR-120）");
  assert.ok(!("address" in transferPatch), "PATCH 载荷不得携带 address 键（DR-120）");
  assert.ok(!("ip_pool" in transferPatch), "PATCH 载荷不得携带 ip_pool 键（DR-122）");
  // 仅描述变化：清空（显式 null）/ 设置（null → 文本）
  const descCleared = parseIpAddressFormValues(
    { ...ipAddressFormValuesFromIpAddress(ipAddressFixture), description: "" },
    "edit",
  );
  assert.deepEqual(buildIpAddressPatch(ipAddressFixture, descCleared.fields), {
    version: 3,
    description: null,
  });
  const descSet = parseIpAddressFormValues(
    {
      ...ipAddressFormValuesFromIpAddress({ ...ipAddressFixture, description: null }),
      description: "新描述",
    },
    "edit",
  );
  assert.deepEqual(buildIpAddressPatch(ipAddressFixture, descSet.fields), {
    version: 3,
    description: "新描述",
  });
  // 解绑 + 清空描述同时变化
  const both = parseIpAddressFormValues(
    { ...ipAddressFormValuesFromIpAddress(ipAddressFixture), interface: "", description: "" },
    "edit",
  );
  assert.deepEqual(buildIpAddressPatch(ipAddressFixture, both.fields), {
    version: 3,
    interface: null,
    description: null,
  });
});

await test("F010 ipAddressFormValuesFromIpAddress：null → 默认空值；未绑定 → 空串；往返无变化（与 buildIpAddressPatch=null 联动）", async () => {
  const values = ipAddressFormValuesFromIpAddress(ipAddressFixture);
  assert.equal(values.network, ipAddressFixture.network.id);
  assert.equal(values.address, "10.0.0.5");
  assert.equal(values.ip_pool, ipAddressFixture.ip_pool.id);
  assert.equal(values.interface, "a1b2c3d4-0000-4000-8000-0000000000f1");
  assert.equal(values.description, "管理网示例地址");
  // 未绑定 / 无来源池 / 无描述 → 空串
  const unboundValues = ipAddressFormValuesFromIpAddress({
    ...ipAddressFixture,
    interface: null,
    ip_pool: null,
    description: null,
  });
  assert.equal(unboundValues.interface, "");
  assert.equal(unboundValues.ip_pool, "");
  assert.equal(unboundValues.description, "");
  // null → 全空（防御旧版后端）
  assert.deepEqual(ipAddressFormValuesFromIpAddress(null), emptyIpAddressFormValues());
  // 往返：初始化 → 解析 → 无变化（与 buildIpAddressPatch=null 联动）
  const roundTrip = parseIpAddressFormValues(
    ipAddressFormValuesFromIpAddress(ipAddressFixture),
    "edit",
  );
  assert.equal(roundTrip.ok, true);
  assert.equal(buildIpAddressPatch(ipAddressFixture, roundTrip.fields), null);
});

// ---------- F011 Service API 机制级（Contract：docs/api/F011.md v1） ----------

/** F011 用例共用的 Service 夹具（Contract §3 形状）。 */
const serviceFixture = {
  id: "0b9f4c6b-8f82-4b7a-9b95-a1e93b1f0b01",
  resource: { id: "0b9f4c6b-8f82-4b7a-9b95-a1e93b1f0004", hostname: "cn001" },
  name: "slurmd",
  status: "RUNNING",
  description: "Slurm compute daemon",
  metadata: { port: 6818 },
  version: 3,
  created_at: "2026-10-09T08:00:00Z",
  updated_at: "2026-10-09T09:00:00Z",
  deleted_at: null,
};

await test("F011 listServices 默认：GET /api/v1/services，无查询串", async () => {
  respond = () => jsonResponse(200, { items: [], page: 1, page_size: 20, total: 0 });
  const data = await listServices();
  assert.equal(data.total, 0);
  assert.equal(calls.length, 1);
  assert.equal(calls[0].url, "/api/v1/services");
  assert.equal(calls[0].init.method, "GET");
  assert.equal(calls[0].init.credentials, "include");
});

await test("F011 listServices 组合查询：resource_id/status/q/deleted/page/page_size/sort/order（AND 组合）", async () => {
  respond = () => jsonResponse(200, { items: [], page: 2, page_size: 50, total: 0 });
  await listServices({
    resource_id: "0b9f4c6b-8f82-4b7a-9b95-a1e93b1f0004",
    status: "RUNNING",
    q: "slurm",
    deleted: "only",
    page: 2,
    page_size: 50,
    sort: "name",
    order: "asc",
  });
  assert.equal(calls.length, 1);
  assert.equal(
    calls[0].url,
    "/api/v1/services?resource_id=0b9f4c6b-8f82-4b7a-9b95-a1e93b1f0004" +
      "&status=RUNNING&q=slurm&deleted=only&page=2&page_size=50&sort=name&order=asc",
  );
});

await test("F011 listServices 空串过滤项不发（q=''/resource_id=''），status 省略不发", async () => {
  respond = () => jsonResponse(200, { items: [], page: 1, page_size: 20, total: 0 });
  await listServices({ q: "", resource_id: "" });
  assert.equal(calls[0].url, "/api/v1/services");
});

await test("F011 createService：POST /services + JSON body；201 解析 {service}", async () => {
  respond = () => jsonResponse(201, { service: serviceFixture });
  const { service } = await createService({
    resource: "0b9f4c6b-8f82-4b7a-9b95-a1e93b1f0004",
    name: "slurmd",
    status: "RUNNING",
    description: "Slurm compute daemon",
    metadata: { port: 6818 },
  });
  assert.equal(service.id, serviceFixture.id);
  assert.equal(service.resource.hostname, "cn001");
  assert.equal(calls.length, 1);
  assert.equal(calls[0].url, "/api/v1/services");
  assert.equal(calls[0].init.method, "POST");
  assert.deepEqual(JSON.parse(calls[0].init.body), {
    resource: "0b9f4c6b-8f82-4b7a-9b95-a1e93b1f0004",
    name: "slurmd",
    status: "RUNNING",
    description: "Slurm compute daemon",
    metadata: { port: 6818 },
  });
});

await test("F011 getService：已删对象显式 ?deleted=true；默认不带", async () => {
  respond = () =>
    jsonResponse(200, { service: { id: "s1", deleted_at: "2026-10-09T12:00:00Z" } });
  await getService("s1", { deleted: true });
  await getService("s1");
  assert.equal(calls[0].url, "/api/v1/services/s1?deleted=true");
  assert.equal(calls[1].url, "/api/v1/services/s1");
});

await test("F011 updateService：PATCH 且仅携带变化字段（省略 = 不重置，Contract §6.4）", async () => {
  respond = () => jsonResponse(200, { service: { id: "s1", version: 4 } });
  const { service } = await updateService("s1", {
    version: 3,
    name: "slurmd",
    status: "STOPPED",
    metadata: { port: 6819 },
  });
  assert.equal(service.version, 4);
  assert.equal(calls.length, 1);
  assert.equal(calls[0].url, "/api/v1/services/s1");
  assert.equal(calls[0].init.method, "PATCH");
  // body 只含 version + 变化字段；resource 创建后不可改不出现（DR-144）
  assert.deepEqual(JSON.parse(calls[0].init.body), {
    version: 3,
    name: "slurmd",
    status: "STOPPED",
    metadata: { port: 6819 },
  });
});

await test("F011 updateService：description 显式 null = 清空", async () => {
  respond = () => jsonResponse(200, { service: { id: "s1" } });
  await updateService("s1", { version: 3, description: null });
  assert.deepEqual(JSON.parse(calls[0].init.body), { version: 3, description: null });
});

await test("F011 deleteService：DELETE + version 为 Query 参数；204 → undefined", async () => {
  respond = () => new Response(null, { status: 204 });
  const result = await deleteService("s1", 5);
  assert.equal(result, undefined);
  assert.equal(calls.length, 1);
  assert.equal(calls[0].url, "/api/v1/services/s1?version=5");
  assert.equal(calls[0].init.method, "DELETE");
});

await test("F011 restoreService：POST /{id}/restore + version Query 参数", async () => {
  respond = () => jsonResponse(200, { service: { id: "s1", deleted_at: null, version: 7 } });
  const { service } = await restoreService("s1", 6);
  assert.equal(service.deleted_at, null);
  assert.equal(calls.length, 1);
  assert.equal(calls[0].url, "/api/v1/services/s1/restore?version=6");
  assert.equal(calls[0].init.method, "POST");
});

await test("F011 getServiceActivity：GET /{id}/activity + deleted/page/page_size", async () => {
  respond = () =>
    jsonResponse(200, {
      items: [
        {
          id: "a1",
          action: "CREATE",
          operator_user_id: null,
          operator_username: "bootstrap",
          before_data: null,
          after_data: { name: "slurmd", resource_id: "r1", status: "UNKNOWN" },
          created_at: "2026-10-09T08:00:00Z",
        },
      ],
      page: 1,
      page_size: 20,
      total: 1,
    });
  const data = await getServiceActivity("s1", { deleted: true, page: 1, page_size: 20 });
  assert.equal(data.total, 1);
  assert.equal(data.items[0].action, "CREATE");
  assert.equal(data.items[0].after_data.name, "slurmd");
  assert.equal(calls.length, 1);
  assert.equal(calls[0].url, "/api/v1/services/s1/activity?deleted=true&page=1&page_size=20");
});

await test("F011 409 CONFLICT unique_conflict：落到 name 字段级错误；不重试", async () => {
  respond = () =>
    jsonResponse(409, {
      error: {
        code: "CONFLICT",
        message: "Conflict",
        details: { reason: "unique_conflict", field: "name" },
      },
    });
  const err = await expectApiError(
    createService({ resource: "r1", name: "slurmd" }),
  );
  assert.equal(err.status, 409);
  assert.equal(err.code, "CONFLICT");
  assert.equal(err.details.reason, "unique_conflict");
  const described = describeServiceActionError(err);
  assert.equal(described.versionConflict, false);
  assert.ok(described.fields.name, "unique_conflict 应落到 name 字段错误");
  assert.ok(described.fields.name.includes("大小写不敏感"));
  assert.ok(described.fields.name.includes("跨资源允许同名"));
  assert.equal(calls.length, 1); // 不自动重试
});

await test("F011 409 VERSION_CONFLICT：标记刷新后重改、携带 current_version；不重试", async () => {
  respond = () =>
    jsonResponse(409, {
      error: {
        code: "VERSION_CONFLICT",
        message: "Version conflict",
        details: { current_version: 9 },
      },
    });
  const err = await expectApiError(updateService("s1", { version: 3, name: "x" }));
  assert.equal(err.details.current_version, 9);
  const described = describeServiceActionError(err);
  assert.equal(described.versionConflict, true);
  assert.equal(described.currentVersion, 9);
  assert.ok(described.message.includes("刷新"), "应提示刷新后重改");
  assert.ok(described.message.includes("不会自动重试"));
  assert.equal(calls.length, 1); // 不静默重试覆盖
});

await test("F011 409 CONFLICT reference_exists：删除被未删 ServiceEndpoint 引用 → references；不重试", async () => {
  respond = () =>
    jsonResponse(409, {
      error: {
        code: "CONFLICT",
        message: "Conflict",
        details: {
          reason: "reference_exists",
          references: [
            { object_type: "service_endpoint", object_id: "e1", label: "slurmd:6818" },
            { object_type: "service_endpoint", object_id: "e2", label: null },
          ],
        },
      },
    });
  const err = await expectApiError(deleteService("s1", 3));
  const described = describeServiceActionError(err);
  assert.equal(described.versionConflict, false);
  assert.equal(described.references.length, 2);
  assert.equal(described.references[0].object_type, "service_endpoint");
  assert.equal(described.references[0].label, "slurmd:6818");
  assert.equal(described.references[1].label, null); // label 缺失为 null
  assert.ok(described.message.includes("无法删除"));
  assert.ok(described.message.includes("CONFLICT/reference_exists"));
  assert.equal(calls.length, 1); // 不自动重试
});

await test("F011 409 CONFLICT dependency_deleted：恢复时解析 conflicts（所属 Resource）", async () => {
  respond = () =>
    jsonResponse(409, {
      error: {
        code: "CONFLICT",
        message: "Conflict",
        details: {
          reason: "dependency_deleted",
          conflicts: [{ object_type: "resource", object_id: "r1" }],
        },
      },
    });
  const err = await expectApiError(restoreService("s1", 3));
  const described = describeServiceActionError(err);
  assert.equal(described.versionConflict, false);
  assert.equal(described.dependencyConflicts.length, 1);
  assert.equal(described.dependencyConflicts[0].object_type, "resource");
  assert.equal(described.dependencyConflicts[0].object_id, "r1");
  assert.ok(described.message.includes("所属资源"));
  assert.ok(described.message.includes("不会覆盖资源或其上新对象"));
});

await test("F011 409 CONFLICT not_deleted：恢复未删对象的明确文案", async () => {
  respond = () =>
    jsonResponse(409, {
      error: { code: "CONFLICT", message: "Conflict", details: { reason: "not_deleted" } },
    });
  const err = await expectApiError(restoreService("s1", 3));
  const described = describeServiceActionError(err);
  assert.ok(described.message.includes("未处于已删除状态"));
  assert.ok(described.message.includes("CONFLICT/not_deleted"));
});

await test("F011 422 VALIDATION_ERROR：details.fields 透传为字段级错误（含 resource）", async () => {
  respond = () =>
    jsonResponse(422, {
      error: {
        code: "VALIDATION_ERROR",
        message: "Validation error",
        details: {
          fields: [
            { field: "resource", message: "资源不存在或已删除" },
            { field: "name", message: "name 不能为空" },
            { field: "status", message: "status 非法" },
            { field: "metadata", message: "metadata 必须为 JSON 对象" },
          ],
        },
      },
    });
  const err = await expectApiError(
    createService({ resource: "nope", name: "", status: "BAD", metadata: [] }),
  );
  const described = describeServiceActionError(err);
  assert.equal(described.fields.resource, "资源不存在或已删除");
  assert.equal(described.fields.name, "name 不能为空");
  assert.equal(described.fields.status, "status 非法");
  assert.equal(described.fields.metadata, "metadata 必须为 JSON 对象");
});

await test("F011 403 / 404：明确文案（不泄露存在性 / 权限不足）", async () => {
  respond = () =>
    jsonResponse(403, {
      error: { code: "FORBIDDEN", message: "没有权限", details: { reason: "permission" } },
    });
  const err403 = await expectApiError(deleteService("s1", 3));
  assert.ok(describeServiceActionError(err403).message.includes("没有权限"));
  respond = () =>
    jsonResponse(404, { error: { code: "NOT_FOUND", message: "不存在", details: {} } });
  const err404 = await expectApiError(getService("s1"));
  assert.ok(describeServiceActionError(err404).message.includes("服务不存在"));
});

await test("F011 网络层错误（fetch reject）：不伪装成业务结果", async () => {
  respond = () => Promise.reject(new TypeError("Failed to fetch"));
  await assert.rejects(listServices(), TypeError);
  assert.equal(calls.length, 1); // 失败不重发
  const described = describeServiceActionError(new TypeError("Failed to fetch"));
  assert.equal(described.message, "无法连接服务器，请稍后重试");
  assert.equal(described.versionConflict, false);
});

await test("F011 parseServiceFormValues：合法值（trim / status 透传 / 空描述=null；内部空格与中文允许）", async () => {
  const parsed = parseServiceFormValues({
    ...emptyServiceFormValues(),
    name: "  计算服务 node 01 ",
    status: "STOPPED",
    description: "示例描述",
  });
  assert.equal(parsed.ok, true);
  // trim 首尾但保留内部空格不合并（与 Interface 禁内部空白不同，§2.1/I-5）
  assert.equal(parsed.fields.name, "计算服务 node 01");
  assert.equal(parsed.fields.status, "STOPPED");
  assert.equal(parsed.fields.description, "示例描述");
  // 空描述 → null；默认 status=UNKNOWN 透传（§2.2）
  const emptyDesc = parseServiceFormValues({
    ...emptyServiceFormValues(),
    name: "slurmd",
  });
  assert.equal(emptyDesc.ok, true);
  assert.equal(emptyDesc.fields.description, null);
  assert.equal(emptyDesc.fields.status, "UNKNOWN");
});

await test("F011 parseServiceFormValues：非法输入 → 字段级错误（空 / 纯空白 / 控制字符 / 超长）", async () => {
  const cases = [
    { name: "", hint: "不能为空" },
    { name: "   ", hint: "不能为空" },
    { name: "bad\u0000name", hint: "控制字符" },
    { name: "bad\u200bname", hint: "控制字符" }, // Cf（零宽空格）
    { name: "x".repeat(256), hint: "255" },
  ];
  for (const { name, hint } of cases) {
    const parsed = parseServiceFormValues({ ...emptyServiceFormValues(), name });
    assert.equal(parsed.ok, false, `应校验失败：name=${JSON.stringify(name)}`);
    if (!parsed.ok) {
      assert.ok(parsed.errors.name, "应产生 name 字段错误");
      assert.ok(
        parsed.errors.name.includes(hint),
        `name 错误文案应含「${hint}」，实际：${parsed.errors.name}`,
      );
    }
  }
  // 255 code point 恰好合法（含中文按 code point 计）
  const boundary = parseServiceFormValues({
    ...emptyServiceFormValues(),
    name: "服".repeat(255),
  });
  assert.equal(boundary.ok, true);
});

await test("F011 serviceFormFieldFromPath：服务端 422 点路径 → 表单键（顶层直通；未知路径 → null）", async () => {
  assert.equal(serviceFormFieldFromPath("resource"), "resource");
  assert.equal(serviceFormFieldFromPath("name"), "name");
  assert.equal(serviceFormFieldFromPath("status"), "status");
  assert.equal(serviceFormFieldFromPath("description"), "description");
  assert.equal(serviceFormFieldFromPath("metadata"), "metadata");
  assert.equal(serviceFormFieldFromPath("resource_id"), null); // 不可改别名不映射
  assert.equal(serviceFormFieldFromPath("name_key"), null); // 不暴露（§3）
  assert.equal(serviceFormFieldFromPath("unknown.field"), null);
});

await test("F011 buildServiceCreateInput：resource/name/status 恒携带；description/metadata 仅已登记值", async () => {
  const parsed = parseServiceFormValues({
    ...emptyServiceFormValues(),
    name: " slurmd ",
    status: "UNKNOWN",
  });
  assert.equal(parsed.ok, true);
  // 全部留空：status 默认 UNKNOWN 由显式值承载；description/metadata 省略（→ null / {}）
  assert.deepEqual(buildServiceCreateInput("r-uuid-1", parsed.fields, {}), {
    resource: "r-uuid-1",
    name: "slurmd",
    status: "UNKNOWN",
  });
  // 全字段登记：description 与非空 metadata 照常携带
  const full = parseServiceFormValues({
    ...emptyServiceFormValues(),
    name: "slurmd",
    status: "RUNNING",
    description: "Slurm compute daemon",
  });
  assert.equal(full.ok, true);
  assert.deepEqual(
    buildServiceCreateInput("r-uuid-1", full.fields, { port: 6818 }),
    {
      resource: "r-uuid-1",
      name: "slurmd",
      status: "RUNNING",
      description: "Slurm compute daemon",
      metadata: { port: 6818 },
    },
  );
});

await test("F011 buildServicePatch：exclude_unset 镜像（无变化 → null；name/status/description/metadata；resource 恒不上送）", async () => {
  // 无变化 → null（不发起空更新）
  const unchanged = parseServiceFormValues(serviceFormValuesFromService(serviceFixture));
  assert.equal(unchanged.ok, true);
  const unchangedMetadata = JSON.parse(
    serviceFormValuesFromService(serviceFixture).metadata,
  );
  assert.equal(buildServicePatch(serviceFixture, unchanged.fields, unchangedMetadata), null);
  // 仅改名（改后重检同 Resource 唯一由服务端 409 承载）
  const renamed = parseServiceFormValues({
    ...serviceFormValuesFromService(serviceFixture),
    name: "node_exporter",
  });
  assert.deepEqual(buildServicePatch(serviceFixture, renamed.fields, unchangedMetadata), {
    version: 3,
    name: "node_exporter",
  });
  // 仅改 status / 清空 description（显式 null）/ metadata 整值替换
  const statusChanged = parseServiceFormValues({
    ...serviceFormValuesFromService(serviceFixture),
    status: "STOPPED",
    description: "",
  });
  const statusPatch = buildServicePatch(serviceFixture, statusChanged.fields, {
    port: 6818,
    extra: true,
  });
  assert.deepEqual(statusPatch, {
    version: 3,
    status: "STOPPED",
    description: null,
    metadata: { port: 6818, extra: true },
  });
  // metadata 清空（→ {}）也携带（整值替换，与省略=保持可区分）
  const metadataCleared = buildServicePatch(serviceFixture, unchanged.fields, {});
  assert.deepEqual(metadataCleared, { version: 3, metadata: {} });
  // resource 创建后不可改（DR-144）：载荷恒不含 resource/resource_id
  const allChanged = parseServiceFormValues({
    ...serviceFormValuesFromService(serviceFixture),
    name: "sshd",
    status: "STOPPED",
    description: "",
    resource: "another-resource",
  });
  const allPatch = buildServicePatch(serviceFixture, allChanged.fields, {});
  assert.ok(!("resource" in allPatch), "PATCH 载荷不得携带 resource 键（DR-144）");
  assert.ok(!("resource_id" in allPatch), "PATCH 载荷不得携带 resource_id 键（DR-144）");
  assert.deepEqual(allPatch, {
    version: 3,
    name: "sshd",
    status: "STOPPED",
    description: null,
    metadata: {},
  });
});

await test("F011 serviceFormValuesFromService：null → 默认空值；metadata 对象 ↔ JSON 文本；空 metadata → 空文本", async () => {
  assert.deepEqual(serviceFormValuesFromService(null), emptyServiceFormValues());
  const values = serviceFormValuesFromService(serviceFixture);
  assert.equal(values.resource, serviceFixture.resource.id);
  assert.equal(values.name, "slurmd");
  assert.equal(values.status, "RUNNING");
  assert.equal(values.description, "Slurm compute daemon");
  assert.deepEqual(JSON.parse(values.metadata), { port: 6818 });
  // 空 metadata 对象 → 空文本（不显示 "{}" 噪音）；description null → 空串
  const emptyMeta = serviceFormValuesFromService({
    ...serviceFixture,
    description: null,
    metadata: {},
  });
  assert.equal(emptyMeta.metadata, "");
  assert.equal(emptyMeta.description, "");
});

// ---------- F012 ServiceEndpoint API 机制级（Contract：docs/api/F012.md v1） ----------

/** F012 用例共用的 ServiceEndpoint 夹具（Contract §3 形状：嵌套 service / ip_address 展开）。 */
const serviceEndpointFixture = {
  id: "0b9f4c6b-8f82-4b7a-9b95-a1e93b1f0c01",
  service: {
    id: "0b9f4c6b-8f82-4b7a-9b95-a1e93b1f0b01",
    name: "slurmd",
    resource: { id: "0b9f4c6b-8f82-4b7a-9b95-a1e93b1f0004", hostname: "cn001" },
  },
  ip_address: {
    id: "0b9f4c6b-8f82-4b7a-9b95-a1e93b1f0a01",
    address: "10.10.0.5",
    network: { id: "0b9f4c6b-8f82-4b7a-9b95-a1e93b1f0006", name: "mgmt" },
    interface: { id: "0b9f4c6b-8f82-4b7a-9b95-a1e93b1f0007", name: "eth0" },
  },
  protocol: "TCP",
  port: 6818,
  description: "Slurmd listen port",
  version: 2,
  created_at: "2026-10-09T08:00:00Z",
  updated_at: "2026-10-09T09:00:00Z",
  deleted_at: null,
};

await test("F012 listServiceEndpoints 默认：GET /api/v1/service-endpoints，无查询串", async () => {
  respond = () => jsonResponse(200, { items: [], page: 1, page_size: 20, total: 0 });
  const data = await listServiceEndpoints();
  assert.equal(data.total, 0);
  assert.equal(calls.length, 1);
  assert.equal(calls[0].url, "/api/v1/service-endpoints");
  assert.equal(calls[0].init.method, "GET");
  assert.equal(calls[0].init.credentials, "include");
});

await test("F012 listServiceEndpoints 组合查询：service_id/ip_address_id/protocol/deleted/分页/排序（AND 组合）", async () => {
  respond = () => jsonResponse(200, { items: [], page: 2, page_size: 50, total: 0 });
  await listServiceEndpoints({
    service_id: "0b9f4c6b-8f82-4b7a-9b95-a1e93b1f0b01",
    ip_address_id: "0b9f4c6b-8f82-4b7a-9b95-a1e93b1f0a01",
    protocol: "TCP",
    deleted: "only",
    page: 2,
    page_size: 50,
    sort: "port",
    order: "asc",
  });
  assert.equal(calls.length, 1);
  assert.equal(
    calls[0].url,
    "/api/v1/service-endpoints?service_id=0b9f4c6b-8f82-4b7a-9b95-a1e93b1f0b01" +
      "&ip_address_id=0b9f4c6b-8f82-4b7a-9b95-a1e93b1f0a01" +
      "&protocol=TCP&deleted=only&page=2&page_size=50&sort=port&order=asc",
  );
});

await test("F012 listServiceEndpoints 空串过滤项不发（service_id=''/ip_address_id=''），protocol 省略不发", async () => {
  respond = () => jsonResponse(200, { items: [], page: 1, page_size: 20, total: 0 });
  await listServiceEndpoints({ service_id: "", ip_address_id: "" });
  assert.equal(calls[0].url, "/api/v1/service-endpoints");
});

await test("F012 createServiceEndpoint：POST /service-endpoints + JSON body；201 解析 {service_endpoint}", async () => {
  respond = () => jsonResponse(201, { service_endpoint: serviceEndpointFixture });
  const { service_endpoint: endpoint } = await createServiceEndpoint({
    service: "0b9f4c6b-8f82-4b7a-9b95-a1e93b1f0b01",
    ip_address: "0b9f4c6b-8f82-4b7a-9b95-a1e93b1f0a01",
    protocol: "TCP",
    port: 6818,
    description: "Slurmd listen port",
  });
  assert.equal(endpoint.id, serviceEndpointFixture.id);
  assert.equal(endpoint.service.name, "slurmd");
  assert.equal(endpoint.service.resource.hostname, "cn001");
  assert.equal(endpoint.ip_address.address, "10.10.0.5");
  assert.equal(endpoint.ip_address.interface.name, "eth0");
  assert.equal(calls.length, 1);
  assert.equal(calls[0].url, "/api/v1/service-endpoints");
  assert.equal(calls[0].init.method, "POST");
  assert.deepEqual(JSON.parse(calls[0].init.body), {
    service: "0b9f4c6b-8f82-4b7a-9b95-a1e93b1f0b01",
    ip_address: "0b9f4c6b-8f82-4b7a-9b95-a1e93b1f0a01",
    protocol: "TCP",
    port: 6818,
    description: "Slurmd listen port",
  });
});

await test("F012 getServiceEndpoint：已删对象显式 ?deleted=true；默认不带", async () => {
  respond = () =>
    jsonResponse(200, {
      service_endpoint: { id: "e1", deleted_at: "2026-10-09T12:00:00Z" },
    });
  await getServiceEndpoint("e1", { deleted: true });
  await getServiceEndpoint("e1");
  assert.equal(calls[0].url, "/api/v1/service-endpoints/e1?deleted=true");
  assert.equal(calls[1].url, "/api/v1/service-endpoints/e1");
});

await test("F012 updateServiceEndpoint：PATCH 且仅携带变化字段（省略 = 不重置，Contract §6.4）", async () => {
  respond = () => jsonResponse(200, { service_endpoint: { id: "e1", version: 4 } });
  const { service_endpoint: endpoint } = await updateServiceEndpoint("e1", {
    version: 3,
    protocol: "UDP",
    port: 6819,
  });
  assert.equal(endpoint.version, 4);
  assert.equal(calls.length, 1);
  assert.equal(calls[0].url, "/api/v1/service-endpoints/e1");
  assert.equal(calls[0].init.method, "PATCH");
  // body 只含 version + 变化字段；service/ip_address 创建后不可改不出现（DR-157）
  assert.deepEqual(JSON.parse(calls[0].init.body), {
    version: 3,
    protocol: "UDP",
    port: 6819,
  });
});

await test("F012 updateServiceEndpoint：description 显式 null = 清空", async () => {
  respond = () => jsonResponse(200, { service_endpoint: { id: "e1" } });
  await updateServiceEndpoint("e1", { version: 3, description: null });
  assert.deepEqual(JSON.parse(calls[0].init.body), { version: 3, description: null });
});

await test("F012 deleteServiceEndpoint：DELETE + version 为 Query 参数；204 → undefined", async () => {
  respond = () => new Response(null, { status: 204 });
  const result = await deleteServiceEndpoint("e1", 5);
  assert.equal(result, undefined);
  assert.equal(calls.length, 1);
  assert.equal(calls[0].url, "/api/v1/service-endpoints/e1?version=5");
  assert.equal(calls[0].init.method, "DELETE");
});

await test("F012 restoreServiceEndpoint：POST /{id}/restore + version Query 参数", async () => {
  respond = () =>
    jsonResponse(200, { service_endpoint: { id: "e1", deleted_at: null, version: 7 } });
  const { service_endpoint: endpoint } = await restoreServiceEndpoint("e1", 6);
  assert.equal(endpoint.deleted_at, null);
  assert.equal(calls.length, 1);
  assert.equal(calls[0].url, "/api/v1/service-endpoints/e1/restore?version=6");
  assert.equal(calls[0].init.method, "POST");
});

await test("F012 getServiceEndpointActivity：GET /{id}/activity + deleted/page/page_size", async () => {
  respond = () =>
    jsonResponse(200, {
      items: [
        {
          id: "a1",
          action: "CREATE",
          operator_user_id: null,
          operator_username: "bootstrap",
          before_data: null,
          after_data: {
            service_id: "0b9f4c6b-8f82-4b7a-9b95-a1e93b1f0b01",
            ip_address_id: "0b9f4c6b-8f82-4b7a-9b95-a1e93b1f0a01",
            protocol: "TCP",
            port: 6818,
            description: null,
          },
          created_at: "2026-10-09T08:00:00Z",
        },
      ],
      page: 1,
      page_size: 20,
      total: 1,
    });
  const data = await getServiceEndpointActivity("e1", { deleted: true, page: 1, page_size: 20 });
  assert.equal(data.total, 1);
  assert.equal(data.items[0].action, "CREATE");
  assert.equal(data.items[0].after_data.port, 6818);
  assert.equal(calls.length, 1);
  assert.equal(
    calls[0].url,
    "/api/v1/service-endpoints/e1/activity?deleted=true&page=1&page_size=20",
  );
});

await test("F012 409 CONFLICT unique_conflict：落到 port 字段级错误、携带冲突监听三元组；不重试", async () => {
  respond = () =>
    jsonResponse(409, {
      error: {
        code: "CONFLICT",
        message: "Conflict",
        details: {
          reason: "unique_conflict",
          field: "port",
          ip_address_id: "0b9f4c6b-8f82-4b7a-9b95-a1e93b1f0a01",
          protocol: "TCP",
          port: 6818,
        },
      },
    });
  const err = await expectApiError(
    createServiceEndpoint({
      service: "0b9f4c6b-8f82-4b7a-9b95-a1e93b1f0b01",
      ip_address: "0b9f4c6b-8f82-4b7a-9b95-a1e93b1f0a01",
      protocol: "TCP",
      port: 6818,
    }),
  );
  assert.equal(err.status, 409);
  assert.equal(err.code, "CONFLICT");
  assert.equal(err.details.reason, "unique_conflict");
  const described = describeServiceEndpointActionError(err);
  assert.equal(described.versionConflict, false);
  assert.ok(described.fields.port, "unique_conflict 应落到 port 字段错误");
  assert.ok(described.fields.port.includes("IPAddress"), "应说明同 IP 作用域");
  assert.ok(described.message.includes("TCP/6818"), "应携带冲突 protocol/port");
  assert.ok(described.message.includes("ip_address_id="), "应携带冲突 ip_address_id");
  assert.equal(calls.length, 1); // 不自动重试
});

await test("F012 409 VERSION_CONFLICT：标记刷新后重改、携带 current_version；不重试", async () => {
  respond = () =>
    jsonResponse(409, {
      error: {
        code: "VERSION_CONFLICT",
        message: "Version conflict",
        details: { current_version: 9 },
      },
    });
  const err = await expectApiError(
    updateServiceEndpoint("e1", { version: 3, port: 6819 }),
  );
  assert.equal(err.details.current_version, 9);
  const described = describeServiceEndpointActionError(err);
  assert.equal(described.versionConflict, true);
  assert.equal(described.currentVersion, 9);
  assert.ok(described.message.includes("刷新"), "应提示刷新后重改");
  assert.ok(described.message.includes("不会自动重试"));
  assert.equal(calls.length, 1); // 不静默重试覆盖
});

await test("F012 409 CONFLICT dependency_deleted：按 object_type 区分文案（service / ip_address / interface）", async () => {
  // service 仍软删 → 所属服务文案
  respond = () =>
    jsonResponse(409, {
      error: {
        code: "CONFLICT",
        message: "Conflict",
        details: {
          reason: "dependency_deleted",
          conflicts: [{ object_type: "service", object_id: "s1" }],
        },
      },
    });
  const errService = await expectApiError(restoreServiceEndpoint("e1", 3));
  const describedService = describeServiceEndpointActionError(errService);
  assert.equal(describedService.dependencyConflicts.length, 1);
  assert.equal(describedService.dependencyConflicts[0].object_type, "service");
  assert.ok(describedService.message.includes("所属服务"));
  assert.ok(describedService.message.includes("CONFLICT/dependency_deleted"));

  // ip_address 仍软删 → 引用 IP 文案
  respond = () =>
    jsonResponse(409, {
      error: {
        code: "CONFLICT",
        message: "Conflict",
        details: {
          reason: "dependency_deleted",
          conflicts: [{ object_type: "ip_address", object_id: "ip1" }],
        },
      },
    });
  const errIp = await expectApiError(restoreServiceEndpoint("e1", 3));
  const describedIp = describeServiceEndpointActionError(errIp);
  assert.ok(describedIp.message.includes("IP 地址"));

  // interface 仍软删 → 绑定接口文案
  respond = () =>
    jsonResponse(409, {
      error: {
        code: "CONFLICT",
        message: "Conflict",
        details: {
          reason: "dependency_deleted",
          conflicts: [{ object_type: "interface", object_id: "if1" }],
        },
      },
    });
  const errIface = await expectApiError(restoreServiceEndpoint("e1", 3));
  const describedIface = describeServiceEndpointActionError(errIface);
  assert.ok(describedIface.message.includes("接口"));

  // 混合依赖 → 通用文案（不伪装成单一原因）
  respond = () =>
    jsonResponse(409, {
      error: {
        code: "CONFLICT",
        message: "Conflict",
        details: {
          reason: "dependency_deleted",
          conflicts: [
            { object_type: "service", object_id: "s1" },
            { object_type: "interface", object_id: "if1" },
          ],
        },
      },
    });
  const errMixed = await expectApiError(restoreServiceEndpoint("e1", 3));
  const describedMixed = describeServiceEndpointActionError(errMixed);
  assert.equal(describedMixed.dependencyConflicts.length, 2);
  assert.ok(describedMixed.message.includes("依赖对象"));
});

await test("F012 409 CONFLICT not_deleted：恢复未删对象的明确文案", async () => {
  respond = () =>
    jsonResponse(409, {
      error: { code: "CONFLICT", message: "Conflict", details: { reason: "not_deleted" } },
    });
  const err = await expectApiError(restoreServiceEndpoint("e1", 3));
  const described = describeServiceEndpointActionError(err);
  assert.ok(described.message.includes("未处于已删除状态"));
  assert.ok(described.message.includes("CONFLICT/not_deleted"));
});

await test("F012 409 CONFLICT reference_exists：解析 references（防御，Endpoint 无子对象）", async () => {
  respond = () =>
    jsonResponse(409, {
      error: {
        code: "CONFLICT",
        message: "Conflict",
        details: {
          reason: "reference_exists",
          references: [{ object_type: "service_endpoint", object_id: "e2", label: "TCP/22" }],
        },
      },
    });
  const err = await expectApiError(deleteServiceEndpoint("e1", 3));
  const described = describeServiceEndpointActionError(err);
  assert.equal(described.versionConflict, false);
  assert.equal(described.references.length, 1);
  assert.equal(described.references[0].object_type, "service_endpoint");
  assert.equal(described.references[0].label, "TCP/22");
  assert.ok(described.message.includes("CONFLICT/reference_exists"));
});

await test("F012 422 VALIDATION_ERROR：details.fields 透传为字段级错误（含 service / ip_address）", async () => {
  respond = () =>
    jsonResponse(422, {
      error: {
        code: "VALIDATION_ERROR",
        message: "Validation error",
        details: {
          fields: [
            { field: "service", message: "服务不存在或已删除" },
            { field: "ip_address", message: "IP 未绑定接口或不属于服务所在资源" },
            { field: "protocol", message: "protocol 必须为 TCP 或 UDP" },
            { field: "port", message: "port 必须在 1–65535 范围内" },
          ],
        },
      },
    });
  const err = await expectApiError(
    createServiceEndpoint({
      service: "nope",
      ip_address: "nope",
      protocol: "tcp",
      port: 0,
    }),
  );
  const described = describeServiceEndpointActionError(err);
  assert.equal(described.fields.service, "服务不存在或已删除");
  assert.equal(described.fields.ip_address, "IP 未绑定接口或不属于服务所在资源");
  assert.equal(described.fields.protocol, "protocol 必须为 TCP 或 UDP");
  assert.equal(described.fields.port, "port 必须在 1–65535 范围内");
});

await test("F012 403 / 404：明确文案（不泄露存在性 / 权限不足）", async () => {
  respond = () =>
    jsonResponse(403, {
      error: { code: "FORBIDDEN", message: "没有权限", details: { reason: "permission" } },
    });
  const err403 = await expectApiError(deleteServiceEndpoint("e1", 3));
  assert.ok(describeServiceEndpointActionError(err403).message.includes("没有权限"));
  respond = () =>
    jsonResponse(404, { error: { code: "NOT_FOUND", message: "不存在", details: {} } });
  const err404 = await expectApiError(getServiceEndpoint("e1"));
  assert.ok(describeServiceEndpointActionError(err404).message.includes("监听端点不存在"));
});

await test("F012 网络层错误（fetch reject）：不伪装成业务结果", async () => {
  respond = () => Promise.reject(new TypeError("Failed to fetch"));
  await assert.rejects(listServiceEndpoints(), TypeError);
  assert.equal(calls.length, 1); // 失败不重发
  const described = describeServiceEndpointActionError(new TypeError("Failed to fetch"));
  assert.equal(described.message, "无法连接服务器，请稍后重试");
  assert.equal(described.versionConflict, false);
});

await test("F012 parseServiceEndpointFormValues：合法值（trim / 边界 1 与 65535 / 空描述=null）", async () => {
  const parsed = parseServiceEndpointFormValues({
    ...emptyServiceEndpointFormValues(),
    service: "s-1",
    ipAddress: "ip-1",
    protocol: "TCP",
    port: " 6818 ",
    description: "示例描述",
  });
  assert.equal(parsed.ok, true);
  assert.equal(parsed.fields.protocol, "TCP");
  assert.equal(parsed.fields.port, 6818); // trim 后严格整数
  assert.equal(parsed.fields.description, "示例描述");
  // 空描述 → null；UDP 合法
  const emptyDesc = parseServiceEndpointFormValues({
    ...emptyServiceEndpointFormValues(),
    protocol: "UDP",
    port: "53",
  });
  assert.equal(emptyDesc.ok, true);
  assert.equal(emptyDesc.fields.description, null);
  // 边界 1 与 65535 接受（含端点，Contract §2.2）
  assert.equal(
    parseServiceEndpointFormValues({ ...emptyServiceEndpointFormValues(), port: "1" }).ok,
    true,
  );
  assert.equal(
    parseServiceEndpointFormValues({
      ...emptyServiceEndpointFormValues(),
      port: "65535",
    }).ok,
    true,
  );
});

await test("F012 parseServiceEndpointFormValues：非法输入 → 字段级错误（空 / 0 / 65536 / 负 / 非整数 / 非法 protocol）", async () => {
  const portCases = [
    { port: "", hint: "不能为空" },
    { port: "0", hint: "1–65535" },
    { port: "65536", hint: "1–65535" },
    { port: "-1", hint: "1–65535" },
    { port: "1.5", hint: "整数" },
    { port: "abc", hint: "整数" },
    { port: "  ", hint: "不能为空" },
  ];
  for (const { port, hint } of portCases) {
    const parsed = parseServiceEndpointFormValues({
      ...emptyServiceEndpointFormValues(),
      port,
    });
    assert.equal(parsed.ok, false, `应校验失败：port=${JSON.stringify(port)}`);
    if (!parsed.ok) {
      assert.ok(parsed.errors.port, "应产生 port 字段错误");
      assert.ok(
        parsed.errors.port.includes(hint),
        `port 错误文案应含「${hint}」，实际：${parsed.errors.port}`,
      );
    }
  }
  // protocol 仅大写规范值（"tcp" 不归一化、直接报错，Contract §2.2/DR-160）
  const badProtocol = parseServiceEndpointFormValues({
    ...emptyServiceEndpointFormValues(),
    protocol: "tcp",
    port: "6818",
  });
  assert.equal(badProtocol.ok, false);
  assert.ok(badProtocol.errors.protocol.includes("TCP"));
  // 多字段同时非法 → 同时报错
  const both = parseServiceEndpointFormValues({
    ...emptyServiceEndpointFormValues(),
    protocol: "tcp",
    port: "0",
  });
  assert.equal(both.ok, false);
  assert.ok(both.errors.protocol);
  assert.ok(both.errors.port);
});

await test("F012 serviceEndpointFormFieldFromPath：422 点路径 → 表单键（顶层直通；不可变别名 → null）", async () => {
  assert.equal(serviceEndpointFormFieldFromPath("service"), "service");
  assert.equal(serviceEndpointFormFieldFromPath("ip_address"), "ip_address");
  assert.equal(serviceEndpointFormFieldFromPath("protocol"), "protocol");
  assert.equal(serviceEndpointFormFieldFromPath("port"), "port");
  assert.equal(serviceEndpointFormFieldFromPath("description"), "description");
  assert.equal(serviceEndpointFormFieldFromPath("service_id"), null); // 不可变别名不映射
  assert.equal(serviceEndpointFormFieldFromPath("ip_address_id"), null); // 不可变别名不映射
  assert.equal(serviceEndpointFormFieldFromPath("metadata"), null); // 不落字段（I-1/DR-156）
  assert.equal(serviceEndpointFormFieldFromPath("unknown.field"), null);
});

await test("F012 buildServiceEndpointCreateInput：service/ip_address/protocol/port 恒携带；description 仅已登记值", async () => {
  const parsed = parseServiceEndpointFormValues({
    ...emptyServiceEndpointFormValues(),
    protocol: "TCP",
    port: "6818",
  });
  assert.equal(parsed.ok, true);
  // 未设置描述：description 省略（→ null，Contract §2.5）
  assert.deepEqual(
    buildServiceEndpointCreateInput("s-1", "ip-1", parsed.fields),
    {
      service: "s-1",
      ip_address: "ip-1",
      protocol: "TCP",
      port: 6818,
    },
  );
  // 已设置描述照常携带
  const withDesc = parseServiceEndpointFormValues({
    ...emptyServiceEndpointFormValues(),
    protocol: "UDP",
    port: "53",
    description: "DNS",
  });
  assert.equal(withDesc.ok, true);
  assert.deepEqual(
    buildServiceEndpointCreateInput("s-1", "ip-1", withDesc.fields),
    {
      service: "s-1",
      ip_address: "ip-1",
      protocol: "UDP",
      port: 53,
      description: "DNS",
    },
  );
});

await test("F012 buildServiceEndpointPatch：exclude_unset 镜像（无变化 → null；service/ip_address 恒不上送）", async () => {
  // 无变化 → null（不发起空更新）
  const unchanged = parseServiceEndpointFormValues(
    serviceEndpointFormValuesFromEndpoint(serviceEndpointFixture),
  );
  assert.equal(unchanged.ok, true);
  assert.equal(
    buildServiceEndpointPatch(serviceEndpointFixture, unchanged.fields),
    null,
  );
  // 改 protocol/port（改后重检同 IP 监听唯一由服务端 409 承载）+ 清空 description
  const changed = parseServiceEndpointFormValues({
    ...serviceEndpointFormValuesFromEndpoint(serviceEndpointFixture),
    protocol: "UDP",
    port: "6819",
    description: "",
  });
  assert.equal(changed.ok, true);
  assert.deepEqual(
    buildServiceEndpointPatch(serviceEndpointFixture, changed.fields),
    { version: 2, protocol: "UDP", port: 6819, description: null },
  );
  // 仅改 description（非清空）→ 只携带 description
  const descOnly = parseServiceEndpointFormValues({
    ...serviceEndpointFormValuesFromEndpoint(serviceEndpointFixture),
    description: "新描述",
  });
  assert.deepEqual(
    buildServiceEndpointPatch(serviceEndpointFixture, descOnly.fields),
    { version: 2, description: "新描述" },
  );
  // service/ip_address 创建后不可改（DR-157）：载荷恒不含这些键（即使表单值被篡改）
  const tampered = parseServiceEndpointFormValues({
    ...serviceEndpointFormValuesFromEndpoint(serviceEndpointFixture),
    service: "another-service",
    ipAddress: "another-ip",
    port: "6820",
  });
  const tamperedPatch = buildServiceEndpointPatch(serviceEndpointFixture, tampered.fields);
  assert.ok(!("service" in tamperedPatch), "PATCH 载荷不得携带 service 键（DR-157）");
  assert.ok(!("service_id" in tamperedPatch), "PATCH 载荷不得携带 service_id 键");
  assert.ok(!("ip_address" in tamperedPatch), "PATCH 载荷不得携带 ip_address 键（DR-157）");
  assert.ok(!("ip_address_id" in tamperedPatch), "PATCH 载荷不得携带 ip_address_id 键");
  assert.deepEqual(tamperedPatch, { version: 2, port: 6820 });
});

await test("F012 serviceEndpointFormValuesFromEndpoint：null → 默认空值；嵌套引用 id 提取与 port 字符串化", async () => {
  assert.deepEqual(
    serviceEndpointFormValuesFromEndpoint(null),
    emptyServiceEndpointFormValues(),
  );
  const values = serviceEndpointFormValuesFromEndpoint(serviceEndpointFixture);
  assert.equal(values.service, serviceEndpointFixture.service.id);
  assert.equal(values.ipAddress, serviceEndpointFixture.ip_address.id);
  assert.equal(values.protocol, "TCP");
  assert.equal(values.port, "6818"); // 数值 → 文本（表单输入）
  assert.equal(values.description, "Slurmd listen port");
  // description null → 空串；往返解析后无变化（与 buildServiceEndpointPatch=null 联动）
  const noDesc = serviceEndpointFormValuesFromEndpoint({
    ...serviceEndpointFixture,
    description: null,
  });
  assert.equal(noDesc.description, "");
  const roundTrip = parseServiceEndpointFormValues(noDesc);
  assert.equal(roundTrip.ok, true);
  assert.equal(
    buildServiceEndpointPatch(
      { ...serviceEndpointFixture, description: null },
      roundTrip.fields,
    ),
    null,
  );
});

// ---------- F013 全局搜索 / Dashboard 机制级（Contract：docs/api/F013.md v1） ----------

/** F013 搜索 typed 行响应样本（Contract §2.2：四类行各一，去重键 (object_type,id)）。 */
const SEARCH_RESPONSE_FIXTURE = {
  items: [
    {
      object_type: "resource",
      id: "r-uuid-1",
      matched_field: "hostname",
      matched_value: "gpu0701",
      resource: {
        id: "r-uuid-1",
        hostname: "gpu0701",
        resource_type: "BARE_METAL",
        role: "COMPUTE",
        status: "IDLE",
        cluster: { id: "c-uuid-1", code: "N96P", name: "N96P 集群" },
      },
      cluster: null,
      ip_address: null,
      service: null,
    },
    {
      object_type: "cluster",
      id: "c-uuid-1",
      matched_field: "code",
      matched_value: "N96P",
      resource: null,
      cluster: { id: "c-uuid-1", code: "N96P", name: "N96P 集群", status: "ACTIVE" },
      ip_address: null,
      service: null,
    },
    {
      object_type: "ip_address",
      id: "ip-uuid-1",
      matched_field: "address",
      matched_value: "10.10.1.50",
      resource: {
        id: "r-uuid-1",
        hostname: "gpu0701",
        resource_type: "BARE_METAL",
        role: "COMPUTE",
        status: "IDLE",
        cluster: { id: "c-uuid-1", code: "N96P", name: "N96P 集群" },
      },
      cluster: null,
      ip_address: {
        id: "ip-uuid-1",
        address: "10.10.1.50",
        network: { id: "n-uuid-1", name: "mgmt" },
        interface: { id: "if-uuid-1", name: "eth0" },
      },
      service: null,
    },
    {
      object_type: "ip_address",
      id: "ip-uuid-2",
      matched_field: "address",
      matched_value: "10.20.1.50",
      resource: null,
      cluster: null,
      ip_address: {
        id: "ip-uuid-2",
        address: "10.20.1.50",
        network: { id: "n-uuid-2", name: "storage" },
        interface: null,
      },
      service: null,
    },
    {
      object_type: "service",
      id: "s-uuid-1",
      matched_field: "name",
      matched_value: "slurmd",
      resource: {
        id: "r-uuid-1",
        hostname: "gpu0701",
        resource_type: "BARE_METAL",
        role: "COMPUTE",
        status: "IDLE",
        cluster: { id: "c-uuid-1", code: "N96P", name: "N96P 集群" },
      },
      cluster: null,
      ip_address: null,
      service: { id: "s-uuid-1", name: "slurmd", status: "RUNNING" },
    },
  ],
  page: 1,
  page_size: 20,
  total: 5,
};

await test("F013 search：q 必携带；默认无其余参数（deleted 等由服务端默认生效）", async () => {
  respond = () => jsonResponse(200, { items: [], page: 1, page_size: 20, total: 0 });
  const data = await search({ q: "gpu07" });
  assert.equal(data.total, 0);
  assert.equal(calls.length, 1);
  assert.equal(calls[0].url, "/api/v1/search?q=gpu07");
  assert.equal(calls[0].init.method, "GET");
  assert.equal(calls[0].init.credentials, "include");
});

await test("F013 search 组合查询：type/deleted/page/page_size 序列化（AND 组合）", async () => {
  respond = () => jsonResponse(200, { items: [], page: 2, page_size: 50, total: 0 });
  await search({ q: " gpu 07 ", type: "resource", deleted: "only", page: 2, page_size: 50 });
  assert.equal(calls.length, 1);
  // q 原样上送（trim 由调用方 / globalSearchForm 负责；URLSearchParams 将空格编码为 +）
  assert.equal(
    calls[0].url,
    "/api/v1/search?q=+gpu+07+&type=resource&deleted=only&page=2&page_size=50",
  );
});

await test("F013 search 响应解析：typed 行（4 类）、嵌套对象、未绑定 IP resource=null", async () => {
  respond = () => jsonResponse(200, SEARCH_RESPONSE_FIXTURE);
  const data = await search({ q: "07" });
  assert.equal(data.total, 5);
  assert.equal(data.items.length, 5);
  const [resource, cluster, boundIp, unboundIp, service] = data.items;
  // resource 行仅由 hostname 命中产生（§2.3）；其余嵌套对象为 null（字段集不因查询变化）
  assert.equal(resource.object_type, "resource");
  assert.equal(resource.resource.hostname, "gpu0701");
  assert.equal(resource.cluster, null);
  // cluster 行：code 与 name 皆命中取 code（确定性，§2.2）
  assert.equal(cluster.matched_field, "code");
  assert.equal(cluster.cluster.code, "N96P");
  assert.equal(cluster.cluster.status, "ACTIVE");
  // 已绑定 IP：经 interface→resource 填充 resource（§2.4）
  assert.equal(boundIp.object_type, "ip_address");
  assert.equal(boundIp.ip_address.interface.name, "eth0");
  assert.equal(boundIp.resource.hostname, "gpu0701");
  // 未绑定 IP：resource=null，不伪造归属（A5/I-6）
  assert.equal(unboundIp.resource, null);
  assert.equal(unboundIp.ip_address.interface, null);
  assert.equal(unboundIp.ip_address.network.name, "storage");
  // service 行：嵌入承载 Resource（§2.2）
  assert.equal(service.object_type, "service");
  assert.equal(service.service.status, "RUNNING");
  assert.equal(service.resource.id, "r-uuid-1");
});

await test("F013 空结果：200 空列表（非 404 / 500，I-3）", async () => {
  respond = () => jsonResponse(200, { items: [], page: 1, page_size: 20, total: 0 });
  const data = await search({ q: "不存在的对象" });
  assert.deepEqual(data.items, []);
  assert.equal(data.total, 0);
});

await test("F013 describeSearchError：401 / 403（permission 与未知 reason）/ 422 / 网络层", async () => {
  respond = () =>
    jsonResponse(401, {
      error: { code: "AUTH_REQUIRED", message: "未认证或会话已过期", details: {} },
    });
  const unauth = await expectApiError(search({ q: "x" }));
  assert.ok(describeSearchError(unauth).message.includes("AUTH_REQUIRED"));

  respond = () =>
    jsonResponse(403, {
      error: {
        code: "FORBIDDEN",
        message: "Forbidden",
        details: { reason: "permission" },
      },
    });
  const forbidden = await expectApiError(search({ q: "x", deleted: "only" }));
  const forbiddenDescribed = describeSearchError(forbidden);
  assert.ok(forbiddenDescribed.message.includes("VIEW_DELETED"));
  assert.ok(forbiddenDescribed.message.includes("FORBIDDEN"));

  // 未知 reason：原样透出 reason 值，不伪装成已知原因
  respond = () =>
    jsonResponse(403, {
      error: {
        code: "FORBIDDEN",
        message: "Forbidden",
        details: { reason: "something_else" },
      },
    });
  const unknownReason = await expectApiError(search({ q: "x" }));
  assert.ok(describeSearchError(unknownReason).message.includes("something_else"));

  respond = () =>
    jsonResponse(422, {
      error: {
        code: "VALIDATION_ERROR",
        message: "Validation error",
        details: {
          fields: [
            { field: "q", message: "不能为空" },
            { field: "type", message: "非法枚举值" },
          ],
        },
      },
    });
  const invalid = await expectApiError(search({ q: "x", type: "bogus" }));
  const invalidDescribed = describeSearchError(invalid);
  assert.equal(invalidDescribed.fields.q, "不能为空");
  assert.equal(invalidDescribed.fields.type, "非法枚举值");
  assert.ok(invalidDescribed.message.includes("VALIDATION_ERROR"));

  // 网络层错误（fetch reject）：固定文案，不伪装成业务结果
  respond = () => Promise.reject(new TypeError("Failed to fetch"));
  await assert.rejects(search({ q: "x" }), TypeError);
  const networkDescribed = describeSearchError(new TypeError("Failed to fetch"));
  assert.ok(networkDescribed.message.includes("无法连接服务器"));
  // 本用例共发起 5 次请求（401/403×2/422/网络层），每次恰好一次、不重试
  assert.equal(calls.length, 5);
});

/** F013 Dashboard 响应样本（Contract §3.2：counts + networks 行 + AUTO 池，含负 remaining）。 */
const DASHBOARD_RESPONSE_FIXTURE = {
  counts: {
    clusters: 3,
    resources: 128,
    bare_metal: 96,
    virtual_machines: 32,
    networks: 7,
  },
  networks: {
    items: [
      {
        network: {
          id: "n-uuid-1",
          name: "mgmt",
          cidr: "10.10.0.0/16",
          status: "ACTIVE",
          auto_allocate: true,
          cluster: { id: "c-uuid-1", code: "N96P", name: "N96P 集群" },
        },
        capacity: { allocatable_total: 65534, occupied: 120, remaining: 65414 },
        auto_pools: [
          {
            ip_pool: {
              id: "p-uuid-1",
              name: "auto",
              start_address: "10.10.1.50",
              end_address: "10.10.1.200",
            },
            allocatable_total: 151,
            occupied: 12,
            remaining: 139,
          },
        ],
      },
      {
        // INACTIVE 网络：容量不清零、仍出现（A19）；remaining 为负原样返回（DR-130）
        network: {
          id: "n-uuid-2",
          name: "legacy",
          cidr: "10.20.0.0/24",
          status: "INACTIVE",
          auto_allocate: false,
          cluster: { id: "c-uuid-1", code: "N96P", name: "N96P 集群" },
        },
        capacity: { allocatable_total: 250, occupied: 251, remaining: -1 },
        auto_pools: [],
      },
    ],
    page: 1,
    page_size: 20,
    total: 7,
  },
};

await test("F013 getDashboard 默认：GET /api/v1/dashboard，无查询串", async () => {
  respond = () => jsonResponse(200, DASHBOARD_RESPONSE_FIXTURE);
  const data = await getDashboard();
  assert.equal(data.counts.clusters, 3);
  assert.equal(calls.length, 1);
  assert.equal(calls[0].url, "/api/v1/dashboard");
  assert.equal(calls[0].init.method, "GET");
  assert.equal(calls[0].init.credentials, "include");
});

await test("F013 getDashboard 分页：page/page_size 仅作用于 networks", async () => {
  respond = () => jsonResponse(200, DASHBOARD_RESPONSE_FIXTURE);
  const data = await getDashboard({ page: 2, page_size: 50 });
  assert.equal(calls.length, 1);
  assert.equal(calls[0].url, "/api/v1/dashboard?page=2&page_size=50");
  // counts 不受分页影响（恒为全局未删口径，§3.2）
  assert.equal(data.counts.networks, 7);
  assert.equal(data.networks.page, 1);
});

await test("F013 getDashboard 响应解析：counts / capacity / auto_pools / 负 remaining 原样", async () => {
  respond = () => jsonResponse(200, DASHBOARD_RESPONSE_FIXTURE);
  const data = await getDashboard();
  const [active, inactive] = data.networks.items;
  // 容量三元组只消费不重算（DR-182）
  assert.equal(active.capacity.allocatable_total, 65534);
  assert.equal(active.capacity.occupied, 120);
  assert.equal(active.capacity.remaining, 65414);
  // 每行 AUTO 池容量（池范围口径）
  assert.equal(active.auto_pools.length, 1);
  assert.equal(active.auto_pools[0].ip_pool.name, "auto");
  assert.equal(active.auto_pools[0].remaining, 139);
  // INACTIVE 网络：容量不清零；status / auto_allocate 与容量分别展示（A19）
  assert.equal(inactive.network.status, "INACTIVE");
  assert.equal(inactive.network.auto_allocate, false);
  assert.equal(inactive.capacity.remaining, -1); // 可为负、原样返回不截断（DR-130）
  assert.deepEqual(inactive.auto_pools, []); // 无 AUTO 池为空数组非 null
  // counts 为未删口径（bare_metal + virtual_machines = resources）
  assert.equal(data.counts.bare_metal + data.counts.virtual_machines, data.counts.resources);
});

await test("F013 describeDashboardError：401 / 403 / 422 / 网络层（不伪装成空数据）", async () => {
  respond = () =>
    jsonResponse(401, {
      error: { code: "AUTH_REQUIRED", message: "未认证或会话已过期", details: {} },
    });
  const unauth = await expectApiError(getDashboard());
  assert.ok(describeDashboardError(unauth).message.includes("AUTH_REQUIRED"));

  respond = () =>
    jsonResponse(403, {
      error: {
        code: "FORBIDDEN",
        message: "Forbidden",
        details: { reason: "permission" },
      },
    });
  const forbidden = await expectApiError(getDashboard());
  assert.ok(describeDashboardError(forbidden).message.includes("FORBIDDEN"));

  respond = () =>
    jsonResponse(422, {
      error: {
        code: "VALIDATION_ERROR",
        message: "Validation error",
        details: { fields: [{ field: "page", message: "必须 ≥ 1" }] },
      },
    });
  const invalid = await expectApiError(getDashboard({ page: 0 }));
  assert.ok(describeDashboardError(invalid).message.includes("page"));

  respond = () => Promise.reject(new TypeError("Failed to fetch"));
  await assert.rejects(getDashboard(), TypeError);
  const networkDescribed = describeDashboardError(new TypeError("Failed to fetch"));
  assert.ok(networkDescribed.message.includes("无法连接服务器"));
  // 本用例共发起 4 次请求（401/403/422/网络层），每次恰好一次、不重试
  assert.equal(calls.length, 4);
});

await test("F013 buildSearchQuery：空 / 纯空白 q → null（不发请求，I-13）；trim 后携带", async () => {
  const empty = emptyGlobalSearchFormValues();
  assert.equal(buildSearchQuery(empty), null);
  assert.equal(
    buildSearchQuery({ ...empty, q: "   \t\n " }),
    null,
    "纯空白 q 同样不发请求（服务端 422 field=q，前端本地拦截）",
  );
  const query = buildSearchQuery({ ...empty, q: "  gpu07 " });
  assert.deepEqual(query, {
    q: "gpu07",
    deleted: "exclude",
    page: 1,
    page_size: 20,
  });
  // type 非空才携带（空 = 全部，省略参数）；deleted / page / page_size 原样序列化
  assert.deepEqual(
    buildSearchQuery({ q: "N96P", type: "cluster", deleted: "include", page: 3, pageSize: 100 }),
    { q: "N96P", type: "cluster", deleted: "include", page: 3, page_size: 100 },
  );
});

await test("F013 parseGlobalSearchFormValues：空 q / 超长 255 code point / 非法 type → 本地错误", async () => {
  // 空 / 纯空白 q：本地拦截（不发起请求）
  assert.equal(parseGlobalSearchFormValues({ q: "   ", type: "" }).ok, false);
  // 恰 255 code point 合法（含端点）；256 报错（含中文按 code point 计长，非 UTF-16 码元）
  const atLimit = parseGlobalSearchFormValues({ q: "a".repeat(255), type: "" });
  assert.equal(atLimit.ok, true);
  const cjk = "\u96c6\u7fa4".repeat(128); // 256 code points
  assert.equal(Array.from(cjk).length, 256);
  const tooLong = parseGlobalSearchFormValues({ q: cjk, type: "" });
  assert.equal(tooLong.ok, false);
  if (!tooLong.ok) {
    assert.ok(tooLong.errors.q.includes("255"));
  }
  // type 自由输入非法值：不归一化、不改写，直接报错（服务端同样 422 field=type）
  for (const badType of ["Resource", "resource ", "bogus"]) {
    const bad = parseGlobalSearchFormValues({ q: "x", type: badType });
    assert.equal(bad.ok, false, `type=${JSON.stringify(badType)} 应本地报错`);
    if (!bad.ok) {
      assert.ok(bad.errors.type);
    }
  }
  // 合法枚举值全部通过（含空串 = 全部）
  for (const goodType of ["", "resource", "cluster", "ip_address", "service"]) {
    assert.equal(parseGlobalSearchFormValues({ q: "x", type: goodType }).ok, true);
  }
});

await test("F013 searchFormFieldFromPath：422 点路径 → 表单键（顶层直通；未知 → null）", async () => {
  assert.equal(searchFormFieldFromPath("q"), "q");
  assert.equal(searchFormFieldFromPath("type"), "type");
  assert.equal(searchFormFieldFromPath("deleted"), "deleted");
  assert.equal(searchFormFieldFromPath("page"), "page");
  assert.equal(searchFormFieldFromPath("page_size"), "page_size");
  assert.equal(searchFormFieldFromPath("object.field"), null); // 未知路径不强行映射
  assert.equal(searchFormFieldFromPath("cluster"), null);
});

await test("F013 highlightSegments：ASCII 大小写不敏感子串；非子串模糊命中 / 空 q 不高亮", async () => {
  // 命中：命中段保留原展示大小写（不改写值），前缀 / 后缀分段
  assert.deepEqual(highlightSegments("GPU0701", "gpu07"), [
    { text: "GPU07", hit: true },
    { text: "01", hit: false },
  ]);
  // 中段命中：前缀 / 命中 / 后缀三段
  assert.deepEqual(highlightSegments("cn-gpu0701.n96p", "GPU07"), [
    { text: "cn-", hit: false },
    { text: "gpu07", hit: true },
    { text: "01.n96p", hit: false },
  ]);
  // 模糊（trigram）命中但非连续子串：整段不高亮，不伪造高亮位置
  assert.deepEqual(highlightSegments("gpu0701", "gp07"), [
    { text: "gpu0701", hit: false },
  ]);
  // 空 q / 纯空白：整段不高亮
  assert.deepEqual(highlightSegments("gpu0701", "   "), [
    { text: "gpu0701", hit: false },
  ]);
  // 中文与内部空格原样保留（ASCII 折叠不影响非 ASCII，A3）
  assert.deepEqual(highlightSegments("集群 gpu0701", "gpu07"), [
    { text: "集群 ", hit: false },
    { text: "gpu07", hit: true },
    { text: "01", hit: false },
  ]);
});

// ---------- F014 Import API 机制级（Contract：docs/api/F014.md v1） ----------

/** 构造最小 CSV 测试文件（multipart file 字段）。 */
function importCsvFile(name = "resources.csv") {
  return new File(
    ["cluster,hostname,resource_type\nN96P,cn001,BARE_METAL\n"],
    name,
    { type: "text/csv" },
  );
}

await test("F014 getImportTemplates：GET /api/v1/imports/resources/templates；解析两套模板列描述", async () => {
  respond = () =>
    jsonResponse(200, {
      templates: [
        {
          resource_type: "BARE_METAL",
          columns: [
            { name: "cluster", required: true, target: "resource.cluster", type: "string", unit: null, enum: null, description: "Cluster code (case-insensitive) or UUID; must exist and be undeleted", example: "N96P" },
            { name: "memory_mb", required: false, target: "hardware.memory_mb", type: "integer", unit: "MiB", enum: null, description: "Physical memory; empty = unknown (null)", example: "262144" },
            { name: "role", required: false, target: "resource.role", type: "enum", unit: null, enum: ["COMPUTE", "LOGIN", "OTHER"], description: "Role; empty→OTHER", example: "COMPUTE" },
          ],
        },
        {
          resource_type: "VIRTUAL_MACHINE",
          columns: [
            { name: "host", required: true, target: "virtual_machine.host_resource_id", type: "string", unit: null, enum: null, description: "Hostname (or UUID) of an existing, undeleted BARE_METAL host in the same cluster", example: "cn001" },
          ],
        },
      ],
    });
  const data = await getImportTemplates();
  assert.equal(data.templates.length, 2);
  assert.equal(data.templates[0].resource_type, "BARE_METAL");
  assert.equal(data.templates[0].columns[1].unit, "MiB");
  assert.equal(data.templates[0].columns[1].required, false);
  assert.deepEqual(data.templates[0].columns[2].enum, ["COMPUTE", "LOGIN", "OTHER"]);
  assert.equal(data.templates[1].columns[0].name, "host");
  assert.equal(calls.length, 1);
  assert.equal(calls[0].url, "/api/v1/imports/resources/templates");
  assert.equal(calls[0].init.method, "GET");
  assert.equal(calls[0].init.credentials, "include");
});

await test("F014 validateResourceImport：POST multipart（FormData：file+format），不手动设 Content-Type", async () => {
  respond = () =>
    jsonResponse(200, {
      format: "csv",
      total_rows: 12,
      importable_rows: 10,
      error_count: 3,
      errors: [
        { row: 4, field: "cluster", reason: "cluster does not exist or is not selectable", related_row: null },
        { row: 7, field: "hostname", reason: "duplicate hostname within file (also at row 2)", related_row: 2 },
      ],
      errors_truncated: false,
    });
  const file = importCsvFile();
  const data = await validateResourceImport(file, "csv");
  assert.equal(data.format, "csv");
  assert.equal(data.total_rows, 12);
  assert.equal(data.importable_rows, 10);
  assert.equal(data.error_count, 3);
  assert.equal(data.errors[1].related_row, 2);
  assert.equal(data.errors_truncated, false);
  assert.equal(calls.length, 1);
  assert.equal(calls[0].url, "/api/v1/imports/resources/validate");
  assert.equal(calls[0].init.method, "POST");
  assert.equal(calls[0].init.credentials, "include");
  // multipart：body 为 FormData；不得手动设置 Content-Type（boundary 由 fetch 生成）
  assert.ok(calls[0].init.body instanceof FormData, "body 应为 FormData（multipart）");
  assert.ok(
    !("Content-Type" in (calls[0].init.headers ?? {})),
    "不得手动设置 Content-Type（boundary 由 fetch 生成）",
  );
  assert.equal(calls[0].init.headers["Accept"], "application/json");
  assert.equal(calls[0].init.body.get("format"), "csv");
  const uploaded = calls[0].init.body.get("file");
  assert.ok(uploaded instanceof File, "file 字段应为文件对象");
  assert.equal(uploaded.name, "resources.csv");
  assert.equal(uploaded.size, file.size);
});

await test("F014 importResources：POST /imports/resources multipart；201 解析 {created,total_rows}", async () => {
  respond = () => jsonResponse(201, { created: 10, total_rows: 10 });
  const file = new File(
    [new Uint8Array([0x50, 0x4b, 0x03, 0x04])],
    "resources.xlsx",
    { type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" },
  );
  const data = await importResources(file, "xlsx");
  assert.equal(data.created, 10);
  assert.equal(data.total_rows, 10);
  assert.equal(calls.length, 1);
  assert.equal(calls[0].url, "/api/v1/imports/resources");
  assert.equal(calls[0].init.method, "POST");
  assert.equal(calls[0].init.credentials, "include");
  assert.ok(calls[0].init.body instanceof FormData);
  assert.equal(calls[0].init.body.get("format"), "xlsx");
  assert.equal(calls[0].init.body.get("file").name, "resources.xlsx");
});

await test("F014 上传 401：抛 ApiError、触发全局 401 处理器、不重试；describeImportError 明确文案", async () => {
  respond = () =>
    jsonResponse(401, {
      error: { code: "AUTH_REQUIRED", message: "未认证或会话已过期", details: {} },
    });
  const err = await expectApiError(validateResourceImport(importCsvFile(), "csv"));
  assert.equal(err.status, 401);
  assert.equal(handlerCalls, 1);
  assert.equal(calls.length, 1);
  const described = describeImportError(err);
  assert.ok(described.message.includes("重新登录"));
  assert.equal(described.validationFailed, null);
});

await test("F014 403 FORBIDDEN（permission / csrf）：明确文案（隐藏不替代服务端校验）", async () => {
  respond = () =>
    jsonResponse(403, {
      error: { code: "FORBIDDEN", message: "Forbidden", details: { reason: "permission" } },
    });
  const permission = describeImportError(
    await expectApiError(validateResourceImport(importCsvFile(), "csv")),
  );
  assert.ok(permission.message.includes("导入权限"));
  assert.equal(handlerCalls, 0);

  respond = () =>
    jsonResponse(403, {
      error: { code: "FORBIDDEN", message: "Forbidden", details: { reason: "csrf" } },
    });
  const csrf = describeImportError(
    await expectApiError(importResources(importCsvFile(), "csv")),
  );
  assert.ok(csrf.message.includes("csrf"));
});

await test("F014 413 IMPORT_FILE_TOO_LARGE / IMPORT_ROW_LIMIT_EXCEEDED：携带上限值、无部分导入语义", async () => {
  respond = () =>
    jsonResponse(413, {
      error: { code: "IMPORT_FILE_TOO_LARGE", message: "File too large", details: { limit_bytes: 5242880 } },
    });
  const fileErr = describeImportError(
    await expectApiError(validateResourceImport(importCsvFile(), "csv")),
  );
  assert.equal(fileErr.code, "IMPORT_FILE_TOO_LARGE");
  assert.equal(fileErr.limitBytes, 5242880);
  assert.ok(fileErr.message.includes("5242880"));
  assert.ok(fileErr.message.includes("未导入任何数据"));

  respond = () =>
    jsonResponse(413, {
      error: { code: "IMPORT_ROW_LIMIT_EXCEEDED", message: "Row limit exceeded", details: { limit_rows: 5000 } },
    });
  const rowErr = describeImportError(
    await expectApiError(importResources(importCsvFile(), "csv")),
  );
  assert.equal(rowErr.limitRows, 5000);
  assert.ok(rowErr.message.includes("5000"));
  assert.ok(rowErr.message.includes("未导入任何数据"));
});

await test("F014 422 IMPORT_INVALID_FILE：reason 映射与缺失 / 未定义列拼接", async () => {
  respond = () =>
    jsonResponse(422, {
      error: {
        code: "IMPORT_INVALID_FILE",
        message: "Invalid file",
        details: { reason: "missing_columns", missing_columns: ["cluster", "hostname"] },
      },
    });
  const missing = describeImportError(
    await expectApiError(validateResourceImport(importCsvFile(), "csv")),
  );
  assert.equal(missing.invalidFile.reason, "missing_columns");
  assert.deepEqual(missing.invalidFile.missingColumns, ["cluster", "hostname"]);
  assert.ok(missing.message.includes("缺失列"));
  assert.ok(missing.message.includes("cluster"));
  assert.ok(missing.message.includes("IMPORT_INVALID_FILE"));

  respond = () =>
    jsonResponse(422, {
      error: {
        code: "IMPORT_INVALID_FILE",
        message: "Invalid file",
        details: { reason: "unknown_columns", unknown_columns: ["rack"] },
      },
    });
  const unknown = describeImportError(
    await expectApiError(validateResourceImport(importCsvFile(), "csv")),
  );
  assert.deepEqual(unknown.invalidFile.unknownColumns, ["rack"]);
  assert.ok(unknown.message.includes("未定义列"));

  respond = () =>
    jsonResponse(422, {
      error: { code: "IMPORT_INVALID_FILE", message: "Invalid file", details: { reason: "unsupported_format" } },
    });
  const unsupported = describeImportError(
    await expectApiError(importResources(importCsvFile(), "xlsx")),
  );
  assert.equal(unsupported.invalidFile.reason, "unsupported_format");
  assert.ok(unsupported.message.includes(".xls"));

  respond = () =>
    jsonResponse(422, {
      error: { code: "IMPORT_INVALID_FILE", message: "Invalid file", details: { reason: "column_order" } },
    });
  const order = describeImportError(
    await expectApiError(validateResourceImport(importCsvFile(), "csv")),
  );
  assert.ok(order.message.includes("顺序"));
});

await test("F014 422 IMPORT_VALIDATION_FAILED：整批回滚语义 + 行错误明细（与预校验同形状）", async () => {
  respond = () =>
    jsonResponse(422, {
      error: {
        code: "IMPORT_VALIDATION_FAILED",
        message: "Import validation failed",
        details: {
          total_rows: 12,
          importable_rows: 10,
          error_count: 3,
          errors: [
            { row: 4, field: "cluster", reason: "cluster does not exist or is not selectable", related_row: null },
            { row: 7, field: "hostname", reason: "duplicate hostname within file (also at row 2)", related_row: 2 },
          ],
          errors_truncated: true,
        },
      },
    });
  const err = await expectApiError(importResources(importCsvFile(), "csv"));
  const described = describeImportError(err);
  assert.equal(described.code, "IMPORT_VALIDATION_FAILED");
  assert.ok(described.validationFailed !== null, "应解析出行错误明细");
  assert.equal(described.validationFailed.total_rows, 12);
  assert.equal(described.validationFailed.importable_rows, 10);
  assert.equal(described.validationFailed.error_count, 3);
  assert.equal(described.validationFailed.errors.length, 2);
  assert.equal(described.validationFailed.errors[1].related_row, 2);
  assert.equal(described.validationFailed.errors_truncated, true);
  // 无部分成功语义：文案明确整批回滚、未创建任何资源
  assert.ok(described.message.includes("整批失败"));
  assert.ok(described.message.includes("回滚"));
  assert.ok(described.message.includes("未创建任何资源"));
});

await test("F014 422 IMPORT_VALIDATION_FAILED details 形状不符：不伪造行错误明细", async () => {
  respond = () =>
    jsonResponse(422, {
      error: { code: "IMPORT_VALIDATION_FAILED", message: "Import validation failed", details: {} },
    });
  const err = await expectApiError(importResources(importCsvFile(), "csv"));
  const described = describeImportError(err);
  assert.equal(described.validationFailed, null);
  assert.ok(described.message.includes("整批失败"));
  assert.ok(described.message.includes("回滚"));
});

await test("F014 422 VALIDATION_ERROR field=format：字段级错误（供表单 format 输入呈现）", async () => {
  respond = () =>
    jsonResponse(422, {
      error: {
        code: "VALIDATION_ERROR",
        message: "Validation error",
        details: { fields: [{ field: "format", message: "format 必须为 csv 或 xlsx" }] },
      },
    });
  const err = await expectApiError(validateResourceImport(importCsvFile(), "csv"));
  const described = describeImportError(err);
  assert.equal(described.fields.format, "format 必须为 csv 或 xlsx");
  assert.equal(described.validationFailed, null);
});

await test("F014 500 / 网络层错误：兑底文案，不伪装成空结果、不重试", async () => {
  respond = () =>
    jsonResponse(500, { error: { code: "INTERNAL_ERROR", message: "内部错误", details: {} } });
  const err = await expectApiError(validateResourceImport(importCsvFile(), "csv"));
  const described = describeImportError(err);
  assert.equal(described.code, "INTERNAL_ERROR");
  assert.ok(described.message.includes("内部错误"));
  assert.equal(described.validationFailed, null);
  assert.equal(calls.length, 1); // 500 不重试

  respond = () => Promise.reject(new TypeError("Failed to fetch"));
  await assert.rejects(validateResourceImport(importCsvFile(), "csv"), TypeError);
  assert.equal(calls.length, 2); // 网络层失败也不重发（每次恰好一次调用）
  const networkDescribed = describeImportError(new TypeError("Failed to fetch"));
  assert.ok(networkDescribed.message.includes("无法连接服务器"));
});

await test("F014 parseImportFormValues：空输入不发请求（file 未选 → 本地错误）；非法 format 防御", async () => {
  const empty = parseImportFormValues(emptyImportFormValues());
  assert.equal(empty.ok, false);
  assert.ok(empty.errors.file.includes("选择"), "未选文件应本地报错（不发起请求）");

  // format 下拉恒合法；防御自由输入的非法值（服务端同样 422 field="format"）
  const badFormat = parseImportFormValues({ format: "xls", file: importCsvFile() });
  assert.equal(badFormat.ok, false);
  assert.ok(badFormat.errors.format);

  // 合法最小输入通过（csv 不限扩展名）
  const ok = parseImportFormValues({ format: "csv", file: importCsvFile("resources") });
  assert.equal(ok.ok, true);
});

await test("F014 parseImportFormValues：xlsx 仅接受 .xlsx（.xls 拒绝、大小写不敏感）", async () => {
  const xls = parseImportFormValues({ format: "xlsx", file: new File(["x"], "resources.xls") });
  assert.equal(xls.ok, false);
  assert.ok(xls.errors.file.includes(".xlsx"));

  const upper = parseImportFormValues({ format: "xlsx", file: new File(["x"], "Resources.XLSX") });
  assert.equal(upper.ok, true);
});

await test("F014 parseImportFormValues：文件大小超上限本地拦截（§10 签核值 5,242,880 字节）", async () => {
  const big = new File(["x"], "big.csv");
  Object.defineProperty(big, "size", { value: IMPORT_MAX_FILE_BYTES + 1 });
  const tooBig = parseImportFormValues({ format: "csv", file: big });
  assert.equal(tooBig.ok, false);
  assert.ok(tooBig.errors.file.includes("5242880"));
  assert.ok(tooBig.errors.file.includes("IMPORT_FILE_TOO_LARGE"));

  // 恰好等于上限：本地通过（服务端拦 > 上限；> 为严格比较）
  const exact = new File(["x"], "exact.csv");
  Object.defineProperty(exact, "size", { value: IMPORT_MAX_FILE_BYTES });
  assert.equal(parseImportFormValues({ format: "csv", file: exact }).ok, true);
});

await test("F014 importTargetKey：format/文件名/大小/修改时间指纹，变化即失效", async () => {
  const fileA = new File(["a,b\n"], "a.csv");
  const fileB = new File(["a,b\n"], "a.csv", { lastModified: 12345 });
  const keyA = importTargetKey({ format: "csv", file: fileA });
  assert.ok(keyA !== null);
  assert.equal(keyA, importTargetKey({ format: "csv", file: fileA }));
  assert.notEqual(keyA, importTargetKey({ format: "xlsx", file: fileA }));
  assert.notEqual(keyA, importTargetKey({ format: "csv", file: fileB }));
  assert.equal(importTargetKey({ format: "csv", file: null }), null);
});

await test("F014 importFormFieldFromPath：422 点路径 → 表单键（format 直通；未知 → null）", async () => {
  assert.equal(importFormFieldFromPath("format"), "format");
  assert.equal(importFormFieldFromPath("file"), null); // file 由 multipart 形状承载，非 422 字段
  assert.equal(importFormFieldFromPath("format.x"), null);
  assert.equal(importFormFieldFromPath(""), null);
});

await test("F014 模板渲染辅助：类型·单位/枚举标签、必填标签、表头行 CSV 生成（DR-208）", async () => {
  const template = {
    resource_type: "BARE_METAL",
    columns: [
      { name: "cluster", required: true, target: "resource.cluster", type: "string", unit: null, enum: null, description: "d", example: "N96P" },
      { name: "memory_mb", required: false, target: "hardware.memory_mb", type: "integer", unit: "MiB", enum: null, description: "d", example: "262144" },
      { name: "role", required: false, target: "resource.role", type: "enum", unit: null, enum: ["COMPUTE", "LOGIN", "OTHER"], description: "d", example: "COMPUTE" },
    ],
  };
  assert.equal(templateColumnTypeLabel(template.columns[0]), "string");
  assert.equal(templateColumnTypeLabel(template.columns[1]), "integer · MiB");
  assert.equal(templateColumnTypeLabel(template.columns[2]), "enum（COMPUTE | LOGIN | OTHER）");
  assert.equal(templateColumnRequiredLabel(template.columns[0]), "必填");
  assert.ok(templateColumnRequiredLabel(template.columns[1]).includes("省略"));
  // 表头行：列名按冻结顺序拼接（.xlsx 模板使用相同表头，§6.3）
  assert.equal(buildTemplateCsv(template), "cluster,memory_mb,role\n");
});

// ---------------------------------------------------------------------------
// F015：Audit 查询 / 已删对象 / 账号管理（Contract：docs/api/F015.md v1）
// ---------------------------------------------------------------------------

const AUDIT_ROW_FIXTURE = {
  id: "a0000000-0000-0000-0000-00000000000f",
  action: "UPDATE",
  object_type: "resource",
  object_id: "0b9f4c6b-8f82-4b7a-9b95-a1e93b1f0004",
  operator_user_id: null,
  operator_username: "bootstrap",
  before_data: { status: "IDLE" },
  after_data: { status: "DOWN" },
  created_at: "2026-10-06T12:00:00+00:00",
};

await test("F015 listAudit 默认：GET /api/v1/audit，无查询串", async () => {
  respond = () => jsonResponse(200, { items: [], page: 1, page_size: 20, total: 0 });
  const data = await listAudit();
  assert.equal(data.total, 0);
  assert.equal(calls.length, 1);
  assert.equal(calls[0].url, "/api/v1/audit");
  assert.equal(calls[0].init.method, "GET");
  assert.equal(calls[0].init.credentials, "include");
});

await test("F015 listAudit 组合查询：operator/object_type/object_id/action/created_from/created_to/分页/排序（AND 组合）", async () => {
  respond = () => jsonResponse(200, { items: [], page: 2, page_size: 50, total: 0 });
  await listAudit({
    operator: "user01",
    object_type: "resource",
    object_id: "0b9f4c6b-8f82-4b7a-9b95-a1e93b1f0004",
    action: "UPDATE",
    created_from: "2026-10-01T00:00:00Z",
    created_to: "2026-10-06T23:59:59Z",
    page: 2,
    page_size: 50,
    sort: "created_at",
    order: "asc",
  });
  assert.equal(calls.length, 1);
  assert.equal(
    calls[0].url,
    "/api/v1/audit?operator=user01&object_type=resource" +
      "&object_id=0b9f4c6b-8f82-4b7a-9b95-a1e93b1f0004&action=UPDATE" +
      "&created_from=2026-10-01T00%3A00%3A00Z&created_to=2026-10-06T23%3A59%3A59Z" +
      "&page=2&page_size=50&sort=created_at&order=asc",
  );
});

await test("F015 listAudit 空串过滤项不发（operator=''/object_id=''/created_from=''）", async () => {
  respond = () => jsonResponse(200, { items: [], page: 1, page_size: 20, total: 0 });
  await listAudit({ operator: "", object_id: "", created_from: "", created_to: "" });
  assert.equal(calls[0].url, "/api/v1/audit");
});

await test("F015 listAudit 响应解析：AuditRow 字段（operator_user_id/before_data 可 null；不含密码/令牌）", async () => {
  respond = () =>
    jsonResponse(200, {
      items: [AUDIT_ROW_FIXTURE],
      page: 1,
      page_size: 20,
      total: 137,
    });
  const data = await listAudit();
  assert.equal(data.total, 137);
  assert.equal(data.items.length, 1);
  const row = data.items[0];
  assert.equal(row.id, AUDIT_ROW_FIXTURE.id);
  assert.equal(row.action, "UPDATE");
  assert.equal(row.object_type, "resource");
  assert.equal(row.operator_user_id, null);
  assert.equal(row.operator_username, "bootstrap");
  assert.deepEqual(row.before_data, { status: "IDLE" });
  assert.deepEqual(row.after_data, { status: "DOWN" });
  assert.ok(!("password" in row) && !("token" in row));
});

await test("F015 describeAuditQueryError：401/403/422（fields）/网络层兑底", async () => {
  respond = () =>
    jsonResponse(401, {
      error: { code: "AUTH_REQUIRED", message: "未认证或会话已过期", details: {} },
    });
  const unauthorized = await expectApiError(listAudit());
  const unauthorizedDescribed = describeAuditQueryError(unauthorized);
  assert.equal(unauthorizedDescribed.code, "AUTH_REQUIRED");
  assert.ok(unauthorizedDescribed.message.includes("未认证"));
  assert.equal(handlerCalls, 1); // 401 先触发全局处理器（回登录页）再呈现

  respond = () =>
    jsonResponse(403, {
      error: {
        code: "FORBIDDEN",
        message: "没有权限",
        details: { reason: "permission", permission: "AUDIT_READ" },
      },
    });
  const forbidden = await expectApiError(listAudit());
  const forbiddenDescribed = describeAuditQueryError(forbidden);
  assert.ok(forbiddenDescribed.message.includes("AUDIT_READ"));
  assert.ok(forbiddenDescribed.message.includes("FORBIDDEN"));

  respond = () =>
    jsonResponse(422, {
      error: {
        code: "VALIDATION_ERROR",
        message: "请求参数校验失败",
        details: {
          fields: [
            { field: "object_id", message: "须与 object_type 同现" },
            { field: "created_to", message: "不能早于 created_from" },
          ],
        },
      },
    });
  const invalid = await expectApiError(listAudit());
  const invalidDescribed = describeAuditQueryError(invalid);
  assert.equal(invalidDescribed.fields.object_id, "须与 object_type 同现");
  assert.equal(invalidDescribed.fields.created_to, "不能早于 created_from");
  assert.ok(invalidDescribed.message.includes("VALIDATION_ERROR"));

  const networkDescribed = describeAuditQueryError(new TypeError("Failed to fetch"));
  assert.ok(networkDescribed.message.includes("无法连接服务器"));
});

const DELETED_ITEM_FIXTURES = [
  {
    object_type: "network",
    object_id: "d0000000-0000-0000-0000-000000000001",
    version: 3,
    label: "mgmt",
    cluster: {
      id: "c0000000-0000-0000-0000-000000000001",
      code: "N96P",
      name: "N96 生产集群",
    },
    deleted_at: "2026-10-05T08:30:00+00:00",
  },
  {
    object_type: "cluster",
    object_id: "d0000000-0000-0000-0000-000000000002",
    version: 2,
    label: "N96P",
    cluster: null,
    deleted_at: "2026-10-04T09:00:00+00:00",
  },
];

await test("F015 listDeleted 默认：GET /api/v1/deleted，无查询串", async () => {
  respond = () => jsonResponse(200, { items: [], page: 1, page_size: 20, total: 0 });
  const data = await listDeleted();
  assert.equal(data.total, 0);
  assert.equal(calls.length, 1);
  assert.equal(calls[0].url, "/api/v1/deleted");
  assert.equal(calls[0].init.method, "GET");
  assert.equal(calls[0].init.credentials, "include");
});

await test("F015 listDeleted 组合查询：object_type/page/page_size/sort=deleted_at/order", async () => {
  respond = () => jsonResponse(200, { items: [], page: 3, page_size: 100, total: 0 });
  await listDeleted({ object_type: "ip_pool", page: 3, page_size: 100, sort: "deleted_at", order: "asc" });
  assert.equal(calls.length, 1);
  assert.equal(
    calls[0].url,
    "/api/v1/deleted?object_type=ip_pool&page=3&page_size=100&sort=deleted_at&order=asc",
  );
});

await test("F015 listDeleted 响应解析：DeletedItem（label/version/cluster 可 null；不返回删除操作者）", async () => {
  respond = () =>
    jsonResponse(200, {
      items: DELETED_ITEM_FIXTURES,
      page: 1,
      page_size: 20,
      total: 6,
    });
  const data = await listDeleted();
  assert.equal(data.total, 6);
  assert.equal(data.items.length, 2);
  const [networkItem, clusterItem] = data.items;
  assert.equal(networkItem.object_type, "network");
  assert.equal(networkItem.label, "mgmt");
  assert.equal(networkItem.version, 3);
  assert.equal(networkItem.cluster.code, "N96P");
  assert.equal(networkItem.deleted_at, "2026-10-05T08:30:00+00:00");
  assert.equal(clusterItem.cluster, null); // cluster 类型自身无归属 cluster
  assert.equal(clusterItem.label, "N96P"); // cluster 的 label=code（§3.2 口径）
  assert.ok(!("operator" in networkItem) && !("deleted_by" in networkItem)); // O-7：不返回删除操作者
});

await test("F015 restoreDeletedItem 路由表：按 object_type 调各域既有 restore（POST + version Query，§5）", async () => {
  respond = () => jsonResponse(200, {}); // 各域响应信封形状各异，调用方只关心成败
  const id = "0b9f4c6b-8f82-4b7a-9b95-a1e93b1f0004";
  const version = 7;
  const expectedPaths = {
    cluster: "/clusters",
    resource: "/resources",
    interface: "/interfaces",
    network: "/networks",
    ip_pool: "/ip-pools",
    ip_address: "/ip-addresses",
    service: "/services",
    service_endpoint: "/service-endpoints",
  };
  for (const [objectType, path] of Object.entries(expectedPaths)) {
    await restoreDeletedItem(objectType, id, version);
  }
  assert.equal(calls.length, 8);
  let index = 0;
  for (const [objectType, path] of Object.entries(expectedPaths)) {
    assert.equal(
      calls[index].url,
      `/api/v1${path}/${id}/restore?version=${version}`,
      `object_type=${objectType} 应路由到 ${path}`,
    );
    assert.equal(calls[index].init.method, "POST");
    assert.equal(calls[index].init.credentials, "include");
    index += 1;
  }
});

await test("F015 describeDeletedActionError：409 reason 逐类映射 + VERSION_CONFLICT + 403 + 网络层；不重试", async () => {
  respond = () =>
    jsonResponse(409, {
      error: {
        code: "CONFLICT",
        message: "Conflict",
        details: { reason: "unique_conflict", field: "name" },
      },
    });
  const unique = await expectApiError(
    restoreDeletedItem("network", "d0000000-0000-0000-0000-000000000001", 3),
  );
  const uniqueDescribed = describeDeletedActionError(unique);
  assert.ok(uniqueDescribed.message.includes("已被新的未删除对象占用"));
  assert.ok(uniqueDescribed.message.includes("unique_conflict"));
  assert.ok(uniqueDescribed.message.includes("不会被覆盖"));

  respond = () =>
    jsonResponse(409, {
      error: {
        code: "CONFLICT",
        message: "Conflict",
        details: { reason: "dependency_deleted", conflicts: [] },
      },
    });
  const dependency = await expectApiError(
    restoreDeletedItem("service", "d0000000-0000-0000-0000-000000000003", 5),
  );
  const dependencyDescribed = describeDeletedActionError(dependency);
  assert.ok(dependencyDescribed.message.includes("依赖"));
  assert.ok(dependencyDescribed.message.includes("dependency_deleted"));

  respond = () =>
    jsonResponse(409, {
      error: {
        code: "CONFLICT",
        message: "Conflict",
        details: { reason: "not_deleted" },
      },
    });
  const notDeleted = await expectApiError(
    restoreDeletedItem("ip_pool", "d0000000-0000-0000-0000-000000000004", 2),
  );
  const notDeletedDescribed = describeDeletedActionError(notDeleted);
  assert.ok(notDeletedDescribed.message.includes("未处于已删除状态"));

  respond = () =>
    jsonResponse(409, {
      error: {
        code: "VERSION_CONFLICT",
        message: "数据已被他人修改",
        details: { current_version: 9 },
      },
    });
  const versionConflict = await expectApiError(
    restoreDeletedItem("cluster", "d0000000-0000-0000-0000-000000000002", 8),
  );
  const versionDescribed = describeDeletedActionError(versionConflict);
  assert.equal(versionDescribed.versionConflict, true);
  assert.equal(versionDescribed.currentVersion, 9);
  assert.ok(versionDescribed.message.includes("不会自动重试"));

  respond = () =>
    jsonResponse(403, {
      error: { code: "FORBIDDEN", message: "没有权限", details: { reason: "permission" } },
    });
  const forbidden = await expectApiError(
    restoreDeletedItem("resource", "d0000000-0000-0000-0000-000000000005", 4),
  );
  const forbiddenDescribed = describeDeletedActionError(forbidden);
  assert.ok(forbiddenDescribed.message.includes("RESTORE"));

  const networkDescribed = describeDeletedActionError(new TypeError("Failed to fetch"));
  assert.ok(networkDescribed.message.includes("无法连接服务器"));
  assert.equal(calls.length, 5); // 每次恰好一次调用，不重试
});

const USER_ROW_FIXTURE = {
  id: "u0000000-0000-0000-0000-000000000001",
  username: "user01",
  role: "EDITOR",
  status: "ACTIVE",
  version: 3,
  created_at: "2026-09-01T08:00:00+00:00",
  updated_at: "2026-10-06T09:00:00+00:00",
};

await test("F015 listUsers 默认：GET /api/v1/users，无查询串", async () => {
  respond = () => jsonResponse(200, { items: [], page: 1, page_size: 20, total: 0 });
  const data = await listUsers();
  assert.equal(data.total, 0);
  assert.equal(calls.length, 1);
  assert.equal(calls[0].url, "/api/v1/users");
  assert.equal(calls[0].init.method, "GET");
  assert.equal(calls[0].init.credentials, "include");
});

await test("F015 listUsers 组合查询：role/status/q/分页/排序（AND 组合）", async () => {
  respond = () => jsonResponse(200, { items: [], page: 2, page_size: 50, total: 0 });
  await listUsers({
    role: "EDITOR",
    status: "ACTIVE",
    q: "user",
    page: 2,
    page_size: 50,
    sort: "username",
    order: "asc",
  });
  assert.equal(calls.length, 1);
  assert.equal(
    calls[0].url,
    "/api/v1/users?role=EDITOR&status=ACTIVE&q=user&page=2&page_size=50&sort=username&order=asc",
  );
});

await test("F015 listUsers 空串 q 不发；响应不含 password_hash", async () => {
  respond = () =>
    jsonResponse(200, {
      items: [USER_ROW_FIXTURE],
      page: 1,
      page_size: 20,
      total: 1,
    });
  const data = await listUsers({ q: "" });
  assert.equal(calls[0].url, "/api/v1/users");
  assert.equal(data.items[0].username, "user01");
  assert.equal(data.items[0].version, 3);
  assert.ok(!("password_hash" in data.items[0])); // UserRow 永不含 password_hash
  assert.ok(!("password" in data.items[0]));
});

await test("F015 createUser：POST /users + body 恰含 username/password/role；201 解析 {user}", async () => {
  respond = () => jsonResponse(201, { user: USER_ROW_FIXTURE });
  const { user } = await createUser({
    username: "user01",
    password: "initial-password",
    role: "EDITOR",
  });
  assert.equal(user.id, USER_ROW_FIXTURE.id);
  assert.equal(user.username, "user01");
  assert.equal(calls.length, 1);
  assert.equal(calls[0].url, "/api/v1/users");
  assert.equal(calls[0].init.method, "POST");
  assert.equal(calls[0].init.headers["Content-Type"], "application/json");
  // body 恰含三字段：无 id/version/status 等只读字段（出现即 422，§4.3）
  assert.deepEqual(JSON.parse(calls[0].init.body), {
    username: "user01",
    password: "initial-password",
    role: "EDITOR",
  });
});

await test("F015 getUser：GET /users/{id}；404 NOT_FOUND 描述", async () => {
  respond = () => jsonResponse(200, { user: USER_ROW_FIXTURE });
  const { user } = await getUser(USER_ROW_FIXTURE.id);
  assert.equal(user.username, "user01");
  assert.equal(calls[0].url, `/api/v1/users/${USER_ROW_FIXTURE.id}`);
  assert.equal(calls[0].init.method, "GET");

  respond = () =>
    jsonResponse(404, {
      error: { code: "NOT_FOUND", message: "账号不存在", details: {} },
    });
  const err = await expectApiError(getUser("u0000000-0000-0000-0000-000000000009"));
  const described = describeUserActionError(err);
  assert.ok(described.message.includes("账号不存在"));
});

await test("F015 updateUser：PATCH /users/{id} 且仅携带变化字段（version + role 或 status；省略 = 不重置）", async () => {
  respond = () => jsonResponse(200, { user: { ...USER_ROW_FIXTURE, role: "ADMIN", version: 4 } });
  const { user } = await updateUser(USER_ROW_FIXTURE.id, { version: 3, role: "ADMIN" });
  assert.equal(user.version, 4);
  assert.equal(calls[0].url, `/api/v1/users/${USER_ROW_FIXTURE.id}`);
  assert.equal(calls[0].init.method, "PATCH");
  assert.deepEqual(JSON.parse(calls[0].init.body), { version: 3, role: "ADMIN" });

  respond = () => jsonResponse(200, { user: { ...USER_ROW_FIXTURE, status: "DISABLED", version: 4 } });
  await updateUser(USER_ROW_FIXTURE.id, { version: 3, status: "DISABLED" });
  assert.deepEqual(JSON.parse(calls[1].init.body), { version: 3, status: "DISABLED" });
  // username/password_hash 不可出现（§4.4）：本 client 类型不提供该形态
});

await test("F015 describeUserActionError：409 unique_conflict → username 字段级；VERSION_CONFLICT → 刷新后重改；422/403；不重试", async () => {
  respond = () =>
    jsonResponse(409, {
      error: {
        code: "CONFLICT",
        message: "Conflict",
        details: { reason: "unique_conflict", field: "username" },
      },
    });
  const unique = await expectApiError(
    createUser({ username: "user01", password: "initial-password", role: "VIEWER" }),
  );
  const uniqueDescribed = describeUserActionError(unique);
  assert.ok(uniqueDescribed.fields.username.includes("冲突"));
  assert.ok(uniqueDescribed.message.includes("username"));

  respond = () =>
    jsonResponse(409, {
      error: {
        code: "VERSION_CONFLICT",
        message: "数据已被他人修改",
        details: { current_version: 8 },
      },
    });
  const versionConflict = await expectApiError(
    updateUser(USER_ROW_FIXTURE.id, { version: 3, status: "DISABLED" }),
  );
  const versionDescribed = describeUserActionError(versionConflict);
  assert.equal(versionDescribed.versionConflict, true);
  assert.equal(versionDescribed.currentVersion, 8);
  assert.ok(versionDescribed.message.includes("不会自动重试"));

  respond = () =>
    jsonResponse(422, {
      error: {
        code: "VALIDATION_ERROR",
        message: "请求参数校验失败",
        details: {
          fields: [
            { field: "password", message: "长度须为 8–128" },
            { field: "role", message: "role/status 至少一个" },
          ],
        },
      },
    });
  const invalid = await expectApiError(
    createUser({ username: "user02", password: "short", role: "VIEWER" }),
  );
  const invalidDescribed = describeUserActionError(invalid);
  assert.equal(invalidDescribed.fields.password, "长度须为 8–128");
  assert.equal(invalidDescribed.fields.role, "role/status 至少一个");

  respond = () =>
    jsonResponse(403, {
      error: { code: "FORBIDDEN", message: "没有权限", details: { reason: "permission" } },
    });
  const forbidden = await expectApiError(listUsers());
  const forbiddenDescribed = describeUserActionError(forbidden);
  assert.ok(forbiddenDescribed.message.includes("USER_ADMIN"));

  const networkDescribed = describeUserActionError(new TypeError("Failed to fetch"));
  assert.ok(networkDescribed.message.includes("无法连接服务器"));
  assert.equal(calls.length, 4); // 每次恰好一次调用，不重试
});

await test("F015 parseIso8601UtcInput：datetime-local → ISO-8601 UTC（秒省略补 00；空 = 未提供）", async () => {
  assert.deepEqual(parseIso8601UtcInput(""), { ok: true, value: null });
  assert.deepEqual(parseIso8601UtcInput("   "), { ok: true, value: null });
  assert.deepEqual(parseIso8601UtcInput("2026-10-06T12:00"), {
    ok: true,
    value: "2026-10-06T12:00:00Z",
  });
  assert.deepEqual(parseIso8601UtcInput(" 2026-10-06T12:00:31 "), {
    ok: true,
    value: "2026-10-06T12:00:31Z",
  });
  // 格式 / 分量 / 日历非法
  assert.equal(parseIso8601UtcInput("2026-10-06").ok, false);
  assert.equal(parseIso8601UtcInput("2026-10-06T25:00").ok, false);
  assert.equal(parseIso8601UtcInput("2026-13-01T00:00").ok, false);
  assert.equal(parseIso8601UtcInput("2026-02-30T00:00").ok, false);
  assert.equal(parseIso8601UtcInput("not-a-date").ok, false);
});

await test("F015 parseAuditQueryFormValues：合法值（operator trim / object_id UUID / 时间归一；空 = 未提供）", async () => {
  const parsed = parseAuditQueryFormValues({
    ...emptyAuditQueryFormValues(),
    operator: "  user01  ",
    objectType: "resource",
    objectId: " 0b9f4c6b-8f82-4b7a-9b95-a1e93b1f0004 ",
    action: "UPDATE",
    createdFrom: "2026-10-01T00:00",
    createdTo: "2026-10-06T23:59:59",
  });
  assert.equal(parsed.ok, true);
  assert.equal(parsed.fields.operator, "user01");
  assert.equal(parsed.fields.objectType, "resource");
  assert.equal(parsed.fields.objectId, "0b9f4c6b-8f82-4b7a-9b95-a1e93b1f0004");
  assert.equal(parsed.fields.action, "UPDATE");
  assert.equal(parsed.fields.createdFrom, "2026-10-01T00:00:00Z");
  assert.equal(parsed.fields.createdTo, "2026-10-06T23:59:59Z");

  // 全空：未提供任何过滤（均 null）
  const empty = parseAuditQueryFormValues(emptyAuditQueryFormValues());
  assert.equal(empty.ok, true);
  assert.equal(empty.fields.operator, null);
  assert.equal(empty.fields.objectType, null);
  assert.equal(empty.fields.objectId, null);
  assert.equal(empty.fields.action, null);
  assert.equal(empty.fields.createdFrom, null);
  assert.equal(empty.fields.createdTo, null);
});

await test("F015 parseAuditQueryFormValues：object_id 须与 object_type 同现（单独提供 → 本地错误；object_type 单独 → 合法）", async () => {
  const objectIdOnly = parseAuditQueryFormValues({
    ...emptyAuditQueryFormValues(),
    objectId: "0b9f4c6b-8f82-4b7a-9b95-a1e93b1f0004",
  });
  assert.equal(objectIdOnly.ok, false);
  assert.ok(objectIdOnly.errors.objectId.includes("同现"));

  const objectTypeOnly = parseAuditQueryFormValues({
    ...emptyAuditQueryFormValues(),
    objectType: "cluster",
  });
  assert.equal(objectTypeOnly.ok, true);
  assert.equal(objectTypeOnly.fields.objectType, "cluster");
  assert.equal(objectTypeOnly.fields.objectId, null);
});

await test("F015 parseAuditQueryFormValues：非法输入本地拦截（operator>64 / object_id 非 UUID / 时间非法 / from>to）", async () => {
  const longOperator = parseAuditQueryFormValues({
    ...emptyAuditQueryFormValues(),
    operator: "a".repeat(65),
  });
  assert.equal(longOperator.ok, false);
  assert.ok(longOperator.errors.operator.includes("64"));

  // 恰好 64：合法（服务端 >64 才 422）
  const exactOperator = parseAuditQueryFormValues({
    ...emptyAuditQueryFormValues(),
    operator: "a".repeat(64),
  });
  assert.equal(exactOperator.ok, true);

  const badUuid = parseAuditQueryFormValues({
    ...emptyAuditQueryFormValues(),
    objectType: "resource",
    objectId: "not-a-uuid",
  });
  assert.equal(badUuid.ok, false);
  assert.ok(badUuid.errors.objectId.includes("UUID"));

  const badTime = parseAuditQueryFormValues({
    ...emptyAuditQueryFormValues(),
    createdFrom: "2026-02-30T00:00",
  });
  assert.equal(badTime.ok, false);
  assert.ok(badTime.errors.createdFrom !== undefined);

  const reversed = parseAuditQueryFormValues({
    ...emptyAuditQueryFormValues(),
    createdFrom: "2026-10-06T12:00",
    createdTo: "2026-10-01T00:00",
  });
  assert.equal(reversed.ok, false);
  assert.ok(reversed.errors.createdTo.includes("不能晚于"));

  // 闭区间：from == to 合法（含边界）
  const sameBoundary = parseAuditQueryFormValues({
    ...emptyAuditQueryFormValues(),
    createdFrom: "2026-10-06T12:00",
    createdTo: "2026-10-06T12:00:00",
  });
  assert.equal(sameBoundary.ok, true);
});

await test("F015 buildAuditQuery：过滤项省略不发（null → 不携带）；分页/sort/order 恒携带", async () => {
  const query = buildAuditQuery(
    {
      operator: null,
      objectType: null,
      objectId: null,
      action: null,
      createdFrom: null,
      createdTo: null,
    },
    1,
    20,
    "desc",
  );
  assert.deepEqual(query, { page: 1, page_size: 20, sort: "created_at", order: "desc" });

  const full = buildAuditQuery(
    {
      operator: "user01",
      objectType: "user",
      objectId: "0b9f4c6b-8f82-4b7a-9b95-a1e93b1f0004",
      action: "CREATE",
      createdFrom: "2026-10-01T00:00:00Z",
      createdTo: "2026-10-06T23:59:59Z",
    },
    2,
    50,
    "asc",
  );
  assert.deepEqual(full, {
    operator: "user01",
    object_type: "user",
    object_id: "0b9f4c6b-8f82-4b7a-9b95-a1e93b1f0004",
    action: "CREATE",
    created_from: "2026-10-01T00:00:00Z",
    created_to: "2026-10-06T23:59:59Z",
    page: 2,
    page_size: 50,
    sort: "created_at",
    order: "asc",
  });
});

await test("F015 auditQueryFieldFromPath：422 参数名（snake）→ 表单键（camel）；分页/排序/未知 → null", async () => {
  assert.equal(auditQueryFieldFromPath("operator"), "operator");
  assert.equal(auditQueryFieldFromPath("object_type"), "objectType");
  assert.equal(auditQueryFieldFromPath("object_id"), "objectId");
  assert.equal(auditQueryFieldFromPath("action"), "action");
  assert.equal(auditQueryFieldFromPath("created_from"), "createdFrom");
  assert.equal(auditQueryFieldFromPath("created_to"), "createdTo");
  // 分页 / 排序参数无对应过滤表单控件：不强行映射（页面在通用错误区呈现）
  assert.equal(auditQueryFieldFromPath("page"), null);
  assert.equal(auditQueryFieldFromPath("page_size"), null);
  assert.equal(auditQueryFieldFromPath("sort"), null);
  assert.equal(auditQueryFieldFromPath("order"), null);
  // 未知路径 / 嵌套路径 → null
  assert.equal(auditQueryFieldFromPath("unknown"), null);
  assert.equal(auditQueryFieldFromPath("object_id.x"), "objectId"); // 顶层直通
});

// 还原全局状态
setUnauthorizedHandler(null);
globalThis.fetch = originalFetch;

console.log(`\n${passed} passed, ${failed} failed`);
process.exit(failed > 0 ? 1 : 0);
