import { describe, expect, it } from 'vitest'
import {
  PASSWORD_POLICY_MESSAGE,
  USERNAME_RULE_MESSAGE,
  isProtectedAdmin,
  roleLabel,
  statusLabel,
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
