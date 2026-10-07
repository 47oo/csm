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

// 还原全局状态
setUnauthorizedHandler(null);
globalThis.fetch = originalFetch;

console.log(`\n${passed} passed, ${failed} failed`);
process.exit(failed > 0 ? 1 : 0);
