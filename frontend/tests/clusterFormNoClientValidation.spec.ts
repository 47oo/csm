import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

/**
 * F016 静态 guard（Architecture Handoff「形式 A」）：Cluster 写入路径前端
 * 零业务校验 / 零名称变换（AC-05；§21 前后端职责边界）。
 *
 * 扫描 ClusterFormDialog.vue 与两个接线页面（剥离注释后）断言源码不含
 * 业务校验 / 变换 token；对 ClusterFormDialog.vue 另行断言不引用任何读 /
 * 预检 API、不直接 fetch，且从 ../api/clusters 的 import 名称集合恰为
 * {createCluster, updateCluster, ClusterRead}。
 *
 * 边界声明（必须先读）：本文件断言的是「前端未实现任何业务校验 / 变换」，
 * **不是**「空名 / 空白名 / 含斜杠名在业务上合法」——这些取值属
 * undefined_constraints（docs/api/f001-cluster.md §7），既不确认合法也
 * 不确认非法；斜杠禁令与活跃唯一性的唯一裁决方是后端 + 数据库（§21）。
 * 若产品未来确认把空串 / 首尾空白 / 长度升级为规则（f016 PROPOSED-3），
 * 必须由产品决策同步修改本 guard 与组件，不得由实现方静默补校验。
 *
 * 本 guard 是静态最佳努力（注释剥离后的 token 扫描）；行为级的权威保障
 * 是组件探针 clusterFormDialog.spec.ts（形式 B：空名可提交、原样字节提交、
 * 无预检 GET）。
 */

/** 被扫描文件（Cluster 写入路径的全部前端触点）。 */
const SCANNED_FILES = [
  'src/components/ClusterFormDialog.vue',
  'src/pages/ClusterListPage.vue',
  'src/pages/ClusterDetailPage.vue',
] as const

const DIALOG_FILE = 'src/components/ClusterFormDialog.vue'

/**
 * 剥离注释后返回源码：块注释、模板注释与行注释均不参与扫描，避免文档
 * 注释中「不检测斜杠、不做首尾空白处理」等措辞造成误报。被扫描文件中
 * 不存在含注释起止符的字符串字面量（已人工核对）。
 */
function readStripped(relative: string): string {
  const source = readFileSync(resolve(process.cwd(), relative), 'utf-8')
  return source
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .replace(/<!--[\s\S]*?-->/g, '')
    .replace(/\/\/[^\n]*/g, '')
}

/** 禁止出现的业务校验 / 名称变换 token（任一出现即失败，AC-05）。 */
const BANNED_TOKENS: ReadonlyArray<{ name: string; pattern: RegExp }> = [
  { name: '大小写折叠（toLowerCase / toUpperCase）', pattern: /toLowerCase|toUpperCase/ },
  { name: '首尾空白变换（trim）', pattern: /\.trim\s*\(/ },
  { name: 'Unicode 归一化（normalize）', pattern: /\.normalize\s*\(/ },
  { name: '本地化比较（localeCompare）', pattern: /localeCompare/ },
  { name: "斜杠检测（includes('/')）", pattern: /includes\s*\(\s*['"]\/['"]\s*\)/ },
  { name: "斜杠检测（indexOf('/')）", pattern: /indexOf\s*\(\s*['"]\/['"]\s*\)/ },
  { name: "斜杠检测（split('/')）", pattern: /\bsplit\s*\(\s*['"]\/['"]\s*\)/ },
  { name: '斜杠检测（正则字面量转义斜杠）', pattern: /\/\\\// },
]

describe('F016 形式 A：Cluster 写入路径前端零业务校验 / 变换（AC-05）', () => {
  it('三个触点文件剥离注释后均不含任何业务校验 / 名称变换 token', () => {
    const offenders: string[] = []
    for (const relative of SCANNED_FILES) {
      const stripped = readStripped(relative)
      for (const token of BANNED_TOKENS) {
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

  it('提交按钮的 disabled 绑定不依赖 form.name（REQUIRED #4；行为级兜底见组件探针「空名称可提交」）', () => {
    const stripped = readStripped(DIALOG_FILE)
    expect(stripped).not.toMatch(/:disabled="[^"]*form\.name/)
  })
})
