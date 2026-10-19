/**
 * 二次确认对话框的一次性提交守卫（F020；docs/features/F020/architecture.md
 * DR-354/DR-363；Test Design F020-T06a–T06d）。
 *
 * 纯逻辑模块（无 JSX / React / API 依赖）：scripts/smoke-client.mjs 以 Node
 * type stripping 直接加载本模块做机制级冒烟（同 src/api/*.ts、
 * ./interfaceIpSelection.ts；ui/ConfirmDialog.tsx 含 JSX 无法被 Node 加载，
 * 故守卫逻辑独立成本模块）。
 *
 * 状态转换（DR-354）：
 * - tryBegin()：空闲 → true（占用，进入提交中）；占用期间重复调用
 *   （confirmLoading 回落前的双击 / 回车连发等重复确认）→ false，由调用方
 *   忽略重复派发（once-only，T06a）；
 * - settle()：一次提交结束（成功或失败，confirmLoading 回落）后释放守卫，
 *   允许用户再次手动触发；本模块不派发请求、不自动重试（T06c）；
 * - reset()：取消 / 关闭对话框时释放守卫，对话框重开后可再次提交（T06b）；
 * - 实例隔离：createConfirmCommitGuard() 每次调用返回独立实例，多个对话框
 *   的守卫互不影响（T06d）。
 */

/** 一次性提交守卫：占用 / 释放语义见模块头注释（DR-354）。 */
export interface ConfirmCommitGuard {
  /** 尝试开始一次提交：空闲 → true；已占用（未 settle / reset）→ false。 */
  tryBegin(): boolean;
  /** 提交结束（成功或失败）后释放；不派发、不自动重试（T06c）。 */
  settle(): void;
  /** 取消 / 关闭对话框时释放；对话框重开后可再次提交（T06b）。 */
  reset(): void;
  /** 当前是否占用（已派发提交且未释放）。 */
  isInFlight(): boolean;
}

/** 创建独立的一次性提交守卫实例（实例隔离，T06d）。 */
export function createConfirmCommitGuard(): ConfirmCommitGuard {
  let inFlight = false;
  return {
    tryBegin() {
      if (inFlight) {
        return false; // 重复派发：忽略（once-only，T06a）
      }
      inFlight = true;
      return true;
    },
    settle() {
      inFlight = false;
    },
    reset() {
      inFlight = false;
    },
    isInFlight() {
      return inFlight;
    },
  };
}
