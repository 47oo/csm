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
  parseResourceFieldErrors,
  resourceConflictMessage,
  resourceDeleteConfirmMatches,
  resourceStatusLabel,
  resourceTypeLabel,
  validateInterfaceName,
  validateResourceName,
  type InterfaceCard,
} from './resourceRules'

function card(overrides: Partial<InterfaceCard> & Pick<InterfaceCard, 'key'>): InterfaceCard {
  return {
    id: null,
    name: '',
    segmentId: null,
    originalName: '',
    originalSegmentId: null,
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
    expect(parsed.cards['card-a']).toEqual({ name: '第 1 张网卡接口名不能为空', segment_id: '', other: '' })
    expect(parsed.cards['card-b']).toEqual({ name: '', segment_id: '网段必须与本资源同集群', other: '' })
    expect(parsed.cards['card-c']).toEqual({ name: '', segment_id: '', other: '网卡不存在或不属于该资源' })
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
})
