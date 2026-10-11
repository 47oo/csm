/**
 * Service API（F011，Contract：docs/api/F011.md v1，READY）。
 *
 * 端点（Contract §6）：
 * - GET    /services                          列表（分页/排序/过滤/软删可见性，§4/§5）
 * - POST   /services                          创建（201 {"service":Service}）
 * - GET    /services/{id}                     详情（?deleted=true 需 VIEW_DELETED）
 * - PATCH  /services/{id}                     部分更新（body 必带 version）
 * - DELETE /services/{id}?version=N           软删（204；删除前调用 Service←
 *                                            ServiceEndpoint 引用检查，F011 默认
 *                                            空集、F012 注册真实 provider，DR-146）
 * - POST   /services/{id}/restore?version=N   恢复（200，重检同 Resource name 唯一、
 *                                            所属 Resource 未软删/存在）
 * - GET    /services/{id}/activity            对象 Activity（VIEW_ACTIVITY，全角色）
 *
 * 注意：
 * - Service 为独立可寻址对象（自身 UUID/version/软删/恢复/Activity，DR-140/DR-149），
 *   归属 Resource 经 resource_id 关联、经 Resource 间接归属 Cluster（无 cluster
 *   过滤参数，DR-153）；Resource 本体不并入。resource 创建必填（引用须存在、
 *   未软删，422 field="resource"）、创建后不可改（PATCH 出现 resource/resource_id
 *   → 422，DR-144，本 client 的 PATCH 载荷恒不含该键）；无 resource_type 限制。
 * - name 大小写不敏感（仅 ASCII A-Z→a-z 折叠）、同 Resource 未删唯一、软删后
 *   可复用（§2.1）；跨 Resource 同名允许。
 * - status ∈ {RUNNING, STOPPED, UNKNOWN} 默认 UNKNOWN；人工维护、非探测、不由
 *   名称或外部监控推导/自动转换（§15/T21）。
 * - description nullable、无长度上限；metadata 必为 JSON object、默认 {}、
 *   整值替换、Service 自有（不并入 Resource 公共 metadata，§2.2/DR-143）。
 * - PATCH 仅携带变化字段（省略 = 保持原值不重置，exclude_unset，§2.4）；
 *   description 显式 null = 清空；name 改后重检同 Resource 唯一。
 * - 409 CONFLICT（unique_conflict / reference_exists / dependency_deleted /
 *   not_deleted）/ VERSION_CONFLICT 的页面呈现语义见 describeServiceActionError；
 *   任何写失败都不自动重试（Contract §7）。
 * - 本文件 import 显式带 .ts 扩展名：scripts/smoke-client.mjs 以 Node
 *   type stripping 直接加载本模块做机制级冒烟（同 src/api/*.ts）。
 */
import { displayError, envelopeFieldErrors, isApiError, request } from "./client.ts";
import type { DeletedMode, SortOrder } from "./clusters.ts";

/** 软删可见性 / 排序方向与 F003 同一语义，复用同一类型定义（Contract §4/§5）。 */
export type { DeletedMode, SortOrder } from "./clusters.ts";

/** 服务登记状态（Contract §2.2：RUNNING|STOPPED|UNKNOWN，创建默认 UNKNOWN；人工维护、非探测，§15/T21）。 */
export type ServiceStatus = "RUNNING" | "STOPPED" | "UNKNOWN";

/** 列表排序字段白名单（Contract §4；sort=name 按 name_key）。 */
export type ServiceSortField = "name" | "status" | "created_at" | "updated_at";

/** Service 响应内嵌的所属 Resource 引用（Contract §3：{id,hostname}，只读）。 */
export interface ServiceResourceRef {
  id: string;
  hostname: string;
}

/**
 * Service 响应对象（Contract §3）。
 * description 未设置为 null，绝不以空串代替（D01 §5.10）；
 * name_key 不暴露；metadata 必为 JSON object（默认 {}，整值替换）。
 */
export interface Service {
  id: string;
  resource: ServiceResourceRef;
  /** 大小写不敏感唯一（同 Resource 未删；仅 ASCII 折叠），保留展示大小写（§2.1）。 */
  name: string;
  status: ServiceStatus;
  description: string | null;
  /** Service 自有 JSON object（DR-143；不并入 Resource 公共 metadata）。 */
  metadata: Record<string, unknown>;
  version: number;
  created_at: string;
  updated_at: string;
  deleted_at: string | null;
}

/** 列表响应（Contract §4：{items, page, page_size, total}）。 */
export interface ServiceListResponse {
  items: Service[];
  page: number;
  page_size: number;
  total: number;
}

/** 单对象响应信封（Contract §6.2/§6.3/§6.4/§6.6：{"service":Service}）。 */
export interface ServiceEnvelope {
  service: Service;
}

/** Activity 条目（Contract §6.7；只读，无修改/删除入口）。 */
export interface ServiceActivityItem {
  id: string;
  action: "CREATE" | "UPDATE" | "DELETE" | "RESTORE";
  operator_user_id: string | null;
  operator_username: string;
  before_data: Record<string, unknown> | null;
  after_data: Record<string, unknown> | null;
  created_at: string;
}

/** Activity 响应（Contract §6.7：created_at 升序、同刻 id 升序）。 */
export interface ServiceActivityResponse {
  items: ServiceActivityItem[];
  page: number;
  page_size: number;
  total: number;
}

/** GET /services 查询参数（省略项不发，由服务端默认值生效，Contract §4）。 */
export interface ListServicesQuery {
  /** 所属 Resource UUID 精确过滤（非 UUID → 422；不存在 → 空结果非 404）。 */
  resource_id?: string;
  status?: ServiceStatus;
  /** 对 name 的大小写不敏感子串匹配（空/纯空白视为未提供；不用 pg_trgm）。 */
  q?: string;
  deleted?: DeletedMode;
  page?: number;
  page_size?: number;
  sort?: ServiceSortField;
  order?: SortOrder;
}

/** 列表查询：GET /api/v1/services（READ；deleted=include|only 另需 VIEW_DELETED）。 */
export function listServices(query: ListServicesQuery = {}): Promise<ServiceListResponse> {
  const search = new URLSearchParams();
  if (query.resource_id !== undefined && query.resource_id !== "") {
    search.set("resource_id", query.resource_id);
  }
  if (query.status !== undefined) {
    search.set("status", query.status);
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
  return request<ServiceListResponse>(`/services${queryString ? `?${queryString}` : ""}`);
}

/**
 * POST /services 请求体（Contract §6.2）。
 * resource/name 必填；status 省略默认 UNKNOWN（表单恒显式携带）；
 * description 省略 → null；metadata 省略 → {}（非空才携带）；
 * resource_id/id/name_key 等不可变 / 只读 / 未知字段不可出现（→ 422）。
 */
export interface CreateServicePayload {
  /** 所属 Resource UUID（创建必填、须存在未软删，§2.2；创建后不可改，DR-144）。 */
  resource: string;
  name: string;
  status?: ServiceStatus;
  description?: string;
  metadata?: Record<string, unknown>;
}

/** 创建：POST /api/v1/services（WRITE）；201；同 Resource name 冲突 409 CONFLICT{unique_conflict}。 */
export function createService(payload: CreateServicePayload): Promise<ServiceEnvelope> {
  return request<ServiceEnvelope>("/services", { method: "POST", body: payload });
}

/** 详情：GET /api/v1/services/{id}（READ）。已删对象需显式 deleted=true 且具 VIEW_DELETED，否则 404（§5）。 */
export function getService(
  id: string,
  options: { deleted?: boolean } = {},
): Promise<ServiceEnvelope> {
  const search = new URLSearchParams();
  if (options.deleted) {
    search.set("deleted", "true");
  }
  const queryString = search.toString();
  return request<ServiceEnvelope>(
    `/services/${encodeURIComponent(id)}${queryString ? `?${queryString}` : ""}`,
  );
}

/**
 * PATCH /services/{id} 请求体（Contract §6.4，exclude_unset）。
 * version 必填；其余字段省略 = 保持原值不重置；description 显式 null = 清空；
 * name 改后重检同 Resource 唯一；metadata 整值替换（不可显式 null → 422，
 * 本类型不提供 null 形态）；resource/resource_id/id/name_key 等不可变 / 只读
 * 字段不可出现在请求体（→ 422，DR-144）。
 */
export interface UpdateServicePayload {
  version: number;
  name?: string;
  status?: ServiceStatus;
  description?: string | null;
  metadata?: Record<string, unknown>;
}

/** 部分更新：PATCH /api/v1/services/{id}（WRITE）；成功 200，version+1。 */
export function updateService(
  id: string,
  payload: UpdateServicePayload,
): Promise<ServiceEnvelope> {
  return request<ServiceEnvelope>(`/services/${encodeURIComponent(id)}`, {
    method: "PATCH",
    body: payload,
  });
}

/**
 * 软删：DELETE /api/v1/services/{id}?version=N（DELETE_OBJECT；204）。
 * 不级联；删除前调用 Service←ServiceEndpoint 引用检查（F011 默认空集；
 * F012 注册真实 provider，DR-146）：有未删 Endpoint → 409
 * CONFLICT{reference_exists,references}。
 */
export function deleteService(id: string, version: number): Promise<void> {
  const search = new URLSearchParams({ version: String(version) });
  return request<void>(`/services/${encodeURIComponent(id)}?${search.toString()}`, {
    method: "DELETE",
  });
}

/**
 * 恢复：POST /api/v1/services/{id}/restore?version=N（RESTORE；200，仅恢复自身）。
 * 重检同 Resource name 唯一、所属 Resource 未软删/存在；失败不覆盖新对象
 * （§6.6/DR-148）；不级联、不自动恢复 Endpoint。
 */
export function restoreService(id: string, version: number): Promise<ServiceEnvelope> {
  const search = new URLSearchParams({ version: String(version) });
  return request<ServiceEnvelope>(
    `/services/${encodeURIComponent(id)}/restore?${search.toString()}`,
    { method: "POST" },
  );
}

/** 对象 Activity：GET /api/v1/services/{id}/activity（VIEW_ACTIVITY，全角色）。 */
export function getServiceActivity(
  id: string,
  query: { deleted?: boolean; page?: number; page_size?: number } = {},
): Promise<ServiceActivityResponse> {
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
  return request<ServiceActivityResponse>(
    `/services/${encodeURIComponent(id)}/activity${queryString ? `?${queryString}` : ""}`,
  );
}

/** reference_exists 冲突明细：删除 Service 被未删 ServiceEndpoint 引用（Contract §1.2；F011 默认空集，F012 起真实，DR-146）。 */
export interface ServiceReferenceItem {
  object_type: string;
  object_id: string;
  label: string | null;
}

/** dependency_deleted 冲突明细：恢复时所属 Resource 仍软删/缺失（Contract §1.2）。 */
export interface ServiceDependencyConflictItem {
  object_type: string;
  object_id: string;
}

/**
 * 面向页面的写操作错误描述（Contract §1.2/§7）：
 * - 409 VERSION_CONFLICT：versionConflict=true 并携带 current_version；
 *   页面提示刷新后重新操作，绝不静默重试 / 覆盖。
 * - 409 CONFLICT：按 details.reason 映射；
 *   unique_conflict 落为 name 字段级错误（field 恒为 "name"，§1.2）；
 *   reference_exists 携带 references（object_type="service_endpoint"，
 *   F011 默认空集、F012 起真实）；
 *   dependency_deleted 携带 conflicts（object_type="resource"，恢复时所属
 *   Resource 仍删 / 缺失，DR-148）；
 *   not_deleted = 对未软删对象 restore。
 * - 422 VALIDATION_ERROR：details.fields → 字段级错误（resource / name /
 *   status / description / metadata，Contract §2.3）。
 * - 403 / 404：明确文案（权限不足 / 对象不存在，不泄露存在性细节）。
 */
export interface ServiceActionError {
  message: string;
  code: string | null;
  /** 409 VERSION_CONFLICT（乐观锁过期，需刷新后重改）。 */
  versionConflict: boolean;
  /** 服务器当前版本（VERSION_CONFLICT details.current_version；未知为 null）。 */
  currentVersion: number | null;
  /** 字段级错误（422 fields / 409 CONFLICT unique_conflict 的 field）。 */
  fields: Record<string, string>;
  /** 删除被未删 ServiceEndpoint 引用阻止时的引用列表（CONFLICT reference_exists）。 */
  references: ServiceReferenceItem[];
  /** 恢复时所属 Resource 仍软删的冲突列表（CONFLICT dependency_deleted）。 */
  dependencyConflicts: ServiceDependencyConflictItem[];
}

const CONFLICT_REASON_MESSAGES: Record<string, string> = {
  unique_conflict:
    "name 与该资源内现存（未删除）服务冲突（大小写不敏感，仅 ASCII 折叠；已软删服务不占用名称，软删后可复用；跨资源允许同名）",
  reference_exists:
    "仍存在未删除的服务端点（ServiceEndpoint）引用该服务，无法删除；请先软删除这些服务端点后再删除服务（不隐式级联）",
  not_deleted: "该服务未处于已删除状态，无需恢复",
};

/** 把写操作错误归类为页面可直接呈现的结构（不抛出、不重试）。 */
export function describeServiceActionError(error: unknown): ServiceActionError {
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
    };
  }

  const result: ServiceActionError = {
    message: displayError(error),
    code: error.code,
    versionConflict: false,
    currentVersion: null,
    fields: {},
    references: [],
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
      `该服务已被其他人修改（服务器当前版本 ${result.currentVersion ?? "未知"}）。` +
      "请刷新最新数据后重新操作；系统不会自动重试或覆盖他人修改。";
  } else if (error.status === 409 && error.code === "CONFLICT") {
    const reason = details["reason"];
    if (reason === "unique_conflict") {
      // field 恒为 "name"（Contract §1.2）；形状不符时回退 name，不伪造其它字段
      const field = details["field"];
      const fieldName = typeof field === "string" && field !== "" ? field : "name";
      result.fields[fieldName] = CONFLICT_REASON_MESSAGES["unique_conflict"];
      result.message = `保存失败：${fieldName} 冲突。`;
    } else if (reason === "reference_exists") {
      // references 为未删 ServiceEndpoint 明细（F011 默认空集，F012 起真实，DR-146）
      result.references = parseReferences(details["references"]);
      result.message = `${CONFLICT_REASON_MESSAGES["reference_exists"]}（CONFLICT/reference_exists）`;
    } else if (reason === "dependency_deleted") {
      result.dependencyConflicts = parseDependencyConflicts(details["conflicts"]);
      result.message =
        "恢复失败：所属资源（resource）仍处于已删除状态或已不存在，" +
        "需先恢复所属资源后再恢复该服务（恢复不会覆盖资源或其上新对象）（CONFLICT/dependency_deleted）";
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
    result.message = "服务不存在，或已删除且您无权查看（NOT_FOUND）。";
  }
  return result;
}

/** 解析 CONFLICT reference_exists 的 references 列表（形状不符返回空数组）。 */
function parseReferences(value: unknown): ServiceReferenceItem[] {
  if (!Array.isArray(value)) {
    return [];
  }
  const references: ServiceReferenceItem[] = [];
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

/** 解析 CONFLICT dependency_deleted 的 conflicts（resource 明细；形状不符返回空数组）。 */
function parseDependencyConflicts(value: unknown): ServiceDependencyConflictItem[] {
  if (!Array.isArray(value)) {
    return [];
  }
  const conflicts: ServiceDependencyConflictItem[] = [];
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
