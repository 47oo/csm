/**
 * Container 产品 API 客户端。
 *
 * 契约依据：docs/api/f007-container.md（READY，唯一权威）。
 * - 字段集合封闭（契约 §2）：恰为 10 字段；不存在 deleted_at（不对外暴露）、
 *   status 或任何状态字段（Q-002=B，Container 无状态）、cluster_id / cluster /
 *   cluster_name（Cluster 归属由载体推导、不持久化，R-CONTAINER-002）、
 *   bare_metal_id / virtual_machine_id（存储层原始列名，API 层不暴露）、
 *   NIC / IP / Service 字段与 K8s / Docker / Runtime / 位置字段（R-CONTAINER-001；
 *   契约 §10）；
 * - 载体身份 = (carrier_type, carrier_id) 二元组（契约 §3）：carrier_type 为
 *   封闭枚举 {"BARE_METAL", "VIRTUAL_MACHINE"}（R-CONTAINER-002），carrier_id
 *   为载体在该类型表中的 id；请求体、响应体与按载体读取 query 统一使用该对；
 * - R-CONTAINER-004 四字段（image / cpu / memory / owner）均为 string | null：
 *   可选、纯文本、不结构化、不拆分 / 不归一；未登记为 null，响应返回 null
 *   而非省略（api-conventions.md §4）；
 * - name 为必填身份标识，同一载体内活跃唯一、大小写敏感（R-CONTAINER-003）；
 *   原样存取，不 trim、不归一化、不做长度 / 空串 / 字符 / 格式分支（契约 §8
 *   undefined_constraints）；
 * - 时间字段为 RFC 3339 不透明字符串，不解析、不假设时区（契约 §2）；
 * - 写操作一律走 id（ADR-0003）；PATCH 可变字段封闭为四字段，name / 载体绑定 /
 *   created_at 不可变（NQ-1，登记后不可变）；错误语义由 api/http.ts 统一解析为
 *   ApiError，消费方按 error.code（必要时结合 details[].code）分支，不解析 message。
 */
import type { PageParams, Paginated } from '../types/api'
import { apiRequest } from './http'

/** 载体类型封闭集合（契约 §2；R-CONTAINER-002：BareMetal 或 VirtualMachine 二选一）。 */
export const CONTAINER_CARRIER_TYPES = ['BARE_METAL', 'VIRTUAL_MACHINE'] as const

/** 载体类型（契约 §2 枚举）。 */
export type ContainerCarrierType = (typeof CONTAINER_CARRIER_TYPES)[number]

/** 载体身份：(carrier_type, carrier_id) 二元组（契约 §3）。 */
export interface ContainerCarrier {
  carrier_type: ContainerCarrierType
  carrier_id: number
}

/** Container 资源表示（契约 §2；所有返回单对象的端点共用该结构）。 */
export interface ContainerRead {
  /** 不可变代理主键；写操作一律使用该值（ADR-0003）。 */
  id: number
  /** 载体类型（封闭枚举）；由存储层非空载体列派生，不由客户端写入。 */
  carrier_type: ContainerCarrierType
  /** 载体在该类型表中的 id；与 carrier_type 共同构成载体身份。 */
  carrier_id: number
  /** 身份标识；同一载体内活跃唯一、大小写敏感（R-CONTAINER-003）；原样存取（契约 §8）。 */
  name: string
  /** R-CONTAINER-004 可选字段：可选、纯文本、未登记为 null。 */
  image: string | null
  cpu: string | null
  memory: string | null
  owner: string | null
  /** 登记时间（RFC 3339 不透明字符串）。 */
  created_at: string
  /** 最近更新时间（RFC 3339 不透明字符串；不是并发控制依据）。 */
  updated_at: string
}

/** R-CONTAINER-004 可选字段键列表（登记 / 编辑表单与详情展示共用）。 */
export const CONTAINER_OPTIONAL_FIELDS = ['image', 'cpu', 'memory', 'owner'] as const

/** R-CONTAINER-004 可选字段键。 */
export type ContainerOptionalField = (typeof CONTAINER_OPTIONAL_FIELDS)[number]

/** 登记 Container 请求体（契约 §4.1）。载体对 + name 必填，四字段可选。 */
export interface ContainerCreateBody extends ContainerCarrier {
  /** 同一载体内活跃唯一、大小写敏感（由服务端裁决，重复 → 409）；不做任何前端校验。 */
  name: string
  /** R-CONTAINER-004 字段：缺省 / null 均存为 null。 */
  image?: string | null
  cpu?: string | null
  memory?: string | null
  owner?: string | null
}

/**
 * 更新 Container 请求体（契约 §4.4，部分更新）。
 * 可变字段封闭为 R-CONTAINER-004 四字段；id / carrier_type / carrier_id / name /
 * created_at 不可变（NQ-1），不得出现在请求体中。
 */
export interface ContainerUpdateBody {
  /** 提供 null 表示清空该字段；缺省表示不修改。 */
  image?: string | null
  cpu?: string | null
  memory?: string | null
  owner?: string | null
}

/** 列表查询参数（契约 §4.2）。 */
export interface ContainerListParams extends PageParams {
  /**
   * 按载体限定（R-QUERY-003 的 F007 侧 canonical 能力，供 F010 复用、不得另写
   * 一份过滤）：carrier_type 与 carrier_id 必须成对出现（仅提供其一 → 400），
   * 故以单一对象表达，结构上不可只携带其一；未提供时返回全部活跃 Container。
   */
  carrier?: ContainerCarrier | null
}

/**
 * 列出活跃 Container（契约 §4.2）。
 *
 * - 未提供 carrier → 全部活跃 Container；无活跃 → 200 + items == []（Empty）；
 * - 提供 carrier → 该载体的活跃 Container：载体不存在 / 已逻辑删除 / 类型与
 *   标识不一致 → 404 NOT_FOUND（Not Found，与 Empty 是不同状态）；载体存在
 *   但无活跃 Container → 200 + items == []（Empty）；
 * - 已逻辑删除的 Container 不出现在 items / total（R-DELETE-002）。
 */
export function listContainers(
  params: ContainerListParams = {},
): Promise<Paginated<ContainerRead>> {
  return apiRequest<Paginated<ContainerRead>>('/api/containers', {
    method: 'GET',
    query: {
      page: params.page,
      page_size: params.page_size,
      carrier_type: params.carrier?.carrier_type,
      carrier_id: params.carrier?.carrier_id,
    },
  })
}

/**
 * 按 id 读取 Container（契约 §4.3，规范路径）。
 * 不存在或已被逻辑删除 → 404 NOT_FOUND（两者不区分）。
 */
export function getContainer(containerId: number): Promise<ContainerRead> {
  return apiRequest<ContainerRead>(`/api/containers/${containerId}`, { method: 'GET' })
}

/**
 * 登记 Container（契约 §4.1）。成功 → 201 + ContainerRead。
 * 载体内 name 唯一性（409）、载体存在性 / 活跃性 / 类型一致性（404）、字段
 * 合法性（400，含请求携带未识别字段）均由服务端裁决（§21）。
 */
export function createContainer(body: ContainerCreateBody): Promise<ContainerRead> {
  return apiRequest<ContainerRead>('/api/containers', { method: 'POST', body })
}

/**
 * 更新 R-CONTAINER-004 可选字段（契约 §4.4，部分更新）。成功 → 200 + ContainerRead；
 * id / carrier_type / carrier_id / name / created_at 保持不变。请求体至少含一个
 * 可变字段（空 body → 400，服务端裁决）。
 */
export function updateContainer(
  containerId: number,
  body: ContainerUpdateBody,
): Promise<ContainerRead> {
  return apiRequest<ContainerRead>(`/api/containers/${containerId}`, {
    method: 'PATCH',
    body,
  })
}

/**
 * 逻辑删除 Container（契约 §4.5）。
 *
 * - `DELETE /api/containers/{container_id}`：写操作一律走 id；
 * - 成功 → 204（无响应体，apiRequest 归一为 undefined，不抛出）；
 * - 404 NOT_FOUND：不存在或已被逻辑删除（两者不区分，重复删除亦 404）；
 * - 409 CONFLICT：目标存在活跃子资源（details[].code === 'ACTIVE_CHILDREN_EXIST'；
 *   当前 CONTAINER_ACTIVE_CHILD_CHECKS 为显式空元组（Service 表尚不存在），该
 *   分支在本 Feature 内不可达，由 F008 落地 Service 后触发；不得因此假定
 *   「Container 永远无子资源」）；
 * - 401 UNAUTHENTICATED：由全局会话失效处理；
 * - 不发送请求体（契约 §4.5：客户端不得发送）。
 */
export function deleteContainer(containerId: number): Promise<void> {
  return apiRequest<void>(`/api/containers/${containerId}`, { method: 'DELETE' })
}
