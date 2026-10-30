/**
 * `.tsx` 边界的静态结构断言（F043-C08 / C11 / C14；architecture §5 X1–X3）。
 *
 * 层：S（源文本结构）。Node ≥22.18 的 type stripping 无法加载 `.tsx`（无 JSX
 * transform），而 `react-dom/server` 渲染需 esbuild（明令不得直接使用），故
 * 这三项以**文本模式**断言接线存在，只断言模式命中、**不绑死行号**（R6）。
 *
 * R2：用例名强制 `[S-STATIC]` 后缀；本文件结果**不计入** A3 的可观察量列。
 * X4（App.tsx 处理器注册点）为 NOT TESTED，不在此断言、不记 PASS。
 */
import assert from "node:assert/strict";
import { readFileSync, readdirSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const SCRIPTS_DIR = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const SRC_DIR = path.join(path.dirname(SCRIPTS_DIR), "src");

/** 子串出现次数。 */
function countOf(text, needle) {
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

/** 递归列出 src 下的源文件（相对 src 的 posix 路径）。 */
function listSources(dir = SRC_DIR) {
  return readdirSync(dir, { recursive: true, withFileTypes: true })
    .filter((entry) => entry.isFile() && /\.(ts|tsx)$/.test(entry.name))
    .map((entry) => {
      const absolute = path.join(entry.parentPath ?? entry.path, entry.name);
      return { relative: path.relative(SRC_DIR, absolute).split(path.sep).join("/"), absolute };
    });
}

/** 读取 src 下的文件源文本。 */
function readSource(relative) {
  return readFileSync(path.join(SRC_DIR, relative), "utf8");
}

export default async function register(h) {
  await h.test("C08 409 后刷新接线：refreshAfterConflict 定义 + onRefresh 接线命中载体 >=8 [S-STATIC]", async () => {
    const definition = "function refreshAfterConflict()";
    const wiring = "onRefresh={refreshAfterConflict}";
    const carriers = listSources()
      .map((file) => file.relative)
      .filter((relative) => {
        const source = readSource(relative);
        return source.includes(definition) && source.includes(wiring);
      });
    assert.ok(
      carriers.length >= 8,
      `同时含「${definition}」与「${wiring}」的载体应 >=8，实际 ${carriers.length}：${carriers.join(", ")}`,
    );
    for (const relative of carriers) {
      const source = readSource(relative);
      assert.equal(countOf(source, definition), 1, `${relative} 的 ${definition} 应恰 1 次`);
    }
    assert.equal(h.calls.length, 0); // 静态族不发请求
  });

  await h.test("C11 单资源导入 canConfirm 门控：validatedKey/currentKey/error_count/success/提交拦截齐备 [S-STATIC]", async () => {
    const source = readSource("components/ResourceImportPanel.tsx");
    const patterns = [
      "validatedKey !== null",
      "validatedKey === currentKey",
      "error_count === 0",
      'importState.kind !== "success"',
      "if (busy || !canConfirm)",
    ];
    for (const pattern of patterns) {
      assert.ok(source.includes(pattern), `ResourceImportPanel.tsx 应含 ${pattern}`);
    }
    assert.equal(h.calls.length, 0);
  });

  await h.test("C14 ConfirmDialog 接线：提交态禁用遮罩/Esc/取消、危险语义、守卫接线（tryBegin/settle 各 1、reset 2）[S-STATIC]", async () => {
    const source = readSource("components/ui/ConfirmDialog.tsx");
    const patterns = [
      "maskClosable={!confirmLoading}",
      "keyboard={!confirmLoading}",
      "disabled: confirmLoading",
      "okButtonProps={{ danger }}",
    ];
    for (const pattern of patterns) {
      assert.ok(source.includes(pattern), `ConfirmDialog.tsx 应含 ${pattern}`);
    }
    for (const [call, expected] of [
      ["guardRef.current.tryBegin()", 1],
      ["guardRef.current.settle()", 1],
      // 源码实际 2 处：confirmLoading 回落后 settle、关闭（open=false）时 reset，
      // 以及 onCancel 内显式 reset（architecture §5 X1 记「各 1 次」与实际不符）
      ["guardRef.current.reset()", 2],
    ]) {
      assert.equal(countOf(source, call), expected, `${call} 应恰 ${expected} 次`);
    }
    assert.equal(h.calls.length, 0);
  });
}
