/**
 * F035 — H 层真实栈验证（T117.4 / T118 / T119 / T120 / T124 / T123 mixed-batch）。
 *
 * 目标栈：`http://localhost:18080`（compose project `csmtest`，nginx → backend，
 * 候选 HEAD `187ddf3` 重建）。multipart 载荷由**真实前端载体原语**
 * （`frontend/src/components/importCarrier.ts`，Node type stripping 加载）构造，
 * 因此「文本载体」与「文件载体」走同一 wire 形状。
 *
 * 两类用例：
 *  1) 只读（既有 Cluster `N96P` / 既有 Resource `luck`）：`POST /validate` 追加
 *     语义 + `field` 归因；断言无写入副作用（宿主 version/updated_at、子对象计数、
 *     Activity total 不变）。
 *  2) 写入（自建 Cluster `F35TH` + Network `f35th-net` + Host `f35th-host`）：
 *     一次成功追加（`created===0`，宿主不变）+ 一次混合批失败（整批回滚零残留）。
 *     结束后按依赖顺序软删自建对象（清理策略见报告 §2）。
 *
 * Usage:
 *   CSM_PASSWORD=testadmin node docs/features/F035/artifacts/f035-live-validate.mjs
 *   CSM_BASE_URL=... CSM_USERNAME=... CSM_PASSWORD=... node ...
 *
 * Output: docs/features/F035/artifacts/f035-live-validate.json
 *         docs/features/F035/artifacts/logs/f035-live-validate.log
 */

import { mkdirSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import {
  PASTED_CSV_FILE_NAME,
  PASTED_CSV_MIME_TYPE,
  pastedCsvFile,
} from "../../../../frontend/src/components/importCarrier.ts";

const HERE = dirname(fileURLToPath(import.meta.url));
const BASE = process.env.CSM_BASE_URL ?? "http://localhost:18080";
const USERNAME = process.env.CSM_USERNAME ?? "admin";
const PASSWORD = process.env.CSM_PASSWORD ?? "";
if (!PASSWORD) {
  console.error("CSM_PASSWORD must be provided (TEST stack credential; do not commit it)");
  process.exit(2);
}

const VALIDATE = "/api/v1/imports/resource-interfaces-ips/validate";
const WRITE = "/api/v1/imports/resource-interfaces-ips";
const TEMPLATES = "/api/v1/imports/resource-interfaces-ips/templates";

const HEADERS = [
  "cluster",
  "hostname",
  "resource_type",
  "role",
  "status",
  "host",
  "vcpu",
  "memory_mb",
  "disk_gb",
  "hypervisor",
  "manufacturer",
  "model",
  "serial_number",
  "cpu_model",
  "cpu_sockets",
  "cpu_cores",
  "gpu_model",
  "gpu_count",
  "name",
  "interface_type",
  "mac_address",
  "speed_mbps",
  "mtu",
  "enabled",
  "network",
  "ip",
];

const results = [];
const lines = [];
const log = (msg) => {
  lines.push(msg);
  console.log(msg);
};
let failures = 0;

function check(name, ok, detail = "") {
  results.push({ name, ok: Boolean(ok), detail });
  if (ok) {
    log(`PASS ${name}${detail ? ` :: ${detail}` : ""}`);
  } else {
    failures += 1;
    log(`FAIL ${name}${detail ? ` :: ${detail}` : ""}`);
  }
}

function csv(rows) {
  const linesOut = [HEADERS.join(",")];
  for (const row of rows) {
    linesOut.push(HEADERS.map((h) => (row[h] === undefined || row[h] === null ? "" : String(row[h]))).join(","));
  }
  return `${linesOut.join("\n")}\n`;
}

// --- HTTP helpers -----------------------------------------------------------

let cookie = "";

async function call(method, path, { json, form, raw = false } = {}) {
  const headers = { Accept: "application/json" };
  if (cookie) headers.Cookie = cookie;
  if (json !== undefined) headers["Content-Type"] = "application/json";
  const response = await fetch(`${BASE}${path}`, {
    method,
    headers,
    body: json !== undefined ? JSON.stringify(json) : form,
  });
  const setCookie = response.headers.getSetCookie?.() ?? [];
  for (const item of setCookie) {
    const [pair] = item.split(";");
    if (pair.startsWith("csm_session=")) cookie = pair;
  }
  const text = await response.text();
  if (raw) return { status: response.status, text };
  let body = null;
  try {
    body = text ? JSON.parse(text) : null;
  } catch {
    body = { unparsed: text.slice(0, 400) };
  }
  return { status: response.status, body, text };
}

function multipart(bytes, fileName, mime, format = "csv") {
  const form = new FormData();
  form.append("file", new Blob([bytes], { type: mime }), fileName);
  form.append("format", format);
  return form;
}

/** 文件载体：CSV 字节以固定文件名提交。 */
function fileCarrier(text, name = "f035-live.csv") {
  return multipart(text, name, "text/csv");
}

/** 文本载体：走真实前端原语 `pastedCsvFile`（UTF-8 + 固定文件名的 File）。 */
function textCarrier(text) {
  const file = pastedCsvFile(text);
  const form = new FormData();
  form.append("file", file, file.name);
  form.append("format", "csv");
  return form;
}

const validateFile = (text) => call("POST", VALIDATE, { form: fileCarrier(text) });
const validateText = (text) => call("POST", VALIDATE, { form: textCarrier(text) });
const writeFile = (text) => call("POST", WRITE, { form: fileCarrier(text) });

function errorAt(payload, field, row) {
  const errors = payload?.errors ?? payload?.error?.details?.errors ?? [];
  return errors.find((e) => e.field === field && (row === undefined || e.row === row)) ?? null;
}

async function listAll(path) {
  const response = await call("GET", `${path}?page_size=100`);
  return response.body;
}

// --- 1) login + baseline ----------------------------------------------------

const login = await call("POST", "/api/v1/auth/login", {
  json: { username: USERNAME, password: PASSWORD },
});
check("login", login.status === 200, `status=${login.status}`);

const templates = await call("GET", TEMPLATES);
check(
  "templates 26 列且首列 cluster 末列 ip",
  templates.status === 200 &&
    templates.body.template.columns.length === 26 &&
    templates.body.template.columns[0].name === "cluster" &&
    templates.body.template.columns.at(-1).name === "ip",
  `status=${templates.status} cols=${templates.body?.template?.columns?.length}`,
);

const clusters = await listAll("/api/v1/clusters");
const cluster = clusters.items.find((c) => c.code === "N96P");
check("既有 Cluster N96P 存在", Boolean(cluster), JSON.stringify(cluster?.id));

const networks = await listAll("/api/v1/networks");
const netTest = networks.items.find((n) => n.name === "TEST" && n.cluster.code === "N96P");
const netTestnet = networks.items.find((n) => n.name === "TESTNET" && n.cluster.code === "N96P");
check("既有 Network TEST/TESTNET 存在且 ACTIVE", Boolean(netTest && netTestnet) &&
  netTest.status === "ACTIVE" && netTestnet.status === "ACTIVE");

const resources = await listAll("/api/v1/resources");
const luck = resources.items.find((r) => r.hostname === "luck");
check("既有 Resource luck 存在（BM）", Boolean(luck) && luck.resource_type === "BARE_METAL");

const ifaceBefore = await listAll("/api/v1/interfaces");
const ipBefore = await listAll("/api/v1/ip-addresses");
const luckDetailBefore = (await call("GET", `/api/v1/resources/${luck.id}`)).body.resource;
const luckActivityBefore = (await call("GET", `/api/v1/resources/${luck.id}/activity?page_size=100`)).body;
const luckIfacesBefore = (await call("GET", `/api/v1/interfaces?resource_id=${luck.id}&page_size=100`)).body;

// --- 2) read-only validate probes on the existing host ----------------------

const appendRow = {
  cluster: "N96P",
  hostname: "luck",
  resource_type: "BARE_METAL",
  role: "LOGIN",
  status: "ALLOC",
  name: "f35-probe-eth",
  network: "TEST",
  ip: "192.168.10.231",
};
const appendText = csv([appendRow]);

const validateOk = await validateFile(appendText);
check(
  "T117.4 追加行预校验 200 / 0 错误",
  validateOk.status === 200 &&
    validateOk.body.error_count === 0 &&
    validateOk.body.importable_rows === validateOk.body.total_rows &&
    validateOk.body.total_rows === 1,
  JSON.stringify({ status: validateOk.status, ...validateOk.body }),
);

const validateTextCarrier = await validateText(appendText);
check(
  "文本载体与文件载体逐字段一致（F034 增补节沿用）",
  JSON.stringify({ ...validateTextCarrier.body }) === JSON.stringify({ ...validateOk.body }),
  `text.status=${validateTextCarrier.status}`,
);

const mismatch = await validateFile(csv([{ ...appendRow, role: "COMPUTE", name: "f35-probe-eth2", ip: "192.168.10.232" }]));
const roleError = errorAt(mismatch.body, "role");
check(
  "T119.2 既有 role 不一致 → field=role / related_row=null",
  mismatch.status === 200 && roleError !== null && roleError.related_row === null,
  JSON.stringify(roleError),
);

const typeMismatch = await validateFile(
  csv([
    {
      cluster: "N96P",
      hostname: "luck",
      resource_type: "VIRTUAL_MACHINE",
      host: "cn001",
      vcpu: "2",
      memory_mb: "2048",
      name: "f35-probe-eth3",
      network: "TEST",
      ip: "192.168.10.233",
    },
  ]),
);
const typeError = errorAt(typeMismatch.body, "resource_type");
check(
  "T119.1 resource_type 不一致 → field=resource_type",
  typeMismatch.status === 200 && typeError !== null,
  JSON.stringify({ typeError, fields: [...new Set((typeMismatch.body.errors ?? []).map((e) => e.field))] }),
);

const nameConflict = await validateFile(
  csv([{ ...appendRow, name: "eth6", ip: "192.168.10.234" }]),
);
const nameError = errorAt(nameConflict.body, "name");
check(
  "T120.1 宿主既有 Interface 同名 → field=name",
  nameConflict.status === 200 && nameError !== null,
  JSON.stringify(nameError),
);

const ipConflict = await validateFile(csv([{ ...appendRow, name: "f35-probe-eth4", ip: "192.168.10.221" }]));
const ipError = errorAt(ipConflict.body, "ip");
check(
  "T120.3 同 Cluster 既有 IP → field=ip",
  ipConflict.status === 200 && ipError !== null,
  JSON.stringify(ipError),
);

// --- 3) read-only proof: no side effects ------------------------------------

const luckDetailAfter = (await call("GET", `/api/v1/resources/${luck.id}`)).body.resource;
const luckActivityAfter = (await call("GET", `/api/v1/resources/${luck.id}/activity?page_size=100`)).body;
const luckIfacesAfter = (await call("GET", `/api/v1/interfaces?resource_id=${luck.id}&page_size=100`)).body;
const ifaceAfter = await listAll("/api/v1/interfaces");
const ipAfter = await listAll("/api/v1/ip-addresses");

check(
  "预校验无写入副作用：宿主 version/updated_at 不变",
  luckDetailAfter.version === luckDetailBefore.version &&
    luckDetailAfter.updated_at === luckDetailBefore.updated_at,
  `version=${luckDetailAfter.version} updated_at=${luckDetailAfter.updated_at}`,
);
check(
  "预校验无写入副作用：Activity total / interfaces / ip 计数不变",
  luckActivityAfter.total === luckActivityBefore.total &&
    luckIfacesAfter.total === luckIfacesBefore.total &&
    ifaceAfter.total === ifaceBefore.total &&
    ipAfter.total === ipBefore.total,
  JSON.stringify({
    activity: [luckActivityBefore.total, luckActivityAfter.total],
    resourceIfaces: [luckIfacesBefore.total, luckIfacesAfter.total],
    ifaces: [ifaceBefore.total, ifaceAfter.total],
    ips: [ipBefore.total, ipAfter.total],
  }),
);

// --- 4) write cases on a self-created cluster ------------------------------

// Cluster `code_key` is globally UNIQUE (soft delete keeps the code), so each
// run uses a fresh code; the cleanup block soft-deletes it again.
const CODE = process.env.CSM_F035_CLUSTER_CODE ?? `F35T${Date.now().toString(36).slice(-4).toUpperCase()}`;
const created = { cluster: null, network: null, resource: null, interfaces: [], ips: [] };

const clusterCreate = await call("POST", "/api/v1/clusters", {
  json: { code: CODE, name: "F035 Tester H-layer cluster" },
});
if (clusterCreate.status === 201) created.cluster = clusterCreate.body.cluster;
check(`自建 Cluster ${CODE}`, clusterCreate.status === 201, `status=${clusterCreate.status}`);

const networkCreate = await call("POST", "/api/v1/networks", {
  json: { cluster: created.cluster.id, name: "f35th-net", cidr: "10.180.0.0/24" },
});
if (networkCreate.status === 201) created.network = networkCreate.body.network;
check("自建 Network f35th-net 10.180.0.0/24", networkCreate.status === 201, `status=${networkCreate.status}`);

const hostCreate = await call("POST", "/api/v1/resources", {
  json: {
    cluster: CODE,
    hostname: "f35th-host",
    resource_type: "BARE_METAL",
    role: "COMPUTE",
    status: "IDLE",
    hardware: { manufacturer: "Dell", cpu_cores: 16, memory_mb: 65536 },
  },
});
if (hostCreate.status === 201) created.resource = hostCreate.body.resource;
check("自建既有宿主 f35th-host", hostCreate.status === 201, `status=${hostCreate.status}`);

const ifaceCreate = await call("POST", "/api/v1/interfaces", {
  json: { resource: created.resource.id, name: "eth0" },
});
if (ifaceCreate.status === 201) created.interfaces.push(ifaceCreate.body.interface);
check("自建既有 Interface eth0", ifaceCreate.status === 201, `status=${ifaceCreate.status}`);

// F010: allocation and binding are separate steps (POST allocates, PATCH binds).
const ipCreate = await call("POST", "/api/v1/ip-addresses", {
  json: { network: created.network.id, address: "10.180.0.10" },
});
if (ipCreate.status === 201) created.ips.push(ipCreate.body.ip_address);
check("自建既有 IP 10.180.0.10", ipCreate.status === 201, `status=${ipCreate.status}`);
if (ipCreate.status === 201) {
  const bind = await call("PATCH", `/api/v1/ip-addresses/${ipCreate.body.ip_address.id}`, {
    json: { version: ipCreate.body.ip_address.version, interface: created.interfaces[0].id },
  });
  check(
    "绑定既有 IP → eth0（F010 PATCH）",
    bind.status === 200 && bind.body.ip_address.interface?.id === created.interfaces[0].id,
    `status=${bind.status}`,
  );
  created.ips[created.ips.length - 1] = bind.body.ip_address ?? ipCreate.body.ip_address;
}

const hostBefore = (await call("GET", `/api/v1/resources/${created.resource.id}`)).body.resource;
const hostActivityBefore = (
  await call("GET", `/api/v1/resources/${created.resource.id}/activity?page_size=100`)
).body;
const hostIfacesBefore = (
  await call("GET", `/api/v1/interfaces?resource_id=${created.resource.id}&page_size=100`)
).body;

const appendWriteRows = [
  {
    cluster: CODE,
    hostname: "f35th-host",
    resource_type: "BARE_METAL",
    role: "COMPUTE",
    status: "IDLE",
    manufacturer: "Dell",
    cpu_cores: "16",
    memory_mb: "65536",
    name: "f35th-eth1",
    interface_type: "PHYSICAL",
    network: "f35th-net",
    ip: "10.180.0.11",
  },
];
const appendValidate = await validateFile(csv(appendWriteRows));
check(
  "写入前预校验（追加行）0 错误",
  appendValidate.status === 200 && appendValidate.body.error_count === 0,
  JSON.stringify(appendValidate.body),
);

const appendWrite = await writeFile(csv(appendWriteRows));
check(
  "T117.1 真实栈追加写入 201 / created===0 / 响应键恰 4 个",
  appendWrite.status === 201 &&
    appendWrite.body.created === 0 &&
    appendWrite.body.interfaces_created === 1 &&
    appendWrite.body.ip_addresses_created === 1 &&
    appendWrite.body.total_rows === 1 &&
    Object.keys(appendWrite.body).sort().join(",") ===
      ["created", "interfaces_created", "ip_addresses_created", "total_rows"].join(","),
  JSON.stringify(appendWrite.body),
);

const hostAfter = (await call("GET", `/api/v1/resources/${created.resource.id}`)).body.resource;
const hostIfacesAfterWrite = (
  await call("GET", `/api/v1/interfaces?resource_id=${created.resource.id}&page_size=100`)
).body;
const hostActivityAfter = (
  await call("GET", `/api/v1/resources/${created.resource.id}/activity?page_size=100`)
).body;
const newIface = hostIfacesAfterWrite.items.find((i) => i.name === "f35th-eth1");
if (newIface) created.interfaces.push(newIface);
const newIp = (await listAll("/api/v1/ip-addresses")).items.find(
  (i) => i.address.startsWith("10.180.0.11"),
);
if (newIp) created.ips.push(newIp);

check(
  "T118.1 真实栈追加后既有 Resource 未变（version/updated_at/全字段）",
  JSON.stringify(hostAfter) === JSON.stringify(hostBefore),
  `version ${hostBefore.version}→${hostAfter.version}`,
);
check(
  "T118.3 宿主 Activity 无 UPDATE 项且 total 不变",
  { ...hostActivityAfter }.items.every((item) => item.action === "CREATE") &&
    hostActivityAfter.total === hostActivityBefore.total,
  JSON.stringify({ actions: [...new Set(hostActivityAfter.items.map((i) => i.action))], totals: [hostActivityBefore.total, hostActivityAfter.total] }),
);
check(
  "T117.2 新 Interface 归属既有宿主 + 新 IP 绑定新 Interface",
  Boolean(newIface && newIp) &&
    newIface.resource?.id === created.resource.id &&
    newIp.interface?.id === newIface.id,
  JSON.stringify({ newIface: newIface?.id, newIp: newIp?.id, bound: newIp?.interface?.id }),
);

// --- 5) mixed batch failure (create group + append group) ------------------

const mixedRows = [
  {
    cluster: CODE,
    hostname: "f35th-new",
    resource_type: "BARE_METAL",
    name: "f35th-new-eth",
    network: "f35th-net",
    ip: "10.180.0.31",
  },
  {
    cluster: CODE,
    hostname: "f35th-host",
    resource_type: "BARE_METAL",
    role: "GPU",
    name: "f35th-eth2",
    network: "f35th-net",
    ip: "10.180.0.32",
  },
];
const mixedWrite = await writeFile(csv(mixedRows));
const mixedRoleError = errorAt(mixedWrite.body?.error?.details, "role");
check(
  "T123.2 混合批失败 → 422 IMPORT_VALIDATION_FAILED + field=role",
  mixedWrite.status === 422 &&
    mixedWrite.body.error.code === "IMPORT_VALIDATION_FAILED" &&
    mixedRoleError !== null,
  JSON.stringify({ status: mixedWrite.status, code: mixedWrite.body?.error?.code, role: mixedRoleError }),
);

const resourcesAfterMixed = await listAll("/api/v1/resources");
const hostIfacesAfterMixed = (
  await call("GET", `/api/v1/interfaces?resource_id=${created.resource.id}&page_size=100`)
).body;
const ipsAfterMixed = await listAll("/api/v1/ip-addresses");
check(
  "T123.2 零残留：新建组 Resource 不留存、无新 Interface/IP",
  resourcesAfterMixed.items.every((r) => r.hostname !== "f35th-new") &&
    hostIfacesAfterMixed.items.every((i) => i.name !== "f35th-eth2") &&
    ipsAfterMixed.items.every((i) => !i.address.startsWith("10.180.0.32")),
  JSON.stringify({
    newHostPresent: resourcesAfterMixed.items.some((r) => r.hostname === "f35th-new"),
    ifaceNames: hostIfacesAfterMixed.items.map((i) => i.name),
  }),
);

const hostAfterMixed = (await call("GET", `/api/v1/resources/${created.resource.id}`)).body.resource;
check(
  "T123.2 宿主仍零变化（失败批不产生 UPDATE）",
  JSON.stringify(hostAfterMixed) === JSON.stringify(hostBefore),
  `version ${hostBefore.version}→${hostAfterMixed.version}`,
);

// --- 6) cleanup (soft delete, dependency order) ----------------------------

const cleanup = [];
async function softDelete(path, version, label) {
  const response = await call("DELETE", `${path}?version=${version}`);
  cleanup.push({ label, status: response.status });
  log(`cleanup ${label} -> ${response.status}`);
}
for (const ip of created.ips) {
  const current = (await call("GET", `/api/v1/ip-addresses/${ip.id}`)).body.ip_address;
  await softDelete(`/api/v1/ip-addresses/${ip.id}`, current.version, `ip ${ip.address}`);
}
for (const iface of created.interfaces) {
  const current = (await call("GET", `/api/v1/interfaces/${iface.id}`)).body.interface;
  await softDelete(`/api/v1/interfaces/${iface.id}`, current.version, `interface ${iface.name}`);
}
const hostCurrent = (await call("GET", `/api/v1/resources/${created.resource.id}`)).body.resource;
await softDelete(`/api/v1/resources/${created.resource.id}`, hostCurrent.version, "resource f35th-host");
const netCurrent = (await call("GET", `/api/v1/networks/${created.network.id}`)).body.network;
await softDelete(`/api/v1/networks/${created.network.id}`, netCurrent.version, "network f35th-net");
const clusterCurrent = (await call("GET", `/api/v1/clusters/${created.cluster.id}`)).body.cluster;
await softDelete(`/api/v1/clusters/${created.cluster.id}`, clusterCurrent.version, `cluster ${CODE}`);
check(
  "清理：自建对象全部软删成功（204）",
  cleanup.length === created.ips.length + created.interfaces.length + 3 &&
    cleanup.every((item) => item.status === 204),
  JSON.stringify(cleanup),
);
const activeAfter = await listAll("/api/v1/resources");
check(
  "清理：自建 hostname 不再出现在默认列表",
  activeAfter.items.every((r) => r.hostname !== "f35th-host"),
);

// --- output ---------------------------------------------------------------

const payload = {
  feature: "F035",
  layer: "H (real stack)",
  base: BASE,
  candidate_head: process.env.CANDIDATE_HEAD ?? "187ddf3",
  executed_at: new Date().toISOString(),
  password_used: "TEST stack credential (.env.test INITIAL_ADMIN_PASSWORD); not recorded",
  pasted_carrier_file: PASTED_CSV_FILE_NAME,
  pasted_carrier_mime: PASTED_CSV_MIME_TYPE,
  read_only_host: { cluster: "N96P", hostname: "luck", id: luck.id },
  write_scope: { cluster: CODE, network: "f35th-net", hostname: "f35th-host" },
  cleanup,
  failures,
  results,
};

mkdirSync(join(HERE, "logs"), { recursive: true });
writeFileSync(join(HERE, "f035-live-validate.json"), `${JSON.stringify(payload, null, 2)}\n`);
writeFileSync(join(HERE, "logs", "f035-live-validate.log"), `${lines.join("\n")}\n`);
log(`\n${results.length - failures}/${results.length} checks passed`);
process.exit(failures === 0 ? 0 : 1);
