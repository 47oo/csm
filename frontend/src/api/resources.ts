/**
 * Resource API（F004，Contract：docs/api/F004.md v2，READY）。
 *
 * 端点（Contract §6）：
 * - GET    /resources                          列表（分页/排序/过滤/模糊/软删可见性，§4/§5）
 * - POST   /resources                          创建（201 {"resource":Resource}）
 * - GET    /resources/{id}                     详情（?deleted=true 需 VIEW_DELETED）
 * - PATCH  /resources/{id}                     部分更新（body 必带 version；cluster/resource_type 不可改）
 * - DELETE /resources/{id}?version=N           软删（204；version 为 Query 参数，§6.5）
 * - POST   /resources/{id}/restore?version=N   恢复（200 deleted_at=null，重检唯一性与所属 Cluster）
 * - GET    /resources/{id}/activity            对象 Activity（VIEW_ACTIVITY，全角色）
 *
 * 注意：
 * - 列表过滤参数名按 Contract §4：cluster=Cluster code、type=资源类型
 *   （无 resource_type 别名）；排序字段名则为 resource_type，两者不可互换。
 * - PATCH 仅携带变化字段（JSON.stringify 丢弃 undefined 属性；
 *   省略 = 保持原值不重置，Contract §6.4）；description 显式 null = 清空。
 * - BareMetal hardware（F005，Contract v2 §2.4）：hardware 仅适用于
 *   BARE_METAL；VM 请求体出现 hardware（含显式 null）→ 422（DR-51），
 *   因此 VM 载荷绝不携带 hardware 键；响应 hardware：BARE_METAL = 对象、
 *   VIRTUAL_MACHINE = null。未知子字段为 null，绝不以 0 代替
 *   （gpu_count=0 = 明确无 GPU，与 null=未知可区分）。不新增独立端点。
 * - 409 CONFLICT / VERSION_CONFLICT 的页面呈现语义见 describeResourceActionError；
 *   任何写失败都不自动重试（Contract §7）。
 * - 本文件 import 显式带 .ts 扩展名：scripts/smoke-client.mjs 以 Node
 *   type stripping 直接加载本模块做机制级冒烟（Vite 构建同样支持）。
 */
import { displayError, envelopeFieldErrors, isApiError, request } from "./client.ts";
import type { DeletedMode, SortOrder } from "./clusters.ts";

/** 软删可见性 / 排序方向与 F003 同一语义，复用同一类型定义（Contract §4/§5）。 */
export type { DeletedMode, SortOrder } from "./clusters.ts";

/** 资源类型（Contract §2.2：BARE_METAL | VIRTUAL_MACHINE，必填无默认，创建后不可改）。 */
export type ResourceType = "BARE_METAL" | "VIRTUAL_MACHINE";

/** 资源角色（Contract §2.2：默认 OTHER；可扩展）。 */
export type ResourceRole =
  | "COMPUTE"
  | "LOGIN"
  | "MANAGEMENT"
  | "STORAGE"
  | "SERVICE"
  | "GPU"
  | "OTHER";

/** 资源状态（Contract §2.2：默认 UNKNOWN，人工维护）。 */
export type ResourceStatus = "IDLE" | "ALLOC" | "DOWN" | "UNKNOWN";

/** 列表排序字段白名单（Contract §4；sort=hostname 实际按 hostname_key 排序）。 */
export type ResourceSortField =
  | "hostname"
  | "resource_type"
  | "role"
  | "status"
  | "created_at"
  | "updated_at";

/** Resource 响应内嵌的所属 Cluster（Contract §3：{id, code, name}）。 */
export interface ResourceClusterRef {
  id: string;
  code: string;
  name: string;
}

/**
 * BareMetal hardware 嵌套对象（Contract §2.4，v2 新增；仅 BARE_METAL）。
 *
 * 9 个硬件字段全部 nullable：未知 / 未登记 = null，绝不以 0 代替
 * （gpu_count=0 表示明确无 GPU，与 null=未知语义不同且可区分）；
 * cpu_cores 为整机物理核心总数（不含超线程，无跨字段推导）；
 * memory_mb 单位 MiB，原样存储不换算（1 GiB = 1024 MiB）；
 * 字符串为服务端 trim 后的展示值（≤255 code point，无唯一性 / 归一化键）。
 */
export interface Hardware {
  manufacturer: string | null;
  model: string | null;
  serial_number: string | null;
  cpu_model: string | null;
  /** CPU 插槽数，正整数或 null。 */
  cpu_sockets: number | null;
  /** 整机物理核心总数（不含超线程），正整数或 null。 */
  cpu_cores: number | null;
  /** 内存容量，单位 MiB，正整数或 null。 */
  memory_mb: number | null;
  gpu_model: string | null;
  /** GPU 数量，非负整数或 null；0 = 明确无 GPU，null = 未知。 */
  gpu_count: number | null;
  /** 厂商特有 / 低频扩展（JSONB，整值替换；区别于 Resource.metadata）。 */
  metadata: Record<string, unknown>;
}

/** POST hardware 输入（Contract §2.4）：仅携带已登记子字段——
 * 省略子字段 → null（无默认 0）；服务端为最终权威（trim / 范围 / 422）。 */
export interface HardwareInput {
  manufacturer?: string;
  model?: string;
  serial_number?: string;
  cpu_model?: string;
  cpu_sockets?: number;
  cpu_cores?: number;
  memory_mb?: number;
  gpu_model?: string;
  gpu_count?: number;
  metadata?: Record<string, unknown>;
}

/** PATCH hardware 输入（Contract §2.4）：子字段级 exclude_unset——
 * 省略子字段 = 保持原值；显式 null = 清空该 nullable 子字段；
 * metadata 为整值替换（非 null）；hardware 整体不可显式 null（422）。 */
export interface HardwarePatch {
  manufacturer?: string | null;
  model?: string | null;
  serial_number?: string | null;
  cpu_model?: string | null;
  cpu_sockets?: number | null;
  cpu_cores?: number | null;
  memory_mb?: number | null;
  gpu_model?: string | null;
  gpu_count?: number | null;
  metadata?: Record<string, unknown>;
}

/** Resource 响应对象（Contract §3）。hostname 为归一化小写展示值；hostname_key 不暴露。 */
export interface Resource {
  id: string;
  cluster: ResourceClusterRef;
  hostname: string;
  resource_type: ResourceType;
  role: ResourceRole;
  status: ResourceStatus;
  description: string | null;
  metadata: Record<string, unknown>;
  /**
   * hardware（Contract §3，v2 新增）：BARE_METAL = Hardware 对象
   * （未登记子字段为 null）；VIRTUAL_MACHINE 恒为 null。
   */
  hardware: Hardware | null;
  version: number;
  created_at: string;
  updated_at: string;
  deleted_at: string | null;
}

/** 列表响应（Contract §4：{items, page, page_size, total}）。 */
export interface ResourceListResponse {
  items: Resource[];
  page: number;
  page_size: number;
  total: number;
}

/** 单对象响应信封（Contract §6.2/§6.3/§6.4/§6.6：{"resource":Resource}）。 */
export interface ResourceEnvelope {
  resource: Resource;
}

/** Activity 条目（Contract §6.7；只读，无修改/删除入口）。 */
export interface ResourceActivityItem {
  id: string;
  action: "CREATE" | "UPDATE" | "DELETE" | "RESTORE";
  operator_user_id: string | null;
  operator_username: string;
  before_data: Record<string, unknown> | null;
  after_data: Record<string, unknown> | null;
  created_at: string;
}

/** Activity 响应（Contract §6.7：created_at 升序、同刻 id 升序）。 */
export interface ResourceActivityResponse {
  items: ResourceActivityItem[];
  page: number;
  page_size: number;
  total: number;
}

/** GET /resources 查询参数（省略项不发，由服务端默认值生效，Contract §4）。 */
export interface ListResourcesQuery {
  /** hostname 大小写不敏感子串匹配（ILIKE，基础搜索，F013 前无 pg_trgm）。 */
  q?: string;
  /** 所属 Cluster code 精确过滤（code_key 大小写不敏感；不存在→空结果）。 */
  cluster?: string;
  /** 所属 Cluster UUID 精确过滤。 */
  cluster_id?: string;
  /** 资源类型过滤（查询参数规范名为 type，无 resource_type 别名）。 */
  type?: ResourceType;
  role?: ResourceRole;
  status?: ResourceStatus;
  deleted?: DeletedMode;
  page?: number;
  page_size?: number;
  sort?: ResourceSortField;
  order?: SortOrder;
}

/** 列表查询：GET /api/v1/resources（READ；deleted=include|only 另需 VIEW_DELETED）。 */
export function listResources(query: ListResourcesQuery = {}): Promise<ResourceListResponse> {
  const search = new URLSearchParams();
  if (query.q !== undefined && query.q !== "") {
    search.set("q", query.q);
  }
  if (query.cluster !== undefined && query.cluster !== "") {
    search.set("cluster", query.cluster);
  }
  if (query.cluster_id !== undefined && query.cluster_id !== "") {
    search.set("cluster_id", query.cluster_id);
  }
  if (query.type !== undefined) {
    search.set("type", query.type);
  }
  if (query.role !== undefined) {
    search.set("role", query.role);
  }
  if (query.status !== undefined) {
    search.set("status", query.status);
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
  return request<ResourceListResponse>(`/resources${queryString ? `?${queryString}` : ""}`);
}

/** POST /resources 请求体（Contract §6.2）。cluster 接受 Cluster UUID 或 code。 */
export interface CreateResourcePayload {
  cluster: string;
  hostname: string;
  resource_type: ResourceType;
  role?: ResourceRole;
  status?: ResourceStatus;
  description?: string | null;
  metadata?: Record<string, unknown>;
  /**
   * hardware（可选；仅 BARE_METAL，Contract §2.4）：整体省略 → 全 null
   * （metadata={}）。VM 载荷不得携带本键（出现即 422，DR-51），
   * 构造方对 VIRTUAL_MACHINE 必须省略该属性（undefined 经 JSON.stringify 丢弃）。
   */
  hardware?: HardwareInput;
}

/** 创建：POST /api/v1/resources（WRITE）；201；同 Cluster hostname 冲突 409 CONFLICT{unique_conflict}。 */
export function createResource(payload: CreateResourcePayload): Promise<ResourceEnvelope> {
  return request<ResourceEnvelope>("/resources", { method: "POST", body: payload });
}

/** 详情：GET /api/v1/resources/{id}（READ）。已删对象需显式 deleted=true 且具 VIEW_DELETED，否则 404（§5）。 */
export function getResource(
  id: string,
  options: { deleted?: boolean } = {},
): Promise<ResourceEnvelope> {
  const search = new URLSearchParams();
  if (options.deleted) {
    search.set("deleted", "true");
  }
  const queryString = search.toString();
  return request<ResourceEnvelope>(
    `/resources/${encodeURIComponent(id)}${queryString ? `?${queryString}` : ""}`,
  );
}

/**
 * PATCH /resources/{id} 请求体（Contract §6.4）。
 * version 必填；其余字段省略 = 保持原值不重置；description 显式 null = 清空；
 * metadata 整值替换；hostname 改后重检唯一；cluster / resource_type 不可改
 * （前端不提供编辑入口，出现即 422）。
 */
export interface UpdateResourcePayload {
  version: number;
  hostname?: string;
  role?: ResourceRole;
  status?: ResourceStatus;
  description?: string | null;
  metadata?: Record<string, unknown>;
  /**
   * hardware（可选；仅 BARE_METAL，Contract §2.4）：子字段级 exclude_unset
   * （省略子字段 = 保持原值；显式 null = 清空该 nullable 子字段）；
   * VM 载荷不得携带本键（出现即 422，DR-51）。
   */
  hardware?: HardwarePatch;
}

/** 部分更新：PATCH /api/v1/resources/{id}（WRITE）；成功 200，version+1。 */
export function updateResource(
  id: string,
  payload: UpdateResourcePayload,
): Promise<ResourceEnvelope> {
  return request<ResourceEnvelope>(`/resources/${encodeURIComponent(id)}`, {
    method: "PATCH",
    body: payload,
  });
}

/** 软删：DELETE /api/v1/resources/{id}?version=N（DELETE_OBJECT；204，不级联）。 */
export function deleteResource(id: string, version: number): Promise<void> {
  const search = new URLSearchParams({ version: String(version) });
  return request<void>(`/resources/${encodeURIComponent(id)}?${search.toString()}`, {
    method: "DELETE",
  });
}

/** 恢复：POST /api/v1/resources/{id}/restore?version=N（RESTORE；200，仅恢复自身，重检唯一与依赖）。 */
export function restoreResource(id: string, version: number): Promise<ResourceEnvelope> {
  const search = new URLSearchParams({ version: String(version) });
  return request<ResourceEnvelope>(
    `/resources/${encodeURIComponent(id)}/restore?${search.toString()}`,
    { method: "POST" },
  );
}

/** 对象 Activity：GET /api/v1/resources/{id}/activity（VIEW_ACTIVITY，全角色）。 */
export function getResourceActivity(
  id: string,
  query: { deleted?: boolean; page?: number; page_size?: number } = {},
): Promise<ResourceActivityResponse> {
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
  return request<ResourceActivityResponse>(
    `/resources/${encodeURIComponent(id)}/activity${queryString ? `?${queryString}` : ""}`,
  );
}

/**
 * 面向页面的写操作错误描述（Contract §1.2/§7）：
 * - 409 VERSION_CONFLICT：versionConflict=true 并携带 current_version；
 *   页面提示刷新后重新操作，绝不静默重试 / 覆盖。
 * - 409 CONFLICT：按 details.reason 映射；unique_conflict 落为 hostname 字段级错误；
 *   dependency_deleted 携带 conflicts（所属 Cluster 列表）。
 * - 422 VALIDATION_ERROR：details.fields → 字段级错误（cluster 缺失/不存在/软删
 *   也固定落在 field="cluster"，Contract §6.2）。
 * - 403 / 404：明确文案（权限不足 / 对象不存在，不泄露存在性细节）。
 */
export interface ResourceActionError {
  message: string;
  code: string | null;
  /** 409 VERSION_CONFLICT（乐观锁过期，需刷新后重改）。 */
  versionConflict: boolean;
  /** 服务器当前版本（VERSION_CONFLICT details.current_version；未知为 null）。 */
  currentVersion: number | null;
  /** 字段级错误（422 fields / 409 CONFLICT unique_conflict 的 field）。 */
  fields: Record<string, string>;
  /** 删除被引用阻止时的引用列表（CONFLICT reference_exists；F004 引用集为空）。 */
  references: { object_type: string; object_id: string; label: string | null }[];
  /** 恢复时所属 Cluster 仍软删的冲突列表（CONFLICT dependency_deleted）。 */
  conflicts: { object_type: string; object_id: string }[];
}

const CONFLICT_REASON_MESSAGES: Record<string, string> = {
  unique_conflict:
    "hostname 与该集群内现存（未删除）资源冲突：归一化（去首尾空白 + ASCII 小写折叠）后相同。跨集群允许同名；已软删资源不占用 hostname，可复用。",
  reference_exists: "仍有其它对象引用该资源，无法删除",
  not_deleted: "该资源未处于已删除状态，无需恢复",
  dependency_deleted: "恢复失败：所属集群仍处于已删除状态，需先恢复集群",
};

/** 把写操作错误归类为页面可直接呈现的结构（不抛出、不重试）。 */
export function describeResourceActionError(error: unknown): ResourceActionError {
  if (!isApiError(error)) {
    // 网络层错误（fetch reject）：固定文案，不伪装成业务结果
    return {
      message: "无法连接服务器，请稍后重试",
      code: null,
      versionConflict: false,
      currentVersion: null,
      fields: {},
      references: [],
      conflicts: [],
    };
  }

  const result: ResourceActionError = {
    message: displayError(error),
    code: error.code,
    versionConflict: false,
    currentVersion: null,
    fields: {},
    references: [],
    conflicts: [],
  };
  const details = error.details ?? {};

  if (error.status === 409 && error.code === "VERSION_CONFLICT") {
    result.versionConflict = true;
    const current = details["current_version"];
    if (typeof current === "number") {
      result.currentVersion = current;
    }
    result.message =
      `该资源已被其他人修改（服务器当前版本 ${result.currentVersion ?? "未知"}）。` +
      "请刷新最新数据后重新操作；系统不会自动重试或覆盖他人修改。";
  } else if (error.status === 409 && error.code === "CONFLICT") {
    const reason = details["reason"];
    if (reason === "unique_conflict") {
      const field = details["field"];
      const fieldName = typeof field === "string" && field !== "" ? field : "hostname";
      result.fields[fieldName] = CONFLICT_REASON_MESSAGES["unique_conflict"];
      result.message = `保存失败：${fieldName} 冲突。`;
    } else if (typeof reason === "string" && reason in CONFLICT_REASON_MESSAGES) {
      result.message = `${CONFLICT_REASON_MESSAGES[reason]}（CONFLICT/${reason}）`;
      if (reason === "reference_exists") {
        result.references = parseReferences(details["references"]);
      }
      if (reason === "dependency_deleted") {
        result.conflicts = parseConflicts(details["conflicts"]);
      }
    } else {
      result.message = `操作冲突：${error.message}（CONFLICT）`;
    }
  } else if (error.status === 422 && error.code === "VALIDATION_ERROR") {
    result.fields = envelopeFieldErrors(error.details);
  } else if (error.status === 403) {
    result.message = "没有权限执行该操作（服务端已拒绝，FORBIDDEN）。";
  } else if (error.status === 404) {
    result.message = "资源不存在，或已删除且您无权查看（NOT_FOUND）。";
  }
  return result;
}

/** 解析 CONFLICT reference_exists 的 references 列表（形状不符返回空数组）。 */
function parseReferences(value: unknown): ResourceActionError["references"] {
  if (!Array.isArray(value)) {
    return [];
  }
  const references: ResourceActionError["references"] = [];
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
function parseConflicts(value: unknown): ResourceActionError["conflicts"] {
  if (!Array.isArray(value)) {
    return [];
  }
  const conflicts: ResourceActionError["conflicts"] = [];
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
