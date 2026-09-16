/**
 * VirtualMachine 产品 API 客户端。
 *
 * 契约依据：docs/api/f006-virtual-machine.md（READY，唯一权威）。
 * - 字段集合封闭（契约 §2）：恰为 11 字段；不存在 deleted_at、status /
 *   cluster_id（VM 无状态 Q-002=B；Cluster 归属由宿主推导 R-VM-005）、
 *   NIC / IP / Container / Service / 位置 / 平台同步字段；
 * - R-VM-006 六字段（cpu / memory / disk / os / hypervisor / owner）均为
 *   string | null：未登记为 null，响应返回 null 而非省略（api-conventions §4）；
 * - name 为必填身份标识，全局活跃唯一、大小写敏感（R-VM-004）；原样存取，
 *   不 trim、不归一化、不做长度 / 空串 / 字符分支（契约 §7 undefined_constraints）；
 * - hypervisor 仅是文本登记字段，不代表任何虚拟化平台接入（R-VM-002）；
 * - 时间字段为 RFC 3339 不透明字符串，不解析、不假设时区（契约 §2）；
 * - 写操作一律走 id（ADR-0003）；PATCH 可变字段封闭为六字段，name /
 *   bare_metal_id 不可变（NQ-1，登记后不可变）；错误语义由 api/http.ts
 *   统一解析为 ApiError，消费方按 error.code 分支，不解析 message。
 */
import type { PageParams, Paginated } from '../types/api'
import { apiRequest } from './http'

/** VirtualMachine 资源表示（契约 §2；所有返回单对象的端点共用该结构）。 */
export interface VirtualMachineRead {
  /** 不可变代理主键；写操作一律使用该值（ADR-0003）。 */
  id: number
  /** 宿主 BareMetal 的 id（R-VM-005，必属恰好一个宿主）。 */
  bare_metal_id: number
  /** 身份标识；全局活跃唯一、大小写敏感（R-VM-004）；原样存取（契约 §7）。 */
  name: string
  /** R-VM-006 可选字段：可选、纯文本、未登记为 null。 */
  cpu: string | null
  memory: string | null
  disk: string | null
  os: string | null
  /** 纯文本登记字段；不代表平台接入（R-VM-002）。 */
  hypervisor: string | null
  owner: string | null
  /** 登记时间（RFC 3339 不透明字符串）。 */
  created_at: string
  /** 最近更新时间（RFC 3339 不透明字符串；不是并发控制依据）。 */
  updated_at: string
}

/** R-VM-006 可选字段键列表（登记 / 编辑表单与详情展示共用）。 */
export const VIRTUAL_MACHINE_OPTIONAL_FIELDS = [
  'cpu',
  'memory',
  'disk',
  'os',
  'hypervisor',
  'owner',
] as const

/** R-VM-006 可选字段键。 */
export type VirtualMachineOptionalField = (typeof VIRTUAL_MACHINE_OPTIONAL_FIELDS)[number]

/** 登记 VirtualMachine 请求体（契约 §3.1）。bare_metal_id + name 必填，六字段可选。 */
export interface VirtualMachineCreateBody {
  /** 宿主 BareMetal 的 id；必须存在且活跃（由服务端裁决，不存在 / 已删 → 404）。 */
  bare_metal_id: number
  /** 全局活跃唯一、大小写敏感（由服务端裁决，重复 → 409）；不做任何前端校验。 */
  name: string
  /** R-VM-006 字段：缺省 / null 均存为 null。 */
  cpu?: string | null
  memory?: string | null
  disk?: string | null
  os?: string | null
  hypervisor?: string | null
  owner?: string | null
}

/**
 * 更新 VirtualMachine 请求体（契约 §3.4，部分更新）。
 * 可变字段封闭为 R-VM-006 六字段；id / bare_metal_id / name / created_at
 * 不可变（NQ-1），不得出现在请求体中。
 */
export interface VirtualMachineUpdateBody {
  /** 提供 null 表示清空该字段；缺省表示不修改。 */
  cpu?: string | null
  memory?: string | null
  disk?: string | null
  os?: string | null
  hypervisor?: string | null
  owner?: string | null
}

/** 列表查询参数（契约 §3.2）。 */
export interface VirtualMachineListParams extends PageParams {
  /** 按宿主 BareMetal 限定（R-QUERY-003 的 F006 侧 canonical 能力）；未提供时返回全部活跃 VM。 */
  bareMetalId?: number
}

/**
 * 列出活跃 VirtualMachine（契约 §3.2）。
 *
 * - 未提供 bareMetalId → 全部活跃 VM；无活跃 → 200 + items == []（Empty）；
 * - 提供 bareMetalId → 该宿主的活跃 VM：宿主不存在或已逻辑删除 →
 *   404 NOT_FOUND（Not Found，与 Empty 是不同状态）；宿主存在但无活跃
 *   VM → 200 + items == []（Empty）；
 * - 已逻辑删除的 VM 不出现在 items / total（R-DELETE-002）。
 */
export function listVirtualMachines(
  params: VirtualMachineListParams = {},
): Promise<Paginated<VirtualMachineRead>> {
  return apiRequest<Paginated<VirtualMachineRead>>('/api/virtual-machines', {
    method: 'GET',
    query: {
      page: params.page,
      page_size: params.page_size,
      bare_metal_id: params.bareMetalId,
    },
  })
}

/**
 * 按 id 读取 VirtualMachine（契约 §3.3，规范路径）。
 * 不存在或已被逻辑删除 → 404 NOT_FOUND（两者不区分）。
 */
export function getVirtualMachine(virtualMachineId: number): Promise<VirtualMachineRead> {
  return apiRequest<VirtualMachineRead>(`/api/virtual-machines/${virtualMachineId}`, {
    method: 'GET',
  })
}

/**
 * 登记 VirtualMachine（契约 §3.1）。成功 → 201 + VirtualMachineRead。
 * 全局 name 唯一性（409）、宿主存在性 / 活跃性（404）、字段合法性（400）
 * 均由服务端裁决（§21）。
 */
export function createVirtualMachine(
  body: VirtualMachineCreateBody,
): Promise<VirtualMachineRead> {
  return apiRequest<VirtualMachineRead>('/api/virtual-machines', {
    method: 'POST',
    body,
  })
}

/**
 * 更新 R-VM-006 可选字段（契约 §3.4，部分更新）。成功 → 200 + VirtualMachineRead。
 * 请求体至少含一个可变字段（空 body → 400）；name / bare_metal_id 不在可变集内。
 */
export function updateVirtualMachine(
  virtualMachineId: number,
  body: VirtualMachineUpdateBody,
): Promise<VirtualMachineRead> {
  return apiRequest<VirtualMachineRead>(`/api/virtual-machines/${virtualMachineId}`, {
    method: 'PATCH',
    body,
  })
}

/**
 * 逻辑删除 VirtualMachine（契约 §3.5）。
 *
 * - `DELETE /api/virtual-machines/{virtual_machine_id}`：写操作一律走 id；
 * - 成功 → 204（无响应体，apiRequest 归一为 undefined，不抛出）；
 * - 404 NOT_FOUND：不存在或已被逻辑删除（两者不区分，重复删除亦 404）；
 * - 409 CONFLICT：目标存在活跃子资源（details[].code === 'ACTIVE_CHILDREN_EXIST'；
 *   当前 VM 无子资源表，该分支在本 Feature 内不可达，由 F007 落地 Container 后
 *   触发；不得因此假定「VM 永远无子资源」）；
 * - 401 UNAUTHENTICATED：由全局会话失效处理；
 * - 不发送请求体（契约 §3.5：客户端不得发送）。
 */
export function deleteVirtualMachine(virtualMachineId: number): Promise<void> {
  return apiRequest<void>(`/api/virtual-machines/${virtualMachineId}`, { method: 'DELETE' })
}
