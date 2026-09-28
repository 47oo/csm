import { describe, expect, it } from 'vitest'
import {
  CLUSTER_CODE_RULE_MESSAGE,
  CLUSTER_NAME_RULE_MESSAGE,
  CLUSTER_PURPOSE_RULE_MESSAGE,
  PASSWORD_POLICY_MESSAGE,
  USERNAME_RULE_MESSAGE,
  clusterDeleteConfirmMatches,
  isProtectedAdmin,
  normalizeClusterCode,
  roleLabel,
  statusLabel,
  validateClusterCode,
  validateClusterName,
  validateClusterPurpose,
  validatePassword,
  validateUsername,
} from './validation'

describe('validateUsername（BQ-W/BQ-X：仅字母与数字、长度 1–128）', () => {
  it.each([
    'a',
    'A',
    'z0',
    'Admin01',
    'a'.repeat(128),
  ])('接受合法用户名 %s', (value) => {
    expect(validateUsername(value)).toBeNull()
  })

  it.each([
    '',
    ' ', // 空白
    'ab c', // 含空格
    'user_name', // 下划线
    'user-01', // 连字符
    '用户01', // 非 ASCII
    'user@example', // 特殊字符
    'a'.repeat(129), // 超长
  ])('拒绝非法用户名 %j', (value) => {
    expect(validateUsername(value)).toBe(USERNAME_RULE_MESSAGE)
  })
})

describe('validatePassword（§4.9.8：≥8 位且同时含字母与数字）', () => {
  it.each([
    'abcdefg1', // 恰好 8 位含字母数字
    'a1234567',
    'A1b2c3d4',
    'password2026',
    'x'.repeat(7) + '9', // 8 位，末位数字
  ])('接受合法口令 %s', (value) => {
    expect(validatePassword(value)).toBeNull()
  })

  it.each([
    '', // 空
    'ab1', // 过短
    'abcdefg', // 7 位纯字母
    '1234567', // 7 位纯数字
    'abcdefgh', // 8 位纯字母（无数字）
    '12345678', // 8 位纯数字（无字母）
    'abcdefg ', // 含空格且无数字
  ])('拒绝不满足策略的口令 %j', (value) => {
    expect(validatePassword(value)).toBe(PASSWORD_POLICY_MESSAGE)
  })
})

describe('内置管理员账号判定（BQ-Y：仅保护固定账号 admin，区分大小写）', () => {
  it('用户名 admin 为内置管理员账号', () => {
    expect(isProtectedAdmin('admin')).toBe(true)
  })

  it.each(['Admin', 'ADMIN', 'admin1', 'root', ''])('用户名 %j 不是内置管理员账号，可正常操作', (value) => {
    expect(isProtectedAdmin(value)).toBe(false)
  })
})

describe('角色与状态中文映射（Contract §5）', () => {
  it('角色映射为中文展示名', () => {
    expect(roleLabel('viewer')).toBe('运维查看者')
    expect(roleLabel('maintainer')).toBe('资源维护者')
    expect(roleLabel('admin')).toBe('平台管理员')
  })

  it('状态映射为中文展示名', () => {
    expect(statusLabel('enabled')).toBe('启用')
    expect(statusLabel('disabled')).toBe('禁用')
  })
})

// ---------- 集群（F001：需求 §4.1/§4.4、BQ-W/BQ-Z） ----------

describe('normalizeClusterCode（BQ-Z：去首尾空格 + 统一大写，与服务端一致）', () => {
  it('规范化 code', () => {
    expect(normalizeClusterCode('  n96p ')).toBe('N96P')
    expect(normalizeClusterCode('A01')).toBe('A01')
    expect(normalizeClusterCode('')).toBe('')
  })
})

describe('validateClusterCode（BQ-Z：规范化后 `^[A-Z0-9]{1,32}$`）', () => {
  it.each([
    'N96P',
    'A',
    '01',
    'n96p', // 规范化后合法（小写转大写）
    '  n96p  ', // 去首尾空格后合法
    'A'.repeat(32), // 恰好 32 位
  ])('接受合法 code %j', (value) => {
    expect(validateClusterCode(value)).toBeNull()
  })

  it.each([
    '',
    '   ', // 纯空白
    'AB-1', // 连字符
    'AB_1', // 下划线
    '集群01', // 中文
    'A B', // 含空格
    'A'.repeat(33), // 超长
  ])('拒绝非法 code %j', (value) => {
    expect(validateClusterCode(value)).toBe(CLUSTER_CODE_RULE_MESSAGE)
  })
})

describe('validateClusterName（BQ-W：仅字母/中文/下划线/数字，1–64，含空格直接拒绝）', () => {
  it.each([
    'N96P',
    '生产集群',
    'Prod_Cluster01',
    'abc', // 与 ABC 大小写不同，服务端区分大小写判重
    'ABC',
    '名'.repeat(64), // 恰好 64 个字符
  ])('接受合法名称 %j', (value) => {
    expect(validateClusterName(value)).toBeNull()
  })

  it.each([
    '',
    '生产 集群', // 中间空格：直接拒绝、不裁剪
    ' 生产集群', // 首空格
    '生产集群 ', // 尾空格
    '  ', // 纯空白
    'prod-cluster', // 连字符
    'prod.cluster', // 点号
    '名'.repeat(65), // 超长
  ])('拒绝非法名称 %j', (value) => {
    expect(validateClusterName(value)).toBe(CLUSTER_NAME_RULE_MESSAGE)
  })
})

describe('validateClusterPurpose（非空；架构 §8 PROPOSED-2：上限 200）', () => {
  it.each(['训练集群', '推理服务专用', 'a', '用'.repeat(200)])('接受合法用途', (value) => {
    expect(validateClusterPurpose(value)).toBeNull()
  })

  it.each(['', '   ', '用'.repeat(201)])('拒绝非法用途（空/纯空白/超长）', (value) => {
    expect(validateClusterPurpose(value)).toBe(CLUSTER_PURPOSE_RULE_MESSAGE)
  })
})

describe('clusterDeleteConfirmMatches（BQ-Z / Contract §2.5：输入名称或 code 匹配才可提交）', () => {
  const target = { code: 'N96P', name: '生产集群' }

  it.each([
    ['生产集群'], // 精确名称
    ['  生产集群  '], // 输入去首尾空格后匹配名称（Contract §2.5）
    ['生产集群 '], // 尾空格同样去首尾后匹配
    ['N96P'], // 精确 code
    ['n96p'], // code 大小写不敏感
    ['  n96p '], // code 去首尾空格 + 大小写不敏感
  ])('输入 %j 匹配，允许提交', (input) => {
    expect(clusterDeleteConfirmMatches(input, target)).toBe(true)
  })

  it.each([
    [''],
    ['   '],
    ['生产集群1'], // 名称多一个字符
    ['生产集'], // 名称少一个字符
    ['测试集群'], // 其它集群的名称
    ['TST1'], // 其它编号
  ])('输入 %j 不匹配，不允许提交', (input) => {
    expect(clusterDeleteConfirmMatches(input, target)).toBe(false)
  })

  it('名称匹配区分大小写（ABC ≠ abc）', () => {
    const english = { code: 'C01', name: 'ABC' }
    expect(clusterDeleteConfirmMatches('ABC', english)).toBe(true)
    expect(clusterDeleteConfirmMatches('abc', english)).toBe(false)
  })

  it('code 大小写不敏感（展示形态保留大小写，ADR-002）', () => {
    const lowercaseCode = { code: 'n96p', name: '生产集群' }
    expect(clusterDeleteConfirmMatches('N96P', lowercaseCode)).toBe(true)
    expect(clusterDeleteConfirmMatches('n96p', lowercaseCode)).toBe(true)
  })

  it('其它集群的名称/code 不匹配', () => {
    expect(clusterDeleteConfirmMatches('测试集群', target)).toBe(false)
    expect(clusterDeleteConfirmMatches('TST1', target)).toBe(false)
  })
})
