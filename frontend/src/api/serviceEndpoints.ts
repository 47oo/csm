/**
 * ServiceEndpoint API（F012，Contract：docs/api/F012.md v1，READY）。
 *
 * 端点（Contract §6，共 7 个）：
 * - GET    /service-endpoints                          列表（分页/排序/过滤/软删可见性，§4/§5）
 * - POST   /service-endpoints                          创建（201 {"service_endpoint":ServiceEndpoint}）
 * - GET    /service-endpoints/{id}                     详情（?deleted=true 需 VIEW_DELETED）
 * - PATCH  /service-endpoints/{id}                     部分更新（body 必带 version）
 * - DELETE /service-endpoints/{id}?version=N           软删（204；无子对象引用，删除前无引用检查）
 * - POST   /service-endpoints/{id}/restore?version=N   恢复（RESTORE；200，重检依赖/归属/监听唯一）
 * - GET    /service-endpoints/{id}/activity            对象 Activity（VIEW_ACTIVITY，全角色）
 *
 * 注意：
 * - ServiceEndpoint 为独立可寻址对象（自身 UUID/version/软删/恢复/Activity，
 *   DR-155），非 Service / IPAddress 的 1:1 明细；归属 Service 经 service、
 *   引用 IP 经 ip_address 关联，本对象不并入两者。
 * - service 创建必填（须引用存在、未软删 Service，422 field="service"）、
 *   创建后不可改（PATCH 出现 service/service_id → 422，DR-157，本 client 的
 *   PATCH 载荷恒不含该键）。
 * - ip_address 创建必填（须引用存在、未软删 IPAddress，且该 IP 已绑定
 *   Interface、该 Interface 存在未软删且 interfaces.resource_id ==
 *   services.resource_id（同 Resource ⇒ 同 Cluster），违反 → 422
 *   field="ip_address"，DR-158）；创建后不可改（PATCH 出现
 *   ip_address/ip_address_id → 422，本 client 恒不含）。不支持未绑定 IP、
 *   跨 Resource/跨 Cluster 共享 VIP。
 * - protocol ∈ {TCP,UDP}：仅接受大写规范值、存储大写（DR-160）；显式 null /
 *   其它值（含 "tcp"）→ 422 field="protocol"。
 * - port 整数 1–65535（含端点；0、65536、负数、非整数、显式 null → 422
 *   field="port"）。
 * - description 可选 nullable、无长度上限；显式 null 清空、省略保持。
 * - 无 metadata/name/status/listen_address 字段（I-1/DR-156）：请求含
 *   metadata → 422；响应不含。
 * - PATCH 仅携带变化字段（省略 = 保持原值不重置，exclude_unset，§2.5）。
 * - 监听唯一 = 同一 IPAddress 未删 (protocol,port)（部分唯一，DR-159）：
 *   创建 / PATCH 改 protocol·port / 恢复冲突 → 409 CONFLICT{unique_conflict,
 *   field:"port"}；软删释放；不同 IP 对象各自独立。
 * - 409 CONFLICT（unique_conflict / not_deleted / dependency_deleted /
 *   reference_exists）/ VERSION_CONFLICT 的页面呈现语义见
 *   describeServiceEndpointActionError；任何写失败都不自动重试（Contract §7）。
 * - 本文件 import 显式带 .ts 扩展名：scripts/smoke-client.mjs 以 Node
 *   type stripping 直接加载本模块做机制级冒烟（同 src/api/*.ts）。
 */
import { displayError, envelopeFieldErrors, isApiError, request } from "./client.ts";
import type { DeletedMode, SortOrder } from "./clusters.ts";

/** 软删可见性 / 排序方向与 F003 同一语义，复用同一类型定义（Contract §4/§5）。 */
export type { DeletedMode, SortOrder } from "./clusters.ts";

/** 监听协议（Contract §2.2：TCP|UDP，仅大写规范值；"tcp" 等其它值 → 422）。 */
export type EndpointProtocol = "TCP" | "UDP";

/** 列表排序字段白名单（Contract §4；sort=port 按数值）。 */
export type ServiceEndpointSortField = "protocol" | "port" | "created_at" | "updated_at";

/** ServiceEndpoint 响应内嵌的所属 Service 引用（Contract §3：{id,name,resource{id,hostname}}）。 */
export interface ServiceEndpointServiceRef {
  id: string;
  name: string;
  resource: { id: string; hostname: string };
}

/**
 * ServiceEndpoint 响应内嵌的 IPAddress 引用（Contract §3：
 * {id,address,network{id,name},interface{id,name}}；interface 恒非空——
 * 归属要求 IP 已绑定 Interface，DR-158）。
 */
export interface ServiceEndpointIpAddressRef {
  id: string;
  address: string;
  network: { id: string; name: string };
  interface: { id: string; name: string };
}

/**
 * ServiceEndpoint 响应对象（Contract §3）。
 * description 未设置为 null，绝不以空串代替；响应不含 metadata /
 * 原始 service_id/ip_address_id（I-1/DR-156）。
 */
export interface ServiceEndpoint {
  id: string;
  service: ServiceEndpointServiceRef;
  ip_address: ServiceEndpointIpAddressRef;
  protocol: EndpointProtocol;
  port: number;
  description: string | null;
  version: number;
  created_at: string;
  updated_at: string;
  deleted_at: string | null;
}

/** 列表响应（Contract §4：{items, page, page_size, total}）。 */
export interface ServiceEndpointListResponse {
  items: ServiceEndpoint[];
  page: number;
  page_size: number;
  total: number;
}

/** 单对象响应信封（Contract §6.2/§6.3/§6.4/§6.6：{"service_endpoint":ServiceEndpoint}）。 */
export interface ServiceEndpointEnvelope {
  service_endpoint: ServiceEndpoint;
}

/** Activity 条目（Contract §6.7；只读，无修改/删除入口）。 */
export interface ServiceEndpointActivityItem {
  id: string;
  action: "CREATE" | "UPDATE" | "DELETE" | "RESTORE";
  operator_user_id: string | null;
  operator_username: string;
  before_data: Record<string, unknown> | null;
  after_data: Record<string, unknown> | null;
  created_at: string;
}

/** Activity 响应（Contract §6.7：created_at 升序、同刻 id 升序）。 */
export interface ServiceEndpointActivityResponse {
  items: ServiceEndpointActivityItem[];
  page: number;
  page_size: number;
  total: number;
}

/** GET /service-endpoints 查询参数（省略项不发，由服务端默认值生效，Contract §4）。 */
export interface ListServiceEndpointsQuery {
  /** 所属 Service UUID 精确过滤（非 UUID → 422；不存在 → 空结果非 404）。 */
  service_id?: string;
  /** 引用 IPAddress UUID 精确过滤（非 UUID → 422；不存在 → 空结果非 404）。 */
  ip_address_id?: string;
  protocol?: EndpointProtocol;
  deleted?: DeletedMode;
  page?: number;
  page_size?: number;
  sort?: ServiceEndpointSortField;
  order?: SortOrder;
}

/** 列表查询：GET /api/v1/service-endpoints（READ；deleted=include|only 另需 VIEW_DELETED）。 */
export function listServiceEndpoints(
  query: ListServiceEndpointsQuery = {},
): Promise<ServiceEndpointListResponse> {
  const search = new URLSearchParams();
  if (query.service_id !== undefined && query.service_id !== "") {
    search.set("service_id", query.service_id);
  }
  if (query.ip_address_id !== undefined && query.ip_address_id !== "") {
    search.set("ip_address_id", query.ip_address_id);
  }
  if (query.protocol !== undefined) {
    search.set("protocol", query.protocol);
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
  return request<ServiceEndpointListResponse>(
    `/service-endpoints${queryString ? `?${queryString}` : ""}`,
  );
}

/**
 * POST /service-endpoints 请求体（Contract §6.2）。
 * service/ip_address/protocol/port 必填；description 省略 → null；
 * service_id/ip_address_id/id/metadata 等未列 / 只读 / 未知字段不可出现
 * （→ 422，DR-156/DR-157；表单不提供这些输入）。
 */
export interface CreateServiceEndpointPayload {
  /** 所属 Service UUID（创建必填、须存在未软删，§2.1；创建后不可改，DR-157）。 */
  service: string;
  /** 引用 IPAddress UUID（创建必填、须存在未软删且已绑定同 Resource Interface，§2.1；创建后不可改）。 */
  ip_address: string;
  protocol: EndpointProtocol;
  port: number;
  description?: string;
}

/** 创建：POST /api/v1/service-endpoints（WRITE）；201；同 IP (protocol,port) 冲突 409 CONFLICT{unique_conflict}。 */
export function createServiceEndpoint(
  payload: CreateServiceEndpointPayload,
): Promise<ServiceEndpointEnvelope> {
  return request<ServiceEndpointEnvelope>("/service-endpoints", {
    method: "POST",
    body: payload,
  });
}

/** 详情：GET /api/v1/service-endpoints/{id}（READ）。已删对象需显式 deleted=true 且具 VIEW_DELETED，否则 404（§5）。 */
export function getServiceEndpoint(
  id: string,
  options: { deleted?: boolean } = {},
): Promise<ServiceEndpointEnvelope> {
  const search = new URLSearchParams();
  if (options.deleted) {
    search.set("deleted", "true");
  }
  const queryString = search.toString();
  return request<ServiceEndpointEnvelope>(
    `/service-endpoints/${encodeURIComponent(id)}${queryString ? `?${queryString}` : ""}`,
  );
}

/**
 * PATCH /service-endpoints/{id} 请求体（Contract §6.4，exclude_unset）。
 * version 必填；protocol/port 省略 = 保持原值不重置；description 显式 null =
 * 清空；改 protocol/port 重检监听唯一（排除自身）；service/service_id/
 * ip_address/ip_address_id/id/metadata 等不可变 / 只读 / 未知字段不可出现在
 * 请求体（→ 422，DR-157，本 client 的载荷恒不含这些键）。
 */
export interface UpdateServiceEndpointPayload {
  version: number;
  protocol?: EndpointProtocol;
  port?: number;
  description?: string | null;
}

/** 部分更新：PATCH /api/v1/service-endpoints/{id}（WRITE）；成功 200，version+1。 */
export function updateServiceEndpoint(
  id: string,
  payload: UpdateServiceEndpointPayload,
): Promise<ServiceEndpointEnvelope> {
  return request<ServiceEndpointEnvelope>(
    `/service-endpoints/${encodeURIComponent(id)}`,
    { method: "PATCH", body: payload },
  );
}

/**
 * 软删：DELETE /api/v1/service-endpoints/{id}?version=N（DELETE_OBJECT；204）。
 * 不级联；无子对象引用 Endpoint，删除前无需引用检查（Contract §6.5）。
 */
export function deleteServiceEndpoint(id: string, version: number): Promise<void> {
  const search = new URLSearchParams({ version: String(version) });
  return request<void>(
    `/service-endpoints/${encodeURIComponent(id)}?${search.toString()}`,
    { method: "DELETE" },
  );
}

/**
 * 恢复：POST /api/v1/service-endpoints/{id}/restore?version=N（RESTORE；200，
 * 仅恢复自身不级联）。重检（DR-166）：监听唯一 → Service 依赖 → ip_address
 * 依赖 → 绑定 Interface 依赖（409 dependency_deleted）→ 归属成立（422
 * field="ip_address"）；失败不覆盖新对象；不自动恢复 Service/IP/Interface。
 */
export function restoreServiceEndpoint(
  id: string,
  version: number,
): Promise<ServiceEndpointEnvelope> {
  const search = new URLSearchParams({ version: String(version) });
  return request<ServiceEndpointEnvelope>(
    `/service-endpoints/${encodeURIComponent(id)}/restore?${search.toString()}`,
    { method: "POST" },
  );
}

/** 对象 Activity：GET /api/v1/service-endpoints/{id}/activity（VIEW_ACTIVITY，全角色）。 */
export function getServiceEndpointActivity(
  id: string,
  query: { deleted?: boolean; page?: number; page_size?: number } = {},
): Promise<ServiceEndpointActivityResponse> {
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
  return request<ServiceEndpointActivityResponse>(
    `/service-endpoints/${encodeURIComponent(id)}/activity${queryString ? `?${queryString}` : ""}`,
  );
}

// ---------- 写操作错误描述（Contract §1.2/§7） ----------

/** reference_exists 冲突明细（Contract §1.2；Endpoint 无子对象，本 Feature 操作不产生，防御性解析）。 */
export interface ServiceEndpointReferenceItem {
  object_type: string;
  object_id: string;
  label: string | null;
}

/** dependency_deleted 冲突明细：恢复时 Service / IPAddress / Interface 仍软删或缺失（Contract §1.2）。 */
export interface ServiceEndpointDependencyConflictItem {
  object_type: "service" | "ip_address" | "interface" | string;
  object_id: string;
}

/**
 * 面向页面的写操作错误描述（Contract §1.2/§7）：
 * - 409 VERSION_CONFLICT：versionConflict=true 并携带 current_version；
 *   页面提示刷新后重新操作，绝不静默重试 / 覆盖。
 * - 409 CONFLICT：按 details.reason 映射；
 *   unique_conflict 落为 port 字段级错误（field 恒为 "port"，§1.2）并携带
 *   冲突的 ip_address_id/protocol/port（若服务端提供）；
 *   dependency_deleted 携带 conflicts（object_type=service|ip_address|
 *   interface，恢复时依赖仍软删/缺失，DR-166）；
 *   not_deleted = 对未软删对象 restore；
 *   reference_exists 携带 references（Endpoint 无子对象，正常不出现，防御呈现）。
 * - 422 VALIDATION_ERROR：details.fields → 字段级错误（service / ip_address /
 *   protocol / port / description，Contract §2.4；恢复时归属不成立亦为
 *   field="ip_address"，§6.6）。
 * - 403 / 404：明确文案（权限不足 / 对象不存在，不泄露存在性细节）。
 */
export interface ServiceEndpointActionError {
  message: string;
  code: string | null;
  /** 409 VERSION_CONFLICT（乐观锁过期，需刷新后重改）。 */
  versionConflict: boolean;
  /** 服务器当前版本（VERSION_CONFLICT details.current_version；未知为 null）。 */
  currentVersion: number | null;
  /** 字段级错误（422 fields / 409 CONFLICT unique_conflict 的 field）。 */
  fields: Record<string, string>;
  /** 引用列表（CONFLICT reference_exists；Endpoint 无子对象，正常为空）。 */
  references: ServiceEndpointReferenceItem[];
  /** 恢复时依赖仍软删的冲突列表（CONFLICT dependency_deleted）。 */
  dependencyConflicts: ServiceEndpointDependencyConflictItem[];
}

const CONFLICT_REASON_MESSAGES: Record<string, string> = {
  unique_conflict:
    "该 IP 地址上已存在相同 (protocol, port) 的未删除监听端点（监听唯一按同一 IPAddress 作用域；软删后释放可复用；不同 IP 对象各自独立；恢复会重检且不覆盖新对象）",
  not_deleted: "该监听端点未处于已删除状态，无需恢复",
  reference_exists:
    "该操作被未删除对象的引用阻止（不隐式级联）；请先处理这些引用后再重试",
};

/**
 * dependency_deleted 的文案按 conflicts 的 object_type 区分（Contract §1.2/
 * §6.6/DR-166：service=所属 Service 仍软删/缺失；ip_address=引用的 IP 地址
 * 仍软删/缺失；interface=IP 绑定的接口仍软删/缺失）：恢复失败不覆盖新对象，
 * 不自动恢复依赖。冲突列表为空 / 形状不符时用通用文案，不伪装成已知原因。
 */
function dependencyDeletedMessage(
  conflicts: ServiceEndpointDependencyConflictItem[],
): string {
  const types = new Set(conflicts.map((conflict) => conflict.object_type));
  if (types.size === 1 && types.has("service")) {
    return (
      "恢复失败：所属服务（service）仍处于已删除状态或已不存在，" +
      "需先恢复该服务后再恢复此监听端点（恢复不会覆盖服务或其上新对象）"
    );
  }
  if (types.size === 1 && types.has("ip_address")) {
    return (
      "恢复失败：引用的 IP 地址（ip_address）仍处于已删除状态或已不存在，" +
      "需先恢复该 IP 地址后再恢复此监听端点（恢复不会覆盖 IP 地址或其上新对象）"
    );
  }
  if (types.size === 1 && types.has("interface")) {
    return (
      "恢复失败：IP 地址绑定的接口（interface）仍处于已删除状态或已不存在，" +
      "需先恢复该接口后再恢复此监听端点（恢复不会覆盖接口或其上新对象）"
    );
  }
  return "恢复失败：依赖对象（服务 / IP 地址 / 接口）仍处于已删除状态，需先恢复对应依赖对象后再重试";
}

/** 把写操作错误归类为页面可直接呈现的结构（不抛出、不重试）。 */
export function describeServiceEndpointActionError(
  error: unknown,
): ServiceEndpointActionError {
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

  const result: ServiceEndpointActionError = {
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
      `该监听端点已被其他人修改（服务器当前版本 ${result.currentVersion ?? "未知"}）。` +
      "请刷新最新数据后重新操作；系统不会自动重试或覆盖他人修改。";
  } else if (error.status === 409 && error.code === "CONFLICT") {
    const reason = details["reason"];
    if (reason === "unique_conflict") {
      // field 恒为 "port"（Contract §1.2）；形状不符时回退 port，不伪造其它字段
      const field = details["field"];
      const fieldName = typeof field === "string" && field !== "" ? field : "port";
      // details 另携带 ip_address_id/protocol/port（冲突定位，Contract §1.2）
      const protocol = details["protocol"];
      const port = details["port"];
      const ipId = details["ip_address_id"];
      const listenParts: string[] = [];
      if (typeof protocol === "string") {
        listenParts.push(protocol);
      }
      if (typeof port === "number") {
        listenParts.push(String(port));
      }
      const suffixParts: string[] = [];
      if (listenParts.length > 0) {
        suffixParts.push(listenParts.join("/"));
      }
      if (typeof ipId === "string") {
        suffixParts.push(`ip_address_id=${ipId}`);
      }
      result.fields[fieldName] = CONFLICT_REASON_MESSAGES["unique_conflict"];
      result.message =
        `保存失败：${fieldName} 冲突${suffixParts.length > 0 ? `（${suffixParts.join("，")}）` : ""}。`;
    } else if (reason === "dependency_deleted") {
      result.dependencyConflicts = parseDependencyConflicts(details["conflicts"]);
      result.message = `${dependencyDeletedMessage(result.dependencyConflicts)}（CONFLICT/dependency_deleted）`;
    } else if (reason === "reference_exists") {
      result.references = parseReferences(details["references"]);
      result.message = `${CONFLICT_REASON_MESSAGES["reference_exists"]}（CONFLICT/reference_exists）`;
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
    result.message = "监听端点不存在，或已删除且您无权查看（NOT_FOUND）。";
  }
  return result;
}

/** 解析 CONFLICT reference_exists 的 references 列表（形状不符返回空数组）。 */
function parseReferences(value: unknown): ServiceEndpointReferenceItem[] {
  if (!Array.isArray(value)) {
    return [];
  }
  const references: ServiceEndpointReferenceItem[] = [];
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
function parseDependencyConflicts(
  value: unknown,
): ServiceEndpointDependencyConflictItem[] {
  if (!Array.isArray(value)) {
    return [];
  }
  const conflicts: ServiceEndpointDependencyConflictItem[] = [];
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
