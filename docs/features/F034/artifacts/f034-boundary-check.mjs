/**
 * F034 — independent U-layer boundary check (TD3-T111.1/2/3/4/8, TD3-T110.1/2).
 *
 * Loads the real `importForm.ts` / `resourceInterfaceIpImportForm.ts` /
 * `importCarrier.ts` through Node's TypeScript type stripping and asserts the
 * local (non-authoritative) gate semantics that the Test Design fixes:
 *
 *   - byte counting is UTF-8 bytes, not `String.length` (anti-hole pair);
 *   - the rejection comparison is **strictly greater** than 5,242,880;
 *   - blank / whitespace-only payloads are rejected locally;
 *   - the row cap (5000) is NOT mirrored on the client.
 *
 * No network, no database, no writes. Run:
 *   node docs/features/F034/artifacts/f034-boundary-check.mjs
 */

import { readFileSync, writeFileSync, mkdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { IMPORT_MAX_FILE_BYTES } from "../../../../frontend/src/api/imports.ts";
import {
  emptyImportFormValues,
  parseImportFormValues,
} from "../../../../frontend/src/components/importForm.ts";
import { parseResourceInterfaceIpImportFormValues } from "../../../../frontend/src/components/resourceInterfaceIpImportForm.ts";
import {
  fileImportTargetKey,
  textImportTargetKey,
  utf8ByteLength,
} from "../../../../frontend/src/components/importCarrier.ts";

const HERE = dirname(fileURLToPath(import.meta.url));
const LIMIT = IMPORT_MAX_FILE_BYTES;

const lines = [];
let failures = 0;
const check = (name, ok, detail = "") => {
  if (!ok) failures += 1;
  const line = `${ok ? "PASS" : "FAIL"} ${name}${detail ? ` — ${detail}` : ""}`;
  lines.push(line);
  console.log(line);
};

const textValues = (text) => ({ ...emptyImportFormValues(), carrier: "text", format: "csv", text });
const fileValues = () => ({ ...emptyImportFormValues(), carrier: "file" });

check("IMPORT_MAX_FILE_BYTES === 5,242,880", LIMIT === 5_242_880, String(LIMIT));

// --- T111.1 byte counting ----------------------------------------------------

for (const [name, value] of Object.entries({ ascii: "abc", chinese: "中文", emoji: "🚀", mixed: "a中🚀" })) {
  const expected = new TextEncoder().encode(value).length;
  check(`T111.1 utf8ByteLength(${name})`, utf8ByteLength(value) === expected, `${utf8ByteLength(value)} == ${expected}`);
}
check(
  "T111.1 byte length differs from String.length (multi-byte)",
  utf8ByteLength("中".repeat(100)) === 300 && "中".repeat(100).length === 100,
);

// --- T111.2 strict boundary (ASCII filler, 1 byte per code unit) -------------

const ascii = (n) => "a".repeat(n);
for (const [label, size, expected] of [
  ["limit-1", LIMIT - 1, true],
  ["limit", LIMIT, true],
  ["limit+1", LIMIT + 1, false],
]) {
  const parsed = parseImportFormValues(textValues(ascii(size)));
  check(
    `T111.2 text carrier ${label} (${size} bytes) -> ${expected ? "accepted" : "rejected locally"}`,
    parsed.ok === expected,
    parsed.ok ? "" : JSON.stringify(parsed.errors),
  );
  const parsedIp = parseResourceInterfaceIpImportFormValues(textValues(ascii(size)));
  check(
    `T111.2 F023 carrier ${label} (${size} bytes) -> ${expected ? "accepted" : "rejected locally"}`,
    parsedIp.ok === expected,
    parsedIp.ok ? "" : JSON.stringify(parsedIp.errors),
  );
}

// --- T111.3 anti-hole: String.length below the limit, UTF-8 bytes above it ---

const multiByte = "中".repeat(Math.ceil((LIMIT + 1000) / 3));
const multiByteLength = multiByte.length;
const multiByteBytes = utf8ByteLength(multiByte);
check(
  "T111.3 anti-hole fixture is constructed correctly",
  multiByteLength < LIMIT && multiByteBytes > LIMIT,
  `String.length=${multiByteLength} bytes=${multiByteBytes} limit=${LIMIT}`,
);
const holeParsed = parseImportFormValues(textValues(multiByte));
check(
  "T111.3 anti-hole: multi-byte payload over the byte cap is rejected locally",
  holeParsed.ok === false && Boolean(holeParsed.errors.text),
  JSON.stringify(holeParsed.ok ? "accepted (would be a FAIL)" : holeParsed.errors),
);

// --- T110.1 blank payloads ---------------------------------------------------

for (const blank of ["", "   ", "\n\n", " \t\r\n "]) {
  const parsed = parseImportFormValues(textValues(blank));
  check(
    `T110.1 blank ${JSON.stringify(blank)} rejected locally with a text error`,
    parsed.ok === false && Boolean(parsed.errors.text),
    JSON.stringify(parsed.ok ? "accepted" : parsed.errors),
  );
}

// --- T111.8 the row cap is not mirrored on the client -----------------------

const header = readFileSync(join(HERE, "corpus", "F-01.txt"), "utf8").split("\n")[0];
const bigRows = Array.from({ length: 5001 }, (_, index) => `F34A,f34-row-${index},BARE_METAL`).join("\n");
const bigText = `${header}\n${bigRows}\n`;
const bigParsed = parseImportFormValues(textValues(bigText));
check(
  "T111.8 5001-row small-byte text is accepted locally (server is authoritative)",
  bigParsed.ok === true,
  bigParsed.ok ? `${utf8ByteLength(bigText)} bytes` : JSON.stringify(bigParsed.errors),
);

// --- format / carrier defensive branches (T116.5) ---------------------------

const badFormat = parseImportFormValues({ ...textValues("a,b\n"), format: "xlsx" });
check(
  "T116.5 text carrier with format=xlsx is rejected (defensive branch)",
  badFormat.ok === false && Boolean(badFormat.errors.format),
  JSON.stringify(badFormat.ok ? "accepted" : badFormat.errors),
);
const badCarrier = parseImportFormValues({ ...emptyImportFormValues(), carrier: "nope", text: "a,b\n" });
check(
  "T116.5 unknown carrier value is rejected (defensive branch)",
  badCarrier.ok === false && Boolean(badCarrier.errors.carrier),
  JSON.stringify(badCarrier.ok ? "accepted" : badCarrier.errors),
);

// --- file carrier regression (T107.5) --------------------------------------

const noFile = parseImportFormValues(fileValues());
check("T107.5 file carrier with no file still rejected locally", noFile.ok === false && Boolean(noFile.errors.file));
const file = new File([ascii(LIMIT + 1)], "big.csv", { type: "text/csv" });
const tooBig = parseImportFormValues({ ...fileValues(), file });
check("T107.5 file carrier over the byte cap still rejected locally", tooBig.ok === false && Boolean(tooBig.errors.file));
const wrongExt = parseImportFormValues({
  ...fileValues(),
  format: "xlsx",
  file: new File(["PK"], "x.csv", { type: "text/csv" }),
});
check(
  "T107.5 file carrier format=xlsx with a non-.xlsx name still rejected locally",
  wrongExt.ok === false && Boolean(wrongExt.errors.file),
  JSON.stringify(wrongExt.ok ? "accepted" : wrongExt.errors),
);

// --- T116 fingerprints -------------------------------------------------------

const base = readFileSync(join(HERE, "corpus", "F-01.txt"), "utf8");
const mutations = [
  ["first char", "X" + base.slice(1)],
  ["middle char", base.slice(0, 30) + (base[30] === "X" ? "Y" : "X") + base.slice(31)],
  ["last char", base.slice(0, -2) + "Z" + "\n"],
  ["extra trailing space", base.replace("\n", " \n")],
  ["removed space", base.replace("PowerEdge R750", "PowerEdgeR750")],
  ["CJK replacement", base.replace("Dell", "戴尔")],
  ["emoji replacement", base.replace("Dell", "🚀")],
];
for (const [label, mutated] of mutations) {
  check(
    `T116.1 fingerprint changes on ${label}`,
    mutated !== base && textImportTargetKey(mutated) !== textImportTargetKey(base),
  );
}
check("T116.2 identical text gives a stable fingerprint", textImportTargetKey(base) === textImportTargetKey(base));
check("T116.2 text fingerprint is tagged", textImportTargetKey(base).startsWith("text:csv:"));
const probeFile = new File([base], "x.csv", { type: "text/csv" });
const fileKey = fileImportTargetKey("csv", probeFile);
check("T116.2 file fingerprint is tagged", fileKey.startsWith("file:csv:"));
check(
  "T116.2 same bytes under the two carriers produce different fingerprints",
  fileKey !== textImportTargetKey(base),
  `${fileKey} vs ${textImportTargetKey(base)}`,
);
const trimTrio = ["a,b\n", "a,b \n", "a,b\n\n"].map(textImportTargetKey);
check(
  "T116.3 payload is not trimmed (three near-identical payloads differ)",
  new Set(trimTrio).size === 3,
  JSON.stringify(trimTrio),
);

mkdirSync(join(HERE, "logs"), { recursive: true });
lines.push("", `${failures} failures`);
writeFileSync(join(HERE, "logs", "boundary-check.log"), lines.join("\n") + "\n");
process.exit(failures === 0 ? 0 : 1);
