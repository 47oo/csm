/**
 * 交互族 ⑤：危险操作取消 / 一次性提交（F020；F043-C12–C13）。
 *
 * 层：P（confirmDialogState.ts 的守卫状态机）+ R（请求层：确认恰 1 次、取消 0 次）。
 * ConfirmDialog.tsx 的接线（maskClosable / keyboard / 禁用取消）由
 * tsxBoundary.static.mjs 的 C14 静态结构断言覆盖（architecture §5 X1）。
 */
import assert from "node:assert/strict";

import { deleteCluster } from "../../src/api/clusters.ts";
import { createConfirmCommitGuard } from "../../src/components/confirmDialogState.ts";

const CLUSTER_ID = "3f0f2b8e-1c4d-4a5b-9c8d-7e6f5a4b3c2d";

export default async function register(h) {
  await h.test("C12 危险操作确认正例：tryBegin()===true → calls.length===1；第二次 tryBegin()===false → 仍 1", async () => {
    h.setRespond(() => new Response(null, { status: 204 }));
    const guard = createConfirmCommitGuard();

    const onSubmit = async () => {
      if (!guard.tryBegin()) {
        return; // confirmLoading 回落前的重复派发：忽略（不派发请求）
      }
      await deleteCluster(CLUSTER_ID, 3);
    };

    assert.equal(guard.isInFlight(), false);
    await onSubmit();
    assert.equal(h.calls.length, 1);
    assert.equal(h.calls[0].init.method, "DELETE");
    assert.equal(h.calls[0].url, `/api/v1/clusters/${CLUSTER_ID}?version=3`);
    assert.equal(guard.isInFlight(), true);

    await onSubmit(); // 双击 / 回车连发
    assert.equal(h.calls.length, 1);
    assert.equal(guard.isInFlight(), true);

    // 提交结束后可再次手动触发（不自动重试）
    guard.settle();
    await onSubmit();
    assert.equal(h.calls.length, 2);
  });

  await h.test("C13 危险操作取消负例：tryBegin()→reset() 后 isInFlight()===false 且 calls.length===0", async () => {
    h.setRespond(() => new Response(null, { status: 204 }));
    const guard = createConfirmCommitGuard();

    // 取消 / Esc / 遮罩关闭：只 reset，不派发提交
    const onCancel = () => {
      guard.reset();
    };
    const begin = guard.tryBegin();
    assert.equal(begin, true);
    onCancel();
    assert.equal(guard.isInFlight(), false);
    assert.equal(h.calls.length, 0);

    // 对话框重开后仍可提交（判据：reset 不是永久禁用）
    assert.equal(guard.tryBegin(), true);
    guard.reset();
    assert.equal(h.calls.length, 0);
  });
}
