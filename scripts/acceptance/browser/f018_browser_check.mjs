// F018 test-only headless-browser acceptance harness.
//
// Verifies the runtime-rendered DOM criteria (F018 AC-3/4/5/6/7/8/9/10) against
// the REAL deployed stack (entry Nginx -> FastAPI -> PostgreSQL) at F018_BASE_URL.
// It does NOT touch frontend/src, api, smoke-client.mjs, production deps or Git
// state. It only observes real API-backed pages; the single route interception is
// a *delay* of a real response used to observe the Loading state, data is never
// rewritten. Every criterion that cannot be observed is reported as NOT TESTED.
//
// Usage (env):
//   F018_BASE_URL=http://localhost:18080
//   F018_ADMIN_USERNAME / F018_ADMIN_PASSWORD   bootstrap ADMIN
//   F018_OUT_DIR   evidence directory (screenshots + JSON)
//   F018_CHROME_EXE  path to chrome-headless-shell (playwright-core executablePath)
//
// Exit code 0 = every executed check PASSed (unexecuted items are recorded as
// NOT TESTED in the JSON, never silently counted as PASS).

import fs from "node:fs";
import path from "node:path";
import { execSync } from "node:child_process";
import { chromium, request } from "playwright-core";

const BASE = (process.env.F018_BASE_URL || "http://localhost:18080").replace(/\/+$/, "");
const OUT = process.env.F018_OUT_DIR || "/tmp/f018-browser";
const ADMIN_USER = process.env.F018_ADMIN_USERNAME || "admin";
const ADMIN_PW = process.env.F018_ADMIN_PASSWORD || "";
const CHROME_EXE = process.env.F018_CHROME_EXE || "";
const BACKEND_CONTAINER = process.env.F018_BACKEND_CONTAINER || "";

const SHOTS = path.join(OUT, "shots");
fs.mkdirSync(SHOTS, { recursive: true });

const results = [];
const notTested = [];

function assert(cond, msg) {
  if (!cond) throw new Error(msg);
}

async function check(name, fn) {
  try {
    const detail = await fn();
    results.push({ name, status: "PASS", detail: detail ?? null });
    console.log(`[PASS] ${name}`);
  } catch (err) {
    results.push({ name, status: "FAIL", error: String((err && err.message) || err) });
    console.log(`[FAIL] ${name}: ${(err && err.message) || err}`);
  }
}

function markNotTested(name, reason) {
  notTested.push({ name, status: "NOT TESTED", reason });
  console.log(`[NOT TESTED] ${name}: ${reason}`);
}

async function shot(page, name) {
  try {
    await page.screenshot({ path: path.join(SHOTS, `${name}.png`), fullPage: true });
  } catch {
    /* screenshot best-effort */
  }
}

async function login(username, password, role) {
  const ctx = await request.newContext({
    baseURL: BASE,
    extraHTTPHeaders: { Origin: BASE },
    timeout: 60000,
  });
  const resp = await ctx.post("/api/v1/auth/login", {
    data: { username, password },
  });
  assert(resp.status() === 200, `${role} login failed: ${resp.status()} ${await resp.text()}`);
  return ctx;
}

const runId = Math.random().toString(36).slice(2, 8);
const viewerUser = `f018viewer-${runId}`;
const viewerPw = "f018-viewer-pass1";
const clusterCode = `F18C-${runId}`;
const hostname = `f18-${runId}`;

const adminApi = await login(ADMIN_USER, ADMIN_PW, "ADMIN");

// --- seed minimal real data + a no-permission user (real HTTP) ---------------
const createdUsers = [];
const createUser = async (username, password, role) => {
  const resp = await adminApi.post("/api/v1/users", {
    data: { username, password, role },
  });
  assert(resp.status() === 201, `create ${role} user ${username}: ${resp.status()} ${await resp.text()}`);
  createdUsers.push(username);
};
await createUser(viewerUser, viewerPw, "VIEWER");

const clusterResp = await adminApi.post("/api/v1/clusters", {
  data: { code: clusterCode, name: `F018 acceptance ${runId}` },
});
assert(clusterResp.status() === 201, `create cluster: ${clusterResp.status()} ${await clusterResp.text()}`);

const resResp = await adminApi.post("/api/v1/resources", {
  data: { cluster: clusterCode, hostname, resource_type: "BARE_METAL" },
});
assert(resResp.status() === 201, `create resource: ${resResp.status()} ${await resResp.text()}`);

const viewerCookies = (await (await login(viewerUser, viewerPw, "VIEWER")).storageState()).cookies;
const adminCookies = (await adminApi.storageState()).cookies;

const browser = await chromium.launch({
  executablePath: CHROME_EXE,
  args: ["--no-sandbox", "--disable-dev-shm-usage"],
});

async function newPage(cookies) {
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
  if (cookies) await ctx.addCookies(cookies);
  return { ctx, page: await ctx.newPage() };
}

const openHome = async (page) => {
  await page.goto(`${BASE}/`, { waitUntil: "load" });
  await page.waitForSelector(".ant-menu", { timeout: 20000 });
};
const navTo = async (page, label) => {
  await page.locator(".ant-menu-item", { hasText: label }).first().click();
};

// ============================ AC-3 =========================================
await check("AC-3 layer order", async () => {
  const { ctx, page } = await newPage(adminCookies);
  await openHome(page);
  const info = await page.evaluate(() => {
    const ordered = [];
    const blocks = [];
    for (const sheet of Array.from(document.styleSheets)) {
      let rules;
      try {
        rules = sheet.cssRules;
      } catch {
        continue;
      }
      for (const rule of Array.from(rules)) {
        if (rule.constructor.name === "CSSLayerStatementRule") {
          ordered.push(...rule.nameList);
        }
        if (rule.constructor.name === "CSSLayerBlockRule") {
          ordered.push(rule.name);
          blocks.push({ name: rule.name, hasAntdBtn: /\.ant-btn/.test(rule.cssText) });
        }
      }
    }
    return { ordered, blocks };
  });
  fs.writeFileSync(path.join(OUT, "layer-order.json"), JSON.stringify(info, null, 2));
  const unique = [...new Set(info.ordered)];
  // Tailwind v4 may emit an internal `properties` layer first; the D04-7
  // ordering that matters is the relative order of the five shared layers.
  const expected = ["theme", "base", "antd", "components", "utilities"];
  const idx = expected.map((n) => unique.indexOf(n));
  assert(idx.every((i) => i >= 0), `missing layer(s): ${JSON.stringify(unique)}`);
  assert(idx.every((v, i) => i === 0 || v > idx[i - 1]), `layer order mismatch: ${JSON.stringify(unique)}`);
  assert(!unique.includes("legacy"), "legacy layer present");
  await shot(page, "ac3-layer-order");
  await ctx.close();
  return { order: unique, blocks: info.blocks.map((b) => b.name) };
});

await check("AC-3 antd style effective", async () => {
  const { ctx, page } = await newPage(adminCookies);
  await openHome(page);
  const antdBtnInLayer = await page.evaluate(() => {
    for (const sheet of Array.from(document.styleSheets)) {
      let rules;
      try {
        rules = sheet.cssRules;
      } catch {
        continue;
      }
      for (const rule of Array.from(rules)) {
        if (rule.constructor.name === "CSSLayerBlockRule" && rule.name === "antd") {
          if (/\.ant-btn/.test(rule.cssText)) return true;
        }
      }
    }
    return false;
  });
  const logout = page.locator("header .ant-btn").first();
  const cs = await logout.evaluate((el) => {
    const s = getComputedStyle(el);
    return {
      borderRadius: s.borderRadius,
      paddingLeft: s.paddingLeft,
      background: s.backgroundColor,
      classList: el.className,
    };
  });
  fs.writeFileSync(path.join(OUT, "computed-style.json"), JSON.stringify({ antdBtnInLayer, logout: cs }, null, 2));
  assert(antdBtnInLayer, ".ant-btn not found inside @layer antd");
  assert(/\bant-btn\b/.test(cs.classList), `logout button not an antd button: ${cs.classList}`);
  await ctx.close();
  return { antdBtnInLayer, logout: cs };
});

await check("AC-3 utility overrides antd", async () => {
  const { ctx, page } = await newPage(adminCookies);
  await openHome(page);
  const probe = await page.evaluate(() => {
    const el = document.createElement("button");
    el.className = "ant-btn ant-btn-default px-0";
    el.textContent = "probe";
    document.body.appendChild(el);
    const s = getComputedStyle(el);
    return { paddingLeft: s.paddingLeft, paddingRight: s.paddingRight };
  });
  fs.writeFileSync(path.join(OUT, "utility-override.json"), JSON.stringify(probe, null, 2));
  assert(probe.paddingLeft === "0px", `utilities did not override antd padding: ${probe.paddingLeft}`);
  await ctx.close();
  return probe;
});

await check("AC-3 preflight did not break layout", async () => {
  const { ctx, page } = await newPage(adminCookies);
  await openHome(page);
  const pre = await page.evaluate(() => {
    const body = getComputedStyle(document.body);
    const h1 = document.querySelector("h1");
    const h1s = h1 ? getComputedStyle(h1) : null;
    return {
      bodyMargin: body.margin,
      bodyBoxSizing: body.boxSizing,
      h1Margin: h1s ? `${h1s.marginTop} ${h1s.marginRight} ${h1s.marginBottom} ${h1s.marginLeft}` : null,
    };
  });
  fs.writeFileSync(path.join(OUT, "preflight.json"), JSON.stringify(pre, null, 2));
  assert(pre.bodyMargin === "0px", `preflight body margin not reset: ${pre.bodyMargin}`);
  assert(pre.bodyBoxSizing === "border-box", `preflight box-sizing not applied: ${pre.bodyBoxSizing}`);
  await ctx.close();
  return pre;
});

// ============================ AC-4 =========================================
await check("AC-4 viewer nav gate (hidden + no reach)", async () => {
  const meResp = await (await login(viewerUser, viewerPw, "VIEWER")).get("/api/v1/auth/me");
  const me = await meResp.json();
  assert(!me.user.permissions.includes("AUDIT_READ"), "viewer unexpectedly has AUDIT_READ");
  assert(!me.user.permissions.includes("USER_ADMIN"), "viewer unexpectedly has USER_ADMIN");
  assert(!me.user.permissions.includes("VIEW_DELETED"), "viewer unexpectedly has VIEW_DELETED");

  const { ctx, page } = await newPage(viewerCookies);
  await openHome(page);
  const labels = await page.$$eval(".ant-menu-item", (els) => els.map((e) => e.textContent.trim()));
  await shot(page, "ac4-viewer-nav");
  assert(!labels.includes("Audit"), `viewer nav reveals Audit: ${JSON.stringify(labels)}`);
  assert(!labels.includes("System"), `viewer nav reveals System: ${JSON.stringify(labels)}`);
  // No client-side route exists: a direct /audit URL just reloads the app shell (not Audit).
  await page.goto(`${BASE}/audit`, { waitUntil: "load" });
  await page.waitForSelector(".ant-menu", { timeout: 20000 });
  const direct = await page.$$eval(".ant-menu-item", (els) => els.map((e) => e.textContent.trim()));
  const bodyText = await page.textContent("body");
  assert(!direct.includes("Audit"), "direct /audit URL reached Audit nav");
  assert(!bodyText.includes("完整审计查询"), "direct /audit URL rendered Audit panel");
  await ctx.close();
  return { permissions: me.user.permissions, nav: labels, directNav: direct };
});

await check("AC-4 admin nav visible", async () => {
  const { ctx, page } = await newPage(adminCookies);
  await openHome(page);
  const labels = await page.$$eval(".ant-menu-item", (els) => els.map((e) => e.textContent.trim()));
  await shot(page, "ac4-admin-nav");
  assert(labels.includes("Audit"), `admin nav missing Audit: ${JSON.stringify(labels)}`);
  assert(labels.includes("System"), `admin nav missing System: ${JSON.stringify(labels)}`);
  await ctx.close();
  return { nav: labels };
});

// ============================ AC-7 =========================================
await check("AC-7 audit page has no write controls", async () => {
  const { ctx, page } = await newPage(adminCookies);
  await openHome(page);
  await navTo(page, "Audit");
  await page.waitForSelector("text=完整审计查询", { timeout: 20000 });
  await page.waitForTimeout(500);
  const dump = await page.evaluate(() => {
    const controls = Array.from(document.querySelectorAll("button, a, [role='button']"));
    const btns = controls.map((b) => b.textContent.trim()).filter(Boolean);
    const norm = btns.map((t) => t.replace(/\s+/g, ""));
    return { btns, normalized: norm };
  });
  await shot(page, "ac7-audit-page");
  fs.writeFileSync(path.join(OUT, "audit-controls.json"), JSON.stringify(dump, null, 2));
  assert(
    !dump.normalized.some((t) => /删除|清空|修改/.test(t)),
    `audit page exposes a write control: ${JSON.stringify(dump.btns)}`,
  );
  assert(
    dump.normalized.some((t) => /查询|筛选/.test(t)),
    `audit page has no query control: ${JSON.stringify(dump.btns)}`,
  );
  await ctx.close();
  return dump;
});

// ============================ AC-8 =========================================
await check("AC-8 filter param 'type' + sort param 'resource_type'", async () => {
  const { ctx, page } = await newPage(adminCookies);
  const urls = [];
  page.on("request", (r) => {
    if (r.url().includes("/api/v1/resources?")) urls.push(r.url());
  });
  await openHome(page);
  await navTo(page, "Resources");
  await page.waitForSelector("#resource-filter-q", { timeout: 20000 });
  await page.waitForTimeout(800);

  // filter: type -> param must be `type`
  await page.locator(".ant-select:has(#resource-filter-type) .ant-select-selector").first().click();
  await page.click(".ant-select-item-option[title='BARE_METAL（物理机）']");
  await page.getByRole("button", { name: /筛\s*选/ }).click();
  await page.waitForTimeout(800);
  const filterUrl = urls[urls.length - 1] || "";
  assert(/[?&]type=BARE_METAL(&|$)/.test(filterUrl), `filter did not send type=BARE_METAL: ${filterUrl}`);
  assert(!/[?&]resource_type=BARE_METAL(&|$)/.test(filterUrl), `filter wrongly used resource_type: ${filterUrl}`);

  // sort: click header "类型" -> param must be `sort=resource_type`
  await page.locator("thead th button", { hasText: "类型" }).first().click();
  await page.waitForTimeout(800);
  const sortUrl = urls[urls.length - 1] || "";
  assert(/[?&]sort=resource_type(&|$)/.test(sortUrl), `sort did not send sort=resource_type: ${sortUrl}`);
  fs.writeFileSync(path.join(OUT, "network-params.json"), JSON.stringify({ filterUrl, sortUrl, all: urls }, null, 2));
  await shot(page, "ac8-resources-params");
  await ctx.close();
  return { filterUrl, sortUrl };
});

// ============================ AC-10 ========================================
await check("AC-10 clusters column alignment", async () => {
  const { ctx, page } = await newPage(adminCookies);
  await openHome(page);
  await navTo(page, "Clusters");
  await page.waitForSelector(".ant-table-thead th", { timeout: 20000 });
  await page.waitForSelector(".ant-table-tbody tr.ant-table-row td", { timeout: 20000 });
  const align = await page.evaluate(() => {
    const heads = Array.from(document.querySelectorAll(".ant-table-thead th")).map((e) => ({
      text: e.textContent.trim(),
      left: Math.round(e.getBoundingClientRect().left),
    }));
    const firstRow = document.querySelector(".ant-table-tbody tr.ant-table-row");
    const cells = firstRow
      ? Array.from(firstRow.querySelectorAll("td")).map((e) => Math.round(e.getBoundingClientRect().left))
      : [];
    const equal = heads.length === cells.length && heads.every((h, i) => Math.abs(h.left - cells[i]) <= 2);
    return { heads, cells, equal };
  });
  fs.writeFileSync(path.join(OUT, "clusters-columns.json"), JSON.stringify(align, null, 2));
  await shot(page, "ac10-clusters");
  assert(align.heads.length > 0, "no cluster table headers rendered");
  assert(align.equal, `column misalignment: ${JSON.stringify(align)}`);
  await ctx.close();
  return align;
});

// ============================ AC-5 =========================================
await check("AC-5 loading state (real response delayed)", async () => {
  const { ctx, page } = await newPage(adminCookies);
  await openHome(page);
  await page.route("**/api/v1/clusters*", async (route) => {
    await new Promise((r) => setTimeout(r, 800));
    await route.continue();
  });
  await navTo(page, "Clusters");
  const loading = await page
    .waitForSelector("text=正在加载集群列表", { timeout: 5000 })
    .then(() => true)
    .catch(() => false);
  await shot(page, "ac5-loading");
  await page.unroute("**/api/v1/clusters*");
  await ctx.close();
  assert(loading, "loading state text did not appear");
  return { loading };
});

await check("AC-5 success state (real rows)", async () => {
  const { ctx, page } = await newPage(adminCookies);
  await openHome(page);
  await navTo(page, "Clusters");
  await page.waitForSelector(".ant-table-tbody tr.ant-table-row td", { timeout: 20000 });
  const rows = await page.$$eval(".ant-table-tbody tr.ant-table-row", (els) => els.length);
  const bodyText = await page.textContent(".ant-table-tbody");
  await shot(page, "ac5-success");
  await ctx.close();
  assert(rows > 0, "no rows in success state");
  assert(bodyText.includes(clusterCode), `seeded cluster ${clusterCode} not shown`);
  return { rows, containsSeeded: true };
});

await check("AC-5 empty state (real filter, zero hit)", async () => {
  const { ctx, page } = await newPage(adminCookies);
  await openHome(page);
  await navTo(page, "Clusters");
  await page.waitForSelector("#cluster-filter-q", { timeout: 20000 });
  await page.fill("#cluster-filter-q", "zzz-no-such-cluster-xyz");
  await page.getByRole("button", { name: /筛\s*选/ }).click();
  await page.waitForSelector(".ant-empty", { timeout: 20000 });
  const txt = await page.textContent(".ant-empty");
  await shot(page, "ac5-empty");
  await ctx.close();
  assert(/没有符合条件的集群/.test(txt), `empty message missing: ${txt}`);
  return { empty: txt.trim() };
});

// Real "backend unreachable" error is an AC-5-sanctioned Error trigger.
await check("AC-5 error state (real backend down)", async () => {
  assert(BACKEND_CONTAINER, "F018_BACKEND_CONTAINER not set; cannot trigger real backend-down error");
  const { ctx, page } = await newPage(adminCookies);
  await openHome(page);
  await navTo(page, "Clusters");
  await page.waitForSelector(".ant-table-tbody tr.ant-table-row td", { timeout: 20000 });
  execSync(`docker kill ${BACKEND_CONTAINER}`, { stdio: "ignore" });
  for (let i = 0; i < 30; i += 1) {
    try {
      const r = await fetch(`${BASE}/api/v1/health/ready`);
      if (r.status !== 200) break;
    } catch {
      break; // connection refused -> backend is down
    }
    await new Promise((r) => setTimeout(r, 500));
  }
  try {
    await page.getByRole("button", { name: /筛\s*选/ }).click(); // real request now fails
    await page.waitForSelector(".ant-alert-error", { timeout: 20000 });
    const txt = (await page.textContent(".ant-alert-error")) || "";
    await shot(page, "ac5-error");
    assert(/加载集群列表失败/.test(txt), `error alert missing: ${txt}`);
    return { errorText: txt.trim() };
  } finally {
    execSync(`docker start ${BACKEND_CONTAINER}`, { stdio: "ignore" });
    for (let i = 0; i < 90; i += 1) {
      try {
        const r = await fetch(`${BASE}/api/v1/health/ready`);
        if (r.status === 200) break;
      } catch {
        /* still starting */
      }
      await new Promise((r) => setTimeout(r, 1000));
    }
    await ctx.close();
  }
});
// ============================ AC-6 =========================================
await check("AC-6 401 -> global return to login page", async () => {
  const { ctx, page } = await newPage(adminCookies);
  await openHome(page);
  await ctx.clearCookies();
  await navTo(page, "Clusters"); // triggers authenticated request -> 401
  const loginVisible = await page
    .waitForSelector("input[autocomplete='username']", { timeout: 10000 })
    .then(() => true)
    .catch(() => false);
  await shot(page, "ac6-401-relogin");
  await ctx.close();
  assert(loginVisible, "401 did not return to login page");
  return { loginVisible };
});

await check("AC-6 403/409/422 real HTTP semantics (same origin)", async () => {
  const out = {};
  // 403: VIEWER tries an ADMIN-only endpoint (users list)
  const viewerApi = await login(viewerUser, viewerPw, "VIEWER");
  const r403 = await viewerApi.get("/api/v1/users");
  out["403"] = { status: r403.status(), body: await r403.json().catch(() => null) };
  // 422: invalid resource create body
  const r422 = await adminApi.post("/api/v1/resources", { data: { hostname: "" } });
  out["422"] = { status: r422.status(), body: await r422.json().catch(() => null) };
  // 409: stale version PATCH on the seeded resource
  const list = await adminApi.get(`/api/v1/resources?q=${hostname}`);
  const items = (await list.json()).items;
  const resource = items.find((r) => r.hostname === hostname);
  const r409 = await adminApi.patch(`/api/v1/resources/${resource.id}`, {
    data: { version: 999, status: "IDLE" },
  });
  out["409"] = { status: r409.status(), body: await r409.json().catch(() => null) };
  fs.writeFileSync(path.join(OUT, "http-error-semantics.json"), JSON.stringify(out, null, 2));
  assert(out["403"].status === 403, `expected 403 got ${out["403"].status}`);
  assert(out["422"].status === 422, `expected 422 got ${out["422"].status}`);
  assert(out["409"].status === 409, `expected 409 got ${out["409"].status}`);
  assert(/VERSION_CONFLICT/.test(JSON.stringify(out["409"].body)), "409 body missing VERSION_CONFLICT");
  return out;
});

await check("AC-6 409 VERSION_CONFLICT presentation (DOM)", async () => {
  const { ctx, page } = await newPage(adminCookies);
  await openHome(page);
  await navTo(page, "Resources");
  await page.waitForSelector(".ant-table-tbody tr.ant-table-row td", { timeout: 20000 });
  await page
    .locator(".ant-table-tbody tr.ant-table-row", { hasText: hostname })
    .getByRole("button", { name: /查\s*看/ })
    .first()
    .click();
  await page.getByRole("button", { name: /编\s*辑/ }).first().click();
  await page.waitForSelector("#resource-description", { timeout: 20000 });
  await page.fill("#resource-description", "f018 stale edit");
  // Bump the version over the REAL API so the browser's form is now stale.
  const list = await adminApi.get(`/api/v1/resources?q=${hostname}`);
  const res = (await list.json()).items.find((r) => r.hostname === hostname);
  const bumped = await adminApi.patch(`/api/v1/resources/${res.id}`, {
    data: { version: res.version, description: "bumped by f018 harness" },
  });
  assert(bumped.status() === 200, `version bump failed: ${bumped.status()}`);
  await page.getByRole("button", { name: /保存修改/ }).click();
  await page.waitForSelector(".ant-alert-error", { timeout: 20000 });
  const txt = (await page.textContent(".ant-alert-error")) || "";
  await shot(page, "ac6-409-version-conflict");
  await ctx.close();
  assert(/已被其他人修改/.test(txt), `409 VERSION_CONFLICT UI message missing: ${txt}`);
  return { message: txt.trim().slice(0, 200) };
});

await check("AC-6 422 validation presentation (DOM)", async () => {
  const { ctx, page } = await newPage(adminCookies);
  await openHome(page);
  await navTo(page, "Resources");
  await page.waitForSelector("#resource-filter-q, .ant-btn", { timeout: 20000 });
  await page.getByRole("button", { name: /新建资源/ }).first().click();
  await page.waitForSelector("#resource-hostname", { timeout: 20000 });
  // pick the seeded cluster from the create form's cluster Select
  await page.locator(".ant-select:has(#resource-cluster) .ant-select-selector").first().click();
  await page.click(`.ant-select-item-option[title*='F18C-${runId}']`);
  // hostname with an internal space passes local validation (only empty is checked)
  // but the server rejects it -> real 422 field error rendered in the form.
  await page.fill("#resource-hostname", "bad host f018");
  await page.getByRole("button", { name: /创\s*建/ }).first().click();
  await page.waitForSelector(".ant-alert-error", { timeout: 20000 });
  const txt = (await page.textContent(".ant-alert-error")) || "";
  await shot(page, "ac6-422-validation");
  await ctx.close();
  assert(/VALIDATION_ERROR|\u6821\u9a8c|hostname/.test(txt), `422 UI message missing: ${txt}`);
  return { message: txt.trim().slice(0, 200) };
});

await check("AC-6 403 FORBIDDEN presentation (DOM)", async () => {
  const editorUser = `f018editor-${runId}`;
  const editorPw = "f018-editor-pass1";
  await createUser(editorUser, editorPw, "EDITOR");
  const editorCookies2 = (await (await login(editorUser, editorPw, "EDITOR")).storageState()).cookies;
  const { ctx, page } = await newPage(editorCookies2);
  await openHome(page);
  await navTo(page, "Resources");
  await page.waitForSelector(".ant-table-tbody tr.ant-table-row td", { timeout: 20000 });
  await page
    .locator(".ant-table-tbody tr.ant-table-row", { hasText: hostname })
    .getByRole("button", { name: /查\s*看/ })
    .first()
    .click();
  await page.getByRole("button", { name: /编\s*辑/ }).first().click();
  await page.waitForSelector("#resource-description", { timeout: 20000 });
  await page.fill("#resource-description", "f018 forbidden edit");
  // Demote the session's role to VIEWER over the REAL API (takes effect immediately),
  // so the editor's submit hits a genuine server-side 403 FORBIDDEN.
  const ulist = await adminApi.get(`/api/v1/users?q=${editorUser}`);
  const editorRow = (await ulist.json()).items.find((u) => u.username === editorUser);
  const demote = await adminApi.patch(`/api/v1/users/${editorRow.id}`, {
    data: { version: editorRow.version, role: "VIEWER" },
  });
  assert(demote.status() === 200, `role demotion failed: ${demote.status()}`);
  await page.getByRole("button", { name: /保存修改/ }).click();
  await page.waitForSelector(".ant-alert-error", { timeout: 20000 });
  const txt = (await page.textContent(".ant-alert-error")) || "";
  await shot(page, "ac6-403-forbidden");
  await ctx.close();
  assert(/没有权限|FORBIDDEN/.test(txt), `403 UI message missing: ${txt}`);
  return { message: txt.trim().slice(0, 200) };
});

// ============================ AC-9 =========================================
await check("AC-9 key pages render against real API data", async () => {
  const { ctx, page } = await newPage(adminCookies);
  await openHome(page);
  const seen = {};
  await navTo(page, "Clusters");
  await page.waitForSelector(".ant-table-tbody tr.ant-table-row td", { timeout: 20000 });
  seen.clusters = (await page.$$eval(".ant-table-tbody tr.ant-table-row", (e) => e.length)) > 0;
  await navTo(page, "Resources");
  await page.waitForSelector(".ant-table-tbody tr.ant-table-row td", { timeout: 20000 });
  seen.resources = (await page.$$eval(".ant-table-tbody tr.ant-table-row", (e) => e.length)) > 0;
  await navTo(page, "Audit");
  await page.waitForSelector("text=完整审计查询", { timeout: 20000 });
  seen.audit = true;
  await shot(page, "ac9-pages");
  await ctx.close();
  assert(seen.clusters && seen.resources && seen.audit, `pages not rendered: ${JSON.stringify(seen)}`);
  return seen;
});

// ============================ teardown =====================================
for (const u of createdUsers) {
  // best-effort: deactivate seeded users to keep the acceptance DB tidy
  try {
    const list = await adminApi.get(`/api/v1/users?q=${u}`);
    const items = (await list.json()).items || [];
    for (const it of items) {
      if (it.username === u) {
        await adminApi.patch(`/api/v1/users/${it.id}`, { data: { version: it.version, status: "DISABLED" } });
      }
    }
  } catch {
    /* best-effort cleanup */
  }
}
await browser.close();
await adminApi.dispose();

const summary = {
  base: BASE,
  executed: results.length,
  passed: results.filter((r) => r.status === "PASS").length,
  failed: results.filter((r) => r.status === "FAIL").length,
  notTested: notTested.length,
  results,
  notTestedItems: notTested,
};
fs.writeFileSync(path.join(OUT, "browser-summary.json"), JSON.stringify(summary, null, 2));
console.log(`\nF018 browser summary: ${summary.passed}/${summary.executed} PASS, ${summary.failed} FAIL, ${summary.notTested} NOT TESTED`);
process.exit(summary.failed === 0 ? 0 : 1);