/**
 * IPAddressRange（IP 地址范围段 / 地址池）产品 API 客户端。
 *
 * 契约依据：docs/api/f020-ip-address-range.md（READY，唯一权威；含 F022
 * 纯增量修订：新增 3 个可选元数据字段 name / subnet_mask / vlan）。
 *
 * - 字段集合封闭（契约 §2）：恰为 9 字段 {id, cluster_id, start_ip, end_ip,
 *   name, subnet_mask, vlan, created_at, updated_at}；不存在 deleted_at（不
 *   对外暴露）、状态字段（Q-002=B，范围段无状态）、description / 用途字段
 *   （契约 §2 / §10）、CIDR / 前缀长度 / 网络地址 / 广播地址 / 网关 / DHCP /
 *   DNS 字段、使用率 / 剩余地址 / 容量字段、分配对象 / 分配时间 / 回收状态
 *   字段（F021 范围）；
 * - cluster_id 是范围段的登记事实，直接在响应中返回（与 F005 的 IPAddress
 *   不同——后者的 Cluster 归属是推导值、不对外暴露）；登记后不可变（契约
 *   §3.4：PATCH 可变字段封闭为 {start_ip, end_ip, name, subnet_mask, vlan}，
 *   cluster_id 不在其中）；
 * - start_ip / end_ip 为服务端规范化后的 dotted-quad IPv4 字面值，前端
 *   **原样存取与提交**：不做任何 IPv4 解析 / 格式校验 / 归一化 / 去除空白，
 *   不做 start<=end 预判，也不做同 Cluster 重叠预检 —— 字段合法性 / 归属
 *   活跃性 / 重叠唯一性全部由服务端裁决（契约 §7 / §21），前端不得重复实现
 *   业务守卫；
 * - name / subnet_mask / vlan 为 3 个可选元数据字段（契约 §1.12 / §2 /
 *   §7.3，F022）：未登记为 null，原样存取（不做 trim / 归一化 / 大小写
 *   折叠）；name 同 Cluster 活跃唯一（区分大小写）、subnet_mask 合法性与
 *   vlan 1–4094 取值范围均由服务端裁决（400），name 唯一冲突由服务端裁决
 *   （409 CONFLICT + details[].code === 'DUPLICATE'）—— 前端不做 name 唯一 /
 *   掩码格式 / VLAN 范围的客户端业务校验（§21），不预判、不拦截、不禁用
 *   提交；三者均不参与重叠判定，也不是查询 / 筛选 / 排序参数（契约 §10：
 *   本模块不构造按 name / subnet_mask / vlan 的过滤参数）；
 * - 时间字段为 RFC 3339 不透明字符串，不解析、不假设时区（契约 §2）；
 * - 写操作一律走 id（ADR-0003）；错误语义由 api/http.ts 统一解析为 ApiError，
 *   消费方按 error.code（必要时结合 details[].code）分支，不解析 message。
 */
import type { PageParams, Paginated } from '../types/api'
import { apiRequest } from './http'

/** IPAddressRange 资源表示（契约 §2；所有返回单对象的端点共用该结构）。 */
export interface IpAddressRangeRead {
  /** 不可变代理主键；写操作一律使用该值（ADR-0003）。 */
  id: number
  /** 归属 Cluster 的 id（N:1 Mandatory，恰好一个；登记后不可变）。 */
  cluster_id: number
  /** 范围下界（服务端规范化的 dotted-quad IPv4，如 10.0.0.1）；原样展示。 */
  start_ip: string
  /** 范围上界（服务端规范化的 dotted-quad IPv4，如 10.0.0.255）；原样展示。 */
  end_ip: string
  /** 可选网段自定义名称（F022，R-IP-004）；未登记为 null；原样存取，不做
   * trim / 归一化；同 Cluster 活跃唯一（区分大小写）、跨 Cluster 可重复，
   * 唯一性由服务端裁决（409 CONFLICT + details[].code === 'DUPLICATE'）。 */
  name: string | null
  /** 可选 dotted-quad IPv4 掩码（F022，如 255.255.255.0）；未登记为 null；
   * 原样存取（不归一化）；合法性（连续 1 后连续 0，非 CIDR）由服务端
   * 裁决（400），不校验与 start_ip–end_ip 自洽。 */
  subnet_mask: string | null
  /** 可选 VLAN 标注（F022）；未登记为 null；取值 1–4094、不唯一，均由
   * 服务端裁决（越界 / 非整数 → 400）。 */
  vlan: number | null
  /** 登记时间（RFC 3339 不透明字符串）。 */
  created_at: string
  /** 最近更新时间（RFC 3339 不透明字符串；不是并发控制依据）。 */
  updated_at: string
}

/**
 * 登记范围段请求体（契约 §3.1，含 F022 修订）。恰为 6 字段：前 3 个必填，
 * 后 3 个可选（不提供 / 提供 null 均视为未登记）；请求 schema 封闭（不接受
 * 任何未识别字段 → 400）。
 */
export interface IpAddressRangeCreateBody {
  /** 归属 Cluster 的 id；必须存在且活跃（由服务端裁决，不存在 / 已删 →
   * 404 NOT_FOUND）。 */
  cluster_id: number
  /** 范围下界；合法性 / 规范化由服务端裁决（非法 IPv4 → 400）。 */
  start_ip: string
  /** 范围上界；合法性 / 规范化 / start<=end 由服务端裁决。 */
  end_ip: string
  /** 可选网段名称（F022）；缺省 / null 均视为未登记；同 Cluster 活跃唯一
   * 由服务端裁决（409 CONFLICT + details[].code === 'DUPLICATE'）；长度 /
   * 空串 / 字符集未定义约束，原样提交（契约 §7.3）。 */
  name?: string | null
  /** 可选 dotted-quad IPv4 掩码（F022）；缺省 / null 均视为未登记；合法性
   * 由服务端裁决（非法掩码 → 400 + details[].field === 'subnet_mask'）。 */
  subnet_mask?: string | null
  /** 可选 VLAN（F022）；缺省 / null 均视为未登记；取值 1–4094 由服务端
   * 裁决（越界 / 非整数 → 400 + details[].field === 'vlan'）。 */
  vlan?: number | null
}

/**
 * 修正范围段请求体（契约 §3.4，部分更新，含 F022 修订）。
 * 可变字段封闭为 {start_ip, end_ip, name, subnet_mask, vlan}；id /
 * cluster_id / created_at 不可变，不得出现在请求体中。至少需包含一个可变
 * 字段（空 body → 400）；start_ip / end_ip 提供时不得为 null（null → 400）；
 * name / subnet_mask / vlan 可为 null（null → 清空为未登记）。
 */
export interface IpAddressRangeUpdateBody {
  /** 新范围下界；原样提交，不做任何变换；修正后由服务端重新裁决。 */
  start_ip?: string
  /** 新范围上界；原样提交，不做任何变换；修正后由服务端重新裁决。 */
  end_ip?: string
  /** 新网段名称（F022）；提供 null → 清空为未登记；缺省 → 不修改；提供
   * 非空值时由服务端重新执行同 Cluster 活跃唯一校验（排除自身，409
   * CONFLICT + details[].code === 'DUPLICATE'）。 */
  name?: string | null
  /** 新掩码（F022）；提供 null → 清空；缺省 → 不修改；提供时由服务端
   * 重新执行合法性校验（非法 → 400）。 */
  subnet_mask?: string | null
  /** 新 VLAN（F022）；提供 null → 清空；缺省 → 不修改；提供时由服务端
   * 重新执行范围校验（越界 / 非整数 → 400）。 */
  vlan?: number | null
}

/** 列表查询参数（契约 §3.2）。 */
export interface IpAddressRangeListParams extends PageParams {
  /**
   * 按 Cluster 限定：未提供时返回全部活跃范围段；提供时父 Cluster 不存在
   * 或已逻辑删除 → 404 NOT_FOUND（Not Found，与 Empty 是不同状态）。
   */
  cluster_id?: number
}

/**
 * 列出活跃范围段（契约 §3.2）。
 *
 * - 未提供 cluster_id → 全部活跃范围段；无活跃 → 200 + items == []
 *   （Empty，不得 404）；
 * - 提供 cluster_id → 该 Cluster 的活跃范围段：父 Cluster 不存在或已逻辑
 *   删除 → 404 NOT_FOUND；父 Cluster 存在但无活跃范围段 → 200 + items == []
 *   （Empty）；
 * - 已逻辑删除的范围段不出现在 items / total；items 按 id 升序；total 为
 *   活跃数（受过滤时为该过滤域内活跃数）；
 * - 不存在 status / 关键字 / 排序等第二维度查询参数，name / subnet_mask /
 *   vlan 也不是查询 / 筛选 / 排序参数（契约 §3.2 / §10），本模块不构造
 *   任何此类参数。
 */
export function listIpAddressRanges(
  params: IpAddressRangeListParams = {},
): Promise<Paginated<IpAddressRangeRead>> {
  return apiRequest<Paginated<IpAddressRangeRead>>('/api/ip-address-ranges', {
    method: 'GET',
    query: {
      page: params.page,
      page_size: params.page_size,
      cluster_id: params.cluster_id,
    },
  })
}

/**
 * 按 id 读取范围段（契约 §3.3）。
 * 不存在或已被逻辑删除 → 404 NOT_FOUND（两者不区分，契约 §9）。
 */
export function getIpAddressRange(ipAddressRangeId: number): Promise<IpAddressRangeRead> {
  return apiRequest<IpAddressRangeRead>(`/api/ip-address-ranges/${ipAddressRangeId}`, {
    method: 'GET',
  })
}

/**
 * 登记范围段（契约 §3.1，含 F022 修订）。成功 → 201 + IpAddressRangeRead。
 * 父 Cluster 存在性 / 活跃性（404）、字段合法性（400，含请求携带未识别
 * 字段、非法 subnet_mask / 越界 vlan）、同 Cluster 重叠（409 CONFLICT +
 * details[].code === 'OVERLAP'）、同 Cluster 活跃同名 name（409 CONFLICT +
 * details[].code === 'DUPLICATE'）均由服务端裁决（§21）；前端不做 IPv4 /
 * 掩码 / VLAN 校验、不预判重叠 / 重名、不预判父 Cluster 状态、不禁用入口。
 */
export function createIpAddressRange(
  body: IpAddressRangeCreateBody,
): Promise<IpAddressRangeRead> {
  return apiRequest<IpAddressRangeRead>('/api/ip-address-ranges', { method: 'POST', body })
}

/**
 * 修正 start_ip / end_ip / name / subnet_mask / vlan（契约 §3.4，部分更新，
 * 含 F022 修订）。成功 → 200 + IpAddressRangeRead；id / cluster_id /
 * created_at 保持不变。修正后由服务端重新执行 IPv4 解析 / start<=end /
 * 重叠校验（与同 Cluster 其它活跃范围段重叠 → 409 OVERLAP，无部分写入）、
 * name 同 Cluster 活跃唯一校验（409 + details[].code === 'DUPLICATE'）与
 * 掩码 / VLAN 校验（400）；name / subnet_mask / vlan 提供 null → 清空；
 * 无并发控制（最后提交生效，updated_at 不是并发控制依据）。
 */
export function updateIpAddressRange(
  ipAddressRangeId: number,
  body: IpAddressRangeUpdateBody,
): Promise<IpAddressRangeRead> {
  return apiRequest<IpAddressRangeRead>(`/api/ip-address-ranges/${ipAddressRangeId}`, {
    method: 'PATCH',
    body,
  })
}

/**
 * 逻辑删除范围段（契约 §3.5）。
 *
 * - `DELETE /api/ip-address-ranges/{ip_address_range_id}`：写操作一律走 id；
 * - 成功 → 204（无响应体，apiRequest 归一为 undefined，不抛出）；
 * - 404 NOT_FOUND：不存在或已被逻辑删除（两者不区分，重复删除亦 404）；
 * - 409 CONFLICT + details[].code === 'ACTIVE_CHILDREN_EXIST'：范围内仍有
 *   活跃 IP，禁止删除（须先软删这些 IP；删除守卫由后端裁决，§21）；
 * - 401 UNAUTHENTICATED：由全局会话失效处理；
 * - 不发送请求体（契约 §3.5：客户端不得发送）。
 */
export function deleteIpAddressRange(ipAddressRangeId: number): Promise<void> {
  return apiRequest<void>(`/api/ip-address-ranges/${ipAddressRangeId}`, { method: 'DELETE' })
}
