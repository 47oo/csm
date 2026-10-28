/**
 * F034 — H-layer live evidence (TD-7 command 5).
 *
 * Uses the REAL frontend carrier primitives (`frontend/src/components/importCarrier.ts`,
 * loaded through Node's TypeScript type stripping — the same mechanism
 * `npm run smoke:client` uses) to build the multipart payload, and submits it to
 * the REAL deployed stack (`http://localhost:18080`, compose project `csmtest`,
 * nginx -> backend). This closes the "frontend artifact + real deployment"
 * half of the equivalence chain (TEST DESIGN TD-2 §3).
 *
 * Read-only: only `POST /api/v1/imports/{resources,resource-interfaces-ips}/validate`
 * (no writes) plus login and `GET /api/v1/clusters`. No business data is created
 * in the `csmtest` database.
 *
 * Usage:
 *   node docs/features/F034/artifacts/f034-live-validate.mjs
 *   CSM_BASE_URL=... CSM_USERNAME=... CSM_PASSWORD=... node ...   (CSM_PASSWORD required)
 *
 * Output: `docs/features/F034/artifacts/live-validate-results.json`
 *         `docs/features/F034/artifacts/logs/live-validate.log`
 */

import { readFileSync, readdirSync, writeFileSync, mkdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import {
  PASTED_CSV_FILE_NAME,
  PASTED_CSV_MIME_TYPE,
  isBlankImportText,
  pastedCsvFile,
  textImportTargetKey,
  utf8ByteLength,
} from "../../../../frontend/src/components/importCarrier.ts";

const HERE = dirname(fileURLToPath(import.meta.url));
const CORPUS = join(HERE, "corpus");
const BASE = process.env.CSM_BASE_URL ?? "http://localhost:18080";
const USERNAME = process.env.CSM_USERNAME ?? "admin";
// TEST credential only; never stored in the repo (`.env.test` is git-ignored).
const PASSWORD = process.env.CSM_PASSWORD ?? "";
if (!PASSWORD) {
  console.error("CSM_PASSWORD must be provided (TEST stack credential; do not commit it)");
  process.exit(2);
}
const ORIGIN = BASE;
const PASTED_MIME = PASTED_CSV_MIME_TYPE;
const FILE_MIME = "text/csv";
const FILE_NAME = "f034-live-file-carrier.csv";

const results = [];
const lines = [];
const log = (msg) => {
  lines.push(msg);
  console.log(msg);
};

let failures = 0;
function check(name, ok, detail = "") {
  if (!ok) failures += 1;
  log(`${ok ? "PASS" : "FAIL"} ${name}${detail ? ` — ${detail}` : ""}`);
  return ok;
}

// --- 1. carrier primitives (U layer, real frontend source) -------------------

log("== carrier primitives (frontend/src/components/importCarrier.ts) ==");
const samples = { ascii: "abc", chinese: "中文", emoji: "🚀", mixed: "a中🚀" };
for (const [name, value] of Object.entries(samples)) {
  const expected = new TextEncoder().encode(value).length;
  check(
    `utf8ByteLength(${name}) === TextEncoder bytes`,
    utf8ByteLength(value) === expected,
    `${utf8ByteLength(value)} vs ${expected} (String.length ${value.length})`,
  );
}
check(
  "utf8ByteLength differs from String.length for multi-byte text",
  utf8ByteLength("中".repeat(10)) === 30 && "中".repeat(10).length === 10,
);
check("isBlankImportText(\"\")", isBlankImportText("") === true);
check("isBlankImportText(\"   \")", isBlankImportText("   ") === true);
check("isBlankImportText(\"\\n\\n\")", isBlankImportText("\n\n") === true);
check("isBlankImportText(\" \\t\\r\\n \")", isBlankImportText(" \t\r\n ") === true);
check("isBlankImportText(csv) === false", isBlankImportText("a,b\n") === false);
check("textImportTargetKey changes on 1 char", textImportTargetKey("a,b\n") !== textImportTargetKey("a,c\n"));
check(
  "textImportTargetKey is carrier-tagged",
  textImportTargetKey("a,b\n").startsWith("text:csv:"),
  textImportTargetKey("a,b\n"),
);

// byte-exactness of the text carrier for every corpus fixture.
const fixtureNames = readdirSync(CORPUS)
  .filter((name) => name.endsWith(".txt"))
  .map((name) => name.replace(/\.txt$/, ""))
  .sort();
for (const name of fixtureNames) {
  const text = readFileSync(join(CORPUS, `${name}.txt`)).toString("utf8");
  const csv = readFileSync(join(CORPUS, `${name}.csv`));
  const file = pastedCsvFile(text);
  const carried = Buffer.from(await file.arrayBuffer());
  const ok =
    Buffer.compare(carried, csv) === 0 &&
    file.name === PASTED_CSV_FILE_NAME &&
    file.type === PASTED_MIME &&
    file.size === utf8ByteLength(text);
  check(`pastedCsvFile(${name}) reproduces corpus bytes`, ok, `${carried.length} bytes`);
}

// --- 2. login ---------------------------------------------------------------

log(`\n== live stack ${BASE} ==`);
const loginResp = await fetch(`${BASE}/api/v1/auth/login`, {
  method: "POST",
  headers: { "Content-Type": "application/json", Origin: ORIGIN },
  body: JSON.stringify({ username: USERNAME, password: PASSWORD }),
});
const cookie = (loginResp.headers.getSetCookie?.() ?? [])
  .map((value) => value.split(";")[0])
  .join("; ");
check("login 200", loginResp.status === 200, `status=${loginResp.status}`);
check("session cookie issued", cookie.length > 0, `cookie parts=${cookie.split("; ").length}`);

const clustersResp = await fetch(`${BASE}/api/v1/clusters`, { headers: { Cookie: cookie } });
const clustersBody = await clustersResp.json();
log(`GET /api/v1/clusters -> ${clustersResp.status}, existing clusters = ${clustersBody.total ?? 0}`);
const existingCluster = clustersBody.items?.[0]?.code ?? null;

// --- 3. equivalence on the live deployment ---------------------------------

async function submit(path, { carrier, bytes, text }) {
  const form = new FormData();
  if (carrier === "text") {
    const file = pastedCsvFile(text);
    form.append("file", file, file.name);
  } else {
    form.append("file", new File([bytes], FILE_NAME, { type: FILE_MIME }), FILE_NAME);
  }
  form.append("format", "csv");
  const resp = await fetch(`${BASE}${path}`, {
    method: "POST",
    headers: { Cookie: cookie, Origin: ORIGIN },
    body: form,
  });
  const raw = await resp.text();
  let body;
  try {
    body = JSON.parse(raw);
  } catch {
    body = { unparsable: raw.slice(0, 200) };
  }
  return { status: resp.status, body, raw };
}

const ENDPOINTS = [
  "/api/v1/imports/resources/validate",
  "/api/v1/imports/resource-interfaces-ips/validate",
];

for (const path of ENDPOINTS) {
  for (const name of fixtureNames) {
    const text = readFileSync(join(CORPUS, `${name}.txt`)).toString("utf8");
    const bytes = readFileSync(join(CORPUS, `${name}.csv`));
    const fromText = await submit(path, { carrier: "text", bytes, text });
    const fromFile = await submit(path, { carrier: "file", bytes, text });
    const same = fromText.status === fromFile.status && fromText.raw === fromFile.raw;
    check(
      `live equivalence ${path.split("/")[4]} ${name}`,
      same,
      `status ${fromText.status}/${fromFile.status}`,
    );
    results.push({
      endpoint: path,
      fixture: name,
      textStatus: fromText.status,
      fileStatus: fromFile.status,
      identicalBody: fromText.raw === fromFile.raw,
      body: fromText.body,
    });
  }
}

// A cluster-scoped fixture on the live DB (read-only): reuse a real cluster code
// when the deployment has one, otherwise assert the row-level error is identical.
if (existingCluster) {
  const header = "cluster,hostname,resource_type,role,status,manufacturer,model,serial_number,cpu_model,cpu_sockets,cpu_cores,memory_mb,gpu_model,gpu_count";
  const row = `${existingCluster},f034-live-h1,BARE_METAL,COMPUTE,IDLE,Dell,PowerEdge R750,F034-LIVE-1,Intel Xeon 6338,2,32,262144,NVIDIA A100,4`;
  const text = `${header}\n${row}\n`;
  const fromText = await submit(ENDPOINTS[0], { carrier: "text", bytes: Buffer.from(text), text });
  const fromFile = await submit(ENDPOINTS[0], { carrier: "file", bytes: Buffer.from(text), text });
  check(
    `live equivalence with real cluster ${existingCluster}`,
    fromText.status === fromFile.status && fromText.raw === fromFile.raw,
    `status ${fromText.status}, error_count ${fromText.body.error_count}`,
  );
  results.push({
    endpoint: ENDPOINTS[0],
    fixture: `live-cluster-${existingCluster}`,
    textStatus: fromText.status,
    fileStatus: fromFile.status,
    identicalBody: fromText.raw === fromFile.raw,
    body: fromText.body,
  });
} else {
  log("NOTE: deployment has no Cluster yet; only row-level-error equivalence exercised.");
}

// --- 4. auth boundaries on the live deployment ------------------------------

for (const path of ENDPOINTS) {
  const form = new FormData();
  const file = pastedCsvFile(readFileSync(join(CORPUS, "F-01.txt")).toString("utf8"));
  form.append("file", file, file.name);
  form.append("format", "csv");
  const anon = await fetch(`${BASE}${path}`, { method: "POST", headers: { Origin: ORIGIN }, body: form });
  check(`live 401 without session ${path.split("/")[4]}`, anon.status === 401, `status=${anon.status}`);
}

// --- 5. marker not echoed in the response ----------------------------------

const marker = "F034-MARKER-8a1f4c0d-6f4f-4ef3-9d4a-9f7f3c1b2e55";
const markerText = readFileSync(join(CORPUS, "F-25.txt")).toString("utf8");
const markerResp = await submit(ENDPOINTS[0], { carrier: "text", bytes: Buffer.from(markerText), text: markerText });
check("live response does not echo the pasted payload", !markerResp.raw.includes(marker), `status=${markerResp.status}`);
check(
  "live response does not echo the header line",
  !markerResp.raw.includes(markerText.split("\n")[0]),
);

// --- write out --------------------------------------------------------------

mkdirSync(join(HERE, "logs"), { recursive: true });
writeFileSync(join(HERE, "live-validate-results.json"), JSON.stringify(results, null, 2) + "\n");
log(`\n${results.length} live equivalence cases, ${failures} failures`);
writeFileSync(join(HERE, "logs", "live-validate.log"), lines.join("\n") + "\n");
process.exit(failures === 0 ? 0 : 1);
