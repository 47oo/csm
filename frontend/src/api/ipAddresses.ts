/**
 * IP Address API（F010，Contract：docs/api/F010.md v1，READY）。
 *
 * 端点（Contract §6，共 9 个）：
 * - GET    /ip-addresses                          列表（分页/排序/过滤/软删可见性，§4/§5）
 * - POST   /ip-addresses                          手动分配=创建（201 {"ip_address":IPAddress}）
 * - POST   /ip-addresses/auto-allocate            自动分配=创建（201；指定 AUTO 池内升序选址）
 * - GET    /ip-addresses/{id}                     详情（?deleted=true 需 VIEW_DELETED）
 * - PATCH  /ip-addresses/{id}                     绑定/解绑/转移/描述（body 必带 version）
 * - DELETE /ip-addresses/{id}?version=N           释放（RELEASE_IP；204 软删，不级联）
 * - POST   /ip-addresses/{id}/restore?version=N   恢复（RESTORE；200，重检唯一/CIDR/依赖）
 * - GET    /ip-addresses/{id}/activity            对象 Activity（VIEW_ACTIVITY，全角色）
 * - GET    /networks/{id}/capacity                Network 容量数据（READ；显示归 F013，§6.9）
 *
 * 注意：
 * - IPAddress 为独立可寻址对象（自身 UUID/version/软删/恢复/Activity，DR-129）；
 *   归属 Network 经 network 关联；cluster 为唯一作用域展开（冗余 cluster_id 不暴露）。
 * - address 为单个裸 IPv4 主机地址（点分四段，非 CIDR/掩码；含前缀/掩码/IPv6 →
 *   422 field="address"，不静默归一化）；同 Cluster 未删唯一（跨 Network/Pool），
 *   软删释放后可复用；创建必填、创建后不可改（DR-120）。
 * - network 创建必填、创建后不可改（PATCH 含 network/network_id → 422，本 client
 *   的 PATCH 载荷恒不含该键）；仅新建分配要求 Network ACTIVE（409
 *   allocation_not_allowed{network_inactive}）；绑定/解绑/转移为关系编辑不受
 *   INACTIVE 限制（DR-136）。
 * - interface 可选 nullable（未绑定 null）；POST 创建不接受 interface（分配与
 *   绑定分离，DR-137）；PATCH 显式 null = 解绑（IP 继续占用），非空 = 绑定/转移
 *   （须同 Cluster，422 field="interface"）。
 * - ip_pool 只读（服务端推导：自动=指定 AUTO 池、手动=地址所属未删池或 null）；
 *   请求体出现 → 422（DR-122）；创建后不可改；Pool 删除/缩小不回收。
 * - IPAddress 无 metadata（请求含 metadata → 422，I-3/DR-123）。
 * - PATCH 仅携带变化字段（省略 = 保持原值不重置，exclude_unset，§2.4）。
 * - 409 CONFLICT（unique_conflict{field:"address"} / allocation_not_allowed
 *   {condition} / no_available_address / reference_exists / dependency_deleted /
 *   not_deleted）/ VERSION_CONFLICT 的页面呈现语义见 describeIpAddressActionError；
 *   任何写失败都不自动重试（Contract §7）。
 * - 容量：allocatable_total/occupied/remaining 按 §20 口径；remaining 直接相减
 *   不截断，可为负值原样呈现（DR-130 定稿裁定）；显示归 F013，本 client 仅提供数据。
 * - 本文件 import 显式带 .ts 扩展名：scripts/smoke-client.mjs 以 Node
 *   type stripping 直接加载本模块做机制级冒烟（同 src/api/*.ts）。
 */
import { displayError, envelopeFieldErrors, isApiError, request } from "./client.ts";
import type { DeletedMode, SortOrder } from "./clusters.ts";
import type { NetworkStatus } from "./networks.ts";

/** 软删可见性 / 排序方向与 F003 同一语义，复用同一类型定义（Contract §4/§5）。 */
export type { DeletedMode, SortOrder } from "./clusters.ts";

/** 列表排序字段白名单（Contract §4；sort=address 按数值地址升序）。 */
export type IpAddressSortField = "address" | "created_at" | "updated_at";

/** IPAddress 响应内嵌的所属 Network 引用（Contract §3：{id,name,cidr}，只读）。 */
export interface IpAddressNetworkRef {
  id: string;
  name: string;
  cidr: string;
}

/** IPAddress 响应内嵌的 Cluster 引用（Contract §3：{id,code,name}，唯一作用域）。 */
export interface IpAddressClusterRef {
  id: string;
  code: string;
  name: string;
}

/** 绑定 Interface 展开引用（Contract §3：{id,name,resource{id,hostname}}；未绑定 null）。 */
export interface IpAddressInterfaceRef {
  id: string;
  name: string;
  resource: { id: string; hostname: string };
}

/** 分配来源 IPPool 展开引用（Contract §3：{id,name}；池外手动分配 null）。 */
export interface IpAddressPoolRef {
  id: string;
  name: string;
}

/**
 * IPAddress 响应对象（Contract §3）。
 * interface/ip_pool/description 未设置为 null，绝不以空串代替；
 * 响应不含 metadata / 原始 network_id/cluster_id（I-3/DR-123）。
 */
export interface IpAddress {
  id: string;
  network: IpAddressNetworkRef;
  cluster: IpAddressClusterRef;
  /** 点分十进制 IPv4 主机地址（无 /32 后缀，Contract §2.1）。 */
  address: string;
  interface: IpAddressInterfaceRef | null;
  ip_pool: IpAddressPoolRef | null;
  description: string | null;
  version: number;
  created_at: string;
  updated_at: string;
  deleted_at: string | null;
}

/** 列表响应（Contract §4：{items, page, page_size, total}）。 */
export interface IpAddressListResponse {
  items: IpAddress[];
  page: number;
  page_size: number;
  total: number;
}

/** 单对象响应信封（Contract §6.2/§6.3/§6.4/§6.7：{"ip_address":IPAddress}）。 */
export interface IpAddressEnvelope {
  ip_address: IpAddress;
}

/** Activity 条目（Contract §6.8；只读，无修改/删除入口）。 */
export interface IpAddressActivityItem {
  id: string;
  action: "CREATE" | "UPDATE" | "DELETE" | "RESTORE";
  operator_user_id: string | null;
  operator_username: string;
  before_data: Record<string, unknown> | null;
  after_data: Record<string, unknown> | null;
  created_at: string;
}

/** Activity 响应（Contract §6.8：created_at 升序、同刻 id 升序）。 */
export interface IpAddressActivityResponse {
  items: IpAddressActivityItem[];
  page: number;
  page_size: number;
  total: number;
}

/** GET /ip-addresses 查询参数（省略项不发，由服务端默认值生效，Contract §4）。 */
export interface ListIpAddressesQuery {
  /** 所属 Network UUID 精确过滤（非 UUID → 422；不存在 → 空结果非 404）。 */
  network_id?: string;
  /** Cluster UUID 精确过滤（唯一作用域；非 UUID → 422）。 */
  cluster_id?: string;
  /** 绑定 Interface UUID 精确过滤（非 UUID → 422；不存在 → 空结果）。 */
  interface_id?: string;
  /** 分配来源 IPPool UUID 精确过滤（非 UUID → 422；不存在 → 空结果）。 */
  ip_pool_id?: string;
  /** IPv4 主机地址精确匹配（非法 → 422）。 */
  address?: string;
  /** true=已绑定（interface 非空）；false=未绑定。 */
  bound?: boolean;
  /** 对 address 的大小写不敏感子串（空/纯空白视为未提供；不用 pg_trgm）。 */
  q?: string;
  deleted?: DeletedMode;
  page?: number;
  page_size?: number;
  sort?: IpAddressSortField;
  order?: SortOrder;
}

/** 列表查询：GET /api/v1/ip-addresses（READ；deleted=include|only 另需 VIEW_DELETED）。 */
export function listIpAddresses(query: ListIpAddressesQuery = {}): Promise<IpAddressListResponse> {
  const search = new URLSearchParams();
  if (query.network_id !== undefined && query.network_id !== "") {
    search.set("network_id", query.network_id);
  }
  if (query.cluster_id !== undefined && query.cluster_id !== "") {
    search.set("cluster_id", query.cluster_id);
  }
  if (query.interface_id !== undefined && query.interface_id !== "") {
    search.set("interface_id", query.interface_id);
  }
  if (query.ip_pool_id !== undefined && query.ip_pool_id !== "") {
    search.set("ip_pool_id", query.ip_pool_id);
  }
  if (query.address !== undefined && query.address !== "") {
    search.set("address", query.address);
  }
  if (query.bound !== undefined) {
    search.set("bound", String(query.bound));
  }
  if (query.q !== undefined && query.q !== "") {
    search.set("q", query.q);
  }
  if (query.deleted !== undefined) {
    search.set("deleted", query.deleted);
  }
  if (query.page !== undefined) {
    search.set("page", String(query.page));
  }
  if (query.page_size !== undefined) {
    search.set("page_size", String(query.page_size));
  }
  if (query.sort !== undefined) {
    search.set("sort", query.sort);
  }
  if (query.order !== undefined) {
    search.set("order", query.order);
  }
  const queryString = search.toString();
  return request<IpAddressListResponse>(`/ip-addresses${queryString ? `?${queryString}` : ""}`);
}

/**
 * POST /ip-addresses 请求体（手动分配=创建，Contract §6.2）。
 * network/address 必填；description 省略 → null；
 * interface/ip_pool/cluster_id/metadata 等未列 / 只读字段不可出现（→ 422，
 * 分配与绑定分离 DR-137、ip_pool 服务端推导 DR-122，表单不提供该输入）。
 */
export interface CreateIpAddressPayload {
  /** 所属 Network UUID（创建必填、须存在未软删，§2.2；创建后不可改，DR-120）。 */
  network: string;
  /** 裸 IPv4 主机地址（属 Network CIDR、非网络/广播/禁用/gateway/RESERVED，§2.1）。 */
  address: string;
  description?: string;
}

/** 手动分配：POST /api/v1/ip-addresses（WRITE）；201；同 Cluster 未删地址冲突 409 CONFLICT{unique_conflict,field:"address"}。 */
export function createIpAddress(payload: CreateIpAddressPayload): Promise<IpAddressEnvelope> {
  return request<IpAddressEnvelope>("/ip-addresses", { method: "POST", body: payload });
}

/**
 * POST /ip-addresses/auto-allocate 请求体（自动分配=创建，Contract §6.3）。
 * network/ip_pool 必填；条件不满足（Network 非 ACTIVE / auto_allocate 关闭 /
 * 池非 AUTO）→ 409 allocation_not_allowed，不降级为手动；池耗尽 → 409
 * no_available_address，不切换其它池（DR-125）。
 */
export interface AutoAllocateIpAddressPayload {
  network: string;
  /** 指定 AUTO 池 UUID（须存在、未软删、属该 Network、allocation_mode=AUTO）。 */
  ip_pool: string;
  description?: string;
}

/** 自动分配：POST /api/v1/ip-addresses/auto-allocate（WRITE）；201（interface=null；ip_pool=指定池）。 */
export function autoAllocateIpAddress(
  payload: AutoAllocateIpAddressPayload,
): Promise<IpAddressEnvelope> {
  return request<IpAddressEnvelope>("/ip-addresses/auto-allocate", {
    method: "POST",
    body: payload,
  });
}

/** 详情：GET /api/v1/ip-addresses/{id}（READ）。已删对象需显式 deleted=true 且具 VIEW_DELETED，否则 404（§5）。 */
export function getIpAddress(
  id: string,
  options: { deleted?: boolean } = {},
): Promise<IpAddressEnvelope> {
  const search = new URLSearchParams();
  if (options.deleted) {
    search.set("deleted", "true");
  }
  const queryString = search.toString();
  return request<IpAddressEnvelope>(
    `/ip-addresses/${encodeURIComponent(id)}${queryString ? `?${queryString}` : ""}`,
  );
}

/**
 * PATCH /ip-addresses/{id} 请求体（绑定/解绑/转移/描述，Contract §6.5，exclude_unset）。
 * version 必填；interface 省略 = 保持绑定；显式 null = 解绑（IP 继续占用）；
 * 非空 UUID = 绑定/转移（服务端重检存在/未软删/同 Cluster，422 field="interface"）；
 * description 显式 null = 清空；
 * network/address/cluster_id/ip_pool/id 等不可变 / 只读字段不可出现在请求体
 * （→ 422，DR-120/DR-122，本 client 的载荷恒不含这些键）。
 */
export interface UpdateIpAddressPayload {
  version: number;
  interface?: string | null;
  description?: string | null;
}

/** 绑定/解绑/转移/描述：PATCH /api/v1/ip-addresses/{id}（WRITE）；成功 200，version+1。 */
export function updateIpAddress(
  id: string,
  payload: UpdateIpAddressPayload,
): Promise<IpAddressEnvelope> {
  return request<IpAddressEnvelope>(`/ip-addresses/${encodeURIComponent(id)}`, {
    method: "PATCH",
    body: payload,
  });
}

/**
 * 释放：DELETE /api/v1/ip-addresses/{id}?version=N（RELEASE_IP；204 软删）。
 * 不级联；被未删 Endpoint 引用 → 409 reference_exists；不自动解绑其它对象（§6.6）。
 */
export function releaseIpAddress(id: string, version: number): Promise<void> {
  const search = new URLSearchParams({ version: String(version) });
  return request<void>(`/ip-addresses/${encodeURIComponent(id)}?${search.toString()}`, {
    method: "DELETE",
  });
}

/**
 * 恢复：POST /api/v1/ip-addresses/{id}/restore?version=N（RESTORE；200，仅恢复自身）。
 * 重检同 Cluster 地址唯一、所属 Network 未软删、地址仍属 CIDR、绑定 Interface
 * 有效性；失败不覆盖新对象（§6.7/DR-128）；恢复不要求 Network ACTIVE（DR-136）。
 */
export function restoreIpAddress(id: string, version: number): Promise<IpAddressEnvelope> {
  const search = new URLSearchParams({ version: String(version) });
  return request<IpAddressEnvelope>(
    `/ip-addresses/${encodeURIComponent(id)}/restore?${search.toString()}`,
    { method: "POST" },
  );
}

/** 对象 Activity：GET /api/v1/ip-addresses/{id}/activity（VIEW_ACTIVITY，全角色）。 */
export function getIpAddressActivity(
  id: string,
  query: { deleted?: boolean; page?: number; page_size?: number } = {},
): Promise<IpAddressActivityResponse> {
  const search = new URLSearchParams();
  if (query.deleted) {
    search.set("deleted", "true");
  }
  if (query.page !== undefined) {
    search.set("page", String(query.page));
  }
  if (query.page_size !== undefined) {
    search.set("page_size", String(query.page_size));
  }
  const queryString = search.toString();
  return request<IpAddressActivityResponse>(
    `/ip-addresses/${encodeURIComponent(id)}/activity${queryString ? `?${queryString}` : ""}`,
  );
}

// ---------- 容量数据端点（Contract §6.9；显示归 F013，此处仅数据 client） ----------

/** 容量响应内的 Network 引用（Contract §6.9：{id,name,cidr,status,auto_allocate}）。 */
export interface NetworkCapacityNetworkRef {
  id: string;
  name: string;
  cidr: string;
  status: NetworkStatus;
  auto_allocate: boolean;
}

/** 容量响应内的 AUTO 池引用（Contract §6.9：{id,name,start_address,end_address}）。 */
export interface NetworkCapacityPoolRef {
  id: string;
  name: string;
  start_address: string;
  end_address: string;
}

/** Network 级容量（Contract §6.9/§20：口径见 DR-130；停用不清零）。 */
export interface NetworkCapacitySummary {
  network: NetworkCapacityNetworkRef;
  /** 基础可用地址 − gateway − RESERVED 池范围 − 禁用地址（去重）。 */
  allocatable_total: number;
  /** 该 Network 下未删 IP 数（含未绑定、含池外手动）。 */
  occupied: number;
  /** allocatable_total − occupied；直接相减不截断，可为负值原样返回（DR-130）。 */
  remaining: number;
}

/** AUTO 池容量（Contract §6.9：池范围 ∩ Network 可分配集合口径，按当前地址不按来源）。 */
export interface AutoPoolCapacitySummary {
  ip_pool: NetworkCapacityPoolRef;
  allocatable_total: number;
  occupied: number;
  remaining: number;
}

/** GET /networks/{id}/capacity 响应（Contract §6.9；未删 Network 才返回，软删 → 404）。 */
export interface NetworkCapacityResponse {
  network_capacity: NetworkCapacitySummary;
  auto_pools: AutoPoolCapacitySummary[];
}

/** Network 容量数据：GET /api/v1/networks/{id}/capacity（READ；§20 口径，显示归 F013）。 */
export function getNetworkCapacity(networkId: string): Promise<NetworkCapacityResponse> {
  return request<NetworkCapacityResponse>(`/networks/${encodeURIComponent(networkId)}/capacity`);
}

// ---------- 写操作错误描述（Contract §1.2/§7） ----------

/** reference_exists 冲突明细：解绑/转移/释放被未删 Endpoint 引用（label 可能缺失）。 */
export interface IpAddressReferenceItem {
  object_type: string;
  object_id: string;
  label: string | null;
}

/** dependency_deleted 冲突明细：恢复时所属 Network / 绑定 Interface 仍软删或缺失。 */
export interface IpAddressDependencyConflictItem {
  object_type: string;
  object_id: string;
}

/** allocation_not_allowed 的条件枚举（Contract §1.2/DR-125/DR-136）。 */
export type AllocationCondition = "network_inactive" | "auto_allocate_disabled" | "pool_not_auto";

/** no_available_address 的附加字段（Contract §1.2：指定池内无可用地址，不切换）。 */
export interface NoAvailableAddressInfo {
  network_id: string | null;
  ip_pool_id: string | null;
}

/**
 * 面向页面的写操作错误描述（Contract §1.2/§7）：
 * - 409 VERSION_CONFLICT：versionConflict=true 并携带 current_version；
 *   页面提示刷新后重新操作，绝不静默重试 / 覆盖。
 * - 409 CONFLICT：按 details.reason 映射；
 *   unique_conflict 落为 address 字段级错误（field 恒为 "address"，§1.2）；
 *   allocation_not_allowed 携带 condition（network_inactive / auto_allocate_disabled /
 *   pool_not_auto，DR-125/DR-136）并按条件给出文案；
 *   no_available_address 携带 {network_id, ip_pool_id}（不切换其它池）；
 *   reference_exists 携带 references（未删 Endpoint，F012 注册后非空；本 Feature 空集）；
 *   dependency_deleted 携带 conflicts 并按 object_type 区分文案（network=所属网络 /
 *   interface=绑定接口）；not_deleted = 对未软删对象 restore。
 * - 422 VALIDATION_ERROR：details.fields → 字段级错误（点路径 network/address/
 *   interface/description，Contract §2.3；恢复 CIDR 越界为 field="address"）。
 * - 403 / 404：明确文案（权限不足 / 对象不存在，不泄露存在性细节）。
 */
export interface IpAddressActionError {
  message: string;
  code: string | null;
  /** 409 VERSION_CONFLICT（乐观锁过期，需刷新后重改）。 */
  versionConflict: boolean;
  /** 服务器当前版本（VERSION_CONFLICT details.current_version；未知为 null）。 */
  currentVersion: number | null;
  /** 字段级错误（422 fields / 409 CONFLICT unique_conflict 的 field）。 */
  fields: Record<string, string>;
  /** 解绑/转移/释放被引用阻止时的引用列表（CONFLICT reference_exists）。 */
  references: IpAddressReferenceItem[];
  /** 恢复时依赖仍软删的冲突列表（CONFLICT dependency_deleted）。 */
  dependencyConflicts: IpAddressDependencyConflictItem[];
  /** allocation_not_allowed 的条件（无该 reason 时 null）。 */
  allocationCondition: AllocationCondition | null;
  /** no_available_address 的池信息（无该 reason 时 null）。 */
  noAvailable: NoAvailableAddressInfo | null;
}

const CONFLICT_REASON_MESSAGES: Record<string, string> = {
  unique_conflict:
    "该地址与同集群内现存（未删除）IP 地址冲突（地址唯一按 Cluster 作用域，跨网络/地址池；不同集群可重复；已软删地址不占用，软删后可复用）",
  not_deleted: "该 IP 地址未处于已删除状态，无需恢复",
  reference_exists:
    "仍存在未删除对象引用该 IP 地址（如 Endpoint），无法解绑/转移/释放；请先处理这些引用后再试（不隐式级联、不自动解绑）",
};

/** allocation_not_allowed 的条件文案（Contract §1.2；未知条件回退通用文案）。 */
const ALLOCATION_CONDITION_MESSAGES: Record<AllocationCondition, string> = {
  network_inactive:
    "分配失败：所属网络处于 INACTIVE 状态，不允许新增分配（仅绑定/解绑/转移等关系编辑不受限）（CONFLICT/allocation_not_allowed，condition=network_inactive）",
  auto_allocate_disabled:
    "自动分配失败：该网络未开启 auto_allocate 自动分配（CONFLICT/allocation_not_allowed，condition=auto_allocate_disabled）",
  pool_not_auto:
    "自动分配失败：所选地址池不是 AUTO 分配模式，不降级为手动分配（CONFLICT/allocation_not_allowed，condition=pool_not_auto）",
};

/**
 * dependency_deleted 的文案按 conflicts 的 object_type 区分（Contract §1.2：
 * network=所属 Network 仍软删/缺失；interface=绑定 Interface 失效）：
 * 恢复失败不覆盖新对象。冲突列表为空 / 形状不符时用通用文案，不伪装成已知原因。
 */
function dependencyDeletedMessage(
  conflicts: IpAddressDependencyConflictItem[],
): string {
  const types = new Set(conflicts.map((conflict) => conflict.object_type));
  if (types.size === 1 && types.has("network")) {
    return (
      "恢复失败：所属网络（network）仍处于已删除状态或已不存在，" +
      "需先恢复所属网络后再恢复该 IP 地址（恢复不会覆盖网络或其上新对象）"
    );
  }
  if (types.size === 1 && types.has("interface")) {
    return (
      "恢复失败：绑定的接口（interface）仍处于已删除状态或已不存在，" +
      "需先恢复该接口后再恢复该 IP 地址（恢复不会覆盖接口或其上新对象）"
    );
  }
  return "恢复失败：依赖对象仍处于已删除状态，需先恢复对应依赖对象后再重试";
}

/** 把写操作错误归类为页面可直接呈现的结构（不抛出、不重试）。 */
export function describeIpAddressActionError(error: unknown): IpAddressActionError {
  if (!isApiError(error)) {
    // 网络层错误（fetch reject）：固定文案，不伪装成业务结果
    return {
      message: "无法连接服务器，请稍后重试",
      code: null,
      versionConflict: false,
      currentVersion: null,
      fields: {},
      references: [],
      dependencyConflicts: [],
      allocationCondition: null,
      noAvailable: null,
    };
  }

  const result: IpAddressActionError = {
    message: displayError(error),
    code: error.code,
    versionConflict: false,
    currentVersion: null,
    fields: {},
    references: [],
    dependencyConflicts: [],
    allocationCondition: null,
    noAvailable: null,
  };
  const details = error.details ?? {};

  if (error.status === 409 && error.code === "VERSION_CONFLICT") {
    result.versionConflict = true;
    const current = details["current_version"];
    if (typeof current === "number") {
      result.currentVersion = current;
    }
    result.message =
      `该 IP 地址已被其他人修改（服务器当前版本 ${result.currentVersion ?? "未知"}）。` +
      "请刷新最新数据后重新操作；系统不会自动重试或覆盖他人修改。";
  } else if (error.status === 409 && error.code === "CONFLICT") {
    const reason = details["reason"];
    if (reason === "unique_conflict") {
      // field 恒为 "address"（Contract §1.2）；形状不符时回退 address，不伪造其它字段
      const field = details["field"];
      const fieldName = typeof field === "string" && field !== "" ? field : "address";
      result.fields[fieldName] = CONFLICT_REASON_MESSAGES["unique_conflict"];
      result.message = `保存失败：${fieldName} 冲突。`;
    } else if (reason === "allocation_not_allowed") {
      const condition = details["condition"];
      if (
        condition === "network_inactive" ||
        condition === "auto_allocate_disabled" ||
        condition === "pool_not_auto"
      ) {
        result.allocationCondition = condition;
        result.message = ALLOCATION_CONDITION_MESSAGES[condition];
      } else {
        result.message = `分配失败：分配条件不满足（CONFLICT/allocation_not_allowed${
          typeof condition === "string" ? `，condition=${condition}` : ""
        }）`;
      }
    } else if (reason === "no_available_address") {
      result.noAvailable = {
        network_id: typeof details["network_id"] === "string" ? details["network_id"] : null,
        ip_pool_id: typeof details["ip_pool_id"] === "string" ? details["ip_pool_id"] : null,
      };
      result.message =
        "自动分配失败：所选 AUTO 地址池范围内已无可用地址（不切换其它地址池；" +
        "可扩大池范围、释放池内地址或改用手动分配）（CONFLICT/no_available_address）";
    } else if (reason === "dependency_deleted") {
      result.dependencyConflicts = parseDependencyConflicts(details["conflicts"]);
      result.message = `${dependencyDeletedMessage(result.dependencyConflicts)}（CONFLICT/dependency_deleted）`;
    } else if (typeof reason === "string" && reason in CONFLICT_REASON_MESSAGES) {
      result.message = `${CONFLICT_REASON_MESSAGES[reason]}（CONFLICT/${reason}）`;
      if (reason === "reference_exists") {
        result.references = parseReferences(details["references"]);
      }
    } else {
      result.message = `操作冲突：${error.message}（CONFLICT）`;
    }
  } else if (error.status === 422 && error.code === "VALIDATION_ERROR") {
    result.fields = envelopeFieldErrors(error.details);
  } else if (error.status === 403) {
    result.message = "没有权限执行该操作（服务端已拒绝，FORBIDDEN）。";
  } else if (error.status === 404) {
    result.message = "IP 地址不存在，或已删除且您无权查看（NOT_FOUND）。";
  }
  return result;
}

/** 解析 CONFLICT reference_exists 的 references 列表（形状不符返回空数组）。 */
function parseReferences(value: unknown): IpAddressReferenceItem[] {
  if (!Array.isArray(value)) {
    return [];
  }
  const references: IpAddressReferenceItem[] = [];
  for (const item of value) {
    if (typeof item !== "object" || item === null) {
      continue;
    }
    const { object_type, object_id, label } = item as Record<string, unknown>;
    if (typeof object_type === "string" && typeof object_id === "string") {
      references.push({
        object_type,
        object_id,
        label: typeof label === "string" ? label : null,
      });
    }
  }
  return references;
}

/** 解析 CONFLICT dependency_deleted 的 conflicts 列表（形状不符返回空数组）。 */
function parseDependencyConflicts(value: unknown): IpAddressDependencyConflictItem[] {
  if (!Array.isArray(value)) {
    return [];
  }
  const conflicts: IpAddressDependencyConflictItem[] = [];
  for (const item of value) {
    if (typeof item !== "object" || item === null) {
      continue;
    }
    const { object_type, object_id } = item as Record<string, unknown>;
    if (typeof object_type === "string" && typeof object_id === "string") {
      conflicts.push({ object_type, object_id });
    }
  }
  return conflicts;
}
