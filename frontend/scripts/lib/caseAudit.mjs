/**
 * F043 用例台账审计（docs/features/F043/architecture.md §4 / F043-S02）。
 *
 * 只读扫描被审计脚本的用例登记点，把「逐文件计数白名单 + 用例名摘要 + skip /
 * 注释停用扫描」落成 scripts/lib/case-ledger.json 台账，用于证明 smoke 拆分
 * 没有静默删除、改名、重排或停用既有用例（ON-2 / ON-3 / R5）。
 *
 * 判据：
 * - counts：逐文件 `await test(` 登记点计数，必须与台账**相等**，总和 = 台账 total；
 * - digest：按出现顺序连接用例名的 sha256（顺序敏感，改名 / 删除 / 重排即变）；
 * - digest_sorted：用例名排序后连接的 sha256（集合敏感的辅助判据）；
 * - skip_hits：skip / only 型登记点与注释停用扫描命中数，必须为 0。
 *
 * 用法：
 *   node scripts/lib/caseAudit.mjs --emit   # 采基线并写台账（实现首步，此后只读）
 *   node scripts/lib/caseAudit.mjs          # 只读审计当前文件与台账是否一致
 * 退出码：0 = 一致；1 = 不一致（打印每项差异）。无第三方依赖、无 process.exit。
 */
import { createHash } from "node:crypto";
import { readFileSync, writeFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

/** scripts 目录（台账中的路径以此目录的父目录为基准，形如 `scripts/x.mjs`）。 */
const LIB_DIR = path.dirname(fileURLToPath(import.meta.url));
const SCRIPTS_DIR = path.dirname(LIB_DIR);
const FRONTEND_DIR = path.dirname(SCRIPTS_DIR);

/** 台账路径（本文件同级）。 */
export const LEDGER_PATH = path.join(LIB_DIR, "case-ledger.json");

/** 被审计文件白名单（I-3：台账只覆盖既有 smoke；交互族不进台账）。 */
export const AUDITED_FILES = ["scripts/smoke-client.mjs"];

/** 用例登记点前缀（既有 smoke 的顶层登记形式）。 */
const CALL = "await test(";

/** skip / only 型登记点（源码命中即算停用；注释中的命中由掩码比对补充）。 */
const SKIP_MARKERS = [
  { id: "test.skip", re: /\btest\.skip\s*\(/g },
  { id: "test.only", re: /\btest\.only\s*\(/g },
  { id: "describe.skip", re: /\bdescribe\.skip\s*\(/g },
  { id: "xit", re: /\bxit\s*\(/g },
];

/**
 * 注释 / 字符串掩码：返回与源码等长的文本，注释内容替换为空格（保留换行与偏移）。
 * 用于把「真实登记点」与「注释内 / 字符串内的 await test(」区分开（不靠行号，R6）。
 */
export function maskCommentsAndStrings(source) {
  const masked = source.split("");
  let state = "code";
  let index = 0;
  while (index < source.length) {
    const char = source[index];
    const next = source[index + 1];
    if (state === "code") {
      if (char === "/" && next === "/") {
        state = "line";
        masked[index] = " ";
        masked[index + 1] = " ";
        index += 2;
        continue;
      }
      if (char === "/" && next === "*") {
        state = "block";
        masked[index] = " ";
        masked[index + 1] = " ";
        index += 2;
        continue;
      }
      if (char === '"') {
        state = "double";
      } else if (char === "'") {
        state = "single";
      } else if (char === "`") {
        state = "template";
      }
      index += 1;
      continue;
    }
    if (state === "line") {
      if (char === "\n") {
        state = "code";
        index += 1;
        continue;
      }
      masked[index] = " ";
      index += 1;
      continue;
    }
    if (state === "block") {
      if (char === "*" && next === "/") {
        masked[index] = " ";
        masked[index + 1] = " ";
        state = "code";
        index += 2;
        continue;
      }
      if (char !== "\n") {
        masked[index] = " ";
      }
      index += 1;
      continue;
    }
    // 字符串内部（不掩码：用例名需要读取原文）
    if (char === "\\") {
      index += 2;
      continue;
    }
    if (
      (state === "double" && char === '"') ||
      (state === "single" && char === "'") ||
      (state === "template" && char === "`")
    ) {
      state = "code";
    }
    index += 1;
  }
  return masked.join("");
}

/** 子串出现次数。 */
function countOccurrences(text, needle) {
  let count = 0;
  let cursor = 0;
  while (true) {
    const at = text.indexOf(needle, cursor);
    if (at < 0) {
      return count;
    }
    count += 1;
    cursor = at + needle.length;
  }
}

/** sha256 十六进制。 */
function sha256(text) {
  return createHash("sha256").update(text, "utf8").digest("hex");
}

/**
 * 解析源文本 `index` 起始处的字符串字面量（"…" / '…' / `…`）。
 * 反引号模板含 `${` 时返回 unsupported（避免把插值当字面量改名判据）。
 */
function parseStringLiteral(source, index) {
  const quote = source[index];
  if (quote !== '"' && quote !== "'" && quote !== "`") {
    return null;
  }
  const escapes = { n: "\n", t: "\t", r: "\r", "\\": "\\", '"': '"', "'": "'", "`": "`" };
  let value = "";
  let cursor = index + 1;
  while (cursor < source.length) {
    const char = source[cursor];
    if (char === "\\") {
      const next = source[cursor + 1] ?? "";
      value += next in escapes ? escapes[next] : next;
      cursor += 2;
      continue;
    }
    if (quote === "`" && char === "$" && source[cursor + 1] === "{") {
      return null;
    }
    if (char === quote) {
      return { value };
    }
    value += char;
    cursor += 1;
  }
  return null;
}

/** 提取用例名（按出现顺序，只取代码态登记点）；非字符串首参返回 null 占位。 */
export function readCaseNames(source) {
  const code = maskCommentsAndStrings(source);
  const names = [];
  let cursor = 0;
  while (true) {
    const at = code.indexOf(CALL, cursor);
    if (at < 0) {
      break;
    }
    let start = at + CALL.length;
    while (start < source.length && /\s/.test(source[start])) {
      start += 1;
    }
    cursor = at + CALL.length;
    const literal = parseStringLiteral(source, start);
    names.push(literal === null ? null : literal.value);
  }
  return names;
}

/** 统计 skip / only 登记点与「注释停用」命中（期望 0）。 */
export function scanSkipPatterns(source) {
  const code = maskCommentsAndStrings(source);
  const hits = [];
  for (const { id, re } of SKIP_MARKERS) {
    const count = (source.match(new RegExp(re.source, "g")) ?? []).length;
    if (count > 0) {
      hits.push({ id, count });
    }
  }
  const disabledRegistrations = countOccurrences(source, CALL) - countOccurrences(code, CALL);
  if (disabledRegistrations > 0) {
    hits.push({ id: "commented-out-registration", count: disabledRegistrations });
  }
  return hits;
}

/** 摘要台账（顺序摘要 + 排序摘要）。 */
export function digestNames(names) {
  const plain = names.map((name) => (name === null ? "\u0000<non-literal>" : name));
  return {
    digest: sha256(plain.join("\n")),
    digest_sorted: sha256([...plain].sort().join("\n")),
  };
}

/** 采集一份台账快照（不写盘）。 */
export function capture(filePaths = AUDITED_FILES) {
  const counts = {};
  const problems = [];
  let total = 0;
  const allNames = [];
  let skipHits = 0;
  const skipDetail = [];
  for (const relativePath of filePaths) {
    const source = readFileSync(path.join(FRONTEND_DIR, relativePath), "utf8");
    const names = readCaseNames(source);
    counts[relativePath] = names.length;
    total += names.length;
    allNames.push(...names);
    const hits = scanSkipPatterns(source);
    skipDetail.push(...hits.map((hit) => ({ file: relativePath, ...hit })));
    skipHits += hits.reduce((sum, hit) => sum + hit.count, 0);
    const missing = names.filter((name) => name === null).length;
    if (missing > 0) {
      problems.push(`${relativePath}: ${missing} 处登记点首参不是字符串字面量`);
    }
  }
  const { digest, digest_sorted: digestSorted } = digestNames(allNames);
  return {
    counts,
    total,
    digest,
    digest_sorted: digestSorted,
    skip_hits: skipHits,
    skip_detail: skipDetail,
    problems,
  };
}

/** 写台账（--emit；只写 LEDGER_PATH）。 */
export function emit(filePaths = AUDITED_FILES) {
  const snapshot = capture(filePaths);
  const ledger = {
    feature: "F043",
    generated_by: "node scripts/lib/caseAudit.mjs --emit",
    scope: [...filePaths],
    counts: snapshot.counts,
    total: snapshot.total,
    digest_algo: 'sha256(names.join("\\n"))',
    digest: snapshot.digest,
    digest_sorted: snapshot.digest_sorted,
    skip_hits: snapshot.skip_hits,
    node: process.version,
  };
  writeFileSync(LEDGER_PATH, `${JSON.stringify(ledger, null, 2)}\n`, "utf8");
  return { ledger, snapshot };
}

/** 只读审计：当前文件 vs 台账。返回 {ok, problems, observed}。 */
export function audit(ledgerPath = LEDGER_PATH) {
  const ledger = JSON.parse(readFileSync(ledgerPath, "utf8"));
  const observed = capture(ledger.scope);
  const problems = [...observed.problems];
  for (const [relativePath, expected] of Object.entries(ledger.counts)) {
    const actual = observed.counts[relativePath] ?? 0;
    if (actual !== expected) {
      problems.push(`${relativePath}: 登记点 ${actual}，台账 ${expected}`);
    }
  }
  if (observed.total !== ledger.total) {
    problems.push(`总计 ${observed.total}，台账 ${ledger.total}`);
  }
  if (observed.digest !== ledger.digest) {
    problems.push(`名称顺序摘要 ${observed.digest.slice(0, 12)}，台账 ${ledger.digest.slice(0, 12)}`);
  }
  if (observed.digest_sorted !== ledger.digest_sorted) {
    problems.push(
      `名称集合摘要 ${observed.digest_sorted.slice(0, 12)}，台账 ${ledger.digest_sorted.slice(0, 12)}（基线名称集合须 ⊆ 当前集合）`,
    );
  }
  if (observed.skip_hits !== 0) {
    problems.push(`skip / 注释停用命中 ${observed.skip_hits} 处：${JSON.stringify(observed.skip_detail)}`);
  }
  return { ok: problems.length === 0, problems, observed, ledger };
}

/** CLI 入口（导入本模块无副作用）。 */
const isMain = process.argv[1] !== undefined && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url);
if (isMain) {
  if (process.argv.includes("--emit")) {
    const { ledger, snapshot } = emit();
    console.log(
      `caseAudit --emit: ${JSON.stringify(ledger.counts)} total=${ledger.total} ` +
        `digest=${ledger.digest} (prefix ${ledger.digest.slice(0, 8)}) ` +
        `sorted=${ledger.digest_sorted} skip_hits=${ledger.skip_hits} → ${LEDGER_PATH}`,
    );
    if (snapshot.problems.length > 0) {
      console.error(snapshot.problems.join("\n"));
      process.exitCode = 1;
    }
  } else {
    const result = audit();
    if (result.ok) {
      console.log(
        `caseAudit: OK ${JSON.stringify(result.observed.counts)} total=${result.observed.total} ` +
          `digest=${result.observed.digest} skip_hits=0`,
      );
    } else {
      console.error("caseAudit: MISMATCH");
      for (const problem of result.problems) {
        console.error(`  - ${problem}`);
      }
      process.exitCode = 1;
    }
  }
}
