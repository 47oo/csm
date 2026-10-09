/**
 * IP Pool API（F009，Contract：docs/api/F009.md v1，READY）。
 *
 * 端点（Contract §6）：
 * - GET    /ip-pools                          列表（分页/排序/过滤/软删可见性，§4/§5）
 * - POST   /ip-pools                          创建（201 {"ip_pool":IPPool}）
 * - GET    /ip-pools/{id}                     详情（?deleted=true 需 VIEW_DELETED）
 * - PATCH  /ip-pools/{id}                     部分更新（body 必带 version）
 * - DELETE /ip-pools/{id}?version=N           软删（204；不做 IP 分配来源引用检查，§6.5/DR-108）
 * - POST   /ip-pools/{id}/restore?version=N   恢复（200，重检 name/network/CIDR/重叠/RESERVED 占用）
 * - GET    /ip-pools/{id}/activity            对象 Activity（VIEW_ACTIVITY，全角色）
 *
 * 注意：
 * - IPPool 为独立可寻址对象（自身 UUID/version/软删/恢复/Activity，DR-102/DR-111），
 *   归属 Network 经 network_id 关联；network 创建必填、创建后不可改
 *   （PATCH 携带 network/network_id → 422，DR-107，本 client 的 PATCH 载荷恒不含该键）。
 * - name 大小写不敏感（ASCII 折叠）、同 Network 未删唯一、软删后可复用（§2.1）；
 *   start/end 为单个 IPv4 主机地址（非 CIDR/掩码）、须属所属 Network CIDR、
 *   start ≤ end（start=end 为单地址池，§2.2）；同 Network 未删池闭区间不重叠
 *   （含共享端点）由服务端 409 range_overlap 承载；allocation_mode ∈
 *   {MANUAL, AUTO, RESERVED} 默认 MANUAL；description nullable、无长度上限；
 *   IPPool 无 metadata（请求含 metadata → 422，I-6）。
 * - PATCH 仅携带变化字段（省略 = 保持原值不重置，exclude_unset，§2.4）。
 * - 409 CONFLICT（unique_conflict / range_overlap / address_in_use / not_deleted /
 *   dependency_deleted）/ VERSION_CONFLICT 的页面呈现语义见
 *   describeIpPoolActionError；任何写失败都不自动重试（Contract §7）。
 * - 本文件 import 显式带 .ts 扩展名：scripts/smoke-client.mjs 以 Node
 *   type stripping 直接加载本模块做机制级冒烟（同 src/api/*.ts）。
 */
import { displayError, envelopeFieldErrors, isApiError, request } from "./client.ts";
import type { DeletedMode, SortOrder } from "./clusters.ts";

/** 软删可见性 / 排序方向与 F003 同一语义，复用同一类型定义（Contract §4/§5）。 */
export type { DeletedMode, SortOrder } from "./clusters.ts";

/** allocation_mode（Contract §2.2：MANUAL|AUTO|RESERVED，创建默认 MANUAL；分配执行 F010）。 */
export type IpPoolAllocationMode = "MANUAL" | "AUTO" | "RESERVED";

/** 列表排序字段白名单（Contract §4；sort=name 按 name_key）。 */
export type IpPoolSortField =
  | "name"
  | "start_address"
  | "end_address"
  | "allocation_mode"
  | "created_at"
  | "updated_at";

/** IPPool 响应内嵌的所属 Network 引用（Contract §3：{id,name,cidr}，只读）。 */
export interface IpPoolNetworkRef {
  id: string;
  name: string;
  cidr: string;
}

/**
 * IPPool 响应对象（Contract §3）。
 * description 未设置为 null，绝不以空串代替（D01 §5.8）；
 * name_key/address_range 不暴露；响应不含 metadata（I-6）。
 */
export interface IpPool {
  id: string;
  network: IpPoolNetworkRef;
  /** 大小写不敏感唯一（同 Network 未删），保留展示大小写（§2.1）。 */
  name: string;
  /** IPv4 主机地址（非 CIDR/掩码），属所属 Network CIDR（§2.2）。 */
  start_address: string;
  end_address: string;
  allocation_mode: IpPoolAllocationMode;
  description: string | null;
  version: number;
  created_at: string;
  updated_at: string;
  deleted_at: string | null;
}

/** 列表响应（Contract §4：{items, page, page_size, total}）。 */
export interface IpPoolListResponse {
  items: IpPool[];
  page: number;
  page_size: number;
  total: number;
}

/** 单对象响应信封（Contract §6.2/§6.3/§6.4/§6.6：{"ip_pool":IPPool}）。 */
export interface IpPoolEnvelope {
  ip_pool: IpPool;
}

/** Activity 条目（Contract §6.7；只读，无修改/删除入口）。 */
export interface IpPoolActivityItem {
  id: string;
  action: "CREATE" | "UPDATE" | "DELETE" | "RESTORE";
  operator_user_id: string | null;
  operator_username: string;
  before_data: Record<string, unknown> | null;
  after_data: Record<string, unknown> | null;
  created_at: string;
}

/** Activity 响应（Contract §6.7：created_at 升序、同刻 id 升序）。 */
export interface IpPoolActivityResponse {
  items: IpPoolActivityItem[];
  page: number;
  page_size: number;
  total: number;
}

/** GET /ip-pools 查询参数（省略项不发，由服务端默认值生效，Contract §4）。 */
export interface ListIpPoolsQuery {
  /** 所属 Network UUID 精确过滤（非 UUID → 422；不存在 → 空结果非 404）。 */
  network_id?: string;
  allocation_mode?: IpPoolAllocationMode;
  /** 对 name 的大小写不敏感子串匹配（空/纯空白视为未提供；不用 pg_trgm）。 */
  q?: string;
  deleted?: DeletedMode;
  page?: number;
  page_size?: number;
  sort?: IpPoolSortField;
  order?: SortOrder;
}

/** 列表查询：GET /api/v1/ip-pools（READ；deleted=include|only 另需 VIEW_DELETED）。 */
export function listIpPools(query: ListIpPoolsQuery = {}): Promise<IpPoolListResponse> {
  const search = new URLSearchParams();
  if (query.network_id !== undefined && query.network_id !== "") {
    search.set("network_id", query.network_id);
  }
  if (query.allocation_mode !== undefined) {
    search.set("allocation_mode", query.allocation_mode);
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
  return request<IpPoolListResponse>(`/ip-pools${queryString ? `?${queryString}` : ""}`);
}

/**
 * POST /ip-pools 请求体（Contract §6.2）。
 * network/name/start_address/end_address 必填；allocation_mode 省略默认
 * MANUAL（表单恒显式携带）；description 省略 → null；
 * metadata 等未列 / 只读字段不可出现（→ 422，I-6）。
 */
export interface CreateIpPoolPayload {
  /** 所属 Network UUID（创建必填、须存在未软删，§2.2；创建后不可改，DR-107）。 */
  network: string;
  name: string;
  start_address: string;
  end_address: string;
  allocation_mode?: IpPoolAllocationMode;
  description?: string;
}

/** 创建：POST /api/v1/ip-pools（WRITE）；201；name 唯一 / 范围重叠 / RESERVED 占用冲突 409 CONFLICT。 */
export function createIpPool(payload: CreateIpPoolPayload): Promise<IpPoolEnvelope> {
  return request<IpPoolEnvelope>("/ip-pools", { method: "POST", body: payload });
}

/** 详情：GET /api/v1/ip-pools/{id}（READ）。已删对象需显式 deleted=true 且具 VIEW_DELETED，否则 404（§5）。 */
export function getIpPool(
  id: string,
  options: { deleted?: boolean } = {},
): Promise<IpPoolEnvelope> {
  const search = new URLSearchParams();
  if (options.deleted) {
    search.set("deleted", "true");
  }
  const queryString = search.toString();
  return request<IpPoolEnvelope>(
    `/ip-pools/${encodeURIComponent(id)}${queryString ? `?${queryString}` : ""}`,
  );
}

/**
 * PATCH /ip-pools/{id} 请求体（Contract §6.4，exclude_unset）。
 * version 必填；其余字段省略 = 保持原值不重置；description 显式 null = 清空；
 * name 改后重检同 Network 唯一；start/end/allocation_mode 变更由服务端重检
 * CIDR 包含 / 重叠 / RESERVED 占用（DR-110）；
 * network/network_id/id 等不可变 / 只读字段不可出现在请求体（→ 422，DR-107）。
 */
export interface UpdateIpPoolPayload {
  version: number;
  name?: string;
  start_address?: string;
  end_address?: string;
  allocation_mode?: IpPoolAllocationMode;
  description?: string | null;
}

/** 部分更新：PATCH /api/v1/ip-pools/{id}（WRITE）；成功 200，version+1。 */
export function updateIpPool(
  id: string,
  payload: UpdateIpPoolPayload,
): Promise<IpPoolEnvelope> {
  return request<IpPoolEnvelope>(`/ip-pools/${encodeURIComponent(id)}`, {
    method: "PATCH",
    body: payload,
  });
}

/**
 * 软删：DELETE /api/v1/ip-pools/{id}?version=N（DELETE_OBJECT；204）。
 * 不级联；不做 IP 分配来源引用检查、不回收已分配 IP（§12/§21 例外，DR-108）。
 */
export function deleteIpPool(id: string, version: number): Promise<void> {
  const search = new URLSearchParams({ version: String(version) });
  return request<void>(`/ip-pools/${encodeURIComponent(id)}?${search.toString()}`, {
    method: "DELETE",
  });
}

/**
 * 恢复：POST /api/v1/ip-pools/{id}/restore?version=N（RESTORE；200，仅恢复自身）。
 * 重检同 Network name 唯一、所属 Network 未软删、起止仍属 CIDR、范围不重叠、
 * RESERVED 另检占用；失败不覆盖新对象（§6.6/DR-112）。
 */
export function restoreIpPool(id: string, version: number): Promise<IpPoolEnvelope> {
  const search = new URLSearchParams({ version: String(version) });
  return request<IpPoolEnvelope>(
    `/ip-pools/${encodeURIComponent(id)}/restore?${search.toString()}`,
    { method: "POST" },
  );
}

/** 对象 Activity：GET /api/v1/ip-pools/{id}/activity（VIEW_ACTIVITY，全角色）。 */
export function getIpPoolActivity(
  id: string,
  query: { deleted?: boolean; page?: number; page_size?: number } = {},
): Promise<IpPoolActivityResponse> {
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
  return request<IpPoolActivityResponse>(
    `/ip-pools/${encodeURIComponent(id)}/activity${queryString ? `?${queryString}` : ""}`,
  );
}

/** range_overlap 冲突明细：同 Network 未删池（Contract §1.2；label 可能缺失）。 */
export interface IpPoolRangeConflictItem {
  object_type: string;
  object_id: string;
  label: string | null;
  start_address: string;
  end_address: string;
}

/** address_in_use 冲突明细：范围内未删 IP（含未绑定，Contract §1.2/DR-110）。 */
export interface IpOccupancyConflictItem {
  object_type: string;
  object_id: string;
  address: string;
  /** 是否已绑定 Interface（bound=false 表示未绑定但已登记）。 */
  bound: boolean;
  interface_id: string | null;
  resource_id: string | null;
  resource_hostname: string | null;
}

/** address_in_use 的解析结果（conflict_count 为总数；conflicts 为预览，至多 CONFLICT_PREVIEW_LIMIT 条）。 */
export interface IpOccupancyInfo {
  /** 服务端 details.field（start_address/end_address/allocation_mode/gateway）。 */
  field: string;
  /** 变更后范围内未删 IP 的总数（details.conflict_count）。 */
  count: number;
  /** 冲突预览明细（details.conflicts；截断时仅含前 CONFLICT_PREVIEW_LIMIT 条）。 */
  conflicts: IpOccupancyConflictItem[];
  /** details.conflicts_truncated：true 表示预览被截断，完整明细由 F010 列表查询。 */
  truncated: boolean;
}

/** dependency_deleted 冲突明细：恢复时所属 Network 仍软删/缺失（Contract §1.2）。 */
export interface IpPoolDependencyConflictItem {
  object_type: string;
  object_id: string;
}

/**
 * 面向页面的写操作错误描述（Contract §1.2/§7）：
 * - 409 VERSION_CONFLICT：versionConflict=true 并携带 current_version；
 *   页面提示刷新后重新操作，绝不静默重试 / 覆盖。
 * - 409 CONFLICT：按 details.reason 映射；
 *   unique_conflict 落为 name 字段级错误（field 恒为 "name"，§1.2）；
 *   range_overlap 落为 start_address/end_address 字段级错误并携带 conflicts
 *   （重叠 IPPool 列表，含起止地址）；
 *   address_in_use 落为对应字段级错误并携带 occupancy（conflict_count 总数 +
 *   conflicts 预览 + conflicts_truncated，DR-110）；
 *   dependency_deleted 携带 conflicts（object_type=network，恢复时所属
 *   Network 仍删/缺失）；
 *   not_deleted = 对未软删对象 restore。
 * - 422 VALIDATION_ERROR：details.fields → 字段级错误（network / name /
 *   start_address / end_address / allocation_mode / description，Contract §2.3）。
 * - 403 / 404：明确文案（权限不足 / 对象不存在，不泄露存在性细节）。
 */
export interface IpPoolActionError {
  message: string;
  code: string | null;
  /** 409 VERSION_CONFLICT（乐观锁过期，需刷新后重改）。 */
  versionConflict: boolean;
  /** 服务器当前版本（VERSION_CONFLICT details.current_version；未知为 null）。 */
  currentVersion: number | null;
  /** 字段级错误（422 fields / 409 CONFLICT 的 field）。 */
  fields: Record<string, string>;
  /** 范围重叠冲突列表（CONFLICT range_overlap；含起止地址）。 */
  rangeConflicts: IpPoolRangeConflictItem[];
  /** RESERVED / 范围扩大占用的冲突结构（CONFLICT address_in_use；无该 reason 时 null）。 */
  occupancy: IpOccupancyInfo | null;
  /** 恢复时依赖仍软删的冲突列表（CONFLICT dependency_deleted）。 */
  dependencyConflicts: IpPoolDependencyConflictItem[];
}

const CONFLICT_REASON_MESSAGES: Record<string, string> = {
  unique_conflict:
    "name 与该网络内现存（未删除）地址池冲突（大小写不敏感；已软删地址池不占用名称，软删后可复用）",
  not_deleted: "该地址池未处于已删除状态，无需恢复",
};

/** address_in_use 的文案（Contract §1.2/DR-110：变更后范围内存在未删 IP，含未绑定）。 */
function addressInUseMessage(occupancy: IpOccupancyInfo): string {
  const truncatedNote = occupancy.truncated
    ? `；明细预览已截断，仅显示前 ${occupancy.conflicts.length} 条，完整明细可通过 IP 地址列表（F010）查询`
    : "";
  return (
    `保存失败：变更后的地址范围内存在 ${occupancy.count} 个未删除的 IP 地址（含未绑定接口的记录），` +
    `无法设为 RESERVED 或扩大保留范围（CONFLICT/address_in_use，field=${occupancy.field}）` +
    truncatedNote
  );
}

/** 把写操作错误归类为页面可直接呈现的结构（不抛出、不重试）。 */
export function describeIpPoolActionError(error: unknown): IpPoolActionError {
  if (!isApiError(error)) {
    // 网络层错误（fetch reject）：固定文案，不伪装成业务结果
    return {
      message: "无法连接服务器，请稍后重试",
      code: null,
      versionConflict: false,
      currentVersion: null,
      fields: {},
      rangeConflicts: [],
      occupancy: null,
      dependencyConflicts: [],
    };
  }

  const result: IpPoolActionError = {
    message: displayError(error),
    code: error.code,
    versionConflict: false,
    currentVersion: null,
    fields: {},
    rangeConflicts: [],
    occupancy: null,
    dependencyConflicts: [],
  };
  const details = error.details ?? {};

  if (error.status === 409 && error.code === "VERSION_CONFLICT") {
    result.versionConflict = true;
    const current = details["current_version"];
    if (typeof current === "number") {
      result.currentVersion = current;
    }
    result.message =
      `该地址池已被其他人修改（服务器当前版本 ${result.currentVersion ?? "未知"}）。` +
      "请刷新最新数据后重新操作；系统不会自动重试或覆盖他人修改。";
  } else if (error.status === 409 && error.code === "CONFLICT") {
    const reason = details["reason"];
    if (reason === "unique_conflict") {
      // field 恒为 "name"（Contract §1.2）；形状不符时回退 name，不伪造其它字段
      const field = details["field"];
      const fieldName = typeof field === "string" && field !== "" ? field : "name";
      result.fields[fieldName] = CONFLICT_REASON_MESSAGES["unique_conflict"];
      result.message = `保存失败：${fieldName} 冲突。`;
    } else if (reason === "range_overlap") {
      // field ∈ {start_address, end_address}（Contract §1.2）；conflicts 为重叠 IPPool 明细
      const field = details["field"];
      const fieldName =
        field === "end_address" ? "end_address" : "start_address";
      result.rangeConflicts = parseRangeConflicts(details["conflicts"]);
      result.fields[fieldName] =
        "该地址范围与同网络内现存（未删除）地址池重叠（闭区间，含共享端点；已软删地址池不占用范围）";
      result.message =
        "保存失败：地址范围与同网络内现存地址池重叠，请调整起止地址后重试（CONFLICT/range_overlap）。";
    } else if (reason === "address_in_use") {
      // field ∈ {start_address, end_address, allocation_mode, gateway}（Contract §1.2/DR-110）
      const occupancy = parseOccupancy(details);
      result.occupancy = occupancy;
      result.fields[occupancy.field] =
        "变更后的地址范围内存在未删除的 IP 地址（含未绑定接口的记录），无法设为 RESERVED 或扩大保留范围";
      result.message = addressInUseMessage(occupancy);
    } else if (reason === "dependency_deleted") {
      result.dependencyConflicts = parseDependencyConflicts(details["conflicts"]);
      result.message =
        "恢复失败：所属网络（network）仍处于已删除状态或已不存在，" +
        "需先恢复所属网络后再恢复该地址池（恢复不会覆盖网络或其上新对象）（CONFLICT/dependency_deleted）";
    } else if (typeof reason === "string" && reason in CONFLICT_REASON_MESSAGES) {
      result.message = `${CONFLICT_REASON_MESSAGES[reason]}（CONFLICT/${reason}）`;
    } else {
      result.message = `操作冲突：${error.message}（CONFLICT）`;
    }
  } else if (error.status === 422 && error.code === "VALIDATION_ERROR") {
    result.fields = envelopeFieldErrors(error.details);
  } else if (error.status === 403) {
    result.message = "没有权限执行该操作（服务端已拒绝，FORBIDDEN）。";
  } else if (error.status === 404) {
    result.message = "地址池不存在，或已删除且您无权查看（NOT_FOUND）。";
  }
  return result;
}

/** 解析 range_overlap 的 conflicts（IPPool 明细含起止地址；形状不符返回空数组）。 */
function parseRangeConflicts(value: unknown): IpPoolRangeConflictItem[] {
  if (!Array.isArray(value)) {
    return [];
  }
  const items: IpPoolRangeConflictItem[] = [];
  for (const item of value) {
    if (typeof item !== "object" || item === null) {
      continue;
    }
    const {
      object_type,
      object_id,
      label,
      start_address,
      end_address,
    } = item as Record<string, unknown>;
    if (
      typeof object_type === "string" &&
      typeof object_id === "string" &&
      typeof start_address === "string" &&
      typeof end_address === "string"
    ) {
      items.push({
        object_type,
        object_id,
        label: typeof label === "string" ? label : null,
        start_address,
        end_address,
      });
    }
  }
  return items;
}

/** 解析 address_in_use 的占用结构（count / conflicts / truncated；缺省保守回退）。 */
function parseOccupancy(details: Record<string, unknown>): IpOccupancyInfo {
  const rawField = details["field"];
  const field = typeof rawField === "string" && rawField !== "" ? rawField : "allocation_mode";
  const rawCount = details["conflict_count"];
  const conflicts = parseOccupancyConflicts(details["conflicts"]);
  const count = typeof rawCount === "number" ? rawCount : conflicts.length;
  return {
    field,
    count,
    conflicts,
    truncated: details["conflicts_truncated"] === true,
  };
}

/** 解析 address_in_use 的 conflicts（IPAddress 明细；形状不符返回空数组）。 */
function parseOccupancyConflicts(value: unknown): IpOccupancyConflictItem[] {
  if (!Array.isArray(value)) {
    return [];
  }
  const items: IpOccupancyConflictItem[] = [];
  for (const item of value) {
    if (typeof item !== "object" || item === null) {
      continue;
    }
    const {
      object_type,
      object_id,
      address,
      bound,
      interface_id,
      resource_id,
      resource_hostname,
    } = item as Record<string, unknown>;
    if (
      typeof object_type === "string" &&
      typeof object_id === "string" &&
      typeof address === "string"
    ) {
      items.push({
        object_type,
        object_id,
        address,
        bound: bound === true,
        interface_id: typeof interface_id === "string" ? interface_id : null,
        resource_id: typeof resource_id === "string" ? resource_id : null,
        resource_hostname: typeof resource_hostname === "string" ? resource_hostname : null,
      });
    }
  }
  return items;
}

/** 解析 dependency_deleted 的 conflicts（network 明细；形状不符返回空数组）。 */
function parseDependencyConflicts(value: unknown): IpPoolDependencyConflictItem[] {
  if (!Array.isArray(value)) {
    return [];
  }
  const items: IpPoolDependencyConflictItem[] = [];
  for (const item of value) {
    if (typeof item !== "object" || item === null) {
      continue;
    }
    const { object_type, object_id } = item as Record<string, unknown>;
    if (typeof object_type === "string" && typeof object_id === "string") {
      items.push({ object_type, object_id });
    }
  }
  return items;
}
