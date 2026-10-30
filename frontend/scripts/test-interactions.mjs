/**
 * F043 交互回归可重复入口（`npm run test:interactions`）。
 *
 * docs/features/F043/architecture.md §3/§7：
 * - 固定顺序、无并发、无时序依赖（A1）；连续两次运行结果一致；
 * - 入口链无第三方 import（react / react-dom / antd / esbuild 均不加载），
 *   `node_modules` 缺失时仍可执行（R4）；Node ≥22.18 的 type stripping 加载
 *   src 下无 JSX 的 .ts 纯逻辑与 client（R3：版本不足显式报错退出，不静默跳过）。
 * - `process.exit` 只在本入口（I-2）；`lib/report.mjs` 只返回退出码。
 *
 * 用例数期望 14 = C01..C14（§6）；静态族带 `[S-STATIC]` 后缀，不计入 A3
 * 可观察量列（R2）。X4 为 NOT TESTED，不在本入口断言。
 */
const MIN_NODE = [22, 18];

const [major, minor] = process.versions.node.split(".").map((part) => Number(part));
if (major < MIN_NODE[0] || (major === MIN_NODE[0] && minor < MIN_NODE[1])) {
  console.error(
    `test:interactions 需要 Node >= ${MIN_NODE.join(".")}（内置 TypeScript type stripping），` +
      `当前 ${process.versions.node}；请升级 Node 后重试（不静默跳过）。`,
  );
  process.exit(1);
}

// 版本校验通过后才加载 src 下 `.ts`（静态 import 会在校验前求值，故用动态 import）
const { createHarness } = await import("./lib/harness.mjs");
const { report } = await import("./lib/report.mjs");
const { setUnauthorizedHandler } = await import("../src/api/client.ts");

const harness = createHarness({ label: "F043 " });
setUnauthorizedHandler(() => {
  harness.countUnauthorized();
});

/** 固定顺序（§6 交互族顺序；无并发、无时序依赖）。 */
const REGISTRY = [
  "./interaction/candidate.mjs", // ① C01–C03
  "./interaction/auth.mjs", // ② C04–C05
  "./interaction/conflict.mjs", // ③ C06–C07
  "./interaction/importCarrier.mjs", // ④ C09–C10
  "./interaction/dangerousAction.mjs", // ⑤ C12–C13
  "./interaction/tsxBoundary.static.mjs", // S C08 / C11 / C14
];

for (const modulePath of REGISTRY) {
  const { default: register } = await import(modulePath);
  await register(harness);
}

setUnauthorizedHandler(null);
harness.restore();

process.exit(report({ passed: harness.passed, failed: harness.failed }));
