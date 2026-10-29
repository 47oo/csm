/**
 * 交互族 ④：CSV 文件 / 文本载体切换（F034 / F036；F043-C09–C10）。
 *
 * 层：P（纯逻辑：importCarrier.ts / importForm.ts）+ R（切换与校验不产生请求）。
 * 面板内的 `canConfirm` 门控（ResourceImportPanel.tsx 不可加载）以本文件镜像 +
 * C11 静态结构断言双重覆盖；镜像只复用 src 真实导出的 importTargetKey，
 * 不改写判定、不放宽为「不抛错即通过」。
 */
import assert from "node:assert/strict";

import {
  emptyImportFormValues,
  importCarrierPatch,
  importTargetKey,
  parseImportFormValues,
} from "../../src/components/importForm.ts";

const CSV_TEXT = "cluster,hostname,resource_type\nN96P,cn001,BARE_METAL\n";

export default async function register(h) {
  await h.test("C09 载体切换正例：切 text 强制 format=csv；切回 file 不回填且 file=null；两载体 importTargetKey 不等且非 null", async () => {
    const base = emptyImportFormValues();
    assert.deepEqual(base, { carrier: "file", format: "csv", file: null, text: "" });

    // xlsx 下切到文本载体 → 强制 csv（不提供 .xlsx 文本载体）
    assert.deepEqual(importCarrierPatch({ ...base, format: "xlsx" }, "text"), {
      carrier: "text",
      format: "csv",
    });
    assert.deepEqual(importCarrierPatch(base, "text"), { carrier: "text", format: "csv" });

    const textValues = { ...base, ...importCarrierPatch(base, "text"), text: CSV_TEXT };
    const textKey = importTargetKey(textValues);
    assert.ok(textKey !== null);
    assert.ok(textKey.startsWith("text:csv:"), textKey);

    // 切回文件载体：format 保留 csv、file 置 null（不回填历史 xlsx / 旧文件）
    assert.deepEqual(importCarrierPatch(textValues, "file"), {
      carrier: "file",
      format: "csv",
      file: null,
    });
    const fileOnly = { ...emptyImportFormValues(), format: "xlsx" };
    assert.deepEqual(importCarrierPatch(fileOnly, "file"), {
      carrier: "file",
      format: "xlsx",
      file: null,
    });

    const fileValues = {
      ...textValues,
      ...importCarrierPatch(textValues, "file"),
      file: new File([CSV_TEXT], "resources.csv", { type: "text/csv" }),
    };
    const fileKey = importTargetKey(fileValues);
    assert.ok(fileKey !== null);
    assert.ok(fileKey.startsWith("file:csv:"), fileKey);
    assert.notEqual(textKey, fileKey);
  });

  await h.test("C10 载体切换负例：切换后 validatedKey!==currentKey 且确认门控为 false；未校验/确认前 calls.length===0", async () => {
    const fileValues = {
      ...emptyImportFormValues(),
      file: new File([CSV_TEXT], "resources.csv", { type: "text/csv" }),
    };
    // 文件载体已预校验通过（validatedKey = 当次输入指纹）
    const validatedKey = importTargetKey(fileValues);
    assert.ok(validatedKey !== null);

    // 切到文本载体：当前输入指纹改变 ⇒ 既有预校验结果失效
    const switched = { ...fileValues, ...importCarrierPatch(fileValues, "text"), text: CSV_TEXT };
    const currentKey = importTargetKey(switched);
    assert.ok(currentKey !== null);
    assert.notEqual(validatedKey, currentKey);

    // 面板门控（镜像 ResourceImportPanel.tsx：validatePassed = error_count===0 &&
    // validatedKey!==null && validatedKey===currentKey）：失效项为 key 相等性
    const errorCount = 0;
    const validatePassed = errorCount === 0 && validatedKey !== null && validatedKey === currentKey;
    assert.equal(validatePassed, false);
    const importStateKind = "idle";
    const canConfirm = validatePassed && importStateKind !== "success";
    assert.equal(canConfirm, false);
    const busy = false;
    assert.equal(busy || !canConfirm, true); // 「确认导入」入口不可用（if (busy || !canConfirm) return）

    // 切换与本地解析都不发请求（未显式「校验 / 确认」）
    const parsed = parseImportFormValues(switched);
    assert.deepEqual(Object.keys(parsed), ["ok", "file"]);
    assert.equal(parsed.ok, true); // 解析只构造 File，不请求
    assert.equal(h.calls.length, 0);

    // 空文本（未选择内容）本地拦截，同样不发请求
    const blank = { ...switched, text: "   " };
    const blankParsed = parseImportFormValues(blank);
    assert.equal(blankParsed.ok, false);
    assert.ok(blankParsed.errors.text, "空文本应有本地错误");
    assert.equal(h.calls.length, 0);
  });
}
