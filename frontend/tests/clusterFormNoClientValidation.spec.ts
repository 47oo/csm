import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

/**
 * F016 静态 guard（Architecture Handoff「形式 A」）：Cluster 写入路径前端
 * 零业务校验 / 零名称变换（AC-05；§21 前后端职责边界）。
 * 本文件含 F016 REV-1 / REV-4 的 follow-up 加固（见 docs/reviews/
 * f016-cluster-registration-ui.md）。
 *
 * 与组件探针（clusterFormDialog.spec.ts，形式 B）互补的三层防线：
 *
 * 1. 脚本层 token：三个触点文件剥离注释后不得出现业务校验 / 名称变换 /
 *    斜杠检测的**已知等价写法**（方法调用族、正则字面量、与 '/' 的比较、
 *    前后缀检测等）。可枚举语法在此失败最早、定位最准（REV-1 前半）。
 * 2. 模板层属性：三个触点文件不得出现 maxlength / minlength / rules /
 *    :rules / :model / pattern 等可变相限制输入的模板属性。**这是
 *    maxlength 类限制的唯一可失败保障**：VTU 的 setValue 直接写 DOM
 *    value、绕过属性截断，行为探针对它天然失明（REV-1 后半 / R-B）。
 * 3. 结构层白名单：ClusterFormDialog 的 import 模块来源集合固定为显式
 *    白名单且无动态 import——「把校验封装进 helper 模块再 import」会
 *    立即失败而非静默绕过（REV-4 前半）；两个接线页面不引用任何 Cluster
 *    写函数 / 写类型（Cluster 写入路径唯一化，防第二表单绕过）。
 *
 * 边界声明（必须先读）：本文件断言的是「前端未实现任何业务校验 / 变换」，
 * **不是**「空名 / 空白名 / 含斜杠名在业务上合法」——这些取值属
 * undefined_constraints（docs/api/f001-cluster.md §7），既不确认合法也
 * 不确认非法；斜杠禁令与活跃唯一性的唯一裁决方是后端 + 数据库（§21）。
 * 若产品未来确认把空串 / 首尾空白 / 长度升级为规则（f016 PROPOSED-3），
 * 必须由产品决策同步修改本 guard 与组件，不得由实现方静默补校验。
 *
 * 本 guard 是静态最佳努力：token 无法穷尽未知语法（新方法名、helper 模块
 * 内部逻辑），行为级兜底是组件探针（提交被拦截 → 写请求数变 0；body 被
 * 改变 → 逐字节比对失败）。两层互补，任何一层都不能单独声称穷尽。
 */

/** 被扫描文件（Cluster 写入路径的全部前端触点）。 */
const SCANNED_FILES = [
  'src/components/ClusterFormDialog.vue',
  'src/pages/ClusterListPage.vue',
  'src/pages/ClusterDetailPage.vue',
] as const

const DIALOG_FILE = 'src/components/ClusterFormDialog.vue'

const PAGE_FILES = ['src/pages/ClusterListPage.vue', 'src/pages/ClusterDetailPage.vue'] as const

/**
 * ClusterFormDialog 允许 import 的模块来源集合（REV-4 前半：显式白名单）。
 * 任何新增模块（如 utils/validateClusterName 之类的校验 helper）都会使
 * 下方位序比对失败，从而把「静默绕过」变成「立即失败」。合法新增依赖须
 * 连同本白名单一起、经有意识的变更（并重跑组件探针）才能进入。
 */
const DIALOG_IMPORT_MODULE_WHITELIST = ['../api/clusters', '../api/http', '../types/api', 'vue']

function readRaw(relative: string): string {
  return readFileSync(resolve(process.cwd(), relative), 'utf-8')
}

/**
 * 剥离注释后返回源码，供 token / 属性扫描。剥离按类进行：
 * 1. 块注释（非贪婪全文件匹配，含 JSDoc）；
 * 2. 模板 HTML 注释；
 * 3. 仅「整行」行注释（行首除空格 / 制表符外以行注释定界符开始）。
 *
 * REV-4 后半修正：原先剥离行注释的模式会匹配行内**任意位置**的双斜杠，
 * 从而把字符串 / 正则字面量中的双斜杠一并吞掉（例如 URL 字面量会被拦腰
 * 截断），既可能让被扫描内容失真、也可能把注释放进扫描范围。改为只剥
 * 离整行注释后，行内出现的任何双斜杠都原样保留。这对本用例足够的理由：
 * 被扫描文件中的注释**全部**是整行注释或块注释（无行尾注释），且该前提
 * 由下方「注释剥离前提」用例固化为不变量——若未来出现行尾注释或字符串
 * 内的双斜杠，guard 会显式失败并指出位置，而不是静默改变剥离行为。
 *
 * 块 / HTML 注释剥离仍为非贪婪全文件匹配，其唯一隐患是字符串字面量中出
 * 现块注释或 HTML 注释的**起始**定界符时，剥离器会把其后的活代码当作注
 * 释一并吞掉（即把校验代码藏进这种字符串以绕过扫描）。同样由「注释剥离
 * 前提」用例封堵：被扫描文件中两类起始定界符都必须位于行首（前面只有
 * 空白），剥离器因此不可能从字符串字面量中间开始吞。已知残余：多行模板
 * 字符串内部行首出现注释定界符的情形无法静态区分（当前文件无多行模板
 * 字符串），该路径由组件探针按行为兜底。
 */
function readStripped(relative: string): string {
  return readRaw(relative)
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .replace(/<!--[\s\S]*?-->/g, '')
    .replace(/^[ \t]*\/\/[^\n]*/gm, '')
}

/**
 * 禁止出现的业务校验 / 名称变换 token（任一出现即失败，AC-05；REV-1 加固）。
 * 覆盖已知等价写法：字符串方法族（前后缀 / 字符位 / 查找 / 替换）、正则
 * 执行族、动态正则构造、正则字面量中的转义斜杠与斜杠字符类、以及与
 * '/' 的比较 / switch 分支。当前正确源码均不含以下任一 token（已逐一
 * 核对，见各用例）；若未来某 token 与合法代码冲突，应改用更精确的写法
 * 而不是删除覆盖。
 */
const BANNED_TOKENS: ReadonlyArray<{ name: string; pattern: RegExp }> = [
  { name: '大小写折叠（toLowerCase / toUpperCase）', pattern: /toLowerCase|toUpperCase/ },
  { name: '首尾空白变换（trim）', pattern: /\.trim\s*\(/ },
  { name: 'Unicode 归一化（normalize）', pattern: /\.normalize\s*\(/ },
  { name: '本地化比较（localeCompare）', pattern: /localeCompare/ },
  { name: '前缀检测（startsWith）', pattern: /startsWith/ },
  { name: '后缀检测（endsWith）', pattern: /endsWith/ },
  {
    name: '按字符位取值（charAt / charCodeAt / codePointAt）',
    pattern: /\.(?:charAt|charCodeAt|codePointAt)\b/,
  },
  { name: '正则执行（match）', pattern: /\.match\s*\(/ },
  { name: '正则执行（matchAll）', pattern: /\.matchAll\s*\(/ },
  { name: '正则执行（search）', pattern: /\.search\s*\(/ },
  { name: '字符串替换（replace）', pattern: /\.replace\s*\(/ },
  { name: '正则执行（test）', pattern: /\.test\s*\(/ },
  { name: '正则执行（exec）', pattern: /\.exec\s*\(/ },
  { name: '动态构造正则（RegExp）', pattern: /\bRegExp\s*\(/ },
  { name: "斜杠检测（includes('/')）", pattern: /includes\s*\(\s*['"]\/['"]\s*\)/ },
  { name: "斜杠检测（indexOf('/')）", pattern: /indexOf\s*\(\s*['"]\/['"]\s*\)/ },
  { name: "斜杠检测（lastIndexOf('/')）", pattern: /lastIndexOf\s*\(\s*['"]\/['"]\s*\)/ },
  { name: "斜杠检测（split('/')）", pattern: /\bsplit\s*\(\s*['"]\/['"]\s*\)/ },
  {
    name: '斜杠检测（正则字面量中的转义斜杠）',
    pattern: /\\\//,
  },
  { name: '斜杠检测（正则字符类 [/]）', pattern: /\[\/\]/ },
  {
    name: "与 '/' 的比较（== / === / != / !==，正向与反向）",
    pattern: /(?:={2,3}|!=)\s*['"`]\/['"`]|['"`]\/['"`]\s*(?:={2,3}|!=)/,
  },
  { name: "switch 分支匹配 '/'（case '/'）", pattern: /case\s*['"`]\/['"`]/ },
]

/**
 * 模板层禁止出现的「变相限制输入」属性（REV-1 后半：maxlength / rules
 * 不进 script、token 扫描天然盲区，必须单独断言模板属性）。
 *
 * - maxlength / minlength（含驼峰与连字符变体）：真实浏览器中截断人工
 *   输入；VTU setValue 绕过截断，探针无法感知——本断言是其唯一出路；
 * - :rules / rules= / rules:（含 v-bind 对象展开）：Element Plus 表单
 *   校验规则入口；与 :model 组合构成完整校验装配，禁 rules 即同时封掉
 *   「:model + rules」组合；
 * - :model：el-form 校验数据源，在 ClusterFormDialog 中无校验之外的
 *   用途，出现即视为校验装配的前置步骤；
 * - pattern / :pattern：原生格式校验属性（el-input 透传到内部 input）。
 *
 * 注：el-form-item 的 required 星标（纯视觉，NQ-3）未列入——本对话框提
 * 交走 footer 按钮点击而非原生表单 submit，required 单独出现不构成拦截；
 * 且 defineModel({ required: true }) 会使粗粒度 token 误报。若未来引入
 * 原生 form submit 路径，须重新评估。
 */
const TEMPLATE_BANNED_TOKENS: ReadonlyArray<{ name: string; pattern: RegExp }> = [
  { name: '输入长度上限（maxlength / max-length / maxLength）', pattern: /\bmax-?length\b/i },
  { name: '输入长度下限（minlength / min-length / minLength）', pattern: /\bmin-?length\b/i },
  { name: 'el-form 校验规则（:rules）', pattern: /:rules\b/ },
  { name: '校验规则绑定（rules= / rules:）', pattern: /\brules\s*[:=]/ },
  { name: 'el-form 校验数据源（:model）', pattern: /:model\b/ },
  { name: '原生格式校验属性（pattern= / :pattern）', pattern: /(?:\bpattern\s*[:=]|:pattern\b)/i },
]

describe('F016 形式 A：Cluster 写入路径前端零业务校验 / 变换（AC-05）', () => {
  it('三个触点文件剥离注释后均不含任何业务校验 / 名称变换 token（REV-1 脚本层）', () => {
    const offenders: string[] = []
    for (const relative of SCANNED_FILES) {
      const stripped = readStripped(relative)
      for (const token of BANNED_TOKENS) {
        if (token.pattern.test(stripped)) offenders.push(`${relative}: ${token.name}`)
      }
    }
    expect(offenders).toEqual([])
  })

  it('三个触点文件的模板层均不含可变相限制输入的属性（REV-1 模板层：maxlength / minlength / rules / :model / pattern）', () => {
    const offenders: string[] = []
    for (const relative of SCANNED_FILES) {
      const stripped = readStripped(relative)
      for (const token of TEMPLATE_BANNED_TOKENS) {
        if (token.pattern.test(stripped)) offenders.push(`${relative}: ${token.name}`)
      }
    }
    expect(offenders).toEqual([])
  })

  it('ClusterFormDialog 不引用任何读 / 预检 API，也不直接 fetch（REQUIRED #5：唯一允许的调用是 createCluster / updateCluster）', () => {
    const stripped = readStripped(DIALOG_FILE)
    const offenders: string[] = []
    // 读 / 预检 API：列表（重名预检）、按 id / 按名称读取（存在性预检）。
    for (const token of ['listClusters', 'getClusterByName', 'getCluster', 'fetch(']) {
      if (stripped.includes(token)) offenders.push(token)
    }
    expect(offenders).toEqual([])
  })

  it("ClusterFormDialog 从 '../api/clusters' 的 import 名称集合恰为 {createCluster, updateCluster, ClusterRead}", () => {
    const stripped = readStripped(DIALOG_FILE)
    const names = new Set<string>()
    for (const match of stripped.matchAll(
      /import\s+(?:type\s+)?\{([^}]*)\}\s+from\s+['"]\.\.\/api\/clusters['"]/g,
    )) {
      for (const name of match[1]!.split(',')) {
        const identifier = name.trim()
        if (identifier !== '') names.add(identifier)
      }
    }
    expect([...names].sort()).toEqual(['ClusterRead', 'createCluster', 'updateCluster'])
  })

  it('ClusterFormDialog 的 import 模块来源集合恰为显式白名单，且无动态 import / require（REV-4 前半：封堵 helper 绕过）', () => {
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

  it('两个接线页面不引用任何 Cluster 写函数 / 写类型（写入路径唯一化：提交逻辑只存在于 ClusterFormDialog）', () => {
    const offenders: string[] = []
    for (const relative of PAGE_FILES) {
      const stripped = readStripped(relative)
      for (const token of ['createCluster', 'updateCluster', 'ClusterWriteBody']) {
        if (stripped.includes(token)) offenders.push(`${relative}: ${token}`)
      }
    }
    expect(offenders).toEqual([])
  })

  it('提交按钮的 disabled 绑定不依赖 form.name（REQUIRED #4；行为级兜底见组件探针「空名称可提交」）', () => {
    const stripped = readStripped(DIALOG_FILE)
    expect(stripped).not.toMatch(/:disabled="[^"]*form\.name/)
  })

  it('注释剥离前提（REV-4 后半）：所有注释定界符均位于行首，剥离不会吞掉活代码或字符串字面量', () => {
    const offenders: string[] = []
    for (const relative of SCANNED_FILES) {
      for (const [index, line] of readRaw(relative).split('\n').entries()) {
        const lineNumber = index + 1
        // 块注释起始定界符必须在行首（前面只有空白）：否则非贪婪剥离可能
        // 从字符串字面量中间开始吞掉其后的活代码（静默绕过通道）。
        if (line.includes('/*') && !/^\s*\/\*/.test(line)) {
          offenders.push(`${relative}:${lineNumber}: 行内块注释起始定界符`)
        }
        // HTML 注释起始定界符同理。
        if (line.includes('<!--') && !/^\s*<!--/.test(line)) {
          offenders.push(`${relative}:${lineNumber}: 行内模板注释起始定界符`)
        }
        // 行注释必须独占一行：保证「只剥整行」策略剥离的内容恰为注释本身，
        // 行尾注释（或字符串内的双斜杠）会让被扫描内容失真 / 混入注释文本。
        if (line.includes('//') && !/^\s*\/\//.test(line)) {
          offenders.push(`${relative}:${lineNumber}: 行内双斜杠（行尾注释或字符串字面量）`)
        }
      }
    }
    expect(offenders).toEqual([])
  })
})
