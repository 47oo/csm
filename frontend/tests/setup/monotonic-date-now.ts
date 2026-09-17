/**
 * 测试环境时钟单调化（F004-T-01 根因修复）。
 *
 * ## 背景（缺陷 F004-T-01，MEDIUM）
 *
 * `tests/networkInterfaceListPage.spec.ts` 的登记用例曾出现非确定性失败：
 * 单文件约一半运行失败，失败用例在「401 / 提交中 / 400 / 登记成功」等之间漂移，
 * 均表现为点击提交 / 打开对话框后 `vi.waitFor` 轮询至超时（无 POST、无对话框）。
 *
 * ## 根因（在本机实测定位，非推测）
 *
 * 本开发机的系统时钟会周期性**向后跳变**（实测每 10~30 秒一次，每次
 * 0.5s ~ 2.5s；在 vitest 进程与独立 `node -e` 进程中均可用 2ms 采样看门狗
 * 复现，与测试框架无关，属宿主机 NTP/chrony 对快时钟的反复回拨校正）。
 *
 * 该跳变与两段库代码组合成静默吞点击的竞态：
 *
 * 1. Vue（runtime-dom `createInvoker`）为每个 DOM 事件监听 invoker 记录
 *    `attached = Date.now()`（创建时间），并在事件回调里做去重：
 *    `if (e._vts <= invoker.attached) return`（用于同帧 click+dblclick 去重，
 *    隐含「时钟单调递增」假设）；
 * 2. @vue/test-utils 的 `trigger()` 以 `event._vts = Date.now() + 1` 分发事件
 *    （VTU 为规避 fake timers 同毫秒问题加 1，同样假设时钟单调）。
 *
 * 当时钟在「invoker 创建（组件挂载）」与「trigger 点击」之间向后跳变超过
 * 1ms 时，`_vts（回拨后的 now+1）<= attached（回拨前的挂载时刻）`成立，
 * Vue 静默丢弃该点击 —— 无报错、无 POST、无渲染，随后用例的 waitForUi
 * 轮询 10s 超时失败。登记流程「对话框挂载 → 填表 1~2s → 点击」的窗口最长，
 * 命中概率最高，故失败集中在该 spec 并随跳变落点漂移。
 *
 * ## 修复
 *
 * 在测试进程内将 `Date.now()` 单调化：永远返回历史最大值。时钟正常时为
 * 恒等操作（不影响任何断言与时序）；时钟回拨期间冻结在已见最大值，直至
 * 真实时钟追平，使 Vue invoker 去重与 VTU `_vts` 的比较恢复「健康机器」
 * 语义。本修复不放宽任何超时、不重试、不跳过用例、不改变断言语义；
 * `src/**` 业务代码零改动。
 *
 * 幂等保护：vitest 每个测试文件隔离执行会重复加载本 setup，补丁带标记，
 * 重复应用时直接跳过。
 */

const MONOTONIC_NOW_FLAG = '__csmTestMonotonicDateNow'

const realDateNow: () => number = Date.now

if ((realDateNow as unknown as Record<string, unknown>)[MONOTONIC_NOW_FLAG] !== true) {
  let lastNow = realDateNow()
  const monotonicNow = (): number => {
    const current = realDateNow()
    if (current > lastNow) {
      lastNow = current
    }
    return lastNow
  }
  ;(monotonicNow as unknown as Record<string, unknown>)[MONOTONIC_NOW_FLAG] = true
  Date.now = monotonicNow
}
