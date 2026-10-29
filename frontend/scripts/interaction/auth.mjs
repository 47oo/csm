/**
 * 交互族 ②：401（F043-C04–C05）。
 *
 * 层：R（请求层 / 全局处理器计数）。依据 src/api/client.ts：
 * 401 → 先触发全局处理器（handlerCalls +1）→ 抛 ApiError（不被吞）；
 * 任何失败都不自动重试（用户显式重试才发第 2 次）。
 */
import assert from "node:assert/strict";

import { getHealth, isApiError } from "../../src/api/client.ts";

const UNAUTHORIZED = {
  error: { code: "AUTH_REQUIRED", message: "登录已失效，请重新登录", details: {} },
};

export default async function register(h) {
  await h.test("C04 401 正例：首错 status=401/code=AUTH_REQUIRED 未被吞、处理器恰 1 次；用户显式重试后第 2 次 200", async () => {
    let attempt = 0;
    h.setRespond(() => {
      attempt += 1;
      if (attempt === 1) {
        return h.jsonResponse(401, UNAUTHORIZED);
      }
      return h.jsonResponse(200, { status: "ok", service: "csm-backend" });
    });

    const err = await h.expectApiError(getHealth());
    assert.equal(isApiError(err), true);
    assert.equal(err.status, 401);
    assert.equal(err.code, "AUTH_REQUIRED");
    assert.equal(h.handlerCalls, 1); // 处理器只清一次登录态
    assert.equal(h.calls.length, 1);

    // 用户显式「重试」：再发 1 次并成功（无自动重试）
    const health = await getHealth();
    assert.equal(health.status, "ok");
    assert.equal(h.calls.length, 2);
    assert.equal(h.handlerCalls, 1); // 第 2 次 200 不再触发
  });

  await h.test("C05 401 负例：单次 401 → calls.length===1（无自动重试）且 handlerCalls===1", async () => {
    h.setRespond(() => h.jsonResponse(401, UNAUTHORIZED));
    await h.expectApiError(getHealth());
    assert.equal(h.calls.length, 1);
    assert.equal(h.handlerCalls, 1);
  });
}
