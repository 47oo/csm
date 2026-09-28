// 固定枚举本地模糊匹配单测（架构 F008 §4.2/§5.4，需求 §8.1/§8.2）：
// 中文展示名与英文代码均可匹配、英文不区分大小写、去首尾空格、
// rank 阶梯（完全 1 / 前缀 2 / 包含 4）、多目标取最小、同级稳定排序、空输入不过滤。
import { describe, expect, it } from 'vitest'
import { filterEnumOptions, match } from './enumSearch'

describe('match：中文展示名 / 英文代码匹配（§8.1/§8.2）', () => {
  it('命中中文展示名：完全 1 / 前缀 2 / 包含 4', () => {
    expect(match('裸金属', 'bare_metal', '裸金属')).toBe(1)
    expect(match('裸金属', 'bare_metal', '裸')).toBe(2)
    expect(match('裸金属', 'bare_metal', '金')).toBe(4)
    expect(match('裸金属', 'bare_metal', '铜')).toBeNull()
  })

  it('命中英文代码：不区分大小写', () => {
    expect(match('裸金属', 'bare_metal', 'bare_metal')).toBe(1)
    expect(match('裸金属', 'bare_metal', 'BARE_METAL')).toBe(1)
    expect(match('裸金属', 'bare_metal', 'bare')).toBe(2)
    expect(match('裸金属', 'bare_metal', 'Bare')).toBe(2)
    expect(match('裸金属', 'bare_metal', 'metal')).toBe(4)
    expect(match('空闲', 'IDLE', 'idle')).toBe(1)
  })

  it('多目标取最小 rank：label 包含(4) 与 code 前缀(2) → 2', () => {
    expect(match('运维查看者', 'viewer', 'view')).toBe(2)
    expect(match('运维查看者', 'viewer', '查看')).toBe(4)
  })

  it('去首尾空格；空输入（含仅空白）不匹配', () => {
    expect(match('裸金属', 'bare_metal', '  裸金属  ')).toBe(1)
    expect(match('裸金属', 'bare_metal', '  BARE_METAL ')).toBe(1)
    expect(match('裸金属', 'bare_metal', '')).toBeNull()
    expect(match('裸金属', 'bare_metal', '   ')).toBeNull()
  })

  it('% 与 _ 按普通字符处理（本地子串匹配，无 LIKE 语义）', () => {
    expect(match('a_b', 'code', 'a_b')).toBe(1)
    expect(match('a_b', 'code', 'a%b')).toBeNull()
  })
})

describe('filterEnumOptions：过滤 + rank 稳定排序', () => {
  const options = [
    { value: 'IDLE', label: '空闲' },
    { value: 'ALLOC', label: '已分配' },
    { value: 'DOWN', label: '宕机 / 不可用' },
    { value: 'UNKNOWN', label: '未知' },
  ]

  it('空输入（含仅空白）返回全部（= 初始候选）', () => {
    expect(filterEnumOptions(options, '')).toEqual(options)
    expect(filterEnumOptions(options, '   ')).toEqual(options)
  })

  it('中文展示名与英文代码均可命中', () => {
    expect(filterEnumOptions(options, '空闲').map((o) => o.value)).toEqual(['IDLE'])
    expect(filterEnumOptions(options, 'idle').map((o) => o.value)).toEqual(['IDLE'])
    // 「不」命中「宕机 / 不可用」的 label（包含）
    expect(filterEnumOptions(options, '不可用').map((o) => o.value)).toEqual(['DOWN'])
  })

  it('按 rank 排序：完全 > 前缀 > 包含；同级保持原顺序（稳定）', () => {
    // DOWN：code 完全(1)；IDLE：code 包含(4) → 完全在前
    expect(filterEnumOptions(options, 'D').map((o) => o.value)).toEqual(['DOWN', 'IDLE'])
    // UNKNOWN：code 前缀(2)
    expect(filterEnumOptions(options, 'UN').map((o) => o.value)).toEqual(['UNKNOWN'])
    // IDLE/ALLOC：均包含(4) → 保持原顺序
    expect(filterEnumOptions(options, 'L').map((o) => o.value)).toEqual(['IDLE', 'ALLOC'])
  })

  it('未命中任何选项返回空数组', () => {
    expect(filterEnumOptions(options, '不存在')).toEqual([])
  })
})
