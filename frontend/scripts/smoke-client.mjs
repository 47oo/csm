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
 * 运行：npm run smoke:client（Node ≥ 22.18 内置 TypeScript type stripping，
 * 直接加载 src/api/client.ts，无需新增测试框架；仅替换 globalThis.fetch 为受控响应）。
 */
import assert from "node:assert/strict";
import {
  getHealth,
  isApiError,
  request,
  setUnauthorizedHandler,
} from "../src/api/client.ts";

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

// 还原全局状态
setUnauthorizedHandler(null);
globalThis.fetch = originalFetch;

console.log(`\n${passed} passed, ${failed} failed`);
process.exit(failed > 0 ? 1 : 0);
