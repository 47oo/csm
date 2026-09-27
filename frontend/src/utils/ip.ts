// IPv4 地址与 CIDR 工具（F005）：纯函数 + 数值比较，供网段表单即时校验使用，
// 亦为后续 IP 分配相关 Feature（F006）提供可复用的地址集合运算基础。
// 规则依据：需求 §5、架构 F005 §4.2/§4.8——仅 IPv4；CIDR 前缀 /0–/32；
// 接受带主机位的输入（如 192.168.1.5/24），按网络地址归一化（与服务端
// ipaddress.IPv4Network(strict=False) 规范化一致，服务端为最终保证）；
// 「落在 CIDR 内」= 地址数值 ∈ [网络地址数值, 广播地址数值]（含端点，
// 需求仅要求落在 CIDR 内，不额外排除网络/广播地址）。
//
// 地址格式为严格点分十进制：每段 0–255、不允许前导零（与 Python ipaddress 一致），
// 不做 trim——含空格的输入按非法处理，由服务端同一口径最终校验。

const IPV4_OCTET = '25[0-5]|2[0-4]\\d|1\\d\\d|[1-9]?\\d'
const IPV4_PATTERN = new RegExp(`^(?:${IPV4_OCTET})(?:\\.(?:${IPV4_OCTET})){3}$`)

/** 解析点分十进制 IPv4 为无符号 32 位整数；非法返回 null */
export function ipv4ToInt(ip: string): number | null {
  if (!IPV4_PATTERN.test(ip)) return null
  const octets = ip.split('.').map((part) => Number(part))
  // 最大 255.255.255.255 = 2^32 - 1，仍在 Number 安全整数范围内
  return ((octets[0] * 256 + octets[1]) * 256 + octets[2]) * 256 + octets[3]
}

/** 无符号 32 位整数 → 点分十进制 IPv4 */
export function intToIpv4(value: number): string {
  return [value >>> 24, (value >>> 16) & 255, (value >>> 8) & 255, value & 255].join('.')
}

/** 解析后的 IPv4 CIDR（数值比较键） */
export interface ParsedIpv4Cidr {
  /** 规范化网络地址数值（主机位归零） */
  networkInt: number
  /** 广播地址数值（网络地址 | 主机位全 1） */
  broadcastInt: number
  /** 前缀长度 0–32 */
  prefix: number
  /** 规范化 CIDR 字符串（网络地址/前缀），与服务端 cidr_key 口径一致 */
  normalized: string
}

/** 解析 IPv4 CIDR（接受带主机位输入并归一化）；非法（非 IPv4、无前缀、前缀 > 32 等）返回 null */
export function parseIpv4Cidr(raw: string): ParsedIpv4Cidr | null {
  const slash = raw.indexOf('/')
  if (slash === -1) return null
  const ipPart = raw.slice(0, slash)
  const prefixPart = raw.slice(slash + 1)
  if (!/^\d{1,2}$/.test(prefixPart)) return null
  const prefix = Number(prefixPart)
  if (prefix > 32) return null
  const ipInt = ipv4ToInt(ipPart)
  if (ipInt === null) return null
  const mask = prefix === 0 ? 0 : (0xffffffff << (32 - prefix)) >>> 0
  const networkInt = (ipInt & mask) >>> 0
  const hostBits = 32 - prefix
  // 注意 1 << 32 在 JS 中等于 1 << 0（移位数按 32 取模），/0 须特判
  const hostMask = hostBits >= 32 ? 0xffffffff : ((1 << hostBits) - 1) >>> 0
  const broadcastInt = (networkInt | hostMask) >>> 0
  return { networkInt, broadcastInt, prefix, normalized: `${intToIpv4(networkInt)}/${prefix}` }
}

/** 地址数值是否落在 CIDR 内（含网络/广播端点；数值比较） */
export function ipIntInCidr(ipInt: number, cidr: ParsedIpv4Cidr): boolean {
  return ipInt >= cidr.networkInt && ipInt <= cidr.broadcastInt
}
