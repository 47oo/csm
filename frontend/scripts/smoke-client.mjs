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

// 还原全局状态
setUnauthorizedHandler(null);
globalThis.fetch = originalFetch;

console.log(`\n${passed} passed, ${failed} failed`);
process.exit(failed > 0 ? 1 : 0);
