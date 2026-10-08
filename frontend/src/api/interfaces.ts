/**
 * Interface API（F007，Contract：docs/api/F007.md v1，READY）。
 *
 * 端点（Contract §6）：
 * - GET    /interfaces                          列表（分页/排序/过滤/软删可见性，§4/§5）
 * - POST   /interfaces                          创建（201 {"interface":Interface}）
 * - GET    /interfaces/{id}                     详情（?deleted=true 需 VIEW_DELETED）
 * - PATCH  /interfaces/{id}                     部分更新（body 必带 version；resource 不可改）
 * - DELETE /interfaces/{id}?version=N           软删（204；version 为 Query 参数，§6.5）
 * - POST   /interfaces/{id}/restore?version=N   恢复（200，重检 name/Resource/parent）
 * - GET    /interfaces/{id}/activity            对象 Activity（VIEW_ACTIVITY，全角色）
 *
 * 注意：
 * - Interface 为独立可寻址对象（自身 UUID/version/软删/恢复/Activity，DR-84），
 *   不并入 /resources 嵌套；resource 归属创建必填、创建后不可改（DR-79）。
 * - name 区分大小写保留输入、同 Resource 未删唯一、软删后可复用（§2.1）；
 *   mac_address/speed_mbps/mtu/parent_interface/description 可空（显式 null 清空）；
 *   speed_mbps/mtu 为正整数 1..2147483647，未知存 null 不以 0 代替（D01 §5.6）。
 * - PATCH 仅携带变化字段（省略 = 保持原值不重置，Contract §6.4）。
 * - 409 CONFLICT（unique_conflict / not_deleted / dependency_deleted /
 *   reference_exists）/ VERSION_CONFLICT 的页面呈现语义见
 *   describeInterfaceActionError；任何写失败都不自动重试（Contract §7）。
 * - 本文件 import 显式带 .ts 扩展名：scripts/smoke-client.mjs 以 Node
 *   type stripping 直接加载本模块做机制级冒烟（同 src/api/*.ts）。
 */
import { displayError, envelopeFieldErrors, isApiError, request } from "./client.ts";
import type { DeletedMode, SortOrder } from "./clusters.ts";

/** 软删可见性 / 排序方向与 F003 同一语义，复用同一类型定义（Contract §4/§5）。 */
export type { DeletedMode, SortOrder } from "./clusters.ts";

/** 接口类型（Contract §2.2：7 值，默认 OTHER；不据 name 推断，DR-74）。 */
export type InterfaceTypeValue =
  | "PHYSICAL"
  | "VIRTUAL"
  | "BOND"
  | "BRIDGE"
  | "VLAN"
  | "LOOPBACK"
  | "OTHER";

/** 列表排序字段白名单（Contract §4；sort=name 按区分大小写原值）。 */
export type InterfaceSortField =
  | "name"
  | "interface_type"
  | "speed_mbps"
  | "mtu"
  | "created_at"
  | "updated_at";

/** Interface 响应内嵌的所属 Resource 引用（Contract §3：{id, hostname}，只读）。 */
export interface InterfaceResourceRef {
  id: string;
  hostname: string;
}

/** parent_interface 展开引用（Contract §3：{id, name}；无父接口为 null）。 */
export interface InterfaceParentRef {
  id: string;
  name: string;
}

/**
 * Interface 响应对象（Contract §3）。
 * mac_address/speed_mbps/mtu/parent_interface/description 未设置为 null，
 * 绝不以 0 / 空串代替未知（D01 §5.6）；metadata 为 Interface 自有（DR-83）。
 */
export interface Interface {
  id: string;
  resource: InterfaceResourceRef;
  /** 区分大小写保留输入（§2.1；eth0 与 ETH0 为不同名称）。 */
  name: string;
  interface_type: InterfaceTypeValue;
  mac_address: string | null;
  /** 标称速率 Mbps，正整数或 null（非实时探测）。 */
  speed_mbps: number | null;
  /** 单位字节，正整数或 null；未知存 null 不转 0。 */
  mtu: number | null;
  parent_interface: InterfaceParentRef | null;
  /** 登记状态非实时探测，默认 true。 */
  enabled: boolean;
  description: string | null;
  metadata: Record<string, unknown>;
  version: number;
  created_at: string;
  updated_at: string;
  deleted_at: string | null;
}

/** 列表响应（Contract §4：{items, page, page_size, total}）。 */
export interface InterfaceListResponse {
  items: Interface[];
  page: number;
  page_size: number;
  total: number;
}

/** 单对象响应信封（Contract §6.2/§6.3/§6.4/§6.6：{"interface":Interface}）。 */
export interface InterfaceEnvelope {
  interface: Interface;
}

/** Activity 条目（Contract §6.7；只读，无修改/删除入口）。 */
export interface InterfaceActivityItem {
  id: string;
  action: "CREATE" | "UPDATE" | "DELETE" | "RESTORE";
  operator_user_id: string | null;
  operator_username: string;
  before_data: Record<string, unknown> | null;
  after_data: Record<string, unknown> | null;
  created_at: string;
}

/** Activity 响应（Contract §6.7：created_at 升序、同刻 id 升序）。 */
export interface InterfaceActivityResponse {
  items: InterfaceActivityItem[];
  page: number;
  page_size: number;
  total: number;
}

/** GET /interfaces 查询参数（省略项不发，由服务端默认值生效，Contract §4）。 */
export interface ListInterfacesQuery {
  /** 对 name 的大小写敏感子串匹配（特殊字符按字面量转义；空/纯空白视为未提供）。 */
  q?: string;
  /** 所属 Resource UUID 精确过滤（非 UUID → 422；不存在 → 空结果非 404）。 */
  resource_id?: string;
  interface_type?: InterfaceTypeValue;
  enabled?: boolean;
  /** 父接口 UUID 精确过滤（非 UUID → 422；不存在 → 空结果）。 */
  parent_interface_id?: string;
  deleted?: DeletedMode;
  page?: number;
  page_size?: number;
  sort?: InterfaceSortField;
  order?: SortOrder;
}

/** 列表查询：GET /api/v1/interfaces（READ；deleted=include|only 另需 VIEW_DELETED）。 */
export function listInterfaces(
  query: ListInterfacesQuery = {},
): Promise<InterfaceListResponse> {
  const search = new URLSearchParams();
  if (query.q !== undefined && query.q !== "") {
    search.set("q", query.q);
  }
  if (query.resource_id !== undefined && query.resource_id !== "") {
    search.set("resource_id", query.resource_id);
  }
  if (query.interface_type !== undefined) {
    search.set("interface_type", query.interface_type);
  }
  if (query.enabled !== undefined) {
    search.set("enabled", String(query.enabled));
  }
  if (query.parent_interface_id !== undefined && query.parent_interface_id !== "") {
    search.set("parent_interface_id", query.parent_interface_id);
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
  return request<InterfaceListResponse>(`/interfaces${queryString ? `?${queryString}` : ""}`);
}

/**
 * POST /interfaces 请求体（Contract §6.2）。
 * resource/name 必填；interface_type 省略默认 OTHER、enabled 省略默认 true；
 * 可空字段省略 → null（无默认 0）；metadata 默认 {}、整值替换。
 */
export interface CreateInterfacePayload {
  /** 所属 Resource UUID（创建必填、须存在未软删，创建后不可改，DR-79）。 */
  resource: string;
  name: string;
  interface_type?: InterfaceTypeValue;
  mac_address?: string;
  speed_mbps?: number;
  mtu?: number;
  /** 父接口 UUID（须同 Resource、非自身、无环）；省略 = 根接口。 */
  parent_interface?: string;
  enabled?: boolean;
  description?: string;
  metadata?: Record<string, unknown>;
}

/** 创建：POST /api/v1/interfaces（WRITE）；201；同 Resource 未删 name 冲突 409 CONFLICT{unique_conflict,field:"name"}。 */
export function createInterface(payload: CreateInterfacePayload): Promise<InterfaceEnvelope> {
  return request<InterfaceEnvelope>("/interfaces", { method: "POST", body: payload });
}

/** 详情：GET /api/v1/interfaces/{id}（READ）。已删对象需显式 deleted=true 且具 VIEW_DELETED，否则 404（§5）。 */
export function getInterface(
  id: string,
  options: { deleted?: boolean } = {},
): Promise<InterfaceEnvelope> {
  const search = new URLSearchParams();
  if (options.deleted) {
    search.set("deleted", "true");
  }
  const queryString = search.toString();
  return request<InterfaceEnvelope>(
    `/interfaces/${encodeURIComponent(id)}${queryString ? `?${queryString}` : ""}`,
  );
}

/**
 * PATCH /interfaces/{id} 请求体（Contract §6.4）。
 * version 必填；其余字段省略 = 保持原值不重置；可空字段显式 null = 清空；
 * name 改后重检同 Resource 唯一；metadata 整值替换；
 * resource / id / 只读字段不可出现在请求体（前端不提供编辑入口，出现即 422）。
 */
export interface UpdateInterfacePayload {
  version: number;
  name?: string;
  interface_type?: InterfaceTypeValue;
  mac_address?: string | null;
  speed_mbps?: number | null;
  mtu?: number | null;
  /** 显式 null = 清空为根接口；变更时服务端重检同 Resource / 无环。 */
  parent_interface?: string | null;
  enabled?: boolean;
  description?: string | null;
  metadata?: Record<string, unknown>;
}

/** 部分更新：PATCH /api/v1/interfaces/{id}（WRITE）；成功 200，version+1。 */
export function updateInterface(
  id: string,
  payload: UpdateInterfacePayload,
): Promise<InterfaceEnvelope> {
  return request<InterfaceEnvelope>(`/interfaces/${encodeURIComponent(id)}`, {
    method: "PATCH",
    body: payload,
  });
}

/** 软删：DELETE /api/v1/interfaces/{id}?version=N（DELETE_OBJECT；204，不级联；被未删子接口 / IP 引用 → 409 reference_exists）。 */
export function deleteInterface(id: string, version: number): Promise<void> {
  const search = new URLSearchParams({ version: String(version) });
  return request<void>(`/interfaces/${encodeURIComponent(id)}?${search.toString()}`, {
    method: "DELETE",
  });
}

/** 恢复：POST /api/v1/interfaces/{id}/restore?version=N（RESTORE；200，仅恢复自身，重检 name/Resource/parent，不覆盖新对象）。 */
export function restoreInterface(id: string, version: number): Promise<InterfaceEnvelope> {
  const search = new URLSearchParams({ version: String(version) });
  return request<InterfaceEnvelope>(
    `/interfaces/${encodeURIComponent(id)}/restore?${search.toString()}`,
    { method: "POST" },
  );
}

/** 对象 Activity：GET /api/v1/interfaces/{id}/activity（VIEW_ACTIVITY，全角色）。 */
export function getInterfaceActivity(
  id: string,
  query: { deleted?: boolean; page?: number; page_size?: number } = {},
): Promise<InterfaceActivityResponse> {
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
  return request<InterfaceActivityResponse>(
    `/interfaces/${encodeURIComponent(id)}/activity${queryString ? `?${queryString}` : ""}`,
  );
}

/**
 * 面向页面的写操作错误描述（Contract §1.2/§7）：
 * - 409 VERSION_CONFLICT：versionConflict=true 并携带 current_version；
 *   页面提示刷新后重新操作，绝不静默重试 / 覆盖。
 * - 409 CONFLICT：按 details.reason 映射；unique_conflict 落为 name 字段级错误
 *   （field 恒为 "name"，§1.2）；reference_exists 携带 references（未删子
 *   Interface / F010 IPAddress，DR-80/DR-82）；dependency_deleted 携带
 *   conflicts 并按 object_type 区分文案（resource=所属资源 / interface=父接口）；
 *   not_deleted = 对未软删对象 restore。
 * - 422 VALIDATION_ERROR：details.fields → 字段级错误（Interface 为顶层字段，
 *   如 name / mac_address / speed_mbps / mtu / parent_interface / resource，
 *   Contract §2.3）。
 * - 403 / 404：明确文案（权限不足 / 对象不存在，不泄露存在性细节）。
 */
export interface InterfaceActionError {
  message: string;
  code: string | null;
  /** 409 VERSION_CONFLICT（乐观锁过期，需刷新后重改）。 */
  versionConflict: boolean;
  /** 服务器当前版本（VERSION_CONFLICT details.current_version；未知为 null）。 */
  currentVersion: number | null;
  /** 字段级错误（422 fields / 409 CONFLICT unique_conflict 的 field）。 */
  fields: Record<string, string>;
  /** 删除被引用阻止时的引用列表（CONFLICT reference_exists）。 */
  references: { object_type: string; object_id: string; label: string | null }[];
  /** 恢复时依赖仍软删的冲突列表（CONFLICT dependency_deleted）。 */
  conflicts: { object_type: string; object_id: string }[];
}

const CONFLICT_REASON_MESSAGES: Record<string, string> = {
  unique_conflict:
    "name 与该资源内现存（未删除）接口冲突（区分大小写保留输入；已软删接口不占用名称，软删后可复用）",
  not_deleted: "该接口未处于已删除状态，无需恢复",
  reference_exists:
    "仍存在未删除对象引用该接口（子接口 / IP 地址），无法删除；请先删除或迁移这些引用后再试（不隐式级联）",
};

/**
 * dependency_deleted 的文案按 conflicts 的 object_type 区分（Contract §1.2：
 * resource=所属 Resource 仍软删 / 缺失；interface=parent 失效）：恢复失败不覆盖
 * 新对象。冲突列表为空 / 形状不符时用通用文案，不伪装成已知原因。
 */
function dependencyDeletedMessage(
  conflicts: { object_type: string; object_id: string }[],
): string {
  const types = new Set(conflicts.map((conflict) => conflict.object_type));
  if (types.size === 1 && types.has("resource")) {
    return (
      "恢复失败：所属资源（Resource）仍处于已删除状态或已不存在，" +
      "需先恢复所属资源后再恢复该接口（恢复不会覆盖资源或其上新对象）"
    );
  }
  if (types.size === 1 && types.has("interface")) {
    return (
      "恢复失败：父接口（parent_interface）仍处于已删除状态或已不存在，" +
      "需先恢复父接口后再恢复该接口（恢复不会覆盖父接口或其上新对象）"
    );
  }
  return "恢复失败：依赖对象仍处于已删除状态，需先恢复对应依赖对象后再重试";
}

/** 把写操作错误归类为页面可直接呈现的结构（不抛出、不重试）。 */
export function describeInterfaceActionError(error: unknown): InterfaceActionError {
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

  const result: InterfaceActionError = {
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
      `该接口已被其他人修改（服务器当前版本 ${result.currentVersion ?? "未知"}）。` +
      "请刷新最新数据后重新操作；系统不会自动重试或覆盖他人修改。";
  } else if (error.status === 409 && error.code === "CONFLICT") {
    const reason = details["reason"];
    if (reason === "unique_conflict") {
      // field 恒为 "name"（Contract §1.2）；形状不符时回退 name，不伪造其它字段
      const field = details["field"];
      const fieldName = typeof field === "string" && field !== "" ? field : "name";
      result.fields[fieldName] = CONFLICT_REASON_MESSAGES["unique_conflict"];
      result.message = `保存失败：${fieldName} 冲突。`;
    } else if (reason === "dependency_deleted") {
      result.conflicts = parseConflicts(details["conflicts"]);
      result.message = `${dependencyDeletedMessage(result.conflicts)}（CONFLICT/dependency_deleted）`;
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
    result.message = "接口不存在，或已删除且您无权查看（NOT_FOUND）。";
  }
  return result;
}

/** 解析 CONFLICT reference_exists 的 references 列表（形状不符返回空数组）。 */
function parseReferences(value: unknown): InterfaceActionError["references"] {
  if (!Array.isArray(value)) {
    return [];
  }
  const references: InterfaceActionError["references"] = [];
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
function parseConflicts(value: unknown): InterfaceActionError["conflicts"] {
  if (!Array.isArray(value)) {
    return [];
  }
  const conflicts: InterfaceActionError["conflicts"] = [];
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
