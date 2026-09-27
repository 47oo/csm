// 计算资源规则单测：字段即时校验（§7.2）、同表单接口名重复、删除二次确认（BQ-Z）、
// 权限入口可见性（§7.2）、网卡 op 映射（架构 §5.3）、errors[] 字段/网卡卡片定位（§7.3）
// 与记录级错误文案映射（Contract §0）。
import { describe, expect, it } from 'vitest'
import type { FieldError } from '../api/types'
import {
  buildCreateInterfaceItems,
  buildInterfaceOps,
  canManageResources,
  emptyResourceFormErrors,
  findDuplicateInterfaceKeys,
  findDuplicateIpKeys,
  ipConflictsNotice,
  parseResourceFieldErrors,
  readIpConflicts,
  resourceConflictMessage,
  resourceDeleteConfirmMatches,
  resourceStatusLabel,
  resourceTypeLabel,
  validateInterfaceName,
  validateIpInSegment,
  validateIpv4Address,
  validateResourceName,
  type InterfaceCard,
  type InterfaceIpItem,
} from './resourceRules'

function card(overrides: Partial<InterfaceCard> & Pick<InterfaceCard, 'key'>): InterfaceCard {
  return {
    id: null,
    name: '',
    segmentId: null,
    originalName: '',
    originalSegmentId: null,
    removed: false,
    ips: [],
    ...overrides,
  }
}

/** IP 条目工厂（F006） */
function ip(overrides: Partial<InterfaceIpItem> & Pick<InterfaceIpItem, 'key'>): InterfaceIpItem {
  return {
    id: null,
    mode: 'manual',
    address: '',
    segmentId: null,
    removed: false,
    ...overrides,
  }
}

describe('字段即时校验（§7.2：必填与长度；唯一性由服务端保证）', () => {
  it('资源名：空白/纯空格/超长拒绝；去首尾空格后非空且 ≤128 通过', () => {
    expect(validateResourceName('')).not.toBeNull()
    expect(validateResourceName('   ')).not.toBeNull()
    expect(validateResourceName('a'.repeat(129))).not.toBeNull()
    expect(validateResourceName('cn001')).toBeNull()
    expect(validateResourceName('  cn001  ')).toBeNull()
    expect(validateResourceName('a'.repeat(128))).toBeNull()
  })

  it('接口名：空白/纯空格/超长拒绝；合法通过', () => {
    expect(validateInterfaceName('')).not.toBeNull()
    expect(validateInterfaceName('  ')).not.toBeNull()
    expect(validateInterfaceName('a'.repeat(129))).not.toBeNull()
    expect(validateInterfaceName('eth0')).toBeNull()
    expect(validateInterfaceName(' ib0 ')).toBeNull()
  })
})

describe('同表单接口名重复（去首尾空格、区分大小写，与服务端口径一致）', () => {
  it('重复（含首尾空格差异）双方卡片均标记', () => {
    const duplicated = findDuplicateInterfaceKeys([
      { key: 'a', name: 'eth0' },
      { key: 'b', name: ' eth0 ' },
      { key: 'c', name: 'ib0' },
    ])
    expect(duplicated.has('a')).toBe(true)
    expect(duplicated.has('b')).toBe(true)
    expect(duplicated.has('c')).toBe(false)
  })

  it('大小写不同不视为重复（区分大小写，BQ-W）', () => {
    const duplicated = findDuplicateInterfaceKeys([
      { key: 'a', name: 'eth0' },
      { key: 'b', name: 'ETH0' },
    ])
    expect(duplicated.size).toBe(0)
  })
})

describe('真实删除二次确认（BQ-Z：去首尾空格、区分大小写，仅名称）', () => {
  it('完全匹配（可含首尾空格）才允许提交', () => {
    expect(resourceDeleteConfirmMatches('cn001', { name: 'cn001' })).toBe(true)
    expect(resourceDeleteConfirmMatches('  cn001  ', { name: 'cn001' })).toBe(true)
    expect(resourceDeleteConfirmMatches('CN001', { name: 'cn001' })).toBe(false)
    expect(resourceDeleteConfirmMatches('cn001 ', { name: 'cn001' })).toBe(true)
    expect(resourceDeleteConfirmMatches('', { name: 'cn001' })).toBe(false)
    expect(resourceDeleteConfirmMatches('   ', { name: 'cn001' })).toBe(false)
    expect(resourceDeleteConfirmMatches('cn002', { name: 'cn001' })).toBe(false)
  })
})

describe('权限入口可见性（§7.2：仅 maintainer/admin；服务端为最终校验）', () => {
  it('viewer 与未登录不可见写入口；maintainer/admin 可见', () => {
    expect(canManageResources('viewer')).toBe(false)
    expect(canManageResources(null)).toBe(false)
    expect(canManageResources(undefined)).toBe(false)
    expect(canManageResources('maintainer')).toBe(true)
    expect(canManageResources('admin')).toBe(true)
  })
})

describe('网卡 op 映射（架构 §5.3 / Contract §2.3：显式区分删除/未修改/新增或修改）', () => {
  it('标记删除的既有网卡 → op:delete（仅 id）；未修改的既有网卡不列入', () => {
    const { ops, cardKeys } = buildInterfaceOps([
      card({ key: 'a', id: 10, name: 'eth0', segmentId: 3, originalName: 'eth0', originalSegmentId: 3, removed: true }),
      card({ key: 'b', id: 11, name: 'ib0', segmentId: null, originalName: 'ib0', originalSegmentId: null }),
    ])
    expect(ops).toEqual([{ op: 'delete', id: 10 }])
    expect(cardKeys).toEqual(['a'])
  })

  it('新增网卡 → op:create（名称 + segment_id，null=不选）', () => {
    const { ops } = buildInterfaceOps([
      card({ key: 'a', name: 'eth0', segmentId: 3 }),
      card({ key: 'b', name: 'ib0', segmentId: null }),
    ])
    expect(ops).toEqual([
      { op: 'create', name: 'eth0', segment_id: 3 },
      { op: 'create', name: 'ib0', segment_id: null },
    ])
  })

  it('修改的既有网卡 → op:update 仅携带变化字段（省略=不修改；null=清空网段）', () => {
    const { ops } = buildInterfaceOps([
      // 仅改名
      card({ key: 'a', id: 10, name: 'eth1', segmentId: 3, originalName: 'eth0', originalSegmentId: 3 }),
      // 仅改网段
      card({ key: 'b', id: 11, name: 'ib0', segmentId: 5, originalName: 'ib0', originalSegmentId: 4 }),
      // 清空网段
      card({ key: 'c', id: 12, name: 'ib1', segmentId: null, originalName: 'ib1', originalSegmentId: 4 }),
      // 名称仅首尾空格差异（去首尾空格后相同）→ 未修改
      card({ key: 'd', id: 13, name: ' eth2 ', segmentId: 3, originalName: 'eth2', originalSegmentId: 3 }),
    ])
    expect(ops).toEqual([
      { op: 'update', id: 10, name: 'eth1' },
      { op: 'update', id: 11, segment_id: 5 },
      { op: 'update', id: 12, segment_id: null },
    ])
  })

  it('全部未修改 → ops 为空（调用方省略 interfaces = 不改动网卡）', () => {
    const { ops, cardKeys } = buildInterfaceOps([
      card({ key: 'a', id: 10, name: 'eth0', segmentId: 3, originalName: 'eth0', originalSegmentId: 3 }),
    ])
    expect(ops).toEqual([])
    expect(cardKeys).toEqual([])
  })

  it('ops 与 cardKeys 按下标一一对应（interfaces[i] 错误定位回卡片）', () => {
    const { ops, cardKeys } = buildInterfaceOps([
      card({ key: 'keep', id: 10, name: 'eth0', segmentId: 3, originalName: 'eth0', originalSegmentId: 3 }),
      card({ key: 'new', name: 'ib1', segmentId: 4 }),
      card({ key: 'renamed', id: 11, name: 'ib0-renamed', segmentId: null, originalName: 'ib0', originalSegmentId: null }),
    ])
    expect(ops).toHaveLength(2)
    expect(cardKeys).toEqual(['new', 'renamed'])
  })

  it('新增模式：全部卡片映射为 NetworkInterfaceCreate[]（removed 的卡片不列入）', () => {
    const { items, cardKeys } = buildCreateInterfaceItems([
      card({ key: 'a', name: 'eth0', segmentId: 3 }),
      card({ key: 'b', name: 'ib0', segmentId: null }),
      card({ key: 'c', name: 'gone', segmentId: 1, removed: true }),
    ])
    expect(items).toEqual([
      { name: 'eth0', segment_id: 3 },
      { name: 'ib0', segment_id: null },
    ])
    expect(cardKeys).toEqual(['a', 'b'])
  })
})

describe('errors[] → 字段与网卡卡片定位（§7.3：错误定位到具体字段和记录）', () => {
  const errors: FieldError[] = [
    { field: 'name', code: 'NAME_FORMAT', message: '资源名称不能为空' },
    { field: 'resource_type', code: 'RESOURCE_TYPE_INVALID', message: '资源类型非法' },
    { field: 'status', code: 'STATUS_INVALID', message: '状态非法' },
    { field: 'interfaces[0].name', code: 'INTERFACE_NAME_FORMAT', message: '第 1 张网卡接口名不能为空' },
    { field: 'interfaces[1].segment_id', code: 'INTERFACE_SEGMENT_CLUSTER_MISMATCH', message: '网段必须与本资源同集群' },
    { field: 'interfaces[2].id', code: 'INTERFACE_NOT_FOUND', message: '网卡不存在或不属于该资源' },
  ]

  it('interfaces[i] 按下标经 cardKeys 定位到对应网卡卡片（name/segment_id/其它子字段）', () => {
    const parsed = parseResourceFieldErrors(errors, ['card-a', 'card-b', 'card-c'])
    expect(parsed.cards['card-a']).toEqual({ name: '第 1 张网卡接口名不能为空', segment_id: '', other: '', ips: {} })
    expect(parsed.cards['card-b']).toEqual({ name: '', segment_id: '网段必须与本资源同集群', other: '', ips: {} })
    expect(parsed.cards['card-c']).toEqual({ name: '', segment_id: '', other: '网卡不存在或不属于该资源', ips: {} })
    expect(parsed.name).toBe('资源名称不能为空')
    expect(parsed.resource_type).toBe('资源类型非法')
    expect(parsed.status).toBe('状态非法')
    expect(parsed.general).toEqual([])
  })

  it('下标越界（不应发生）归入记录级，不崩溃', () => {
    const parsed = parseResourceFieldErrors(
      [{ field: 'interfaces[5].name', code: 'INTERFACE_NAME_FORMAT', message: '越界' }],
      ['card-a'],
    )
    expect(parsed.general).toEqual(['越界'])
    expect(parsed.cards).toEqual({})
  })

  it('field 缺失时按 code 兜底定位（NAME_FORMAT → name 等）', () => {
    const parsed = parseResourceFieldErrors(
      [
        { field: '', code: 'NAME_FORMAT', message: '名称格式非法' },
        { field: '', code: 'RESOURCE_TYPE_IMMUTABLE', message: '资源类型不可修改' },
        { field: '', code: 'RESOURCE_CLUSTER_IMMUTABLE', message: '所属集群不可修改' },
      ],
      [],
    )
    expect(parsed.name).toBe('名称格式非法')
    expect(parsed.resource_type).toBe('资源类型不可修改')
    expect(parsed.cluster_id).toBe('所属集群不可修改')
  })

  it('未知字段（如 interfaces 记录级 / NO_FIELDS）归入 general', () => {
    const parsed = parseResourceFieldErrors(
      [
        { field: 'interfaces', code: 'INTERFACE_NAME_DUPLICATE_IN_PAYLOAD', message: 'payload 内接口名重复' },
        { field: '', code: 'NO_FIELDS', message: '没有可改字段' },
      ],
      [],
    )
    expect(parsed.general).toEqual(['payload 内接口名重复', '没有可改字段'])
  })

  it('空 errors → 空映射（与 emptyResourceFormErrors 等价）', () => {
    expect(parseResourceFieldErrors([], [])).toEqual(emptyResourceFormErrors())
  })
})

describe('展示映射与记录级文案（§9.4 状态含文字；Contract §0 错误码）', () => {
  it('资源类型/状态中文标签（状态必须含文字）', () => {
    expect(resourceTypeLabel('bare_metal')).toBe('裸金属')
    expect(resourceTypeLabel('virtual_machine')).toBe('虚拟机')
    expect(resourceTypeLabel('unknown')).toBe('unknown')
    expect(resourceStatusLabel('IDLE')).toBe('空闲')
    expect(resourceStatusLabel('ALLOC')).toBe('已分配')
    expect(resourceStatusLabel('DOWN')).toBe('宕机 / 不可用')
    expect(resourceStatusLabel('UNKNOWN')).toBe('未知')
  })

  it('记录级错误码文案映射（409/400/422；未映射返回 undefined）', () => {
    expect(resourceConflictMessage('RESOURCE_NAME_EXISTS')).toContain('同名')
    expect(resourceConflictMessage('INTERFACE_NAME_TAKEN')).toContain('接口名')
    expect(resourceConflictMessage('RESOURCE_HAS_INTERFACES')).toContain('网卡')
    expect(resourceConflictMessage('VERSION_CONFLICT')).toContain('并发冲突')
    expect(resourceConflictMessage('DELETE_CONFIRMATION_MISMATCH')).toContain('不匹配')
    expect(resourceConflictMessage('RESOURCE_TYPE_IMMUTABLE')).toContain('资源类型')
    expect(resourceConflictMessage('RESOURCE_CLUSTER_IMMUTABLE')).toContain('集群')
    expect(resourceConflictMessage('NO_FIELDS')).toContain('修改')
    expect(resourceConflictMessage('INVALID_INTERFACE_OP')).toContain('create')
    expect(resourceConflictMessage('SOME_UNKNOWN_CODE')).toBeUndefined()
  })

  it('F006 错误码文案映射（SEGMENT_NOT_SELECTED / INTERFACE_HAS_IPS / MANAGEMENT_IP_REQUIRED 等）', () => {
    expect(resourceConflictMessage('SEGMENT_NOT_SELECTED')).toContain('先选择网段')
    expect(resourceConflictMessage('AUTO_RANGE_NOT_ENABLED')).toContain('自动分配范围')
    expect(resourceConflictMessage('IP_NOT_FOUND')).toContain('不属于该网卡')
    expect(resourceConflictMessage('INTERFACE_HAS_IPS')).toContain('先逐项删除')
    expect(resourceConflictMessage('INTERFACE_SEGMENT_CHANGE_REQUIRES_IP_RELEASE')).toContain('释放')
    expect(resourceConflictMessage('MANAGEMENT_IP_REQUIRED')).toContain('显式清空或重选')
    expect(resourceConflictMessage('MANAGEMENT_IP_INVALID')).toContain('有效网卡 IP')
    expect(resourceConflictMessage('NO_AVAILABLE_ADDRESS')).toContain('不会自动切换')
    expect(resourceConflictMessage('IP_ALREADY_IN_USE')).toBeUndefined() // 无固定文案：由 conflicts 归属展示
  })
})
// ---------- F006：IP 字段校验 ----------

describe('IP 字段即时校验（F006 §7.2/§5：语法 / CIDR 内 / 同表单重复）', () => {
  it('validateIpv4Address：合法点分十进制通过；空白/前导零/越界段/IPv6 形态拒绝', () => {
    expect(validateIpv4Address('192.168.1.10')).toBeNull()
    expect(validateIpv4Address(' 10.0.0.1 ')).toBeNull() // 内部 trim
    expect(validateIpv4Address('0.0.0.0')).toBeNull()
    expect(validateIpv4Address('255.255.255.255')).toBeNull()
    expect(validateIpv4Address('')).not.toBeNull()
    expect(validateIpv4Address('  ')).not.toBeNull()
    expect(validateIpv4Address('192.168.1.256')).not.toBeNull()
    expect(validateIpv4Address('192.168.01.1')).not.toBeNull() // 前导零（与服务端 ipaddress 口径一致）
    expect(validateIpv4Address('::1')).not.toBeNull()
    expect(validateIpv4Address('192.168.1')).not.toBeNull()
  })

  it('validateIpInSegment：CIDR 内通过；网络/广播端点按落在 CIDR 内处理；越界拒绝', () => {
    expect(validateIpInSegment('192.168.1.10', '192.168.1.0/24')).toBeNull()
    expect(validateIpInSegment('192.168.1.0', '192.168.1.0/24')).toBeNull()
    expect(validateIpInSegment('192.168.1.255', '192.168.1.0/24')).toBeNull() // 仅判断落在 CIDR 内（保留/网络/广播由服务端权威拒绝）
    expect(validateIpInSegment('192.168.2.1', '192.168.1.0/24')).toContain('CIDR')
    expect(validateIpInSegment('10.0.0.1', '192.168.1.0/24')).toContain('CIDR')
  })

  it('validateIpInSegment：CIDR 未知（null/空/非法）返回 null，交由服务端判定', () => {
    expect(validateIpInSegment('192.168.2.1', null)).toBeNull()
    expect(validateIpInSegment('192.168.2.1', undefined)).toBeNull()
    expect(validateIpInSegment('192.168.2.1', '')).toBeNull()
  })

  it('findDuplicateIpKeys：同表单将保存的 IP 重复时双方标记；auto/空地址/已删项不参与', () => {
    const duplicated = findDuplicateIpKeys([
      card({
        key: 'a',
        ips: [
          ip({ key: 'a1', id: 55, address: '192.168.1.10' }), // 既有未删
          ip({ key: 'a2', mode: 'auto' }), // auto 地址未定：不参与
        ],
      }),
      card({
        key: 'b',
        ips: [
          ip({ key: 'b1', address: ' 192.168.1.10 ' }), // 与 a1 重复（trim 后比较）
          ip({ key: 'b2', address: '' }), // 空地址不参与
        ],
      }),
      card({ key: 'c', removed: true, ips: [ip({ key: 'c1', address: '192.168.1.10' })] }), // 将删除网卡：不参与
      card({
        key: 'd',
        ips: [ip({ key: 'd1', id: 56, address: '192.168.1.11', removed: true })], // 已标记删除：不参与
      }),
    ])
    expect(duplicated.has('a1')).toBe(true)
    expect(duplicated.has('b1')).toBe(true)
    expect(duplicated.size).toBe(2)
  })
})

// ---------- F006：网卡 IP op 映射 ----------

describe('网卡 IP op 映射（F006 §5.1：嵌套显式操作；未列出=未修改；不可改地址）', () => {
  it('编辑：既有标记删除 → ips:[{op:delete,id}]；待分配 manual 带 address、auto 省略 address', () => {
    const { ops, ipKeys } = buildInterfaceOps([
      card({
        key: 'a',
        id: 10,
        name: 'eth0',
        segmentId: 3,
        originalName: 'eth0',
        originalSegmentId: 3,
        ips: [
          ip({ key: 'keep', id: 55, address: '192.168.1.5', segmentId: 3 }), // 未修改：不列入
          ip({ key: 'del', id: 56, address: '192.168.1.6', segmentId: 3, removed: true }),
          ip({ key: 'new-m', mode: 'manual', address: '192.168.1.7 ' }),
          ip({ key: 'new-a', mode: 'auto' }),
        ],
      }),
    ])
    expect(ops).toEqual([
      {
        op: 'update',
        id: 10,
        ips: [
          { op: 'delete', id: 56 },
          { op: 'create', mode: 'manual', address: '192.168.1.7' },
          { op: 'create', mode: 'auto' },
        ],
      },
    ])
    expect(ipKeys).toEqual([['del', 'new-m', 'new-a']])
  })

  it('编辑：仅 IP 变化的既有网卡 → op:update 只携带 ips（无 name/segment_id）；未修改的既有 IP 不列入', () => {
    const { ops, cardKeys } = buildInterfaceOps([
      card({
        key: 'a',
        id: 10,
        name: 'eth0',
        segmentId: 3,
        originalName: 'eth0',
        originalSegmentId: 3,
        ips: [ip({ key: 'd1', id: 56, address: '192.168.1.6', segmentId: 3, removed: true })],
      }),
      card({
        key: 'b',
        id: 11,
        name: 'ib0',
        segmentId: null,
        originalName: 'ib0',
        originalSegmentId: null,
        ips: [ip({ key: 'keep', id: 57, address: '10.0.0.1', segmentId: 4 })],
      }),
    ])
    expect(ops).toEqual([{ op: 'update', id: 10, ips: [{ op: 'delete', id: 56 }] }])
    expect(cardKeys).toEqual(['a'])
  })

  it('编辑：标记删除的既有网卡 → op:delete 同项携带其全部既有 IP 显式删除（INTERFACE_HAS_IPS 前置）', () => {
    const { ops, ipKeys } = buildInterfaceOps([
      card({
        key: 'a',
        id: 10,
        name: 'eth0',
        segmentId: 3,
        originalName: 'eth0',
        originalSegmentId: 3,
        removed: true,
        ips: [
          ip({ key: 'i1', id: 55, address: '192.168.1.5', segmentId: 3 }),
          ip({ key: 'i2', id: 56, address: '192.168.1.6', segmentId: 3 }),
          ip({ key: 'pending', mode: 'manual', address: '192.168.1.7' }), // 待分配随卡片取消：不提交
        ],
      }),
    ])
    expect(ops).toEqual([
      {
        op: 'delete',
        id: 10,
        ips: [
          { op: 'delete', id: 55 },
          { op: 'delete', id: 56 },
        ],
      },
    ])
    expect(ipKeys).toEqual([['i1', 'i2']])
  })

  it('编辑：新增网卡携带待分配 IP → op:create + ips', () => {
    const { ops } = buildInterfaceOps([
      card({ key: 'a', name: 'ib1', segmentId: 4, ips: [ip({ key: 'n1', mode: 'manual', address: '10.0.0.7' })] }),
    ])
    expect(ops).toEqual([
      {
        op: 'create',
        name: 'ib1',
        segment_id: 4,
        ips: [{ op: 'create', mode: 'manual', address: '10.0.0.7' }],
      },
    ])
  })

  it('新增模式：items[].ips 为 IpCreate（mode/address，无 op 字段）；无 IP 时省略 ips', () => {
    const { items, ipKeys } = buildCreateInterfaceItems([
      card({
        key: 'a',
        name: 'eth0',
        segmentId: 3,
        ips: [
          ip({ key: 'm1', mode: 'manual', address: '192.168.1.10' }),
          ip({ key: 'a1', mode: 'auto' }),
        ],
      }),
      card({ key: 'b', name: 'ib0', segmentId: null, ips: [] }),
    ])
    expect(items).toEqual([
      {
        name: 'eth0',
        segment_id: 3,
        ips: [
          { mode: 'manual', address: '192.168.1.10' },
          { mode: 'auto' },
        ],
      },
      { name: 'ib0', segment_id: null },
    ])
    expect(ipKeys).toEqual([['m1', 'a1'], []])
  })
})

// ---------- F006：errors[] → IP 条目定位 ----------

describe('errors[] → IP 条目定位（F006 §7.3：interfaces[i].ips[j] 定位到具体网卡的具体 IP）', () => {
  it('interfaces[1].ips[0].address → 第 2 项操作的第 1 个 IP 条目 address 槽位', () => {
    const parsed = parseResourceFieldErrors(
      [
        { field: 'interfaces[1].ips[0].address', code: 'IP_OUT_OF_SEGMENT', message: '10.0.0.1 不在网卡所选网段内' },
        { field: 'interfaces[0].ips[1].address', code: 'IP_ALREADY_IN_USE', message: '192.168.1.10 已被本集群使用' },
      ],
      ['card-a', 'card-b'],
      [['ip-a0', 'ip-a1'], ['ip-b0']],
    )
    expect(parsed.cards['card-b']?.ips['ip-b0']).toEqual({ address: '10.0.0.1 不在网卡所选网段内', other: '' })
    expect(parsed.cards['card-a']?.ips['ip-a1']).toEqual({ address: '192.168.1.10 已被本集群使用', other: '' })
    expect(parsed.cards['card-a']?.ips['ip-a0']).toBeUndefined()
    expect(parsed.general).toEqual([])
  })

  it('裸 interfaces[0].ips[1]（AUTO_RANGE_NOT_ENABLED / NO_AVAILABLE_ADDRESS 等）→ IP other 槽位', () => {
    const parsed = parseResourceFieldErrors(
      [{ field: 'interfaces[0].ips[1]', code: 'AUTO_RANGE_NOT_ENABLED', message: '网段未启用自动分配范围' }],
      ['card-a'],
      [['ip-a0', 'ip-a1']],
    )
    expect(parsed.cards['card-a']?.ips['ip-a1']).toEqual({ address: '', other: '网段未启用自动分配范围' })
  })

  it('ips[j] 下标越界（不应发生）归入记录级，不崩溃', () => {
    const parsed = parseResourceFieldErrors(
      [{ field: 'interfaces[0].ips[9].address', code: 'IP_OUT_OF_SEGMENT', message: '越界' }],
      ['card-a'],
      [['ip-a0']],
    )
    expect(parsed.general).toEqual(['越界'])
    expect(parsed.cards).toEqual({})
  })

  it('management_ip 字段与 code 兜底定位（MANAGEMENT_IP_REQUIRED / INVALID）', () => {
    const parsed = parseResourceFieldErrors(
      [
        { field: 'management_ip', code: 'MANAGEMENT_IP_REQUIRED', message: '须同次显式清空或重选管理 IP' },
        { field: '', code: 'MANAGEMENT_IP_INVALID', message: '管理 IP 引用无效' },
      ],
      [],
    )
    expect(parsed.management_ip).toBe('须同次显式清空或重选管理 IP')
    // 已定位到字段时 code 兜底不覆盖
    expect(parsed.management_ip).not.toContain('引用无效')
  })

  it('无 ipKeys 时 interfaces[i].ips[j] 归入记录级（兼容旧调用）', () => {
    const parsed = parseResourceFieldErrors(
      [{ field: 'interfaces[0].ips[0].address', code: 'IP_OUT_OF_SEGMENT', message: '越界' }],
      ['card-a'],
    )
    expect(parsed.general).toEqual(['越界'])
  })
})

// ---------- F006：conflicts 归属展示 ----------

describe('IP_ALREADY_IN_USE conflicts 归属展示（Contract F006 §0 扩展成员）', () => {
  it('readIpConflicts：从扩展成员提取；缺失/形状非法 → []（不伪装）', () => {
    expect(
      readIpConflicts({
        conflicts: [
          { ip: '10.0.0.1', resource_id: 7, resource_name: 'cn002', interface_id: 12, interface_name: 'ib0' },
        ],
      }),
    ).toEqual([{ ip: '10.0.0.1', resource_id: 7, resource_name: 'cn002', interface_id: 12, interface_name: 'ib0' }])
    expect(readIpConflicts({})).toEqual([])
    expect(readIpConflicts({ conflicts: 'not-array' })).toEqual([])
    expect(readIpConflicts({ conflicts: [null, 42, { ip: 1 }] })).toEqual([])
  })

  it('ipConflictsNotice：单条「已被本集群 X/Y 使用」；多条以「；」连接；空 → 空串', () => {
    expect(
      ipConflictsNotice([{ ip: '10.0.0.1', resource_id: 7, resource_name: 'cn002', interface_id: 12, interface_name: 'ib0' }]),
    ).toBe('10.0.0.1 已被本集群 cn002/ib0 使用')
    expect(
      ipConflictsNotice([
        { ip: '10.0.0.1', resource_id: 7, resource_name: 'cn002', interface_id: 12, interface_name: 'ib0' },
        { ip: '10.0.0.2', resource_id: 8, resource_name: 'cn003', interface_id: 13, interface_name: 'eth1' },
      ]),
    ).toBe('10.0.0.1 已被本集群 cn002/ib0 使用；10.0.0.2 已被本集群 cn003/eth1 使用')
    expect(ipConflictsNotice([])).toBe('')
  })
})
