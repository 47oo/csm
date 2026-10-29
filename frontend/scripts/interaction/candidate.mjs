/**
 * 交互族 ①：候选检索选中第 101 条（F041 / F043-C01–C03）。
 *
 * 层：P（纯逻辑：candidateSelectModel.ts）+ R（请求层：listResources 的 URL）。
 * 只读 `src/**` 的既有导出的纯逻辑与 client 行为，不触碰 `.tsx`。
 * 判定式见 docs/features/F043/architecture.md §6。
 */
import assert from "node:assert/strict";

import { listResources } from "../../src/api/resources.ts";
import {
  applyCandidateResponse,
  buildCandidateQuery,
  candidateOptions,
  candidateTruncation,
  candidateView,
  loadingCandidateState,
} from "../../src/components/candidateSelectModel.ts";

/** 造 100 条页内候选（id 为 UUID 形状，label 为 hostname）。 */
function pageItems() {
  return Array.from({ length: 100 }, (_unused, index) => ({
    id: `7c9e6679-7425-40de-944b-e07fc1f90a${String(index).padStart(2, "0")}`,
    label: `bm-node-${String(index).padStart(3, "0")}`,
  }));
}

export default async function register(h) {
  await h.test("C01 候选查询与截断：page=1/page_size=100/type=BARE_METAL/cluster_id/q；total=154 截断；第 101 位 id 恰一次且 label 不退化", async () => {
    const built = buildCandidateQuery("host", { clusterId: "c1", search: "  bm  " });
    assert.equal(built.domain, "host");
    const q = built.query;
    assert.equal(q.page, 1);
    assert.equal(q.page_size, 100);
    assert.equal(q.type, "BARE_METAL");
    assert.equal(q.cluster_id, "c1");
    assert.equal(q.q, "bm"); // 仅首尾 trim
    assert.equal(q.sort, "hostname");
    assert.equal(q.order, "asc");

    const items = pageItems();
    const state = applyCandidateResponse(loadingCandidateState(), 1, 1, {
      kind: "success",
      items,
      total: 154,
      pageSize: 100,
    });
    assert.equal(candidateView(state, "host").kind, "ready");

    const truncation = candidateTruncation(state, "host");
    assert.equal(truncation.truncated, true);
    assert.ok(truncation.text !== null);
    assert.ok(truncation.text.includes("154"), `截断文案应含总数 154：${truncation.text}`);
    assert.ok(truncation.text.includes("100"), `截断文案应含分页上限 100：${truncation.text}`);

    // 用户选中第 101 位对象（不在当前页）：候选中该 id 恰一次，label 不退化
    const pinned = { id: "d2f4c1b0-0000-4000-8000-000000000101", label: "bm-node-101" };
    const options = candidateOptions(state, pinned);
    assert.equal(options.length, 101);
    const pinnedHits = options.filter((option) => option.value === pinned.id);
    assert.equal(pinnedHits.length, 1);
    assert.equal(pinnedHits[0].label, "bm-node-101"); // 不退化为 id / 序号
    assert.equal(options[0].value, pinned.id);
    for (const item of items) {
      assert.equal(options.filter((option) => option.value === item.id).length, 1);
    }
  });

  await h.test("C02 候选取数：单次交互 calls.length===1 且 URL 含 page=1/page_size=100/type=BARE_METAL/cluster_id=c1", async () => {
    h.setRespond(() =>
      h.jsonResponse(200, { items: [], page: 1, page_size: 100, total: 0 }),
    );
    const built = buildCandidateQuery("host", { clusterId: "c1", search: "bm" });
    await listResources(built.query);
    assert.equal(h.calls.length, 1);
    const url = h.calls[0].url;
    assert.equal(url.startsWith("/api/v1/resources?"), true, url);
    for (const fragment of ["q=bm", "page=1", "page_size=100", "type=BARE_METAL", "cluster_id=c1"]) {
      assert.ok(url.includes(fragment), `URL 应含 ${fragment}：${url}`);
    }
  });

  await h.test("C03 候选取数负例：URL 不含 page>=2 / page_size>100 / include= / only= / deleted=", async () => {
    h.setRespond(() =>
      h.jsonResponse(200, { items: [], page: 1, page_size: 100, total: 0 }),
    );
    const built = buildCandidateQuery("host", { clusterId: "c1", search: "bm" });
    await listResources(built.query);
    assert.equal(h.calls.length, 1);
    const url = h.calls[0].url;
    const params = new URL(url, "http://csm.invalid").searchParams;
    const page = Number(params.get("page"));
    const pageSize = Number(params.get("page_size"));
    assert.equal(page, 1);
    assert.ok(page < 2, `page 不应 >=2：${page}`);
    assert.ok(pageSize <= 100, `page_size 不应 >100：${pageSize}`);
    for (const forbidden of ["include", "only", "deleted"]) {
      assert.equal(params.has(forbidden), false, `URL 不应含 ${forbidden}=：${url}`);
    }
    assert.equal(h.calls.length, 1); // 单次交互不循环翻页
  });
}
