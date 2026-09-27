// 计算资源 API（Contract docs/api/F002.md：新增 / 表单加载详情 / 编辑 / 真实删除，4 端点）。
// 字段与错误语义严格按 Contract；401/403 全局处理（client 拦截），
// 400/409/422 由页面按 code/字段呈现（utils/resourceRules 的文案与卡片定位映射）。
// 409 RESOURCE_NAME_EXISTS 的扩展成员 existing_resource_id / existing_resource_type
// 经 ApiError.extensions 读取（Contract §0 problem+json 扩展成员）。
import { client } from './client'

/** 资源类型（Contract §0：bare_metal / virtual_machine；创建后只读） */
export type ResourceType = 'bare_metal' | 'virtual_machine'

/** 资源状态（Contract §0：IDLE / ALLOC / DOWN / UNKNOWN；未提供默认 ALLOC） */
export type ResourceStatus = 'IDLE' | 'ALLOC' | 'DOWN' | 'UNKNOWN'

/** 网段摘要（Contract §1 InterfaceSegmentSummary：便利字段，表单内只读带出） */
export interface InterfaceSegmentSummary {
  id: number
  name: string
  /** 规范化 IPv4 CIDR */
  cidr: string
  purpose: string
  technology: string
  /** 未填为 null */
  vlan: number | null
  /** 未设为 null */
  gateway: string | null
}

/** 响应中的网卡 IP（Contract F006 §1 IpAddressResource；按地址数值升序） */
export interface IpAddressResource {
  id: number
  /** 规范化 IPv4 */
  address: string
  /** 分配时所选网段 ID */
  segment_id: number
  /** 所属网卡 ID */
  interface_id: number
  /** 是否为所属资源的管理 IP（§4.2.9） */
  is_management: boolean
  created_at: string
}

/** 响应中的网卡（Contract §1 NetworkInterfaceResource；F006 扩展 ips） */
export interface NetworkInterfaceResource {
  id: number
  name: string
  /** 关联网段 ID；未选为 null */
  segment_id: number | null
  /** 关联网段摘要；未选为 null（便利字段） */
  segment: InterfaceSegmentSummary | null
  /** 该网卡 IP；无 IP 为 []（F006） */
  ips: IpAddressResource[]
  created_at: string
  updated_at: string
}

/** 响应中的管理 IP 摘要（Contract F006 §1 ManagementIpSummary；未指定 null） */
export interface ManagementIpSummary {
  ip_id: number
  address: string
  interface_id: number
  interface_name: string
}

/** 表单详情（Contract §1 ResourceFormDetail：GET/POST/PATCH 响应） */
export interface ResourceFormDetail {
  id: number
  cluster_id: number
  /** 所属集群展示编号（便利字段） */
  cluster_code: string
  /** 所属集群名称（便利字段） */
  cluster_name: string
  name: string
  resource_type: ResourceType
  status: ResourceStatus
  /** 状态来源操作者用户 ID；无记录为 null（BQ-AA：仅记录操作者） */
  status_updated_by: number | null
  status_updated_by_username: string | null
  status_updated_at: string
  /** 网卡列表（按 name 稳定排序；空为 []；每项含 ips） */
  interfaces: NetworkInterfaceResource[]
  /** 管理 IP 摘要；未指定 null（F006 §1） */
  management_ip: ManagementIpSummary | null
  /** 乐观锁 */
  version: number
  created_at: string
  updated_at: string
}

/** POST /resources 网卡 IP 新增项（Contract F006 §1 IpCreate；manual 必填 address，
 * auto 省略 address 由服务端选址） */
export interface IpCreateItem {
  mode: 'manual' | 'auto'
  /** manual 必填且合法；auto 省略或 null */
  address?: string | null
}

/** POST /resources 网卡项（Contract §1 NetworkInterfaceCreate；F006 扩展 ips） */
export interface NetworkInterfaceCreateItem {
  name: string
  /** 省略或 null = 不选网段 */
  segment_id: number | null
  /** 缺省 []；分配 IP 时 segment_id 必须非空 */
  ips?: IpCreateItem[]
}

/** POST /resources 请求体（Contract §2.1） */
export interface ResourceCreatePayload {
  cluster_id: number
  name: string
  resource_type: ResourceType
  /** 未提供默认 ALLOC */
  status?: ResourceStatus
  /** 缺省=空数组；同 payload 内接口名不得重复 */
  interfaces?: NetworkInterfaceCreateItem[]
  /** 缺省/null = 无管理 IP；仅可引用本请求内的 IP（{interface_index,address}） */
  management_ip?: ManagementIpRef | null
}

/** 管理 IP 引用（Contract F006 §1 ManagementIpRef）：{ip_id}=重选既有；
 * {interface_index,address}=引用同一请求 interfaces[]（0 基下标）内的 IP；
 * 创建资源时 IP 尚无 ID，仅后者可用 */
export type ManagementIpRef = { ip_id: number } | { interface_index: number; address: string }

/** PATCH 网卡 IP 显式操作项（Contract F006 §1 IpOp，判别字段 op：
 * create 新增（manual 必填 address / auto 省略）、delete 显式删除既有 id；
 * 未列入 ips[] 的既有 IP = 未修改；IP 不可改地址，改址=删除后重新分配） */
export interface IpOpItem {
  op: 'create' | 'delete'
  /** delete 必填：须属于该网卡/资源，否则 IP_NOT_FOUND */
  id?: number
  /** create：manual/auto */
  mode?: 'manual' | 'auto'
  /** create+manual 必填且合法 IPv4 */
  address?: string | null
}

/** PATCH /resources/{id} 网卡显式操作项（Contract §1 NetworkInterfaceOp，判别字段 op；
 * F006 扩展 ips：delete 网卡可同项携带其 IP 显式删除） */
export interface NetworkInterfaceOpItem {
  op: 'create' | 'update' | 'delete'
  /** update/delete 必填：须属于该资源 */
  id?: number
  /** create 必填；update 省略=不修改 */
  name?: string
  /** update 省略=不修改；null=清空（create：null=不选网段） */
  segment_id?: number | null
  /** 显式 IP 增/删；缺省=不改动该网卡 IP */
  ips?: IpOpItem[]
}

/** PATCH /resources/{id} 请求体（Contract §2.3：省略字段=不修改；version 必填；
 * resource_type/cluster_id 只读，不发送） */
export interface ResourceUpdatePayload {
  name?: string
  status?: ResourceStatus
  /** 省略或 [] = 不改动网卡；显式 op 增/改/删 */
  interfaces?: NetworkInterfaceOpItem[]
  /** 省略=不修改；null=显式清空；否则重选（F006 §2.3）；删除当前管理 IP/其网卡
   * 而未给出 → MANAGEMENT_IP_REQUIRED */
  management_ip?: ManagementIpRef | null
  version: number
}

/** DELETE /resources/{id} 查询参数（Contract §2.4：二次确认 + 乐观锁） */
export interface ResourceDeleteQuery {
  /** 二次确认：去首尾空格后须等于资源名称（区分大小写，BQ-Z） */
  confirm: string
  version: number
}

/** POST /resources：新增（201 → ResourceFormDetail；409 RESOURCE_NAME_EXISTS
 * 响应扩展成员 existing_resource_id/existing_resource_type → ApiError.extensions；
 * 404 CLUSTER_NOT_FOUND、422 字段级 errors[]（含 F006 IP 错误码）、409 IP_ALREADY_IN_USE
 * （附 conflicts）/ NO_AVAILABLE_ADDRESS 由页面呈现） */
export function createResource(payload: ResourceCreatePayload): Promise<ResourceFormDetail> {
  return client.post<ResourceFormDetail>('/resources', payload).then((res) => res.data)
}

/** GET /resources/{resource_id}：表单加载详情（含网卡与 version；任意已登录） */
export function getResource(resourceId: number): Promise<ResourceFormDetail> {
  return client.get<ResourceFormDetail>(`/resources/${resourceId}`).then((res) => res.data)
}

/** PATCH /resources/{resource_id}：编辑公共信息 + 网卡/IP 显式增/删 + 管理 IP 清空/重选
 * （乐观锁、整单原子；F006 扩展） */
export function updateResource(
  resourceId: number,
  payload: ResourceUpdatePayload,
): Promise<ResourceFormDetail> {
  return client.patch<ResourceFormDetail>(`/resources/${resourceId}`, payload).then((res) => res.data)
}

/** DELETE /resources/{resource_id}?confirm=&version=：真实删除（二次确认 + 乐观锁 +
 * 删除前置：仍有网卡 → 409 RESOURCE_HAS_INTERFACES） */
export function deleteResource(resourceId: number, query: ResourceDeleteQuery): Promise<void> {
  return client
    .delete<void>(`/resources/${resourceId}`, { params: { confirm: query.confirm, version: query.version } })
    .then(() => undefined)
}
