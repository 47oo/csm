// 资源表单状态机单测（架构 F002 §2.4 + F006 §2.4）：通过在真实 router（memory history）+
// pinia 下挂载宿主组件驱动 composable（模式与 useSegmentPageScope.test.ts 一致），API 模块 mock。
// 覆盖：路由匹配与编辑初始化、网卡/IP op 映射端到端（interfaces/ips 缺省=不改动）、
// 同名 409 RESOURCE_NAME_EXISTS 进入编辑、并发冲突保留输入与刷新重提、
// 删除二次确认（BQ-Z）与删除前置、字段级错误定位到网卡卡片与 IP 条目（interfaces[i].ips[j]）、
// IP 冲突 conflicts 归属展示、未选网段禁用分配、改网段清除待分配/须释放既有 IP、
// 管理 IP 强制清空/重选（MANAGEMENT_IP_REQUIRED 前端阻断）、前端基础校验、
// 权限隐藏（viewer 只读）、切换集群清除不匹配网段（§7.1）。
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createApp, defineComponent, h, nextTick } from 'vue'
import { createPinia, setActivePinia, type Pinia } from 'pinia'
import { createMemoryHistory, createRouter, type Router } from 'vue-router'
import { routes } from '../router'
import { useAuthStore } from '../stores/auth'
import { useClusterStore } from '../stores/clusters'
import { ApiError } from '../api/client'
import type { CurrentUser } from '../api/types'
import type { ResourceFormDetail } from '../api/resources'
import { useResourceForm } from './useResourceForm'

vi.mock('element-plus', () => ({
  ElMessage: { success: vi.fn(), warning: vi.fn(), error: vi.fn(), info: vi.fn() },
}))

vi.mock('../api/resources', () => ({
  createResource: vi.fn(),
  getResource: vi.fn(),
  updateResource: vi.fn(),
  deleteResource: vi.fn(),
}))

vi.mock('../api/segments', () => ({
  listNetworkSegments: vi.fn(),
}))

vi.mock('../api/clusters', () => ({
  listClusters: vi.fn(),
}))

// vi.mock 的模块在静态提升后可用：在此处引入以获得类型化的 mock
import * as resourcesApi from '../api/resources'
import { listNetworkSegments } from '../api/segments'
import { listClusters } from '../api/clusters'

const maintainer: CurrentUser = {
  id: 2,
  username: 'ops01',
  role: 'maintainer',
  status: 'enabled',
  must_change_password: false,
}

const viewer: CurrentUser = { ...maintainer, id: 3, username: 'view01', role: 'viewer' }

const NOW = '2026-09-25T00:00:00Z'

function segmentListItem(id: number, clusterId: number, name: string, cidr: string) {
  return {
    id,
    cluster_id: clusterId,
    cluster_code: 'N96P',
    cluster_name: '生产集群',
    name,
    cidr,
    purpose: '管理',
    technology: 'Ethernet',
    vlan: 100,
    gateway: '192.168.1.1',
    auto_alloc_start: null,
    auto_alloc_end: null,
    auto_alloc_enabled: false,
    reserved_address_count: 0,
    allocated_count: 0,
    auto_assignable_count: 0,
    has_overlap: false,
    created_at: NOW,
    updated_at: NOW,
  }
}

const CLUSTER_1_SEGMENTS = [segmentListItem(3, 1, 'management', '192.168.1.0/24')]
const CLUSTER_2_SEGMENTS = [segmentListItem(5, 2, 'storage', '10.0.0.0/24')]

/** F002 形态基线（无 IP、无管理 IP） */
const detail: ResourceFormDetail = {
  id: 7,
  cluster_id: 1,
  cluster_code: 'N96P',
  cluster_name: '生产集群',
  name: 'cn001',
  resource_type: 'bare_metal',
  status: 'ALLOC',
  status_updated_by: 2,
  status_updated_by_username: 'ops01',
  status_updated_at: NOW,
  interfaces: [
    {
      id: 10,
      name: 'eth0',
      segment_id: 3,
      segment: {
        id: 3,
        name: 'management',
        cidr: '192.168.1.0/24',
        purpose: '管理',
        technology: 'Ethernet',
        vlan: 100,
        gateway: '192.168.1.1',
      },
      ips: [],
      created_at: NOW,
      updated_at: NOW,
    },
    {
      id: 11,
      name: 'ib0',
      segment_id: null,
      segment: null,
      ips: [],
      created_at: NOW,
      updated_at: NOW,
    },
  ],
  management_ip: null,
  version: 3,
  created_at: NOW,
  updated_at: NOW,
}

/** F006 形态基线：eth0 已有 1 个 IP（55，管理 IP），ib0 无 IP */
const detailWithIp: ResourceFormDetail = {
  ...detail,
  interfaces: [
    {
      ...detail.interfaces[0]!,
      ips: [
        {
          id: 55,
          address: '192.168.1.10',
          segment_id: 3,
          interface_id: 10,
          is_management: true,
          created_at: NOW,
        },
      ],
    },
    detail.interfaces[1]!,
  ],
  management_ip: { ip_id: 55, address: '192.168.1.10', interface_id: 10, interface_name: 'eth0' },
}

let router: Router
let pinia: Pinia
let exposed: ReturnType<typeof useResourceForm> | null = null

/** 挂载仅运行 composable 的宿主组件（无需 @vue/test-utils） */
function mountHost(): void {
  const Host = defineComponent({
    setup() {
      exposed = useResourceForm()
      return () => h('div')
    },
  })
  const app = createApp(Host)
  app.use(pinia)
  app.use(router)
  app.mount(document.createElement('div'))
}

/** 排空 watcher → init / 提交等异步链（微任务 + 一次宏任务边界） */
async function flush(): Promise<void> {
  for (let i = 0; i < 10; i++) await nextTick()
  await new Promise((resolve) => setTimeout(resolve, 0))
  for (let i = 0; i < 10; i++) await nextTick()
}

/** 等待条件成立（轮询真实定时器；用于懒加载路由的导航完成等并不可靠的异步链） */
async function waitFor(predicate: () => boolean, timeoutMs = 2000): Promise<void> {
  const start = Date.now()
  while (!predicate()) {
    if (Date.now() - start > timeoutMs) throw new Error('waitFor 超时')
    await new Promise((resolve) => setTimeout(resolve, 5))
    for (let i = 0; i < 5; i++) await nextTick()
  }
}

async function mountForm(path: string): Promise<void> {
  router = createRouter({ history: createMemoryHistory(), routes })
  await router.push(path)
  await router.isReady()
  mountHost()
  await flush()
}

beforeEach(() => {
  pinia = createPinia()
  setActivePinia(pinia)
  window.localStorage.clear()
  exposed = null
  vi.clearAllMocks()
  // 注意传入副本：pinia 对象 $patch 会深度合并到已存储的原始对象上，
  // 共享 fixture 引用会被后续 patch 原地改写（避免跨用例污染）
  useAuthStore().$patch({ user: { ...maintainer }, initialized: true })
  // 默认应答：集群列表（1/2）、网段（按集群）、资源详情
  vi.mocked(listClusters).mockResolvedValue({
    items: [
      { id: 1, code: 'N96P', name: '生产集群', purpose: '训练', created_at: NOW, updated_at: NOW },
      { id: 2, code: 'N97P', name: '测试集群', purpose: '测试', created_at: NOW, updated_at: NOW },
    ],
    total: 2,
    page: 1,
    page_size: 100,
  })
  vi.mocked(listNetworkSegments).mockImplementation(async (query) => ({
    items: query.cluster_id === 2 ? CLUSTER_2_SEGMENTS : CLUSTER_1_SEGMENTS,
    total: query.cluster_id === 2 ? CLUSTER_2_SEGMENTS.length : CLUSTER_1_SEGMENTS.length,
    page: 1,
    page_size: 100,
  }))
  vi.mocked(resourcesApi.getResource).mockResolvedValue(detail)
  vi.mocked(resourcesApi.createResource).mockResolvedValue(detail)
  vi.mocked(resourcesApi.updateResource).mockResolvedValue(detail)
  vi.mocked(resourcesApi.deleteResource).mockResolvedValue(undefined)
})

describe('路由匹配（/clusters/:clusterId/resources/...）', () => {
  it('新增/编辑路由按数字 ID 匹配；非数字不匹配（落入 404 兜底）', () => {
    router = createRouter({ history: createMemoryHistory(), routes })
    expect(router.resolve('/clusters/3/resources/new').name).toBe('resource-new')
    expect(router.resolve('/clusters/3/resources/7/edit').name).toBe('resource-edit')
    expect(router.resolve('/clusters/abc/resources/new').name).not.toBe('resource-new')
    expect(router.resolve('/clusters/3/resources/x/edit').name).not.toBe('resource-edit')
    // 编辑路由不吞并 new（resourceId 仅数字）
    expect(router.resolve('/clusters/3/resources/new/edit').name).not.toBe('resource-edit')
  })
})

describe('编辑初始化（Contract §2.2：详情供表单加载）', () => {
  it('加载详情与网段选项；集群只读回显并同步作用域；网卡卡片建立基线', async () => {
    await mountForm('/clusters/1/resources/7/edit')
    expect(exposed?.mode.value).toBe('edit')
    expect(exposed?.detail.value?.id).toBe(7)
    expect(exposed?.name.value).toBe('cn001')
    expect(exposed?.resourceType.value).toBe('bare_metal')
    expect(exposed?.version.value).toBe(3)
    expect(exposed?.cards.value).toHaveLength(2)
    expect(exposed?.cards.value[0]?.id).toBe(10)
    expect(exposed?.cards.value[0]?.originalName).toBe('eth0')
    expect(exposed?.cards.value[1]?.segmentId).toBeNull()
    expect(resourcesApi.getResource).toHaveBeenCalledWith(7)
    expect(listNetworkSegments).toHaveBeenCalledWith(
      expect.objectContaining({ cluster_id: 1, page: 1, page_size: 100 }),
    )
    expect(useClusterStore().currentClusterId).toBe(1)
    // 网段选项来自 F005 API（仅本集群仍存网段）
    expect(exposed?.segmentOptions.value.map((s) => s.id)).toEqual([3])
    expect(exposed?.segmentSummary(3)?.cidr).toBe('192.168.1.0/24')
  })

  it('404 RESOURCE_NOT_FOUND → notFound 状态（不伪装成空表单）', async () => {
    vi.mocked(resourcesApi.getResource).mockRejectedValue(
      new ApiError(404, 'RESOURCE_NOT_FOUND', '资源不存在'),
    )
    await mountForm('/clusters/1/resources/999/edit')
    expect(exposed?.notFound.value).toBe(true)
    expect(exposed?.loading.value).toBe(false)
  })

  it('新增模式：路由集群初始化选择；集群不存在 → 显式错误', async () => {
    await mountForm('/clusters/1/resources/new')
    expect(exposed?.mode.value).toBe('create')
    expect(exposed?.selectedClusterId.value).toBe(1)
    expect(exposed?.status.value).toBe('ALLOC')

    await mountForm('/clusters/99/resources/new')
    expect(exposed?.loadError.value).toContain('所选集群不存在')
  })
})

describe('网卡 op 映射端到端（编辑提交，架构 §5.3 / Contract §2.3）', () => {
  it('删除/未修改/新增或修改 → delete / 不列入 / create / update(仅变化字段)', async () => {
    await mountForm('/clusters/1/resources/7/edit')
    const cards = exposed!.cards.value
    // eth0（id 10）标记删除；ib0（id 11）改名；追加新网卡 eth9
    exposed!.removeInterface(cards[0]!.key)
    cards[1]!.name = 'ib0-new'
    exposed!.addInterface()
    const added = exposed!.cards.value[2]!
    added.name = 'eth9'
    exposed!.setCardSegment(added, 3)
    exposed!.name.value = 'cn001-new'
    exposed!.status.value = 'DOWN'

    await exposed!.submit()
    await flush()

    expect(resourcesApi.updateResource).toHaveBeenCalledTimes(1)
    expect(resourcesApi.updateResource).toHaveBeenCalledWith(7, {
      name: 'cn001-new',
      status: 'DOWN',
      interfaces: [
        { op: 'delete', id: 10 },
        { op: 'update', id: 11, name: 'ib0-new' },
        { op: 'create', name: 'eth9', segment_id: 3 },
      ],
      version: 3,
    })
  })

  it('仅改网段（含清空）→ update 只携带 segment_id（null=清空）', async () => {
    await mountForm('/clusters/1/resources/7/edit')
    const cards = exposed!.cards.value
    exposed!.setCardSegment(cards[0]!, 5) // 3 → 5（改网段）
    exposed!.setCardSegment(cards[1]!, null) // null → null（无变化，不列入）
    await exposed!.submit()
    await flush()
    expect(resourcesApi.updateResource).toHaveBeenCalledWith(7, {
      interfaces: [{ op: 'update', id: 10, segment_id: 5 }],
      version: 3,
    })
  })

  it('未做任何修改 → 不发请求（NO_FIELDS 前端预检）；仅改名称时 interfaces 缺省=不改动', async () => {
    await mountForm('/clusters/1/resources/7/edit')
    await exposed!.submit()
    expect(resourcesApi.updateResource).not.toHaveBeenCalled()
    expect(exposed!.formNotice.value).toContain('没有可保存的修改')

    exposed!.name.value = 'cn002'
    await exposed!.submit()
    await flush()
    expect(resourcesApi.updateResource).toHaveBeenCalledWith(7, { name: 'cn002', version: 3 })
  })

  it('新增提交：cluster_id/名称/类型/状态 + 网卡项', async () => {
    await mountForm('/clusters/1/resources/new')
    exposed!.name.value = 'vm001'
    exposed!.resourceType.value = 'virtual_machine'
    exposed!.addInterface()
    const card = exposed!.cards.value[0]!
    card.name = 'eth0'
    exposed!.setCardSegment(card, 3)
    await exposed!.submit()
    await flush()
    expect(resourcesApi.createResource).toHaveBeenCalledWith({
      cluster_id: 1,
      name: 'vm001',
      resource_type: 'virtual_machine',
      status: 'ALLOC',
      interfaces: [{ name: 'eth0', segment_id: 3 }],
    })
  })

  it('新增提交：无网卡时 interfaces 省略（缺省=空数组）', async () => {
    await mountForm('/clusters/1/resources/new')
    exposed!.name.value = 'vm002'
    exposed!.resourceType.value = 'virtual_machine'
    await exposed!.submit()
    await flush()
    expect(resourcesApi.createResource).toHaveBeenCalledWith({
      cluster_id: 1,
      name: 'vm002',
      resource_type: 'virtual_machine',
      status: 'ALLOC',
    })
  })

  it('保存成功后以响应重建基线（展示保存结果，version 自增）', async () => {
    await mountForm('/clusters/1/resources/7/edit')
    vi.mocked(resourcesApi.updateResource).mockResolvedValue({ ...detail, name: 'cn001-new', version: 4 })
    exposed!.name.value = 'cn001-new'
    await exposed!.submit()
    await flush()
    expect(exposed!.name.value).toBe('cn001-new')
    expect(exposed!.version.value).toBe(4)
    expect(exposed!.cards.value).toHaveLength(2)
  })
})

describe('同名处理（§4.1.10、场景 2/45：existing_resource_id 确认进入编辑）', () => {
  it('创建 409 RESOURCE_NAME_EXISTS → 弹确认；确认后跳转既有资源编辑路由', async () => {
    await mountForm('/clusters/1/resources/new')
    exposed!.name.value = 'cn001'
    exposed!.resourceType.value = 'bare_metal'
    vi.mocked(resourcesApi.createResource).mockRejectedValue(
      new ApiError(409, 'RESOURCE_NAME_EXISTS', '该集群已存在同名资源', [], {
        existing_resource_id: 42,
        existing_resource_type: 'bare_metal',
      }),
    )
    await exposed!.submit()
    await flush()

    // 输入保留 + 弹确认（含扩展成员）
    expect(exposed!.name.value).toBe('cn001')
    expect(exposed!.sameNamePrompt.value).toEqual({ existingId: 42, existingType: 'bare_metal' })

    exposed!.confirmSameNameGoEdit()
    await waitFor(() => router.currentRoute.value.name === 'resource-edit')
    expect(router.currentRoute.value.params.resourceId).toBe('42')
    expect(router.currentRoute.value.params.clusterId).toBe('1')
    // 路由切换触发编辑初始化（加载既有资源 42 的详情）
    await waitFor(() => vi.mocked(resourcesApi.getResource).mock.calls.some((c) => c[0] === 42))
  })

  it('取消留在本页：不跳转、输入保留、提示关闭', async () => {
    await mountForm('/clusters/1/resources/new')
    exposed!.name.value = 'cn001'
    exposed!.resourceType.value = 'bare_metal'
    vi.mocked(resourcesApi.createResource).mockRejectedValue(
      new ApiError(409, 'RESOURCE_NAME_EXISTS', '该集群已存在同名资源', [], {
        existing_resource_id: 42,
        existing_resource_type: 'virtual_machine',
      }),
    )
    await exposed!.submit()
    await flush()
    exposed!.dismissSameName()
    await flush()
    expect(router.currentRoute.value.name).toBe('resource-new')
    expect(exposed!.sameNamePrompt.value).toBeNull()
    expect(exposed!.name.value).toBe('cn001')
  })

  it('扩展成员缺失 → 回退为记录级提示（不弹确认、不跳转）', async () => {
    await mountForm('/clusters/1/resources/new')
    exposed!.name.value = 'cn001'
    exposed!.resourceType.value = 'bare_metal'
    vi.mocked(resourcesApi.createResource).mockRejectedValue(
      new ApiError(409, 'RESOURCE_NAME_EXISTS', '该集群已存在同名资源'),
    )
    await exposed!.submit()
    await flush()
    expect(exposed!.sameNamePrompt.value).toBeNull()
    expect(exposed!.formNotice.value).toContain('同名')
  })

  it('编辑改名撞名 → 名称字段级错误（保留输入）', async () => {
    await mountForm('/clusters/1/resources/7/edit')
    vi.mocked(resourcesApi.updateResource).mockRejectedValue(
      new ApiError(409, 'RESOURCE_NAME_EXISTS', '该集群已存在同名资源'),
    )
    exposed!.name.value = 'cn002'
    await exposed!.submit()
    await flush()
    expect(exposed!.fieldErrors.name).toContain('同名')
    expect(exposed!.name.value).toBe('cn002')
  })
})

describe('并发冲突（§4.5、场景 47：保留输入，刷新确认后重提）', () => {
  it('409 VERSION_CONFLICT → 冲突提示且输入保留；提交被阻止', async () => {
    await mountForm('/clusters/1/resources/7/edit')
    vi.mocked(resourcesApi.updateResource).mockRejectedValue(
      new ApiError(409, 'VERSION_CONFLICT', '并发冲突'),
    )
    exposed!.name.value = 'cn001-x'
    await exposed!.submit()
    await flush()
    expect(exposed!.conflict.value).toBe(true)
    expect(exposed!.name.value).toBe('cn001-x')
    expect(resourcesApi.updateResource).toHaveBeenCalledTimes(1)

    // 冲突未解决前提交被阻止
    await exposed!.submit()
    expect(resourcesApi.updateResource).toHaveBeenCalledTimes(1)
  })

  it('刷新版本保留当前输入 → 版本更新、冲突清除、可按新版本重提', async () => {
    await mountForm('/clusters/1/resources/7/edit')
    vi.mocked(resourcesApi.updateResource).mockRejectedValue(
      new ApiError(409, 'VERSION_CONFLICT', '并发冲突'),
    )
    exposed!.name.value = 'cn001-x'
    await exposed!.submit()
    await flush()

    // 其他人保存了新版本（name 不同、version 自增）
    vi.mocked(resourcesApi.getResource).mockResolvedValue({ ...detail, name: 'cn001-other', version: 4 })
    await exposed!.refreshVersionKeepInput()
    await flush()
    expect(exposed!.version.value).toBe(4)
    expect(exposed!.conflict.value).toBe(false)
    expect(exposed!.conflictResolved.value).toBe(true)
    // 用户输入保留（未被他人内容覆盖）
    expect(exposed!.name.value).toBe('cn001-x')

    // 确认后重提：携带新 version 与用户输入
    vi.mocked(resourcesApi.updateResource).mockClear()
    await exposed!.submit()
    await flush()
    expect(resourcesApi.updateResource).toHaveBeenCalledWith(7, {
      name: 'cn001-x',
      version: 4,
    })
  })
})

describe('字段级错误定位（§7.3：errors[] 含 interfaces[i] 下标定位到具体网卡卡片）', () => {
  it('422 VALIDATION_ERROR：interfaces[1].name / segment_id 定位到第 2 张网卡卡片，输入保留', async () => {
    await mountForm('/clusters/1/resources/new')
    exposed!.name.value = 'vm001'
    exposed!.resourceType.value = 'virtual_machine'
    exposed!.addInterface()
    exposed!.cards.value[0]!.name = 'eth0'
    exposed!.addInterface()
    exposed!.cards.value[1]!.name = 'ib0'
    vi.mocked(resourcesApi.createResource).mockRejectedValue(
      new ApiError(422, 'VALIDATION_ERROR', '字段校验失败', [
        { field: 'interfaces[1].name', code: 'INTERFACE_NAME_FORMAT', message: '接口名不能为空' },
        {
          field: 'interfaces[1].segment_id',
          code: 'INTERFACE_SEGMENT_CLUSTER_MISMATCH',
          message: '网段必须与本资源同集群',
        },
      ]),
    )
    await exposed!.submit()
    await flush()

    const second = exposed!.cards.value[1]!
    expect(exposed!.fieldErrors.cards[second.key]?.name).toBe('接口名不能为空')
    expect(exposed!.fieldErrors.cards[second.key]?.segment_id).toBe('网段必须与本资源同集群')
    // 第一张卡片不受影响；全部输入保留
    const first = exposed!.cards.value[0]!
    expect(exposed!.fieldErrors.cards[first.key]).toBeUndefined()
    expect(first.name).toBe('eth0')
    expect(second.name).toBe('ib0')
  })

  it('400 INVALID_REQUEST（RESOURCE_TYPE_IMMUTABLE，errors[].field 定位）→ 类型字段错误', async () => {
    await mountForm('/clusters/1/resources/7/edit')
    vi.mocked(resourcesApi.updateResource).mockRejectedValue(
      new ApiError(400, 'INVALID_REQUEST', '请求体非法', [
        { field: 'resource_type', code: 'RESOURCE_TYPE_IMMUTABLE', message: '资源类型创建后不可修改' },
      ]),
    )
    // 需先有一个可改字段变化（否则被 NO_FIELDS 预检拦截）
    exposed!.name.value = 'cn002'
    await exposed!.submit()
    await flush()
    expect(exposed!.fieldErrors.resource_type).toContain('资源类型')
  })

  it('409 INTERFACE_NAME_TAKEN → 记录级提示（保留输入不关窗）', async () => {
    await mountForm('/clusters/1/resources/7/edit')
    vi.mocked(resourcesApi.updateResource).mockRejectedValue(
      new ApiError(409, 'INTERFACE_NAME_TAKEN', '接口名重复'),
    )
    exposed!.name.value = 'cn002'
    await exposed!.submit()
    await flush()
    expect(exposed!.formNotice.value).toContain('接口名')
    expect(exposed!.name.value).toBe('cn002')
  })
})

describe('前端基础校验（§7.2；不发起请求）', () => {
  it('名称空白/类型未选/集群未选 → 字段错误，不发请求', async () => {
    await mountForm('/clusters/1/resources/new')
    exposed!.name.value = '   '
    await exposed!.submit()
    expect(resourcesApi.createResource).not.toHaveBeenCalled()
    expect(exposed!.fieldErrors.name).not.toBe('')

    exposed!.name.value = 'vm001'
    await exposed!.submit()
    expect(resourcesApi.createResource).not.toHaveBeenCalled()
    expect(exposed!.fieldErrors.resource_type).not.toBe('')
  })

  it('同表单接口名重复（去首尾空格、区分大小写）→ 双卡片错误，不发请求', async () => {
    await mountForm('/clusters/1/resources/new')
    exposed!.name.value = 'vm001'
    exposed!.resourceType.value = 'virtual_machine'
    exposed!.addInterface()
    exposed!.cards.value[0]!.name = 'eth0'
    exposed!.addInterface()
    exposed!.cards.value[1]!.name = ' eth0 '
    await exposed!.submit()
    expect(resourcesApi.createResource).not.toHaveBeenCalled()
    expect(exposed!.fieldErrors.cards[exposed!.cards.value[0]!.key]?.name).toContain('重复')
    expect(exposed!.fieldErrors.cards[exposed!.cards.value[1]!.key]?.name).toContain('重复')
  })
})

describe('真实删除（BQ-Z 二次确认 + 删除前置 §6.2）', () => {
  it('确认输入不匹配（区分大小写）不允许提交；匹配后按 confirm+version 提交', async () => {
    await mountForm('/clusters/1/resources/7/edit')
    exposed!.openDelete()
    expect(exposed!.deleteVisible.value).toBe(true)

    // 未输入 / 大小写不符 → 不发请求
    await exposed!.submitDelete()
    expect(resourcesApi.deleteResource).not.toHaveBeenCalled()
    exposed!.deleteConfirmInput.value = 'CN001'
    expect(exposed!.deleteConfirmMatched.value).toBe(false)
    await exposed!.submitDelete()
    expect(resourcesApi.deleteResource).not.toHaveBeenCalled()

    exposed!.deleteConfirmInput.value = 'cn001'
    expect(exposed!.deleteConfirmMatched.value).toBe(true)
    await exposed!.submitDelete()
    await waitFor(() => router.currentRoute.value.name === 'clusters')
    expect(resourcesApi.deleteResource).toHaveBeenCalledWith(7, { confirm: 'cn001', version: 3 })
  })

  it('409 RESOURCE_HAS_INTERFACES → 保留对话框并引导先删网卡；确认输入保留', async () => {
    await mountForm('/clusters/1/resources/7/edit')
    vi.mocked(resourcesApi.deleteResource).mockRejectedValue(
      new ApiError(409, 'RESOURCE_HAS_INTERFACES', '仍有网卡'),
    )
    exposed!.openDelete()
    exposed!.deleteConfirmInput.value = 'cn001'
    await exposed!.submitDelete()
    await flush()
    expect(exposed!.deleteVisible.value).toBe(true)
    expect(exposed!.deleteBlockError.value).toContain('网卡')
    expect(exposed!.deleteConfirmInput.value).toBe('cn001')
  })

  it('422 DELETE_CONFIRMATION_MISMATCH → 确认错误提示，不删除', async () => {
    await mountForm('/clusters/1/resources/7/edit')
    vi.mocked(resourcesApi.deleteResource).mockRejectedValue(
      new ApiError(422, 'DELETE_CONFIRMATION_MISMATCH', '确认不匹配'),
    )
    exposed!.openDelete()
    exposed!.deleteConfirmInput.value = 'cn001'
    await exposed!.submitDelete()
    await flush()
    expect(exposed!.deleteConfirmError.value).toContain('不匹配')
    expect(exposed!.deleteVisible.value).toBe(true)
  })

  it('409 VERSION_CONFLICT → 保留对话框与输入；刷新版本后可重试', async () => {
    await mountForm('/clusters/1/resources/7/edit')
    vi.mocked(resourcesApi.deleteResource).mockRejectedValue(
      new ApiError(409, 'VERSION_CONFLICT', '并发冲突'),
    )
    exposed!.openDelete()
    exposed!.deleteConfirmInput.value = 'cn001'
    await exposed!.submitDelete()
    await flush()
    expect(exposed!.deleteVersionConflict.value).toBe(true)
    expect(exposed!.deleteVisible.value).toBe(true)
    expect(exposed!.deleteConfirmInput.value).toBe('cn001')

    // 刷新版本（保留确认输入）：他人已改名 → 名称基线更新，原输入不再匹配
    vi.mocked(resourcesApi.getResource).mockResolvedValue({ ...detail, name: 'cn001-renamed', version: 4 })
    await exposed!.refreshVersionKeepInput()
    await flush()
    expect(exposed!.version.value).toBe(4)
    expect(exposed!.deleteConfirmMatched.value).toBe(false)
    exposed!.deleteConfirmInput.value = 'cn001-renamed'
    vi.mocked(resourcesApi.deleteResource).mockClear()
    await exposed!.submitDelete()
    await flush()
    expect(resourcesApi.deleteResource).toHaveBeenCalledWith(7, {
      confirm: 'cn001-renamed',
      version: 4,
    })
  })
})

describe('权限隐藏（§7.2：viewer 只读；服务端为最终校验）', () => {
  it('viewer：canManage=false，提交/添加网卡/删除入口均不产生动作', async () => {
    useAuthStore().$patch({ user: { ...viewer } })
    await mountForm('/clusters/1/resources/7/edit')
    expect(exposed!.canManage.value).toBe(false)

    await exposed!.submit()
    expect(resourcesApi.updateResource).not.toHaveBeenCalled()

    exposed!.addInterface()
    expect(exposed!.cards.value).toHaveLength(2)

    exposed!.openDelete()
    expect(exposed!.deleteVisible.value).toBe(false)

    // 名称修改被允许（本地状态），但提交入口（submit）已由 canManage 阻止
    exposed!.name.value = 'viewer-edit'
    await exposed!.submit()
    expect(resourcesApi.updateResource).not.toHaveBeenCalled()
  })
})

describe('切换集群清除不匹配网段（§7.1：新增表单未保存时）', () => {
  it('切换到集群 2 后，原集群 1 的网段选择被清除', async () => {
    await mountForm('/clusters/1/resources/new')
    exposed!.name.value = 'vm001'
    exposed!.resourceType.value = 'virtual_machine'
    exposed!.addInterface()
    const card = exposed!.cards.value[0]!
    card.name = 'eth0'
    exposed!.setCardSegment(card, 3)
    expect(card.segmentId).toBe(3)

    await exposed!.selectCluster(2)
    await flush()
    expect(exposed!.selectedClusterId.value).toBe(2)
    expect(exposed!.segmentOptions.value.map((s) => s.id)).toEqual([5])
    // 集群 2 无网段 3 → 清除选择；接口名保留
    expect(card.segmentId).toBeNull()
    expect(card.name).toBe('eth0')
  })
})

// ---------- F006：IP 分配与管理 IP ----------

describe('IP op 映射端到端（F006 §5.1：嵌套显式操作；未列出=未修改）', () => {
  it('编辑：删既有 IP + 待分配 manual/auto + 新网卡带 IP + 删含 IP 网卡 → 嵌套 ips 显式操作', async () => {
    vi.mocked(resourcesApi.getResource).mockResolvedValue(detailWithIp)
    await mountForm('/clusters/1/resources/7/edit')
    const cards = exposed!.cards.value
    const eth0 = cards[0]!

    // 删除既有 IP 55；追加待分配 manual + auto
    exposed!.removeCardIp(eth0, eth0.ips[0]!.key)
    exposed!.addCardIp(eth0, 'manual')
    eth0.ips[1]!.address = '192.168.1.20'
    exposed!.addCardIp(eth0, 'auto')
    // 新网卡带 manual IP
    exposed!.addInterface()
    const added = exposed!.cards.value[2]!
    added.name = 'eth9'
    exposed!.setCardSegment(added, 3)
    exposed!.addCardIp(added, 'manual')
    added.ips[0]!.address = '192.168.1.21'
    // 同步删除管理 IP：显式清空（否则被 MANAGEMENT_IP_REQUIRED 前端阻断）
    exposed!.setManagementIpValue('__none__')

    await exposed!.submit()
    await flush()

    expect(resourcesApi.updateResource).toHaveBeenCalledWith(7, {
      interfaces: [
        {
          op: 'update',
          id: 10,
          ips: [
            { op: 'delete', id: 55 },
            { op: 'create', mode: 'manual', address: '192.168.1.20' },
            { op: 'create', mode: 'auto' },
          ],
        },
        {
          op: 'create',
          name: 'eth9',
          segment_id: 3,
          ips: [{ op: 'create', mode: 'manual', address: '192.168.1.21' }],
        },
      ],
      management_ip: null,
      version: 3,
    })
  })

  it('编辑：仅删除既有 IP（网卡未改名/未改网段）→ op:update 只携带 ips；未修改的既有 IP 不列入', async () => {
    vi.mocked(resourcesApi.getResource).mockResolvedValue(detailWithIp)
    await mountForm('/clusters/1/resources/7/edit')
    const eth0 = exposed!.cards.value[0]!
    exposed!.removeCardIp(eth0, eth0.ips[0]!.key) // 删除管理 IP 55
    exposed!.setManagementIpValue('__none__') // 同次显式清空
    await exposed!.submit()
    await flush()
    expect(resourcesApi.updateResource).toHaveBeenCalledWith(7, {
      interfaces: [{ op: 'update', id: 10, ips: [{ op: 'delete', id: 55 }] }],
      management_ip: null,
      version: 3,
    })
  })

  it('编辑：标记删除含 IP 的网卡 → op:delete 同项携带 IP 显式删除（INTERFACE_HAS_IPS 前置）', async () => {
    vi.mocked(resourcesApi.getResource).mockResolvedValue(detailWithIp)
    await mountForm('/clusters/1/resources/7/edit')
    const eth0 = exposed!.cards.value[0]!
    exposed!.removeInterface(eth0.key)
    exposed!.setManagementIpValue('__none__') // 管理 IP 随网卡删除：须显式清空
    await exposed!.submit()
    await flush()
    expect(resourcesApi.updateResource).toHaveBeenCalledWith(7, {
      interfaces: [{ op: 'delete', id: 10, ips: [{ op: 'delete', id: 55 }] }],
      management_ip: null,
      version: 3,
    })
  })

  it('新增提交：ips（manual/auto）+ management_ip={interface_index,address}（IP 尚无 ID，Contract F006 §1）', async () => {
    await mountForm('/clusters/1/resources/new')
    exposed!.name.value = 'cn002'
    exposed!.resourceType.value = 'bare_metal'
    exposed!.addInterface()
    const card = exposed!.cards.value[0]!
    card.name = 'eth0'
    exposed!.setCardSegment(card, 3)
    exposed!.addCardIp(card, 'manual')
    card.ips[0]!.address = '192.168.1.10'
    exposed!.addCardIp(card, 'auto')
    // 选定第 0 张网卡的 manual IP 为管理 IP
    exposed!.setManagementIpValue(`${card.key}::${card.ips[0]!.key}`)

    await exposed!.submit()
    await flush()

    expect(resourcesApi.createResource).toHaveBeenCalledWith({
      cluster_id: 1,
      name: 'cn002',
      resource_type: 'bare_metal',
      status: 'ALLOC',
      interfaces: [
        {
          name: 'eth0',
          segment_id: 3,
          ips: [
            { mode: 'manual', address: '192.168.1.10' },
            { mode: 'auto' },
          ],
        },
      ],
      management_ip: { interface_index: 0, address: '192.168.1.10' },
    })
  })

  it('编辑重选既有 IP → management_ip={ip_id}；未选择时省略（=不修改）', async () => {
    vi.mocked(resourcesApi.getResource).mockResolvedValue(detailWithIp)
    await mountForm('/clusters/1/resources/7/edit')
    const ib0 = exposed!.cards.value[1]!
    exposed!.setCardSegment(ib0, 3)
    exposed!.addCardIp(ib0, 'manual')
    ib0.ips[0]!.address = '192.168.1.99'
    // 重选到新 IP（本请求内新建 → interface_index）
    exposed!.setManagementIpValue(`${ib0.key}::${ib0.ips[0]!.key}`)
    await exposed!.submit()
    await flush()
    expect(resourcesApi.updateResource).toHaveBeenCalledWith(7, {
      interfaces: [
        { op: 'update', id: 11, segment_id: 3, ips: [{ op: 'create', mode: 'manual', address: '192.168.1.99' }] },
      ],
      management_ip: { interface_index: 0, address: '192.168.1.99' },
      version: 3,
    })
  })

  it('编辑重选未修改网卡上的既有 IP → management_ip={ip_id}（无需 interface_index，网卡可不列入 interfaces[]）', async () => {
    vi.mocked(resourcesApi.getResource).mockResolvedValue(detailWithIp)
    await mountForm('/clusters/1/resources/7/edit')
    const eth0 = exposed!.cards.value[0]!
    // 直接把管理 IP 重选到同一既有 IP（ip_id 55，网卡未修改）
    exposed!.setManagementIpValue(`${eth0.key}::${eth0.ips[0]!.key}`)
    await exposed!.submit()
    await flush()
    expect(resourcesApi.updateResource).toHaveBeenCalledWith(7, {
      management_ip: { ip_id: 55 },
      version: 3,
    })
  })

  it('保存成功后以响应重建基线：IP 与管理 IP 回显、「保持当前」重置', async () => {
    vi.mocked(resourcesApi.getResource).mockResolvedValue(detailWithIp)
    await mountForm('/clusters/1/resources/7/edit')
    // 服务端响应含既有 IP 55 与新建的 192.168.1.20（按地址数值升序）
    const saved: ResourceFormDetail = {
      ...detailWithIp,
      version: 4,
      interfaces: [
        {
          ...detailWithIp.interfaces[0]!,
          ips: [
            ...detailWithIp.interfaces[0]!.ips,
            {
              id: 80,
              address: '192.168.1.20',
              segment_id: 3,
              interface_id: 10,
              is_management: false,
              created_at: NOW,
            },
          ],
        },
        detailWithIp.interfaces[1]!,
      ],
    }
    vi.mocked(resourcesApi.updateResource).mockResolvedValue(saved)
    const eth0 = exposed!.cards.value[0]!
    exposed!.addCardIp(eth0, 'manual')
    eth0.ips[1]!.address = '192.168.1.20'
    await exposed!.submit()
    await flush()
    expect(exposed!.version.value).toBe(4)
    expect(exposed!.cards.value[0]!.ips.map((ip) => ip.address)).toEqual(['192.168.1.10', '192.168.1.20'])
    expect(exposed!.managementIpValue.value).toBe('__keep__')
    expect(exposed!.managementKeepLabel.value).toContain('192.168.1.10')
  })
})

describe('未选网段禁用分配（§4.6.7、场景 31：分配 IP 前必须选定网段）', () => {
  it('未选网段时 addCardIp 不产生条目；选定网段后可分配', async () => {
    await mountForm('/clusters/1/resources/new')
    exposed!.name.value = 'vm001'
    exposed!.resourceType.value = 'virtual_machine'
    exposed!.addInterface()
    const card = exposed!.cards.value[0]!
    card.name = 'ib0'
    expect(card.segmentId).toBeNull()
    exposed!.addCardIp(card, 'manual')
    exposed!.addCardIp(card, 'auto')
    expect(card.ips).toHaveLength(0)

    exposed!.setCardSegment(card, 3)
    exposed!.addCardIp(card, 'manual')
    exposed!.addCardIp(card, 'auto')
    expect(card.ips).toHaveLength(2)
    expect(card.ips[0]).toMatchObject({ mode: 'manual', address: '' })
    expect(card.ips[1]).toMatchObject({ mode: 'auto' })
  })

  it('网段选项携带自动分配范围信息（autoAllocEnabled；供视图禁用「自动分配」，服务端权威）', async () => {
    await mountForm('/clusters/1/resources/7/edit')
    expect(exposed!.segmentSummary(3)?.autoAllocEnabled).toBe(false)
    // 启用自动范围的网段
    vi.mocked(listNetworkSegments).mockImplementation(async () => ({
      items: [{ ...CLUSTER_1_SEGMENTS[0]!, auto_alloc_start: '192.168.1.20', auto_alloc_end: '192.168.1.30', auto_alloc_enabled: true }],
      total: 1,
      page: 1,
      page_size: 100,
    }))
    await exposed!.retryLoadSegments()
    await flush()
    expect(exposed!.segmentSummary(3)?.autoAllocEnabled).toBe(true)
  })
})

describe('切换网段（§7.4：清除待分配地址；既有 IP 须显式释放）', () => {
  it('切换网段清除原网段的待分配地址（manual/auto），既有 IP 保留', async () => {
    vi.mocked(resourcesApi.getResource).mockResolvedValue(detailWithIp)
    await mountForm('/clusters/1/resources/7/edit')
    const eth0 = exposed!.cards.value[0]!
    exposed!.addCardIp(eth0, 'manual')
    eth0.ips[1]!.address = '192.168.1.20'
    exposed!.addCardIp(eth0, 'auto')

    exposed!.setCardSegment(eth0, 3) // 同值：不清除
    expect(eth0.ips).toHaveLength(3)

    exposed!.setCardSegment(eth0, null) // 清空网段：待分配清除、既有保留
    expect(eth0.ips).toHaveLength(1)
    expect(eth0.ips[0]!.id).toBe(55)
  })

  it('已有 IP 的网卡改网段但未释放旧 IP → 前端阻断（INTERFACE_SEGMENT_CHANGE_REQUIRES_IP_RELEASE），不发请求', async () => {
    vi.mocked(resourcesApi.getResource).mockResolvedValue(detailWithIp)
    await mountForm('/clusters/1/resources/7/edit')
    const eth0 = exposed!.cards.value[0]!
    exposed!.setCardSegment(eth0, 5) // 3 → 5，仍保留 IP 55
    await exposed!.submit()
    expect(resourcesApi.updateResource).not.toHaveBeenCalled()
    expect(exposed!.fieldErrors.cards[eth0.key]?.segment_id).toContain('释放')

    // 显式删除旧 IP + 同次显式清空管理 IP 后允许提交（新网段重新分配）
    exposed!.removeCardIp(eth0, eth0.ips[0]!.key)
    exposed!.setManagementIpValue('__none__')
    await exposed!.submit()
    await flush()
    expect(resourcesApi.updateResource).toHaveBeenCalledWith(7, {
      interfaces: [
        { op: 'update', id: 10, segment_id: 5, ips: [{ op: 'delete', id: 55 }] },
      ],
      management_ip: null,
      version: 3,
    })
  })
})

describe('管理 IP 强制清空/重选（§4.2.11、场景 46：MANAGEMENT_IP_REQUIRED 前端阻断）', () => {
  it('删除当前管理 IP 但未显式清空/重选 → 提交阻断并提示，不发请求；输入保留', async () => {
    vi.mocked(resourcesApi.getResource).mockResolvedValue(detailWithIp)
    await mountForm('/clusters/1/resources/7/edit')
    const eth0 = exposed!.cards.value[0]!
    exposed!.removeCardIp(eth0, eth0.ips[0]!.key)
    await exposed!.submit()
    expect(resourcesApi.updateResource).not.toHaveBeenCalled()
    expect(exposed!.fieldErrors.management_ip).toContain('显式清空或重选')
    // 输入保留：IP 仍标记删除（用户意图保留）
    expect(eth0.ips[0]!.removed).toBe(true)
  })

  it('删除管理 IP 所在网卡但未显式清空/重选 → 同样阻断', async () => {
    vi.mocked(resourcesApi.getResource).mockResolvedValue(detailWithIp)
    await mountForm('/clusters/1/resources/7/edit')
    const eth0 = exposed!.cards.value[0]!
    exposed!.removeInterface(eth0.key)
    await exposed!.submit()
    expect(resourcesApi.updateResource).not.toHaveBeenCalled()
    expect(exposed!.fieldErrors.management_ip).toContain('显式清空或重选')
  })

  it('显式清空（无管理 IP）后允许提交：management_ip=null', async () => {
    vi.mocked(resourcesApi.getResource).mockResolvedValue(detailWithIp)
    await mountForm('/clusters/1/resources/7/edit')
    const eth0 = exposed!.cards.value[0]!
    exposed!.removeCardIp(eth0, eth0.ips[0]!.key)
    exposed!.setManagementIpValue('__none__')
    await exposed!.submit()
    await flush()
    expect(resourcesApi.updateResource).toHaveBeenCalledWith(7, {
      interfaces: [{ op: 'update', id: 10, ips: [{ op: 'delete', id: 55 }] }],
      management_ip: null,
      version: 3,
    })
  })

  it('仅清空管理 IP（无其它修改）→ 允许提交（management_ip:null 是有效变更）', async () => {
    vi.mocked(resourcesApi.getResource).mockResolvedValue(detailWithIp)
    await mountForm('/clusters/1/resources/7/edit')
    exposed!.setManagementIpValue('__none__')
    await exposed!.submit()
    await flush()
    expect(resourcesApi.updateResource).toHaveBeenCalledWith(7, {
      management_ip: null,
      version: 3,
    })
  })

  it('所选候选 IP 被删除后 → 提交阻断并提示重选；重选后可提交', async () => {
    vi.mocked(resourcesApi.getResource).mockResolvedValue(detailWithIp)
    await mountForm('/clusters/1/resources/7/edit')
    const eth0 = exposed!.cards.value[0]!
    exposed!.addCardIp(eth0, 'manual')
    eth0.ips[1]!.address = '192.168.1.20'
    exposed!.setManagementIpValue(`${eth0.key}::${eth0.ips[1]!.key}`)
    exposed!.removeCardIp(eth0, eth0.ips[1]!.key) // 选出后删除该候选
    await exposed!.submit()
    expect(resourcesApi.updateResource).not.toHaveBeenCalled()
    expect(exposed!.fieldErrors.management_ip).toContain('重新选择')

    exposed!.setManagementIpValue('__none__')
    await exposed!.submit()
    await flush()
    expect(resourcesApi.updateResource).toHaveBeenCalledTimes(1)
  })

  it('候选列表：既有未删与待分配 manual（非空地址）参与；auto 与已删除不参与', async () => {
    vi.mocked(resourcesApi.getResource).mockResolvedValue(detailWithIp)
    await mountForm('/clusters/1/resources/7/edit')
    const eth0 = exposed!.cards.value[0]!
    exposed!.addCardIp(eth0, 'manual')
    eth0.ips[1]!.address = '192.168.1.20'
    exposed!.addCardIp(eth0, 'auto')
    const candidates = exposed!.managementIpCandidates.value
    expect(candidates.map((c) => c.address)).toEqual(['192.168.1.10', '192.168.1.20'])
    // 标记删除后从候选移除
    exposed!.removeCardIp(eth0, eth0.ips[0]!.key)
    expect(exposed!.managementIpCandidates.value.map((c) => c.address)).toEqual(['192.168.1.20'])
  })
})

describe('IP 字段级错误定位与冲突展示（F006 §7.3/§0）', () => {
  it('422 VALIDATION_ERROR：interfaces[0].ips[0].address（IP_OUT_OF_SEGMENT）定位到具体 IP 条目，输入保留', async () => {
    await mountForm('/clusters/1/resources/new')
    exposed!.name.value = 'vm001'
    exposed!.resourceType.value = 'virtual_machine'
    exposed!.addInterface()
    const card = exposed!.cards.value[0]!
    card.name = 'eth0'
    exposed!.setCardSegment(card, 3)
    exposed!.addCardIp(card, 'manual')
    // 192.168.1.100 在 CIDR 内（本机可判的越界已由前端校验拦截；保留地址等仅服务端可知）
    card.ips[0]!.address = '192.168.1.100'
    vi.mocked(resourcesApi.createResource).mockRejectedValue(
      new ApiError(422, 'VALIDATION_ERROR', '字段校验失败', [
        { field: 'interfaces[0].ips[0].address', code: 'IP_RESERVED', message: '192.168.1.100 命中保留地址' },
      ]),
    )
    await exposed!.submit()
    await flush()
    const ipKey = card.ips[0]!.key
    expect(exposed!.fieldErrors.cards[card.key]?.ips[ipKey]?.address).toBe('192.168.1.100 命中保留地址')
    expect(card.ips[0]!.address).toBe('192.168.1.100') // 冲突保留输入
  })

  it('409 IP_ALREADY_IN_USE：conflicts 归属展示 + errors[] 定位 + 输入保留', async () => {
    await mountForm('/clusters/1/resources/new')
    exposed!.name.value = 'vm001'
    exposed!.resourceType.value = 'virtual_machine'
    exposed!.addInterface()
    const card = exposed!.cards.value[0]!
    card.name = 'eth0'
    exposed!.setCardSegment(card, 3)
    exposed!.addCardIp(card, 'manual')
    card.ips[0]!.address = '192.168.1.10'
    vi.mocked(resourcesApi.createResource).mockRejectedValue(
      new ApiError(
        409,
        'IP_ALREADY_IN_USE',
        'IP 已被占用',
        [{ field: 'interfaces[0].ips[0].address', code: 'IP_ALREADY_IN_USE', message: '192.168.1.10 已被本集群使用' }],
        {
          conflicts: [
            { ip: '192.168.1.10', resource_id: 7, resource_name: 'cn002', interface_id: 12, interface_name: 'ib0' },
          ],
        },
      ),
    )
    await exposed!.submit()
    await flush()
    expect(exposed!.formNotice.value).toBe('192.168.1.10 已被本集群 cn002/ib0 使用')
    expect(exposed!.fieldErrors.cards[card.key]?.ips[card.ips[0]!.key]?.address).toBe('192.168.1.10 已被本集群使用')
    expect(card.ips[0]!.address).toBe('192.168.1.10') // 冲突保留输入
  })

  it('409 NO_AVAILABLE_ADDRESS（errors[] 裸 ips[j]）→ 定位到 IP 条目 + 记录级提示，不切换网段', async () => {
    await mountForm('/clusters/1/resources/new')
    exposed!.name.value = 'vm001'
    exposed!.resourceType.value = 'virtual_machine'
    exposed!.addInterface()
    const card = exposed!.cards.value[0]!
    card.name = 'eth0'
    exposed!.setCardSegment(card, 3)
    exposed!.addCardIp(card, 'auto')
    vi.mocked(resourcesApi.createResource).mockRejectedValue(
      new ApiError(409, 'NO_AVAILABLE_ADDRESS', '自动分配范围内暂无可用地址', [
        { field: 'interfaces[0].ips[0]', code: 'NO_AVAILABLE_ADDRESS', message: '自动分配范围内暂无可用地址' },
      ]),
    )
    await exposed!.submit()
    await flush()
    const ipKey = card.ips[0]!.key
    expect(exposed!.fieldErrors.cards[card.key]?.ips[ipKey]?.other).toBe('自动分配范围内暂无可用地址')
    expect(exposed!.formNotice.value).toContain('不会自动切换')
    expect(card.segmentId).toBe(3) // 不切换网段
  })

  it('422 MANAGEMENT_IP_REQUIRED（服务端返回）→ 管理 IP 字段错误（前端预检漏网时兜底）', async () => {
    vi.mocked(resourcesApi.getResource).mockResolvedValue(detailWithIp)
    await mountForm('/clusters/1/resources/7/edit')
    vi.mocked(resourcesApi.updateResource).mockRejectedValue(
      new ApiError(422, 'MANAGEMENT_IP_REQUIRED', '删除管理 IP 或其网卡前须同次显式清空或重选管理 IP'),
    )
    // 不改动管理 IP 选择（keep）但让其它字段变化触发提交
    exposed!.name.value = 'cn001-x'
    await exposed!.submit()
    await flush()
    expect(exposed!.fieldErrors.management_ip).toContain('显式清空或重选')
  })
})

describe('IP 前端基础校验（§7.2：语法 / CIDR 内 / 同表单重复；不发请求）', () => {
  it('manual 地址非法 / 越出所选网段 → IP 条目错误，不发请求', async () => {
    await mountForm('/clusters/1/resources/new')
    exposed!.name.value = 'vm001'
    exposed!.resourceType.value = 'virtual_machine'
    exposed!.addInterface()
    const card = exposed!.cards.value[0]!
    card.name = 'eth0'
    exposed!.setCardSegment(card, 3)

    exposed!.addCardIp(card, 'manual')
    card.ips[0]!.address = '300.1.1.1'
    await exposed!.submit()
    expect(resourcesApi.createResource).not.toHaveBeenCalled()
    expect(exposed!.fieldErrors.cards[card.key]?.ips[card.ips[0]!.key]?.address).toContain('IPv4')

    card.ips[0]!.address = '10.99.0.1' // 语法合法但不在 192.168.1.0/24 内
    await exposed!.submit()
    expect(resourcesApi.createResource).not.toHaveBeenCalled()
    expect(exposed!.fieldErrors.cards[card.key]?.ips[card.ips[0]!.key]?.address).toContain('CIDR')

    card.ips[0]!.address = '192.168.1.50' // 网段内（保留/网关/网络/广播由服务端权威拒绝）
    await exposed!.submit()
    await flush()
    expect(resourcesApi.createResource).toHaveBeenCalledTimes(1)
  })

  it('同表单重复 IP（跨网卡、与既有未删重复）→ 双条目错误，不发请求', async () => {
    vi.mocked(resourcesApi.getResource).mockResolvedValue(detailWithIp)
    await mountForm('/clusters/1/resources/7/edit')
    const eth0 = exposed!.cards.value[0]!
    const ib0 = exposed!.cards.value[1]!
    exposed!.setCardSegment(ib0, 3)
    exposed!.addCardIp(ib0, 'manual')
    ib0.ips[0]!.address = '192.168.1.10' // 与 eth0 既有 IP 55 重复
    exposed!.addCardIp(ib0, 'manual')
    ib0.ips[1]!.address = '192.168.1.10' // 本网卡内重复
    await exposed!.submit()
    expect(resourcesApi.updateResource).not.toHaveBeenCalled()
    const eth0IpKey = eth0.ips[0]!.key
    expect(exposed!.fieldErrors.cards[eth0.key]?.ips[eth0IpKey]?.address).toContain('重复')
    expect(exposed!.fieldErrors.cards[ib0.key]?.ips[ib0.ips[0]!.key]?.address).toContain('重复')
    expect(exposed!.fieldErrors.cards[ib0.key]?.ips[ib0.ips[1]!.key]?.address).toContain('重复')
  })
})

describe('权限隐藏（F006：viewer 只读；服务端为最终校验）', () => {
  it('viewer：IP 增删与管理 IP 选择均不产生动作', async () => {
    useAuthStore().$patch({ user: { ...viewer } })
    vi.mocked(resourcesApi.getResource).mockResolvedValue(detailWithIp)
    await mountForm('/clusters/1/resources/7/edit')
    expect(exposed!.canManage.value).toBe(false)
    const eth0 = exposed!.cards.value[0]!
    const before = eth0.ips[0]!.removed
    exposed!.addCardIp(eth0, 'manual')
    expect(eth0.ips).toHaveLength(1)
    exposed!.removeCardIp(eth0, eth0.ips[0]!.key)
    expect(eth0.ips[0]!.removed).toBe(before)
    exposed!.setManagementIpValue('__none__')
    expect(exposed!.managementIpValue.value).toBe('__keep__')
    await exposed!.submit()
    expect(resourcesApi.updateResource).not.toHaveBeenCalled()
  })
})
