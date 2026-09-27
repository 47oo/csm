// IPv4/CIDR 工具单测：数值解析、规范化（主机位归零）、边界前缀（/0、/31、/32）
// 与数值比较（需求 §5、架构 F005 §4.2/§4.8）。
import { describe, expect, it } from 'vitest'
import { intToIpv4, ipIntInCidr, ipv4ToInt, parseIpv4Cidr } from './ip'

describe('ipv4ToInt / intToIpv4', () => {
  it('合法点分十进制 → 数值', () => {
    expect(ipv4ToInt('0.0.0.0')).toBe(0)
    expect(ipv4ToInt('192.168.1.10')).toBe(3232235786)
    expect(ipv4ToInt('255.255.255.255')).toBe(4294967295)
  })

  it.each([
    '256.1.1.1', // 段越界
    '1.2.3', // 缺段
    '1.2.3.4.5', // 多段
    'a.b.c.d', // 非数字
    '01.2.3.4', // 前导零（与服务端 ipaddress 一致拒绝）
    '1.2.3.4 ', // 含空格（严格格式）
    ' 1.2.3.4',
    '1..3.4',
    '', // 空串
  ])('非法输入 %s → null', (input) => {
    expect(ipv4ToInt(input)).toBeNull()
  })

  it('intToIpv4 与 ipv4ToInt 互逆', () => {
    expect(intToIpv4(3232235786)).toBe('192.168.1.10')
    expect(intToIpv4(0)).toBe('0.0.0.0')
    expect(intToIpv4(4294967295)).toBe('255.255.255.255')
    expect(ipv4ToInt(intToIpv4(168430090))).toBe(168430090)
  })
})

describe('parseIpv4Cidr（规范化：主机位归零；前缀 /0–/32）', () => {
  it('网络地址输入原样规范化', () => {
    const parsed = parseIpv4Cidr('192.168.1.0/24')
    expect(parsed).not.toBeNull()
    expect(parsed?.normalized).toBe('192.168.1.0/24')
    expect(parsed?.networkInt).toBe(ipv4ToInt('192.168.1.0'))
    expect(parsed?.broadcastInt).toBe(ipv4ToInt('192.168.1.255'))
    expect(parsed?.prefix).toBe(24)
  })

  it('带主机位输入归一化为网络地址（如 192.168.1.5/24 → 192.168.1.0/24）', () => {
    const parsed = parseIpv4Cidr('192.168.1.5/24')
    expect(parsed?.normalized).toBe('192.168.1.0/24')
    expect(parsed?.networkInt).toBe(ipv4ToInt('192.168.1.0'))
  })

  it('边界前缀：/0、/31、/32', () => {
    const zero = parseIpv4Cidr('10.0.0.0/0')
    expect(zero?.normalized).toBe('0.0.0.0/0')
    expect(zero?.networkInt).toBe(0)
    expect(zero?.broadcastInt).toBe(4294967295)

    const p2p = parseIpv4Cidr('10.0.0.0/31')
    expect(p2p?.networkInt).toBe(ipv4ToInt('10.0.0.0'))
    expect(p2p?.broadcastInt).toBe(ipv4ToInt('10.0.0.1'))

    const host = parseIpv4Cidr('10.0.0.7/32')
    expect(host?.networkInt).toBe(ipv4ToInt('10.0.0.7'))
    expect(host?.broadcastInt).toBe(ipv4ToInt('10.0.0.7'))
  })

  it.each([
    '192.168.1.0', // 无前缀
    '/24', // 无地址
    '192.168.1.0/', // 空前缀
    '192.168.1.0/33', // 前缀越界
    '192.168.1.0/abc', // 前缀非数字
    'fd00::/8', // IPv6 拒绝
    '::1/128',
    '192.168.1.0/24 ', // 含空格
    '256.0.0.0/8', // 地址非法
    '', // 空串
  ])('非法 CIDR %s → null', (input) => {
    expect(parseIpv4Cidr(input)).toBeNull()
  })
})

describe('ipIntInCidr（数值比较：含网络/广播端点）', () => {
  const cidr = parseIpv4Cidr('192.168.1.0/24')!
  const ip = (value: string): number => ipv4ToInt(value)!

  it('网络地址与广播地址端点均算落在 CIDR 内（需求仅要求落在 CIDR 内）', () => {
    expect(ipIntInCidr(ip('192.168.1.0'), cidr)).toBe(true)
    expect(ipIntInCidr(ip('192.168.1.255'), cidr)).toBe(true)
  })

  it('范围内地址为 true；范围外（数值比较）为 false', () => {
    expect(ipIntInCidr(ip('192.168.1.1'), cidr)).toBe(true)
    expect(ipIntInCidr(ip('192.168.1.254'), cidr)).toBe(true)
    expect(ipIntInCidr(ip('192.168.0.255'), cidr)).toBe(false)
    expect(ipIntInCidr(ip('192.168.2.0'), cidr)).toBe(false)
    expect(ipIntInCidr(ip('10.0.0.1'), cidr)).toBe(false)
  })

  it('数值比较不受点分字符串字典序影响（如 192.168.1.9 < 192.168.1.10）', () => {
    const small = parseIpv4Cidr('192.168.1.9/32')!
    expect(ipIntInCidr(ip('192.168.1.10'), small)).toBe(false)
    expect(ipIntInCidr(ip('192.168.1.9'), small)).toBe(true)
  })
})
