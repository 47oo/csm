/**
 * Dashboard API（F013，Contract：docs/api/F013.md v1 §3，READY）。
 *
 * 端点（Contract §3）：
 * - GET /dashboard  资源汇总（READ；VIEWER / EDITOR / ADMIN 全角色）
 *
 * 注意：
 * - 无 `deleted` 参数：计数与容量恒为未删口径（I-1/DR-180，含 INACTIVE
 *   Cluster/Network，状态不改变计数，I-8）；无 cluster_id 过滤（I-8 未确认，
 *   不默认新增，DR-188）。
 * - `counts` 恒为全局未删口径，不受 page/page_size 影响；`networks.items`
 *   受分页影响（行序固定 created_at DESC, id ASC，无 sort/order，§3.1）。
 * - 容量只消费 F010 §6.9 口径（DR-182，数值逐项一致 A20）：allocatable_total
 *   = 基础可用 − gateway − RESERVED 池范围 − 禁用地址（去重）；occupied =
 *   未删 IP 数（含未绑定、含池外手动）；remaining = 差值，可为负、原样返回
 *   不截断（DR-130）；AUTO 池按 池范围 ∩ 可分配集合 口径。
 * - 容量与 status / auto_allocate 分别展示（A19）：INACTIVE 网络仍出现且
 *   容量不清零；前端不得以状态掩盖或重算容量。
 * - 不提供跨 Network 全局合计（I-16/DR-183 定稿）：前端不自行相加。
 * - 不是监控面板（§3/§20）：无实时 CPU/内存/流量/可达性数据，前端不伪造。
 * - 只读：无写入口、无 Audit、幂等（§5/A21）；任何失败不自动重试。
 * - 401 / 403 / 422 / 500 / 网络层错误的页面呈现语义见 describeDashboardError。
 * - 本文件 import 显式带 .ts 扩展名：scripts/smoke-client.mjs 以 Node
 *   type stripping 直接加载本模块做机制级冒烟（同 src/api/*.ts）。
 */
import { displayError, isApiError, request } from "./client.ts";
import type { NetworkClusterRef, NetworkStatus } from "./networks.ts";
import type { NetworkCapacityPoolRef } from "./ipAddresses.ts";

/** GET /dashboard 查询参数（Contract §3.1；仅作用于 networks.items）。 */
export interface DashboardQuery {
  page?: number;
  page_size?: number;
}

/** 全局计数（Contract §3.2：均为未删口径；clusters/networks 含 INACTIVE）。 */
export interface DashboardCounts {
  clusters: number;
  /** 未删 Resource 总数（bare_metal + virtual_machines）。 */
  resources: number;
  bare_metal: number;
  virtual_machines: number;
  networks: number;
}

/** Dashboard 行内嵌的 Network（Contract §3.2：附 cluster 上下文，A20）。 */
export interface DashboardNetworkRef {
  id: string;
  name: string;
  /** CIDR 字符串（归一化后的网络地址，如 10.10.0.0/16）。 */
  cidr: string;
  status: NetworkStatus;
  auto_allocate: boolean;
  cluster: NetworkClusterRef;
}

/** 容量三元组（Contract §3.2/§3.3：remaining 可为负，原样展示不截断）。 */
export interface DashboardCapacity {
  allocatable_total: number;
  occupied: number;
  remaining: number;
}

/** 每行 AUTO 池容量（Contract §3.2：池范围 ∩ 可分配集合口径，DR-182）。 */
export interface DashboardAutoPoolCapacity {
  ip_pool: NetworkCapacityPoolRef;
  allocatable_total: number;
  occupied: number;
  remaining: number;
}

/** Dashboard per-Network 行（Contract §3.2：network + capacity + auto_pools）。 */
export interface DashboardNetworkRow {
  network: DashboardNetworkRef;
  capacity: DashboardCapacity;
  /** 0..N（无 AUTO 池为空数组，非 null）。 */
  auto_pools: DashboardAutoPoolCapacity[];
}

/** networks 分页信封（Contract §3.2）。 */
export interface DashboardNetworksPage {
  items: DashboardNetworkRow[];
  page: number;
  page_size: number;
  total: number;
}

/** GET /dashboard 响应（Contract §3.2）。 */
export interface DashboardResponse {
  counts: DashboardCounts;
  networks: DashboardNetworksPage;
}

/**
 * Dashboard 汇总：GET /api/v1/dashboard（READ）。
 * page/page_size 仅作用于 networks.items（1–100）；counts 不受分页影响。
 */
export function getDashboard(query: DashboardQuery = {}): Promise<DashboardResponse> {
  const search = new URLSearchParams();
  if (query.page !== undefined) {
    search.set("page", String(query.page));
  }
  if (query.page_size !== undefined) {
    search.set("page_size", String(query.page_size));
  }
  const queryString = search.toString();
  return request<DashboardResponse>(`/dashboard${queryString ? `?${queryString}` : ""}`);
}

/** 面向页面的 Dashboard 加载错误（Contract §1.2/§3.5）。 */
export interface DashboardLoadError {
  message: string;
  code: string | null;
}

/**
 * 把 Dashboard 加载错误归类为页面可直接呈现的结构（不抛出、不重试）：
 * - 网络层错误（fetch reject）：固定文案，不伪装成业务结果；
 * - 401：会话缺失（client 全局处理器已同时清登录态回登录页）；
 * - 403：明确文案（本端点 READ 全角色，出现即为异常，不伪装成空数据）；
 * - 422：参数校验失败（page/page_size，Contract §3.1）；
 * - 其余（含 500 / 非 JSON 信封）：回退信封 message + code，不伪造内容。
 * 错误不得伪装成空列表 / 计数为 0（实现规则「查询与界面」）。
 */
export function describeDashboardError(error: unknown): DashboardLoadError {
  if (!isApiError(error)) {
    return { message: "无法连接服务器，请稍后重试", code: null };
  }

  const result: DashboardLoadError = {
    message: displayError(error),
    code: error.code,
  };
  if (error.status === 401) {
    result.message = "尚未登录或会话已过期（AUTH_REQUIRED），请重新登录。";
  } else if (error.status === 403) {
    result.message = "没有权限查看 Dashboard（服务端已拒绝，FORBIDDEN）。";
  } else if (error.status === 422) {
    result.message = "查询参数校验失败（page / page_size，VALIDATION_ERROR）。";
  }
  return result;
}
