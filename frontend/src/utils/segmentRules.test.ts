// 网段规则单测：字段即时校验（与 Contract §0/§2/§3 及架构 §4 一致）、删除二次确认
// （BQ-Z）、重叠提示文案（§4.6.5）、服务端错误码映射与权限入口可见性（§8.2）。
import { describe, expect, it } from 'vitest'
import {
  canManageSegments,
  overlapWarningText,
  segmentConflictMessage,
  segmentDeleteConfirmMatches,
  validateAutoAllocRange,
  validateGatewayInCidr,
  validateReservedRange,
  validateSegmentCidr,
  validateSegmentName,
  validateSegmentPurpose,
  validateSegmentTechnology,
  validateSegmentVlan,
} from './segmentRules'

const CIDR = '192.168.1.0/24'

describe('字段即时校验', () => {
  describe('名称（去首尾空格非空、≤128；区分大小写判重由服务端保证）', () => {
    it('空白/纯空格/超长拒绝', () => {
      expect(validateSegmentName('')).not.toBeNull()
      expect(validateSegmentName('   ')).not.toBeNull()
      expect(validateSegmentName('a'.repeat(129))).not.toBeNull()
    })
    it('合法名称（含首尾空格的输入由服务端去空格存储）通过', () => {
      expect(validateSegmentName('management')).toBeNull()
      expect(validateSegmentName('  mgmt-net  ')).toBeNull()
      expect(validateSegmentName('a'.repeat(128))).toBeNull()
    })
  })

  describe('用途/技术类型（去首尾空格非空、长度上限 200/100）', () => {
    it('空白拒绝', () => {
      expect(validateSegmentPurpose('')).not.toBeNull()
      expect(validateSegmentPurpose('  ')).not.toBeNull()
      expect(validateSegmentTechnology('')).not.toBeNull()
    })
    it('合法通过；超长拒绝', () => {
      expect(validateSegmentPurpose('管理网络')).toBeNull()
      expect(validateSegmentPurpose('a'.repeat(201))).not.toBeNull()
      expect(validateSegmentTechnology('Ethernet')).toBeNull()
      expect(validateSegmentTechnology('a'.repeat(101))).not.toBeNull()
    })
  })

  describe('CIDR（仅 IPv4、前缀 /0–/32）', () => {
    it('IPv6 与非法格式拒绝', () => {
      expect(validateSegmentCidr('fd00::/8')).not.toBeNull()
      expect(validateSegmentCidr('192.168.1.0')).not.toBeNull()
      expect(validateSegmentCidr('192.168.1.0/33')).not.toBeNull()
      expect(validateSegmentCidr('')).not.toBeNull()
    })
    it('合法 IPv4 CIDR 通过（含带主机位输入，服务端规范化）', () => {
      expect(validateSegmentCidr('192.168.1.0/24')).toBeNull()
      expect(validateSegmentCidr('192.168.1.5/24')).toBeNull()
      expect(validateSegmentCidr('10.0.0.0/8')).toBeNull()
      expect(validateSegmentCidr('0.0.0.0/0')).toBeNull()
      expect(validateSegmentCidr('10.0.0.7/32')).toBeNull()
    })
  })

  describe('VLAN（null 或整数 1–4094）', () => {
    it('留空（null/undefined）通过', () => {
      expect(validateSegmentVlan(null)).toBeNull()
      expect(validateSegmentVlan(undefined)).toBeNull()
    })
    it('边界值：1 与 4094 通过；0 与 4095 拒绝', () => {
      expect(validateSegmentVlan(1)).toBeNull()
      expect(validateSegmentVlan(4094)).toBeNull()
      expect(validateSegmentVlan(0)).not.toBeNull()
      expect(validateSegmentVlan(4095)).not.toBeNull()
    })
    it('非整数拒绝', () => {
      expect(validateSegmentVlan(1.5)).not.toBeNull()
      expect(validateSegmentVlan(Number.NaN)).not.toBeNull()
    })
  })

  describe('网关（落在 CIDR 内，数值比较；对应 422 GATEWAY_OUT_OF_CIDR）', () => {
    it('空串（未设置）通过', () => {
      expect(validateGatewayInCidr('', CIDR)).toBeNull()
    })
    it('CIDR 内通过（含网络/广播地址端点——需求仅要求落在 CIDR 内）', () => {
      expect(validateGatewayInCidr('192.168.1.1', CIDR)).toBeNull()
      expect(validateGatewayInCidr('192.168.1.254', CIDR)).toBeNull()
      expect(validateGatewayInCidr('192.168.1.0', CIDR)).toBeNull()
      expect(validateGatewayInCidr('192.168.1.255', CIDR)).toBeNull()
    })
    it('CIDR 外或非法 IPv4 拒绝', () => {
      expect(validateGatewayInCidr('192.168.2.1', CIDR)).not.toBeNull()
      expect(validateGatewayInCidr('192.168.0.255', CIDR)).not.toBeNull()
      expect(validateGatewayInCidr('10.0.0.1', CIDR)).not.toBeNull()
      expect(validateGatewayInCidr('not-an-ip', CIDR)).not.toBeNull()
      expect(validateGatewayInCidr('fd00::1', CIDR)).not.toBeNull()
    })
    it('CIDR 本身非法时跳过网关校验（由 CIDR 字段呈现错误）', () => {
      expect(validateGatewayInCidr('192.168.2.1', 'not-a-cidr')).toBeNull()
    })
  })

  describe('自动分配范围（成对、落在 CIDR 内、起 ≤ 止；对应 422 AUTO_RANGE_INVALID）', () => {
    it('两端同空（未启用）通过', () => {
      expect(validateAutoAllocRange('', '', CIDR)).toBeNull()
    })
    it('仅一端非空拒绝', () => {
      expect(validateAutoAllocRange('192.168.1.20', '', CIDR)).not.toBeNull()
      expect(validateAutoAllocRange('', '192.168.1.30', CIDR)).not.toBeNull()
    })
    it('成对且在 CIDR 内通过（起 = 止 亦合法）', () => {
      expect(validateAutoAllocRange('192.168.1.20', '192.168.1.30', CIDR)).toBeNull()
      expect(validateAutoAllocRange('192.168.1.20', '192.168.1.20', CIDR)).toBeNull()
    })
    it('越界或起 > 止拒绝', () => {
      expect(validateAutoAllocRange('192.168.1.20', '192.168.2.30', CIDR)).not.toBeNull()
      expect(validateAutoAllocRange('192.168.0.20', '192.168.1.30', CIDR)).not.toBeNull()
      expect(validateAutoAllocRange('192.168.1.30', '192.168.1.20', CIDR)).not.toBeNull()
      expect(validateAutoAllocRange('bad', '192.168.1.30', CIDR)).not.toBeNull()
    })
    it('数值比较：192.168.1.9 ≤ 192.168.1.10（不受字符串字典序影响）', () => {
      expect(validateAutoAllocRange('192.168.1.9', '192.168.1.10', CIDR)).toBeNull()
      expect(validateAutoAllocRange('192.168.1.10', '192.168.1.9', CIDR)).not.toBeNull()
    })
    it('CIDR 非法时跳过（两端成对检查仍生效）', () => {
      expect(validateAutoAllocRange('192.168.1.20', '192.168.1.30', 'bad')).toBeNull()
      expect(validateAutoAllocRange('192.168.1.20', '', 'bad')).not.toBeNull()
    })
  })

  describe('保留地址（落在 CIDR 内、起 ≤ 止；结束空 = 单地址；对应 422 RESERVED_*）', () => {
    it('单地址（结束空）通过', () => {
      expect(validateReservedRange('192.168.1.100', '', CIDR)).toBeNull()
    })
    it('范围通过；起 > 止或越界拒绝', () => {
      expect(validateReservedRange('192.168.1.100', '192.168.1.110', CIDR)).toBeNull()
      expect(validateReservedRange('192.168.1.110', '192.168.1.100', CIDR)).not.toBeNull()
      expect(validateReservedRange('192.168.1.100', '192.168.2.1', CIDR)).not.toBeNull()
      expect(validateReservedRange('192.168.2.1', '', CIDR)).not.toBeNull()
      expect(validateReservedRange('bad', '', CIDR)).not.toBeNull()
    })
    it('与既有保留范围的重叠（RESERVED_OVERLAP）由服务端校验，前端不做假阴性判断', () => {
      // 前端无既有保留列表上下文，重叠判断交服务端；此处仅验证同输入不会误报
      expect(validateReservedRange('192.168.1.100', '192.168.1.100', CIDR)).toBeNull()
    })
  })
})

describe('真实删除二次确认（BQ-Z / Contract §2.5：去首尾空格后等于网段名称，区分大小写）', () => {
  const segment = { name: 'Management-Net' }

  it('精确匹配与首尾空格容忍通过', () => {
    expect(segmentDeleteConfirmMatches('Management-Net', segment)).toBe(true)
    expect(segmentDeleteConfirmMatches('  Management-Net  ', segment)).toBe(true)
  })
  it('大小写敏感、名称不符、空输入不匹配', () => {
    expect(segmentDeleteConfirmMatches('management-net', segment)).toBe(false)
    expect(segmentDeleteConfirmMatches('Management Net', segment)).toBe(false)
    expect(segmentDeleteConfirmMatches('', segment)).toBe(false)
    expect(segmentDeleteConfirmMatches('   ', segment)).toBe(false)
  })
})

describe('重叠风险提示（§4.6.5：仅提示、允许保存）', () => {
  it('无重叠返回 null', () => {
    expect(overlapWarningText({ has_overlap: false, overlaps: [] })).toBeNull()
    expect(
      overlapWarningText({
        has_overlap: false,
        overlaps: [{ segment_id: 6, name: 'storage', cidr: '192.168.1.128/25' }],
      }),
    ).toBeNull()
  })
  it('有重叠时文案包含重叠网段名称与 CIDR，并说明允许保存', () => {
    const text = overlapWarningText({
      has_overlap: true,
      overlaps: [
        { segment_id: 6, name: 'storage', cidr: '192.168.1.128/25' },
        { segment_id: 7, name: 'bmc', cidr: '192.168.1.0/25' },
      ],
    })
    expect(text).toContain('storage（192.168.1.128/25）')
    expect(text).toContain('bmc（192.168.1.0/25）')
    expect(text).toContain('允许保存')
  })
  it('has_overlap 但 overlaps 为空时的兜底文案', () => {
    const text = overlapWarningText({ has_overlap: true, overlaps: [] })
    expect(text).toContain('重叠')
    expect(text).not.toContain('（）')
  })
})

describe('服务端错误码 → 用户提示（409/422 业务语义映射）', () => {
  it.each([
    'SEGMENT_NAME_TAKEN',
    'SEGMENT_CIDR_TAKEN',
    'SEGMENT_HAS_RESERVED_ADDRESSES',
    'SEGMENT_GATEWAY_NOT_CLEARED',
    'SEGMENT_HAS_INTERFACES',
    'SEGMENT_HAS_ALLOCATIONS',
    'CIDR_IMMUTABLE',
    'VERSION_CONFLICT',
    'DELETE_CONFIRMATION_MISMATCH',
  ])('%s 有映射文案', (code) => {
    expect(segmentConflictMessage(code)).toBeTruthy()
  })

  it('删除前置文案指向处理路径（保留地址/网关）', () => {
    expect(segmentConflictMessage('SEGMENT_HAS_RESERVED_ADDRESSES')).toContain('保留地址')
    expect(segmentConflictMessage('SEGMENT_GATEWAY_NOT_CLEARED')).toContain('网关')
  })

  it('未知 code 无映射（undefined，由页面按通用错误处理）', () => {
    expect(segmentConflictMessage('SOMETHING_ELSE')).toBeUndefined()
  })
})

describe('权限入口可见性（§8.2：写操作仅 maintainer/admin；服务端为最终校验）', () => {
  it('viewer 只读、未登录不可见', () => {
    expect(canManageSegments('viewer')).toBe(false)
    expect(canManageSegments(null)).toBe(false)
    expect(canManageSegments(undefined)).toBe(false)
  })
  it('maintainer/admin 可见', () => {
    expect(canManageSegments('maintainer')).toBe(true)
    expect(canManageSegments('admin')).toBe(true)
  })
})
