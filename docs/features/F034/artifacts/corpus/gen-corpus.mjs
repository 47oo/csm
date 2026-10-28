/**
 * F034 corpus generator (TEST DESIGN v1.1 TD-8.1).
 *
 * Single source of truth for the F-01 … F-26 fixtures used by
 * `backend/tests/integration/test_f034_csv_text_carrier*.py`.
 *
 * For every fixture it writes two files into this directory:
 *   - `F-xx.txt` : the exact text a user would paste (UTF-8 bytes);
 *   - `F-xx.csv` : `Buffer.from(text, "utf8")` written once — the byte-identical
 *                  "file carrier" counterpart.
 *
 * It then re-reads both and asserts `Buffer.compare(txt, csv) === 0`, closing
 * TD-5 equivalence layer 1 ("the two carriers carry the same bytes").
 *
 * Read-only w.r.t. the application: only writes files inside this directory.
 *
 * Usage: node docs/features/F034/artifacts/corpus/gen-corpus.mjs
 */

import { writeFileSync, readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));

// --- frozen template headers (Contract F014 §6 / F023 §6) -------------------

const BM = [
  "cluster", "hostname", "resource_type", "role", "status", "manufacturer",
  "model", "serial_number", "cpu_model", "cpu_sockets", "cpu_cores",
  "memory_mb", "gpu_model", "gpu_count",
];
const VM = [
  "cluster", "hostname", "resource_type", "role", "status", "host", "vcpu",
  "memory_mb", "disk_gb", "hypervisor",
];
const W26 = [
  "cluster", "hostname", "resource_type", "role", "status", "host", "vcpu",
  "memory_mb", "disk_gb", "hypervisor", "manufacturer", "model",
  "serial_number", "cpu_model", "cpu_sockets", "cpu_cores", "gpu_model",
  "gpu_count", "name", "interface_type", "mac_address", "speed_mbps", "mtu",
  "enabled", "network", "ip",
];

const CLUSTER = "F34A";
const MARKER = "F034-MARKER-8a1f4c0d-6f4f-4ef3-9d4a-9f7f3c1b2e55";

// --- helpers ----------------------------------------------------------------

const line = (cells) => cells.join(",");

/** Build a CSV row for `headers` from a partial record. */
function row(headers, values) {
  return line(headers.map((h) => (values[h] === undefined || values[h] === null ? "" : String(values[h]))));
}

const bmRow = (v) => row(BM, v);
const vmRow = (v) => row(VM, v);
const w26Row = (v) => row(W26, v);

/** Quote a cell the way a spreadsheet/CSV writer would (double `"` escapes). */
const q = (cell) => `"${String(cell).replaceAll('"', '""')}"`;

// A canonical legal BARE_METAL record set (F-01).
const BM_ROWS = [
  { cluster: CLUSTER, hostname: "f34-h1", resource_type: "BARE_METAL", role: "COMPUTE", status: "IDLE", manufacturer: "Dell", model: "PowerEdge R750", serial_number: "F34-SN-1", cpu_model: "Intel Xeon 6338", cpu_sockets: 2, cpu_cores: 32, memory_mb: 262144, gpu_model: "NVIDIA A100", gpu_count: 4 },
  { cluster: CLUSTER, hostname: "f34-h2", resource_type: "BARE_METAL", role: "COMPUTE", status: "IDLE", manufacturer: "Dell", model: "PowerEdge R750", serial_number: "F34-SN-2", cpu_model: "Intel Xeon 6338", cpu_sockets: 2, cpu_cores: 32, memory_mb: 262144, gpu_model: "NVIDIA A100", gpu_count: 4 },
];

const BM_HEADER_LINE = line(BM);
const VM_HEADER_LINE = line(VM);
const W26_HEADER_LINE = line(W26);

/** F-01 canonical body (header + 2 legal BM rows), LF, no BOM, trailing LF. */
const F01 = [BM_HEADER_LINE, ...BM_ROWS.map(bmRow)].join("\n") + "\n";

// --- fixture definitions ----------------------------------------------------

const corpus = new Map();

// F-01 legal BM text (LF).
corpus.set("F-01", F01);

// F-02 legal VM text; `host` must be an undeleted BARE_METAL of the same cluster
// (the test pre-creates `f34-pre` through the API, never through this batch).
corpus.set(
  "F-02",
  [
    VM_HEADER_LINE,
    vmRow({ cluster: CLUSTER, hostname: "f34-vm1", resource_type: "VIRTUAL_MACHINE", role: "COMPUTE", status: "IDLE", host: "f34-pre", vcpu: 8, memory_mb: 16384, disk_gb: 200, hypervisor: "KVM" }),
  ].join("\n") + "\n",
);

// F-03 26-column BM + VM mix (one resource with several IPs, different hosts).
corpus.set(
  "F-03",
  [
    W26_HEADER_LINE,
    w26Row({ cluster: CLUSTER, hostname: "f34-w-bm1", resource_type: "BARE_METAL", role: "COMPUTE", status: "IDLE", name: "eth0", interface_type: "PHYSICAL", network: "f34-net", ip: "10.34.0.11" }),
    w26Row({ cluster: CLUSTER, hostname: "f34-w-bm1", resource_type: "BARE_METAL", role: "COMPUTE", status: "IDLE", name: "eth1", interface_type: "PHYSICAL", network: "f34-net", ip: "10.34.0.12" }),
    w26Row({ cluster: CLUSTER, hostname: "f34-w-h1", resource_type: "BARE_METAL", role: "COMPUTE", status: "IDLE", name: "eth0", interface_type: "PHYSICAL", network: "f34-net", ip: "10.34.0.13" }),
  ].join("\n") + "\n",
);

// F-04 completely empty (0 bytes).
corpus.set("F-04", "");

// F-05 pure whitespace (frontend blocks locally; server side observation only).
corpus.set("F-05", "   ");

// F-05b non-blank but no usable header -> header_missing (TD3-T110.5).
corpus.set("F-05b", ",,,\n");

// F-06a / F-06b header only, no data row -> empty_file.
corpus.set("F-06a", BM_HEADER_LINE + "\n");
corpus.set("F-06b", W26_HEADER_LINE + "\n");

// F-07 BOM + F-01 (utf-8-sig; header first column must not be polluted).
corpus.set("F-07", "\uFEFF" + F01);

// F-08 CRLF everywhere.
corpus.set("F-08", F01.replaceAll("\n", "\r\n"));

// F-09 mixed line endings: header CRLF, row 1 LF, row 2 CRLF.
{
  const lines = F01.split("\n").filter((l, i, all) => !(i === all.length - 1 && l === ""));
  corpus.set("F-09", [lines[0] + "\r\n", lines[1] + "\n", lines[2] + "\r\n"].join(""));
}

// F-10 F-01 + 3 trailing blank lines + trailing newline (trailing records dropped).
corpus.set("F-10", F01 + "\n\n\n");

// F-10b F-01 shape with a 3rd (invalid) data row + trailing blank lines: real
// data row numbers must not move (the error stays at row 4).
corpus.set(
  "F-10b",
  [
    BM_HEADER_LINE,
    bmRow(BM_ROWS[0]),
    bmRow(BM_ROWS[1]),
    bmRow({ ...BM_ROWS[0], hostname: "BAD HOSTNAME!", serial_number: "F34-SN-3" }),
  ].join("\n") + "\n\n\n\n",
);

// F-11 quoted embedded newline in `manufacturer`; 2nd data row invalid.
corpus.set(
  "F-11",
  [
    BM_HEADER_LINE,
    line([CLUSTER, "f34-q1", "BARE_METAL", "COMPUTE", "IDLE"]) + "," + q("Manu\nal") + "," + line(["PowerEdge R750", "F34-SN-Q1", "Intel Xeon 6338", "2", "32", "262144", "NVIDIA A100", "4"]),
    bmRow({ cluster: CLUSTER, hostname: "BAD HOSTNAME!", resource_type: "BARE_METAL", role: "COMPUTE", status: "IDLE", serial_number: "F34-SN-Q2" }),
  ].join("\n") + "\n",
);

// F-12 comma inside a quoted field + doubled-quote escape.
corpus.set(
  "F-12",
  [
    BM_HEADER_LINE,
    line([CLUSTER, "f34-q2", "BARE_METAL", "COMPUTE", "IDLE"]) + "," + q("Dell, Inc.") + "," + line(["PowerEdge R750", "F34-SN-Q3", "Intel Xeon 6338", "2", "32", "262144", "NVIDIA A100", "4"]),
    line([CLUSTER, "f34-q3", "BARE_METAL", "COMPUTE", "IDLE"]) + "," + q('Manu"facturer') + "," + line(["PowerEdge R750", "F34-SN-Q4", "Intel Xeon 6338", "2", "32", "262144", "NVIDIA A100", "4"]),
  ].join("\n") + "\n",
);

// F-13 unclosed quote in the middle of the file (existing csv.reader behaviour:
// it swallows the remaining physical lines into one field). T114 is judged by
// EQUIVALENCE only (architecture §12 / TD-I-1), never by "must be 422".
corpus.set(
  "F-13",
  [
    BM_HEADER_LINE,
    line([CLUSTER, "f34-u1", "BARE_METAL", "COMPUTE", "IDLE"]) + ',"Manu',
    bmRow({ ...BM_ROWS[1], hostname: "f34-u2", serial_number: "F34-SN-U2" }),
  ].join("\n") + "\n",
);

// F-14 F-01 with every comma replaced by a tab (separator sniffing must not happen).
corpus.set("F-14", F01.replaceAll(",", "\t"));

// F-15 first physical line is a data row (no header at all).
corpus.set("F-15", bmRow(BM_ROWS[0]) + "\n" + bmRow(BM_ROWS[1]) + "\n");

// F-15a blank first line then data rows -> header_missing.
corpus.set("F-15a", "\n" + bmRow(BM_ROWS[0]) + "\n");

// F-16 missing column `hostname` (BM) -> missing_columns.
corpus.set(
  "F-16",
  [line(BM.filter((h) => h !== "hostname")), line([CLUSTER, "BARE_METAL", "COMPUTE", "IDLE"])].join("\n") + "\n",
);

// F-17 extra undefined column `interface_name` -> unknown_columns.
corpus.set("F-17", [line([...BM, "interface_name"]), line([CLUSTER, "f34-x1", "BARE_METAL", "COMPUTE", "IDLE", "", "", "", "", "", "", "", "", "", "", "eth9"])].join("\n") + "\n");

// F-18a header fully reversed -> column_order.
corpus.set("F-18a", [line([...BM].reverse()), bmRow(BM_ROWS[0])].join("\n") + "\n");

// F-18b only the first two columns swapped -> column_order.
corpus.set("F-18b", [line(["hostname", "cluster", ...BM.slice(2)]), line(["f34-y1", CLUSTER])].join("\n") + "\n");

// F-19 case-folded header (HOSTNAME) -> must NOT be accepted.
corpus.set("F-19", [line(BM.map((h) => (h === "hostname" ? "HOSTNAME" : h))), bmRow(BM_ROWS[0])].join("\n") + "\n");

// F-20 six-class row-error matrix (no fail-fast; aggregated errors).
corpus.set(
  "F-20",
  [
    BM_HEADER_LINE,
    // row 2: illegal enum
    bmRow({ cluster: CLUSTER, hostname: "f34-e-role", resource_type: "BARE_METAL", role: "FOO", status: "IDLE" }),
    // row 3: illegal integer
    bmRow({ cluster: CLUSTER, hostname: "f34-e-int", resource_type: "BARE_METAL", role: "COMPUTE", status: "IDLE", memory_mb: "abc" }),
    // row 4: length > 255
    bmRow({ cluster: CLUSTER, hostname: "f34-e-len", resource_type: "BARE_METAL", role: "COMPUTE", status: "IDLE", manufacturer: "M".repeat(256) }),
    // row 5 / row 6: batch duplicate (row 6 -> related_row 5)
    bmRow({ cluster: CLUSTER, hostname: "f34-e-dup", resource_type: "BARE_METAL", role: "COMPUTE", status: "IDLE" }),
    bmRow({ cluster: CLUSTER, hostname: "f34-e-dup", resource_type: "BARE_METAL", role: "COMPUTE", status: "IDLE", serial_number: "F34-SN-DUP2" }),
    // row 7: conflicts with a resource the test pre-creates through the API
    bmRow({ cluster: CLUSTER, hostname: "f34-exists", resource_type: "BARE_METAL", role: "COMPUTE", status: "IDLE" }),
    // row 8: cluster does not exist (or is out of scope)
    bmRow({ cluster: "F34MISSING", hostname: "f34-e-cl", resource_type: "BARE_METAL", role: "COMPUTE", status: "IDLE" }),
  ].join("\n") + "\n",
);

// F-24 BOM only (frontend `trim()` treats U+FEFF as blank; server would say empty_file).
corpus.set("F-24", "\uFEFF");

// F-25 F-01 plus a searchable marker in a legal field (leak probe).
corpus.set(
  "F-25",
  [
    BM_HEADER_LINE,
    bmRow({ ...BM_ROWS[0], hostname: "f34-marker", serial_number: MARKER }),
  ].join("\n") + "\n",
);

// F-26 non-ASCII values (Chinese + emoji) — byte counting / round-trip.
corpus.set(
  "F-26",
  [
    BM_HEADER_LINE,
    line([CLUSTER, "f34-utf8", "BARE_METAL", "COMPUTE", "IDLE"]) + "," + q("戴尔, Inc.") + "," + line(["PowerEdge R750", "F34-SN-UTF8", "Intel Xeon 6338", "2", "32", "262144"]) + "," + "A100-🚀" + ",4",
  ].join("\n") + "\n",
);

// F-03f same logical shape as F-03 with distinct hosts/IPs, used to compare the
// write envelope of the FILE carrier against the TEXT carrier's F-03 run
// (TD3-T108.8) without creating duplicate-conflicts between the two runs.
corpus.set(
  "F-03f",
  [
    W26_HEADER_LINE,
    w26Row({ cluster: CLUSTER, hostname: "f34-f-bm1", resource_type: "BARE_METAL", role: "COMPUTE", status: "IDLE", name: "eth0", interface_type: "PHYSICAL", network: "f34-net", ip: "10.34.0.21" }),
    w26Row({ cluster: CLUSTER, hostname: "f34-f-bm1", resource_type: "BARE_METAL", role: "COMPUTE", status: "IDLE", name: "eth1", interface_type: "PHYSICAL", network: "f34-net", ip: "10.34.0.22" }),
    w26Row({ cluster: CLUSTER, hostname: "f34-f-h1", resource_type: "BARE_METAL", role: "COMPUTE", status: "IDLE", name: "eth0", interface_type: "PHYSICAL", network: "f34-net", ip: "10.34.0.23" }),
  ].join("\n") + "\n",
);

// F-20w 26-column row-error matrix (T109.3): batch duplicate (cluster, ip) with
// related_row, unresolvable Network, and row-type applicability conflict.
corpus.set(
  "F-20w",
  [
    W26_HEADER_LINE,
    w26Row({ cluster: CLUSTER, hostname: "f34-w-e-a", resource_type: "BARE_METAL", role: "COMPUTE", status: "IDLE", name: "eth0", interface_type: "PHYSICAL", network: "f34-net", ip: "10.34.0.41" }),
    w26Row({ cluster: CLUSTER, hostname: "f34-w-e-b", resource_type: "BARE_METAL", role: "COMPUTE", status: "IDLE", name: "eth0", interface_type: "PHYSICAL", network: "f34-net", ip: "10.34.0.41" }),
    w26Row({ cluster: CLUSTER, hostname: "f34-w-e-c", resource_type: "BARE_METAL", role: "COMPUTE", status: "IDLE", name: "eth0", interface_type: "PHYSICAL", network: "f34-no-such-net", ip: "10.34.0.42" }),
    w26Row({ cluster: CLUSTER, hostname: "f34-w-e-d", resource_type: "BARE_METAL", role: "COMPUTE", status: "IDLE", vcpu: 8, name: "eth0", interface_type: "PHYSICAL", network: "f34-net", ip: "10.34.0.43" }),
  ].join("\n") + "\n",
);

// --- write + verify ---------------------------------------------------------

let failures = 0;
const rows = [];
for (const [name, text] of corpus) {
  const bytes = Buffer.from(text, "utf8");
  writeFileSync(join(HERE, `${name}.txt`), bytes);
  writeFileSync(join(HERE, `${name}.csv`), bytes);
  const txtRead = readFileSync(join(HERE, `${name}.txt`));
  const csvRead = readFileSync(join(HERE, `${name}.csv`));
  const identical = Buffer.compare(txtRead, csvRead) === 0;
  const roundTrip = Buffer.compare(Buffer.from(txtRead.toString("utf8"), "utf8"), txtRead) === 0;
  if (!identical || !roundTrip) failures += 1;
  rows.push({ name, bytes: bytes.length, identical, roundTrip });
}

// Boundary arithmetic (TD3-T111.1/2/3): UTF-8 bytes, strictly-greater rejection.
const LIMIT = 5_242_880;
const utf8 = (s) => new TextEncoder().encode(s).length;
const asciiBoundary = (n) => "a".repeat(n); // 1 byte per code unit
const multiByteOver = (() => {
  // 2,621,441 CJK code points = 7,864,323 bytes (> limit) while
  // String.length (2,621,441) is far below the limit -> kills `.length` impls.
  const s = "中".repeat(2_621_441);
  return { length: s.length, bytes: utf8(s) };
})();

const boundary = {
  limit: LIMIT,
  ascii: {
    minus1: { length: LIMIT - 1, bytes: utf8(asciiBoundary(LIMIT - 1)) },
    exact: { length: LIMIT, bytes: utf8(asciiBoundary(LIMIT)) },
    plus1: { length: LIMIT + 1, bytes: utf8(asciiBoundary(LIMIT + 1)) },
  },
  antiHole: {
    multiByteOver,
    lengthBelowLimit: multiByteOver.length < LIMIT,
    bytesAboveLimit: multiByteOver.bytes > LIMIT,
  },
  samples: {
    ascii: utf8("abc"),
    chinese: utf8("中文"),
    emoji: utf8("🚀"),
    mixed: utf8("a中🚀"),
  },
};

writeFileSync(join(HERE, "boundary.json"), JSON.stringify(boundary, null, 2) + "\n");
writeFileSync(
  join(HERE, "corpus-manifest.json"),
  JSON.stringify({ cluster: CLUSTER, marker: MARKER, headers: { BM, VM, W26 }, files: rows }, null, 2) + "\n",
);

for (const r of rows) {
  console.log(`${r.identical && r.roundTrip ? "OK  " : "FAIL"} ${r.name.padEnd(7)} ${String(r.bytes).padStart(8)} bytes`);
}
console.log(
  `\n${rows.length} fixtures, ${failures} byte-identity failures\n` +
    `boundary: ascii ${boundary.ascii.minus1.bytes}/${boundary.ascii.exact.bytes}/${boundary.ascii.plus1.bytes} bytes (limit ${LIMIT})`,
);
console.log(
  `anti-hole: length=${boundary.antiHole.multiByteOver.length} (< limit) bytes=${boundary.antiHole.multiByteOver.bytes} (> limit) -> ${boundary.antiHole.lengthBelowLimit && boundary.antiHole.bytesAboveLimit ? "OK" : "FAIL"}`,
);
process.exit(failures === 0 ? 0 : 1);
