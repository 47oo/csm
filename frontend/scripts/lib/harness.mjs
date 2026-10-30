/**
 * 用例登记器 + fetch 桩原语（F043 architecture §3 / §4）。
 *
 * 从既有 scripts/smoke-client.mjs 抽出（首个「逐步拆分」步骤）：登记器打印体、
 * 计数清理时机、fetch 桩行为与抽取前**逐字节等价**，因此 352 个既有用例的
 * 断言与顺序均不受影响（A4 / A6）。`process.exit` 不在本模块（I-2）。
 *
 * 用法：
 *   const h = createHarness({ label: "" });            // smoke：label 为空串
 *   h.setRespond((input, init) => h.jsonResponse(200, body));
 *   await h.test("名", async () => { ... h.calls ... });
 *   h.restore();
 *
 * `resolveRespond` / `onTestStart` 供既有 smoke 复用其模块级 `respond` 变量与
 * `handlerCalls` 计数器（用例体零改动）；不传时用内部 `setRespond` 与内部计数
 * `countUnauthorized()` / `handlerCalls`。
 */
import assert from "node:assert/strict";

import { isApiError } from "../../src/api/client.ts";

/**
 * 创建登记器。
 * @param {object} [options]
 * @param {string} [options.label] 用例名前缀（smoke 为空串，交互 runner 用 "F043 "）
 * @param {() => Function|null} [options.resolveRespond] 取当前受控响应函数
 * @param {() => void} [options.onTestStart] 每个用例开始时的额外计数清理
 */
export function createHarness({ label = "", resolveRespond, onTestStart } = {}) {
  let respond = null;
  let handlerCount = 0;
  let passed = 0;
  let failed = 0;
  const calls = [];
  const originalFetch = globalThis.fetch;
  const getRespond = typeof resolveRespond === "function" ? resolveRespond : () => respond;

  globalThis.fetch = async (input, init) => {
    calls.push({ url: String(input), init });
    const current = getRespond();
    if (typeof current !== "function") {
      throw new Error("harness: 未设置受控响应（setRespond）");
    }
    return current(input, init);
  };

  return {
    /** 已记录的请求（`{url, init}`），用时实时增长；每个用例开始时清空。 */
    calls,
    /** 累计通过数。 */
    get passed() {
      return passed;
    },
    /** 累计失败数。 */
    get failed() {
      return failed;
    },
    /** 全局 401 处理器触发次数（本实例内部计数；每个用例开始时清零）。 */
    get handlerCalls() {
      return handlerCount;
    },
    /** 401 处理器回调内调用：本用例内的触发次数 +1。 */
    countUnauthorized() {
      handlerCount += 1;
    },
    /** 设置受控响应（`resolveRespond` 优先；smoke 自行维护模块级变量）。 */
    setRespond(next) {
      respond = next;
    },
    /** 受控 JSON 响应。 */
    jsonResponse(status, body) {
      return new Response(JSON.stringify(body), {
        status,
        headers: { "Content-Type": "application/json" },
      });
    },
    /** 断言 promise 抛出 ApiError 并返回该错误（与拆分前同一断言）。 */
    async expectApiError(promise) {
      try {
        await promise;
      } catch (err) {
        assert.ok(isApiError(err), `应为 ApiError，实际 ${err?.constructor?.name}`);
        return err;
      }
      throw new assert.AssertionError({ message: "应抛出 ApiError，实际 resolve" });
    },
    /** 运行一个用例（打印体与拆分前等价：`PASS: <label><name>`）。 */
    async test(name, fn) {
      calls.length = 0;
      handlerCount = 0;
      if (typeof onTestStart === "function") {
        onTestStart();
      }
      try {
        await fn();
        passed += 1;
        console.log(`PASS: ${label}${name}`);
      } catch (err) {
        failed += 1;
        console.error(`FAIL: ${label}${name}`);
        console.error(`  ${err?.stack ?? String(err)}`);
      }
    },
    /** 还原 globalThis.fetch（入口脚本收尾调用）。 */
    restore() {
      globalThis.fetch = originalFetch;
    },
  };
}
