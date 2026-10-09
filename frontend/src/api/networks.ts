/**
 * Network API（F008，Contract：docs/api/F008.md v1，READY）。
 *
 * 端点（Contract §6）：
 * - GET    /networks                          列表（分页/排序/过滤/软删可见性，§4/§5）
 * - POST   /networks                          创建（201 {"network":Network}）
 * - GET    /networks/{id}                     详情（?deleted=true 需 VIEW_DELETED）
 * - PATCH  /networks/{id}                     部分更新（body 必带 version）
 * - DELETE /networks/{id}?version=N           软删（204；version 为 Query 参数，§6.5）
 * - POST   /networks/{id}/restore?version=N   恢复（200，重检 name/cluster/CIDR）
 * - GET    /networks/{id}/activity            对象 Activity（VIEW_ACTIVITY，全角色）
 *
 * 注意：
 * - Network 为独立可寻址对象（自身 UUID/version/软删/恢复/Activity，DR-89/DR-97），
 *   不并入 /clusters 嵌套；cluster 创建必填，可在有未删除 Pool/IP 引用前变更（I-4）。
 * - name 大小写不敏感（ASCII 折叠）、同 Cluster 未删唯一、软删后可复用（§2.1）；
 *   cidr 为合法 IPv4 CIDR，host 位由服务端归一化为网络地址（§2.2）；
 *   gateway 可选 nullable IPv4，须属 CIDR 基础可用地址且非禁用范围（§2.2/§11.1）；
 *   status 默认 ACTIVE；auto_allocate 默认 false；metadata Network 自有（DR-95）。
 * - PATCH 仅携带变化字段（省略 = 保持原值不重置，Contract §6.4）。
 * - 409 CONFLICT（unique_conflict / range_overlap / reference_exists / not_deleted /
 *   dependency_deleted）/ VERSION_CONFLICT 的页面呈现语义见
 *   describeNetworkActionError；任何写失败都不自动重试（Contract §7）。
 * - 本文件 import 显式带 .ts 扩展名：scripts/smoke-client.mjs 以 Node
 *   type stripping 直接加载本模块做机制级冒烟（同 src/api/*.ts）。
 */
import { displayError, envelopeFieldErrors, isApiError, request } from "./client.ts";
import type { DeletedMode, SortOrder } from "./clusters.ts";

/** 软删可见性 / 排序方向与 F003 同一语义，复用同一类型定义（Contract §4/§5）。 */
export type { DeletedMode, SortOrder } from "./clusters.ts";

/** Network 状态（Contract §2.2/§3：ACTIVE | INACTIVE，创建默认 ACTIVE）。 */
export type NetworkStatus = "ACTIVE" | "INACTIVE";

/** 列表排序字段白名单（Contract §4；sort=name 按 name_key）。 */
export type NetworkSortField =
  | "name"
  | "cidr"
  | "status"
  | "created_at"
  | "updated_at";

/** Network 响应内嵌的所属 Cluster 引用（Contract §3：{id, code, name}，只读）。 */
export interface NetworkClusterRef {
  id: string;
  code: string;
  name: string;
}

/**
 * Network 响应对象（Contract §3）。
 * gateway/description 未设置为 null，绝不以空串代替（D01 §5.6）；
 * metadata 为 Network 自有（DR-95）；name_key 不暴露。
 */
export interface Network {
  id: string;
  cluster: NetworkClusterRef;
  /** 大小写不敏感唯一，保留展示大小写（§2.1）。 */
  name: string;
  /** 归一化后的网络地址（PG cidr，如 10.0.0.0/24）。 */
  cidr: string;
  gateway: string | null;
  status: NetworkStatus;
  auto_allocate: boolean;
  description: string | null;
  metadata: Record<string, unknown>;
  version: number;
  created_at: string;
  updated_at: string;
  deleted_at: string | null;
}

/** 列表响应（Contract §4：{items, page, page_size, total}）。 */
export interface NetworkListResponse {
  items: Network[];
  page: number;
  page_size: number;
  total: number;
}

/** 单对象响应信封（Contract §6.2/§6.3/§6.4/§6.6：{"network":Network}）。 */
export interface NetworkEnvelope {
  network: Network;
}

/** Activity 条目（Contract §6.7；只读，无修改/删除入口）。 */
export interface NetworkActivityItem {
  id: string;
  action: "CREATE" | "UPDATE" | "DELETE" | "RESTORE";
  operator_user_id: string | null;
  operator_username: string;
  before_data: Record<string, unknown> | null;
  after_data: Record<string, unknown> | null;
  created_at: string;
}

/** Activity 响应（Contract §6.7：created_at 升序、同刻 id 升序）。 */
export interface NetworkActivityResponse {
  items: NetworkActivityItem[];
  page: number;
  page_size: number;
  total: number;
}

/** GET /networks 查询参数（省略项不发，由服务端默认值生效，Contract §4）。 */
export interface ListNetworksQuery {
  /** 对 name 的大小写不敏感子串匹配（空/纯空白视为未提供；不用 pg_trgm）。 */
  q?: string;
  /** 所属 Cluster UUID 精确过滤（非 UUID → 422；不存在 → 空结果非 404）。 */
  cluster_id?: string;
  status?: NetworkStatus;
  auto_allocate?: boolean;
  deleted?: DeletedMode;
  page?: number;
  page_size?: number;
  sort?: NetworkSortField;
  order?: SortOrder;
}

/** 列表查询：GET /api/v1/networks（READ；deleted=include|only 另需 VIEW_DELETED）。 */
export function listNetworks(query: ListNetworksQuery = {}): Promise<NetworkListResponse> {
  const search = new URLSearchParams();
  if (query.q !== undefined && query.q !== "") {
    search.set("q", query.q);
  }
  if (query.cluster_id !== undefined && query.cluster_id !== "") {
    search.set("cluster_id", query.cluster_id);
  }
  if (query.status !== undefined) {
    search.set("status", query.status);
  }
  if (query.auto_allocate !== undefined) {
    search.set("auto_allocate", String(query.auto_allocate));
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
  return request<NetworkListResponse>(`/networks${queryString ? `?${queryString}` : ""}`);
}

/**
 * POST /networks 请求体（Contract §6.2）。
 * cluster/name/cidr 必填；status 省略默认 ACTIVE、auto_allocate 省略默认 false；
 * gateway/description 省略 → null；metadata 默认 {}、整值替换。
 */
export interface CreateNetworkPayload {
  /** 所属 Cluster UUID（创建必填、须存在未软删，§2.2）。 */
  cluster: string;
  name: string;
  cidr: string;
  gateway?: string;
  status?: NetworkStatus;
  auto_allocate?: boolean;
  description?: string;
  metadata?: Record<string, unknown>;
}

/** 创建：POST /api/v1/networks（WRITE）；201；同 Cluster 未删 name / CIDR 冲突 409 CONFLICT。 */
export function createNetwork(payload: CreateNetworkPayload): Promise<NetworkEnvelope> {
  return request<NetworkEnvelope>("/networks", { method: "POST", body: payload });
}

/** 详情：GET /api/v1/networks/{id}（READ）。已删对象需显式 deleted=true 且具 VIEW_DELETED，否则 404（§5）。 */
export function getNetwork(
  id: string,
  options: { deleted?: boolean } = {},
): Promise<NetworkEnvelope> {
  const search = new URLSearchParams();
  if (options.deleted) {
    search.set("deleted", "true");
  }
  const queryString = search.toString();
  return request<NetworkEnvelope>(
    `/networks/${encodeURIComponent(id)}${queryString ? `?${queryString}` : ""}`,
  );
}

/**
 * PATCH /networks/{id} 请求体（Contract §6.4）。
 * version 必填；其余字段省略 = 保持原值不重置；可空字段显式 null = 清空；
 * name 改后重检同 Cluster 唯一；cidr/cluster 改后重检引用与重叠；
 * metadata 整值替换；id / 只读字段不可出现在请求体。
 */
export interface UpdateNetworkPayload {
  version: number;
  name?: string;
  cidr?: string;
  /** 显式 null = 清空 gateway；改 cidr 时服务端重检边界。 */
  gateway?: string | null;
  cluster?: string;
  status?: NetworkStatus;
  auto_allocate?: boolean;
  description?: string | null;
  metadata?: Record<string, unknown>;
}

/** 部分更新：PATCH /api/v1/networks/{id}（WRITE）；成功 200，version+1。 */
export function updateNetwork(
  id: string,
  payload: UpdateNetworkPayload,
): Promise<NetworkEnvelope> {
  return request<NetworkEnvelope>(`/networks/${encodeURIComponent(id)}`, {
    method: "PATCH",
    body: payload,
  });
}

/** 软删：DELETE /api/v1/networks/{id}?version=N（DELETE_OBJECT；204，不级联；被未删 Pool/IP 引用 → 409 reference_exists）。 */
export function deleteNetwork(id: string, version: number): Promise<void> {
  const search = new URLSearchParams({ version: String(version) });
  return request<void>(`/networks/${encodeURIComponent(id)}?${search.toString()}`, {
    method: "DELETE",
  });
}

/** 恢复：POST /api/v1/networks/{id}/restore?version=N（RESTORE；200，仅恢复自身，重检 name/cluster/CIDR，不覆盖新对象）。 */
export function restoreNetwork(id: string, version: number): Promise<NetworkEnvelope> {
  const search = new URLSearchParams({ version: String(version) });
  return request<NetworkEnvelope>(
    `/networks/${encodeURIComponent(id)}/restore?${search.toString()}`,
    { method: "POST" },
  );
}

/** 对象 Activity：GET /api/v1/networks/{id}/activity（VIEW_ACTIVITY，全角色）。 */
export function getNetworkActivity(
  id: string,
  query: { deleted?: boolean; page?: number; page_size?: number } = {},
): Promise<NetworkActivityResponse> {
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
  return request<NetworkActivityResponse>(
    `/networks/${encodeURIComponent(id)}/activity${queryString ? `?${queryString}` : ""}`,
  );
}

/** range_overlap / dependency_deleted 冲突明细条目（label 可能缺失）。 */
export interface NetworkConflictItem {
  object_type: string;
  object_id: string;
  label: string | null;
}

/**
 * 面向页面的写操作错误描述（Contract §1.2/§7）：
 * - 409 VERSION_CONFLICT：versionConflict=true 并携带 current_version；
 *   页面提示刷新后重新操作，绝不静默重试 / 覆盖。
 * - 409 CONFLICT：按 details.reason 映射；
 *   unique_conflict 落为 name 字段级错误（field 恒为 "name"，§1.2）；
 *   range_overlap 落为 cidr 字段级错误并携带 conflicts（重叠 Network 列表）；
 *   reference_exists 携带 references（未删 IPPool / IPAddress，F009/F010）；
 *   dependency_deleted 携带 conflicts（object_type=cluster，恢复时所属 Cluster 仍删/缺失）；
 *   not_deleted = 对未软删对象 restore。
 * - 422 VALIDATION_ERROR：details.fields → 字段级错误（name / cluster / cidr /
 *   gateway / status / auto_allocate / metadata，Contract §2.3）。
 * - 403 / 404：明确文案（权限不足 / 对象不存在，不泄露存在性细节）。
 */
export interface NetworkActionError {
  message: string;
  code: string | null;
  /** 409 VERSION_CONFLICT（乐观锁过期，需刷新后重改）。 */
  versionConflict: boolean;
  /** 服务器当前版本（VERSION_CONFLICT details.current_version；未知为 null）。 */
  currentVersion: number | null;
  /** 字段级错误（422 fields / 409 CONFLICT unique_conflict 的 field / range_overlap 的 cidr）。 */
  fields: Record<string, string>;
  /** 删除/改 cidr/改 cluster 被引用阻止时的引用列表（CONFLICT reference_exists）。 */
  references: NetworkConflictItem[];
  /** CIDR 重叠冲突列表（CONFLICT range_overlap）。 */
  rangeConflicts: NetworkConflictItem[];
  /** 恢复时依赖仍软删的冲突列表（CONFLICT dependency_deleted）。 */
  dependencyConflicts: NetworkConflictItem[];
}

const CONFLICT_REASON_MESSAGES: Record<string, string> = {
  unique_conflict:
    "name 与该集群内现存（未删除）网络冲突（大小写不敏感；已软删网络不占用名称，软删后可复用）",
  not_deleted: "该网络未处于已删除状态，无需恢复",
  reference_exists:
    "仍存在未删除对象引用该网络（地址池 / IP 地址），无法删除或修改归属；请先处理这些引用后再试（不隐式级联）",
};

/**
 * dependency_deleted 的文案（Contract §1.2：恢复时所属 Cluster 仍软删 / 缺失）：
 * 恢复失败不覆盖新对象。
 */
function dependencyDeletedMessage(): string {
  return (
    "恢复失败：所属集群（cluster）仍处于已删除状态或已不存在，" +
    "需先恢复所属集群后再恢复该网络（恢复不会覆盖集群或其上新对象）"
  );
}

/** 把写操作错误归类为页面可直接呈现的结构（不抛出、不重试）。 */
export function describeNetworkActionError(error: unknown): NetworkActionError {
  if (!isApiError(error)) {
    // 网络层错误（fetch reject）：固定文案，不伪装成业务结果
    return {
      message: "无法连接服务器，请稍后重试",
      code: null,
      versionConflict: false,
      currentVersion: null,
      fields: {},
      references: [],
      rangeConflicts: [],
      dependencyConflicts: [],
    };
  }

  const result: NetworkActionError = {
    message: displayError(error),
    code: error.code,
    versionConflict: false,
    currentVersion: null,
    fields: {},
    references: [],
    rangeConflicts: [],
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
      `该网络已被其他人修改（服务器当前版本 ${result.currentVersion ?? "未知"}）。` +
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
      // field 恒为 "cidr"（Contract §1.2）；conflicts 为重叠 Network 明细
      result.rangeConflicts = parseConflicts(details["conflicts"]);
      result.fields["cidr"] =
        "该 CIDR 与同集群内现存（未删除）网络重叠（INACTIVE 网络同样参与重叠检查）";
      result.message =
        "保存失败：cidr 与同集群内现存网络重叠，请调整网段后重试（CONFLICT/range_overlap）。";
    } else if (reason === "dependency_deleted") {
      result.dependencyConflicts = parseConflicts(details["conflicts"]);
      result.message = `${dependencyDeletedMessage()}（CONFLICT/dependency_deleted）`;
    } else if (typeof reason === "string" && reason in CONFLICT_REASON_MESSAGES) {
      result.message = `${CONFLICT_REASON_MESSAGES[reason]}（CONFLICT/${reason}）`;
      if (reason === "reference_exists") {
        result.references = parseConflicts(details["references"]);
      }
    } else {
      result.message = `操作冲突：${error.message}（CONFLICT）`;
    }
  } else if (error.status === 422 && error.code === "VALIDATION_ERROR") {
    result.fields = envelopeFieldErrors(error.details);
  } else if (error.status === 403) {
    result.message = "没有权限执行该操作（服务端已拒绝，FORBIDDEN）。";
  } else if (error.status === 404) {
    result.message = "网络不存在，或已删除且您无权查看（NOT_FOUND）。";
  }
  return result;
}

/** 解析 CONFLICT conflicts / references 列表（形状不符返回空数组，label 缺失为 null）。 */
function parseConflicts(value: unknown): NetworkConflictItem[] {
  if (!Array.isArray(value)) {
    return [];
  }
  const items: NetworkConflictItem[] = [];
  for (const item of value) {
    if (typeof item !== "object" || item === null) {
      continue;
    }
    const { object_type, object_id, label } = item as Record<string, unknown>;
    if (typeof object_type === "string" && typeof object_id === "string") {
      items.push({
        object_type,
        object_id,
        label: typeof label === "string" ? label : null,
      });
    }
  }
  return items;
}