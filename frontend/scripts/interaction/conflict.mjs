/**
 * 交互族 ③：409 版本冲突 → 刷新最新数据（F043-C06–C07）。
 *
 * 层：R（请求层：PATCH / GET 序列与 payload.version）。
 * 依据 src/api/clusters.ts：updateCluster / getCluster / describeClusterActionError
 * （VERSION_CONFLICT → versionConflict + currentVersion；不静默重试、不自动刷新）。
 */
import assert from "node:assert/strict";

import {
  describeClusterActionError,
  getCluster,
  updateCluster,
} from "../../src/api/clusters.ts";

const CLUSTER_ID = "3f0f2b8e-1c4d-4a5b-9c8d-7e6f5a4b3c2d";

function clusterFixture(version) {
  return {
    id: CLUSTER_ID,
    code: "N96P",
    name: "N96P 集群",
    status: "ACTIVE",
    description: null,
    metadata: {},
    version,
    created_at: "2026-10-29T00:00:00Z",
    updated_at: "2026-10-29T00:00:00Z",
    deleted_at: null,
  };
}

const VERSION_CONFLICT = {
  error: {
    code: "VERSION_CONFLICT",
    message: "数据已被他人修改",
    details: { current_version: 7 },
  },
};

export default async function register(h) {
  await h.test("C06 409 正例：versionConflict + currentVersion=7；刷新后 calls.length===3 且重提 body.version===7", async () => {
    h.setRespond((input, init) => {
      const body = init?.body === undefined ? null : JSON.parse(init.body);
      if (init?.method === "PATCH") {
        if (body.version === 6) {
          return h.jsonResponse(409, VERSION_CONFLICT);
        }
        return h.jsonResponse(200, { cluster: clusterFixture(body.version) });
      }
      return h.jsonResponse(200, { cluster: clusterFixture(7) });
    });

    // 1) 旧 version 提交 → 409
    const conflict = describeClusterActionError(
      await h.expectApiError(updateCluster(CLUSTER_ID, { version: 6, name: "改名" })),
    );
    assert.equal(conflict.versionConflict, true);
    assert.equal(conflict.currentVersion, 7);
    assert.equal(h.calls.length, 1); // 不静默重试、不自动刷新

    // 2) 用户「刷新最新数据」→ 取到 7
    const fresh = await getCluster(CLUSTER_ID);
    assert.equal(fresh.cluster.version, 7);
    assert.equal(h.calls.length, 2);

    // 3) 用新 version 重新提交 → 200，payload 携带 7
    await updateCluster(CLUSTER_ID, { version: fresh.cluster.version, name: "改名" });
    assert.equal(h.calls.length, 3);
    assert.equal(h.calls[2].init.method, "PATCH");
    assert.equal(JSON.parse(h.calls[2].init.body).version, 7);
  });

  await h.test("C07 409 负例：409 后 calls.length===1（无自动刷新）；旧 version 重提仍 409 且 handlerCalls===0", async () => {
    h.setRespond(() => h.jsonResponse(409, VERSION_CONFLICT));

    const first = describeClusterActionError(
      await h.expectApiError(updateCluster(CLUSTER_ID, { version: 5, name: "改名" })),
    );
    assert.equal(first.versionConflict, true);
    assert.equal(h.calls.length, 1);

    const second = describeClusterActionError(
      await h.expectApiError(updateCluster(CLUSTER_ID, { version: 5, name: "改名" })),
    );
    assert.equal(second.versionConflict, true);
    assert.equal(second.currentVersion, 7);
    assert.equal(h.calls.length, 2); // 只有两次显式提交，无自动刷新 / 重试
    assert.equal(h.calls[1].init.method, "PATCH");
    assert.equal(JSON.parse(h.calls[1].init.body).version, 5); // 旧 version 未被静默改写
    assert.equal(h.handlerCalls, 0); // 409 不触发 401 全局处理器
  });
}
