/**
 * 通过数报告原语（F043 architecture §3 / I-2）。
 *
 * 打印格式与原 smoke-client.mjs 收尾行**逐字节一致**（`\n<passed> passed,
 * <failed> failed`），只返回进程退出码：本模块（及 lib/ 全部文件）**不得**
 * 调用 process.exit —— 退出只发生在入口脚本层，否则 runner 与 smoke 无法复用
 * （ON-1 阻断）。
 */

/** 打印汇总并返回退出码（0 = 全通过；1 = 有失败）。 */
export function report({ passed, failed }) {
  console.log(`\n${passed} passed, ${failed} failed`);
  return failed > 0 ? 1 : 0;
}
