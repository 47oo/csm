/**
 * Service 产品 API 客户端。
 *
 * 契约依据：docs/api/f008-service.md（READY，唯一权威）。
 * - 字段集合封闭（契约 §2）：ServiceRead 恰为 11 字段；不存在 deleted_at
 *   （不对外暴露）、status 或任何状态字段（Q-002=B，Service 无状态）、
 *   cluster_id / cluster / cluster_name（Cluster 归属由载体推导、不持久化，
 *   R-SVC-004/006）、bare_metal_id / virtual_machine_id / container_id
 *   （存储层原始列名，API 层不暴露；载体统一由 carriers 表达）；
 * - 载体身份 = (carrier_type, carrier_id) 二元组（契约 §3）：carrier_type 为
 *   封闭三值集合 {"BARE_METAL", "VIRTUAL_MACHINE", "CONTAINER"}（字面量与
 *   F007 一致并扩展 CONTAINER，R-SVC-002）；carriers 为 N:M 绑定集合，
 *   至少 1 项（R-SVC-005），同一请求内重复给出同一载体 → 400（契约 §4.1）；
 * - 6 个可选字段（service_type / url / port / protocol / owner / description）
 *   均为 string | null：可选、纯文本、不结构化、不拆分 / 不归一；未登记为
 *   null，响应返回 null 而非省略（api-conventions.md §4）；
 * - name 为必填身份标识，在所有当前有效 Service 范围内全局唯一、大小写
 *   敏感（R-SVC-008）；原样存取，不 trim、不归一化、不做长度 / 空串 /
 *   字符 / 格式分支（契约 §8 undefined_constraints）；
 * - 绑定在登记时一次确定、登记后不可变（NQ-01 用户确认）：PATCH 可变字段
 *   封闭为 6 个可选字段，name / carriers 不可变，不存在解绑 / 替换路径；
 * - 时间字段为 RFC 3339 不透明字符串，不解析、不假设时区（契约 §2）；
 * - 写操作一律走 id（ADR-0003）；错误语义由 api/http.ts 统一解析为
 *   ApiError，消费方按 error.code（必要时结合 details[].code）分支，
 *   不解析 message。
 */
import type { PageParams, Paginated } from '../types/api'
import { apiRequest } from './http'

/** 载体类型封闭集合（契约 §2；R-SVC-002：BareMetal / VirtualMachine / Container 三选一）。 */
export const SERVICE_CARRIER_TYPES = ['BARE_METAL', 'VIRTUAL_MACHINE', 'CONTAINER'] as const

/** 载体类型（契约 §2 枚举）。 */
export type ServiceCarrierType = (typeof SERVICE_CARRIER_TYPES)[number]

/** 载体身份：(carrier_type, carrier_id) 二元组（契约 §3；CarrierRef 恰 2 字段）。 */
export interface ServiceCarrier {
  carrier_type: ServiceCarrierType
  carrier_id: number
}

/** Service 资源表示（契约 §2；所有返回单对象的端点共用该结构，恰 11 字段）。 */
export interface ServiceRead {
  /** 不可变代理主键；写操作一律使用该值（ADR-0003）。 */
  id: number
  /** 身份标识；全局活跃唯一、大小写敏感（R-SVC-008）；原样存取（契约 §8）。 */
  name: string
  /** 6 个可选字段（契约 §2）：可选、纯文本、未登记为 null。 */
  service_type: string | null
  url: string | null
  port: string | null
  protocol: string | null
  owner: string | null
  description: string | null
  /**
   * 运行载体绑定集合（R-SVC-002/005）：至少 1 项；响应恒按
   * (carrier_type rank, carrier_id) 升序稳定排列（契约 §2），前端可依赖
   * 该顺序展示，但不得据此实现业务语义。
   */
  carriers: ServiceCarrier[]
  /** 登记时间（RFC 3339 不透明字符串）。 */
  created_at: string
  /** 最近更新时间（RFC 3339 不透明字符串；不是并发控制依据）。 */
  updated_at: string
}

/** 6 个可选字段键列表（登记 / 编辑表单与详情展示共用）。 */
export const SERVICE_OPTIONAL_FIELDS = [
  'service_type',
  'url',
  'port',
  'protocol',
  'owner',
  'description',
] as const

/** 6 个可选字段键。 */
export type ServiceOptionalField = (typeof SERVICE_OPTIONAL_FIELDS)[number]

/** 登记 Service 请求体（契约 §4.1）。name + carriers（≥1 项）必填，6 字段可选。 */
export interface ServiceCreateBody {
  /** 全局活跃唯一、大小写敏感（由服务端裁决，重复 → 409）；不做任何前端校验。 */
  name: string
  /** 载体绑定集合：至少 1 项（R-SVC-005）；载体存在性 / 活跃性 / 类型一致性由服务端裁决（404）。 */
  carriers: ServiceCarrier[]
  /** 6 个可选字段：缺省 / null 均存为 null。 */
  service_type?: string | null
  url?: string | null
  port?: string | null
  protocol?: string | null
  owner?: string | null
  description?: string | null
}

/**
 * 更新 Service 请求体（契约 §4.4，部分更新）。
 * 可变字段封闭为 6 个可选字段；id / name / carriers（载体绑定）/
 * created_at 不可变（NQ-01 / NQ-02，登记后不可变），不得出现在请求体中。
 */
export interface ServiceUpdateBody {
  /** 提供 null 表示清空该字段；缺省表示不修改。 */
  service_type?: string | null
  url?: string | null
  port?: string | null
  protocol?: string | null
  owner?: string | null
  description?: string | null
}

/** 列表查询参数（契约 §4.2）。 */
export interface ServiceListParams extends PageParams {
  /**
   * 按载体限定（R-QUERY-003 的 canonical 能力，供 F010 复用、不得另写
   * 一份过滤）：carrier_type 与 carrier_id 必须成对出现（仅提供其一 → 400），
   * 故以单一对象表达，结构上不可只携带其一；未提供时返回全部活跃 Service。
   */
  carrier?: ServiceCarrier | null
}

/**
 * 列出活跃 Service（契约 §4.2）。
 *
 * - 未提供 carrier → 全部活跃 Service；无活跃 → 200 + items == []（Empty）；
 * - 提供 carrier → 绑定到该载体的活跃 Service（三种载体类型均成立）：
 *   载体不存在 / 已逻辑删除 / 类型与标识不一致 → 404 NOT_FOUND（Not Found，
 *   与 Empty 是不同状态）；载体存在但无活跃 Service 绑定 → 200 + items == []
 *   （Empty）；
 * - 已逻辑删除的 Service 不出现在 items / total（R-DELETE-002）。
 */
export function listServices(params: ServiceListParams = {}): Promise<Paginated<ServiceRead>> {
  return apiRequest<Paginated<ServiceRead>>('/api/services', {
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
 * 按 id 读取 Service（契约 §4.3，规范路径）。
 * 不存在或已被逻辑删除 → 404 NOT_FOUND（两者不区分）。
 */
export function getService(serviceId: number): Promise<ServiceRead> {
  return apiRequest<ServiceRead>(`/api/services/${serviceId}`, { method: 'GET' })
}

/**
 * 登记 Service（契约 §4.1）。成功 → 201 + ServiceRead。
 * name 全局唯一（409）、载体存在性 / 活跃性 / 类型一致性（404）、字段
 * 合法性（400，含同一请求内重复载体与请求携带未识别字段）均由服务端
 * 裁决（§21）。
 */
export function createService(body: ServiceCreateBody): Promise<ServiceRead> {
  return apiRequest<ServiceRead>('/api/services', { method: 'POST', body })
}

/**
 * 更新 6 个可选字段（契约 §4.4，部分更新）。成功 → 200 + ServiceRead；
 * id / name / carriers / created_at 保持不变。请求体至少含一个可变字段
 * （空 body → 400，服务端裁决）。
 */
export function updateService(
  serviceId: number,
  body: ServiceUpdateBody,
): Promise<ServiceRead> {
  return apiRequest<ServiceRead>(`/api/services/${serviceId}`, {
    method: 'PATCH',
    body,
  })
}

/**
 * 逻辑删除 Service（契约 §4.5）。
 *
 * - `DELETE /api/services/{service_id}`：写操作一律走 id；
 * - 成功 → 204（无响应体，apiRequest 归一为 undefined，不抛出）；
 * - 404 NOT_FOUND：不存在或已被逻辑删除（两者不区分，重复删除亦 404）；
 * - 401 UNAUTHENTICATED：由全局会话失效处理；
 * - Service 无子资源（契约 §4.5：删除不产生 409），本层不假定其他冲突
 *   形态，若出现按 error.code 兜底分支；
 * - 不发送请求体（契约 §4.5：客户端不得发送）。
 */
export function deleteService(serviceId: number): Promise<void> {
  return apiRequest<void>(`/api/services/${serviceId}`, { method: 'DELETE' })
}
