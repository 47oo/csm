import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

/**
 * F021 / F023 静态 guard：IP 分配写入路径前端零业务校验 / 零 IP 变换
 * （§21 / AC-33；f021-ip-address-allocation-handoff.md Frontend Work
 * 「不做」清单：不做 IPv4 格式 / trim / 范围 / 占用预判）。
 *
 * 与组件探针（ipAddressAllocateDialog.spec.ts，形式 B）互补的防线，仿
 * F016 clusterFormNoClientValidation.spec.ts（形式 A）：
 *
 * 1. 脚本层 token：分配对话框剥离注释后不得出现 IPv4 校验 / 变换的已知
 *    等价写法（正则族、trim / 大小写折叠 / Unicode 归一化、数值解析、
 *    dotted-quad 拆分与点存在探测、前后缀检测）。
 * 2. 模板层属性：不得出现 maxlength / minlength / rules / :model /
 *    pattern 等可变相限制输入的模板属性（VTU setValue 绕过属性截断，
 *    行为探针对其天然失明）。
 * 3. 结构层白名单：分配对话框的 import 模块来源集合固定为显式白名单且无
 *    动态 import——「把校验封装进 helper 模块再 import」会立即失败而非
 *    静默绕过；接线页面不引用任何分配写函数（分配写入路径唯一化，防第二
 *    表单绕过）。
 *
 * 边界声明（必须先读）：本文件断言的是「前端未实现任何 IPv4 格式 / 范围 /
 * 占用 / 归一化业务裁决」，**不是**「这些取值在业务上合法」——非法 IPv4
 * （400 VALIDATION_ERROR）、范围外（409 OUT_OF_RANGE）、已占用
 * （409 DUPLICATE）、耗尽（409 NO_AVAILABLE_IP）、范围段不可用
 * （404 / 409 + IP_ADDRESS_RANGE_UNAVAILABLE）的唯一裁决方是服务端
 * （§21，f021 契约 §3 / §4）。
 *
 * 允许且仅允许三项非业务守卫：目标 NIC 与 ip_address 的基础必填（空值 =
 * 表单未完成，f021 handoff「基础必填 / 类型提示」）与 auto 模式
 * ip_address_range_id 的基础必选（空值 = 表单未完成，**F023 / AC-18
 * 产品裁定**：未选范围段不得提交；Empty 态禁用自动提交），其行为级断言见
 * 组件探针。若未来产品确认把更多检查前移到客户端，必须由产品决策同步
 * 修改本 guard 与组件，不得由实现方静默补校验。
 *
 * F023 制定的只读链（f023-ip-range-selection-handoff.md Frontend Work
 * 方案 1）为合法读取面：分配对话框允许 import getNetworkInterface /
 * getBareMetal / listIpAddressRanges，仅用于「选定 NIC → 解析宿主
 * BareMetal → 加载该 Cluster 活跃范围段」渲染下拉选项；它们不是分配
 * 预检（存在性 / 归属 / 余量仍由服务端在提交时独立裁决），其用途由
 * 下方位序精确的 import 名称集合断言钉死。占用预检（listIpAddresses /
 * getIpAddress）、按 id 预检所选范围段（getIpAddressRange）与直接
 * fetch 仍禁止。
 *
 * 本 guard 是静态最佳努力：token 无法穷尽未知语法（新方法名、helper 模块
 * 内部逻辑），行为级兜底是组件探针（非法格式 / 首尾空白 / 前导零 / 仅空白
 * 串均原样提交，提交被拦截 → 请求数变 0；body 被改变 → 逐字节比对失败）。
 * 两层互补，任何一层都不能单独声称穷尽。
 */

/** 分配写入路径的前端触点。 */
const DIALOG_FILE = 'src/components/IpAddressAllocateDialog.vue'
const PAGE_FILE = 'src/pages/IpAddressListPage.vue'

/**
 * 分配对话框允许 import 的模块来源集合（显式白名单）。任何新增模块
 * （如 utils/validateIpAddress 之类的校验 helper）都会使下方位序比对失败。
 * 合法新增依赖须连同本白名单一起、经有意识的变更（并重跑组件探针）才能进入。
 * F023 增量：新增 bareMetals / ipAddressRanges 两个只读客户端（方案 1
 * 只读链的组成成员，用途由下方 import 名称集合断言钉死）。
 */
const DIALOG_IMPORT_MODULE_WHITELIST = [
  '../api/bareMetals',
  '../api/http',
  '../api/ipAddressRanges',
  '../api/ipAddresses',
  '../api/networkInterfaces',
  '../types/api',
  'vue',
]

function readRaw(relative: string): string {
  return readFileSync(resolve(process.cwd(), relative), 'utf-8')
}

/**
 * 剥离注释后返回源码，供 token / 属性扫描。剥离按类进行：
 * 1. 块注释（非贪婪全文件匹配，含 JSDoc）；
 * 2. 模板 HTML 注释；
 * 3. 仅「整行」行注释（行首除空格 / 制表符外以行注释定界符开始）。
 *
 * 剥离器的前提（块 / HTML 注释起始定界符位于行首、行注释独占一行）由
 * 下方「注释剥离前提」用例固化为不变量，防止剥离器吞掉字符串字面量或
 * 把注释放进扫描范围（与 F016 guard 同一策略）。
 */
function readStripped(relative: string): string {
  return readRaw(relative)
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .replace(/<!--[\s\S]*?-->/g, '')
    .replace(/^[ \t]*\/\/[^\n]*/gm, '')
}

/**
 * 禁止出现的 IPv4 校验 / 变换 token（任一出现即失败，AC-33）。
 * 覆盖已知等价写法：正则执行与动态构造、字符串变换族（trim / 大小写
 * 折叠 / Unicode 归一化 / 本地化比较 / 替换）、IPv4 数值解析（范围 /
 * 占用预判的前置）、dotted-quad 拆分与点存在探测（格式预判）、前后缀
 * 检测。当前正确源码均不含以下任一 token；若未来某 token 与合法代码
 * 冲突，应改用更精确的写法而不是删除覆盖。
 */
const BANNED_TOKENS: ReadonlyArray<{ name: string; pattern: RegExp }> = [
  { name: '大小写折叠（toLowerCase / toUpperCase）', pattern: /toLowerCase|toUpperCase/ },
  { name: '首尾空白变换（trim）', pattern: /\.trim\s*\(/ },
  { name: 'Unicode 归一化（normalize）', pattern: /\.normalize\s*\(/ },
  { name: '本地化比较（localeCompare）', pattern: /localeCompare/ },
  { name: '前缀检测（startsWith）', pattern: /startsWith/ },
  { name: '后缀检测（endsWith）', pattern: /endsWith/ },
  { name: '正则执行（match）', pattern: /\.match\s*\(/ },
  { name: '正则执行（matchAll）', pattern: /\.matchAll\s*\(/ },
  { name: '正则执行（search）', pattern: /\.search\s*\(/ },
  { name: '字符串替换（replace）', pattern: /\.replace\s*\(/ },
  { name: '正则执行（test）', pattern: /\.test\s*\(/ },
  { name: '正则执行（exec）', pattern: /\.exec\s*\(/ },
  { name: '动态构造正则（RegExp）', pattern: /\bRegExp\s*\(/ },
  { name: '数值解析（parseInt）', pattern: /\bparseInt\b/ },
  { name: '数值解析（parseFloat）', pattern: /\bparseFloat\b/ },
  { name: 'dotted-quad 拆分（split(".")）', pattern: /\bsplit\s*\(\s*['"]\.['"]\s*\)/ },
  { name: '点存在探测（includes(".")）', pattern: /\.includes\s*\(\s*['"]\.['"]\s*\)/ },
]

/**
 * 模板层禁止出现的「变相限制输入」属性（与 F016 同一策略）。
 * maxlength / minlength：真实浏览器中截断人工输入，VTU setValue 绕过；
 * :rules / rules=：Element Plus 表单校验规则入口；:model：el-form 校验
 * 数据源；pattern：原生格式校验属性。
 */
const TEMPLATE_BANNED_TOKENS: ReadonlyArray<{ name: string; pattern: RegExp }> = [
  { name: '输入长度上限（maxlength / max-length / maxLength）', pattern: /\bmax-?length\b/i },
  { name: '输入长度下限（minlength / min-length / minLength）', pattern: /\bmin-?length\b/i },
  { name: 'el-form 校验规则（:rules）', pattern: /:rules\b/ },
  { name: '校验规则绑定（rules= / rules:）', pattern: /\brules\s*[:=]/ },
  { name: 'el-form 校验数据源（:model）', pattern: /:model\b/ },
  { name: '原生格式校验属性（pattern= / :pattern）', pattern: /(?:\bpattern\s*[:=]|:pattern\b)/i },
]

describe('F021 形式 A：IP 分配写入路径前端零业务校验 / 零 IP 变换（AC-33）', () => {
  it('分配对话框剥离注释后不含任何 IPv4 校验 / 变换 token（脚本层）', () => {
    const stripped = readStripped(DIALOG_FILE)
    const offenders: string[] = []
    for (const token of BANNED_TOKENS) {
      if (token.pattern.test(stripped)) offenders.push(token.name)
    }
    expect(offenders).toEqual([])
  })

  it('分配对话框的模板层不含可变相限制输入的属性（maxlength / minlength / rules / :model / pattern）', () => {
    const stripped = readStripped(DIALOG_FILE)
    const offenders: string[] = []
    for (const token of TEMPLATE_BANNED_TOKENS) {
      if (token.pattern.test(stripped)) offenders.push(token.name)
    }
    expect(offenders).toEqual([])
  })

  it('分配对话框不引用任何占用预检 / 范围段预检 / 无关读取 API，也不直接 fetch（分配地址的唯一来源是两个分配端点）', () => {
    const stripped = readStripped(DIALOG_FILE)
    const offenders: string[] = []
    // 占用 / 无关预检 API：IP 列表与按 id 读取 IP（占用预检）、按 id 读取
    // 范围段（对所选范围段的存在性 / 归属预检——选项渲染必须来自 F020
    // 列表端点，逐 id 预检属业务裁决前移）。F023 方案 1 只读链成员
    // （getNetworkInterface / getBareMetal / listIpAddressRanges，仅选项
    // 渲染用途）不在禁止之列，其用途由下方 import 名称集合断言钉死。
    for (const token of ['listIpAddresses', 'getIpAddress', 'getIpAddressRange', 'fetch(']) {
      if (stripped.includes(token)) offenders.push(token)
    }
    expect(offenders).toEqual([])
  })

  it("分配对话框从 '../api/ipAddresses' 的 import 名称集合恰为 {allocateIpAddress, allocateIpAddressManual, IpAddressRead}", () => {
    const stripped = readStripped(DIALOG_FILE)
    const names = new Set<string>()
    for (const match of stripped.matchAll(
      /import\s+(?:type\s+)?\{([^}]*)\}\s+from\s+['"]\.\.\/api\/ipAddresses['"]/g,
    )) {
      for (const name of match[1]!.split(',')) {
        const identifier = name.trim()
        if (identifier !== '') names.add(identifier)
      }
    }
    expect([...names].sort()).toEqual([
      'IpAddressRead',
      'allocateIpAddress',
      'allocateIpAddressManual',
    ])
  })

  it("分配对话框从 '../api/networkInterfaces' 的 import 名称集合恰为 {NetworkInterfaceRead, getNetworkInterface, listNetworkInterfaces}（F023 方案 1 只读链：选项渲染 + 解析宿主裸金属）", () => {
    const stripped = readStripped(DIALOG_FILE)
    const names = new Set<string>()
    for (const match of stripped.matchAll(
      /import\s+(?:type\s+)?\{([^}]*)\}\s+from\s+['"]\.\.\/api\/networkInterfaces['"]/g,
    )) {
      for (const name of match[1]!.split(',')) {
        const identifier = name.trim()
        if (identifier !== '') names.add(identifier)
      }
    }
    expect([...names].sort()).toEqual([
      'NetworkInterfaceRead',
      'getNetworkInterface',
      'listNetworkInterfaces',
    ])
  })

  it("分配对话框从 '../api/bareMetals' 的 import 名称集合恰为 {getBareMetal}（仅方案 1 只读链：宿主裸金属 → Cluster）", () => {
    const stripped = readStripped(DIALOG_FILE)
    const names = new Set<string>()
    for (const match of stripped.matchAll(
      /import\s+(?:type\s+)?\{([^}]*)\}\s+from\s+['"]\.\.\/api\/bareMetals['"]/g,
    )) {
      for (const name of match[1]!.split(',')) {
        const identifier = name.trim()
        if (identifier !== '') names.add(identifier)
      }
    }
    expect([...names].sort()).toEqual(['getBareMetal'])
  })

  it("分配对话框从 '../api/ipAddressRanges' 的 import 名称集合恰为 {IpAddressRangeRead, listIpAddressRanges}（仅方案 1 只读链：目标地址范围下拉选项；禁止 getIpAddressRange 预检）", () => {
    const stripped = readStripped(DIALOG_FILE)
    const names = new Set<string>()
    for (const match of stripped.matchAll(
      /import\s+(?:type\s+)?\{([^}]*)\}\s+from\s+['"]\.\.\/api\/ipAddressRanges['"]/g,
    )) {
      for (const name of match[1]!.split(',')) {
        const identifier = name.trim()
        if (identifier !== '') names.add(identifier)
      }
    }
    expect([...names].sort()).toEqual(['IpAddressRangeRead', 'listIpAddressRanges'])
  })

  it('分配对话框的 import 模块来源集合恰为显式白名单，且无动态 import / require（封堵 helper 绕过）', () => {
    const stripped = readStripped(DIALOG_FILE)
    const modules = new Set<string>()
    for (const match of stripped.matchAll(/from\s+['"]([^'"]+)['"]/g)) {
      modules.add(match[1]!)
    }
    expect([...modules].sort()).toEqual(DIALOG_IMPORT_MODULE_WHITELIST)
    // 静态 import 之外的模块获取通道一并封堵。
    expect(stripped).not.toMatch(/\bimport\s*\(/)
    expect(stripped).not.toMatch(/\brequire\s*\(/)
  })

  it('接线页面不引用任何分配写函数（分配写入路径唯一化：提交逻辑只存在于分配对话框）', () => {
    const stripped = readStripped(PAGE_FILE)
    const offenders: string[] = []
    for (const token of [
      'allocateIpAddress',
      'allocateIpAddressManual',
      'IpAddressAutoAllocateBody',
      'IpAddressManualAllocateBody',
    ]) {
      if (stripped.includes(token)) offenders.push(token)
    }
    expect(offenders).toEqual([])
  })

  it('提交按钮的 disabled 绑定仅依赖基础必填（目标 NIC / 空串 ip_address / auto 模式未选 ip_address_range_id），不做任何取值内容判断（行为级兜底见组件探针）', () => {
    const stripped = readStripped(DIALOG_FILE)
    // 基础必填的合法形态：networkInterfaceId === null、ipAddress === '' 与
    // （F023 / AC-18）ipAddressRangeId === null。任何基于取值内容的条件
    // （长度 / 格式 / 字符存在性）在此处或组件探针中失败。
    expect(stripped).toContain('form.networkInterfaceId === null')
    expect(stripped).toContain("form.ipAddress === ''")
    expect(stripped).toContain('form.ipAddressRangeId === null')
    // 禁用绑定中不出现对 ipAddress / ipAddressRangeId 的其它比较。
    const disabledBindings = stripped.match(/:disabled="[^"]*"/g) ?? []
    for (const binding of disabledBindings) {
      if (binding.includes('form.ipAddressRangeId')) {
        if (!binding.includes('form.ipAddressRangeId === null')) {
          throw new Error(`提交禁用绑定包含基础必填之外的 ip_address_range_id 判断：${binding}`)
        }
        continue
      }
      if (binding.includes('form.ipAddress') && !binding.includes("form.ipAddress === ''")) {
        throw new Error(`提交禁用绑定包含基础必填之外的 ip_address 判断：${binding}`)
      }
    }
  })

  it('注释剥离前提：所有注释定界符均位于行首，剥离不会吞掉活代码或字符串字面量', () => {
    const offenders: string[] = []
    for (const [index, line] of readRaw(DIALOG_FILE).split('\n').entries()) {
      const lineNumber = index + 1
      // 块注释起始定界符必须在行首（前面只有空白）。
      if (line.includes('/*') && !/^\s*\/\*/.test(line)) {
        offenders.push(`${DIALOG_FILE}:${lineNumber}: 行内块注释起始定界符`)
      }
      // HTML 注释起始定界符同理。
      if (line.includes('<!--') && !/^\s*<!--/.test(line)) {
        offenders.push(`${DIALOG_FILE}:${lineNumber}: 行内模板注释起始定界符`)
      }
      // 行注释必须独占一行。
      if (line.includes('//') && !/^\s*\/\//.test(line)) {
        offenders.push(`${DIALOG_FILE}:${lineNumber}: 行内双斜杠（行尾注释或字符串字面量）`)
      }
    }
    expect(offenders).toEqual([])
  })
})
